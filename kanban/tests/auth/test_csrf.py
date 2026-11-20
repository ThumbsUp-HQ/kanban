# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for CSRF token generation, header verification, and middleware defenses (KB-P2-02)."""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse

from kanban.api.deps import PrincipalContext
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_EXEMPT_PATHS,
    CSRF_HEADER_NAME,
    FALLBACK_CSRF_COOKIE_NAME,
    PRE_SESSION_ID,
    CsrfMiddleware,
    build_clear_csrf_cookie_header,
    build_clear_fallback_csrf_cookie_header,
    build_set_csrf_cookie_header,
    build_set_fallback_csrf_cookie_header,
    extract_csrf_cookie,
    generate_csrf_token,
    validate_csrf_token,
    verify_same_origin_request,
)
from kanban.security.keys import KeyMaterial
from kanban.settings import get_settings

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


@pytest.fixture
def hmac_key() -> bytes:
    """Fixture providing a 32-byte HMAC key."""
    return os.urandom(32)


def test_csrf_token_generation_and_validation(hmac_key: bytes) -> None:
    """Verify cryptographic token binding and tampering rejection."""
    s1 = uuid.uuid4()
    s2 = uuid.uuid4()

    token1 = generate_csrf_token(s1, hmac_key)
    assert "." in token1
    assert validate_csrf_token(token1, s1, hmac_key) is True

    # Token for session 1 fails verification against session 2
    assert validate_csrf_token(token1, s2, hmac_key) is False

    # Token with tampered signature fails
    parts = token1.split(".")
    tampered_sig = parts[0] + "." + ("B" if parts[1][0] == "A" else "A") + parts[1][1:]
    assert validate_csrf_token(tampered_sig, s1, hmac_key) is False

    # Pre-session token validation
    pre_token = generate_csrf_token(PRE_SESSION_ID, hmac_key)
    assert validate_csrf_token(pre_token, PRE_SESSION_ID, hmac_key) is True


def test_csrf_cookie_headers() -> None:
    """Verify __Host-kb_csrf attributes (SameSite=Strict, Secure, non-HttpOnly for SPA)."""
    set_hdr = build_set_csrf_cookie_header("test_csrf_token")
    assert f"{CSRF_COOKIE_NAME}=test_csrf_token" in set_hdr
    assert "Secure" in set_hdr
    assert "SameSite=Strict" in set_hdr
    assert "Path=/" in set_hdr
    assert "HttpOnly" not in set_hdr  # SPA must be able to read this cookie

    clear_hdr = build_clear_csrf_cookie_header()
    assert f"{CSRF_COOKIE_NAME}=" in clear_hdr
    assert "Max-Age=0" in clear_hdr
    assert "SameSite=Strict" in clear_hdr


