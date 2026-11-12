# Copyright 2026 Kanban Platform Contributors
"""Unit tests for passive proof bundle inspector and ticket parser."""

from __future__ import annotations

import os
import struct
import zlib
from typing import TYPE_CHECKING

import pytest

import agent.qa_validator.bundle_inspector as bi
from agent.qa_validator.bundle_inspector import (
    MAX_FILE_BYTES,
    ProofInspectionError,
    inspect_png_file,
    inspect_proof_directory,
    parse_ticket_file,
)
from agent.qa_validator.schemas import DodItemAudit, QaPacketVerdict

if TYPE_CHECKING:
    from pathlib import Path


def _make_png(path: Path, width: int = 100, height: int = 100) -> None:
    """Write a valid minimal PNG file."""
    header = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc
    scanlines = b"".join(b"\x00" + b"\x10\x20\x30" * width for _ in range(height))
    compressed = zlib.compress(scanlines)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
    idat_chunk = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend_chunk = struct.pack(">I", 0) + b"IEND" + iend_crc
    path.write_bytes(header + ihdr_chunk + idat_chunk + iend_chunk)


def test_png_inspection_valid(tmp_path: Path) -> None:
    """Verify PNG header inspection returns exact dimensions."""
    png_file = tmp_path / "valid.png"
    _make_png(png_file, 800, 600)
    w, h = inspect_png_file(png_file)
    assert (w, h) == (800, 600)


def test_png_inspection_invalid_signature(tmp_path: Path) -> None:
    """Verify invalid PNG signature raises ValueError."""
    bad_file = tmp_path / "bad.png"
    bad_file.write_bytes(b"NOT_A_PNG_HEADER")
    with pytest.raises(ValueError, match="Invalid PNG signature"):
        inspect_png_file(bad_file)


def test_png_inspection_truncated_chunk_length(tmp_path: Path) -> None:
    """Verify truncated chunk length in PNG raises ValueError."""
    bad_file = tmp_path / "trunc_chunk.png"
    bad_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    with pytest.raises(ValueError, match="Truncated PNG chunk length"):
        inspect_png_file(bad_file)


def test_png_inspection_truncated_ihdr(tmp_path: Path) -> None:
    """Verify truncated IHDR data raises ValueError."""
    bad_file = tmp_path / "trunc_ihdr.png"
    bad_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00")
    with pytest.raises(ValueError, match="Truncated IHDR data"):
        inspect_png_file(bad_file)


def test_parse_ticket_file_yaml(tmp_path: Path) -> None:
    """Verify parsing a valid YAML ticket file."""
    t_file = tmp_path / "ticket.yaml"
    t_file.write_text(
        """id: TEST-01
title: "[UI] Implement feature"
gates: [ui-specialist, reality-checker]
definition_of_done:
  - "Criterion 1"
  - "Criterion 2"
""",
        encoding="utf-8",
    )
    spec = parse_ticket_file(t_file)
    assert spec.id == "TEST-01"
    assert spec.has_ui_gate is True
    assert len(spec.definition_of_done) == 2


def test_parse_ticket_file_markdown(tmp_path: Path) -> None:
    """Verify parsing a Markdown ticket file with frontmatter and body DoD."""
    md_file = tmp_path / "ticket.md"
    md_file.write_text(
        """---
id: KB-P5-99
title: "Sample Ticket"
gates: [api-specialist]
new_dependencies: [pydantic]
---
# Ticket Body
### Definition of Done
- [ ] Task 1
- [ ] Task 2
""",
        encoding="utf-8",
    )
    spec = parse_ticket_file(md_file)
    assert spec.id == "KB-P5-99"
    assert spec.has_api_gate is True
    assert spec.has_dep_gate is True
    assert len(spec.definition_of_done) == 2
    assert "Task 1" in spec.definition_of_done[0]


