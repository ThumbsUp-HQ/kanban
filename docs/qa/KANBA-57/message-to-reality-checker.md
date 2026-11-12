# Reality-Checker Verification Packet: KANBA-57 (KB-P2-01)

## Ticket Metadata
- Ticket ID: `KANBA-57`
- Spec Key: `KB-P2-01`
- Title: `[Phase 2 / Kanban API] FastAPI v1 router skeleton, RFC 7807 error model, request-id, key material provider & RLS request dependency`
- Epic: `KB-E2` (Phase 2 Kanban API & Core Platform Services)
- Spec Sections: `3.3` (`SET LOCAL` context binding under `kanban_app`), `3.4` item 2 (indistinguishable `404`, `<= 5.0ms` jitter), `2.2` item 1 (key names `MASTER_KEK`, `KB_AUTH_PEPPER`, `SESSION_HMAC_KEY`), Requirement `#1`
- Dependencies: `KB-P1-17`, `KB-P0-10`
- Gate: `reality-checker` (Passive Forensic Mode), `api-specialist`, `ui-specialist`

---

## User Story
As a **kanban API engineer**, I need **a single `/api/v1` router tree whose every request runs inside an RLS-bound database transaction, returns RFC 7807 problem documents, carries a validated request id, and answers unreadable objects with a timing-equalized `404`** so that **every later endpoint inherits principal binding, anti-enumeration and non-leaking errors by construction instead of by convention**.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** `kanban/api/problems.py`, `kanban/api/request_id.py`, `kanban/api/deps.py`, `kanban/api/timing.py`, `kanban/api/v1/__init__.py`, `kanban/api/v1/health.py`, `kanban/security/keys.py` exist and define `Problem`, `ProblemException`, `not_found`, `PrincipalContext`, `PrincipalResolver`, `DenyAllResolver`, `get_principal`, `get_rls_session`, `timing_floor`, `load_or_404`, `KeyMaterial`, `load_key_material`, `derive_subkey`, `build_v1_router`.
- [x] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api kanban/tests/security/test_keys.py -q --cov=kanban/api --cov=kanban/security/keys.py --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with `0` failures and all 12 cases present (39 passed, 100.00% branch and line coverage across all 8 target modules).
- [x] **Build / Type / Lint Clean:** `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict kanban && uv run lint-imports` exits `0`.
- [x] **No principal from client input:** `grep -rn "X-Principal\|X-Workspace" kanban/api` returns zero code matches (only present in negative security test assertions).
- [x] **No Forbidden Unicode Dashes:** Repository passes `uv run python -m scripts.check_no_dashes --all` with zero violations.
- [x] **License Gate Clean:** `make license` passes with 0 violations.
- [x] **Forensic Proof Packet Complete:** All required proof files exist under `docs/qa/KANBA-57/`.

---

## Mandatory Feature Unit Tests Matrix (12/12 Covered)

| Case | Category | Test Target | Verification Description |
| :--- | :--- | :--- | :--- |
| **Case 1** | Positive Smoke | `kanban/tests/api/test_request_id.py::test_case_1_healthz_generates_32_hex_id` | `GET /api/v1/healthz` returns 200 `{"status": "ok"}` with generated 32-hex `X-Request-ID`. |
| **Case 2** | Positive RLS | `kanban/tests/api/test_rls_dependency.py::test_case_2_positive_rls_session_context_binding` | Test route using `get_rls_session` observes `current_setting('app.principal_id')` equal to stub principal inside request. |
| **Case 3** | Security (Anti-Spoofing) | `kanban/tests/api/test_rls_dependency.py::test_case_3_security_header_spoofing_denied` | Inbound request with `X-Principal-Id`, `X-Workspace-Id`, `?principal_id=` and default `DenyAllResolver` returns 401 `AUTHENTICATION_REQUIRED`; DB session factory never called. |
| **Case 4** | Security (Context Leak) | `kanban/tests/api/test_rls_dependency.py::test_case_4_security_context_leak_and_pool_isolation` | Sequential requests with different principals on 1-conn pooled connection; second request sees only its own principal; connection returned to pool has `app.principal_id` cleared. |
| **Case 5** | Security (Error Leak) | `kanban/tests/api/test_problems.py::test_case_5_security_error_disclosure` | Route raising internal error returns 500 `INTERNAL_ERROR` problem document; body contains none of `SELECT`, `/srv/`, `RuntimeError`, `Traceback`, `secret`; `X-Request-ID` is echoed. |
| **Case 6** | Security (XSS / Input Echo) | `kanban/tests/api/test_problems.py::test_case_6_security_validation_echo` | 422 body for `<script>alert(1)</script>` strips user input; `FieldError` has path and message only. |
| **Case 7** | Security (Log Injection) | `kanban/tests/api/test_request_id.py::test_case_7_security_request_id_log_injection` | Malformed inbound `X-Request-ID` values (CRLF, Unicode, oversize, whitespace) replaced with clean 32-hex UUIDv4; valid `req-0123456789` echoed unchanged. |
| **Case 8** | Anti-Enumeration | `kanban/tests/api/test_timing.py::test_case_8_anti_enumeration_identical_response` | Route using `load_or_404` + `timing_floor` returns identical status (404), headers, and body for random UUID vs existing object unreadable under PostgreSQL RLS. |
| **Case 9** | Timing (Deterministic) | `kanban/tests/api/test_timing.py::test_case_9_deterministic_timing_floor` | `timing_floor` with fake clock sleeps exactly `floor - elapsed`, 0 when elapsed > floor, and executes sleep on exception. |
| **Case 10** | Timing (Statistical) | `kanban/tests/api/test_timing.py::test_case_10_statistical_timing_equalization` | 200 alternating requests (100 non-existent, 100 unreadable) against real app show `abs(median(a) - median(b)) = 0.05ms <= 5.0ms`. |
| **Case 11** | Key Material Constraints | `kanban/tests/security/test_keys.py::test_case_11_*` | Keyring file loads; mode 0644 rejected; symlink rejected; 31-byte key rejected; missing source rejected; `repr(KeyMaterial)` masks all key bytes. |
| **Case 12** | HKDF Subkey Separation | `kanban/tests/security/test_keys.py::test_case_12_*` | `derive_subkey(k, "session/cookie") != derive_subkey(k, "session/csrf")`; invalid purpose raises `ValueError`; RFC 5869 Test Case 1 test vector matches. |

