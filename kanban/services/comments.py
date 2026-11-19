# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comment service for threaded comments, reactions, permalinks and mentions (KB-P3-05)."""

from __future__ import annotations

import base64
import hashlib
import unicodedata
import urllib.parse
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from database.models.issues import CommentReaction, Issue, IssueComment
from database.models.principals import EffectiveResourceAccess, Principal
from database.models.projects import Project
from database.models.spine import ObjectRecord
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.comments import (
    AuthorSummary,
    CommentCreate,
    CommentList,
    CommentPatch,
    CommentResponse,
    MentionSummary,
    ReactionResponse,
    ReactionSummary,
)
from kanban.content import ContentNormalizeError, normalize_to_markdown
from kanban.security.permissions import Capability, evaluate_capabilities, require_capability
from kanban.security.scrubber import scrub_text
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.mentions import extract_mentions, resolve_mentions

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

__all__ = [
    "ALLOWED_EMOJIS",
    "MAX_COMMENT_BYTES",
    "MIN_COMMENT_BYTES",
    "add_reaction",
    "create_comment",
    "delete_comment",
    "delete_reaction",
    "list_comments",
    "update_comment",
]

MIN_COMMENT_BYTES: Final[int] = 1
MAX_COMMENT_BYTES: Final[int] = 262144
MAX_INLINED_REPLIES: Final[int] = 200
CURSOR_PARTS_COUNT: Final[int] = 2

# Canonical 8 reaction emojis normalized with NFC
_RAW_EMOJIS: Final[tuple[str, ...]] = ("👍", "👎", "😄", "🎉", "😕", "❤️", "🚀", "👀")
ALLOWED_EMOJIS: Final[frozenset[str]] = frozenset(
    unicodedata.normalize("NFC", e) for e in _RAW_EMOJIS
)


def _normalize_emoji(raw: str) -> str:
    """URL-decode and normalize emoji to NFC, verifying against allowlist."""
    decoded = urllib.parse.unquote(raw)
    normalized = unicodedata.normalize("NFC", decoded)
    # Special-case red heart without variation selector (U+2764 -> U+2764 U+FE0F)
    if normalized == "\u2764":
        normalized = "\u2764\ufe0f"

    if normalized not in ALLOWED_EMOJIS:
        raise ProblemException(
            code="EMOJI_NOT_ALLOWED",
            status=422,
            title="Emoji Not Allowed",
            detail=f"Emoji {decoded!r} is not in the allowed reaction set.",
        )
    return normalized


def _normalize_comment_body(raw: str) -> str:
    """Normalize body to canonical Markdown and enforce 1..262144 byte bounds."""
    try:
        normalized = normalize_to_markdown(raw)
    except ContentNormalizeError as exc:
        raise ProblemException(
            code="COMMENT_LENGTH" if exc.code == "CONTENT_TOO_LARGE" else "INVALID_CONTENT",
            status=422,
            title="Invalid Content",
        ) from exc
    except UnicodeEncodeError as exc:
        raise ProblemException(code="INVALID_CONTENT", status=422, title="Invalid Content") from exc

    byte_len = len(normalized.encode("utf-8"))
    if byte_len < MIN_COMMENT_BYTES or byte_len > MAX_COMMENT_BYTES:
        err_detail = (
            f"Comment body must be between {MIN_COMMENT_BYTES} and {MAX_COMMENT_BYTES} bytes."
        )
        raise ProblemException(
            code="COMMENT_LENGTH",
            status=422,
            title="Comment Length",
            detail=err_detail,
        )
    return normalized


def _encode_cursor(ts: datetime, cid: uuid.UUID) -> str:
    """Encode created_at and id into an opaque URL-safe keyset cursor."""
    raw = f"{ts.isoformat()}|{cid}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Decode an opaque URL-safe keyset cursor, raising 422 INVALID_CURSOR on malformed data."""
    try:
        raw_bytes = base64.urlsafe_b64decode(cursor.encode("ascii"))
        raw = raw_bytes.decode("utf-8")
        parts = raw.split("|", 1)
        if len(parts) == CURSOR_PARTS_COUNT:
            ts = datetime.fromisoformat(parts[0])
            cid = uuid.UUID(parts[1])
            return ts, cid
    except Exception as exc:
        raise ProblemException(
            code="INVALID_CURSOR",
            status=422,
            title="Invalid Cursor",
            detail="The provided pagination cursor is invalid.",
        ) from exc
    raise ProblemException(
        code="INVALID_CURSOR",
        status=422,
        title="Invalid Cursor",
        detail="The provided pagination cursor is invalid.",
    )


