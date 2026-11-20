# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, ANN401, PLR0911, PLR0912, PLR0915, C901, ASYNC240, ARG001, TRY004, S603, S607
"""CLI command validate-transition: workbench for transition helper testing (S15.3)."""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import ipaddress
import json
import logging
import os
import ssl
import subprocess
import tempfile
import time
import traceback
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import websockets
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from agent.cli_report import (
    ContextScrubber,
    ExitCode,
    ReportMetrics,
    SchemaStatus,
    ValidationReport,
)
from agent.context.transition_context import (
    RepoContext,
    build_transition_context,
)
from agent.context.verdict import (
    VerdictParseError,
    parse_verdict_output,
)
from agent.harnesses.in_app_sdk import InAppSdkHarness
from agent.harnesses.remote_runner import RemoteRunnerHarness
from agent.providers.base import ToolCallStep
from agent.remote_runner.config import RunnerConfig
from agent.remote_runner.daemon import RunnerDaemon
from agent.remote_runner.executor import RunnerJobExecutor
from agent.runners.cli_pipe import CliPipeHarness
from agent.testing.fixtures import (
    Cassette,
    FixtureCLIRunner,
    FixtureLLMProvider,
    load_cassette,
)
from kanban.agents.cli_policy import CliPolicyError, assert_runtime_argv
from kanban.runners.hub import (
    HelloAckFrame,
    HelloFrame,
    RunnerWssHub,
)

if TYPE_CHECKING:
    import argparse

__all__ = [
    "configure_validate_transition_parser",
    "handle_validate_transition",
]


class ExplicitFixtureLLMProvider(FixtureLLMProvider):
    """Fixture LLM provider that replays explicit single cassette without slug mismatch."""

    def _find_matching_cassette(
        self,
        *,
        model: str,
        prompt: str,
        metadata: dict[str, str],
    ) -> Cassette:
        if len(self._cassettes) == 1:
            return self._cassettes[0]
        return super()._find_matching_cassette(model=model, prompt=prompt, metadata=metadata)


class ExplicitFixtureCLIRunner(FixtureCLIRunner):
    """Fixture CLI runner that replays explicit single cassette without prefix mismatch."""

    def _find_matching_cassette(
        self,
        *,
        argv: tuple[str, ...],
        stdin_str: str,
    ) -> Cassette:
        if len(self._cassettes) == 1:
            return self._cassettes[0]
        return super()._find_matching_cassette(argv=argv, stdin_str=stdin_str)


logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_MS: Final[int] = 60_000
_MIN_FRONTMATTER_PARTS: Final[int] = 3


def configure_validate_transition_parser(parser: argparse.ArgumentParser) -> None:
    """Configure arguments and flags for validate-transition subcommand (S15.3)."""
    parser.add_argument(
        "--agent-config",
        type=str,
        required=True,
        help="Path to YAML/JSON AgentDefinition config file.",
    )
    parser.add_argument(
        "--ticket-file",
        type=str,
        required=True,
        help="Path to YAML/JSON or Markdown ticket file.",
    )
    parser.add_argument(
        "--repo-path",
        type=str,
        default=None,
        help="Path to Git repository checkout or bare .git directory.",
    )
    parser.add_argument(
        "--head-ref",
        type=str,
        default="HEAD",
        help="Target Git reference (branch, tag, or SHA). Defaults to HEAD.",
    )
    parser.add_argument(
        "--from-state",
        type=str,
        required=True,
        help="Initial ticket state before transition (e.g. 'In Review').",
    )
    parser.add_argument(
        "--to-state",
        type=str,
        required=True,
        help="Destination ticket state for transition (e.g. 'Done').",
    )
    parser.add_argument(
        "--print-stdin-context",
        action="store_true",
        default=False,
        help="Print full scrubbed kb-transition-context/v1 YAML in Section 1.",
    )
    parser.add_argument(
        "--verbose-tools",
        action="store_true",
        default=False,
        help="Print verbose JSON arguments and results for executed tool steps.",
    )
    parser.add_argument(
        "--provider",
        choices=("ollama", "gemini", "openai", "fixture"),
        default=None,
        help="LLM provider kind override.",
    )
    parser.add_argument(
        "--cassette",
        type=str,
        default=None,
        help="Path to YAML fixture cassette for offline replay.",
    )
    parser.add_argument(
        "--http-cassette",
        type=str,
        default=None,
        help="Path to HTTP cassette for network replay.",
    )
    parser.add_argument(
        "--mcp-fixture",
        type=str,
        default=None,
        help="Path to YAML file mapping canned read-only MCP responses.",
    )
    parser.add_argument(
        "--remote-loopback",
        action="store_true",
        default=False,
        help="Spin up in-process TLS 1.3 mTLS RunnerWssHub + RunnerDaemon for remote_runner.",
    )
    parser.add_argument(
        "--report",
        choices=("text", "json"),
        default="text",
        help="Output report serialization format.",
    )
    parser.add_argument(
        "--require-approve",
        action="store_true",
        default=False,
        help="Require decision to be 'approve'; exits with code 2 on 'reject'.",
    )


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    """Parse a file as YAML or JSON into a dictionary."""
    content = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(content)
    if not isinstance(loaded, dict):
        msg = f"Expected YAML/JSON object in {path}, got {type(loaded).__name__}"
        raise ValueError(msg)
    return loaded


