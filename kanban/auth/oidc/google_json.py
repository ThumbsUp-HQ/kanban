# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Google OAuth 2.0 Web Client JSON parser and endpoint pinning (KB-AUTH-JSON)."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from kanban.api.problems import ProblemException

MAX_GOOGLE_JSON_BYTES: int = 32768
SURROGATE_MIN: int = 0xD800
SURROGATE_MAX: int = 0xDFFF
MIN_CLIENT_ID_LEN: int = 1
MAX_CLIENT_ID_LEN: int = 255
MIN_CLIENT_SECRET_LEN: int = 1
MAX_CLIENT_SECRET_LEN: int = 512

ALLOWED_AUTH_URIS: frozenset[str] = frozenset(
    {
        "https://accounts.google.com/o/oauth2/auth",
        "https://accounts.google.com/o/oauth2/v2/auth",
    }
)

ALLOWED_TOKEN_URIS: frozenset[str] = frozenset(
    {
        "https://oauth2.googleapis.com/token",
        "https://accounts.google.com/o/oauth2/token",
        "https://www.googleapis.com/oauth2/v4/token",
    }
)

ALLOWED_CERT_URL_PREFIXES: tuple[str, ...] = (
    "https://www.googleapis.com/oauth2/",
    "https://accounts.google.com/",
)

DEFAULT_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105


