# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: ANN401, S311, BLE001
"""Outbound mTLS WSS runner daemon: heartbeat, concurrency, cancel & backoff (KB-P5-22b, S14.2)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import ssl
import time
import traceback
import uuid
from typing import TYPE_CHECKING, Any, Final

import websockets

from agent.remote_runner.config import (
    RunnerConfig,
    validate_key_permissions,
)
from agent.remote_runner.executor import RunnerJobExecutor
from kanban.runners.hub import (
    HeartbeatFrame,
    HelloAckFrame,
    HelloFrame,
    JobCancelFrame,
    JobDispatchFrame,
    JobResultFrame,
    JobToolEventFrame,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "CLOSE_CODE_REVOKED",
    "EXIT_CODE_REVOKED",
    "RunnerDaemon",
    "RunnerRevokedError",
]

logger = logging.getLogger(__name__)

CLOSE_CODE_REVOKED: Final[int] = 4003
EXIT_CODE_REVOKED: Final[int] = 78

MIN_BACKOFF_S: Final[float] = 1.0
MAX_BACKOFF_S: Final[float] = 60.0


class RunnerRevokedError(Exception):
    """Raised when runner certificate is revoked by server (close code 4003)."""

    def __init__(self, message: str = "Runner revoked by server (close code 4003)") -> None:
        """Initialize with message and standard exit code 78."""
        super().__init__(message)
        self.exit_code = EXIT_CODE_REVOKED


class RunnerDaemon:
    """Outbound-only TLS 1.3 mTLS WebSocket daemon executing transition jobs."""

    def __init__(
        self,
        config: RunnerConfig,
        *,
        executor: RunnerJobExecutor | None = None,
        ws_connector: Callable[..., Any] | None = None,
        time_func: Callable[[], float] | None = None,
        sleep_func: Callable[[float], Any] | None = None,
    ) -> None:
        """Initialize daemon with config, executor and optional test overrides."""
        validate_key_permissions(config.client_key_path)
        self.config = config
        self.executor = executor or RunnerJobExecutor(config)
        self.ws_connector = ws_connector or websockets.connect
        self.time_func = time_func or time.monotonic
        self.sleep_func = sleep_func or asyncio.sleep

        self.runner_id: uuid.UUID = config.runner_id or uuid.uuid4()
        self._stop_event = asyncio.Event()
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._active_jobs: set[str] = set()
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._ws: Any = None
        self._close_task: asyncio.Task[Any] | None = None
        self._reconnect_attempts = 0

    def build_ssl_context(self) -> ssl.SSLContext:
        """Build strict TLS 1.3 client SSLContext with pinned CA and client cert/key."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True

        if self.config.ca_cert_path.exists():
            ctx.load_verify_locations(cafile=str(self.config.ca_cert_path))
        if self.config.client_cert_path.exists() and self.config.client_key_path.exists():
            ctx.load_cert_chain(
                certfile=str(self.config.client_cert_path),
                keyfile=str(self.config.client_key_path),
            )
        return ctx

    def compute_backoff(self, attempt: int) -> float:
        """Calculate full-jitter exponential backoff (1.0s .. 60.0s)."""
        base_backoff = min(MAX_BACKOFF_S, MIN_BACKOFF_S * (2 ** min(attempt, 6)))
        jitter = random.uniform(0.0, 1.0)
        return float(max(MIN_BACKOFF_S, base_backoff * jitter))

    def stop(self) -> None:
        """Signal daemon to stop and cancel active work."""
        self._stop_event.set()
        for task in list(self._running_tasks.values()):
            if not task.done():
                task.cancel()
        ws = self._ws
        if ws is not None:
            with contextlib.suppress(RuntimeError):
                loop = asyncio.get_running_loop()
                self._close_task = loop.create_task(ws.close())

    async def run_forever(self) -> None:
        """Run outbound daemon loop with auto-reconnect until stopped or revoked."""
        validate_key_permissions(self.config.client_key_path)
        ssl_ctx = self.build_ssl_context()
        wss_url = self.config.resolve_wss_url()

        while not self._stop_event.is_set():
            try:
                await self._connect_and_run(wss_url, ssl_ctx)
                self._reconnect_attempts = 0
            except RunnerRevokedError:
                self.stop()
                raise
            except Exception as exc:
                traceback.print_exc()
                if self._stop_event.is_set():
                    break
                # Check for 4003 close code
                close_code = getattr(exc, "code", None) or getattr(
                    getattr(exc, "rcvd", None), "code", None
                )
                if close_code == CLOSE_CODE_REVOKED:
                    self.stop()
                    msg = "Runner revoked by server (close code 4003)"
                    raise RunnerRevokedError(msg) from exc

                self._reconnect_attempts += 1
                backoff = self.compute_backoff(self._reconnect_attempts)
                logger.warning(
                    "WebSocket disconnected (%s). Reconnecting in %.2fs (attempt %d)",
                    exc,
                    backoff,
                    self._reconnect_attempts,
                )
                await self.sleep_func(backoff)

    async def _connect_and_run(self, wss_url: str, ssl_ctx: ssl.SSLContext) -> None:
        """Establish mTLS WSS connection and handle messages until disconnected."""
        async with self.ws_connector(
            wss_url,
            ssl=ssl_ctx,
            max_size=1_310_720,
        ) as ws:
            self._ws = ws

            # 1. Perform Hello handshake
            hello = HelloFrame(
                schema="kb-runner-ws/v1",
                runner_id=self.runner_id,
                max_concurrency=self.config.max_concurrency,
                capabilities=self.config.capabilities,
            )
            await ws.send(hello.model_dump_json(by_alias=True))

            raw_ack = await ws.recv()
            if isinstance(raw_ack, bytes):
                raw_ack = raw_ack.decode("utf-8")
            data_ack = json.loads(raw_ack)
            HelloAckFrame.model_validate(data_ack)

            # 2. Launch background heartbeat task
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                # 3. Main receive loop
                async for raw_msg in ws:
                    if self._stop_event.is_set():
                        break
                    msg_text = raw_msg.decode("utf-8") if isinstance(raw_msg, bytes) else raw_msg
                    msg_dict = json.loads(msg_text)
                    msg_type = msg_dict.get("type")

                    if msg_type == "job.dispatch":
                        dispatch = JobDispatchFrame.model_validate(msg_dict)
                        self._spawn_job(dispatch)
                    elif msg_type == "job.cancel":
                        cancel = JobCancelFrame.model_validate(msg_dict)
                        self._cancel_job(cancel.job_id)
            finally:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task
                self._ws = None

    def _spawn_job(self, dispatch: JobDispatchFrame) -> None:
        """Spawn concurrent job execution under semaphore guard."""
        job_id = dispatch.job_id
        self._active_jobs.add(job_id)

        async def _job_wrapper() -> None:
            async with self._semaphore:
                try:
                    result = await self.executor.execute_job(
                        dispatch,
                        on_tool_event=self._send_tool_event,
                    )
                except asyncio.CancelledError:
                    result = JobResultFrame(
                        job_id=job_id,
                        status="error",
                        error_code="RUNNER_JOB_CANCELLED",
                    )
                finally:
                    self._active_jobs.discard(job_id)
                    self._running_tasks.pop(job_id, None)

                # Transmit result back over WebSocket if connected
                if self._ws is not None:
                    try:
                        await self._ws.send(result.model_dump_json())
                    except Exception:
                        logger.warning("Failed to send job result for %s", job_id)

        task = asyncio.create_task(_job_wrapper())
        self._running_tasks[job_id] = task

    def _cancel_job(self, job_id: str) -> None:
        """Cancel running job within < 250ms."""
        task = self._running_tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()

    async def _send_tool_event(self, event: JobToolEventFrame) -> None:
        """Send tool event progress frame to server hub."""
        if self._ws is not None:
            try:
                await self._ws.send(event.model_dump_json())
            except Exception:
                logger.debug("Failed to send tool event for %s", event.job_id)

    async def _heartbeat_loop(self, ws: Any) -> None:
        """Periodically emit HeartbeatFrame every heartbeat_interval_s."""
        interval = self.config.heartbeat_interval_s
        while not self._stop_event.is_set():
            await self.sleep_func(interval)
            try:
                hb = HeartbeatFrame(
                    runner_id=self.runner_id,
                    active_jobs=list(self._active_jobs),
                )
                await ws.send(hb.model_dump_json())
            except Exception:
                break
