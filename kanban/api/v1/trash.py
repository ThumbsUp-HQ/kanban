"""Alias for kanban.api.v1.issue_delete providing trash and restore router."""

from kanban.api.v1.issue_delete import (
    delete_issue,
    delete_preview,
    list_trash,
    restore_issue,
    router,
)

__all__ = [
    "delete_issue",
    "delete_preview",
    "list_trash",
    "restore_issue",
    "router",
]
