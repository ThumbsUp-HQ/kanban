"""Typed object links, canonical URL helper, and restricted-target masking API tests.

Traceability: Spec S7.2 8m, S12.1.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from database.models import ObjectKind, ObjectRecord
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.links import LinkCreateRequest
from kanban.services.links import build_canonical_url, create_object_link, list_object_links
from kanban.services.object_ref import resolve_object_ref
from kanban.settings import Settings
from kanban.tests.security.helpers import (
    add_role_binding,
    create_registered_object,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db

_VOLATILE_KEYS = frozenset({"request_id", "instance"})


def _strip(body: dict[str, Any]) -> dict[str, Any]:
    """Remove request-scoped members before comparing problem documents."""
    return {k: v for k, v in body.items() if k not in _VOLATILE_KEYS}


async def _count(env: ApiEnv, sql: str, **params: Any) -> int:  # noqa: ANN401
    """Return a scalar count from the committed seed session."""
    await env.seed.rollback()
    return int((await env.seed.execute(text(sql), params)).scalar_one())


async def _create_test_issue(client: httpx.AsyncClient, project_key: str, summary: str) -> str:
    """Create an issue via API and return its canonical key."""
    resp = await client.post(
        f"/api/v1/projects/{project_key}/issues",
        json={"summary": summary, "description_markdown": f"Body for {summary}"},
    )
    assert resp.status_code == 201, resp.text
    key = resp.json()["key"]
    assert isinstance(key, str)
    return key


async def test_case_1_positive_link_creation_bidirectional_and_activity(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: KAN-1 BLOCKS KAN-2 returns 201, GET lists outbound/inbound, 2 LINK_CREATED rows."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("KAN", created_by=admin)
    client = as_principal(admin)

    k1 = await _create_test_issue(client, "KAN", "First Issue")
    k2 = await _create_test_issue(client, "KAN", "Second Issue")

    # 1. Create link: KAN-1 BLOCKS KAN-2
    resp = await client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k2, "link_type": "BLOCKS"},
    )
    contract_recorder.record("create_link_201", resp.request, resp)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    link_id = body["id"]
    assert body["link_type"] == "BLOCKS"
    assert body["link_state"] == "ACTIVE"
    assert body["target"]["key"] == k2
    assert body["target"]["type"] == "issue"

    # 2. GET on KAN-1: lists outbound link
    r_k1 = await client.get(f"/api/v1/objects/{k1}/links")
    assert r_k1.status_code == 200
    b_k1 = r_k1.json()
    assert len(b_k1["outbound"]) == 1
    assert b_k1["outbound"][0]["id"] == link_id
    assert b_k1["outbound"][0]["target"]["key"] == k2
    assert len(b_k1["inbound"]) == 0
    assert b_k1["truncated"] is False

    # 3. GET on KAN-2: lists inbound link
    r_k2 = await client.get(f"/api/v1/objects/{k2}/links")
    assert r_k2.status_code == 200
    b_k2 = r_k2.json()
    assert len(b_k2["outbound"]) == 0
    assert len(b_k2["inbound"]) == 1
    assert b_k2["inbound"][0]["id"] == link_id
    assert b_k2["inbound"][0]["source"]["key"] == k1
    assert b_k2["truncated"] is False

    # 4. Check two LINK_CREATED activity rows written
    activity_count = await _count(
        api_env,
        "SELECT count(*) FROM activity_records WHERE event_type = 'LINK_CREATED'",
    )
    assert activity_count == 2


async def test_case_2_restricted_target_masking(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: Link from readable KAN-1 to SEC-9 shows restricted: true without id/key/title."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer", workspace_role="WORKSPACE_GUEST")

    await make_project("KAN", created_by=admin, roles={viewer: "VIEWER"})
    await make_project("SEC", created_by=admin)

    admin_client = as_principal(admin)
    k1 = await _create_test_issue(admin_client, "KAN", "Public Issue 1")
    s9 = await _create_test_issue(admin_client, "SEC", "Secret Issue 9")

    # Admin creates link: KAN-1 RELATES_TO SEC-9
    resp = await admin_client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": s9, "link_type": "RELATES_TO"},
    )
    assert resp.status_code == 201, resp.text

    # Also admin creates reverse link: SEC-9 RELATES_TO KAN-1
    resp_rev = await admin_client.post(
        f"/api/v1/objects/{s9}/links",
        json={"target": k1, "link_type": "RELATES_TO"},
    )
    assert resp_rev.status_code == 201, resp_rev.text

    # Viewer queries KAN-1 links
    viewer_client = as_principal(viewer)
    r_viewer = await viewer_client.get(f"/api/v1/objects/{k1}/links")
    contract_recorder.record("list_links_masked_200", r_viewer.request, r_viewer)
    assert r_viewer.status_code == 200, r_viewer.text
    data = r_viewer.json()

    # Outbound far endpoint (target) must be masked strictly
    assert len(data["outbound"]) == 1
    masked_target = data["outbound"][0]["target"]
    assert set(masked_target.keys()) == {"restricted", "label"}
    assert masked_target["restricted"] is True
    assert masked_target["label"] == "🔒 Restricted Object"

    # Inbound far endpoint (source) must be masked strictly
    assert len(data["inbound"]) == 1
    masked_source = data["inbound"][0]["source"]
    assert set(masked_source.keys()) == {"restricted", "label"}
    assert masked_source["restricted"] is True
    assert masked_source["label"] == "🔒 Restricted Object"


async def test_case_3_anti_enumeration_on_target(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: Targeting SEC-9 and SEC-99999 return identical 422 TARGET_NOT_FOUND."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer", workspace_role="WORKSPACE_GUEST")

    kan_proj_id = await make_project("KAN", created_by=admin)
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        viewer.id,
        role="MEMBER",
        scope_type="project",
        project_id=kan_proj_id,
    )
    await make_project("SEC", created_by=admin)
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    admin_client = as_principal(admin)
    k1 = await _create_test_issue(admin_client, "KAN", "Public Issue 1")
    s9 = await _create_test_issue(admin_client, "SEC", "Secret Issue 9")

    # Viewer attempts to target existing unreadable SEC-9
    viewer_client = as_principal(viewer)
    resp_unreadable = await viewer_client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": s9, "link_type": "BLOCKS"},
    )
    contract_recorder.record("target_not_found_422", resp_unreadable.request, resp_unreadable)
    assert resp_unreadable.status_code == 422, resp_unreadable.text
    b_unreadable = resp_unreadable.json()
    assert b_unreadable["code"] == "TARGET_NOT_FOUND"

    # Viewer attempts to target absent SEC-99999
    resp_absent = await viewer_client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": "SEC-99999", "link_type": "BLOCKS"},
    )
    assert resp_absent.status_code == 422, resp_absent.text
    b_absent = resp_absent.json()
    assert b_absent["code"] == "TARGET_NOT_FOUND"

    # Verify identical problem document bodies (modulo request_id)
    assert _strip(b_unreadable) == _strip(b_absent)


async def test_case_4_matrix_user_creatable_self_link_duplicate(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 4: Disallowed matrix tuple 422, system kind 422, self-link 422, duplicate 409."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("KAN", created_by=admin)
    client = as_principal(admin)

    k1 = await _create_test_issue(client, "KAN", "Issue 1")
    k2 = await _create_test_issue(client, "KAN", "Issue 2")

    # 1. System kind -> 422 LINK_TYPE_NOT_USER_CREATABLE
    r_sys = await client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k2, "link_type": "PROMOTED_TO_DOC"},
    )
    assert r_sys.status_code == 422, r_sys.text
    assert r_sys.json()["code"] == "LINK_TYPE_NOT_USER_CREATABLE"

    # 2. Disallowed matrix tuple: issue BLOCKS project -> 422 LINK_TYPE_NOT_ALLOWED
    r_dis = await client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": "KAN", "link_type": "BLOCKS"},
    )
    contract_recorder.record("link_type_not_allowed_422", r_dis.request, r_dis)
    assert r_dis.status_code == 422, r_dis.text
    assert r_dis.json()["code"] == "LINK_TYPE_NOT_ALLOWED"

    # 3. Self-link -> 422 SELF_LINK
    r_self = await client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k1, "link_type": "BLOCKS"},
    )
    assert r_self.status_code == 422, r_self.text
    assert r_self.json()["code"] == "SELF_LINK"

    # 4. Duplicate link -> 409 LINK_EXISTS
    r_ok = await client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k2, "link_type": "RELATES_TO"},
    )
    assert r_ok.status_code == 201, r_ok.text

    r_dup = await client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k2, "link_type": "RELATES_TO"},
    )
    contract_recorder.record("link_exists_409", r_dup.request, r_dup)
    assert r_dup.status_code == 409, r_dup.text
    assert r_dup.json()["code"] == "LINK_EXISTS"

    # 5. Unknown link kind -> 422 LINK_TYPE_NOT_ALLOWED
    r_unk = await client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k2, "link_type": "TOTALLY_UNKNOWN"},
    )
    assert r_unk.status_code == 422, r_unk.text
    assert r_unk.json()["code"] == "LINK_TYPE_NOT_ALLOWED"


async def test_case_5_canonical_url_host_header_immunity(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 5: Canonical URL starts with configured public_base_url and ignores Host header."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("KAN", created_by=admin)
    client = as_principal(admin)

    k1 = await _create_test_issue(client, "KAN", "Canonical URL Issue")

    custom_settings = Settings(
        deployment_mode="production",
        public_base_url="https://kb.test",
    )
    api_env.client._transport.app.state.settings = custom_settings  # type: ignore[attr-defined] # noqa: SLF001

    resp = await client.get(
        f"/api/v1/objects/{k1}/canonical-url",
        headers={"Host": "evil.test"},
    )
    contract_recorder.record("canonical_url_200", resp.request, resp)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["url"].startswith("https://kb.test")
    assert data["url"] == f"https://kb.test/projects/KAN/issues/{k1}"
    assert data["markdown"] == f"[{k1}](https://kb.test/projects/KAN/issues/{k1})"
    assert "evil.test" not in data["url"]
    assert "evil.test" not in data["markdown"]


async def test_case_6_boundaries_flagged_invalid_and_permissions_and_delete(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 6: FLAGGED_INVALID exposed, VIEW-only 403 on POST, ref > 64 404, and DELETE endpoint."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer", workspace_role="WORKSPACE_GUEST")

    await make_project("KAN", created_by=admin, roles={viewer: "VIEWER"})

    admin_client = as_principal(admin)
    k1 = await _create_test_issue(admin_client, "KAN", "Issue 1")
    k2 = await _create_test_issue(admin_client, "KAN", "Issue 2")

    # 1. Admin creates link
    resp = await admin_client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k2, "link_type": "BLOCKS"},
    )
    assert resp.status_code == 201, resp.text
    flagged_link_id = resp.json()["id"]

    # Manually update link_state to FLAGGED_INVALID
    await api_env.seed.execute(
        text("UPDATE object_links SET link_state = 'FLAGGED_INVALID' WHERE id = :id"),
        {"id": uuid.UUID(flagged_link_id)},
    )
    await api_env.seed.commit()

    # GET links: verify FLAGGED_INVALID appears
    r_list = await admin_client.get(f"/api/v1/objects/{k1}/links")
    assert r_list.status_code == 200
    assert r_list.json()["outbound"][0]["link_state"] == "FLAGGED_INVALID"

    # Direct delete of FLAGGED_INVALID link -> 422
    r_del_flagged = await admin_client.delete(f"/api/v1/links/{flagged_link_id}")
    assert r_del_flagged.status_code == 422
    assert r_del_flagged.json()["code"] == "FLAGGED_LINK_REQUIRES_AUDITED_PURGE"

    # Create a separate active link to test DELETE endpoint
    k3 = await _create_test_issue(admin_client, "KAN", "Issue 3")
    resp_active = await admin_client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k3, "link_type": "RELATES_TO"},
    )
    assert resp_active.status_code == 201, resp_active.text
    active_link_id = resp_active.json()["id"]

    # 2. VIEW-only user attempts to POST link -> 403 INSUFFICIENT_CAPABILITY
    viewer_client = as_principal(viewer)
    r_perm = await viewer_client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k2, "link_type": "BLOCKS"},
    )
    assert r_perm.status_code == 403, r_perm.text
    assert r_perm.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 3. Ref longer than 64 characters -> 404
    long_ref = "A" * 65
    assert (await admin_client.get(f"/api/v1/objects/{long_ref}/links")).status_code == 404
    assert (await admin_client.get(f"/api/v1/objects/{long_ref}/canonical-url")).status_code == 404
    assert (
        await admin_client.post(
            f"/api/v1/objects/{long_ref}/links",
            json={"target": k2, "link_type": "BLOCKS"},
        )
    ).status_code == 404

    # 4. DELETE endpoint tests
    assert (await admin_client.delete(f"/api/v1/links/{uuid.uuid4()}")).status_code == 404

    # Viewer without LINK capability attempts delete -> 403
    r_del_viewer = await viewer_client.delete(f"/api/v1/links/{active_link_id}")
    assert r_del_viewer.status_code == 403, r_del_viewer.text
    assert r_del_viewer.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # Admin successfully deletes active link -> 204
    admin_client = as_principal(admin)
    r_del_admin = await admin_client.delete(f"/api/v1/links/{active_link_id}")
    contract_recorder.record("delete_link_204", r_del_admin.request, r_del_admin)
    assert r_del_admin.status_code == 204

    # Assert link no longer in DB
    link_count = await _count(
        api_env,
        "SELECT count(*) FROM object_links WHERE id = :id",
        id=uuid.UUID(active_link_id),
    )
    assert link_count == 0

    # Assert LINK_DELETED activity rows written
    deleted_activity_count = await _count(
        api_env,
        "SELECT count(*) FROM activity_records WHERE event_type = 'LINK_DELETED'",
    )
    assert deleted_activity_count == 2


async def test_canonical_url_various_object_kinds(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test canonical URL generation across projects, docs, stickies, and brackets."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("CORE", created_by=admin)
    client = as_principal(admin)

    # 1. Project canonical URL
    r_proj = await client.get("/api/v1/objects/CORE/canonical-url")
    assert r_proj.status_code == 200
    assert r_proj.json()["url"] == "https://kanban.example/projects/CORE"
    assert r_proj.json()["markdown"] == "[CORE](https://kanban.example/projects/CORE)"

    # 2. Doc object with brackets in title/key
    doc_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="doc",
        key="[ARCH](1)",
        title="Architecture [Spec]",
        project_id=proj_id,
        created_by_id=admin.id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    r_doc = await client.get(f"/api/v1/objects/{doc_id}/canonical-url")
    assert r_doc.status_code == 200
    doc_data = r_doc.json()
    assert "\\[ARCH\\]\\(1\\)" in doc_data["markdown"]


async def test_links_truncation_service_coverage(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test max_links truncation branch in list_object_links."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("TRUNC", created_by=admin)
    client = as_principal(admin)

    k1 = await _create_test_issue(client, "TRUNC", "Issue 1")
    k2 = await _create_test_issue(client, "TRUNC", "Issue 2")

    await client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k2, "link_type": "BLOCKS"},
    )

    k1_obj = (
        await api_env.seed.execute(select(ObjectRecord).where(ObjectRecord.canonical_key == k1))
    ).scalar_one()

    caller = api_env.resolver.principal
    assert caller is not None

    res_out = await list_object_links(api_env.seed, caller, k1_obj, max_links=0)
    assert res_out.truncated is True
    assert len(res_out.outbound) == 0

    k2_obj = (
        await api_env.seed.execute(select(ObjectRecord).where(ObjectRecord.canonical_key == k2))
    ).scalar_one()

    res_in = await list_object_links(api_env.seed, caller, k2_obj, max_links=0)
    assert res_in.truncated is True
    assert len(res_in.inbound) == 0


async def test_links_token_scope_restrictions_and_capabilities(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test endpoints when caller has no token scopes (Capability.NONE)."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("SCOPE", created_by=admin)
    client = as_principal(admin)

    k1 = await _create_test_issue(client, "SCOPE", "Issue 1")
    k2 = await _create_test_issue(client, "SCOPE", "Issue 2")

    r_link = await client.post(
        f"/api/v1/objects/{k1}/links",
        json={"target": k2, "link_type": "BLOCKS"},
    )
    link_id = r_link.json()["id"]

    no_scope_client = as_principal(admin, scopes=())

    assert (await no_scope_client.get(f"/api/v1/objects/{k1}/links")).status_code == 404
    assert (await no_scope_client.get(f"/api/v1/objects/{k1}/canonical-url")).status_code == 404
    assert (
        await no_scope_client.post(
            f"/api/v1/objects/{k1}/links",
            json={"target": k2, "link_type": "BLOCKS"},
        )
    ).status_code == 404
    assert (await no_scope_client.delete(f"/api/v1/links/{link_id}")).status_code == 404


async def test_create_link_integrity_error_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test IntegrityError branches in create_object_link."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("ERR", created_by=admin)
    client = as_principal(admin)

    k1 = await _create_test_issue(client, "ERR", "Issue 1")
    k2 = await _create_test_issue(client, "ERR", "Issue 2")

    caller = api_env.resolver.principal
    assert caller is not None

    req = LinkCreateRequest(target=k2, link_type="BLOCKS")

    # 1 and 2: Expected mapped IntegrityErrors
    for orig_msg, expected_code in [
        ("LINK_TYPE_NOT_ALLOWED", "LINK_TYPE_NOT_ALLOWED"),
        ("23505 unique_violation", "LINK_EXISTS"),
    ]:
        src_obj = await resolve_object_ref(api_env.seed, k1)
        assert src_obj is not None
        with patch.object(
            api_env.seed,
            "flush",
            AsyncMock(side_effect=IntegrityError("stmt", "params", orig=Exception(orig_msg))),
        ):
            with pytest.raises(ProblemException) as exc_info:
                await create_object_link(api_env.seed, caller, src_obj, req)
            assert exc_info.value.code == expected_code
        await api_env.seed.rollback()

    # 3. Unexpected IntegrityError
    src_obj = await resolve_object_ref(api_env.seed, k1)
    assert src_obj is not None
    with (
        patch.object(
            api_env.seed,
            "flush",
            AsyncMock(side_effect=IntegrityError("stmt", "params", orig=Exception("other error"))),
        ),
        pytest.raises(IntegrityError),
    ):
        await create_object_link(api_env.seed, caller, src_obj, req)
    await api_env.seed.rollback()


async def test_build_canonical_url_direct_service_coverage() -> None:
    """Direct unit tests for build_canonical_url with diverse kinds."""
    settings = Settings(deployment_mode="production", public_base_url="https://kb.test")
    ws_id = uuid.uuid4()
    u_id = uuid.uuid4()

    sticky_obj = ObjectRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        object_type=ObjectKind.STICKY,
        canonical_key="stk-abc123",
        display_title="Quick Sticky",
        created_by_id=u_id,
    )
    res_stk = build_canonical_url(settings, sticky_obj)
    assert res_stk.url == "https://kb.test/stickies/stk-abc123"

    cycle_obj = ObjectRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        object_type=ObjectKind.CYCLE,
        canonical_key="cyc-1",
        display_title="Sprint 1",
        created_by_id=u_id,
    )
    res_cyc = build_canonical_url(settings, cycle_obj)
    assert res_cyc.url == "https://kb.test/cycles/cyc-1"

    doc_obj = ObjectRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        object_type=ObjectKind.DOC,
        project_id=None,
        canonical_key="spec-root",
        display_title="Root Spec",
        created_by_id=u_id,
    )
    res_doc = build_canonical_url(settings, doc_obj)
    assert res_doc.url == "https://kb.test/docs/spec-root"

    view_obj = ObjectRecord(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        object_type=ObjectKind.VIEW,
        canonical_key="view-triage",
        display_title="Triage View",
        created_by_id=u_id,
    )
    res_view = build_canonical_url(settings, view_obj)
    assert res_view.url == "https://kb.test/views/view-triage"
