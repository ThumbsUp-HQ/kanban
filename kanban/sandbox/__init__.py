# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hardened sandboxed execution subsystem for untrusted scripts and CLI pipes.

Provides dual-tier sandbox support, Linux namespace startup probes, out-of-sandbox
Unix-socket egress proxy with token injection, seccomp-BPF enforcement, and Tier A
Wasmtime module execution (KB-P5-13, KB-P5-14).
"""

from __future__ import annotations

from kanban.sandbox.egress_proxy import EgressProxyPolicy, TokenInjectingEgressProxy
from kanban.sandbox.nsjail_runner import (
    DefaultSubprocessLauncher,
    NsjailCommandBuilder,
    NsjailRunResult,
    SandboxExecutionError,
    ScriptOutputTooLargeError,
    ScriptTimeoutError,
    TierBNsjailRunner,
    TierBRunner,
)
from kanban.sandbox.probe import (
    SandboxProbeResult,
    SandboxUnavailableError,
    SubprocessLauncher,
    get_cached_sandbox_probe,
    probe_nsjail_userns,
    reset_cached_sandbox_probe,
    set_cached_sandbox_probe,
)
from kanban.sandbox.wasm_runner import (
    TierAWasmRunner,
    UnavailableTierBRunner,
    WasmRunError,
    WasmRunLimits,
    WasmRunResult,
)

__all__ = [
    "DefaultSubprocessLauncher",
    "EgressProxyPolicy",
    "NsjailCommandBuilder",
    "NsjailRunResult",
    "SandboxExecutionError",
    "SandboxProbeResult",
    "SandboxUnavailableError",
    "ScriptOutputTooLargeError",
    "ScriptTimeoutError",
    "SubprocessLauncher",
    "TierAWasmRunner",
    "TierBNsjailRunner",
    "TierBRunner",
    "TokenInjectingEgressProxy",
    "UnavailableTierBRunner",
    "WasmRunError",
    "WasmRunLimits",
    "WasmRunResult",
    "get_cached_sandbox_probe",
    "probe_nsjail_userns",
    "reset_cached_sandbox_probe",
    "set_cached_sandbox_probe",
]
