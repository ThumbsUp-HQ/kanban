# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, PLR0913, PLR0917, SLF001, ARG001, ARG005, ANN401, D401, S106, PT011, PT017, PTH123, ASYNC230, PLW2901, C901, PLC0415
"""Feature unit tests for identity linking and unlink boundary controls (KB-P2-08)."""

from __future__ import annotations

import json
import pathlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from starlette.requests import Request

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.v1.auth_identities import router as auth_identities_router
from kanban.auth.identity import ExternalIdentityAssertion
from kanban.auth.identity_service import DatabaseIdentityResolver, IdentityLinkService
from kanban.services.activity import ActivityEventType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


def _make_dummy_request(
    app: FastAPI | None = None,
    principal: PrincipalContext | None = None,
    session_factory: RLSSessionFactory | None = None,
) -> Request:
    """Helper to create dummy starlette request with app.state."""
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/callback",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    if app is not None:
        scope["app"] = app
    req = Request(scope)
    if principal is not None:
        req.state.principal = principal
    if app is not None and session_factory is not None:
        app.state.session_factory = session_factory
    return req


async def _create_test_env(
    factory: RLSSessionFactory,
    *,
    num_users: int = 1,
) -> tuple[uuid.UUID, list[tuple[uuid.UUID, uuid.UUID]], uuid.UUID, uuid.UUID]:
    """Provision workspace, users, sessions, and cards for testing."""
    ws_id = uuid.uuid4()
    card_oidc_id = uuid.uuid4()
    card_ldap_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:6]

    users_and_sessions: list[tuple[uuid.UUID, uuid.UUID]] = []

    ctx = RLSContext(principal_id=uuid.uuid4(), workspace_id=ws_id, aal_level=2)
    async with factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-link-{suffix}", "name": "Link Test WS"},
        )

        # Create OIDC / OAuth card
        await session.execute(
            text(
                "INSERT INTO auth_provider_cards ("
                "  id, workspace_id, provider_kind, slug, display_name, is_enabled, sort_rank, "
                "  auto_provision_users, allowed_email_domains"
                ") VALUES ("
                "  :id, :ws_id, 'OIDC', :slug, 'GitHub OAuth', true, '0|h00000:', true, ARRAY[]::text[]"
                ")"
            ),
            {"id": card_oidc_id, "ws_id": ws_id, "slug": f"github-{suffix}"},
        )

        # Create LDAP card
        await session.execute(
            text(
                "INSERT INTO auth_provider_cards ("
                "  id, workspace_id, provider_kind, slug, display_name, is_enabled, sort_rank, "
                "  auto_provision_users, allowed_email_domains"
                ") VALUES ("
                "  :id, :ws_id, 'LDAP', :slug, 'Corp LDAP', true, '0|h00001:', true, ARRAY[]::text[]"
                ")"
            ),
            {"id": card_ldap_id, "ws_id": ws_id, "slug": f"ldap-{suffix}"},
        )

        # Create requested users and sessions
        for i in range(num_users):
            u_id = uuid.uuid4()
            s_id = uuid.uuid4()
            clean_display = f"Test User {i + 1}"
            clean_email = f"user{i + 1}-{suffix}@example.com"

            await session.execute(
                text(
                    "INSERT INTO principals (id, principal_type, workspace_id, status, display_name) "
                    "VALUES (:id, 'USER', :ws_id, 'ACTIVE', :disp)"
                ),
                {"id": u_id, "ws_id": ws_id, "disp": clean_display},
            )
            await session.execute(
                text(
                    "INSERT INTO objects (id, object_type, workspace_id, canonical_key, display_title, created_by_id) "
                    "VALUES (:id, 'user'::object_kind, :ws_id, :ckey, :title, :u_id)"
                ),
                {
                    "id": u_id,
                    "ws_id": ws_id,
                    "ckey": f"usr-{u_id.hex}",
                    "title": clean_display,
                    "u_id": u_id,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                    "VALUES (:id, 'user', 'USER', :ws_id, :email)"
                ),
                {"id": u_id, "ws_id": ws_id, "email": clean_email},
            )
            await session.execute(
                text(
                    "INSERT INTO sessions ("
                    "  id, token_sha256, principal_id, workspace_id, auth_card_id, aal_level, "
                    "  aal2_verified_at, idle_expires_at, absolute_expires_at"
                    ") VALUES ("
                    "  :id, :token_sha, :p_id, :ws_id, :card_id, 2, "
                    "  clock_timestamp(), clock_timestamp() + interval '1 hour', clock_timestamp() + interval '8 hours'"
                    ")"
                ),
                {
                    "id": s_id,
                    "token_sha": uuid.uuid4().bytes + uuid.uuid4().bytes,
                    "p_id": u_id,
                    "ws_id": ws_id,
                    "card_id": card_oidc_id,
                },
            )
            users_and_sessions.append((u_id, s_id))

    return ws_id, users_and_sessions, card_oidc_id, card_ldap_id