def _parse_ticket_file(ticket_path: Path) -> dict[str, Any]:
    """Parse ticket file (YAML, JSON, or Markdown with frontmatter)."""
    raw_text = ticket_path.read_text(encoding="utf-8")
    ticket_data: dict[str, Any] = {}
    body_text = raw_text

    if raw_text.startswith("---"):
        parts = raw_text.split("---", 2)
        if len(parts) >= _MIN_FRONTMATTER_PARTS:
            loaded = yaml.safe_load(parts[1])
            if isinstance(loaded, dict):
                ticket_data = loaded
            body_text = parts[2].strip()
    else:
        loaded = yaml.safe_load(raw_text)
        if isinstance(loaded, dict):
            ticket_data = loaded

    ticket_id = str(ticket_data.get("id") or ticket_data.get("key") or ticket_path.stem)
    summary = str(ticket_data.get("title") or ticket_data.get("summary") or "")
    priority = str(ticket_data.get("priority") or "High")
    labels = list(ticket_data.get("labels") or [])

    if "description_markdown" in ticket_data:
        desc = str(ticket_data["description_markdown"])
    elif "description" in ticket_data:
        desc = str(ticket_data["description"])
    else:
        desc_parts: list[str] = []
        if "user_story" in ticket_data:
            desc_parts.append(f"### User Story\n{ticket_data['user_story']}")
        if "scoped_technical_actions" in ticket_data:
            acts = "\n".join(f"- {a}" for a in ticket_data["scoped_technical_actions"])
            desc_parts.append(f"### Scoped Technical Actions\n{acts}")
        if "definition_of_done" in ticket_data:
            dods = "\n".join(f"- {d}" for d in ticket_data["definition_of_done"])
            desc_parts.append(f"### Definition of Done\n{dods}")
        desc = "\n\n".join(desc_parts) if desc_parts else body_text

    actor = str(ticket_data.get("actor") or "@agent")

    return {
        "key": ticket_id,
        "summary": summary,
        "priority": priority,
        "labels": labels,
        "description_markdown": desc,
        "actor": actor,
    }


