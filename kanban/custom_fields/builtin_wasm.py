# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Built-in starter WebAssembly presets and module resolution (KAN-32, KB-P5-13)."""

from __future__ import annotations

import base64
import hashlib
from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from database.models.wasm_module import ApprovedWasmModule
from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

# 213-byte echo_cvss.wasm starter preset module (compiled from echo_cvss.wat)
ECHO_CVSS_WASM_BASE64: Final[str] = (
    "AGFzbQEAAAABEQNgAn9/AGABfwF/YAJ/fwF/AhEBA2VudglrYl9vdXRwdXQAAAMDAgECBQMBAAEHHgMG"
    "bWVtb3J5AgAIa2JfYWxsb2MAAQZrYl9ydW4AAgoTAgUAQYAQCwsAQYAIQTQQAEEACws7AQBBgAgLNHsi"
    "bGV2ZWwiOiAiaGlnaCIsICJzY29yZSI6IDguOCwgImxhYmVsIjogIjguOCBIaWdoIn0AKQRuYW1lAQwB"
    "AAlrYl9vdXRwdXQCFAIBAQADbGVuAgIAA3B0cgEDbGVu"
)

ECHO_CVSS_WASM_BYTES: Final[bytes] = base64.b64decode(ECHO_CVSS_WASM_BASE64)
ECHO_CVSS_SHA256_BYTES: Final[bytes] = hashlib.sha256(ECHO_CVSS_WASM_BYTES).digest()
ECHO_CVSS_SHA256_HEX: Final[str] = ECHO_CVSS_SHA256_BYTES.hex()

BUILTIN_STARTER_WASM_BY_NAME: Final[dict[str, bytes]] = {
    "echo_cvss": ECHO_CVSS_WASM_BYTES,
    "echo_cvss.wasm": ECHO_CVSS_WASM_BYTES,
    "cvss-score": ECHO_CVSS_WASM_BYTES,
    "cvss_score": ECHO_CVSS_WASM_BYTES,
}

BUILTIN_STARTER_WASM_BY_SHA: Final[dict[bytes, bytes]] = {
    ECHO_CVSS_SHA256_BYTES: ECHO_CVSS_WASM_BYTES,
}


def _parse_sha(sha256: bytes | str | None) -> bytes | None:
    if sha256 is None:
        return None
    if isinstance(sha256, (bytes, memoryview)):
        return bytes(sha256)
    try:
        return bytes.fromhex(str(sha256).strip())
    except ValueError as ex:
        raise ProblemException(
            status=422,
            code="INVALID_WASM_SHA256",
            title="Invalid WASM SHA256",
            detail=f"WASM SHA256 must be valid hex: {ex}",
        ) from ex


async def _resolve_by_sha(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    raw_sha: bytes,
    source: str | None,
) -> tuple[bytes, bytes]:
    mod_stmt = select(ApprovedWasmModule).where(
        ApprovedWasmModule.workspace_id == workspace_id,
        ApprovedWasmModule.sha256 == raw_sha,
    )
    wasm_mod = (await session.execute(mod_stmt)).scalar_one_or_none()
    if wasm_mod is not None:
        return wasm_mod.wasm_bytes, bytes(wasm_mod.sha256)

    source_clean = (source or "").strip().lower()
    if raw_sha in BUILTIN_STARTER_WASM_BY_SHA and (
        not source_clean or any(k in source_clean for k in BUILTIN_STARTER_WASM_BY_NAME)
    ):
        return BUILTIN_STARTER_WASM_BY_SHA[raw_sha], raw_sha

    raise ProblemException(
        status=404,
        code="WASM_MODULE_NOT_FOUND",
        title="WebAssembly Module Not Found",
        detail="Approved WebAssembly module was not found in workspace",
    )


async def _resolve_by_name(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    name_ref: str,
) -> tuple[bytes, bytes]:
    name_stmt = select(ApprovedWasmModule).where(
        ApprovedWasmModule.workspace_id == workspace_id,
        ApprovedWasmModule.name == name_ref,
    )
    wasm_mod_name = (await session.execute(name_stmt)).scalar_one_or_none()
    if wasm_mod_name is not None:
        return wasm_mod_name.wasm_bytes, bytes(wasm_mod_name.sha256)

    lower_name = name_ref.lower()
    if lower_name in BUILTIN_STARTER_WASM_BY_NAME:
        mod_bytes = BUILTIN_STARTER_WASM_BY_NAME[lower_name]
        return mod_bytes, hashlib.sha256(mod_bytes).digest()

    raise ProblemException(
        status=404,
        code="WASM_MODULE_NOT_FOUND",
        title="WebAssembly Module Not Found",
        detail="Approved WebAssembly module was not found in workspace",
    )