@pytest.mark.asyncio
async def test_case_5_positive_explicit_aal2_link_oidc_and_ldap(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 5: Positive explicit AAL2 link (OIDC & LDAP flows).

    User U1 elevates session to AAL2 -> starts link for GitHub card -> completes callback ->
    user_identities row created for U1; repeats for LDAP card -> U1 can now sign in via all linked cards.
    """
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, users_and_sessions, card_oidc_id, card_ldap_id = await _create_test_env(
        session_factory, num_users=2
    )
    u1_id, s1_id = users_and_sessions[0]
    _u2_id, _s2_id = users_and_sessions[1]

    link_service = IdentityLinkService()
    resolver = DatabaseIdentityResolver(session_factory=session_factory)

    app = FastAPI()
    app.state.session_factory = session_factory
    principal_ctx = PrincipalContext(
        principal_id=u1_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
        session_id=s1_id,
        aal2_verified_at=datetime.now(UTC),
    )

    # 1. Start link for OIDC card (mock oidc_flow)
    mock_oidc = AsyncMock()
    mock_oidc.start = AsyncMock(
        return_value=type(
            "StartResp",
            (),
            {
                "authorize_url": "https://github.com/login/oauth/authorize?state=xyz",
                "cookie_header": None,
            },
        )()
    )
    app.state.oidc_flow = mock_oidc

    req = _make_dummy_request(app, principal=principal_ctx, session_factory=session_factory)

    async with session_factory.session(
        RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)
    ) as session:
        # Get card slug
        card_slug = await session.scalar(
            text("SELECT slug FROM auth_provider_cards WHERE id = :id"), {"id": card_oidc_id}
        )
        assert card_slug is not None
        start_res = await link_service.start_link(session, principal_ctx, card_slug, req)
        assert start_res["mode"] == "redirect"
        assert "authorize_url" in start_res

    # Check intent was inserted in db
    intent_id = mock_oidc.start.call_args.kwargs["link_intent_id"]
    assert intent_id is not None

    # 2. Complete callback for OIDC assertion
    assertion_oidc = ExternalIdentityAssertion(
        card_id=card_oidc_id,
        subject="gh-user-u1",
        email="u1@github.com",
        email_verified=True,
        display_name="User One",
        groups=(),
    )
    resolved_oidc = await resolver.resolve(assertion_oidc, req, link_intent_id=intent_id)
    assert resolved_oidc.principal_id == u1_id
    assert resolved_oidc.workspace_id == ws_id

    # 3. Repeat for LDAP card via link_ldap
    async with session_factory.session(
        RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)
    ) as session:
        ldap_card_slug = await session.scalar(
            text("SELECT slug FROM auth_provider_cards WHERE id = :id"), {"id": card_ldap_id}
        )
        assert ldap_card_slug is not None
        start_ldap_res = await link_service.start_link(session, principal_ctx, ldap_card_slug, req)
        assert start_ldap_res["mode"] == "ldap_credentials"
        ldap_intent_id = uuid.UUID(start_ldap_res["link_intent_id"])

    # Mock LDAP service
    async def mock_authenticate_user(
        sess: Any,
        card: Any,
        username: str,
        password: str,
        request: Request,
        link_intent_id: uuid.UUID,
    ) -> None:
        assertion_ldap = ExternalIdentityAssertion(
            card_id=card_ldap_id,
            subject=f"cn={username},dc=corp,dc=example",
            email=f"{username}@corp.example",
            email_verified=True,
            display_name="User One LDAP",
            groups=(),
        )
        await resolver.resolve(assertion_ldap, request, link_intent_id=link_intent_id)

    mock_ldap = AsyncMock()
    mock_ldap.authenticate_user = AsyncMock(side_effect=mock_authenticate_user)
    app.state.ldap_service = mock_ldap

    async with session_factory.session(
        RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)
    ) as session:
        link_ldap_out = await link_service.link_ldap(
            session,
            principal_ctx,
            link_intent_id=ldap_intent_id,
            username="u1_ldap",
            password="secretpassword",
            request=req,
        )
        assert link_ldap_out["status"] == "ok"

    # Verify both identities exist in list_identities
    async with session_factory.session(
        RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)
    ) as session:
        identities = await link_service.list_identities(session, u1_id)
        assert len(identities) == 2
        card_slugs = {item["card_slug"] for item in identities}
        assert card_slug in card_slugs
        assert ldap_card_slug in card_slugs

    # 4. Verify U1 can now sign in via both linked cards independently
    login_oidc = await resolver.resolve(assertion_oidc, req, link_intent_id=None)
    assert login_oidc.principal_id == u1_id

    assertion_ldap_check = ExternalIdentityAssertion(
        card_id=card_ldap_id,
        subject="cn=u1_ldap,dc=corp,dc=example",
        email="u1_ldap@corp.example",
        email_verified=True,
        display_name="User One LDAP",
        groups=(),
    )
    login_ldap = await resolver.resolve(assertion_ldap_check, req, link_intent_id=None)
    assert login_ldap.principal_id == u1_id


@pytest.mark.asyncio
async def test_case_6_security_aal1_and_stale_aal2_link_blocked(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 6: Calling /identities/link/start with AAL1 -> 403 AAL2_REQUIRED; with AAL2 > 900s -> 403 AAL2_STALE."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, users_and_sessions, card_oidc_id, _ = await _create_test_env(
        session_factory, num_users=1
    )
    u1_id, s1_id = users_and_sessions[0]

    app = FastAPI()
    app.state.session_factory = session_factory
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.include_router(auth_identities_router, prefix="/api/v1")

    # Fetch card slug
    ctx = RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx) as session:
        card_slug = await session.scalar(
            text("SELECT slug FROM auth_provider_cards WHERE id = :id"), {"id": card_oidc_id}
        )

    # Dependency override helper
    current_principal: PrincipalContext | None = None

    async def get_test_principal() -> PrincipalContext:
        assert current_principal is not None
        return current_principal

    app.dependency_overrides[get_principal] = get_test_principal

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # A: AAL1 session -> 403 AAL2_REQUIRED
        current_principal = PrincipalContext(
            principal_id=u1_id,
            workspace_id=ws_id,
            token_scopes=("session",),
            aal_level=1,
            session_id=s1_id,
            aal2_verified_at=None,
        )
        resp1 = await client.post(
            "/api/v1/auth/identities/link/start",
            json={"card_slug": card_slug},
        )
        assert resp1.status_code == 403
        data1 = resp1.json()
        assert data1["code"] == "AAL2_REQUIRED"

        # B: Stale AAL2 session (> 900s) -> 403 AAL2_STALE
        stale_time = datetime.now(UTC) - timedelta(seconds=905)
        current_principal = PrincipalContext(
            principal_id=u1_id,
            workspace_id=ws_id,
            token_scopes=("session",),
            aal_level=2,
            session_id=s1_id,
            aal2_verified_at=stale_time,
        )
        resp2 = await client.post(
            "/api/v1/auth/identities/link/start",
            json={"card_slug": card_slug},
        )
        assert resp2.status_code == 403
        data2 = resp2.json()
        assert data2["code"] == "AAL2_STALE"


@pytest.mark.asyncio
async def test_case_7_security_cross_session_csrf_and_intent_replay(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 7: Cross-session CSRF, intent replay, expired intent, wrong card all rejected."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, users_and_sessions, card_oidc_id, card_ldap_id = await _create_test_env(
        session_factory, num_users=2
    )
    u1_id, s1_id = users_and_sessions[0]
    u2_id, s2_id = users_and_sessions[1]

    resolver = DatabaseIdentityResolver(session_factory=session_factory)
    app = FastAPI()
    app.state.session_factory = session_factory

    # 1. Create intent for U1 / S1 / card_oidc_id
    ctx = RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx) as session:
        intent_id = await session.scalar(
            text("SELECT kb_auth.identity_link_intent_create(:p_id, :s_id, :card_id, 300)"),
            {"p_id": u1_id, "s_id": s1_id, "card_id": card_oidc_id},
        )
        await session.commit()

    assert intent_id is not None

    # Sub-case A: Cross-session CSRF - S2 presents intent created for S1
    p2_ctx = PrincipalContext(
        principal_id=u2_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
        session_id=s2_id,
    )
    req_s2 = _make_dummy_request(app, principal=p2_ctx, session_factory=session_factory)
    assertion = ExternalIdentityAssertion(
        card_id=card_oidc_id,
        subject="gh-attacker-sub",
        email="attacker@example.com",
        email_verified=True,
        display_name="Attacker",
        groups=(),
    )
    with pytest.raises(ProblemException) as exc_csrf:
        await resolver.resolve(assertion, req_s2, link_intent_id=intent_id)
    assert exc_csrf.value.status == 400
    assert exc_csrf.value.code == "LINK_INTENT_INVALID"

    # Sub-case B: Wrong card - assertion from card_ldap_id presented for intent created for card_oidc_id
    p1_ctx = PrincipalContext(
        principal_id=u1_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
        session_id=s1_id,
    )
    req_s1 = _make_dummy_request(app, principal=p1_ctx, session_factory=session_factory)
    assertion_wrong_card = ExternalIdentityAssertion(
        card_id=card_ldap_id,
        subject="ldap-u1",
        email="u1@example.com",
        email_verified=True,
        display_name="User One",
        groups=(),
    )
    with pytest.raises(ProblemException) as exc_card:
        await resolver.resolve(assertion_wrong_card, req_s1, link_intent_id=intent_id)
    assert exc_card.value.status == 400
    assert exc_card.value.code == "LINK_INTENT_INVALID"

    # Sub-case C: Legitimate consumption succeeds
    assertion_valid = ExternalIdentityAssertion(
        card_id=card_oidc_id,
        subject="gh-u1-valid",
        email="u1@example.com",
        email_verified=True,
        display_name="User One",
        groups=(),
    )
    resolved = await resolver.resolve(assertion_valid, req_s1, link_intent_id=intent_id)
    assert resolved.principal_id == u1_id

    # Sub-case D: Replay of consumed intent fails
    with pytest.raises(ProblemException) as exc_replay:
        await resolver.resolve(assertion_valid, req_s1, link_intent_id=intent_id)
    assert exc_replay.value.status == 400
    assert exc_replay.value.code == "LINK_INTENT_INVALID"

    # Sub-case E: Expired intent (> 300s) fails
    async with session_factory.session(ctx) as session:
        expired_intent_id = uuid.uuid4()
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text(
                "INSERT INTO identity_link_intents ("
                "  id, principal_id, session_id, target_card_id, expires_at, consumed_at"
                ") VALUES ("
                "  :id, :p_id, :s_id, :card_id, clock_timestamp() - interval '5 seconds', NULL"
                ")"
            ),
            {"id": expired_intent_id, "p_id": u1_id, "s_id": s1_id, "card_id": card_oidc_id},
        )
        await session.commit()

    with pytest.raises(ProblemException) as exc_expired:
        await resolver.resolve(assertion_valid, req_s1, link_intent_id=expired_intent_id)
    assert exc_expired.value.status == 400
    assert exc_expired.value.code == "LINK_INTENT_INVALID"


@pytest.mark.asyncio
async def test_case_8_security_already_linked_subject_rejected(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 8: Attempting to link (card_B, sub_B) already owned by user U2 onto user U1 raises 409 IDENTITY_ALREADY_LINKED."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, users_and_sessions, card_oidc_id, _ = await _create_test_env(
        session_factory, num_users=2
    )
    u1_id, s1_id = users_and_sessions[0]
    u2_id, s2_id = users_and_sessions[1]

    resolver = DatabaseIdentityResolver(session_factory=session_factory)
    app = FastAPI()
    app.state.session_factory = session_factory

    # Bind (card_oidc_id, "shared-sub") to U2
    ctx_u2 = RLSContext(principal_id=u2_id, workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx_u2) as session:
        intent_u2 = await session.scalar(
            text("SELECT kb_auth.identity_link_intent_create(:p_id, :s_id, :card_id, 300)"),
            {"p_id": u2_id, "s_id": s2_id, "card_id": card_oidc_id},
        )
        await session.commit()

    p2_ctx = PrincipalContext(
        principal_id=u2_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
        session_id=s2_id,
    )
    req_u2 = _make_dummy_request(app, principal=p2_ctx, session_factory=session_factory)
    assertion = ExternalIdentityAssertion(
        card_id=card_oidc_id,
        subject="shared-sub",
        email="shared@example.com",
        email_verified=True,
        display_name="User Two",
        groups=(),
    )
    await resolver.resolve(assertion, req_u2, link_intent_id=intent_u2)

    # Now U1 creates a link intent and tries to bind the exact same (card_oidc_id, "shared-sub")
    ctx_u1 = RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx_u1) as session:
        intent_u1 = await session.scalar(
            text("SELECT kb_auth.identity_link_intent_create(:p_id, :s_id, :card_id, 300)"),
            {"p_id": u1_id, "s_id": s1_id, "card_id": card_oidc_id},
        )
        await session.commit()

    p1_ctx = PrincipalContext(
        principal_id=u1_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
        session_id=s1_id,
    )
    req_u1 = _make_dummy_request(app, principal=p1_ctx, session_factory=session_factory)

    with pytest.raises(ProblemException) as exc_linked:
        await resolver.resolve(assertion, req_u1, link_intent_id=intent_u1)
    assert exc_linked.value.status == 409
    assert exc_linked.value.code == "IDENTITY_ALREADY_LINKED"

    # Verify U2 still retains ownership
    async with session_factory.session(ctx_u2) as session:
        lookup = await session.execute(
            text("SELECT principal_id FROM kb_auth.identity_lookup(:card_id, :sub)"),
            {"card_id": card_oidc_id, "sub": "shared-sub"},
        )
        owner_row = lookup.mappings().first()
        assert owner_row is not None
        assert owner_row["principal_id"] == u2_id


@pytest.mark.asyncio
async def test_case_10_unlink_and_privilege_boundary(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 10: Unlink secondary card succeeds; unlinking sole identity -> 409 LAST_AUTH_METHOD; SELECT * FROM user_identities as kanban_app -> 42501."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, users_and_sessions, card_oidc_id, card_ldap_id = await _create_test_env(
        session_factory, num_users=2
    )
    u1_id, s1_id = users_and_sessions[0]
    _u2_id, _s2_id = users_and_sessions[1]

    link_service = IdentityLinkService()
    p1_ctx = PrincipalContext(
        principal_id=u1_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
        session_id=s1_id,
        aal2_verified_at=datetime.now(UTC),
    )

    ctx = RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)

    # 1. Bind two identities to U1
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()
    async with session_factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text(
                "INSERT INTO user_identities ("
                "  id, workspace_id, principal_id, auth_card_id, immutable_subject_id, subject_email_at_link"
                ") VALUES ("
                "  :id1, :ws_id, :p_id, :card1, 'sub1', 'u1@card1.example'), ("
                "  :id2, :ws_id, :p_id, :card2, 'sub2', 'u1@card2.example')"
            ),
            {
                "id1": id1,
                "id2": id2,
                "ws_id": ws_id,
                "p_id": u1_id,
                "card1": card_oidc_id,
                "card2": card_ldap_id,
            },
        )
        await session.commit()

    # 2. Unlinking one secondary identity succeeds
    async with session_factory.session(ctx) as session:
        await link_service.unlink_identity(session, p1_ctx, id1)

    # Verify 1 remains
    async with session_factory.session(ctx) as session:
        remaining = await link_service.list_identities(session, u1_id)
        assert len(remaining) == 1
        assert remaining[0]["id"] == str(id2)

        # Check activity recorded
        act_res = await session.execute(
            text(
                "SELECT event_type FROM activity_records "
                "WHERE workspace_id = :ws_id AND actor_id = :p_id "
                "ORDER BY recorded_at DESC LIMIT 1"
            ),
            {"ws_id": ws_id, "p_id": u1_id},
        )
        act_row = act_res.mappings().first()
        assert act_row is not None
        assert act_row["event_type"] == ActivityEventType.IDENTITY_UNLINKED.value

    # 3. Unlinking sole remaining identity without local admin credentials fails -> 409 LAST_AUTH_METHOD
    async with session_factory.session(ctx) as session:
        with pytest.raises(ProblemException) as exc_last:
            await link_service.unlink_identity(session, p1_ctx, id2)
        assert exc_last.value.status == 409
        assert exc_last.value.code == "LAST_AUTH_METHOD"

    # 4. If user adds local_admin_credentials, unlinking sole identity succeeds
    async with session_factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text(
                "INSERT INTO local_admin_credentials ("
                "  principal_id, username, password_hash, pepper_kid"
                ") VALUES ("
                "  :p_id, :username, '$argon2id$v=19$m=65536,t=3,p=4$dummyhash$dummyhash', 'pepper-v1'"
                ")"
            ),
            {"p_id": u1_id, "username": f"admin-{uuid.uuid4().hex[:6]}"},
        )
        await session.commit()

    # Now unlinking id2 succeeds
    async with session_factory.session(ctx) as session:
        await link_service.unlink_identity(session, p1_ctx, id2)
        remaining_now = await link_service.list_identities(session, u1_id)
        assert len(remaining_now) == 0

    # 5. Raw privilege boundary check: SELECT * FROM user_identities as kanban_app -> 42501
    async with session_factory.session(ctx) as session:
        # Re-ensure session authorization is kanban_app
        await session.execute(text("SET SESSION AUTHORIZATION kanban_app"))
        with pytest.raises(Exception) as exc_priv:
            await session.execute(text("SELECT * FROM user_identities LIMIT 1"))
        err_msg = str(exc_priv.value)
        assert "permission denied for table user_identities" in err_msg or "42501" in err_msg

    # Same for identity_link_intents
    async with session_factory.session(ctx) as session:
        await session.execute(text("SET SESSION AUTHORIZATION kanban_app"))
        with pytest.raises(Exception) as exc_priv2:
            await session.execute(text("SELECT * FROM identity_link_intents LIMIT 1"))
        err_msg2 = str(exc_priv2.value)
        assert (
            "permission denied for table identity_link_intents" in err_msg2 or "42501" in err_msg2
        )


@pytest.mark.asyncio
async def test_api_endpoints_and_contract_samples(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test HTTP API endpoints and generate contract response samples for docs/qa/KANBA-98/."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, users_and_sessions, card_oidc_id, card_ldap_id = await _create_test_env(
        session_factory, num_users=2
    )
    u1_id, s1_id = users_and_sessions[0]
    _u2_id, _s2_id = users_and_sessions[1]

    app = FastAPI()
    app.state.session_factory = session_factory
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.include_router(auth_identities_router, prefix="/api/v1")

    # Get card slugs
    ctx = RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx) as session:
        await session.scalar(
            text("SELECT slug FROM auth_provider_cards WHERE id = :id"), {"id": card_oidc_id}
        )
        ldap_slug = await session.scalar(
            text("SELECT slug FROM auth_provider_cards WHERE id = :id"), {"id": card_ldap_id}
        )

    current_principal: PrincipalContext | None = None

    async def get_test_principal() -> PrincipalContext:
        assert current_principal is not None
        return current_principal

    app.dependency_overrides[get_principal] = get_test_principal

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Sample 1: 403 AAL2_REQUIRED on link start
        current_principal = PrincipalContext(
            principal_id=u1_id,
            workspace_id=ws_id,
            token_scopes=("session",),
            aal_level=1,
            session_id=s1_id,
            aal2_verified_at=None,
        )
        resp_aal2_req = await client.post(
            "/api/v1/auth/identities/link/start",
            json={"card_slug": ldap_slug},
        )
        assert resp_aal2_req.status_code == 403
        sample_aal2_required = resp_aal2_req.json()

        # Switch to fresh AAL2
        current_principal = PrincipalContext(
            principal_id=u1_id,
            workspace_id=ws_id,
            token_scopes=("session",),
            aal_level=2,
            session_id=s1_id,
            aal2_verified_at=datetime.now(UTC),
        )

        # Sample 2: 200 POST /api/v1/auth/identities/link/start (LDAP mode)
        resp_link_start = await client.post(
            "/api/v1/auth/identities/link/start",
            json={"card_slug": ldap_slug},
        )
        assert resp_link_start.status_code == 200
        sample_link_start = resp_link_start.json()
        assert sample_link_start["mode"] == "ldap_credentials"
        uuid.UUID(sample_link_start["link_intent_id"])

        # Insert one bound identity so GET /identities has data
        ident_id = uuid.uuid4()
        async with session_factory.session(ctx) as session:
            await session.execute(text("RESET SESSION AUTHORIZATION"))
            await session.execute(
                text(
                    "INSERT INTO user_identities ("
                    "  id, workspace_id, principal_id, auth_card_id, immutable_subject_id, subject_email_at_link"
                    ") VALUES ("
                    "  :id, :ws_id, :p_id, :card_id, 'gh-u1', 'u1@github.example')"
                ),
                {"id": ident_id, "ws_id": ws_id, "p_id": u1_id, "card_id": card_oidc_id},
            )
            await session.commit()

        # Sample 3: 200 GET /api/v1/auth/identities
        resp_list = await client.get("/api/v1/auth/identities")
        assert resp_list.status_code == 200
        sample_list_identities = resp_list.json()
        assert len(sample_list_identities["identities"]) == 1

        # Sample 4: 409 LAST_AUTH_METHOD on DELETE sole identity
        resp_unlink = await client.delete(f"/api/v1/auth/identities/{ident_id}")
        assert resp_unlink.status_code == 409
        sample_last_auth_method = resp_unlink.json()
        assert sample_last_auth_method["code"] == "LAST_AUTH_METHOD"

        # Sample 5: 409 IDENTITY_LINK_REQUIRED from DatabaseIdentityResolver
        resolver = DatabaseIdentityResolver(session_factory=session_factory)
        req_dummy = _make_dummy_request(
            app, principal=current_principal, session_factory=session_factory
        )

        # Existing user email lookup
        async with session_factory.session(ctx) as session:
            u_email = await session.scalar(
                text("SELECT email FROM users WHERE id = :id"), {"id": u1_id}
            )

        assertion_prehijack = ExternalIdentityAssertion(
            card_id=card_oidc_id,
            subject="different-sub-prehijack",
            email=u_email,
            email_verified=True,
            display_name="Prehijack Victim",
            groups=(),
        )
        sample_identity_link_required: dict[str, Any] = {}
        try:
            await resolver.resolve(assertion_prehijack, req_dummy, link_intent_id=None)
        except ProblemException as exc:
            assert exc.status == 409
            assert exc.code == "IDENTITY_LINK_REQUIRED"
            sample_identity_link_required = {
                "type": "about:blank",
                "title": exc.title,
                "status": exc.status,
                "detail": exc.detail,
                "code": exc.code,
            }

        # Save contract samples to docs/qa/KANBA-98/contract-sample.json
        contract_bundle = {
            "409_IDENTITY_LINK_REQUIRED": sample_identity_link_required,
            "403_AAL2_REQUIRED": sample_aal2_required,
            "200_POST_identities_link_start": sample_link_start,
            "200_GET_api_v1_auth_identities": sample_list_identities,
            "409_LAST_AUTH_METHOD": sample_last_auth_method,
        }
        out_path = pathlib.Path("/tmp/kb-wt-KANBA-98/docs/qa/KANBA-98/contract-sample.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(contract_bundle, f, indent=2)


@pytest.mark.asyncio
async def test_api_endpoints_full_coverage(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test API endpoint routes edge cases: OIDC cookie header, link LDAP, and successful unlink."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, users_and_sessions, card_oidc_id, card_ldap_id = await _create_test_env(
        session_factory, num_users=2
    )
    u1_id, s1_id = users_and_sessions[0]
    _u2_id, _s2_id = users_and_sessions[1]

    app = FastAPI()
    app.state.session_factory = session_factory
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.include_router(auth_identities_router, prefix="/api/v1")

    # Get card slugs
    ctx = RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx) as session:
        oidc_slug = await session.scalar(
            text("SELECT slug FROM auth_provider_cards WHERE id = :id"), {"id": card_oidc_id}
        )
        ldap_slug = await session.scalar(
            text("SELECT slug FROM auth_provider_cards WHERE id = :id"), {"id": card_ldap_id}
        )

    current_principal = PrincipalContext(
        principal_id=u1_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
        session_id=s1_id,
        aal2_verified_at=datetime.now(UTC),
    )

    async def get_test_principal() -> PrincipalContext:
        return current_principal

    app.dependency_overrides[get_principal] = get_test_principal

    # Mock OIDC flow with cookie header
    mock_oidc = AsyncMock()
    mock_oidc.start = AsyncMock(
        return_value=type(
            "StartResp",
            (),
            {
                "authorize_url": "https://auth.example.com/oauth/authorize?state=abc",
                "cookie_header": "__Host-kb_oidc=secretstate; Path=/; Secure; HttpOnly; SameSite=Lax",
            },
        )()
    )
    app.state.oidc_flow = mock_oidc

    # Mock LDAP service
    mock_ldap = AsyncMock()
    mock_ldap.authenticate_user = AsyncMock(return_value=None)
    app.state.ldap_service = mock_ldap

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. POST /link/start for OIDC: verify redirect mode and set-cookie header
        resp_oidc = await client.post(
            "/api/v1/auth/identities/link/start",
            json={"card_slug": oidc_slug},
        )
        assert resp_oidc.status_code == 200
        assert resp_oidc.json()["mode"] == "redirect"
        assert "__Host-kb_oidc" in resp_oidc.headers.get("set-cookie", "")

        # 1b. POST /link/start for OIDC without cookie_header
        mock_oidc.start.return_value.cookie_header = None
        resp_oidc_nocookie = await client.post(
            "/api/v1/auth/identities/link/start",
            json={"card_slug": oidc_slug},
        )
        assert resp_oidc_nocookie.status_code == 200
        assert resp_oidc_nocookie.json()["mode"] == "redirect"

        # 2. POST /link/start for LDAP to get a valid intent
        resp_ldap_start = await client.post(
            "/api/v1/auth/identities/link/start",
            json={"card_slug": ldap_slug},
        )
        assert resp_ldap_start.status_code == 200
        intent_id_str = resp_ldap_start.json()["link_intent_id"]

        # 3. POST /link/ldap to complete LDAP link
        resp_ldap_link = await client.post(
            "/api/v1/auth/identities/link/ldap",
            json={
                "link_intent_id": intent_id_str,
                "username": "ldapuser",
                "password": "ldappassword",
            },
        )
        assert resp_ldap_link.status_code == 200
        assert resp_ldap_link.json()["status"] == "ok"

        # 4. Insert 2 identities and test DELETE /identities/{id} success
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        async with session_factory.session(ctx) as session:
            await session.execute(text("RESET SESSION AUTHORIZATION"))
            await session.execute(
                text(
                    "INSERT INTO user_identities ("
                    "  id, workspace_id, principal_id, auth_card_id, immutable_subject_id, subject_email_at_link"
                    ") VALUES ("
                    "  :id1, :ws_id, :p_id, :card1, 'sub-api-1', 'u1@card1.example'), ("
                    "  :id2, :ws_id, :p_id, :card2, 'sub-api-2', 'u1@card2.example')"
                ),
                {
                    "id1": id1,
                    "id2": id2,
                    "ws_id": ws_id,
                    "p_id": u1_id,
                    "card1": card_oidc_id,
                    "card2": card_ldap_id,
                },
            )
            await session.commit()

        resp_del = await client.delete(f"/api/v1/auth/identities/{id1}")
        assert resp_del.status_code == 200
        assert resp_del.json()["unlinked"] is True

    # 5. Missing session_factory error branch
    app_no_factory = FastAPI()
    app_no_factory.include_router(auth_identities_router, prefix="/api/v1")
    app_no_factory.dependency_overrides[get_principal] = get_test_principal
    transport_no_fac = httpx.ASGITransport(app=app_no_factory)
    async with httpx.AsyncClient(transport=transport_no_fac, base_url="http://test") as client:
        with pytest.raises(RuntimeError, match="Session factory is not configured"):
            await client.get("/api/v1/auth/identities")

        with pytest.raises(RuntimeError, match="Session factory is not configured"):
            await client.post("/api/v1/auth/identities/link/start", json={"card_slug": oidc_slug})

        with pytest.raises(RuntimeError, match="Session factory is not configured"):
            await client.post(
                "/api/v1/auth/identities/link/ldap",
                json={"link_intent_id": intent_id_str, "username": "u", "password": "p"},
            )

        with pytest.raises(RuntimeError, match="Session factory is not configured"):
            await client.delete(f"/api/v1/auth/identities/{id2}")


@pytest.mark.asyncio
async def test_identity_service_internal_methods(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test internal helper branches of DatabaseIdentityResolver and IdentityLinkService."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, users_and_sessions, card_oidc_id, card_ldap_id = await _create_test_env(
        session_factory, num_users=2
    )
    u1_id, s1_id = users_and_sessions[0]
    u2_id, s2_id = users_and_sessions[1]

    # 1. _get_session_factory branches
    resolver_no_fac = DatabaseIdentityResolver(session_factory=None)
    dummy_req = _make_dummy_request()
    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        resolver_no_fac._get_session_factory(dummy_req)

    app_with_fac = FastAPI()
    app_with_fac.state.session_factory = session_factory
    req_with_app = _make_dummy_request(app_with_fac)
    assert resolver_no_fac._get_session_factory(req_with_app) is session_factory

    # 2. _open_session branches
    # Branch: sessionmaker attribute
    class DummyMakerHolder:
        sessionmaker = session_factory.sessionmaker

    resolver_maker = DatabaseIdentityResolver(session_factory=cast("Any", DummyMakerHolder()))
    async with resolver_maker._open_session(req_with_app) as sess:
        assert sess is not None

    # Branch: callable returning async context manager
    resolver_callable = DatabaseIdentityResolver(
        session_factory=cast("Any", lambda: session_factory.session(RLSContext(u1_id, ws_id)))
    )
    async with resolver_callable._open_session(req_with_app) as sess:
        assert sess is not None

    # Branch: callable returning direct object
    resolver_direct = DatabaseIdentityResolver(session_factory=cast("Any", lambda: "dummy_session"))
    async with resolver_direct._open_session(req_with_app) as sess:
        assert str(sess) == "dummy_session"

    # Branch: invalid type
    resolver_invalid = DatabaseIdentityResolver(session_factory=cast("Any", "not_a_factory"))
    with pytest.raises(
        TypeError, match="Configured session_factory must have sessionmaker or be callable"
    ):
        async with resolver_invalid._open_session(req_with_app):
            pass

    # 3. _resolve_link branches: principal resolver fallback, principal None, session_id None
    resolver = DatabaseIdentityResolver(session_factory=session_factory)
    assertion = ExternalIdentityAssertion(
        card_id=card_oidc_id,
        subject="test-sub-fallback",
        email="test@example.com",
        email_verified=True,
        display_name="Fallback",
        groups=(),
    )
    dummy_intent = uuid.uuid4()

    # Principal is None
    req_no_principal = _make_dummy_request(app_with_fac)
    with pytest.raises(ProblemException) as exc_no_p:
        await resolver.resolve(assertion, req_no_principal, link_intent_id=dummy_intent)
    assert exc_no_p.value.status == 400
    assert exc_no_p.value.code == "LINK_INTENT_INVALID"

    # Principal resolver returns None
    mock_presolver = AsyncMock()
    mock_presolver.resolve = AsyncMock(return_value=None)
    app_with_fac.state.principal_resolver = mock_presolver
    with pytest.raises(ProblemException) as exc_no_p2:
        await resolver.resolve(assertion, req_no_principal, link_intent_id=dummy_intent)
    assert exc_no_p2.value.status == 400

    # Principal has no session_id
    mock_presolver.resolve = AsyncMock(
        return_value=PrincipalContext(
            principal_id=u1_id,
            workspace_id=ws_id,
            token_scopes=("session",),
            aal_level=2,
            session_id=None,
        )
    )
    with pytest.raises(ProblemException) as exc_no_sid:
        await resolver.resolve(assertion, req_no_principal, link_intent_id=dummy_intent)
    assert exc_no_sid.value.status == 400

    # 4. _resolve_login branches: disabled card
    disabled_card_id = uuid.uuid4()
    ctx = RLSContext(principal_id=u1_id, workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text(
                "INSERT INTO auth_provider_cards ("
                "  id, workspace_id, provider_kind, slug, display_name, is_enabled, sort_rank"
                ") VALUES ("
                "  :id, :ws_id, 'OIDC', :slug, 'Disabled Card', false, '0|h00099:'"
                ")"
            ),
            {"id": disabled_card_id, "ws_id": ws_id, "slug": f"disabled-{uuid.uuid4().hex[:6]}"},
        )
        await session.commit()

    assertion_disabled = ExternalIdentityAssertion(
        card_id=disabled_card_id,
        subject="sub-disabled",
        email="disabled@example.com",
        email_verified=True,
        display_name="Disabled",
        groups=(),
    )
    with pytest.raises(ProblemException) as exc_dis:
        await resolver.resolve(assertion_disabled, req_with_app, link_intent_id=None)
    assert exc_dis.value.status == 403
    assert exc_dis.value.code == "IDENTITY_NOT_PROVISIONED"

    # Card with workspace_id IS NULL falling back to default workspace
    null_ws_card_id = uuid.uuid4()
    async with session_factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text(
                "INSERT INTO auth_provider_cards ("
                "  id, workspace_id, provider_kind, slug, display_name, is_enabled, sort_rank, auto_provision_users"
                ") VALUES ("
                "  :id, NULL, 'OIDC', :slug, 'Null WS Card', true, '0|h00098:', true"
                ")"
            ),
            {"id": null_ws_card_id, "slug": f"nullws-{uuid.uuid4().hex[:6]}"},
        )
        await session.commit()

    assertion_null_ws = ExternalIdentityAssertion(
        card_id=null_ws_card_id,
        subject="sub-null-ws",
        email=f"nullws-{uuid.uuid4().hex[:6]}@example.com",
        email_verified=True,
        display_name="Null WS User",
        groups=(),
    )
    resolved_null_ws = await resolver.resolve(assertion_null_ws, req_with_app, link_intent_id=None)
    assert resolved_null_ws.principal_id is not None
    assert resolved_null_ws.workspace_id is not None

    # 5. start_link branches: card not found, invalid provider kind, missing oidc_flow
    link_service = IdentityLinkService()
    p_ctx = PrincipalContext(
        principal_id=u1_id,
        workspace_id=ws_id,
        token_scopes=("session",),
        aal_level=2,
        session_id=s1_id,
        aal2_verified_at=datetime.now(UTC),
    )
    async with session_factory.session(ctx) as session:
        # Card not found
        with pytest.raises(ProblemException) as exc_cnf:
            await link_service.start_link(session, p_ctx, "nonexistent-card-slug", req_with_app)
        assert exc_cnf.value.status == 404
        assert exc_cnf.value.code == "CARD_NOT_FOUND"

        # Invalid provider kind (LOCAL_ADMIN)
        local_card_id = uuid.uuid4()
        local_slug = f"local-{uuid.uuid4().hex[:6]}"
        async with session_factory.session(ctx) as session:
            await session.execute(text("RESET SESSION AUTHORIZATION"))
            await session.execute(
                text(
                    "INSERT INTO auth_provider_cards ("
                    "  id, workspace_id, provider_kind, slug, display_name, is_enabled, sort_rank"
                    ") VALUES ("
                    "  :id, :ws_id, 'LOCAL_ADMIN', :slug, 'Local Card', true, '0|h00097:'"
                    ")"
                ),
                {"id": local_card_id, "ws_id": ws_id, "slug": local_slug},
            )
            await session.commit()

        async with session_factory.session(ctx) as session:
            with pytest.raises(ProblemException) as exc_inv_k:
                await link_service.start_link(session, p_ctx, local_slug, req_with_app)
            assert exc_inv_k.value.status == 400
            assert exc_inv_k.value.code == "INVALID_PROVIDER_KIND"

        # Missing oidc_flow on app.state
        async with session_factory.session(ctx) as session:
            oidc_slug = await session.scalar(
                text("SELECT slug FROM auth_provider_cards WHERE id = :id"), {"id": card_oidc_id}
            )
            app_no_oidc = FastAPI()
            app_no_oidc.state.session_factory = session_factory
            req_no_oidc = _make_dummy_request(app_no_oidc)
            with pytest.raises(RuntimeError, match="OIDC flow is not configured"):
                await link_service.start_link(session, p_ctx, oidc_slug, req_no_oidc)

    # 6. link_ldap branches: missing intent, mismatched principal/session, card not found/disabled/not LDAP, missing ldap_service
    async with session_factory.session(ctx) as session:
        # Intent not found
        with pytest.raises(ProblemException) as exc_lint_nf:
            await link_service.link_ldap(
                session, p_ctx, uuid.uuid4(), username="u", password="p", request=req_with_app
            )
        assert exc_lint_nf.value.status == 400
        assert exc_lint_nf.value.code == "LINK_INTENT_INVALID"

        # Intent with mismatched principal
        other_intent_id = await session.scalar(
            text("SELECT kb_auth.identity_link_intent_create(:p_id, :s_id, :card_id, 300)"),
            {"p_id": u2_id, "s_id": s2_id, "card_id": card_ldap_id},
        )
        with pytest.raises(ProblemException) as exc_lint_mismatch:
            await link_service.link_ldap(
                session, p_ctx, other_intent_id, username="u", password="p", request=req_with_app
            )
        assert exc_lint_mismatch.value.status == 400
        assert exc_lint_mismatch.value.code == "LINK_INTENT_INVALID"

        # Intent pointing to OIDC card (not LDAP)
        non_ldap_intent = await session.scalar(
            text("SELECT kb_auth.identity_link_intent_create(:p_id, :s_id, :card_id, 300)"),
            {"p_id": u1_id, "s_id": s1_id, "card_id": card_oidc_id},
        )
        with pytest.raises(ProblemException) as exc_not_ldap:
            await link_service.link_ldap(
                session, p_ctx, non_ldap_intent, username="u", password="p", request=req_with_app
            )
        assert exc_not_ldap.value.status == 404
        assert exc_not_ldap.value.code == "CARD_NOT_FOUND"

        # Valid LDAP intent but missing ldap_service on app.state
        ldap_intent = await session.scalar(
            text("SELECT kb_auth.identity_link_intent_create(:p_id, :s_id, :card_id, 300)"),
            {"p_id": u1_id, "s_id": s1_id, "card_id": card_ldap_id},
        )
        app_no_ldap = FastAPI()
        app_no_ldap.state.session_factory = session_factory
        req_no_ldap = _make_dummy_request(app_no_ldap)
        with pytest.raises(RuntimeError, match="LDAP service is not configured"):
            await link_service.link_ldap(
                session, p_ctx, ldap_intent, username="u", password="p", request=req_no_ldap
            )

    # 7. unlink_identity branch: identity not found (404)
    async with session_factory.session(ctx) as session:
        with pytest.raises(ProblemException) as exc_unl_nf:
            await link_service.unlink_identity(session, p_ctx, uuid.uuid4())
        assert exc_unl_nf.value.status == 404
        assert exc_unl_nf.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_identity_service_error_handling_and_unexpected_exceptions() -> None:
    """Test unexpected exceptions, activity ledger error logging, and prov_row is None."""
    link_service = IdentityLinkService()
    p_ctx = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("session",),
        aal_level=2,
        session_id=uuid.uuid4(),
        aal2_verified_at=datetime.now(UTC),
    )

    # 1. unlink_identity unexpected database exception
    mock_sess = AsyncMock()
    mock_sess.execute = AsyncMock(side_effect=RuntimeError("unexpected sql failure"))
    with pytest.raises(RuntimeError, match="unexpected sql failure"):
        await link_service.unlink_identity(mock_sess, p_ctx, uuid.uuid4())

    # 2. unlink_identity activity logging failure branch
    mock_sess_ok = AsyncMock()
    mock_sess_ok.execute = AsyncMock(return_value=None)
    mock_sess_ok.commit = AsyncMock(return_value=None)
    from unittest.mock import patch

    with patch(
        "kanban.auth.identity_service.record_activity", side_effect=Exception("ledger error")
    ):
        # Should not raise exception even if ledger fails
        await link_service.unlink_identity(mock_sess_ok, p_ctx, uuid.uuid4())

    # 3. _resolve_link unexpected database error
    app = FastAPI()
    resolver = DatabaseIdentityResolver()
    req = _make_dummy_request(app, principal=p_ctx)
    assertion = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="sub-err",
        email="err@example.com",
        email_verified=True,
        display_name="Err",
        groups=(),
    )

    class FailingSessionContext:
        async def __aenter__(self) -> Any:
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(side_effect=RuntimeError("unexpected link db failure"))
            return mock_db

        async def __aexit__(self, *args: object) -> None:
            pass

    resolver._open_session = lambda *args, **kwargs: FailingSessionContext()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="unexpected link db failure"):
        await resolver.resolve(assertion, req, link_intent_id=uuid.uuid4())

    # 4. _resolve_link activity logging failure
    class OkSessionContext:
        async def __aenter__(self) -> Any:
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(return_value=None)
            mock_db.commit = AsyncMock(return_value=None)
            return mock_db

        async def __aexit__(self, *args: object) -> None:
            pass

    resolver._open_session = lambda *args, **kwargs: OkSessionContext()  # type: ignore[assignment]
    with patch(
        "kanban.auth.identity_service.record_activity", side_effect=Exception("ledger error")
    ):
        resolved = await resolver.resolve(assertion, req, link_intent_id=uuid.uuid4())
        assert resolved.principal_id == p_ctx.principal_id

    # 5. prov_row is None in _resolve_login
    class ProvNoneSessionContext:
        def __init__(self) -> None:
            self.step = 0

        async def __aenter__(self) -> Any:
            mock_db = AsyncMock()

            async def mock_exec(stmt: Any, params: Any = None) -> Any:
                sql_str = str(stmt)
                if "identity_lookup" in sql_str:
                    res = AsyncMock()
                    res.mappings = lambda: AsyncMock(first=lambda: None)
                    return res
                if "card_get_by_id" in sql_str:
                    res = AsyncMock()
                    res.mappings = lambda: AsyncMock(
                        first=lambda: {
                            "id": uuid.uuid4(),
                            "workspace_id": uuid.uuid4(),
                            "is_enabled": True,
                            "auto_provision_users": True,
                            "allowed_email_domains": [],
                        }
                    )
                    return res
                if "lower(email)" in sql_str:
                    res = AsyncMock()
                    res.scalar = lambda: None
                    return res
                if "identity_provision_new_user" in sql_str:
                    res = AsyncMock()
                    res.mappings = lambda: AsyncMock(first=lambda: None)
                    return res
                return AsyncMock()

            mock_db.execute = mock_exec
            return mock_db

        async def __aexit__(self, *args: object) -> None:
            pass

    resolver_prov_none = DatabaseIdentityResolver()
    resolver_prov_none._open_session = lambda *args, **kwargs: ProvNoneSessionContext()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="Failed to provision new user identity"):
        await resolver_prov_none.resolve(assertion, req, link_intent_id=None)
