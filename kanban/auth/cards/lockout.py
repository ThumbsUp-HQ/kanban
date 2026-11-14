# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Anti-lockout safeguards and exception mapping (KB-P2-09, KB-P2-10, S4.3)."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Final, Literal

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from database.models.auth import AuthProviderCard
from kanban.api.problems import ProblemException
from kanban.auth.cards.repository import admin_get, admin_list

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "HANDSHAKE_PROBE_MAX_AGE_SECONDS",
    "LOCKOUT_TYPE_URI",
    "LockoutLayer",
    "LockoutPreventedError",
    "assert_local_admin_disable_allowed",
    "extract_lockout_layer",
    "map_sqlstate_to_lockout_error",
    "record_external_admin_handshake",
]

HANDSHAKE_PROBE_MAX_AGE_SECONDS: int = 900  # 15 minutes
type LockoutLayer = Literal["db_trigger", "handshake_probe_15m"]

LOCKOUT_TYPE_URI = "urn:kanban:problem:lockout-prevented"
_LOCKOUT_PATTERN = re.compile(r"LOCKOUT_PREVENTED:\s*(.+)", re.IGNORECASE)


class LockoutPreventedError(Exception):
    """Raised when an operation would violate anti-lockout safeguards (S4.3)."""

    def __init__(
        self,
        message_or_layer: str | LockoutLayer = "",
        layer: LockoutLayer = "db_trigger",
        *,
        detail: str | None = None,
    ) -> None:
        """Initialize LockoutPreventedError supporting both positional and keyword invocations."""
        if message_or_layer in ("db_trigger", "handshake_probe_15m") and detail is not None:
            actual_layer: LockoutLayer = message_or_layer
            actual_detail = detail
        elif detail is not None:
            actual_layer = layer
            actual_detail = detail
        else:
            actual_layer = layer
            actual_detail = str(message_or_layer)

        super().__init__(f"LOCKOUT_PREVENTED: {actual_detail} (layer={actual_layer})")
        self.layer: LockoutLayer = actual_layer
        self.detail: str = actual_detail
        self.message: str = actual_detail
        self.code: str = "LOCKOUT_PREVENTED"

    def to_problem_exception(self) -> ProblemException:
        """Map to canonical RFC 7807 ProblemException with status 409 and layer extension."""
        return ProblemException(
            code="LOCKOUT_PREVENTED",
            status=409,
            title="Lockout Prevented",
            detail=self.detail,
            type_uri=LOCKOUT_TYPE_URI,
            extra={"layer": self.layer},
        )


def extract_lockout_layer(exc: BaseException) -> LockoutLayer:
    """Inspect DB exception or text to determine the lockout layer."""
    exc_str = str(exc)
    if "handshake_probe_15m" in exc_str:
        return "handshake_probe_15m"
    return "db_trigger"


def map_sqlstate_to_lockout_error(exc: Exception) -> LockoutPreventedError | None:
    """Parse PostgreSQL exception (SQLSTATE P0001) for LOCKOUT_PREVENTED triggers."""
    target: BaseException = (
        exc.orig if (isinstance(exc, DBAPIError) and exc.orig is not None) else exc
    )

    msg = str(target)
    sqlstate = getattr(target, "sqlstate", None) or getattr(target, "pgcode", None)
    detail_field = getattr(target, "detail", None)

    # Check for P0001 or LOCKOUT_PREVENTED in exception text
    if "LOCKOUT_PREVENTED" in msg or sqlstate == "P0001":
        layer: LockoutLayer = "db_trigger"
        if detail_field == "handshake_probe_15m" or "handshake_probe_15m" in msg:
            layer = "handshake_probe_15m"
        elif detail_field == "db_trigger" or "db_trigger" in msg:
            layer = "db_trigger"

        match = _LOCKOUT_PATTERN.search(msg)
        if match:
            detail_text = match.group(1).split("(layer=")[0].strip().rstrip("'\"")
        else:
            detail_text = (
                "disabling LOCAL_ADMIN requires a verified external SERVER_ADMIN login "
                "within 15 minutes"
                if layer == "handshake_probe_15m"
                else "zero enabled cards can authenticate an active SERVER_ADMIN"
            )

        return LockoutPreventedError(layer=layer, detail=detail_text)

    return None


async def record_external_admin_handshake(
    session: AsyncSession,
    card_id: uuid.UUID,
) -> bool:
    """Record verified login handshake on an external SERVER_ADMIN-mapped IdP card."""
    stmt = text("SELECT kb_auth.card_record_admin_handshake(:card_id)")
    result = await session.execute(stmt, {"card_id": card_id})
    return bool(result.scalar_one_or_none())


_UNSET: Final[object] = object()


async def _can_use_kb_auth_admin(session: AsyncSession) -> bool:
    """Return True when the session carries SERVER_ADMIN + AAL2 RLS context."""
    stmt = text(
        "SELECT ("
        "  EXISTS ("
        "    SELECT 1 FROM role_bindings rb "
        "    WHERE rb.principal_id = ANY (app_effective_principal_set()) "
        "      AND rb.role = 'SERVER_ADMIN'"
        "  ) AND current_setting('app.aal_level', true) = '2'"
        ")"
    )
    return bool((await session.execute(stmt)).scalar_one())


async def _fetch_card(session: AsyncSession, card_id: uuid.UUID) -> AuthProviderCard | None:
    """Fetch a card via kb_auth.card_admin_get under RLS or direct ORM in raw test sessions."""
    if await _can_use_kb_auth_admin(session):
        return await admin_get(session, card_id)
    return await session.get(AuthProviderCard, card_id)


