"""Background job registry and lifespan scheduler (S7.2 8p)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kanban.jobs.auto_archive import (
    AutoArchiveReport,
    run_auto_archive,
    run_auto_archive_pass,
)
from kanban.jobs.trash_purge import (
    PurgeReport,
    run_trash_purge,
    run_trash_purge_pass,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from fastapi import FastAPI

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class JobDefinition:
    """Registered background job definition."""

    name: str
    interval_seconds: float
    func: Callable[..., Any]


class JobRegistry:
    """Central registry of platform background maintenance jobs."""

    def __init__(self) -> None:
        """Initialize empty job registry."""
        self._jobs: dict[str, JobDefinition] = {}

    def register(
        self,
        name: str,
        interval_seconds: float,
        func: Callable[..., Any],
    ) -> None:
        """Register a background job definition."""
        self._jobs[name] = JobDefinition(
            name=name,
            interval_seconds=interval_seconds,
            func=func,
        )

    def get(self, name: str) -> JobDefinition | None:
        """Retrieve job definition by name."""
        return self._jobs.get(name)

    def all_jobs(self) -> list[JobDefinition]:
        """List all registered job definitions."""
        return list(self._jobs.values())


registry = JobRegistry()
registry.register(
    name="auto_archive",
    interval_seconds=3600.0,
    func=run_auto_archive,
)
registry.register(
    name="trash_purge",
    interval_seconds=3600.0,
    func=run_trash_purge,
)


class JobScheduler:
    """Scheduler managing background task loops for registered jobs."""

    def __init__(self, job_registry: JobRegistry) -> None:
        """Initialize scheduler with a JobRegistry."""
        self._registry = job_registry
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    async def start(self, session_target: Any) -> None:  # noqa: ANN401
        """Start background loops for all registered jobs."""
        if self._running:
            return
        self._running = True
        for job in self._registry.all_jobs():
            task = asyncio.create_task(
                self._run_job_loop(job, session_target),
                name=f"job-{job.name}",
            )
            self._tasks.append(task)

    async def stop(self) -> None:
        """Cancel and wait for all running background loops."""
        if not self._running:
            return
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def _run_job_loop(self, job: JobDefinition, session_target: Any) -> None:  # noqa: ANN401
        """Run single job continuously on its interval."""
        while self._running:
            try:
                res = job.func(session_target)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                logger.exception("Background job %s encountered unhandled error", job.name)
            try:
                await asyncio.sleep(job.interval_seconds)
            except asyncio.CancelledError:
                break


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager starting and stopping background jobs."""
    scheduler = JobScheduler(registry)
    app.state.job_scheduler = scheduler
    app.state.job_registry = registry

    session_target = getattr(app.state, "session_factory", None)
    should_run = getattr(app.state, "enable_background_jobs", False)

    if should_run and session_target is not None:
        await scheduler.start(session_target)

    try:
        yield
    finally:
        await scheduler.stop()


__all__ = [
    "AutoArchiveReport",
    "JobDefinition",
    "JobRegistry",
    "JobScheduler",
    "PurgeReport",
    "lifespan",
    "registry",
    "run_auto_archive",
    "run_auto_archive_pass",
    "run_trash_purge",
    "run_trash_purge_pass",
]
