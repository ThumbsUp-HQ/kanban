# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for Issue Workflow API endpoints (KB-P4-06).

Covers:
  - POST /api/v1/issues/{id}/begin-work: atomic assignment, started state, cycle, plan comment.
  - POST /api/v1/issues/{id}/transition: state changes, USE_COMPLETE_WORK guard, gate hold.
  - POST /api/v1/issues/{id}/complete-work: blocker check, QA gate check, proof table comment,
    activity record, redacted foreign blockers, path traversal rejection.
"""

# ruff: noqa: ARG001, ARG002, F841, PLR0913, PLR0917, ANN401, D401

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from kanban.issues.workflow_service import (
    GateHoldResult,
    WorkflowGateHook,
    set_workflow_gate_hook,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _make_valid_proof(key: str) -> dict[str, Any]:
    """Helper to build a valid VerificationProof dictionary for a given ticket key."""
    return {
        "qa_dir": f"docs/qa/{key}/",
        "reality_checker": {
            "verdict": "READY",
            "grade": "A",
            "report_path": f"docs/qa/{key}/reality-checker-report.md",
        },
        "ci_run_url": "https://dash.hackedyour.info/runs/12345",
        "artifacts": [
            f"docs/qa/{key}/git-diff.patch",
            f"docs/qa/{key}/unit-test-results.txt",
        ],
    }


def _make_valid_report(verdict: str = "READY", grade: str = "A") -> str:
    return f"""# Integration Agent Reality-Based Report

## Reality Check Validation
- Verified all deliverables against acceptance criteria.
- Complete audit of all source files and assets.

## Complete System Evidence
- System running smoothly with zero errors.
- Verification artifacts collected in docs/qa.

## Integration Testing Results
- All unit and integration test suites executed cleanly.
- Full regression suite passing.

## Comprehensive Issue Assessment
- Root cause identified and systematically resolved.
- Security and performance invariants verified.

## Realistic Quality Certification
- Verdict: {verdict}
- Grade: {grade}

## Deployment Readiness Assessment
- Ready for immediate production deployment.
- No rollback concerns or migration locks.
"""


async def test_begin_work_positive(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """begin_work moves issue to started state, assigns caller, binds active cycle, posts plan."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    dev = await make_user("dev")
    proj_id = await make_project(
        "BWK", created_by=admin, roles={admin: "PROJECT_ADMIN", dev: "MEMBER"}
    )

    client_admin = as_principal(admin)

    # Seed an active cycle in project via API
    c_resp = await client_admin.post(
        "/api/v1/projects/BWK/cycles",
        json={"name": "Sprint 1", "start_date": "2026-11-15", "end_date": "2026-11-29"},
    )
    assert c_resp.status_code == 201, c_resp.text
    cycle_id = c_resp.json()["id"]
    start_resp = await client_admin.post(f"/api/v1/cycles/{cycle_id}/start")
    assert start_resp.status_code == 200, start_resp.text

    # Create issue in Todo
    create_resp = await client_admin.post(
        "/api/v1/projects/BWK/issues",
        json={"summary": "Build workflow engine", "description_markdown": "Details"},
    )
    assert create_resp.status_code == 201
    issue_data = create_resp.json()
    issue_key = issue_data["key"]

    # Call begin_work as dev
    client_dev = as_principal(dev)
    plan = "### Execution Plan\n1. Write tests\n2. Implement\n3. Verify"
    bw_resp = await client_dev.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": plan},
    )
    assert bw_resp.status_code == 200, bw_resp.text
    result = bw_resp.json()

    assert result["status"] == "started"
    assert result["key"] == issue_key
    assert result["from_state"]["name"] in ("Backlog", "Todo")
    assert result["to_state"]["name"] == "In Progress"
    assert result["cycle_id"] == str(cycle_id)
    res_assignees = [
        str(a["principal"]["id"])
        for a in result.get("assignees", [])
        if a.get("kind") == "principal"
    ]
    assert str(dev.id) in res_assignees
    assert result["comment_id"] is not None

    # Check issue in database: state, cycle, assignee
    get_resp = await client_dev.get(f"/api/v1/issues/{issue_key}")
    assert get_resp.status_code == 200
    issue_after = get_resp.json()
    assert issue_after["state"]["name"] == "In Progress"
    assert issue_after["cycle_id"] == str(cycle_id)
    assignee_ids = [
        str(a["principal"]["id"])
        for a in issue_after.get("assignees", [])
        if a.get("kind") == "principal"
    ]
    assert str(dev.id) in assignee_ids

    # Second call to begin_work: caller is already assigned, cycle already attached, already started
    bw2_resp = await client_dev.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": "Updated plan\n- step A"},
    )
    assert bw2_resp.status_code == 200
    assert bw2_resp.json()["status"] == "started"


