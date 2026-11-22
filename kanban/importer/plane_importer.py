# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Lossless transactional Plane importer implementation (KB-P6-01, KB-MIGRATION-PLANE-DB-01, S1.3, S15.5)."""
# ruff: noqa: E501, C901, PLR0912, PLR0913, PLR0915, BLE001, ICN001, TRY300

from __future__ import annotations

import datetime
import hashlib
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
    IssueKeyAlias,
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
from kanban.content.normalize import normalize_plain_text, normalize_to_markdown
from kanban.content.svg_sanitizer import sanitize_svg
from kanban.importer.plane_mapper import (
    PRIORITY_MAP,
    RELATION_KIND_MAP,
    STATE_GROUP_MAP,
    ImportDiffReport,
    PlaneMapper,
    compute_source_sha256,
    normalize_state_key,
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


def _parse_iso_datetime(val: str | None) -> datetime.datetime | None:
    """Parse ISO datetime string into UTC datetime."""
    if not val:
        return None
    try:
        dt = datetime.datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.UTC)
        return dt
    except Exception:
        return None


def _parse_iso_date(val: str | None) -> date | None:
    """Parse ISO date or datetime string into date object."""
    if not val:
        return None
    try:
        if "T" in val or " " in val:
            return datetime.datetime.fromisoformat(val).date()
        return date.fromisoformat(val)
    except Exception:
        return None


