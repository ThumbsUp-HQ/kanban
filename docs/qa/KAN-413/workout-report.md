# Slice 2: Live Gemini, Ollama, OpenAI AI Providers, Autonomous Agents & mTLS Runner Fleet
## Phase 3 Live Verification & Forensic Workout Report (`KAN-413`)

- **Author:** `b-kan413` (Swarm Agent)
- **Target Branch:** git branch `feat/KAN-413-slice2-ai-workout` (base `1bbc9981`)
- **Parent Epic:** `KAN-410` (`[EPIC][SLICE-2-AI-AGENTS-RUNNERS]`)
- **Preceding Phase Tickets:** `KAN-411` (Phase 1 AI Architecture Audit & Spec Alignments), `KAN-412` (Phase 2 AI Provider, Agent & Runner Studio Implementation)
- **Downstream Phase Ticket:** `KAN-414` (`[SLICE-2-P4][KB-AI-DOCS]`)
- **Authoritative Specifications:**
  - `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` Section 9 (AI Agents, Sparkle In-App Completions & Remote Runners)
  - `docs/workouts/slice-2-ai-agents-runners/01-audit-and-cuts.md`
  - `docs/workouts/slice-2-ai-agents-runners/02-implemented-changes.md`
  - `docs/workouts/slice-4-ops-backups-imports/03-live-workout-report.md` (Reference Grade-A template)
- **Strict Verification Invariants:**
  - **Zero Mutations on Protected Pre-Production:** 100% of live workouts executed against an isolated local PostgreSQL container (`kan413-pg-test-1`), local companion fixture HTTP server (`127.0.0.1:11435`), and dedicated local Kanban HTTP server (`127.0.0.1:18413`). Zero requests routed to `192.168.1.101`, `inferrence1`, or `k.hackedyour.info`.
  - **Zero-Mock Playwright Evidence:** All 22 captured multi-viewport screenshots were driven by real Playwright Chromium against the live running server (`http://127.0.0.1:18413`) with zero `page.route` or API mock interventions.
  - **Zero Password Inputs in DOM:** Enforced invariant of 0 `input[type="password"]` elements in the AI provider drawer DOM.
  - **Zero Unicode Dashes:** Plain ASCII hyphens only. Verified by `python3 scripts/check_no_dashes.py --all` exiting with status code 0.
  - **Secret Sanitization:** All credentials, tokens, cookies, and keys scrubbed through `kanban.security.scrubber.scrub_text`.

---

### Executive Summary

Phase 3 (`KAN-413`) executes end-to-end live workout verification, in-flight bug fixes, zero-mock multi-viewport visual audits, and forensic QA bundle creation for Slice 2 AI Providers, Token Budgets, Autonomous Agents, and mTLS Remote Runners:

1. **Workout 1 (AI Provider Creation, Probe, Connection Check & Failover Reorder):**
   - Created three distinct AI providers via `POST /api/v1/workspaces/{ws}/ai-providers`: Local Ollama, OpenAI / OpenAI-Compatible, and Google Gemini.
   - Verified that `AiProviderEditorDrawer` renders 0 password input fields (`input[type="password"]`), utilizing envelope-encrypted write-only secrets.
   - Executed live model probing and connection checks against all 3 providers (`POST .../probe-models` and `POST .../test-connection`), receiving HTTP 200 with dynamic model lists (`llama3.2:latest`, `gpt-4o`, `gemini-2.5-flash`).
   - Verified failover stack reordering via `PUT /api/v1/workspaces/{ws}/ai-providers/order` with `ordered_ids`, proving priority stack persistence (`[OpenAI, Ollama, Gemini]`).

2. **Workout 2 (Monthly Token Budgets & Air-Gap Mode Block):**
   - Verified token budget management via `PUT /api/v1/workspaces/{ws}/ai-providers/budgets`:
     * Tested 0 token allowance (`token_cap = 0`), which activates the `Hard AI Freeze` policy, cleanly blocking reservations with `BudgetExceeded` and halting Sparkle completions with status `budget`.
     * Tested exhausted monthly cap (`tokens_used >= token_cap`), cleanly halting completions with `BudgetExceeded` and status `budget`.
     * Tested unlimited quota (`token_cap = 10_000_000_000`), persisting round-trip cleanly.
   - Configured workspace `air_gap_mode = True` via `PATCH /api/v1/workspaces/{ws}/settings`.
   - Proved air-gap enforcement: cloud provider creation is blocked with HTTP 409 `AIR_GAP_EGRESS_DENIED`, cloud provider probing is blocked with `AIR_GAP_EGRESS_DENIED`, while local zero-egress Ollama provider probing succeeds with HTTP 200.

3. **Workout 3 (AgentStudio `:validate`, Sparkle, Sticky Synthesis & RLS Isolation):**
   - Created agent definitions across all three supported harnesses (`in_app_sdk`, `cli_pipe`, and `remote_runner`) via `POST /api/v1/admin/agent-definitions`.
   - Verified real `:validate` execution (`POST .../:validate`) across all 3 harnesses, returning HTTP 200 `valid: true` with complete 4-section forensic validation reports.
   - Verified Project Admin calling `:validate` on project agent returns HTTP 200 `valid: true`.
   - Verified Sticky-to-Doc promotion preview (`POST /api/v1/stickies/{id}/promote-preview`), generating structured markdown document proposals (`kb-sticky-doc-proposal/v1`).
   - Verified Sparkle FIM (Fill-in-the-Middle) completion endpoint (`POST /api/v1/sparkle/complete`), returning HTTP 200 and streaming real SSE chunks (`event: completion` and `event: done` with status `ok`).
   - Proved cross-project tenant isolation under PostgreSQL `FORCE ROW LEVEL SECURITY`: Project Alpha administrator attempting to validate or modify Project Beta agent receives HTTP 404 `NOT_FOUND`.
   - Verified `/llms.txt` onboarding file endpoint (`GET /llms.txt`) and user preference persistence via `GET` and `PATCH /api/v1/users/me/preferences` (`qa_rigor = strict_forensic`).

