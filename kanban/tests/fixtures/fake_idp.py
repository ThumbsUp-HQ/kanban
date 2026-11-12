# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""In-memory fake OIDC and OAuth2 Identity Provider served via httpx.MockTransport (KB-P2-06)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc import jwt
from joserfc.jwk import RSAKey

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class IssuedAuthCode:
    """Authorization code issued by FakeIdP with bound client parameters."""

    code: str
    client_id: str
    redirect_uri: str
    scope: str
    state: str
    nonce: str | None
    code_challenge: str
    code_challenge_method: str
    issued_at: float = field(default_factory=time.time)


class FakeIdP:
    """In-memory ASGI mock IdP providing discovery, JWKS, token exchange, and userinfo."""

    def __init__(
        self,
        issuer: str = "https://idp.example.com",
        client_id: str = "test-client-id",
        client_secret: str = "test-client-secret",  # noqa: S107
    ) -> None:
        """Initialize FakeIdP with RSA key pair and default endpoints."""
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.kid = "fake-key-1"

        # Generate RSA signing key for ID tokens
        self._rsa_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self._priv_pem = self._rsa_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._pub_pem = self._rsa_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        self._jwk = RSAKey.import_key(
            self._priv_pem, {"kid": self.kid, "use": "sig", "alg": "RS256"}
        )
        self._pub_jwk_dict = self._jwk.as_dict(private=False)

        # State tracking
        self.issued_codes: dict[str, IssuedAuthCode] = {}
        self.observed_authorizations: list[dict[str, str]] = []
        self.observed_token_requests: list[dict[str, Any]] = []
        self.observed_assertions: list[dict[str, Any]] = []
        self.jwks_fetch_count: int = 0

        # Endpoint hooks / overrides for fault simulation
        self.discovery_override: Callable[[httpx.Request], httpx.Response | None] | None = None
        self.jwks_override: Callable[[httpx.Request], httpx.Response | None] | None = None
        self.token_override: (
            Callable[[httpx.Request, dict[str, str]], httpx.Response | None] | None
        ) = None
        self.userinfo_override: Callable[[httpx.Request], httpx.Response | None] | None = None

        # Userinfo payload
        self.userinfo_data: dict[str, Any] = {
            "sub": "user-4242",
            "id": 4242,
            "email": "user4242@example.com",
            "email_verified": True,
            "name": "Jane User",
        }

        # Client public key for verifying private_key_jwt assertions
        self.client_public_key_pem: bytes | None = None

    @property
    def rsa_private_key_pem(self) -> bytes:
        """Return IdP private key in PEM format."""
        return self._priv_pem

    @property
    def rsa_public_key_pem(self) -> bytes:
        """Return IdP public key in PEM format."""
        return self._pub_pem

    @property
    def jwk_public_dict(self) -> dict[str, Any]:
        """Return IdP public key dictionary formatted for JWKS."""
        return dict(self._pub_jwk_dict)

    def create_id_token(  # noqa: PLR0913
        self,
        subject: str = "user-4242",
        *,
        client_id: str | None = None,
        nonce: str | None = None,
        issuer: str | None = None,
        audience: str | list[str] | None = None,
        azp: str | None = None,
        alg: str = "RS256",
        iat: int | None = None,
        exp: int | None = None,
        nbf: int | None = None,
        email: str | None = "user4242@example.com",
        email_verified: bool = True,
        custom_claims: dict[str, Any] | None = None,
        custom_header: dict[str, Any] | None = None,
        signing_key: Any | None = None,  # noqa: ANN401
    ) -> str:
        """Generate and sign an ID token JWT."""
        now = int(time.time())
        token_iat = now if iat is None else iat
        token_exp = now + 3600 if exp is None else exp
        token_aud = (client_id or self.client_id) if audience is None else audience
        token_iss = self.issuer if issuer is None else issuer

        header = {"alg": alg, "typ": "JWT", "kid": self.kid}
        if custom_header:
            header.update(custom_header)

        claims: dict[str, Any] = {
            "iss": token_iss,
            "sub": subject,
            "aud": token_aud,
            "iat": token_iat,
            "exp": token_exp,
        }
        if nbf is not None:
            claims["nbf"] = nbf
        if nonce is not None:
            claims["nonce"] = nonce
        if azp is not None:
            claims["azp"] = azp
        if email is not None:
            claims["email"] = email
            claims["email_verified"] = email_verified
        if custom_claims:
            claims.update(custom_claims)

        key = self._jwk if signing_key is None else signing_key
        return jwt.encode(header, claims, key)

    def authorize_url_for_params(  # noqa: PLR0913, PLR0917
        self,
        client_id: str,
        redirect_uri: str,
        state: str,
        nonce: str | None = None,
        code_challenge: str = "",
        code_challenge_method: str = "S256",
    ) -> str:
        """Simulate IdP authorization and return callback URL with issued code."""
        code = f"authcode-{secrets.token_hex(8)}"
        self.issued_codes[code] = IssuedAuthCode(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope="openid",
            state=state,
            nonce=nonce,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )
        return f"{redirect_uri}?code={code}&state={state}"

    async def handle_request(self, request: httpx.Request) -> httpx.Response:  # noqa: C901, PLR0911, PLR0912, PLR0915
        """Handle incoming HTTP request and route to appropriate mock endpoint."""
        path = request.url.path

        # 1. Discovery document
        if path == "/.well-known/openid-configuration":
            if self.discovery_override is not None:
                resp = self.discovery_override(request)
                if resp is not None:
                    return resp

            doc = {
                "issuer": self.issuer,
                "authorization_endpoint": f"{self.issuer}/oauth/authorize",
                "token_endpoint": f"{self.issuer}/oauth/token",
                "jwks_uri": f"{self.issuer}/.well-known/jwks.json",
                "userinfo_endpoint": f"{self.issuer}/oauth/userinfo",
                "id_token_signing_alg_values_supported": ["RS256", "ES256"],
            }
            return httpx.Response(200, json=doc)

        # 2. JWKS endpoint
        if path == "/.well-known/jwks.json":
            self.jwks_fetch_count += 1
            if self.jwks_override is not None:
                resp = self.jwks_override(request)
                if resp is not None:
                    return resp

            jwks = {"keys": [self._pub_jwk_dict]}
            return httpx.Response(200, json=jwks)

        # 3. Authorization endpoint
        if path == "/oauth/authorize":
            params = dict(request.url.params)
            self.observed_authorizations.append(params)

            code = f"code-{secrets.token_hex(8)}"
            self.issued_codes[code] = IssuedAuthCode(
                code=code,
                client_id=params.get("client_id", ""),
                redirect_uri=params.get("redirect_uri", ""),
                scope=params.get("scope", ""),
                state=params.get("state", ""),
                nonce=params.get("nonce"),
                code_challenge=params.get("code_challenge", ""),
                code_challenge_method=params.get("code_challenge_method", ""),
            )

            redir_target = f"{params['redirect_uri']}?code={code}&state={params.get('state', '')}"
            return httpx.Response(302, headers={"Location": redir_target})

        # 4. Token endpoint
        if path == "/oauth/token":
            body_bytes = request.read()
            body_str = body_bytes.decode("utf-8")
            form_data = dict(urllib.parse.parse_qsl(body_str))

            if self.token_override is not None:
                resp = self.token_override(request, form_data)
                if resp is not None:
                    return resp

            self.observed_token_requests.append(
                {"headers": dict(request.headers), "form": form_data}
            )

            # Check client authentication
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Basic "):
                b64_creds = auth_header.split(" ", 1)[1]
                try:
                    creds = base64.b64decode(b64_creds).decode("utf-8")
                    c_id, c_secret = creds.split(":", 1)
                    if c_id != self.client_id or c_secret != self.client_secret:
                        return httpx.Response(401, json={"error": "invalid_client"})
                except (ValueError, binascii.Error, UnicodeDecodeError):
                    return httpx.Response(401, json={"error": "invalid_client"})
            elif (
                form_data.get("client_assertion_type")
                == "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
            ):
                assertion = form_data.get("client_assertion", "")
                if self.client_public_key_pem is not None:
                    client_key = RSAKey.import_key(self.client_public_key_pem)
                    decoded = jwt.decode(assertion, client_key, algorithms=["RS256", "ES256"])
                    self.observed_assertions.append(dict(decoded.claims))
                else:
                    # Parse unverified claims for assertion tracking
                    parts = assertion.split(".")
                    if len(parts) >= 2:
                        padding = "=" * (-len(parts[1]) % 4)
                        claims_raw = base64.urlsafe_b64decode(parts[1] + padding)
                        self.observed_assertions.append(json.loads(claims_raw))

            code_val = form_data.get("code")
            code_verifier = form_data.get("code_verifier", "")

            # Verify PKCE code_challenge if code was registered
            issued = self.issued_codes.get(code_val or "")
            if issued is not None and issued.code_challenge:
                computed_challenge = (
                    base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
                    .rstrip(b"=")
                    .decode("ascii")
                )
                if computed_challenge != issued.code_challenge:
                    return httpx.Response(
                        400,
                        json={
                            "error": "invalid_grant",
                            "error_description": "PKCE verification failed",
                        },
                    )

            # Issue tokens
            access_token = f"acc-{secrets.token_hex(16)}"
            stored_nonce = issued.nonce if issued else None
            id_token = self.create_id_token(nonce=stored_nonce)

            response_data = {
                "token_type": "Bearer",
                "access_token": access_token,
                "expires_in": 3600,
                "id_token": id_token,
            }
            return httpx.Response(200, json=response_data)

        # 5. Userinfo endpoint
        if path == "/oauth/userinfo":
            if self.userinfo_override is not None:
                resp = self.userinfo_override(request)
                if resp is not None:
                    return resp

            auth_hdr = request.headers.get("Authorization", "")
            if not auth_hdr.startswith("Bearer "):
                return httpx.Response(401, json={"error": "unauthorized"})

            return httpx.Response(200, json=self.userinfo_data)

        return httpx.Response(404, json={"error": f"Path not found: {path}"})

    def as_transport(self) -> httpx.MockTransport:
        """Return an httpx.MockTransport dispatching directly to handle_request."""
        return httpx.MockTransport(self.handle_request)

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,  # noqa: ANN401
        send: Any,  # noqa: ANN401
    ) -> None:
        """ASGI application interface for FakeIdP."""
        if scope["type"] != "http":
            return

        method = scope["method"]
        path = scope["path"]
        query_string = scope.get("query_string", b"").decode("latin-1")
        url_str = f"https://{scope.get('server', ('localhost', 443))[0]}{path}"
        if query_string:
            url_str += f"?{query_string}"

        headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in scope.get("headers", [])]

        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        httpx_req = httpx.Request(method, url_str, headers=headers, content=body)
        httpx_resp = await self.handle_request(httpx_req)

        await send(
            {
                "type": "http.response.start",
                "status": httpx_resp.status_code,
                "headers": [
                    (k.encode("latin-1"), v.encode("latin-1"))
                    for k, v in httpx_resp.headers.items()
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": httpx_resp.content,
            }
        )
