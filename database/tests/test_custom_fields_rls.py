# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive PostgreSQL RLS and WITH CHECK tests for custom fields (KB-P5-11, S13.1, S3.3)."""

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


def _manifest(source: str, fmt: str, meta: dict[str, object]) -> bytes:
    payload = {
        "credential_mode": "INVOKING_USER",
        "egress_allowlist": [],
        "output_format": fmt,
        "output_format_metadata": meta,
        "script_source": source,
        "target_scope": "PROJECT",
        "tier": "wasm",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).digest()


async def _setup_fixture(
    session: AsyncSession,
) -> dict[str, uuid.UUID]:
    """Provision workspace, project, issue, and principals for RLS testing."""
    await session.execute(text("RESET SESSION AUTHORIZATION"))
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Custom Fields WS"},
    )

    admin_id = uuid.uuid4()
    member_id = uuid.uuid4()
    viewer_id = uuid.uuid4()
    guest_id = uuid.uuid4()

    for pid, dname in (
        (admin_id, "Admin User"),
        (member_id, "Member User"),
        (viewer_id, "Viewer User"),
        (guest_id, "Guest User"),
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

    # Project triggers automatically seed default workflow states and priorities
    state_id = await session.scalar(
        text(
            "SELECT id FROM workflow_states WHERE project_id = :proj AND is_default = true LIMIT 1"
        ),
        {"proj": proj_id},
    )
    assert isinstance(state_id, uuid.UUID)

    prio_id = await session.scalar(
        text(
            "SELECT id FROM project_priorities "
            "WHERE project_id = :proj AND is_default = true LIMIT 1"
        ),
        {"proj": proj_id},
    )
    assert isinstance(prio_id, uuid.UUID)

    # Issue
    seq = await session.scalar(text("SELECT allocate_issue_sequence(:proj)"), {"proj": proj_id})
    issue_ckey = f"{ident}-{seq}"
    issue_id = await session.scalar(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, 'Test Issue', :uid)"),
        {"ws": ws_id, "proj": proj_id, "ckey": issue_ckey, "uid": admin_id},
    )
    assert isinstance(issue_id, uuid.UUID)
    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  state_id, priority_id, created_by_id, original_created_by_id, board_rank"
            ") VALUES ("
            "  :id, :ws, :proj, :seq, 'Test Issue', "
            "  :state_id, :prio_id, :uid, :uid, '0|hzzzzz:'"
            ")"
        ),
        {
            "id": issue_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq,
            "state_id": state_id,
            "prio_id": prio_id,
            "uid": admin_id,
        },
    )

    # Role bindings
    for pid, role, scope, prj in (
        (admin_id, "PROJECT_ADMIN", "project", proj_id),
        (member_id, "MEMBER", "project", proj_id),
        (viewer_id, "VIEWER", "project", proj_id),
        (guest_id, "WORKSPACE_GUEST", "workspace", None),
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
        "issue_id": issue_id,
        "admin_id": admin_id,
        "member_id": member_id,
        "viewer_id": viewer_id,
        "guest_id": guest_id,
    }


