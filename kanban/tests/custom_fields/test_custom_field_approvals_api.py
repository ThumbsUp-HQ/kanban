# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API tests for Custom Field escalation approvals (KB-P5-12, S13.2, S4.2, S3.2)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from database.models.custom_field import CustomFieldDefinition
from kanban.api.deps import PrincipalContext
from kanban.custom_fields.approvals import ApprovalRevokedError, assert_execution_authorized
from kanban.tests.security.helpers import add_role_binding

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


def _as_admin_aal2(
    api_env: ApiEnv,
    user: SeededUser,
    *,
    aal2_verified_at: datetime | None = None,
    set_timestamp: bool = True,
) -> httpx.AsyncClient:
    """Configure active principal context with AAL2 and optional freshness timestamp."""
    v_time = aal2_verified_at if (aal2_verified_at or not set_timestamp) else datetime.now(UTC)
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
        aal2_verified_at=v_time,
    )
    return api_env.client


def _as_user_aal1(api_env: ApiEnv, user: SeededUser) -> httpx.AsyncClient:
    """Configure active principal context with AAL1."""
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    return api_env.client


def _record_sample(
    samples: dict[str, Any],
    name: str,
    resp: httpx.Response,
) -> None:
    """Record contract sample for verification proof bundle."""
    req_body = None
    if resp.request.content:
        try:
            req_body = json.loads(resp.request.content.decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            req_body = resp.request.content.decode("utf-8", errors="replace")

    res_body = None
    if resp.content:
        try:
            res_body = resp.json()
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            res_body = resp.text

    samples[name] = {
        "request": {
            "method": resp.request.method,
            "url": str(resp.request.url),
            "headers": dict(resp.request.headers),
            "body": req_body,
        },
        "response": {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "body": res_body,
        },
    }


def _append_samples_to_disk(samples: dict[str, Any]) -> None:
    """Write contract samples to docs/qa/KANBA-114/contract-sample.json."""
    sample_file = Path("/tmp/kb-wt-KANBA-114/docs/qa/KANBA-114/contract-sample.json")
    sample_file.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if sample_file.exists():
        try:
            existing = json.loads(sample_file.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError):
            existing = {}
    existing.update(samples)
    sample_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")


async def test_01_request_approval_lifecycle_and_boundaries(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test approval request creation, validation errors, and baseline passthrough."""
    captured_samples: dict[str, Any] = {}
    admin = await make_user("adm1", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("mem1")
    _ = await make_project(
        "APR", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"}
    )

    # 1. Create baseline field (PROJECT, INVOKING_USER)
    client = _as_admin_aal2(api_env, admin)
    resp_base = await client.post(
        "/api/v1/projects/APR/custom-fields",
        json={
            "slug": "baseline-field",
            "name": "Baseline Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"format": "text", "max_length": 50},
            "script_source": "export default () => 'ok';",
            "target_scope": "PROJECT",
            "credential_mode": "INVOKING_USER",
        },
    )
    assert resp_base.status_code == 201
    base_id = resp_base.json()["id"]
    base_manifest = resp_base.json()["manifest_sha256"]

    # Requesting approval for baseline returns 422 NO_ESCALATION_REQUIRED
    resp_no_esc = await client.post(
        f"/api/v1/custom-fields/{base_id}/approval-requests",
        json={"manifest_sha256": base_manifest, "justification": "This should not be needed."},
    )
    assert resp_no_esc.status_code == 422
    assert resp_no_esc.json()["code"] == "NO_ESCALATION_REQUIRED"

    # 2. Create escalated field (PROJECT, PROJECT_ADMIN_SP)
    resp_esc = await client.post(
        "/api/v1/projects/APR/custom-fields",
        json={
            "slug": "sp-field",
            "name": "SP Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"format": "text", "max_length": 50},
            "script_source": "export default () => 'sp';",
            "target_scope": "PROJECT",
            "credential_mode": "PROJECT_ADMIN_SP",
        },
    )
    assert resp_esc.status_code == 201
    esc_id = resp_esc.json()["id"]
    esc_manifest = resp_esc.json()["manifest_sha256"]
    assert resp_esc.json()["approval_status"] == "UNAPPROVED"
    assert resp_esc.json()["required_approver_tier"] == "PROJECT_ADMIN"

    # AAL1 caller gets 403 AAL2_REQUIRED
    _as_user_aal1(api_env, admin)
    resp_aal1 = await api_env.client.post(
        f"/api/v1/custom-fields/{esc_id}/approval-requests",
        json={"manifest_sha256": esc_manifest, "justification": "Valid justification text"},
    )
    assert resp_aal1.status_code == 403
    assert resp_aal1.json()["code"] == "AAL2_REQUIRED"

    # Member caller gets 403 INSUFFICIENT_CAPABILITY
    _as_admin_aal2(api_env, member)
    resp_mem = await api_env.client.post(
        f"/api/v1/custom-fields/{esc_id}/approval-requests",
        json={"manifest_sha256": esc_manifest, "justification": "Member requesting"},
    )
    assert resp_mem.status_code == 403
    assert resp_mem.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # Hash mismatch gets 409 MANIFEST_MISMATCH (as admin)
    _as_admin_aal2(api_env, admin)
    resp_mismatch = await api_env.client.post(
        f"/api/v1/custom-fields/{esc_id}/approval-requests",
        json={"manifest_sha256": "00" * 32, "justification": "Valid justification text"},
    )
    assert resp_mismatch.status_code == 409
    assert resp_mismatch.json()["code"] == "MANIFEST_MISMATCH"

    # Valid request gets 201
    resp_req = await api_env.client.post(
        f"/api/v1/custom-fields/{esc_id}/approval-requests",
        json={
            "manifest_sha256": esc_manifest,
            "justification": "Requires elevated Project Admin privileges to compute metric.",
        },
    )
    assert resp_req.status_code == 201
    req_json = resp_req.json()
    assert req_json["status"] == "PENDING"
    assert req_json["required_tier"] == "PROJECT_ADMIN"
    assert req_json["manifest_sha256"] == esc_manifest
    contract_recorder.record("create_approval_request_201", resp_req.request, resp_req)
    _record_sample(captured_samples, "create_approval_request_201", resp_req)
    _append_samples_to_disk(captured_samples)


async def test_02_project_admin_sp_approval(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """(PROJECT, PROJECT_ADMIN_SP) approval requires sp_warning_acknowledged=True."""
    admin = await make_user("adm2", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("PSP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)

    resp_create = await client.post(
        "/api/v1/projects/PSP/custom-fields",
        json={
            "slug": "sp-metric",
            "name": "SP Metric",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"format": "text", "max_length": 50},
            "script_source": "export default () => 'val';",
            "target_scope": "PROJECT",
            "credential_mode": "PROJECT_ADMIN_SP",
        },
    )
    assert resp_create.status_code == 201
    fid = resp_create.json()["id"]
    m_sha = resp_create.json()["manifest_sha256"]

    resp_req = await client.post(
        f"/api/v1/custom-fields/{fid}/approval-requests",
        json={"manifest_sha256": m_sha, "justification": "Valid justification text"},
    )
    assert resp_req.status_code == 201
    appr_id = resp_req.json()["id"]

    # Reject if sp_warning_acknowledged is False
    resp_no_warn = await client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": False},
    )
    assert resp_no_warn.status_code == 422
    assert resp_no_warn.json()["code"] == "SP_WARNING_ACK_REQUIRED"

    # Approve with sp_warning_acknowledged=True
    resp_appr = await client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_appr.status_code == 200
    appr_json = resp_appr.json()
    assert appr_json["status"] == "APPROVED"
    assert appr_json["sp_warning_acknowledged"] is True
    assert appr_json["primary_approver_id"] == str(admin.id)
    contract_recorder.record("approve_project_admin_sp_200", resp_appr.request, resp_appr)


async def test_03_workspace_admin_approval_and_tier_enforcement(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """Workspace admin tier enforcement."""
    p_admin = await make_user("padm")
    w_admin = await make_user("wadm", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project(
        "WSP",
        created_by=p_admin,
        roles={p_admin: "PROJECT_ADMIN", w_admin: "PROJECT_ADMIN"},
    )

    client = _as_admin_aal2(api_env, p_admin)
    resp_create = await client.post(
        "/api/v1/projects/WSP/custom-fields",
        json={
            "slug": "ws-field",
            "name": "WS Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"format": "text", "max_length": 50},
            "script_source": "export default () => 'ws';",
            "target_scope": "WORKSPACE",
            "credential_mode": "INVOKING_USER",
        },
    )
    assert resp_create.status_code == 201
    fid = resp_create.json()["id"]
    m_sha = resp_create.json()["manifest_sha256"]

    resp_req = await client.post(
        f"/api/v1/custom-fields/{fid}/approval-requests",
        json={
            "manifest_sha256": m_sha,
            "justification": "Requires workspace scope for cross-project views.",
        },
    )
    assert resp_req.status_code == 201
    appr_id = resp_req.json()["id"]

    # PROJECT_ADMIN cannot approve WORKSPACE_ADMIN tier
    resp_p_denied = await client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha},
    )
    assert resp_p_denied.status_code == 403
    assert resp_p_denied.json()["code"] == "INSUFFICIENT_APPROVER_TIER"

    # WORKSPACE_ADMIN approves successfully
    _as_admin_aal2(api_env, w_admin)
    resp_w_appr = await api_env.client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha},
    )
    assert resp_w_appr.status_code == 200
    assert resp_w_appr.json()["status"] == "APPROVED"
    contract_recorder.record("approve_workspace_admin_200", resp_w_appr.request, resp_w_appr)


async def test_04_server_admin_dual_control_and_self_approval_block(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """(SERVER, SERVER_ADMIN_SP) enforces dual distinct SERVER_ADMIN approvals."""
    captured_samples: dict[str, Any] = {}
    p_admin = await make_user("padm4")
    sa1 = await make_user("sa1")
    sa2 = await make_user("sa2")
    _ = await make_project(
        "SRV",
        created_by=p_admin,
        roles={p_admin: "PROJECT_ADMIN", sa1: "PROJECT_ADMIN", sa2: "PROJECT_ADMIN"},
    )

    # Bind SERVER_ADMIN roles on server scope
    await add_role_binding(
        api_env.seed, api_env.workspace_id, sa1.id, role="SERVER_ADMIN", scope_type="server"
    )
    await add_role_binding(
        api_env.seed, api_env.workspace_id, sa2.id, role="SERVER_ADMIN", scope_type="server"
    )
    await api_env.seed.commit()

    client = _as_admin_aal2(api_env, p_admin)
    resp_create = await client.post(
        "/api/v1/projects/SRV/custom-fields",
        json={
            "slug": "server-field",
            "name": "Server Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"format": "text", "max_length": 50},
            "script_source": "export default () => 'srv';",
            "target_scope": "SERVER",
            "credential_mode": "SERVER_ADMIN_SP",
        },
    )
    assert resp_create.status_code == 201
    fid = resp_create.json()["id"]
    m_sha = resp_create.json()["manifest_sha256"]

    resp_req = await client.post(
        f"/api/v1/custom-fields/{fid}/approval-requests",
        json={
            "manifest_sha256": m_sha,
            "justification": "Requires server-wide infrastructure inspection.",
        },
    )
    assert resp_req.status_code == 201
    appr_id = resp_req.json()["id"]

    # 1. Primary approval by Server Admin 1 -> PENDING_SECOND_APPROVER
    _as_admin_aal2(api_env, sa1)
    resp_sa1 = await api_env.client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_sa1.status_code == 200
    sa1_json = resp_sa1.json()
    assert sa1_json["status"] == "PENDING_SECOND_APPROVER"
    assert sa1_json["primary_approver_id"] == str(sa1.id)
    assert sa1_json["secondary_approver_id"] is None
    contract_recorder.record("dual_control_primary_approved_200", resp_sa1.request, resp_sa1)
    _record_sample(captured_samples, "dual_control_primary_approved_200", resp_sa1)

    # 2. Self-second-approval by Server Admin 1 is blocked -> 409
    resp_self = await api_env.client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_self.status_code == 409
    assert resp_self.json()["code"] == "DUAL_CONTROL_DISTINCT_APPROVER_REQUIRED"

    # 3. Secondary approval by distinct Server Admin 2 -> APPROVED
    _as_admin_aal2(api_env, sa2)
    resp_sa2 = await api_env.client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_sa2.status_code == 200
    sa2_json = resp_sa2.json()
    assert sa2_json["status"] == "APPROVED"
    assert sa2_json["primary_approver_id"] == str(sa1.id)
    assert sa2_json["secondary_approver_id"] == str(sa2.id)
    contract_recorder.record("dual_control_secondary_approved_200", resp_sa2.request, resp_sa2)
    _record_sample(captured_samples, "dual_control_secondary_approved_200", resp_sa2)

    _append_samples_to_disk(captured_samples)


async def test_05_aal2_freshness_enforcement(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """Approvals require AAL2 and fresh verification (<= 900s)."""
    captured_samples: dict[str, Any] = {}
    admin = await make_user("adm5", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("AAL", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)

    resp_create = await client.post(
        "/api/v1/projects/AAL/custom-fields",
        json={
            "slug": "aal-field",
            "name": "AAL Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"format": "text", "max_length": 50},
            "script_source": "export default () => 'aal';",
            "target_scope": "PROJECT",
            "credential_mode": "PROJECT_ADMIN_SP",
        },
    )
    fid = resp_create.json()["id"]
    m_sha = resp_create.json()["manifest_sha256"]

    resp_req = await client.post(
        f"/api/v1/custom-fields/{fid}/approval-requests",
        json={"manifest_sha256": m_sha, "justification": "Valid justification text"},
    )
    appr_id = resp_req.json()["id"]

    # 1. AAL1 caller -> 403 AAL2_REQUIRED
    _as_user_aal1(api_env, admin)
    resp_aal1 = await api_env.client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_aal1.status_code == 403
    assert resp_aal1.json()["code"] == "AAL2_REQUIRED"
    contract_recorder.record("approve_aal1_denied_403", resp_aal1.request, resp_aal1)
    _record_sample(captured_samples, "403_aal2_required", resp_aal1)

    # 2. AAL2 caller with expired verification (901s ago) -> 403 AAL2_REQUIRED
    expired_time = datetime.now(UTC) - timedelta(seconds=901)
    _as_admin_aal2(api_env, admin, aal2_verified_at=expired_time)
    resp_expired = await api_env.client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_expired.status_code == 403
    assert resp_expired.json()["code"] == "AAL2_REQUIRED"

    _append_samples_to_disk(captured_samples)


async def test_06_toctou_manifest_mismatch_and_single_byte_tamper_auto_revocation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """TOCTOU hash mismatch returns 409; modifying definition immediately revokes approval."""
    captured_samples: dict[str, Any] = {}
    admin = await make_user("adm6", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("TOC", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)

    resp_create = await client.post(
        "/api/v1/projects/TOC/custom-fields",
        json={
            "slug": "tamper-field",
            "name": "Tamper Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"format": "text", "max_length": 50},
            "script_source": "export default () => 42;",
            "target_scope": "PROJECT",
            "credential_mode": "PROJECT_ADMIN_SP",
        },
    )
    fid = resp_create.json()["id"]
    m_sha = resp_create.json()["manifest_sha256"]

    resp_req = await client.post(
        f"/api/v1/custom-fields/{fid}/approval-requests",
        json={"manifest_sha256": m_sha, "justification": "Valid justification text"},
    )
    appr_id = resp_req.json()["id"]

    # 1. TOCTOU: Approve with stale/tampered manifest hash -> 409 MANIFEST_MISMATCH
    resp_stale = await client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": "ff" * 32, "sp_warning_acknowledged": True},
    )
    assert resp_stale.status_code == 409
    assert resp_stale.json()["code"] == "MANIFEST_MISMATCH"
    contract_recorder.record("approve_toctou_manifest_mismatch_409", resp_stale.request, resp_stale)
    _record_sample(captured_samples, "409_manifest_mismatch", resp_stale)

    # 2. Approve cleanly
    resp_appr = await client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_appr.status_code == 200
    assert resp_appr.json()["status"] == "APPROVED"

    # Verify assert_execution_authorized succeeds before tamper
    await api_env.seed.rollback()
    def_row = await api_env.seed.get(CustomFieldDefinition, uuid.UUID(fid))
    assert def_row is not None
    auth_ok = await assert_execution_authorized(api_env.seed, def_row)
    assert auth_ok is not None
    assert auth_ok.status == "APPROVED"

    # 3. Single-byte tamper on script_source: append one space " "
    resp_patch = await client.patch(
        f"/api/v1/projects/TOC/custom-fields/{fid}",
        json={"script_source": "export default () => 42; "},
    )
    assert resp_patch.status_code == 200
    new_manifest = resp_patch.json()["manifest_sha256"]
    assert new_manifest != m_sha

    # 4. Trigger auto-revocation: approval status is now REVOKED
    resp_history = await client.get(f"/api/v1/custom-fields/{fid}/approvals")
    assert resp_history.status_code == 200
    history = resp_history.json()
    assert len(history) >= 1
    revoked_entry = next(item for item in history if item["id"] == appr_id)
    assert revoked_entry["status"] == "REVOKED"
    assert revoked_entry["revoked_reason"] == "MANIFEST_SHA256_CHANGED"
    _record_sample(captured_samples, "post_edit_revoked_state", resp_history)

    # 5. assert_execution_authorized fails closed (raises ApprovalRevokedError)
    await api_env.seed.rollback()
    def_updated = await api_env.seed.get(CustomFieldDefinition, uuid.UUID(fid))
    assert def_updated is not None
    with pytest.raises(ApprovalRevokedError) as exc_info:
        await assert_execution_authorized(api_env.seed, def_updated)
    assert exc_info.value.code == "APPROVAL_REVOKED"

    _append_samples_to_disk(captured_samples)


async def test_07_list_approvals_and_anti_enumeration(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Approval history listing and 404 anti-enumeration."""
    admin = await make_user("adm7", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("LST", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)

    resp_create = await client.post(
        "/api/v1/projects/LST/custom-fields",
        json={
            "slug": "list-field",
            "name": "List Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"format": "text", "max_length": 50},
            "script_source": "export default () => 'list';",
            "target_scope": "PROJECT",
            "credential_mode": "PROJECT_ADMIN_SP",
        },
    )
    fid = resp_create.json()["id"]
    m_sha = resp_create.json()["manifest_sha256"]

    # Initial list is empty
    resp_init = await client.get(f"/api/v1/custom-fields/{fid}/approvals")
    assert resp_init.status_code == 200
    assert resp_init.json() == []

    # Create request
    resp_req = await client.post(
        f"/api/v1/custom-fields/{fid}/approval-requests",
        json={"manifest_sha256": m_sha, "justification": "Valid justification text"},
    )
    assert resp_req.status_code == 201

    # List has 1 item
    resp_after = await client.get(f"/api/v1/custom-fields/{fid}/approvals")
    assert resp_after.status_code == 200
    items = resp_after.json()
    assert len(items) == 1
    assert items[0]["status"] == "PENDING"

    # Non-existent field returns 404
    resp_404 = await client.get(f"/api/v1/custom-fields/{uuid.uuid4()}/approvals")
    assert resp_404.status_code == 404


async def test_08_approval_api_edge_cases_and_coverage(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Cover edge cases: slug lookup, 404s, already resolved approvals, null aal2_verified_at."""
    admin = await make_user("adm8", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("EDG", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)

    # 1. Request approval on non-existent field -> 404
    resp_bad_field = await client.post(
        f"/api/v1/custom-fields/{uuid.uuid4()}/approval-requests",
        json={"manifest_sha256": "00" * 32, "justification": "Valid justification text"},
    )
    assert resp_bad_field.status_code == 404

    # Create field
    resp_create = await client.post(
        "/api/v1/projects/EDG/custom-fields",
        json={
            "slug": "edge-field",
            "name": "Edge Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"format": "text", "max_length": 50},
            "script_source": "export default () => 'edge';",
            "target_scope": "PROJECT",
            "credential_mode": "PROJECT_ADMIN_SP",
        },
    )
    _ = resp_create.json()["id"]
    m_sha = resp_create.json()["manifest_sha256"]

    # 2. Request approval using slug instead of UUID
    resp_slug_req = await client.post(
        "/api/v1/custom-fields/edge-field/approval-requests",
        json={"manifest_sha256": m_sha, "justification": "Valid justification text"},
    )
    assert resp_slug_req.status_code == 201
    appr_id = resp_slug_req.json()["id"]

    # 3. Approve on non-existent approval_id -> 404
    resp_bad_appr = await client.post(
        f"/api/v1/custom-field-approvals/{uuid.uuid4()}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_bad_appr.status_code == 404

    # 4. Caller with aal2_verified_at=None succeeds (fresh AAL2 session without recorded timestamp)
    client_no_time = _as_admin_aal2(api_env, admin, aal2_verified_at=None, set_timestamp=False)
    resp_appr = await client_no_time.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_appr.status_code == 200
    assert resp_appr.json()["status"] == "APPROVED"

    # 5. Attempting to approve an already approved approval -> 409 APPROVAL_ALREADY_RESOLVED
    resp_dup = await client.post(
        f"/api/v1/custom-field-approvals/{appr_id}/approve",
        json={"manifest_sha256": m_sha, "sp_warning_acknowledged": True},
    )
    assert resp_dup.status_code == 409
    assert resp_dup.json()["code"] == "APPROVAL_ALREADY_RESOLVED"
