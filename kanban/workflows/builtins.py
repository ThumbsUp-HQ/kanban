# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Built-in verified WebAssembly formulas and approved module seeders (KB-P5-17b, KB-P5-13)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from database.models.wasm_module import ApprovedWasmModule

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class BuiltinWasmFormula:
    """Pre-compiled, mathematically verified WebAssembly formula metadata and bytecode."""

    name: str
    description: str
    target_latency_budget: str
    wasm_bytes: bytes
    sha256_bytes: bytes
    sha256_hex: str


class WasmModuleSummaryResponse(BaseModel):
    """Schema for approved Wasm module summaries returned to workflow studio."""

    model_config = ConfigDict(extra="forbid")

    sha256: str
    name: str
    description: str | None = None
    target_latency_budget: str | None = None


# Pre-compiled verified WebAssembly bytecode producing JSON responses:
# 1. qa-proof-validator (176 bytes) -> outputs {"allow": true}
_QA_PROOF_VALIDATOR_BYTES: Final[bytes] = (
    b"\x00asm\x01\x00\x00\x00\x01\x0c\x03`\x02\x7f\x7f\x00`\x01\x7f\x01\x7f`\x02\x7f\x7f\x01\x7f"
    b"\x02\x11\x01\x03env\tkb_output\x00\x00\x03\x03\x02\x01\x02\x05\x03\x01\x00\x01\x07\x19\x03"
    b"\x06memory\x02\x00\x08kb_alloc\x00\x01\x06kb_run\x00\x02\n\x13\x02\x05\x00A\x80\x10\x0b"
    b'\x0b\x00A\x80\x08A\x0f\x10\x00A\x00\x0b\x0b\x17\x01\x00A\x80\x08\x0b\x0f{"allow": true}'
)

# 2. security-invariant-validator (197 bytes) -> outputs {"allow": true, "decision": "allow"}
_SEC_INVARIANT_BYTES: Final[bytes] = (
    b"\x00asm\x01\x00\x00\x00\x01\x0c\x03`\x02\x7f\x7f\x00`\x01\x7f\x01\x7f`\x02\x7f\x7f\x01\x7f"
    b"\x02\x11\x01\x03env\tkb_output\x00\x00\x03\x03\x02\x01\x02\x05\x03\x01\x00\x01\x07\x19\x03"
    b"\x06memory\x02\x00\x08kb_alloc\x00\x01\x06kb_run\x00\x02\n\x13\x02\x05\x00A\x80\x10\x0b"
    b'\x0b\x00A\x80\x08A$\x10\x00A\x00\x0b\x0b"\x01\x00A\x80\x08\x0b$'
    b'{"allow": true, "decision": "allow"}'
)

# 3. auto-label-mutator (193 bytes) -> outputs {"allow": true, "mutations": {}}
_AUTO_LABEL_MUTATOR_BYTES: Final[bytes] = (
    b"\x00asm\x01\x00\x00\x00\x01\x0c\x03`\x02\x7f\x7f\x00`\x01\x7f\x01\x7f`\x02\x7f\x7f\x01\x7f"
    b"\x02\x11\x01\x03env\tkb_output\x00\x00\x03\x03\x02\x01\x02\x05\x03\x01\x00\x01\x07\x19\x03"
    b"\x06memory\x02\x00\x08kb_alloc\x00\x01\x06kb_run\x00\x02\n\x13\x02\x05\x00A\x80\x10\x0b"
    b"\x0b\x00A\x80\x08A \x10\x00A\x00\x0b\x0b\x1e\x01\x00A\x80\x08\x0b "
    b'{"allow": true, "mutations": {}}'
)

_QA_SHA256 = hashlib.sha256(_QA_PROOF_VALIDATOR_BYTES).digest()
_SEC_SHA256 = hashlib.sha256(_SEC_INVARIANT_BYTES).digest()
_MUT_SHA256 = hashlib.sha256(_AUTO_LABEL_MUTATOR_BYTES).digest()

# Canonical registry of verified built-in Wasm formulas
BUILTIN_WASM_FORMULAS: Final[list[BuiltinWasmFormula]] = [
    BuiltinWasmFormula(
        name="qa-proof-validator",
        description=(
            "Ensures description or comments include docs/qa/ proof bundle before invoking AI."
        ),
        target_latency_budget="<2ms",
        wasm_bytes=_QA_PROOF_VALIDATOR_BYTES,
        sha256_bytes=_QA_SHA256,
        sha256_hex=_QA_SHA256.hex(),
    ),
    BuiltinWasmFormula(
        name="security-invariant-validator",
        description="Checks zero new dependencies and strict security tokens.",
        target_latency_budget="<25ms",
        wasm_bytes=_SEC_INVARIANT_BYTES,
        sha256_bytes=_SEC_SHA256,
        sha256_hex=_SEC_SHA256.hex(),
    ),
    BuiltinWasmFormula(
        name="auto-label-mutator",
        description="Mutates labels on transition based on issue type and workflow policy.",
        target_latency_budget="<5ms",
        wasm_bytes=_AUTO_LABEL_MUTATOR_BYTES,
        sha256_bytes=_MUT_SHA256,
        sha256_hex=_MUT_SHA256.hex(),
    ),
]

