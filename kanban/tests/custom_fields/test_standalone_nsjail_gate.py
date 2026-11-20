# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for standalone nsjail sandbox fail-closed gating and tier_b_runner wiring (KAN-32)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.custom_fields.manifest import compute_field_manifest_sha256
from kanban.custom_fields.service import assert_tier_available, is_tier_b_available
from kanban.sandbox.nsjail_runner import NsjailRunResult

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _as_admin_aal2(api_env: ApiEnv, user: SeededUser) -> httpx.AsyncClient:
    """Configure active principal context with PROJECT_ADMIN and AAL2."""
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )
    return api_env.client


class MockTierBRunner:
    """Mock Tier B nsjail runner returning deterministic output."""

    async def execute(self, *args: object, **kwargs: object) -> NsjailRunResult:  # noqa: ARG002
        """Execute mock nsjail container."""
        return NsjailRunResult(
            returncode=0,
            stdout=b'"mocked-nsjail-output"',
            stderr=b"",
        )

    async def run(self, *args: object, **kwargs: object) -> bytes:  # noqa: ARG002
        """Run mock nsjail script."""
        return b'"mocked-nsjail-output"'


def _set_tier_b_state(
    client: httpx.AsyncClient,
    *,
    available: bool,
    runner: object = None,
) -> None:
    """Configure tier_b_sandbox_available and optional tier_b_runner on test app."""
    transport = getattr(client, "_transport", None)
    app = getattr(transport, "app", None)
    assert app is not None
    app.state.tier_b_sandbox_available = available
    if runner is not None:
        app.state.tier_b_runner = runner


async def _create_test_issue(
    client: httpx.AsyncClient,
    project_ref: str,
) -> str:
    """Create a minimal issue for test execution via API."""
    resp = await client.post(
        f"/api/v1/projects/{project_ref}/issues",
        json={"summary": "Gate Test Issue", "description_markdown": "Test Description"},
    )
    assert resp.status_code == 201
    return str(resp.json()["key"])


