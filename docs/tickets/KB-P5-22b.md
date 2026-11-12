---
id: KB-P5-22b
title: "[Phase 5 / Agent + Deploy] kanban-agent-runner outbound mTLS WSS daemon, local :ro repo/CLI execution & Dockerfile agent-runner target"
epic: KB-E5
depends_on: [KB-P5-22a, KB-P5-20, KB-P5-21, KB-P0-08]
spec_sections: ["14.2", "14.3", "2.4"]
gates: [reality-checker]
new_dependencies: []
state: Backlog
---

> Split note: second half of manifest row `KB-P5-22` (see `KB-P5-22a`).

### User Story
As a **DevSecOps engineer running transition gates on an air-gapped GPU box or isolated CI host**, I need **the standalone `kanban-agent-runner` daemon and `Dockerfile` `agent-runner` image target that connects outbound over TLS 1.3 mTLS `WSS` with zero inbound listening ports, verifies local Git mounts are read-only, and executes `ollama`/`gemini` or `agy -p`/`codex -p` jobs** so that **remote source repositories and local GPUs can evaluate workflow gates without opening firewall ports or risking repository mutation**.

**Requirement Traceability:** `S14.2` item 3 (`kanban-agent-runner` daemon outbound mTLS TLS 1.3 `WSS`, local `:ro` source checkouts), `S14.3` (`assert_runtime_argv` before CLI spawn, secret-path masking, ephemeral MCP token handling), `S2.4` (`Dockerfile` target `agent-runner`, container row `kanban-agent-runner`: outbound TLS 1.3 `WSS` to `reverse-proxy`, zero inbound firewall ports) | Original requirement `#2`, `#3` | **Dependencies:** `KB-P5-22a`, `KB-P5-20`, `KB-P5-21`, `KB-P0-08`

### Scoped Technical Actions
1. **Target Files:**
   - `agent/remote_runner/config.py` (`RunnerConfig` Pydantic v2 settings, `extra="forbid"`)
   - `agent/remote_runner/executor.py` (`RunnerJobExecutor` dispatching to `BareGitRepoToolkit`/`InAppSdkHarness` or `CliPipeHarness` with `:ro` mount verification)
   - `agent/remote_runner/daemon.py` (`RunnerDaemon` outbound TLS 1.3 mTLS WSS loop, jittered backoff, heartbeat, cancel propagation)
   - `agent/remote_runner/cli.py` (`kanban-agent-runner` CLI with `enroll` and `run` subcommands; registered under `[project.scripts]` in `agent/pyproject.toml`)
   - `Dockerfile` (modify: add stage `agent-runner` extending `runtime-slim` base with `git` + `nsjail` where packaged, `USER 65532:65532`, zero `EXPOSE` directives, zero Postgres/Caddy/SPA assets, `ENTRYPOINT ["/usr/bin/tini", "--", "kanban-agent-runner"]`)
   - `deploy/runner/docker-compose.runner.example.yml` (reference compose mounting `/workspace/repos:ro`, `read_only: true`, `cap_drop: [ALL]`)
   - `agent/GEMINI.md` (update runner operational contract)
2. **TLS 1.3 Outbound-Only mTLS Client (`agent/remote_runner/daemon.py`):**
   - Builds `ssl.SSLContext(ssl.Purpose.SERVER_AUTH)` with `minimum_version = ssl.TLSVersion.TLSv1_3`, `verify_mode = ssl.CERT_REQUIRED`, `check_hostname = True`, pinned server CA bundle (`config.ca_cert_path`), and runner client cert + `0600` private key (`config.client_cert_path`, `config.client_key_path`; startup refuses to boot if private key file permissions have group/other bits `(st_mode & 0o077) != 0`).
   - Connects strictly outbound to `wss://.../api/v1/agent-runners/ws` (`trust_env=False` unless explicit `https_proxy` configured in `RunnerConfig`); binds **zero** listening TCP/UDP sockets anywhere in the process.
   - Sends `hello`, maintains `15s` `heartbeat` task, enforces `asyncio.Semaphore(config.max_concurrency)` (`1..8`), cancels the running `asyncio.Task` + child process group within `< 250ms` upon receiving `job.cancel` or WebSocket disconnect, and reconnects with full-jitter exponential backoff (`1.0s .. 60.0s`) unless close code is `4003` (revoked -> halts daemon with exit code `78` `RUNNER_REVOKED`).
3. **Runner-Side `:ro` Repo Verification & Execution (`agent/remote_runner/executor.py`):**
   - Repo mapping: `RunnerConfig.repo_mounts: Mapping[str, Path]` maps approved repo slugs to local paths under `/workspace/repos/<slug>`. Unmapped slug -> `job.result {status: "error", error_code: "RUNNER_REPO_NOT_MOUNTED"}`.
   - Before running any job with `repo_access_mode != "none"`:
     - Verifies the path resolves inside the configured mount root (no symlink escape), AND either (a) is a bare Git repo used exclusively through `BareGitRepoToolkit` (`KB-P5-20`) with `is_secret_repo_path` masking, OR (b) for `ro_vfs_mount`, verifies `(os.statvfs(repo_path).f_flag & os.ST_RDONLY) != 0` (refuses writable host mounts with `RUNNER_MOUNT_NOT_READONLY` unless cloned via `RoRepoSnapshotManager` + `nsjail` from `KB-P5-21`).
   - For `cli_pipe` agent specs: calls `assert_runtime_argv` (`KB-P5-16`) before spawning; refuses banned flags (`--yolo`, `--dangerously-*`) even if a compromised server frame attempted to send them (`RUNNER_BANNED_CLI_FLAG`).
   - Holds `ephemeral_mcp_token` from `job.dispatch` in a `bytearray` and zeroes it in `finally` before sending `job.result`.
