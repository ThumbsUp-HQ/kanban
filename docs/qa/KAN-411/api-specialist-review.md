# API Specialist Review & Verification: KAN-411

- **Ticket ID:** KAN-411
- **Reviewer Persona:** Senior Backend & API Architect (`@api-spec`)
- **Target Surfaces:** Slice 2 Backend Wiring & Setting Inventory Audit (`docs/workouts/slice-2-ai-agents-runners/01-audit-and-cuts.md`)
- **Audit Date:** 2026-11-25
- **Verdict:** APPROVED (Zero REST or MCP Contract Regressions; 100% Backend Wiring Traceability Verified)

---

## 1. Scope & Backend Topology Audit

A comprehensive forensic audit of the Slice 2 setting inventory and simplification audit document (`docs/workouts/slice-2-ai-agents-runners/01-audit-and-cuts.md`) was performed against all relevant backend routers, services, and CLI endpoints:
- `kanban/api/v1/admin/ai_providers.py`:
  - `GET /api/v1/admin/ai/providers`: Correctly inventoried; verifies caller possesses `require_admin_aal2` and workspace/project admin authority before returning `ProviderConfigPublic` (omitting secret material).
  - `PUT /api/v1/admin/ai/providers/order`: Correctly inventoried; requires full membership validation and sets atomic priority ranks in multiples of 10 (`(idx + 1) * 10`).
  - `POST /api/v1/admin/ai/providers/probe-models` & `POST /api/v1/admin/ai/providers/{id}/probe-models`: Correctly inventoried; passes draft or stored envelope key to `AIProviderConfigService.probe_provider()`, enforcing air-gap check.
  - `POST /api/v1/admin/ai/providers/test-connection` & `POST /api/v1/admin/ai/providers/{id}/test-connection`: Correctly mapped; verifies network latency, model counts, and authentication.
  - `POST /api/v1/admin/ai/providers` & `PATCH /api/v1/admin/ai/providers/{id}`: Correctly mapped; enforces KEK/DEK envelope encryption and raises `409 AIR_GAP_EGRESS_DENIED` on cloud endpoints during active air-gap mode.
  - `POST /api/v1/admin/ai/providers/{id}:disable`: Correctly mapped; suspends provider completions.
  - `DELETE /api/v1/admin/ai/providers/{id}`: Correctly mapped; purges provider config and writes audit ledger activity.
  - `GET /api/v1/admin/ai/budgets` & `PUT /api/v1/admin/ai/budgets`: Correctly mapped; updates daily/monthly token caps. Setting `token_cap=0` freezes provider completions.
- `kanban/api/v1/agent_definitions.py`:
  - `POST /api/v1/workspaces/{workspace}/agent-definitions` and admin equivalent: Correctly mapped; validates slug pattern (`^[a-z0-9][a-z0-9-]{1,62}$`), harness kind, and CLI arguments against pinned policy.
  - `POST /api/v1/admin/agent-definitions/{id}:validate`: Correctly mapped; executes `validate-echo` and returns structured 4-section verification report (`rendered_context`, `tool_trace`, `latency_and_tokens`, `schema_and_policy`).
- `kanban/api/v1/remote_runners.py`:
  - `POST /api/v1/admin/agent-runners/enrollment-tokens`: Correctly mapped; mints cryptographically signed single-use token (`kb_rnr_enroll_*`) with TTL 60..900s.
  - `GET /api/v1/admin/agent-runners`: Correctly mapped; returns registered runners with status, certificate expiration, and last heartbeat.
  - `POST /api/v1/admin/agent-runners/{id}:revoke`: Correctly mapped; requires AAL2, cancels in-flight WebSocket jobs, and invalidates client certificate.
  - `POST /api/v1/agent-runners/enroll`: Correctly mapped; validates CSR, signs leaf certificate via derived intermediate CA, and returns certificate bundle with WSS URL.
  - `GET/WS /api/v1/agent-runners/ws`: Correctly mapped; enforces mTLS client certificate verification, Proof-of-Possession challenge, and heartbeat touch.
- `agent/remote_runner/cli.py`:
  - Rejects passing `--token` on CLI arguments to protect `/proc/cmdline`.
  - Audited improvements align with KAN-399 (`default_runner_state_dir()` with `0o700` POSIX permissions, `--server-url` flag parity).
- `kanban/ops/llms_txt.py`:
  - In-memory cached `/llms.txt`, `/llms-full.txt`, `/llms-skills/{slug}.md`, and `/api/v1/system/skills`.
  - Zero Host-header injection, ETag caching, and local-folder onboarding alignment with KAN-403.

---

## 2. API Contract & Wiring Verification

1. **Setting-by-Setting Mapping Parity:**
   Every UI control identified in the inventory table maps to a real backend endpoint or property. No hallucinated routes or invalid parameters exist in the specification.
2. **Security & Boundary Invariants:**
   - Write-only envelope encryption for API keys is strictly preserved.
   - Air-gap policy enforcement is documented and tested fail-closed (`409 AIR_GAP_EGRESS_DENIED`).
   - AAL2 requirement on all administrative routes (`require_admin_aal2`) is maintained without bypass.
3. **Traceability to Downstream Tickets:**
   The action checklist cleanly isolates Phase 2 tasks from KAN-404 (WebSudo), KAN-399 (Runner CLI), KAN-400 (Password Manager fix), KAN-401/402 (Workspace/Project scope), and KAN-403 (Local folder onboarding).

---

## 3. Verdict

**APPROVED.** The audit document is technically precise, forensically verified, and provides an authoritative foundation for Phase 2 implementation.
