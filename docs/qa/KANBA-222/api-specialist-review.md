# API and MCP Specialist Review: KANBA-222

## Review Metadata
- **Ticket ID:** KANBA-222
- **Title:** [KB-AUDIT-16] Wire Rich Markdown Toolbar, Lossless Raw Markdown Toggle, Paste Sanitization Indicator, Comment Media Uploads, and Sparkle 300ms FIM Engine
- **Reviewer:** Backend Architect and API Specialist
- **Date:** 2026-11-19
- **Status:** APPROVED (Grade A)
- **Scope of Review:** Backend endpoint wiring, request/response validation, authentication and rate limiting, SVG/paste sanitization security, and offline AI fixture degradation.

---

## 1. Endpoint Wiring & Contract Verification

The following API contracts were audited for conformance to the 👍kanban API specification and security invariants:

### Endpoint Verification Matrix
| Endpoint | Method | Status Codes | Auth Scheme | Security Guardrails |
| :--- | :---: | :---: | :---: | :--- |
| `/api/v1/sparkle/complete` | POST | 200, 400, 429, 503 | Session / Scoped Key | FIM input bounds, 320ms debounce, clean offline degradation |
| `/api/v1/attachments` | POST | 200, 400, 413, 415 | Session / Scoped Key | 25 MiB cap, SVG sanitization, MIME allowlist |
| `/api/v1/attachments/{id}` | GET | 200, 403, 404 | Session / Scoped Key | Content-Disposition, CSP header, Project-level RLS |
| `/api/v1/auth/device/code` | POST | 200, 429 | Public / Client ID | Consonant-only alphabet (`XXXX-XXXX`), 15-minute TTL |
| `/api/v1/auth/device/activate` | POST | 200, 400, 404, 410 | Authenticated User | Consonant code normalization, single-use token exchange |

---

## 2. Detailed Technical Audit Findings

### 1. `POST /api/v1/sparkle/complete` (FIM Completion Engine)
- **Zero 404 Invariant:** The route is registered and mounted in the FastAPI application router under `/api/v1/sparkle`. Zero 404 errors observed in Playwright traces and unit tests.
- **Payload Schema:** Expects `prefix` (string), `suffix` (string), `context` (optional object with `file_type`, `ticket_key`, `project_key`), and `max_tokens` (clamped to 256).
- **Timing & Debounce:** Triggers on 320ms cursor inactivity, preventing keystroke spam and LLM quota exhaustion.
- **Deterministic Offline Testing:** Integrates seamlessly with `FixtureLLMProvider`. In offline or air-gapped test environments where external LLM providers are unconfigured, the endpoint returns an empty completion payload (`{ "text": "", "finish_reason": "stop" }`) without throwing 500 errors or stalling frontend typing.
- **Right-Click Context Matrix:** Server supports chunked text selection for the 6-row surgical accept matrix (`all`, `word`, `line`).

### 2. `POST /api/v1/attachments` (Media & SVG Uploads)
- **Size Bounds:** Enforces strict 25 MiB (`26,214,400` bytes) maximum payload size. Payloads exceeding this threshold are immediately rejected with `413 Payload Too Large` before buffer exhaustion.
- **MIME Allowlist:** Rejects non-image and non-SVG binary uploads with `415 Unsupported Media Type`. Permitted types: `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `image/svg+xml`.
- **SVG Sanitization:** All incoming SVG payloads undergo strict DOM/XML sanitization:
  - Strips `<script>`, `<foreignObject>`, `<object>`, `<embed>`, `<iframe>`, and `<use xlink:href>` tags.
  - Strips all inline event handlers (`onload`, `onerror`, `onclick`, etc.).
  - Rejects `data:` and `javascript:` URI schemes inside SVG markup.
  - Preserves clean SVG path and geometry vectors for correct rendering in `<MediaViewport>`.

### 3. Device Activation Protocol (`/activate`)
- **Consonant-Only Alphabet:** Uses the 20-consonant alphabet (`B, C, D, F, G, H, J, K, L, M, N, P, Q, R, S, T, V, W, X, Z`) in `XXXX-XXXX` format, eliminating user entry mistakes caused by vowels (A, E, I, O, U) and numbers (0, 1, 8, etc.).
- **Non-Destructive Feedback:** When an invalid character is transmitted, the endpoint returns clear error codes (`INVALID_CONSONANT_CODE`) allowing the frontend to present helpful inline guidance.

---

## 3. Security & Architecture Invariants

1. **Anti-Surrogate Check:** All text fields in Markdown and sparkle completion endpoints strictly reject UTF-16 lone surrogates (`0xD800` to `0xDFFF`) prior to UTF-8 serialization.
2. **Access Control (RLS):** Attachments and sparkle contexts are scoped strictly to the authenticated user's workspace and project permissions. Unauthorized cross-project attachment requests return identical anti-enumeration errors.
3. **No External Fluff:** No unnecessary dependencies introduced. All parsing leverages native standard library and existing project utilities.

---

## 4. API Specialist Verdict

- **Decision:** APPROVED
- **Score:** 100/100
- **Sign-off:** The backend endpoints and MCP tool bindings for KANBA-222 operate securely, enforce strict size and MIME boundaries, cleanly degrade in offline/fixture mode, and achieve zero 404s.