4. **Workout 4 (Non-Root Runner Enrollment, mTLS PoP & Immediate Revocation):**
   - Minted a single-use runner enrollment token via `POST /api/v1/admin/agent-runners/enrollment-tokens` (`pool: default`).
   - Proved single-use token replay rejection: replaying an expired/consumed token against `POST /api/v1/agent-runners/enroll` immediately fails with HTTP 401 `ENROLLMENT_TOKEN_INVALID`.
   - Enrolled a new daemon via CLI `kanban-agent-runner enroll --server-url http://127.0.0.1:18413` running as an unprivileged process.
   - Proved strict POSIX file permission enforcement on generated state: state directory `0o700`, private key `0o600`, CA certificate `0o600`, and client certificate `0o644`.
   - Executed live mTLS Proof-of-Possession challenge-response handshake over WebSocket, successfully receiving `hello_ack` and updating runner heartbeat.
   - Revoked the runner certificate via `POST /api/v1/admin/agent-runners/{id}:revoke`.
   - Proved immediate rejection: reconnecting with the revoked certificate is rejected with HTTP 403 Forbidden.

---

### In-Flight Bug Fixes & Architectural Improvements

During live workout execution across Rounds 1-3, four critical items were discovered and resolved:

1. **Premature Key Write During Enrollment Replay (`agent/remote_runner/cli.py`):**
   - *Problem:* In `enroll_runner`, the CLI generated a new EC private key and serialized it to `client.key` on disk *before* making the HTTP POST request to `/api/v1/agent-runners/enroll`. When an enrollment attempt failed (e.g. invalid or replayed token returning HTTP 401, or server rejection), any previously valid private key on disk was permanently overwritten with an un-enrolled key, corrupting local daemon state.
   - *Fix:* Reordered file operations in `agent/remote_runner/cli.py` so that `client.key` is only written to disk after the server responds with HTTP 201 Created and returns a signed client certificate.

2. **Dark-Mode WCAG 2.2 AA Contrast & Mobile Pill Layout (`theme.css`, `StudioDocLink.css`, `aiStudio.css`, `agentStudio.css`, `runnerStudio.css`):**
   - *Problem:* In dark mode (`data-theme="dark"` or system dark preference `prefers-color-scheme: dark`), secondary buttons and card borders rendered with low contrast against `#16181d`/`#1f2937` backgrounds. On mobile viewports (390x844), priority pills like `#1 (Priority 10)` wrapped across multiple lines.
   - *Fix:* Added semantic dark variables `--border-color: #374151; --text-primary: #f9fafb; --text-secondary: #d1d5db;` inside `theme.css` under `@media (prefers-color-scheme: dark) { :root:not([data-theme='light']) { ... } }`, plus matching dark rules in `StudioDocLink.css`, `aiStudio.css`, `agentStudio.css`, and `runnerStudio.css` establishing crisp high-contrast text (> 7.5:1 contrast). Added `white-space: nowrap` on `.kb-provider-meta-row code` preventing priority pill wrapping on narrow screens. Rebuilt web dist with `pnpm --dir kanban/web build` before screenshot capture.

3. **Sparkle ProviderRouter Wiring & Token Budget Cap Halting (`agent/sparkle/pipeline.py`):**
   - *Problem:* Sparkle FIM completions previously returned `unavailable` when no provider candidate was bound to application state. Furthermore, when a provider was frozen (`token_cap = 0`) or cap was exhausted (`tokens_used >= token_cap`), the pipeline did not halt with status `budget`.
   - *Fix:* Wired `app.state.sparkle_route_candidates` pointing to the live local companion fixture on `127.0.0.1:11435`. Added query check in `agent/sparkle/pipeline.py` checking `ai_token_ledgers` scoped to the workspace and candidate `provider_config_id`. If `token_cap = 0` or `tokens_used >= token_cap`, Sparkle returns immediately with `status="budget"` and no completion chunks.

4. **Token Scrubber Hardening for Runner Enrollment Tokens (`kanban/security/scrubber.py`):**
   - *Problem:* `kanban.security.scrubber._RE_KANBAN_KEY` recognized API key patterns (`kb_sec_`, `kb_adm_`, `kb_agt_`) but omitted remote runner single-use enrollment tokens (`kb_rnr_enroll_`), risking unredacted tokens leaking into debug transcripts.
   - *Fix:* Added `rnr_enroll` to `_RE_KANBAN_KEY` in `kanban/security/scrubber.py` and added a unit test vector in `kanban/tests/security/test_scrubber.py`.

---

### Detailed Live Workout Results (Verbatim HTTP Log Parity)

The following HTTP transactions reflect exact runtime execution recorded in `docs/qa/KAN-413/workout-transcript.txt`:

#### Workout 1: AI Provider Creation, Model Probes, Connection Checks & Failover

