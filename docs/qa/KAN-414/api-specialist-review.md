# API Specialist Review: KAN-414 (Slice 2 Phase 4 Publish Verified AI Providers, Agents, mTLS Runners & Local Onboarding Wiki + In-App Docs)

**Ticket:** KAN-414 (`[SLICE-2-P4][KB-AI-DOCS]`)  
**Parent Epic:** KAN-410 (`[EPIC][SLICE-2-AI-AGENTS-RUNNERS]`)  
**Auditor:** `api-spec` (API Architect & Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan414-4c7f6e57`  
**Target Commit:** `f7f38a74` (branch `docs/KAN-414-slice2-ai-docs`)  
**Wiki Commit:** `5365cc5` (branch `docs/KAN-414-slice2-ai-docs` inside `./thumbs-up-kanban.wiki`)  

---

## 1. Executive Summary & Verdict

This API Specialist Review audits the technical accuracy, schema fidelity, protocol specifications, API contracts, and security documentation delivered in **KAN-414: Phase 4 Publish Verified AI Providers, Agents, mTLS Runners & Local Onboarding Wiki + In-App Docs**.

The documentation covers the entire Slice-2 subsystem across authoritative wiki chapters (`Multi-Provider-AI-Engine-and-Runners.md` and Sections 8, 9, 10 of `Studio-Configuration-Reference.md`) and the compiled offline in-app DocsCenter manifest (`wikiManifest.ts`). Every setting, data type, sandbox tier, validation trace, and daemon protocol was verified against the backend API routers and React studio components:
1. **Multi-Provider AI Engine & Token Budgets**:
   - Provider probing and connection testing routes: `POST /api/v1/admin/ai-providers/probe-models` (backend proxy discovery) and `POST /api/v1/admin/ai-providers/test-connection`.
   - Ordering and failover persistence: `POST /api/v1/admin/ai-providers/order`.
   - Token budget ceiling semantics verified: `POST /api/v1/admin/ai-providers/budgets` where `token_cap=0` strictly enforces **Hard AI Freeze** (`TOKEN_BUDGET_EXCEEDED`) and `token_cap=10_000_000_000` indicates **Unlimited Quota**.
   - Zero cleartext secrets exposed in frontend responses; credentials write-only.
2. **Autonomous Agent Definitions & Validation Sandbox**:
   - Validation endpoint `POST /api/v1/agent-definitions/{id}:validate` documented with atomic 4-section execution trace:
     1. Prompt Assembly
     2. Provider Dispatch
     3. Output Parse
     4. State Transition
   - Reasoning timeout ceiling enforced per KAN-430: `timeout_ms <= 300000` (300 seconds).
   - Trigger modes: `on_issue_create`, `on_comment`, `manual_invoke`.
   - Repository access modes: `none`, `ro_mount` (`CLONE_NEWNS` isolated mount), and `ephemeral_clone`.
3. **Remote mTLS Runners & Proof-of-Possession Handshake**:
   - Single-use enrollment tokens minted via `POST /api/v1/admin/agent-runners/enrollment-tokens` (`max_ttl_seconds <= 900`).
   - Cryptographic Proof-of-Possession header: `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256}` with replay window tolerance `abs(now - ts) <= 300` and single-use nonce consumption.
   - Non-root daemon POSIX permissions: directory `0o700`, private key and CA bundle `0o600`, certificate `0o644`.
   - Certificate revocation endpoint: `POST /api/v1/admin/agent-runners/{id}:revoke`.
4. **Local-Folder Discovery & Parallel-Safe Governance**:
   - Local onboarding discovery documented via `/llms.txt` and `/llms-full.txt`.
   - Parallel-safe wiki editing strictly respected: edits confined to Sections 8, 9, and 10 of `Studio-Configuration-Reference.md`.
   - All 7 UI `StudioDocLink` and `FieldHelpHint` `docHref` anchors resolve via `slugifyAnchor()` with 0 broken links.

**Verdict: APPROVED.** All API contracts, schemas, security bounds, and operator procedures in KAN-414 are thoroughly verified and approved.

---

## 2. API Contract & Security Invariant Audit

### 2.1 Verified REST Endpoints
- **AI Providers & Token Budgets:**
  - `POST /api/v1/admin/ai-providers/probe-models`
  - `POST /api/v1/admin/ai-providers/test-connection`
  - `POST /api/v1/admin/ai-providers/order`
  - `POST /api/v1/admin/ai-providers/budgets`
- **Agent Definitions:**
  - `POST /api/v1/agent-definitions`
  - `POST /api/v1/agent-definitions/{id}:validate`
- **Remote mTLS Runners:**
  - `POST /api/v1/admin/agent-runners/enrollment-tokens`
  - `POST /api/v1/admin/agent-runners/{id}:revoke`
  - `WebSocket /api/v1/agent-runners/ws`
- **Onboarding Discovery:**
  - `GET /llms.txt`
  - `GET /llms-full.txt`

### 2.2 Security Invariants Verified
- **Hostile Wire Invariant:** Egress denial strictly enforced under `air_gap_mode = True` (HTTP 409 `AIR_GAP_EGRESS_DENIED`).
- **Walled Component Garden:** Multi-tenant RLS isolation verified (`FORCE ROW LEVEL SECURITY`).
- **Volatile State Sanitization:** Single-use enrollment tokens invalidated immediately upon consumption.

---

## 3. Automated Test Verification & Quality Gates

1. **Backend Pytest Suite (`kanban/tests/`)**:
   - **7/7 wiki sync tests passed in 0.13s** (`test_wiki_bundle_sync.py`).
   - Image parity verified with zero external image links and zero unreferenced orphans.

2. **Frontend Vitest Suite (`src/features/docs-center/`)**:
   - **71/71 tests passed across 2 suites in 6.42s** (`DocsCenter.test.tsx` and `DocsCenterImages.test.tsx`).
   - Branch coverage: **96.44%** (Statements 99.6%, Functions 100%, Lines 100%).
   - All 7 Slice-2 `docHref` anchors resolve cleanly to real heading elements.

3. **Build & Quality Pipeline**:
   - `scripts/check_no_dashes.py`: 0 Unicode dashes repository-wide and across all wiki chapters.
   - `tsc -b --noEmit`: 0 TypeScript errors.
   - `eslint . --max-warnings 0`: 0 warnings, 0 errors.
   - `vite build`: Clean production bundle in 1.25s.

---

## 4. Forensic QA Artifact Alignment

- QA Directory: `docs/qa/KAN-414/`
- Specialist Reviews:
  - `api-specialist-review.md`: **APPROVED** (`api-spec`)
  - `ui-specialist-review.md`: **APPROVED** (`ui-spec`)
- Forensic Artifacts:
  - `build-check.txt`: Exit code 0 across sync, dashes, typecheck, lint, and build.
  - `unit-test-results.txt`: Documents 7 Pytest and 71 Vitest tests with 96.44% branch coverage.
  - `wiki-diff.patch`: Patch of commit `5365cc5` across wiki chapters.
  - `screenshots/`: 12 multi-viewport PNG captures visually verified.

The documentation, endpoint schemas, and security controls for KAN-414 are robust, verified, and approved for release.
