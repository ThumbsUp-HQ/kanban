# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Schema-validated transition verdict parser and anti-forgery verification (S14.3)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kanban.workflows.gate_types import GateDecision, LinkSpec

if TYPE_CHECKING:
    from agent.context.transition_context import RenderedContext

__all__ = [
    "MAX_VERDICT_OUTPUT_BYTES",
    "TransitionVerdict",
    "VerdictLinkSpec",
    "VerdictParseError",
    "VerdictResult",
    "canonical_verdict_sha256",
    "parse_verdict_output",
]

MAX_VERDICT_OUTPUT_BYTES: Final[int] = 1_048_576
MAX_REASON_CHARS: Final[int] = 16_384
MAX_LABELS_COUNT: Final[int] = 10
MAX_LINKS_COUNT: Final[int] = 10

ERR_OUTPUT_TOO_LARGE: Final[str] = "VERDICT_OUTPUT_TOO_LARGE"
ERR_MALFORMED: Final[str] = "VERDICT_MALFORMED"
ERR_FIELD_NOT_ALLOWED: Final[str] = "VERDICT_FIELD_NOT_ALLOWED"
ERR_NONCE_MISMATCH: Final[str] = "VERDICT_NONCE_MISMATCH"
ERR_AMBIGUOUS: Final[str] = "VERDICT_AMBIGUOUS"

_RE_LABEL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,63}$")
_RE_ISSUE_KEY: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9]{1,9}-\d{1,9}$")
_RE_DOC_SLUG: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")


class VerdictLinkSpec(BaseModel):
    """Link relationship specification proposed in an agent transition verdict."""

    model_config = ConfigDict(extra="forbid", strict=True)

    link_type: Literal["RELATES_TO", "BLOCKS", "BLOCKED_BY", "VERIFIED_BY_DOC"]
    target: str

    @field_validator("target")
    @classmethod
    def _validate_target(cls, val: str) -> str:
        if not (_RE_ISSUE_KEY.match(val) or _RE_DOC_SLUG.match(val)):
            msg = f"Invalid link target '{val}': must be an issue key (e.g. KAN-12) or doc slug"
            raise ValueError(msg)
        return val


