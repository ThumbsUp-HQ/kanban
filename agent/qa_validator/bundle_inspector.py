# Copyright 2026 Kanban Platform Contributors
"""Passive read-only proof bundle and ticket specification inspector."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import yaml
from pydantic import BaseModel, ConfigDict

from agent.providers.base import ToolCallStep
from agent.providers.errors import ProviderPolicyError
from agent.qa_validator.schemas import (
    DeterministicCheckResult,
    TicketSpecInput,
)
from kanban.security.scrubber import outbound_secret_scrubber

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "MAX_BUNDLE_BYTES",
    "MAX_FILE_BYTES",
    "ProofBundle",
    "ProofFileEntry",
    "ProofInspectionError",
    "inspect_png_file",
    "inspect_proof_directory",
    "parse_ticket_file",
]

MAX_FILE_BYTES: Final[int] = 2 * 1024 * 1024  # 2 MiB per file
MAX_BUNDLE_BYTES: Final[int] = 16 * 1024 * 1024  # 16 MiB total bundle
PNG_HEADER: Final[bytes] = b"\x89PNG\r\n\x1a\n"

_CODE_SYMLINK_ESCAPE: Final[str] = "PROOF_SYMLINK_ESCAPE"
_CODE_INVALID_ENTRY: Final[str] = "PROOF_INVALID_ENTRY"
_CODE_BUNDLE_TOO_LARGE: Final[str] = "PROOF_BUNDLE_TOO_LARGE"

_PNG_SIGNATURE_BYTES: Final[int] = 8
_CHUNK_LEN_BYTES: Final[int] = 12
_IHDR_START: Final[int] = 12
_IHDR_END: Final[int] = 16
_DIMS_START: Final[int] = 16
_DIMS_END: Final[int] = 24

_MIN_FRONTMATTER_PARTS: Final[int] = 2
_MIN_SCREENSHOTS: Final[int] = 3


class ProofInspectionError(ProviderPolicyError):
    """Raised when proof bundle inspection fails security or containment constraints."""

    def __init__(self, code: str, detail: str) -> None:
        """Initialize ProofInspectionError with error code and detail."""
        super().__init__(f"{code}: {detail}", code=code)
        self.code = code
        self.detail = detail


class ProofFileEntry(BaseModel):
    """Metadata and content for an inspected proof bundle file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rel_path: str
    abs_path: str
    size_bytes: int
    is_png: bool
    png_dimensions: tuple[int, int] | None = None
    content: str | None = None
    scrubbed_content: str | None = None


@dataclass(frozen=True)
class ProofBundle:
    """Inspected proof bundle containing entries, deterministic checks, and tool steps."""

    ticket: TicketSpecInput
    proof_dir: Path
    files: dict[str, ProofFileEntry]
    deterministic_checks: list[DeterministicCheckResult]
    tool_steps: list[ToolCallStep]


def inspect_png_file(path: Path) -> tuple[int, int]:
    """Inspect PNG file header and return (width, height) without decoding image."""
    try:
        raw = path.read_bytes()
    except OSError as err:
        msg = f"Failed to read PNG file {path.name}: {err}"
        raise ValueError(msg) from err

    if len(raw) < _PNG_SIGNATURE_BYTES or not raw.startswith(PNG_HEADER):
        msg = f"Invalid PNG signature in {path.name}"
        raise ValueError(msg)
    if len(raw) < _CHUNK_LEN_BYTES:
        msg = f"Truncated PNG chunk length in {path.name}"
        raise ValueError(msg)
    chunk_type = raw[_IHDR_START:_IHDR_END]
    if chunk_type != b"IHDR":
        msg = f"Expected IHDR chunk in {path.name}, got {chunk_type!r}"
        raise ValueError(msg)
    if len(raw) < _DIMS_END:
        msg = f"Truncated IHDR data in {path.name}"
        raise ValueError(msg)
    width, height = struct.unpack(">II", raw[_DIMS_START:_DIMS_END])
    return width, height


