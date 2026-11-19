"""Issue deletion, blast radius calculation, trash, and restore service (S7.2 8q, S12.3)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from database.models import (
    Issue,
    ObjectKind,
    ObjectRecord,
    Project,
    ProjectPriority,
    WorkflowState,
)
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.issue_delete import (
    IssueDeleteResponse,
    TrashedIssueItem,
    TrashedIssueList,
    TrashedObjectItem,
    TrashedObjectList,
)
from kanban.api.v1.schemas.issues import IssueResponse, PrioritySummary, StateSummary
from kanban.security.permissions import (
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
    require_capability,
)
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.issues import decode_issue_cursor, encode_issue_cursor, serialize_issue
from kanban.services.projects import get_project_or_404
from kanban.settings import get_settings

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

__all__ = [
    "BlastRadius",
    "compute_blast_radius",
    "list_trash",
    "list_trash_items",
    "restore_issue",
    "trash_issue",
]


@dataclass(frozen=True, slots=True)
class BlastRadius:
    """Computed blast radius for an issue delete preview."""

    issue_id: uuid.UUID
    issue_key: str
    sub_issues_unparented: int
    inbound_links_flagged: int
    outbound_links: int
    comments: int
    attachments: int
    summary_text: str
    blast_hash: str
    retention_days: int
    child_ids: tuple[uuid.UUID, ...]
    inbound_link_ids: tuple[uuid.UUID, ...]
    outbound_link_ids: tuple[uuid.UUID, ...]


async def compute_blast_radius(
    session: AsyncSession,
    issue_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> BlastRadius:
    """Compute the blast radius preview and deterministic SHA-256 blast hash.

    Counts:
        - sub_issues_unparented: direct children (parent_issue_id = issue_id)
        - inbound_links_flagged: ACTIVE object_links with target_id = issue_id
        - outbound_links: ACTIVE object_links with source_id = issue_id
        - comments: issue_comments count
        - attachments: attachments count
    """
    if for_update:
        issue_stmt = (
            select(Issue, Project.identifier)
            .join(Project, Project.id == Issue.project_id)
            .where(Issue.id == issue_id)
            .with_for_update(of=Issue)
        )
    else:
        issue_stmt = (
            select(Issue, Project.identifier)
            .join(Project, Project.id == Issue.project_id)
            .where(Issue.id == issue_id)
        )
    row = (await session.execute(issue_stmt)).first()
    if row is None:
        not_found()
    issue, proj_ident = row
    issue_key = f"{proj_ident}-{issue.sequence_id}"

    obj = await session.get(ObjectRecord, issue_id)
    if obj is None or obj.deleted_at is not None:
        not_found()

    desc_sha = issue.description_sha256.hex().lower() if issue.description_sha256 else ""

    # Fetch blast radius components via SECURITY DEFINER helper to ensure all
    # direct children, links, comments and attachments across the workspace
    # are counted even if hidden from caller by RLS
    priv_res = (
        await session.execute(
            text(
                "SELECT child_ids, inbound_link_ids, outbound_link_ids, "
                "comment_count, attachment_count "
                "FROM get_issue_blast_radius_privileged(:issue_id)"
            ),
            {"issue_id": issue_id},
        )
    ).first()

    if priv_res is not None:
        child_ids = tuple(priv_res[0])
        inbound_link_ids = tuple(priv_res[1])
        outbound_link_ids = tuple(priv_res[2])
        comment_count = int(priv_res[3])
        attachment_count = int(priv_res[4])
    else:
        not_found()

    retention_days = get_settings().trash_retention_days

    # Canonical JSON for blast hash:
    # {issue_id, description_sha256, sorted child ids, sorted inbound link ids,
    #  sorted outbound link ids, comment count, attachment count}
    canonical_dict = {
        "attachment_count": attachment_count,
        "child_ids": sorted([str(cid) for cid in child_ids]),
        "comment_count": comment_count,
        "description_sha256": desc_sha,
        "inbound_link_ids": sorted([str(lid) for lid in inbound_link_ids]),
        "issue_id": str(issue_id),
        "outbound_link_ids": sorted([str(lid) for lid in outbound_link_ids]),
    }
    canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
    blast_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest().lower()

    sub_issues_unparented = len(child_ids)
    inbound_links_flagged = len(inbound_link_ids)
    outbound_links = len(outbound_link_ids)

    sub_plural = "s" if sub_issues_unparented != 1 else ""
    in_plural = "s" if inbound_links_flagged != 1 else ""
    sub_part = f"{sub_issues_unparented} sub-issue{sub_plural} unparented"
    in_part = f"{inbound_links_flagged} inbound object_link{in_plural} flagged"
    summary_text = f"{sub_part}, {in_part}"

    return BlastRadius(
        issue_id=issue_id,
        issue_key=issue_key,
        sub_issues_unparented=sub_issues_unparented,
        inbound_links_flagged=inbound_links_flagged,
        outbound_links=outbound_links,
        comments=comment_count,
        attachments=attachment_count,
        summary_text=summary_text,
        blast_hash=blast_hash,
        retention_days=retention_days,
        child_ids=child_ids,
        inbound_link_ids=inbound_link_ids,
        outbound_link_ids=outbound_link_ids,
    )


async def trash_issue(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    blast_hash_header: str | None,
) -> IssueDeleteResponse:
    """Soft-delete an issue into trash after validating blast radius concurrency."""
    if not blast_hash_header or not blast_hash_header.strip():
        preview_url = f"/api/v1/issues/{issue_ref}/delete-preview"
        hint = (
            f"Obtain blast_hash by calling GET {preview_url} "
            f"and provide it via 'Kb-Blast-Hash' header (confirm_blast_hash) to confirm deletion."
        )
        raise ProblemException(
            code="BLAST_HASH_REQUIRED",
            status=428,
            title="Blast Hash Required",
            detail=f"Header 'Kb-Blast-Hash' is required to delete an issue. {hint}",
            extra={
                "preview_url": preview_url,
                "hint": hint,
                "confirm_blast_hash": "Kb-Blast-Hash",
            },
        )

    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(session, caller, issue.id, Capability.DELETE)

    blast = await compute_blast_radius(session, issue.id, for_update=True)
    if blast_hash_header.strip().lower() != blast.blast_hash.lower():
        current_preview = {
            "issue_key": blast.issue_key,
            "sub_issues_unparented": blast.sub_issues_unparented,
            "inbound_links_flagged": blast.inbound_links_flagged,
            "outbound_links": blast.outbound_links,
            "comments": blast.comments,
            "attachments": blast.attachments,
            "summary_text": blast.summary_text,
            "blast_hash": blast.blast_hash,
            "retention_days": blast.retention_days,
        }
        raise ProblemException(
            code="BLAST_RADIUS_CHANGED",
            status=412,
            title="Blast Radius Changed",
            detail="The issue blast radius has changed since the preview was generated",
            current_preview=current_preview,
        )

    now_ts = datetime.now(UTC)
    obj = await session.get(ObjectRecord, issue.id)
    if obj is None:
        not_found()
    obj.deleted_at = now_ts

    # Direct children get parent_issue_id = NULL via SECURITY DEFINER helper
    # ensuring children hidden by caller RLS are cleanly unparented
    unparented_res = (
        await session.execute(
            text("SELECT unparent_issue_children_privileged(:issue_id)"),
            {"issue_id": issue.id},
        )
    ).scalar_one_or_none()
    unparented_ids: list[uuid.UUID] = (
        list(unparented_res) if unparented_res else list(blast.child_ids)
    )

    await record_activity(
        session=session,
        workspace_id=issue.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_TRASHED,
        payload={
            "blast_hash": blast.blast_hash,
            "unparented_child_ids": [str(cid) for cid in unparented_ids],
            "inbound_links_flagged": blast.inbound_links_flagged,
        },
    )

    purge_after = now_ts + timedelta(days=blast.retention_days)
    return IssueDeleteResponse(
        issue_key=blast.issue_key,
        deleted_at=now_ts,
        purge_after=purge_after,
    )


async def list_trash(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    *,
    cursor: str | None,
    limit: int,
) -> TrashedIssueList:
    """List soft-deleted issues in project trash where caller holds DELETE capability.

    Note: Keyset pagination applies limit at the query level before filtering by
    the caller's DELETE capability. As a result, page sizes may be smaller than
    the requested limit when the caller lacks DELETE on some items in the slice.
    """
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    stmt = (
        select(Issue, ObjectRecord.deleted_at)
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(
            Issue.workspace_id == caller.workspace_id,
            Issue.project_id == project.id,
            ObjectRecord.deleted_at.is_not(None),
        )
    )

    if cursor is not None:
        last_seq = decode_issue_cursor(cursor)
        stmt = stmt.where(Issue.sequence_id < last_seq)

    stmt = stmt.order_by(Issue.sequence_id.desc()).limit(limit + 1)
    rows = (await session.execute(stmt)).all()

    retention_days = get_settings().trash_retention_days
    items: list[TrashedIssueItem] = []
    has_more = len(rows) > limit
    page_rows = rows[:limit]

    for issue, deleted_at in page_rows:
        caps = await evaluate_capabilities(session, caller, issue.id)
        if Capability.DELETE not in caps:
            continue
        purge_after = deleted_at + timedelta(days=retention_days)
        state_summary: StateSummary | None = None
        if issue.state_id is not None:
            state = await session.get(WorkflowState, issue.state_id)
            if state is not None:
                state_summary = StateSummary(id=state.id, name=state.name, group=state.state_group)
        priority_summary: PrioritySummary | None = None
        if issue.priority_id is not None:
            priority = await session.get(ProjectPriority, issue.priority_id)
            if priority is not None:
                priority_summary = PrioritySummary(
                    slug=priority.slug,
                    label=priority.label,
                    emoji=priority.emoji,
                )
        items.append(
            TrashedIssueItem(
                id=issue.id,
                key=f"{project.identifier}-{issue.sequence_id}",
                summary=issue.summary,
                deleted_at=deleted_at,
                purge_after=purge_after,
                state=state_summary,
                priority=priority_summary,
                capabilities=capabilities_to_names(caps),
            )
        )

    next_cursor = (
        encode_issue_cursor(page_rows[-1][0].sequence_id) if has_more and page_rows else None
    )
    return TrashedIssueList(items=items, next_cursor=next_cursor)


async def restore_issue(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
) -> IssueResponse:
    """Restore a soft-deleted issue from trash back to active state."""
    issue = await resolve_issue_ref(session, caller, issue_ref, include_deleted=True)
    await require_capability(session, caller, issue.id, Capability.DELETE)

    obj = await session.get(ObjectRecord, issue.id)
    if obj is None or obj.deleted_at is None:
        raise ProblemException(
            code="NOT_IN_TRASH",
            status=409,
            title="Not in Trash",
            detail="Issue is not in trash",
        )

    retention_days = get_settings().trash_retention_days
    now_ts = datetime.now(UTC)
    if obj.deleted_at + timedelta(days=retention_days) < now_ts:
        raise ProblemException(
            code="RETENTION_EXPIRED",
            status=409,
            title="Retention Expired",
            detail="Issue retention window has expired and cannot be restored",
        )

    obj.deleted_at = None

    await record_activity(
        session=session,
        workspace_id=issue.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_RESTORED,
        payload={},
    )

    resp = await serialize_issue(session, caller, issue)
    resp.note = "sub-issues remain unparented"
    return resp


async def list_trash_items(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    *,
    kind: str | None = None,
) -> TrashedObjectList:
    """List all soft-deleted entities (issues, cycles, modules, stickies, docs, pages, project)."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    retention_days = get_settings().trash_retention_days
    now_ts = datetime.now(UTC)

    stmt = (
        select(ObjectRecord)
        .where(
            ObjectRecord.workspace_id == caller.workspace_id,
            (ObjectRecord.project_id == project.id) | (ObjectRecord.id == project.id),
            ObjectRecord.deleted_at.is_not(None),
        )
        .order_by(ObjectRecord.deleted_at.desc())
        .limit(200)
    )
    if kind and kind.lower() != "all":
        kind_clean = kind.lower().strip()
        matching_kinds = [k for k in ObjectKind if k.value.lower() == kind_clean]
        if matching_kinds:
            stmt = stmt.where(ObjectRecord.object_type == matching_kinds[0])

    rows = (await session.execute(stmt)).scalars().all()

    items: list[TrashedObjectItem] = []
    for obj in rows:
        if obj.deleted_at is None:
            continue
        caps = await evaluate_capabilities(session, caller, obj.id)
        if Capability.DELETE not in caps and Capability.ADMIN not in caps:
            continue
        deleted_at = obj.deleted_at
        purge_after = deleted_at + timedelta(days=retention_days)
        remaining_sec = (purge_after - now_ts).total_seconds()
        remaining_days = max(0, int(remaining_sec // 86400))
        items.append(
            TrashedObjectItem(
                id=obj.id,
                key=obj.canonical_key or str(obj.id),
                kind=obj.object_type.value.lower(),
                title=obj.display_title or obj.canonical_key or str(obj.id),
                deleted_at=deleted_at,
                purge_after=purge_after,
                remaining_days=remaining_days,
                capabilities=capabilities_to_names(caps),
            )
        )
    return TrashedObjectList(items=items, retention_days=retention_days)
