# Reality Checker Forensic QA Audit Report: KANBA-205

**Ticket ID:** KANBA-205  
**Title:** [KB-QA-MCP] CLI MCP Scoping QA: User vs Project Agent Matrix (agy & codex)  
**Branch:** `feat/kanba-205`  
**Target Commit:** `5fe0de9` (merged into `main`)  
**Scope Classification:** `N/A - Non-UI Ticket`  
**Auditor:** reality-checker (Passive Forensic QA Gate Persona)  
**Date:** 2026-11-18  
**Final Grade:** A  
**Final Verdict:** READY  

---

## 1. Executive Summary & Gate Status

A rigorous passive forensic QA audit was performed for ticket `KANBA-205` based strictly on git diffs, unit and branch coverage test logs, static analysis logs, specialist review certifications, wire transcripts, configuration integrity logs, and CLI probe execution outputs in `docs/qa/KANBA-205/`. In strict accordance with passive audit directives, no live shell commands were executed, and no external endpoints were visited.

All mandatory project-local gates and security invariants have been verified and certified:
- **Scope Classification:** Certified as `N/A - Non-UI Ticket` (no browser DOM elements or styles modified; no UI screenshots required).
- **API Specialist Sign-Off:** APPROVED by `api-specialist` in `docs/qa/KANBA-205/api-specialist-review.md`.
- **UI Specialist Sign-Off:** APPROVED by `ui-specialist` in `docs/qa/KANBA-205/ui-specialist-review.md` (DX, CLI ergonomics, configuration hygiene, and error feedback).
- **Automated Tests & Coverage:** 328 unit tests passed cleanly with 95.67% total branch coverage on `mcp` (satisfying the >=95% gate mandate).
- **Static Analysis & Build:** Clean passes on Ruff check, Ruff format, MyPy strict typing, single migration head check, and `check_no_dashes --all`.
- **Atomic Configuration Integrity:** Pre-run and post-run SHA-256 validation confirms bit-for-bit restoration of `mcp_config.json` and `config.toml` with zero residual probe entries.
- **Secret Scrubbing:** Zero raw `kb_*` bearer tokens appear across all files, transcripts, and logs (all sanitized as `kb_agt_***REDACTED***`).
- **Typography & Punctuation:** Verified zero em-dashes and zero en-dashes across all code, tests, and documentation.

---

## 2. Multi-Tenant Scoping Matrix (Conditions A through F) Verification

| Condition | Description & Protocol Bounds | Implementation & Test Proof | Verdict |
| :--- | :--- | :--- | :---: |
| **Condition A: User Agent Unscoped Global Key** | `personal_user` token (`kb_agt_*`) on `/mcp/agent`. `tools/list` returns exactly 9 core agent tools; disposable CRUD on `QAUSR1` succeeds; unauthorized project accesses return RFC 7807 `404 NOT_FOUND` (anti-enumeration). | `tests/mcp/test_mcp_scoping_qa_matrix.py` (Condition A); verified in `cli-probes.txt` for both `agy` and `codex`. | PASS |
| **Condition B: User Agent Unscoped Key to Scoped Endpoints** | Connection to `/mcp/agent/w/kanban` and `/mcp/agent/w/kanban/p/QAUSR1`. Project parameter auto-populates as `QAUSR1` when omitted; cross-project write mutations (e.g. `QAADM`) are rejected with `403 CONNECTION_SCOPE_VIOLATION`. | `tests/mcp/test_mcp_scoping_qa_matrix.py` (Condition B); verified in `mcp-transcript.txt`. | PASS |
| **Condition C: User Agent Project-Pinned Key** | `scope_tier="project"` pinned to `QAUSR1`. Presenting key on `/mcp/agent` narrows effective scope to `QAUSR1`; connecting to `/mcp/agent/w/kanban/p/QAADM` fails with `403 KEY_SCOPE_VIOLATION`; read-only keys reject writes with `403 INSUFFICIENT_SCOPE`. | `tests/mcp/test_mcp_scoping_qa_matrix.py` (Condition C); verified in `cli-probes.txt`. | PASS |
| **Condition D: Project Agent (Service Bot)** | `service_bot` (`kb_agt_*`) bound to `QAADM`. Connects to `/mcp/agent/w/kanban/p/QAADM` and header-scoped `/mcp/agent`; foreign project connections fail `403 KEY_SCOPE_VIOLATION`; `allowed_tools`/`disabled_tools` filter list and calls; `capability_mask=1` rejects writes with `403 INSUFFICIENT_CAPABILITY`. | `tests/mcp/test_mcp_scoping_qa_matrix.py` (Condition D); verified in `contract-sample.json`. | PASS |
| **Condition E: Surface Cross-Isolation & Admin RBAC** | Cross-surface key mismatch (`kb_agt_*` on docs/admin, `kb_doc_*` on agent/admin, `kb_adm_*` on agent/docs) yields `403 SURFACE_KEY_MISMATCH`. Read-only admin keys cannot execute modifying tools; 2-stage destructive lifecycle (`request_delete` -> `execute_delete`) enforced. | `tests/mcp/test_mcp_scoping_qa_matrix.py` (Condition E); verified in `cli-probes.txt`. | PASS |
| **Condition F: Protocol Preconditions, Session Binding, TaintGuard, TTL Revocation** | Unauthenticated `POST /mcp/agent` returns `401` with RFC 9728 `resource_metadata`; conflicting headers return `400 CONFLICTING_SCOPE_HEADERS`; missing workspace returns `400 VALIDATION_FAILED`; session replay across scopes returns `404`; TaintGuard blocks cross-scope writes with `409 CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`; cache TTL expiry evicts in 15s. | `tests/mcp/test_mcp_scoping_qa_matrix.py` (Condition F); verified in `mcp-transcript.txt`. | PASS |