def _extract_frontmatter_and_body(raw_text: str) -> tuple[dict[str, Any], str]:
    """Split frontmatter YAML and markdown body if present."""
    if raw_text.startswith("---"):
        parts = raw_text.split("---", _MIN_FRONTMATTER_PARTS)
        if len(parts) >= _MIN_FRONTMATTER_PARTS:
            try:
                loaded = yaml.safe_load(parts[1])
                fm = loaded if isinstance(loaded, dict) else {}
            except Exception as err:
                msg = f"Failed to parse YAML frontmatter: {err}"
                raise ValueError(msg) from err
            body = parts[2] if len(parts) > _MIN_FRONTMATTER_PARTS else ""
            return fm, body
    try:
        loaded = yaml.safe_load(raw_text)
    except Exception as err:
        msg = f"Failed to parse ticket YAML: {err}"
        raise ValueError(msg) from err
    fm = loaded if isinstance(loaded, dict) else {}
    return fm, raw_text


def _extract_dods_from_markdown(body_markdown: str) -> list[str]:
    """Parse DoD bullet items from markdown body."""
    dods: list[str] = []
    in_dod = False
    for line in body_markdown.splitlines():
        line_lower = line.lower()
        if "definition of done" in line_lower:
            in_dod = True
            continue
        if in_dod and line.startswith("#"):
            break
        if in_dod:
            stripped = line.strip()
            if stripped.startswith(("- [ ]", "- [x]", "*", "-")):
                item = stripped.lstrip("-* [x]").strip()
                if item:
                    dods.append(item)
    return dods


def _extract_dods(frontmatter_dict: dict[str, Any], body_markdown: str) -> tuple[str, ...]:
    """Extract Definition of Done criteria list from frontmatter or body markdown."""
    if frontmatter_dict.get("definition_of_done"):
        raw_dods = frontmatter_dict["definition_of_done"]
        if isinstance(raw_dods, (list, tuple)):
            items = [str(d).strip() for d in raw_dods if str(d).strip()]
            if items:
                return tuple(items)

    if body_markdown:
        md_dods = _extract_dods_from_markdown(body_markdown)
        if md_dods:
            return tuple(md_dods)

    return ("All acceptance criteria and Definition of Done items met",)


def parse_ticket_file(ticket_path: Path) -> TicketSpecInput:
    """Parse ticket specification from either YAML file or Markdown with frontmatter."""
    if not ticket_path.exists():
        msg = f"Ticket file does not exist: {ticket_path}"
        raise FileNotFoundError(msg)
    if ticket_path.is_dir():
        msg = f"Ticket path is a directory, expected file: {ticket_path}"
        raise IsADirectoryError(msg)

    st = ticket_path.stat()
    if st.st_size > MAX_FILE_BYTES:
        msg = f"Ticket file size {st.st_size} exceeds {MAX_FILE_BYTES} bytes"
        raise ProofInspectionError(_CODE_BUNDLE_TOO_LARGE, msg)

    raw_text = ticket_path.read_text(encoding="utf-8")
    frontmatter_dict, body_markdown = _extract_frontmatter_and_body(raw_text)

    ticket_id = str(
        frontmatter_dict.get("id")
        or frontmatter_dict.get("identifier")
        or frontmatter_dict.get("ticket_id")
        or ticket_path.stem
    )
    title = str(frontmatter_dict.get("title") or "")
    epic = str(frontmatter_dict["epic"]) if frontmatter_dict.get("epic") else None

    raw_gates = frontmatter_dict.get("gates") or ()
    gates = tuple(str(g).strip() for g in raw_gates if str(g).strip())

    raw_deps = frontmatter_dict.get("new_dependencies") or ()
    new_dependencies = tuple(str(d).strip() for d in raw_deps if str(d).strip())

    dods = _extract_dods(frontmatter_dict, body_markdown)

    lowered_raw = raw_text.lower()
    is_non_ui = (
        "non-ui ticket" in lowered_raw
        or "n/a - non-ui ticket" in lowered_raw
        or "n/a - non-ui" in lowered_raw
    )
    has_ui = "ui-specialist" in gates or "[ui]" in title.lower() or "[ui]" in lowered_raw[:400]
    has_api = "api-specialist" in gates or "[api]" in title.lower() or "[api]" in lowered_raw[:400]
    has_dep = bool(new_dependencies) or "[dep]" in title.lower() or "[dep]" in lowered_raw[:400]

    return TicketSpecInput(
        id=ticket_id,
        title=title,
        epic=epic,
        gates=gates,
        new_dependencies=new_dependencies,
        definition_of_done=dods,
        is_non_ui_ticket=is_non_ui,
        has_ui_gate=has_ui,
        has_api_gate=has_api,
        has_dep_gate=has_dep,
        raw_text=raw_text,
        body_markdown=body_markdown,
    )


