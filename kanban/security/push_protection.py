# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Synchronous pre-persistence secret push-protection and Shannon entropy scanner (KB-SEC-SCRUB-01).

Scans untrusted prose and entity write payloads synchronously before PostgreSQL persistence,
search_tsv indexing, vector embedding, or activity ledger commits. Detects deterministic
cloud credentials, private keys, PATs, DSN passwords, and high-entropy secret assignments
while strictly exempting UUIDs, Git commit SHAs, SHA digests, base-62 ranks, and code identifiers.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from kanban.api.problems import ProblemException
from kanban.security.scrubber import (
    _RE_API_KEY,
    _RE_AQ_KEY,
    _RE_AWS_ACCESS_KEY,
    _RE_BEARER_TOKEN,
    _RE_GITHUB_TOKEN,
    _RE_GITLAB_TOKEN,
    _RE_GOOGLE_KEY,
    _RE_JWT,
    _RE_KANBAN_KEY,
    _RE_SLACK_TOKEN,
    _RE_STRIPE_KEY,
    SecretKind,
    _scan_pem_private_keys,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_PUSH_PROTECTION_CODE",
    "PushProtectionMode",
    "SecretFinding",
    "calculate_shannon_entropy",
    "enforce_secret_push_protection",
    "is_exempt_token",
    "mask_fingerprint",
    "redact_text_findings",
    "scan_text_for_secrets",
]

DEFAULT_PUSH_PROTECTION_CODE: Final[str] = "SECRET_DETECTED_IN_PAYLOAD"
PUSH_PROTECTION_CODE_ALIAS: Final[str] = "SECRET_DETECTED_PUSH_PROTECTION"

# Regexes for structured key-value assignment scanning
_RE_KEY_VALUE_ASSIGNMENT: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?P<key>PASSWORD|PASSWD|PASS|SECRET|SECRET_KEY|TOKEN|API_KEY|API_SECRET|"
    r"AUTH_TOKEN|PRIVATE_KEY|ACCESS_TOKEN|STRIPE_SECRET_KEY|WEBHOOK_SECRET)\s*[:=]\s*"
    r"[\"']?(?P<val>[^\s\"';]{8,256})[\"']?"
)

# Connection URI regex capturing protocol, user, password, and host
_RE_CONNECTION_URI: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b([a-zA-Z][a-zA-Z0-9+.-]+://[^:\s@]*:)(.+)@((?:localhost|[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*|\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?(?:/[^\s]*)?)"
)
_RE_REDIS_URI: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(redis(?:s)?://:)(.+)@((?:localhost|[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*|\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?(?:/[^\s]*)?)"
)

# Exemption matchers
_RE_UUID: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_RE_HEX_DIGEST: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{32,128}$")
_RE_BASE62_RANK: Final[re.Pattern[str]] = re.compile(r"^0\|[0-9a-zA-Z:]+$")
_RE_CANDIDATE_TOKEN: Final[re.Pattern[str]] = re.compile(r"\b[A-Za-z0-9+/=_-]{16,256}\b")

_MIN_SECRET_LENGTH: Final[int] = 8
_MIN_ENTROPY_ASSIGNMENT: Final[float] = 3.2
_MIN_CANDIDATE_TOKEN_LENGTH: Final[int] = 20
_MIN_SHANNON_ENTROPY: Final[float] = 4.5

_EXEMPT_WORDS: Final[frozenset[str]] = frozenset(
    {
        "placeholder",
        "changeme",
        "change_me",
        "example",
        "none",
        "null",
        "true",
        "false",
        "undefined",
        "dummy",
        "test",
        "todo",
        "password",
        "secret",
        "token",
        "value",
        "string",
    }
)


class PushProtectionMode(StrEnum):
    """Enforcement policy mode for secret push protection."""

    BLOCK = "block"
    REDACT_ON_WRITE = "redact_on_write"


@dataclass(frozen=True, slots=True)
class SecretFinding:
    """Diagnostic location and fingerprint of detected secret material."""

    rule_id: str
    kind: SecretKind
    start: int
    end: int
    line: int
    fingerprint: str
    secret_value: str = ""  # Retained ephemerally for redaction; never echoed