async def _fetch_all_cards(session: AsyncSession) -> list[AuthProviderCard]:
    """List cards via kb_auth.card_admin_list under RLS or direct ORM in raw test sessions."""
    if await _can_use_kb_auth_admin(session):
        return await admin_list(session)
    rows = (await session.execute(select(AuthProviderCard))).scalars().all()
    return list(rows)


async def assert_local_admin_disable_allowed(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    card_id_or_workspace: uuid.UUID | None,
    workspace_id: uuid.UUID | object | None = _UNSET,
) -> None:
    """Validate that disabling or deleting a card satisfies anti-lockout safeguards.

    Supports both (session, card_id, workspace_id) and (session, workspace_id) calling patterns.
    """
    target_ws_id: uuid.UUID | None
    if workspace_id is not _UNSET:
        card_id = card_id_or_workspace
        target_ws_id = workspace_id if isinstance(workspace_id, uuid.UUID) else None
    elif card_id_or_workspace is not None:
        # Check if card_id_or_workspace matches a card in DB
        maybe_card = await _fetch_card(session, card_id_or_workspace)
        if maybe_card is not None:
            card_id = card_id_or_workspace
            target_ws_id = maybe_card.workspace_id
        else:
            card_id = None
            target_ws_id = card_id_or_workspace
    else:
        card_id = None
        target_ws_id = None

    if card_id is not None:
        card = await _fetch_card(session, card_id)
        if card is None:
            return

        ws_id = target_ws_id or card.workspace_id

        # 1. Does workspace have active SERVER_ADMIN? (bootstrap check)
        has_active_admin = (
            await session.execute(
                text(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM principals p "
                    "  JOIN role_bindings rb ON rb.principal_id = p.id "
                    "  WHERE p.status = 'ACTIVE' "
                    "    AND rb.role = 'SERVER_ADMIN' "
                    "    AND (CAST(:ws_id AS uuid) IS NULL "
                    "         OR rb.workspace_id = CAST(:ws_id AS uuid))"
                    ")"
                ),
                {"ws_id": ws_id},
            )
        ).scalar_one()

        if not has_active_admin:
            return

        # 2. Layer 2: If disabling LOCAL_ADMIN, verify live 15-minute external handshake
        if card.provider_kind == "LOCAL_ADMIN" and card.is_enabled:
            all_cards = await _fetch_all_cards(session)
            has_valid_external = False
            for c in all_cards:
                if c.id == card_id:
                    continue
                if ws_id is not None and c.workspace_id is not None and c.workspace_id != ws_id:
                    continue
                if c.provider_kind not in ("OIDC", "OAUTH2", "LDAP") or not c.is_enabled:
                    continue
                if c.last_admin_handshake_at is None:
                    continue
                can_auth = (
                    await session.execute(
                        text(
                            "SELECT kb_auth.card_can_authenticate_active_server_admin("
                            ":cid, :kind, :ws)"
                        ),
                        {"cid": c.id, "kind": c.provider_kind, "ws": c.workspace_id},
                    )
                ).scalar_one()
                if not can_auth:
                    continue
                is_recent = (
                    await session.execute(
                        text("SELECT :ts >= clock_timestamp() - interval '15 minutes'"),
                        {"ts": c.last_admin_handshake_at},
                    )
                ).scalar_one()
                if is_recent:
                    has_valid_external = True
                    break

            if not has_valid_external:
                raise LockoutPreventedError(
                    layer="handshake_probe_15m",
                    detail=(
                        "disabling LOCAL_ADMIN requires a verified external "
                        "SERVER_ADMIN login within 15 minutes"
                    ),
                )

        # 3. Layer 1: Check remaining enabled admin-capable cards
        all_cards = await _fetch_all_cards(session)
        enabled_cards = [
            c
            for c in all_cards
            if c.is_enabled and (ws_id is None or c.workspace_id is None or c.workspace_id == ws_id)
        ]

        remaining_admin_cards = 0
        for c in enabled_cards:
            if c.id == card_id:
                continue
            can_auth = (
                await session.execute(
                    text(
                        "SELECT kb_auth.card_can_authenticate_active_server_admin(:cid, :kind, :ws)"
                    ),
                    {"cid": c.id, "kind": c.provider_kind, "ws": c.workspace_id},
                )
            ).scalar_one()
            if can_auth:
                remaining_admin_cards += 1

        if remaining_admin_cards == 0:
            raise LockoutPreventedError(
                layer="db_trigger",
                detail="zero enabled cards can authenticate an active SERVER_ADMIN",
            )
    else:
        # Workspace-level check when card_id is not provided
        all_cards = await _fetch_all_cards(session)
        has_recent_handshake = False
        for c in all_cards:
            if (
                target_ws_id is not None
                and c.workspace_id is not None
                and c.workspace_id != target_ws_id
            ):
                continue
            if c.provider_kind not in ("OIDC", "OAUTH2", "LDAP") or not c.is_enabled:
                continue
            if c.last_admin_handshake_at is None:
                continue
            is_recent = (
                await session.execute(
                    text("SELECT :ts >= clock_timestamp() - interval '15 minutes'"),
                    {"ts": c.last_admin_handshake_at},
                )
            ).scalar_one()
            if is_recent:
                has_recent_handshake = True
                break

        if not has_recent_handshake:
            msg = (
                "Disabling LOCAL_ADMIN requires a verified login on an external "
                "card within 15 minutes"
            )
            raise LockoutPreventedError(msg, layer="handshake_probe_15m")