@pytest.mark.asyncio
async def test_01_project_admin_creates_definitions_all_7_formats(
    db_session: AsyncSession,
) -> None:
    """Test 1: PROJECT_ADMIN with aal_level=2 creates definitions for all 7 output formats."""
    ids = await _setup_fixture(db_session)
    ws_id, proj_id, admin_id = ids["ws_id"], ids["proj_id"], ids["admin_id"]

    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, admin_id, ws_id)
    await db_session.execute(text("SELECT set_config('app.aal_level', '2', true)"))

    formats_and_meta: list[tuple[str, dict[str, Any]]] = [
        ("text", {"format": "text", "max_length": 140}),
        ("number", {"format": "number", "maximum_fraction_digits": 2}),
        ("badge", {"format": "badge", "color_token": "info"}),
        ("markdown_snippet", {"format": "markdown_snippet", "max_chars": 500}),
        ("url", {"format": "url", "allowed_schemes": ["https"]}),
        (
            "json_table",
            {
                "format": "json_table",
                "columns": [{"key": "col1", "label": "Column 1"}],
                "max_rows": 20,
            },
        ),
        ("severity_pill", {"format": "severity_pill"}),
    ]

    for fmt, meta in formats_and_meta:
        f_id = uuid.uuid4()
        slug = f"field-{fmt.replace('_', '-')}"
        source = f"export default function() {{ return '{fmt}'; }}"
        manifest = _manifest(source, fmt, meta)

        await db_session.execute(
            text(
                "INSERT INTO custom_field_definitions ("
                "  id, workspace_id, project_id, slug, name, tier, output_format, "
                "  output_format_metadata, script_source, script_version, target_scope, "
                "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, created_by_id"
                ") VALUES ("
                "  :id, :ws, :proj, :slug, :name, 'wasm', :fmt, "
                "  CAST(:meta AS jsonb), :source, 1, 'PROJECT', "
                "  'INVOKING_USER', '{}', :manifest, true, :uid"
                ")"
            ),
            {
                "id": f_id,
                "ws": ws_id,
                "proj": proj_id,
                "slug": slug,
                "name": f"Field {fmt}",
                "fmt": fmt,
                "meta": json.dumps(meta),
                "source": source,
                "manifest": manifest,
                "uid": admin_id,
            },
        )

        # Query back and verify 32-byte manifest and script_version == 1
        row = (
            await db_session.execute(
                text(
                    "SELECT script_version, octet_length(manifest_sha256) as m_len, "
                    "manifest_sha256 FROM custom_field_definitions WHERE id = :id"
                ),
                {"id": f_id},
            )
        ).one()
        assert row.script_version == 1
        assert row.m_len == 32
        assert row.manifest_sha256 == manifest


