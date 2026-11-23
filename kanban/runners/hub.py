# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""WSS Hub: Connection pool, heartbeat tracking, dispatch & cancellation (KB-P5-22a, S14.2)."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

logger: Final = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.websockets import WebSocket

__all__ = [
    "MAX_FRAME_BYTES",
    "ChallengeHelloFrame",
    "ChallengeResponseFrame",
    "ConnectedRunner",
    "CrossRunnerJobForgeryError",
    "HeartbeatFrame",
    "HelloAckFrame",
    "HelloFrame",
    "JobCancelFrame",
    "JobDispatchFrame",
    "JobResultFrame",
    "JobToolEventFrame",
    "RemoteRunnerDisconnectedError",
    "RemoteRunnerError",
    "RemoteRunnerExecutionError",
    "RemoteRunnerRevokedError",
    "RemoteRunnerUnavailableError",
    "RunnerAlreadyConnectedError",
    "RunnerWssHub",
    "get_global_hub",
]

MAX_FRAME_BYTES: Final[int] = 1_310_720
HEARTBEAT_INTERVAL_S: Final[int] = 15
DEAD_EVICTION_S: Final[float] = 45.0


# --- Exceptions ---


class RemoteRunnerError(Exception):
    """Base exception for remote runner infrastructure errors."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Initialize with machine-readable code and optional explanation."""
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code


class RemoteRunnerUnavailableError(RemoteRunnerError):
    """Raised when no online runners are available in the requested pool."""


class RemoteRunnerDisconnectedError(RemoteRunnerError):
    """Raised when runner disconnects or heartbeat times out during execution."""


class RemoteRunnerRevokedError(RemoteRunnerError):
    """Raised when runner certificate is revoked during job execution."""


class RunnerAlreadyConnectedError(RemoteRunnerError):
    """Raised when registering a runner slot that is already actively connected."""

    def __init__(self, code: str = "ALREADY_CONNECTED", detail: str = "") -> None:
        """Initialize with error code ALREADY_CONNECTED and descriptive detail."""
        super().__init__(code, detail or "Runner is already connected")


class CrossRunnerJobForgeryError(RemoteRunnerError):
    """Raised when runner attempts to submit results or events for another runner's job."""

    def __init__(
        self,
        code: str = "CROSS_RUNNER_FORGERY_DETECTED",
        detail: str = "Runner does not own the specified job",
    ) -> None:
        """Initialize with error code CROSS_RUNNER_FORGERY_DETECTED and descriptive detail."""
        super().__init__(code, detail)


class RemoteRunnerExecutionError(RemoteRunnerError):
    """Raised when runner returns an error status payload."""

    def __init__(
        self,
        code: str,
        detail: str = "",
        *,
        exit_code: int | None = None,
        stdout_bytes: bytes | None = None,
    ) -> None:
        """Initialize with error code, detail, exit code, and captured stdout."""
        super().__init__(code, detail)
        self.exit_code = exit_code
        self.stdout_bytes = stdout_bytes


# --- Typed Protocol Frames (extra="forbid") ---


class ChallengeHelloFrame(BaseModel):
    """Pre-registration Proof-of-Possession challenge hello from server to runner."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["challenge_hello"] = "challenge_hello"
    nonce: str
    runner_id: uuid.UUID


class ChallengeResponseFrame(BaseModel):
    """Proof-of-Possession challenge response from runner to server."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["challenge_response"] = "challenge_response"
    signature_b64: str


class HelloFrame(BaseModel):
    """Inbound handshake frame from runner to server."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["hello"] = "hello"
    schema_version: Literal["kb-runner-ws/v1"] = Field(alias="schema")
    runner_id: uuid.UUID
    max_concurrency: int = Field(default=1, ge=1, le=8)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class HelloAckFrame(BaseModel):
    """Outbound handshake acknowledgement from server to runner."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["hello_ack"] = "hello_ack"
    heartbeat_interval_s: int = HEARTBEAT_INTERVAL_S


class HeartbeatFrame(BaseModel):
    """Periodic health beacon from runner."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["heartbeat"] = "heartbeat"
    runner_id: uuid.UUID
    active_jobs: list[str] = Field(default_factory=list)


class JobToolEventFrame(BaseModel):
    """Granular progress event reported during tool execution."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["job.tool_event"] = "job.tool_event"
    job_id: str
    tool_name: str
    duration_ms: int = Field(ge=0)
    status: str


