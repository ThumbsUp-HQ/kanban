# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLC0415, S106
"""Integration and unit tests for System Status, Encrypted Backup, and Compose Export (KB-P3-52)."""

from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from database.session import RLSSessionFactory
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.app import create_app
from kanban.auth.mfa.policy import assert_admin_routes_protected
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.ops.build_info import resolve_platform_version
from kanban.security.keys import KeyMaterial
from kanban.settings import Settings
from kanban.standalone.export_service import (
    BackupError,
    RestoreError,
    decrypt_backup,
    encrypt_backup,
    get_standalone_status,
    run_pg_dump,
)


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
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision workspace, SERVER_ADMIN, and regular PROJECT_ADMIN / MEMBER principals."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "System Status WS"},
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
            "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": server_admin_id},
    )
    await session.execute(
        text(
            "INSERT INTO local_admin_credentials (principal_id, username, password_hash) "
            "VALUES (:p_id, :username, '$argon2id$v=19$m=65536,t=3,p=4$fakehash$fakehash')"
        ),
        {"p_id": server_admin_id, "username": f"admin-{server_admin_id.hex[:8]}"},
    )

    # 2. Member User (Non-server admin)
    member_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{member_id.hex}",
            "title": "Member User",
            "u_id": member_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Member User', 'ACTIVE')"
        ),
        {"id": member_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'member@example.com')"
        ),
        {"id": member_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_MEMBER', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": member_id},
    )

    # Register MFA TOTP for server_admin to satisfy require_admin_aal2
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
        {
            "p_id": server_admin_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await session.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": server_admin_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )

    # Default session RLS context to server admin AAL2
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(server_admin_id), "w_id": str(ws_id)},
    )

    return ws_id, server_admin_id, member_id


