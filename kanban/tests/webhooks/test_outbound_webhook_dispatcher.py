# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for OutboundWebhookDispatcher (KB-DEVSECOPS-BUS-01)."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import text

from database.models.webhooks import WebhookDelivery, WebhookSubscription
from database.models.workspace_settings import WorkspaceSettings
from database.outbox.broker import OutboxEnvelope, enqueue_outbox_event
from database.outbox.relay import OutboxRelay
from database.session import RLSContext
from kanban.security.envelope import StaticKekProvider, seal_bound
from kanban.webhooks.outbound_dispatcher import OutboundWebhookDispatcher

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _make_kek() -> StaticKekProvider:
    return StaticKekProvider({"kek-v1": b"k" * 32}, current="kek-v1")


async def _enroll_totp(session: AsyncSession, p_id: uuid.UUID) -> None:
    """Enroll and confirm active TOTP factor to satisfy require_admin_aal2."""
    fid = (
        await session.execute(
            text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
            {"p_id": p_id, "blob": b"\x01" + b"\x00" * 28, "dek": b"\x01" + b"\x00" * 44},
        )
    ).scalar_one()
    await session.execute(
        text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
        {"p_fid": fid},
    )
    await session.commit()


async def test_outbound_webhook_dispatch_signed_positive(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """OutboundWebhookDispatcher signs payload and delivers successfully to public target."""
    admin = await make_user("admin_wh", workspace_role="WORKSPACE_ADMIN")
    project_id = await make_project("WH", created_by=admin)

    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    engine = app.state.session_factory.engine
    kek = _make_kek()

    sub_id = uuid.uuid4()
    secret_str = "super-secret-signing-key"
    aad = f"kanban/webhook-sub/v1|{sub_id}|{admin.workspace_id}".encode()
    sealed = seal_bound(secret_str.encode("utf-8"), aad, kek)
    wrapped_len = len(sealed.wrapped_dek).to_bytes(2, "big")
    secret_ct = wrapped_len + sealed.wrapped_dek + sealed.encrypted_secret_blob

    sub = WebhookSubscription(
        id=sub_id,
        workspace_id=admin.workspace_id,
        project_id=project_id,
        target_url="https://hooks.example.com/events",
        events=["issue.*"],
        secret_ciphertext=secret_ct,
        secret_dek_kid=sealed.dek_kid,
        is_active=True,
        created_by=admin.id,
    )
    admin_ctx = RLSContext(principal_id=admin.id, workspace_id=admin.workspace_id)
    async with app.state.session_factory.session(admin_ctx) as session:
        session.add(sub)
        await session.commit()

    captured_requests: list[httpx.Request] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"received": True})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    dispatcher = OutboundWebhookDispatcher(
        engine=engine,
        kek_provider=kek,
        http_client=mock_client,
        dns_resolver=lambda _h: ["93.184.216.34"],  # public IP
    )

    envelope = OutboxEnvelope(
        id=uuid.uuid4(),
        seq=1,
        workspace_id=admin.workspace_id,
        project_id=project_id,
        object_id=uuid.uuid4(),
        topic="issue.created",
        payload={"key": "WH-1", "title": "First issue"},
        created_at=datetime.now(UTC),
    )

    deliveries = await dispatcher.dispatch_envelope(envelope)
    assert len(deliveries) == 1
    d = deliveries[0]
    assert d.status == "delivered"
    assert d.status_code == 200

    assert len(captured_requests) == 1
    req = captured_requests[0]
    sig_header = req.headers.get("X-Kanban-Signature-256")
    assert sig_header is not None
    assert sig_header.startswith("sha256=")
    expected_sig = hmac.new(secret_str.encode("utf-8"), req.content, hashlib.sha256).hexdigest()
    assert sig_header == f"sha256={expected_sig}"
    assert req.headers.get("X-Kanban-Timestamp")
    assert req.headers.get("X-Kanban-Delivery-Id") == str(d.id)


