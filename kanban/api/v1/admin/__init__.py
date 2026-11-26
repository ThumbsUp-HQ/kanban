# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Admin REST API router package."""

from kanban.api.v1.admin.default_workflow_hooks import (
    router as default_workflow_hooks_router,
)
from kanban.api.v1.admin.default_workflow_hooks import (
    workspace_router as workspace_default_workflow_hooks_router,
)
from kanban.api.v1.admin.link_auditor import router as link_auditor_router

__all__ = [
    "default_workflow_hooks_router",
    "link_auditor_router",
    "workspace_default_workflow_hooks_router",
]