async def test_begin_work_no_started_state_error(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """begin_work returns 409 NO_STARTED_STATE when no started states exist."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("NSS", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Delete or change all 'started' states
    await api_env.seed.execute(
        text("UPDATE workflow_states SET state_group = 'unstarted' WHERE project_id = :proj"),
        {"proj": proj_id},
    )
    await api_env.seed.commit()

    create_resp = await client.post(
        "/api/v1/projects/NSS/issues",
        json={"summary": "Task with no started state", "description_markdown": "None"},
    )
    issue_key = create_resp.json()["key"]

    bw_resp = await client.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": "My plan"},
    )
    assert bw_resp.status_code == 409
    body = bw_resp.json()
    assert body["code"] == "NO_STARTED_STATE"


async def test_transition_ticket_positive_and_guards(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """transition_ticket transitions non-completed states and blocks completed states."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("TRN", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/TRN/issues",
        json={"summary": "Transition testing", "description_markdown": "Testing"},
    )
    issue_key = create_resp.json()["key"]

    # 1. Attempt to transition directly to completed state -> 422 USE_COMPLETE_WORK
    trans_done_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transition",
        json={"to_state": "Done"},
    )
    assert trans_done_resp.status_code == 422
    assert trans_done_resp.json()["code"] == "USE_COMPLETE_WORK"

    # 2. Transition to "In Progress" -> 200 OK
    trans_prog_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transition",
        json={"to_state": "In Progress", "comment_markdown": "Moving to in progress"},
    )
    assert trans_prog_resp.status_code == 200
    res = trans_prog_resp.json()
    assert res["status"] == "transitioned"
    assert res["to_state"]["name"] == "In Progress"

    # 3. Invalid state name -> 422 INVALID_TRANSITION
    bad_state_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transition",
        json={"to_state": "NonExistentState"},
    )
    assert bad_state_resp.status_code == 422
    assert bad_state_resp.json()["code"] == "INVALID_TRANSITION"


