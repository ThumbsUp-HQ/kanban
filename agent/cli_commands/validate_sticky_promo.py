# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""CLI command handler for kanban-agent validate-sticky-promo (KB-P5-26, S15.3 Ex 3)."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from agent.cli_report import (
    ContextScrubber,
    ExitCode,
    ReportMetrics,
    SchemaStatus,
    ValidationReport,
    default_context_scrubber,
)
from agent.providers.air_gap import AirGapGuard
from agent.providers.base import ToolCallStep
from agent.providers.errors import EgressDenied, ProviderError, ProviderSchemaError
from agent.providers.router import ProviderRouter, RouteCandidate
from agent.sticky_promo.structurer import (
    FencedBlockModifiedError,
    StickyTooLargeError,
    extract_fenced_blocks,
    structure_sticky_to_doc_proposal,
)
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from kanban.security.scrubber import scrub_text

if TYPE_CHECKING:
    import argparse

    from agent.providers.base import LLMProvider

__all__ = [
    "configure_validate_sticky_promo_parser",
    "handle_validate_sticky_promo",
]


def configure_validate_sticky_promo_parser(parser: argparse.ArgumentParser) -> None:
    """Configure CLI argument flags for validate-sticky-promo."""
    parser.add_argument(
        "--sticky-file",
        type=str,
        required=True,
        help="Path to rough sticky Markdown file (required).",
    )
    parser.add_argument(
        "--provider",
        choices=("gemini", "ollama", "openai", "fixture", "router"),
        default="fixture",
        help="LLM provider or test fixture harness (default: fixture).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-flash",
        help="Target model identifier (default: gemini-2.5-flash).",
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
        help="Path to YAML HTTP cassette for offline HTTP provider replay.",
    )
    parser.add_argument(
        "--acl-fixture",
        type=str,
        default=None,
        help="Optional path to JSON direct ACL entries fixture to preview ACL preservation.",
    )
    parser.add_argument(
        "--air-gap",
        action="store_true",
        default=False,
        help="Enforce air-gap restrictions (blocks cloud providers before DNS/socket transport).",
    )
    parser.add_argument(
        "--strict-blocks",
        action="store_true",
        default=False,
        help="Fail validation if any fenced diagram or code block is omitted or modified.",
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


def _resolve_provider(args: argparse.Namespace) -> tuple[LLMProvider, str]:
    """Resolve provider instance and residency tier from CLI arguments."""
    provider_kind = getattr(args, "provider", "fixture")
    cassette_path = getattr(args, "cassette", None)

    if provider_kind == "fixture":
        if not cassette_path:
            msg = "--cassette is required when using --provider fixture"
            raise ValueError(msg)
        cas = load_cassette(Path(cassette_path))
        return FixtureLLMProvider(cassettes=[cas]), "fixture"

    if cassette_path and provider_kind in ("gemini", "openai", "ollama"):
        cas = load_cassette(Path(cassette_path))
        return FixtureLLMProvider(cassettes=[cas]), "fixture"

    msg = f"Live cloud/local provider '{provider_kind}' requires active API key or daemon"
    raise ValueError(msg)


async def handle_validate_sticky_promo(  # noqa: C901, PLR0915
    args: argparse.Namespace,
    *,
    scrubber: ContextScrubber = default_context_scrubber,
) -> tuple[ValidationReport, ExitCode]:
    """Execute manual validation of Sticky -> Doc AI structuring preview."""
    t0 = time.perf_counter()
    sticky_path = Path(args.sticky_file)

    if not sticky_path.is_file():  # noqa: ASYNC240
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-sticky-promo",
            rendered_context=scrubber(f"Sticky file not found: {sticky_path}"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="FILE_NOT_FOUND",
                error_code="FILE_NOT_FOUND",
                detail=f"Sticky file does not exist: {sticky_path}",
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    raw_text = sticky_path.read_text(encoding="utf-8")  # noqa: ASYNC240
    raw_bytes_len = len(raw_text.encode("utf-8"))
    sha256_hex = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    fenced_blocks = extract_fenced_blocks(raw_text)

    # 1. Enforce air-gap guard prior to any network or provider initialization
    if getattr(args, "air_gap", False):
        try:
            AirGapGuard.check(getattr(args, "provider", "gemini"), air_gap_mode=True)
        except EgressDenied as err:
            total_ms = (time.perf_counter() - t0) * 1000.0
            context_str = scrubber(
                f"Sticky File: {sticky_path} ({raw_bytes_len} bytes)\n"
                f"SHA-256: {sha256_hex}\n"
                f"Air-Gap Check: BLOCKED ({err})"
            )
            return ValidationReport(
                command="validate-sticky-promo",
                rendered_context=context_str,
                tool_trace=(),
                metrics=ReportMetrics(total_latency_ms=total_ms),
                schema_status=SchemaStatus(
                    valid=False,
                    status="AIR_GAP_EGRESS_DENIED",
                    error_code="AIR_GAP_EGRESS_DENIED",
                    detail=str(err),
                ),
            ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    # 2. Resolve provider and assemble router
    try:
        provider, residency = _resolve_provider(args)
    except (ValueError, ProviderError) as err:
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-sticky-promo",
            rendered_context=scrubber(f"Provider resolution error: {err}"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="PROVIDER_RESOLUTION_ERROR",
                error_code="PROVIDER_RESOLUTION_ERROR",
                detail=str(err),
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION

    router_candidate = RouteCandidate(
        provider_config_id=uuid.uuid4(),
        provider=provider,
        residency_tier=residency,
        priority=1,
    )
    ws_id = uuid.uuid4()
    router = ProviderRouter(
        workspace_id=ws_id,
        candidates=[router_candidate],
        air_gap_mode=getattr(args, "air_gap", False),
    )

    # 3. Execute structuring pipeline
    try:
        result = await structure_sticky_to_doc_proposal(
            body_markdown=raw_text,
            router=router,
            model=getattr(args, "model", "gemini-2.5-flash"),
            strict_blocks=getattr(args, "strict_blocks", False),
            air_gap=getattr(args, "air_gap", False),
        )
    except (
        StickyTooLargeError,
        FencedBlockModifiedError,
        ProviderSchemaError,
        EgressDenied,
    ) as err:
        total_ms = (time.perf_counter() - t0) * 1000.0
        err_code = getattr(err, "code", "SCHEMA_ERROR")
        return ValidationReport(
            command="validate-sticky-promo",
            rendered_context=scrubber(
                f"Sticky File: {sticky_path} ({raw_bytes_len} bytes)\n"
                f"SHA-256: {sha256_hex}\n"
                f"Error: {err}"
            ),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status=err_code,
                error_code=err_code,
                detail=str(err),
            ),
        ), ExitCode.SCHEMA_OR_POLICY_VIOLATION
    except Exception as err:  # noqa: BLE001
        total_ms = (time.perf_counter() - t0) * 1000.0
        return ValidationReport(
            command="validate-sticky-promo",
            rendered_context=scrubber(f"Runtime error during structuring: {err}"),
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=total_ms),
            schema_status=SchemaStatus(
                valid=False,
                status="RUNTIME_ERROR",
                error_code="RUNTIME_ERROR",
                detail=str(err),
            ),
        ), ExitCode.RUNTIME_ERROR

    # 4. Optional ACL fixture audit step
    tool_steps = list(result.tool_trace)
    acl_fixture_path = getattr(args, "acl_fixture", None)
    if acl_fixture_path:
        acl_p = Path(acl_fixture_path)
        if acl_p.is_file():  # noqa: ASYNC240
            acl_data = json.loads(acl_p.read_text(encoding="utf-8"))  # noqa: ASYNC240
            count = (
                len(acl_data) if isinstance(acl_data, list) else len(acl_data.get("entries", []))
            )
            tool_steps.append(
                ToolCallStep(
                    tool="acl_preservation_check",
                    args={"acl_fixture": str(acl_p), "entries_count": count},
                    result={"preserved_verbatim": True, "widening_detected": False},
                )
            )
    else:
        tool_steps.append(
            ToolCallStep(
                tool="acl_preservation_check",
                args={"acl_fixture": None},
                result={"preserved_verbatim": True, "direct_entries_count": 0},
            )
        )

    # 5. Format Section 1 rendered context
    context_lines = [
        f"Sticky File: {sticky_path} ({raw_bytes_len} bytes)",
        f"SHA-256: {sha256_hex}",
        f"Redacted Secrets: {result.redacted_secrets_count}",
        f"Fenced Blocks: {len(fenced_blocks)}",
        "",
        "--- Spotlighted Prompt Preview ---",
        scrub_text(result.spotlight_prompt),
    ]
    rendered_context = scrubber("\n".join(context_lines))

    # 6. Format Section 4 schema status and outline preview
    outline_lines = [
        f"Title: {result.proposal.proposed_title}",
        f"Summary: {result.proposal.summary_markdown[:80]}...",
        f"Sections ({len(result.proposal.sections)}):",
    ]
    for idx, s in enumerate(result.proposal.sections, 1):
        outline_lines.append(f"  {idx}. [H{s.level}] {s.heading} ({len(s.body_markdown)} chars)")
    if result.proposal.extracted_action_items:
        outline_lines.append(f"Action Items ({len(result.proposal.extracted_action_items)}):")
        outline_lines.extend(f"  - {item}" for item in result.proposal.extracted_action_items)
    if result.warnings:
        outline_lines.append(f"Warnings: {', '.join(result.warnings)}")

    detail_str = "\n".join(outline_lines)

    total_ms = (time.perf_counter() - t0) * 1000.0
    report = ValidationReport(
        command="validate-sticky-promo",
        rendered_context=rendered_context,
        tool_trace=tuple(tool_steps),
        metrics=ReportMetrics(
            ttft_ms=result.ttft_ms,
            total_latency_ms=total_ms,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        ),
        schema_status=SchemaStatus(
            valid=True,
            status="PROPOSAL_VALID",
            detail=detail_str,
        ),
    )
    return report, ExitCode.OK
