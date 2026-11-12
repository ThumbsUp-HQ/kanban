# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""LDAP and StartTLS authentication module (KB-P2-07)."""

from kanban.auth.ldap.client import (
    LdapBindError,
    LdapError,
    LdapSearchError,
    LdapTlsError,
    LdapTlsHardClient,
    SearchEntry,
)
from kanban.auth.ldap.config import LdapCardConfig
from kanban.auth.ldap.escape import (
    LdapFilterError,
    escape_dn_value,
    escape_filter_chars,
    escape_filter_value,
    normalize_dn,
    render_user_filter,
)
from kanban.auth.ldap.router import (
    LdapLoginRequest,
)
from kanban.auth.ldap.router import (
    router as auth_ldap_router,
)
from kanban.auth.ldap.service import LdapAuthService
from kanban.auth.ldap.sync import sync_ldap_groups

__all__ = [
    "LdapAuthService",
    "LdapBindError",
    "LdapCardConfig",
    "LdapError",
    "LdapFilterError",
    "LdapLoginRequest",
    "LdapSearchError",
    "LdapTlsError",
    "LdapTlsHardClient",
    "SearchEntry",
    "auth_ldap_router",
    "escape_dn_value",
    "escape_filter_chars",
    "escape_filter_value",
    "normalize_dn",
    "render_user_filter",
    "sync_ldap_groups",
]
