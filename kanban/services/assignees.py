# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hybrid assignees service: assignment, access verification, and suggestions (KB-P3-03)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Final, NoReturn

from sqlalchemy import delete, func, select, text

from database.models.issues import IssueAssignee
from database.models.principals import Principal, User
from database.models.spine import ObjectRecord
from kanban.api.problems import ProblemException, not_found
from kanban.api.v1.schemas.assignees import (
    FREE_TEXT_HINT,
    AssigneeCreate,
    AssigneeResponse,
    AssigneeSuggestionItem,
    AssigneeSuggestionsResponse,
    FreeTextAssigneeResponse,
    PrincipalAssigneeResponse,
    PrincipalSummary,
)
from kanban.content import normalize_plain_text
from kanban.security.permissions import Capability, require_capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.projects import get_project_or_404

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models.issues import Issue
    from kanban.api.deps import PrincipalContext

MAX_TOTAL_ASSIGNEES: Final[int] = 20
MAX_FREE_TEXT_ASSIGNEES: Final[int] = 10
MIN_FREE_TEXT_LENGTH: Final[int] = 1
MAX_FREE_TEXT_LENGTH: Final[int] = 120
MIN_QUERY_LENGTH: Final[int] = 1
MAX_QUERY_LENGTH: Final[int] = 64
DEFAULT_SUGGESTION_LIMIT: Final[int] = 10
MAX_SUGGESTION_LIMIT: Final[int] = 20


