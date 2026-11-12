# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""JWT validation and private_key_jwt generation for OIDC/OAuth2 authentication (KB-P2-06)."""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import TYPE_CHECKING, Any, Final

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from joserfc import jwt
from joserfc.jwk import ECKey, KeySet, RSAKey

from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    from collections.abc import Sequence

JWT_COMPACT_PARTS_COUNT: Final[int] = 3
DEFAULT_CLOCK_SKEW_SECONDS: Final[float] = 60.0
MAX_IAT_AGE_SECONDS: Final[float] = 600.0


def build_private_key_jwt(
    client_id: str,
    token_endpoint: str,
    private_key_pem: bytes | str,
    now: float | None = None,
) -> str:
    """Build and sign an asymmetric client_assertion JWT (RFC 7523) for private_key_jwt."""
    pem_bytes = (
        private_key_pem.encode("utf-8") if isinstance(private_key_pem, str) else private_key_pem
    )

    # Load cryptographic key to determine type
    loaded_key = serialization.load_pem_private_key(pem_bytes, password=None)

    signing_key: RSAKey | ECKey
    if isinstance(loaded_key, rsa.RSAPrivateKey):
        alg = "RS256"
        signing_key = RSAKey.import_key(pem_bytes)
    elif isinstance(loaded_key, ec.EllipticCurvePrivateKey):
        alg = "ES256"
        signing_key = ECKey.import_key(pem_bytes)
    else:
        msg = f"Unsupported private key type: {type(loaded_key).__name__}"
        raise TypeError(msg)

    current_time = int(time.time() if now is None else now)

    header = {
        "alg": alg,
        "typ": "JWT",
    }
    claims = {
        "iss": client_id,
        "sub": client_id,
        "aud": token_endpoint,
        "jti": str(uuid.uuid4()),
        "iat": current_time,
        "exp": current_time + 60,
    }

    return jwt.encode(header, claims, signing_key)


def validate_id_token(  # noqa: C901, PLR0912, PLR0913, PLR0915
    id_token: str,
    jwks: KeySet,
    *,
    issuer: str,
    client_id: str,
    expected_nonce: bytes,
    allowed_algs: Sequence[str],
    now: float | None = None,
) -> dict[str, Any]:
    """Rigorously validate an OIDC ID token using joserfc and pinned invariants (S4.2).

    Enforces:
    - Algorithm allowlist matching (rejects 'none', HS*, unapproved algs)
    - Rejection of external header references (jku, x5u, jwk)
    - Signature validation against pinned JWKS keyset
    - Byte-for-byte issuer match
    - Audience inclusion of client_id, and azp pinning for multi-audience tokens
    - 60s clock skew on exp/iat/nbf, iat not older than 600s
    - Single-use nonce match
    """
    parts = id_token.strip().split(".")
    if len(parts) != JWT_COMPACT_PARTS_COUNT:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="ID token does not conform to compact serialization format",
        )

    # Inspect unverified header for algorithm and prohibited parameters
    try:
        header_raw = parts[0]
        padding = "=" * (-len(header_raw) % 4)
        header_bytes = base64.urlsafe_b64decode(header_raw + padding)
        header = json.loads(header_bytes)
    except Exception as err:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Failed to parse ID token header",
        ) from err

    alg = header.get("alg")
    if not alg or alg == "none":
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Algorithm 'none' is strictly prohibited",
        )

    if alg.startswith("HS"):
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Symmetric HMAC algorithms are strictly prohibited for ID tokens",
        )

    if alg not in allowed_algs:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail=f"Token algorithm '{alg}' is not in allowed algorithms",
        )

    # Reject untrusted header key lookups
    if any(param in header for param in ("jku", "x5u", "jwk")):
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Header key reference parameters (jku, x5u, jwk) are prohibited",
        )

    # Verify signature against pinned JWKS
    try:
        token_obj = jwt.decode(id_token, jwks, algorithms=allowed_algs)
        claims = dict(token_obj.claims)
    except Exception as err:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Token signature or structure validation failed",
        ) from err

    # 1. Pinned issuer validation (byte-for-byte match)
    token_iss = claims.get("iss")
    if token_iss != issuer:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail=f"Token issuer '{token_iss}' does not match expected issuer '{issuer}'",
        )

    # 2. Audience & authorized party (azp) validation
    aud = claims.get("aud")
    if aud is None:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Token missing required 'aud' claim",
        )

    aud_list: list[str] = [str(aud)] if isinstance(aud, (str, int)) else [str(a) for a in aud]
    if client_id not in aud_list:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Client ID is not present in token audience",
        )

    azp = claims.get("azp")
    if len(aud_list) > 1 and azp != client_id:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Multi-audience token requires azp matching client_id",
        )
    if azp is not None and azp != client_id:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail=f"Token azp '{azp}' does not match client_id",
        )

    # 3. Timestamps & clock skew validation (60s skew permitted)
    now_ts = time.time() if now is None else now
    clock_skew = 60.0

    exp = claims.get("exp")
    if exp is None:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Token missing required 'exp' claim",
        )
    try:
        exp_val = float(exp)
    except (ValueError, TypeError) as err:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Invalid 'exp' claim format",
        ) from err

    if now_ts > exp_val + clock_skew:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="ID token has expired",
        )

    iat = claims.get("iat")
    if iat is None:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Token missing required 'iat' claim",
        )
    try:
        iat_val = float(iat)
    except (ValueError, TypeError) as err:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Invalid 'iat' claim format",
        ) from err

    if now_ts < iat_val - clock_skew:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Token issued in the future beyond acceptable clock skew",
        )

    # Max age: iat cannot be older than 600s
    if now_ts > iat_val + 600.0:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Token iat is older than 600 seconds",
        )

    nbf = claims.get("nbf")
    if nbf is not None:
        try:
            nbf_val = float(nbf)
            if now_ts < nbf_val - clock_skew:
                raise ProblemException(
                    code="OIDC_TOKEN_INVALID",
                    status=401,
                    title="Invalid ID Token",
                    detail="Token not yet valid",
                )
        except (ValueError, TypeError) as err:
            raise ProblemException(
                code="OIDC_TOKEN_INVALID",
                status=401,
                title="Invalid ID Token",
                detail="Invalid 'nbf' claim format",
            ) from err

    # 4. Nonce validation
    token_nonce = claims.get("nonce")
    if token_nonce is None:
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Token missing required 'nonce' claim",
        )

    expected_b64 = base64.urlsafe_b64encode(expected_nonce).rstrip(b"=").decode("ascii")
    expected_hex = expected_nonce.hex()
    expected_raw = expected_nonce.decode("latin-1", errors="ignore")

    if str(token_nonce) not in (expected_b64, expected_hex, expected_raw):
        raise ProblemException(
            code="OIDC_TOKEN_INVALID",
            status=401,
            title="Invalid ID Token",
            detail="Token nonce does not match stored authorization request nonce",
        )

    return claims
