"""Project API tests: CRUD, authorization discipline, module rules and contract capture."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from kanban.content import ContentNormalizeError
from kanban.security.permissions import Capability
from kanban.services.projects import decode_cursor, encode_cursor

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db

_VOLATILE_KEYS = frozenset({"request_id", "instance"})


def _strip(body: dict[str, Any]) -> dict[str, Any]:
    """Remove request-scoped members before comparing problem documents."""
    return {k: v for k, v in body.items() if k not in _VOLATILE_KEYS}


async def _count(env: ApiEnv, sql: str, **params: Any) -> int:  # noqa: ANN401
    """Return a scalar count from the committed seed session."""
    await env.seed.rollback()
    return int((await env.seed.execute(text(sql), params)).scalar_one())


async def test_case_1_admin_create_seeds_defaults_and_activity(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: POST 201 + Location, 5 states, 5 priorities (None default), 1 PROJECT_CREATED."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    resp = await client.post(
        "/api/v1/projects",
        json={"identifier": "KAN", "name": "  Platform Core  ", "description_markdown": "Hello"},
    )
    contract_recorder.record("create_project_201", resp.request, resp)
    assert resp.status_code == 201, resp.text
    assert resp.headers["Location"] == "/api/v1/projects/KAN"
    body = resp.json()
    assert body["identifier"] == "KAN"
    assert body["name"] == "Platform Core"
    assert body["modules_enabled"] is False
    assert body["skip_loaded_sequence_numbers"] is False
    assert body["default_module_ids"] == []
    assert body["auto_archive_days"] is None
    assert {"VIEW", "EDIT", "ADMIN"} <= set(body["capabilities"])
    assert body["access_manifest"]["inherited_scope"]["kind"] == "workspace"

    pid = body["id"]
    assert (
        await _count(api_env, "SELECT count(*) FROM workflow_states WHERE project_id = :p", p=pid)
        == 5
    )
    assert (
        await _count(
            api_env, "SELECT count(*) FROM project_priorities WHERE project_id = :p", p=pid
        )
        == 5
    )
    default_slug = (
        await api_env.seed.execute(
            text("SELECT slug FROM project_priorities WHERE project_id = :p AND is_default"),
            {"p": pid},
        )
    ).scalar_one()
    assert default_slug == "none"
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :p"
            " AND event_type = 'PROJECT_CREATED' AND payload = CAST(:pl AS jsonb)",
            p=pid,
            pl='{"identifier": "KAN"}',
        )
        == 1
    )
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM role_bindings WHERE project_id = :p AND role = 'PROJECT_ADMIN'",
            p=pid,
        )
        == 1
    )

    get_resp = await client.get("/api/v1/projects/KAN")
    contract_recorder.record("get_project_200", get_resp.request, get_resp)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == pid
    by_uuid = await client.get(f"/api/v1/projects/{pid}")
    assert by_uuid.status_code == 200


async def test_case_2_unreadable_404_and_viewer_patch_403(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: unreadable == absent (byte-identical body); VIEW-only PATCH is 403."""
    del api_env
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    viewer = await make_user("viewer")
    outsider = await make_user("outsider")
    await make_project("SEC", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    await make_project("OPEN", created_by=admin, roles={viewer: "VIEWER"})

    unreadable = await as_principal(outsider).get("/api/v1/projects/SEC")
    absent = await as_principal(outsider).get("/api/v1/projects/NOPE")
    contract_recorder.record("get_unreadable_404", unreadable.request, unreadable)
    assert unreadable.status_code == absent.status_code == 404
    assert _strip(unreadable.json()) == _strip(absent.json())
    assert unreadable.content.replace(unreadable.json()["request_id"].encode(), b"") == (
        absent.content.replace(absent.json()["request_id"].encode(), b"")
    )
    malformed = await as_principal(outsider).get("/api/v1/projects/not-a-ref!")
    assert malformed.status_code == 404
    assert _strip(malformed.json()) == _strip(absent.json())

    patch = await as_principal(viewer).patch("/api/v1/projects/OPEN", json={"name": "Renamed"})
    contract_recorder.record("patch_as_viewer_403", patch.request, patch)
    assert patch.status_code == 403
    assert patch.json()["code"] == "INSUFFICIENT_CAPABILITY"

    hidden_patch = await as_principal(outsider).patch("/api/v1/projects/SEC", json={"name": "X"})
    assert hidden_patch.status_code == 404


async def test_case_3_validation_and_conflict(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: bad identifiers 422, duplicate 409, unknown key 422."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    for bad in ("kan", "K", "KANBANPROJECT1"):
        resp = await client.post("/api/v1/projects", json={"identifier": bad, "name": "N"})
        if bad == "kan":
            contract_recorder.record("create_invalid_identifier_422", resp.request, resp)
        assert resp.status_code == 422
        assert resp.json()["code"] == "VALIDATION_FAILED"

    first = await client.post("/api/v1/projects", json={"identifier": "DUP", "name": "One"})
    assert first.status_code == 201
    second = await client.post("/api/v1/projects", json={"identifier": "DUP", "name": "Two"})
    contract_recorder.record("create_duplicate_409", second.request, second)
    assert second.status_code == 409
    assert second.json()["code"] == "PROJECT_IDENTIFIER_TAKEN"

    unknown = await client.post(
        "/api/v1/projects", json={"identifier": "UNK", "name": "N", "extra_key": 1}
    )
    assert unknown.status_code == 422
    blank = await client.post("/api/v1/projects", json={"identifier": "BLK", "name": "   "})
    assert blank.status_code == 422
    long_name = await client.post("/api/v1/projects", json={"identifier": "LNG", "name": "x" * 121})
    assert long_name.status_code == 422


async def test_case_4_boundaries(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 4: auto_archive_days 0/366 rejected, 1/365 accepted; limit 0/101 rejected."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    for bad in (0, 366):
        resp = await client.post(
            "/api/v1/projects", json={"identifier": "BAD", "name": "N", "auto_archive_days": bad}
        )
        assert resp.status_code == 422
    for ident, good in (("LOW", 1), ("HIGH", 365)):
        resp = await client.post(
            "/api/v1/projects", json={"identifier": ident, "name": "N", "auto_archive_days": good}
        )
        assert resp.status_code == 201
        assert resp.json()["auto_archive_days"] == good
    for bad_limit in (0, 101):
        resp = await client.get(f"/api/v1/projects?limit={bad_limit}")
        assert resp.status_code == 422


async def test_case_5_module_rules(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_module: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 5: MODULES_DISABLED, MODULE_NOT_IN_PROJECT, MODULES_IN_USE, success path."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    a = (await client.post("/api/v1/projects", json={"identifier": "MODA", "name": "A"})).json()
    b = (await client.post("/api/v1/projects", json={"identifier": "MODB", "name": "B"})).json()

    disabled = await client.put(
        "/api/v1/projects/MODA/module-defaults", json={"module_ids": [str(uuid.uuid4())]}
    )
    assert disabled.status_code == 422
    assert disabled.json()["code"] == "MODULES_DISABLED"

    for ident in ("MODA", "MODB"):
        enabled = await client.patch(f"/api/v1/projects/{ident}", json={"modules_enabled": True})
        assert enabled.status_code == 200
        assert enabled.json()["modules_enabled"] is True

    mod_a = await make_module(uuid.UUID(a["id"]), "alpha", created_by=admin)
    mod_b = await make_module(uuid.UUID(b["id"]), "beta", created_by=admin)

    foreign = await client.put(
        "/api/v1/projects/MODA/module-defaults", json={"module_ids": [str(mod_b)]}
    )
    assert foreign.status_code == 422
    assert foreign.json()["code"] == "MODULE_NOT_IN_PROJECT"

    ok = await client.put(
        "/api/v1/projects/MODA/module-defaults", json={"module_ids": [str(mod_a)]}
    )
    contract_recorder.record("put_module_defaults_200", ok.request, ok)
    assert ok.status_code == 200
    assert ok.json()["default_module_ids"] == [str(mod_a)]

    dup = await client.put(
        "/api/v1/projects/MODA/module-defaults", json={"module_ids": [str(mod_a), str(mod_a)]}
    )
    assert dup.status_code == 422
    too_many = await client.put(
        "/api/v1/projects/MODA/module-defaults",
        json={"module_ids": [str(uuid.uuid4()) for _ in range(21)]},
    )
    assert too_many.status_code == 422

    cleared = await client.put("/api/v1/projects/MODA/module-defaults", json={"module_ids": []})
    assert cleared.status_code == 200
    assert cleared.json()["default_module_ids"] == []

    in_use = await client.patch("/api/v1/projects/MODA", json={"modules_enabled": False})
    assert in_use.status_code == 409
    assert in_use.json()["code"] == "MODULES_IN_USE"


async def test_patch_semantics_and_activity(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """PATCH changes fields, records hashed description diffs, and rejects identifier edits."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    created = (
        await client.post(
            "/api/v1/projects",
            json={"identifier": "PAT", "name": "Old", "description_markdown": "old body"},
        )
    ).json()

    changed = await client.patch(
        "/api/v1/projects/PAT",
        json={
            "name": "New",
            "description_markdown": "new body",
            "auto_archive_days": 30,
            "skip_loaded_sequence_numbers": True,
        },
    )
    assert changed.status_code == 200
    assert changed.json()["name"] == "New"
    assert changed.json()["auto_archive_days"] == 30
    assert changed.json()["skip_loaded_sequence_numbers"] is True

    row = (
        await api_env.seed.execute(
            text(
                "SELECT payload FROM activity_records WHERE object_id = :p"
                " AND event_type = 'PROJECT_UPDATED'"
            ),
            {"p": created["id"]},
        )
    ).scalar_one()
    changes = row["changes"]
    assert changes["name"] == {"old": "Old", "new": "New"}
    assert changes["skip_loaded_sequence_numbers"] == {"old": False, "new": True}
    assert set(changes["description_markdown"]) == {"old_sha256", "new_sha256"}
    assert "new body" not in str(row)

    noop = await client.patch("/api/v1/projects/PAT", json={"name": "New"})
    assert noop.status_code == 200
    cleared = await client.patch("/api/v1/projects/PAT", json={"auto_archive_days": None})
    assert cleared.json()["auto_archive_days"] is None
    assert (
        await _count(
            api_env,
            "SELECT count(*) FROM activity_records WHERE object_id = :p"
            " AND event_type = 'PROJECT_UPDATED'",
            p=created["id"],
        )
        == 2
    )

    immutable = await client.patch("/api/v1/projects/PAT", json={"identifier": "ZZZ"})
    assert immutable.status_code == 422
    assert immutable.json()["code"] == "IDENTIFIER_IMMUTABLE"
    bad_key = await client.patch("/api/v1/projects/PAT", json={"nope": 1})
    assert bad_key.status_code == 422


async def test_description_too_large(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Oversized descriptions map to 422 DESCRIPTION_TOO_LARGE (create and patch)."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    huge = "a" * 600_000
    resp = await client.post(
        "/api/v1/projects", json={"identifier": "BIG", "name": "N", "description_markdown": huge}
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "DESCRIPTION_TOO_LARGE"
    way_too_big = "b" * 2_200_000
    resp = await client.post(
        "/api/v1/projects",
        json={"identifier": "BIG", "name": "N", "description_markdown": way_too_big},
    )
    assert resp.status_code in (413, 422)
    assert resp.json()["code"] in ("DESCRIPTION_TOO_LARGE", "PAYLOAD_TOO_LARGE")
    surrogate = await client.post(
        "/api/v1/projects",
        content=b'{"identifier": "BAD", "name": "N", "description_markdown": "x\\ud800y"}',
        headers={"Content-Type": "application/json"},
    )
    assert surrogate.status_code == 422


async def test_create_authorization(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Non-admins, narrow token scopes and OBO agents cannot create projects."""
    member = await make_user("member", workspace_role="WORKSPACE_MEMBER")
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    payload = {"identifier": "NOPE", "name": "N"}

    denied = await as_principal(member).post("/api/v1/projects", json=payload)
    assert denied.status_code == 403
    assert denied.json()["code"] == "INSUFFICIENT_CAPABILITY"

    narrow = await as_principal(admin, scopes=("write",)).post("/api/v1/projects", json=payload)
    assert narrow.status_code == 403

    obo = await as_principal(admin, agent_principal_id=admin.id).post(
        "/api/v1/projects", json=payload
    )
    assert obo.status_code == 403

    unauth = await as_principal(admin).get("/api/v1/projects/NOPE")
    assert unauth.status_code == 404


async def test_list_pagination_and_cursor(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Keyset pagination returns stable pages, hides unreadable projects and rejects bad cursors."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    outsider = await make_user("outsider")
    client = as_principal(admin)
    for ident in ("AAA", "BBB", "CCC"):
        assert (
            await client.post("/api/v1/projects", json={"identifier": ident, "name": ident})
        ).status_code == 201

    page1 = (await client.get("/api/v1/projects?limit=2")).json()
    assert [p["identifier"] for p in page1["items"]] == ["AAA", "BBB"]
    assert page1["next_cursor"] is not None
    page2 = (await client.get(f"/api/v1/projects?limit=2&cursor={page1['next_cursor']}")).json()
    assert [p["identifier"] for p in page2["items"]] == ["CCC"]
    assert page2["next_cursor"] is None

    hidden = (await as_principal(outsider).get("/api/v1/projects")).json()
    assert hidden == {"items": [], "next_cursor": None}

    as_principal(admin)
    for bad in ("!!!notbase64", "bm9wZQ", "a" * 65):
        resp = await client.get(f"/api/v1/projects?cursor={bad}")
        assert resp.status_code == 422
        if bad != "a" * 65:
            assert resp.json()["code"] == "INVALID_CURSOR"


def test_cursor_round_trip_and_rejection() -> None:
    """Cursor helpers round-trip identifiers and reject non-identifier payloads."""
    assert decode_cursor(encode_cursor("KAN")) == "KAN"
    assert "=" not in encode_cursor("KAN")
    with pytest.raises(Exception, match="Invalid Cursor"):
        decode_cursor("bm9wZQ")


async def test_patch_unchanged_description_and_module_toggle(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No-op description patches record nothing; modules can toggle off when none exist."""
    admin = await make_user("admin", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)
    await client.post(
        "/api/v1/projects",
        json={
            "identifier": "TOG",
            "name": "N",
            "description_markdown": "same",
            "modules_enabled": True,
        },
    )
    same = await client.patch("/api/v1/projects/TOG", json={"description_markdown": "same"})
    assert same.status_code == 200
    off = await client.patch("/api/v1/projects/TOG", json={"modules_enabled": False})
    assert off.status_code == 200
    assert off.json()["modules_enabled"] is False

    def _boom(_raw: str) -> str:
        msg = "INVALID_UTF8_SURROGATE"
        raise ContentNormalizeError(msg)

    monkeypatch.setattr("kanban.services.projects.normalize_to_markdown", _boom)
    bad = await client.patch("/api/v1/projects/TOG", json={"description_markdown": "x"})
    assert bad.status_code == 422
    assert bad.json()["code"] == "INVALID_CONTENT"

    def _too_big(_raw: str) -> str:
        msg = "CONTENT_TOO_LARGE"
        raise ContentNormalizeError(msg)

    monkeypatch.setattr("kanban.services.projects.normalize_to_markdown", _too_big)
    bad_big = await client.patch("/api/v1/projects/TOG", json={"description_markdown": "x"})
    assert bad_big.status_code == 422
    assert bad_big.json()["code"] == "DESCRIPTION_TOO_LARGE"

    def _unicode_err(_raw: str) -> str:
        msg = "utf-8"
        raise UnicodeEncodeError(msg, "x", 0, 1, "surrogate")

    monkeypatch.setattr("kanban.services.projects.normalize_to_markdown", _unicode_err)
    bad_enc = await client.patch("/api/v1/projects/TOG", json={"description_markdown": "x"})
    assert bad_enc.status_code == 422
    assert bad_enc.json()["code"] == "INVALID_CONTENT"

    big_doc = "a" * (524288 + 1)
    monkeypatch.setattr("kanban.services.projects.normalize_to_markdown", lambda _x: big_doc)
    bad_cap = await client.patch("/api/v1/projects/TOG", json={"description_markdown": "x"})
    assert bad_cap.status_code == 422
    assert bad_cap.json()["code"] == "DESCRIPTION_TOO_LARGE"


async def test_project_members_endpoints(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify list, add, and remove project members endpoints with commit semantics."""
    admin = await make_user("admin_proj_mem", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("target_proj_mem", workspace_role="WORKSPACE_MEMBER")
    client = as_principal(admin)

    # 1. Create project
    resp_create = await client.post(
        "/api/v1/projects",
        json={"identifier": "PMEM", "name": "Project Members Test"},
    )
    assert resp_create.status_code == 201

    # 2. List members initially
    resp_list = await client.get("/api/v1/projects/PMEM/members")
    assert resp_list.status_code == 200
    assert isinstance(resp_list.json(), list)

    # Nonexistent principal yields 404
    bad_resp = await client.post(
        "/api/v1/projects/PMEM/members",
        json={"principal_id": "00000000-0000-0000-0000-000000000000", "role": "MEMBER"},
    )
    assert bad_resp.status_code == 404

    # 3. Add member
    resp_add = await client.post(
        "/api/v1/projects/PMEM/members",
        json={"principal_id": str(member.id), "role": "MEMBER"},
    )
    assert resp_add.status_code == 201
    assert resp_add.json()["role"] == "MEMBER"

    # Update existing member role
    resp_update = await client.post(
        "/api/v1/projects/PMEM/members",
        json={"principal_id": str(member.id), "role": "PROJECT_ADMIN"},
    )
    assert resp_update.status_code == 201
    assert resp_update.json()["role"] == "PROJECT_ADMIN"

    # 4. Remove member
    resp_del = await client.delete(f"/api/v1/projects/PMEM/members/{member.id}")
    assert resp_del.status_code == 204


async def test_serialize_project_capability_fallbacks(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller without explicit role binding falls back through capability checks."""
    admin1 = await make_user("admin_p1", workspace_role="WORKSPACE_ADMIN")
    admin2 = await make_user("admin_p2", workspace_role="WORKSPACE_ADMIN")
    client1 = as_principal(admin1)
    await client1.post("/api/v1/projects", json={"identifier": "FALL", "name": "Fallback Test"})

    # admin2 has no explicit role_binding, but is workspace admin (Capability.ADMIN)
    client2 = as_principal(admin2)
    r1 = await client2.get("/api/v1/projects/FALL")
    assert r1.status_code == 200
    assert r1.json()["project_role"] == "PROJECT_ADMIN"

    # EDIT capability fallback
    async def _caps_edit(*_args: object, **_kwargs: object) -> Capability:
        return Capability.EDIT | Capability.VIEW

    monkeypatch.setattr("kanban.services.projects.evaluate_capabilities", _caps_edit)
    r2 = await client2.get("/api/v1/projects/FALL")
    assert r2.status_code == 200
    assert r2.json()["project_role"] == "MEMBER"

    # VIEW capability fallback
    async def _caps_view(*_args: object, **_kwargs: object) -> Capability:
        return Capability.VIEW

    monkeypatch.setattr("kanban.services.projects.evaluate_capabilities", _caps_view)
    r3 = await client2.get("/api/v1/projects/FALL")
    assert r3.status_code == 200
    assert r3.json()["project_role"] == "VIEWER"

    # None capability fallback
    async def _caps_none(*_args: object, **_kwargs: object) -> Capability:
        return Capability.NONE

    monkeypatch.setattr("kanban.services.projects.evaluate_capabilities", _caps_none)
    r4 = await client2.get("/api/v1/projects/FALL")
    assert r4.status_code == 200
    assert r4.json()["project_role"] is None


async def test_skip_loaded_sequences_inheritance_and_explicit_override(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify projects inherit default_skip_loaded_sequence_numbers or accept explicit overrides."""
    admin = await make_user("admin_seq_inherit", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # 1. Workspace default is False -> Project created without flag inherits False
    p1 = (
        await client.post(
            "/api/v1/projects",
            json={"identifier": "SEQ1", "name": "Default False Project"},
        )
    ).json()
    assert p1["skip_loaded_sequence_numbers"] is False

    # 2. Explicitly override with True on creation
    p2 = (
        await client.post(
            "/api/v1/projects",
            json={
                "identifier": "SEQ2",
                "name": "Explicit True Project",
                "skip_loaded_sequence_numbers": True,
            },
        )
    ).json()
    assert p2["skip_loaded_sequence_numbers"] is True

    # 3. Update workspace setting to True via direct SQL or admin endpoint
    await api_env.seed.execute(
        text(
            "INSERT INTO workspace_settings "
            "(workspace_id, display_name, default_skip_loaded_sequence_numbers) "
            "VALUES (:ws, 'Workspace', TRUE) "
            "ON CONFLICT (workspace_id) DO UPDATE SET default_skip_loaded_sequence_numbers = TRUE"
        ),
        {"ws": admin.workspace_id},
    )
    await api_env.seed.commit()

    # 4. New project created without flag now inherits True
    p3 = (
        await client.post(
            "/api/v1/projects",
            json={"identifier": "SEQ3", "name": "Inherit True Project"},
        )
    ).json()
    assert p3["skip_loaded_sequence_numbers"] is True

    # 5. Explicitly override with False even though workspace default is True
    p4 = (
        await client.post(
            "/api/v1/projects",
            json={
                "identifier": "SEQ4",
                "name": "Explicit False Project",
                "skip_loaded_sequence_numbers": False,
            },
        )
    ).json()
    assert p4["skip_loaded_sequence_numbers"] is False


async def test_skip_loaded_sequences_end_to_end_rest(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify creating issues via REST respects skip_loaded_sequence_numbers and logs audit."""
    admin = await make_user("admin_seq_e2e", workspace_role="WORKSPACE_ADMIN")
    client = as_principal(admin)

    # Create project with skip_loaded_sequence_numbers=True
    resp = await client.post(
        "/api/v1/projects",
        json={
            "identifier": "SAFE",
            "name": "Safe Sequences E2E",
            "skip_loaded_sequence_numbers": True,
        },
    )
    assert resp.status_code == 201
    proj_id = resp.json()["id"]

    # Advance sequence counter to 12
    await api_env.seed.execute(
        text("UPDATE projects SET issue_seq_counter = 12 WHERE id = :p"),
        {"p": proj_id},
    )
    await api_env.seed.commit()

    # Create issue via REST: next sequence would be 13, so it must skip 13 and become 14!
    issue_resp = await client.post(
        "/api/v1/projects/SAFE/issues",
        json={"summary": "Should skip 13 to 14"},
    )
    assert issue_resp.status_code == 201, issue_resp.text
    issue_body = issue_resp.json()
    assert issue_body["key"] == "SAFE-14"

    # Verify SEQUENCE_SKIPPED activity record was emitted
    skip_events = (
        (
            await api_env.seed.execute(
                text(
                    "SELECT payload FROM activity_records "
                    "WHERE workspace_id = :ws AND event_type = 'SEQUENCE_SKIPPED'"
                ),
                {"ws": admin.workspace_id},
            )
        )
        .scalars()
        .all()
    )
    assert len(skip_events) >= 1
    assert any(ev.get("skipped_sequences") == [13] for ev in skip_events)

    # Now disable skip_loaded_sequence_numbers on project via PATCH
    patch_resp = await client.patch(
        "/api/v1/projects/SAFE",
        json={"skip_loaded_sequence_numbers": False},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["skip_loaded_sequence_numbers"] is False

    # Advance sequence counter to 68
    await api_env.seed.execute(
        text("UPDATE projects SET issue_seq_counter = 68 WHERE id = :p"),
        {"p": proj_id},
    )
    await api_env.seed.commit()

    # Next issue should NOT skip 69
    issue69_resp = await client.post(
        "/api/v1/projects/SAFE/issues",
        json={"summary": "Should NOT skip 69"},
    )
    assert issue69_resp.status_code == 201
    assert issue69_resp.json()["key"] == "SAFE-69"

    # Invalid content with lone surrogates
    surrogate_body = (
        b'{"identifier": "SURR", "name": "Surrogate Test", '
        b'"description_markdown": "Bad \xed\xa0\x80 content"}'
    )
    bad_content = await client.post(
        "/api/v1/projects",
        content=surrogate_body,
        headers={"Content-Type": "application/json"},
    )
    assert bad_content.status_code == 422
    assert bad_content.json()["code"] == "INVALID_UTF8_SURROGATE"

    # Non-admin member viewing project with MEMBER and VIEWER roles
    member_user = await make_user("mem_view_user", workspace_role="WORKSPACE_MEMBER")
    mem_client = as_principal(member_user)

    # 1. Project with role binding as VIEWER
    await api_env.seed.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws, :pid, CAST('VIEWER' AS rbac_role), 'project', :proj)"
        ),
        {"ws": admin.workspace_id, "pid": member_user.id, "proj": proj_id},
    )
    await api_env.seed.commit()

    v_res = await mem_client.get("/api/v1/projects/SAFE")
    assert v_res.status_code == 200
    assert v_res.json()["project_role"] == "VIEWER"

    # 2. Update role binding to MEMBER
    await api_env.seed.execute(
        text(
            "UPDATE role_bindings SET role = CAST('MEMBER' AS rbac_role) "
            "WHERE project_id = :proj AND principal_id = :pid"
        ),
        {"proj": proj_id, "pid": member_user.id},
    )
    await api_env.seed.commit()

    m_res = await mem_client.get("/api/v1/projects/SAFE")
    assert m_res.status_code == 200
    assert m_res.json()["project_role"] == "MEMBER"
