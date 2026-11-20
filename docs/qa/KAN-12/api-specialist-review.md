# API Specialist Review: KAN-12 (KB-P3-AUDIT-06)

- Ticket: KAN-12
- Title: [KB-P3-AUDIT-06] Sync Topbar Air-Gap Indicator on kb:system-status-changed, Hide Reset Password on Groups/Agents, Use Group @slug Handles, and Add #tab-* Hash Anchors (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-12`
- Branch: `main`
- Commit: `b3b0f4ba81f185fe96b5a19c72e2cf5a83a05fe3`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-12 on `main` at commit `b3b0f4ba`, incorporating concrete evidence from live full-stack R3 verification (`live-fullstack-proof.txt`), unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves four distinct operational, administrative, and reactive synchronization problems across administrative principal formatting, UI authorization guarding, real-time topbar system status synchronization, and deep-linkable tab navigation:
1. Reactive Topbar Air-Gap Sync (Problem 1): In `useSystemStatus.ts`, registers a window event listener for `kb:system-status-changed` (with strict unmount cleanup) that immediately invalidates query cache `['system', 'status']`. Saving Workspace Settings dispatches `kb:system-status-changed`, updating the topbar air-gap badge reactively without a full page reload.
2. Guard Reset Password on Groups/Agents (Problem 2): In `AuthStudioPage.tsx`, strictly restricts the Reset Password action button and its modal dialog to `principal.type === 'USER'`, completely hiding and disabling it for `GROUP` and `AGENT` principals where credential reset is semantically invalid.
3. Group `@slug` Handle Formatting (Problem 3): In `kanban/admin/principal_service.py`, implemented `_slugify_or_default()` in `get_principal_detail` and `_format_principal_entry`. Normalizes group display names (e.g., "DevOps Security Team") to clean human-readable handles (`@devops-security-team`) or falls back safely to `@group` / `@agent` / `@user`, eliminating internal RFC 4122 UUID leakage across `/api/v1/admin/principals` endpoints.
4. Workspace Settings Tab Anchors & Deep Linking (Problem 4): In `WorkspaceSettingsPage.tsx`, added `id="tab-general"`, `id="tab-members"`, and `id="tab-groups"` attributes and synchronized active tab state with `window.location.hash` across initial mount, hashchange events, and tab clicks.

All API contracts, security invariants, transaction boundaries, handle slugification rules, and test coverage requirements are verified and certified:
- Zero new runtime dependencies introduced (`Apache-2.0` stack only).
- Architectural compliance with `import-linter` unidirectional layering (`agent -> mcp -> kanban -> database`).
- Strict 0 em-dashes and en-dashes across code, tests, and documentation.
- High test coverage: 16/16 backend Pytest tests passing with 96% coverage on `kanban.admin.principal_service`. 100/100 frontend Vitest tests passing with >=95% coverage across all 6 touched components (including `Topbar.tsx` at 98.05% coverage and zero `act(...)` stderr warnings in `WorkspaceSettingsPage.test.tsx`).
- Live full-stack R3 verification confirms 100% pass across all 4 operational scenarios on containerized live environment `kanban-liveqa-1`.

---

## 2. Detailed Contract & Security Verification

### 2.1 Principal Handle Slugification & Anti-Leak Discipline (`kanban/admin/principal_service.py`)
- Problem: Group principals in `/api/v1/admin/principals` and `/api/v1/admin/principals/{id}` previously rendered handles as `@<UUID>`, leaking internal database UUIDs and violating human-readable handle standards.
- Implementation:
  ```python
  def _slugify_or_default(value: str | None, default: str) -> str:
      if not value:
          return default
      clean = value.strip().lstrip("@")
      if not clean or _RFC4122_UUID_REGEX.match(clean):
          return default
      slug = re.sub(r"[^a-z0-9._-]+", "-", clean.lower()).strip("-")
      return slug or default
  ```
  - In `get_principal_detail` and `_format_principal_entry`:
    - Checks `raw_principal` and `display_name` against `_RFC4122_UUID_REGEX`.
    - If valid non-UUID name: generates clean `@slug`.
    - If UUID or absent: defaults cleanly to `@group`, `@agent`, or `@user`.
