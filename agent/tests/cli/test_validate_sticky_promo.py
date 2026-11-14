# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: ARG001, PLC0415, TRY003, EM101, TC002
"""Tests for kanban-agent validate-sticky-promo CLI command (KB-P5-26, S15.3 Ex 3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.cli import main
from agent.cli_report import ExitCode

_FIXTURES_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "ai"
_STICKY_FILE = Path("examples/stickies/rough-auth-notes.md")


def test_validate_sticky_promo_file_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify missing sticky file returns exit code 2."""
    code = main(
        [
            "validate-sticky-promo",
            "--sticky-file",
            "/tmp/nonexistent-sticky-file.md",
        ]
    )
    assert code == ExitCode.SCHEMA_OR_POLICY_VIOLATION
    captured = capsys.readouterr()
    assert "FILE_NOT_FOUND" in captured.out


def test_validate_sticky_promo_missing_cassette_for_fixture(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify fixture provider without cassette returns exit code 2."""
    code = main(
        [
            "validate-sticky-promo",
            "--sticky-file",
            str(_STICKY_FILE),
            "--provider",
            "fixture",
        ]
    )
    assert code == ExitCode.SCHEMA_OR_POLICY_VIOLATION
    captured = capsys.readouterr()
    assert "PROVIDER_RESOLUTION_ERROR" in captured.out


def test_validate_sticky_promo_ok_text_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify valid sticky promo run exits 0 and prints all 4 S15.3 report sections."""
    cassette = _FIXTURES_DIR / "sticky_promo_auth_notes_ok.yaml"
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "fixture",
            "--model",
            "gemini-2.5-flash",
            "--cassette",
            str(cassette),
            "--sticky-file",
            str(_STICKY_FILE),
            "--report",
            "text",
        ]
    )
    assert code == ExitCode.OK
    out = capsys.readouterr().out
    assert "=== 1. RENDERED CONTEXT ===" in out
    assert "=== 2. TOOL TRACE ===" in out
    assert "=== 3. LATENCY & TOKENS ===" in out
    assert "=== 4. SCHEMA & POLICY STATUS ===" in out
    assert "PROPOSAL_VALID" in out
    assert "Authentication Architecture and Multi-Card Flow" in out


def test_validate_sticky_promo_ok_json_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify --report json prints valid JSON payload."""
    cassette = _FIXTURES_DIR / "sticky_promo_auth_notes_ok.yaml"
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "fixture",
            "--cassette",
            str(cassette),
            "--sticky-file",
            str(_STICKY_FILE),
            "--report",
            "json",
        ]
    )
    assert code == ExitCode.OK
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["command"] == "validate-sticky-promo"
    assert data["schema_status"]["valid"] is True
    assert data["schema_status"]["status"] == "PROPOSAL_VALID"


def test_validate_sticky_promo_schema_invalid(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify schema invalid cassette exits 2."""
    cassette = _FIXTURES_DIR / "sticky_promo_schema_invalid.yaml"
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "fixture",
            "--cassette",
            str(cassette),
            "--sticky-file",
            str(_STICKY_FILE),
        ]
    )
    assert code == ExitCode.SCHEMA_OR_POLICY_VIOLATION
    out = capsys.readouterr().out
    assert "SCHEMA_ERROR" in out or "VALIDATION_FAILED" in out


def test_validate_sticky_promo_air_gap_denied(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify --air-gap with gemini provider exits 2 with AIR_GAP_EGRESS_DENIED."""
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "gemini",
            "--air-gap",
            "--sticky-file",
            str(_STICKY_FILE),
        ]
    )
    assert code == ExitCode.SCHEMA_OR_POLICY_VIOLATION
    out = capsys.readouterr().out
    assert "AIR_GAP_EGRESS_DENIED" in out


def test_validate_sticky_promo_strict_blocks_dropped_mermaid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify --strict-blocks with dropped mermaid cassette exits 2."""
    cassette = _FIXTURES_DIR / "sticky_promo_dropped_mermaid.yaml"
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "fixture",
            "--cassette",
            str(cassette),
            "--sticky-file",
            str(_STICKY_FILE),
            "--strict-blocks",
        ]
    )
    assert code == ExitCode.SCHEMA_OR_POLICY_VIOLATION
    out = capsys.readouterr().out
    assert "FENCED_BLOCK_MODIFIED" in out


