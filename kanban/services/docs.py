# Copyright 2026 Kanban Platform Contributors
"""Domain services for Docs, hierarchical Pages, versions, and outline extraction (S8.1, S12.2)."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from database.models.knowledge import Doc, Page, PageVersion
from database.models.projects import Project
from database.models.spine import ObjectRecord
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.docs import (
    BreadcrumbItem,
    DocCreate,
    DocResponse,
    DocSummaryResponse,
    DocUpdate,
    OutlineItem,
    PageCreate,
    PageMove,
    PageResponse,
    PageTreeNode,
    PageUpdate,
    PageVersionResponse,
)
from kanban.content.normalize import normalize_to_markdown
from kanban.security.access_manifest import build_access_manifest
from kanban.security.permissions import Capability, evaluate_capabilities, require_capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.lexorank import midpoint_rank
from kanban.services.markdown_outline import extract_markdown_outline

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

__all__ = [
    "create_doc",
    "create_page",
    "delete_doc",
    "delete_page",
    "get_doc",
    "get_doc_tree",
    "get_page",
    "get_page_version",
    "list_docs",
    "list_page_versions",
    "move_page",
    "restore_page_version",
    "update_doc",
    "update_page",
]

_MAX_TITLE_LENGTH: Final[int] = 500
_MAX_BODY_BYTES: Final[int] = 1_048_576  # 1 MiB
_ZERO_WIDTH_CHARS: Final[re.Pattern[str]] = re.compile(r"[\u200b-\u200f\ufeff]")
_SLUG_NON_ALPHANUM: Final[re.Pattern[str]] = re.compile(r"[^\w-]")
_SLUG_SPACES: Final[re.Pattern[str]] = re.compile(r"[\s_]+")
_PAGE_LTREE_LABEL_LEN: Final[int] = 33


def _clean_title(title: str) -> str:
    """Normalize title, strip zero-width characters and whitespace, enforce 1..500 bounds."""
    stripped = _ZERO_WIDTH_CHARS.sub("", title).strip()
    if len(stripped) < 1 or len(stripped) > _MAX_TITLE_LENGTH:
        raise ProblemException(
            code="TITLE_LENGTH",
            status=422,
            title="Title Length Invalid",
            detail=f"Title must be between 1 and {_MAX_TITLE_LENGTH} characters",
        )
    return stripped


def _clean_body(body: str) -> str:
    """Normalize markdown and enforce maximum body length."""
    normalized = normalize_to_markdown(body)
    encoded = normalized.encode("utf-8")
    if len(encoded) > _MAX_BODY_BYTES:
        raise ProblemException(
            code="BODY_TOO_LARGE",
            status=422,
            title="Body Too Large",
            detail=f"body_markdown must not exceed {_MAX_BODY_BYTES} bytes",
        )
    return normalized


def _to_slug(text_val: str, default: str) -> str:
    """Convert text to lowercase URL-safe slug."""
    base = _SLUG_SPACES.sub("-", text_val.lower())
    slug = _SLUG_NON_ALPHANUM.sub("", base).strip("-")
    return slug or default


def _extract_ancestor_uuids(hierarchy_path: str | None) -> list[uuid.UUID]:
    """Parse ancestor UUIDs from ltree hierarchy_path skipping doc root and self."""
    if not hierarchy_path:
        return []
    res: list[uuid.UUID] = []
    labels = hierarchy_path.split(".")
    for label in labels[1:-1]:
        if label.startswith("p") and len(label) == _PAGE_LTREE_LABEL_LEN:
            try:
                res.append(uuid.UUID(hex=label[1:]))
            except ValueError:
                continue
    return res


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

    # Compare hex string directly or quoted ETag
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


async def _auto_create_root_doc(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    proj_id: uuid.UUID,
    clean_ref: str,
    caller_principal_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Auto-create default root doc for a fresh project with zero existing docs."""
    proj_obj = (
        await session.execute(
            select(ObjectRecord.display_title, ObjectRecord.created_by_id).where(
                ObjectRecord.id == proj_id,
                ObjectRecord.workspace_id == workspace_id,
            )
        )
    ).first()
    proj_rec = proj_obj[0] if proj_obj else None
    proj_creator = proj_obj[1] if proj_obj else None

    creator_id = caller_principal_id
    if creator_id is None:
        guc_res = (
            await session.execute(
                text("SELECT nullif(current_setting('app.principal_id', true), '')::uuid")
            )
        ).scalar_one_or_none()
        if guc_res is not None:
            creator_id = guc_res
    if creator_id is None and proj_creator is not None:
        creator_id = proj_creator

    doc_title = f"{proj_rec or clean_ref.upper()} Documentation"
    base_slug = _to_slug(doc_title, "doc")
    canonical_key = await _allocate_unique_canonical_key(
        session, workspace_id, "doc", "docs", base_slug
    )
    new_doc_id = (
        await session.execute(
            text(
                "SELECT register_object("
                "  CAST('doc' AS object_kind), :ws, :proj, :ckey, :title, :creator"
                ")"
            ),
            {
                "ws": workspace_id,
                "proj": proj_id,
                "ckey": canonical_key,
                "title": doc_title,
                "creator": creator_id,
            },
        )
    ).scalar_one()
    doc_inst = Doc(
        id=new_doc_id,
        workspace_id=workspace_id,
        project_id=proj_id,
        title=doc_title,
        body_markdown="",
        hierarchy_path="pending",
    )
    session.add(doc_inst)
    await session.flush()
    return uuid.UUID(str(new_doc_id))


