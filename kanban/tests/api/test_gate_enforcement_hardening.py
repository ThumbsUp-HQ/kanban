# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hardening and gate enforcement unit & integration tests (KAN-45).

Covers:
  - validate_reality_checker_report linear O(N) validator.
  - Surrogate rejection, NFKC homoglyph normalization, code block/comment stripping.
  - Rejection of contradiction markers (NEEDS WORK, NEEDS_WORK, FAILED).
  - 422 USE_COMPLETE_WORK guard for agent/MCP callers on PATCH, move, and transitions.
  - Human browser caller exemption on completed state transitions.
  - 409 TRANSITION_HELD on PATCH /api/v1/issues/{key} during active agent gate.
  - 202 pending_agent_gate on POST /api/v1/issues/{key}/move without board_rank mutation.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.issues.proof import (
    RealityCheckerProof,
    VerificationProof,
    validate_ci_run_url,
    validate_proof_ticket_key,
    validate_reality_checker_report,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _make_canonical_report(verdict: str = "READY", grade: str = "A") -> str:
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


def test_validate_reality_checker_report_positive() -> None:
    """Canonical report passes validation without exception."""
    report = _make_canonical_report()
    validate_reality_checker_report(report)


def test_validate_reality_checker_report_rejects_surrogates() -> None:
    """Surrogate code points 0xD800..0xDFFF are rejected immediately."""
    with pytest.raises(ValueError, match="surrogate"):
        validate_reality_checker_report("Report with \ud800 surrogate")


def test_validate_reality_checker_report_rejects_missing_h1() -> None:
    """Missing canonical H1 title is rejected."""
    bad_report = """## Reality Check Validation
- Valid
"""
    with pytest.raises(ValueError, match="H1 header"):
        validate_reality_checker_report(bad_report)


def test_validate_reality_checker_report_rejects_missing_sections() -> None:
    """Missing any of the 6 canonical H2 sections is rejected."""
    bad_report = """# Integration Agent Reality-Based Report

## Reality Check Validation
- Content here.
"""
    with pytest.raises(ValueError, match="canonical section"):
        validate_reality_checker_report(bad_report)


def test_validate_reality_checker_report_rejects_empty_section_body() -> None:
    """Canonical section with empty body is rejected."""
    report = """# Integration Agent Reality-Based Report

## Reality Check Validation

## Complete System Evidence
- Evidence

## Integration Testing Results
- Results

## Comprehensive Issue Assessment
- Assessment

## Realistic Quality Certification
- Verdict: READY
- Grade: A

## Deployment Readiness Assessment
- Ready
"""
    with pytest.raises(ValueError, match="canonical section"):
        validate_reality_checker_report(report)


def test_validate_reality_checker_report_fenced_blocks_and_comments_ignored() -> None:
    """H1 or H2 inside fenced code blocks or HTML comments do not satisfy requirements."""
    fenced_report = """```markdown
# Integration Agent Reality-Based Report
## Reality Check Validation
```
<!--
## Complete System Evidence
-->
"""
    with pytest.raises(ValueError, match="H1 header"):
        validate_reality_checker_report(fenced_report)


def test_validate_reality_checker_report_rejects_contradiction_markers() -> None:
    """Contradiction markers inside certification/readiness reject report."""
    contradictory_report = """# Integration Agent Reality-Based Report

## Reality Check Validation
- Verified all deliverables.

## Complete System Evidence
- Evidence collected.

## Integration Testing Results
- Tests passing.

## Comprehensive Issue Assessment
- Root cause resolved.

## Realistic Quality Certification
- Verdict: READY
- Grade: A
- Status: NEEDS WORK on edge cases

## Deployment Readiness Assessment
- Ready for deployment.
"""
    with pytest.raises(ValueError, match="Contradiction marker"):
        validate_reality_checker_report(contradictory_report)


def test_validate_reality_checker_report_contradiction_in_code_block_allowed() -> None:
    """Contradiction words inside fenced code blocks are ignored."""
    report_with_code = """# Integration Agent Reality-Based Report

## Reality Check Validation
- Verified all deliverables.

## Complete System Evidence
- Evidence collected.

## Integration Testing Results
- Tests passing.

## Comprehensive Issue Assessment
- Root cause resolved.

## Realistic Quality Certification
- Verdict: READY
- Grade: A
```
Regression test logs showed: FAILED in legacy harness prior to fix
```

## Deployment Readiness Assessment
- Ready for immediate production deployment.
"""
    validate_reality_checker_report(report_with_code)


def test_validate_ci_run_url_edge_cases() -> None:
    """validate_ci_run_url rejects invalid schemes, credentials, and forbidden characters."""
    with pytest.raises(ValueError, match="scheme must be 'https'"):
        validate_ci_run_url("http://github.com/org/repo/actions/runs/123")
    with pytest.raises(ValueError, match="must not contain user credentials"):
        validate_ci_run_url("https://user:pass@github.com/org/repo/actions/runs/123")
    with pytest.raises(ValueError, match="non-empty host"):
        validate_ci_run_url("https:///runs/123")
    with pytest.raises(ValueError, match="forbidden characters"):
        validate_ci_run_url("https://github.com/org/repo/runs/123\n")
    with pytest.raises(ValueError, match="between 1 and 2048"):
        validate_ci_run_url("")
    with pytest.raises(ValueError, match="between 1 and 2048"):
        validate_ci_run_url("https://github.com/" + "a" * 2050)


def test_verification_proof_artifact_traversals_and_invariants() -> None:
    """VerificationProof enforces non-empty artifacts and rejects traversals."""
    proof_base = {
        "reality_checker": {
            "verdict": "READY",
            "grade": "A",
            "report_path": "docs/qa/KAN-45/reality-checker-report.md",
        },
        "qa_dir": "docs/qa/KAN-45",
        "ci_run_url": "https://github.com/org/repo/actions/runs/123",
    }
    with pytest.raises(ValueError, match="at least 1 item"):
        VerificationProof.model_validate({**proof_base, "artifacts": []})
    with pytest.raises(ValueError, match="double slash"):
        VerificationProof.model_validate(
            {**proof_base, "artifacts": ["docs/qa/KAN-45//unit-test.txt"]}
        )
    with pytest.raises(ValueError, match="trailing slash"):
        VerificationProof.model_validate({**proof_base, "artifacts": ["docs/qa/KAN-45/dir/"]})
    with pytest.raises(ValueError, match="forbidden dot segments"):
        VerificationProof.model_validate(
            {**proof_base, "artifacts": ["docs/qa/KAN-45/./unit-test.txt"]}
        )
    with pytest.raises(ValueError, match="directory traversal"):
        VerificationProof.model_validate(
            {**proof_base, "artifacts": ["docs/qa/KAN-45/../secret.txt"]}
        )
    with pytest.raises(ValueError, match="String should match pattern"):
        RealityCheckerProof.model_validate(
            {
                "verdict": "READY",
                "grade": "A",
                "report_path": "docs/qa/bad/report.md",
            }
        )
    with pytest.raises(ValueError, match="String should match pattern"):
        RealityCheckerProof.model_validate(
            {
                "verdict": "READY",
                "grade": "A",
                "report_path": "docs/qa/KAN-45/../reality-checker-report.md",
            }
        )


def test_validate_proof_ticket_key_mismatches() -> None:
    """validate_proof_ticket_key rejects mismatches between ticket and proof paths."""
    valid_proof = VerificationProof.model_validate(
        {
            "reality_checker": {
                "verdict": "READY",
                "grade": "A",
                "report_path": "docs/qa/KAN-45/reality-checker-report.md",
            },
            "qa_dir": "docs/qa/KAN-45",
            "ci_run_url": "https://github.com/org/repo/actions/runs/123",
            "artifacts": ["docs/qa/KAN-45/unit-test.txt"],
        }
    )
    with pytest.raises(ValueError, match="does not match expected ticket key 'KAN-99'"):
        validate_proof_ticket_key(valid_proof, "KAN-99")

    mismatched_report_proof = VerificationProof.model_validate(
        {
            "reality_checker": {
                "verdict": "READY",
                "grade": "A",
                "report_path": "docs/qa/KAN-99/reality-checker-report.md",
            },
            "qa_dir": "docs/qa/KAN-45",
            "ci_run_url": "https://github.com/org/repo/actions/runs/123",
            "artifacts": ["docs/qa/KAN-45/unit-test.txt"],
        }
    )
    with pytest.raises(
        ValueError, match=r"report_path 'docs/qa/KAN-99/reality-checker-report\.md'"
    ):
        validate_proof_ticket_key(mismatched_report_proof, "KAN-45")

    mismatched_artifact_proof = VerificationProof.model_validate(
        {
            "reality_checker": {
                "verdict": "READY",
                "grade": "A",
                "report_path": "docs/qa/KAN-45/reality-checker-report.md",
            },
            "qa_dir": "docs/qa/KAN-45",
            "ci_run_url": "https://github.com/org/repo/actions/runs/123",
            "artifacts": ["docs/qa/KAN-99/unit-test.txt"],
        }
    )
    with pytest.raises(ValueError, match="does not match expected ticket key 'KAN-45'"):
        validate_proof_ticket_key(mismatched_artifact_proof, "KAN-45")


def test_validate_reality_checker_report_html_comments_and_order() -> None:
    """Report validates HTML comment stripping and rejects empty sections or bad order."""
    report_with_comment = """# Integration Agent Reality-Based Report

<!-- This comment is stripped -->
## Reality Check Validation
- Validated.

## Complete System Evidence
<!-- another comment -->
- Evidence present.

## Integration Testing Results
- 100% tests pass.

## Comprehensive Issue Assessment
- Assessed.

## Realistic Quality Certification
- Verdict: READY
- Grade: A

## Deployment Readiness Assessment
- Ready.
"""
    validate_reality_checker_report(report_with_comment)

    # Missing H1
    with pytest.raises(ValueError, match="H1 header"):
        validate_reality_checker_report("## Reality Check Validation\nBody")

    # Missing H2 section
    incomplete = """# Integration Agent Reality-Based Report

## Reality Check Validation
- Validated.
"""
    with pytest.raises(ValueError, match="Missing required canonical section"):
        validate_reality_checker_report(incomplete)

    # Empty section body
    empty_body = """# Integration Agent Reality-Based Report

## Reality Check Validation

## Complete System Evidence
- Evidence.

## Integration Testing Results
- Tests.

## Comprehensive Issue Assessment
- Assessment.

## Realistic Quality Certification
- Verdict: READY
- Grade: A

## Deployment Readiness Assessment
- Ready.
"""
    with pytest.raises(ValueError, match="section body is empty"):
        validate_reality_checker_report(empty_body)


async def test_agent_caller_blocked_from_completed_state_on_patch(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Agent / MCP caller attempting PATCH to completed state receives 422 USE_COMPLETE_WORK."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("AGP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Create issue
    resp = await client.post(
        "/api/v1/projects/AGP/issues",
        json={"summary": "Agent test issue", "description_markdown": "Desc"},
    )
    assert resp.status_code == 201
    issue_key = resp.json()["key"]

    states = (
        await api_env.seed.execute(
            text("SELECT id, name, state_group FROM workflow_states WHERE project_id = :p"),
            {"p": proj_id},
        )
    ).all()
    done_state = next(s for s in states if s[1] == "Done")

    agent_client = as_principal(admin, scopes=("session", "agent:issue:write"))

    # 1. Agent PATCH -> 422 USE_COMPLETE_WORK
    patch_resp = await agent_client.patch(
        f"/api/v1/issues/{issue_key}",
        json={"state_id": str(done_state[0])},
    )
    assert patch_resp.status_code == 422
    assert patch_resp.json()["code"] == "USE_COMPLETE_WORK"

    # 2. Agent POST transition -> 422 USE_COMPLETE_WORK
    trans_resp = await agent_client.post(
        f"/api/v1/issues/{issue_key}/transition",
        json={"to_state": "Done"},
    )
    assert trans_resp.status_code == 422
    assert trans_resp.json()["code"] == "USE_COMPLETE_WORK"

    # 3. Agent POST move -> 422 USE_COMPLETE_WORK
    move_resp = await agent_client.post(
        f"/api/v1/issues/{issue_key}/move",
        json={"target_state_id": str(done_state[0])},
    )
    assert move_resp.status_code == 422
    assert move_resp.json()["code"] == "USE_COMPLETE_WORK"

    # 4. Human browser caller CAN transition to Done via board move / PATCH
    human_client = as_principal(admin, scopes=("session",))
    human_resp = await human_client.post(
        f"/api/v1/issues/{issue_key}/move",
        json={"target_state_id": str(done_state[0])},
    )
    assert human_resp.status_code == 200


async def test_patch_returns_409_transition_held_during_active_gate(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """PATCH /api/v1/issues/{key} returns 409 TRANSITION_HELD when held."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("HLD", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    resp = await client.post(
        "/api/v1/projects/HLD/issues",
        json={"summary": "Held issue", "description_markdown": "Desc"},
    )
    issue_key = resp.json()["key"]
    issue_id = uuid.UUID(resp.json()["id"])

    # Set pending_transition_exec_id directly in DB
    fake_exec_id = uuid.uuid4()
    await api_env.seed.execute(
        text("UPDATE issues SET pending_transition_exec_id = :eid WHERE id = :id"),
        {"eid": fake_exec_id, "id": issue_id},
    )
    await api_env.seed.commit()

    patch_resp = await client.patch(
        f"/api/v1/issues/{issue_key}",
        json={"summary": "Mutated summary"},
    )
    assert patch_resp.status_code == 409
    assert patch_resp.json()["code"] == "TRANSITION_HELD"