def test_validate_sticky_promo_non_strict_blocks_dropped_mermaid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify non-strict mode with dropped mermaid cassette exits 0 and appends fallback."""
    cassette = _FIXTURES_DIR / "sticky_promo_dropped_mermaid.yaml"
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "fixture",
            "--cassette",
            str(cassette),
            "--sticky-file",
            str(_STICKY_FILE),
        ]
    )
    assert code == ExitCode.OK
    out = capsys.readouterr().out
    assert "PROPOSAL_VALID" in out
    assert "Warnings: FENCED_BLOCK_MODIFIED" in out


def test_validate_sticky_promo_with_acl_fixture(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify --acl-fixture is audited in tool trace."""
    acl_file = tmp_path / "acls.json"
    acl_file.write_text(json.dumps([{"principal_id": "u1", "effect": "ALLOW"}]), encoding="utf-8")

    cassette = _FIXTURES_DIR / "sticky_promo_auth_notes_ok.yaml"
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "fixture",
            "--cassette",
            str(cassette),
            "--sticky-file",
            str(_STICKY_FILE),
            "--acl-fixture",
            str(acl_file),
            "--verbose-tools",
        ]
    )
    assert code == ExitCode.OK
    out = capsys.readouterr().out
    assert "acl_preservation_check" in out
    assert "preserved_verbatim" in out


def test_validate_sticky_promo_live_provider_missing_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify live provider without cassette exits with error."""
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "gemini",
            "--sticky-file",
            str(_STICKY_FILE),
        ]
    )
    assert code == ExitCode.SCHEMA_OR_POLICY_VIOLATION
    out = capsys.readouterr().out
    assert "requires active API key or daemon" in out


def test_validate_sticky_promo_provider_with_cassette_override(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify named provider with explicit cassette uses cassette fixture."""
    cassette = _FIXTURES_DIR / "sticky_promo_auth_notes_ok.yaml"
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "gemini",
            "--cassette",
            str(cassette),
            "--sticky-file",
            str(_STICKY_FILE),
        ]
    )
    assert code == ExitCode.OK


def test_validate_sticky_promo_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify unexpected runtime error during structuring exits with RUNTIME_ERROR."""
    from agent.cli_commands import validate_sticky_promo

    async def _failing_structurer(*args: object, **kwargs: object) -> object:
        raise RuntimeError("Simulated unexpected crash")

    monkeypatch.setattr(
        validate_sticky_promo, "structure_sticky_to_doc_proposal", _failing_structurer
    )

    cassette = _FIXTURES_DIR / "sticky_promo_auth_notes_ok.yaml"
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "fixture",
            "--cassette",
            str(cassette),
            "--sticky-file",
            str(_STICKY_FILE),
        ]
    )
    assert code == ExitCode.RUNTIME_ERROR
    out = capsys.readouterr().out
    assert "Simulated unexpected crash" in out


def test_validate_sticky_promo_acl_fixture_not_a_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify missing acl-fixture file is handled gracefully without crashing."""
    cassette = _FIXTURES_DIR / "sticky_promo_auth_notes_ok.yaml"
    code = main(
        [
            "validate-sticky-promo",
            "--provider",
            "fixture",
            "--cassette",
            str(cassette),
            "--sticky-file",
            str(_STICKY_FILE),
            "--acl-fixture",
            "/tmp/nonexistent_acl_file_12345.json",
        ]
    )
    assert code == ExitCode.OK
