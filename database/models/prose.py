# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Re-export knowledge and prose models with content provenance tiers (KB-SEC-PROV-01)."""

from __future__ import annotations

from typing import Final

from database.models.knowledge import Doc, Page, PageVersion, Sticky

__all__ = [
    "ALL_PROVENANCE_TIERS",
    "UNTRUSTED_PROVENANCE_TIERS",
    "Doc",
    "Page",
    "PageVersion",
    "Sticky",
]

ALL_PROVENANCE_TIERS: Final[frozenset[str]] = frozenset(
    {
        "trusted_member",
        "verified_agent",
        "imported",
        "external_webhook",
        "public_reporter",
        "untrusted_intake",
    }
)

UNTRUSTED_PROVENANCE_TIERS: Final[frozenset[str]] = frozenset(
    {
        "imported",
        "external_webhook",
        "public_reporter",
        "untrusted_intake",
    }
)
