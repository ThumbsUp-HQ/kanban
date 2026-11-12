"""Media proxy service coordinating air-gap checks, DNS pinning, and fetch (S5.4, S10.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kanban.media_proxy.client import PinnedTlsMediaClient
from kanban.media_proxy.placeholder import (
    AIR_GAP_PLACEHOLDER_PNG,
    AIR_GAP_STATUS_HEADER,
    DefaultAirGapChecker,
)
from kanban.media_proxy.signing import validate_external_image_url
from kanban.media_proxy.ssrf import resolve_and_select_pinned_ip

if TYPE_CHECKING:
    from uuid import UUID

    from kanban.media_proxy.client import PinnedConnectionTransport
    from kanban.media_proxy.placeholder import AirGapChecker
    from kanban.media_proxy.ssrf import AsyncHostResolver


class MediaProxyService:
    """High-level media proxy service coordinating SSRF defense and retrieval."""

    def __init__(
        self,
        resolver: AsyncHostResolver | None = None,
        client: PinnedTlsMediaClient | None = None,
        air_gap_checker: AirGapChecker | None = None,
        transport: PinnedConnectionTransport | None = None,
    ) -> None:
        """Initialize service with optional custom resolver, client, or air-gap checker."""
        self._resolver = resolver
        self._client = client or PinnedTlsMediaClient(transport=transport)
        self._air_gap_checker = air_gap_checker or DefaultAirGapChecker()

    async def fetch_proxy_media(
        self,
        url: str,
        workspace_id: UUID | None = None,
    ) -> tuple[str, bytes, dict[str, str]]:
        """Retrieve external media or return air-gap placeholder.

        Returns tuple of (content_type, body_bytes, extra_headers).
        """
        if self._air_gap_checker.is_air_gap_enabled(workspace_id):
            headers = {
                "X-Kanban-Media-Status": AIR_GAP_STATUS_HEADER,
                "Cache-Control": "private, no-store",
            }
            return "image/png", AIR_GAP_PLACEHOLDER_PNG, headers

        parsed = validate_external_image_url(url)
        hostname = parsed.hostname or ""

        pinned_ip = await resolve_and_select_pinned_ip(hostname, resolver=self._resolver)

        path_and_query = parsed.path or "/"
        if parsed.query:
            path_and_query = f"{path_and_query}?{parsed.query}"

        content_type, body_bytes = await self._client.fetch_media(
            pinned_ip=pinned_ip,
            original_host=hostname,
            path_and_query=path_and_query,
        )

        headers = {
            "Cache-Control": "private, max-age=3600",
        }
        return content_type, body_bytes, headers
