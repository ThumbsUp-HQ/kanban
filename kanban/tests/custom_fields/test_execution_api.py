# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for custom field execution REST API (KB-P5-13, S13.1, S13.3)."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext
from kanban.custom_fields.manifest import compute_field_manifest_sha256

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db

WASM_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "wasm"


def _read_fixture(filename: str) -> bytes:
    p = WASM_DIR / filename
    return p.read_bytes()


def _as_admin_aal2(api_env: ApiEnv, user: SeededUser) -> httpx.AsyncClient:
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )
    return api_env.client


def _as_user_aal1(api_env: ApiEnv, user: SeededUser) -> httpx.AsyncClient:
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    return api_env.client


async def test_upload_wasm_module_lifecycle_and_security(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """Validate upload, structural linting, AAL2 and role gating for Wasm modules."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member")
    _ = await make_project(
        "WASM", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"}
    )

    echo_bytes = _read_fixture("echo_cvss.wasm")
    echo_b64 = base64.b64encode(echo_bytes).decode("ascii")

    # 1. Non-admin user gets 403
    client_member = _as_user_aal1(api_env, member)
    resp_member = await client_member.post(
        "/api/v1/projects/WASM/wasm-modules",
        json={"name": "echo_cvss", "wasm_base64": echo_b64},
    )
    assert resp_member.status_code == 403
    assert resp_member.json()["code"] in (
        "PROJECT_ADMIN_REQUIRED",
        "AAL2_REQUIRED",
        "INSUFFICIENT_CAPABILITY",
    )

    # 2. Admin with AAL1 gets 403 AAL2_REQUIRED
    client_admin_aal1 = _as_user_aal1(api_env, admin)
    resp_aal1 = await client_admin_aal1.post(
        "/api/v1/projects/WASM/wasm-modules",
        json={"name": "echo_cvss", "wasm_base64": echo_b64},
    )
    assert resp_aal1.status_code == 403
    assert resp_aal1.json()["code"] == "AAL2_REQUIRED"

    client_admin = _as_admin_aal2(api_env, admin)

    # 3. Nonexistent project gets 404
    resp_no_proj = await client_admin.post(
        "/api/v1/projects/NONEXIST/wasm-modules",
        json={"name": "echo_cvss", "wasm_base64": echo_b64},
    )
    assert resp_no_proj.status_code == 404

    # 4. Invalid base64 gets 422 WASM_BINARY_INVALID
    resp_bad_b64 = await client_admin.post(
        "/api/v1/projects/WASM/wasm-modules",
        json={"name": "bad", "wasm_base64": "!!!not_valid_base64!!!"},
    )
    assert resp_bad_b64.status_code == 422
    assert resp_bad_b64.json()["code"] == "WASM_BINARY_INVALID"

    # 5. Invalid wasm binary (not WebAssembly magic header) gets 422
    resp_corrupt = await client_admin.post(
        "/api/v1/projects/WASM/wasm-modules",
        json={
            "name": "corrupt",
            "wasm_base64": base64.b64encode(b"not a wasm module").decode("ascii"),
        },
    )
    assert resp_corrupt.status_code == 422
    assert resp_corrupt.json()["code"] == "WASM_BINARY_INVALID"

    # 6. Forbidden WASI/host import gets 422 WASM_FORBIDDEN_IMPORT
    wasi_bytes = _read_fixture("wasi_fs_import.wasm")
    resp_wasi = await client_admin.post(
        "/api/v1/projects/WASM/wasm-modules",
        json={"name": "wasi", "wasm_base64": base64.b64encode(wasi_bytes).decode("ascii")},
    )
    assert resp_wasi.status_code == 422
    assert resp_wasi.json()["code"] == "WASM_FORBIDDEN_IMPORT"

    # 7. Valid module upload succeeds with 201 Created
    resp_ok = await client_admin.post(
        "/api/v1/projects/WASM/wasm-modules",
        json={"name": "echo_cvss", "wasm_base64": echo_b64},
    )
    contract_recorder.record("upload_wasm_module_201", resp_ok.request, resp_ok)
    assert resp_ok.status_code == 201, resp_ok.text
    data = resp_ok.json()
    assert len(data["sha256"]) == 64
    assert data["name"] == "echo_cvss"
    assert data["size_bytes"] == len(echo_bytes)

    # 8. Re-uploading existing module returns 201 idempotently
    resp_idempotent = await client_admin.post(
        "/api/v1/projects/WASM/wasm-modules",
        json={"name": "echo_cvss", "wasm_base64": echo_b64},
    )
    assert resp_idempotent.status_code == 201
    assert resp_idempotent.json()["sha256"] == data["sha256"]


async def test_custom_field_execution_and_cache_flow(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test full execution flow: create issue, upload wasm, define field, GET and POST execute."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("EXEC", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)

    # 1. Create an issue EXEC-1
    resp_issue = await client.post(
        "/api/v1/projects/EXEC/issues",
        json={"summary": "Execution Test Issue", "description_markdown": "Test Description"},
    )
    assert resp_issue.status_code == 201, resp_issue.text
    issue_data = resp_issue.json()
    issue_key = issue_data["key"]

    # 2. Upload echo_cvss wasm module
    echo_bytes = _read_fixture("echo_cvss.wasm")
    resp_wasm = await client.post(
        "/api/v1/projects/EXEC/wasm-modules",
        json={"name": "echo_cvss", "wasm_base64": base64.b64encode(echo_bytes).decode("ascii")},
    )
    assert resp_wasm.status_code == 201
    wasm_sha256 = resp_wasm.json()["sha256"]

    # 3. Create custom field definition linked to the wasm module
    resp_field = await client.post(
        "/api/v1/projects/EXEC/custom-fields",
        json={
            "slug": "cvss-score",
            "name": "CVSS Score",
            "tier": "wasm",
            "output_format": "severity_pill",
            "output_format_metadata": {},
            "script_source": "wasm:echo_cvss",
            "wasm_module_sha256": wasm_sha256,
        },
    )
    assert resp_field.status_code == 201, resp_field.text
    field_id = resp_field.json()["id"]

    # 4. GET /api/v1/issues/{issue_key}/custom-fields computes value on read
    resp_get = await client.get(f"/api/v1/issues/{issue_key}/custom-fields")
    contract_recorder.record("list_custom_fields_for_issue_200", resp_get.request, resp_get)
    assert resp_get.status_code == 200, resp_get.text
    items = resp_get.json()
    assert len(items) == 1
    item = items[0]
    assert item["status"] == "computed", f"Unexpected status: {item}"
    assert item["field_id"] == field_id
    assert item["slug"] == "cvss-score"
    assert item["name"] == "CVSS Score"
    assert item["tier"] == "wasm"
    assert item["output_format"] == "severity_pill"
    assert item["value"] == {"level": "high", "score": 8.8, "label": "8.8 High"}
    assert item["last_latency_ms"] >= 0

    # 5. Subsequent GET returns same computed value
    resp_get_cached = await client.get(f"/api/v1/issues/{issue_key}/custom-fields")
    assert resp_get_cached.status_code == 200
    items_cached = resp_get_cached.json()
    assert len(items_cached) == 1
    assert items_cached[0]["value"] == {"level": "high", "score": 8.8, "label": "8.8 High"}

    # 6. POST execute forces fresh execution
    resp_exec = await client.post(f"/api/v1/issues/{issue_key}/custom-fields/{field_id}/execute")
    contract_recorder.record("execute_custom_field_200", resp_exec.request, resp_exec)
    assert resp_exec.status_code == 200, resp_exec.text
    item_exec = resp_exec.json()
    assert item_exec["field_id"] == field_id
    assert item_exec["value"] == {"level": "high", "score": 8.8, "label": "8.8 High"}

    # 7. 404 on missing issue
    resp_missing_issue = await client.post(
        f"/api/v1/issues/EXEC-999/custom-fields/{field_id}/execute"
    )
    assert resp_missing_issue.status_code == 404

    # 8. 404 on missing field
    resp_missing_field = await client.post(
        f"/api/v1/issues/{issue_key}/custom-fields/{uuid.uuid4()}/execute"
    )
    assert resp_missing_field.status_code == 404


async def test_custom_field_execution_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Test fuel exhaustion, revoked escalation approval, and tier B in standalone mode."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("EDGE", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)

    # Create issue
    resp_issue = await client.post(
        "/api/v1/projects/EDGE/issues",
        json={"summary": "Edge Test Issue", "description_markdown": "Edge case"},
    )
    assert resp_issue.status_code == 201
    issue_key = resp_issue.json()["key"]

    # 1. Fuel exhaustion trap handling
    loop_bytes = _read_fixture("infinite_loop.wasm")
    resp_loop_wasm = await client.post(
        "/api/v1/projects/EDGE/wasm-modules",
        json={"name": "infinite_loop", "wasm_base64": base64.b64encode(loop_bytes).decode("ascii")},
    )
    assert resp_loop_wasm.status_code == 201
    loop_sha = resp_loop_wasm.json()["sha256"]

    resp_loop_field = await client.post(
        "/api/v1/projects/EDGE/custom-fields",
        json={
            "slug": "infinite-loop-field",
            "name": "Infinite Loop",
            "tier": "wasm",
            "output_format": "text",
            "script_source": "wasm:infinite_loop",
            "wasm_module_sha256": loop_sha,
        },
    )
    assert resp_loop_field.status_code == 201
    loop_field_id = resp_loop_field.json()["id"]

    # 1. Fuel exhaustion trap handling
    resp_loop_list = await client.get(f"/api/v1/issues/{issue_key}/custom-fields")
    assert resp_loop_list.status_code == 200
    loop_item = next(it for it in resp_loop_list.json() if it["field_id"] == loop_field_id)
    assert loop_item["status"] == "SCRIPT_FUEL_EXHAUSTED"
    assert loop_item["value"] is None

    resp_exec_loop = await client.post(
        f"/api/v1/issues/{issue_key}/custom-fields/{loop_field_id}/execute"
    )
    assert resp_exec_loop.status_code == 422
    assert resp_exec_loop.json()["code"] == "SCRIPT_FUEL_EXHAUSTED"

    # 2. Tier B (nsjail) raises 503 SANDBOX_UNAVAILABLE_IN_STANDALONE
    # Insert a tier B field directly in DB (or via API if supported)
    # Tier B definition:
    tier_b_id = uuid.uuid4()
    manifest_b = compute_field_manifest_sha256(
        script_source="echo test",
        output_format="text",
        output_format_metadata={},
        tier="nsjail",
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
    )
    proj_row = await api_env.seed.execute(text("SELECT id FROM projects WHERE identifier = 'EDGE'"))
    proj_id = proj_row.scalar_one()

    await api_env.seed.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "id, workspace_id, project_id, name, slug, tier, output_format, "
            "output_format_metadata, script_source, manifest_sha256, target_scope, "
            "credential_mode, created_by_id"
            ") VALUES ("
            ":id, :ws, :proj, 'Tier B Field', 'tier-b-field', 'nsjail', 'text', "
            "'{}'::jsonb, 'echo test', :man, 'PROJECT', 'INVOKING_USER', :uid"
            ")"
        ),
        {
            "id": tier_b_id,
            "ws": api_env.workspace_id,
            "proj": proj_id,
            "man": manifest_b,
            "uid": admin.id,
        },
    )
    await api_env.seed.commit()

    resp_tier_b = await client.post(f"/api/v1/issues/{issue_key}/custom-fields/{tier_b_id}/execute")
    assert resp_tier_b.status_code == 503
    assert resp_tier_b.json()["code"] == "SANDBOX_UNAVAILABLE_IN_STANDALONE"

    # 3. Unapproved escalation raises 409 APPROVAL_REVOKED
    escalated_id = uuid.uuid4()
    manifest_esc = compute_field_manifest_sha256(
        script_source="echo escalated",
        output_format="text",
        output_format_metadata={},
        tier="wasm",
        target_scope="SERVER",
        credential_mode="SERVER_ADMIN_SP",
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "id, workspace_id, project_id, name, slug, tier, output_format, "
            "output_format_metadata, script_source, manifest_sha256, target_scope, "
            "credential_mode, created_by_id"
            ") VALUES ("
            ":id, :ws, :proj, 'Escalated Field', 'escalated-field', 'wasm', 'text', "
            "'{}'::jsonb, 'echo escalated', :man, 'SERVER', 'SERVER_ADMIN_SP', :uid"
            ")"
        ),
        {
            "id": escalated_id,
            "ws": api_env.workspace_id,
            "proj": proj_id,
            "man": manifest_esc,
            "uid": admin.id,
        },
    )
    await api_env.seed.commit()

    resp_esc = await client.post(f"/api/v1/issues/{issue_key}/custom-fields/{escalated_id}/execute")
    assert resp_esc.status_code == 409
    assert resp_esc.json()["code"] == "APPROVAL_REVOKED"
