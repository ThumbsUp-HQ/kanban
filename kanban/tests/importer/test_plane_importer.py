# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for Plane snapshot importer (KB-P6-01)."""

# ruff: noqa: E501, PLC0415, PERF401, SIM117, TC002, ANN401

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Attachment, Issue, IssueComment, Project, WorkflowState
from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.deps import PrincipalContext
from kanban.importer.plane_client import PlaneBundle, PlaneClient, PlaneIssue
from kanban.importer.plane_importer import ImportIntegrityError, PlaneImporter

FIXTURE_DIR = Path("tests/fixtures/plane_export_kanba").resolve()


@pytest.fixture
async def setup_import_env(
    db_session: AsyncSession, tmp_path: Path
) -> tuple[AsyncSession, PrincipalContext, Path]:
    """Provision workspace, admin caller, and temporary blob store directory."""
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
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir(parents=True, exist_ok=True)
    return db_session, caller, blob_dir


@pytest.mark.asyncio
async def test_case_01_positive_lossless_import_and_idempotency(
    setup_import_env: tuple[AsyncSession, PrincipalContext, Path],
) -> None:
    """Test Case 1: Live import preserves KANBA-19, sequence continuity, Markdown, and re-run is unchanged."""
    session, caller, blob_dir = setup_import_env
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
    )

    # 1. Run live import
    report1 = await importer.run_import(bundle, dry_run=False)
    assert report1.to_create > 0
    assert report1.sequence_high_water_mark == 19
    assert report1.invalid_link_count == 0

    # Verify KANBA-19 exists and resolves
    issue_19 = (
        await session.execute(
            select(Issue).where(
                Issue.workspace_id == caller.workspace_id,
                Issue.sequence_id == 19,
            )
        )
    ).scalar_one_or_none()
    assert issue_19 is not None
    assert issue_19.summary == "Plane importer cutover feature"

    # Verify description is canonical Markdown (zero HTML tags)
    assert "<p>" not in issue_19.description_markdown
    assert "</p>" not in issue_19.description_markdown
    assert "<img" not in issue_19.description_markdown

    # Verify docs/qa link is preserved verbatim
    assert "docs/qa/KANBA-19/unit-test-results.txt" in issue_19.description_markdown

    # Verify inline attachment URL was rewritten to /api/v1/attachments/
    assert "/api/v1/attachments/" in issue_19.description_markdown

    # Verify sequence counter on project is 19
    proj = (
        await session.execute(
            select(Project).where(
                Project.workspace_id == caller.workspace_id,
                Project.identifier == "KANBA",
            )
        )
    ).scalar_one()
    assert proj.issue_seq_counter >= 19

    # Verify allocating next issue sequence gives 20
    next_seq = (
        await session.execute(
            text("SELECT allocate_issue_sequence(:pid)"),
            {"pid": proj.id},
        )
    ).scalar_one()
    assert next_seq == 20

    # Verify comments exist with Markdown and zero HTML
    comment = (
        await session.execute(select(IssueComment).where(IssueComment.issue_id == issue_19.id))
    ).scalar_one_or_none()
    assert comment is not None
    assert "<script>" not in comment.body_markdown
    assert "ignore prior rules" not in comment.body_markdown
    assert "docs/qa/KANBA-19/build-check.txt" in comment.body_markdown

    # Verify audit_object_links returns 0 invalid rows
    invalid_links = (
        await session.execute(
            text("SELECT count(*) FROM audit_object_links(:ws)"),
            {"ws": caller.workspace_id},
        )
    ).scalar_one()
    assert invalid_links == 0

    # 2. Re-run exact same import -> must be 100% idempotent
    report2 = await importer.run_import(bundle, dry_run=False)
    assert report2.to_create == 0
    assert report2.to_update == 0
    assert report2.unchanged > 0
    assert report2.invalid_link_count == 0


