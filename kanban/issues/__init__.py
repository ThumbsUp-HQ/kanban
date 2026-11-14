# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue management services, tree operations, and domain workflows (KB-P4-05, KB-P4-06)."""

from __future__ import annotations

from kanban.issues.tree_service import (
    count_nodes,
    create_issue_tree,
    get_tree_height,
)
from kanban.issues.workflow_service import (
    DefaultWorkflowGateHook,
    GateHoldResult,
    WorkflowGateHook,
    begin_work,
    complete_work,
    get_workflow_gate_hook,
    set_workflow_gate_hook,
    transition_ticket,
)

__all__ = [
    "DefaultWorkflowGateHook",
    "GateHoldResult",
    "WorkflowGateHook",
    "begin_work",
    "complete_work",
    "count_nodes",
    "create_issue_tree",
    "get_tree_height",
    "get_workflow_gate_hook",
    "set_workflow_gate_hook",
    "transition_ticket",
]
