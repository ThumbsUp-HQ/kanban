# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for workflow hook manifest SHA-256 calculation (KB-P5-17a)."""

from __future__ import annotations

import hashlib
import uuid

from kanban.workflows.manifest import compute_hook_manifest_sha256


def test_manifest_determinism_and_length() -> None:
    """Verify compute_hook_manifest_sha256 is deterministic and returns 32 bytes."""
    to_state = uuid.uuid4()
    wasm_bytes = hashlib.sha256(b"module").digest()

    h1 = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=wasm_bytes,
        allowed_mutable_fields=["labels", "priority"],
        failure_policy="fail_closed",
        from_state_id=None,
        to_state_id=to_state,
    )
    h2 = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=wasm_bytes,
        allowed_mutable_fields=["priority", "labels"],
        failure_policy="fail_closed",
        from_state_id=None,
        to_state_id=to_state,
    )
    assert len(h1) == 32
    assert h1 == h2


def test_manifest_hex_and_bytes_equivalence() -> None:
    """Verify wasm_module_sha256 as bytes vs lower-case hex produces identical manifest."""
    to_state = uuid.uuid4()
    wasm_bytes = hashlib.sha256(b"module").digest()
    wasm_hex = wasm_bytes.hex()

    h_bytes = compute_hook_manifest_sha256(
        hook_kind="sync_mutator",
        wasm_module_sha256=wasm_bytes,
        to_state_id=to_state,
    )
    h_hex = compute_hook_manifest_sha256(
        hook_kind="sync_mutator",
        wasm_module_sha256=wasm_hex,
        to_state_id=to_state,
    )
    assert h_bytes == h_hex


def test_manifest_wildcard_from_state() -> None:
    """Verify from_state_id=None and empty string map to '*' in canonical hash."""
    to_state = uuid.uuid4()
    agent_id = uuid.uuid4()

    h_none = compute_hook_manifest_sha256(
        hook_kind="agent_interceptor",
        agent_definition_id=agent_id,
        from_state_id=None,
        to_state_id=to_state,
    )
    h_empty = compute_hook_manifest_sha256(
        hook_kind="agent_interceptor",
        agent_definition_id=agent_id,
        from_state_id="",
        to_state_id=to_state,
    )
    assert h_none == h_empty


def test_manifest_tamper_sensitivity() -> None:
    """Verify modifying any field changes the resulting manifest hash."""
    to_state = uuid.uuid4()
    from_state = uuid.uuid4()
    wasm_bytes = hashlib.sha256(b"module").digest()

    base = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=wasm_bytes,
        allowed_mutable_fields=["labels"],
        failure_policy="fail_closed",
        from_state_id=from_state,
        to_state_id=to_state,
    )

    diff_kind = compute_hook_manifest_sha256(
        hook_kind="sync_mutator",
        wasm_module_sha256=wasm_bytes,
        allowed_mutable_fields=["labels"],
        failure_policy="fail_closed",
        from_state_id=from_state,
        to_state_id=to_state,
    )
    assert diff_kind != base

    diff_policy = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=wasm_bytes,
        allowed_mutable_fields=["labels"],
        failure_policy="fail_open_warn",
        from_state_id=from_state,
        to_state_id=to_state,
    )
    assert diff_policy != base

    diff_fields = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=wasm_bytes,
        allowed_mutable_fields=["labels", "priority"],
        failure_policy="fail_closed",
        from_state_id=from_state,
        to_state_id=to_state,
    )
    assert diff_fields != base

    diff_to = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=wasm_bytes,
        allowed_mutable_fields=["labels"],
        failure_policy="fail_closed",
        from_state_id=from_state,
        to_state_id=uuid.uuid4(),
    )
    assert diff_to != base

    diff_from = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=wasm_bytes,
        allowed_mutable_fields=["labels"],
        failure_policy="fail_closed",
        from_state_id=None,
        to_state_id=to_state,
    )
    assert diff_from != base
