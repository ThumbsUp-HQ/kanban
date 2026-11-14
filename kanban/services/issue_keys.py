"""Issue key and reference resolution service (S7.2 8a, S3.4, S11.1).

Resolves human-readable issue references (<IDENTIFIER>-<sequence_id>) or UUIDs to Issue
records under the caller's RLS session. Unreadable, non-existent, or soft-deleted issues
raise the canonical 404 NOT_FOUND problem document without enumeration side-channels.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Final, cast

from sqlalchemy import select

from database.models import Issue, ObjectRecord, Project, Workspace
from kanban.api.problems import ProblemException, not_found

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

ISSUE_KEY_PATTERN: Final[str] = r"^[A-Z][A-Z0-9]{1,9}-[1-9][0-9]{0,17}$"
_ISSUE_KEY_RE: Final[re.Pattern[str]] = re.compile(ISSUE_KEY_PATTERN)


async def resolve_issue_ref(  # noqa: C901, PLR0912
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    *,
    workspace_ref: str | None = None,
    include_deleted: bool = False,
) -> Issue:
    """Resolve an issue reference through RLS or raise the canonical 404 / 409 AMBIGUOUS_IDENTIFIER.

    Accepts:
        - Project issue key: <IDENTIFIER>-<sequence_id> (e.g. KAN-142)
        - Issue UUID string

    Returns:
        The resolved Issue model instance.

    Raises:
        ProblemException: 409 AMBIGUOUS_IDENTIFIER if unambiguous key matches across workspaces.
        ProblemException: 404 NOT_FOUND if the issue does not exist or caller lacks access.

    """
    target_ws_id: uuid.UUID | None = None
    if workspace_ref:
        try:
            target_ws_id = uuid.UUID(workspace_ref)
        except ValueError:
            ws_stmt = select(Workspace.id).where(Workspace.slug == workspace_ref)
            target_ws_id = (await session.execute(ws_stmt)).scalar_one_or_none()
            if target_ws_id is None:
                not_found()
    elif getattr(caller, "scope_tier", None) != "global" and getattr(caller, "workspace_id", None):
        target_ws_id = caller.workspace_id

    if _ISSUE_KEY_RE.fullmatch(issue_ref):
        ident, seq_str = issue_ref.rsplit("-", 1)
        seq_id = int(seq_str)
        stmt = (
            select(Issue, Project.identifier, Workspace.slug)
            .join(ObjectRecord, ObjectRecord.id == Issue.id)
            .join(Project, Project.id == Issue.project_id)
            .join(Workspace, Workspace.id == Project.workspace_id)
            .where(
                Project.identifier == ident,
                Issue.sequence_id == seq_id,
            )
        )
        if not include_deleted:
            stmt = stmt.where(ObjectRecord.deleted_at.is_(None))
        if target_ws_id is not None:
            stmt = stmt.where(Issue.workspace_id == target_ws_id)

        rows = list((await session.execute(stmt)).all())
        if len(rows) > 1:
            candidates = [
                {
                    "workspace": ws_slug,
                    "project": p_ident,
                    "key": f"{p_ident}-{iss.sequence_id}",
                    "title": iss.summary,
                }
                for iss, p_ident, ws_slug in rows
            ]
            raise ProblemException(
                code="AMBIGUOUS_IDENTIFIER",
                status=409,
                title="Ambiguous Identifier",
                detail=f"Issue key '{issue_ref}' exists in multiple authorized workspaces",
                candidates=candidates,
                extra={
                    "hint": (
                        "Pass workspace='<slug>' (e.g. workspace='prod') "
                        "or connect via /mcp/agent/w/<slug>"
                    )
                },
            )
        if len(rows) == 1:
            return cast("Issue", rows[0][0])
        not_found()

    try:
        issue_id = uuid.UUID(issue_ref)
    except ValueError:
        not_found()

    stmt_uuid = (
        select(Issue).join(ObjectRecord, ObjectRecord.id == Issue.id).where(Issue.id == issue_id)
    )
    if not include_deleted:
        stmt_uuid = stmt_uuid.where(ObjectRecord.deleted_at.is_(None))
    if target_ws_id is not None:
        stmt_uuid = stmt_uuid.where(Issue.workspace_id == target_ws_id)

    issue = (await session.execute(stmt_uuid)).scalar_one_or_none()
    if issue is None:
        not_found()
    return issue
