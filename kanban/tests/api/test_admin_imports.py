# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and security tests for Admin Imports REST API (KB-P6-01, S1.3, S15.5)."""

# ruff: noqa: E501, PLR0915, PLC0415

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.auth.mfa.policy import assert_admin_routes_protected
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    PRE_SESSION_ID,
    CsrfMiddleware,
    generate_csrf_token,
)
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.importer.plane_importer import ImportIntegrityError
from kanban.security.keys import KeyMaterial

FIXTURE_DIR = Path("tests/fixtures/plane_export_kanba").resolve()


@pytest.fixture
def key_material() -> KeyMaterial:
    """Fixture providing testing key material."""
    return KeyMaterial(
        master_kek=b"k" * 32,
        master_kek_kid="kek-v1",
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )


async def _setup_workspace_and_principals(
    engine: AsyncEngine,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision workspace, SERVER_ADMIN, and WORKSPACE_ADMIN principals with enrolled TOTP."""
    ws_id = uuid.uuid4()
    async with AsyncSession(engine) as session:
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Admin Imports WS"},
        )

        # 1. Server Admin
        server_admin_id = uuid.uuid4()
        await session.execute(
            text(
                "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {
                "ws_id": ws_id,
                "ckey": f"usr-{server_admin_id.hex}",
                "title": "Server Admin",
                "u_id": server_admin_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Server Admin', 'ACTIVE')"
            ),
            {"id": server_admin_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'server-admin@example.com')"
            ),
            {"id": server_admin_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :pid, 'SERVER_ADMIN', 'server', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "pid": server_admin_id},
        )

        # 2. Workspace Admin (non-server admin)
        workspace_admin_id = uuid.uuid4()
        await session.execute(
            text(
                "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {
                "ws_id": ws_id,
                "ckey": f"usr-{workspace_admin_id.hex}",
                "title": "Workspace Admin",
                "u_id": workspace_admin_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Workspace Admin', 'ACTIVE')"
            ),
            {"id": workspace_admin_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'workspace-admin@example.com')"
            ),
            {"id": workspace_admin_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :pid, 'WORKSPACE_ADMIN', 'workspace', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "pid": workspace_admin_id},
        )

        # Register and confirm MFA TOTP for both administrators to satisfy require_admin_aal2
        for p_id in (server_admin_id, workspace_admin_id):
            await session.execute(
                text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
                {
                    "p_id": p_id,
                    "blob": b"\x01" + b"\x00" * 28,
                    "dek": b"\x01" + b"\x00" * 44,
                },
            )
            res = await session.execute(
                text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
                {"p_id": p_id},
            )
            p_row = res.mappings().first()
            if p_row:
                await session.execute(
                    text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
                    {"p_fid": p_row["id"]},
                )

        await session.commit()
    return ws_id, server_admin_id, workspace_admin_id


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_admin_imports_security_and_execution(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Case 4 & API: AAL2 enforcement, SERVER_ADMIN gate, path traversal, dry-run & live apply."""
    factory = RLSSessionFactory(pg_worker_db)
    ws_id, server_admin_id, workspace_admin_id = await _setup_workspace_and_principals(pg_worker_db)

    imports_dir = tmp_path / "imports_storage"
    imports_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("KANBAN_IMPORTS_DIR", str(imports_dir))

    # Copy fixture bundle into imports storage as "plane-kanba"
    bundle_target = imports_dir / "plane-kanba"
    shutil.copytree(FIXTURE_DIR, bundle_target)

    # Build FastAPI test application
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CsrfMiddleware,
        session_hmac_key=key_material.session_hmac_key,
    )
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    v1_router = build_v1_router()
    app.include_router(v1_router, prefix="/api/v1")

    session_service = SessionService(key_material.session_hmac_key)
    cookie_resolver = SessionCookieResolver(session_service, factory)

    app.state.session_factory = factory
    app.state.principal_resolver = cookie_resolver
    app.state.session_service = session_service

    # Route audit: assert all admin routes require require_admin_aal2
    unprotected = assert_admin_routes_protected(app)
    assert unprotected == []

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated -> 401
        pre_csrf = generate_csrf_token(PRE_SESSION_ID, key_material.session_hmac_key)
        client.cookies.set(CSRF_COOKIE_NAME, pre_csrf)
        res_anon = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "plane-kanba", "dry_run": True},
            headers={CSRF_HEADER_NAME: pre_csrf},
        )
        assert res_anon.status_code == 401

        # 2. AAL1 SERVER_ADMIN -> 403 AAL2_REQUIRED
        async with factory.session(anon_ctx) as sess:
            sess_aal1 = await session_service.create_after_login(
                sess,
                principal_id=server_admin_id,
                workspace_id=ws_id,
                aal_level=1,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal1.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal1.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_aal1.csrf_token

        res_aal1 = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "plane-kanba", "dry_run": True},
        )
        assert res_aal1.status_code == 403
        assert res_aal1.json()["code"] in ("AAL2_REQUIRED", "MFA_ENROLLMENT_REQUIRED")

        # 3. AAL2 PROJECT_ADMIN (not SERVER_ADMIN) -> 403 INSUFFICIENT_CAPABILITY
        async with factory.session(anon_ctx) as sess:
            sess_proj_admin = await session_service.create_after_login(
                sess,
                principal_id=workspace_admin_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_proj_admin.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_proj_admin.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_proj_admin.csrf_token

        res_proj = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "plane-kanba", "dry_run": True},
        )
        assert res_proj.status_code == 403
        assert res_proj.json()["code"] == "INSUFFICIENT_CAPABILITY"

        # 4. AAL2 SERVER_ADMIN
        async with factory.session(anon_ctx) as sess:
            sess_server_admin = await session_service.create_after_login(
                sess,
                principal_id=server_admin_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_server_admin.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_server_admin.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_server_admin.csrf_token

        # 4a. Path traversal: ../../etc -> 422
        res_trav1 = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "../../etc"},
        )
        assert res_trav1.status_code == 422
        assert res_trav1.json()["code"] == "PATH_TRAVERSAL_DETECTED"

        # 4b. Path traversal: foo/bar -> 422
        res_trav2 = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "foo/bar"},
        )
        assert res_trav2.status_code == 422

        # 4c. Nonexistent bundle -> 404
        res_notfound = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "nonexistent-bundle"},
        )
        assert res_notfound.status_code == 404
        assert res_notfound.json()["code"] == "BUNDLE_NOT_FOUND"

        # 4d. Dry-run preview -> 200 ImportDiffReport
        res_preview = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "plane-kanba", "dry_run": True},
        )
        assert res_preview.status_code == 200
        preview_data = res_preview.json()
        assert preview_data["to_create"] > 0
        assert preview_data["sequence_high_water_mark"] == 19
        assert preview_data["invalid_link_count"] == 0

        # 4e. Live apply -> 200 ImportDiffReport
        res_live = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "plane-kanba", "dry_run": False},
        )
        assert res_live.status_code == 200
        live_data = res_live.json()
        assert live_data["to_create"] > 0
        assert live_data["sequence_high_water_mark"] == 19

        # 4f. Idempotent re-run -> 200 unchanged
        res_rerun = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "plane-kanba", "dry_run": False},
        )
        assert res_rerun.status_code == 200
        rerun_data = res_rerun.json()
        assert rerun_data["to_create"] == 0
        assert rerun_data["unchanged"] > 0

        # 4g. Nonexistent target workspace_slug -> 404 WORKSPACE_NOT_FOUND
        res_bad_ws = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "plane-kanba", "workspace_slug": "nonexistent-slug-xyz"},
        )
        assert res_bad_ws.status_code == 404
        assert res_bad_ws.json()["code"] == "WORKSPACE_NOT_FOUND"

        # 4h. Valid target workspace_slug -> 200
        ws2_id = uuid.uuid4()
        ws2_slug = f"ws-{ws2_id.hex[:10]}"
        ws2_adm_id = uuid.uuid4()
        async with factory.session(anon_ctx) as sess:
            await sess.execute(
                text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Second WS')"),
                {"id": ws2_id, "slug": ws2_slug},
            )
            await sess.execute(
                text(
                    "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'WS2 Admin', :u_id, :u_id)"
                ),
                {"ws_id": ws2_id, "ckey": f"usr-{ws2_adm_id.hex}", "u_id": ws2_adm_id},
            )
            await sess.execute(
                text(
                    "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) VALUES (:id, 'USER', :ws_id, 'WS2 Admin', 'ACTIVE')"
                ),
                {"id": ws2_adm_id, "ws_id": ws2_id},
            )
            await sess.execute(
                text(
                    "INSERT INTO users (id, object_type, principal_type, workspace_id, email) VALUES (:id, 'user', 'USER', :ws_id, 'ws2-admin@example.com')"
                ),
                {"id": ws2_adm_id, "ws_id": ws2_id},
            )
            await sess.execute(
                text(
                    "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id) VALUES (:id, :ws_id, :pid, 'WORKSPACE_ADMIN', 'workspace', NULL)"
                ),
                {"id": uuid.uuid4(), "ws_id": ws2_id, "pid": ws2_adm_id},
            )
            await sess.commit()

        res_ws2 = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "plane-kanba", "workspace_slug": ws2_slug, "dry_run": True},
        )
        assert res_ws2.status_code == 200

        # 4i. Corrupt bundle -> 422 BUNDLE_INVALID
        corrupt_bundle_dir = imports_dir / "corrupt-bundle"
        corrupt_bundle_dir.mkdir(parents=True, exist_ok=True)
        (corrupt_bundle_dir / "projects.json").write_text("{corrupt json", encoding="utf-8")
        res_corrupt = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_name": "corrupt-bundle"},
        )
        assert res_corrupt.status_code == 422
        assert res_corrupt.json()["code"] == "BUNDLE_INVALID"

        # 4k. Direct bundle_data JSON dictionary payload -> 200
        sample_bundle = {
            "projects": [{"id": str(uuid.uuid4()), "identifier": "IMP", "name": "Imported"}],
            "states": [{"id": str(uuid.uuid4()), "name": "Backlog", "group": "backlog"}],
            "issues": [],
        }
        res_data = await client.post(
            "/api/v1/admin/imports/plane",
            json={"bundle_data": sample_bundle, "dry_run": True},
        )
        assert res_data.status_code == 200
        assert res_data.json()["to_create"] >= 0

        # 4l. Missing both bundle_name and bundle_data -> 422 BUNDLE_REQUIRED
        res_none = await client.post(
            "/api/v1/admin/imports/plane",
            json={"dry_run": True},
        )
        assert res_none.status_code == 422
        assert res_none.json()["code"] == "BUNDLE_REQUIRED"

        # 4m. ImportIntegrityError -> 422 IMPORT_INTEGRITY_FAILED
        with patch(
            "kanban.api.v1.admin.imports.PlaneImporter.run_import",
            side_effect=ImportIntegrityError("Integrity breached"),
        ):
            res_integrity = await client.post(
                "/api/v1/admin/imports/plane",
                json={"bundle_name": "plane-kanba"},
            )
            assert res_integrity.status_code == 422
            assert res_integrity.json()["code"] == "IMPORT_INTEGRITY_FAILED"

        # 4k. Generic Exception -> 500 IMPORT_EXECUTION_ERROR
        with patch(
            "kanban.api.v1.admin.imports.PlaneImporter.run_import",
            side_effect=RuntimeError("DB exploded"),
        ):
            res_error = await client.post(
                "/api/v1/admin/imports/plane",
                json={"bundle_name": "plane-kanba"},
            )
            assert res_error.status_code == 500
            assert res_error.json()["code"] == "IMPORT_EXECUTION_ERROR"


def test_resolve_bundle_path_escape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test _resolve_bundle_path escapes allowed directory via symlink."""
    from kanban.api.v1.admin.imports import _resolve_bundle_path

    imports_dir = tmp_path / "imports"
    imports_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    escape_link = imports_dir / "escaped"
    escape_link.symlink_to(outside_dir)

    monkeypatch.setenv("KANBAN_IMPORTS_DIR", str(imports_dir))
    with pytest.raises(ProblemException) as exc_info:
        _resolve_bundle_path("escaped")
    assert exc_info.value.code == "PATH_TRAVERSAL_DETECTED"