@pytest.mark.asyncio
async def test_02_rls_with_check_admin_only_gate(
    db_session: AsyncSession,
) -> None:
    """Test 2: Direct SQL INSERT/UPDATE fails for non-admins and admin with aal_level=1."""
    ids = await _setup_fixture(db_session)
    ws_id, proj_id, admin_id = ids["ws_id"], ids["proj_id"], ids["admin_id"]

    # First, under admin authority, seed one definition to test UPDATE on
    seed_id = uuid.uuid4()
    source = "export default function() { return 'seed'; }"
    meta = {"format": "text", "max_length": 100}
    manifest = _manifest(source, "text", meta)

    await db_session.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "  id, workspace_id, project_id, slug, name, tier, output_format, "
            "  output_format_metadata, script_source, script_version, target_scope, "
            "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, created_by_id"
            ") VALUES ("
            "  :id, :ws, :proj, 'seed-field', 'Seed Field', 'wasm', 'text', "
            "  CAST(:meta AS jsonb), :source, 1, 'PROJECT', "
            "  'INVOKING_USER', '{}', :manifest, true, :uid"
            ")"
        ),
        {
            "id": seed_id,
            "ws": ws_id,
            "proj": proj_id,
            "meta": json.dumps(meta),
            "source": source,
            "manifest": manifest,
            "uid": admin_id,
        },
    )

    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 1. Non-admin roles (MEMBER, VIEWER, GUEST) with AAL2 fail WITH CHECK on INSERT and UPDATE
    non_admins = [
        ("member_id", ids["member_id"]),
        ("viewer_id", ids["viewer_id"]),
        ("guest_id", ids["guest_id"]),
    ]
    for role_name, pid in non_admins:
        await bind_ctx(db_session, pid, ws_id)
        await db_session.execute(text("SELECT set_config('app.aal_level', '2', true)"))

        # Direct INSERT fails
        with pytest.raises(DBAPIError) as exc_info:
            async with db_session.begin_nested():
                await db_session.execute(
                    text(
                        "INSERT INTO custom_field_definitions ("
                        "  id, workspace_id, project_id, slug, name, tier, output_format, "
                        "  output_format_metadata, script_source, script_version, target_scope, "
                        "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, "
                        "  created_by_id"
                        ") VALUES ("
                        "  :id, :ws, :proj, :slug, 'Malicious Field', 'wasm', 'text', "
                        "  CAST(:meta AS jsonb), :source, 1, 'PROJECT', "
                        "  'INVOKING_USER', '{}', :manifest, true, :uid"
                        ")"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "ws": ws_id,
                        "proj": proj_id,
                        "slug": f"evil-{role_name}",
                        "meta": json.dumps(meta),
                        "source": source,
                        "manifest": manifest,
                        "uid": pid,
                    },
                )
        assert (
            "violates row-level security policy" in str(exc_info.value).lower()
            or "check" in str(exc_info.value).lower()
        )

        # Direct UPDATE fails (MEMBER/VIEWER fail WITH CHECK; GUEST cannot see row -> rowcount 0)
        if role_name == "guest_id":
            async with db_session.begin_nested():
                res = await db_session.execute(
                    text("UPDATE custom_field_definitions SET name = 'Hacked' WHERE id = :id"),
                    {"id": seed_id},
                )
                assert getattr(res, "rowcount", 0) == 0
        else:
            with pytest.raises(DBAPIError) as exc_info:
                async with db_session.begin_nested():
                    await db_session.execute(
                        text("UPDATE custom_field_definitions SET name = 'Hacked' WHERE id = :id"),
                        {"id": seed_id},
                    )
            assert (
                "violates row-level security policy" in str(exc_info.value).lower()
                or "check" in str(exc_info.value).lower()
            )

    # 2. PROJECT_ADMIN with app.aal_level = '1' fails WITH CHECK
    await bind_ctx(db_session, admin_id, ws_id)
    await db_session.execute(text("SELECT set_config('app.aal_level', '1', true)"))

    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO custom_field_definitions ("
                    "  id, workspace_id, project_id, slug, name, tier, output_format, "
                    "  output_format_metadata, script_source, script_version, target_scope, "
                    "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, "
                    "  created_by_id"
                    ") VALUES ("
                    "  :id, :ws, :proj, 'aal1-admin-field', 'Admin AAL1 Field', 'wasm', 'text', "
                    "  CAST(:meta AS jsonb), :source, 1, 'PROJECT', "
                    "  'INVOKING_USER', '{}', :manifest, true, :uid"
                    ")"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": ws_id,
                    "proj": proj_id,
                    "meta": json.dumps(meta),
                    "source": source,
                    "manifest": manifest,
                    "uid": admin_id,
                },
            )
    assert (
        "violates row-level security policy" in str(exc_info.value).lower()
        or "check" in str(exc_info.value).lower()
    )

    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE custom_field_definitions SET name = 'AAL1 Mutate' WHERE id = :id"),
                {"id": seed_id},
            )
    assert (
        "violates row-level security policy" in str(exc_info.value).lower()
        or "check" in str(exc_info.value).lower()
    )


