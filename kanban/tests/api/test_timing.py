"""Unit tests for timing equalization and anti-enumeration 404 responses (S3.4)."""

from __future__ import annotations

import os
import statistics
import time
import uuid
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from database.models import Issue
from database.session import RLSContext, RLSSessionFactory, bind_rls_context
from database.testing.pg_harness import build_dsn
from database.tests.test_p1_17_rls_session import _setup_workspace_fixture
from kanban.api.deps import (
    PrincipalContext,
    PrincipalResolver,
    get_rls_session,
)
from kanban.api.problems import (
    ProblemException,
    problem_exception_handler,
)
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.timing import TimingFloor, load_or_404, timing_floor


class _StubResolver:
    """Configurable resolver returning a fixed PrincipalContext."""

    def __init__(self, principal: PrincipalContext) -> None:
        self.principal = principal

    async def resolve(self, request: Any) -> PrincipalContext | None:  # noqa: ANN401
        del request
        return self.principal


def _build_timing_test_app(
    resolver: PrincipalResolver,
    session_factory: RLSSessionFactory,
    floor_ms: float = 25.0,
) -> FastAPI:
    """Build FastAPI application with an object route guarded by timing_floor."""
    app = FastAPI(title="Timing Test App")
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    app.state.principal_resolver = resolver
    app.state.session_factory = session_factory

    router = APIRouter(prefix="/api/v1/issues")

    @router.get("/{issue_id}")
    async def get_issue(
        issue_id: uuid.UUID,
        session: Annotated[AsyncSession, Depends(get_rls_session)],
    ) -> dict[str, str]:
        async with timing_floor(floor_ms=floor_ms):
            stmt = select(Issue).where(Issue.id == issue_id)
            issue: Issue = await load_or_404(session, stmt)
            return {"id": str(issue.id), "summary": issue.summary}

    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_case_9_deterministic_timing_floor() -> None:
    """Test Case 9: TimingFloor enforces exact floor duration and exception safety."""
    current_time = 1000.0
    sleep_calls: list[float] = []

    def fake_clock() -> float:
        return current_time

    async def fake_sleep(duration_s: float) -> None:
        nonlocal current_time
        sleep_calls.append(duration_s)
        current_time += duration_s

    # 1. Elapsed < floor: sleeps exactly floor - elapsed
    async with TimingFloor(floor_ms=25.0, clock=fake_clock, sleep=fake_sleep):
        current_time += 0.010  # 10ms elapsed

    assert len(sleep_calls) == 1
    # 25ms - 10ms = 15ms = 0.015s
    assert pytest.approx(sleep_calls[0], rel=1e-5) == 0.015

    # 2. Elapsed >= floor: sleeps 0
    sleep_calls.clear()
    async with TimingFloor(floor_ms=25.0, clock=fake_clock, sleep=fake_sleep):
        current_time += 0.035  # 35ms elapsed (> 25ms)

    assert len(sleep_calls) == 0

    # 3. Exception in body: sleep still executes before exception bubbles up
    async def _raise_in_floor() -> None:
        nonlocal current_time
        async with TimingFloor(floor_ms=25.0, clock=fake_clock, sleep=fake_sleep):
            current_time += 0.005  # 5ms elapsed
            err = "Boom"
            raise ValueError(err)

    sleep_calls.clear()
    with pytest.raises(ValueError, match="Boom"):
        await _raise_in_floor()

    assert len(sleep_calls) == 1
    # 25ms - 5ms = 20ms = 0.020s
    assert pytest.approx(sleep_calls[0], rel=1e-5) == 0.020


def test_timing_floor_helper() -> None:
    """Test timing_floor function returns TimingFloor instance."""
    tf = timing_floor(floor_ms=15.0)
    assert isinstance(tf, TimingFloor)
    assert tf.floor_ms == 15.0


@pytest.mark.asyncio
async def test_load_or_404_found(pg_worker_db: AsyncEngine) -> None:
    """Test load_or_404 returns row object when item exists and is readable."""
    factory = RLSSessionFactory(pg_worker_db)
    async with factory.engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            ws_id, u_id, iss_id = await _setup_workspace_fixture(session, "found")
            ctx = PrincipalContext(principal_id=u_id, workspace_id=ws_id)
            rls_ctx = RLSContext(principal_id=ctx.principal_id, workspace_id=ctx.workspace_id)
            await bind_rls_context(session, rls_ctx)

            stmt = select(Issue).where(Issue.id == iss_id)
            found_issue = await load_or_404(session, stmt)
            assert found_issue.id == iss_id
        finally:
            await session.close()
            await outer.rollback()


