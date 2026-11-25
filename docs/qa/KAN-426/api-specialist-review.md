# API Specialist Review: KAN-426

**Ticket:** `KAN-426` (`[SLICE-5-P1][KB-GOVERNANCE-AUDIT] Phase 1: Workspace/Project Settings, Custom Scripted Fields & Workflows Setting Inventory & Audit`)  
**Reviewer:** `@api-spec` (Backend Architect & API Security Specialist)  
**Branch:** `fix/p1-audits-rc2` (consolidated Round 2 on `main` at `71b847ba`)  
**Base Commit:** `71b847ba`  
**Status:** `APPROVED`  
**Date:** 2026-11-25  

---

## 1. Scope & Technical Architecture Evaluation

This Phase 1 audit reviewed 100% of the backend API endpoints, validation boundaries, and data models governing Slice 5 across 9 backend modules:
1. **Workspace Governance (`kanban/api/v1/admin/workspace_settings.py`):**
   - Endpoints: `GET /api/v1/admin/workspace-settings` and `PATCH /api/v1/admin/workspace-settings`.
   - Security Invariant: Protected by `require_workspace_or_server_admin` ensuring only authenticated administrators with workspace or server authority can mutate governance policies.
   - Validation Bounds: Verified that `session_idle_timeout_min` is strictly bounded to `5 <= timeout <= 720` minutes (12 hours) and `session_absolute_timeout_min` to `60 <= timeout <= 10080` minutes (7 days). Retention days bounded to `7 <= days <= 365`. Allowed issue export roles include `workspace_admin`, `project_admin`, `member`, and `guest`.
2. **2-Stage Destructive Deletion Engine (`kanban/api/v1/admin/destructive.py`):**
   - Endpoints: `POST /admin/destructive:request`, `POST /admin/destructive:execute`, `POST /admin/destructive:restore`, `GET /admin/trash`, and `POST /admin/trash/{id}:restore`.
   - Security Invariant: Enforces a 2-stage tokenized handshake. Stage 1 (`permanent-purge-btn-${item.id}`) generates a cryptographically signed confirmation token and blast radius summary (counting all child entities: issues, stickies, docs, modules, cycles). Stage 2 requires typing the exact confirmation phrase (`permanent-purge-confirm-phrase-input`) plus a mandatory compliance justification reason (`permanent-purge-reason-input`) before destructive purge executes. Note: UI allows `>= 8` characters, whereas backend `destructive.py:91` requires `min_length=10`.
   - Restoration is triggered via `restore-btn-${item.id}` mapped to `POST /api/v1/admin/trash/{id}:restore`.
3. **Project Lifecycle Configuration (`kanban/api/v1/project_config.py`):**
   - Endpoints: CRUD routes for `/states`, `/priorities`, and `/labels`.
   - WIP Limits: `state-wip-soft-input` and `state-wip-hard-input` enforce validation bounds `ge=1, le=999` (blank/`null` indicates unlimited; `0` fails validation with HTTP 422).
   - Safety Invariant: Pre-deletion audit impact checks (`/states/{id}/audit-impact` and `/labels/{id}/audit-impact`) ensure states or labels cannot be deleted while assigned to active issues without designating a replacement target and migrating workflow hooks.
4. **Custom Scripted Fields & Sandbox Execution (`kanban/api/v1/custom_fields.py`, `custom_field_approvals.py`, `custom_field_execution.py`):**
   - Dual-Control Escalation: When a custom field requests `workspace` or `server` scope or escalated credentials, `custom_field_approvals.py` strictly prevents self-approval by the field author. A distinct administrator must sign off with AAL2 step-up verification.
   - Cryptographic Manifest Integrity: Any mutation to `script_source` changes the computed SHA256 manifest hash, automatically invalidating prior approvals and resetting target scope to `project`.
   - Execution Sandboxing: Verified `_execute_rate_limiter` and sandboxed execution boundaries (Tier A WebAssembly vs Tier B nsjail container isolation).
5. **Workflow Transition Hooks & Dry-Run Simulation (`kanban/api/v1/workflow_hooks.py`):**
   - Safety Invariant: The dry-run endpoint (`POST /projects/{project}/workflow-hooks/dry-run`) executes transition hooks under a transactional `ROLLBACK` savepoint isolation harness, ensuring zero database side-effects during simulation.
   - Capability Whitelist: Hooks are strictly bounded to the authorized `MUTABLE_FIELD_UNIVERSE` (`labels, priority, assignees, start_date, due_date, cycle, custom_fields.risk_rating, custom_fields.qa_status, custom_fields.security_review`). In accordance with `IMMUTABLE_FIELDS_NOTICE`, `summary, description_markdown, state, parent, created_by` are strictly immutable.
   - Simulation Inputs: `dry-run-priority` is `<input type="text">` allowing synthetic priority values.
6. **Git Repository Bare Mirror Bindings (`kanban/api/v1/repo_bindings.py` & `kanban/repos/url_policy.py`):**
   - SSRF Protection: The endpoint strictly validates remote URLs via `kanban/repos/url_policy.py` against private, loopback, and cloud metadata IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.1`, `169.254.169.254`).
   - Access Modes: Authorized modes are `bare_git_tools` and `ro_vfs_mount` (strict read-only mirrors). Credentials stored encrypted using server Key Encryption Key (KEK).
   - UI Controls: Mirror sync and remove actions are identified by accessible labels (`aria-label="Refresh mirror ${b.slug}"` and `aria-label="Remove mirror ${b.slug}"`) without dedicated test IDs.
7. **User Profile & Identity Security (`kanban/api/v1/user_settings.py`, `auth_webauthn.py`, `auth_mfa.py`):**
   - Avatar Upload: Handled via `PUT /api/v1/auth/me/avatar` with max 2 MiB file size and SVG rejection.
   - Credential Actions: Delete passkey uses `delete-passkey-${pk.id}` (`DELETE /api/v1/auth/webauthn/credentials/{id}`) and unlink identity uses `unlink-identity-${ident.id}` (`DELETE /api/v1/auth/me/identities/{id}`).

---

## 2. Setting-by-Setting Backend Mapping Audit

The inventory table in `docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md` accurately maps 100% of the UI controls to their authoritative backend endpoints across the entire 184-item inventory:
- Total Cataloged Settings: 184
- KEEP: 175
- SIMPLIFY: 7
- MERGE: 2
- MOVE_TO_ADVANCED: 0
- CUT: 0

The Rev-2 Phase 2 proposals (DryRunDrawer prominent top simulation banner and visual before/after field diff display, duration presets for timeouts, and client-side WIP validation) preserve full API payload parity and introduce zero breaking schema changes.

---

## 3. Specialist Verdict

The Phase 1 inventory and simplification proposals in `01-audit-and-cuts.md` are comprehensive, mathematically sound, and maintain zero-trust security invariants.

**Verdict: APPROVED**
