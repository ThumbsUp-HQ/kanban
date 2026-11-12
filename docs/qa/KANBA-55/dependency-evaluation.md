# Dependency Evaluation: KANBA-55 (KB-P1-17)

## Overview
- Ticket: KANBA-55 (KB-P1-17)
- Scope: SQLAlchemy 2.0 async ORM models, SET LOCAL RLS session binder, and BaseRepository
- Date: 2026-11-12
- New Runtime Dependencies Introduced: 0 (Zero)

## Reuse of Pinned Dependencies
This ticket reuses existing pinned dependencies established in KB-P0-05:
1. `sqlalchemy[asyncio]>=2.0.38` (Apache-2.0)
   - Provides native DeclarativeBase, Mapped, and mapped_column typing.
   - Provides async_sessionmaker and event listener hooks for RLS session lifecycle.
2. `asyncpg>=0.30.0` (Apache-2.0)
   - Provides asynchronous PostgreSQL 16 driver connecting over Unix domain sockets.

## Evaluated & Rejected Alternatives

### 1. SQLModel
- Status: REJECTED (Explicitly prohibited by Architecture Spec S2.5)
- Rationale:
  - Spec S2.5 explicitly mandates SQLAlchemy 2.0 native DeclarativeBase with strict Mapped typing.
  - SQLModel couples Pydantic validation into database schema models, leading to performance overhead, impedance mismatches with PostgreSQL generated/computed columns, and schema coupling.
  - SQLAlchemy 2.0 native DeclarativeBase provides superior typing under `mypy --strict` and direct support for PostgreSQL-specific constructs.
- Verification:
  - `grep -rn "sqlmodel" database/ pyproject.toml uv.lock` returns zero matches.
  - Automated test in `database/tests/test_p1_17_models.py::test_supply_chain_checks` asserts `sqlmodel` is not installed or imported.

### 2. sqlalchemy-utils
- Status: REJECTED
- Rationale:
  - `sqlalchemy-utils` provides an LtreeType implementation, but it pulls in numerous unneeded dependencies and maintains legacy compatibility shims that do not adhere to strict SQLAlchemy 2.0 typing.
  - The in-tree `LtreeType` in `database/models/base.py` is implemented in 25 lines of strictly typed Python as `UserDefinedType[str]`, validating input via regex `^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$` and returning `"LTREE"` as its PostgreSQL column spec.
  - In-tree implementation eliminates supply-chain exposure, avoids licensing ambiguities, and guarantees zero third-party drift.

## Specialist Review Sign-Offs

### Architect Review (@arch-reviewer, #116)
- Evaluated: Architecture Spec S2.5 and S3.3 compliance.
- Finding: SQLAlchemy 2.0 native DeclarativeBase and in-tree LtreeType cleanly isolate database schema from validation layers and honor the Universal Object Graph. Zero new runtime dependencies approved.

### Security Engineering Review (@sec-eng, #118)
- Evaluated: Supply-chain risk and licensing.
- Finding: Zero new dependencies introduced. All reused packages are Apache-2.0 compliant. Custom LtreeType regex prevents SQL/ltree injection by strictly enforcing alphanumeric and underscore label syntax.

### QA Engineering Review (@qa-eng, #120)
- Evaluated: Testability and clean-DB harness compatibility.
- Finding: Pure SQLAlchemy 2.0 constructs allow 100% clean-DB SAVEPOINT isolation per test without connection leaks or pool state corruption.

## Conclusion
Zero new dependencies were added. The project maintains zero warnings, 100% Apache-2.0 compliance, and zero supply-chain expansion.
