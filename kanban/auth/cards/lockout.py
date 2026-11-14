# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Anti-lockout safeguards and exception mapping (KB-P2-09, KB-P2-10, S4.3)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from database.models.auth import AuthProviderCard
from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    import uuid

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


async def assert_local_admin_disable_allowed(  # noqa: C901, PLR0912
    session: AsyncSession,
    card_id_or_workspace: uuid.UUID | None,
    workspace_id: uuid.UUID | None = None,
) -> None:
    """Validate that disabling or deleting a card satisfies anti-lockout safeguards.

    Supports both (session, card_id, workspace_id) and (session, workspace_id) calling patterns.
    """
    target_ws_id: uuid.UUID | None
    if workspace_id is not None:
        card_id = card_id_or_workspace
        target_ws_id = workspace_id
    elif card_id_or_workspace is not None:
        # Check if card_id_or_workspace matches a card in DB
        maybe_card = await session.get(AuthProviderCard, card_id_or_workspace)
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
        card = await session.get(AuthProviderCard, card_id)
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
            has_valid_external = (
                await session.execute(
                    text(
                        "SELECT EXISTS ("
                        "  SELECT 1 FROM auth_provider_cards c "
                        "  WHERE (CAST(:ws_id AS uuid) IS NULL OR "
                        "         c.workspace_id = CAST(:ws_id AS uuid)) "
                        "    AND c.id <> :card_id "
                        "    AND c.provider_kind IN ('OIDC', 'OAUTH2', 'LDAP') "
                        "    AND c.is_enabled = TRUE "
                        "    AND kb_auth.card_can_authenticate_active_server_admin("
                        "          c.id, c.provider_kind, c.workspace_id"
                        "        ) "
                        "    AND c.last_admin_handshake_at IS NOT NULL "
                        "    AND c.last_admin_handshake_at >= "
                        "          clock_timestamp() - interval '15 minutes'"
                        ")"
                    ),
                    {"ws_id": ws_id, "card_id": card_id},
                )
            ).scalar_one()

            if not has_valid_external:
                raise LockoutPreventedError(
                    layer="handshake_probe_15m",
                    detail=(
                        "disabling LOCAL_ADMIN requires a verified external "
                        "SERVER_ADMIN login within 15 minutes"
                    ),
                )

        # 3. Layer 1: Check remaining enabled admin-capable cards
        enabled_cards = (
            (
                await session.execute(
                    select(AuthProviderCard).where(
                        AuthProviderCard.is_enabled.is_(True),
                        (AuthProviderCard.workspace_id == ws_id)
                        if ws_id is not None
                        else (AuthProviderCard.workspace_id.is_(None)),
                    )
                )
            )
            .scalars()
            .all()
        )

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
        stmt = text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM auth_provider_cards "
            "  WHERE (workspace_id IS NOT DISTINCT FROM :ws_id) "
            "    AND provider_kind IN ('OIDC', 'OAUTH2', 'LDAP') "
            "    AND is_enabled = TRUE "
            "    AND last_admin_handshake_at IS NOT NULL "
            "    AND last_admin_handshake_at >= clock_timestamp() - INTERVAL '15 minutes'"
            ")"
        )
        result = await session.execute(stmt, {"ws_id": target_ws_id})
        has_recent_handshake = bool(result.scalar_one())
        if not has_recent_handshake:
            msg = (
                "Disabling LOCAL_ADMIN requires a verified login on an external "
                "card within 15 minutes"
            )
            raise LockoutPreventedError(msg, layer="handshake_probe_15m")
