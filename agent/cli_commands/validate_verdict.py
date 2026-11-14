# Copyright 2026 Kanban Platform Contributors
"""CLI command validate-verdict for transition context rendering and verdict parsing."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from agent.cli_report import (
    ExitCode,
    ReportMetrics,
    SchemaStatus,
    ValidationReport,
)
from agent.context.transition_context import (
    RenderedContext,
    RepoContext,
    build_transition_context,
)
from agent.context.verdict import (
    VerdictParseError,
    parse_verdict_output,
)

if TYPE_CHECKING:
    import argparse

__all__ = [
    "configure_validate_verdict_parser",
    "handle_validate_verdict",
]


def configure_validate_verdict_parser(parser: argparse.ArgumentParser) -> None:
    """Configure arguments and flags for validate-verdict subcommand."""
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="Path to file containing raw agent stdout to validate.",
    )
    parser.add_argument(
        "--nonce",
        type=str,
        default=None,
        help="Expected verdict nonce hex string.",
    )
    parser.add_argument(
        "--allowed-mutable-fields",
        type=str,
        default=None,
        help="Comma-separated list of allowed mutable fields (e.g. 'labels,priority').",
    )
    parser.add_argument(
        "--render-context",
        action="store_true",
        default=False,
        help="Render spotlighted context YAML for a local ticket file.",
    )
    parser.add_argument(
        "--ticket-file",
        type=str,
        default=None,
        help="Path to local ticket file (YAML or Markdown) for context rendering.",
    )
    parser.add_argument(
        "--report",
        choices=("text", "json"),
        default="text",
        help="Output report serialization format.",
    )


def _load_raw_output_bytes(path: Path) -> bytes:
    """Read output bytes from file, extracting stdout from YAML cassette if present."""
    raw = path.read_bytes()
    if path.suffix.lower() in (".yaml", ".yml") or b"cli_result:" in raw:
        try:
            data = yaml.safe_load(raw.decode("utf-8"))
            if isinstance(data, dict):
                if "cli_result" in data and isinstance(data["cli_result"], dict):
                    stdout_str = str(data["cli_result"].get("stdout", ""))
                    return stdout_str.encode("utf-8")
                if "final_verdict" in data and isinstance(data["final_verdict"], dict):
                    return json.dumps(data["final_verdict"]).encode("utf-8")
        except (yaml.YAMLError, ValueError, KeyError):
            pass
    return raw


_MIN_FRONTMATTER_PARTS = 3


def _handle_render_context(  # noqa: C901, PLR0912, PLR0915
    args: argparse.Namespace,
    t0: float,
) -> tuple[ValidationReport, ExitCode]:
    """Render spotlighted context YAML for a local ticket file."""
    if not args.ticket_file:
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-verdict",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="INVALID_ARGUMENTS",
                detail="Flag --ticket-file is required when --render-context is specified.",
            ),
        ), ExitCode.RUNTIME_ERROR

    ticket_path = Path(args.ticket_file)
    if not ticket_path.exists() or ticket_path.is_dir():
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-verdict",
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
        priority = str(ticket_data.get("priority") or "Urgent")
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

        project_key = ticket_id.split("-", maxsplit=1)[0] if "-" in ticket_id else "KAN"

        execution = {
            "id": "0196ed40-7b2a-7000-8000-112233445566",
            "project_key": project_key,
            "from_state": ticket_data.get("state") or "In Review",
            "to_state": "Done",
            "actor": "@adam",
            "allowed_mutable_fields": ["labels", "priority"],
        }
        issue = {
            "key": ticket_id,
            "summary": summary,
            "priority": priority,
            "labels": labels,
            "description_markdown": desc,
        }
        agent_def = {
            "slug": "validate-verdict-cli",
            "timeout_ms": 30000,
        }
        mcp_urls = {
            "agent_url": "https://kanban.internal/mcp/agent",
            "docs_url": "https://kanban.internal/mcp/docs",
        }
        repo_context = RepoContext(
            mount_path="/workspace/repo",
            access="read-only",
            head_commit="94a1f02c8e",
        )

        ctx = build_transition_context(
            execution=execution,
            issue=issue,
            agent_def=agent_def,
            repo_context=repo_context,
            mcp_urls=mcp_urls,
            ephemeral_token="kb_agt_eph_" + "sample_token_for_cli_demo",
        )

        rendered_yaml = ctx.yaml_bytes.decode("utf-8")
        rendered_context = f"# Ephemeral token: <not rendered>\n{rendered_yaml}"
        ctx.destroy()

        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-verdict",
            rendered_context=rendered_context,
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=True,
                status="passed",
                detail="Context rendered successfully",
            ),
        ), ExitCode.OK

    except Exception as exc:  # noqa: BLE001
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-verdict",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=type(exc).__name__,
                detail=str(exc),
            ),
        ), ExitCode.RUNTIME_ERROR


async def handle_validate_verdict(  # noqa: PLR0911
    args: argparse.Namespace,
) -> tuple[ValidationReport, ExitCode]:
    """Execute validate-verdict CLI command to render context or validate agent stdout."""
    t0 = time.perf_counter()

    if getattr(args, "render_context", False):
        return _handle_render_context(args, t0)

    if not args.output_file:
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-verdict",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="INVALID_ARGUMENTS",
                detail="Must specify --output-file or --render-context.",
            ),
        ), ExitCode.RUNTIME_ERROR

    output_path = Path(args.output_file)
    if not output_path.exists() or output_path.is_dir():  # noqa: ASYNC240
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-verdict",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="FILE_NOT_FOUND",
                detail=f"Output file does not exist: {output_path}",
            ),
        ), ExitCode.RUNTIME_ERROR

    try:
        raw_bytes = _load_raw_output_bytes(output_path)
    except Exception as exc:  # noqa: BLE001
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-verdict",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="FILE_READ_ERROR",
                detail=f"Failed to read output file: {exc}",
            ),
        ), ExitCode.RUNTIME_ERROR

    allowed_fields: frozenset[str] = frozenset()
    if args.allowed_mutable_fields:
        allowed_fields = frozenset(
            field.strip() for field in args.allowed_mutable_fields.split(",") if field.strip()
        )

    ctx = RenderedContext(
        yaml_bytes=b"",
        sha256="",
        delimiter="",
        verdict_nonce=args.nonce or "",
        ephemeral_token=bytearray(),
        allowed_mutable_fields=allowed_fields,
    )

    try:
        result = parse_verdict_output(raw_bytes, ctx)
        total_ms = (time.perf_counter() - t0) * 1000.0
        detail = (
            f"decision: {result.decision.decision}, "
            f"verdict_sha256: {result.verdict_sha256}, "
            f"forged_candidates: {result.forged_candidates}"
        )
        return ValidationReport(
            command="validate-verdict",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=True,
                status="passed",
                detail=detail,
            ),
        ), ExitCode.OK

    except VerdictParseError as exc:
        total_ms = (time.perf_counter() - t0) * 1000.0
        detail = f"forged_candidates: {exc.forged_candidates}; {exc.detail}"
        return ValidationReport(
            command="validate-verdict",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=exc.code,
                detail=detail,
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    except Exception as exc:  # noqa: BLE001
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-verdict",
            rendered_context="N/A",
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=type(exc).__name__,
                detail=str(exc),
            ),
        ), ExitCode.RUNTIME_ERROR
