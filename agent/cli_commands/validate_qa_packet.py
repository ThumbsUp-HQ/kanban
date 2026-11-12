# Copyright 2026 Kanban Platform Contributors
"""CLI command handler for kanban-agent validate-qa-packet."""

from __future__ import annotations

import ipaddress
import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import HttpUrl, SecretStr

from agent.cli_report import (
    ContextScrubber,
    ExitCode,
    ReportMetrics,
    SchemaStatus,
    ValidationReport,
    default_context_scrubber,
    map_exception_to_exit_code,
)
from agent.providers.air_gap import AirGapGuard
from agent.providers.errors import EgressDenied
from agent.providers.gemini import GeminiSettings
from agent.providers.ollama import OllamaSettings
from agent.providers.openai_provider import OpenAISettings
from agent.providers.registry import build_provider
from agent.providers.router import ProviderRouter, RouteCandidate
from agent.qa_validator.auditor import run_qa_packet_audit
from agent.qa_validator.bundle_inspector import (
    ProofBundle,
    ProofInspectionError,
    inspect_proof_directory,
)
from agent.qa_validator.schemas import (
    DodItemAudit,
    QaPacketVerdict,
)
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from agent.testing.http_cassette import CassetteTransport
from kanban.security.scrubber import scrub_text

if TYPE_CHECKING:
    import argparse

    from agent.providers.base import LLMProvider

__all__ = [
    "configure_validate_qa_packet_parser",
    "handle_validate_qa_packet",
]

_DEFAULT_CIDRS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
)


def configure_validate_qa_packet_parser(parser: argparse.ArgumentParser) -> None:
    """Configure CLI argument parser for validate-qa-packet subcommand."""
    parser.add_argument(
        "--ticket-file",
        type=str,
        required=True,
        help="Path to ticket YAML file or Markdown ticket with frontmatter.",
    )
    parser.add_argument(
        "--proof-dir",
        type=str,
        required=True,
        help="Path to proof directory containing audit artifacts (e.g. ./docs/qa/<ID>/).",
    )
    parser.add_argument(
        "--provider",
        choices=("fixture", "ollama", "gemini", "openai", "router"),
        default="gemini",
        help="LLM provider for forensic audit.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-flash",
        help="Target model identifier (default: gemini-2.5-flash).",
    )
    parser.add_argument(
        "--route",
        type=str,
        default="fixture,fixture",
        help="Comma-separated candidate kinds for router (e.g. 'fixture,fixture').",
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
        help="Path to HTTP cassette for offline HTTP provider replay.",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Base URL for remote or local LLM daemon.",
    )
    parser.add_argument(
        "--deterministic-only",
        action="store_true",
        default=False,
        help="Run deterministic proof checks only without invoking an LLM provider.",
    )
    parser.add_argument(
        "--air-gap",
        action="store_true",
        default=False,
        help="Enforce air-gap restrictions (blocks cloud providers before DNS/socket transport).",
    )
    parser.add_argument(
        "--verbose-tools",
        action="store_true",
        help="Print verbose JSON arguments and results for all executed tool steps.",
    )
    parser.add_argument(
        "--report",
        choices=("text", "json"),
        default="text",
        help="Output report serialization format.",
    )


def _build_router_provider(args: argparse.Namespace, cassette_path: str | None) -> LLMProvider:
    """Build ProviderRouter instance from CLI route specifications."""
    route_str = getattr(args, "route", "fixture,fixture")
    kinds = [k.strip() for k in route_str.split(",") if k.strip()]
    candidates: list[RouteCandidate] = []
    for idx, k in enumerate(kinds, start=1):
        p: LLMProvider
        if k == "fixture":
            cas = load_cassette(Path(cassette_path)) if cassette_path else None
            p = FixtureLLMProvider(cassettes=[cas] if cas else [])
            tier = "fixture"
        else:
            p = build_provider(
                k,
                OllamaSettings(
                    base_url=HttpUrl("http://127.0.0.1:11434"),
                    allowed_ollama_cidrs=_DEFAULT_CIDRS,
                    model_allowlist=("qwen2.5-coder:7b",),
                ),
            )
            tier = "local"
        candidates.append(
            RouteCandidate(
                provider_config_id=uuid.uuid4(),
                provider=p,
                priority=idx,
                residency_tier=tier,
            )
        )
    return ProviderRouter(
        workspace_id=uuid.uuid4(),
        candidates=candidates,
        air_gap_mode=getattr(args, "air_gap", False),
    )


