# Copyright 2026 Kanban Platform Contributors
"""Standardized 4-section report schema, exit codes, and formatters for agent CLI."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from agent.providers.base import ToolCallStep  # noqa: TC001  # Runtime Pydantic model field
from agent.providers.errors import (
    ProviderPolicyError,
    ProviderRefusal,
    ProviderSafetyBlock,
    ProviderSchemaError,
    ProviderTimeout,
)
from agent.testing.fixtures import (
    CassetteMismatchError,
    CassetteValidationError,
)

__all__ = [
    "ContextScrubber",
    "ExitCode",
    "ReportMetrics",
    "SchemaStatus",
    "ValidationReport",
    "default_context_scrubber",
    "map_exception_to_exit_code",
    "render_report",
]

ContextScrubber = Callable[[str], str]


def default_context_scrubber(text: str) -> str:
    """Identity context scrubber used by default in CLI reports."""
    return text


class ExitCode(IntEnum):
    """Deterministic exit codes for kanban-agent CLI commands."""

    OK = 0
    RUNTIME_ERROR = 1
    SCHEMA_OR_POLICY_VIOLATION = 2


def map_exception_to_exit_code(err: Exception) -> ExitCode:
    """Map provider and system exceptions to deterministic CLI exit codes."""
    if isinstance(
        err,
        (
            CassetteValidationError,
            CassetteMismatchError,
            ProviderSchemaError,
            ProviderPolicyError,
            ProviderSafetyBlock,
            ProviderRefusal,
        ),
    ):
        return ExitCode.SCHEMA_OR_POLICY_VIOLATION
    if isinstance(err, ProviderTimeout) and "TTFT" in str(err):
        return ExitCode.SCHEMA_OR_POLICY_VIOLATION
    return ExitCode.RUNTIME_ERROR


class ReportMetrics(BaseModel):
    """Metrics section capturing execution latency, TTFT, and token usage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ttft_ms: float | None = None
    total_latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    route_trace: tuple[dict[str, Any], ...] = ()
    iterations: int | None = None
    p50_latency_ms: float | None = None
    p90_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None


class SchemaStatus(BaseModel):
    """Schema and policy status capturing outcome validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    valid: bool
    status: str
    error_code: str | None = None
    detail: str | None = None


class ValidationReport(BaseModel):
    """Standardized 4-section report emitted by all kanban-agent validate-* commands."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[
        "kb-cli-validation-report/v1",
        "kb-sparkle-report/v1",
        "kb-validate-transition-report/v1",
    ] = "kb-cli-validation-report/v1"
    command: str
    rendered_context: str
    tool_trace: tuple[ToolCallStep, ...] = ()
    metrics: ReportMetrics
    schema_status: SchemaStatus
    qa_verdict: object = None
    sparkle_details: dict[str, Any] | None = None
    transition_details: dict[str, Any] | None = None


def _render_tool_trace(
    tool_trace: Sequence[ToolCallStep],
    *,
    verbose_tools: bool,
) -> list[str]:
    lines = ["=== 2. TOOL TRACE ==="]
    if not tool_trace:
        lines.append("Calls: 0; Tools: (none)")
    elif not verbose_tools:
        tools_list = ", ".join(step.tool for step in tool_trace)
        lines.append(f"Calls: {len(tool_trace)}; Tools: {tools_list}")
    else:
        lines.append(f"Calls: {len(tool_trace)}")
        for step in tool_trace:
            lines.append(f"  - Tool: {step.tool}")
            lines.append(f"    Args: {json.dumps(step.args)}")
            lines.append(f"    Result: {json.dumps(step.result)}")
    return lines


def _render_schema_section(
    schema_status: SchemaStatus,
    qa_verdict: object,
) -> list[str]:
    valid_str = str(schema_status.valid).lower()
    lines = [
        "=== 4. SCHEMA & POLICY STATUS ===",
        f"Valid: {valid_str} (valid: {valid_str}) | Status: {schema_status.status}",
    ]
    if qa_verdict:
        grade = getattr(qa_verdict, "grade", None) or (
            qa_verdict.get("grade") if isinstance(qa_verdict, dict) else None
        )
        readiness = getattr(qa_verdict, "readiness", None) or (
            qa_verdict.get("readiness") if isinstance(qa_verdict, dict) else None
        )
        if grade and readiness:
            lines.append(f"Grade: {grade} | Readiness: {readiness}")

    if schema_status.error_code:
        lines.append(f"Error Code: {schema_status.error_code}")
    if schema_status.detail:
        lines.append(f"Detail: {schema_status.detail}")
    return lines


def render_report(
    report: ValidationReport,
    fmt: Literal["text", "json"],
    *,
    verbose_tools: bool = False,
) -> str:
    """Render a validation report to standard text or JSON format."""
    if fmt == "json":
        return report.model_dump_json(indent=2)

    lines: list[str] = [
        "=== 1. RENDERED CONTEXT ===",
        report.rendered_context,
        "",
    ]
    lines.extend(_render_tool_trace(report.tool_trace, verbose_tools=verbose_tools))

    ttft_str = f"{report.metrics.ttft_ms:.1f}ms" if report.metrics.ttft_ms is not None else "N/A"
    latency_line = (
        f"TTFT: {ttft_str} | Total: {report.metrics.total_latency_ms:.1f}ms | "
        f"Tokens: {report.metrics.prompt_tokens} in, {report.metrics.completion_tokens} out"
    )
    latency_section = ["", "=== 3. LATENCY & TOKENS ===", latency_line]
    if report.metrics.p95_latency_ms is not None:
        latency_section.extend(
            [
                f"Iterations: {report.metrics.iterations or 1}",
                (
                    f"Percentiles: p50={report.metrics.p50_latency_ms:.2f}ms | "
                    f"p90={(report.metrics.p90_latency_ms or 0.0):.2f}ms | "
                    f"p95={report.metrics.p95_latency_ms:.2f}ms | "
                    f"p99={(report.metrics.p99_latency_ms or 0.0):.2f}ms"
                ),
            ]
        )
    latency_section.append("")
    lines.extend(latency_section)
    lines.extend(_render_schema_section(report.schema_status, report.qa_verdict))

    if report.metrics.route_trace:
        lines.extend(["", "=== 5. ROUTE TRACE ==="])
        for entry in report.metrics.route_trace:
            cid = entry.get("provider_config_id", "")
            outcome = entry.get("outcome", "")
            st = entry.get("breaker_state", "")
            ttft = entry.get("ttft_ms")
            ttft_fmt = f"{ttft:.1f}ms" if isinstance(ttft, (int, float)) else "N/A"
            lines.append(
                f"  - Provider: {cid} | Outcome: {outcome} | Breaker: {st} | TTFT: {ttft_fmt}"
            )

    return "\n".join(lines)
