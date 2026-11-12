# Reality-Checker Verification Packet: KANBA-72 (KB-P2-04)

## Ticket Overview
- **Ticket ID**: `KANBA-72`
- **Spec Section**: `KB-P2-04` (S4.2 item 3, S2.2 item 1, S2.5, requirement #6)
- **Title**: `[Phase 2 / Auth] Local Admin card: Argon2id + HMAC-SHA256 pepper login with constant-time miss path and rate limits`
- **Wave**: `W14`
- **Git Branch**: `feat/KANBA-72` in isolated worktree `/tmp/kb-wt-KANBA-72`

---

## Technical Actions & File Manifest

1. **Database Migration & DDL**:
   - `database/migrations/versions/p2_04_local_admin_credentials.py` (`down_revision = "p2_02_sessions"`)
   - `database/migrations/sql/p2_04_local_admin_credentials.up.sql`
   - `database/migrations/sql/p2_04_local_admin_credentials.down.sql`
   - Table `local_admin_credentials` created under schema `public`, owned by `kb_auth_owner`, revoked from `PUBLIC, kanban_app, app_rls_reader`, with `ENABLE` and `FORCE ROW LEVEL SECURITY`, and policy `kb_auth_owner_all`.
   - Functions in `kb_auth`:
     * `kb_auth.local_get_credential(p_username text)` (returns principal_id, password_hash, pepper_kid or empty row)
     * `kb_auth.local_set_password_hash(p_principal uuid, p_hash text)` (atomic rehash update)
     * `kb_auth.local_admin_create(...)` (SERVER_ADMIN with AAL2 or setup-claim context required)
   - Model `LocalAdminCredential` mapped in `database/models/auth.py` and exported in `database/models/__init__.py`. Table count in `database/tests/test_p1_17_models.py` updated to 39 tables (`len(orm_tables) == 39`). `database/GEMINI.md` manifest updated.

2. **Core Auth Implementation**:
   - `kanban/auth/local/hashing.py`:
     * RFC 9106 Argon2id parameters: `m = 65536` KiB (64 MiB), `t = 3`, `p = 4`, `hash_len = 32`, `salt_len = 16`.
     * Pre-hash pipeline: `unicodedata.normalize("NFKC", password)` -> UTF-8 byte conversion -> length check `8 <= len(bytes) <= 1024` -> `hmac.new(auth_pepper, pw_bytes, sha256).digest()` -> `base64.b64encode` -> Argon2id.
     * Concurrency bounding: Offloaded to worker thread via `anyio.to_thread.run_sync` behind `asyncio.Semaphore(default 4)` with 2.0s acquisition timeout -> RFC 7807 `503 AUTH_BUSY` (`Retry-After: 2`).
     * `DUMMY_HASH`: Precomputed at module import from random entropy using the same parameters for the constant-work miss path.
     * `needs_rehash`: Automatically detects legacy hashes (e.g. `t = 2`) to trigger inline upgrade.
   - `kanban/auth/local/service.py`:
     * `LocalAdminLoginService.login(...)`: Orchestrates rate limit evaluation (`AUTH_LOGIN_IP` limit 20, `AUTH_LOGIN_ACCOUNT` limit 5), card enablement verification (`LOCAL_ADMIN` provider card), credential lookup, single Argon2 verification (real hash or `DUMMY_HASH` on failure), parameter rehash upgrade, bucket reset on success, session issuance (`aal_level=1, mfa_pending=True`), and sanitized activity ledger logging.
     * Sanitized activity events: `LOCAL_ADMIN_LOGIN_SUCCEEDED` and `LOCAL_ADMIN_LOGIN_FAILED` recorded with hashed IP and card ID; sensitive passwords and failed usernames are never logged.
   - `kanban/auth/local/__init__.py`: Public symbols exported.
   - `kanban/api/v1/auth_local.py`: `POST /api/v1/auth/local/login` mounted in `kanban/api/v1/__init__.py` with pre-session CSRF token validation and session cookie headers.

---

## Verification & Quality Metrics

1. **Unit Test Suite & Coverage**:
   - Test files: `kanban/tests/auth/test_local_hashing.py`, `kanban/tests/auth/test_local_login.py`, `database/tests/migrations/test_p2_04_migration.py`.
   - Results: **12/12 test cases passed** in 10.96s.
   - Statement Coverage: **100.00%** on `kanban.auth.local` (187/187 statements, 26/26 branches, 0 missed).
   - Migration lifecycle: `test_p2_04_migration.py` passed (upgrade -> downgrade -> upgrade).
   - Full migration suite: `database/tests/migrations/` 22/22 passed in 6.95s.
   - Models & RLS parity: `database/tests/test_p1_17_models.py` (6/6 passed, 39 tables) and `database/tests/test_p1_14_rls_catalog.py` passed.

2. **Timing Side-Channel Analysis**:
   - `docs/qa/KANBA-72/enumeration-timing.txt`: Evaluated 50 unknown-user attempts vs. 50 wrong-password attempts.
   - Median latency: Unknown = 53.27 ms, Wrong = 58.24 ms.
   - Median delta: **4.97 ms** (well within the maximum permitted threshold of 15.00 ms). Result: **PASS**.

3. **Build & Static Integrity**:
   - `ruff check .`: 0 errors.
   - `ruff format --check .`: Clean across 604 files.
   - `mypy --strict kanban database`: 0 errors across 229 files.
   - `lint-imports`: 2 contracts kept, 0 broken.
   - `make license`: SUMMARY python=110 node=1 violations=0.
   - `check_no_dashes --all`: Clean (0 non-ASCII Unicode dashes repo-wide).

4. **Dependency Compliance**:
   - `argon2-cffi==25.1.0` (MIT) pinned in `kanban/pyproject.toml` and locked in `uv.lock`.
   - Documented in `docs/qa/KANBA-72/dependency-evaluation.md` with sign-offs from `@arch-reviewer` (#116), `@sec-eng` (#118), and `@qa-eng` (#120).

5. **Proof Artifacts**:
   - `docs/qa/KANBA-72/git-diff.patch`
   - `docs/qa/KANBA-72/unit-test-results.txt`
   - `docs/qa/KANBA-72/build-check.txt`
   - `docs/qa/KANBA-72/schema-dump.sql`
   - `docs/qa/KANBA-72/enumeration-timing.txt`
   - `docs/qa/KANBA-72/contract-sample.json`
   - `docs/qa/KANBA-72/dependency-evaluation.md`
   - `docs/qa/KANBA-72/message-to-reality-checker.md`
