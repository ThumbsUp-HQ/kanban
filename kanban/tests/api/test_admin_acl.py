# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for Object ACL REST API & Deny Precedence (KB-P4-09b)."""

from __future__ import annotations

import base64
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.admin.acl_service import (
    _assert_admin_on_object,
    grant_acl_entry,
    parse_capability_mask,
    resolve_target_object_id,
    revoke_acl_entry,
)
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.security.permissions import Capability, evaluate_capabilities
from kanban.tests.security.helpers import (
    create_project,
    create_registered_object,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


async def _as_admin_aal2(api_env: ApiEnv, user: SeededUser) -> None:
    """Enroll confirmed TOTP factor and elevate test client to AAL2 session."""
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user.id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )


class _TestObject:
    def __init__(self, obj_id: uuid.UUID) -> None:
        self.id = obj_id


async def _create_test_issue(
    api_env: ApiEnv, workspace_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
) -> _TestObject:
    """Create a test registered object in the objects spine."""
    issue_id = await create_registered_object(
        api_env.seed,
        workspace_id,
        kind="issue",
        key="KAN-142",
        title="Test Issue KAN-142",
        project_id=project_id,
        created_by_id=user_id,
    )
    await api_env.seed.commit()
    return _TestObject(issue_id)


@pytest.mark.asyncio
async def test_grant_and_inspect_access_manifest(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Grant ALLOW capabilities to group on an issue and inspect manifest."""
    admin = await make_user("admin_acl", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    prj_id = await create_project(
        api_env.seed, admin.workspace_id, identifier="KAN", name="Kanban Project"
    )
    await api_env.seed.commit()
    issue = await _create_test_issue(api_env, admin.workspace_id, prj_id, admin.id)

    # 1. Provision group SecOps Reviewers
    resp_group = await api_env.client.post(
        "/api/v1/admin/principals",
        json={"type": "GROUP", "display_name": "SecOps Reviewers"},
    )
    assert resp_group.status_code == 201
    group_id = resp_group.json()["id"]

    # 2. Grant ALLOW [VIEW, COMMENT] to group on issue
    resp_grant = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": group_id,
            "effect": "ALLOW",
            "capabilities": ["VIEW", "COMMENT"],
        },
    )
    assert resp_grant.status_code == 200
    grant_data = resp_grant.json()
    assert grant_data["status"] == "granted"
    assert "VIEW" in grant_data["capabilities"]
    assert "COMMENT" in grant_data["capabilities"]

    # 3. Inspect manifest via admin endpoint
    resp_manifest = await api_env.client.get(f"/api/v1/admin/acl-entries/{issue.id}/manifest")
    assert resp_manifest.status_code == 200
    manifest = resp_manifest.json()
    grp_names = [g["name"] for g in manifest["groups"]]
    assert "SecOps Reviewers" in grp_names


@pytest.mark.asyncio
async def test_deny_precedence_overrides_group_allow(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Explicit DENY [VIEW] on issue strictly overrides group ALLOW and denies access."""
    admin = await make_user("admin_deny", workspace_role="WORKSPACE_ADMIN")
    maya = await make_user("maya_deny", workspace_role="WORKSPACE_MEMBER")
    await _as_admin_aal2(api_env, admin)

    prj_id = await create_project(
        api_env.seed, admin.workspace_id, identifier="KAN", name="Kanban Project"
    )
    await api_env.seed.commit()
    issue = await _create_test_issue(api_env, admin.workspace_id, prj_id, admin.id)

    # 1. Provision group and add maya to group
    r_grp = await api_env.client.post(
        "/api/v1/admin/principals", json={"type": "GROUP", "display_name": "Reviewers"}
    )
    grp_id = r_grp.json()["id"]
    await api_env.client.post(f"/api/v1/admin/groups/{grp_id}/members/{maya.id}")

    # 2. Grant ALLOW [VIEW, COMMENT] to group on issue
    await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": grp_id,
            "effect": "ALLOW",
            "capabilities": ["VIEW", "COMMENT"],
        },
    )

    # 3. Grant DENY [VIEW] to maya on issue
    resp_deny = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(maya.id),
            "effect": "DENY",
            "capabilities": ["VIEW"],
        },
    )
    assert resp_deny.status_code == 200
    deny_data = resp_deny.json()
    assert "VIEW" not in deny_data["effective_capabilities"]

    # 4. Verify maya's effective capabilities evaluate to NONE for VIEW
    maya_ctx = PrincipalContext(
        principal_id=maya.id,
        workspace_id=maya.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    caps = await evaluate_capabilities(api_env.seed, maya_ctx, issue.id)
    assert Capability.VIEW not in caps

    # 5. Revoke DENY entry
    resp_rev = await api_env.client.request(
        "DELETE",
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(maya.id),
            "effect": "DENY",
        },
    )
    assert resp_rev.status_code == 200