4. **`kanban-agent-runner` CLI (`agent/remote_runner/cli.py`):**
   - `kanban-agent-runner enroll --server-url https://... --token-stdin --pool <slug> --state-dir /var/lib/kanban-runner`: reads single-use enrollment token from `stdin` (never `--token` CLI arg where `/proc/<pid>/cmdline` exposes it!), generates ECDSA P-256 keypair (`0600` atomic write), submits CSR to `/api/v1/agent-runners/enroll`, writes `client.crt` and `ca.crt`.
   - `kanban-agent-runner run --config /etc/kanban-runner/config.yaml`: validates config & key permissions, runs `RunnerDaemon` until `SIGINT`/`SIGTERM` (drains or cancels cleanly).

### Mandatory Feature Unit Tests
- **Test File(s):**
  - `agent/tests/remote_runner/test_config_and_enroll.py`
  - `agent/tests/remote_runner/test_executor.py`
  - `agent/tests/remote_runner/test_daemon_e2e.py` (connects `RunnerDaemon` to `RunnerWssHub` from `KB-P5-22a` over an in-memory / loopback TLS 1.3 mTLS pair generated in `tmp_path` using `cryptography`)
  - `tests/deploy/test_dockerfile_agent_runner.py`
- **Required Test Cases:**
  1. Positive (end-to-end loopback mTLS WSS): `enroll` exchanges token over `stdin` for P-256 leaf cert (`0600` key); `RunnerDaemon` connects over TLS 1.3 mTLS to `RunnerWssHub`, executes both an `in_app_sdk` job (`FixtureLLMProvider` cassette `transition_rls_veto.yaml` + bare Git fixture) and a `cli_pipe` job (`FixtureCLIRunner` cassette `cli_agy_approve.yaml`), emits `job.tool_event` frames, and delivers valid `kb-transition-verdict/v1` bytes.
  2. Security (key permissions & cmdline secrecy): `client.key` with mode `0644` -> `RunnerDaemon` refuses to start with `KEY_PERMISSIONS_TOO_OPEN`; passing `--token` on argv is unsupported/rejected so secrets only enter via `--token-stdin`.
  3. Security (writable mount refusal & server-frame defense-in-depth): `ro_vfs_mount` pointing to a writable directory (`ST_RDONLY` unset and `nsjail` disabled) fails closed with `RUNNER_MOUNT_NOT_READONLY`; crafted `job.dispatch` carrying `cli_args: ["-p", "--yolo"]` is blocked on the runner by `assert_runtime_argv` (`RUNNER_BANNED_CLI_FLAG`) with `0` subprocess spawns.
  4. Security (TLS 1.3 & revocation halt): TLS 1.2-only server rejected by `SSLContext.minimum_version == TLSv1_3`; server closing WSS with `4003` (revoked) causes `RunnerDaemon` to cancel running jobs, zero token `bytearray`s, and exit `78` without reconnecting.
  5. Fault & boundary: transient WSS drop triggers jittered backoff (`1s..60s` via injected clock) and re-handshake; `job.cancel` cancels a blocked job within `< 250ms`; `Dockerfile` `agent-runner` stage inspection confirms `USER 65532:65532` and `0` `EXPOSE` lines.
- **Coverage:** `>= 95%` line + branch across `agent.remote_runner`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** `agent/remote_runner/config.py`, `agent/remote_runner/executor.py`, `agent/remote_runner/daemon.py`, `agent/remote_runner/cli.py`, `deploy/runner/docker-compose.runner.example.yml`, and `Dockerfile` target `agent-runner` exist and implement all specifications above.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest agent/tests/remote_runner tests/deploy/test_dockerfile_agent_runner.py -q -p no:cacheprovider --cov=agent.remote_runner --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with `0` failures.
- [ ] **Container Target Builds Clean:** `docker build --target agent-runner -t kanban:agent-runner .` exits `0`, `docker run --rm kanban:agent-runner --help` prints `enroll` and `run`, and `docker image inspect kanban:agent-runner` shows `User == "65532:65532"` and empty `ExposedPorts`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict agent && uv run lint-imports` exits `0`.
- [ ] **Forensic Proof Packet Complete:** All files listed below exist in `docs/qa/<TICKET_ID>/`.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
The implementing sub-agent MUST populate `docs/qa/<TICKET_ID>/` with the following raw, unedited artifacts (no summaries) so `reality-checker` can audit the ticket without executing commands:
1. `docs/qa/<TICKET_ID>/git-diff.patch` - Complete unified `git diff`.
2. `docs/qa/<TICKET_ID>/unit-test-results.txt` - Full output and exit code of the DoD pytest command.
3. `docs/qa/<TICKET_ID>/build-check.txt` - Full output of ruff, mypy, lint-imports, and `docker build --target agent-runner`.
4. `docs/qa/<TICKET_ID>/container-inspect.json` - Output of `docker image inspect kanban:agent-runner --format '{{json .Config}}'` + `docker run --rm kanban:agent-runner --help`.
5. `docs/qa/<TICKET_ID>/mtls-loopback-trace.txt` - Test output showing TLS protocol version `TLSv1.3`, client cert SAN URI, dispatched tool events, and `job.cancel` cancellation latency.
6. Screenshots: N/A - Non-UI Ticket.
