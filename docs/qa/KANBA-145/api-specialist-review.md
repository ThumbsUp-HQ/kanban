# API Specialist Gate Review: KANBA-145 (KB-P5-14)

- **Ticket**: `KANBA-145` (`KB-P5-14`: `[Phase 5 / Sandbox + Deploy] Tier B nsjail runner, seccomp-BPF sandbox-profile.json, Unix-socket token-injecting proxy & standalone CLONE_NEWUSER probe`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-145` (`HEAD: f82ae29`)
- **Worktree**: `/tmp/kb-wt-KANBA-145`
- **Scope**: `kanban/api/middleware/script_depth.py`, `kanban/sandbox/egress_proxy.py`, `kanban/sandbox/nsjail_runner.py`, `kanban/sandbox/probe.py`, `kanban/app.py`, `deploy/standalone/storage_probe.py`, `deploy/seccomp/sandbox-profile.json`

---

### 1. Architectural & Security Evaluation

#### A. Recursion & Re-entrancy Prevention (`ScriptDepthGuardMiddleware`, S13.3)
- Middleware inspects incoming HTTP request header `X-Kanban-Script-Depth`.
- Any non-digit value or integer value >= 1 targeting mutating or script execution endpoints:
  - `/api/v1/issues/{id}/custom-fields/{field_id}/execute`
  - `/api/v1/issues/{id}/transitions`
  - `/mcp/*`
  is immediately rejected with HTTP 409 Conflict and error code `SCRIPT_RECURSION_BLOCKED`.
- Read-only queries to `/api/v1/issues/{id}/custom-fields` return cached field values without re-executing scripts, ensuring safe inspection without recursion hazards.
- Scope state `scope["state"]["script_depth"]` is cleanly populated for downstream handler inspection.

#### B. Unix-Socket Token-Injecting Egress Proxy (`TokenInjectingEgressProxy`, S13.3, S3.2)
- Server socket is created strictly on a local Unix stream socket (`proxy.sock`) inside a private `0700` directory with `0600` socket permissions.
- Injects short-lived caller credentials (`TTL <= 15s`, `X-Kanban-Script-Depth: 1`) on outbound HTTP requests forwarded to the host app ASGI handler without exposing raw tokens inside the sandbox environment.
- Host token buffer is managed in mutable `bytearray` and securely wiped (`token_buf[:] = b"\x00" * len(token_buf)`) in a guaranteed `finally` block upon proxy stop.
- Strict request enforcement:
  - Max 10 requests per execution lifetime; the 11th request receives HTTP 429 `TOO_MANY_REQUESTS`.
  - Expired tokens receive HTTP 401 `UNAUTHORIZED`.
  - Strict method allowlist: only `GET` is permitted; `POST`/`PUT`/`DELETE` receive HTTP 405 `METHOD_NOT_ALLOWED`.
  - Strict path prefix validation: only allowlisted subpaths under `/api/v1/...` are allowed. Dot-dot traversal (`..`) and non-allowlisted routes receive HTTP 403 `FORBIDDEN`.
  - Body streaming cap: capped at 512 KiB; excess payload triggers HTTP 413 `REQUEST_ENTITY_TOO_LARGE`.
- Wire exchange verification: fully verified in `docs/qa/KANBA-145/proxy-exchange-trace.json`.

#### C. Subprocess Launcher & Namespace Probe (`probe_nsjail_userns`, S13.3)
- Dry-run self-test validates `nsjail` binary existence, UID 0 root ownership, non-writable permissions, and execution capabilities with 500ms timeout.
- Host systems lacking `CLONE_NEWUSER` or unprivileged user namespaces fail closed with `SANDBOX_UNAVAILABLE_IN_STANDALONE` rather than silently executing untrusted code on the host.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 46/46 passed in 3.87s (`kanban/tests/sandbox/`).
- **Coverage**: 98.80% total branch+line coverage across all touched modules:
  - `kanban/api/middleware/script_depth.py`: 100%
  - `kanban/sandbox/__init__.py`: 100%
  - `kanban/sandbox/egress_proxy.py`: 98%
  - `kanban/sandbox/nsjail_runner.py`: 99%
  - `kanban/sandbox/probe.py`: 100%
- **Static Analysis**: Ruff check clean (0 errors), Ruff format clean (1249 files), Mypy strict clean (425 source files), ImportLinter 2/2 kept, zero Unicode dashes.

---

### 3. Gate Verdict

The API and middleware implementations satisfy all security and architectural requirements.

STATUS: APPROVED
Verdict: APPROVED
