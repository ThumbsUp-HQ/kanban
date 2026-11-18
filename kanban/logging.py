# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Standardized semantic emoji logging system (👍 / ⛔ / ❌) for the Kanban platform.

Provides log-injection sanitization, credential scrubbing, request correlation,
and single-line log formatting across application, MCP, agent, database, and CLI runtimes.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import TYPE_CHECKING, Any, Final, cast

from kanban.api.request_id import _REQUEST_ID_CTX
from kanban.security.scrubber import scrub_text

if TYPE_CHECKING:
    from typing import TextIO

__all__ = [
    "STATUS_BLOCKED",
    "STATUS_ERROR",
    "STATUS_OK",
    "KanbanLogFilter",
    "KanbanLogFormatter",
    "KanbanStreamHandler",
    "configure_logging",
    "extract_http_status_code",
    "log_blocked",
    "log_error",
    "log_ok",
    "sanitize_log_text",
    "scrub_log_secrets",
    "status_symbol_for_http_status",
    "status_symbol_for_level",
]

STATUS_OK: Final[str] = "👍"
STATUS_BLOCKED: Final[str] = "⛔"
STATUS_ERROR: Final[str] = "❌"

_STATUS_ICONS: Final[tuple[str, ...]] = (STATUS_OK, STATUS_BLOCKED, STATUS_ERROR)

