"""Air-gap mode detection and static offline placeholder PNG (S5.4, S10.2)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from starlette.requests import Request

# Valid 1x1 transparent RGBA PNG image bytes
AIR_GAP_PLACEHOLDER_PNG: bytes = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    b"\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)

AIR_GAP_STATUS_HEADER: str = "air-gap-placeholder"


class AirGapChecker(Protocol):
    """Protocol for checking whether air-gap mode is active for a workspace."""

    def is_air_gap_enabled(self, workspace_id: UUID | None = None) -> bool:
        """Return True if air-gap isolation is active."""
        ...


class DefaultAirGapChecker:
    """Default air-gap evaluator reading request state or environment variable."""

    def __init__(self, request: Request | None = None) -> None:
        """Initialize air-gap checker with optional Starlette request."""
        self._request = request

    def is_air_gap_enabled(self, workspace_id: UUID | None = None) -> bool:
        """Evaluate air-gap mode from request app.state or KANBAN_AIR_GAP_MODE env."""
        if self._request is not None:
            fn = getattr(self._request.app.state, "is_air_gap_enabled", None)
            if callable(fn):
                res = fn(workspace_id)
                if isinstance(res, bool):
                    return res

            settings = getattr(self._request.app.state, "settings", None)
            if settings is not None:
                val = getattr(settings, "air_gap_mode", None)
                if isinstance(val, bool):
                    return val

        env_val = os.environ.get("KANBAN_AIR_GAP_MODE") or os.environ.get("KB_AIR_GAP_MODE", "")
        return env_val.strip().lower() in ("true", "1", "yes", "on")
