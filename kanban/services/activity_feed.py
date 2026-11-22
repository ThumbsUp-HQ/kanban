# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Activity feed service implementing 4-tab filtering and cursor pagination (KB-P3-13)."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import os
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, select

from database.models.activity import ActivityRecord
from database.models.issues import CommentReaction, Issue, IssueComment
from database.models.principals import EffectiveResourceAccess, Principal, RoleBinding
from database.models.projects import Project
from database.models.spine import ObjectRecord
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.activity import (
    ActiveCommentSummary,
    ActivityCounts,
    ActivityFeedResponse,
    ActivityItemResponse,
    NormalActorSummary,
    RedactedActorSummary,
    SoftDeletedCommentSummary,
)
from kanban.api.v1.schemas.comments import ReactionSummary
from kanban.security.permissions import Capability, evaluate_capabilities, require_capability
from kanban.security.scrubber import scrub_text
from kanban.services.activity import (
    EVENT_CATEGORY,
    ActivityCategory,
    ActivityEventType,
)
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.projects import get_project_or_404

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

__all__ = [
    "decode_activity_cursor",
    "encode_activity_cursor",
    "get_issue_activity",
    "get_project_activity",
]

_DEFAULT_CURSOR_SECRET: Final[bytes] = b"kanban-activity-cursor-hmac-secret-v1"
_COMMENT_DELETED_STR: Final[str] = ActivityEventType.COMMENT_DELETED.value
_CURSOR_SEGMENTS: Final[int] = 5


def _get_cursor_secret() -> bytes:
    """Return HMAC secret key for cursor signing."""
    val = os.environ.get("KB_CURSOR_SECRET")
    if val:
        return val.encode("utf-8")
    return _DEFAULT_CURSOR_SECRET


def encode_activity_cursor(
    scope_id: uuid.UUID,
    tab: str,
    order: str,
    recorded_at: datetime,
    record_id: uuid.UUID,
) -> str:
    """Encode keyset pagination parameters into an opaque URL-safe base64 HMAC token."""
    ns = int(recorded_at.timestamp() * 1_000_000_000)
    raw = f"{scope_id}:{tab}:{order}:{ns}:{record_id}".encode("ascii")
    sig = hmac.new(_get_cursor_secret(), raw, hashlib.sha256).hexdigest().encode("ascii")
    return base64.urlsafe_b64encode(raw + b"." + sig).decode("ascii").rstrip("=")


def _cursor_error() -> ProblemException:
    return ProblemException(
        code="INVALID_CURSOR",
        status=422,
        title="Invalid Cursor",
        detail="The provided pagination cursor is invalid or mismatched.",
    )


def _parse_cursor(
    cursor: str,
    expected_scope_id: uuid.UUID,
    expected_tab: str,
    expected_order: str,
) -> tuple[datetime, uuid.UUID]:
    padded = cursor + "=" * (-len(cursor) % 4)
    data = base64.urlsafe_b64decode(padded.encode("ascii"))
    if b"." not in data:
        raise _cursor_error()
    raw, sig = data.split(b".", 1)
    expected_sig = hmac.new(_get_cursor_secret(), raw, hashlib.sha256).hexdigest().encode("ascii")
    if not hmac.compare_digest(sig, expected_sig):
        raise _cursor_error()
    parts = raw.decode("utf-8").split(":")
    if len(parts) != _CURSOR_SEGMENTS:
        raise _cursor_error()
    scope_id_str, tab, order, ns_str, id_str = parts
    if uuid.UUID(scope_id_str) != expected_scope_id:
        raise _cursor_error()
    if tab != expected_tab or order != expected_order:
        raise _cursor_error()
    ns = int(ns_str)
    ts = datetime.fromtimestamp(ns / 1_000_000_000, tz=UTC)
    rid = uuid.UUID(id_str)
    return ts, rid


