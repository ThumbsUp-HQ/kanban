# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""LDAP group synchronization re-exports (KB-P2-07)."""

from kanban.auth.ldap.sync import sync_ldap_groups

__all__ = ["sync_ldap_groups"]