@pytest.mark.asyncio
async def test_case_8_security_csrf_protections(hmac_key: bytes) -> None:
    """Test Case 8: CSRF validation failure scenarios and successful submission."""
    test_app = FastAPI()
    test_app.add_middleware(CsrfMiddleware, session_hmac_key=hmac_key)

    @test_app.post("/api/v1/test-action")
    async def test_action() -> JSONResponse:
        return JSONResponse({"status": "action_performed"})

    @test_app.get("/api/v1/auth/session")
    async def exempt_session_route() -> JSONResponse:
        return JSONResponse({"status": "exempt_ok"})

    session_a = uuid.uuid4()
    session_b = uuid.uuid4()

    token_a = generate_csrf_token(session_a, hmac_key)
    token_b = generate_csrf_token(session_b, hmac_key)

    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Mock active session A on request.state
        def set_session_a(request: Request) -> None:
            request.state.session_id = session_a
            request.state.principal = PrincipalContext(
                principal_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                session_id=session_a,
            )

        # 1. Missing X-CSRF-Token header -> 403 CSRF_REJECTED
        res1 = await client.post(
            "/api/v1/test-action",
            headers={"host": "testserver"},
            cookies={CSRF_COOKIE_NAME: token_a},
        )
        assert res1.status_code == 403
        data1 = res1.json()
        assert data1["code"] == "CSRF_REJECTED"

        # 2. Token from session A used with session B -> 403 CSRF_REJECTED
        # Simulate request bound to session B but sending token A
        class SessionInjectionMiddleware:
            def __init__(self, app: ASGIApp, sess_id: uuid.UUID) -> None:
                self.app = app
                self.sess_id = sess_id

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                if scope["type"] == "http":
                    scope["state"] = {
                        "session_id": self.sess_id,
                        "principal": PrincipalContext(
                            principal_id=uuid.uuid4(),
                            workspace_id=uuid.uuid4(),
                            session_id=self.sess_id,
                        ),
                    }
                await self.app(scope, receive, send)

        app_b = FastAPI()
        app_b.add_middleware(CsrfMiddleware, session_hmac_key=hmac_key)
        app_b.add_api_route("/api/v1/test-action", test_action, methods=["POST"])

        wrapped_b = SessionInjectionMiddleware(app_b, session_b)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=wrapped_b, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client_b:
            res2 = await client_b.post(
                "/api/v1/test-action",
                headers={"host": "testserver", CSRF_HEADER_NAME: token_a},
                cookies={CSRF_COOKIE_NAME: token_a},
            )
            assert res2.status_code == 403
            assert res2.json()["code"] == "CSRF_REJECTED"

            # 3. Origin: https://evil.example -> 403 CSRF_REJECTED
            res3 = await client_b.post(
                "/api/v1/test-action",
                headers={
                    "host": "testserver",
                    "origin": "https://evil.example",
                    CSRF_HEADER_NAME: token_b,
                },
                cookies={CSRF_COOKIE_NAME: token_b},
            )
            assert res3.status_code == 403
            assert res3.json()["code"] == "CSRF_REJECTED"

            # 4. Sec-Fetch-Site: cross-site -> 403 CSRF_REJECTED
            res4 = await client_b.post(
                "/api/v1/test-action",
                headers={
                    "host": "testserver",
                    "sec-fetch-site": "cross-site",
                    CSRF_HEADER_NAME: token_b,
                },
                cookies={CSRF_COOKIE_NAME: token_b},
            )
            assert res4.status_code == 403
            assert res4.json()["code"] == "CSRF_REJECTED"

            # 5. Correct token + same-origin -> 200 OK
            res5 = await client_b.post(
                "/api/v1/test-action",
                headers={
                    "host": "testserver",
                    "origin": "http://testserver",
                    "sec-fetch-site": "same-origin",
                    CSRF_HEADER_NAME: token_b,
                },
                cookies={CSRF_COOKIE_NAME: token_b},
            )
            assert res5.status_code == 200
            assert res5.json() == {"status": "action_performed"}