---

## 3. Forensic Review of Dual Specialist Sign-Offs

### 3.1 API Specialist Review (`docs/qa/KANBA-205/api-specialist-review.md`)
- **Reviewer:** `api-specialist` (API & Security Architecture Swarm Reviewer)
- **Verdict:** `APPROVED`
- **Audit Findings:**
  - Audited all six conditions (A through F) against MCP application factory, authentication middleware, and protocol handlers.
  - Confirmed cryptographic surface isolation and 2-stage destructive lifecycle safety.
  - Confirmed 328 unit tests passed with 95.67% total branch coverage on `mcp`.
  - Confirmed secret scrubbing and strict ASCII hyphenation.

### 3.2 UI Specialist Review (`docs/qa/KANBA-205/ui-specialist-review.md`)
- **Reviewer:** `ui-specialist` (UX Architect & UI Designer Specialist Persona)
- **Verdict:** `APPROVED`
- **Audit Findings:**
  - Validated developer experience and CLI tool ergonomics across `agy` and `codex` probes.
  - Verified clear, actionable error feedback structures (`KEY_SCOPE_VIOLATION`, `SURFACE_KEY_MISMATCH`, RFC 9728 `WWW-Authenticate`).
  - Audited `mcp-config-integrity.log` confirming bit-for-bit configuration rollback.
  - Verified and confirmed `N/A - Non-UI Ticket` scope classification.

---

## 4. Live CLI Probes & Configuration Integrity

### 4.1 Live Isolated CLI Probes (`docs/qa/KANBA-205/cli-probes.txt`)
- **Harness 1 (`agy`):** Executed `agy -p ... --model gemini-4-hydrogen-low --dangerously-skip-permissions` from clean `/tmp/kb-mcp-probe` directory. Correctly discovered all 9 core agent tools and executed lexical search on `QAUSR1`.
- **Harness 2 (`codex`):** Executed `codex --model gpt-6-luna --yolo exec --cd /tmp/kb-mcp-probe`. Correctly inspected `kb_probe_1` tool definitions and reported all 9 agent tools with terse descriptions.
- **Probe Scenarios:** Cleanly recorded live responses for workspace scoping (200 OK), project-pinned violation (403 KEY_SCOPE_VIOLATION), service bot scoping (200 OK), surface key mismatch (403 SURFACE_KEY_MISMATCH), and unauthenticated challenge (401 Unauthorized with RFC 9728 `resource_metadata` link).

### 4.2 Configuration Integrity Log (`docs/qa/KANBA-205/mcp-config-integrity.log`)
- Pre-run SHA-256 baseline comparison:
  - `/home/adamoutler/.gemini/config/mcp_config.json`: OK
  - `/home/adamoutler/.codex/config.toml`: OK
- Verified clean rollback with zero residual probe server entries.

---

## 5. Automated Test & Static Analysis Proofs

### 5.1 Unit & Branch Coverage Test Logs (`docs/qa/KANBA-205/unit-test-results.txt`)
- Total statements: 13,351
- Total branch points: 2,940
- Total coverage: 95.67% (exceeding the >=95% gate requirement)
- Test outcomes: 328 passed, 0 failures, 1 warning (deprecation notice from dependency) in 89.43s.

### 5.2 Build & Linter Logs (`docs/qa/KANBA-205/build-check.txt`)
- Ruff check (tests/mcp): All checks passed.
- Ruff format (tests/mcp): 2 files already formatted.
- MyPy strict typing: 0 issues found in 2 source files.
- Single migration head: All 60 migrations valid. Single head: `p4_21_workspace_project_rbac_fix`.
- Dash check: 0 dash violations.

### 5.3 Wire Transcript & Contract Sample (`docs/qa/KANBA-205/mcp-transcript.txt`, `contract-sample.json`)
- Verified wire exchanges for JSON-RPC 2.0 `initialize`, `tools/list`, and `tools/call`.
- Verified RFC 9728 discovery metadata and error payload structures across Conditions A through F.
- Confirmed zero plaintext tokens leaked in transcripts or contract samples.

---

## 6. Audit Verdict & Certification

All Definition of Done requirements, multi-tenant scoping invariants, test coverage gates (>=95%), CLI configuration hygiene guarantees, and dual specialist gate approvals for ticket `KANBA-205` are completely fulfilled.

**Final Grade:** A  
**Final Verdict:** READY
