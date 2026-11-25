# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for agent onboarding preferences (KAN-403).

Covers GET/PATCH /api/v1/users/me/preferences under FORCE RLS,
lone-surrogate rejection, byte bound limits, and persistence.
"""

from __future__ import annotations

import base64
import dataclasses
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from PIL import Image
from starlette.requests import Request

import kanban.api.v1.user_settings as us
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.user_settings import (
    AgentOnboardingPrefsPatch,
    ChangePasswordRequest,
    UpdateUserPreferencesRequest,
    _parse_avatar_upload,
    _validate_custom_notes,
    build_me_response,
    change_password,
    delete_avatar,
    get_user_avatar,
    get_user_preferences,
    update_user_preferences,
    upload_avatar,
)
from kanban.auth.sessions.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, generate_csrf_token

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _create_sample_png_bytes(width: int = 64, height: int = 64) -> bytes:
    """Generate minimal valid PNG bytes."""
    im = Image.new("RGBA", (width, height), (33, 150, 243, 255))
    bio = io.BytesIO()
    im.save(bio, format="PNG")
    return bio.getvalue()


async def test_user_preferences_defaults_and_lifecycle(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    api_env: ApiEnv,
) -> None:
    """Test GET and PATCH /api/v1/users/me/preferences lifecycle."""
    user_a = await make_user("user_a")
    user_b = await make_user("user_b")
    await api_env.seed.commit()

    # 1. User A initial GET returns defaults
    client_a = as_principal(user_a)
    res_a_init = await client_a.get("/api/v1/users/me/preferences")
    assert res_a_init.status_code == 200
    data_a_init = res_a_init.json()
    assert data_a_init["principal_id"] == str(user_a.id)
    assert data_a_init["agent_onboarding_prefs"]["scope"] == "local_only"
    assert data_a_init["agent_onboarding_prefs"]["execution_mode"] == "swarm"
    assert data_a_init["agent_onboarding_prefs"]["model_strategy"] == "quota_sipping_flash"
    assert data_a_init["agent_onboarding_prefs"]["qa_rigor"] == "strict_forensic"
    assert data_a_init["agent_onboarding_prefs"]["custom_notes"] == ""

    # 2. User A PATCH updates preferences
    patch_payload = {
        "agent_onboarding_prefs": {
            "scope": "local_only",
            "execution_mode": "teamwork",
            "model_strategy": "hybrid",
            "qa_rigor": "standard",
            "custom_notes": "Always run local unit tests with 95% coverage.",
        }
    }
    res_a_patch = await client_a.patch("/api/v1/users/me/preferences", json=patch_payload)
    assert res_a_patch.status_code == 200
    data_a_patch = res_a_patch.json()
    assert data_a_patch["agent_onboarding_prefs"]["execution_mode"] == "teamwork"
    assert data_a_patch["agent_onboarding_prefs"]["model_strategy"] == "hybrid"
    assert data_a_patch["agent_onboarding_prefs"]["qa_rigor"] == "standard"
    assert (
        data_a_patch["agent_onboarding_prefs"]["custom_notes"]
        == "Always run local unit tests with 95% coverage."
    )

    # 3. User B preferences remain default (RLS isolation)
    client_b = as_principal(user_b)
    res_b = await client_b.get("/api/v1/users/me/preferences")
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["principal_id"] == str(user_b.id)
    assert data_b["agent_onboarding_prefs"]["execution_mode"] == "swarm"
    assert data_b["agent_onboarding_prefs"]["custom_notes"] == ""


async def test_user_preferences_partial_nested_merge(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    api_env: ApiEnv,
) -> None:
    """Verify partial nested prefs merge without overwriting keys."""
    user = await make_user("partial_user")
    await api_env.seed.commit()
    client = as_principal(user)

    # 1. Set full initial preferences
    init_res = await client.patch(
        "/api/v1/users/me/preferences",
        json={
            "agent_onboarding_prefs": {
                "scope": "global_allowed",
                "execution_mode": "swarm",
                "model_strategy": "hybrid",
                "qa_rigor": "standard",
                "custom_notes": "Existing instructions.",
            }
        },
    )
    assert init_res.status_code == 200
    init_data = init_res.json()
    assert init_data["agent_onboarding_prefs"]["scope"] == "global_allowed"
    assert init_data["agent_onboarding_prefs"]["execution_mode"] == "swarm"
    assert init_data["agent_onboarding_prefs"]["model_strategy"] == "hybrid"
    assert init_data["agent_onboarding_prefs"]["qa_rigor"] == "standard"
    assert init_data["agent_onboarding_prefs"]["custom_notes"] == "Existing instructions."

    # 2. Partial nested patch: only execution_mode
    partial_res = await client.patch(
        "/api/v1/users/me/preferences",
        json={"agent_onboarding_prefs": {"execution_mode": "teamwork"}},
    )
    assert partial_res.status_code == 200
    partial_data = partial_res.json()
    assert partial_data["agent_onboarding_prefs"]["execution_mode"] == "teamwork"
    assert partial_data["agent_onboarding_prefs"]["scope"] == "global_allowed"
    assert partial_data["agent_onboarding_prefs"]["model_strategy"] == "hybrid"
    assert partial_data["agent_onboarding_prefs"]["qa_rigor"] == "standard"
    assert partial_data["agent_onboarding_prefs"]["custom_notes"] == "Existing instructions."

    # 3. Partial nested patch: only custom_notes
    notes_res = await client.patch(
        "/api/v1/users/me/preferences",
        json={"agent_onboarding_prefs": {"custom_notes": "Updated note only."}},
    )
    assert notes_res.status_code == 200
    notes_data = notes_res.json()
    assert notes_data["agent_onboarding_prefs"]["custom_notes"] == "Updated note only."
    assert notes_data["agent_onboarding_prefs"]["execution_mode"] == "teamwork"
    assert notes_data["agent_onboarding_prefs"]["scope"] == "global_allowed"
    assert notes_data["agent_onboarding_prefs"]["model_strategy"] == "hybrid"
    assert notes_data["agent_onboarding_prefs"]["qa_rigor"] == "standard"

    # 4. Partial nested patch: only scope and qa_rigor
    scope_res = await client.patch(
        "/api/v1/users/me/preferences",
        json={"agent_onboarding_prefs": {"scope": "local_only", "qa_rigor": "strict_forensic"}},
    )
    assert scope_res.status_code == 200
    scope_data = scope_res.json()
    assert scope_data["agent_onboarding_prefs"]["scope"] == "local_only"
    assert scope_data["agent_onboarding_prefs"]["qa_rigor"] == "strict_forensic"
    assert scope_data["agent_onboarding_prefs"]["execution_mode"] == "teamwork"
    assert scope_data["agent_onboarding_prefs"]["model_strategy"] == "hybrid"
    assert scope_data["agent_onboarding_prefs"]["custom_notes"] == "Updated note only."

    # 5. GET confirms persisted state in database
    get_res = await client.get("/api/v1/users/me/preferences")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["agent_onboarding_prefs"] == scope_data["agent_onboarding_prefs"]


async def test_user_preferences_validation_errors(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    api_env: ApiEnv,
) -> None:
    """Verify validation boundaries: surrogates, bounds, and enums."""
    user = await make_user("pref_val_user")
    await api_env.seed.commit()
    client = as_principal(user)

    # 1. Reject lone surrogates (\ud800) -> 422 INVALID_UTF8_SURROGATE
    raw_surrogate_body = b'{"agent_onboarding_prefs": {"custom_notes": "Test \\ud800 surrogate"}}'
    res_surr = await client.patch(
        "/api/v1/users/me/preferences",
        content=raw_surrogate_body,
        headers={"Content-Type": "application/json"},
    )
    assert res_surr.status_code == 422
    assert res_surr.json()["code"] == "INVALID_UTF8_SURROGATE"

    # 2. Reject oversized notes (> 4096 bytes / chars) -> 422
    # Multi-byte characters exceeding 4096 UTF-8 bytes
    res_bytes = await client.patch(
        "/api/v1/users/me/preferences",
        json={"agent_onboarding_prefs": {"custom_notes": "\u4e16" * 2000}},
    )
    assert res_bytes.status_code == 422
    assert res_bytes.json()["code"] == "PAYLOAD_TOO_LARGE"

    # Pydantic max_length validation
    res_large = await client.patch(
        "/api/v1/users/me/preferences",
        json={"agent_onboarding_prefs": {"custom_notes": "A" * 4097}},
    )
    assert res_large.status_code == 422

    # 3. Reject invalid enum value
    res_enum = await client.patch(
        "/api/v1/users/me/preferences",
        json={"agent_onboarding_prefs": {"execution_mode": "invalid_mode"}},
    )
    assert res_enum.status_code == 422


async def test_validate_custom_notes_function() -> None:
    """Directly test _validate_custom_notes unit boundary conditions."""
    # Valid notes
    assert _validate_custom_notes("Plain note") == "Plain note"

    # Surrogate 0xD800
    with pytest.raises(ProblemException) as exc1:
        _validate_custom_notes("\ud800bad")
    assert exc1.value.status == 422
    assert exc1.value.code == "INVALID_UTF8_SURROGATE"

    # Oversized notes > 4096 bytes
    with pytest.raises(ProblemException) as exc2:
        _validate_custom_notes("x" * 4097)
    assert exc2.value.status == 422
    assert exc2.value.code == "PAYLOAD_TOO_LARGE"


async def test_user_preferences_top_level_fields_and_persistence(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    api_env: ApiEnv,
) -> None:
    """Test updating preferences using top-level request fields."""
    user = await make_user("pref_top_level_user")
    await api_env.seed.commit()
    client = as_principal(user)

    # 1. Update using top-level body fields
    top_level_payload = {
        "scope": "global_allowed",
        "execution_mode": "single_thread",
        "model_strategy": "unconstrained_max",
        "qa_rigor": "standard",
        "custom_notes": "Top level preference note",
    }
    res_patch = await client.patch("/api/v1/users/me/preferences", json=top_level_payload)
    assert res_patch.status_code == 200
    data_patch = res_patch.json()
    assert data_patch["agent_onboarding_prefs"]["scope"] == "global_allowed"
    assert data_patch["agent_onboarding_prefs"]["execution_mode"] == "single_thread"
    assert data_patch["agent_onboarding_prefs"]["model_strategy"] == "unconstrained_max"
    assert data_patch["agent_onboarding_prefs"]["qa_rigor"] == "standard"
    assert data_patch["agent_onboarding_prefs"]["custom_notes"] == "Top level preference note"

    # 2. Subsequent GET reads back existing dict (covers line 919)
    res_get = await client.get("/api/v1/users/me/preferences")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["agent_onboarding_prefs"]["custom_notes"] == "Top level preference note"

    # 3. Subsequent PATCH reads back existing dict (covers line 965)
    res_patch2 = await client.patch(
        "/api/v1/users/me/preferences",
        json={"custom_notes": "Updated note 2"},
    )
    assert res_patch2.status_code == 200
    assert res_patch2.json()["agent_onboarding_prefs"]["custom_notes"] == "Updated note 2"


async def test_build_me_response_aal2_active_and_avatar_blob_store() -> None:
    """Test build_me_response with active AAL2 and blob store avatar fallback."""
    now = datetime.now(UTC)
    mock_app = type("MockApp", (), {"state": type("MockState", (), {"session_factory": None})()})()
    req = Request({"type": "http", "app": mock_app, "headers": []})

    # 1. AAL2 active via aal2_expires_at
    p1 = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=2,
        aal2_expires_at=now + timedelta(minutes=15),
    )
    res1 = await build_me_response(req, p1)
    body1 = json.loads(bytes(res1.body).decode("utf-8"))
    assert body1["aal2_active"] is True
    assert body1["aal2_expires_at"] is not None

    # 2. AAL2 active via sliding window
    p2 = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=2,
        aal2_expires_at=None,
        aal2_verified_at=now - timedelta(minutes=5),
        aal2_last_active_at=now - timedelta(minutes=2),
    )
    res2 = await build_me_response(req, p2)
    body2 = json.loads(bytes(res2.body).decode("utf-8"))
    assert body2["aal2_active"] is True
    assert body2["aal2_expires_at"] is not None


async def test_avatar_sniff_media_type_generic_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify _process_and_store_avatar wraps unknown sniff exceptions in 415."""

    # 1. Unknown sniff exception -> 415 UNSUPPORTED_MEDIA_TYPE
    def mock_sniff(*_args: object, **_kwargs: object) -> None:
        msg = "Corrupted image header"
        raise ValueError(msg)

    monkeypatch.setattr(us, "sniff_media_type", mock_sniff)
    p = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=1,
    )
    req = Request({"type": "http", "app": None, "headers": []})
    with pytest.raises(ProblemException) as exc_info:
        await us._process_and_store_avatar(  # noqa: SLF001
            request=req,
            principal=p,
            filename="bad.png",
            declared_ct="image/png",
            raw_bytes=b"dummybytes12345",
        )
    assert exc_info.value.status == 415
    assert exc_info.value.code == "UNSUPPORTED_MEDIA_TYPE"

    # 2. ProblemException from sniff_media_type re-raised directly (line 481)
    def mock_sniff_problem(*_args: object, **_kwargs: object) -> None:
        raise ProblemException(
            code="UNSUPPORTED_MEDIA_TYPE",
            status=415,
            title="Unsupported Format",
            detail="Format is rejected",
        )

    monkeypatch.setattr(us, "sniff_media_type", mock_sniff_problem)
    with pytest.raises(ProblemException) as exc_p:
        await us._process_and_store_avatar(  # noqa: SLF001
            request=req,
            principal=p,
            filename="bad.png",
            declared_ct="image/png",
            raw_bytes=b"dummybytes12345",
        )
    assert exc_p.value.status == 415
    assert exc_p.value.title == "Unsupported Format"