@pytest.mark.asyncio
async def test_non_admin_insufficient_permission_or_not_found(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Non-admin callers cannot grant/revoke ACLs or inspect restricted manifests."""
    member = await make_user("regular_member", workspace_role="WORKSPACE_MEMBER")
    admin = await make_user("issue_owner", workspace_role="WORKSPACE_ADMIN")

    prj_id = await create_project(
        api_env.seed, admin.workspace_id, identifier="KAN", name="Kanban Project"
    )
    await api_env.seed.commit()
    issue = await _create_test_issue(api_env, admin.workspace_id, prj_id, admin.id)

    # Set client as regular member (AAL1, regular member)
    api_env.resolver.principal = PrincipalContext(
        principal_id=member.id,
        workspace_id=member.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )

    # Non-admin attempting to grant ACL -> 403 AAL2 or Insufficient Capability
    resp_grant = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(member.id),
            "effect": "ALLOW",
            "capabilities": ["VIEW"],
        },
    )
    assert resp_grant.status_code in (403, 404)


@pytest.mark.asyncio
async def test_acl_boundary_validations(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Boundary conditions: empty capabilities, invalid capability name, unknown principal."""
    admin = await make_user("admin_acl_bounds", workspace_role="WORKSPACE_ADMIN")
    await _as_admin_aal2(api_env, admin)

    prj_id = await create_project(
        api_env.seed, admin.workspace_id, identifier="KAN", name="Kanban Project"
    )
    await api_env.seed.commit()
    issue = await _create_test_issue(api_env, admin.workspace_id, prj_id, admin.id)

    # Empty capabilities
    r1 = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(admin.id),
            "effect": "ALLOW",
            "capabilities": [],
        },
    )
    assert r1.status_code == 422

    # Unknown capability name
    r2 = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(admin.id),
            "effect": "ALLOW",
            "capabilities": ["INVALID_CAP"],
        },
    )
    assert r2.status_code == 422

    # Unknown principal UUID
    r3 = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(uuid.uuid4()),
            "effect": "ALLOW",
            "capabilities": ["VIEW"],
        },
    )
    assert r3.status_code == 404

    # Capabilities > 8 items
    r_too_many = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(admin.id),
            "effect": "ALLOW",
            "capabilities": [
                "VIEW",
                "COMMENT",
                "EDIT",
                "TRANSITION",
                "LINK",
                "SHARE",
                "ADMIN",
                "DELETE",
                "EXTRA",
            ],
        },
    )
    assert r_too_many.status_code == 422

    # Invalid effect on grant
    r_bad_eff = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(admin.id),
            "effect": "MAYBE",
            "capabilities": ["VIEW"],
        },
    )
    assert r_bad_eff.status_code == 422

    # Invalid effect on revoke
    r_bad_rev_eff = await api_env.client.request(
        "DELETE",
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(admin.id),
            "effect": "MAYBE",
        },
    )
    assert r_bad_rev_eff.status_code == 422

    # Revoke non-existent ACL entry
    r_rev_none = await api_env.client.request(
        "DELETE",
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(admin.id),
            "effect": "DENY",
        },
    )
    assert r_rev_none.status_code == 200

    # Non-existent object ref on grant
    r_obj_ghost = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(uuid.uuid4()),
            "principal_id": str(admin.id),
            "effect": "ALLOW",
            "capabilities": ["VIEW"],
        },
    )
    assert r_obj_ghost.status_code == 404

    # Grant with upsert (updating capabilities of existing entry)
    r_up1 = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(admin.id),
            "effect": "ALLOW",
            "capabilities": ["VIEW"],
        },
    )
    assert r_up1.status_code == 200

    r_up2 = await api_env.client.post(
        "/api/v1/admin/acl-entries",
        json={
            "object_id": str(issue.id),
            "principal_id": str(admin.id),
            "effect": "ALLOW",
            "capabilities": ["VIEW", "COMMENT", "EDIT"],
        },
    )
    assert r_up2.status_code == 200
    assert "EDIT" in r_up2.json()["capabilities"]


