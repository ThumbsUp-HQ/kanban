# API Specialist Gate Final Audit: APPROVED for KANBA-70 (KB-P5-07)

- Auditor: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-70`
- Branch: `feat/KANBA-70`
- Commit: `c62aa45`
- Ticket: `KANBA-70` (`KB-P5-07`: `[Phase 5 / Agent + API] Sparkle FIM backend: scrub-first, RLS-pinned 18ms retrieval, 1-48 token FIM, output filter, SSE endpoint`)

---

### 1. Executive Summary & Verification Matrix

A comprehensive systems architecture, API transport, and security invariant audit of the Sparkle (`✨`) Fill-In-the-Middle (FIM) backend implementation was conducted in worktree `/tmp/kb-wt-KANBA-70`. The implementation was evaluated against specification sections 9.1, 9.3, 15.2, and 2.4, as well as core security invariants regarding anti-enumeration, RLS least privilege, secret scrubbing, prompt injection defense, timing floors, and unidirectional module layering.

| Verification Dimension | Specification Target | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Pipeline Order & Scrub-First** | S9.3 item 1: secrets scrubbed before socket | Scrub prefix/suffix via `outbound_secret_scrubber` at step 2; zero embedder, DB, or provider calls on secret detection | PASS |
| **Least-Privilege RLS Retrieval** | S9.3 item 2: `app_rls_reader`, 18ms budget | `SET LOCAL ROLE app_rls_reader`, `SET LOCAL TRANSACTION READ ONLY`, `statement_timeout = '18ms'`, context bound from verified principal | PASS |
| **RLS Cross-Tenant Isolation** | S9.3 item 2: no leakage across boundaries | Base tables (`issues`, `docs`, `stickies`, `pages`) evaluated under RLS; canary test `SEC-CANARY-7731` yields 0 matches | PASS |
| **Retrieval Timeout Resiliency** | S9.3 item 2: 18ms timeout graceful fallback | Catches PostgreSQL `QueryCanceled` / `57014`; proceeds with empty snippets and `retrieval_status="timeout"` | PASS |
| **Bounded FIM Generation** | S9.3 item 3: 1-48 tokens, temp 0.15, 115ms TTFT | `max_output_tokens=48`, `temperature=0.15`, `ttft_deadline_ms=115`, overall timeout 130ms; stream `aclose()` on fault | PASS |
| **Output Sanitization & Defense** | S15.2: strip HTML, drop prompt overrides | Removes zero-width/tag plane chars; unescapes entities; drops prompt injections; strips `<...>`; re-scrubs secrets; caps at 400 chars | PASS |
| **SSE Streaming Transport** | Event schema & buffering | `POST /api/v1/sparkle/complete` emits `completion` then `done`; headers `no-store` + `X-Accel-Buffering: no`; disconnect cancels task | PASS |
| **Anti-Enumeration & CSRF** | S3.4: 404 before 403; CSRF double-submit | Enforces `X-CSRF-Token` with `hmac.compare_digest`; authorization failures yield timing-equalized RFC 7807 404 | PASS |
| **Payload Size Protection** | Denial-of-service prevention | Request bodies exceeding 16 KiB rejected with RFC 7807 413 `PAYLOAD_TOO_LARGE` | PASS |
| **Unidirectional Architecture** | Agent -> MCP -> Kanban -> Database | Composition isolated in `agent/asgi.py` (`create_agent_app`); `kanban/` imports zero `agent/` modules; `lint-imports` clean | PASS |
| **Automated Test Coverage** | Mandatory Feature Tests (>=95%) | 43/43 tests passing in 3.48s; 99.08% combined branch+line coverage across target files | PASS |
| **End-to-End Latency SLA** | S9.3: p95 < 150.0ms over 200 iterations | Latency benchmark report confirms p50 = 1.27ms, p95 = 1.73ms, p99 = 2.04ms (budget < 150.0ms) | PASS |
| **Quality & Static Analysis** | Zero-Tolerance Quality Mandate | Mypy strict clean (64 files), Ruff clean, Ruff format clean, zero Unicode dashes, make license 0 violations | PASS |

---

### 2. Forensic Architectural & Security Invariant Audit

#### A. Pipeline Order & Scrub-First Mandate (`agent/sparkle/pipeline.py`)
- **Strict Execution Hierarchy**: `run_sparkle_pipeline` adheres to the mandated 7-step sequence:
  1. Prefix truncated to last 1,500 chars; suffix truncated to first 500 chars.
  2. Both truncated prefix and suffix evaluated through `outbound_secret_scrubber`. If `redacted` is true on either, the pipeline short-circuits immediately, returning `SparkleResult(status="secret_scrubbed")` with `0` tokens, `0.0ms` TTFT, and zero invocations to the embedder, database, or provider.
  3. Last 512 characters of scrubbed prefix embedded via the local in-process embedder.
  4. Context retrieved via `retrieve_context` under `app_rls_reader`.
  5. Streaming FIM dispatched to `ProviderRouter.stream_complete` within a strict `asyncio.timeout(0.130)` ceiling and `ttft_deadline_ms=115`.
  6. Completion buffered and sanitized through `filter_completion`.
  7. Terminal `SparkleResult` returned with telemetry.
- **Provider Stream Cleanup**: On timeout or provider errors, `stream_iter.aclose()` is awaited, ensuring background sockets and streaming resources are destroyed immediately without connection leakage.

#### B. RLS Least-Privilege & Read-Only Retrieval (`agent/sparkle/retrieval.py`)
- **Role & Transaction Constraints**: The dedicated database session executes:
  - `SET LOCAL ROLE app_rls_reader`: Enforces least-privilege role permissions.
  - `SET LOCAL TRANSACTION READ ONLY`: Prevents any mutation side effects.
  - `SET LOCAL statement_timeout = '18ms'`: Hard PostgreSQL engine ceiling.
- **Principal Binding Integrity**: Session configuration variables (`app.principal_id`, `app.workspace_id`, `app.token_scopes`, `app.aal_level`) are bound exclusively from the verified `principal_ctx` parameter, preventing caller spoofing.
- **Base Table RLS Isolation**: Cosine vector distance queries on `object_embeddings` locate candidate chunks within the project, but actual markdown content is retrieved via `SELECT ... FROM issues/docs/stickies/pages WHERE id = :id`. Because base tables enforce row-level security, unreadable cross-tenant or private project objects resolve to empty results.
- **Canary Isolation Proof**: Verified by Case 3 and `docs/qa/KANBA-70/rls-canary-proof.txt`. A sticky containing `SEC-CANARY-7731` in an unreadable project produced zero matches (`grep -c SEC-CANARY-7731 = 0`), proving RLS containment.
- **Timeout Recovery**: Injected `QueryCanceled` or `57014` SQLSTATE errors are caught gracefully, returning empty snippets with `retrieval_status="timeout"`. The pipeline continues without breaking the user typing experience.
- **Prompt Isolation**: Retrieved snippets are capped at 400 characters, re-scrubbed with `outbound_secret_scrubber`, and wrapped inside per-request random delimiters `<<<UNTRUSTED_CONTEXT_<16 hex>>>>`.

#### C. Defense-in-Depth Output Filter (`agent/sparkle/output_filter.py`)
- **Multi-Stage Sanitization**:
  1. Invisible zero-width and unicode tag plane characters (`U+200B..U+200F`, `U+E0000..U+E007F`) stripped.
  2. HTML entities unescaped prior to pattern inspection.
  3. Prompt override / jailbreak patterns evaluated before tag stripping (detects patterns like `ignore previous instructions`, `system:`, `assistant:`, `<|im_start|>`, `[INST]`, `BEGIN SYSTEM PROMPT`, `you are now`). Detection drops the entire completion to `""`.
  4. HTML tags stripped via regex `r"<[^>]*>?"` (verified: `<img src=x onerror=alert(1)> verify` becomes `verify`).
  5. Scanned with `outbound_secret_scrubber`. If an echoed secret or credential is found, the completion is dropped to `""`.
  6. Hard caps enforced: character length <= 400, token count <= 48.

#### D. API Transport, Anti-Enumeration & CSRF (`agent/sparkle/router.py`)
- **Body Size Ceiling**: `raw_body` length checked against `_MAX_BODY_BYTES = 16384` (16 KiB). Overflow immediately raises RFC 7807 413 `PAYLOAD_TOO_LARGE`.
- **Double-Submit CSRF**: `verify_csrf` validates header `X-CSRF-Token` against cookie `__Host-kb_csrf` (or `kb_csrf`) using constant-time `hmac.compare_digest`. Missing or mismatched tokens raise RFC 7807 403 `CSRF_TOKEN_MISSING` / `CSRF_TOKEN_INVALID`.
- **Anti-Enumeration via Timing Floor**: `verify_sparkle_access` executes within `timing_floor()`. Callers require EDIT capability on `object_id` (when supplied) or VIEW capability on `project_id`. Access denials raise RFC 7807 404 `NOT_FOUND` rather than 403, preventing unauthorized resource enumeration.
- **SSE Wire Format**: Emits strictly `event: completion` (only on `ok`, with `text` and `tokens`) followed by `event: done` (with `status`, `ttft_ms`, and `total_ms`). Headers include `Cache-Control: no-store` and `X-Accel-Buffering: no`. Zero internal prompt text, context snippets, or system traces are exposed to the client.
- **Cancellation**: Request disconnect checks (`is_disconnected()`) ensure client typing interruptions immediately cancel the in-flight pipeline task and terminate provider connections.

#### E. Module Architecture & Composition (`agent/asgi.py`)
- **Unidirectional Layering**: Core `kanban/` code does not import `agent/`. Instead, `agent/asgi.py` defines `create_agent_app()` which calls `kanban.app.create_app()` and mounts `sparkle_router`.
- `lint-imports` confirms contracts are kept with 0 broken imports.

---

### 3. Latency & Test Suite Verification

1. **Mandatory Test Cases (43/43 Passing)**:
   - Case 1 (Positive): Cassette `sparkle_fim_ok.yaml` returns `status="ok"` with correct token limits and parameters.
   - Case 2 (Scrub-First): Secret in prefix triggers `status="secret_scrubbed"` with zero DB/embedder/provider calls.
   - Case 3 (RLS Isolation): Unreadable canary sticky yields zero context in provider prompt.
   - Case 4 (Read-Only 18ms): Session verifies `app_rls_reader`, `transaction_read_only = on`, `statement_timeout = 18ms`.
   - Case 5 (Output Defense): HTML stripped, prompt overrides dropped, echoed secrets dropped.
   - Case 6 (Timeout Fault): Retrieval `QueryCanceled` continues with `retrieval_status="timeout"`.
   - Case 7 (Provider Fault): TTFT > 115ms yields `status="timeout"` with stream closed; 429 yields `status="unavailable"`.
   - Case 8 (Boundaries): Overlong tokens capped at 48; body > 16 KiB yields 413; prefix 1,500 chars preserved.
   - Case 9 (Endpoint): Missing CSRF yields 403; unreadable object yields 404; SSE stream strictly formatted.
   - Case 10 (Latency): 200 iterations benchmarked.
2. **Latency Report**:
   - Total iterations: 200
   - Mean latency: 1.34ms
   - p50: 1.27ms
   - p90: 1.57ms
   - p95: 1.73ms (SLA budget: < 150.0ms)
   - p99: 2.04ms
   - SLA compliance: PASS
3. **Branch + Line Coverage**:
   - `agent/asgi.py`: 100%
   - `agent/sparkle/__init__.py`: 100%
   - `agent/sparkle/output_filter.py`: 100%
   - `agent/sparkle/pipeline.py`: 98%
   - `agent/sparkle/retrieval.py`: 100%
   - `agent/sparkle/router.py`: 98%
   - Combined coverage: **99.08%** (exceeds >= 95% threshold).
4. **Typography**: Plain ASCII hyphens `-` only throughout. Zero non-ASCII Unicode dashes (`U+2014`, `U+2013`).

---

### 4. Gate Sign-Off

The Sparkle FIM backend implementation in `/tmp/kb-wt-KANBA-70` fully satisfies all architectural, security, performance, and contract requirements of ticket `KANBA-70` (`KB-P5-07`).

Verdict: APPROVED
