# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Lossless transactional Plane importer implementation (KB-P6-01, S1.3, S15.5)."""

from __future__ import annotations

import logging
import uuid
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from database.models import (
    Attachment,
    Cycle,
    ImportEntityMapping,
    Issue,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    IssueModule,
    LinkKind,
    Module,
    ObjectKind,
    ObjectLink,
    Project,
    ProjectLabel,
    ProjectPriority,
    RoleBinding,
    WorkflowState,
)
from kanban.attachments.pdf import sanitize_and_validate_pdf
from kanban.attachments.raster import sanitize_and_reencode_raster
from kanban.attachments.sniff import sniff_media_type
from kanban.attachments.storage import LocalFilesystemBlobStore
from kanban.content.svg_sanitizer import sanitize_svg
from kanban.importer.plane_mapper import (
    PRIORITY_MAP,
    RELATION_KIND_MAP,
    STATE_GROUP_MAP,
    ImportDiffReport,
    PlaneMapper,
    compute_source_sha256,
)
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.board_rank import allocate_initial_board_rank

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext
    from kanban.importer.plane_client import PlaneBundle, PlaneIssue

logger = logging.getLogger(__name__)

__all__ = ["ImportDiffReport", "ImportIntegrityError", "PlaneImporter"]


class ImportIntegrityError(Exception):
    """Raised when post-import integrity audit or foreign key verification fails."""