---

## Technical Actions & Implementation Matrix

| Component | Target Location | Description |
| :--- | :--- | :--- |
| **Package Exports** | `kanban/api/__init__.py` | Clean re-exports of all API primitives, problem classes, request ID middleware, timing helpers, and router builder. |
| **RFC 7807 Error Model** | `kanban/api/problems.py` | `FieldError`, `Problem` (`application/problem+json`), `ProblemException`, `not_found()` raising 404 with S3.4 anti-enumeration rule comment, and handlers for `ProblemException`, `RequestValidationError` (422), `StarletteHTTPException`, and catch-all `Exception` (500). |
| **Request ID Middleware** | `kanban/api/request_id.py` | Pure ASGI `RequestIdMiddleware` validating `^[A-Za-z0-9-]{8,64}$` or generating 32-hex UUIDv4 tokens, `ContextVar[str]` propagation, `get_request_id()`, and `RequestIdFilter`. |
| **Key Material Provider** | `kanban/security/keys.py` | `KeyMaterial` (frozen, redacted `__repr__`, 32-byte checks), `KeyMaterialError`, `load_key_material` (mode <= 0600, non-symlink JSON file or env vars), `derive_subkey` via HKDF-SHA256 (`info=b"kanban/" + purpose`). |
| **Security Module Exports** | `kanban/security/__init__.py` | Re-exports `KeyMaterial`, `KeyMaterialError`, `load_key_material`, and `derive_subkey` with PEP 562 lazy loading to avoid premature import during test setup. |
| **RLS Request Dependency** | `kanban/api/deps.py` | `PrincipalContext`, `PrincipalResolver`, default `DenyAllResolver`, `get_principal` (401 on unauthenticated; client headers strictly ignored), `get_rls_session` yielding session from `RLSSessionFactory`. |
| **Timing Equalization** | `kanban/api/timing.py` | `TimingFloor` context manager enforcing `floor_ms = 25.0` via `asyncio.sleep`, `timing_floor` helper, and `load_or_404(session, stmt)` helper raising 404 on None. |
| **Smoke Router & V1 Root** | `kanban/api/v1/health.py`, `kanban/api/v1/__init__.py` | `GET /api/v1/healthz` and `/health` returning `{"status": "ok"}` with zero DB access; `build_v1_router()` assembling v1 subrouters. |
| **App Assembly** | `kanban/app.py` | Updated `title="👍kanban API"`, registered `RequestIdMiddleware`, registered problem handlers, mounted `build_v1_router()` under `/api/v1`, initialized `principal_resolver` and `session_factory` state defaults. |
| **Module Manifest** | `kanban/GEMINI.md` | Updated module responsibilities, inbound/outbound contracts, 25.0ms timing floor budget, and failure modes. |

---

## Forensic Proof Artifacts in `docs/qa/KANBA-57/`
1. `git-diff.patch`: Complete unified `git diff` for this ticket.
2. `unit-test-results.txt`: Raw output and exit code of `pytest kanban/tests/api kanban/tests/security/test_keys.py -q --cov=kanban/api --cov=kanban/security/keys.py --cov-branch --cov-report=term-missing --cov-fail-under=95` (39 passed in 6.80s, 100.00% coverage, EXIT=0).
3. `build-check.txt`: Raw output of `ruff check .`, `ruff format --check .`, `mypy --strict kanban`, and `lint-imports` (all checks passed, 41 source files clean, 1 contract kept 0 broken, EXIT=0).
4. `contract-sample.json`: Captured live HTTP responses (headers + parsed JSON body) for `401 AUTHENTICATION_REQUIRED`, `422 VALIDATION_FAILED`, and `500 INTERNAL_ERROR`.
5. `timing-equalization.txt`: Empirical measurement report of 200 alternating requests showing delta of `0.05ms` (well below the `<= 5.0ms` threshold).
6. `api-specialist-review.md`: Verbatim review and approval by API Specialist (`@arch-reviewer`).
7. `ui-specialist-review.md`: Verbatim review and approval by UI Specialist (`@ui-specialist`).
8. `message-to-reality-checker.md`: This forensic sign-off document.
