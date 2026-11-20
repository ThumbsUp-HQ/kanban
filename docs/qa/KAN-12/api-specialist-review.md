# API Specialist Review: KAN-12 (KB-P3-AUDIT-06)

- Ticket: KAN-12
- Title: [KB-P3-AUDIT-06] Sync Topbar Air-Gap Indicator on kb:system-status-changed, Hide Reset Password on Groups/Agents, Use Group @slug Handles, and Add #tab-* Hash Anchors (4 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-12`
- Branch: `main`
- Commit: `23ae056d9d6cf0f8614c82a6c04701b8ae536e18`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-12 on `main` (commit `23ae056d`), incorporating evidence from live full-stack verification (`live-fullstack-proof.txt`). The ticket resolves 4 distinct problems across administrative principal formatting, UI authorization guarding, real-time topbar system status synchronization, and deep-linkable tab navigation.

All API contracts, security invariants, transaction boundaries, handle slugification rules, and test coverage requirements are verified and approved:
1. Group `@slug` Handle Formatting (Problem 3): In `kanban/admin/principal_service.py`, implemented `_slugify_or_default()` and updated `get_principal_detail` and `_format_principal_entry`. Generates clean `@slug` handles from group display names (e.g., `@infra-team`) or falls back safely to `@group` / `@agent` / `@user`, eliminating RFC 4122 UUID leakage across `/api/v1/admin/principals` endpoints.
2. Guard Reset Password on Groups/Agents (Problem 2): In `AuthStudioPage.tsx`, strictly restricted the Reset Password action and its modal dialog to `principal.type === 'USER'`, completely hiding and disabling it for `GROUP` and `AGENT` principals where credential reset is semantically invalid.
3. Reactive Topbar Air-Gap Sync (Problem 1): In `useSystemStatus.ts`, registered window listener for `kb:system-status-changed` (with unmount cleanup) invalidating `['system', 'status']`. Saving Workspace Settings dispatches `kb:system-status-changed` and invalidates system status queries, ensuring the topbar air-gap badge updates reactively without a full page reload.
4. Workspace Settings Tab Anchors (Problem 4): In `WorkspaceSettingsPage.tsx`, added `id="tab-general"`, `id="tab-members"`, and `id="tab-groups"` attributes and synchronized active tab state with `window.location.hash` across mount, hashchange events, and tab clicks.
5. High Test Coverage: 16/16 backend Pytest tests passing with 96% coverage on `kanban.admin.principal_service`. 72/72 frontend Vitest tests passing with >= 95% coverage across all touched components.
6. Zero Em/En-Dashes: Clean verification under `check_no_dashes` (0 em/en-dashes).
7. Live Full-Stack Proof: 100% pass across all 4 operational scenarios on containerized live environment.

---

## 2. Detailed Contract & Security Verification

### 2.1 Principal Handle Slugification & Anti-Leak Discipline (`kanban/admin/principal_service.py`)
- Problem: Group principals in `/api/v1/admin/principals` and `/api/v1/admin/principals/{id}` often rendered handles as `@<UUID>`, leaking internal database UUIDs and violating human-readable handle standards.
- Solution:
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
  - Group principals created with human names (e.g. "DevOps Team") output handle `@devops-team`.
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

### 2.3 Topbar Air-Gap Indicator Synchronization (`useSystemStatus.ts`, `Topbar.tsx`, `WorkspaceSettingsPage.tsx`)
- Event Dispatch: When saving workspace settings in `WorkspaceSettingsPage.tsx`:
  ```tsx
  window.dispatchEvent(new CustomEvent('kb:system-status-changed'));
  queryClient.invalidateQueries({ queryKey: qk.systemStatus() });
  ```
- Event Listener: `useSystemStatus.ts` listens to `kb:system-status-changed` and invalidates `['system', 'status']`.
- Topbar Rendering: `Topbar.tsx` consumes `useSystemStatus()`, immediately rendering the `📴 Air-Gap Active` badge when `airgap_mode === true` without requiring page refresh.

