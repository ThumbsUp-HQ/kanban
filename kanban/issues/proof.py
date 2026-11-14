# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Verification proof model and path invariants for issue workflow (KB-P4-06)."""

from __future__ import annotations

import re
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "ARTIFACT_PATH_REGEX",
    "CI_RUN_URL_REGEX",
    "QA_DIR_REGEX",
    "RealityCheckerProof",
    "VerificationProof",
    "validate_proof_ticket_key",
]

QA_DIR_REGEX: Final[str] = r"^docs/qa/([A-Z][A-Z0-9]{1,9}-[0-9]{1,18})/?$"
ARTIFACT_PATH_REGEX: Final[str] = (
    r"^docs/qa/([A-Z][A-Z0-9]{1,9}-[0-9]{1,18})/([A-Za-z0-9._/-]{1,200})$"
)
CI_RUN_URL_REGEX: Final[str] = r"^https://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=]+$"

_QA_DIR_PAT: Final[re.Pattern[str]] = re.compile(QA_DIR_REGEX)
_ARTIFACT_PAT: Final[re.Pattern[str]] = re.compile(ARTIFACT_PATH_REGEX)


def _check_no_traversal(path: str) -> None:
    """Ensure path contains no directory traversal (..) or double slashes (//)."""
    if ".." in path:
        msg = f"Path '{path}' contains forbidden directory traversal '..'"
        raise ValueError(msg)
    if "//" in path:
        msg = f"Path '{path}' contains forbidden double slash '//'"
        raise ValueError(msg)


class RealityCheckerProof(BaseModel):
    """Reality-checker forensic report proof block."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["READY", "NEEDS_WORK"]
    grade: Annotated[str, Field(pattern=r"^[A-F]$")]
    report_path: Annotated[
        str,
        Field(pattern=r"^docs/qa/[A-Z][A-Z0-9]{1,9}-[0-9]{1,18}/[A-Za-z0-9._/-]{1,200}$"),
    ]

    @field_validator("report_path")
    @classmethod
    def _validate_report_path(cls, v: str) -> str:
        _check_no_traversal(v)
        return v


class VerificationProof(BaseModel):
    """Pydantic model representing structured forensic verification proof packet."""

    model_config = ConfigDict(extra="forbid")

    qa_dir: Annotated[str, Field(pattern=r"^docs/qa/[A-Z][A-Z0-9]{1,9}-[0-9]{1,18}/?$")]
    artifacts: Annotated[
        list[
            Annotated[
                str,
                Field(pattern=r"^docs/qa/[A-Z][A-Z0-9]{1,9}-[0-9]{1,18}/[A-Za-z0-9._/-]{1,200}$"),
            ]
        ],
        Field(max_length=50),
    ]
    reality_checker: RealityCheckerProof
    ci_run_url: Annotated[str, Field(pattern=CI_RUN_URL_REGEX)]

    @field_validator("qa_dir")
    @classmethod
    def _validate_qa_dir(cls, v: str) -> str:
        _check_no_traversal(v)
        return v

    @field_validator("artifacts")
    @classmethod
    def _validate_artifacts(cls, v: list[str]) -> list[str]:
        for item in v:
            _check_no_traversal(item)
        return v


def validate_proof_ticket_key(proof: VerificationProof, expected_ticket_key: str) -> None:
    """Assert all paths in verification proof target the exact issue key."""
    m_dir = _QA_DIR_PAT.match(proof.qa_dir)
    if not m_dir or m_dir.group(1) != expected_ticket_key:
        msg = f"qa_dir '{proof.qa_dir}' does not match expected ticket key '{expected_ticket_key}'"
        raise ValueError(msg)

    m_rep = _ARTIFACT_PAT.match(proof.reality_checker.report_path)
    if not m_rep or m_rep.group(1) != expected_ticket_key:
        msg = (
            f"report_path '{proof.reality_checker.report_path}' does not match "
            f"expected ticket key '{expected_ticket_key}'"
        )
        raise ValueError(msg)

    for item in proof.artifacts:
        m_art = _ARTIFACT_PAT.match(item)
        if not m_art or m_art.group(1) != expected_ticket_key:
            msg = f"artifact '{item}' does not match expected ticket key '{expected_ticket_key}'"
            raise ValueError(msg)