def test_parse_ticket_file_corrupt_yaml(tmp_path: Path) -> None:
    """Verify corrupt YAML raises ValueError."""
    bad_frontmatter = tmp_path / "bad_fm.md"
    bad_frontmatter.write_text("---\n[invalid yaml\n---\nBody", encoding="utf-8")
    with pytest.raises(ValueError, match="Failed to parse YAML frontmatter"):
        parse_ticket_file(bad_frontmatter)

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("[invalid yaml\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Failed to parse ticket YAML"):
        parse_ticket_file(bad_yaml)


def test_parse_ticket_file_empty_dod_fallback(tmp_path: Path) -> None:
    """Verify ticket without DoD items falls back to default."""
    t_file = tmp_path / "plain.yaml"
    t_file.write_text("id: NO-DOD\ntitle: No DoD\n", encoding="utf-8")
    spec = parse_ticket_file(t_file)
    assert len(spec.definition_of_done) == 1
    assert "All acceptance criteria" in spec.definition_of_done[0]


def test_parse_ticket_file_missing_and_dir(tmp_path: Path) -> None:
    """Verify missing ticket file or directory path raises appropriate errors."""
    with pytest.raises(FileNotFoundError):
        parse_ticket_file(tmp_path / "nonexistent.yaml")
    with pytest.raises(IsADirectoryError):
        parse_ticket_file(tmp_path)


def test_parse_ticket_file_oversized(tmp_path: Path) -> None:
    """Verify ticket file exceeding 2 MiB is rejected with PROOF_BUNDLE_TOO_LARGE."""
    big_file = tmp_path / "big_ticket.yaml"
    big_file.write_bytes(b"a" * (MAX_FILE_BYTES + 10))
    with pytest.raises(ProofInspectionError) as exc_info:
        parse_ticket_file(big_file)
    assert exc_info.value.code == "PROOF_BUNDLE_TOO_LARGE"


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    """Verify symlink escaping proof directory is rejected with PROOF_SYMLINK_ESCAPE."""
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secret outside", encoding="utf-8")

    link_path = proof_dir / "git-diff.patch"
    link_path.symlink_to(outside_file)

    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text("id: ESC-1\ntitle: Escaper\n", encoding="utf-8")

    with pytest.raises(ProofInspectionError) as exc_info:
        inspect_proof_directory(ticket_file, proof_dir)
    assert exc_info.value.code == "PROOF_SYMLINK_ESCAPE"


def test_file_oversized_rejected(tmp_path: Path) -> None:
    """Verify individual file > 2 MiB in proof dir is rejected."""
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    (proof_dir / "big.patch").write_bytes(b"x" * (MAX_FILE_BYTES + 10))

    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text("id: BIG-1\ntitle: Big\n", encoding="utf-8")

    with pytest.raises(ProofInspectionError) as exc_info:
        inspect_proof_directory(ticket_file, proof_dir)
    assert exc_info.value.code == "PROOF_BUNDLE_TOO_LARGE"