def escape_like(s: str) -> str:
    """Escape LIKE pattern special characters (backslash, percent, underscore)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _assignee_not_eligible() -> NoReturn:
    """Raise byte-identical non-leaking 422 problem detail for ineligible assignees."""
    raise ProblemException(
        code="ASSIGNEE_NOT_ELIGIBLE",
        status=422,
        title="Assignee Not Eligible",
        detail="The specified principal is not eligible for assignment in this project",
    )


async def _add_principal_assignee(
    session: AsyncSession,
    caller: PrincipalContext,
    issue: Issue,
    principal_val: str | uuid.UUID,
) -> PrincipalAssigneeResponse:
    """Validate, link, and log a principal assignee."""
    target_id: uuid.UUID
    if isinstance(principal_val, uuid.UUID):
        target_id = principal_val
    else:
        raw_str = str(principal_val).strip()
        try:
            target_id = uuid.UUID(raw_str)
        except ValueError:
            clean_handle = raw_str.lstrip("@")
            obj_row = (
                await session.execute(
                    select(ObjectRecord.id).where(
                        ObjectRecord.workspace_id == caller.workspace_id,
                        ObjectRecord.object_type == "user",
                        ObjectRecord.canonical_key == clean_handle,
                        ObjectRecord.deleted_at.is_(None),
                    )
                )
            ).first()
            if obj_row is not None:
                target_id = obj_row[0]
            else:
                compact_name = func.lower(func.replace(Principal.display_name, " ", ""))
                p_user = (
                    await session.execute(
                        select(Principal.id)
                        .join(User, User.id == Principal.id)
                        .where(
                            Principal.workspace_id == caller.workspace_id,
                            Principal.status == "ACTIVE",
                            (
                                (compact_name == clean_handle.lower())
                                | (func.lower(Principal.display_name) == clean_handle.lower())
                                | (func.lower(User.email) == raw_str.lower())
                                | (func.lower(User.email) == f"{clean_handle.lower()}@example.com")
                                | (
                                    func.split_part(func.lower(User.email), "@", 1)
                                    == clean_handle.lower()
                                )
                            ),
                        )
                    )
                ).scalars().first()
                if p_user is None:
                    _assignee_not_eligible()
                target_id = p_user

    # Verify principal exists, is in same workspace, active, and USER or AGENT
    p_row = (
        await session.execute(
            select(Principal).where(
                Principal.id == target_id,
                Principal.workspace_id == caller.workspace_id,
                Principal.status == "ACTIVE",
                Principal.principal_type.in_(["USER", "AGENT"]),
            )
        )
    ).scalar_one_or_none()
    if p_row is None:
        _assignee_not_eligible()

    # Check effective_resource_access for project VIEW bit set and DENY bit clear
    era_row = (
        await session.execute(
            text(
                "SELECT 1 FROM effective_resource_access "
                "WHERE object_id = :project_id "
                "  AND principal_id = :principal_id "
                "  AND workspace_id = :workspace_id "
                "  AND (allow_mask & 1) = 1 "
                "  AND (deny_mask & 1) = 0"
            ),
            {
                "project_id": issue.project_id,
                "principal_id": target_id,
                "workspace_id": caller.workspace_id,
            },
        )
    ).first()
    if era_row is None:
        _assignee_not_eligible()

    # Check duplicate
    existing = (
        await session.execute(
            select(IssueAssignee.id).where(
                IssueAssignee.issue_id == issue.id,
                IssueAssignee.principal_id == target_id,
            )
        )
    ).first()
    if existing is not None:
        raise ProblemException(
            code="ASSIGNEE_EXISTS",
            status=409,
            title="Assignee Already Exists",
            detail="Principal is already assigned to this issue",
        )

    # Lookup handle for response
    handle_row = (
        await session.execute(
            select(ObjectRecord.canonical_key).where(
                ObjectRecord.id == target_id,
                ObjectRecord.workspace_id == caller.workspace_id,
            )
        )
    ).first()
    handle_val = handle_row[0] if handle_row else p_row.display_name.lower().replace(" ", "")

    ins_res = await session.execute(
        text(
            "INSERT INTO issue_assignees (workspace_id, issue_id, principal_id) "
            "VALUES (:workspace_id, :issue_id, :principal_id) "
            "RETURNING id"
        ),
        {
            "workspace_id": caller.workspace_id,
            "issue_id": issue.id,
            "principal_id": target_id,
        },
    )
    assignee_id = ins_res.scalar_one()
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ASSIGNEE_ADDED,
        payload={"kind": "principal", "principal_id": str(target_id)},
    )

    return PrincipalAssigneeResponse(
        id=assignee_id,
        kind="principal",
        principal=PrincipalSummary(
            id=target_id,
            handle=handle_val,
            display_name=p_row.display_name,
            type=p_row.principal_type,
        ),
    )


async def _add_free_text_assignee(
    session: AsyncSession,
    caller: PrincipalContext,
    issue: Issue,
    free_text_val: str,
) -> FreeTextAssigneeResponse:
    """Validate, link, and log a free-text assignee."""
    ft_count = (
        await session.execute(
            select(func.count(IssueAssignee.id)).where(
                IssueAssignee.issue_id == issue.id,
                IssueAssignee.free_text_assignee.is_not(None),
            )
        )
    ).scalar_one()
    if ft_count >= MAX_FREE_TEXT_ASSIGNEES:
        raise ProblemException(
            code="ASSIGNEE_LIMIT",
            status=422,
            title="Assignee Limit Exceeded",
            detail="Issue cannot have more than 10 free-text assignees",
        )

    cleaned = normalize_plain_text(free_text_val).strip()
    if not (MIN_FREE_TEXT_LENGTH <= len(cleaned) <= MAX_FREE_TEXT_LENGTH):
        raise ProblemException(
            code="FREE_TEXT_INVALID",
            status=422,
            title="Invalid Free Text",
            detail="Free text assignee must be between 1 and 120 characters after normalization",
        )

    existing_ft = (
        await session.execute(
            select(IssueAssignee.id).where(
                IssueAssignee.issue_id == issue.id,
                func.lower(IssueAssignee.free_text_assignee) == cleaned.lower(),
            )
        )
    ).first()
    if existing_ft is not None:
        raise ProblemException(
            code="ASSIGNEE_EXISTS",
            status=409,
            title="Assignee Already Exists",
            detail="Free-text assignee is already assigned to this issue",
        )

    ins_res = await session.execute(
        text(
            "INSERT INTO issue_assignees (workspace_id, issue_id, free_text_assignee) "
            "VALUES (:workspace_id, :issue_id, :free_text) "
            "RETURNING id"
        ),
        {
            "workspace_id": caller.workspace_id,
            "issue_id": issue.id,
            "free_text": cleaned,
        },
    )
    assignee_id = ins_res.scalar_one()
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ASSIGNEE_ADDED,
        payload={"kind": "free_text", "free_text": cleaned},
    )

    return FreeTextAssigneeResponse(
        id=assignee_id,
        kind="free_text",
        free_text=cleaned,
        notify=False,
        hint=FREE_TEXT_HINT,
    )


async def add_assignee(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    body: AssigneeCreate,
) -> AssigneeResponse:
    """Assign an eligible project viewer or free-text label to an issue."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(session, caller, issue.id, Capability.EDIT)

    total_count = (
        await session.execute(
            select(func.count(IssueAssignee.id)).where(IssueAssignee.issue_id == issue.id)
        )
    ).scalar_one()
    if total_count >= MAX_TOTAL_ASSIGNEES:
        raise ProblemException(
            code="ASSIGNEE_LIMIT",
            status=422,
            title="Assignee Limit Exceeded",
            detail="Issue cannot have more than 20 assignees",
        )

    if body.principal is not None:
        return await _add_principal_assignee(session, caller, issue, body.principal)

    if body.free_text is not None:
        return await _add_free_text_assignee(session, caller, issue, body.free_text)

    raise ProblemException(
        code="INVALID_PAYLOAD",
        status=422,
        title="Invalid Assignee Payload",
        detail="Must provide either principal or free_text",
    )


