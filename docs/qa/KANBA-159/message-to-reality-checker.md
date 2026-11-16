# Verification Audit Request: KANBA-159 (KB-P5-22b)

**Ticket:** `KANBA-159` (`KB-P5-22b`): `[Phase 5 / Agent + Deploy] kanban-agent-runner outbound mTLS WSS daemon, local :ro repo/CLI execution & Dockerfile agent-runner target`  
**Author:** `@p5-157`  
**Target QA Gate:** `reality-checker`  

---

## Executive Summary
All Technical Actions and Definitions of Done for ticket `KANBA-159` are complete, verified with automated unit tests achieving **95.41% line+branch coverage** (exceeding the >= 95% threshold), zero compiler/linter warnings (`ruff`, `mypy --strict agent`, `lint-imports`), a cleanly built and validated Docker `agent-runner` target with `USER 65532:65532` and zero `EXPOSE` directives, and passive forensic artifacts deposited in `docs/qa/KANBA-159/`.

---

## Deliverables & Security Invariants

### 1. Configuration & CLI Enrollment (`agent/remote_runner/config.py`, `agent/remote_runner/cli.py`)
- **Strict Pydantic v2 Config:** `RunnerConfig` (`extra="forbid"`, `strict=True`) validates URL schemas, UUIDs, integer concurrency (1..8), and local repo mount dictionaries.
- **Key Permission Enforcement:** `validate_key_permissions` enforces `0600`/`0400` on the runner private key file. If group or other permission bits are set (`st_mode & 0o077 != 0`), boots fail immediately with `KeyPermissionsError(KEY_PERMISSIONS_TOO_OPEN)`.
- **Command-Line Secrecy:** `kanban-agent-runner enroll` exclusively accepts enrollment tokens via `--token-stdin` (reading from stdin). Passing `--token` on argv is explicitly disallowed to prevent token exposure in `/proc/<pid>/cmdline`. The CLI generates a fresh P-256 ECDSA keypair, secures it with `0600`, submits a CSR to `/api/v1/agent-runners/enroll`, and atomically persists `client.crt` and `ca.crt`.

### 2. Hardened Job Execution & Zeroization (`agent/remote_runner/executor.py`)
- **Read-Only Mount Enforcement:** For `ro_vfs_mount` jobs, `RunnerJobExecutor` queries `os.statvfs(repo_path).f_flag & os.ST_RDONLY`. If the filesystem is not mounted read-only, execution is rejected with `RUNNER_MOUNT_NOT_READONLY`.
- **Symlink Escape Defense:** Validates that configured repo paths resolve strictly inside the allowed mount root, preventing symlink traversal attacks outside the sandbox (`RUNNER_REPO_NOT_MOUNTED`).
- **Server-Frame Defense-in-Depth:** For `cli_pipe` jobs, `assert_runtime_argv` double-checks CLI flags before process spawn, blocking banned flags (`--yolo`, `--dangerously-*`) with `RUNNER_BANNED_CLI_FLAG` even if sent by a compromised or buggy server.
- **Volatile Token Hygiene:** MCP ephemeral bearer tokens from `job.dispatch` are held in mutable `bytearray` memory and zeroized in a `finally` block before returning the job result.

### 3. Outbound-Only mTLS TLS 1.3 Daemon (`agent/remote_runner/daemon.py`)
- **Zero Inbound Ports:** Connects strictly outbound to `wss://<host>/api/v1/agent-runners/ws` over TLS 1.3 (`ssl.TLSVersion.TLSv1_3` minimum) with mutual certificate verification. Binds zero listening TCP/UDP ports.
- **Heartbeat & Resiliency:** Runs a 15-second heartbeat loop and handles transient disconnects using full-jitter exponential backoff (1.0s .. 60.0s).
- **Sub-250ms Cancellation:** Incoming `job.cancel` frames cancel the active task within < 250ms (measured at 1.47ms in e2e tests).
- **Revocation Safety:** Server close code `4003` raises `RunnerRevokedError` and terminates the daemon with exit code `78` (`RUNNER_REVOKED`) without reconnecting.

### 4. Container & Reference Compose (`Dockerfile`, `deploy/runner/docker-compose.runner.example.yml`)
- **`agent-runner` Docker Target:** Built on `runtime-slim` with `git`, `USER 65532:65532`, 0 `EXPOSE` directives, zero database/web assets, and `ENTRYPOINT ["/usr/bin/tini", "--", "kanban-agent-runner"]`.
- **Compose Hardening:** Reference compose specifies `read_only: true`, `cap_drop: [ALL]`, and mounts repositories as `:ro`.

---

## Verification Evidence & Artifact Index

All artifacts are present in `docs/qa/KANBA-159/`:

1. `docs/qa/KANBA-159/git-diff.patch`: Unified diff of all modified and newly created files.
2. `docs/qa/KANBA-159/unit-test-results.txt`:
   - Command: `uv run pytest agent/tests/remote_runner tests/deploy/test_dockerfile_agent_runner.py -q -p no:cacheprovider --cov=agent.remote_runner --cov-branch --cov-report=term-missing --cov-fail-under=95`
   - Results: **25 passed in 5.27s**, **95.41% total coverage**, `EXIT_CODE=0`.
3. `docs/qa/KANBA-159/build-check.txt`:
   - `ruff check`: All checks passed (`EXIT_CODE=0`).
   - `ruff format --check`: 10 files checked, clean (`EXIT_CODE=0`).
   - `mypy --strict agent`: Success, 0 issues across 109 source files (`EXIT_CODE=0`).
   - `lint-imports`: 2 contracts kept, 0 broken (`EXIT_CODE=0`).
   - `docker build --target agent-runner`: Built clean (`EXIT_CODE=0`).
4. `docs/qa/KANBA-159/container-inspect.json`:
   - Inspect: `{"User":"65532:65532", "Entrypoint":["/usr/bin/tini","--","kanban-agent-runner"], "Cmd":["run"], ...}` (0 exposed ports).
   - `--help`: Outputs `enroll` and `run` subcommands.
5. `docs/qa/KANBA-159/mtls-loopback-trace.txt`:
   - Negotiated protocol: `TLSv1.3`.
   - Peer cert SAN: `urn:kanban:agent-runner:<uuid>`.
   - Tool events captured: `['read_ticket', 'repo_grep']`.
   - Cancellation latency: `1.47ms` (< 250ms SLA).
   - Results: 8 passed in 1.96s (`EXIT_CODE=0`).
6. Non-UI Scope:
   - Non-UI ticket; no UI screenshots required.

---

## Conclusion & Request
Ticket `KANBA-159` satisfies all requirements and Definition of Done criteria. Please review and certify Grade-A `READY`.
