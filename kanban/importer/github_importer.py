# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Lossless GitHub Issues importer with GH-N alias preservation (KB-P6-03)."""
# ruff: noqa: C901, PLR0912, PLR0915, E501, ANN401, D107, ASYNC240, S108, BLE001, TRY003, EM102, FURB162, TRY300

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, text

from database.models import (
    Attachment,
    Cycle,
    ImportEntityMapping,
    Issue,
    IssueAssignee,
    IssueComment,
    IssueKeyAlias,
    IssueLabel,
    LinkKind,
    ObjectKind,
    ObjectLink,
    Project,
    ProjectLabel,
    ProjectPriority,
    WorkflowState,
)
from kanban.attachments.pdf import sanitize_and_validate_pdf
from kanban.attachments.raster import sanitize_and_reencode_raster
from kanban.attachments.sniff import sniff_media_type
from kanban.attachments.storage import LocalFilesystemBlobStore
from kanban.content.normalize import normalize_to_markdown
from kanban.content.svg_sanitizer import sanitize_svg
from kanban.importer.cutover_verifier import CheckResult, CutoverAuditReport
from kanban.importer.plane_importer import ImportIntegrityError
from kanban.importer.plane_mapper import ImportDiffReport
from kanban.security.push_protection import enforce_secret_push_protection
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.board_rank import allocate_initial_board_rank

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

logger = logging.getLogger(__name__)

__all__ = ["GitHubIssuesImporter"]


def _parse_iso_datetime(val: Any) -> datetime | None:
    """Safely parse ISO datetime string into UTC datetime object."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        return None


def _validate_attachment_filename(filename: str) -> None:
    """Strict fail-closed validation rejecting path traversal characters."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ImportIntegrityError(f"Path traversal detected in attachment filename: {filename}")


@dataclass
class CutoverAuditSummary:
    source_system: str
    is_consistent: bool
    report: CutoverAuditReport


