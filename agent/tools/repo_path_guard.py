# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Secret-path and path-traversal guard for read-only repository tools (S14.2, S14.3)."""

from __future__ import annotations

import fnmatch
from typing import Final

__all__ = [
    "CODE_REPO_BINARY_FILE",
    "CODE_REPO_BINARY_FILE_UNSUPPORTED",
    "CODE_REPO_EXEC_FAILED",
    "CODE_REPO_FILE_NOT_FOUND",
    "CODE_REPO_GREP_PATTERN_INVALID",
    "CODE_REPO_PATH_INVALID",
    "CODE_REPO_SECRET_PATH_DENIED",
    "CODE_REPO_TIMEOUT",
    "MAX_REPO_PATH_BYTES",
    "SECRET_PATH_PATTERNS",
    "RepoToolPolicyError",
    "is_secret_repo_path",
    "normalize_repo_relpath",
]

CODE_REPO_PATH_INVALID: Final[str] = "REPO_PATH_INVALID"
CODE_REPO_SECRET_PATH_DENIED: Final[str] = "REPO_SECRET_PATH_DENIED"  # noqa: S105
CODE_REPO_TIMEOUT: Final[str] = "REPO_TIMEOUT"
CODE_REPO_EXEC_FAILED: Final[str] = "REPO_EXEC_FAILED"
CODE_REPO_FILE_NOT_FOUND: Final[str] = "REPO_FILE_NOT_FOUND"
CODE_REPO_BINARY_FILE: Final[str] = "REPO_BINARY_FILE"
CODE_REPO_BINARY_FILE_UNSUPPORTED: Final[str] = "REPO_BINARY_FILE_UNSUPPORTED"
CODE_REPO_GREP_PATTERN_INVALID: Final[str] = "REPO_GREP_PATTERN_INVALID"

MAX_REPO_PATH_BYTES: Final[int] = 512

SECRET_PATH_PATTERNS: Final[tuple[str, ...]] = (
    ".env",
    ".env.*",
    "*.env",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*id_rsa*",
    "*id_ed25519*",
    "*id_ecdsa*",
    ".git",
    ".git/*",
    ".netrc",
    ".npmrc",
    ".pypirc",
)


class RepoToolPolicyError(Exception):
    """Raised when repository tool arguments violate safety boundaries or policy."""

    def __init__(self, code: str, message: str | None = None) -> None:
        """Initialize error with standardized policy code and optional detail message."""
        self.code = code
        self.message = message or code
        super().__init__(f"[{code}] {self.message}" if message else code)


def _validate_path_chars_and_prefix(raw: str) -> None:
    """Validate forbidden characters and prefixes in raw path."""
    if "\0" in raw:
        msg = "Path contains NUL byte"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)
    if "\r" in raw or "\n" in raw:
        msg = "Path contains newline or carriage return characters"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)
    if "\\" in raw:
        msg = "Backslash path separators are forbidden; use forward slash '/'"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)
    if raw.startswith("-"):
        msg = "Path begins with '-' which could be interpreted as a command-line option"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)
    if raw.startswith("/"):
        msg = "Absolute paths are forbidden; path must be relative to repository root"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)


def normalize_repo_relpath(raw: str) -> str:
    """Normalize and validate a repository-relative path.

    Rejects NUL, CR/LF, leading '-', leading '/', backslashes, '.' and '..' segments,
    consecutive slashes, and paths exceeding 512 UTF-8 bytes.

    Raises:
        RepoToolPolicyError: with code "REPO_PATH_INVALID" on any violation.

    """
    raw_val: object = raw
    if not isinstance(raw_val, str):
        msg = f"Path must be a string, got {type(raw_val).__name__}"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)

    stripped = raw.strip()
    if not stripped:
        return ""

    _validate_path_chars_and_prefix(raw)

    # Normalize trailing slashes (e.g. "database/" -> "database")
    norm_text = raw.rstrip("/")

    try:
        raw_bytes = norm_text.encode("utf-8")
    except UnicodeEncodeError as exc:
        msg = f"Path cannot be encoded to UTF-8: {exc}"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg) from exc

    if len(raw_bytes) > MAX_REPO_PATH_BYTES:
        msg = f"Path exceeds maximum allowed length of {MAX_REPO_PATH_BYTES} bytes"
        raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)

    segments = norm_text.split("/")
    for segment in segments:
        if segment in (".", ".."):
            msg = f"Path traversal segment '{segment}' is strictly forbidden"
            raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)
        if segment == "":
            msg = "Empty path segment (consecutive slashes) is forbidden"
            raise RepoToolPolicyError(CODE_REPO_PATH_INVALID, msg)

    return "/".join(segments)


def is_secret_repo_path(relpath: str) -> bool:
    """Check whether a repository path references sensitive configuration or keys.

    Case-insensitively tests the full path, basename, and individual path segments
    against SECRET_PATH_PATTERNS.
    """
    if not relpath:
        return False

    lowered = relpath.strip().lower()
    if lowered == ".git" or lowered.startswith((".git/", ".git\\")):
        return True

    segments = lowered.replace("\\", "/").split("/")
    basename = segments[-1] if segments else ""

    for pattern in SECRET_PATH_PATTERNS:
        pat_lower = pattern.lower()
        # Test full relative path
        if fnmatch.fnmatchcase(lowered, pat_lower):
            return True
        # Test file basename
        if basename and fnmatch.fnmatchcase(basename, pat_lower):
            return True
        # Test each directory / file segment
        for segment in segments:
            if segment and fnmatch.fnmatchcase(segment, pat_lower):
                return True

    return False
