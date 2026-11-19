# API and Security Specialist Review: KANBA-219

## Review Metadata
- **Ticket ID:** KANBA-219
- **Title:** [KB-AUDIT-13] Implement Workspace AI Providers, Token Budgets, Autonomous Agent Definitions, and Remote mTLS Runners Admin Studio
- **Reviewer:** Backend Architect and API Security Specialist
- **Date:** 2026-11-19
- **Status:** APPROVED (Grade A)
- **Scope of Review:** Backend route registration, request/response validation, authentication and AAL2 enforcement, write-only secret custody, Air-Gap Mode validation, CLI execution policy, single-reveal enrollment token security, and runner revocation integrity.

---

## 1. Endpoint Contracts and Verification Matrix

The following administrative endpoints were audited for conformance to the 👍kanban API specification and security invariants:

| Endpoint | Method | Status Codes | Auth Scheme | Security Guardrails |
| :--- | :---: | :---: | :---: | :--- |
| `/api/v1/admin/ai/providers` | GET, POST | 200, 201, 400, 403, 404 | Server Admin (AAL2) | Write-only secret custody; air-gap cloud blocking |
| `/api/v1/admin/ai/providers/{id}` | GET, PATCH, DELETE | 200, 204, 400, 403, 404 | Server Admin (AAL2) | Preserve secret on partial PATCH; safe deletion |
| `/api/v1/admin/ai/budgets` | GET, PUT | 200, 400, 403, 404 | Server Admin (AAL2) | Token caps and ledger usage accounting |
| `/api/v1/admin/agent-definitions` | GET, POST | 200, 201, 400, 403, 404 | Server Admin (AAL2) | Harness validation; banned flag checks |
| `/api/v1/admin/agent-definitions/{id}` | GET, PATCH, DELETE | 200, 204, 400, 403, 404 | Server Admin (AAL2) | Timeout clamping (1s-300s); tool allowlists |
| `/api/v1/admin/agent-definitions/{id}:validate` | POST | 200, 400, 403, 404 | Server Admin (AAL2) | `kanban-agent validate-echo` offline test probe |
| `/api/v1/admin/agent-runners` | GET | 200, 403, 404 | Server Admin (AAL2) | List runners with heartbeat and cert fingerprint |
| `/api/v1/admin/agent-runners/enrollment-tokens` | POST | 201, 400, 403, 404 | Server Admin (AAL2) | Ephemeral single-reveal token (15m TTL) |
| `/api/v1/admin/agent-runners/{id}:revoke` | POST | 200, 400, 403, 404 | Server Admin (AAL2) | Immediate runner revocation; terminates active jobs |

---

## 2. Technical and Security Audit Findings

### 1. Write-Only Secret Custody and Air-Gap Enforcement
- **Write-Only API Keys:** Provider API keys are never returned in plaintext or masked form in GET or error payloads (`api_key_set: boolean` returned instead). During PATCH updates, existing credentials are preserved intact if the secret field is empty or omitted, and purged only upon explicit request.
- **Air-Gap Mode Guardrail:** When Air-Gap Mode is enabled on the workspace/server, saving or enabling cloud providers (`openai`, `gemini`, or non-local custom endpoints) is blocked with clear validation feedback, while local providers (`ollama`) and local CLI runners operate without restriction.

### 2. Autonomous Agent Definitions and CLI Execution Policy
- **CLI Policy Invariants:**
  - For `agy` binary: CLI arguments must strictly start with `['-p']`.
  - For `codex` binary: CLI arguments must strictly start with `['exec', '-s', 'read-only', '-']`.
  - Banned flags (`--yolo`, `--dangerously*`, `--full-auto`, `--elevated`, `--no-sandbox`) are rejected with RFC 7807 validation errors on both client and server.
- **Execution Bounds:** Timeout values are strictly clamped between 1,000ms (1 second) and 300,000ms (5 minutes).
- **Validation Probe:** The `:validate` endpoint safely runs a synthetic echo probe (`kanban-agent validate-echo`), reporting round-trip latency, exit code, and sanitized stdout/stderr traces without modifying system state.

### 3. Remote mTLS Runners and Enrollment Security
- **Single-Reveal Enrollment Tokens:** Generated tokens have a strict 15-minute time-to-live (`TTL`) and are revealed exactly once in the response payload. They are stored only as cryptographic hashes and cannot be retrieved again after modal dismissal.
- **Immediate Revocation:** The revocation endpoint immediately invalidates the runner certificate association, updates its status to `revoked`, and rejects subsequent heartbeat or mTLS communication.
- **AAL2 and Anti-Enumeration:** All endpoints enforce `require_admin_aal2`. Unauthorized or unauthenticated attempts return standard 403/404 responses without leaking entity existence or metadata.

---

## 3. Security and Architecture Invariants

1. **UTF-16 Surrogate Protection:** All input strings are validated against lone surrogates (`0xD800 <= ord(c) <= 0xDFFF`) prior to UTF-8 serialization.
2. **Strict Safe Typing:** All TypeScript interfaces and backend Pydantic models are strictly typed with zero `any` escapes.
3. **No Unapproved Dependencies:** Zero GPL/AGPL dependencies introduced. All functionality uses native standard libraries and existing project utilities.

---

## 4. API Specialist Verdict

- **Decision:** APPROVED
- **Score:** 100/100
- **Notes:** All backend contracts, security boundaries, and validation requirements requested by @api-spec have been verified and approved.
