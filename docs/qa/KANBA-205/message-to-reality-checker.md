# Forensic Verification Proof Packet: KANBA-205

## Ticket Identification
- **Ticket ID:** KANBA-205
- **Title:** [KB-QA-MCP] CLI MCP Scoping QA: User vs Project Agent Matrix (agy & codex)
- **Branch:** `feat/kanba-205`
- **Scope Classification:** `N/A - Non-UI Ticket`

---

## 1. Executive Summary & Verification Narrative

Ticket KANBA-205 establishes the definitive, deterministic contract and live CLI verification matrix for Model Context Protocol (MCP) dynamic connection scoping across Antigravity CLI (`agy`) and OpenAI Codex CLI (`codex`).

The test suite validates:
1. **Condition A (User Agent Unscoped Global Key):**
   - Verified that `tools/list` on `/mcp/agent` exposes exactly the 9 official agent tools.
   - Verified disposable CRUD operations on project `QAUSR1`.
   - Verified anti-enumeration fail-closed behavior returning RFC 7807 `404 NOT_FOUND` for unauthorized issues.
2. **Condition B (User Agent Unscoped Key to Scoped Endpoints):**
   - Verified workspace resolution on `/mcp/agent/w/kanban`.
   - Verified automatic population of `project="QAUSR1"` on mutations when omitted in project-scoped connections.
   - Verified cross-project mutation rejection with `CONNECTION_SCOPE_VIOLATION`.
3. **Condition C (User Agent Project-Pinned Key):**
   - Verified that presenting a project-pinned key on unscoped `/mcp/agent` monotonically narrows effective scope to `QAUSR1`.
   - Verified that connecting to foreign workspace or foreign project endpoints fails with HTTP 403 `KEY_SCOPE_VIOLATION`.
   - Verified that `agent:read`-only keys reject mutations with `INSUFFICIENT_SCOPE`.
4. **Condition D (Project Agent Service Bot):**
   - Verified service bot operations within `QAADM` via `/mcp/agent/w/kanban/p/QAADM` and header-scoped `/mcp/agent`.
   - Verified rejection on foreign scopes with HTTP 403 `KEY_SCOPE_VIOLATION`.
   - Verified `allowed_tools` and `disabled_tools` filtering in both `tools/list` and `tools/call`.
   - Verified that read-only capability mask (`capability_mask=1`) blocks write mutations with `INSUFFICIENT_CAPABILITY` / `INSUFFICIENT_PERMISSION`.
5. **Condition E (Surface Cross-Isolation & Admin RBAC Parity):**
   - Verified surface key mismatch rejection (HTTP 403 `SURFACE_KEY_MISMATCH`) for cross-surface key usage.
   - Verified admin downstream RBAC parity denying read-only keys on mutations and denying workspace administrators on server administrator operations (`manage_auth_cards`).
   - Verified 2-stage confirmation on `destructive_lifecycle` (`request_delete` -> `execute_delete`).
6. **Condition F (Protocol Preconditions, Session Binding, TaintGuard, and TTL Revocation):**
   - Verified unauthenticated HTTP 401 carrying RFC 9728 `resource_metadata` challenge.
   - Verified RFC 9728 metadata JSON payload at `/.well-known/oauth-protected-resource/mcp/*`.
   - Verified 400 `CONFLICTING_SCOPE_HEADERS` and 400 `VALIDATION_FAILED`.
   - Verified session replay protection returning HTTP 404 on scope or token mismatch.
   - Verified `TaintGuard` cross-scope write block returning HTTP 409 `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`.
   - Verified cache TTL expiry (15s) and token revocation transitioning to HTTP 401.

---

## 2. Forensic Proof Inventory & Evidence Mapping

| Definition of Done Requirement | Primary Evidence File | Forensic Validation Description |
| :--- | :--- | :--- |
| **1. Live Isolated CLI Probes (`agy` & `codex`)** | `docs/qa/KANBA-205/cli-probes.txt` | Live non-interactive CLI probe outputs from `agy -p ... --model gemini-4-hydrogen-low --dangerously-skip-permissions` and `codex --model gpt-6-luna --yolo exec --cd /tmp/kb-mcp-probe` discovering all 9 tools on `kb_probe_1` from clean `/tmp/kb-mcp-probe` directory. |
| **2. Atomic Config Integrity & Zero Secret Leakage** | `docs/qa/KANBA-205/mcp-config-integrity.log` | Pre-run and post-run SHA-256 validation proving bit-for-bit restoration of `/home/adamoutler/.gemini/config/mcp_config.json` and `/home/adamoutler/.codex/config.toml`. Zero raw tokens appear across all files. |
| **3. Deterministic Scoping Matrix Suite (>=95% Coverage)** | `docs/qa/KANBA-205/unit-test-results.txt` | 328 passed unit tests with 95.67% total branch coverage on `mcp` (meeting the >=95% gate requirement). Zero failed or skipped tests. |
| **4. Build & Static Analysis Checks** | `docs/qa/KANBA-205/build-check.txt` | Output from `uv run python -m scripts.check_no_dashes --all` and static analysis checks confirming zero errors. |
| **5. Wire-Level HTTP/JSON-RPC Transcript** | `docs/qa/KANBA-205/mcp-transcript.txt` | Complete redacted HTTP/1.1 wire exchanges recorded via `KB_MCP_TRANSCRIPT_PATH`. All tokens sanitized as `kb_agt_***REDACTED***`. |
| **6. Structured Contract Sample** | `docs/qa/KANBA-205/contract-sample.json` | JSON document containing `matrix_summary`, RFC 9728 metadata samples, and recorded exchanges across Conditions A-F. |
| **7. Dual Specialist Approvals** | `docs/qa/KANBA-205/api-specialist-review.md`, `docs/qa/KANBA-205/ui-specialist-review.md` | Both reviews certify `Verdict: APPROVED` evaluating MCP protocol contracts, scoping invariants, and CLI setup ergonomics. |
| **8. Non-UI Ticket Certification** | This document | Declares `N/A - Non-UI Ticket` confirming zero frontend DOM components were altered and no dummy screenshots are required. |

---

## 3. Cryptographic Verification & Secret Audit

- **Raw Secret Audit Command:** `grep -rnE "kb_(agt|doc|adm)_[A-Za-z0-9]{10,}" docs/qa/KANBA-205/`
- **Result:** `0` matches found. All secrets are scrubbed and redacted.
- **Em-Dash / En-Dash Audit Command:** `uv run python -m scripts.check_no_dashes --all`
- **Result:** `PASS` (0 forbidden unicode dashes).
