# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Role-bound HKDF-HMAC internal service authentication and verified mTLS peer checks.

Implements KB-SEC-CODEX-01 (KAN-63 / S11.1, S14.3):
- Derives per-role HKDF-SHA256 subkeys from master_kek:
  derive_subkey(km.master_kek, f"internal-service-v2/{principal}")
- Signs and verifies canonical request envelopes:
  ts + principal + method + path + sha256(body)
- Enforces <= 300s clock drift tolerance and constant-time HMAC comparison
- Supports verified ASGI TLS scope["client_cert"] X.509 CN/SAN extraction
- Never trusts raw HTTP identity headers (X-KB-Service-Principal, X-SSL-Client-Cert, etc.)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import urllib.parse
from typing import TYPE_CHECKING, Final, cast

from cryptography import x509
from cryptography.x509.oid import ExtensionOID, NameOID

from kanban.api.problems import ProblemException
from kanban.security.keys import KeyMaterial, KeyMaterialError, derive_subkey, load_key_material

if TYPE_CHECKING:
    from collections.abc import Collection

    from fastapi import Request

__all__ = [
    "INTERNAL_AUTH_DRIFT_SECONDS",
    "INTERNAL_AUTH_HEADER",
    "KNOWN_SERVICE_PRINCIPALS",
    "create_internal_service_auth_header",
    "derive_internal_service_key",
    "verify_internal_service_auth",
]

KNOWN_SERVICE_PRINCIPALS: Final[frozenset[str]] = frozenset(
    {"mcp-gateway", "agent-runtime", "kanban-api"}
)
INTERNAL_AUTH_HEADER: Final[str] = "X-KB-Internal-Auth"
INTERNAL_AUTH_DRIFT_SECONDS: Final[int] = 300

# Process-local CSPRNG fallback root key used only in in-process unit tests that do not
# configure KANBAN_KEYRING_FILE or KANBAN_MASTER_KEK environment variables.
_PROCESS_FALLBACK_KEK: Final[bytes] = secrets.token_bytes(32)


def _resolve_root_kek(key_material: KeyMaterial | None = None) -> bytes:
    """Resolve 32-byte root master_kek from explicit KeyMaterial, keyring/env, or test fallback."""
    if key_material is not None:
        return key_material.master_kek

    has_configured_source = bool(
        os.environ.get("KANBAN_KEYRING_FILE")
        or os.environ.get("KANBAN_MASTER_KEK")
        or os.environ.get("KB_MASTER_KEK_B64")
    )
    if has_configured_source:
        return load_key_material().master_kek

    try:
        return load_key_material().master_kek
    except KeyMaterialError:
        return _PROCESS_FALLBACK_KEK


def derive_internal_service_key(
    principal: str,
    *,
    key_material: KeyMaterial | None = None,
) -> bytes:
    """Derive a role-bound HKDF-SHA256 subkey for the given internal service principal."""
    if principal not in KNOWN_SERVICE_PRINCIPALS:
        msg = (
            f"Unknown internal service principal {principal!r}; "
            f"allowed: {sorted(KNOWN_SERVICE_PRINCIPALS)}"
        )
        raise ValueError(msg)

    root_kek = _resolve_root_kek(key_material)
    return derive_subkey(root_kek, f"internal-service-v2/{principal}")


def _normalize_method(method: str) -> str:
    return method.upper().strip() or "GET"


def _normalize_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(path.strip())
    return parsed.path or "/"


def _coerce_body_bytes(body_bytes: bytes | bytearray | memoryview | str | None) -> bytes:
    if body_bytes is None:
        return b""
    if isinstance(body_bytes, str):
        return body_bytes.encode("utf-8")
    return bytes(body_bytes)


def _build_canonical_message(
    timestamp: int,
    principal: str,
    method: str,
    path: str,
    body_bytes: bytes,
) -> bytes:
    norm_method = _normalize_method(method)
    norm_path = _normalize_path(path)
    body_sha256 = hashlib.sha256(body_bytes).hexdigest()
    return f"{timestamp}\n{principal}\n{norm_method}\n{norm_path}\n{body_sha256}".encode("ascii")