@pytest.mark.asyncio
async def test_csrf_referer_validation(hmac_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify standalone Referer validation when Origin header is absent."""
    test_app = FastAPI()
    test_app.add_middleware(CsrfMiddleware, session_hmac_key=hmac_key)

    @test_app.post("/api/v1/resource")
    async def modify_resource() -> JSONResponse:
        return JSONResponse({"status": "modified"})

    session_id = uuid.uuid4()
    token = generate_csrf_token(session_id, hmac_key)

    class InjectSessionMiddleware:
        def __init__(self, app: ASGIApp, sess_id: uuid.UUID) -> None:
            self.app = app
            self.sess_id = sess_id

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                scope["state"] = {
                    "session_id": self.sess_id,
                    "principal": PrincipalContext(
                        principal_id=uuid.uuid4(),
                        workspace_id=uuid.uuid4(),
                        session_id=self.sess_id,
                    ),
                }
            await self.app(scope, receive, send)

    app_wrapped = InjectSessionMiddleware(test_app, session_id)
    transport = httpx.ASGITransport(app=app_wrapped, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Origin absent, Referer: https://evil.example/attack -> 403 CSRF_REJECTED
        res_evil = await client.post(
            "/api/v1/resource",
            headers={
                "host": "testserver",
                "referer": "https://evil.example/attack?param=value",
                CSRF_HEADER_NAME: token,
            },
            cookies={CSRF_COOKIE_NAME: token},
        )
        assert res_evil.status_code == 403
        assert res_evil.json()["code"] == "CSRF_REJECTED"

        # 2. Origin absent, Referer: http://testserver/app/issues -> 200 OK
        res_ok = await client.post(
            "/api/v1/resource",
            headers={
                "host": "testserver",
                "referer": "http://testserver/app/issues",
                CSRF_HEADER_NAME: token,
            },
            cookies={CSRF_COOKIE_NAME: token},
        )
        assert res_ok.status_code == 200
        assert res_ok.json() == {"status": "modified"}

        # 3. Origin absent, malformed Referer -> 403 CSRF_REJECTED
        res_malformed = await client.post(
            "/api/v1/resource",
            headers={
                "host": "testserver",
                "referer": "not-a-valid-url",
                CSRF_HEADER_NAME: token,
            },
            cookies={CSRF_COOKIE_NAME: token},
        )
        assert res_malformed.status_code == 403
        assert res_malformed.json()["code"] == "CSRF_REJECTED"

        # 4. Origin absent, non-HTTP Referer -> 403 CSRF_REJECTED
        res_js = await client.post(
            "/api/v1/resource",
            headers={
                "host": "testserver",
                "referer": "javascript:alert(1)",
                CSRF_HEADER_NAME: token,
            },
            cookies={CSRF_COOKIE_NAME: token},
        )
        assert res_js.status_code == 403
        assert res_js.json()["code"] == "CSRF_REJECTED"

        # 5. Public origin configured: matches Referer
        monkeypatch.setenv("KB_PUBLIC_ORIGIN", "https://kanban.example")
        res_public_ok = await client.post(
            "/api/v1/resource",
            headers={
                "host": "kanban.internal",
                "referer": "https://kanban.example/board",
                CSRF_HEADER_NAME: token,
            },
            cookies={CSRF_COOKIE_NAME: token},
        )
        assert res_public_ok.status_code == 200

        # 6. Public origin configured: mismatch Referer -> 403 CSRF_REJECTED
        res_public_mismatch = await client.post(
            "/api/v1/resource",
            headers={
                "host": "kanban.internal",
                "referer": "https://other.example/board",
                CSRF_HEADER_NAME: token,
            },
            cookies={CSRF_COOKIE_NAME: token},
        )
        assert res_public_mismatch.status_code == 403
        assert res_public_mismatch.json()["code"] == "CSRF_REJECTED"


def test_csrf_exempt_paths() -> None:
    """Verify exempt paths constant contains required endpoints."""
    assert "/api/v1/auth/session" in CSRF_EXEMPT_PATHS
    assert "/api/v1/healthz" in CSRF_EXEMPT_PATHS
    assert "/health" in CSRF_EXEMPT_PATHS


def test_csrf_token_validation_error_branches(hmac_key: bytes) -> None:
    """Verify input validation branches for validate_csrf_token."""
    s = uuid.uuid4()
    assert validate_csrf_token("", s, hmac_key) is False
    assert validate_csrf_token("nodot", s, hmac_key) is False
    assert validate_csrf_token("a.b.c", s, hmac_key) is False
    assert validate_csrf_token("inv@lid.b64!", s, hmac_key) is False
    assert validate_csrf_token("AAAA.BBBB", s, hmac_key) is False


@pytest.mark.asyncio
async def test_csrf_middleware_edge_cases(hmac_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify middleware branches: non-api, exemptions, public origin, key material."""
    app = FastAPI()
    app.state.key_material = KeyMaterial(
        master_kek=os.urandom(32),
        master_kek_kid="kek-v1",
        auth_pepper=os.urandom(32),
        session_hmac_key=hmac_key,
    )
    # Init without passing session_hmac_key explicitly to test _get_key from app.state
    app.add_middleware(CsrfMiddleware)

    @app.post("/non-api/action")
    async def non_api_action() -> JSONResponse:
        return JSONResponse({"status": "non_api_ok"})

    @app.post("/api/v1/healthz")
    async def exempt_post() -> JSONResponse:
        return JSONResponse({"status": "exempt_ok"})

    @app.post("/api/v1/protected")
    async def protected_action() -> JSONResponse:
        return JSONResponse({"status": "protected_ok"})

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Non-api path bypassed
        res_non_api = await client.post("/non-api/action")
        assert res_non_api.status_code == 200

        # 2. Exempt path bypassed
        res_exempt = await client.post("/api/v1/healthz")
        assert res_exempt.status_code == 200

        # 3. Header mismatch cookie
        tok1 = generate_csrf_token(PRE_SESSION_ID, hmac_key)
        tok2 = generate_csrf_token(PRE_SESSION_ID, hmac_key)
        res_mismatch = await client.post(
            "/api/v1/protected",
            headers={"host": "testserver", CSRF_HEADER_NAME: tok1},
            cookies={CSRF_COOKIE_NAME: tok2},
        )
        assert res_mismatch.status_code == 403
        assert "CSRF header does not match cookie" in res_mismatch.json()["detail"]

        # 4. KANBAN_PUBLIC_ORIGIN check
        monkeypatch.setenv("KANBAN_PUBLIC_ORIGIN", "https://kanban.example.com")
        res_evil_origin = await client.post(
            "/api/v1/protected",
            headers={
                "host": "testserver",
                "origin": "https://evil.example.com",
                CSRF_HEADER_NAME: tok1,
            },
            cookies={CSRF_COOKIE_NAME: tok1},
        )
        assert res_evil_origin.status_code == 403
        assert "Origin does not match" in res_evil_origin.json()["detail"]

        # 5. Matching KANBAN_PUBLIC_ORIGIN succeeds
        res_good_origin = await client.post(
            "/api/v1/protected",
            headers={
                "host": "testserver",
                "origin": "https://kanban.example.com",
                CSRF_HEADER_NAME: tok1,
            },
            cookies={CSRF_COOKIE_NAME: tok1},
        )
        assert res_good_origin.status_code == 200
        assert res_good_origin.json()["status"] == "protected_ok"

        # 6. Safe method GET on protected endpoint
        res_get = await client.get("/api/v1/protected")
        assert res_get.status_code in {405, 200}

    # Test resolver invocation inside CsrfMiddleware
    app_with_resolver = FastAPI()
    app_with_resolver.add_middleware(CsrfMiddleware, session_hmac_key=hmac_key)
    res_sess_id = uuid.uuid4()

    class MockResolver:
        async def resolve(self, _req: Request) -> PrincipalContext | None:
            return PrincipalContext(
                principal_id=uuid.uuid4(),
                workspace_id=uuid.uuid4(),
                session_id=res_sess_id,
            )

    app_with_resolver.state.principal_resolver = MockResolver()

    @app_with_resolver.post("/api/v1/action")
    async def act() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    transport_res = httpx.ASGITransport(app=app_with_resolver)
    tok_res = generate_csrf_token(res_sess_id, hmac_key)
    async with httpx.AsyncClient(transport=transport_res, base_url="http://testserver") as cl:
        r = await cl.post(
            "/api/v1/action",
            headers={"host": "testserver", CSRF_HEADER_NAME: tok_res},
            cookies={CSRF_COOKIE_NAME: tok_res},
        )
        assert r.status_code == 200

    # Middleware fallback when key_material is missing
    app_no_km = FastAPI()
    app_no_km.add_middleware(CsrfMiddleware)
    req = Request({"type": "http", "app": app_no_km, "headers": []})
    mw = CsrfMiddleware(app_no_km)
    assert mw._get_key(req) == b"\x00" * 32  # noqa: SLF001


@pytest.mark.asyncio
async def test_csrf_fallback_cookie_and_scope_branches(hmac_key: bytes) -> None:
    """Verify fallback cookies, non-http scopes, metadata fallbacks, and state principal."""
    # 1. Fallback cookie headers
    set_fb = build_set_fallback_csrf_cookie_header("fb_token")
    assert f"{FALLBACK_CSRF_COOKIE_NAME}=fb_token" in set_fb
    assert "SameSite=Strict" in set_fb

    clear_fb = build_clear_fallback_csrf_cookie_header()
    assert f"{FALLBACK_CSRF_COOKIE_NAME}=" in clear_fb
    assert "Max-Age=0" in clear_fb

    # 2. extract_csrf_cookie with fallback cookie and matching header
    req_fb = Request(
        {
            "type": "http",
            "headers": [
                (b"cookie", f"{FALLBACK_CSRF_COOKIE_NAME}=fb_val".encode()),
                (b"x-csrf-token", b"fb_val"),
            ],
        }
    )
    assert extract_csrf_cookie(req_fb) == "fb_val"

    req_fb_no_match = Request(
        {
            "type": "http",
            "headers": [
                (b"cookie", f"{FALLBACK_CSRF_COOKIE_NAME}=fb_val".encode()),
                (b"x-csrf-token", b"other_val"),
            ],
        }
    )
    assert extract_csrf_cookie(req_fb_no_match) == "fb_val"

    # 3. Non-http scope in CsrfMiddleware
    app = FastAPI()
    mw = CsrfMiddleware(app, session_hmac_key=hmac_key)
    ws_scope = {"type": "websocket"}
    called = False

    async def mock_app(_s: Scope, _r: Receive, _snd: Send) -> None:
        nonlocal called
        called = True

    async def dummy_rcv() -> dict[str, Any]:
        return {}

    async def dummy_snd(_: object) -> None:
        pass

    mw.app = mock_app
    await mw(ws_scope, dummy_rcv, dummy_snd)
    assert called is True

    # 4. Metadata validation when host header is missing
    req_no_host = Request({"type": "http", "headers": [(b"origin", b"https://some.origin")]})
    assert mw._validate_metadata(req_no_host) is not None  # noqa: SLF001

    # 5. Metadata validation using settings.public_origin fallback
    orig_pub = get_settings().public_origin
    try:
        object.__setattr__(get_settings(), "public_origin", "https://settings.kanban.test")
        req_settings = Request(
            {
                "type": "http",
                "path": "/",
                "headers": [
                    (b"host", b"kanban.internal"),
                    (b"origin", b"https://settings.kanban.test"),
                ],
            }
        )
        assert mw._validate_metadata(req_settings) is None  # noqa: SLF001
    finally:
        object.__setattr__(get_settings(), "public_origin", orig_pub)

    # 6. Principal on request.state fallback in _resolve_session_id
    test_sid = uuid.uuid4()
    req_princ = Request({"type": "http", "path": "/", "app": app, "headers": []})
    req_princ.state.principal = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        session_id=test_sid,
    )
    resolved_sess = await mw._resolve_session_id(req_princ)  # noqa: SLF001
    assert resolved_sess == test_sid


