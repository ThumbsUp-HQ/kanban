# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for VerificationProof and RealityCheckerProof models (KB-P4-06)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from kanban.issues.proof import (
    RealityCheckerProof,
    VerificationProof,
    validate_proof_ticket_key,
)


def _valid_proof_dict(key: str = "KAN-142") -> dict[str, Any]:
    return {
        "qa_dir": f"docs/qa/{key}/",
        "artifacts": [
            f"docs/qa/{key}/git-diff.patch",
            f"docs/qa/{key}/unit-test-results.txt",
        ],
        "reality_checker": {
            "verdict": "READY",
            "grade": "A",
            "report_path": f"docs/qa/{key}/reality-checker-report.md",
        },
        "ci_run_url": "https://dash.hackedyour.info/runs/1234",
    }


def test_proof_positive_validation() -> None:
    """Validate that positive verification proof parses cleanly and matches ticket key."""
    data = _valid_proof_dict("KAN-142")
    proof = VerificationProof.model_validate(data)
    assert proof.qa_dir == "docs/qa/KAN-142/"
    assert proof.reality_checker.verdict == "READY"
    assert proof.reality_checker.grade == "A"
    validate_proof_ticket_key(proof, "KAN-142")


def test_proof_traversal_double_slash_rejected() -> None:
    """Verify that double slashes are rejected across all paths in verification proof."""
    # Double slash in artifacts
    data = _valid_proof_dict("KAN-142")
    data["artifacts"] = ["docs/qa/KAN-142/dir//git-diff.patch"]
    with pytest.raises(ValidationError, match="forbidden double slash"):
        VerificationProof.model_validate(data)

    # Double slash in report_path
    data2 = _valid_proof_dict("KAN-142")
    rc_data = dict(data2["reality_checker"])
    rc_data["report_path"] = "docs/qa/KAN-142/sub//report.md"
    data2["reality_checker"] = rc_data
    with pytest.raises(ValidationError, match="forbidden double slash"):
        VerificationProof.model_validate(data2)


def test_proof_directory_traversal_dot_dot_rejected() -> None:
    """Verify that directory traversal (..) is rejected in verification proof."""
    data = _valid_proof_dict("KAN-142")
    data["artifacts"] = ["docs/qa/KAN-142/sub/../git-diff.patch"]
    with pytest.raises(ValidationError, match="forbidden directory traversal"):
        VerificationProof.model_validate(data)


def test_proof_ticket_key_mismatch_detection() -> None:
    """Verify that mismatched ticket keys in qa_dir, report_path, or artifacts raise error."""
    data = _valid_proof_dict("KAN-142")
    proof = VerificationProof.model_validate(data)

    # qa_dir mismatch
    with pytest.raises(ValueError, match="qa_dir 'docs/qa/KAN-142/' does not match"):
        validate_proof_ticket_key(proof, "KAN-999")

    # report_path mismatch
    bad_rep_data = _valid_proof_dict("KAN-142")
    bad_rep_rc = dict(bad_rep_data["reality_checker"])
    bad_rep_rc["report_path"] = "docs/qa/KAN-999/reality-checker-report.md"
    bad_rep_data["reality_checker"] = bad_rep_rc
    proof_bad_rep = VerificationProof.model_validate(bad_rep_data)
    with pytest.raises(
        ValueError,
        match=r"report_path '.*' does not match expected ticket key 'KAN-142'",
    ):
        validate_proof_ticket_key(proof_bad_rep, "KAN-142")

    # artifact mismatch
    bad_art_data = _valid_proof_dict("KAN-142")
    bad_art_data["artifacts"] = ["docs/qa/KAN-999/git-diff.patch"]
    proof_bad_art = VerificationProof.model_validate(bad_art_data)
    with pytest.raises(
        ValueError,
        match=r"artifact '.*' does not match expected ticket key 'KAN-142'",
    ):
        validate_proof_ticket_key(proof_bad_art, "KAN-142")


def test_reality_checker_grade_and_verdict_bounds() -> None:
    """Verify that reality-checker grade and verdict boundaries are enforced by enum/regex."""
    with pytest.raises(ValidationError):
        RealityCheckerProof.model_validate(
            {
                "verdict": "INVALID_VERDICT",
                "grade": "A",
                "report_path": "docs/qa/KAN-142/report.md",
            }
        )

    with pytest.raises(ValidationError):
        RealityCheckerProof.model_validate(
            {
                "verdict": "READY",
                "grade": "Z",
                "report_path": "docs/qa/KAN-142/report.md",
            }
        )