async def remove_assignee(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    assignee_id: uuid.UUID,
) -> None:
    """Remove an assignee from an issue (requires EDIT on issue)."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    await require_capability(session, caller, issue.id, Capability.EDIT)

    row = (
        await session.execute(
            select(IssueAssignee).where(
                IssueAssignee.id == assignee_id,
                IssueAssignee.issue_id == issue.id,
                IssueAssignee.workspace_id == caller.workspace_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        not_found()

    payload: dict[str, Any]
    if row.principal_id is not None:
        payload = {"kind": "principal", "principal_id": str(row.principal_id)}
    else:
        payload = {"kind": "free_text", "free_text": row.free_text_assignee}

    await session.execute(
        delete(IssueAssignee).where(
            IssueAssignee.id == assignee_id,
            IssueAssignee.issue_id == issue.id,
        )
    )
    await session.flush()

    await record_activity(
        session,
        workspace_id=caller.workspace_id,
        object_id=issue.id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.ASSIGNEE_REMOVED,
        payload=payload,
    )


async def get_assignee_suggestions(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    q: str,
    limit: int = DEFAULT_SUGGESTION_LIMIT,
) -> AssigneeSuggestionsResponse:
    """Return autocomplete suggestions of active project viewers with zero cross-scope leakage."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    if not (MIN_QUERY_LENGTH <= len(q) <= MAX_QUERY_LENGTH):
        raise ProblemException(
            code="INVALID_QUERY",
            status=422,
            title="Invalid Query Parameter",
            detail="Query string 'q' must be between 1 and 64 characters",
        )

    clamped_limit = max(1, min(MAX_SUGGESTION_LIMIT, limit))
    escaped_q = escape_like(q)
    pattern = f"{escaped_q}%"

    stmt = text(
        "SELECT "
        "  p.id AS id, "
        "  o.canonical_key AS handle, "
        "  p.display_name AS display_name, "
        "  p.principal_type AS type "
        "FROM principals p "
        "JOIN objects o ON o.id = p.id "
        "JOIN effective_resource_access era ON era.principal_id = p.id "
        "WHERE era.object_id = :project_id "
        "  AND era.workspace_id = :workspace_id "
        "  AND (era.allow_mask & 1) = 1 "
        "  AND (era.deny_mask & 1) = 0 "
        "  AND p.workspace_id = :workspace_id "
        "  AND p.status = 'ACTIVE' "
        "  AND p.principal_type IN ('USER', 'AGENT') "
        "  AND ( "
        "    o.canonical_key ILIKE :pattern ESCAPE '\\' "
        "    OR p.display_name ILIKE :pattern ESCAPE '\\' "
        "  ) "
        "ORDER BY p.display_name ASC, o.canonical_key ASC "
        "LIMIT :limit"
    )

    rows = (
        (
            await session.execute(
                stmt,
                {
                    "project_id": project.id,
                    "workspace_id": caller.workspace_id,
                    "pattern": pattern,
                    "limit": clamped_limit,
                },
            )
        )
        .mappings()
        .all()
    )

    items = [
        AssigneeSuggestionItem(
            id=row["id"],
            handle=row["handle"] or "",
            display_name=row["display_name"],
            type=row["type"],
        )
        for row in rows
    ]
    return AssigneeSuggestionsResponse(items=items)


async def get_issue_assignees(
    session: AsyncSession,
    issue_id: uuid.UUID,
) -> list[AssigneeResponse]:
    """Fetch and serialize all assignees for an issue in deterministic order."""
    stmt = text(
        "SELECT "
        "  ia.id AS id, "
        "  ia.principal_id AS principal_id, "
        "  ia.free_text_assignee AS free_text_assignee, "
        "  o.canonical_key AS handle, "
        "  p.display_name AS display_name, "
        "  p.principal_type AS principal_type "
        "FROM issue_assignees ia "
        "LEFT JOIN principals p ON p.id = ia.principal_id "
        "LEFT JOIN objects o ON o.id = p.id "
        "WHERE ia.issue_id = :issue_id "
        "ORDER BY ia.created_at ASC, ia.id ASC"
    )
    rows = (await session.execute(stmt, {"issue_id": issue_id})).mappings().all()

    result: list[AssigneeResponse] = []
    for row in rows:
        if row["principal_id"] is not None:
            result.append(
                PrincipalAssigneeResponse(
                    id=row["id"],
                    kind="principal",
                    principal=PrincipalSummary(
                        id=row["principal_id"],
                        handle=row["handle"] or "",
                        display_name=row["display_name"] or "",
                        type=row["principal_type"] or "USER",
                    ),
                )
            )
        else:
            result.append(
                FreeTextAssigneeResponse(
                    id=row["id"],
                    kind="free_text",
                    free_text=row["free_text_assignee"] or "",
                    notify=False,
                    hint=FREE_TEXT_HINT,
                )
            )
    return result
