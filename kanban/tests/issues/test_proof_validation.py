# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for reality-checker report validation and verification proof invariants (KAN-45)."""

from __future__ import annotations

import pytest

from kanban.issues.proof import validate_reality_checker_report


def _build_report(
    *,
    cert_verdict: str = "READY",
    cert_grade: str = "A",
    deployment_readiness: str = "READY",
    h2_order: list[str] | None = None,
) -> str:
    """Build canonical reality-checker report with configurable sections and verdicts."""
    sections = {
        "Reality Check Validation": "- Forensic check verified against real database.",
        "Complete System Evidence": "- Visual screenshots captured across viewports.",
        "Integration Testing Results": "- 100% automated test suites executed with 0 failures.",
        "Comprehensive Issue Assessment": "- Security invariants and policies validated.",
        "Realistic Quality Certification": f"- Verdict: {cert_verdict}\n- Grade: {cert_grade}",
        "Deployment Readiness Assessment": f"- Deployment Status: {deployment_readiness}",
    }

    order = h2_order or [
        "Reality Check Validation",
        "Complete System Evidence",
        "Integration Testing Results",
        "Comprehensive Issue Assessment",
        "Realistic Quality Certification",
        "Deployment Readiness Assessment",
    ]

    body_parts = ["# Integration Agent Reality-Based Report\n"]
    body_parts.extend(f"## {title}\n{sections[title]}\n" for title in order)
    return "\n".join(body_parts)


def test_validate_reality_checker_report_positive() -> None:
    """Canonical report with correct H2 ordering and READY / A succeeds."""
    report = _build_report()
    validate_reality_checker_report(report)
    validate_reality_checker_report(report, require_ready=True)


def test_validate_reality_checker_report_rejects_out_of_order_headings() -> None:
    """Report with out-of-order canonical H2 sections is rejected."""
    bad_order = [
        "Complete System Evidence",  # Swapped with Reality Check Validation
        "Reality Check Validation",
        "Integration Testing Results",
        "Comprehensive Issue Assessment",
        "Realistic Quality Certification",
        "Deployment Readiness Assessment",
    ]
    report = _build_report(h2_order=bad_order)
    with pytest.raises(ValueError, match="out of order"):
        validate_reality_checker_report(report)


def test_validate_reality_checker_report_rejects_needs_work_when_ready_omitted() -> None:
    """Report containing NEEDS WORK is rejected even when READY is omitted."""
    report = _build_report(
        cert_verdict="NEEDS WORK", cert_grade="C+", deployment_readiness="NEEDS WORK"
    )
    with pytest.raises(ValueError, match="Contradiction marker 'NEEDS WORK'"):
        validate_reality_checker_report(report)
    with pytest.raises(ValueError, match="Contradiction marker 'NEEDS WORK'"):
        validate_reality_checker_report(report, require_ready=True)


def test_validate_reality_checker_report_rejects_failed_marker() -> None:
    """Report containing FAILED is rejected immediately."""
    report = _build_report(cert_verdict="FAILED", cert_grade="F", deployment_readiness="FAILED")
    with pytest.raises(ValueError, match="Contradiction marker 'FAILED'"):
        validate_reality_checker_report(report)


def test_validate_reality_checker_report_require_ready_rejects_non_ready() -> None:
    """When require_ready=True, summary_markdown must explicitly certify READY with grade A."""
    report = _build_report(
        cert_verdict="IN PROGRESS", cert_grade="B", deployment_readiness="PENDING"
    )
    # require_ready=False allows if no contradiction markers
    validate_reality_checker_report(report, require_ready=False)
    # require_ready=True rejects because READY/A is missing
    with pytest.raises(ValueError, match="must certify READY with grade A"):
        validate_reality_checker_report(report, require_ready=True)