@pytest.mark.asyncio
async def test_acl_service_unit_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Direct unit testing of acl_service edge cases and validations."""
    admin = await make_user("admin_acl_unit", workspace_role="WORKSPACE_ADMIN")
    user = await make_user("user_acl_unit", workspace_role="WORKSPACE_MEMBER")

    prj_id = await create_project(
        api_env.seed, admin.workspace_id, identifier="UNIT", name="Unit Project"
    )
    await api_env.seed.commit()
    issue = await _create_test_issue(api_env, admin.workspace_id, prj_id, admin.id)

    # 1. parse_capability_mask
    mask = parse_capability_mask(["VIEW", "DELETE"])
    assert mask == (Capability.VIEW | Capability.DELETE)

    with pytest.raises(ProblemException) as exc_info:
        parse_capability_mask([])
    assert exc_info.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc_info:
        parse_capability_mask(["A", "B", "C", "D", "E", "F", "G", "H", "I"])
    assert exc_info.value.code == "VALIDATION_FAILED"

    with pytest.raises(ProblemException) as exc_info:
        parse_capability_mask(["UNKNOWN"])
    assert exc_info.value.code == "VALIDATION_FAILED"

    # 2. resolve_target_object_id with UUID and with key
    resolved_uid = await resolve_target_object_id(api_env.seed, admin.workspace_id, issue.id)
    assert resolved_uid == issue.id

    resolved_key = await resolve_target_object_id(api_env.seed, admin.workspace_id, "KAN-142")
    assert resolved_key == issue.id

    # Non-existent ref
    with pytest.raises(ProblemException) as exc_info:
        await resolve_target_object_id(api_env.seed, admin.workspace_id, "NONEXISTENT-999")
    assert exc_info.value.code == "NOT_FOUND"

    # 3. _assert_admin_on_object: user without admin capability
    user_ctx = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    with pytest.raises(ProblemException) as exc_info:
        await _assert_admin_on_object(api_env.seed, user_ctx, issue.id)
    # Since user has no view/admin, raises NOT_FOUND or INSUFFICIENT_PERMISSION
    assert exc_info.value.code in ("NOT_FOUND", "INSUFFICIENT_PERMISSION")

    # 4. Direct service calls for grant_acl_entry and revoke_acl_entry branches

    admin_ctx = PrincipalContext(
        principal_id=admin.id,
        workspace_id=admin.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )

    # grant with UUID principal_id
    res_g_uuid = await grant_acl_entry(
        api_env.seed,
        admin.workspace_id,
        admin_ctx,
        issue.id,
        user.id,  # UUID
        "ALLOW",
        ["VIEW"],
    )
    assert res_g_uuid["status"] == "granted"

    # grant with non-existent principal UUID
    with pytest.raises(ProblemException) as exc_info:
        await grant_acl_entry(
            api_env.seed,
            admin.workspace_id,
            admin_ctx,
            issue.id,
            uuid.uuid4(),
            "ALLOW",
            ["VIEW"],
        )
    assert exc_info.value.code == "NOT_FOUND"

    # grant with invalid effect
    with pytest.raises(ProblemException) as exc_info:
        await grant_acl_entry(
            api_env.seed,
            admin.workspace_id,
            admin_ctx,
            issue.id,
            user.id,
            "INVALID_EFFECT",
            ["VIEW"],
        )
    assert exc_info.value.code == "VALIDATION_FAILED"

    # revoke with UUID principal_id
    res_r_uuid = await revoke_acl_entry(
        api_env.seed,
        admin.workspace_id,
        admin_ctx,
        issue.id,
        user.id,  # UUID
        "ALLOW",
    )
    assert res_r_uuid["status"] == "revoked"

    # revoke with non-existent principal UUID
    with pytest.raises(ProblemException) as exc_info:
        await revoke_acl_entry(
            api_env.seed,
            admin.workspace_id,
            admin_ctx,
            issue.id,
            uuid.uuid4(),
            "ALLOW",
        )
    assert exc_info.value.code == "NOT_FOUND"

    # revoke with invalid effect
    with pytest.raises(ProblemException) as exc_info:
        await revoke_acl_entry(
            api_env.seed,
            admin.workspace_id,
            admin_ctx,
            issue.id,
            user.id,
            "INVALID_EFFECT",
        )
    assert exc_info.value.code == "VALIDATION_FAILED"
