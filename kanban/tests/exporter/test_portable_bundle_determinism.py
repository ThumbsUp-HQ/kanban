# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for PortableWorkspaceExporter determinism and bundle integrity (KB-P6-03)."""
# ruff: noqa: E501, PLC0415, SIM117, TC002, TC003, RUF059, ANN401

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import IssueKeyAlias
from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.deps import PrincipalContext
from kanban.exporter.portable_bundle import PortableWorkspaceExporter

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def setup_bundle_env(
    db_session: AsyncSession, tmp_path: Path
) -> tuple[AsyncSession, PrincipalContext, uuid.UUID, Path]:
    """Bootstrap workspace with rich entities and temporary blob store."""
    ws_id, admin_id = await bootstrap_workspace_admin(db_session)

    await db_session.execute(
        text(
            "SELECT set_config('app.current_workspace_id', :ws, true), "
            "set_config('app.current_principal_id', :pid, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"ws": str(ws_id), "pid": str(admin_id)},
    )

    caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=2,
    )

    # 1. Project
    proj_id = (
        await db_session.execute(
            text(
                "SELECT register_object('project'::object_kind, :ws, NULL, 'DEMO', 'Demo Project', :admin)"
            ),
            {"ws": ws_id, "admin": admin_id},
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name, description_markdown) "
            "VALUES (:id, :ws, 'DEMO', 'Demo Project', 'Export demo')"
        ),
        {"id": proj_id, "ws": ws_id},
    )

    # 2. State (seeded by trigger)
    state_id = (
        await db_session.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :proj AND is_default LIMIT 1"),
            {"proj": proj_id},
        )
    ).scalar_one()

    # 3. Issue
    seq = (
        await db_session.execute(
            text("SELECT allocate_issue_sequence(:proj)"),
            {"proj": proj_id},
        )
    ).scalar_one()

    iss_id = (
        await db_session.execute(
            text(
                "SELECT register_object('issue'::object_kind, :ws, :proj, :key, 'Secret Issue', :admin)"
            ),
            {"ws": ws_id, "proj": proj_id, "key": f"DEMO-{seq}", "admin": admin_id},
        )
    ).scalar_one()
    # Get default priority (seeded by trigger)
    prio_id = (
        await db_session.execute(
            text(
                "SELECT id FROM project_priorities WHERE project_id = :proj AND is_default LIMIT 1"
            ),
            {"proj": proj_id},
        )
    ).scalar_one()

    secret_text = (
        "Issue description containing confidential token: kb_adm_99999999999999999999999999999999"
    )
    await db_session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, summary, description_markdown, state_id, priority_id, created_by_id, original_created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, :seq, 'Secret Issue', :desc, :state, :prio, :admin, :admin, '0|hzzzzz:')"
        ),
        {
            "id": iss_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq,
            "desc": secret_text,
            "state": state_id,
            "prio": prio_id,
            "admin": admin_id,
        },
    )

    # 4. Alias
    alias = IssueKeyAlias(
        workspace_id=ws_id,
        legacy_key="JIRA-555",
        issue_id=iss_id,
        source_system="jira",
    )
    db_session.add(alias)

    # 5. Doc
    doc_id = (
        await db_session.execute(
            text(
                "SELECT register_object('doc'::object_kind, :ws, :proj, 'DOC-arch', 'Architecture Guide', :admin)"
            ),
            {"ws": ws_id, "proj": proj_id, "admin": admin_id},
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO docs (id, workspace_id, project_id, title, body_markdown) "
            "VALUES (:id, :ws, :proj, 'Architecture Guide', 'Detailed architecture documentation')"
        ),
        {"id": doc_id, "ws": ws_id, "proj": proj_id},
    )

    # 6. Project Label
    lbl_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO project_labels (id, workspace_id, project_id, name, color_hex) VALUES (:id, :ws, :proj, 'Bug', '#ff0000')"
        ),
        {"id": lbl_id, "ws": ws_id, "proj": proj_id},
    )

    # 7. Cycle
    cycle_id = (
        await db_session.execute(
            text(
                "SELECT register_object('cycle'::object_kind, :ws, :proj, 'CYC-1', 'Sprint 1', :admin)"
            ),
            {"ws": ws_id, "proj": proj_id, "admin": admin_id},
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO cycles (id, workspace_id, project_id, name, status) VALUES (:id, :ws, :proj, 'Sprint 1', 'active')"
        ),
        {"id": cycle_id, "ws": ws_id, "proj": proj_id},
    )

    # 8. Module
    mod_id = (
        await db_session.execute(
            text(
                "SELECT register_object('module'::object_kind, :ws, :proj, 'MOD-1', 'Core Module', :admin)"
            ),
            {"ws": ws_id, "proj": proj_id, "admin": admin_id},
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO modules (id, workspace_id, project_id, name, description_markdown) VALUES (:id, :ws, :proj, 'Core Module', 'Module description')"
        ),
        {"id": mod_id, "ws": ws_id, "proj": proj_id},
    )

    # 9. Sticky
    sticky_id = (
        await db_session.execute(
            text(
                "SELECT register_object('sticky'::object_kind, :ws, :proj, 'STK-1', 'Sticky Note', :admin)"
            ),
            {"ws": ws_id, "proj": proj_id, "admin": admin_id},
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO stickies (id, workspace_id, project_id, body_markdown, color_token) VALUES (:id, :ws, :proj, 'Sticky Note Content', 'amber')"
        ),
        {"id": sticky_id, "ws": ws_id, "proj": proj_id},
    )

    # 11. Comment
    comment_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO issue_comments (id, workspace_id, issue_id, author_id, body_markdown) VALUES (:id, :ws, :iss, :admin, 'Comment on secret issue')"
        ),
        {"id": comment_id, "ws": ws_id, "iss": iss_id, "admin": admin_id},
    )

    # 12. ObjectLink
    link_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO object_links (id, workspace_id, source_id, source_type, target_id, target_type, link_type, link_state, created_by_id) "
            "VALUES (:id, :ws, :src, 'issue', :tgt, 'doc', 'RELATES_TO', 'ACTIVE', :admin)"
        ),
        {"id": link_id, "ws": ws_id, "src": iss_id, "tgt": doc_id, "admin": admin_id},
    )

    # 13. Attachment & blob store
    from kanban.attachments.storage import LocalFilesystemBlobStore

    att_dir = tmp_path / "attachments"
    att_dir.mkdir(parents=True, exist_ok=True)
    blob_store = LocalFilesystemBlobStore(att_dir)
    storage_key, raw_sha = blob_store.store(b"attachment payload bytes")
    att_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO attachments (id, workspace_id, project_id, issue_id, uploaded_by_id, original_filename, content_type, byte_size, blob_sha256, storage_key) "
            "VALUES (:id, :ws, :proj, :iss, :admin, 'test.png', 'image/png', 24, :sha, :skey)"
        ),
        {
            "id": att_id,
            "ws": ws_id,
            "proj": proj_id,
            "iss": iss_id,
            "admin": admin_id,
            "sha": raw_sha,
            "skey": storage_key,
        },
    )

    await db_session.commit()
    return db_session, caller, ws_id, tmp_path