@pytest.mark.asyncio
async def test_csrf_token_bypass_and_login_branches(hmac_key: bytes) -> None:
    """Verify subject/internal tokens bypass and login pre-session token grace."""
    app2 = FastAPI()
    app2.add_middleware(CsrfMiddleware, session_hmac_key=hmac_key)

    @app2.post("/api/v1/agent-endpoint")
    async def agent_act() -> JSONResponse:
        return JSONResponse({"status": "agent_ok"})

    transport = httpx.ASGITransport(app=app2, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Subject token bypass
        res_subj = await client.post(
            "/api/v1/agent-endpoint",
            headers={"x-kb-subject-token": "kb_agt_test"},
        )
        assert res_subj.status_code == 200

        # Internal auth bypass
        res_int = await client.post(
            "/api/v1/agent-endpoint",
            headers={"x-kb-internal-auth": "secret-internal"},
        )
        assert res_int.status_code == 200

        # Pre-session token on /api/v1/auth/local/login with active session
        pre_token = generate_csrf_token(PRE_SESSION_ID, hmac_key)

        @app2.post("/api/v1/auth/local/login")
        async def login_act() -> JSONResponse:
            return JSONResponse({"status": "logged_in"})

        class SessionInjector:
            def __init__(self, inner: ASGIApp) -> None:
                self.inner = inner

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                if scope["type"] == "http":
                    scope["state"] = {"session_id": uuid.uuid4()}
                await self.inner(scope, receive, send)

        app_login = SessionInjector(app2)
        trans_login = httpx.ASGITransport(app=app_login, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=trans_login, base_url="http://testserver"
        ) as cl_login:
            res_login = await cl_login.post(
                "/api/v1/auth/local/login",
                headers={
                    "host": "testserver",
                    CSRF_HEADER_NAME: pre_token,
                },
                cookies={CSRF_COOKIE_NAME: pre_token},
            )
            assert res_login.status_code == 200


@pytest.mark.anyio
async def test_csrf_middleware_dead_session_clears_cookies(hmac_key: bytes) -> None:
    """Verify that dead session on CSRF failure clears cookies and reissues pre-session CSRF."""
    app = FastAPI()
    app.add_middleware(CsrfMiddleware, session_hmac_key=hmac_key)

    @app.post("/api/v1/protected")
    async def protected_act() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Request with a dead session cookie and invalid CSRF token
        res = await client.post(
            "/api/v1/protected",
            headers={
                "host": "testserver",
                CSRF_HEADER_NAME: "invalid-token",
            },
            cookies={
                "__Host-kb_session": "dead.cookie.token.value",
                CSRF_COOKIE_NAME: "invalid-token",
            },
        )
        assert res.status_code == 403
        set_cookies = res.headers.get_list("set-cookie")
        # Should clear session cookie and set fresh pre-session CSRF cookie
        cookie_text = " ".join(set_cookies)
        assert "Max-Age=0" in cookie_text or "kb_session=" in cookie_text
        assert CSRF_COOKIE_NAME in cookie_text or FALLBACK_CSRF_COOKIE_NAME in cookie_text

    # Request to /api/v1/setup/claim with dead session cookie and valid pre-session token
    @app.post("/api/v1/setup/claim")
    async def claim_act() -> JSONResponse:
        return JSONResponse({"status": "claimed"})

    pre_tok = generate_csrf_token(PRE_SESSION_ID, hmac_key)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res_claim = await client.post(
            "/api/v1/setup/claim",
            headers={
                "host": "testserver",
                CSRF_HEADER_NAME: pre_tok,
            },
            cookies={
                "__Host-kb_session": "dead.cookie.token.value",
                CSRF_COOKIE_NAME: pre_tok,
            },
        )
        assert res_claim.status_code == 200
        set_cookies_claim = res_claim.headers.get_list("set-cookie")
        assert any("Max-Age=0" in c for c in set_cookies_claim)


def test_verify_same_origin_request_origin_null_referrer_policy() -> None:
    """Validate verify_same_origin_request handling of Origin: null.

    Under Referrer-Policy: no-referrer, accept null origin only with same-origin site.
    """
    # 1. Origin: null with Sec-Fetch-Site: same-origin is accepted
    req_null_same = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"sec-fetch-site", b"same-origin"),
                (b"origin", b"null"),
            ],
        }
    )
    assert verify_same_origin_request(req_null_same) is True

    # 2. Origin: null with Sec-Fetch-Site: cross-site is rejected
    req_null_cross = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"sec-fetch-site", b"cross-site"),
                (b"origin", b"null"),
            ],
        }
    )
    assert verify_same_origin_request(req_null_cross) is False

    # 3. Origin: null with Sec-Fetch-Site: none is rejected
    req_null_none = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"sec-fetch-site", b"none"),
                (b"origin", b"null"),
            ],
        }
    )
    assert verify_same_origin_request(req_null_none) is False

    # 4. Origin: null with missing Sec-Fetch-Site is rejected
    req_null_missing = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "path": "/oauth/authorize/decision",
            "headers": [
                (b"host", b"127.0.0.1:8000"),
                (b"origin", b"null"),
            ],
        }
    )
    assert verify_same_origin_request(req_null_missing) is False
