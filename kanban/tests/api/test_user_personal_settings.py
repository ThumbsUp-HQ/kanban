# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for user personal settings studio, avatar, and password change.

Part of KB-USER-SETTINGS / KANBA-187.
"""

from __future__ import annotations

import base64
import dataclasses
import io
import json
import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import text
from starlette.requests import Request

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.user_settings import _resolve_auth_pepper, build_me_response
from kanban.auth.local.hashing import get_auth_pepper, hash_password_sync
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


async def test_user_personal_settings_profile_and_avatar_lifecycle(  # noqa: PLR0915
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test full profile update, timezone validation, avatar upload, and removal."""
    user = await make_user("alice")
    client = as_principal(user)

    # 1. Initial GET /api/v1/auth/me
    me_res = await client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["display_name"] == "Alice"
    assert me_data["timezone"] == "UTC"
    assert me_data["avatar_url"] is None
    assert me_data["has_local_password"] is False

    # 2. PATCH /api/v1/auth/me: Invalid Timezone
    bad_tz = await client.patch(
        "/api/v1/auth/me",
        json={"display_name": "Alice Updated", "timezone": "NonExistent/Zone"},
    )
    assert bad_tz.status_code == 422
    assert bad_tz.json()["code"] == "INVALID_TIMEZONE"

    # 3. PATCH /api/v1/auth/me: Valid update
    good_update = await client.patch(
        "/api/v1/auth/me",
        json={"display_name": "Alice Developer", "timezone": "America/New_York"},
    )
    assert good_update.status_code == 200
    assert good_update.json()["display_name"] == "Alice Developer"
    assert good_update.json()["timezone"] == "America/New_York"

    # Verify persisted in GET /api/v1/auth/me
    me_res2 = await client.get("/api/v1/auth/me")
    assert me_res2.status_code == 200
    assert me_res2.json()["display_name"] == "Alice Developer"
    assert me_res2.json()["timezone"] == "America/New_York"

    # 4. Avatar Upload: SVG rejected with 415
    svg_content = (
        b"<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        b"<circle cx='5' cy='5' r='5'/></svg>"
    )
    svg_res = await client.put(
        "/api/v1/auth/me/avatar",
        files={"file": ("avatar.svg", svg_content, "image/svg+xml")},
    )
    assert svg_res.status_code == 415
    assert svg_res.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"

    # 5. Avatar Upload: Valid PNG
    png_bytes = _create_sample_png_bytes()
    png_res = await client.put(
        "/api/v1/auth/me/avatar",
        files={"file": ("avatar.png", png_bytes, "image/png")},
    )
    assert png_res.status_code == 200
    expected_url_prefix = f"/api/v1/users/{user.id}/avatar"
    avatar_url = png_res.json()["avatar_url"]
    assert avatar_url.startswith(expected_url_prefix)
    assert "?v=" in avatar_url
    assert len(avatar_url.split("?v=")[1]) == 12
    # Verify canonical UserProfileResponse fields are present and display_name is preserved
    assert png_res.json()["display_name"] == "Alice Developer"
    assert png_res.json()["timezone"] == "America/New_York"
    assert "workspace_role" in png_res.json()
    assert "workspace_capabilities" in png_res.json()

    # Check me returns avatar_url
    me_res3 = await client.get("/api/v1/auth/me")
    assert me_res3.json()["avatar_url"] == avatar_url
    assert me_res3.json()["display_name"] == "Alice Developer"

    # 6. Retrieve avatar bytes and verify CSP sandbox, nosniff, same-origin, and ETag
    avatar_get = await client.get(avatar_url)
    assert avatar_get.status_code == 200
    assert avatar_get.headers["content-type"] == "image/png"
    assert avatar_get.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert avatar_get.headers["x-content-type-options"] == "nosniff"
    assert avatar_get.headers["cross-origin-resource-policy"] == "same-origin"
    assert "etag" in avatar_get.headers
    assert len(avatar_get.content) > 0

    # Conditional GET with If-None-Match returns 304 Not Modified
    etag = avatar_get.headers["etag"]
    avatar_cached = await client.get(avatar_url, headers={"If-None-Match": etag})
    assert avatar_cached.status_code == 304

    # 7. Avatar Removal: DELETE /api/v1/auth/me/avatar
    del_res = await client.delete("/api/v1/auth/me/avatar")
    assert del_res.status_code == 200
    assert del_res.json()["avatar_url"] is None
    assert del_res.json()["display_name"] == "Alice Developer"

    # Verify avatar is now 404
    avatar_get2 = await client.get(expected_url_prefix)
    assert avatar_get2.status_code == 404
    assert avatar_get2.json()["code"] == "AVATAR_NOT_FOUND"


