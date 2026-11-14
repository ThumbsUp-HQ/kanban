# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for Plane import CLI commands (KB-P6-01, S1.3)."""

# ruff: noqa: E501, PLC0415, ANN401, TC002

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from database.session import RLSContext, RLSSessionFactory
from kanban.cli.ctl import main as ctl_main
from kanban.cli.import_plane import (
    _execute_import_db,
    _get_admin_dsn,
    _run_fetch_snapshot,
    _run_plane_import,
    register_import_subparsers,
)
from kanban.importer.plane_client import PlaneSecurityError
from kanban.importer.plane_importer import ImportIntegrityError

FIXTURE_DIR = Path("tests/fixtures/plane_export_kanba").resolve()


def test_ctl_help_and_subparsers() -> None:
    """Test parser registration and help output."""
    parser = argparse.ArgumentParser(prog="kanban-ctl")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    register_import_subparsers(subparsers)

    assert ctl_main(["import", "--help"]) == 0
    assert ctl_main(["import", "plane", "--help"]) == 0


def test_run_fetch_snapshot_success(tmp_path: Path) -> None:
    """Test fetch snapshot CLI execution success."""
    args = argparse.Namespace(
        base_url="https://plane.example.com",
        workspace_slug="ws-test",
        project_identifier="PRJ",
        out_dir=str(tmp_path / "out"),
        allow_loopback_http=False,
        allow_private_cidr=False,
    )
    with patch(
        "kanban.cli.import_plane.PlaneClient.fetch_snapshot", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = None
        code = _run_fetch_snapshot(args)
        assert code == 0
        mock_fetch.assert_awaited_once()


def test_run_fetch_snapshot_security_error(tmp_path: Path) -> None:
    """Test fetch snapshot CLI security failure."""
    args = argparse.Namespace(
        base_url="http://169.254.169.254",
        workspace_slug="ws-test",
        project_identifier="PRJ",
        out_dir=str(tmp_path / "out"),
        allow_loopback_http=False,
        allow_private_cidr=False,
    )
    with patch(
        "kanban.cli.import_plane.PlaneClient.fetch_snapshot",
        side_effect=PlaneSecurityError("Blocked IP"),
    ):
        code = _run_fetch_snapshot(args)
        assert code == 2


def test_run_fetch_snapshot_unexpected_error(tmp_path: Path) -> None:
    """Test fetch snapshot CLI unexpected error."""
    args = argparse.Namespace(
        base_url="https://plane.example.com",
        workspace_slug="ws-test",
        project_identifier="PRJ",
        out_dir=str(tmp_path / "out"),
        allow_loopback_http=False,
        allow_private_cidr=False,
    )
    with patch(
        "kanban.cli.import_plane.PlaneClient.fetch_snapshot", side_effect=RuntimeError("DNS Boom")
    ):
        code = _run_fetch_snapshot(args)
        assert code == 1


def test_run_plane_import_validation_errors(tmp_path: Path) -> None:
    """Test validation errors for CLI arguments before DB connection."""
    # 1. Missing bundle_dir or workspace
    args = argparse.Namespace(bundle_dir=None, workspace=None)
    assert _run_plane_import(args) == 2

    # 2. Non-existent bundle dir
    args = argparse.Namespace(
        bundle_dir=str(tmp_path / "nonexistent"), workspace="my-ws", user_map=None
    )
    assert _run_plane_import(args) == 2

    # 3. Non-existent user map
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    args = argparse.Namespace(
        bundle_dir=str(bundle_dir), workspace="my-ws", user_map=str(tmp_path / "bad-map.yaml")
    )
    assert _run_plane_import(args) == 2

    # 4. Corrupted user map
    corrupt_map = tmp_path / "corrupt_map.yaml"
    corrupt_map.write_text("invalid: [yaml: unclosed", encoding="utf-8")
    args = argparse.Namespace(
        bundle_dir=str(bundle_dir), workspace="my-ws", user_map=str(corrupt_map)
    )
    assert _run_plane_import(args) == 2

    # 5. Invalid bundle content
    corrupt_bundle = tmp_path / "corrupt_bundle"
    corrupt_bundle.mkdir()
    (corrupt_bundle / "projects.json").write_text("{corrupt json", encoding="utf-8")
    valid_map = tmp_path / "valid_map.yaml"
    valid_map.write_text("plane-user-1: k-user-1\n", encoding="utf-8")
    args = argparse.Namespace(
        bundle_dir=str(corrupt_bundle), workspace="my-ws", user_map=str(valid_map)
    )
    assert _run_plane_import(args) == 2


def test_run_plane_import_delegates_to_asyncio(tmp_path: Path) -> None:
    """Test _run_plane_import wrapper executes asyncio.run."""
    from typing import Any

    valid_map = tmp_path / "valid_map.yaml"
    valid_map.write_text("plane-user-1: k-user-1\n", encoding="utf-8")
    args = argparse.Namespace(
        bundle_dir=str(FIXTURE_DIR),
        workspace="my-ws",
        user_map=str(valid_map),
        dry_run=True,
        report_out=None,
    )

    def fake_run(coro: Any) -> int:
        coro.close()
        return 0

    with patch("kanban.cli.import_plane.asyncio.run", side_effect=fake_run) as mock_run:
        assert _run_plane_import(args) == 0
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_run_plane_import_db_execution(
    pg_worker_db: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test full CLI import against test PostgreSQL database (dry-run and live)."""
    from kanban.importer.plane_client import PlaneClient

    factory = RLSSessionFactory(pg_worker_db)
    ws_id = uuid.uuid4()
    ws_slug = f"cli-ws-{ws_id.hex[:8]}"
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)

    async with factory.session(anon_ctx) as session:
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'CLI WS')"),
            {"id": ws_id, "slug": ws_slug},
        )
        u_id = uuid.uuid4()
        await session.execute(
            text(
                "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'CLI Admin', :u_id, :u_id)"
            ),
            {"ws_id": ws_id, "ckey": f"usr-{u_id.hex}", "u_id": u_id},
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) VALUES (:id, 'USER', :ws_id, 'CLI Admin', 'ACTIVE')"
            ),
            {"id": u_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) VALUES (:id, 'user', 'USER', :ws_id, 'cli-admin@example.com')"
            ),
            {"id": u_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id) VALUES (:id, :ws_id, :pid, 'WORKSPACE_ADMIN', 'workspace', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "pid": u_id},
        )
        await session.commit()

    # Configure DSN to point to pg_worker_db
    monkeypatch.setenv("KANBAN_DATABASE_URL", str(pg_worker_db.url))

    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    # 1. Non-existent workspace
    args_bad_ws = argparse.Namespace(
        bundle_dir=str(FIXTURE_DIR),
        workspace="non-existent-ws-xyz",
        user_map=None,
        dry_run=True,
        report_out=None,
    )
    assert await _execute_import_db(args_bad_ws, bundle, {}) == 2

    # 2. Dry run with report out
    report_file = tmp_path / "cli_report.json"
    args_dry = argparse.Namespace(
        bundle_dir=str(FIXTURE_DIR),
        workspace=ws_slug,
        user_map=None,
        dry_run=True,
        report_out=str(report_file),
    )
    res_dry = await _execute_import_db(args_dry, bundle, {})
    assert res_dry == 0
    assert report_file.is_file()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["to_create"] > 0

    # 3. Live import
    args_live = argparse.Namespace(
        bundle_dir=str(FIXTURE_DIR),
        workspace=ws_slug,
        user_map=None,
        dry_run=False,
        report_out=None,
    )
    res_live = await _execute_import_db(args_live, bundle, {})
    assert res_live == 0

    # 3b. Dry run with warnings
    with patch("kanban.cli.import_plane.PlaneImporter.run_import") as mock_run_import:
        from kanban.importer.plane_mapper import ImportDiffReport

        mock_rep = ImportDiffReport(warnings=["Simulated import warning"])
        mock_run_import.return_value = mock_rep
        res_warn = await _execute_import_db(args_dry, bundle, {})
        assert res_warn == 0

    # 4. Handle ImportIntegrityError
    with patch(
        "kanban.cli.import_plane.PlaneImporter.run_import",
        side_effect=ImportIntegrityError("Integrity breached"),
    ):
        res_integrity = await _execute_import_db(args_dry, bundle, {})
        assert res_integrity == 2

    # 5. Handle unexpected runtime error
    with patch(
        "kanban.cli.import_plane.PlaneImporter.run_import",
        side_effect=RuntimeError("Unexpected DB crash"),
    ):
        res_crash = await _execute_import_db(args_dry, bundle, {})
        assert res_crash == 1


def test_get_admin_dsn_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _get_admin_dsn fallbacks."""
    monkeypatch.delenv("KANBAN_ADMIN_DATABASE_URL", raising=False)
    monkeypatch.delenv("KANBAN_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KB_TEST_PGHOST", "/tmp/test-sock")
    monkeypatch.setenv("KB_ADMIN_PGUSER", "test_user")
    monkeypatch.setenv("PGDATABASE", "test_db")
    dsn = _get_admin_dsn()
    assert dsn == "postgresql+asyncpg://test_user@/test_db?host=/tmp/test-sock"


@pytest.mark.asyncio
async def test_cli_fallback_principal_resolution(
    pg_worker_db: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test CLI resolves fallback principal when role_bindings has no admin."""
    from kanban.importer.plane_client import PlaneClient

    factory = RLSSessionFactory(pg_worker_db)
    ws_id = uuid.uuid4()
    ws_slug = f"fallback-ws-{ws_id.hex[:8]}"
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)

    u_id = uuid.uuid4()
    async with factory.session(anon_ctx) as session:
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Fallback WS')"),
            {"id": ws_id, "slug": ws_slug},
        )
        await session.execute(
            text(
                "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'User Only', :u_id, :u_id)"
            ),
            {"ws_id": ws_id, "ckey": f"usr-{u_id.hex}", "u_id": u_id},
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) VALUES (:id, 'USER', :ws_id, 'User Only', 'ACTIVE')"
            ),
            {"id": u_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) VALUES (:id, 'user', 'USER', :ws_id, 'user-only@example.com')"
            ),
            {"id": u_id, "ws_id": ws_id},
        )
        await session.commit()

    monkeypatch.setenv("KANBAN_DATABASE_URL", str(pg_worker_db.url))
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    args = argparse.Namespace(
        bundle_dir=str(FIXTURE_DIR),
        workspace=ws_slug,
        user_map=None,
        dry_run=True,
        report_out=None,
    )
    res = await _execute_import_db(args, bundle, {})
    assert res == 0
