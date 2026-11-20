# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for JsonLimitsMiddleware streaming byte caps and JSON bounds (KB-P3-AUDIT-11)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from kanban.api.middleware.json_limits import (
    DEFAULT_MAX_BODY_BYTES,
    LARGE_UPLOAD_MAX_BODY_BYTES,
    MAX_JSON_DEPTH,
    MAX_JSON_KEYS,
    JsonDepthLimitError,
    JsonLimitsMiddleware,
    JsonSurrogateLimitError,
    _scan_json_depth_iterative,
    _validate_json_structure_iterative,
)

if TYPE_CHECKING:
    from starlette.requests import Request


def _create_test_app() -> Starlette:
    async def echo_json(request: Request) -> JSONResponse:
        data = await request.json()
        return JSONResponse({"status": "ok", "echo": data})

    async def echo_raw(request: Request) -> JSONResponse:
        body = await request.body()
        _ = await request.body()  # read again to trigger second receive call
        return JSONResponse({"status": "ok", "bytes_len": len(body)})

    routes = [
        Route("/api/v1/echo", echo_json, methods=["POST"]),
        Route("/api/v1/attachments/upload", echo_raw, methods=["POST"]),
        Route("/api/v1/admin/imports/plane", echo_raw, methods=["POST"]),
        Route("/api/v1/text", echo_raw, methods=["POST"]),
    ]

    return Starlette(
        routes=routes,
        middleware=[Middleware(JsonLimitsMiddleware)],
    )


