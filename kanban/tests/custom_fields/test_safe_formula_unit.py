# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for AST-based safe formula evaluator and CustomFieldExecutor.test_execute.

KB-AUDIT-10, KANBA-216.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kanban.api.deps import PrincipalContext
from kanban.api.v1.schemas.custom_fields import CustomFieldTestExecuteRequest
from kanban.custom_fields.executor import (
    CustomFieldExecutor,
    _eval_safe_formula,
)


def test_eval_safe_formula_math() -> None:
    """Verify basic arithmetic evaluation."""
    assert _eval_safe_formula("1 + 2 * 3", {}) == 7
    assert _eval_safe_formula("10 - 4 / 2", {}) == 8.0
    assert _eval_safe_formula("2 ** 3", {}) == 8


def test_eval_safe_formula_issue_context() -> None:
    """Verify issue attribute lookups and string operations."""
    ctx = {
        "issue": {
            "key": "KANBA-42",
            "summary": "Implement Custom Fields",
            "state": "IN_PROGRESS",
            "priority": "HIGH",
        }
    }

    # String concatenation
    res = _eval_safe_formula('issue.key + " - " + issue.summary', ctx)
    assert res == "KANBA-42 - Implement Custom Fields"

    # Attribute lookup
    assert _eval_safe_formula("issue.key", ctx) == "KANBA-42"
    assert _eval_safe_formula("issue.state", ctx) == "IN_PROGRESS"

    # Subscript lookup
    assert _eval_safe_formula('issue["priority"]', ctx) == "HIGH"


def test_eval_safe_formula_js_ternary() -> None:
    """Verify JS ternary condition operator conversion."""
    ctx_done = {"issue": {"state": "DONE"}}
    ctx_prog = {"issue": {"state": "IN_PROGRESS"}}

    formula = 'issue.state === "DONE" ? "Completed" : "Pending"'
    assert _eval_safe_formula(formula, ctx_done) == "Completed"
    assert _eval_safe_formula(formula, ctx_prog) == "Pending"


def test_eval_safe_formula_blocks_unsafe_ast() -> None:
    """Verify builtins, imports, functions, and dangerous attributes are rejected."""
    ctx = {"issue": {"key": "TEST-1"}}

    # Disallowed function calls
    assert _eval_safe_formula("__import__('os').system('ls')", ctx) is None
    assert _eval_safe_formula("open('/etc/passwd').read()", ctx) is None
    assert _eval_safe_formula("eval('1+1')", ctx) is None

    # Disallowed dunder attributes
    assert _eval_safe_formula("issue.__class__.__name__", ctx) is None


@pytest.mark.asyncio
async def test_custom_field_executor_test_execute_scalar() -> None:
    """Verify test_execute with scalar: prefix."""
    db_session = AsyncMock()
    executor = CustomFieldExecutor(db_session)

    proj_id = uuid.uuid4()
    project = MagicMock()
    project.id = proj_id
    project.key = "KANBA"

    issue = MagicMock()
    issue.id = uuid.uuid4()
    issue.project_id = proj_id
    issue.summary = "Fix Custom Fields Studio"
    issue.description_markdown = "Test description"
    issue.state_id = uuid.uuid4()
    issue.priority_id = uuid.uuid4()

    caller = MagicMock(spec=PrincipalContext)
    caller.workspace_id = uuid.uuid4()
    caller.user_id = uuid.uuid4()

    req = CustomFieldTestExecuteRequest(
        issue_key="KANBA-216",
        tier="wasm",
        output_format="severity_pill",
        output_format_metadata={},
        script_source='scalar: {"level": "high", "score": 8.8, "label": "8.8 High"}',
    )

    with patch(
        "kanban.custom_fields.executor.resolve_issue_ref", new_callable=AsyncMock
    ) as mock_resolve:
        mock_resolve.return_value = issue
        res = await executor.test_execute(db_session, caller, project, req)

    assert res["status"] == "SUCCESS"
    assert res["value"] == {"level": "high", "score": 8.8, "label": "8.8 High"}
    assert res["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_custom_field_executor_test_execute_formula() -> None:
    """Verify test_execute with formula: prefix."""
    db_session = AsyncMock()
    executor = CustomFieldExecutor(db_session)

    proj_id = uuid.uuid4()
    project = MagicMock()
    project.id = proj_id
    project.key = "KANBA"

    issue = MagicMock()
    issue.id = uuid.uuid4()
    issue.project_id = proj_id
    issue.summary = "Formula Test"
    issue.description_markdown = "Formula Description"
    issue.state_id = uuid.uuid4()
    issue.priority_id = uuid.uuid4()

    caller = MagicMock(spec=PrincipalContext)
    caller.workspace_id = uuid.uuid4()
    caller.user_id = uuid.uuid4()

    req = CustomFieldTestExecuteRequest(
        issue_key="KANBA-100",
        tier="wasm",
        output_format="text",
        output_format_metadata={},
        script_source='formula: issue.key + ": " + issue.summary',
    )

    with patch(
        "kanban.custom_fields.executor.resolve_issue_ref", new_callable=AsyncMock
    ) as mock_resolve:
        mock_resolve.return_value = issue
        res = await executor.test_execute(db_session, caller, project, req)

    assert res["status"] == "SUCCESS"
    assert res["value"] == "KANBA-100: Formula Test"
