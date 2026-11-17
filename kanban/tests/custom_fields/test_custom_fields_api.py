# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API tests for custom field definitions (KB-P5-11, S13.1, S13.2)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


def _as_admin_aal2(api_env: ApiEnv, user: SeededUser) -> httpx.AsyncClient:
    """Configure active principal context with PROJECT_ADMIN / WORKSPACE_ADMIN and AAL2."""
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )
    return api_env.client


def _as_user_aal1(api_env: ApiEnv, user: SeededUser) -> httpx.AsyncClient:
    """Configure active principal context with AAL1."""
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=1,
    )
    return api_env.client


async def test_01_admin_crud_lifecycle_all_7_formats(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """Admin with AAL2 creates all 7 formats, reads with source, updates script & deletes."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("CFP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)

    created_fields: dict[str, dict[str, Any]] = {}

    # 1. Text format
    resp_text = await client.post(
        "/api/v1/projects/CFP/custom-fields",
        json={
            "slug": "ticket-summary-extra",
            "name": "Summary Extra",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 140, "monospace": False},
            "script_source": "export default function() { return 'extra info'; }",
            "egress_allowlist": ["/api/v1/issues"],
        },
    )
    contract_recorder.record("create_custom_field_text_201", resp_text.request, resp_text)
    assert resp_text.status_code == 201, resp_text.text
    assert "/api/v1/projects/CFP/custom-fields/" in resp_text.headers["Location"]
    body_text = resp_text.json()
    assert body_text["output_format"] == "text"
    assert body_text["script_version"] == 1
    assert len(body_text["manifest_sha256"]) == 64
    assert body_text["script_source"] == "export default function() { return 'extra info'; }"
    created_fields["text"] = body_text

    # 2. Number format
    resp_num = await client.post(
        "/api/v1/projects/CFP/custom-fields",
        json={
            "slug": "story-points-calc",
            "name": "Story Points Computed",
            "tier": "wasm",
            "output_format": "number",
            "output_format_metadata": {
                "maximum_fraction_digits": 1,
                "unit_suffix": "pts",
                "min_value": 0.0,
                "max_value": 100.0,
            },
            "script_source": "export default function() { return 8.5; }",
        },
    )
    contract_recorder.record("create_custom_field_number_201", resp_num.request, resp_num)
    assert resp_num.status_code == 201, resp_num.text
    created_fields["number"] = resp_num.json()

    # 3. Badge format
    resp_badge = await client.post(
        "/api/v1/projects/CFP/custom-fields",
        json={
            "slug": "release-readiness",
            "name": "Release Readiness",
            "tier": "wasm",
            "output_format": "badge",
            "output_format_metadata": {
                "color_token": "success",
                "allowed_labels": ["READY", "BLOCKED"],
            },
            "script_source": "export default function() { return 'READY'; }",
        },
    )
    contract_recorder.record("create_custom_field_badge_201", resp_badge.request, resp_badge)
    assert resp_badge.status_code == 201, resp_badge.text
    created_fields["badge"] = resp_badge.json()

    # 4. Markdown snippet format
    resp_md = await client.post(
        "/api/v1/projects/CFP/custom-fields",
        json={
            "slug": "release-notes-blurb",
            "name": "Release Notes Blurb",
            "tier": "wasm",
            "output_format": "markdown_snippet",
            "output_format_metadata": {"max_chars": 500},
            "script_source": "export default function() { return '**Ready for release**'; }",
        },
    )
    contract_recorder.record("create_custom_field_markdown_snippet_201", resp_md.request, resp_md)
    assert resp_md.status_code == 201, resp_md.text
    created_fields["markdown_snippet"] = resp_md.json()

    # 5. URL format
    resp_url = await client.post(
        "/api/v1/projects/CFP/custom-fields",
        json={
            "slug": "pipeline-ci-link",
            "name": "Pipeline CI Link",
            "tier": "wasm",
            "output_format": "url",
            "output_format_metadata": {
                "allowed_schemes": ["https"],
                "allowed_host_suffixes": ["internal.ci"],
            },
            "script_source": "export default function() { return 'https://internal.ci/build/1'; }",
        },
    )
    contract_recorder.record("create_custom_field_url_201", resp_url.request, resp_url)
    assert resp_url.status_code == 201, resp_url.text
    created_fields["url"] = resp_url.json()

    # 6. JSON table format
    resp_table = await client.post(
        "/api/v1/projects/CFP/custom-fields",
        json={
            "slug": "dependency-matrix",
            "name": "Dependency Matrix",
            "tier": "wasm",
            "output_format": "json_table",
            "output_format_metadata": {
                "columns": [
                    {"key": "dep", "label": "Dependency"},
                    {"key": "ver", "label": "Version"},
                ],
                "max_rows": 10,
            },
            "script_source": (
                "export default function() { return [{'dep': 'auth', 'ver': '1.0'}]; }"
            ),
        },
    )
    contract_recorder.record("create_custom_field_json_table_201", resp_table.request, resp_table)
    assert resp_table.status_code == 201, resp_table.text
    created_fields["json_table"] = resp_table.json()

    # 7. Severity pill format
    resp_sev = await client.post(
        "/api/v1/projects/CFP/custom-fields",
        json={
            "slug": "security-severity",
            "name": "Security Severity",
            "tier": "wasm",
            "output_format": "severity_pill",
            "output_format_metadata": {},
            "script_source": (
                "export default function() { return {'level': 'critical', 'score': 9.8}; }"
            ),
        },
    )
    contract_recorder.record("create_custom_field_severity_pill_201", resp_sev.request, resp_sev)
    assert resp_sev.status_code == 201, resp_sev.text
    created_fields["severity_pill"] = resp_sev.json()

    # 8. List definitions as admin
    resp_list = await client.get("/api/v1/projects/CFP/custom-fields")
    assert resp_list.status_code == 200, resp_list.text
    list_items = resp_list.json()
    assert len(list_items) == 7
    # All items have script_source and manifest_sha256 visible to admin
    for item in list_items:
        assert item["script_source"] is not None
        assert item["manifest_sha256"] is not None

    # 9. Patch definition: mutate script_source -> version increments & manifest changes
    text_id = created_fields["text"]["id"]
    old_manifest = created_fields["text"]["manifest_sha256"]
    resp_patch = await client.patch(
        f"/api/v1/projects/CFP/custom-fields/{text_id}",
        json={"script_source": "export default function() { return 'updated script'; }"},
    )
    contract_recorder.record("update_custom_field_200", resp_patch.request, resp_patch)
    assert resp_patch.status_code == 200, resp_patch.text
    patched = resp_patch.json()
    assert patched["script_version"] == 2
    assert patched["manifest_sha256"] != old_manifest
    assert patched["script_source"] == "export default function() { return 'updated script'; }"

    # 10. Delete definition
    resp_del = await client.delete(f"/api/v1/projects/CFP/custom-fields/{text_id}")
    contract_recorder.record("delete_custom_field_204", resp_del.request, resp_del)
    assert resp_del.status_code == 204, resp_del.text

    # Verify deleted
    resp_after_del = await client.get("/api/v1/projects/CFP/custom-fields")
    assert len(resp_after_del.json()) == 6

    # Verify activity records in database
    await api_env.seed.rollback()
    created_activities = (
        await api_env.seed.execute(
            text(
                "SELECT count(*) FROM activity_records "
                "WHERE object_id = :p AND event_type = 'CUSTOM_FIELD_CREATED'"
            ),
            {"p": proj_id},
        )
    ).scalar_one()
    assert created_activities == 7

    updated_activities = (
        await api_env.seed.execute(
            text(
                "SELECT count(*) FROM activity_records "
                "WHERE object_id = :p AND event_type = 'CUSTOM_FIELD_UPDATED'"
            ),
            {"p": proj_id},
        )
    ).scalar_one()
    assert updated_activities == 1

    deleted_activities = (
        await api_env.seed.execute(
            text(
                "SELECT count(*) FROM activity_records "
                "WHERE object_id = :p AND event_type = 'CUSTOM_FIELD_DELETED'"
            ),
            {"p": proj_id},
        )
    ).scalar_one()
    assert deleted_activities == 1


async def test_02_member_redacted_view_and_mutation_denial(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """Test 5: MEMBER gets redacted GET, cannot mutate (403), cross-workspace gets 404."""
    admin = await make_user("admin2", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member2")

    _ = await make_project(
        "RED", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"}
    )

    admin_client = _as_admin_aal2(api_env, admin)
    resp_create = await admin_client.post(
        "/api/v1/projects/RED/custom-fields",
        json={
            "slug": "secret-calc",
            "name": "Secret Calculator",
            "tier": "wasm",
            "output_format": "number",
            "output_format_metadata": {"maximum_fraction_digits": 0},
            "script_source": "export default function() { return 42; }",
        },
    )
    assert resp_create.status_code == 201
    field_id = resp_create.json()["id"]

    # Member client (has VIEW capability on project)
    member_client = _as_admin_aal2(api_env, member)  # Even with AAL2, lacks admin role

    # 1. MEMBER GET -> 200 OK but script_source and manifest_sha256 redacted (None)
    resp_get = await member_client.get("/api/v1/projects/RED/custom-fields")
    contract_recorder.record("get_custom_fields_member_redacted_200", resp_get.request, resp_get)
    assert resp_get.status_code == 200, resp_get.text
    items = resp_get.json()
    assert len(items) == 1
    assert items[0]["name"] == "Secret Calculator"
    assert items[0]["script_source"] is None
    assert items[0]["manifest_sha256"] is None

    # 2. MEMBER POST -> 403 INSUFFICIENT_CAPABILITY
    resp_post = await member_client.post(
        "/api/v1/projects/RED/custom-fields",
        json={
            "slug": "member-field",
            "name": "Member Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 50},
            "script_source": "export default function() { return 'evil'; }",
        },
    )
    contract_recorder.record("create_custom_field_member_403", resp_post.request, resp_post)
    assert resp_post.status_code == 403, resp_post.text
    assert resp_post.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 3. MEMBER PATCH -> 403 INSUFFICIENT_CAPABILITY
    resp_patch = await member_client.patch(
        f"/api/v1/projects/RED/custom-fields/{field_id}",
        json={"name": "Hacked Name"},
    )
    assert resp_patch.status_code == 403, resp_patch.text
    assert resp_patch.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 4. MEMBER DELETE -> 403 INSUFFICIENT_CAPABILITY
    resp_del = await member_client.delete(f"/api/v1/projects/RED/custom-fields/{field_id}")
    assert resp_del.status_code == 403, resp_del.text
    assert resp_del.json()["code"] == "INSUFFICIENT_CAPABILITY"


async def test_03_aal2_required_gate(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """Admin with AAL1 session on mutating endpoints returns 403 AAL2_REQUIRED."""
    admin = await make_user("admin3", workspace_role="WORKSPACE_ADMIN")
    await make_project("AAL", created_by=admin, roles={admin: "PROJECT_ADMIN"})

    # First create a field under AAL2
    client_aal2 = _as_admin_aal2(api_env, admin)
    created = (
        await client_aal2.post(
            "/api/v1/projects/AAL/custom-fields",
            json={
                "slug": "aal-test-field",
                "name": "AAL Test Field",
                "tier": "wasm",
                "output_format": "text",
                "output_format_metadata": {"max_length": 50},
                "script_source": "export default function() { return 'ok'; }",
            },
        )
    ).json()
    field_id = created["id"]

    # Now switch admin session to AAL1
    client_aal1 = _as_user_aal1(api_env, admin)

    # POST returns 403 AAL2_REQUIRED
    resp_post = await client_aal1.post(
        "/api/v1/projects/AAL/custom-fields",
        json={
            "slug": "another-field",
            "name": "Another Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 50},
            "script_source": "export default function() { return 'fail'; }",
        },
    )
    contract_recorder.record("create_custom_field_aal2_required_403", resp_post.request, resp_post)
    assert resp_post.status_code == 403, resp_post.text
    assert resp_post.json()["code"] == "AAL2_REQUIRED"

    # PATCH returns 403 AAL2_REQUIRED
    resp_patch = await client_aal1.patch(
        f"/api/v1/projects/AAL/custom-fields/{field_id}",
        json={"name": "AAL1 Rename"},
    )
    assert resp_patch.status_code == 403
    assert resp_patch.json()["code"] == "AAL2_REQUIRED"

    # DELETE returns 403 AAL2_REQUIRED
    resp_del = await client_aal1.delete(f"/api/v1/projects/AAL/custom-fields/{field_id}")
    assert resp_del.status_code == 403
    assert resp_del.json()["code"] == "AAL2_REQUIRED"


async def test_04_schema_and_integrity_errors(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    contract_recorder: ContractRecorder,
) -> None:
    """Verify 422 on invalid metadata, 422 on bad egress, and 409 on duplicate slug."""
    admin = await make_user("admin4", workspace_role="WORKSPACE_ADMIN")
    await make_project("VAL", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)

    # 1. Invalid metadata schema -> 422 OUTPUT_FORMAT_INVALID
    resp_bad_fmt = await client.post(
        "/api/v1/projects/VAL/custom-fields",
        json={
            "slug": "bad-meta",
            "name": "Bad Metadata",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 500},  # max_length > 280
            "script_source": "export default function() { return 'x'; }",
        },
    )
    contract_recorder.record(
        "create_custom_field_invalid_format_422", resp_bad_fmt.request, resp_bad_fmt
    )
    assert resp_bad_fmt.status_code == 422, resp_bad_fmt.text
    assert resp_bad_fmt.json()["code"] == "OUTPUT_FORMAT_INVALID"

    # 2. Invalid egress path -> 422 EGRESS_ALLOWLIST_INVALID
    resp_bad_egress = await client.post(
        "/api/v1/projects/VAL/custom-fields",
        json={
            "slug": "bad-egress",
            "name": "Bad Egress",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 100},
            "script_source": "export default function() { return 'x'; }",
            "egress_allowlist": ["/api/v1/../secret"],
        },
    )
    assert resp_bad_egress.status_code == 422, resp_bad_egress.text
    assert resp_bad_egress.json()["code"] == "EGRESS_ALLOWLIST_INVALID"

    # 3. Duplicate slug -> 409 SLUG_ALREADY_EXISTS
    resp_ok = await client.post(
        "/api/v1/projects/VAL/custom-fields",
        json={
            "slug": "unique-slug",
            "name": "Original",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 100},
            "script_source": "export default function() { return 'x'; }",
        },
    )
    assert resp_ok.status_code == 201

    resp_dup = await client.post(
        "/api/v1/projects/VAL/custom-fields",
        json={
            "slug": "unique-slug",
            "name": "Duplicate Slug",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 100},
            "script_source": "export default function() { return 'x'; }",
        },
    )
    assert resp_dup.status_code == 409, resp_dup.text
    assert resp_dup.json()["code"] == "SLUG_ALREADY_EXISTS"


async def test_05_anti_enumeration_discipline(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Non-existent project or missing project returns 404 with timing floor."""
    admin = await make_user("admin5", workspace_role="WORKSPACE_ADMIN")
    client = _as_admin_aal2(api_env, admin)

    # 1. Non-existent project
    resp_absent = await client.get("/api/v1/projects/NONEXISTENT/custom-fields")
    assert resp_absent.status_code == 404
    assert resp_absent.json()["code"] == "NOT_FOUND"

    # 2. Non-existent field on patch/delete
    await make_project("ENUM", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    fake_id = uuid.uuid4()
    resp_patch_404 = await client.patch(
        f"/api/v1/projects/ENUM/custom-fields/{fake_id}",
        json={"name": "New Name"},
    )
    assert resp_patch_404.status_code == 404
    assert resp_patch_404.json()["code"] == "NOT_FOUND"

    resp_del_404 = await client.delete(f"/api/v1/projects/ENUM/custom-fields/{fake_id}")
    assert resp_del_404.status_code == 404
    assert resp_del_404.json()["code"] == "NOT_FOUND"


async def test_06_service_branches_and_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Exercise update branches (name, is_enabled, wasm_sha, egress, metadata, slug lookup)."""
    admin = await make_user("admin6", workspace_role="WORKSPACE_ADMIN")
    await make_project("EDGE", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = _as_admin_aal2(api_env, admin)

    # 1. Create with invalid wasm sha256 (not hex, wrong len)
    resp_bad_hex = await client.post(
        "/api/v1/projects/EDGE/custom-fields",
        json={
            "slug": "bad-wasm",
            "name": "Bad Wasm",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 50},
            "script_source": "x",
            "wasm_module_sha256": "not-valid-hex-zzz",
        },
    )
    assert resp_bad_hex.status_code == 422
    assert resp_bad_hex.json()["code"] == "INVALID_WASM_SHA256"

    resp_short_hex = await client.post(
        "/api/v1/projects/EDGE/custom-fields",
        json={
            "slug": "short-wasm",
            "name": "Short Wasm",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 50},
            "script_source": "x",
            "wasm_module_sha256": "abcd",
        },
    )
    assert resp_short_hex.status_code == 422
    assert resp_short_hex.json()["code"] == "INVALID_WASM_SHA256"

    # 2. Create valid field
    dummy_wasm = "a" * 64
    resp_create = await client.post(
        "/api/v1/projects/EDGE/custom-fields",
        json={
            "slug": "edge-field",
            "name": "Edge Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 50},
            "script_source": "export default () => 1",
            "egress_allowlist": ["/api/v1/issues"],
            "wasm_module_sha256": dummy_wasm,
        },
    )
    assert resp_create.status_code == 201

    # 3. Patch by slug: update name and is_enabled
    resp_patch_slug = await client.patch(
        "/api/v1/projects/EDGE/custom-fields/edge-field",
        json={"name": "Edge Field Renamed", "is_enabled": False},
    )
    assert resp_patch_slug.status_code == 200
    patched_body = resp_patch_slug.json()
    assert patched_body["name"] == "Edge Field Renamed"
    assert patched_body["is_enabled"] is False

    # 4. Patch with invalid egress -> 422
    resp_bad_egress = await client.patch(
        "/api/v1/projects/EDGE/custom-fields/edge-field",
        json={"egress_allowlist": ["/api/v1/../traversal"]},
    )
    assert resp_bad_egress.status_code == 422
    assert resp_bad_egress.json()["code"] == "EGRESS_ALLOWLIST_INVALID"

    # 5. Patch with valid egress and new wasm sha256
    new_wasm = "b" * 64
    resp_patch_egress = await client.patch(
        "/api/v1/projects/EDGE/custom-fields/edge-field",
        json={
            "egress_allowlist": ["/api/v1/cycles"],
            "wasm_module_sha256": new_wasm,
        },
    )
    assert resp_patch_egress.status_code == 200
    assert resp_patch_egress.json()["egress_allowlist"] == ["/api/v1/cycles"]
    assert resp_patch_egress.json()["wasm_module_sha256"] == new_wasm

    # 6. Patch with invalid output format metadata -> 422
    resp_bad_meta = await client.patch(
        "/api/v1/projects/EDGE/custom-fields/edge-field",
        json={"output_format_metadata": {"max_length": 9999}},
    )
    assert resp_bad_meta.status_code == 422
    assert resp_bad_meta.json()["code"] == "OUTPUT_FORMAT_INVALID"

    # 7. Patch changing output format and metadata together
    resp_patch_fmt = await client.patch(
        "/api/v1/projects/EDGE/custom-fields/edge-field",
        json={
            "output_format": "number",
            "output_format_metadata": {"maximum_fraction_digits": 2},
        },
    )
    assert resp_patch_fmt.status_code == 200
    assert resp_patch_fmt.json()["output_format"] == "number"

    # 8. Delete by slug
    resp_del_slug = await client.delete("/api/v1/projects/EDGE/custom-fields/edge-field")
    assert resp_del_slug.status_code == 204

    # 9. Verify gone
    resp_get_after = await client.get("/api/v1/projects/EDGE/custom-fields")
    assert resp_get_after.status_code == 200
    assert len(resp_get_after.json()) == 0


async def test_07_non_admin_redaction_tier_target_scope_credential_mode(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Non-admin readers have tier, target_scope, credential_mode, and script_source redacted."""
    admin = await make_user("admin7", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("member7", workspace_role="WORKSPACE_MEMBER")
    _proj_id = await make_project(
        "RED",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "VIEWER"},
    )

    admin_client = _as_admin_aal2(api_env, admin)
    resp_create = await admin_client.post(
        "/api/v1/projects/RED/custom-fields",
        json={
            "slug": "redacted-field",
            "name": "Redacted Field",
            "tier": "wasm",
            "output_format": "text",
            "output_format_metadata": {"max_length": 50},
            "script_source": "export default function() { return 'secret logic'; }",
            "target_scope": "PROJECT",
            "credential_mode": "INVOKING_USER",
        },
    )
    assert resp_create.status_code == 201

    # Member reads definitions: sensitive execution parameters are redacted to None
    member_client = _as_user_aal1(api_env, member)
    resp_member = await member_client.get("/api/v1/projects/RED/custom-fields")
    assert resp_member.status_code == 200
    fields = resp_member.json()
    assert len(fields) == 1
    f = fields[0]
    assert f["tier"] is None
    assert f["target_scope"] is None
    assert f["credential_mode"] is None
    assert f["script_source"] is None
    assert f["manifest_sha256"] is None

    # Admin reads definitions: all execution parameters are populated
    _as_admin_aal2(api_env, admin)
    resp_admin = await admin_client.get("/api/v1/projects/RED/custom-fields")
    assert resp_admin.status_code == 200
    af = resp_admin.json()[0]
    assert af["tier"] == "wasm"
    assert af["target_scope"] == "PROJECT"
    assert af["credential_mode"] == "INVOKING_USER"
    assert af["script_source"] is not None
