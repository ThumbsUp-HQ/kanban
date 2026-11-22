# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, F841
"""Unit tests for CSRF Bearer token exemption and cookie precedence (KAN-48)."""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
from fastapi import FastAPI
from starlette.responses import JSONResponse

from kanban.auth.sessions.cookies import (
    SESSION_COOKIE_NAME,
    encode_session_cookie,
    generate_session_token,
)
from kanban.auth.sessions.csrf import (
    CSRF_HEADER_NAME,
    PRE_SESSION_ID,
    CsrfMiddleware,
    build_set_csrf_cookie_header,
    generate_csrf_token,
)


@pytest.fixture
def hmac_key() -> bytes:
    """Fixture providing a 32-byte HMAC key."""
    return os.urandom(32)


@pytest.fixture
def test_app(hmac_key: bytes) -> FastAPI:
    """Fixture providing a FastAPI app equipped with CsrfMiddleware."""
    app = FastAPI()
    app.add_middleware(CsrfMiddleware, session_hmac_key=hmac_key)

    @app.post("/api/v1/test-mutation")
    async def test_mutation() -> JSONResponse:
        return JSONResponse({"status": "mutation_success"})

    @app.get("/api/v1/test-query")
    async def test_query() -> JSONResponse:
        return JSONResponse({"status": "query_success"})

    return app


@pytest.mark.asyncio
async def test_stateless_bearer_bypasses_csrf(test_app: FastAPI) -> None:
    """Stateless requests with Authorization: Bearer <token> and no cookie bypass CSRF."""
    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/v1/test-mutation",
            headers={"Authorization": "Bearer kb_agt_test_token_123"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "mutation_success"}


@pytest.mark.asyncio
async def test_cookie_authenticated_request_requires_csrf(
    test_app: FastAPI, hmac_key: bytes
) -> None:
    """Requests carrying an ambient session cookie must provide a valid CSRF token."""
    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=False)
    session_id = uuid.uuid4()
    raw_token = generate_session_token()
    cookie_val = encode_session_cookie(raw_token, hmac_key)
    cookie_str = f"{SESSION_COOKIE_NAME}={cookie_val}"

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Session cookie without CSRF header fails with 403
        resp_no_csrf = await client.post(
            "/api/v1/test-mutation",
            headers={"Cookie": cookie_str},
        )
        assert resp_no_csrf.status_code == 403

        # 2. Session cookie WITH Authorization header but WITHOUT CSRF header still fails with 403
        # (attacker cannot bypass CSRF on a cookie-authenticated request by attaching an arbitrary Bearer)
        resp_cookie_and_bearer = await client.post(
            "/api/v1/test-mutation",
            headers={
                "Cookie": cookie_str,
                "Authorization": "Bearer attacker_provided_token",
            },
        )
        assert resp_cookie_and_bearer.status_code == 403

        # 3. Request WITH valid CSRF header and cookie succeeds
        csrf_token = generate_csrf_token(PRE_SESSION_ID, hmac_key)
        csrf_cookie = build_set_csrf_cookie_header(csrf_token).split(";")[0]
        combined_cookies = f"{cookie_str}; {csrf_cookie}"

        resp_valid = await client.post(
            "/api/v1/test-mutation",
            headers={
                "Cookie": combined_cookies,
                CSRF_HEADER_NAME: csrf_token,
                "Origin": "http://testserver",
            },
        )
        assert resp_valid.status_code == 200
        assert resp_valid.json() == {"status": "mutation_success"}


@pytest.mark.asyncio
async def test_empty_or_malformed_bearer_does_not_bypass(test_app: FastAPI) -> None:
    """Empty or whitespace-only Bearer token does not trigger stateless CSRF bypass."""
    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Empty bearer
        resp1 = await client.post(
            "/api/v1/test-mutation",
            headers={"Authorization": "Bearer "},
        )
        assert resp1.status_code == 403

        # Just 'Bearer' without space
        resp2 = await client.post(
            "/api/v1/test-mutation",
            headers={"Authorization": "Bearer"},
        )
        assert resp2.status_code == 403

        # Non-bearer auth scheme
        resp3 = await client.post(
            "/api/v1/test-mutation",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp3.status_code == 403


@pytest.mark.asyncio
async def test_safe_get_with_cookie_always_allowed(test_app: FastAPI, hmac_key: bytes) -> None:
    """Safe HTTP methods like GET are always permitted even with ambient session cookies."""
    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=False)
    session_id = uuid.uuid4()
    raw_token = generate_session_token()
    cookie_val = encode_session_cookie(raw_token, hmac_key)
    cookie_str = f"{SESSION_COOKIE_NAME}={cookie_val}"

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/api/v1/test-query",
            headers={"Cookie": cookie_str},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "query_success"}