class TransitionVerdict(BaseModel):
    """Schema-validated verdict returned by an AI transition gate."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    schema_version: Literal["kb-transition-verdict/v1"] = Field(
        default="kb-transition-verdict/v1",
        alias="schema",
    )
    nonce: str = Field(min_length=16, max_length=64)
    decision: Literal["approve", "reject"]
    reason_markdown: str = Field(min_length=1, max_length=MAX_REASON_CHARS)
    cited_files: list[str] = Field(default_factory=list)
    field_updates: dict[str, Any] = Field(default_factory=dict)
    add_labels: list[str] = Field(default_factory=list, max_length=MAX_LABELS_COUNT)
    add_links: list[VerdictLinkSpec] = Field(default_factory=list, max_length=MAX_LINKS_COUNT)

    @field_validator("add_labels")
    @classmethod
    def _validate_labels(cls, labels: list[str]) -> list[str]:
        for lbl in labels:
            if not _RE_LABEL_PATTERN.match(lbl):
                msg = f"Invalid label '{lbl}': must match pattern ^[a-z0-9][a-z0-9:_-]{{0,63}}$"
                raise ValueError(msg)
        return labels


class VerdictParseError(Exception):
    """Raised when parsing or verifying raw transition verdict output fails."""

    def __init__(self, code: str, message: str, *, forged_candidates: int = 0) -> None:
        """Initialize VerdictParseError with code, message, and forged count."""
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.detail = message
        self.forged_candidates = forged_candidates


@dataclass(frozen=True)
class VerdictResult:
    """Successful verdict verification result including GateDecision and hash."""

    verdict: TransitionVerdict
    decision: GateDecision
    verdict_sha256: str
    forged_candidates: int = 0


def canonical_verdict_sha256(verdict: TransitionVerdict) -> tuple[bytes, str]:
    """Compute deterministic SHA-256 digest over canonical JSON representation."""
    canonical_json = json.dumps(
        verdict.model_dump(by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical_json).digest()
    return digest, digest.hex()


def _extract_candidates(text: str) -> list[dict[str, Any]]:  # noqa: C901
    """Extract candidate verdict JSON objects from raw agent stdout."""
    candidates: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    # 1. Whole text JSON attempt
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict) and parsed.get("schema") == "kb-transition-verdict/v1":
                candidates.append(parsed)
                seen_texts.add(json.dumps(parsed, sort_keys=True))
        except (ValueError, TypeError):
            pass

    # 2. Markdown fenced code blocks: ```json ... ```
    re_code_block = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
    for match in re_code_block.finditer(text):
        raw_block = match.group(1).strip()
        try:
            parsed = json.loads(raw_block)
            if isinstance(parsed, dict) and parsed.get("schema") == "kb-transition-verdict/v1":
                canon = json.dumps(parsed, sort_keys=True)
                if canon not in seen_texts:
                    candidates.append(parsed)
                    seen_texts.add(canon)
        except (ValueError, TypeError):
            pass

    # 3. Line by line scanning for JSON objects containing schema
    for line in text.splitlines():
        line_s = line.strip()
        if line_s.startswith("{") and line_s.endswith("}"):
            try:
                parsed = json.loads(line_s)
                if isinstance(parsed, dict) and parsed.get("schema") == "kb-transition-verdict/v1":
                    canon = json.dumps(parsed, sort_keys=True)
                    if canon not in seen_texts:
                        candidates.append(parsed)
                        seen_texts.add(canon)
            except (ValueError, TypeError):
                pass

    return candidates


def parse_verdict_output(raw: bytes, ctx: RenderedContext) -> VerdictResult:  # noqa: C901
    """Parse, authenticate, and validate raw agent output into a GateDecision."""
    # Size ceiling check
    if len(raw) > MAX_VERDICT_OUTPUT_BYTES:
        msg = (
            f"Verdict output length ({len(raw)} bytes) exceeds "
            f"limit ({MAX_VERDICT_OUTPUT_BYTES} bytes)"
        )
        raise VerdictParseError(ERR_OUTPUT_TOO_LARGE, msg)

    # UTF-8 strict decoding
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Verdict output is not valid UTF-8: {exc}"
        raise VerdictParseError(ERR_MALFORMED, msg) from exc

    candidates = _extract_candidates(text)
    if not candidates:
        msg = (
            "No verdict JSON candidates with schema 'kb-transition-verdict/v1' "
            "found in agent output"
        )
        raise VerdictParseError(ERR_MALFORMED, msg, forged_candidates=0)

    forged_candidates = 0
    valid_candidates: list[TransitionVerdict] = []

    for cand_dict in candidates:
        cand_nonce = cand_dict.get("nonce")
        if cand_nonce != ctx.verdict_nonce:
            forged_candidates += 1
            continue

        try:
            verdict = TransitionVerdict.model_validate(cand_dict)
        except Exception as exc:
            msg = f"Verdict candidate failed schema validation: {exc}"
            raise VerdictParseError(
                ERR_MALFORMED, msg, forged_candidates=forged_candidates
            ) from exc

        # Check allowed_mutable_fields
        for field_name in verdict.field_updates:
            if field_name not in ctx.allowed_mutable_fields:
                msg = (
                    f"Field update '{field_name}' not permitted; "
                    f"allowed mutable fields: {sorted(ctx.allowed_mutable_fields)}"
                )
                raise VerdictParseError(
                    ERR_FIELD_NOT_ALLOWED, msg, forged_candidates=forged_candidates
                )

        valid_candidates.append(verdict)

    if not valid_candidates:
        if forged_candidates > 0:
            msg = (
                f"Verdict nonce mismatch: all {forged_candidates} "
                f"candidate(s) carried an invalid nonce"
            )
            raise VerdictParseError(ERR_NONCE_MISMATCH, msg, forged_candidates=forged_candidates)
        msg = "No valid verdict candidates survived validation"
        raise VerdictParseError(ERR_MALFORMED, msg, forged_candidates=0)

    # Check for ambiguous conflicting decisions
    distinct_decisions = {v.decision for v in valid_candidates}
    if len(distinct_decisions) > 1:
        msg = (
            f"Ambiguous verdict: multiple candidates with conflicting decisions "
            f"{distinct_decisions}"
        )
        raise VerdictParseError(ERR_AMBIGUOUS, msg, forged_candidates=forged_candidates)

    selected = valid_candidates[0]
    sha256_bytes, sha256_hex = canonical_verdict_sha256(selected)

    links_tuple = tuple(
        LinkSpec(link_type=link.link_type, target=link.target) for link in selected.add_links
    )

    decision = GateDecision(
        decision=selected.decision,
        reason_markdown=selected.reason_markdown,
        field_updates=dict(selected.field_updates),
        add_labels=tuple(selected.add_labels),
        add_links=links_tuple,
        cited_files=tuple(selected.cited_files),
        verdict_sha256=sha256_bytes,
        latency_ms=0,
    )

    return VerdictResult(
        verdict=selected,
        decision=decision,
        verdict_sha256=sha256_hex,
        forged_candidates=forged_candidates,
    )