async def _resolve_doc_id(  # noqa: RET503
    session: AsyncSession,
    workspace_id: uuid.UUID,
    doc_ref: str,
    caller_principal_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Resolve doc UUID from UUID string or canonical key, or project identifier."""
    try:
        doc_uuid = uuid.UUID(doc_ref)
        doc = (
            await session.execute(
                select(Doc.id).where(
                    Doc.id == doc_uuid,
                    Doc.workspace_id == workspace_id,
                )
            )
        ).scalar_one_or_none()
        if doc is not None:
            return doc
    except ValueError:
        pass

    clean_ref = doc_ref.strip("/")
    ref_with_prefix = f"docs/{clean_ref}" if not clean_ref.startswith("docs/") else clean_ref

    obj_id = (
        await session.execute(
            select(ObjectRecord.id).where(
                ObjectRecord.workspace_id == workspace_id,
                ObjectRecord.object_type == "doc",
                ObjectRecord.canonical_key.in_([clean_ref, ref_with_prefix]),
                ObjectRecord.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if obj_id is not None:
        return obj_id

    # Fallback: check if doc_ref is a Project identifier or Project UUID
    proj_id: uuid.UUID | None = None
    try:
        proj_uuid = uuid.UUID(doc_ref)
        p_row = (
            await session.execute(
                select(Project.id).where(
                    Project.id == proj_uuid,
                    Project.workspace_id == workspace_id,
                )
            )
        ).scalar_one_or_none()
        if p_row is not None:
            proj_id = p_row
    except ValueError:
        pass

    if proj_id is None:
        p_row = (
            await session.execute(
                select(Project.id).where(
                    Project.workspace_id == workspace_id,
                    Project.identifier == clean_ref.upper(),
                )
            )
        ).scalar_one_or_none()
        if p_row is not None:
            proj_id = p_row

    if proj_id is not None:
        existing_doc = (
            (
                await session.execute(
                    select(Doc.id)
                    .join(ObjectRecord, ObjectRecord.id == Doc.id)
                    .where(
                        Doc.project_id == proj_id,
                        Doc.workspace_id == workspace_id,
                        ObjectRecord.deleted_at.is_(None),
                    )
                    .order_by(ObjectRecord.created_at.asc())
                )
            )
            .scalars()
            .first()
        )
        if existing_doc is not None:
            return existing_doc

        return await _auto_create_root_doc(
            session,
            workspace_id,
            proj_id,
            clean_ref,
            caller_principal_id=caller_principal_id,
        )

    not_found()


async def _resolve_page_id(  # noqa: RET503
    session: AsyncSession,
    workspace_id: uuid.UUID,
    page_ref: str,
) -> uuid.UUID:
    """Resolve page UUID from UUID string or canonical key, falling back to Doc root page."""
    try:
        page_uuid = uuid.UUID(page_ref)
        page = (
            await session.execute(
                select(Page.id).where(
                    Page.id == page_uuid,
                    Page.workspace_id == workspace_id,
                )
            )
        ).scalar_one_or_none()
        if page is not None:
            return page

        # If page_uuid is actually a Doc UUID, resolve to its root page
        doc_root_page = (
            (
                await session.execute(
                    select(Page.id)
                    .where(
                        Page.doc_id == page_uuid,
                        Page.workspace_id == workspace_id,
                    )
                    .order_by(
                        Page.parent_page_id.is_(None).desc(),
                        Page.sort_rank.collate("C").asc(),
                        Page.id.asc(),
                    )
                )
            )
            .scalars()
            .first()
        )
        if doc_root_page is not None:
            return doc_root_page
    except ValueError:
        pass

    clean_ref = page_ref.strip("/")
    ref_with_prefix = f"docs/{clean_ref}" if not clean_ref.startswith("docs/") else clean_ref

    obj_id = (
        await session.execute(
            select(ObjectRecord.id).where(
                ObjectRecord.workspace_id == workspace_id,
                ObjectRecord.object_type == "page",
                ObjectRecord.canonical_key.in_([clean_ref, ref_with_prefix]),
                ObjectRecord.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if obj_id is not None:
        return obj_id

    # If canonical key resolves to a Doc, resolve to its root page
    doc_obj_id = (
        await session.execute(
            select(ObjectRecord.id).where(
                ObjectRecord.workspace_id == workspace_id,
                ObjectRecord.object_type == "doc",
                ObjectRecord.canonical_key.in_([clean_ref, ref_with_prefix]),
                ObjectRecord.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if doc_obj_id is not None:
        doc_root_page = (
            (
                await session.execute(
                    select(Page.id)
                    .where(
                        Page.doc_id == doc_obj_id,
                        Page.workspace_id == workspace_id,
                    )
                    .order_by(
                        Page.parent_page_id.is_(None).desc(),
                        Page.sort_rank.collate("C").asc(),
                        Page.id.asc(),
                    )
                )
            )
            .scalars()
            .first()
        )
        if doc_root_page is not None:
            return doc_root_page

    not_found()


def _capabilities_to_list(caps: Capability) -> list[str]:
    """Convert Capability bitmask to sorted string representation list."""
    res: list[str] = []
    for member in Capability:
        if member.name in ("NONE", "ALL"):
            continue
        if member in caps and member.name:
            res.append(member.name)
    return sorted(res)


# =========================================================================
# DOCS OPERATIONS
# =========================================================================


async def list_docs(
    session: AsyncSession,
    caller: PrincipalContext,
    project_id: uuid.UUID | None = None,
) -> list[DocSummaryResponse]:
    """List documents visible to the caller filtered by workspace and optional project."""
    stmt = (
        select(Doc)
        .join(ObjectRecord, ObjectRecord.id == Doc.id)
        .where(
            Doc.workspace_id == caller.workspace_id,
            ObjectRecord.deleted_at.is_(None),
        )
    )

    if project_id is not None:
        # Require VIEW capability on project
        await require_capability(session, caller, project_id, Capability.VIEW)
        stmt = stmt.where(Doc.project_id == project_id)
    else:
        stmt = stmt.where(Doc.project_id.is_(None))

    stmt = stmt.order_by(Doc.title.asc(), Doc.id.asc())
    docs = (await session.execute(stmt)).scalars().all()

    results: list[DocSummaryResponse] = []
    for d in docs:
        caps = await evaluate_capabilities(session, caller, d.id)
        if Capability.VIEW in caps:
            results.append(
                DocSummaryResponse(
                    id=d.id,
                    canonical_key=d.hierarchy_path,
                    project_id=d.project_id,
                    title=d.title,
                    version_seq=d.version_seq,
                    body_sha256=d.body_sha256.hex() if d.body_sha256 else "",
                )
            )
    return results


async def create_doc(
    session: AsyncSession,
    caller: PrincipalContext,
    body: DocCreate,
) -> tuple[DocResponse, str]:
    """Create a new top-level documentation entity."""
    clean_title = _clean_title(body.title)
    clean_body = _clean_body(body.body_markdown)

    if body.project_id is not None:
        await require_capability(session, caller, body.project_id, Capability.EDIT)

    base_slug = _to_slug(clean_title, "doc")
    canonical_key = await _allocate_unique_canonical_key(
        session, caller.workspace_id, "doc", "docs", base_slug
    )

    async with session.begin_nested():
        doc_id = (
            await session.execute(
                text(
                    "SELECT register_object("
                    "  CAST('doc' AS object_kind), :ws, :proj, :ckey, :title, :creator"
                    ")"
                ),
                {
                    "ws": caller.workspace_id,
                    "proj": body.project_id,
                    "ckey": canonical_key,
                    "title": clean_title,
                    "creator": caller.principal_id,
                },
            )
        ).scalar_one()

        doc = Doc(
            id=doc_id,
            workspace_id=caller.workspace_id,
            project_id=body.project_id,
            title=clean_title,
            body_markdown=clean_body,
            hierarchy_path="pending",  # populated by database trigger docs_hierarchy_bi
        )
        session.add(doc)
        await session.flush()
        await session.refresh(doc)

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=doc.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.DOC_CREATED,
            payload={},
        )

    etag = _format_etag(doc.body_sha256)
    manifest = await build_access_manifest(session, caller, doc.id)
    caps = await evaluate_capabilities(session, caller, doc.id)

    breadcrumbs = [
        BreadcrumbItem(
            id=str(doc.id),
            title=doc.title,
            slug=base_slug,
            canonical_key=canonical_key,
        )
    ]
    outline = [
        OutlineItem(
            level=e.level,
            text=e.text,
            anchor=e.anchor,
            start_line=e.start_line,
        )
        for e in extract_markdown_outline(clean_body)
    ]

    resp = DocResponse(
        id=doc.id,
        canonical_key=canonical_key,
        workspace_id=doc.workspace_id,
        project_id=doc.project_id,
        title=doc.title,
        body_markdown=doc.body_markdown,
        body_sha256=doc.body_sha256.hex() if doc.body_sha256 else "",
        hierarchy_path=doc.hierarchy_path,
        version_seq=doc.version_seq,
        breadcrumbs=breadcrumbs,
        outline=outline,
        access_manifest=manifest.model_dump(),
        capabilities=_capabilities_to_list(caps),
    )
    return resp, etag


async def get_doc(
    session: AsyncSession,
    caller: PrincipalContext,
    doc_ref: str,
) -> tuple[DocResponse, str]:
    """Retrieve full document detail, breadcrumbs, outline, and access metadata."""
    doc_id = await _resolve_doc_id(
        session, caller.workspace_id, doc_ref, caller_principal_id=caller.principal_id
    )
    caps = await require_capability(session, caller, doc_id, Capability.VIEW)

    doc = (
        await session.execute(
            select(Doc, ObjectRecord.canonical_key)
            .join(ObjectRecord, ObjectRecord.id == Doc.id)
            .where(
                Doc.id == doc_id,
                Doc.workspace_id == caller.workspace_id,
                ObjectRecord.deleted_at.is_(None),
            )
        )
    ).first()

    if doc is None:
        not_found()

    doc_obj, canonical_key = doc
    etag = _format_etag(doc_obj.body_sha256)
    manifest = await build_access_manifest(session, caller, doc_id)

    slug = canonical_key.split("/")[-1]
    breadcrumbs = [
        BreadcrumbItem(
            id=str(doc_obj.id),
            title=doc_obj.title,
            slug=slug,
            canonical_key=canonical_key,
        )
    ]
    outline = [
        OutlineItem(
            level=e.level,
            text=e.text,
            anchor=e.anchor,
            start_line=e.start_line,
        )
        for e in extract_markdown_outline(doc_obj.body_markdown)
    ]

    resp = DocResponse(
        id=doc_obj.id,
        canonical_key=canonical_key,
        workspace_id=doc_obj.workspace_id,
        project_id=doc_obj.project_id,
        title=doc_obj.title,
        body_markdown=doc_obj.body_markdown,
        body_sha256=doc_obj.body_sha256.hex() if doc_obj.body_sha256 else "",
        hierarchy_path=doc_obj.hierarchy_path,
        version_seq=doc_obj.version_seq,
        breadcrumbs=breadcrumbs,
        outline=outline,
        access_manifest=manifest.model_dump(),
        capabilities=_capabilities_to_list(caps),
    )
    return resp, etag


async def update_doc(
    session: AsyncSession,
    caller: PrincipalContext,
    doc_ref: str,
    body: DocUpdate,
    if_match: str | None,
) -> tuple[DocResponse, str]:
    """Update document title or body markdown under optimistic concurrency."""
    doc_id = await _resolve_doc_id(
        session, caller.workspace_id, doc_ref, caller_principal_id=caller.principal_id
    )
    await require_capability(session, caller, doc_id, Capability.EDIT)

    doc_row = (
        await session.execute(
            select(Doc).where(Doc.id == doc_id, Doc.workspace_id == caller.workspace_id)
        )
    ).scalar_one_or_none()

    if doc_row is None:
        not_found()

    old_sha = doc_row.body_sha256.hex() if doc_row.body_sha256 else ""

    if body.body_markdown is not None:
        _verify_if_match(if_match, doc_row.body_sha256)
        doc_row.body_markdown = _clean_body(body.body_markdown)

    if body.title is not None:
        clean_title = _clean_title(body.title)
        doc_row.title = clean_title
        await session.execute(
            text("UPDATE objects SET display_title = :t WHERE id = :id"),
            {"t": clean_title, "id": doc_id},
        )

    await session.flush()
    await session.refresh(doc_row)

    new_sha = doc_row.body_sha256.hex() if doc_row.body_sha256 else ""
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=doc_row.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.DOC_UPDATED,
        payload={
            "old_sha256": old_sha,
            "new_sha256": new_sha,
            "version_seq": doc_row.version_seq,
        },
    )

    return await get_doc(session, caller, str(doc_id))


async def delete_doc(
    session: AsyncSession,
    caller: PrincipalContext,
    doc_ref: str,
) -> None:
    """Soft-trash document and all hierarchical pages."""
    doc_id = await _resolve_doc_id(
        session, caller.workspace_id, doc_ref, caller_principal_id=caller.principal_id
    )
    await require_capability(session, caller, doc_id, Capability.DELETE)

    # Soft trash doc in objects
    await session.execute(
        text("UPDATE objects SET deleted_at = clock_timestamp() WHERE id = :id"),
        {"id": doc_id},
    )
    # Soft trash all pages of this doc
    await session.execute(
        text(
            "UPDATE objects SET deleted_at = clock_timestamp() "
            "WHERE id IN (SELECT id FROM pages WHERE doc_id = :did)"
        ),
        {"did": doc_id},
    )

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=doc_id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.DOC_TRASHED,
        payload={},
    )


async def get_doc_tree(
    session: AsyncSession,
    caller: PrincipalContext,
    doc_ref: str,
) -> list[PageTreeNode]:
    """Retrieve full hierarchical page tree with restricted ancestor masking."""
    doc_id = await _resolve_doc_id(
        session, caller.workspace_id, doc_ref, caller_principal_id=caller.principal_id
    )
    await require_capability(session, caller, doc_id, Capability.VIEW)

    rows = (
        await session.execute(
            select(
                Page.id,
                Page.parent_page_id,
                Page.title,
                Page.sort_rank,
                ObjectRecord.canonical_key,
                Page.hierarchy_path,
            )
            .join(ObjectRecord, ObjectRecord.id == Page.id)
            .where(
                Page.doc_id == doc_id,
                Page.workspace_id == caller.workspace_id,
                ObjectRecord.deleted_at.is_(None),
            )
            .order_by(Page.sort_rank.collate("C").asc(), Page.id.asc())
        )
    ).all()

    page_map: dict[uuid.UUID, dict[str, Any]] = {}
    children_map: dict[uuid.UUID | None, list[uuid.UUID]] = {}

    for row in rows:
        pid, parent_id, title, sort_rank, ckey, hpath = row
        caps = await evaluate_capabilities(session, caller, pid)
        slug = ckey.split("/")[-1]
        page_map[pid] = {
            "id": pid,
            "parent_id": parent_id,
            "title": title,
            "slug": slug,
            "sort_rank": sort_rank,
            "can_view": Capability.VIEW in caps,
            "restricted": False,
        }

        # Synthesize restricted ancestor nodes if hidden by RLS
        ancestors = _extract_ancestor_uuids(hpath)
        prev_aid: uuid.UUID | None = None
        for aid in ancestors:
            if aid not in page_map:
                page_map[aid] = {
                    "id": aid,
                    "parent_id": prev_aid,
                    "title": None,
                    "slug": None,
                    "sort_rank": "",
                    "can_view": False,
                    "restricted": True,
                }
                c_list = children_map.setdefault(prev_aid, [])
                if aid not in c_list:
                    c_list.append(aid)
            prev_aid = aid

        effective_parent = parent_id if (parent_id is None or parent_id in page_map) else prev_aid
        c_list = children_map.setdefault(effective_parent, [])
        if pid not in c_list:
            c_list.append(pid)

    def _build_nodes(parent_id: uuid.UUID | None) -> list[PageTreeNode]:
        nodes: list[PageTreeNode] = []
        for child_id in children_map.get(parent_id, []):
            info = page_map[child_id]
            child_nodes = _build_nodes(child_id)
            if info["can_view"]:
                nodes.append(
                    PageTreeNode(
                        id=str(info["id"]),
                        title=info["title"],
                        slug=info["slug"],
                        sort_rank=info["sort_rank"],
                        children=child_nodes,
                    )
                )
            else:
                # Mask restricted ancestor with zero id/title/slug leakage
                nodes.append(
                    PageTreeNode(
                        restricted=True,
                        label="🔒 Restricted Page",
                        children=child_nodes,
                    )
                )
        return nodes

    return _build_nodes(None)


# =========================================================================
# PAGES OPERATIONS
# =========================================================================


async def _validate_parent_page(
    session: AsyncSession,
    caller: PrincipalContext,
    parent_page_id: uuid.UUID | None,
    doc_id: uuid.UUID,
) -> None:
    """Ensure parent page exists, belongs to same doc, and caller has edit capability."""
    if parent_page_id is None:
        return
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
    if parent_page.doc_id != doc_id:
        raise ProblemException(
            code="PAGE_PARENT_DOC_MISMATCH",
            status=422,
            title="Parent Doc Mismatch",
            detail="Parent page must belong to the same document",
        )


def _compute_new_sort_rank(
    siblings: Sequence[Any],
    after_id: uuid.UUID | None,
    before_id: uuid.UUID | None,
) -> str:
    """Calculate the midpoint sort_rank among siblings given optional relative positioning."""
    prev_rank: str | None = None
    next_rank: str | None = None

    if after_id:
        for idx, (sid, srank) in enumerate(siblings):
            if sid == after_id:
                prev_rank = srank
                if idx + 1 < len(siblings):
                    next_rank = siblings[idx + 1][1]
                break
    elif before_id:
        for idx, (sid, srank) in enumerate(siblings):
            if sid == before_id:
                next_rank = srank
                if idx > 0:
                    prev_rank = siblings[idx - 1][1]
                break
    elif siblings:
        prev_rank = siblings[-1][1]

    return midpoint_rank(prev_rank, next_rank)


def _handle_page_db_error(exc: DBAPIError) -> None:
    """Translate Postgres page trigger/hierarchy exceptions to API problems."""
    err_str = str(exc)
    if "PAGE_MAX_DEPTH_EXCEEDED" in err_str:
        raise ProblemException(
            code="PAGE_MAX_DEPTH_EXCEEDED",
            status=422,
            title="Max Depth Exceeded",
            detail="Page hierarchy depth cannot exceed 10",
        ) from exc
    if "PAGE_CYCLE" in err_str:
        raise ProblemException(
            code="PAGE_CYCLE",
            status=409,
            title="Page Cycle",
            detail="Hierarchy cycle detected",
        ) from exc
    if "PAGE_PARENT_DOC_MISMATCH" in err_str:
        raise ProblemException(
            code="PAGE_PARENT_DOC_MISMATCH",
            status=422,
            title="Parent Doc Mismatch",
            detail="Parent page must belong to the same document",
        ) from exc
    raise exc


async def create_page(
    session: AsyncSession,
    caller: PrincipalContext,
    doc_ref: str,
    body: PageCreate,
) -> tuple[PageResponse, str]:
    """Create a hierarchical page within a document."""
    doc_id = await _resolve_doc_id(
        session, caller.workspace_id, doc_ref, caller_principal_id=caller.principal_id
    )
    await require_capability(session, caller, doc_id, Capability.EDIT)
    await _validate_parent_page(session, caller, body.parent_page_id, doc_id)

    clean_title = _clean_title(body.title)
    clean_body = _clean_body(body.body_markdown)

    # Determine doc canonical key prefix
    doc_obj = (
        await session.execute(
            select(Doc, ObjectRecord.canonical_key)
            .join(ObjectRecord, ObjectRecord.id == Doc.id)
            .where(Doc.id == doc_id)
        )
    ).first()
    if doc_obj is None:
        not_found()
    doc_entity, doc_ckey = doc_obj

    base_slug = _to_slug(clean_title, "page")
    canonical_key = await _allocate_unique_canonical_key(
        session, caller.workspace_id, "page", doc_ckey, base_slug
    )

    # Compute sort_rank
    siblings = (
        await session.execute(
            select(Page.id, Page.sort_rank)
            .where(
                Page.doc_id == doc_id,
                Page.parent_page_id == body.parent_page_id,
            )
            .order_by(Page.sort_rank.collate("C").asc(), Page.id.asc())
        )
    ).all()

    new_rank = _compute_new_sort_rank(siblings, body.after_page_id, body.before_page_id)

    async with session.begin_nested():
        page_id = (
            await session.execute(
                text(
                    "SELECT register_object("
                    "  CAST('page' AS object_kind), :ws, :proj, :ckey, :title, :creator"
                    ")"
                ),
                {
                    "ws": caller.workspace_id,
                    "proj": doc_entity.project_id,
                    "ckey": canonical_key,
                    "title": clean_title,
                    "creator": caller.principal_id,
                },
            )
        ).scalar_one()

        page = Page(
            id=page_id,
            workspace_id=caller.workspace_id,
            doc_id=doc_id,
            parent_page_id=body.parent_page_id,
            title=clean_title,
            body_markdown=clean_body,
            sort_rank=new_rank,
            hierarchy_path="pending",  # populated by pages_hierarchy_biu trigger
        )
        session.add(page)

        try:
            await session.flush()
            await session.refresh(page)
        except DBAPIError as exc:
            _handle_page_db_error(exc)

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=page.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.PAGE_CREATED,
            payload={},
        )

    return await get_page(session, caller, str(page.id))


async def get_page(
    session: AsyncSession,
    caller: PrincipalContext,
    page_ref: str,
) -> tuple[PageResponse, str]:
    """Retrieve full page detail, breadcrumbs, outline, and access metadata."""
    page_id = await _resolve_page_id(session, caller.workspace_id, page_ref)
    caps = await require_capability(session, caller, page_id, Capability.VIEW)

    page_row = (
        await session.execute(
            select(Page, ObjectRecord.canonical_key)
            .join(ObjectRecord, ObjectRecord.id == Page.id)
            .where(
                Page.id == page_id,
                Page.workspace_id == caller.workspace_id,
                ObjectRecord.deleted_at.is_(None),
            )
        )
    ).first()

    if page_row is None:
        not_found()

    page_obj, canonical_key = page_row
    etag = _format_etag(page_obj.body_sha256)
    manifest = await build_access_manifest(session, caller, page_id)

    # Build ancestor breadcrumbs
    doc_row = (
        await session.execute(
            select(Doc.id, Doc.title, ObjectRecord.canonical_key)
            .join(ObjectRecord, ObjectRecord.id == Doc.id)
            .where(Doc.id == page_obj.doc_id)
        )
    ).first()

    breadcrumbs: list[BreadcrumbItem] = []
    if doc_row is not None:
        d_id, d_title, d_ckey = doc_row
        d_caps = await evaluate_capabilities(session, caller, d_id)
        if Capability.VIEW in d_caps:
            breadcrumbs.append(
                BreadcrumbItem(
                    id=str(d_id),
                    title=d_title,
                    slug=d_ckey.split("/")[-1],
                    canonical_key=d_ckey,
                )
            )
        else:
            breadcrumbs.append(BreadcrumbItem(restricted=True, label="🔒 Restricted Page"))

    # Parse ancestors from ltree hierarchy_path
    ancestor_ids = _extract_ancestor_uuids(page_obj.hierarchy_path)

    for aid in ancestor_ids:
        acaps = await evaluate_capabilities(session, caller, aid)
        if Capability.VIEW in acaps:
            arow = (
                await session.execute(
                    select(Page.title, ObjectRecord.canonical_key)
                    .join(ObjectRecord, ObjectRecord.id == Page.id)
                    .where(Page.id == aid)
                )
            ).first()
            if arow is not None:
                atitle, ackey = arow
                breadcrumbs.append(
                    BreadcrumbItem(
                        id=str(aid),
                        title=atitle,
                        slug=ackey.split("/")[-1],
                        canonical_key=ackey,
                    )
                )
            else:
                breadcrumbs.append(BreadcrumbItem(restricted=True, label="🔒 Restricted Page"))
        else:
            breadcrumbs.append(BreadcrumbItem(restricted=True, label="🔒 Restricted Page"))

    # Add current page
    slug = canonical_key.split("/")[-1]
    breadcrumbs.append(
        BreadcrumbItem(
            id=str(page_obj.id),
            title=page_obj.title,
            slug=slug,
            canonical_key=canonical_key,
        )
    )

    outline = [
        OutlineItem(
            level=e.level,
            text=e.text,
            anchor=e.anchor,
            start_line=e.start_line,
        )
        for e in extract_markdown_outline(page_obj.body_markdown)
    ]

    resp = PageResponse(
        id=page_obj.id,
        canonical_key=canonical_key,
        doc_id=page_obj.doc_id,
        parent_page_id=page_obj.parent_page_id,
        workspace_id=page_obj.workspace_id,
        title=page_obj.title,
        body_markdown=page_obj.body_markdown,
        body_sha256=page_obj.body_sha256.hex() if page_obj.body_sha256 else "",
        hierarchy_path=page_obj.hierarchy_path,
        version_seq=page_obj.version_seq,
        sort_rank=page_obj.sort_rank,
        breadcrumbs=breadcrumbs,
        outline=outline,
        access_manifest=manifest.model_dump(),
        capabilities=_capabilities_to_list(caps),
    )
    return resp, etag


async def update_page(
    session: AsyncSession,
    caller: PrincipalContext,
    page_ref: str,
    body: PageUpdate,
    if_match: str | None,
) -> tuple[PageResponse, str]:
    """Update page title or body markdown under optimistic concurrency."""
    page_id = await _resolve_page_id(session, caller.workspace_id, page_ref)
    await require_capability(session, caller, page_id, Capability.EDIT)

    page_row = (
        await session.execute(
            select(Page).where(Page.id == page_id, Page.workspace_id == caller.workspace_id)
        )
    ).scalar_one_or_none()

    if page_row is None:
        not_found()

    old_sha = page_row.body_sha256.hex() if page_row.body_sha256 else ""

    if body.body_markdown is not None:
        _verify_if_match(if_match, page_row.body_sha256)
        page_row.body_markdown = _clean_body(body.body_markdown)

    if body.title is not None:
        clean_title = _clean_title(body.title)
        page_row.title = clean_title
        await session.execute(
            text("UPDATE objects SET display_title = :t WHERE id = :id"),
            {"t": clean_title, "id": page_id},
        )

    await session.flush()
    await session.refresh(page_row)

    new_sha = page_row.body_sha256.hex() if page_row.body_sha256 else ""
    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=page_row.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.PAGE_UPDATED,
        payload={
            "old_sha256": old_sha,
            "new_sha256": new_sha,
            "version_seq": page_row.version_seq,
        },
    )

    return await get_page(session, caller, str(page_id))


async def move_page(
    session: AsyncSession,
    caller: PrincipalContext,
    page_ref: str,
    body: PageMove,
) -> PageResponse:
    """Move a page to a new parent or re-order among siblings."""
    page_id = await _resolve_page_id(session, caller.workspace_id, page_ref)
    await require_capability(session, caller, page_id, Capability.EDIT)

    page_row = (
        await session.execute(
            select(Page).where(Page.id == page_id, Page.workspace_id == caller.workspace_id)
        )
    ).scalar_one_or_none()

    if page_row is None:
        not_found()

    await _validate_parent_page(session, caller, body.parent_page_id, page_row.doc_id)

    old_parent_id = page_row.parent_page_id
    new_parent_id = body.parent_page_id

    # Compute sort_rank among target siblings
    target_siblings = (
        await session.execute(
            select(Page.id, Page.sort_rank)
            .where(
                Page.doc_id == page_row.doc_id,
                Page.parent_page_id == new_parent_id,
                Page.id != page_id,
            )
            .order_by(Page.sort_rank.collate("C").asc(), Page.id.asc())
        )
    ).all()

    new_rank = _compute_new_sort_rank(target_siblings, body.after_page_id, body.before_page_id)

    async with session.begin_nested():
        page_row.parent_page_id = new_parent_id
        page_row.sort_rank = new_rank

        try:
            await session.flush()
            await session.refresh(page_row)
        except DBAPIError as exc:
            _handle_page_db_error(exc)

        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=page_row.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.PAGE_MOVED,
            payload={
                "old_parent_id": str(old_parent_id) if old_parent_id else None,
                "new_parent_id": str(new_parent_id) if new_parent_id else None,
                "new_sort_rank": page_row.sort_rank,
            },
        )

    resp, _ = await get_page(session, caller, str(page_id))
    return resp


async def delete_page(
    session: AsyncSession,
    caller: PrincipalContext,
    page_ref: str,
) -> None:
    """Soft-trash page and all its hierarchical descendants."""
    page_id = await _resolve_page_id(session, caller.workspace_id, page_ref)
    await require_capability(session, caller, page_id, Capability.DELETE)

    page_row = (
        await session.execute(
            select(Page).where(Page.id == page_id, Page.workspace_id == caller.workspace_id)
        )
    ).scalar_one_or_none()

    if page_row is None:
        not_found()

    # Soft trash page and descendants in objects
    await session.execute(
        text(
            "UPDATE objects SET deleted_at = clock_timestamp() "
            "WHERE id IN ("
            "  SELECT id FROM pages WHERE hierarchy_path <@ cast(:path as ltree)"
            ")"
        ),
        {"path": page_row.hierarchy_path},
    )

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=page_id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.PAGE_TRASHED,
        payload={},
    )


async def list_page_versions(
    session: AsyncSession,
    caller: PrincipalContext,
    page_ref: str,
    cursor: int | None = None,
    limit: int = 50,
) -> list[PageVersionResponse]:
    """List historical version snapshots of a page."""
    page_id = await _resolve_page_id(session, caller.workspace_id, page_ref)
    await require_capability(session, caller, page_id, Capability.VIEW)

    stmt = select(PageVersion).where(
        PageVersion.page_id == page_id,
        PageVersion.workspace_id == caller.workspace_id,
    )
    if cursor is not None:
        stmt = stmt.where(PageVersion.version_seq < cursor)

    stmt = stmt.order_by(PageVersion.version_seq.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()

    return [
        PageVersionResponse(
            page_id=r.page_id,
            version_seq=r.version_seq,
            title=r.title,
            body_markdown=r.body_markdown,
            body_sha256=r.body_sha256.hex() if r.body_sha256 else "",
            created_by_id=r.created_by_id,
            created_at=r.created_at,
        )
        for r in rows
    ]


async def get_page_version(
    session: AsyncSession,
    caller: PrincipalContext,
    page_ref: str,
    version_seq: int,
) -> PageVersionResponse:
    """Retrieve a single historical version snapshot of a page."""
    page_id = await _resolve_page_id(session, caller.workspace_id, page_ref)
    await require_capability(session, caller, page_id, Capability.VIEW)

    version_row = (
        await session.execute(
            select(PageVersion).where(
                PageVersion.page_id == page_id,
                PageVersion.version_seq == version_seq,
                PageVersion.workspace_id == caller.workspace_id,
            )
        )
    ).scalar_one_or_none()

    if version_row is None:
        not_found()

    return PageVersionResponse(
        page_id=version_row.page_id,
        version_seq=version_row.version_seq,
        title=version_row.title,
        body_markdown=version_row.body_markdown,
        body_sha256=version_row.body_sha256.hex() if version_row.body_sha256 else "",
        created_by_id=version_row.created_by_id,
        created_at=version_row.created_at,
    )


async def restore_page_version(
    session: AsyncSession,
    caller: PrincipalContext,
    page_ref: str,
    version_seq: int,
    if_match: str | None,
) -> tuple[PageResponse, str]:
    """Restore historical version content into the current page under If-Match concurrency."""
    page_id = await _resolve_page_id(session, caller.workspace_id, page_ref)
    await require_capability(session, caller, page_id, Capability.EDIT)

    page_row = (
        await session.execute(
            select(Page).where(Page.id == page_id, Page.workspace_id == caller.workspace_id)
        )
    ).scalar_one_or_none()

    if page_row is None:
        not_found()

    _verify_if_match(if_match, page_row.body_sha256)

    historical = (
        await session.execute(
            select(PageVersion).where(
                PageVersion.page_id == page_id,
                PageVersion.version_seq == version_seq,
                PageVersion.workspace_id == caller.workspace_id,
            )
        )
    ).scalar_one_or_none()

    if historical is None:
        not_found()

    page_row.title = historical.title
    page_row.body_markdown = historical.body_markdown

    await session.flush()
    await session.refresh(page_row)

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=page_row.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.PAGE_VERSION_RESTORED,
        payload={
            "restored_from_seq": version_seq,
            "new_version_seq": page_row.version_seq,
        },
    )

    return await get_page(session, caller, str(page_id))
