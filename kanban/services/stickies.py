# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Domain services for Stickies API: complexity signals, snooze & promote-to-doc (KB-P3-15)."""

from __future__ import annotations

import base64
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import func, select, text

from database.models import (
    Doc,
    LinkKind,
    ObjectKind,
    ObjectLink,
    ObjectRecord,
    Page,
    ResourceAclEntry,
    Sticky,
)
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.stickies import (
    PromotedDocSummary,
    StickyCreate,
    StickyList,
    StickyPromoteRequest,
    StickyResponse,
    StickyUpdate,
)
from kanban.content.normalize import normalize_to_markdown
from kanban.security.access_manifest import build_access_manifest
from kanban.security.permissions import (
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
    require_capability,
)
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.lexorank import midpoint_rank
from kanban.services.projects import get_project_or_404
from kanban.services.sticky_heuristic import evaluate_sticky_promotion

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

__all__ = [
    "create_sticky",
    "delete_sticky",
    "get_sticky",
    "list_project_stickies",
    "list_workspace_stickies",
    "promote_sticky_to_doc",
    "snooze_sticky_promotion",
    "unarchive_sticky_copy",
    "update_sticky",
]

_MAX_BODY_BYTES: Final[int] = 65536
_MAX_TITLE_LENGTH: Final[int] = 120
_CURSOR_PARTS_COUNT: Final[int] = 2
_MIN_PAGE_LIMIT: Final[int] = 1
_MAX_PAGE_LIMIT: Final[int] = 100

_ZERO_WIDTH_CHARS: Final[re.Pattern[str]] = re.compile(r"[\u200b-\u200f\ufeff]")
_SLUG_NON_ALPHANUM: Final[re.Pattern[str]] = re.compile(r"[^\w-]")
_SLUG_SPACES: Final[re.Pattern[str]] = re.compile(r"[\s_]+")
_ATX_HEADING_RE: Final[re.Pattern[str]] = re.compile(r"^ {0,3}#{1,6}\s+(.+)$")
_MD_STRIP_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^[>\s*\-+\d\.]+")


def _clean_body(body: str) -> str:
    """Normalize markdown and enforce maximum body length."""
    normalized = normalize_to_markdown(body)
    encoded = normalized.encode("utf-8")
    if len(encoded) > _MAX_BODY_BYTES:
        raise ProblemException(
            code="STICKY_TOO_LARGE",
            status=422,
            title="Sticky Too Large",
            detail=f"body_markdown must not exceed {_MAX_BODY_BYTES} bytes",
        )
    return normalized


def _derive_title(title: str | None, body_markdown: str) -> str:
    """Derive display title from input or first ATX heading or first non-empty line."""
    if title:
        stripped = _ZERO_WIDTH_CHARS.sub("", title).strip()
        if stripped:
            return stripped[:_MAX_TITLE_LENGTH]

    lines = body_markdown.splitlines()
    for line in lines:
        match = _ATX_HEADING_RE.match(line)
        if match:
            heading = _ZERO_WIDTH_CHARS.sub("", match.group(1)).strip()
            if heading:
                return heading[:_MAX_TITLE_LENGTH]

    for line in lines:
        cleaned = _ZERO_WIDTH_CHARS.sub("", _MD_STRIP_PREFIX_RE.sub("", line)).strip()
        if cleaned:
            return cleaned[:_MAX_TITLE_LENGTH]

    return "Untitled Sticky"


def _to_slug(text_val: str, default: str) -> str:
    """Convert text to lowercase URL-safe slug."""
    base = _SLUG_SPACES.sub("-", text_val.lower())
    slug = _SLUG_NON_ALPHANUM.sub("", base).strip("-")
    return slug or default


