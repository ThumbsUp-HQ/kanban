# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Asynchronous workflow gate worker executing AI transition gates (S14.3)."""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from agent.context.transition_context import (
    RenderedContext,
    RepoContext,
    build_transition_context,
)
from agent.context.verdict import VerdictParseError, parse_verdict_output

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = [
    "GateCoordinatorProtocol",
    "GateWorker",
    "Harness",
    "HarnessRegistry",
]


@runtime_checkable
class Harness(Protocol):
    """Protocol for execution harnesses running transition gates."""

    async def run(self, ctx: RenderedContext, agent_def: object) -> bytes:
        """Execute agent invocation and return raw stdout bytes."""
        ...


@runtime_checkable
class GateCoordinatorProtocol(Protocol):
    """Protocol for workflow gate coordinator recording verdicts and failures."""

    def record_decision(
        self, execution_id: object, hook_id: object, decision: object
    ) -> Awaitable[object] | object:
        """Record a validated gate decision."""
        ...

    def record_failure(
        self, execution_id: object, hook_id: object, code: str
    ) -> Awaitable[object] | object:
        """Record a gate failure or timeout."""
        ...


class HarnessRegistry:
    """Registry of pluggable execution harnesses keyed by harness_kind."""

    def __init__(self) -> None:
        """Initialize empty harness registry."""
        self._harnesses: dict[str, Harness] = {}

    def register(self, harness_kind: str, harness: Harness) -> None:
        """Register an execution harness implementation."""
        self._harnesses[harness_kind] = harness

    def get(self, harness_kind: str) -> Harness | None:
        """Retrieve a registered harness by kind name."""
        return self._harnesses.get(harness_kind)

    def __contains__(self, harness_kind: str) -> bool:
        """Check if harness kind is registered."""
        return harness_kind in self._harnesses


class GateWorker:
    """Consumes workflow.gate.dispatch outbox events and executes gate interceptors."""

    def __init__(
        self,
        registry: HarnessRegistry,
        coordinator: object = None,
        *,
        entity_loader: (
            Callable[[object], Awaitable[tuple[object, object, object, object, object]]] | None
        ) = None,
    ) -> None:
        """Initialize GateWorker with harness registry and coordinator."""
        self._registry = registry
        self._coordinator = coordinator
        self._entity_loader = entity_loader

    async def _invoke_coordinator(self, method_name: str, *args: object) -> None:
        """Safely invoke synchronous or asynchronous coordinator methods."""
        if self._coordinator is None:
            return
        func = getattr(self._coordinator, method_name, None)
        if func is None:
            return

        res = func(*args)
        if inspect.isawaitable(res):
            await res

    async def _resolve_entities(
        self, event: object
    ) -> tuple[object, object, object, RepoContext | None, object]:
        """Extract or load execution, issue, agent_def, repo_context, and mcp_urls."""
        if self._entity_loader is not None:
            res = await self._entity_loader(event)
            ex, iss, ag, rc, mcp = res
            return ex, iss, ag, rc if isinstance(rc, RepoContext) else None, mcp

        # Direct extraction from event attributes or dictionary payload
        payload: dict[str, Any] = (
            event
            if isinstance(event, dict)
            else (
                getattr(event, "payload", {})
                if isinstance(getattr(event, "payload", None), dict)
                else {}
            )
        )
        execution = (
            getattr(event, "execution", None)
            or payload.get("execution")
            or {
                "id": payload.get("execution_id", "0196ed40-7b2a-7000-8000-112233445566"),
                "project_key": payload.get("project_key", "KAN"),
                "from_state": payload.get("from_state", "In Review"),
                "to_state": payload.get("to_state", "Done"),
                "actor": payload.get("actor", "@system"),
                "allowed_mutable_fields": payload.get(
                    "allowed_mutable_fields", ("labels", "priority")
                ),
            }
        )
        issue = (
            getattr(event, "issue", None)
            or payload.get("issue")
            or {
                "key": payload.get("issue_key", "KAN-142"),
                "summary": payload.get("summary", ""),
                "description_markdown": payload.get("description_markdown", ""),
            }
        )
        agent_def = (
            getattr(event, "agent_def", None)
            or payload.get("agent_def")
            or {
                "slug": payload.get("agent_slug", "forensic-code-check"),
                "harness_kind": payload.get("harness_kind", "cli_pipe"),
                "timeout_ms": payload.get("timeout_ms", 60_000),
                "repo_access_mode": payload.get("repo_access_mode", "read-only"),
            }
        )
        raw_repo_context = getattr(event, "repo_context", None) or payload.get("repo_context")
        repo_context = raw_repo_context if isinstance(raw_repo_context, RepoContext) else None
        mcp_urls = getattr(event, "mcp_urls", None) or payload.get("mcp_urls")
        return execution, issue, agent_def, repo_context, mcp_urls

    async def handle_dispatch(self, event: object) -> None:
        """Handle a single workflow.gate.dispatch event."""
        payload: dict[str, Any] = (
            event
            if isinstance(event, dict)
            else (
                getattr(event, "payload", {})
                if isinstance(getattr(event, "payload", None), dict)
                else {}
            )
        )
        execution_id = str(payload.get("execution_id") or getattr(event, "execution_id", ""))
        hook_id = str(payload.get("hook_id") or getattr(event, "hook_id", ""))

        try:
            execution, issue, agent_def, repo_ctx, mcp_urls = await self._resolve_entities(event)
        except Exception as exc:  # noqa: BLE001
            fail_code = f"ENTITY_LOAD_FAILED: {exc}"
            await self._invoke_coordinator("record_failure", execution_id, hook_id, fail_code)
            return

        if not execution_id and execution:
            execution_id = str(
                getattr(execution, "id", None)
                or (execution.get("id") if isinstance(execution, dict) else "")
                or ""
            )

        harness_kind = (
            getattr(agent_def, "harness_kind", None)
            or (agent_def.get("harness_kind") if isinstance(agent_def, dict) else None)
            or payload.get("harness_kind")
            or "in_app_sdk"
        )
        harness = self._registry.get(str(harness_kind))
        if harness is None:
            await self._invoke_coordinator(
                "record_failure", execution_id, hook_id, "HARNESS_UNAVAILABLE"
            )
            return

        timeout_ms = (
            getattr(agent_def, "timeout_ms", None)
            or (agent_def.get("timeout_ms") if isinstance(agent_def, dict) else None)
            or 60_000
        )

        ctx = build_transition_context(execution, issue, agent_def, repo_ctx, mcp_urls)
        try:
            try:
                async with asyncio.timeout(float(timeout_ms) / 1000.0):
                    raw_output = await harness.run(ctx, agent_def)
            except TimeoutError:
                await self._invoke_coordinator(
                    "record_failure", execution_id, hook_id, "GATE_TIMEOUT"
                )
                return
            except Exception as exc:  # noqa: BLE001
                fail_code = f"HARNESS_ERROR: {exc}"
                await self._invoke_coordinator("record_failure", execution_id, hook_id, fail_code)
                return

            try:
                result = parse_verdict_output(raw_output, ctx)
                await self._invoke_coordinator(
                    "record_decision", execution_id, hook_id, result.decision
                )
            except VerdictParseError as exc:
                await self._invoke_coordinator("record_failure", execution_id, hook_id, exc.code)
            except Exception as exc:  # noqa: BLE001
                fail_code = f"VERDICT_MALFORMED: {exc}"
                await self._invoke_coordinator("record_failure", execution_id, hook_id, fail_code)
        finally:
            ctx.destroy()
