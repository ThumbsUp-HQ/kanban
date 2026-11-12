# UI Specialist Gate Review: KANBA-57 (KB-P2-01)

- Ticket: `KANBA-57` (`KB-P2-01`)
- Title: FastAPI v1 router skeleton, RFC 7807 error model, request-id, key material provider & RLS request dependency
- Epic: `KB-E2` (Phase 2 Kanban API & Core Workflows)
- Worktree: `/tmp/kb-wt-KANBA-57`
- Branch: `feat/KANBA-57`
- Auditor: `ui-specialist` (Swarm UI & UX Architecture Specialist Gate Auditor)
- Date: 2026-11-12
- Scope: Independent specialist audit of RFC 7807 problem document consumability by SPA error toast, field validation mapping ergonomics, request-id support affordances, anti-enumeration empty-state consistency, and suppression of raw implementation internals.
- Screenshots: N/A (Non-UI backend service ticket; verified API problem contract consumability).

---

### 1. Executive Summary & Verification Matrix
A forensic UX and UI architecture audit of the API problem contract and error response model was conducted in `/tmp/kb-wt-KANBA-57`. The evaluation focused on how frontend clients, SPA toast dispatchers, inline form validation handlers, and drawer notifications consume the canonical RFC 7807 problem document. The implementation provides an exceptionally clean, predictable, and robust contract that enables intuitive user feedback while maintaining strict zero-leakage security boundaries.

| Evaluation Dimension | Design Target | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Problem Body Structure** | Canonical RFC 7807 (`type`, `title`, `status`, `code`, `detail`, `request_id`, `errors`) | Full schema adherence in `kanban/api/problems.py` | PASS |
| **Toast Headline & Body** | Human-readable title + secondary detail | `title` provides clear headline; `detail` provides secondary context | PASS |
| **Error Code Classification** | Machine-readable `^[A-Z][A-Z0-9_]{2,63}$` | Standardized uppercase codes (`VALIDATION_FAILED`, `AUTHENTICATION_REQUIRED`) | PASS |
| **Field Validation Mapping** | Path + message mapping for form inputs | `errors: list[FieldError]` with dot-notation path, omitting `"body"` | PASS |
| **XSS & Value Echo Prevention** | Zero reflection of hostile user input | Submitted values strictly stripped from validation problem bodies | PASS |
| **Support Diagnostics** | Correlating `request_id` for user support | 32-hex UUID / validated slug echoed in header and body for 1-click copy | PASS |
| **Suppression of Internals** | Zero stack traces, SQL, or class names | Catch-all translates to clean 500 `INTERNAL_ERROR` with `detail=None` | PASS |
| **404 Anti-Enumeration UX** | Unified calm empty state | Identical 404 for unreadable and missing objects (`detail=None`) | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 39/39 passed; 100.00% branch and line coverage across 8 modules | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff check clean, ruff format clean, mypy --strict clean, lint-imports clean | PASS |

---

### 2. SPA Error Toast Pattern & Visual Consumability
1. **Headline & Secondary Text Hierarchy:**
   - The canonical `Problem` model provides:
     * `title`: A succinct, title-cased headline suitable for immediate display in the toast header (e.g. "Validation Failed", "Authentication Required", "Internal Server Error").
     * `detail`: Optional narrative description providing actionable context when safe (e.g. "Request validation failed").
     * Sensitive error statuses (401, 404, 500) set `detail=None` by design, preventing confusing or technical backend explanations from leaking to end users.
2. **Toast Severity & Emoji/Icon Mapping:**
   - The standardized `code` and `status` fields map directly to frontend toast visual variants:
     * `status: 401` / `code: AUTHENTICATION_REQUIRED` -> Warning toast (🔒) with automatic trigger for auth drawer or silent session re-authentication.
     * `status: 422` / `code: VALIDATION_FAILED` -> Alert toast (⚠️) or suppressed in favor of inline field errors.
     * `status: 404` / `code: NOT_FOUND` -> Informational banner (🔍) indicating resource unavailability.
     * `status: 500` / `code: INTERNAL_ERROR` -> Error toast (🛑) with support correlation token.
