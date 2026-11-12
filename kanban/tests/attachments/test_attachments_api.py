# ruff: noqa: PLR0913, PLR0917, PLR0915, SLF001
"""Feature integration tests for attachment endpoints and security gates (S5.4, KB-P2-15)."""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational
from sqlalchemy import text

from kanban.attachments.service import AttachmentService
from kanban.attachments.sniff import MAX_ATTACHMENT_BYTES
from kanban.attachments.storage import LocalFilesystemBlobStore
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    PRE_SESSION_ID,
    generate_csrf_token,
)
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit.pg import PgRateLimiter
from kanban.tests.attachments.test_sniff_and_raster import _create_synthetic_png_header
from kanban.tests.security.helpers import (
    add_acl_entry,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


def _make_jpeg_payload() -> tuple[bytes, bytes]:
    """Generate JPEG with EXIF GPS tags and trailing polyglot bytes."""
    im = Image.new("RGB", (64, 64), color="blue")
    exif = im.getexif()
    exif[0x010F] = "TestCamera"
    exif[0xA431] = "SN-00112233"

    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (IFDRational(37, 1), IFDRational(46, 1), IFDRational(29, 1))
    gps[3] = "W"
    gps[4] = (IFDRational(122, 1), IFDRational(25, 1), IFDRational(10, 1))

    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    polyglot = b"<?php phpinfo(); ?>trailing_payload"
    return buf.getvalue() + polyglot, polyglot


def _setup_api_app_state(
    env: ApiEnv, tmp_path: Path
) -> tuple[KeyMaterial, LocalFilesystemBlobStore]:
    """Ensure key material, rate limiter, and blob store are configured on app state."""
    app = env.client._transport.app  # type: ignore[attr-defined]
    km = KeyMaterial(
        master_kek=b"\x11" * 32,
        auth_pepper=b"\x22" * 32,
        session_hmac_key=b"\x33" * 32,
    )
    blob_store = LocalFilesystemBlobStore(tmp_path / "blobs")
    app.state.key_material = km
    app.state.attachment_blob_store = blob_store
    app.state.attachment_service = AttachmentService(blob_store, km.session_hmac_key)

    # Use database rate limiter backed by pg_worker_db
    app_engine = app.state.session_factory._engine
    app.state.rate_limiter = PgRateLimiter(engine=app_engine)

    # Supply CSRF token and cookie for mutating API requests (KB-P2-02 CsrfMiddleware)
    csrf_tok = generate_csrf_token(PRE_SESSION_ID, km.session_hmac_key)
    env.client.headers[CSRF_HEADER_NAME] = csrf_tok
    env.client.cookies.set(CSRF_COOKIE_NAME, csrf_tok)
    return km, blob_store


async def test_case_1_raster_roundtrip_exif_strip(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
    tmp_path: Path,
) -> None:
    """Case 1: Upload JPEG with EXIF GPS; verify 201, stripped EXIF, zero trailing bytes."""
    _setup_api_app_state(api_env, tmp_path)
    user = await make_user("uploader")
    proj_id = await make_project("ATT1", created_by=user, roles={user: "MEMBER"})

    client = as_principal(user)
    raw_payload, polyglot = _make_jpeg_payload()

    # Upload via multipart
    resp = await client.post(
        "/api/v1/projects/ATT1/attachments",
        files={"file": ("photo.jpg", raw_payload, "image/jpeg")},
    )
    contract_recorder.record("attachment_upload_201", resp.request, resp)
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["content_type"] == "image/jpeg"
    assert data["markdown_uri"] == f"attachment://att_{data['id']}"
    assert data["byte_size"] > 0
    assert data["pixel_width"] == 64
    assert data["pixel_height"] == 64
    assert "signed_url" in data
    assert data["expires_in"] == 300

    # Verify Activity Ledger recorded ATTACHMENT_UPLOADED
    await api_env.seed.rollback()
    act_row = (
        (
            await api_env.seed.execute(
                text(
                    "SELECT event_type, payload FROM activity_records "
                    "WHERE object_id = :proj_id ORDER BY recorded_at DESC LIMIT 1"
                ),
                {"proj_id": proj_id},
            )
        )
        .mappings()
        .first()
    )
    assert act_row is not None
    assert act_row["event_type"] == "ATTACHMENT_UPLOADED"
    assert act_row["payload"]["attachment_id"] == data["id"]

    # Fetch content via signed_url
    content_resp = await client.get(data["signed_url"])
    assert content_resp.status_code == 200
    assert content_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert content_resp.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert content_resp.headers["Cache-Control"] == "private, max-age=300"
    assert 'filename="photo.jpg"' in content_resp.headers["Content-Disposition"]
    assert "inline" in content_resp.headers["Content-Disposition"]

    # Verify 0 polyglot bytes
    downloaded = content_resp.content
    assert polyglot not in downloaded

    # Verify 0 EXIF / GPS tags survive
    im = Image.open(io.BytesIO(downloaded))
    exif = im.getexif()
    assert len(exif) == 0
    assert len(exif.get_ifd(0x8825)) == 0


async def test_case_2_svg_upload_and_sec_fetch_dest_shield(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
    tmp_path: Path,
) -> None:
    """Case 2: SVG upload scrubs <script>; GET checks Sec-Fetch-Dest inline vs attachment shield."""
    _setup_api_app_state(api_env, tmp_path)
    user = await make_user("designer")
    await make_project("SVGPROJ", created_by=user, roles={user: "MEMBER"})

    client = as_principal(user)
    svg_raw = (
        b"<svg xmlns='http://www.w3.org/2000/svg' width='100' height='60'>"
        b"<rect width='80' height='40' fill='green'/>"
        b"<script>alert(1)</script>"
        b"</svg>"
    )

    upload_resp = await client.post(
        "/api/v1/projects/SVGPROJ/attachments",
        files={"file": ("diagram.svg", svg_raw, "image/svg+xml")},
    )
    assert upload_resp.status_code == 201, upload_resp.text
    att = upload_resp.json()
    assert att["content_type"] == "image/svg+xml"

    # Fetch with Sec-Fetch-Dest: image -> inline + CSP sandbox
    resp_image = await client.get(
        att["signed_url"],
        headers={"Sec-Fetch-Dest": "image"},
    )
    contract_recorder.record("svg_content_fetch_dest_image", resp_image.request, resp_image)
    assert resp_image.status_code == 200
    assert resp_image.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert resp_image.headers["X-Content-Type-Options"] == "nosniff"
    assert "inline" in resp_image.headers["Content-Disposition"]
    assert b"<script" not in resp_image.content
    assert b"<rect" in resp_image.content

    # Fetch with Sec-Fetch-Dest: document -> attachment + CSP sandbox
    resp_doc = await client.get(
        att["signed_url"],
        headers={"Sec-Fetch-Dest": "document"},
    )
    contract_recorder.record("svg_content_fetch_dest_document", resp_doc.request, resp_doc)
    assert resp_doc.status_code == 200
    assert resp_doc.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert "attachment" in resp_doc.headers["Content-Disposition"]

    # Fetch with no Sec-Fetch-Dest header -> attachment + CSP sandbox
    resp_no_dest = await client.get(att["signed_url"])
    assert resp_no_dest.status_code == 200
    assert resp_no_dest.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert "attachment" in resp_no_dest.headers["Content-Disposition"]


async def test_case_3_magic_byte_spoofing(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
    tmp_path: Path,
) -> None:
    """Case 3: Reject spoofed magic bytes, HTML as SVG, and script as PNG with 415."""
    _setup_api_app_state(api_env, tmp_path)
    user = await make_user("attacker")
    await make_project("SPOOF", created_by=user, roles={user: "MEMBER"})
    client = as_principal(user)

    # 1. HTML named diagram.svg with Content-Type: image/svg+xml
    html_bytes = b"<!DOCTYPE html><html><body>XSS</body></html>"
    r1 = await client.post(
        "/api/v1/projects/SPOOF/attachments",
        files={"file": ("diagram.svg", html_bytes, "image/svg+xml")},
    )
    contract_recorder.record("attachment_upload_415_html", r1.request, r1)
    assert r1.status_code == 415
    assert r1.json()["code"] == "MIME_MISMATCH_OR_UNSUPPORTED"

    # 2. PNG bytes named icon.svg
    png_im = Image.new("RGB", (10, 10))
    pbuf = io.BytesIO()
    png_im.save(pbuf, format="PNG")
    r2 = await client.post(
        "/api/v1/projects/SPOOF/attachments",
        files={"file": ("icon.svg", pbuf.getvalue(), "image/svg+xml")},
    )
    assert r2.status_code == 415
    assert r2.json()["code"] == "MIME_MISMATCH_OR_UNSUPPORTED"

    # 3. <script> named photo.png
    script_bytes = b"<script>alert(1)</script>"
    r3 = await client.post(
        "/api/v1/projects/SPOOF/attachments",
        files={"file": ("photo.png", script_bytes, "image/png")},
    )
    assert r3.status_code == 415
    assert r3.json()["code"] == "MIME_MISMATCH_OR_UNSUPPORTED"


async def test_case_4_decompression_bomb(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
    tmp_path: Path,
) -> None:
    """Case 4: Synthetic 10000x5000 PNG rejected with 422 IMAGE_DIMENSIONS_EXCEEDED."""
    _setup_api_app_state(api_env, tmp_path)
    user = await make_user("bombuser")
    await make_project("BOMBPROJ", created_by=user, roles={user: "MEMBER"})
    client = as_principal(user)

    bomb_bytes = _create_synthetic_png_header(10000, 5000)
    resp = await client.post(
        "/api/v1/projects/BOMBPROJ/attachments",
        files={"file": ("bomb.png", bomb_bytes, "image/png")},
    )
    contract_recorder.record("attachment_upload_422_decompression_bomb", resp.request, resp)
    assert resp.status_code == 422
    assert resp.json()["code"] == "IMAGE_DIMENSIONS_EXCEEDED"


async def test_case_5_streaming_cap_boundary(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
    tmp_path: Path,
) -> None:
    """Case 5: 26,214,401-byte upload rejected with 413 and zero files written to disk."""
    _, blob_store = _setup_api_app_state(api_env, tmp_path)
    user = await make_user("heavyuser")
    await make_project("HEAVY", created_by=user, roles={user: "MEMBER"})
    client = as_principal(user)

    oversized_data = b"A" * (MAX_ATTACHMENT_BYTES + 1)
    resp = await client.post(
        "/api/v1/projects/HEAVY/attachments",
        content=oversized_data,
        headers={"Content-Type": "image/png", "X-Filename": "huge.png"},
    )
    contract_recorder.record("attachment_upload_413_oversized", resp.request, resp)
    assert resp.status_code == 413
    assert resp.json()["code"] == "PAYLOAD_TOO_LARGE"

    # Zero files written to blob store
    stored_files = list(blob_store.root_dir.rglob("*"))
    actual_files = [f for f in stored_files if f.is_file()]
    assert len(actual_files) == 0


async def test_case_6_path_traversal_filename(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
) -> None:
    """Case 6: Path traversal filename sanitized in DB and Content-Disposition; stored by sha256."""
    _setup_api_app_state(api_env, tmp_path)
    user = await make_user("traversaluser")
    await make_project("TRAV", created_by=user, roles={user: "MEMBER"})
    client = as_principal(user)

    im = Image.new("RGB", (10, 10), color="yellow")
    buf = io.BytesIO()
    im.save(buf, format="PNG")

    dirty_filename = "../../etc/passwd\x00.png"
    resp = await client.post(
        "/api/v1/projects/TRAV/attachments",
        files={"file": (dirty_filename, buf.getvalue(), "image/png")},
    )
    assert resp.status_code == 201
    att_id = resp.json()["id"]

    # Verify DB original_filename has no traversal or null bytes
    await api_env.seed.rollback()
    row = (
        (
            await api_env.seed.execute(
                text("SELECT original_filename, storage_key FROM attachments WHERE id = :id"),
                {"id": uuid.UUID(att_id)},
            )
        )
        .mappings()
        .first()
    )
    assert row is not None
    assert "/" not in row["original_filename"]
    assert "\\" not in row["original_filename"]
    assert "\x00" not in row["original_filename"]
    assert row["storage_key"].startswith("sha256/")

    # Fetch content and verify safe Content-Disposition
    fetch_resp = await client.get(resp.json()["signed_url"])
    cd = fetch_resp.headers["Content-Disposition"]
    assert "/" not in cd
    assert "\\" not in cd
    assert ".." not in cd


async def test_case_7_signed_url_security_and_revocation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
) -> None:
    """Case 7: Signed URL tamper, expiry, cross-user replay (403) and live ACL revocation (404)."""
    _setup_api_app_state(api_env, tmp_path)
    u1 = await make_user("user1")
    u2 = await make_user("user2")
    proj_id = await make_project("SECACL", created_by=u1, roles={u1: "MEMBER", u2: "MEMBER"})

    client1 = as_principal(u1)

    im = Image.new("RGB", (10, 10))
    buf = io.BytesIO()
    im.save(buf, format="PNG")

    upload_resp = await client1.post(
        "/api/v1/projects/SECACL/attachments",
        files={"file": ("test.png", buf.getvalue(), "image/png")},
    )
    assert upload_resp.status_code == 201
    signed_url = upload_resp.json()["signed_url"]

    # 1. Tampered signature -> 403
    tampered_url = signed_url[:-4] + "xxxx"
    r_tamper = await client1.get(tampered_url)
    assert r_tamper.status_code == 403
    assert r_tamper.json()["code"] == "INVALID_SIGNED_URL"

    # 2. Expired signature -> 403
    # Replace exp with past timestamp
    url_base, query = signed_url.split("?")
    params = dict(q.split("=") for q in query.split("&"))
    params["exp"] = "100"  # past
    expired_url = f"{url_base}?exp=100&p={params['p']}&sig={params['sig']}"
    r_expired = await client1.get(expired_url)
    assert r_expired.status_code == 403
    assert r_expired.json()["code"] == "INVALID_SIGNED_URL"

    # 3. Cross-user replay: URL minted for U1 requested by U2 -> 403
    client2 = as_principal(u2)
    r_replay = await client2.get(signed_url)
    assert r_replay.status_code == 403
    assert r_replay.json()["code"] == "INVALID_SIGNED_URL"

    # 4. Live ACL revocation: U1 granted DENY VIEW at t=10, fetches at t=20 -> 404 NOT_FOUND
    client1 = as_principal(u1)
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        u1.id,
        effect="DENY",
        capability_mask=1,  # VIEW
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    r_revoked = await client1.get(signed_url)
    assert r_revoked.status_code == 404
    assert r_revoked.json()["code"] == "NOT_FOUND"


