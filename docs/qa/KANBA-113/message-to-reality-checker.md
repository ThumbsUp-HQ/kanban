# Reality-Checker Verification Packet: KANBA-113 (KB-P3-41)

- **Ticket**: `KANBA-113` (`KB-P3-41`: `[Phase 3 / Frontend] Ticket drawer shell (640px prose + 320px rail) & zero-remount full screen`)
- **Author**: `builder-22` (Implementation Author)
- **Worktree**: `/tmp/kb-wt-KANBA-113`
- **Branch**: `feat/KANBA-113`
- **Specification**: Section 7.1, Section 7.2 (8a, 8o), Section 6.1, Section 6.2

---

## 1. Architectural Summary & Zero-Remount Contract

`KANBA-113` implements the right-docked ticket drawer shell and zero-remount full-screen issue surface in accordance with Section 7.1, 7.2 8a/8o, and Section 6.1/6.2 tokens:

1. **Zero-Remount Surface Host Invariant (S7.2 8o)**:
   - `<IssueSurface />` is rendered once inside `#kb-issue-surface-host` within `<AppShell>`, outside the routed `<Outlet />`.
   - The route layout is unified under `UnifiedAppShellLayout` in `app/routes.tsx`, ensuring that transitions between project views with `?peek=<KEY>` and full-screen `/projects/:projectKey/issues/:issueKey` never remount `<AppShell>` or `<IssueSurface>`.
   - Invariant proof: `data-mount-id` (crypto UUID generated on mount) and `data-mount-seq` (module-level mount counter) remain completely identical across 5 round-trip toggles between drawer and full-screen modes, with exactly zero additional network requests (verified by both Vitest unit test and Playwright E2E test).
   - Component state (such as unsaved draft text in `SummaryField`) is 100% preserved when toggling full-screen mode via button or `Cmd+Shift+F` / `Ctrl+Shift+F`.

2. **Design Tokens & Responsive Layout (S6.1)**:
   - Drawer container width: `var(--drawer-w)` (`min(960px, 68vw)`: 960px at 1440px desktop, 696px at 1024px tablet).
   - Desktop (1440x900): Side-by-side grid with 640px editorial prose column (`minmax(0, 640px)`) and 320px rail column (`320px`).
   - Tablet (1024x768): Stacks vertically via `@container issue-surface (max-width: 879px)`, rail placed below prose.
   - Mobile (390x844): Full-viewport sheet (`inset: 0; width: 100vw; height: 100dvh`), `aria-modal="true"`, focus trap active (`useFocusTrap`).
   - Constant spacing tokens preserved across all viewports: `--prose-pad` (32px 40px), `--section-gap` (32px), `--text-body` (15px), `--leading-prose` (25.95px), and `--prop-row-h` (38px). Zero compact/dense overrides.

3. **Header Row (S7.1)**:
   - Collapse button (`→` glyph, accessible name `Close issue panel`).
   - Full-screen toggle button (`↗` glyph, accessible name `Open in full screen` in drawer mode, `Return to side panel` in full mode, `aria-keyshortcuts="Meta+Shift+F Control+Shift+F"`, `onMouseDown` prevents blur-commit).
   - Priority `EmojiHint` (`variant="tooltip"`): Literal hover text template: `Priority: <label> - sort weight <sort_order>. SLA target: <sla_target or "not configured">. Press P to change.`.
   - Monospace issue key: `<span class="mono issue-header__key">{issueKey}</span>`.
   - Access `EmojiHint` (`AccessPill`, `variant="interactive"`): Renders `🛡️ <scope_label> + <count>` pill; popup displays exact literal template (`Project: <name> - <users> users, <groups> groups, <agents> agents, <deny_rules> deny rules. Inherited from Project.`). Dispatches `kb:open-access-inspector` CustomEvent.
   - 3 extensible action slots: `subscribe`, `link`, `overflow` via `IssueSurfaceSlotsContext`.

4. **Summary Field (S7.2 8a)**:
   - Auto-growing inline textarea with C0/C1 and newline sanitization to single space.
   - Code point bounds validation (`1..500` characters via `Array.from(val.trim()).length`).
   - Inline alert on empty summary (`Summary cannot be empty.`) or >500 characters (`Summary must be 500 characters or fewer (currently N).`).
   - Optimistic mutation via `PATCH /api/v1/issues/{issue_key}` with `If-Match: <etag>`.
   - On `412 Precondition Failed`: Rolls back draft, displays conflict banner with `Reload` button invalidating query cache.
   - Keyboard navigation: `Enter` commits and moves focus to description slot; `Escape` reverts to original summary; blur commits.

5. **Security & Input Hardening**:
   - Strict `ISSUE_KEY_REGEX` (`^[A-Z][A-Z0-9]{1,9}-[1-9][0-9]{0,8}$`) and project prefix matching.
   - Malicious peek parameters (e.g. `javascript:alert(1)`, `../../admin`, mismatched projects) are rejected, stripped via `replace` navigation, and yield `issueKey: null`.
   - Malicious HTML/script payloads in summary and description render strictly as plain React text nodes (0 injected `<script>` or `<img>` elements).
   - Equalized error responses: `403` and `404` render the identical message `Issue <KEY> was not found or you do not have access.` to prevent resource enumeration.
   - Zero inline `style=` attributes in components; strict CSP compliance (`style-src 'self'`).

---

## 2. Verification Proof Matrix

- **Unit Tests**:
  - Test files: 8 files under `src/features/drawer/`.
  - Result: 71/71 tests passing (Duration 2.22s, exit code 0).
  - Coverage:
    * Statements: 99.37% (threshold >= 95%)
    * Branches: 96.04% (threshold >= 95%)
    * Functions: 100.00% (threshold >= 95%)
    * Lines: 99.37% (threshold >= 95%)
  - Artifact: `docs/qa/KANBA-113/unit-test-results.txt`.

- **Static Analysis & Linters**:
  - `pnpm check:api`: Clean (0 errors).
  - `pnpm typecheck`: Clean (0 errors).
  - `pnpm lint`: Clean (`eslint . --max-warnings 0`, 0 errors, 0 warnings).
  - `pnpm build`: Clean (0 errors).
  - Python workspace: `mypy --strict`, `ruff check`, `ruff format --check`, `lint-imports`, `scripts/license_gate.py`, and `scripts/check_no_dashes.py --all` all exit code 0.
  - Artifact: `docs/qa/KANBA-113/build-check.txt`.

- **Playwright E2E Suite**:
  - Command: `E2E_PORT=4193 QA_TICKET_ID=KANBA-113 pnpm --dir kanban/web exec playwright test e2e/drawer/issue-surface.spec.ts --project=desktop --project=tablet --project=mobile`
  - Result: 6/6 tests passing across all 3 viewports (16.1s).
  - Artifacts:
    * `docs/qa/KANBA-113/e2e-results.txt`
    * `docs/qa/KANBA-113/computed-styles-desktop.json`
    * `docs/qa/KANBA-113/computed-styles-tablet.json`
    * `docs/qa/KANBA-113/computed-styles-mobile.json`
    * 21 annotated visual screenshots in `docs/qa/KANBA-113/screenshots/` (7 tests x 3 viewports).

- **Specialist Gate Review**:
  - UI Specialist Gate: Authored and prepared in `docs/qa/KANBA-113/ui-specialist-review.md`.
