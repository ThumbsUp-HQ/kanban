# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and integration tests for Plane import merge mode (KB-MIGRATION-PLANE-DB-01)."""

# ruff: noqa: E501, PLC0415, ANN401, TC002, S101, ICN001

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Attachment,
    ImportEntityMapping,
    Issue,
    IssueAssignee,
    IssueKeyAlias,
    Module,
    Project,
)
from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.deps import PrincipalContext
from kanban.importer.cutover_verifier import verify_cutover
from kanban.importer.plane_client import PlaneBundle, PlaneClient
from kanban.importer.plane_importer import ImportIntegrityError, PlaneImporter

FIXTURE_DIR = Path("tests/fixtures/plane_export_kanba").resolve()


@pytest.fixture
async def setup_merge_env(
    db_session: AsyncSession, tmp_path: Path
) -> tuple[AsyncSession, PrincipalContext, Path, Project]:
    """Provision workspace, admin caller, temporary blob store, and target project 'KAN'."""
    ws_id, admin_id = await bootstrap_workspace_admin(db_session, slug="kanban")

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
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir(parents=True, exist_ok=True)

    # Provision target project 'KAN'
    kan_id_res = await db_session.execute(
        text(
            "SELECT register_object("
            "  CAST('project' AS object_kind), :ws, NULL, "
            "  :ident, :name, :creator"
            ")"
        ),
        {
            "ws": ws_id,
            "ident": "KAN",
            "name": "Platform Core Target",
            "creator": admin_id,
        },
    )
    kan_id = kan_id_res.scalar_one()

    target_proj = Project(
        id=kan_id,
        workspace_id=ws_id,
        identifier="KAN",
        name="Platform Core Target",
        description_markdown="Target project for merge",
        issue_seq_counter=0,
    )
    db_session.add(target_proj)
    await db_session.flush()

    return db_session, caller, blob_dir, target_proj


@pytest.mark.asyncio
async def test_merge_mode_target_project_missing(
    setup_merge_env: tuple[AsyncSession, PrincipalContext, Path, Project],
) -> None:
    """Verify ImportIntegrityError is raised when --target-project does not exist."""
    session, caller, blob_dir, _ = setup_merge_env
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        target_project_identifier="NONEXISTENT",
    )

    with pytest.raises(ImportIntegrityError, match="Target project 'NONEXISTENT' not found"):
        await importer.run_import(bundle, dry_run=False)


