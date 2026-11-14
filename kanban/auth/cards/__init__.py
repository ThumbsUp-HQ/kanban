# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Multi-Card Auth Studio schemas, repository, service, and diagnostics (KB-P2-10)."""

from kanban.auth.cards.handshake import probe_auth_card_handshake
from kanban.auth.cards.lockout import (
    HANDSHAKE_PROBE_MAX_AGE_SECONDS,
    LockoutLayer,
    LockoutPreventedError,
    assert_local_admin_disable_allowed,
    record_external_admin_handshake,
)
from kanban.auth.cards.repository import (
    admin_get,
    admin_list,
    admin_upsert,
    card_rewrap,
    get_for_login,
    list_enabled_public,
    rewrap_all,
    to_admin_schema,
)
from kanban.auth.cards.schemas import (
    AuthCardAdmin,
    AuthCardAdminListResponse,
    AuthCardCreate,
    AuthCardDeleteRequest,
    AuthCardPublic,
    AuthCardPublicListResponse,
    AuthCardReorderRequest,
    AuthCardUpdate,
    HandshakeProbeResult,
)
from kanban.auth.cards.service import AuthCardAdminService

__all__ = [
    "HANDSHAKE_PROBE_MAX_AGE_SECONDS",
    "AuthCardAdmin",
    "AuthCardAdminListResponse",
    "AuthCardAdminService",
    "AuthCardCreate",
    "AuthCardDeleteRequest",
    "AuthCardPublic",
    "AuthCardPublicListResponse",
    "AuthCardReorderRequest",
    "AuthCardUpdate",
    "HandshakeProbeResult",
    "LockoutLayer",
    "LockoutPreventedError",
    "admin_get",
    "admin_list",
    "admin_upsert",
    "assert_local_admin_disable_allowed",
    "card_rewrap",
    "get_for_login",
    "list_enabled_public",
    "probe_auth_card_handshake",
    "record_external_admin_handshake",
    "rewrap_all",
    "to_admin_schema",
]
