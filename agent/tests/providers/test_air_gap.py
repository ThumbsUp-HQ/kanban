# Copyright 2026 Kanban Platform Contributors
"""Unit tests for air-gap enforcement guard."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent.providers.air_gap import AirGapGuard
from agent.providers.errors import EgressDenied


def test_case_6_air_gap_denies_cloud_providers_before_transport() -> None:
    """Case 6: air_gap_mode=True with gemini/openai -> AIR_GAP_EGRESS_DENIED; 0 calls."""
    resolver_mock = MagicMock()
    transport_mock = MagicMock()

    with pytest.raises(EgressDenied) as exc_info:
        AirGapGuard.check("gemini", air_gap_mode=True)
    assert exc_info.value.code == "AIR_GAP_EGRESS_DENIED"
    assert "gemini" in str(exc_info.value)

    with pytest.raises(EgressDenied) as exc_info:
        AirGapGuard.check("openai", air_gap_mode=True)
    assert exc_info.value.code == "AIR_GAP_EGRESS_DENIED"
    assert "openai" in str(exc_info.value)

    assert resolver_mock.call_count == 0
    assert transport_mock.call_count == 0


def test_case_7_air_gap_fails_closed_when_mode_is_none() -> None:
    """Case 7: air_gap_mode=None treated as TRUE (fail closed)."""
    with pytest.raises(EgressDenied) as exc_info:
        AirGapGuard.check("gemini", air_gap_mode=None)
    assert exc_info.value.code == "AIR_GAP_EGRESS_DENIED"

    with pytest.raises(EgressDenied) as exc_info:
        AirGapGuard.check("openai", air_gap_mode=None)
    assert exc_info.value.code == "AIR_GAP_EGRESS_DENIED"


def test_air_gap_permits_ollama_and_fixture_under_air_gap() -> None:
    """Verify local ollama and deterministic fixture providers are permitted under air-gap."""
    AirGapGuard.check("ollama", air_gap_mode=True)
    AirGapGuard.check("fixture", air_gap_mode=True)
    AirGapGuard.check("ollama", air_gap_mode=None)
    AirGapGuard.check("fixture", air_gap_mode=None)


def test_air_gap_permits_cloud_when_mode_is_false() -> None:
    """Verify cloud providers are permitted when air_gap_mode is explicitly disabled."""
    AirGapGuard.check("gemini", air_gap_mode=False)
    AirGapGuard.check("openai", air_gap_mode=False)
    AirGapGuard.check("ollama", air_gap_mode=False)
    AirGapGuard.check("fixture", air_gap_mode=False)