async def test_case_8_anti_enumeration_and_rate_limit(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
) -> None:
    """Case 8: Anti-enumeration 404 on unreadable/missing; 31st upload returns 429."""
    _setup_api_app_state(api_env, tmp_path)
    admin = await make_user("adminuser")
    viewer = await make_user("vieweruser")
    outsider = await make_user("outsider")

    proj_id = await make_project("SECRET", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        viewer.id,
        effect="ALLOW",
        capability_mask=1,  # VIEW only
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Admin uploads attachment in secret project
    client_admin = as_principal(admin)
    im = Image.new("RGB", (10, 10))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    up_resp = await client_admin.post(
        "/api/v1/projects/SECRET/attachments",
        files={"file": ("sec.png", buf.getvalue(), "image/png")},
    )
    assert up_resp.status_code == 201
    secret_att_id = up_resp.json()["id"]

    # Outsider requests signed URL for non-existent vs secret attachment
    client_out = as_principal(outsider)
    random_id = str(uuid.uuid4())
    r_nonexistent = await client_out.post(f"/api/v1/attachments/{random_id}/signed-url")
    r_unreadable = await client_out.post(f"/api/v1/attachments/{secret_att_id}/signed-url")

    # Identical 404 NOT_FOUND anti-enumeration discipline
    assert r_nonexistent.status_code == 404
    assert r_unreadable.status_code == 404
    assert r_nonexistent.json()["code"] == r_unreadable.json()["code"] == "NOT_FOUND"

    # Viewer (VIEW only) attempting upload -> 403 INSUFFICIENT_CAPABILITY
    client_viewer = as_principal(viewer)
    r_view_only = await client_viewer.post(
        "/api/v1/projects/SECRET/attachments",
        files={"file": ("sec.png", buf.getvalue(), "image/png")},
    )
    assert r_view_only.status_code == 403
    assert r_view_only.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # Outsider (no VIEW) attempting upload -> 404 NOT_FOUND
    client_out = as_principal(outsider)
    r_no_view = await client_out.post(
        "/api/v1/projects/SECRET/attachments",
        files={"file": ("sec.png", buf.getvalue(), "image/png")},
    )
    assert r_no_view.status_code == 404
    assert r_no_view.json()["code"] == "NOT_FOUND"

    # Rate limiting: 30 uploads allowed within 60s, 31st returns 429
    # Switch back to admin
    client_admin = as_principal(admin)
    # Admin has already made 1 upload above. Let's make 29 more (total 30)
    for _ in range(29):
        resp = await client_admin.post(
            "/api/v1/projects/SECRET/attachments",
            files={"file": ("sec.png", buf.getvalue(), "image/png")},
        )
        assert resp.status_code == 201

    # 31st upload must be rejected with 429 RATE_LIMITED
    r_31 = await client_admin.post(
        "/api/v1/projects/SECRET/attachments",
        files={"file": ("sec.png", buf.getvalue(), "image/png")},
    )
    assert r_31.status_code == 429
    assert r_31.json()["code"] == "RATE_LIMITED"
    assert "Retry-After" in r_31.headers


async def test_case_9_issue_attachment_and_raw_upload(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
) -> None:
    """Case 9: Raw binary upload and issue-scoped attachment creation & signed-url minting."""
    _setup_api_app_state(api_env, tmp_path)
    user = await make_user("issueowner")
    proj_id = await make_project("ISSPROJ", created_by=user, roles={user: "MEMBER"})
    client = as_principal(user)

    # 1. Raw binary upload with x-filename header
    im = Image.new("RGB", (32, 32), color="purple")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    raw_data = buf.getvalue()

    raw_resp = await client.post(
        "/api/v1/projects/ISSPROJ/attachments",
        content=raw_data,
        headers={"Content-Type": "image/png", "X-Filename": "raw_capture.png"},
    )
    assert raw_resp.status_code == 201
    raw_data_json = raw_resp.json()
    assert raw_data_json["byte_size"] > 0
    att_id = raw_data_json["id"]

    # 2. Call POST /api/v1/attachments/{id}/signed-url directly
    mint_resp = await client.post(f"/api/v1/attachments/{att_id}/signed-url")
    assert mint_resp.status_code == 200
    mint_json = mint_resp.json()
    assert "signed_url" in mint_json
    assert mint_json["expires_in"] == 300

    # 3. Create an issue in the project
    state_id = await api_env.seed.scalar(
        text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
        {"p": proj_id},
    )
    prio_id = await api_env.seed.scalar(
        text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
        {"p": proj_id},
    )
    seq = await api_env.seed.scalar(
        text("SELECT allocate_issue_sequence(:p)"),
        {"p": proj_id},
    )
    issue_id = await api_env.seed.scalar(
        text("SELECT register_object('issue', :ws, :p, :ident, 'Issue for attachment', :u)"),
        {
            "ws": api_env.workspace_id,
            "p": proj_id,
            "ident": f"ISSPROJ-{seq}",
            "u": user.id,
        },
    )
    await api_env.seed.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
            "state_id, priority_id, summary, created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, :seq, :st, :pr, 'Attachment Issue', :creator, '0|hzzzzz:')"
        ),
        {
            "id": issue_id,
            "ws": api_env.workspace_id,
            "proj": proj_id,
            "seq": seq,
            "st": state_id,
            "pr": prio_id,
            "creator": user.id,
        },
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Upload attachment attached to this issue via multipart
    issue_att_resp = await client.post(
        "/api/v1/projects/ISSPROJ/attachments",
        data={"issue_id": str(issue_id)},
        files={"file": ("issue_shot.png", raw_data, "image/png")},
    )
    assert issue_att_resp.status_code == 201
    issue_att_id = issue_att_resp.json()["id"]

    # Verify attachment is linked to the issue in database
    row = (
        await api_env.seed.execute(
            text("SELECT issue_id FROM attachments WHERE id = :id"),
            {"id": issue_att_id},
        )
    ).scalar_one()
    assert str(row) == str(issue_id)

    # Call POST /api/v1/attachments/{issue_att_id}/signed-url
    iss_mint_resp = await client.post(f"/api/v1/attachments/{issue_att_id}/signed-url")
    assert iss_mint_resp.status_code == 200
    assert "signed_url" in iss_mint_resp.json()

    # 4. Upload with non-existent issue_id -> 404
    non_existent_issue = str(uuid.uuid4())
    bad_iss_resp = await client.post(
        "/api/v1/projects/ISSPROJ/attachments",
        data={"issue_id": non_existent_issue},
        files={"file": ("fail.png", raw_data, "image/png")},
    )
    assert bad_iss_resp.status_code == 404

    # 5. Raw upload with filename and issue_id in query params
    query_resp = await client.post(
        f"/api/v1/projects/ISSPROJ/attachments?filename=query.png&issue_id={issue_id}",
        content=raw_data,
        headers={"Content-Type": "image/png"},
    )
    assert query_resp.status_code == 201

    # 6. Issue with DENY COMMENT and DENY EDIT -> 403 INSUFFICIENT_CAPABILITY
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        issue_id,
        user.id,
        effect="DENY",
        capability_mask=6,  # COMMENT (2) | EDIT (4)
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    deny_comment_resp = await client.post(
        f"/api/v1/projects/ISSPROJ/attachments?issue_id={issue_id}",
        content=raw_data,
        headers={"Content-Type": "image/png"},
    )
    assert deny_comment_resp.status_code == 403
    assert deny_comment_resp.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 7. Issue with DENY VIEW -> 404 NOT_FOUND
    await api_env.seed.execute(
        text(
            "DELETE FROM resource_acl_entries "
            "WHERE object_id = :obj AND principal_id = :p AND effect = 'DENY'"
        ),
        {"obj": issue_id, "p": user.id},
    )
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        issue_id,
        user.id,
        effect="DENY",
        capability_mask=1,  # VIEW
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    deny_view_resp = await client.post(
        f"/api/v1/projects/ISSPROJ/attachments?issue_id={issue_id}",
        content=raw_data,
        headers={"Content-Type": "image/png"},
    )
    assert deny_view_resp.status_code == 404
    assert deny_view_resp.json()["code"] == "NOT_FOUND"