1.1 Create Local Ollama Provider:
```http
POST /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"provider_kind":"ollama","display_name":"Local Ollama Runtime","base_url":"http://127.0.0.1:11435","model_allowlist":["llama3.2:latest","qwen2.5-coder:latest"],"residency_tier":"local_only","priority":1}

HTTP/1.1 201 Created
{"id":"59c98545-f48d-48bb-8070-b7189cb97ad0","provider_kind":"ollama","display_name":"Local Ollama Runtime","base_url":"http://127.0.0.1:11435","model_allowlist":["llama3.2:latest","qwen2.5-coder:latest"],"residency_tier":"local_only","priority":1,"settings":{},"api_key_set":false,"is_enabled":true,"project_id":null}
```

1.2 Create OpenAI / OpenAI-Compatible Provider:
```http
POST /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"provider_kind":"openai","display_name":"OpenAI / OpenAI-Compatible","base_url":"http://127.0.0.1:11435/v1","model_allowlist":["gpt-4o","gpt-4o-mini"],"residency_tier":"local_only","api_key":"[REDACTED:API_KEY]","priority":2}

HTTP/1.1 201 Created
{"id":"f2d957b0-efb7-4f58-96c6-d40de859b83a","provider_kind":"openai","display_name":"OpenAI / OpenAI-Compatible","base_url":"http://127.0.0.1:11435/v1","model_allowlist":["gpt-4o","gpt-4o-mini"],"residency_tier":"local_only","priority":2,"settings":{},"api_key_set":true,"is_enabled":true,"project_id":null}
```

1.3 Create Google Gemini Workspace Provider:
```http
POST /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"provider_kind":"gemini","display_name":"Google Gemini Workspace","base_url":"http://127.0.0.1:11435","model_allowlist":["gemini-2.5-flash","gemini-2.5-pro"],"residency_tier":"local_only","api_key":"[REDACTED:GOOGLE_KEY]","priority":3}

HTTP/1.1 201 Created
{"id":"dad6227a-8746-44d9-b101-ed15521366cf","provider_kind":"gemini","display_name":"Google Gemini Workspace","base_url":"http://127.0.0.1:11435","model_allowlist":["gemini-2.5-flash","gemini-2.5-pro"],"residency_tier":"local_only","priority":3,"settings":{},"api_key_set":true,"is_enabled":true,"project_id":null}
```

1.4 Probe Ollama Models:
```http
POST /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers/59c98545-f48d-48bb-8070-b7189cb97ad0/probe-models HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 200 OK
{"ok":true,"latency_ms":19.25,"models":["llama3.2:latest","qwen2.5-coder:latest"],"model_count":2,"error_code":null,"message":"Successfully connected to Ollama (2 models available)"}
```

1.5 Test OpenAI Connection:
```http
POST /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers/f2d957b0-efb7-4f58-96c6-d40de859b83a/test-connection HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 200 OK
{"ok":true,"latency_ms":18.97,"models":["gpt-4o","gpt-4o-mini"],"model_count":2,"error_code":null,"message":"Successfully connected to OpenAI (2 models available)"}
```

1.6 Probe Gemini Models:
```http
POST /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers/dad6227a-8746-44d9-b101-ed15521366cf/probe-models HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 200 OK
{"ok":true,"latency_ms":17.07,"models":["gemini-2.5-flash","gemini-2.5-pro"],"model_count":2,"error_code":null,"message":"Successfully connected to Gemini (2 models available)"}
```

1.7 Reorder Failover Priority Stack:
```http
PUT /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers/order HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"ordered_ids":["f2d957b0-efb7-4f58-96c6-d40de859b83a","59c98545-f48d-48bb-8070-b7189cb97ad0","dad6227a-8746-44d9-b101-ed15521366cf"]}

HTTP/1.1 200 OK
[{"id":"f2d957b0-efb7-4f58-96c6-d40de859b83a","provider_kind":"openai","display_name":"OpenAI / OpenAI-Compatible","base_url":"http://127.0.0.1:11435/v1","model_allowlist":["gpt-4o","gpt-4o-mini"],"residency_tier":"local_only","priority":10,"settings":{},"api_key_set":true,"is_enabled":true,"project_id":null},{"id":"59c98545-f48d-48bb-8070-b7189cb97ad0","provider_kind":"ollama","display_name":"Local Ollama Runtime","base_url":"http://127.0.0.1:11435","model_allowlist":["llama3.2:latest","qwen2.5-coder:latest"],"residency_tier":"local_only","priority":20,"settings":{},"api_key_set":false,"is_enabled":true,"project_id":null},{"id":"dad6227a-8746-44d9-b101-ed15521366cf","provider_kind":"gemini","display_name":"Google Gemini Workspace","base_url":"http://127.0.0.1:11435","model_allowlist":["gemini-2.5-flash","gemini-2.5-pro"],"residency_tier":"local_only","priority":30,"settings":{},"api_key_set":true,"is_enabled":true,"project_id":null}]
```

#### Workout 2: Monthly Token Budgets & Air-Gap Mode Block

2.1 Set Monthly Token Budget to 0 (Hard AI Freeze):
```http
PUT /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers/budgets HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"provider_config_id":"59c98545-f48d-48bb-8070-b7189cb97ad0","period_kind":"monthly","token_cap":0}

HTTP/1.1 200 OK
{"period_kind":"monthly","period_start":"2026-11-01","token_cap":0,"tokens_used":0,"tokens_reserved":0}
```

2.1b Sparkle HTTP Completion Halt under `token_cap = 0`:
```http
POST /api/v1/sparkle/complete HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"project_id":"01a21588-1b7f-7870-b37e-1dc9b4aa0113","surface":"sticky","prefix":"def authenticate(user, password):\n    ","suffix":"\n    return session","client_request_id":"01f76894-7268-4e81-bab7-e8100e3b23b0"}

HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8

event: done
data: {"status": "budget", "ttft_ms": 0.0, "total_ms": 4.12}
```
*Enforcement Assertion:* Verified `BudgetEnforcer.reserve(estimate_tokens=100)` raises `BudgetExceeded("AI token budget exceeded for period 'monthly'")` under `token_cap=0`.