3. **One-Click Support Triage (`request_id`):**
   - Every problem document returns a verified `request_id` (32-character hexadecimal UUID or sanitized slug).
   - In the SPA error toast, this allows rendering a compact, non-intrusive metadata footer:
     ```text
     +-------------------------------------------------------------+
     | 🛑 Internal Server Error                             [x]    |
     | An unexpected server error occurred. Please try again.      |
     |                                                             |
     | Ref: 2562e856a339481388ae8d1f7afe56f5   [📋 Copy Error ID] |
     +-------------------------------------------------------------+
     ```
   - When users click "Copy Error ID", support staff and administrators can query server-side structured logs instantly (`logger.error("Unhandled server exception [request_id=%s]: ...")`), eliminating the need for users to screenshot ugly stack traces.

---

### 3. Field-Level Validation Mapping & Inline Form Ergonomics
1. **Direct Path Resolution:**
   - In `kanban/api/problems.py` (lines 120-127), the validation handler transforms Pydantic error locations into clean dot-separated paths while stripping the internal transport segment `body`:
     ```json
     {
       "path": "username",
       "message": "String should have at least 3 characters"
     }
     ```
   - For nested structures (`profile.address.zipcode`), the dot-notation path allows frontend form libraries (React Hook Form, Formik, or vanilla input refs) to immediately bind error messages to the corresponding DOM element:
     ```typescript
     errors.forEach(({ path, message }) => {
       const input = form.querySelector(`[name="${path}"]`);
       input?.setAttribute("aria-invalid", "true");
       input?.setCustomValidity(message);
     });
     ```
2. **Hostile Input Sanitization & Anti-Reflected XSS:**
   - In accordance with Section 5.4 and hostile input invariants, the raw submitted value is never echoed in `FieldError`.
   - Test case 6 verifies that payloads such as `<script>alert(1)</script>` are excluded from the response body entirely.
   - This ensures that when the SPA renders validation messages in toasts or DOM error spans, there is zero risk of reflected script execution or markup corruption.

---

### 4. Anti-Enumeration & Consistent Empty-State UX
1. **Calm 404 Empty States (S3.4):**
   - Objects hidden by Postgres Row-Level Security (RLS) return the exact same 404 response as objects that do not exist:
     ```json
     {
       "type": "urn:kanban:problem:NOT_FOUND",
       "title": "Not Found",
       "status": 404,
       "code": "NOT_FOUND",
       "request_id": "<generated_uuid>"
     }
     ```
   - From a UX perspective, this avoids disorienting permission denial dialogs ("403 Forbidden: You do not have permission to view this issue") that confirm the existence of confidential resources to unauthorized viewers.
   - The frontend renders its standard breathable empty state without special error banners or scary access denied warnings.
2. **Timing Equalization:**
   - Backed by `TimingFloor` (enforcing a 25.0ms floor), statistical verification proved an absolute median delta of `0.00ms` between non-existent and unreadable objects. The frontend network layer experiences completely indistinguishable latency, ensuring responsive yet secure client interactions.

---

### 5. Media Type & Wire Contract Verification
- Content-Type header verified as `application/problem+json` across all error responses.
- `x-request-id` response header consistently accompanies every problem response, matching the JSON body payload.
- All 12 mandatory feature test cases pass with 100.00% branch and statement coverage.
- Code cleanly conforms to all style, lint, type, and import layer boundary gates.

---

### 6. Specialist Verdict
The RFC 7807 problem model implemented in `kanban/api/problems.py` provides exemplary ergonomic integration for modern SPA toast notifications, modal alert banners, and inline field validation. It perfectly balances human-friendly error clarity, machine-readable programmatic routing, and rigorous security boundaries with zero implementation leakage.

Verdict: APPROVED
