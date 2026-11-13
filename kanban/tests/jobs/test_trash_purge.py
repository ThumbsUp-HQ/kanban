"""Unit tests for periodic trash retention purge background job and CLI (S7.2 8q; KB-P3-09b)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession as AsyncSessionCls,
)

from database.models import (
    ActivityRecord,
    Issue,
    LinkKind,
    ObjectKind,
    ObjectLink,
    ObjectRecord,
)
from database.session import RLSSessionFactory
from kanban.cli.ctl import main as ctl_main
from kanban.jobs import (
    PurgeReport,
    registry,
    run_trash_purge,
    run_trash_purge_pass,
)
from kanban.jobs.trash_purge import _extract_engine

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def _make_link(  # noqa: PLR0913, PLR0917
    seed: AsyncSession,
    ws_id: uuid.UUID,
    source_id: uuid.UUID,
    source_key: str,
    target_id: uuid.UUID,
    target_key: str,
    creator_id: uuid.UUID,
    link_type: LinkKind = LinkKind.RELATES_TO,
) -> uuid.UUID:
    """Create an ACTIVE object_link directly in the seed session."""
    link_id = uuid.uuid4()
    link = ObjectLink(
        id=link_id,
        workspace_id=ws_id,
        source_id=source_id,
        source_type=ObjectKind.ISSUE,
        target_id=target_id,
        target_type=ObjectKind.ISSUE,
        link_type=link_type,
        link_state="ACTIVE",
        source_key_snapshot=source_key,
        target_key_snapshot=target_key,
        created_by_id=creator_id,
    )
    seed.add(link)
    await seed.commit()
    return link_id


async def test_case_5_trash_purge_expired_vs_unexpired(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 5: Issue trashed 31d ago with links is purged via audited purge; 29d issue remains."""
    admin = await make_user("purge_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("PURGE", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create target issue 1 (to be expired at 31 days ago)
    r1 = await client.post(
        "/api/v1/projects/PURGE/issues",
        json={"summary": "Expired Issue 31d"},
    )
    assert r1.status_code == 201
    i1_key = r1.json()["key"]
    i1_id = uuid.UUID(r1.json()["id"])

    # 2. Create target issue 2 (to be unexpired at 29 days ago)
    r2 = await client.post(
        "/api/v1/projects/PURGE/issues",
        json={"summary": "Unexpired Issue 29d"},
    )
    assert r2.status_code == 201
    i2_key = r2.json()["key"]
    i2_id = uuid.UUID(r2.json()["id"])

    # 3. Create a bystander issue to link with both
    r3 = await client.post(
        "/api/v1/projects/PURGE/issues",
        json={"summary": "Bystander Issue"},
    )
    assert r3.status_code == 201
    i3_key = r3.json()["key"]
    i3_id = uuid.UUID(r3.json()["id"])

    # Add active links to both issues
    await _make_link(
        seed=api_env.seed,
        ws_id=api_env.workspace_id,
        source_id=i3_id,
        source_key=i3_key,
        target_id=i1_id,
        target_key=i1_key,
        creator_id=admin.id,
    )
    await _make_link(
        seed=api_env.seed,
        ws_id=api_env.workspace_id,
        source_id=i3_id,
        source_key=i3_key,
        target_id=i2_id,
        target_key=i2_key,
        creator_id=admin.id,
    )

    now = datetime.now(UTC)
    t31 = now - timedelta(days=31)
    t29 = now - timedelta(days=29)

    # Soft-delete i1 at 31 days ago, i2 at 29 days ago
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = :ts WHERE id = :oid"),
        {"ts": t31, "oid": i1_id},
    )
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = :ts WHERE id = :oid"),
        {"ts": t29, "oid": i2_id},
    )
    await api_env.seed.commit()

    # 4. Run trash purge job
    engine = api_env.seed.bind
    assert isinstance(engine, AsyncEngine)
    report = await run_trash_purge(engine, now=now, batch_size=10)

    assert report.issues_purged >= 1
    assert report.links_purged >= 1

    # 5. Verify i1 is completely removed from issues and objects
    await api_env.seed.rollback()
    i1_exists_issue = (
        await api_env.seed.execute(select(Issue.id).where(Issue.id == i1_id))
    ).first()
    i1_exists_obj = (
        await api_env.seed.execute(select(ObjectRecord.id).where(ObjectRecord.id == i1_id))
    ).first()
    assert i1_exists_issue is None
    assert i1_exists_obj is None

    # 6. Verify i2 (29 days ago) remains in issues and objects
    i2_exists_issue = (
        await api_env.seed.execute(select(Issue.id).where(Issue.id == i2_id))
    ).first()
    i2_exists_obj = (
        await api_env.seed.execute(select(ObjectRecord.id).where(ObjectRecord.id == i2_id))
    ).first()
    assert i2_exists_issue is not None
    assert i2_exists_obj is not None

    # 7. Verify INVALID_OBJECT_LINK_PURGED activity row exists
    link_purged_act = (
        await api_env.seed.execute(
            select(ActivityRecord.id).where(
                ActivityRecord.event_type == "INVALID_OBJECT_LINK_PURGED"
            )
        )
    ).first()
    assert link_purged_act is not None

    # 8. Verify ISSUE_PURGED activity row exists against the project object
    issue_purged_act = (
        await api_env.seed.execute(
            select(ActivityRecord.payload).where(
                ActivityRecord.object_id == proj_id,
                ActivityRecord.event_type == "ISSUE_PURGED",
            )
        )
    ).scalar_one_or_none()
    assert issue_purged_act is not None
    assert issue_purged_act["issue_key"] == i1_key
    assert issue_purged_act["purged_link_count"] >= 1


