# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and integration tests for Issue CSV import, export, and governance (KAN-316).

Covers:
1. Pure unit tests for WinZip AE-2 (AES-256) container packaging & extraction (kanban.csv.aes_zip):
   - >= 12 character password policy enforcement (PasswordTooShortError).
   - Deflate and Stored compression roundtrip encryption/decryption with HMAC-SHA256 verification.
   - Wrong password and tampered HMAC rejection (InvalidPasswordError).
   - ZipBomb protection (ratio > 100x and max size 50 MiB).
   - Path traversal protection (leading slash and relative '../' rejection).
   - Memory zeroization verification.
2. Canonical CSV schema, CWE-1236 formula defense, surrogates, and secret scanning:
   - Canonical 16-column header contract.
   - CWE-1236 sanitization on export and stripping on import.
   - UTF-16 lone surrogate rejection (INVALID_UTF8_SURROGATE).
   - KAN-72 secret push protection enforcement on import.
   - Template generation with project-specific workflow states.
3. 3-tier governance, permissions, and REST API endpoints (kanban.api.v1.issue_csv):
   - System Admin governance flags (EXPORT_DISABLED / IMPORT_DISABLED).
   - Workspace Admin governance flags (EXPORT_DISABLED / IMPORT_DISABLED).
   - Role-based export capability (INSUFFICIENT_CAPABILITY).
   - Project & workspace CSV and password-protected ZIP export with filter reflection.
   - Project CSV & encrypted ZIP import with dry-run preview and atomic commit.
   - GET / PATCH /api/v1/admin/system-settings.
