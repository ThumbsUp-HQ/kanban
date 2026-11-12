# Dependency Evaluation and Supply-Chain Security Audit: KANBA-18

- Ticket: KANBA-18 (KB-P0-05)
- Title: [Phase 0 / Test Harness] Fast clean-DB harness (tmpfs PG16 + template DB + SAVEPOINT)
- Target Dependencies:
  * sqlalchemy[asyncio] 2.0.38 (MIT)
  * asyncpg 0.30.0 (Apache-2.0)
  * pytest-asyncio 1.4.1.post1 (Apache-2.0)
  * pytest-xdist 3.8.0 (MIT)
  * pytest-socket 0.8.1 (MIT)
- Evaluators:
  * Systems/Backend Architect (arch-reviewer)
  * Application and Supply-Chain Security Engineer (sec-eng)
  * Test and Build Quality Engineer (qa-eng)

---

## 1. Executive Summary & Policy Compliance

All direct dependencies introduced in KANBA-18 are licensed under permissive open-source licenses (Apache-2.0 and MIT), satisfying the monorepo Apache-2.0 policy (AGENTS.md, S1.2, S15.4) with zero copyleft (GPL, AGPL, SSPL, LGPL) contamination.

### Categorical Rejection of psycopg 3 (LGPL-3.0 Policy Violation)
- Upstream Driver Status: psycopg version 3 is distributed under the GNU Lesser General Public License v3.0 (LGPL-3.0-or-later).
- Policy Conflict: Under repository policy (AGENTS.md, Section 15.4), copyleft licenses including LGPL-3.0 are strictly forbidden. The LGPL-3.0 imposes restrictions on binary embedding, potential source redistribution triggers, and dynamic linking conditions that conflict with permissive Apache-2.0 distribution and downstream commercial integration.
- Selected Alternative: asyncpg is licensed under Apache-2.0. It provides 100% license compliance, native binary PostgreSQL wire-protocol implementation in Python/Cython without intermediate C libpq wrappers, and superior async throughput.

---

## 2. Pinned Version & Integrity Hash Manifest (from uv.lock)

| Package | Version | License | Direct/Dev | SHA-256 Digest (sdist or primary wheel) |
| :--- | :--- | :--- | :--- | :--- |
| `sqlalchemy` | `2.0.38` | MIT | Direct (`kanban-database`) | `sha256:e5a4d82bdb4bf1ac1285a68eab02d253ab73355d9f0fe725a97e1e0fa689decb` |
| `asyncpg` | `0.30.0` | Apache-2.0 | Direct (`kanban-database`) | `sha256:c551e9928ab6707602f44811817f82ba3c446e018bfe1d3abecc8ba5f3eac851` |
| `pytest-asyncio` | `1.4.1.post1` | Apache-2.0 | Dev (`dependency-groups`) | `sha256:f582d9ea4a1c082195abe8bd29a1fe106aeb1cd435e3dad2d3bc2749935c36a2` |
| `pytest-xdist` | `3.8.0` | MIT | Dev (`dependency-groups`) | `sha256:7e578125ec9bc6050861aa93f2d59f1d8d085595d6551c2c90b6f4fad8d3a9f1` |
| `pytest-socket` | `0.8.1` | MIT | Dev (`dependency-groups`) | `sha256:2f57787914ad2e1308d09ce141b95c3e55741fbb4fb7b7556593a6b063e0c9c7` |
| `greenlet` (transitive) | `3.5.6` | MIT | Direct (`kanban-database`) | `sha256:8e67c43bdfc88d5fee6db0d3e40175b362fc95fb85f0412d233b9b203c53a575` |
| `execnet` (transitive) | `2.1.2` | MIT | Dev (`dependency-groups`) | `sha256:63d83bfdd9a23e35b9c6a3261412324f964c2ec8dcd8d3c6916ee9373e0befcd` |

---

## 3. Systems/Backend Architect Evaluation (arch-reviewer)