def test_bundle_oversized_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify total bundle size exceeding 16 MiB is rejected."""
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    (proof_dir / "file1.txt").write_text("a", encoding="utf-8")

    # Lower MAX_BUNDLE_BYTES dynamically to test threshold cleanly
    monkeypatch.setattr(bi, "MAX_BUNDLE_BYTES", 5)

    (proof_dir / "file2.txt").write_text("123456", encoding="utf-8")
    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text("id: BUNDLE-1\ntitle: Bundle\n", encoding="utf-8")

    with pytest.raises(ProofInspectionError) as exc_info:
        inspect_proof_directory(ticket_file, proof_dir)
    assert exc_info.value.code == "PROOF_BUNDLE_TOO_LARGE"


def test_missing_proof_dir(tmp_path: Path) -> None:
    """Verify missing proof dir raises FileNotFoundError."""
    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text("id: T-1\ntitle: Test\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        inspect_proof_directory(ticket_file, tmp_path / "does_not_exist")
    with pytest.raises(NotADirectoryError):
        inspect_proof_directory(ticket_file, ticket_file)


def test_special_device_rejected(tmp_path: Path) -> None:
    """Verify special FIFO entry in proof directory is rejected."""
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    fifo_path = proof_dir / "pipe.fifo"
    try:
        os.mkfifo(fifo_path)
    except (AttributeError, OSError):
        pytest.skip("mkfifo not supported on filesystem")

    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text("id: DEV-1\ntitle: Dev\n", encoding="utf-8")

    with pytest.raises(ProofInspectionError) as exc_info:
        inspect_proof_directory(ticket_file, proof_dir)
    assert exc_info.value.code == "PROOF_INVALID_ENTRY"


def test_core_artifacts_missing_branches(tmp_path: Path) -> None:
    """Verify check 1 fails when individual core artifacts are missing."""
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text("id: CORE-1\ntitle: Core\n", encoding="utf-8")

    bundle = inspect_proof_directory(ticket_file, proof_dir)
    c1 = next(c for c in bundle.deterministic_checks if c.check_id == "CORE_ARTIFACTS_PRESENT")
    assert c1.passed is False
    assert "git-diff.patch" in c1.detail


def test_unit_tests_missing_and_no_pass_marker(tmp_path: Path) -> None:
    """Verify check 2 fails when unit tests output lacks pass marker."""
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    (proof_dir / "git-diff.patch").write_text("patch", encoding="utf-8")
    (proof_dir / "unit-test-results.txt").write_text(
        "Some random text without pass marker", encoding="utf-8"
    )
    (proof_dir / "build-check.txt").write_text("clean", encoding="utf-8")

    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text("id: UT-1\ntitle: Unit Test\n", encoding="utf-8")

    bundle = inspect_proof_directory(ticket_file, proof_dir)
    c2 = next(c for c in bundle.deterministic_checks if c.check_id == "UNIT_TESTS_EXIT_ZERO")
    assert c2.passed is False
    assert "does not contain a recognized passing summary marker" in c2.detail


def test_ui_specialist_gate_missing_viewports(tmp_path: Path) -> None:
    """Verify check 4 fails when screenshots are missing specific viewports."""
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    (proof_dir / "git-diff.patch").write_text("patch", encoding="utf-8")
    (proof_dir / "unit-test-results.txt").write_text("10 passed", encoding="utf-8")
    (proof_dir / "build-check.txt").write_text("clean", encoding="utf-8")
    (proof_dir / "ui-specialist-review.md").write_text("Verdict: APPROVED", encoding="utf-8")

    screenshots_dir = proof_dir / "screenshots"
    screenshots_dir.mkdir()
    _make_png(screenshots_dir / "shot-desktop-1.png", 100, 100)
    _make_png(screenshots_dir / "shot-desktop-2.png", 100, 100)
    _make_png(screenshots_dir / "shot-tablet-1.png", 100, 100)

    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text(
        "id: UI-VP\ntitle: '[UI] Viewport check'\ngates: [ui-specialist]\n",
        encoding="utf-8",
    )

    bundle = inspect_proof_directory(ticket_file, proof_dir)
    c4 = next(c for c in bundle.deterministic_checks if c.check_id == "UI_SPECIALIST_GATE")
    assert c4.passed is False
    assert "mobile" in c4.detail


def test_ui_specialist_gate_non_ui_ticket_screenshots_na(tmp_path: Path) -> None:
    """Verify non-UI ticket with ui-specialist-review.md passes without screenshots."""
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    (proof_dir / "git-diff.patch").write_text("patch", encoding="utf-8")
    (proof_dir / "unit-test-results.txt").write_text("10 passed", encoding="utf-8")
    (proof_dir / "build-check.txt").write_text("clean", encoding="utf-8")
    (proof_dir / "ui-specialist-review.md").write_text("Verdict: APPROVED", encoding="utf-8")

    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text(
        "id: NON-UI\n"
        "title: Non UI Task\n"
        "gates: [ui-specialist]\n"
        "screenshots: N/A - Non-UI Ticket\n",
        encoding="utf-8",
    )

    bundle = inspect_proof_directory(ticket_file, proof_dir)
    c4 = next(c for c in bundle.deterministic_checks if c.check_id == "UI_SPECIALIST_GATE")
    assert c4.passed is True
    assert "screenshots N/A" in c4.detail


def test_api_specialist_gate_variants(tmp_path: Path) -> None:
    """Verify check 5 fails when api-specialist review is missing or unapproved."""
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    (proof_dir / "git-diff.patch").write_text("patch", encoding="utf-8")
    (proof_dir / "unit-test-results.txt").write_text("10 passed", encoding="utf-8")
    (proof_dir / "build-check.txt").write_text("clean", encoding="utf-8")
    (proof_dir / "ui-specialist-review.md").write_text("Verdict: APPROVED", encoding="utf-8")

    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text(
        "id: API-1\ntitle: '[API] Endpoint'\ngates: [api-specialist]\n",
        encoding="utf-8",
    )

    # 1. Missing api-specialist-review.md
    b1 = inspect_proof_directory(ticket_file, proof_dir)
    c5_1 = next(c for c in b1.deterministic_checks if c.check_id == "API_SPECIALIST_GATE")
    assert c5_1.passed is False

    # 2. Unapproved api-specialist-review.md
    (proof_dir / "api-specialist-review.md").write_text("Verdict: REJECTED", encoding="utf-8")
    b2 = inspect_proof_directory(ticket_file, proof_dir)
    c5_2 = next(c for c in b2.deterministic_checks if c.check_id == "API_SPECIALIST_GATE")
    assert c5_2.passed is False

    # 3. Both approved
    (proof_dir / "api-specialist-review.md").write_text("Verdict: APPROVED", encoding="utf-8")
    b3 = inspect_proof_directory(ticket_file, proof_dir)
    c5_3 = next(c for c in b3.deterministic_checks if c.check_id == "API_SPECIALIST_GATE")
    assert c5_3.passed is True


def test_dependency_evaluation_gate_variants(tmp_path: Path) -> None:
    """Verify check 6 fails on incomplete dependency evaluation."""
    proof_dir = tmp_path / "proof"
    proof_dir.mkdir()
    (proof_dir / "git-diff.patch").write_text("patch", encoding="utf-8")
    (proof_dir / "unit-test-results.txt").write_text("10 passed", encoding="utf-8")
    (proof_dir / "build-check.txt").write_text("clean", encoding="utf-8")

    ticket_file = tmp_path / "ticket.yaml"
    ticket_file.write_text(
        "id: DEP-1\ntitle: Dep Task\nnew_dependencies: [some-lib]\n",
        encoding="utf-8",
    )

    # 1. Missing dependency-evaluation.md
    b1 = inspect_proof_directory(ticket_file, proof_dir)
    c6_1 = next(c for c in b1.deterministic_checks if c.check_id == "DEPENDENCY_EVALUATION_GATE")
    assert c6_1.passed is False

    # 2. Incomplete dependency evaluation (missing sha and signoffs)
    (proof_dir / "dependency-evaluation.md").write_text("License: Apache-2.0", encoding="utf-8")
    b2 = inspect_proof_directory(ticket_file, proof_dir)
    c6_2 = next(c for c in b2.deterministic_checks if c.check_id == "DEPENDENCY_EVALUATION_GATE")
    assert c6_2.passed is False
    assert "SHA-256" in c6_2.detail

    # 3. Complete dependency evaluation
    sha_str = "0123456789abcdef" * 4
    (proof_dir / "dependency-evaluation.md").write_text(
        f"License: Apache-2.0\nSHA-256: {sha_str}\nSign-offs: arch-reviewer, qa-eng, sec-eng",
        encoding="utf-8",
    )
    b3 = inspect_proof_directory(ticket_file, proof_dir)
    c6_3 = next(c for c in b3.deterministic_checks if c.check_id == "DEPENDENCY_EVALUATION_GATE")
    assert c6_3.passed is True


def test_qa_verdict_schema_property() -> None:
    """Verify QaPacketVerdict.schema property returns expected identifier."""
    v = QaPacketVerdict(
        grade="A",
        readiness="READY",
        dod_verdicts=[DodItemAudit(criterion="Test", passed=True, evidence_ref="ref")],
        critical_issues=[],
        report_markdown="ok",
    )
    assert v.schema_ == "kb-qa-verdict/v1"
    assert v.model_dump(by_alias=True)["schema"] == "kb-qa-verdict/v1"


def test_png_wrong_chunk_type(tmp_path: Path) -> None:
    """Verify PNG without initial IHDR chunk raises ValueError."""
    bad_file = tmp_path / "wrong_chunk.png"
    bad_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIDAT1234567890123")
    with pytest.raises(ValueError, match="Expected IHDR chunk"):
        inspect_png_file(bad_file)


def test_parse_ticket_frontmatter_non_dict(tmp_path: Path) -> None:
    """Verify ticket with frontmatter not resolving to dict."""
    fm_file = tmp_path / "non_dict.md"
    fm_file.write_text("---\n'just a string'\n---\nBody", encoding="utf-8")
    spec = parse_ticket_file(fm_file)
    assert spec.id == "non_dict"


def test_specific_check_failure_branches(tmp_path: Path) -> None:
    """Verify individual failure branches for unit tests, build check, and screenshots."""
    # 1. Unit tests with 'failures' word
    p1 = tmp_path / "p1"
    p1.mkdir()
    (p1 / "git-diff.patch").write_text("patch", encoding="utf-8")
    (p1 / "unit-test-results.txt").write_text("10 passed, 2 failures in 0.1s", encoding="utf-8")
    (p1 / "build-check.txt").write_text("SyntaxError: bad syntax", encoding="utf-8")
    t1 = tmp_path / "t1.yaml"
    t1.write_text("id: T1\ntitle: T1\n", encoding="utf-8")
    b1 = inspect_proof_directory(t1, p1)
    checks1 = {c.check_id: c for c in b1.deterministic_checks}
    assert checks1["UNIT_TESTS_EXIT_ZERO"].passed is False
    assert checks1["BUILD_CHECK_CLEAN"].passed is False

    # 2. UI Specialist Gate missing desktop screenshot
    p2 = tmp_path / "p2"
    p2.mkdir()
    (p2 / "git-diff.patch").write_text("patch", encoding="utf-8")
    (p2 / "unit-test-results.txt").write_text("10 passed", encoding="utf-8")
    (p2 / "build-check.txt").write_text("clean", encoding="utf-8")
    (p2 / "ui-specialist-review.md").write_text("Verdict: APPROVED", encoding="utf-8")
    s2 = p2 / "screenshots"
    s2.mkdir()
    _make_png(s2 / "shot-tablet.png", 100, 100)
    _make_png(s2 / "shot-mobile-1.png", 100, 100)
    _make_png(s2 / "shot-mobile-2.png", 100, 100)
    t2 = tmp_path / "t2.yaml"
    t2.write_text("id: T2\ntitle: '[UI] UI T2'\ngates: [ui-specialist]\n", encoding="utf-8")
    b2 = inspect_proof_directory(t2, p2)
    c4 = next(c for c in b2.deterministic_checks if c.check_id == "UI_SPECIALIST_GATE")
    assert c4.passed is False
    assert "desktop" in c4.detail

    # 3. UI Specialist Gate missing tablet screenshot
    p3 = tmp_path / "p3"
    p3.mkdir()
    (p3 / "git-diff.patch").write_text("patch", encoding="utf-8")
    (p3 / "unit-test-results.txt").write_text("10 passed", encoding="utf-8")
    (p3 / "build-check.txt").write_text("clean", encoding="utf-8")
    (p3 / "ui-specialist-review.md").write_text("Verdict: APPROVED", encoding="utf-8")
    s3 = p3 / "screenshots"
    s3.mkdir()
    _make_png(s3 / "shot-desktop.png", 100, 100)
    _make_png(s3 / "shot-mobile-1.png", 100, 100)
    _make_png(s3 / "shot-mobile-2.png", 100, 100)
    b3 = inspect_proof_directory(t2, p3)
    c4_3 = next(c for c in b3.deterministic_checks if c.check_id == "UI_SPECIALIST_GATE")
    assert c4_3.passed is False
    assert "tablet" in c4_3.detail
