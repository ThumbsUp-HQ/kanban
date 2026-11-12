"""Service layer for saved views CRUD and query dispatch (S6.4, S3.4)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final

from pydantic import ValidationError
from sqlalchemy import delete, select, text

from database.models import (
    ObjectRecord,
    Principal,
    Project,
    View,
)
from database.models import (
    ViewLayout as DbViewLayout,
)
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.views import (
    AdHocQueryRequest,
    FilterSpec,
    GroupAxis,
    SortDir,
    SortField,
    ViewCreate,
    ViewLayout,
    ViewList,
    ViewOwnerSummary,
    ViewPatch,
    ViewQueryResponse,
    ViewResponse,
)
from kanban.content import ContentNormalizeError, normalize_to_markdown
from kanban.security.access_manifest import build_access_manifest
from kanban.security.permissions import (
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
    require_capability,
)
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.projects import get_project_or_404
from kanban.services.query_engine import execute_view_query
from kanban.services.view_dsl import validate_group_axes

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

MAX_VIEW_DESCRIPTION_BYTES: Final[int] = 16384
MAX_QUERY_LIMIT: Final[int] = 200
_ALLOWED_DB_FILTER_KEYS: Final[set[str]] = {
    "state_ids",
    "state_groups",
    "priority_ids",
    "assignee_ids",
    "label_ids",
    "cycle_ids",
    "module_ids",
    "start_date",
    "due_date",
    "gate_status",
    "search_query",
}


def _normalize_view_description(raw: str) -> str:
    """Normalize markdown and enforce the 16384 byte view description cap."""
    if not raw:
        return ""
    try:
        normalized = normalize_to_markdown(raw)
    except ContentNormalizeError as exc:
        raise ProblemException(
            code="INVALID_CONTENT", status=422, title="Invalid Content", detail=str(exc)
        ) from exc
    if len(normalized.encode()) > MAX_VIEW_DESCRIPTION_BYTES:
        raise ProblemException(
            code="DESCRIPTION_TOO_LARGE",
            status=422,
            title="Description Too Large",
            detail=f"Description exceeds maximum {MAX_VIEW_DESCRIPTION_BYTES} bytes",
        )
    return normalized


def _to_slug(name: str) -> str:
    """Convert a name into a lowercase URL slug."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return s[:40] if s else "view"


