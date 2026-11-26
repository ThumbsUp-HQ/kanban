# Message to Reality-Checker: Forensic QA Audit Packet for KAN-413

**Author / Swarm Worker:** `b-kan413`  
**Target Ticket:** `KAN-413` (`[SLICE-2-P3][KB-AI-WORKOUT] Phase 3: Live Gemini/Ollama AI Provider, Autonomous Agent & mTLS Runner Workout + Screenshots`)  
**Parent Epic:** `KAN-410` (`[EPIC][SLICE-2-AI-AGENTS-RUNNERS]`)  
**Target Documentation Ticket:** `KAN-414` (`[SLICE-2-P4][KB-AI-DOCS]`)  
**Branch:** `feat/KAN-413-slice2-ai-workout` (base `1bbc9981`, implementation commit `fa3ea25d`, specialist re-stamps `9f6d3b6d` and `1fe908fa`)  
**Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan413-b9640aad`  
**Status:** **READY FOR REALITY-CHECKER AUDIT**  
**Pre-Prod Safety Invariant:** Absolute zero mutations on protected pre-production (`192.168.1.101` / `k.hackedyour.info` / `inferrence1`). All live workouts executed hermetically against isolated local PostgreSQL container `kan413-pg-test-1`, companion fixture `127.0.0.1:11435`, and dedicated local Kanban server `127.0.0.1:18413`.

---

## 1. Executive Summary & Verification Matrix

Phase 3 executes comprehensive end-to-end verification, in-flight bug fixes, zero-mock multi-viewport visual audits, and forensic QA bundle creation for Slice 2 AI Providers, Token Budgets, Autonomous Agents, and Remote Runners:

| Verification Area | Requirement & Scoped Action | Forensic Evidence & Result | Status |
| :--- | :--- | :--- | :---: |
| **Provider Creation & Presets** | Create Ollama, OpenAI, and Gemini providers via `AiProviderEditorDrawer`; verify 0 `input[type="password"]` fields in DOM. | Created via `POST /api/v1/workspaces/{ws}/ai-providers` (HTTP 201 Created). DOM inspection confirmed exactly 0 password inputs (`input[type="password"]`). | **PASS** |
| **Model Probing & Connection** | Live model probe and connection check (`POST .../probe`, `POST .../test-connection`). | Received HTTP 200 OK with dynamic model metadata: Ollama (`llama3.2:latest`, `qwen2.5-coder:latest`), OpenAI (`gpt-4o`, `gpt-4o-mini`), Gemini (`gemini-2.5-flash`, `gemini-2.5-pro`). | **PASS** |
| **Failover Stack Reordering** | Atomic priority stack reordering (`PUT .../order`). | Reordered stack to `[OpenAI (10), Ollama (20), Gemini (30)]` via `PUT /api/v1/workspaces/{ws}/ai-providers/order` (HTTP 200 OK). | **PASS** |
| **Monthly Token Budgets** | Verify 0 allowance (Hard AI Freeze) and unlimited quota (10B tokens). | `token_cap = 0` triggers `Hard AI Freeze` warning banner and blocks completions; `token_cap = 10_000_000_000` persists round-trip cleanly (HTTP 200 OK). | **PASS** |
| **Air-Gap Egress Wall** | Configure `air_gap_mode = True`; prove cloud providers blocked while local Ollama permitted. | Cloud provider creation rejected with HTTP 409 `AIR_GAP_EGRESS_DENIED`; cloud probe returns `AIR_GAP_EGRESS_DENIED`; local Ollama probe returns HTTP 200 OK. | **PASS** |
| **Multi-Harness :validate** | Test `:validate` endpoint across `in_app_sdk`, `cli_pipe`, and `remote_runner`. | `POST /api/v1/admin/agent-definitions/{id}:validate` returns HTTP 200 OK `valid: true` with complete 4-section reports. | **PASS** |
| **Sparkle & Sticky Synthesis** | Test Sparkle FIM completion and Sticky-to-Doc promotion preview. | Sparkle FIM streams SSE chunks cleanly (HTTP 200 OK); Sticky promote preview returns structured markdown document proposal (`Incident Response Spec`, HTTP 200 OK). | **PASS** |
| **Cross-Project FORCE RLS** | Verify tenant isolation under PostgreSQL `FORCE ROW LEVEL SECURITY`. | Project Alpha admin attempting to modify Project Beta agent definition returns HTTP 404 `NOT_FOUND`. | **PASS** |
| **Onboarding & /llms.txt** | Verify `/llms.txt` retrieval and preference persistence. | `GET /llms.txt` returns 3,941 bytes; `PATCH /api/v1/users/me/preferences` persists `qa_rigor: strict_forensic` (HTTP 200 OK). | **PASS** |
| **Non-Root Runner Enrollment** | Mint single-use token; enroll non-root daemon with strict POSIX permissions. | Token minted (HTTP 201 Created); `kanban-agent-runner enroll` exit code 0; state dir `0o700`, keys `0o600`, cert `0o644`. | **PASS** |
| **Token Replay Rejection** | Replay consumed single-use enrollment token. | Replayed token rejected with HTTP 401 `ENROLLMENT_TOKEN_INVALID`. | **PASS** |
| **In-Flight CLI Bug Fix** | Fix premature key serialization in `agent/remote_runner/cli.py`. | Key write deferred until server responds HTTP 201 Created, preventing private key clobbering on replay failures. | **PASS** |
| **mTLS PoP WebSocket Handshake** | Live challenge-response handshake over WebSocket. | Client signs `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256}`; server verifies and responds with `hello_ack`. | **PASS** |
| **Cert Revocation & Ejection** | Revoke runner certificate; prove immediate WebSocket reconnect rejection. | Revoked via `POST /api/v1/admin/agent-runners/{id}:revoke` (HTTP 200 OK); reconnect rejected with HTTP 403 Forbidden. | **PASS** |

---

## 2. In-Flight Bug Fixes & Code Changes

### `agent/remote_runner/cli.py` (Premature Private Key Write Bug Fix)
- **Problem:** `enroll_runner` previously generated a new EC private key and serialized it to `client.key` on disk *before* submitting the CSR to the server. If the server rejected enrollment (e.g. 401 replayed token or CSR failure), any existing private key on disk was permanently clobbered with an un-enrolled key, corrupting local daemon state.
- **Fix:** Moved directory creation and `_write_secure_file(key_path, key_pem, mode=0o600)` to execute strictly after checking `resp.status_code == _HTTP_CREATED`.

### Dark-Mode Theme Contrast & Mobile Pill Nowrap
- **Fix:** Added `--border-color: #374151; --text-primary: #f9fafb; --text-secondary: #d1d5db;` inside `theme.css` under `@media (prefers-color-scheme: dark) { :root:not([data-theme='light']) { ... } }`, plus matching dark styles in `StudioDocLink.css`, `aiStudio.css`, `agentStudio.css`, `runnerStudio.css`. Ensured web dist rebuild occurred prior to screenshot capture. Verified priority pill `#1 (Priority 10)` renders on 1 single line in `slice2-ai-studio-390x844-mobile-portrait.png`.

