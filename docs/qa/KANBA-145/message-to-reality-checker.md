# Reality-Checker Audit Note: KANBA-145 (KB-P5-14)

## Architectural Scope & Technical Implementation
This ticket (`KANBA-145` / `KB-P5-14`: `[Phase 5 / Sandbox + Deploy] Tier B nsjail runner, seccomp-BPF sandbox-profile.json, Unix-socket token-injecting proxy & standalone CLONE_NEWUSER probe`) implements the hardened Tier B script execution runtime, seccomp-BPF policy, out-of-sandbox Unix stream token-injecting egress proxy, standalone user namespace probe, and script recursion guard middleware under Spec S13.3, S14.1, S3.2, and S15.5:

1. **Target Files**:
   - `deploy/seccomp/sandbox-profile.json`: Strict OCI / Kafel seccomp-BPF profile with `defaultAction: "SCMP_ACT_ERRNO"` (errnoRet 1), AF_UNIX domain=1 allowed strictly, and 23 container-escape syscalls denied.
   - `kanban/sandbox/probe.py`: `SandboxProbeResult`, `SandboxUnavailableError`, `SubprocessLauncher` protocol, and `probe_nsjail_userns()` verifying `nsjail` binary existence, UID 0 root ownership, non-writable permissions, and executing 500ms dry self-test. Fails closed with `SANDBOX_UNAVAILABLE_IN_STANDALONE`.
   - `deploy/standalone/storage_probe.py`: Extended `StandaloneStatus` with `tier_b_sandbox_available: bool = False` and `tier_b_unavailable_reason: str | None = None`.
   - `kanban/api/middleware/script_depth.py`: `ScriptDepthGuardMiddleware` inspecting `X-Kanban-Script-Depth`. Non-digit or `>= 1` targeting `/api/v1/issues/*/custom-fields/*/execute`, `/api/v1/issues/*/transitions`, or `/mcp/*` rejected with HTTP 409 `SCRIPT_RECURSION_BLOCKED`. `GET .../custom-fields` returns cached values.
   - `kanban/sandbox/egress_proxy.py`: `TokenInjectingEgressProxy` and `EgressProxyPolicy`. Out-of-sandbox Unix stream server over `proxy.sock` (`0600`) in `0700` dir. Injects short-lived token (`TTL <= 15s`, `X-Kanban-Script-Depth: 1`) without exposing token inside sandbox. Host token buffer in mutable `bytearray` securely zeroed in guaranteed `finally`. Max 10 requests (`429`), expiry (`401`), strictly `GET` (`405`), allowlisted paths under `/api/v1/...` with path traversal defense (`403`), 512 KiB body streaming cap (`413`).
   - `kanban/sandbox/nsjail_runner.py`: `TierBNsjailRunner` implementing `TierBRunner` from `KB-P5-13`. Spawns `nsjail` with explicit argv (`--mode o`, `--time_limit 3`, `--cgroup_mem_max 134217728`, `--disable_clone_newnet=false`, `--chroot`, tmpfs `/tmp`, bind-mount `proxy.sock`, `--seccomp_policy`, `--keep_env=false`, `--env KANBAN_EGRESS_SOCK=/run/sandbox/proxy.sock`). Streams `kb-field-input/v1` over stdin, kills process group on timeout (`SCRIPT_TIMEOUT`), caps stdout at 64 KiB (`SCRIPT_OUTPUT_TOO_LARGE`).
   - `kanban/app.py`: Wired `app.state.tier_b_runner = TierBNsjailRunner()` and registered `ScriptDepthGuardMiddleware`.
   - `kanban/GEMINI.md`: Updated with sandbox contracts, failure codes, and probe/proxy/depth guard details.

2. **Mandatory Test Cases Verified (DoD Items 1-7)**:
   - **Test Case 1 (`test_nsjail_runner.py`)**: `nsjail` argv construction verified with exact CLI flags, `134217728` cgroup cap, `keep_env=false`, proxy socket bind mount, and zero token leakage. Process timeout kills process group and returns `SCRIPT_TIMEOUT`. Excessive stdout (>64 KiB) returns `SCRIPT_OUTPUT_TOO_LARGE`.
   - **Test Case 2 (`test_seccomp_profile.py`)**: Strict seccomp JSON parsed and verified. `defaultAction` is `SCMP_ACT_ERRNO` with `errnoRet: 1`. 23 container escape syscalls are explicitly blocked. AF_UNIX domain 1 is allowed.
   - **Test Case 3 (`test_egress_proxy.py`)**: Unix-socket proxy created in `0700` directory with `0600` socket permissions. Forwards HTTP GET with injected bearer token and `X-Kanban-Script-Depth: 1`. Rejects non-allowlisted paths and `..` directory traversal with HTTP 403.
   - **Test Case 4 (`test_egress_proxy.py`)**: Egress proxy enforces 10-request cap (11th request returns 429), token TTL expiration (returns 401), non-GET methods (returns 405), and body size limit of 512 KiB (returns 413). Host memory token buffer zeroed on shutdown.
   - **Test Case 5 (`test_script_depth_middleware.py`)**: Request with `X-Kanban-Script-Depth: 1` targeting execute, transition, or MCP endpoints returns HTTP 409 `SCRIPT_RECURSION_BLOCKED`. Read-only GET returns cached values without re-executing scripts.
   - **Test Case 6 (`test_userns_probe.py`)**: `probe_nsjail_userns` detects missing binary, non-root ownership, writable permissions, dry self-test timeout, and successful dry self-test. Host without unprivileged user namespaces fails closed with `SANDBOX_UNAVAILABLE_IN_STANDALONE`.
   - **Test Case 7 (`test_userns_probe.py`)**: `StandaloneStatus` model includes `tier_b_sandbox_available` and `tier_b_unavailable_reason`. Probe integrates into standalone health check and reports accurate state.

3. **Verification & Quality Metrics**:
   - **Unit Tests**: 65/65 pytest passed in 5.03s with **98.64%** branch+line coverage (`kanban.sandbox` + `kanban.api.middleware.script_depth`), exceeding the 95% threshold.
   - **Static Checks**: Ruff check clean, Ruff format clean (1249 files), Mypy strict clean (425 source files), Lint-imports clean (2 kept, 0 broken), zero Unicode dashes repo-wide.
   - **Argv Trace**: `nsjail-argv-trace.txt` captures verified `nsjail` execution arguments and environment array demonstrating zero token leakage and `134217728` memory limit.
   - **Proxy Trace**: `proxy-exchange-trace.json` captures all 6 required HTTP wire exchanges (`200 OK`, `405 Method Denied`, `403 Path Denied`, `409 Recursion Blocked`, `429 Rate Cap`, `401 Expired`) with bearer tokens cleanly redacted.