class JobResultFrame(BaseModel):
    """Final job completion or failure frame from runner."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["job.result"] = "job.result"
    job_id: str
    status: Literal["ok", "error"] | None = None
    exit_code: int | None = None
    stdout_b64: str | None = None
    error_code: str | None = None


class JobDispatchFrame(BaseModel):
    """Job assignment frame dispatched to runner."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["job.dispatch"] = "job.dispatch"
    job_id: str
    execution_id: str
    agent_spec: dict[str, Any]
    context_yaml_b64: str
    ephemeral_mcp_token: str
    head_commit: str | None = None


class JobCancelFrame(BaseModel):
    """Job cancellation notice sent to runner."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["job.cancel"] = "job.cancel"
    job_id: str
    reason: str


# --- Hub Architecture ---


@dataclass
class ConnectedRunner:
    """State tracking for an active WebSocket connection to a remote runner."""

    runner_id: uuid.UUID
    workspace_id: uuid.UUID
    pool_slug: str
    hostname: str
    websocket: WebSocket
    max_concurrency: int = 1
    capabilities: dict[str, Any] = field(default_factory=dict)
    active_jobs: set[str] = field(default_factory=set)
    last_heartbeat_at: float = field(default_factory=time.monotonic)
    status: str = "online"


class RunnerWssHub:
    """Central server-side control hub managing connected remote runner WebSockets."""

    def __init__(self, time_func: Callable[[], float] | None = None) -> None:
        """Initialize empty hub registry."""
        self._runners: dict[uuid.UUID, ConnectedRunner] = {}
        self._pending_jobs: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._job_to_runner: dict[str, uuid.UUID] = {}
        self._time_func: Callable[[], float] = (
            time_func if time_func is not None else time.monotonic
        )
        self._tool_events: list[dict[str, Any]] = []

    def set_time_func(self, time_func: Callable[[], float]) -> None:
        """Override clock source for deterministic timeout testing."""
        self._time_func = time_func

    @property
    def _connections(self) -> dict[uuid.UUID, ConnectedRunner]:
        """Expose active runner connections dictionary."""
        return self._runners

    def register_runner(  # noqa: PLR0913, PLR0917
        self,
        runner_id: uuid.UUID,
        workspace_id: uuid.UUID,
        pool_slug: str,
        hostname: str,
        websocket: WebSocket,
        max_concurrency: int = 1,
        capabilities: dict[str, Any] | None = None,
    ) -> ConnectedRunner:
        """Register newly connected runner socket."""
        if runner_id in self._connections:
            existing = self._connections[runner_id]
            if existing.status == "online":
                msg = f"Runner {runner_id} already has an active live connection slot"
                err_code = "ALREADY_CONNECTED"
                raise RunnerAlreadyConnectedError(err_code, msg)

        runner = ConnectedRunner(
            runner_id=runner_id,
            workspace_id=workspace_id,
            pool_slug=pool_slug,
            hostname=hostname,
            websocket=websocket,
            max_concurrency=max(1, min(max_concurrency, 8)),
            capabilities=capabilities or {},
            last_heartbeat_at=self._time_func(),
            status="online",
        )
        self._runners[runner_id] = runner
        return runner

    register = register_runner

    def unregister_runner(self, runner_id: uuid.UUID, reason: str = "disconnected") -> None:
        """Unregister runner socket and fail any in-flight jobs."""
        runner = self._runners.pop(runner_id, None)
        if runner is None:
            return
        runner.status = "offline"
        exc_cls = RemoteRunnerRevokedError if reason == "revoked" else RemoteRunnerDisconnectedError
        fail_code = "REMOTE_RUNNER_REVOKED" if reason == "revoked" else "REMOTE_RUNNER_DISCONNECTED"
        for job_id in list(runner.active_jobs):
            fut = self._pending_jobs.pop(job_id, None)
            self._job_to_runner.pop(job_id, None)
            if fut and not fut.done():
                fut.set_exception(exc_cls(fail_code, f"Runner {reason} during execution"))
        runner.active_jobs.clear()

    async def revoke_runner(self, runner_id: uuid.UUID) -> None:
        """Immediately close active runner socket with 4003 and cancel in-flight jobs."""
        runner = self._runners.get(runner_id)
        if runner is not None:
            ws = runner.websocket
            self.unregister_runner(runner_id, reason="revoked")
            with contextlib.suppress(Exception):
                await ws.close(code=4003, reason="runner revoked")

    def evict_stale_runners(self, now: float | None = None) -> list[uuid.UUID]:
        """Evict runners whose heartbeat has exceeded DEAD_EVICTION_S (45s)."""
        current_time = now if now is not None else self._time_func()
        evicted: list[uuid.UUID] = []
        for runner_id, runner in list(self._runners.items()):
            elapsed = current_time - runner.last_heartbeat_at
            if runner.status == "online" and (elapsed > DEAD_EVICTION_S):
                evicted.append(runner_id)
                self.unregister_runner(runner_id, reason="heartbeat_timeout")
        return evicted

    def get_pool_runners(self, workspace_id: uuid.UUID, pool_slug: str) -> list[ConnectedRunner]:
        """Return list of connected runners in the given workspace and pool."""
        return [
            r
            for r in self._runners.values()
            if r.workspace_id == workspace_id and r.pool_slug == pool_slug and r.status == "online"
        ]

    def select_runner(self, workspace_id: uuid.UUID, pool_slug: str) -> ConnectedRunner | None:
        """Select least-loaded eligible runner with available capacity, or None if full/offline."""
        eligible = [
            r
            for r in self._runners.values()
            if r.workspace_id == workspace_id
            and r.pool_slug == pool_slug
            and r.status == "online"
            and len(r.active_jobs) < r.max_concurrency
        ]
        if not eligible:
            return None
        return min(eligible, key=lambda r: len(r.active_jobs) / max(1, r.max_concurrency))

    async def cancel_job(self, job_id: str, reason: str = "cancelled") -> bool:
        """Cancel an in-flight job by sending job.cancel frame and cancelling pending future."""
        runner_id = self._job_to_runner.get(job_id)
        if runner_id is None:
            return False
        runner = self._runners.get(runner_id)
        cancel_frame = JobCancelFrame(job_id=job_id, reason=reason)
        if runner is not None:
            with contextlib.suppress(Exception):
                await self._send_frame(runner.websocket, cancel_frame)
            runner.active_jobs.discard(job_id)
        fut = self._pending_jobs.pop(job_id, None)
        self._job_to_runner.pop(job_id, None)
        if fut and not fut.done():
            fut.cancel()
        return True

    def notify_runner_revoked(self, runner_id: uuid.UUID) -> None:
        """Notify that a runner was revoked, cancelling its pending jobs and evicting it."""
        self.unregister_runner(runner_id, reason="revoked")

    def handle_frame(
        self,
        runner_id: uuid.UUID,
        frame_data: dict[str, Any] | None = None,
        *,
        frame: dict[str, Any] | None = None,
    ) -> None:
        """Handle incoming parsed JSON frame from a runner."""
        data = frame if frame is not None else (frame_data or {})
        runner = self._runners.get(runner_id)
        if runner is None:
            return

        frame_type = data.get("type")
        if frame_type == "heartbeat":
            hb = HeartbeatFrame.model_validate(data)
            runner.last_heartbeat_at = self._time_func()
            runner.active_jobs = set(hb.active_jobs)
        elif frame_type == "job.tool_event":
            event = JobToolEventFrame.model_validate(data)
            owner_runner_id = self._job_to_runner.get(event.job_id)
            if owner_runner_id is None or owner_runner_id != runner_id:
                msg = (
                    f"Cross-runner tool event forgery: runner {runner_id} does not own "
                    f"job {event.job_id} (assigned to {owner_runner_id})"
                )
                logger.warning(msg)
                err_code = "CROSS_RUNNER_FORGERY_DETECTED"
                raise CrossRunnerJobForgeryError(err_code, msg)
            self._tool_events.append(event.model_dump())
        elif frame_type == "job.result":
            res = JobResultFrame.model_validate(data)
            owner_runner_id = self._job_to_runner.get(res.job_id)
            if owner_runner_id is None or owner_runner_id != runner_id:
                msg = (
                    f"Cross-runner result forgery: runner {runner_id} does not own "
                    f"job {res.job_id} (assigned to {owner_runner_id})"
                )
                logger.warning(msg)
                err_code = "CROSS_RUNNER_FORGERY_DETECTED"
                raise CrossRunnerJobForgeryError(err_code, msg)
            fut = self._pending_jobs.get(res.job_id)
            if fut and not fut.done():
                fut.set_result(res.model_dump())

    async def _send_frame(self, ws: Any, frame: BaseModel) -> None:  # noqa: ANN401
        """Serialize and send typed frame over WebSocket."""
        payload = frame.model_dump(by_alias=True)
        raw_text = json.dumps(payload)
        if hasattr(ws, "send_text"):
            await ws.send_text(raw_text)
        else:
            await ws.send(raw_text)

    async def dispatch_job(
        self,
        workspace_id: uuid.UUID,
        pool_slug: str,
        job_spec: dict[str, Any],
        timeout_s: float | None = None,
    ) -> bytes:
        """Dispatch job to least-loaded online runner in pool and await result bytes."""
        self.evict_stale_runners()

        eligible = [
            r
            for r in self._runners.values()
            if r.workspace_id == workspace_id and r.pool_slug == pool_slug and r.status == "online"
        ]
        if not eligible:
            msg = "REMOTE_RUNNER_POOL_OFFLINE"
            raise RemoteRunnerUnavailableError(msg)

        # Select least-loaded runner by active_jobs / max_concurrency ratio
        runner = min(eligible, key=lambda r: len(r.active_jobs) / max(1, r.max_concurrency))

        job_id = str(job_spec.get("job_id") or f"job-{uuid.uuid4()}")
        runner.active_jobs.add(job_id)
        self._job_to_runner[job_id] = runner.runner_id

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_jobs[job_id] = future

        dispatch_frame = JobDispatchFrame(
            job_id=job_id,
            execution_id=str(job_spec.get("execution_id", "")),
            agent_spec=job_spec.get("agent_spec", {}),
            context_yaml_b64=job_spec.get("context_yaml_b64", ""),
            ephemeral_mcp_token=job_spec.get("ephemeral_mcp_token", ""),
            head_commit=job_spec.get("head_commit"),
        )

        try:
            await self._send_frame(runner.websocket, dispatch_frame)
        except Exception as exc:
            runner.active_jobs.discard(job_id)
            self._pending_jobs.pop(job_id, None)
            self._job_to_runner.pop(job_id, None)
            msg = "REMOTE_RUNNER_DISCONNECTED"
            raise RemoteRunnerDisconnectedError(msg) from exc

        try:
            if timeout_s is not None and timeout_s > 0:
                async with asyncio.timeout(timeout_s):
                    result = await future
            else:
                result = await future
        except (TimeoutError, asyncio.CancelledError) as err:
            cancel_frame = JobCancelFrame(
                job_id=job_id,
                reason="timeout" if isinstance(err, TimeoutError) else "cancelled",
            )
            with contextlib.suppress(Exception):
                await self._send_frame(runner.websocket, cancel_frame)
            raise
        finally:
            runner.active_jobs.discard(job_id)
            self._pending_jobs.pop(job_id, None)
            self._job_to_runner.pop(job_id, None)

        status = result.get("status")
        exit_code = result.get("exit_code")
        if status == "ok" or (status is None and exit_code == 0):
            stdout_b64 = result.get("stdout_b64") or ""
            return base64.b64decode(stdout_b64.encode("ascii"))
        error_code = result.get("error_code") or "REMOTE_RUNNER_ERROR"
        stdout_b64 = result.get("stdout_b64")
        stdout_bytes = base64.b64decode(stdout_b64.encode("ascii")) if stdout_b64 else None
        raise RemoteRunnerExecutionError(
            error_code,
            exit_code=exit_code,
            stdout_bytes=stdout_bytes,
        )


_GLOBAL_HUB: RunnerWssHub | None = None


def get_global_hub() -> RunnerWssHub:
    """Retrieve or initialize singleton RunnerWssHub."""
    global _GLOBAL_HUB  # noqa: PLW0603
    if _GLOBAL_HUB is None:
        _GLOBAL_HUB = RunnerWssHub()
    return _GLOBAL_HUB