def _build_gemini_provider(args: argparse.Namespace) -> LLMProvider:
    """Build GeminiProvider configured from CLI arguments."""
    transport = None
    http_cas = getattr(args, "http_cassette", None)
    if http_cas:
        transport = CassetteTransport(Path(http_cas))
    api_key = os.environ.get("GEMINI_API_KEY", "dummy-gemini-key-00000000000000000000")
    settings = GeminiSettings(
        mode="ai_studio_paid",
        api_key=SecretStr(api_key),
        model_allowlist=(args.model, "gemini-2.5-flash", "gemini-2.5-pro"),
    )
    return build_provider("gemini", settings, transport=transport)


def _build_openai_provider(args: argparse.Namespace) -> LLMProvider:
    """Build OpenAIProvider configured from CLI arguments."""
    transport = None
    http_cas = getattr(args, "http_cassette", None)
    if http_cas:
        transport = CassetteTransport(Path(http_cas))
    api_key = os.environ.get("OPENAI_API_KEY", "test-mock-openai-key")
    base_url_str = getattr(args, "base_url", None)
    base_url = HttpUrl(base_url_str) if base_url_str else None
    settings_oai = OpenAISettings(
        api_key=SecretStr(api_key),
        base_url=base_url,
        model_allowlist=(args.model, "gpt-4o-mini", "gpt-4.1"),
    )
    return build_provider("openai", settings_oai, transport=transport)


def _build_ollama_provider(args: argparse.Namespace) -> LLMProvider:
    """Build OllamaProvider configured from CLI arguments."""
    base_url_str = getattr(args, "base_url", "http://127.0.0.1:11434")
    base_url = HttpUrl(base_url_str)
    settings_ollama = OllamaSettings(
        base_url=base_url,
        allowed_ollama_cidrs=_DEFAULT_CIDRS,
        model_allowlist=(args.model, "qwen2.5-coder:7b"),
    )
    return build_provider("ollama", settings_ollama)


def _resolve_qa_provider(args: argparse.Namespace) -> LLMProvider:
    """Resolve and configure LLM provider or offline fixture for QA packet audit."""
    if getattr(args, "air_gap", False):
        AirGapGuard.check(getattr(args, "provider", "gemini"), air_gap_mode=True)

    cassette_path = getattr(args, "cassette", None)
    provider_kind = getattr(args, "provider", "fixture")

    if provider_kind == "fixture":
        if not cassette_path:
            msg = "--cassette is required when using --provider fixture"
            raise ValueError(msg)
        c = load_cassette(Path(cassette_path))
        return FixtureLLMProvider(cassettes=[c])

    if cassette_path and provider_kind == "gemini":
        c = load_cassette(Path(cassette_path))
        return FixtureLLMProvider(cassettes=[c])

    if provider_kind == "router":
        return _build_router_provider(args, cassette_path)
    if provider_kind == "gemini":
        return _build_gemini_provider(args)
    if provider_kind == "openai":
        return _build_openai_provider(args)
    if provider_kind == "ollama":
        return _build_ollama_provider(args)

    msg = f"Unsupported provider: {provider_kind}"
    raise ValueError(msg)


