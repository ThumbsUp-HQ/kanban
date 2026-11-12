# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""LDAP and StartTLS authentication endpoints re-export (KB-P2-07)."""

from kanban.auth.ldap.router import LdapLoginRequest
from kanban.auth.ldap.router import router as auth_ldap_router

__all__ = ["LdapLoginRequest", "auth_ldap_router"]
