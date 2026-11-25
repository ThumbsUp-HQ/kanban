# API Specialist Review & Verification: KAN-411

- **Ticket ID:** KAN-411
- **Reviewer Persona:** Senior Backend & API Architect (`@api-spec`)
- **Target Surfaces:** Slice 2 Backend Wiring & Setting Inventory Audit (`docs/workouts/slice-2-ai-agents-runners/01-audit-and-cuts.md`)
- **Audit Date:** 2026-11-25
- **Branch:** `fix/p1-audits-rc2` (base `71b847ba`)
- **Verdict:** APPROVED (Zero REST or MCP Contract Regressions; 100% Backend Wiring Traceability Verified)

---

## 1. Scope & Backend Topology Audit

A comprehensive forensic audit of the Slice 2 setting inventory and simplification audit document (`docs/workouts/slice-2-ai-agents-runners/01-audit-and-cuts.md`) was performed against all relevant backend routers, services, and CLI endpoints across all 127 cataloged settings (119 KEEP, 4 SIMPLIFY, 4 MOVE_TO_ADVANCED, 0 MERGE, 0 CUT):

### 1.1 AI Provider Management (`kanban/api/v1/admin/ai_providers.py`)
- **Air-Gap Egress vs Probe Semantics:**
  - `POST /api/v1/admin/ai/providers` and `PATCH /api/v1/admin/ai/providers/{id}` strictly enforce air-gap policy at the persistence boundary: attempting to configure or update cloud endpoints while air-gap mode is active raises `409 AIR_GAP_EGRESS_DENIED`.
  - `POST /api/v1/admin/ai/providers/probe-models` and `POST /api/v1/admin/ai/providers/{id}/probe-models` execute probe diagnostics gracefully: if air-gap mode is active, the endpoint does not throw an unhandled 409; instead, it returns `200 ProviderProbeResult(ok=False, error="Air gap egress blocked")`.
- **Secret Envelope & Key Clearing:**
  - Write-only envelope encryption (KEK/DEK) is strictly preserved.
  - The `clear-key-checkbox` control in `AiProviderEditorDrawer.tsx` sends `api_key: null` in the `PATCH` payload to clear stored secret envelope material (NOT a separate pseudo-parameter like `clear_api_key`).
- **Provider Ordering & Priority:**
  - `PUT /api/v1/admin/ai/providers/order` sets atomic priority ranks in clean multiples of 10 (`(idx + 1) * 10`), mapped to `provider-rank-${p.id}`.
- **Provider Lifecycle:**
  - `POST /api/v1/admin/ai/providers/{id}:disable` suspends completions.
  - `DELETE /api/v1/admin/ai/providers/{id}` deletes the provider configuration and records an immutable audit ledger entry.
- **Quota & Budgets:**
  - `GET /api/v1/admin/ai/budgets` and `PUT /api/v1/admin/ai/budgets` manage token budgets. Setting `token_cap=0` enforces a freeze on completions.

### 1.2 Autonomous Agents & Schemas (`kanban/api/v1/agent_definitions.py` & `kanban/agents/schemas.py`)
- **Project-Scope Schema Parity:**
  - Multi-tenant `project_id` schema declarations are located in `kanban/agents/schemas.py:33,274` (not in `agent_definitions.py`).
- **Agent Definition Endpoints:**
  - `GET /api/v1/admin/agent-definitions`, `POST /api/v1/admin/agent-definitions`, `PATCH /api/v1/admin/agent-definitions/{id}`, and `DELETE /api/v1/admin/agent-definitions/{id}` are mapped 1:1.
  - CLI binary validation for `agent-cli-binary-select` (`gemini-cli` and `claude-code`) is governed by `kanban/web/src/features/admin-agents/cliPolicy.ts:12-17` and backend agent definition runner dispatch.
- **Validation Execution:**
  - `POST /api/v1/admin/agent-definitions/{id}:validate` executes live or dry-run validation, returning the structured 4-section verification report (`rendered_context`, `tool_trace`, `latency_and_tokens`, `schema_and_policy`).

### 1.3 Remote Runners & CLI Harness (`kanban/api/v1/remote_runners.py` & `agent/remote_runner/cli.py`)
- **Runner State & CLI Compatibility (Merged via KAN-399 on `main` at `71b847ba`):**
  - `agent/remote_runner/cli.py:93-129,262-310`: `default_runner_state_dir()` enforces `~/.kanban-runner/` with `0o700` POSIX directory permissions.
  - `default_runner_config_path()` locates configuration cleanly within the state directory.
  - CLI flag `--server-url` is canonical; `--url` is preserved as a backwards-compatible alias.
  - CLI rejects `--token` passed via command-line arguments to prevent token exposure in `/proc/cmdline`, requiring `--token-stdin`.
- **Enrollment & Operations:**
  - `POST /api/v1/admin/agent-runners/enrollment-tokens` mints single-use `kb_rnr_enroll_*` with TTL 60..900s.
  - `POST /api/v1/agent-runners/enroll` validates CSR and issues leaf certificate with intermediate CA bundle.
  - `GET /api/v1/admin/agent-runners` lists registered runners with status, certificate expiration, and last heartbeat.
  - `POST /api/v1/admin/agent-runners/{id}:revoke` revokes runner access under AAL2 protection.
  - `GET/WS /api/v1/agent-runners/ws` enforces mTLS client certificate verification, Proof-of-Possession challenge, and heartbeat touch.

### 1.4 LLM Manifest & Documentation Ops (`kanban/ops/llms_txt.py`)
- In-memory cached `/llms.txt`, `/llms-full.txt`, `/llms-skills/{slug}.md`, and `/api/v1/system/skills`.
- Zero Host-header injection, ETag caching, and alignment with local-folder onboarding (`KAN-403`).

### 1.5 Security & Session Integrity
- **WebSudo Session Keepalive:**
  - Drawer and modal components leverage `useAal2DirtyKeepalive()` from `KAN-404` to maintain AAL2 session validity during active drafting.
- **Password Manager Neutralization (Merged via KAN-400 on `main` at `71b847ba`):**
  - `AiProviderEditorDrawer.tsx:527-551` contains zero `input[type="password"]` fields, utilizing masked text inputs with `.kb-masked-api-key` and `data-1p-ignore`/`data-lpignore` attributes.

---

## 2. API Contract & Wiring Verification

1. **Setting-by-Setting Mapping Parity:**
   Every one of the 127 UI controls identified in the inventory table maps accurately to a real backend endpoint, schema, or CLI parameter.
2. **Security & Boundary Invariants:**
   - Envelope encryption for stored provider keys is strictly enforced.
   - Air-gap policy enforcement is documented and tested fail-closed (`409 AIR_GAP_EGRESS_DENIED` on mutating endpoints; non-crashing `200 ProviderProbeResult(ok=False)` on diagnostic probes).
   - Administrative AAL2 requirement (`require_admin_aal2`) is maintained across all administrative surfaces.
3. **Traceability to Downstream Tickets:**
   The Phase 2 (`KAN-412`) checklist cleanly separates implementation tasks, respecting already-merged work on `main` (`KAN-399`, `KAN-400`).

---

## 3. Verdict

**APPROVED.** The audit document is technically precise, forensically verified against backend code on `main` (`71b847ba`), and provides an authoritative foundation for Phase 2 implementation.
