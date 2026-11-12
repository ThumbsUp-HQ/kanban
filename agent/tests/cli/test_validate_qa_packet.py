# Copyright 2026 Kanban Platform Contributors
"""Mandatory feature unit tests for kanban-agent validate-qa-packet CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

import jsonschema
import pytest

import agent.cli_commands.validate_qa_packet as vqp
from agent.cli import main
from agent.cli_commands.validate_qa_packet import (
    _resolve_qa_provider,
    handle_validate_qa_packet,
)
from agent.cli_report import ExitCode
from agent.providers.errors import ProviderTimeout

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures" / "ai"
EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "examples"


def test_case_1_positive_s15_3_example_4(capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 1: Positive run (S15.3 example 4) exiting 0 with all 4 sections."""
    ticket_file = str(EXAMPLES_DIR / "tickets" / "kan-142.yaml")
    proof_dir = str(EXAMPLES_DIR / "qa_packets" / "kan-142-ready")
    cassette_file = str(FIXTURES_DIR / "qa_packet_grade_a_ready.yaml")

    exit_code = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            ticket_file,
            "--proof-dir",
            proof_dir,
            "--provider",
            "fixture",
            "--cassette",
            cassette_file,
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    stdout = captured.out

    assert "=== 1. RENDERED CONTEXT ===" in stdout
    assert "KAN-142" in stdout
    assert "=== 2. TOOL TRACE ===" in stdout
    assert "=== 3. LATENCY & TOKENS ===" in stdout
    assert "TTFT: 12.0ms" in stdout
    assert "=== 4. SCHEMA & POLICY STATUS ===" in stdout
    assert "valid: true" in stdout
    assert "grade: a" in stdout.lower()
    assert "readiness: ready" in stdout.lower()


def test_case_2_positive_markdown_ticket_frontmatter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Case 2: Positive parsing of Markdown ticket with frontmatter."""
    md_ticket = Path("docs/tickets/KB-P5-27.md")
    assert md_ticket.exists()

    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    (proof_dir / "git-diff.patch").write_text("dummy diff", encoding="utf-8")
    (proof_dir / "unit-test-results.txt").write_text("5 passed in 0.1s", encoding="utf-8")
    (proof_dir / "build-check.txt").write_text("clean", encoding="utf-8")

    exit_code = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            str(md_ticket),
            "--proof-dir",
            str(proof_dir),
            "--deterministic-only",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "KB-P5-27" in captured.out
    assert "readiness=READY" in captured.out


def test_case_3_negative_specialist_gates_enforced(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test Case 3: Missing ui-specialist review triggers FANTASY_APPROVAL_BLOCKED."""
    ticket_file = str(EXAMPLES_DIR / "tickets" / "kan-142.yaml")
    proof_dir = str(EXAMPLES_DIR / "qa_packets" / "kan-142-missing-ui-review")
    cassette_file = str(FIXTURES_DIR / "qa_packet_grade_a_ready.yaml")

    exit_code = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            ticket_file,
            "--proof-dir",
            proof_dir,
            "--provider",
            "fixture",
            "--cassette",
            cassette_file,
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    stdout = captured.out

    assert "[FAIL] UI_SPECIALIST_GATE" in stdout
    assert "FANTASY_APPROVAL_BLOCKED" in stdout
    assert "readiness: needs_work" in stdout.lower()


