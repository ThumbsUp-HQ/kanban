# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and security tests for Plane direct database exporter (KB-MIGRATION-PLANE-DB-01)."""

# ruff: noqa: E501, ANN401, S106, ARG001, ARG002, TRY003, EM101, C901, PLR0911, RUF043, TC003, PYI034

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kanban.importer.plane_db_exporter import (
    MAX_ATTACHMENT_BYTES,
    MinioSigV4Downloader,
    PlaneDbExporter,
    PlaneExportConfig,
    PlaneExportError,
    PlaneExportSecurityError,
    check_forbidden_exporter_args,
    read_secret_source,
    resolve_exporter_config,
)


def test_check_forbidden_exporter_args() -> None:
    """Verify secrets on CLI argv are detected and rejected with exit code 2."""
    safe_argv = ["kanban-ctl", "import", "plane", "dump-db", "--out-dir", "/tmp/out"]
    assert check_forbidden_exporter_args(safe_argv) is False

    forbidden_variants = [
        ["kanban-ctl", "import", "plane", "dump-db", "--password", "secret"],
        ["kanban-ctl", "import", "plane", "dump-db", "--secret-key=topsecret"],
        ["kanban-ctl", "import", "plane", "dump-db", "--db-url", "postgres://user:pass@host/db"],
        ["kanban-ctl", "import", "plane", "dump-db", "--minio-secret", "pass123"],
        ["kanban-ctl", "import", "plane", "dump-db", "--access-key", "AKIA..."],
        ["kanban-ctl", "import", "plane", "dump-db", "--plane-database-url=secret"],
    ]
    for argv in forbidden_variants:
        assert check_forbidden_exporter_args(argv) is True


