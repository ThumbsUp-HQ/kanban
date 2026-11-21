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
    assert ctl_main(["import", "plane", "dump-db", "--help"]) == 0


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

    args_no_map = argparse.Namespace(
        bundle_dir=str(FIXTURE_DIR),
        workspace="my-ws",
        user_map=None,
        dry_run=True,
        report_out=None,
    )
    with patch("kanban.cli.import_plane.asyncio.run", side_effect=fake_run):
        assert _run_plane_import(args_no_map) == 0


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


def test_run_plane_import_user_map_loading(tmp_path: Path) -> None:
    """Test loading valid dict and non-dict user map YAML files."""
    user_map_file = tmp_path / "users.yaml"
    user_map_file.write_text("u-plane-1: admin\n", encoding="utf-8")

    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    args = argparse.Namespace(
        bundle_dir=str(bundle_dir),
        workspace="ws-test",
        user_map=str(user_map_file),
    )

    with (
        patch("kanban.cli.import_plane.PlaneClient.load_bundle_from_dir") as mock_load,
        patch("kanban.cli.import_plane._execute_import_db", new_callable=AsyncMock) as mock_exec,
    ):
        mock_load.return_value = None
        mock_exec.return_value = 0
        code = _run_plane_import(args)
        assert code == 0

    # Non-dict YAML file
    list_map_file = tmp_path / "list_users.yaml"
    list_map_file.write_text("- item1\n- item2\n", encoding="utf-8")
    args_list = argparse.Namespace(
        bundle_dir=str(bundle_dir),
        workspace="ws-test",
        user_map=str(list_map_file),
    )
    with (
        patch("kanban.cli.import_plane.PlaneClient.load_bundle_from_dir") as mock_load,
        patch("kanban.cli.import_plane._execute_import_db", new_callable=AsyncMock) as mock_exec,
    ):
        mock_load.return_value = None
        mock_exec.return_value = 0
        code = _run_plane_import(args_list)
        assert code == 0


