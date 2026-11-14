# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Anti-lockout safeguards and exception mapping (KB-P2-09, KB-P2-10, S4.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sqlalchemy import text

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "HANDSHAKE_PROBE_MAX_AGE_SECONDS",
    "LockoutLayer",
    "LockoutPreventedError",
    "assert_local_admin_disable_allowed",
    "extract_lockout_layer",
    "record_external_admin_handshake",
]

HANDSHAKE_PROBE_MAX_AGE_SECONDS: int = 900  # 15 minutes
type LockoutLayer = Literal["db_trigger", "handshake_probe_15m"]


class LockoutPreventedError(Exception):
    """Raised when an operation would violate anti-lockout safeguards."""

    def __init__(self, message: str, layer: LockoutLayer = "db_trigger") -> None:
        """Initialize LockoutPreventedError with diagnostic message and layer."""
        super().__init__(message)
        self.message = message
        self.layer: LockoutLayer = layer
        self.code = "LOCKOUT_PREVENTED"


def extract_lockout_layer(exc: BaseException) -> LockoutLayer:
    """Inspect DB exception or text to determine the lockout layer."""
    exc_str = str(exc)
    if "handshake_probe_15m" in exc_str:
        return "handshake_probe_15m"
    return "db_trigger"


async def record_external_admin_handshake(
    session: AsyncSession,
    card_id: uuid.UUID,
) -> bool:
    """Record verified login handshake on an external SERVER_ADMIN-mapped card."""
    stmt = text("SELECT kb_auth.card_record_admin_handshake(:card_id)")
    result = await session.execute(stmt, {"card_id": card_id})
    return bool(result.scalar_one_or_none())


async def assert_local_admin_disable_allowed(
    session: AsyncSession,
    workspace_id: uuid.UUID | None,
) -> None:
    """Verify Layer 2 safeguard: external card with verified login within 15 minutes.

    Disabling LOCAL_ADMIN requires at least one external (OIDC/OAuth2/LDAP) enabled card
    with a verified SERVER_ADMIN login within the preceding 15 minutes.
    """
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
    result = await session.execute(stmt, {"ws_id": workspace_id})
    has_recent_handshake = bool(result.scalar_one())
    if not has_recent_handshake:
        msg = (
            "Disabling LOCAL_ADMIN requires a verified login on an external card within 15 minutes"
        )
        raise LockoutPreventedError(msg, layer="handshake_probe_15m")
