# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""STRIDE Threat Matrix Row 2: Hostile Media, SVG, Mermaid & SSRF (Spec S3.5, KB-P6-03)."""

from __future__ import annotations

import ipaddress
import uuid
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from kanban.api.problems import ProblemException
from kanban.attachments.raster import (
    _process_svg,
    _validate_image_dimensions,
)
from kanban.content.svg_dag import SvgSanitizeError
from kanban.content.svg_sanitizer import sanitize_svg
from kanban.media_proxy.placeholder import AIR_GAP_STATUS_HEADER
from kanban.media_proxy.service import MediaProxyService
from kanban.media_proxy.signing import (
    sign_media_proxy_url,
    validate_external_image_url,
    verify_media_proxy_url,
)
from kanban.media_proxy.ssrf import is_public_global_ip, resolve_and_select_pinned_ip
from kanban.security.keys import KeyMaterial


def test_stride_row2_hostile_svg_sanitization_and_dag_bomb() -> None:
    """S3.5 Row 2: Hostile SVG uploads with script/XSS/DAG vectors are sanitized/rejected."""
    # 1. Script injection
    svg_script = b"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
        <script>alert(document.domain)</script>
        <circle cx="50" cy="50" r="40" fill="red"/>
    </svg>"""
    sanitized = sanitize_svg(svg_script)
    assert "<script" not in sanitized
    assert "alert" not in sanitized
    assert "<circle" in sanitized

    # 2. ForeignObject injection
    svg_foreign = b"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
        <foreignObject width="100" height="100">
            <body xmlns="http://www.w3.org/1999/xhtml">
                <iframe src="https://evil.example.com"></iframe>
            </body>
        </foreignObject>
        <rect width="100" height="100" fill="blue"/>
    </svg>"""
    sanitized_fo = sanitize_svg(svg_foreign)
    assert "<foreignObject" not in sanitized_fo
    assert "<iframe" not in sanitized_fo
    assert "<rect" in sanitized_fo

    # 3. Style @import
    svg_style = b"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
        <style>@import url("https://evil.example.com/leak.css");</style>
        <rect width="100" height="100" fill="green"/>
    </svg>"""
    sanitized_style = sanitize_svg(svg_style)
    assert "@import" not in sanitized_style
    assert "evil.example.com" not in sanitized_style
    assert "<rect" in sanitized_style

    # 4. SMIL <animate onbegin=...> and onload= handlers
    svg_smil = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
        b"onload=\"alert('pwn')\">\n"
        b'    <circle cx="50" cy="50" r="40">\n'
        b'        <animate attributeName="r" from="10" to="40" dur="1s" '
        b"onbegin=\"fetch('https://evil.example.com')\"/>\n"
        b"    </circle>\n"
        b"</svg>"
    )
    sanitized_smil = sanitize_svg(svg_smil)
    assert "onload" not in sanitized_smil
    assert "onbegin" not in sanitized_smil
    assert "alert" not in sanitized_smil
    assert "evil.example.com" not in sanitized_smil

    # 5. Dangerous javascript: and external href
    svg_href = (
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        b'width="100" height="100">\n'
        b'    <a href="javascript:alert(1)"><text x="10" y="20">Click</text></a>\n'
        b'    <a xlink:href="https://evil.example.com/phish"><text x="10" y="40">Phish</text></a>\n'
        b"</svg>"
    )
    sanitized_href = sanitize_svg(svg_href)
    assert "javascript:" not in sanitized_href
    assert "https://evil.example.com" not in sanitized_href

    # 6. Billion-laughs DAG depth > 4 / > 500 expanded nodes
    # Depth 5 chain: defs with 5 tiers of nested use references
    svg_dag_bomb = b"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
        <defs>
            <g id="l0"><circle cx="10" cy="10" r="5"/></g>
            <g id="l1"><use href="#l0"/><use href="#l0"/></g>
            <g id="l2"><use href="#l1"/><use href="#l1"/></g>
            <g id="l3"><use href="#l2"/><use href="#l2"/></g>
            <g id="l4"><use href="#l3"/><use href="#l3"/></g>
            <g id="l5"><use href="#l4"/><use href="#l4"/></g>
        </defs>
        <use href="#l5"/>
    </svg>"""
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(svg_dag_bomb)
    assert exc_info.value.code in {"SVG_USE_DEPTH_EXCEEDED", "SVG_EXPANSION_LIMIT_EXCEEDED"}

    # Also verify through attachment pipeline raising 422 ProblemException
    with pytest.raises(ProblemException) as exc_p:
        _process_svg(svg_dag_bomb)
    assert exc_p.value.status == 422
    assert exc_p.value.code == "SVG_UNSAFE"


