"""Object links service: creation, listing with masking, deletion, and canonical URLs.

Traceability: Spec S7.2 8m, S12.1, S12.3.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from database.models import LinkKind, ObjectLink, ObjectRecord
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.links import (
    CanonicalUrlResponse,
    EndpointOut,
    InboundLinkOut,
    LinkCreateRequest,
    LinksListResponse,
    OutboundLinkOut,
    RestrictedEndpointOut,
    UnrestrictedEndpointOut,
)
from kanban.security.granular_permissions import GranularPermission, require_permissions
from kanban.security.permissions import Capability, evaluate_capabilities
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.object_ref import resolve_object_ref

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext
    from kanban.settings import Settings

MAX_LINKS_PER_DIRECTION: Final[int] = 500

USER_CREATABLE_LINK_KINDS: Final[frozenset[str]] = frozenset(
    {
        "BLOCKS",
        "BLOCKED_BY",
        "RELATES_TO",
        "DUPLICATES",
        "VERIFIED_BY_DOC",
        "DERIVED_FROM_STICKY",
    }
)

SYSTEM_LINK_KINDS: Final[frozenset[str]] = frozenset(
    {
        "PARENT_OF",
        "ASSIGNED_TO",
        "IN_CYCLE",
        "IN_MODULE",
        "PROMOTED_TO_DOC",
        "EMBEDS_OBJECT",
        "GOVERNED_BY_VIEW",
        "IMPLEMENTED_IN_PR",
        "REFERENCED_BY_COMMIT",
        "TRACKED_ON_BRANCH",
    }
)


async def list_object_links(
    session: AsyncSession,
    caller: PrincipalContext,
    obj: ObjectRecord,
    *,
    max_links: int = MAX_LINKS_PER_DIRECTION,
) -> LinksListResponse:
    """List inbound and outbound typed links for an object with restricted-target masking."""
    # 1. Fetch up to max_links + 1 in each direction to check truncation
    stmt_out = (
        select(ObjectLink)
        .where(ObjectLink.source_id == obj.id)
        .order_by(ObjectLink.created_at.asc())
        .limit(max_links + 1)
    )
    stmt_in = (
        select(ObjectLink)
        .where(ObjectLink.target_id == obj.id)
        .order_by(ObjectLink.created_at.asc())
        .limit(max_links + 1)
    )

    out_links = list((await session.execute(stmt_out)).scalars().all())
    in_links = list((await session.execute(stmt_in)).scalars().all())

    truncated = False
    if len(out_links) > max_links:
        truncated = True
        out_links = out_links[:max_links]
    if len(in_links) > max_links:
        truncated = True
        in_links = in_links[:max_links]

    # 2. Collect all far endpoint IDs
    far_ids = {link.target_id for link in out_links} | {link.source_id for link in in_links}

    # 3. Batch fetch far endpoints visible under caller's RLS session
    readable_map: dict[uuid.UUID, ObjectRecord] = {}
    if far_ids:
        stmt_far = select(ObjectRecord).where(
            ObjectRecord.id.in_(far_ids),
            ObjectRecord.deleted_at.is_(None),
        )
        for row in (await session.execute(stmt_far)).scalars().all():
            caps = await evaluate_capabilities(session, caller, row.id)
            if Capability.VIEW in caps:
                readable_map[row.id] = row

    # 4. Construct outbound link list
    outbound_list: list[OutboundLinkOut] = []
    for link in out_links:
        endpoint_out: EndpointOut
        if link.target_id in readable_map:
            t_rec = readable_map[link.target_id]
            endpoint_out = UnrestrictedEndpointOut(
                id=t_rec.id,
                type=t_rec.object_type.value,
                key=t_rec.canonical_key,
                title=t_rec.display_title,
            )
        else:
            endpoint_out = RestrictedEndpointOut()
        outbound_list.append(
            OutboundLinkOut(
                id=link.id,
                link_type=link.link_type.value,
                link_state=link.link_state,
                target=endpoint_out,
            )
        )

    # 5. Construct inbound link list
    inbound_list: list[InboundLinkOut] = []
    for link in in_links:
        if link.source_id in readable_map:
            s_rec = readable_map[link.source_id]
            endpoint_out = UnrestrictedEndpointOut(
                id=s_rec.id,
                type=s_rec.object_type.value,
                key=s_rec.canonical_key,
                title=s_rec.display_title,
            )
        else:
            endpoint_out = RestrictedEndpointOut()
        inbound_list.append(
            InboundLinkOut(
                id=link.id,
                link_type=link.link_type.value,
                link_state=link.link_state,
                source=endpoint_out,
            )
        )

    return LinksListResponse(outbound=outbound_list, inbound=inbound_list, truncated=truncated)


def _validate_user_creatable_kind(link_type_str: str) -> LinkKind:
    """Validate requested link type is user-creatable under Spec S7.2 8m."""
    if link_type_str in SYSTEM_LINK_KINDS:
        raise ProblemException(
            code="LINK_TYPE_NOT_USER_CREATABLE",
            status=422,
            title="Link Type Not User Creatable",
            detail=(
                f"Link type '{link_type_str}' is managed by the system and "
                "cannot be created directly"
            ),
        )

    if link_type_str not in USER_CREATABLE_LINK_KINDS:
        raise ProblemException(
            code="LINK_TYPE_NOT_ALLOWED",
            status=422,
            title="Link Type Not Allowed",
            detail=f"Link type '{link_type_str}' is not permitted",
        )

    return LinkKind(link_type_str)


async def _assert_link_matrix_allowed(
    session: AsyncSession,
    source: ObjectRecord,
    target: ObjectRecord,
    link_kind: LinkKind,
) -> None:
    """Validate (source_type, link_type, target_type) exists in link_type_matrix."""
    matrix_stmt = text(
        "SELECT 1 FROM link_type_matrix "
        "WHERE source_type = :st AND link_type = :lt AND target_type = :tt "
        "AND is_user_creatable = TRUE"
    )
    matrix_row = (
        await session.execute(
            matrix_stmt,
            {
                "st": source.object_type.value,
                "lt": link_kind.value,
                "tt": target.object_type.value,
            },
        )
    ).scalar_one_or_none()

    if matrix_row is None:
        raise ProblemException(
            code="LINK_TYPE_NOT_ALLOWED",
            status=422,
            title="Link Type Not Allowed",
            detail=(
                f"Link type '{link_kind.value}' is not permitted between "
                f"'{source.object_type.value}' and '{target.object_type.value}'"
            ),
        )


async def create_object_link(  # noqa: C901
    session: AsyncSession,
    caller: PrincipalContext,
    source: ObjectRecord,
    req: LinkCreateRequest,
) -> OutboundLinkOut:
    """Validate and insert a typed object link, emitting two LINK_CREATED activity events."""
    link_kind = _validate_user_creatable_kind(req.link_type.strip())

    # 1. Caller capability on source: require LINK
    source_caps = await evaluate_capabilities(session, caller, source.id)
    if Capability.VIEW not in source_caps:
        not_found()
    if Capability.LINK not in source_caps:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail=None,
        )

    if str(source.object_type).lower() == "issue":
        await require_permissions(
            session,
            caller,
            source.workspace_id,
            {GranularPermission.ISSUE_LINK.value},
            project_id=source.project_id,
            object_readable=True,
        )

    # 2. Resolve target through caller's RLS session
    target = await resolve_object_ref(session, req.target)
    if target is None or target.workspace_id != source.workspace_id:
        raise ProblemException(
            code="TARGET_NOT_FOUND",
            status=422,
            title="Target Not Found",
            detail="Target object does not exist or is not readable",
        )

    target_caps = await evaluate_capabilities(session, caller, target.id)
    if Capability.VIEW not in target_caps:
        raise ProblemException(
            code="TARGET_NOT_FOUND",
            status=422,
            title="Target Not Found",
            detail="Target object does not exist or is not readable",
        )

    # 3. Self-link check -> 422 SELF_LINK
    if source.id == target.id:
        raise ProblemException(
            code="SELF_LINK",
            status=422,
            title="Self Link Not Allowed",
            detail="An object cannot be linked to itself",
        )

    # 4. Matrix allowlist validation -> 422 LINK_TYPE_NOT_ALLOWED
    await _assert_link_matrix_allowed(session, source, target, link_kind)

    # 5. Duplicate link check -> 409 LINK_EXISTS
    dup_stmt = select(ObjectLink.id).where(
        ObjectLink.source_id == source.id,
        ObjectLink.target_id == target.id,
        ObjectLink.link_type == link_kind,
    )
    if (await session.execute(dup_stmt)).scalar_one_or_none() is not None:
        raise ProblemException(
            code="LINK_EXISTS",
            status=409,
            title="Link Already Exists",
            detail="A link of this type already exists between the source and target objects",
        )

    # 6. Insert link into object_links
    new_link = ObjectLink(
        workspace_id=source.workspace_id,
        source_id=source.id,
        source_type=source.object_type,
        target_id=target.id,
        target_type=target.object_type,
        link_type=link_kind,
        link_state="ACTIVE",
        source_key_snapshot=source.canonical_key,
        target_key_snapshot=target.canonical_key,
        created_by_id=caller.principal_id,
    )
    session.add(new_link)
    try:
        await session.flush()
    except IntegrityError as exc:
        orig_msg = str(exc.orig) if hasattr(exc, "orig") else str(exc)
        if "LINK_TYPE_NOT_ALLOWED" in orig_msg:
            raise ProblemException(
                code="LINK_TYPE_NOT_ALLOWED",
                status=422,
                title="Link Type Not Allowed",
                detail="The requested link type is not permitted",
            ) from exc
        if "23505" in orig_msg or "unique" in orig_msg.lower():
            raise ProblemException(
                code="LINK_EXISTS",
                status=409,
                title="Link Already Exists",
                detail="A link of this type already exists between the source and target objects",
            ) from exc
        raise

    # 7. Emit LINK_CREATED activity records (source and target)
    activity_payload = {
        "link_id": str(new_link.id),
        "link_type": new_link.link_type.value,
        "source_id": str(new_link.source_id),
        "target_id": str(new_link.target_id),
    }
    await record_activity(
        session,
        workspace_id=source.workspace_id,
        object_id=source.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.LINK_CREATED,
        payload=activity_payload,
    )
    await record_activity(
        session,
        workspace_id=target.workspace_id,
        object_id=target.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.LINK_CREATED,
        payload=activity_payload,
    )

    return OutboundLinkOut(
        id=new_link.id,
        link_type=new_link.link_type.value,
        link_state=new_link.link_state,
        target=UnrestrictedEndpointOut(
            id=target.id,
            type=target.object_type.value,
            key=target.canonical_key,
            title=target.display_title,
        ),
    )


async def delete_object_link(
    session: AsyncSession,
    caller: PrincipalContext,
    link_id: uuid.UUID,
) -> None:
    """Delete a typed object link, requiring LINK on source and anti-enumeration 404."""
    # 1. Fetch link
    link = await session.get(ObjectLink, link_id)
    if link is None:
        not_found()

    # 2. Anti-enumeration: if source object is unreadable or deleted, return 404
    stmt_src = select(ObjectRecord).where(
        ObjectRecord.id == link.source_id,
        ObjectRecord.deleted_at.is_(None),
    )
    source_rec = (await session.execute(stmt_src)).scalar_one_or_none()
    if source_rec is None:
        not_found()

    # 3. Check caller capabilities on source: require LINK
    caps = await evaluate_capabilities(session, caller, source_rec.id)
    if Capability.VIEW not in caps:
        not_found()
    if Capability.LINK not in caps:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail=None,
        )

    if str(source_rec.object_type).lower() == "issue":
        await require_permissions(
            session,
            caller,
            source_rec.workspace_id,
            {GranularPermission.ISSUE_LINK.value},
            project_id=source_rec.project_id,
            object_readable=True,
        )

    # 4. Guard: Flagged invalid links require audited purge (S12.3, KB-P1-16)
    if link.link_state == "FLAGGED_INVALID":
        raise ProblemException(
            code="FLAGGED_LINK_REQUIRES_AUDITED_PURGE",
            status=422,
            title="Flagged Link Requires Audited Purge",
            detail="Flagged invalid links cannot be directly deleted and require audited purge",
        )

    # 5. Delete the link
    await session.delete(link)
    await session.flush()

    # 6. Emit LINK_DELETED activity events
    activity_payload = {
        "link_id": str(link.id),
        "link_type": link.link_type.value,
        "source_id": str(link.source_id),
        "target_id": str(link.target_id),
    }
    await record_activity(
        session,
        workspace_id=link.workspace_id,
        object_id=link.source_id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.LINK_DELETED,
        payload=activity_payload,
    )

    # If target is visible and caller holds VIEW, write activity to target as well
    stmt_tgt = select(ObjectRecord).where(
        ObjectRecord.id == link.target_id,
        ObjectRecord.deleted_at.is_(None),
    )
    target_rec = (await session.execute(stmt_tgt)).scalar_one_or_none()
    if target_rec is not None:
        target_caps = await evaluate_capabilities(session, caller, link.target_id)
        if Capability.VIEW in target_caps:
            await record_activity(
                session,
                workspace_id=link.workspace_id,
                object_id=link.target_id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.LINK_DELETED,
                payload=activity_payload,
            )


def build_canonical_url(
    settings: Settings,
    obj: ObjectRecord,
) -> CanonicalUrlResponse:
    """Generate server-authoritative canonical URL and escaped Markdown link."""
    base_url = settings.public_base_url.rstrip("/")

    # Construct object-specific URL path
    if "-" in obj.canonical_key:
        proj_ident = obj.canonical_key.split("-", 1)[0]
    else:
        proj_ident = obj.canonical_key

    if obj.object_type.value == "issue":
        path = f"/projects/{proj_ident}/issues/{obj.canonical_key}"
    elif obj.object_type.value == "project":
        path = f"/projects/{obj.canonical_key}"
    elif obj.object_type.value in ("doc", "page"):
        if obj.project_id is not None:
            path = f"/projects/{proj_ident}/docs/{obj.canonical_key}"
        else:
            path = f"/docs/{obj.canonical_key}"
    elif obj.object_type.value == "sticky":
        path = f"/stickies/{obj.canonical_key}"
    else:
        path = f"/{obj.object_type.value}s/{obj.canonical_key}"

    full_url = f"{base_url}{path}"
    # Escape markdown link characters []() in the key
    escaped_key = re.sub(r"([\[\]\(\)])", r"\\\1", obj.canonical_key)
    markdown = f"[{escaped_key}]({full_url})"

    return CanonicalUrlResponse(url=full_url, markdown=markdown)
