# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Three-layer anti-lockout safeguards and error mapping (KB-P2-09, S4.3)."""

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

type LockoutLayer = Literal["db_trigger", "handshake_probe_15m"]

LOCKOUT_TYPE_URI = "urn:kanban:problem:lockout-prevented"
_LOCKOUT_PATTERN = re.compile(r"LOCKOUT_PREVENTED:\s*(.+)", re.IGNORECASE)


class LockoutPreventedError(Exception):
    """Raised when an operation is aborted by the three-layer anti-lockout safeguard (S4.3)."""

    def __init__(self, layer: LockoutLayer, detail: str) -> None:
        """Initialize lockout error with safeguard layer and descriptive detail."""
        super().__init__(f"LOCKOUT_PREVENTED: {detail} (layer={layer})")
        self.layer: LockoutLayer = layer
        self.detail: str = detail

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


async def record_external_admin_handshake(session: AsyncSession, card_id: uuid.UUID) -> None:
    """Record verified login handshake on an external SERVER_ADMIN-mapped IdP card."""
    await session.execute(
        text("SELECT kb_auth.card_record_admin_handshake(:card_id)"),
        {"card_id": card_id},
    )


async def assert_local_admin_disable_allowed(
    session: AsyncSession,
    card_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
) -> None:
    """Validate that disabling or deleting a card satisfies anti-lockout safeguards in Python.

    Layers evaluated:
    1. Layer 2: Disabling LOCAL_ADMIN requires verified external admin handshake within 15m.
    2. Layer 1: Disabling any card cannot leave zero enabled cards capable of auth.
    """
    card = await session.get(AuthProviderCard, card_id)
    if card is None:
        return

    ws_id = workspace_id or card.workspace_id

    # 1. Does workspace have active SERVER_ADMIN? (bootstrap check)
    has_active_admin = (
        await session.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM principals p "
                "  JOIN role_bindings rb ON rb.principal_id = p.id "
                "  WHERE p.status = 'ACTIVE' "
                "    AND rb.role = 'SERVER_ADMIN' "
                "    AND (CAST(:ws_id AS uuid) IS NULL OR rb.workspace_id = CAST(:ws_id AS uuid))"
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
                    "    AND c.last_admin_handshake_at >= clock_timestamp() - interval '15 minutes'"
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
                text("SELECT kb_auth.card_can_authenticate_active_server_admin(:cid, :kind, :ws)"),
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