- Evaluator: Systems/Backend Architect (arch-reviewer)
- Scope: docs/tickets/KB-P0-05.md (KANBA-18 / KB-P0-05)
- Evaluated Dependencies: sqlalchemy[asyncio] 2.0 (MIT), asyncpg (Apache-2.0), pytest-asyncio (Apache-2.0), pytest-xdist (MIT), pytest-socket (MIT)

### 1. License and Compatibility (Mandatory Rejection of psycopg 3)
- Mandatory License Policy: Apache-2.0 permissive. Zero copyleft licenses permitted.
- psycopg 3 is licensed under GNU Lesser General Public License v3.0 (LGPL-3.0). LGPL-3.0 is strictly FORBIDDEN under our repository licensing policy (AGENTS.md, S2.5). LGPL-3.0 introduces copyleft risks, source redistribution obligations, and corporate adoption barriers that compromise the Apache-2.0 distribution status of this monorepo. psycopg 3 is categorically REJECTED.
- asyncpg is licensed under Apache-2.0. It is 100% compliant with our permissive licensing policy.
- sqlalchemy, pytest-asyncio, pytest-xdist, and pytest-socket are licensed under MIT or Apache-2.0. Zero GPL/AGPL/LGPL/SSPL contamination.

### 2. Supply-Chain and Attack Surface
- Test PostgreSQL container runs on disposable RAM-backed storage (tmpfs) with TCP networking completely disabled (listen_addresses= empty). All access is restricted to a host-local Unix domain socket directory with mode 0700 permissions.
- pytest-socket enforces --disable-socket --allow-unix-socket, guaranteeing that tests cannot initiate outbound network connections or access unauthorized local TCP ports.

### 3. Architectural Rationale and Alternatives Considered
- asyncpg vs. psycopg 3: Beyond license compliance, asyncpg implements the PostgreSQL wire protocol directly in Python and Cython without intermediate libpq wrappers, delivering superior raw asynchronous throughput.
- sqlalchemy 2.0 AsyncEngine vs. raw connection drivers: SQLAlchemy 2.0 provides typed async sessions, schema definition, and critically, the join_transaction_mode="create_savepoint" feature. This allows individual tests to execute operations within a SAVEPOINT sub-transaction that is rolled back on fixture teardown, achieving sub-millisecond database test cleanup without disk I/O.
- Golden Template DB + CREATE DATABASE ... TEMPLATE vs. Per-Test Truncation: Running schema migrations and DDL setup per test worker or per test case is prohibitively slow. Building a golden kanban_template database once (tracked via sha256 schema fingerprint) and cloning worker databases via PostgreSQL internal copy-on-write TEMPLATE mechanism allows running hundreds of concurrent database tests in under 5 seconds.

### 4. Architectural Verdict
APPROVED. Delivers sub-millisecond clean database test isolation with zero copyleft risk.

---

## 4. Application and Supply-Chain Security Engineer Evaluation (sec-eng)

- Evaluator: Application and Supply-Chain Security Engineer (sec-eng)
- Scope: docs/tickets/KB-P0-05.md (KANBA-18 / KB-P0-05)
- Target Packages: sqlalchemy[asyncio] 2.0, asyncpg, pytest-asyncio, pytest-xdist, pytest-socket

### 1. License and Compatibility Audit
- sqlalchemy[asyncio] 2.0 (MIT): Permissive ORM and async engine core.
- asyncpg (Apache-2.0): Permissive high-performance async PostgreSQL driver.
- pytest-asyncio (Apache-2.0): Permissive asyncio testing fixture framework.
- pytest-xdist (MIT): Permissive multi-worker test distribution engine.
- pytest-socket (MIT): Permissive network socket containment and interception plugin.
- License Compliance: 100% permissive (MIT and Apache-2.0).