async def test_transition_ticket_pending_gate_hold(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """transition_ticket returns 202 Accepted when a WorkflowGateHook holds transition."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("HLD", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/HLD/issues",
        json={"summary": "Held transition issue", "description_markdown": "Test"},
    )
    issue_key = create_resp.json()["key"]

    exec_id = uuid.uuid4()

    class MockGateHook(WorkflowGateHook):
        async def evaluate_transition(
            self,
            session: Any,
            caller: Any,
            issue: Any,
            from_state: Any,
            to_state: Any,
            verification_proof: Any = None,
        ) -> GateHoldResult | None:
            return GateHoldResult(
                execution_id=exec_id,
                active_agent="code-reviewer",
                from_state=from_state.name,
                to_state=to_state.name,
            )

    set_workflow_gate_hook(MockGateHook())
    try:
        resp = await client.post(
            f"/api/v1/issues/{issue_key}/transition",
            json={"to_state": "In Progress"},
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert data["status"] == "pending_agent_gate"
        assert data["execution_id"] == str(exec_id)
        assert data["active_agent"] == "code-reviewer"
        assert data["from_state"] in ("Backlog", "Todo")
        assert data["to_state"] == "In Progress"

        # Create separate issue for begin-work gate hold (202 Accepted)
        c_bw = await client.post(
            "/api/v1/projects/HLD/issues",
            json={"summary": "Held begin issue", "description_markdown": "Test"},
        )
        issue_bw_key = c_bw.json()["key"]
        bw_held = await client.post(
            f"/api/v1/issues/{issue_bw_key}/begin-work",
            json={"plan_markdown": "Plan for held issue"},
        )
        assert bw_held.status_code == 202
        assert bw_held.json()["status"] == "pending_agent_gate"

        # Create separate issue for complete-work gate hold (202 Accepted)
        c_cw = await client.post(
            "/api/v1/projects/HLD/issues",
            json={"summary": "Held complete issue", "description_markdown": "Test"},
        )
        issue_cw_key = c_cw.json()["key"]
        proof = _make_valid_proof(issue_cw_key)
        cw_held = await client.post(
            f"/api/v1/issues/{issue_cw_key}/complete-work",
            json={"summary_markdown": _make_valid_report(), "verification_proof": proof},
        )
        assert cw_held.status_code == 202
        assert cw_held.json()["status"] == "pending_agent_gate"
    finally:
        set_workflow_gate_hook(None)


async def test_complete_work_positive(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """complete_work transitions issue to completed, writes proof table comment and activity."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("CMP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/CMP/issues",
        json={"summary": "Feature to complete", "description_markdown": "Feature desc"},
    )
    issue_key = create_resp.json()["key"]

    # First begin work to move to In Progress
    await client.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": "Start feature"},
    )

    # Call complete_work
    proof = _make_valid_proof(issue_key)
    comp_resp = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={
            "summary_markdown": _make_valid_report(),
            "verification_proof": proof,
        },
    )
    assert comp_resp.status_code == 200, comp_resp.text
    result = comp_resp.json()
    assert result["status"] == "completed"
    assert result["key"] == issue_key
    assert result["from_state"]["name"] == "In Progress"
    assert result["to_state"]["name"] == "Done"
    assert result["comment_id"] is not None

    # Check comments on issue
    comments_resp = await client.get(f"/api/v1/issues/{issue_key}/comments")
    assert comments_resp.status_code == 200
    comments = comments_resp.json()["items"]
    # The last comment should contain the verification proof table
    last_comment = comments[-1] if comments else None
    assert last_comment is not None
    assert "### Verification Proof" in last_comment["body_markdown"]
    assert "| **Verdict** | `READY` |" in last_comment["body_markdown"]
    assert "| **Grade** | `A` |" in last_comment["body_markdown"]

    # Verify WORK_COMPLETED activity record
    activity_count = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM activity_records WHERE event_type = 'WORK_COMPLETED'")
        )
    ).scalar_one()
    assert activity_count >= 1


