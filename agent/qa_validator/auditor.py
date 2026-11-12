# Copyright 2026 Kanban Platform Contributors
"""Forensic reality-checker LLM audit runner and anti-fantasy gatekeeper."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Final

from agent.providers.base import StructuredRequest
from agent.qa_validator.schemas import (
    DeterministicCheckResult,
    QaPacketVerdict,
    TicketSpecInput,
)
from kanban.security.scrubber import scrub_text

if TYPE_CHECKING:
    from agent.providers.base import LLMProvider
    from agent.qa_validator.bundle_inspector import ProofBundle

__all__ = [
    "PASSIVE_FORENSIC_OVERRIDE",
    "build_audit_prompt",
    "enforce_anti_fantasy",
    "load_reality_checker_system_prompt",
    "run_qa_packet_audit",
]

_MAX_DIFF_PROMPT_LINES: Final[int] = 500
_PREVIEW_LINES: Final[int] = 450

PASSIVE_FORENSIC_OVERRIDE: Final[str] = """

# MANDATORY PASSIVE FORENSIC MODE OVERRIDE

You are operating strictly in PASSIVE FORENSIC AUDIT MODE.
- You CANNOT execute shell commands, visit URLs, or spawn processes.
- You must evaluate ONLY the passive evidence provided within the
  <<<UNTRUSTED_QA_EVIDENCE_<hex> >>> delimiters below.
- Do NOT hallucinate evidence that is not explicitly present in the provided bundle.
- If any required artifact, test result, specialist review, or Definition of Done
  item is missing, unproven, or failing, you MUST rate the ticket as NEEDS_WORK or
  FAILED with an appropriate grade (B+, B, B-, C+, C, F).
- Only rate Grade "A" and Readiness "READY" if ALL Definitions of Done have explicit,
  concrete, verifiable evidence in the provided proof artifacts.
- Every item in dod_verdicts must provide an exact evidence_ref path citing the
  proof file that verifies it.