async def test_password_change_policy_and_session_revocation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test password policy (admin vs user), unchanged rejection, and session revocation."""
    pepper_bytes = b"p" * 32
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", base64.urlsafe_b64encode(pepper_bytes).decode("ascii"))
    admin = await make_user("admin", workspace_role="SERVER_ADMIN")
    current_session_id = uuid.uuid4()
    client = as_principal(admin, aal_level=2)
    assert api_env.resolver.principal is not None
    api_env.resolver.principal = dataclasses.replace(
        api_env.resolver.principal, session_id=current_session_id
    )

    # Seed an existing local credential
    current_pw = "CurrentSecret1234!"
    pepper = get_auth_pepper()
    pw_hash = hash_password_sync(current_pw, pepper)

    await api_env.seed.execute(text("SET LOCAL app.is_setup_claim = 'true'"))
    await api_env.seed.execute(
        text("SELECT kb_auth.local_admin_create(:p_id, 'admin-user', :hash)"),
        {"p_id": admin.id, "hash": pw_hash},
    )

    # Seed 2 active sessions
    other_session_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "INSERT INTO sessions (id, token_sha256, principal_id, workspace_id, aal_level, "
            "idle_expires_at, absolute_expires_at, is_persistent) "
            "VALUES (:s1, :t1, :p_id, :w_id, 2, clock_timestamp() + interval '1 hour', "
            "clock_timestamp() + interval '1 day', true), "
            "(:s2, :t2, :p_id, :w_id, 2, clock_timestamp() + interval '1 hour', "
            "clock_timestamp() + interval '1 day', true)"
        ),
        {
            "s1": current_session_id,
            "s2": other_session_id,
            "p_id": admin.id,
            "w_id": admin.workspace_id,
            "t1": b"\x01" * 32,
            "t2": b"\x02" * 32,
        },
    )
    await api_env.seed.commit()

    csrf_tok = generate_csrf_token(current_session_id, b"\x00" * 32)
    auth_headers = {CSRF_HEADER_NAME: csrf_tok}
    client.cookies.set(CSRF_COOKIE_NAME, csrf_tok)

    # 1. Admin min length < 14 rejected with 422
    short_res = await client.post(
        "/api/v1/auth/me/password",
        json={"current_password": current_pw, "new_password": "Short12345!"},
        headers=auth_headers,
    )
    assert short_res.status_code == 422
    assert short_res.json()["code"] == "PASSWORD_TOO_SHORT"

    # 2. Unchanged password rejected with 422
    same_res = await client.post(
        "/api/v1/auth/me/password",
        json={"current_password": current_pw, "new_password": current_pw},
        headers=auth_headers,
    )
    assert same_res.status_code == 422
    assert same_res.json()["code"] == "PASSWORD_UNCHANGED"

    # 3. Wrong current password rejected with 401
    wrong_res = await client.post(
        "/api/v1/auth/me/password",
        json={"current_password": "WrongPassword123!", "new_password": "BrandNewSecret1234!"},
        headers=auth_headers,
    )
    assert wrong_res.status_code == 401
    assert wrong_res.json()["code"] == "INVALID_CREDENTIALS"

    # 4. Successful password change
    new_pw = "BrandNewSecret1234!"
    success_res = await client.post(
        "/api/v1/auth/me/password",
        json={"current_password": current_pw, "new_password": new_pw},
        headers=auth_headers,
    )
    assert success_res.status_code == 200
    assert success_res.json()["success"] is True

    # Verify other session was revoked, but current session is retained
    res = await api_env.seed.execute(
        text("SELECT id, revoked_at FROM sessions WHERE principal_id = :p_id ORDER BY id"),
        {"p_id": admin.id},
    )
    rows = res.mappings().all()
    for r in rows:
        if r["id"] == current_session_id:
            assert r["revoked_at"] is None, "Current session must remain active"
        else:
            assert r["revoked_at"] is not None, "Other session must be revoked"


async def test_passkey_rename_and_mfa_status(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test passkey nickname rename endpoint and MFA status reporting."""
    user = await make_user("bob")
    client = as_principal(user)

    # Seed a webauthn credential
    cred_uuid = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "INSERT INTO webauthn_credentials "
            "(id, principal_id, credential_id, public_key, sign_count, nickname) "
            "VALUES (:id, :p_id, :cid, :pk, 0, 'Original YubiKey')"
        ),
        {
            "id": cred_uuid,
            "p_id": user.id,
            "cid": b"\x10" * 32,
            "pk": b"\x20" * 64,
        },
    )
    await api_env.seed.commit()

    # Check GET /api/v1/auth/mfa/status
    status_res = await client.get("/api/v1/auth/mfa/status")
    assert status_res.status_code == 200
    st = status_res.json()
    assert st["totp_enabled"] is False
    assert st["passkeys_count"] == 1
    assert st["recovery_codes_remaining"] == 0
    assert st["preferred_method"] == "webauthn"

    # Rename passkey
    rename_res = await client.patch(
        f"/api/v1/auth/webauthn/credentials/{cred_uuid}",
        json={"nickname": "Hardware Key Office"},
    )
    assert rename_res.status_code == 200
    assert rename_res.json()["nickname"] == "Hardware Key Office"

    # Verify DB updated
    nick_res = await api_env.seed.execute(
        text("SELECT nickname FROM webauthn_credentials WHERE id = :id"),
        {"id": cred_uuid},
    )
    assert nick_res.scalar_one() == "Hardware Key Office"


