"""HMAC URL signing and validation for external Markdown images (S5.4, S10.2)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

from kanban.api.problems import ProblemException
from kanban.media_proxy.ssrf import is_public_global_ip
from kanban.security.keys import derive_subkey

if TYPE_CHECKING:
    from urllib.parse import SplitResult

    from kanban.security.keys import KeyMaterial

_MAX_URL_LENGTH = 2048
_MAX_HOST_LENGTH = 253
_MAX_SIG_LENGTH = 64
_HTTPS_PORT = 443


def _validate_host(hostname: str | None) -> None:
    """Validate external image hostname bounds and literal IP restrictions."""
    if not hostname:
        msg = "Media URL must contain a non-empty host"
        raise ProblemException(
            code="INVALID_MEDIA_URL",
            status=400,
            title="Invalid Media URL",
            detail=msg,
        )

    if len(hostname) > _MAX_HOST_LENGTH:
        msg = f"Media host length exceeds {_MAX_HOST_LENGTH} characters"
        raise ProblemException(
            code="INVALID_MEDIA_URL",
            status=400,
            title="Invalid Media URL",
            detail=msg,
        )

    cleaned_host = hostname.strip("[]")
    try:
        ip = ipaddress.ip_address(cleaned_host)
        if not is_public_global_ip(ip):
            msg = f"Literal host IP '{hostname}' belongs to a blocked or private range"
            raise ProblemException(
                code="INVALID_MEDIA_URL",
                status=400,
                title="Invalid Media URL",
                detail=msg,
            )
    except ValueError:
        pass


def _validate_components(parsed: SplitResult) -> None:
    """Validate URL scheme, credentials, fragment, and port."""
    if parsed.scheme.lower() != "https":
        msg = f"Disallowed URL scheme '{parsed.scheme}'; media proxy requires HTTPS"
        raise ProblemException(
            code="INVALID_MEDIA_URL",
            status=400,
            title="Invalid Media URL",
            detail=msg,
        )

    if parsed.username is not None or parsed.password is not None:
        msg = "Media URL must not contain username or password credentials"
        raise ProblemException(
            code="INVALID_MEDIA_URL",
            status=400,
            title="Invalid Media URL",
            detail=msg,
        )

    if parsed.fragment:
        msg = "Media URL must not contain a URL fragment identifier"
        raise ProblemException(
            code="INVALID_MEDIA_URL",
            status=400,
            title="Invalid Media URL",
            detail=msg,
        )

    if parsed.port not in (None, _HTTPS_PORT):
        msg = f"Disallowed media port '{parsed.port}'; media proxy requires port {_HTTPS_PORT}"
        raise ProblemException(
            code="INVALID_MEDIA_URL",
            status=400,
            title="Invalid Media URL",
            detail=msg,
        )


def validate_external_image_url(url: str) -> SplitResult:
    """Validate external image URL against strict security boundaries.

    Requires exact scheme 'https', non-empty ASCII/IDNA hostname <= 253 chars,
    total URL length <= 2048, zero userinfo, zero fragment, and port None or 443.
    Rejects literal IP hostnames in blocked or private ranges immediately.
    """
    if not url or not url.strip():
        msg = "Media URL must be a non-empty string"
        raise ProblemException(
            code="INVALID_MEDIA_URL",
            status=400,
            title="Invalid Media URL",
            detail=msg,
        )

    if len(url) > _MAX_URL_LENGTH:
        msg = f"Media URL length exceeds {_MAX_URL_LENGTH} characters"
        raise ProblemException(
            code="INVALID_MEDIA_URL",
            status=400,
            title="Invalid Media URL",
            detail=msg,
        )

    try:
        parsed = urlsplit(url)
    except ValueError as err:
        msg = f"Failed to parse media URL: {err}"
        raise ProblemException(
            code="INVALID_MEDIA_URL",
            status=400,
            title="Invalid Media URL",
            detail=msg,
        ) from err

    _validate_components(parsed)
    _validate_host(parsed.hostname)
    return parsed


def sign_media_proxy_url(url: str, key_material: KeyMaterial) -> str:
    """Validate and compute HMAC signature for external media URL.

    Returns canonical relative proxy URL '/api/v1/media-proxy?u=...&sig=...'.
    """
    validate_external_image_url(url)
    subkey = derive_subkey(key_material.session_hmac_key, "media-proxy/url")
    digest = hmac.new(subkey, url.encode("utf-8"), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    quoted_url = quote(url, safe="")
    return f"/api/v1/media-proxy?u={quoted_url}&sig={sig}"


def verify_media_proxy_url(url: str, sig: str, key_material: KeyMaterial) -> bool:
    """Verify media proxy HMAC signature using constant-time comparison.

    Executed BEFORE URL parsing or DNS resolution to eliminate unauthenticated work.
    """
    if not sig or len(sig) > _MAX_SIG_LENGTH or not url:
        return False

    subkey = derive_subkey(key_material.session_hmac_key, "media-proxy/url")
    expected_digest = hmac.new(subkey, url.encode("utf-8"), hashlib.sha256).digest()

    padded_sig = sig + "=" * (-len(sig) % 4)
    try:
        candidate_digest = base64.urlsafe_b64decode(padded_sig.encode("ascii"))
    except (ValueError, binascii.Error):
        return False

    return hmac.compare_digest(candidate_digest, expected_digest)
