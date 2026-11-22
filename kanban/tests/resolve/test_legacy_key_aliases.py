# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for legacy key alias resolution and cross-workspace RLS isolation (KB-P6-03)."""
# ruff: noqa: E501, TC002, TC003, ANN401, PLR0915

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import IssueKeyAlias
from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import (
    ProblemException,
    problem_exception_handler,
    validation_exception_handler,
)
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1.issues import router as issues_router
from kanban.api.v1.resolve import resolve_router
from kanban.resolve.service import ResolutionService
from kanban.services.issue_keys import resolve_issue_ref


class _TestPrincipalResolver:
    """Configurable principal resolver for testing."""

    def __init__(self, principal: PrincipalContext) -> None:
        self.principal = principal

    async def resolve(self, request: Any) -> PrincipalContext | None:
        del request
        return self.principal


def _build_test_app(
    principal_resolver: _TestPrincipalResolver,
    db_session: AsyncSession,
) -> FastAPI:
    """Construct FastAPI application with resolve and issues routers wired."""
    app = FastAPI(title="Legacy Aliases Test API")
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

    app.state.principal_resolver = principal_resolver
    app.state.resolution_service = ResolutionService()

    async def _override_get_rls_session() -> AsyncIterator[AsyncSession]:
        p = principal_resolver.principal
        await db_session.execute(
            text(
                "SELECT set_config('app.principal_id', :pid, true), "
                "set_config('app.workspace_id', :ws, true), "
                "set_config('app.current_principal_id', :pid, true), "
                "set_config('app.current_workspace_id', :ws, true), "
                "set_config('app.aal_level', '2', true)"
            ),
            {"ws": str(p.workspace_id), "pid": str(p.principal_id)},
        )
        yield db_session

    async def _override_get_principal() -> PrincipalContext:
        return principal_resolver.principal

    app.dependency_overrides[get_rls_session] = _override_get_rls_session
    app.dependency_overrides[get_principal] = _override_get_principal

    app.include_router(resolve_router, prefix="/api/v1")
    app.include_router(issues_router, prefix="/api/v1")
    return app


