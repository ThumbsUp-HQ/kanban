"""Issue business logic: CRUD, sequence allocation, concurrency and activity (S7.2 8a/8e/8g/8h/8i).

Every function runs inside the caller's RLS-bound request transaction; no function opens
its own connection. Reads rely on PostgreSQL RLS for visibility, so an unreadable issue
is indistinguishable from an absent one (404-not-403, S3.4).

Failure modes (all raised as ProblemException with a stable code):
    - 404 NOT_FOUND: issue absent, deleted, or caller lacks VIEW.
    - 403 INSUFFICIENT_CAPABILITY: caller lacks EDIT or TRANSITION capability.
    - 412 PRECONDITION_FAILED: ETag mismatch or concurrent description modification.
    - 428 PRECONDITION_REQUIRED: If-Match header missing when patching description.
    - 409 PARENT_CYCLE: parent hierarchy cycle detected.
    - 409 PARENT_DEPTH_EXCEEDED: parent hierarchy depth exceeds 6 levels.
    - 422 INVALID_REFERENCE: referenced object absent, unreadable, or from another project.
    - 422 EXCLUSIVE_GROUP_CONFLICT: multiple labels from the same exclusive group requested.
    - 422 MODULES_DISABLED: module_ids supplied when modules_enabled is false.
    - 422 SUMMARY_LENGTH: summary length outside 1..500 characters.
    - 422 DESCRIPTION_TOO_LARGE: normalized description exceeds 1,048,576 bytes.
    - 422 DATE_ORDER: due_date earlier than start_date.
    - 422 INVALID_CURSOR: malformed pagination cursor.
    - 422 INVALID_CONTENT: surrogate characters or unparseable input.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from database.models import (
    Cycle,
    Issue,
    IssueLabel,
    IssueModule,
    Module,
    ObjectRecord,
    Project,
    ProjectLabel,
    ProjectModuleDefault,
    ProjectPriority,
    WorkflowState,
)
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.issues import (
    ArchiveEligibility,
    CycleSummary,
    IssueCreate,
    IssueList,
    IssuePatch,
    IssueResponse,
    LabelSummary,
    ModuleSummary,
    NormalParentSummary,
    PrioritySummary,
    RestrictedParentSummary,
    StateSummary,
)
from kanban.content import ContentNormalizeError, normalize_plain_text, normalize_to_markdown
from kanban.issues.serializers import (
    resolve_latest_gate_verdict,
    resolve_pending_gate,
)
from kanban.security.access_manifest import build_access_manifest
from kanban.security.permissions import (
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
    require_capability,
)
from kanban.security.scrubber import scrub_text
from kanban.services.activity import ActivityEventType, JSONValue, record_activity
from kanban.services.assignees import get_issue_assignees
from kanban.services.issue_keys import _ISSUE_KEY_RE, resolve_issue_ref
from kanban.services.issue_provenance import build_issue_provenance
from kanban.services.projects import get_project_or_404
from kanban.workflows.engine import TransitionEngine

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

MAX_DESCRIPTION_BYTES: Final[int] = 1048576
MAX_SUMMARY_LENGTH: Final[int] = 500
BASE62_ALPHABET: Final[str] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def to_base62(num: int) -> str:
    """Encode a positive integer into base62."""
    if num < 0:
        msg = "num must be non-negative"
        raise ValueError(msg)
    if num == 0:
        return "0"
    digits: list[str] = []
    n = num
    while n > 0:
        digits.append(BASE62_ALPHABET[n % 62])
        n //= 62
    return "".join(reversed(digits))


def initial_board_rank(sequence_id: int) -> str:
    """Compute the initial deterministic board rank token for sequence_id."""
    from kanban.services.board_rank import allocate_initial_board_rank  # noqa: PLC0415

    return allocate_initial_board_rank(sequence_id)


def encode_issue_cursor(sequence_id: int) -> str:
    """Encode sequence_id into an opaque URL-safe base64 cursor."""
    return base64.urlsafe_b64encode(str(sequence_id).encode("ascii")).decode("ascii").rstrip("=")


def decode_issue_cursor(cursor: str) -> int:
    """Decode a base64url cursor into sequence_id or raise 422 INVALID_CURSOR."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
        seq_id = int(raw)
    except (binascii.Error, UnicodeError, ValueError) as exc:
        raise _problem(code="INVALID_CURSOR", status=422, title="Invalid Cursor") from exc

    if seq_id <= 0:
        raise _problem(code="INVALID_CURSOR", status=422, title="Invalid Cursor")
    return seq_id


def _problem(  # noqa: PLR0913
    *,
    code: str,
    status: int,
    title: str,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    current_etag: str | None = None,
    field: str | None = None,
) -> ProblemException:
    """Build a ProblemException with explicit problem attributes."""
    return ProblemException(
        code=code,
        status=status,
        title=title,
        detail=detail,
        headers=headers,
        current_etag=current_etag,
        field=field,
    )


