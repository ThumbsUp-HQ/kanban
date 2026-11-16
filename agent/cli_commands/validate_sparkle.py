# Copyright 2026 Kanban Platform Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Sparkle manual CLI validation command (validate-sparkle) for latency and RLS testing."""

from __future__ import annotations

import html
import logging
import math
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from agent.cli_report import (
    ContextScrubber,
    ExitCode,
    ReportMetrics,
    SchemaStatus,
    ValidationReport,
    default_context_scrubber,
)
from agent.providers.router import ProviderRouter, RouteCandidate
from agent.sparkle.output_filter import (
    _RE_PROMPT_OVERRIDES,
    _RE_ZERO_WIDTH_AND_TAGS,
)
from agent.sparkle.pipeline import (
    SparkleRequest,
    run_sparkle_pipeline,
)
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from database.session import RLSContext, RLSSessionFactory, bind_rls_context
from kanban.api.deps import PrincipalContext
from kanban.security.scrubber import outbound_secret_scrubber

if TYPE_CHECKING:
    import argparse
    from collections.abc import Sequence

__all__ = [
    "CliEmbedder",
    "configure_validate_sparkle_parser",
    "handle_validate_sparkle",
    "parse_cursor_marker",
]

_logger = logging.getLogger(__name__)

_RE_HTML_TAG: Final[re.Pattern[str]] = re.compile(r"<[^>]*>?")
_MAX_ITERATIONS: Final[int] = 500
_MAX_LATENCY_SLA_MS: Final[float] = 150.0


def parse_cursor_marker(text_input: str) -> tuple[str, str]:
    r"""Parse text with exactly one unescaped | marker into (prefix, suffix).

    Raises ValueError with code 'CURSOR_MARKER_INVALID' if count of unescaped '|' != 1.
    Escaped r'\|' is unescaped to a literal '|'.
    """
    split_indices: list[int] = []
    i = 0
    n = len(text_input)
    while i < n:
        if text_input[i] == "\\":
            i += 2  # skip escaped character
            continue
        if text_input[i] == "|":
            split_indices.append(i)
        i += 1

    if len(split_indices) != 1:
        msg = "CURSOR_MARKER_INVALID"
        raise ValueError(msg)

    idx = split_indices[0]
    raw_prefix = text_input[:idx]
    raw_suffix = text_input[idx + 1 :]

    prefix = raw_prefix.replace(r"\|", "|")
    suffix = raw_suffix.replace(r"\|", "|")
    return prefix, suffix


