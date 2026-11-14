# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue management services and tree operations (KB-P4-05)."""

from __future__ import annotations

from kanban.issues.tree_service import (
    count_nodes,
    create_issue_tree,
    get_tree_height,
)

__all__ = [
    "count_nodes",
    "create_issue_tree",
    "get_tree_height",
]