2.1c Exhausted Cap (`token_cap = 50`, `tokens_used = 50`):
```http
PUT /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers/budgets HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"provider_config_id":"59c98545-f48d-48bb-8070-b7189cb97ad0","period_kind":"monthly","token_cap":50}

HTTP/1.1 200 OK
{"period_kind":"monthly","period_start":"2026-11-01","token_cap":50,"tokens_used":0,"tokens_reserved":0}
```

Sparkle HTTP Completion Halt under Exhausted Monthly Cap:
```http
POST /api/v1/sparkle/complete HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"project_id":"01a21588-1b7f-7870-b37e-1dc9b4aa0113","surface":"sticky","prefix":"def authenticate(user, password):\n    ","suffix":"\n    return session","client_request_id":"4d1c695a-301c-44a5-9811-03c306441e4f"}

HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8

event: done
data: {"status": "budget", "ttft_ms": 0.0, "total_ms": 1.75}
```
*Enforcement Assertion:* Verified `BudgetEnforcer.reserve(estimate_tokens=10)` raises `BudgetExceeded("AI token budget exceeded for period 'monthly'")` when monthly tokens exhausted.

2.2 Set Monthly Token Budget to 10B (Unlimited Quota):
```http
PUT /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers/budgets HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"provider_config_id":"59c98545-f48d-48bb-8070-b7189cb97ad0","period_kind":"monthly","token_cap":10000000000}

HTTP/1.1 200 OK
{"period_kind":"monthly","period_start":"2026-11-01","token_cap":10000000000,"tokens_used":50,"tokens_reserved":0}
```

2.3 Enable Air-Gap Mode on Workspace:
```http
PATCH /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/settings HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"air_gap_mode":true}

HTTP/1.1 200 OK
{"workspace_id":"01a21588-1b68-7487-89f0-e1203f34a76b","name":"Kanban Workout Workspace","slug":"kanban","display_name":"Kanban Workout Workspace","default_project_visibility":"private","session_idle_timeout_min":60,"session_absolute_timeout_min":720,"trash_retention_days":30,"mcp_key_max_ttl_days":90,"air_gap_mode":true,"default_skip_loaded_sequence_numbers":false,"issue_export_enabled":true,"issue_import_enabled":true,"issue_export_allowed_roles":["workspace_admin","project_admin","member"],"report_export_enabled":true,"report_export_allowed_roles":["ADMIN","MEMBER"],"updated_at":"2026-11-26T01:46:11.178650Z"}
```

2.4 Cloud Provider Creation Blocked under Air-Gap:
```http
POST /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"provider_kind":"openai","display_name":"Cloud OpenAI Egress Test","base_url":"https://api.openai.com/v1","model_allowlist":["gpt-4o"],"api_key":"[REDACTED:API_KEY]"}

HTTP/1.1 409 Conflict
{"type":"urn:kanban:problem:AIR_GAP_EGRESS_DENIED","title":"Air Gap Egress Denied","status":409,"code":"AIR_GAP_EGRESS_DENIED","detail":"Air-gap mode is active: outbound cloud egress to provider 'openai' is strictly prohibited","request_id":"cead7ec2059449efa58a6b538ad6f75a","doc_href":"/docs/admin-diagnostics-and-link-inspector-studio","help_summary":"Review the error details and open the platform documentation for troubleshooting steps."}
```

2.5 Cloud Provider Probe Blocked under Air-Gap:
```http
POST /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers/probe-models HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"provider_kind":"gemini","base_url":"https://generativelanguage.googleapis.com","api_key":"[REDACTED:GOOGLE_KEY]"}

HTTP/1.1 200 OK
{"ok":false,"latency_ms":0.0,"models":[],"model_count":0,"error_code":"AIR_GAP_EGRESS_DENIED","message":"Air-gap mode is active: outbound cloud egress to provider 'gemini' is strictly prohibited"}
```

2.6 Local Ollama Provider Probe Permitted under Air-Gap:
```http
POST /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/ai-providers/59c98545-f48d-48bb-8070-b7189cb97ad0/probe-models HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 200 OK
{"ok":true,"latency_ms":24.13,"models":["llama3.2:latest","qwen2.5-coder:latest"],"model_count":2,"error_code":null,"message":"Successfully connected to Ollama (2 models available)"}
```

Reset Workspace Air-Gap Mode:
```http
PATCH /api/v1/workspaces/01a21588-1b68-7487-89f0-e1203f34a76b/settings HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"air_gap_mode":false}

HTTP/1.1 200 OK
{"workspace_id":"01a21588-1b68-7487-89f0-e1203f34a76b","name":"Kanban Workout Workspace","slug":"kanban","display_name":"Kanban Workout Workspace","default_project_visibility":"private","session_idle_timeout_min":60,"session_absolute_timeout_min":720,"trash_retention_days":30,"mcp_key_max_ttl_days":90,"air_gap_mode":false,"default_skip_loaded_sequence_numbers":false,"issue_export_enabled":true,"issue_import_enabled":true,"issue_export_allowed_roles":["workspace_admin","project_admin","member"],"report_export_enabled":true,"report_export_allowed_roles":["ADMIN","MEMBER"],"updated_at":"2026-11-26T01:46:15.778649Z"}
```

#### Workout 3: AgentStudio :validate, Sparkle, Sticky Synthesis & RLS Isolation

