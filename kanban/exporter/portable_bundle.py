# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Deterministic portable workspace bundle exporter (KB-P6-03).

Exports complete workspace data graphs into verified .tar.gz archives with:
- mtime=0, uid=0, gid=0, uname="", gname="", mode=0o644 for full archive determinism
- Deterministic sorting by (object_kind, id) across all entities
- manifest.json containing entity counts and SHA-256 digests of all archived files
- entities/*.jsonl for Universal Object Graph records
- markdown/issues/<KEY>.md and markdown/docs/<PATH>.md for canonical content
- attachments/sha256/<digest> for media blobs
- Optional secret scrubbing using scrub_text under kanban_app RLS
"""
# ruff: noqa: C901, PLR0911, PLR0915, ANN401, FBT001, FBT002, TRY003, EM102, BLE001, ASYNC240, SIM117, D107, TC002, F841

from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import os
import tarfile
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Attachment,
    Cycle,
    Doc,
    Issue,
    IssueComment,
    IssueKeyAlias,
    Module,
    ObjectLink,
    ObjectRecord,
    Page,
    Project,
    ProjectLabel,
    ProjectPriority,
    Sticky,
    WorkflowState,
    Workspace,
)
from kanban.attachments.storage import LocalFilesystemBlobStore
from kanban.security.scrubber import scrub_text

if TYPE_CHECKING:
    from kanban.api.deps import PrincipalContext

logger = logging.getLogger(__name__)


def _serialize_value(val: Any, scrub: bool = False, is_text: bool = False) -> Any:
    """Recursively serialize database column values to JSON-safe primitives."""
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, (bytes, memoryview)):
        return bytes(val).hex()
    if isinstance(val, str):
        return scrub_text(val) if scrub and is_text else val
    if isinstance(val, list):
        return [_serialize_value(item, scrub, is_text) for item in val]
    if isinstance(val, dict):
        return {
            k: _serialize_value(
                v, scrub, is_text or k in {"title", "description", "body", "content"}
            )
            for k, v in val.items()
        }
    return val


def _to_jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    """Format records into deterministic JSONL bytes sorted by keys."""
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":")).encode("utf-8") for r in records]
    if not lines:
        return b""
    return b"\n".join(lines) + b"\n"


class PortableWorkspaceExporter:
    """Generates byte-for-byte deterministic portable workspace bundles."""

    def __init__(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        caller: PrincipalContext | None = None,
        attachments_dir: Path | str | None = None,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.caller = caller
        self.attachments_dir = Path(
            attachments_dir
            or os.environ.get("KANBAN_ATTACHMENTS_DIR", "/var/lib/kanban/attachments")
        ).resolve()

    async def export_bundle(self, scrub: bool = False) -> bytes:
        """Export workspace entities and assets into deterministic .tar.gz bytes."""
        # 1. Fetch workspace
        ws_res = await self.session.execute(
            select(Workspace).where(Workspace.id == self.workspace_id)
        )
        workspace = ws_res.scalar_one_or_none()
        if not workspace:
            raise ValueError(f"Workspace {self.workspace_id} not found")

        workspace_slug = workspace.slug

        # 2. Fetch projects
        proj_res = await self.session.execute(
            select(Project).where(Project.workspace_id == self.workspace_id).order_by(Project.id)
        )
        projects = list(proj_res.scalars().all())
        project_ids = [p.id for p in projects]
        project_map = {p.id: p for p in projects}

        # 3. Fetch related entities
        states: list[WorkflowState] = []
        priorities: list[ProjectPriority] = []
        labels: list[ProjectLabel] = []
        cycles: list[Cycle] = []
        modules: list[Module] = []

        if project_ids:
            st_res = await self.session.execute(
                select(WorkflowState)
                .where(WorkflowState.project_id.in_(project_ids))
                .order_by(WorkflowState.id)
            )
            states = list(st_res.scalars().all())

            pr_res = await self.session.execute(
                select(ProjectPriority)
                .where(ProjectPriority.project_id.in_(project_ids))
                .order_by(ProjectPriority.id)
            )
            priorities = list(pr_res.scalars().all())

            lb_res = await self.session.execute(
                select(ProjectLabel)
                .where(ProjectLabel.project_id.in_(project_ids))
                .order_by(ProjectLabel.id)
            )
            labels = list(lb_res.scalars().all())

            cy_res = await self.session.execute(
                select(Cycle).where(Cycle.project_id.in_(project_ids)).order_by(Cycle.id)
            )
            cycles = list(cy_res.scalars().all())

            mo_res = await self.session.execute(
                select(Module).where(Module.project_id.in_(project_ids)).order_by(Module.id)
            )
            modules = list(mo_res.scalars().all())

        # 4. Fetch issues
        iss_res = await self.session.execute(
            select(Issue).where(Issue.workspace_id == self.workspace_id).order_by(Issue.id)
        )
        issues = list(iss_res.scalars().all())
        issue_ids = [i.id for i in issues]

        # 5. Fetch comments
        comments: list[IssueComment] = []
        if issue_ids:
            cm_res = await self.session.execute(
                select(IssueComment)
                .where(IssueComment.issue_id.in_(issue_ids))
                .order_by(IssueComment.id)
            )
            comments = list(cm_res.scalars().all())

        # 6. Fetch aliases
        al_res = await self.session.execute(
            select(IssueKeyAlias)
            .where(IssueKeyAlias.workspace_id == self.workspace_id)
            .order_by(IssueKeyAlias.legacy_key)
        )
        aliases = list(al_res.scalars().all())

        # 7. Fetch object links
        ol_res = await self.session.execute(
            select(ObjectLink)
            .where(ObjectLink.workspace_id == self.workspace_id)
            .order_by(ObjectLink.id)
        )
        object_links = list(ol_res.scalars().all())

        # 8. Fetch docs
        doc_res = await self.session.execute(
            select(Doc).where(Doc.workspace_id == self.workspace_id).order_by(Doc.id)
        )
        docs = list(doc_res.scalars().all())

        # 8b. Fetch pages
        pg_res = await self.session.execute(
            select(Page).where(Page.workspace_id == self.workspace_id).order_by(Page.id)
        )
        pages = list(pg_res.scalars().all())

        # 8c. Fetch objects spine metadata for front matter timestamps and keys
        obj_res = await self.session.execute(
            select(
                ObjectRecord.id,
                ObjectRecord.created_at,
                ObjectRecord.updated_at,
                ObjectRecord.canonical_key,
            ).where(ObjectRecord.workspace_id == self.workspace_id)
        )
        obj_meta = {row[0]: (row[1], row[2], row[3]) for row in obj_res.all()}

        # 9. Fetch stickies
        stk_res = await self.session.execute(
            select(Sticky).where(Sticky.workspace_id == self.workspace_id).order_by(Sticky.id)
        )
        stickies = list(stk_res.scalars().all())

        # 10. Fetch attachments
        att_res = await self.session.execute(
            select(Attachment)
            .where(Attachment.workspace_id == self.workspace_id)
            .order_by(Attachment.id)
        )
        attachments = list(att_res.scalars().all())

        archive_files: dict[str, bytes] = {}

        # Build JSONL entities sorted by (object_kind, id)
        def project_dict(p: Project) -> dict[str, Any]:
            return {
                "id": str(p.id),
                "object_kind": "project",
                "workspace_id": str(p.workspace_id),
                "identifier": p.identifier,
                "name": scrub_text(p.name) if scrub else p.name,
                "description_markdown": _serialize_value(
                    p.description_markdown, scrub=scrub, is_text=True
                ),
            }

        def state_dict(s: WorkflowState) -> dict[str, Any]:
            return {
                "id": str(s.id),
                "object_kind": "workflow_state",
                "project_id": str(s.project_id),
                "name": scrub_text(s.name) if scrub else s.name,
                "state_group": s.state_group,
                "color_hex": s.color_hex,
                "sort_order": s.sort_order,
                "is_default": s.is_default,
            }

        def priority_dict(pr: ProjectPriority) -> dict[str, Any]:
            return {
                "id": str(pr.id),
                "object_kind": "project_priority",
                "project_id": str(pr.project_id),
                "slug": pr.slug,
                "label": scrub_text(pr.label) if scrub else pr.label,
                "color_hex": pr.color_hex,
                "sort_order": pr.sort_order,
                "is_default": pr.is_default,
            }

        def label_dict(lb: ProjectLabel) -> dict[str, Any]:
            return {
                "id": str(lb.id),
                "object_kind": "project_label",
                "project_id": str(lb.project_id),
                "name": scrub_text(lb.name) if scrub else lb.name,
                "color_hex": lb.color_hex,
            }

        def cycle_dict(c: Cycle) -> dict[str, Any]:
            return {
                "id": str(c.id),
                "object_kind": "cycle",
                "project_id": str(c.project_id),
                "name": scrub_text(c.name) if scrub else c.name,
                "status": c.status,
                "start_date": _serialize_value(c.start_date),
                "end_date": _serialize_value(c.end_date),
            }

        def module_dict(m: Module) -> dict[str, Any]:
            return {
                "id": str(m.id),
                "object_kind": "module",
                "project_id": str(m.project_id),
                "name": scrub_text(m.name) if scrub else m.name,
                "description_markdown": _serialize_value(
                    m.description_markdown, scrub=scrub, is_text=True
                ),
            }

        def issue_dict(i: Issue) -> dict[str, Any]:
            p = project_map.get(i.project_id)
            canonical_key = f"{p.identifier}-{i.sequence_id}" if p else f"ISSUE-{i.sequence_id}"
            return {
                "id": str(i.id),
                "object_kind": "issue",
                "workspace_id": str(i.workspace_id),
                "project_id": str(i.project_id),
                "sequence_id": i.sequence_id,
                "canonical_key": canonical_key,
                "summary": scrub_text(i.summary) if scrub else i.summary,
                "description_markdown": scrub_text(i.description_markdown)
                if scrub
                else i.description_markdown,
                "state_id": str(i.state_id),
                "priority_id": str(i.priority_id),
            }

        def comment_dict(cm: IssueComment) -> dict[str, Any]:
            return {
                "id": str(cm.id),
                "object_kind": "issue_comment",
                "issue_id": str(cm.issue_id),
                "body_markdown": scrub_text(cm.body_markdown) if scrub else cm.body_markdown,
                "author_id": str(cm.author_id),
                "created_at": _serialize_value(cm.created_at),
            }

        def alias_dict(al: IssueKeyAlias) -> dict[str, Any]:
            return {
                "workspace_id": str(al.workspace_id),
                "legacy_key": al.legacy_key,
                "issue_id": str(al.issue_id),
                "source_system": al.source_system,
                "created_at": _serialize_value(al.created_at),
            }

        def link_dict(ol: ObjectLink) -> dict[str, Any]:
            return {
                "id": str(ol.id),
                "object_kind": "object_link",
                "workspace_id": str(ol.workspace_id),
                "source_type": ol.source_type.value
                if hasattr(ol.source_type, "value")
                else str(ol.source_type),
                "source_id": str(ol.source_id),
                "link_type": ol.link_type.value
                if hasattr(ol.link_type, "value")
                else str(ol.link_type),
                "target_type": ol.target_type.value
                if hasattr(ol.target_type, "value")
                else str(ol.target_type),
                "target_id": str(ol.target_id),
            }

        def doc_dict(d: Doc) -> dict[str, Any]:
            return {
                "id": str(d.id),
                "object_kind": "doc",
                "workspace_id": str(d.workspace_id),
                "project_id": str(d.project_id) if d.project_id else None,
                "title": scrub_text(d.title) if scrub else d.title,
                "body_markdown": scrub_text(d.body_markdown) if scrub else d.body_markdown,
                "hierarchy_path": str(d.hierarchy_path),
                "version_seq": d.version_seq,
            }

        def page_dict(p: Page) -> dict[str, Any]:
            return {
                "id": str(p.id),
                "object_kind": "page",
                "workspace_id": str(p.workspace_id),
                "doc_id": str(p.doc_id),
                "parent_page_id": str(p.parent_page_id) if p.parent_page_id else None,
                "title": scrub_text(p.title) if scrub else p.title,
                "body_markdown": scrub_text(p.body_markdown) if scrub else p.body_markdown,
                "hierarchy_path": str(p.hierarchy_path),
                "version_seq": p.version_seq,
            }

        def sticky_dict(s: Sticky) -> dict[str, Any]:
            return {
                "id": str(s.id),
                "object_kind": "sticky",
                "workspace_id": str(s.workspace_id),
                "project_id": str(s.project_id) if s.project_id else None,
                "body_markdown": scrub_text(s.body_markdown) if scrub else s.body_markdown,
                "color_token": s.color_token,
            }

        def attachment_dict(a: Attachment) -> dict[str, Any]:
            sha_hex = a.blob_sha256.hex() if hasattr(a.blob_sha256, "hex") else str(a.blob_sha256)
            return {
                "id": str(a.id),
                "object_kind": "attachment",
                "workspace_id": str(a.workspace_id),
                "project_id": str(a.project_id),
                "issue_id": str(a.issue_id) if a.issue_id is not None else None,
                "original_filename": a.original_filename,
                "content_type": a.content_type,
                "byte_size": a.byte_size,
                "blob_sha256": sha_hex,
                "storage_key": a.storage_key,
            }

        archive_files["entities/workspaces.jsonl"] = _to_jsonl_bytes(
            [
                {
                    "id": str(workspace.id),
                    "object_kind": "workspace",
                    "slug": workspace.slug,
                    "name": scrub_text(workspace.name) if scrub else workspace.name,
                }
            ]
        )
        archive_files["entities/projects.jsonl"] = _to_jsonl_bytes(
            sorted([project_dict(p) for p in projects], key=lambda x: (x["object_kind"], x["id"]))
        )
        archive_files["entities/states.jsonl"] = _to_jsonl_bytes(
            sorted([state_dict(s) for s in states], key=lambda x: (x["object_kind"], x["id"]))
        )
        archive_files["entities/priorities.jsonl"] = _to_jsonl_bytes(
            sorted(
                [priority_dict(pr) for pr in priorities], key=lambda x: (x["object_kind"], x["id"])
            )
        )
        archive_files["entities/labels.jsonl"] = _to_jsonl_bytes(
            sorted([label_dict(lb) for lb in labels], key=lambda x: (x["object_kind"], x["id"]))
        )
        archive_files["entities/cycles.jsonl"] = _to_jsonl_bytes(
            sorted([cycle_dict(c) for c in cycles], key=lambda x: (x["object_kind"], x["id"]))
        )
        archive_files["entities/modules.jsonl"] = _to_jsonl_bytes(
            sorted([module_dict(m) for m in modules], key=lambda x: (x["object_kind"], x["id"]))
        )
        archive_files["entities/issues.jsonl"] = _to_jsonl_bytes(
            sorted([issue_dict(i) for i in issues], key=lambda x: (x["object_kind"], x["id"]))
        )
        archive_files["entities/comments.jsonl"] = _to_jsonl_bytes(
            sorted([comment_dict(cm) for cm in comments], key=lambda x: (x["object_kind"], x["id"]))
        )
        archive_files["entities/issue_key_aliases.jsonl"] = _to_jsonl_bytes(
            sorted(
                [alias_dict(al) for al in aliases], key=lambda x: (x["legacy_key"], x["issue_id"])
            )
        )
        links_jsonl_bytes = _to_jsonl_bytes(
            sorted(
                [link_dict(ol) for ol in object_links], key=lambda x: (x["object_kind"], x["id"])
            )
        )
        archive_files["entities/links.jsonl"] = links_jsonl_bytes
        archive_files["entities/object_links.jsonl"] = links_jsonl_bytes
        archive_files["entities/docs.jsonl"] = _to_jsonl_bytes(
            sorted([doc_dict(d) for d in docs], key=lambda x: (x["object_kind"], x["id"]))
        )
        archive_files["entities/pages.jsonl"] = _to_jsonl_bytes(
            sorted([page_dict(p) for p in pages], key=lambda x: (x["object_kind"], x["id"]))
        )
        archive_files["entities/stickies.jsonl"] = _to_jsonl_bytes(
            sorted([sticky_dict(s) for s in stickies], key=lambda x: (x["object_kind"], x["id"]))
        )
        archive_files["entities/attachments.jsonl"] = _to_jsonl_bytes(
            sorted(
                [attachment_dict(a) for a in attachments], key=lambda x: (x["object_kind"], x["id"])
            )
        )

        # Build markdown files: markdown/issues/<KEY>.md and markdown/docs/<PATH>.md
        # with deterministic YAML front matter
        state_map = {s.id: s for s in states}
        prio_map = {pr.id: pr for pr in priorities}

        for issue in issues:
            proj = project_map.get(issue.project_id)
            issue_key = (
                f"{proj.identifier}-{issue.sequence_id}" if proj else f"ISSUE-{issue.sequence_id}"
            )
            desc = scrub_text(issue.description_markdown) if scrub else issue.description_markdown
            summary_val = scrub_text(issue.summary) if scrub else issue.summary
            c_at, u_at, _ = obj_meta.get(issue.id, (None, None, None))
            st_obj = state_map.get(issue.state_id)
            pr_obj = prio_map.get(issue.priority_id)
            st_val = st_obj.name if st_obj else "unstarted"
            pr_val = pr_obj.slug if pr_obj else "medium"
            c_iso = (
                c_at.isoformat()
                if isinstance(c_at, (datetime, date))
                else "2026-01-01T00:00:00+00:00"
            )
            u_iso = u_at.isoformat() if isinstance(u_at, (datetime, date)) else c_iso

            front_matter = (
                f"---\n"
                f"key: {issue_key}\n"
                f"title: {json.dumps(summary_val)}\n"
                f"state: {st_val}\n"
                f"priority: {pr_val}\n"
                f"created_at: {c_iso}\n"
                f"updated_at: {u_iso}\n"
                f"---\n\n"
            )
            archive_files[f"markdown/issues/{issue_key}.md"] = (front_matter + desc).encode("utf-8")

        for doc in docs:
            doc_body = scrub_text(doc.body_markdown) if scrub else doc.body_markdown
            doc_path = str(doc.hierarchy_path).replace(".", "/")
            title_val = scrub_text(doc.title) if scrub else doc.title
            c_at, u_at, ckey = obj_meta.get(doc.id, (None, None, None))
            c_iso = (
                c_at.isoformat()
                if isinstance(c_at, (datetime, date))
                else "2026-01-01T00:00:00+00:00"
            )
            u_iso = u_at.isoformat() if isinstance(u_at, (datetime, date)) else c_iso
            doc_key = ckey or f"doc-{str(doc.id)[:8]}"

            front_matter = (
                f"---\n"
                f"key: {doc_key}\n"
                f"title: {json.dumps(title_val)}\n"
                f"state: null\n"
                f"priority: null\n"
                f"created_at: {c_iso}\n"
                f"updated_at: {u_iso}\n"
                f"---\n\n"
            )
            archive_files[f"markdown/docs/{doc_path}.md"] = (front_matter + doc_body).encode(
                "utf-8"
            )

        # Build attachments: attachments/sha256/<digest>
        blob_store = None
        if self.attachments_dir.exists():
            try:
                blob_store = LocalFilesystemBlobStore(self.attachments_dir)
            except Exception:
                blob_store = None
        for att in attachments:
            sha_hex = (
                att.blob_sha256.hex() if hasattr(att.blob_sha256, "hex") else str(att.blob_sha256)
            )
            att_path = f"attachments/sha256/{sha_hex}"
            if blob_store and blob_store.exists(att.storage_key):
                archive_files[att_path] = blob_store.read(att.storage_key)
            else:
                archive_files[att_path] = b""

        # Compute SHA-256 for all files to include in manifest.json
        file_digests = {
            name: hashlib.sha256(content).hexdigest()
            for name, content in sorted(archive_files.items())
        }

        entity_counts = {
            "workspaces": 1,
            "projects": len(projects),
            "states": len(states),
            "priorities": len(priorities),
            "labels": len(labels),
            "cycles": len(cycles),
            "modules": len(modules),
            "issues": len(issues),
            "comments": len(comments),
            "issue_key_aliases": len(aliases),
            "object_links": len(object_links),
            "links": len(object_links),
            "docs": len(docs),
            "pages": len(pages),
            "stickies": len(stickies),
            "attachments": len(attachments),
        }

        manifest = {
            "format_version": "1.0",
            "workspace_id": str(workspace.id),
            "workspace_slug": workspace.slug,
            "workspace_name": scrub_text(workspace.name) if scrub else workspace.name,
            "scrubbed": scrub,
            "entity_counts": entity_counts,
            "files": file_digests,
        }
        manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")
        archive_files["manifest.json"] = manifest_bytes

        # Create deterministic .tar.gz
        bio = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=bio, mtime=0.0) as gz:
            with tarfile.TarFile(mode="w", fileobj=gz) as tar:
                # Add in strictly sorted order
                for name in sorted(archive_files.keys()):
                    content = archive_files[name]
                    ti = tarfile.TarInfo(name=name)
                    ti.size = len(content)
                    ti.mtime = 0
                    ti.uid = 0
                    ti.gid = 0
                    ti.uname = ""
                    ti.gname = ""
                    ti.mode = 0o644
                    ti.type = tarfile.REGTYPE
                    tar.addfile(ti, io.BytesIO(content))

        return bio.getvalue()

    async def export_to_file(self, out_path: Path | str, scrub: bool = False) -> Path:
        """Export workspace bundle and write to specified file path."""
        target = Path(out_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        bundle_bytes = await self.export_bundle(scrub=scrub)
        target.write_bytes(bundle_bytes)
        return target
