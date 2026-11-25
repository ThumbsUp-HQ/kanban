# API Specialist Review: KAN-426

**Ticket:** `KAN-426` (`[SLICE-5-P1][KB-GOVERNANCE-AUDIT] Phase 1: Workspace/Project Settings, Custom Scripted Fields & Workflows Setting Inventory & Audit`)  
**Reviewer:** `@api-spec` (Backend Architect & API Security Specialist)  
**Branch:** `fix/KAN-426-rc1`  
**Base Commit:** `620f66cd`  
**Status:** `APPROVED`  
**Date:** 2026-11-25  

---

## 1. Scope & Technical Architecture Evaluation

This Phase 1 audit reviewed 100% of the backend API endpoints, validation boundaries, and data models governing Slice 5 across 9 backend modules:
1. **Workspace Governance (`kanban/api/v1/admin/workspace_settings.py`):**
   - Endpoints: `GET /api/v1/admin/workspace-settings` and `PATCH /api/v1/admin/workspace-settings`.
   - Security Invariant: Protected by `require_workspace_or_server_admin` ensuring only authenticated administrators with workspace or server authority can mutate governance policies.
   - Validation Bounds: Verified that `session_idle_timeout_min` is strictly bounded to `5 <= timeout <= 720` minutes (8 hours) and `session_absolute_timeout_min` to `60 <= timeout <= 10080` minutes (7 days). Retention days bounded to `7 <= days <= 365`.
2. **2-Stage Destructive Deletion Engine (`kanban/api/v1/admin/destructive.py`):**
   - Endpoints: `POST /admin/destructive:request`, `POST /admin/destructive:execute`, `POST /admin/destructive:restore`, `GET /admin/trash`, and `POST /admin/trash/{id}:restore`.
   - Security Invariant: Enforces a 2-stage tokenized handshake. Stage 1 generates a cryptographically signed confirmation token and blast radius summary (counting all child entities: issues, stickies, docs, modules, cycles). Stage 2 requires typing the exact confirmation phrase plus a mandatory audit justification reason before destructive purge executes.
3. **Project Lifecycle Configuration (`kanban/api/v1/project_config.py`):**
   - Endpoints: CRUD routes for `/states`, `/priorities`, and `/labels`.
   - Safety Invariant: Pre-deletion audit impact checks (`/states/{id}/audit-impact` and `/labels/{id}/audit-impact`) ensure states or labels cannot be deleted while assigned to active issues without designating a replacement target and migrating workflow hooks.
4. **Custom Scripted Fields & Sandbox Execution (`kanban/api/v1/custom_fields.py`, `custom_field_approvals.py`, `custom_field_execution.py`):**
   - Dual-Control Escalation: When a custom field requests `workspace` or `server` scope or escalated credentials, `custom_field_approvals.py` strictly prevents self-approval by the field author. A distinct administrator must sign off with AAL2 step-up verification.
   - Cryptographic Manifest Integrity: Any mutation to `script_source` changes the computed SHA256 manifest hash, automatically invalidating prior approvals and resetting target scope to `project`.
   - Execution Sandboxing: Verified `_execute_rate_limiter` and sandboxed execution boundaries (Tier A WebAssembly vs Tier B nsjail container isolation).
5. **Workflow Transition Hooks & Dry-Run Simulation (`kanban/api/v1/workflow_hooks.py`):**
   - Safety Invariant: The dry-run endpoint (`POST /projects/{project}/workflow-hooks/dry-run`) executes transition hooks under a transactional `ROLLBACK` savepoint isolation harness, ensuring zero database side-effects during simulation.
   - Capability Whitelist: Hooks are restricted to mutating only explicitly permitted fields (`summary`, `description`, `priority`, `labels`, `custom_fields`).
6. **Git Repository Bare Mirror Bindings (`kanban/api/v1/repo_bindings.py`):**
   - SSRF Protection: The endpoint strictly validates remote URLs against private, loopback, and cloud metadata IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.1`, `169.254.169.254`).
   - Access Mode: Hardcoded to `bare_mirror_ro` (strict read-only bare mirror), ensuring no push credentials or destructive remote git operations are possible. Credentials stored encrypted using server Key Encryption Key (KEK).
7. **User Profile & Identity Security (`kanban/api/v1/user_settings.py`):**
   - Avatar Upload: Enforces max 2 MiB file size, MIME-type inspection, and secure storage in the local blob store.
   - Password Rotation: Requires current password re-verification, minimum complexity, and rate limiting.

---

## 2. Setting-by-Setting Backend Mapping Audit

The inventory table in `docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md` accurately maps 100% of the UI controls to their authoritative backend endpoints:
- Workspace Settings: 15 controls mapped to `admin/workspace_settings.py` and `admin/destructive.py`.
- Project Settings: 28 controls mapped to `project_config.py` and `admin/destructive.py`.
- Personal Settings: 20 controls mapped to `user_settings.py`, `auth_webauthn.py`, and `auth_mfa.py`.
- Custom Fields: 20 controls mapped to `custom_fields.py`, `custom_field_approvals.py`, and `custom_field_execution.py`.
- Workflows: 26 controls mapped to `workflow_hooks.py` and `repo_bindings.py`.

The proposed simplifications (e.g. presets for timeouts, client-side WIP validation, structured format metadata form) preserve full API payload parity and introduce zero breaking schema changes.

---

## 3. Specialist Verdict

The Phase 1 inventory and simplification proposals in `01-audit-and-cuts.md` are comprehensive, mathematically sound, and maintain zero-trust security invariants.

**Verdict: APPROVED**
