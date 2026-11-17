# API Specialist Forensic QA Review: KANBA-189

## Metadata
- **Ticket ID:** KANBA-189
- **Title:** [KB-DB-GOV] Zero-Guesswork Database Migration & Schema Consistency Standard: GEMINI.md Policy, kanban-ctl db Scaffolding/Validator CLI, and Column-Level ORM/RLS Gates
- **Reviewer:** api-specialist (Backend Architect & API Tester Persona)
- **Target Commit:** `9e2e286` (merged into `main`)
- **Review Date:** 2026-11-17
- **Verdict:** APPROVED

---

## 1. Architectural & Engineering Assessment

### 1.1 Zero-Guesswork Schema Change & Migration Policy
- **Policy Contract in `database/GEMINI.md`:** Added comprehensive specification defining the canonical migration revision format (`^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+$`), strict prohibition against hand-rolling migration revision IDs or editing already-merged `.up.sql` files, and 3 explicit copy-pasteable SQL templates (Tenant Table, Isolated Table under `kb_auth_owner`/`kb_infra_owner`, and `SECURITY DEFINER` function).
- **Global Instruction & Symlink Parity:**
  - `GEMINI.md -> AGENTS.md` root symlink established and enforced by `tests/test_workspace_layout.py`.
  - `.agents/skills/kanban-ticket/SKILL.md` updated to mandate the Zero-Guesswork standard for any ticket introducing schema modifications.
- **Architectural Layering:** Preserves `lint-imports` strict unidirectional contract (`agent -> mcp -> kanban -> database`). `database/migrations/cli.py` is directly runnable via `python -m database.migrations.cli` without any upward imports to `kanban`. `kanban/cli/db.py` cleanly routes `kanban-ctl db` down to `database.migrations.cli` with zero layer leakage.

### 1.2 Deterministic Scaffolding & Migration Validator CLI
- **Scaffolding Generator (`database/migrations/scaffold.py`):**
  - Enforces strict regex validation on revision names.
  - Queries `ScriptDirectory.from_config().get_heads()` to ensure a strictly linear single-head migration chain, failing closed if zero or multiple heads exist.
  - Generates synchronized migration files atomically: `versions/<rev>.py`, `sql/<rev>.up.sql`, `sql/<rev>.down.sql`, and `database/tests/migrations/test_<rev>_migration.py`.
- **Consistency Validator (`database/migrations/validator.py`):**
  - Static mode verifies single Alembic head, naming rules, bidirectional `.up.sql`/`.down.sql` pairing, AST-level execution safety, and absence of orphaned SQL files.
  - Database-connected mode verifies `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` across public tenant tables and validates column/nullability parity against PostgreSQL `information_schema.columns`.
  - Successfully integrated into `Makefile` (`make check` executes `check-migrations --static-only`).

### 1.3 ORM Parity & Drift Resolution
- **`LinkTypeMatrix` (`database/models/spine.py`):**
  - Outdated unmigrated attributes (`is_bidirectional`, `inverse_link_type`, `created_at`) removed.
  - Added `is_user_creatable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)` matching `p1_11_object_links.up.sql`.
- **`UserIdentity` (`database/models/auth.py`):**
  - Added missing columns (`email_at_link`, `display_name_at_link`, `linked_at`, `last_used_at`) matching `p2_08_user_identities.up.sql`.
  - Fixed `workspace_id: Mapped[uuid.UUID | None]` to allow `nullable=True` in parity with the SQL definition.
- **`OAuthDeviceCode` (`database/models/oauth.py`):**
  - Fixed `workspace_id: Mapped[uuid.UUID | None]` to allow `nullable=True` matching `p4_16_oauth_device_codes.up.sql`.
- **Deep Parity Test (`database/tests/test_p1_17_models.py`):**
  - Replaced hardcoded `len(orm_tables) == 76` with dynamic 4-point verification: table existence parity, column name parity, nullability parity, and primary key set parity across all models.

---

## 2. Test Suite & Proof Verification

### 2.1 Unit & Integration Test Verification
- Executed the full database governance and security verification suite:
  - `database/tests/test_migration_consistency_static.py`
  - `database/tests/test_p1_17_models.py`
  - `database/tests/test_p1_14_rls_catalog.py`
  - `tests/security/test_stride_rls_and_invariants.py`
  - `tests/test_workspace_layout.py`
  - `kanban/tests/oauth/test_device_flow.py`
  - **Result:** 27 passed in 2.83s, 0 failures, 0 warnings.
- Ran `kanban-ctl db check-migrations --static-only` and `python -m database.migrations.cli check-migrations --static-only`: both exit 0 with "OK: All 57 migrations valid. Single head: p4_18_oauth_mcp_scoping".

### 2.2 Proof Artifacts Audit (`docs/qa/KANBA-189/`)
- `git-diff.patch`: Comprehensive and cleanly matches commit `9e2e286`.
- `changed-files-manifest.txt`: All 17 modified/created files cataloged with SHA-256 hashes and line counts.
- `unit-test-results.txt`: Verbatim raw pytest output verifying 27 tests passing with exit code 0.
- `build-check.txt`: Verbatim raw output of `ruff check`, `ruff format`, `mypy` (1021 files), `lint-imports` (2 contracts kept), `check_no_dashes`, and `check-migrations --static-only` with exit code 0.
- `contract-sample.json`: Valid JSON payload reporting `valid: true`, single head `p4_18_oauth_mcp_scoping`, 57 revisions, 114 SQL files, and 0 issues.
- `message-to-reality-checker.md`: Explicitly details non-UI status, requirement traceability, and exact DoD fulfillment.

---

## 3. Specialist Verdict

The implementation in commit `9e2e286` satisfies all database architecture requirements, migration safety standards, and ORM/RLS invariants specified in KANBA-189.

**Verdict: APPROVED**