def _check_core_artifacts(
    files: dict[str, ProofFileEntry],
) -> DeterministicCheckResult:
    """Check 1: CORE_ARTIFACTS_PRESENT."""
    missing: list[str] = []
    if "git-diff.patch" not in files or files["git-diff.patch"].size_bytes == 0:
        missing.append("git-diff.patch")
    if "unit-test-results.txt" not in files or files["unit-test-results.txt"].size_bytes == 0:
        missing.append("unit-test-results.txt")
    has_build = ("build-check.txt" in files and files["build-check.txt"].size_bytes > 0) or (
        "build-or-typecheck.txt" in files and files["build-or-typecheck.txt"].size_bytes > 0
    )
    if not has_build:
        missing.append("build-check.txt (or build-or-typecheck.txt)")

    if missing:
        return DeterministicCheckResult(
            check_id="CORE_ARTIFACTS_PRESENT",
            passed=False,
            detail=f"Missing or empty core artifacts: {', '.join(missing)}",
        )
    return DeterministicCheckResult(
        check_id="CORE_ARTIFACTS_PRESENT",
        passed=True,
        detail="Core artifacts git-diff.patch, unit-test-results.txt, and build-check.txt present.",
    )


def _check_unit_tests(
    files: dict[str, ProofFileEntry],
) -> DeterministicCheckResult:
    """Check 2: UNIT_TESTS_EXIT_ZERO."""
    entry = files.get("unit-test-results.txt")
    if not entry or not entry.content:
        return DeterministicCheckResult(
            check_id="UNIT_TESTS_EXIT_ZERO",
            passed=False,
            detail="unit-test-results.txt is missing or empty.",
        )
    content = entry.content

    fail_patterns = [
        r"\b[1-9]\d*\s+failed\b",
        r"\b[1-9]\d*\s+failures\b",
        r"= FAILURES =",
        r"= ERRORS =",
        r"\bFAIL:\s+",
        r"exit\s*=\s*[1-9]\d*",
        r"exit code:\s*[1-9]\d*",
        r"exit status\s*[1-9]\d*",
    ]
    for pat in fail_patterns:
        match = re.search(pat, content, re.IGNORECASE)
        if match:
            return DeterministicCheckResult(
                check_id="UNIT_TESTS_EXIT_ZERO",
                passed=False,
                detail=f"Unit test output contains failure marker: '{match.group(0)}'",
            )

    pass_patterns = [
        r"\b\d+\s+passed\b",
        r"\bpassed in\b",
        r"\btests passed\b",
        r"\bOK\b",
    ]
    has_pass = any(re.search(p, content, re.IGNORECASE) for p in pass_patterns)
    if not has_pass:
        return DeterministicCheckResult(
            check_id="UNIT_TESTS_EXIT_ZERO",
            passed=False,
            detail="unit-test-results.txt does not contain a recognized passing summary marker.",
        )

    return DeterministicCheckResult(
        check_id="UNIT_TESTS_EXIT_ZERO",
        passed=True,
        detail="Unit tests executed cleanly with zero failures and verified passing summary.",
    )


def _check_build_clean(
    files: dict[str, ProofFileEntry],
) -> DeterministicCheckResult:
    """Check 3: BUILD_CHECK_CLEAN."""
    entry = files.get("build-check.txt") or files.get("build-or-typecheck.txt")
    if not entry or not entry.content:
        return DeterministicCheckResult(
            check_id="BUILD_CHECK_CLEAN",
            passed=False,
            detail="build-check.txt (or build-or-typecheck.txt) is missing or empty.",
        )
    content = entry.content

    error_patterns = [
        r"exit\s*=\s*[1-9]\d*",
        r"exit code:\s*[1-9]\d*",
        r"exit status\s*[1-9]\d*",
        r"Traceback \(most recent call last\):",
        r"\bSyntaxError\b",
        r"\bTypeError\b",
        r"\bImportError\b",
        r"\bModuleNotFoundError\b",
        r"\bFAILED\b",
        r"\bFailed:\s*[1-9]\d*",
    ]
    for pat in error_patterns:
        match = re.search(pat, content)
        if match:
            return DeterministicCheckResult(
                check_id="BUILD_CHECK_CLEAN",
                passed=False,
                detail=f"Build check output contains error marker: '{match.group(0)}'",
            )

    return DeterministicCheckResult(
        check_id="BUILD_CHECK_CLEAN",
        passed=True,
        detail="Build, typecheck, and linter checks executed cleanly with zero error exit markers.",
    )


