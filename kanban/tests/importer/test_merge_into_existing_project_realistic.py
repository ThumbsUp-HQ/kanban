# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Realistic 304-issue Plane merge, non-clobber immutability, state mapping, and pagination tests (KAN-84)."""

# ruff: noqa: E501, PLR0915

from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import func, select, text

from database.models import (
    Issue,
    IssueComment,
    IssueLabel,
    IssueModule,
    Module,
    ObjectRecord,
    Project,
    ProjectLabel,
    ProjectPriority,
    WorkflowState,
)
from kanban.api.deps import PrincipalContext
from kanban.importer.cutover_verifier import verify_cutover
from kanban.importer.plane_client import (
    PlaneBundle,
    PlaneComment,
    PlaneCycle,
    PlaneIssue,
    PlaneLabel,
    PlaneModule,
    PlaneProject,
    PlaneState,
)
from kanban.importer.plane_importer import PlaneImporter
from kanban.importer.plane_mapper import normalize_state_key
from kanban.services.board_rank import allocate_initial_board_rank
from kanban.tests.security.helpers import rebuild_era

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _dump_bundle_dir(bundle: PlaneBundle, bundle_dir: Path) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "projects.json").write_text(
        json.dumps([p.model_dump() for p in bundle.projects]), encoding="utf-8"
    )
    (bundle_dir / "states.json").write_text(
        json.dumps([s.model_dump() for s in bundle.states]), encoding="utf-8"
    )
    (bundle_dir / "labels.json").write_text(
        json.dumps([lbl.model_dump() for lbl in bundle.labels]), encoding="utf-8"
    )
    (bundle_dir / "cycles.json").write_text(
        json.dumps([c.model_dump() for c in bundle.cycles]), encoding="utf-8"
    )
    (bundle_dir / "modules.json").write_text(
        json.dumps([m.model_dump() for m in bundle.modules]), encoding="utf-8"
    )
    (bundle_dir / "issues.json").write_text(
        json.dumps([i.model_dump() for i in bundle.issues]), encoding="utf-8"
    )
    (bundle_dir / "comments.json").write_text(
        json.dumps([c.model_dump() for c in bundle.comments]), encoding="utf-8"
    )
    (bundle_dir / "relations.json").write_text(
        json.dumps([r.model_dump() for r in bundle.relations]), encoding="utf-8"
    )
    (bundle_dir / "members.json").write_text(
        json.dumps([m.model_dump() for m in bundle.members]), encoding="utf-8"
    )


