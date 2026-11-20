# Reality-Checker Forensic Audit Report: KAN-7

- **Ticket:** KAN-7 (`[KB-P3-AUDIT-01] Fix Setup Claim RLS Context Binding, Headless Setup Token Permissions, Recovery Code /v Regex, and SecondFactorStep Test ID (4 Problems)`)
- **Auditor:** Isolated Clean-Room `reality-checker` Subagent (`f7101dd0-cbd1-41c7-b6ed-9abfca37e913`)
- **Overall Quality Grade:** **A**
- **Production Readiness Verdict:** **READY**

---

## 1. Forensic Evidence Packet Verification

All 8 text proof files and all 12 live screenshot PNGs in `/home/adamoutler/kanban/docs/qa/KAN-7/` were directly inspected, along with the target implementation files on disk:

- `docs/qa/KAN-7/git-diff.patch` (2,994 lines across 15 code/test files)
- `docs/qa/KAN-7/changed-files-manifest.txt` (SHA-256 manifest of 17 code/test files and 12 live PNGs)
- `docs/qa/KAN-7/unit-test-results.txt` (46 Pytest + 134 Vitest tests with coverage tables)
- `docs/qa/KAN-7/build-or-typecheck.txt` (mypy, ruff check, ruff format, lint-imports, tsc, eslint, vite build, check_no_dashes)
- `docs/qa/KAN-7/live-fullstack-proof.txt` (Zero-mock live container run against `http://localhost:18951`)
- `docs/qa/KAN-7/api-specialist-review.md` (`STATUS: APPROVED` by `api-spec-2`)
- `docs/qa/KAN-7/ui-specialist-review.md` (`STATUS: APPROVED` by `ui-spec-2`)
- `docs/qa/KAN-7/message-to-reality-checker.md`

---

## 2. Definition of Done Compliance Matrix

### Requirement 1: `kanban/auth/setup.py` (RLS Context Binding & Token Persistence Fallback) - PASS
- `SetupBootstrapService.claim_initial_admin` normalizes `principal_id` and `workspace_id` to `uuid.UUID` and invokes `await bind_rls_context(session, RLSContext(principal_id=admin_principal_id, workspace_id=admin_workspace_id))` immediately after `kb_auth.setup_consume_and_create_admin(...)` and prior to `UPDATE workspaces`, `SELECT id FROM projects`, `INSERT INTO objects`, and `INSERT INTO projects` under PostgreSQL `FORCE ROW LEVEL SECURITY`.
- `mint_token_if_uninitialized` reads `KB_SETUP_TOKEN_FILE` (default `/run/kanban/setup_token`) and delegates to `_persist_token`, which writes with `0o600` permissions, catches `PermissionError` on the primary destination, and falls back sequentially across `KB_DATA_DIR/setup_token`, `KB_RUN_DIR/setup_token`, `/var/lib/kanban/data/setup_token`, `/var/lib/kanban/setup_token`, and `tempfile.gettempdir()` paths (also `0o600`).
- **Unit Test Coverage:** `kanban/auth/setup.py` achieves **100%** coverage (127 stmts, 0 miss, 20 branches, 0 partial).

### Requirement 2: `deploy/standalone/entrypoint.py` (Passthrough Env, `/run/kanban` UID 65532 Permissions, >=95% Coverage) - PASS
- `"KB_SETUP_TOKEN_FILE"` added to `_PASSTHROUGH_ENV_VARS`; creates `/run/kanban` and executes `shutil.chown(str(run_kanban_dir), user=65532, group=65532)` and `run_kanban_dir.chmod(0o775)` when running as root.
- **Live Container Proof:** `docker exec kanban-liveqa-1 stat /run/kanban/setup_token` returned `Access: (0600/-rw-------) Uid: (65532/kanban) Gid: (65532/kanban)`.
- **Unit Test Coverage:** `deploy/standalone/entrypoint.py` achieves **99%** coverage (286 stmts, 0 miss, 72 branches, 5 partial). Combined Pytest suite: **46 passed** (99% combined coverage).

### Requirement 3: `kanban/web/src/features/auth/SecondFactorStep.tsx` (`/v` Regex, `data-testid`, Single Card, Zero Inline Styles) - PASS
- `pattern="[A-Za-z0-9\-]{8,32}"` compiles cleanly under `new RegExp(patternStr, 'v')` without throwing `SyntaxError` and verified live in Chromium during Recovery Code login.
- Root container declares `data-testid="second-factor-step"`, zero `style={{...}}` inline style props, single `.auth-panel` card shell (`authPanels=1, nestedAuthPanels=0`).

### Requirement 4: Fail-Closed `AppShell.tsx`, `useSessionGuard.ts`, and `RealtimeProvider` - PASS
- `useSessionGuard.ts` initializes to `status: 'checking'` on protected routes; `AppShell.tsx` gates `useRealtimeSubscription` and `meQuery` on `isAuthReady`, rendering minimal `<div className="kb-app-shell" data-testid="app-shell-auth-loading" />` placeholder when `!isAuthReady`; `RealtimeProvider` and `RealtimeClient` block connections whenever `!isSessionAllowed()`.

### Requirement 5: Coverage, Static Checks, Dual Reviews, Punctuation, Zero-Mock Live Proof, and Screenshots - PASS
- **Vitest Coverage:** 7 test files, **134 passed** - **99.29%** Stmts, **96.30%** Branch, **100%** Funcs, **99.71%** Lines (`cssTokensAudit.test.ts` 4/4 passed).
- **Static Checks:** `mypy` (0 issues in 1094 files), `ruff check`, `ruff format`, `lint-imports` (2 kept, 0 broken), `tsc -b --noEmit` (0 errors), `eslint` (0 errors/warnings), `vite build` (1.11s), `check_no_dashes` (0 em/en-dashes).
- **Zero-Mock Live Full-Stack Proof:** Pre-claim `GET /`, unauthenticated `GET /`, and `mfa_pending` `GET /` all produced `0` `401`s, `0` WS/SSE attempts, `0` `console.error`, `0` `pageerror`; container logs (101 lines) had `0` occurrences of `401`, `403`, `404`, or `500`.

---

## 3. Final Certification

- **Grade:** **A**
- **Status:** **READY**
- **Assessment:** All 4 scoped defects, fail-closed `AppShell`/`useSessionGuard`/`RealtimeProvider` gating, `>=95%` unit test coverage mandates, static checks, dual specialist reviews, zero-mock live container proof, and 12 live visual proofs pass without defects or gaps. Approved for KAN-7 closure and merge.
