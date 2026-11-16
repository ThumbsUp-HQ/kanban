"""End-to-end integration tests for backup creation, verification, restore, and CLI."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from typing import TYPE_CHECKING

import argon2
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from database.testing.pg_harness import build_dsn
from kanban.cli.ctl import main as ctl_main
from kanban.cli.ops import main as ops_main
from kanban.ops.backup_crypto import RawKeySource
from kanban.ops.backup_service import (
    TargetDatabaseNotEmptyError,
    create_backup,
    restore_backup,
    verify_backup,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


def _wrap_secret_dek(plaintext: bytes, kek: bytes) -> bytes:
    """Envelope-encrypt secret payload using AES-256-GCM and MASTER_KEK."""
    nonce = os.urandom(12)
    ct = AESGCM(kek).encrypt(nonce, plaintext, b"AUTH_CARD_DEK")
    return nonce + ct


def _unwrap_secret_dek(wrapped: bytes, kek: bytes) -> bytes:
    """Envelope-decrypt secret payload using AES-256-GCM and MASTER_KEK."""
    nonce = wrapped[:12]
    ct = wrapped[12:]
    return AESGCM(kek).decrypt(nonce, ct, b"AUTH_CARD_DEK")


def _hash_password_with_pepper(password: str, pepper: bytes) -> str:
    """Compute Argon2id password hash using HMAC-SHA256 pepper."""
    keyed = hmac.new(pepper, password.encode("utf-8"), hashlib.sha256).digest()
    ph = argon2.PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    return ph.hash(keyed)


def _verify_password_with_pepper(hash_str: str, password: str, pepper: bytes) -> bool:
    """Verify password hash using HMAC-SHA256 pepper."""
    keyed = hmac.new(pepper, password.encode("utf-8"), hashlib.sha256).digest()
    ph = argon2.PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    try:
        return ph.verify(hash_str, keyed)
    except argon2.exceptions.VerifyMismatchError:
        return False


async def _create_test_db(db_name: str, *, from_template: bool) -> str:
    """Create test database on local socket, optionally cloned from kanban_template."""
    sock = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    admin_dsn = build_dsn("template1", host=sock)
    engine = create_async_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}";'))
        if from_template:
            await conn.execute(text(f'CREATE DATABASE "{db_name}" TEMPLATE kanban_template;'))
        else:
            await conn.execute(text(f'CREATE DATABASE "{db_name}";'))
    await engine.dispose()
    return build_dsn(db_name, host=sock)


async def _drop_test_db(db_name: str) -> None:
    """Drop test database."""
    sock = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    admin_dsn = build_dsn("template1", host=sock)
    engine = create_async_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :dname AND pid <> pg_backend_pid();"
            ),
            {"dname": db_name},
        )
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}";'))
    await engine.dispose()


@pytest.fixture
async def src_database() -> AsyncGenerator[tuple[str, str], None]:
    """Provide isolated source database initialized from kanban_template."""
    db_name = f"kb_src_{uuid.uuid4().hex[:8]}"
    db_url = await _create_test_db(db_name, from_template=True)
    yield db_name, db_url
    await _drop_test_db(db_name)


@pytest.fixture
async def dst_database() -> AsyncGenerator[tuple[str, str], None]:
    """Provide clean empty target database for restore tests."""
    db_name = f"kb_dst_{uuid.uuid4().hex[:8]}"
    db_url = await _create_test_db(db_name, from_template=False)
    yield db_name, db_url
    await _drop_test_db(db_name)


async def _seed_source_database(db_url: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed comprehensive entity dataset into source database."""
    engine = create_async_engine(db_url)
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async with engine.begin() as conn:
        # 1. Workspace
        await conn.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name);"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:6]}", "name": "Promotion Workspace"},
        )

        # 2. Principal & User (principals, objects, users)
        await conn.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', :name);"
            ),
            {"id": user_id, "ws_id": ws_id, "name": "Local Admin"},
        )
        await conn.execute(
            text(
                "SELECT register_object("
                "  'user'::object_kind, :ws_id, NULL, :ckey, :name, :uid, :id"
                ");"
            ),
            {
                "ws_id": ws_id,
                "ckey": f"usr-{user_id.hex[:8]}",
                "name": "Local Admin",
                "uid": user_id,
                "id": user_id,
            },
        )
        await conn.execute(
            text(
                "INSERT INTO users (id, workspace_id, email) "
                "VALUES (:id, :ws_id, 'admin@example.com');"
            ),
            {"id": user_id, "ws_id": ws_id},
        )
        await conn.execute(
            text(
                "INSERT INTO role_bindings ("
                "  workspace_id, principal_id, role, scope_type, project_id"
                ") VALUES (:ws_id, :uid, 'WORKSPACE_ADMIN', 'workspace', NULL);"
            ),
            {"ws_id": ws_id, "uid": user_id},
        )

        # 3. Project KAN
        reg_proj = await conn.execute(
            text(
                "SELECT register_object("
                "  'project'::object_kind, :ws_id, NULL, 'KAN', 'Kanban Project', :uid"
                ");"
            ),
            {"ws_id": ws_id, "uid": user_id},
        )
        proj_id = reg_proj.scalar_one()
        await conn.execute(
            text(
                "INSERT INTO projects (id, workspace_id, identifier, name) "
                "VALUES (:id, :ws_id, 'KAN', 'Kanban Project');"
            ),
            {"id": proj_id, "ws_id": ws_id},
        )

        # 4. State & Priority IDs
        state_id = (
            await conn.execute(
                text(
                    "SELECT id FROM workflow_states WHERE project_id = :pid AND is_default = true;"
                ),
                {"pid": proj_id},
            )
        ).scalar_one()

        prio_id = (
            await conn.execute(
                text(
                    "SELECT id FROM project_priorities "
                    "WHERE project_id = :pid AND is_default = true;"
                ),
                {"pid": proj_id},
            )
        ).scalar_one()

        # 5. Issues KAN-1 and KAN-2
        issue_1_id: uuid.UUID | None = None
        for _ in (1, 2):
            seq = (
                await conn.execute(
                    text("SELECT allocate_issue_sequence(:pid);"),
                    {"pid": proj_id},
                )
            ).scalar_one()
            iss_id = uuid.uuid4()
            if issue_1_id is None:
                issue_1_id = iss_id
            ckey = f"KAN-{seq}"
            await conn.execute(
                text(
                    "SELECT register_object("
                    "  'issue'::object_kind, :ws_id, :pid, :ckey, :title, :uid, :id"
                    ");"
                ),
                {
                    "ws_id": ws_id,
                    "pid": proj_id,
                    "ckey": ckey,
                    "title": f"Issue Title {seq}",
                    "uid": user_id,
                    "id": iss_id,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO issues ("
                    "  id, workspace_id, project_id, sequence_id, summary, "
                    "  description_markdown, state_id, priority_id, "
                    "  created_by_id, original_created_by_id, board_rank"
                    ") VALUES ("
                    "  :id, :ws_id, :pid, :seq, :summary, 'Desc', :state_id, "
                    "  :prio_id, :uid, :uid, :rank"
                    ");"
                ),
                {
                    "id": iss_id,
                    "ws_id": ws_id,
                    "pid": proj_id,
                    "seq": seq,
                    "summary": f"Issue Summary {seq}",
                    "state_id": state_id,
                    "prio_id": prio_id,
                    "uid": user_id,
                    "rank": f"0|i{seq:05d}:",
                },
            )

        assert issue_1_id is not None

        # 6. Prose tables: Doc, Page, Sticky
        doc_id = uuid.uuid4()
        await conn.execute(
            text(
                "SELECT register_object("
                "  'doc'::object_kind, :ws_id, :pid, :ckey, :title, :uid, :id"
                ");"
            ),
            {
                "ws_id": ws_id,
                "pid": proj_id,
                "ckey": f"doc-{doc_id.hex[:8]}",
                "title": "Architecture Doc",
                "uid": user_id,
                "id": doc_id,
            },
        )
        await conn.execute(
            text(
                "INSERT INTO docs ("
                "  id, workspace_id, project_id, title, body_markdown"
                ") VALUES (:id, :ws_id, :pid, 'Architecture Doc', '# Doc Markdown');"
            ),
            {"id": doc_id, "ws_id": ws_id, "pid": proj_id},
        )

        page_id = uuid.uuid4()
        await conn.execute(
            text(
                "SELECT register_object("
                "  'page'::object_kind, :ws_id, :pid, :ckey, :title, :uid, :id"
                ");"
            ),
            {
                "ws_id": ws_id,
                "pid": proj_id,
                "ckey": f"pg-{page_id.hex[:8]}",
                "title": "Project Page",
                "uid": user_id,
                "id": page_id,
            },
        )
        await conn.execute(
            text(
                "INSERT INTO pages ("
                "  id, workspace_id, doc_id, title, body_markdown"
                ") VALUES (:id, :ws_id, :doc_id, 'Project Page', 'Page Content');"
            ),
            {"id": page_id, "ws_id": ws_id, "doc_id": doc_id},
        )

        sticky_id = uuid.uuid4()
        await conn.execute(
            text(
                "SELECT register_object("
                "  'sticky'::object_kind, :ws_id, NULL, :ckey, 'Idea Sticky', :uid, :id"
                ");"
            ),
            {
                "ws_id": ws_id,
                "ckey": f"stk-{sticky_id.hex[:8]}",
                "uid": user_id,
                "id": sticky_id,
            },
        )
        await conn.execute(
            text(
                "INSERT INTO stickies ("
                "  id, workspace_id, project_id, body_markdown, color_token"
                ") VALUES (:id, :ws_id, NULL, 'Quick idea', 'amber');"
            ),
            {"id": sticky_id, "ws_id": ws_id},
        )

        # 7. Object link: link issue KAN-1 to Doc
        await conn.execute(
            text(
                "INSERT INTO object_links ("
                "  workspace_id, source_id, source_type, target_id, target_type, "
                "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
                ") VALUES ("
                "  :ws_id, :src_id, 'issue'::object_kind, :tgt_id, 'doc'::object_kind, "
                "  'RELATES_TO'::link_kind, 'KAN-1', :tgt_key, :uid"
                ");"
            ),
            {
                "ws_id": ws_id,
                "src_id": issue_1_id,
                "tgt_id": doc_id,
                "tgt_key": f"doc-{doc_id.hex[:8]}",
                "uid": user_id,
            },
        )

        # 8. Activity Records with hash chain via append_activity
        append_sql = (
            "SELECT append_activity("
            "  :ws_id, :obj_id, CAST(:kind AS object_kind), :uid, :evt, CAST(:payload AS jsonb)"
            ");"
        )
        await conn.execute(
            text(append_sql),
            {
                "ws_id": ws_id,
                "obj_id": proj_id,
                "kind": "project",
                "uid": user_id,
                "evt": "PROJECT_INITIALIZED",
                "payload": '{"mode": "standalone"}',
            },
        )
        await conn.execute(
            text(append_sql),
            {
                "ws_id": ws_id,
                "obj_id": issue_1_id,
                "kind": "issue",
                "uid": user_id,
                "evt": "ISSUE_CREATED",
                "payload": '{"key": "KAN-1"}',
            },
        )

    await engine.dispose()
    return ws_id, proj_id, user_id


async def _verify_restored_database(dst_url: str, ws_id: uuid.UUID) -> None:
    """Verify table row counts, activity chain, links, and RLS on destination DB."""
    engine = create_async_engine(dst_url)
    async with engine.connect() as conn:
        ws_count = (await conn.execute(text("SELECT count(*) FROM workspaces;"))).scalar()
        proj_count = (await conn.execute(text("SELECT count(*) FROM projects;"))).scalar()
        issue_count = (await conn.execute(text("SELECT count(*) FROM issues;"))).scalar()
        doc_count = (await conn.execute(text("SELECT count(*) FROM docs;"))).scalar()
        page_count = (await conn.execute(text("SELECT count(*) FROM pages;"))).scalar()
        sticky_count = (await conn.execute(text("SELECT count(*) FROM stickies;"))).scalar()
        link_count = (await conn.execute(text("SELECT count(*) FROM object_links;"))).scalar()
        act_count = (await conn.execute(text("SELECT count(*) FROM activity_records;"))).scalar()

        assert ws_count == 1
        assert proj_count == 1
        assert issue_count == 2
        assert doc_count == 1
        assert page_count == 1
        assert sticky_count == 1
        assert link_count == 1
        assert act_count is not None
        assert int(act_count) >= 2

        chain_res = await conn.execute(
            text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws_id);"),
            {"ws_id": ws_id},
        )
        chain_row = chain_res.mappings().one()
        assert chain_row["is_valid"] is True
        checked_rows = chain_row["checked_rows"]
        assert checked_rows is not None
        assert int(checked_rows) >= 2

        audit_res = await conn.execute(
            text("SELECT count(*) FROM audit_object_links(:ws_id);"),
            {"ws_id": ws_id},
        )
        assert audit_res.scalar() == 0

        rls_rows = (
            await conn.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public') "
                    "AND relkind IN ('r', 'p') "
                    "AND relname NOT IN ('alembic_version', 'link_type_matrix', 'spatial_ref_sys');"
                )
            )
        ).fetchall()
        for r in rls_rows:
            assert r[1] is True, f"relrowsecurity false on {r[0]}"
            assert r[2] is True, f"relforcerowsecurity false on {r[0]}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_positive_standalone_to_production_roundtrip(
    src_database: tuple[str, str],
    dst_database: tuple[str, str],
    tmp_path: Path,
) -> None:
    """Test Case 1: Standalone -> external PG16 lossless promotion round-trip."""
    _, src_url = src_database
    _, dst_url = dst_database

    ws_id, _proj_id, _ = await _seed_source_database(src_url)

    # 1. Setup standalone keyring and cryptographic secrets
    master_kek_bytes = os.urandom(32)
    auth_pepper_bytes = os.urandom(32)
    master_kek_b64 = base64.urlsafe_b64encode(master_kek_bytes).decode("ascii").rstrip("=")
    auth_pepper_b64 = base64.urlsafe_b64encode(auth_pepper_bytes).decode("ascii").rstrip("=")

    keyring_file = tmp_path / "standalone_keyring.json"
    session_key_b64 = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    keyring_file.write_text(
        json.dumps(
            {
                "version": 1,
                "created_at": "2026-11-11T00:00:00Z",
                "MASTER_KEK": master_kek_b64,
                "KB_AUTH_PEPPER": auth_pepper_b64,
                "SESSION_HMAC_KEY": session_key_b64,
                "db_roles": {"kanban_app": "app_pw", "kanban_migrator": "mig_pw"},
            }
        ),
        encoding="utf-8",
    )

    raw_oidc_secret = b"okta_client_secret_xyz123_confidential"
    wrapped_secret = _wrap_secret_dek(raw_oidc_secret, master_kek_bytes)

    admin_password = "SuperSecretLocalAdminPass123!"
    password_hash = _hash_password_with_pepper(admin_password, auth_pepper_bytes)

    att_dir = tmp_path / "attachments_src"
    att_dir.mkdir(parents=True)
    sample_file = att_dir / "diagram.png"
    sample_file.write_bytes(b"\x89PNG\r\n\x1a\n" + os.urandom(100))

    # 2. Create encrypted backup
    backup_file = tmp_path / "backup_archive.kbbak"
    backup_key_bytes = os.urandom(32)
    key_src = RawKeySource(backup_key_bytes)

    summary = create_backup(
        db_url=src_url,
        out_path=backup_file,
        key_source=key_src,
        include_secrets=True,
        keyring_path=keyring_file,
        attachments_dir=att_dir,
    )

    assert backup_file.is_file()
    assert summary.size_bytes > 0
    assert summary.manifest.includes_keyring_secrets is True
    assert summary.manifest.attachments_count == 1

    # 3. Verify backup without connecting to database
    manifest = verify_backup(backup_file, key_src)
    assert manifest.sha256_pgdump == summary.manifest.sha256_pgdump
    assert manifest.format_version == 1

    # 4. Restore backup into second clean PG16 database
    target_keyring_file = tmp_path / "restored_keyring.json"
    restored_att_dir = tmp_path / "attachments_restored"

    report = restore_backup(
        archive_path=backup_file,
        target_db_url=dst_url,
        key_source=key_src,
        confirm_overwrite=True,
        target_keyring_path=target_keyring_file,
        restore_attachments_dir=restored_att_dir,
    )

    assert report.workspaces_verified >= 1
    assert report.secrets_restored is True
    assert report.attachments_restored == 1

    # 5. Verify database contents on destination PostgreSQL 16
    await _verify_restored_database(dst_url, ws_id)

    # 6. Verify carried-over secrets
    assert target_keyring_file.is_file()
    restored_keyring_data = json.loads(target_keyring_file.read_text(encoding="utf-8"))
    assert restored_keyring_data["MASTER_KEK"] == master_kek_b64
    assert restored_keyring_data["KB_AUTH_PEPPER"] == auth_pepper_b64

    unwrapped = _unwrap_secret_dek(wrapped_secret, master_kek_bytes)
    assert unwrapped == raw_oidc_secret

    assert _verify_password_with_pepper(password_hash, admin_password, auth_pepper_bytes) is True
    assert _verify_password_with_pepper(password_hash, "WrongPassword", auth_pepper_bytes) is False

    restored_file = restored_att_dir / "diagram.png"
    assert restored_file.is_file()
    assert restored_file.read_bytes() == sample_file.read_bytes()