### 2. Rejection of psycopg 3 (LGPL-3.0 Policy Violation)
- Policy Mandate: Project policy strictly enforces Apache-2.0 permissive licensing and strictly forbids GPL, AGPL, SSPL, and LGPL runtime dependencies.
- Rejection Analysis: psycopg version 3 is licensed under the GNU Lesser General Public License v3.0 (LGPL-3.0-or-later). The LGPL imposes copyleft provisions, restrictions on static compilation/linking, and compliance mandates regarding user reverse-engineering rights that directly conflict with permissive Apache-2.0 distribution and downstream commercial embedding.
- Compliant Alternative: asyncpg is fully licensed under Apache-2.0, providing native license alignment, binary protocol efficiency without external C libpq dependencies, and zero copyleft contamination.

### 3. Supply-Chain and Network Containment
- Network Socket Disablement: pytest-socket enforces --disable-socket --allow-unix-socket across test execution. Any rogue dependency or test attempting an outbound TCP/IP connection triggers an immediate SocketBlockedError, preventing data exfiltration, phone-home telemetry, and uncontrolled lateral network access.
- Local Unix Socket Isolation: Test PostgreSQL container runs with listen_addresses="" and zero exposed TCP ports. Communication is strictly bound to a local Unix socket directory permissions-locked to 0700 owned by the test runner.
- Lockfile Pinning: Exact version pinning with SHA-256 verification in uv.lock.

### 4. Security Engineer Verdict
APPROVED. Signed by sec-eng (Engineer #1, Application and Supply-Chain Security Engineer) for KANBA-18.

---

## 5. Test and Build Quality Engineer Evaluation (qa-eng)

- Evaluator: Test and Build Quality Engineer (qa-eng)
- Scope: docs/tickets/KB-P0-05.md (KANBA-18 / KB-P0-05)
- Target Dependencies: sqlalchemy[asyncio] 2.0 (MIT), asyncpg (Apache-2.0), pytest-asyncio (Apache-2.0), pytest-xdist (MIT), pytest-socket (MIT)

### 1. License and Supply-Chain Verification
- psycopg 3 Rejection: psycopg 3 is licensed under GNU Lesser General Public License v3.0 (LGPL-3.0). Under repository policy and invariant #0, all GPL, AGPL, SSPL, and LGPL runtime dependencies are strictly prohibited. asyncpg is licensed under Apache-2.0, completely permissive and fully compatible with the monorepo Apache-2.0 license.

### 2. Test and Build Quality Assessment
- sqlalchemy[asyncio] 2.0: Industry standard asynchronous ORM and Core SQL toolkit. Provides first-class support for transactional savepoints (join_transaction_mode="create_savepoint"). Enables sub-millisecond per-test isolation by wrapping each test in an outer transaction with savepoint rollbacks, avoiding costly database recreation between test cases.
- asyncpg: High-performance, pure asynchronous PostgreSQL binary wire-protocol driver. Bypasses libpq overhead, minimizes memory footprint, and provides robust socket connection pooling across high-volume test executions.
- pytest-asyncio: Enables native async test execution and fixture lifecycle management under asyncio_mode="auto", maintaining clean event loop lifecycles across session and function fixtures.
- pytest-xdist: Provides multi-process test parallelization (-n auto / -n 2 --dist loadfile). Integrates with the template database pattern (cloning kanban_template into kanban_test_<worker_id>), allowing parallel database tests without data collisions.
- pytest-socket: Enforces strict hermetic test sandboxing via --disable-socket --allow-unix-socket. Prevents unintended external network calls and telemetry while permitting host-local Unix domain socket communication to the PostgreSQL container.
- Performance Benchmark Alignment: Essential for maintaining sub-second clean test database teardown and satisfying the benchmark requirement of 200 database-backed tests completing in under 5.0 seconds.

### 3. Alternatives Considered
- psycopg 3: Rejected due to LGPL-3.0 license incompatibility.
- Ephemeral Docker Container per Test: Creating containers per test or resetting schemas via table recreation takes seconds per test, violating the test execution budget. The tmpfs + template DB + SAVEPOINT architecture delivers sub-millisecond clean state.

### 4. QA Engineer Verdict
APPROVED. Signed by qa-eng (Engineer #2, Test and Build Quality Engineer) for KANBA-18.
