# Dependency Evaluation and Supply-Chain Security Audit: KANBA-25

- Ticket: KANBA-25 (KB-P1-01)
- Title: [Phase 1 / Database] Alembic async baseline, DB roles, extensions & uuidv7()
- Target Dependencies:
  * alembic 1.20.1 (MIT)
  * Mako 1.4.3 (MIT, transitive dependency of alembic)
  * Note: Executes in conjunction with sqlalchemy[asyncio] 2.0.38 (MIT) and asyncpg 0.30.0 (Apache-2.0) previously approved in KANBA-18.
- Evaluators:
  * Systems/Backend Architect (arch-reviewer)
  * Application and Supply-Chain Security Engineer (sec-eng)
  * Test and Build Quality Engineer (qa-eng)

---

## 1. Executive Summary & Policy Compliance

All direct and transitive dependencies introduced in KANBA-25 are licensed under permissive open-source licenses (MIT and Apache-2.0), satisfying the monorepo Apache-2.0 policy (AGENTS.md, S1.2, S15.4) with zero copyleft (GPL, AGPL, SSPL, LGPL) contamination.

### Categorical Rejection of psycopg 3 (LGPL-3.0 Policy Violation)
- Upstream Driver Status: psycopg version 3 is distributed under the GNU Lesser General Public License v3.0 (LGPL-3.0-or-later).
- Policy Conflict: Under repository policy (AGENTS.md, Section 15.4), copyleft licenses including LGPL-3.0 are strictly forbidden. The LGPL-3.0 imposes restrictions on binary embedding, potential source redistribution triggers, and dynamic linking conditions that conflict with permissive Apache-2.0 distribution and downstream commercial integration.
- Selected Alternative: asyncpg is licensed under Apache-2.0. It provides 100% license compliance, native binary PostgreSQL wire-protocol implementation in Python/Cython without intermediate C libpq wrappers, and superior async throughput.

---

## 2. Pinned Version & Integrity Hash Manifest (from uv.lock)

| Package | Version | License | Direct/Dev | SHA-256 Digest (sdist or primary wheel) |
| :--- | :--- | :--- | :--- | :--- |
| `alembic` | `1.20.1` | MIT | Direct (`kanban-database`) | `sha256:9970712cfb81ea26c8658d378aaa5b8f6ff9146e5bb111d70497c164016cf598` |
| `Mako` (transitive) | `1.4.3` | MIT | Direct (`kanban-database`) | `sha256:723296007c870bfd6b3f0c3230dba7198096e5269297ebf5e4eff9e7ffa39d4f` |
| `sqlalchemy` | `2.0.38` | MIT | Direct (`kanban-database`) | `sha256:12d5b06a1f3aeccf295a5843c86835033797fea292c60e72b07bcb5d820e6dd3` |
| `asyncpg` | `0.30.0` | Apache-2.0 | Direct (`kanban-database`) | `sha256:c551e9928ab6707602f44811817f82ba3c446e018bfe1d3abecc8ba5f3eac851` |

---

## 3. Systems/Backend Architect Evaluation (arch-reviewer)

- Evaluator: Systems/Backend Architect (arch-reviewer)
- Scope: docs/tickets/KB-P1-01.md (KANBA-25 / KB-P1-01)
- Evaluated Packages:
  * alembic (MIT) in database dependencies (paired with sqlalchemy[asyncio] and asyncpg from KANBA-18)

### 1. License and Compatibility:
alembic is licensed under the permissive MIT license. 100% compatible with the monorepo Apache-2.0 licensing policy. Zero copyleft.

### 2. Supply-Chain and Attack Surface:
- Scoped to schema migration orchestration. Migrations run under a dedicated, privileged role (kanban_migrator) with BYPASSRLS during maintenance windows, followed by immediate privilege dropping before application runtime (kanban_app is NOSUPERUSER, NOBYPASSRLS).
- Migration scripts execute raw SQL files with strict filename validation (^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+\.(up|down)\.sql$), preventing path-traversal and arbitrary file execution.
- alembic operates strictly over local database connections with no external telemetry or network calls.

