"""Unit and integration tests for created-by admin override and provenance serializer (KB-P3-04)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from database.models.issues import Issue
from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.issue_provenance import IssueOverrideCreatorRequest
from kanban.api.v1.schemas.issues import IssueCreate
from kanban.services.issue_provenance import (
    build_issue_provenance,
    override_issue_created_by,
    resolve_creator_summary,
)
from kanban.services.issues import create_issue
from kanban.tests.security.helpers import add_acl_entry, create_agent, rebuild_era

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _count(env: ApiEnv, sql: str, params: dict[str, object] | None = None) -> int:
    """Execute count query directly."""
    row = await env.seed.execute(text(sql), params or {})
    return int(row.scalar_one())


async def test_case_1_positive_admin_override_and_provenance(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: AAL2 project admin overrides creator with a 20-char reason.

    Response provenance.overridden == true, original_created_by unchanged,
    exactly one CREATOR_OVERRIDDEN row with reason.
    """
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    original_creator = await make_user("original_creator", workspace_role="WORKSPACE_MEMBER")
    new_creator = await make_user("new_creator", workspace_role="WORKSPACE_MEMBER")
    await make_project(
        "PROV",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", original_creator: "MEMBER", new_creator: "MEMBER"},
    )

    # Original creator creates an issue
    client_orig = as_principal(original_creator)
    create_resp = await client_orig.post(
        "/api/v1/projects/PROV/issues",
        json={
            "summary": "Original issue summary",
            "description_markdown": "# Provenance test",
        },
    )
    assert create_resp.status_code == 201
    issue_data = create_resp.json()
    assert issue_data["provenance"]["overridden"] is False
    assert issue_data["provenance"]["created_by"]["handle"] == "original_creator"
    assert issue_data["provenance"]["original_created_by"]["handle"] == "original_creator"
    assert issue_data["provenance"]["creator_modified_by"] is None
    assert issue_data["provenance"]["reason"] is None

    # AAL2 Admin overrides creator
    client_admin = as_principal(admin, aal_level=2)
    override_reason = "12345678901234567890"  # Exactly 20 chars
    patch_resp = await client_admin.patch(
        "/api/v1/issues/PROV-1/created-by",
        json={
            "created_by": "@new_creator",
            "reason": override_reason,
        },
    )
    contract_recorder.record("override_creator_200", patch_resp.request, patch_resp)
    assert patch_resp.status_code == 200
    patched_data = patch_resp.json()

    # Assert provenance response fields
    prov = patched_data["provenance"]
    assert prov["overridden"] is True
    assert prov["created_by"]["id"] == str(new_creator.id)
    assert prov["created_by"]["handle"] == "new_creator"
    assert prov["original_created_by"]["id"] == str(original_creator.id)
    assert prov["original_created_by"]["handle"] == "original_creator"
    assert prov["creator_modified_by"]["id"] == str(admin.id)
    assert prov["creator_modified_by"]["handle"] == "admin"
    assert prov["creator_modified_at"] is not None
    assert prov["reason"] == override_reason

    # Verify exactly one CREATOR_OVERRIDDEN activity row
    select_act_sql = (
        "SELECT id, workspace_id, object_id, object_type, actor_id, event_type, "
        "payload, prev_hash, row_hash, chain_seq, recorded_at "
        "FROM activity_records WHERE object_id = :obj AND event_type = 'CREATOR_OVERRIDDEN'"
    )
    act_rows = (
        (
            await api_env.seed.execute(
                text(select_act_sql),
                {"obj": issue_data["id"]},
            )
        )
        .mappings()
        .all()
    )
    assert len(act_rows) == 1
    act = act_rows[0]
    assert act["event_type"] == "CREATOR_OVERRIDDEN"
    assert act["actor_id"] == admin.id
    assert act["payload"]["old_created_by_id"] == str(original_creator.id)
    assert act["payload"]["new_created_by_id"] == str(new_creator.id)
    assert act["payload"]["original_created_by_id"] == str(original_creator.id)
    assert act["payload"]["reason"] == override_reason
    assert len(bytes(act["prev_hash"])) == 32
    assert len(bytes(act["row_hash"])) == 32

    # Save raw activity row sample proof
    raw_sample = {
        "id": str(act["id"]),
        "workspace_id": str(act["workspace_id"]),
        "object_id": str(act["object_id"]),
        "object_type": str(act["object_type"]),
        "actor_id": str(act["actor_id"]),
        "event_type": act["event_type"],
        "chain_seq": act["chain_seq"],
        "payload": act["payload"],
        "recorded_at": act["recorded_at"].isoformat(),
        "prev_hash": bytes(act["prev_hash"]).hex(),
        "row_hash": bytes(act["row_hash"]).hex(),
    }
    proof_path = Path("/tmp/kb-wt-KANBA-84/docs/qa/KANBA-84/activity-row-sample.json")
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(raw_sample, indent=2), encoding="utf-8")  # noqa: ASYNC240


