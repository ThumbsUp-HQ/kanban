# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for inbound SCM webhooks (KB-DEVSECOPS-BUS-01)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from starlette.requests import Request

from database.models.repo_binding import ProjectRepoBinding
from database.models.spine import ObjectLink
from database.models.webhooks import ScmArtifact
from database.session import RLSContext
from kanban.api.v1.webhooks_scm import _extract_delivery_id, _extract_event_type
from kanban.security.envelope import StaticKekProvider, seal_bound

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _make_kek() -> StaticKekProvider:
    return StaticKekProvider({"kek-v1": b"k" * 32}, current="kek-v1")


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


async def _create_repo_binding_with_secret(  # noqa: PLR0913
    api_env: ApiEnv,
    admin: SeededUser,
    project_id: uuid.UUID,
    *,
    slug: str,
    remote_url: str,
    secret_str: str,
) -> uuid.UUID:
    """Create a project repo binding with an envelope-encrypted webhook secret."""
    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    kek = _make_kek()
    binding_id = uuid.uuid4()
    aad = f"kanban/repo-binding/v1|{binding_id}|{project_id}".encode()
    sealed = seal_bound(secret_str.encode("utf-8"), aad, kek)
    wrapped_len = len(sealed.wrapped_dek).to_bytes(2, "big")
    wrapped_secret = wrapped_len + sealed.wrapped_dek + sealed.encrypted_secret_blob

    binding = ProjectRepoBinding(
        id=binding_id,
        workspace_id=admin.workspace_id,
        project_id=project_id,
        slug=slug,
        remote_url=remote_url,
        default_ref="main",
        access_mode="bare_git_tools",
        wrapped_webhook_secret=wrapped_secret,
        webhook_secret_dek_kid=sealed.dek_kid,
        created_by=admin.id,
    )
    session_factory = app.state.session_factory
    ctx = RLSContext(principal_id=admin.id, workspace_id=admin.workspace_id)
    async with session_factory.session(ctx) as session:
        session.add(binding)
        await session.flush()
    return binding_id


async def test_github_pull_request_autolink_and_deduplication(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """GitHub PR with KAN-<N> issue key in title creates scm_artifact and IMPLEMENTED_IN_PR link."""
    admin = await make_user("admin_scm", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("SCM", created_by=admin)
    client = as_principal(admin, aal_level=2)

    issue_key = await _create_test_issue(client, "SCM", "Implement feature X")
    seq_id = issue_key.split("-")[-1]

    webhook_secret = "secret-token-gh-42"
    binding_id = await _create_repo_binding_with_secret(
        api_env,
        admin,
        project_id,
        slug="gh-repo",
        remote_url="https://github.com/example/my-repo.git",
        secret_str=webhook_secret,
    )

    pr_payload = {
        "action": "opened",
        "number": 101,
        "pull_request": {
            "id": 555001,
            "number": 101,
            "title": f"feat: Add support for SCM-{seq_id} fast pipeline",
            "body": f"Resolves SCM-{seq_id} cleanly.",
            "state": "open",
            "html_url": "https://github.com/example/my-repo/pull/101",
            "head": {
                "ref": f"feat/SCM-{seq_id}",
                "sha": "0123456789abcdef0123456789abcdef01234567",
            },
        },
        "repository": {
            "clone_url": "https://github.com/example/my-repo.git",
            "html_url": "https://github.com/example/my-repo",
        },
    }
    raw_body = json.dumps(pr_payload).encode("utf-8")
    sig = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    anon_client = api_env.client

    # 1. Delivery succeeds and links PR
    delivery_id = "del-gh-1001"
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Delivery": delivery_id,
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": f"sha256={sig}",
    }
    resp = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={binding_id}",
        content=raw_body,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    res_data = resp.json()
    assert res_data["status"] == "ok"
    assert res_data["links_created"] >= 1
    assert issue_key in res_data["issues_linked"]

    # Verify scm_artifact in DB
    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    ctx = RLSContext(principal_id=admin.id, workspace_id=admin.workspace_id)
    async with app.state.session_factory.session(ctx) as session:
        art_res = await session.execute(
            select(ScmArtifact).where(
                ScmArtifact.repo_binding_id == binding_id,
                ScmArtifact.artifact_kind == "pull_request",
            )
        )
        art = art_res.scalar_one()
        assert art.external_id == "555001"
        assert "SCM-" in art.title

        link_res = await session.execute(
            select(ObjectLink).where(
                ObjectLink.target_id == art.object_id,
                ObjectLink.link_type == "IMPLEMENTED_IN_PR",
            )
        )
        link = link_res.scalar_one()
        assert link.source_key_snapshot == issue_key

    # 2. Replay of same delivery_id is deduplicated
    resp_dup = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={binding_id}",
        content=raw_body,
        headers=headers,
    )
    assert resp_dup.status_code == 200
    assert resp_dup.json()["status"] == "duplicate_ignored"


