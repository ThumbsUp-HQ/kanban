# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Canonical API v1 router composition (KAN-307 compatibility export)."""

from __future__ import annotations

from kanban.api.v1 import build_v1_router
from kanban.api.v1.admin.webhooks import router as admin_webhooks_router
from kanban.api.v1.webhooks_scm import router as webhooks_scm_router

__all__ = [
    "admin_webhooks_router",
    "build_v1_router",
    "webhooks_scm_router",
]