async def test_outbound_webhook_ssrf_and_redirect_blocked(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Outbound dispatcher rejects internal RFC1918/IMDS targets and 300..399 HTTP redirects."""
    admin = await make_user("admin_ssrf_wh", workspace_role="WORKSPACE_ADMIN")
    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    engine = app.state.session_factory.engine
    kek = _make_kek()
    admin_ctx = RLSContext(principal_id=admin.id, workspace_id=admin.workspace_id)

    # 1. Target resolving to private IP
    sub_private = WebhookSubscription(
        id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        target_url="http://internal.service.local/webhook",
        events=["*"],
        is_active=True,
        created_by=admin.id,
    )
    async with app.state.session_factory.session(admin_ctx) as session:
        session.add(sub_private)
        await session.commit()

    dispatcher_private = OutboundWebhookDispatcher(
        engine=engine,
        kek_provider=kek,
        dns_resolver=lambda _h: ["192.168.1.100"],  # RFC 1918 private
    )
    envelope = OutboxEnvelope(
        id=uuid.uuid4(),
        seq=2,
        workspace_id=admin.workspace_id,
        project_id=None,
        object_id=None,
        topic="user.created",
        payload={"user": "attacker"},
        created_at=datetime.now(UTC),
    )
    deliveries = await dispatcher_private.dispatch_envelope(envelope)
    assert len(deliveries) == 1
    assert deliveries[0].status == "failed"
    assert "SSRF_BLOCKED" in (deliveries[0].error_message or "")

    # 2. Target returning redirect (302)
    sub_redir = WebhookSubscription(
        id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        target_url="https://public.service.org/webhook",
        events=["*"],
        is_active=True,
        created_by=admin.id,
    )
    async with app.state.session_factory.session(admin_ctx) as session:
        session.add(sub_redir)
        await session.commit()

    def redir_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(redir_handler))
    dispatcher_redir = OutboundWebhookDispatcher(
        engine=engine,
        kek_provider=kek,
        http_client=mock_client,
        dns_resolver=lambda _h: ["93.184.216.34"],
    )
    deliveries_redir = await dispatcher_redir.dispatch_envelope(envelope)
    assert any(d.subscription_id == sub_redir.id for d in deliveries_redir)
    target_d = next(d for d in deliveries_redir if d.subscription_id == sub_redir.id)
    assert target_d.status == "failed"
    assert "SSRF_REDIRECT_BLOCKED" in (target_d.error_message or "")


async def test_outbound_webhook_air_gap_and_dead_letter_transition(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Outbound dispatcher blocks in air-gap mode and transitions to dead_letter."""
    admin = await make_user("admin_dl", workspace_role="WORKSPACE_ADMIN")
    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    engine = app.state.session_factory.engine
    kek = _make_kek()
    admin_ctx = RLSContext(principal_id=admin.id, workspace_id=admin.workspace_id)

    sub = WebhookSubscription(
        id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        target_url="https://public.target.org/failing",
        events=["*"],
        is_active=True,
        created_by=admin.id,
    )
    async with app.state.session_factory.session(admin_ctx) as session:
        session.add(sub)
        await session.commit()

    envelope = OutboxEnvelope(
        id=uuid.uuid4(),
        seq=3,
        workspace_id=admin.workspace_id,
        project_id=None,
        object_id=None,
        topic="system.alert",
        payload={"level": "warning"},
        created_at=datetime.now(UTC),
    )

    # 1. Air gap mode blocks dispatch
    airgap_dispatcher = OutboundWebhookDispatcher(
        engine=engine,
        kek_provider=kek,
        air_gap_mode=True,
    )
    deliveries_ag = await airgap_dispatcher.dispatch_envelope(envelope)
    assert len(deliveries_ag) == 1
    assert deliveries_ag[0].status == "failed"
    assert deliveries_ag[0].error_message == "AIR_GAP_MODE"

    # 2. 5 consecutive 503 failures transitions to dead_letter
    def fail_503_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    fail_client = httpx.AsyncClient(transport=httpx.MockTransport(fail_503_handler))
    failing_dispatcher = OutboundWebhookDispatcher(
        engine=engine,
        kek_provider=kek,
        http_client=fail_client,
        max_attempts=5,
        dns_resolver=lambda _h: ["93.184.216.34"],
    )

    delivery = WebhookDelivery(
        id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        subscription_id=sub.id,
        event_id=envelope.id,
        event_topic=envelope.topic,
        payload_json=dict(envelope.payload),
        attempt_count=4,  # Next attempt is 5th
        status="failed",
    )
    async with app.state.session_factory.session(admin_ctx) as session:
        session.add(delivery)
        await failing_dispatcher.execute_delivery(session, delivery, sub)
        await session.commit()

    assert delivery.attempt_count == 5
    assert delivery.status == "dead_letter"
    assert delivery.status_code == 503


async def test_admin_webhooks_crud(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Admin webhooks API enforces AAL2 and supports full CRUD lifecycle."""
    admin = await make_user("admin_crud", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("regular_user")

    # 1. Non-admin or non-AAL2 gets 403
    member_client = as_principal(member, aal_level=1)
    resp_403 = await member_client.get("/api/v1/admin/webhooks")
    assert resp_403.status_code == 403

    # Enroll TOTP for admin to satisfy require_admin_aal2
    await _enroll_totp(api_env.seed, admin.id)
    admin_client = as_principal(admin, aal_level=2)
    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    app.state.git_dns_resolver = lambda _h: ["93.184.216.34"]

    # 2. Successful create
    resp_create = await admin_client.post(
        "/api/v1/admin/webhooks",
        json={
            "target_url": "https://hooks.valid.org/events",
            "events": ["issue.*"],
            "secret": "my-custom-secret-key",
            "is_active": True,
        },
    )
    assert resp_create.status_code == 201, resp_create.text
    created = resp_create.json()
    sub_id = created["id"]
    assert created["target_url"] == "https://hooks.valid.org/events"
    assert created["events"] == ["issue.*"]
    assert created["secret"] == "my-custom-secret-key"

    # 3. Get subscription
    resp_get = await admin_client.get(f"/api/v1/admin/webhooks/{sub_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == sub_id
    assert resp_get.json()["secret"] is None  # Secret omitted on GET

    # 4. Patch subscription
    resp_patch = await admin_client.patch(
        f"/api/v1/admin/webhooks/{sub_id}",
        json={"is_active": False},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["is_active"] is False

    # 5. List deliveries
    resp_deliv = await admin_client.get(f"/api/v1/admin/webhooks/{sub_id}/deliveries")
    assert resp_deliv.status_code == 200
    assert isinstance(resp_deliv.json(), list)

    # 6. Delete subscription
    resp_del = await admin_client.delete(f"/api/v1/admin/webhooks/{sub_id}")
    assert resp_del.status_code == 204

    # 7. 404 cases
    missing_id = uuid.uuid4()
    assert (await admin_client.get(f"/api/v1/admin/webhooks/{missing_id}")).status_code == 404
    assert (await admin_client.delete(f"/api/v1/admin/webhooks/{missing_id}")).status_code == 404
    resp_deliv_404 = await admin_client.get(f"/api/v1/admin/webhooks/{missing_id}/deliveries")
    assert resp_deliv_404.status_code == 404
    resp_patch_404 = await admin_client.patch(
        f"/api/v1/admin/webhooks/{missing_id}", json={"is_active": True}
    )
    assert resp_patch_404.status_code == 404


async def test_admin_webhooks_ssrf_and_error_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Admin webhooks API rejects SSRF targets and validates URLs on create/patch."""
    admin = await make_user("admin_ssrf", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)
    admin_client = as_principal(admin, aal_level=2)

    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    app.state.git_dns_resolver = lambda h: ["127.0.0.1"] if "internal" in h else ["93.184.216.34"]

    # 1. SSRF rejection on create
    resp_ssrf = await admin_client.post(
        "/api/v1/admin/webhooks",
        json={
            "target_url": "https://internal.corp/hook",
            "events": ["issue.created"],
        },
    )
    assert resp_ssrf.status_code == 400
    assert resp_ssrf.json()["code"] == "SSRF_TARGET_BLOCKED"

    # 2. Invalid URL format on create
    resp_bad_url = await admin_client.post(
        "/api/v1/admin/webhooks",
        json={"target_url": "ftp://bad.scheme/hook", "events": ["*"]},
    )
    assert resp_bad_url.status_code == 400

    # 3. Create valid subscription to test patch validation
    resp_sub2 = await admin_client.post(
        "/api/v1/admin/webhooks",
        json={"target_url": "https://hooks2.valid.org/events", "events": ["*"]},
    )
    assert resp_sub2.status_code == 201
    sub2_id = resp_sub2.json()["id"]

    resp_patch_bad = await admin_client.patch(
        f"/api/v1/admin/webhooks/{sub2_id}",
        json={"target_url": "not-a-url"},
    )
    assert resp_patch_bad.status_code == 400

    resp_patch_ssrf = await admin_client.patch(
        f"/api/v1/admin/webhooks/{sub2_id}",
        json={"target_url": "https://internal.bad/hook"},
    )
    assert resp_patch_ssrf.status_code == 400

    resp_patch_ok = await admin_client.patch(
        f"/api/v1/admin/webhooks/{sub2_id}",
        json={
            "target_url": "https://hooks3.valid.org/events",
            "events": ["project.*"],
            "secret": "new-patch-secret",
        },
    )
    assert resp_patch_ok.status_code == 200
    assert resp_patch_ok.json()["target_url"] == "https://hooks3.valid.org/events"
    assert resp_patch_ok.json()["events"] == ["project.*"]

    # 10. List subscriptions
    resp_list = await admin_client.get("/api/v1/admin/webhooks")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) >= 1

    resp_list_proj = await admin_client.get(f"/api/v1/admin/webhooks?project_id={uuid.uuid4()}")
    assert resp_list_proj.status_code == 200
    assert resp_list_proj.json() == []

    # 11. Air-gap mode restriction on admin API
    admin_ctx = RLSContext(principal_id=admin.id, workspace_id=admin.workspace_id)
    async with app.state.session_factory.session(admin_ctx) as s:
        ws_settings = await s.get(WorkspaceSettings, admin.workspace_id)
        if ws_settings:
            ws_settings.air_gap_mode = True
        else:
            s.add(WorkspaceSettings(workspace_id=admin.workspace_id, air_gap_mode=True))
        await s.commit()

    resp_ag = await admin_client.post(
        "/api/v1/admin/webhooks",
        json={"target_url": "https://hooks4.valid.org/events", "events": ["*"]},
    )
    assert resp_ag.status_code == 400
    assert resp_ag.json()["code"] == "AIR_GAP_RESTRICTION"

    # Reset air_gap_mode
    async with app.state.session_factory.session(admin_ctx) as s:
        ws_settings = await s.get(WorkspaceSettings, admin.workspace_id)
        if ws_settings:
            ws_settings.air_gap_mode = False
            await s.commit()


def test_outbound_webhook_dispatcher_topic_matching() -> None:
    """Verify _matches_topic wildcard and exact matching rules."""
    engine = MagicMock()
    kek = _make_kek()
    dispatcher = OutboundWebhookDispatcher(engine=engine, kek_provider=kek)

    assert dispatcher._matches_topic(["*"], "issue.created") is True  # noqa: SLF001
    assert dispatcher._matches_topic(["*"], "anything") is True  # noqa: SLF001
    assert dispatcher._matches_topic(["issue.*"], "issue.created") is True  # noqa: SLF001
    assert dispatcher._matches_topic(["issue.*"], "issue.deleted") is True  # noqa: SLF001
    assert dispatcher._matches_topic(["issue.*"], "project.created") is False  # noqa: SLF001
    assert dispatcher._matches_topic(["issue.created"], "issue.created") is True  # noqa: SLF001
    assert dispatcher._matches_topic(["issue.created"], "issue.updated") is False  # noqa: SLF001
    assert dispatcher._matches_topic([], "issue.created") is False  # noqa: SLF001


@pytest.mark.asyncio
async def test_outbound_webhook_dispatcher_invalid_target_and_network_error() -> None:
    """Verify execute_delivery handles invalid target schemes and network transport errors."""
    engine = MagicMock()
    kek = _make_kek()
    sub_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    # 1. Invalid target URL scheme
    bad_sub = WebhookSubscription(
        id=sub_id,
        workspace_id=ws_id,
        target_url="file:///etc/passwd",
        events=["*"],
        is_active=True,
    )
    delivery = WebhookDelivery(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        subscription_id=sub_id,
        event_topic="test",
        payload_json={},
        attempt_count=0,
    )
    dispatcher = OutboundWebhookDispatcher(engine=engine, kek_provider=kek, max_attempts=1)
    mock_session = AsyncMock()
    await dispatcher.execute_delivery(mock_session, delivery, bad_sub)
    assert delivery.status == "dead_letter"
    assert "Invalid target URL" in (delivery.error_message or "")

    # 2. Network connection failure
    def conn_fail_handler(_req: httpx.Request) -> httpx.Response:
        err_msg = "Network unreachable"
        raise httpx.ConnectError(err_msg)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(conn_fail_handler))
    net_dispatcher = OutboundWebhookDispatcher(
        engine=engine,
        kek_provider=kek,
        http_client=mock_client,
        max_attempts=1,
        dns_resolver=lambda _h: ["93.184.216.34"],
    )
    valid_sub = WebhookSubscription(
        id=sub_id,
        workspace_id=ws_id,
        target_url="https://valid.target.org/webhook",
        events=["*"],
        is_active=True,
    )
    delivery_net = WebhookDelivery(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        subscription_id=sub_id,
        event_topic="test",
        payload_json={},
        attempt_count=0,
    )
    await net_dispatcher.execute_delivery(mock_session, delivery_net, valid_sub)
    assert delivery_net.status == "dead_letter"
    assert "Network unreachable" in (delivery_net.error_message or "")

    # 3. DNS resolution failure
    dns_fail_dispatcher = OutboundWebhookDispatcher(
        engine=engine,
        kek_provider=kek,
        max_attempts=1,
        dns_resolver=lambda _h: (_ for _ in ()).throw(RuntimeError("DNS dead")),
    )
    delivery_dns = WebhookDelivery(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        subscription_id=sub_id,
        event_topic="test",
        payload_json={},
        attempt_count=0,
    )
    await dns_fail_dispatcher.execute_delivery(mock_session, delivery_dns, valid_sub)
    assert delivery_dns.status == "dead_letter"
    assert "DNS resolution failed" in (delivery_dns.error_message or "")

    # 4. Dispatch error / unexpected exception
    def crash_handler(_req: httpx.Request) -> httpx.Response:
        crash_msg = "Unexpected crash"
        raise ValueError(crash_msg)

    crash_client = httpx.AsyncClient(transport=httpx.MockTransport(crash_handler))
    crash_dispatcher = OutboundWebhookDispatcher(
        engine=engine,
        kek_provider=kek,
        http_client=crash_client,
        max_attempts=1,
        dns_resolver=lambda _h: ["93.184.216.34"],
    )
    delivery_crash = WebhookDelivery(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        subscription_id=sub_id,
        event_topic="test",
        payload_json={},
        attempt_count=0,
    )
    await crash_dispatcher.execute_delivery(mock_session, delivery_crash, valid_sub)
    assert delivery_crash.status == "dead_letter"
    assert "DISPATCH_ERROR" in (delivery_crash.error_message or "")

    # 5. Direct __call__ delegation
    envelope = OutboxEnvelope(
        id=uuid.uuid4(),
        seq=10,
        workspace_id=ws_id,
        project_id=None,
        object_id=None,
        topic="test",
        payload={},
        created_at=datetime.now(UTC),
    )
    with patch.object(net_dispatcher, "dispatch_envelope", new_callable=AsyncMock) as mock_dispatch:
        await net_dispatcher(envelope)
        mock_dispatch.assert_awaited_once_with(envelope)

    # 6. Unseal short secret returns empty
    sub_short = WebhookSubscription(
        id=sub_id,
        workspace_id=ws_id,
        target_url="https://valid.target.org",
        secret_ciphertext=b"x",
        secret_dek_kid="kid",  # noqa: S106
    )
    assert net_dispatcher._unseal_secret(sub_short) == b""  # noqa: SLF001

    # 7. Intermediate failure when attempt_count < max_attempts
    retry_dispatcher = OutboundWebhookDispatcher(
        engine=engine,
        kek_provider=kek,
        http_client=crash_client,
        max_attempts=5,
        dns_resolver=lambda _h: ["93.184.216.34"],
    )
    delivery_retry = WebhookDelivery(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        subscription_id=sub_id,
        event_topic="test",
        payload_json={},
        attempt_count=0,
    )
    await retry_dispatcher.execute_delivery(mock_session, delivery_retry, valid_sub)
    assert delivery_retry.status == "failed"
    assert delivery_retry.attempt_count == 1

    # 8. Unseal with invalid decryption blob logs warning and returns empty
    sub_corrupted = WebhookSubscription(
        id=sub_id,
        workspace_id=ws_id,
        target_url="https://valid.target.org",
        secret_ciphertext=b"\x00\x051234567890corrupted",
        secret_dek_kid="kek-v1",  # noqa: S106
    )
    assert net_dispatcher._unseal_secret(sub_corrupted) == b""  # noqa: SLF001