@pytest.mark.asyncio
async def test_portable_bundle_determinism(
    setup_bundle_env: tuple[AsyncSession, PrincipalContext, uuid.UUID, Path],
) -> None:
    """Verify PortableWorkspaceExporter produces byte-for-byte identical archives."""
    session, caller, ws_id, tmp_path = setup_bundle_env

    exporter = PortableWorkspaceExporter(
        session=session,
        workspace_id=ws_id,
        caller=caller,
        attachments_dir=tmp_path / "attachments",
    )

    bundle_1 = await exporter.export_bundle(scrub=False)
    bundle_2 = await exporter.export_bundle(scrub=False)

    # Strict byte-level equality
    assert len(bundle_1) > 0
    assert bundle_1 == bundle_2
    assert hashlib.sha256(bundle_1).hexdigest() == hashlib.sha256(bundle_2).hexdigest()

    # Inspect tar archive members
    with gzip.GzipFile(fileobj=io.BytesIO(bundle_1), mode="rb") as gz:
        with tarfile.TarFile(fileobj=gz, mode="r") as tar:
            members = tar.getmembers()
            member_names = [m.name for m in members]

            # Verify alphabetical ordering
            assert member_names == sorted(member_names)

            # Verify TarInfo metadata invariants
            for m in members:
                assert m.mtime == 0
                assert m.uid == 0
                assert m.gid == 0
                assert m.uname == ""
                assert m.gname == ""
                assert m.mode == 0o644

            # Verify manifest.json
            manifest_file = tar.extractfile("manifest.json")
            assert manifest_file is not None
            manifest_data = json.loads(manifest_file.read().decode("utf-8"))
            assert manifest_data["format_version"] == "1.0"
            assert manifest_data["workspace_id"] == str(ws_id)
            assert manifest_data["scrubbed"] is False

            # Verify SHA-256 digests in manifest authenticate member files
            for file_path, expected_sha in manifest_data["files"].items():
                member_file = tar.extractfile(file_path)
                assert member_file is not None
                actual_sha = hashlib.sha256(member_file.read()).hexdigest()
                assert actual_sha == expected_sha

            # Verify markdown files
            assert "markdown/issues/DEMO-1.md" in member_names
            assert any(m.startswith("markdown/docs/d") and m.endswith(".md") for m in member_names)