class ParsedGoogleOAuthClient(BaseModel):
    """Normalized and validated Google OAuth 2.0 web application client configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    client_secret: str
    project_id: str | None = None
    auth_uri: str = "https://accounts.google.com/o/oauth2/v2/auth"
    token_uri: str = DEFAULT_GOOGLE_TOKEN_ENDPOINT
    auth_provider_x509_cert_url: str | None = None
    redirect_uris: list[str] = Field(default_factory=list)
    javascript_origins: list[str] = Field(default_factory=list)
    expected_callback_uri: str | None = None
    callback_uri_matched: bool = False
    issuer: str = "https://accounts.google.com"
    kind: str = "OIDC"
    scopes: list[str] = Field(default_factory=lambda: ["openid", "profile", "email"])
    client_auth: str = "client_secret_basic"


def _check_surrogates_and_bytes(raw_json: str | bytes) -> bytes:
    if isinstance(raw_json, str):
        for ch in raw_json:
            code = ord(ch)
            if SURROGATE_MIN <= code <= SURROGATE_MAX:
                raise ProblemException(
                    code="INVALID_UTF8_SURROGATE",
                    status=422,
                    title="Invalid UTF-8 Surrogate",
                    detail="Google OAuth JSON contains forbidden UTF-16 lone surrogate character.",
                )
        payload = raw_json.encode("utf-8")
    else:
        payload = raw_json

    if len(payload) > MAX_GOOGLE_JSON_BYTES:
        raise ProblemException(
            code="GOOGLE_JSON_TOO_LARGE",
            status=422,
            title="Google JSON Too Large",
            detail=f"Google OAuth JSON exceeds limit of {MAX_GOOGLE_JSON_BYTES} bytes.",
        )
    return payload


def _validate_web_block(parsed: object) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ProblemException(
            code="INVALID_GOOGLE_JSON",
            status=422,
            title="Invalid Google JSON",
            detail="Top-level payload must be a JSON object.",
        )
    if "installed" in parsed and "web" not in parsed:
        msg = (
            "Google OAuth JSON is for an Installed/Desktop client; "
            "create a Web application OAuth client in Google Cloud Console."
        )
        raise ProblemException(
            code="INVALID_GOOGLE_CLIENT_TYPE",
            status=422,
            title="Invalid Google Client Type",
            detail=msg,
        )
    if "web" not in parsed or not isinstance(parsed["web"], dict):
        raise ProblemException(
            code="INVALID_GOOGLE_CLIENT_TYPE",
            status=422,
            title="Invalid Google Client Type",
            detail="Google OAuth JSON must contain a top-level 'web' configuration object.",
        )
    return parsed["web"]


def _validate_client_credentials(web: dict[str, Any]) -> tuple[str, str]:
    cid = web.get("client_id")
    if not isinstance(cid, str) or not (MIN_CLIENT_ID_LEN <= len(cid.strip()) <= MAX_CLIENT_ID_LEN):
        raise ProblemException(
            code="INVALID_GOOGLE_CLIENT_ID",
            status=422,
            title="Invalid Client ID",
            detail="Field 'client_id' must be a non-empty string between 1 and 255 characters.",
        )
    csec = web.get("client_secret")
    if not isinstance(csec, str) or not (
        MIN_CLIENT_SECRET_LEN <= len(csec.strip()) <= MAX_CLIENT_SECRET_LEN
    ):
        raise ProblemException(
            code="INVALID_GOOGLE_CLIENT_SECRET",
            status=422,
            title="Invalid Client Secret",
            detail="Field 'client_secret' must be a non-empty string between 1 and 512 characters.",
        )
    return cid.strip(), csec.strip()


def _validate_endpoints(web: dict[str, Any]) -> tuple[str, str, str | None]:
    auth_uri = web.get("auth_uri")
    if auth_uri is not None:
        if not isinstance(auth_uri, str) or auth_uri.strip() not in ALLOWED_AUTH_URIS:
            raise ProblemException(
                code="UNTRUSTED_GOOGLE_ENDPOINT",
                status=422,
                title="Untrusted Google Endpoint",
                detail=f"Field 'auth_uri' ({auth_uri}) not in Google allowlist.",
            )
        resolved_auth = auth_uri.strip()
    else:
        resolved_auth = "https://accounts.google.com/o/oauth2/v2/auth"

    token_uri = web.get("token_uri")
    if token_uri is not None:
        if not isinstance(token_uri, str) or token_uri.strip() not in ALLOWED_TOKEN_URIS:
            raise ProblemException(
                code="UNTRUSTED_GOOGLE_ENDPOINT",
                status=422,
                title="Untrusted Google Endpoint",
                detail=f"Field 'token_uri' ({token_uri}) not in Google allowlist.",
            )
        resolved_token = token_uri.strip()
    else:
        resolved_token = DEFAULT_GOOGLE_TOKEN_ENDPOINT

    cert_url = web.get("auth_provider_x509_cert_url")
    resolved_cert: str | None = None
    if cert_url is not None:
        if not isinstance(cert_url, str) or not any(
            cert_url.strip().startswith(prefix) for prefix in ALLOWED_CERT_URL_PREFIXES
        ):
            raise ProblemException(
                code="UNTRUSTED_GOOGLE_ENDPOINT",
                status=422,
                title="Untrusted Google Endpoint",
                detail="Field 'auth_provider_x509_cert_url' must match Google endpoint prefix.",
            )
        resolved_cert = cert_url.strip()

    return resolved_auth, resolved_token, resolved_cert


def _extract_uris(web: dict[str, Any]) -> tuple[list[str], list[str]]:
    redirect_uris_raw = web.get("redirect_uris", [])
    if not isinstance(redirect_uris_raw, list):
        raise ProblemException(
            code="INVALID_REDIRECT_URIS",
            status=422,
            title="Invalid Redirect URIs",
            detail="Field 'redirect_uris' must be a list of URI strings.",
        )
    redirect_uris: list[str] = []
    for uri in redirect_uris_raw:
        if isinstance(uri, str) and uri.strip():
            u = uri.strip()
            parsed_u = urllib.parse.urlsplit(u)
            if not parsed_u.scheme or not parsed_u.netloc:
                raise ProblemException(
                    code="INVALID_REDIRECT_URIS",
                    status=422,
                    title="Invalid Redirect URIs",
                    detail=f"Invalid URI format in redirect_uris: '{u}'.",
                )
            redirect_uris.append(u)

    js_origins_raw = web.get("javascript_origins", [])
    javascript_origins: list[str] = []
    if isinstance(js_origins_raw, list):
        javascript_origins.extend(
            orig.strip() for orig in js_origins_raw if isinstance(orig, str) and orig.strip()
        )

    return redirect_uris, javascript_origins


def parse_google_oauth_client_json(
    raw_json: str | bytes,
    *,
    expected_redirect_uri: str | None = None,
) -> ParsedGoogleOAuthClient:
    """Parse and validate Google Cloud Console OAuth client secret JSON."""
    payload_bytes = _check_surrogates_and_bytes(raw_json)

    try:
        decoded_text = payload_bytes.decode("utf-8")
        parsed = json.loads(decoded_text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProblemException(
            code="INVALID_JSON",
            status=422,
            title="Invalid JSON",
            detail=f"Failed to parse Google OAuth client JSON: {exc}",
        ) from exc

    web = _validate_web_block(parsed)
    client_id, client_secret = _validate_client_credentials(web)
    auth_uri, token_uri, cert_url = _validate_endpoints(web)
    redirect_uris, javascript_origins = _extract_uris(web)

    project_id = web.get("project_id")
    clean_project_id = (
        project_id.strip() if isinstance(project_id, str) and project_id.strip() else None
    )

    clean_expected = expected_redirect_uri.strip() if expected_redirect_uri is not None else None
    matched = clean_expected in redirect_uris if clean_expected is not None else False

    return ParsedGoogleOAuthClient(
        client_id=client_id,
        client_secret=client_secret,
        project_id=clean_project_id,
        auth_uri=auth_uri,
        token_uri=token_uri,
        auth_provider_x509_cert_url=cert_url,
        redirect_uris=redirect_uris,
        javascript_origins=javascript_origins,
        expected_callback_uri=clean_expected,
        callback_uri_matched=matched,
        issuer="https://accounts.google.com",
        kind="OIDC",
        scopes=["openid", "profile", "email"],
        client_auth="client_secret_basic",
    )
