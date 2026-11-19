# Copyright 2026 Kanban Platform Contributors
"""Air-gap enforcement guard blocking cloud provider egress before transport."""

from __future__ import annotations

from agent.providers.errors import EgressDenied
from kanban.ai_config.net_guard import is_local_base_url

__all__ = [
    "ALLOWED_AIR_GAP_KINDS",
    "AirGapGuard",
]

ALLOWED_AIR_GAP_KINDS: frozenset[str] = frozenset({"ollama", "fixture"})


class AirGapGuard:
    """Security guard enforcing workspace air-gap policy prior to provider construction."""

    @classmethod
    def check(
        cls,
        provider_kind: str,
        settings: object = None,
        *,
        air_gap_mode: bool | None,
    ) -> None:
        """Assert provider kind is permitted under air-gap policy.

        Fails closed: if air_gap_mode is True or None (unspecified), egress to cloud
        endpoints is forbidden and raises EgressDenied(code='AIR_GAP_EGRESS_DENIED')
        before DNS resolution or socket allocation.
        """
        # Unknown/None is treated as True (fail-closed)
        is_air_gapped = air_gap_mode is not False
        normalized_kind = provider_kind.strip().lower()

        if is_air_gapped:
            if normalized_kind == "openai" and settings is not None:
                base_url = getattr(settings, "base_url", None)
                if base_url is None and isinstance(settings, dict):
                    base_url = settings.get("base_url")
                if base_url is not None and is_local_base_url(str(base_url)):
                    return
            if normalized_kind not in ALLOWED_AIR_GAP_KINDS:
                msg = (
                    f"Air-gap mode is active: outbound cloud egress to provider '{provider_kind}' "
                    f"is strictly prohibited"
                )
                raise EgressDenied(msg, code="AIR_GAP_EGRESS_DENIED")