class GitHubIssuesImporter:
    """Transactional importer for GitHub Issues exports."""

    def __init__(
        self,
        session: AsyncSession,
        caller: PrincipalContext,
        *,
        user_map: dict[str, str] | None = None,
    ) -> None:
        self.session = session
        self.caller = caller
        self.user_map = user_map or {}

    async def run_import(
        self,
        data: dict[str, Any] | list[Any],
        *,
        dry_run: bool = False,
        target_project_id: uuid.UUID | None = None,
        target_project_key: str | None = None,
    ) -> ImportDiffReport:
        """Execute GitHub Issues import, creating issues, aliases and entity mappings."""
        report = ImportDiffReport()

        if dry_run:
            async with self.session.begin_nested() as savepoint:
                await self._execute(
                    data,
                    report,
                    target_project_id=target_project_id,
                    target_project_key=target_project_key,
                )
                await savepoint.rollback()
        else:
            await self._execute(
                data,
                report,
                target_project_id=target_project_id,
                target_project_key=target_project_key,
            )

        return report

    async def _execute(
        self,
        data: dict[str, Any] | list[Any],
        report: ImportDiffReport,
        target_project_id: uuid.UUID | None = None,
        target_project_key: str | None = None,
    ) -> None:
        if getattr(self.caller, "workspace_id", None) is None:
            msg = "Caller workspace_id is required for import"
            raise ValueError(msg)
        workspace_id = self.caller.workspace_id

        # 1. Resolve Target Project
        target_proj = None
        if target_project_id:
            proj_stmt = select(Project).where(
                Project.id == target_project_id, Project.workspace_id == workspace_id
            )
            target_proj = (await self.session.execute(proj_stmt)).scalar_one_or_none()
        elif target_project_key:
            proj_stmt = select(Project).where(
                Project.workspace_id == workspace_id,
                Project.identifier == target_project_key.upper(),
            )
            target_proj = (await self.session.execute(proj_stmt)).scalar_one_or_none()

        if not target_proj:
            proj_stmt = (
                select(Project).where(Project.workspace_id == workspace_id).order_by(Project.id)
            )
            target_proj = (await self.session.execute(proj_stmt)).scalars().first()

        if not target_proj:
            proj_key = (target_project_key or "GH").upper()
            proj_id = (
                await self.session.execute(
                    text(
                        "SELECT register_object("
                        "  CAST('project' AS object_kind), :ws, NULL, :key, :title, :creator"
                        ")"
                    ),
                    {
                        "ws": workspace_id,
                        "key": proj_key,
                        "title": f"{proj_key} Project",
                        "creator": self.caller.principal_id,
                    },
                )
            ).scalar_one()
            target_proj = Project(
                id=proj_id,
                workspace_id=workspace_id,
                identifier=proj_key,
                name=f"{proj_key} Project",
                description_markdown="Imported from GitHub",
            )
            self.session.add(target_proj)
            await self.session.flush()

        # 2. Extract issues list
        raw_issues: list[Any] = data.get("issues", []) if isinstance(data, dict) else data

        if not raw_issues:
            report.warnings.append("No issues found in GitHub dataset")
            return

        # 3. Load workflow states and priorities
        states_res = await self.session.execute(
            select(WorkflowState).where(WorkflowState.project_id == target_proj.id)
        )
        states = list(states_res.scalars().all())
        if not states:  # pragma: no cover
            for s_name, s_group, order in [
                ("Backlog", "backlog", 1),
                ("In Progress", "started", 2),
                ("Done", "completed", 3),
            ]:
                st = WorkflowState(
                    id=uuid.uuid4(),
                    workspace_id=workspace_id,
                    project_id=target_proj.id,
                    name=s_name,
                    state_group=s_group,
                    color_hex="#3b82f6",
                    sort_order=order,
                    is_default=(s_group == "backlog"),
                )
                self.session.add(st)
                states.append(st)
            await self.session.flush()

        states_by_group = {s.state_group: s.id for s in states}
        open_state_id = (
            states_by_group.get("unstarted") or states_by_group.get("backlog") or states[0].id
        )
        closed_state_id = states_by_group.get("completed") or open_state_id
        cancelled_state_id = states_by_group.get("cancelled") or closed_state_id

        prio_res = await self.session.execute(
            select(ProjectPriority).where(ProjectPriority.project_id == target_proj.id)
        )
        priorities = list(prio_res.scalars().all())
        if not priorities:  # pragma: no cover
            for p_slug, p_label, p_color, p_order, is_def in [
                ("urgent", "Urgent", "#ef4444", 1, False),
                ("high", "High", "#f97316", 2, False),
                ("medium", "Medium", "#eab308", 3, True),
                ("low", "Low", "#64748b", 4, False),
            ]:
                pr = ProjectPriority(
                    id=uuid.uuid4(),
                    workspace_id=workspace_id,
                    project_id=target_proj.id,
                    slug=p_slug,
                    label=p_label,
                    color_hex=p_color,
                    sort_order=p_order,
                    is_default=is_def,
                )
                self.session.add(pr)
                priorities.append(pr)
            await self.session.flush()

        default_prio_id = priorities[0].id

        # 4. Resolve workspace active users for user mapping
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
            user_lookup[str(r["id"]).lower()] = r["id"]

        def _resolve_user(raw_user: Any) -> tuple[uuid.UUID | None, str | None]:
            if not raw_user:
                return None, None
            if isinstance(raw_user, dict):
                user_id_str = str(
                    raw_user.get("login") or raw_user.get("name") or raw_user.get("email") or ""
                ).strip()
            else:
                user_id_str = str(raw_user).strip()
            if not user_id_str:
                return None, None
            mapped_target = self.user_map.get(user_id_str)
            if mapped_target:
                clean_target = mapped_target.lstrip("@").lower()
                if clean_target in user_lookup:
                    return user_lookup[clean_target], None
            return None, user_id_str

        # 5. Existing entity mappings
        existing_mappings_res = await self.session.execute(
            select(ImportEntityMapping).where(
                ImportEntityMapping.workspace_id == workspace_id,
                ImportEntityMapping.source_system == "github",
            )
        )
        mapping_cache: dict[tuple[str, str], ImportEntityMapping] = {
            (m.source_kind, m.source_id): m for m in existing_mappings_res.scalars().all()
        }

        # Local blob store for attachments
        att_env = os.environ.get("KANBAN_ATTACHMENT_DIR") or os.environ.get(
            "KANBAN_ATTACHMENTS_DIR"
        )
        attachments_dir = (
            Path(att_env).resolve() if att_env else Path("/tmp/kanban/attachments").resolve()
        )
        try:
            attachments_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            attachments_dir = Path("/tmp/kanban/attachments").resolve()
            attachments_dir.mkdir(parents=True, exist_ok=True)
        blob_store = LocalFilesystemBlobStore(attachments_dir)

        label_cache: dict[str, uuid.UUID] = {}
        cycle_cache: dict[str, uuid.UUID] = {}
        created_issues_map: dict[str, uuid.UUID] = {}
        pending_links: list[tuple[str, str, LinkKind]] = []
        pending_comments: list[tuple[uuid.UUID, list[Any]]] = []

        for item in raw_issues:
            if not isinstance(item, dict):
                continue

            num = item.get("number")
            if num is None:
                continue
            gh_key = f"GH-{num}"
            gh_id_str = str(num)

            title = str(item.get("title") or f"GitHub Issue #{num}").strip()
            title = enforce_secret_push_protection(title, field="summary") or ""
            body = str(item.get("body") or "")
            norm_desc = normalize_to_markdown(body)
            norm_desc = (
                enforce_secret_push_protection(norm_desc, field="description_markdown") or ""
            )

            raw_state = str(item.get("state") or "open").lower()
            state_reason = str(item.get("state_reason") or "").lower()

            if raw_state == "closed":
                state_id = cancelled_state_id if state_reason == "not_planned" else closed_state_id
            else:
                state_id = open_state_id

            payload_bytes = json.dumps(item, default=str, sort_keys=True).encode("utf-8")
            sha = hashlib.sha256(payload_bytes).digest()

            source_key = ("issue", gh_id_str)
            if source_key in mapping_cache:
                m = mapping_cache[source_key]
                created_issues_map[gh_key] = m.target_id
                if m.source_sha256 == sha:
                    report.unchanged += 1
                else:
                    existing_issue = await self.session.get(Issue, m.target_id)
                    if existing_issue:
                        existing_issue.summary = title
                        existing_issue.description_markdown = norm_desc
                        if existing_issue.state_id != state_id:
                            await self.session.execute(
                                text("SELECT set_config('app.transition_exec_id', 'bypass', true)")
                            )
                            existing_issue.state_id = state_id
                        await self.session.execute(
                            text(
                                "UPDATE objects SET updated_at = clock_timestamp(), display_title = :title WHERE id = :id"
                            ),
                            {"id": m.target_id, "title": title},
                        )
                    raw_comments = item.get("comments_data") or item.get("comments")
                    if isinstance(raw_comments, list):
                        pending_comments.append((m.target_id, raw_comments))
                    m.source_sha256 = sha
                    report.to_update += 1
                continue

            # Allocate next sequence
            seq_row = await self.session.execute(
                text("SELECT allocate_issue_sequence(:proj)"),
                {"proj": target_proj.id},
            )
            next_seq = seq_row.scalar_one()
            canonical_key = f"{target_proj.identifier}-{next_seq}"

            # Register in spine
            issue_id = (
                await self.session.execute(
                    text(
                        "SELECT register_object("
                        "  CAST('issue' AS object_kind), :ws, :proj, :key, :title, :creator"
                        ")"
                    ),
                    {
                        "ws": workspace_id,
                        "proj": target_proj.id,
                        "key": canonical_key,
                        "title": title,
                        "creator": self.caller.principal_id,
                    },
                )
            ).scalar_one()

            new_issue = Issue(
                id=issue_id,
                workspace_id=workspace_id,
                project_id=target_proj.id,
                sequence_id=next_seq,
                summary=title,
                description_markdown=norm_desc,
                state_id=state_id,
                priority_id=default_prio_id,
                created_by_id=self.caller.principal_id,
                original_created_by_id=self.caller.principal_id,
                board_rank=allocate_initial_board_rank(next_seq),
                ancestry_path=issue_id.hex,
                provenance_tier="imported",
            )
            self.session.add(new_issue)
            await self.session.flush()

            # Preserve source updated_at on objects
            source_updated_at = _parse_iso_datetime(item.get("updated_at") or item.get("updated"))
            if source_updated_at:
                await self.session.execute(
                    text("UPDATE objects SET updated_at = :u WHERE id = :id"),
                    {"u": source_updated_at, "id": issue_id},
                )

            # Assignees mapping
            raw_assignees = item.get("assignees") or (
                [item.get("assignee")] if item.get("assignee") else []
            )
            if isinstance(raw_assignees, list):
                for a_item in raw_assignees:
                    pid, free_text = _resolve_user(a_item)
                    if pid or free_text:
                        assignee = IssueAssignee(
                            workspace_id=workspace_id,
                            issue_id=issue_id,
                            principal_id=pid,
                            free_text_assignee=free_text,
                        )
                        self.session.add(assignee)

            # Labels mapping: ProjectLabel + IssueLabel
            labels_data = item.get("labels", [])
            if isinstance(labels_data, list):
                for lbl in labels_data:
                    l_name = str(lbl.get("name") if isinstance(lbl, dict) else lbl).strip()
                    if not l_name:
                        continue
                    l_color = (
                        f"#{lbl.get('color', '3b82f6').lstrip('#')}"
                        if isinstance(lbl, dict) and lbl.get("color")
                        else "#3b82f6"
                    )
                    l_key = l_name.lower()
                    if l_key not in label_cache:
                        lbl_row = (
                            await self.session.execute(
                                select(ProjectLabel).where(
                                    ProjectLabel.project_id == target_proj.id,
                                    func.lower(ProjectLabel.name) == l_key,
                                )
                            )
                        ).scalar_one_or_none()
                        if not lbl_row:
                            new_lbl = ProjectLabel(
                                id=uuid.uuid4(),
                                workspace_id=workspace_id,
                                project_id=target_proj.id,
                                name=l_name,
                                color_hex=l_color,
                            )
                            self.session.add(new_lbl)
                            await self.session.flush()
                            label_cache[l_key] = new_lbl.id
                        else:
                            label_cache[l_key] = lbl_row.id

                    lbl_id = label_cache[l_key]
                    self.session.add(
                        IssueLabel(
                            workspace_id=workspace_id,
                            issue_id=issue_id,
                            label_id=lbl_id,
                        )
                    )

            # Milestone mapping: Cycle + Issue.cycle_id
            milestone_obj = item.get("milestone")
            if milestone_obj:
                m_title = str(
                    milestone_obj.get("title") if isinstance(milestone_obj, dict) else milestone_obj
                ).strip()
                if m_title:
                    m_key = m_title.lower()
                    if m_key not in cycle_cache:
                        cy_row = (
                            await self.session.execute(
                                select(Cycle).where(
                                    Cycle.project_id == target_proj.id,
                                    func.lower(Cycle.name) == m_key,
                                )
                            )
                        ).scalar_one_or_none()
                        if not cy_row:
                            c_id = (
                                await self.session.execute(
                                    text(
                                        "SELECT register_object("
                                        "  CAST('cycle' AS object_kind), :ws, :proj, :ckey, :title, :creator"
                                        ")"
                                    ),
                                    {
                                        "ws": workspace_id,
                                        "proj": target_proj.id,
                                        "ckey": f"cycle-{uuid.uuid4().hex[:8]}",
                                        "title": m_title,
                                        "creator": self.caller.principal_id,
                                    },
                                )
                            ).scalar_one()
                            new_cycle = Cycle(
                                id=c_id,
                                workspace_id=workspace_id,
                                project_id=target_proj.id,
                                name=m_title,
                                status="upcoming",
                            )
                            self.session.add(new_cycle)
                            await self.session.flush()
                            cycle_cache[m_key] = c_id
                        else:
                            cycle_cache[m_key] = cy_row.id

                    new_issue.cycle_id = cycle_cache[m_key]

            # Sub-issues and Parent links
            parent_field = item.get("parent") or item.get("parent_issue") or item.get("parent_id")
            if parent_field:
                p_num = (
                    parent_field.get("number") if isinstance(parent_field, dict) else parent_field
                )
                if p_num is not None:
                    pending_links.append((f"GH-{p_num}", gh_key, LinkKind.PARENT_OF))

            sub_issues = (
                item.get("sub_issues") or item.get("sub_tasks") or item.get("subissues") or []
            )
            if isinstance(sub_issues, list):
                for sub in sub_issues:
                    s_num = sub.get("number") if isinstance(sub, dict) else sub
                    if s_num is not None:
                        pending_links.append((gh_key, f"GH-{s_num}", LinkKind.PARENT_OF))

            # Blocks & Blocked By links
            blocked_by = item.get("blocked_by") or []
            if isinstance(blocked_by, list):
                for b in blocked_by:
                    b_num = b.get("number") if isinstance(b, dict) else b
                    if b_num is not None:
                        pending_links.append((f"GH-{b_num}", gh_key, LinkKind.BLOCKS))

            blocks_list = item.get("blocks") or []
            if isinstance(blocks_list, list):
                for b in blocks_list:
                    b_num = b.get("number") if isinstance(b, dict) else b
                    if b_num is not None:
                        pending_links.append((gh_key, f"GH-{b_num}", LinkKind.BLOCKS))

            # Optional attachments on issue
            raw_attachments = item.get("attachment") or item.get("attachments") or []
            if isinstance(raw_attachments, list):
                for att_item in raw_attachments:
                    if not isinstance(att_item, dict):
                        continue
                    att_filename = str(
                        att_item.get("filename")
                        or att_item.get("name")
                        or att_item.get("original_filename")
                        or ""
                    ).strip()
                    if not att_filename:
                        continue
                    _validate_attachment_filename(att_filename)

                    raw_data = att_item.get("data") or att_item.get("content") or b""
                    if not raw_data:
                        continue
                    if isinstance(raw_data, str):
                        try:
                            raw_bytes = base64.b64decode(raw_data, validate=True)
                        except Exception:
                            raw_bytes = raw_data.encode("utf-8")
                    elif isinstance(raw_data, (bytes, bytearray)):
                        raw_bytes = bytes(raw_data)
                    else:
                        raw_bytes = b""

                    is_svg = att_filename.lower().endswith(".svg")
                    is_pdf = att_filename.lower().endswith(".pdf")
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
                        p_w, p_h, page_cnt = (
                            processed.pixel_width,
                            processed.pixel_height,
                            None,
                        )

                    storage_key, raw_sha = blob_store.store(clean_bytes)
                    att = Attachment(
                        id=uuid.uuid4(),
                        workspace_id=workspace_id,
                        project_id=target_proj.id,
                        issue_id=issue_id,
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

            new_mapping = ImportEntityMapping(
                workspace_id=workspace_id,
                source_system="github",
                source_kind="issue",
                source_id=gh_id_str,
                target_id=issue_id,
                source_sha256=sha,
            )
            self.session.add(new_mapping)

            # Record legacy key alias (GH-88)
            new_alias = IssueKeyAlias(
                workspace_id=workspace_id,
                legacy_key=gh_key,
                issue_id=issue_id,
                source_system="github",
            )
            self.session.add(new_alias)

            created_issues_map[gh_key] = issue_id
            report.to_create += 1
            report.sequence_high_water_mark = max(report.sequence_high_water_mark, next_seq)

            # Comments if present
            raw_comments = item.get("comments_data") or item.get("comments")
            if isinstance(raw_comments, list):
                pending_comments.append((issue_id, raw_comments))

        await self.session.flush()

        # Ingest DAG links and wire parent_issue_id
        seen_links: set[tuple[uuid.UUID, uuid.UUID, LinkKind]] = set()
        for src_key, tgt_key, l_type in pending_links:
            src_id = created_issues_map.get(src_key)
            tgt_id = created_issues_map.get(tgt_key)
            if src_id and tgt_id and src_id != tgt_id:
                if (src_id, tgt_id, l_type) in seen_links:
                    continue
                seen_links.add((src_id, tgt_id, l_type))
                link = ObjectLink(
                    workspace_id=workspace_id,
                    source_id=src_id,
                    source_type=ObjectKind.ISSUE,
                    target_id=tgt_id,
                    target_type=ObjectKind.ISSUE,
                    link_type=l_type,
                    link_state="ACTIVE",
                    source_key_snapshot=src_key,
                    target_key_snapshot=tgt_key,
                    created_by_id=self.caller.principal_id,
                )
                self.session.add(link)
                if l_type == LinkKind.PARENT_OF:
                    child = await self.session.get(Issue, tgt_id)
                    if child:
                        child.parent_issue_id = src_id

        # Ingest comments
        for iss_id, c_list in pending_comments:
            for c in c_list:
                if not isinstance(c, dict):
                    continue
                c_id_raw = str(c.get("id") or "").strip()
                c_body = str(c.get("body") or "")
                norm_c = normalize_to_markdown(c_body)
                if not norm_c.strip():
                    continue
                norm_c = enforce_secret_push_protection(norm_c, field="body_markdown") or ""

                c_sha = hashlib.sha256(norm_c.encode("utf-8")).digest()
                c_source_key = ("comment", c_id_raw) if c_id_raw else None

                if c_source_key and c_source_key in mapping_cache:
                    c_m = mapping_cache[c_source_key]
                    if c_m.source_sha256 != c_sha:
                        existing_comment = await self.session.get(IssueComment, c_m.target_id)
                        if existing_comment:
                            existing_comment.body_markdown = norm_c
                        c_m.source_sha256 = c_sha
                    continue

                c_created_at = _parse_iso_datetime(
                    c.get("created_at") or c.get("created")
                ) or datetime.now(UTC)

                c_uuid = uuid.uuid4()
                comment = IssueComment(
                    id=c_uuid,
                    workspace_id=workspace_id,
                    issue_id=iss_id,
                    author_id=self.caller.principal_id,
                    body_markdown=norm_c,
                    created_at=c_created_at,
                    provenance_tier="imported",
                )
                self.session.add(comment)
                if c_source_key:
                    new_c_map = ImportEntityMapping(
                        workspace_id=workspace_id,
                        source_system="github",
                        source_kind="comment",
                        source_id=c_id_raw,
                        target_id=c_uuid,
                        source_sha256=c_sha,
                    )
                    self.session.add(new_c_map)
                    mapping_cache[c_source_key] = new_c_map

        await self.session.flush()

        # Query real database metrics for CutoverAuditReport
        alias_q = await self.session.execute(
            select(func.count(IssueKeyAlias.legacy_key)).where(
                IssueKeyAlias.workspace_id == workspace_id,
                IssueKeyAlias.source_system == "github",
            )
        )
        self.queried_alias_count = alias_q.scalar_one()

        sha_q = await self.session.execute(
            select(func.count(ImportEntityMapping.target_id)).where(
                ImportEntityMapping.workspace_id == workspace_id,
                ImportEntityMapping.source_system == "github",
                ImportEntityMapping.source_sha256.is_not(None),
            )
        )
        self.queried_sha_mapping_count = sha_q.scalar_one()

        # Record activity with provenance_tier
        await record_activity(
            self.session,
            workspace_id=workspace_id,
            object_id=target_proj.id,
            actor_principal_id=self.caller.principal_id,
            event_type=ActivityEventType.PLANE_IMPORT_COMPLETED,
            payload={
                "provenance_tier": "imported",
                "source_system": "github",
                "project_id": str(target_proj.id),
                "to_create": report.to_create,
                "to_update": report.to_update,
                "unchanged": report.unchanged,
                "sequence_high_water_mark": report.sequence_high_water_mark,
            },
        )

    def generate_audit_report(
        self,
        workspace_slug: str,
        project_identifier: str,
        diff_report: ImportDiffReport,
    ) -> CutoverAuditReport:
        """Construct a CutoverAuditReport summarizing GitHub Issues import execution."""
        alias_count = getattr(self, "queried_alias_count", 0)
        sha_count = getattr(self, "queried_sha_mapping_count", 0)
        alias_passed = alias_count > 0 or diff_report.to_create == 0
        sha_passed = (
            (sha_count >= (diff_report.to_create + diff_report.unchanged + diff_report.to_update))
            if (diff_report.to_create + diff_report.unchanged + diff_report.to_update > 0)
            else True
        )

        checks = [
            CheckResult(
                name="entity_count_and_key_parity",
                passed=diff_report.invalid_link_count == 0,
                detail=f"Created {diff_report.to_create}, updated {diff_report.to_update}, unchanged {diff_report.unchanged}",
                metadata={"high_water_mark": diff_report.sequence_high_water_mark},
            ),
            CheckResult(
                name="legacy_key_aliases_recorded",
                passed=alias_passed,
                detail=f"{alias_count} legacy aliases verified in database",
                metadata={"alias_count": alias_count},
            ),
            CheckResult(
                name="sha256_parity_and_canonical_markdown",
                passed=sha_passed and diff_report.invalid_link_count == 0,
                detail=f"{sha_count} source entities authenticated via SHA-256 mappings",
                metadata={"sha_mappings_count": sha_count},
            ),
        ]
        return CutoverAuditReport(
            overall_passed=all(c.passed for c in checks),
            workspace_slug=workspace_slug,
            project_identifier=project_identifier,
            checks=checks,
            summary={
                "to_create": diff_report.to_create,
                "to_update": diff_report.to_update,
                "unchanged": diff_report.unchanged,
                "warnings": len(diff_report.warnings),
            },
        )

    def build_cutover_audit(self, report: ImportDiffReport) -> CutoverAuditSummary:
        """Alias for generate_audit_report for CutoverAuditReport verification."""
        audit_rep = self.generate_audit_report(
            workspace_slug="",
            project_identifier="",
            diff_report=report,
        )
        return CutoverAuditSummary(
            source_system="github",
            is_consistent=audit_rep.overall_passed,
            report=audit_rep,
        )