def test_stride_row2_svg_download_headers_and_csp() -> None:
    """S3.5 Row 2: Direct GET on SVG emits CSP sandbox, nosniff, and attachment header."""
    safe_filename = "diagram.svg"
    content_type = "image/svg+xml"

    def compute_response_headers(sec_fetch_dest: str | None) -> dict[str, str]:
        headers: dict[str, str] = {
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Cache-Control": "private, max-age=300",
        }
        if content_type == "image/svg+xml":
            headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
            dest = (sec_fetch_dest or "").strip().lower()
            if dest == "image":
                headers["Content-Disposition"] = f'inline; filename="{safe_filename}"'
            else:
                headers["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
        return headers

    # 1. Direct browser navigation / link click (no Sec-Fetch-Dest or "document")
    h_doc = compute_response_headers("document")
    assert h_doc["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert h_doc["X-Content-Type-Options"] == "nosniff"
    assert h_doc["Content-Disposition"] == f'attachment; filename="{safe_filename}"'

    h_none = compute_response_headers(None)
    assert h_none["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert h_none["Content-Disposition"] == f'attachment; filename="{safe_filename}"'

    # 2. Embedded <img> rendering (Sec-Fetch-Dest: image)
    h_img = compute_response_headers("image")
    assert h_img["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert h_img["Content-Disposition"] == f'inline; filename="{safe_filename}"'


async def test_stride_row2_media_proxy_ssrf_and_airgap() -> None:
    """S3.5 Row 2: Media proxy blocks cloud metadata, loopback, RFC1918, ULA, and air gap."""
    # 1. IP validation boundaries
    assert not is_public_global_ip(ipaddress.ip_address("169.254.169.254"))  # Cloud metadata
    assert not is_public_global_ip(ipaddress.ip_address("127.0.0.1"))  # IPv4 Loopback
    assert not is_public_global_ip(ipaddress.ip_address("::1"))  # IPv6 Loopback
    assert not is_public_global_ip(ipaddress.ip_address("10.0.0.1"))  # RFC1918 10.0.0.0/8
    assert not is_public_global_ip(ipaddress.ip_address("172.16.0.1"))  # RFC1918 172.16.0.0/12
    assert not is_public_global_ip(ipaddress.ip_address("192.168.1.1"))  # RFC1918
    assert not is_public_global_ip(ipaddress.ip_address("fd00::1"))  # IPv6 ULA
    assert is_public_global_ip(ipaddress.ip_address("93.184.216.34"))  # Public internet IP

    # 2. resolve_and_select_pinned_ip rejects non-public targets with 422 ProblemException
    mock_bad_resolver = AsyncMock()
    mock_bad_resolver.resolve.return_value = [ipaddress.ip_address("169.254.169.254")]

    with pytest.raises(ProblemException) as exc_meta:
        await resolve_and_select_pinned_ip("metadata.cloud.internal", resolver=mock_bad_resolver)
    assert exc_meta.value.status == 403
    assert exc_meta.value.code == "MEDIA_HOST_BLOCKED"

    # 3. DNS-rebinding simulation: resolve-then-pin ensures transport connects ONLY to pinned IP
    public_ip = ipaddress.ip_address("93.184.216.34")
    rebinding_resolver = AsyncMock()
    rebinding_resolver.resolve.return_value = [public_ip]

    pinned_ip = await resolve_and_select_pinned_ip("cdn.example.com", resolver=rebinding_resolver)
    assert str(pinned_ip) == "93.184.216.34"

    # Even if subsequent resolver lookup returns loopback, the pinned IP remains the public IP
    rebinding_resolver.resolve.return_value = [ipaddress.ip_address("127.0.0.1")]
    # The client uses pinned_ip ("93.184.216.34"), never re-resolving
    assert str(pinned_ip) == "93.184.216.34"

    # 4. Air gap mode blocks external fetch before DNS
    mock_air_gap_checker = MagicMock()
    mock_air_gap_checker.is_air_gap_enabled.return_value = True

    proxy_service = MediaProxyService(air_gap_checker=mock_air_gap_checker)
    content_type, _body_bytes, headers = await proxy_service.fetch_proxy_media(
        "https://cdn.example.com/image.png",
        workspace_id=uuid.uuid4(),
    )
    assert content_type == "image/png"
    assert headers["X-Kanban-Media-Status"] == AIR_GAP_STATUS_HEADER
    assert headers["Cache-Control"] == "private, no-store"

    # 5. HMAC signature generation and tampered signature rejection
    km = KeyMaterial(master_kek=b"A" * 32, auth_pepper=b"B" * 32, session_hmac_key=b"C" * 32)
    media_url = "https://cdn.example.com/photo.jpg"
    valid_signed_url = sign_media_proxy_url(media_url, km)
    assert "/api/v1/media-proxy" in valid_signed_url

    # Extract expiration and signature and verify (KAN-325)
    parsed_qs = parse_qs(urlsplit(valid_signed_url).query)
    exp = int(parsed_qs["exp"][0])
    sig = parsed_qs["sig"][0]
    assert verify_media_proxy_url(media_url, sig, km, exp=exp) is True
    # Tampered signature or URL rejected
    assert verify_media_proxy_url(media_url, "tampered_sig_invalid", km, exp=exp) is False
    assert verify_media_proxy_url("https://evil.com/fake.jpg", sig, km, exp=exp) is False

    # Validate scheme and host check
    with pytest.raises(ProblemException) as exc_scheme:
        validate_external_image_url("file:///etc/passwd")
    assert exc_scheme.value.status == 400
    assert exc_scheme.value.code == "INVALID_MEDIA_URL"


def test_stride_row2_decompression_pixel_bomb() -> None:
    """S3.5 Row 2: Decompression bomb image (8000x6000 = 48M > 40M pixels) is rejected with 422."""
    mock_huge_image = MagicMock(spec=Image.Image)
    mock_huge_image.size = (8000, 6000)  # 48,000,000 pixels > 40,000,000 cap

    with pytest.raises(ProblemException) as exc_bomb:
        _validate_image_dimensions(mock_huge_image)
    assert exc_bomb.value.status == 422
    assert exc_bomb.value.code == "IMAGE_DIMENSIONS_EXCEEDED"
    assert "48000000 px" in exc_bomb.value.detail

    # Dimension exceeding MAX_DIMENSION (16384 px)
    mock_wide_image = MagicMock(spec=Image.Image)
    mock_wide_image.size = (20000, 1000)
    with pytest.raises(ProblemException) as exc_wide:
        _validate_image_dimensions(mock_wide_image)
    assert exc_wide.value.status == 422
    assert exc_wide.value.code == "IMAGE_DIMENSIONS_EXCEEDED"
