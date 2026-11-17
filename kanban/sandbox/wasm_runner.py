# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tier A Wasmtime runner, resource limits, and sandbox protocols (KB-P5-13, S13.3)."""

from __future__ import annotations

import asyncio
import hashlib
import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Final, Protocol

import wasmtime

from kanban.api.problems import ProblemException

_MAX_PERMITTED_FUEL: Final[int] = 50_000_000
_MAX_PERMITTED_MEMORY_BYTES: Final[int] = 33_554_432
_MAX_PERMITTED_TIMEOUT_MS: Final[int] = 500
_MIN_WASM_LEN: Final[int] = 8
_MAX_WASM_LEN: Final[int] = 1_048_576
_MAX_MEMORY_PAGES: Final[int] = 512
_MAX_INPUT_PAYLOAD_BYTES: Final[int] = 262_144
_MAX_OUTPUT_PAYLOAD_BYTES: Final[int] = 65_536
_MEMORY_LIMIT_EXIT_CODE: Final[int] = 2


@dataclass(frozen=True, slots=True)
class WasmRunLimits:
    """Resource bounds for Tier A Wasmtime execution (configurable downward only)."""

    max_fuel: int = _MAX_PERMITTED_FUEL
    max_memory_bytes: int = _MAX_PERMITTED_MEMORY_BYTES  # 32 MiB = 512 pages * 64 KiB
    timeout_ms: int = _MAX_PERMITTED_TIMEOUT_MS

    def __post_init__(self) -> None:
        """Validate configured limit thresholds."""
        if self.max_fuel <= 0 or self.max_fuel > _MAX_PERMITTED_FUEL:
            msg = f"max_fuel must be between 1 and 50,000,000 (got {self.max_fuel})"
            raise ValueError(msg)
        if self.max_memory_bytes <= 0 or self.max_memory_bytes > _MAX_PERMITTED_MEMORY_BYTES:
            msg = f"max_memory_bytes must be between 1 and 33,554,432 (got {self.max_memory_bytes})"
            raise ValueError(msg)
        if self.timeout_ms <= 0 or self.timeout_ms > _MAX_PERMITTED_TIMEOUT_MS:
            msg = f"timeout_ms must be between 1 and 500 (got {self.timeout_ms})"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class WasmRunResult:
    """Execution telemetry and captured output for a Tier A invocation."""

    output_bytes: bytes
    fuel_consumed: int
    duration_ms: float


class WasmRunError(Exception):
    """Deterministic failure during Tier A WebAssembly validation or execution."""

    def __init__(self, message: str, *, code: str) -> None:
        """Initialize deterministic Wasm failure with error code."""
        super().__init__(message)
        self.message = message
        self.code = code


class TierBRunner(Protocol):
    """Protocol for Tier B nsjail container execution."""

    async def run(
        self,
        script_source: str,
        input_json: bytes,
        *,
        timeout_ms: int = 5000,
    ) -> bytes:
        """Execute a Python custom script inside an isolated nsjail container."""
        ...


class UnavailableTierBRunner:
    """Default Tier B runner raising 503 until KB-P5-14 integrates nsjail."""

    async def run(
        self,
        script_source: str,
        input_json: bytes,
        *,
        timeout_ms: int = 5000,
    ) -> bytes:
        """Reject Tier B execution with 503 until nsjail runner is integrated."""
        del script_source, input_json, timeout_ms
        raise ProblemException(
            status=503,
            code="SANDBOX_UNAVAILABLE_IN_STANDALONE",
            title="Sandbox Unavailable",
            detail="Tier B sandbox is unavailable in standalone mode",
        )


class _ModuleLRU:
    """Thread-safe LRU cache for pre-compiled wasmtime.Module instances."""

    def __init__(self, maxsize: int = 128) -> None:
        self._maxsize = maxsize
        self._cache: OrderedDict[bytes, wasmtime.Module] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, sha256_hash: bytes) -> wasmtime.Module | None:
        with self._lock:
            if sha256_hash in self._cache:
                self._cache.move_to_end(sha256_hash)
                return self._cache[sha256_hash]
            return None

    def put(self, sha256_hash: bytes, module: wasmtime.Module) -> None:
        with self._lock:
            self._cache[sha256_hash] = module
            self._cache.move_to_end(sha256_hash)
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


