# Forensic Verification Audit Packet: KANBA-156

**Ticket:** `KANBA-156` (`docs/tickets/KB-P5-20.md`)  
**Title:** `[Phase 5 / Agent] in_app_sdk transition harness with 5 read-only bare-Git repo tools & ephemeral MCP read tools`  
**Author / Worker:** `p5-156`  
**Gate:** `reality-checker` (Passive Forensic Audit Mode)  
**Status:** Implementation Complete, Tested, Audited, and Ready for Certification  

---

## 1. Executive Summary & Scoped Deliverables

In accordance with specifications `S14.2`, `S14.3`, `S10.1`, and `S15.2`, we implemented the `in_app_sdk` execution harness, 5 sandboxed bare-Git read tools, 4 ephemeral MCP read tools, path traversal guards, secret pattern masking, and deterministic AI cassette replays.

### Target Files Implemented:
1. `agent/tools/repo_path_guard.py`:
   - `normalize_repo_relpath(raw)`: Path validation rejecting NUL, CR/LF, leading `-` (git option injection), leading `/`, backslashes, `.`/`..` traversal segments, empty segments, and paths exceeding 512 UTF-8 bytes (`REPO_PATH_INVALID`).
   - `is_secret_repo_path(relpath)`: Glob matching on `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`, `*id_rsa*`, `*id_ed25519*`, `*id_ecdsa*`, `.git/*`, `.netrc`, `.npmrc`, `.pypirc` returning `REPO_SECRET_PATH_DENIED` on direct access and filtering entries from git outputs.
2. `agent/tools/repo_tools.py` (`BareGitRepoToolkit`):
   - 5 Read-Only Bare-Git Tools: `repo_tree`, `repo_read_file`, `repo_grep`, `repo_git_log`, `repo_git_diff`.
   - Security Sandboxing: Runs via `asyncio.create_subprocess_exec("git", "--git-dir=" + mirror_path, "-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never", ...)`. Clean environment (`GIT_CONFIG_NOSYSTEM=1`, `PATH=/usr/bin:/bin`).
   - Limits: 5.0s timeout (`REPO_TIMEOUT`), 64 KiB output truncation with `[TRUNCATED]`, binary file rejection (`REPO_BINARY_FILE_UNSUPPORTED`), and outbound secret scrubbing via `scrub_text()`.
3. `agent/tools/mcp_read_tools.py` (`EphemeralMcpReadToolkit`):
   - 4 Ephemeral MCP Read Tools: `search_tickets`, `read_ticket`, `search_knowledge`, `read_doc`.
   - Enforces client-side call cap (`MAX_MCP_CALLS = 25`, raising `MCP_CALL_CAP_EXCEEDED` on 26th call).
   - Undeclared or write tools (`update_ticket`, `complete_work`) fail closed with `TOOL_NOT_PERMITTED` without making network calls.
   - Ephemeral bearer header injection and recursive payload secret scrubbing.
4. `agent/harnesses/in_app_sdk.py` (`InAppSdkHarness`):
   - Implements `Harness` protocol for transition gates.
   - Hardened preamble enforcing untrusted delimiter boundary isolation.
   - Tool loop bounded to max 8 turns and max 20 tool calls (`TOOL_LOOP_LIMIT_EXCEEDED`).
   - Token budget reservation, settlement, and release via `BudgetEnforcer`.
   - Dynamic `ctx.verdict_nonce` injection into final verdict JSON bytes.
   - Records ordered `ToolCallTrace` items in `last_tool_traces` and generates `HarnessRunReport`.
5. `agent/gates/worker.py`:
   - Registered `"in_app_sdk"` in `HarnessRegistry._register_defaults()`.
6. `agent/GEMINI.md`:
   - Updated documentation covering `InAppSdkHarness`, bare-Git repo tools, ephemeral MCP read tools, tool loop bounds, and security invariants.
7. Cassettes:
   - `tests/fixtures/ai/in_app_sdk_approve_with_diff.yaml`
   - `tests/fixtures/ai/in_app_sdk_tool_loop_exceeded.yaml`
   - `tests/fixtures/ai/in_app_sdk_forbidden_tool_attempt.yaml`
   - Existing `tests/fixtures/ai/transition_rls_veto.yaml` replayed and verified.

---

## 2. Definition of Done Compliance Audit

| Requirement / Pass Criteria | Verification Method | Status |
| :--- | :--- | :--- |
| **Target Files Implemented** | Code inspection of `agent/tools/`, `agent/harnesses/`, `agent/gates/worker.py` | PASS |
| **Cassettes Validated** | Loaded and validated with `load_cassette()` across test suite | PASS |
| **Coverage Requirement (>=95%)** | Pytest line + branch coverage across `agent.tools` and `agent.harnesses.in_app_sdk` | **PASS (96.56%)** |
| **0 Pytest Failures** | 28/28 tests passing | **PASS (28 passed in 4.83s)** |
| **Ruff Check (0 warnings/errors)** | `uv run ruff check agent/tools agent/harnesses agent/tests/tools agent/tests/harnesses agent/context/transition_context.py agent/gates/worker.py` | **PASS (0 errors)** |
| **Mypy Strict (0 errors)** | `uv run mypy --strict agent` | **PASS (99 source files clean)** |
| **Import Linter Contracts Kept** | `uv run lint-imports` | **PASS (2 kept, 0 broken)** |
| **Forensic Proof Packet Complete** | 6 raw artifact files populated in `docs/qa/KANBA-156/` | PASS |

---

## 3. Forensic Proof Artifacts Inventory

All proof artifacts are unedited, static text files located in [docs/qa/KANBA-156/](file:///home/adamoutler/kanban/docs/qa/KANBA-156/):

1. **`git-diff.patch`**:
   - Location: [docs/qa/KANBA-156/git-diff.patch](file:///home/adamoutler/kanban/docs/qa/KANBA-156/git-diff.patch)
   - Size: ~99 KB unified diff containing all scoped tools, harnesses, manifests, cassettes, and test suites.
2. **`unit-test-results.txt`**:
   - Location: [docs/qa/KANBA-156/unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-156/unit-test-results.txt)
   - Result: 28 passed in 4.83s. Total line + branch coverage: **96.56%** (exceeding 95% threshold).
3. **`build-check.txt`**:
   - Location: [docs/qa/KANBA-156/build-check.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-156/build-check.txt)
   - Result: Ruff clean (exit 0), Mypy strict clean (exit 0), Lint-imports clean (exit 0).
4. **`tool-trace-sample.json`**:
   - Location: [docs/qa/KANBA-156/tool-trace-sample.json](file:///home/adamoutler/kanban/docs/qa/KANBA-156/tool-trace-sample.json)
   - Result: Verbatim tool trace replay of `transition_rls_veto.yaml` displaying ordered traces for `read_ticket` and `repo_grep` with timing, redacted arguments, byte sizes, and validated `reject` decision payload with authenticated nonce.
5. **`secret-mask-proof.txt`**:
   - Location: [docs/qa/KANBA-156/secret-mask-proof.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-156/secret-mask-proof.txt)
   - Result: Concrete verification of secret masking across all 4 repo tools (`repo_tree`, `repo_read_file`, `repo_grep`, `repo_git_diff`) excluding `.env.production` and `certs/server.key`.
6. **UI Screenshots**:
   - N/A: Non-UI backend agent harness ticket.
