"""Periodic trash retention purge background job with advisory lock concurrency guard.

Follows S7.2 8q and S12.3.
"""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from database.models import (
    Attachment,
    Cycle,
    Doc,
    Issue,
    IssueAssignee,
    IssueComment,
    IssueLabel,
    IssueModule,
    IssueSubscription,
    Module,
    ObjectKind,
    ObjectRecord,
    Page,
    Principal,
    Project,
    ProjectLabel,
    ProjectModuleDefault,
    ProjectPriority,
    Sticky,
    View,
    WorkflowState,
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
    objects_purged: int = 0

    def to_dict(self) -> dict[str, int]:
        """Convert report to dictionary for JSON output."""
        return {
            "issues_purged": self.issues_purged,
            "links_purged": self.links_purged,
            "batches": self.batches,
            "objects_purged": self.objects_purged,
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


async def _process_trash_purge_batch(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    now: datetime,
    *,
    batch_size: int,
    commit_batches: bool,
) -> tuple[int, int, int, bool]:
    """Process a single batch of expired trashed objects across all entity types.

    Returns (issues_purged_in_batch, links_purged_in_batch, objects_purged_in_batch, has_more).
    """
    # 1. Find batch of expired objects ordered deterministically by deleted_at and id
    stmt = (
        select(
            ObjectRecord.id,
            ObjectRecord.workspace_id,
            ObjectRecord.project_id,
            ObjectRecord.object_type,
            ObjectRecord.canonical_key,
            ObjectRecord.deleted_at,
        )
        .join(Workspace, Workspace.id == ObjectRecord.workspace_id)
        .where(
            ObjectRecord.deleted_at.is_not(None),
            ObjectRecord.deleted_at
            + func.make_interval(0, 0, 0, func.coalesce(Workspace.trash_retention_days, 30))
            <= now,
        )
        .order_by(ObjectRecord.deleted_at.asc(), ObjectRecord.id.asc())
        .limit(batch_size)
    )
    expired_rows = (await session.execute(stmt)).all()
    if not expired_rows:
        return 0, 0, 0, False

    # Group by workspace_id
    ws_objects: dict[
        uuid.UUID, list[tuple[uuid.UUID, uuid.UUID | None, ObjectKind, str | None]]
    ] = {}
    for obj_id, ws_id, proj_id, obj_type, canon_key, _del_at in expired_rows:
        ws_objects.setdefault(ws_id, []).append((obj_id, proj_id, obj_type, canon_key))

    batch_issues_purged = 0
    batch_links_purged = 0
    batch_objects_purged = 0

    for ws_id, items in ws_objects.items():
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

        batch_obj_ids = [item[0] for item in items]
        batch_obj_set = set(batch_obj_ids)

        # 3. Run audit_object_links to detect invalid links across the workspace
        await session.execute(
            text("SELECT audit_id, link_id, reason FROM audit_object_links(:ws_id, :now)"),
            {"ws_id": ws_id, "now": now},
        )

        # 4. Restrict purge strictly to open audits whose links touch the expired
        # object IDs in this batch (S12.3 / AGENTS invariant 5)
        touching_audits_stmt = text(
            "SELECT a.id, a.link_id, l.source_id, l.target_id "
            "FROM invalid_object_link_audits a "
            "JOIN object_links l ON l.id = a.link_id "
            "WHERE a.workspace_id = :ws_id "
            "  AND a.purged_at IS NULL "
            "  AND a.resolved_at IS NULL "
            "  AND (l.source_id = ANY(:obj_ids) OR l.target_id = ANY(:obj_ids))"
        )
        touching_audits_res = (
            await session.execute(
                touching_audits_stmt,
                {"ws_id": ws_id, "obj_ids": batch_obj_ids},
            )
        ).all()

        link_to_objects: dict[uuid.UUID, set[uuid.UUID]] = {}
        target_audit_ids: set[uuid.UUID] = set()
        for aud_id, lnk_id, src_id, tgt_id in touching_audits_res:
            target_audit_ids.add(aud_id)
            link_to_objects.setdefault(lnk_id, set())
            if src_id in batch_obj_set:
                link_to_objects[lnk_id].add(src_id)
            if tgt_id in batch_obj_set:
                link_to_objects[lnk_id].add(tgt_id)

        all_audits = sorted(target_audit_ids)
        purged_links_for_batch: set[uuid.UUID] = set()
        purged_counts_per_obj: dict[uuid.UUID, int] = dict.fromkeys(batch_obj_ids, 0)

        # 5. Call purge_invalid_object_links for audits touching this batch's objects
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
                for r in purge_res:
                    pl_id = r[1]
                    if pl_id is not None and pl_id not in purged_links_for_batch:
                        purged_links_for_batch.add(pl_id)
                        if pl_id in link_to_objects:
                            for aff_obj in link_to_objects[pl_id]:
                                purged_counts_per_obj[aff_obj] += 1
            batch_links_purged += len(purged_links_for_batch)

        # 6. Delete dependent rows and entity rows + objects row for each expired entity
        for obj_id, proj_id, obj_type, canon_key in items:
            purged_for_obj = purged_counts_per_obj.get(obj_id, 0)

            # Clear ACL entries, effective access, and embeddings for all object types
            await session.execute(
                text("DELETE FROM resource_acl_entries WHERE object_id = :oid"),
                {"oid": obj_id},
            )
            await session.execute(
                text("DELETE FROM effective_resource_access WHERE object_id = :oid"),
                {"oid": obj_id},
            )
            await session.execute(
                text("DELETE FROM object_embeddings WHERE object_id = :oid"),
                {"oid": obj_id},
            )

            if obj_type == ObjectKind.ISSUE:
                iss_stmt = (
                    select(Issue.sequence_id, Issue.project_id, Project.identifier)
                    .join(Project, Project.id == Issue.project_id)
                    .where(Issue.id == obj_id)
                )
                iss_row = (await session.execute(iss_stmt)).first()
                issue_key = canon_key or (f"{iss_row[2]}-{iss_row[0]}" if iss_row else str(obj_id))
                target_proj_id = proj_id or (iss_row[1] if iss_row else None)

                await session.execute(delete(IssueComment).where(IssueComment.issue_id == obj_id))
                await session.execute(delete(IssueAssignee).where(IssueAssignee.issue_id == obj_id))
                await session.execute(delete(IssueLabel).where(IssueLabel.issue_id == obj_id))
                await session.execute(delete(IssueModule).where(IssueModule.issue_id == obj_id))
                await session.execute(
                    delete(IssueSubscription).where(IssueSubscription.issue_id == obj_id)
                )
                await session.execute(
                    update(Attachment).where(Attachment.issue_id == obj_id).values(issue_id=None)
                )
                await session.execute(
                    update(Issue)
                    .where(Issue.parent_issue_id == obj_id)
                    .values(parent_issue_id=None)
                )
                await session.execute(delete(Issue).where(Issue.id == obj_id))
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id == obj_id))

                if target_proj_id is not None:
                    await record_activity(
                        session=session,
                        workspace_id=ws_id,
                        object_id=target_proj_id,
                        actor_principal_id=sp_id,
                        event_type=ActivityEventType.ISSUE_PURGED,
                        payload={
                            "issue_key": issue_key,
                            "purged_link_count": purged_for_obj,
                        },
                    )
                batch_issues_purged += 1

            elif obj_type == ObjectKind.PAGE:
                desc_res = await session.execute(
                    text(
                        "SELECT id FROM pages "
                        "WHERE doc_id = (SELECT doc_id FROM pages WHERE id = :p_id) "
                        "  AND hierarchy_path <@ "
                        "(SELECT hierarchy_path FROM pages WHERE id = :p_id)"
                    ),
                    {"p_id": obj_id},
                )
                desc_ids = list(desc_res.scalars().all())
                all_page_ids = [obj_id, *[p for p in desc_ids if p != obj_id]]
                for pid in reversed(all_page_ids):
                    await session.execute(delete(Page).where(Page.id == pid))
                    await session.execute(delete(ObjectRecord).where(ObjectRecord.id == pid))

            elif obj_type == ObjectKind.DOC:
                pages_res = await session.execute(select(Page.id).where(Page.doc_id == obj_id))
                doc_page_ids = list(pages_res.scalars().all())
                if doc_page_ids:
                    for pid in doc_page_ids:
                        await session.execute(delete(Page).where(Page.id == pid))
                        await session.execute(delete(ObjectRecord).where(ObjectRecord.id == pid))
                await session.execute(delete(Doc).where(Doc.id == obj_id))
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id == obj_id))

            elif obj_type == ObjectKind.STICKY:
                await session.execute(delete(Sticky).where(Sticky.id == obj_id))
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id == obj_id))

            elif obj_type == ObjectKind.CYCLE:
                await session.execute(
                    text("UPDATE issues SET cycle_id = NULL WHERE cycle_id = :cid"),
                    {"cid": obj_id},
                )
                await session.execute(delete(Cycle).where(Cycle.id == obj_id))
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id == obj_id))

            elif obj_type == ObjectKind.MODULE:
                await session.execute(delete(IssueModule).where(IssueModule.module_id == obj_id))
                await session.execute(
                    delete(ProjectModuleDefault).where(ProjectModuleDefault.module_id == obj_id)
                )
                await session.execute(delete(Module).where(Module.id == obj_id))
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id == obj_id))

            elif obj_type == ObjectKind.VIEW:
                await session.execute(delete(View).where(View.id == obj_id))
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id == obj_id))

            elif obj_type == ObjectKind.PROJECT:
                issues_res = await session.execute(
                    select(Issue.id).where(Issue.project_id == obj_id)
                )
                proj_issue_ids = list(issues_res.scalars().all())
                if proj_issue_ids:
                    await session.execute(
                        delete(IssueComment).where(IssueComment.issue_id.in_(proj_issue_ids))
                    )
                    await session.execute(
                        delete(IssueAssignee).where(IssueAssignee.issue_id.in_(proj_issue_ids))
                    )
                    await session.execute(
                        delete(IssueLabel).where(IssueLabel.issue_id.in_(proj_issue_ids))
                    )
                    await session.execute(
                        delete(IssueModule).where(IssueModule.issue_id.in_(proj_issue_ids))
                    )
                    await session.execute(
                        delete(IssueSubscription).where(
                            IssueSubscription.issue_id.in_(proj_issue_ids)
                        )
                    )
                    await session.execute(delete(Issue).where(Issue.id.in_(proj_issue_ids)))
                    await session.execute(
                        delete(ObjectRecord).where(ObjectRecord.id.in_(proj_issue_ids))
                    )

                docs_res = await session.execute(select(Doc.id).where(Doc.project_id == obj_id))
                proj_doc_ids = list(docs_res.scalars().all())
                if proj_doc_ids:
                    pages_res = await session.execute(
                        select(Page.id).where(Page.doc_id.in_(proj_doc_ids))
                    )
                    proj_page_ids = list(pages_res.scalars().all())
                    if proj_page_ids:
                        await session.execute(delete(Page).where(Page.id.in_(proj_page_ids)))
                        await session.execute(
                            delete(ObjectRecord).where(ObjectRecord.id.in_(proj_page_ids))
                        )
                    await session.execute(delete(Doc).where(Doc.id.in_(proj_doc_ids)))
                    await session.execute(
                        delete(ObjectRecord).where(ObjectRecord.id.in_(proj_doc_ids))
                    )

                stickies_res = await session.execute(
                    select(Sticky.id).where(Sticky.project_id == obj_id)
                )
                proj_sticky_ids = list(stickies_res.scalars().all())
                if proj_sticky_ids:
                    await session.execute(delete(Sticky).where(Sticky.id.in_(proj_sticky_ids)))
                    await session.execute(
                        delete(ObjectRecord).where(ObjectRecord.id.in_(proj_sticky_ids))
                    )

                cycles_res = await session.execute(
                    select(Cycle.id).where(Cycle.project_id == obj_id)
                )
                proj_cycle_ids = list(cycles_res.scalars().all())
                if proj_cycle_ids:
                    await session.execute(delete(Cycle).where(Cycle.id.in_(proj_cycle_ids)))
                    await session.execute(
                        delete(ObjectRecord).where(ObjectRecord.id.in_(proj_cycle_ids))
                    )

                modules_res = await session.execute(
                    select(Module.id).where(Module.project_id == obj_id)
                )
                proj_mod_ids = list(modules_res.scalars().all())
                if proj_mod_ids:
                    await session.execute(
                        delete(ProjectModuleDefault).where(
                            ProjectModuleDefault.module_id.in_(proj_mod_ids)
                        )
                    )
                    await session.execute(
                        delete(IssueModule).where(IssueModule.module_id.in_(proj_mod_ids))
                    )
                    await session.execute(delete(Module).where(Module.id.in_(proj_mod_ids)))
                    await session.execute(
                        delete(ObjectRecord).where(ObjectRecord.id.in_(proj_mod_ids))
                    )

                views_res = await session.execute(select(View.id).where(View.project_id == obj_id))
                proj_view_ids = list(views_res.scalars().all())
                if proj_view_ids:
                    await session.execute(delete(View).where(View.id.in_(proj_view_ids)))
                    await session.execute(
                        delete(ObjectRecord).where(ObjectRecord.id.in_(proj_view_ids))
                    )

                await session.execute(text("SET LOCAL kanban.allow_project_delete = 'on'"))
                await session.execute(
                    delete(ProjectModuleDefault).where(ProjectModuleDefault.project_id == obj_id)
                )
                await session.execute(
                    delete(ProjectPriority).where(ProjectPriority.project_id == obj_id)
                )
                await session.execute(delete(ProjectLabel).where(ProjectLabel.project_id == obj_id))
                await session.execute(
                    delete(WorkflowState).where(WorkflowState.project_id == obj_id)
                )
                await session.execute(delete(Project).where(Project.id == obj_id))
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id == obj_id))

            else:
                await session.execute(delete(ObjectRecord).where(ObjectRecord.id == obj_id))

            batch_objects_purged += 1

    if commit_batches:
        await session.commit()

    return (
        batch_issues_purged,
        batch_links_purged,
        batch_objects_purged,
        len(expired_rows) >= batch_size,
    )


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
    total_objects = 0
    total_batches = 0

    while True:
        p_issues, p_links, p_objects, has_more = await _process_trash_purge_batch(
            session,
            now,
            batch_size=batch_size,
            commit_batches=commit_batches,
        )
        if p_objects == 0:
            break
        total_issues += p_issues
        total_links += p_links
        total_objects += p_objects
        total_batches += 1
        if not has_more:
            break

    return PurgeReport(
        issues_purged=total_issues,
        links_purged=total_links,
        batches=total_batches,
        objects_purged=total_objects,
    )


async def run_trash_purge(  # noqa: PLR0912
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

    created_engine = False
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
        created_engine = True

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
    try:
        async with (
            engine.connect() as conn,
            AsyncSession(bind=conn, expire_on_commit=False) as session,
        ):
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
                    await conn.execute(
                        text("SELECT pg_advisory_unlock(hashtext(:k))"),
                        {"k": TRASH_PURGE_ADVISORY_LOCK_KEY},
                    )
                    await conn.commit()
    finally:
        if created_engine:
            await engine.dispose()


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