async def test_create_custom_field_nsjail_rejected_in_standalone(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """In standalone mode (tier_b_sandbox_available=False), creating nsjail tier returns 422."""
    admin = await make_user("admin-gate-1", workspace_role="WORKSPACE_ADMIN")
    await make_project("GATE1", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)
    _set_tier_b_state(client, available=False)

    resp = await client.post(
        "/api/v1/projects/GATE1/custom-fields",
        json={
            "slug": "nsjail-standalone-test",
            "name": "Nsjail Test Field",
            "tier": "nsjail",
            "output_format": "text",
            "output_format_metadata": {"max_length": 140},
            "script_source": "import sys; print('hello')",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "SANDBOX_UNAVAILABLE_IN_STANDALONE"
    assert "standalone" in body["detail"].lower()
    assert "formula" in body["detail"].lower()


async def test_create_custom_field_nsjail_succeeds_in_multicontainer(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """In multi-container mode (tier_b_sandbox_available=True), creating nsjail tier succeeds."""
    admin = await make_user("admin-gate-2", workspace_role="WORKSPACE_ADMIN")
    await make_project("GATE2", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)
    _set_tier_b_state(client, available=True)

    resp = await client.post(
        "/api/v1/projects/GATE2/custom-fields",
        json={
            "slug": "nsjail-multi-test",
            "name": "Nsjail Multi Test Field",
            "tier": "nsjail",
            "output_format": "text",
            "output_format_metadata": {"max_length": 140},
            "script_source": "import sys; print('hello')",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["tier"] == "nsjail"


async def test_update_custom_field_nsjail_rejected_in_standalone(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Updating definition tier to nsjail in standalone mode fails with 422."""
    admin = await make_user("admin-gate-3", workspace_role="WORKSPACE_ADMIN")
    await make_project("GATE3", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)
    _set_tier_b_state(client, available=True)

    # Create wasm field first
    create_resp = await client.post(
        "/api/v1/projects/GATE3/custom-fields",
        json={
            "slug": "wasm-to-nsjail",
            "name": "Wasm to Nsjail Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 140},
            "script_source": "scalar: 'initial'",
        },
    )
    assert create_resp.status_code == 201
    field_id = create_resp.json()["id"]

    # Switch to standalone mode
    _set_tier_b_state(client, available=False)

    # Attempt to patch tier to nsjail
    patch_resp = await client.patch(
        f"/api/v1/projects/GATE3/custom-fields/{field_id}",
        json={"tier": "nsjail"},
    )
    assert patch_resp.status_code == 422
    assert patch_resp.json()["code"] == "SANDBOX_UNAVAILABLE_IN_STANDALONE"


async def test_update_existing_nsjail_field_metadata_succeeds_in_standalone(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Editing non-tier properties on pre-existing nsjail field succeeds in standalone mode."""
    admin = await make_user("admin-gate-4", workspace_role="WORKSPACE_ADMIN")
    await make_project("GATE4", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)
    _set_tier_b_state(client, available=True)

    # Create nsjail field while available
    create_resp = await client.post(
        "/api/v1/projects/GATE4/custom-fields",
        json={
            "slug": "preexisting-nsjail",
            "name": "Preexisting Nsjail Field",
            "tier": "nsjail",
            "output_format": "text",
            "output_format_metadata": {"max_length": 140},
            "script_source": "import sys; print('initial')",
        },
    )
    assert create_resp.status_code == 201
    field_id = create_resp.json()["id"]

    # Switch to standalone mode (simulating imported backup)
    _set_tier_b_state(client, available=False)

    # Updating name and enabled state without passing tier must succeed
    patch_resp = await client.patch(
        f"/api/v1/projects/GATE4/custom-fields/{field_id}",
        json={"name": "Renamed Preexisting Nsjail", "is_enabled": False},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Renamed Preexisting Nsjail"
    assert patch_resp.json()["tier"] == "nsjail"
    assert patch_resp.json()["is_enabled"] is False


async def test_test_execute_nsjail_rejected_in_standalone(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Test-executing draft nsjail field in standalone mode returns 422."""
    admin = await make_user("admin-gate-5", workspace_role="WORKSPACE_ADMIN")
    await make_project("GATE5", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)
    issue_key = await _create_test_issue(client, "GATE5")
    _set_tier_b_state(client, available=False)

    resp = await client.post(
        "/api/v1/projects/GATE5/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "nsjail",
            "output_format": "text",
            "output_format_metadata": {},
            "script_source": "import sys; print('test')",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "SANDBOX_UNAVAILABLE_IN_STANDALONE"
    assert "formula" in body["detail"].lower()


async def test_test_execute_nsjail_succeeds_with_wired_tier_b_runner(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Test-executing nsjail field in multi-container mode uses wired tier_b_runner."""
    admin = await make_user("admin-gate-6", workspace_role="WORKSPACE_ADMIN")
    await make_project("GATE6", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)
    issue_key = await _create_test_issue(client, "GATE6")
    _set_tier_b_state(client, available=True, runner=MockTierBRunner())

    resp = await client.post(
        "/api/v1/projects/GATE6/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "nsjail",
            "output_format": "text",
            "output_format_metadata": {},
            "script_source": "import sys; print('test')",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "SUCCESS"
    assert body["value"] == "mocked-nsjail-output"


async def test_execute_custom_field_uses_wired_tier_b_runner(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """POST /issues/{key}/custom-fields/{id}/execute wires tier_b_runner from app.state."""
    admin = await make_user("admin-gate-7", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("GATE7", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)
    await _create_test_issue(client, "GATE7")
    _set_tier_b_state(client, available=True, runner=MockTierBRunner())

    # Create nsjail field
    field_id = uuid.uuid4()
    manifest = compute_field_manifest_sha256(
        script_source="import sys; print('execute')",
        output_format="text",
        output_format_metadata={},
        tier="nsjail",
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "id, workspace_id, project_id, name, slug, tier, output_format, "
            "output_format_metadata, script_source, manifest_sha256, target_scope, "
            "credential_mode, created_by_id"
            ") VALUES ("
            ":id, :ws, :proj, 'Nsjail Exec Field', 'nsjail-exec-field', 'nsjail', 'text', "
            "'{}'::jsonb, 'import sys; print(\"execute\")', :man, 'PROJECT', 'INVOKING_USER', :uid"
            ")"
        ),
        {
            "id": field_id,
            "ws": api_env.workspace_id,
            "proj": proj_id,
            "man": manifest,
            "uid": admin.id,
        },
    )
    await api_env.seed.commit()

    resp = await client.post(f"/api/v1/issues/GATE7-1/custom-fields/{field_id}/execute")
    assert resp.status_code == 200
    body = resp.json()
    assert body["value"] == "mocked-nsjail-output"


def test_is_tier_b_available_direct_helpers() -> None:
    """Test helper functions is_tier_b_available and assert_tier_available directly."""
    # 1. Override takes precedence
    assert is_tier_b_available(override=True) is True
    assert is_tier_b_available(override=False) is False

    # 2. Request with app.state.tier_b_sandbox_available
    req = MagicMock()
    req.app.state.tier_b_sandbox_available = True
    assert is_tier_b_available(request=req) is True
    req.app.state.tier_b_sandbox_available = False
    assert is_tier_b_available(request=req) is False

    # 3. Request without tier_b_sandbox_available attribute
    del req.app.state.tier_b_sandbox_available
    req.app.state.settings = None
    res = is_tier_b_available(request=req)
    assert isinstance(res, bool)

    # 4. Request is None
    res_none = is_tier_b_available(request=None)
    assert isinstance(res_none, bool)

    # 5. assert_tier_available passes for scalar/formula/wasm regardless of tier_b
    assert_tier_available("scalar", tier_b_sandbox_available=False)
    assert_tier_available("formula", tier_b_sandbox_available=False)
    assert_tier_available("wasm", tier_b_sandbox_available=False)

    # 6. assert_tier_available passes for nsjail when available
    assert_tier_available("nsjail", tier_b_sandbox_available=True)

    # 7. assert_tier_available raises 422 ProblemException for nsjail when unavailable
    with pytest.raises(ProblemException) as exc_info:
        assert_tier_available("nsjail", tier_b_sandbox_available=False)
    assert exc_info.value.status == 422
    assert exc_info.value.code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"