### Sparkle Provider Routing & Budget Cap Halting (`agent/sparkle/pipeline.py`)
- **Fix:** Wired `ProviderRouter` and route candidate pointing to companion `127.0.0.1:11435`. Resolved candidate provider configuration ID against DB by (1) config ID, (2) candidate provider kind (`ollama`, `openai`, `gemini`), and (3) highest-priority enabled provider in DB. Wrapped Step 4 in fail-closed error handling returning `status: "budget"` on unexpected DB exceptions. Added 18 unit tests in `agent/tests/test_sparkle_pipeline.py` achieving 97% coverage on `agent/sparkle/pipeline.py`. Live `POST /api/v1/sparkle/complete` streams real `event: completion` + `event: done` (`status: "ok"`). Verified Sparkle completion under `token_cap=0` and exhausted monthly cap (`tokens_used >= token_cap`) halts cleanly with `event: done` `status: "budget"` and no completion chunks in `workout-transcript.txt`.

### Scrubber Hardening & Verbatim Report Parity
- **Fix:** Added `rnr_enroll` (`kb_rnr_enroll_*`) to `_RE_KANBAN_KEY` in `kanban/security/scrubber.py`. Redacted CSRF tokens, `sk-*`, and `AIza*` in workout runner transcript. Copied 100% verbatim HTTP blocks into `03-live-workout-report.md`. Clean container & port teardown verified (`docker ps -a` shows 0 containers).