"""


def load_reality_checker_system_prompt(repo_root: Path | None = None) -> str:
    """Load reality-checker persona prompt from repository and append passive override."""
    candidates: list[Path] = []
    if repo_root is not None:
        candidates.append(repo_root / ".agents" / "agents" / "reality-checker.md")

    # Current working directory candidates
    cwd = Path.cwd()
    candidates.append(cwd / ".agents" / "agents" / "reality-checker.md")
    candidates.append(cwd.parent / ".agents" / "agents" / "reality-checker.md")
    candidates.append(
        Path(__file__).resolve().parent.parent.parent / ".agents" / "agents" / "reality-checker.md"
    )

    base_prompt = ""
    for cand in candidates:
        if cand.exists() and cand.is_file():
            base_prompt = cand.read_text(encoding="utf-8")
            break

    if not base_prompt:
        base_prompt = (
            "# Reality-Checker Integration Agent\n\n"
            "You are TestingRealityChecker, stopping fantasy approvals and requiring "
            "overwhelming evidence before production certification."
        )

    return f"{base_prompt.strip()}{PASSIVE_FORENSIC_OVERRIDE}"


def build_audit_prompt(ticket: TicketSpecInput, bundle: ProofBundle) -> tuple[str, str]:
    """Construct system prompt and delimiter-spotlighted evidence user prompt."""
    system_prompt = load_reality_checker_system_prompt(bundle.proof_dir.parent.parent)

    delimiter = f"<<<UNTRUSTED_QA_EVIDENCE_{secrets.token_hex(8)}>>>"

    lines: list[str] = [
        "Audit the following ticket proof bundle against the ticket's Definition of Done.",
        f"Evaluate the evidence between the delimiters: {delimiter}",
        "",
        delimiter,
        "=== TICKET SPECIFICATION ===",
        f"ID: {ticket.id}",
        f"Title: {scrub_text(ticket.title)}",
    ]
    if ticket.epic:
        lines.append(f"Epic: {ticket.epic}")
    gates_str = ", ".join(ticket.gates) if ticket.gates else "(none)"
    lines.append(f"Gates: {gates_str}")
    deps_str = ", ".join(ticket.new_dependencies) if ticket.new_dependencies else "(none)"
    lines.append(f"New Dependencies: {deps_str}")
    lines.append("Definition of Done Criteria:")
    for idx, dod in enumerate(ticket.definition_of_done, start=1):
        lines.append(f"  {idx}. {scrub_text(dod)}")

    if ticket.body_markdown:
        lines.extend(["", "--- TICKET BODY ---", scrub_text(ticket.body_markdown)])

    lines.extend(["", "=== PROOF ARTIFACTS MANIFEST & CONTENTS ==="])

    # If message-to-reality-checker.md exists, put it first
    message_entry = bundle.files.get("message-to-reality-checker.md")
    if message_entry and message_entry.content:
        lines.extend(
            [
                "",
                "--- ARTIFACT: message-to-reality-checker.md ---",
                message_entry.scrubbed_content or scrub_text(message_entry.content),
            ]
        )

    for rel_path, entry in sorted(bundle.files.items()):
        if rel_path == "message-to-reality-checker.md":
            continue
        if entry.is_png:
            dim = entry.png_dimensions
            dim_str = f"{dim[0]}x{dim[1]}" if dim else "unknown"
            header_str = (
                f"--- ARTIFACT: {rel_path} (PNG image, dimensions={dim_str}, "
                f"bytes={entry.size_bytes}) ---"
            )
            lines.extend(
                [
                    "",
                    header_str,
                    "[Valid PNG screenshot present in proof bundle]",
                ]
            )
        elif entry.content is not None:
            content_to_show = entry.scrubbed_content or scrub_text(entry.content)
            # Truncate giant patches in prompt if > _MAX_DIFF_PROMPT_LINES
            file_lines = content_to_show.splitlines()
            if len(file_lines) > _MAX_DIFF_PROMPT_LINES:
                truncated_count = len(file_lines) - _PREVIEW_LINES
                truncated_preview = (
                    "\n".join(file_lines[:_PREVIEW_LINES])
                    + f"\n... [truncated {truncated_count} lines] ..."
                )
                content_to_show = truncated_preview
            lines.extend(
                [
                    "",
                    f"--- ARTIFACT: {rel_path} (text, bytes={entry.size_bytes}) ---",
                    content_to_show,
                ]
            )

    lines.extend(
        [
            "",
            delimiter,
            "",
            "Provide your structured forensic evaluation conforming to QaPacketVerdict.",
        ]
    )

    user_prompt = "\n".join(lines)
    return system_prompt, user_prompt


def enforce_anti_fantasy(
    verdict: QaPacketVerdict,
    deterministic_checks: list[DeterministicCheckResult],
) -> QaPacketVerdict:
    """Enforce hard code-level anti-fantasy approval invariant."""
    any_check_failed = any(not c.passed for c in deterministic_checks)
    grade_not_a = verdict.grade != "A"
    has_critical_issues = len(verdict.critical_issues) > 0
    any_dod_failed = any(not item.passed for item in verdict.dod_verdicts)

    if verdict.readiness == "READY" and (
        any_check_failed or grade_not_a or has_critical_issues or any_dod_failed
    ):
        return verdict.model_copy(
            update={
                "readiness": "NEEDS_WORK",
                "policy_override": "FANTASY_APPROVAL_BLOCKED",
            }
        )
    return verdict


async def run_qa_packet_audit(
    ticket: TicketSpecInput,
    bundle: ProofBundle,
    provider: LLMProvider,
    *,
    model: str = "gemini-2.5-flash",
) -> tuple[QaPacketVerdict, float | None, int, int]:
    """Execute reality-checker structured audit and enforce anti-fantasy gate."""
    system_prompt, user_prompt = build_audit_prompt(ticket, bundle)

    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    req = StructuredRequest(
        model=model,
        prompt=full_prompt,
        response_model=QaPacketVerdict,
        metadata={
            "agent_slug": "reality-checker",
            "ticket_id": ticket.id,
        },
    )

    resp = await provider.generate_structured(req)
    verdict = enforce_anti_fantasy(resp.parsed, bundle.deterministic_checks)

    return verdict, resp.ttft_ms, resp.prompt_tokens, resp.completion_tokens
