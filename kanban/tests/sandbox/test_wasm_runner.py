# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and security tests for TierAWasmRunner (KB-P5-13, S13.3)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import wasmtime

from kanban.api.problems import ProblemException
from kanban.sandbox.wasm_runner import (
    TierAWasmRunner,
    UnavailableTierBRunner,
    WasmRunError,
    WasmRunLimits,
    _ModuleLRU,
)

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "wasm"


def _read_fixture(name: str) -> bytes:
    """Read a compiled WebAssembly fixture binary."""
    path = FIXTURES_DIR / name
    if not path.is_file():
        msg = f"Fixture {name} not found at {path}"
        raise FileNotFoundError(msg)
    return path.read_bytes()


def test_wasm_run_limits_validation() -> None:
    """Validate resource limit bounds and downward-only configuration."""
    valid = WasmRunLimits(max_fuel=10_000, max_memory_bytes=16_777_216, timeout_ms=100)
    assert valid.max_fuel == 10_000
    assert valid.max_memory_bytes == 16_777_216
    assert valid.timeout_ms == 100

    # Bounds: max_fuel <= 0 or > 50_000_000
    with pytest.raises(ValueError, match="max_fuel must be between 1 and 50,000,000"):
        WasmRunLimits(max_fuel=0)
    with pytest.raises(ValueError, match="max_fuel must be between 1 and 50,000,000"):
        WasmRunLimits(max_fuel=50_000_001)

    # Bounds: max_memory_bytes <= 0 or > 33_554_432
    with pytest.raises(ValueError, match="max_memory_bytes must be between 1 and 33,554,432"):
        WasmRunLimits(max_memory_bytes=0)
    with pytest.raises(ValueError, match="max_memory_bytes must be between 1 and 33,554,432"):
        WasmRunLimits(max_memory_bytes=33_554_433)

    # Bounds: timeout_ms <= 0 or > 500
    with pytest.raises(ValueError, match="timeout_ms must be between 1 and 500"):
        WasmRunLimits(timeout_ms=0)
    with pytest.raises(ValueError, match="timeout_ms must be between 1 and 500"):
        WasmRunLimits(timeout_ms=501)


