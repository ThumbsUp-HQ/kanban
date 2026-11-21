# API Specialist Review: KAN-16 (KB-P3-AUDIT-10)

- **Ticket:** KAN-16
- **Title:** [KB-P3-AUDIT-10] Build Offline /docs Documentation Center, Contextual HelpDrawer, and Studio-Wide (?) + More Info -> Links
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-16`
- **Branch:** `main` (commit `9b163f07`)
- **Container Environment:** `http://127.0.0.1:18961` (container: `kanban-liveqa-1`)
- **Live Stack Status:** `LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Route Architecture audit inspects ticket **KAN-16** on branch `main` at commit `9b163f07`. The review integrates empirical proof from zero-mock Live Full-Stack QA execution against container `kanban-liveqa-1` (`http://127.0.0.1:18961`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-16/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-16/screenshots/`, unit test execution logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket implements an offline documentation center, contextual help drawer, and studio-wide help links, successfully remediating all forensic findings raised in `reality-checker-report.md`:
1. **Public Unauthenticated Documentation Access:** Clean top-level bypass routes for `/docs` and `/help` ensure immediate, unauthenticated documentation availability pre-bootstrap without redirect loops or setup traps.
2. **Zero-Egress Offline Image Resolution:** `DocMarkdownViewer.tsx` implements strict URL sanitization (`resolveSafeDocImageUrl`) that resolves bundled local images (`/docs-images/*.png`) and rejects all external or protocol-prefixed URLs (`http:`, `https:`, `//`, `data:`, `javascript:`), guaranteeing zero external network egress. All embedded images, including `/docs-images/14-custom-fields-studio.png`, load cleanly with HTTP 200 (`naturalWidth=1440, naturalHeight=900`).
3. **Wiki Bundle Synchronization:** `scripts/sync_wiki_bundle.py` synchronizes 65 PNG screenshots from `thumbs-up-kanban.wiki/images/` to `kanban/web/public/docs-images/`, bundles 28 documentation chapters, and prioritizes `Home.md` as "Chapter 1 of 28".
4. **Contextual Help & Focus Suppression Timing Order:**
   - In `HelpDrawer.tsx` (lines 67-76), `onClose` sets `data-kb-suppress-focus="true"` on `previousActiveElementRef.current` immediately prior to calling `focus()`.
   - In `FieldHelpHint.tsx`, `handleFocus` checks for `data-kb-suppress-focus="true"`, removes the attribute, and returns early without re-opening the popover. `handleDocLinkClick` sets `data-kb-suppress-focus="true"` and `suppressNextFocusRef.current = true` before `focus()`.
   - Live QA on `kanban-liveqa-1` confirms: pressing Escape inside HelpDrawer restores browser focus to the invoking `(?)` trigger button with `popoverOpenAfterEscape=false` and `ariaExpandedAfterEscape="false"` on both `/projects/KAN/settings` and `/projects/KAN/settings/custom-fields`, while preserving active form inputs (`UNSAVED-DRAFT-42`).
5. **Quality & Test Coverage:** Vitest code coverage across all touched docs-center and help components achieved 99.63% Statements, 95.56% Branch, 100% Functions, and 100% Lines (all exceeding the >=95% requirement) with 69/69 passing tests and zero `act(...)` console warnings. Static analysis, lint-imports, and check_no_dashes passed with 0 errors.

---

## 2. Forensic API, Security, & Route Layering Audit

### 2.1 Public Unauthenticated Route Bypass (`kanban/web/src/app/routes.tsx`)
- **Route Topology:** In `routes.tsx`, `/docs`, `/docs/:slug`, `/help`, and `/help/:slug` are mounted as top-level public bypass routes outside authenticated shell layouts:
  ```typescript
  {
    path: '/docs',
    element: <DocsCenterPage />,
  },
  {
    path: '/docs/:slug',
    element: <DocsCenterPage />,
  },
  {
    path: '/help',
    element: <Navigate to="/docs" replace />,
  },
  {
    path: '/help/:slug',
    element: <DocsCenterPage />,
  }
  ```
- **Dead Route Deduplication:** Shadowed child routes inside `RootShellLayout` were completely removed, eliminating conflicting route matching, auth redirect traps, or unauthenticated redirect loops during initial setup.
- **Live Stack Proof (Container `kanban-liveqa-1`, `:18961`):**
  - Script: `round4_live_qa.mjs` executed before `/setup` claim.
  - `GET http://127.0.0.1:18961/docs`: Loaded in 1042ms with 0 redirects to `/login` or `/setup`.
  - Verified H1: `"👍kanban: Executive Architecture and System Overview"`, Chapter badge: `"Chapter 1 of 28"`, 28 total chapter links.

