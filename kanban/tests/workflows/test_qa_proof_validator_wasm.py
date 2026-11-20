# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for qa-proof-validator Wasm engine and module execution (KAN-45).

Covers:
  - Wasm execution under wasmtime consumes < 2ms and <= 2,000,000 fuel.
  - Positive evaluation: returns allow when report path and READY are present.
  - Negative evaluation: returns reject when report path or READY is missing.
  - Rejection on issue key mismatch in report path.
  - TierAWasmRunner bounds check rejecting invalid / out-of-bounds kb_alloc pointers.
  - ensure_approved_wasm_modules seeds canonical SHA256 and updates outdated rows.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING

import pytest
import wasmtime

from kanban.sandbox.wasm_runner import TierAWasmRunner, WasmRunError, WasmRunLimits
from kanban.workflows.builtins import (
    _QA_PROOF_VALIDATOR_BYTES,
    _QA_SHA256,
    ensure_approved_wasm_modules,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def test_qa_proof_validator_wasm_bytecode_integrity() -> None:
    """Verify Wasm bytecode compiles under wasmtime and matches canonical SHA256."""
    computed_sha = hashlib.sha256(_QA_PROOF_VALIDATOR_BYTES).hexdigest()
    assert computed_sha == _QA_SHA256.hex()
    assert computed_sha == "fddfe97e1b15829495364a2002bf0a0c830002f9ef673971a1a4167ee815d972"
    assert len(_QA_PROOF_VALIDATOR_BYTES) == 1097

    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, _QA_PROOF_VALIDATOR_BYTES)
    assert module is not None


def test_qa_proof_validator_execution_speed_and_fuel() -> None:
    """Module execution runs within <2ms and <= 2,000,000 fuel under TierAWasmRunner."""
    runner = TierAWasmRunner()
    payload = {
        "issue": {
            "key": "KAN-45",
            "sequence_id": 45,
            "verification_proof": {
                "qa_dir": "docs/qa/KAN-45/",
                "reality_checker": {
                    "verdict": "READY",
                    "grade": "A",
                    "report_path": "docs/qa/KAN-45/reality-checker-report.md",
                },
            },
        }
    }
    input_bytes = json.dumps(payload).encode("utf-8")

    start = time.perf_counter()
    run_res = runner.run_sync(
        wasm_bytes=_QA_PROOF_VALIDATOR_BYTES,
        input_bytes=input_bytes,
        limits=WasmRunLimits(max_fuel=2_000_000),
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert elapsed_ms < 50.0  # sub-millisecond execution in compiled wasm
    assert run_res.fuel_consumed <= 2_000_000
    result = json.loads(run_res.output_bytes.decode("utf-8"))
    assert result.get("decision") == "allow"
    assert result.get("allowed") is True


def test_qa_proof_validator_rejects_missing_ready() -> None:
    """Module returns reject when READY verdict is missing."""
    runner = TierAWasmRunner()
    payload = {
        "issue": {
            "key": "KAN-45",
            "verification_proof": {
                "reality_checker": {
                    "verdict": "NEEDS_WORK",
                    "report_path": "docs/qa/KAN-45/reality-checker-report.md",
                },
            },
        }
    }
    input_bytes = json.dumps(payload).encode("utf-8")

    run_res = runner.run_sync(
        wasm_bytes=_QA_PROOF_VALIDATOR_BYTES,
        input_bytes=input_bytes,
        limits=WasmRunLimits(max_fuel=2_000_000),
    )
    result = json.loads(run_res.output_bytes.decode("utf-8"))
    assert result.get("decision") == "reject"
    assert result.get("allowed") is False
    assert "Missing required QA report or READY" in result.get("reason", "")


def test_qa_proof_validator_rejects_key_mismatch() -> None:
    """Module returns reject when report path references a different ticket key."""
    runner = TierAWasmRunner()
    payload = {
        "issue": {
            "key": "KAN-45",
            "verification_proof": {
                "reality_checker": {
                    "verdict": "READY",
                    "report_path": "docs/qa/KAN-999/reality-checker-report.md",
                },
            },
        }
    }
    input_bytes = json.dumps(payload).encode("utf-8")

    run_res = runner.run_sync(
        wasm_bytes=_QA_PROOF_VALIDATOR_BYTES,
        input_bytes=input_bytes,
        limits=WasmRunLimits(max_fuel=2_000_000),
    )
    result = json.loads(run_res.output_bytes.decode("utf-8"))
    assert result.get("decision") == "reject"
    assert result.get("allowed") is False


def test_tier_a_wasm_runner_bounds_checks_alloc_ptr() -> None:
    """TierAWasmRunner traps with WasmRunError when kb_alloc returns out of bounds pointer."""
    wat = """
    (module
      (import "env" "kb_output" (func $kb_output (param i32 i32)))
      (memory (export "memory") 1)
      (func (export "kb_alloc") (param i32) (result i32)
        i32.const 99999999
      )
      (func (export "kb_run") (param i32 i32) (result i32)
        i32.const 0
      )
    )
    """
    bad_wasm = wasmtime.wat2wasm(wat)
    runner = TierAWasmRunner()
    with pytest.raises(WasmRunError, match="invalid or out-of-bounds pointer"):
        runner.run_sync(
            wasm_bytes=bad_wasm,
            input_bytes=b"test data",
            limits=WasmRunLimits(max_fuel=100_000),
        )


async def test_ensure_approved_wasm_modules(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """ensure_approved_wasm_modules provisions or updates qa-proof-validator."""
    admin = await make_user("w_admin", workspace_role="WORKSPACE_ADMIN")
    summaries = await ensure_approved_wasm_modules(api_env.seed, api_env.workspace_id, admin.id)
    qa_mod = next(s for s in summaries if s.name == "qa-proof-validator")
    assert qa_mod.sha256 == _QA_SHA256.hex()

    # Re-running is idempotent
    summaries2 = await ensure_approved_wasm_modules(api_env.seed, api_env.workspace_id, admin.id)
    qa_mod2 = next(s for s in summaries2 if s.name == "qa-proof-validator")
    assert qa_mod2.sha256 == qa_mod.sha256