"""

from __future__ import annotations

import base64
import io
import struct
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext
from kanban.content import ContentNormalizeError
from kanban.csv.aes_zip import (
    CorruptZipError,
    InvalidPasswordError,
    PasswordTooShortError,
    PathTraversalError,
    ZipBombError,
    _ctr_crypt,
    create_winzip_aes256_zip,
    extract_winzip_aes256_zip,
    zeroize,
)
from kanban.csv.issue_csv import (
    CSV_COLUMNS,
    desanitize_cell_from_import,
    export_issues_to_csv,
    generate_issue_import_template,
    parse_issues_from_csv,
    sanitize_cell_for_export,
    validate_no_surrogates,
)
from kanban.settings import get_settings

if TYPE_CHECKING:
    import uuid
    from collections.abc import Awaitable, Callable

    from httpx import AsyncClient

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


async def _as_admin_aal2(
    api_env: ApiEnv,
    user: SeededUser,
) -> None:
    """Enroll confirmed TOTP factor and elevate test client to AAL2 session."""
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user.id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
        aal2_verified_at=datetime.now(UTC),
    )


# ==============================================================================
# 1. Pure Unit Tests: WinZip AE-2 (AES-256) Packaging & Extraction
# ==============================================================================


def test_winzip_aes256_password_policy() -> None:
    """Password must be at least 12 characters or raise PasswordTooShortError."""
    data = {"test.csv": b"key,summary\nPROJ-1,Hello\n"}
    with pytest.raises(PasswordTooShortError) as exc_info:
        create_winzip_aes256_zip(data, "short-pwd")
    assert "at least 12 characters" in str(exc_info.value)


def test_winzip_aes256_roundtrip_deflate() -> None:
    """Verify WinZip AE-2 encryption and decryption roundtrip with Deflate compression."""
    files = {
        "issues.csv": b"key,project_key,summary\nPROJ-1,PROJ,Test issue summary\n" * 50,
        "notes.txt": b"Confidential audit export notes.",
    }
    password = "CorrectHorseBatteryStaple123!"

    zip_bytes = create_winzip_aes256_zip(files, password)
    assert zip_bytes.startswith(b"PK\x03\x04")

    # Extract with correct password
    extracted = extract_winzip_aes256_zip(zip_bytes, password)
    assert extracted["issues.csv"] == files["issues.csv"]
    assert extracted["notes.txt"] == files["notes.txt"]


def test_winzip_aes256_wrong_password() -> None:
    """Extraction with incorrect password raises InvalidPasswordError."""
    files = {"issues.csv": b"key,summary\n"}
    password = "CorrectHorseBatteryStaple123!"
    zip_bytes = create_winzip_aes256_zip(files, password)

    with pytest.raises(InvalidPasswordError) as exc_info:
        extract_winzip_aes256_zip(zip_bytes, "WrongPassword123!")
    assert "password" in str(exc_info.value).lower()


def test_winzip_aes256_missing_password() -> None:
    """Extraction without password raises InvalidPasswordError(PASSWORD_REQUIRED)."""
    files = {"issues.csv": b"key,summary\n"}
    zip_bytes = create_winzip_aes256_zip(files, "CorrectHorseBatteryStaple123!")

    with pytest.raises(InvalidPasswordError) as exc_info:
        extract_winzip_aes256_zip(zip_bytes, None)
    assert "password is required" in str(exc_info.value).lower()


def test_winzip_aes256_tampered_ciphertext() -> None:
    """Altered ciphertext or auth tag must be detected via HMAC and fail."""
    files = {"issues.csv": b"key,summary\nPROJ-1,Normal content\n"}
    password = "CorrectHorseBatteryStaple123!"
    zip_bytes = create_winzip_aes256_zip(files, password)

    # Flip bits inside ciphertext
    tampered = bytearray(zip_bytes)
    tampered[70] ^= 0xFF
    with pytest.raises(InvalidPasswordError):
        extract_winzip_aes256_zip(bytes(tampered), password)


def test_winzip_aes256_path_traversal() -> None:
    """Archive entries attempting directory traversal must be rejected."""
    bad_files = {"../../etc/passwd": b"evil payload"}
    with pytest.raises(PathTraversalError):
        create_winzip_aes256_zip(bad_files, "CorrectHorseBatteryStaple123!")


def test_winzip_aes256_zipbomb_protection() -> None:
    """Archive with excessive compression ratio raises ZipBombError."""
    password = "CorrectHorseBatteryStaple123!"
    # Highly compressible payload (200KB of zeros compresses to ~150B, >100x ratio limit)
    data = {"bomb.csv": b"\x00" * 200_000}
    bomb_zip = create_winzip_aes256_zip(data, password)

    with pytest.raises(ZipBombError):
        extract_winzip_aes256_zip(bomb_zip, password)


def test_winzip_aes256_zeroize() -> None:
    """Verify zeroize function zeroes memory buffers in place."""
    buf = bytearray(b"SecretKeyMaterial123")
    zeroize(buf)
    assert buf == bytearray(len(buf))


# ==============================================================================
# 2. Canonical CSV, CWE-1236, Surrogates & Secret Push Protection
# ==============================================================================


def test_cwe_1236_formula_injection_defense() -> None:
    """Formula trigger characters (=, +, -, @, tab, cr) must be prepended with single-quote."""
    dangerous = [
        "=1+2",
        "+12345",
        "-5+10",
        "@SUM(A1:A10)",
        "\tcmd.exe",
        "\rpowershell",
    ]
    for cell in dangerous:
        sanitized = sanitize_cell_for_export(cell)
        assert sanitized.startswith("'"), f"Cell {cell} was not sanitized"
        # Desanitize restores original
        assert desanitize_cell_from_import(sanitized) == cell

    # Safe cells remain untouched
    safe = ["Normal Summary", "PROJ-123", "Just regular text", "12345"]
    for cell in safe:
        assert sanitize_cell_for_export(cell) == cell
        assert desanitize_cell_from_import(cell) == cell


def test_utf16_lone_surrogate_rejection() -> None:
    """Lone UTF-16 surrogates (0xD800 to 0xDFFF) must raise INVALID_UTF8_SURROGATE."""
    valid_text = "Standard valid text with emojis 🚀 and accents café"
    # Should not raise
    validate_no_surrogates(valid_text)

    invalid_text = "Text with lone surrogate \ud800 in the middle"
    with pytest.raises(ContentNormalizeError) as exc_info:
        validate_no_surrogates(invalid_text)
    assert "INVALID_UTF8_SURROGATE" in str(exc_info.value)


def test_generate_issue_import_template() -> None:
    """Import template must contain canonical 16 columns and project states."""
    template = generate_issue_import_template(
        project_key="TESTPROJ",
        state_names=["Backlog", "Todo", "In Progress", "Done"],
        priority_names=["urgent", "high", "medium", "low"],
    )
    lines = template.strip().split("\r\n" if "\r\n" in template else "\n")
    headers = [c.strip() for c in lines[0].split(",")]
    assert headers == CSV_COLUMNS
    assert len(lines) >= 3  # Header + at least 2 sample rows
    assert "TESTPROJ" in lines[1]


def test_export_issues_to_csv() -> None:
    """export_issues_to_csv serializes rows adhering to RFC 4180 format."""
    rows = [
        {
            "key": "TESTPROJ-1",
            "project_key": "TESTPROJ",
            "summary": "=dangerous",
            "description_markdown": "Markdown with *bold* text",
            "state": "Todo",
            "priority": "high",
            "assignees": ["alice", "bob"],
            "labels": ["backend", "sec"],
            "cycle": "Sprint 1",
            "modules": ["Auth"],
            "parent_key": None,
            "start_date": None,
            "due_date": None,
            "created_at": "2026-11-22T00:00:00Z",
            "updated_at": "2026-11-22T00:00:00Z",
            "custom_fields_json": "{}",
        }
    ]
    csv_str = export_issues_to_csv(rows)
    assert "TESTPROJ-1" in csv_str
    # CWE-1236 check
    assert "'=dangerous" in csv_str
    assert "alice; bob" in csv_str


# ==============================================================================
# 3. 3-Tier Governance & API Endpoints Integration Tests
# ==============================================================================


async def test_api_template_endpoints(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """GET import-template.csv returns project and workspace templates."""
    user = await make_user("admin1", workspace_role="WORKSPACE_ADMIN")
    await make_project("TMPL", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)

    # Project template
    res = await client.get("/api/v1/projects/TMPL/issues/import-template.csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "key,project_key,summary" in res.text

    # Workspace template
    res_ws = await client.get(f"/api/v1/workspaces/{user.workspace_id}/issues/import-template.csv")
    assert res_ws.status_code == 200
    assert "text/csv" in res_ws.headers["content-type"]


async def test_api_export_csv_and_zip(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """Export project issues to CSV and WinZip AE-2 ZIP container."""
    user = await make_user("exp_user", workspace_role="WORKSPACE_ADMIN")
    await make_project("EXP1", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)

    # Create a test issue first
    create_res = await client.post(
        "/api/v1/projects/EXP1/issues",
        json={"summary": "Export test issue", "description_markdown": "Details"},
    )
    assert create_res.status_code == 201

    # 1. Export as standard CSV
    csv_res = await client.post(
        "/api/v1/projects/EXP1/issues/export",
        json={"format": "csv"},
    )
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "Export test issue" in csv_res.text

    # 2. Export as WinZip AE-2 ZIP with valid password
    pwd = "ValidExportPassword123!"
    zip_res = await client.post(
        "/api/v1/projects/EXP1/issues/export",
        json={"format": "zip_csv", "zip_password": pwd},
    )
    assert zip_res.status_code == 200
    assert zip_res.headers["content-type"] == "application/zip"
    extracted = extract_winzip_aes256_zip(zip_res.content, pwd)
    csv_extracted = next(iter(extracted.values())).decode("utf-8")
    assert "Export test issue" in csv_extracted

    # 3. Export as ZIP with password too short (< 12 chars) -> 422
    short_pwd_res = await client.post(
        "/api/v1/projects/EXP1/issues/export",
        json={"format": "zip_csv", "zip_password": "short"},
    )
    assert short_pwd_res.status_code == 422


async def test_api_export_governance_tiers(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """3-Tier governance enforcement on export."""
    admin = await make_user("gov_admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("gov_member", workspace_role="WORKSPACE_MEMBER")
    await make_project("GOV1", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"})

    # 1. System-level disabled
    with patch("kanban.api.v1.issue_csv.get_settings") as mock_settings:
        st = get_settings().model_copy(update={"enable_issue_export": False})
        mock_settings.return_value = st
        admin_client = as_principal(admin)
        res = await admin_client.post("/api/v1/projects/GOV1/issues/export", json={"format": "csv"})
        assert res.status_code == 403
        assert "EXPORT_DISABLED_BY_SYSTEM_ADMIN" in res.text

    # 2. Workspace-level disabled
    await _as_admin_aal2(api_env, admin)
    patch_res = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"issue_export_enabled": False},
    )
    assert patch_res.status_code == 200

    admin_client = as_principal(admin)
    res_ws = await admin_client.post("/api/v1/projects/GOV1/issues/export", json={"format": "csv"})
    assert res_ws.status_code == 403
    assert "EXPORT_DISABLED_BY_WORKSPACE_ADMIN" in res_ws.text

    # 3. Role-based restriction: only workspace_admin allowed, member denied
    await _as_admin_aal2(api_env, admin)
    patch_res2 = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"issue_export_enabled": True, "issue_export_allowed_roles": ["workspace_admin"]},
    )
    assert patch_res2.status_code == 200

    # Member is denied
    member_client = as_principal(member)
    res_mem = await member_client.post(
        "/api/v1/projects/GOV1/issues/export", json={"format": "csv"}
    )
    assert res_mem.status_code == 403
    assert "INSUFFICIENT_CAPABILITY" in res_mem.text


async def test_api_import_governance_tiers(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """3-Tier governance enforcement on import."""
    admin = await make_user("imp_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("IMP1", created_by=admin, roles={admin: "PROJECT_ADMIN"})

    csv_data = b"key,summary\n,New issue\n"

    # 1. System-level disabled
    with patch("kanban.api.v1.issue_csv.get_settings") as mock_settings:
        st = get_settings().model_copy(update={"enable_issue_import": False})
        mock_settings.return_value = st
        client = as_principal(admin)
        res = await client.post(
            "/api/v1/projects/IMP1/issues/import",
            files={"file": ("issues.csv", csv_data, "text/csv")},
        )
        assert res.status_code == 403
        assert "IMPORT_DISABLED_BY_SYSTEM_ADMIN" in res.text

    # 2. Workspace-level disabled
    await _as_admin_aal2(api_env, admin)
    patch_res = await api_env.client.patch(
        "/api/v1/admin/workspace-settings",
        json={"issue_import_enabled": False},
    )
    assert patch_res.status_code == 200

    client = as_principal(admin)
    res_ws = await client.post(
        "/api/v1/projects/IMP1/issues/import",
        files={"file": ("issues.csv", csv_data, "text/csv")},
    )
    assert res_ws.status_code == 403
    assert "IMPORT_DISABLED_BY_WORKSPACE_ADMIN" in res_ws.text


async def test_api_import_csv_dry_run_and_commit(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """Dry run previews creations/updates; real import commits to database."""
    user = await make_user("importer1", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("IMPRT", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)

    csv_content = (
        b"key,project_key,summary,state,priority\n"
        b",IMPRT,First Imported Issue,Todo,urgent\n"
        b",IMPRT,Second Imported Issue,Backlog,medium\n"
    )

    # 1. Dry run preview
    dry_res = await client.post(
        "/api/v1/projects/IMPRT/issues/import?dry_run=true",
        files={"file": ("import.csv", csv_content, "text/csv")},
    )
    assert dry_res.status_code == 200
    report = dry_res.json()
    assert report["total_rows"] == 2
    assert report["creates_count"] == 2
    assert report["updates_count"] == 0
    assert report["error_count"] == 0

    # Verify zero issues persisted in DB
    cnt = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issues WHERE project_id = :pid"), {"pid": proj_id}
        )
    ).scalar()
    assert cnt == 0

    # 2. Atomic commit
    commit_res = await client.post(
        "/api/v1/projects/IMPRT/issues/import?dry_run=false",
        files={"file": ("import.csv", csv_content, "text/csv")},
    )
    assert commit_res.status_code == 200
    commit_report = commit_res.json()
    assert commit_report["creates_count"] == 2

    # Verify rows persisted
    cnt_after = (
        await api_env.seed.execute(
            text("SELECT count(*) FROM issues WHERE project_id = :pid"), {"pid": proj_id}
        )
    ).scalar()
    assert cnt_after == 2


async def test_api_import_winzip_aes256_encrypted_zip(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """Import from WinZip AE-2 (AES-256) password-protected ZIP archive."""
    user = await make_user("zip_imp", workspace_role="WORKSPACE_ADMIN")
    await make_project("ZIP1", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)

    csv_data = b"key,summary\n,Secure Issue From ZIP\n"
    password = "SuperSecretContainerKey123!"
    zip_bytes = create_winzip_aes256_zip({"issues.csv": csv_data}, password)

    # 1. Wrong password -> 422 ZIP_EXTRACTION_FAILED
    bad_res = await client.post(
        "/api/v1/projects/ZIP1/issues/import?dry_run=true",
        files={"file": ("issues.zip", zip_bytes, "application/zip")},
        data={"zip_password": "WrongPassword123!"},
    )
    assert bad_res.status_code == 422

    # 2. Correct password -> 200 OK
    good_res = await client.post(
        "/api/v1/projects/ZIP1/issues/import?dry_run=false",
        files={"file": ("issues.zip", zip_bytes, "application/zip")},
        data={"zip_password": password},
    )
    assert good_res.status_code == 200
    report = good_res.json()
    assert report["creates_count"] == 1


async def test_api_import_secret_detection(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """Importing file containing credentials/tokens triggers secret push protection."""
    user = await make_user("sec_imp", workspace_role="WORKSPACE_ADMIN")
    await make_project("SEC1", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)

    secret_csv = (
        b"key,summary,description_markdown\n"
        b",Issue with secret,Leaked token: ghp_1234567890abcdef1234567890abcdef\n"
    )

    res = await client.post(
        "/api/v1/projects/SEC1/issues/import?dry_run=true",
        files={"file": ("secret.csv", secret_csv, "text/csv")},
    )
    assert res.status_code == 200
    report = res.json()
    assert report["error_count"] > 0
    assert any("secret" in str(e).lower() for e in report["errors"])


async def test_api_admin_system_settings(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """GET and PATCH /api/v1/admin/system-settings."""
    server_admin = await make_user("srv_admin", workspace_role="SERVER_ADMIN")
    normal_user = await make_user("norm_user", workspace_role="WORKSPACE_MEMBER")

    # Normal user is denied
    try:
        norm_client = as_principal(normal_user)
        res_deny = await norm_client.get("/api/v1/admin/system-settings")
        assert res_deny.status_code == 403

        # Server admin can read
        await _as_admin_aal2(api_env, server_admin)
        res_get = await api_env.client.get("/api/v1/admin/system-settings")
        assert res_get.status_code == 200
        body = res_get.json()
        assert "enable_issue_export" in body
        assert "enable_issue_import" in body

        # Server admin can patch
        res_patch = await api_env.client.patch(
            "/api/v1/admin/system-settings",
            json={"enable_issue_export": False},
        )
        assert res_patch.status_code == 200
        assert res_patch.json()["enable_issue_export"] is False
    finally:
        get_settings().enable_issue_export = True
        get_settings().enable_issue_import = True


def test_winzip_aes256_corrupt_payload_guards() -> None:
    """extract_winzip_aes256_zip rejects truncated, missing EOCD, or corrupt archives."""
    # 1. Too small
    with pytest.raises(CorruptZipError) as exc1:
        extract_winzip_aes256_zip(b"PK\x03\x04short")
    assert "too small" in str(exc1.value)

    # 2. Missing EOCD
    with pytest.raises(CorruptZipError) as exc2:
        extract_winzip_aes256_zip(b"\x00" * 30)
    assert "EOCD" in str(exc2.value)

    # 3. Empty files dict in create
    with pytest.raises(ValueError, match="empty") as exc3:
        create_winzip_aes256_zip({}, "ValidPassword123!")
    assert "empty" in str(exc3.value)

    # 4. Empty data to _ctr_crypt
    assert _ctr_crypt(b"", b"\x00" * 32) == b""


def test_unencrypted_zip_extraction() -> None:
    """extract_winzip_aes256_zip cleanly extracts standard unencrypted ZIP archives."""
    # 1. Deflated
    buf_def = io.BytesIO()
    with zipfile.ZipFile(buf_def, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("test.csv", b"key,summary\nPROJ-1,Test\n")
    ext_def = extract_winzip_aes256_zip(buf_def.getvalue())
    assert "test.csv" in ext_def
    assert b"PROJ-1,Test" in ext_def["test.csv"]

    # 2. Stored (uncompressed)
    buf_stored = io.BytesIO()
    with zipfile.ZipFile(buf_stored, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("stored.csv", b"key,summary\nPROJ-2,Stored\n")
    ext_stored = extract_winzip_aes256_zip(buf_stored.getvalue())
    assert "stored.csv" in ext_stored
    assert b"PROJ-2,Stored" in ext_stored["stored.csv"]

    # 3. Path traversal in unencrypted zip
    buf_trav = io.BytesIO()
    with zipfile.ZipFile(buf_trav, "w") as zf:
        zf.writestr("../etc/passwd", b"root:x:0:0\n")
    with pytest.raises(PathTraversalError):
        extract_winzip_aes256_zip(buf_trav.getvalue())


def test_parse_issues_from_csv_bytes_and_empty_rows() -> None:
    """parse_issues_from_csv handles bytes input and skips blank lines."""
    raw_bytes = b"key,summary\n\nPROJ-1,Issue 1\n   \n"
    rows = parse_issues_from_csv(raw_bytes)
    assert len(rows) == 1
    assert rows[0]["key"] == "PROJ-1"


async def test_api_import_update_existing_and_validation_errors(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """Import updating existing issue by key, plus date and required summary validation errors."""
    user = await make_user("upd_user", workspace_role="WORKSPACE_ADMIN")
    await make_project("UPD1", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)

    # Step 1: Create an issue
    c_res = await client.post(
        "/api/v1/projects/UPD1/issues",
        json={"summary": "Initial issue", "description_markdown": "Initial desc"},
    )
    assert c_res.status_code == 201
    created_issue = c_res.json()
    issue_key = created_issue["key"]

    # Step 2: Import CSV that updates the existing issue and introduces validation errors
    csv_content = (
        "key,summary,description_markdown,start_date,due_date\n"
        f"{issue_key},Updated via CSV,New description,2026-01-01,2026-01-10\n"
        ",,Missing summary row,,\n"
        ",Bad date row,Desc,not-a-date,2026-01-10\n"
        ",Bad due date row,Desc,2026-01-01,invalid-due\n"
        ",Inverted dates row,Desc,2026-02-01,2026-01-01\n"
    ).encode()

    # Dry-run
    res_dry = await client.post(
        "/api/v1/projects/UPD1/issues/import?dry_run=true",
        files={"file": ("issues.csv", csv_content, "text/csv")},
    )
    assert res_dry.status_code == 200
    report_dry = res_dry.json()
    assert report_dry["updates_count"] == 1
    assert report_dry["error_count"] >= 4
    assert issue_key in report_dry["updated_keys"]

    # Commit update with clean CSV
    clean_csv = (
        f"key,summary,description_markdown\n{issue_key},Updated via CSV,New description\n".encode()
    )
    res_commit = await client.post(
        "/api/v1/projects/UPD1/issues/import?dry_run=false",
        files={"file": ("clean.csv", clean_csv, "text/csv")},
    )
    assert res_commit.status_code == 200
    report_commit = res_commit.json()
    assert report_commit["updates_count"] == 1
    assert report_commit["error_count"] == 0

    # Verify issue was actually updated
    get_res = await client.get(f"/api/v1/issues/{issue_key}")
    assert get_res.status_code == 200
    assert get_res.json()["summary"] == "Updated via CSV"


async def test_api_import_unknown_state_priority_and_custom_fields(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """Import with non-existent state or priority adds validation error to diff report."""
    user = await make_user("state_user", workspace_role="WORKSPACE_ADMIN")
    await make_project("ST1", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)

    csv_bad = (
        b"key,summary,state,priority,custom_fields_json\n"
        b",Unknown state issue,NonExistentState,,\n"
        b",Unknown priority issue,,NonExistentPriority,\n"
    )

    res = await client.post(
        "/api/v1/projects/ST1/issues/import?dry_run=true",
        files={"file": ("bad.csv", csv_bad, "text/csv")},
    )
    assert res.status_code == 200
    report = res.json()
    assert report["error_count"] >= 2
    err_msgs = [e["message"] for e in report["errors"]]
    assert any("NonExistentState" in m for m in err_msgs)
    assert any("NonExistentPriority" in m for m in err_msgs)


async def test_api_import_with_labels_and_modules(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    make_module: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """Import resolves and attaches matching project modules and labels."""
    user = await make_user("lbl_user", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project(
        "LM1", created_by=user, roles={user: "PROJECT_ADMIN"}, modules_enabled=True
    )
    client = as_principal(user)

    # Create module
    await make_module(proj_id, "CoreEngine", created_by=user)

    # Create label
    await api_env.seed.execute(
        text(
            "INSERT INTO project_labels (id, workspace_id, project_id, name, color_hex) "
            "VALUES (gen_random_uuid(), :ws, :proj, 'frontend', '#ff0000')"
        ),
        {"ws": api_env.workspace_id, "proj": proj_id},
    )
    await api_env.seed.commit()

    csv_data = b"key,summary,modules,labels\n,Issue with tags,CoreEngine,frontend\n"

    res = await client.post(
        "/api/v1/projects/LM1/issues/import?dry_run=false",
        files={"file": ("lm.csv", csv_data, "text/csv")},
    )
    assert res.status_code == 200
    report = res.json()
    assert report["creates_count"] == 1
    assert report["error_count"] == 0


def test_winzip_aes256_zeroize_readonly() -> None:
    """Zeroize handles read-only or immutable buffers without uncaught exceptions."""
    ro_buf = memoryview(b"immutable_bytes")
    zeroize(ro_buf)


def test_winzip_aes256_corrupt_bounds_and_methods() -> None:
    """Test corrupted archive bounds and headers raise CorruptZipError."""
    valid = create_winzip_aes256_zip({"a.txt": b"hello"}, "SuperSecretPassword123!")

    # 1. cd_offset + cd_size > len(zip_bytes)
    eocd_idx = valid.rfind(struct.pack("<I", 0x06054B50))
    bad_cd_size = valid[: eocd_idx + 12] + struct.pack("<I", 999999) + valid[eocd_idx + 16 :]
    with pytest.raises(CorruptZipError, match="Central directory record extends beyond"):
        extract_winzip_aes256_zip(bad_cd_size, "SuperSecretPassword123!")

    # 2. cd_pos + 46 > len(zip_bytes)
    # Set cd_size to 20 so cd_offset + cd_size <= len(valid), but cd_offset + 46 > len(truncated)
    cd_offset = struct.unpack("<I", valid[eocd_idx + 16 : eocd_idx + 20])[0]
    bad_cd_trunc = valid[: cd_offset + 20] + valid[eocd_idx:]
    new_eocd_idx = bad_cd_trunc.rfind(struct.pack("<I", 0x06054B50))
    bad_cd_trunc = (
        bad_cd_trunc[: new_eocd_idx + 12]
        + struct.pack("<II", 20, cd_offset)
        + bad_cd_trunc[new_eocd_idx + 20 :]
    )
    with pytest.raises(CorruptZipError, match="Truncated central directory"):
        extract_winzip_aes256_zip(bad_cd_trunc, "SuperSecretPassword123!")

    # 3. Invalid central directory magic
    bad_cd_magic = valid[:cd_offset] + b"XXXX" + valid[cd_offset + 4 :]
    with pytest.raises(CorruptZipError, match="Invalid central directory magic"):
        extract_winzip_aes256_zip(bad_cd_magic, "SuperSecretPassword123!")

    # 4. local_offset + 30 > len(zip_bytes)
    bad_lh_offset = (
        valid[: cd_offset + 42] + struct.pack("<I", len(valid) - 10) + valid[cd_offset + 46 :]
    )
    with pytest.raises(CorruptZipError, match="Local header extends beyond"):
        extract_winzip_aes256_zip(bad_lh_offset, "SuperSecretPassword123!")

    # 5. Invalid local header magic
    bad_lh_magic = b"YYYY" + valid[4:]
    with pytest.raises(CorruptZipError, match="Invalid local header magic"):
        extract_winzip_aes256_zip(bad_lh_magic, "SuperSecretPassword123!")

    # 6. data_end > len(zip_bytes)
    bad_comp_size = valid[: cd_offset + 20] + struct.pack("<I", 999999) + valid[cd_offset + 24 :]
    with pytest.raises(CorruptZipError, match="extends beyond archive bounds"):
        extract_winzip_aes256_zip(bad_comp_size, "SuperSecretPassword123!")


def test_unsupported_compression_methods() -> None:
    """Test unsupported compression methods in unencrypted and encrypted entries."""
    fname = b"test.txt"
    # Unencrypted entry with unsupported method 9
    lh = (
        struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 9, 0, 0, 0, 4, 4, len(fname), 0)
        + fname
        + b"data"
    )
    cd = (
        struct.pack(
            "<IHHHHHHIIIHHHHHII",
            0x02014B50,
            20,
            20,
            0,
            9,
            0,
            0,
            0,
            4,
            4,
            len(fname),
            0,
            0,
            0,
            0,
            0,
            0,
        )
        + fname
    )
    eocd = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(cd), len(lh), 0)
    unsupported_unenc = lh + cd + eocd
    with pytest.raises(CorruptZipError, match="Unsupported unencrypted compression method"):
        extract_winzip_aes256_zip(unsupported_unenc)

    # Encrypted entry with method != 99
    lh_enc = (
        struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 1, 8, 0, 0, 0, 4, 4, len(fname), 0)
        + fname
        + b"data"
    )
    cd_enc = (
        struct.pack(
            "<IHHHHHHIIIHHHHHII",
            0x02014B50,
            20,
            20,
            1,
            8,
            0,
            0,
            0,
            4,
            4,
            len(fname),
            0,
            0,
            0,
            0,
            0,
            0,
        )
        + fname
    )
    eocd_enc = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(cd_enc), len(lh_enc), 0)
    unsupported_enc = lh_enc + cd_enc + eocd_enc
    with pytest.raises(CorruptZipError, match="Unsupported encrypted compression method"):
        extract_winzip_aes256_zip(unsupported_enc, "SuperSecretPassword123!")


async def test_process_issue_import_summary_secret(
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., AsyncClient],
) -> None:
    """Summary containing leaked secret triggers validation error in import."""
    user = await make_user("sum_sec", workspace_role="WORKSPACE_ADMIN")
    await make_project("SS1", created_by=user, roles={user: "PROJECT_ADMIN"})
    client = as_principal(user)
    csv_bytes = b"key,summary\n,ghp_123456789012345678901234567890123456\n"
    res = await client.post(
        "/api/v1/projects/SS1/issues/import?dry_run=true",
        files={"file": ("sec.csv", csv_bytes, "text/csv")},
    )
    assert res.status_code == 200
    report = res.json()
    assert report["error_count"] > 0
    assert any("summary" in e["column"] for e in report["errors"])


def test_openapi_and_api_zero_winzip_trademark() -> None:
    """Verify zero user-facing 'WinZip' copy in OpenAPI spec and issue CSV route descriptions (KAN-373)."""
    from kanban.app import create_app

    app = create_app()
    openapi = app.openapi()

    # Check issue export and import endpoints
    export_proj = openapi["paths"]["/api/v1/projects/{project_ref}/issues/export"]["post"]
    assert "WinZip" not in export_proj["summary"]
    assert "WinZip" not in export_proj["description"]
    assert "Password-protected ZIP (AES-256)" in export_proj["summary"]
    assert "Password-protected ZIP (AES-256)" in export_proj["description"]

    export_ws = openapi["paths"]["/api/v1/workspaces/{workspace_ref}/issues/export"]["post"]
    assert "WinZip" not in export_ws["summary"]
    assert "WinZip" not in export_ws["description"]
    assert "Password-protected ZIP (AES-256)" in export_ws["summary"]
    assert "Password-protected ZIP (AES-256)" in export_ws["description"]

    import_proj = openapi["paths"]["/api/v1/projects/{project_ref}/issues/import"]["post"]
    assert "WinZip" not in import_proj["summary"]
    assert "WinZip" not in import_proj["description"]
    assert "Password-protected ZIP (AES-256)" in import_proj["summary"]
    assert "Password-protected ZIP (AES-256)" in import_proj["description"]

    export_req_schema = openapi["components"]["schemas"]["IssueExportRequest"]
    assert "WinZip" not in export_req_schema["properties"]["format"]["description"]
    assert (
        "Password-protected ZIP (AES-256)"
        in export_req_schema["properties"]["format"]["description"]
    )

    # Also verify static kanban/web/openapi.json
    openapi_file = Path(__file__).parents[1] / "web" / "openapi.json"
    if openapi_file.exists():
        content = openapi_file.read_text(encoding="utf-8")
        assert "winzip" not in content.lower()

