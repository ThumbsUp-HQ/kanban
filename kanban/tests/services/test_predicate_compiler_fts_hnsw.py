# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, ANN401, ARG002, PYI036, BLE001, S110
"""Comprehensive unit and integration tests for predicate compiler, FTS stemming, and HNSW (KAN-78).

Validates:
1. Bounded DSL filter predicate compiler (MAX_QUERY_LENGTH=512, MAX_CLAUSES=32, MAX_TOKENS=32)
   parsing state, priority, assignee, label, cycle, module, project, key, and free-text terms.
2. Injection safety, ReDoS resistance (< 10ms), and error contracts (FILTER_TOO_COMPLEX 422).
3. English FTS stemming consistency: websearch_to_tsquery('english', ...) matching inflections.
4. HNSW iterative scan (SET LOCAL hnsw.iterative_scan = 'relaxed_order') and safe fallback.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Self
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Issue,
    IssueAssignee,
    IssueLabel,
    Project,
    ProjectLabel,
)
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.views import FilterSpec, GroupAxis
from kanban.services.predicate_compiler import (
    MAX_CLAUSES,
    MAX_QUERY_LENGTH,
    MAX_TOKENS,
    ParsedComparisonClause,
    ParsedToken,
    compile_predicate_string,
    parse_comparison_clause,
    sanitize_query_string,
    split_query_clauses,
    tokenize_predicate_string,
)
from kanban.services.search import _query_vector_candidates
from kanban.services.view_dsl import (
    compile_issue_filter_predicates,
    validate_group_axes,
)
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_user,
    create_workspace,
    rebuild_era,
)

# ============================================================================
# Section 1: Predicate Compiler Sanitization, Tokenization, and Complexity
# ============================================================================


def test_sanitize_query_string_bounds_and_control_chars() -> None:
    """Verify input sanitization strips control chars, surrogates, and enforces max length."""
    # Empty / non-string
    assert sanitize_query_string("") == ""
    assert sanitize_query_string(None) == ""  # type: ignore[arg-type]

    # Strips control chars and lone surrogates
    raw = "state:todo\x00\x1f\x7f \ud800priority:high"
    cleaned = sanitize_query_string(raw)
    assert "\x00" not in cleaned
    assert "\x1f" not in cleaned
    assert "\x7f" not in cleaned
    assert "\ud800" not in cleaned
    assert "state:todo" in cleaned
    assert "priority:high" in cleaned

    # Rejects oversized queries exceeding MAX_QUERY_LENGTH
    oversized = "state:todo AND " * 40  # > 512 chars
    assert len(oversized) > MAX_QUERY_LENGTH
    with pytest.raises(ProblemException) as exc_info:
        sanitize_query_string(oversized)
    assert exc_info.value.code == "FILTER_TOO_COMPLEX"
    assert exc_info.value.status == 422


def test_split_query_clauses_and_clause_budget() -> None:
    """Verify clause splitting handles AND keywords outside quotes and enforces clause limit."""
    # Single clause
    assert split_query_clauses("state:todo") == ["state:todo"]

    # Multiple AND clauses
    query = 'status = "Todo" AND priority = "high" And cycle = "Sprint 1" and label = "bug"'
    clauses = split_query_clauses(query)
    assert len(clauses) == 4
    assert clauses[0] == 'status = "Todo"'
    assert clauses[1] == 'priority = "high"'
    assert clauses[2] == 'cycle = "Sprint 1"'
    assert clauses[3] == 'label = "bug"'

    # AND inside quotes must NOT split
    quoted = 'summary = "cats AND dogs" AND state:todo'
    q_clauses = split_query_clauses(quoted)
    assert len(q_clauses) == 2
    assert q_clauses[0] == 'summary = "cats AND dogs"'
    assert q_clauses[1] == "state:todo"

    # Exceeding MAX_CLAUSES (32) raises FILTER_TOO_COMPLEX
    trimmed_many = " AND ".join(f"s:{i}" for i in range(35))
    with pytest.raises(ProblemException) as exc_info:
        split_query_clauses(trimmed_many, max_clauses=MAX_CLAUSES)
    assert exc_info.value.code == "FILTER_TOO_COMPLEX"
    assert exc_info.value.status == 422


def test_parse_comparison_clause() -> None:
    """Verify comparison clause parser extracts field, operator (=, !=), and value."""
    # Equality
    c1 = parse_comparison_clause('status = "In Progress"')
    assert c1 == ParsedComparisonClause(
        field="status", operator="=", value="In Progress", negated=False
    )

    # Inequality
    c2 = parse_comparison_clause("priority != urgent")
    assert c2 == ParsedComparisonClause(
        field="priority", operator="!=", value="urgent", negated=False
    )

    # NOT prefix
    c3 = parse_comparison_clause('NOT state = "Done"')
    assert c3 == ParsedComparisonClause(field="state", operator="=", value="Done", negated=True)

    # Single quotes
    c4 = parse_comparison_clause("project = 'KAN'")
    assert c4 == ParsedComparisonClause(field="project", operator="=", value="KAN", negated=False)

    # Non-comparison clause returns None
    assert parse_comparison_clause("state:todo priority:high") is None
    assert parse_comparison_clause('summary = "quoted" with extra') is not None
    assert parse_comparison_clause('invalid-field!@# = "test"') is None


def test_tokenize_predicate_string_and_token_budget() -> None:
    """Verify tokenizer extracts field:value, negated tokens, quotes, and enforces token limit."""
    s = '-state:completed !priority:low "mars rover" telemetry NOT "jupiter" label:\'sec\''
    tokens = tokenize_predicate_string(s)
    assert len(tokens) == 6
    assert tokens[0] == ParsedToken(field="state", value="completed", negated=True)
    assert tokens[1] == ParsedToken(field="priority", value="low", negated=True)
    assert tokens[2] == ParsedToken(field=None, value="mars rover", negated=False)
    assert tokens[3] == ParsedToken(field=None, value="telemetry", negated=False)
    assert tokens[4] == ParsedToken(field=None, value="jupiter", negated=True)
    assert tokens[5] == ParsedToken(field="label", value="sec", negated=False)

    # Standalone single-quoted string
    s_single = "'hardware failure' cycle:active"
    toks_single = tokenize_predicate_string(s_single)
    assert toks_single[0] == ParsedToken(field=None, value="hardware failure", negated=False)
    assert toks_single[1] == ParsedToken(field="cycle", value="active", negated=False)

    # Exceeding MAX_TOKENS (32) raises FILTER_TOO_COMPLEX
    many_tokens = " ".join(f"t{i}" for i in range(35))
    with pytest.raises(ProblemException) as exc_info:
        tokenize_predicate_string(many_tokens, max_tokens=MAX_TOKENS)
    assert exc_info.value.code == "FILTER_TOO_COMPLEX"
    assert exc_info.value.status == 422


def test_adversarial_redos_resistance() -> None:
    """Verify adversarial unclosed quotes and repeated patterns evaluate in < 10ms."""
    t0 = time.perf_counter()
    res = compile_predicate_string('a:"' * 50)
    elapsed = (time.perf_counter() - t0) * 1000.0
    assert elapsed < 10.0
    assert isinstance(res, list)


# ============================================================================
# Section 2: Predicate Compilation Unit Assertions Across All DSL Fields
# ============================================================================


def test_compile_predicate_all_fields_structure() -> None:
    """Verify compile_predicate_string handles all required filter fields without errors."""
    proj_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Empty query
    assert compile_predicate_string("", project=proj_id, caller_principal_id=user_id) == []
    assert compile_predicate_string("   ", project=proj_id) == []

    # 1. State / Status expressions
    p_state = compile_predicate_string(
        "state:todo state!=done -state:cancelled !status:closed state:actionable status:active state:all state:*"
    )
    assert len(p_state) == 8

    # Comma-separated state and state UUID
    uid_st = str(uuid.uuid4())
    p_state_multi = compile_predicate_string(f"state:todo,in_progress state:{uid_st}")
    assert len(p_state_multi) == 2

    # 2. State Group expressions
    p_group = compile_predicate_string(
        "state_group:started group:unstarted state_group!=completed group:actionable group:all"
    )
    assert len(p_group) == 5

    # 3. Priority expressions
    uid_pr = str(uuid.uuid4())
    p_prio = compile_predicate_string(
        f"priority:high,urgent priority:low priority!=low -priority:low priority:{uid_pr}"
    )
    assert len(p_prio) == 5

    # 4. Assignee expressions
    uid_asg = str(uuid.uuid4())
    p_asg = compile_predicate_string(
        f"assignee:@me assignee:me assignee:unassigned assignee:none -assignee:unassigned assignee:alice assignee:@bob assignee:{uid_asg}",
        caller_principal_id=user_id,
    )
    assert len(p_asg) == 8

    # Assignee @me without caller_principal_id yields false condition
    p_asg_no_caller = compile_predicate_string("assignee:@me", caller_principal_id=None)
    assert len(p_asg_no_caller) == 1

    # 5. Label expressions
    uid_lbl = str(uuid.uuid4())
    p_lbl = compile_predicate_string(
        f"label:security label:bug,enhancement -label:wontfix label:{uid_lbl}"
    )
    assert len(p_lbl) == 4

    # 6. Cycle expressions
    uid_cyc = str(uuid.uuid4())
    p_cyc = compile_predicate_string(
        f"cycle:current cycle:active cycle:none cycle:no-cycle cycle:Sprint1 cycle:{uid_cyc}"
    )
    assert len(p_cyc) == 6

    # 7. Module expressions
    uid_mod = str(uuid.uuid4())
    p_mod = compile_predicate_string(f"module:none module:Rover module:{uid_mod} -module:Rover")
    assert len(p_mod) == 4

    # 8. Project expressions
    p_proj = compile_predicate_string('project:KAN AND project = "ENG" AND project!=KAN')
    assert len(p_proj) == 3

    # 9. Key expressions
    uid_key = str(uuid.uuid4())
    p_key = compile_predicate_string(f"key:KAN-101 AND key={uid_key} AND -key:KAN-102")
    assert len(p_key) == 3

    # 10. Free-text terms
    p_text = compile_predicate_string('"mars rover" telemetry -jupiter NOT "venus"')
    assert len(p_text) == 4

    # 11. Comparison clauses with = and !=
    p_cmp = compile_predicate_string(
        'status = "In Progress" AND priority != "low" AND NOT state = "Cancelled"'
    )
    assert len(p_cmp) == 3

    # 12. Unrecognized field falls back to text search
    p_unknown = compile_predicate_string('custom_attribute:foo AND custom_other = "bar"')
    assert len(p_unknown) == 2


# ============================================================================
# Section 3: Integration Tests Against Clean PostgreSQL Database
# ============================================================================


@pytest.mark.committed_db
async def test_predicate_compiler_execution_against_database(
    committed_db_session: AsyncSession,
) -> None:
    """Verify compiled SQL predicates execute against real PostgreSQL tables with expected filtering."""
    session = committed_db_session

    ws_id = await create_workspace(session, name="Search Test WS")
    admin_id = await create_user(session, ws_id, handle="@alice", display_name="Alice Engineer")
    await add_role_binding(session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace")
    await session.commit()

    proj_id = await create_project(
        session, ws_id, identifier="FLTR", name="Filter Test Project", created_by_id=admin_id
    )
    await add_role_binding(
        session, ws_id, admin_id, role="PROJECT_ADMIN", scope_type="project", project_id=proj_id
    )
    await rebuild_era(session, ws_id)
    await session.commit()

    proj = await session.get(Project, proj_id)
    assert proj is not None

    # Load seeded workflow states
    states = (
        await session.execute(
            text(
                "SELECT id, name, state_group FROM workflow_states WHERE project_id = :p ORDER BY sort_order"
            ),
            {"p": proj_id},
        )
    ).all()
    st_todo_id = next(s[0] for s in states if s[2] in ("unstarted", "backlog"))
    st_done_id = next(s[0] for s in states if s[2] == "completed")

    # Load seeded priorities
    priorities = (
        await session.execute(
            text(
                "SELECT id, slug FROM project_priorities WHERE project_id = :p ORDER BY sort_order"
            ),
            {"p": proj_id},
        )
    ).all()
    prio_high_id = next(p[0] for p in priorities if p[1] == "high")
    prio_low_id = next(p[0] for p in priorities if p[1] == "low")

    # Insert explicit label
    lbl_sec_id = uuid.uuid4()
    lbl_sec = ProjectLabel(
        id=lbl_sec_id,
        workspace_id=ws_id,
        project_id=proj_id,
        name="security",
        color_hex="#ff0000",
    )
    session.add(lbl_sec)
    await session.commit()

    # Create Issue 1: Todo, High, Alice, Security, Mars Antenna
    i1_id = uuid.uuid4()
    seq1 = (
        await session.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
    ).scalar_one()
    await session.execute(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"FLTR-{seq1}",
            "title": "Mars antenna telemetry connection",
            "cr": admin_id,
            "id": i1_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, description_markdown, state_id, priority_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, :summary, :desc, :st, :pri, :cr, :cr, '0|hzzzzz:', 'top')"
        ),
        {
            "id": i1_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq1,
            "summary": "Mars antenna telemetry connection",
            "desc": "Investigating telemetry antennas on rover.",
            "st": st_todo_id,
            "pri": prio_high_id,
            "cr": admin_id,
        },
    )
    i1_asg = IssueAssignee(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        issue_id=i1_id,
        principal_id=admin_id,
    )
    i1_lbl = IssueLabel(
        issue_id=i1_id,
        label_id=lbl_sec_id,
        workspace_id=ws_id,
    )
    session.add_all([i1_asg, i1_lbl])

    # Create Issue 2: Done, Low, Unassigned, Jupiter Camera
    i2_id = uuid.uuid4()
    seq2 = (
        await session.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
    ).scalar_one()
    await session.execute(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"FLTR-{seq2}",
            "title": "Jupiter camera calibration",
            "cr": admin_id,
            "id": i2_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, description_markdown, state_id, priority_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, :summary, :desc, :st, :pri, :cr, :cr, '0|hzzzzz:', 'top')"
        ),
        {
            "id": i2_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq2,
            "summary": "Jupiter camera calibration",
            "desc": "Calibrating optic sensors for Jupiter flyby.",
            "st": st_done_id,
            "pri": prio_low_id,
            "cr": admin_id,
        },
    )
    await session.commit()

    # Query 1: Actionable state and high priority -> matches i1 only
    q1 = "state:actionable AND priority:high"
    preds1 = compile_predicate_string(q1, project=proj, caller_principal_id=admin_id)
    stmt1 = select(Issue.id).where(Issue.project_id == proj_id, *preds1)
    res1 = (await session.execute(stmt1)).scalars().all()
    assert res1 == [i1_id]

    # Query 2: Assignee @me -> matches i1 only
    q2 = "assignee:@me"
    preds2 = compile_predicate_string(q2, project=proj, caller_principal_id=admin_id)
    stmt2 = select(Issue.id).where(Issue.project_id == proj_id, *preds2)
    res2 = (await session.execute(stmt2)).scalars().all()
    assert res2 == [i1_id]

    # Query 3: Assignee unassigned -> matches i2 only
    q3 = "assignee:unassigned"
    preds3 = compile_predicate_string(q3, project=proj, caller_principal_id=admin_id)
    stmt3 = select(Issue.id).where(Issue.project_id == proj_id, *preds3)
    res3 = (await session.execute(stmt3)).scalars().all()
    assert res3 == [i2_id]

    # Query 4: Negative state: -state:completed -> matches i1 only
    q4 = "-state:completed"
    preds4 = compile_predicate_string(q4, project=proj, caller_principal_id=admin_id)
    stmt4 = select(Issue.id).where(Issue.project_id == proj_id, *preds4)
    res4 = (await session.execute(stmt4)).scalars().all()
    assert res4 == [i1_id]

    # Query 5: Label security -> matches i1 only
    q5 = "label:security"
    preds5 = compile_predicate_string(q5, project=proj, caller_principal_id=admin_id)
    stmt5 = select(Issue.id).where(Issue.project_id == proj_id, *preds5)
    res5 = (await session.execute(stmt5)).scalars().all()
    assert res5 == [i1_id]


# ============================================================================
# Section 4: English Full-Text Search Stemming Consistency (Problem 2)
# ============================================================================


@pytest.mark.committed_db
async def test_english_fts_stemming_consistency_vs_simple(
    committed_db_session: AsyncSession,
) -> None:
    """Verify english dictionary matches inflected/plural terms while simple dictionary fails."""
    session = committed_db_session

    ws_id = await create_workspace(session, name="FTS Stemming WS")
    admin_id = await create_user(session, ws_id, handle="@stemmer", display_name="Stemmer")
    await add_role_binding(session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace")
    await session.commit()

    proj_id = await create_project(
        session, ws_id, identifier="STEM", name="Stemming Test Project", created_by_id=admin_id
    )
    await add_role_binding(
        session, ws_id, admin_id, role="PROJECT_ADMIN", scope_type="project", project_id=proj_id
    )
    await rebuild_era(session, ws_id)
    await session.commit()

    proj = await session.get(Project, proj_id)
    assert proj is not None

    states = (
        await session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p ORDER BY sort_order"),
            {"p": proj_id},
        )
    ).all()
    st_id = states[0][0]

    priorities = (
        await session.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p ORDER BY sort_order"),
            {"p": proj_id},
        )
    ).all()
    pri_id = priorities[0][0]

    # Issue with text containing stemmed terms
    iss_id = uuid.uuid4()
    seq = (
        await session.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": proj_id})
    ).scalar_one()
    await session.execute(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"STEM-{seq}",
            "title": "Database connection retry",
            "cr": admin_id,
            "id": iss_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, description_markdown, state_id, priority_id, created_by_id, original_created_by_id, board_rank, ancestry_path) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, :summary, :desc, :st, :pri, :cr, :cr, '0|hzzzzz:', 'top')"
        ),
        {
            "id": iss_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq,
            "summary": "Database connection retry",
            "desc": "The server establishes connections and handles connection timeouts.",
            "st": st_id,
            "pri": pri_id,
            "cr": admin_id,
        },
    )
    await session.commit()

    # In PostgreSQL, search_tsv is generated with 'english' configuration.
    # Query with inflected plural 'connections' using 'english':
    # to_tsquery('english', 'connections') stems to 'connect', matching 'connection' and 'connections'.
    sql_english = text(
        "SELECT issues.search_tsv @@ websearch_to_tsquery('english', :q) FROM issues WHERE id = :id"
    )
    res_english = (await session.execute(sql_english, {"q": "connections", "id": iss_id})).scalar()
    assert res_english is True

    # Query with 'retrying' vs 'retry'
    res_inflection = (await session.execute(sql_english, {"q": "retrying", "id": iss_id})).scalar()
    assert res_inflection is True

    # Under 'simple' dictionary, no stemming occurs: 'retrying' != 'retry'
    sql_simple = text(
        "SELECT issues.search_tsv @@ websearch_to_tsquery('simple', :q) FROM issues WHERE id = :id"
    )
    res_simple_inflection = (
        await session.execute(sql_simple, {"q": "retrying", "id": iss_id})
    ).scalar()
    # 'retrying' does not match 'retry' under simple dictionary
    assert res_simple_inflection is False

    # Verify compile_issue_filter_predicates compiles search_query with english stemming
    filters = FilterSpec(search_query="connections")
    preds = compile_issue_filter_predicates(session, proj, filters, admin_id)
    stmt = select(Issue.id).where(Issue.id == iss_id, *preds)
    matched_ids = (await session.execute(stmt)).scalars().all()
    assert matched_ids == [iss_id]


# ============================================================================
# Section 5: HNSW Iterative Scan & Safe Fallback (Problem 3)
# ============================================================================


@pytest.mark.committed_db
async def test_hnsw_iterative_scan_and_fallback(
    committed_db_session: AsyncSession,
) -> None:
    """Verify SET LOCAL hnsw.iterative_scan = 'relaxed_order' executes or falls back cleanly."""
    session = committed_db_session

    # Test direct execution of the GUC or safe fallback
    async with session.begin_nested():
        try:
            async with session.begin_nested():
                await session.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))
        except Exception:
            pass
        # Ensure transaction is healthy and subsequent queries succeed
        res = (await session.execute(text("SELECT 1"))).scalar()
        assert res == 1


class _DummySession:
    """Mock session with sync begin / begin_nested returning self as async context manager."""

    def __init__(self) -> None:
        self.info: dict[str, Any] = {}
        self.executed_statements: list[str] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    def begin(self) -> _DummySession:
        return self

    def begin_nested(self) -> _DummySession:
        return self

    async def execute(self, stmt: Any, params: Any = None) -> Any:
        sql = str(stmt)
        self.executed_statements.append(sql)
        if "hnsw.iterative_scan" in sql:
            msg = "unrecognized configuration parameter 'hnsw.iterative_scan'"
            raise RuntimeError(msg)
        res = MagicMock()
        res.fetchall.return_value = []
        return res


async def test_search_candidates_hnsw_iterative_scan_fallback_unit() -> None:
    """Verify _query_vector_candidates executes hnsw.iterative_scan with fallback on mock session."""
    dummy_session = _DummySession()

    ws_id = uuid.uuid4()
    query_vector = [0.1] * 384
    candidates = await _query_vector_candidates(
        session=dummy_session,  # type: ignore[arg-type]
        workspace_id=ws_id,
        project_id=None,
        target_kinds=["issue"],
        query_vector=query_vector,
    )
    assert candidates is None
    # Verify statement_timeout and hnsw.iterative_scan were attempted
    assert any("statement_timeout" in s for s in dummy_session.executed_statements)
    assert any("hnsw.iterative_scan" in s for s in dummy_session.executed_statements)


def test_predicate_compiler_edge_cases_and_branches() -> None:
    """Exercise all branch conditions and edge cases in predicate_compiler."""
    # 1. split_query_clauses extra whitespace after AND
    clauses = split_query_clauses("state:todo    AND    priority:high")
    assert clauses == ["state:todo", "priority:high"]

    # 2. split_query_clauses exceeding max_clauses on tail
    query_35 = " " + " AND ".join([f"f{i}:v{i}" for i in range(35)])
    with pytest.raises(ProblemException) as exc_info:
        split_query_clauses(query_35, max_clauses=32)
    assert exc_info.value.code == "FILTER_TOO_COMPLEX"

    # 3. parse_comparison_clause edge cases
    # Multiple != or = operators
    cmp1 = parse_comparison_clause("state!=todo!=done")
    assert cmp1 is not None
    assert cmp1.field == "state"
    assert cmp1.operator == "!="
    cmp2 = parse_comparison_clause("state=todo=done")
    assert cmp2 is not None
    assert cmp2.field == "state"
    assert cmp2.operator == "="
    # Negated comparison
    cmp3 = parse_comparison_clause("NOT priority=urgent")
    assert cmp3 is not None
    assert cmp3.negated is True
    assert cmp3.field == "priority"
    # Invalid syntax or no identifier
    assert parse_comparison_clause("=invalid") is None
    assert parse_comparison_clause("invalid-field!=abc") is None

    # 4. tokenize_predicate_string quotes and edge cases
    toks1 = tokenize_predicate_string("state:'in progress' priority:\"urgent task\" key:FLTR-1")
    assert any(t.field == "state" and t.value == "in progress" for t in toks1)
    assert any(t.field == "priority" and t.value == "urgent task" for t in toks1)
    assert any(t.field == "key" and t.value == "FLTR-1" for t in toks1)

    # Exceeding max_tokens
    many_tokens = " ".join([f"t{i}:val{i}" for i in range(35)])
    with pytest.raises(ProblemException) as exc_tok:
        tokenize_predicate_string(many_tokens, max_tokens=32)
    assert exc_tok.value.code == "FILTER_TOO_COMPLEX"

    # Negated free text words and dangling quotes
    toks2 = tokenize_predicate_string('word1 NOT word2 NOT word3 "unclosed quote')
    assert any(t.value == "word2" and t.negated is True for t in toks2)
    assert any(t.value == "word3" and t.negated is True for t in toks2)

    # 5. compile_predicate_string with varied project and caller_id types
    p_uuid = uuid.uuid4()
    caller_uuid = uuid.uuid4()
    # project as UUID
    preds_p = compile_predicate_string("state:closed", project=p_uuid)
    assert len(preds_p) == 1
    # caller_id as string UUID
    preds_c = compile_predicate_string("assignee:@me", caller_principal_id=str(caller_uuid))
    assert len(preds_c) == 1
    # caller_id as non-UUID string
    preds_bad_c = compile_predicate_string("assignee:@me", caller_principal_id="not-a-uuid")
    assert len(preds_bad_c) == 1
    # caller_id None
    preds_no_c = compile_predicate_string("assignee:@me", caller_principal_id=None)
    assert len(preds_no_c) == 1

    # 6. compile_predicate_string fields with project, UUIDs, and invalid UUID fallback
    # state
    p_st1 = compile_predicate_string("state:closed", project=p_uuid)
    p_st2 = compile_predicate_string("state:terminal", project=None)
    p_st3 = compile_predicate_string("state:all,state:*")
    p_st4 = compile_predicate_string(f"state:{uuid.uuid4()}", project=p_uuid)
    p_st5 = compile_predicate_string("state:not-a-uuid-fallback", project=p_uuid)
    assert len(p_st1) == 1
    assert len(p_st2) == 1
    assert len(p_st3) == 1
    assert len(p_st4) == 1
    assert len(p_st5) == 1

    # state_group
    p_sg1 = compile_predicate_string("state_group:active", project=p_uuid)
    p_sg2 = compile_predicate_string("state_group:all", project=p_uuid)
    p_sg3 = compile_predicate_string("state_group:backlog", project=p_uuid)
    assert len(p_sg1) == 1
    assert len(p_sg2) == 1
    assert len(p_sg3) == 1

    # priority
    p_pr1 = compile_predicate_string(f"priority:{uuid.uuid4()}", project=p_uuid)
    p_pr2 = compile_predicate_string("priority:not-a-uuid-fallback", project=p_uuid)
    assert len(p_pr1) == 1
    assert len(p_pr2) == 1

    # assignee
    p_asg1 = compile_predicate_string(f"assignee:{uuid.uuid4()}")
    p_asg2 = compile_predicate_string("assignee:unassigned,none")
    p_asg3 = compile_predicate_string("assignee:alice.dev")
    assert len(p_asg1) == 1
    assert len(p_asg2) == 1
    assert len(p_asg3) == 1

    # label
    p_lbl1 = compile_predicate_string(f"label:{uuid.uuid4()}")
    p_lbl2 = compile_predicate_string("label:frontend")
    assert len(p_lbl1) == 1
    assert len(p_lbl2) == 1

    # cycle
    p_cyc1 = compile_predicate_string("cycle:current", project=p_uuid)
    p_cyc2 = compile_predicate_string("cycle:none,no-cycle", project=p_uuid)
    p_cyc3 = compile_predicate_string(f"cycle:{uuid.uuid4()}", project=p_uuid)
    p_cyc4 = compile_predicate_string("cycle:Sprint1", project=p_uuid)
    p_cyc5 = compile_predicate_string("cycle:Sprint1", project=None)
    assert len(p_cyc1) == 1
    assert len(p_cyc2) == 1
    assert len(p_cyc3) == 1
    assert len(p_cyc4) == 1
    assert len(p_cyc5) == 1

    # module
    p_mod1 = compile_predicate_string("module:none", project=p_uuid)
    p_mod2 = compile_predicate_string(f"module:{uuid.uuid4()}", project=p_uuid)
    p_mod3 = compile_predicate_string("module:Billing", project=p_uuid)
    p_mod4 = compile_predicate_string("module:Billing", project=None)
    assert len(p_mod1) == 1
    assert len(p_mod2) == 1
    assert len(p_mod3) == 1
    assert len(p_mod4) == 1

    # project & key
    p_prj = compile_predicate_string("project:KANBA,-project:OTHER")
    p_key1 = compile_predicate_string(f"key:{uuid.uuid4()}")
    p_key2 = compile_predicate_string("key:KANBA-42")
    p_key3 = compile_predicate_string("key:invalid_key_format")
    assert len(p_prj) == 1
    assert len(p_key1) == 1
    assert len(p_key2) == 1
    assert len(p_key3) == 1

    # free text & unrecognized field
    p_ft1 = compile_predicate_string("some_unrecognized_field:value")
    p_ft2 = compile_predicate_string("")
    p_ft3 = compile_predicate_string("   ")
    assert len(p_ft1) == 1
    assert len(p_ft2) == 0
    assert len(p_ft3) == 0


def test_view_dsl_filter_predicates_and_branches() -> None:
    """Exercise branch conditions in view_dsl compile_issue_filter_predicates and validate_group_axes."""
    mock_session = MagicMock(spec=AsyncSession)
    caller_id = uuid.uuid4()
    p_uuid = uuid.uuid4()

    mock_project = MagicMock(spec=Project)
    mock_project.id = p_uuid
    mock_project.modules_enabled = True

    # 1. validate_group_axes branch testing
    # Same group axis
    with pytest.raises(ProblemException) as exc_dup:
        validate_group_axes(mock_project, GroupAxis.STATE, GroupAxis.STATE)
    assert exc_dup.value.code == "DUPLICATE_GROUP_AXIS"

    # Modules disabled but requested
    mock_no_modules = MagicMock(spec=Project)
    mock_no_modules.id = p_uuid
    mock_no_modules.modules_enabled = False
    with pytest.raises(ProblemException) as exc_mod:
        validate_group_axes(mock_no_modules, GroupAxis.MODULE, None)
    assert exc_mod.value.code == "MODULES_DISABLED"

    with pytest.raises(ProblemException) as exc_mod_fltr:
        validate_group_axes(mock_no_modules, None, None, FilterSpec(module_ids=[str(uuid.uuid4())]))
    assert exc_mod_fltr.value.code == "MODULES_DISABLED"

    # 2. compile_issue_filter_predicates with project=None
    filters_no_proj = FilterSpec(
        state_ids=[uuid.uuid4()],
        priority_ids=[uuid.uuid4()],
        assignee_ids=["invalid-assignee-uuid", str(uuid.uuid4())],
        parent_issue_id="invalid-parent-uuid",
        module_ids=["none", str(uuid.uuid4()), "invalid-module-uuid"],
        search_query="   ",
    )
    preds_no_proj = compile_issue_filter_predicates(
        session=mock_session,
        project=None,
        filters=filters_no_proj,
        caller_principal_id=caller_id,
    )
    assert len(preds_no_proj) > 0

    # 3. parent_issue_id valid uuid, cycle_ids with invalid uuid
    filters_proj = FilterSpec(
        parent_issue_id=str(uuid.uuid4()),
        cycle_ids=["none", "active", str(uuid.uuid4()), "invalid-cycle-uuid"],
        search_query="mars rover telemetry",
    )
    preds_proj = compile_issue_filter_predicates(
        session=mock_session,
        project=mock_project,
        filters=filters_proj,
        caller_principal_id=caller_id,
    )
    assert len(preds_proj) > 0