def decode_activity_cursor(
    cursor: str,
    expected_scope_id: uuid.UUID,
    expected_tab: str,
    expected_order: str,
) -> tuple[datetime, uuid.UUID]:
    """Decode and verify an opaque base64url HMAC token, raising 422 INVALID_CURSOR on mismatch."""
    try:
        return _parse_cursor(cursor, expected_scope_id, expected_tab, expected_order)
    except ProblemException:
        raise
    except Exception as exc:
        raise _cursor_error() from exc


COMMENT_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    event.value for event, cat in EVENT_CATEGORY.items() if cat == ActivityCategory.COMMENT
)
GATE_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    event.value for event, cat in EVENT_CATEGORY.items() if cat == ActivityCategory.AGENT_GATE
)
HISTORY_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    event.value for event, cat in EVENT_CATEGORY.items() if cat == ActivityCategory.HISTORY
)
ALL_TAB_EVENT_TYPES: Final[frozenset[str]] = (
    COMMENT_EVENT_TYPES | GATE_EVENT_TYPES | HISTORY_EVENT_TYPES
)

TAB_EVENT_TYPES: Final[dict[str, frozenset[str]]] = {
    "all": ALL_TAB_EVENT_TYPES,
    "comments": COMMENT_EVENT_TYPES,
    "history": HISTORY_EVENT_TYPES,
    "gates": GATE_EVENT_TYPES,
}


def _build_permalink(project_identifier: str, issue_seq: int, comment_id: uuid.UUID) -> str:
    """Format canonical permalink URL for an issue comment."""
    ident = project_identifier
    return f"/projects/{ident}/issues/{ident}-{issue_seq}#comment-{comment_id}"


async def _batch_reactions(
    session: AsyncSession, comment_ids: set[uuid.UUID], caller_id: uuid.UUID
) -> dict[uuid.UUID, list[ReactionSummary]]:
    """Batch-aggregate emoji reactions for a collection of comments."""
    if not comment_ids:
        return {}

    stmt = (
        select(
            CommentReaction.comment_id,
            CommentReaction.emoji,
            func.count().label("reaction_count"),
            func.bool_or(CommentReaction.principal_id == caller_id).label("reacted_by_me"),
        )
        .where(CommentReaction.comment_id.in_(comment_ids))
        .group_by(CommentReaction.comment_id, CommentReaction.emoji)
    )
    rows = (await session.execute(stmt)).all()

    result: dict[uuid.UUID, list[ReactionSummary]] = {cid: [] for cid in comment_ids}
    for cid, emoji, count, reacted_by_me in rows:
        result[cid].append(
            ReactionSummary(
                emoji=emoji,
                count=count,
                reacted_by_me=bool(reacted_by_me),
            )
        )
    return result


