# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: C901, PLR0911, PLR0912, PLR0915, ASYNC240, PLC0415, TC001
"""Runner job executor: safe local execution, :ro repo checks & CLI confinement (KB-P5-22b)."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import yaml

from agent.context.transition_context import (
    McpAccess,
    RenderedContext,
    RepoContext,
)
from agent.harnesses.in_app_sdk import InAppSdkHarness
from agent.remote_runner.config import RunnerConfig
from agent.runners.cli_pipe import CliPipeHarness
from kanban.agents.cli_policy import CliPolicyError, assert_runtime_argv
from kanban.runners.hub import (
    JobDispatchFrame,
    JobResultFrame,
    JobToolEventFrame,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = ["RunnerJobExecutor"]

CODE_REPO_NOT_MOUNTED: Final[str] = "RUNNER_REPO_NOT_MOUNTED"
CODE_MOUNT_NOT_READONLY: Final[str] = "RUNNER_MOUNT_NOT_READONLY"
CODE_BANNED_CLI_FLAG: Final[str] = "RUNNER_BANNED_CLI_FLAG"
CODE_EXECUTION_FAILED: Final[str] = "RUNNER_EXECUTION_FAILED"


class RunnerJobExecutor:
    """Executes transition gate jobs locally on the remote runner with :ro confinement."""

    def __init__(
        self,
        config: RunnerConfig,
        *,
        in_app_harness_factory: Callable[..., Any] | None = None,
        cli_pipe_harness_factory: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize executor with runner config and optional harness factories."""
        self.config = config
        self._in_app_harness_factory = in_app_harness_factory or InAppSdkHarness
        self._cli_pipe_harness_factory = cli_pipe_harness_factory or CliPipeHarness

    async def execute_job(
        self,
        dispatch: JobDispatchFrame,
        *,
        on_tool_event: Callable[[JobToolEventFrame], Awaitable[None]] | None = None,
    ) -> JobResultFrame:
        """Execute assigned job according to agent_spec, enforcing :ro repos and zero-shell."""
        agent_spec = dispatch.agent_spec or {}
        harness_kind = str(agent_spec.get("harness_kind") or "in_app_sdk")
        repo_access_mode = str(agent_spec.get("repo_access_mode") or "none")

        # 1. Ephemeral MCP token isolation in mutable bytearray (zeroed in finally)
        token_ba = bytearray(dispatch.ephemeral_mcp_token.encode("ascii"))

        # 2. Server-frame defense-in-depth: check CLI policy before touching any resources
        if harness_kind == "cli_pipe":
            # Normalize cli_args if sent as cli_args or cli_args_json
            args_list = agent_spec.get("cli_args_json") or agent_spec.get("cli_args") or []
            spec_copy = dict(agent_spec)
            spec_copy["cli_args_json"] = args_list
            try:
                assert_runtime_argv(spec_copy)
            except CliPolicyError:
                return JobResultFrame(
                    job_id=dispatch.job_id,
                    status="error",
                    error_code=CODE_BANNED_CLI_FLAG,
                )

        # 3. Read-only repo mount verification
        resolved_repo_path: Path | None = None
        if repo_access_mode != "none":
            repo_slug = str(
                agent_spec.get("repo_slug")
                or (agent_spec.get("repo_context") or {}).get("slug")
                or ""
            )
            if not repo_slug or repo_slug not in self.config.repo_mounts:
                return JobResultFrame(
                    job_id=dispatch.job_id,
                    status="error",
                    error_code=CODE_REPO_NOT_MOUNTED,
                )

            configured_path = Path(self.config.repo_mounts[repo_slug])
            try:
                resolved_repo_path = configured_path.resolve(strict=True)
            except (OSError, ValueError):
                return JobResultFrame(
                    job_id=dispatch.job_id,
                    status="error",
                    error_code=CODE_REPO_NOT_MOUNTED,
                )

            # Prevent symlink traversal escapes
            mount_root = configured_path.parent.resolve()
            if not resolved_repo_path.is_relative_to(mount_root):
                return JobResultFrame(
                    job_id=dispatch.job_id,
                    status="error",
                    error_code=CODE_REPO_NOT_MOUNTED,
                )

            # For ro_vfs_mount, verify filesystem is strictly read-only
            if repo_access_mode == "ro_vfs_mount":
                try:
                    stat_res = os.statvfs(str(resolved_repo_path))
                    is_ro = (stat_res.f_flag & os.ST_RDONLY) != 0
                except (OSError, AttributeError):
                    is_ro = False
                if not is_ro:
                    return JobResultFrame(
                        job_id=dispatch.job_id,
                        status="error",
                        error_code=CODE_MOUNT_NOT_READONLY,
                    )

        # 4. Context reconstitution
        ctx: RenderedContext | None = None
        try:
            yaml_bytes = base64.b64decode(dispatch.context_yaml_b64)
            parsed_ctx = yaml.safe_load(yaml_bytes) or {}
            verdict_nonce = str(parsed_ctx.get("verdict_nonce") or "")
            delimiter = str(
                (parsed_ctx.get("ticket_snapshot") or {}).get("delimiter")
                or "<<<UNTRUSTED_TICKET_DATA>>>"
            )

            repo_ctx_model: RepoContext | None = None
            if resolved_repo_path is not None:
                repo_ctx_model = RepoContext(
                    mount_path=str(resolved_repo_path),
                    access="read-only",
                    head_commit=dispatch.head_commit or "HEAD",
                    mirror_path=str(resolved_repo_path),
                )

            mcp_access_dict = parsed_ctx.get("mcp_access") or {}
            mcp_access_model = McpAccess(
                agent_url=mcp_access_dict.get("agent_url") or "",
                docs_url=mcp_access_dict.get("docs_url") or "",
                ephemeral_bearer_env="KANBAN_EPHEMERAL_MCP_TOKEN",
            )

            ctx = RenderedContext(
                yaml_bytes=yaml_bytes,
                sha256=hashlib.sha256(yaml_bytes).hexdigest(),
                delimiter=delimiter,
                verdict_nonce=verdict_nonce,
                ephemeral_token=token_ba,
                allowed_mutable_fields=frozenset(),
            )
            if repo_ctx_model is not None:
                ctx.repo_context = repo_ctx_model
            if mcp_access_model is not None:
                ctx.mcp_access = mcp_access_model

            # 5. Execution dispatch based on harness_kind
            raw_output: bytes
            if harness_kind == "cli_pipe":
                cli_harness = self._cli_pipe_harness_factory()
                git_dir = (
                    resolved_repo_path / ".git"
                    if resolved_repo_path is not None and (resolved_repo_path / ".git").exists()
                    else resolved_repo_path
                )
                repo_dict = (
                    {
                        "mirror_path": str(git_dir),
                        "head_commit": dispatch.head_commit or "HEAD",
                    }
                    if resolved_repo_path is not None
                    else None
                )
                raw_output = await cli_harness.run(
                    ctx,
                    agent_spec,
                    repo_context=repo_dict,
                )
            else:
                in_app_harness = self._in_app_harness_factory()
                raw_output = await in_app_harness.run(ctx, agent_spec)

                # Stream tool traces if on_tool_event callback provided
                if on_tool_event is not None:
                    for trace in getattr(in_app_harness, "last_tool_traces", []):
                        await on_tool_event(
                            JobToolEventFrame(
                                job_id=dispatch.job_id,
                                tool_name=trace.tool_name,
                                duration_ms=int(trace.duration_ms),
                                status=trace.status,
                            )
                        )

            return JobResultFrame(
                job_id=dispatch.job_id,
                status="ok",
                stdout_b64=base64.b64encode(raw_output).decode("ascii"),
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("Job execution exception: %s", exc, exc_info=True)
            return JobResultFrame(
                job_id=dispatch.job_id,
                status="error",
                error_code=CODE_EXECUTION_FAILED,
            )
        finally:
            # 6. Ephemeral secret zeroization
            if ctx is not None:
                ctx.destroy()
            for i in range(len(token_ba)):
                token_ba[i] = 0
            del token_ba[:]
