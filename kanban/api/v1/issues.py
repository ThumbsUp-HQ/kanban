"""Issue endpoints CRUD and outbound secret scrubbing.

Covers CRUD, keyset listing, description ETag concurrency, and secret redaction (S7.2, S3.4).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession  # Required by FastAPI at runtime

from database.models.prose import ALL_PROVENANCE_TIERS, UNTRUSTED_PROVENANCE_TIERS
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.issues import IssueCreate, IssueList, IssuePatch, IssueResponse
from kanban.security.read_taint import (
    TaintGuard,
    TaintRecorder,
    get_taint_guard,
    get_taint_recorder,
)
from kanban.services import issues as svc

router = APIRouter(tags=["issues"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]
StateGroupFilter = Literal["backlog", "unstarted", "started", "completed", "cancelled"]


def _derive_provenance_tier(  # noqa: C901
    request: Request,
    caller: PrincipalContext,
) -> str:
    """Derive provenance tier from request channel and caller principal, preventing self-upgrade."""
    channel_header = (
        (
            request.headers.get("x-kb-channel")
            or request.headers.get("x-kanban-channel")
            or request.headers.get("x-kb-ingestion-channel")
            or request.headers.get("x-kanban-ingestion-channel")
            or ""
        )
        .lower()
        .strip()
    )

    req_query_tier: str | None = None
    req_scope = getattr(request, "scope", None)
    if isinstance(req_scope, dict) and "query_string" in req_scope:
        req_query_tier = request.query_params.get("provenance_tier")

    requested_tier = (
        (
            request.headers.get("x-kb-provenance-tier")
            or request.headers.get("x-kanban-provenance-tier")
            or req_query_tier
            or ""
        )
        .lower()
        .strip()
    )

    # Determine caller's base ingestion channel tier
    if (
        "external_webhook" in caller.token_scopes
        or "webhook" in caller.token_scopes
        or channel_header in ("webhook", "external_webhook")
    ):
        base_channel_tier = "external_webhook"
    elif (
        "imported" in caller.token_scopes
        or "import" in caller.token_scopes
        or channel_header in ("import", "imported")
    ):
        base_channel_tier = "imported"
    elif channel_header in ("public_reporter", "public"):
        base_channel_tier = "public_reporter"
    elif channel_header in ("untrusted_intake", "intake"):
        base_channel_tier = "untrusted_intake"
    elif caller.agent_principal_id is not None or caller.principal_type == "agent":
        base_channel_tier = "verified_agent"
    else:
        base_channel_tier = "trusted_member"

    # Self-upgrade check: if channel is untrusted,
    # attempting to claim trusted_member or verified_agent is forbidden
    if base_channel_tier in UNTRUSTED_PROVENANCE_TIERS:
        if requested_tier in ("trusted_member", "verified_agent"):
            raise ProblemException(
                code="PROVENANCE_SELF_UPGRADE_FORBIDDEN",
                status=403,
                title="Provenance Self Upgrade Forbidden",
                detail=(
                    "Client cannot self-upgrade provenance tier from untrusted channel "
                    "to trusted tier."
                ),
            )
        return requested_tier if requested_tier in ALL_PROVENANCE_TIERS else base_channel_tier

    if requested_tier:
        if requested_tier not in ALL_PROVENANCE_TIERS:
            raise ProblemException(
                code="INVALID_PROVENANCE_TIER",
                status=422,
                title="Invalid Provenance Tier",
                detail=(
                    f"Provenance tier '{requested_tier}' is invalid. "
                    f"Allowed: {sorted(ALL_PROVENANCE_TIERS)}"
                ),
            )
        if requested_tier == "verified_agent" and not (
            caller.agent_principal_id or caller.principal_type == "agent"
        ):
            raise ProblemException(
                code="PROVENANCE_SELF_UPGRADE_FORBIDDEN",
                status=403,
                title="Provenance Self Upgrade Forbidden",
                detail="Only verified agents can claim verified_agent provenance tier.",
            )
        return requested_tier

    return base_channel_tier


@router.post(
    "/projects/{project_ref}/issues",
    status_code=201,
    response_model=IssueResponse,
    summary="Create an issue",
)
async def create_issue(  # noqa: PLR0913, PLR0917
    project_ref: str,
    body: IssueCreate,
    caller: Caller,
    session: Session,
    response: Response,
    request: Request,
) -> IssueResponse:
    """Create an issue in a project (caller requires EDIT capability on project)."""
    async with timing_floor(floor_ms=25.0):
        if request.headers.get("x-kb-mcp-session") or not request.headers.get("x-kb-internal-auth"):
            taint_guard = get_taint_guard(request, session, caller)
            await taint_guard.check_write(project_ref, tool_name="create_ticket")
        derived_tier = _derive_provenance_tier(request, caller)
        result, etag = await svc.create_issue(session, caller, project_ref, body)
        if derived_tier != "trusted_member":
            await session.execute(
                text("UPDATE issues SET provenance_tier = :pt WHERE id = :id"),
                {"pt": derived_tier, "id": result.id},
            )
        response.headers["Location"] = f"/api/v1/issues/{result.key}"
        response.headers["ETag"] = etag
        await session.commit()
        return result


@router.get(
    "/issues/{issue_key}",
    response_model=IssueResponse,
    summary="Get an issue by key or UUID",
)
async def get_issue(  # noqa: PLR0913, PLR0917
    issue_key: str,
    caller: Caller,
    session: Session,
    response: Response,
    request: Request,
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
    workspace: Annotated[str | None, Query(description="Optional workspace slug or UUID")] = None,
    lod: Annotated[
        Literal["summary", "standard", "full"],
        Query(description="Level of detail tier: summary, standard, or full"),
    ] = "full",
    if_none_match: Annotated[str | None, Header()] = None,
) -> IssueResponse | Response:
    """Return an issue, or 304 when If-None-Match matches current issue ETag."""
    workspace_ref = workspace or request.headers.get("x-kb-scope-workspace")
    async with timing_floor(floor_ms=25.0):
        issue = await svc.get_issue_or_404(session, caller, issue_key, workspace_ref=workspace_ref)
        if getattr(issue, "is_untrusted_content", False):
            response.headers["X-Kanban-Untrusted-Taint"] = "1"
            await taint_recorder.record_untrusted_read(
                issue.project_id, untrusted_source_object_id=issue.id
            )
        else:
            await taint_recorder.record_project_ids([issue.project_id])
        serialized = await svc.serialize_issue(session, caller, issue, lod=lod)
        desc_sha = issue.description_sha256.hex() if issue.description_sha256 else ""
        etag = serialized.etag or (f'"{desc_sha}"' if desc_sha else '""')
        etag_hex = etag.strip('"')

        if if_none_match is not None:
            raw_header = if_none_match.strip()
            if raw_header.startswith("W/"):
                raw_header = raw_header[2:].strip()
            client_hex = raw_header.strip('"')
            if client_hex.lower() == etag_hex.lower() or raw_header == etag:
                headers = {"ETag": etag}
                if getattr(issue, "_resolved_via_alias", False) or serialized.key != issue_key:
                    headers["X-Kanban-Canonical-Key"] = serialized.key
                return Response(status_code=304, headers=headers)

        response.headers["ETag"] = etag
        is_alias = getattr(issue, "_resolved_via_alias", False) or serialized.key != issue_key
        if is_alias:
            response.headers["X-Kanban-Canonical-Key"] = serialized.key
            accept = request.headers.get("accept", "")
            if "text/html" in accept and "application/json" not in accept:
                project_key = serialized.key.rsplit("-", 1)[0]
                canonical_url = f"/projects/{project_key}/issues/{serialized.key}"
                return Response(
                    status_code=308,
                    headers={"Location": canonical_url, "X-Kanban-Canonical-Key": serialized.key},
                )

        return serialized


@router.patch(
    "/issues/{issue_key}",
    response_model=IssueResponse,
    summary="Update an issue",
)
async def patch_issue(  # noqa: PLR0913, PLR0917
    issue_key: str,
    body: IssuePatch,
    caller: Caller,
    session: Session,
    response: Response,
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
    if_match: Annotated[str | None, Header()] = None,
) -> IssueResponse:
    """Update issue fields under description ETag concurrency check."""
    async with timing_floor(floor_ms=25.0):
        issue = await svc.get_issue_or_404(session, caller, issue_key)
        await taint_guard.check_write(issue.project_id, tool_name="update_ticket")
        result, new_etag = await svc.update_issue(session, caller, issue_key, body, if_match)
        await session.commit()
        response.headers["ETag"] = new_etag
        return result


@router.get(
    "/projects/{project_ref}/issues",
    response_model=IssueList,
    summary="List issues in a project",
)
async def list_issues(  # noqa: PLR0913
    project_ref: str,
    caller: Caller,
    session: Session,
    response: Response,
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
    *,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    include_archived: Annotated[bool, Query()] = False,
    only_archived: Annotated[bool, Query()] = False,
    state_group: Annotated[
        list[StateGroupFilter] | None,
        Query(description="Optional workflow state_group filter"),
    ] = None,
    lod: Annotated[
        Literal["summary", "standard", "full"],
        Query(description="Level of detail tier: summary, standard, or full"),
    ] = "full",
) -> IssueList:
    """List RLS-visible issues within a project using keyset pagination."""
    if not include_archived and only_archived:
        raise ProblemException(
            code="ARCHIVE_FILTER_CONFLICT",
            status=422,
            title="Archive Filter Conflict",
            detail="Cannot filter only_archived=true when include_archived=false",
        )
    async with timing_floor(floor_ms=25.0):
        res = await svc.list_issues(
            session,
            caller,
            project_ref,
            cursor=cursor,
            limit=limit,
            include_archived=include_archived,
            only_archived=only_archived,
            state_group=state_group,
            lod=lod,
        )
        item_ids = [item.id for item in res.items]
        untrusted_found = False
        if item_ids:
            untrusted_q = await session.execute(
                text(
                    "SELECT id FROM issues "
                    "WHERE id = ANY(:ids) AND is_untrusted_content = TRUE LIMIT 1"
                ),
                {"ids": item_ids},
            )
            untrusted_row = untrusted_q.first()
            if untrusted_row is not None:
                untrusted_found = True
                response.headers["X-Kanban-Untrusted-Taint"] = "1"
                await taint_recorder.record_untrusted_read(
                    project_ref, untrusted_source_object_id=untrusted_row[0]
                )
        if not untrusted_found:
            await taint_recorder.record_project_ids([project_ref])
        return res
