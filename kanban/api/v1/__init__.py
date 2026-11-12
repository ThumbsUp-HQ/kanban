"""FastAPI v1 router composition for the Kanban API."""

from __future__ import annotations

from fastapi import APIRouter

from kanban.api.v1.health import router as health_router


def build_v1_router() -> APIRouter:
    """Build and compose the canonical v1 API router tree."""
    v1 = APIRouter()
    v1.include_router(health_router)
    return v1


__all__ = ["build_v1_router"]