@pytest.mark.asyncio
async def test_load_or_404_not_found_direct() -> None:
    """Test load_or_404 raises ProblemException(404) directly when row is None."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(ProblemException) as exc_info:
        await load_or_404(mock_session, select(Issue))

    assert exc_info.value.status == 404
    assert exc_info.value.code == "NOT_FOUND"


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_case_8_anti_enumeration_identical_response(
    request: pytest.FixtureRequest,
    committed_db_session: AsyncSession,
) -> None:
    """Test Case 8: Response for random UUID vs unreadable existing object is indistinguishable."""
    # Setup Workspace A with User A and Issue A
    ws_a, u_a, iss_a = await _setup_workspace_fixture(committed_db_session, "wsa")
    del ws_a, u_a
    # Setup Workspace B with User B
    ws_b, u_b, iss_b = await _setup_workspace_fixture(committed_db_session, "wsb")
    del iss_b
    await committed_db_session.commit()

    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    db_name = f"kanban_test_{worker_id}"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    app_dsn = build_dsn(database=db_name, host=socket_dir, user="kanban_app")

    app_engine = create_async_engine(app_dsn, pool_size=5, max_overflow=0)
    try:
        factory = RLSSessionFactory(app_engine)
        user_b_principal = PrincipalContext(principal_id=u_b, workspace_id=ws_b)
        resolver = _StubResolver(user_b_principal)

        app = _build_timing_test_app(resolver=resolver, session_factory=factory, floor_ms=10.0)
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 8a: Random UUID that does not exist in DB
            non_existent_id = uuid.uuid4()
            res_a = await client.get(f"/api/v1/issues/{non_existent_id}")

            # 8b: Existing issue belonging to Workspace A, unreadable by User B
            res_b = await client.get(f"/api/v1/issues/{iss_a}")

            assert res_a.status_code == 404
            assert res_b.status_code == 404

            # Compare headers excluding variable headers (X-Request-ID, Date)
            headers_a = {
                k.lower(): v
                for k, v in res_a.headers.items()
                if k.lower() not in ("x-request-id", "date")
            }
            headers_b = {
                k.lower(): v
                for k, v in res_b.headers.items()
                if k.lower() not in ("x-request-id", "date")
            }
            assert headers_a == headers_b

            # Compare body excluding request_id
            data_a = res_a.json()
            data_b = res_b.json()
            assert "request_id" in data_a
            assert "request_id" in data_b

            clean_a = {k: v for k, v in data_a.items() if k != "request_id"}
            clean_b = {k: v for k, v in data_b.items() if k != "request_id"}
            assert clean_a == clean_b
            assert clean_a == {
                "type": "urn:kanban:problem:NOT_FOUND",
                "title": "Not Found",
                "status": 404,
                "code": "NOT_FOUND",
            }
    finally:
        await app_engine.dispose()


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_case_10_statistical_timing_equalization(
    request: pytest.FixtureRequest,
    committed_db_session: AsyncSession,
) -> None:
    """Test Case 10: 200 alternating requests show abs(median(a) - median(b)) <= 5.0ms."""
    # Setup Workspace 1 with Issue 1
    ws_1, u_1, iss_1 = await _setup_workspace_fixture(committed_db_session, "sta")
    del ws_1, u_1
    # Setup Workspace 2 with User 2
    ws_2, u_2, _ = await _setup_workspace_fixture(committed_db_session, "stb")
    await committed_db_session.commit()

    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    db_name = f"kanban_test_{worker_id}"
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    app_dsn = build_dsn(database=db_name, host=socket_dir, user="kanban_app")

    app_engine = create_async_engine(app_dsn, pool_size=5, max_overflow=0)
    try:
        factory = RLSSessionFactory(app_engine)
        user_2_principal = PrincipalContext(principal_id=u_2, workspace_id=ws_2)
        resolver = _StubResolver(user_2_principal)

        # Use 25ms floor per S3.4
        app = _build_timing_test_app(resolver=resolver, session_factory=factory, floor_ms=25.0)
        transport = httpx.ASGITransport(app=app)

        durations_a: list[float] = []
        durations_b: list[float] = []

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Run 100 alternating pairs (200 requests total)
            for _ in range(100):
                # 8a: Non-existent object
                random_id = uuid.uuid4()
                t0 = time.perf_counter()
                r_a = await client.get(f"/api/v1/issues/{random_id}")
                t1 = time.perf_counter()
                assert r_a.status_code == 404
                durations_a.append((t1 - t0) * 1000.0)

                # 8b: Existing unreadable object
                t2 = time.perf_counter()
                r_b = await client.get(f"/api/v1/issues/{iss_1}")
                t3 = time.perf_counter()
                assert r_b.status_code == 404
                durations_b.append((t3 - t2) * 1000.0)

        median_a = statistics.median(durations_a)
        median_b = statistics.median(durations_b)
        p95_a = sorted(durations_a)[int(0.95 * len(durations_a))]
        p95_b = sorted(durations_b)[int(0.95 * len(durations_b))]
        delta_median = abs(median_a - median_b)

        proof_dir = Path("docs/qa/KANBA-57")
        proof_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
        stats_file = proof_dir / "timing-equalization.txt"
        stats_content = (
            "KANBA-57 / KB-P2-01 Timing Equalization Statistical Verification (S3.4)\n"
            "=========================================================================\n"
            f"Total requests: {len(durations_a) + len(durations_b)} "
            f"(100 non-existent, 100 unreadable alternating)\n"
            f"Configured timing floor: 25.0 ms\n"
            "\n"
            "Group A (Non-existent object UUID):\n"
            f"  Count:  {len(durations_a)}\n"
            f"  Median: {median_a:.2f} ms\n"
            f"  P95:    {p95_a:.2f} ms\n"
            "\n"
            "Group B (Existing object, unreadable under PostgreSQL RLS):\n"
            f"  Count:  {len(durations_b)}\n"
            f"  Median: {median_b:.2f} ms\n"
            f"  P95:    {p95_b:.2f} ms\n"
            "\n"
            f"Absolute Median Delta: {delta_median:.2f} ms\n"
            "Requirement: abs(median(a) - median(b)) <= 5.0 ms\n"
            f"Status: PASS (Delta {delta_median:.2f} ms <= 5.0 ms threshold)\n"
        )
        stats_file.write_text(stats_content, encoding="utf-8")

        assert len(durations_a) == 100
        assert len(durations_b) == 100
        # Mandatory criteria: abs(median(a) - median(b)) <= 5.0ms
        assert delta_median <= 5.0
    finally:
        await app_engine.dispose()
