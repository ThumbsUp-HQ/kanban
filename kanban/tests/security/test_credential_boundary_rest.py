# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Security unit and integration tests for CredentialBoundary across REST Bearer auth (KAN-66).

Enforces KB-SEC-04 Actions 1-4:
- Action 1: PrincipalContext.credential_boundary immutability & attachment for MCP keys and tokens.
- Action 2: Client IP CIDR allowlist, workspace allowlist, and REST surface restrictions.
- Action 3: compute_effective_capabilities and evaluate_capabilities project & mask enforcement.
- Action 4: require_admin_aal2 rejection of headless agent/docs tokens minted by admins.
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING, Annotated, Any, cast

import httpx
import pytest
from fastapi import Depends, FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse

from database.session import RLSContext, bind_rls_context
from kanban.api.deps import PrincipalContext, get_current_principal, get_principal
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.security.boundary import CredentialBoundary, EmptyCapabilitySet
from kanban.security.mcp_keys import (
    McpIntrospectionResult,
    mint_mcp_api_key,
)
from kanban.security.permissions import (
    Capability,
    compute_effective_capabilities,
    evaluate_capabilities,
    require_capability,
)
from kanban.tests.security.helpers import (
    add_acl_entry,
    add_role_binding,
    create_project,
    create_registered_object,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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


# ==============================================================================
# Action 1: Model Invariants, Immutability & Attachment
# ==============================================================================


def test_action_1_boundary_model_immutability_and_defaults() -> None:
    """Verify CredentialBoundary is frozen, immutable, and normalizes inputs."""
    ws_1 = uuid.uuid4()
    proj_1 = uuid.uuid4()

    boundary = CredentialBoundary(
        scope_tier="server",  # Normalized to "global"
        surface="agent",
        workspace_allowlist=[str(ws_1)],  # Normalized to frozenset[uuid.UUID]
        project_allowlist=[proj_1],  # Normalized to frozenset[uuid.UUID]
        capability_mask=15,
        allowed_tools=["read_ticket", "search_tickets"],  # Normalized to frozenset[str]
        allowed_cidrs=["192.168.1.0/24"],  # Normalized to tuple
        has_aal2_provenance=False,
    )

    # Immutability
    with pytest.raises(FrozenInstanceError):
        boundary.surface = "admin"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        boundary.capability_mask = 255  # type: ignore[misc]

    # Normalization checks
    assert boundary.scope_tier == "global"
    assert boundary.surface == "agent"
    assert boundary.workspace_allowlist == frozenset({ws_1})
    assert boundary.project_allowlist == frozenset({proj_1})
    assert boundary.capability_mask == 15
    assert boundary.allowed_tools == frozenset({"read_ticket", "search_tickets"})
    assert boundary.allowed_cidrs == ("192.168.1.0/24",)
    assert boundary.has_aal2_provenance is False

    # Attachment to PrincipalContext
    ctx = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=ws_1,
        credential_boundary=boundary,
    )
    assert ctx.credential_boundary is boundary
    assert ctx.credential_boundary.allows_workspace(ws_1) is True
    assert ctx.credential_boundary.allows_workspace(uuid.uuid4()) is False