### 3. Architectural Rationale and Alternatives Considered:
- alembic vs. custom raw SQL migration runner:
  * An ad-hoc migration runner lacks formal revision graph resolution (down_revision tracking), single-head verification, and standard schema rollback capabilities.
  * alembic provides mature, battle-tested migration versioning that enforces a strictly linear revision history and integrates directly with asyncpg and SQLAlchemy AsyncEngine.
- alembic vs. yoyo-migrations:
  * yoyo-migrations lacks deep integration with SQLAlchemy 2.0 async connection pooling and has a smaller ecosystem footprint. alembic is the established standard for enterprise PostgreSQL migrations.

### 4. Architectural Verdict:
APPROVED. Essential for reversible, audited, privilege-separated database schema migrations.

---

## 4. Application and Supply-Chain Security Engineer Evaluation (sec-eng)

- Evaluator: Application and Supply-Chain Security Engineer (sec-eng)
- Scope: docs/tickets/KB-P1-01.md (KANBA-25 / KB-P1-01)
- Target Packages: alembic (in database dependencies, paired with sqlalchemy[asyncio] and asyncpg from KANBA-18)

### 1. License and Compatibility Audit:
- alembic (MIT): Permissive database migration framework.
- Mako (MIT): Permissive template engine for migration script generation.
- License Compliance: 100% permissive. 100% compliant with Apache-2.0 policy.

### 2. Supply-Chain and Database Security Hardening:
- Privilege Separation: Migrations execute strictly under the dedicated kanban_migrator role (possessing BYPASSRLS for table and schema creation). After migration, web and MCP workers execute under unprivileged kanban_app (NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE), enforcing strict defense-in-depth and least privilege.
- Simple Query Protocol: DDL scripts execute via raw asyncpg simple query protocol, avoiding prepared statement caching issues and multi-statement injection vulnerabilities.
- Path Traversal Defense: execute_sql_file strictly validates file names against ^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+\.(up|down)\.sql$, preventing directory traversal attacks.
- Security Definer Function Hardening: All SECURITY DEFINER functions set search_path = pg_catalog, public, revoke public execute privileges, and grant execute explicitly to application roles.

### 3. Alternatives Evaluated:
- Raw SQL migration runner: Lacks formal revision DAG tracking, single-head verification, and migration history rollback auditing. Alembic ensures deterministic, reversible, and auditable schema state.
- yoyo-migrations: Lacks tight integration with SQLAlchemy 2.0 AsyncEngine and has limited support for advanced PostgreSQL features (RLS policies, extensions, GUC-based context functions).

### 4. Verdict:
- Role Sign-Off: APPROVED by sec-eng (Engineer #1, Application and Supply-Chain Security Engineer) for KANBA-25.

---

## 5. Test and Build Quality Engineer Evaluation (qa-eng)

- Reviewer: qa-eng (Engineer #2, Test and Build Quality Engineer)
- Scope: docs/tickets/KB-P1-01.md (KANBA-25 / KB-P1-01)
- Target Dependencies:
  * alembic (MIT, schema migration management)
  * Note: Executes in conjunction with sqlalchemy[asyncio] (MIT) and asyncpg (Apache-2.0) previously approved in KANBA-18.

### 1. Test and Build Quality Assessment:
- alembic: Industry-standard migration framework providing linear, version-controlled schema evolution. Configured with an asynchronous environment (database/migrations/env.py) executing multi-statement DDL via asyncpg simple query protocols.
- Single-Head Determinism: Enforces strict single-head linearity (uv run alembic heads), preventing concurrent migration branching and silent schema divergences.
- Automated Migration Verification: Integrates with MigrationHarness to execute full migration round-trips (upgrade head -> downgrade base -> upgrade head) in isolated test databases, validating schema reproducibility via byte-for-byte schema dumps.
- Privilege Boundary Enforcement: Executes migrations under the kanban_migrator role, separating schema alteration capabilities from runtime application execution (kanban_app).

### 2. Alternatives Considered:
- Raw SQL Migration Scripts: High maintenance overhead, prone to ordering errors, lacks dependency graphs, and reinvents version tracking and rollback logic.
- yoyo-migrations: Lacks direct integration with SQLAlchemy metadata and asyncpg connection pooling. Alembic provides first-class compatibility with SQLAlchemy 2.0 async workflows.

### 3. Engineer #2 Sign-off:
APPROVED.