async def _resolve_authors(
    session: AsyncSession,
    author_ids: set[uuid.UUID],
    caller: PrincipalContext | None = None,
    project_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, AuthorSummary]:
    """Batch-resolve author principals and handles with visibility boundary masking."""
    if not author_ids:
        return {}

    project_members: set[uuid.UUID] = set()
    caller_is_admin = False
    if caller is not None:
        caller_is_admin = bool(
            (
                await session.execute(
                    text(
                        "SELECT app_principal_has_role("
                        "NULL, ARRAY['WORKSPACE_ADMIN', 'SERVER_ADMIN'])"
                    )
                )
            ).scalar_one()
        )
        if project_id is not None:
            era_stmt = select(EffectiveResourceAccess.principal_id).where(
                EffectiveResourceAccess.object_id == project_id,
                EffectiveResourceAccess.principal_id.in_(author_ids),
                EffectiveResourceAccess.effective_mask > 0,
            )
            project_members = set((await session.execute(era_stmt)).scalars().all())

    stmt = (
        select(Principal, ObjectRecord.canonical_key)
        .outerjoin(ObjectRecord, ObjectRecord.id == Principal.id)
        .where(Principal.id.in_(author_ids))
    )
    rows = (await session.execute(stmt)).all()
    result: dict[uuid.UUID, AuthorSummary] = {}
    for p, ckey in rows:
        if caller is not None:
            is_cross_ws = p.workspace_id != caller.workspace_id
            is_unauth_peer = (
                not caller_is_admin
                and project_id is not None
                and p.id not in project_members
                and p.id != caller.principal_id
            )
            if is_cross_ws or is_unauth_peer or p.principal_type == "SCRIPT_EPHEMERAL":
                result[p.id] = AuthorSummary(
                    id=p.id,
                    handle="",
                    display_name="1 External Collaborator",
                    redacted=True,
                    label="1 External Collaborator",
                )
                continue

        handle = f"@{ckey.lstrip('@')}" if ckey else f"@{p.display_name.lower().replace(' ', '')}"
        result[p.id] = AuthorSummary(id=p.id, handle=handle, display_name=p.display_name)
    return result


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


def _build_permalink(project_identifier: str, issue_seq: int, comment_id: uuid.UUID) -> str:
    """Format canonical permalink fragment."""
    frag = f"{project_identifier}-{issue_seq}#comment-{comment_id}"
    return f"/projects/{project_identifier}/issues/{frag}"