---

## 3. Automated Test Verification & Static Quality Gates

1. **Backend Unit Tests (Pytest):**
   - Command: `KB_TEST_PGHOST=/tmp/kb-pgsock-kan413 PYTHONPATH=. uv run coverage run -m pytest kanban/tests/api/admin/test_ai_providers_api.py kanban/tests/ai_config/test_net_guard.py kanban/tests/agents/test_agent_definitions_api.py kanban/tests/api/test_llms_txt.py agent/tests/test_remote_runner.py kanban/tests/security/test_scrubber.py agent/tests/test_sparkle_pipeline.py agent/tests/sparkle/test_pipeline.py -v`
   - Result: **105 passed in 37.69s**, 0 warnings, **97% overall coverage** across touched modules (`agent/remote_runner/cli.py` 96%, `agent/sparkle/pipeline.py` 97%, `kanban/agents/service.py` 97%, `kanban/ops/llms_txt.py` 100%, `kanban/security/scrubber.py` 95%).
   - Verbatim scrubbed logs: `docs/qa/KAN-413/unit-test-results.txt`.

2. **Frontend Unit Tests (Vitest):**
   - Command: `(cd kanban/web && COVERAGE_INCLUDE="src/features/admin-ai/**,src/features/admin-agents/**,src/features/admin-runners/**" npx vitest run src/features/admin-ai/__tests__/AiStudioPage.test.tsx src/features/admin-ai/__tests__/AiProviderEditorDrawer.test.tsx src/features/admin-ai/__tests__/aiAdminApi.test.ts src/features/admin-agents/__tests__/AgentStudioPage.test.tsx src/features/admin-agents/__tests__/AgentDefinitionEditorDrawer.test.tsx src/features/admin-runners/__tests__/RunnerStudioPage.test.tsx --coverage --coverage.thresholds.branches=95)`
   - Result: **165 passed across 6 test files in 4.55s**, 0 `act(...)` warnings, **96.60% branch coverage** with complete V8 branch coverage table (all files >= 95.48%).
   - Verbatim scrubbed logs: `docs/qa/KAN-413/unit-test-results.txt`.

3. **Static Build Gates:**
   - Ruff lint: `uv run --no-sync ruff check kanban/ agent/` -> **All checks passed!**
   - Mypy typecheck: `uv run --no-sync mypy kanban/ agent/` -> **Success: no issues found in 816 source files**
   - Dash check: `python3 scripts/check_no_dashes.py --all` -> **0 violations**
   - Frontend TypeScript: `pnpm --dir kanban/web typecheck` -> **0 errors**
   - Frontend ESLint: `pnpm --dir kanban/web lint` -> **0 warnings**
   - Frontend Production Build: `pnpm --dir kanban/web build` -> **Built in 1.26s**
   - Verbatim scrubbed logs: `docs/qa/KAN-413/build-check.txt`.

---

## 4. Zero-Mock Screenshot Inventory (22 PNGs Across 5 Viewports)

All 22 screenshots were captured against the real running server (`http://127.0.0.1:18413`) with 0 `page.route` / 0 `mockApi`, saved in both `docs/workouts/slice-2-ai-agents-runners/screenshots/` and `docs/qa/KAN-413/screenshots/`, and visually inspected via `read_file`:

1. `slice2-ai-studio-1440x900-light.png`: Desktop AI Providers Studio (Light).
2. `slice2-ai-studio-1440x900-dark.png`: Desktop AI Providers Studio (Dark).
3. `slice2-ai-studio-1024x768-tablet-landscape.png`: Tablet landscape AI Providers Studio.
4. `slice2-ai-studio-768x1024-tablet-portrait.png`: Tablet portrait AI Providers Studio.
5. `slice2-ai-studio-390x844-mobile-portrait.png`: Mobile portrait AI Providers Studio.
6. `slice2-agent-studio-1440x900-light.png`: Desktop Agent Definitions Studio (Light).
7. `slice2-agent-studio-1440x900-dark.png`: Desktop Agent Definitions Studio (Dark).
8. `slice2-agent-studio-1024x768-tablet-landscape.png`: Tablet landscape Agent Studio.
9. `slice2-agent-studio-768x1024-tablet-portrait.png`: Tablet portrait Agent Studio.
10. `slice2-agent-studio-390x844-mobile-portrait.png`: Mobile portrait Agent Studio.
11. `slice2-runner-studio-1440x900-light.png`: Desktop Remote Runners Studio (Light).
12. `slice2-runner-studio-1440x900-dark.png`: Desktop Remote Runners Studio (Dark).
13. `slice2-runner-studio-1024x768-tablet-landscape.png`: Tablet landscape Remote Runners Studio.
14. `slice2-runner-studio-768x1024-tablet-portrait.png`: Tablet portrait Remote Runners Studio.
15. `slice2-runner-studio-390x844-mobile-portrait.png`: Mobile portrait Remote Runners Studio.
16. `slice2-onboarding-1440x900-light.png`: Agent Onboarding Prompt card (Light).
17. `slice2-onboarding-1440x900-dark.png`: Agent Onboarding Prompt card (Dark).
18. `slice2-ai-provider-drawer-create.png`: Register Provider drawer (0 password inputs).
19. `slice2-ai-budget-modal-unlimited.png`: Token Budget modal in Unlimited mode.
20. `slice2-ai-budget-modal-freeze.png`: Token Budget modal with Hard AI Freeze.
21. `slice2-agent-validation-modal-trace.png`: Agent validation modal (4-section trace).
22. `slice2-runner-mint-token-modal.png`: Mint runner token modal with CLI snippet.

---

## 5. Specialist Review Certifications

1. **API Specialist Review (`docs/qa/KAN-413/api-specialist-review.md`)**:
   - Status: **APPROVED**
   - Reviewer: `@api-spec`
   - Verified live provider creation, model probing, atomic failover stack reordering, 0 password inputs, monthly token budget freeze and unlimited modes, air-gap wall enforcement, multi-harness agent validation, RLS tenant isolation, non-root runner enrollment, POSIX permissions, token replay rejection, mTLS PoP challenge handshake, and certificate revocation.

2. **UI Specialist Review (`docs/qa/KAN-413/ui-specialist-review.md`)**:
   - Status: **APPROVED**
   - Reviewer: `@ui-spec`
   - Verified all 22 zero-mock screenshots across 5 viewports, responsive reflow, WCAG 2.2 AA contrast ratios (> 7.5:1 in dark mode, > 4.5:1 in light mode), unclipped modals, and zero Unicode dashes.

---

## 6. Phase 3 Handoff Status

- **Epic Comment (`KAN-410`)**: Posted `## Phase 3 Handoff Packet: slice-2-ai-agents-runners (P3 -> P4)` via `ServerName: "kanban"` `add_comment` (comment id `KAN-410#c-01a21537`).
- **Downstream Documentation Ticket (`KAN-414`)**: Posted `## Phase 3 Handoff Packet: slice-2-ai-agents-runners (P3 -> P4)` via `ServerName: "kanban"` `add_comment` (comment id `KAN-414#c-01a21537`).
- **Ticket Lifecycle Policy**: In strict compliance with instructions, `complete_work` was NOT called, and no tickets were closed or transitioned to Done.
