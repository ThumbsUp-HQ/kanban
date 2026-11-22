# API and Security Specialist Review: KAN-70

- **Ticket:** KAN-70 ([KB-SEC-TAINT-01]) - Add Content Provenance Trust Tiers, Same-Project Prompt-Injection Taint Tracking & Dynamic MCP Capability Stripping
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `feat/KAN-70-content-provenance-taint`
- **Commit Under Audit:** `c8dfa07c` (`feat(security): KAN-70 content provenance trust tiers, taint tracking and capability stripping`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan70-13acc0b7`
- **Status:** APPROVED

---

## 1. Executive Security & Architecture Evaluation

Ticket KAN-70 establishes end-to-end prompt injection defenses across the database engine, API mutation pipelines, MCP tool catalog dispatch, and agent transition context formatting.

Audited security invariants across the four problem areas:
1. **Content Provenance Trust Tiers & Self-Upgrade Prevention (Alembic `p6_07`):**
   - Chains onto `p6_05_issue_leases_and_fencing` with clean up and down SQL definitions.
   - Installs `provenance_tier` enum/check constraint (`trusted_member`, `verified_agent`, `imported`, `external_webhook`, `public_reporter`, `untrusted_intake`) and stored generated column `is_untrusted_content` across `issues`, `issue_comments`, `docs`, `pages`, and `stickies`.
   - ORM models in `database/models/issues.py`, `database/models/knowledge.py`, and `database/models/prose.py` maintain strict schema parity.
   - Server-side derivation in `kanban/api/v1/issues.py` and `comments.py` blocks caller self-upgrade: requests arriving over untrusted channels attempting to claim `trusted_member` or `verified_agent` are rejected with HTTP 403 `PROVENANCE_SELF_UPGRADE_FORBIDDEN`.
2. **Same-Project Prompt-Injection Taint Tracking & Exfiltration Guard:**
   - Extends `mcp_read_taint` with `untrusted_source_object_id` and `contains_untrusted_content`.
   - Reading untrusted content records active taint and sets `X-Kanban-Untrusted-Taint: 1`.
   - Subsequent mutating or linking operations across all projects (including the same project) are blocked with HTTP 409 `UNTRUSTED_CONTENT_TAINT_ACTIVE` and logged to the ledger as `MCP_TAINT_BLOCKED`.
   - Clean reads of `trusted_member` content do not trigger untrusted taint, preserving same-project workflows.
   - Explicit human confirmation tokens (`human_confirmation_token` query parameter or `X-KB-Human-Confirmation-Token` header) permit intentional human overrides.
3. **Dynamic MCP Capability Stripping & Notification:**
   - Advertises `"tools": {"listChanged": true}` during `initialize` for dynamic client notification.
   - When untrusted content is read, the session is marked untrusted-tainted. `_handle_tools_list()` dynamically strips all mutation, state transition, and linking tools from the catalog.
   - Pre-dispatch guard in `_handle_tools_call()` aborts any attempted execution of stripped tools.
4. **Transition Context Spotlighting & Delimiter Collision Resistance:**
   - In `agent/context/transition_context.py`, all fields containing untrusted data (`summary`, `priority`, `labels`, `actor`, and hydrated `comments`) are enclosed in randomized delimiters (`<<<UNTRUSTED_TICKET_DATA_{16-hex}>>>`).
   - Delimiter generation verifies that hostile prose does not collide with candidate delimiters across up to 8 randomized attempts (`MAX_DELIMITER_ATTEMPTS = 8`), failing closed with `ContextDelimiterCollisionError` on exhaustion.

---

## 2. Wire Contracts & Security Invariants

### A. HTTP & MCP Error Contracts
- Attempted self-upgrade returns HTTP 403 `PROVENANCE_SELF_UPGRADE_FORBIDDEN`.
- Mutation with active untrusted taint returns HTTP 409 `UNTRUSTED_CONTENT_TAINT_ACTIVE` detailing source object ID and tainted project.
- Pre-dispatch MCP tool calls on tainted sessions return standard JSON-RPC 2.0 error responses with `code: "UNTRUSTED_CONTENT_TAINT_ACTIVE"`.

### B. Tenancy & Anti-Enumeration
- Taint records and provenance checks strictly respect active Row-Level Security contexts.
- Error payloads reveal no unauthorized principal or cross-tenant metadata.

---

## 3. Unit Test Coverage & Verification Metrics

- **Backend Pytest Results:** 42 passed in 4.60s (`test_untrusted_content_taint.py`, `test_read_taint.py`, `test_dynamic_taint_stripping.py`, `test_protocol.py`, `test_transition_context_spotlighting.py`, `test_transition_context.py`, `test_p1_17_models.py`).
- **Static Quality Checks:**
  - `ruff check`: All checks passed (0 errors).
  - `ruff format --check`: 2227 files formatted.
  - `mypy`: 0 issues found in 1235 source files.
  - `lint-imports`: 2 kept, 0 broken contracts.
  - `check-migrations`: Valid single head `p6_07_content_provenance_and_taint` (68 valid migrations).
  - `check_no_dashes`: Clean across repository (0 violations).

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review and routing to `@merge-ci`.
