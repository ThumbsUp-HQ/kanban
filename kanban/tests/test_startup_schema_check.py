# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for startup Alembic schema head verification diagnostic (KANBA-230)."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kanban.app import verify_schema_head


@pytest.mark.asyncio
async def test_verify_schema_head_matching(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that startup schema verification succeeds when db head matches code head."""
    session_factory = MagicMock()
    mock_engine = MagicMock()
    session_factory._engine = mock_engine  # noqa: SLF001

    mock_conn = AsyncMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    # Mock DB returning current head
    mock_res = MagicMock()
    mock_res.fetchall.return_value = [("rev_head_123",)]
    mock_conn.execute.return_value = mock_res

    with (
        patch("alembic.script.ScriptDirectory.from_config") as mock_script_cls,
        caplog.at_level(logging.INFO),
    ):
        mock_script = MagicMock()
        mock_script.get_heads.return_value = ["rev_head_123"]
        mock_script_cls.return_value = mock_script

        await verify_schema_head(session_factory)

    assert "Database schema head verified" in caplog.text


@pytest.mark.asyncio
async def test_verify_schema_head_behind_logs_cross_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify that startup schema verification emits cross diagnostic when db is behind."""
    session_factory = MagicMock()
    mock_engine = MagicMock()
    session_factory._engine = mock_engine  # noqa: SLF001

    mock_conn = AsyncMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    # Mock DB returning an older head
    mock_res = MagicMock()
    mock_res.fetchall.return_value = [("rev_old_001",)]
    mock_conn.execute.return_value = mock_res

    with (
        patch("alembic.script.ScriptDirectory.from_config") as mock_script_cls,
        caplog.at_level(logging.ERROR),
    ):
        mock_script = MagicMock()
        mock_script.get_heads.return_value = ["rev_new_002"]
        mock_script_cls.return_value = mock_script

        await verify_schema_head(session_factory)

    assert "❌ Database schema is out of date" in caplog.text
    assert "behind code head" in caplog.text