async def test_case_10_app_state_fallback(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 10: AttachmentService construction fallback when state is not pre-populated."""
    monkeypatch.setenv("KANBAN_ATTACHMENT_DIR", str(tmp_path / "fallback-attachments"))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE=")
    # Ensure rate limiter uses the test database engine
    app = api_env.client._transport.app  # type: ignore[attr-defined]
    app_engine = app.state.session_factory._engine
    app.state.rate_limiter = PgRateLimiter(engine=app_engine)
    # Clear any pre-existing attachment state
    app.state.attachment_service = None
    app.state.attachment_blob_store = None

    user = await make_user("fallbackuser")
    await make_project("FALLPROJ", created_by=user, roles={user: "MEMBER"})
    client = as_principal(user)

    fallback_csrf = generate_csrf_token(PRE_SESSION_ID, b"\x00" * 32)
    client.headers[CSRF_HEADER_NAME] = fallback_csrf
    client.cookies.set(CSRF_COOKIE_NAME, fallback_csrf)

    im = Image.new("RGB", (10, 10))
    buf = io.BytesIO()
    im.save(buf, format="PNG")

    resp = await client.post(
        "/api/v1/projects/FALLPROJ/attachments",
        files={"file": ("test.png", buf.getvalue(), "image/png")},
    )
    assert resp.status_code == 201


async def test_case_11_empty_body_and_content_disposition_upload(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
) -> None:
    """Case 11: Empty payload returns 415; Content-Disposition header filename is parsed."""
    _setup_api_app_state(api_env, tmp_path)
    user = await make_user("cduser")
    await make_project("CDPROJ", created_by=user, roles={user: "MEMBER"})
    client = as_principal(user)

    # Empty payload
    r_empty = await client.post(
        "/api/v1/projects/CDPROJ/attachments",
        content=b"",
        headers={"Content-Type": "image/png"},
    )
    assert r_empty.status_code == 415

    # Content-Disposition header with filename
    im = Image.new("RGB", (16, 16))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    r_cd = await client.post(
        "/api/v1/projects/CDPROJ/attachments",
        content=buf.getvalue(),
        headers={
            "Content-Type": "image/png",
            "Content-Disposition": 'attachment; filename="cd_pic.png"',
        },
    )
    assert r_cd.status_code == 201
    cd_att_id = r_cd.json()["id"]
    row_fn = (
        await api_env.seed.execute(
            text("SELECT original_filename FROM attachments WHERE id = :id"),
            {"id": cd_att_id},
        )
    ).scalar_one()
    assert row_fn == "cd_pic.png"