def _check_ui_screenshots(
    files: dict[str, ProofFileEntry],
) -> DeterministicCheckResult:
    """Validate screenshots directory contains >= 3 responsive PNG viewports."""
    screenshots = [
        e
        for k, e in files.items()
        if (k.startswith("screenshots/") or "/screenshots/" in k) and e.is_png
    ]
    if len(screenshots) < _MIN_SCREENSHOTS:
        return DeterministicCheckResult(
            check_id="UI_SPECIALIST_GATE",
            passed=False,
            detail=f"UI specialist gate requires >= 3 screenshots, found {len(screenshots)}.",
        )

    has_desktop = any("desktop" in e.rel_path.lower() for e in screenshots)
    has_tablet = any("tablet" in e.rel_path.lower() for e in screenshots)
    has_mobile = any("mobile" in e.rel_path.lower() for e in screenshots)

    missing: list[str] = []
    if not has_desktop:
        missing.append("desktop")
    if not has_tablet:
        missing.append("tablet")
    if not has_mobile:
        missing.append("mobile")

    if missing:
        return DeterministicCheckResult(
            check_id="UI_SPECIALIST_GATE",
            passed=False,
            detail=f"Screenshots missing viewports: {', '.join(missing)}.",
        )

    return DeterministicCheckResult(
        check_id="UI_SPECIALIST_GATE",
        passed=True,
        detail=(
            f"UI specialist review approved with {len(screenshots)} "
            "responsive screenshots (desktop, tablet, mobile)."
        ),
    )


def _check_ui_specialist_gate(
    ticket: TicketSpecInput,
    files: dict[str, ProofFileEntry],
) -> DeterministicCheckResult:
    """Check 4: UI_SPECIALIST_GATE."""
    if not ticket.has_ui_gate:
        return DeterministicCheckResult(
            check_id="UI_SPECIALIST_GATE",
            passed=True,
            detail="N/A - Ticket does not require UI specialist gate.",
        )

    rev_entry = files.get("ui-specialist-review.md")
    if not rev_entry or not rev_entry.content or rev_entry.size_bytes == 0:
        return DeterministicCheckResult(
            check_id="UI_SPECIALIST_GATE",
            passed=False,
            detail="ui-specialist-review.md is missing or empty.",
        )

    rev_text = rev_entry.content
    has_approval = bool(
        re.search(
            r"\b(APPROVED|Verdict:\s*APPROVED|Status:\s*APPROVED)\b",
            rev_text,
            re.IGNORECASE,
        )
    )
    if not has_approval:
        return DeterministicCheckResult(
            check_id="UI_SPECIALIST_GATE",
            passed=False,
            detail="ui-specialist-review.md lacks explicit APPROVED verdict.",
        )

    if ticket.is_non_ui_ticket:
        return DeterministicCheckResult(
            check_id="UI_SPECIALIST_GATE",
            passed=True,
            detail="UI specialist review approved (screenshots N/A for non-UI ticket).",
        )

    return _check_ui_screenshots(files)


def _check_api_specialist_gate(
    ticket: TicketSpecInput,
    files: dict[str, ProofFileEntry],
) -> DeterministicCheckResult:
    """Check 5: API_SPECIALIST_GATE."""
    if not ticket.has_api_gate:
        return DeterministicCheckResult(
            check_id="API_SPECIALIST_GATE",
            passed=True,
            detail="N/A - Ticket does not require API specialist gate.",
        )

    api_entry = files.get("api-specialist-review.md")
    if not api_entry or not api_entry.content or api_entry.size_bytes == 0:
        return DeterministicCheckResult(
            check_id="API_SPECIALIST_GATE",
            passed=False,
            detail="api-specialist-review.md is missing or empty.",
        )
    if not re.search(r"\b(APPROVED|Verdict:\s*APPROVED)\b", api_entry.content, re.IGNORECASE):
        return DeterministicCheckResult(
            check_id="API_SPECIALIST_GATE",
            passed=False,
            detail="api-specialist-review.md lacks explicit APPROVED verdict.",
        )

    ui_entry = files.get("ui-specialist-review.md")
    if not ui_entry or not ui_entry.content or ui_entry.size_bytes == 0:
        return DeterministicCheckResult(
            check_id="API_SPECIALIST_GATE",
            passed=False,
            detail=(
                "API + UI Dual Specialist Gate requires ui-specialist-review.md (missing or empty)."
            ),
        )
    if not re.search(r"\b(APPROVED|Verdict:\s*APPROVED)\b", ui_entry.content, re.IGNORECASE):
        return DeterministicCheckResult(
            check_id="API_SPECIALIST_GATE",
            passed=False,
            detail=(
                "API + UI Dual Specialist Gate: "
                "ui-specialist-review.md lacks explicit APPROVED verdict."
            ),
        )

    return DeterministicCheckResult(
        check_id="API_SPECIALIST_GATE",
        passed=True,
        detail="API and UI specialist gate reviews both approved with verified sign-offs.",
    )