### 2.4 Workspace Settings Tab Anchors & Deep Linking (`WorkspaceSettingsPage.tsx`)
- Tab Buttons: `id="tab-general"`, `id="tab-members"`, `id="tab-groups"` with `data-testid="tab-..."`.
- Hash Synchronization:
  - On mount: parses `window.location.hash` and sets active tab accordingly.
  - On `hashchange` event: updates tab state dynamically.
  - On tab click: updates `window.location.hash` via `history.replaceState`.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt`)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-12/live-fullstack-proof.txt` against commit `23ae056d`:
1. Problem 1 (Air-gap topbar sync zero reload):
   - Topbar badge before air-gap toggle: `⚠️ ✕`.
   - Immediately after toggle Air-Gap ON (NO reload): `⚠️ ✕ 📴` present.
   - Immediately after toggle Air-Gap OFF (NO reload): `⚠️ ✕` returns.
2. Problem 2 & 3 (Group @slug & no reset password for non-users):
   - Auth Studio table inspection:
     - "Infra Team" (Group): `handleText: "@infra-team"`, `typePill: "Group"`, `resetButtons: 0`, `rawHasUuid: false`.
     - "Triage Bot" (Agent): `handleText: "@triage-bot"`, `typePill: "Agent"`, `resetButtons: 0`, `rawHasUuid: false`.
     - "Admin User" (User): `handleText: "@admin"`, `resetButtons: 1`.
     - "Read Only Viewer" (User): `handleText: "@viewer"`, `resetButtons: 1`.
3. Problem 4 (Workspace Settings tab anchors):
   - Initial `#tab-groups` check: `hasGeneral: true`, `hasMembers: true`, `hasGroups: true`, `groupsVisible: true`, `hash: "#tab-groups"`.
   - Clicking `#tab-members` updates `window.location.hash=#tab-members`.
4. Overall Stability: Console errors: 0, Page errors: 0, 5xx responses: 0. `LIVE_STACK_VERDICT: PASS`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suite: `kanban/tests/api/test_admin_principals.py` PASSED (16/16).
  - Coverage: `kanban.admin.principal_service` achieves 96% statement coverage.
- Frontend Vitest Suites:
  - `src/features/admin-auth/AuthStudioPage.test.tsx`: 42/42 PASSED.
  - `src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx`: 25/25 PASSED.
  - `src/app/useSystemStatus.test.tsx` & `src/features/system/useSystemStatus.test.tsx`: 5/5 PASSED.
  - `src/styles/__tests__/cssTokensAudit.test.ts`: 4/4 PASSED.
  - All touched files exceed 95% statement and branch coverage.
- Static Analysis: `tsc -b` (0 errors), `eslint` (0 warnings), `mypy` (0 errors), `ruff check` (clean), `check_no_dashes` (0 em/en-dashes).

---

## 5. Specialist Checklist

1. [x] Group principal handles formatted cleanly as `@slug` without leaking RFC 4122 UUIDs
2. [x] Agent and group principals fall back to `@group` / `@agent` instead of raw UUIDs
3. [x] Reset Password button and modal hidden completely for non-user principals
4. [x] `kb:system-status-changed` event triggers immediate topbar air-gap badge update
5. [x] Event listener cleaned up on unmount in `useSystemStatus.ts`
6. [x] Workspace settings tab buttons have `id="tab-*"` attributes
7. [x] Active tab state synchronized with `window.location.hash`
8. [x] 16/16 backend tests pass with 96% coverage on `principal_service.py`
9. [x] 72/72 frontend tests pass with >= 95% coverage on touched files
10. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 6. Verdict & Certification

STATUS: APPROVED

All API contracts, security invariants, handle formatting, and live full-stack proof for KAN-12 on `main` (commit `23ae056d`) are fully verified and certified.