async def create_comment(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    body: CommentCreate,
) -> tuple[CommentResponse, str]:
    """Create a top-level comment or depth-1 reply, enforce mention access, and emit activity."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(session, caller, issue.id, Capability.COMMENT)

    project = await session.get(Project, issue.project_id)
    if project is None:  # pragma: no cover
        not_found()

    # Threading validation: parent must be non-deleted top-level comment on the same issue
    if body.parent_comment_id is not None:
        parent = await session.get(IssueComment, body.parent_comment_id)
        if (
            parent is None
            or parent.issue_id != issue.id
            or parent.deleted_at is not None
            or parent.parent_comment_id is not None
        ):
            raise ProblemException(
                code="INVALID_PARENT_COMMENT",
                status=422,
                title="Invalid Parent Comment",
                detail="Parent comment must be a non-deleted top-level comment on the same issue.",
            )

    normalized_body = _normalize_comment_body(body.body_markdown)
    extracted_handles = extract_mentions(normalized_body)

    authorized_mentions, unnotified_mentions, newly_acked_pids = await resolve_mentions(
        session,
        caller,
        issue.id,
        extracted_handles,
        acknowledge_mentions=body.acknowledge_mentions,
    )

    comment = IssueComment(
        workspace_id=caller.workspace_id,
        issue_id=issue.id,
        parent_comment_id=body.parent_comment_id,
        author_id=caller.principal_id,
        body_markdown=normalized_body,
    )
    session.add(comment)
    await session.flush()
    await session.refresh(comment)

    body_sha256_hex = (
        comment.body_sha256.hex()
        if comment.body_sha256 is not None
        else hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
    )
    etag = f'"{body_sha256_hex}"'

    # Emit COMMENT_CREATED activity
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.COMMENT_CREATED,
        payload={
            "comment_id": str(comment.id),
            "parent_comment_id": str(comment.parent_comment_id)
            if comment.parent_comment_id
            else None,
            "body_sha256": body_sha256_hex,
            "mentioned_principal_ids": [str(m.principal_id) for m in authorized_mentions],
        },
    )

    # Emit MENTION_ACCESS_ACKNOWLEDGED activity if unauthorized mentions were bypassed
    if newly_acked_pids:
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.MENTION_ACCESS_ACKNOWLEDGED,
            payload={
                "comment_id": str(comment.id),
                "principal_ids": [str(p) for p in newly_acked_pids],
            },
        )

    # Author details
    authors = await _resolve_authors(
        session, {caller.principal_id}, caller=caller, project_id=issue.project_id
    )
    author_summary = authors.get(
        caller.principal_id,
        AuthorSummary(id=caller.principal_id, handle="", display_name=""),
    )

    permalink = _build_permalink(project.identifier, issue.sequence_id, comment.id)

    response = CommentResponse(
        id=comment.id,
        issue_id=issue.id,
        parent_comment_id=comment.parent_comment_id,
        author_id=caller.principal_id,
        author=author_summary,
        body_markdown=scrub_text(normalized_body) if normalized_body else normalized_body,
        body_sha256=body_sha256_hex,
        permalink=permalink,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
        deleted=False,
        reactions=[],
        replies=[],
        replies_next_cursor=None,
        mentions=[
            MentionSummary(handle=m.handle, principal_id=m.principal_id, has_access=m.has_access)
            for m in authorized_mentions
        ],
        unnotified_mentions=[
            MentionSummary(handle=m.handle, principal_id=m.principal_id, has_access=m.has_access)
            for m in unnotified_mentions
        ],
    )
    return response, etag


async def _fetch_replies(
    session: AsyncSession, top_level_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[IssueComment]]:
    """Fetch and group depth-1 replies by parent comment ID."""
    replies_by_parent: dict[uuid.UUID, list[IssueComment]] = {cid: [] for cid in top_level_ids}
    if not top_level_ids:
        return replies_by_parent

    replies_stmt = (
        select(IssueComment)
        .where(IssueComment.parent_comment_id.in_(top_level_ids))
        .order_by(IssueComment.created_at.asc(), IssueComment.id.asc())
    )
    all_replies = (await session.execute(replies_stmt)).scalars().all()
    for r in all_replies:
        if r.parent_comment_id in replies_by_parent:
            replies_by_parent[r.parent_comment_id].append(r)
    return replies_by_parent


async def list_comments(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    cursor: str | None = None,
    limit: int = 50,
) -> CommentList:
    """List top-level comments with nested depth-1 replies using keyset pagination."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(session, caller, issue.id, Capability.VIEW)

    project = await session.get(Project, issue.project_id)
    if project is None:  # pragma: no cover
        not_found()

    clamped_limit = max(1, min(limit, 100))

    # Query top-level comments
    stmt = (
        select(IssueComment)
        .where(
            IssueComment.issue_id == issue.id,
            IssueComment.parent_comment_id.is_(None),
        )
        .order_by(IssueComment.created_at.asc(), IssueComment.id.asc())
    )

    if cursor is not None:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            (IssueComment.created_at > cursor_ts)
            | ((IssueComment.created_at == cursor_ts) & (IssueComment.id > cursor_id))
        )

    stmt = stmt.limit(clamped_limit + 1)
    top_level_rows = list((await session.execute(stmt)).scalars().all())

    next_cursor: str | None = None
    if len(top_level_rows) > clamped_limit:
        last_item = top_level_rows[clamped_limit - 1]
        next_cursor = _encode_cursor(last_item.created_at, last_item.id)
        top_level_rows = top_level_rows[:clamped_limit]

    top_level_ids = [c.id for c in top_level_rows]
    replies_by_parent = await _fetch_replies(session, top_level_ids)

    # Collect all comment IDs and authors for batch resolution
    all_comments = list(top_level_rows)
    for r_list in replies_by_parent.values():
        all_comments.extend(r_list)

    all_ids = {c.id for c in all_comments}
    author_ids = {c.author_id for c in all_comments}

    authors_map = await _resolve_authors(
        session, author_ids, caller=caller, project_id=issue.project_id
    )
    reactions_map = await _batch_reactions(session, all_ids, caller.principal_id)

    def _to_response(c: IssueComment) -> CommentResponse:
        is_deleted = c.deleted_at is not None
        sha_hex = c.body_sha256.hex() if c.body_sha256 is not None and not is_deleted else None
        body_text = None if is_deleted else c.body_markdown
        author = authors_map.get(
            c.author_id,
            AuthorSummary(id=c.author_id, handle="", display_name="Deleted" if is_deleted else ""),
        )
        permalink = _build_permalink(project.identifier, issue.sequence_id, c.id)
        scrubbed_body = scrub_text(body_text) if body_text else body_text
        return CommentResponse(
            id=c.id,
            issue_id=c.issue_id,
            parent_comment_id=c.parent_comment_id,
            author_id=c.author_id,
            author=author,
            body_markdown=scrubbed_body,
            body_sha256=sha_hex,
            permalink=permalink,
            created_at=c.created_at,
            edited_at=c.edited_at,
            deleted=is_deleted,
            reactions=reactions_map.get(c.id, []),
            replies=[],
            replies_next_cursor=None,
            mentions=[],
            unnotified_mentions=[],
        )

    items: list[CommentResponse] = []
    for top_c in top_level_rows:
        resp = _to_response(top_c)
        child_replies = replies_by_parent.get(top_c.id, [])
        # Inline up to MAX_INLINED_REPLIES replies
        inlined = child_replies[:MAX_INLINED_REPLIES]
        resp.replies = [_to_response(r) for r in inlined]
        if len(child_replies) > MAX_INLINED_REPLIES:
            last_reply = child_replies[MAX_INLINED_REPLIES - 1]
            resp.replies_next_cursor = _encode_cursor(last_reply.created_at, last_reply.id)
        items.append(resp)

    return CommentList(items=items, next_cursor=next_cursor)


