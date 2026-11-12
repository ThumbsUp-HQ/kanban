"""Unit tests for periodic auto-archive background job and CLI (S7.2 8p; KB-P3-09a)."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from database.models import ObjectRecord, WorkflowState
from database.session import RLSSessionFactory
from kanban.cli.ctl import main as ctl_main
from kanban.jobs import (
    JobRegistry,
    JobScheduler,
    lifespan,
    registry,
    run_auto_archive,
    run_auto_archive_pass,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def test_case_4_job_boundary(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 4: auto_archive_days=7; completed 7d ago is archived, 6d23h is not."""
    admin = await make_user("job_admin", workspace_role="WORKSPACE_ADMIN")
    p7_id = await make_project("ARC7", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    pnull_id = await make_project("ARCN", created_by=admin, roles={admin: "PROJECT_ADMIN"})

    # Configure auto_archive_days = 7 on ARC7 and ensure NULL on ARCN
    await api_env.seed.execute(
        text("UPDATE projects SET auto_archive_days = 7 WHERE id = :id"),
        {"id": p7_id},
    )
    await api_env.seed.execute(
        text("UPDATE projects SET auto_archive_days = NULL WHERE id = :id"),
        {"id": pnull_id},
    )
    await api_env.seed.commit()

    # Fetch states for ARC7
    done_row = (
        await api_env.seed.execute(
            select(WorkflowState.id).where(
                WorkflowState.project_id == p7_id,
                WorkflowState.state_group == "completed",
            )
        )
    ).first()
    assert done_row is not None
    done_state_id = done_row[0]

    cancel_row = (
        await api_env.seed.execute(
            select(WorkflowState.id).where(
                WorkflowState.project_id == p7_id,
                WorkflowState.state_group == "cancelled",
            )
        )
    ).first()
    assert cancel_row is not None
    cancel_state_id = cancel_row[0]

    todo_row = (
        await api_env.seed.execute(
            select(WorkflowState.id).where(
                WorkflowState.project_id == p7_id,
                WorkflowState.state_group == "unstarted",
            )
        )
    ).first()
    assert todo_row is not None
    todo_state_id = todo_row[0]

    # Fetch Done state for ARCN
    done_null_row = (
        await api_env.seed.execute(
            select(WorkflowState.id).where(
                WorkflowState.project_id == pnull_id,
                WorkflowState.state_group == "completed",
            )
        )
    ).first()
    assert done_null_row is not None
    done_null_state_id = done_null_row[0]

    client = as_principal(admin)
    ref_now = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)
    t_exact_7d = ref_now - timedelta(days=7)
    t_6d23h = ref_now - timedelta(days=6, hours=23)

    # 1. Issue completed exactly 7 days ago -> ELIGIBLE
    r1 = await client.post(
        "/api/v1/projects/ARC7/issues",
        json={"summary": "Completed 7 days ago", "state_id": str(done_state_id)},
    )
    assert r1.status_code == 201
    iss1 = uuid.UUID(r1.json()["id"])

    # 2. Issue completed 6 days 23 hours ago -> NOT ELIGIBLE
    r2 = await client.post(
        "/api/v1/projects/ARC7/issues",
        json={"summary": "Completed 6d 23h ago", "state_id": str(done_state_id)},
    )
    assert r2.status_code == 201
    iss2 = uuid.UUID(r2.json()["id"])

    # 3. Issue in cancelled state completed 7 days ago -> ELIGIBLE
    r3 = await client.post(
        "/api/v1/projects/ARC7/issues",
        json={"summary": "Cancelled 7 days ago", "state_id": str(cancel_state_id)},
    )
    assert r3.status_code == 201
    iss3 = uuid.UUID(r3.json()["id"])

    # 4. Issue in project with NULL auto_archive_days completed 10 days ago -> SKIPPED
    r_null = await client.post(
        "/api/v1/projects/ARCN/issues",
        json={"summary": "Null project issue", "state_id": str(done_null_state_id)},
    )
    assert r_null.status_code == 201
    iss_null = uuid.UUID(r_null.json()["id"])

    # 5. Issue completed 8 days ago but has an OPEN sub-issue -> BLOCKED (skipped)
    r_parent = await client.post(
        "/api/v1/projects/ARC7/issues",
        json={"summary": "Parent with open child", "state_id": str(done_state_id)},
    )
    assert r_parent.status_code == 201
    iss_parent_blocked = uuid.UUID(r_parent.json()["id"])

    r_child = await client.post(
        "/api/v1/projects/ARC7/issues",
        json={
            "summary": "Open sub-issue",
            "state_id": str(todo_state_id),
            "parent": str(iss_parent_blocked),
        },
    )
    assert r_child.status_code == 201

    # 6. Add 3 more eligible completed issues so total eligible = 5
    r4 = await client.post(
        "/api/v1/projects/ARC7/issues",
        json={"summary": "Batch item 4", "state_id": str(done_state_id)},
    )
    assert r4.status_code == 201
    iss4 = uuid.UUID(r4.json()["id"])

    r5 = await client.post(
        "/api/v1/projects/ARC7/issues",
        json={"summary": "Batch item 5", "state_id": str(done_state_id)},
    )
    assert r5.status_code == 201
    iss5 = uuid.UUID(r5.json()["id"])

    r6 = await client.post(
        "/api/v1/projects/ARC7/issues",
        json={"summary": "Batch item 6", "state_id": str(done_state_id)},
    )
    assert r6.status_code == 201
    iss6 = uuid.UUID(r6.json()["id"])

    # Disable immutable trigger temporarily to simulate backdated creation times
    await api_env.seed.commit()
    await api_env.seed.execute(text("ALTER TABLE objects DISABLE TRIGGER objects_guard_bu_trg"))
    try:
        await api_env.seed.execute(
            text("UPDATE objects SET created_at = :t WHERE id = :id"),
            {"t": t_exact_7d, "id": iss1},
        )
        await api_env.seed.execute(
            text("UPDATE objects SET created_at = :t WHERE id = :id"),
            {"t": t_6d23h, "id": iss2},
        )
        await api_env.seed.execute(
            text("UPDATE objects SET created_at = :t WHERE id = :id"),
            {"t": t_exact_7d, "id": iss3},
        )
        await api_env.seed.execute(
            text("UPDATE objects SET created_at = :t WHERE id = :id"),
            {"t": ref_now - timedelta(days=10), "id": iss_null},
        )
        await api_env.seed.execute(
            text("UPDATE objects SET created_at = :t WHERE id = :id"),
            {"t": ref_now - timedelta(days=8), "id": iss_parent_blocked},
        )
        await api_env.seed.execute(
            text("UPDATE objects SET created_at = :t WHERE id = :id"),
            {"t": ref_now - timedelta(days=8), "id": iss4},
        )
        await api_env.seed.execute(
            text("UPDATE objects SET created_at = :t WHERE id = :id"),
            {"t": ref_now - timedelta(days=9), "id": iss5},
        )
        await api_env.seed.execute(
            text("UPDATE objects SET created_at = :t WHERE id = :id"),
            {"t": ref_now - timedelta(days=10), "id": iss6},
        )
        await api_env.seed.commit()
    finally:
        await api_env.seed.execute(text("ALTER TABLE objects ENABLE TRIGGER objects_guard_bu_trg"))
        await api_env.seed.commit()

    # Execute auto-archive pass with batch_size=2
    # 5 eligible issues with batch_size=2 yields exactly 3 batches
    report = await run_auto_archive(
        api_env.seed,
        now=ref_now,
        batch_size=2,
        commit_batches=True,
    )

    assert report.projects_scanned == 1
    assert report.issues_archived == 5
    assert report.batches == 3

    # Verify that eligible issues have archived_at set, while ineligible ones remain NULL
    async def _is_archived(issue_id: uuid.UUID) -> bool:
        res = await api_env.seed.execute(
            select(ObjectRecord.archived_at).where(ObjectRecord.id == issue_id)
        )
        return res.scalar_one_or_none() is not None

    assert await _is_archived(iss1) is True
    assert await _is_archived(iss3) is True
    assert await _is_archived(iss4) is True
    assert await _is_archived(iss5) is True
    assert await _is_archived(iss6) is True

    # 6d23h issue was NOT archived
    assert await _is_archived(iss2) is False

    # Issue in project with NULL auto_archive_days was NOT archived
    assert await _is_archived(iss_null) is False

    # Parent with open sub-issue was NOT archived
    assert await _is_archived(iss_parent_blocked) is False

    # Second pass with same session: service principal already exists and 0 eligible issues
    report_second = await run_auto_archive(
        api_env.seed,
        now=ref_now,
        batch_size=2,
    )
    assert report_second.issues_archived == 0

    # Naive now and now=None parameter handling
    r_naive = await run_auto_archive(
        api_env.seed,
        now=datetime(2026, 11, 15, 12, 0, 0),  # noqa: DTZ001
    )
    assert r_naive.issues_archived == 0
    r_none = await run_auto_archive(api_env.seed, now=None)
    assert r_none.issues_archived == 0

    # RLSSessionFactory, async_sessionmaker, and invalid target handling
    engine = api_env.seed.bind
    assert isinstance(engine, AsyncEngine)
    fac = RLSSessionFactory(engine)
    r_fac = await run_auto_archive(fac, now=ref_now)
    assert r_fac.issues_archived == 0

    maker = async_sessionmaker(engine)
    r_maker = await run_auto_archive(maker, now=ref_now)
    assert r_maker.issues_archived == 0

    with pytest.raises(TypeError, match="Cannot extract AsyncEngine"):
        await run_auto_archive(12345)  # type: ignore[arg-type]