def create_internal_service_auth_header(  # noqa: PLR0913
    principal: str = "mcp-gateway",
    method: str = "POST",
    path: str = "/internal/v1/mcp/introspect",
    body_bytes: bytes | bytearray | memoryview | str | None = b"",
    *,
    timestamp: float | None = None,
    key_material: KeyMaterial | None = None,
) -> str:
    """Create a role-bound HKDF-HMAC X-KB-Internal-Auth header value.

    Format: t=<unix_ts>,p=<principal>,v2=<hex_hmac_sha256>
    """
    key = derive_internal_service_key(principal, key_material=key_material)
    ts = int(timestamp if timestamp is not None else time.time())
    raw_body = _coerce_body_bytes(body_bytes)
    msg = _build_canonical_message(ts, principal, method, path, raw_body)
    sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"t={ts},p={principal},v2={sig}"


def _match_candidate_principal(candidate: str) -> str | None:
    """Match an X.509 CN or SAN value to a known internal service principal."""
    val = candidate.strip().lower()
    if not val:
        return None
    if val in KNOWN_SERVICE_PRINCIPALS:
        return val
    for known in KNOWN_SERVICE_PRINCIPALS:
        if (
            val == f"{known}.internal"
            or val.startswith(f"{known}.")
            or val.endswith((f"/sa/{known}", f":{known}", f"/{known}"))
        ):
            return known
    return None


def _extract_candidates_from_dict(cert_dict: dict[object, object]) -> list[str]:
    """Extract CN and SAN candidate strings from a peer certificate dictionary."""
    candidates: list[str] = [
        raw_val
        for direct_key in ("cn", "common_name", "commonName", "principal")
        if isinstance((raw_val := cert_dict.get(direct_key)), str)
    ]

    raw_san = cert_dict.get("san") or cert_dict.get("subjectAltName")
    if isinstance(raw_san, (list, tuple)):
        for item in raw_san:
            if isinstance(item, str):
                candidates.append(item)
            elif (
                isinstance(item, tuple)
                and len(item) == 2  # noqa: PLR2004
                and isinstance(item[1], str)
            ):
                candidates.append(item[1])

    raw_subject = cert_dict.get("subject")
    if isinstance(raw_subject, (list, tuple)):
        for rdn in raw_subject:
            candidates.extend(
                attr[1]
                for attr in (rdn if isinstance(rdn, (list, tuple)) else ())
                if (
                    isinstance(attr, tuple)
                    and len(attr) == 2  # noqa: PLR2004
                    and attr[0] in ("commonName", "CN")
                    and isinstance(attr[1], str)
                )
            )
    return candidates


def _extract_candidates_from_x509(cert: x509.Certificate) -> list[str]:
    """Extract Subject CN and SAN DNS/URI entries from a cryptography.x509.Certificate."""
    candidates: list[str] = [
        str(attr.value) for attr in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    ]
    try:
        san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        san_val = cast("x509.SubjectAlternativeName", san_ext.value)
        candidates.extend(san_val.get_values_for_type(x509.DNSName))
        candidates.extend(san_val.get_values_for_type(x509.UniformResourceIdentifier))
    except x509.ExtensionNotFound:
        pass
    return candidates


def _extract_principal_from_client_cert(cert_obj: object) -> str | None:
    """Extract a verified service principal from ASGI TLS scope['client_cert']."""
    candidates: list[str] = []
    if isinstance(cert_obj, dict):
        candidates.extend(_extract_candidates_from_dict(cert_obj))
    elif isinstance(cert_obj, x509.Certificate):
        candidates.extend(_extract_candidates_from_x509(cert_obj))
    elif isinstance(cert_obj, (bytes, str)):
        pem_bytes = (
            cert_obj.encode("ascii", errors="ignore") if isinstance(cert_obj, str) else cert_obj
        )
        if b"-----BEGIN CERTIFICATE-----" in pem_bytes:
            try:
                parsed_cert = x509.load_pem_x509_certificate(pem_bytes)
            except ValueError:
                return None
            candidates.extend(_extract_candidates_from_x509(parsed_cert))

    for candidate in candidates:
        matched = _match_candidate_principal(candidate)
        if matched is not None:
            return matched
    return None