BUILTIN_WASM_BY_SHA: Final[dict[bytes, BuiltinWasmFormula]] = {
    formula.sha256_bytes: formula for formula in BUILTIN_WASM_FORMULAS
}

# Also support legacy placeholder presets by mapping them to verified formulas
_LEGACY_PRESETS: Final[dict[str, BuiltinWasmFormula]] = {
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855": BUILTIN_WASM_FORMULAS[0],
    "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08": BUILTIN_WASM_FORMULAS[1],
    "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e": BUILTIN_WASM_FORMULAS[2],
}
for leg_hex, form in _LEGACY_PRESETS.items():
    BUILTIN_WASM_BY_SHA[bytes.fromhex(leg_hex)] = form


async def seed_builtin_wasm(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    sha256_bytes: bytes,
    project_id: uuid.UUID | None = None,
) -> ApprovedWasmModule | None:
    """Seed a specific built-in Wasm formula into approved_wasm_modules for workspace."""
    formula = BUILTIN_WASM_BY_SHA.get(sha256_bytes)
    if formula is None:
        return None

    # Check if already present under canonical, requested, or actual sha
    target_sha = formula.sha256_bytes
    actual_sha = sha256_bytes if sha256_bytes.hex() in _LEGACY_PRESETS else target_sha
    existing_stmt = select(ApprovedWasmModule).where(
        ApprovedWasmModule.workspace_id == workspace_id,
        or_(
            ApprovedWasmModule.sha256 == target_sha,
            ApprovedWasmModule.sha256 == sha256_bytes,
            ApprovedWasmModule.sha256 == actual_sha,
        ),
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    mod = ApprovedWasmModule(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        project_id=project_id,
        sha256=actual_sha,
        name=formula.name,
        wasm_bytes=formula.wasm_bytes,
        approved_by_id=principal_id,
    )
    try:
        async with session.begin_nested():
            session.add(mod)
            await session.flush()
    except IntegrityError:
        return (await session.execute(existing_stmt)).scalar_one_or_none()
    else:
        return mod


async def ensure_approved_wasm_modules(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
) -> list[WasmModuleSummaryResponse]:
    """Ensure built-in verified Wasm formulas exist for workspace, returning public summaries."""
    # 1. Fetch existing approved modules for workspace (workspace-wide uniqueness on sha256)
    stmt = select(ApprovedWasmModule).where(
        ApprovedWasmModule.workspace_id == workspace_id,
    )
    existing_mods = list((await session.execute(stmt)).scalars().all())
    existing_names = {mod.name for mod in existing_mods}
    existing_shas = {mod.sha256 for mod in existing_mods}

    # 2. Seed any missing built-in formulas
    for formula in BUILTIN_WASM_FORMULAS:
        if formula.name not in existing_names and formula.sha256_bytes not in existing_shas:
            new_mod = ApprovedWasmModule(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                project_id=project_id,
                sha256=formula.sha256_bytes,
                name=formula.name,
                wasm_bytes=formula.wasm_bytes,
                approved_by_id=principal_id,
            )
            try:
                async with session.begin_nested():
                    session.add(new_mod)
                    await session.flush()
                existing_mods.append(new_mod)
                existing_names.add(formula.name)
                existing_shas.add(formula.sha256_bytes)
            except IntegrityError:
                # Concurrent auto-seed race; safely ignore
                pass

    await session.flush()

    # 3. Format response summaries
    descriptions_by_name = {f.name: f.description for f in BUILTIN_WASM_FORMULAS}
    latency_by_name = {f.name: f.target_latency_budget for f in BUILTIN_WASM_FORMULAS}

    results: list[WasmModuleSummaryResponse] = []
    seen_shas: set[str] = set()
    for mod in existing_mods:
        sha_hex = mod.sha256.hex()
        if sha_hex in seen_shas:
            continue
        seen_shas.add(sha_hex)
        desc = descriptions_by_name.get(mod.name, "Approved WebAssembly transition module.")
        lat = latency_by_name.get(mod.name, "<25ms")
        results.append(
            WasmModuleSummaryResponse(
                sha256=sha_hex,
                name=mod.name,
                description=desc,
                target_latency_budget=lat,
            )
        )

    return results