async def test_complete_work_qa_verdict_not_ready(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """complete_work returns 422 QA_VERDICT_NOT_READY when verdict or grade is not READY / A."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("QAF", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/QAF/issues",
        json={"summary": "Fail QA gate", "description_markdown": "Test"},
    )
    issue_key = create_resp.json()["key"]

    proof = _make_valid_proof(issue_key)
    proof["reality_checker"]["verdict"] = "NEEDS_WORK"

    resp = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={
            "summary_markdown": "Almost done",
            "verification_proof": proof,
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "QA_VERDICT_NOT_READY"


async def test_complete_work_open_child_and_link_blockers(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """complete_work returns 409 OPEN_CHILD_BLOCKERS when child or BLOCKS link is open."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("BLK", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create parent issue
    parent_resp = await client.post(
        "/api/v1/projects/BLK/issues",
        json={"summary": "Parent task", "description_markdown": "Parent"},
    )
    parent_key = parent_resp.json()["key"]
    parent_id = parent_resp.json()["id"]

    # 2. Create child issue
    child_resp = await client.post(
        "/api/v1/projects/BLK/issues",
        json={"summary": "Child task", "description_markdown": "Child", "parent": parent_key},
    )
    assert child_resp.status_code == 201, child_resp.text
    child_key = child_resp.json()["key"]

    # Attempt complete parent -> blocked by child
    proof = _make_valid_proof(parent_key)
    comp_resp = await client.post(
        f"/api/v1/issues/{parent_key}/complete-work",
        json={"summary_markdown": _make_valid_report(), "verification_proof": proof},
    )
    assert comp_resp.status_code == 409
    body = comp_resp.json()
    assert body["code"] == "OPEN_CHILD_BLOCKERS"
    assert child_key in body["blockers"]

    # Complete the child first
    child_proof = _make_valid_proof(child_key)
    child_comp_resp = await client.post(
        f"/api/v1/issues/{child_key}/complete-work",
        json={"summary_markdown": _make_valid_report(), "verification_proof": child_proof},
    )
    assert child_comp_resp.status_code == 200

    # 3. Create a dependency blocker via BLOCKS link
    dep_resp = await client.post(
        "/api/v1/projects/BLK/issues",
        json={"summary": "Blocking task", "description_markdown": "Blocker"},
    )
    assert dep_resp.status_code == 201, dep_resp.text
    dep_key = dep_resp.json()["key"]
    dep_id = dep_resp.json()["id"]

    # Link: dep BLOCKS parent
    link_resp = await client.post(
        f"/api/v1/objects/{dep_key}/links",
        json={"target": parent_key, "link_type": "BLOCKS"},
    )
    assert link_resp.status_code == 201, link_resp.text

    # Attempt complete parent -> blocked by BLOCKS link
    comp_resp2 = await client.post(
        f"/api/v1/issues/{parent_key}/complete-work",
        json={"summary_markdown": _make_valid_report(), "verification_proof": proof},
    )
    assert comp_resp2.status_code == 409
    body2 = comp_resp2.json()
    assert body2["code"] == "OPEN_CHILD_BLOCKERS"
    assert dep_key in body2["blockers"]


async def test_complete_work_redacted_foreign_blocker(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Caller without VIEW permission on foreign blocking issue gets redacted blocker notice."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member")

    proj_pub = await make_project(
        "PUB", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"}
    )
    proj_sec = await make_project(
        "SEC",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN"},  # member has NO access to SEC
    )

    client_admin = as_principal(admin)

    # Public issue
    pub_resp = await client_admin.post(
        "/api/v1/projects/PUB/issues",
        json={"summary": "Public task", "description_markdown": "Public"},
    )
    assert pub_resp.status_code == 201, pub_resp.text
    pub_key = pub_resp.json()["key"]

    # Secret issue
    sec_resp = await client_admin.post(
        "/api/v1/projects/SEC/issues",
        json={"summary": "Secret blocker", "description_markdown": "Secret"},
    )
    assert sec_resp.status_code == 201, sec_resp.text
    sec_key = sec_resp.json()["key"]

    # Link: SEC issue blocks PUB issue
    link_resp = await client_admin.post(
        f"/api/v1/objects/{sec_key}/links",
        json={"target": pub_key, "link_type": "BLOCKS"},
    )
    assert link_resp.status_code == 201, link_resp.text

    # Member attempts complete PUB issue -> blocked with redacted foreign identifier
    client_member = as_principal(member)
    proof = _make_valid_proof(pub_key)
    comp_resp = await client_member.post(
        f"/api/v1/issues/{pub_key}/complete-work",
        json={"summary_markdown": _make_valid_report(), "verification_proof": proof},
    )
    assert comp_resp.status_code == 409
    body = comp_resp.json()
    assert body["code"] == "OPEN_CHILD_BLOCKERS"
    assert "redacted: 1 hidden blocker" in body["blockers"]
    assert sec_key not in body["blockers"]


async def test_complete_work_path_validation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """complete_work rejects path traversal (..) and key mismatches in verification_proof."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("PTH", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/PTH/issues",
        json={"summary": "Path testing", "description_markdown": "Desc"},
    )
    issue_key = create_resp.json()["key"]

    # 1. Path traversal in artifact
    bad_proof = _make_valid_proof(issue_key)
    bad_proof["artifacts"].append(f"docs/qa/{issue_key}/../secret.txt")

    resp1 = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={"summary_markdown": "Bad path", "verification_proof": bad_proof},
    )
    assert resp1.status_code == 422
    assert resp1.json()["code"] == "VALIDATION_FAILED"

    # 2. Key mismatch in artifact
    mismatch_proof = _make_valid_proof(issue_key)
    mismatch_proof["artifacts"].append("docs/qa/OTHER-99/unit-test-results.txt")

    resp2 = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={"summary_markdown": "Mismatch key", "verification_proof": mismatch_proof},
    )
    assert resp2.status_code == 422
    assert resp2.json()["code"] == "VALIDATION_FAILED"


async def test_if_match_etag_handling(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """If-Match header is enforced on workflow mutations."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("ETG", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/ETG/issues",
        json={"summary": "ETag test", "description_markdown": "Original description"},
    )
    assert create_resp.status_code == 201
    issue_data = create_resp.json()
    issue_key = issue_data["key"]
    correct_etag = issue_data["description_sha256"]

    # Wrong ETag -> 412
    bw_fail = await client.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": "Plan"},
        headers={"if-match": "deadbeef" * 8},
    )
    assert bw_fail.status_code == 412
    assert bw_fail.json()["code"] == "CONFLICT_ETAG"

    # Correct ETag -> 200
    bw_ok = await client.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": "Plan"},
        headers={"if-match": f'"{correct_etag}"'},
    )
    assert bw_ok.status_code == 200


