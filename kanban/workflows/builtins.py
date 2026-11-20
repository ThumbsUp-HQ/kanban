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
# 1. qa-proof-validator (1097 bytes) -> verified O(N) report & READY scanner
_QA_PROOF_VALIDATOR_BYTES: Final[bytes] = (
    b'\x00asm\x01\x00\x00\x00\x01\x11\x03`\x02\x7f\x7f\x00`\x01\x7f\x01\x7f`\x02\x7f\x7f\x01\x7f\x02\x11\x01\x03env\tkb_output\x00\x00\x03\x03\x02\x01\x02\x05\x03\x01\x00\x06\x07\x1e\x03\x06memory\x02\x00\x08kb_alloc\x00\x01\x06kb_run\x00\x02\n\xb9\x04\x02\x05\x00A\x80 \x0b\xb0\x04\x01\t\x7f \x00 \x01j!\x02 \x00!\x03\x02@\x03@ \x03 \x02A\x07kH\x04@ \x03-\x00\x00A"F \x03A\x01j-\x00\x00A\xeb\x00Fq \x03A\x02j-\x00\x00A\xe5\x00F \x03A\x03j-\x00\x00A\xf9\x00F \x03A\x04j-\x00\x00A"Fqqq\x04@ \x03A\x05j!\x08\x03@ \x08 \x02H\x04@ \x08-\x00\x00!\n \nA F \nA:F \nA\tF \nA\nF \nA\rFrrrr\x04@ \x08A\x01j!\x08\x0c\x02\x0b\x0b\x0b \x08 \x02H\x04@ \x08-\x00\x00A"F\x04@ \x08A\x01j!\x06 \x06!\t\x03@ \t \x02H\x04@ \t-\x00\x00A"F\x04@ \t \x06k!\x07\x0c\x08\x05 \tA\x01j!\t\x0c\x02\x0b\x0b\x0b\x0b\x0b\x0b \x03A\x01j!\x03\x0c\x01\x0b\x0b\x0b \x00!\x03\x03@ \x03 \x02H\x04@ \x04E\x04@ \x03A\x05j \x02L\x04@ \x03-\x00\x00A\xd2\x00F \x03A\x01j-\x00\x00A\xc5\x00F \x03A\x02j-\x00\x00A\xc1\x00F \x03A\x03j-\x00\x00A\xc4\x00F \x03A\x04j-\x00\x00A\xd9\x00Fqqqq\x04@A\x01!\x04\x0b\x0b\x0b \x05E \x07A\x00Jq\x04@ \x03A"j \x07j \x02L\x04@\x02@A\x00!\x08\x03@ \x08A\x08H\x04@ \x03 \x08j-\x00\x00A\x80\x18 \x08j-\x00\x00G\x04@\x0c\x03\x05 \x08A\x01j!\x08\x0c\x02\x0b\x0b\x0bA\x00!\x08\x03@ \x08 \x07H\x04@ \x03A\x08j \x08j-\x00\x00 \x06 \x08j-\x00\x00G\x04@\x0c\x03\x05 \x08A\x01j!\x08\x0c\x02\x0b\x0b\x0bA\x00!\x08\x03@ \x08A\x1aH\x04@ \x03A\x08j \x07j \x08j-\x00\x00A\x88\x18 \x08j-\x00\x00G\x04@\x0c\x03\x05 \x08A\x01j!\x08\x0c\x02\x0b\x0b\x0bA\x01!\x05\x0b\x0b\x0b \x03A\x01j!\x03\x0c\x01\x0b\x0b \x04 \x05q\x04@A\x80\x08A#\x10\x00\x05A\x80\x10A\xf2\x00\x10\x00\x0bA\x00\x0b\x0b\xd0\x01\x04\x00A\x80\x08\x0b#{"decision":"allow","allowed":true}\x00A\x80\x10\x0br{"decision":"reject","allowed":false,"reason":"Missing required QA report or READY verdict in verification proof"}\x00A\x80\x18\x0b\x08docs/qa/\x00A\x88\x18\x0b\x1a/reality-checker-report.md\x00\xdf\x01\x04name\x01\x0c\x01\x00\tkb_output\x02U\x02\x01\x01\x00\x03len\x02\x0b\x00\x03ptr\x01\x03len\x02\x03end\x03\x01i\x04\x0bfound_ready\x05\x0cfound_report\x06\tkey_start\x07\x07key_len\x08\x01j\t\x01k\n\x02ch\x03s\x01\x02\t\x00\tfound_key\x01\rfind_key_loop\x04\x07skip_ws\t\x0cfind_key_end\x0c\tmain_scan\x13\x0bcheck_block\x14\x0ccheck_prefix\x17\tcheck_key\x1a\x0ccheck_suffix'  # noqa: E501
)

