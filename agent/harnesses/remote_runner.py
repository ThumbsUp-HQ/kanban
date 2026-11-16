# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: C901, PLR0912, PLR0915, ANN401
"""RemoteRunnerHarness for transition gate execution over WSS control hub (KB-P5-22a, S14.2)."""

from __future__ import annotations

import base64
import uuid
from typing import TYPE_CHECKING, Any

from agent.gates.worker import Harness, HarnessRegistry
from kanban.runners.hub import (
    RunnerWssHub,
    get_global_hub,
)

if TYPE_CHECKING:
    from agent.context.transition_context import RenderedContext

__all__ = [
    "RemoteRunnerHarness",
    "register_remote_runner_harness",
]


class RemoteRunnerHarness(Harness):
    """Transition gate execution harness delegating work to remote runner hosts."""

    def __init__(self, hub: RunnerWssHub | None = None) -> None:
        """Initialize with provided RunnerWssHub or default global hub."""
        self._hub = hub

    @property
    def hub(self) -> RunnerWssHub:
        """Return active RunnerWssHub instance."""
        if self._hub is not None:
            return self._hub
        return get_global_hub()

    async def run(self, ctx: RenderedContext, agent_def: object) -> bytes:
        """Dispatch transition context to remote runner pool and return stdout bytes."""
        workspace_id = getattr(agent_def, "workspace_id", None)
        if workspace_id is None:
            raw_ws = getattr(ctx, "workspace_id", None)
            workspace_id = raw_ws if isinstance(raw_ws, uuid.UUID) else uuid.UUID(int=0)

        pool_slug = getattr(agent_def, "remote_runner_pool_slug", None)
        if not pool_slug and isinstance(agent_def, dict):
            pool_slug = agent_def.get("remote_runner_pool_slug")
        if not pool_slug:
            err_msg = "Agent definition must specify remote_runner_pool_slug"
            raise ValueError(err_msg)

        timeout_ms = getattr(agent_def, "timeout_ms", None)
        if timeout_ms is None and isinstance(agent_def, dict):
            timeout_ms = agent_def.get("timeout_ms")
        if timeout_ms is None:
            timeout_ms = 60_000

        timeout_s = float(timeout_ms) / 1000.0

        cli_args = getattr(agent_def, "cli_args_json", None)
        if cli_args is None and isinstance(agent_def, dict):
            cli_args = agent_def.get("cli_args_json") or agent_def.get("cli_args")
        if cli_args is None:
            cli_args = getattr(agent_def, "cli_args", [])

        mcp_tools = getattr(agent_def, "mcp_allowed_tools", None)
        if mcp_tools is None and isinstance(agent_def, dict):
            mcp_tools = agent_def.get("mcp_allowed_tools")
        if mcp_tools is None:
            mcp_tools = []

        def _get_field(name: str, default: Any = None) -> Any:
            if isinstance(agent_def, dict):
                val = agent_def.get(name)
                return val if val is not None else default
            return getattr(agent_def, name, default)

        agent_spec = {
            "harness_mode": "remote_runner",
            "harness_kind": (
                "cli_pipe"
                if _get_field("cli_binary_allowlist_id")
                else (
                    _get_field("harness_kind")
                    if _get_field("harness_kind") != "remote_runner"
                    else "in_app_sdk"
                )
            ),
            "provider_kind": _get_field("provider_kind"),
            "model_id": _get_field("model_id"),
            "cli_binary_allowlist_id": _get_field("cli_binary_allowlist_id"),
            "cli_args": list(cli_args) if isinstance(cli_args, (list, tuple)) else [],
            "repo_access_mode": _get_field("repo_access_mode", "none"),
            "repo_slug": _get_field("repo_slug") or "default",
            "mcp_allowed_tools": list(mcp_tools) if isinstance(mcp_tools, (list, tuple)) else [],
            "system_instructions_md": _get_field("system_instructions_md", ""),
            "timeout_ms": timeout_ms,
        }

        context_yaml_b64 = base64.b64encode(ctx.yaml_bytes).decode("ascii")
        raw_token = getattr(ctx, "ephemeral_token", None)
        if raw_token:
            if isinstance(raw_token, str):
                ephemeral_token_str = raw_token
            elif isinstance(raw_token, (bytes, bytearray)):
                try:
                    ephemeral_token_str = raw_token.decode("utf-8")
                except UnicodeDecodeError:
                    b64_part = base64.urlsafe_b64encode(raw_token).rstrip(b"=").decode("ascii")
                    ephemeral_token_str = f"kb_agt_eph_{b64_part}"
            else:
                ephemeral_token_str = str(raw_token)
        else:
            ephemeral_token_str = ""

        repo_context = getattr(ctx, "repo_context", None)
        head_commit = getattr(repo_context, "head_commit", None) if repo_context else None

        execution_id = getattr(ctx, "execution_id", None) or str(uuid.uuid4())
        job_id = f"job-{uuid.uuid4()}"

        job_spec = {
            "job_id": job_id,
            "execution_id": str(execution_id),
            "agent_spec": agent_spec,
            "context_yaml_b64": context_yaml_b64,
            "ephemeral_mcp_token": ephemeral_token_str,
            "head_commit": head_commit,
        }

        return await self.hub.dispatch_job(
            workspace_id=workspace_id,
            pool_slug=str(pool_slug),
            job_spec=job_spec,
            timeout_s=timeout_s,
        )


def register_remote_runner_harness(
    registry: HarnessRegistry,
    hub: RunnerWssHub | None = None,
) -> RemoteRunnerHarness:
    """Register RemoteRunnerHarness under kind name 'remote_runner'."""
    harness = RemoteRunnerHarness(hub=hub)
    registry.register("remote_runner", harness)
    return harness