async def test_forgejo_push_commit_autolink(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Forgejo push webhook with commit referencing issue creates link."""
    admin = await make_user("admin_fj", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("FORG", created_by=admin)
    client = as_principal(admin, aal_level=2)

    issue_key = await _create_test_issue(client, "FORG", "Bug in parser")
    seq_id = issue_key.split("-")[-1]

    webhook_secret = "secret-forgejo-99"
    binding_id = await _create_repo_binding_with_secret(
        api_env,
        admin,
        project_id,
        slug="fj-repo",
        remote_url="https://forgejo.example/org/project.git",
        secret_str=webhook_secret,
    )

    commit_sha = "abcdef0123456789abcdef0123456789abcdef01"
    push_payload = {
        "ref": "refs/heads/main",
        "commits": [
            {
                "id": commit_sha,
                "message": f"Fix parser memory leak (FORG-{seq_id})\n\nDetailed commit body.",
                "url": f"https://forgejo.example/org/project/commit/{commit_sha}",
                "author": {"name": "Dev", "email": "dev@example.com"},
            }
        ],
        "repository": {
            "clone_url": "https://forgejo.example/org/project.git",
        },
    }
    raw_body = json.dumps(push_payload).encode("utf-8")
    sig = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    anon_client = api_env.client
    headers = {
        "Content-Type": "application/json",
        "X-Forgejo-Delivery": "fj-del-2002",
        "X-Forgejo-Event": "push",
        "X-Forgejo-Signature": sig,
    }
    resp = await anon_client.post(
        f"/api/v1/webhooks/git/forgejo?binding_id={binding_id}",
        content=raw_body,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    res_data = resp.json()
    assert res_data["status"] == "ok"
    assert issue_key in res_data["issues_linked"]

    # Verify link in database
    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    ctx = RLSContext(principal_id=admin.id, workspace_id=admin.workspace_id)
    async with app.state.session_factory.session(ctx) as session:
        art_res = await session.execute(
            select(ScmArtifact).where(
                ScmArtifact.repo_binding_id == binding_id,
                ScmArtifact.artifact_kind == "commit",
            )
        )
        art = art_res.scalar_one()
        assert art.external_id == commit_sha

        link_res = await session.execute(
            select(ObjectLink).where(
                ObjectLink.target_id == art.object_id,
                ObjectLink.link_type == "REFERENCED_BY_COMMIT",
            )
        )
        link = link_res.scalar_one()
        assert link.source_key_snapshot == issue_key


async def test_webhook_security_rejections(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Forged signatures, oversized payloads, and missing bindings fail closed."""
    admin = await make_user("admin_sec", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("SEC", created_by=admin)

    webhook_secret = "correct-secret"
    binding_id = await _create_repo_binding_with_secret(
        api_env,
        admin,
        project_id,
        slug="sec-repo",
        remote_url="https://github.com/example/sec-repo.git",
        secret_str=webhook_secret,
    )

    anon_client = api_env.client
    payload = json.dumps({"action": "ping"}).encode("utf-8")

    # 1. Invalid signature (401)
    bad_sig_hex = "0" * 64
    bad_headers = {
        "Content-Type": "application/json",
        "X-GitHub-Delivery": "sec-del-1",
        "X-GitHub-Event": "ping",
        "X-Hub-Signature-256": f"sha256={bad_sig_hex}",
    }
    resp = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={binding_id}",
        content=payload,
        headers=bad_headers,
    )
    assert resp.status_code == 401

    # 2. Missing signature when secret configured (401)
    no_sig_headers = {
        "Content-Type": "application/json",
        "X-GitHub-Delivery": "sec-del-2",
        "X-GitHub-Event": "ping",
    }
    resp_no_sig = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={binding_id}",
        content=payload,
        headers=no_sig_headers,
    )
    assert resp_no_sig.status_code == 401

    # 3. Unknown repo binding (404)
    fake_id = uuid.uuid4()
    resp_404 = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={fake_id}",
        content=payload,
        headers=bad_headers,
    )
    assert resp_404.status_code == 404

    # 4. Oversized payload > 1 MiB (413)
    oversized = json.dumps({"action": "ping", "data": "x" * (1_048_576 + 10)}).encode("utf-8")
    resp_413 = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={binding_id}",
        content=oversized,
        headers={"Content-Type": "application/json", "Content-Length": str(len(oversized))},
    )
    assert resp_413.status_code == 413

    # 5. Unsupported provider (400)
    resp_400 = await anon_client.post(
        f"/api/v1/webhooks/git/bitbucket?binding_id={binding_id}",
        content=payload,
        headers=bad_headers,
    )
    assert resp_400.status_code == 400