class TierAWasmRunner:
    """Deterministic, fuel-metered Tier A WebAssembly runner powered by Wasmtime (S13.3)."""

    _instance: TierAWasmRunner | None = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        """Initialize engine, LRU module cache, and monotonic background ticker."""
        cfg = wasmtime.Config()
        cfg.consume_fuel = True
        cfg.epoch_interruption = True
        cfg.wasm_threads = False
        cfg.wasm_simd = True
        cfg.cranelift_opt_level = "speed"
        cfg.cranelift_nan_canonicalization = True

        self._engine = wasmtime.Engine(cfg)
        self._cache = _ModuleLRU(maxsize=128)
        self._ticker_stop = threading.Event()
        self._ticker_thread = threading.Thread(
            target=self._epoch_ticker,
            name="kb-wasmtime-epoch-ticker",
            daemon=True,
        )
        self._ticker_thread.start()

    @classmethod
    def get_instance(cls) -> TierAWasmRunner:
        """Obtain the process-singleton Tier A Wasmtime runner."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _epoch_ticker(self) -> None:
        """Background monotonic ticker incrementing engine epoch every 5ms."""
        while not self._ticker_stop.is_set():
            time.sleep(0.005)
            self._engine.increment_epoch()

    def validate_module(self, wasm_bytes: bytes | bytearray) -> bytes:  # noqa: C901
        """Validate binary structure, exports, imports, and memory bounds, returning sha256."""
        if len(wasm_bytes) < _MIN_WASM_LEN or len(wasm_bytes) > _MAX_WASM_LEN:
            msg = (
                f"WebAssembly binary length ({len(wasm_bytes)}) "
                f"outside permitted range [{_MIN_WASM_LEN}, {_MAX_WASM_LEN}]"
            )
            raise WasmRunError(msg, code="WASM_BINARY_INVALID")

        try:
            mod = wasmtime.Module(self._engine, bytes(wasm_bytes))
        except Exception as ex:
            msg = f"Failed to compile WebAssembly binary: {ex}"
            raise WasmRunError(msg, code="WASM_BINARY_INVALID") from ex

        # Verify Zero Host Capabilities: only env.kb_output allowed
        for imp in mod.imports:
            if imp.module != "env" or imp.name != "kb_output":
                msg = f"Forbidden host import detected: '{imp.module}.{imp.name}'"
                raise WasmRunError(msg, code="WASM_FORBIDDEN_IMPORT")

        # Verify guest ABI exports: memory, kb_alloc, kb_run
        export_names = {exp.name: exp for exp in mod.exports}
        if "memory" not in export_names:
            msg = "Missing required WebAssembly export: 'memory'"
            raise WasmRunError(msg, code="WASM_BINARY_INVALID")
        if "kb_alloc" not in export_names:
            msg = "Missing required WebAssembly export: 'kb_alloc'"
            raise WasmRunError(msg, code="WASM_BINARY_INVALID")
        if "kb_run" not in export_names:
            msg = "Missing required WebAssembly export: 'kb_run'"
            raise WasmRunError(msg, code="WASM_BINARY_INVALID")

        # Verify memory limits <= 512 64KiB pages (32 MiB)
        mem_exp = export_names["memory"]
        mem_type = mem_exp.type
        if isinstance(mem_type, wasmtime.MemoryType):
            if mem_type.limits.min > _MAX_MEMORY_PAGES:
                msg = (
                    f"WebAssembly initial memory pages ({mem_type.limits.min}) "
                    f"exceed {_MAX_MEMORY_PAGES} (32 MiB)"
                )
                raise WasmRunError(msg, code="SCRIPT_MEMORY_LIMIT")
            if mem_type.limits.max is not None and mem_type.limits.max > _MAX_MEMORY_PAGES:
                msg = (
                    f"WebAssembly maximum memory pages ({mem_type.limits.max}) "
                    f"exceed {_MAX_MEMORY_PAGES} (32 MiB)"
                )
                raise WasmRunError(msg, code="SCRIPT_MEMORY_LIMIT")

        sha256_hash = hashlib.sha256(wasm_bytes).digest()
        self._cache.put(sha256_hash, mod)
        return sha256_hash

    def get_or_compile_module(self, wasm_bytes: bytes | bytearray) -> tuple[wasmtime.Module, bytes]:
        """Retrieve pre-compiled Module from LRU cache or compile and validate."""
        sha256_hash = hashlib.sha256(wasm_bytes).digest()
        cached = self._cache.get(sha256_hash)
        if cached is not None:
            return cached, sha256_hash

        self.validate_module(wasm_bytes)
        mod = self._cache.get(sha256_hash)
        if mod is None:
            mod = wasmtime.Module(self._engine, bytes(wasm_bytes))
            self._cache.put(sha256_hash, mod)
        return mod, sha256_hash

    def run_sync(  # noqa: C901, PLR0912, PLR0915
        self,
        wasm_bytes: bytes | bytearray,
        input_bytes: bytes,
        limits: WasmRunLimits | None = None,
    ) -> WasmRunResult:
        """Execute a Tier A WebAssembly module synchronously under strict limits."""
        effective_limits = limits or WasmRunLimits()

        if len(input_bytes) > _MAX_INPUT_PAYLOAD_BYTES:
            msg = (
                f"Input payload ({len(input_bytes)} bytes) exceeds "
                f"maximum permitted {_MAX_INPUT_PAYLOAD_BYTES} bytes"
            )
            raise WasmRunError(msg, code="SCRIPT_TRAP")

        mod, _ = self.get_or_compile_module(wasm_bytes)

        store = wasmtime.Store(self._engine)
        store.set_fuel(effective_limits.max_fuel)
        store.set_limits(
            memory_size=effective_limits.max_memory_bytes,
            table_elements=1024,
            instances=1,
            tables=1,
            memories=1,
        )
        ticks = max(2, math.ceil(effective_limits.timeout_ms / 5.0) + 1)
        store.set_epoch_deadline(ticks)

        captured_output: list[bytes] = []
        output_too_large: list[bool] = []
        call_count: list[int] = [0]
        multiple_calls_detected: list[bool] = []
        bounds_violation_detected: list[bool] = []

        def host_kb_output(caller: wasmtime.Caller, ptr: int, length: int) -> None:
            call_count[0] += 1
            if call_count[0] > 1:
                multiple_calls_detected.append(True)
                return

            if ptr < 0 or length < 0:
                bounds_violation_detected.append(True)
                return

            if length > _MAX_OUTPUT_PAYLOAD_BYTES:
                output_too_large.append(True)
                return

            mem_item = caller["memory"]
            if not isinstance(mem_item, wasmtime.Memory):
                bounds_violation_detected.append(True)
                return

            data_len = mem_item.data_len(caller)
            if ptr + length > data_len:
                bounds_violation_detected.append(True)
                return

            data = bytes(mem_item.read(caller, ptr, ptr + length))
            captured_output.append(data)

        linker = wasmtime.Linker(self._engine)
        output_type = wasmtime.FuncType([wasmtime.ValType.i32(), wasmtime.ValType.i32()], [])
        linker.define_func("env", "kb_output", output_type, host_kb_output, access_caller=True)

        try:
            instance = linker.instantiate(store, mod)
        except wasmtime.WasmtimeError as ex:
            msg = f"Failed to instantiate WebAssembly module: {ex}"
            raise WasmRunError(msg, code="WASM_BINARY_INVALID") from ex

        exports = instance.exports(store)
        kb_alloc = exports["kb_alloc"]
        kb_run = exports["kb_run"]
        memory = exports["memory"]

        if not isinstance(kb_alloc, wasmtime.Func) or not isinstance(kb_run, wasmtime.Func):
            msg = "Exports 'kb_alloc' and 'kb_run' must be functions"
            raise WasmRunError(msg, code="WASM_BINARY_INVALID")

        if not isinstance(memory, wasmtime.Memory):
            msg = "Exported 'memory' is not a valid Memory object"
            raise WasmRunError(msg, code="WASM_BINARY_INVALID")

        store.set_epoch_deadline(ticks)
        start_time = time.perf_counter()
        try:
            # Allocate guest buffer and copy input bytes
            alloc_ptr = kb_alloc(store, len(input_bytes))
            if isinstance(alloc_ptr, int):
                memory.write(store, input_bytes, alloc_ptr)

            # Invoke guest run entrypoint
            ret = kb_run(store, alloc_ptr, len(input_bytes))
        except wasmtime.Trap as trap:
            trap_str = str(trap).lower()
            fuel_remaining = store.get_fuel()
            if fuel_remaining == 0 or "all fuel consumed" in trap_str:
                msg = "WebAssembly execution exhausted instruction fuel (<= 50M)"
                raise WasmRunError(msg, code="SCRIPT_FUEL_EXHAUSTED") from trap
            if "interrupt" in trap_str:
                msg = f"WebAssembly execution timed out (> {effective_limits.timeout_ms}ms)"
                raise WasmRunError(msg, code="SCRIPT_TIMEOUT") from trap
            if "memory" in trap_str or "out of bounds" in trap_str:
                msg = "WebAssembly execution exceeded linear memory limits"
                raise WasmRunError(msg, code="SCRIPT_MEMORY_LIMIT") from trap
            msg = f"WebAssembly execution trapped: {trap}"
            raise WasmRunError(msg, code="SCRIPT_TRAP") from trap

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        fuel_consumed = effective_limits.max_fuel - store.get_fuel()

        if multiple_calls_detected:
            msg = "WebAssembly guest called 'kb_output' multiple times (exactly one call permitted)"
            raise WasmRunError(msg, code="SCRIPT_TRAP")

        if bounds_violation_detected:
            msg = "WebAssembly guest passed out-of-bounds pointer or length to 'kb_output'"
            raise WasmRunError(msg, code="SCRIPT_TRAP")

        if output_too_large:
            msg = "Script output exceeds maximum allowed 65,536 bytes"
            raise WasmRunError(msg, code="SCRIPT_OUTPUT_TOO_LARGE")

        if ret == _MEMORY_LIMIT_EXIT_CODE:
            msg = "Script exceeded linear memory limit during execution"
            raise WasmRunError(msg, code="SCRIPT_MEMORY_LIMIT")

        if ret != 0:
            msg = f"Script execution returned non-zero error code {ret}"
            raise WasmRunError(msg, code="SCRIPT_TRAP")

        result_bytes = captured_output[0] if captured_output else b""
        return WasmRunResult(
            output_bytes=result_bytes,
            fuel_consumed=fuel_consumed,
            duration_ms=duration_ms,
        )

    async def run(
        self,
        wasm_bytes: bytes | bytearray,
        input_bytes: bytes,
        *,
        limits: WasmRunLimits | None = None,
    ) -> WasmRunResult:
        """Asynchronously execute a Tier A WebAssembly module bounded by asyncio.timeout."""
        effective_limits = limits or WasmRunLimits()
        # Add safety margin to the outer asyncio timeout so the inner epoch interruption fires first
        guard_timeout_sec = (effective_limits.timeout_ms + 250) / 1000.0
        try:
            async with asyncio.timeout(guard_timeout_sec):
                return await asyncio.to_thread(
                    self.run_sync,
                    wasm_bytes,
                    input_bytes,
                    effective_limits,
                )
        except TimeoutError:
            msg = f"WebAssembly execution timed out (> {effective_limits.timeout_ms}ms)"
            raise WasmRunError(msg, code="SCRIPT_TIMEOUT") from None
