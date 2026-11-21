# Copyright 2026 Kanban Platform Contributors
"""Typed error hierarchy for LLM providers with secret redaction."""

from __future__ import annotations

import re

from kanban.ai_config.net_guard import EgressDeniedError

_CODE_PATTERN: re.Pattern[str] = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")

_BEARER_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+",
)
_SK_PATTERN: re.Pattern[str] = re.compile(
    r"\bsk-[a-zA-Z0-9_-]{8,}\b",
)
_GHP_PATTERN: re.Pattern[str] = re.compile(
    r"\bghp_[a-zA-Z0-9]{20,}\b",
)
_AKIA_PATTERN: re.Pattern[str] = re.compile(
    r"\bAKIA[0-9A-Z]{16}\b",
)
_KB_PATTERN: re.Pattern[str] = re.compile(
    r"\bkb_[a-zA-Z0-9_-]{8,}\b",
)
_AIZA_PATTERN: re.Pattern[str] = re.compile(
    r"\bAIza[0-9A-Za-z_-]{20,}\b",
)
_AQ_PATTERN: re.Pattern[str] = re.compile(
    r"\bAQ\.[A-Za-z0-9_-]{20,}\b",
)
_JWT_PATTERN: re.Pattern[str] = re.compile(
    r"\beyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b",
)
_PARAM_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|authorization)\s*([:=])\s*['\"]?[a-zA-Z0-9_.\-~/+=]{8,}['\"]?",
)


def redact_secrets(text: str) -> str:
    """Redact bearer tokens, API keys, and sensitive authorization strings."""
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    redacted = _SK_PATTERN.sub("sk-[REDACTED]", redacted)
    redacted = _GHP_PATTERN.sub("ghp-[REDACTED]", redacted)
    redacted = _AKIA_PATTERN.sub("AKIA[REDACTED]", redacted)
    redacted = _KB_PATTERN.sub("kb_[REDACTED]", redacted)
    redacted = _AIZA_PATTERN.sub("AIza[REDACTED]", redacted)
    redacted = _AQ_PATTERN.sub("AQ.[REDACTED]", redacted)
    redacted = _JWT_PATTERN.sub("[REDACTED_JWT]", redacted)
    return _PARAM_PATTERN.sub(r"\1\2[REDACTED]", redacted)


def _validate_code(code: str) -> str:
    """Validate error code conforms to ^[A-Z][A-Z0-9_]{2,63}$."""
    if not _CODE_PATTERN.match(code):
        msg = f"Invalid provider error code '{code}'; must match ^[A-Z][A-Z0-9_]{{2,63}}$"
        raise ValueError(msg)
    return code


class ProviderError(Exception):
    """Root error for all LLM and CLI provider failures."""

    def __init__(self, message: str, code: str = "PROVIDER_ERROR") -> None:
        """Initialize ProviderError with sanitized message and validated code."""
        self.code: str = _validate_code(code)
        self.message: str = redact_secrets(message)
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return formatted error string with code and message."""
        return f"[{self.code}] {self.message}"

    def __repr__(self) -> str:
        """Return developer-facing representation of the error."""
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r})"


class ProviderHTTPError(ProviderError):
    """Raised when an upstream provider returns an HTTP error status."""

    def __init__(
        self,
        message: str,
        status: int,
        retry_after_s: float | None = None,
        code: str = "HTTP_ERROR",
    ) -> None:
        """Initialize HTTP error with status code and optional retry header."""
        self.status: int = status
        self.retry_after_s: float | None = retry_after_s
        super().__init__(message, code=code)


class ProviderTimeout(ProviderError):  # noqa: N818  # Class name mandated by KB-P0-12 spec
    """Raised when an upstream provider call or TTFT deadline times out."""

    def __init__(self, message: str, code: str = "TIMEOUT") -> None:
        """Initialize provider timeout error."""
        super().__init__(message, code=code)


class ProviderUnavailable(ProviderError):  # noqa: N818  # Class name mandated by KB-P0-12 spec
    """Raised when an individual LLM provider is offline or unreachable."""

    def __init__(self, message: str, code: str = "UNAVAILABLE") -> None:
        """Initialize provider unavailable error."""
        super().__init__(message, code=code)


class AllProvidersUnavailable(ProviderUnavailable):
    """Raised when all configured providers in a residency tier are unavailable."""

    def __init__(self, message: str, code: str = "ALL_PROVIDERS_UNAVAILABLE") -> None:
        """Initialize all providers unavailable error."""
        super().__init__(message, code=code)


class ProviderProtocolError(ProviderError):
    """Raised when an upstream provider violates the wire protocol."""

    def __init__(self, message: str, code: str = "PROTOCOL_ERROR") -> None:
        """Initialize provider protocol error."""
        super().__init__(message, code=code)


class ProviderSchemaError(ProviderError):
    """Raised when model output fails to parse into the requested Pydantic schema."""

    def __init__(self, message: str, code: str = "SCHEMA_ERROR") -> None:
        """Initialize provider schema error."""
        super().__init__(message, code=code)


class ProviderSafetyBlock(ProviderError):  # noqa: N818  # Class name mandated by KB-P0-12 spec
    """Raised when provider content safety filters trigger and block generation."""

    def __init__(self, message: str, code: str = "SAFETY_BLOCK") -> None:
        """Initialize provider safety block error."""
        super().__init__(message, code=code)


class ProviderRefusal(ProviderError):  # noqa: N818  # Class name mandated by KB-P0-12 spec
    """Raised when a model explicitly refuses to answer or follow instructions."""

    def __init__(self, message: str, code: str = "REFUSAL") -> None:
        """Initialize provider refusal error."""
        super().__init__(message, code=code)


class ProviderPolicyError(ProviderError):
    """Raised when a provider request violates platform governance or budget policies."""

    def __init__(self, message: str, code: str = "POLICY_ERROR") -> None:
        """Initialize provider policy error."""
        super().__init__(message, code=code)


class EgressDenied(ProviderPolicyError, EgressDeniedError):  # noqa: N818  # Class name mandated by KB-P0-12 spec
    """Raised when air-gap mode or network policy forbids egress to the provider."""

    def __init__(self, message: str, code: str = "EGRESS_DENIED") -> None:
        """Initialize egress denied policy error."""
        super().__init__(message, code=code)
        self.code = _validate_code(code)
