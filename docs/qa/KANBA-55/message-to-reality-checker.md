# Reality-Checker Verification Packet: KANBA-55 (KB-P1-17)

## Ticket Metadata
- Ticket ID: `KANBA-55`
- Spec Key: `KB-P1-17`
- Title: `[Phase 1 / Database] SQLAlchemy 2.0 async ORM models, SET LOCAL RLS session binder & BaseRepository`
- Epic: `KB-E1` (Phase 1 Database Architecture)
- Spec Sections: `3.3` (`SET LOCAL` binding `app.principal_id`, `app.workspace_id`, `app.token_scopes`, `app.aal_level` under `kanban_app`), `2.5` (`SQLAlchemy 2.0` + `asyncpg`; `SQLModel` explicitly banned), `12.1`, `12.2`, Requirement `#1`, `#13`
- Dependencies: `KB-P1-14` (`role_derivation`), `KB-P1-16` (`link_purger`)
- Gate: `reality-checker` (Passive Forensic Mode)

---

## User Story
As a **backend engineer**, I need **strictly typed SQLAlchemy 2.0 `DeclarativeBase` models for every Phase 1 table (zero `SQLModel`), an `RLSSessionFactory` that binds `SET LOCAL` session context per transaction and refuses unbound queries, and a typed `BaseRepository`** so that **Phase 2+ services query the Universal Object Graph with full `mypy --strict` safety and impossible cross-transaction RLS context leakage**.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** `database/models/{__init__,base,spine,principals,projects,issues,knowledge,activity}.py`, `database/session.py`, and `database/repositories.py` exist and implement all 33 Phase 1 ORM models, `LtreeType`, `RLSContext`, `bind_rls_context`, `RLSSessionFactory`, `verify_non_bypass_role`, and `BaseRepository`.
- [x] **Zero SQLModel:** `grep -rn "sqlmodel" database/ pyproject.toml uv.lock` returns zero matches, and `database/tests/test_p1_17_models.py::test_supply_chain_checks` asserts `sqlmodel` is not installed or imported.
- [x] **In-Tree LtreeType:** Custom `LtreeType(UserDefinedType[str])` validates against `^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$` without third-party `sqlalchemy-utils`.
- [x] **Unit Tests Implemented & Passing:** `uv run pytest database/tests/test_p1_17_models.py database/tests/test_p1_17_rls_session.py database/tests/test_p1_17_repositories.py -v --cov=database.models --cov=database.session --cov=database.repositories --cov-branch --cov-report=term-missing --cov-fail-under=95` exits code 0 with 12/12 passing tests and 99.22% overall test coverage (models: 100%, repositories: 100%, session: 96%).
- [x] **Build / Type / Lint Clean:** `uv run ruff check database && uv run ruff format --check database && uv run mypy --strict database && uv run lint-imports` exits code 0 across all 82 checked source files.
- [x] **No Forbidden Unicode Dashes:** Repository passes `uv run python -m scripts.check_no_dashes --all` with zero violations.
- [x] **License Gate Clean:** `make license` passes with 0 violations.
- [x] **Forensic Proof Packet Complete:** All required proof files exist under `docs/qa/KANBA-55/`.

---

## Technical Actions & Implementation Matrix