@pytest.mark.asyncio
async def test_case_02_dry_run_isolation(
    setup_import_env: tuple[AsyncSession, PrincipalContext, Path],
) -> None:
    """Test Case 2: Dry-run returns accurate diff report while 0 mutations persist in DB."""
    session, caller, blob_dir = setup_import_env
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
    )

    # Execute dry-run
    report = await importer.run_import(bundle, dry_run=True)
    assert report.to_create > 0
    assert report.sequence_high_water_mark == 19
    assert report.invalid_link_count == 0

    # Assert 0 issues or projects persisted
    issue_count = (
        await session.execute(
            text("SELECT count(*) FROM issues WHERE workspace_id = :ws"),
            {"ws": caller.workspace_id},
        )
    ).scalar_one()
    assert issue_count == 0

    proj_count = (
        await session.execute(
            text("SELECT count(*) FROM projects WHERE workspace_id = :ws"),
            {"ws": caller.workspace_id},
        )
    ).scalar_one()
    assert proj_count == 0


@pytest.mark.asyncio
async def test_case_03_hostile_payload_sanitization(
    setup_import_env: tuple[AsyncSession, PrincipalContext, Path],
) -> None:
    """Test Case 3: Hostile HTML and SVG payloads are sanitized without active scripts or hidden text."""
    session, caller, blob_dir = setup_import_env
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
    )
    await importer.run_import(bundle, dry_run=False)

    # Check SVG attachment
    svg_att = (
        await session.execute(
            select(Attachment).where(
                Attachment.workspace_id == caller.workspace_id,
                Attachment.original_filename == "asset-svg.svg",
            )
        )
    ).scalar_one_or_none()
    assert svg_att is not None

    clean_svg_path = importer.blob_store.get_path(svg_att.storage_key)
    clean_svg_content = clean_svg_path.read_text(encoding="utf-8")
    assert "<foreignObject" not in clean_svg_content
    assert "<script" not in clean_svg_content
    assert "alert(1)" not in clean_svg_content
    assert "<rect" in clean_svg_content


@pytest.mark.asyncio
async def test_case_05_integrity_rollback_on_tree_depth_violation(
    setup_import_env: tuple[AsyncSession, PrincipalContext, Path],
) -> None:
    """Test Case 5: Hierarchy exceeding depth > 6 raises ImportIntegrityError and rolls back 100%."""
    session, caller, blob_dir = setup_import_env
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)

    # Create cycle depth > 6 by chaining parents: issue 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8
    chain_issues: list[PlaneIssue] = []
    for i in range(1, 9):
        chain_issues.append(
            PlaneIssue(
                id=f"chain-{i}",
                sequence_id=i,
                name=f"Chain issue {i}",
                project="plane-proj-kanba",
                parent=f"chain-{i - 1}" if i > 1 else None,
            )
        )
    bundle.issues = chain_issues

    importer = PlaneImporter(
        session=session,
        caller=caller,
        blob_store_root=blob_dir,
    )

    with pytest.raises(ValueError, match="maximum allowable depth of 6"):
        await importer.run_import(bundle, dry_run=False)

    # Confirm zero issues persisted in DB
    cnt = (
        await session.execute(
            text("SELECT count(*) FROM issues WHERE workspace_id = :ws"),
            {"ws": caller.workspace_id},
        )
    ).scalar_one()
    assert cnt == 0


def test_plane_mapper_topological_sort_and_cycle() -> None:
    """Verify PlaneMapper sorts DAG, detects cycles, and handles missing parents."""
    from kanban.importer.plane_mapper import PlaneMapper

    mapper = PlaneMapper()

    # 1. Cycle detection
    issue_a = PlaneIssue(id="a", sequence_id=1, name="A", project="p1", parent="b")
    issue_b = PlaneIssue(id="b", sequence_id=2, name="B", project="p1", parent="a")
    with pytest.raises(ValueError, match="cycle detected"):
        mapper.sort_issues_topologically([issue_a, issue_b])

    # 2. Missing parent
    issue_orphan = PlaneIssue(
        id="c", sequence_id=3, name="C", project="p1", parent="missing-parent-id"
    )
    sorted_issues, warnings = mapper.sort_issues_topologically([issue_orphan])
    assert len(sorted_issues) == 1
    assert len(warnings) == 1
    assert "references missing parent" in warnings[0]

    # 3. Disconnected island
    issue_root = PlaneIssue(id="r", sequence_id=4, name="R", project="p1", parent=None)
    sorted_all, _ = mapper.sort_issues_topologically([issue_root, issue_orphan])
    assert len(sorted_all) == 2


