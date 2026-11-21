# ruff: noqa: SLF001
# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for PDF attachment upload, signed URL, and security headers (KAN-81)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kanban.attachments.service import AttachmentService
from kanban.attachments.storage import LocalFilesystemBlobStore
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    PRE_SESSION_ID,
    generate_csrf_token,
)
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit.pg import PgRateLimiter
from kanban.tests.attachments.test_pdf_validation import SAMPLE_VALID_PDF, _make_pdf_with_content

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


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

    app_engine = app.state.session_factory._engine
    app.state.rate_limiter = PgRateLimiter(engine=app_engine)

    csrf_tok = generate_csrf_token(PRE_SESSION_ID, km.session_hmac_key)
    env.client.headers[CSRF_HEADER_NAME] = csrf_tok
    env.client.cookies.set(CSRF_COOKIE_NAME, csrf_tok)
    return km, blob_store


async def test_pdf_upload_roundtrip_and_headers(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
) -> None:
    """Upload valid PDF, verify 201 response, page_count, and forced-download security headers."""
    _setup_api_app_state(api_env, tmp_path)
    user = await make_user("pdf_uploader")
    proj_id = await make_project("PDF1", created_by=user, roles={user: "MEMBER"})
    client = as_principal(user)

    # 1. Upload valid PDF
    files = {"file": ("architecture-spec.pdf", SAMPLE_VALID_PDF, "application/pdf")}
    res = await client.post(f"/api/v1/projects/{proj_id}/attachments", files=files)
    assert res.status_code == 201, res.text
    data = res.json()

    assert data["content_type"] == "application/pdf"
    assert data["byte_size"] == len(SAMPLE_VALID_PDF)
    assert data["page_count"] == 1
    assert data["markdown_uri"].startswith("attachment://att_")
    attachment_id = data["id"]
    signed_url = data["signed_url"]

    # 2. Retrieve attachment direct
    direct_res = await client.get(f"/api/v1/attachments/{attachment_id}")
    assert direct_res.status_code == 200
    assert (
        direct_res.headers["content-disposition"] == 'attachment; filename="architecture-spec.pdf"'
    )
    assert direct_res.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert direct_res.headers["x-content-type-options"] == "nosniff"
    assert direct_res.headers["cross-origin-resource-policy"] == "same-origin"
    assert direct_res.content == SAMPLE_VALID_PDF

    # 3. Retrieve attachment via signed URL
    signed_res = await client.get(signed_url)
    assert signed_res.status_code == 200
    assert (
        signed_res.headers["content-disposition"] == 'attachment; filename="architecture-spec.pdf"'
    )
    assert signed_res.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert signed_res.headers["x-content-type-options"] == "nosniff"
    assert signed_res.content == SAMPLE_VALID_PDF


async def test_pdf_upload_rejects_active_javascript(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    tmp_path: Path,
) -> None:
    """Upload PDF with /JS active content and verify HTTP 422 UNSAFE_PDF_CONTENT rejection."""
    _setup_api_app_state(api_env, tmp_path)
    user = await make_user("malicious_uploader")
    proj_id = await make_project("PDF2", created_by=user, roles={user: "MEMBER"})
    client = as_principal(user)

    malicious_pdf = _make_pdf_with_content(b"/JS (app.alert('exploit'))")
    files = {"file": ("exploit.pdf", malicious_pdf, "application/pdf")}
    res = await client.post(f"/api/v1/projects/{proj_id}/attachments", files=files)
    assert res.status_code == 422, res.text
    problem = res.json()
    assert problem["code"] == "UNSAFE_PDF_CONTENT"
    assert "/JS" in problem["detail"]
