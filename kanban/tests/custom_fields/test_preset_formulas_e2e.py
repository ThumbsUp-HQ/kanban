# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Full-stack integration tests for Starter Formula Presets (KAN-15, KB-P3-AUDIT-09).

Verifies that all formula presets from presets.ts execute through CustomFieldExecutor
and pass validate_output_for_format across multiple issue states.
"""

from __future__ import annotations

import ast
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from database.models import (
    CustomFieldDefinition,
    Project,
)
from kanban.api.deps import PrincipalContext
from kanban.api.v1.schemas.custom_fields import CustomFieldTestExecuteRequest
from kanban.custom_fields.executor import (
    CustomFieldExecutor,
    _check_formula_ast_bounds,
    _convert_js_ternary,
    _eval_safe_formula,
    _strip_outer_parens,
    build_issue_context,
)
from kanban.custom_fields.manifest import compute_field_manifest_sha256
from kanban.custom_fields.output_formats import (
    parse_output_format_metadata,
    validate_field_output_value,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.committed_db

PRESETS_PATH = (
    Path(__file__).resolve().parents[2]
    / "web"
    / "src"
    / "features"
    / "custom-fields"
    / "presets.ts"
)


def _load_formula_presets_from_file() -> dict[str, dict[str, Any]]:
    """Parse starter formula presets directly from presets.ts on disk."""
    content = PRESETS_PATH.read_text(encoding="utf-8")
    formula_presets: dict[str, dict[str, Any]] = {}

    for raw_block in content.split("{\n    id:"):
        if not raw_block.strip():
            continue
        block = "id:" + raw_block
        id_m = re.search(r"id:\s*['\"]([^'\"]+)['\"]", block)
        flavor_m = re.search(r"flavor:\s*['\"]([^'\"]+)['\"]", block)
        fmt_m = re.search(r"outputFormat:\s*['\"]([^'\"]+)['\"]", block)
        script_m = re.search(r"scriptSource:\s*\n\s*(?:'([^']+)'|\"([^\"]+)\"),", block)

        if id_m and flavor_m and flavor_m.group(1) == "formula" and script_m and fmt_m:
            pid = id_m.group(1)
            fmt = fmt_m.group(1)
            script = script_m.group(1) or script_m.group(2)

            # Metadata extraction
            if pid == "days-until-due-sla":
                metadata: dict[str, Any] = {}
            elif pid == "blocker-count":
                metadata = {"color_token": "danger", "allowed_labels": ["Blocked", "Clear"]}
            elif pid == "sub-issue-completion":
                metadata = {"maximum_fraction_digits": 1, "unit_suffix": "%"}
            else:
                metadata = {}

            formula_presets[pid] = {
                "id": pid,
                "output_format": fmt,
                "script_source": script,
                "metadata": metadata,
            }

    return formula_presets


def test_presets_ts_discovery_and_ast_bounds() -> None:
    """Verify that all 3 formula presets are present, start with 'formula:', and pass AST bounds."""
    presets = _load_formula_presets_from_file()
    assert len(presets) == 3, f"Expected 3 formula presets, found: {list(presets.keys())}"
    assert "days-until-due-sla" in presets
    assert "blocker-count" in presets
    assert "sub-issue-completion" in presets

    for pid, p in presets.items():
        src = p["script_source"]
        assert src.startswith("formula:"), f"Preset {pid} does not start with 'formula:'"
        expr = src[len("formula:") :].strip()

        # AST Bounds validation
        parsed = ast.parse(expr, mode="eval")
        assert _check_formula_ast_bounds(parsed.body), (
            f"Preset {pid} formula exceeded AST depth or node count limits"
        )


def test_preset_formulas_across_all_issue_states() -> None:  # noqa: C901, PLR0912
    """Evaluate all formula presets across multiple issue states proving 0 failures."""
    presets = _load_formula_presets_from_file()

    # Define diverse matrix of issue states
    issue_states: dict[str, dict[str, Any]] = {
        "overdue": {
            "days_until_due": -3,
            "due_date": "2026-11-17",
            "priority": "LOW",
            "priority_slug": "low",
            "state": "Backlog",
            "blocker_count": 0,
            "sub_issue_count": 0,
            "completed_sub_issue_count": 0,
        },
        "due_soon": {
            "days_until_due": 1,
            "due_date": "2026-11-21",
            "priority": "LOW",
            "priority_slug": "low",
            "state": "Backlog",
            "blocker_count": 0,
            "sub_issue_count": 0,
            "completed_sub_issue_count": 0,
        },
        "no_due_date": {
            "days_until_due": None,
            "due_date": None,
            "priority": "LOW",
            "priority_slug": "low",
            "state": "Backlog",
            "blocker_count": 0,
            "sub_issue_count": 0,
            "completed_sub_issue_count": 0,
        },
        "urgent_priority": {
            "days_until_due": None,
            "due_date": None,
            "priority": "URGENT",
            "priority_slug": "urgent",
            "state": "Backlog",
            "blocker_count": 0,
            "sub_issue_count": 0,
            "completed_sub_issue_count": 0,
        },
        "high_priority": {
            "days_until_due": 10,
            "due_date": "2026-11-30",
            "priority": "HIGH",
            "priority_slug": "high",
            "state": "Backlog",
            "blocker_count": 0,
            "sub_issue_count": 0,
            "completed_sub_issue_count": 0,
        },
        "blockers_positive": {
            "days_until_due": None,
            "due_date": None,
            "priority": "LOW",
            "priority_slug": "low",
            "state": "In Progress",
            "blocker_count": 3,
            "sub_issue_count": 0,
            "completed_sub_issue_count": 0,
        },
        "blockers_zero": {
            "days_until_due": None,
            "due_date": None,
            "priority": "LOW",
            "priority_slug": "low",
            "state": "In Progress",
            "blocker_count": 0,
            "sub_issue_count": 0,
            "completed_sub_issue_count": 0,
        },
        "cancelled_state": {
            "days_until_due": None,
            "due_date": None,
            "priority": "LOW",
            "priority_slug": "low",
            "state": "CANCELLED",
            "blocker_count": 0,
            "sub_issue_count": 0,
            "completed_sub_issue_count": 0,
        },
        "sub_issues_zero_todo": {
            "days_until_due": None,
            "due_date": None,
            "priority": "LOW",
            "priority_slug": "low",
            "state": "Todo",
            "blocker_count": 0,
            "sub_issue_count": 0,
            "completed_sub_issue_count": 0,
        },
        "sub_issues_zero_done": {
            "days_until_due": None,
            "due_date": None,
            "priority": "LOW",
            "priority_slug": "low",
            "state": "DONE",
            "blocker_count": 0,
            "sub_issue_count": 0,
            "completed_sub_issue_count": 0,
        },
        "sub_issues_positive": {
            "days_until_due": None,
            "due_date": None,
            "priority": "LOW",
            "priority_slug": "low",
            "state": "In Progress",
            "blocker_count": 0,
            "sub_issue_count": 4,
            "completed_sub_issue_count": 3,
        },
    }

    for pid, p in presets.items():
        fmt = p["output_format"]
        parsed_meta = parse_output_format_metadata(fmt, p["metadata"])

        for sname, ctx in issue_states.items():
            raw_val = _eval_safe_formula(p["script_source"], ctx)
            assert raw_val is not None, (
                f"Formula '{pid}' returned None on issue state '{sname}'"
            )

            # Validate against schema
            validated = validate_field_output_value(fmt, parsed_meta, raw_val)
            assert validated is not None

            # Check specific expectations
            if pid == "days-until-due-sla":
                assert isinstance(validated, dict)
                assert "level" in validated
                assert validated["level"] in ("low", "medium", "high", "critical")
                if sname in ("overdue", "urgent_priority"):
                    assert validated["level"] == "critical"
                elif sname in ("due_soon", "high_priority"):
                    assert validated["level"] == "high"
                elif sname in ("no_due_date", "blockers_zero"):
                    assert validated["level"] == "low"

            elif pid == "blocker-count":
                assert isinstance(validated, str)
                assert validated in ("Blocked", "Clear")
                if sname in ("blockers_positive", "cancelled_state"):
                    assert validated == "Blocked"
                elif sname in ("blockers_zero", "no_due_date"):
                    assert validated == "Clear"

            elif pid == "sub-issue-completion":
                assert isinstance(validated, (int, float))
                if sname == "sub_issues_positive":
                    assert validated == 75.0
                elif sname == "sub_issues_zero_done":
                    assert validated == 100.0
                elif sname == "sub_issues_zero_todo":
                    assert validated == 0.0


@pytest.mark.asyncio
async def test_preset_formulas_end_to_end_in_executor(
    db_session: AsyncSession,
) -> None:
    """Verify live CustomFieldExecutor.execute_for_issue on PostgreSQL for all 3 formula presets."""
    ws_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    iss_id = uuid.uuid4()

    await db_session.execute(text("RESET SESSION AUTHORIZATION"))
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Custom Fields Test WS"},
    )

    await db_session.execute(
        text("SELECT register_object('user'::object_kind, :ws, NULL, :ckey, :name, :uid, :id)"),
        {
            "ws": ws_id,
            "ckey": f"usr-{admin_id.hex[:8]}",
            "name": "Admin",
            "uid": admin_id,
            "id": admin_id,
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'USER', :name)"
        ),
        {"id": admin_id, "ws_id": ws_id, "name": "Admin"},
    )
    await db_session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
        {"id": admin_id, "ws_id": ws_id, "email": f"{admin_id.hex[:8]}@example.com"},
    )

    # Register project TFP
    await db_session.execute(
        text(
            "SELECT register_object("
            "'project'::object_kind, :ws, NULL, 'TFP', 'Test Formula Project', :uid, :id)"
        ),
        {"ws": ws_id, "uid": admin_id, "id": proj_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, 'TFP', 'Test Formula Project')"
        ),
        {"id": proj_id, "ws_id": ws_id},
    )

    # Role binding
    await db_session.execute(
        text(
            "INSERT INTO role_bindings ("
            "id, workspace_id, principal_id, role, scope_type, project_id"
            ") VALUES (uuidv7(), :ws, :uid, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"ws": ws_id, "uid": admin_id},
    )

    # Fetch priority 'urgent' and state 'Backlog' (seeded by trigger)
    pr_row = await db_session.execute(
        text("SELECT id FROM project_priorities WHERE project_id = :p AND slug = 'urgent'"),
        {"p": proj_id},
    )
    pr_id = pr_row.scalar_one()

    st_row = await db_session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p AND name = 'Backlog'"),
        {"p": proj_id},
    )
    st_id = st_row.scalar_one()

    # Register issue TFP-1
    await db_session.execute(
        text("UPDATE projects SET issue_seq_counter = 1 WHERE id = :p"),
        {"p": proj_id},
    )
    await db_session.execute(
        text(
            "SELECT register_object("
            "'issue'::object_kind, :ws, :proj, 'TFP-1', 'SLA Baseline Test Issue', :cr, :id)"
        ),
        {"ws": ws_id, "proj": proj_id, "cr": admin_id, "id": iss_id},
    )
    due_date = (datetime.now(UTC) + timedelta(days=1)).date()
    await db_session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
            "state_id, priority_id, summary, created_by_id, board_rank, due_date) "
            "VALUES (:id, :ws, :proj, 1, :st, :pr, 'SLA Baseline', :cr, '0|hzzzzz:', :dd)"
        ),
        {
            "id": iss_id,
            "ws": ws_id,
            "proj": proj_id,
            "st": st_id,
            "pr": pr_id,
            "cr": admin_id,
            "dd": due_date,
        },
    )

    await db_session.commit()

    proj = (
        await db_session.execute(select(Project).where(Project.id == proj_id))
    ).scalar_one()

    caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=1,
    )

    executor = CustomFieldExecutor(db_session)
    presets = _load_formula_presets_from_file()

    for pid, p in presets.items():
        fid = uuid.uuid4()
        manifest = compute_field_manifest_sha256(
            script_source=p["script_source"],
            output_format=p["output_format"],
            output_format_metadata=p["metadata"],
            tier="wasm",
            target_scope="PROJECT",
            credential_mode="INVOKING_USER",
        )
        defn = CustomFieldDefinition(
            id=fid,
            workspace_id=ws_id,
            project_id=proj_id,
            slug=pid,
            name=pid.title(),
            tier="wasm",
            output_format=p["output_format"],
            output_format_metadata=p["metadata"],
            script_source=p["script_source"],
            script_version=1,
            target_scope="PROJECT",
            credential_mode="INVOKING_USER",
            egress_allowlist=[],
            manifest_sha256=manifest,
            is_enabled=True,
            created_by_id=admin_id,
        )
        db_session.add(defn)
        await db_session.commit()

        # Execute for issue
        res = await executor.execute_for_issue(
            db_session, caller, "TFP-1", fid, force_refresh=True
        )
        assert res["status"] == "computed"
        assert res["value"] is not None

        if pid == "days-until-due-sla":
            # Priority is URGENT -> critical
            assert res["value"]["level"] == "critical"
            assert res["value"]["score"] == 9.5
        elif pid == "blocker-count":
            assert res["value"] == "Clear"
        elif pid == "sub-issue-completion":
            assert res["value"] == 0.0

        # Also test test_execute method
        test_req = CustomFieldTestExecuteRequest(
            issue_key="TFP-1",
            tier="wasm",
            script_source=p["script_source"],
            output_format=p["output_format"],
            output_format_metadata=p["metadata"],
            target_scope="PROJECT",
            credential_mode="INVOKING_USER",
        )
        test_res = await executor.test_execute(db_session, caller, proj, test_req)
        assert test_res["status"] == "SUCCESS", f"test_execute failed: {test_res.get('error')}"
        assert test_res["error"] is None
        assert test_res["value"] is not None

    await db_session.execute(text("RESET SESSION AUTHORIZATION"))
    await db_session.commit()


def test_formula_evaluator_ast_operators_and_edge_cases() -> None:
    """Exercise branch conditions in _strip_outer_parens, _convert_js_ternary, and formulas."""
    # 1. _strip_outer_parens branches
    assert _strip_outer_parens("(((1 + 2)))") == "1 + 2"
    assert _strip_outer_parens("(1) + (2)") == "(1) + (2)"
    assert _strip_outer_parens("no_parens") == "no_parens"

    # 2. _convert_js_ternary branches
    assert _convert_js_ternary("1 + 2") == "1 + 2"
    assert (
        _convert_js_ternary("a ? {'level': 'crit'} : {'level': 'low'}")
        == "({'level': 'crit'}) if (a) else ({'level': 'low'})"
    )
    assert _convert_js_ternary("a ? [1, 2] : [3, 4]") == "([1, 2]) if (a) else ([3, 4])"
    assert (
        _convert_js_ternary("a ? 'foo:bar' : 'baz:qux'")
        == "('foo:bar') if (a) else ('baz:qux')"
    )
    assert (
        _convert_js_ternary("a ? (b ? 1 : 2) : 3")
        == "((1) if (b) else (2)) if (a) else (3)"
    )
    assert (
        _convert_js_ternary('a ? "quote\\"esc" : "plain"')
        == '("quote\\"esc") if (a) else ("plain")'
    )

    # 3. _eval_safe_formula UnaryOp, BoolOp, Compare, Call
    ctx: dict[str, Any] = {"x": 5, "y": 10, "empty": None, "str_empty": "", "flag": True}

    # UnaryOp
    assert _eval_safe_formula("-x", ctx) == -5
    assert _eval_safe_formula("+x", ctx) == 5
    assert _eval_safe_formula("not flag", ctx) is False
    assert _eval_safe_formula("not False", ctx) is True

    # BoolOp
    assert _eval_safe_formula("flag and x > 3", ctx) is True
    assert _eval_safe_formula("flag and x < 3", ctx) is False
    assert _eval_safe_formula("not flag or y == 10", ctx) is True
    assert _eval_safe_formula("not flag or y == 99", ctx) is False

    # Compare
    assert _eval_safe_formula("x >= 5", ctx) is True
    assert _eval_safe_formula("x >= 6", ctx) is False
    assert _eval_safe_formula("x is 5", ctx) is True
    assert _eval_safe_formula("x is not 10", ctx) is True
    assert _eval_safe_formula("x in [1, 5, 10]", ctx) is True
    assert _eval_safe_formula("x not in [1, 2, 3]", ctx) is True
    assert _eval_safe_formula("empty < 10", ctx) is False
    assert _eval_safe_formula("str_empty >= 10", ctx) is False

    # Call
    assert _eval_safe_formula("round(3.14159, 2)", ctx) == 3.14
    assert _eval_safe_formula("int('42')", ctx) == 42
    assert _eval_safe_formula("float('3.14')", ctx) == 3.14
    assert _eval_safe_formula("min(x, y)", ctx) == 5
    assert _eval_safe_formula("max(x, y)", ctx) == 10
    assert _eval_safe_formula("len('hello')", ctx) == 5
    assert _eval_safe_formula("abs(-42)", ctx) == 42
    assert _eval_safe_formula("str(123)", ctx) == "123"

    # Call error handling
    assert _eval_safe_formula("round('invalid')", ctx) is None
    assert _eval_safe_formula("nonexistent_func(1)", ctx) is None

    # BinaryOp Pow & bounds
    assert _eval_safe_formula("2 ** 3", ctx) == 8
    assert _eval_safe_formula("2 ** 1000", ctx) is None
    assert _eval_safe_formula("'a' * 10", ctx) == "aaaaaaaaaa"
    assert _eval_safe_formula("'a' * 20000", ctx) is None


@pytest.mark.asyncio
async def test_build_issue_context_branches() -> None:
    """Test build_issue_context with real session, mocks, and error fallback paths."""
    # 1. Test with None session
    ctx_none = await build_issue_context(None, MagicMock(), "TFP-1")
    assert isinstance(ctx_none, dict)
    assert ctx_none["blocker_count"] == 0

    # 2. Test with mock session error handling
    mock_session = AsyncMock()
    mock_session.get.side_effect = SQLAlchemyError("DB error")
    mock_session.execute.side_effect = SQLAlchemyError("DB error")

    mock_issue = MagicMock()
    mock_issue.id = uuid.uuid4()
    mock_issue.state_id = uuid.uuid4()
    mock_issue.priority_id = uuid.uuid4()
    mock_issue.summary = "Mock Error Issue"
    mock_issue.description_markdown = "Desc"
    mock_issue.created_by_id = uuid.uuid4()
    mock_issue.due_date = None

    ctx_err = await build_issue_context(mock_session, mock_issue, "TFP-1")
    assert ctx_err["summary"] == "Mock Error Issue"
    assert ctx_err["blocker_count"] == 0