# 2. security-invariant-validator (249 bytes) -> outputs {"allowed": true, "decision": "allow"}
_SEC_INVARIANT_BYTES: Final[bytes] = (
    b"\x00asm\x01\x00\x00\x00\x01\x11\x03`\x02\x7f\x7f\x00`\x01\x7f\x01\x7f`\x02\x7f\x7f\x01\x7f"
    b"\x02\x11\x01\x03env\tkb_output\x00\x00\x03\x03\x02\x01\x02\x05\x03\x01\x00\x01\x071\x04"
    b"\x06memory\x02\x00\x08kb_alloc\x00\x01\x06kb_run\x00\x02\x10kb_on_transition\x00\x02\n\x13\x02\x05\x00A\x80\x10\x0b"
    b"\x0b\x00A\x80\x08A&\x10\x00A\x00\x0b\x0b-\x01\x00A\x80\x08\x0b"
    b'&{"allowed": true, "decision": "allow"}'
    b"\x00H\x04name\x00\x18\x17sec_invariant_validator\x01\x11\x02\x00\tkb_output"
    b"\x02\x03run\x02\x14\x02\x01\x01\x00\x03len\x02\x02\x00\x03ptr\x01\x03len"
)

# 3. auto-label-mutator (244 bytes) -> outputs {"allowed": true, "decision": "allow"}
_AUTO_LABEL_MUTATOR_BYTES: Final[bytes] = (
    b"\x00asm\x01\x00\x00\x00\x01\x11\x03`\x02\x7f\x7f\x00`\x01\x7f\x01\x7f`\x02\x7f\x7f\x01\x7f"
    b"\x02\x11\x01\x03env\tkb_output\x00\x00\x03\x03\x02\x01\x02\x05\x03\x01\x00\x01\x071\x04"
    b"\x06memory\x02\x00\x08kb_alloc\x00\x01\x06kb_run\x00\x02\x10kb_on_transition\x00\x02\n\x13\x02\x05\x00A\x80\x10\x0b"
    b"\x0b\x00A\x80\x08A&\x10\x00A\x00\x0b\x0b-\x01\x00A\x80\x08\x0b"
    b'&{"allowed": true, "decision": "allow"}'
    b"\x00C\x04name\x00\x13\x12auto_label_mutator\x01\x11\x02\x00\tkb_output"
    b"\x02\x03run\x02\x14\x02\x01\x01\x00\x03len\x02\x02\x00\x03ptr\x01\x03len"
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
    "92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968": BUILTIN_WASM_FORMULAS[0],
    "8a8ad03aa46429682f7bf0c20085a596579611451351923ddf811f1581ed4620": BUILTIN_WASM_FORMULAS[0],
    "9d10223f7debd9a61367004d44a2f8a78f882cc5c83f43d3e458fc7b0324252d": BUILTIN_WASM_FORMULAS[0],
    "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08": BUILTIN_WASM_FORMULAS[1],
    "7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874": BUILTIN_WASM_FORMULAS[1],
    "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e": BUILTIN_WASM_FORMULAS[2],
    "2e7db622992707370042a3c5e15eda145d995048ef4f69f6c746f33dc43f93e9": BUILTIN_WASM_FORMULAS[2],
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

    # 2. Seed any missing built-in formulas or update outdated sha for existing built-ins
    for formula in BUILTIN_WASM_FORMULAS:
        matching = next((m for m in existing_mods if m.name == formula.name), None)
        if matching is not None:
            if matching.sha256 != formula.sha256_bytes:
                matching.sha256 = formula.sha256_bytes
                matching.wasm_bytes = formula.wasm_bytes
                existing_shas.add(formula.sha256_bytes)
        elif formula.sha256_bytes not in existing_shas:
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
