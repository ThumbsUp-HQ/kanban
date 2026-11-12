"""Periodic trash retention purge background job with advisory lock concurrency guard.

Follows S7.2 8q and S12.3.
"""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from database.models import (
    Attachment,
    Issue,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    IssueModule,
    IssueSubscription,
    ObjectRecord,
    Principal,
    Project,
    Workspace,
)
from database.session import RLSContext, RLSSessionFactory, bind_rls_context, create_rls_engine
from kanban.services.activity import ActivityEventType, record_activity
from kanban.settings import get_settings

logger = logging.getLogger(__name__)

TRASH_PURGE_ADVISORY_LOCK_KEY: Final[str] = "kanban.trash_purge"


@dataclass(frozen=True, slots=True)
class PurgeReport:
    """Execution summary report for trash purge job."""

    issues_purged: int
    links_purged: int
    batches: int

    def to_dict(self) -> dict[str, int]:
        """Convert report to dictionary for JSON output."""
        return {
            "issues_purged": self.issues_purged,
            "links_purged": self.links_purged,
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


async def _process_trash_purge_batch(  # noqa: PLR0915
    session: AsyncSession,
    now: datetime,
    *,
    batch_size: int,
    commit_batches: bool,
) -> tuple[int, int, bool]:
    """Process a single batch of expired trashed issues.

    Returns (issues_purged_in_batch, links_purged_in_batch, has_more).
    """
    retention_days = get_settings().trash_retention_days
    threshold = now - timedelta(days=retention_days)

    # 1. Find batch of expired issues ordered deterministically
    stmt = (
        select(
            Issue.id,
            Issue.project_id,
            Issue.workspace_id,
            Issue.sequence_id,
            Project.identifier,
        )
        .join(ObjectRecord, ObjectRecord.id == Issue.id)
        .join(Project, Project.id == Issue.project_id)
        .where(
            ObjectRecord.deleted_at.is_not(None),
            ObjectRecord.deleted_at <= threshold,
        )
        .order_by(ObjectRecord.deleted_at.asc(), Issue.id.asc())
        .limit(batch_size)
    )
    expired_rows = (await session.execute(stmt)).all()
    if not expired_rows:
        return 0, 0, False

    # Group by workspace_id
    ws_issues: dict[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID, int, str]]] = {}
    for issue_id, proj_id, ws_id, seq_id, proj_ident in expired_rows:
        ws_issues.setdefault(ws_id, []).append((issue_id, proj_id, seq_id, proj_ident))

    batch_issues_purged = 0
    batch_links_purged = 0

    for ws_id, items in ws_issues.items():
        # Sync workspace trash_retention_days to match settings
        await session.execute(
            update(Workspace)
            .where(Workspace.id == ws_id)
            .values(trash_retention_days=retention_days)
        )

        # 2. Resolve or create system service principal for this workspace
        sp_stmt = select(Principal.id).where(
            Principal.workspace_id == ws_id,
            Principal.principal_type == "SERVICE_PRINCIPAL",
            Principal.display_name == "system:trash-purge",
        )
        sp_row = (await session.execute(sp_stmt)).first()
        if sp_row is not None:
            sp_id = sp_row[0]
        else:
            sp_id = uuid.uuid4()
            await session.execute(
                text(
                    "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                    "VALUES (:id, :ws_id, 'SERVICE_PRINCIPAL', 'system:trash-purge') "
                    "ON CONFLICT DO NOTHING"
                ),
                {"id": sp_id, "ws_id": ws_id},
            )

        # Grant WORKSPACE_ADMIN role binding so RLS permits access
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:ws_id, :sp_id, 'WORKSPACE_ADMIN', 'workspace', NULL) "
                "ON CONFLICT DO NOTHING"
            ),
            {"ws_id": ws_id, "sp_id": sp_id},
        )

        # Bind RLS context
        rls_ctx = RLSContext(
            principal_id=sp_id,
            workspace_id=ws_id,
            token_scopes=("session",),
            aal_level=1,
        )
        await bind_rls_context(session, rls_ctx)

        # 3. Count links touching each issue before purge
        issue_link_counts: dict[uuid.UUID, int] = {}
        for issue_id, _, _, _ in items:
            c_res = await session.execute(
                text(
                    "SELECT count(*) FROM object_links WHERE source_id = :oid OR target_id = :oid"
                ),
                {"oid": issue_id},
            )
            issue_link_counts[issue_id] = int(c_res.scalar_one())

        # 4. Run audit_object_links to detect invalid links
        audit_res = (
            await session.execute(
                text("SELECT audit_id, link_id, reason FROM audit_object_links(:ws_id, :now)"),
                {"ws_id": ws_id, "now": now},
            )
        ).all()
        detected_audit_ids = [row[0] for row in audit_res if row[0] is not None]

        # Also collect any open audit rows in this workspace
        open_audits_res = (
            (
                await session.execute(
                    text(
                        "SELECT id FROM invalid_object_link_audits "
                        "WHERE workspace_id = :ws_id AND purged_at IS NULL AND resolved_at IS NULL"
                    ),
                    {"ws_id": ws_id},
                )
            )
            .scalars()
            .all()
        )

        all_audits = sorted(set(detected_audit_ids + list(open_audits_res)))

        # 5. Call purge_invalid_object_links for all open audit ids
        if all_audits:
            for chunk_start in range(0, len(all_audits), 500):
                chunk = all_audits[chunk_start : chunk_start + 500]
                purge_res = (
                    await session.execute(
                        text(
                            "SELECT * FROM purge_invalid_object_links("
                            ":audit_ids, :actor_id, 'TRASH_RETENTION_EXPIRED')"
                        ),
                        {"audit_ids": chunk, "actor_id": sp_id},
                    )
                ).all()
                purged_links = {r[1] for r in purge_res if r[1] is not None}
                batch_links_purged += len(purged_links)

        # 6. Delete dependent rows and the issues + objects rows
        for issue_id, proj_id, seq_id, proj_ident in items:
            purged_for_issue = issue_link_counts.get(issue_id, 0)
            issue_key = f"{proj_ident}-{seq_id}"

            # Delete issue comments
            await session.execute(delete(IssueComment).where(IssueComment.issue_id == issue_id))

            # Delete issue assignees
            await session.execute(delete(IssueAssignee).where(IssueAssignee.issue_id == issue_id))

            # Delete issue labels
            await session.execute(delete(IssueLabel).where(IssueLabel.issue_id == issue_id))

            # Delete issue modules
            await session.execute(delete(IssueModule).where(IssueModule.issue_id == issue_id))

            # Delete issue subscriptions
            await session.execute(
                delete(IssueSubscription).where(IssueSubscription.issue_id == issue_id)
            )

            # Clear attachments.issue_id
            await session.execute(
                update(Attachment).where(Attachment.issue_id == issue_id).values(issue_id=None)
            )

            # Clear parent_issue_id on direct children
            await session.execute(
                update(Issue).where(Issue.parent_issue_id == issue_id).values(parent_issue_id=None)
            )

            # Clear ACL entries, effective access, and embeddings
            await session.execute(
                text("DELETE FROM resource_acl_entries WHERE object_id = :oid"),
                {"oid": issue_id},
            )
            await session.execute(
                text("DELETE FROM effective_resource_access WHERE object_id = :oid"),
                {"oid": issue_id},
            )
            await session.execute(
                text("DELETE FROM object_embeddings WHERE object_id = :oid"),
                {"oid": issue_id},
            )

            # Delete issues row
            await session.execute(delete(Issue).where(Issue.id == issue_id))

            # Delete objects row
            await session.execute(delete(ObjectRecord).where(ObjectRecord.id == issue_id))

            # Emit ISSUE_PURGED activity event against the project object
            await record_activity(
                session=session,
                workspace_id=ws_id,
                object_id=proj_id,
                actor_principal_id=sp_id,
                event_type=ActivityEventType.ISSUE_PURGED,
                payload={
                    "issue_key": issue_key,
                    "purged_link_count": purged_for_issue,
                },
            )

            batch_issues_purged += 1

    if commit_batches:
        await session.commit()

    return batch_issues_purged, batch_links_purged, len(expired_rows) >= batch_size


