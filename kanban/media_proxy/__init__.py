"""Cookieless external media proxy with DNS-pinning SSRF protection (S5.4, S10.2)."""

from __future__ import annotations

from kanban.media_proxy.client import (
    MAX_PROXY_BYTES,
    PinnedConnectionTransport,
    PinnedTlsMediaClient,
)
from kanban.media_proxy.placeholder import (
    AIR_GAP_PLACEHOLDER_PNG,
    AIR_GAP_STATUS_HEADER,
    AirGapChecker,
    DefaultAirGapChecker,
)
from kanban.media_proxy.service import MediaProxyService
from kanban.media_proxy.signing import (
    DEFAULT_MEDIA_PROXY_TTL_SECONDS,
    MAX_MEDIA_PROXY_TTL_SECONDS,
    sign_media_proxy_url,
    validate_external_image_url,
    verify_media_proxy_url,
)
from kanban.media_proxy.ssrf import (
    AsyncHostResolver,
    DefaultAsyncHostResolver,
    is_public_global_ip,
    resolve_and_select_pinned_ip,
)

__all__ = [
    "AIR_GAP_PLACEHOLDER_PNG",
    "AIR_GAP_STATUS_HEADER",
    "DEFAULT_MEDIA_PROXY_TTL_SECONDS",
    "MAX_MEDIA_PROXY_TTL_SECONDS",
    "MAX_PROXY_BYTES",
    "AirGapChecker",
    "AsyncHostResolver",
    "DefaultAirGapChecker",
    "DefaultAsyncHostResolver",
    "MediaProxyService",
    "PinnedConnectionTransport",
    "PinnedTlsMediaClient",
    "is_public_global_ip",
    "resolve_and_select_pinned_ip",
    "sign_media_proxy_url",
    "validate_external_image_url",
    "verify_media_proxy_url",
]
