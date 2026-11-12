"""Canonical API v1 router mounting all modular sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from kanban.api.internal.mcp_introspect import router as mcp_introspect_router
from kanban.api.v1.activity import router as activity_router
from kanban.api.v1.admin.mcp_keys import router as admin_mcp_keys_router
from kanban.api.v1.agent_definitions import router as agent_definitions_router
from kanban.api.v1.assignees import router as assignees_router
from kanban.api.v1.attachments import router as attachments_router
from kanban.api.v1.auth_ldap import auth_ldap_router
from kanban.api.v1.auth_local import router as auth_local_router
from kanban.api.v1.auth_mfa import router as auth_mfa_router
from kanban.api.v1.auth_oidc import router as auth_oidc_router
from kanban.api.v1.auth_session import router as auth_session_router
from kanban.api.v1.auth_webauthn import router as auth_webauthn_router
from kanban.api.v1.comments import router as comments_router
from kanban.api.v1.cycles import router as cycles_router
from kanban.api.v1.docs import router as docs_router
from kanban.api.v1.health import router as health_router
from kanban.api.v1.issue_archive import router as archive_router
from kanban.api.v1.issue_copy import router as issue_copy_router
from kanban.api.v1.issue_move import router as issue_move_router
from kanban.api.v1.issue_provenance import router as issue_provenance_router
from kanban.api.v1.issues import router as issues_router
from kanban.api.v1.links import router as links_router
from kanban.api.v1.media_proxy import router as media_proxy_router
from kanban.api.v1.modules import router as modules_router
from kanban.api.v1.notifications import router as notifications_router
from kanban.api.v1.objects_access import router as objects_access_router
from kanban.api.v1.project_config import router as project_config_router
from kanban.api.v1.projects import router as projects_router
from kanban.api.v1.resolve import router as resolve_router
from kanban.api.v1.stickies import router as stickies_router
from kanban.api.v1.subscriptions import router as subscriptions_router
from kanban.api.v1.views import router as views_router


def build_v1_router() -> APIRouter:
    """Build and compose the canonical v1 API router tree."""
    v1 = APIRouter()
    v1.include_router(health_router)
    v1.include_router(media_proxy_router)
    v1.include_router(objects_access_router)
    v1.include_router(projects_router)
    v1.include_router(project_config_router)
    v1.include_router(modules_router)
    v1.include_router(issues_router)
    v1.include_router(issue_copy_router)
    v1.include_router(assignees_router)
    v1.include_router(links_router)
    v1.include_router(issue_move_router)
    v1.include_router(issue_provenance_router)
    v1.include_router(resolve_router)
    v1.include_router(comments_router)
    v1.include_router(activity_router)
    v1.include_router(auth_session_router)
    v1.include_router(auth_local_router)
    v1.include_router(auth_oidc_router)
    v1.include_router(auth_mfa_router)
    v1.include_router(auth_ldap_router)
    v1.include_router(auth_webauthn_router)
    v1.include_router(cycles_router)
    v1.include_router(docs_router)
    v1.include_router(stickies_router)
    v1.include_router(agent_definitions_router)
    v1.include_router(attachments_router)
    v1.include_router(views_router)
    v1.include_router(archive_router)
    v1.include_router(admin_mcp_keys_router)
    v1.include_router(mcp_introspect_router)
    v1.include_router(subscriptions_router)
    v1.include_router(notifications_router)
    return v1