### 2.2 Offline Bundled Wiki Images & Zero-Egress SSRF Protection (`DocMarkdownViewer.tsx`)
- **Strict Image URL Resolver (`resolveSafeDocImageUrl`):**
  ```typescript
  export function resolveSafeDocImageUrl(src: string): string | null {
    if (!src || typeof src !== 'string') return null;
    const trimmed = src.trim();
    if (
      trimmed.startsWith('http:') ||
      trimmed.startsWith('https:') ||
      trimmed.startsWith('//') ||
      trimmed.startsWith('data:') ||
      trimmed.startsWith('javascript:')
    ) {
      return null;
    }
    const clean = trimmed.replace(/^\.?\/?(images|docs-images)\//, '');
    if (!clean || clean.includes('..') || clean.includes('/') || clean.includes('\\')) {
      return null;
    }
    return `/docs-images/${encodeURIComponent(clean)}`;
  }
  ```
- **Security Invariant Verification:**
  - Rejection of Remote Schemes: Prevents arbitrary egress requests, SSRF, tracking beacons, and cross-site data leaks in air-gapped or offline environments.
  - Path Traversal Defense: Rejects `..`, `/`, and `\` in resolved filenames, preventing arbitrary static asset directory traversal.
  - Rejection of `data:` and `javascript:`: Blocks potential inline payload execution or XSS vectors.
- **Live Stack Verification:**
  - Chapter `/docs/admin-custom-scripted-fields-and-sandbox` verified in live container:
    * `/docs-images/14-custom-fields-studio.png` (`complete=true`, `naturalWidth=1440`, `naturalHeight=900`, non-404)
    * `/docs-images/53-custom-fields-test-execute.png` (`complete=true`, `naturalWidth=1440`, `naturalHeight=900`)
    * `/docs-images/36-rail-custom-fields.png` (`complete=true`, `naturalWidth=1440`, `naturalHeight=900`)
    * `/docs-images/52-custom-fields-dual-control.png` (`complete=true`, `naturalWidth=1440`, `naturalHeight=900`)
  - External network egress requests during load: exactly 0.

### 2.3 Wiki Synchronization Pipeline (`scripts/sync_wiki_bundle.py`)
- Python synchronization tool syncs wiki markdown chapters and images into the static frontend bundle:
  - `sync_wiki_images()` copies 65 image assets to `kanban/web/public/docs-images/`.
  - `load_chapters_from_wiki()` orders `Home.md` as Chapter 1, generating a consistent 28-chapter sequence.
- Code hygiene: passes `ruff check`, `ruff format --check`, `mypy`, and `check_no_dashes` with 0 errors.

### 2.4 Contextual HelpDrawer & Focus Suppression Order (`HelpDrawer.tsx`, `FieldHelpHint.tsx`)
- **Focus Suppression Timing Order:**
  - In `HelpDrawer.tsx`: `onClose` sets `previousActiveElementRef.current.setAttribute('data-kb-suppress-focus', 'true')` immediately prior to calling `.focus()`.
  - In `FieldHelpHint.tsx`: `handleFocus` checks for `data-kb-suppress-focus="true"`, removes the attribute, and returns early without opening the popover. `handleDocLinkClick` sets `data-kb-suppress-focus="true"` and `suppressNextFocusRef.current = true` before calling `triggerRef.current?.focus()`.
- **Live Stack Verification on Container `kanban-liveqa-1`:**
  - Studio 1 (`/projects/KAN/settings`): Entered `"UNSAVED-DRAFT-42"` into project name, clicked `(?)` `[data-testid="proj-modules-help"]`, clicked `"More info ->"`, opened HelpDrawer, pressed Escape.
    * Drawer closed (`drawerCount=0`), draft `"UNSAVED-DRAFT-42"` preserved.
    * Focus restored to `[data-testid="proj-modules-help"]` (`restoredToHelpBtn=true`).
    * Popover remained closed: `popoverOpenAfterEscape=false`, `ariaExpandedAfterEscape="false"`, `popoverCountAfterEscape=0`.
  - Studio 2 (`/projects/KAN/settings/custom-fields`): Clicked `(?)` `[data-testid="hint-field-flavor"]`, clicked `"More info ->"`, opened HelpDrawer, pressed Escape.
    * Focus restored to `[data-testid="hint-field-flavor"]` (`restoredToHelpBtn=true`).
    * Popover remained closed: `popoverOpenAfterEscape=false`, `ariaExpandedAfterEscape="false"`, `popoverCountAfterEscape=0`.

---

## 3. Test Suites, Coverage, & Static Gate Results

### 3.1 Vitest Coverage (Docs Center & FieldHelpHint)
- Command: `COVERAGE_INCLUDE="src/features/docs-center/DocsCenterPage.tsx,src/features/docs-center/DocMarkdownViewer.tsx,src/features/docs-center/HelpDrawer.tsx,src/components/help/FieldHelpHint.tsx,src/components/help/StudioDocLink.tsx" pnpm --dir kanban/web exec vitest run --coverage src/features/docs-center/DocsCenter.test.tsx src/components/help/FieldHelpHint.test.tsx`
- Results: 2 test files passed, 69/69 tests passed in 3.75s (0 failures, 0 skipped).
- Code Coverage Table:

| File | % Stmts | % Branch | % Funcs | % Lines | Uncovered Lines |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **All files** | **99.63%** | **95.56%** | **100%** | **100%** | |
| `components/help/FieldHelpHint.tsx` | 100% | 95.19% | 100% | 100% | 77, 293, 315-326 |
| `components/help/StudioDocLink.tsx` | 100% | 100% | 100% | 100% | None |
| `features/docs-center/DocMarkdownViewer.tsx` | 99.07% | 95.77% | 100% | 100% | 50, 169, 241, 475 |
| `features/docs-center/DocsCenterPage.tsx` | 100% | 93.90% | 100% | 100% | 48, 159, 366, 407 |
| `features/docs-center/HelpDrawer.tsx` | 100% | 97.72% | 100% | 100% | 68 |

### 3.2 Design Token & Styling Audit
- Command: `pnpm --dir kanban/web exec vitest run src/styles/__tests__/cssTokensAudit.test.ts`
- Results: 4/4 passed (0 inline JSX `style={...}` attributes, 100% CSS token compliance).

### 3.3 Static Gate Verification (Commit `9b163f07`)
- Database Migrations (`uv run kanban-ctl db check-migrations`): OK: All 63 migrations valid, single head (`p4_24_agent_safe_sequences`).
- Python Ruff Check (`uv run ruff check .`): All checks passed.
- Python Ruff Format Check (`uv run ruff format --check .`): 2027 files already formatted.
- Mypy Strict Typecheck (`uv run mypy database kanban mcp agent`): Success: no issues found in 997 source files.
- Import Linter (`uv run lint-imports`): Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- TypeScript Typecheck (`pnpm --dir kanban/web run typecheck`): 0 errors.
- ESLint (`pnpm --dir kanban/web run lint`): 0 errors, 0 warnings.
- Vite Production Build (`pnpm --dir kanban/web run build`): Built cleanly in 1.09s.
- Typography Audit (`python3 -m scripts.check_no_dashes --all`): 0 forbidden unicode dashes across repository.

---

## 4. Security & Architecture Invariants Checklist

| Invariant / Check | Requirement | Live Verification Result |
| :--- | :--- | :--- |
| **Public Unauthenticated Access** | `/docs` accessible pre-bootstrap without redirect | 200 OK, 1042ms, 0 redirects to `/login` or `/setup` |
| **Zero External Egress** | Offline docs viewing makes zero remote HTTP calls | 0 external requests recorded during full run |
| **URL Scheme Sanitization** | Reject `http:`, `https:`, `//`, `data:`, `javascript:` | `resolveSafeDocImageUrl` strictly returns `null` |
| **Path Traversal Defense** | Reject `..`, `/`, and `\` in image paths | Verified by unit tests; returns `null` |
| **Focus Restoration on Escape** | Restore focus to invoking `(?)` trigger button | Verified on `/projects/KAN/settings` and `/projects/KAN/settings/custom-fields` |
| **Popover Suppression on Escape** | Prevent popover from reopening on Escape focus | `popoverOpenAfterEscape=false`, `ariaExpandedAfterEscape="false"` |
| **Draft Preservation** | Do not clear unsaved inputs when opening/closing help | `"UNSAVED-DRAFT-42"` retained in form state |
| **Keyboard Accessibility** | Cyclic `Tab` / `Shift+Tab` focus trap inside drawer | Verified in live stack and Vitest suites |
| **Design Token Adherence** | 0 inline `style={...}`, 100% CSS token compliance | `cssTokensAudit.test.ts` passed 4/4 |
| **Typography Standards** | 0 em-dashes (`\u2014`) and 0 en-dashes (`\u2013`) | `scripts.check_no_dashes` clean (0 violations) |

---

## 5. Certification Signoff

STATUS: APPROVED

Ticket KAN-16 is fully remediated, verified against live unmocked container execution on `kanban-liveqa-1` (`:18961`, commit `9b163f07`), meets all security, route, and architectural invariants, and is certified ready for reality-checker QA gate closure.