async def update_comment(
    session: AsyncSession,
    caller: PrincipalContext,
    comment_id: uuid.UUID,
    body: CommentPatch,
    if_match: str | None,
) -> tuple[CommentResponse, str]:
    """Edit comment body under ETag concurrency check and emit activity."""
    comment = await session.get(IssueComment, comment_id)
    if comment is None:
        not_found()

    issue = await session.get(Issue, comment.issue_id)
    if issue is None:
        not_found()

    # Anti-enumeration check
    caps = await evaluate_capabilities(session, caller, issue.id)
    if Capability.VIEW not in caps:
        not_found()

    if comment.author_id != caller.principal_id:
        raise ProblemException(
            code="NOT_COMMENT_AUTHOR",
            status=403,
            title="Not Comment Author",
            detail="Only the author can edit this comment.",
        )

    if comment.deleted_at is not None:
        raise ProblemException(
            code="COMMENT_DELETED",
            status=409,
            title="Comment Deleted",
            detail="Cannot edit a deleted comment.",
        )

    if if_match is None:
        raise ProblemException(
            code="PRECONDITION_REQUIRED",
            status=428,
            title="Precondition Required",
            detail="If-Match header is required for comment modification.",
        )

    old_sha256 = (
        comment.body_sha256.hex()
        if comment.body_sha256 is not None
        else hashlib.sha256(comment.body_markdown.encode("utf-8")).hexdigest()
    )
    if if_match.strip('"') != old_sha256:
        raise ProblemException(
            code="PRECONDITION_FAILED",
            status=412,
            title="Precondition Failed",
            detail="Comment was modified by another request.",
            current_etag=f'"{old_sha256}"',
        )

    project = await session.get(Project, issue.project_id)
    if project is None:  # pragma: no cover
        not_found()

    normalized_body = _normalize_comment_body(body.body_markdown)
    extracted_handles = extract_mentions(normalized_body)

    authorized_mentions, unnotified_mentions, newly_acked_pids = await resolve_mentions(
        session,
        caller,
        issue.id,
        extracted_handles,
        acknowledge_mentions=body.acknowledge_mentions,
    )

    new_sha256 = hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
    comment.body_markdown = normalized_body
    comment.edited_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(comment)

    # Emit COMMENT_EDITED activity
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.COMMENT_EDITED,
        payload={
            "comment_id": str(comment.id),
            "old_sha256": old_sha256,
            "new_sha256": new_sha256,
        },
    )

    if newly_acked_pids:
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.MENTION_ACCESS_ACKNOWLEDGED,
            payload={
                "comment_id": str(comment.id),
                "principal_ids": [str(p) for p in newly_acked_pids],
            },
        )

    authors = await _resolve_authors(
        session, {comment.author_id}, caller=caller, project_id=issue.project_id
    )
    author_summary = authors.get(
        comment.author_id,
        AuthorSummary(id=comment.author_id, handle="", display_name=""),
    )
    reactions_map = await _batch_reactions(session, {comment.id}, caller.principal_id)
    permalink = _build_permalink(project.identifier, issue.sequence_id, comment.id)

    response = CommentResponse(
        id=comment.id,
        issue_id=issue.id,
        parent_comment_id=comment.parent_comment_id,
        author_id=comment.author_id,
        author=author_summary,
        body_markdown=scrub_text(normalized_body) if normalized_body else normalized_body,
        body_sha256=new_sha256,
        permalink=permalink,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
        deleted=False,
        reactions=reactions_map.get(comment.id, []),
        replies=[],
        replies_next_cursor=None,
        mentions=[
            MentionSummary(handle=m.handle, principal_id=m.principal_id, has_access=m.has_access)
            for m in authorized_mentions
        ],
        unnotified_mentions=[
            MentionSummary(handle=m.handle, principal_id=m.principal_id, has_access=m.has_access)
            for m in unnotified_mentions
        ],
    )
    return response, f'"{new_sha256}"'


