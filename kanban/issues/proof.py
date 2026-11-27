# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Verification proof model and path invariants for issue workflow (KB-P4-06, KAN-45)."""

from __future__ import annotations

import re
import unicodedata
import urllib.parse
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "ARTIFACT_PATH_REGEX",
    "CI_RUN_URL_REGEX",
    "QA_DIR_REGEX",
    "REPORT_PATH_REGEX",
    "RealityCheckerProof",
    "VerificationProof",
    "validate_ci_run_url",
    "validate_ci_run_url_live",
    "validate_proof_ticket_key",
    "validate_reality_checker_report",
]

QA_DIR_REGEX: Final[str] = r"\Adocs/qa/([A-Z][A-Z0-9]{1,9}-[0-9]{1,18})/?\Z"
ARTIFACT_PATH_REGEX: Final[str] = (
    r"\Adocs/qa/([A-Z][A-Z0-9]{1,9}-[0-9]{1,18})/([A-Za-z0-9._/-]{1,200})\Z"
)
REPORT_PATH_REGEX: Final[str] = (
    r"\Adocs/qa/([A-Z][A-Z0-9]{1,9}-[0-9]{1,18})/reality-checker-report\.md\Z"
)
CI_RUN_URL_REGEX: Final[str] = r"\Ahttps://[A-Za-z0-9\-._~:/?#$!&*+,;=]{1,2048}\Z"

_QA_DIR_PAT: Final[re.Pattern[str]] = re.compile(QA_DIR_REGEX)
_ARTIFACT_PAT: Final[re.Pattern[str]] = re.compile(ARTIFACT_PATH_REGEX)
_REPORT_PAT: Final[re.Pattern[str]] = re.compile(REPORT_PATH_REGEX)

_FORBIDDEN_URL_CHARS: Final[set[str]] = {
    "[",
    "]",
    "(",
    ")",
    "<",
    ">",
    '"',
    "'",
    "`",
    "|",
    "\n",
    "\r",
    "\t",
    " ",
}


def _check_no_traversal(path: str) -> None:
    """Ensure path contains no directory traversal (..) or double slashes (//)."""
    if ".." in path:
        msg = f"Path '{path}' contains forbidden directory traversal '..'"
        raise ValueError(msg)
    if "//" in path:
        msg = f"Path '{path}' contains forbidden double slash '//'"
        raise ValueError(msg)


MAX_CI_RUN_URL_LEN: Final[int] = 2048
_SURROGATE_MIN: Final[int] = 0xD800
_SURROGATE_MAX: Final[int] = 0xDFFF


def validate_ci_run_url(v: str) -> str:
    """Validate ci_run_url via urllib.parse.urlsplit ensuring safe https and no credentials."""
    if len(v) < 1 or len(v) > MAX_CI_RUN_URL_LEN:
        msg = f"ci_run_url length ({len(v)}) must be between 1 and {MAX_CI_RUN_URL_LEN} characters"
        raise ValueError(msg)
    if any(ch in _FORBIDDEN_URL_CHARS for ch in v):
        msg = f"ci_run_url '{v}' contains forbidden characters or Markdown delimiters"
        raise ValueError(msg)

    parsed = urllib.parse.urlsplit(v)
    if parsed.scheme != "https":
        msg = f"ci_run_url scheme must be 'https', got '{parsed.scheme}'"
        raise ValueError(msg)
    if not parsed.netloc or not parsed.hostname:
        msg = "ci_run_url must contain a non-empty host"
        raise ValueError(msg)
    if parsed.username or parsed.password or "@" in parsed.netloc:
        msg = "ci_run_url must not contain user credentials"
        raise ValueError(msg)

    return v


async def validate_ci_run_url_live(
    v: str,
    head_sha: str,
    *,
    air_gap_mode: bool = False,
    auth_token: str | None = None,
) -> str:
    """Validate ci_run_url syntax and verify live passing CI check-run status."""
    clean_url = validate_ci_run_url(v)
    from kanban.workflows.attestation_gate import verify_live_ci_check_run  # noqa: PLC0415

    res = await verify_live_ci_check_run(
        clean_url,
        head_sha,
        air_gap_mode=air_gap_mode,
        auth_token=auth_token,
    )
    if not res.verified:
        msg = f"Live CI check-run verification failed: {res.error_detail}"
        raise ValueError(msg)
    return clean_url


