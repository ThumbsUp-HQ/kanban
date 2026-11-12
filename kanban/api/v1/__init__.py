"""Canonical API v1 router mounting all modular sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from kanban.api.v1.auth_session import router as auth_session_router
from kanban.api.v1.health import router as health_router
from kanban.api.v1.issues import router as issues_router
from kanban.api.v1.links import router as links_router
from kanban.api.v1.media_proxy import router as media_proxy_router
from kanban.api.v1.objects_access import router as objects_access_router
from kanban.api.v1.projects import router as projects_router
from kanban.api.v1.resolve import router as resolve_router


def build_v1_router() -> APIRouter:
    """Build and compose the canonical v1 API router tree."""
    v1 = APIRouter()
    v1.include_router(health_router)
    v1.include_router(media_proxy_router)
    v1.include_router(objects_access_router)
    v1.include_router(projects_router)
    v1.include_router(issues_router)
    v1.include_router(links_router)
    v1.include_router(resolve_router)
    v1.include_router(auth_session_router)
    return v1