- Test Verification: `kanban/tests/api/test_admin_principals.py` proves:
  - Group principals created with human names (e.g., "DevOps Security Team") output handle `@devops-security-team`.
  - Group principals with UUID display names output handle `@group` without leaking the raw UUID.
  - Agent principals output `@agent` or slugified handle.
  - User principals retain user handle or slugified display name.

### 2.2 Reset Password Authorization Guard (`AuthStudioPage.tsx`)
- In `AuthStudioPage.tsx`:
  - `isUser = principal.type === 'USER'`
  - Action button rendering:
    ```tsx
    {isUser && (
      <button
        type="button"
        className="auth-studio-btn auth-studio-btn-secondary"
        onClick={() => setResetPasswordTarget(principal)}
      >
        Reset Password
      </button>
    )}
    ```
  - Modal dialog strictly checks `resetPasswordTarget && resetPasswordTarget.type === 'USER'`.
  - Eliminates invalid password reset attempts for group and agent principals.

### 2.3 Reactive Topbar Air-Gap Indicator Synchronization (`useSystemStatus.ts`, `Topbar.tsx`, `WorkspaceSettingsPage.tsx`)
- Event Dispatch: When saving workspace settings in `WorkspaceSettingsPage.tsx`:
  ```tsx
  window.dispatchEvent(new CustomEvent('kb:system-status-changed'));
  queryClient.invalidateQueries({ queryKey: qk.systemStatus() });
  ```
- Event Listener: `useSystemStatus.ts` registers a window listener for `kb:system-status-changed` and cleans up on unmount, invalidating query key `['system', 'status']`.
- Topbar Rendering: `Topbar.tsx` (98.05% statement coverage, 95.37% branch, 100% lines) consumes `useSystemStatus()`, immediately rendering the `📴 Air-Gap Active` badge when `airgap_mode === true` without requiring page reload.

### 2.4 Workspace Settings Tab Anchors & Deep Linking (`WorkspaceSettingsPage.tsx`)
- Tab Buttons: `id="tab-general"`, `id="tab-members"`, `id="tab-groups"` with `data-testid="tab-..."`.
- Hash Synchronization:
  - On mount: parses `window.location.hash` and sets active tab accordingly.
  - On `hashchange` event: updates tab state dynamically.
  - On tab click: updates `window.location.hash` via `history.replaceState`.
- Zero `act(...)` stderr warnings across all 26 tests in `WorkspaceSettingsPage.test.tsx`.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt` - R3)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-12/live-fullstack-proof.txt` on target container `kanban-liveqa-1` (`http://localhost:18961`) at commit `b3b0f4ba`:
1. Problem 3 (Group @slug handle formatting & zero UUID leakage):
   - `GET /api/v1/admin/principals` -> HTTP 200 OK:
     - `Admin User` (User): handle `@admin`, role `SERVER_ADMIN`, provider `LOCAL`.
     - `DevOps Security Team` (Group): handle `@devops-security-team`, role `WORKSPACE_MEMBER`, provider `LOCAL`.
     - `Read Only Viewer` (User): handle `@viewer`, role `WORKSPACE_GUEST`, provider `LOCAL`.
     - `Triage Bot` (Agent): handle `@triage-bot`, role `WORKSPACE_MEMBER`, provider `LOCAL`.
2. Problem 2 (Guard reset password on groups and agents):
   - Auth Studio table rows (light):
     - `Admin User`: `resetButtonCount: 1`, `hasUuid: false`.
     - `DevOps Security Team`: `resetButtonCount: 0`, `hasUuid: false`.
     - `Read Only Viewer`: `resetButtonCount: 1`, `hasUuid: false`.
     - `Triage Bot`: `resetButtonCount: 0`, `hasUuid: false`.
   - Screenshots captured: `screenshots/live-kan12-auth-studio-groups-desktop-light.png` and `screenshots/live-kan12-auth-studio-groups-desktop-dark.png`.
