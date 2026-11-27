# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Verification proof model and path invariants for MCP agent workflows (KB-P4-06, KAN-45)."""

from __future__ import annotations

from typing import Any, Final

from kanban.issues.proof import (
    ARTIFACT_PATH_REGEX,
    CI_RUN_URL_REGEX,
    QA_DIR_REGEX,
    REPORT_PATH_REGEX,
    RealityCheckerProof,
    VerificationProof,
    validate_ci_run_url,
    validate_proof_ticket_key,
    validate_reality_checker_report,
)

__all__ = [
    "ARTIFACT_PATH_REGEX",
    "CI_RUN_URL_REGEX",
    "QA_DIR_REGEX",
    "REPORT_PATH_REGEX",
    "VERIFICATION_PROOF_SCHEMA",
    "RealityCheckerProof",
    "VerificationProof",
    "validate_ci_run_url",
    "validate_proof_ticket_key",
    "validate_reality_checker_report",
]

VERIFICATION_PROOF_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "description": "Proof packet",
    "properties": {
        "qa_dir": {
            "type": "string",
            "pattern": r"^docs/qa/[A-Z][A-Z0-9]{1,9}-[0-9]{1,18}/?$",
        },
        "artifacts": {
            "type": "array",
            "minItems": 1,
            "maxItems": 50,
            "items": {
                "type": "string",
                "pattern": r"^docs/qa/[A-Z][A-Z0-9]{1,9}-[0-9]{1,18}/[A-Za-z0-9._/-]{1,200}$",
            },
        },
        "reality_checker": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["READY", "NEEDS_WORK"],
                },
                "grade": {
                    "type": "string",
                    "pattern": r"^[A-F][+-]?$",
                },
                "report_path": {
                    "type": "string",
                    "pattern": (
                        r"^docs/qa/[A-Z][A-Z0-9]{1,9}-[0-9]{1,18}/reality-checker-report\.md$"
                    ),
                },
            },
            "required": ["verdict", "grade", "report_path"],
            "additionalProperties": False,
        },
        "ci_run_url": {
            "type": "string",
            "maxLength": 2048,
        },
    },
    "required": ["qa_dir", "artifacts", "reality_checker", "ci_run_url"],
    "additionalProperties": False,
}
