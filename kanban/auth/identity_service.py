# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Database identity resolver and identity link service (S4.2, KB-P2-08)."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import RowMapping, event, text

from database.session import RLSContext, bind_rls_context
from kanban.api.problems import ProblemException
from kanban.auth.cards.repository import get_for_login
from kanban.auth.identity import ExternalIdentityAssertion, ResolvedLogin
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.requests import Request

    from database.session import RLSSessionFactory
    from kanban.api.deps import PrincipalContext
    from kanban.auth.sessions.service import SessionService

logger = logging.getLogger("kanban.auth.identity")

__all__ = [
    "DatabaseIdentityResolver",
    "IdentityLinkService",
]


def _evaluate_card_access(  # noqa: C901, PLR0911
    card_row: RowMapping | Mapping[str, Any] | None,
    assertion: ExternalIdentityAssertion,
) -> tuple[bool, bool]:
    """Evaluate whether assertion meets card allowlist policy. Returns (is_allowed, is_admin)."""
    if card_row is None:
        return True, False

    pub_cfg = card_row.get("public_config", {}) if hasattr(card_row, "get") else {}
    if not isinstance(pub_cfg, dict):
        pub_cfg = {}

    # LDAP Group policy
    access_mode = pub_cfg.get("access_mode", "any_user")
    admin_groups: list[str] = pub_cfg.get("admin_groups") or []
    user_groups: list[str] = pub_cfg.get("user_groups") or []

    assertion_groups_lower = {g.strip().lower() for g in assertion.groups}
    in_ldap_admin = any(ag.strip().lower() in assertion_groups_lower for ag in admin_groups)
    in_ldap_user = any(ug.strip().lower() in assertion_groups_lower for ug in user_groups)

    if in_ldap_admin:
        return True, True
    if in_ldap_user:
        return True, False
    if access_mode == "group_restricted" and (admin_groups or user_groups):
        return False, False

    # OIDC/OAuth allowlist policy
    admin_allowlist: list[str] = pub_cfg.get("admin_allowlist") or []
    user_allowlist: list[str] = pub_cfg.get("user_allowlist") or []

    is_admin = "SERVER_ADMIN" in assertion.groups
    if not admin_allowlist and not user_allowlist:
        return True, is_admin

    user_candidates: set[str] = set()
    if assertion.email:
        user_candidates.add(assertion.email.lower())
        user_candidates.add(assertion.email.split("@")[0].lower())
    if assertion.subject:
        user_candidates.add(assertion.subject.lower())
    if assertion.display_name:
        user_candidates.add(assertion.display_name.lower())

    in_admin = any(ag.strip().lower() in user_candidates for ag in admin_allowlist)
    in_user = any(ug.strip().lower() in user_candidates for ug in user_allowlist)

    if in_admin:
        return True, True
    if in_user:
        return True, False

    return False, False


async def _ensure_server_admin_role(
    db_session: AsyncSession,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
) -> None:
    """Grant SERVER_ADMIN role binding if not already present."""
    db_session.info["rls_bound"] = True
    try:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT kb_auth_ensure_server_admin_role(:ws_id, :pid)"),
                {"ws_id": workspace_id, "pid": principal_id},
            )
            return
    except Exception:  # noqa: BLE001
        logger.debug("Fallback to direct role_bindings insert for SERVER_ADMIN")

    db_session.info["rls_bound"] = True
    stmt = text(
        "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type) "
        "VALUES (uuidv7(), :ws_id, :pid, 'SERVER_ADMIN', 'server') "
        "ON CONFLICT DO NOTHING"
    )
    await db_session.execute(stmt, {"ws_id": workspace_id, "pid": principal_id})


