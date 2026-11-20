# API Specialist Review: KAN-16 (KB-P3-AUDIT-10)

- **Ticket:** KAN-16
- **Title:** [KB-P3-AUDIT-10] Build Offline /docs Documentation Center, Contextual HelpDrawer, and Studio-Wide (?) + More Info -> Links
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)
- **Date:** 2026-11-20
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-16`
- **Branch:** `main` (commit `7913c2c8`)
- **Container Environment:** `http://127.0.0.1:18961` (container: `kanban-liveqa-1`)
- **Live Stack Status:** `LIVE_STACK_VERDICT: PASS`
- **Status:** APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Route Architecture audit inspects ticket **KAN-16** on branch `main` at commit `7913c2c8`. The review integrates empirical proof from zero-mock Live Full-Stack QA execution against container `kanban-liveqa-1` (`http://127.0.0.1:18961`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-16/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-16/screenshots/`, unit test execution logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket implements an offline documentation center, contextual help drawer, and studio-wide help links, successfully remediating all forensic findings raised in `reality-checker-report.md`:
1. **Public Unauthenticated Documentation Access:** Clean top-level bypass routes for `/docs` and `/help` ensure immediate, unauthenticated documentation availability pre-bootstrap without redirect loops or setup traps.
2. **Zero-Egress Offline Image Resolution:** `DocMarkdownViewer.tsx` implements strict URL sanitization (`resolveSafeDocImageUrl`) that resolves bundled local images (`/docs-images/*.png`) and rejects all external or protocol-prefixed URLs (`http:`, `https:`, `//`, `data:`, `javascript:`), guaranteeing zero external network egress.
3. **Wiki Bundle Synchronization:** `scripts/sync_wiki_bundle.py` synchronizes 65 PNG screenshots from `thumbs-up-kanban.wiki/images/` to `kanban/web/public/docs-images/`, bundles 28 documentation chapters, and prioritizes `Home.md` as "Chapter 1 of 28".
4. **Contextual Help & Focus Management:** `HelpDrawer.tsx` implements initial focus placement, cyclic `Tab` / `Shift+Tab` focus trapping, and focus restoration to the invoking trigger button upon `Escape` dismissal, while preserving active form inputs (e.g., `UNSAVED-DRAFT-42`).
5. **Quality & Test Coverage:** Vitest code coverage on touched docs-center modules achieved 99.5% Statements, 97.06% Branch, 100% Functions, and 100% Lines (surpassing the >=95% requirement). Full 14-file test suite passed 350/350 tests with exactly zero `act(...)` warnings. Zero em-dashes and en-dashes across all files.

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
- **Dead Route Deduplication:** The shadowed child routes inside `RootShellLayout` were completely removed, eliminating conflicting route matching, auth redirect traps, or unauthenticated redirect loops during initial setup.
- **Live Stack Proof (Container `kanban-liveqa-1`):**
  - Script: `kan16_kan33_docs.mjs` executed before `/setup` claim.
  - `GET http://127.0.0.1:18961/docs`: Loaded in 1420ms with 0 redirects to `/login` or `/setup`.
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
    * `/docs-images/14-custom-fields-studio.png` (`complete=true`, `naturalWidth=1440`)
    * `/docs-images/53-custom-fields-test-execute.png` (`complete=true`, `naturalWidth=1440`)
    * `/docs-images/36-rail-custom-fields.png` (`complete=true`, `naturalWidth=1440`)
    * `/docs-images/52-custom-fields-dual-control.png` (`complete=true`, `naturalWidth=1440`)
  - External network egress requests during load: exactly 0.

### 2.3 Wiki Synchronization Pipeline (`scripts/sync_wiki_bundle.py`)
- Python synchronization tool syncs wiki markdown chapters and images into the static frontend bundle:
  - `sync_wiki_images()` copies 65 image assets to `kanban/web/public/docs-images/`.
  - `load_chapters_from_wiki()` orders `Home.md` as Chapter 1, generating a consistent 28-chapter sequence.
- Code hygiene: passes `ruff check`, `ruff format --check`, `mypy`, and `check_no_dashes` with 0 errors.

### 2.4 Contextual HelpDrawer & Escape Focus Restoration (`HelpDrawer.tsx`, `FieldHelpHint.tsx`)
- **Focus Preservation & Restoration:**
  - On mount, `HelpDrawer` captures the invoking element in `previousActiveElementRef.current = document.activeElement as HTMLElement`.
  - On close or unmount, focus is explicitly restored: `previousActiveElementRef.current?.focus()`.
  - Keyboard focus trap wraps `Tab` from the last focusable element to the first, and `Shift+Tab` from the first focusable element to the last.
- **Unsaved Draft Preservation:**
  - Live container test in `/projects/KAN/settings`: typed `"UNSAVED-DRAFT-42"` into project name, opened `HelpDrawer` via `proj-modules-help` `(?)` -> `"More info ->"`, pressed `Escape`.
  - Drawer closed (`drawerCount=0`), focus restored directly to `<button data-testid="proj-modules-help">`, and draft `"UNSAVED-DRAFT-42"` remained intact.
  - Same focus restoration verified in `/projects/SEC2/settings/custom-fields` for `hint-field-flavor`.

---

## 3. Test Suites, Coverage, & Static Gate Results

### 3.1 Vitest Coverage (Docs Center & StudioDocLink)
- Command: `COVERAGE_INCLUDE="src/features/docs-center/**,src/components/help/StudioDocLink.tsx" npm run test:coverage -- src/features/docs-center/__tests__/DocsCenter.test.tsx`
- Results:
  - `DocsCenter.test.tsx`: 35/35 passed (2.55s).
  - Code Coverage Table:

| File | % Stmts | % Branch | % Funcs | % Lines | Uncovered Lines |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **All files** | **99.50%** | **97.06%** | **100%** | **100%** | |
| `components/help/StudioDocLink.tsx` | 100% | 100% | 100% | 100% | None |
| `features/docs-center/DocMarkdownViewer.tsx` | 99.02% | 95.58% | 100% | 100% | 46, 165, 235, 460 |
| `features/docs-center/DocsCenterPage.tsx` | 100% | 100% | 100% | 100% | None |
| `features/docs-center/HelpDrawer.tsx` | 100% | 95.00% | 100% | 100% | 68, 136 |
| `features/docs-center/docsService.ts` | 100% | 100% | 100% | 100% | None |
| `features/docs-center/wikiManifest.ts` | 100% | 100% | 100% | 100% | None |

### 3.2 Full 14-Suite Unit Test Execution
- Command: `npm run test:unit -- [14 affected test files]`
- Results: 14 test files passed, 350 tests passed, 0 failed, 0 warnings.
- Warning Audit: Exactly 0 `act(...)` warnings and 0 uncontrolled input warnings across all 350 tests.
- Design Token Audit: `cssTokensAudit.test.ts` passed 4/4 (0 inline JSX `style={...}` attributes, 100% design token compliance).

### 3.3 Static Gate Verification
- TypeScript (`tsc -b --noEmit`): 0 errors.
- ESLint (`eslint . --max-warnings 0`): 0 problems.
- Vite Production Build: built in 1.28s, 720 modules transformed.
- Python Ruff Check (`scripts/sync_wiki_bundle.py`): All checks passed.
- Python Ruff Format Check: 1 file already formatted.
- Mypy: Success: no issues found in 1 source file.
- Check No Dashes (`python3 -m scripts.check_no_dashes`): 0 forbidden unicode dashes.

---

## 4. Security & Architecture Invariants Checklist

| Invariant / Check | Requirement | Live Verification Result |
| :--- | :--- | :--- |
| **Public Unauthenticated Access** | `/docs` accessible pre-bootstrap without redirect | 200 OK, 1420ms, 0 redirects to `/login` or `/setup` |
| **Zero External Egress** | Offline docs viewing makes zero remote HTTP calls | 0 external requests recorded during full run |
| **URL Scheme Sanitization** | Reject `http:`, `https:`, `//`, `data:`, `javascript:` | `resolveSafeDocImageUrl` strictly returns `null` |
| **Path Traversal Defense** | Reject `..`, `/`, and `\` in image paths | Verified by unit tests; returns `null` |
| **Focus Restoration on Escape** | Restore focus to invoking `(?)` trigger button | Verified on `/projects/KAN/settings` and `/projects/SEC2/settings/custom-fields` |
| **Draft Preservation** | Do not clear unsaved inputs when opening/closing help | `"UNSAVED-DRAFT-42"` retained in form state |
| **Keyboard Accessibility** | Cyclic `Tab` / `Shift+Tab` focus trap inside drawer | Verified in live stack and Vitest suites |
| **Design Token Adherence** | 0 inline `style={...}`, 100% CSS token compliance | `cssTokensAudit.test.ts` passed 4/4 |
| **Typography Standards** | 0 em-dashes (`\u2014`) and 0 en-dashes (`\u2013`) | `scripts.check_no_dashes` clean |

---

## 5. Certification Signoff

STATUS: APPROVED

Ticket KAN-16 is fully remediated, verified against live unmocked container execution on `kanban-liveqa-1` (`:18961`, commit `7913c2c8`), meets all security and architectural invariants, and is certified ready for reality-checker QA gate closure.