def test_action_1_from_introspection_mapping() -> None:
    """Verify CredentialBoundary.from_introspection correctly maps McpIntrospectionResult."""
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    exec_id = uuid.uuid4()

    # Case A: Admin API key with verified provenance
    intro_admin = McpIntrospectionResult(
        active=True,
        principal_id=uuid.uuid4(),
        workspace_id=ws_id,
        surface="admin",
        scope_tier="workspace",
        project_id=proj_id,
        allowed_workspace_ids=[ws_id],
        allowed_project_ids=[proj_id],
        capability_mask=63,
        allowed_tools=["manage_users"],
        allowed_cidrs=["10.0.0.0/8"],
        execution_id=exec_id,
        token_kind="api_key",  # noqa: S106
    )
    boundary_admin = CredentialBoundary.from_introspection(intro_admin)
    assert boundary_admin.surface == "admin"
    assert boundary_admin.scope_tier == "workspace"
    assert boundary_admin.workspace_allowlist == frozenset({ws_id})
    assert boundary_admin.project_allowlist == frozenset({proj_id})
    assert boundary_admin.capability_mask == 63
    assert boundary_admin.allowed_tools == frozenset({"manage_users"})
    assert boundary_admin.allowed_cidrs == ("10.0.0.0/8",)
    assert boundary_admin.execution_id == exec_id
    assert boundary_admin.has_aal2_provenance is True

    # Case B: Ephemeral token has no AAL2 provenance
    intro_eph = McpIntrospectionResult(
        active=True,
        principal_id=uuid.uuid4(),
        workspace_id=ws_id,
        surface="agent",
        scope_tier="project",
        project_id=proj_id,
        token_kind="ephemeral",  # noqa: S106
    )
    boundary_eph = CredentialBoundary.from_introspection(intro_eph)
    assert boundary_eph.surface == "agent"
    assert boundary_eph.scope_tier == "project"
    assert boundary_eph.has_aal2_provenance is False


@pytest.mark.asyncio
async def test_action_1_session_resolver_attaches_boundary(db_session: AsyncSession) -> None:
    """Verify SessionCookieResolver constructs and attaches CredentialBoundary upon Bearer auth."""
    ws_id = await create_workspace(db_session, name="WS-Boundary-Mint")
    user_id = await create_user(db_session, ws_id, handle="@bounduser", display_name="Bound User")
    await add_role_binding(
        db_session, ws_id, user_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    ctx = RLSContext(
        principal_id=user_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
    )
    await bind_rls_context(db_session, ctx)

    _key_record, plaintext = await mint_mcp_api_key(
        db_session,
        workspace_id=ws_id,
        principal_id=user_id,
        surface="agent",
        scopes=["agent:read", "agent:write"],
        created_by_id=user_id,
        allowed_cidrs=["127.0.0.1/32"],
        capability_mask=31,
    )

    # Set up resolver with a fake session factory returning db_session
    class _FakeFactory:
        def session(self, _ctx: object) -> object:
            class _CtxMgr:
                async def __aenter__(self) -> AsyncSession:
                    return db_session

                async def __aexit__(self, *args: object) -> None:
                    pass

            return _CtxMgr()

    resolver = SessionCookieResolver(
        SessionService(b"s" * 32),
        _FakeFactory(),  # type: ignore[arg-type]
    )

    # Create dummy Starlette request with Bearer token
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/issues",
        "headers": [(b"authorization", f"Bearer {plaintext}".encode())],
    }
    req = Request(scope)

    resolved_ctx = await resolver.resolve(req)
    assert resolved_ctx is not None
    assert resolved_ctx.is_mcp_credential is True
    assert resolved_ctx.credential_boundary is not None
    boundary = resolved_ctx.credential_boundary
    assert boundary.surface == "agent"
    assert boundary.scope_tier == "workspace"
    assert boundary.workspace_allowlist == frozenset({ws_id})
    assert boundary.capability_mask == 31
    assert boundary.allowed_cidrs == ("127.0.0.1/32",)
    assert boundary.has_aal2_provenance is False


# ==============================================================================
# Action 2: REST Bearer Validation (CIDR, Workspace Scope, Surface Restrictions)
# ==============================================================================


