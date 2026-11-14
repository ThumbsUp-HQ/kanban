# API Specialist Gate Review: KANBA-114 (KB-P3-49)

- **Ticket**: `KANBA-114` (`KB-P3-49`: `[Phase 3 / Frontend] Effective Access Inspector popover: Users, Groups, Agents kill-switch, Deny overrides & redaction`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Worktree**: `/tmp/kb-wt-KANBA-114`
- **Branch**: `feat/KANBA-114` (commit `6343fb0`)
- **Verdict**: **APPROVED**

---

## 1. Executive Summary & Verification Matrix

As Systems/Backend Architect & API Specialist, I have conducted a rigorous architectural and API consumption audit of `KANBA-114` (`KB-P3-49`), implementing the Effective Access Inspector popover according to specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (Sections 3.4, 3.2, 6.1, 6.2).

The implementation satisfies all architectural, API contract, security, anti-enumeration, and CSRF requirements:
- **API Wire Contract Consumption (`GET /api/v1/objects/{id}/access`)**: Consumes the full `AccessManifest` model (inherited scope, direct users, synced groups, active agents, deny overrides, and caller capabilities) with clean fallback and optimistic updates.
- **Anti-Enumeration Redaction Invariant (S3.4 item 2, S3.5)**: Out-of-boundary principals marked with `redacted: true` (or enumerated in `redacted_count`) render strictly as `<N> External Collaborator(s) - outside your visibility boundary` (or `"1 External Collaborator"`). Any leaked fields on redacted entries (such as email or handle) are strictly pruned and never emitted to the DOM.
- **Indistinguishable 403/404 Parity (S3.4, S3.5)**: HTTP 403 Forbidden and 404 Not Found return byte-identical client error messaging (`Object was not found or you do not have access.`), eliminating object existence oracles.
- **Agent Kill Switch Hook & CSRF Protection (S3.2, S3.4)**: `AgentKillSwitchControl` enforces 2-step inline confirmation with default focus on Cancel to prevent accidental activation; dispatches `POST /api/v1/objects/{id}/access/agent-kill-switch` with mandatory `X-CSRF-Token`; executes optimistic agent revocation with deterministic rollback on network or server failure.
- **Input Sanitization & Egress Protection**: UUID validation via strict regex `/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i` rejects malformed strings and path-traversal inputs before initiating network calls.

| Verification Dimension | Specification Target | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **API Manifest Model** | S3.4 full access manifest consumption | `types.ts` & `AccessInspectorPopover.tsx` cleanly deserialize all 5 sections | PASS |
| **Anti-Enumeration** | S3.4 item 2 zero principal leakage | Redacted rows render `"1 External Collaborator"`; extra fields pruned | PASS |
| **Hostile Input & XSS** | React text child nodes; zero HTML injection | Group name `<img src=x onerror=alert(1)>` renders literal text | PASS |
| **Existence Oracle Defense** | S3.4 byte-identical 403/404 handling | Uniform string: `"Object was not found or you do not have access."` | PASS |
| **CSRF on Mutations** | Double-submit CSRF protection on POST | `apiFetch` transmits `X-CSRF-Token` header on kill-switch mutation | PASS |
| **Optimistic Rollback** | Immediate state update + rollback on error | Optimistic empty `agents: []` with rollback announcement on 500 | PASS |
| **Input Validation** | Canonical UUID format validation | Strict regex `/^[0-9a-f]{8}-...-[0-9a-f]{12}$/i` rejects non-UUIDs | PASS |
| **Role Gating** | Caller capabilities determine controls | Non-admin callers see zero kill-switch and manage-access buttons | PASS |
| **Unit Test Coverage** | >= 95% lines, branches, funcs, stmts | 22/22 passed in 2.18s; **100%** lines, **96.57%** branch coverage | PASS |
| **Static Code Quality** | Zero compiler, linter, or type errors | `tsc -b --noEmit`, `eslint`, `vite build` clean (exit code 0) | PASS |
| **Typography Standard** | Plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

## 2. Deep Technical & Security Invariant Audits

### 2.1 API Consumption & Capability Gating (`GET /api/v1/objects/{id}/access`)
- **Query Key & Lifecycle**: `AccessInspectorPopover.tsx` uses `useQuery` bound to `qk.access(objectId)` with standard query configuration.
- **Capability-Gated Surface Controls**:
  * `[Manage Access...]` button: Only mounted when `caller_capabilities` contains `'SHARE'` or `'ADMIN'`. Dispatches `kb:open-manage-access` custom event.
  * `[ Kill Switch ]` button: Only mounted when `caller_capabilities` contains `'ADMIN'` AND active agents count > 0.
  * When caller holds only `VIEW` or `COMMENT`, administrative controls are completely absent from the DOM, not hidden via CSS.

### 2.2 Anti-Enumeration Redaction & XSS Defense (S3.4, S5.4)
- **Redaction Sanitization**: In `AccessInspectorPopover.tsx`, the redacted section renders:
  ```tsx
  {hasRedacted && (
    <section className="access-inspector__section">
      {hasRedactedEntries ? (
        (manifest.redacted_entries ?? []).map((entry, idx) => (
          <div key={`redacted-${String(idx)}`} className="access-inspector__row access-inspector__row--redacted">
            <span className="access-inspector__redacted-label">
              {formatRedactedLabel(manifest.redacted_count, entry.label)} - outside your visibility boundary
            </span>
          </div>
        ))
      ) : (
        <div className="access-inspector__row access-inspector__row--redacted">
          <span className="access-inspector__redacted-label">
            {formatRedactedLabel(manifest.redacted_count)} - outside your visibility boundary
          </span>
        </div>
      )}
    </section>
  )}
  ```
- **Defense-in-Depth Leak Proof**: Even if an upstream API bug were to serialize private fields (e.g., `email: "secret@vendor.io"`), the component only ever references `entry.label`. Unit test `AccessInspectorPopover.test.tsx` verifies that `secret@vendor.io` is never present anywhere in `document.body.textContent`.
- **XSS Immunity**: Hostile principal names (e.g. `<img src=x onerror=alert(1)>`) are passed directly into React string children (`<span>{group.name}</span>`), preventing DOM script execution (`querySelector('img') === null`).

### 2.3 Indistinguishable 403 / 404 Response Handling (S3.4)
- When a caller lacks access to an object, or when an object does not exist, the component catches the failure and renders:
  ```tsx
  {isError && (
    <div className="access-inspector__error" role="alert">
      Object was not found or you do not have access.
    </div>
  )}
  ```
- Both HTTP 403 and 404 trigger `isError`, outputting the byte-identical string without revealing whether the target UUID exists in the system.

### 2.4 Agent Kill Switch Hook & CSRF Defense (`POST .../access/agent-kill-switch`)
- **Safety Interlock**: `AgentKillSwitchControl.tsx` provides a 2-step inline confirmation banner (`Revoke all active agent grants on <CANONICAL_KEY>?`).
- **Focus Safety**: When confirmation opens, focus is explicitly set to `cancelButtonRef.current?.focus()`. This prevents a rapid press of the Enter key from triggering unintended destructive revocation.
- **CSRF Token Attachment**: Calls `apiFetch('POST', '/api/v1/objects/{object_id}/access/agent-kill-switch', ...)`, which automatically attaches `X-CSRF-Token` from document cookies (`__Host-kb_csrf` / `kb_csrf`).
- **Optimistic Update & Deterministic Rollback**: Uses `useOptimisticMutation` (`KB-P3-33`) to set `manifest.agents = []`. If the mutation fails (e.g., 500 Internal Server Error), the cache automatically reverts to the original agent list and announces `Failed to revoke agent grants. Reverting changes.` to screen readers via `role="status"`.

### 2.5 UUID Input Sanitization & Shell Integration (`useAccessInspector.ts`)
- **Regex Validation**:
  ```ts
  export const UUID_REGEX =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  ```
- **Fail-Closed Target Parsing**: `parseAccessTarget()` tests both string arguments and `{ objectId, anchorEl }` detail payloads against `UUID_REGEX`. Invalid formats (such as path traversal strings like `../../admin`) return `null`, immediately suppressing popover mounting and making zero HTTP requests.

---

## 3. Test Coverage & Verification Results

### 3.1 Unit Test Suite (`vitest`)
Executed `pnpm --dir kanban/web exec vitest run --coverage --coverage.include="src/features/access/**" src/features/access`:
- **Files**: 3/3 passed (`AccessInspectorPopover.test.tsx`, `AgentKillSwitchControl.test.tsx`, `useAccessInspector.test.tsx`).
- **Tests**: 22 passed, 0 failures (runtime 2.18s).
- **Statements**: **100.00%** (exceeds >= 95% threshold).
- **Branches**: **96.57%** (exceeds >= 95% threshold).
- **Functions**: **100.00%** (exceeds >= 95% threshold).
- **Lines**: **100.00%** (exceeds >= 95% threshold).

### 3.2 Production Build, Typecheck, and Lint
- `pnpm --dir kanban/web typecheck` (`tsc -b --noEmit`): 0 errors.
- `pnpm --dir kanban/web lint` (`eslint . --max-warnings 0`): 0 errors, 0 warnings.
- `pnpm --dir kanban/web build` (`tsc -b && vite build`): Clean build in 1.20s (exit code 0).

### 3.3 Playwright E2E & Style Probes
- `playwright test e2e/access/access-inspector.spec.ts`: 9/9 passed across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844).
- Verified computed styles: `.access-inspector` width 520px (max-height 680px), `.access-inspector__row` min-height 38px (`--prop-row-h`), `.emoji-hint` 24px x 24px, `--danger-fg` on `--danger-bg` contrast >= 4.5:1.

### 3.4 Dash Standard Compliance
- `python3 scripts/check_no_dashes.py --all`: 0 non-ASCII dashes detected.

---

## 4. Final Architectural Sign-Off

The `KANBA-114` (`KB-P3-49`) implementation adheres to all backend architecture, API consumption, anti-enumeration, and CSRF protection specifications. The API Specialist Gate requirements are completely satisfied.

**VERDICT: APPROVED**
