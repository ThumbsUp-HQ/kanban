# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SSRF-safe workload identity federation token validation (KB-AUTH-OIDC-EXCHANGE-01, KAN-74)."""

from __future__ import annotations

import base64
import fnmatch
import json
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import httpx  # noqa: TC002
from joserfc import errors as joserfc_errors
from joserfc import jwt
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.models.workload_identity import WorkloadIdentityPolicy, WorkloadJtiReplay
from kanban.auth.oidc.discovery import JwksCache, OidcError, fetch_discovery
from kanban.oauth.server import OAuth2Error

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_SIGNING_ALGORITHMS: Final[frozenset[str]] = frozenset({"RS256", "PS256", "ES256", "EdDSA"})
MAX_CLOCK_SKEW_OR_AGE_SECONDS: Final[float] = 600.0
CLOCK_SKEW_LEEWAY_SECONDS: Final[float] = 60.0

ERR_INVALID_GRANT: Final[str] = "invalid_grant"
ERR_TOKEN_REPLAYED: Final[str] = "WORKLOAD_TOKEN_REPLAYED"  # noqa: S105
ERR_JSON_ROOT_NOT_OBJECT: Final[str] = "JSON root must be an object"

_workload_jwks_cache: JwksCache | None = None
_test_workload_client: httpx.AsyncClient | None = None


def get_workload_jwks_cache() -> JwksCache:
    """Retrieve or construct the process-level workload JWKS cache."""
    global _workload_jwks_cache  # noqa: PLW0603
    if _workload_jwks_cache is None:
        _workload_jwks_cache = JwksCache()
    return _workload_jwks_cache


