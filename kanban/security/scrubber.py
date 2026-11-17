"""Outbound secret scrubber for credential redaction in outbound payloads.

Scans untrusted text strings to detect and redact API keys, GitHub tokens,
AWS credentials, PEM private keys, HTTP Bearer tokens, JWTs, and platform
keys before they leave process boundaries (e.g. to LLM APIs or agent pipes).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

_MAX_PEM_SCAN_WINDOW: Final[int] = 16384
_MAX_PEM_HEADER_LEN: Final[int] = 128
_B64_CHARS: Final[set[str]] = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
)
_PEM_HEADER_CHARS: Final[set[str]] = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-,: "
)

# Deterministic regular expressions compiled at module load time
_RE_KANBAN_KEY: Final[re.Pattern[str]] = re.compile(
    r"\bkb_(?:agt_eph|agt|doc|adm|setup|pat|runner)_[A-Za-z0-9_-]{16,128}(?![A-Za-z0-9_-])"
)
_RE_GITHUB_TOKEN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b"
)
_RE_AWS_ACCESS_KEY: Final[re.Pattern[str]] = re.compile(r"\b(?:AKIA|ASIA)[A-Z2-70-9]{16}\b")
_RE_API_KEY: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9_-])sk-(?:proj-|ant-api\d{2}-|live-|test-)?([A-Za-z0-9_-]{20,256})(?![A-Za-z0-9_-])"
)
_RE_BEARER_TOKEN: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(Bearer)(\s+)[A-Za-z0-9._~+/=-]{20,2048}(?![A-Za-z0-9._~+/=-])"
)
_RE_JWT: Final[re.Pattern[str]] = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,512}\.eyJ[A-Za-z0-9_-]{8,1024}\.[A-Za-z0-9_-]{16,1024}\b"
)


class SecretKind(StrEnum):
    """Enumeration of secret classes recognized by the outbound scrubber."""

    API_KEY = "API_KEY"
    GITHUB_TOKEN = "GITHUB_TOKEN"  # noqa: S105  # Secret class identifier
    AWS_ACCESS_KEY = "AWS_ACCESS_KEY"
    PRIVATE_KEY = "PRIVATE_KEY"
    BEARER_TOKEN = "BEARER_TOKEN"  # noqa: S105  # Secret class identifier
    JWT = "JWT"
    KANBAN_KEY = "KANBAN_KEY"


@dataclass(frozen=True)
class ScrubFinding:
    """Location and metadata of a redacted secret.

    Raw secret substrings are intentionally omitted from this structure
    to prevent accidental credential exposure via logging, error reports,
    or serialization.
    """

    kind: SecretKind
    start: int
    end: int
    placeholder: str


@dataclass(frozen=True)
class ScrubResult:
    """Outcome of an outbound secret scrubbing pass."""

    text: str
    redacted: bool
    count: int
    findings: tuple[ScrubFinding, ...]


def _find_base64_body_end(text: str, start: int, cutoff: int) -> int:
    """Locate the terminal index of a PEM base64 body before cutoff."""
    curr = start
    last_valid = start
    while curr < cutoff:
        nl = text.find("\n", curr, cutoff)
        line_end = nl + 1 if nl != -1 else cutoff
        line = text[curr:line_end]
        stripped = line.strip()
        if not stripped:
            curr = line_end
            continue
        if ":" in stripped and set(stripped).issubset(_PEM_HEADER_CHARS):
            last_valid = curr + len(line.rstrip("\r\n"))
            curr = line_end
            continue
        if set(stripped).issubset(_B64_CHARS):
            last_valid = curr + len(line.rstrip("\r\n"))
            curr = line_end
            continue
        # If the header had no trailing newline and base64 followed inline
        if curr == start:
            while curr < cutoff and text[curr] in _B64_CHARS:
                curr += 1
            last_valid = curr
        break

    return last_valid


def _scan_pem_private_keys(
    text: str,
) -> list[tuple[int, int, SecretKind, str, int]]:
    """Scan text linearly for PEM private key blocks and unclosed headers."""
    findings: list[tuple[int, int, SecretKind, str, int]] = []
    text_len = len(text)
    idx = 0
    header_prefix = "-----BEGIN "

    while idx < text_len:
        pos = text.find(header_prefix, idx)
        if pos == -1:
            break

        header_close = text.find("-----", pos + len(header_prefix))
        if header_close == -1 or (header_close - pos) > _MAX_PEM_HEADER_LEN:
            idx = pos + len(header_prefix)
            continue

        header_end = header_close + 5
        label = text[pos + len(header_prefix) : header_close].strip()
        if not label.endswith(("PRIVATE KEY", "PRIVATE KEY BLOCK")):
            idx = header_end
            continue

        expected_footer = f"-----END {label}-----"
        search_limit = min(text_len, pos + _MAX_PEM_SCAN_WINDOW)
        footer_pos = text.find(expected_footer, header_end, search_limit)

        if footer_pos != -1:
            span_end = footer_pos + len(expected_footer)
            findings.append((pos, span_end, SecretKind.PRIVATE_KEY, "[REDACTED:PRIVATE_KEY]", 1))
            idx = span_end
        else:
            # Unclosed header within search window (e.g. truncated paste)
            next_begin = text.find(header_prefix, header_end, search_limit)
            cutoff = next_begin if next_begin != -1 else search_limit
            span_end = _find_base64_body_end(text, header_end, cutoff)
            findings.append((pos, span_end, SecretKind.PRIVATE_KEY, "[REDACTED:PRIVATE_KEY]", 1))
            idx = span_end

    return findings


def outbound_secret_scrubber(text: str) -> ScrubResult:  # noqa: C901, PLR0912  # Multi-secret detector branches
    """Scrub sensitive credentials from outbound text payloads.

    Detects API keys, GitHub tokens, AWS keys, PEM private key blocks,
    Bearer authorization tokens, JWTs, and Kanban platform keys. Redacts
    matched spans using non-overlapping left-to-right span resolution where
    longest-span wins on ties.

    Returns:
        ScrubResult containing the sanitized text, a redacted boolean flag,
        the count of redacted secrets, and a tuple of ScrubFinding instances.

    """
    if not text:
        return ScrubResult(text=text, redacted=False, count=0, findings=())

    # Candidate matches: (start, end, kind, placeholder, rule_priority)
    candidates: list[tuple[int, int, SecretKind, str, int]] = []

    # Rule 1: PEM Private Key Blocks
    if "-----BEGIN " in text:
        candidates.extend(_scan_pem_private_keys(text))

    # Rule 2: Kanban Platform Keys
    if "kb_" in text:
        candidates.extend(
            (match.start(), match.end(), SecretKind.KANBAN_KEY, "[REDACTED:KANBAN_KEY]", 2)
            for match in _RE_KANBAN_KEY.finditer(text)
        )

    # Rule 3: GitHub Tokens
    if "gh" in text or "git" in text:
        candidates.extend(
            (match.start(), match.end(), SecretKind.GITHUB_TOKEN, "[REDACTED:GITHUB_TOKEN]", 3)
            for match in _RE_GITHUB_TOKEN.finditer(text)
        )

    # Rule 4: AWS Access Key IDs
    if "AKIA" in text or "ASIA" in text:
        candidates.extend(
            (match.start(), match.end(), SecretKind.AWS_ACCESS_KEY, "[REDACTED:AWS_ACCESS_KEY]", 4)
            for match in _RE_AWS_ACCESS_KEY.finditer(text)
        )

    # Rule 5: OpenAI / Anthropic / Provider sk-* Keys
    if "sk-" in text:
        for match in _RE_API_KEY.finditer(text):
            token_body = match.group(1)
            # Require at least one digit or mixed-case character
            has_digit = any(c.isdigit() for c in token_body)
            mixed_case = any(c.isupper() for c in token_body) and any(
                c.islower() for c in token_body
            )
            if has_digit or mixed_case:
                candidates.append(
                    (
                        match.start(),
                        match.end(),
                        SecretKind.API_KEY,
                        "[REDACTED:API_KEY]",
                        5,
                    )
                )

    # Rule 6: HTTP Bearer Authorization Tokens
    if "bearer" in text.lower():
        candidates.extend(
            (
                match.start(),
                match.end(),
                SecretKind.BEARER_TOKEN,
                f"{match.group(1)} [REDACTED:BEARER_TOKEN]",
                6,
            )
            for match in _RE_BEARER_TOKEN.finditer(text)
        )

    # Rule 7: Standalone 3-Segment JWTs
    if "eyJ" in text:
        candidates.extend(
            (match.start(), match.end(), SecretKind.JWT, "[REDACTED:JWT]", 7)
            for match in _RE_JWT.finditer(text)
        )

    if not candidates:
        return ScrubResult(text=text, redacted=False, count=0, findings=())

    # Non-overlapping left-to-right span resolution:
    # Sort primarily by start ascending, then span length descending (longest wins),
    # then rule priority ascending.
    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0]), c[4]))

    resolved_findings: list[ScrubFinding] = []
    last_end = 0
    for start, end, kind, placeholder, _ in candidates:
        if start >= last_end:
            resolved_findings.append(
                ScrubFinding(kind=kind, start=start, end=end, placeholder=placeholder)
            )
            last_end = end

    # Reconstruct string with non-secret substrings preserved byte-for-byte
    pieces: list[str] = []
    last_pos = 0
    for f in resolved_findings:
        pieces.append(text[last_pos : f.start])
        pieces.append(f.placeholder)
        last_pos = f.end
    pieces.append(text[last_pos:])
    scrubbed_text = "".join(pieces)

    return ScrubResult(
        text=scrubbed_text,
        redacted=True,
        count=len(resolved_findings),
        findings=tuple(resolved_findings),
    )


def scrub_text(text: str) -> str:
    """Return redacted text from outbound_secret_scrubber."""
    return outbound_secret_scrubber(text).text
