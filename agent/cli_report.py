# Copyright 2026 Kanban Platform Contributors
"""Standardized 4-section report schema, exit codes, and formatters for agent CLI."""

from __future__ import annotations

import json
from collections.abc import Callable
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

    schema_version: Literal["kb-cli-validation-report/v1"] = "kb-cli-validation-report/v1"
    command: str
    rendered_context: str
    tool_trace: tuple[ToolCallStep, ...] = ()
    metrics: ReportMetrics
    schema_status: SchemaStatus


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
        "=== 2. TOOL TRACE ===",
    ]

    if not report.tool_trace:
        lines.append("Calls: 0; Tools: (none)")
    elif not verbose_tools:
        tools_list = ", ".join(step.tool for step in report.tool_trace)
        lines.append(f"Calls: {len(report.tool_trace)}; Tools: {tools_list}")
    else:
        lines.append(f"Calls: {len(report.tool_trace)}")
        for step in report.tool_trace:
            lines.append(f"  - Tool: {step.tool}")
            lines.append(f"    Args: {json.dumps(step.args)}")
            lines.append(f"    Result: {json.dumps(step.result)}")

    ttft_str = f"{report.metrics.ttft_ms:.1f}ms" if report.metrics.ttft_ms is not None else "N/A"
    lines.extend(
        [
            "",
            "=== 3. LATENCY & TOKENS ===",
            (
                f"TTFT: {ttft_str} | Total: {report.metrics.total_latency_ms:.1f}ms | "
                f"Tokens: {report.metrics.prompt_tokens} in, {report.metrics.completion_tokens} out"
            ),
            "",
            "=== 4. SCHEMA & POLICY STATUS ===",
            (
                f"Valid: {str(report.schema_status.valid).lower()} (valid: "
                f"{str(report.schema_status.valid).lower()}) | "
                f"Status: {report.schema_status.status}"
            ),
        ]
    )

    if report.schema_status.error_code:
        lines.append(f"Error Code: {report.schema_status.error_code}")
    if report.schema_status.detail:
        lines.append(f"Detail: {report.schema_status.detail}")

    return "\n".join(lines)