def _extract_unverified_header_and_claims(raw_jwt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract header and claims dictionaries from raw JWT without signature verification."""
    parts = raw_jwt.strip().split(".")
    if len(parts) != 3:  # noqa: PLR2004
        msg = "Malformed JWT: expected 3 dot-separated segments"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)

    def _b64_decode(segment: str) -> dict[str, Any]:
        rem = len(segment) % 4
        padded = segment + ("=" * (4 - rem) if rem else "")
        try:
            data = base64.urlsafe_b64decode(padded.encode("ascii"))
            res = json.loads(data.decode("utf-8"))
        except Exception as err:
            msg = f"Failed to parse JWT segment: {err}"
            raise OAuth2Error(ERR_INVALID_GRANT, msg, 400) from err
        if not isinstance(res, dict):
            msg = "Failed to parse JWT segment: JSON root must be an object"
            raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)
        return res

    header = _b64_decode(parts[0])
    claims = _b64_decode(parts[1])
    return header, claims


async def validate_workload_jwt(  # noqa: C901, PLR0912, PLR0913, PLR0915
    session: AsyncSession,
    raw_jwt: str,
    policy: WorkloadIdentityPolicy,
    *,
    client: httpx.AsyncClient | None = None,
    jwks_cache: JwksCache | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Validate external OIDC JWT against a WorkloadIdentityPolicy.

    Reuses fetch_discovery and JwksCache. Enforces:
    - Allowed algorithms: RS256, PS256, ES256, EdDSA (none and HS* strictly forbidden).
    - Signature verification via discovered JWKS keyset.
    - Issuer exact byte-for-byte match against policy.issuer.
    - Audience match against policy.client_id.
    - Expiration (exp) and not-before (nbf) timing validity.
    - Issued-at (iat) within <= 600 seconds clock skew / age.
    - Subject (sub) glob or exact match against policy.subject_pattern.
    - Required claims exact match against policy.required_claims_json.
    - Atomic workload_jti_replays insertion with 401 WORKLOAD_TOKEN_REPLAYED on duplicate.
    """
    current_time = time.time() if now is None else now
    header, _ = _extract_unverified_header_and_claims(raw_jwt)

    alg = str(header.get("alg", ""))
    if not alg or alg == "none" or alg.startswith("HS") or alg not in ALLOWED_SIGNING_ALGORITHMS:
        msg = (
            f"Forbidden or unsupported signing algorithm '{alg}'; "
            f"allowed: {sorted(ALLOWED_SIGNING_ALGORITHMS)}"
        )
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)

    # 1. Fetch discovery and JWKS keyset
    effective_client = client or _test_workload_client
    cache = jwks_cache or get_workload_jwks_cache()
    try:
        discovery_doc = await fetch_discovery(policy.issuer, client=effective_client)
        kid = header.get("kid")
        keyset = await cache.get_keyset(
            policy.id,
            discovery_doc.jwks_uri,
            kid=str(kid) if kid is not None else None,
            client=effective_client,
            now=current_time,
        )
    except OidcError as err:
        msg = f"OIDC discovery/JWKS resolution failed: {err.message}"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400) from err

    # 2. Cryptographic signature and envelope decoding
    try:
        token_obj = jwt.decode(
            raw_jwt,
            keyset,
            algorithms=list(ALLOWED_SIGNING_ALGORITHMS),
        )
        claims = dict(token_obj.claims)
    except (joserfc_errors.JoseError, ValueError) as err:
        msg = f"JWT signature validation failed: {err}"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400) from err

    # 3. Enforce iss match
    token_iss = claims.get("iss")
    configured_iss = policy.issuer.rstrip("/")
    if token_iss is None or str(token_iss).rstrip("/") != configured_iss:
        msg = f"Token issuer '{token_iss}' does not match policy issuer '{policy.issuer}'"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)

    # 4. Enforce aud match
    token_aud = claims.get("aud")
    if token_aud is None:
        msg = "Token missing aud claim"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)
    if isinstance(token_aud, str):
        aud_matched = token_aud == policy.client_id
    elif isinstance(token_aud, list):
        aud_matched = policy.client_id in [str(a) for a in token_aud]
    else:
        aud_matched = False
    if not aud_matched:
        msg = f"Token audience '{token_aud}' does not match policy client_id '{policy.client_id}'"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)

    # 5. Enforce exp
    token_exp = claims.get("exp")
    if token_exp is None or not isinstance(token_exp, (int, float)):
        msg = "Token missing valid numeric exp claim"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)
    if current_time >= float(token_exp):
        msg = "Token has expired"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)

    # 6. Enforce nbf if present
    token_nbf = claims.get("nbf")
    if (
        token_nbf is not None
        and isinstance(token_nbf, (int, float))
        and current_time + CLOCK_SKEW_LEEWAY_SECONDS < float(token_nbf)
    ):
        msg = "Token not yet valid (nbf)"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)

    # 7. Enforce iat (<= 600s clock skew / age)
    token_iat = claims.get("iat")
    if token_iat is None or not isinstance(token_iat, (int, float)):
        msg = "Token missing valid numeric iat claim"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)
    token_age = current_time - float(token_iat)
    if token_age > MAX_CLOCK_SKEW_OR_AGE_SECONDS or token_age < -CLOCK_SKEW_LEEWAY_SECONDS:
        msg = (
            f"Token age/skew ({token_age:.1f}s) exceeds maximum allowed "
            f"{MAX_CLOCK_SKEW_OR_AGE_SECONDS}s"
        )
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)

    # 8. Enforce sub pattern match
    token_sub = claims.get("sub")
    if not token_sub or not isinstance(token_sub, str):
        msg = "Token missing valid string sub claim"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)
    pattern = policy.subject_pattern
    if "*" in pattern or "?" in pattern:
        sub_matched = fnmatch.fnmatchcase(token_sub, pattern)
    else:
        sub_matched = token_sub == pattern
    if not sub_matched:
        msg = f"Token subject '{token_sub}' does not match policy pattern '{pattern}'"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)

    # 9. Enforce required_claims_json
    required_claims = policy.required_claims_json or {}
    if isinstance(required_claims, dict):
        for req_k, req_v in required_claims.items():
            if req_k not in claims:
                msg = f"Token missing required claim '{req_k}'"
                raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)
            token_val = claims[req_k]
            if isinstance(req_v, list) and isinstance(token_val, list):
                if not set(req_v).issubset(set(token_val)):
                    msg = (
                        f"Claim '{req_k}' value mismatch: required subset "
                        f"'{req_v}', got '{token_val}'"
                    )
                    raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)
            elif token_val != req_v:
                msg = f"Claim '{req_k}' value mismatch: expected '{req_v}', got '{token_val}'"
                raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)

    # 10. Enforce jti & atomic replay prevention
    token_jti = claims.get("jti")
    if not token_jti or not isinstance(token_jti, str):
        msg = "Token missing valid string jti claim"
        raise OAuth2Error(ERR_INVALID_GRANT, msg, 400)

    stmt_replay = (
        pg_insert(WorkloadJtiReplay)
        .values(
            workspace_id=policy.workspace_id,
            policy_id=policy.id,
            jti=token_jti,
            expires_at=datetime.fromtimestamp(float(token_exp), tz=UTC),
        )
        .on_conflict_do_nothing(index_elements=["policy_id", "jti"])
        .returning(WorkloadJtiReplay.id)
    )
    res_replay = (await session.execute(stmt_replay)).scalar_one_or_none()
    if res_replay is None:
        # Replay detected!
        msg = f"Workload token JTI '{token_jti}' has already been exchanged"
        raise OAuth2Error(ERR_TOKEN_REPLAYED, msg, 401)

    return claims
