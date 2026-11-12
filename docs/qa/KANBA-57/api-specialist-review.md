# API Specialist Gate Independent Forensic Audit: KANBA-57 (KB-P2-01)

- Ticket: `KANBA-57` (`KB-P2-01`)
- Title: FastAPI v1 router skeleton, RFC 7807 error model, request-id, key material provider & RLS request dependency
- Epic: `KB-E2` (Phase 2 Kanban API & Core Business Engine)
- Auditor: `arch-reviewer` (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Date: 2026-11-12
- Worktree: `/tmp/kb-wt-KANBA-57` on branch `feat/KANBA-57` (commit `61ebeab`)
- Scope: Independent forensic audit of the `/api/v1` router skeleton, canonical RFC 7807 problem details model (`application/problem+json`), anti-enumeration 404 timing equalization engine, pure ASGI request-id middleware, cryptographic key material provider (`KeyMaterial`, HKDF `derive_subkey`), and fail-closed RLS session dependency.

---

### 1. Executive Summary & Verification Matrix

An independent forensic API and systems architecture audit of `KANBA-57` (`KB-P2-01`) was conducted across all 8 target modules in `kanban/api/` and `kanban/security/`, application factory wiring in `kanban/app.py`, 39 feature and security unit tests, live response captures in `contract-sample.json`, and statistical timing data in `timing-equalization.txt`.

The implementation satisfies all architectural, security, and protocol requirements of `docs/tickets/KB-P2-01.md` and `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (S3.3, S3.4, S2.2 item 1).

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Router Skeleton** | `build_v1_router() -> APIRouter` mounted under `/api/v1` | Clean modular router in `kanban/api/v1/__init__.py`; single entry point | PASS |
| **Smoke Route** | `GET /api/v1/healthz` (and `/health`) returning `{"status": "ok"}` | Zero database touch; returns 200 with generated/validated `X-Request-ID` | PASS |
| **RFC 7807 Problem Model** | `application/problem+json` with `type`, `title`, `status`, `code`, `request_id` | Full compliance in `kanban/api/problems.py`; code regex `^[A-Z][A-Z0-9_]{2,63}$` | PASS |
| **Zero Stacktrace/Path Disclosure** | 500 `INTERNAL_ERROR` conceals SQL, tracebacks, and paths | Tested with simulated SQL errors; details stripped, correlated in server logs | PASS |
| **Input Sanitization on 422** | Strips submitted values from `errors` list on validation failures | `FieldError(path, message)` only; hostile payload `<script>alert(1)</script>` never echoed | PASS |
| **Anti-Enumeration 404** | 403 strictly forbidden for object reads; indistinguishable 404 | Enforced in `not_found()` with S3.4 citation; same code path in `load_or_404` | PASS |
| **Timing Equalization Floor** | `TimingFloor(floor_ms=25.0)`; statistical delta `<= 5.0ms` | 200 alternating real-app requests measured absolute median delta of `0.00ms` | PASS |
| **Request-ID ASGI Middleware** | Validate `^[A-Za-z0-9-]{8,64}$` or replace with UUIDv4 hex | Replaces invalid, oversized, or Unicode IDs; echoes clean ID in headers and problem JSON | PASS |
| **Log Injection Defense** | Inject clean `request_id` via `RequestIdFilter` | Log records decorated via `ContextVar`; header-injected CRLF stripped | PASS |
| **Key Material Provider** | `KeyMaterial` (frozen, redacted `__repr__`, 32-byte keys) | Validates `MASTER_KEK`, `KB_AUTH_PEPPER`, `SESSION_HMAC_KEY`; fails closed if missing | PASS |
| **Keyring File Security** | Mode `<= 0600`, regular file only (symlinks strictly refused) | Refuses mode `0644` and symlinks; parses base64url keys | PASS |
| **HKDF Subkey Derivation** | RFC 5869 HKDF-SHA256 with `info=b"kanban/" + purpose` | `purpose` validated against `^[a-z0-9][a-z0-9./-]{2,63}$`; purpose-separated | PASS |
| **Principal Resolution** | Fail-closed `DenyAllResolver`; 401 when unauthenticated | Zero inspection of client headers (`X-Principal-Id`, `X-Workspace-Id` ignored) | PASS |
| **RLS Session Dependency** | `get_rls_session` binds context before any statement | `SET LOCAL` context bound; commits on success, rolls back on exception | PASS |
| **Brand Rule Compliance** | FastAPI `title="👍kanban API"` (#199) | Set in `kanban/app.py`; problem URNs and headers remain clean ASCII | PASS |
| **Test Coverage & Quality** | 12 mandatory test cases; >=95% branch+line coverage | 39/39 tests pass in 6.64s; 100.00% branch and line coverage; zero warnings | PASS |

---

### 2. Detailed Technical & Security Review

#### A. RFC 7807 Error Architecture (`kanban/api/problems.py`)
1. **Problem Document Structure:**
   - `Problem` Pydantic model serializes `type` (`urn:kanban:problem:<code>`), `title`, `status`, `code`, `detail`, `request_id`, and `errors`.
   - Excludes `None` fields from serialized JSON to produce clean, compact error bodies.
   - Handlers registered on FastAPI for `ProblemException`, `RequestValidationError` (422), `StarletteHTTPException`, and generic `Exception` (500).
2. **Anti-Leakage Safeguards:**
   - Catch-all handler logs the raw exception server-side with `request_id` correlation, while the response body strictly returns `{"type": "urn:kanban:problem:INTERNAL_ERROR", "title": "Internal Server Error", "status": 500, "code": "INTERNAL_ERROR", "request_id": "<id>"}` with `detail=None`.
   - `RequestValidationError` maps validation errors to `FieldError` containing only `path` and `message`. The submitted field values are completely omitted, preventing reflected XSS and credential reflection.
3. **Anti-Enumeration Invariant (S3.4):**
   - Helper function `not_found()` raises `ProblemException(code="NOT_FOUND", status=404, title="Not Found", detail=None)`.
   - Object access layers never return 403 Forbidden on reads; non-existent and unreadable objects produce identical 404 responses.

#### B. Request ID Middleware & Tracing (`kanban/api/request_id.py`)
1. **Pure ASGI Interception:**
   - Inspects inbound `X-Request-ID` headers. Rejects values failing `^[A-Za-z0-9-]{8,64}$`, Unicode strings, and carriage returns / line feeds.
   - Generates clean 32-character hexadecimal UUIDv4 strings for missing or invalid IDs.
   - Propagates ID via `contextvars.ContextVar`, binds it to `scope["state"]["request_id"]`, and injects it into outbound HTTP response headers and problem documents.
2. **Log Correlation:**
   - `RequestIdFilter` injects `record.request_id` into all server log records without manual plumbing.

#### C. Cryptographic Key Management (`kanban/security/keys.py`)
1. **Root Key Invariants:**
   - `KeyMaterial` is an immutable, slotted dataclass containing `master_kek`, `auth_pepper`, and `session_hmac_key`.
   - All three root keys are verified to be exactly 32 bytes (256 bits).
   - `__repr__` returns `KeyMaterial(<redacted>)`, preventing accidental secret disclosure in tracebacks, debug dumps, or logs.
2. **Keyring Loading & Perms Enforcement:**
   - `load_key_material()` reads from `KANBAN_KEYRING_FILE` or environment variables `KANBAN_MASTER_KEK`, `KANBAN_AUTH_PEPPER`, `KANBAN_SESSION_HMAC_KEY`.
   - For file sources: strictly refuses symlinks, directories, or permissions broader than `0600` (fails closed if `mode & 0o077 != 0`).
3. **HKDF Subkey Derivation:**
   - `derive_subkey(root, purpose)` derives cryptographically isolated subkeys via HKDF-SHA256 with `info=b"kanban/" + purpose.encode("ascii")`.
   - Validates `purpose` against `^[a-z0-9][a-z0-9./-]{2,63}$`.
   - Prevents key reuse across different subsystems (cookies, CSRF, signed tokens).

#### D. Authentication & RLS Session Binding (`kanban/api/deps.py`)
1. **Principal Resolution:**
   - Default `DenyAllResolver` safely denies resolution, raising 401 `AUTHENTICATION_REQUIRED`.
   - Client headers (`X-Principal-Id`, `X-Workspace-Id`) and query parameters are never parsed for identity.
2. **Database Context Binding:**
   - `get_rls_session` depends on verified `PrincipalContext`.
   - Obtains an async session from `app.state.session_factory` and enters an active transaction with `SET LOCAL` context bound (`app.principal_id`, `app.workspace_id`, `app.token_scopes`, `app.aal_level`).
   - Transaction commits upon successful handler execution and rolls back on any exception.

#### E. Anti-Enumeration Timing Equalization (`kanban/api/timing.py`)
1. **Timing Floor Execution:**
   - `TimingFloor` async context manager measures monotonic execution time and sleeps `max(0.0, floor_ms - elapsed)` on exit, guaranteeing execution takes at least `floor_ms` (25.0ms) regardless of success or failure.
   - `load_or_404(session, stmt)` executes the RLS-filtered query and calls `not_found()` when `scalar_one_or_none()` is None, ensuring non-existent and unreadable objects follow the identical execution path.
2. **Statistical Proof:**
   - Automated test case 10 ran 200 alternating requests against the live application.
   - Group A (non-existent object): median 28.76ms, p95 29.64ms.
   - Group B (unreadable object hidden by RLS): median 28.75ms, p95 29.90ms.
   - Absolute median delta: `0.00ms` (significantly below the `<= 5.0ms` threshold).

---

### 3. Verdict

The implementation of `KANBA-57` (`KB-P2-01`) is impeccable, architecturally hardened, strictly zero-leak, and fully compliant with all security and API requirements.

**Gate Verdict:** **`APPROVED`**