async def _run_pass_with_session(
    session: AsyncSession,
    now: datetime,
    *,
    batch_size: int,
    commit_batches: bool,
) -> PurgeReport:
    """Execute trash purge loop on an existing session."""
    total_issues = 0
    total_links = 0
    total_batches = 0

    while True:
        p_issues, p_links, has_more = await _process_trash_purge_batch(
            session,
            now,
            batch_size=batch_size,
            commit_batches=commit_batches,
        )
        if p_issues == 0:
            break
        total_issues += p_issues
        total_links += p_links
        total_batches += 1
        if not has_more:
            break

    return PurgeReport(
        issues_purged=total_issues,
        links_purged=total_links,
        batches=total_batches,
    )


async def run_trash_purge(
    target_or_now: (
        AsyncEngine
        | RLSSessionFactory
        | async_sessionmaker[AsyncSession]
        | AsyncSession
        | datetime
        | None
    ) = None,
    now: datetime | None = None,
    *,
    batch_size: int = 100,
    commit_batches: bool | None = None,
) -> PurgeReport:
    """Execute periodic trash retention purge pass for expired issues.

    Guarded by PostgreSQL single-runner advisory lock hashtext('kanban.trash_purge').
    """
    if isinstance(target_or_now, datetime):
        now = target_or_now
        target = None
    else:
        target = target_or_now

    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    if target is None:
        dsn = (
            os.environ.get("KANBAN_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or getattr(get_settings(), "database_url", None)
        )
        if not dsn:
            msg = "Target engine or KANBAN_DATABASE_URL must be provided"
            raise ValueError(msg)
        target = create_rls_engine(str(dsn))

    if isinstance(target, AsyncSession):
        locked = bool(
            (
                await target.execute(
                    text("SELECT pg_try_advisory_lock(hashtext(:k))"),
                    {"k": TRASH_PURGE_ADVISORY_LOCK_KEY},
                )
            ).scalar()
        )
        if not locked:
            logger.info("Trash purge advisory lock held by another worker; skipping run.")
            return PurgeReport(issues_purged=0, links_purged=0, batches=0)

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
                    {"k": TRASH_PURGE_ADVISORY_LOCK_KEY},
                )

    engine = _extract_engine(target)
    should_commit = commit_batches if commit_batches is not None else True
    async with AsyncSession(engine) as session:
        locked = bool(
            (
                await session.execute(
                    text("SELECT pg_try_advisory_lock(hashtext(:k))"),
                    {"k": TRASH_PURGE_ADVISORY_LOCK_KEY},
                )
            ).scalar()
        )
        if not locked:
            logger.info("Trash purge advisory lock held by another worker; skipping run.")
            return PurgeReport(issues_purged=0, links_purged=0, batches=0)
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
                    {"k": TRASH_PURGE_ADVISORY_LOCK_KEY},
                )


async def run_trash_purge_pass(
    target: AsyncEngine | RLSSessionFactory | async_sessionmaker[AsyncSession] | AsyncSession,
    now: datetime | None = None,
    *,
    batch_size: int = 100,
    commit_batches: bool | None = None,
) -> int:
    """Periodic trash purge pass returning total count of purged issues."""
    report = await run_trash_purge(
        target,
        now=now,
        batch_size=batch_size,
        commit_batches=commit_batches,
    )
    return report.issues_purged
