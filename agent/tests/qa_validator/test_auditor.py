# Copyright 2026 Kanban Platform Contributors
"""Unit tests for reality-checker LLM auditor and anti-fantasy gatekeeper."""

from __future__ import annotations

from pathlib import Path

import pytest

import agent.qa_validator.auditor as aud
from agent.qa_validator.auditor import (
    build_audit_prompt,
    enforce_anti_fantasy,
    load_reality_checker_system_prompt,
    run_qa_packet_audit,
)
from agent.qa_validator.bundle_inspector import (
    ProofBundle,
    ProofFileEntry,
    inspect_proof_directory,
)
from agent.qa_validator.schemas import (
    DeterministicCheckResult,
    DodItemAudit,
    QaPacketVerdict,
    TicketSpecInput,
)
from agent.testing.fixtures import FixtureLLMProvider, load_cassette

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures" / "ai"


def test_load_reality_checker_system_prompt() -> None:
    """Verify loading reality-checker prompt includes passive override."""
    prompt = load_reality_checker_system_prompt()
    assert "MANDATORY PASSIVE FORENSIC MODE OVERRIDE" in prompt
    assert "PASSIVE FORENSIC AUDIT MODE" in prompt


def test_load_reality_checker_prompt_fallback(tmp_path: Path) -> None:
    """Verify fallback prompt when reality-checker.md cannot be located."""
    mp = pytest.MonkeyPatch()
    # Mock Path.exists to return False for markdown files
    orig_exists = Path.exists

    def _mock_exists(self: Path) -> bool:
        if self.name == "reality-checker.md":
            return False
        return orig_exists(self)

    mp.setattr(Path, "exists", _mock_exists)
    prompt = aud.load_reality_checker_system_prompt(tmp_path)
    assert "Reality-Checker Integration Agent" in prompt
    mp.undo()


def test_build_audit_prompt_formatting(tmp_path: Path) -> None:
    """Verify audit prompt builds randomized delimiters and spotlights evidence."""
    ticket = TicketSpecInput(
        id="T-100",
        title="Sample Task",
        epic="KB-E1",
        gates=("ui-specialist",),
        definition_of_done=("Criterion 1", "Criterion 2"),
        raw_text="id: T-100\ntitle: Sample Task",
        body_markdown="Details here",
    )

    # Large patch to trigger line truncation branch (> 500 lines)
    big_patch_lines = ["+line" + str(i) for i in range(550)]
    big_patch = "\n".join(big_patch_lines)

    bundle = ProofBundle(
        ticket=ticket,
        proof_dir=tmp_path,
        files={
            "git-diff.patch": ProofFileEntry(
                rel_path="git-diff.patch",
                abs_path=str(tmp_path / "git-diff.patch"),
                size_bytes=len(big_patch),
                is_png=False,
                content=big_patch,
                scrubbed_content=None,
            ),
            "screenshots/mobile.png": ProofFileEntry(
                rel_path="screenshots/mobile.png",
                abs_path=str(tmp_path / "screenshots" / "mobile.png"),
                size_bytes=1000,
                is_png=True,
                png_dimensions=(390, 844),
            ),
            "message-to-reality-checker.md": ProofFileEntry(
                rel_path="message-to-reality-checker.md",
                abs_path=str(tmp_path / "message-to-reality-checker.md"),
                size_bytes=50,
                is_png=False,
                content="High priority note to reality checker",
                scrubbed_content=None,
            ),
        },
        deterministic_checks=[DeterministicCheckResult(check_id="C1", passed=True, detail="ok")],
        tool_steps=[],
    )

    sys_prompt, user_prompt = build_audit_prompt(ticket, bundle)
    assert "MANDATORY PASSIVE FORENSIC MODE OVERRIDE" in sys_prompt
    assert "<<<UNTRUSTED_QA_EVIDENCE_" in user_prompt
    assert "T-100" in user_prompt
    assert "Criterion 1" in user_prompt
    assert "message-to-reality-checker.md" in user_prompt
    assert "screenshots/mobile.png (PNG image, dimensions=390x844" in user_prompt
    assert "truncated" in user_prompt  # verifies > 500 lines truncation


def test_anti_fantasy_enforcement_blocks() -> None:
    """Verify code-enforced anti-fantasy gate blocks premature READY approvals."""
    clean_checks = [DeterministicCheckResult(check_id="C1", passed=True, detail="ok")]
    failed_checks = [DeterministicCheckResult(check_id="C1", passed=False, detail="failed")]

    # 1. READY with grade A and all passed -> unchanged
    v_ok = QaPacketVerdict(
        grade="A",
        readiness="READY",
        dod_verdicts=[DodItemAudit(criterion="Test", passed=True, evidence_ref="ref")],
        critical_issues=[],
        report_markdown="ok",
    )
    res_ok = enforce_anti_fantasy(v_ok, clean_checks)
    assert res_ok.readiness == "READY"
    assert res_ok.policy_override is None

    # 2. READY with failing deterministic check -> BLOCKED
    res_fail_check = enforce_anti_fantasy(v_ok, failed_checks)
    assert res_fail_check.readiness == "NEEDS_WORK"
    assert res_fail_check.policy_override == "FANTASY_APPROVAL_BLOCKED"

    # 3. READY with grade B+ -> BLOCKED
    v_b = v_ok.model_copy(update={"grade": "B+"})
    res_b = enforce_anti_fantasy(v_b, clean_checks)
    assert res_b.readiness == "NEEDS_WORK"
    assert res_b.policy_override == "FANTASY_APPROVAL_BLOCKED"

    # 4. READY with critical issue -> BLOCKED
    v_crit = v_ok.model_copy(update={"critical_issues": ["Issue 1"]})
    res_crit = enforce_anti_fantasy(v_crit, clean_checks)
    assert res_crit.readiness == "NEEDS_WORK"
    assert res_crit.policy_override == "FANTASY_APPROVAL_BLOCKED"

    # 5. READY with failed DoD item -> BLOCKED
    v_dod_fail = v_ok.model_copy(
        update={"dod_verdicts": [DodItemAudit(criterion="Test", passed=False, evidence_ref="ref")]}
    )
    res_dod = enforce_anti_fantasy(v_dod_fail, clean_checks)
    assert res_dod.readiness == "NEEDS_WORK"
    assert res_dod.policy_override == "FANTASY_APPROVAL_BLOCKED"

    # 6. Non-READY verdict (e.g. FAILED) -> unchanged
    v_failed = v_ok.model_copy(update={"grade": "F", "readiness": "FAILED"})
    res_failed = enforce_anti_fantasy(v_failed, clean_checks)
    assert res_failed.readiness == "FAILED"
    assert res_failed.policy_override is None


@pytest.mark.asyncio
async def test_run_qa_packet_audit_fixture() -> None:
    """Verify run_qa_packet_audit executes with FixtureLLMProvider."""
    ticket_file = Path("examples/tickets/kan-142.yaml")
    proof_dir = Path("examples/qa_packets/kan-142-ready")
    bundle = inspect_proof_directory(ticket_file, proof_dir)

    cassette = load_cassette(FIXTURES_DIR / "qa_packet_grade_a_ready.yaml")
    provider = FixtureLLMProvider(cassettes=[cassette])

    verdict, ttft, p_tok, c_tok = await run_qa_packet_audit(
        bundle.ticket, bundle, provider, model="fixture-model"
    )

    assert verdict.grade == "A"
    assert verdict.readiness == "READY"
    assert ttft == 12.0
    assert p_tok == 520
    assert c_tok == 140
