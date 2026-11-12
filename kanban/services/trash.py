"""Alias for kanban.services.issue_delete providing trash and restore functionality."""

from kanban.services.issue_delete import (
    BlastRadius,
    compute_blast_radius,
    list_trash,
    restore_issue,
    trash_issue,
)

__all__ = [
    "BlastRadius",
    "compute_blast_radius",
    "list_trash",
    "restore_issue",
    "trash_issue",
]
