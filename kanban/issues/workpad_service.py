# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Service layer for silent per-issue Agent Workpad slot (KB-AGENT-WORKPAD-01, KAN-71)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from database.models.issue_workpad import IssueWorkpad
from kanban.api.problems import ProblemException
from kanban.content.normalize import ContentNormalizeError, normalize_to_markdown
from kanban.security.permissions import Capability, require_capability
from kanban.services.issue_keys import resolve_issue_ref

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

__all__ = [
    "MAX_WORKPAD_BYTES",
    "get_issue_workpad",
    "put_issue_workpad",
]

MAX_WORKPAD_BYTES: Final[int] = 65536


async def get_issue_workpad(
    session: AsyncSession,
    caller: PrincipalContext,
    identifier: str,
    principal_id: uuid.UUID | None = None,
) -> IssueWorkpad:
    """Retrieve issue workpad slot for a principal or the issue's latest workpad."""
    issue = await resolve_issue_ref(session, caller, identifier)
    await require_capability(session, caller, issue.id, Capability.VIEW)

    if principal_id is not None:
        stmt = select(IssueWorkpad).where(
            IssueWorkpad.issue_id == issue.id,
            IssueWorkpad.principal_id == principal_id,
        )
        workpad = (await session.execute(stmt)).scalar_one_or_none()
    else:
        # Check caller principal first
        stmt = select(IssueWorkpad).where(
            IssueWorkpad.issue_id == issue.id,
            IssueWorkpad.principal_id == caller.principal_id,
        )
        workpad = (await session.execute(stmt)).scalar_one_or_none()
        if workpad is None:
            # Fall back to most recently updated workpad on the issue
            stmt_latest = (
                select(IssueWorkpad)
                .where(IssueWorkpad.issue_id == issue.id)
                .order_by(IssueWorkpad.updated_at.desc())
                .limit(1)
            )
            workpad = (await session.execute(stmt_latest)).scalar_one_or_none()

    if workpad is None:
        # Return an empty slot with revision 0
        return IssueWorkpad(
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            principal_id=principal_id or caller.principal_id,
            body_markdown="",
            revision=0,
            updated_at=datetime.now(UTC),
        )

    return workpad


async def put_issue_workpad(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    caller: PrincipalContext,
    identifier: str,
    body_markdown: str,
    expected_revision: int | None = None,
    if_match_revision: int | None = None,
) -> IssueWorkpad:
    """Create or update silent agent workpad slot with CAS revision protection."""
    target_rev = expected_revision if expected_revision is not None else if_match_revision
    issue = await resolve_issue_ref(session, caller, identifier)
    await require_capability(
        session,
        caller,
        issue.id,
        Capability.VIEW | Capability.COMMENT | Capability.EDIT,
    )

    # Validate UTF-8 byte length
    try:
        raw_bytes = body_markdown.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ProblemException(
            code="INVALID_UTF8_SURROGATE",
            status=422,
            title="Invalid UTF-8 Surrogate",
            detail="Markdown contains invalid encoding",
        ) from exc

    if len(raw_bytes) > MAX_WORKPAD_BYTES:
        raise ProblemException(
            code="WORKPAD_PAYLOAD_TOO_LARGE",
            status=422,
            title="Payload Too Large",
            detail=f"Workpad body markdown exceeds maximum limit of {MAX_WORKPAD_BYTES} bytes",
        )

    try:
        normalized = normalize_to_markdown(body_markdown, max_input_bytes=MAX_WORKPAD_BYTES)
    except ContentNormalizeError as norm_err:
        raise ProblemException(
            code="INVALID_UTF8_SURROGATE",
            status=422,
            title="Invalid UTF-8 Surrogate",
            detail=f"Content normalization failed: {norm_err}",
        ) from norm_err

    now = datetime.now(UTC)

    # Query existing workpad with row lock
    stmt = (
        select(IssueWorkpad)
        .where(
            IssueWorkpad.issue_id == issue.id,
            IssueWorkpad.principal_id == caller.principal_id,
        )
        .with_for_update()
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing is not None:
        if target_rev is not None and existing.revision != target_rev:
            raise ProblemException(
                code="PRECONDITION_FAILED",
                status=412,
                title="Precondition Failed",
                detail=(
                    f"Current workpad revision {existing.revision} does not match "
                    f"requested revision {target_rev}"
                ),
            )

        existing.body_markdown = normalized
        existing.revision += 1
        existing.updated_at = now
        await session.flush()
        await session.refresh(existing)
        return existing

    if target_rev is not None and target_rev != 0:
        raise ProblemException(
            code="PRECONDITION_FAILED",
            status=412,
            title="Precondition Failed",
            detail=f"Initial workpad creation expects revision 0, got {target_rev}",
        )

    new_id = uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4()
    workpad = IssueWorkpad(
        id=new_id,
        workspace_id=issue.workspace_id,
        project_id=issue.project_id,
        issue_id=issue.id,
        principal_id=caller.principal_id,
        body_markdown=normalized,
        revision=1,
        updated_at=now,
    )
    session.add(workpad)
    await session.flush()
    await session.refresh(workpad)
    return workpad
