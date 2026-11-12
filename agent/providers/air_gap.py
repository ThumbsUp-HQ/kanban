# Copyright 2026 Kanban Platform Contributors
"""Air-gap enforcement guard blocking cloud provider egress before transport."""

from __future__ import annotations

from agent.providers.errors import EgressDenied

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
        del settings  # Reserved for provider-specific setting audits
        # Unknown/None is treated as True (fail-closed)
        is_air_gapped = air_gap_mode is not False
        normalized_kind = provider_kind.strip().lower()

        if is_air_gapped and normalized_kind not in ALLOWED_AIR_GAP_KINDS:
            msg = (
                f"Air-gap mode is active: outbound cloud egress to provider '{provider_kind}' "
                f"is strictly prohibited"
            )
            raise EgressDenied(msg, code="AIR_GAP_EGRESS_DENIED")