async def _add_workspace_admin(
    session: AsyncSession,
    ws_id: uuid.UUID,
) -> uuid.UUID:
    """Provision a WORKSPACE_ADMIN principal with enrolled MFA."""
    ws_admin_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{ws_admin_id.hex}",
            "title": "Workspace Admin",
            "u_id": ws_admin_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Workspace Admin', 'ACTIVE')"
        ),
        {"id": ws_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'ws-admin@example.com')"
        ),
        {"id": ws_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": ws_admin_id},
    )
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
        {
            "p_id": ws_admin_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await session.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": ws_admin_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    return ws_admin_id


def _create_test_app(
    factory: RLSSessionFactory,
    key_material: KeyMaterial,
    session_service: SessionService,
) -> FastAPI:
    """Instantiate configured FastAPI application with test dependencies."""
    app = FastAPI()
    app.state.session_factory = factory
    app.state.session_service = session_service
    app.state.key_material = key_material

    resolver = SessionCookieResolver(
        session_service=session_service,
        session_factory=factory,
    )
    app.state.principal_resolver = resolver

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(CsrfMiddleware)
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    v1_router = build_v1_router()
    app.include_router(v1_router, prefix="/api/v1")
    return app


async def _login_and_elevate(  # noqa: PLR0913, PLR0917
    client: httpx.AsyncClient,
    session_service: SessionService,
    db_session: AsyncSession,
    principal_id: uuid.UUID,
    workspace_id: uuid.UUID,
    aal_level: int = 2,
) -> tuple[str, str]:
    """Issue authenticated session cookie and CSRF token for testing client."""
    sess = await session_service.create_after_login(
        db_session,
        principal_id=principal_id,
        workspace_id=workspace_id,
        aal_level=aal_level,
    )
    client.cookies.set(SESSION_COOKIE_NAME, sess.cookie_val)
    client.cookies.set(CSRF_COOKIE_NAME, sess.csrf_token)
    return sess.cookie_val, sess.csrf_token


def _assert_admin_status(data: dict[str, Any]) -> None:
    assert data["deployment_mode"] == "standalone_embedded_pg"
    assert data["persistent_volume"] is False
    assert data["data_mount_point"] == "/var/lib/kanban/data"
    assert data["data_mount_fstype"] == "overlay"
    assert data["tier_b_sandbox_available"] is False
    assert data["supported_custom_field_tiers"] == ["scalar", "formula", "wasm"]
    assert data["sandbox_unavailable_reason"] is not None
    assert "nsjail" in data["sandbox_unavailable_reason"]
    assert data["local_llm_endpoint_host"] == "http://host.docker.internal:11434"
    assert data["is_server_admin"] is True
    assert data["git_commit"] is not None
    assert "build_timestamp" in data
    assert data["openapi_version"] == resolve_platform_version()
    assert data["version"] == resolve_platform_version()
    assert "openapi_bundle_hash" in data
    assert "frontend_bundle_hash" in data


@pytest.mark.asyncio
async def test_case_1_system_status_admin_full_fields_and_member_redaction(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 1: Reading standalone_status.json returns full fields to SERVER_ADMIN and redacts for MEMBER."""
    status_file = tmp_path / "standalone_status.json"
    status_file.write_text(
        """{
            "mode": "standalone_embedded_pg",
            "persistent_volume": false,
            "data_mount_point": "/var/lib/kanban/data",
            "data_mount_fstype": "overlay",
            "tier_b_sandbox_available": false
        }""",
        encoding="utf-8",
    )
    monkeypatch.setenv("KB_STANDALONE_STATUS_PATH", str(status_file))
    monkeypatch.setenv("KANBAN_LOCAL_LLM_HOST", "http://host.docker.internal:11434")

    ws_id, admin_id, member_id = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. As SERVER_ADMIN: full topology returned
        await _login_and_elevate(client, session_service, db_session, admin_id, ws_id, aal_level=2)
        resp_admin = await client.get("/api/v1/system/status")
        assert resp_admin.status_code == 200
        _assert_admin_status(resp_admin.json())

        # Test admin standalone status endpoint
        resp_admin_sa = await client.get("/api/v1/admin/standalone/status")
        assert resp_admin_sa.status_code == 200
        data_admin_sa = resp_admin_sa.json()
        assert data_admin_sa["tier_b_sandbox_available"] is False
        assert data_admin_sa["supported_custom_field_tiers"] == ["scalar", "formula", "wasm"]
        assert data_admin_sa["sandbox_unavailable_reason"] is not None
        assert data_admin_sa["git_commit"] is not None
        assert "build_timestamp" in data_admin_sa
        assert data_admin_sa["openapi_version"] == resolve_platform_version()
        assert data_admin_sa["version"] == resolve_platform_version()

        # 2. As regular MEMBER: sensitive host topology redacted to null
        client.cookies.clear()
        await _login_and_elevate(client, session_service, db_session, member_id, ws_id, aal_level=1)
        resp_member = await client.get("/api/v1/system/status")
        assert resp_member.status_code == 200
        data_member = resp_member.json()
        assert data_member["deployment_mode"] == "standalone_embedded_pg"
        assert data_member["persistent_volume"] is False
        assert data_member["tier_b_sandbox_available"] is False
        assert data_member["supported_custom_field_tiers"] == ["scalar", "formula", "wasm"]
        assert data_member["sandbox_unavailable_reason"] is not None
        assert data_member["data_mount_point"] is None  # Redacted
        assert data_member["data_mount_fstype"] is None  # Redacted
        assert data_member["local_llm_endpoint_host"] is None  # Redacted
        assert data_member["is_server_admin"] is False


@pytest.mark.asyncio
async def test_case_1b_missing_status_file_defaults_to_production_multi_container(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 1b: Missing or corrupted status file defaults to production_multi_container."""
    nonexistent_file = tmp_path / "absent_status.json"
    monkeypatch.setenv("KB_STANDALONE_STATUS_PATH", str(nonexistent_file))

    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _login_and_elevate(client, session_service, db_session, admin_id, ws_id, aal_level=2)
        resp = await client.get("/api/v1/system/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deployment_mode"] == "production_multi_container"
        assert data["persistent_volume"] is True
        assert data["tier_b_sandbox_available"] is True
        assert data["supported_custom_field_tiers"] == ["scalar", "formula", "wasm", "nsjail"]
        assert data["sandbox_unavailable_reason"] is None

        resp_admin_sa = await client.get("/api/v1/admin/standalone/status")
        assert resp_admin_sa.status_code == 200
        data_sa = resp_admin_sa.json()
        assert data_sa["tier_b_sandbox_available"] is True
        assert data_sa["supported_custom_field_tiers"] == ["scalar", "formula", "wasm", "nsjail"]
        assert data_sa["sandbox_unavailable_reason"] is None


@pytest.mark.asyncio
async def test_case_2_standalone_encrypted_backup_and_zero_shell(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 2: POST /api/v1/admin/standalone/backup produces valid AES-256-GCM .kbkp archive and enforces guards."""
    status_file = tmp_path / "standalone_status.json"
    status_file.write_text(
        '{"mode": "standalone_embedded_pg", "persistent_volume": true}',
        encoding="utf-8",
    )
    monkeypatch.setenv("KB_STANDALONE_STATUS_PATH", str(status_file))

    ws_id, admin_id, member_id = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    mock_dump_data = b"PG_CUSTOM_DUMP_FORMAT_OCTETS_VALID_1234567890"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, csrf_token = await _login_and_elevate(
            client, session_service, db_session, admin_id, ws_id, aal_level=2
        )

        with patch(
            "kanban.api.v1.system_status.run_pg_dump", new_callable=AsyncMock
        ) as mock_pg_dump:
            mock_pg_dump.return_value = mock_dump_data

            # 1. Successful backup with passphrase >= 16 chars
            passphrase = "correct-horse-battery-staple-passphrase"
            resp = await client.post(
                "/api/v1/admin/standalone/backup",
                json={"passphrase": passphrase},
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/octet-stream"
            assert "kanban-backup-" in resp.headers["content-disposition"]
            assert resp.headers["content-disposition"].endswith('.kbbak"')

            encrypted_bytes = resp.content
            assert encrypted_bytes.startswith(b"KBKP")

            # Decrypt with correct passphrase -> returns exact mock dump bytes
            decrypted = decrypt_backup(encrypted_bytes, passphrase=passphrase)
            assert decrypted == mock_dump_data

            # 2. Successful backup with use_master_kek
            resp_kek = await client.post(
                "/api/v1/admin/standalone/backup",
                json={"use_master_kek": True},
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_kek.status_code == 200
            decrypted_kek = decrypt_backup(resp_kek.content, master_kek=key_material.master_kek)
            assert decrypted_kek == mock_dump_data

            # 3. Reject passphrase < 16 chars (422)
            resp_short = await client.post(
                "/api/v1/admin/standalone/backup",
                json={"passphrase": "too-short"},
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_short.status_code == 422
            assert "INVALID_BACKUP_PASSPHRASE" in resp_short.text

            # 4. Reject in production_multi_container mode (409)
            with patch(
                "kanban.api.v1.system_status.get_standalone_status",
                return_value={"deployment_mode": "production_multi_container"},
            ):
                resp_not_standalone = await client.post(
                    "/api/v1/admin/standalone/backup",
                    json={"passphrase": passphrase},
                    headers={CSRF_HEADER_NAME: csrf_token},
                )
                assert resp_not_standalone.status_code == 409
                assert "NOT_STANDALONE_MODE" in resp_not_standalone.text

            # 5. Reject regular member caller (403 INSUFFICIENT_CAPABILITY)
            client.cookies.clear()
            _, member_csrf = await _login_and_elevate(
                client, session_service, db_session, member_id, ws_id, aal_level=1
            )
            resp_forbidden = await client.post(
                "/api/v1/admin/standalone/backup",
                json={"passphrase": passphrase},
                headers={CSRF_HEADER_NAME: member_csrf},
            )
            assert resp_forbidden.status_code == 403


@pytest.mark.asyncio
async def test_case_3_compose_export_secret_audit_and_network_topology(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Case 3: GET /api/v1/admin/standalone/compose-export returns valid YAML without secrets."""
    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _login_and_elevate(client, session_service, db_session, admin_id, ws_id, aal_level=2)
        resp = await client.get("/api/v1/admin/standalone/compose-export")
        assert resp.status_code == 200
        data = resp.json()

        assert data["filename"] == "docker-compose.yml"
        compose_yaml = data["compose_yaml"]

        # Network topology verification
        assert "edge_net:" in compose_yaml
        assert "app_net:" in compose_yaml
        assert "data_net:" in compose_yaml
        assert "sandbox_net:" in compose_yaml
        assert "egress_llm_net:" in compose_yaml

        # Isolation verification: mcp-server & sandbox must NOT attach to data_net
        lines = compose_yaml.splitlines()
        current_service = None
        service_networks: dict[str, list[str]] = {}
        for line in lines:
            if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
                current_service = line.strip()[:-1]
                service_networks[current_service] = []
            elif current_service and line.strip().startswith("- ") and "net" in line:
                net_name = line.strip().split("- ")[1]
                service_networks[current_service].append(net_name)

        assert "data_net" not in service_networks.get("mcp-server", [])
        assert "data_net" not in service_networks.get("sandbox", [])

        # Zero secrets verification
        assert "${POSTGRES_PASSWORD}" in compose_yaml
        assert "${MASTER_KEK}" in compose_yaml
        assert "k" * 32 not in compose_yaml
        assert "p" * 32 not in compose_yaml
        assert "s" * 32 not in compose_yaml


@pytest.mark.asyncio
async def test_case_4_backup_encryption_and_decryption_edge_cases() -> None:
    """Case 4: Test cipher envelope error branches and validation guards."""
    # 1. Missing both passphrase and master_kek
    with pytest.raises(BackupError, match="Either passphrase or master_kek"):
        encrypt_backup(b"data")

    # 2. Valid payload for subsequent corruption tests
    valid_enc = encrypt_backup(b"valid-data", passphrase="a-strong-passphrase-16+")

    # 3. Payload too short
    with pytest.raises(RestoreError, match="Payload too short"):
        decrypt_backup(b"short")

    # 4. Invalid magic header
    corrupt_magic = b"FAIL" + valid_enc[4:]
    with pytest.raises(RestoreError, match="Invalid magic header"):
        decrypt_backup(corrupt_magic, passphrase="a-strong-passphrase-16+")

    # 5. Invalid version
    corrupt_version = valid_enc[:4] + b"\x02" + valid_enc[5:]
    with pytest.raises(RestoreError, match="Unsupported backup version"):
        decrypt_backup(corrupt_version, passphrase="a-strong-passphrase-16+")

    # 6. Unknown KDF mode
    corrupt_kdf = valid_enc[:5] + b"\x99" + valid_enc[6:]
    with pytest.raises(RestoreError, match="Unknown KDF mode"):
        decrypt_backup(corrupt_kdf, passphrase="a-strong-passphrase-16+")

    # 7. Missing passphrase on PBKDF2 payload
    with pytest.raises(RestoreError, match="Passphrase required"):
        decrypt_backup(valid_enc, passphrase=None)

    # 8. Missing master_kek on HKDF payload
    valid_hkdf = encrypt_backup(b"valid-data", master_kek=b"m" * 32)
    with pytest.raises(RestoreError, match="MASTER_KEK required"):
        decrypt_backup(valid_hkdf, master_kek=None)

    # 9. Decryption failure on corrupted ciphertext / wrong passphrase
    with pytest.raises(RestoreError, match="Decryption failed"):
        decrypt_backup(valid_enc, passphrase="wrong-passphrase-16+")


@pytest.mark.asyncio
async def test_case_5_run_pg_dump_execution_and_errors() -> None:
    """Case 5: Exercise run_pg_dump binary resolution and error branches."""
    # 1. FileNotFoundError (binary missing)
    with pytest.raises(BackupError, match="pg_dump binary not found"):
        await run_pg_dump(pg_dump_bin="/nonexistent/bin/pg_dump_fake")

    # 2. Non-zero exit code
    mock_proc_fail = AsyncMock()
    mock_proc_fail.returncode = 1
    mock_proc_fail.communicate.return_value = (b"", b"connection refused to postgres")

    with (
        patch("asyncio.create_subprocess_exec", return_value=mock_proc_fail),
        pytest.raises(BackupError, match="pg_dump exited with code 1"),
    ):
        await run_pg_dump(
            pg_dump_bin="/usr/bin/pg_dump",
            socket_dir="/tmp/fake-sock",
            port=5432,
            extra_env={"MOCK_VAR": "1"},
        )

    # 3. Successful execution
    mock_proc_success = AsyncMock()
    mock_proc_success.returncode = 0
    mock_proc_success.communicate.return_value = (b"DUMP_OUTPUT_OCTETS", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc_success):
        out = await run_pg_dump(
            pg_dump_bin="/usr/bin/pg_dump",
            socket_dir="/tmp/fake-sock",
            port=5432,
        )
        assert out == b"DUMP_OUTPUT_OCTETS"


@pytest.mark.asyncio
async def test_case_6_standalone_status_edge_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 6: Exercise get_standalone_status error handling and settings overrides."""
    # 1. Corrupted JSON file falls back cleanly
    corrupt_file = tmp_path / "corrupt_status.json"
    corrupt_file.write_text("{bad-json-content", encoding="utf-8")
    status = get_standalone_status(status_path=corrupt_file)
    assert status["deployment_mode"] == "production_multi_container"
    assert status["persistent_volume"] is True

    # 2. Settings with air_gap_mode = True
    settings = Settings(air_gap_mode=True)
    status_airgap = get_standalone_status(status_path=tmp_path / "absent.json", settings=settings)
    assert status_airgap["air_gap_mode"] is True

    # 3. KANBAN_AIR_GAP_MODE environment variable
    monkeypatch.setenv("KANBAN_AIR_GAP_MODE", "true")
    status_env_airgap = get_standalone_status(status_path=tmp_path / "absent.json")
    assert status_env_airgap["air_gap_mode"] is True


@pytest.mark.asyncio
async def test_case_7_api_backup_error_branches(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 7: Exercise API error branches (MASTER_KEK unavailable, pg_dump exception, non-admin)."""
    status_file = tmp_path / "standalone_status.json"
    status_file.write_text(
        '{"mode": "standalone_embedded_pg", "persistent_volume": true}',
        encoding="utf-8",
    )
    monkeypatch.setenv("KB_STANDALONE_STATUS_PATH", str(status_file))

    ws_id, admin_id, _member_id = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, csrf_token = await _login_and_elevate(
            client, session_service, db_session, admin_id, ws_id, aal_level=2
        )

        # 1. use_master_kek when master_kek is None -> 500 MASTER_KEK_UNAVAILABLE
        app.state.key_material = SimpleNamespace(
            session_hmac_key=key_material.session_hmac_key,
            auth_pepper=key_material.auth_pepper,
            master_kek=None,
        )
        resp_no_kek = await client.post(
            "/api/v1/admin/standalone/backup",
            json={"use_master_kek": True},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_no_kek.status_code == 500
        assert "MASTER_KEK_UNAVAILABLE" in resp_no_kek.text

        # Restore key_material
        app.state.key_material = key_material

        # 2. run_pg_dump raises Exception -> 500 BACKUP_DUMP_FAILED
        with patch(
            "kanban.api.v1.system_status.run_pg_dump", side_effect=RuntimeError("pg_dump crash")
        ):
            resp_dump_fail = await client.post(
                "/api/v1/admin/standalone/backup",
                json={"passphrase": "a-strong-passphrase-16+"},
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_dump_fail.status_code == 500
            assert "BACKUP_DUMP_FAILED" in resp_dump_fail.text

        # 3. Non-server-admin caller (WORKSPACE_ADMIN with AAL2) -> 403 INSUFFICIENT_CAPABILITY
        ws_admin_id = await _add_workspace_admin(db_session, ws_id)
        client.cookies.clear()
        _, ws_admin_csrf = await _login_and_elevate(
            client, session_service, db_session, ws_admin_id, ws_id, aal_level=2
        )
        resp_non_admin = await client.post(
            "/api/v1/admin/standalone/backup",
            json={"passphrase": "a-strong-passphrase-16+"},
            headers={CSRF_HEADER_NAME: ws_admin_csrf},
        )
        assert resp_non_admin.status_code == 403
        assert "INSUFFICIENT_CAPABILITY" in resp_non_admin.text


@pytest.mark.asyncio
async def test_case_8_backup_schedule_and_snapshots_api(  # noqa: PLR0915
    db_session: AsyncSession,
    key_material: KeyMaterial,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 8: Exercise backup schedule CRUD and snapshot listing / download APIs."""
    schedule_file = tmp_path / "backup_schedule.json"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("KB_BACKUP_SCHEDULE_PATH", str(schedule_file))
    monkeypatch.setenv("KB_BACKUP_DIR", str(backup_dir))

    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, csrf_token = await _login_and_elevate(
            client, session_service, db_session, admin_id, ws_id, aal_level=2
        )

        # 1. GET initial backup schedule
        resp_sched = await client.get("/api/v1/admin/standalone/backup-schedule")
        assert resp_sched.status_code == 200
        sched_data = resp_sched.json()
        assert sched_data["enabled"] is False
        assert sched_data["interval_hours"] == 24
        assert sched_data["retention_count"] == 7

        # 2. PUT updated backup schedule
        resp_put = await client.put(
            "/api/v1/admin/standalone/backup-schedule",
            json={"enabled": True, "interval_hours": 12, "retention_count": 5},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_put.status_code == 200
        updated = resp_put.json()
        assert updated["enabled"] is True
        assert updated["interval_hours"] == 12
        assert updated["retention_count"] == 5
        assert updated["next_run_at"] is not None

        # 3. GET backups list (initially empty)
        resp_list = await client.get("/api/v1/admin/standalone/backups")
        assert resp_list.status_code == 200
        assert resp_list.json() == []

        # 4. Create mock snapshot file on disk
        test_snapshot = backup_dir / "kanban-backup-20260101T000000Z.kbbak"
        test_snapshot.write_bytes(b"MOCK_ENCRYPTED_BACKUP_BYTES")

        resp_list2 = await client.get("/api/v1/admin/standalone/backups")
        assert resp_list2.status_code == 200
        items = resp_list2.json()
        assert len(items) == 1
        assert items[0]["filename"] == "kanban-backup-20260101T000000Z.kbbak"
        assert items[0]["size_bytes"] == len(b"MOCK_ENCRYPTED_BACKUP_BYTES")

        # 5. Download snapshot file
        resp_dl = await client.get(f"/api/v1/admin/standalone/backups/{test_snapshot.name}")
        assert resp_dl.status_code == 200
        assert resp_dl.content == b"MOCK_ENCRYPTED_BACKUP_BYTES"

        # 6. Traversal attack prevented
        resp_trav = await client.get("/api/v1/admin/standalone/backups/..%2Fetc%2Fpasswd")
        assert resp_trav.status_code in (400, 404)

        # 7. PUT backup schedule validation error (422)
        resp_bad_sched = await client.put(
            "/api/v1/admin/standalone/backup-schedule",
            json={"enabled": True, "interval_hours": 0, "retention_count": 5},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_bad_sched.status_code == 422

        # 8. PUT backup schedule OS persistence error (500) and ValueError (422)
        with patch(
            "kanban.api.v1.system_status.update_backup_schedule",
            side_effect=ValueError("Invalid retention count range"),
        ):
            resp_val_err = await client.put(
                "/api/v1/admin/standalone/backup-schedule",
                json={"enabled": True, "interval_hours": 24, "retention_count": 7},
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_val_err.status_code == 422
            assert "INVALID_BACKUP_SCHEDULE" in resp_val_err.text

        with patch(
            "kanban.api.v1.system_status.update_backup_schedule",
            side_effect=OSError("Read-only filesystem"),
        ):
            resp_os_err = await client.put(
                "/api/v1/admin/standalone/backup-schedule",
                json={"enabled": True, "interval_hours": 24, "retention_count": 7},
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_os_err.status_code == 500
            assert "BACKUP_SCHEDULE_SAVE_FAILED" in resp_os_err.text

        # 9. POST run-now error handling
        with patch(
            "kanban.api.v1.system_status.run_scheduled_backup_pass",
            side_effect=RuntimeError("pg_dump connection error"),
        ):
            resp_run_fail = await client.post(
                "/api/v1/admin/standalone/backups/run-now",
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_run_fail.status_code == 500
            assert "BACKUP_RUN_FAILED" in resp_run_fail.text

        with patch(
            "kanban.api.v1.system_status.run_scheduled_backup_pass",
            return_value=None,
        ):
            resp_run_none = await client.post(
                "/api/v1/admin/standalone/backups/run-now",
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_run_none.status_code == 500
            assert "BACKUP_RUN_FAILED" in resp_run_none.text

        # 10. POST run-now success
        with patch(
            "kanban.api.v1.system_status.run_scheduled_backup_pass",
            return_value=SimpleNamespace(
                archive_path=Path("/tmp/test.kbbak"),
                size_bytes=128,
                manifest=SimpleNamespace(to_dict=lambda: {"format": "kbbak"}),
                duration_seconds=0.25,
            ),
        ):
            resp_run_ok = await client.post(
                "/api/v1/admin/standalone/backups/run-now",
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_run_ok.status_code == 200
            assert resp_run_ok.json()["status"] == "success"

        # 11. Download invalid filename character (400)
        resp_bad_dl = await client.get("/api/v1/admin/standalone/backups/bad%20name.kbbak")
        assert resp_bad_dl.status_code == 400


@pytest.mark.asyncio
async def test_case_9_backup_verify_and_restore_api(  # noqa: PLR0915
    db_session: AsyncSession,
    key_material: KeyMaterial,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 9: Exercise backup verify and restore endpoints with RESTORE gate."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("KB_BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://kanban_test@/kanban_test?host=/tmp/kb-pgsock"
    )

    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, csrf_token = await _login_and_elevate(
            client, session_service, db_session, admin_id, ws_id, aal_level=2
        )

        # 1. Verify legacy .kbkp payload
        plain_dump = b"PGDUMP_MOCK_CONTENT"
        test_passphrase = "a-strong-passphrase-16+"
        enc_kbkp = encrypt_backup(plain_dump, passphrase=test_passphrase)
        kbkp_file = backup_dir / "test.kbkp"
        kbkp_file.write_bytes(enc_kbkp)

        resp_v_kbkp = await client.post(
            "/api/v1/admin/standalone/backup/verify",
            json={"filename": "test.kbkp", "passphrase": test_passphrase},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_v_kbkp.status_code == 200
        v_data = resp_v_kbkp.json()
        assert v_data["valid"] is True
        assert v_data["format"] == "kbkp"

        # 2. Restore fails without exact confirm_overwrite="RESTORE" (422)
        resp_r_fail = await client.post(
            "/api/v1/admin/standalone/restore",
            json={"filename": "test.kbkp", "confirm_overwrite": "yes"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_r_fail.status_code == 422
        assert "INVALID_CONFIRM_OVERWRITE" in resp_r_fail.text

        # Test invalid base64 and invalid filename handling on verify
        resp_v_bad_b64 = await client.post(
            "/api/v1/admin/standalone/backup/verify",
            json={"file_base64": "a"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_v_bad_b64.status_code == 422

        resp_v_bad_fn = await client.post(
            "/api/v1/admin/standalone/backup/verify",
            json={"filename": "../evil_path.kbbak"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_v_bad_fn.status_code == 400

        # Test invalid base64 on restore
        resp_r_bad_b64 = await client.post(
            "/api/v1/admin/standalone/restore",
            json={"file_base64": "a", "confirm_overwrite": "RESTORE"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_r_bad_b64.status_code == 422

        # 3. Verify multipart form upload and use_master_kek
        with patch.object(
            Request,
            "form",
            AsyncMock(
                return_value={
                    "file": SimpleNamespace(
                        read=AsyncMock(return_value=enc_kbkp),
                        filename="test.kbkp",
                    ),
                    "passphrase": test_passphrase,
                }
            ),
        ):
            resp_v_form = await client.post(
                "/api/v1/admin/standalone/backup/verify",
                headers={
                    CSRF_HEADER_NAME: csrf_token,
                    "content-type": "multipart/form-data; boundary=boundary",
                },
            )
            assert resp_v_form.status_code == 200
            assert resp_v_form.json()["valid"] is True

        enc_kek = encrypt_backup(plain_dump, master_kek=key_material.master_kek)
        with patch.object(
            Request,
            "form",
            AsyncMock(
                return_value={
                    "file": SimpleNamespace(
                        read=AsyncMock(return_value=enc_kek),
                        filename="test_kek.kbkp",
                    ),
                    "use_master_kek": "true",
                }
            ),
        ):
            resp_v_kek = await client.post(
                "/api/v1/admin/standalone/backup/verify",
                headers={
                    CSRF_HEADER_NAME: csrf_token,
                    "content-type": "multipart/form-data; boundary=boundary",
                },
            )
            assert resp_v_kek.status_code == 200
            assert resp_v_kek.json()["valid"] is True

        # 4. Verify invalid filename and missing payload
        resp_v_trav = await client.post(
            "/api/v1/admin/standalone/backup/verify",
            json={"filename": "../etc/passwd"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_v_trav.status_code == 400

        resp_v_missing = await client.post(
            "/api/v1/admin/standalone/backup/verify",
            json={"filename": "nonexistent.kbbak"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_v_missing.status_code == 404

        resp_v_empty = await client.post(
            "/api/v1/admin/standalone/backup/verify",
            json={},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_v_empty.status_code == 422

        # 5. Verify .kbbak format with mock verify_backup
        kbbak_file = backup_dir / "test.kbbak"
        kbbak_file.write_bytes(b"MOCK_KBBAK_TAR_BYTES")
        with patch("kanban.api.v1.system_status.verify_backup") as mock_v:
            mock_v.return_value = SimpleNamespace(to_dict=lambda: {"format": "kbbak", "version": 1})
            resp_v_kbbak = await client.post(
                "/api/v1/admin/standalone/backup/verify",
                json={"filename": "test.kbbak"},
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_v_kbbak.status_code == 200
            assert resp_v_kbbak.json()["format"] == "kbbak"

        with patch(
            "kanban.api.v1.system_status.verify_backup", side_effect=ValueError("Corrupted tar")
        ):
            resp_v_err = await client.post(
                "/api/v1/admin/standalone/backup/verify",
                json={"filename": "test.kbbak"},
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_v_err.status_code == 422
            assert "BACKUP_VERIFICATION_FAILED" in resp_v_err.text

        # 6. Restore invalid filename and missing payload
        resp_r_trav = await client.post(
            "/api/v1/admin/standalone/restore",
            json={"filename": "../test.kbbak", "confirm_overwrite": "RESTORE"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_r_trav.status_code == 400

        resp_r_notfound = await client.post(
            "/api/v1/admin/standalone/restore",
            json={"filename": "notfound.kbbak", "confirm_overwrite": "RESTORE"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_r_notfound.status_code == 404

        resp_r_empty = await client.post(
            "/api/v1/admin/standalone/restore",
            json={"confirm_overwrite": "RESTORE"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_r_empty.status_code == 422

        # 7. Restore successful execution via multipart upload and filename
        with (
            patch("kanban.api.v1.system_status.restore_backup") as mock_r,
            patch.object(
                Request,
                "form",
                AsyncMock(
                    return_value={
                        "file": SimpleNamespace(
                            read=AsyncMock(return_value=b"RESTORE_MOCK_PAYLOAD"),
                            filename="upload.kbbak",
                        ),
                        "confirm_overwrite": "RESTORE",
                        "use_master_kek": "true",
                    }
                ),
            ),
        ):
            mock_r.return_value = SimpleNamespace(
                workspaces_verified=1,
                links_audited=0,
                duration_seconds=0.42,
            )
            app.state.engine = AsyncMock()
            app.state.engine.dispose = AsyncMock()
            resp_r_upload = await client.post(
                "/api/v1/admin/standalone/restore",
                headers={
                    CSRF_HEADER_NAME: csrf_token,
                    "content-type": "multipart/form-data; boundary=boundary",
                },
            )
            assert resp_r_upload.status_code == 200
            assert resp_r_upload.json()["status"] == "success"
            assert resp_r_upload.json()["workspaces_verified"] == 1

            resp_r_file = await client.post(
                "/api/v1/admin/standalone/restore",
                json={
                    "filename": "test.kbkp",
                    "confirm_overwrite": "RESTORE",
                    "passphrase": test_passphrase,
                },
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_r_file.status_code == 200
            assert resp_r_file.json()["status"] == "success"

        # 8. Restore execution exception (500)
        with patch(
            "kanban.api.v1.system_status.restore_backup",
            side_effect=RuntimeError("pg_restore failed"),
        ):
            resp_r_exc = await client.post(
                "/api/v1/admin/standalone/restore",
                json={
                    "filename": "test.kbkp",
                    "confirm_overwrite": "RESTORE",
                    "passphrase": test_passphrase,
                },
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_r_exc.status_code == 500
            assert "RESTORE_EXECUTION_FAILED" in resp_r_exc.text

        # 9. Download missing backup file (404)
        resp_dl_missing = await client.get("/api/v1/admin/standalone/backups/missing-file.kbbak")
        assert resp_dl_missing.status_code == 404

        # 10. Restore with default key source (no passphrase, no kek)
        with patch("kanban.api.v1.system_status.restore_backup") as mock_r:
            mock_r.return_value = SimpleNamespace(
                workspaces_verified=1,
                links_audited=0,
                duration_seconds=0.1,
            )
            resp_no_key = await client.post(
                "/api/v1/admin/standalone/restore",
                json={
                    "filename": "test.kbkp",
                    "confirm_overwrite": "RESTORE",
                },
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_no_key.status_code == 200

        # 11. Target database URL not configured (500)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        app.state.settings = None
        resp_db_err = await client.post(
            "/api/v1/admin/standalone/restore",
            json={"filename": "test.kbkp", "confirm_overwrite": "RESTORE"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_db_err.status_code == 500
        assert "DATABASE_UNAVAILABLE" in resp_db_err.text

        # 12. Download backup invalid filename traversal (400)
        resp_dl_bad = await client.get("/api/v1/admin/standalone/backups/..%2Fevil.kbbak")
        assert resp_dl_bad.status_code in (400, 404)

        # 13. Verify backup invalid filename and missing payload (400, 422)
        resp_v_bad_name = await client.post(
            "/api/v1/admin/standalone/backup/verify",
            json={"filename": "../forbidden.kbbak"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_v_bad_name.status_code == 400

        resp_v_missing = await client.post(
            "/api/v1/admin/standalone/backup/verify",
            json={},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_v_missing.status_code == 422

        # 14. Verify backup KBKP format
        fake_kbkp = b"KBKP" + b"\x00" * 60
        with patch("kanban.api.v1.system_status.decrypt_backup", return_value=b"DUMP_CONTENT"):
            resp_v_kbkp = await client.post(
                "/api/v1/admin/standalone/backup/verify",
                json={
                    "file_base64": base64.b64encode(fake_kbkp).decode("ascii"),
                    "passphrase": test_passphrase,
                },
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            assert resp_v_kbkp.status_code == 200
            assert resp_v_kbkp.json()["format"] == "kbkp"

        # 15. Restore backup missing payload (422) and invalid filename (400)
        resp_r_bad_name = await client.post(
            "/api/v1/admin/standalone/restore",
            json={"filename": "../bad.kbbak", "confirm_overwrite": "RESTORE"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_r_bad_name.status_code == 400

        resp_r_missing = await client.post(
            "/api/v1/admin/standalone/restore",
            json={"confirm_overwrite": "RESTORE"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_r_missing.status_code == 422


def test_assert_admin_routes_protected_compliance() -> None:
    """Verify all admin routes declare require_admin_aal2 dependency."""
    app = create_app()
    unprotected = assert_admin_routes_protected(app)
    assert not unprotected, f"Unprotected admin routes detected: {unprotected}"


@pytest.mark.asyncio
async def test_system_status_workspace_air_gap_sqlalchemy_error() -> None:
    """Test system status endpoint handles SQLAlchemyError during workspace air gap check."""
    from kanban.api.v1.system_status import _assemble_system_status_response

    mock_caller = MagicMock()
    mock_caller.workspace_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.execute.side_effect = [
        MagicMock(scalar_one=MagicMock(return_value=True)),
        SQLAlchemyError("DB error"),
    ]

    mock_req = MagicMock()
    mock_req.app.state.settings = Settings()
    mock_req.app.openapi.return_value = {"info": {"version": "1.0.0"}, "paths": {}}

    resp = await _assemble_system_status_response(
        caller=mock_caller,
        session=mock_session,
        request=mock_req,
    )
    assert resp.air_gap_mode is False


@pytest.mark.asyncio
async def test_run_backup_now_ops_socket_oserror_fallback(tmp_path: Path) -> None:
    """Test run_backup_now falls back to direct pass when ops socket raises OSError."""
    from kanban.api.v1.system_status import run_backup_now_endpoint

    fake_sock = tmp_path / "fake.sock"
    fake_sock.touch()

    mock_req = MagicMock()
    mock_req.app.state.settings = Settings()

    with (
        patch("pathlib.Path.is_socket", return_value=True),
        patch("socket.socket", side_effect=OSError("Socket connect failure")),
        patch.dict(os.environ, {"KB_OPS_SOCK": str(fake_sock)}),
        patch(
            "kanban.api.v1.system_status.run_scheduled_backup_pass",
            return_value=MagicMock(filename="backup.kbbak", size_bytes=100),
        ),
    ):
        res = await run_backup_now_endpoint(request=mock_req)
        assert res["status"] == "success"


@pytest.mark.asyncio
async def test_restore_backup_ops_socket_engine_dispose(tmp_path: Path) -> None:
    """Test restore_backup_endpoint disposes app engine when ops socket restore succeeds."""
    from kanban.api.v1.system_status import restore_backup_endpoint

    fake_sock = tmp_path / "fake.sock"
    fake_sock.touch()

    mock_req = MagicMock()
    mock_req.headers = {"content-type": "application/json"}
    mock_req.json = AsyncMock(
        return_value={
            "file_base64": base64.b64encode(b"dummy_payload").decode("ascii"),
            "confirm_overwrite": "RESTORE",
        }
    )
    mock_engine = AsyncMock()
    mock_req.app.state.engine = mock_engine
    mock_req.app.state.key_material = None

    mock_client = MagicMock()
    mock_client.recv.side_effect = [
        json.dumps({"status": "ok", "report": {"workspaces_verified": 1}}).encode("utf-8") + b"\n",
        b"",
    ]

    with (
        patch("pathlib.Path.is_socket", return_value=True),
        patch("socket.socket") as mock_sock_cls,
        patch.dict(os.environ, {"KB_OPS_SOCK": str(fake_sock)}),
    ):
        mock_sock_cls.return_value.__enter__.return_value = mock_client
        res = await restore_backup_endpoint(request=mock_req)
        assert res["status"] == "success"
        mock_engine.dispose.assert_awaited_once()
