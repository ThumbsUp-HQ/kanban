# Copyright 2026 Kanban Platform Contributors
"""Clean-DB integration tests for /api/v1/resolve and ResolutionService (S11.1)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text

from database.session import RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import (
    ProblemException,
    problem_exception_handler,
    validation_exception_handler,
)
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1.resolve import resolve_router
from kanban.resolve import KindProvider, ResolutionService, ResolvedRef
from kanban.resolve.service import StubHookProvider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class _TestPrincipalResolver:
    """Configurable principal resolver for testing."""

    def __init__(self, principal: PrincipalContext) -> None:
        self.principal = principal

    async def resolve(self, request: Any) -> PrincipalContext | None:  # noqa: ANN401
        del request
        return self.principal


def _build_test_app(
    principal: PrincipalContext,
    session_factory: RLSSessionFactory,
    service: ResolutionService | None = None,
) -> FastAPI:
    """Construct FastAPI application with resolve_router and dependencies wired."""
    app = FastAPI(title="Resolve Test API")
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

    app.state.principal_resolver = _TestPrincipalResolver(principal)
    app.state.session_factory = session_factory
    app.state.resolution_service = service or ResolutionService()

    app.include_router(resolve_router, prefix="/api/v1")
    return app


async def _seed_test_data(
    session: AsyncSession,
) -> dict[str, Any]:
    """Seed comprehensive workspace, user, project, states, cycle, module, and issues."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Resolution Workspace"},
    )

    # Seed User 1 (Adam)
    adam_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws, 'Adam')"
        ),
        {"id": adam_id, "ws": ws_id},
    )
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws, NULL::uuid, "
            ":ckey, 'Adam', :creator, :id)"
        ),
        {"ws": ws_id, "ckey": f"usr-{adam_id.hex[:8]}", "creator": adam_id, "id": adam_id},
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws, 'adam@example.com')"),
        {"id": adam_id, "ws": ws_id},
    )

    # Seed User 2 (Bob in different workspace for cross-tenant isolation test)
    ws_other_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_other_id, "slug": f"ws-{ws_other_id.hex[:10]}", "name": "Other Workspace"},
    )
    bob_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws, 'Bob')"
        ),
        {"id": bob_id, "ws": ws_other_id},
    )
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws, NULL::uuid, "
            ":ckey, 'Bob', :creator, :id)"
        ),
        {"ws": ws_other_id, "ckey": f"usr-{bob_id.hex[:8]}", "creator": bob_id, "id": bob_id},
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws, 'bob@example.com')"),
        {"id": bob_id, "ws": ws_other_id},
    )

    # Seed Project KAN
    kan_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('project'::object_kind, :ws, NULL::uuid, "
            "'KAN', 'Kanban Core', :creator, :id)"
        ),
        {"ws": ws_id, "creator": adam_id, "id": kan_id},
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, modules_enabled) "
            "VALUES (:id, :ws, 'KAN', 'Kanban Core', true)"
        ),
        {"id": kan_id, "ws": ws_id},
    )

    # Project SEC (modules disabled)
    sec_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('project'::object_kind, :ws, NULL::uuid, "
            "'SEC', 'Security Hardening', :creator, :id)"
        ),
        {"ws": ws_id, "creator": adam_id, "id": sec_id},
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, modules_enabled) "
            "VALUES (:id, :ws, 'SEC', 'Security Hardening', false)"
        ),
        {"id": sec_id, "ws": ws_id},
    )

    # Workflow state In Progress
    in_prog_row = await session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p AND name = 'In Progress'"),
        {"p": kan_id},
    )
    in_prog_id = in_prog_row.scalar_one()

    # Priorities
    prio_row = await session.execute(
        text("SELECT id FROM project_priorities WHERE project_id = :p AND is_default = true"),
        {"p": kan_id},
    )
    prio_id = prio_row.scalar_one()

    # Cycle 4 in KAN
    cycle_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('cycle'::object_kind, :ws, :proj, "
            "'c-4', 'Cycle 4', :creator, :id)"
        ),
        {"ws": ws_id, "proj": kan_id, "creator": adam_id, "id": cycle_id},
    )
    await session.execute(
        text(
            "INSERT INTO cycles (id, workspace_id, project_id, name, status) "
            "VALUES (:id, :ws, :proj, 'Cycle 4', 'active')"
        ),
        {"id": cycle_id, "ws": ws_id, "proj": kan_id},
    )

    # Module Auth in KAN
    mod_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('module'::object_kind, :ws, :proj, "
            "'m-auth', 'Auth Engine', :creator, :id)"
        ),
        {"ws": ws_id, "proj": kan_id, "creator": adam_id, "id": mod_id},
    )
    await session.execute(
        text(
            "INSERT INTO modules (id, workspace_id, project_id, name) "
            "VALUES (:id, :ws, :proj, 'Auth Engine')"
        ),
        {"id": mod_id, "ws": ws_id, "proj": kan_id},
    )

    # Project labels in KAN
    label_sec_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO project_labels (id, workspace_id, project_id, name, color_hex) "
            "VALUES (:id, :ws, :proj, 'security', '#ff0000')"
        ),
        {"id": label_sec_id, "ws": ws_id, "proj": kan_id},
    )

    # Labels with same case-insensitive name: 'Bug' and 'bug'
    label_bug1_id = uuid.uuid4()
    label_bug2_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO project_labels (id, workspace_id, project_id, name, color_hex) "
            "VALUES (:id1, :ws, :proj, 'Bug', '#00ff00'), (:id2, :ws, :proj, 'bug', '#0000ff')"
        ),
        {"id1": label_bug1_id, "id2": label_bug2_id, "ws": ws_id, "proj": kan_id},
    )

    # Seed 7 labels with matching prefix for candidate capping test
    candidate_ids = []
    for i in range(1, 8):
        c_id = uuid.uuid4()
        candidate_ids.append(c_id)
        await session.execute(
            text(
                "INSERT INTO project_labels (id, workspace_id, project_id, name, color_hex) "
                "VALUES (:id, :ws, :proj, :name, '#cccccc')"
            ),
            {"id": c_id, "ws": ws_id, "proj": kan_id, "name": f"dup-label-{i}"},
        )

    # Issue KAN-142
    seq_142 = 142
    iss_142_id = uuid.uuid4()
    await session.execute(
        text("UPDATE projects SET issue_seq_counter = 142 WHERE id = :id"),
        {"id": kan_id},
    )
    await session.execute(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, "
            "'KAN-142', 'Target Issue', :creator, :id)"
        ),
        {"ws": ws_id, "proj": kan_id, "creator": adam_id, "id": iss_142_id},
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
            "state_id, priority_id, summary, created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, :seq, :st, :pr, 'Target Issue', :creator, '0|hzzzzz:')"
        ),
        {
            "id": iss_142_id,
            "ws": ws_id,
            "proj": kan_id,
            "seq": seq_142,
            "st": in_prog_id,
            "pr": prio_id,
            "creator": adam_id,
        },
    )

    # Bind Adam as MEMBER on project KAN and VIEWER on SEC
    await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws, :p, 'MEMBER', 'project', :proj)"
        ),
        {"ws": ws_id, "p": adam_id, "proj": kan_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws, :p, 'VIEWER', 'project', :proj)"
        ),
        {"ws": ws_id, "p": adam_id, "proj": sec_id},
    )
    await session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws)"),
        {"ws": ws_id},
    )

    return {
        "ws_id": ws_id,
        "adam_id": adam_id,
        "bob_id": bob_id,
        "kan_id": kan_id,
        "sec_id": sec_id,
        "in_prog_id": in_prog_id,
        "cycle_id": cycle_id,
        "mod_id": mod_id,
        "label_sec_id": label_sec_id,
        "label_bug1_id": label_bug1_id,
        "label_bug2_id": label_bug2_id,
        "candidate_ids": candidate_ids,
        "iss_142_id": iss_142_id,
    }


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_case_1_positive_resolutions(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Test Case 1: Positive lookups for project, issue, state, user, cycle, label, me, and UUID."""
    data = await _seed_test_data(committed_db_session)
    await committed_db_session.commit()

    factory = RLSSessionFactory(pg_worker_db)
    principal = PrincipalContext(principal_id=data["adam_id"], workspace_id=data["ws_id"])
    app = _build_test_app(principal, factory)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Project KAN
        r = await client.get("/api/v1/resolve?kind=project&ref=KAN")
        assert r.status_code == 200
        assert r.json() == {
            "id": str(data["kan_id"]),
            "kind": "project",
            "key": "KAN",
            "title": "Kanban Core",
        }

        # Issue KAN-142
        r = await client.get("/api/v1/resolve?kind=issue&ref=KAN-142")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["iss_142_id"])
        assert r.json()["key"] == "KAN-142"

        # State 'In Progress' in KAN
        r = await client.get("/api/v1/resolve?kind=state&ref=In%20Progress&project=KAN")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["in_prog_id"])
        assert r.json()["title"] == "In Progress"

        # User @adam
        r = await client.get("/api/v1/resolve?kind=user&ref=@adam")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["adam_id"])
        assert r.json()["title"] == "Adam"

        # Capture contract sample proof (200, 404, 409)
        r_404 = await client.get("/api/v1/resolve?kind=issue&ref=KAN-9999")
        r_409 = await client.get("/api/v1/resolve?kind=label&ref=bug&project=KAN")
        sample_path = Path("docs/qa/KANBA-69/contract-sample.json")
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_text(  # noqa: ASYNC240
            json.dumps(
                {
                    "resolve_200_success": {
                        "status": 200,
                        "body": {
                            "id": str(data["kan_id"]),
                            "kind": "project",
                            "key": "KAN",
                            "title": "Kanban Core",
                        },
                    },
                    "resolve_404_not_found": {
                        "status": r_404.status_code,
                        "body": r_404.json(),
                    },
                    "resolve_409_ambiguous_identifier": {
                        "status": r_409.status_code,
                        "body": r_409.json(),
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        # User 'me' resolves to caller
        r = await client.get("/api/v1/resolve?kind=user&ref=me")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["adam_id"])

        # Cycle 'Cycle 4' in KAN
        r = await client.get("/api/v1/resolve?kind=cycle&ref=Cycle%204&project=KAN")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["cycle_id"])

        # Label 'security' in KAN
        r = await client.get("/api/v1/resolve?kind=label&ref=security&project=KAN")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["label_sec_id"])

        # UUID direct lookup
        r = await client.get(f"/api/v1/resolve?kind=project&ref={data['kan_id']}")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["kan_id"])


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_case_2_security_cross_tenant_and_sanitization(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Test Case 2: 404 on cross-workspace, 404 on non-existent, and 422 on control chars."""
    data = await _seed_test_data(committed_db_session)
    await committed_db_session.commit()

    factory = RLSSessionFactory(pg_worker_db)
    principal = PrincipalContext(principal_id=data["adam_id"], workspace_id=data["ws_id"])
    app = _build_test_app(principal, factory)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Cross-workspace user @bob in another workspace returns 404
        r_bob = await client.get("/api/v1/resolve?kind=user&ref=@bob")
        assert r_bob.status_code == 404
        assert r_bob.headers.get("content-type") == "application/problem+json"

        r_nonexistent_user = await client.get("/api/v1/resolve?kind=user&ref=@nonexistent")
        assert r_nonexistent_user.status_code == 404
        assert r_bob.json()["code"] == r_nonexistent_user.json()["code"] == "NOT_FOUND"

        # Missing issue returns 404
        r_iss = await client.get("/api/v1/resolve?kind=issue&ref=KAN-9999")
        assert r_iss.status_code == 404
        assert r_iss.json()["code"] == "NOT_FOUND"

        # ref containing null byte or control character returns 422
        r_ctrl = await client.get("/api/v1/resolve?kind=project&ref=KAN%00HACK")
        assert r_ctrl.status_code == 422
        assert r_ctrl.json()["code"] == "VALIDATION_FAILED"


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_case_3_ambiguity_and_boundaries(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Test Case 3: 409 ambiguity with candidates, 201-char 422, modules disabled."""
    data = await _seed_test_data(committed_db_session)
    await committed_db_session.commit()

    factory = RLSSessionFactory(pg_worker_db)
    principal = PrincipalContext(principal_id=data["adam_id"], workspace_id=data["ws_id"])
    app = _build_test_app(principal, factory)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Ambiguity between 'Bug' and 'bug' in KAN -> 409 AMBIGUOUS_IDENTIFIER with 2 candidates
        r_amb = await client.get("/api/v1/resolve?kind=label&ref=bug&project=KAN")
        assert r_amb.status_code == 409
        body = r_amb.json()
        assert body["code"] == "AMBIGUOUS_IDENTIFIER"
        assert "candidates" in body
        assert len(body["candidates"]) == 2

        # 7 matches capped at exactly 5 candidates
        # Register custom provider returning 7 matches to verify cap
        class SevenMatchProvider(KindProvider):
            async def resolve(
                self,
                session: AsyncSession,
                ref: str,
                *,
                project_id: uuid.UUID | None = None,
                workspace_id: uuid.UUID | None = None,
            ) -> list[ResolvedRef]:
                del session, ref, project_id, workspace_id
                return [
                    ResolvedRef(id=uuid.uuid4(), kind="test", key=f"k-{i}", title=f"Match {i}")
                    for i in range(7)
                ]

        svc_capped = ResolutionService()
        svc_capped.register_provider("capped", SevenMatchProvider())
        app_capped = _build_test_app(principal, factory, service=svc_capped)
        transport_capped = httpx.ASGITransport(app=app_capped)

        async with httpx.AsyncClient(
            transport=transport_capped, base_url="http://test"
        ) as c_capped:
            r_7 = await c_capped.get("/api/v1/resolve?kind=capped&ref=multi")
            assert r_7.status_code == 409
            assert len(r_7.json()["candidates"]) == 5

        # Ref length of 201 chars -> 422
        long_ref = "A" * 201
        r_long = await client.get(f"/api/v1/resolve?kind=project&ref={long_ref}")
        assert r_long.status_code == 422
        assert r_long.json()["code"] == "VALIDATION_FAILED"

        # Module on project with modules_enabled=false -> MODULES_DISABLED
        r_mod = await client.get("/api/v1/resolve?kind=module&ref=Core&project=SEC")
        assert r_mod.status_code == 422
        assert r_mod.json()["code"] == "MODULES_DISABLED"

        # State lookup without project parameter -> VALIDATION_FAILED
        r_state_no_proj = await client.get("/api/v1/resolve?kind=state&ref=Todo")
        assert r_state_no_proj.status_code == 422
        assert r_state_no_proj.json()["code"] == "VALIDATION_FAILED"
        assert "pass project=" in r_state_no_proj.json()["detail"]


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_hook_provider_stub(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Verify hook provider stub is registered and callable."""
    data = await _seed_test_data(committed_db_session)
    await committed_db_session.commit()

    factory = RLSSessionFactory(pg_worker_db)
    principal = PrincipalContext(principal_id=data["adam_id"], workspace_id=data["ws_id"])
    app = _build_test_app(principal, factory)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/resolve?kind=hook&ref=my-hook")
        assert r.status_code == 404
        assert r.json()["code"] == "NOT_FOUND"


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_comprehensive_resolution_branches(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Exercise all per-kind branch paths (name matching, email, UUIDs, not-found paths)."""
    data = await _seed_test_data(committed_db_session)
    await committed_db_session.commit()

    factory = RLSSessionFactory(pg_worker_db)
    principal = PrincipalContext(principal_id=data["adam_id"], workspace_id=data["ws_id"])
    app = _build_test_app(principal, factory)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Project by case-insensitive name
        r = await client.get("/api/v1/resolve?kind=project&ref=kanban%20core")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["kan_id"])

        # Project by unknown UUID -> 404
        r = await client.get(f"/api/v1/resolve?kind=project&ref={uuid.uuid4()}")
        assert r.status_code == 404

        # Issue by UUID -> 200
        r = await client.get(f"/api/v1/resolve?kind=issue&ref={data['iss_142_id']}")
        assert r.status_code == 200
        assert r.json()["key"] == "KAN-142"

        # Issue by unknown UUID -> 404
        r = await client.get(f"/api/v1/resolve?kind=issue&ref={uuid.uuid4()}")
        assert r.status_code == 404

        # Issue by invalid key syntax -> 404
        r = await client.get("/api/v1/resolve?kind=issue&ref=KAN_142")
        assert r.status_code == 404

        # User by email -> 200
        r = await client.get("/api/v1/resolve?kind=user&ref=adam@example.com")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["adam_id"])

        # User by display name -> 200
        r = await client.get("/api/v1/resolve?kind=user&ref=Adam")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["adam_id"])

        # User by UUID -> 200
        r = await client.get(f"/api/v1/resolve?kind=user&ref={data['adam_id']}")
        assert r.status_code == 200

        # User by unknown UUID -> 404
        r = await client.get(f"/api/v1/resolve?kind=user&ref={uuid.uuid4()}")
        assert r.status_code == 404

        # State by UUID -> 200
        r = await client.get(f"/api/v1/resolve?kind=state&ref={data['in_prog_id']}&project=KAN")
        assert r.status_code == 200

        # State by unknown UUID -> 404
        r = await client.get(f"/api/v1/resolve?kind=state&ref={uuid.uuid4()}&project=KAN")
        assert r.status_code == 404

        # Cycle by UUID -> 200
        r = await client.get(f"/api/v1/resolve?kind=cycle&ref={data['cycle_id']}&project=KAN")
        assert r.status_code == 200

        # Cycle by unknown UUID -> 404
        r = await client.get(f"/api/v1/resolve?kind=cycle&ref={uuid.uuid4()}&project=KAN")
        assert r.status_code == 404

        # Module by name in KAN -> 200
        r = await client.get("/api/v1/resolve?kind=module&ref=Auth%20Engine&project=KAN")
        assert r.status_code == 200
        assert r.json()["id"] == str(data["mod_id"])

        # Module by UUID in KAN -> 200
        r = await client.get(f"/api/v1/resolve?kind=module&ref={data['mod_id']}&project=KAN")
        assert r.status_code == 200

        # Module by unknown UUID in KAN -> 404
        r = await client.get(f"/api/v1/resolve?kind=module&ref={uuid.uuid4()}&project=KAN")
        assert r.status_code == 404

        # Label by UUID -> 200
        r = await client.get(f"/api/v1/resolve?kind=label&ref={data['label_sec_id']}&project=KAN")
        assert r.status_code == 200

        # Label by unknown UUID -> 404
        r = await client.get(f"/api/v1/resolve?kind=label&ref={uuid.uuid4()}&project=KAN")
        assert r.status_code == 404


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_comprehensive_resolution_missing_context(
    pg_worker_db: AsyncEngine,
    committed_db_session: AsyncSession,
) -> None:
    """Verify 422 on missing required project context or unsupported kind."""
    data = await _seed_test_data(committed_db_session)
    await committed_db_session.commit()

    factory = RLSSessionFactory(pg_worker_db)
    principal = PrincipalContext(principal_id=data["adam_id"], workspace_id=data["ws_id"])
    app = _build_test_app(principal, factory)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Cycle without project context -> 422
        r = await client.get("/api/v1/resolve?kind=cycle&ref=Cycle%204")
        assert r.status_code == 422

        # Module without project context -> 422
        r = await client.get("/api/v1/resolve?kind=module&ref=Auth%20Engine")
        assert r.status_code == 422

        # Label without project context -> 422
        r = await client.get("/api/v1/resolve?kind=label&ref=security")
        assert r.status_code == 422

        # Unsupported kind -> 422
        r = await client.get("/api/v1/resolve?kind=unknown_kind&ref=foo")
        assert r.status_code == 422


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_service_direct_edge_cases(
    committed_db_session: AsyncSession,
) -> None:
    """Directly test ResolutionService edge cases (caller None, direct unhandled kind)."""
    svc = ResolutionService()

    # Register provider coverage
    class DummyHookProvider(KindProvider):
        async def resolve(
            self,
            session: AsyncSession,
            ref: str,
            *,
            project_id: uuid.UUID | None = None,
            workspace_id: uuid.UUID | None = None,
        ) -> list[ResolvedRef]:
            del session, ref, project_id, workspace_id
            return []

    svc.register_provider("custom_hook", DummyHookProvider())

    # User 'me' when caller_principal_id is None -> ProblemException 404
    with pytest.raises(ProblemException) as exc_info:
        await svc.resolve(
            committed_db_session,
            kind="user",
            ref="me",
            caller_principal_id=None,
        )
    assert exc_info.value.status == 404

    # User 'me' when caller_principal_id does not exist -> ProblemException 404
    with pytest.raises(ProblemException) as exc_info2:
        await svc.resolve(
            committed_db_session,
            kind="user",
            ref="me",
            caller_principal_id=uuid.uuid4(),
        )
    assert exc_info2.value.status == 404

    # StubHookProvider add_stub and resolve
    hook_provider = StubHookProvider()
    hook_id = uuid.uuid4()
    stub_ref = ResolvedRef(id=hook_id, kind="hook", key="pre_commit", title="Pre-commit hook")
    hook_provider.add_stub("pre_commit", stub_ref)
    svc.register_provider("hook", hook_provider)
    resolved_hook = await svc.resolve(committed_db_session, kind="hook", ref="pre_commit")
    assert resolved_hook.id == hook_id
    assert resolved_hook.key == "pre_commit"

    # Unsupported kind direct call raises ProblemException with 422
    with pytest.raises(ProblemException) as exc_unsupported:
        await svc.resolve(committed_db_session, kind="non_existent", ref="test")
    assert exc_unsupported.value.status == 422

    # Project ref matching identifier regex but not matching any identifier (falls through to name)
    with pytest.raises(ProblemException) as exc_p:
        await svc.resolve(committed_db_session, kind="project", ref="ZZZ", caller_workspace_id=None)
    assert exc_p.value.status == 404