async def test_case_5_advisory_lock_concurrency(
    api_env: ApiEnv,
) -> None:
    """Case 5: Single-runner advisory lock prevents concurrent execution."""
    # Acquire advisory lock manually
    locked = bool(
        (
            await api_env.seed.execute(
                text("SELECT pg_try_advisory_lock(hashtext('kanban.trash_purge'))")
            )
        ).scalar()
    )
    assert locked is True

    try:
        engine = api_env.seed.bind
        assert isinstance(engine, AsyncEngine)

        # Attempt trash purge while lock is held (engine target)
        report = await run_trash_purge(engine, batch_size=10)
        assert report.issues_purged == 0
        assert report.links_purged == 0
        assert report.batches == 0

        # Attempt trash purge while lock is held (second session target on engine)
        async with AsyncSessionCls(engine) as second_sess:
            report_sess = await run_trash_purge(second_sess, batch_size=10)
            assert report_sess.issues_purged == 0
            assert report_sess.links_purged == 0
            assert report_sess.batches == 0

        # Also verify run_trash_purge_pass returns 0
        count = await run_trash_purge_pass(engine, batch_size=10)
        assert count == 0
    finally:
        # Release the advisory lock
        unlock_res = await api_env.seed.execute(
            text("SELECT pg_advisory_unlock(hashtext('kanban.trash_purge'))")
        )
        assert unlock_res.scalar() is True


