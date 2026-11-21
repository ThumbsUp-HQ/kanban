# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Enforcement unit tests for complete_work reality-checker report validation (KAN-45)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.issues.workflow_service import complete_work as service_complete_work

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _make_proof(ticket_key: str, verdict: str = "READY", grade: str = "A") -> dict[str, Any]:
    """Construct a valid VerificationProof dictionary for a ticket key."""
    return {
        "qa_dir": f"docs/qa/{ticket_key}/",
        "reality_checker": {
            "verdict": verdict,
            "grade": grade,
            "report_path": f"docs/qa/{ticket_key}/reality-checker-report.md",
        },
        "ci_run_url": "https://dash.hackedyour.info/runs/9876",
        "artifacts": [
            f"docs/qa/{ticket_key}/git-diff.patch",
            f"docs/qa/{ticket_key}/unit-test-results.txt",
        ],
    }


def _make_report(
    *,
    cert_verdict: str = "READY",
    cert_grade: str = "A",
    deployment_readiness: str = "READY",
    h2_order: list[str] | None = None,
) -> str:
    """Build canonical reality-checker report markdown."""
    sections = {
        "Reality Check Validation": "- Forensic check verified against real database.",
        "Complete System Evidence": "- Visual screenshots captured across viewports.",
        "Integration Testing Results": "- 100% automated test suites executed with 0 failures.",
        "Comprehensive Issue Assessment": "- Security invariants and policies validated.",
        "Realistic Quality Certification": f"- Verdict: {cert_verdict}\n- Grade: {cert_grade}",
        "Deployment Readiness Assessment": f"- Deployment Status: {deployment_readiness}",
    }

    order = h2_order or [
        "Reality Check Validation",
        "Complete System Evidence",
        "Integration Testing Results",
        "Comprehensive Issue Assessment",
        "Realistic Quality Certification",
        "Deployment Readiness Assessment",
    ]

    body_parts = ["# Integration Agent Reality-Based Report\n"]
    body_parts.extend(f"## {title}\n{sections[title]}\n" for title in order)
    return "\n".join(body_parts)


@pytest.mark.usefixtures("api_env")
async def test_complete_work_rejects_needs_work_summary_even_if_proof_ready(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """complete_work endpoint rejects NEEDS WORK in summary_markdown.

    Even when verification_proof asserts READY.
    """
    admin = await make_user("cw_admin_nw", workspace_role="WORKSPACE_ADMIN")
    await make_project("CWNW", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/CWNW/issues",
        json={"summary": "Needs work issue", "description_markdown": "Body"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]

    # Begin work
    await client.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": "Starting work"},
    )

    proof = _make_proof(issue_key, verdict="READY", grade="A")
    bad_summary = _make_report(
        cert_verdict="NEEDS WORK", cert_grade="C+", deployment_readiness="NEEDS WORK"
    )

    resp = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={
            "summary_markdown": bad_summary,
            "verification_proof": proof,
        },
    )
    assert resp.status_code == 422
    err_body = resp.json()
    assert err_body["code"] == "INVALID_REALITY_CHECKER_REPORT"
    assert "Contradiction marker 'NEEDS WORK'" in err_body["detail"]


@pytest.mark.usefixtures("api_env")
async def test_complete_work_rejects_out_of_order_h2_sections(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """complete_work endpoint rejects summary_markdown with canonical H2 headings out of order."""
    admin = await make_user("cw_admin_ord", workspace_role="WORKSPACE_ADMIN")
    await make_project("CWORD", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/CWORD/issues",
        json={"summary": "Out of order issue", "description_markdown": "Body"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]

    await client.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": "Starting work"},
    )

    proof = _make_proof(issue_key, verdict="READY", grade="A")
    bad_order_summary = _make_report(
        h2_order=[
            "Complete System Evidence",
            "Reality Check Validation",
            "Integration Testing Results",
            "Comprehensive Issue Assessment",
            "Realistic Quality Certification",
            "Deployment Readiness Assessment",
        ]
    )

    resp = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={
            "summary_markdown": bad_order_summary,
            "verification_proof": proof,
        },
    )
    assert resp.status_code == 422
    err_body = resp.json()
    assert err_body["code"] == "INVALID_REALITY_CHECKER_REPORT"
    assert "out of order" in err_body["detail"]


@pytest.mark.usefixtures("api_env")
async def test_complete_work_rejects_missing_ready_verdict(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """complete_work rejects summary_markdown that omits READY verdict.

    Even when contradiction markers are absent.
    """
    admin = await make_user("cw_admin_nr", workspace_role="WORKSPACE_ADMIN")
    await make_project("CWNR", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/CWNR/issues",
        json={"summary": "Missing ready issue", "description_markdown": "Body"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]

    await client.post(
        f"/api/v1/issues/{issue_key}/begin-work",
        json={"plan_markdown": "Starting work"},
    )

    proof = _make_proof(issue_key, verdict="READY", grade="A")
    no_ready_summary = _make_report(
        cert_verdict="IN PROGRESS", cert_grade="B", deployment_readiness="PENDING"
    )

    resp = await client.post(
        f"/api/v1/issues/{issue_key}/complete-work",
        json={
            "summary_markdown": no_ready_summary,
            "verification_proof": proof,
        },
    )
    assert resp.status_code == 422
    err_body = resp.json()
    assert err_body["code"] == "INVALID_REALITY_CHECKER_REPORT"
    assert "must certify READY with grade A" in err_body["detail"]


async def test_service_complete_work_direct_invocation_invariants(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Direct workflow_service.complete_work call enforces report invariants."""
    admin = await make_user("cw_admin_srv", workspace_role="WORKSPACE_ADMIN")
    await make_project("CWSRV", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    caller = PrincipalContext(
        principal_id=admin.id,
        workspace_id=api_env.workspace_id,
        token_scopes=("session",),
    )
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/CWSRV/issues",
        json={
            "summary": "Service level test issue",
            "description_markdown": "Service level description",
        },
    )
    assert create_resp.status_code == 201
    issue_data = create_resp.json()
    issue_key = issue_data["key"]

    proof = _make_proof(issue_key, verdict="READY", grade="A")

    # 1. Reject NEEDS WORK
    bad_summary = _make_report(
        cert_verdict="NEEDS WORK", cert_grade="C+", deployment_readiness="NEEDS WORK"
    )
    with pytest.raises(ProblemException) as exc1:
        await service_complete_work(
            session=api_env.seed,
            caller=caller,
            issue_ref=issue_key,
            summary_markdown=bad_summary,
            verification_proof=proof,
        )
    assert exc1.value.status == 422
    assert exc1.value.code == "INVALID_REALITY_CHECKER_REPORT"

    # 2. Reject out-of-order H2
    bad_order = _make_report(
        h2_order=[
            "Complete System Evidence",
            "Reality Check Validation",
            "Integration Testing Results",
            "Comprehensive Issue Assessment",
            "Realistic Quality Certification",
            "Deployment Readiness Assessment",
        ]
    )
    with pytest.raises(ProblemException) as exc2:
        await service_complete_work(
            session=api_env.seed,
            caller=caller,
            issue_ref=issue_key,
            summary_markdown=bad_order,
            verification_proof=proof,
        )
    assert exc2.value.status == 422
    assert exc2.value.code == "INVALID_REALITY_CHECKER_REPORT"
