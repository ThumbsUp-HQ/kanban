# Reality-Checker Audit Note: KANBA-80 (KB-P5-10)

## Architectural Scope & Workflow Ownership

This ticket (`KANBA-80` / `KB-P5-10`) implements the manual terminal validation command `validate-sparkle` for the Sparkle FIM completion pipeline:

1. **CLI Subcommand Implementation (`agent/cli_commands/validate_sparkle.py`):**
   - Registered as `validate-sparkle` in `agent/cli.py`.
   - Exact flags: `--provider`, `--model`, `--input-markdown`, `--project`, `--as-user`, `--cassette`, `--http-cassette`, `--iterations`, `--surface`, `--report`, `--database-url`, `--verbose-tools`.
   - Single canonical pipeline call: delegates execution to `run_sparkle_pipeline()` from `agent.sparkle.pipeline` (zero reimplementation of pipeline steps).

2. **Security & RLS Invariants:**
   - Single unescaped `|` cursor marker parser (`parse_cursor_marker`), unescaping literal `\|`. Multi-marker or missing marker rejects with exit code 2 (`CURSOR_MARKER_INVALID`).
   - RLS bypass check: queries `pg_roles` for `rolsuper` and `rolbypassrls`, refusing bypass roles with exit code 2 (`RLS_BYPASS_ROLE_REFUSED`).
   - Inbound secret scrub-first mandate: evaluates input prefix and suffix before any network or database I/O, halting with exit code 2 (`secret_scrubbed`) on secret detection. Raw secrets are strictly redacted from terminal stdout and serialized JSON reports.
   - User principal and project resolution under tenant boundary; missing user or project yields exit code 2 (`PRINCIPAL_NOT_FOUND` / `PROJECT_NOT_FOUND`).
   - RLS-scoped retrieval trace guarantees zero cross-project canary leaks (`SEC-CANARY-7731`).

3. **Multi-Iteration Benchmark & Schema Compliance:**
   - Bounded iterations (1..500); multi-iteration runs (`--iterations N`, `> 1`) compute and display percentile statistics (`p50`, `p90`, `p95`, `p99`). Latency over 150.0ms p95 fails with exit code 2 (`LATENCY_SLA_BREACH`).
   - Standard 4-section report rendering (`=== 1. RENDERED CONTEXT ===`, `=== 2. TOOL TRACE ===`, `=== 3. LATENCY & TOKENS ===`, `=== 4. SCHEMA & POLICY STATUS ===`, `=== 5. ROUTE TRACE ===`).
   - JSON report (`--report json`) validates strictly against schema `agent/schemas/kb-sparkle-report-v1.json` (`additionalProperties: false`).

4. **Demo RLS Seed (`examples/sparkle/seed_rls_demo.sql`):**
   - Populates workspace `demo-sparkle`, projects `KAN` and `SEC`, user principal `@adam` with `MEMBER` role on `KAN` only (zero access on `SEC`), canary issue `SEC-1` (`SEC-CANARY-7731`), issue `KAN-1` (`OAuth2/LDAP`), and fixed vector embeddings.

5. **Mandatory Feature Unit Tests (`agent/tests/cli/test_validate_sparkle.py`):**
   - 18 passed tests in 8.50s.
   - Combined statement + branch coverage: **98.20%** (exceeds `>= 95%` mandate).
   - All 8 required test cases present and validated.

6. **Static Checks & Quality Invariants:**
   - `mypy --strict agent`: Clean (66 source files checked, 0 errors).
   - `ruff check .`: Clean (0 errors).
   - `ruff format --check .`: Clean (586 files already formatted).
   - `lint-imports`: 2 kept, 0 broken.
   - `check_no_dashes --all`: Clean (0 non-ASCII dashes repo-wide).
   - `make license`: Clean (SUMMARY python=110 node=1 violations=0).

7. **Specialist Gate Applicability:**
   - Non-UI Ticket: Declared `N/A - Non-UI Ticket` in frontmatter and specification.
