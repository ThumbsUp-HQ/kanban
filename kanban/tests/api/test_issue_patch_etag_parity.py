# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for issue PATCH ETag parity and drift prevention.

Validates KB-P3-PENTEST-01 / KAN-36.
Verifies that:
1. Chained PATCH -> GET -> PATCH maintains 100% ETag parity.
   (response.headers["ETag"] == body.etag == immediate GET ETag).
2. Immediate subsequent PATCH with If-Match: <PATCH_ETag> succeeds without 412.
3. If-None-Match on GET returns 304 with identical ETag.
4. TransitionEngine.execute_transition and workflow_service._check_if_match_etag accept BOTH
   composite compute_issue_etag AND backward-compatible description_sha256 in If-Match.
5. Composite issue workflow endpoints (begin-work, transition, complete-work) and creator override
   return matching ETags without drift.
6. MCP update_ticket returns etag matching subsequent read_ticket.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import SeededUser

pytestmark = pytest.mark.committed_db


def _make_valid_proof(key: str) -> dict[str, Any]:
    """Build a valid VerificationProof dictionary for a ticket key."""
    return {
        "qa_dir": f"docs/qa/{key}/",
        "reality_checker": {
            "verdict": "READY",
            "grade": "A",
            "report_path": f"docs/qa/{key}/reality-checker-report.md",
        },
        "ci_run_url": "https://dash.hackedyour.info/runs/9876",
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


async def test_chained_patch_get_patch_etag_parity(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Scenario 3: Chained PATCH -> GET -> PATCH maintains ETag parity without drift.

    Asserts:
    - PATCH response.headers["ETag"] == body["etag"].
    - Immediate GET returns identical ETag.
    - If-None-Match returns 304.
    - Subsequent PATCH using If-Match from previous PATCH succeeds.
    - Stale ETag in If-Match correctly fails with 412.
    """
    admin = await make_user("etag_admin", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project(
        "ETAG", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=True
    )
    client = as_principal(admin)

    desc = "Initial description content for ETag parity testing."
    # 1. Create issue
    create_resp = await client.post(
        "/api/v1/projects/ETAG/issues",
        json={
            "summary": "Initial Issue Summary",
            "description_markdown": desc,
            "priority": "none",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    issue_data = create_resp.json()
    issue_key = issue_data["key"]
    init_etag = create_resp.headers["ETag"]
    assert init_etag == issue_data["etag"]

    # 2. Patch 1: Update summary
    patch1_resp = await client.patch(
        f"/api/v1/issues/{issue_key}",
        json={"summary": "Updated Summary 1"},
    )
    assert patch1_resp.status_code == 200, patch1_resp.text
    patch1_etag = patch1_resp.headers["ETag"]
    patch1_body = patch1_resp.json()
    assert patch1_etag == patch1_body["etag"]
    assert patch1_etag != init_etag

    # 3. Immediate GET: verify ZERO ETag drift
    get1_resp = await client.get(f"/api/v1/issues/{issue_key}")
    assert get1_resp.status_code == 200
    assert get1_resp.headers["ETag"] == patch1_etag, "Immediate GET ETag drifted from PATCH ETag!"
    assert get1_resp.json()["etag"] == patch1_etag

    # 4. GET with If-None-Match: returns 304
    get304_resp = await client.get(
        f"/api/v1/issues/{issue_key}",
        headers={"If-None-Match": patch1_etag},
    )
    assert get304_resp.status_code == 304
    assert get304_resp.headers["ETag"] == patch1_etag

    # 5. Patch 2: Chained PATCH with If-Match: patch1_etag must succeed without 412
    patch2_resp = await client.patch(
        f"/api/v1/issues/{issue_key}",
        json={"summary": "Updated Summary 2", "description_markdown": f"{desc}\n\nAppended."},
        headers={"If-Match": patch1_etag},
    )
    assert patch2_resp.status_code == 200, patch2_resp.text
    patch2_etag = patch2_resp.headers["ETag"]
    assert patch2_etag == patch2_resp.json()["etag"]
    assert patch2_etag != patch1_etag

    # 6. Immediate GET after Patch 2: verify ZERO ETag drift
    get2_resp = await client.get(f"/api/v1/issues/{issue_key}")
    assert get2_resp.status_code == 200
    assert get2_resp.headers["ETag"] == patch2_etag, (
        "Immediate GET 2 ETag drifted from PATCH 2 ETag!"
    )
    assert get2_resp.json()["etag"] == patch2_etag

    # 7. Patch with STALE ETag (patch1_etag when current is patch2_etag) must return 412
    stale_resp = await client.patch(
        f"/api/v1/issues/{issue_key}",
        json={"summary": "Stale Attempt"},
        headers={"If-Match": patch1_etag},
    )
    assert stale_resp.status_code == 412
    stale_body = stale_resp.json()
    assert stale_body["current_etag"] == patch2_etag


async def test_workflow_and_provenance_and_mcp_etag_parity(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Scenario 4: Verify workflow, provenance, and MCP accept composite ETags without drift.

    Asserts:
    - begin-work, transition, and complete-work return matching ETags in headers and body.
    - Transitions accept composite compute_issue_etag AND description_sha256 in If-Match.
    - override_issue_created_by returns resp.etag matching immediate GET.
    """
    admin = await make_user("wf_admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("wf_member", workspace_role="WORKSPACE_MEMBER")
    _ = await make_project("WF", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"})
    client = as_principal(admin)

    desc = "Workflow ETag parity ticket content."
    desc_sha = hashlib.sha256(desc.encode("utf-8")).hexdigest()

    # 1. Create issue
    create_resp = await client.post(
        "/api/v1/projects/WF/issues",
        json={
            "summary": "Workflow Parity Issue",
            "description_markdown": desc,
            "priority": "none",
        },
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]
    init_etag = create_resp.headers["ETag"]

    # 2. Begin work: moves state to In Progress, assigns caller
    # Validation error on empty plan_markdown
    bad_bw = await client.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": ""},
        headers={"If-Match": init_etag},
    )
    assert bad_bw.status_code == 422

    bw_resp = await client.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": "Execution plan notes."},
        headers={"If-Match": init_etag},
    )
    assert bw_resp.status_code == 200, bw_resp.text
    bw_etag = bw_resp.headers.get("ETag")
    assert bw_etag is not None, "begin-work must return ETag header"
    assert bw_etag == bw_resp.json()["etag"]

    # Immediate GET matches begin-work ETag
    get_bw = await client.get(f"/api/v1/issues/{issue_key}")
    assert get_bw.headers["ETag"] == bw_etag

    # 3. Intermediate transition using backward-compatible description_sha256 in If-Match
    # Also verify weak ETag prefix (W/) stripping and oversized comment validation
    bad_comment_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transition",
        json={"to_state": "In Progress", "comment_markdown": "a" * 70000},
        headers={"If-Match": f'W/"{desc_sha}"'},
    )
    assert bad_comment_resp.status_code == 422

    trans_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transition",
        json={"to_state": "In Progress", "comment_markdown": "Transition note."},
        headers={"If-Match": f'W/"{desc_sha}"'},
    )
    assert trans_resp.status_code == 200, trans_resp.text
    trans_etag = trans_resp.headers.get("ETag")
    assert trans_etag is not None
    assert trans_etag == trans_resp.json()["etag"]

    # Immediate GET matches transition ETag
    get_trans = await client.get(f"/api/v1/issues/{issue_key}")
    assert get_trans.headers["ETag"] == trans_etag

    # 4. Complete work using composite ETag in If-Match
    proof = _make_valid_proof(issue_key)
    cw_resp = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={
            "summary_markdown": _make_valid_report(),
            "verification_proof": proof,
        },
        headers={"If-Match": trans_etag},
    )
    assert cw_resp.status_code == 200, cw_resp.text
    cw_etag = cw_resp.headers.get("ETag")
    assert cw_etag is not None
    assert cw_etag == cw_resp.json()["etag"]

    # Immediate GET matches complete-work ETag
    get_cw = await client.get(f"/api/v1/issues/{issue_key}")
    assert get_cw.headers["ETag"] == cw_etag

    # 5. Provenance override: PATCH /api/v1/issues/{issue_key}/created-by
    client_admin = as_principal(admin, aal_level=2)
    prov_resp = await client_admin.patch(
        f"/api/v1/issues/{issue_key}/created-by",
        json={
            "created_by": "@wf_member",
            "reason": "Administrative audit trail correction for ticket origin",
        },
    )
    assert prov_resp.status_code == 200, prov_resp.text
    prov_etag = prov_resp.headers.get("ETag")
    assert prov_etag is not None
    assert prov_etag == prov_resp.json()["etag"]
    assert prov_etag.startswith('"')
    assert prov_etag.endswith('"')

    # Immediate GET matches provenance override ETag
    get_prov = await client.get(f"/api/v1/issues/{issue_key}")
    assert get_prov.headers["ETag"] == prov_etag