def calculate_shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string in bits per character."""
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for c in s:
        counts[c] = counts.get(c, 0) + 1
    length = len(s)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def mask_fingerprint(secret: str) -> str:
    """Mask secret value retaining short prefix and suffix without revealing plaintext."""
    if not secret:
        return ""
    if len(secret) <= _MIN_SECRET_LENGTH:
        return "*" * len(secret)

    known_prefixes = (
        "ghp_",
        "gho_",
        "ghu_",
        "ghs_",
        "ghr_",
        "github_pat_",
        "glpat-",
        "xoxb-",
        "xoxp-",
        "xoxa-",
        "xoxr-",
        "xoxs-",
        "AIza",
        "sk-proj-",
        "sk-ant-api",
        "sk-live-",
        "sk-test-",
        "sk-",
        "rk_live_",
        "rk_test_",
        "kb_pat_",
        "kb_eat_",
        "kb_agt_",
        "kb_runner_",
        "kb_",
        "AKIA",
        "ASIA",
    )
    prefix_len = 4
    for p in known_prefixes:
        if secret.startswith(p):
            prefix_len = len(p)
            break

    suffix_len = 4
    if len(secret) <= prefix_len + suffix_len:
        safe_p = min(prefix_len, 4)
        return f"{secret[:safe_p]}...{secret[-2:]}"
    return f"{secret[:prefix_len]}...{secret[-suffix_len:]}"


def is_exempt_token(token: str) -> bool:
    """Determine whether a candidate string is an exempt technical value."""
    if not token or len(token) < _MIN_SECRET_LENGTH:
        return True
    if (
        _RE_UUID.match(token)
        or _RE_HEX_DIGEST.match(token)
        or _RE_BASE62_RANK.match(token)
        or (token.startswith(("http://", "https://", "/")) and "@" not in token)
    ):
        return True
    if "/" in token and "@" not in token:
        parts = token.split("/")
        if any(_RE_UUID.match(p) or _RE_HEX_DIGEST.match(p) for p in parts):
            return True
    return token.lower() in _EXEMPT_WORDS


def _get_line_number(text: str, index: int) -> int:
    """Compute 1-based line number for a character offset."""
    return text.count("\n", 0, index) + 1


def _is_line_allowlisted(text: str, start: int, end: int) -> bool:
    """Check if the line containing the finding has an explicit test allowlist marker."""
    line_start = text.rfind("\n", 0, start)
    line_start = 0 if line_start == -1 else line_start + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end == -1 else line_end
    line_text = text[line_start:line_end]
    return "kb-allow-secret" in line_text


def scan_text_for_secrets(  # noqa: C901, PLR0912, PLR0915
    text: str,
    *,
    allow_markers: bool = True,
) -> list[SecretFinding]:
    """Scan untrusted text synchronously for secrets using signatures and Shannon entropy.

    Returns non-overlapping SecretFinding objects ordered left-to-right.
    """
    if not text:
        return []

    candidates: list[SecretFinding] = []

    # 1. PEM Private Key Blocks
    if "-----BEGIN " in text:
        for p_start, p_end, p_kind, _, _ in _scan_pem_private_keys(text):
            val = text[p_start:p_end]
            candidates.append(
                SecretFinding(
                    rule_id="PEM_PRIVATE_KEY",
                    kind=p_kind,
                    start=p_start,
                    end=p_end,
                    line=_get_line_number(text, p_start),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 2. Kanban Platform Tokens
    if "kb_" in text:
        for match in _RE_KANBAN_KEY.finditer(text):
            val = match.group(0)
            candidates.append(
                SecretFinding(
                    rule_id="KANBAN_TOKEN",
                    kind=SecretKind.KANBAN_KEY,
                    start=match.start(),
                    end=match.end(),
                    line=_get_line_number(text, match.start()),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 3. GitHub Tokens
    if "gh" in text or "git" in text:
        for match in _RE_GITHUB_TOKEN.finditer(text):
            val = match.group(0)
            candidates.append(
                SecretFinding(
                    rule_id="GITHUB_TOKEN",
                    kind=SecretKind.GITHUB_TOKEN,
                    start=match.start(),
                    end=match.end(),
                    line=_get_line_number(text, match.start()),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 4. GitLab Personal Access Tokens
    if "glpat-" in text:
        for match in _RE_GITLAB_TOKEN.finditer(text):
            val = match.group(0)
            candidates.append(
                SecretFinding(
                    rule_id="GITLAB_TOKEN",
                    kind=SecretKind.GITLAB_TOKEN,
                    start=match.start(),
                    end=match.end(),
                    line=_get_line_number(text, match.start()),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 5. AWS Access Keys
    if "AKIA" in text or "ASIA" in text:
        for match in _RE_AWS_ACCESS_KEY.finditer(text):
            val = match.group(0)
            candidates.append(
                SecretFinding(
                    rule_id="AWS_ACCESS_KEY",
                    kind=SecretKind.AWS_ACCESS_KEY,
                    start=match.start(),
                    end=match.end(),
                    line=_get_line_number(text, match.start()),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 6. Slack Tokens
    if "xox" in text:
        for match in _RE_SLACK_TOKEN.finditer(text):
            val = match.group(0)
            candidates.append(
                SecretFinding(
                    rule_id="SLACK_TOKEN",
                    kind=SecretKind.SLACK_TOKEN,
                    start=match.start(),
                    end=match.end(),
                    line=_get_line_number(text, match.start()),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 7. Google API Keys
    if "AIza" in text:
        for match in _RE_GOOGLE_KEY.finditer(text):
            val = match.group(0)
            candidates.append(
                SecretFinding(
                    rule_id="GOOGLE_API_KEY",
                    kind=SecretKind.GOOGLE_KEY,
                    start=match.start(),
                    end=match.end(),
                    line=_get_line_number(text, match.start()),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 8. Stripe Secret & Restricted Keys
    if "sk_" in text or "rk_" in text:
        for match in _RE_STRIPE_KEY.finditer(text):
            val = match.group(0)
            candidates.append(
                SecretFinding(
                    rule_id="STRIPE_KEY",
                    kind=SecretKind.STRIPE_KEY,
                    start=match.start(),
                    end=match.end(),
                    line=_get_line_number(text, match.start()),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 9. OpenAI / Anthropic Provider sk-* Keys
    if "sk-" in text:
        for match in _RE_API_KEY.finditer(text):
            token_body = match.group(1)
            has_digit = any(c.isdigit() for c in token_body)
            mixed_case = any(c.isupper() for c in token_body) and any(
                c.islower() for c in token_body
            )
            if has_digit or mixed_case:
                val = match.group(0)
                candidates.append(
                    SecretFinding(
                        rule_id="OPENAI_ANTHROPIC_KEY",
                        kind=SecretKind.API_KEY,
                        start=match.start(),
                        end=match.end(),
                        line=_get_line_number(text, match.start()),
                        fingerprint=mask_fingerprint(val),
                        secret_value=val,
                    )
                )

    # 10. Google Gemini / Vertex AQ.* Keys
    if "AQ." in text:
        for match in _RE_AQ_KEY.finditer(text):
            val = match.group(0)
            candidates.append(
                SecretFinding(
                    rule_id="GEMINI_VERTEX_KEY",
                    kind=SecretKind.API_KEY,
                    start=match.start(),
                    end=match.end(),
                    line=_get_line_number(text, match.start()),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 11. Bearer Authorization Tokens
    if "bearer" in text.lower():
        for match in _RE_BEARER_TOKEN.finditer(text):
            val = match.group(0)
            candidates.append(
                SecretFinding(
                    rule_id="BEARER_TOKEN",
                    kind=SecretKind.BEARER_TOKEN,
                    start=match.start(),
                    end=match.end(),
                    line=_get_line_number(text, match.start()),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 12. Standalone 3-Segment JWTs
    if "eyJ" in text:
        for match in _RE_JWT.finditer(text):
            val = match.group(0)
            candidates.append(
                SecretFinding(
                    rule_id="JWT_TOKEN",
                    kind=SecretKind.JWT,
                    start=match.start(),
                    end=match.end(),
                    line=_get_line_number(text, match.start()),
                    fingerprint=mask_fingerprint(val),
                    secret_value=val,
                )
            )

    # 13. Connection URIs with Passwords (DSNs)
    if "://" in text and "@" in text:
        for match in _RE_CONNECTION_URI.finditer(text):
            pwd = match.group(2)
            if not is_exempt_token(pwd):
                val = match.group(0)
                candidates.append(
                    SecretFinding(
                        rule_id="CONNECTION_URI_PASSWORD",
                        kind=SecretKind.CONNECTION_URI,
                        start=match.start(2),
                        end=match.end(2),
                        line=_get_line_number(text, match.start(2)),
                        fingerprint=mask_fingerprint(pwd),
                        secret_value=pwd,
                    )
                )
        for match in _RE_REDIS_URI.finditer(text):
            pwd = match.group(2)
            if not is_exempt_token(pwd):
                val = match.group(0)
                candidates.append(
                    SecretFinding(
                        rule_id="CONNECTION_URI_PASSWORD",
                        kind=SecretKind.CONNECTION_URI,
                        start=match.start(2),
                        end=match.end(2),
                        line=_get_line_number(text, match.start(2)),
                        fingerprint=mask_fingerprint(pwd),
                        secret_value=pwd,
                    )
                )

    # 14. Key-Value Secret Assignments
    if any(k in text.upper() for k in ("PASSWORD", "SECRET", "TOKEN", "API_KEY")):
        for match in _RE_KEY_VALUE_ASSIGNMENT.finditer(text):
            val = match.group("val")
            if not is_exempt_token(val):
                entropy = calculate_shannon_entropy(val)
                has_mixed = any(c.isupper() for c in val) and any(c.islower() for c in val)
                has_num = any(c.isdigit() for c in val)
                has_punct = any(not c.isalnum() for c in val)
                if entropy >= _MIN_ENTROPY_ASSIGNMENT or (has_num and (has_mixed or has_punct)):
                    candidates.append(
                        SecretFinding(
                            rule_id="ASSIGNED_SECRET",
                            kind=SecretKind.ASSIGNED_SECRET,
                            start=match.start("val"),
                            end=match.end("val"),
                            line=_get_line_number(text, match.start("val")),
                            fingerprint=mask_fingerprint(val),
                            secret_value=val,
                        )
                    )

    # 15. Standalone High Shannon Entropy Tokens (H >= 4.5 bits/char)
    # Check words that are not already covered by specific signatures
    for match in _RE_CANDIDATE_TOKEN.finditer(text):
        token = match.group(0)
        if len(token) >= _MIN_CANDIDATE_TOKEN_LENGTH and not is_exempt_token(token):
            entropy = calculate_shannon_entropy(token)
            if entropy >= _MIN_SHANNON_ENTROPY:
                # Require mixed character classes (e.g. letters and numbers or symbols)
                has_digit = any(c.isdigit() for c in token)
                has_alpha = any(c.isalpha() for c in token)
                if has_digit and has_alpha:
                    candidates.append(
                        SecretFinding(
                            rule_id="SHANNON_ENTROPY_SECRET",
                            kind=SecretKind.HIGH_ENTROPY_SECRET,
                            start=match.start(),
                            end=match.end(),
                            line=_get_line_number(text, match.start()),
                            fingerprint=mask_fingerprint(token),
                            secret_value=token,
                        )
                    )

    if not candidates:
        return []

    # Filter out findings on allowlisted lines if markers are permitted
    if allow_markers:
        candidates = [c for c in candidates if not _is_line_allowlisted(text, c.start, c.end)]

    # Non-overlapping left-to-right span resolution (longest span wins on ties)
    candidates.sort(key=lambda c: (c.start, -(c.end - c.start)))

    resolved: list[SecretFinding] = []
    last_end = 0
    for finding in candidates:
        if finding.start >= last_end:
            resolved.append(finding)
            last_end = finding.end

    return resolved


def redact_text_findings(text: str, findings: Sequence[SecretFinding]) -> str:
    """Redact secret spans from text using non-overlapping findings."""
    if not findings:
        return text

    pieces: list[str] = []
    last_pos = 0
    for f in findings:
        pieces.append(text[last_pos : f.start])
        placeholder = f"[REDACTED:{f.kind.value}]"
        pieces.append(placeholder)
        last_pos = f.end
    pieces.append(text[last_pos:])
    return "".join(pieces)


def enforce_secret_push_protection(  # noqa: PLR0913
    text: str | None,
    field: str,
    *,
    mode: PushProtectionMode | str = PushProtectionMode.BLOCK,
    allow_markers: bool = True,
    code: str = DEFAULT_PUSH_PROTECTION_CODE,
    workspace_id: uuid.UUID | None = None,  # noqa: ARG001  # Reserved for workspace policy lookup
) -> str | None:
    """Enforce pre-persistence secret push-protection synchronously.

    In BLOCK mode, raises RFC 7807 422 ProblemException without echoing the raw secret value.
    In REDACT_ON_WRITE mode, returns sanitized text with spans replaced and logs a warning.
    """
    if not text:
        return text

    findings = scan_text_for_secrets(text, allow_markers=allow_markers)
    if not findings:
        return text

    resolved_mode = PushProtectionMode(mode)
    if resolved_mode == PushProtectionMode.BLOCK:
        first = findings[0]
        logger.warning(
            "Secret push-protection blocked write in field '%s' at line %d (rule: %s, kind: %s)",
            field,
            first.line,
            first.rule_id,
            first.kind.value,
        )
        raise ProblemException(
            code=code,
            status=422,
            title="Secret Detected In Payload",
            detail=f"Secret material detected in field '{field}' at line {first.line}",
            field=field,
            extra={
                "rule_id": first.rule_id,
                "secret_kind": first.kind.value,
                "line": first.line,
                "fingerprint": first.fingerprint,
            },
        )

    # REDACT_ON_WRITE mode
    logger.warning(
        "SECRET_REDACTED_ON_WRITE: field '%s' had %d secret finding(s) redacted",
        field,
        len(findings),
    )
    return redact_text_findings(text, findings)