def test_run_dump_db_forbidden_args(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test dump-db CLI rejects forbidden secrets in argv."""
    from kanban.cli.import_plane import _run_dump_db

    monkeypatch.setattr(
        "sys.argv", ["kanban-ctl", "import", "plane", "dump-db", "--password", "secret"]
    )
    args = argparse.Namespace(
        out_dir=str(tmp_path / "out"), workspace_slug=None, exclude_project_identifiers="TEST"
    )
    assert _run_dump_db(args) == 2


def test_run_dump_db_missing_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test dump-db CLI returns exit code 2 on missing environment variables."""
    from kanban.cli.import_plane import _run_dump_db

    monkeypatch.setattr(
        "sys.argv", ["kanban-ctl", "import", "plane", "dump-db", "--out-dir", str(tmp_path)]
    )
    monkeypatch.delenv("PLANE_DATABASE_URL", raising=False)
    args = argparse.Namespace(
        out_dir=str(tmp_path / "out"), workspace_slug=None, exclude_project_identifiers="TEST"
    )
    assert _run_dump_db(args) == 2


def test_run_dump_db_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test dump-db CLI executes export successfully and returns 0."""
    from kanban.cli.import_plane import _run_dump_db

    monkeypatch.setattr(
        "sys.argv", ["kanban-ctl", "import", "plane", "dump-db", "--out-dir", str(tmp_path)]
    )
    monkeypatch.setenv("PLANE_DATABASE_URL", "postgresql://user:pass@127.0.0.1:5432/plane")
    monkeypatch.setenv("PLANE_MINIO_ENDPOINT", "http://127.0.0.1:9000")

    summary = {
        "projects_exported": 2,
        "issues_exported": 50,
        "comments_exported": 20,
        "attachments_exported": 5,
        "out_dir": str(tmp_path),
    }

    with patch(
        "kanban.importer.plane_db_exporter.PlaneDbExporter.export", new_callable=AsyncMock
    ) as mock_exp:
        mock_exp.return_value = summary
        args = argparse.Namespace(
            out_dir=str(tmp_path), workspace_slug="ws", exclude_project_identifiers="TEST"
        )
        assert _run_dump_db(args) == 0


def test_run_dump_db_exception_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test dump-db exception branches returning 2 for export errors and 1 for unexpected errors."""
    from kanban.cli.import_plane import _run_dump_db
    from kanban.importer.plane_db_exporter import PlaneExportError, PlaneExportSecurityError

    monkeypatch.setattr(
        "sys.argv", ["kanban-ctl", "import", "plane", "dump-db", "--out-dir", str(tmp_path)]
    )
    monkeypatch.setenv("PLANE_DATABASE_URL", "postgresql://user:pass@127.0.0.1:5432/plane")
    monkeypatch.setenv("PLANE_MINIO_ENDPOINT", "http://127.0.0.1:9000")
    args = argparse.Namespace(
        out_dir=str(tmp_path), workspace_slug="ws", exclude_project_identifiers="TEST"
    )

    # 1. PlaneExportSecurityError -> 2
    with patch(
        "kanban.importer.plane_db_exporter.PlaneDbExporter.export",
        side_effect=PlaneExportSecurityError("Forbidden"),
    ):
        assert _run_dump_db(args) == 2

    # 2. PlaneExportError -> 2
    with patch(
        "kanban.importer.plane_db_exporter.PlaneDbExporter.export",
        side_effect=PlaneExportError("Export failed"),
    ):
        assert _run_dump_db(args) == 2

    # 3. RuntimeError -> 1
    with patch(
        "kanban.importer.plane_db_exporter.PlaneDbExporter.export",
        side_effect=RuntimeError("Unexpected boom"),
    ):
        assert _run_dump_db(args) == 1


def test_get_admin_dsn_socket_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _get_admin_dsn socket directory resolution branches."""
    monkeypatch.delenv("KANBAN_ADMIN_DATABASE_URL", raising=False)
    monkeypatch.delenv("KANBAN_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("KB_TEST_PGHOST", raising=False)

    # 1. Custom socket via env
    monkeypatch.setenv("KB_TEST_PGHOST", "/var/custom/socket")
    assert "host=/var/custom/socket" in _get_admin_dsn()
    monkeypatch.delenv("KB_TEST_PGHOST", raising=False)

    # 2. /run/postgresql is_dir
    with patch.object(
        Path, "is_dir", autospec=True, side_effect=lambda self: str(self) == "/run/postgresql"
    ):
        dsn1 = _get_admin_dsn()
        assert "host=/run/postgresql" in dsn1

    # 3. /tmp/kb-pgsock is_dir
    with patch.object(
        Path, "is_dir", autospec=True, side_effect=lambda self: str(self) == "/tmp/kb-pgsock"
    ):
        dsn2 = _get_admin_dsn()
        assert "host=/tmp/kb-pgsock" in dsn2

    # 4. Fallback when neither exists
    with patch.object(Path, "is_dir", autospec=True, return_value=False):
        dsn3 = _get_admin_dsn()
        assert "host=/run/postgresql" in dsn3


def test_run_generic_import_input_validation(tmp_path: Path) -> None:
    """Test generic source import argument validation and file parsing."""
    from kanban.cli.import_plane import _run_generic_import

    # 1. Missing both file and bundle-dir
    args_empty = argparse.Namespace(file=None, bundle_dir=None)
    assert _run_generic_import(args_empty, "jira") == 2

    # 2. Path not found
    args_not_found = argparse.Namespace(file=str(tmp_path / "nonexistent.json"), bundle_dir=None)
    assert _run_generic_import(args_not_found, "jira") == 2

    # 3. Invalid JSON file
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{invalid json", encoding="utf-8")
    args_bad_json = argparse.Namespace(file=str(bad_json), bundle_dir=None)
    assert _run_generic_import(args_bad_json, "jira") == 2

    # 4. Invalid user map file
    good_json = tmp_path / "good.json"
    good_json.write_text('{"issues": []}', encoding="utf-8")
    args_bad_user_map = argparse.Namespace(
        file=str(good_json),
        bundle_dir=None,
        user_map=str(tmp_path / "missing_user_map.yaml"),
    )
    assert _run_generic_import(args_bad_user_map, "jira") == 2

    bad_user_map = tmp_path / "bad_user_map.yaml"
    bad_user_map.write_text("not: valid: yaml: :", encoding="utf-8")
    args_corrupt_user_map = argparse.Namespace(
        file=str(good_json),
        bundle_dir=None,
        user_map=str(bad_user_map),
    )
    assert _run_generic_import(args_corrupt_user_map, "jira") == 2

    # 5. Empty directory (no valid export files)
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    args_empty_dir = argparse.Namespace(file=None, bundle_dir=str(empty_dir), user_map=None)
    assert _run_generic_import(args_empty_dir, "jira") == 2

    # 6. Directory with bad JSON candidate
    dir_bad_cand = tmp_path / "dir_bad_cand"
    dir_bad_cand.mkdir()
    (dir_bad_cand / "issues.json").write_text("{bad json", encoding="utf-8")
    args_dir_bad_cand = argparse.Namespace(file=None, bundle_dir=str(dir_bad_cand), user_map=None)
    assert _run_generic_import(args_dir_bad_cand, "jira") == 2


def test_run_generic_import_dispatch_and_execution(tmp_path: Path) -> None:
    """Test generic source import execution across sources, dry-run, and error handling."""
    from kanban.cli.import_plane import _run_generic_import

    good_json = tmp_path / "export.json"
    good_json.write_text('{"issues": []}', encoding="utf-8")

    user_map_file = tmp_path / "user_map.yaml"
    user_map_file.write_text("old_id: new_handle\n", encoding="utf-8")

    async def _dummy_exec(*_args: object, **_kwargs: object) -> int:
        return 0

    # 1. Successful file-based dispatch into _execute_generic_import_db
    with patch(
        "kanban.cli.import_plane._execute_generic_import_db", side_effect=_dummy_exec
    ) as mock_exec:
        args = argparse.Namespace(
            file=str(good_json),
            bundle_dir=None,
            user_map=str(user_map_file),
            workspace="kanban",
            dry_run=True,
            project_key="JIRA",
            report_out=None,
        )
        code = _run_generic_import(args, "jira")
        assert code == 0
        assert mock_exec.called

    # 2. Directory-based CSV dispatch for Linear
    bundle_dir = tmp_path / "bundle_dir"
    bundle_dir.mkdir()
    (bundle_dir / "linear.csv").write_text("id,title\n1,Issue\n", encoding="utf-8")
    with patch(
        "kanban.cli.import_plane._execute_generic_import_db", side_effect=_dummy_exec
    ) as mock_exec:
        args = argparse.Namespace(
            file=None,
            bundle_dir=str(bundle_dir),
            user_map=None,
            workspace="kanban",
            dry_run=False,
            project_key="LIN",
            report_out=None,
        )
        code = _run_generic_import(args, "linear")
        assert code == 0
        assert mock_exec.called


@pytest.mark.asyncio
async def test_execute_generic_import_db_branches(
    pg_worker_db: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test _execute_generic_import_db database branches: workspace missing, sources, integrity, and runtime errors."""
    from kanban.cli.import_plane import _execute_generic_import_db
    from kanban.importer.plane_mapper import ImportDiffReport

    factory = RLSSessionFactory(pg_worker_db)
    ws_id = uuid.uuid4()
    ws_slug = f"gen-ws-{ws_id.hex[:8]}"
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)

    async with factory.session(anon_ctx) as session:
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Generic WS')"),
            {"id": ws_id, "slug": ws_slug},
        )
        u_id = uuid.uuid4()
        await session.execute(
            text(
                "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'Generic Admin', :u_id, :u_id)"
            ),
            {"ws_id": ws_id, "ckey": f"usr-{u_id.hex}", "u_id": u_id},
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) VALUES (:id, 'USER', :ws_id, 'Generic Admin', 'ACTIVE')"
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

    monkeypatch.setenv("KANBAN_DATABASE_URL", str(pg_worker_db.url))

    report = ImportDiffReport()
    report.to_create = 2
    report.warnings = ["Test warning"]

    report_out_path = tmp_path / "report_out.json"
    args = argparse.Namespace(
        workspace=ws_slug,
        project_key="KEY",
        dry_run=False,
        report_out=str(report_out_path),
    )

    # 1. Workspace not found
    args_bad_ws = argparse.Namespace(
        workspace="nonexistent_ws_slug",
        project_key="KEY",
        dry_run=False,
        report_out=None,
    )
    assert await _execute_generic_import_db(args_bad_ws, "jira", {}, {}) == 2

    # 2. Success across jira, github, linear
    for src, importer_cls in [
        ("jira", "JiraImporter"),
        ("github", "GitHubIssuesImporter"),
        ("linear", "LinearImporter"),
    ]:
        with patch(
            f"kanban.cli.import_plane.{importer_cls}.run_import", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = report
            code = await _execute_generic_import_db(args, src, {}, {})
            assert code == 0

    # 3. Unsupported source
    assert await _execute_generic_import_db(args, "unsupported_source", {}, {}) == 2

    # 4. ImportIntegrityError
    with patch(
        "kanban.cli.import_plane.JiraImporter.run_import", new_callable=AsyncMock
    ) as mock_run:
        mock_run.side_effect = ImportIntegrityError("Integrity violation")
        assert await _execute_generic_import_db(args, "jira", {}, {}) == 2

    # 5. Runtime error
    with patch(
        "kanban.cli.import_plane.JiraImporter.run_import", new_callable=AsyncMock
    ) as mock_run:
        mock_run.side_effect = RuntimeError("Fatal crash")
        assert await _execute_generic_import_db(args, "jira", {}, {}) == 1