async def test_case_2_security_authorization_and_trigger_guards(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: Security checks for role, AAL level, visibility, and DB trigger regression guard."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member", workspace_role="WORKSPACE_MEMBER")
    outsider = await make_user("outsider")
    target_user = await make_user("target_user")
    await make_project(
        "SEC",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER", target_user: "MEMBER"},
    )

    # Admin creates issue SEC-1
    client_admin = as_principal(admin, aal_level=2)
    res = await client_admin.post(
        "/api/v1/projects/SEC/issues",
        json={"summary": "Security test issue", "description_markdown": "desc"},
    )
    assert res.status_code == 201

    # 2a: EDIT member gets 403 INSUFFICIENT_CAPABILITY
    client_member = as_principal(member, aal_level=2)
    resp_member = await client_member.patch(
        "/api/v1/issues/SEC-1/created-by",
        json={"created_by": str(target_user.id), "reason": "Valid reason exceeding ten"},
    )
    contract_recorder.record(
        "override_creator_403_insufficient_capability", resp_member.request, resp_member
    )
    assert resp_member.status_code == 403
    assert resp_member.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 2b: Non-viewer outsider gets 404 NOT_FOUND
    client_outsider = as_principal(outsider, aal_level=2)
    resp_outsider = await client_outsider.patch(
        "/api/v1/issues/SEC-1/created-by",
        json={"created_by": str(target_user.id), "reason": "Valid reason exceeding ten"},
    )
    contract_recorder.record("override_creator_404_not_found", resp_outsider.request, resp_outsider)
    assert resp_outsider.status_code == 404
    assert resp_outsider.json()["code"] == "NOT_FOUND"

    # 2c: AAL1 admin gets 403 AAL2_REQUIRED
    client_admin_aal1 = as_principal(admin, aal_level=1)
    resp_aal1 = await client_admin_aal1.patch(
        "/api/v1/issues/SEC-1/created-by",
        json={"created_by": str(target_user.id), "reason": "Valid reason exceeding ten"},
    )
    contract_recorder.record("override_creator_403_aal2_required", resp_aal1.request, resp_aal1)
    assert resp_aal1.status_code == 403
    assert resp_aal1.json()["code"] == "AAL2_REQUIRED"

    # 2d: Direct UPDATE issues SET created_by_id as non-admin session is rejected by trigger
    bind = api_env.seed.bind
    assert isinstance(bind, AsyncEngine)
    factory = RLSSessionFactory(bind)
    async with factory.session(
        RLSContext(principal_id=member.id, workspace_id=api_env.workspace_id, aal_level=1)
    ) as session:
        update_sql = "UPDATE issues SET created_by_id = :u WHERE summary = 'Security test issue'"
        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            async with session.begin_nested():
                await session.execute(text(update_sql), {"u": target_user.id})
        assert "CREATOR_OVERRIDE_FORBIDDEN" in str(exc_info.value)