@pytest.mark.asyncio
async def test_legacy_key_aliases_resolution_and_rls(
    db_session: AsyncSession,
) -> None:
    """Verify legacy key aliases resolve to canonical issue, redirect HTML, and respect RLS."""
    # 1. Bootstrap Workspace 1 (owner of CORE-1 and JIRA-101 alias)
    ws1_id, admin1_id = await bootstrap_workspace_admin(db_session)

    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :pid, true), "
            "set_config('app.workspace_id', :ws, true), "
            "set_config('app.current_principal_id', :pid, true), "
            "set_config('app.current_workspace_id', :ws, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"ws": str(ws1_id), "pid": str(admin1_id)},
    )

    proj_id = (
        await db_session.execute(
            text(
                "SELECT register_object('project'::object_kind, :ws, NULL, 'CORE', 'Core Project', :admin)"
            ),
            {"ws": ws1_id, "admin": admin1_id},
        )
    ).scalar_one()

    await db_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, description_markdown) "
            "VALUES (:id, :ws, 'CORE', 'Core Project', 'Core issue tracking')"
        ),
        {"id": proj_id, "ws": ws1_id},
    )

    state_id = (
        await db_session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :proj AND is_default LIMIT 1"),
            {"proj": proj_id},
        )
    ).scalar_one()

    prio_id = (
        await db_session.execute(
            text(
                "SELECT id FROM project_priorities WHERE project_id = :proj AND is_default LIMIT 1"
            ),
            {"proj": proj_id},
        )
    ).scalar_one()

    seq = (
        await db_session.execute(
            text("SELECT allocate_issue_sequence(:proj)"),
            {"proj": proj_id},
        )
    ).scalar_one()

    issue_id = (
        await db_session.execute(
            text(
                "SELECT register_object('issue'::object_kind, :ws, :proj, :key, 'Canonical Issue One', :admin)"
            ),
            {"ws": ws1_id, "proj": proj_id, "key": f"CORE-{seq}", "admin": admin1_id},
        )
    ).scalar_one()

    await db_session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, summary, description_markdown, state_id, priority_id, created_by_id, original_created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, :seq, 'Canonical Issue One', 'Canonical description', :state, :prio, :admin, :admin, '0|hzzzzz:')"
        ),
        {
            "id": issue_id,
            "ws": ws1_id,
            "proj": proj_id,
            "seq": seq,
            "state": state_id,
            "prio": prio_id,
            "admin": admin1_id,
        },
    )

    # Insert legacy aliases
    aliases = [
        ("JIRA-101", "jira"),
        ("ENG-42", "linear"),
        ("GH-88", "github"),
        ("KANBA-123", "plane"),
    ]
    for leg_key, src in aliases:
        alias = IssueKeyAlias(
            workspace_id=ws1_id,
            legacy_key=leg_key,
            issue_id=issue_id,
            source_system=src,
        )
        db_session.add(alias)

    # Rebuild effective resource access for Workspace 1 so capabilities resolve
    await db_session.flush()
    await db_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": ws1_id},
    )

    # 2. Bootstrap Workspace 2 (isolated tenant)
    ws2_id, admin2_id = await bootstrap_workspace_admin(db_session)

    await db_session.flush()

    # 3. Setup test app and HTTP client
    principal_1 = PrincipalContext(
        principal_id=admin1_id,
        workspace_id=ws1_id,
        token_scopes=("session",),
        aal_level=2,
    )
    principal_2 = PrincipalContext(
        principal_id=admin2_id,
        workspace_id=ws2_id,
        token_scopes=("session",),
        aal_level=2,
    )

    resolver_wrapper = _TestPrincipalResolver(principal_1)
    app = _build_test_app(resolver_wrapper, db_session)
    transport = httpx.ASGITransport(app=app)

    # Set GUC context to Workspace 1
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :pid, true), "
            "set_config('app.workspace_id', :ws, true), "
            "set_config('app.current_principal_id', :pid, true), "
            "set_config('app.current_workspace_id', :ws, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"ws": str(ws1_id), "pid": str(admin1_id)},
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 4. JSON Resolution for JIRA-101 in Workspace 1 -> 200 with X-Kanban-Canonical-Key
        res_json = await client.get(
            "/api/v1/issues/JIRA-101",
            headers={"Accept": "application/json"},
        )
        assert res_json.status_code == 200
        assert res_json.headers.get("X-Kanban-Canonical-Key") == "CORE-1"
        data_json = res_json.json()
        assert data_json["key"] == "CORE-1"
        assert data_json["summary"] == "Canonical Issue One"

        # 5. HTML Resolution for JIRA-101 in Workspace 1 -> 308 Permanent Redirect
        res_html = await client.get(
            "/api/v1/issues/JIRA-101",
            headers={"Accept": "text/html"},
        )
        assert res_html.status_code == 308
        assert res_html.headers.get("Location") == "/projects/CORE/issues/CORE-1"
        assert res_html.headers.get("X-Kanban-Canonical-Key") == "CORE-1"

        # 6. JSON Resolution for other aliases in Workspace 1
        for alias_key in ("ENG-42", "GH-88", "KANBA-123"):
            r = await client.get(
                f"/api/v1/issues/{alias_key}",
                headers={"Accept": "application/json"},
            )
            assert r.status_code == 200
            assert r.headers.get("X-Kanban-Canonical-Key") == "CORE-1"

        # 7. Entity resolve endpoint (/api/v1/resolve)
        res_resolve = await client.get("/api/v1/resolve?kind=issue&ref=JIRA-101")
        assert res_resolve.status_code == 200
        assert res_resolve.headers.get("X-Kanban-Canonical-Key") == "CORE-1"
        resolve_data = res_resolve.json()
        assert resolve_data["canonical_key"] == "CORE-1"
        assert resolve_data["id"] == str(issue_id)

        # 7b. Direct ResolutionService and resolve_issue_ref unit assertions
        rec = await resolve_issue_ref(db_session, principal_1, "KANBA-123")
        assert rec.id == issue_id
        rec_linear = await resolve_issue_ref(db_session, principal_1, "ENG-42")
        assert rec_linear.id == issue_id
        rec_uuid = await resolve_issue_ref(db_session, principal_1, str(issue_id))
        assert rec_uuid.id == issue_id
        rec_canon = await resolve_issue_ref(db_session, principal_1, "CORE-1")
        assert rec_canon.id == issue_id
        with pytest.raises(ProblemException):
            await resolve_issue_ref(db_session, principal_1, "DOES-NOT-EXIST-999")

        direct_resolver = ResolutionService()
        for test_key in ("KANBA-123", "JIRA-101", "GH-88", "ENG-42"):
            resolved = await direct_resolver.resolve(
                session=db_session,
                kind="issue",
                ref=test_key,
                caller_workspace_id=ws1_id,
                caller_principal_id=admin1_id,
            )
            assert resolved is not None
            assert resolved.kind == "issue"
            assert resolved.id == issue_id
            assert resolved.canonical_key == "CORE-1"
            assert resolved.is_alias is True

        canonical_res = await direct_resolver.resolve(
            session=db_session,
            kind="issue",
            ref="CORE-1",
            caller_workspace_id=ws1_id,
            caller_principal_id=admin1_id,
        )
        assert canonical_res is not None
        assert canonical_res.id == issue_id
        assert canonical_res.is_alias is False

        # 8. Cross-Workspace RLS Isolation: Switch principal and GUC to Workspace 2
        resolver_wrapper.principal = principal_2
        await db_session.execute(
            text(
                "SELECT set_config('app.principal_id', :pid, true), "
                "set_config('app.workspace_id', :ws, true), "
                "set_config('app.current_principal_id', :pid, true), "
                "set_config('app.current_workspace_id', :ws, true), "
                "set_config('app.aal_level', '2', true)"
            ),
            {"ws": str(ws2_id), "pid": str(admin2_id)},
        )

        # In Workspace 2, JIRA-101 must return 404 Not Found
        res_ws2_alias = await client.get(
            "/api/v1/issues/JIRA-101",
            headers={"Accept": "application/json"},
        )
        assert res_ws2_alias.status_code == 404

        # Canonical CORE-1 must also return 404 in Workspace 2
        res_ws2_canon = await client.get(
            "/api/v1/issues/CORE-1",
            headers={"Accept": "application/json"},
        )
        assert res_ws2_canon.status_code == 404

        # Entity resolve endpoint also returns 404
        res_ws2_resolve = await client.get("/api/v1/resolve?kind=issue&ref=JIRA-101")
        assert res_ws2_resolve.status_code == 404