def _check_dependency_evaluation(
    ticket: TicketSpecInput,
    files: dict[str, ProofFileEntry],
) -> DeterministicCheckResult:
    """Check 6: DEPENDENCY_EVALUATION_GATE."""
    if not ticket.has_dep_gate:
        return DeterministicCheckResult(
            check_id="DEPENDENCY_EVALUATION_GATE",
            passed=True,
            detail="N/A - No new dependencies declared on ticket.",
        )

    dep_entry = files.get("dependency-evaluation.md")
    if not dep_entry or not dep_entry.content or dep_entry.size_bytes == 0:
        return DeterministicCheckResult(
            check_id="DEPENDENCY_EVALUATION_GATE",
            passed=False,
            detail=(
                "dependency-evaluation.md is missing or empty on ticket "
                "introducing new dependencies."
            ),
        )

    content = dep_entry.content
    has_license = bool(
        re.search(r"\b(Apache|MIT|BSD|OFL|permissive|PSF|ISC)\b", content, re.IGNORECASE)
    )
    has_sha = bool(re.search(r"\b(sha-?256|[0-9a-fA-F]{64})\b", content, re.IGNORECASE))
    has_signoffs = bool(
        re.search(
            r"\b(architect|arch-reviewer|qa-eng|sec-eng|sign-?off|reviewed by)\b",
            content,
            re.IGNORECASE,
        )
    )

    missing: list[str] = []
    if not has_license:
        missing.append("permissive license reference")
    if not has_sha:
        missing.append("SHA-256 cryptographic hash")
    if not has_signoffs:
        missing.append("architect and engineer sign-offs")

    if missing:
        return DeterministicCheckResult(
            check_id="DEPENDENCY_EVALUATION_GATE",
            passed=False,
            detail=f"dependency-evaluation.md incomplete: missing {', '.join(missing)}.",
        )

    return DeterministicCheckResult(
        check_id="DEPENDENCY_EVALUATION_GATE",
        passed=True,
        detail=(
            "Dependency evaluation verified with permissive license, "
            "SHA-256 hash, and specialist sign-offs."
        ),
    )


def _check_no_raw_secrets(
    files: dict[str, ProofFileEntry],
) -> tuple[DeterministicCheckResult, dict[str, ProofFileEntry]]:
    """Check 7: NO_RAW_SECRETS_IN_PROOF.

    Scans text artifacts with outbound_secret_scrubber, fails if raw secrets appear,
    and returns updated entries dictionary with scrubbed_content populated.
    """
    total_findings = 0
    detected_kinds: set[str] = set()
    updated_files: dict[str, ProofFileEntry] = {}

    for rel_path, entry in files.items():
        if entry.is_png or entry.content is None:
            updated_files[rel_path] = entry
            continue

        res = outbound_secret_scrubber(entry.content)
        scrubbed = res.text
        if res.redacted:
            total_findings += res.count
            detected_kinds.update(f.kind.value for f in res.findings)

        updated_files[rel_path] = ProofFileEntry(
            rel_path=entry.rel_path,
            abs_path=entry.abs_path,
            size_bytes=entry.size_bytes,
            is_png=entry.is_png,
            png_dimensions=entry.png_dimensions,
            content=entry.content,
            scrubbed_content=scrubbed,
        )

    if total_findings > 0:
        kinds_sorted = sorted(detected_kinds)
        return (
            DeterministicCheckResult(
                check_id="NO_RAW_SECRETS_IN_PROOF",
                passed=False,
                detail=(
                    f"Detected {total_findings} raw live secrets in proof bundle: {kinds_sorted}"
                ),
            ),
            updated_files,
        )

    return (
        DeterministicCheckResult(
            check_id="NO_RAW_SECRETS_IN_PROOF",
            passed=True,
            detail="Zero raw secrets detected in proof bundle text artifacts.",
        ),
        updated_files,
    )