@pytest.mark.asyncio
async def test_action_2_rest_bearer_cidr_allowlist_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify client IP validation raises 403 CIDR_NOT_ALLOWED if outside allowlist."""
    monkeypatch.setenv("KANBAN_TRUSTED_PROXIES", "127.0.0.1/32")
    app = FastAPI()
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    @app.get("/api/v1/test/cidr")
    async def sample_endpoint(
        principal: Annotated[PrincipalContext, Depends(get_current_principal)],
    ) -> JSONResponse:
        return JSONResponse({"status": "ok", "user": str(principal.principal_id)})

    # Mock resolver returning a principal with CIDR restriction
    allowed_net = "192.168.1.0/24"
    boundary = CredentialBoundary(
        scope_tier="global",
        surface="agent",
        allowed_cidrs=(allowed_net,),
    )

    class _MockResolver:
        async def resolve(self, _request: Request) -> PrincipalContext:
            return PrincipalContext(
                principal_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                credential_boundary=boundary,
            )

    app.state.principal_resolver = _MockResolver()

    transport = httpx.ASGITransport(app=app)

    # 1. Request from allowed IP (192.168.1.42)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"x-forwarded-for": "192.168.1.42"},
    ) as client:
        res = await client.get("/api/v1/test/cidr")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    # 2. Request from disallowed IP (10.0.0.50)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"x-forwarded-for": "10.0.0.50"},
    ) as client:
        res = await client.get("/api/v1/test/cidr")
        assert res.status_code == 403
        data = res.json()
        assert data["code"] == "CIDR_NOT_ALLOWED"
        assert "outside allowed CIDRs" in data["detail"]


@pytest.mark.asyncio
async def test_action_2_rest_bearer_workspace_allowlist_validation() -> None:
    """Verify workspace validation raises 403 CREDENTIAL_SCOPE_VIOLATION if outside allowlist."""
    app = FastAPI()
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    ws_allowed = uuid.uuid4()
    ws_forbidden = uuid.uuid4()

    boundary = CredentialBoundary(
        scope_tier="workspace",
        surface="agent",
        workspace_allowlist=frozenset({ws_allowed}),
    )

    # Endpoint with get_principal
    @app.get("/api/v1/test/ws")
    async def sample_endpoint(
        principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> JSONResponse:
        return JSONResponse({"status": "ok", "workspace": str(principal.workspace_id)})

    # Case A: Principal belongs to allowed workspace -> 200 OK
    class _AllowedWsResolver:
        async def resolve(self, _request: Request) -> PrincipalContext:
            return PrincipalContext(
                principal_id=uuid.uuid4(),
                workspace_id=ws_allowed,
                credential_boundary=boundary,
            )

    app.state.principal_resolver = _AllowedWsResolver()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/test/ws")
        assert res.status_code == 200
        assert res.json()["workspace"] == str(ws_allowed)

    # Case B: Principal belongs to forbidden workspace -> 403 CREDENTIAL_SCOPE_VIOLATION
    class _ForbiddenWsResolver:
        async def resolve(self, _request: Request) -> PrincipalContext:
            return PrincipalContext(
                principal_id=uuid.uuid4(),
                workspace_id=ws_forbidden,
                credential_boundary=boundary,
            )

    app.state.principal_resolver = _ForbiddenWsResolver()
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/test/ws")
        assert res.status_code == 403
        data = res.json()
        assert data["code"] == "CREDENTIAL_SCOPE_VIOLATION"


@pytest.mark.asyncio
async def test_action_2_rest_bearer_surface_restrictions() -> None:
    """Verify surface restrictions for docs and admin endpoints."""
    app = FastAPI()
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    # Setup routes representing various REST endpoints
    @app.post("/api/v1/issues")
    async def create_issue_endpoint(
        _principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> JSONResponse:
        return JSONResponse({"created": "issue"})

    @app.patch("/api/v1/issues/{issue_id}")
    async def update_issue_endpoint(
        issue_id: str,
        _principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> JSONResponse:
        return JSONResponse({"updated": issue_id})

    @app.delete("/api/v1/issues/{issue_id}")
    async def delete_issue_endpoint(
        issue_id: str,
        _principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> JSONResponse:
        return JSONResponse({"deleted": issue_id})

    @app.get("/api/v1/issues")
    async def list_issues_endpoint(
        _principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> JSONResponse:
        return JSONResponse({"issues": []})

    @app.post("/api/v1/docs")
    async def create_doc_endpoint(
        _principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> JSONResponse:
        return JSONResponse({"created": "doc"})

    @app.put("/api/v1/docs/{doc_id}")
    async def update_doc_endpoint(
        doc_id: str,
        _principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> JSONResponse:
        return JSONResponse({"updated": doc_id})

    @app.get("/api/v1/admin/server/settings")
    async def admin_settings_endpoint(
        _principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> JSONResponse:
        return JSONResponse({"admin": "settings"})

    transport = httpx.ASGITransport(app=app)

    # 1. Test DOCS surface credential
    docs_boundary = CredentialBoundary(scope_tier="global", surface="docs")

    class _DocsResolver:
        async def resolve(self, _request: Request) -> PrincipalContext:
            return PrincipalContext(
                principal_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                credential_boundary=docs_boundary,
            )

    app.state.principal_resolver = _DocsResolver()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Docs surface mutating issues -> 403 INSUFFICIENT_SCOPE
        res_post_issue = await client.post("/api/v1/issues", json={"title": "test"})
        assert res_post_issue.status_code == 403
        assert res_post_issue.json()["code"] == "INSUFFICIENT_SCOPE"

        res_patch_issue = await client.patch("/api/v1/issues/123", json={"title": "new"})
        assert res_patch_issue.status_code == 403
        assert res_patch_issue.json()["code"] == "INSUFFICIENT_SCOPE"

        res_del_issue = await client.delete("/api/v1/issues/123")
        assert res_del_issue.status_code == 403
        assert res_del_issue.json()["code"] == "INSUFFICIENT_SCOPE"

        # Docs surface reading issues -> 200 OK
        res_get_issues = await client.get("/api/v1/issues")
        assert res_get_issues.status_code == 200

        # Docs surface mutating docs -> 200 OK
        res_post_doc = await client.post("/api/v1/docs", json={"title": "Design"})
        assert res_post_doc.status_code == 200

        res_put_doc = await client.put("/api/v1/docs/456", json={"title": "Updated"})
        assert res_put_doc.status_code == 200

        # Docs surface accessing /api/v1/admin/* -> 403 AAL2_REQUIRED
        res_admin = await client.get("/api/v1/admin/server/settings")
        assert res_admin.status_code == 403
        assert res_admin.json()["code"] == "AAL2_REQUIRED"

    # 2. Test AGENT surface credential
    agent_boundary = CredentialBoundary(scope_tier="global", surface="agent")

    class _AgentResolver:
        async def resolve(self, _request: Request) -> PrincipalContext:
            return PrincipalContext(
                principal_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                credential_boundary=agent_boundary,
            )

    app.state.principal_resolver = _AgentResolver()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Agent surface mutating issues -> 200 OK
        res_agent_post = await client.post("/api/v1/issues", json={"title": "agent issue"})
        assert res_agent_post.status_code == 200

        # Agent surface calling /api/v1/admin/* -> 403 AAL2_REQUIRED
        res_agent_admin = await client.get("/api/v1/admin/server/settings")
        assert res_agent_admin.status_code == 403
        assert res_agent_admin.json()["code"] == "AAL2_REQUIRED"


# ==============================================================================
# Action 3: Project Allowlists, Capability Mask & compute_effective_capabilities
# ==============================================================================


def test_action_3_compute_effective_capabilities_matrix() -> None:
    """Verify compute_effective_capabilities enforces project allowlists and capability masks."""
    proj_allowed = uuid.uuid4()
    proj_denied = uuid.uuid4()

    # Boundary allowing only proj_allowed with capability_mask=5 (VIEW(1) | EDIT(4))
    boundary = CredentialBoundary(
        scope_tier="project",
        surface="agent",
        project_allowlist=frozenset({proj_allowed}),
        capability_mask=int(Capability.VIEW | Capability.EDIT),
    )
    caller = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        credential_boundary=boundary,
    )

    # 1. Outside project_allowlist -> returns frozenset() / EmptyCapabilitySet
    denied_res = compute_effective_capabilities(
        Capability.ALL, caller=caller, project_id=proj_denied
    )
    assert denied_res == frozenset()
    assert not bool(denied_res)
    assert cast("Any", denied_res) == Capability.NONE

    denied_str_res = compute_effective_capabilities(
        {"VIEW", "EDIT", "DELETE"}, caller=caller, project_id=proj_denied
    )
    assert denied_str_res == frozenset()

    # 2. Inside project_allowlist -> intersects RBAC with capability_mask
    allowed_cap = cast(
        "Capability",
        compute_effective_capabilities(Capability.ALL, caller=caller, project_id=proj_allowed),
    )
    assert allowed_cap == (Capability.VIEW | Capability.EDIT)
    assert Capability.DELETE not in allowed_cap
    assert Capability.ADMIN not in allowed_cap

    # 3. String sets intersection
    allowed_str = compute_effective_capabilities(
        {"VIEW", "EDIT", "DELETE", "ADMIN"}, caller=caller, project_id=proj_allowed
    )
    assert allowed_str == frozenset({"VIEW", "EDIT"})

    # 4. Caller without boundary returns full RBAC capabilities
    unbounded_caller = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        credential_boundary=None,
    )
    unbounded_cap = compute_effective_capabilities(
        Capability.ALL, caller=unbounded_caller, project_id=proj_denied
    )
    assert unbounded_cap == Capability.ALL

    unbounded_str = compute_effective_capabilities(
        {"VIEW", "EDIT"}, caller=unbounded_caller, project_id=proj_denied
    )
    assert unbounded_str == frozenset({"VIEW", "EDIT"})


@pytest.mark.asyncio
async def test_action_3_evaluate_capabilities_and_require_capability(
    db_session: AsyncSession,
) -> None:
    """Verify evaluate_capabilities enforces CredentialBoundary project allowlist and mask."""
    ws_id = await create_workspace(db_session, name="WS-Proj-Eval")
    admin_id = await create_user(db_session, ws_id, handle="@evaladmin", display_name="Eval Admin")
    await add_role_binding(
        db_session, ws_id, admin_id, role="WORKSPACE_ADMIN", scope_type="workspace"
    )

    proj_1 = await create_project(db_session, ws_id, identifier="PRJA", name="Project One")
    proj_2 = await create_project(db_session, ws_id, identifier="PRJB", name="Project Two")

    issue_1 = await create_registered_object(
        db_session, ws_id, kind="issue", key="PRJA-1", title="Issue in P1", project_id=proj_1
    )
    issue_2 = await create_registered_object(
        db_session, ws_id, kind="issue", key="PRJB-1", title="Issue in P2", project_id=proj_2
    )

    # Give admin full access to both issues via ERA
    await add_acl_entry(db_session, ws_id, issue_1, admin_id, capability_mask=int(Capability.ALL))
    await add_acl_entry(db_session, ws_id, issue_2, admin_id, capability_mask=int(Capability.ALL))
    await rebuild_era(db_session, ws_id)

    # Boundary restricted strictly to proj_1 with capability_mask=VIEW (1)
    boundary = CredentialBoundary(
        scope_tier="project",
        surface="agent",
        project_allowlist=frozenset({proj_1}),
        capability_mask=int(Capability.VIEW),
    )
    caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("agent:read", "agent:write"),
        credential_boundary=boundary,
    )

    # 1. Object in allowed project (issue_1 in proj_1) -> has VIEW, lacks EDIT
    caps_1 = await evaluate_capabilities(db_session, caller, issue_1)
    assert Capability.VIEW in caps_1
    assert Capability.EDIT not in caps_1

    # require_capability VIEW passes
    req_pass = await require_capability(db_session, caller, issue_1, Capability.VIEW)
    assert req_pass == caps_1

    # require_capability EDIT raises 403 INSUFFICIENT_CAPABILITY
    with pytest.raises(ProblemException) as exc_info:
        await require_capability(db_session, caller, issue_1, Capability.EDIT)
    assert exc_info.value.status == 403
    assert exc_info.value.code == "INSUFFICIENT_CAPABILITY"

    # 2. Object in disallowed project (issue_2 in proj_2) -> returns Capability.NONE
    caps_2 = await evaluate_capabilities(db_session, caller, issue_2)
    assert caps_2 == Capability.NONE

    # S3.4 Anti-enumeration: require_capability VIEW raises 404 NOT_FOUND!
    with pytest.raises(ProblemException) as exc_info_404:
        await require_capability(db_session, caller, issue_2, Capability.VIEW)
    assert exc_info_404.value.status == 404
    assert exc_info_404.value.code == "NOT_FOUND"


# ==============================================================================
# Action 4: require_admin_aal2 Headless Token Rejection
# ==============================================================================


@pytest.mark.asyncio
async def test_action_4_require_admin_aal2_headless_rejection(db_session: AsyncSession) -> None:
    """Verify require_admin_aal2 rejects headless agent/docs tokens minted by admins."""
    ws_id = await create_workspace(db_session, name="WS-AAL2-Policy")
    admin_id = await create_user(
        db_session, ws_id, handle="@serveradm", display_name="Server Administrator"
    )
    # Grant SERVER_ADMIN role
    await add_role_binding(db_session, ws_id, admin_id, role="SERVER_ADMIN", scope_type="server")

    # Set up dummy session factory for require_admin_aal2
    class _Factory:
        def session(self, _ctx: object) -> object:
            class _CtxMgr:
                async def __aenter__(self) -> AsyncSession:
                    return db_session

                async def __aexit__(self, *args: object) -> None:
                    pass

            return _CtxMgr()

    app = FastAPI()
    app.state.session_factory = _Factory()

    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/admin/server/settings",
            "app": app,
        }
    )

    # 1. Agent token minted by this SERVER_ADMIN (surface="agent") -> 403 AAL2_REQUIRED
    agent_boundary = CredentialBoundary(
        scope_tier="global",
        surface="agent",
        has_aal2_provenance=False,
    )
    agent_caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=1,
        is_mcp_credential=True,
        credential_boundary=agent_boundary,
    )

    with pytest.raises(ProblemException) as exc_agent:
        await require_admin_aal2(req, agent_caller)
    assert exc_agent.value.status == 403
    assert exc_agent.value.code == "AAL2_REQUIRED"
    assert exc_agent.value.detail is not None
    assert "Administrative routes require multi-factor authentication" in exc_agent.value.detail

    # 2. Docs token minted by this SERVER_ADMIN (surface="docs") -> 403 AAL2_REQUIRED
    docs_boundary = CredentialBoundary(
        scope_tier="global",
        surface="docs",
        has_aal2_provenance=False,
    )
    docs_caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=1,
        is_mcp_credential=True,
        credential_boundary=docs_boundary,
    )

    with pytest.raises(ProblemException) as exc_docs:
        await require_admin_aal2(req, docs_caller)
    assert exc_docs.value.status == 403
    assert exc_docs.value.code == "AAL2_REQUIRED"

    # 3. Admin token with verified AAL2 provenance -> passes!
    admin_boundary = CredentialBoundary(
        scope_tier="global",
        surface="admin",
        has_aal2_provenance=True,
    )
    admin_caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=2,
        is_mcp_credential=True,
        credential_boundary=admin_boundary,
    )

    passed_ctx = await require_admin_aal2(req, admin_caller)
    assert passed_ctx is admin_caller


# ==============================================================================
# Additional Exhaustive Tests for 100% Boundary Coverage
# ==============================================================================


def test_boundary_model_and_introspection_edge_cases() -> None:
    """Exercise EmptyCapabilitySet and from_introspection edge cases."""
    # 1. EmptyCapabilitySet
    empty_cap = EmptyCapabilitySet()
    assert empty_cap == Capability.NONE
    assert empty_cap == 0
    assert empty_cap == frozenset()
    assert empty_cap != {"VIEW"}
    assert int(empty_cap) == 0
    assert not bool(empty_cap)
    assert isinstance(hash(empty_cap), int)

    # 2. Normalization & immutability
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    b_norm = CredentialBoundary(
        scope_tier="server",
        workspace_allowlist=frozenset({ws_id}),
        project_allowlist=frozenset({proj_id}),
        allowed_tools=frozenset({"tool1"}),
        allowed_cidrs=("10.0.0.0/8",),
    )
    assert b_norm.scope_tier == "global"
    assert b_norm.workspace_allowlist == frozenset({ws_id})
    assert b_norm.project_allowlist == frozenset({proj_id})
    assert b_norm.allowed_tools == frozenset({"tool1"})
    assert b_norm.allowed_cidrs == ("10.0.0.0/8",)

    # 3. from_introspection branch coverage
    # 3a. server scope tier & legacy allowed_projects list
    intro_server = McpIntrospectionResult(
        active=True,
        principal_id=uuid.uuid4(),
        workspace_id=None,
        surface="custom_surface",  # fallback to "agent"
        scope_tier="server",  # maps to "global"
        allowed_projects=[proj_id],  # legacy field
        project_id=None,
        capability_mask=None,  # defaults to 255
        allowed_tools=None,
        allowed_cidrs=None,
    )
    b_server = CredentialBoundary.from_introspection(intro_server)
    assert b_server.scope_tier == "global"
    assert b_server.surface == "agent"
    assert b_server.project_allowlist == frozenset({proj_id})
    assert b_server.capability_mask == 255
    assert b_server.allowed_tools is None
    assert b_server.allowed_cidrs == ()

    # 3b. fallback tier
    intro_fallback = McpIntrospectionResult(
        active=True,
        principal_id=uuid.uuid4(),
        scope_tier="unknown_tier",  # fallback to "workspace"
        surface=None,
    )
    b_fallback = CredentialBoundary.from_introspection(intro_fallback)
    assert b_fallback.scope_tier == "workspace"
    assert b_fallback.surface == "agent"


def test_boundary_scoping_and_capabilities_edge_cases() -> None:
    """Exercise allows_workspace, allows_project, allows_ip, and effective_capabilities."""
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    b_norm = CredentialBoundary(
        scope_tier="global",
        workspace_allowlist=frozenset({ws_id}),
        project_allowlist=frozenset({proj_id}),
    )

    # 1. allows_workspace
    assert b_norm.allows_workspace(None) is True
    assert b_norm.allows_workspace(ws_id) is True
    assert b_norm.allows_workspace(str(ws_id)) is True
    assert b_norm.allows_workspace(uuid.uuid4()) is False

    b_empty_ws_global = CredentialBoundary(scope_tier="global", workspace_allowlist=frozenset())
    assert b_empty_ws_global.allows_workspace(uuid.uuid4()) is True

    b_empty_ws_scoped = CredentialBoundary(scope_tier="workspace", workspace_allowlist=frozenset())
    assert b_empty_ws_scoped.allows_workspace(uuid.uuid4()) is False

    # 2. allows_project
    assert b_norm.allows_project(None) is True
    assert b_norm.allows_project(proj_id) is True
    assert b_norm.allows_project(str(proj_id)) is True
    assert b_norm.allows_project(uuid.uuid4()) is False

    b_empty_proj_tier = CredentialBoundary(scope_tier="project", project_allowlist=frozenset())
    assert b_empty_proj_tier.allows_project(uuid.uuid4()) is False

    b_empty_proj_ws = CredentialBoundary(scope_tier="workspace", project_allowlist=frozenset())
    assert b_empty_proj_ws.allows_project(uuid.uuid4()) is True

    # 3. allows_ip
    b_no_cidr = CredentialBoundary(allowed_cidrs=())
    assert b_no_cidr.allows_ip("192.168.1.1") is True

    b_cidr = CredentialBoundary(allowed_cidrs=("10.0.0.0/8", "192.168.1.0/24"))
    assert b_cidr.allows_ip(None) is True
    assert b_cidr.allows_ip("") is True
    assert b_cidr.allows_ip("10.5.6.7") is True
    assert b_cidr.allows_ip("192.168.1.100") is True
    assert b_cidr.allows_ip("172.16.0.1") is False
    assert b_cidr.allows_ip("not-a-valid-ip") is False

    # 4. effective_capabilities
    b_mask = CredentialBoundary(capability_mask=int(Capability.VIEW))
    assert b_mask.effective_capabilities(Capability.ALL) == Capability.VIEW
    assert b_mask.effective_capabilities(int(Capability.ALL)) == Capability.VIEW
    assert b_mask.effective_capabilities([]) == frozenset()
    assert b_mask.effective_capabilities(set()) == frozenset()
    assert b_mask.effective_capabilities([Capability.VIEW, Capability.EDIT]) == frozenset(
        {Capability.VIEW}
    )
    assert b_mask.effective_capabilities({"VIEW", "EDIT"}) == frozenset({"VIEW"})
    assert b_mask.effective_capabilities(None) is None
    assert b_mask.effective_capabilities("passthrough") == "passthrough"