class DatabaseIdentityResolver:
    """Production identity resolver binding IdP assertions to user principals (KB-P2-08).

    Enforces strict (auth_card_id, immutable_subject_id) uniqueness,
    zero cross-card email auto-merge, and explicit AAL2 link verification.
    """

    def __init__(
        self,
        session_factory: RLSSessionFactory | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        """Initialize DatabaseIdentityResolver with session factory and service."""
        self._session_factory = session_factory
        self._session_service = session_service

    def _get_session_factory(self, request: Request) -> Any:  # noqa: ANN401
        """Resolve session factory from self or request.app.state."""
        if self._session_factory is not None:
            return self._session_factory
        app = request.scope.get("app")
        factory = getattr(app.state, "session_factory", None) if app is not None else None
        if factory is not None:
            return factory
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)

    @asynccontextmanager
    async def _open_session(
        self, request: Request, ctx: RLSContext | None = None
    ) -> AsyncIterator[AsyncSession]:
        """Open an RLS-bound AsyncSession from configured session_factory or app state."""
        session_factory = self._get_session_factory(request)
        effective_ctx = ctx or RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("auth",),
            aal_level=1,
        )

        if hasattr(session_factory, "session"):
            async with session_factory.session(effective_ctx) as sess:
                if hasattr(sess, "sync_session"):

                    @event.listens_for(sess.sync_session, "after_begin")
                    def _rebind_on_begin(s: Any, _trans: Any, _conn: Any) -> None:  # noqa: ANN401
                        s.info["rls_bound"] = True

                yield sess
        elif hasattr(session_factory, "sessionmaker"):
            maker = session_factory.sessionmaker
            async with maker() as sess, sess.begin():
                if hasattr(sess, "sync_session"):

                    @event.listens_for(sess.sync_session, "after_begin")
                    def _rebind_on_begin_maker(s: Any, _trans: Any, _conn: Any) -> None:  # noqa: ANN401
                        s.info["rls_bound"] = True

                await bind_rls_context(sess, effective_ctx)
                yield sess
        elif callable(session_factory):
            res = session_factory()
            if hasattr(res, "__aenter__"):
                async with res as sess:
                    yield sess
            else:
                yield res
        else:
            msg = "Configured session_factory must have sessionmaker or be callable"
            raise TypeError(msg)

    async def resolve(
        self,
        assertion: ExternalIdentityAssertion,
        request: Request,
        link_intent_id: uuid.UUID | None,
    ) -> ResolvedLogin:
        """Resolve external identity assertion, or raise ProblemException."""
        if link_intent_id is not None:
            return await self._resolve_link(assertion, request, link_intent_id)
        return await self._resolve_login(assertion, request)

    async def _resolve_link(
        self,
        assertion: ExternalIdentityAssertion,
        request: Request,
        link_intent_id: uuid.UUID,
    ) -> ResolvedLogin:
        """Explicit AAL2 link flow: atomically bind IdP identity to active caller."""
        principal: PrincipalContext | None = getattr(request.state, "principal", None)
        if principal is None:
            resolver = getattr(request.app.state, "principal_resolver", None)
            if resolver is not None:
                principal = await resolver.resolve(request)

        if principal is None or principal.session_id is None:
            raise ProblemException(
                code="LINK_INTENT_INVALID",
                status=400,
                title="Link Intent Invalid",
                detail="Active authenticated session required for identity linking",
            )

        async with self._open_session(request) as db_session:
            stmt = text(
                "SELECT kb_auth.identity_link_consume_and_bind("
                "  :p_intent_id, :p_principal_id, :p_session_id, :p_card_id, :p_subject, :p_email"
                ")"
            )
            try:
                await db_session.execute(
                    stmt,
                    {
                        "p_intent_id": link_intent_id,
                        "p_principal_id": principal.principal_id,
                        "p_session_id": principal.session_id,
                        "p_card_id": assertion.card_id,
                        "p_subject": assertion.subject,
                        "p_email": assertion.email,
                    },
                )
            except Exception as exc:
                err_msg = str(exc)
                if "LINK_INTENT_INVALID" in err_msg:
                    raise ProblemException(
                        code="LINK_INTENT_INVALID",
                        status=400,
                        title="Link Intent Invalid",
                        detail="Link intent is invalid, expired, or was already consumed",
                    ) from exc
                if "IDENTITY_ALREADY_LINKED" in err_msg or "23505" in err_msg:
                    raise ProblemException(
                        code="IDENTITY_ALREADY_LINKED",
                        status=409,
                        title="Identity Already Linked",
                        detail="External identity is already linked to an account",
                    ) from exc
                raise

            try:
                await record_activity(
                    db_session,
                    workspace_id=principal.workspace_id,
                    actor_principal_id=principal.principal_id,
                    event_type=ActivityEventType.IDENTITY_LINKED,
                    payload={
                        "card_id": str(assertion.card_id),
                        "subject": assertion.subject,
                        "email": assertion.email,
                    },
                )
            except Exception:
                logger.debug("Failed to record IDENTITY_LINKED activity", exc_info=True)

            await db_session.commit()

            return ResolvedLogin(
                principal_id=principal.principal_id,
                workspace_id=principal.workspace_id,
                aal_level=principal.aal_level,
                mfa_pending=False,
            )

    async def _resolve_login(
        self,
        assertion: ExternalIdentityAssertion,
        request: Request,
    ) -> ResolvedLogin:
        """Resolve standard login: lookup bound identity or auto-provision if permitted."""
        async with self._open_session(request) as db_session:
            lookup_stmt = text(
                "SELECT id, workspace_id, principal_id, status, last_login_at, "
                "       subject_email_at_link, user_email, display_name "
                "FROM kb_auth.identity_lookup(:card_id, :subject)"
            )
            lookup_res = await db_session.execute(
                lookup_stmt,
                {"card_id": assertion.card_id, "subject": assertion.subject},
            )
            identity_row = lookup_res.mappings().first()

            if identity_row is not None:
                return await self._resolve_bound_login(db_session, assertion, identity_row)
            return await self._resolve_unbound_login(db_session, assertion)

    async def _resolve_bound_login(
        self,
        db_session: AsyncSession,
        assertion: ExternalIdentityAssertion,
        identity_row: RowMapping | Mapping[str, Any],
    ) -> ResolvedLogin:
        """Handle login when existing user identity binding exists."""
        if identity_row["status"] != "ACTIVE":
            logger.warning(
                "External login rejected: account disabled (card_id=%s, principal_id=%s)",
                assertion.card_id,
                identity_row["principal_id"],
            )
            raise ProblemException(
                code="ACCOUNT_DISABLED",
                status=403,
                title="Account Disabled",
                detail="Account is disabled",
            )

        await db_session.execute(
            text(
                "SELECT set_config('app.principal_id', :p_id, true), "
                "set_config('app.workspace_id', :w_id, true)"
            ),
            {
                "p_id": str(identity_row["principal_id"]),
                "w_id": str(identity_row["workspace_id"]),
            },
        )

        # Check card allowlist policy if configured
        card_res = await db_session.execute(
            text(
                "SELECT id, workspace_id, provider_kind, public_config "
                "FROM kb_auth.card_get_by_id(:id)"
            ),
            {"id": assertion.card_id},
        )
        card_row = card_res.mappings().first()
        is_allowed, is_admin_card = _evaluate_card_access(card_row, assertion)
        if not is_allowed:
            logger.warning(
                "External login rejected: user not in card allowlist (card_id=%s, email=%s)",
                assertion.card_id,
                assertion.email,
            )
            raise ProblemException(
                code="IDENTITY_NOT_PROVISIONED",
                status=403,
                title="Access Denied",
                detail="User is not in the authorized access list",
            )
        if is_admin_card:
            await _ensure_server_admin_role(
                db_session, identity_row["workspace_id"], identity_row["principal_id"]
            )

        # Record login timestamp
        await db_session.execute(
            text("SELECT kb_auth.identity_record_login(:id)"),
            {"id": identity_row["id"]},
        )

        # Check if principal holds SERVER_ADMIN or PROJECT_ADMIN
        admin_res = await db_session.execute(
            text(
                "SELECT 1 FROM role_bindings "
                "WHERE principal_id = :p_id AND role IN ('SERVER_ADMIN', 'PROJECT_ADMIN') "
                "LIMIT 1"
            ),
            {"p_id": identity_row["principal_id"]},
        )
        is_admin = admin_res.scalar() is not None

        try:
            await record_activity(
                db_session,
                workspace_id=identity_row["workspace_id"],
                actor_principal_id=identity_row["principal_id"],
                event_type=ActivityEventType.EXTERNAL_LOGIN_SUCCEEDED,
                payload={
                    "card_id": str(assertion.card_id),
                    "subject": assertion.subject,
                    "principal_id": str(identity_row["principal_id"]),
                },
            )
        except Exception:
            logger.debug("Failed to record login success activity", exc_info=True)

        await db_session.commit()
        logger.info(
            "External bound login succeeded (card_id=%s, principal_id=%s, workspace_id=%s)",
            assertion.card_id,
            identity_row["principal_id"],
            identity_row["workspace_id"],
        )

        return ResolvedLogin(
            principal_id=identity_row["principal_id"],
            workspace_id=identity_row["workspace_id"],
            aal_level=1,
            mfa_pending=is_admin,
        )

    @staticmethod
    def _validate_assertion_email(
        card_row: RowMapping | Mapping[str, Any], assertion: ExternalIdentityAssertion
    ) -> None:
        """Validate assertion email is present, verified, and in allowed domains."""
        if not assertion.email or not assertion.email_verified:
            raise ProblemException(
                code="EMAIL_NOT_VERIFIED",
                status=403,
                title="Email Not Verified",
                detail="IdP assertion email must be verified to auto-provision account",
            )

        allowed_domains = card_row["allowed_email_domains"] or []
        if allowed_domains:
            domain = assertion.email.rsplit("@", 1)[1].lower()
            allowed_lower = [d.lower() for d in allowed_domains]
            if domain not in allowed_lower:
                raise ProblemException(
                    code="EMAIL_DOMAIN_FORBIDDEN",
                    status=403,
                    title="Email Domain Forbidden",
                    detail="Email domain is not allowed by this authentication card",
                )

    async def _resolve_unbound_login(  # noqa: C901, PLR0912
        self,
        db_session: AsyncSession,
        assertion: ExternalIdentityAssertion,
    ) -> ResolvedLogin:
        """Handle login when identity is unbound, auto-provisioning if allowed."""
        card_res = await db_session.execute(
            text(
                "SELECT id, workspace_id, is_enabled, auto_provision_users, allowed_email_domains, "
                "       provider_kind, public_config "
                "FROM kb_auth.card_get_by_id(:id)"
            ),
            {"id": assertion.card_id},
        )
        card_row = card_res.mappings().first()

        if card_row is None or not card_row["is_enabled"]:
            raise ProblemException(
                code="IDENTITY_NOT_PROVISIONED",
                status=403,
                title="Identity Not Provisioned",
                detail="External identity is not provisioned in this workspace",
            )

        effective_ws_id = card_row["workspace_id"]
        if effective_ws_id is None:
            try:
                async with db_session.begin_nested():
                    effective_ws_id = await db_session.scalar(
                        text("SELECT get_default_workspace_id()")
                    )
            except Exception:  # noqa: BLE001
                effective_ws_id = None
            if effective_ws_id is None:
                default_ws = await db_session.scalar(
                    text("SELECT id FROM workspaces ORDER BY created_at ASC LIMIT 1")
                )
                effective_ws_id = default_ws

        if effective_ws_id is not None:
            await db_session.execute(
                text("SELECT set_config('app.workspace_id', :w_id, true)"),
                {"w_id": str(effective_ws_id)},
            )

        if not card_row["auto_provision_users"]:
            if effective_ws_id is not None:
                try:
                    await record_activity(
                        db_session,
                        workspace_id=effective_ws_id,
                        actor_principal_id=None,
                        event_type=ActivityEventType.EXTERNAL_LOGIN_UNPROVISIONED,
                        payload={
                            "card_id": str(assertion.card_id),
                            "subject": assertion.subject,
                        },
                    )
                except Exception:
                    logger.debug("Failed to record unprovisioned activity", exc_info=True)
                await db_session.commit()

            logger.warning(
                "External login rejected: auto_provision_users=false on card %s for email=%s",
                assertion.card_id,
                assertion.email,
            )
            raise ProblemException(
                code="IDENTITY_NOT_PROVISIONED",
                status=403,
                title="Identity Not Provisioned",
                detail="External identity is not provisioned in this workspace",
            )

        # Validate email and domain allowlist
        self._validate_assertion_email(card_row, assertion)

        # Check OAuth/OIDC admin and user allowlists if configured
        is_allowed, is_admin_user = _evaluate_card_access(card_row, assertion)
        if not is_allowed:
            logger.warning(
                "External login rejected: user %s not in card allowlist (card_id=%s)",
                assertion.email,
                assertion.card_id,
            )
            raise ProblemException(
                code="IDENTITY_NOT_PROVISIONED",
                status=403,
                title="Access Denied",
                detail="User is not in the authorized access list",
            )

        if effective_ws_id is None:
            msg = "No target workspace found for user auto-provisioning"
            raise RuntimeError(msg)

        # Provision new user atomically (or bind to bootstrap local admin if verified email matches)
        new_principal_id = await self._provision_user(db_session, effective_ws_id, assertion)

        # Bind SERVER_ADMIN role if user qualified as admin
        if is_admin_user:
            if hasattr(db_session, "info") and isinstance(db_session.info, dict):
                db_session.info["rls_bound"] = True
            await _ensure_server_admin_role(db_session, effective_ws_id, new_principal_id)
            await db_session.commit()
            if hasattr(db_session, "info") and isinstance(db_session.info, dict):
                db_session.info["rls_bound"] = True

        logger.info(
            "Auto-provisioned external user (card=%s, principal=%s, ws=%s, admin=%s)",
            assertion.card_id,
            new_principal_id,
            effective_ws_id,
            is_admin_user,
        )
        return ResolvedLogin(
            principal_id=new_principal_id,
            workspace_id=effective_ws_id,
            aal_level=1,
            mfa_pending=is_admin_user,
        )

    @staticmethod
    async def _provision_user(
        db_session: AsyncSession,
        effective_ws_id: uuid.UUID,
        assertion: ExternalIdentityAssertion,
    ) -> uuid.UUID:
        """Provision new user and identity atomically and record audit ledger entry."""
        clean_display = assertion.display_name or (
            assertion.email.split("@")[0] if assertion.email else "User"
        )
        prov_stmt = text(
            "SELECT principal_id, identity_id FROM kb_auth.identity_provision_new_user("
            "  :ws_id, :card_id, :subject, :email, :display_name"
            ")"
        )
        try:
            nested_ctx: Any = db_session.begin_nested()
            if hasattr(nested_ctx, "__aenter__"):
                async with nested_ctx:
                    prov_res = await db_session.execute(
                        prov_stmt,
                        {
                            "ws_id": effective_ws_id,
                            "card_id": assertion.card_id,
                            "subject": assertion.subject,
                            "email": assertion.email,
                            "display_name": clean_display,
                        },
                    )
            else:
                if hasattr(nested_ctx, "close"):
                    nested_ctx.close()
                prov_res = await db_session.execute(
                    prov_stmt,
                    {
                        "ws_id": effective_ws_id,
                        "card_id": assertion.card_id,
                        "subject": assertion.subject,
                        "email": assertion.email,
                        "display_name": clean_display,
                    },
                )
        except Exception as exc:
            err_msg = str(exc)
            if "IDENTITY_LINK_REQUIRED" in err_msg:
                try:
                    await record_activity(
                        db_session,
                        workspace_id=effective_ws_id,
                        actor_principal_id=None,
                        event_type=ActivityEventType.IDENTITY_AUTO_MERGE_BLOCKED,
                        payload={
                            "card_id": str(assertion.card_id),
                            "subject": assertion.subject,
                            "email": assertion.email,
                        },
                    )
                    await db_session.commit()
                except Exception:
                    logger.debug("Failed to record auto-merge blocked activity", exc_info=True)
                logger.warning(
                    "External login auto-merge blocked: email=%s already exists in workspace=%s",
                    assertion.email,
                    effective_ws_id,
                )
                raise ProblemException(
                    code="IDENTITY_LINK_REQUIRED",
                    status=409,
                    title="Identity Link Required",
                    detail=(
                        "An account with this email already exists. "
                        "Sign in with your existing credentials, elevate to AAL2, "
                        "and link this provider in settings."
                    ),
                ) from exc
            if "IDENTITY_ALREADY_LINKED" in err_msg:
                raise ProblemException(
                    code="IDENTITY_ALREADY_LINKED",
                    status=409,
                    title="Identity Already Linked",
                    detail="External identity is already linked to an account",
                ) from exc
            raise
        prov_row = prov_res.mappings().first()
        if prov_row is None:
            msg = "Failed to provision new user identity"
            raise RuntimeError(msg)

        new_principal_id: uuid.UUID = prov_row["principal_id"]

        try:
            await record_activity(
                db_session,
                workspace_id=effective_ws_id,
                actor_principal_id=new_principal_id,
                event_type=ActivityEventType.EXTERNAL_LOGIN_SUCCEEDED,
                payload={
                    "card_id": str(assertion.card_id),
                    "subject": assertion.subject,
                    "principal_id": str(new_principal_id),
                },
            )
        except Exception:
            logger.debug("Failed to record provision success activity", exc_info=True)

        await db_session.commit()
        return new_principal_id