def _parse_and_verify_hmac_header(  # noqa: PLR0911, PLR0913
    header_val: str,
    *,
    method: str,
    path: str,
    body_bytes: bytes,
    max_drift_s: int,
    key_material: KeyMaterial | None,
) -> str | None:
    """Parse X-KB-Internal-Auth header and verify role-bound HKDF-HMAC signature."""
    parts: dict[str, str] = {}
    for raw_part in header_val.split(","):
        part = raw_part.strip()
        if "=" not in part:
            return None
        k, v = part.split("=", 1)
        k_clean = k.strip()
        if not k_clean or k_clean in parts:
            return None
        parts[k_clean] = v.strip()

    ts_str = parts.get("t")
    principal = parts.get("p")
    sig = parts.get("v2")
    if not ts_str or not principal or not sig:
        return None

    if principal not in KNOWN_SERVICE_PRINCIPALS:
        return None

    try:
        ts_float = float(ts_str)
        ts_int = int(ts_str)
    except ValueError:
        return None

    if abs(time.time() - ts_float) > max_drift_s:
        return None

    key = derive_internal_service_key(principal, key_material=key_material)
    msg = _build_canonical_message(ts_int, principal, method, path, body_bytes)
    expected_sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None

    return principal


def verify_internal_service_auth(
    request: Request,
    allowed_principals: Collection[str] = KNOWN_SERVICE_PRINCIPALS,
    *,
    body_bytes: bytes | bytearray | memoryview | str | None = None,
    max_drift_s: int = INTERNAL_AUTH_DRIFT_SECONDS,
    key_material: KeyMaterial | None = None,
) -> str:
    """Verify request carries valid role-bound HMAC signature or verified ASGI mTLS client cert.

    Raises:
        ProblemException(401 AUTHENTICATION_REQUIRED): When missing, spoofed, expired, or invalid.
        ProblemException(403 FORBIDDEN): When authenticated principal is not in allowed_principals.

    """
    if body_bytes is not None:
        raw_body = _coerce_body_bytes(body_bytes)
    else:
        cached_body = getattr(request, "_body", None)
        raw_body = bytes(cached_body) if isinstance(cached_body, (bytes, bytearray)) else b""

    km = key_material
    if km is None:
        app_obj = request.scope.get("app")
        app_state = getattr(app_obj, "state", None) if app_obj is not None else None
        km = getattr(app_state, "key_material", None) if app_state is not None else None

    auth_header = request.headers.get("x-kb-internal-auth")
    client_cert = request.scope.get("client_cert")

    verified_principal: str | None = None

    if auth_header is not None:
        hmac_principal = _parse_and_verify_hmac_header(
            auth_header,
            method=request.method,
            path=request.url.path,
            body_bytes=raw_body,
            max_drift_s=max_drift_s,
            key_material=km,
        )
        if hmac_principal is None:
            raise ProblemException(
                code="AUTHENTICATION_REQUIRED",
                status=401,
                title="Authentication Required",
                detail="Invalid or expired internal service authentication signature.",
            )
        if client_cert is not None:
            cert_principal = _extract_principal_from_client_cert(client_cert)
            if cert_principal is None or cert_principal != hmac_principal:
                raise ProblemException(
                    code="AUTHENTICATION_REQUIRED",
                    status=401,
                    title="Authentication Required",
                    detail="mTLS client certificate principal does not match HMAC principal.",
                )
        verified_principal = hmac_principal
    elif client_cert is not None:
        cert_principal = _extract_principal_from_client_cert(client_cert)
        if cert_principal is None:
            raise ProblemException(
                code="AUTHENTICATION_REQUIRED",
                status=401,
                title="Authentication Required",
                detail="Unverified or unrecognized mTLS client certificate principal.",
            )
        verified_principal = cert_principal
    else:
        raise ProblemException(
            code="AUTHENTICATION_REQUIRED",
            status=401,
            title="Authentication Required",
            detail="Internal service HMAC signature or verified mTLS client certificate required.",
        )

    if verified_principal not in allowed_principals:
        raise ProblemException(
            code="FORBIDDEN",
            status=403,
            title="Forbidden",
            detail=(
                f"{verified_principal} service principal is forbidden from accessing "
                "this internal endpoint."
            ),
        )

    return verified_principal