async def test_outbox_relay_event_hook_invocation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """OutboxRelay executes registered event_hooks during drain_once."""
    admin = await make_user("admin_relay_hook", workspace_role="WORKSPACE_ADMIN")
    app = api_env.client._transport.app  # type: ignore[attr-defined] # noqa: SLF001
    engine = app.state.session_factory.engine

    called_envelopes: list[OutboxEnvelope] = []

    async def sample_hook(envelope: OutboxEnvelope) -> None:
        called_envelopes.append(envelope)

    mock_broker = MagicMock()
    mock_broker.publish = AsyncMock()

    relay = OutboxRelay(
        engine=engine,
        listen_dsn="postgresql://localhost/dummy",
        broker=mock_broker,
        event_hooks=[sample_hook],
    )

    added_envelopes: list[OutboxEnvelope] = []

    async def added_hook(envelope: OutboxEnvelope) -> None:
        added_envelopes.append(envelope)

    relay.add_event_hook(added_hook)

    admin_ctx = RLSContext(principal_id=admin.id, workspace_id=admin.workspace_id)
    async with app.state.session_factory.session(admin_ctx) as session:
        event_id = await enqueue_outbox_event(
            session,
            workspace_id=admin.workspace_id,
            topic="test.event",
            payload={"hello": "world"},
        )
        await session.commit()

    drained = await relay.drain_once()
    assert drained == 1
    assert len(called_envelopes) == 1
    assert called_envelopes[0].id == event_id
    assert called_envelopes[0].topic == "test.event"
    assert len(added_envelopes) == 1
    assert added_envelopes[0].id == event_id