async def test_admin_totp_last_factor_guard(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test admin cannot delete active TOTP factor if zero WebAuthn factors remain."""
    admin = await make_user("superadmin", workspace_role="SERVER_ADMIN")
    current_session_id = uuid.uuid4()
    client = as_principal(admin, aal_level=2)
    assert api_env.resolver.principal is not None
    api_env.resolver.principal = dataclasses.replace(
        api_env.resolver.principal, session_id=current_session_id
    )

    csrf_tok = generate_csrf_token(current_session_id, b"\x00" * 32)
    auth_headers = {CSRF_HEADER_NAME: csrf_tok}
    client.cookies.set(CSRF_COOKIE_NAME, csrf_tok)

    # Seed active TOTP factor
    totp_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "INSERT INTO totp_factors "
            "(id, principal_id, encrypted_secret_blob, wrapped_dek, status) "
            "VALUES (:id, :p_id, :sec, :dek, 'ACTIVE')"
        ),
        {
            "id": totp_id,
            "p_id": admin.id,
            "sec": b"\x01" * 32,
            "dek": b"\x02" * 32,
        },
    )
    await api_env.seed.commit()

    # Attempt to delete TOTP as admin with 0 passkeys -> 409 LAST_FACTOR
    del_res = await client.delete("/api/v1/auth/mfa/totp", headers=auth_headers)
    assert del_res.status_code == 409
    assert del_res.json()["code"] == "LAST_FACTOR"


async def test_user_personal_settings_validation_errors(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test validation boundaries for display_name, empty avatar, and limits."""
    user = await make_user("bob")
    client = as_principal(user)

    # Empty display name -> 422
    res_empty_name = await client.patch(
        "/api/v1/auth/me",
        json={"display_name": "   ", "timezone": "UTC"},
    )
    assert res_empty_name.status_code == 422
    assert res_empty_name.json()["code"] == "INVALID_DISPLAY_NAME"

    # Oversized display name (> 120 chars) -> 422
    res_long_name = await client.patch(
        "/api/v1/auth/me",
        json={"display_name": "A" * 121, "timezone": "UTC"},
    )
    assert res_long_name.status_code == 422

    # Empty avatar payload -> 400
    res_empty_avatar = await client.put(
        "/api/v1/auth/me/avatar",
        content=b"",
        headers={"Content-Type": "image/png"},
    )
    assert res_empty_avatar.status_code == 400
    assert res_empty_avatar.json()["code"] == "EMPTY_PAYLOAD"

    # Oversized avatar stream payload (> 2 MiB + 65536) -> 413
    res_huge_avatar = await client.put(
        "/api/v1/auth/me/avatar",
        content=b"x" * (2 * 1024 * 1024 + 70000),
        headers={"Content-Type": "image/png"},
    )
    assert res_huge_avatar.status_code == 413
    assert res_huge_avatar.json()["code"] == "PAYLOAD_TOO_LARGE"

    # Unsupported avatar MIME type (e.g. GIF) -> 415
    gif_bytes = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00"
        b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )
    res_gif = await client.put(
        "/api/v1/auth/me/avatar",
        files={"file": ("test.gif", gif_bytes, "image/gif")},
    )
    assert res_gif.status_code == 415
    assert res_gif.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"

    # Non-existent user avatar -> 404
    res_missing = await client.get(f"/api/v1/users/{uuid.uuid4()}/avatar")
    assert res_missing.status_code == 404
    assert res_missing.json()["code"] == "AVATAR_NOT_FOUND"