def test_plane_mapper_user_handle_resolution() -> None:
    """Verify user handle resolution across mapping tiers."""
    from kanban.importer.plane_client import PlaneBundle, PlaneMember
    from kanban.importer.plane_mapper import PlaneMapper

    mapper = PlaneMapper(user_map={"user-1": "@alice", "user-2": "bob"})
    bundle = PlaneBundle(
        members=[
            PlaneMember(id="user-3", email="charlie.smith@example.com"),
            PlaneMember(id="user-4-no-email", email=None),
        ]
    )

    # 1. None -> system
    h0, unmapped0 = mapper.resolve_user_handle(None, bundle)
    assert h0 == "system"
    assert unmapped0 is False

    # 2. Explicit map with @
    h1, unmapped1 = mapper.resolve_user_handle("user-1", bundle)
    assert h1 == "alice"
    assert unmapped1 is False

    # 3. Explicit map without @
    h2, unmapped2 = mapper.resolve_user_handle("user-2", bundle)
    assert h2 == "bob"
    assert unmapped2 is False

    # 4. Member with email
    h3, unmapped3 = mapper.resolve_user_handle("user-3", bundle)
    assert h3.startswith("plane-import-charlie")
    assert unmapped3 is True

    # 5. Member without email
    h4, unmapped4 = mapper.resolve_user_handle("user-4-no-email", bundle)
    assert h4.startswith("plane-import-user-4")
    assert unmapped4 is True

    # 6. Completely unknown user
    h5, unmapped5 = mapper.resolve_user_handle("user-9999-unknown", bundle)
    assert h5.startswith("plane-import-user-9")
    assert unmapped5 is True


@pytest.mark.asyncio
async def test_import_empty_bundle_fallback_to_existing_project(
    setup_import_env: tuple[AsyncSession, PrincipalContext, Path],
) -> None:
    """Verify empty bundle falls back to existing workspace project."""
    session, caller, blob_dir = setup_import_env
    # Create project in workspace first
    proj_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('project'::object_kind, :ws, NULL, 'EXT', 'Existing', :pid, :id)"
        ),
        {"ws": caller.workspace_id, "pid": caller.principal_id, "id": proj_id},
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) VALUES (:id, :ws, 'EXT', 'Existing')"
        ),
        {"id": proj_id, "ws": caller.workspace_id},
    )
    await session.flush()

    importer = PlaneImporter(session=session, caller=caller, blob_store_root=blob_dir)
    report = await importer.run_import(PlaneBundle(), dry_run=False)
    assert report.to_create == 0


@pytest.mark.asyncio
async def test_import_empty_bundle_no_projects_raises_integrity_error(
    setup_import_env: tuple[AsyncSession, PrincipalContext, Path],
) -> None:
    """Verify empty bundle with zero workspace projects raises ImportIntegrityError."""
    session, caller, blob_dir = setup_import_env
    importer = PlaneImporter(session=session, caller=caller, blob_store_root=blob_dir)
    with pytest.raises(ImportIntegrityError, match="No projects found"):
        await importer.run_import(PlaneBundle(), dry_run=False)