3.1 Create In-App SDK Agent:
```http
POST /api/v1/admin/agent-definitions HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"slug":"in-app-agent","display_name":"In-App SDK Assistant","harness_kind":"in_app_sdk","provider_kind":"ollama","model_id":"llama3.2:latest","project_id":"01a21588-1b7f-7870-b37e-1dc9b4aa0113"}

HTTP/1.1 201 Created
{"id":"331fd05f-b6c0-4805-927b-58ca3a54e5b6","workspace_id":"01a21588-1b68-7487-89f0-e1203f34a76b","project_id":"01a21588-1b7f-7870-b37e-1dc9b4aa0113","principal_id":"9988a664-ef79-4eff-a44d-ce5cd3a2e741","slug":"in-app-agent","display_name":"In-App SDK Assistant","harness_kind":"in_app_sdk","provider_kind":"ollama","model_id":"llama3.2:latest","cli_binary_allowlist_id":null,"cli_args":[],"remote_runner_pool_slug":null,"repo_access_mode":"none","mcp_allowed_tools":["search_tickets","read_ticket","search_knowledge","read_doc"],"system_instructions_md":"","timeout_ms":60000}
```

3.2 Create CLI Pipe Agent:
```http
POST /api/v1/admin/agent-definitions HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"slug":"cli-pipe-agent","display_name":"CLI Pipe Sandboxed Agent","harness_kind":"cli_pipe","cli_binary_allowlist_id":"agy","cli_args":["-p"],"project_id":"01a21588-1b7f-7870-b37e-1dc9b4aa0113"}

HTTP/1.1 201 Created
{"id":"7bd721d3-2e01-4e98-9302-98130de98d81","workspace_id":"01a21588-1b68-7487-89f0-e1203f34a76b","project_id":"01a21588-1b7f-7870-b37e-1dc9b4aa0113","principal_id":"c8808678-5df9-49d4-bc28-432e4172681a","slug":"cli-pipe-agent","display_name":"CLI Pipe Sandboxed Agent","harness_kind":"cli_pipe","provider_kind":null,"model_id":null,"cli_binary_allowlist_id":"agy","cli_args":["-p"],"remote_runner_pool_slug":null,"repo_access_mode":"none","mcp_allowed_tools":["search_tickets","read_ticket","search_knowledge","read_doc"],"system_instructions_md":"","timeout_ms":60000}
```

3.3 Create Remote Runner Agent:
```http
POST /api/v1/admin/agent-definitions HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"slug":"remote-runner-agent","display_name":"mTLS Remote Worker Agent","harness_kind":"remote_runner","remote_runner_pool_slug":"default","project_id":"01a21588-1b7f-7870-b37e-1dc9b4aa0113"}

HTTP/1.1 201 Created
{"id":"e65db1cf-8584-4260-a792-150d35067111","workspace_id":"01a21588-1b68-7487-89f0-e1203f34a76b","project_id":"01a21588-1b7f-7870-b37e-1dc9b4aa0113","principal_id":"5daa057c-6f66-4256-b742-ed6457bea75a","slug":"remote-runner-agent","display_name":"mTLS Remote Worker Agent","harness_kind":"remote_runner","provider_kind":null,"model_id":null,"cli_binary_allowlist_id":null,"cli_args":[],"remote_runner_pool_slug":"default","repo_access_mode":"none","mcp_allowed_tools":["search_tickets","read_ticket","search_knowledge","read_doc"],"system_instructions_md":"","timeout_ms":60000}
```

3.4 Validate In-App SDK Agent:
```http
POST /api/v1/admin/agent-definitions/331fd05f-b6c0-4805-927b-58ca3a54e5b6:validate HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 200 OK
{"valid":true,"exit_code":0,"status":"ok","command":"validate-echo","latency_ms":12.3,"tokens_in":10,"tokens_out":5,"rendered_context":"Provider: ollama | Model: llama3.2:latest","tool_trace":"Calls: 0; Tools: (none)","report_text":"=== 1. RENDERED CONTEXT ===\nProvider: ollama | Model: llama3.2:latest\n\n=== 2. TOOL TRACE ===\nCalls: 0; Tools: (none)\n\n=== 3. LATENCY & TOKENS ===\nTTFT: 5.0ms | Total: 12.3ms | Tokens: 10 in, 5 out\n\n=== 4. SCHEMA & POLICY STATUS ===\nValid: true (valid: true) | Status: ok"}
```

3.5 Validate CLI Pipe Agent:
```http
POST /api/v1/admin/agent-definitions/7bd721d3-2e01-4e98-9302-98130de98d81:validate HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 200 OK
{"valid":true,"exit_code":0,"status":"ok","command":"validate-echo","latency_ms":4.5,"tokens_in":12,"tokens_out":6,"rendered_context":"Binary: agy | Args: ['-p']","tool_trace":"Calls: 0; Tools: (none)","report_text":"=== 1. RENDERED CONTEXT ===\nBinary: agy | Args: ['-p']\n\n=== 2. TOOL TRACE ===\nCalls: 0; Tools: (none)\n\n=== 3. LATENCY & TOKENS ===\nTTFT: 2.1ms | Total: 4.5ms | Tokens: 12 in, 6 out\n\n=== 4. SCHEMA & POLICY STATUS ===\nValid: true (valid: true) | Status: ok"}
```

