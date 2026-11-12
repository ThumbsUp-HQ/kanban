# Copyright 2026 Kanban Platform Contributors
"""Unit tests for kanban-agent CLI skeleton, 4-section report, and validate-echo."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent.cli import (
    SubcommandSpec,
    add_common_agent_flags,
    get_registered_subcommands,
    main,
    register_subcommand,
)
from agent.cli_commands.validate_echo import (
    configure_validate_echo_parser,
    handle_validate_echo,
)
from agent.cli_report import (
    ExitCode,
    ReportMetrics,
    SchemaStatus,
    ValidationReport,
    default_context_scrubber,
    map_exception_to_exit_code,
    render_report,
)
from agent.providers.errors import (
    ProviderPolicyError,
    ProviderRefusal,
    ProviderSafetyBlock,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
)
from agent.testing.fixtures import (
    CassetteMismatchError,
    CassetteValidationError,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures" / "ai"


def test_case_1_positive_text_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 1: Positive text report with all 4 headings and valid status."""
    cassette_file = str(FIXTURES_DIR / "echo_stream_ok.yaml")
    exit_code = main(
        [
            "validate-echo",
            "--provider",
            "fixture",
            "--cassette",
            cassette_file,
            "--prompt",
            "Hello Sparkle",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    stdout = captured.out

    assert "=== 1. RENDERED CONTEXT ===" in stdout
    assert "Hello Sparkle" in stdout
    assert "=== 2. TOOL TRACE ===" in stdout
    assert "=== 3. LATENCY & TOKENS ===" in stdout
    assert "TTFT: 5.0ms" in stdout
    assert "Tokens: 10 in, 5 out" in stdout
    assert "=== 4. SCHEMA & POLICY STATUS ===" in stdout
    assert "valid: true" in stdout
    assert "Status: ok" in stdout


def test_case_2_positive_json_and_verbose_tools(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 2: Positive JSON report and verbose-tools flag against tool_script cassette."""
    cassette_file = str(FIXTURES_DIR / "transition_rls_veto.yaml")

    # Structured mode with JSON report and verbose tools
    exit_code = main(
        [
            "validate-echo",
            "--mode",
            "structured",
            "--report",
            "json",
            "--verbose-tools",
            "--cassette",
            cassette_file,
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    report = ValidationReport.model_validate(data)
    assert report.schema_version == "kb-cli-validation-report/v1"
    assert report.command == "validate-echo"
    assert len(report.tool_trace) == 2
    assert report.tool_trace[0].tool == "read_ticket"
    assert report.tool_trace[0].args == {"identifier": "KAN-100"}
    assert report.tool_trace[1].tool == "repo_grep"
    assert report.tool_trace[1].args == {
        "pattern": "FORCE ROW LEVEL SECURITY",
        "path": "database/",
    }
    assert report.schema_status.valid is True
    assert report.schema_status.status == "ok"

    # Text mode without --verbose-tools omits raw tool result bodies
    exit_code_text = main(
        [
            "validate-echo",
            "--mode",
            "structured",
            "--report",
            "text",
            "--cassette",
            cassette_file,
        ]
    )
    assert exit_code_text == 0
    captured_text = capsys.readouterr()
    assert "Calls: 2; Tools: read_ticket, repo_grep" in captured_text.out
    assert "Args:" not in captured_text.out
    assert "Result:" not in captured_text.out

    # Text mode with --verbose-tools includes raw tool result bodies
    exit_code_verbose = main(
        [
            "validate-echo",
            "--mode",
            "structured",
            "--report",
            "text",
            "--verbose-tools",
            "--cassette",
            cassette_file,
        ]
    )
    assert exit_code_verbose == 0
    captured_verbose = capsys.readouterr()
    assert "Calls: 2" in captured_verbose.out
    assert "Tool: read_ticket" in captured_verbose.out
    assert "Tool: repo_grep" in captured_verbose.out
    assert "Args: " in captured_verbose.out


def test_case_3_policy_and_schema_violations(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Test Case 3: Policy, schema, safety, and TTFT SLA violations exit code 2."""
    cassette_veto = str(FIXTURES_DIR / "transition_rls_veto.yaml")

    # TTFT SLA breach (simulated 18ms > deadline 5ms)
    exit_code = main(
        [
            "validate-echo",
            "--ttft-deadline-ms",
            "5",
            "--cassette",
            cassette_veto,
        ]
    )
    assert exit_code == ExitCode.SCHEMA_OR_POLICY_VIOLATION.value
    captured = capsys.readouterr()
    assert "Error Code: TIMEOUT" in captured.out
    assert "TTFT SLA breached" in captured.out

    # Unknown CLI flag --bogus exits with code 2 and writes error to stderr
    with pytest.raises(SystemExit) as exc_info:
        main(["validate-echo", "--bogus"])
    assert exc_info.value.code == ExitCode.SCHEMA_OR_POLICY_VIOLATION.value
    captured_err = capsys.readouterr()
    assert "error: unrecognized arguments: --bogus" in captured_err.err

    # Safety block fault cassette
    safety_cassette = tmp_path / "safety_block.yaml"
    safety_cassette.write_text(
        """
cassette_version: 1
matcher: {}
simulated_ttft_ms: 1.0
fault:
  kind: safety_block
""",
        encoding="utf-8",
    )
    exit_safety = main(["validate-echo", "--cassette", str(safety_cassette)])
    assert exit_safety == ExitCode.SCHEMA_OR_POLICY_VIOLATION.value
    out_safety = capsys.readouterr().out
    assert "Error Code: SAFETY_BLOCK" in out_safety

    # Refusal fault cassette
    refusal_cassette = tmp_path / "refusal.yaml"
    refusal_cassette.write_text(
        """
cassette_version: 1
matcher: {}
simulated_ttft_ms: 1.0
fault:
  kind: refusal
""",
        encoding="utf-8",
    )
    exit_refusal = main(["validate-echo", "--cassette", str(refusal_cassette)])
    assert exit_refusal == ExitCode.SCHEMA_OR_POLICY_VIOLATION.value
    out_refusal = capsys.readouterr().out
    assert "Error Code: REFUSAL" in out_refusal

    # Cassette mismatch error
    mismatch_cassette = tmp_path / "mismatch.yaml"
    mismatch_cassette.write_text(
        """
cassette_version: 1
matcher:
  model: specific-unmatched-model
simulated_ttft_ms: 1.0
stream_chunks: ["ok"]
""",
        encoding="utf-8",
    )
    exit_mismatch = main(
        [
            "validate-echo",
            "--cassette",
            str(mismatch_cassette),
            "--model",
            "different-model",
            "--prompt",
            "Custom prompt",
        ]
    )
    assert exit_mismatch == ExitCode.SCHEMA_OR_POLICY_VIOLATION.value
    out_mismatch = capsys.readouterr().out
    assert "Error Code: CASSETTE_MISMATCH_ERROR" in out_mismatch


def test_case_4_runtime_errors(capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 4: Runtime errors (HTTP 429, missing cassette) exit code 1 without tracebacks."""
    cassette_429 = str(FIXTURES_DIR / "fault_429.yaml")

    exit_code_429 = main(["validate-echo", "--cassette", cassette_429])
    assert exit_code_429 == ExitCode.RUNTIME_ERROR.value
    captured_429 = capsys.readouterr()
    assert captured_429.err == ""  # Zero raw traceback on stderr
    assert "Error Code: HTTP_ERROR" in captured_429.out
    assert "Simulated rate limit exceeded" in captured_429.out

    # Nonexistent cassette path
    exit_code_missing = main(["validate-echo", "--cassette", "/nonexistent.yaml"])
    assert exit_code_missing == ExitCode.RUNTIME_ERROR.value
    captured_missing = capsys.readouterr()
    assert captured_missing.err == ""  # Zero raw traceback on stderr
    assert "Error Code: FILE_NOT_FOUND" in captured_missing.out
    assert "Cassette file not found" in captured_missing.out


def test_case_5_extensibility_and_boundaries(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 5: Extensibility, duplicate registration, ContextScrubber hook, subprocess."""
    # Duplicate subcommand registration raises ValueError
    dup_spec = SubcommandSpec(
        name="validate-echo",
        help="Duplicate validate echo specification",
        configure_parser=configure_validate_echo_parser,
        handler=handle_validate_echo,
    )
    with pytest.raises(ValueError, match="already registered"):
        register_subcommand(dup_spec)

    # get_registered_subcommands returns dictionary containing validate-echo
    specs = get_registered_subcommands()
    assert "validate-echo" in specs
    assert specs["validate-echo"].name == "validate-echo"

    # Custom ContextScrubber replaces sensitive tokens before rendering
    def custom_scrubber(text: str) -> str:
        return text.replace("SECRET-123", "[REDACTED]")

    exit_code_scrub = main(
        [
            "validate-echo",
            "--prompt",
            "Check SECRET-123 credentials",
        ],
        scrubber=custom_scrubber,
    )
    assert exit_code_scrub == 0
    captured_scrub = capsys.readouterr()
    assert "Check [REDACTED] credentials" in captured_scrub.out
    assert "SECRET-123" not in captured_scrub.out

    # Subprocess smoke test: kanban-agent --help exits 0
    res = subprocess.run(
        [sys.executable, "-m", "agent.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "usage: kanban-agent" in res.stdout
    assert "validate-echo" in res.stdout


def test_cli_report_formatting_and_mapping() -> None:
    """Test edge cases in cli_report.py formatters and exception mapping."""
    # default_context_scrubber identity
    assert default_context_scrubber("sample text") == "sample text"

    # map_exception_to_exit_code checks
    policy_code = ExitCode.SCHEMA_OR_POLICY_VIOLATION
    assert map_exception_to_exit_code(CassetteValidationError("val")) == policy_code
    assert map_exception_to_exit_code(CassetteMismatchError("mis")) == policy_code
    assert map_exception_to_exit_code(ProviderSchemaError("sch")) == policy_code
    assert map_exception_to_exit_code(ProviderPolicyError("pol")) == policy_code
    assert map_exception_to_exit_code(ProviderSafetyBlock("saf")) == policy_code
    assert map_exception_to_exit_code(ProviderRefusal("ref")) == policy_code
    assert map_exception_to_exit_code(ProviderTimeout("TTFT breach")) == policy_code
    assert map_exception_to_exit_code(ProviderTimeout("Network timeout")) == ExitCode.RUNTIME_ERROR
    assert map_exception_to_exit_code(ProviderUnavailable("Down")) == ExitCode.RUNTIME_ERROR
    assert map_exception_to_exit_code(RuntimeError("Unexpected crash")) == ExitCode.RUNTIME_ERROR

    # render_report edge cases
    report_no_tools = ValidationReport(
        command="test-cmd",
        rendered_context="context string",
        tool_trace=(),
        metrics=ReportMetrics(
            ttft_ms=None,
            total_latency_ms=12.34,
            prompt_tokens=5,
            completion_tokens=10,
        ),
        schema_status=SchemaStatus(
            valid=False,
            status="failed",
            error_code="TEST_ERR",
            detail="Error detail information",
        ),
    )
    text_out = render_report(report_no_tools, "text", verbose_tools=False)
    assert "=== 1. RENDERED CONTEXT ===" in text_out
    assert "Calls: 0; Tools: (none)" in text_out
    assert "TTFT: N/A" in text_out
    assert "Error Code: TEST_ERR" in text_out
    assert "Detail: Error detail information" in text_out

    json_out = render_report(report_no_tools, "json")
    parsed_json = json.loads(json_out)
    assert parsed_json["command"] == "test-cmd"
    assert parsed_json["schema_status"]["error_code"] == "TEST_ERR"


def test_cli_handler_unexpected_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test handler throwing uncaught exception returns ExitCode.RUNTIME_ERROR."""

    async def _failing_handler(_args: argparse.Namespace) -> tuple[ValidationReport, ExitCode]:
        msg = "Uncaught handler crash"
        raise RuntimeError(msg)

    crash_spec = SubcommandSpec(
        name="test-crash",
        help="Subcommand that crashes",
        configure_parser=lambda _: None,
        handler=_failing_handler,
    )
    register_subcommand(crash_spec)

    exit_code = main(["test-crash"])
    assert exit_code == ExitCode.RUNTIME_ERROR.value
    captured = capsys.readouterr()
    assert "error: Uncaught handler crash" in captured.err


def test_validate_echo_non_fixture_provider_error() -> None:
    """Test unsupported provider configuration triggers runtime error report."""
    ns = argparse.Namespace(
        prompt="Test prompt",
        provider="unsupported_cloud",
        model="unsupported-model",
        cassette=None,
        mode="stream",
        ttft_deadline_ms=None,
    )
    report, code = asyncio.run(handle_validate_echo(ns))
    assert code == ExitCode.RUNTIME_ERROR
    assert report.schema_status.valid is False
    assert report.schema_status.error_code == "ValueError"
    assert "Non-fixture providers are not implemented" in (report.schema_status.detail or "")


def test_validate_echo_cassette_matcher_adaptation(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Test cassette matcher adaptation for model and provider attributes."""
    cas_path = tmp_path / "matcher_adapt.yaml"
    cas_path.write_text(
        """
cassette_version: 1
matcher:
  model: custom-model-v2
  provider: ollama
stream_chunks: ["adapted"]
""",
        encoding="utf-8",
    )
    exit_code = main(["validate-echo", "--cassette", str(cas_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "valid: true" in captured.out


def test_validate_echo_structured_fault_handling(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Test structured mode error handling on cassette fault."""
    cas_path = tmp_path / "structured_fault.yaml"
    cas_path.write_text(
        """
cassette_version: 1
matcher: {}
simulated_ttft_ms: 5.0
fault:
  kind: http_503
""",
        encoding="utf-8",
    )
    exit_code = main(
        [
            "validate-echo",
            "--mode",
            "structured",
            "--cassette",
            str(cas_path),
        ]
    )
    assert exit_code == ExitCode.RUNTIME_ERROR.value
    captured = capsys.readouterr()
    assert "Error Code: HTTP_ERROR" in captured.out
    assert "Simulated service unavailable" in captured.out


def test_cli_handler_without_scrubber_kwarg(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test handler that does not accept scrubber kwarg falls back gracefully."""

    async def _legacy_handler(_args: argparse.Namespace) -> tuple[ValidationReport, ExitCode]:
        report = ValidationReport(
            command="legacy-cmd",
            rendered_context="raw",
            metrics=ReportMetrics(total_latency_ms=1.0),
            schema_status=SchemaStatus(valid=True, status="ok"),
        )
        return report, ExitCode.OK

    legacy_spec = SubcommandSpec(
        name="test-legacy",
        help="Subcommand without scrubber kwarg",
        configure_parser=add_common_agent_flags,
        handler=_legacy_handler,
    )
    register_subcommand(legacy_spec)

    exit_code = main(["test-legacy"], scrubber=lambda t: t.upper())
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "=== 1. RENDERED CONTEXT ===" in captured.out
