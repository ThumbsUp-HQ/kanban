# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Verification proof model and path invariants for MCP agent workflows (KB-P4-06)."""

from __future__ import annotations

from typing import Any, Final

from kanban.issues.proof import (
    ARTIFACT_PATH_REGEX,
    CI_RUN_URL_REGEX,
    QA_DIR_REGEX,
    RealityCheckerProof,
    VerificationProof,
    validate_proof_ticket_key,
)

__all__ = [
    "ARTIFACT_PATH_REGEX",
    "CI_RUN_URL_REGEX",
    "QA_DIR_REGEX",
    "VERIFICATION_PROOF_SCHEMA",
    "RealityCheckerProof",
    "VerificationProof",
    "validate_proof_ticket_key",
]

VERIFICATION_PROOF_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "description": "Proof packet",
    "properties": {
        "qa_dir": {
            "type": "string",
            "description": "QA directory path",
        },
        "artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "QA artifact paths",
        },
        "reality_checker": {
            "type": "object",
            "description": "Reality-checker audit verdict",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["READY", "NEEDS_WORK"],
                },
                "grade": {
                    "type": "string",
                    "pattern": "^[A-F]$",
                },
                "report_path": {
                    "type": "string",
                    "description": "Report path",
                },
            },
            "required": ["verdict", "grade", "report_path"],
            "additionalProperties": False,
        },
        "ci_run_url": {
            "type": "string",
            "description": "CI run URL",
        },
    },
    "required": ["qa_dir", "artifacts", "reality_checker", "ci_run_url"],
    "additionalProperties": False,
}
