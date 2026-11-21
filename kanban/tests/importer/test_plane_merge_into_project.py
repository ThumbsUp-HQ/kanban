# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and integration tests for merging Plane into existing project (KAN-82)."""

# ruff: noqa: E501, PLC0415, TC002, ICN001, PLR0915

from __future__ import annotations

import datetime
import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Attachment,
    ImportEntityMapping,
    Issue,
    IssueComment,
    IssueKeyAlias,
    IssueLabel,
    IssueModule,
    Module,
    ObjectLink,
    ObjectRecord,
    Project,
    ProjectLabel,
)
from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.deps import PrincipalContext
from kanban.content.normalize import ContentNormalizeError
from kanban.importer.plane_client import (
    PlaneBundle,
    PlaneComment,
    PlaneIssue,
    PlaneLabel,
    PlaneModule,
    PlaneProject,
    PlaneState,
)
from kanban.importer.plane_importer import PlaneImporter

FIXTURE_DIR = Path("tests/fixtures/plane_export_kanba").resolve()


@pytest.fixture
async def setup_merge_into_project_env(
    db_session: AsyncSession, tmp_path: Path
) -> tuple[AsyncSession, PrincipalContext, Path, Project]:
    """Provision workspace, admin caller, blob store root, and pre-populated project 'KAN' (KAN-1..10)."""
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

    # 1. Provision target project 'KAN'
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
        issue_seq_counter=10,
    )
    db_session.add(target_proj)
    await db_session.flush()

    # Pre-populate workflow state & priority for KAN
    st_res = await db_session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :pid LIMIT 1"),
        {"pid": kan_id},
    )
    default_state_id = st_res.scalar_one_or_none()
    if not default_state_id:
        from database.models import WorkflowState

        new_st = WorkflowState(
            workspace_id=ws_id,
            project_id=kan_id,
            name="Todo",
            state_group="unstarted",
            color_hex="#3B82F6",
            is_default=True,
            sort_order=10,
        )
        db_session.add(new_st)
        await db_session.flush()
        default_state_id = new_st.id

    prio_res = await db_session.execute(
        text("SELECT id FROM project_priorities WHERE project_id = :pid LIMIT 1"),
        {"pid": kan_id},
    )
    default_prio_id = prio_res.scalar_one_or_none()
    if not default_prio_id:
        from database.models import ProjectPriority

        new_prio = ProjectPriority(
            workspace_id=ws_id,
            project_id=kan_id,
            slug="none",
            name="None",
            color_hex="#A3A3A3",
            sort_order=10,
            is_default=True,
        )
        db_session.add(new_prio)
        await db_session.flush()
        default_prio_id = new_prio.id

    # 2. Pre-populate issues KAN-1..KAN-10
    core_lbl = ProjectLabel(
        workspace_id=ws_id,
        project_id=kan_id,
        name="Core",
        color_hex="#EF4444",
    )
    db_session.add(core_lbl)

    core_mod_id = (
        await db_session.execute(
            text(
                "SELECT register_object("
                "  CAST('module' AS object_kind), :ws, :proj, :ckey, :title, :creator"
                ")"
            ),
            {
                "ws": ws_id,
                "proj": kan_id,
                "ckey": "mod-core-01",
                "title": "Core Module",
                "creator": admin_id,
            },
        )
    ).scalar_one()

    core_mod = Module(
        id=core_mod_id,
        workspace_id=ws_id,
        project_id=kan_id,
        name="Core Module",
        status="in_progress",
    )
    db_session.add(core_mod)

    for seq in range(1, 11):
        iss_id = (
            await db_session.execute(
                text(
                    "SELECT register_object("
                    "  CAST('issue' AS object_kind), :ws, :proj, :key, :title, :creator"
                    ")"
                ),
                {
                    "ws": ws_id,
                    "proj": kan_id,
                    "key": f"KAN-{seq}",
                    "title": f"Existing Pre-populated Issue {seq}",
                    "creator": admin_id,
                },
            )
        ).scalar_one()

        pre_iss = Issue(
            id=iss_id,
            workspace_id=ws_id,
            project_id=kan_id,
            sequence_id=seq,
            summary=f"Existing Pre-populated Issue {seq}",
            description_markdown=f"Issue {seq} body",
            state_id=default_state_id,
            priority_id=default_prio_id,
            board_rank=f"0|{seq:05d}:",
            created_by_id=admin_id,
            original_created_by_id=admin_id,
            ancestry_path=iss_id.hex,
        )
        db_session.add(pre_iss)

    await db_session.flush()

    return db_session, caller, blob_dir, target_proj