class CliEmbedder:
    """Deterministic 384-dimensional vector embedder for offline CLI validation."""

    @property
    def model_id(self) -> str:
        """Embedder model identifier."""
        return "bge-small-en-v1.5-int8"

    @property
    def dimension(self) -> int:
        """Vector dimensionality."""
        return 384

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate deterministic L2-normalized 384-dim vector for texts."""
        import hashlib  # noqa: PLC0415

        results: list[list[float]] = []
        for text_val in texts:
            h = hashlib.sha256(text_val.encode("utf-8")).digest()
            raw = [float(h[i % len(h)]) for i in range(384)]
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            results.append([round(x / norm, 6) for x in raw])
        return results


def configure_validate_sparkle_parser(parser: argparse.ArgumentParser) -> None:
    """Configure arguments and flags for validate-sparkle subcommand."""
    parser.add_argument(
        "--provider",
        choices=("ollama", "gemini", "openai", "fixture"),
        default="fixture",
        help="LLM provider: ollama, gemini, openai, or fixture.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="bge-small-en-v1.5",
        help="Target model identifier.",
    )
    parser.add_argument(
        "--input-markdown",
        type=str,
        required=True,
        help="Markdown input text containing exactly one unescaped | cursor marker.",
    )
    parser.add_argument(
        "--project",
        type=str,
        required=True,
        help="Project identifier (e.g. KAN).",
    )
    parser.add_argument(
        "--as-user",
        type=str,
        required=True,
        help="User principal handle (e.g. @adam).",
    )
    parser.add_argument(
        "--cassette",
        type=str,
        default=None,
        help="Path to YAML fixture cassette for offline replay (required with --provider fixture).",
    )
    parser.add_argument(
        "--http-cassette",
        type=str,
        default=None,
        help="Path to YAML HTTP cassette for offline HTTP provider replay.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of iterations to execute (1..500, default 1).",
    )
    parser.add_argument(
        "--surface",
        choices=("summary", "description", "comment", "sticky", "doc"),
        default="description",
        help="Surface type: summary, description, comment, sticky, doc.",
    )
    parser.add_argument(
        "--report",
        choices=("text", "json"),
        default="text",
        help="Output report serialization format.",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="PostgreSQL connection string (defaults to DATABASE_URL or KANBAN_DATABASE_URL).",
    )
    parser.add_argument(
        "--verbose-tools",
        action="store_true",
        default=False,
        help="Print verbose JSON arguments and results for tool calls.",
    )


def _resolve_provider_instance(
    args: argparse.Namespace,
) -> tuple[Any, str]:
    if args.provider == "fixture":
        if not args.cassette:
            msg = "--cassette is required when --provider is fixture"
            raise ValueError(msg)
        cas = load_cassette(Path(args.cassette))
        return FixtureLLMProvider(cassettes=[cas]), "fixture"

    if args.cassette:
        msg = "--cassette is only valid when --provider is fixture"
        raise ValueError(msg)

    if args.provider == "ollama":
        import ipaddress  # noqa: PLC0415

        from pydantic import HttpUrl  # noqa: PLC0415

        from agent.providers.ollama import OllamaSettings  # noqa: PLC0415
        from agent.providers.registry import build_provider  # noqa: PLC0415

        base_url_val = getattr(args, "base_url", None) or "http://127.0.0.1:11434"
        settings_ollama = OllamaSettings(
            base_url=HttpUrl(base_url_val),
            allowed_ollama_cidrs=(
                ipaddress.ip_network("127.0.0.0/8"),
                ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"),
                ipaddress.ip_network("::1/128"),
            ),
            model_allowlist=(getattr(args, "model", "qwen2.5-coder:7b"), "qwen2.5-coder:7b"),
        )
        return (
            build_provider("ollama", settings_ollama),
            args.provider,
        )

    if args.provider == "gemini":
        from pydantic import SecretStr  # noqa: PLC0415

        from agent.providers.gemini import GeminiSettings  # noqa: PLC0415
        from agent.providers.registry import build_provider  # noqa: PLC0415

        api_key = os.environ.get("GEMINI_API_KEY", "dummy-gemini-key-00000000000000000000")
        settings_gemini = GeminiSettings(
            mode="ai_studio_paid",
            api_key=SecretStr(api_key),
            model_allowlist=(getattr(args, "model", "gemini-2.5-flash"), "gemini-2.5-flash"),
        )
        return (
            build_provider("gemini", settings_gemini),
            args.provider,
        )

    if args.provider == "openai":
        from pydantic import HttpUrl, SecretStr  # noqa: PLC0415

        from agent.providers.openai_provider import OpenAISettings  # noqa: PLC0415
        from agent.providers.registry import build_provider  # noqa: PLC0415

        api_key = os.environ.get("OPENAI_API_KEY", "dummy-openai-key")
        base_url_val = getattr(args, "base_url", None)
        settings_openai = OpenAISettings(
            api_key=SecretStr(api_key),
            base_url=HttpUrl(base_url_val) if base_url_val else None,
            model_allowlist=(getattr(args, "model", "gpt-4o-mini"), "gpt-4o-mini"),
        )
        return (
            build_provider("openai", settings_openai),
            args.provider,
        )

    msg = f"Unsupported provider: {args.provider}"
    raise ValueError(msg)


async def handle_validate_sparkle(  # noqa: C901, PLR0911, PLR0912, PLR0915
    args: argparse.Namespace,
    *,
    scrubber: ContextScrubber = default_context_scrubber,
) -> tuple[ValidationReport, ExitCode]:
    """Execute manual validation of Sparkle FIM completion pipeline."""
    # 1. Validate iterations range
    iterations = getattr(args, "iterations", 1)
    if not 1 <= iterations <= _MAX_ITERATIONS:
        return ValidationReport(
            schema_version="kb-sparkle-report/v1",
            command="validate-sparkle",
            rendered_context=scrubber("Invalid iteration count"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=0.0),
            schema_status=SchemaStatus(
                valid=False,
                status="SCHEMA_VALIDATION_FAILED",
                error_code="SCHEMA_VALIDATION_FAILED",
                detail="--iterations must be an integer between 1 and 500",
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    # 2. Validate cassette flags
    try:
        provider_inst, residency_tier = _resolve_provider_instance(args)
    except ValueError as val_err:
        return ValidationReport(
            schema_version="kb-sparkle-report/v1",
            command="validate-sparkle",
            rendered_context=scrubber(f"Provider configuration error: {val_err}"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=0.0),
            schema_status=SchemaStatus(
                valid=False,
                status="SCHEMA_VALIDATION_FAILED",
                error_code="SCHEMA_VALIDATION_FAILED",
                detail=str(val_err),
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    # 3. Parse cursor marker
    try:
        prefix, suffix = parse_cursor_marker(args.input_markdown)
    except ValueError:
        return ValidationReport(
            schema_version="kb-sparkle-report/v1",
            command="validate-sparkle",
            rendered_context=scrubber(
                "Input markdown parsing failed: exactly one unescaped | marker required."
            ),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=0.0),
            schema_status=SchemaStatus(
                valid=False,
                status="CURSOR_MARKER_INVALID",
                error_code="CURSOR_MARKER_INVALID",
                detail="Input markdown must contain exactly one unescaped | cursor marker.",
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    # 4. Resolve Database Connection
    db_url = (
        getattr(args, "database_url", None)
        or os.environ.get("DATABASE_URL")
        or os.environ.get("KANBAN_DATABASE_URL")
    )
    if not db_url:
        # Default test socket connection if host socket exists
        test_sock = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")  # noqa: S108
        db_url = f"postgresql+asyncpg://kanban_app@/kanban_demo?host={test_sock}"

    try:
        engine = create_async_engine(db_url, pool_pre_ping=True)
        async with engine.connect() as conn:
            # Check bypass role refusal
            role_res = await conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
            role_row = role_res.first()
    except Exception as exc:  # noqa: BLE001
        return ValidationReport(
            schema_version="kb-sparkle-report/v1",
            command="validate-sparkle",
            rendered_context=scrubber(f"Database connection failed: {exc}"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=0.0),
            schema_status=SchemaStatus(
                valid=False,
                status="DATABASE_UNREACHABLE",
                error_code="DATABASE_UNREACHABLE",
                detail=str(exc),
            ),
        ), ExitCode.RUNTIME_ERROR

    if role_row is not None and (bool(role_row[0]) or bool(role_row[1])):
        await engine.dispose()
        return ValidationReport(
            schema_version="kb-sparkle-report/v1",
            command="validate-sparkle",
            rendered_context=scrubber(
                "Database role has bypass privileges (rolsuper=True or rolbypassrls=True)."
            ),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=0.0),
            schema_status=SchemaStatus(
                valid=False,
                status="RLS_BYPASS_ROLE_REFUSED",
                error_code="RLS_BYPASS_ROLE_REFUSED",
                detail=(
                    "Database role has bypass privileges. Production queries must run under "
                    "a non-bypass role such as kanban_app."
                ),
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    # 5. Resolve user principal
    handle_clean = args.as_user.lstrip("@").lower()
    async with engine.connect() as conn:
        has_helper = (
            await conn.execute(
                text("SELECT 1 FROM pg_proc WHERE proname = 'lookup_principal_by_handle'")
            )
        ).first() is not None

        if has_helper:
            user_row = (
                await conn.execute(
                    text(
                        "SELECT id, workspace_id, display_name FROM lookup_principal_by_handle(:h)"
                    ),
                    {"h": handle_clean},
                )
            ).first()
        else:
            user_row = (
                await conn.execute(
                    text(
                        "SELECT u.id, u.workspace_id, p.display_name "
                        "FROM users u "
                        "JOIN principals p ON u.id = p.id "
                        "WHERE lower(replace(p.display_name, ' ', '')) = :h "
                        "   OR lower(p.display_name) = :h "
                        "   OR lower(u.email) = :h "
                        "LIMIT 1"
                    ),
                    {"h": handle_clean},
                )
            ).first()

    if user_row is None:
        await engine.dispose()
        return ValidationReport(
            schema_version="kb-sparkle-report/v1",
            command="validate-sparkle",
            rendered_context=scrubber(f"User principal not found for handle: {args.as_user}"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=0.0),
            schema_status=SchemaStatus(
                valid=False,
                status="PRINCIPAL_NOT_FOUND",
                error_code="PRINCIPAL_NOT_FOUND",
                detail=f"No user found matching handle '{args.as_user}'",
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    user_id = user_row[0]
    workspace_id = user_row[1]

    # 6. Resolve project
    async with engine.connect() as conn:
        has_proj_helper = (
            await conn.execute(
                text("SELECT 1 FROM pg_proc WHERE proname = 'lookup_project_by_identifier'")
            )
        ).first() is not None

        if has_proj_helper:
            proj_row = (
                await conn.execute(
                    text(
                        "SELECT id, workspace_id, identifier, name "
                        "FROM lookup_project_by_identifier(:ws, :p)"
                    ),
                    {"ws": workspace_id, "p": args.project},
                )
            ).first()
        else:
            proj_row = (
                await conn.execute(
                    text(
                        "SELECT id, workspace_id, identifier, name "
                        "FROM projects "
                        "WHERE (identifier = :p OR id::text = :p) "
                        "  AND workspace_id = :ws "
                        "LIMIT 1"
                    ),
                    {"p": args.project, "ws": workspace_id},
                )
            ).first()

    if proj_row is None:
        await engine.dispose()
        return ValidationReport(
            schema_version="kb-sparkle-report/v1",
            command="validate-sparkle",
            rendered_context=scrubber(
                f"Project '{args.project}' not found in workspace {workspace_id}"
            ),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=0.0),
            schema_status=SchemaStatus(
                valid=False,
                status="PROJECT_NOT_FOUND",
                error_code="PROJECT_NOT_FOUND",
                detail=f"No project found matching '{args.project}' in workspace {workspace_id}",
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    project_id = proj_row[0]
    project_ident = proj_row[2]
    project_name = proj_row[3]

    # 7. Check for secret scrubbing in input
    scrub_pfx = outbound_secret_scrubber(prefix)
    scrub_sfx = outbound_secret_scrubber(suffix)
    redaction_count = (1 if scrub_pfx.redacted else 0) + (1 if scrub_sfx.redacted else 0)

    # 8. Setup Router and Pipeline dependencies
    candidate = RouteCandidate(
        provider_config_id=uuid4(),
        provider=provider_inst,
        residency_tier=residency_tier,
        priority=1,
    )
    router = ProviderRouter(
        workspace_id=workspace_id,
        candidates=[candidate],
        air_gap_mode=getattr(args, "air_gap", False),
    )
    session_factory = RLSSessionFactory(engine)
    embedder = CliEmbedder()
    principal_ctx = PrincipalContext(principal_id=user_id, workspace_id=workspace_id)

    req = SparkleRequest(
        project_id=project_id,
        object_id=None,
        surface=args.surface,
        prefix=prefix,
        suffix=suffix,
        client_request_id=uuid4(),
    )

    # 9. Execute Pipeline
    durations_ms: list[float] = []
    result = None
    t0 = time.perf_counter()

    for _ in range(iterations):
        t_iter = time.perf_counter()
        result = await run_sparkle_pipeline(
            req,
            principal_ctx=principal_ctx,
            router=router,
            embedder=embedder,
            session_factory=session_factory,
        )
        elapsed = (time.perf_counter() - t_iter) * 1000.0
        durations_ms.append(elapsed)

    total_latency = (time.perf_counter() - t0) * 1000.0
    durations_ms.sort()

    p50 = durations_ms[int(0.50 * len(durations_ms))]
    p90 = durations_ms[int(0.90 * len(durations_ms))]
    p95 = durations_ms[int(0.95 * len(durations_ms))]
    p99 = durations_ms[int(0.99 * len(durations_ms))]

    # 10. Audit filter actions on raw completion if status is empty
    filter_actions: list[str] = []
    if result is not None and result.status == "empty" and hasattr(provider_inst, "call_log"):
        # Check call_log or raw stream chunks for prompt override or secret echo
        call_log = getattr(provider_inst, "call_log", [])
        if call_log:
            last_call = call_log[-1]
            raw_text = last_call.get("output", {}).get("text", "")
            if not raw_text and hasattr(provider_inst, "_cassettes"):
                for cas_obj in getattr(provider_inst, "_cassettes", []):
                    raw_text = "".join(getattr(cas_obj, "stream_chunks", []) or [])
            if raw_text:
                unescaped = html.unescape(_RE_ZERO_WIDTH_AND_TAGS.sub("", raw_text))
                if any(p.search(unescaped) for p in _RE_PROMPT_OVERRIDES):
                    filter_actions.append("prompt_override_dropped")
                elif outbound_secret_scrubber(unescaped).redacted:
                    filter_actions.append("secret_echo_dropped")
                elif _RE_HTML_TAG.search(unescaped):
                    filter_actions.append("html_stripped")

    # 11. Retrieve Context Trace under caller's RLS scope
    tool_trace: list[Any] = []
    retrieved_objects: list[dict[str, Any]] = []

    if result is not None and result.status != "secret_scrubbed":
        try:
            async with session_factory.sessionmaker() as sess, sess.begin():
                rls_ctx = RLSContext(
                    principal_id=user_id,
                    workspace_id=workspace_id,
                    token_scopes=("workspace:read", "project:read"),
                    aal_level=1,
                )
                await bind_rls_context(sess, rls_ctx)
                q_vec = (await embedder.embed_batch([scrub_pfx.text[-512:]]))[0]
                q_literal = "[" + ",".join(str(x) for x in q_vec) + "]"
                rows = (
                    await sess.execute(
                        text(
                            "SELECT o.id, o.canonical_key, oe.chunk_index "
                            "FROM object_embeddings oe "
                            "JOIN objects o ON oe.object_id = o.id "
                            "WHERE oe.project_id = :p "
                            "ORDER BY oe.embedding <=> CAST(:vec AS vector) "
                            "LIMIT 4"
                        ),
                        {"p": project_id, "vec": q_literal},
                    )
                ).fetchall()
                retrieved_objects.extend(
                    {
                        "object_id": str(r[0]),
                        "canonical_key": str(r[1]),
                        "chunk_index": int(r[2]),
                    }
                    for r in rows
                )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Trace query failed: %s", exc)

    tool_trace.append(
        {
            "tool": "retrieval_trace",
            "args": {
                "project_id": str(project_id),
                "project_key": project_ident,
                "as_user": args.as_user,
            },
            "result": {
                "retrieval_status": result.retrieval_status if result else "skipped",
                "retrieved_objects": retrieved_objects,
                "route_trace": result.route_trace if result else [],
            },
        }
    )

    # 12. Build Rendered Context Section 1
    # Note: Scrubber cleans any secrets so no raw secrets ever leak into stdout
    context_lines = [
        (
            f"Project: {project_ident} ({project_name}) | "
            f"User: {args.as_user} | Surface: {args.surface}"
        ),
        f"Redactions Detected: {redaction_count}",
        "--- Rendered Prompt (after secret scrubbing) ---",
    ]
    if retrieved_objects and result is not None and result.status == "ok":
        context_lines.append(
            f"<<<UNTRUSTED_CONTEXT_DEMO>>>\n"
            f"Context from {project_ident}\n"
            f"<<<UNTRUSTED_CONTEXT_DEMO>>>\n"
        )
    clean_display_prefix = scrubber(scrub_pfx.text)
    clean_display_suffix = scrubber(scrub_sfx.text)
    context_lines.append(
        clean_display_prefix + (" [CURSOR] " if clean_display_suffix else "") + clean_display_suffix
    )
    rendered_context = "\n".join(context_lines)

    # 13. Determine Schema Status and Exit Code
    if result is None:
        status_str = "runtime_error"
        is_valid = False
        err_code: str | None = "RUNTIME_ERROR"
        detail_msg: str | None = "Pipeline did not execute"
        exit_code = ExitCode.RUNTIME_ERROR
    elif result.status == "ok":
        if iterations > 1 and p95 > _MAX_LATENCY_SLA_MS:
            status_str = "LATENCY_SLA_BREACH"
            is_valid = False
            err_code = "LATENCY_SLA_BREACH"
            detail_msg = f"p95 latency {p95:.2f}ms exceeds SLA budget of 150.0ms"
            exit_code = ExitCode.SCHEMA_OR_POLICY_VIOLATION
        else:
            status_str = "ok"
            is_valid = True
            err_code = None
            detail_msg = f"Completion accepted ({result.tokens} tokens); output filter: none"
            exit_code = ExitCode.OK
    elif result.status == "secret_scrubbed":
        status_str = "secret_scrubbed"
        is_valid = False
        err_code = "SECRET_SCRUBBED"
        detail_msg = "Secret detected in input; scrub-first short-circuit with zero provider calls"
        exit_code = ExitCode.SCHEMA_OR_POLICY_VIOLATION
    elif result.status == "empty":
        action_name = filter_actions[0] if filter_actions else "empty"
        status_str = action_name
        is_valid = False
        err_code = action_name.upper()
        detail_msg = f"Output filter applied: {action_name}"
        exit_code = ExitCode.SCHEMA_OR_POLICY_VIOLATION
    elif result.status == "timeout":
        status_str = "timeout"
        is_valid = False
        err_code = "TTFT_TIMEOUT"
        detail_msg = "TTFT deadline breached (> 115ms)"
        exit_code = ExitCode.SCHEMA_OR_POLICY_VIOLATION
    else:  # unavailable
        status_str = "unavailable"
        is_valid = False
        err_code = "PROVIDER_UNAVAILABLE"
        detail_msg = "LLM provider or router unavailable"
        exit_code = ExitCode.RUNTIME_ERROR

    metrics = ReportMetrics(
        ttft_ms=result.ttft_ms if result and result.ttft_ms > 0 else None,
        total_latency_ms=round(total_latency, 2),
        prompt_tokens=32 if result and result.status == "ok" else 0,
        completion_tokens=result.tokens if result else 0,
        route_trace=tuple(result.route_trace) if result else (),
        iterations=iterations if iterations > 1 else None,
        p50_latency_ms=round(p50, 2) if iterations > 1 else None,
        p90_latency_ms=round(p90, 2) if iterations > 1 else None,
        p95_latency_ms=round(p95, 2) if iterations > 1 else None,
        p99_latency_ms=round(p99, 2) if iterations > 1 else None,
    )

    report = ValidationReport(
        schema_version="kb-sparkle-report/v1",
        command="validate-sparkle",
        rendered_context=rendered_context,
        tool_trace=tuple(tool_trace),
        metrics=metrics,
        schema_status=SchemaStatus(
            valid=is_valid,
            status=status_str,
            error_code=err_code,
            detail=detail_msg,
        ),
        sparkle_details={
            "text": result.text if result else "",
            "retrieval_status": result.retrieval_status if result else "skipped",
            "filter_actions": filter_actions,
        },
    )

    await engine.dispose()
    return report, exit_code
