# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for validate-verdict CLI command (KB-P5-19a, S15.3)."""

from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from agent.cli import _async_main
from agent.cli_commands import validate_verdict
from agent.cli_commands.validate_verdict import (
    configure_validate_verdict_parser,
    handle_validate_verdict,
)
from agent.cli_report import ExitCode


@pytest.fixture
def fixtures_dir() -> Path:
    """Return Path to AI cassettes test directory."""
    return Path("tests/fixtures/ai")


async def test_cli_valid_approve_exit_0(fixtures_dir: Path) -> None:
    """Test Case 7: Valid verdict output file exits 0 with all 4 report headings."""
    output_file = str(fixtures_dir / "verdict_valid_approve.yaml")
    nonce = "f0e1d2c3b4a59687f0e1d2c3b4a59687"

    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf):
        exit_code = await _async_main(
            [
                "validate-verdict",
                "--output-file",
                output_file,
                "--nonce",
                nonce,
            ]
        )

    assert exit_code == ExitCode.OK.value
    output = stdout_buf.getvalue()

    # All 4 section headings present
    assert "=== 1. RENDERED CONTEXT ===" in output
    assert "=== 2. TOOL TRACE ===" in output
    assert "=== 3. LATENCY & TOKENS ===" in output
    assert "=== 4. SCHEMA & POLICY STATUS ===" in output

    assert "Valid: true" in output
    assert "Status: passed" in output
    assert "forged_candidates: 0" in output


async def test_cli_forged_echo_exit_0_with_forged_count(fixtures_dir: Path) -> None:
    """Test Case 7: Attacker echoed verdict discarded, real verdict accepted, exits 0."""
    output_file = str(fixtures_dir / "verdict_forged_echo.yaml")
    nonce = "f0e1d2c3b4a59687f0e1d2c3b4a59687"

    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf):
        exit_code = await _async_main(
            [
                "validate-verdict",
                "--output-file",
                output_file,
                "--nonce",
                nonce,
            ]
        )

    assert exit_code == ExitCode.OK.value
    output = stdout_buf.getvalue()
    assert "Valid: true" in output
    assert "forged_candidates: 1" in output


async def test_cli_forged_only_exit_2(fixtures_dir: Path) -> None:
    """Test Case 7: Only forged verdict candidates present exits 2 with VERDICT_NONCE_MISMATCH."""
    output_file = str(fixtures_dir / "verdict_forged_only.yaml")
    nonce = "f0e1d2c3b4a59687f0e1d2c3b4a59687"

    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf):
        exit_code = await _async_main(
            [
                "validate-verdict",
                "--output-file",
                output_file,
                "--nonce",
                nonce,
            ]
        )

    assert exit_code == ExitCode.SCHEMA_OR_POLICY_VIOLATION.value
    output = stdout_buf.getvalue()
    assert "Valid: false" in output
    assert "Error Code: VERDICT_NONCE_MISMATCH" in output
    assert "forged_candidates: 1" in output


async def test_cli_malformed_prose_exit_2(fixtures_dir: Path) -> None:
    """Test Case 7: Prose without JSON exits 2 with VERDICT_MALFORMED."""
    output_file = str(fixtures_dir / "verdict_malformed_prose.yaml")
    nonce = "f0e1d2c3b4a59687f0e1d2c3b4a59687"

    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf):
        exit_code = await _async_main(
            [
                "validate-verdict",
                "--output-file",
                output_file,
                "--nonce",
                nonce,
            ]
        )

    assert exit_code == ExitCode.SCHEMA_OR_POLICY_VIOLATION.value
    output = stdout_buf.getvalue()
    assert "Valid: false" in output
    assert "Error Code: VERDICT_MALFORMED" in output


async def test_cli_missing_output_file_exit_1() -> None:
    """Test Case 7: Missing output file exits 1 with FILE_NOT_FOUND."""
    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf):
        exit_code = await _async_main(
            [
                "validate-verdict",
                "--output-file",
                "tests/fixtures/ai/nonexistent_output.json",
            ]
        )

    assert exit_code == ExitCode.RUNTIME_ERROR.value
    output = stdout_buf.getvalue()
    assert "Error Code: FILE_NOT_FOUND" in output