| Component | Target Location | Description |
| :--- | :--- | :--- |
| **Base & Custom Types** | `database/models/base.py` | `Base(DeclarativeBase)` with native `Mapped` typing, custom `LtreeType(UserDefinedType[str])`, and 5 StrEnums with `values_callable` (`ObjectKind`, `LinkKind`, `ViewLayout`, `RbacRole`, `InvalidLinkReason`). |
| **Spine Models** | `database/models/spine.py` | Universal Object Graph models: `Workspace`, `ObjectRecord`, `ObjectLink`, `LinkTypeMatrix`, `InvalidObjectLinkAudit`. |
| **Principal Models** | `database/models/principals.py` | Principals & RBAC models: `Principal`, `User`, `Group`, `PrincipalGroupEdge`, `PrincipalGroupClosure`, `RoleBinding`, `ResourceAclEntry`, `EffectiveResourceAccess` (with `Computed` `effective_mask`). |
| **Project Models** | `database/models/projects.py` | Project hierarchy models: `Project`, `WorkflowState`, `ProjectPriority`, `ProjectLabel`, `Cycle`, `Module`, `ProjectModuleDefault`, `View` (with `Computed` `summary_sha256`). |
| **Issue Models** | `database/models/issues.py` | Issue & tracker models: `Issue` (with `Computed` `description_sha256` and `search_tsv`), `IssueModule`, `IssueAssignee`, `IssueLabel`, `IssueSubscription`, `IssueComment` (with `Computed` `body_sha256`). |
| **Knowledge Models** | `database/models/knowledge.py` | Knowledge store models: `Doc`, `Page`, `PageVersion`, `Sticky` (all `body_sha256` marked `Computed(..., persisted=True)`). |
| **Activity Models** | `database/models/activity.py` | Immutable audit ledger models: `ActivityChainHead`, `ActivityRecord`. |
| **Models Module Export** | `database/models/__init__.py` | Clean `__all__` re-exporting `Base`, `LtreeType`, 5 enums, and all 33 ORM model classes. |
| **RLS Session Binder** | `database/session.py` | `RLSContext` validation, `bind_rls_context()` executing S3.3 `set_config` parameters, `do_orm_execute` and `after_transaction_end` event guards preventing unbound queries or connection reuse leakage, `create_rls_engine()`, `verify_non_bypass_role()`, and `RLSSessionFactory`. |
| **Base Repository** | `database/repositories.py` | Generic `BaseRepository[TModel]` verifying RLS-bound session, with `get_by_id`, `list_all` (bounded 1..500), `add`, `delete`, and `flush`. |
| **Module Manifest** | `database/GEMINI.md` | Updated inbound/outbound contracts, budgets, and failure modes. |
| **Models Unit Tests** | `database/tests/test_p1_17_models.py` | 5 tests: 1:1 schema parity against `pg_tables`, round-trip CRUD with computed SHA/TSV/mask columns, `LtreeType` path validation, and supply-chain exclusion checks. |
| **RLS Session Tests** | `database/tests/test_p1_17_rls_session.py` | 4 tests: `SET LOCAL` binding and tenant isolation under connection pool reuse, unbound session guard before execution and after commit, `verify_non_bypass_role` superuser/bypassrls rejection, and `RLSContext` validation. |
| **Repository Tests** | `database/tests/test_p1_17_repositories.py` | 3 tests: repository unbound session guard, CRUD operations, and pagination limit boundary validation (1..500). |

---

## Forensic Artifacts in `docs/qa/KANBA-55/`
1. `git-diff.patch`: Complete unified `git diff` for this ticket.
2. `unit-test-results.txt`: Full output and exit code of `pytest database/tests/test_p1_17_models.py database/tests/test_p1_17_rls_session.py database/tests/test_p1_17_repositories.py -v --cov=database.models --cov=database.session --cov=database.repositories --cov-branch --cov-report=term-missing --cov-fail-under=95` (12 passed in 0.78s, 99.22% coverage, EXIT_CODE=0).
3. `build-check.txt`: Full output of `ruff check database`, `ruff format --check database`, `mypy --strict database`, and `lint-imports` (all checks passed, 82 source files clean, EXIT_CODE=0).
4. `orm-table-parity.txt`: Output listing all 33 mapped `Base.metadata` tables matched 1:1 against PostgreSQL `pg_tables` in `public`.
5. `dependency-evaluation.md`: Documents reuse of KB-P0-05 `sqlalchemy[asyncio]` + `asyncpg` pins, in-tree `LtreeType` vs rejected `sqlalchemy-utils`, and rejection of `SQLModel` per S2.5, with architect and engineer sign-offs.
6. `message-to-reality-checker.md`: This forensic sign-off document.
