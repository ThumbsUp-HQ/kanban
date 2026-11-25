# API Specialist Review: KAN-427 (Slice 5 Phase 2 Governance & Workflows Simplification)

**Ticket:** KAN-427 (`[SLICE-5-P2][KB-GOVERNANCE-SIMPLIFY]`)  
**Parent Epic:** KAN-425 (`[EPIC][SLICE-5-GOVERNANCE]`)  
**Auditor:** `api-spec` (API Architect & Security Auditor)  
**Status:** **APPROVED**  
**Date:** 2026-11-25  
**Worktree Base:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan427-3a52f19e`  
**Target Commit:** `feat/KAN-427-slice5-governance-simplify`  

---

## 1. Executive Summary & Verdict

This API Specialist Review audits the REST schemas, security contracts, dual-control cryptographic boundaries, and client integrations in **KAN-427: Simplify Workspace & Project Settings, Custom Fields & Workflows UI**.

The implementation in `feat/KAN-427-slice5-governance-simplify` enforces critical architectural invariants:
1. **Custom Field Script Boundaries & Tier Isolation**:
   - Accurately conveys Tier A (`Wasm` in-process runtime with zero external network egress) and Tier B (`nsjail` Linux namespace sandbox with network boundary controls).
   - In `CustomFieldDefinitionEditor.tsx`, computes reactive SHA-256 script hashes over normalized script source, metadata, and egress rules via `crypto.subtle.digest`.
   - In `EscalationApprovalPanel.tsx`, strictly respects dual-control approval policies, displaying cryptographic signature requirements (`ed25519` / `ecdsa`) and preventing unapproved script privilege escalation across Workspace and Server scopes.
2. **Workflow Hooks & Git Repo SSRF Guard**:
   - `AttachHookDialog.tsx` cleanly differentiates hook kinds (`sync_validator`, `sync_mutator`, `agent_interceptor`) and dispatches transitions strictly matching `POST /api/v1/projects/{project_id}/workflow-hooks`.
   - `GitRepoBindingsSection.tsx` enforces SSRF callouts prohibiting loopback / private IP bindings on repository URLs, and protects Personal Access Tokens (PATs) using `.kb-masked-api-key` masking and password manager suppression attributes (`data-1p-ignore="true"`, `autoComplete="off"`) with zero `input[type="password"]` elements.
3. **Workflow Transition Dry-Run Simulation**:
   - `DryRunDrawer.tsx` interacts with `POST /api/v1/projects/{project_id}/workflows/dry-run`, rendering before-and-after diff tables with precise field mutability breakdowns without committing changes to the universal object graph.
4. **Zero Database Migrations & Single Head Parity**:
   - All enhancements operate directly over existing database models with zero migration delta.
5. **Coverage & Quality Verification**:
   - The test suite executes 93 backend Pytest tests (85.09s) and 279 frontend Vitest tests (17.14s).
   - Vitest branch coverage is **96.08%** overall (with every touched file achieving >=95%: CustomFieldDefinitionEditor 97.01%, EscalationApprovalPanel 95.74%, PersonalSettingsPage 96.57%, ProjectSettingsPage 95.05%, WorkspaceSettingsPage 96.23%, AttachHookDialog 98.24%, DryRunDrawer 96.77%, GitRepoBindingsSection 95.34%).
   - All tests pass with 0 act(...) warnings, 0 key warnings, and the test suite exits 0 cleanly.

**Verdict: APPROVED.** Zero API contract drift, zero security bypasses, clean typing, and rock-solid architectural boundaries.

---

## 2. API Contract & Security Invariant Audit

### 2.1 Custom Fields & Script Escalation Approvals
- **Routes:**
  - `POST /api/v1/projects/{project_id}/custom-fields`
  - `POST /api/v1/workspaces/{workspace_id}/custom-fields`
  - `POST /api/v1/admin/custom-fields/approvals/{approval_id}/approve`
  - `POST /api/v1/admin/custom-fields/approvals/{approval_id}/reject`
- **Security Invariants:**
  - Hardened execution sandbox: Scripts run with ephemeral project-scoped tokens. Escalation to workspace or server scope requires explicit dual-control administrative approval.
  - Clean error handling for `NSJAIL_GATE_DENIED` and `AIR_GAP_EGRESS_DENIED`.

### 2.2 Workflow Hooks & Git Repository Bindings
- **Routes:**
  - `GET /api/v1/projects/{project_id}/workflow-hooks`
  - `POST /api/v1/projects/{project_id}/workflow-hooks`
  - `POST /api/v1/projects/{project_id}/workflows/dry-run`
  - `GET /api/v1/projects/{project_id}/git-bindings`
  - `POST /api/v1/projects/{project_id}/git-bindings`
- **Security Invariants:**
  - SSRF blocklists enforced on Git URLs.
  - Zero password input autofill leaks on PAT secrets.
  - Safe Dry-Run execution validating transition logic without mutating database state.

---

## 3. Automated Test Verification & Quality Gates

1. **Backend Test Suite (Pytest)**:
   - 93 tests passed in 85.09s across `test_workspace_settings.py`, `test_project_config.py`, `test_admin_trash_api.py`, `test_user_personal_settings.py`, `test_custom_fields_api.py`, `test_custom_field_approvals_api.py`, `test_standalone_nsjail_gate.py`, `test_workflow_hooks_api.py`, and `test_dry_run.py`.
   - 0 failures, 0 errors, 0 warnings.

2. **Frontend Test Suite (Vitest)**:
   - 279 passed across 10 test suites (`WorkspaceSettingsPage`, `ProjectSettingsPage`, `PersonalSettingsPage`, `CustomFieldDefinitionEditor`, `EscalationApprovalPanel`, `AttachHookDialog`, `DryRunDrawer`, `GitRepoBindingsSection`, `WorkflowStudioPage`).
   - 0 `act(...)` stderr warnings, 0 `key` warnings.
   - >=95% branch coverage achieved across all touched files (96.08% overall, 99.63% statements, 99.9% lines).

3. **Build & Static Analysis Pipeline**:
   - `ruff check`: All checks passed.
   - `mypy`: 0 issues found in 680 source files.
   - `tsc -b --noEmit`: 0 errors.
   - `eslint`: 0 warnings, 0 errors.
   - `vite build`: Succeeded in 1.22s.
   - `check_no_dashes.py`: 0 forbidden Unicode dashes found.

---

## 4. Forensic QA Artifact Alignment

- QA Directory: `docs/qa/KAN-427/`
- Specialist Reviews:
  - `api-specialist-review.md`: **APPROVED** (`api-spec`)
  - `ui-specialist-review.md`: **APPROVED** (`ui-spec`)
- Forensic Artifacts:
  - `build-check.txt`: All static tools exit 0 cleanly.
  - `unit-test-results.txt`: Documents 93 backend and 279 frontend tests.
  - `screenshots/`: 25 multi-viewport unclipped PNG captures.

The API architecture and security controls for KAN-427 are robust, sound, and approved.