async def test_case_5_cli(
    api_env: ApiEnv,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 5: kanban-ctl jobs run trash-purge --now exits 0 and prints JSON report."""
    engine = api_env.seed.bind
    assert isinstance(engine, AsyncEngine)
    dsn = str(engine.url)
    monkeypatch.setenv("KANBAN_DATABASE_URL", dsn)

    # 1. Successful run with valid ISO timestamp
    exit_code = ctl_main(["jobs", "run", "trash-purge", "--now", "2026-11-12T00:00:00Z"])
    assert exit_code == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert "issues_purged" in report
    assert "links_purged" in report
    assert "batches" in report

    # 2. Invalid ISO timestamp returns exit code 2
    err_code = ctl_main(["jobs", "run", "trash-purge", "--now", "invalid-date"])
    assert err_code == 2
    err_captured = capsys.readouterr()
    assert "Invalid --now timestamp" in err_captured.err

    # 3. DB failure returns exit code 1
    fail_dsn = "postgresql+asyncpg://kanban_test@/nonexistent_db?host=/tmp/nonexistent"
    monkeypatch.setenv("KANBAN_DATABASE_URL", fail_dsn)
    fail_code = ctl_main(["jobs", "run", "trash-purge"])
    assert fail_code == 1
    fail_captured = capsys.readouterr()
    assert "Trash-purge failed" in fail_captured.err


def test_registry_registration() -> None:
    """Verify trash_purge is registered in global registry."""
    job_def = registry.get("trash_purge")
    assert job_def is not None
    assert job_def.name == "trash_purge"
    assert job_def.interval_seconds == 3600.0


async def test_purge_engine_targets_and_type_error(api_env: ApiEnv) -> None:
    """Test _extract_engine with RLSSessionFactory, async_sessionmaker and TypeError."""
    engine = api_env.seed.bind
    assert isinstance(engine, AsyncEngine)

    # 1. RLSSessionFactory target
    factory = RLSSessionFactory(engine)
    assert _extract_engine(factory) is engine

    # 2. async_sessionmaker target
    maker = async_sessionmaker(engine)
    assert _extract_engine(maker) is engine

    # 3. Invalid target raises TypeError
    with pytest.raises(TypeError, match="Cannot extract AsyncEngine"):
        _extract_engine(12345)


async def test_purge_issue_without_links_and_naive_datetime(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test purging an issue that has no links (covers empty audits branch) and naive datetime."""
    admin = await make_user("nolink_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("NOLNK", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Create issue with no links
    r = await client.post("/api/v1/projects/NOLNK/issues", json={"summary": "No Links Issue"})
    assert r.status_code == 201
    i_id = uuid.UUID(r.json()["id"])

    # Trash it at 35 days ago
    t35 = datetime.now(UTC) - timedelta(days=35)
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = :ts WHERE id = :oid"),
        {"ts": t35, "oid": i_id},
    )
    await api_env.seed.commit()

    # Run trash purge with session target and naive datetime
    naive_now = datetime.now(UTC).replace(tzinfo=None)
    rep = await run_trash_purge(api_env.seed, now=naive_now)
    assert rep.issues_purged >= 1
    assert rep.links_purged == 0


async def test_purge_target_none_and_existing_sp(
    api_env: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test passing datetime as first positional arg with target None and existing SP."""
    engine = api_env.seed.bind
    assert isinstance(engine, AsyncEngine)
    monkeypatch.setenv("KANBAN_DATABASE_URL", str(engine.url))

    # 1. Target is None, now passed as first arg
    now = datetime.now(UTC)
    rep1 = await run_trash_purge(now)
    assert isinstance(rep1, PurgeReport)

    # 2. Second run on session where system:trash-purge SP already exists (line 129)
    rep2 = await run_trash_purge(api_env.seed, now=now)
    assert isinstance(rep2, PurgeReport)


async def test_unrelated_flagged_link_survives_trash_purge(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test that an unrelated FLAGGED_INVALID link survives the purge and stays open (B1)."""
    admin = await make_user("unrel_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("UNREL", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create two active issues with an active link between them
    r1 = await client.post("/api/v1/projects/UNREL/issues", json={"summary": "Active 1"})
    assert r1.status_code == 201
    i1_id = uuid.UUID(r1.json()["id"])
    i1_key = r1.json()["key"]

    r2 = await client.post("/api/v1/projects/UNREL/issues", json={"summary": "Active 2"})
    assert r2.status_code == 201
    i2_id = uuid.UUID(r2.json()["id"])
    i2_key = r2.json()["key"]

    unrel_link_id = await _make_link(
        api_env.seed,
        api_env.workspace_id,
        source_id=i1_id,
        source_key=i1_key,
        target_id=i2_id,
        target_key=i2_key,
        creator_id=admin.id,
        link_type=LinkKind.BLOCKS,
    )

    # 2. Archive i1 with active uncompleted target i2
    # Trigger automatically detects ARCHIVED_POLICY_VIOLATION and inserts an open audit row
    await api_env.seed.execute(
        text("UPDATE objects SET archived_at = now() WHERE id = :oid"),
        {"oid": i1_id},
    )
    await api_env.seed.commit()

    audit_row_init = (
        await api_env.seed.execute(
            text(
                "SELECT id FROM invalid_object_link_audits "
                "WHERE link_id = :lid AND purged_at IS NULL AND resolved_at IS NULL"
            ),
            {"lid": unrel_link_id},
        )
    ).first()
    assert audit_row_init is not None
    unrel_audit_id = audit_row_init[0]

    # 3. Create an expired issue (35 days ago) with its own link
    r3 = await client.post("/api/v1/projects/UNREL/issues", json={"summary": "Expired Issue"})
    assert r3.status_code == 201
    exp_id = uuid.UUID(r3.json()["id"])
    exp_key = r3.json()["key"]

    await _make_link(
        api_env.seed,
        api_env.workspace_id,
        source_id=exp_id,
        source_key=exp_key,
        target_id=i1_id,
        target_key=i1_key,
        creator_id=admin.id,
    )

    t35 = datetime.now(UTC) - timedelta(days=35)
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = :ts WHERE id = :oid"),
        {"ts": t35, "oid": exp_id},
    )
    await api_env.seed.commit()

    # 4. Run trash purge
    now = datetime.now(UTC)
    engine = api_env.seed.bind
    assert isinstance(engine, AsyncEngine)
    rep = await run_trash_purge(engine, now=now, batch_size=10)
    assert rep.issues_purged >= 1
    assert rep.links_purged >= 1

    # 5. Verify the unrelated audit row survived and remains open (purged_at IS NULL)
    audit_row = (
        await api_env.seed.execute(
            text("SELECT purged_at, resolved_at FROM invalid_object_link_audits WHERE id = :aid"),
            {"aid": unrel_audit_id},
        )
    ).first()
    assert audit_row is not None
    assert audit_row[0] is None  # purged_at IS NULL
    assert audit_row[1] is None  # resolved_at IS NULL

    # 6. Verify the unrelated link still exists in object_links
    link_row = (
        await api_env.seed.execute(select(ObjectLink.id).where(ObjectLink.id == unrel_link_id))
    ).first()
    assert link_row is not None