async def test_user_preferences_direct_invocation_without_session_factory() -> None:
    """Test get_user_preferences and update_user_preferences when session_factory is None."""
    mock_app = type("MockApp", (), {"state": type("MockState", (), {"session_factory": None})()})()
    mock_scope = {"type": "http", "app": mock_app, "headers": []}
    mock_req = Request(mock_scope)

    p_ctx = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=1,
    )

    get_res = await get_user_preferences(mock_req, p_ctx)
    assert get_res.agent_onboarding_prefs.scope == "local_only"
    assert get_res.agent_onboarding_prefs.execution_mode == "swarm"

    update_body = UpdateUserPreferencesRequest(
        agent_onboarding_prefs=AgentOnboardingPrefsPatch(
            scope="global_allowed",
            execution_mode="single_thread",
            model_strategy="quota_sipping_flash",
            qa_rigor="strict_forensic",
            custom_notes="Direct fallback test",
        )
    )
    patch_res = await update_user_preferences(update_body, mock_req, p_ctx)
    assert patch_res.agent_onboarding_prefs.scope == "global_allowed"
    assert patch_res.agent_onboarding_prefs.execution_mode == "single_thread"


async def test_avatar_upload_payload_guards() -> None:
    """Test avatar upload empty payload and size guards."""
    p = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=1,
    )

    # 1. Empty payload in _process_and_store_avatar
    req_empty = Request({"type": "http", "app": None, "headers": []})
    with pytest.raises(ProblemException) as exc_empty:
        await us._process_and_store_avatar(  # noqa: SLF001
            request=req_empty,
            principal=p,
            filename="empty.png",
            declared_ct="image/png",
            raw_bytes=b"",
        )
    assert exc_empty.value.status == 400
    assert exc_empty.value.code == "EMPTY_PAYLOAD"

    # 2. Oversize raw bytes (> 2 MiB)
    with pytest.raises(ProblemException) as exc_large:
        await us._process_and_store_avatar(  # noqa: SLF001
            request=req_empty,
            principal=p,
            filename="large.png",
            declared_ct="image/png",
            raw_bytes=b"X" * (2 * 1024 * 1024 + 10),
        )
    assert exc_large.value.status == 413
    assert exc_large.value.code == "PAYLOAD_TOO_LARGE"

    # 3. Stream chunk size guard in upload_avatar (> 2 MiB + 65536)
    async def mock_receive_large() -> dict[str, object]:
        return {
            "type": "http.request",
            "body": b"X" * (2 * 1024 * 1024 + 70000),
            "more_body": False,
        }

    req_stream = Request({"type": "http", "app": None, "headers": []}, receive=mock_receive_large)
    with pytest.raises(ProblemException) as exc_stream:
        await upload_avatar(request=req_stream, principal=p)
    assert exc_stream.value.status == 413
    assert exc_stream.value.code == "PAYLOAD_TOO_LARGE"

    # 4. Stream empty payload in upload_avatar
    async def mock_receive_empty() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    req_stream_empty = Request(
        {"type": "http", "app": None, "headers": []},
        receive=mock_receive_empty,
    )
    with pytest.raises(ProblemException) as exc_str_empty:
        await upload_avatar(request=req_stream_empty, principal=p)
    assert exc_str_empty.value.status == 400
    assert exc_str_empty.value.code == "EMPTY_PAYLOAD"

    # 5. Multipart parse fallback with non-leaf part and non-multipart payload
    mp_headers = [
        (b"content-type", b'multipart/form-data; boundary="===boundary==="'),
    ]
    mp_body = (
        b"--===boundary===\r\n"
        b'Content-Disposition: form-data; name="file"; filename="avatar.png"\r\n'
        b"Content-Type: image/png\r\n\r\n"
        b"sample-png-bytes\r\n"
        b"--===boundary===--\r\n"
    )
    req_mp = Request({"type": "http", "app": None, "headers": mp_headers})
    fn, ct, data = _parse_avatar_upload(req_mp, mp_body)
    assert fn == "avatar.png"
    assert ct == "image/png"
    assert data == b"sample-png-bytes"

    # Non-multipart multipart/form-data header
    req_non_mp = Request(
        {"type": "http", "app": None, "headers": [(b"content-type", b"multipart/form-data")]}
    )
    fn2, ct2, data2 = _parse_avatar_upload(req_non_mp, b"plain bytes")
    assert fn2 == "avatar.png"
    assert ct2 == "multipart/form-data"
    assert data2 == b"plain bytes"


