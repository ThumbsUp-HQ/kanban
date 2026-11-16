# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Cryptographic manifest calculation for workflow transition hooks (KB-P5-17a, S14.2)."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection


def compute_hook_manifest_sha256(  # noqa: PLR0913
    *,
    hook_kind: str,
    wasm_module_sha256: bytes | str | None = None,
    agent_definition_id: uuid.UUID | str | None = None,
    allowed_mutable_fields: Collection[str] | None = None,
    failure_policy: str = "fail_closed",
    from_state_id: uuid.UUID | str | None = None,
    to_state_id: uuid.UUID | str,
) -> bytes:
    """Compute deterministic SHA-256 manifest hash over workflow hook specification.

    Specification (S14.2):
    SHA256(
        hook_kind || 0x00 ||
        hex(wasm_module_sha256 or '') || 0x00 ||
        str(agent_definition_id or '') || 0x00 ||
        ",".join(sorted(allowed_mutable_fields)) || 0x00 ||
        failure_policy || 0x00 ||
        str(from_state_id or '*') || 0x00 ||
        str(to_state_id)
    )
    """
    if isinstance(wasm_module_sha256, (bytes, bytearray)):
        wasm_hex = bytes(wasm_module_sha256).hex()
    elif wasm_module_sha256:
        wasm_hex = str(wasm_module_sha256)
    else:
        wasm_hex = ""

    agent_def_str = str(agent_definition_id) if agent_definition_id is not None else ""
    sorted_fields = sorted(set(allowed_mutable_fields or []))
    fields_str = ",".join(sorted_fields)
    from_str = str(from_state_id) if from_state_id is not None and str(from_state_id) != "" else "*"
    to_str = str(to_state_id)

    parts = [
        hook_kind.encode("utf-8"),
        wasm_hex.encode("utf-8"),
        agent_def_str.encode("utf-8"),
        fields_str.encode("utf-8"),
        failure_policy.encode("utf-8"),
        from_str.encode("utf-8"),
        to_str.encode("utf-8"),
    ]
    payload = b"\x00".join(parts)
    return hashlib.sha256(payload).digest()
