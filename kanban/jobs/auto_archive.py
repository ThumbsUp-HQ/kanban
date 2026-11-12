"""Periodic auto-archive background job with advisory lock concurrency guard (S7.2 8p)."""

from __future__ import annotations

import contextlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from database.models import (
    ActivityRecord,
    ObjectRecord,
    Principal,
    Project,
    WorkflowState,
)
from database.models import Issue as IssueModel
from database.session import RLSContext, RLSSessionFactory, bind_rls_context
from kanban.services.activity import ActivityEventType, record_activity

logger = logging.getLogger(__name__)

AUTO_ARCHIVE_ADVISORY_LOCK_KEY: Final[str] = "kanban.auto_archive"
ARCHIVE_TERMINAL_GROUPS: Final[frozenset[str]] = frozenset({"completed", "cancelled"})


@dataclass(frozen=True, slots=True)
class AutoArchiveReport:
    """Execution summary report for auto-archive job."""

    projects_scanned: int
    issues_archived: int
    batches: int

    def to_dict(self) -> dict[str, int]:
        """Convert report to dictionary for JSON output."""
        return {
            "projects_scanned": self.projects_scanned,
            "issues_archived": self.issues_archived,
            "batches": self.batches,
        }


def _extract_engine(
    target: AsyncEngine | RLSSessionFactory | async_sessionmaker[AsyncSession] | Any,  # noqa: ANN401
) -> AsyncEngine:
    """Extract AsyncEngine from supported target types."""
    if isinstance(target, RLSSessionFactory):
        return target._engine  # noqa: SLF001
    if isinstance(target, AsyncEngine):
        return target
    raw_bind: Any = getattr(target, "kw", {}).get("bind", getattr(target, "_bind", None))
    if isinstance(raw_bind, AsyncEngine):
        return raw_bind
    msg = f"Cannot extract AsyncEngine from target {type(target)}"
    raise TypeError(msg)


