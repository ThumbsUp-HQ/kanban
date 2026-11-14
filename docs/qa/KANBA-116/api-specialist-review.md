# API Specialist Gate Review: KANBA-116 (KB-P3-51)

- **Ticket**: `KANBA-116` (`KB-P3-51`: `[Phase 3 / Frontend] Project Stickies 6-palette grid, 1000ms idle complexity heuristic, promotion banner & Doc stub`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Worktree**: `/tmp/kb-wt-KANBA-116`
- **Branch**: `feat/KANBA-116` (commit `71702ee`)
- **Verdict**: **APPROVED**

---

## 1. Executive Summary & Verification Matrix

As Systems/Backend Architect & API Specialist, I have conducted an exhaustive forensic audit of the implementation of `KANBA-116` (`KB-P3-51`), covering client-side API contracts, complexity heuristics, snooze mathematics, atomic promotion lifecycle, and storage limits across `kanban/web/src/features/stickies/`.

The implementation satisfies all architectural, API contract, security, and complexity specification requirements defined in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (Sections 8.1, 8.2, 6.1, 6.2):
- **API Wire Contract Consumption (KB-P3-15, S8.1, S8.2)**: `stickiesApi.ts` implements typed REST operations covering project-scoped list/create (`GET`/`POST /api/v1/projects/{projectKey}/stickies`), workspace overview (`GET /api/v1/stickies`), optimistic updates (`PATCH /api/v1/stickies/{id}` with `If-Match` ETag), deletion (`DELETE`), dedicated snooze persistence (`POST .../snooze-promotion` with PATCH fallback), atomic doc promotion (`POST .../promote-to-doc`), and editable copy unarchival (`POST .../unarchive-copy`).
- **Client/Server Heuristic Parity (S8.2)**: `stickyHeuristic.ts` evaluates all 5 structural complexity triggers outside code fences (char count > 600, line count > 10, headings >= 2, tables/diagrams/code blocks > 6 lines, and links >= 3). The parser accurately tracks code fence boundaries (``` and ~~~), ensuring markdown comments (`#`) and bracketed tokens inside code blocks do not induce false positive promotion recommendations.
- **Snooze Threshold Persistence & Exact Integer Math (S8.2)**: Persists `promotion_snoozed_at_length` across page reloads. Re-evaluates snooze suppression using exact integer arithmetic (`charLength * 2 >= promotionSnoozedAtLength * 3`), guaranteeing the promotion banner remains silenced until content grows by at least +50% over the snoozed length.
- **Atomic Promotion to Doc & Promoted Stub (S8.2, KB-P3-15)**: Activating `[Promote to Doc ->]` dispatches `POST .../promote-to-doc`, invalidates sticky and doc tree query caches, and immediately renders `PromotedStickyStub` with deep link `[📄 Open Doc]` and non-destructive `[Unarchive Copy]`.
- **Defensive Bounds & XSS Immunity**: Enforces `maxBytes={65536}` on sticky bodies; renders hostile payloads (e.g. `<img src=x onerror=alert(1)>`) exclusively through React string text nodes; avoids inline `style` strings by utilizing pure CSS classes bound to theme variables (`--sticky-amber` through `--sticky-slate`).

| Verification Dimension | Specification Target | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **REST API Coverage** | List, create, patch, delete, promote, unarchive | Full typed client in `stickiesApi.ts` with error unwrapping | PASS |
| **5 Complexity Triggers** | S8.2 char, line, heading, diagram, link limits | Verified in 25 unit tests in `stickyHeuristic.test.ts` | PASS |
| **Code Fence Isolation** | Ignore headings and links inside code blocks | Robust fence state machine in `analyzeBlocks()` | PASS |
| **Snooze >= 1.5x Math** | Integer `charLength * 2 >= snoozed * 3` | Verified boundary tests (e.g. snoozed at 620, fires at 930) | PASS |
| **Idle Debounce** | 1,000ms idle timer before complexity check | `STICKY_IDLE_DEBOUNCE_MS = 1000` with timer cleanup | PASS |
| **Optimistic Concurrency** | `If-Match` ETag header on PATCH mutations | Included in `updateSticky()` when etag is provided | PASS |
| **Atomic Doc Promotion** | Single-transaction Doc creation + ACL copy | Calls `POST .../promote-to-doc`; renders `PromotedStickyStub` | PASS |
| **Unarchive Copy** | Fresh editable sticky while preserving Doc | Calls `POST .../unarchive-copy`; resets stub state | PASS |
| **Hostile Input & XSS** | Text node children; zero raw HTML execution | `<img onerror>` renders as harmless string text node | PASS |
| **Unit Test Coverage** | >= 95% lines, branches, funcs, stmts | 7/7 files, 58/58 passed in 3.89s; **100%** lines, **96.15%** branch | PASS |
| **Static Code Quality** | Zero compiler, linter, or type errors | `tsc -b --noEmit`, `eslint`, `vite build` clean (exit code 0) | PASS |
| **Typography Standard** | Plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

## 2. Deep Technical & Security Invariant Audits

### 2.1 API Wire Contract Consumption (`stickiesApi.ts`)
- **Query Keys & Cache Invalidation**: The hook layer binds stickies queries to `qk.stickies(projectKey)` or `qk.workspaceStickies()`. On successful promotion, it coordinates invalidation of both `qk.stickies(projectKey)` and `qk.docsTree(projectKey)`, ensuring the document hierarchy sidebar updates immediately.
- **Optimistic Concurrency Control**: `updateSticky()` inspects `etag` and passes the HTTP header `If-Match: <etag>`, preventing lost updates in concurrent editing sessions.
- **REST Error Unwrapping**: `handleResponse()` defensively checks JSON error bodies for RFC 7807 `detail` or `message` fields, surfacing human-readable messages to the caller.

### 2.2 S8.2 Complexity Heuristics State Machine (`stickyHeuristic.ts`)
- **Unicode Code-Point Accuracy**: `Array.from(bodyMarkdown).length` computes character count using full Unicode code points rather than UTF-16 code units, matching PostgreSQL `char_length(body_markdown)` semantics.
- **Code Fence State Machine**:
  * Tracks opening fences matching `/^ {0,3}(`{3,}|~{3,})(.*)$/`.
  * Evaluates inner line count against `MAX_CODE_FENCE_LINES = 6`.
  * Detects `mermaid` and `svg` language identifiers.
  * Disables heading (`#`) and link regex matching while inside an open fence, guaranteeing that code comments do not trigger false complexity warnings.
- **Trigger Inventory**:
  1. `charLength > 600` -> `"<N> chars (> 600)"`
  2. `lineCount > 10` -> `"<N> lines (> 10)"`
  3. `headingCount >= 2` -> `"<N> headings (>= 2)"`
  4. Structured block (GFM table, mermaid, svg, code fence > 6 lines) -> `"table, diagram, or >6-line code block"`
  5. `outboundLinkCount >= 3` -> `"<N> links (>= 3)"`

### 2.3 Snooze Math & Persistence Invariant
- **Exact Integer Comparison**:
  ```ts
  if (promotionSnoozedAtLength !== null) {
    let snoozeCleared = false;
    if (promotionSnoozedAtLength === 0) {
      snoozeCleared = charLength > 0;
    } else {
      snoozeCleared = charLength * 2 >= promotionSnoozedAtLength * 3;
    }
    shouldShowBanner = exceeded && snoozeCleared;
  }
  ```
  This eliminates floating-point rounding errors and strictly satisfies the specification rule: content must expand by at least +50% over the length at which the user snoozed.
- **Snooze Action Persistence**: Clicking `[Snooze]` calls `snoozeStickyPromotion(stickyId, charLength, etag)`, persisting the current length to the database so page reloads do not reshow the banner.

### 2.4 Atomic Promotion & Promoted Doc Stub Lifecycle
- **Transition Contract**: When `promoted_to_doc_id` is populated (either returned from `POST .../promote-to-doc` or fetched on initial load), `StickyCard` transitions into `PromotedStickyStub`.
- **Stub Immutability & Access**: The stub renders a read-only 160-character plaintext preview, a direct link `[📄 Open Doc]` pointing to `/projects/:projectKey/docs/:promotedPageId`, and an interactive `🛡️` access button dispatching `kb:open-access-inspector`.
- **Unarchive Flow**: Clicking `[Unarchive Copy]` dispatches `POST /api/v1/stickies/{id}/unarchive-copy`, generating an independent, editable sticky with a fresh UUID while preserving the promoted document intact.

### 2.5 Security, Bounds & CSP Invariants
- **Input Sanitization**: Embedded `MarkdownEditor` enforces `maxBytes={65536}` (64 KB). Payload sizing is checked on the client before dispatch.
- **XSS Immunity**: Preview strings and descriptions strip markup or render as React string children. Hostile strings containing `<img src=x onerror=alert(1)>` render literal text without injecting HTML elements.
- **Strict CSP Compliance**: All 6 color variants (`amber`, `mint`, `sky`, `lavender`, `coral`, `slate`) apply CSS class names (`.sticky-card--amber`, etc.) mapped to CSS variables in `StickiesGrid.css`, with zero inline `style` strings.

---

## 3. Test Coverage & Verification Results

### 3.1 Unit Test Suite (`vitest`)
Executed `pnpm --dir kanban/web exec vitest run --coverage --coverage.include="src/features/stickies/**" src/features/stickies`:
- **Files**: 7/7 passed (`stickyHeuristic.test.ts`, `stickiesApi.test.ts`, `StickyCard.test.tsx`, `StickyPromotionBanner.test.tsx`, `PromotedStickyStub.test.tsx`, `StickiesGrid.test.tsx`, `StickiesViews.test.tsx`).
- **Tests**: 58 passed, 0 failures (runtime 3.89s).
- **Statements**: **100.00%** (exceeds >= 95% threshold).
- **Branches**: **96.15%** (exceeds >= 95% threshold).
- **Functions**: **100.00%** (exceeds >= 95% threshold).
- **Lines**: **100.00%** (exceeds >= 95% threshold).

### 3.2 Production Build, Typecheck, and Lint
- `pnpm --dir kanban/web typecheck` (`tsc -b --noEmit`): 0 errors.
- `pnpm --dir kanban/web lint` (`eslint . --max-warnings 0`): 0 errors, 0 warnings.
- `pnpm --dir kanban/web build` (`tsc -b && vite build`): Clean build in 1.51s (exit code 0).

### 3.3 Playwright E2E & Style Probes
- `playwright test e2e/stickies/stickies-promotion.spec.ts`: 12/12 passed across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844).
- Verified computed styles: `.stickies-grid` gap 20px (`--space-5`), `.sticky-card` padding 16px 18px (`--card-pad`), `.emoji-hint` 24px x 24px, all 6 palette surfaces tested in Light and Dark themes with WCAG AA contrast compliance.

### 3.4 Dash Standard Compliance
- `python3 scripts/check_no_dashes.py --all`: 0 non-ASCII dashes detected.

---

## 4. Final Architectural Sign-Off

The `KANBA-116` (`KB-P3-51`) implementation fulfills all backend architecture, API consumption, complexity heuristic parity, snooze mathematics, and doc promotion lifecycle specifications. The API Specialist Gate requirements are completely satisfied.

**VERDICT: APPROVED**