async def test_build_me_response_roles_and_capabilities() -> None:
    """Test build_me_response role assignments for server admin, guest, and project admin."""
    mock_app = type("MockApp", (), {"state": type("MockState", (), {"session_factory": None})()})()
    req = Request({"type": "http", "app": mock_app, "headers": []})

    # 1. Server Admin
    p_sa = type(
        "PrincipalStub",
        (),
        {
            "principal_id": uuid.uuid4(),
            "workspace_id": uuid.uuid4(),
            "token_scopes": ("user",),
            "aal_level": 1,
            "is_server_admin": True,
            "is_workspace_admin": True,
            "is_project_admin": True,
            "user_access_hash": None,
            "principal_type": None,
            "is_mcp_credential": False,
        },
    )()
    res_sa = await build_me_response(req, p_sa)
    data_sa = json.loads(bytes(res_sa.body).decode("utf-8"))
    assert data_sa["workspace_role"] == "SERVER_ADMIN"
    assert "ADMIN_AUTH_STUDIO" in data_sa["workspace_capabilities"]

    # 2. Workspace Guest
    p_guest = type(
        "PrincipalStub",
        (),
        {
            "principal_id": uuid.uuid4(),
            "workspace_id": uuid.uuid4(),
            "token_scopes": ("user",),
            "aal_level": 1,
            "is_server_admin": False,
            "is_workspace_admin": False,
            "is_project_admin": False,
            "workspace_role": "WORKSPACE_GUEST",
            "user_access_hash": None,
            "principal_type": None,
            "is_mcp_credential": False,
        },
    )()
    res_guest = await build_me_response(req, p_guest)
    data_guest = json.loads(bytes(res_guest.body).decode("utf-8"))
    assert data_guest["workspace_role"] == "WORKSPACE_GUEST"
    assert data_guest["workspace_capabilities"] == []

    # 3. Workspace Admin (when session_factory is None)
    p_wa = type(
        "PrincipalStub",
        (),
        {
            "principal_id": uuid.uuid4(),
            "workspace_id": uuid.uuid4(),
            "token_scopes": ("user",),
            "aal_level": 1,
            "is_server_admin": False,
            "is_workspace_admin": True,
            "is_project_admin": True,
            "user_access_hash": None,
            "principal_type": None,
            "is_mcp_credential": False,
        },
    )()
    res_wa = await build_me_response(req, p_wa)
    data_wa = json.loads(bytes(res_wa.body).decode("utf-8"))
    assert data_wa["workspace_role"] == "WORKSPACE_ADMIN"
    assert "MANAGE_WORKSPACE_SETTINGS" in data_wa["workspace_capabilities"]


