# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit tests for the standardized semantic emoji logging system (KB-LOG-STD)."""

from __future__ import annotations

import io
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException

from deploy.standalone.entrypoint import build_child_env, log_phase
from kanban.api.problems import starlette_http_exception_handler
from kanban.api.request_id import _REQUEST_ID_CTX
from kanban.auth.setup import SetupBootstrapService
from kanban.logging import (
    STATUS_BLOCKED,
    STATUS_ERROR,
    STATUS_OK,
    KanbanLogFilter,
    KanbanLogFormatter,
    configure_logging,
    log_blocked,
    log_error,
    log_ok,
    sanitize_log_text,
    scrub_log_secrets,
    status_symbol_for_level,
)
from kanban.security.keys import KeyMaterial


# -----------------------------------------------------------------------------
# Case 1: Positive Formatting & Semantic Icons
# -----------------------------------------------------------------------------
def test_status_symbol_mapping() -> None:
    """Verify numeric log levels map to canonical status emojis."""
    assert status_symbol_for_level(logging.DEBUG) == STATUS_OK
    assert status_symbol_for_level(logging.INFO) == STATUS_OK
    assert status_symbol_for_level(logging.WARNING) == STATUS_BLOCKED
    assert status_symbol_for_level(logging.ERROR) == STATUS_ERROR
    assert status_symbol_for_level(logging.CRITICAL) == STATUS_ERROR


def test_positive_formatting_and_deduplication() -> None:
    """Verify log lines are formatted with status emoji, level, req_id, and no duplicate emoji."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    formatter = KanbanLogFormatter()
    log_filter = KanbanLogFilter()
    handler.setFormatter(formatter)
    handler.addFilter(log_filter)

    logger = logging.getLogger("test_pos_logger")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False

    # Outside HTTP context: req=-
    logger.info("Normal startup message")
    logger.warning("Rate limit approaching")
    logger.error("Database connection dropped")

    # Already prefixed with semantic emojis: should not be duplicated
    logger.info("👍 Already contains ok icon")
    logger.warning("⛔ Already contains blocked icon")
    logger.error("❌ Already contains error icon")

    lines = [line for line in stream.getvalue().splitlines() if line]
    assert len(lines) == 6

    # Verify line prefixes and contents
    assert lines[0].startswith("👍 ")
    assert "[INFO]" in lines[0]
    assert "[req=-]" in lines[0]
    assert "Normal startup message" in lines[0]

    assert lines[1].startswith("⛔ ")
    assert "[WARNING]" in lines[1]
    assert "Rate limit approaching" in lines[1]

    assert lines[2].startswith("❌ ")
    assert "[ERROR]" in lines[2]
    assert "Database connection dropped" in lines[2]

    # Verify deduplication
    assert lines[3].startswith("👍 ")
    assert "👍 👍" not in lines[3]
    assert "Already contains ok icon" in lines[3]

    assert lines[4].startswith("⛔ ")
    assert "⛔ ⛔" not in lines[4]
    assert "Already contains blocked icon" in lines[4]

    assert lines[5].startswith("❌ ")
    assert "❌ ❌" not in lines[5]
    assert "Already contains error icon" in lines[5]


def test_request_id_correlation() -> None:
    """Verify active request_id contextvar is injected into formatted records."""
    token = _REQUEST_ID_CTX.set("req_deadbeef1234")
    try:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(KanbanLogFormatter())
        handler.addFilter(KanbanLogFilter())

        logger = logging.getLogger("test_req_logger")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.propagate = False

        logger.info("Request correlated event")
        out = stream.getvalue()
        assert "[req=req_deadbeef1234]" in out
        assert "Request correlated event" in out
    finally:
        _REQUEST_ID_CTX.reset(token)


def test_semantic_helper_functions() -> None:
    """Verify log_ok, log_blocked, and log_error helper functions."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(KanbanLogFormatter())
    handler.addFilter(KanbanLogFilter())

    test_logger = logging.getLogger("test_helpers")
    test_logger.setLevel(logging.DEBUG)
    test_logger.handlers.clear()
    test_logger.addHandler(handler)
    test_logger.propagate = False

    log_ok(test_logger, "Success step: %s", "done")
    log_blocked(test_logger, "Blocked step: %s", "denied")
    log_error(test_logger, "Failure step: %s", "crashed")

    lines = [line for line in stream.getvalue().splitlines() if line]
    assert len(lines) == 3
    assert lines[0].startswith("👍 ")
    assert "Success step: done" in lines[0]
    assert lines[1].startswith("⛔ ")
    assert "Blocked step: denied" in lines[1]
    assert lines[2].startswith("❌ ")
    assert "Failure step: crashed" in lines[2]