@pytest.mark.asyncio
async def test_03_cache_isolation_rls(
    db_session: AsyncSession,
) -> None:
    """Test 4: custom_field_values row for User A's user_access_hash is invisible to User B."""
    ids = await _setup_fixture(db_session)
    ws_id, proj_id, issue_id = ids["ws_id"], ids["proj_id"], ids["issue_id"]
    admin_id, member_id, viewer_id = ids["admin_id"], ids["member_id"], ids["viewer_id"]

    # Seed custom field definition under admin
    field_id = uuid.uuid4()
    source = "export default function() { return 'val'; }"
    meta = {"format": "text", "max_length": 100}
    manifest = _manifest(source, "text", meta)

    await db_session.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "  id, workspace_id, project_id, slug, name, tier, output_format, "
            "  output_format_metadata, script_source, script_version, target_scope, "
            "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, created_by_id"
            ") VALUES ("
            "  :id, :ws, :proj, 'test-field', 'Test Field', 'wasm', 'text', "
            "  CAST(:meta AS jsonb), :source, 1, 'PROJECT', "
            "  'INVOKING_USER', '{}', :manifest, true, :uid"
            ")"
        ),
        {
            "id": field_id,
            "ws": ws_id,
            "proj": proj_id,
            "meta": json.dumps(meta),
            "source": source,
            "manifest": manifest,
            "uid": admin_id,
        },
    )

    user_a_hash = hashlib.sha256(b"user_a_secret_token_123").digest()
    user_b_hash = hashlib.sha256(b"user_b_secret_token_456").digest()

    val_a_id = uuid.uuid4()

    # User A inserts value under their user_access_hash
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, member_id, ws_id)
    await db_session.execute(
        text("SELECT set_config('app.user_access_hash', :hash, true)"),
        {"hash": user_a_hash.hex()},
    )

    await db_session.execute(
        text(
            "INSERT INTO custom_field_values ("
            "  id, workspace_id, project_id, issue_id, field_id, script_version, "
            "  user_access_hash, value_json, last_latency_ms, expires_at"
            ") VALUES ("
            "  :id, :ws, :proj, :issue, :field, 1, "
            "  :hash, '\"User A secret output\"'::jsonb, 12, clock_timestamp() + interval '1 hour'"
            ")"
        ),
        {
            "id": val_a_id,
            "ws": ws_id,
            "proj": proj_id,
            "issue": issue_id,
            "field": field_id,
            "hash": user_a_hash,
        },
    )

    # User A can query their own row
    count_a = await db_session.scalar(
        text("SELECT count(*) FROM custom_field_values WHERE id = :id"),
        {"id": val_a_id},
    )
    assert count_a == 1

    # Switch session context to User B with User B's access hash
    await bind_ctx(db_session, viewer_id, ws_id)
    await db_session.execute(
        text("SELECT set_config('app.user_access_hash', :hash, true)"),
        {"hash": user_b_hash.hex()},
    )

    # User B cannot see User A's row: exactly 0 rows returned
    count_b = await db_session.scalar(
        text("SELECT count(*) FROM custom_field_values WHERE id = :id"),
        {"id": val_a_id},
    )
    assert count_b == 0

    # User B also cannot update or delete User A's row
    del_res = await db_session.execute(
        text("DELETE FROM custom_field_values WHERE id = :id"),
        {"id": val_a_id},
    )
    assert getattr(del_res, "rowcount", 0) == 0

    # Shared unpartitioned cache row (empty bytea hash) is visible to User B
    val_shared_id = uuid.uuid4()
    await db_session.execute(text("RESET SESSION AUTHORIZATION"))
    await db_session.execute(
        text(
            "INSERT INTO custom_field_values ("
            "  id, workspace_id, project_id, issue_id, field_id, script_version, "
            "  user_access_hash, value_json, last_latency_ms, expires_at"
            ") VALUES ("
            "  :id, :ws, :proj, :issue, :field, 1, "
            "  ''::bytea, '\"Shared public output\"'::jsonb, 5, "
            "  clock_timestamp() + interval '1 hour'"
            ")"
        ),
        {
            "id": val_shared_id,
            "ws": ws_id,
            "proj": proj_id,
            "issue": issue_id,
            "field": field_id,
        },
    )

    # User B queries shared row -> returns 1
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_ctx(db_session, viewer_id, ws_id)
    await db_session.execute(
        text("SELECT set_config('app.user_access_hash', :hash, true)"),
        {"hash": user_b_hash.hex()},
    )
    count_shared = await db_session.scalar(
        text("SELECT count(*) FROM custom_field_values WHERE id = :id"),
        {"id": val_shared_id},
    )
    assert count_shared == 1