def test_json_limits_default_2mib_ceiling() -> None:
    """Enforce 2 MiB ceiling on default routes and reject larger payloads with 413."""
    client = TestClient(_create_test_app())

    # 1. Normal payload below 2 MiB succeeds
    small_data = {"key": "hello world"}
    res_ok = client.post("/api/v1/echo", json=small_data)
    assert res_ok.status_code == 200
    assert res_ok.json()["echo"] == small_data

    # 2. Content-Length exceeding 2 MiB rejected with 413
    huge_len = DEFAULT_MAX_BODY_BYTES + 1024
    res_too_large_header = client.post(
        "/api/v1/echo",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": str(huge_len)},
    )
    assert res_too_large_header.status_code == 413
    assert res_too_large_header.json()["code"] == "PAYLOAD_TOO_LARGE"

    # 3. Streaming body exceeding 2 MiB rejected with 413
    huge_body = b'{"data": "' + (b"X" * (DEFAULT_MAX_BODY_BYTES + 100)) + b'"}'
    res_too_large_body = client.post(
        "/api/v1/echo",
        content=huge_body,
        headers={"Content-Type": "application/json"},
    )
    assert res_too_large_body.status_code == 413
    assert res_too_large_body.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_json_limits_large_upload_routes_allow_up_to_25mib() -> None:
    """Attachments and imports routes allow up to 25 MiB."""
    client = TestClient(_create_test_app())

    # 1. Payload > 2 MiB but < 25 MiB allowed on /attachments and /imports
    mid_bytes = 3 * 1024 * 1024  # 3 MiB
    chunk = b"A" * mid_bytes

    res_att = client.post(
        "/api/v1/attachments/upload",
        content=chunk,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert res_att.status_code == 200
    assert res_att.json()["bytes_len"] == mid_bytes

    res_imp = client.post(
        "/api/v1/admin/imports/plane",
        content=chunk,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert res_imp.status_code == 200
    assert res_imp.json()["bytes_len"] == mid_bytes

    # 2. Content-Length exceeding 25 MiB rejected with 413
    over_limit = LARGE_UPLOAD_MAX_BODY_BYTES + 1024
    res_huge = client.post(
        "/api/v1/attachments/upload",
        content=b"X",
        headers={"Content-Type": "application/octet-stream", "Content-Length": str(over_limit)},
    )
    assert res_huge.status_code == 413
    assert res_huge.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_json_limits_non_json_content_types_skip_json_validation() -> None:
    """Non-JSON content-types bypass JSON structural checks."""
    client = TestClient(_create_test_app())

    # Plain text containing deeply nested brackets is NOT checked as JSON
    non_json_text = "[" * 100
    res = client.post(
        "/api/v1/text",
        content=non_json_text.encode("utf-8"),
        headers={"Content-Type": "text/plain"},
    )
    assert res.status_code == 200
    assert res.json()["bytes_len"] == len(non_json_text)


def test_json_limits_depth_ceiling_32() -> None:
    """JSON requests with nesting depth exceeding 32 rejected with 422 JSON_DEPTH_EXCEEDED."""
    client = TestClient(_create_test_app())

    # 1. Depth <= 32 passes
    safe_nested: Any = "leaf"
    for _ in range(MAX_JSON_DEPTH - 2):
        safe_nested = [safe_nested]
    res_ok = client.post("/api/v1/echo", json=safe_nested)
    assert res_ok.status_code == 200

    # 2. Depth > 32 rejected
    deep_nested: Any = "leaf"
    for _ in range(MAX_JSON_DEPTH + 5):
        deep_nested = [deep_nested]
    res_deep = client.post("/api/v1/echo", json=deep_nested)
    assert res_deep.status_code == 422
    assert res_deep.json()["code"] == "JSON_DEPTH_EXCEEDED"

    # 3. Massive nested brackets (e.g. 200 levels) rejected iteratively before parser recursion
    massive_raw = ("[" * 200) + ("]" * 200)
    res_massive = client.post(
        "/api/v1/echo",
        content=massive_raw.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert res_massive.status_code == 422
    assert res_massive.json()["code"] == "JSON_DEPTH_EXCEEDED"

    # 4. Bracket characters inside JSON string literal do NOT increment depth
    brackets_in_string = {"message": ("[" * 100) + ("]" * 100)}
    res_string = client.post("/api/v1/echo", json=brackets_in_string)
    assert res_string.status_code == 200


def test_json_limits_keys_ceiling_5000() -> None:
    """JSON object key count exceeding 5000 rejected with 422 JSON_KEYS_EXCEEDED."""
    client = TestClient(_create_test_app())

    # Object with 5001 keys rejected
    too_many_keys = {f"k_{i}": i for i in range(MAX_JSON_KEYS + 1)}
    res = client.post("/api/v1/echo", json=too_many_keys)
    assert res.status_code == 422
    assert res.json()["code"] == "JSON_KEYS_EXCEEDED"


def test_json_limits_utf16_lone_surrogate_rejection() -> None:
    """UTF-16 lone surrogates (raw or escaped) rejected with 422 INVALID_UTF8_SURROGATE."""
    client = TestClient(_create_test_app())

    # 1. Escaped lone high surrogate in value (\ud800)
    surrogate_val = b'{"name": "\\ud800"}'
    res_val = client.post(
        "/api/v1/echo",
        content=surrogate_val,
        headers={"Content-Type": "application/json"},
    )
    assert res_val.status_code == 422
    assert res_val.json()["code"] == "INVALID_UTF8_SURROGATE"

    # 2. Escaped lone surrogate in key (\udfff)
    surrogate_key = b'{"\\udfff": "bad_key"}'
    res_key = client.post(
        "/api/v1/echo",
        content=surrogate_key,
        headers={"Content-Type": "application/json"},
    )
    assert res_key.status_code == 422
    assert res_key.json()["code"] == "INVALID_UTF8_SURROGATE"

    # 3. Escaped lone surrogate in array
    surrogate_arr = b'["safe", "\\ud83d"]'
    res_arr = client.post(
        "/api/v1/echo",
        content=surrogate_arr,
        headers={"Content-Type": "application/json"},
    )
    assert res_arr.status_code == 422
    assert res_arr.json()["code"] == "INVALID_UTF8_SURROGATE"

    # 4. Valid surrogate pair (\ud83d\ude00 -> 😀) succeeds
    valid_pair = b'{"emoji": "\\ud83d\\ude00"}'
    res_ok = client.post(
        "/api/v1/echo",
        content=valid_pair,
        headers={"Content-Type": "application/json"},
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["echo"]["emoji"] == "😀"

    # 5. Raw UTF-8 bytes encoding lone surrogate (e.g. \xed\xa0\x80 for U+D800)
    raw_surrogate_bytes = b'{"raw": "' + b"\xed\xa0\x80" + b'"}'
    res_raw_surr = client.post(
        "/api/v1/echo",
        content=raw_surrogate_bytes,
        headers={"Content-Type": "application/json"},
    )
    assert res_raw_surr.status_code == 422
    assert res_raw_surr.json()["code"] == "INVALID_UTF8_SURROGATE"


def test_json_limits_empty_and_syntax_error() -> None:
    """Empty JSON body passes through; syntax errors return 422 INVALID_JSON."""
    client = TestClient(_create_test_app())

    # Malformed JSON
    res_malformed = client.post(
        "/api/v1/echo",
        content=b"{invalid_json",
        headers={"Content-Type": "application/json"},
    )
    assert res_malformed.status_code == 422
    assert res_malformed.json()["code"] == "INVALID_JSON"

    # Empty body
    res_empty = client.post(
        "/api/v1/text",
        content=b"",
        headers={"Content-Type": "application/json"},
    )
    assert res_empty.status_code == 200


def test_json_scanner_helpers_coverage() -> None:
    """Direct unit testing of helper functions to ensure 100% branch and statement coverage."""
    # Depth scanner depth underflow check
    assert _scan_json_depth_iterative("}}}}") is True
    # Escaped quote inside string
    assert _scan_json_depth_iterative('{"test": "hello \\" world"}') is True

    # Validate structure helper on string root
    _validate_json_structure_iterative("safe string")

    # Validate structure helper lone surrogate in root string
    with pytest.raises(JsonSurrogateLimitError):
        _validate_json_structure_iterative("\ud800")

    # Validate surrogate in dictionary value
    with pytest.raises(JsonSurrogateLimitError):
        _validate_json_structure_iterative({"key": "\ud800"})

    # Validate surrogate in list item
    with pytest.raises(JsonSurrogateLimitError):
        _validate_json_structure_iterative(["safe", "\ud800"])

    # Validate depth in parsed object
    deep_obj: Any = "leaf"
    for _ in range(MAX_JSON_DEPTH + 1):
        deep_obj = {"nested": deep_obj}
    with pytest.raises(JsonDepthLimitError):
        _validate_json_structure_iterative(deep_obj)


@pytest.mark.asyncio
async def test_json_limits_asgi_edge_cases() -> None:
    """Test ASGI non-http scopes, non-request messages, and non-utf8 decode errors."""
    called = False

    async def dummy_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ARG001, ANN401
        nonlocal called
        called = True

    mw = JsonLimitsMiddleware(dummy_app)

    # 1. Non-http scope passes through
    await mw({"type": "lifespan"}, None, None)  # type: ignore[arg-type]
    assert called is True

    # 2. Non-digit Content-Length is ignored
    client = TestClient(_create_test_app())
    res_bad_cl = client.post(
        "/api/v1/echo",
        content=b'{"ok": true}',
        headers={"Content-Type": "application/json", "Content-Length": "not-an-int"},
    )
    assert res_bad_cl.status_code == 200

    # 3. Non-UTF-8 bytes return 422 INVALID_JSON
    res_bad_utf8 = client.post(
        "/api/v1/echo",
        content=b"\xff\xfe\x00\x00",
        headers={"Content-Type": "application/json"},
    )
    assert res_bad_utf8.status_code == 422
    assert res_bad_utf8.json()["code"] == "INVALID_JSON"

    # 4. Non-request message during receive loop (e.g. disconnect)
    sent_messages: list[dict[str, Any]] = []

    async def mock_receive_disconnect() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    async def recording_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ARG001, ANN401
        msg = await receive()
        sent_messages.append(msg)

    mw2 = JsonLimitsMiddleware(recording_app)
    scope_headers = [(b"content-type", b"application/json")]
    await mw2(
        {"type": "http", "path": "/api/v1/echo", "headers": scope_headers},
        mock_receive_disconnect,
        None,  # type: ignore[arg-type]
    )
    assert len(sent_messages) == 1
    assert sent_messages[0]["type"] == "http.disconnect"

    # 5. Non-JSON streaming chunk overflow
    huge_bytes = b"X" * (DEFAULT_MAX_BODY_BYTES + 100)

    async def mock_receive_huge_stream() -> dict[str, Any]:
        return {"type": "http.request", "body": huge_bytes, "more_body": False}

    response_starts: list[dict[str, Any]] = []

    async def capture_send(msg: dict[str, Any]) -> None:
        response_starts.append(msg)

    async def reading_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ARG001, ANN401
        await receive()

    mw3 = JsonLimitsMiddleware(reading_app)
    await mw3(
        {"type": "http", "path": "/api/v1/text", "headers": [(b"content-type", b"text/plain")]},
        mock_receive_huge_stream,
        capture_send,  # type: ignore[arg-type]
    )
    assert any(m.get("status") == 413 for m in response_starts)
