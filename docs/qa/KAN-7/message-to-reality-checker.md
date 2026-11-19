# Forensic QA Verification Packet: KAN-7 ([KB-P3-AUDIT-01])

## 1. Executive Summary & Verification Context
- **Ticket ID:** KAN-7 ([KB-P3-AUDIT-01])
- **Branch:** `feat/KAN-7`
- **Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9`
- **Author:** `@b-kan7`
- **Status:** READY FOR REVIEW

This packet provides indisputable forensic proof for the four defects addressed in KAN-7:
1. `POST /api/v1/setup/claim` RLS Context Binding under `FORCE ROW LEVEL SECURITY`.
2. Headless setup token permissions, container initialization, and fallback persistence.
3. Recovery Code HTML5 pattern UnicodeSets (`/v` flag) `SyntaxError` resolution.
4. `SecondFactorStep` root container `data-testid="second-factor-step"` attribute.

---

## 2. Root Cause Analysis & Architectural Fixes

### Defect 1: Setup Claim RLS Context Binding (`kanban/auth/setup.py`)
- **Root Cause:** In `SetupBootstrapService.claim_initial_admin`, the database bootstrap was performed under an anonymous context (principal 0, workspace 0). `setup_consume_and_create_admin` creates the initial admin user, workspace, and local card credential in `kb_auth`. However, subsequent queries that verify the existence of the default project and insert into `objects` and `projects` were executing on the same session while the session was still bound to the anonymous context. Under PostgreSQL `FORCE ROW LEVEL SECURITY` on `objects` (`objects_insert_rls`), inserting rows without the principal and workspace RLS context failed.
- **Forensic Fix:** Immediately following `setup_consume_and_create_admin`, the returned `principal_id` and `workspace_id` are bound to the session via:
  ```python
  await bind_rls_context(
      session,
      RLSContext(principal_id=admin_principal_id, workspace_id=workspace_id),
  )
  ```
  This ensures all subsequent entity queries and inserts execute under valid authenticated workspace administrator credentials with full RLS authorization.

### Defect 2: Headless Setup Token Permissions & Fallback (`deploy/standalone/entrypoint.py`, `kanban/auth/setup.py`)
- **Root Cause:**
  1. In standalone single-container boot (`entrypoint.py`), `_PASSTHROUGH_ENV_VARS` did not include `KB_SETUP_TOKEN_FILE`. When `build_child_env` prepared the sanitized environment for the unprivileged `kanban_app` (UID 65532) process, any custom `KB_SETUP_TOKEN_FILE` was stripped.
  2. When running as root during standalone container boot, `/run/kanban` was either not created or owned by root with 0755 permissions, causing `kanban_app` (UID 65532) to fail with `PermissionError` when persisting the minted token.
  3. `SetupBootstrapService._persist_token` failed fatally if `/run/kanban` was unwritable.
- **Forensic Fix:**
  1. Added `"KB_SETUP_TOKEN_FILE"` to `_PASSTHROUGH_ENV_VARS` in `deploy/standalone/entrypoint.py`.
  2. In `entrypoint.py`, ensure `/run/kanban` is created and chowned to UID 65532 with mode `0o775` when `os.getuid() == 0`.
  3. In `SetupBootstrapService._persist_token`, wrapped persistence with graceful fallback candidates (`KB_DATA_DIR`, `KB_RUN_DIR`, `/var/lib/kanban/data`, `/var/lib/kanban`, and `tempfile.gettempdir()`) if `PermissionError` occurs on the primary path.

### Defect 3: Recovery Code HTML5 Pattern `/v` Regex Fix (`kanban/web/src/features/auth/SecondFactorStep.tsx`)
- **Root Cause:** In ECMAScript 2024 / Chromium UnicodeSets (`/v` flag), unescaped hyphens inside character classes `[...]` trigger a `SyntaxError: Invalid regular expression: Invalid character class` because `-` is a reserved operator for character set subtraction and intersection (e.g. `[A-Z--[Q]]`). The previous pattern attribute `^[A-Za-z0-9-]{8,32}$` or unescaped hyphen caused browser form validation engines or libraries compiling with `new RegExp(pattern, 'v')` to throw an unhandled `SyntaxError`.
- **Forensic Fix:** Updated the input pattern attribute in `SecondFactorStep.tsx` to:
  ```tsx
  pattern="[A-Za-z0-9\-]{8,32}"
  ```
  The escaped hyphen `\-` is valid both in standard regular expressions and under `/v` UnicodeSets mode. Added an explicit unit test verifying `expect(() => new RegExp(patternStr, 'v')).not.toThrow()`.

### Defect 4: SecondFactorStep Root testid (`kanban/web/src/features/auth/SecondFactorStep.tsx`)
- **Root Cause:** The root container element lacked `data-testid="second-factor-step"`, preventing reliable deterministic selection by automated end-to-end testing and QA inspection.
- **Forensic Fix:** Added `data-testid="second-factor-step"` to the outer wrapper `<div>` of `SecondFactorStep.tsx`.

---

## 3. Unit Test Results & Coverage Metrics

### Backend Coverage (`kanban/auth/setup.py` & `deploy/standalone/entrypoint.py`)
- Command: `uv run pytest kanban/tests/auth/test_setup.py tests/deploy/test_standalone_entrypoint.py -v --cov=kanban.auth.setup --cov=deploy.standalone.entrypoint --cov-branch --cov-report=term-missing`
- Result: **38 passed in 0.71s**
- Coverage for `kanban/auth/setup.py`:
  - **Statements:** 127/127 (**100%**)
  - **Branches:** 20/20 (**100%**)
  - **Missing lines:** None

### Frontend Coverage (`kanban/web/src/features/auth/SecondFactorStep.tsx`)
- Command: `(cd kanban/web && pnpm vitest run src/features/auth/SecondFactorStep.test.tsx --coverage --coverage.include='src/features/auth/SecondFactorStep.tsx')`
- Result: **19 passed in 1.65s**
- Coverage for `SecondFactorStep.tsx`:
  - **Statements:** 98.96%
  - **Branches:** 96.25% (exceeds `>= 95.10%` threshold)
  - **Functions:** 100.00%
  - **Lines:** 100.00%

### Code Quality & Static Analysis Checks
- `uv run ruff check`: **All checks passed (0 errors)**
- `uv run ruff format --check`: **All files formatted**
- `uv run mypy`: **Success: no issues found in 4 source files**
- `uv run lint-imports`: **Contracts: 2 kept, 0 broken**
- `pnpm --dir kanban/web typecheck`: **Exit code 0 (clean)**
- `pnpm --dir kanban/web lint`: **Exit code 0 (0 warnings, 0 errors)**
- `python3 -m scripts.check_no_dashes --all`: **Exit code 0 (zero em-dashes/en-dashes)**

---

## 4. Visual Evidence & Artifacts

All screenshot artifacts have been captured using Playwright across Desktop (1280x800) and Mobile (390x844) viewports in both Light and Dark themes:

1. **Setup Claim Screen:**
   - Light Desktop: [kan-7-setup-claim-light-desktop.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/screenshots/kan-7-setup-claim-light-desktop.png)
   - Dark Desktop: [kan-7-setup-claim-dark-desktop.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/screenshots/kan-7-setup-claim-dark-desktop.png)
   - Light Mobile: [kan-7-setup-claim-light-mobile.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/screenshots/kan-7-setup-claim-light-mobile.png)
   - Dark Mobile: [kan-7-setup-claim-dark-mobile.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/screenshots/kan-7-setup-claim-dark-mobile.png)

2. **Second Factor Recovery Code Screen:**
   - Light Desktop: [kan-7-second-factor-recovery-light-desktop.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/screenshots/kan-7-second-factor-recovery-light-desktop.png)
   - Dark Desktop: [kan-7-second-factor-recovery-dark-desktop.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/screenshots/kan-7-second-factor-recovery-dark-desktop.png)
   - Light Mobile: [kan-7-second-factor-recovery-light-mobile.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/screenshots/kan-7-second-factor-recovery-light-mobile.png)
   - Dark Mobile: [kan-7-second-factor-recovery-dark-mobile.png](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/screenshots/kan-7-second-factor-recovery-dark-mobile.png)

---

## 5. QA Artifact Inventory (`docs/qa/KAN-7/`)
- [build-or-typecheck.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/build-or-typecheck.txt)
- [unit-test-results.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/unit-test-results.txt)
- [git-diff.patch](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/git-diff.patch)
- [changed-files-manifest.txt](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/changed-files-manifest.txt)
- [message-to-reality-checker.md](file:///home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan7-7e7025e9/docs/qa/KAN-7/message-to-reality-checker.md)
- `screenshots/` (8 full-fidelity PNGs)