def _verify_entry_security(
    entry: Path,
    resolved_proof_dir: Path,
) -> None:
    """Verify an entry does not violate containment or device restrictions."""
    if entry.is_fifo() or entry.is_socket() or entry.is_block_device() or entry.is_char_device():
        msg = f"Forbidden special device entry: {entry.name}"
        raise ProofInspectionError(_CODE_INVALID_ENTRY, msg)

    try:
        resolved_target = entry.resolve(strict=True)
        if not resolved_target.is_relative_to(resolved_proof_dir):
            msg = f"Symlink {entry.name} escapes proof directory to {resolved_target}"
            raise ProofInspectionError(_CODE_SYMLINK_ESCAPE, msg)
    except (ValueError, RuntimeError) as err:
        msg = f"Symlink escape verification failed for {entry.name}: {err}"
        raise ProofInspectionError(_CODE_SYMLINK_ESCAPE, msg) from err


def inspect_proof_directory(ticket_file: Path, proof_dir: Path) -> ProofBundle:
    """Inspect proof directory and ticket file passively without executing commands."""
    ticket = parse_ticket_file(ticket_file)

    if not proof_dir.exists():
        msg = f"Proof directory does not exist: {proof_dir}"
        raise FileNotFoundError(msg)
    if not proof_dir.is_dir():
        msg = f"Proof path is not a directory: {proof_dir}"
        raise NotADirectoryError(msg)

    resolved_proof_dir = proof_dir.resolve(strict=True)

    total_bundle_bytes = 0
    raw_files: dict[str, ProofFileEntry] = {}

    for entry in sorted(resolved_proof_dir.rglob("*")):
        if entry.is_dir():
            continue

        _verify_entry_security(entry, resolved_proof_dir)

        st = entry.stat()
        if st.st_size > MAX_FILE_BYTES:
            msg = f"File {entry.name} size {st.st_size} exceeds {MAX_FILE_BYTES} bytes"
            raise ProofInspectionError(_CODE_BUNDLE_TOO_LARGE, msg)

        total_bundle_bytes += st.st_size
        if total_bundle_bytes > MAX_BUNDLE_BYTES:
            msg = f"Bundle total size {total_bundle_bytes} exceeds {MAX_BUNDLE_BYTES} bytes"
            raise ProofInspectionError(_CODE_BUNDLE_TOO_LARGE, msg)

        rel_path = str(entry.relative_to(resolved_proof_dir))
        is_png = rel_path.lower().endswith(".png")

        png_dim: tuple[int, int] | None = None
        content: str | None = None
        if is_png:
            png_dim = inspect_png_file(entry)
        else:
            content = entry.read_text(encoding="utf-8", errors="replace")

        raw_files[rel_path] = ProofFileEntry(
            rel_path=rel_path,
            abs_path=str(entry),
            size_bytes=st.st_size,
            is_png=is_png,
            png_dimensions=png_dim,
            content=content,
            scrubbed_content=None,
        )

    check7, files = _check_no_raw_secrets(raw_files)

    checks = [
        _check_core_artifacts(files),
        _check_unit_tests(files),
        _check_build_clean(files),
        _check_ui_specialist_gate(ticket, files),
        _check_api_specialist_gate(ticket, files),
        _check_dependency_evaluation(ticket, files),
        check7,
    ]

    tool_steps: list[ToolCallStep] = [
        ToolCallStep(
            tool="deterministic_check",
            args={"check_id": c.check_id},
            result={"passed": c.passed, "detail": c.detail},
        )
        for c in checks
    ]
    tool_steps.extend(
        ToolCallStep(
            tool="inspect_file",
            args={"path": f.rel_path},
            result={
                "bytes": f.size_bytes,
                "is_png": f.is_png,
                "png_dimensions": (
                    f"{f.png_dimensions[0]}x{f.png_dimensions[1]}" if f.png_dimensions else None
                ),
            },
        )
        for f in files.values()
    )

    return ProofBundle(
        ticket=ticket,
        proof_dir=resolved_proof_dir,
        files=files,
        deterministic_checks=checks,
        tool_steps=tool_steps,
    )