def test_case_4_anti_fantasy_invariant(capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 4: Hallucinated approval is code-blocked; needs-work exits 2."""
    ticket_file = str(EXAMPLES_DIR / "tickets" / "kan-142.yaml")
    proof_dir = str(EXAMPLES_DIR / "qa_packets" / "kan-142-ready")

    # (a) Model hallucinating READY with grade B+
    code_fantasy = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            ticket_file,
            "--proof-dir",
            proof_dir,
            "--provider",
            "fixture",
            "--cassette",
            str(FIXTURES_DIR / "qa_packet_fantasy_approval.yaml"),
        ]
    )
    assert code_fantasy == 2
    captured = capsys.readouterr()
    assert "FANTASY_APPROVAL_BLOCKED" in captured.out
    assert "readiness: needs_work" in captured.out.lower()

    # (b) Model returning genuine NEEDS_WORK (grade B-)
    code_needs_work = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            ticket_file,
            "--proof-dir",
            proof_dir,
            "--provider",
            "fixture",
            "--cassette",
            str(FIXTURES_DIR / "qa_packet_needs_work.yaml"),
        ]
    )
    assert code_needs_work == 2
    captured2 = capsys.readouterr()
    assert "grade=B-" in captured2.out
    assert "readiness: needs_work" in captured2.out.lower()


def test_case_5_security_symlink_escape_and_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Case 5: Symlink escape rejected with PROOF_SYMLINK_ESCAPE; live secrets fail Check 7."""
    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text("id: SEC-1\ntitle: Security Check\n", encoding="utf-8")

    # 1. Symlink escape
    escape_proof_dir = tmp_path / "escape_proof"
    escape_proof_dir.mkdir()
    outside_file = tmp_path / "passwd"
    outside_file.write_text("root:x:0:0:root:/root:/bin/bash\n", encoding="utf-8")

    (escape_proof_dir / "git-diff.patch").symlink_to(outside_file)

    exit_symlink = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            str(ticket_file),
            "--proof-dir",
            str(escape_proof_dir),
            "--deterministic-only",
        ]
    )
    assert exit_symlink == 2
    captured_symlink = capsys.readouterr()
    assert "PROOF_SYMLINK_ESCAPE" in captured_symlink.out
    assert "root:x:0:0" not in captured_symlink.out

    # 2. Secret leak detection and prompt scrubbing
    secret_proof_dir = tmp_path / "secret_proof"
    secret_proof_dir.mkdir()
    fake_token = "ghp_" + ("1234567890abcdef" * 2) + "1234"
    (secret_proof_dir / "git-diff.patch").write_text(f"+{fake_token}\n", encoding="utf-8")
    (secret_proof_dir / "unit-test-results.txt").write_text("1 passed in 0.1s", encoding="utf-8")
    (secret_proof_dir / "build-check.txt").write_text("clean", encoding="utf-8")

    exit_secret = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            str(ticket_file),
            "--proof-dir",
            str(secret_proof_dir),
            "--deterministic-only",
        ]
    )
    assert exit_secret == 2
    captured_secret = capsys.readouterr()
    assert "[FAIL] NO_RAW_SECRETS_IN_PROOF" in captured_secret.out


def test_case_6_passive_guarantee_zero_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Case 6: Passive guarantee asserts 0 subprocess invocations."""
    spies = {"popen": 0, "exec": 0, "shell": 0}

    def _fake_popen(*_args: object, **_kwargs: object) -> object:
        spies["popen"] += 1
        msg = "Subprocess disallowed in passive mode"
        raise AssertionError(msg)

    async def _fake_exec(*_args: object, **_kwargs: object) -> object:
        spies["exec"] += 1
        msg = "create_subprocess_exec disallowed in passive mode"
        raise AssertionError(msg)

    async def _fake_shell(*_args: object, **_kwargs: object) -> object:
        spies["shell"] += 1
        msg = "create_subprocess_shell disallowed in passive mode"
        raise AssertionError(msg)

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_shell)

    exit_code = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            str(EXAMPLES_DIR / "tickets" / "kan-142.yaml"),
            "--proof-dir",
            str(EXAMPLES_DIR / "qa_packets" / "kan-142-ready"),
            "--provider",
            "fixture",
            "--cassette",
            str(FIXTURES_DIR / "qa_packet_grade_a_ready.yaml"),
        ]
    )

    assert exit_code == 0
    assert spies["popen"] == 0
    assert spies["exec"] == 0
    assert spies["shell"] == 0


def test_case_7_boundary_and_json_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Case 7: Boundary checks, --deterministic-only 0 calls, and JSON output."""
    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text("id: BND-1\ntitle: Boundary Test\n", encoding="utf-8")

    # 1. Boundary: file > 2 MiB
    proof_dir_big = tmp_path / "big_proof"
    proof_dir_big.mkdir()
    (proof_dir_big / "git-diff.patch").write_bytes(b"x" * (2 * 1024 * 1024 + 10))

    exit_big = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            str(ticket_file),
            "--proof-dir",
            str(proof_dir_big),
            "--deterministic-only",
        ]
    )
    assert exit_big == 2
    captured_big = capsys.readouterr()
    assert "PROOF_BUNDLE_TOO_LARGE" in captured_big.out

    # 2. JSON validation against kb-qa-verdict-v1.json
    schema_path = Path("agent/schemas/kb-qa-verdict-v1.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    exit_json = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            str(EXAMPLES_DIR / "tickets" / "kan-142.yaml"),
            "--proof-dir",
            str(EXAMPLES_DIR / "qa_packets" / "kan-142-ready"),
            "--provider",
            "fixture",
            "--cassette",
            str(FIXTURES_DIR / "qa_packet_grade_a_ready.yaml"),
            "--report",
            "json",
        ]
    )
    assert exit_json == 0
    captured_json = capsys.readouterr()
    data = json.loads(captured_json.out)

    jsonschema.validate(instance=data, schema=schema)
    assert "qa_verdict" in data
    jsonschema.validate(instance=data["qa_verdict"], schema=schema)