async def _allocate_view_canonical_key(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_identifier: str,
    base_slug: str,
) -> str:
    """Find a unique canonical_key in objects for a view."""
    candidate = f"{project_identifier}/views/{base_slug}"
    idx = 1
    while True:
        exists_row = (
            await session.execute(
                select(ObjectRecord.id).where(
                    ObjectRecord.workspace_id == workspace_id,
                    ObjectRecord.object_type == "view",
                    ObjectRecord.canonical_key == candidate,
                    ObjectRecord.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if exists_row is None:
            return candidate
        candidate = f"{project_identifier}/views/{base_slug}-{idx}"
        idx += 1


def _extract_db_filters(filters: FilterSpec) -> dict[str, Any]:
    """Extract only keys allowed by PostgreSQL validate_view_filters_json constraint."""
    dumped = filters.model_dump(mode="json")
    db_dict: dict[str, Any] = {}
    for k, v in dumped.items():
        if k in _ALLOWED_DB_FILTER_KEYS and v is not None:
            if isinstance(v, list) and not v:
                continue
            db_dict[k] = v
    return db_dict


def _reconstruct_filters(view: View) -> FilterSpec:
    """Reconstruct complete FilterSpec from view display_props_json and filters_json."""
    full_dict = {}
    if "full_filters" in view.display_props_json:
        full_dict = view.display_props_json["full_filters"]
    elif view.filters_json:
        full_dict = view.filters_json
    try:
        return FilterSpec.model_validate(full_dict)
    except (ValueError, TypeError, ValidationError):
        return FilterSpec()


async def serialize_view(
    session: AsyncSession,
    caller: PrincipalContext,
    view: View,
) -> ViewResponse:
    """Serialize a View instance into ViewResponse with access manifest and capabilities."""
    manifest = await build_access_manifest(session, caller, view.id)
    caps = await evaluate_capabilities(session, caller, view.id)

    owner_principal = await session.get(Principal, view.owner_principal_id)
    display_name = owner_principal.display_name if owner_principal else "Unknown"

    user_row = (
        await session.execute(
            select(ObjectRecord.canonical_key).where(
                ObjectRecord.id == view.owner_principal_id,
                ObjectRecord.object_type == "user",
            )
        )
    ).scalar_one_or_none()
    handle = user_row or display_name

    layout_str = view.layout.value if hasattr(view.layout, "value") else str(view.layout)
    layout_val = ViewLayout(layout_str)

    return ViewResponse(
        id=view.id,
        project_id=view.project_id,
        name=view.name,
        description_markdown=view.summary_markdown,
        layout=layout_val,
        group_by=view.group_by or "none",
        sub_group_by=view.sub_group_by or "none",
        filters=_reconstruct_filters(view),
        wip_limits_override=view.wip_limits_json or {},
        is_shared=(view.visibility != "private"),
        visibility="personal" if view.visibility == "private" else "project",
        owner=ViewOwnerSummary(
            id=view.owner_principal_id,
            display_name=display_name,
            handle=handle,
        ),
        access_manifest=manifest,
        capabilities=capabilities_to_names(caps),
    )


async def get_view_or_404(
    session: AsyncSession,
    caller: PrincipalContext,
    view_id: uuid.UUID,
) -> View:
    """Fetch View under PostgreSQL RLS or raise 404."""
    await require_capability(session, caller, view_id, Capability.VIEW)
    stmt = select(View).where(
        View.id == view_id,
        View.workspace_id == caller.workspace_id,
    )
    view = (await session.execute(stmt)).scalar_one_or_none()
    if view is None:
        not_found()
    return view


async def create_view(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    body: ViewCreate,
) -> ViewResponse:
    """Create a new saved view in a project."""
    project = await get_project_or_404(session, caller, project_ref)

    if body.visibility is not None:
        is_shared = body.visibility.strip().lower() not in ("personal", "private")
    else:
        is_shared = body.is_shared

    if is_shared:
        await require_capability(session, caller, project.id, Capability.EDIT)
    else:
        await require_capability(session, caller, project.id, Capability.VIEW)

    gb = body.group_by or (GroupAxis.STATE if body.layout == ViewLayout.BOARD else GroupAxis.NONE)
    sgb = body.sub_group_by or GroupAxis.NONE
    validate_group_axes(project, gb, sgb, body.filters)

    description = _normalize_view_description(body.description_markdown)
    slug = _to_slug(body.name)
    canonical_key = await _allocate_view_canonical_key(
        session, caller.workspace_id, project.identifier, slug
    )

    db_layout = DbViewLayout(body.layout.value)
    visibility_val = "project" if is_shared else "private"

    gb_str = gb.value if gb != GroupAxis.NONE else None
    sgb_str = sgb.value if sgb != GroupAxis.NONE else None

    db_filters = _extract_db_filters(body.filters)
    display_props = {"full_filters": body.filters.model_dump(mode="json")}

    wip_json: dict[str, Any] = {}
    if body.wip_limits_override:
        for k, v in body.wip_limits_override.items():
            wip_json[k] = v.model_dump() if hasattr(v, "model_dump") else v

    async with session.begin_nested():
        view_id = (
            await session.execute(
                text(
                    "SELECT register_object("
                    "  CAST('view' AS object_kind), :ws, :proj, :ckey, :name, :creator"
                    ")"
                ),
                {
                    "ws": caller.workspace_id,
                    "proj": project.id,
                    "ckey": canonical_key,
                    "name": body.name,
                    "creator": caller.principal_id,
                },
            )
        ).scalar_one()

        view = View(
            id=view_id,
            object_type="view",
            workspace_id=caller.workspace_id,
            project_id=project.id,
            owner_principal_id=caller.principal_id,
            visibility=visibility_val,
            name=body.name,
            summary_markdown=description,
            layout=db_layout,
            group_by=gb_str,
            sub_group_by=sgb_str,
            filters_json=db_filters,
            display_props_json=display_props,
            wip_limits_json=wip_json,
            sort_rank="a0",
        )
        session.add(view)
        await session.flush()

        if is_shared:
            await record_activity(
                session=session,
                workspace_id=caller.workspace_id,
                object_id=view_id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.VIEW_CREATED,
                payload={"layout": body.layout.value, "is_shared": True},
            )

        await session.execute(
            text("SELECT rebuild_effective_access_for_object(:oid)"),
            {"oid": view_id},
        )

    await session.flush()
    return await serialize_view(session, caller, view)


async def list_project_views(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
) -> ViewList:
    """List all saved views in a project visible to caller under RLS."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    stmt = (
        select(View)
        .where(
            View.project_id == project.id,
            View.workspace_id == caller.workspace_id,
        )
        .order_by(View.sort_rank, View.name)
    )
    rows = (await session.execute(stmt)).scalars().all()
    items: list[ViewResponse] = []
    for v in rows:
        caps = await evaluate_capabilities(session, caller, v.id)
        if Capability.VIEW in caps:
            items.append(await serialize_view(session, caller, v))
    return ViewList(items=items)


def _apply_filter_and_wip_updates(
    view: View,
    body: ViewPatch,
) -> dict[str, Any]:
    """Apply filters and WIP limit updates to a View entity."""
    changes: dict[str, Any] = {}
    if body.filters is not None:
        view.filters_json = _extract_db_filters(body.filters)
        current_display = dict(view.display_props_json or {})
        current_display["full_filters"] = body.filters.model_dump(mode="json")
        view.display_props_json = current_display
        changes["filters"] = body.filters.model_dump(mode="json")

    if body.wip_limits_override is not None:
        wip_json: dict[str, Any] = {}
        for k, v in body.wip_limits_override.items():
            wip_json[k] = v.model_dump() if hasattr(v, "model_dump") else v
        view.wip_limits_json = wip_json
        changes["wip_limits_override"] = wip_json
    return changes


def _apply_view_updates(
    view: View,
    body: ViewPatch,
    project: Project | None,
) -> dict[str, Any]:
    """Apply validated updates to a View entity, returning modified attributes."""
    changes: dict[str, Any] = {}

    if body.name is not None and body.name != view.name:
        view.name = body.name
        changes["name"] = body.name

    if body.description_markdown is not None:
        new_desc = _normalize_view_description(body.description_markdown)
        if new_desc != view.summary_markdown:
            view.summary_markdown = new_desc
            changes["description_markdown"] = new_desc

    if body.layout is not None:
        db_layout = DbViewLayout(body.layout.value)
        if db_layout != view.layout:
            view.layout = db_layout
            changes["layout"] = body.layout.value

    gb = body.group_by if body.group_by is not None else GroupAxis(view.group_by or "none")
    sgb = (
        body.sub_group_by
        if body.sub_group_by is not None
        else GroupAxis(view.sub_group_by or "none")
    )
    cur_filters = body.filters if body.filters is not None else _reconstruct_filters(view)

    if project:
        validate_group_axes(project, gb, sgb, cur_filters)

    if body.group_by is not None:
        view.group_by = body.group_by.value if body.group_by != GroupAxis.NONE else None
        changes["group_by"] = view.group_by

    if body.sub_group_by is not None:
        view.sub_group_by = body.sub_group_by.value if body.sub_group_by != GroupAxis.NONE else None
        changes["sub_group_by"] = view.sub_group_by

    changes.update(_apply_filter_and_wip_updates(view, body))
    return changes


async def update_view(
    session: AsyncSession,
    caller: PrincipalContext,
    view_id: uuid.UUID,
    body: ViewPatch,
) -> ViewResponse:
    """Update an existing saved view."""
    view = await get_view_or_404(session, caller, view_id)
    project = await session.get(Project, view.project_id) if view.project_id else None

    is_owner = view.owner_principal_id == caller.principal_id
    project_caps = (
        await evaluate_capabilities(session, caller, view.project_id)
        if view.project_id
        else Capability.NONE
    )
    is_admin = bool(project_caps & Capability.ADMIN)

    if not (is_owner or is_admin):
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="Only the view owner or project admin can update this view",
        )

    changes: dict[str, Any] = {}
    if body.visibility is not None or body.is_shared is not None:
        if body.visibility is not None:
            target_shared = body.visibility.strip().lower() not in ("personal", "private")
        else:
            target_shared = bool(body.is_shared)

        currently_shared = view.visibility != "private"
        if target_shared != currently_shared:
            if target_shared:
                if view.project_id:
                    await require_capability(session, caller, view.project_id, Capability.EDIT)
                view.visibility = "project"
            else:
                view.visibility = "private"
            changes["is_shared"] = target_shared

    sub_changes = _apply_view_updates(view, body, project)
    changes.update(sub_changes)

    if view.visibility != "private" and changes:
        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            object_id=view.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.VIEW_UPDATED,
            payload={"changes": changes},
        )

    if "is_shared" in changes:
        await session.execute(
            text("SELECT rebuild_effective_access_for_object(:oid)"),
            {"oid": view.id},
        )

    await session.flush()
    return await serialize_view(session, caller, view)


async def delete_view(
    session: AsyncSession,
    caller: PrincipalContext,
    view_id: uuid.UUID,
) -> None:
    """Delete a saved view."""
    view = await get_view_or_404(session, caller, view_id)
    project_id = view.project_id
    was_shared = view.visibility != "private"

    is_owner = view.owner_principal_id == caller.principal_id
    project_caps = (
        await evaluate_capabilities(session, caller, view.project_id)
        if view.project_id
        else Capability.NONE
    )
    is_admin = bool(project_caps & Capability.ADMIN)

    if not (is_owner or is_admin):
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail="Only the view owner or project admin can delete this view",
        )

    async with session.begin_nested():
        if was_shared and project_id:
            await record_activity(
                session=session,
                workspace_id=caller.workspace_id,
                object_id=project_id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.VIEW_DELETED,
                payload={"view_id": str(view_id)},
            )
        await session.execute(delete(View).where(View.id == view_id))
        await session.execute(delete(ObjectRecord).where(ObjectRecord.id == view_id))

    await session.flush()


async def query_view_issues(
    session: AsyncSession,
    caller: PrincipalContext,
    view_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 50,
) -> ViewQueryResponse:
    """Execute view query using its saved spec and caller RLS."""
    if limit < 1 or limit > MAX_QUERY_LIMIT:
        raise ProblemException(
            code="INVALID_LIMIT",
            status=422,
            title="Invalid Limit",
            detail=f"Query limit must be between 1 and {MAX_QUERY_LIMIT}",
        )

    view = await get_view_or_404(session, caller, view_id)
    project = await session.get(Project, view.project_id)
    if project is None:
        not_found()

    filters = _reconstruct_filters(view)
    gb = GroupAxis(view.group_by) if view.group_by else GroupAxis.NONE
    sgb = GroupAxis(view.sub_group_by) if view.sub_group_by else GroupAxis.NONE
    layout_str = view.layout.value if hasattr(view.layout, "value") else str(view.layout)
    layout = ViewLayout(layout_str)

    return await execute_view_query(
        session=session,
        caller=caller,
        project=project,
        filters=filters,
        layout=layout,
        group_by=gb,
        sub_group_by=sgb,
        sort_by=SortField.BOARD_RANK if layout == ViewLayout.BOARD else SortField.SEQUENCE_ID,
        sort_dir=SortDir.ASC if layout == ViewLayout.BOARD else SortDir.DESC,
        wip_limits_override=view.wip_limits_json or {},
        limit=limit,
        cursor=cursor,
    )


async def query_project_issues_adhoc(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    req: AdHocQueryRequest,
) -> ViewQueryResponse:
    """Execute ad-hoc issue query over a project."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    return await execute_view_query(
        session=session,
        caller=caller,
        project=project,
        filters=req.filters,
        layout=req.layout,
        group_by=req.group_by,
        sub_group_by=req.sub_group_by,
        sort_by=req.sort_by,
        sort_dir=req.sort_dir,
        wip_limits_override=req.wip_limits_override or {},
        limit=req.limit,
        cursor=req.cursor,
    )
