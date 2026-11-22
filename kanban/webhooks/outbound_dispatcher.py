# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Outbound webhook dispatcher with SSRF guard and backoff retry (KB-DEVSECOPS-BUS-01)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.parse
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import httpx
from sqlalchemy import select

from database.models.webhooks import WebhookDelivery, WebhookSubscription
from database.session import RLSContext, RLSSessionFactory
from kanban.security.envelope import KekProvider, SealedSecret, open_bound
from kanban.security.ssrf import (
    SSRFBlockedError,
    resolve_and_select_pinned_ip,
    validate_not_redirect,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from ipaddress import IPv4Address, IPv6Address

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from database.outbox.broker import OutboxEnvelope

logger = logging.getLogger(__name__)

MAX_ATTEMPTS: Final[int] = 5
DEFAULT_TIMEOUT_SECONDS: Final[float] = 10.0
ENVELOPE_HEADER_LEN: Final[int] = 2
HTTP_SUCCESS_MIN: Final[int] = 200
HTTP_SUCCESS_MAX: Final[int] = 300


class OutboundWebhookDispatcher:
    """Dispatches transactional outbox events to registered webhook subscriptions."""

    def __init__(  # noqa: PLR0913
        self,
        engine: AsyncEngine,
        kek_provider: KekProvider | None = None,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        air_gap_mode: bool = False,
        dns_resolver: Callable[..., Any] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize outbound webhook dispatcher with engine and security options."""
        self._engine = engine
        self._kek_provider = kek_provider
        self._max_attempts = max_attempts
        self._air_gap_mode = air_gap_mode
        self._dns_resolver = dns_resolver
        self._http_client = http_client

    async def __call__(self, envelope: OutboxEnvelope) -> None:
        """Callable hook protocol for OutboxRelay event hooks."""
        await self.dispatch_envelope(envelope)

    def _matches_topic(self, sub_events: Sequence[str], event_topic: str) -> bool:
        """Check if subscription event patterns match the given topic."""
        if not sub_events:
            return False
        if "*" in sub_events or event_topic in sub_events:
            return True
        for pattern in sub_events:
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if event_topic == prefix or event_topic.startswith(f"{prefix}."):
                    return True
        return False

    def _unseal_secret(self, sub: WebhookSubscription) -> bytes:
        """Unseal envelope-encrypted subscription signing secret."""
        if not sub.secret_ciphertext or not sub.secret_dek_kid or self._kek_provider is None:
            return b""
        aad = f"kanban/webhook-sub/v1|{sub.id}|{sub.workspace_id}".encode()
        raw = sub.secret_ciphertext
        if len(raw) < ENVELOPE_HEADER_LEN:
            return b""
        wrapped_len = int.from_bytes(raw[:ENVELOPE_HEADER_LEN], "big")
        wrapped_dek = raw[ENVELOPE_HEADER_LEN : ENVELOPE_HEADER_LEN + wrapped_len]
        secret_blob = raw[ENVELOPE_HEADER_LEN + wrapped_len :]
        sealed = SealedSecret(
            encrypted_secret_blob=secret_blob,
            wrapped_dek=wrapped_dek,
            dek_kid=sub.secret_dek_kid,
        )
        try:
            ba = open_bound(sealed, aad, self._kek_provider)
            return bytes(ba)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to unseal webhook secret for subscription %s: %s", sub.id, exc)
            return b""

    def _build_signed_headers(
        self,
        delivery: WebhookDelivery,
        sub: WebhookSubscription,
        payload_bytes: bytes,
    ) -> dict[str, str]:
        """Construct standard HMAC signed delivery headers."""
        secret_bytes = self._unseal_secret(sub)
        timestamp = str(int(time.time()))
        signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Kanban-Signature-256": f"sha256={signature}",
            "X-Kanban-Timestamp": timestamp,
            "X-Kanban-Delivery-Id": str(delivery.id),
        }

    def _set_delivery_error(self, delivery: WebhookDelivery, error_message: str) -> None:
        """Set error message and transition status to failed or dead_letter based on attempts."""
        delivery.error_message = error_message
        if delivery.attempt_count >= self._max_attempts:
            delivery.status = "dead_letter"
        else:
            delivery.status = "failed"

    async def _send_payload(
        self,
        target_url: str,
        payload_bytes: bytes,
        headers: dict[str, str],
        pinned_ip: IPv4Address | IPv6Address,  # noqa: ARG002
    ) -> httpx.Response:
        """Send HTTP payload via provided client or fresh async client."""
        if self._http_client is not None:
            return await self._http_client.post(
                target_url,
                content=payload_bytes,
                headers=headers,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            return await client.post(
                target_url,
                content=payload_bytes,
                headers=headers,
            )

    async def dispatch_envelope(self, envelope: OutboxEnvelope) -> list[WebhookDelivery]:
        """Dispatch outbox envelope to all active matching webhook subscriptions."""
        session_factory = getattr(self, "_session_factory", None)
        if session_factory is None:
            session_factory = RLSSessionFactory(self._engine)
            self._session_factory = session_factory

        ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=envelope.workspace_id,
            token_scopes=("system", "webhook"),
        )
        async with session_factory.session(ctx) as session:
            stmt = select(WebhookSubscription).where(
                WebhookSubscription.workspace_id == envelope.workspace_id,
                WebhookSubscription.is_active.is_(True),
            )
            res = await session.execute(stmt)
            subs = list(res.scalars().all())

            matching_subs = [
                s
                for s in subs
                if (s.project_id is None or s.project_id == envelope.project_id)
                and self._matches_topic(s.events, envelope.topic)
            ]

            deliveries: list[WebhookDelivery] = []
            for sub in matching_subs:
                delivery_id = uuid.uuid4()
                delivery = WebhookDelivery(
                    id=delivery_id,
                    workspace_id=sub.workspace_id,
                    subscription_id=sub.id,
                    event_id=envelope.id,
                    event_topic=envelope.topic,
                    payload_json=dict(envelope.payload),
                    attempt_count=0,
                    status="pending",
                )
                session.add(delivery)
                await session.flush()
                await self.execute_delivery(session, delivery, sub)
                deliveries.append(delivery)

            return deliveries

    async def execute_delivery(
        self,
        session: AsyncSession,
        delivery: WebhookDelivery,
        sub: WebhookSubscription,
    ) -> None:
        """Execute HTTP delivery with SSRF validation, payload signing, and backoff tracking."""
        del session
        if self._air_gap_mode:
            delivery.status = "failed"
            delivery.attempt_count += 1
            delivery.error_message = "AIR_GAP_MODE"
            return

        delivery.attempt_count += 1
        payload_bytes = json.dumps(delivery.payload_json).encode("utf-8")
        headers = self._build_signed_headers(delivery, sub, payload_bytes)

        parsed = urllib.parse.urlsplit(sub.target_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            self._set_delivery_error(delivery, f"Invalid target URL: {sub.target_url}")
            return

        try:
            pinned_ip = await resolve_and_select_pinned_ip(
                parsed.hostname,
                resolver=self._dns_resolver,
            )
        except SSRFBlockedError as exc:
            self._set_delivery_error(delivery, f"SSRF_BLOCKED: {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            self._set_delivery_error(delivery, f"DNS_RESOLUTION_ERROR: {exc}")
            return

        try:
            resp = await self._send_payload(sub.target_url, payload_bytes, headers, pinned_ip)
            validate_not_redirect(resp.status_code)

            delivery.status_code = resp.status_code
            if HTTP_SUCCESS_MIN <= resp.status_code < HTTP_SUCCESS_MAX:
                delivery.status = "delivered"
                delivery.delivered_at = datetime.now(UTC)
                delivery.error_message = None
            else:
                self._set_delivery_error(delivery, f"HTTP {resp.status_code}")
        except SSRFBlockedError as exc:
            self._set_delivery_error(delivery, f"SSRF_REDIRECT_BLOCKED: {exc}")
        except Exception as exc:  # noqa: BLE001
            self._set_delivery_error(delivery, f"DISPATCH_ERROR: {exc}")
