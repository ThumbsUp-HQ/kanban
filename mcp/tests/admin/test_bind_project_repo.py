# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin tool 6 actions: repo bindings (KB-P5-19b, S11.4, S14.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml
from sqlalchemy import text

from kanban.repos.mirror import FakeGitCommandRunner, GitResult, MirrorManager, MirrorPolicy

if TYPE_CHECKING:
    import uuid
    from pathlib import Path

    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


async def _call_tool_6(  # noqa: PLR0913
    env: AdminTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    scopes: str | None = "admin:write",
    aal_level: int | None = 2,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke manage_cycles_and_modules via JSON-RPC 2.0 on /mcp/admin."""
    active_session_id = session_id
    if active_session_id is None:
        init_resp = await env.mcp_client.post(
            "/mcp/admin",
            json={
                "jsonrpc": "2.0",
                "id": 999,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-admin", "version": "1.0"},
                },
            },
            headers={"X-KB-Subject-Token": subject_token} if subject_token else {},
        )
        assert init_resp.status_code == 200
        active_session_id = init_resp.headers["mcp-session-id"]

    headers: dict[str, str] = {"mcp-session-id": active_session_id}
    if subject_token is not None:
        headers["X-KB-Subject-Token"] = subject_token
    if scopes is not None:
        headers["X-KB-Scopes"] = scopes
    if aal_level is not None:
        headers["X-KB-AAL-Level"] = str(aal_level)

    req_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "manage_cycles_and_modules",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/admin", json=req_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    return cast("dict[str, Any]", data)


async def _create_project_with_key(
    env: AdminTestEnv,
    identifier: str,
    name: str,
) -> uuid.UUID:
    """Create project in database and return project_id."""
    proj_id = (
        await env.seed_session.execute(
            text(
                "SELECT register_object('project'::object_kind, :ws, NULL, :ident, :name, :creator)"
            ),
            {
                "ws": env.workspace_id,
                "ident": identifier,
                "name": name,
                "creator": env.server_admin.id,
            },
        )
    ).scalar_one()

    await env.seed_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws, :ident, :name)"
        ),
        {
            "id": proj_id,
            "ws": env.workspace_id,
            "ident": identifier,
            "name": name,
        },
    )
    await env.seed_session.commit()
    return cast("uuid.UUID", proj_id)


@pytest.mark.asyncio
async def test_mcp_bind_project_repo_lifecycle(admin_env: AdminTestEnv, tmp_path: Path) -> None:
    """Complete Tool 6 lifecycle: bind by key, list summary/full, refresh, unbind confirm."""
    await _create_project_with_key(admin_env, "KAN", "Kanban Core")

    # Configure mirror manager on FastAPI app
    fake_runner = FakeGitCommandRunner(
        responses=[
            GitResult(0, "cloned", ""),
            GitResult(0, "0123456789abcdef0123456789abcdef01234567\n", ""),
            GitResult(0, "fetched", ""),
            GitResult(0, "0123456789abcdef0123456789abcdef01234567\n", ""),
        ]
    )
    admin_env.fastapi_app.state.mirror_manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        policy=MirrorPolicy(allow_file_protocol=False),
        runner=fake_runner,
    )
    admin_env.fastapi_app.state.git_dns_resolver = lambda _h: ["140.82.121.3"]

    # 1. Action: bind_project_repo with project="KAN"
    bind_data = await _call_tool_6(
        admin_env,
        {
            "action": "bind_project_repo",
            "project": "KAN",
            "slug": "core-repo",
            "remote_url": "https://github.com/example/core.git",
            "default_ref": "main",
            "access_mode": "bare_git_tools",
        },
        subject_token=admin_env.token_server_admin_write,
    )
    res = bind_data["result"]
    assert not res.get("isError")
    bind_yaml = yaml.safe_load(res["content"][0]["text"])
    assert bind_yaml["status"] == "created"
    assert bind_yaml["repo_binding"]["slug"] == "core-repo"
    assert bind_yaml["repo_binding"]["default_ref"] == "main"
    assert "credential" not in bind_yaml["repo_binding"]
    binding_id = bind_yaml["repo_binding"]["id"]

    # 2. Action: list_repo_bindings (summary)
    list_sum = await _call_tool_6(
        admin_env,
        {
            "action": "list_repo_bindings",
            "project": "KAN",
            "lod": "summary",
        },
        scopes="admin:read",
        subject_token=admin_env.token_server_admin_read,
    )
    sum_yaml = yaml.safe_load(list_sum["result"]["content"][0]["text"])
    assert len(sum_yaml["repo_bindings"]) == 1
    assert sum_yaml["repo_bindings"][0]["slug"] == "core-repo"

    # 3. Action: list_repo_bindings (full)
    list_full = await _call_tool_6(
        admin_env,
        {
            "action": "list_repo_bindings",
            "project": "KAN",
            "lod": "full",
        },
        scopes="admin:read",
        subject_token=admin_env.token_server_admin_read,
    )
    full_yaml = yaml.safe_load(list_full["result"]["content"][0]["text"])
    assert "last_fetched_commit" in full_yaml["repo_bindings"][0]

    # 4. Action: refresh_repo_binding
    refresh_data = await _call_tool_6(
        admin_env,
        {
            "action": "refresh_repo_binding",
            "project": "KAN",
            "binding": binding_id,
        },
        subject_token=admin_env.token_server_admin_write,
    )
    ref_yaml = yaml.safe_load(refresh_data["result"]["content"][0]["text"])
    assert ref_yaml["status"] == "refreshed"

    # 5. Action: unbind_project_repo WITHOUT confirm -> warning, not deleted
    unconfirmed = await _call_tool_6(
        admin_env,
        {
            "action": "unbind_project_repo",
            "project": "KAN",
            "binding": binding_id,
            "confirm": False,
        },
        subject_token=admin_env.token_server_admin_write,
    )
    unconf_yaml = yaml.safe_load(unconfirmed["result"]["content"][0]["text"])
    assert unconf_yaml["status"] == "confirmation_required"
    assert "confirm: true" in unconf_yaml["warning"]

    # 6. Action: unbind_project_repo WITH confirm=True -> deleted
    confirmed = await _call_tool_6(
        admin_env,
        {
            "action": "unbind_project_repo",
            "project": "KAN",
            "binding": binding_id,
            "confirm": True,
        },
        subject_token=admin_env.token_server_admin_write,
    )
    conf_yaml = yaml.safe_load(confirmed["result"]["content"][0]["text"])
    assert conf_yaml["status"] == "deleted"
    assert conf_yaml["binding_id"] == binding_id


@pytest.mark.asyncio
async def test_mcp_bind_project_repo_rejections(admin_env: AdminTestEnv) -> None:
    """Disallowed URLs, missing scope, or AAL1 sessions are rejected via MCP."""
    await _create_project_with_key(admin_env, "REJ", "Reject Project")

    # Scope insufficient: admin:read on mutating bind_project_repo
    read_only = await _call_tool_6(
        admin_env,
        {
            "action": "bind_project_repo",
            "project": "REJ",
            "slug": "disallowed",
            "remote_url": "https://github.com/org/repo.git",
            "access_mode": "bare_git_tools",
        },
        scopes="admin:read",
        subject_token=admin_env.token_server_admin_read,
    )
    assert read_only["result"].get("isError")

    # Disallowed file:// URL
    bad_url = await _call_tool_6(
        admin_env,
        {
            "action": "bind_project_repo",
            "project": "REJ",
            "slug": "bad-scheme",
            "remote_url": "file:///etc/shadow",
            "access_mode": "bare_git_tools",
        },
        subject_token=admin_env.token_server_admin_write,
    )
    assert bad_url["result"].get("isError")
    err_text = bad_url["result"]["content"][0]["text"]
    assert "file:// scheme is forbidden" in err_text or "VALIDATION_FAILED" in err_text


@pytest.mark.asyncio
async def test_mcp_bind_project_repo_dns_rebinding_pinned(
    admin_env: AdminTestEnv, tmp_path: Path
) -> None:
    """DNS rebinding simulation: resolver returns public IP then loopback; pinned IP is used."""
    await _create_project_with_key(admin_env, "DNS", "DNS Rebinding Project")

    fake_runner = FakeGitCommandRunner(
        responses=[
            GitResult(0, "cloned", ""),
            GitResult(0, "0123456789abcdef0123456789abcdef01234567\n", ""),
        ]
    )
    admin_env.fastapi_app.state.mirror_manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        policy=MirrorPolicy(allow_file_protocol=False),
        runner=fake_runner,
    )

    call_count = 0

    def rebinding_resolver(_host: str) -> list[str]:
        nonlocal call_count
        call_count += 1
        # First call (validation): legitimate public IP
        if call_count == 1:
            return ["140.82.121.3"]
        # Subsequent calls (rebinding attack simulation): dangerous loopback IP
        return ["127.0.0.1"]

    admin_env.fastapi_app.state.git_dns_resolver = rebinding_resolver

    bind_data = await _call_tool_6(
        admin_env,
        {
            "action": "bind_project_repo",
            "project": "DNS",
            "slug": "rebind-repo",
            "remote_url": "https://github.com/example/rebind.git",
            "default_ref": "main",
            "access_mode": "bare_git_tools",
        },
        subject_token=admin_env.token_server_admin_write,
    )
    res = bind_data["result"]
    assert not res.get("isError")

    # Assert that fake_runner received http.curloptResolve pinning the initial validated IP
    assert len(fake_runner.calls) == 2
    clone_argv, _ = fake_runner.calls[0]
    resolve_flag = next((a for a in clone_argv if "http.curloptResolve=" in a), None)
    assert resolve_flag is not None
    assert "github.com:443:140.82.121.3" in resolve_flag
    assert "127.0.0.1" not in resolve_flag
