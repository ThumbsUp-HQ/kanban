# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Webhooks package for inbound SCM webhooks and outbound event dispatch (KB-DEVSECOPS-BUS-01)."""

from __future__ import annotations

from kanban.webhooks.outbound_dispatcher import OutboundWebhookDispatcher

__all__ = [
    "OutboundWebhookDispatcher",
]
