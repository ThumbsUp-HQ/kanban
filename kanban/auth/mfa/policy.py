# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""AAL2 session enforcement and admin route security policies (KB-P2-05a)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Final, Literal, cast

from fastapi import Depends
from sqlalchemy import text
from starlette.requests import Request  # noqa: TC002  # Required at runtime for FastAPI dependency analysis

from database.session import RLSContext
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import ProblemException

AAL2_LEVEL: Final[int] = 2
ADMIN_AAL2_MAX_AGE_SECONDS: Final[int] = 900

__all__ = [
    "AAL2_LEVEL",
    "assert_admin_routes_protected",
    "require_aal2",
    "require_admin_aal2",
]


async def _get_enrolled_methods(
    request: Request,
    principal: PrincipalContext,
) -> list[str]:
    """Query enrolled confirmed MFA methods for the principal."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        return []
    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )
    async with session_factory.session(rls_ctx) as db_session:
        status_res = await db_session.execute(
            text("SELECT * FROM kb_auth.mfa_status(:p_id)"),
            {"p_id": principal.principal_id},
        )
        status_row = status_res.mappings().first()
        if not status_row:
            return []
        methods: list[str] = []
        if int(status_row.get("webauthn_credential_count", 0)) > 0:
            methods.append("webauthn")
        if bool(status_row.get("has_active_totp")):
            methods.append("totp")
        if int(status_row.get("unused_recovery_codes", 0)) > 0:
            methods.append("recovery")
        return methods


class _RequireAal2:
    """Callable dependency enforcing AAL2 status and maximum age freshness."""

    def __init__(self, max_age_seconds: int | None = None) -> None:
        """Initialize dependency with optional max age freshness in seconds."""
        self.max_age_seconds = max_age_seconds

    async def __call__(
        self,
        request: Request,
        principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> PrincipalContext:
        """Verify principal has AAL2 credentials and verification is fresh."""
        if principal.aal_level < AAL2_LEVEL:
            methods = await _get_enrolled_methods(request, principal)
            preferred = "webauthn" if "webauthn" in methods else "totp"
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Authentication Required",
                detail="This operation requires multi-factor authentication (AAL2).",
                methods=methods,
                preferred_method=preferred,
            )

        if self.max_age_seconds is not None:
            verified_at = principal.aal2_verified_at
            if verified_at is None:
                methods = await _get_enrolled_methods(request, principal)
                preferred = "webauthn" if "webauthn" in methods else "totp"
                raise ProblemException(
                    code="AAL2_STALE",
                    status=403,
                    title="AAL2 Session Stale",
                    detail="AAL2 verification timestamp is missing or stale.",
                    methods=methods,
                    preferred_method=preferred,
                )

            now = datetime.now(UTC)
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=UTC)
            age = (now - verified_at).total_seconds()
            if age > self.max_age_seconds:
                methods = await _get_enrolled_methods(request, principal)
                preferred = "webauthn" if "webauthn" in methods else "totp"
                detail_msg = f"AAL2 verification is stale ({int(age)}s > {self.max_age_seconds}s)."
                raise ProblemException(
                    code="AAL2_STALE",
                    status=403,
                    title="AAL2 Session Stale",
                    detail=detail_msg,
                    methods=methods,
                    preferred_method=preferred,
                )

        return principal


def require_aal2(max_age_seconds: int | None = None) -> _RequireAal2:
    """Return dependency requiring AAL2 elevation with optional max age freshness."""
    return _RequireAal2(max_age_seconds=max_age_seconds)


async def require_admin_aal2(  # noqa: C901
    request: Request,
    principal: Annotated[PrincipalContext, Depends(get_principal)],
) -> PrincipalContext:
    """Enforce AAL2 MFA policy on administrative routes (KB-P2-05a).

    - Principal with SERVER_ADMIN or PROJECT_ADMIN and no enrolled confirmed factor:
      raises 403 MFA_ENROLLMENT_REQUIRED.
    - Principal with factor enrolled but AAL1 session:
      raises 403 AAL2_REQUIRED.
    - Non-admin principal:
      raises 403 FORBIDDEN.
    """
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    rls_ctx = RLSContext(
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        token_scopes=principal.token_scopes,
        aal_level=cast("Literal[1, 2]", principal.aal_level),
    )

    async with session_factory.session(rls_ctx) as db_session:
        admin_res = await db_session.execute(
            text(
                "SELECT 1 FROM role_bindings "
                "WHERE principal_id = :p_id "
                "  AND role IN ('SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN')"
            ),
            {"p_id": principal.principal_id},
        )
        admin_res = await db_session.execute(
            text(
                "SELECT 1 FROM role_bindings "
                "WHERE principal_id = :p_id "
                "  AND role IN ('SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN') "
                "LIMIT 1"
            ),
            {"p_id": principal.principal_id},
        )
        is_admin = admin_res.scalar_one_or_none() is not None
        if not is_admin:
            raise ProblemException(
                code="FORBIDDEN",
                status=403,
                title="Forbidden",
                detail="Principal does not possess an administrative role.",
            )

        status_res = await db_session.execute(
            text("SELECT * FROM kb_auth.mfa_status(:p_id)"),
            {"p_id": principal.principal_id},
        )
        status_row = status_res.mappings().first()
        has_active_totp = bool(status_row["has_active_totp"]) if status_row else False
        unused_codes = int(status_row["unused_recovery_codes"]) if status_row else 0
        has_webauthn = (
            int(status_row["webauthn_credential_count"]) > 0
            if status_row and "webauthn_credential_count" in status_row
            else False
        )

        if not has_active_totp and unused_codes == 0 and not has_webauthn:
            raise ProblemException(
                code="MFA_ENROLLMENT_REQUIRED",
                status=403,
                title="MFA Enrollment Required",
                detail="Administrators must enroll and confirm a second authentication factor.",
            )

    admin_methods: list[str] = []
    if has_webauthn:
        admin_methods.append("webauthn")
    if has_active_totp:
        admin_methods.append("totp")
    if unused_codes > 0:
        admin_methods.append("recovery")

    preferred = "webauthn" if has_webauthn else "totp"

    if principal.aal_level < AAL2_LEVEL:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Authentication Required",
            detail="Administrative routes require multi-factor authentication (AAL2).",
            methods=admin_methods,
            preferred_method=preferred,
        )

    if principal.session_id is not None:
        verified_at = principal.aal2_verified_at
        if verified_at is None:
            raise ProblemException(
                code="AAL2_STALE",
                status=403,
                title="AAL2 Session Stale",
                detail="AAL2 verification timestamp is missing or stale.",
                methods=admin_methods,
                preferred_method=preferred,
            )
        now = datetime.now(UTC)
        if verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=UTC)
        age = (now - verified_at).total_seconds()
        if age > ADMIN_AAL2_MAX_AGE_SECONDS:
            detail_msg = (
                f"AAL2 verification is stale ({int(age)}s > {ADMIN_AAL2_MAX_AGE_SECONDS}s)."
            )
            raise ProblemException(
                code="AAL2_STALE",
                status=403,
                title="AAL2 Session Stale",
                detail=detail_msg,
                methods=admin_methods,
                preferred_method=preferred,
            )

    return principal


def _has_dependency(dependant: object, target: object) -> bool:
    """Recursively check whether target callable is present in dependant tree."""
    if getattr(dependant, "call", None) == target:
        return True
    sub_deps = getattr(dependant, "dependencies", [])
    return any(_has_dependency(sub, target) for sub in sub_deps)


def assert_admin_routes_protected(app: object) -> list[str]:
    """Audit route table for admin routes lacking require_admin_aal2.

    Returns a list of route paths matching '/api/v1/admin*' that lack require_admin_aal2.
    """
    unprotected: list[str] = []
    routes = getattr(app, "routes", [])
    for route in routes:
        if hasattr(route, "effective_route_contexts") and callable(route.effective_route_contexts):
            for ctx in route.effective_route_contexts():
                path = getattr(ctx, "path", "")
                if path.startswith("/api/v1/admin"):
                    dependant = getattr(ctx, "dependant", None)
                    if dependant is None or not _has_dependency(dependant, require_admin_aal2):
                        unprotected.append(path)
        else:
            path = getattr(route, "path", "")
            if path.startswith("/api/v1/admin"):
                dependant = getattr(route, "dependant", None)
                if dependant is None or not _has_dependency(dependant, require_admin_aal2):
                    unprotected.append(path)
    return unprotected