async def _process_project_auto_archive(  # noqa: PLR0913
    session: AsyncSession,
    project_id: uuid.UUID,
    workspace_id: uuid.UUID,
    auto_archive_days: int,
    now: datetime,
    *,
    batch_size: int,
    commit_batches: bool,
) -> tuple[int, int]:
    """Process auto-archive batches for a single project.

    Returns (issues_archived_count, batches_count).
    """
    threshold = now - timedelta(days=auto_archive_days)

    # 1. Resolve or create system service principal for this workspace
    sp_stmt = select(Principal.id).where(
        Principal.workspace_id == workspace_id,
        Principal.principal_type == "SERVICE_PRINCIPAL",
        Principal.display_name == "system:auto-archive",
    )
    sp_row = (await session.execute(sp_stmt)).first()
    if sp_row is not None:
        sp_id = sp_row[0]
    else:
        sp_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'SERVICE_PRINCIPAL', 'system:auto-archive') "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": sp_id, "ws_id": workspace_id},
        )

    # 2. Grant workspace admin role binding so RLS permits access
    await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :sp_id, 'WORKSPACE_ADMIN', 'workspace', NULL) "
            "ON CONFLICT DO NOTHING"
        ),
        {"ws_id": workspace_id, "sp_id": sp_id},
    )

    # 3. Bind RLS context
    rls_ctx = RLSContext(
        principal_id=sp_id,
        workspace_id=workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    await bind_rls_context(session, rls_ctx)

    sub_issue = aliased(IssueModel)
    sub_object = aliased(ObjectRecord)
    sub_state = aliased(WorkflowState)

    open_subissues_exist = exists(
        select(1)
        .select_from(sub_issue)
        .join(sub_state, sub_state.id == sub_issue.state_id)
        .join(sub_object, sub_object.id == sub_issue.id)
        .where(
            sub_issue.parent_issue_id == IssueModel.id,
            sub_object.deleted_at.is_(None),
            sub_object.archived_at.is_(None),
            sub_state.state_group.notin_(ARCHIVE_TERMINAL_GROUPS),
        )
    )

    latest_state_change = (
        select(func.max(ActivityRecord.recorded_at))
        .where(
            ActivityRecord.object_id == IssueModel.id,
            ActivityRecord.event_type == ActivityEventType.ISSUE_STATE_CHANGED.value,
        )
        .scalar_subquery()
    )
    cutoff_time = func.coalesce(latest_state_change, ObjectRecord.created_at)

    project_archived = 0
    project_batches = 0

    while True:
        issue_query = (
            select(IssueModel.id)
            .join(ObjectRecord, ObjectRecord.id == IssueModel.id)
            .join(WorkflowState, WorkflowState.id == IssueModel.state_id)
            .where(
                IssueModel.project_id == project_id,
                ObjectRecord.deleted_at.is_(None),
                ObjectRecord.archived_at.is_(None),
                WorkflowState.state_group.in_(ARCHIVE_TERMINAL_GROUPS),
                cutoff_time <= threshold,
                ~open_subissues_exist,
            )
            .order_by(IssueModel.sequence_id)
            .limit(batch_size)
            .with_for_update(of=IssueModel, skip_locked=True)
        )

        batch_ids = list((await session.execute(issue_query)).scalars().all())
        if not batch_ids:
            break

        for issue_id in batch_ids:
            await session.execute(
                text("UPDATE objects SET archived_at = :now WHERE id = :id"),
                {"now": now, "id": issue_id},
            )
            await record_activity(
                session=session,
                workspace_id=workspace_id,
                object_id=issue_id,
                actor_principal_id=sp_id,
                event_type=ActivityEventType.ISSUE_ARCHIVED,
                payload={
                    "mode": "auto",
                    "source": "auto",
                    "threshold_days": auto_archive_days,
                },
            )

        project_archived += len(batch_ids)
        project_batches += 1

        await session.flush()
        if commit_batches:
            await session.commit()

        if len(batch_ids) < batch_size:
            break

    return project_archived, project_batches


async def _run_pass_with_session(
    session: AsyncSession,
    now: datetime,
    *,
    batch_size: int,
    commit_batches: bool,
) -> AutoArchiveReport:
    """Scan eligible projects and execute archive passes."""
    proj_stmt = (
        select(Project.id, Project.workspace_id, Project.identifier, Project.auto_archive_days)
        .join(ObjectRecord, ObjectRecord.id == Project.id)
        .where(
            Project.auto_archive_days.is_not(None),
            ObjectRecord.deleted_at.is_(None),
        )
        .order_by(Project.identifier)
    )
    eligible_projects = list((await session.execute(proj_stmt)).all())

    total_archived = 0
    total_batches = 0

    for proj_id, ws_id, _ident, auto_days in eligible_projects:
        p_archived, p_batches = await _process_project_auto_archive(
            session=session,
            project_id=proj_id,
            workspace_id=ws_id,
            auto_archive_days=auto_days,
            now=now,
            batch_size=batch_size,
            commit_batches=commit_batches,
        )
        total_archived += p_archived
        total_batches += p_batches

    return AutoArchiveReport(
        projects_scanned=len(eligible_projects),
        issues_archived=total_archived,
        batches=total_batches,
    )


async def run_auto_archive(
    target: AsyncEngine | RLSSessionFactory | async_sessionmaker[AsyncSession] | AsyncSession,
    now: datetime | None = None,
    *,
    batch_size: int = 500,
    commit_batches: bool | None = None,
) -> AutoArchiveReport:
    """Execute periodic auto-archive pass across all configured projects.

    Guarded by PostgreSQL single-runner advisory lock hashtext('kanban.auto_archive').
    """
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    if isinstance(target, AsyncSession):
        locked = bool(
            (
                await target.execute(
                    text("SELECT pg_try_advisory_lock(hashtext(:k))"),
                    {"k": AUTO_ARCHIVE_ADVISORY_LOCK_KEY},
                )
            ).scalar()
        )
        if not locked:
            return AutoArchiveReport(projects_scanned=0, issues_archived=0, batches=0)

        should_commit = commit_batches if commit_batches is not None else False
        try:
            return await _run_pass_with_session(
                target,
                now,
                batch_size=batch_size,
                commit_batches=should_commit,
            )
        finally:
            with contextlib.suppress(Exception):
                await target.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:k))"),
                    {"k": AUTO_ARCHIVE_ADVISORY_LOCK_KEY},
                )

    engine = _extract_engine(target)
    should_commit = commit_batches if commit_batches is not None else True
    async with AsyncSession(engine) as session:
        locked = bool(
            (
                await session.execute(
                    text("SELECT pg_try_advisory_lock(hashtext(:k))"),
                    {"k": AUTO_ARCHIVE_ADVISORY_LOCK_KEY},
                )
            ).scalar()
        )
        if not locked:
            return AutoArchiveReport(projects_scanned=0, issues_archived=0, batches=0)
        try:
            return await _run_pass_with_session(
                session,
                now,
                batch_size=batch_size,
                commit_batches=should_commit,
            )
        finally:
            with contextlib.suppress(Exception):
                await session.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:k))"),
                    {"k": AUTO_ARCHIVE_ADVISORY_LOCK_KEY},
                )


async def run_auto_archive_pass(
    target: AsyncEngine | RLSSessionFactory | async_sessionmaker[AsyncSession] | AsyncSession,
    now: datetime | None = None,
    *,
    batch_size: int = 500,
    commit_batches: bool | None = None,
) -> int:
    """Periodic auto-archive pass returning total count of archived issues."""
    report = await run_auto_archive(
        target,
        now=now,
        batch_size=batch_size,
        commit_batches=commit_batches,
    )
    return report.issues_archived
