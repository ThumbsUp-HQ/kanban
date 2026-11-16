# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for project repo-bindings REST API (KB-P5-19b, S14.3, S3.4)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from kanban.api.v1.repo_bindings import RepoBindingCreateRequest, _get_kek
from kanban.repos.mirror import FakeGitCommandRunner, GitResult, MirrorManager, MirrorPolicy

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


@pytest.fixture
def fake_mirror_manager(tmp_path: Path) -> MirrorManager:
    """Provide a MirrorManager wired to a FakeGitCommandRunner."""
    runner = FakeGitCommandRunner(
        responses=[
            GitResult(0, "cloned", ""),
            GitResult(0, "0123456789abcdef0123456789abcdef01234567\n", ""),
            GitResult(0, "fetched", ""),
            GitResult(0, "abcdef0123456789abcdef0123456789abcdef01\n", ""),
            GitResult(0, "cloned", ""),
            GitResult(0, "0123456789abcdef0123456789abcdef01234567\n", ""),
        ]
    )
    return MirrorManager(
        base_dir=tmp_path / "git-mirrors",
        policy=MirrorPolicy(allow_file_protocol=False),
        runner=runner,
    )


async def test_create_repo_binding_admin_aal2_success(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    fake_mirror_manager: MirrorManager,
) -> None:
    """Workspace admin with AAL2 creates repo binding; credentials omitted from output."""
    admin = await make_user("repo_admin", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("REP", created_by=admin)

    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    app.state.mirror_manager = fake_mirror_manager
    app.state.git_dns_resolver = lambda _h: ["140.82.121.3"]
    app.state.git_dns_resolver = lambda _h: ["140.82.121.3"]
    app.state.allowed_git_cidrs = ["10.0.0.0/8"]

    client = as_principal(admin, aal_level=2)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/repo-bindings",
        json={
            "slug": "main-mirror",
            "remote_url": "https://github.com/octocat/Hello-World.git",
            "default_ref": "main",
            "access_mode": "bare_git_tools",
            "credential": "deploy-token-secret-xyz",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["slug"] == "main-mirror"
    assert data["remote_url"] == "https://github.com/octocat/Hello-World.git"
    assert data["default_ref"] == "main"
    assert data["access_mode"] == "bare_git_tools"
    assert data["last_fetched_commit"] == "0123456789abcdef0123456789abcdef01234567"
    assert "credential_ciphertext" not in data
    assert "credential" not in data
    assert "credential_dek_kid" not in data
    assert "Location" in resp.headers

    # List endpoint returns the created binding
    list_resp = await client.get(f"/api/v1/projects/{project_id}/repo-bindings")
    assert list_resp.status_code == 200
    bindings = list_resp.json()
    assert len(bindings) == 1
    assert bindings[0]["id"] == data["id"]
    assert "credential_ciphertext" not in bindings[0]


@pytest.mark.usefixtures("api_env")
async def test_member_gets_404_anti_enumeration(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Non-admin member receives 404 Not Found on all repo-binding operations (S3.4)."""
    admin = await make_user("admin_user", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("regular_member")
    project_id = await make_project("PRJ", created_by=admin, roles={member: "MEMBER"})

    client = as_principal(member, aal_level=1)
    get_resp = await client.get(f"/api/v1/projects/{project_id}/repo-bindings")
    assert get_resp.status_code == 404

    post_resp = await client.post(
        f"/api/v1/projects/{project_id}/repo-bindings",
        json={
            "slug": "leak-attempt",
            "remote_url": "https://github.com/octocat/Hello-World.git",
            "access_mode": "bare_git_tools",
        },
    )
    assert post_resp.status_code == 404


@pytest.mark.usefixtures("api_env")
async def test_aal1_admin_rejected_with_403_aal2_required(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Admin with only AAL1 session receives 403 AAL2_REQUIRED on mutating actions."""
    admin = await make_user("aal1_admin", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("AAL", created_by=admin)

    client = as_principal(admin, aal_level=1)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/repo-bindings",
        json={
            "slug": "aal1-fail",
            "remote_url": "https://github.com/octocat/Hello-World.git",
            "access_mode": "bare_git_tools",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "AAL2_REQUIRED"


@pytest.mark.usefixtures("api_env")
async def test_rejected_malicious_refs_and_urls(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Directory traversal refs and disallowed URLs are rejected with 422."""
    admin = await make_user("sec_admin", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("SEC", created_by=admin)
    client = as_principal(admin, aal_level=2)

    # Malicious ref with traversal
    r1 = await client.post(
        f"/api/v1/projects/{project_id}/repo-bindings",
        json={
            "slug": "bad-ref-1",
            "remote_url": "https://github.com/octocat/Hello-World.git",
            "default_ref": "../../../etc/passwd",
            "access_mode": "bare_git_tools",
        },
    )
    assert r1.status_code == 422

    # Malicious ref with command injection attempt
    r2 = await client.post(
        f"/api/v1/projects/{project_id}/repo-bindings",
        json={
            "slug": "bad-ref-2",
            "remote_url": "https://github.com/octocat/Hello-World.git",
            "default_ref": "main; rm -rf /",
            "access_mode": "bare_git_tools",
        },
    )
    assert r2.status_code == 422

    # Disallowed file:// scheme
    r3 = await client.post(
        f"/api/v1/projects/{project_id}/repo-bindings",
        json={
            "slug": "bad-url-file",
            "remote_url": "file:///etc/passwd",
            "default_ref": "main",
            "access_mode": "bare_git_tools",
        },
    )
    assert r3.status_code == 422
    assert r3.json()["code"] == "REPO_URL_REJECTED"


async def test_refresh_and_delete_repo_binding(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    fake_mirror_manager: MirrorManager,
) -> None:
    """Refresh triggers mirror sync; delete succeeds when not in use."""
    admin = await make_user("del_admin", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("DEL", created_by=admin)

    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    app.state.mirror_manager = fake_mirror_manager
    app.state.git_dns_resolver = lambda _h: ["140.82.121.3"]

    client = as_principal(admin, aal_level=2)

    # Create
    create_resp = await client.post(
        f"/api/v1/projects/{project_id}/repo-bindings",
        json={
            "slug": "to-delete",
            "remote_url": "https://github.com/octocat/Hello-World.git",
            "access_mode": "ro_vfs_mount",
        },
    )
    assert create_resp.status_code == 201
    binding_id = create_resp.json()["id"]

    # Refresh
    refresh_resp = await client.post(f"/api/v1/repo-bindings/{binding_id}/refresh")
    assert refresh_resp.status_code == 200

    # Delete
    del_resp = await client.delete(f"/api/v1/repo-bindings/{binding_id}")
    assert del_resp.status_code == 204

    # Verify deleted
    list_resp = await client.get(f"/api/v1/projects/{project_id}/repo-bindings")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0


async def test_delete_returns_409_when_in_use_by_hook(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    fake_mirror_manager: MirrorManager,
) -> None:
    """Delete returns 409 REPO_BINDING_IN_USE when active workflow hook requires repo access."""
    admin = await make_user("hook_admin", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("HOK", created_by=admin)

    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    app.state.mirror_manager = fake_mirror_manager
    app.state.git_dns_resolver = lambda _h: ["140.82.121.3"]

    client = as_principal(admin, aal_level=2)
    create_resp = await client.post(
        f"/api/v1/projects/{project_id}/repo-bindings",
        json={
            "slug": "in-use-binding",
            "remote_url": "https://github.com/octocat/Hello-World.git",
            "access_mode": "ro_vfs_mount",
        },
    )
    assert create_resp.status_code == 201
    binding_id = create_resp.json()["id"]

    # Create dummy workflow_transition_hooks table if it doesn't exist
    await api_env.seed.execute(
        text(
            "CREATE TABLE IF NOT EXISTS workflow_transition_hooks ("
            "  id UUID PRIMARY KEY DEFAULT uuidv7(),"
            "  project_id UUID NOT NULL,"
            "  agent_definition_id UUID NOT NULL,"
            "  is_enabled BOOLEAN NOT NULL DEFAULT TRUE"
            ")"
        )
    )
    await api_env.seed.execute(text("GRANT ALL ON workflow_transition_hooks TO kanban_app"))
    agent_id = uuid.uuid4()
    # Insert valid agent definition with repo_access_mode != 'none'
    await api_env.seed.execute(
        text(
            "INSERT INTO agent_definitions ("
            "  id, workspace_id, principal_id, slug, display_name, "
            "  harness_kind, provider_kind, model_id, repo_access_mode"
            ") VALUES ("
            "  :id, :ws, :pid, 'test-agent', 'Test Agent', "
            "  'in_app_sdk', 'openai', 'gpt-4o', 'ro_vfs_mount'"
            ")"
        ),
        {"id": agent_id, "ws": admin.workspace_id, "pid": admin.id},
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO workflow_transition_hooks (project_id, agent_definition_id, is_enabled) "
            "VALUES (:pid, :aid, TRUE)"
        ),
        {"pid": project_id, "aid": agent_id},
    )
    await api_env.seed.commit()

    del_resp = await client.delete(f"/api/v1/repo-bindings/{binding_id}")
    assert del_resp.status_code == 409
    assert del_resp.json()["code"] == "REPO_BINDING_IN_USE"


async def test_duplicate_slug_rejected_with_409(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    fake_mirror_manager: MirrorManager,
) -> None:
    """Duplicate slug within same project returns 409 SLUG_ALREADY_EXISTS."""
    admin = await make_user("slug_admin", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("SLUG", created_by=admin)

    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    app.state.mirror_manager = fake_mirror_manager
    app.state.git_dns_resolver = lambda _h: ["140.82.121.3"]

    client = as_principal(admin, aal_level=2)
    payload = {
        "slug": "same-slug",
        "remote_url": "https://github.com/octocat/Hello-World.git",
        "access_mode": "ro_vfs_mount",
    }
    r1 = await client.post(f"/api/v1/projects/{project_id}/repo-bindings", json=payload)
    assert r1.status_code == 201

    r2 = await client.post(f"/api/v1/projects/{project_id}/repo-bindings", json=payload)
    assert r2.status_code == 409
    assert r2.json()["code"] == "SLUG_ALREADY_EXISTS"


@pytest.mark.usefixtures("api_env")
async def test_nonexistent_binding_operations_return_404(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Refresh or delete on unknown UUID returns 404."""
    admin = await make_user("nf_admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin, aal_level=2)
    fake_id = uuid.uuid4()

    r_refresh = await client.post(f"/api/v1/repo-bindings/{fake_id}/refresh")
    assert r_refresh.status_code == 404

    r_del = await client.delete(f"/api/v1/repo-bindings/{fake_id}")
    assert r_del.status_code == 404


async def test_mirror_failure_handled_gracefully(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
) -> None:
    """When git mirror manager raises RuntimeError, API still records record and logs warning."""
    admin = await make_user("fail_admin", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("FAIL", created_by=admin)

    class FailingRunner:
        async def run(self, *_args: object, **_kwargs: object) -> GitResult:
            msg = "Mirror download failed abruptly"
            raise RuntimeError(msg)

    failing_mgr = MirrorManager(
        base_dir=tmp_path / "mirrors",
        policy=MirrorPolicy(allow_file_protocol=False),
        runner=FailingRunner(),
    )

    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    app.state.mirror_manager = failing_mgr
    app.state.git_dns_resolver = lambda _h: ["140.82.121.3"]

    client = as_principal(admin, aal_level=2)
    r = await client.post(
        f"/api/v1/projects/{project_id}/repo-bindings",
        json={
            "slug": "failing-mirror",
            "remote_url": "https://github.com/octocat/Hello-World.git",
            "access_mode": "bare_git_tools",
        },
    )
    assert r.status_code == 201
    binding_id = r.json()["id"]

    # Also test refresh with failure
    r_ref = await client.post(f"/api/v1/repo-bindings/{binding_id}/refresh")
    assert r_ref.status_code == 200


async def test_refresh_or_delete_by_non_admin_returns_404(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    fake_mirror_manager: MirrorManager,
) -> None:
    """Non-admin user receives 404 for refresh and delete on existing binding."""
    admin = await make_user("proj_adm", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("proj_mem")
    project_id = await make_project("NOADM", created_by=admin)

    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    app.state.mirror_manager = fake_mirror_manager
    app.state.git_dns_resolver = lambda _h: ["140.82.121.3"]

    admin_client = as_principal(admin, aal_level=2)
    r = await admin_client.post(
        f"/api/v1/projects/{project_id}/repo-bindings",
        json={
            "slug": "perm-test",
            "remote_url": "https://github.com/octocat/Hello-World.git",
            "access_mode": "bare_git_tools",
        },
    )
    assert r.status_code == 201
    binding_id = r.json()["id"]

    member_client = as_principal(member, aal_level=2)

    # Member tries refresh -> 404
    r_ref = await member_client.post(f"/api/v1/repo-bindings/{binding_id}/refresh")
    assert r_ref.status_code == 404

    # Member tries delete -> 404
    r_del = await member_client.delete(f"/api/v1/repo-bindings/{binding_id}")
    assert r_del.status_code == 404


def test_schema_validators_and_get_kek() -> None:
    """Test RepoBindingCreateRequest validation and _get_kek key_material branch."""
    with pytest.raises(ValueError, match="Invalid slug"):
        RepoBindingCreateRequest(
            slug="-invalid-start",
            remote_url="https://github.com/org/repo.git",
            access_mode="ro_vfs_mount",
        )

    with pytest.raises(ValueError, match="Invalid default_ref"):
        RepoBindingCreateRequest(
            slug="valid-slug",
            remote_url="https://github.com/org/repo.git",
            access_mode="ro_vfs_mount",
            default_ref="feature/../evil",
        )

    req = MagicMock()
    req.app.state.kek_provider = None
    req.app.state.key_material.master_kek_kid = "kek-km-1"
    req.app.state.key_material.master_kek = b"m" * 32
    kek = _get_kek(req)
    assert kek is not None