async def test_transition_held_conflict_on_all_endpoints(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Active pending_transition_exec_id causes 409 TRANSITION_HELD across endpoints."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("HLD", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/HLD/issues",
        json={"summary": "Held issue", "description_markdown": "Desc"},
    )
    issue_key = create_resp.json()["key"]

    # Mark issue as pending transition in database
    exec_id = uuid.uuid4()
    await api_env.seed.execute(
        text("UPDATE issues SET pending_transition_exec_id = :eid WHERE sequence_id = 1"),
        {"eid": exec_id},
    )
    await api_env.seed.commit()

    # begin-work -> 409
    res1 = await client.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": "Plan"},
    )
    assert res1.status_code == 409
    assert res1.json()["code"] == "TRANSITION_HELD"

    # transition -> 409
    res2 = await client.post(
        f"/api/v1/issues/{issue_key}/transition",
        json={"to_state": "Todo"},
    )
    assert res2.status_code == 409
    assert res2.json()["code"] == "TRANSITION_HELD"

    # complete-work -> 409
    proof = _make_valid_proof(issue_key)
    res3 = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={"summary_markdown": _make_valid_report(), "verification_proof": proof},
    )
    assert res3.status_code == 409
    assert res3.json()["code"] == "TRANSITION_HELD"


async def test_state_resolution_and_custom_to_state(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test UUID state resolution, invalid state error, and non-completed target state error."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("RES", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/RES/issues",
        json={"summary": "State resolution test", "description_markdown": "Desc"},
    )
    issue_key = create_resp.json()["key"]

    # Fetch states
    states = (
        await api_env.seed.execute(
            text("SELECT id, name, state_group FROM workflow_states WHERE project_id = :p"),
            {"p": proj_id},
        )
    ).all()
    todo_state = next(s for s in states if s[1] == "Todo")
    done_state = next(s for s in states if s[1] == "Done")

    # Transition using state UUID string
    tr_uuid_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transition",
        json={"to_state": str(todo_state[0]), "comment_markdown": "Move via UUID"},
    )
    assert tr_uuid_resp.status_code == 200
    assert tr_uuid_resp.json()["to_state"]["name"] == "Todo"

    # Invalid state string -> 422
    tr_inv_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transition",
        json={"to_state": "NonExistentState"},
    )
    assert tr_inv_resp.status_code == 422
    assert tr_inv_resp.json()["code"] == "INVALID_TRANSITION"

    # complete_work with non-completed state -> 422
    proof = _make_valid_proof(issue_key)
    comp_inv_resp = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={
            "summary_markdown": _make_valid_report(),
            "verification_proof": proof,
            "to_state": "Todo",
        },
    )
    assert comp_inv_resp.status_code == 422
    assert comp_inv_resp.json()["code"] == "INVALID_TRANSITION"

    # complete_work with valid completed UUID state -> 200
    comp_ok_resp = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={
            "summary_markdown": _make_valid_report(),
            "verification_proof": proof,
            "to_state": str(done_state[0]),
        },
    )
    assert comp_ok_resp.status_code == 200
    assert comp_ok_resp.json()["status"] == "completed"


async def test_complete_work_no_completed_state_error(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """complete_work returns 409 NO_COMPLETED_STATE when project lacks a completed state."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("NCS", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Change all completed states to started
    await api_env.seed.execute(
        text("UPDATE workflow_states SET state_group = 'started' WHERE project_id = :proj"),
        {"proj": proj_id},
    )
    await api_env.seed.commit()

    create_resp = await client.post(
        "/api/v1/projects/NCS/issues",
        json={"summary": "No completed state", "description_markdown": "Test"},
    )
    issue_key = create_resp.json()["key"]

    proof = _make_valid_proof(issue_key)
    cw_resp = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={"summary_markdown": _make_valid_report(), "verification_proof": proof},
    )
    assert cw_resp.status_code == 422
    assert cw_resp.json()["code"] == "INVALID_TRANSITION"
    assert "no workflow state configured in the 'completed' group" in cw_resp.json()["detail"]