# -----------------------------------------------------------------------------
# Case 2: Negative & Security (Sanitization & Secret Redaction)
# -----------------------------------------------------------------------------
def test_direct_sanitization_and_scrubbing_apis() -> None:
    """Verify direct sanitize_log_text and scrub_log_secrets functions."""
    raw = "test\r\nline2\x1b[31mred\x1b[0m password=supersecret postgresql://a:b@h/db"
    sanitized = sanitize_log_text(raw)
    assert "\r" not in sanitized
    assert "\n" not in sanitized
    assert "\\r\\n" in sanitized
    assert "\x1b" not in sanitized
    assert "supersecret" not in sanitized
    assert "[REDACTED:SECRET]" in sanitized
    assert "[REDACTED:PASSWORD]" in sanitized

    raw_secret = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc"
    scrubbed = scrub_log_secrets(raw_secret)
    assert "[REDACTED:BEARER_TOKEN]" in scrubbed


def test_log_injection_neutralization() -> None:
    """Verify CRLF, ANSI, BiDi, and surrogates cannot forge log lines or crash."""
    forged_input = (
        "User entered text\r\n👍 2026-11-17 12:00:00 [INFO] [auth] [req=none] Forged admin login"
        "\u2028Second forged line\u2029Third forged line\x1b[31;1mRed text\x1b[0m"
        "\x9b2J\u202eBiDiSpoof\ud800LoneSurrogate"
    )

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(KanbanLogFormatter())
    handler.addFilter(KanbanLogFilter())

    logger = logging.getLogger("test_injection_logger")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False

    # This MUST NOT raise UnicodeEncodeError and MUST emit exactly ONE log line
    logger.info("Hostile payload: %s", forged_input)
    raw_output = stream.getvalue()

    # Must be strictly 1 newline terminating the single record
    assert raw_output.count("\n") == 1
    assert "\r" not in raw_output
    assert "\u2028" not in raw_output
    assert "\u2029" not in raw_output
    assert "\x1b" not in raw_output
    assert "\x9b" not in raw_output
    assert "\u202e" not in raw_output
    # Surrogate replaced
    assert "\ufffd" in raw_output
    # CRLF was escaped
    assert "\\r\\n" in raw_output


def test_credential_scrubbing_in_message_and_tracebacks() -> None:
    """Verify Bearer tokens, platform keys, cookies, DSN passwords, and secrets are redacted."""
    sensitive_msg = (
        "Credentials leaked: Bearer "
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW4ifQ.signature "
        "kb_pat_0123456789abcdef0123456789 "
        "kb_runner_9876543210fedcba9876543210 "
        "kb_setup_abcdef0123456789abcdef0123 "
        "Cookie: __Host-kb_session=sess_tok_12345; "
        "kb_session=legacy_tok_67890; kb_csrf=csrf_tok_abc "
        "Database DSN: postgresql://admin:super_secret_db_pass@db.local:5432/kanban "
        "Config: password=my_plain_pass, "
        'client_secret="quoted_client_secret", '
        "secret='single_quoted'"
    )

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(KanbanLogFormatter())
    handler.addFilter(KanbanLogFilter())

    logger = logging.getLogger("test_scrub_logger")
    logger.setLevel(logging.ERROR)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False

    try:
        msg = "postgresql://kanban_app:vault_secret@127.0.0.1/kanban and password=exc_pass"
        raise ValueError(msg)  # noqa: TRY301
    except Exception:
        logger.error(sensitive_msg, exc_info=True)  # noqa: G201

    out = stream.getvalue()

    # Must be a single line record despite carrying a traceback
    assert out.count("\n") == 1
    assert " | exc=" in out

    # Verify redactions in log message
    assert "super_secret_db_pass" not in out
    assert "sess_tok_12345" not in out
    assert "legacy_tok_67890" not in out
    assert "csrf_tok_abc" not in out
    assert "my_plain_pass" not in out
    assert "quoted_client_secret" not in out
    assert "single_quoted" not in out
    assert "0123456789abcdef0123456789" not in out
    assert "9876543210fedcba9876543210" not in out
    assert "abcdef0123456789abcdef0123" not in out

    # Verify redactions in exception traceback
    assert "vault_secret" not in out
    assert "exc_pass" not in out
    assert "[REDACTED:PASSWORD]" in out
    assert "[REDACTED:SECRET]" in out
    assert "[REDACTED:COOKIE]" in out