async def test_case_3_validation_boundaries(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: Reason bounds (9, 10, 501), creator unchanged, non-viewer target."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    target_user = await make_user("target_user")
    outsider_user = await make_user("outsider_user")
    await make_project(
        "BND",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", target_user: "MEMBER"},
    )

    client = as_principal(admin, aal_level=2)
    c_resp = await client.post(
        "/api/v1/projects/BND/issues",
        json={"summary": "Boundary test issue", "description_markdown": "desc"},
    )
    assert c_resp.status_code == 201

    # 3a: Reason of 9 chars returns 422 REASON_REQUIRED
    resp_9 = await client.patch(
        "/api/v1/issues/BND-1/created-by",
        json={"created_by": str(target_user.id), "reason": "123456789"},
    )
    contract_recorder.record("override_creator_422_reason_required", resp_9.request, resp_9)
    assert resp_9.status_code == 422
    assert resp_9.json()["code"] == "REASON_REQUIRED"

    # 3b: Reason of 501 chars returns 422 REASON_REQUIRED
    resp_501 = await client.patch(
        "/api/v1/issues/BND-1/created-by",
        json={"created_by": str(target_user.id), "reason": "a" * 501},
    )
    assert resp_501.status_code == 422
    assert resp_501.json()["code"] == "REASON_REQUIRED"

    # 3c: Same creator returns 422 CREATOR_UNCHANGED
    resp_same = await client.patch(
        "/api/v1/issues/BND-1/created-by",
        json={"created_by": str(admin.id), "reason": "Valid reason exceeding ten"},
    )
    contract_recorder.record("override_creator_422_creator_unchanged", resp_same.request, resp_same)
    assert resp_same.status_code == 422
    assert resp_same.json()["code"] == "CREATOR_UNCHANGED"

    # 3d: Non-viewer target user returns 422 CREATOR_NOT_ELIGIBLE identical to random UUID
    resp_non_viewer = await client.patch(
        "/api/v1/issues/BND-1/created-by",
        json={"created_by": str(outsider_user.id), "reason": "Valid reason exceeding ten"},
    )
    contract_recorder.record(
        "override_creator_422_creator_not_eligible", resp_non_viewer.request, resp_non_viewer
    )
    assert resp_non_viewer.status_code == 422
    assert resp_non_viewer.json()["code"] == "CREATOR_NOT_ELIGIBLE"

    random_id = uuid.uuid4()
    resp_random = await client.patch(
        "/api/v1/issues/BND-1/created-by",
        json={"created_by": str(random_id), "reason": "Valid reason exceeding ten"},
    )
    assert resp_random.status_code == 422
    assert resp_random.json()["code"] == "CREATOR_NOT_ELIGIBLE"
    assert resp_random.json()["detail"] == resp_non_viewer.json()["detail"]

    # 3e: Reason of exactly 10 chars succeeds
    resp_10 = await client.patch(
        "/api/v1/issues/BND-1/created-by",
        json={"created_by": str(target_user.id), "reason": "1234567890"},
    )
    assert resp_10.status_code == 200
    assert resp_10.json()["provenance"]["reason"] == "1234567890"


async def test_case_4_redaction_for_out_of_boundary_viewer(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 4: Viewer outside admin's boundary sees creator_modified_by as redacted: true."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    target_user = await make_user("target_user")
    viewer = await make_user("viewer", workspace_role="WORKSPACE_MEMBER")

    await make_project(
        "RED",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", target_user: "MEMBER", viewer: "MEMBER"},
    )

    client_admin = as_principal(admin, aal_level=2)
    c_res = await client_admin.post(
        "/api/v1/projects/RED/issues",
        json={"summary": "Redaction issue", "description_markdown": "desc"},
    )
    assert c_res.status_code == 201

    # Override creator so creator_modified_by is admin
    ov_res = await client_admin.patch(
        "/api/v1/issues/RED-1/created-by",
        json={"created_by": str(target_user.id), "reason": "Overridden by admin"},
    )
    assert ov_res.status_code == 200

    # Add explicit DENY ACL on admin user object for viewer
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        admin.id,
        viewer.id,
        effect="DENY",
        capability_mask=1,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Viewer fetches issue RED-1
    client_viewer = as_principal(viewer)
    get_res = await client_viewer.get("/api/v1/issues/RED-1")
    assert get_res.status_code == 200
    prov = get_res.json()["provenance"]

    assert prov["overridden"] is True
    assert prov["creator_modified_by"]["redacted"] is True
    assert prov["creator_modified_by"]["label"] == "1 External Collaborator"
    assert "handle" not in prov["creator_modified_by"]
    assert "id" not in prov["creator_modified_by"]


async def test_case_5_second_override_preserves_original_creator(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 5: Second override keeps original_created_by_id and writes a second activity row."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    u1 = await make_user("u1")
    u2 = await make_user("u2")
    u3 = await make_user("u3")

    await make_project(
        "MULTI",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", u1: "MEMBER", u2: "MEMBER", u3: "MEMBER"},
    )

    client_u1 = as_principal(u1)
    c_res = await client_u1.post(
        "/api/v1/projects/MULTI/issues",
        json={"summary": "Multi override issue", "description_markdown": "desc"},
    )
    assert c_res.status_code == 201

    # First override: u1 -> u2
    client_admin = as_principal(admin, aal_level=2)
    ov1 = await client_admin.patch(
        "/api/v1/issues/MULTI-1/created-by",
        json={"created_by": str(u2.id), "reason": "First override reason 123"},
    )
    assert ov1.status_code == 200
    assert ov1.json()["provenance"]["original_created_by"]["id"] == str(u1.id)
    assert ov1.json()["provenance"]["created_by"]["id"] == str(u2.id)
    assert ov1.json()["provenance"]["reason"] == "First override reason 123"

    # Second override: u2 -> u3
    ov2 = await client_admin.patch(
        "/api/v1/issues/MULTI-1/created-by",
        json={"created_by": str(u3.id), "reason": "Second override reason 456"},
    )
    assert ov2.status_code == 200
    assert ov2.json()["provenance"]["original_created_by"]["id"] == str(u1.id)
    assert ov2.json()["provenance"]["created_by"]["id"] == str(u3.id)
    assert ov2.json()["provenance"]["reason"] == "Second override reason 456"

    # Verify exactly 2 CREATOR_OVERRIDDEN activity records
    count_sql = (
        "SELECT count(*) FROM activity_records WHERE event_type = 'CREATOR_OVERRIDDEN' "
        "AND object_id = (SELECT id FROM objects WHERE canonical_key = 'MULTI-1')"
    )
    act_count = await _count(api_env, count_sql)
    assert act_count == 2


async def test_provenance_services_validation_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Direct unit tests for service validation, authorization, and summary helpers."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    u1 = await make_user("u1", workspace_role="WORKSPACE_MEMBER")
    await make_project("VAL", created_by=admin, roles={admin: "PROJECT_ADMIN", u1: "MEMBER"})

    bind = api_env.seed.bind
    assert isinstance(bind, AsyncEngine)
    factory = RLSSessionFactory(bind)

    # Create an issue VAL-1
    async with factory.session(
        RLSContext(principal_id=admin.id, workspace_id=api_env.workspace_id, aal_level=2)
    ) as session:
        await create_issue(
            session,
            PrincipalContext(
                principal_id=admin.id,
                workspace_id=api_env.workspace_id,
                token_scopes=("session",),
                aal_level=2,
            ),
            "VAL",
            IssueCreate(summary="Validation test issue", description_markdown="desc"),
        )
        await session.commit()

    async with factory.session(
        RLSContext(
            principal_id=admin.id,
            workspace_id=api_env.workspace_id,
            token_scopes=("session",),
            aal_level=2,
        )
    ) as session:
        # 1. resolve_creator_summary with None
        summary_none = await resolve_creator_summary(session, None)
        assert summary_none is None

        # 2. resolve_creator_summary with non-existent id
        summary_missing = await resolve_creator_summary(session, uuid.uuid4())
        assert summary_missing is not None
        assert summary_missing.model_dump()["redacted"] is True

        caller_ctx = PrincipalContext(
            principal_id=admin.id,
            workspace_id=api_env.workspace_id,
            token_scopes=("session",),
            aal_level=2,
        )

        # 3. override_issue_created_by with non-existent issue
        with pytest.raises(ProblemException) as exc_404:
            await override_issue_created_by(
                session,
                caller_ctx,
                "NONEXISTENT-9999",
                IssueOverrideCreatorRequest(
                    created_by=str(u1.id),
                    reason="Valid reason exceeding ten",
                ),
            )
        assert exc_404.value.status == 404

        # 4. Reason validation length < 10
        with pytest.raises(ProblemException) as exc_reason_short:
            await override_issue_created_by(
                session,
                caller_ctx,
                "VAL-1",
                IssueOverrideCreatorRequest(created_by=str(u1.id), reason="short"),
            )
        assert exc_reason_short.value.status == 422
        assert exc_reason_short.value.code == "REASON_REQUIRED"

        # 5. Caller lacking admin role
        async with factory.session(
            RLSContext(
                principal_id=u1.id,
                workspace_id=api_env.workspace_id,
                token_scopes=("session",),
                aal_level=2,
            )
        ) as member_session:
            member_ctx = PrincipalContext(
                principal_id=u1.id,
                workspace_id=api_env.workspace_id,
                token_scopes=("session",),
                aal_level=2,
            )
            with pytest.raises(ProblemException) as exc_role:
                await override_issue_created_by(
                    member_session,
                    member_ctx,
                    "VAL-1",
                    IssueOverrideCreatorRequest(
                        created_by=str(admin.id),
                        reason="Valid reason exceeding ten",
                    ),
                )
            assert exc_role.value.status == 403
            assert exc_role.value.code == "INSUFFICIENT_CAPABILITY"

        # 6. Caller with AAL1
        aal1_ctx = PrincipalContext(
            principal_id=admin.id,
            workspace_id=api_env.workspace_id,
            token_scopes=("session",),
            aal_level=1,
        )
        with pytest.raises(ProblemException) as exc_aal:
            await override_issue_created_by(
                session,
                aal1_ctx,
                "VAL-1",
                IssueOverrideCreatorRequest(
                    created_by=str(u1.id),
                    reason="Valid reason exceeding ten",
                ),
            )
        assert exc_aal.value.status == 403
        assert exc_aal.value.code == "AAL2_REQUIRED"


async def test_provenance_services_execution_and_trigger_guards(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Direct unit tests for eligibility, trigger error mappings, and fallback branches."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    u1 = await make_user("u1", workspace_role="WORKSPACE_MEMBER")
    other_user = await make_user("other_user")
    await make_project("EXEC", created_by=admin, roles={admin: "PROJECT_ADMIN", u1: "MEMBER"})

    bind = api_env.seed.bind
    assert isinstance(bind, AsyncEngine)
    factory = RLSSessionFactory(bind)

    async with factory.session(
        RLSContext(principal_id=admin.id, workspace_id=api_env.workspace_id, aal_level=2)
    ) as session:
        await create_issue(
            session,
            PrincipalContext(
                principal_id=admin.id,
                workspace_id=api_env.workspace_id,
                token_scopes=("session",),
                aal_level=2,
            ),
            "EXEC",
            IssueCreate(summary="Exec test issue", description_markdown="desc"),
        )
        await session.commit()

    async with factory.session(
        RLSContext(
            principal_id=admin.id,
            workspace_id=api_env.workspace_id,
            token_scopes=("session",),
            aal_level=2,
        )
    ) as session:
        caller_ctx = PrincipalContext(
            principal_id=admin.id,
            workspace_id=api_env.workspace_id,
            token_scopes=("session",),
            aal_level=2,
        )

        # 7. Target user not found by handle
        with pytest.raises(ProblemException) as exc_no_user:
            await override_issue_created_by(
                session,
                caller_ctx,
                "EXEC-1",
                IssueOverrideCreatorRequest(
                    created_by="@does_not_exist",
                    reason="Valid reason exceeding ten",
                ),
            )
        assert exc_no_user.value.status == 422
        assert exc_no_user.value.code == "CREATOR_NOT_ELIGIBLE"

        # 8. Target user who is an agent
        agent_id = await create_agent(api_env.seed, api_env.workspace_id, "Test Agent")
        await api_env.seed.commit()
        with pytest.raises(ProblemException) as exc_agent:
            await override_issue_created_by(
                session,
                caller_ctx,
                "EXEC-1",
                IssueOverrideCreatorRequest(
                    created_by=str(agent_id),
                    reason="Valid reason exceeding ten",
                ),
            )
        assert exc_agent.value.status == 422
        assert exc_agent.value.code == "CREATOR_NOT_ELIGIBLE"

        # 9. Target user who lacks VIEW on project
        with pytest.raises(ProblemException) as exc_no_view:
            await override_issue_created_by(
                session,
                caller_ctx,
                "EXEC-1",
                IssueOverrideCreatorRequest(
                    created_by=str(other_user.id),
                    reason="Valid reason exceeding ten",
                ),
            )
        assert exc_no_view.value.status == 422
        assert exc_no_view.value.code == "CREATOR_NOT_ELIGIBLE"

        # 10. Target user who is already creator
        with pytest.raises(ProblemException) as exc_same:
            await override_issue_created_by(
                session,
                caller_ctx,
                "EXEC-1",
                IssueOverrideCreatorRequest(
                    created_by=str(admin.id),
                    reason="Valid reason exceeding ten",
                ),
            )
        assert exc_same.value.status == 422
        assert exc_same.value.code == "CREATOR_UNCHANGED"

        # 11. Fake issue provenance without creator_modified_at and without reason
        fake_issue = Issue(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            sequence_id=999,
            summary="Fake Issue",
            created_by_id=u1.id,
            original_created_by_id=admin.id,
            creator_modified_by_id=None,
            creator_modified_at=None,
        )
        fake_prov = await build_issue_provenance(session, fake_issue)
        assert fake_prov.overridden is True
        assert fake_prov.creator_modified_at is None
        assert fake_prov.reason is None


async def test_provenance_trigger_error_mappings(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Direct unit tests for trigger exception mappings."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    u1 = await make_user("u1", workspace_role="WORKSPACE_MEMBER")
    await make_project("TRIG", created_by=admin, roles={admin: "PROJECT_ADMIN", u1: "MEMBER"})

    bind = api_env.seed.bind
    assert isinstance(bind, AsyncEngine)
    factory = RLSSessionFactory(bind)

    async with factory.session(
        RLSContext(principal_id=admin.id, workspace_id=api_env.workspace_id, aal_level=2)
    ) as session:
        await create_issue(
            session,
            PrincipalContext(
                principal_id=admin.id,
                workspace_id=api_env.workspace_id,
                token_scopes=("session",),
                aal_level=2,
            ),
            "TRIG",
            IssueCreate(summary="Trig test issue", description_markdown="desc"),
        )
        await session.commit()

    async with factory.session(
        RLSContext(
            principal_id=admin.id,
            workspace_id=api_env.workspace_id,
            token_scopes=("session",),
            aal_level=2,
        )
    ) as session:
        caller_ctx = PrincipalContext(
            principal_id=admin.id,
            workspace_id=api_env.workspace_id,
            token_scopes=("session",),
            aal_level=2,
        )

        orig_execute = session.execute

        async def mock_exec_forbid(stmt: object, *args: object, **kwargs: object) -> object:
            if "UPDATE issues" in str(stmt):
                msg = "UPDATE"
                err = Exception("CREATOR_OVERRIDE_FORBIDDEN")
                raise DBAPIError(msg, {}, err)
            return await orig_execute(stmt, *args, **kwargs)  # type: ignore[call-overload]

        with (
            patch.object(session, "execute", side_effect=mock_exec_forbid),
            pytest.raises(ProblemException) as exc_trig_forbid,
        ):
            await override_issue_created_by(
                session,
                caller_ctx,
                "TRIG-1",
                IssueOverrideCreatorRequest(
                    created_by=str(u1.id),
                    reason="Valid reason exceeding ten",
                ),
            )
        assert exc_trig_forbid.value.status == 403

        async def mock_exec_ws(stmt: object, *args: object, **kwargs: object) -> object:
            if "UPDATE issues" in str(stmt):
                msg = "UPDATE"
                err = Exception("CREATOR_OVERRIDE_WORKSPACE_MISMATCH")
                raise DBAPIError(msg, {}, err)
            return await orig_execute(stmt, *args, **kwargs)  # type: ignore[call-overload]

        with (
            patch.object(session, "execute", side_effect=mock_exec_ws),
            pytest.raises(ProblemException) as exc_trig_ws,
        ):
            await override_issue_created_by(
                session,
                caller_ctx,
                "TRIG-1",
                IssueOverrideCreatorRequest(
                    created_by=str(u1.id),
                    reason="Valid reason exceeding ten",
                ),
            )
        assert exc_trig_ws.value.status == 422

        async def mock_exec_other(stmt: object, *args: object, **kwargs: object) -> object:
            if "UPDATE issues" in str(stmt):
                msg = "UPDATE"
                err = Exception("OTHER_DB_ERROR")
                raise DBAPIError(msg, {}, err)
            return await orig_execute(stmt, *args, **kwargs)  # type: ignore[call-overload]

        with (
            patch.object(session, "execute", side_effect=mock_exec_other),
            pytest.raises(DBAPIError),
        ):
            await override_issue_created_by(
                session,
                caller_ctx,
                "TRIG-1",
                IssueOverrideCreatorRequest(
                    created_by=str(u1.id),
                    reason="Valid reason exceeding ten",
                ),
            )
