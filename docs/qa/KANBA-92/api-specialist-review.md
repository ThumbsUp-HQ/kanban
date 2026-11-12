# API Specialist Gate Review: KANBA-92 (KB-P3-33)

- **Ticket**: `KANBA-92` (`KB-P3-33`: Typed OpenAPI client, TanStack Query keys, optimistic mutations & realtime WS/SSE client)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-92` (`HEAD: 376e20e`)
- **Worktree**: `/tmp/kb-wt-KANBA-92`
- **Scope**: `kanban/tools/export_openapi.py`, `kanban/tests/test_export_openapi.py`, `kanban/api/v1/issues.py`, `kanban/web/src/api/` (`client.ts`, `problem.ts`, `queryKeys.ts`, `queryClient.ts`, `optimistic.ts`, `realtime.ts`)

---

### 1. Architectural & Security Evaluation

#### A. CSRF Enforcement & Hostile Wire Boundaries (S4.1 / S3.4)
- `client.ts` implements strict `assertRelative` validation: any absolute URL, protocol-relative prefix (`//`), scheme (`http:`, `javascript:`, etc.), or backslash character immediately aborts with `ApiClientError('ABSOLUTE_URL_FORBIDDEN')` prior to network invocation.
- For all state-mutating HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`), `getCsrfToken()` extracts the `__Host-kb_csrf` cookie value. If absent, the client immediately throws `ApiClientError('CSRF_TOKEN_MISSING')` without dispatching wire traffic.
- Requests enforce `credentials: 'same-origin'` and `Accept: application/json`. Non-JSON responses on body-bearing responses trigger `ApiClientError('UNEXPECTED_CONTENT_TYPE')`.
- Default request timeout is strictly bounded via `AbortSignal.timeout(15000)` composed with optional caller cancellation signals (`AbortSignal.any`).

#### B. Concurrency Control & ETag Semantics (S1.3 / S7.2)
- `apiFetch` accepts an optional `ifMatch` parameter mapped directly to the `If-Match` HTTP header, guaranteeing optimistic lock integrity for description edits and state transitions.
- `problem.ts` exports `isPreconditionFailed(e)`, providing uniform detection of HTTP 412 responses for mid-air collision handling.
- `kanban/api/v1/issues.py` route parameters were aligned to `{issue_key}`, ensuring generated TypeScript types and openapi.json match ticket requirements while preserving backend UUID/key resolution.

#### C. RFC 7807 Problem Mapping & Anti-Enumeration (S3.4)
- `ApiProblem` parses standard RFC 7807 problem details (`status`, `code`, `title`, `detail`, `instance`). Malformed or non-standard payloads gracefully default to `code: 'UNKNOWN'`.
- `isNotFound(e)` helper evaluates HTTP 404 responses uniformly without distinguishing between nonexistent and unreadable resources, strictly upholding Section 3.4 anti-enumeration requirements.

#### D. Realtime Protocol Alignment & Fallback Resilience (S2.3 / KANBA-77)
- WebSocket client derives endpoints strictly from `window.location` (`ws:` or `wss:`), preventing host injection or rogue broker connections.
- Client envelope matches the KANBA-77 server wire protocol (`op: 'subscribe'`, `req_id`, `channels`, `last_event_id?`) while maintaining backwards-compatible decoding for ticket event structures.
- Frame validation enforces the 256 KiB maximum byte limit and 128-character ID constraint, incrementing `droppedEvents` without executing unsafe deserialization or `eval`.
- Deduplication cache (1000 IDs) prevents replay during transport transitions.
- Exponential backoff with full jitter (`random(0, min(15000, 500 * 2^attempt))`) governs reconnection.
- Automatic failover to SSE (`/sse?channels=...`) activates after 3 consecutive WebSocket failures, utilizing native `Last-Event-ID` resumption.
- Background WebSocket probing every 60s restores primary duplex streaming once connectivity recovers.
- Control frame handling (`ping` -> `pong`, `channel.revoked` -> subscription cleanup, `resync_required` -> full query cache invalidation) is fully verified.

---

### 2. Ruling on Specific Technical Decisions

1. **Server-Contract Alignment (Decision 1)**: APPROVED. Adhering to the authoritative backend contract from KANBA-77 (`kanban/api/ws.py`) while accepting both envelope formats guarantees interoperability with zero regressions.
2. **Route Parameter Rename (Decision 2)**: APPROVED. Renaming `{issue_ref}` to `{issue_key}` in `kanban/api/v1/issues.py` aligns the OpenAPI schema without altering runtime parameter extraction.
3. **SSE Event Naming Gap (Decision 3)**: APPROVED. The client's explicit `SSE_EVENT_NAMES` listener registry resolves the current SSE delivery behavior. A follow-up backlog ticket should be filed to standardize server-side default message event wrapping.
4. **Vitest Coverage Command (Decision 4)**: APPROVED. Scoping coverage via `--coverage.include='src/api/**'` ensures accurate threshold enforcement for the targeted API units.

---

### 3. Verification & Test Metrics

- **Unit Tests**: 76/76 vitest passed in 1.38s (97.96% branch / 100% line in `src/api`).
- **Python Tests**: 4/4 pytest passed in 1.31s (`test_export_openapi.py`).
- **Benchmark**: 500-issue synchronous cache mutation median: 0.014ms (well within the 12ms SLA limit).
- **Static Analysis**: TypeScript check clean, ESLint clean (0 warnings), Ruff clean, Mypy strict clean, ImportLinter 2/2 kept, License gate 0 violations, zero Unicode dashes.

---

### 4. Gate Verdict

The typed OpenAPI client, TanStack Query integration, optimistic mutation pipeline, and realtime client meet all architectural and security requirements.

**VERDICT: APPROVED**