def _decode_bytecode(clean_code: str) -> bytes:
    try:
        return bytes.fromhex(clean_code)
    except ValueError:
        try:
            return base64.b64decode(clean_code, validate=True)
        except Exception as err:
            raise ProblemException(
                status=422,
                code="WASM_BINARY_INVALID",
                title="Invalid WebAssembly Binary",
                detail=f"Cannot decode WebAssembly module bytes: {err}",
            ) from err


async def _resolve_by_bytecode(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    clean_src: str,
    clean_code: str,
    *,
    allow_raw_bytecode: bool = False,
) -> tuple[bytes, bytes]:
    wasm_bytes = _decode_bytecode(clean_code)
    computed_sha = hashlib.sha256(wasm_bytes).digest()

    has_preset_name = any(k in clean_src.lower() for k in BUILTIN_STARTER_WASM_BY_NAME)
    if computed_sha in BUILTIN_STARTER_WASM_BY_SHA and has_preset_name:
        mod_stmt = select(ApprovedWasmModule).where(
            ApprovedWasmModule.workspace_id == workspace_id,
            ApprovedWasmModule.sha256 == computed_sha,
        )
        wasm_mod = (await session.execute(mod_stmt)).scalar_one_or_none()
        if wasm_mod is not None:
            return wasm_mod.wasm_bytes, bytes(wasm_mod.sha256)
        return BUILTIN_STARTER_WASM_BY_SHA[computed_sha], computed_sha

    if allow_raw_bytecode:
        return wasm_bytes, computed_sha

    mod_stmt = select(ApprovedWasmModule).where(
        ApprovedWasmModule.workspace_id == workspace_id,
        ApprovedWasmModule.sha256 == computed_sha,
    )
    wasm_mod = (await session.execute(mod_stmt)).scalar_one_or_none()
    if wasm_mod is not None:
        return wasm_mod.wasm_bytes, bytes(wasm_mod.sha256)

    raise ProblemException(
        status=404,
        code="WASM_MODULE_NOT_FOUND",
        title="WebAssembly Module Not Found",
        detail="Approved WebAssembly module was not found in workspace",
    )


async def resolve_wasm_module_bytes(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    sha256: bytes | str | None = None,
    source: str | None = None,
    allow_raw_bytecode: bool = False,
) -> tuple[bytes, bytes]:
    """Resolve WebAssembly module bytes and sha256 digest.

    Checks workspace ApprovedWasmModule rows first. If not overridden in the DB,
    resolves built-in starter preset modules (such as echo_cvss / echo_cvss.wasm).

    Returns:
        tuple[bytes, bytes]: (wasm_bytes, sha256_bytes)

    Raises:
        ProblemException(404, "WASM_MODULE_NOT_FOUND"): Module not found in DB or builtins.
        ProblemException(422, "INVALID_WASM_SHA256"): If sha256 string is invalid hex.
        ProblemException(422, "WASM_BINARY_INVALID"): If script_source cannot be decoded.

    """
    raw_sha = _parse_sha(sha256)
    if raw_sha is not None:
        return await _resolve_by_sha(session, workspace_id, raw_sha, source)

    clean_src = (source or "").strip()
    if clean_src:
        clean_lines = [
            line
            for line in clean_src.splitlines()
            if not line.strip().startswith("//") and not line.strip().startswith("#")
        ]
        clean_code = "\n".join(clean_lines).strip()

        if clean_code.startswith("wasm:") or clean_code.lower() in BUILTIN_STARTER_WASM_BY_NAME:
            name_ref = (
                clean_code[len("wasm:") :].strip() if clean_code.startswith("wasm:") else clean_code
            )
            return await _resolve_by_name(session, workspace_id, name_ref)

        if not clean_code:
            if any(k in clean_src.lower() for k in BUILTIN_STARTER_WASM_BY_NAME):
                return ECHO_CVSS_WASM_BYTES, ECHO_CVSS_SHA256_BYTES
            raise ProblemException(
                status=404,
                code="WASM_MODULE_NOT_FOUND",
                title="WebAssembly Module Not Found",
                detail="Approved WebAssembly module was not found in workspace",
            )

        return await _resolve_by_bytecode(
            session,
            workspace_id,
            clean_src,
            clean_code,
            allow_raw_bytecode=allow_raw_bytecode,
        )

    raise ProblemException(
        status=404,
        code="WASM_MODULE_NOT_FOUND",
        title="WebAssembly Module Not Found",
        detail="Approved WebAssembly module was not found in workspace",
    )