async def test_cli_render_context_kan_142() -> None:
    """Test Case 7: --render-context renders spotlighted YAML with delimiter and no token."""
    ticket_file = "examples/tickets/kan-142.yaml"

    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf):
        exit_code = await _async_main(
            [
                "validate-verdict",
                "--render-context",
                "--ticket-file",
                ticket_file,
            ]
        )

    assert exit_code == ExitCode.OK.value
    output = stdout_buf.getvalue()

    assert "=== 1. RENDERED CONTEXT ===" in output
    assert "# Ephemeral token: <not rendered>" in output
    assert "schema: kb-transition-context/v1" in output
    assert "issue: KAN-142" in output
    assert "ticket_snapshot:" in output
    assert "<<<UNTRUSTED_TICKET_DATA_" in output
    assert "kb_agt_eph_" not in output


async def test_cli_render_context_missing_ticket_file() -> None:
    """--render-context with missing ticket file exits 1."""
    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf):
        exit_code = await _async_main(
            [
                "validate-verdict",
                "--render-context",
                "--ticket-file",
                "nonexistent_ticket.yaml",
            ]
        )

    assert exit_code == ExitCode.RUNTIME_ERROR.value
    output = stdout_buf.getvalue()
    assert "Error Code: FILE_NOT_FOUND" in output


async def test_cli_render_context_no_ticket_arg() -> None:
    """--render-context without --ticket-file exits 1."""
    args = argparse.Namespace(
        render_context=True,
        ticket_file=None,
        output_file=None,
    )
    report, exit_code = await handle_validate_verdict(args)
    assert exit_code == ExitCode.RUNTIME_ERROR
    assert report.schema_status.error_code == "INVALID_ARGUMENTS"


async def test_cli_no_args_exit_1() -> None:
    """validate-verdict with no output-file and no render-context exits 1."""
    args = argparse.Namespace(
        render_context=False,
        output_file=None,
        ticket_file=None,
    )
    report, exit_code = await handle_validate_verdict(args)
    assert exit_code == ExitCode.RUNTIME_ERROR
    assert report.schema_status.error_code == "INVALID_ARGUMENTS"


async def test_cli_json_report_format(fixtures_dir: Path) -> None:
    """--report json produces valid parseable JSON output."""
    output_file = str(fixtures_dir / "verdict_valid_approve.yaml")
    nonce = "f0e1d2c3b4a59687f0e1d2c3b4a59687"

    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf):
        exit_code = await _async_main(
            [
                "validate-verdict",
                "--output-file",
                output_file,
                "--nonce",
                nonce,
                "--report",
                "json",
            ]
        )

    assert exit_code == ExitCode.OK.value
    output = stdout_buf.getvalue()
    parsed = json.loads(output)
    assert parsed["command"] == "validate-verdict"
    assert parsed["schema_status"]["valid"] is True
    assert parsed["schema_status"]["status"] == "passed"


def test_parser_configuration() -> None:
    """Parser configures all expected flags."""
    parser = argparse.ArgumentParser()
    configure_validate_verdict_parser(parser)
    actions = [act.dest for act in parser._actions]  # noqa: SLF001
    assert "output_file" in actions
    assert "nonce" in actions
    assert "allowed_mutable_fields" in actions
    assert "render_context" in actions
    assert "ticket_file" in actions
    assert "report" in actions