3. Problem 1 (Reactive topbar air-gap sync zero reload):
   - Topbar right text before Air-Gap ON: `⚠️\n✕\n🔔\nA`.
   - Air-Gap ON sync frame check (NO reload): `tabGeneralInView: true`, `tabMembersInView: true`, `tabGroupsInView: true`, `airGapBadgeVisible: true`, `topbarRightText: "⚠️✕📴🔔A"`.
   - Screenshot: `screenshots/live-kan12-workspace-tabs-airgap-sync-desktop-light.png` (demonstrates `#tab-*` anchor and `📴` air-gap badge visible together without page reload).
   - Topbar Air-Gap badge cleared immediately after Air-Gap OFF (NO reload).
4. Problem 4 (Workspace settings hash anchor reset):
   - `#tab-groups` aria-selected=true, after `window.location.hash=""` -> `#tab-general` aria-selected=true.
5. Overall Stability: Console errors: 0, Page errors: 0, Server 5xx responses: 0. `LIVE_STACK_VERDICT: PASS`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suite (`unit-test-results.txt`):
  - `kanban/tests/api/test_admin_principals.py`: 16 passed in 19.99s.
  - Coverage: `kanban/admin/principal_service.py` achieves 96% statement coverage (429 stmts, 9 miss, 160 branch, 14 brpart).
- Frontend Vitest Suites (`unit-test-results.txt`):
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4 passed.
  - `src/features/system/useSystemStatus.test.tsx`: 1 passed.
  - `src/app/useSystemStatus.test.tsx`: 4 passed.
  - `src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx`: 26 passed (0 act warnings).
  - `src/app/Topbar.test.tsx`: 23 passed.
  - `src/features/admin-auth/AuthStudioPage.test.tsx`: 42 passed.
  - Total: 100 passed in 11.86s across 6 test suites.
  - Overall coverage: 98.81% stmts, 95.32% branch, 99.48% funcs, 100% lines.
  - `Topbar.tsx`: 98.05% stmts, 95.37% branch, 100% funcs, 100% lines.
  - `WorkspaceSettingsPage.tsx`: 99.67% stmts, 95.09% branch, 100% funcs, 100% lines.
  - `AuthStudioPage.tsx`: 98.31% stmts, 95.43% branch, 99% funcs, 100% lines.
  - `useSystemStatus.ts`: 100% across all metrics.
- Static Analysis (`build-or-typecheck.txt`):
  - `uv run ruff check .`: Clean (All checks passed).
  - `uv run mypy`: Clean (Success: no issues found in 1 source file).
  - `uv run lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `pnpm --dir kanban/web typecheck` (`tsc -b`): Clean (0 errors).
  - `pnpm --dir kanban/web lint` (`eslint`): Clean (0 warnings).
  - `pnpm --dir kanban/web build` (`vite build`): Clean in 1.73s (0 errors).
  - `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes found).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Group Slugification | Group handles formatted as `@slug` | `_slugify_or_default()` in `principal_service.py` | PASS |
| UUID Leakage Prevention | Raw database UUIDs never used as handles | RFC 4122 regex check with `@group` / `@agent` fallback | PASS |
| Non-User Reset Guard | Reset Password hidden for groups & agents | `principal.type === 'USER'` check in `AuthStudioPage` | PASS |
| Air-Gap Reactive Sync | Immediate indicator sync without full reload | `kb:system-status-changed` event and listener | PASS |
| Unmount Listener Cleanup | Zero memory leaks or dangling event handlers | React `useEffect` returns removeEventListener cleanup | PASS |
| Tab Anchor Deep Linking | Tabs mapped to URL hash (`#tab-*`) | `id="tab-*"` and hashchange synchronization | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API routes, admin principal formatting rules, credential authorization guards, reactive system status sync handlers, and unit test suites for KAN-12 on `main` at commit `b3b0f4ba` have been thoroughly audited, verified against live container `kanban-liveqa-1`, and certified. Ready for Clean-Room Reality-Checker QA.
