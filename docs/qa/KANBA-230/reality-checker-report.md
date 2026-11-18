# Reality-Checker Forensic Audit Report: KANBA-230

Auditor: TestingRealityChecker (Passive Forensic QA Gate)
Target Ticket: KANBA-230 (Post-Upgrade Local Admin Sign-In Failures & CSRF Cookie Lifecycle)
Integrated Commit: c72c45e (pushed to origin/main at e55c4ab4)
Verification Packet: docs/qa/KANBA-230/

---

## 1. Forensic Assessment & Scope Verification

Operating in passive forensic audit mode:
- No tests executed manually.
- No live environments accessed.
- Passive inspection of raw unedited logs, diffs, manifests, specialist reviews, and test outputs.

Audited Proof Packet Artifacts:
- `docs/qa/KANBA-230/git-diff.patch` (modifications across client.ts, csrf.py, LoginPage.tsx, authApi.ts, docker-compose.yml)
- `docs/qa/KANBA-230/changed-files-manifest.txt` (cataloged with SHA-256 and line counts)
- `docs/qa/KANBA-230/unit-test-results.txt` (raw unedited test outputs for auth, CSRF, and login)
- `docs/qa/KANBA-230/build-or-typecheck.txt` (tsc, eslint, ruff, mypy, license_gate, check_no_dashes, compose-check)
- `docs/qa/KANBA-230/api-specialist-review.md` (Signed STATUS: APPROVED)
- `docs/qa/KANBA-230/ui-specialist-review.md` (Signed STATUS: APPROVED)
- `docs/qa/KANBA-230/screenshots/` (8 Playwright PNG screenshots inspected via read_file across Desktop, Tablet, and Mobile)

---

## 2. Technical Invariants & Verification Analysis

1. **Eliminate Stale CSRF Cookie Wedge (`client.ts`, `csrf.py`, `LoginPage.tsx`):**
   - On `/login` mount, bootstraps `GET /api/v1/auth/session` to synchronize valid session and CSRF cookies before submission.
   - `client.ts` uses `cachedCsrfToken` and retries unsafe requests (`/api/v1/auth/local/login`, `/api/v1/setup/claim`) once after refreshing on 403 `CSRF_REJECTED`.
   - In `CsrfMiddleware`, unresolvable/expired sessions falling back to `PRE_SESSION_ID` clear stale cookies (`Max-Age=0`) and reissue valid pre-session tokens.

2. **Automate Schema Migrations in Compose (`docker-compose.yml`):**
   - Added `kanban-migrate` service running `alembic upgrade head` with `condition: service_completed_successfully` prior to `kanban-api` and `outbox-relay` startup.
   - `scripts/check_compose_networks.py` passes cleanly.
   - Startup check `verify_schema_head()` in `kanban/app.py` logs `❌` diagnostic if Alembic head is behind code head.

3. **Normalize Origin Comparisons (`csrf.py`):**
   - Parses `KANBAN_PUBLIC_ORIGIN` / `KB_PUBLIC_ORIGIN` with `urllib.parse.urlsplit` to `scheme://netloc`, preventing false-positive 403 `CSRF_REJECTED` on subpath deployments.

4. **Actionable Non-Enumerating Error Copy (`authApi.ts`, `LoginPage.tsx`):**
   - Distinguishes between stale tokens ("Your browser session token is out of date - reload the page and try again"), credential rejection (anti-enumeration copy), and server-side errors (displays correlation Request ID).
   - Inspected in screenshot `kanba-230-login-error-correlation-light-desktop.png`.

5. **Security & Quality Gates:**
   - Static analysis: `tsc -b` (0 errors), `eslint` (0 warnings), `ruff check` (0 errors), `mypy` (0 errors).
   - Zero non-ASCII dash violations in source, test, or proof files.
   - Signed dual specialist approvals: `api-specialist-review.md` (APPROVED), `ui-specialist-review.md` (APPROVED).

---

## 3. Final Quality Certification

- Overwhelming evidence provided across all deliverables.
- Zero stubbed tests, zero skipped checks, zero lowered coverage thresholds.

**Overall Quality Rating**: A
**Production Readiness**: READY

STATUS: READY
GRADE: A