class PlaneImporter:
    """Transactional engine importing Plane snapshots with exact sequence continuity and merge mode."""

    def __init__(
        self,
        session: AsyncSession,
        caller: PrincipalContext,
        *,
        blob_store_root: Path | str | None = None,
        user_map: dict[str, str] | None = None,
        unmapped_assignees_as_free_text: bool = True,
        target_project_identifier: str | None = None,
        exclude_project_identifiers: list[str] | set[str] | str | None = None,
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
        self.target_project_identifier = (
            target_project_identifier.strip().upper() if target_project_identifier else None
        )

        if isinstance(exclude_project_identifiers, str):
            self.exclude_project_identifiers = {
                x.strip().upper() for x in exclude_project_identifiers.split(",") if x.strip()
            }
        elif isinstance(exclude_project_identifiers, (list, set)):
            self.exclude_project_identifiers = {
                str(x).strip().upper() for x in exclude_project_identifiers if str(x).strip()
            }
        else:
            self.exclude_project_identifiers = set()

    async def run_import(
        self,
        bundle: PlaneBundle,
        *,
        dry_run: bool = False,
    ) -> ImportDiffReport:
        """Execute Plane import within a transactional boundary, supporting dry-run rollback."""
        report = ImportDiffReport()

        if dry_run:
            async with self.session.begin_nested():
                await self._execute_import(bundle, report)
                await self.session.rollback()
        else:
            await self._execute_import(bundle, report)

        return report

    async def _execute_import(
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

        # Resolve workspace users/principals for user mapping
        p_users_res = await self.session.execute(
            text(
                "SELECT p.id, u.email, p.display_name, o.canonical_key "
                "FROM principals p "
                "JOIN users u ON p.id = u.id "
                "JOIN objects o ON p.id = o.id "
                "WHERE p.workspace_id = :ws AND p.status = 'ACTIVE'"
            ),
            {"ws": workspace_id},
        )
        user_lookup: dict[str, uuid.UUID] = {}
        for r in p_users_res.mappings().all():
            user_lookup[r["canonical_key"].lower()] = r["id"]
            user_lookup[r["email"].lower()] = r["id"]
            user_lookup[r["display_name"].lower()] = r["id"]

        def _resolve_principal(plane_uid: str | None) -> uuid.UUID | None:
            if not plane_uid or not self.mapper.user_map:
                return None
            target_str = self.mapper.user_map.get(plane_uid)
            if not target_str:
                return None
            clean_str = target_str.lstrip("@").lower()
            return user_lookup.get(clean_str)

        # 1. Projects resolution
        project_map: dict[str, uuid.UUID] = {}
        project_ident_map: dict[str, str] = {}
        target_project_id: uuid.UUID | None = None
        target_project_ident: str | None = self.target_project_identifier

        # Excluded projects set: identifiers and IDs
        excluded_project_ids = {
            p.id
            for p in bundle.projects
            if p.identifier.upper() in self.exclude_project_identifiers
        }
        excluded_project_idents = {
            p.identifier.upper()
            for p in bundle.projects
            if p.identifier.upper() in self.exclude_project_identifiers
        } | self.exclude_project_identifiers

        # Filter out excluded projects
        active_bundle_projects = [
            p
            for p in bundle.projects
            if p.identifier.upper() not in excluded_project_idents
            and p.id not in excluded_project_ids
        ]

        if self.target_project_identifier:
            # Merge mode: all bundle projects are mapped to the specified target project
            target_proj_row = (
                await self.session.execute(
                    select(Project).where(
                        Project.workspace_id == workspace_id,
                        Project.identifier == self.target_project_identifier,
                    )
                )
            ).scalar_one_or_none()

            if not target_proj_row:
                msg = f"Target project '{self.target_project_identifier}' not found in workspace."
                raise ImportIntegrityError(msg)

            target_project_id = target_proj_row.id
            target_project_ident = target_proj_row.identifier

            for p in active_bundle_projects:
                source_key = ("project", p.id)
                sha = compute_source_sha256(p)
                project_map[p.id] = target_project_id
                project_ident_map[p.id] = p.identifier

                if source_key in mapping_cache:
                    report.unchanged += 1
                else:
                    new_mapping = ImportEntityMapping(
                        workspace_id=workspace_id,
                        source_system="plane",
                        source_kind="project",
                        source_id=p.id,
                        target_id=target_project_id,
                        source_sha256=sha,
                    )
                    self.session.add(new_mapping)
                    mapping_cache[source_key] = new_mapping
                    report.to_create += 1
        else:
            for p in active_bundle_projects:
                source_key = ("project", p.id)
                sha = compute_source_sha256(p)

                if source_key in mapping_cache:
                    m = mapping_cache[source_key]
                    project_map[p.id] = m.target_id
                    project_ident_map[p.id] = p.identifier
                    target_project_id = m.target_id
                    target_project_ident = p.identifier
                    if m.source_sha256 == sha:
                        report.unchanged += 1
                    else:
                        report.to_update += 1
                else:
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
                        clean_proj_name = (
                            normalize_plain_text(p.name)[:500] if p.name else ""
                        ) or "(untitled project)"
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
                                    "name": clean_proj_name,
                                    "creator": self.caller.principal_id,
                                },
                            )
                        ).scalar_one()

                        new_proj = Project(
                            id=p_id,
                            workspace_id=workspace_id,
                            identifier=p.identifier,
                            name=clean_proj_name,
                            description_markdown=p.description or "",
                            modules_enabled=len(bundle.modules) > 0,
                        )
                        self.session.add(new_proj)
                        await self.session.flush()

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
                    project_ident_map[p.id] = p.identifier
                    target_project_id = p_id
                    target_project_ident = p.identifier

        if not target_project_id:
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
                target_project_ident = first_proj.identifier
            else:
                msg = "No projects found in bundle or workspace."
                raise ImportIntegrityError(msg)

        # 2. Workflow States (deduplicated per target project)
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
        states_by_norm = {norm: s for s in existing_states if (norm := normalize_state_key(s.name))}
        states_by_group = {s.state_group.lower(): s for s in existing_states}

        for s in bundle.states:
            if s.project in excluded_project_ids or (
                s.project and s.project.upper() in excluded_project_idents
            ):
                continue
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
                clean_state_name = (normalize_plain_text(s.name)[:500] if s.name else "") or "State"
                s_name_lower = clean_state_name.lower()
                s_norm = normalize_state_key(clean_state_name)
                mapped_group = STATE_GROUP_MAP.get(s.group.lower(), "unstarted")

                if s_name_lower in states_by_name:
                    st_id = states_by_name[s_name_lower].id
                    report.unchanged += 1
                elif s_norm and s_norm in states_by_norm:
                    st_id = states_by_norm[s_norm].id
                    report.unchanged += 1
                elif mapped_group in states_by_group and s_norm in {
                    "backlog",
                    "todo",
                    "inprogress",
                    "done",
                    "cancelled",
                }:
                    st_id = states_by_group[mapped_group].id
                    report.unchanged += 1
                else:
                    new_state = WorkflowState(
                        workspace_id=workspace_id,
                        project_id=state_proj,
                        name=clean_state_name,
                        state_group=mapped_group,
                        color_hex=s.color or "#A3A3A3",
                        sort_order=s.sequence or 0,
                    )
                    self.session.add(new_state)
                    await self.session.flush()
                    st_id = new_state.id
                    states_by_name[s_name_lower] = new_state
                    if s_norm:
                        states_by_norm[s_norm] = new_state
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

        # 4. Project Labels (deduplicated per target project)
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
            if lbl.project in excluded_project_ids or (
                lbl.project and lbl.project.upper() in excluded_project_idents
            ):
                continue
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
                clean_label_name = (
                    normalize_plain_text(lbl.name)[:500] if lbl.name else ""
                ) or "Label"
                lbl_name_lower = clean_label_name.lower()
                if lbl_name_lower in labels_by_name:
                    target_lbl_id = labels_by_name[lbl_name_lower].id
                    report.unchanged += 1
                else:
                    new_lbl = ProjectLabel(
                        workspace_id=workspace_id,
                        project_id=lbl_proj,
                        name=clean_label_name,
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
            if c.project in excluded_project_ids or (
                c.project and c.project.upper() in excluded_project_idents
            ):
                continue
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
                clean_cycle_name = (
                    normalize_plain_text(c.name)[:500] if c.name else ""
                ) or "(untitled cycle)"
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
                        "title": clean_cycle_name,
                        "creator": self.caller.principal_id,
                        "id": cycle_id,
                    },
                )
                s_date = _parse_iso_date(c.start_date)
                e_date = _parse_iso_date(c.end_date)
                raw_status = (c.status or "upcoming").lower()
                c_status = (
                    raw_status if raw_status in ("active", "upcoming", "completed") else "upcoming"
                )

                if c_status == "active":
                    active_check = await self.session.execute(
                        text(
                            "SELECT 1 FROM cycles WHERE project_id = :proj AND status = 'active' LIMIT 1"
                        ),
                        {"proj": c_proj},
                    )
                    if active_check.scalar_one_or_none():
                        c_status = (
                            "upcoming"
                            if (s_date and s_date > datetime.datetime.now(tz=datetime.UTC).date())
                            else "completed"
                        )

                if s_date and e_date and e_date < s_date:
                    e_date = s_date

                if s_date and e_date:
                    overlap_check = await self.session.execute(
                        text(
                            "SELECT 1 FROM cycles "
                            "WHERE project_id = :proj "
                            "  AND start_date IS NOT NULL AND end_date IS NOT NULL "
                            "  AND daterange(start_date, end_date, '[]') && daterange(:s, :e, '[]') "
                            "LIMIT 1"
                        ),
                        {"proj": c_proj, "s": s_date, "e": e_date},
                    )
                    if overlap_check.scalar_one_or_none():
                        e_date = None

                new_cycle = Cycle(
                    id=cycle_id,
                    workspace_id=workspace_id,
                    project_id=c_proj,
                    name=clean_cycle_name,
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

        # 6. Modules (deduplicated per target project to avoid modules_project_id_name_key collision)
        module_map: dict[str, uuid.UUID] = {}
        if bundle.modules:
            await self.session.execute(
                text("UPDATE projects SET modules_enabled = TRUE WHERE id = :pid"),
                {"pid": target_project_id},
            )

        existing_modules_rows = (
            (
                await self.session.execute(
                    select(Module).where(Module.project_id == target_project_id)
                )
            )
            .scalars()
            .all()
        )
        modules_by_proj_and_name = {
            (m.project_id, m.name.lower()): m for m in existing_modules_rows
        }

        for mod in bundle.modules:
            if mod.project in excluded_project_ids or (
                mod.project and mod.project.upper() in excluded_project_idents
            ):
                continue
            source_key = ("module", mod.id)
            sha = compute_source_sha256(mod)
            mod_proj = project_map.get(mod.project or "", target_project_id)

            clean_mod_name = (
                normalize_plain_text(mod.name)[:500] if mod.name else ""
            ) or "(untitled module)"

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                module_map[mod.id] = m.target_id
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    report.to_update += 1
            elif (mod_proj, clean_mod_name.lower()) in modules_by_proj_and_name:
                existing_mod = modules_by_proj_and_name[(mod_proj, clean_mod_name.lower())]
                module_map[mod.id] = existing_mod.id
                report.unchanged += 1

                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="module",
                    source_id=mod.id,
                    target_id=existing_mod.id,
                    source_sha256=sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
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
                        "title": clean_mod_name,
                        "creator": self.caller.principal_id,
                        "id": mod_id,
                    },
                )
                raw_mod_status = (mod.status or "planned").lower().replace("-", "_")
                if raw_mod_status == "canceled":
                    raw_mod_status = "cancelled"
                if raw_mod_status not in (
                    "backlog",
                    "planned",
                    "in_progress",
                    "paused",
                    "completed",
                    "cancelled",
                ):
                    raw_mod_status = "planned"

                m_start_date = _parse_iso_date(mod.start_date)
                m_target_date = _parse_iso_date(mod.target_date)
                if m_start_date and m_target_date and m_target_date < m_start_date:
                    m_target_date = m_start_date

                new_mod = Module(
                    id=mod_id,
                    workspace_id=workspace_id,
                    project_id=mod_proj,
                    name=clean_mod_name,
                    description_markdown=mod.description or "",
                    status=raw_mod_status,
                    start_date=m_start_date,
                    target_date=m_target_date,
                )
                self.session.add(new_mod)
                await self.session.flush()
                modules_by_proj_and_name[(mod_proj, clean_mod_name.lower())] = new_mod

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
        md_attachments: dict[str, str] = {}

        for att_filename, raw_bytes in bundle.attachments.items():
            if att_filename == "manifest.json":
                continue
            source_key = ("attachment", att_filename)
            source_raw_sha = hashlib.sha256(
                raw_bytes
            ).digest()  # Actual 32-byte sha256 of source payload
            safe_source_id = att_filename[:128]

            is_md = att_filename.lower().endswith((".md", ".markdown"))
            if is_md:
                # Pure markdown attachment: normalize content without calling raster sniffer
                text_content = raw_bytes.decode("utf-8", errors="surrogatepass")
                clean_md = normalize_to_markdown(text_content, mode="auto")
                md_attachments[att_filename] = clean_md

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                att_id = m.target_id
                report.unchanged += 1
            elif is_md:
                att_id = uuid.uuid4()
                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="attachment",
                    source_id=safe_source_id,
                    target_id=att_id,
                    source_sha256=source_raw_sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
                report.to_create += 1
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
                    detected_type = sniff_media_type(
                        raw_bytes[:4096], "application/pdf", att_filename
                    )
                    pdf_res = await sanitize_and_validate_pdf(raw_bytes)
                    clean_bytes = pdf_res.clean_bytes
                    p_w, p_h, page_cnt = None, None, pdf_res.page_count
                else:
                    detected_type = sniff_media_type(raw_bytes[:4096], None, att_filename)
                    processed = await sanitize_and_reencode_raster(raw_bytes, detected_type)
                    clean_bytes = processed.clean_bytes
                    p_w, p_h, page_cnt = processed.pixel_width, processed.pixel_height, None

                storage_key, clean_sha = self.blob_store.store(clean_bytes)
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
                    blob_sha256=clean_sha,
                    storage_key=storage_key,
                )
                self.session.add(att)
                await self.session.flush()

                new_mapping = ImportEntityMapping(
                    workspace_id=workspace_id,
                    source_system="plane",
                    source_kind="attachment",
                    source_id=safe_source_id,
                    target_id=att_id,
                    source_sha256=source_raw_sha,
                )
                self.session.add(new_mapping)
                mapping_cache[source_key] = new_mapping
                report.to_create += 1

            if not is_md:
                attachment_url_map[att_filename] = att_id
                attachment_url_map[f"/api/assets/v1/workspace/{att_filename}"] = att_id

        # 8. Filter and Partition Issues
        active_issues = [
            iss
            for iss in bundle.issues
            if iss.project not in excluded_project_ids
            and (not iss.project or iss.project.upper() not in excluded_project_idents)
            and project_ident_map.get(iss.project or "", target_project_ident or "").upper()
            not in excluded_project_idents
        ]

        unmapped_issues = [iss for iss in active_issues if ("issue", iss.id) not in mapping_cache]

        key_remap_manifest: dict[str, str] = {}
        issue_seq_map: dict[str, int] = {}
        issue_key_map: dict[str, str] = {}

        if self.target_project_identifier and unmapped_issues:
            # Sort unmapped issues ascending by sequence_id (KANBA-1..233)
            unmapped_issues_sorted = sorted(unmapped_issues, key=lambda x: x.sequence_id)

            # Allocate fresh sequences in chunks <= 1000 via allocate_issue_sequences
            allocated_seqs: list[int] = []
            chunk_size = 1000
            for idx in range(0, len(unmapped_issues_sorted), chunk_size):
                batch = unmapped_issues_sorted[idx : idx + chunk_size]
                seq_alloc_res = await self.session.execute(
                    text(
                        "SELECT allocated_sequences, skipped_sequences "
                        "FROM allocate_issue_sequences(:proj_id, :count, true)"
                    ),
                    {"proj_id": target_project_id, "count": len(batch)},
                )
                alloc_row = seq_alloc_res.mappings().one()
                allocated_seqs.extend(alloc_row["allocated_sequences"])

            for iss, new_seq in zip(unmapped_issues_sorted, allocated_seqs, strict=False):
                src_ident = project_ident_map.get(iss.project or "", "KANBA")
                old_key = f"{src_ident}-{iss.sequence_id}"
                new_key = f"{self.target_project_identifier}-{new_seq}"
                key_remap_manifest[old_key] = new_key
                issue_seq_map[iss.id] = new_seq
                issue_key_map[iss.id] = new_key

        report.key_remap_manifest = dict(key_remap_manifest)

        # Sort all issues topologically (parents first)
        sorted_issues, depth_warnings = self.mapper.sort_issues_topologically(active_issues)
        report.warnings.extend(depth_warnings)

        if sorted_issues and not self.target_project_identifier:
            max_seq = max(i.sequence_id for i in sorted_issues)
            report.sequence_high_water_mark = max_seq

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
        elif allocated_seqs := list(issue_seq_map.values()):
            report.sequence_high_water_mark = max(allocated_seqs)

        # Cache project states and priorities
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
        states_by_proj_and_norm = {
            (s.project_id, norm): s.id for s in all_states if (norm := normalize_state_key(s.name))
        }
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

        issue_map: dict[str, uuid.UUID] = {}
        issue_canonical_key_map: dict[uuid.UUID, str] = {}
        parent_child_links: list[tuple[uuid.UUID, uuid.UUID, str, str]] = []

        # Ingest issues in topological order (parents first)
        for issue in sorted_issues:
            source_key = ("issue", issue.id)
            sha = compute_source_sha256(issue)
            issue_proj = project_map.get(issue.project or "", target_project_id)
            src_proj_ident = project_ident_map.get(issue.project or "", "KANBA")
            original_issue_key = f"{src_proj_ident}-{issue.sequence_id}"

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                issue_map[issue.id] = m.target_id
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    report.to_update += 1
            else:
                effective_seq = issue_seq_map.get(issue.id, issue.sequence_id)
                proj_ident = (
                    await self.session.execute(
                        select(Project.identifier).where(Project.id == issue_proj)
                    )
                ).scalar_one()
                canonical_key = issue_key_map.get(issue.id, f"{proj_ident}-{effective_seq}")

                # Resolve mapped creator if available
                mapped_creator_id = _resolve_principal(issue.created_by) or self.caller.principal_id

                clean_issue_name = (
                    normalize_plain_text(issue.name)[:500] if issue.name else ""
                ) or "(untitled issue)"

                iss_created_at = _parse_iso_datetime(getattr(issue, "created_at", None))
                iss_updated_at = _parse_iso_datetime(getattr(issue, "updated_at", None))
                iss_archived_at = _parse_iso_datetime(getattr(issue, "archived_at", None))

                issue_id = uuid.uuid4()
                obj_created_at = iss_created_at or datetime.datetime.now(tz=datetime.UTC)
                obj_updated_at = iss_updated_at or obj_created_at

                # Register object in spine directly preserving historical created_at and updated_at
                # without violating objects_guard_bu trigger (which strictly enforces immutability
                # on UPDATE, rejecting NEW.created_at <> OLD.created_at with OBJECT_CREATED_AT_IMMUTABLE).
                await self.session.execute(
                    text(
                        "INSERT INTO objects ("
                        "  id, object_type, workspace_id, project_id, canonical_key, display_title, "
                        "  created_by_id, created_at, updated_at, archived_at"
                        ") VALUES ("
                        "  :id, CAST('issue' AS object_kind), :ws, :proj, :key, :title, "
                        "  :creator, :created_at, :updated_at, :archived_at"
                        ")"
                    ),
                    {
                        "id": issue_id,
                        "ws": workspace_id,
                        "proj": issue_proj,
                        "key": canonical_key,
                        "title": clean_issue_name,
                        "creator": mapped_creator_id,
                        "created_at": obj_created_at,
                        "updated_at": obj_updated_at,
                        "archived_at": iss_archived_at,
                    },
                )

                # Normalize description and rewrite attachment URLs
                raw_desc = issue.description_html or issue.description_stripped or ""
                clean_desc, rewritten_cnt = self.mapper.normalize_content_and_rewrite_attachments(
                    raw_desc, attachment_url_map, md_attachments
                )
                report.rewritten_attachments += rewritten_cnt

                # Context-aware rewriting of issue key references
                if key_remap_manifest:
                    clean_desc = self.mapper.rewrite_issue_references(
                        clean_desc, key_remap_manifest
                    )

                # Provenance header when remapping key
                if original_issue_key != canonical_key:
                    provenance_line = f"> Imported from `{original_issue_key}`\n\n"
                    if provenance_line not in clean_desc:
                        clean_desc = provenance_line + clean_desc

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
                    target_state_id = (
                        states_by_proj_and_name.get((issue_proj, pst.name.lower()))
                        or states_by_proj_and_norm.get((issue_proj, normalize_state_key(pst.name)))
                        or states_by_proj_and_group.get((issue_proj, pst.group.lower()))
                    )

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

                s_date = _parse_iso_date(issue.start_date)
                t_date = _parse_iso_date(issue.target_date)

                rank = allocate_initial_board_rank(effective_seq)

                # Compute ancestry path
                ancestry = issue_id.hex
                if target_parent_id:
                    parent_ancestry_res = await self.session.execute(
                        text("SELECT ancestry_path FROM issues WHERE id = :pid"),
                        {"pid": target_parent_id},
                    )
                    parent_ancestry = parent_ancestry_res.scalar_one_or_none()
                    if parent_ancestry:
                        ancestry = f"{parent_ancestry}.{issue_id.hex}"

                new_issue = Issue(
                    id=issue_id,
                    workspace_id=workspace_id,
                    project_id=issue_proj,
                    sequence_id=effective_seq,
                    summary=clean_issue_name,
                    description_markdown=clean_desc,
                    state_id=target_state_id,
                    priority_id=target_prio_id,
                    parent_issue_id=target_parent_id,
                    cycle_id=target_cycle_id,
                    board_rank=rank,
                    created_by_id=mapped_creator_id,
                    original_created_by_id=mapped_creator_id,
                    start_date=s_date,
                    due_date=t_date,
                    ancestry_path=ancestry,
                )
                self.session.add(new_issue)
                await self.session.flush()

                # Queue PARENT_OF ObjectLink
                if target_parent_id:
                    parent_key = issue_canonical_key_map.get(target_parent_id, "PARENT")
                    parent_child_links.append(
                        (target_parent_id, issue_id, parent_key, canonical_key)
                    )

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

                # Join assignees (principal_id if mapped, free_text_assignee fallback)
                for assignee_ref in issue.assignees:
                    handle, _ = self.mapper.resolve_user_handle(assignee_ref, bundle)
                    p_id_mapped = _resolve_principal(assignee_ref)
                    self.session.add(
                        IssueAssignee(
                            issue_id=issue_id,
                            workspace_id=workspace_id,
                            principal_id=p_id_mapped,
                            free_text_assignee=handle if not p_id_mapped else None,
                        )
                    )

                # Write issue_key_aliases if remapped (rebased onto KAN-77)
                if original_issue_key != canonical_key:
                    self.session.add(
                        IssueKeyAlias(
                            workspace_id=workspace_id,
                            legacy_key=original_issue_key,
                            issue_id=issue_id,
                            source_system="plane",
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
                issue_canonical_key_map[issue_id] = canonical_key
                report.to_create += 1

        # Insert ObjectLink(LinkKind.PARENT_OF) edges
        for p_parent_id, p_child_id, p_parent_key, p_child_key in parent_child_links:
            new_parent_link = ObjectLink(
                workspace_id=workspace_id,
                source_id=p_parent_id,
                source_type=ObjectKind.ISSUE,
                target_id=p_child_id,
                target_type=ObjectKind.ISSUE,
                link_type=LinkKind.PARENT_OF,
                link_state="ACTIVE",
                source_key_snapshot=p_parent_key,
                target_key_snapshot=p_child_key,
                created_by_id=self.caller.principal_id,
            )
            self.session.add(new_parent_link)

        # 9. Comments
        comment_map: dict[str, uuid.UUID] = {}
        for comm in bundle.comments:
            source_key = ("comment", comm.id)
            sha = compute_source_sha256(comm)
            target_issue_id = issue_map.get(comm.issue_id or comm.issue or "")

            if not target_issue_id:
                continue

            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                comment_map[comm.id] = m.target_id
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    report.to_update += 1
            else:
                clean_comment, rew_cnt = self.mapper.normalize_content_and_rewrite_attachments(
                    comm.comment_html or "", attachment_url_map, md_attachments
                )
                report.rewritten_attachments += rew_cnt

                if key_remap_manifest:
                    clean_comment = self.mapper.rewrite_issue_references(
                        clean_comment, key_remap_manifest
                    )

                if not clean_comment.strip():
                    clean_comment = "(empty comment)"

                mapped_author_id = (
                    _resolve_principal(comm.actor or comm.created_by) or self.caller.principal_id
                )
                target_parent_comm = comment_map.get(comm.parent_comment or "")
                comm_created_at = _parse_iso_datetime(
                    getattr(comm, "created_at", None)
                ) or datetime.datetime.now(tz=datetime.UTC)

                new_comment = IssueComment(
                    workspace_id=workspace_id,
                    issue_id=target_issue_id,
                    author_id=mapped_author_id,
                    body_markdown=clean_comment,
                    parent_comment_id=target_parent_comm,
                    created_at=comm_created_at,
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
                comment_map[comm.id] = new_comment.id
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