async def _allocate_unique_canonical_key(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    object_type: str,
    prefix: str,
    base_slug: str,
) -> str:
    """Find a unique canonical_key in objects for the given slug, appending -1, -2 if needed."""
    candidate = f"{prefix}/{base_slug}" if prefix else base_slug
    idx = 1
    while True:
        exists = (
            await session.execute(
                select(ObjectRecord.id).where(
                    ObjectRecord.workspace_id == workspace_id,
                    ObjectRecord.object_type == object_type,
                    ObjectRecord.canonical_key == candidate,
                    ObjectRecord.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            return candidate
        candidate = f"{prefix}/{base_slug}-{idx}" if prefix else f"{base_slug}-{idx}"
        idx += 1


def _format_etag(sha256_bytes: bytes | None) -> str:
    """Format sha256 byte string into standard quoted ETag header value."""
    if not sha256_bytes:
        return '""'
    return f'"{sha256_bytes.hex()}"'


def _verify_if_match(if_match: str | None, current_sha: bytes | None) -> None:
    """Validate If-Match precondition against current body_sha256."""
    if if_match is None:
        raise ProblemException(
            code="PRECONDITION_REQUIRED",
            status=428,
            title="Precondition Required",
            detail="If-Match header is required when modifying body_markdown",
        )

    current_tag = _format_etag(current_sha)
    clean_match = if_match.strip()

    if clean_match == "*":
        return

    current_hex = current_sha.hex() if current_sha else ""
    unquoted = clean_match.strip('"')

    if clean_match != current_tag and unquoted != current_hex:
        raise ProblemException(
            code="PRECONDITION_FAILED",
            status=412,
            title="Precondition Failed",
            detail="Provided ETag does not match current resource state",
            headers={"ETag": current_tag},
            current_etag=current_tag,
        )


def _encode_cursor(ts: datetime, sid: uuid.UUID) -> str:
    """Encode created_at and sticky UUID into URL-safe base64 keyset cursor."""
    raw = f"{ts.isoformat()}|{sid}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Decode an opaque URL-safe keyset cursor, raising 422 INVALID_CURSOR on malformed data."""
    try:
        raw_bytes = base64.urlsafe_b64decode(cursor.encode("ascii"))
        raw = raw_bytes.decode("utf-8")
        parts = raw.split("|", 1)
        if len(parts) == _CURSOR_PARTS_COUNT:
            ts = datetime.fromisoformat(parts[0])
            sid = uuid.UUID(parts[1])
            return ts, sid
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


async def _resolve_promoted_doc_summary(
    session: AsyncSession,
    caller: PrincipalContext,
    promoted_to_doc_id: uuid.UUID,
) -> PromotedDocSummary:
    """Build summary for target doc, returning restricted placeholder if unreadable."""
    doc_row = (
        await session.execute(
            select(Doc, ObjectRecord.canonical_key)
            .join(ObjectRecord, ObjectRecord.id == Doc.id)
            .where(
                Doc.id == promoted_to_doc_id,
                ObjectRecord.deleted_at.is_(None),
            )
        )
    ).first()

    if doc_row is not None:
        doc_entity, doc_ckey = doc_row
        doc_caps = await evaluate_capabilities(session, caller, doc_entity.id)
        if Capability.VIEW in doc_caps:
            return PromotedDocSummary(
                id=doc_entity.id,
                canonical_key=doc_ckey,
                title=doc_entity.title,
                restricted=False,
            )

    return PromotedDocSummary(restricted=True)


async def _build_sticky_response(
    session: AsyncSession,
    caller: PrincipalContext,
    sticky: Sticky,
    obj_rec: ObjectRecord,
) -> tuple[StickyResponse, str]:
    """Construct a full StickyResponse with access manifest, capabilities and doc summary."""
    etag = _format_etag(sticky.body_sha256)
    manifest = await build_access_manifest(session, caller, sticky.id)
    caps = await evaluate_capabilities(session, caller, sticky.id)
    assessment = evaluate_sticky_promotion(
        sticky.body_markdown,
        sticky.promotion_snoozed_at_length,
        sticky.promoted_to_doc_id,
    )

    promoted_to_doc: PromotedDocSummary | None = None
    is_promoted_stub = sticky.promoted_to_doc_id is not None

    if is_promoted_stub and sticky.promoted_to_doc_id is not None:
        promoted_to_doc = await _resolve_promoted_doc_summary(
            session, caller, sticky.promoted_to_doc_id
        )

    resp = StickyResponse(
        id=sticky.id,
        workspace_id=sticky.workspace_id,
        project_id=sticky.project_id,
        body_markdown=sticky.body_markdown,
        body_sha256=sticky.body_sha256.hex() if sticky.body_sha256 else "",
        color_token=sticky.color_token,
        sort_rank=sticky.sort_rank,
        promotion_recommended=assessment.recommended,
        promotion_snoozed_at_length=sticky.promotion_snoozed_at_length,
        promoted_to_doc_id=sticky.promoted_to_doc_id,
        is_promoted_stub=is_promoted_stub,
        promoted_to_doc=promoted_to_doc,
        triggers=assessment.triggers,
        etag=etag,
        access_manifest=manifest.model_dump(),
        capabilities=capabilities_to_names(caps),
        created_at=obj_rec.created_at,
        updated_at=obj_rec.updated_at,
    )
    return resp, etag


async def create_sticky(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    body: StickyCreate,
) -> tuple[StickyResponse, str]:
    """Create a new sticky note in the specified project."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.EDIT)

    clean_body = _clean_body(body.body_markdown)
    color_val = body.color_token.value

    if body.sort_rank:
        sort_rank = body.sort_rank
    else:
        last_rank = (
            await session.execute(
                select(Sticky.sort_rank)
                .join(ObjectRecord, ObjectRecord.id == Sticky.id)
                .where(
                    Sticky.workspace_id == caller.workspace_id,
                    Sticky.project_id == project.id,
                    ObjectRecord.deleted_at.is_(None),
                )
                .order_by(Sticky.sort_rank.collate("C").desc(), Sticky.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        sort_rank = midpoint_rank(last_rank, None)

    assessment = evaluate_sticky_promotion(clean_body)
    sticky_id = uuid.uuid4()
    canonical_key = f"stickies/{sticky_id}"
    display_title = _derive_title(None, clean_body)

    async with session.begin_nested():
        await session.execute(
            text(
                "SELECT register_object("
                "  CAST('sticky' AS object_kind), :ws, :proj, :ckey, :title, :creator, :id"
                ")"
            ),
            {
                "ws": caller.workspace_id,
                "proj": project.id,
                "ckey": canonical_key,
                "title": display_title,
                "creator": caller.principal_id,
                "id": sticky_id,
            },
        )

        sticky = Sticky(
            id=sticky_id,
            workspace_id=caller.workspace_id,
            project_id=project.id,
            body_markdown=clean_body,
            color_token=color_val,
            promotion_recommended=assessment.recommended,
            promotion_snoozed_at_length=None,
            promoted_to_doc_id=None,
            sort_rank=sort_rank,
        )
        session.add(sticky)
        await session.flush()
        await session.refresh(sticky)

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=sticky.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.STICKY_CREATED,
            payload={"color_token": color_val},
        )

    obj_rec = await session.get(ObjectRecord, sticky.id)
    if obj_rec is None:
        not_found()
    return await _build_sticky_response(session, caller, sticky, obj_rec)


async def list_project_stickies(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    *,
    include_promoted: bool = True,
) -> list[StickyResponse]:
    """List stickies for a project ordered by sort_rank COLLATE 'C'."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    stmt = (
        select(Sticky, ObjectRecord)
        .join(ObjectRecord, ObjectRecord.id == Sticky.id)
        .where(
            Sticky.workspace_id == caller.workspace_id,
            Sticky.project_id == project.id,
            ObjectRecord.deleted_at.is_(None),
        )
    )
    if not include_promoted:
        stmt = stmt.where(Sticky.promoted_to_doc_id.is_(None))

    stmt = stmt.order_by(Sticky.sort_rank.collate("C").asc(), Sticky.id.asc())
    rows = (await session.execute(stmt)).all()

    results: list[StickyResponse] = []
    for sticky, obj_rec in rows:
        caps = await evaluate_capabilities(session, caller, sticky.id)
        if Capability.VIEW in caps:
            resp, _ = await _build_sticky_response(session, caller, sticky, obj_rec)
            results.append(resp)
    return results


async def list_workspace_stickies(
    session: AsyncSession,
    caller: PrincipalContext,
    *,
    cursor: str | None = None,
    limit: int = 50,
) -> StickyList:
    """Keyset-paginated listing of stickies across the workspace."""
    if limit < _MIN_PAGE_LIMIT or limit > _MAX_PAGE_LIMIT:
        raise ProblemException(
            code="INVALID_LIMIT",
            status=422,
            title="Invalid Limit",
            detail=f"Limit must be between {_MIN_PAGE_LIMIT} and {_MAX_PAGE_LIMIT}",
        )

    stmt = (
        select(Sticky, ObjectRecord)
        .join(ObjectRecord, ObjectRecord.id == Sticky.id)
        .where(
            Sticky.workspace_id == caller.workspace_id,
            ObjectRecord.deleted_at.is_(None),
        )
    )

    if cursor is not None:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            (ObjectRecord.created_at < cursor_ts)
            | ((ObjectRecord.created_at == cursor_ts) & (Sticky.id < cursor_id))
        )

    stmt = stmt.order_by(ObjectRecord.created_at.desc(), Sticky.id.desc()).limit(limit + 1)
    rows = (await session.execute(stmt)).all()

    has_more = len(rows) > limit
    target_rows = rows[:limit]

    items: list[StickyResponse] = []
    for sticky, obj_rec in target_rows:
        caps = await evaluate_capabilities(session, caller, sticky.id)
        if Capability.VIEW in caps:
            resp, _ = await _build_sticky_response(session, caller, sticky, obj_rec)
            items.append(resp)

    next_cursor = None
    if has_more and target_rows:
        last_sticky, last_obj = target_rows[-1]
        next_cursor = _encode_cursor(last_obj.created_at, last_sticky.id)

    return StickyList(items=items, next_cursor=next_cursor)


async def get_sticky(
    session: AsyncSession,
    caller: PrincipalContext,
    sticky_id: uuid.UUID,
) -> tuple[StickyResponse, str]:
    """Retrieve a sticky note by UUID, enforcing VIEW capability."""
    stmt = (
        select(Sticky, ObjectRecord)
        .join(ObjectRecord, ObjectRecord.id == Sticky.id)
        .where(
            Sticky.id == sticky_id,
            Sticky.workspace_id == caller.workspace_id,
            ObjectRecord.deleted_at.is_(None),
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        not_found()
    sticky, obj_rec = row
    await require_capability(session, caller, sticky.id, Capability.VIEW)
    return await _build_sticky_response(session, caller, sticky, obj_rec)


async def update_sticky(
    session: AsyncSession,
    caller: PrincipalContext,
    sticky_id: uuid.UUID,
    body: StickyUpdate,
    if_match: str | None = None,
) -> tuple[StickyResponse, str]:
    """Update a sticky note, enforcing ETag preconditions on markdown body edits."""
    stmt = (
        select(Sticky, ObjectRecord)
        .join(ObjectRecord, ObjectRecord.id == Sticky.id)
        .where(
            Sticky.id == sticky_id,
            Sticky.workspace_id == caller.workspace_id,
            ObjectRecord.deleted_at.is_(None),
        )
        .with_for_update(of=Sticky)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        not_found()
    sticky, obj_rec = row
    await require_capability(session, caller, sticky.id, Capability.EDIT)

    fields_set = body.model_fields_set

    async with session.begin_nested():
        if "body_markdown" in fields_set and body.body_markdown is not None:
            if sticky.promoted_to_doc_id is not None:
                raise ProblemException(
                    code="STICKY_PROMOTED_READONLY",
                    status=409,
                    title="Sticky Promoted Readonly",
                    detail="Cannot edit markdown body of a promoted sticky note",
                )
            _verify_if_match(if_match, sticky.body_sha256)
            clean_body = _clean_body(body.body_markdown)
            sticky.body_markdown = clean_body
            assessment = evaluate_sticky_promotion(
                clean_body,
                sticky.promotion_snoozed_at_length,
                sticky.promoted_to_doc_id,
            )
            sticky.promotion_recommended = assessment.recommended

            new_title = _derive_title(None, clean_body)
            obj_rec.display_title = new_title
            await session.flush()
            await session.refresh(sticky)

            await record_activity(
                session,
                workspace_id=caller.workspace_id,
                object_id=sticky.id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.STICKY_UPDATED,
                payload={"body_sha256": sticky.body_sha256.hex() if sticky.body_sha256 else ""},
            )

        if "color_token" in fields_set and body.color_token is not None:
            old_color = sticky.color_token
            new_color = body.color_token.value
            if old_color != new_color:
                sticky.color_token = new_color
                await session.flush()
                await record_activity(
                    session,
                    workspace_id=caller.workspace_id,
                    object_id=sticky.id,
                    actor_principal_id=caller.principal_id,
                    event_type=ActivityEventType.STICKY_RECOLORED,
                    payload={"from": old_color, "to": new_color},
                )

        if "sort_rank" in fields_set and body.sort_rank is not None:
            sticky.sort_rank = body.sort_rank
            await session.flush()

    await session.refresh(sticky)
    await session.refresh(obj_rec)
    return await _build_sticky_response(session, caller, sticky, obj_rec)


async def delete_sticky(
    session: AsyncSession,
    caller: PrincipalContext,
    sticky_id: uuid.UUID,
) -> dict[str, Any]:
    """Soft-delete a sticky note by updating objects.deleted_at."""
    stmt = (
        select(Sticky, ObjectRecord)
        .join(ObjectRecord, ObjectRecord.id == Sticky.id)
        .where(
            Sticky.id == sticky_id,
            Sticky.workspace_id == caller.workspace_id,
            ObjectRecord.deleted_at.is_(None),
        )
        .with_for_update(of=ObjectRecord)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        not_found()
    sticky, obj_rec = row
    await require_capability(session, caller, sticky.id, Capability.DELETE)

    async with session.begin_nested():
        obj_rec.deleted_at = func.clock_timestamp()
        await session.flush()

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=sticky.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.STICKY_TRASHED,
            payload={},
        )

    return {"ok": True, "id": str(sticky.id)}


async def snooze_sticky_promotion(
    session: AsyncSession,
    caller: PrincipalContext,
    sticky_id: uuid.UUID,
) -> tuple[StickyResponse, str]:
    """Snooze promotion recommendation until body grows by >= 1.5x."""
    stmt = (
        select(Sticky, ObjectRecord)
        .join(ObjectRecord, ObjectRecord.id == Sticky.id)
        .where(
            Sticky.id == sticky_id,
            Sticky.workspace_id == caller.workspace_id,
            ObjectRecord.deleted_at.is_(None),
        )
        .with_for_update(of=Sticky)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        not_found()
    sticky, obj_rec = row
    await require_capability(session, caller, sticky.id, Capability.EDIT)

    if sticky.promoted_to_doc_id is not None:
        raise ProblemException(
            code="ALREADY_PROMOTED",
            status=409,
            title="Sticky Already Promoted",
            detail="This sticky has already been promoted to a document",
        )

    at_length = len(sticky.body_markdown)
    async with session.begin_nested():
        sticky.promotion_snoozed_at_length = at_length
        assessment = evaluate_sticky_promotion(
            sticky.body_markdown, at_length, sticky.promoted_to_doc_id
        )
        sticky.promotion_recommended = assessment.recommended
        await session.flush()

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=sticky.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.STICKY_PROMOTION_SNOOZED,
            payload={"at_length": at_length},
        )

    await session.refresh(sticky)
    await session.refresh(obj_rec)
    return await _build_sticky_response(session, caller, sticky, obj_rec)


async def _create_doc_and_root_page(
    session: AsyncSession,
    caller: PrincipalContext,
    sticky: Sticky,
    doc_title: str,
    body_markdown: str | None = None,
) -> tuple[uuid.UUID, str, Page]:
    """Create a new Doc entity and initial root Page holding sticky markdown content."""
    content = body_markdown if body_markdown is not None else sticky.body_markdown
    base_slug = _to_slug(doc_title, "doc")
    doc_ckey = await _allocate_unique_canonical_key(
        session, caller.workspace_id, "doc", "docs", base_slug
    )
    doc_id = (
        await session.execute(
            text(
                "SELECT register_object("
                "  CAST('doc' AS object_kind), :ws, :proj, :ckey, :title, :creator"
                ")"
            ),
            {
                "ws": caller.workspace_id,
                "proj": sticky.project_id,
                "ckey": doc_ckey,
                "title": doc_title,
                "creator": caller.principal_id,
            },
        )
    ).scalar_one()

    doc = Doc(
        id=doc_id,
        workspace_id=caller.workspace_id,
        project_id=sticky.project_id,
        title=doc_title,
        body_markdown=content,
        hierarchy_path="pending",
    )
    session.add(doc)
    await session.flush()
    await session.refresh(doc)

    page_slug = _to_slug(doc_title, "page")
    page_ckey = await _allocate_unique_canonical_key(
        session, caller.workspace_id, "page", doc_ckey, page_slug
    )
    page_id = (
        await session.execute(
            text(
                "SELECT register_object("
                "  CAST('page' AS object_kind), :ws, :proj, :ckey, :title, :creator"
                ")"
            ),
            {
                "ws": caller.workspace_id,
                "proj": sticky.project_id,
                "ckey": page_ckey,
                "title": doc_title,
                "creator": caller.principal_id,
            },
        )
    ).scalar_one()

    page = Page(
        id=page_id,
        workspace_id=caller.workspace_id,
        doc_id=doc.id,
        parent_page_id=None,
        title=doc_title,
        body_markdown=content,
        sort_rank="a0",
        hierarchy_path="pending",
    )
    session.add(page)
    await session.flush()
    await session.refresh(page)

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=doc.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.DOC_CREATED,
        payload={},
    )
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=page.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.PAGE_CREATED,
        payload={},
    )
    return doc.id, doc_ckey, page


async def _create_sub_page_under_parent(  # noqa: PLR0913
    session: AsyncSession,
    caller: PrincipalContext,
    sticky: Sticky,
    parent_target: tuple[Doc, uuid.UUID | None],
    *,
    doc_title: str,
    body_markdown: str | None = None,
) -> tuple[uuid.UUID, str, Page]:
    """Create a Page under an existing Doc / parent page."""
    content = body_markdown if body_markdown is not None else sticky.body_markdown
    parent_doc, parent_page_id = parent_target
    parent_doc_obj = await session.get(ObjectRecord, parent_doc.id)
    target_doc_ckey = parent_doc_obj.canonical_key if parent_doc_obj else f"docs/{parent_doc.id}"

    siblings = (
        await session.execute(
            select(Page.id, Page.sort_rank)
            .where(
                Page.doc_id == parent_doc.id,
                Page.parent_page_id == parent_page_id,
            )
            .order_by(Page.sort_rank.collate("C").asc(), Page.id.asc())
        )
    ).all()
    new_rank = midpoint_rank(siblings[-1][1] if siblings else None, None)

    page_slug = _to_slug(doc_title, "page")
    page_ckey = await _allocate_unique_canonical_key(
        session, caller.workspace_id, "page", target_doc_ckey, page_slug
    )
    page_id = (
        await session.execute(
            text(
                "SELECT register_object("
                "  CAST('page' AS object_kind), :ws, :proj, :ckey, :title, :creator"
                ")"
            ),
            {
                "ws": caller.workspace_id,
                "proj": sticky.project_id,
                "ckey": page_ckey,
                "title": doc_title,
                "creator": caller.principal_id,
            },
        )
    ).scalar_one()

    page = Page(
        id=page_id,
        workspace_id=caller.workspace_id,
        doc_id=parent_doc.id,
        parent_page_id=parent_page_id,
        title=doc_title,
        body_markdown=content,
        sort_rank=new_rank,
        hierarchy_path="pending",
    )
    session.add(page)
    await session.flush()
    await session.refresh(page)

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=page.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.PAGE_CREATED,
        payload={},
    )
    return parent_doc.id, target_doc_ckey, page


async def _copy_direct_acls_verbatim(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    caller_principal_id: uuid.UUID,
    source_acls: Sequence[ResourceAclEntry],
    target_ids: Sequence[uuid.UUID],
) -> None:
    """Copy source ACL entries identically to each target object, refreshing ERA."""
    for entry in source_acls:
        for tid in target_ids:
            cloned = ResourceAclEntry(
                workspace_id=workspace_id,
                object_id=tid,
                principal_id=entry.principal_id,
                effect=entry.effect,
                capability_mask=entry.capability_mask,
                created_by_id=caller_principal_id,
            )
            session.add(cloned)

    if source_acls:
        await session.flush()
        await session.execute(
            text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
            {"ws_id": workspace_id},
        )


async def _validate_parent_scope(
    session: AsyncSession,
    caller: PrincipalContext,
    parent_doc_id: uuid.UUID,
    parent_page_id: uuid.UUID | None,
    sticky_project_id: uuid.UUID | None,
) -> Doc:
    """Validate that parent doc exists, matches sticky project scope, and parent page matches."""
    await require_capability(session, caller, parent_doc_id, Capability.EDIT)
    parent_doc = (
        await session.execute(
            select(Doc).where(
                Doc.id == parent_doc_id,
                Doc.workspace_id == caller.workspace_id,
            )
        )
    ).scalar_one_or_none()
    if parent_doc is None:
        not_found()

    if parent_doc.project_id != sticky_project_id:
        raise ProblemException(
            code="CROSS_SCOPE_PROMOTION_FORBIDDEN",
            status=422,
            title="Cross Scope Promotion Forbidden",
            detail="Cannot promote sticky into a document in a different project scope",
        )

    if parent_page_id is not None:
        await require_capability(session, caller, parent_page_id, Capability.EDIT)
        parent_page = (
            await session.execute(
                select(Page).where(
                    Page.id == parent_page_id,
                    Page.workspace_id == caller.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if parent_page is None:
            not_found()
        if parent_page.doc_id != parent_doc.id:
            raise ProblemException(
                code="PAGE_PARENT_DOC_MISMATCH",
                status=422,
                title="Parent Doc Mismatch",
                detail="Parent page must belong to the target document",
            )

    return parent_doc


async def promote_sticky_to_doc(
    session: AsyncSession,
    caller: PrincipalContext,
    sticky_id: uuid.UUID,
    body: StickyPromoteRequest,
) -> tuple[StickyResponse, str]:
    """Atomically promote a sticky into a Doc + Page preserving direct ACLs verbatim."""
    stmt = (
        select(Sticky, ObjectRecord)
        .join(ObjectRecord, ObjectRecord.id == Sticky.id)
        .where(
            Sticky.id == sticky_id,
            Sticky.workspace_id == caller.workspace_id,
            ObjectRecord.deleted_at.is_(None),
        )
        .with_for_update(of=Sticky)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        not_found()
    sticky, obj_rec = row
    await require_capability(session, caller, sticky.id, Capability.EDIT)

    if sticky.promoted_to_doc_id is not None:
        raise ProblemException(
            code="ALREADY_PROMOTED",
            status=409,
            title="Sticky Already Promoted",
            detail="This sticky has already been promoted to a document",
        )

    sticky_sha_hex = (
        sticky.body_sha256.hex()
        if isinstance(sticky.body_sha256, (bytes, bytearray, memoryview))
        else str(sticky.body_sha256)
    )
    if body.expected_sticky_sha256 is not None and sticky_sha_hex != body.expected_sticky_sha256:
        raise ProblemException(
            code="STICKY_MODIFIED_SINCE_PREVIEW",
            status=409,
            title="Sticky Modified Since Preview",
            detail="Sticky content was modified after promotion preview was generated",
        )

    target_body = (
        normalize_to_markdown(body.structured_body_markdown)
        if body.structured_body_markdown is not None
        else sticky.body_markdown
    )

    parent_doc: Doc | None = None
    if body.parent_doc_id is not None:
        parent_doc = await _validate_parent_scope(
            session, caller, body.parent_doc_id, body.parent_page_id, sticky.project_id
        )

    doc_title = _derive_title(body.title, target_body)

    async with session.begin_nested():
        if parent_doc is None:
            target_doc_id, target_doc_ckey, page = await _create_doc_and_root_page(
                session, caller, sticky, doc_title, body_markdown=target_body
            )
            acl_targets = [target_doc_id, page.id]
        else:
            target_doc_id, target_doc_ckey, page = await _create_sub_page_under_parent(
                session,
                caller,
                sticky,
                (parent_doc, body.parent_page_id),
                doc_title=doc_title,
                body_markdown=target_body,
            )
            acl_targets = [page.id]

        direct_acls = (
            (
                await session.execute(
                    select(ResourceAclEntry).where(ResourceAclEntry.object_id == sticky.id)
                )
            )
            .scalars()
            .all()
        )

        await _copy_direct_acls_verbatim(
            session, caller.workspace_id, caller.principal_id, direct_acls, acl_targets
        )

        link = ObjectLink(
            workspace_id=caller.workspace_id,
            source_id=sticky.id,
            source_type=ObjectKind.STICKY,
            target_id=target_doc_id,
            target_type=ObjectKind.DOC,
            link_type=LinkKind.PROMOTED_TO_DOC,
            link_state="ACTIVE",
            source_key_snapshot=obj_rec.canonical_key,
            target_key_snapshot=target_doc_ckey,
            created_by_id=caller.principal_id,
        )
        session.add(link)

        sticky.promoted_to_doc_id = target_doc_id
        sticky.promotion_recommended = False
        await session.flush()

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=sticky.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.STICKY_PROMOTED_TO_DOC,
            payload={
                "doc_id": str(target_doc_id),
                "page_id": str(page.id),
                "copied_acl_count": len(direct_acls),
            },
        )

    await session.refresh(sticky)
    await session.refresh(obj_rec)
    return await _build_sticky_response(session, caller, sticky, obj_rec)


async def unarchive_sticky_copy(
    session: AsyncSession,
    caller: PrincipalContext,
    sticky_id: uuid.UUID,
) -> tuple[StickyResponse, str]:
    """Clone a promoted sticky's content, color, and ACLs into a fresh unpromoted sticky note."""
    stmt = (
        select(Sticky, ObjectRecord)
        .join(ObjectRecord, ObjectRecord.id == Sticky.id)
        .where(
            Sticky.id == sticky_id,
            Sticky.workspace_id == caller.workspace_id,
            ObjectRecord.deleted_at.is_(None),
        )
        .with_for_update(of=Sticky)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        not_found()
    sticky, obj_rec = row
    await require_capability(session, caller, sticky.id, Capability.EDIT)

    if sticky.promoted_to_doc_id is None:
        raise ProblemException(
            code="NOT_PROMOTED",
            status=409,
            title="Sticky Not Promoted",
            detail="Only promoted stickies can be unarchived into a new copy",
        )

    new_rank = midpoint_rank(sticky.sort_rank, None)
    assessment = evaluate_sticky_promotion(sticky.body_markdown)
    new_id = uuid.uuid4()
    canonical_key = f"stickies/{new_id}"

    async with session.begin_nested():
        await session.execute(
            text(
                "SELECT register_object("
                "  CAST('sticky' AS object_kind), :ws, :proj, :ckey, :title, :creator, :id"
                ")"
            ),
            {
                "ws": caller.workspace_id,
                "proj": sticky.project_id,
                "ckey": canonical_key,
                "title": obj_rec.display_title,
                "creator": caller.principal_id,
                "id": new_id,
            },
        )

        new_sticky = Sticky(
            id=new_id,
            workspace_id=caller.workspace_id,
            project_id=sticky.project_id,
            body_markdown=sticky.body_markdown,
            color_token=sticky.color_token,
            promotion_recommended=assessment.recommended,
            promotion_snoozed_at_length=None,
            promoted_to_doc_id=None,
            sort_rank=new_rank,
        )
        session.add(new_sticky)
        await session.flush()

        direct_acls = (
            (
                await session.execute(
                    select(ResourceAclEntry).where(ResourceAclEntry.object_id == sticky.id)
                )
            )
            .scalars()
            .all()
        )

        await _copy_direct_acls_verbatim(
            session, caller.workspace_id, caller.principal_id, direct_acls, [new_sticky.id]
        )

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=new_sticky.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.STICKY_CREATED,
            payload={"color_token": sticky.color_token},
        )
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=sticky.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.STICKY_UNARCHIVED_COPY,
            payload={
                "new_sticky_id": str(new_sticky.id),
                "source_sticky_id": str(sticky.id),
            },
        )

    new_obj = await session.get(ObjectRecord, new_sticky.id)
    if new_obj is None:
        not_found()
    return await _build_sticky_response(session, caller, new_sticky, new_obj)
