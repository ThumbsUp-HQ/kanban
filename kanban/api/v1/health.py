"""Liveness and health check endpoint for the v1 API."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe with zero database access."""
    return {"status": "ok"}


@router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """Compatibility alias for health check."""
    return {"status": "ok"}
