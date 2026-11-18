# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for user personal settings studio, avatar, and password change.

Part of KB-USER-SETTINGS / KANBA-187.
"""

from __future__ import annotations

import base64
import dataclasses
import io
import uuid
from typing import TYPE_CHECKING

import pytest
from PIL import Image
from sqlalchemy import text

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


async def test_user_personal_settings_profile_and_avatar_lifecycle(
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
    expected_url = f"/api/v1/users/{user.id}/avatar"
    assert png_res.json()["avatar_url"] == expected_url

    # Check me returns avatar_url
    me_res3 = await client.get("/api/v1/auth/me")
    assert me_res3.json()["avatar_url"] == expected_url

    # 6. Retrieve avatar bytes
    avatar_get = await client.get(expected_url)
    assert avatar_get.status_code == 200
    assert avatar_get.headers["content-type"] == "image/png"
    assert "default-src 'none'" in avatar_get.headers["content-security-policy"]
    assert len(avatar_get.content) > 0

    # 7. Avatar Removal: DELETE /api/v1/auth/me/avatar
    del_res = await client.delete("/api/v1/auth/me/avatar")
    assert del_res.status_code == 200
    assert del_res.json()["avatar_url"] is None

    # Verify avatar is now 404
    avatar_get2 = await client.get(expected_url)
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
