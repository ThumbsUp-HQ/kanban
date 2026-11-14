# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Shared fixtures for custom fields tests."""

import base64

import pytest


@pytest.fixture(autouse=True)
def _setup_test_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide standard test key material for HKDF subkey derivations."""
    key_32 = b"\x31" * 32
    b64 = base64.urlsafe_b64encode(key_32).decode("ascii")
    monkeypatch.setenv("KANBAN_MASTER_KEK", b64)
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", b64)
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", b64)
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")