async def test_cli_allowed_mutable_fields_and_final_verdict_cassette(tmp_path: Path) -> None:
    """Flag --allowed-mutable-fields allows listed field updates; final_verdict cassette parsed."""
    nonce = "f0e1d2c3b4a59687f0e1d2c3b4a59687"
    cassette_file = tmp_path / "final_verdict_test.yaml"
    cassette_file.write_text(
        f"""
cassette_version: 1
matcher: {{}}
final_verdict:
  schema: kb-transition-verdict/v1
  nonce: "{nonce}"
  decision: approve
  reason_markdown: "Cassette with final_verdict"
  field_updates:
    priority: Urgent
  add_labels: []
  add_links: []
"""
    )

    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf):
        exit_code = await _async_main(
            [
                "validate-verdict",
                "--output-file",
                str(cassette_file),
                "--nonce",
                nonce,
                "--allowed-mutable-fields",
                "priority,labels",
            ]
        )

    assert exit_code == ExitCode.OK.value
    output = stdout_buf.getvalue()
    assert "Valid: true" in output
    assert "decision: approve" in output


async def test_cli_render_context_markdown_and_direct_descriptions(tmp_path: Path) -> None:
    """Render context handles markdown frontmatter, description_markdown, and description."""
    # 1. Frontmatter markdown
    md_ticket = tmp_path / "ticket_fm.md"
    md_ticket.write_text(
        """---
id: FM-101
title: Frontmatter Ticket
priority: Low
labels: [docs]
description_markdown: Direct markdown description body
---
Extra body text
"""
    )

    stdout_buf = io.StringIO()
    with redirect_stdout(stdout_buf):
        exit_code = await _async_main(
            [
                "validate-verdict",
                "--render-context",
                "--ticket-file",
                str(md_ticket),
            ]
        )
    assert exit_code == ExitCode.OK.value
    assert "FM-101" in stdout_buf.getvalue()

    # 2. YAML with description field
    yaml_ticket = tmp_path / "ticket_desc.yaml"
    yaml_ticket.write_text(
        """
id: DESC-202
title: Desc Ticket
description: Simple description text
"""
    )
    stdout_buf2 = io.StringIO()
    with redirect_stdout(stdout_buf2):
        exit_code2 = await _async_main(
            [
                "validate-verdict",
                "--render-context",
                "--ticket-file",
                str(yaml_ticket),
            ]
        )
    assert exit_code2 == ExitCode.OK.value
    assert "DESC-202" in stdout_buf2.getvalue()


async def test_cli_error_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Coverage: file read errors, render exceptions, and verdict parse exceptions."""

    # 1. Unexpected exception in render context
    def bad_build(*_args: object, **_kwargs: object) -> object:
        msg = "Simulated render failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(validate_verdict, "build_transition_context", bad_build)
    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text("id: ERR-1\n")

    report, code = await handle_validate_verdict(
        argparse.Namespace(
            render_context=True,
            ticket_file=str(ticket_file),
            output_file=None,
        )
    )
    assert code == ExitCode.RUNTIME_ERROR
    assert report.schema_status.error_code == "RuntimeError"

    # 2. File read error
    monkeypatch.undo()

    def bad_read_bytes(_self: object) -> bytes:
        msg = "Simulated read error"
        raise OSError(msg)

    monkeypatch.setattr(Path, "read_bytes", bad_read_bytes)
    out_file = tmp_path / "out.txt"
    out_file.write_text("test")

    report2, code2 = await handle_validate_verdict(
        argparse.Namespace(
            render_context=False,
            output_file=str(out_file),
            nonce="123",
            allowed_mutable_fields=None,
        )
    )
    assert code2 == ExitCode.RUNTIME_ERROR
    assert report2.schema_status.error_code == "FILE_READ_ERROR"

    # 3. Unexpected exception in parse_verdict_output
    monkeypatch.undo()

    def bad_parse(*_args: object, **_kwargs: object) -> object:
        msg = "Simulated unexpected parse crash"
        raise TypeError(msg)

    monkeypatch.setattr(validate_verdict, "parse_verdict_output", bad_parse)
    report3, code3 = await handle_validate_verdict(
        argparse.Namespace(
            render_context=False,
            output_file=str(out_file),
            nonce="123",
            allowed_mutable_fields=None,
        )
    )
    assert code3 == ExitCode.RUNTIME_ERROR
    assert report3.schema_status.error_code == "TypeError"