async def test_gitlab_inbound_webhooks(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """GitLab token auth and MR/push events create scm_artifacts and links."""
    admin = await make_user("admin_gl", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("GLAB", created_by=admin)
    client = as_principal(admin, aal_level=2)

    issue_key = await _create_test_issue(client, "GLAB", "Support GitLab webhooks")
    secret_str = "shared-gitlab-secret"

    gl_binding_id = await _create_repo_binding_with_secret(
        api_env,
        admin,
        project_id,
        slug="gitlab-repo",
        remote_url="https://gitlab.com/team/gl-repo.git",
        secret_str=secret_str,
    )
    anon_client = api_env.client

    # 1. Push event
    gl_push_payload = json.dumps(
        {
            "object_kind": "push",
            "ref": f"refs/heads/feature/{issue_key}",
            "commits": [
                {
                    "id": "abc123commit",
                    "message": f"Fixes {issue_key}: multi-scm webhook support",
                    "url": "https://gitlab.com/team/gl-repo/commit/abc123commit",
                }
            ],
        }
    ).encode("utf-8")

    gl_headers = {
        "Content-Type": "application/json",
        "X-Gitlab-Token": secret_str,
        "X-Gitlab-Event": "Push Hook",
    }
    resp_gl = await anon_client.post(
        f"/api/v1/webhooks/git/gitlab?binding_id={gl_binding_id}",
        content=gl_push_payload,
        headers=gl_headers,
    )
    assert resp_gl.status_code == 200, resp_gl.text
    assert issue_key in resp_gl.json()["issues_linked"]
    assert resp_gl.json()["links_created"] == 2

    # 2. Merge request event
    gl_mr_payload = json.dumps(
        {
            "object_kind": "merge_request",
            "object_attributes": {
                "id": 99,
                "title": f"Resolve {issue_key}",
                "source_branch": f"feature/{issue_key}",
                "target_branch": "main",
                "url": "https://gitlab.com/team/gl-repo/-/merge_requests/99",
            },
        }
    ).encode("utf-8")
    gl_mr_headers = {
        "Content-Type": "application/json",
        "X-Gitlab-Token": secret_str,
        "X-Gitlab-Event": "Merge Request Hook",
    }
    resp_gl_mr = await anon_client.post(
        f"/api/v1/webhooks/git/gitlab?binding_id={gl_binding_id}",
        content=gl_mr_payload,
        headers=gl_mr_headers,
    )
    assert resp_gl_mr.status_code == 200, resp_gl_mr.text

    # 3. Missing and invalid token
    resp_gl_no_tok = await anon_client.post(
        f"/api/v1/webhooks/git/gitlab?binding_id={gl_binding_id}",
        content=gl_push_payload,
        headers={"Content-Type": "application/json", "X-Gitlab-Event": "Push Hook"},
    )
    assert resp_gl_no_tok.status_code == 401

    resp_gl_bad_tok = await anon_client.post(
        f"/api/v1/webhooks/git/gitlab?binding_id={gl_binding_id}",
        content=gl_push_payload,
        headers={
            "Content-Type": "application/json",
            "X-Gitlab-Token": "wrong-token",
            "X-Gitlab-Event": "Push Hook",
        },
    )
    assert resp_gl_bad_tok.status_code == 401


async def test_forgejo_inbound_webhooks(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Forgejo HMAC auth and PR/push events create and update scm_artifacts and links."""
    admin = await make_user("admin_fj", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("FORG", created_by=admin)
    client = as_principal(admin, aal_level=2)

    issue_key = await _create_test_issue(client, "FORG", "Support Forgejo webhooks")
    secret_str = "shared-forgejo-secret"

    fj_binding_id = await _create_repo_binding_with_secret(
        api_env,
        admin,
        project_id,
        slug="forgejo-repo",
        remote_url="https://forgejo.org/team/fj-repo.git",
        secret_str=secret_str,
    )
    anon_client = api_env.client

    # 1. Push hook with HMAC signature
    fj_push_payload = json.dumps(
        {
            "repository": {
                "clone_url": "https://forgejo.org/team/fj-repo.git",
                "html_url": "https://forgejo.org/team/fj-repo",
            },
            "ref": f"refs/heads/topic/{issue_key}",
            "commits": [
                {
                    "id": "def456commit",
                    "message": f"Implement {issue_key}",
                    "url": "https://forgejo.org/team/fj-repo/commit/def456commit",
                }
            ],
        }
    ).encode("utf-8")
    fj_sig = hmac.new(secret_str.encode("utf-8"), fj_push_payload, hashlib.sha256).hexdigest()
    fj_headers = {
        "Content-Type": "application/json",
        "X-Forgejo-Signature": fj_sig,
        "X-Forgejo-Event": "push",
        "X-Forgejo-Delivery": "fj-del-1",
    }
    # Test resolving by repo_url query param
    resp_fj = await anon_client.post(
        "/api/v1/webhooks/git/forgejo?repo_url=https://forgejo.org/team/fj-repo.git",
        content=fj_push_payload,
        headers=fj_headers,
    )
    assert resp_fj.status_code == 200, resp_fj.text
    assert issue_key in resp_fj.json()["issues_linked"]
    assert resp_fj.json()["links_created"] == 2

    # 2. Forgejo pull_request hook
    fj_pr_payload = json.dumps(
        {
            "pull_request": {
                "id": 101,
                "title": f"Closes {issue_key}",
                "html_url": "https://forgejo.org/team/fj-repo/pulls/101",
                "head": {"ref": f"topic/{issue_key}"},
            }
        }
    ).encode("utf-8")
    fj_pr_sig = hmac.new(secret_str.encode("utf-8"), fj_pr_payload, hashlib.sha256).hexdigest()
    resp_fj_pr = await anon_client.post(
        f"/api/v1/webhooks/git/forgejo?binding_id={fj_binding_id}",
        content=fj_pr_payload,
        headers={
            "Content-Type": "application/json",
            "X-Forgejo-Signature": fj_pr_sig,
            "X-Forgejo-Event": "pull_request",
        },
    )
    assert resp_fj_pr.status_code == 200, resp_fj_pr.text

    # 3. Unconfigured webhook secret returns 400
    no_sec_binding = ProjectRepoBinding(
        id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        project_id=project_id,
        slug="no-secret-repo",
        remote_url="https://github.com/team/no-sec.git",
        default_ref="main",
        access_mode="bare_git_tools",
        created_by=admin.id,
    )
    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    ctx = RLSContext(principal_id=admin.id, workspace_id=admin.workspace_id)
    async with app.state.session_factory.session(ctx) as session:
        session.add(no_sec_binding)
        await session.commit()

    resp_no_sec = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={no_sec_binding.id}",
        content=json.dumps({"action": "ping"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert resp_no_sec.status_code == 400
    assert resp_no_sec.json()["code"] == "WEBHOOK_SECRET_NOT_CONFIGURED"

    # 4. Signature errors
    resp_fj_no_sig = await anon_client.post(
        f"/api/v1/webhooks/git/forgejo?binding_id={fj_binding_id}",
        content=fj_push_payload,
        headers={"Content-Type": "application/json", "X-Forgejo-Event": "push"},
    )
    assert resp_fj_no_sig.status_code == 401

    resp_fj_bad_sig = await anon_client.post(
        f"/api/v1/webhooks/git/forgejo?binding_id={fj_binding_id}",
        content=fj_push_payload,
        headers={
            "Content-Type": "application/json",
            "X-Forgejo-Signature": "bad",
            "X-Forgejo-Event": "push",
        },
    )
    assert resp_fj_bad_sig.status_code == 401

    # 5. Invalid JSON body
    resp_bad_json = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={fj_binding_id}",
        content=b"not json",
        headers={"Content-Type": "text/plain"},
    )
    assert resp_bad_json.status_code == 400
    assert resp_bad_json.json()["code"] == "INVALID_JSON"

    # 6. Gitea header variant
    gitea_payload = json.dumps({"action": "ping"}).encode("utf-8")
    gitea_sig = hmac.new(secret_str.encode("utf-8"), gitea_payload, hashlib.sha256).hexdigest()
    resp_gitea = await anon_client.post(
        f"/api/v1/webhooks/git/forgejo?binding_id={fj_binding_id}",
        content=gitea_payload,
        headers={
            "Content-Type": "application/json",
            "X-Gitea-Signature": gitea_sig,
            "X-Gitea-Event": "push",
        },
    )
    assert resp_gitea.status_code == 200
    assert resp_gitea.json()["delivery_id"]

    # 7. Non-UUID binding_id falls back to 404
    resp_bad_uuid = await anon_client.post(
        "/api/v1/webhooks/git/github?binding_id=invalid-uuid",
        content=json.dumps({"action": "ping"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert resp_bad_uuid.status_code == 404

    # 8. Subsequent webhook updates existing PR artifact
    fj_pr_update = json.dumps(
        {
            "pull_request": {
                "id": 101,
                "title": f"Updated title {issue_key}",
                "html_url": "https://forgejo.org/team/fj-repo/pulls/101",
                "head": {"ref": f"topic/{issue_key}", "sha": "updated123sha"},
                "state": "closed",
            }
        }
    ).encode("utf-8")
    fj_pr_up_sig = hmac.new(secret_str.encode("utf-8"), fj_pr_update, hashlib.sha256).hexdigest()
    resp_up = await anon_client.post(
        f"/api/v1/webhooks/git/forgejo?binding_id={fj_binding_id}",
        content=fj_pr_update,
        headers={
            "Content-Type": "application/json",
            "X-Forgejo-Signature": fj_pr_up_sig,
            "X-Forgejo-Event": "pull_request",
            "X-Forgejo-Delivery": "up-del-1",
        },
    )
    assert resp_up.status_code == 200
    assert resp_up.json()["links_created"] == 0


async def test_inbound_scm_webhooks_coverage_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Exercise coverage edge cases in inbound SCM webhooks router."""
    admin = await make_user("admin_edge", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("EDGE", created_by=admin)
    client = as_principal(admin, aal_level=2)
    await _create_test_issue(client, "EDGE", "Edge case issue")
    secret_str = "secret-edge-key"

    binding_id = await _create_repo_binding_with_secret(
        api_env,
        admin,
        project_id,
        slug="edge-repo",
        remote_url="https://github.com/org/edge.git",
        secret_str=secret_str,
    )
    anon_client = api_env.client

    # 1. Payload with PR without issue keys, commits not a list, ref without keys
    edge_payload = json.dumps(
        {
            "pull_request": {
                "title": "No issue keys here",
                "body": "Still no keys",
            },
            "commits": "not-a-list",
            "ref": "refs/heads/topic/NOKEYS",
        }
    ).encode("utf-8")
    sig = hmac.new(secret_str.encode("utf-8"), edge_payload, hashlib.sha256).hexdigest()
    resp_edge1 = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={binding_id}",
        content=edge_payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={sig}",
            "X-GitHub-Delivery": "edge-del-1",
        },
    )
    assert resp_edge1.status_code == 200
    assert resp_edge1.json()["links_created"] == 0

    # 2. Commits containing a non-dict and a commit with a non-existent issue key
    edge_payload2 = json.dumps(
        {
            "commits": [
                "not-a-dict",
                {"message": "Refs EDGE-99999 non-existent"},
            ],
        }
    ).encode("utf-8")
    sig2 = hmac.new(secret_str.encode("utf-8"), edge_payload2, hashlib.sha256).hexdigest()
    resp_edge2 = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={binding_id}",
        content=edge_payload2,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={sig2}",
            "X-GitHub-Delivery": "edge-del-2",
        },
    )
    assert resp_edge2.status_code == 200
    assert resp_edge2.json()["links_created"] == 0

    # 3. Content-Length header > MAX_PAYLOAD_BYTES triggers 413
    resp_413_cl = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={binding_id}",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "Content-Length": "2000000",
        },
    )
    assert resp_413_cl.status_code == 413

    # 4. Content-Length invalid integer ignored
    resp_bad_cl = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={binding_id}",
        content=edge_payload,
        headers={
            "Content-Type": "application/json",
            "Content-Length": "not-an-int",
            "X-Hub-Signature-256": f"sha256={sig}",
            "X-GitHub-Delivery": "edge-del-3",
        },
    )
    assert resp_bad_cl.status_code == 200

    # 5. Delivery ID from X-Delivery-Id header fallback
    resp_deliv_fallback = await anon_client.post(
        f"/api/v1/webhooks/git/github?binding_id={binding_id}",
        content=edge_payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={sig}",
            "X-Delivery-Id": "generic-delivery-123",
        },
    )
    assert resp_deliv_fallback.status_code == 200
    assert resp_deliv_fallback.json()["delivery_id"] == "generic-delivery-123"

    # 6. Test helper functions directly
    starlette_req = Request({"type": "http", "headers": []})
    assert _extract_delivery_id("unknown", starlette_req, b"body") is not None
    assert _extract_event_type("unknown", starlette_req) == "unknown"