@pytest.mark.asyncio
async def test_plane_merge_into_project_full_lifecycle(
    setup_merge_into_project_env: tuple[AsyncSession, PrincipalContext, Path, Project],
) -> None:
    """Verify merge of KANBA-1..5 into pre-populated KAN-1..10 with parent-child topological sort and security gates."""
    session, caller, blob_dir, target_proj = setup_merge_into_project_env

    bundle = PlaneBundle(
        projects=[
            PlaneProject(id="p-kanba", identifier="KANBA", name="Kanba Source Project"),
            PlaneProject(id="p-test", identifier="TEST", name="Test Excluded Project"),
        ],
        states=[
            PlaneState(id="s-todo", name="Todo", group="unstarted", project="p-kanba"),
        ],
        labels=[
            PlaneLabel(id="l-core", name="Core", color="#FF0000", project="p-kanba"),
        ],
        modules=[
            PlaneModule(id="m-core", name="Core Module", project="p-kanba"),
        ],
        issues=[
            PlaneIssue(
                id="i-kanba-1",
                sequence_id=1,
                name="<script>alert(1)</script> Issue One",
                description_html=(
                    "<p>Referencing KANBA-1 in prose and "
                    "docs/qa/KANBA-1/unit-test-results.txt path directly</p>"
                ),
                project="p-kanba",
                labels=["l-core"],
                module_id="m-core",
                created_at="2026-01-01T10:00:00Z",
                updated_at="2026-01-01T10:05:00Z",
            ),
            PlaneIssue(
                id="i-kanba-2",
                sequence_id=2,
                name="Child Issue Two",
                description_html="<p>Child of KANBA-5</p>",
                parent_id="i-kanba-5",
                project="p-kanba",
                created_at="2026-01-01T11:00:00Z",
                updated_at="2026-01-01T11:05:00Z",
            ),
            PlaneIssue(
                id="i-kanba-3",
                sequence_id=3,
                name="Issue Three with Comment",
                description_html="<p>Issue with historical comment</p>",
                project="p-kanba",
                created_at="2026-01-01T12:00:00Z",
                updated_at="2026-01-01T12:05:00Z",
            ),
            PlaneIssue(
                id="i-kanba-4",
                sequence_id=4,
                name="Issue Four with Attachment",
                description_html="<p>See attached <a href='/api/assets/spec.md'>spec.md</a></p>",
                project="p-kanba",
                created_at="2026-01-01T13:00:00Z",
                updated_at="2026-01-01T13:05:00Z",
            ),
            PlaneIssue(
                id="i-kanba-5",
                sequence_id=5,
                name="Parent Issue Five",
                description_html="<p>Parent issue of KANBA-2</p>",
                project="p-kanba",
                created_at="2026-01-01T14:00:00Z",
                updated_at="2026-01-01T14:05:00Z",
            ),
            PlaneIssue(
                id="i-test-1",
                sequence_id=1,
                name="Excluded Test Issue",
                description_html="<p>Should never leak into KAN</p>",
                project="p-test",
                created_at="2026-01-01T09:00:00Z",
            ),
        ],
        comments=[
            PlaneComment(
                id="c-kanba-3",
                issue_id="i-kanba-3",
                comment_html="<p>Historical comment created on KANBA-3</p>",
                created_at="2026-01-01T12:30:00Z",
            ),
            PlaneComment(
                id="c-test-1",
                issue_id="i-test-1",
                comment_html="<p>Comment on excluded test issue</p>",
                created_at="2026-01-01T09:30:00Z",
            ),
        ],
        attachments={
            "data.png": (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
                b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
            ),
            "spec.md": b"# Specification\n\nFeature specification document in Markdown.",
        },
    )

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        target_project_identifier="KAN",
        exclude_project_identifiers={"TEST"},
    )

    # 1. Execute merge import
    report = await importer.run_import(bundle, dry_run=False)

    # 2. Sequence Allocation Check: KAN-1..10 pre-populated -> KANBA-1..5 allocated KAN-11..15
    await session.refresh(target_proj)
    assert report.sequence_high_water_mark == 15
    assert target_proj.issue_seq_counter == 15

    # 3. Key remap manifest verification
    expected_manifest = {
        "KANBA-1": "KAN-11",
        "KANBA-2": "KAN-12",
        "KANBA-3": "KAN-13",
        "KANBA-4": "KAN-14",
        "KANBA-5": "KAN-15",
    }
    assert report.key_remap_manifest == expected_manifest

    # 4. Legacy issue_key_aliases check
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
    alias_dict = {a.legacy_key: a for a in aliases}
    for old_k in expected_manifest:
        assert old_k in alias_dict
        assert alias_dict[old_k].source_system == "plane"

    # 5. Topological sort check: Parent KANBA-5 (KAN-15) must be parent of Child KANBA-2 (KAN-12)
    kan_12 = (
        await session.execute(
            select(Issue).where(
                Issue.project_id == target_proj.id,
                Issue.sequence_id == 12,
            )
        )
    ).scalar_one()
    kan_15 = (
        await session.execute(
            select(Issue).where(
                Issue.project_id == target_proj.id,
                Issue.sequence_id == 15,
            )
        )
    ).scalar_one()
    assert kan_12.parent_issue_id == kan_15.id
    assert kan_15.id.hex in kan_12.ancestry_path

    # Verify PARENT_OF ObjectLink edge
    parent_link = (
        await session.execute(
            select(ObjectLink).where(
                ObjectLink.workspace_id == caller.workspace_id,
                ObjectLink.source_id == kan_15.id,
                ObjectLink.target_id == kan_12.id,
            )
        )
    ).scalar_one_or_none()
    assert parent_link is not None

    # 6. HTML / <script> stripping and prose reference rewriting
    kan_11 = (
        await session.execute(
            select(Issue).where(
                Issue.project_id == target_proj.id,
                Issue.sequence_id == 11,
            )
        )
    ).scalar_one()
    # Summary must have <script> stripped
    assert "<script>" not in kan_11.summary
    assert "</script>" not in kan_11.summary
    assert kan_11.summary == "Issue One"

    # Description must have docs/qa/KANBA-1/ path untouched, but prose KANBA-1 rewritten to KAN-11
    assert "docs/qa/KANBA-1/unit-test-results.txt" in kan_11.description_markdown
    assert "Referencing KAN-11 in prose" in kan_11.description_markdown
    assert "> Imported from `KANBA-1`" in kan_11.description_markdown

    # 7. Check historical timestamps on objects table
    obj_11 = (
        await session.execute(
            select(ObjectRecord).where(
                ObjectRecord.id == kan_11.id,
            )
        )
    ).scalar_one()
    assert obj_11.created_at == datetime.datetime(2026, 1, 1, 10, 0, tzinfo=datetime.UTC)
    assert obj_11.updated_at == datetime.datetime(2026, 1, 1, 10, 5, tzinfo=datetime.UTC)

    # 8. Check comment created_at preservation
    kan_13 = (
        await session.execute(
            select(Issue).where(
                Issue.project_id == target_proj.id,
                Issue.sequence_id == 13,
            )
        )
    ).scalar_one()
    comm_13 = (
        await session.execute(
            select(IssueComment).where(
                IssueComment.issue_id == kan_13.id,
            )
        )
    ).scalar_one()
    assert comm_13.created_at == datetime.datetime(2026, 1, 1, 12, 30, tzinfo=datetime.UTC)

    # 9. Verify excluded project 'TEST' leakage prevention
    test_issues = (
        (
            await session.execute(
                select(Issue).where(
                    Issue.project_id == target_proj.id,
                    Issue.summary == "Excluded Test Issue",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(test_issues) == 0

    test_comments = (
        (
            await session.execute(
                select(IssueComment).where(
                    IssueComment.body_markdown.contains("excluded test issue"),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(test_comments) == 0

    # 10. Attachment source_raw_sha preservation
    spec_md_mapping = (
        await session.execute(
            select(ImportEntityMapping).where(
                ImportEntityMapping.workspace_id == caller.workspace_id,
                ImportEntityMapping.source_kind == "attachment",
                ImportEntityMapping.source_id == "spec.md",
            )
        )
    ).scalar_one()
    expected_spec_sha = hashlib.sha256(bundle.attachments["spec.md"]).digest()
    assert spec_md_mapping.source_sha256 == expected_spec_sha

    data_png_mapping = (
        await session.execute(
            select(ImportEntityMapping).where(
                ImportEntityMapping.workspace_id == caller.workspace_id,
                ImportEntityMapping.source_kind == "attachment",
                ImportEntityMapping.source_id == "data.png",
            )
        )
    ).scalar_one()
    expected_data_sha = hashlib.sha256(bundle.attachments["data.png"]).digest()
    assert data_png_mapping.source_sha256 == expected_data_sha

    # 11. Deduplication of states, labels, and modules
    lbls = (
        (
            await session.execute(
                select(ProjectLabel).where(ProjectLabel.project_id == target_proj.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(lbls) == 1
    assert lbls[0].name == "Core"

    mods = (
        (await session.execute(select(Module).where(Module.project_id == target_proj.id)))
        .scalars()
        .all()
    )
    assert len(mods) == 1
    assert mods[0].name == "Core Module"

    kan_11_lbl = (
        await session.execute(select(IssueLabel).where(IssueLabel.issue_id == kan_11.id))
    ).scalar_one()
    assert kan_11_lbl.label_id == lbls[0].id

    kan_11_mod = (
        await session.execute(select(IssueModule).where(IssueModule.issue_id == kan_11.id))
    ).scalar_one()
    assert kan_11_mod.module_id == mods[0].id

    # 12. Markdown details block and binary attachment separation
    kan_14 = (
        await session.execute(
            select(Issue).where(
                Issue.project_id == target_proj.id,
                Issue.sequence_id == 14,
            )
        )
    ).scalar_one()
    assert "<details>" in kan_14.description_markdown
    assert "<summary>Attachment: spec.md</summary>" in kan_14.description_markdown
    assert "Feature specification document in Markdown." in kan_14.description_markdown

    spec_att = (
        await session.execute(
            select(Attachment).where(
                Attachment.project_id == target_proj.id,
                Attachment.original_filename == "spec.md",
            )
        )
    ).scalar_one_or_none()
    assert spec_att is None

    # 13. Verify activity ledger chain and cutover verification
    chain_res = (
        await session.execute(
            text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws)"),
            {"ws": caller.workspace_id},
        )
    ).one()
    assert chain_res.is_valid is True

    # 14. Idempotent re-run allocates 0 extra sequences
    report2 = await importer.run_import(bundle, dry_run=False)
    assert report2.to_create == 0
    assert report2.unchanged > 0
    await session.refresh(target_proj)
    assert target_proj.issue_seq_counter == 15


@pytest.mark.asyncio
async def test_plane_merge_rejects_utf16_surrogate_in_issue_name(
    setup_merge_into_project_env: tuple[AsyncSession, PrincipalContext, Path, Project],
) -> None:
    """Verify UTF-16 lone surrogate in issue.name is rejected fail-closed."""
    session, caller, blob_dir, _ = setup_merge_into_project_env

    bundle = PlaneBundle(
        projects=[PlaneProject(id="p-k", identifier="KANBA", name="Kanba")],
        issues=[
            PlaneIssue(
                id="i-bad-surrogate",
                sequence_id=1,
                name="Issue with \ud800 surrogate",
                project="p-k",
            )
        ],
    )

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        target_project_identifier="KAN",
    )

    with pytest.raises(ContentNormalizeError, match="INVALID_UTF8_SURROGATE"):
        await importer.run_import(bundle, dry_run=False)


@pytest.mark.asyncio
async def test_plane_merge_md_attachment_script_stripping_and_surrogate_rejection(
    setup_merge_into_project_env: tuple[AsyncSession, PrincipalContext, Path, Project],
) -> None:
    """Verify .md attachments strip <script> tags and reject UTF-16 lone surrogates fail-closed."""
    session, caller, blob_dir, target_proj = setup_merge_into_project_env

    bundle_script = PlaneBundle(
        projects=[PlaneProject(id="p-k", identifier="KANBA", name="Kanba")],
        issues=[
            PlaneIssue(
                id="i-script-att",
                sequence_id=1,
                name="Issue with script md attachment",
                description_html="<p>Check <a href='/api/assets/evil.md'>evil.md</a></p>",
                project="p-k",
            )
        ],
        attachments={
            "evil.md": b"# Title\n\n<script>alert('xss')</script>\nSafe text.",
        },
    )

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        target_project_identifier="KAN",
    )
    report = await importer.run_import(bundle_script, dry_run=False)
    assert report.to_create > 0

    iss = (
        await session.execute(
            select(Issue).where(
                Issue.project_id == target_proj.id,
                Issue.summary == "Issue with script md attachment",
            )
        )
    ).scalar_one()
    assert "<script>" not in iss.description_markdown
    assert "</script>" not in iss.description_markdown
    assert "<details>" in iss.description_markdown
    assert "<summary>Attachment: evil.md</summary>" in iss.description_markdown
    assert "Safe text." in iss.description_markdown

    # UTF-16 lone surrogate in .md attachment must raise ContentNormalizeError("INVALID_UTF8_SURROGATE")
    bundle_surrogate = PlaneBundle(
        projects=[PlaneProject(id="p-k2", identifier="KANBA2", name="Kanba 2")],
        issues=[
            PlaneIssue(
                id="i-surr-att",
                sequence_id=1,
                name="Issue with surrogate md attachment",
                description_html="<p>Check <a href='/api/assets/bad.md'>bad.md</a></p>",
                project="p-k2",
            )
        ],
        attachments={
            "bad.md": "Corrupt \ud800 surrogate".encode("utf-8", errors="surrogatepass"),
        },
    )
    importer2 = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
        target_project_identifier="KAN",
    )
    with pytest.raises(ContentNormalizeError, match="INVALID_UTF8_SURROGATE"):
        await importer2.run_import(bundle_surrogate, dry_run=False)
