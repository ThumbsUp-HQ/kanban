# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""PostgreSQL trigger, constraints, and RLS tests for custom field escalation approvals.

KB-P5-12.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.tests.conftest import bind_ctx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _compute_manifest(
    source: str,
    fmt: str = "text",
    meta: dict[str, Any] | None = None,
    scope: str = "WORKSPACE",
    cred: str = "INVOKING_USER",
) -> bytes:
    payload = {
        "credential_mode": cred,
        "egress_allowlist": [],
        "output_format": fmt,
        "output_format_metadata": meta or {"format": "text", "max_length": 100},
        "script_source": source,
        "target_scope": scope,
        "tier": "wasm",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).digest()


async def _setup_fixture(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Provision workspace, project, and principals for approvals testing."""
    await session.execute(text("RESET SESSION AUTHORIZATION"))
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Custom Fields WS"},
    )

    admin_id = uuid.uuid4()
    member_id = uuid.uuid4()
    server_admin_id = uuid.uuid4()
    server_admin2_id = uuid.uuid4()

    for pid, dname in (
        (admin_id, "Project Admin"),
        (member_id, "Member User"),
        (server_admin_id, "Server Admin 1"),
        (server_admin2_id, "Server Admin 2"),
    ):
        await session.execute(
            text("SELECT register_object('user'::object_kind, :ws, NULL, :ckey, :name, :uid, :id)"),
            {"ws": ws_id, "ckey": f"usr-{pid.hex[:8]}", "name": dname, "uid": pid, "id": pid},
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', :name)"
            ),
            {"id": pid, "ws_id": ws_id, "name": dname},
        )
        await session.execute(
            text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
            {"id": pid, "ws_id": ws_id, "email": f"{pid.hex[:8]}@example.com"},
        )

    ident = f"P{uuid.uuid4().hex[:4].upper()}"
    proj_id = await session.scalar(
        text(
            "SELECT register_object("
            "'project'::object_kind, :ws, NULL, :ident, 'Custom Field Proj', :uid)"
        ),
        {"ws": ws_id, "ident": ident, "uid": admin_id},
    )
    assert isinstance(proj_id, uuid.UUID)
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws, :ident, 'Custom Field Proj')"
        ),
        {"id": proj_id, "ws": ws_id, "ident": ident},
    )

    # Role bindings
    for pid, role, scope, prj in (
        (admin_id, "PROJECT_ADMIN", "project", proj_id),
        (member_id, "MEMBER", "project", proj_id),
        (server_admin_id, "SERVER_ADMIN", "server", None),
        (server_admin2_id, "SERVER_ADMIN", "server", None),
    ):
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:ws, :p, :role, :scope, :proj)"
            ),
            {"ws": ws_id, "p": pid, "role": role, "scope": scope, "proj": prj},
        )

    await session.execute(text("SELECT rebuild_effective_access_for_workspace(:ws)"), {"ws": ws_id})

    return {
        "ws_id": ws_id,
        "proj_id": proj_id,
        "admin_id": admin_id,
        "member_id": member_id,
        "server_admin_id": server_admin_id,
        "server_admin2_id": server_admin2_id,
    }


@pytest.mark.asyncio
async def test_01_tamper_auto_revocation_trigger(db_session: AsyncSession) -> None:
    """Modifying script_source or metadata updates manifest and auto-revokes approvals."""
    ids = await _setup_fixture(db_session)
    ws_id, proj_id, admin_id = ids["ws_id"], ids["proj_id"], ids["admin_id"]

    field_id = uuid.uuid4()
    source1 = "export default function() { return 'v1'; }"
    meta = {"format": "text", "max_length": 100}
    m1 = _compute_manifest(source1, "text", meta, "WORKSPACE", "INVOKING_USER")

    # Create definition
    await db_session.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "  id, workspace_id, project_id, slug, name, tier, output_format, "
            "  output_format_metadata, script_source, script_version, target_scope, "
            "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, created_by_id"
            ") VALUES ("
            "  :id, :ws, :proj, 'auto-revoke-field', 'Auto Revoke Field', 'wasm', 'text', "
            "  CAST(:meta AS jsonb), :source, 1, 'WORKSPACE', "
            "  'INVOKING_USER', '{}', :manifest, true, :uid"
            ")"
        ),
        {
            "id": field_id,
            "ws": ws_id,
            "proj": proj_id,
            "meta": json.dumps(meta),
            "source": source1,
            "manifest": m1,
            "uid": admin_id,
        },
    )

    # Insert 3 approval rows: PENDING, PENDING_SECOND_APPROVER, and APPROVED
    appr_pending = uuid.uuid4()
    appr_dual = uuid.uuid4()
    appr_approved = uuid.uuid4()

    for a_id, st in (
        (appr_pending, "PENDING"),
        (appr_dual, "PENDING_SECOND_APPROVER"),
        (appr_approved, "APPROVED"),
    ):
        await db_session.execute(
            text(
                "INSERT INTO custom_field_approvals ("
                "  id, workspace_id, project_id, field_id, manifest_sha256, "
                "  target_scope, credential_mode, required_tier, status, "
                "  requested_by_id, justification, primary_approver_id, primary_approver_aal"
                ") VALUES ("
                "  :id, :ws, :proj, :fid, :m, "
                "  'WORKSPACE', 'INVOKING_USER', 'WORKSPACE_ADMIN', :status, "
                "  :uid, 'Legitimate justification for audit', :uid, 2"
                ")"
            ),
            {
                "id": a_id,
                "ws": ws_id,
                "proj": proj_id,
                "fid": field_id,
                "m": m1,
                "status": st,
                "uid": admin_id,
            },
        )

    # 1. Update definition with benign change (name only, manifest_sha256 unchanged)
    await db_session.execute(
        text("UPDATE custom_field_definitions SET name = 'Renamed Field' WHERE id = :id"),
        {"id": field_id},
    )
    statuses = (
        (
            await db_session.execute(
                text("SELECT status FROM custom_field_approvals WHERE field_id = :fid ORDER BY id"),
                {"fid": field_id},
            )
        )
        .scalars()
        .all()
    )
    assert set(statuses) == {"PENDING", "PENDING_SECOND_APPROVER", "APPROVED"}

    # 2. Tamper script source: manifest_sha256 changes -> trigger fires
    source2 = "export default function() { return 'v2-tampered'; }"
    m2 = _compute_manifest(source2, "text", meta, "WORKSPACE", "INVOKING_USER")

    await db_session.execute(
        text(
            "UPDATE custom_field_definitions "
            "SET script_source = :src, manifest_sha256 = :m, script_version = 2 "
            "WHERE id = :id"
        ),
        {"id": field_id, "src": source2, "m": m2},
    )

    rows = (
        await db_session.execute(
            text(
                "SELECT status, revoked_reason, revoked_at "
                "FROM custom_field_approvals WHERE field_id = :fid"
            ),
            {"fid": field_id},
        )
    ).all()
    assert len(rows) == 3
    for r in rows:
        assert r.status == "REVOKED"
        assert r.revoked_reason == "MANIFEST_SHA256_CHANGED"
        assert r.revoked_at is not None


@pytest.mark.asyncio
async def test_02_approvals_db_constraints(db_session: AsyncSession) -> None:
    """Verify CHECK constraints on dual control, invalid combinations, and justification."""
    ids = await _setup_fixture(db_session)
    ws_id, proj_id, admin_id = ids["ws_id"], ids["proj_id"], ids["admin_id"]
    sa1_id = ids["server_admin_id"]

    field_id = uuid.uuid4()
    source = "export default () => 1"
    meta = {"format": "text", "max_length": 50}
    m = _compute_manifest(source, "text", meta, "SERVER", "SERVER_ADMIN_SP")

    await db_session.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "  id, workspace_id, project_id, slug, name, tier, output_format, "
            "  output_format_metadata, script_source, script_version, target_scope, "
            "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, created_by_id"
            ") VALUES ("
            "  :id, :ws, :proj, 'server-field', 'Server Field', 'wasm', 'text', "
            "  CAST(:meta AS jsonb), :source, 1, 'SERVER', "
            "  'SERVER_ADMIN_SP', '{}', :manifest, true, :uid"
            ")"
        ),
        {
            "id": field_id,
            "ws": ws_id,
            "proj": proj_id,
            "meta": json.dumps(meta),
            "source": source,
            "manifest": m,
            "uid": admin_id,
        },
    )

    # 1. Dual control: secondary_approver_id == primary_approver_id fails
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO custom_field_approvals ("
                    "  id, workspace_id, project_id, field_id, manifest_sha256, "
                    "  target_scope, credential_mode, required_tier, status, "
                    "  requested_by_id, justification, primary_approver_id, secondary_approver_id"
                    ") VALUES ("
                    "  :id, :ws, :proj, :fid, :m, "
                    "  'SERVER', 'SERVER_ADMIN_SP', 'SERVER_ADMIN_DUAL', 'APPROVED', "
                    "  :uid, 'Valid length justification for testing', :sa1, :sa1"
                    ")"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": ws_id,
                    "proj": proj_id,
                    "fid": field_id,
                    "m": m,
                    "uid": admin_id,
                    "sa1": sa1_id,
                },
            )
    assert "custom_field_approvals_dual_approver_distinct_check" in str(exc_info.value)

    # 2. Invalid Scope x Principal combination: (PROJECT, SERVER_ADMIN_SP) fails
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO custom_field_approvals ("
                    "  id, workspace_id, project_id, field_id, manifest_sha256, "
                    "  target_scope, credential_mode, required_tier, status, "
                    "  requested_by_id, justification"
                    ") VALUES ("
                    "  :id, :ws, :proj, :fid, :m, "
                    "  'PROJECT', 'SERVER_ADMIN_SP', 'PROJECT_ADMIN', 'PENDING', "
                    "  :uid, 'Valid length justification for testing'"
                    ")"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": ws_id,
                    "proj": proj_id,
                    "fid": field_id,
                    "m": m,
                    "uid": admin_id,
                },
            )
    assert "custom_field_approvals_scope_principal_combo_check" in str(exc_info.value)

    # 3. Justification too short (< 10 chars) fails
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO custom_field_approvals ("
                    "  id, workspace_id, project_id, field_id, manifest_sha256, "
                    "  target_scope, credential_mode, required_tier, status, "
                    "  requested_by_id, justification"
                    ") VALUES ("
                    "  :id, :ws, :proj, :fid, :m, "
                    "  'SERVER', 'SERVER_ADMIN_SP', 'SERVER_ADMIN_DUAL', 'PENDING', "
                    "  :uid, 'short'"
                    ")"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": ws_id,
                    "proj": proj_id,
                    "fid": field_id,
                    "m": m,
                    "uid": admin_id,
                },
            )
    assert "custom_field_approvals_justification_check" in str(exc_info.value)


@pytest.mark.asyncio
async def test_03_approvals_rls_policies(db_session: AsyncSession) -> None:
    """Verify RLS: SELECT requires admin tier; INSERT requires AAL2."""
    ids = await _setup_fixture(db_session)
    ws_id, proj_id = ids["ws_id"], ids["proj_id"]
    admin_id, member_id = ids["admin_id"], ids["member_id"]

    field_id = uuid.uuid4()
    source = "export default () => 'rls-test'"
    meta = {"format": "text", "max_length": 50}
    m = _compute_manifest(source, "text", meta, "WORKSPACE", "INVOKING_USER")

    await db_session.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "  id, workspace_id, project_id, slug, name, tier, output_format, "
            "  output_format_metadata, script_source, script_version, target_scope, "
            "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, created_by_id"
            ") VALUES ("
            "  :id, :ws, :proj, 'rls-appr-field', 'RLS Field', 'wasm', 'text', "
            "  CAST(:meta AS jsonb), :source, 1, 'WORKSPACE', "
            "  'INVOKING_USER', '{}', :manifest, true, :uid"
            ")"
        ),
        {
            "id": field_id,
            "ws": ws_id,
            "proj": proj_id,
            "meta": json.dumps(meta),
            "source": source,
            "manifest": m,
            "uid": admin_id,
        },
    )

    appr_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO custom_field_approvals ("
            "  id, workspace_id, project_id, field_id, manifest_sha256, "
            "  target_scope, credential_mode, required_tier, status, "
            "  requested_by_id, justification"
            ") VALUES ("
            "  :id, :ws, :proj, :fid, :m, "
            "  'WORKSPACE', 'INVOKING_USER', 'WORKSPACE_ADMIN', 'PENDING', "
            "  :uid, 'Valid length justification for testing'"
            ")"
        ),
        {
            "id": appr_id,
            "ws": ws_id,
            "proj": proj_id,
            "fid": field_id,
            "m": m,
            "uid": admin_id,
        },
    )

    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 1. Project admin with AAL2 can see row
    await bind_ctx(db_session, admin_id, ws_id)
    await db_session.execute(text("SELECT set_config('app.aal_level', '2', true)"))
    cnt_admin = await db_session.scalar(
        text("SELECT count(*) FROM custom_field_approvals WHERE id = :id"),
        {"id": appr_id},
    )
    assert cnt_admin == 1

    # 2. Member cannot see row (0 returned)
    await bind_ctx(db_session, member_id, ws_id)
    await db_session.execute(text("SELECT set_config('app.aal_level', '2', true)"))
    cnt_member = await db_session.scalar(
        text("SELECT count(*) FROM custom_field_approvals WHERE id = :id"),
        {"id": appr_id},
    )
    assert cnt_member == 0

    # 3. Direct INSERT with AAL1 fails WITH CHECK
    await bind_ctx(db_session, admin_id, ws_id)
    await db_session.execute(text("SELECT set_config('app.aal_level', '1', true)"))
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO custom_field_approvals ("
                    "  id, workspace_id, project_id, field_id, manifest_sha256, "
                    "  target_scope, credential_mode, required_tier, status, "
                    "  requested_by_id, justification"
                    ") VALUES ("
                    "  :id, :ws, :proj, :fid, :m, "
                    "  'WORKSPACE', 'INVOKING_USER', 'WORKSPACE_ADMIN', 'PENDING', "
                    "  :uid, 'Valid length justification for testing'"
                    ")"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": ws_id,
                    "proj": proj_id,
                    "fid": field_id,
                    "m": m,
                    "uid": admin_id,
                },
            )
    assert (
        "violates row-level security policy" in str(exc_info.value).lower()
        or "check" in str(exc_info.value).lower()
    )