def _pydantic_pattern(rx: str) -> str:
    r"""Convert Python \Z anchor to Rust-compatible \z for Pydantic validation."""
    return rx.replace(r"\Z", r"\z")


class RealityCheckerProof(BaseModel):
    """Reality-checker forensic report proof block."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["READY", "NEEDS_WORK"]
    grade: Annotated[str, Field(pattern=r"^[A-F][+-]?$")]
    report_path: Annotated[
        str,
        Field(pattern=_pydantic_pattern(REPORT_PATH_REGEX)),
    ]

    @field_validator("report_path", mode="before")
    @classmethod
    def _pre_validate_report_path(cls, v: object) -> object:
        if isinstance(v, str) and "//" in v:
            msg = f"Path '{v}' contains forbidden double slash '//'"
            raise ValueError(msg)
        return v

    @field_validator("report_path")
    @classmethod
    def _validate_report_path(cls, v: str) -> str:
        _check_no_traversal(v)
        if not _REPORT_PAT.match(v):
            msg = f"report_path '{v}' does not match canonical reality-checker-report.md path"
            raise ValueError(msg)
        return v


class VerificationProof(BaseModel):
    """Pydantic model representing structured forensic verification proof packet."""

    model_config = ConfigDict(extra="forbid")

    qa_dir: Annotated[str, Field(pattern=_pydantic_pattern(QA_DIR_REGEX))]
    artifacts: Annotated[
        list[
            Annotated[
                str,
                Field(pattern=_pydantic_pattern(ARTIFACT_PATH_REGEX)),
            ]
        ],
        Field(min_length=1, max_length=50),
    ]
    reality_checker: RealityCheckerProof
    ci_run_url: Annotated[str, Field(pattern=_pydantic_pattern(CI_RUN_URL_REGEX))]

    @field_validator("qa_dir")
    @classmethod
    def _validate_qa_dir(cls, v: str) -> str:
        _check_no_traversal(v)
        return v

    @field_validator("artifacts")
    @classmethod
    def _validate_artifacts(cls, v: list[str]) -> list[str]:
        if len(v) < 1:
            msg = "VerificationProof.artifacts must contain at least 1 artifact"
            raise ValueError(msg)
        for item in v:
            _check_no_traversal(item)
            if item.endswith("/"):
                msg = f"Artifact path '{item}' cannot end with a trailing slash"
                raise ValueError(msg)
            segments = item.split("/")
            if any(seg in (".", "..") for seg in segments):
                msg = f"Artifact path '{item}' contains forbidden dot segments"
                raise ValueError(msg)
        return v

    @field_validator("ci_run_url")
    @classmethod
    def _validate_ci_run_url(cls, v: str) -> str:
        return validate_ci_run_url(v)


def validate_proof_ticket_key(proof: VerificationProof, expected_ticket_key: str) -> None:
    """Assert all paths in verification proof target the exact issue key."""
    m_dir = _QA_DIR_PAT.match(proof.qa_dir)
    if not m_dir or m_dir.group(1) != expected_ticket_key:
        msg = f"qa_dir '{proof.qa_dir}' does not match expected ticket key '{expected_ticket_key}'"
        raise ValueError(msg)

    m_rep = _REPORT_PAT.match(proof.reality_checker.report_path)
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


def validate_reality_checker_report(  # noqa: C901, PLR0912, PLR0915
    markdown: str,
    *,
    require_ready: bool = False,
) -> None:
    """Validate reality-checker report structure in deterministic O(N) linear time."""
    if not markdown or not markdown.strip():
        msg = "Reality-checker report markdown cannot be empty"
        raise ValueError(msg)

    # 1. Reject UTF-16 lone surrogates (0xD800..0xDFFF)
    for idx, ch in enumerate(markdown):
        cp = ord(ch)
        if _SURROGATE_MIN <= cp <= _SURROGATE_MAX:
            msg = f"Invalid UTF-16 lone surrogate character at offset {idx}: U+{cp:04X}"
            raise ValueError(msg)

    # 2. Parse lines with NFKC normalization, skipping code blocks and HTML comments
    lines = markdown.splitlines()
    in_code_block: str | None = None
    in_html_comment = False

    has_h1 = False
    canonical_h2_order: Final[list[str]] = [
        "Reality Check Validation",
        "Complete System Evidence",
        "Integration Testing Results",
        "Comprehensive Issue Assessment",
        "Realistic Quality Certification",
        "Deployment Readiness Assessment",
    ]
    sections_found: dict[str, list[str]] = {name: [] for name in canonical_h2_order}
    h2_order_seen: list[str] = []
    current_section: str | None = None

    for raw_line in lines:
        line = unicodedata.normalize("NFKC", raw_line)

        # Handle HTML comment state spanning lines
        if in_html_comment:
            end_comment = line.find("-->")
            if end_comment != -1:
                line = line[end_comment + 3 :]
                in_html_comment = False
            else:
                continue

        # Strip intra-line HTML comments
        while "<!--" in line:
            start_idx = line.find("<!--")
            end_idx = line.find("-->", start_idx + 4)
            if end_idx != -1:
                line = line[:start_idx] + line[end_idx + 3 :]
            else:
                line = line[:start_idx]
                in_html_comment = True
                break

        stripped = line.strip()
        if not stripped:
            continue

        # Handle fenced code blocks
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            if in_code_block == fence:
                in_code_block = None
                continue
            if in_code_block is None:
                in_code_block = fence
                continue

        if in_code_block is not None:
            continue

        # Check H1 header
        if stripped.startswith("# ") and not stripped.startswith("## "):
            h1_text = stripped[2:].strip()
            if h1_text == "Integration Agent Reality-Based Report":
                has_h1 = True
                current_section = None
                continue

        # Check H2 headers
        if stripped.startswith("## "):
            h2_text = stripped[3:].strip()
            matched_name: str | None = None
            for c_name in canonical_h2_order:
                if c_name in h2_text:
                    matched_name = c_name
                    break
            if matched_name is not None:
                h2_order_seen.append(matched_name)
            current_section = matched_name
            continue

        if current_section is not None:
            sections_found[current_section].append(stripped)

    if not has_h1:
        msg = "Missing required '# Integration Agent Reality-Based Report' H1 header"
        raise ValueError(msg)

    # 3. Verify all 6 H2 sections exist with non-empty body lines
    for c_name in canonical_h2_order:
        body_lines = sections_found[c_name]
        if not body_lines:
            msg = f"Missing required canonical section '## {c_name}' or section body is empty"
            raise ValueError(msg)

    # 4. Verify canonical relative order
    if h2_order_seen != canonical_h2_order:
        msg = (
            f"Canonical H2 sections are out of order or repeated: expected {canonical_h2_order}, "
            f"got {h2_order_seen}"
        )
        raise ValueError(msg)

    # 5. Check anti-fantasy contradiction markers inside certification/readiness sections
    cert_body = "\n".join(sections_found["Realistic Quality Certification"])
    ready_body = "\n".join(sections_found["Deployment Readiness Assessment"])
    combined_check = f"{cert_body}\n{ready_body}"

    contradiction_markers: Final[list[str]] = ["NEEDS WORK", "NEEDS_WORK", "FAILED"]
    for marker in contradiction_markers:
        pat = rf"\b{re.escape(marker)}\b"
        if re.search(pat, combined_check, re.IGNORECASE):
            msg = (
                f"Contradiction marker '{marker}' found in certification or deployment "
                "readiness assessment"
            )
            raise ValueError(msg)

    has_ready_keyword = bool(re.search(r"\bREADY\b", combined_check))
    has_grade_a = bool(re.search(r"\bA\b", cert_body) or "A-" in cert_body or "A+" in cert_body)
    claims_ready = has_ready_keyword and has_grade_a
    if require_ready and not claims_ready:
        msg = (
            "Reality-checker report summary_markdown must certify READY with grade A "
            "in realistic quality certification or deployment readiness assessment"
        )
        raise ValueError(msg)