async def test_case_5_job_concurrency(api_env: ApiEnv) -> None:
    """Case 5: Concurrent run that fails to get advisory lock returns issues_archived == 0."""
    # Acquire advisory lock on seed session
    lock_res = await api_env.seed.execute(
        text("SELECT pg_try_advisory_lock(hashtext('kanban.auto_archive'))")
    )
    assert lock_res.scalar() is True

    try:
        # Create second connection/session to attempt concurrent auto-archive
        engine = api_env.seed.bind
        assert isinstance(engine, AsyncEngine)

        # Attempt auto-archive while lock is held (engine target)
        report = await run_auto_archive(engine, batch_size=10)
        assert report.issues_archived == 0
        assert report.batches == 0
        assert report.projects_scanned == 0

        # Attempt auto-archive while lock is held (session target)
        report_sess = await run_auto_archive(api_env.seed, batch_size=10)
        assert report_sess.issues_archived == 0
        assert report_sess.batches == 0

        # Also verify run_auto_archive_pass returns 0
        count = await run_auto_archive_pass(engine, batch_size=10)
        assert count == 0
    finally:
        # Release the advisory lock
        unlock_res = await api_env.seed.execute(
            text("SELECT pg_advisory_unlock(hashtext('kanban.auto_archive'))")
        )
        assert unlock_res.scalar() is True