async def _resolve_actors(  # noqa: C901
    session: AsyncSession,
    caller: PrincipalContext,
    actor_ids: set[uuid.UUID],
    project_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, NormalActorSummary | RedactedActorSummary]:
    """Resolve in-boundary actor principals and redact out-of-boundary collaborators."""
    if not actor_ids:
        return {}

    p_stmt = select(Principal).where(Principal.id.in_(actor_ids))
    p_rows = list((await session.execute(p_stmt)).scalars().all())
    p_map = {p.id: p for p in p_rows}

    # Query workspace roles for these actors (visible to admin or self)
    rb_stmt = select(RoleBinding.principal_id, RoleBinding.role).where(
        RoleBinding.principal_id.in_(actor_ids),
        RoleBinding.workspace_id == caller.workspace_id,
        RoleBinding.scope_type == "workspace",
    )
    rb_rows = list((await session.execute(rb_stmt)).all())
    role_map: dict[uuid.UUID, str] = {
        row[0]: (row[1].value if hasattr(row[1], "value") else str(row[1])) for row in rb_rows
    }

    # Check if caller holds an administrative role
    caller_is_admin = False
    caller_rb_stmt = select(RoleBinding.role).where(
        RoleBinding.principal_id == caller.principal_id,
        RoleBinding.workspace_id == caller.workspace_id,
    )
    caller_roles = list((await session.execute(caller_rb_stmt)).scalars().all())
    if any(
        str(r.value if hasattr(r, "value") else r) in ("SERVER_ADMIN", "WORKSPACE_ADMIN")
        for r in caller_roles
    ):
        caller_is_admin = True

    # Query project membership from effective_resource_access if project_id is provided
    project_members: set[uuid.UUID] = set()
    if project_id is not None:
        era_stmt = select(EffectiveResourceAccess.principal_id).where(
            EffectiveResourceAccess.object_id == project_id,
            EffectiveResourceAccess.principal_id.in_(actor_ids),
            EffectiveResourceAccess.effective_mask > 0,
        )
        project_members = set((await session.execute(era_stmt)).scalars().all())

    # Query objects spine for handles / slugs
    obj_stmt = select(ObjectRecord.id, ObjectRecord.canonical_key).where(
        ObjectRecord.id.in_(actor_ids)
    )
    obj_rows = list((await session.execute(obj_stmt)).all())
    obj_map: dict[uuid.UUID, str] = {row[0]: row[1] for row in obj_rows}

    actors: dict[uuid.UUID, NormalActorSummary | RedactedActorSummary] = {}
    for aid in actor_ids:
        principal = p_map.get(aid)
        if principal is None or principal.workspace_id != caller.workspace_id:
            actors[aid] = RedactedActorSummary()
            continue

        if principal.principal_type == "SCRIPT_EPHEMERAL":
            actors[aid] = RedactedActorSummary()
            continue

        ws_role = role_map.get(aid)
        if ws_role == "WORKSPACE_GUEST" and not caller_is_admin:
            actors[aid] = RedactedActorSummary()
            continue

        if not caller_is_admin and project_id is not None and aid not in project_members:
            actors[aid] = RedactedActorSummary()
            continue

        if principal.status != "ACTIVE" and not caller_is_admin:
            actors[aid] = RedactedActorSummary()
            continue

        if principal.principal_type == "USER":
            raw_key = obj_map.get(aid)
            handle = f"@{raw_key.lstrip('@')}" if raw_key else f"@{principal.id.hex[:8]}"
            actors[aid] = NormalActorSummary(
                id=principal.id,
                type="USER",
                handle=handle,
                display_name=principal.display_name,
            )
        else:
            slug = obj_map.get(aid) or principal.display_name.split()[0].lower()
            actors[aid] = NormalActorSummary(
                id=principal.id,
                type="AGENT",
                slug=slug,
                display_name=principal.display_name,
            )

    return actors


async def _enrich_creator_override_payload(
    session: AsyncSession,
    caller: PrincipalContext,
    payload: dict[str, Any],
    actors_map: dict[uuid.UUID, NormalActorSummary | RedactedActorSummary],
    project_id: uuid.UUID | None = None,
) -> None:
    """Resolve human-readable handles for CREATOR_OVERRIDDEN activity diffs."""
    for id_key, target_field in (
        ("old_created_by_id", "old_created_by"),
        ("new_created_by_id", "new_created_by"),
    ):
        val = payload.get(id_key)
        if val is None or not isinstance(val, str):
            continue
        with contextlib.suppress(ValueError, TypeError):
            ref_u = uuid.UUID(val)
            actor_summary = actors_map.get(ref_u)
            if actor_summary is None:
                sub_map = await _resolve_actors(session, caller, {ref_u}, project_id)
                actor_summary = sub_map.get(ref_u)
            if isinstance(actor_summary, NormalActorSummary):
                actor_name = actor_summary.handle or actor_summary.display_name or "Unknown"
                payload[target_field] = actor_name
            elif isinstance(actor_summary, RedactedActorSummary):
                payload[target_field] = actor_summary.label