async def test_build_me_response_fallbacks(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test build_me_response fallback branches when hash is computed from blob store."""
    user = await make_user("charlie")
    client = as_principal(user)

    # 1. Upload valid avatar
    png_bytes = _create_sample_png_bytes(32, 32)
    png_res = await client.put(
        "/api/v1/auth/me/avatar",
        files={"file": ("avatar.png", png_bytes, "image/png")},
    )
    assert png_res.status_code == 200

    # 2. Null out avatar_sha256 in user_preferences to test dynamic hash calculation from blob store
    await api_env.seed.execute(
        text("UPDATE user_preferences SET avatar_sha256 = NULL WHERE principal_id = :p_id"),
        {"p_id": user.id},
    )
    await api_env.seed.commit()

    me_res = await client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert "?v=" in me_res.json()["avatar_url"]

    # 3. Direct call with session_factory = None on app.state
    mock_app = FastAPI()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/auth/me",
        "headers": [],
        "app": mock_app,
    }
    req = Request(scope)

    p_ctx = PrincipalContext(
        principal_id=user.id,
        workspace_id=uuid.uuid4(),
        token_scopes=("session",),
        aal_level=1,
    )
    resp = await build_me_response(req, p_ctx)
    assert resp.status_code == 200
    data = json.loads(bytes(resp.body).decode("utf-8"))
    assert data["principal_id"] == str(user.id)
    assert data["workspace_role"] == "WORKSPACE_MEMBER"


async def test_user_settings_avatar_etag_and_blob_error(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test avatar ETag 304 handling and blob store error handling."""
    user = await make_user("etag_user")
    client = as_principal(user)

    # 1. Upload valid avatar
    png_bytes = _create_sample_png_bytes(32, 32)
    png_res = await client.put(
        "/api/v1/auth/me/avatar",
        files={"file": ("avatar.png", png_bytes, "image/png")},
    )
    assert png_res.status_code == 200

    # 2. Get avatar with ETag
    get_res = await client.get(f"/api/v1/users/{user.id}/avatar")
    assert get_res.status_code == 200
    etag = get_res.headers.get("etag")
    assert etag is not None

    # 3. Request with matching If-None-Match -> 304 Not Modified
    res_304 = await client.get(
        f"/api/v1/users/{user.id}/avatar",
        headers={"if-none-match": etag},
    )
    assert res_304.status_code == 304

    # 4. Request with wildcard If-None-Match -> 304 Not Modified
    res_304_wildcard = await client.get(
        f"/api/v1/users/{user.id}/avatar",
        headers={"if-none-match": "*"},
    )
    assert res_304_wildcard.status_code == 304

    # 5. Non-matching If-None-Match -> 200
    res_200 = await client.get(
        f"/api/v1/users/{user.id}/avatar",
        headers={"if-none-match": '"nonmatching"'},
    )
    assert res_200.status_code == 200

    # 6. Blob storage file corrupted/missing -> 404
    await api_env.seed.execute(
        text(
            "UPDATE user_preferences SET avatar_storage_key = 'missing_key_file' "
            "WHERE principal_id = :p_id"
        ),
        {"p_id": user.id},
    )
    await api_env.seed.commit()

    res_missing_blob = await client.get(f"/api/v1/users/{user.id}/avatar")
    assert res_missing_blob.status_code == 404
    assert res_missing_blob.json()["code"] == "AVATAR_NOT_FOUND"


async def test_user_settings_password_change_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test password change validation branches and credential creation."""
    pepper_bytes = b"p" * 32
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", base64.urlsafe_b64encode(pepper_bytes).decode("ascii"))
    user = await make_user("pw_user")
    current_session_id = uuid.uuid4()
    client = as_principal(user, aal_level=1)
    assert api_env.resolver.principal is not None
    api_env.resolver.principal = dataclasses.replace(
        api_env.resolver.principal, session_id=current_session_id
    )

    csrf_tok = generate_csrf_token(current_session_id, b"\x00" * 32)
    auth_headers = {CSRF_HEADER_NAME: csrf_tok}
    client.cookies.set(CSRF_COOKIE_NAME, csrf_tok)

    # 1. New password too short for normal user (< 12) -> 422
    res_short = await client.post(
        "/api/v1/auth/me/password",
        json={"new_password": "short"},
        headers=auth_headers,
    )
    assert res_short.status_code == 422
    assert res_short.json()["code"] == "PASSWORD_TOO_SHORT"

    # 2. Identical password -> 422
    res_identical = await client.post(
        "/api/v1/auth/me/password",
        json={"current_password": "ExistingPassword123!", "new_password": "ExistingPassword123!"},
        headers=auth_headers,
    )
    assert res_identical.status_code == 422
    assert res_identical.json()["code"] == "PASSWORD_UNCHANGED"

    # Seed an existing local credential with valid lowercase username
    current_pw = "CurrentSecret1234!"
    pepper = get_auth_pepper()
    pw_hash = hash_password_sync(current_pw, pepper)

    await api_env.seed.execute(text("SET LOCAL app.is_setup_claim = 'true'"))
    await api_env.seed.execute(
        text("SELECT kb_auth.local_admin_create(:p_id, 'pw-user', :hash)"),
        {"p_id": user.id, "hash": pw_hash},
    )
    await api_env.seed.commit()

    # 3. Missing current password when credential exists -> 422
    res_missing_curr = await client.post(
        "/api/v1/auth/me/password",
        json={"new_password": "AnotherBrandNewPassword123!"},
        headers=auth_headers,
    )
    assert res_missing_curr.status_code == 422
    assert res_missing_curr.json()["code"] == "CURRENT_PASSWORD_REQUIRED"

    # 4. Wrong current password -> 401
    res_wrong_curr = await client.post(
        "/api/v1/auth/me/password",
        json={
            "current_password": "WrongPassword123!",
            "new_password": "AnotherBrandNewPassword123!",
        },
        headers=auth_headers,
    )
    assert res_wrong_curr.status_code == 401
    assert res_wrong_curr.json()["code"] == "INVALID_CREDENTIALS"

    # 5. Correct current password -> 200
    res_valid_pw = await client.post(
        "/api/v1/auth/me/password",
        json={"current_password": current_pw, "new_password": "AnotherBrandNewPassword123!"},
        headers=auth_headers,
    )
    assert res_valid_pw.status_code == 200
    assert res_valid_pw.json()["success"] is True

    # 6. Admin user with AAL1 -> 403 AAL2_REQUIRED
    admin = await make_user("admin_aal1", workspace_role="SERVER_ADMIN")
    admin_session_id = uuid.uuid4()
    admin_client = as_principal(admin, aal_level=1)
    assert api_env.resolver.principal is not None
    api_env.resolver.principal = dataclasses.replace(
        api_env.resolver.principal, session_id=admin_session_id
    )
    admin_csrf = generate_csrf_token(admin_session_id, b"\x00" * 32)
    admin_headers = {CSRF_HEADER_NAME: admin_csrf}
    admin_client.cookies.set(CSRF_COOKIE_NAME, admin_csrf)

    res_admin_aal1 = await admin_client.post(
        "/api/v1/auth/me/password",
        json={"new_password": "AdminPasswordWith16Chars!"},
        headers=admin_headers,
    )
    assert res_admin_aal1.status_code == 403
    assert res_admin_aal1.json()["code"] == "AAL2_REQUIRED"

    # 7. Admin password too short (< 16 chars)
    admin_client_aal2 = as_principal(admin, aal_level=2)
    assert api_env.resolver.principal is not None
    api_env.resolver.principal = dataclasses.replace(
        api_env.resolver.principal, session_id=admin_session_id
    )
    admin_client_aal2.cookies.set(CSRF_COOKIE_NAME, admin_csrf)
    res_admin_short = await admin_client_aal2.post(
        "/api/v1/auth/me/password",
        json={"new_password": "Short1!"},
        headers=admin_headers,
    )
    assert res_admin_short.status_code == 422
    assert res_admin_short.json()["code"] == "PASSWORD_TOO_SHORT"


async def test_user_settings_pepper_and_svg_rejection(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test SVG rejection and pepper resolution with key material."""
    user = await make_user("svg_user")
    client = as_principal(user)

    # 1. Reject SVG avatar explicitly
    svg_bytes = b"<svg xmlns='http://www.w3.org/2000/svg'><circle r='10'/></svg>"
    res_svg = await client.put(
        "/api/v1/auth/me/avatar",
        files={"file": ("avatar.svg", svg_bytes, "image/svg+xml")},
    )
    assert res_svg.status_code == 415
    assert "SVG avatars are not allowed" in res_svg.json()["detail"]

    # 2. Test _resolve_auth_pepper with app.state.key_material
    class DummyKeyMaterial:
        auth_pepper = b"custom_pepper_12345"

    app = FastAPI()
    app.state.key_material = DummyKeyMaterial()
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "app": app}
    req = Request(scope)
    pepper = _resolve_auth_pepper(req)
    assert pepper == b"custom_pepper_12345"