class IdentityLinkService:
    """Service handling explicit identity linking, unlinking, and listing operations (KB-P2-08)."""

    async def start_link(
        self,
        session: AsyncSession,
        principal: PrincipalContext,
        card_slug: str,
        request: Request,
    ) -> dict[str, Any]:
        """Initiate identity linking flow for target auth provider card."""
        card = await get_for_login(session, card_slug)

        if card is None or not card.is_enabled:
            raise ProblemException(
                code="CARD_NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail="Authentication card not found or disabled",
            )

        provider_kind = card.provider_kind
        if provider_kind not in ("OIDC", "OAUTH2", "LDAP"):
            raise ProblemException(
                code="INVALID_PROVIDER_KIND",
                status=400,
                title="Invalid Provider Kind",
                detail="Card provider kind does not support identity linking",
            )

        intent_id = await session.scalar(
            text("SELECT kb_auth.identity_link_intent_create(:p_id, :s_id, :card_id, 300)"),
            {
                "p_id": principal.principal_id,
                "s_id": principal.session_id,
                "card_id": card.id,
            },
        )

        if provider_kind in ("OIDC", "OAUTH2"):
            oidc_flow = getattr(request.app.state, "oidc_flow", None)
            if oidc_flow is None:
                msg = "OIDC flow is not configured on app.state.oidc_flow"
                raise RuntimeError(msg)
            start_resp = await oidc_flow.start(
                session,
                slug=card.slug,
                return_to="/",
                link_intent_id=intent_id,
                request=request,
            )
            return {
                "mode": "redirect",
                "authorize_url": start_resp.authorize_url,
                "cookie_header": start_resp.cookie_header,
            }

        return {
            "mode": "ldap_credentials",
            "link_intent_id": str(intent_id),
        }

    async def link_ldap(  # noqa: PLR0913
        self,
        session: AsyncSession,
        principal: PrincipalContext,
        link_intent_id: uuid.UUID,
        *,
        username: str,
        password: str,
        request: Request,
    ) -> dict[str, Any]:
        """Authenticate against target LDAP card and bind identity under link intent."""
        intent_res = await session.execute(
            text(
                "SELECT id, target_card_id, principal_id, session_id, expires_at, consumed_at "
                "FROM kb_auth.identity_link_intent_get(:id)"
            ),
            {"id": link_intent_id},
        )
        intent = intent_res.mappings().first()

        if intent is None or intent["consumed_at"] is not None:
            raise ProblemException(
                code="LINK_INTENT_INVALID",
                status=400,
                title="Link Intent Invalid",
                detail="Link intent is invalid, expired, or was already consumed",
            )

        if (
            intent["principal_id"] != principal.principal_id
            or intent["session_id"] != principal.session_id
        ):
            raise ProblemException(
                code="LINK_INTENT_INVALID",
                status=400,
                title="Link Intent Invalid",
                detail="Link intent does not match active session or principal",
            )

        card_slug = await session.scalar(
            text("SELECT slug FROM kb_auth.card_get_by_id(:id)"),
            {"id": intent["target_card_id"]},
        )
        card = await get_for_login(session, card_slug) if card_slug else None
        if card is None or not card.is_enabled or card.provider_kind != "LDAP":
            raise ProblemException(
                code="CARD_NOT_FOUND",
                status=404,
                title="Card Not Found",
                detail="Target LDAP authentication card not found or disabled",
            )

        ldap_service = getattr(request.app.state, "ldap_service", None)
        if ldap_service is None:
            msg = "LDAP service is not configured on app.state.ldap_service"
            raise RuntimeError(msg)

        await ldap_service.authenticate_user(
            session,
            card,
            username=username,
            password=password,
            request=request,
            link_intent_id=link_intent_id,
        )

        return {"status": "ok", "message": "Identity linked successfully"}

    async def list_identities(
        self,
        session: AsyncSession,
        principal_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """List all external identities linked to the specified principal."""
        res = await session.execute(
            text(
                "SELECT id, auth_card_id, card_slug, card_display_name, provider_kind, "
                "       immutable_subject_id, subject_email_at_link, created_at, last_login_at "
                "FROM kb_auth.identity_list_for_principal(:p_id)"
            ),
            {"p_id": principal_id},
        )

        return [
            {
                "id": str(r["id"]),
                "card_slug": r["card_slug"],
                "card_display_name": r["card_display_name"],
                "provider_kind": r["provider_kind"],
                "subject_email_at_link": r["subject_email_at_link"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "last_login_at": r["last_login_at"].isoformat() if r["last_login_at"] else None,
                "immutable_subject_id": r["immutable_subject_id"],
            }
            for r in res.mappings().all()
        ]

    async def unlink_identity(
        self,
        session: AsyncSession,
        principal: PrincipalContext,
        identity_id: uuid.UUID,
    ) -> None:
        """Unlink external identity while enforcing anti-lockout minimum auth method safeguards."""
        try:
            await session.execute(
                text("SELECT kb_auth.identity_unlink(:p_id, :id)"),
                {"p_id": principal.principal_id, "id": identity_id},
            )
        except Exception as exc:
            err_msg = str(exc)
            if "IDENTITY_NOT_FOUND" in err_msg:
                raise ProblemException(
                    code="NOT_FOUND",
                    status=404,
                    title="Identity Not Found",
                    detail="Identity not found or does not belong to caller",
                ) from exc
            if "LAST_AUTH_METHOD" in err_msg:
                raise ProblemException(
                    code="LAST_AUTH_METHOD",
                    status=409,
                    title="Last Auth Method",
                    detail="Cannot unlink last remaining authentication method",
                ) from exc
            raise

        try:
            await record_activity(
                session,
                workspace_id=principal.workspace_id,
                actor_principal_id=principal.principal_id,
                event_type=ActivityEventType.IDENTITY_UNLINKED,
                payload={"identity_id": str(identity_id)},
            )
        except Exception:
            logger.debug("Failed to record unlinked activity", exc_info=True)