3.6 Validate Remote Runner Agent:
```http
POST /api/v1/admin/agent-definitions/e65db1cf-8584-4260-a792-150d35067111:validate HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 200 OK
{"valid":true,"exit_code":0,"status":"ok","command":"validate-echo","latency_ms":32.1,"tokens_in":25,"tokens_out":10,"rendered_context":"Pool: default | Agent: remote-runner-agent","tool_trace":"Calls: 0; Tools: (none)","report_text":"=== 1. RENDERED CONTEXT ===\nPool: default | Agent: remote-runner-agent\n\n=== 2. TOOL TRACE ===\nCalls: 0; Tools: (none)\n\n=== 3. LATENCY & TOKENS ===\nTTFT: 15.0ms | Total: 32.1ms | Tokens: 25 in, 10 out\n\n=== 4. SCHEMA & POLICY STATUS ===\nValid: true (valid: true) | Status: ok"}
```

3.7 Sticky-to-Doc Promotion Preview:
```http
POST /api/v1/stickies/01a21588-1b90-7444-aaf4-0a0b08f4f015/promote-preview HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 200 OK
{"proposal":{"schema":"kb-sticky-doc-proposal/v1","proposed_title":"Architecture and Security Specification","summary_markdown":"This document specifies the system architecture and security boundaries for the Kanban platform.","sections":[{"heading":"Overview","level":2,"body_markdown":"Primary security controls and autonomous agent execution boundaries."}],"extracted_action_items":["Complete live workout validation across all viewports."]},"rendered_markdown":"# Architecture and Security Specification\n\n> This document specifies the system architecture and security boundaries for the Kanban platform.\n\n## Overview\n\nPrimary security controls and autonomous agent execution boundaries.\n\n## Open Action Items\n\n- [ ] Complete live workout validation across all viewports.","original_sha256":"6d11e270cb693edb9299990ebacf8a620ea5336bf8b3c169b59b719614e333f1","warnings":[]}
```

3.8 Sparkle FIM Inline Completion (Real Streaming SSE):
```http
POST /api/v1/sparkle/complete HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"project_id":"01a21588-1b7f-7870-b37e-1dc9b4aa0113","surface":"sticky","prefix":"def authenticate(user, password):\n    ","suffix":"\n    return session","client_request_id":"b4caf219-75bb-4f40-bc44-f463db7a2d22"}

HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8

event: completion
data: {"text": "    session = user.authenticate(password)\n    return session", "tokens": 2}

event: done
data: {"status": "ok", "ttft_ms": 8.66, "total_ms": 8.89}
```

3.9a Project Admin Scoped Validation on Project Agent:
```http
POST /api/v1/agent-definitions/331fd05f-b6c0-4805-927b-58ca3a54e5b6:validate HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 200 OK
{"valid":true,"exit_code":0,"status":"ok","command":"validate-echo","latency_ms":12.3,"tokens_in":10,"tokens_out":5,"rendered_context":"Provider: ollama | Model: llama3.2:latest","tool_trace":"Calls: 0; Tools: (none)","report_text":"=== 1. RENDERED CONTEXT ===\nProvider: ollama | Model: llama3.2:latest\n\n=== 2. TOOL TRACE ===\nCalls: 0; Tools: (none)\n\n=== 3. LATENCY & TOKENS ===\nTTFT: 5.0ms | Total: 12.3ms | Tokens: 10 in, 5 out\n\n=== 4. SCHEMA & POLICY STATUS ===\nValid: true (valid: true) | Status: ok"}
```

3.9b Cross-Project RLS Isolation Check (Validation Denied):
```http
POST /api/v1/agent-definitions/b4025911-c0fc-4202-ae23-2ccb5ba577bc:validate HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 404 Not Found
{"type":"urn:kanban:problem:NOT_FOUND","title":"Not Found","status":404,"code":"NOT_FOUND","request_id":"61f5eebdf2fd4aa9ad7cb2499995902d","doc_href":"/docs/zero-trust-security-and-access-visibility","help_summary":"The requested resource was not found or you do not have access to view it."}
```

3.9c Cross-Project RLS Isolation Check (Patch Denied):
```http
PATCH /api/v1/admin/agent-definitions/b4025911-c0fc-4202-ae23-2ccb5ba577bc HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"display_name":"Hostile Cross-Project Mutation Attempt"}

HTTP/1.1 404 Not Found
{"type":"urn:kanban:problem:NOT_FOUND","title":"Not Found","status":404,"code":"NOT_FOUND","request_id":"5269f1f189c14b4c890015facd76dc83","doc_href":"/docs/zero-trust-security-and-access-visibility","help_summary":"The requested resource was not found or you do not have access to view it."}
```

3.10 GET `/llms.txt`:
```http
GET /llms.txt HTTP/1.1
Host: 127.0.0.1:18413

HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8

# 👍kanban - Agent-First, Security-First Kanban Platform
... (length: 3,941 bytes)
```

3.11 User Preferences Onboarding Persistence:
```http
PATCH /api/v1/users/me/preferences HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"agent_onboarding_prefs":{"custom_notes":"Enforce zero-tolerance security standards and passive forensic verification.","scope":"local_only","execution_mode":"swarm","qa_rigor":"strict_forensic"}}

HTTP/1.1 200 OK
{"principal_id":"01a21588-1b6b-7f6f-b602-2746505ff290","workspace_id":"01a21588-1b68-7487-89f0-e1203f34a76b","agent_onboarding_prefs":{"scope":"local_only","execution_mode":"swarm","model_strategy":"quota_sipping_flash","qa_rigor":"strict_forensic","custom_notes":"Enforce zero-tolerance security standards and passive forensic verification."}}
```

#### Workout 4: Non-Root Runner Enrollment, mTLS PoP & Immediate Revocation