# -----------------------------------------------------------------------------
# Case 3: Boundary & Integration
# -----------------------------------------------------------------------------
def test_configure_logging_integration(caplog: pytest.LogCaptureFixture) -> None:
    """Verify configure_logging configures root and package loggers while preserving caplog."""
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)

    # Logging through kanban and uvicorn packages
    kanban_log = logging.getLogger("kanban.test")
    uvicorn_log = logging.getLogger("uvicorn.error")

    kanban_log.info("Kanban info event")
    uvicorn_log.warning("Uvicorn warning event")

    out = stream.getvalue()
    assert "👍 " in out
    assert "[kanban.test]" in out
    assert "Kanban info event" in out
    assert "⛔ " in out
    assert "[uvicorn.error]" in out
    assert "Uvicorn warning event" in out

    # Verify caplog captured the records without interference
    assert any(r.name == "kanban.test" for r in caplog.records)
    assert any(r.name == "uvicorn.error" for r in caplog.records)


@pytest.mark.asyncio
async def test_first_boot_setup_url_preserves_stdout() -> None:
    """Verify SetupBootstrapService outputs First-boot setup URL to stdout unredacted."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = True
    mock_session.execute.return_value = mock_res

    mock_factory = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session
    mock_ctx.__aexit__.return_value = None
    mock_factory.session.return_value = mock_ctx

    km = KeyMaterial(
        master_kek=b"0" * 32,
        auth_pepper=b"1" * 32,
        session_hmac_key=b"2" * 32,
    )
    svc = SetupBootstrapService(mock_factory, key_material=km)
    out_buf = io.StringIO()
    token = await svc.mint_token_if_uninitialized(stdout=out_buf)

    assert token is not None
    assert token.startswith("kb_setup_")
    rendered = out_buf.getvalue()
    assert f"First-boot setup URL: http://localhost:8080/setup?token={token}\n" == rendered


def test_standalone_entrypoint_log_level_and_phase_formatting(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify deploy/standalone/entrypoint.py forwards KB_LOG_LEVEL and formats log_phase."""
    monkeypatch.setenv("KB_LOG_LEVEL", "DEBUG")
    child_env = build_child_env()
    assert child_env.get("KB_LOG_LEVEL") == "DEBUG"

    log_phase("initdb", "initializing cluster", level="INFO")
    log_phase("storage", "ephemeral warning", level="WARNING")
    log_phase("crash", "fatal error", level="ERROR")

    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line]
    assert any(line.startswith("👍 ") and "initdb: initializing cluster" in line for line in lines)
    assert any(line.startswith("⛔ ") and "storage: ephemeral warning" in line for line in lines)
    assert any(line.startswith("❌ ") and "crash: fatal error" in line for line in lines)


@pytest.mark.asyncio
async def test_problem_exception_logging() -> None:
    """Verify starlette_http_exception_handler logs 4xx at WARNING and 5xx at ERROR."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(KanbanLogFormatter())
    handler.addFilter(KanbanLogFilter())

    prob_logger = logging.getLogger("kanban.api.problems")
    prob_logger.setLevel(logging.DEBUG)
    prob_logger.handlers.clear()
    prob_logger.addHandler(handler)
    prob_logger.propagate = False

    req = object()  # dummy request

    # 404 Not Found -> WARNING (⛔)
    exc_404 = StarletteHTTPException(status_code=404, detail="Entity missing")
    resp_404 = await starlette_http_exception_handler(req, exc_404)  # type: ignore[arg-type]
    assert resp_404.status_code == 404

    # 500 Internal Error -> ERROR (❌)
    exc_500 = StarletteHTTPException(status_code=500, detail="Database dead")
    resp_500 = await starlette_http_exception_handler(req, exc_500)  # type: ignore[arg-type]
    assert resp_500.status_code == 500

    out = stream.getvalue()
    lines = [line for line in out.splitlines() if line]
    assert len(lines) == 2
    assert lines[0].startswith("⛔ ")
    assert "HTTP 404 NOT_FOUND" in lines[0]
    assert lines[1].startswith("❌ ")
    assert "HTTP 500 INTERNAL_ERROR" in lines[1]
