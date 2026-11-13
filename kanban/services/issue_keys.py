"""Issue key and reference resolution service (S7.2 8a, S3.4).

Resolves human-readable issue references (<IDENTIFIER>-<sequence_id>) or UUIDs to Issue
records under the caller's RLS session. Unreadable, non-existent, or soft-deleted issues
raise the canonical 404 NOT_FOUND problem document without enumeration side-channels.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from database.models import Issue, ObjectRecord, Project
from kanban.api.problems import not_found

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

ISSUE_KEY_PATTERN: Final[str] = r"^[A-Z][A-Z0-9]{1,9}-[1-9][0-9]{0,17}$"
_ISSUE_KEY_RE: Final[re.Pattern[str]] = re.compile(ISSUE_KEY_PATTERN)


async def resolve_issue_ref(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    *,
    include_deleted: bool = False,
) -> Issue:
    """Resolve an issue reference through RLS or raise the canonical 404.

    Accepts:
        - Project issue key: <IDENTIFIER>-<sequence_id> (e.g. KAN-142)
        - Issue UUID string

    Returns:
        The resolved Issue model instance.

    Raises:
        ProblemException: 404 NOT_FOUND if the issue does not exist, belongs to another
        workspace, has been soft-deleted (when include_deleted=False), or the caller lacks VIEW.

    """
    stmt = (
        select(Issue)
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .where(Issue.workspace_id == caller.workspace_id)
    )
    if not include_deleted:
        stmt = stmt.where(ObjectRecord.deleted_at.is_(None))

    if _ISSUE_KEY_RE.fullmatch(issue_ref):
        ident, seq_str = issue_ref.rsplit("-", 1)
        seq_id = int(seq_str)
        stmt = stmt.join(Project, Project.id == Issue.project_id).where(
            Project.identifier == ident,
            Issue.sequence_id == seq_id,
        )
    else:
        try:
            issue_id = uuid.UUID(issue_ref)
        except ValueError:
            not_found()
        stmt = stmt.where(Issue.id == issue_id)

    issue = (await session.execute(stmt)).scalar_one_or_none()
    if issue is None:
        not_found()
    return issue