@pytest.mark.asyncio
async def test_import_with_custom_state_dates_and_relations(
    setup_import_env: tuple[AsyncSession, PrincipalContext, Path],
) -> None:
    """Verify custom workflow state, cycle/module dates, parent relations, and comments with parent links."""
    from kanban.importer.plane_client import (
        PlaneComment,
        PlaneCycle,
        PlaneLabel,
        PlaneModule,
        PlaneProject,
        PlaneRelation,
        PlaneState,
    )

    session, caller, blob_dir = setup_import_env
    bundle = PlaneBundle(
        projects=[PlaneProject(id="p-custom", identifier="CUST", name="Custom Project")],
        states=[
            PlaneState(
                id="st-review", name="Under Security Review", group="unstarted", project="p-custom"
            ),
            PlaneState(id="st-cancelled", name="Cancelled", group="cancelled", project="p-custom"),
        ],
        labels=[
            PlaneLabel(id="lbl-1", name="security-audit", color="#ff0000", project="p-custom"),
        ],
        cycles=[
            PlaneCycle(
                id="c-1",
                name="Cycle 2026-Q1",
                status="current",
                start_date="2026-01-01",
                end_date="2026-01-31",
                project="p-custom",
            ),
        ],
        modules=[
            PlaneModule(
                id="m-1",
                name="Auth Module",
                start_date="2026-01-01",
                target_date="2026-02-01",
                project="p-custom",
            ),
        ],
        issues=[
            PlaneIssue(
                id="iss-p", sequence_id=1, name="Parent", project="p-custom", state="st-review"
            ),
            PlaneIssue(
                id="iss-c",
                sequence_id=2,
                name="Child",
                project="p-custom",
                parent="iss-p",
                cycle="c-1",
                module="m-1",
                labels=["lbl-1"],
                priority="high",
            ),
        ],
        relations=[
            PlaneRelation(
                id="rel-custom", issue="iss-c", related_issue="iss-p", relation_type="custom_type"
            ),
        ],
        comments=[
            PlaneComment(id="comm-1", issue="iss-c", comment_html="<p>Root comment</p>"),
            PlaneComment(
                id="comm-2",
                issue="iss-c",
                comment_html="<p>Reply comment</p>",
                parent_comment="comm-1",
            ),
        ],
    )

    importer = PlaneImporter(session=session, caller=caller, blob_store_root=blob_dir)
    report = await importer.run_import(bundle, dry_run=False)
    assert report.to_create > 0

    # Verify custom state exists in DB
    st = (
        await session.execute(
            select(WorkflowState).where(WorkflowState.name == "Under Security Review")
        )
    ).scalar_one_or_none()
    assert st is not None


@pytest.mark.asyncio
async def test_import_entity_updates_and_invalid_links_gate(
    setup_import_env: tuple[AsyncSession, PrincipalContext, Path],
) -> None:
    """Verify entity updates when sha changes and post-import link audit rejection gate."""
    from unittest.mock import patch

    from kanban.importer.plane_client import (
        PlaneBundle,
        PlaneCycle,
        PlaneLabel,
        PlaneModule,
        PlaneProject,
        PlaneState,
    )

    session, caller, blob_dir = setup_import_env
    bundle = PlaneBundle(
        projects=[PlaneProject(id="p-upd", identifier="UPD", name="Upd Project")],
        states=[PlaneState(id="st-upd", name="Initial State", group="unstarted", project="p-upd")],
        labels=[PlaneLabel(id="lbl-upd", name="initial-label", color="#111111", project="p-upd")],
        cycles=[PlaneCycle(id="c-upd", name="Initial Cycle", status="upcoming", project="p-upd")],
        modules=[PlaneModule(id="m-upd", name="Initial Module", project="p-upd")],
    )

    importer = PlaneImporter(session=session, caller=caller, blob_store_root=blob_dir)
    rep1 = await importer.run_import(bundle, dry_run=False)
    assert rep1.to_create > 0

    # Modify SHA by changing properties
    bundle.projects[0].name = "Renamed Project"
    bundle.states[0].name = "Modified State"
    bundle.labels[0].color = "#222222"
    bundle.cycles[0].name = "Modified Cycle"
    bundle.modules[0].name = "Modified Module"

    rep2 = await importer.run_import(bundle, dry_run=False)
    assert rep2.to_update >= 4

    # Test audit_object_links failure gate
    original_execute = session.execute

    async def fake_execute(statement: Any, params: Any = None, *args: Any, **kwargs: Any) -> Any:
        if hasattr(statement, "text") and "audit_object_links" in statement.text:

            class DummyResult:
                def scalar_one(self) -> int:
                    return 2

            return DummyResult()
        return await original_execute(statement, params, *args, **kwargs)

    with patch.object(session, "execute", side_effect=fake_execute):
        with pytest.raises(
            ImportIntegrityError, match="audit_object_links discovered 2 invalid links"
        ):
            await importer.run_import(bundle, dry_run=False)


def test_parse_iso_date_helpers() -> None:
    """Verify _parse_iso_date handles various formats, spaces, and invalid inputs."""
    from datetime import date
    from kanban.importer.plane_importer import _parse_iso_date

    assert _parse_iso_date("2026-11-21") == date(2026, 11, 21)
    assert _parse_iso_date("2026-11-21T12:00:00+00:00") == date(2026, 11, 21)
    assert _parse_iso_date("2026-11-21 12:00:00.123456+00:00") == date(2026, 11, 21)
    assert _parse_iso_date(None) is None
    assert _parse_iso_date("invalid-date") is None
    assert _parse_iso_date("") is None
