# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for built-in WebAssembly starter presets (KAN-32, KB-P5-13)."""

from __future__ import annotations

import base64
import hashlib
import uuid
from typing import TYPE_CHECKING

import pytest

from database.models.wasm_module import ApprovedWasmModule
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.custom_fields.builtin_wasm import (
    ECHO_CVSS_SHA256_BYTES,
    ECHO_CVSS_SHA256_HEX,
    ECHO_CVSS_WASM_BASE64,
    ECHO_CVSS_WASM_BYTES,
    resolve_wasm_module_bytes,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _as_admin_aal2(api_env: ApiEnv, user: SeededUser) -> httpx.AsyncClient:
    """Return httpx client authenticated as workspace/project admin with AAL2."""
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
    )
    return api_env.client


async def test_resolve_builtin_wasm_by_name(db_session: AsyncSession) -> None:
    """Test 1: resolve_wasm_module_bytes resolves echo_cvss by name out of the box."""
    ws_id = uuid.uuid4()
    for name in ("echo_cvss", "echo_cvss.wasm", "cvss-score", "cvss_score", "wasm:echo_cvss"):
        wasm_b, sha_b = await resolve_wasm_module_bytes(db_session, ws_id, source=name)
        assert wasm_b == ECHO_CVSS_WASM_BYTES
        assert sha_b == ECHO_CVSS_SHA256_BYTES


async def test_resolve_builtin_wasm_by_sha(db_session: AsyncSession) -> None:
    """Test 2: resolve_wasm_module_bytes resolves by SHA256 bytes and hex string."""
    ws_id = uuid.uuid4()
    wasm_b1, sha_b1 = await resolve_wasm_module_bytes(
        db_session, ws_id, sha256=ECHO_CVSS_SHA256_BYTES, source="echo_cvss"
    )
    assert wasm_b1 == ECHO_CVSS_WASM_BYTES
    assert sha_b1 == ECHO_CVSS_SHA256_BYTES

    wasm_b2, sha_b2 = await resolve_wasm_module_bytes(
        db_session, ws_id, sha256=ECHO_CVSS_SHA256_HEX
    )
    assert wasm_b2 == ECHO_CVSS_WASM_BYTES
    assert sha_b2 == ECHO_CVSS_SHA256_BYTES


async def test_resolve_builtin_wasm_by_bytecode_with_comments(db_session: AsyncSession) -> None:
    """Test 3: resolve_wasm_module_bytes resolves preset bytecode containing comments."""
    ws_id = uuid.uuid4()
    preset_source = (
        f"// Built-in WebAssembly Starter Preset: echo_cvss.wasm\n"
        f"// Base64 encoding:\n{ECHO_CVSS_WASM_BASE64}"
    )
    wasm_b, sha_b = await resolve_wasm_module_bytes(db_session, ws_id, source=preset_source)
    assert wasm_b == ECHO_CVSS_WASM_BYTES
    assert sha_b == ECHO_CVSS_SHA256_BYTES


async def test_resolve_builtin_wasm_comments_only(db_session: AsyncSession) -> None:
    """Test 4: resolve_wasm_module_bytes handles comment-only preset references."""
    ws_id = uuid.uuid4()
    wasm_b, sha_b = await resolve_wasm_module_bytes(db_session, ws_id, source="// echo_cvss.wasm")
    assert wasm_b == ECHO_CVSS_WASM_BYTES
    assert sha_b == ECHO_CVSS_SHA256_BYTES

    with pytest.raises(ProblemException) as exc:
        await resolve_wasm_module_bytes(db_session, ws_id, source="// random empty comment")
    assert exc.value.code == "WASM_MODULE_NOT_FOUND"