def _format_manifest(bundle: ProofBundle, scrubber: ContextScrubber) -> str:
    """Format Section 1 rendered context manifest."""
    passed_checks = sum(1 for c in bundle.deterministic_checks if c.passed)
    total_checks = len(bundle.deterministic_checks)
    lines = [
        f"Ticket: {bundle.ticket.id} ({scrub_text(bundle.ticket.title)})",
        f"Proof Directory: {bundle.proof_dir}",
        f"Files Inspected: {len(bundle.files)}",
        f"Deterministic Checks: {passed_checks}/{total_checks} passed",
    ]
    for c in bundle.deterministic_checks:
        status_mark = "PASS" if c.passed else "FAIL"
        lines.append(f"  - [{status_mark}] {c.check_id}: {c.detail}")
    return scrubber("\n".join(lines))


def _handle_deterministic_only(
    bundle: ProofBundle,
    context: str,
    t0: float,
) -> tuple[ValidationReport, ExitCode]:
    """Execute deterministic checks without calling an LLM provider."""
    total_ms = (time.perf_counter() - t0) * 1000.0
    all_passed = all(c.passed for c in bundle.deterministic_checks)
    if all_passed:
        verdict = QaPacketVerdict(
            grade="A",
            readiness="READY",
            dod_verdicts=[
                DodItemAudit(
                    criterion="Deterministic proof bundle verification",
                    passed=True,
                    evidence_ref="Deterministic bundle inspector",
                )
            ],
            critical_issues=[],
            report_markdown=(
                f"# Deterministic Proof Bundle Verification: {bundle.ticket.id}\n\n"
                f"All {len(bundle.deterministic_checks)} deterministic proof checks passed."
            ),
        )
        report = ValidationReport(
            command="validate-qa-packet",
            rendered_context=context,
            tool_trace=tuple(bundle.tool_steps),
            metrics=ReportMetrics(ttft_ms=None, total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=True,
                status=f"grade={verdict.grade}, readiness={verdict.readiness}",
                detail=f"Grade: {verdict.grade} | Readiness: {verdict.readiness}",
            ),
            qa_verdict=verdict,
        )
        return report, ExitCode.OK

    failed_details = [
        f"{c.check_id}: {c.detail}" for c in bundle.deterministic_checks if not c.passed
    ]
    verdict = QaPacketVerdict(
        grade="F",
        readiness="NEEDS_WORK",
        dod_verdicts=[
            DodItemAudit(
                criterion="Deterministic proof bundle verification",
                passed=False,
                evidence_ref="Deterministic bundle inspector",
            )
        ],
        critical_issues=failed_details,
        report_markdown=(
            f"# Deterministic Proof Bundle Verification Failed: {bundle.ticket.id}\n\n"
            f"Failed checks:\n" + "\n".join(f"- {d}" for d in failed_details)
        ),
    )
    detail_msg = (
        f"Grade: {verdict.grade} | Readiness: {verdict.readiness} | "
        f"Failures: {'; '.join(failed_details)}"
    )
    report = ValidationReport(
        command="validate-qa-packet",
        rendered_context=context,
        tool_trace=tuple(bundle.tool_steps),
        metrics=ReportMetrics(ttft_ms=None, total_latency_ms=total_ms),
        schema_status=SchemaStatus(
            valid=False,
            status=f"grade={verdict.grade}, readiness={verdict.readiness}",
            error_code="DETERMINISTIC_CHECK_FAILED",
            detail=detail_msg,
        ),
        qa_verdict=verdict,
    )
    return report, ExitCode.SCHEMA_OR_POLICY_VIOLATION


