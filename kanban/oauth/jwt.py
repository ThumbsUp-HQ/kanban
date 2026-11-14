# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OAuth 2.1 access token minting and verification using ES256 and joserfc (KB-P4-02b)."""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any, Final

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from joserfc import errors as joserfc_errors
from joserfc import jwt
from joserfc.jwk import ECKey

from kanban.security.keys import derive_subkey, load_key_material

if TYPE_CHECKING:
    from collections.abc import Sequence

ACCESS_TOKEN_TTL_SECONDS: Final[int] = 900
P256_ORDER: Final[int] = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


class OAuthTokenError(Exception):
    """Base exception for OAuth access token validation failures."""

    def __init__(self, message: str, code: str = "invalid_token") -> None:
        """Initialize token error with description and error code."""
        super().__init__(message)
        self.code = code


def _get_signing_eckey() -> tuple[ECKey, str]:
    """Derive deterministic P-256 EC signing key from master KEK."""
    km = load_key_material()
    subkey = derive_subkey(km.master_kek, "oauth-jwt-signing-v1")
    val = int.from_bytes(subkey, "big")
    val = (val % (P256_ORDER - 1)) + 1
    priv_key = ec.derive_private_key(val, ec.SECP256R1())
    pem = priv_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    kid = f"oauth-{km.master_kek_kid}"
    key = ECKey.import_key(pem)
    return key, kid


def get_jwks() -> dict[str, Any]:
    """Return public JWKS for OAuth authorization server (/oauth/jwks.json)."""
    key, kid = _get_signing_eckey()
    pub_dict = key.as_dict(private=False)
    pub_dict["use"] = "sig"
    pub_dict["alg"] = "ES256"
    pub_dict["kid"] = kid
    return {"keys": [pub_dict]}


def mint_access_token(  # noqa: PLR0913, PLR0917
    issuer: str,
    subject: str | uuid.UUID,
    audience: str,
    surface: str,
    scopes: Sequence[str],
    client_id: str,
    grant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    allowed_projects: Sequence[uuid.UUID] | None = None,
    ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """Mint a signed ES256 JWT access token bound to a single surface audience."""
    current_time = int(time.time() if now is None else now)
    key, kid = _get_signing_eckey()

    header = {
        "alg": "ES256",
        "typ": "JWT",
        "kid": kid,
    }
    jti = str(uuid.uuid4())
    claims: dict[str, Any] = {
        "iss": issuer,
        "sub": str(subject),
        "aud": audience,
        "surface": surface,
        "scope": " ".join(scopes),
        "client_id": client_id,
        "grant_id": str(grant_id),
        "ws": str(workspace_id),
        "jti": jti,
        "iat": current_time,
        "exp": current_time + ttl_seconds,
    }
    if allowed_projects:
        claims["allowed_projects"] = [str(p) for p in allowed_projects]

    return jwt.encode(header, claims, key)


def verify_access_token(
    token: str,
    expected_surface_url: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Verify an ES256 JWT access token and return validated claims dict."""
    current_time = time.time() if now is None else now
    key, _ = _get_signing_eckey()
    pub_key = ECKey.import_key(key.as_dict(private=False))

    try:
        token_obj = jwt.decode(token, pub_key)
    except (joserfc_errors.JoseError, ValueError) as err:
        msg = f"Invalid token signature or encoding: {err}"
        raise OAuthTokenError(msg, code="invalid_token") from err

    header = token_obj.header
    if header.get("alg") != "ES256":
        msg = f"Forbidden algorithm {header.get('alg')}, ES256 required"
        raise OAuthTokenError(msg, code="invalid_token")

    claims = dict(token_obj.claims)
    exp = claims.get("exp")
    if exp is None or not isinstance(exp, (int, float)):
        msg = "Token missing valid exp claim"
        raise OAuthTokenError(msg, code="invalid_token")

    if current_time >= float(exp):
        msg = "Token has expired"
        raise OAuthTokenError(msg, code="invalid_token")

    if expected_surface_url is not None:
        aud = claims.get("aud")
        if aud != expected_surface_url:
            msg = f"Audience mismatch: expected {expected_surface_url}, got {aud}"
            raise OAuthTokenError(msg, code="SURFACE_KEY_MISMATCH")

    return claims