async def test_resolve_builtin_wasm_db_override(
    db_session: AsyncSession,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test 5: DB row overrides built-in starter preset when present in workspace."""
    admin = await make_user("db_override_admin", workspace_role="WORKSPACE_ADMIN")
    custom_bytes = b"\x00asm\x01\x00\x00\x00\x01\x04\x01`\x00\x00\x03\x02\x01\x00"
    custom_sha = hashlib.sha256(custom_bytes).digest()

    try:
        db_mod = ApprovedWasmModule(
            workspace_id=admin.workspace_id,
            name="echo_cvss",
            sha256=custom_sha,
            wasm_bytes=custom_bytes,
            approved_by_id=admin.id,
        )
        db_session.add(db_mod)
        await db_session.flush()

        # Resolution by name returns DB row instead of builtin
        wasm_b, sha_b = await resolve_wasm_module_bytes(
            db_session, admin.workspace_id, source="wasm:echo_cvss"
        )
        assert wasm_b == custom_bytes
        assert sha_b == custom_sha

        # DB row matching preset sha and comments (line 174)
        db_preset_mod = ApprovedWasmModule(
            workspace_id=admin.workspace_id,
            name="echo_cvss_custom",
            sha256=ECHO_CVSS_SHA256_BYTES,
            wasm_bytes=ECHO_CVSS_WASM_BYTES,
            approved_by_id=admin.id,
        )
        db_session.add(db_preset_mod)
        await db_session.flush()

        b64_preset = base64.b64encode(ECHO_CVSS_WASM_BYTES).decode("ascii")
        src_commented = f"// echo_cvss\n{b64_preset}"
        wasm_from_db, sha_from_db = await resolve_wasm_module_bytes(
            db_session, admin.workspace_id, source=src_commented
        )
        assert wasm_from_db == ECHO_CVSS_WASM_BYTES
        assert sha_from_db == ECHO_CVSS_SHA256_BYTES
    finally:
        await db_session.rollback()


async def test_resolve_builtin_wasm_error_branches(db_session: AsyncSession) -> None:
    """Test 6: Invalid hex sha, invalid base64, and missing module raise expected errors."""
    ws_id = uuid.uuid4()

    # Invalid hex sha
    with pytest.raises(ProblemException) as exc1:
        await resolve_wasm_module_bytes(db_session, ws_id, sha256="not_a_hex_string_zzz")
    assert exc1.value.code == "INVALID_WASM_SHA256"

    # Unknown sha
    with pytest.raises(ProblemException) as exc2:
        await resolve_wasm_module_bytes(db_session, ws_id, sha256="11" * 32)
    assert exc2.value.code == "WASM_MODULE_NOT_FOUND"

    # Unknown name
    with pytest.raises(ProblemException) as exc3:
        await resolve_wasm_module_bytes(db_session, ws_id, source="wasm:totally_nonexistent")
    assert exc3.value.code == "WASM_MODULE_NOT_FOUND"

    # Raw bytecode allowed branch (line 179)
    arbitrary_bytes = b"\x00asm\x01\x00\x00\x00\x00\x00\x00\x00"
    arb_b64 = base64.b64encode(arbitrary_bytes).decode("ascii")
    raw_b, raw_sha = await resolve_wasm_module_bytes(
        db_session, ws_id, source=arb_b64, allow_raw_bytecode=True
    )
    assert raw_b == arbitrary_bytes
    assert raw_sha == hashlib.sha256(arbitrary_bytes).digest()

    # Invalid base64 bytecode
    with pytest.raises(ProblemException) as exc4:
        await resolve_wasm_module_bytes(db_session, ws_id, source="bad_base64_data_!@#$%^")
    assert exc4.value.code == "WASM_BINARY_INVALID"

    # Empty source and no sha
    with pytest.raises(ProblemException) as exc5:
        await resolve_wasm_module_bytes(db_session, ws_id)
    assert exc5.value.code == "WASM_MODULE_NOT_FOUND"


async def test_api_test_execute_preset_cvss_score_fresh_project_200(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Test 7: POST /test-execute with cvss-score preset on fresh project returns HTTP 200."""
    admin = await make_user("admin_preset", workspace_role="WORKSPACE_ADMIN")
    _ = await make_project("PRESET", created_by=admin, roles={admin: "PROJECT_ADMIN"})

    client = _as_admin_aal2(api_env, admin)

    # 1. Create real issue PRESET-1
    resp_issue = await client.post(
        "/api/v1/projects/PRESET/issues",
        json={"summary": "Preset Verification Issue", "description_markdown": "Test Description"},
    )
    assert resp_issue.status_code == 201
    issue_key = resp_issue.json()["key"]

    # 2. Test-execute cvss-score preset with zero DB rows in ApprovedWasmModule
    resp_test = await client.post(
        "/api/v1/projects/PRESET/custom-fields/test-execute",
        json={
            "issue_key": issue_key,
            "tier": "wasm",
            "output_format": "severity_pill",
            "output_format_metadata": {},
            "script_source": "// Built-in Starter Preset Module: echo_cvss.wasm\nwasm:echo_cvss",
        },
    )
    assert resp_test.status_code == 200, resp_test.text
    data = resp_test.json()
    assert data["status"] == "SUCCESS"
    assert data["value"] == {"level": "high", "score": 8.8, "label": "8.8 High"}
    assert "Executed Wasm module" in data["logs"]
