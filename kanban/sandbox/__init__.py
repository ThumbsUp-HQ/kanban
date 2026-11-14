"""Hardened sandboxed execution subsystem for untrusted scripts and CLI pipes.

Provides dual-tier sandbox support, Linux namespace startup probes, out-of-sandbox
Unix-socket egress proxy with token injection, and seccomp-BPF enforcement.
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
    "TierBNsjailRunner",
    "TierBRunner",
    "TokenInjectingEgressProxy",
    "get_cached_sandbox_probe",
    "probe_nsjail_userns",
    "reset_cached_sandbox_probe",
    "set_cached_sandbox_probe",
]
