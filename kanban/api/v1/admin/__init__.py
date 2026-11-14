# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Admin REST API router package."""

from kanban.api.v1.admin.link_auditor import router as link_auditor_router

__all__ = ["link_auditor_router"]