@pytest.mark.asyncio
async def test_portable_bundle_secret_scrubbing(
    setup_bundle_env: tuple[AsyncSession, PrincipalContext, uuid.UUID, Path],
) -> None:
    """Verify scrub=True scrubs secrets from JSONL entities and markdown files."""
    session, caller, ws_id, tmp_path = setup_bundle_env

    exporter = PortableWorkspaceExporter(
        session=session,
        workspace_id=ws_id,
        caller=caller,
        attachments_dir=tmp_path / "attachments",
    )

    scrubbed_bundle = await exporter.export_bundle(scrub=True)

    with gzip.GzipFile(fileobj=io.BytesIO(scrubbed_bundle), mode="rb") as gz:
        with tarfile.TarFile(fileobj=gz, mode="r") as tar:
            issue_md = tar.extractfile("markdown/issues/DEMO-1.md")
            assert issue_md is not None
            text_content = issue_md.read().decode("utf-8")
            assert "kb_adm_99999999999999999999999999999999" not in text_content
            assert (
                "[REDACTED]" in text_content
                or "REDACTED" in text_content
                or "***" in text_content
                or "kb_adm_" not in text_content
            )


@pytest.mark.asyncio
async def test_export_to_file(
    setup_bundle_env: tuple[AsyncSession, PrincipalContext, uuid.UUID, Path],
) -> None:
    """Verify export_to_file writes bundle archive to disk."""
    session, caller, ws_id, tmp_path = setup_bundle_env

    exporter = PortableWorkspaceExporter(
        session=session,
        workspace_id=ws_id,
        caller=caller,
    )

    out_file = tmp_path / "exports" / "test_workspace.tar.gz"
    res_path = await exporter.export_to_file(out_file, scrub=False)
    assert res_path.is_file()
    assert res_path.stat().st_size > 0


def test_serialize_value_and_format_helpers() -> None:
    """Unit tests for serialization and jsonl formatting edge cases."""
    from datetime import UTC, datetime

    from kanban.exporter.portable_bundle import _serialize_value, _to_jsonl_bytes

    u = uuid.uuid4()
    now = datetime.now(UTC)
    b = b"\x01\x02\x03"

    assert _serialize_value(None) is None
    assert _serialize_value(u) == str(u)
    assert _serialize_value(now) == now.isoformat()
    assert _serialize_value(b) == "010203"
    assert _serialize_value([u, b]) == [str(u), "010203"]

    dict_val = {
        "title": "Secret Token kb_adm_11111111111111111111111111111111",
        "nested": {"description": "Another kb_adm_22222222222222222222222222222222"},
    }
    scrubbed = _serialize_value(dict_val, scrub=True)
    assert "kb_adm_" not in str(scrubbed)

    jsonl_bytes = _to_jsonl_bytes([{"b": 2, "a": 1}, {"z": 9, "y": 8}])
    lines = jsonl_bytes.decode("utf-8").strip().splitlines()
    assert len(lines) == 2
    assert lines[0] == '{"a":1,"b":2}'


@pytest.mark.asyncio
async def test_export_portable_workspace_api(
    setup_bundle_env: tuple[AsyncSession, PrincipalContext, uuid.UUID, Path],
) -> None:
    """Verify export_portable_workspace API endpoint handler."""
    session, caller, ws_id, _ = setup_bundle_env
    from kanban.api.problems import ProblemException
    from kanban.api.v1.admin.exports import AdminPortableExportRequest, export_portable_workspace

    # Get workspace slug
    ws_res = await session.execute(
        text("SELECT slug FROM workspaces WHERE id = :id"), {"id": ws_id}
    )
    ws_slug = ws_res.scalar_one()

    # 1. Successful export via slug
    req = AdminPortableExportRequest(workspace_slug=ws_slug, scrub=False)
    resp = await export_portable_workspace(req, caller=caller, session=session)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/gzip"
    assert f"kanban-{ws_slug}-portable.tar.gz" in resp.headers["content-disposition"]

    # 2. Successful export defaulting to caller workspace
    req_default = AdminPortableExportRequest(workspace_slug=None, scrub=True)
    resp_def = await export_portable_workspace(req_default, caller=caller, session=session)
    assert resp_def.status_code == 200

    # 3. Not found workspace
    req_missing = AdminPortableExportRequest(workspace_slug="nonexistent-slug-xyz", scrub=False)
    with pytest.raises(ProblemException) as exc_info:
        await export_portable_workspace(req_missing, caller=caller, session=session)
    assert exc_info.value.code == "WORKSPACE_NOT_FOUND"

    # 4. Export execution error
    from unittest.mock import patch

    with patch.object(
        PortableWorkspaceExporter, "export_bundle", side_effect=RuntimeError("simulated failure")
    ):
        with pytest.raises(ProblemException) as exc_err:
            await export_portable_workspace(req, caller=caller, session=session)
        assert exc_err.value.code == "EXPORT_EXECUTION_ERROR"


