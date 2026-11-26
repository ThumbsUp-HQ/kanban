"""API tests for agent definitions persistence and durability (KAN-433)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def _enroll_totp_and_set_aal2(api_env: ApiEnv, user: SeededUser) -> None:
    """Enroll and confirm TOTP factor to permit AAL2 evaluation for admin."""
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
        aal_level=2,
    )


async def test_create_agent_definition_persists_custom_system_instructions(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify POST agent definition persists custom system_instructions_md durably."""
    admin = await make_user("agent-admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    custom_instructions = (
        "# Security Audit Agent\n\n"
        "- Assume hostile wire.\n"
        "- Run passive forensic checks.\n"
        "- Require verification packets."
    )
    slug = f"sec-auditor-{uuid.uuid4().hex[:8]}"

    payload = {
        "slug": slug,
        "display_name": "Security Audit Agent",
        "harness_kind": "in_app_sdk",
        "provider_kind": "gemini",
        "model_id": "gemini-2.5-flash",
        "system_instructions_md": custom_instructions,
        "repo_access_mode": "none",
        "mcp_allowed_tools": ["search_tickets", "read_ticket"],
        "timeout_ms": 45000,
    }

    # 1. POST agent definition
    create_resp = await client.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions",
        json=payload,
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    agent_id = created["id"]
    assert created["slug"] == slug
    assert created["display_name"] == "Security Audit Agent"
    assert created["system_instructions_md"] == custom_instructions
    assert create_resp.headers.get("Location") == f"/api/v1/agent-definitions/{agent_id}"

    # 2. GET list from workspace
    list_resp = await client.get(f"/api/v1/workspaces/{api_env.workspace_id}/agent-definitions")
    assert list_resp.status_code == 200, list_resp.text
    agents_list = list_resp.json()
    matching = [a for a in agents_list if a["id"] == agent_id]
    assert len(matching) == 1
    assert matching[0]["system_instructions_md"] == custom_instructions

    # 3. GET detail by UUID
    get_by_id_resp = await client.get(f"/api/v1/agent-definitions/{agent_id}")
    assert get_by_id_resp.status_code == 200, get_by_id_resp.text
    detail_by_id = get_by_id_resp.json()
    assert detail_by_id["system_instructions_md"] == custom_instructions

    # 4. GET detail by slug
    get_by_slug_resp = await client.get(f"/api/v1/agent-definitions/{slug}")
    assert get_by_slug_resp.status_code == 200, get_by_slug_resp.text
    detail_by_slug = get_by_slug_resp.json()
    assert detail_by_slug["system_instructions_md"] == custom_instructions

    # 5. PATCH agent definition with updated custom system instructions
    updated_instructions = (
        "# Security Audit Agent (v2)\n\n"
        "- Updated passive audit directives.\n"
        "- Strict bounds checking enabled."
    )
    patch_resp = await client.patch(
        f"/api/v1/agent-definitions/{agent_id}",
        json={"system_instructions_md": updated_instructions},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    patched = patch_resp.json()
    assert patched["system_instructions_md"] == updated_instructions

    # 6. Verify read durability after commit
    verify_resp = await client.get(f"/api/v1/agent-definitions/{agent_id}")
    assert verify_resp.status_code == 200, verify_resp.text
    assert verify_resp.json()["system_instructions_md"] == updated_instructions

    # 7. DELETE agent definition and verify commit durability
    del_resp = await client.delete(f"/api/v1/agent-definitions/{agent_id}")
    assert del_resp.status_code == 204, del_resp.text

    not_found_resp = await client.get(f"/api/v1/agent-definitions/{agent_id}")
    assert not_found_resp.status_code == 404


async def test_admin_agent_definitions_commit_durability(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify admin_router routes commit changes durably."""
    admin = await make_user("server-admin", workspace_role="SERVER_ADMIN")
    await _enroll_totp_and_set_aal2(api_env, admin)
    client = as_principal(admin, aal_level=2)

    slug = f"admin-cli-agent-{uuid.uuid4().hex[:8]}"
    instructions = "# Admin Managed CLI Agent\n\nRun sandboxed checks."

    payload = {
        "slug": slug,
        "display_name": "Admin CLI Agent",
        "harness_kind": "cli_pipe",
        "cli_binary_allowlist_id": "agy",
        "cli_args": ["-p"],
        "system_instructions_md": instructions,
        "repo_access_mode": "none",
        "timeout_ms": 60000,
    }

    # Admin create
    create_resp = await client.post("/api/v1/admin/agent-definitions", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    agent_id = create_resp.json()["id"]
    assert create_resp.json()["system_instructions_md"] == instructions

    # Admin list
    list_resp = await client.get("/api/v1/admin/agent-definitions")
    assert list_resp.status_code == 200, list_resp.text
    matching = [a for a in list_resp.json() if a["id"] == agent_id]
    assert len(matching) == 1
    assert matching[0]["system_instructions_md"] == instructions

    # Admin get
    get_resp = await client.get(f"/api/v1/admin/agent-definitions/{agent_id}")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["system_instructions_md"] == instructions

    # Admin patch
    new_instructions = "# Admin Managed CLI Agent (Patched)\n\nUpdated rules."
    patch_resp = await client.patch(
        f"/api/v1/admin/agent-definitions/{agent_id}",
        json={"system_instructions_md": new_instructions},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["system_instructions_md"] == new_instructions

    # Admin delete
    del_resp = await client.delete(f"/api/v1/admin/agent-definitions/{agent_id}")
    assert del_resp.status_code == 204, del_resp.text

    get_after_del = await client.get(f"/api/v1/admin/agent-definitions/{agent_id}")
    assert get_after_del.status_code == 404
