# API Specialist Gate Review: KANBA-134 (KB-P3-36)

- **Ticket**: `KANBA-134` (`KB-P3-36`: `[Phase 3 / Frontend] Admin Auth Studio UI: multi-card list, enable toggles, drag reorder, write-only secrets, live test-handshake & LOCKOUT_PREVENTED banner`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Worktree**: `/tmp/kb-wt-KANBA-134`
- **Branch**: `feat/KANBA-134` (commit `6fe4970`)
- **Verdict**: **APPROVED**

---

## 1. Executive Summary & Verification Matrix

As Systems/Backend Architect & API Specialist, I have performed an exhaustive architectural and API wire contract review of `KANBA-134` (`KB-P3-36`), implementing the Admin Auth Studio UI at `/admin/auth` according to `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (Sections 4.1, 4.2, 4.3, 3.4, 5.4, 6.1, 6.2) and `AGENTS.md`.

The implementation satisfies all architectural, cryptographic, and security invariant requirements:
- **Wire Contract Conformance (`adminAuthApi.ts`)**: Consumes the full `KB-P2-10` administrative card lifecycle across `GET /api/v1/admin/auth-cards`, `POST /api/v1/admin/auth-cards`, `PATCH /api/v1/admin/auth-cards/{id}`, `PATCH /api/v1/admin/auth-cards/{id}/enabled`, `POST /api/v1/admin/auth-cards/{id}/reorder`, `POST /api/v1/admin/auth-cards/{id}/test-handshake`, and `DELETE /api/v1/admin/auth-cards/{id}`.
- **Write-Only Secrets & Defensive Stripping (S4.1)**: On edit, existing cards render an empty password input with placeholder `"Stored encrypted (dek_kid: <dek_kid>) - leave blank to keep current secret"`. `secret_input` is strictly omitted from `PATCH` payloads unless the explicit `Replace stored secret` checkbox is toggled. Furthermore, `sanitizeAdminAuthCard()` in `adminAuthApi.ts` defensively strips any leaked secret keys (`client_secret`, `bind_dn_password`, `encrypted_secret_blob`, `wrapped_dek`) before passing responses to TanStack Query.
- **Base-62 COLLATE "C" Lexicographic Midpoint Ranks (`cardRank.ts`)**: Implements deterministic Base-62 (`0-9A-Za-z`) midpoint calculation matching PostgreSQL binary byte ordering (`COLLATE "C"`). Validated across 100 sequential top and middle insertions without collision.
- **Three-Layer Anti-Lockout Safeguards (`LockoutPreventedBanner.tsx`, S4.3)**: On `409 LOCKOUT_PREVENTED`, rolls back optimistic toggle/delete operations, focuses `role="alert"` banner, maps `ZERO_ADMIN_CARDS` and `HANDSHAKE_STALE_FOR_LOCAL_DISABLE` to exact specification copy, and surfaces copyable emergency CLI recovery command (`kanban-ctl auth emergency-unlock --enable-local-admin`).
- **Anti-Enumeration & Hostile Input Immunity (S3.4)**: Non-admin users (`me.is_server_admin !== true` or 404 from API) render the uniform `Not found or no access` state. All server-supplied strings (`display_name`, `check_summary`) render as literal React text nodes, eliminating DOM XSS or script injection.
- **Zero Unicode Dashes**: All code and documentation adhere strictly to plain ASCII hyphens `-` (zero `U+2014` or `U+2013` characters).

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **API Endpoints** | Complete KB-P2-10 CRUD, toggle, reorder, test | 7 endpoints typed in `adminAuthApi.ts` | PASS |
| **Write-Only Secrets** | Secrets omitted unless replace checked; sanitized | Verified in `adminAuthApi.ts` and `AuthCardEditorDrawer.tsx` | PASS |
| **COLLATE "C" Midpoint** | Base-62 0-9A-Za-z strict byte order | 100 sequential insertions maintain a < b order | PASS |
| **Lockout Banner** | 409 rollback, reason mapping, CLI command | Verified in `LockoutPreventedBanner.tsx` and unit tests | PASS |
| **Anti-Enumeration** | Uniform "Not found or no access" for non-admins | Verified in `AuthStudioPage.tsx` | PASS |
| **Hostile String XSS** | Literal text rendering for summaries and names | Script and image injection rendered as plain text | PASS |
| **Unit Test Coverage** | >= 95% line, branch, func, stmt coverage | 77/77 passed; **100%** lines, **96.92%** branches | PASS |
| **E2E Playwright Suite** | 18/18 passed across desktop, tablet, mobile | Clean execution with 0 console errors, 0 CSP violations | PASS |
| **Static Code Quality** | Typecheck, lint, build clean | `tsc`, `eslint`, `vite build` clean (exit code 0) | PASS |
| **Typography Standard** | Plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

## 2. Deep Technical & Security Invariant Audits

### 2.1 Write-Only Secrets & Defensive Response Sanitization (`adminAuthApi.ts`, `AuthCardEditorDrawer.tsx`)
- **Drawer Input Guard**:
  ```tsx
  {card?.has_secret && (
    <div className="auth-editor-prop-row">
      <label className="auth-editor-checkbox-label">
        <input
          type="checkbox"
          checked={replaceSecret}
          onChange={(e) => setReplaceSecret(e.target.checked)}
        />
        Replace stored secret
      </label>
    </div>
  )}
  ```
  When editing, `secretInput` is only populated and submitted if `replaceSecret` is explicitly checked. On submit, form state is cleared in `finally`.
- **Defensive Pruning**:
  ```ts
  const FORBIDDEN_SECRET_KEYS = [
    'client_secret',
    'bind_dn_password',
    'encrypted_secret_blob',
    'wrapped_dek',
  ] as const;

  export function sanitizeAdminAuthCard(card: AdminAuthCard): AdminAuthCard {
    const sanitizedRecord: Record<string, unknown> = { ...card };
    for (const key of FORBIDDEN_SECRET_KEYS) {
      Reflect.deleteProperty(sanitizedRecord, key);
    }
    const config: Record<string, unknown> = { ...card.public_config };
    for (const key of FORBIDDEN_SECRET_KEYS) {
      Reflect.deleteProperty(config, key);
    }
    return { ...sanitizedRecord, public_config: config } as AdminAuthCard;
  }
  ```
  Any accidental leak from server or mock responses is pruned prior to application consumption.

### 2.2 Base-62 Lexicographic Midpoint Ranks (`cardRank.ts`)
- **Alphabet**: `0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz`.
- Character indices correspond directly to ASCII integer values: `0-9` (48-57), `A-Z` (65-90), `a-z` (97-122).
- Comparison matches PostgreSQL `COLLATE "C"` binary byte order.
- Unit test `cardRank.test.ts` validates:
  * Insertion at top (`midpointRank(null, next)`).
  * Insertion at bottom (`midpointRank(prev, null)`).
  * Insertion between adjacent cards (`midpointRank(prev, next)`).
  * 100 sequential insertions maintain strict monotonic order without collision.

### 2.3 Lockout Safeguards & Emergency Break-Glass (`LockoutPreventedBanner.tsx`)
- On HTTP 409 with `code === 'LOCKOUT_PREVENTED'`, the application:
  1. Reverts optimistic switch toggle state or deletion in UI.
  2. Directs screen reader focus to `role="alert"` banner.
  3. Displays reason copy corresponding to `ZERO_ADMIN_CARDS` or `HANDSHAKE_STALE_FOR_LOCAL_DISABLE`.
  4. Provides copyable command: `kanban-ctl auth emergency-unlock --enable-local-admin`.

---

## 3. Test Coverage & Verification Results

### 3.1 Unit Test Coverage
- **Suite**: `pnpm --dir kanban/web exec vitest run --coverage src/features/admin-auth`
- **Results**: 4 test files, 77/77 tests passed in 4.58s.
  * Statements: **99.40%** (threshold >= 95%)
  * Branches: **96.92%** (threshold >= 95%)
  * Functions: **98.56%** (threshold >= 95%)
  * Lines: **100.00%** (threshold >= 95%)

### 3.2 End-to-End Playwright Validation
- **Suite**: 18/18 scenarios passed across Desktop, Tablet, and Mobile viewports in 21.5s.
- **Coverage**: Card list ordering, drag/keyboard reordering, write-only secret editing, test handshake status updates, lockout prevented alert banners, and non-admin empty states.

---

## 4. Verdict

The implementation of `KANBA-134` (`KB-P3-36`) satisfies all architectural, security, and wire contract requirements.

**VERDICT: APPROVED**

Signed,
`@arch-reviewer`
Systems/Backend Architect & API Specialist