async def test_user_settings_raw_binary_upload_and_delete_empty(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test raw binary upload branch and deleting avatar when none is set."""
    user = await make_user("raw_user")
    client = as_principal(user)

    # 1. Delete avatar when no avatar exists -> 200 with avatar_url=None
    del_res = await client.delete("/api/v1/auth/me/avatar")
    assert del_res.status_code == 200
    assert del_res.json()["avatar_url"] is None

    # 2. Upload via raw binary with x-filename header
    png_bytes = _create_sample_png_bytes(48, 48)
    upload_res = await client.put(
        "/api/v1/auth/me/avatar",
        content=png_bytes,
        headers={"Content-Type": "image/png", "X-Filename": "my_avatar.png"},
    )
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["avatar_url"] is not None
    assert "?v=" in data["avatar_url"]


async def test_user_preferences_agent_onboarding_lifecycle_and_rls(
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    api_env: ApiEnv,
) -> None:
    """Test GET/PATCH /api/v1/users/me/preferences, defaults, persistence, validation, and RLS isolation."""
    user_a = await make_user("user_a")
    user_b = await make_user("user_b")

    # 1. User A initial GET returns defaults
    client = as_principal(user_a)
    res_a_init = await client.get("/api/v1/users/me/preferences")
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
        "scope": "global_allowed",
        "execution_mode": "teamwork",
        "model_strategy": "hybrid",
        "qa_rigor": "standard",
        "custom_notes": "Always run local unit tests with 95% coverage.",
    }
    res_a_patch = await client.patch("/api/v1/users/me/preferences", json=patch_payload)
    assert res_a_patch.status_code == 200
    data_a_patch = res_a_patch.json()
    assert data_a_patch["agent_onboarding_prefs"]["scope"] == "global_allowed"
    assert data_a_patch["agent_onboarding_prefs"]["execution_mode"] == "teamwork"
    assert data_a_patch["agent_onboarding_prefs"]["model_strategy"] == "hybrid"
    assert data_a_patch["agent_onboarding_prefs"]["qa_rigor"] == "standard"
    assert data_a_patch["agent_onboarding_prefs"]["custom_notes"] == "Always run local unit tests with 95% coverage."

    # 3. User A GET confirms persistence
    res_a_get2 = await client.get("/api/v1/users/me/preferences")
    assert res_a_get2.status_code == 200
    assert res_a_get2.json()["agent_onboarding_prefs"] == data_a_patch["agent_onboarding_prefs"]

    # 4. User B GET still has their own default preferences (RLS isolation)
    as_principal(user_b)
    res_b_get = await client.get("/api/v1/users/me/preferences")
    assert res_b_get.status_code == 200
    data_b = res_b_get.json()
    assert data_b["principal_id"] == str(user_b.id)
    assert data_b["agent_onboarding_prefs"]["scope"] == "local_only"
    assert data_b["agent_onboarding_prefs"]["custom_notes"] == ""

    # 5. User A PATCH with nested agent_onboarding_prefs object
    as_principal(user_a)
    res_nested = await client.patch(
        "/api/v1/users/me/preferences",
        json={
            "agent_onboarding_prefs": {
                "scope": "local_only",
                "execution_mode": "single_thread",
                "model_strategy": "unconstrained_max",
                "qa_rigor": "strict_forensic",
                "custom_notes": "Use Sol MAX for architecture.",
            }
        },
    )
    assert res_nested.status_code == 200
    assert res_nested.json()["agent_onboarding_prefs"]["execution_mode"] == "single_thread"
    assert res_nested.json()["agent_onboarding_prefs"]["model_strategy"] == "unconstrained_max"

    # 6. Negative: Invalid enum returns 422
    res_invalid_enum = await client.patch(
        "/api/v1/users/me/preferences",
        json={"scope": "invalid_scope"},
    )
    assert res_invalid_enum.status_code == 422

    # 7. Negative: UTF-16 lone surrogate character rejected with 422 INVALID_UTF8_SURROGATE
    res_surr = await client.patch(
        "/api/v1/users/me/preferences",
        content=b'{"custom_notes": "bad \\ud800 surrogate"}',
        headers={"Content-Type": "application/json"},
    )
    assert res_surr.status_code == 422
    assert res_surr.json()["code"] == "INVALID_UTF8_SURROGATE"

    # 8. Negative: Oversized custom_notes (> 4096 bytes) returns 422
    oversized = "a" * 5000
    res_too_large = await client.patch(
        "/api/v1/users/me/preferences",
        json={"custom_notes": oversized},
    )
    assert res_too_large.status_code == 422

    # 9. Negative/Boundary: User A executing direct SQL under RLS cannot mutate User B's row
    from database.session import RLSContext
    transport = getattr(api_env.client, "_transport", None)
    app = getattr(transport, "app", None)
    session_factory = getattr(getattr(app, "state", None), "session_factory", None)
    if session_factory is not None:
        rls_ctx_a = RLSContext(
            principal_id=user_a.id,
            workspace_id=user_a.workspace_id,
            token_scopes=frozenset({"user"}),
            aal_level=1,
        )
        async with session_factory.session(rls_ctx_a) as session:
            res_update = await session.execute(
                text(
                    "UPDATE public.user_preferences "
                    "SET agent_onboarding_prefs_json = '{\"custom_notes\": \"hacked\"}'::jsonb "
                    "WHERE principal_id = :target_id"
                ),
                {"target_id": user_b.id},
            )
            assert res_update.rowcount == 0

    # 10. Direct invocation when session_factory is None (fallback handling)
    from kanban.api.v1.user_settings import get_user_preferences, update_user_preferences, UpdateUserPreferencesRequest
    from starlette.requests import Request
    from kanban.api.deps import PrincipalContext

    mock_scope = {"type": "http", "app": type("MockApp", (), {"state": type("MockState", (), {"session_factory": None})()})()}
    mock_req = Request(mock_scope)
    mock_principal = PrincipalContext(
        principal_id=user_a.id,
        workspace_id=user_a.workspace_id,
        token_scopes=("user",),
        aal_level=1,
    )

    prefs_no_db = await get_user_preferences(request=mock_req, principal=mock_principal)
    assert prefs_no_db.agent_onboarding_prefs.scope == "local_only"

    updated_no_db = await update_user_preferences(
        body=UpdateUserPreferencesRequest(scope="global_allowed"),
        request=mock_req,
        principal=mock_principal,
    )
    assert updated_no_db.agent_onboarding_prefs.scope == "global_allowed"


async def test_validate_custom_notes_and_surrogate_boundary() -> None:
    """Verify _validate_custom_notes rejects surrogates, bounds size, and strips controls."""
    from kanban.api.v1.user_settings import _validate_custom_notes
    from kanban.api.problems import ProblemException

    # 1. Valid notes pass
    clean = _validate_custom_notes("Valid preferences note")
    assert clean == "Valid preferences note"

    # 2. UTF-16 surrogate code point explicitly rejected with 422 INVALID_UTF8_SURROGATE
    with pytest.raises(ProblemException) as exc_info:
        _validate_custom_notes(f"note with {chr(0xD800)} surrogate")
    assert exc_info.value.code == "INVALID_UTF8_SURROGATE"
    assert exc_info.value.status == 422

    # 3. Oversized string (> 4096 bytes) rejected with 422
    with pytest.raises(ProblemException) as exc_info2:
        _validate_custom_notes("x" * 4097)
    assert exc_info2.value.status == 422


async def test_build_me_response_branches_and_aal2_sliding_window() -> None:
    """Verify build_me_response handles all principal roles and AAL2 sliding window branches."""
    from datetime import datetime, UTC, timedelta
    from starlette.requests import Request
    from kanban.api.deps import PrincipalContext
    from kanban.api.v1.user_settings import build_me_response

    mock_app = type("MockApp", (), {"state": type("MockState", (), {"session_factory": None})()})()
    mock_scope = {"type": "http", "app": mock_app, "headers": []}
    mock_req = Request(mock_scope)

    # 1. Fallback (session_factory=None) with is_server_admin
    p_server_admin = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=1,
        is_server_admin=True,
    )
    res_sa = await build_me_response(mock_req, p_server_admin)
    data_sa = json.loads(res_sa.body.decode("utf-8"))
    assert data_sa["workspace_role"] == "SERVER_ADMIN"
    assert "ADMIN_AUTH_STUDIO" in data_sa["workspace_capabilities"]

    # 2. Fallback with is_workspace_admin duck typing
    p_ws_admin = type(
        "MockWsAdminPrincipal",
        (),
        {
            "principal_id": uuid.uuid4(),
            "workspace_id": uuid.uuid4(),
            "token_scopes": ("user",),
            "aal_level": 1,
            "is_server_admin": False,
            "is_workspace_admin": True,
            "workspace_role": "WORKSPACE_ADMIN",
            "session_id": None,
            "agent_principal_id": None,
            "ephemeral_project_id": None,
            "read_only": False,
            "mfa_pending": False,
            "aal2_verified_at": None,
            "aal2_last_active_at": None,
            "aal2_expires_at": None,
            "scope_tier": None,
            "scoped_project_id": None,
            "user_access_hash": None,
            "principal_type": None,
            "is_mcp_credential": False,
        },
    )()
    res_wa = await build_me_response(mock_req, p_ws_admin)
    data_wa = json.loads(res_wa.body.decode("utf-8"))
    assert data_wa["workspace_role"] == "WORKSPACE_ADMIN"

    # 3. Fallback with guest role duck typing
    p_guest = type(
        "MockGuestPrincipal",
        (),
        {
            "principal_id": uuid.uuid4(),
            "workspace_id": uuid.uuid4(),
            "token_scopes": ("user",),
            "aal_level": 1,
            "is_server_admin": False,
            "is_workspace_admin": False,
            "workspace_role": "WORKSPACE_GUEST",
            "session_id": None,
            "agent_principal_id": None,
            "ephemeral_project_id": None,
            "read_only": False,
            "mfa_pending": False,
            "aal2_verified_at": None,
            "aal2_last_active_at": None,
            "aal2_expires_at": None,
            "scope_tier": None,
            "scoped_project_id": None,
            "user_access_hash": None,
            "principal_type": None,
            "is_mcp_credential": False,
        },
    )()
    res_guest = await build_me_response(mock_req, p_guest)
    data_guest = json.loads(res_guest.body.decode("utf-8"))
    assert data_guest["workspace_role"] == "WORKSPACE_GUEST"
    assert data_guest["workspace_capabilities"] == []

    # 4. AAL2 with verified_at / last_active_at sliding window
    now = datetime.now(UTC)
    p_aal2_sliding = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=2,
        aal2_verified_at=now,
        aal2_last_active_at=now,
    )
    res_sliding = await build_me_response(mock_req, p_aal2_sliding)
    data_sliding = json.loads(res_sliding.body.decode("utf-8"))
    assert data_sliding["aal2_active"] is True
    assert data_sliding["aal2_expires_at"] is not None

    # 5. AAL2 with expired aal2_expires_at
    past = now - timedelta(hours=1)
    p_aal2_expired = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=2,
        aal2_expires_at=past,
    )
    res_exp = await build_me_response(mock_req, p_aal2_expired)
    data_exp = json.loads(res_exp.body.decode("utf-8"))
    assert data_exp["aal2_active"] is False


async def test_avatar_parsing_and_processing_error_branches() -> None:
    """Verify avatar parser and processor handle multipart bodies, oversize, and errors."""
    import email.message
    from starlette.requests import Request
    from kanban.api.deps import PrincipalContext
    from kanban.api.v1.user_settings import (
        _parse_avatar_upload,
        _process_and_store_avatar,
        MAX_AVATAR_BYTES,
    )
    from kanban.api.problems import ProblemException

    # 1. Parse multipart email payload
    msg = email.message.EmailMessage()
    msg["Content-Type"] = "multipart/form-data; boundary=boundary123"
    part = email.message.EmailMessage()
    part.set_content(b"fake image bytes", maintype="image", subtype="png")
    part.add_header("Content-Disposition", "form-data", name="avatar", filename="custom.png")
    msg.attach(part)
    msg_bytes = msg.as_bytes()

    scope = {
        "type": "http",
        "app": None,
        "headers": [(b"content-type", b"multipart/form-data; boundary=boundary123")],
    }
    req = Request(scope)
    fn, ct, payload = _parse_avatar_upload(req, msg_bytes)
    assert fn == "custom.png"
    assert payload == b"fake image bytes"

    # 2. _process_and_store_avatar: oversized payload
    p = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=1,
    )
    with pytest.raises(ProblemException) as exc_large:
        await _process_and_store_avatar(
            request=req,
            principal=p,
            filename="large.png",
            declared_ct="image/png",
            raw_bytes=b"x" * (MAX_AVATAR_BYTES + 1),
        )
    assert exc_large.value.code == "PAYLOAD_TOO_LARGE"

    # 3. _process_and_store_avatar: empty payload
    with pytest.raises(ProblemException) as exc_empty:
        await _process_and_store_avatar(
            request=req,
            principal=p,
            filename="empty.png",
            declared_ct="image/png",
            raw_bytes=b"",
        )
    assert exc_empty.value.code == "EMPTY_PAYLOAD"


async def test_user_personal_settings_change_password_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test POST /api/v1/auth/me/password endpoint end-to-end for user without prior credentials."""
    pepper_bytes = b"p" * 32
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", base64.urlsafe_b64encode(pepper_bytes).decode("ascii"))
    user = await make_user("pw_change_user_403")
    await api_env.seed.commit()
    current_session_id = uuid.uuid4()
    client = as_principal(user)
    assert api_env.resolver.principal is not None
    api_env.resolver.principal = dataclasses.replace(
        api_env.resolver.principal, session_id=current_session_id
    )

    csrf_tok = generate_csrf_token(current_session_id, b"\x00" * 32)
    auth_headers = {CSRF_HEADER_NAME: csrf_tok}
    client.cookies.set(CSRF_COOKIE_NAME, csrf_tok)

    # 1. Password too short (< 10 chars) returns 422
    res_short = await client.post(
        "/api/v1/auth/me/password",
        json={"new_password": "short"},
        headers=auth_headers,
    )
    assert res_short.status_code == 422
    assert res_short.json()["code"] == "PASSWORD_TOO_SHORT"

    # 2. User initially has no local credentials: create local password successfully
    res_create = await client.post(
        "/api/v1/auth/me/password",
        json={"new_password": "MyNewSecurePassword123!"},
        headers=auth_headers,
    )
    assert res_create.status_code == 200
    assert res_create.json()["success"] is True

    # 3. Identical password returns 422 PASSWORD_UNCHANGED
    res_same = await client.post(
        "/api/v1/auth/me/password",
        json={
            "current_password": "MyNewSecurePassword123!",
            "new_password": "MyNewSecurePassword123!",
        },
        headers=auth_headers,
    )
    assert res_same.status_code == 422
    assert res_same.json()["code"] == "PASSWORD_UNCHANGED"

    # 4. Missing current_password when local password exists returns 422 CURRENT_PASSWORD_REQUIRED
    res_missing_curr = await client.post(
        "/api/v1/auth/me/password",
        json={"new_password": "BrandNewPassword456!"},
        headers=auth_headers,
    )
    assert res_missing_curr.status_code == 422
    assert res_missing_curr.json()["code"] == "CURRENT_PASSWORD_REQUIRED"

    # 5. Invalid current_password returns 401 INVALID_CREDENTIALS
    res_wrong_curr = await client.post(
        "/api/v1/auth/me/password",
        json={
            "current_password": "WrongPassword999!",
            "new_password": "BrandNewPassword456!",
        },
        headers=auth_headers,
    )
    assert res_wrong_curr.status_code == 401
    assert res_wrong_curr.json()["code"] == "INVALID_CREDENTIALS"

    # 6. Valid change with correct current_password succeeds
    res_ok = await client.post(
        "/api/v1/auth/me/password",
        json={
            "current_password": "MyNewSecurePassword123!",
            "new_password": "BrandNewPassword456!",
        },
        headers=auth_headers,
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["success"] is True


async def test_user_personal_settings_roles_in_me(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test GET /api/v1/auth/me for WORKSPACE_ADMIN and WORKSPACE_GUEST."""
    u_admin = await make_user("ws_admin_user", workspace_role="WORKSPACE_ADMIN")
    await api_env.seed.commit()
    c_admin = as_principal(u_admin)
    res_admin = await c_admin.get("/api/v1/auth/me")
    assert res_admin.status_code == 200
    assert res_admin.json()["workspace_role"] == "WORKSPACE_ADMIN"

    u_guest = await make_user("ws_guest_user", workspace_role="WORKSPACE_GUEST")
    await api_env.seed.commit()
    c_guest = as_principal(u_guest)
    res_guest = await c_guest.get("/api/v1/auth/me")
    assert res_guest.status_code == 200
    assert res_guest.json()["workspace_role"] == "WORKSPACE_GUEST"


async def test_session_factory_none_runtime_errors() -> None:
    """Verify endpoints raise RuntimeError when session_factory is missing."""
    from starlette.requests import Request
    from kanban.api.deps import PrincipalContext
    from kanban.api.v1.user_settings import (
        delete_avatar,
        get_user_avatar,
        change_password,
        ChangePasswordRequest,
    )

    mock_app = type("MockApp", (), {"state": type("MockState", (), {"session_factory": None})()})()
    mock_scope = {"type": "http", "app": mock_app, "headers": []}
    mock_req = Request(mock_scope)
    mock_principal = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=1,
    )

    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await delete_avatar(request=mock_req, principal=mock_principal)

    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await get_user_avatar(principal_id=uuid.uuid4(), request=mock_req)

    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await change_password(
            body=ChangePasswordRequest(new_password="ValidNewPassword123!"),
            request=mock_req,
            principal=mock_principal,
        )

    from kanban.api.v1.user_settings import update_profile, UpdateProfileRequest, _process_and_store_avatar

    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await update_profile(
            body=UpdateProfileRequest(display_name="Test"),
            request=mock_req,
            principal=mock_principal,
        )

    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await _process_and_store_avatar(
            request=mock_req,
            principal=mock_principal,
            filename="test.png",
            declared_ct="image/png",
            raw_bytes=_create_sample_png_bytes(16, 16),
        )

    with pytest.raises(ProblemException) as exc_unsupported:
        await _process_and_store_avatar(
            request=mock_req,
            principal=mock_principal,
            filename="unknown.xyz",
            declared_ct="application/octet-stream",
            raw_bytes=b"not an image at all",
        )
    assert exc_unsupported.value.code == "MIME_MISMATCH_OR_UNSUPPORTED"


async def test_multipart_avatar_parsing_and_oversize_upload() -> None:
    """Verify multipart email parsing and stream overflow check in upload_avatar."""
    from starlette.requests import Request
    from kanban.api.deps import PrincipalContext
    from kanban.api.v1.user_settings import _parse_avatar_upload, upload_avatar
    from kanban.api.problems import ProblemException

    # 1. Real multipart body with boundary
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    raw_multipart = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="avatar"; filename="test_pic.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
        f"test-image-content\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    scope = {
        "type": "http",
        "app": None,
        "headers": [(b"content-type", f"multipart/form-data; boundary={boundary}".encode("latin-1"))],
    }
    req = Request(scope)
    fn, ct, payload = _parse_avatar_upload(req, raw_multipart)
    assert fn == "test_pic.png"
    assert ct == "image/png"
    assert payload == b"test-image-content"

    # 2. upload_avatar stream chunk size check (> MAX_AVATAR_BYTES + 65536)
    p = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=1,
    )
    async def mock_receive():
        return {"type": "http.request", "body": b"X" * (2 * 1024 * 1024 + 70000), "more_body": False}

    oversize_req = Request({"type": "http", "app": None, "headers": []}, receive=mock_receive)
    with pytest.raises(ProblemException) as exc_large:
        await upload_avatar(request=oversize_req, principal=p)
    assert exc_large.value.code == "PAYLOAD_TOO_LARGE"


async def test_change_password_short_display_name(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify change_password falls back to user-<hex> when clean display_name is < 3 chars."""
    pepper_bytes = b"p" * 32
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", base64.urlsafe_b64encode(pepper_bytes).decode("ascii"))
    user = await make_user("x")
    await api_env.seed.commit()
    current_session_id = uuid.uuid4()
    client = as_principal(user)
    assert api_env.resolver.principal is not None
    api_env.resolver.principal = dataclasses.replace(
        api_env.resolver.principal, session_id=current_session_id
    )

    csrf_tok = generate_csrf_token(current_session_id, b"\x00" * 32)
    auth_headers = {CSRF_HEADER_NAME: csrf_tok}
    client.cookies.set(CSRF_COOKIE_NAME, csrf_tok)

    res = await client.post(
        "/api/v1/auth/me/password",
        json={"new_password": "ShortNameUserPass123!"},
        headers=auth_headers,
    )
    assert res.status_code == 200


async def test_build_me_response_aal2_active_and_avatar_blob_store() -> None:
    """Test build_me_response with active AAL2 and blob store avatar fallback."""
    from datetime import datetime, timedelta, UTC
    now = datetime.now(UTC)

    mock_app = type("MockApp", (), {"state": type("MockState", (), {"session_factory": None})()})()
    req1 = Request({"type": "http", "app": mock_app, "headers": []})

    # 1. AAL2 active via aal2_expires_at
    p1 = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=2,
        aal2_expires_at=now + timedelta(minutes=15),
    )
    res1 = await build_me_response(req1, p1)
    body1 = json.loads(res1.body.decode("utf-8"))
    assert body1["aal2_active"] is True
    assert body1["aal2_expires_at"] is not None

    # 2. AAL2 active via sliding window (aal2_expires_at is None)
    p2 = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=2,
        aal2_expires_at=None,
        aal2_verified_at=now - timedelta(minutes=5),
        aal2_last_active_at=now - timedelta(minutes=2),
    )
    res2 = await build_me_response(req1, p2)
    body2 = json.loads(res2.body.decode("utf-8"))
    assert body2["aal2_active"] is True
    assert body2["aal2_expires_at"] is not None


async def test_avatar_sniff_media_type_generic_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify _process_and_store_avatar wraps unknown sniff exceptions in 415."""
    import kanban.api.v1.user_settings as us

    def mock_sniff(*args, **kwargs):
        raise ValueError("Corrupted image header")

    monkeypatch.setattr(us, "sniff_media_type", mock_sniff)
    p = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("user",),
        aal_level=1,
    )
    req = Request({"type": "http", "app": None, "headers": []})
    with pytest.raises(ProblemException) as exc_info:
        await us._process_and_store_avatar(
            request=req,
            principal=p,
            filename="bad.png",
            declared_ct="image/png",
            raw_bytes=b"dummybytes12345",
        )
    assert exc_info.value.status == 415
    assert exc_info.value.code == "UNSUPPORTED_MEDIA_TYPE"

