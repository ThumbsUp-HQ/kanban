# Slice-5 Epic KAN-425 Rollup Verification Guide & Forensic QA Manifest

## 1. Executive Summary & Epic Scope

- **Epic Ticket:** `KAN-425` (`[EPIC][SLICE-5-WORKSPACE-PROJECT-WORKFLOWS]`)
- **Execution Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan429-cf10d648`
- **Git Branch:** `docs/KAN-429-slice5-governance-docs`
- **Base Commit:** `1bbc9981`
- **Target Surfaces:**
  - Workspace Settings Studio & Trash Retention Policy (`/workspaces/:ws/settings`)
  - Project Settings Studio, WIP Limits & Lifecycle States (`/projects/:proj/settings`)
  - User Personal Settings, TOTP MFA, Passkeys & Session Management (`/settings/personal`)
  - Custom Fields Studio, 4 Flavors, 7 Output Formats & Sandbox Gating (`/projects/:proj/settings/custom-fields`)
  - Escalation Approval Panel & Dual-Control Step-Up Elevation (`/admin/custom-fields/approvals`)
  - Scripted Workflow Studio, Hook Pipelines & Failure Policies (`/projects/:proj/settings/workflows`)
  - Read-Only Bare Git Repository Mirror Bindings (`/projects/:proj/settings/workflows` git repo section)
  - In-App Help & Documentation Center (`/docs` with offline Wiki Bundle)

---

## 2. 4-Phase Lifecycle & Deliverables Traceability

| Phase | Ticket | Title | Status | Key Artifacts & Proof |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 1** | `KAN-426` | Audit, Inventory & Cuts Blueprint | **Grade-A READY** | `docs/workouts/slice-5-workspace-project-workflows/01-audit-and-cuts.md` |
| **Phase 2** | `KAN-427` | UI Simplification & Backend Wiring | **Grade-A READY** | `docs/workouts/slice-5-workspace-project-workflows/02-implemented-changes.md` |
| **Phase 3** | `KAN-428` | Live Container Workouts & Zero-Mock Proof | **Grade-A READY** | `docs/workouts/slice-5-workspace-project-workflows/03-live-workout-report.md`, 43 PNG screenshots (Merged `9e3fcbf7`) |
| **Phase 4** | `KAN-429` | In-App Docs Sync, Wiki Chapters & Runbooks | **Grade-A READY** | `docs/workouts/slice-5-workspace-project-workflows/04-published-docs-manifest.md`, 30 PNG screenshots |

---

## 3. Automated Unit Testing & Coverage Metrics

### A. Backend Pytest Test Suite (`docs/qa/KAN-425/unit-test-results.txt`)
Executed via:
```bash
PYTHONPATH=. uv run --no-sync python -m pytest \
  kanban/tests/api/test_workspace_settings.py \
  kanban/tests/api/test_project_config.py \
  kanban/tests/api/test_admin_trash_api.py \
  kanban/tests/api/test_user_personal_settings.py \
  kanban/tests/api/test_agent_onboarding_preferences.py \
  kanban/tests/custom_fields/test_custom_fields_api.py \
  kanban/tests/custom_fields/test_custom_field_approvals_api.py \
  kanban/tests/custom_fields/test_execution_api.py \
  kanban/tests/workflows/test_workflow_hooks_api.py \
  kanban/tests/workflows/test_dry_run.py \
  kanban/tests/repos/test_repo_bindings_api.py \
  kanban/tests/test_wiki_bundle_sync.py \
  kanban/tests/test_docs_custom_fields_guide.py \
  --cov=kanban --cov-config=scripts/coverage_slice5.ini --cov-report=term-missing
```

- **Execution Results:** **128 passed in 115.07s** (0 failures, 0 errors, 0 warnings).
- **Core Touched Modules Coverage (100% >=95% Threshold):**
  - `kanban/api/v1/admin/destructive.py`: **95%** (133 stmts, 4 miss, 26 branch, 4 brpart)
  - `kanban/api/v1/admin/workspace_settings.py`: **96%** (187 stmts, 2 miss, 68 branch, 8 brpart)
  - `kanban/api/v1/custom_field_approvals.py`: **100%** (24 stmts, 0 miss)
  - `kanban/api/v1/custom_field_execution.py`: **95%** (104 stmts, 1 miss, 22 branch, 5 brpart)
  - `kanban/api/v1/custom_fields.py`: **100%** (30 stmts, 0 miss)
  - `kanban/api/v1/project_config.py`: **100%** (74 stmts, 0 miss)
  - `kanban/api/v1/repo_bindings.py`: **95%** (184 stmts, 6 miss, 38 branch, 6 brpart)
  - `kanban/api/v1/user_settings.py`: **95%** (408 stmts, 15 miss, 118 branch, 11 brpart)
  - `kanban/api/v1/workflow_hooks.py`: **100%** (52 stmts, 0 miss)
  - **TOTAL:** **96%** coverage across all 1,196 statements and 272 branches (all 9 touched modules >=95%).

### B. Frontend Vitest Test Suite (`docs/qa/KAN-425/unit-test-results.txt`)
Executed via:
```bash
cd kanban/web && COVERAGE_INCLUDE="src/features/custom-fields/**,src/features/workflows/**,src/features/settings/**,src/features/docs-center/**" npx vitest run \
  src/features/custom-fields/ \
  src/features/workflows/ \
  src/features/settings/ \
  src/features/docs-center/ \
  --coverage