async def delete_comment(
    session: AsyncSession,
    caller: PrincipalContext,
    comment_id: uuid.UUID,
) -> None:
    """Soft-delete a comment (author or project ADMIN) and emit activity."""
    comment = await session.get(IssueComment, comment_id)
    if comment is None:
        not_found()

    issue = await session.get(Issue, comment.issue_id)
    if issue is None:
        not_found()

    caps = await evaluate_capabilities(session, caller, issue.id)
    if Capability.VIEW not in caps:
        not_found()

    is_author = comment.author_id == caller.principal_id
    is_admin = Capability.ADMIN in caps

    if not (is_author or is_admin):
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Forbidden",
            detail="Only the author or a project admin can delete this comment.",
        )

    if comment.deleted_at is None:
        comment.deleted_at = datetime.now(UTC)
        await session.flush()

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=issue.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.COMMENT_DELETED,
            payload={
                "comment_id": str(comment.id),
                "deleted_by": str(caller.principal_id),
            },
        )


async def add_reaction(
    session: AsyncSession,
    caller: PrincipalContext,
    comment_id: uuid.UUID,
    emoji: str,
) -> ReactionResponse:
    """Add emoji reaction to comment (idempotent, requires COMMENT capability)."""
    comment = await session.get(IssueComment, comment_id)
    if comment is None:
        not_found()

    issue = await session.get(Issue, comment.issue_id)
    if issue is None:
        not_found()

    caps = await evaluate_capabilities(session, caller, issue.id)
    if Capability.VIEW not in caps:
        not_found()
    if Capability.COMMENT not in caps:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="Caller requires COMMENT capability on the issue to add reactions.",
        )

    normalized_emoji = _normalize_emoji(emoji)

    # Upsert reaction
    stmt = (
        insert(CommentReaction)
        .values(
            comment_id=comment.id,
            principal_id=caller.principal_id,
            emoji=normalized_emoji,
        )
        .on_conflict_do_nothing(index_elements=["comment_id", "principal_id", "emoji"])
    )
    await session.execute(stmt)
    await session.flush()

    # Query total count for this emoji
    count_stmt = (
        select(func.count())
        .select_from(CommentReaction)
        .where(
            CommentReaction.comment_id == comment.id,
            CommentReaction.emoji == normalized_emoji,
        )
    )
    total_count = (await session.execute(count_stmt)).scalar() or 0

    return ReactionResponse(
        emoji=normalized_emoji,
        count=total_count,
        reacted_by_me=True,
    )


async def delete_reaction(
    session: AsyncSession,
    caller: PrincipalContext,
    comment_id: uuid.UUID,
    emoji: str,
) -> None:
    """Remove emoji reaction from comment (idempotent, requires COMMENT capability)."""
    comment = await session.get(IssueComment, comment_id)
    if comment is None:
        not_found()

    issue = await session.get(Issue, comment.issue_id)
    if issue is None:
        not_found()

    caps = await evaluate_capabilities(session, caller, issue.id)
    if Capability.VIEW not in caps:
        not_found()
    if Capability.COMMENT not in caps:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="Caller requires COMMENT capability on the issue to remove reactions.",
        )

    normalized_emoji = _normalize_emoji(emoji)

    del_stmt = delete(CommentReaction).where(
        CommentReaction.comment_id == comment.id,
        CommentReaction.principal_id == caller.principal_id,
        CommentReaction.emoji == normalized_emoji,
    )
    await session.execute(del_stmt)
    await session.flush()
