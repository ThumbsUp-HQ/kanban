# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Deterministic cryptographic manifest SHA-256 calculation for custom fields (KB-P5-11, S13.2)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

MAX_EGRESS_ENTRIES = 16
_EGRESS_ENTRY_REGEX = re.compile(r"^/api/v1/[A-Za-z0-9/_*{}-]{1,120}$")


def validate_egress_allowlist(egress_allowlist: list[str] | None) -> list[str]:
    """Validate egress allowlist paths against strict internal proxy routing constraints."""
    if not egress_allowlist:
        return []

    if len(egress_allowlist) > MAX_EGRESS_ENTRIES:
        msg = (
            f"egress_allowlist length ({len(egress_allowlist)}) "
            f"exceeds maximum allowed ({MAX_EGRESS_ENTRIES})"
        )
        raise ValueError(msg)

    cleaned: list[str] = []
    raw_list: list[object] = list(egress_allowlist)
    for entry in raw_list:
        if not isinstance(entry, str):
            msg = f"egress_allowlist entry must be a string, got {type(entry).__name__}"
            raise TypeError(msg)
        if any(c.isspace() for c in entry):
            msg = f"egress_allowlist entry '{entry}' contains whitespace"
            raise ValueError(msg)
        if ".." in entry:
            msg = f"Path traversal ('..') is strictly prohibited in egress_allowlist: '{entry}'"
            raise ValueError(msg)
        if "?" in entry or "#" in entry:
            msg = f"Query parameters or URL fragments forbidden in egress_allowlist: '{entry}'"
            raise ValueError(msg)
        if not _EGRESS_ENTRY_REGEX.match(entry):
            msg = f"egress_allowlist entry '{entry}' does not match required pattern"
            raise ValueError(msg)
        cleaned.append(entry)

    return sorted(set(cleaned))


def compute_field_manifest_sha256(  # noqa: PLR0913
    *,
    script_source: str,
    output_format: str,
    output_format_metadata: dict[str, Any],
    tier: str = "wasm",
    target_scope: str = "PROJECT",
    credential_mode: str = "INVOKING_USER",
    egress_allowlist: list[str] | None = None,
    wasm_module_sha256: str | bytes | None = None,
) -> bytes:
    """Compute deterministic SHA-256 manifest hash over normalized field specification.

    Per S13.2:
    SHA256(canonical_json({
        "credential_mode": ...,
        "egress_allowlist": sorted(...),
        "output_format": ...,
        "output_format_metadata": ...,
        "script_source": ...,
        "target_scope": ...,
        "tier": ...,
        "wasm_module_sha256": ...
    }))
    """
    valid_egress = validate_egress_allowlist(egress_allowlist)
    wasm_hex: str | None = None
    if isinstance(wasm_module_sha256, bytes):
        wasm_hex = wasm_module_sha256.hex()
    elif isinstance(wasm_module_sha256, str) and wasm_module_sha256.strip():
        wasm_hex = wasm_module_sha256.strip().lower()

    payload = {
        "credential_mode": credential_mode,
        "egress_allowlist": valid_egress,
        "output_format": output_format,
        "output_format_metadata": output_format_metadata,
        "script_source": script_source,
        "target_scope": target_scope,
        "tier": tier,
        "wasm_module_sha256": wasm_hex,
    }
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).digest()