```

- **Execution Results:** **744 passed across 35 test files in 22.23s** (0 failed). Zero `act(...)` stderr warnings.
- **V8 Coverage Breakdown (all >=95% branch threshold):**
  - `All files`: **99.57% Statements, 96.77% Branch, 99.62% Functions, 99.86% Lines**
  - `custom-fields`: **99.69% Stmts, 96.89% Branch, 100% Lines**
  - `settings`: **99.56% Stmts, 96.40% Branch, 99.85% Lines**
  - `workflows`: **99.48% Stmts, 98.64% Branch, 99.64% Lines**
  - `docs-center`: **99.60% Stmts, 96.44% Branch, 100% Lines**

### C. Playwright Multi-Viewport Visual Suite (`docs/qa/KAN-425/unit-test-results.txt`)
- **Execution Results:** **1 passed in 50.2s**
- **Verified Invariants:** Zero horizontal scrollbars at 390px, 768px, 1024px, 1440px across all target chapters. Non-zero `naturalWidth` on all embedded images. Port 18429 cleanly released.

---

## 4. Visual Proof Catalog (73 PNG Artifacts in `docs/qa/KAN-425/screenshots/`)

The rollup screenshot catalog contains 73 unique, unclipped, multi-viewport PNG artifacts:
- **Live Workout Screenshots (43 artifacts from KAN-428):**
  - Workspace Settings: General, Nested Groups, Trash Retention (`01..02`, 5 viewports)
  - Project Settings: Priorities, WIP Limits, Danger Zone Lifecycle (`03..05`, 5 viewports)
  - Personal Settings: Profile, Password, Passkeys, TOTP, Avatar Crop (`08`, 5 viewports)
  - Custom Fields Studio: Presets, Editor, Format Selector, Escalation Dual-Control Panel (`09..14`, 5 viewports)
  - Workflow Transition Studio: Pipeline, Attach Hook Dialog, Dry-Run Drawer, Git Repo Bindings (`15..18`, 5 viewports)
- **Docs Center Screenshots (30 artifacts from KAN-429):**
  - Docs Center Home: Light and Dark themes (`00`, 1440x900)
  - Admin Custom Scripted Fields & Sandbox (`01`, 5 viewports)
  - Guide: How to Use Custom Fields (`02`, 5 viewports)
  - Scripted Workflows & Transition Helpers (`03`, 5 viewports)
  - Zero Trust Security & Access Visibility (`04`, 5 viewports)
  - Studio Configuration Reference (`05`, 5 viewports)
  - Scrolled Views: Embedded KAN-428 Images, Custom Fields Table, Workflow Transition Studio Table (`06..08`, 1440x900)

---

## 5. Static Quality Gates & Operational Invariants

1. **Database Migrations:** Checked via `kanban-ctl db check-migrations --static-only`. Single head `p6_22_mcp_api_keys_capability_mask_boundary` verified. Zero unapplied or branching migrations.
2. **Static Linters:** `ruff check kanban/` clean (0 errors), `tsc` clean (0 errors), `eslint` clean (0 warnings).
3. **Plain ASCII Directives:** `python3 scripts/check_no_dashes.py --all` exit code 0. Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`).
4. **Offline Wiki Bundle:** 34 chapters synced into `kanban/web/src/features/docs-center/wikiManifest.ts` (617,869 bytes, 145 images copied).
5. **Pre-Production Protection:** Zero destructive operations, mutations, or data alterations against `192.168.1.101` / `k.hackedyour.info`.
6. **Clean Port Teardown:** Local test database destroyed (`make testdb-down`). Loopback ports 18428 and 18429 verified 100% free.

---

## 6. Manifest and Verification

All files in `docs/qa/KAN-425/` and `docs/qa/KAN-429/` are registered with SHA-256 checksums in `changed-files-manifest.txt` and verify cleanly (`sha256sum -c`).
Target commit: `HEAD` on `docs/KAN-429-slice5-governance-docs`.
Ready for clean-room reality-checker Grade-A `READY` audit.