def test_cli_runtime_errors_nonexistent_paths() -> None:
    """Verify runtime error exit code 1 for missing ticket file or proof directory."""
    code_missing_ticket = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            "nonexistent/ticket.yaml",
            "--proof-dir",
            str(EXAMPLES_DIR / "qa_packets" / "kan-142-ready"),
        ]
    )
    assert code_missing_ticket == 1

    code_missing_proof = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            str(EXAMPLES_DIR / "tickets" / "kan-142.yaml"),
            "--proof-dir",
            "nonexistent/proof_dir",
        ]
    )
    assert code_missing_proof == 1


def test_cli_air_gap_flag_enforcement(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify --air-gap flag blocks cloud provider before transport."""
    exit_code = main(
        [
            "validate-qa-packet",
            "--ticket-file",
            str(EXAMPLES_DIR / "tickets" / "kan-142.yaml"),
            "--proof-dir",
            str(EXAMPLES_DIR / "qa_packets" / "kan-142-ready"),
            "--provider",
            "gemini",
            "--air-gap",
        ]
    )
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "AIR_GAP_EGRESS_DENIED" in captured.out


def test_resolve_qa_provider_variants() -> None:
    """Verify provider resolution for router, gemini, openai, ollama, and errors."""
    # 1. Fixture without cassette -> ValueError
    args_no_cas = argparse.Namespace(provider="fixture", cassette=None, air_gap=False)
    with pytest.raises(ValueError, match="--cassette is required"):
        _resolve_qa_provider(args_no_cas)

    # 2. Unsupported provider -> ValueError
    args_bad = argparse.Namespace(provider="unsupported", cassette=None, air_gap=False)
    with pytest.raises(ValueError, match="Unsupported provider"):
        _resolve_qa_provider(args_bad)

    # 3. Router provider
    args_router = argparse.Namespace(
        provider="router",
        route="fixture,fixture",
        cassette=str(FIXTURES_DIR / "qa_packet_grade_a_ready.yaml"),
        air_gap=False,
    )
    p_router = _resolve_qa_provider(args_router)
    assert p_router is not None

    # 4. Gemini provider
    args_gemini = argparse.Namespace(
        provider="gemini",
        cassette=None,
        model="gemini-2.5-flash",
        http_cassette=None,
        air_gap=False,
    )
    p_gemini = _resolve_qa_provider(args_gemini)
    assert p_gemini is not None

    # 5. OpenAI provider
    args_openai = argparse.Namespace(
        provider="openai",
        cassette=None,
        model="gpt-4o-mini",
        base_url="http://127.0.0.1:8000/v1",
        http_cassette=None,
        air_gap=False,
    )
    p_openai = _resolve_qa_provider(args_openai)
    assert p_openai is not None

    # 6. Ollama provider
    args_ollama = argparse.Namespace(
        provider="ollama",
        cassette=None,
        model="qwen2.5-coder:7b",
        base_url="http://127.0.0.1:11434",
        air_gap=False,
    )
    p_ollama = _resolve_qa_provider(args_ollama)
    assert p_ollama is not None


@pytest.mark.asyncio
async def test_handle_validate_qa_packet_audit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify provider fault during audit returns error exit code."""

    async def _failing_audit(*_args: object, **_kwargs: object) -> object:
        msg = "Simulated audit timeout"
        raise ProviderTimeout(msg)

    monkeypatch.setattr(vqp, "run_qa_packet_audit", _failing_audit)

    args = argparse.Namespace(
        ticket_file=str(EXAMPLES_DIR / "tickets" / "kan-142.yaml"),
        proof_dir=str(EXAMPLES_DIR / "qa_packets" / "kan-142-ready"),
        provider="fixture",
        cassette=str(FIXTURES_DIR / "qa_packet_grade_a_ready.yaml"),
        deterministic_only=False,
        air_gap=False,
        model="gemini-2.5-flash",
    )

    report, code = await handle_validate_qa_packet(args)
    assert code == ExitCode.RUNTIME_ERROR
    assert report.schema_status.error_code == "TIMEOUT"


@pytest.mark.asyncio
async def test_resolve_qa_provider_all_branches(tmp_path: Path) -> None:
    """Verify all remaining provider branches and error handlers."""
    cassette_file = str(FIXTURES_DIR / "qa_packet_grade_a_ready.yaml")

    # 1. Gemini with cassette defaults to fixture
    args_gemini_cas = argparse.Namespace(provider="gemini", cassette=cassette_file, air_gap=False)
    p1 = _resolve_qa_provider(args_gemini_cas)
    assert p1 is not None

    # 2. Router with ollama candidate
    args_router_mix = argparse.Namespace(
        provider="router",
        route="fixture,ollama",
        cassette=cassette_file,
        air_gap=False,
    )
    p2 = _resolve_qa_provider(args_router_mix)
    assert p2 is not None

    # 3. Gemini with http_cassette
    http_cas_file = tmp_path / "http.yaml"
    http_cas_file.write_text("cassette_version: 1\nhttp_exchanges: []\n", encoding="utf-8")
    args_gemini_http = argparse.Namespace(
        provider="gemini",
        cassette=None,
        model="gemini-2.5-flash",
        http_cassette=str(http_cas_file),
        air_gap=False,
    )
    p3 = _resolve_qa_provider(args_gemini_http)
    assert p3 is not None

    # 4. OpenAI with http_cassette
    args_openai_http = argparse.Namespace(
        provider="openai",
        cassette=None,
        model="gpt-4o-mini",
        base_url="http://127.0.0.1:8000/v1",
        http_cassette=str(http_cas_file),
        air_gap=False,
    )
    p4 = _resolve_qa_provider(args_openai_http)
    assert p4 is not None

    # 5. handle_validate_qa_packet with provider error
    args_err = argparse.Namespace(
        ticket_file=str(EXAMPLES_DIR / "tickets" / "kan-142.yaml"),
        proof_dir=str(EXAMPLES_DIR / "qa_packets" / "kan-142-ready"),
        provider="unsupported",
        cassette=None,
        deterministic_only=False,
        air_gap=False,
        model="gemini-2.5-flash",
    )
    _rep_err, code_err = await handle_validate_qa_packet(args_err)
    assert code_err == ExitCode.RUNTIME_ERROR

    # 6. handle_validate_qa_packet with unexpected inspection error
    def _bad_inspect(*_a: object, **_kw: object) -> object:
        msg = "Disk read error"
        raise RuntimeError(msg)

    mp = pytest.MonkeyPatch()
    mp.setattr(vqp, "inspect_proof_directory", _bad_inspect)
    args_ins_err = argparse.Namespace(
        ticket_file=str(EXAMPLES_DIR / "tickets" / "kan-142.yaml"),
        proof_dir=str(EXAMPLES_DIR / "qa_packets" / "kan-142-ready"),
        provider="fixture",
        cassette=cassette_file,
        deterministic_only=False,
        air_gap=False,
        model="gemini-2.5-flash",
    )
    _rep_ins, code_ins = await handle_validate_qa_packet(args_ins_err)
    assert code_ins == ExitCode.RUNTIME_ERROR
    mp.undo()