@pytest.mark.asyncio
async def test_restore_non_empty_database_safety(
    src_database: tuple[str, str],
    dst_database: tuple[str, str],
    tmp_path: Path,
) -> None:
    """Test Case 2: Refuse restore on non-empty database without confirm_overwrite."""
    _, src_url = src_database
    dst_name, dst_url = dst_database

    await _seed_source_database(src_url)

    # Initialize dst_database with tables
    sock = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    admin_dsn = build_dsn("template1", host=sock)
    engine = create_async_engine(admin_dsn, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{dst_name}";'))
        await conn.execute(text(f'CREATE DATABASE "{dst_name}" TEMPLATE kanban_template;'))
    await engine.dispose()

    # Create backup
    backup_file = tmp_path / "test_safety.kbbak"
    key_src = RawKeySource(os.urandom(32))
    create_backup(db_url=src_url, out_path=backup_file, key_source=key_src)

    # Refuse restore without confirm_overwrite
    with pytest.raises(TargetDatabaseNotEmptyError, match="Target database is not empty"):
        restore_backup(
            archive_path=backup_file,
            target_db_url=dst_url,
            key_source=key_src,
            confirm_overwrite=False,
        )

    # Overwrite allowed with confirm_overwrite=True
    report = restore_backup(
        archive_path=backup_file,
        target_db_url=dst_url,
        key_source=key_src,
        confirm_overwrite=True,
    )
    assert report.workspaces_verified >= 1


@pytest.mark.asyncio
async def test_cli_secret_hygiene_and_commands(
    src_database: tuple[str, str],
    dst_database: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Case 3: CLI secret hygiene (exit 2) and full CLI command execution."""
    _, src_url = src_database
    _, dst_url = dst_database

    await _seed_source_database(src_url)

    # 1. Passing secret directly in argv must exit 2 with SECRET_IN_ARGV_FORBIDDEN
    ret_passphrase = ctl_main(["backup", "create", "--passphrase", "secret123"])
    assert ret_passphrase == 2

    ret_key = ctl_main(["backup", "create", "--key", "secretkey123"])
    assert ret_key == 2

    ret_pass_eq = ops_main(["backup", "create", "--passphrase=secret123"])
    assert ret_pass_eq == 2

    ret_key_eq = ops_main(["backup", "create", "--key=secretkey123"])
    assert ret_key_eq == 2

    # 2. CLI backup create using environment key
    backup_b64 = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    monkeypatch.setenv("KB_BACKUP_KEY", backup_b64)

    archive_path = tmp_path / "cli_backup.kbbak"
    ret_create = ctl_main(
        [
            "backup",
            "create",
            "--out",
            str(archive_path),
            "--db-url",
            src_url,
        ]
    )
    assert ret_create == 0
    assert archive_path.is_file()

    # 3. CLI backup verify
    ret_verify = ctl_main(
        [
            "backup",
            "verify",
            "--in",
            str(archive_path),
        ]
    )
    assert ret_verify == 0

    # 4. CLI backup verify on tampered file exits 2
    tampered_file = tmp_path / "tampered.kbbak"
    tampered_bytes = bytearray(archive_path.read_bytes())
    tampered_bytes[100] ^= 0xFF
    tampered_file.write_bytes(tampered_bytes)

    ret_tamper = ctl_main(
        [
            "backup",
            "verify",
            "--in",
            str(tampered_file),
        ]
    )
    assert ret_tamper == 2

    # 5. CLI restore into destination DB
    ret_restore = ctl_main(
        [
            "restore",
            "--in",
            str(archive_path),
            "--target-db-url",
            dst_url,
            "--confirm-overwrite",
        ]
    )
    assert ret_restore == 0

    # 6. CLI promote export-compose
    export_dir = tmp_path / "cli_compose_export"
    ret_promote = ctl_main(
        [
            "promote",
            "export-compose",
            "--out-dir",
            str(export_dir),
            "--domain",
            "kanban.cli.test",
        ]
    )
    assert ret_promote == 0
    assert (export_dir / "docker-compose.yml").is_file()
    assert (export_dir / "Caddyfile").is_file()
    assert (export_dir / ".env.production").is_file()