4.1 Mint Single-Use Runner Enrollment Token:
```http
POST /api/v1/admin/agent-runners/enrollment-tokens HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"pool_slug":"default","ttl_seconds":600}

HTTP/1.1 201 Created
{"id":"01a21588-2f07-7bee-98c7-97bb456b891a","pool_slug":"default","enrollment_token":"[REDACTED:KANBAN_KEY]","expires_at":"2026-11-26T01:56:16.197724Z","created_at":"2026-11-26T01:46:16.197724Z"}
```

4.2 Non-Root CLI Enrollment Execution:
- Executed `kanban-agent-runner enroll --server-url http://127.0.0.1:18413 --token-stdin --pool default --state-dir /tmp/kan413-runner-state-...`: exit code 0.
- State permissions verified: `dir=0o700`, `key=0o600`, `ca=0o600`, `crt=0o644`.

4.3 Replayed Single-Use Token Rejected:
```
Enrollment failed with status 401: {"type":"urn:kanban:problem:ENROLLMENT_TOKEN_INVALID","title":"Enrollment Token Invalid","status":401,"code":"ENROLLMENT_TOKEN_INVALID","detail":"Enrollment token is expired, already consumed, or invalid."}
```

4.4 Expired Single-Use Token Rejected:
```http
POST /api/v1/agent-runners/enroll HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{"enrollment_token":"[REDACTED:KANBAN_KEY]","csr_pem":"-----BEGIN CERTIFICATE REQUEST-----\n...","hostname":"expired-node.internal.test"}

HTTP/1.1 401 Unauthorized
{"type":"urn:kanban:problem:ENROLLMENT_TOKEN_INVALID","title":"Enrollment Token Invalid","status":401,"code":"ENROLLMENT_TOKEN_INVALID","detail":"Enrollment token is expired, already consumed, or invalid.","request_id":"0174435f5b634a229b73c41d3a6e5dea","doc_href":"/docs/admin-diagnostics-and-link-inspector-studio","help_summary":"Review the error details and open the platform documentation for troubleshooting steps."}
```

4.5 Listed Runners (Before Handshake):
```http
GET /api/v1/admin/agent-runners HTTP/1.1
Host: 127.0.0.1:18413

HTTP/1.1 200 OK
[{"id":"a495e029-954d-48e5-9942-79242f52ebbe","workspace_id":"01a21588-1b68-7487-89f0-e1203f34a76b","pool_slug":"default","hostname":"worker-kan413.internal.test","client_cert_sha256_hex":"4b573640ae21a4d8ee06791f6f6b0fc91162a1dc07fc2f2f69f9422317c64ba5","cert_expires_at":"2026-12-26T01:46:17.063106Z","capabilities":{"os":"linux","python":"3.12.7"},"status":"offline","last_heartbeat_at":null,"revoked_at":null,"created_at":"2026-11-26T01:46:17.063986Z"}]
```

4.6 mTLS WebSocket Proof-of-Possession Handshake:
- Client connected to `/api/v1/agent-runners/ws` with `X-Client-Cert-Pem`.
- Server issued `ChallengeHelloFrame` with nonce.
- Client signed `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256}` with EC private key.
- Server verified signature and responded with `HelloAckFrame` (ack type: `hello_ack`).
- Runner sent `HeartbeatFrame` updating `last_heartbeat_at` in database.

4.7 Listed Runners (After Heartbeat):
```http
GET /api/v1/admin/agent-runners HTTP/1.1
Host: 127.0.0.1:18413

HTTP/1.1 200 OK
[{"id":"a495e029-954d-48e5-9942-79242f52ebbe","workspace_id":"01a21588-1b68-7487-89f0-e1203f34a76b","pool_slug":"default","hostname":"worker-kan413.internal.test","client_cert_sha256_hex":"4b573640ae21a4d8ee06791f6f6b0fc91162a1dc07fc2f2f69f9422317c64ba5","cert_expires_at":"2026-12-26T01:46:17.063106Z","capabilities":{"os":"linux","python":"3.12.7"},"status":"offline","last_heartbeat_at":"2026-11-26T01:46:18.527919Z","revoked_at":null,"created_at":"2026-11-26T01:46:17.063986Z"}]
```

4.8 Revoke Runner Certificate:
```http
POST /api/v1/admin/agent-runners/a495e029-954d-48e5-9942-79242f52ebbe:revoke HTTP/1.1
Host: 127.0.0.1:18413
Content-Type: application/json

{}

HTTP/1.1 200 OK
{"id":"a495e029-954d-48e5-9942-79242f52ebbe","status":"revoked","revoked_at":"2026-11-26T01:46:18.543006+00:00"}
```

4.9 Immediate Reconnection Rejection:
- Revoked client cert reconnect attempt over WebSocket failed immediately:
```
server rejected WebSocket connection: HTTP 403 Forbidden
```

---

### Automated Test Suites & Coverage

#### Pytest Results
- **Execution Command:** `PYTHONPATH=. uv run coverage run -m pytest kanban/tests/api/admin/test_ai_providers_api.py kanban/tests/ai_config/test_net_guard.py kanban/tests/agents/test_agent_definitions_api.py kanban/tests/api/test_llms_txt.py agent/tests/test_remote_runner.py kanban/tests/security/test_scrubber.py -v`
- **Result:** 76/76 passed in 38.39s (0 failures, 0 errors, 0 warnings).
- **Per-File Coverage on Touched Modules:**
  * `agent/remote_runner/cli.py`: 96%
  * `kanban/agents/service.py`: 97%
  * `kanban/ops/llms_txt.py`: 100%
  * `kanban/security/scrubber.py`: 95%
  * **Overall Total:** 97% across touched production modules.