def _resolve_head_commit(repo_path: Path, head_ref: str = "HEAD") -> str:
    """Resolve Git reference to commit SHA without mutating working tree."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", head_ref],
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            sha = proc.stdout.strip()
            if len(sha) in (40, 64):
                return sha
    except (OSError, subprocess.SubprocessError):
        pass
    return "94a1f02c8e000000000000000000000000000000"


def _build_mcp_fixture_transport(
    mcp_data: dict[str, Any],
) -> Any:
    """Create a mock transport callable returning canned MCP tool responses."""

    def transport(url: str, tool_name: str, args: dict[str, object]) -> Any:
        tool_section = mcp_data.get(tool_name)
        if isinstance(tool_section, dict):
            for candidate_key in ("identifier", "ticket_id", "slug", "key", "query"):
                val = args.get(candidate_key)
                if val is not None and str(val) in tool_section:
                    return tool_section[str(val)]
            if "default" in tool_section:
                return tool_section["default"]
            return tool_section
        if tool_section is not None:
            return tool_section
        return {
            "tool": tool_name,
            "status": "ok",
            "args": args,
            "result": f"Simulated output for {tool_name}",
        }

    return transport


async def _run_remote_loopback(
    ctx: Any,
    agent_config: dict[str, Any],
    *,
    repo_path: Path | None,
    cassette: str | None,
) -> bytes:
    """Run an in-process TLS 1.3 mTLS RunnerWssHub and RunnerDaemon loopback execution."""
    # 1. Ephemeral PKI generation in temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        now = dt.datetime.now(dt.UTC)
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Kanban Loopback CA")])
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(ca_key, hashes.SHA256())
        )
        ca_cert_path = tmp_p / "ca.crt"
        ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

        server_key = ec.generate_private_key(ec.SECP256R1())
        server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        server_cert = (
            x509.CertificateBuilder()
            .subject_name(server_name)
            .issuer_name(ca_name)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + dt.timedelta(days=1))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("localhost"),
                        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                    ]
                ),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        server_cert_path = tmp_p / "server.crt"
        server_key_path = tmp_p / "server.key"
        server_cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
        server_key_path.write_bytes(
            server_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )

        client_key = ec.generate_private_key(ec.SECP256R1())
        client_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "loopback-runner")])
        client_cert = (
            x509.CertificateBuilder()
            .subject_name(client_name)
            .issuer_name(ca_name)
            .public_key(client_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + dt.timedelta(days=1))
            .sign(ca_key, hashes.SHA256())
        )
        client_cert_path = tmp_p / "client.crt"
        client_key_path = tmp_p / "client.key"
        client_cert_path.write_bytes(client_cert.public_bytes(serialization.Encoding.PEM))
        client_key_path.write_bytes(
            client_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        client_key_path.chmod(0o600)

        # 2. Server setup
        hub = RunnerWssHub()
        pool_slug = str(agent_config.get("remote_runner_pool_slug") or "default-runners")
        server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ssl.minimum_version = ssl.TLSVersion.TLSv1_3
        server_ssl.verify_mode = ssl.CERT_REQUIRED
        server_ssl.load_verify_locations(cafile=str(ca_cert_path))
        server_ssl.load_cert_chain(certfile=str(server_cert_path), keyfile=str(server_key_path))

        async def ws_handler(ws: Any) -> None:
            r_id: uuid.UUID | None = None
            try:
                raw_hello = await ws.recv()
                if isinstance(raw_hello, bytes):
                    raw_hello = raw_hello.decode("utf-8")
                hello_data = json.loads(raw_hello)
                hello = HelloFrame.model_validate(hello_data)
                r_id = hello.runner_id
                ack = HelloAckFrame()
                await ws.send(ack.model_dump_json(by_alias=True))
                hub.register_runner(
                    runner_id=r_id,
                    workspace_id=uuid.UUID(int=0),
                    pool_slug=pool_slug,
                    hostname="localhost",
                    websocket=ws,
                    max_concurrency=hello.max_concurrency,
                )
                async for raw_msg in ws:
                    msg_str = raw_msg.decode("utf-8") if isinstance(raw_msg, bytes) else raw_msg
                    frame = json.loads(msg_str)
                    hub.handle_frame(r_id, frame)
            except Exception:  # noqa: BLE001, S110
                pass
            finally:
                if r_id is not None:
                    hub.unregister_runner(r_id)

        server = await websockets.serve(ws_handler, "127.0.0.1", 0, ssl=server_ssl)
        port = server.sockets[0].getsockname()[1]

        # 3. Client runner configuration
        repo_slug = str(agent_config.get("repo_slug") or "default")
        mounts: dict[str, Path] = {}
        if repo_path:
            mounts[repo_slug] = repo_path

        runner_cfg = RunnerConfig(
            server_url=f"https://127.0.0.1:{port}",
            pool_slug=pool_slug,
            client_cert_path=client_cert_path,
            client_key_path=client_key_path,
            ca_cert_path=ca_cert_path,
            repo_mounts=mounts,
        )

        cli_pipe_factory: Any = None
        if cassette:
            cas = load_cassette(cassette)
            cli_runner = ExplicitFixtureCLIRunner(cas)
            cli_pipe_factory = lambda **_kw: CliPipeHarness(runner=cli_runner)  # noqa: E731

        class LoopbackJobExecutor(RunnerJobExecutor):
            async def execute_job(
                self,
                dispatch: Any,
                *,
                on_tool_event: Any = None,
            ) -> Any:
                orig_statvfs = os.statvfs

                def safe_statvfs(path: str) -> Any:
                    res = orig_statvfs(path)

                    class _StatVFSRo:
                        f_flag = res.f_flag | os.ST_RDONLY

                        def __getattr__(self, name: str) -> Any:
                            return getattr(res, name)

                    return _StatVFSRo()

                try:
                    os.statvfs = safe_statvfs  # type: ignore[assignment]
                    return await super().execute_job(dispatch, on_tool_event=on_tool_event)
                finally:
                    os.statvfs = orig_statvfs

        executor = LoopbackJobExecutor(
            runner_cfg,
            cli_pipe_harness_factory=cli_pipe_factory,
        )
        daemon = RunnerDaemon(runner_cfg, executor=executor)
        daemon_task = asyncio.create_task(daemon.run_forever())

        try:
            # Wait for runner registration in hub
            for _ in range(500):
                if hub._runners:  # noqa: SLF001
                    break
                await asyncio.sleep(0.01)

            harness = RemoteRunnerHarness(hub=hub)
            spec_copy = dict(agent_config)
            spec_copy["repo_slug"] = repo_slug
            spec_copy["workspace_id"] = uuid.UUID(int=0)
            return await harness.run(ctx, spec_copy)
        finally:
            if daemon_task.done() and not daemon_task.cancelled():
                exc = daemon_task.exception()
                if exc:
                    traceback.print_exception(type(exc), exc, exc.__traceback__)
            daemon.stop()
            daemon_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await daemon_task
            server.close()
            await server.wait_closed()


async def handle_validate_transition(
    args: argparse.Namespace,
    *,
    scrubber: ContextScrubber | None = None,
) -> tuple[ValidationReport, ExitCode]:
    """Execute validate-transition CLI command across in_app_sdk, cli_pipe or remote_runner."""
    t0 = time.perf_counter()

    # 1. Validate & load --agent-config
    if not getattr(args, "agent_config", None):
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            schema_version="kb-validate-transition-report/v1",
            command="validate-transition",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="INVALID_ARGUMENTS",
                detail="Flag --agent-config is required.",
            ),
        ), ExitCode.RUNTIME_ERROR

    cfg_path = Path(args.agent_config)
    if not cfg_path.exists() or cfg_path.is_dir():
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            schema_version="kb-validate-transition-report/v1",
            command="validate-transition",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="FILE_NOT_FOUND",
                detail=f"Agent config file not found: {cfg_path}",
            ),
        ), ExitCode.RUNTIME_ERROR

    try:
        agent_config = _load_yaml_or_json(cfg_path)
    except Exception as exc:  # noqa: BLE001
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            schema_version="kb-validate-transition-report/v1",
            command="validate-transition",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="CONFIG_PARSE_ERROR",
                detail=str(exc),
            ),
        ), ExitCode.RUNTIME_ERROR

    # 2. Runtime argv policy double-gate (S15.3, KB-P5-16) up front
    harness_kind = str(agent_config.get("harness_kind") or "in_app_sdk")
    if (
        harness_kind in ("cli_pipe", "remote_runner")
        or agent_config.get("cli_args")
        or agent_config.get("cli_binary_allowlist_id")
    ):
        try:
            assert_runtime_argv(agent_config)
        except CliPolicyError as exc:
            total_ms = (time.perf_counter() - t0) * 1000.0
            return ValidationReport(
                schema_version="kb-validate-transition-report/v1",
                command="validate-transition",
                rendered_context="N/A",
                tool_trace=(),
                metrics=ReportMetrics(total_latency_ms=total_ms),
                schema_status=SchemaStatus(
                    valid=False,
                    status="failed",
                    error_code=exc.code,
                    detail=str(exc),
                ),
            ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    # 3. Validate & load --ticket-file
    if not getattr(args, "ticket_file", None):
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            schema_version="kb-validate-transition-report/v1",
            command="validate-transition",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="INVALID_ARGUMENTS",
                detail="Flag --ticket-file is required.",
            ),
        ), ExitCode.RUNTIME_ERROR

    ticket_path = Path(args.ticket_file)
    if not ticket_path.exists() or ticket_path.is_dir():
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            schema_version="kb-validate-transition-report/v1",
            command="validate-transition",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="FILE_NOT_FOUND",
                detail=f"Ticket file not found: {ticket_path}",
            ),
        ), ExitCode.RUNTIME_ERROR

    try:
        ticket_data = _parse_ticket_file(ticket_path)
    except Exception as exc:  # noqa: BLE001
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            schema_version="kb-validate-transition-report/v1",
            command="validate-transition",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="TICKET_PARSE_ERROR",
                detail=str(exc),
            ),
        ), ExitCode.RUNTIME_ERROR

    # 4. Resolve --repo-path if repo_access_mode != "none"
    repo_access_mode = str(agent_config.get("repo_access_mode") or "none")
    repo_ctx: RepoContext | None = None
    head_commit: str | None = None
    repo_path: Path | None = None

    if repo_access_mode != "none":
        if not getattr(args, "repo_path", None):
            total_ms = (time.perf_counter() - t0) * 1000.0
            return ValidationReport(
                schema_version="kb-validate-transition-report/v1",
                command="validate-transition",
                rendered_context="N/A",
                tool_trace=(),
                metrics=ReportMetrics(total_latency_ms=total_ms),
                schema_status=SchemaStatus(
                    valid=False,
                    status="failed",
                    error_code="REPO_PATH_REQUIRED",
                    detail="--repo-path is required when repo_access_mode != 'none'.",
                ),
            ), ExitCode.RUNTIME_ERROR

        repo_path = Path(args.repo_path)
        if not repo_path.exists():
            total_ms = (time.perf_counter() - t0) * 1000.0
            return ValidationReport(
                schema_version="kb-validate-transition-report/v1",
                command="validate-transition",
                rendered_context="N/A",
                tool_trace=(),
                metrics=ReportMetrics(total_latency_ms=total_ms),
                schema_status=SchemaStatus(
                    valid=False,
                    status="failed",
                    error_code="FILE_NOT_FOUND",
                    detail=f"Repo path does not exist: {repo_path}",
                ),
            ), ExitCode.RUNTIME_ERROR

        git_dir = repo_path / ".git" if (repo_path / ".git").exists() else repo_path
        head_commit = _resolve_head_commit(repo_path, getattr(args, "head_ref", "HEAD"))
        repo_ctx = RepoContext(
            mount_path=str(repo_path),
            mirror_path=str(git_dir),
            access="read-only",
            head_commit=head_commit,
        )

    # 5. Build Transition Context (KB-P5-19a)
    ticket_id = ticket_data["key"]
    project_key = ticket_id.split("-", maxsplit=1)[0] if "-" in ticket_id else "KAN"
    allowed_fields = list(agent_config.get("allowed_mutable_fields") or ["labels", "priority"])

    execution = {
        "id": "0196ed40-7b2a-7000-8000-112233445566",
        "project_key": project_key,
        "from_state": getattr(args, "from_state", "In Review"),
        "to_state": getattr(args, "to_state", "Done"),
        "actor": ticket_data["actor"],
        "allowed_mutable_fields": allowed_fields,
    }
    issue = {
        "key": ticket_id,
        "summary": ticket_data["summary"],
        "priority": ticket_data["priority"],
        "labels": ticket_data["labels"],
        "description_markdown": ticket_data["description_markdown"],
    }
    mcp_urls = {
        "agent_url": "https://kanban.internal/mcp/agent",
        "docs_url": "https://kanban.internal/mcp/docs",
    }

    ctx = build_transition_context(
        execution=execution,
        issue=issue,
        agent_def=agent_config,
        repo_context=repo_ctx,
        mcp_urls=mcp_urls,
        ephemeral_token="kb_agt_eph_" + "sample_token_for_cli_demo",
    )

    redaction_count = ctx.yaml_bytes.count(b"[REDACTED")

    if getattr(args, "print_stdin_context", False):
        rendered_context = (
            f"# Delimiter: {ctx.delimiter} | Head commit: {head_commit or 'none'} | "
            f"Secret redactions: {redaction_count}\n"
            f"{ctx.yaml_bytes.decode('utf-8')}"
        )
    else:
        rendered_context = (
            f"# Summary: kb-transition-context/v1 | Delimiter: {ctx.delimiter} | "
            f"Head commit: {head_commit or 'none'} | Secret redactions: {redaction_count}"
        )

    # 6. Dispatch to Harness (in_app_sdk, cli_pipe, or remote_runner)
    tool_steps: list[ToolCallStep] = []
    tool_trace_raw: list[dict[str, Any]] = []
    prompt_tokens = 0
    completion_tokens = 0
    ttft_ms: float | None = None

    try:
        if harness_kind == "in_app_sdk":
            provider_inst: Any = None
            if getattr(args, "cassette", None):
                cas = load_cassette(args.cassette)
                provider_inst = ExplicitFixtureLLMProvider([cas])
                ttft_ms = cas.simulated_ttft_ms

            mcp_transport: Any = None
            if getattr(args, "mcp_fixture", None):
                mcp_data = _load_yaml_or_json(Path(args.mcp_fixture))
                mcp_transport = _build_mcp_fixture_transport(mcp_data)

            in_app_harness = InAppSdkHarness(
                provider=provider_inst,
                mcp_transport=mcp_transport,
            )
            raw_bytes = await in_app_harness.run(ctx, agent_config)

            for t in in_app_harness.last_tool_traces:
                tool_steps.append(
                    ToolCallStep(
                        tool=t.tool_name,
                        args=t.args_redacted,
                        result={
                            "status": t.status,
                            "duration_ms": t.duration_ms,
                            "output_bytes": t.output_bytes,
                        },
                    )
                )
                tool_trace_raw.append(
                    {
                        "tool": t.tool_name,
                        "args": t.args_redacted,
                        "duration_ms": t.duration_ms,
                        "status": t.status,
                        "output_bytes": t.output_bytes,
                    }
                )

            if in_app_harness.last_report:
                prompt_tokens = in_app_harness.last_report.prompt_tokens
                completion_tokens = in_app_harness.last_report.completion_tokens

        elif harness_kind == "cli_pipe":
            runner: Any = None
            if getattr(args, "cassette", None):
                cas = load_cassette(args.cassette)
                runner = ExplicitFixtureCLIRunner(cas)
                ttft_ms = cas.simulated_ttft_ms

            cli_harness = CliPipeHarness(runner=runner)
            raw_bytes = await cli_harness.run(ctx, agent_config, repo_context=repo_ctx)

        elif harness_kind == "remote_runner":
            if getattr(args, "remote_loopback", False):
                raw_bytes = await _run_remote_loopback(
                    ctx,
                    agent_config,
                    repo_path=repo_path,
                    cassette=getattr(args, "cassette", None),
                )
            else:
                remote_harness = RemoteRunnerHarness()
                raw_bytes = await remote_harness.run(ctx, agent_config)
        else:
            total_ms = (time.perf_counter() - t0) * 1000.0
            return ValidationReport(
                schema_version="kb-validate-transition-report/v1",
                command="validate-transition",
                rendered_context=rendered_context,
                tool_trace=(),
                metrics=ReportMetrics(total_latency_ms=total_ms),
                schema_status=SchemaStatus(
                    valid=False,
                    status="failed",
                    error_code="UNKNOWN_HARNESS",
                    detail=f"Unknown harness kind: {harness_kind}",
                ),
            ), ExitCode.RUNTIME_ERROR

        # 7. Parse verdict output (KB-P5-19a)
        verdict_res = parse_verdict_output(raw_bytes, ctx)

    except VerdictParseError as exc:
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            schema_version="kb-validate-transition-report/v1",
            command="validate-transition",
            rendered_context=rendered_context,
            tool_trace=tuple(tool_steps),
            metrics=ReportMetrics(
                ttft_ms=ttft_ms,
                total_latency_ms=total_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=exc.code,
                detail=f"forged_candidates: {exc.forged_candidates}; {exc.detail}",
            ),
            transition_details={
                "harness": harness_kind,
                "delimiter": ctx.delimiter,
                "head_commit": head_commit,
                "redaction_count": redaction_count,
                "verdict": None,
                "tool_trace": tool_trace_raw,
            },
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION
    except Exception as exc:  # noqa: BLE001
        total_ms = (time.perf_counter() - t0) * 1000.0
        code = getattr(exc, "code", type(exc).__name__)
        exit_code = (
            ExitCode.SCHEMA_OR_POLICY_VIOLATION
            if "POLICY" in code or "BANNED" in code or "OVERRIDE" in code
            else ExitCode.RUNTIME_ERROR
        )
        return ValidationReport(
            schema_version="kb-validate-transition-report/v1",
            command="validate-transition",
            rendered_context=rendered_context,
            tool_trace=tuple(tool_steps),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=code,
                detail=str(exc),
            ),
        ), exit_code
    finally:
        ctx.destroy()

    decision_str = verdict_res.decision.decision
    verdict_dict = {
        "decision": decision_str,
        "reason_markdown": verdict_res.decision.reason_markdown,
        "verdict_sha256": verdict_res.verdict_sha256,
        "forged_candidates": verdict_res.forged_candidates,
        "field_updates": verdict_res.decision.field_updates,
        "add_labels": list(verdict_res.decision.add_labels),
    }

    total_ms = (time.perf_counter() - t0) * 1000.0
    metrics = ReportMetrics(
        ttft_ms=ttft_ms,
        total_latency_ms=total_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    # 8. Check --require-approve policy
    if decision_str == "reject" and getattr(args, "require_approve", False):
        schema_status = SchemaStatus(
            valid=False,
            status="failed",
            error_code="REJECT_NOT_PERMITTED",
            detail=f"Verdict decision 'reject' rejected under --require-approve: {verdict_res.decision.reason_markdown}",
        )
        exit_code = ExitCode.SCHEMA_OR_POLICY_VIOLATION
    else:
        schema_status = SchemaStatus(
            valid=True,
            status="passed",
            detail=(
                f"decision: {decision_str}, verdict_sha256: {verdict_res.verdict_sha256}, "
                f"forged_candidates: {verdict_res.forged_candidates}"
            ),
        )
        exit_code = ExitCode.OK

    report = ValidationReport(
        schema_version="kb-validate-transition-report/v1",
        command="validate-transition",
        rendered_context=rendered_context,
        tool_trace=tuple(tool_steps),
        metrics=metrics,
        schema_status=schema_status,
        transition_details={
            "harness": harness_kind,
            "delimiter": ctx.delimiter,
            "head_commit": head_commit,
            "redaction_count": redaction_count,
            "verdict": verdict_dict,
            "tool_trace": tool_trace_raw,
        },
    )

    return report, exit_code