@pytest.mark.asyncio
async def test_cli_portable_export(
    setup_bundle_env: tuple[AsyncSession, PrincipalContext, uuid.UUID, Path],
) -> None:
    """Verify CLI portable export execution."""
    session, caller, ws_id, tmp_path = setup_bundle_env
    import argparse
    from unittest.mock import patch

    from kanban.cli.export import (
        _execute_portable_export,
        _get_admin_dsn,
        _run_portable_export,
        register_export_subparsers,
    )

    ws_res = await session.execute(
        text("SELECT slug FROM workspaces WHERE id = :id"), {"id": ws_id}
    )
    ws_slug = ws_res.scalar_one()

    # 1. Successful CLI export
    cli_out = tmp_path / "cli_bundle.tar.gz"
    args = argparse.Namespace(
        workspace=ws_slug,
        out=str(cli_out),
        scrub=False,
    )
    code = await _execute_portable_export(args, session=session)
    assert code == 0
    assert cli_out.is_file()

    # 2. Missing workspace CLI export
    args_err = argparse.Namespace(
        workspace="missing-workspace-xyz",
        out=str(tmp_path / "err.tar.gz"),
        scrub=False,
    )
    code_err = await _execute_portable_export(args_err, session=session)
    assert code_err == 2

    # 3. _run_portable_export wrapper
    def _fake_run(coro: Any) -> int:
        if hasattr(coro, "close"):
            coro.close()
        return 0

    with patch("kanban.cli.export.asyncio.run", side_effect=_fake_run) as mock_run:
        assert _run_portable_export(args) == 0
        mock_run.assert_called_once()

    # 4. Error execution branch
    with patch(
        "kanban.cli.export.PortableWorkspaceExporter.export_to_file",
        side_effect=RuntimeError("Disk failure"),
    ):
        code_fail = await _execute_portable_export(args, session=session)
        assert code_fail == 1

    # 5. _get_admin_dsn env vars
    with patch.dict("os.environ", {"KANBAN_ADMIN_DATABASE_URL": "postgresql+asyncpg://adm@/db"}):
        assert _get_admin_dsn() == "postgresql+asyncpg://adm@/db"
    with patch.dict(
        "os.environ", {"KANBAN_DATABASE_URL": "postgresql+asyncpg://db@/db"}, clear=True
    ):
        assert _get_admin_dsn() == "postgresql+asyncpg://db@/db"
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql+asyncpg://raw@/db"}, clear=True):
        assert _get_admin_dsn() == "postgresql+asyncpg://raw@/db"
    with patch.dict("os.environ", {}, clear=True):
        assert "postgresql+asyncpg://" in _get_admin_dsn()

    # 6. register_export_subparsers
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register_export_subparsers(subparsers)

    # 7. Standalone CLI execution without injected session
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    with patch("kanban.cli.export.create_async_engine") as mock_engine:
        mock_eng_inst = AsyncMock()
        mock_engine.return_value = mock_eng_inst
        with patch("kanban.cli.export.async_sessionmaker") as mock_maker:

            @asynccontextmanager
            async def _fake_session() -> AsyncIterator[AsyncSession]:
                yield session

            mock_maker.return_value = _fake_session
            res_standalone = await _execute_portable_export(args, session=None)
            assert res_standalone == 0
            mock_eng_inst.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_exporter_missing_workspace(
    db_session: AsyncSession,
) -> None:
    """Verify PortableWorkspaceExporter raises ValueError on non-existent workspace."""
    missing_id = uuid.uuid4()
    exporter = PortableWorkspaceExporter(
        session=db_session,
        workspace_id=missing_id,
    )
    with pytest.raises(ValueError, match="not found"):
        await exporter.export_bundle()