async def test_case_6_cli(
    api_env: ApiEnv,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 6: kanban-ctl jobs run auto-archive --now exits 0 and prints JSON report."""
    # Point CLI to the test database
    engine = api_env.seed.bind
    assert isinstance(engine, AsyncEngine)
    dsn = str(engine.url)
    monkeypatch.setenv("KANBAN_DATABASE_URL", dsn)

    # 1. Successful run with valid ISO timestamp
    exit_code = ctl_main(["jobs", "run", "auto-archive", "--now", "2026-11-11T00:00:00Z"])
    assert exit_code == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert "projects_scanned" in report
    assert "issues_archived" in report
    assert "batches" in report

    # 2. Invalid ISO timestamp returns exit code 2
    err_code = ctl_main(["jobs", "run", "auto-archive", "--now", "not-a-valid-date"])
    assert err_code == 2
    err_captured = capsys.readouterr()
    assert "Invalid --now timestamp" in err_captured.err

    # 3. DB failure returns exit code 1
    fail_dsn = "postgresql+asyncpg://kanban_test@/nonexistent_db?host=/tmp/nonexistent"
    monkeypatch.setenv("KANBAN_DATABASE_URL", fail_dsn)
    fail_code = ctl_main(["jobs", "run", "auto-archive"])
    assert fail_code == 1
    fail_captured = capsys.readouterr()
    assert "Auto-archive failed" in fail_captured.err


async def test_scheduler_and_registry() -> None:
    """Test JobRegistry, JobScheduler start/stop and lifespan context."""
    # Test registry
    reg = JobRegistry()
    ran = False

    async def dummy_job(_target: Any) -> int:  # noqa: ANN401
        nonlocal ran
        ran = True
        return 1

    reg.register("dummy", 0.05, dummy_job)
    assert reg.get("dummy") is not None
    assert len(reg.all_jobs()) == 1

    # Test scheduler execution
    scheduler = JobScheduler(reg)
    await scheduler.start(None)
    await asyncio.sleep(0.1)
    await scheduler.stop()
    assert ran is True

    # Test global registry has auto_archive
    assert registry.get("auto_archive") is not None

    # Test lifespan context
    app = FastAPI()
    app.state.session_factory = None
    app.state.enable_background_jobs = False

    async with lifespan(app):
        assert hasattr(app.state, "job_scheduler")
        assert hasattr(app.state, "job_registry")