# Sanitization regex patterns
_RE_SURROGATES: Final[re.Pattern[str]] = re.compile(r"[\ud800-\udfff]")
_RE_ANSI_OSC: Final[re.Pattern[str]] = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)")
_RE_ANSI_CSI_1: Final[re.Pattern[str]] = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_RE_ANSI_CSI_2: Final[re.Pattern[str]] = re.compile(r"\x9b[0-?]*[ -/]*[@-~]")
_RE_BIDI_SPOOF: Final[re.Pattern[str]] = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
_RE_C0_C1_CONTROL: Final[re.Pattern[str]] = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# Credential scrubbing patterns for log entries
_RE_SETUP_TOKEN: Final[re.Pattern[str]] = re.compile(
    r"\bkb_setup_[A-Za-z0-9_-]{16,128}(?![A-Za-z0-9_-])"
)
_RE_COOKIES: Final[re.Pattern[str]] = re.compile(
    r"\b(__Host-kb_session|kb_session|kb_csrf)=(?!\[REDACTED:)([^;\s&]+)"
)
_RE_DSN_PASSWORD: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(postgres(?:ql)?(?:\+[a-z0-9_]+)?://[^:]+:)(?!\[REDACTED:)([^@\s]+)(@)"
)
_RE_KV_SECRETS: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(password|client_secret|secret)\s*([=:]\s*(?:\\*['\"])?)"
    r"(?!\[REDACTED:)([^;'\"\s,]+)((?:\\*['\"])?)"
)
_RE_HTTP_STATUS_IN_ACCESS_LOG: Final[re.Pattern[str]] = re.compile(r'"\s+([1-5]\d\d)\b')

_PACKAGE_LOGGERS: Final[tuple[str, ...]] = (
    "kanban",
    "mcp",
    "database",
    "agent",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "alembic",
)


_HTTP_CLIENT_ERROR_MIN: Final = 400
_HTTP_SERVER_ERROR_MIN: Final = 500
_UVICORN_ACCESS_ARGS_LEN: Final = 5
_UVICORN_ACCESS_STATUS_IDX: Final = 4


def _coerce_int_status(val: object) -> int | None:
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.isdigit():
        return int(val)
    return None


def status_symbol_for_level(levelno: int) -> str:
    """Return the semantic status symbol for a numeric log level.

    - DEBUG and INFO: 👍
    - WARNING: ⛔
    - ERROR and CRITICAL: ❌
    """
    if levelno < logging.WARNING:
        return STATUS_OK
    if levelno < logging.ERROR:
        return STATUS_BLOCKED
    return STATUS_ERROR


def status_symbol_for_http_status(status_code: int) -> str:
    """Return the semantic status symbol for an HTTP status code.

    - 1xx, 2xx, 3xx: 👍
    - 4xx: ⛔
    - 5xx: ❌
    """
    if status_code < _HTTP_CLIENT_ERROR_MIN:
        return STATUS_OK
    if status_code < _HTTP_SERVER_ERROR_MIN:
        return STATUS_BLOCKED
    return STATUS_ERROR


def extract_http_status_code(record: logging.LogRecord) -> int | None:
    """Extract HTTP status code from LogRecord if present."""
    status = _coerce_int_status(getattr(record, "status_code", None))
    if status is not None:
        return status

    args = record.args
    if isinstance(args, tuple) and len(args) >= _UVICORN_ACCESS_ARGS_LEN:
        status = _coerce_int_status(args[_UVICORN_ACCESS_STATUS_IDX])
        if status is not None:
            return status

    if isinstance(args, dict):
        status = _coerce_int_status(args.get("status_code") or args.get("status"))
        if status is not None:
            return status

    name = record.name or ""
    if "access" in name or name.startswith("uvicorn"):
        msg = record.getMessage() if hasattr(record, "getMessage") else str(record.msg)
        match = _RE_HTTP_STATUS_IN_ACCESS_LOG.search(msg)
        if match:
            return int(match.group(1))

    return None


def scrub_log_secrets(text: str) -> str:
    """Scrub sensitive credentials, tokens, session cookies, and database DSN passwords."""
    if not text:
        return text

    # Redact setup tokens to explicit [REDACTED:SETUP_TOKEN]
    text = _RE_SETUP_TOKEN.sub("[REDACTED:SETUP_TOKEN]", text)

    # Pass through primary secret scrubber (API keys, JWT, Bearer, kb_* keys, PEM)
    text = scrub_text(text)

    # Redact session cookies
    text = _RE_COOKIES.sub(r"\g<1>=[REDACTED:COOKIE]", text)

    # Redact PostgreSQL DSN credentials
    text = _RE_DSN_PASSWORD.sub(r"\g<1>[REDACTED:PASSWORD]\g<3>", text)

    # Redact key-value password and secret assignments
    return _RE_KV_SECRETS.sub(r"\g<1>\g<2>[REDACTED:SECRET]\g<4>", text)


def sanitize_log_text(text: str) -> str:
    """Sanitize log text against injection, lone surrogates, ANSI, and secrets.

    Ensures no user input can forge a new log line or break terminal escape sequences.
    """
    if not text:
        return text

    # 1. Replace UTF-16 lone surrogates with replacement character
    text = _RE_SURROGATES.sub("\ufffd", text)

    # 2. Strip ANSI OSC escape sequences
    text = _RE_ANSI_OSC.sub("", text)

    # 3. Strip ANSI CSI escape sequences
    text = _RE_ANSI_CSI_1.sub("", text)
    text = _RE_ANSI_CSI_2.sub("", text)

    # 4. Strip BiDi and zero-width direction overrides
    text = _RE_BIDI_SPOOF.sub("", text)

    # 5. Escape raw line breaks and tabs to prevent multi-line log forging
    text = text.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    text = text.replace("\u0085", "\\n").replace("\u2028", "\\n").replace("\u2029", "\\n")

    # 6. Strip remaining C0/C1 control characters
    text = _RE_C0_C1_CONTROL.sub("", text)

    # 7. Redact sensitive credentials
    return scrub_log_secrets(text)


class KanbanLogFilter(logging.Filter):
    """Logging filter that attaches the semantic status icon and active request_id."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject status_icon and request_id attributes with accurate HTTP severity mapping."""
        http_status = extract_http_status_code(record)
        if http_status is not None:
            record.status_icon = status_symbol_for_http_status(http_status)
            if http_status >= _HTTP_SERVER_ERROR_MIN:
                record.levelno = logging.ERROR
                record.levelname = "ERROR"
            elif http_status >= _HTTP_CLIENT_ERROR_MIN:
                record.levelno = logging.WARNING
                record.levelname = "WARNING"
            elif record.levelno < logging.WARNING:
                record.levelno = logging.INFO
                record.levelname = "INFO"
        else:
            record.status_icon = status_symbol_for_level(record.levelno)

        req_id = getattr(record, "request_id", None)
        if not req_id or req_id == "-":
            ctx_id = _REQUEST_ID_CTX.get()
            record.request_id = ctx_id or "-"
        return True


def _resolve_record_status_icon(record: logging.LogRecord) -> str:
    status_icon = getattr(record, "status_icon", None)
    if status_icon is not None:
        return str(status_icon)

    http_status = extract_http_status_code(record)
    if http_status is None:
        return status_symbol_for_level(record.levelno)

    if http_status >= _HTTP_SERVER_ERROR_MIN and record.levelno < logging.ERROR:
        record.levelno = logging.ERROR
        record.levelname = "ERROR"
    elif http_status >= _HTTP_CLIENT_ERROR_MIN and record.levelno < logging.WARNING:
        record.levelno = logging.WARNING
        record.levelname = "WARNING"
    return status_symbol_for_http_status(http_status)


class KanbanLogFormatter(logging.Formatter):
    """Standardized single-line log formatter with semantic status icons."""

    def format(self, record: logging.LogRecord) -> str:
        """Format record into a single sanitized line prefixed with status icon."""
        record.message = record.getMessage()
        sanitized_msg = sanitize_log_text(record.message)

        # Deduplicate leading status icons if already present in message
        for icon in _STATUS_ICONS:
            if sanitized_msg.startswith(icon):
                sanitized_msg = sanitized_msg[len(icon) :].lstrip()
                break

        status_icon = _resolve_record_status_icon(record)

        req_id = getattr(record, "request_id", None)
        if not req_id or req_id == "-":
            ctx_id = _REQUEST_ID_CTX.get()
            req_id = ctx_id or "-"

        ts = self.formatTime(record, self.datefmt)
        prefix = f"{status_icon} {ts} [{record.levelname}] [{record.name}] [req={req_id}]"
        line = f"{prefix} {sanitized_msg}"

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            sanitized_exc = sanitize_log_text(record.exc_text)
            line += f" | exc={sanitized_exc}"

        if record.stack_info:
            sanitized_stack = sanitize_log_text(self.formatStack(record.stack_info))
            line += f" | stack={sanitized_stack}"

        return line


class KanbanStreamHandler(logging.StreamHandler[Any]):
    """Managed StreamHandler recognized by configure_logging."""

    is_kanban_managed: bool = True


def _resolve_log_level(level: str | int | None) -> int:
    """Resolve configured log level from argument or environment."""
    if level is None:
        level_name = os.environ.get("KB_LOG_LEVEL", "INFO").upper()
        return int(getattr(logging, level_name, logging.INFO))
    if isinstance(level, str):
        return int(getattr(logging, level.upper(), logging.INFO))
    return int(level)


def _find_or_create_handler(
    root_logger: logging.Logger,
    stream: TextIO | None,
) -> logging.StreamHandler[Any]:
    """Find existing managed handler or wrap pre-existing non-pytest stream handler."""
    for h in list(root_logger.handlers):
        if getattr(h, "is_kanban_managed", False):
            return cast("logging.StreamHandler[Any]", h)
        if type(h).__name__ == "LogCaptureHandler" or h.__class__.__module__.startswith("_pytest"):
            continue
        if isinstance(h, logging.StreamHandler):
            return h

    target_stream = stream if stream is not None else sys.stderr
    handler = KanbanStreamHandler(target_stream)
    root_logger.addHandler(handler)
    return handler


def configure_logging(
    *,
    level: str | int | None = None,
    stream: TextIO | None = None,
) -> None:
    """Configure unified semantic emoji logging across application and root loggers."""
    resolved_level = _resolve_log_level(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    managed_handler = _find_or_create_handler(root_logger, stream)
    if stream is not None:
        managed_handler.setStream(stream)

    managed_handler.setLevel(resolved_level)
    managed_handler.setFormatter(KanbanLogFormatter())
    if not any(isinstance(f, KanbanLogFilter) for f in managed_handler.filters):
        managed_handler.addFilter(KanbanLogFilter())

    # Standardize package loggers to propagate through root handler without duplicate handlers
    for pkg_name in _PACKAGE_LOGGERS:
        pkg_logger = logging.getLogger(pkg_name)
        pkg_logger.setLevel(resolved_level)
        pkg_logger.propagate = True
        for h in list(pkg_logger.handlers):
            if (
                not getattr(h, "is_kanban_managed", False)
                and type(h).__name__ != "LogCaptureHandler"
            ):
                pkg_logger.removeHandler(h)


def log_ok(
    logger_or_msg: logging.Logger | str,
    *args: object,
    **kwargs: Any,  # noqa: ANN401
) -> None:
    """Log an operational success or normal progress message (👍 / INFO)."""
    if isinstance(logger_or_msg, logging.Logger):
        msg = args[0] if args else ""
        rem_args = args[1:]
        logger_or_msg.info(msg, *rem_args, **kwargs)
    else:
        logging.getLogger("kanban").info(logger_or_msg, *args, **kwargs)


def log_blocked(
    logger_or_msg: logging.Logger | str,
    *args: object,
    **kwargs: Any,  # noqa: ANN401
) -> None:
    """Log a policy block, client rejection, rate limit, or degraded state (⛔ / WARNING)."""
    if isinstance(logger_or_msg, logging.Logger):
        msg = args[0] if args else ""
        rem_args = args[1:]
        logger_or_msg.warning(msg, *rem_args, **kwargs)
    else:
        logging.getLogger("kanban").warning(logger_or_msg, *args, **kwargs)


def log_error(
    logger_or_msg: logging.Logger | str,
    *args: object,
    **kwargs: Any,  # noqa: ANN401
) -> None:
    """Log a system error, unhandled exception, or fatal failure (❌ / ERROR)."""
    if isinstance(logger_or_msg, logging.Logger):
        msg = args[0] if args else ""
        rem_args = args[1:]
        logger_or_msg.error(msg, *rem_args, **kwargs)
    else:
        logging.getLogger("kanban").error(logger_or_msg, *args, **kwargs)