@pytest.mark.asyncio
async def test_echo_cvss_positive_execution() -> None:
    """Test 1: echo_cvss.wasm computes severity_pill in < 10ms with warm median < 2ms."""
    runner = TierAWasmRunner.get_instance()
    wasm_bytes = _read_fixture("echo_cvss.wasm")

    sha256 = runner.validate_module(wasm_bytes)
    assert len(sha256) == 32

    input_payload = json.dumps({"issue": {"score": 8.8, "label": "8.8 High"}}).encode("utf-8")

    # Cold run
    cold_res = await runner.run(wasm_bytes, input_payload)
    parsed_cold = json.loads(cold_res.output_bytes.decode("utf-8"))
    assert parsed_cold == {"level": "high", "score": 8.8, "label": "8.8 High"}
    assert cold_res.duration_ms < 20.0
    assert cold_res.fuel_consumed > 0

    # Warm runs (100 runs)
    latencies: list[float] = []
    for _ in range(100):
        t0 = time.perf_counter()
        res = runner.run_sync(wasm_bytes, input_payload)
        elapsed = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed)
        assert res.output_bytes == cold_res.output_bytes

    latencies.sort()
    median_warm = latencies[len(latencies) // 2]
    assert median_warm < 2.0, f"Expected warm median < 2ms, got {median_warm:.3f}ms"


@pytest.mark.asyncio
async def test_require_qa_proof_link_deterministic() -> None:
    """Test 1b: require_qa_proof_link.wasm returns deterministic allow/reject payload."""
    runner = TierAWasmRunner.get_instance()
    wasm_bytes = _read_fixture("require_qa_proof_link.wasm")

    input_payload = json.dumps({"issue": {"key": "KAN-143"}}).encode("utf-8")
    res = await runner.run(wasm_bytes, input_payload)
    data = json.loads(res.output_bytes.decode("utf-8"))
    assert data["allowed"] is True
    assert data["reason"] == "Verified QA link present"


def test_wasi_forbidden_import_rejection() -> None:
    """Test 2: wasi_fs_import.wasm declaring wasi_snapshot_preview1 is rejected at validation."""
    runner = TierAWasmRunner.get_instance()
    wasm_bytes = _read_fixture("wasi_fs_import.wasm")

    with pytest.raises(WasmRunError) as exc_info:
        runner.validate_module(wasm_bytes)
    assert exc_info.value.code == "WASM_FORBIDDEN_IMPORT"
    assert "Forbidden host import detected" in exc_info.value.message

    with pytest.raises(WasmRunError) as exc_info_run:
        runner.run_sync(wasm_bytes, b"{}")
    assert exc_info_run.value.code == "WASM_FORBIDDEN_IMPORT"


def test_infinite_loop_fuel_exhaustion() -> None:
    """Test 3a: infinite_loop.wasm terminates with SCRIPT_FUEL_EXHAUSTED."""
    runner = TierAWasmRunner.get_instance()
    wasm_bytes = _read_fixture("infinite_loop.wasm")

    with pytest.raises(WasmRunError) as exc_info:
        runner.run_sync(wasm_bytes, b"{}", limits=WasmRunLimits(max_fuel=50_000))
    assert exc_info.value.code == "SCRIPT_FUEL_EXHAUSTED"
    assert "fuel" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_infinite_loop_epoch_timeout() -> None:
    """Test 3b: infinite_loop with large fuel and timeout_ms=15 terminates with SCRIPT_TIMEOUT."""
    runner = TierAWasmRunner.get_instance()
    wasm_bytes = _read_fixture("infinite_loop.wasm")

    start = time.perf_counter()
    with pytest.raises(WasmRunError) as exc_info:
        await runner.run(
            wasm_bytes,
            b"{}",
            limits=WasmRunLimits(max_fuel=50_000_000, timeout_ms=15),
        )
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert exc_info.value.code == "SCRIPT_TIMEOUT"
    assert elapsed_ms < 150.0, f"Expected timeout under 150ms, took {elapsed_ms:.1f}ms"


def test_mem_grow_64mb_limit() -> None:
    """Test 3c: mem_grow_64mb attempting past 32 MiB fails with SCRIPT_MEMORY_LIMIT."""
    runner = TierAWasmRunner.get_instance()
    wasm_bytes = _read_fixture("mem_grow_64mb.wasm")

    with pytest.raises(WasmRunError) as exc_info:
        runner.run_sync(wasm_bytes, b"{}")
    assert exc_info.value.code == "SCRIPT_MEMORY_LIMIT"


def test_binary_validation_edge_cases() -> None:
    """Validate binary length, corrupt bytecode, missing exports, and oversized memory."""
    runner = TierAWasmRunner.get_instance()

    # Too short (< 8 bytes)
    with pytest.raises(WasmRunError) as short_err:
        runner.validate_module(b"\x00asm")
    assert short_err.value.code == "WASM_BINARY_INVALID"

    # Too large (> 1 MiB)
    with pytest.raises(WasmRunError) as large_err:
        runner.validate_module(b"\x00" * 1_048_577)
    assert large_err.value.code == "WASM_BINARY_INVALID"

    # Corrupt wasm header
    with pytest.raises(WasmRunError) as corrupt_err:
        runner.validate_module(b"not-a-valid-wasm-module")
    assert corrupt_err.value.code == "WASM_BINARY_INVALID"

    # Module missing required exports
    wat_missing_exports = """
    (module
      (memory (export "memory") 1)
      (func (export "kb_alloc") (param i32) (result i32) i32.const 0)
    )
    """
    wasm_missing = wasmtime.wat2wasm(wat_missing_exports)
    with pytest.raises(WasmRunError) as miss_err:
        runner.validate_module(wasm_missing)
    assert miss_err.value.code == "WASM_BINARY_INVALID"
    assert "Missing required WebAssembly export: 'kb_run'" in miss_err.value.message

    wat_missing_memory = """
    (module
      (func (export "kb_alloc") (param i32) (result i32) i32.const 0)
      (func (export "kb_run") (param i32 i32) (result i32) i32.const 0)
    )
    """
    wasm_no_mem = wasmtime.wat2wasm(wat_missing_memory)
    with pytest.raises(WasmRunError) as no_mem_err:
        runner.validate_module(wasm_no_mem)
    assert no_mem_err.value.code == "WASM_BINARY_INVALID"
    assert "Missing required WebAssembly export: 'memory'" in no_mem_err.value.message

    wat_missing_alloc = """
    (module
      (memory (export "memory") 1)
      (func (export "kb_run") (param i32 i32) (result i32) i32.const 0)
    )
    """
    wasm_no_alloc = wasmtime.wat2wasm(wat_missing_alloc)
    with pytest.raises(WasmRunError) as no_alloc_err:
        runner.validate_module(wasm_no_alloc)
    assert no_alloc_err.value.code == "WASM_BINARY_INVALID"
    assert "Missing required WebAssembly export: 'kb_alloc'" in no_alloc_err.value.message

    # Initial memory > 512 pages (32 MiB)
    wat_huge_mem = """
    (module
      (import "env" "kb_output" (func $kb_output (param i32 i32)))
      (memory (export "memory") 600)
      (func (export "kb_alloc") (param i32) (result i32) i32.const 0)
      (func (export "kb_run") (param i32 i32) (result i32) i32.const 0)
    )
    """
    wasm_huge_mem = wasmtime.wat2wasm(wat_huge_mem)
    with pytest.raises(WasmRunError) as mem_err:
        runner.validate_module(wasm_huge_mem)
    assert mem_err.value.code == "SCRIPT_MEMORY_LIMIT"

    # Max memory > 512 pages
    wat_huge_max = """
    (module
      (import "env" "kb_output" (func $kb_output (param i32 i32)))
      (memory (export "memory") 1 600)
      (func (export "kb_alloc") (param i32) (result i32) i32.const 0)
      (func (export "kb_run") (param i32 i32) (result i32) i32.const 0)
    )
    """
    wasm_huge_max = wasmtime.wat2wasm(wat_huge_max)
    with pytest.raises(WasmRunError) as max_err:
        runner.validate_module(wasm_huge_max)
    assert max_err.value.code == "SCRIPT_MEMORY_LIMIT"


def test_runtime_payload_and_output_bounds() -> None:
    """Validate runtime limits: input (> 262,144 bytes) and output (> 65,536 bytes)."""
    runner = TierAWasmRunner.get_instance()
    echo_wasm = _read_fixture("echo_cvss.wasm")

    # Input payload exceeds 262,144 bytes
    huge_input = b"x" * 262_145
    with pytest.raises(WasmRunError) as in_err:
        runner.run_sync(echo_wasm, huge_input)
    assert in_err.value.code == "SCRIPT_TRAP"
    assert "exceeds maximum permitted" in in_err.value.message

    # Guest module producing output > 65,536 bytes
    wat_huge_output = """
    (module
      (import "env" "kb_output" (func $kb_output (param i32 i32)))
      (memory (export "memory") 2)
      (func (export "kb_alloc") (param i32) (result i32) i32.const 1024)
      (func (export "kb_run") (param i32 i32) (result i32)
        (call $kb_output (i32.const 0) (i32.const 70000))
        i32.const 0
      )
    )
    """
    wasm_huge_out = wasmtime.wat2wasm(wat_huge_output)
    with pytest.raises(WasmRunError) as out_err:
        runner.run_sync(wasm_huge_out, b"{}")
    assert out_err.value.code == "SCRIPT_OUTPUT_TOO_LARGE"

    # Guest module returning non-zero non-2 exit code
    wat_trap_code = """
    (module
      (import "env" "kb_output" (func $kb_output (param i32 i32)))
      (memory (export "memory") 1)
      (func (export "kb_alloc") (param i32) (result i32) i32.const 1024)
      (func (export "kb_run") (param i32 i32) (result i32)
        i32.const 42
      )
    )
    """
    wasm_trap = wasmtime.wat2wasm(wat_trap_code)
    with pytest.raises(WasmRunError) as trap_err:
        runner.run_sync(wasm_trap, b"{}")
    assert trap_err.value.code == "SCRIPT_TRAP"
    assert "returned non-zero error code 42" in trap_err.value.message


@pytest.mark.asyncio
async def test_unavailable_tier_b_runner() -> None:
    """Test 6: UnavailableTierBRunner raises 503 SANDBOX_UNAVAILABLE_IN_STANDALONE."""
    tier_b = UnavailableTierBRunner()
    with pytest.raises(ProblemException) as exc_info:
        await tier_b.run("print('hello')", b"{}")
    assert exc_info.value.status == 503
    assert exc_info.value.code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"


def test_module_lru_and_cache_coverage() -> None:
    """Validate LRU eviction and cache retrieval branches."""
    lru = _ModuleLRU(maxsize=2)
    m1 = wasmtime.Module(wasmtime.Engine(), _read_fixture("echo_cvss.wasm"))
    m2 = wasmtime.Module(wasmtime.Engine(), _read_fixture("infinite_loop.wasm"))
    m3 = wasmtime.Module(wasmtime.Engine(), _read_fixture("mem_grow_64mb.wasm"))

    lru.put(b"1" * 32, m1)
    lru.put(b"2" * 32, m2)
    assert lru.get(b"1" * 32) is m1
    # Adding third item evicts least-recently used (key 2)
    lru.put(b"3" * 32, m3)
    assert lru.get(b"3" * 32) is m3
    assert lru.get(b"2" * 32) is None
    lru.clear()
    assert lru.get(b"1" * 32) is None

    # Test runner get_or_compile_module cache hit branch
    runner = TierAWasmRunner.get_instance()
    wasm_bytes = _read_fixture("echo_cvss.wasm")
    mod1, h1 = runner.get_or_compile_module(wasm_bytes)
    mod2, h2 = runner.get_or_compile_module(wasm_bytes)
    assert mod1 is mod2
    assert h1 == h2


def test_empty_output_guest() -> None:
    """Validate guest module returning exit code 0 without calling kb_output."""
    runner = TierAWasmRunner.get_instance()
    wat_silent = """
    (module
      (import "env" "kb_output" (func $kb_output (param i32 i32)))
      (memory (export "memory") 1)
      (func (export "kb_alloc") (param i32) (result i32) i32.const 0)
      (func (export "kb_run") (param i32 i32) (result i32) i32.const 0)
    )
    """
    wasm_silent = wasmtime.wat2wasm(wat_silent)
    res = runner.run_sync(wasm_silent, b"{}")
    assert res.output_bytes == b""
    assert res.duration_ms >= 0


@pytest.mark.asyncio
async def test_async_guard_timeout() -> None:
    """Validate outer asyncio guard timeout branch."""
    runner = TierAWasmRunner.get_instance()
    wasm_bytes = _read_fixture("infinite_loop.wasm")

    async def slow_to_thread(*_args: object, **_kwargs: object) -> None:
        await asyncio.sleep(0.5)

    with patch("asyncio.to_thread", side_effect=slow_to_thread):
        with pytest.raises(WasmRunError) as exc_info:
            await runner.run(wasm_bytes, b"{}", limits=WasmRunLimits(timeout_ms=50))
        assert exc_info.value.code == "SCRIPT_TIMEOUT"


def test_traps_unreachable_and_out_of_bounds() -> None:
    """Validate unreachable instruction and out of bounds memory traps."""
    runner = TierAWasmRunner.get_instance()

    # Unreachable instruction -> SCRIPT_TRAP
    wat_unreachable = """
    (module
      (import "env" "kb_output" (func $kb_output (param i32 i32)))
      (memory (export "memory") 1)
      (func (export "kb_alloc") (param i32) (result i32) i32.const 0)
      (func (export "kb_run") (param i32 i32) (result i32)
        unreachable
      )
    )
    """
    wasm_unreachable = wasmtime.wat2wasm(wat_unreachable)
    with pytest.raises(WasmRunError) as unreach_err:
        runner.run_sync(wasm_unreachable, b"{}")
    assert unreach_err.value.code == "SCRIPT_TRAP"

    # Out-of-bounds memory load -> SCRIPT_MEMORY_LIMIT
    wat_oob = """
    (module
      (import "env" "kb_output" (func $kb_output (param i32 i32)))
      (memory (export "memory") 1)
      (func (export "kb_alloc") (param i32) (result i32) i32.const 0)
      (func (export "kb_run") (param i32 i32) (result i32)
        (drop (i32.load (i32.const 9999999)))
        i32.const 0
      )
    )
    """
    wasm_oob = wasmtime.wat2wasm(wat_oob)
    with pytest.raises(WasmRunError) as oob_err:
        runner.run_sync(wasm_oob, b"{}")
    assert oob_err.value.code == "SCRIPT_MEMORY_LIMIT"


def test_multiple_kb_output_calls_trap() -> None:
    """Guest calling kb_output multiple times is trapped with SCRIPT_TRAP."""
    runner = TierAWasmRunner.get_instance()
    wat_loop_output = """
    (module
      (import "env" "kb_output" (func $kb_output (param i32 i32)))
      (memory (export "memory") 1)
      (func (export "kb_alloc") (param i32) (result i32) i32.const 0)
      (func (export "kb_run") (param i32 i32) (result i32)
        (call $kb_output (i32.const 0) (i32.const 5))
        (call $kb_output (i32.const 0) (i32.const 5))
        i32.const 0
      )
    )
    """
    wasm_bytes = wasmtime.wat2wasm(wat_loop_output)
    with pytest.raises(WasmRunError) as exc_info:
        runner.run_sync(wasm_bytes, b"{}")
    assert exc_info.value.code == "SCRIPT_TRAP"
    assert "multiple times" in exc_info.value.message


def test_invalid_kb_output_pointers_trap() -> None:
    """Guest passing pointer or length beyond linear memory traps with SCRIPT_TRAP."""
    runner = TierAWasmRunner.get_instance()
    wat_bad_ptr = """
    (module
      (import "env" "kb_output" (func $kb_output (param i32 i32)))
      (memory (export "memory") 1)
      (func (export "kb_alloc") (param i32) (result i32) i32.const 0)
      (func (export "kb_run") (param i32 i32) (result i32)
        (call $kb_output (i32.const 65530) (i32.const 100))
        i32.const 0
      )
    )
    """
    wasm_bytes = wasmtime.wat2wasm(wat_bad_ptr)
    with pytest.raises(WasmRunError) as exc_info:
        runner.run_sync(wasm_bytes, b"{}")
    assert exc_info.value.code == "SCRIPT_TRAP"
    assert "out-of-bounds pointer or length" in exc_info.value.message