async def _handle_llm_audit(
    args: argparse.Namespace,
    bundle: ProofBundle,
    context: str,
    t0: float,
) -> tuple[ValidationReport, ExitCode]:
    """Execute LLM forensic audit and enforce anti-fantasy gate."""
    try:
        provider = _resolve_qa_provider(args)
    except EgressDenied as err:
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-qa-packet",
            rendered_context=context,
            tool_trace=tuple(bundle.tool_steps),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=err.code,
                detail=str(err),
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION
    except Exception as err:  # noqa: BLE001
        total_ms = (time.perf_counter() - t0) * 1000.0
        code = map_exception_to_exit_code(err)
        return ValidationReport(
            command="validate-qa-packet",
            rendered_context=context,
            tool_trace=tuple(bundle.tool_steps),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=getattr(err, "code", type(err).__name__),
                detail=str(err),
            ),
        ), code

    try:
        verdict, ttft_ms, prompt_tokens, comp_tokens = await run_qa_packet_audit(
            bundle.ticket,
            bundle,
            provider,
            model=getattr(args, "model", "gemini-2.5-flash"),
        )
    except Exception as err:  # noqa: BLE001
        total_ms = (time.perf_counter() - t0) * 1000.0
        code = map_exception_to_exit_code(err)
        return ValidationReport(
            command="validate-qa-packet",
            rendered_context=context,
            tool_trace=tuple(bundle.tool_steps),
            metrics=ReportMetrics(ttft_ms=None, total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=getattr(err, "code", type(err).__name__),
                detail=str(err),
            ),
        ), code

    total_ms = (time.perf_counter() - t0) * 1000.0
    route_trace = tuple(getattr(provider, "last_route_trace", ()))
    all_checks_passed = all(c.passed for c in bundle.deterministic_checks)
    is_ready = (
        all_checks_passed
        and verdict.grade == "A"
        and verdict.readiness == "READY"
        and verdict.policy_override is None
    )
    exit_code = ExitCode.OK if is_ready else ExitCode.SCHEMA_OR_POLICY_VIOLATION
    override_info = (
        f" | Policy Override: {verdict.policy_override}" if verdict.policy_override else ""
    )

    schema_status = SchemaStatus(
        valid=is_ready,
        status=f"grade={verdict.grade}, readiness={verdict.readiness}",
        error_code=verdict.policy_override if not is_ready else None,
        detail=f"Grade: {verdict.grade} | Readiness: {verdict.readiness}{override_info}",
    )
    report = ValidationReport(
        command="validate-qa-packet",
        rendered_context=context,
        tool_trace=tuple(bundle.tool_steps),
        metrics=ReportMetrics(
            ttft_ms=ttft_ms,
            total_latency_ms=total_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=comp_tokens,
            route_trace=route_trace,
        ),
        schema_status=schema_status,
        qa_verdict=verdict,
    )
    return report, exit_code


async def handle_validate_qa_packet(
    args: argparse.Namespace,
    *,
    scrubber: ContextScrubber = default_context_scrubber,
) -> tuple[ValidationReport, ExitCode]:
    """Execute reality-checker forensic QA audit over proof directory and ticket file."""
    t0 = time.perf_counter()
    ticket_file = Path(args.ticket_file)
    proof_dir = Path(args.proof_dir)

    if not ticket_file.exists():  # noqa: ASYNC240
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-qa-packet",
            rendered_context=scrubber(f"Ticket file not found: {ticket_file}"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="FILE_NOT_FOUND",
                detail=f"Ticket file does not exist: {ticket_file}",
            ),
        ), ExitCode.RUNTIME_ERROR

    if not proof_dir.exists() or not proof_dir.is_dir():  # noqa: ASYNC240
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-qa-packet",
            rendered_context=scrubber(f"Proof directory not found: {proof_dir}"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="DIRECTORY_NOT_FOUND",
                detail=f"Proof directory does not exist or is not a directory: {proof_dir}",
            ),
        ), ExitCode.RUNTIME_ERROR

    try:
        bundle: ProofBundle = inspect_proof_directory(ticket_file, proof_dir)
    except ProofInspectionError as err:
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-qa-packet",
            rendered_context=scrubber(f"Proof inspection failed: {err.code} - {err.detail}"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=err.code,
                detail=err.detail,
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION
    except Exception as err:  # noqa: BLE001
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-qa-packet",
            rendered_context=scrubber(f"Unexpected inspection error: {err}"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=type(err).__name__,
                detail=str(err),
            ),
        ), ExitCode.RUNTIME_ERROR

    context = _format_manifest(bundle, scrubber)
    if getattr(args, "deterministic_only", False):
        return _handle_deterministic_only(bundle, context, t0)

    return await _handle_llm_audit(args, bundle, context, t0)