async def _ensure_kan_six_states(env: ApiEnv, project_id: uuid.UUID) -> dict[str, WorkflowState]:
    """Ensure target project has the exact 6 workflow states including Crazy_Ideas (sort_order=0)."""
    existing = (
        (
            await env.seed.execute(
                select(WorkflowState).where(WorkflowState.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    by_name = {s.name: s for s in existing}
    if "Crazy_Ideas" not in by_name:
        crazy = WorkflowState(
            workspace_id=env.workspace_id,
            project_id=project_id,
            name="Crazy_Ideas",
            state_group="started",
            color_hex="#A855F7",
            sort_order=0,
            is_default=False,
        )
        env.seed.add(crazy)
        await env.seed.flush()
        by_name["Crazy_Ideas"] = crazy

    expected_names = {"Backlog", "Todo", "Crazy_Ideas", "In Progress", "Done", "Cancelled"}
    assert set(by_name.keys()) == expected_names
    return by_name


def _state_for_existing_seq(seq: int, states_by_name: dict[str, WorkflowState]) -> WorkflowState:
    """Return the workflow state matching the live 83-issue distribution."""
    if seq <= 54:
        return states_by_name["Done"]
    if seq <= 75:
        return states_by_name["Todo"]
    if seq <= 82:
        return states_by_name["Crazy_Ideas"]
    return states_by_name["Backlog"]


async def _seed_83_existing_kan_issues(
    api_env: ApiEnv,
    kan_id: uuid.UUID,
    admin_id: uuid.UUID,
    states_by_name: dict[str, WorkflowState],
) -> None:
    """Seed KAN-1..83 matching the live board (54 Done, 21 Todo, 7 Crazy_Ideas, 1 Backlog)."""
    default_prio = (
        await api_env.seed.execute(
            select(ProjectPriority).where(
                ProjectPriority.project_id == kan_id,
                ProjectPriority.is_default.is_(True),
            )
        )
    ).scalar_one()

    core_label = ProjectLabel(
        workspace_id=api_env.workspace_id,
        project_id=kan_id,
        name="Core",
        color_hex="#EF4444",
    )
    api_env.seed.add(core_label)
    await api_env.seed.flush()

    core_mod_id = (
        await api_env.seed.execute(
            text(
                "SELECT register_object("
                "  CAST('module' AS object_kind), :ws, :proj, :ckey, :title, :creator"
                ")"
            ),
            {
                "ws": api_env.workspace_id,
                "proj": kan_id,
                "ckey": "mod-core-01",
                "title": "Core Module",
                "creator": admin_id,
            },
        )
    ).scalar_one()
    core_mod = Module(
        id=core_mod_id,
        workspace_id=api_env.workspace_id,
        project_id=kan_id,
        name="Core Module",
        status="in_progress",
    )
    api_env.seed.add(core_mod)
    await api_env.seed.flush()

    await api_env.seed.execute(
        text("UPDATE projects SET issue_seq_counter = 83 WHERE id = :pid"),
        {"pid": kan_id},
    )
    for seq in range(1, 84):
        st = _state_for_existing_seq(seq, states_by_name)
        summary = f"Existing KAN issue {seq}"
        iss_id = (
            await api_env.seed.execute(
                text(
                    "SELECT register_object("
                    "  CAST('issue' AS object_kind), :ws, :proj, :key, :title, :creator"
                    ")"
                ),
                {
                    "ws": api_env.workspace_id,
                    "proj": kan_id,
                    "key": f"KAN-{seq}",
                    "title": summary,
                    "creator": admin_id,
                },
            )
        ).scalar_one()

        api_env.seed.add(
            Issue(
                id=iss_id,
                workspace_id=api_env.workspace_id,
                project_id=kan_id,
                sequence_id=seq,
                summary=summary,
                description_markdown=f"Pre-existing issue body for KAN-{seq}.",
                state_id=st.id,
                priority_id=default_prio.id,
                board_rank=allocate_initial_board_rank(seq),
                created_by_id=admin_id,
                original_created_by_id=admin_id,
                ancestry_path=iss_id.hex,
            )
        )
        await api_env.seed.flush()

        if seq in (1, 55, 76):
            api_env.seed.add(
                IssueLabel(
                    issue_id=iss_id,
                    label_id=core_label.id,
                    workspace_id=api_env.workspace_id,
                )
            )
        if seq in (1, 83):
            api_env.seed.add(
                IssueModule(
                    issue_id=iss_id,
                    module_id=core_mod.id,
                    workspace_id=api_env.workspace_id,
                )
            )
        if seq in (1, 55, 76, 83):
            api_env.seed.add(
                IssueComment(
                    workspace_id=api_env.workspace_id,
                    issue_id=iss_id,
                    author_id=admin_id,
                    body_markdown=f"Pre-existing comment on KAN-{seq}",
                )
            )

    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()


def _build_realistic_221_kanba_bundle() -> PlaneBundle:
    """Build a 221-issue KANBA PlaneBundle (seq 1..233 with 12 gaps) plus excluded TEST project."""
    deleted_seqs = {10, 22, 35, 48, 61, 74, 87, 100, 113, 126, 139, 152}
    kanba_seqs = [s for s in range(1, 234) if s not in deleted_seqs]
    assert len(kanba_seqs) == 221

    special_specs: dict[int, tuple[str, list[str], str | None, str | None]] = {
        1: (
            "<p>Root historical issue KANBA-1 and docs/qa/KANBA-1/unit-test-results.txt</p>",
            ["p-lbl-core"],
            "p-mod-core",
            "p-cyc-1",
        ),
        2: (
            "<p>Depends on KANBA-1 and docs/qa/KANBA-1/unit-test-results.txt</p>",
            [],
            None,
            None,
        ),
        4: (
            "<p>See attached <a href='/api/assets/spec.md'>spec.md</a> and <img src='/api/assets/data.png' /></p>",
            ["p-lbl-core"],
            "p-mod-core",
            None,
        ),
    }
    parent_map = {2: "i-kanba-5", 20: "i-kanba-15"}

    plane_issues: list[PlaneIssue] = []
    for idx, seq in enumerate(kanba_seqs):
        state_ref = "p-st-cancelled" if idx >= 216 else "p-st-done"
        desc_html, labels, mod_id, cycle_id = special_specs.get(
            seq,
            (f"<p>Historical KANBA issue {seq} migrated cleanly.</p>", [], None, None),
        )
        ts = dt.datetime(2026, 2, 1, 10, 0, tzinfo=dt.UTC) + dt.timedelta(minutes=seq)
        plane_issues.append(
            PlaneIssue(
                id=f"i-kanba-{seq}",
                sequence_id=seq,
                name=f"Imported KANBA Issue {seq}",
                description_html=desc_html,
                state_id=state_ref,
                parent_id=parent_map.get(seq),
                project="p-kanba",
                labels=labels,
                module_id=mod_id,
                cycle_id=cycle_id,
                created_at=ts.isoformat(),
                updated_at=(ts + dt.timedelta(seconds=30)).isoformat(),
            )
        )

    plane_issues.extend(
        PlaneIssue(
            id=f"i-test-{t_seq}",
            sequence_id=t_seq,
            name=f"Excluded TEST Issue {t_seq}",
            description_html="<p>Must be excluded</p>",
            state_id="p-st-test-done",
            project="p-test",
            created_at="2026-02-01T08:00:00Z",
        )
        for t_seq in range(1, 4)
    )

    return PlaneBundle(
        projects=[
            PlaneProject(id="p-kanba", identifier="KANBA", name="Kanba Legacy"),
            PlaneProject(id="p-test", identifier="TEST", name="Excluded Test Project"),
        ],
        states=[
            PlaneState(id="p-st-backlog", name="Backlog", group="backlog", project="p-kanba"),
            PlaneState(id="p-st-todo", name="Todo", group="unstarted", project="p-kanba"),
            PlaneState(id="p-st-inprog", name="In Progress", group="started", project="p-kanba"),
            PlaneState(
                id="p-st-crazy", name="Crazy Ideas", group="started", sequence=0, project="p-kanba"
            ),
            PlaneState(id="p-st-done", name="Done", group="completed", project="p-kanba"),
            PlaneState(id="p-st-cancelled", name="Cancelled", group="cancelled", project="p-kanba"),
            PlaneState(id="p-st-test-done", name="Done", group="completed", project="p-test"),
        ],
        labels=[PlaneLabel(id="p-lbl-core", name="Core", color="#FF0000", project="p-kanba")],
        cycles=[
            PlaneCycle(
                id="p-cyc-1",
                name="Sprint 1",
                start_date="2026-02-01",
                end_date="2026-02-14",
                status="completed",
                project="p-kanba",
            )
        ],
        modules=[PlaneModule(id="p-mod-core", name="Core Module", project="p-kanba")],
        issues=plane_issues,
        comments=[
            PlaneComment(
                id="p-comm-3",
                issue_id="i-kanba-3",
                comment_html="<p>Comment referencing KANBA-1</p>",
                created_at="2026-02-02T09:00:00Z",
            ),
            PlaneComment(
                id="p-comm-test",
                issue_id="i-test-1",
                comment_html="<p>Excluded test comment</p>",
                created_at="2026-02-02T09:05:00Z",
            ),
        ],
        attachments={
            "data.png": TINY_PNG,
            "spec.md": b"# Imported Spec\n\nDetailed specification.",
        },
    )


async def _assert_http_pagination_and_filtering(client: httpx.AsyncClient) -> None:
    """Exercise real HTTP calls under kanban_app FORCE RLS for alias, pagination, and state_group."""
    alias_resp = await client.get("/api/v1/issues/KANBA-1")
    assert alias_resp.status_code == 200
    assert alias_resp.json()["key"] == "KAN-84"
    assert alias_resp.headers["X-Kanban-Canonical-Key"] == "KAN-84"

    # Single-page default GET /api/v1/projects/KAN/issues returns KAN-304..KAN-255 + next_cursor
    r_default = await client.get("/api/v1/projects/KAN/issues")
    assert r_default.status_code == 200
    default_body = r_default.json()
    assert len(default_body["items"]) == 50
    assert [item["key"] for item in default_body["items"]] == [
        f"KAN-{seq}" for seq in range(304, 254, -1)
    ]
    assert all(
        item["state"]["group"] in {"completed", "cancelled"} for item in default_body["items"]
    )
    assert default_body["next_cursor"] is not None

    # Traverse all pages with limit=100 -> 4 pages (100 + 100 + 100 + 4 = 304 unique keys)
    all_items: list[dict[str, Any]] = []
    page_sizes: list[int] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 100}
        if cursor is not None:
            params["cursor"] = cursor
        page_resp = await client.get("/api/v1/projects/KAN/issues", params=params)
        assert page_resp.status_code == 200
        page_body = page_resp.json()
        page_items = page_body["items"]
        page_sizes.append(len(page_items))
        all_items.extend(page_items)
        cursor = page_body["next_cursor"]
        if cursor is None:
            break

    assert page_sizes == [100, 100, 100, 4]
    all_keys = [item["key"] for item in all_items]
    assert len(all_keys) == 304
    assert len(set(all_keys)) == 304
    assert all_keys == [f"KAN-{seq}" for seq in range(304, 0, -1)]

    open_items_via_pages = [
        item for item in all_items if item["state"]["group"] in {"backlog", "unstarted", "started"}
    ]
    assert len(open_items_via_pages) == 29

    # Filtered query returns all 29 open KAN-55..KAN-83 issues on page 1
    r_open = await client.get(
        "/api/v1/projects/KAN/issues",
        params=[
            ("state_group", "backlog"),
            ("state_group", "unstarted"),
            ("state_group", "started"),
            ("limit", "100"),
        ],
    )
    assert r_open.status_code == 200
    open_body = r_open.json()
    assert len(open_body["items"]) == 29
    assert open_body["next_cursor"] is None
    assert [item["key"] for item in open_body["items"]] == [
        f"KAN-{seq}" for seq in range(83, 54, -1)
    ]

    r_invalid = await client.get(
        "/api/v1/projects/KAN/issues", params={"state_group": "invalid_group"}
    )
    assert r_invalid.status_code == 422


async def test_realistic_304_issue_merge_preserves_83_existing_and_paginates_all_open_issues(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
) -> None:
    """Merge 221 KANBA issues into 83 existing KAN issues, preserving KAN-1..83 and paginating all 29 open."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    kan_id = await make_project(
        "KAN", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=True
    )
    states_by_name = await _ensure_kan_six_states(api_env, kan_id)
    await _seed_83_existing_kan_issues(api_env, kan_id, admin.id, states_by_name)

    # Capture complete pre-merge forensic snapshot of KAN-1..KAN-83
    snap_rows = (
        await api_env.seed.execute(
            select(Issue, ObjectRecord)
            .join(ObjectRecord, ObjectRecord.id == Issue.id)
            .where(Issue.project_id == kan_id)
            .order_by(Issue.sequence_id.asc())
        )
    ).all()
    assert len(snap_rows) == 83

    pre_snapshot = {
        iss_row.sequence_id: {
            "id": iss_row.id,
            "sequence_id": iss_row.sequence_id,
            "canonical_key": obj_row.canonical_key,
            "summary": iss_row.summary,
            "description_markdown": iss_row.description_markdown,
            "description_sha256": iss_row.description_sha256,
            "state_id": iss_row.state_id,
            "priority_id": iss_row.priority_id,
            "board_rank": iss_row.board_rank,
            "created_at": obj_row.created_at,
            "updated_at": obj_row.updated_at,
            "archived_at": obj_row.archived_at,
        }
        for iss_row, obj_row in snap_rows
    }
    pre_comment_count = int(
        (
            await api_env.seed.execute(
                select(func.count())
                .select_from(IssueComment)
                .join(Issue, Issue.id == IssueComment.issue_id)
                .where(Issue.project_id == kan_id)
            )
        ).scalar_one()
    )
    assert pre_comment_count == 4

    bundle = _build_realistic_221_kanba_bundle()

    await api_env.seed.execute(
        text(
            "SELECT set_config('app.current_workspace_id', :ws, true), "
            "set_config('app.current_principal_id', :pid, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"ws": str(api_env.workspace_id), "pid": str(admin.id)},
    )
    caller = PrincipalContext(principal_id=admin.id, workspace_id=api_env.workspace_id, aal_level=2)
    importer = PlaneImporter(
        session=api_env.seed,
        caller=caller,
        blob_store_root=tmp_path / "blobs",
        target_project_identifier="KAN",
        exclude_project_identifiers={"TEST"},
    )
    report = await importer.run_import(bundle, dry_run=False)
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    assert len(report.key_remap_manifest) == 221
    assert report.key_remap_manifest["KANBA-1"] == "KAN-84"
    assert report.key_remap_manifest["KANBA-233"] == "KAN-304"

    ws_slug = (
        await api_env.seed.execute(
            text("SELECT slug FROM workspaces WHERE id = :ws"), {"ws": api_env.workspace_id}
        )
    ).scalar_one()
    bundle_dir = tmp_path / "bundle"
    _dump_bundle_dir(bundle, bundle_dir)

    qa_root = tmp_path / "qa"
    kanba1_qa = qa_root / "KANBA-1"
    kanba1_qa.mkdir(parents=True, exist_ok=True)
    (kanba1_qa / "git-diff.patch").write_text("diff --git a/x b/x\n", encoding="utf-8")
    (kanba1_qa / "unit-test-results.txt").write_text("1 passed\n", encoding="utf-8")
    (kanba1_qa / "build-check.txt").write_text("ok\n", encoding="utf-8")

    cutover_report = await verify_cutover(
        session=api_env.seed,
        bundle_dir=bundle_dir,
        workspace_slug=ws_slug,
        project_identifier="KAN",
        source_project_identifier="KANBA",
        qa_root=qa_root,
        pre_cutover_exempt_keys={f"KAN-{i}" for i in range(1, 305) if i != 84},
    )
    assert cutover_report.overall_passed is True, cutover_report.model_dump()
    assert len(cutover_report.checks) == 6

    post_rows = (
        await api_env.seed.execute(
            select(Issue, ObjectRecord)
            .join(ObjectRecord, ObjectRecord.id == Issue.id)
            .where(Issue.project_id == kan_id)
            .order_by(Issue.sequence_id.asc())
        )
    ).all()
    assert len(post_rows) == 304

    kan_proj = (
        await api_env.seed.execute(select(Project).where(Project.id == kan_id))
    ).scalar_one()
    assert kan_proj.issue_seq_counter == 304

    for iss_row, obj_row in post_rows[:83]:
        snap = pre_snapshot[iss_row.sequence_id]
        assert iss_row.id == snap["id"]
        assert iss_row.sequence_id == snap["sequence_id"]
        assert obj_row.canonical_key == snap["canonical_key"]
        assert iss_row.summary == snap["summary"]
        assert iss_row.description_markdown == snap["description_markdown"]
        assert iss_row.description_sha256 == snap["description_sha256"]
        assert iss_row.state_id == snap["state_id"]
        assert iss_row.priority_id == snap["priority_id"]
        assert iss_row.board_rank == snap["board_rank"]
        assert obj_row.created_at == snap["created_at"]
        assert obj_row.updated_at == snap["updated_at"]
        assert obj_row.archived_at == snap["archived_at"]

    assert [r[0].sequence_id for r in post_rows[83:]] == list(range(84, 305))

    test_leaked = (
        (
            await api_env.seed.execute(
                select(Issue).where(
                    Issue.project_id == kan_id,
                    Issue.summary.like("Excluded TEST Issue%"),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(test_leaked) == 0

    kan_states = (
        (
            await api_env.seed.execute(
                select(WorkflowState).where(WorkflowState.project_id == kan_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(kan_states) == 6

    await _assert_http_pagination_and_filtering(as_principal(admin))

    # Idempotent re-import allocates 0 new entities
    await api_env.seed.execute(
        text(
            "SELECT set_config('app.current_workspace_id', :ws, true), "
            "set_config('app.current_principal_id', :pid, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"ws": str(api_env.workspace_id), "pid": str(admin.id)},
    )
    importer2 = PlaneImporter(
        session=api_env.seed,
        caller=caller,
        blob_store_root=tmp_path / "blobs",
        target_project_identifier="KAN",
        exclude_project_identifiers={"TEST"},
    )
    report2 = await importer2.run_import(bundle, dry_run=False)
    await api_env.seed.commit()
    assert report2.to_create == 0

    total_after_reimport = int(
        (
            await api_env.seed.execute(
                select(func.count()).select_from(Issue).where(Issue.project_id == kan_id)
            )
        ).scalar_one()
    )
    assert total_after_reimport == 304


async def test_normalize_state_key_and_crazy_ideas_issue_landing(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    tmp_path: Path,
) -> None:
    """Verify normalize_state_key edge cases and landing 'Crazy Ideas' issues in 'Crazy_Ideas'."""
    assert normalize_state_key(None) == ""
    assert normalize_state_key("") == ""
    assert normalize_state_key("Crazy Ideas") == "crazyideas"
    assert normalize_state_key("Crazy_Ideas") == "crazyideas"
    assert normalize_state_key("crazy-ideas") == "crazyideas"
    assert normalize_state_key("Canceled") == "cancelled"
    assert normalize_state_key("In Progress") == "inprogress"

    admin = await make_user("admin_ci", workspace_role="WORKSPACE_ADMIN")
    kan_id = await make_project(
        "KAN", created_by=admin, roles={admin: "PROJECT_ADMIN"}, modules_enabled=True
    )
    states_by_name = await _ensure_kan_six_states(api_env, kan_id)
    crazy_ideas_id = states_by_name["Crazy_Ideas"].id
    cancelled_id = states_by_name["Cancelled"].id
    await api_env.seed.commit()

    bundle = PlaneBundle(
        projects=[PlaneProject(id="p-src", identifier="SRC", name="Source")],
        states=[
            PlaneState(
                id="st-crazy-space",
                name="Crazy Ideas",
                group="started",
                sequence=0,
                project="p-src",
            ),
            PlaneState(
                id="st-canceled-us",
                name="Canceled",
                group="cancelled",
                sequence=5,
                project="p-src",
            ),
        ],
        issues=[
            PlaneIssue(
                id="iss-crazy",
                sequence_id=1,
                name="Brainstorm idea",
                description_html="<p>Land in Crazy_Ideas</p>",
                state_id="st-crazy-space",
                project="p-src",
            ),
            PlaneIssue(
                id="iss-canceled",
                sequence_id=2,
                name="Canceled idea",
                description_html="<p>Land in Cancelled</p>",
                state_id="st-canceled-us",
                project="p-src",
            ),
        ],
    )

    await api_env.seed.execute(
        text(
            "SELECT set_config('app.current_workspace_id', :ws, true), "
            "set_config('app.current_principal_id', :pid, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"ws": str(api_env.workspace_id), "pid": str(admin.id)},
    )
    caller = PrincipalContext(principal_id=admin.id, workspace_id=api_env.workspace_id, aal_level=2)
    importer = PlaneImporter(
        session=api_env.seed,
        caller=caller,
        blob_store_root=tmp_path / "blobs",
        target_project_identifier="KAN",
    )
    await importer.run_import(bundle, dry_run=False)
    await api_env.seed.commit()

    all_states = (
        (
            await api_env.seed.execute(
                select(WorkflowState).where(WorkflowState.project_id == kan_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(all_states) == 6

    imported_crazy = (
        await api_env.seed.execute(
            select(Issue).where(Issue.project_id == kan_id, Issue.sequence_id == 1)
        )
    ).scalar_one()
    assert imported_crazy.state_id == crazy_ideas_id

    imported_canceled = (
        await api_env.seed.execute(
            select(Issue).where(Issue.project_id == kan_id, Issue.sequence_id == 2)
        )
    ).scalar_one()
    assert imported_canceled.state_id == cancelled_id