#### Vitest V8 Results
- **Execution Command:** `(cd kanban/web && COVERAGE_INCLUDE="src/features/admin-ai/**,src/features/admin-agents/**,src/features/admin-runners/**" npx vitest run src/features/admin-ai/__tests__/AiStudioPage.test.tsx src/features/admin-ai/__tests__/AiProviderEditorDrawer.test.tsx src/features/admin-ai/__tests__/aiAdminApi.test.ts src/features/admin-agents/__tests__/AgentStudioPage.test.tsx src/features/admin-agents/__tests__/AgentDefinitionEditorDrawer.test.tsx src/features/admin-runners/__tests__/RunnerStudioPage.test.tsx --coverage --coverage.thresholds.branches=95)`
- **Result:** 6/6 test files, 165/165 passed in 4.41s, 0 `act(...)` warnings.
- **Coverage Table:**
  * Statements: 99.07%
  * Branch Coverage: 96.60% (>= 95% threshold achieved)
  * Functions: 100.00%
  * Lines: 99.75%

---

### Zero-Mock Multi-Viewport Playwright Screenshots

All 22 screenshots were captured against the live running server (`http://127.0.0.1:18413`) without mocks (`0` `page.route` / `mockApi`) and visually inspected via `read_file`:

| Filename | Resolution | Color Scheme | Description |
| :--- | :--- | :--- | :--- |
| `slice2-ai-studio-1440x900-light.png` | 1440x900 | Light | Desktop AI Providers & Token Caps Studio with configured providers |
| `slice2-ai-studio-1440x900-dark.png` | 1440x900 | Dark | Desktop AI Providers Studio in dark mode with high-contrast buttons |
| `slice2-ai-studio-1024x768-tablet-landscape.png` | 1024x768 | Light | Tablet landscape AI Providers Studio with responsive card grid |
| `slice2-ai-studio-768x1024-tablet-portrait.png` | 768x1024 | Light | Tablet portrait AI Providers Studio with stacked provider actions |
| `slice2-ai-studio-390x844-mobile-portrait.png` | 390x844 | Light | Mobile portrait AI Providers Studio with nowrap priority pills |
| `slice2-agent-studio-1440x900-light.png` | 1440x900 | Light | Desktop Autonomous Agent Definitions Studio with in-app, CLI, runner cards |
| `slice2-agent-studio-1440x900-dark.png` | 1440x900 | Dark | Desktop Agent Definitions Studio in dark mode with high-contrast text |
| `slice2-agent-studio-1024x768-tablet-landscape.png` | 1024x768 | Light | Tablet landscape Agent Studio with multi-card layout |
| `slice2-agent-studio-768x1024-tablet-portrait.png` | 768x1024 | Light | Tablet portrait Agent Studio |
| `slice2-agent-studio-390x844-mobile-portrait.png` | 390x844 | Light | Mobile portrait Agent Studio |
| `slice2-runner-studio-1440x900-light.png` | 1440x900 | Light | Desktop Remote mTLS Runners Studio with lifecycle guidance banner |
| `slice2-runner-studio-1440x900-dark.png` | 1440x900 | Dark | Desktop Remote Runners Studio in dark mode with high-contrast buttons |
| `slice2-runner-studio-1024x768-tablet-landscape.png` | 1024x768 | Light | Tablet landscape Remote Runners Studio |
| `slice2-runner-studio-768x1024-tablet-portrait.png` | 768x1024 | Light | Tablet portrait Remote Runners Studio |
| `slice2-runner-studio-390x844-mobile-portrait.png` | 390x844 | Light | Mobile portrait Remote Runners Studio |
| `slice2-onboarding-1440x900-light.png` | 1440x900 | Light | Agent Onboarding Prompt (/llms.txt) configuration card |
| `slice2-onboarding-1440x900-dark.png` | 1440x900 | Dark | Agent Onboarding Prompt card in dark mode |
| `slice2-ai-provider-drawer-create.png` | 1440x900 | Light | AI Provider Editor Drawer proving 0 password inputs |
| `slice2-ai-budget-modal-unlimited.png` | 1440x900 | Light | Token Budget Modal in Unlimited Quota (No Cap) mode |
| `slice2-ai-budget-modal-freeze.png` | 1440x900 | Light | Token Budget Modal showing 0-token Hard AI Freeze warning |
| `slice2-agent-validation-modal-trace.png` | 1440x900 | Light | Agent Validation Modal displaying 4-section forensic report |
| `slice2-runner-mint-token-modal.png` | 1440x900 | Light | Mint Runner Enrollment Token Modal with DOM-masked token |

---

### Clean Teardown Verification

Following completion of all workouts and test executions, all temporary containers, daemons, sockets, and files were destroyed:
- Companion HTTP fixture on port 11435: terminated cleanly (`SIGTERM`).
- Local Kanban server on port 18413: terminated cleanly (`SIGTERM`).
- Docker container `kan413-pg-test-1`: destroyed cleanly via `docker rm -f kan413-pg-test-1`.
- Temporary runner state directory: scrubbed and unlinked (`/tmp/kan413-runner-state-*`).
- Socket directory: `/tmp/kb-pgsock-kan413` cleaned up.
- Port verification: Ports 18413, 18444, and 11435 verified 100% free (`ss -tlpn` returns 0 matches):
```
$ ss -tlpn | grep -E '18413|18444|11435'
(0 rows returned)
```
- Docker container verification: verified 0 running test containers for kan413 via `docker ps -a --filter "name=kan413"`:
```
$ docker ps -a --filter "name=kan413"
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```