class PlaneImporter:
    """Transactional engine importing Plane snapshots with exact sequence continuity."""

    def __init__(
        self,
        session: AsyncSession,
        caller: PrincipalContext,
        *,
        blob_store_root: Path | str | None = None,
        user_map: dict[str, str] | None = None,
        unmapped_assignees_as_free_text: bool = True,
    ) -> None:
        """Initialize PlaneImporter with database session, caller context, and storage roots."""
        self.session = session
        self.caller = caller
        self.mapper = PlaneMapper(
            user_map=user_map,
            unmapped_assignees_as_free_text=unmapped_assignees_as_free_text,
        )
        default_blob = "/tmp/kanban-attachments"  # noqa: S108
        self.blob_store_root = Path(blob_store_root or default_blob).resolve()
        self.blob_store = LocalFilesystemBlobStore(self.blob_store_root)

    async def run_import(
        self,
        bundle: PlaneBundle,
        *,
        dry_run: bool = False,
    ) -> ImportDiffReport:
        """Execute Plane import within a transactional boundary, supporting dry-run rollback."""
        report = ImportDiffReport()

        if dry_run:
            # Run inside an isolated transaction that always rolls back
            async with self.session.begin_nested():
                await self._execute_import(bundle, report)
                await self.session.rollback()
        else:
            await self._execute_import(bundle, report)

        return report

    async def _execute_import(  # noqa: C901, PLR0912, PLR0915
        self,
        bundle: PlaneBundle,
        report: ImportDiffReport,
    ) -> None:
        workspace_id = self.caller.workspace_id

        # 0. Load existing mappings for idempotency checks
        mappings_stmt = select(ImportEntityMapping).where(
            ImportEntityMapping.workspace_id == workspace_id,
            ImportEntityMapping.source_system == "plane",
        )
        existing_mappings_rows = (await self.session.execute(mappings_stmt)).scalars().all()
        mapping_cache: dict[tuple[str, str], ImportEntityMapping] = {
            (m.source_kind, m.source_id): m for m in existing_mappings_rows
        }

        # 1. Projects
        project_map: dict[str, uuid.UUID] = {}
        target_project_id: uuid.UUID | None = None

        for p in bundle.projects:
            source_key = ("project", p.id)
            sha = compute_source_sha256(p)

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                project_map[p.id] = m.target_id
                target_project_id = m.target_id
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    report.to_update += 1
            else:
                # Check if project with same identifier exists in workspace
                existing_proj = (
                    await self.session.execute(
                        select(Project).where(
                            Project.workspace_id == workspace_id,
                            Project.identifier == p.identifier,
                        )
                    )
                ).scalar_one_or_none()

                if existing_proj:
                    p_id = existing_proj.id
                    report.unchanged += 1
                else:
                    # Register project object
                    p_id = (
                        await self.session.execute(
                            text(
                                "SELECT register_object("
                                "  CAST('project' AS object_kind), :ws, NULL, "
                                "  :ident, :name, :creator"
                                ")"
                            ),
                            {
                                "ws": workspace_id,
                                "ident": p.identifier,
                                "name": p.name,
                                "creator": self.caller.principal_id,
                            },
                        )
                    ).scalar_one()

                    new_proj = Project(
                        id=p_id,
                        workspace_id=workspace_id,
                        identifier=p.identifier,
                        name=p.name,
                        description_markdown=p.description or "",
                        modules_enabled=len(bundle.modules) > 0,
                    )
                    self.session.add(new_proj)
                    await self.session.flush()

                    # Add caller as PROJECT_ADMIN
                    self.session.add(
                        RoleBinding(
                            workspace_id=workspace_id,
                            principal_id=self.caller.principal_id,
                            role="PROJECT_ADMIN",
                            scope_type="project",
                            project_id=p_id,
                        )
                    )
                    report.to_create += 1

                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="project",
                    source_id=p.id,
                    target_id=p_id,
                    source_sha256=sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
                project_map[p.id] = p_id
                target_project_id = p_id

        if not target_project_id:
            # Fallback to existing project in workspace if bundle lacked projects
            first_proj = (
                (
                    await self.session.execute(
                        select(Project).where(Project.workspace_id == workspace_id)
                    )
                )
                .scalars()
                .first()
            )
            if first_proj:
                target_project_id = first_proj.id
            else:
                msg = "No projects found in bundle or workspace."
                raise ImportIntegrityError(msg)

        # 2. Workflow States
        state_map: dict[str, uuid.UUID] = {}
        existing_states = (
            (
                await self.session.execute(
                    select(WorkflowState).where(WorkflowState.project_id == target_project_id)
                )
            )
            .scalars()
            .all()
        )
        states_by_name = {s.name.lower(): s for s in existing_states}
        states_by_group = {s.state_group.lower(): s for s in existing_states}

        for s in bundle.states:
            source_key = ("state", s.id)
            sha = compute_source_sha256(s)
            state_proj = project_map.get(s.project or "", target_project_id)

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                state_map[s.id] = m.target_id
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    report.to_update += 1
            else:
                s_name_lower = s.name.lower()
                mapped_group = STATE_GROUP_MAP.get(s.group.lower(), "unstarted")

                if s_name_lower in states_by_name:
                    st_id = states_by_name[s_name_lower].id
                    report.unchanged += 1
                elif mapped_group in states_by_group and s.name in (
                    "Backlog",
                    "Todo",
                    "In Progress",
                    "Done",
                    "Cancelled",
                ):
                    st_id = states_by_group[mapped_group].id
                    report.unchanged += 1
                else:
                    # Insert custom state
                    new_state = WorkflowState(
                        workspace_id=workspace_id,
                        project_id=state_proj,
                        name=s.name,
                        state_group=mapped_group,
                        color_hex=s.color or "#A3A3A3",
                        sort_order=s.sequence or 0,
                    )
                    self.session.add(new_state)
                    await self.session.flush()
                    st_id = new_state.id
                    states_by_name[s_name_lower] = new_state
                    report.to_create += 1

                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="state",
                    source_id=s.id,
                    target_id=st_id,
                    source_sha256=sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
                state_map[s.id] = st_id

        # 3. Project Priorities
        priorities = (
            (
                await self.session.execute(
                    select(ProjectPriority).where(ProjectPriority.project_id == target_project_id)
                )
            )
            .scalars()
            .all()
        )
        priorities_by_slug = {p.slug.lower(): p.id for p in priorities}
        priorities_by_slug.get("none") or (priorities[0].id if priorities else uuid.uuid4())

        # 4. Project Labels
        label_map: dict[str, uuid.UUID] = {}
        existing_labels = (
            (
                await self.session.execute(
                    select(ProjectLabel).where(ProjectLabel.project_id == target_project_id)
                )
            )
            .scalars()
            .all()
        )
        labels_by_name = {lbl.name.lower(): lbl for lbl in existing_labels}

        for lbl in bundle.labels:
            source_key = ("label", lbl.id)
            sha = compute_source_sha256(lbl)
            lbl_proj = project_map.get(lbl.project or "", target_project_id)

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                label_map[lbl.id] = m.target_id
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    report.to_update += 1
            else:
                lbl_name_lower = lbl.name.lower()
                if lbl_name_lower in labels_by_name:
                    target_lbl_id = labels_by_name[lbl_name_lower].id
                    report.unchanged += 1
                else:
                    new_lbl = ProjectLabel(
                        workspace_id=workspace_id,
                        project_id=lbl_proj,
                        name=lbl.name,
                        color_hex=lbl.color or "#3B82F6",
                    )
                    self.session.add(new_lbl)
                    await self.session.flush()
                    target_lbl_id = new_lbl.id
                    labels_by_name[lbl_name_lower] = new_lbl
                    report.to_create += 1

                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="label",
                    source_id=lbl.id,
                    target_id=target_lbl_id,
                    source_sha256=sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
                label_map[lbl.id] = target_lbl_id

        # 5. Cycles
        cycle_map: dict[str, uuid.UUID] = {}
        for c in bundle.cycles:
            source_key = ("cycle", c.id)
            sha = compute_source_sha256(c)
            c_proj = project_map.get(c.project or "", target_project_id)

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                cycle_map[c.id] = m.target_id
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    report.to_update += 1
            else:
                cycle_id = uuid.uuid4()
                canonical_key = f"cycle-{str(cycle_id)[:8]}"
                await self.session.execute(
                    text(
                        "SELECT register_object("
                        "  CAST('cycle' AS object_kind), :ws, :proj, :ckey, :title, :creator, :id"
                        ")"
                    ),
                    {
                        "ws": workspace_id,
                        "proj": c_proj,
                        "ckey": canonical_key,
                        "title": c.name,
                        "creator": self.caller.principal_id,
                        "id": cycle_id,
                    },
                )
                s_date = date.fromisoformat(c.start_date) if c.start_date else None
                e_date = date.fromisoformat(c.end_date) if c.end_date else None
                raw_status = (c.status or "upcoming").lower()
                if raw_status in ("current", "active"):
                    c_status = "active"
                elif raw_status in ("upcoming", "completed"):
                    c_status = raw_status
                else:
                    c_status = "upcoming"
                new_cycle = Cycle(
                    id=cycle_id,
                    workspace_id=workspace_id,
                    project_id=c_proj,
                    name=c.name,
                    status=c_status,
                    start_date=s_date,
                    end_date=e_date,
                )
                self.session.add(new_cycle)
                await self.session.flush()

                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="cycle",
                    source_id=c.id,
                    target_id=cycle_id,
                    source_sha256=sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
                cycle_map[c.id] = cycle_id
                report.to_create += 1

        # 6. Modules
        module_map: dict[str, uuid.UUID] = {}
        if bundle.modules:
            await self.session.execute(
                text("UPDATE projects SET modules_enabled = TRUE WHERE id = :pid"),
                {"pid": target_project_id},
            )

        for mod in bundle.modules:
            source_key = ("module", mod.id)
            sha = compute_source_sha256(mod)
            mod_proj = project_map.get(mod.project or "", target_project_id)

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                module_map[mod.id] = m.target_id
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    report.to_update += 1
            else:
                mod_id = uuid.uuid4()
                canonical_key = f"mod-{str(mod_id)[:8]}"
                await self.session.execute(
                    text(
                        "SELECT register_object("
                        "  CAST('module' AS object_kind), :ws, :proj, :ckey, :title, :creator, :id"
                        ")"
                    ),
                    {
                        "ws": workspace_id,
                        "proj": mod_proj,
                        "ckey": canonical_key,
                        "title": mod.name,
                        "creator": self.caller.principal_id,
                        "id": mod_id,
                    },
                )
                new_mod = Module(
                    id=mod_id,
                    workspace_id=workspace_id,
                    project_id=mod_proj,
                    name=mod.name,
                    description_markdown=mod.description or "",
                    status=mod.status or "planned",
                )
                self.session.add(new_mod)
                await self.session.flush()

                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="module",
                    source_id=mod.id,
                    target_id=mod_id,
                    source_sha256=sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
                module_map[mod.id] = mod_id
                report.to_create += 1

        # 7. Attachments Ingestion & URL Map
        attachment_url_map: dict[str, uuid.UUID] = {}
        for att_filename, raw_bytes in bundle.attachments.items():
            source_key = ("attachment", att_filename)
            sha = compute_source_sha256({"name": att_filename, "size": len(raw_bytes)})

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                att_id = m.target_id
                report.unchanged += 1
            else:
                is_svg = att_filename.lower().endswith(".svg") or raw_bytes.strip().startswith(
                    b"<svg"
                )
                is_pdf = att_filename.lower().endswith(".pdf") or raw_bytes.startswith(
                    (b"%PDF-1.", b"%PDF-2.")
                )
                if is_svg:
                    clean_svg_val = sanitize_svg(raw_bytes)
                    clean_bytes = clean_svg_val.encode("utf-8")
                    detected_type = "image/svg+xml"
                    p_w, p_h, page_cnt = None, None, None
                elif is_pdf:
                    pdf_res = await sanitize_and_validate_pdf(raw_bytes)
                    clean_bytes = pdf_res.clean_bytes
                    detected_type = "application/pdf"
                    p_w, p_h, page_cnt = None, None, pdf_res.page_count
                else:
                    detected_type = sniff_media_type(raw_bytes[:4096], None, att_filename)
                    processed = await sanitize_and_reencode_raster(raw_bytes, detected_type)
                    clean_bytes = processed.clean_bytes
                    p_w, p_h, page_cnt = processed.pixel_width, processed.pixel_height, None

                storage_key, raw_sha = self.blob_store.store(clean_bytes)
                att_id = uuid.uuid4()
                att = Attachment(
                    id=att_id,
                    workspace_id=workspace_id,
                    project_id=target_project_id,
                    uploaded_by_id=self.caller.principal_id,
                    original_filename=att_filename,
                    content_type=detected_type,
                    byte_size=len(clean_bytes),
                    pixel_width=p_w,
                    pixel_height=p_h,
                    page_count=page_cnt,
                    blob_sha256=raw_sha,
                    storage_key=storage_key,
                )
                self.session.add(att)
                await self.session.flush()

                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="attachment",
                    source_id=att_filename,
                    target_id=att_id,
                    source_sha256=sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
                report.to_create += 1

            attachment_url_map[att_filename] = att_id
            attachment_url_map[f"/api/assets/v1/workspace/{att_filename}"] = att_id

        # 8. Issues & Sequence High Water Mark
        issue_map: dict[str, uuid.UUID] = {}
        sorted_issues, depth_warnings = self.mapper.sort_issues_topologically(bundle.issues)
        report.warnings.extend(depth_warnings)

        if sorted_issues:
            max_seq = max(i.sequence_id for i in sorted_issues)
            report.sequence_high_water_mark = max_seq

            # Group issues by project to advance each project's sequence counter
            issues_by_proj: dict[uuid.UUID, list[PlaneIssue]] = {}
            for issue in sorted_issues:
                proj_id = project_map.get(issue.project or "", target_project_id)
                issues_by_proj.setdefault(proj_id, []).append(issue)

            for p_id, p_issues in issues_by_proj.items():
                p_max_seq = max(i.sequence_id for i in p_issues)
                await self.session.execute(
                    text(
                        "UPDATE projects "
                        "SET issue_seq_counter = GREATEST(issue_seq_counter, :max_seq) "
                        "WHERE id = :pid"
                    ),
                    {"max_seq": p_max_seq, "pid": p_id},
                )
            await self.session.flush()

        # Cache project states and priorities for accurate per-project resolution
        all_states = (
            (
                await self.session.execute(
                    select(WorkflowState).where(WorkflowState.workspace_id == workspace_id)
                )
            )
            .scalars()
            .all()
        )
        states_by_id = {s.id: s for s in all_states}
        states_by_proj_and_name = {(s.project_id, s.name.lower()): s.id for s in all_states}
        states_by_proj_and_group = {(s.project_id, s.state_group.lower()): s.id for s in all_states}
        states_by_proj_default = {s.project_id: s.id for s in all_states if s.is_default}

        all_priorities = (
            (
                await self.session.execute(
                    select(ProjectPriority).where(ProjectPriority.workspace_id == workspace_id)
                )
            )
            .scalars()
            .all()
        )
        priorities_by_proj_and_slug = {(p.project_id, p.slug.lower()): p.id for p in all_priorities}
        priorities_by_proj_default = {p.project_id: p.id for p in all_priorities if p.is_default}

        plane_states_by_id = {s.id: s for s in bundle.states}

        # Resolve unmapped members list for report
        for mbr in bundle.members:
            handle, is_unmapped = self.mapper.resolve_user_handle(mbr.id, bundle)
            if is_unmapped and mbr.id not in report.unmapped_members:
                report.unmapped_members.append(mbr.id)

        # Ingest issues in topological order (parents first)
        for issue in sorted_issues:
            source_key = ("issue", issue.id)
            sha = compute_source_sha256(issue)
            issue_proj = project_map.get(issue.project or "", target_project_id)

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                issue_map[issue.id] = m.target_id
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    report.to_update += 1
            else:
                # Canonical key: <IDENTIFIER>-<sequence_id>
                proj_ident = (
                    await self.session.execute(
                        select(Project.identifier).where(Project.id == issue_proj)
                    )
                ).scalar_one()
                canonical_key = f"{proj_ident}-{issue.sequence_id}"

                # Register object in spine
                issue_id = (
                    await self.session.execute(
                        text(
                            "SELECT register_object("
                            "  CAST('issue' AS object_kind), :ws, :proj, :key, :title, :creator"
                            ")"
                        ),
                        {
                            "ws": workspace_id,
                            "proj": issue_proj,
                            "key": canonical_key,
                            "title": issue.name,
                            "creator": self.caller.principal_id,
                        },
                    )
                ).scalar_one()

                # Normalize description and rewrite attachment URLs
                raw_desc = issue.description_html or issue.description_stripped or ""
                clean_desc, rewritten_cnt = self.mapper.normalize_content_and_rewrite_attachments(
                    raw_desc, attachment_url_map
                )
                report.rewritten_attachments += rewritten_cnt

                # Resolve state strictly within issue_proj
                target_state_id = None
                raw_st_ref = issue.state_id or issue.state
                mapped_st_id = state_map.get(raw_st_ref or "")
                if (
                    mapped_st_id
                    and mapped_st_id in states_by_id
                    and states_by_id[mapped_st_id].project_id == issue_proj
                ):
                    target_state_id = mapped_st_id
                elif raw_st_ref in plane_states_by_id:
                    pst = plane_states_by_id[raw_st_ref]
                    target_state_id = states_by_proj_and_name.get(
                        (issue_proj, pst.name.lower())
                    ) or states_by_proj_and_group.get((issue_proj, pst.group.lower()))

                if not target_state_id:
                    target_state_id = states_by_proj_default.get(issue_proj) or next(
                        s.id for s in all_states if s.project_id == issue_proj
                    )

                # Resolve priority strictly within issue_proj
                target_prio_slug = PRIORITY_MAP.get((issue.priority or "").lower(), "none")
                target_prio_id = (
                    priorities_by_proj_and_slug.get((issue_proj, target_prio_slug))
                    or priorities_by_proj_default.get(issue_proj)
                    or next(p.id for p in all_priorities if p.project_id == issue_proj)
                )

                parent_source_id = issue.parent or issue.parent_id
                target_parent_id = issue_map.get(parent_source_id) if parent_source_id else None

                cycle_source_id = issue.cycle_id or issue.cycle
                target_cycle_id = cycle_map.get(cycle_source_id) if cycle_source_id else None

                s_date = date.fromisoformat(issue.start_date) if issue.start_date else None
                t_date = date.fromisoformat(issue.target_date) if issue.target_date else None

                rank = allocate_initial_board_rank(issue.sequence_id)

                new_issue = Issue(
                    id=issue_id,
                    workspace_id=workspace_id,
                    project_id=issue_proj,
                    sequence_id=issue.sequence_id,
                    summary=issue.name,
                    description_markdown=clean_desc,
                    state_id=target_state_id,
                    priority_id=target_prio_id,
                    parent_issue_id=target_parent_id,
                    cycle_id=target_cycle_id,
                    board_rank=rank,
                    created_by_id=self.caller.principal_id,
                    original_created_by_id=self.caller.principal_id,
                    start_date=s_date,
                    due_date=t_date,
                    ancestry_path=issue_id.hex,
                )
                self.session.add(new_issue)
                await self.session.flush()

                # Join labels
                for lbl_ref in issue.labels:
                    resolved_lbl_id = label_map.get(lbl_ref)
                    if resolved_lbl_id is not None:
                        self.session.add(
                            IssueLabel(
                                issue_id=issue_id,
                                label_id=resolved_lbl_id,
                                workspace_id=workspace_id,
                            )
                        )

                # Join module
                mod_ref = issue.module_id or issue.module
                if mod_ref and mod_ref in module_map:
                    self.session.add(
                        IssueModule(
                            issue_id=issue_id,
                            module_id=module_map[mod_ref],
                            workspace_id=workspace_id,
                        )
                    )

                # Join assignees
                for assignee_ref in issue.assignees:
                    handle, _ = self.mapper.resolve_user_handle(assignee_ref, bundle)
                    if self.mapper.unmapped_assignees_as_free_text:
                        self.session.add(
                            IssueAssignee(
                                issue_id=issue_id,
                                workspace_id=workspace_id,
                                free_text_assignee=handle,
                            )
                        )

                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="issue",
                    source_id=issue.id,
                    target_id=issue_id,
                    source_sha256=sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
                issue_map[issue.id] = issue_id
                report.to_create += 1

        # 9. Comments
        for comm in bundle.comments:
            source_key = ("comment", comm.id)
            sha = compute_source_sha256(comm)
            target_issue_id = issue_map.get(comm.issue_id or comm.issue or "")

            if not target_issue_id:
                continue

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    report.to_update += 1
            else:
                clean_comment, rew_cnt = self.mapper.normalize_content_and_rewrite_attachments(
                    comm.comment_html or "", attachment_url_map
                )
                report.rewritten_attachments += rew_cnt

                new_comment = IssueComment(
                    workspace_id=workspace_id,
                    issue_id=target_issue_id,
                    author_id=self.caller.principal_id,
                    body_markdown=clean_comment,
                )
                self.session.add(new_comment)
                await self.session.flush()

                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="comment",
                    source_id=comm.id,
                    target_id=new_comment.id,
                    source_sha256=sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
                report.to_create += 1

        # 10. Relations / Links
        for rel in bundle.relations:
            src_plane_id = rel.issue or rel.issue_id or ""
            tgt_plane_id = rel.related_issue or rel.related_issue_id or ""
            src_target_id = issue_map.get(src_plane_id)
            tgt_target_id = issue_map.get(tgt_plane_id)

            if not src_target_id or not tgt_target_id or src_target_id == tgt_target_id:
                continue

            link_kind = RELATION_KIND_MAP.get(rel.relation_type.lower(), LinkKind.RELATES_TO)

            # Check existing link
            existing_link = (
                await self.session.execute(
                    select(ObjectLink).where(
                        ObjectLink.workspace_id == workspace_id,
                        ObjectLink.source_id == src_target_id,
                        ObjectLink.target_id == tgt_target_id,
                        ObjectLink.link_type == link_kind,
                    )
                )
            ).scalar_one_or_none()

            if existing_link:
                report.unchanged += 1
            else:
                # Fetch canonical keys
                src_key = (
                    await self.session.execute(
                        text("SELECT canonical_key FROM objects WHERE id = :id"),
                        {"id": src_target_id},
                    )
                ).scalar_one()
                tgt_key = (
                    await self.session.execute(
                        text("SELECT canonical_key FROM objects WHERE id = :id"),
                        {"id": tgt_target_id},
                    )
                ).scalar_one()

                new_link = ObjectLink(
                    workspace_id=workspace_id,
                    source_id=src_target_id,
                    source_type=ObjectKind.ISSUE,
                    target_id=tgt_target_id,
                    target_type=ObjectKind.ISSUE,
                    link_type=link_kind,
                    link_state="ACTIVE",
                    source_key_snapshot=src_key,
                    target_key_snapshot=tgt_key,
                    created_by_id=self.caller.principal_id,
                )
                self.session.add(new_link)
                report.to_create += 1

        await self.session.flush()

        # 11. Post-Import Object Link Audit Gate
        invalid_links_count = (
            await self.session.execute(
                text("SELECT count(*) FROM audit_object_links(:ws)"),
                {"ws": workspace_id},
            )
        ).scalar_one()
        report.invalid_link_count = int(invalid_links_count)

        if report.invalid_link_count > 0:
            msg = (
                f"audit_object_links discovered {report.invalid_link_count} "
                "invalid links post-import."
            )
            raise ImportIntegrityError(msg)

        # 12. Record Activity
        await record_activity(
            self.session,
            workspace_id=workspace_id,
            object_id=target_project_id,
            actor_principal_id=self.caller.principal_id,
            event_type=ActivityEventType.PLANE_IMPORT_COMPLETED,
            payload={
                "project_id": str(target_project_id),
                "to_create": report.to_create,
                "to_update": report.to_update,
                "unchanged": report.unchanged,
                "sequence_high_water_mark": report.sequence_high_water_mark,
                "rewritten_attachments": report.rewritten_attachments,
            },
        )