async def _sanitize_payload(
    session: AsyncSession,
    caller: PrincipalContext,
    record: ActivityRecord,
    actors_map: dict[uuid.UUID, NormalActorSummary | RedactedActorSummary],
    project_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Sanitize referenced principals, mask unreadable linked objects, and strip deleted bodies."""
    payload = dict(record.payload)

    # 1. Redact out-of-boundary referenced principals
    principal_ref_keys = [
        "from_user_id",
        "to_user_id",
        "original_created_by_id",
        "old_created_by_id",
        "new_created_by_id",
        "assignee_id",
        "actor_principal_id",
    ]
    for key in principal_ref_keys:
        val = payload.get(key)
        if val is not None and isinstance(val, str):
            with contextlib.suppress(ValueError, TypeError):
                ref_uuid = uuid.UUID(val)
                actor_summary = actors_map.get(ref_uuid)
                if actor_summary is None:
                    sub_map = await _resolve_actors(session, caller, {ref_uuid}, project_id)
                    actor_summary = sub_map.get(ref_uuid)
                if isinstance(actor_summary, RedactedActorSummary):
                    payload[key] = {"redacted": True, "label": "1 External Collaborator"}

    # Resolve human-readable handles for CREATOR_OVERRIDDEN events
    if record.event_type in (
        "CREATOR_OVERRIDDEN",
        ActivityEventType.CREATOR_OVERRIDDEN.value,
        ActivityEventType.CREATOR_OVERRIDDEN,
    ):
        await _enrich_creator_override_payload(session, caller, payload, actors_map, project_id)

    # 2. Mask unreadable linked objects in LINK_CREATED / LINK_DELETED
    if record.event_type in (
        ActivityEventType.LINK_CREATED.value,
        ActivityEventType.LINK_DELETED.value,
        ActivityEventType.LINK_CREATED,
        ActivityEventType.LINK_DELETED,
    ):
        source_id_str = payload.get("source_id")
        target_id_str = payload.get("target_id")
        if source_id_str and target_id_str:
            with contextlib.suppress(ValueError, TypeError):
                src_u = uuid.UUID(str(source_id_str))
                tgt_u = uuid.UUID(str(target_id_str))
                other_id = tgt_u if record.object_id == src_u else src_u
                caps = await evaluate_capabilities(session, caller, other_id)
                if Capability.VIEW not in caps:
                    payload["target"] = {"restricted": True, "label": "Restricted Object"}
                    payload.pop("target_id", None)
                    payload.pop("source_id", None)

    return payload


async def get_issue_activity(  # noqa: C901, PLR0912, PLR0913, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    *,
    tab: str = "all",
    order: str = "desc",
    limit: int = 50,
    cursor: str | None = None,
    include_hashes: bool = False,
) -> ActivityFeedResponse:
    """Fetch paginated activity feed for a single issue with counts and comment hydration."""
    if tab not in TAB_EVENT_TYPES:
        raise ProblemException(
            code="INVALID_TAB",
            status=422,
            title="Invalid Activity Tab",
            detail=f"Tab must be one of: {', '.join(TAB_EVENT_TYPES.keys())}",
        )

    if order not in ("desc", "asc"):
        raise ProblemException(
            code="INVALID_ORDER",
            status=422,
            title="Invalid Sort Order",
            detail="Order must be 'desc' or 'asc'",
        )

    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(session, caller, issue.id, Capability.VIEW)

    project = await session.get(Project, issue.project_id)
    project_identifier = project.identifier if project else "KAN"

    # Compute tab counts in 1 single query
    counts_stmt = select(
        func.count().filter(ActivityRecord.event_type.in_(COMMENT_EVENT_TYPES)).label("comments"),
        func.count().filter(ActivityRecord.event_type.in_(HISTORY_EVENT_TYPES)).label("history"),
        func.count().filter(ActivityRecord.event_type.in_(GATE_EVENT_TYPES)).label("gates"),
    ).where(
        ActivityRecord.workspace_id == caller.workspace_id,
        ActivityRecord.object_id == issue.id,
    )
    counts_row = (await session.execute(counts_stmt)).one()
    c_comments = counts_row.comments or 0
    c_history = counts_row.history or 0
    c_gates = counts_row.gates or 0
    counts = ActivityCounts(
        all=c_comments + c_history + c_gates,
        comments=c_comments,
        history=c_history,
        gates=c_gates,
    )

    # Build keyset-paginated items query
    target_event_types = TAB_EVENT_TYPES[tab]
    stmt = select(ActivityRecord).where(
        ActivityRecord.workspace_id == caller.workspace_id,
        ActivityRecord.object_id == issue.id,
        ActivityRecord.event_type.in_(target_event_types),
    )

    if cursor is not None:
        c_ts, c_id = decode_activity_cursor(cursor, issue.id, tab, order)
        if order == "desc":
            stmt = stmt.where(
                (ActivityRecord.recorded_at < c_ts)
                | ((ActivityRecord.recorded_at == c_ts) & (ActivityRecord.id < c_id))
            )
        else:
            stmt = stmt.where(
                (ActivityRecord.recorded_at > c_ts)
                | ((ActivityRecord.recorded_at == c_ts) & (ActivityRecord.id > c_id))
            )

    if order == "desc":
        stmt = stmt.order_by(ActivityRecord.recorded_at.desc(), ActivityRecord.id.desc())
    else:
        stmt = stmt.order_by(ActivityRecord.recorded_at.asc(), ActivityRecord.id.asc())

    stmt = stmt.limit(limit + 1)
    records = list((await session.execute(stmt)).scalars().all())

    has_more = len(records) > limit
    page_records = records[:limit]

    # Batch resolve actors for issue
    actor_ids = {r.actor_id for r in page_records if r.actor_id is not None}
    actors_map = await _resolve_actors(session, caller, actor_ids, issue.project_id)

    # Batch resolve comments
    comment_ids: set[uuid.UUID] = set()
    for r in page_records:
        if r.event_type in (
            ActivityEventType.COMMENT_CREATED.value,
            ActivityEventType.COMMENT_EDITED.value,
            ActivityEventType.COMMENT_DELETED.value,
        ):
            cid_val = r.payload.get("comment_id")
            if cid_val is not None:
                with contextlib.suppress(ValueError, TypeError):
                    comment_ids.add(uuid.UUID(str(cid_val)))

    comments_map: dict[uuid.UUID, IssueComment] = {}
    if comment_ids:
        c_stmt = select(IssueComment).where(IssueComment.id.in_(comment_ids))
        c_rows = list((await session.execute(c_stmt)).scalars().all())
        comments_map = {c.id: c for c in c_rows}

    active_comment_ids = {c.id for c in comments_map.values() if c.deleted_at is None}
    reactions_map = await _batch_reactions(session, active_comment_ids, caller.principal_id)

    items: list[ActivityItemResponse] = []
    for r in page_records:
        actor_summary = actors_map.get(r.actor_id) if r.actor_id else None
        sanitized_payload = await _sanitize_payload(
            session, caller, r, actors_map, issue.project_id
        )

        comment_obj: ActiveCommentSummary | SoftDeletedCommentSummary | None = None
        cid_val = r.payload.get("comment_id")
        if cid_val is not None:
            with contextlib.suppress(ValueError, TypeError):
                cid = uuid.UUID(str(cid_val))
                c_model = comments_map.get(cid)
                is_deleted = (
                    c_model is None
                    or c_model.deleted_at is not None
                    or r.event_type == _COMMENT_DELETED_STR
                )
                if is_deleted:
                    comment_obj = SoftDeletedCommentSummary(id=cid, deleted=True)
                    sanitized_payload.pop("body_markdown", None)
                    sanitized_payload.pop("body", None)
                    sanitized_payload.pop("new_sha256", None)
                    sanitized_payload.pop("sha256", None)
                elif c_model is not None:
                    permalink = _build_permalink(project_identifier, issue.sequence_id, c_model.id)
                    b_md = scrub_text(c_model.body_markdown) if c_model.body_markdown else ""
                    comment_obj = ActiveCommentSummary(
                        id=c_model.id,
                        body_markdown=b_md,
                        permalink=permalink,
                        edited_at=c_model.edited_at,
                        reactions=reactions_map.get(c_model.id, []),
                    )

        prev_hash_str = r.prev_hash.hex() if include_hashes else None
        row_hash_str = r.row_hash.hex() if include_hashes else None

        category = EVENT_CATEGORY.get(ActivityEventType(r.event_type), ActivityCategory.HISTORY)

        items.append(
            ActivityItemResponse(
                id=r.id,
                category=category,
                event_type=r.event_type,
                actor=actor_summary,
                created_at=r.recorded_at,
                payload=sanitized_payload,
                comment=comment_obj,
                prev_hash=prev_hash_str,
                row_hash=row_hash_str,
            )
        )

    next_cursor: str | None = None
    if has_more and page_records:
        last_rec = page_records[-1]
        next_cursor = encode_activity_cursor(
            issue.id,
            tab,
            order,
            last_rec.recorded_at,
            last_rec.id,
        )

    return ActivityFeedResponse(
        tab=tab,
        counts=counts,
        items=items,
        next_cursor=next_cursor,
    )


async def get_project_activity(  # noqa: C901, PLR0912, PLR0913, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    *,
    tab: str = "all",
    order: str = "desc",
    limit: int = 50,
    cursor: str | None = None,
    include_hashes: bool = False,
) -> ActivityFeedResponse:
    """Fetch paginated activity feed across an entire project, filtering objects through RLS."""
    if tab not in TAB_EVENT_TYPES:
        raise ProblemException(
            code="INVALID_TAB",
            status=422,
            title="Invalid Activity Tab",
            detail=f"Tab must be one of: {', '.join(TAB_EVENT_TYPES.keys())}",
        )

    if order not in ("desc", "asc"):
        raise ProblemException(
            code="INVALID_ORDER",
            status=422,
            title="Invalid Sort Order",
            detail="Order must be 'desc' or 'asc'",
        )

    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    # Compute tab counts across project under RLS
    counts_stmt = (
        select(
            func.count()
            .filter(ActivityRecord.event_type.in_(COMMENT_EVENT_TYPES))
            .label("comments"),
            func.count()
            .filter(ActivityRecord.event_type.in_(HISTORY_EVENT_TYPES))
            .label("history"),
            func.count().filter(ActivityRecord.event_type.in_(GATE_EVENT_TYPES)).label("gates"),
        )
        .join(ObjectRecord, ObjectRecord.id == ActivityRecord.object_id)
        .where(
            ActivityRecord.workspace_id == caller.workspace_id,
            ObjectRecord.deleted_at.is_(None),
            (ObjectRecord.project_id == project.id) | (ObjectRecord.id == project.id),
        )
    )
    counts_row = (await session.execute(counts_stmt)).one()
    c_comments = counts_row.comments or 0
    c_history = counts_row.history or 0
    c_gates = counts_row.gates or 0
    counts = ActivityCounts(
        all=c_comments + c_history + c_gates,
        comments=c_comments,
        history=c_history,
        gates=c_gates,
    )

    # Keyset paginated items query
    target_event_types = TAB_EVENT_TYPES[tab]
    stmt = (
        select(ActivityRecord)
        .join(ObjectRecord, ObjectRecord.id == ActivityRecord.object_id)
        .where(
            ActivityRecord.workspace_id == caller.workspace_id,
            ObjectRecord.deleted_at.is_(None),
            (ObjectRecord.project_id == project.id) | (ObjectRecord.id == project.id),
            ActivityRecord.event_type.in_(target_event_types),
        )
    )

    if cursor is not None:
        c_ts, c_id = decode_activity_cursor(cursor, project.id, tab, order)
        if order == "desc":
            stmt = stmt.where(
                (ActivityRecord.recorded_at < c_ts)
                | ((ActivityRecord.recorded_at == c_ts) & (ActivityRecord.id < c_id))
            )
        else:
            stmt = stmt.where(
                (ActivityRecord.recorded_at > c_ts)
                | ((ActivityRecord.recorded_at == c_ts) & (ActivityRecord.id > c_id))
            )

    if order == "desc":
        stmt = stmt.order_by(ActivityRecord.recorded_at.desc(), ActivityRecord.id.desc())
    else:
        stmt = stmt.order_by(ActivityRecord.recorded_at.asc(), ActivityRecord.id.asc())

    stmt = stmt.limit(limit + 1)
    records = list((await session.execute(stmt)).scalars().all())

    has_more = len(records) > limit
    page_records = records[:limit]

    # Batch resolve actors for project
    actor_ids = {r.actor_id for r in page_records if r.actor_id is not None}
    actors_map = await _resolve_actors(session, caller, actor_ids, project.id)

    # Batch resolve comments
    comment_ids: set[uuid.UUID] = set()
    for r in page_records:
        if r.event_type in (
            ActivityEventType.COMMENT_CREATED.value,
            ActivityEventType.COMMENT_EDITED.value,
            ActivityEventType.COMMENT_DELETED.value,
        ):
            cid_val = r.payload.get("comment_id")
            if cid_val is not None:
                with contextlib.suppress(ValueError, TypeError):
                    comment_ids.add(uuid.UUID(str(cid_val)))

    comments_map: dict[uuid.UUID, IssueComment] = {}
    issue_seq_map: dict[uuid.UUID, int] = {}
    if comment_ids:
        c_stmt = select(IssueComment).where(IssueComment.id.in_(comment_ids))
        c_rows = list((await session.execute(c_stmt)).scalars().all())
        comments_map = {c.id: c for c in c_rows}
        issue_ids = {c.issue_id for c in c_rows}
        if issue_ids:
            iss_stmt = select(Issue.id, Issue.sequence_id).where(Issue.id.in_(issue_ids))
            iss_rows = list((await session.execute(iss_stmt)).all())
            issue_seq_map = {row[0]: row[1] for row in iss_rows}

    active_comment_ids = {c.id for c in comments_map.values() if c.deleted_at is None}
    reactions_map = await _batch_reactions(session, active_comment_ids, caller.principal_id)

    items: list[ActivityItemResponse] = []
    for r in page_records:
        actor_summary = actors_map.get(r.actor_id) if r.actor_id else None
        sanitized_payload = await _sanitize_payload(session, caller, r, actors_map, project.id)

        comment_obj: ActiveCommentSummary | SoftDeletedCommentSummary | None = None
        cid_val = r.payload.get("comment_id")
        if cid_val is not None:
            with contextlib.suppress(ValueError, TypeError):
                cid = uuid.UUID(str(cid_val))
                c_model = comments_map.get(cid)
                is_deleted = (
                    c_model is None
                    or c_model.deleted_at is not None
                    or r.event_type == _COMMENT_DELETED_STR
                )
                if is_deleted:
                    comment_obj = SoftDeletedCommentSummary(id=cid, deleted=True)
                    sanitized_payload.pop("body_markdown", None)
                    sanitized_payload.pop("body", None)
                    sanitized_payload.pop("new_sha256", None)
                    sanitized_payload.pop("sha256", None)
                elif c_model is not None:
                    seq_id = issue_seq_map.get(c_model.issue_id, 1)
                    permalink = _build_permalink(project.identifier, seq_id, c_model.id)
                    b_md = scrub_text(c_model.body_markdown) if c_model.body_markdown else ""
                    comment_obj = ActiveCommentSummary(
                        id=c_model.id,
                        body_markdown=b_md,
                        permalink=permalink,
                        edited_at=c_model.edited_at,
                        reactions=reactions_map.get(c_model.id, []),
                    )

        prev_hash_str = r.prev_hash.hex() if include_hashes else None
        row_hash_str = r.row_hash.hex() if include_hashes else None

        category = EVENT_CATEGORY.get(ActivityEventType(r.event_type), ActivityCategory.HISTORY)

        items.append(
            ActivityItemResponse(
                id=r.id,
                category=category,
                event_type=r.event_type,
                actor=actor_summary,
                created_at=r.recorded_at,
                payload=sanitized_payload,
                comment=comment_obj,
                prev_hash=prev_hash_str,
                row_hash=row_hash_str,
            )
        )

    next_cursor: str | None = None
    if has_more and page_records:
        last_rec = page_records[-1]
        next_cursor = encode_activity_cursor(
            project.id,
            tab,
            order,
            last_rec.recorded_at,
            last_rec.id,
        )

    return ActivityFeedResponse(
        tab=tab,
        counts=counts,
        items=items,
        next_cursor=next_cursor,
    )