def _normalize_summary(raw: str) -> str:
    """Normalize summary to plain text, strip zero-width characters and check 1..500 bounds."""
    try:
        normalized = normalize_plain_text(raw)
    except (ContentNormalizeError, UnicodeEncodeError) as exc:
        raise _problem(code="INVALID_CONTENT", status=422, title="Invalid Content") from exc

    cleaned = normalized.strip()
    if len(cleaned) < 1 or len(cleaned) > MAX_SUMMARY_LENGTH:
        raise _problem(
            code="SUMMARY_LENGTH",
            status=422,
            title="Summary Length",
            detail="Summary must be between 1 and 500 characters",
            field="summary",
        )
    return cleaned


def _normalize_description(raw: str) -> str:
    """Normalize description to canonical Markdown and enforce 1 MiB byte cap."""
    try:
        normalized = normalize_to_markdown(raw)
    except ContentNormalizeError as exc:
        if exc.code == "CONTENT_TOO_LARGE":
            raise _problem(
                code="DESCRIPTION_TOO_LARGE", status=422, title="Description Too Large"
            ) from exc
        raise _problem(code="INVALID_CONTENT", status=422, title="Invalid Content") from exc
    except UnicodeEncodeError as exc:
        raise _problem(code="INVALID_CONTENT", status=422, title="Invalid Content") from exc

    if len(normalized.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise _problem(code="DESCRIPTION_TOO_LARGE", status=422, title="Description Too Large")
    return normalized


def _validate_dates(start_date: date | None, due_date: date | None) -> None:
    """Enforce due_date >= start_date constraint."""
    if start_date is not None and due_date is not None and due_date < start_date:
        raise _problem(
            code="DATE_ORDER",
            status=422,
            title="Invalid Date Order",
            detail="due_date cannot be earlier than start_date",
        )


def _handle_parent_dag_error(exc: Exception) -> None:
    """Map PostgreSQL parent trigger errors to canonical RFC 7807 problem exceptions."""
    msg = str(exc)
    if "PARENT_CYCLE" in msg or "PARENT_SELF_REFERENCE" in msg:
        raise _problem(
            code="PARENT_CYCLE",
            status=409,
            title="Parent Cycle",
            detail="Setting parent would create a cycle in the issue hierarchy",
            field="parent",
        ) from exc
    if "PARENT_MAX_DEPTH_EXCEEDED" in msg or "issues_ancestry_depth_chk" in msg:
        raise _problem(
            code="PARENT_DEPTH_EXCEEDED",
            status=409,
            title="Parent Depth Exceeded",
            detail="Maximum issue hierarchy depth (6 levels) exceeded",
            field="parent",
        ) from exc
    if "PARENT_NOT_FOUND" in msg or "PARENT_CROSS_PROJECT" in msg:
        raise _problem(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail="Parent issue does not exist or belongs to another project",
            field="parent",
        ) from exc


async def _resolve_parent(
    session: AsyncSession,
    caller: PrincipalContext,
    project: Project,
    parent_ref: str | uuid.UUID,
) -> Issue:
    """Resolve a parent issue reference within the current project and caller RLS."""
    stmt = (
        select(Issue)
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(
            Issue.workspace_id == caller.workspace_id,
            Issue.project_id == project.id,
            ObjectRecord.deleted_at.is_(None),
        )
    )

    if isinstance(parent_ref, uuid.UUID):
        stmt = stmt.where(Issue.id == parent_ref)
    elif _ISSUE_KEY_RE.fullmatch(parent_ref):
        ident, seq_str = parent_ref.rsplit("-", 1)
        if ident != project.identifier:
            raise _problem(
                code="INVALID_REFERENCE",
                status=422,
                title="Invalid Reference",
                detail="Parent issue belongs to another project",
                field="parent",
            )
        stmt = stmt.where(Issue.sequence_id == int(seq_str))
    else:
        try:
            p_uuid = uuid.UUID(parent_ref)
            stmt = stmt.where(Issue.id == p_uuid)
        except ValueError:
            raise _problem(
                code="INVALID_REFERENCE",
                status=422,
                title="Invalid Reference",
                detail="Invalid parent reference format",
                field="parent",
            ) from None

    parent_issue = (await session.execute(stmt)).scalar_one_or_none()
    if parent_issue is None:
        raise _problem(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail="Parent issue does not exist or is not readable",
            field="parent",
        )
    return parent_issue


async def _default_state_id(session: AsyncSession, project_id: uuid.UUID) -> uuid.UUID:
    """Fetch the project default workflow state."""
    state = (
        await session.execute(
            select(WorkflowState.id)
            .where(WorkflowState.project_id == project_id, WorkflowState.is_default.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    if state is None:
        state = (
            await session.execute(
                select(WorkflowState.id)
                .where(WorkflowState.project_id == project_id)
                .order_by(WorkflowState.sort_order)
                .limit(1)
            )
        ).scalar_one()
    return state


async def _resolve_state(
    session: AsyncSession, project_id: uuid.UUID, state_ref: str | uuid.UUID
) -> uuid.UUID:
    """Validate and resolve workflow state by UUID or name within project_id."""
    stmt = select(WorkflowState.id).where(WorkflowState.project_id == project_id)
    if isinstance(state_ref, uuid.UUID):
        stmt = stmt.where(WorkflowState.id == state_ref)
    else:
        try:
            s_uuid = uuid.UUID(state_ref)
            stmt = stmt.where(WorkflowState.id == s_uuid)
        except ValueError:
            stmt = stmt.where(WorkflowState.name == state_ref)

    state = (await session.execute(stmt)).scalar_one_or_none()
    if state is None:
        raise _problem(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail="Workflow state not found in project",
            field="state",
        )
    return state


async def _default_priority_id(session: AsyncSession, project_id: uuid.UUID) -> uuid.UUID:
    """Fetch the project default priority."""
    prio = (
        await session.execute(
            select(ProjectPriority.id)
            .where(ProjectPriority.project_id == project_id, ProjectPriority.is_default.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    if prio is None:
        prio = (
            await session.execute(
                select(ProjectPriority.id)
                .where(ProjectPriority.project_id == project_id)
                .order_by(ProjectPriority.sort_order)
                .limit(1)
            )
        ).scalar_one()
    return prio


async def _resolve_priority(
    session: AsyncSession, project_id: uuid.UUID, priority_ref: str | uuid.UUID
) -> uuid.UUID:
    """Resolve priority by UUID or slug within project_id."""
    stmt = select(ProjectPriority.id).where(ProjectPriority.project_id == project_id)
    if isinstance(priority_ref, uuid.UUID):
        stmt = stmt.where(ProjectPriority.id == priority_ref)
    else:
        try:
            p_uuid = uuid.UUID(priority_ref)
            stmt = stmt.where(ProjectPriority.id == p_uuid)
        except ValueError:
            stmt = stmt.where(ProjectPriority.slug == priority_ref)

    prio_id = (await session.execute(stmt)).scalar_one_or_none()
    if prio_id is None:
        raise _problem(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail="Priority not found in project",
            field="priority",
        )
    return prio_id


async def _resolve_cycle(
    session: AsyncSession, project_id: uuid.UUID, cycle_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Validate that cycle_id belongs to project_id."""
    if cycle_id is None:
        return None
    c_id = (
        await session.execute(
            select(Cycle.id).where(Cycle.project_id == project_id, Cycle.id == cycle_id)
        )
    ).scalar_one_or_none()
    if c_id is None:
        raise _problem(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail="Cycle not found in project",
            field="cycle_id",
        )
    return c_id


async def _resolve_modules(
    session: AsyncSession,
    project: Project,
    module_ids: list[uuid.UUID] | None,
    *,
    is_patch: bool = False,
) -> list[uuid.UUID]:
    """Resolve and validate module assignments adhering to project configuration."""
    if not project.modules_enabled:
        if module_ids is not None:
            raise _problem(
                code="MODULES_DISABLED",
                status=422,
                title="Modules Disabled",
                detail="Modules are disabled for this project",
            )
        return []

    if module_ids is None:
        if is_patch:
            return []
        defaults = (
            (
                await session.execute(
                    select(ProjectModuleDefault.module_id)
                    .where(ProjectModuleDefault.project_id == project.id)
                    .order_by(ProjectModuleDefault.module_id)
                )
            )
            .scalars()
            .all()
        )
        return list(defaults)

    if module_ids:
        rows = (
            (
                await session.execute(
                    select(Module.id).where(
                        Module.project_id == project.id, Module.id.in_(module_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(set(rows)) != len(set(module_ids)):
            raise _problem(
                code="INVALID_REFERENCE",
                status=422,
                title="Invalid Reference",
                detail="One or more module ids do not exist in this project",
                field="module_ids",
            )
    return list(dict.fromkeys(module_ids))


async def _resolve_labels(
    session: AsyncSession, project_id: uuid.UUID, label_ids: list[uuid.UUID] | None
) -> list[uuid.UUID]:
    """Validate labels, verify project membership, and reject exclusive group collisions."""
    if not label_ids:
        return []

    rows = (
        (
            await session.execute(
                select(ProjectLabel).where(
                    ProjectLabel.project_id == project_id, ProjectLabel.id.in_(label_ids)
                )
            )
        )
        .scalars()
        .all()
    )

    if len(rows) != len(set(label_ids)):
        raise _problem(
            code="INVALID_REFERENCE",
            status=422,
            title="Invalid Reference",
            detail="One or more label ids do not exist in this project",
            field="label_ids",
        )

    groups_seen: set[str] = set()
    for lbl in rows:
        if lbl.exclusive_group:
            if lbl.exclusive_group in groups_seen:
                raise _problem(
                    code="EXCLUSIVE_GROUP_CONFLICT",
                    status=422,
                    title="Exclusive Group Conflict",
                    detail=f"Multiple labels share exclusive group {lbl.exclusive_group}",
                )
            groups_seen.add(lbl.exclusive_group)

    return [lbl.id for lbl in rows]


async def _resolve_issue_modules(
    session: AsyncSession, project: Project, issue_id: uuid.UUID
) -> tuple[list[uuid.UUID] | None, list[ModuleSummary]]:
    """Fetch module IDs and summaries for an issue if modules are enabled on the project."""
    if not project.modules_enabled:
        return None, []
    mod_rows = (
        (
            await session.execute(
                select(Module)
                .join(IssueModule, IssueModule.module_id == Module.id)
                .where(IssueModule.issue_id == issue_id)
                .order_by(Module.name)
            )
        )
        .scalars()
        .all()
    )
    return [m.id for m in mod_rows], [ModuleSummary(id=m.id, name=m.name) for m in mod_rows]


async def _resolve_archive_eligibility(
    session: AsyncSession, issue: Issue, state: WorkflowState, archived_at: datetime | None
) -> ArchiveEligibility:
    """Calculate archive eligibility status and explanatory reason for an issue."""
    if archived_at is not None:
        return ArchiveEligibility(
            allowed=False,
            reason="Issue is already archived",
        )
    if state.state_group not in ("completed", "cancelled"):
        return ArchiveEligibility(
            allowed=False,
            reason="Only completed or canceled work items can be archived",
        )
    sub_stmt = (
        select(Issue.id)
        .join(WorkflowState, WorkflowState.id == Issue.state_id)
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(
            Issue.parent_issue_id == issue.id,
            ObjectRecord.deleted_at.is_(None),
            ObjectRecord.archived_at.is_(None),
            WorkflowState.state_group.notin_(["completed", "cancelled"]),
        )
        .limit(1)
    )
    has_open_sub = (await session.execute(sub_stmt)).first() is not None
    if has_open_sub:
        return ArchiveEligibility(
            allowed=False,
            reason="Cannot archive work item with open sub-issues",
        )
    return ArchiveEligibility(allowed=True, reason=None)


def compute_issue_etag(
    issue_resp: IssueResponse,
    updated_at: datetime | str | None = None,
) -> str:
    """Compute strong ETag covering description and all serialized issue attributes (KANBA-212)."""
    assignee_tokens: list[str] = []
    for a in issue_resp.assignees:
        principal_obj = getattr(a, "principal", None)
        free_text_val = getattr(a, "free_text", None)
        token_val = getattr(principal_obj, "id", None) or free_text_val or ""
        assignee_tokens.append(f"{a.kind}:{token_val}")
    assignees_repr = ",".join(sorted(assignee_tokens))
    module_ids_repr = ",".join(sorted(str(m) for m in (issue_resp.module_ids or [])))
    labels_repr = ",".join(sorted(str(lbl.id) for lbl in issue_resp.labels))
    parent_repr = getattr(issue_resp.parent, "key", "") if issue_resp.parent else ""
    updated_at_str = (
        updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at or "")
    )
    parts = [
        issue_resp.description_sha256 or "",
        issue_resp.summary,
        str(issue_resp.created_by_id),
        issue_resp.start_date.isoformat() if issue_resp.start_date else "",
        issue_resp.due_date.isoformat() if issue_resp.due_date else "",
        str(issue_resp.state.id),
        issue_resp.priority.slug,
        assignees_repr,
        str(issue_resp.cycle_id or ""),
        module_ids_repr,
        labels_repr,
        parent_repr,
        f"{issue_resp.access_manifest.pill_label}:{issue_resp.access_manifest.explicit_grant_count}",
        str(issue_resp.board_rank),
        updated_at_str,
    ]
    raw = "|".join(parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f'"{digest}"'


async def serialize_issue(
    session: AsyncSession, caller: PrincipalContext, issue: Issue
) -> IssueResponse:
    """Assemble canonical IssueResponse model including access manifest and capabilities."""
    project = await session.get(Project, issue.project_id)
    if project is None:  # pragma: no cover
        not_found()

    state = await session.get(WorkflowState, issue.state_id)
    priority = await session.get(ProjectPriority, issue.priority_id)
    if state is None or priority is None:  # pragma: no cover
        not_found()

    parent_summary: NormalParentSummary | RestrictedParentSummary | None = None
    if issue.parent_issue_id is not None:
        p_stmt = (
            select(Issue.sequence_id, Issue.summary, Project.identifier)
            .join(Project, Project.id == Issue.project_id)
            .where(Issue.id == issue.parent_issue_id)
        )
        p_row = (await session.execute(p_stmt)).first()
        if p_row is None:
            # Unreadable parent under caller RLS; masked per S7.2 8h
            parent_summary = RestrictedParentSummary()
        else:
            p_seq, p_sum, p_ident = p_row
            parent_summary = NormalParentSummary(key=f"{p_ident}-{p_seq}", summary=p_sum)

    label_rows = (
        (
            await session.execute(
                select(ProjectLabel)
                .join(IssueLabel, IssueLabel.label_id == ProjectLabel.id)
                .where(IssueLabel.issue_id == issue.id)
                .order_by(ProjectLabel.name)
            )
        )
        .scalars()
        .all()
    )

    module_ids, module_summaries = await _resolve_issue_modules(session, project, issue.id)

    cycle_summary: CycleSummary | None = None
    if issue.cycle_id is not None:
        cycle_obj = await session.get(Cycle, issue.cycle_id)
        if cycle_obj is not None:
            cycle_summary = CycleSummary(id=cycle_obj.id, name=cycle_obj.name)

    manifest = await build_access_manifest(session, caller, issue.id)
    caps = await evaluate_capabilities(session, caller, issue.id)
    assignee_items = await get_issue_assignees(session, issue.id)
    provenance = await build_issue_provenance(session, issue)

    sha256_hex = issue.description_sha256.hex() if issue.description_sha256 else ""

    obj = await session.get(ObjectRecord, issue.id, populate_existing=True)
    archived_at = obj.archived_at if obj is not None else None
    archive_eligibility = await _resolve_archive_eligibility(session, issue, state, archived_at)

    pending_gate = await resolve_pending_gate(session, issue)
    latest_gate_verdict = await resolve_latest_gate_verdict(session, issue)

    res = IssueResponse(
        id=issue.id,
        object_id=issue.id,
        key=f"{project.identifier}-{issue.sequence_id}",
        summary=issue.summary,
        description_markdown=(
            scrub_text(issue.description_markdown)
            if issue.description_markdown
            else issue.description_markdown
        ),
        description_sha256=sha256_hex,
        state=StateSummary(
            id=state.id,
            name=state.name,
            group=state.state_group,
            color_hex=state.color_hex,
        ),
        priority=PrioritySummary(slug=priority.slug, label=priority.label, emoji=priority.emoji),
        start_date=issue.start_date,
        due_date=issue.due_date,
        cycle_id=issue.cycle_id,
        cycle=cycle_summary,
        parent=parent_summary,
        labels=[
            LabelSummary(id=lbl.id, name=lbl.name, color_hex=lbl.color_hex) for lbl in label_rows
        ],
        module_ids=module_ids,
        modules=module_summaries,
        assignees=assignee_items,
        board_rank=issue.board_rank,
        created_by_id=issue.created_by_id,
        provenance=provenance,
        access_manifest=manifest,
        capabilities=capabilities_to_names(caps),
        archived_at=archived_at,
        archive_eligibility=archive_eligibility,
        pending_gate=pending_gate,
        latest_gate_verdict=latest_gate_verdict,
    )
    res.etag = compute_issue_etag(res, obj.updated_at if obj is not None else None)
    return res


async def create_issue(
    session: AsyncSession, caller: PrincipalContext, project_ref: str, body: IssueCreate
) -> tuple[IssueResponse, str]:
    """Create an issue, allocate sequence_id, insert joins, emit activity, and return ETag."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.EDIT)

    summary = _normalize_summary(body.summary)
    description = _normalize_description(body.description_markdown)
    _validate_dates(body.start_date, body.due_date)

    target_module_ids = await _resolve_modules(session, project, body.module_ids)
    target_label_ids = await _resolve_labels(session, project.id, body.label_ids)

    state_id = (
        await _default_state_id(session, project.id)
        if body.state_id is None
        else await _resolve_state(session, project.id, body.state_id)
    )

    priority_id = (
        await _default_priority_id(session, project.id)
        if body.priority is None
        else await _resolve_priority(session, project.id, body.priority)
    )

    cycle_id = await _resolve_cycle(session, project.id, body.cycle_id)

    parent_issue_id: uuid.UUID | None = None
    if body.parent is not None:
        parent_issue = await _resolve_parent(session, caller, project, body.parent)
        parent_issue_id = parent_issue.id

    issue_id: uuid.UUID
    canonical_key: str
    seq_id: int

    try:
        async with session.begin_nested():
            seq_row = (
                await session.execute(
                    text(
                        "SELECT allocated_sequences, skipped_sequences "
                        "FROM allocate_issue_sequences(:proj, 1, false)"
                    ),
                    {"proj": project.id},
                )
            ).one()
            allocated_seqs: list[int] = list(seq_row[0])
            skipped_seqs: list[int] = list(seq_row[1])
            seq_id = allocated_seqs[0]

            canonical_key = f"{project.identifier}-{seq_id}"
            rank = initial_board_rank(seq_id)

            if skipped_seqs:
                await record_activity(
                    session,
                    workspace_id=caller.workspace_id,
                    object_id=project.id,
                    actor_principal_id=caller.principal_id,
                    event_type=ActivityEventType.SEQUENCE_SKIPPED,
                    payload={
                        "project_key": project.identifier,
                        "skipped_sequences": skipped_seqs,
                        "allocated_sequence": seq_id,
                        "reason": "agent_safe_sequence_numbering",
                    },
                )

            issue_id = (
                await session.execute(
                    text(
                        "SELECT register_object("
                        "  CAST('issue' AS object_kind), :ws, :proj, :key, :title, :creator"
                        ")"
                    ),
                    {
                        "ws": caller.workspace_id,
                        "proj": project.id,
                        "key": canonical_key,
                        "title": summary,
                        "creator": caller.principal_id,
                    },
                )
            ).scalar_one()

            issue = Issue(
                id=issue_id,
                workspace_id=caller.workspace_id,
                project_id=project.id,
                sequence_id=seq_id,
                summary=summary,
                description_markdown=description,
                state_id=state_id,
                priority_id=priority_id,
                created_by_id=caller.principal_id,
                original_created_by_id=caller.principal_id,
                start_date=body.start_date,
                due_date=body.due_date,
                cycle_id=cycle_id,
                parent_issue_id=parent_issue_id,
                board_rank=rank,
                ancestry_path=issue_id.hex,
            )
            session.add(issue)
            await session.flush()

            if body.module_ids is not None:
                await session.execute(delete(IssueModule).where(IssueModule.issue_id == issue_id))
                for mid in target_module_ids:
                    session.add(
                        IssueModule(
                            issue_id=issue_id, module_id=mid, workspace_id=caller.workspace_id
                        )
                    )

            for lid in target_label_ids:
                session.add(
                    IssueLabel(issue_id=issue_id, label_id=lid, workspace_id=caller.workspace_id)
                )

            await session.flush()
    except (IntegrityError, DBAPIError) as exc:
        _handle_parent_dag_error(exc)
        raise

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue_id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ISSUE_CREATED,
        payload={"key": canonical_key, "copied_from": None},
    )

    created_issue = await session.get(Issue, issue_id)
    if created_issue is None:  # pragma: no cover
        not_found()

    serialized = await serialize_issue(session, caller, created_issue)
    etag = serialized.etag or (
        f'"{created_issue.description_sha256.hex()}"' if created_issue.description_sha256 else '""'
    )
    return serialized, etag


async def get_issue_or_404(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    *,
    workspace_ref: str | None = None,
) -> Issue:
    """Resolve an issue reference through RLS or raise 404 NOT_FOUND."""
    return await resolve_issue_ref(session, caller, issue_ref, workspace_ref=workspace_ref)


async def update_issue(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    body: IssuePatch,
    if_match: str | None,
) -> tuple[IssueResponse, str]:
    """Patch issue fields under description ETag concurrency check and emit activity."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    obj = await session.get(ObjectRecord, issue.id, populate_existing=True)
    if obj is not None and obj.archived_at is not None:
        raise _problem(
            code="ISSUE_ARCHIVED",
            status=409,
            title="Issue Archived",
            detail="Archived issues are read-only and cannot be modified",
        )

    project = await session.get(Project, issue.project_id)
    if project is None:  # pragma: no cover
        not_found()

    required = Capability.EDIT
    if (
        "state_id" in body.model_fields_set
        and body.state_id is not None
        and body.state_id != issue.state_id
    ) or ("state" in body.model_fields_set and body.state is not None):
        required |= Capability.TRANSITION
    await require_capability(session, caller, issue.id, required)

    current_sha256_hex = issue.description_sha256.hex() if issue.description_sha256 else ""
    current_serialized = await serialize_issue(session, caller, issue)
    current_etag = current_serialized.etag or f'"{current_sha256_hex}"'
    current_etag_hex = current_etag.strip('"')

    desc_in_patch = "description_markdown" in body.model_fields_set
    if desc_in_patch and not if_match:
        raise _problem(
            code="PRECONDITION_REQUIRED",
            status=428,
            title="Precondition Required",
            detail="If-Match header is required when updating description",
        )

    if if_match is not None:
        raw_etag = if_match.strip()
        if raw_etag.startswith("W/"):
            raw_etag = raw_etag[2:].strip()
        client_hex = raw_etag.strip('"')
        if client_hex.lower() not in (current_etag_hex.lower(), current_sha256_hex.lower()):
            raise _problem(
                code="PRECONDITION_FAILED",
                status=412,
                title="Precondition Failed",
                detail="Current description ETag does not match If-Match header",
                current_etag=current_etag,
            )

    update_vals: dict[str, Any] = {}
    field_changes: list[tuple[str, JSONValue, JSONValue]] = []

    if "summary" in body.model_fields_set:
        if body.summary is None:
            raise _problem(
                code="SUMMARY_LENGTH",
                status=422,
                title="Summary Length",
                detail="Summary cannot be null",
                field="summary",
            )
        new_summary = _normalize_summary(body.summary)
        if new_summary != issue.summary:
            update_vals["summary"] = new_summary
            field_changes.append(("summary", issue.summary, new_summary))

    desc_changed = False
    new_desc: str = ""
    if desc_in_patch:
        new_desc = _normalize_description(body.description_markdown or "")
        if new_desc != issue.description_markdown:
            update_vals["description_markdown"] = new_desc
            desc_changed = True

    eff_start = body.start_date if "start_date" in body.model_fields_set else issue.start_date
    eff_due = body.due_date if "due_date" in body.model_fields_set else issue.due_date
    _validate_dates(eff_start, eff_due)

    if "start_date" in body.model_fields_set and body.start_date != issue.start_date:
        update_vals["start_date"] = body.start_date
        old_s = issue.start_date.isoformat() if issue.start_date else None
        new_s = body.start_date.isoformat() if body.start_date else None
        field_changes.append(("start_date", old_s, new_s))

    if "due_date" in body.model_fields_set and body.due_date != issue.due_date:
        update_vals["due_date"] = body.due_date
        old_d = issue.due_date.isoformat() if issue.due_date else None
        new_d = body.due_date.isoformat() if body.due_date else None
        field_changes.append(("due_date", old_d, new_d))

    if "priority" in body.model_fields_set:
        new_prio_id = (
            await _default_priority_id(session, issue.project_id)
            if body.priority is None
            else await _resolve_priority(session, issue.project_id, body.priority)
        )
        if new_prio_id != issue.priority_id:
            update_vals["priority_id"] = new_prio_id
            field_changes.append(("priority_id", str(issue.priority_id), str(new_prio_id)))

    target_state_ref = None
    if "state" in body.model_fields_set:
        target_state_ref = body.state
    elif "state_id" in body.model_fields_set:
        target_state_ref = body.state_id

    state_changed = False
    new_state_id: uuid.UUID | None = None
    if "state" in body.model_fields_set or "state_id" in body.model_fields_set:
        new_state_id = (
            await _default_state_id(session, issue.project_id)
            if target_state_ref is None
            else await _resolve_state(session, issue.project_id, target_state_ref)
        )
        if new_state_id != issue.state_id:
            state_changed = True

    if "cycle_id" in body.model_fields_set:
        new_cycle_id = await _resolve_cycle(session, issue.project_id, body.cycle_id)
        if new_cycle_id != issue.cycle_id:
            update_vals["cycle_id"] = new_cycle_id
            old_c = str(issue.cycle_id) if issue.cycle_id else None
            new_c = str(new_cycle_id) if new_cycle_id else None
            field_changes.append(("cycle_id", old_c, new_c))

    if "parent" in body.model_fields_set:
        new_parent_id: uuid.UUID | None = None
        if body.parent is not None:
            parent_obj = await _resolve_parent(session, caller, project, body.parent)
            new_parent_id = parent_obj.id
        if new_parent_id != issue.parent_issue_id:
            update_vals["parent_issue_id"] = new_parent_id
            old_p = str(issue.parent_issue_id) if issue.parent_issue_id else None
            new_p = str(new_parent_id) if new_parent_id else None
            field_changes.append(("parent_issue_id", old_p, new_p))

    modules_changed = False
    target_module_ids: list[uuid.UUID] = []
    if "module_ids" in body.model_fields_set:
        target_module_ids = await _resolve_modules(session, project, body.module_ids, is_patch=True)
        current_module_ids = set(
            (
                await session.execute(
                    select(IssueModule.module_id).where(IssueModule.issue_id == issue.id)
                )
            )
            .scalars()
            .all()
        )
        if set(target_module_ids) != current_module_ids:
            modules_changed = True

    labels_changed = False
    target_label_ids: list[uuid.UUID] = []
    labels_added: list[uuid.UUID] = []
    labels_removed: list[uuid.UUID] = []
    if "label_ids" in body.model_fields_set:
        target_label_ids = await _resolve_labels(session, issue.project_id, body.label_ids)
        current_label_ids = set(
            (
                await session.execute(
                    select(IssueLabel.label_id).where(IssueLabel.issue_id == issue.id)
                )
            )
            .scalars()
            .all()
        )
        target_set = set(target_label_ids)
        labels_added = sorted(target_set - current_label_ids)
        labels_removed = sorted(current_label_ids - target_set)
        labels_changed = bool(labels_added or labels_removed)

    # Check for no-op patch
    if not (update_vals or desc_changed or state_changed or labels_changed or modules_changed):
        return await serialize_issue(session, caller, issue), current_etag

    issue_id = issue.id
    old_desc_sha256_hex = current_sha256_hex

    try:
        async with session.begin_nested():
            if update_vals:
                update_stmt = update(Issue).where(Issue.id == issue_id)
                if if_match is not None and issue.description_sha256 is not None:
                    update_stmt = update_stmt.where(
                        Issue.description_sha256 == issue.description_sha256
                    )
                update_stmt = update_stmt.values(**update_vals)
                res = await session.execute(update_stmt)
                if res.rowcount == 0:
                    fresh_sha = (
                        await session.execute(
                            select(Issue.description_sha256).where(Issue.id == issue_id)
                        )
                    ).scalar_one_or_none()
                    fresh_hex = fresh_sha.hex() if fresh_sha else ""
                    raise _problem(
                        code="PRECONDITION_FAILED",
                        status=412,
                        title="Precondition Failed",
                        detail="Concurrent modification detected",
                        current_etag=f'"{fresh_hex}"',
                    )

            if "summary" in update_vals:
                await session.execute(
                    update(ObjectRecord)
                    .where(ObjectRecord.id == issue_id)
                    .values(display_title=update_vals["summary"])
                )

            if "label_ids" in body.model_fields_set and labels_changed:
                await session.execute(delete(IssueLabel).where(IssueLabel.issue_id == issue_id))
                for lid in target_label_ids:
                    session.add(
                        IssueLabel(
                            issue_id=issue_id, label_id=lid, workspace_id=caller.workspace_id
                        )
                    )

            if "module_ids" in body.model_fields_set and modules_changed:
                await session.execute(delete(IssueModule).where(IssueModule.issue_id == issue_id))
                for mid in target_module_ids:
                    session.add(
                        IssueModule(
                            issue_id=issue_id, module_id=mid, workspace_id=caller.workspace_id
                        )
                    )

            if state_changed and new_state_id is not None:
                await session.flush()
                await TransitionEngine.request_transition(
                    session=session,
                    issue_key=str(issue_id),
                    to_state=new_state_id,
                    actor=caller,
                    if_match=if_match,
                )

            await session.flush()
    except (IntegrityError, DBAPIError) as exc:
        _handle_parent_dag_error(exc)
        raise

    for f_name, old_v, new_v in field_changes:
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
            payload={"field": f_name, "old": old_v, "new": new_v},
        )

    if desc_changed:
        old_h = old_desc_sha256_hex
        new_h = hashlib.sha256(new_desc.encode("utf-8")).hexdigest()
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_DESCRIPTION_CHANGED,
            payload={
                "old_sha256": old_h,
                "new_sha256": new_h,
                "byte_length": len(new_desc.encode("utf-8")),
            },
        )

    if labels_changed:
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.ISSUE_LABELS_CHANGED,
            payload={
                "added": [str(x) for x in labels_added],
                "removed": [str(x) for x in labels_removed],
            },
        )

    await session.flush()
    await session.refresh(issue)
    obj_rec = await session.get(ObjectRecord, issue_id, populate_existing=True)
    if obj_rec is not None:
        await session.refresh(obj_rec)
    updated_issue = issue

    serialized = await serialize_issue(session, caller, updated_issue)
    new_etag = serialized.etag or (
        f'"{updated_issue.description_sha256.hex()}"' if updated_issue.description_sha256 else '""'
    )
    return serialized, new_etag


async def list_issues(  # noqa: PLR0913
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    *,
    cursor: str | None,
    limit: int,
    include_archived: bool = False,
    only_archived: bool = False,
) -> IssueList:
    """List RLS-visible issues within a project in descending sequence order."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    stmt = (
        select(Issue)
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(
            Issue.workspace_id == caller.workspace_id,
            Issue.project_id == project.id,
            ObjectRecord.deleted_at.is_(None),
        )
    )

    if only_archived:
        stmt = stmt.where(ObjectRecord.archived_at.is_not(None))
    elif not include_archived:
        stmt = stmt.where(ObjectRecord.archived_at.is_(None))

    if cursor is not None:
        last_seq = decode_issue_cursor(cursor)
        stmt = stmt.where(Issue.sequence_id < last_seq)

    stmt = stmt.order_by(Issue.sequence_id.desc()).limit(limit + 1)
    rows: Sequence[Issue] = (await session.execute(stmt)).scalars().all()

    page = list(rows[:limit])
    next_cursor = encode_issue_cursor(page[-1].sequence_id) if len(rows) > limit else None

    items = [await serialize_issue(session, caller, item) for item in page]
    return IssueList(items=items, next_cursor=next_cursor)