@pytest.mark.asyncio
async def test_merge_mode_successful_import_and_remap(
    setup_merge_env: tuple[AsyncSession, PrincipalContext, Path, Project],
) -> None:
    """Verify merging KANBA into KAN allocates sequences, records provenance, and creates links."""
    session, caller, blob_dir, target_proj = setup_merge_env
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        target_project_identifier="KAN",
        exclude_project_identifiers="TEST",
    )

    # 1. Run live import in merge mode
    report1 = await importer.run_import(bundle, dry_run=False)
    assert report1.to_create > 0
    assert report1.sequence_high_water_mark > 0

    # 2. Verify all issues created belong to project KAN
    issues = (
        (
            await session.execute(
                select(Issue).where(
                    Issue.workspace_id == caller.workspace_id,
                    Issue.project_id == target_proj.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(issues) > 0
    for iss in issues:
        assert iss.project_id == target_proj.id
        # Verify provenance header
        assert "> Imported from `" in iss.description_markdown
    assert any("> Imported from `KANBA-" in iss.description_markdown for iss in issues)

    # 3. Check legacy aliases recorded
    aliases = (
        (
            await session.execute(
                select(IssueKeyAlias).where(
                    IssueKeyAlias.workspace_id == caller.workspace_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(aliases) > 0
    assert any(a.legacy_key.startswith("KANBA-") and a.source_system == "plane" for a in aliases)

    # 4. Check sequence counter updated
    await session.refresh(target_proj)
    assert target_proj.issue_seq_counter >= len(issues)

    # 5. Idempotency on rerun
    report2 = await importer.run_import(bundle, dry_run=False)
    assert report2.to_create == 0
    assert report2.unchanged > 0


@pytest.mark.asyncio
async def test_merge_mode_pdf_attachment_ingestion(
    setup_merge_env: tuple[AsyncSession, PrincipalContext, Path, Project],
) -> None:
    """Verify PDF attachments during Plane import are validated via sanitize_and_validate_pdf and record page_count."""
    session, caller, blob_dir, target_proj = setup_merge_env
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    # Minimal 1-page valid PDF
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n187\n%%EOF\n"
    )
    bundle.attachments["sample_document.pdf"] = pdf_bytes

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        target_project_identifier="KAN",
        exclude_project_identifiers="TEST",
    )

    report = await importer.run_import(bundle, dry_run=False)
    assert report.to_create > 0

    att = (
        (
            await session.execute(
                select(Attachment).where(
                    Attachment.workspace_id == caller.workspace_id,
                    Attachment.original_filename == "sample_document.pdf",
                )
            )
        )
        .scalars()
        .first()
    )
    assert att is not None
    assert att.content_type == "application/pdf"
    assert att.page_count == 1
    assert att.project_id == target_proj.id


@pytest.mark.asyncio
async def test_merge_mode_module_deduplication(
    setup_merge_env: tuple[AsyncSession, PrincipalContext, Path, Project],
) -> None:
    """Verify modules with identical names in target project are deduplicated without key collisions."""
    session, caller, blob_dir, target_proj = setup_merge_env
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    # Pre-create a module in target project with same name as bundle module ("Auth Engine")
    mod_id_res = await session.execute(
        text(
            "SELECT register_object("
            "  CAST('module' AS object_kind), :ws, :proj, :ckey, :title, :creator"
            ")"
        ),
        {
            "ws": caller.workspace_id,
            "proj": target_proj.id,
            "ckey": "mod-preexisting",
            "title": "Auth Engine",
            "creator": caller.principal_id,
        },
    )
    mod_id = mod_id_res.scalar_one()

    pre_mod = Module(
        id=mod_id,
        workspace_id=caller.workspace_id,
        project_id=target_proj.id,
        name="Auth Engine",
        status="planned",
    )
    session.add(pre_mod)
    await session.flush()

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        target_project_identifier="KAN",
    )

    # Importing should succeed and deduplicate without violating modules_project_id_name_key
    report = await importer.run_import(bundle, dry_run=False)
    assert report.to_create > 0

    mods = (
        (
            await session.execute(
                select(Module).where(
                    Module.project_id == target_proj.id,
                    Module.name == "Auth Engine",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(mods) == 1


@pytest.mark.asyncio
async def test_merge_mode_cutover_verifier(
    setup_merge_env: tuple[AsyncSession, PrincipalContext, Path, Project],
    tmp_path: Path,
) -> None:
    """Verify cutover_verifier in merge mode verifies parity with source project aliases."""
    session, caller, blob_dir, target_proj = setup_merge_env
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        target_project_identifier="KAN",
        exclude_project_identifiers="TEST",
    )
    await importer.run_import(bundle, dry_run=False)

    qa_root = tmp_path / "docs_qa"
    qa_root.mkdir(parents=True, exist_ok=True)
    # Populate QA bundle under source key KANBA-19
    (qa_root / "KANBA-19").mkdir(parents=True, exist_ok=True)
    (qa_root / "KANBA-19" / "git-diff.patch").write_text("diff --git a/a b/b\n", encoding="utf-8")
    (qa_root / "KANBA-19" / "unit-test-results.txt").write_text("passed\n", encoding="utf-8")
    (qa_root / "KANBA-19" / "build-check.txt").write_text("ok\n", encoding="utf-8")

    report = await verify_cutover(
        session=session,
        bundle_dir=FIXTURE_DIR,
        workspace_slug="kanban",
        project_identifier="KAN",
        source_project_identifier="KANBA",
        qa_root=qa_root,
        pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
    )

    # Key parity check should pass
    key_parity_chk = next(
        (c for c in report.checks if c.name == "entity_count_and_key_parity"), None
    )
    assert key_parity_chk is not None
    assert key_parity_chk.passed is True

    # Test merge-mode key parity mismatch when sequence counter < max_db_seq
    from unittest.mock import MagicMock, patch

    orig_execute = session.execute

    async def mock_execute_low_seq(statement: Any, *args: Any, **kwargs: Any) -> Any:
        if "issue_seq_counter" in str(statement):
            mock_res = MagicMock()
            mock_mapping = MagicMock()
            mock_mapping.one_or_none.return_value = {
                "id": target_proj.id,
                "issue_seq_counter": 0,
                "modules_enabled": True,
            }
            mock_res.mappings.return_value = mock_mapping
            return mock_res
        return await orig_execute(statement, *args, **kwargs)

    with patch.object(session, "execute", side_effect=mock_execute_low_seq):
        report_bad_seq = await verify_cutover(
            session=session,
            bundle_dir=FIXTURE_DIR,
            workspace_slug="kanban",
            project_identifier="KAN",
            source_project_identifier="KANBA",
            qa_root=qa_root,
            pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
        )
        chk_bad_seq = next(
            c for c in report_bad_seq.checks if c.name == "entity_count_and_key_parity"
        )
        assert chk_bad_seq.passed is False
        assert "less than max database sequence ID" in (chk_bad_seq.detail or "")

    # Test merge-mode key parity mismatch when mapping is missing
    one_mapping = (
        (
            await session.execute(
                select(ImportEntityMapping).where(ImportEntityMapping.source_kind == "issue")
            )
        )
        .scalars()
        .first()
    )
    assert one_mapping is not None
    await session.delete(one_mapping)
    await session.flush()

    report_missing = await verify_cutover(
        session=session,
        bundle_dir=FIXTURE_DIR,
        workspace_slug="kanban",
        project_identifier="KAN",
        source_project_identifier="KANBA",
        qa_root=qa_root,
        pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
    )
    chk_missing = next(c for c in report_missing.checks if c.name == "entity_count_and_key_parity")
    assert chk_missing.passed is False
    assert chk_missing.error_code == "KEY_PARITY_MISMATCH"


@pytest.mark.asyncio
async def test_merge_mode_markdown_attachment(
    setup_merge_env: tuple[AsyncSession, PrincipalContext, Path, Project],
) -> None:
    """Verify .md attachments are converted to Markdown blocks without media sniffer error."""
    session, caller, blob_dir, target_proj = setup_merge_env
    from kanban.importer.plane_client import PlaneIssue, PlaneProject

    bundle = PlaneBundle(
        projects=[PlaneProject(id="p-1", identifier="KANBA", name="Kanba Project")],
        issues=[
            PlaneIssue(
                id="i-md-1",
                sequence_id=10,
                name="MD Attachment Issue",
                description_html="<p>See attached <a href='/api/assets/spec.md'>spec.md</a></p>",
                project="p-1",
            )
        ],
        attachments={"spec.md": b"# Feature Spec\n\nSome important notes."},
    )

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        target_project_identifier="KAN",
    )
    report = await importer.run_import(bundle, dry_run=False)
    assert report.to_create > 0

    iss = (
        await session.execute(
            select(Issue).where(
                Issue.project_id == target_proj.id,
                Issue.sequence_id == 1,
            )
        )
    ).scalar_one()
    assert "spec.md" in iss.description_markdown


def test_parse_iso_datetime_helper() -> None:
    """Verify _parse_iso_datetime handles None, invalid, naive, and aware timestamps."""
    from kanban.importer.plane_importer import _parse_iso_datetime

    assert _parse_iso_datetime(None) is None
    assert _parse_iso_datetime("invalid-iso-string") is None
    dt_naive = _parse_iso_datetime("2026-05-01T12:00:00")
    assert dt_naive is not None
    assert dt_naive.tzinfo == datetime.UTC
    dt_aware = _parse_iso_datetime("2026-05-01T12:00:00+00:00")
    assert dt_aware is not None


@pytest.mark.asyncio
async def test_merge_mode_user_mapping_and_updates(
    setup_merge_env: tuple[AsyncSession, PrincipalContext, Path, Project],
) -> None:
    """Verify user mapping, exclude_project_identifiers list, and entity updates when SHA changes."""
    session, caller, blob_dir, target_proj = setup_merge_env
    from kanban.importer.plane_client import PlaneComment, PlaneIssue, PlaneProject, PlaneState

    user_map = {"u-plane-1": "@Admin User"}

    bundle = PlaneBundle(
        projects=[
            PlaneProject(id="p-k", identifier="KANBA", name="Kanba Project"),
            PlaneProject(id="p-ex", identifier="EXCLUDED", name="Excluded Project"),
        ],
        states=[
            PlaneState(id="s-backlog", project="p-k", name="Backlog", group="backlog", sequence=10),
            PlaneState(
                id="s-custom", project="p-k", name="Custom Review", group="unstarted", sequence=20
            ),
        ],
        issues=[
            PlaneIssue(
                id="i-user-1",
                sequence_id=1,
                name="First Issue",
                description_html="<p>Testing user map</p>",
                project="p-k",
                created_by="u-plane-1",
                assignees=["u-plane-1"],
                archived_at="2026-05-01T12:00:00Z",
                state="s-backlog",
            )
        ],
        comments=[
            PlaneComment(
                id="c-1",
                issue_id="i-user-1",
                comment_html="<p>First comment</p>",
                actor="u-plane-1",
            )
        ],
    )

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        user_map=user_map,
        target_project_identifier="KAN",
        exclude_project_identifiers=["EXCLUDED"],
    )

    report1 = await importer.run_import(bundle, dry_run=False)
    assert report1.to_create > 0

    # Verify issue creator and assignee were resolved to caller.principal_id (admin)
    iss = (
        await session.execute(
            select(Issue).where(
                Issue.project_id == target_proj.id,
                Issue.sequence_id == 1,
            )
        )
    ).scalar_one()
    assignee_row = (
        await session.execute(
            select(IssueAssignee).where(
                IssueAssignee.issue_id == iss.id,
            )
        )
    ).scalar_one_or_none()
    assert assignee_row is not None
    assert assignee_row.principal_id == caller.principal_id

    # Now simulate an updated bundle where issue and comment content SHA changes
    updated_bundle = PlaneBundle(
        projects=[PlaneProject(id="p-k", identifier="KANBA", name="Kanba Project")],
        states=[
            PlaneState(id="s-backlog", project="p-k", name="Backlog", group="backlog", sequence=10),
            PlaneState(
                id="s-custom",
                project="p-k",
                name="Custom Review Renamed",
                group="unstarted",
                sequence=20,
            ),
        ],
        issues=[
            PlaneIssue(
                id="i-user-1",
                sequence_id=1,
                name="First Issue Modified Title",
                description_html="<p>Testing user map modified</p>",
                project="p-k",
                created_by="u-plane-1",
                assignees=["u-plane-1"],
                archived_at="2026-05-01T12:00:00Z",
                state="s-backlog",
            )
        ],
        comments=[
            PlaneComment(
                id="c-1",
                issue_id="i-user-1",
                comment_html="<p>First comment modified</p>",
                actor="u-plane-1",
            )
        ],
    )

    importer2 = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        user_map=user_map,
        target_project_identifier="KAN",
    )
    report2 = await importer2.run_import(updated_bundle, dry_run=False)
    assert report2.to_update >= 1
