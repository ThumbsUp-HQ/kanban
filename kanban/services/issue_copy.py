"""Service layer implementation for Issue Copy API (KB-P3-08, S7.2 8n)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import select, text

from database.models import (
    Attachment,
    Issue,
    IssueLabel,
    IssueModule,
    ObjectRecord,
    Project,
    WorkflowState,
)
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.issue_copy import (
    CopiedSubIssueSummary,
    IssueCopyRequest,
    IssueCopyResponse,
    IssueCopySkipped,
)
from kanban.api.v1.schemas.links import LinkCreateRequest
from kanban.content import ContentNormalizeError, normalize_to_markdown
from kanban.security.permissions import Capability, evaluate_capabilities
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.issues import (
    initial_board_rank,
    serialize_issue,
)
from kanban.services.links import create_object_link

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

MAX_DESCRIPTION_BYTES: Final[int] = 1048576  # 1 MiB
MAX_READABLE_ISSUES_LIMIT: Final[int] = 200


def _normalize_description(raw: str | None) -> str:
    """Normalize description to canonical Markdown and enforce 1 MiB byte cap."""
    if not raw:
        return ""
    try:
        normalized = normalize_to_markdown(raw)
    except ContentNormalizeError as exc:
        if exc.code == "CONTENT_TOO_LARGE":
            raise ProblemException(
                code="DESCRIPTION_TOO_LARGE",
                status=422,
                title="Description Too Large",
                detail="Description exceeds 1 MiB limit",
            ) from exc
        raise ProblemException(
            code="INVALID_CONTENT",
            status=422,
            title="Invalid Content",
            detail="Description contains invalid content",
        ) from exc
    except UnicodeEncodeError as exc:
        raise ProblemException(
            code="INVALID_CONTENT",
            status=422,
            title="Invalid Content",
            detail="Description contains invalid encoding",
        ) from exc

    if len(normalized.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise ProblemException(
            code="DESCRIPTION_TOO_LARGE",
            status=422,
            title="Description Too Large",
            detail="Description exceeds 1 MiB limit",
        )
    return normalized


async def _get_default_state_id(session: AsyncSession, project_id: uuid.UUID) -> uuid.UUID:
    """Fetch default workflow state for a project."""
    state_id = (
        await session.execute(
            select(WorkflowState.id)
            .where(WorkflowState.project_id == project_id, WorkflowState.is_default.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    if state_id is None:
        state_id = (
            await session.execute(
                select(WorkflowState.id)
                .where(WorkflowState.project_id == project_id)
                .order_by(WorkflowState.sort_order)
                .limit(1)
            )
        ).scalar_one()
    return state_id


async def copy_issue(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    req: IssueCopyRequest,
) -> tuple[IssueCopyResponse, str]:
    """Clone an issue and optionally its descendant subtree and attachments.

    Enforces VIEW on source issue and EDIT on target project.
    Runs entirely within an atomic transaction.
    """
    # 1. Resolve source issue through caller access checks
    source_issue = await resolve_issue_ref(session, caller, issue_ref)
    caps = await evaluate_capabilities(session, caller, source_issue.id)
    if Capability.VIEW not in caps:
        not_found()

    # 2. Check caller capability: EDIT on source project required
    project_caps = await evaluate_capabilities(session, caller, source_issue.project_id)
    if Capability.EDIT not in project_caps:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="EDIT capability required on project to copy issues",
        )

    project = await session.get(Project, source_issue.project_id)
    if project is None:  # pragma: no cover
        not_found()

    # 3. If sub-issues requested, inspect descendant subtree via security definer collector
    descendant_rows: list[Any] = []
    restricted_sub_issues = 0
    readable_rows: list[Any] = []

    if req.include_sub_issues:
        collector_stmt = text(
            "SELECT issue_id, parent_issue_id, rel_depth, summary, description_markdown, "
            "priority_id, board_rank, canonical_key, is_readable, is_skipped "
            "FROM issues_get_copy_subtrees(:root_id)"
        )
        res = await session.execute(collector_stmt, {"root_id": source_issue.id})
        descendant_rows = list(res.all())
        readable_count = sum(1 for r in descendant_rows if r.is_readable)
        # Total readable issues = 1 (top-level copy) + readable sub-issues
        if 1 + readable_count > MAX_READABLE_ISSUES_LIMIT:
            raise ProblemException(
                code="COPY_TOO_LARGE",
                status=422,
                title="Copy Too Large",
                detail="Copy operation exceeds 200 readable issues limit",
            )
        restricted_sub_issues = sum(1 for r in descendant_rows if r.is_skipped)
        readable_rows = [r for r in descendant_rows if r.is_readable]

    # 4. Atomic copy transaction
    async with session.begin_nested():
        default_state_id = await _get_default_state_id(session, project.id)

        # Cloned top-level fields
        top_summary = f"[Copy] {source_issue.summary}"[:500]
        top_desc = _normalize_description(source_issue.description_markdown)

        # Sequence and key allocation
        top_seq_id = (
            await session.execute(
                text("SELECT allocate_issue_sequence(:proj)"), {"proj": project.id}
            )
        ).scalar_one()
        top_canonical_key = f"{project.identifier}-{top_seq_id}"
        top_rank = initial_board_rank(top_seq_id)

        # Register in Universal Objects spine
        top_issue_id = (
            await session.execute(
                text(
                    "SELECT register_object("
                    "  CAST('issue' AS object_kind), :ws, :proj, :key, :title, :creator"
                    ")"
                ),
                {
                    "ws": caller.workspace_id,
                    "proj": project.id,
                    "key": top_canonical_key,
                    "title": top_summary,
                    "creator": caller.principal_id,
                },
            )
        ).scalar_one()

        # Custom fields are out of scope until Phase 5 (KB-P5-01+)
        top_copy = Issue(
            id=top_issue_id,
            workspace_id=caller.workspace_id,
            project_id=project.id,
            sequence_id=top_seq_id,
            summary=top_summary,
            description_markdown=top_desc,
            state_id=default_state_id,
            priority_id=source_issue.priority_id,
            created_by_id=caller.principal_id,
            original_created_by_id=caller.principal_id,
            start_date=None,
            due_date=None,
            cycle_id=None,
            parent_issue_id=None,
            board_rank=top_rank,
            ancestry_path=top_issue_id.hex,
        )
        session.add(top_copy)
        await session.flush()

        # Copy labels
        label_ids = (
            (
                await session.execute(
                    select(IssueLabel.label_id).where(IssueLabel.issue_id == source_issue.id)
                )
            )
            .scalars()
            .all()
        )
        for lid in label_ids:
            session.add(
                IssueLabel(issue_id=top_copy.id, label_id=lid, workspace_id=caller.workspace_id)
            )

        # Copy modules (only when modules_enabled is true)
        if getattr(project, "modules_enabled", False):
            module_ids = (
                (
                    await session.execute(
                        select(IssueModule.module_id).where(IssueModule.issue_id == source_issue.id)
                    )
                )
                .scalars()
                .all()
            )
            for mid in module_ids:
                session.add(
                    IssueModule(
                        issue_id=top_copy.id, module_id=mid, workspace_id=caller.workspace_id
                    )
                )

        await session.flush()

        # Emit ISSUE_CREATED activity for top-level copy
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=top_copy.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_CREATED,
            payload={"key": top_canonical_key, "copied_from": str(source_issue.id)},
        )

        # 5. Process readable sub-issues
        id_map: dict[uuid.UUID, uuid.UUID] = {source_issue.id: top_copy.id}
        copied_sub_issues: list[CopiedSubIssueSummary] = []

        for r in readable_rows:
            sub_parent_id = id_map.get(r.parent_issue_id, top_copy.id)
            sub_summary = f"[Copy] {r.summary}"[:500]
            sub_desc = _normalize_description(r.description_markdown)

            sub_seq_id = (
                await session.execute(
                    text("SELECT allocate_issue_sequence(:proj)"), {"proj": project.id}
                )
            ).scalar_one()
            sub_canonical_key = f"{project.identifier}-{sub_seq_id}"
            sub_rank = initial_board_rank(sub_seq_id)

            sub_issue_id = (
                await session.execute(
                    text(
                        "SELECT register_object("
                        "  CAST('issue' AS object_kind), :ws, :proj, :key, :title, :creator"
                        ")"
                    ),
                    {
                        "ws": caller.workspace_id,
                        "proj": project.id,
                        "key": sub_canonical_key,
                        "title": sub_summary,
                        "creator": caller.principal_id,
                    },
                )
            ).scalar_one()

            sub_copy = Issue(
                id=sub_issue_id,
                workspace_id=caller.workspace_id,
                project_id=project.id,
                sequence_id=sub_seq_id,
                summary=sub_summary,
                description_markdown=sub_desc,
                state_id=default_state_id,
                priority_id=r.priority_id or source_issue.priority_id,
                created_by_id=caller.principal_id,
                original_created_by_id=caller.principal_id,
                start_date=None,
                due_date=None,
                cycle_id=None,
                parent_issue_id=sub_parent_id,
                board_rank=sub_rank,
                ancestry_path=sub_issue_id.hex,
            )
            session.add(sub_copy)
            await session.flush()
            id_map[r.issue_id] = sub_issue_id

            # Copy sub-issue labels
            sub_label_ids = (
                (
                    await session.execute(
                        select(IssueLabel.label_id).where(IssueLabel.issue_id == r.issue_id)
                    )
                )
                .scalars()
                .all()
            )
            for lid in sub_label_ids:
                session.add(
                    IssueLabel(issue_id=sub_copy.id, label_id=lid, workspace_id=caller.workspace_id)
                )

            # Copy sub-issue modules
            if getattr(project, "modules_enabled", False):
                sub_module_ids = (
                    (
                        await session.execute(
                            select(IssueModule.module_id).where(IssueModule.issue_id == r.issue_id)
                        )
                    )
                    .scalars()
                    .all()
                )
                for mid in sub_module_ids:
                    session.add(
                        IssueModule(
                            issue_id=sub_copy.id, module_id=mid, workspace_id=caller.workspace_id
                        )
                    )

            await session.flush()

            # Activity for copied sub-issue
            await record_activity(
                session,
                workspace_id=caller.workspace_id,
                object_id=sub_copy.id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.ISSUE_CREATED,
                payload={"key": sub_canonical_key, "copied_from": str(r.issue_id)},
            )
            copied_sub_issues.append(
                CopiedSubIssueSummary(source_key=r.canonical_key, copy_key=sub_canonical_key)
            )

        # 6. Copy attachments if requested
        copied_attachments = 0
        if req.include_attachments:
            # Collect all issues copied: top-level + readable sub-issues
            source_to_copy_pairs = [(source_issue.id, top_copy.id)]
            source_to_copy_pairs.extend((r.issue_id, id_map[r.issue_id]) for r in readable_rows)

            for src_id, target_id in source_to_copy_pairs:
                att_rows = (
                    (
                        await session.execute(
                            select(Attachment).where(
                                Attachment.issue_id == src_id,
                                Attachment.workspace_id == caller.workspace_id,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )

                for att in att_rows:
                    new_att = Attachment(
                        workspace_id=caller.workspace_id,
                        project_id=project.id,
                        issue_id=target_id,
                        uploaded_by_id=caller.principal_id,
                        original_filename=att.original_filename,
                        content_type=att.content_type,
                        byte_size=att.byte_size,
                        pixel_width=att.pixel_width,
                        pixel_height=att.pixel_height,
                        blob_sha256=att.blob_sha256,
                        storage_key=att.storage_key,
                    )
                    session.add(new_att)
                    copied_attachments += 1

            await session.flush()

        # 7. Optional RELATES_TO link from top copy to original issue
        link_id: uuid.UUID | None = None
        if req.link_as_relates_to:
            source_obj = await session.get(ObjectRecord, top_copy.id)
            if source_obj is None:  # pragma: no cover
                not_found()
            link_req = LinkCreateRequest(target=str(source_issue.id), link_type="RELATES_TO")
            link_out = await create_object_link(session, caller, source_obj, link_req)
            link_id = link_out.id

        # 8. Record ISSUE_COPIED on source issue
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=source_issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_COPIED,
            payload={
                "copy_id": str(top_copy.id),
                "copy_key": top_canonical_key,
                "include_sub_issues": req.include_sub_issues,
                "include_attachments": req.include_attachments,
            },
        )

        # 9. Serialize response
        top_issue_response = await serialize_issue(session, caller, top_copy)
        response = IssueCopyResponse(
            issue=top_issue_response,
            copied_sub_issues=copied_sub_issues,
            skipped=IssueCopySkipped(restricted_sub_issues=restricted_sub_issues),
            copied_attachments=copied_attachments,
            link_id=link_id,
        )

    return response, top_canonical_key