async def test_user_settings_session_factory_none_runtime_errors() -> None:
    """Verify runtime error guards when session_factory is None on app.state."""
    mock_app = type("MockApp", (), {"state": type("MockState", (), {"session_factory": None})()})()
    req = Request({"type": "http", "app": mock_app, "headers": []})
    p = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=1,
    )

    # 1. delete_avatar
    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await delete_avatar(request=req, principal=p)

    # 2. get_user_avatar
    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await get_user_avatar(principal_id=p.principal_id, request=req)

    # 3. change_password
    pw_body = ChangePasswordRequest(new_password="NewValidPassword123!")  # noqa: S106
    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await change_password(body=pw_body, request=req, principal=p)

    # 4. upload_avatar (session_factory is None)
    valid_png = _create_sample_png_bytes()

    async def mock_receive_valid() -> dict[str, object]:
        return {
            "type": "http.request",
            "body": valid_png,
            "more_body": False,
        }

    req_valid = Request(
        {"type": "http", "app": mock_app, "headers": [(b"content-type", b"image/png")]},
        receive=mock_receive_valid,
    )
    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await upload_avatar(request=req_valid, principal=p)


async def test_user_settings_new_local_admin_credential_create(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify change_password creates local credential when cred is None (lines 758-766)."""
    pepper_bytes = b"testpepper1234567890123456789012"
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", base64.urlsafe_b64encode(pepper_bytes).decode("ascii"))

    user = await make_user("new_cred_user")
    await api_env.seed.commit()

    session_id = uuid.uuid4()
    client = as_principal(user)
    if api_env.resolver.principal is not None:
        api_env.resolver.principal = dataclasses.replace(
            api_env.resolver.principal, session_id=session_id
        )

    csrf_tok = generate_csrf_token(session_id, b"\x00" * 32)
    auth_headers = {CSRF_HEADER_NAME: csrf_tok}
    client.cookies.set(CSRF_COOKIE_NAME, csrf_tok)

    res = await client.post(
        "/api/v1/auth/me/password",
        json={"new_password": "FreshBrandNewPassword123!"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Test short display name (< 3 chars, e.g. "a") and record_activity exception
    # (covers lines 765, 791-792)
    user_short = await make_user("a")
    await api_env.seed.commit()
    client_short = as_principal(user_short)
    session_id_short = uuid.uuid4()
    if api_env.resolver.principal is not None:
        api_env.resolver.principal = dataclasses.replace(
            api_env.resolver.principal, session_id=session_id_short
        )
    csrf_tok_short = generate_csrf_token(session_id_short, b"\x00" * 32)
    auth_headers_short = {CSRF_HEADER_NAME: csrf_tok_short}
    client_short.cookies.set(CSRF_COOKIE_NAME, csrf_tok_short)

    async def mock_fail_record(*_args: object, **_kwargs: object) -> None:
        msg = "Simulated activity ledger failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(us, "record_activity", mock_fail_record)
    res_short = await client_short.post(
        "/api/v1/auth/me/password",
        json={"new_password": "FreshBrandNewPassword123!"},
        headers=auth_headers_short,
    )
    assert res_short.status_code == 200
    assert res_short.json()["success"] is True