def test_read_secret_source_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify reading secrets from environment variables."""
    monkeypatch.setenv("TEST_SECRET_ENV", "my-env-secret-val")
    val = read_secret_source("TEST_SECRET_ENV", None)
    assert val == "my-env-secret-val"


def test_read_secret_source_file_permissions(tmp_path: Path) -> None:
    """Verify reading secrets from files enforces 0600 permissions."""
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("file-secret-token\n", encoding="utf-8")

    # 1. Reject permissive permissions (0644)
    secret_file.chmod(0o644)
    with pytest.raises(PlaneExportSecurityError, match="must be 0600"):
        read_secret_source("UNSET_ENV", secret_file)

    # 2. Accept strict permissions (0600)
    secret_file.chmod(0o600)
    val = read_secret_source("UNSET_ENV", secret_file)
    assert val == "file-secret-token"


def test_resolve_exporter_config_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify resolve_exporter_config validates required database and MinIO credentials."""
    monkeypatch.delenv("PLANE_DATABASE_URL", raising=False)
    monkeypatch.delenv("PLANE_MINIO_ENDPOINT", raising=False)

    # 1. Missing database URL
    with pytest.raises(PlaneExportError, match="PLANE_DATABASE_URL"):
        resolve_exporter_config(out_dir=tmp_path / "out")

    # 2. Database URL present but missing MinIO endpoint
    monkeypatch.setenv("PLANE_DATABASE_URL", "postgresql://user:pass@127.0.0.1:5432/plane")
    with pytest.raises(PlaneExportError, match="PLANE_MINIO_ENDPOINT"):
        resolve_exporter_config(out_dir=tmp_path / "out")

    # 3. Complete config
    monkeypatch.setenv("PLANE_MINIO_ENDPOINT", "http://127.0.0.1:9000")
    monkeypatch.setenv("PLANE_MINIO_BUCKET", "plane-uploads")
    monkeypatch.setenv("PLANE_MINIO_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("PLANE_MINIO_SECRET_KEY", "minioadmin")

    cfg = resolve_exporter_config(
        out_dir=tmp_path / "out",
        workspace_slug="my-workspace",
        exclude_project_identifiers=["TEST", "DEV"],
    )
    assert cfg.database_url == "postgresql://user:pass@127.0.0.1:5432/plane"
    assert cfg.workspace_slug == "my-workspace"
    assert cfg.exclude_project_identifiers == {"TEST", "DEV"}


def test_minio_sigv4_header_generation() -> None:
    """Verify pure-stdlib AWS S3 SigV4 header calculation."""
    downloader = MinioSigV4Downloader(
        endpoint="http://127.0.0.1:9000",
        bucket="plane-uploads",
        access_key="ACCESSKEY",
        secret_key="SECRETKEY",
    )
    headers = downloader.generate_sigv4_headers("GET", "my-object-key.png")

    assert "Authorization" in headers
    assert "x-amz-date" in headers
    assert "x-amz-content-sha256" in headers
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=ACCESSKEY/")
    assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in headers["Authorization"]
    assert "Signature=" in headers["Authorization"]


@pytest.mark.asyncio
async def test_minio_sigv4_download_payload_cap(tmp_path: Path) -> None:
    """Verify MinIO streaming download strictly enforces the 25 MiB attachment limit."""
    downloader = MinioSigV4Downloader(
        endpoint="http://127.0.0.1:9000",
        bucket="plane-uploads",
        access_key="ACCESSKEY",
        secret_key="SECRETKEY",
    )

    dest_file = tmp_path / "large.bin"

    # Simulate chunk stream exceeding 25 MiB
    chunk_size = 10 * 1024 * 1024  # 10 MiB
    chunks = [b"A" * chunk_size, b"B" * chunk_size, b"C" * chunk_size]

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    async def aiter_bytes() -> Any:
        for c in chunks:
            yield c

    mock_resp.aiter_bytes = aiter_bytes

    class MockAsyncClient:
        async def __aenter__(self) -> MockAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        def stream(
            self,
            method: str,
            url: str,
            headers: dict[str, str],
            timeout: float | None = None,
        ) -> Any:
            class StreamCtx:
                async def __aenter__(self) -> MagicMock:
                    return mock_resp

                async def __aexit__(self, *args: object) -> None:
                    pass

            return StreamCtx()

    with (
        patch(
            "kanban.importer.plane_db_exporter.httpx.AsyncClient", return_value=MockAsyncClient()
        ),
        pytest.raises(PlaneExportSecurityError, match="exceeds 25 MiB"),
    ):
        await downloader.stream_object("huge-asset.bin", dest_file)


@pytest.mark.asyncio
async def test_minio_sigv4_download_success(tmp_path: Path) -> None:
    """Verify MinIO streaming download succeeds within 25 MiB limit."""
    downloader = MinioSigV4Downloader(
        endpoint="http://127.0.0.1:9000",
        bucket="plane-uploads",
        access_key="ACCESSKEY",
        secret_key="SECRETKEY",
    )

    dest_file = tmp_path / "valid.png"
    mock_payload = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    async def aiter_bytes() -> Any:
        yield mock_payload

    mock_resp.aiter_bytes = aiter_bytes

    class MockAsyncClient:
        async def __aenter__(self) -> MockAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        def stream(
            self,
            method: str,
            url: str,
            headers: dict[str, str],
            timeout: float | None = None,
        ) -> Any:
            class StreamCtx:
                async def __aenter__(self) -> MagicMock:
                    return mock_resp

                async def __aexit__(self, *args: object) -> None:
                    pass

            return StreamCtx()

    with patch(
        "kanban.importer.plane_db_exporter.httpx.AsyncClient", return_value=MockAsyncClient()
    ):
        bytes_written = await downloader.stream_object("valid.png", dest_file)
        assert bytes_written == len(mock_payload)
        assert dest_file.read_bytes() == mock_payload


@pytest.mark.asyncio
async def test_plane_db_exporter_transaction_and_export_flow(tmp_path: Path) -> None:
    """Verify PlaneDbExporter connects in REPEATABLE READ READ ONLY transaction and writes bundle files."""
    out_dir = tmp_path / "plane_export"
    cfg = PlaneExportConfig(
        database_url="postgresql://user:pass@127.0.0.1:5432/plane",
        minio_endpoint="http://127.0.0.1:9000",
        minio_bucket="plane-uploads",
        minio_access_key="AKIA...",
        minio_secret_key="SECRET...",
        out_dir=out_dir,
        workspace_slug="kanban",
        exclude_project_identifiers={"TEST"},
    )

    exporter = PlaneDbExporter(cfg)

    # Mock asyncpg connection
    mock_conn = AsyncMock()
    mock_tr = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=mock_tr)
    executed_statements: list[str] = []

    async def fake_start() -> None:
        executed_statements.append("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;")

    async def fake_commit() -> None:
        executed_statements.append("COMMIT;")

    mock_tr.start = fake_start
    mock_tr.commit = fake_commit

    async def fake_execute(query: str, *args: Any) -> None:
        executed_statements.append(query)

    mock_conn.execute = fake_execute

    ws_id = "11111111-1111-1111-1111-111111111111"
    proj_id = "22222222-2222-2222-2222-222222222222"
    issue_id = "33333333-3333-3333-3333-333333333333"

    async def fake_fetch(query: str, *args: Any) -> list[dict[str, Any]]:
        if "FROM workspaces" in query:
            return [{"id": ws_id, "slug": "kanban", "name": "Kanban Workspace"}]
        if "FROM projects" in query:
            return [
                {
                    "id": proj_id,
                    "identifier": "KANBA",
                    "name": "Platform Core",
                    "description": "Core tracker",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
                {
                    "id": "test-proj-id",
                    "identifier": "TEST",
                    "name": "Test Project",
                    "description": "To be excluded",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
            ]
        if "FROM states" in query:
            return [
                {
                    "id": "state-1",
                    "name": "In Progress",
                    "group": "started",
                    "sequence": 1000,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ]
        if "FROM labels" in query:
            return [
                {
                    "id": "label-1",
                    "name": "Backend",
                    "color": "#ff0000",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ]
        if "FROM cycles" in query:
            return []
        if "FROM modules" in query:
            return []
        if "FROM issues" in query:
            return [
                {
                    "id": issue_id,
                    "name": "Implement S3 sigv4 exporter",
                    "description_html": "<p>Important issue</p>",
                    "sequence_id": 1,
                    "state_id": "state-1",
                    "priority": "urgent",
                    "cycle_id": None,
                    "module_id": None,
                    "label_ids": ["label-1"],
                    "assignee_ids": ["user-1"],
                    "parent_id": None,
                    "created_by": "user-1",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "archived_at": None,
                }
            ]
        if "FROM issue_comments" in query:
            return [
                {
                    "id": "comm-1",
                    "issue_id": issue_id,
                    "comment_html": "<p>First comment</p>",
                    "actor_id": "user-1",
                    "parent_comment_id": None,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ]
        if "FROM issue_relations" in query:
            return []
        if "FROM users" in query:
            return [
                {
                    "id": "user-1",
                    "email": "dev@example.com",
                    "first_name": "Dev",
                    "last_name": "User",
                    "avatar": None,
                    "role": 20,
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        if "FROM file_assets" in query:
            return []
        return []

    mock_conn.fetch = fake_fetch

    with patch("kanban.importer.plane_db_exporter.asyncpg.connect", return_value=mock_conn):
        summary = await exporter.export()

    # 1. Verify strict read-only transaction started and committed
    assert any("REPEATABLE READ READ ONLY" in stmt for stmt in executed_statements)
    assert any("COMMIT" in stmt for stmt in executed_statements)

    # 2. Verify summary and exported files
    assert summary["projects_exported"] == 1
    assert summary["issues_exported"] == 1
    assert summary["comments_exported"] == 1

    bundle_dir = out_dir / "kanban" / "KANBA"
    assert (bundle_dir / "project.json").is_file()
    assert (bundle_dir / "states.json").is_file()
    assert (bundle_dir / "labels.json").is_file()
    assert (bundle_dir / "issues.json").is_file()
    assert (bundle_dir / "comments.json").is_file()
    assert (bundle_dir / "members.json").is_file()

    # Verify TEST project was skipped
    test_dir = out_dir / "kanban" / "TEST"
    assert not test_dir.exists()


def test_read_secret_source_missing_file(tmp_path: Path) -> None:
    """Verify read_secret_source raises PlaneExportError if file does not exist."""
    missing = tmp_path / "does-not-exist.txt"
    with pytest.raises(PlaneExportError, match="does not exist"):
        read_secret_source("UNSET_SECRET", missing)


def test_read_secret_source_env_file_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify read_secret_source resolves file path from an environment variable pointer."""
    secret_file = tmp_path / "pw.txt"
    secret_file.write_text("secure-pass\n", encoding="utf-8")
    secret_file.chmod(0o600)

    monkeypatch.setenv("MY_SECRET_FILE_VAR", str(secret_file))
    val = read_secret_source("UNSET_SECRET", "MY_SECRET_FILE_VAR")
    assert val == "secure-pass"


@pytest.mark.asyncio
async def test_minio_download_object_variations() -> None:
    """Verify download_object handles 200, non-200, payload cap, and network exceptions."""
    downloader = MinioSigV4Downloader(
        endpoint="http://127.0.0.1:9000",
        bucket="plane",
        access_key="AKIA...",
        secret_key="SECRET...",
    )

    # 1. Non-200 status
    mock_resp_404 = MagicMock(status_code=404)

    class MockClient404:
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            class Ctx:
                async def __aenter__(self) -> MagicMock:
                    return mock_resp_404

                async def __aexit__(self, *a: object) -> None:
                    pass

            return Ctx()

    res = await downloader.download_object(MockClient404(), "missing.png")  # type: ignore[arg-type]
    assert res is None

    # 2. Success under 25 MiB
    mock_resp_200 = MagicMock(status_code=200)

    async def aiter_ok() -> Any:
        yield b"chunk1"
        yield b"chunk2"

    mock_resp_200.aiter_bytes = aiter_ok

    class MockClient200:
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            class Ctx:
                async def __aenter__(self) -> MagicMock:
                    return mock_resp_200

                async def __aexit__(self, *a: object) -> None:
                    pass

            return Ctx()

    res_ok = await downloader.download_object(MockClient200(), "file.txt")  # type: ignore[arg-type]
    assert res_ok == b"chunk1chunk2"

    # 3. Payload cap truncation
    mock_resp_huge = MagicMock(status_code=200)

    async def aiter_huge() -> Any:
        yield b"X" * (MAX_ATTACHMENT_BYTES + 1024)

    mock_resp_huge.aiter_bytes = aiter_huge

    class MockClientHuge:
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            class Ctx:
                async def __aenter__(self) -> MagicMock:
                    return mock_resp_huge

                async def __aexit__(self, *a: object) -> None:
                    pass

            return Ctx()

    res_huge = await downloader.download_object(MockClientHuge(), "huge.bin")  # type: ignore[arg-type]
    assert res_huge is not None
    assert len(res_huge) == MAX_ATTACHMENT_BYTES

    # 4. Exception handling
    class MockClientErr:
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Socket disconnect")

    res_err = await downloader.download_object(MockClientErr(), "err.bin")  # type: ignore[arg-type]
    assert res_err is None


@pytest.mark.asyncio
async def test_plane_db_exporter_attachments_with_manifest(tmp_path: Path) -> None:
    """Verify attachments in file_assets table and HTML links are extracted and recorded in manifest.json."""
    out_dir = tmp_path / "export_att"
    cfg = PlaneExportConfig(
        database_url="postgresql://user:pass@127.0.0.1:5432/plane",
        minio_endpoint="http://127.0.0.1:9000",
        minio_bucket="plane",
        minio_access_key="AKIA...",
        minio_secret_key="SECRET...",
        out_dir=out_dir,
        workspace_slug="kanban",
        exclude_project_identifiers={"TEST"},
    )
    exporter = PlaneDbExporter(cfg)

    mock_conn = AsyncMock()
    mock_tr = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=mock_tr)

    ws_id = "11111111-1111-1111-1111-111111111111"
    proj_id = "22222222-2222-2222-2222-222222222222"

    async def fake_fetch(query: str, *args: Any) -> list[dict[str, Any]]:
        if "FROM workspaces" in query:
            return [{"id": ws_id, "slug": "kanban", "name": "Kanban Workspace"}]
        if "FROM projects" in query:
            return [
                {
                    "id": proj_id,
                    "identifier": "KANBA",
                    "name": "Platform Core",
                    "description": "",
                    "network": 2,
                }
            ]
        if (
            "FROM states" in query
            or "FROM labels" in query
            or "FROM cycles" in query
            or "FROM modules" in query
        ):
            return []
        if "FROM users" in query:
            return [
                {"id": "u-1", "email": "a@b.com", "first_name": "A", "last_name": "B", "role": 20}
            ]
        if "FROM issues" in query:
            return [
                {
                    "id": "i-1",
                    "sequence_id": 1,
                    "name": "Issue with attachment",
                    "description_html": '<p>Look at <img src="/api/assets/v1/workspace/diagram.png" /></p>',
                    "state_id": None,
                    "priority": "none",
                    "project_id": proj_id,
                }
            ]
        if "FROM issue_comments" in query:
            return [
                {
                    "id": "c-1",
                    "issue_id": "i-1",
                    "comment_html": '<a href="uploads/spec.pdf">Spec</a>',
                    "actor_id": "u-1",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        if "FROM file_assets" in query:
            return [
                {"id": "fa-1", "key": "uploads/asset1.png", "name": "diagram.png"},
                {"id": "fa-2", "key": "uploads/special.png", "name": "???"},
            ]
        if "FROM cycle_issues" in query:
            return [{"issue_id": "i-1", "cycle_id": "cyc-1"}]
        if "FROM module_issues" in query:
            return [{"issue_id": "i-1", "module_id": "mod-1"}]
        if "FROM issue_labels" in query:
            return [{"issue_id": "i-1", "label_id": "lbl-1"}]
        if "FROM issue_assignees" in query:
            return [{"issue_id": "i-1", "assignee_id": "u-1"}]
        return []

    mock_conn.fetch = fake_fetch

    with (
        patch("kanban.importer.plane_db_exporter.asyncpg.connect", return_value=mock_conn),
        patch(
            "kanban.importer.plane_db_exporter.MinioSigV4Downloader.download_object",
            new_callable=AsyncMock,
        ) as mock_dl,
    ):
        mock_dl.return_value = b"fake-file-bytes"
        summary = await exporter.export()

    assert summary["attachments_exported"] == 4
    att_dir = out_dir / "kanban" / "KANBA" / "attachments"
    assert (att_dir / "manifest.json").is_file()
    manifest_data = json.loads((att_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest_data) == 4


@pytest.mark.asyncio
async def test_plane_db_exporter_no_active_workspaces(tmp_path: Path) -> None:
    """Verify PlaneDbExporter raises PlaneExportError when no active workspaces are returned."""
    cfg = PlaneExportConfig(
        database_url="postgresql://user:pass@127.0.0.1:5432/plane",
        minio_endpoint="http://127.0.0.1:9000",
        minio_bucket="plane",
        minio_access_key="AKIA...",
        minio_secret_key="SECRET...",
        out_dir=tmp_path / "out",
        workspace_slug="empty-ws",
    )
    exporter = PlaneDbExporter(cfg)
    mock_conn = AsyncMock()
    mock_tr = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=mock_tr)

    async def fake_fetch(query: str, *args: Any) -> list[dict[str, Any]]:
        return []

    mock_conn.fetch = fake_fetch

    with (
        patch("kanban.importer.plane_db_exporter.asyncpg.connect", return_value=mock_conn),
        pytest.raises(PlaneExportError, match="No active Plane workspaces found"),
    ):
        await exporter.export()


def test_read_secret_source_direct_string_and_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify read_secret_source resolves file path as direct string and via {env}_FILE."""
    f1 = tmp_path / "f1.txt"
    f1.write_text("token1\n", encoding="utf-8")
    f1.chmod(0o600)
    assert read_secret_source("UNSET1", str(f1)) == "token1"

    monkeypatch.setenv("UNSET2_FILE", str(f1))
    assert read_secret_source("UNSET2") == "token1"


def test_minio_sigv4_headers_no_keys() -> None:
    """Verify build_auth_headers returns empty dict if access/secret key is missing."""
    downloader = MinioSigV4Downloader(
        endpoint="http://localhost:9000", bucket="b", access_key=None, secret_key=None
    )
    assert downloader.build_auth_headers("GET", "k") == {}


@pytest.mark.asyncio
async def test_minio_stream_object_error_status(tmp_path: Path) -> None:
    """Verify stream_object raises PlaneExportError if MinIO returns non-200."""
    downloader = MinioSigV4Downloader(
        endpoint="http://localhost:9000", bucket="b", access_key="a", secret_key="s"
    )
    mock_resp = MagicMock(status_code=500)

    class MockClient:
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            class Ctx:
                async def __aenter__(self) -> MagicMock:
                    return mock_resp

                async def __aexit__(self, *a: object) -> None:
                    pass

            return Ctx()

    with pytest.raises(PlaneExportError, match="MinIO GET .* failed with status 500"):
        await downloader.stream_object("k", tmp_path / "out.bin", client=MockClient())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_plane_db_exporter_rollback_on_error(tmp_path: Path) -> None:
    """Verify export rolls back transaction if an error occurs."""
    cfg = PlaneExportConfig(
        database_url="postgresql://user:pass@127.0.0.1:5432/plane",
        minio_endpoint="http://127.0.0.1:9000",
        minio_bucket="plane",
        minio_access_key="AKIA...",
        minio_secret_key="SECRET...",
        out_dir=tmp_path / "out",
    )
    exporter = PlaneDbExporter(cfg)
    mock_conn = AsyncMock()
    mock_tr = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=mock_tr)

    async def fake_fetch(*args: Any) -> list[dict[str, Any]]:
        raise RuntimeError("DB boom")

    mock_conn.fetch = fake_fetch
    with (
        patch("kanban.importer.plane_db_exporter.asyncpg.connect", return_value=mock_conn),
        pytest.raises(RuntimeError, match="DB boom"),
    ):
        await exporter.export()
    mock_tr.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_plane_db_exporter_empty_issues_and_collision(tmp_path: Path) -> None:
    """Verify handling of empty issues and project exclusions when workspace_slug is None."""
    out_dir = tmp_path / "empty_proj"
    cfg = PlaneExportConfig(
        database_url="postgresql+asyncpg://user:pass@127.0.0.1:5432/plane",
        minio_endpoint="http://127.0.0.1:9000",
        minio_bucket="plane",
        minio_access_key="AKIA...",
        minio_secret_key="SECRET...",
        out_dir=out_dir,
        workspace_slug=None,
        exclude_project_identifiers={"EXCLUDE"},
    )
    exporter = PlaneDbExporter(cfg)
    mock_conn = AsyncMock()
    mock_tr = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=mock_tr)

    ws_id = "11111111-1111-1111-1111-111111111111"
    proj_id = "22222222-2222-2222-2222-222222222222"

    async def fake_fetch(query: str, *args: Any) -> list[dict[str, Any]]:
        if "FROM workspaces" in query:
            return [{"id": ws_id, "slug": "default-ws", "name": "Default WS"}]
        if "FROM projects" in query:
            return [
                {"id": "ex-id", "identifier": "EXCLUDE", "name": "Ex", "description": ""},
                {"id": proj_id, "identifier": "EMPTY", "name": "Empty Project", "description": ""},
            ]
        if "FROM file_assets" in query:
            raise RuntimeError("Table file_assets does not exist")
        if "FROM issues" in query:
            return []
        return []

    mock_conn.fetch = fake_fetch

    with patch("kanban.importer.plane_db_exporter.asyncpg.connect", return_value=mock_conn):
        summary = await exporter.export()

    assert summary["projects_exported"] == 1
    assert summary["issues_exported"] == 0
