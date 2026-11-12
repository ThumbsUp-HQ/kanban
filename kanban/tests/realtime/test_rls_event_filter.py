# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for delivery-time RLS authorization and actor payload redaction (KB-P3-16)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from database.session import RLSContext, RLSSessionFactory
from kanban.realtime.rls_filter import (
    EXTERNAL_COLLABORATOR_REDACTED,
    OutboxEventLike,
    authorize_event_recipients,
    redact_event_payload,
)
from kanban.security.permissions import Capability
from kanban.tests.realtime.conftest import create_realtime_test_fixtures

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


class _FakeEnvelope(OutboxEventLike):
    def __init__(
        self,
        workspace_id: uuid.UUID,
        object_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> None:
        self.workspace_id = workspace_id
        self.object_id = object_id
        self.project_id = project_id


@pytest.mark.asyncio
async def test_redact_event_payload_when_visible() -> None:
    """Test payload is unchanged when actor is within recipient visibility boundary."""
    payload = {
        "actor": {"email": "alice@example.com", "handle": "alice", "id": str(uuid.uuid4())},
        "actor_principal_id": str(uuid.uuid4()),
        "change": "state",
    }
    result = redact_event_payload(payload, is_visible=True)
    assert result == payload
    assert result["actor"]["handle"] == "alice"


@pytest.mark.asyncio
async def test_redact_event_payload_when_outside_boundary() -> None:
    """Test actor is masked and sensitive fields purged when outside visibility boundary."""
    actor_id = str(uuid.uuid4())
    payload = {
        "actor": {"email": "secret@vendor.com", "handle": "secret_vendor", "id": actor_id},
        "actor_email": "secret@vendor.com",
        "actor_handle": "secret_vendor",
        "actor_name": "Vendor User",
        "actor_principal_id": actor_id,
        "change": "COMMENT_CREATED",
    }
    result = redact_event_payload(payload, is_visible=False)
    assert result["actor"] == EXTERNAL_COLLABORATOR_REDACTED
    assert "actor_email" not in result
    assert "actor_handle" not in result
    assert "actor_principal_id" not in result
    assert "actor_name" not in result
    assert result["change"] == "COMMENT_CREATED"


@pytest.mark.asyncio
async def test_redact_event_payload_without_actor_key() -> None:
    """Test payload without actor key purges sensitive top-level fields."""
    payload = {
        "actor_id": str(uuid.uuid4()),
        "change": "WORKSPACE_UPDATED",
    }
    result = redact_event_payload(payload, is_visible=False)
    assert "actor_id" not in result
    assert result["change"] == "WORKSPACE_UPDATED"
    assert "actor" not in result


@pytest.mark.asyncio
async def test_authorize_event_recipients_empty_candidates(pg_worker_db: AsyncEngine) -> None:
    """Test empty candidates sequence returns empty set without executing database queries."""
    factory = RLSSessionFactory(pg_worker_db)
    ctx = RLSContext(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4(), aal_level=1)
    async with factory.session(ctx) as session:
        envelope = _FakeEnvelope(workspace_id=ctx.workspace_id, object_id=uuid.uuid4())
        authorized = await authorize_event_recipients(session, envelope, [])
        assert authorized == set()


@pytest.mark.asyncio
async def test_authorize_event_recipients_batched_view_and_deny(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test batched evaluation correctly includes VIEW and excludes DENY principals."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]
    maya_id = fixture_data["maya_id"]
    other_id = fixture_data["other_id"]
    issue_id = fixture_data["issue_id"]

    # Explicitly add DENY VIEW for Maya on the issue
    ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        view_bit = Capability.VIEW.value
        await session.execute(
            text(
                "UPDATE effective_resource_access "
                "SET deny_mask = :deny "
                "WHERE object_id = :oid AND principal_id = :pid"
            ),
            {"deny": view_bit, "oid": issue_id, "pid": maya_id},
        )

        envelope = _FakeEnvelope(
            workspace_id=ws_id,
            object_id=issue_id,
            project_id=fixture_data["proj_id"],
        )
        candidates = [admin_id, maya_id, other_id]
        authorized = await authorize_event_recipients(session, envelope, candidates)

        # Admin and other_id should be authorized; Maya has DENY VIEW and must be excluded
        assert admin_id in authorized
        assert other_id in authorized
        assert maya_id not in authorized


@pytest.mark.asyncio
async def test_authorize_event_recipients_fallback_to_project(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test authorization checks project permissions when object_id is None."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    ws_id = fixture_data["ws_id"]
    admin_id = fixture_data["admin_id"]
    maya_id = fixture_data["maya_id"]
    proj_id = fixture_data["proj_id"]

    ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        envelope = _FakeEnvelope(
            workspace_id=ws_id,
            object_id=None,
            project_id=proj_id,
        )
        authorized = await authorize_event_recipients(session, envelope, [admin_id, maya_id])
        assert authorized == {admin_id, maya_id}


@pytest.mark.asyncio
async def test_authorize_event_recipients_no_target_id_authorizes_all(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test event with no object_id and no project_id authorizes all candidate principals."""
    factory = RLSSessionFactory(pg_worker_db)
    ctx = RLSContext(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4(), aal_level=1)
    async with factory.session(ctx) as session:
        envelope = _FakeEnvelope(workspace_id=ctx.workspace_id, object_id=None, project_id=None)
        p1, p2 = uuid.uuid4(), uuid.uuid4()
        authorized = await authorize_event_recipients(session, envelope, [p1, p2])
        assert authorized == {p1, p2}


@pytest.mark.asyncio
async def test_authorize_event_recipients_without_workspace_id(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test authorization query executes properly when workspace_id is None on envelope."""
    factory = RLSSessionFactory(pg_worker_db)
    fixture_data = await create_realtime_test_fixtures(factory)
    admin_id = fixture_data["admin_id"]
    issue_id = fixture_data["issue_id"]

    ctx = RLSContext(principal_id=admin_id, workspace_id=fixture_data["ws_id"], aal_level=1)
    async with factory.session(ctx) as session:
        envelope = _FakeEnvelope(
            workspace_id=fixture_data["ws_id"],
            object_id=issue_id,
        )
        object.__setattr__(envelope, "workspace_id", None)
        authorized = await authorize_event_recipients(session, envelope, [admin_id])
        assert authorized == {admin_id}
