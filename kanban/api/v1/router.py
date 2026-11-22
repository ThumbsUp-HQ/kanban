# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Canonical API v1 router composition (KAN-307 compatibility export)."""

from __future__ import annotations

from kanban.api.v1 import build_v1_router
from kanban.api.v1.admin.audit_shred import router as admin_audit_shred_router
from kanban.api.v1.admin.workload_identities import (
    router as admin_workload_identities_router,
)

__all__ = [
    "admin_audit_shred_router",
    "admin_workload_identities_router",
    "build_v1_router",
]
