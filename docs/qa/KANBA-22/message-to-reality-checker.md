# Forensic Message to Reality-Checker: KANBA-22

- Ticket ID: KANBA-22 (KB-P0-07: `[Phase 0 / Containers] Multi-stage Dockerfile (web-builder, py-builder, runtime-slim, standalone)`)
- Worktree Branch: `feat/KANBA-22` inside isolated worktree `/tmp/kb-wt-KANBA-22`
- Specification Traceability: S2.4 (Dockerfile stage contract), S2.2 (standalone image content), S3.5 (standalone misconfiguration defense, zero baked-in secrets), Requirement #3
- Depends On: KB-P0-01 (monorepo layout), KB-P0-03 (kanban/web Vite SPA skeleton)

---

## 1. Implemented Target Files

All target files specified in `KB-P0-07.md` exist and are strictly verified:
1. `Dockerfile`:
   - Line 1 declares `# syntax=docker/dockerfile:1.7`.
   - Stage 1: `web-builder` (`node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS web-builder`).
   - Stage 2: `py-builder` (`python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS py-builder`).
   - Stage 3: `runtime-slim` (`python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS runtime-slim`).
   - Stage 4: `standalone` (`FROM runtime-slim AS standalone`, default final stage).
   - Base images and external stages cryptographically pinned with `@sha256:<64hex>`.
   - PGDG repository key verified against pinned fingerprint `B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8`.
   - Zero toolchains (`gcc`, `cc`, `make`, `node`, `npm`, `pnpm`, `uv`, `pip`) in `runtime-slim`.
   - Runs as non-root `USER 65532:65532` in `runtime-slim`.
   - Standalone stage remains `USER root` with justification comment documented.
2. `.dockerignore`:
   - Excludes `.git`, `.venv`, `node_modules`, `**/__pycache__`, `docs/qa`, `.env*`, `*.pem`, `*.key`, `ci-logs`, `reports`.
3. `Makefile`:
   - Updated `.PHONY` with `image-slim`, `image-standalone`, `hadolint`.
   - Targets `image-slim`, `image-standalone`, and `hadolint` implemented and verified.
4. `deploy/.gitkeep`:
   - Placeholder ensuring `deploy/` directory exists so `COPY deploy/ /opt/kanban/deploy` succeeds cleanly.
5. `tests/deploy/__init__.py` & `tests/deploy/test_dockerfile.py`:
   - 9 static AST/regex unit tests covering all 5 mandatory test cases plus boundary/parser tests.
   - 99% branch and line coverage (exceeds >=95% requirement).

---

## 2. Scoped Definition of Done Audit

- [x] File Existence & Implementation: `Dockerfile`, `.dockerignore`, `Makefile`, `deploy/.gitkeep`, `tests/deploy/__init__.py`, `tests/deploy/test_dockerfile.py` exist and satisfy the stage contract.
- [x] Unit Tests Implemented & Passing: `uv run pytest tests/deploy/test_dockerfile.py -q` exits 0 with 0 failures (9 passed in 0.01s).
- [x] Images Build:
  - `docker build --target runtime-slim -t kanban:runtime-slim .` exits 0.
  - `docker build -t kanban:latest .` exits 0.
- [x] Runtime Checks:
  - `docker image inspect kanban:runtime-slim --format '{{.Config.User}}'` prints `65532:65532` and exits 0.
  - `docker run --rm --entrypoint /bin/sh kanban:runtime-slim -c 'for b in gcc cc make node npm pnpm uv pip; do command -v $b && exit 1; done; echo NO_TOOLCHAINS'` prints `NO_TOOLCHAINS` and exits 0.
  - `docker run --rm --entrypoint python kanban:runtime-slim -c "import database, kanban, mcp, agent"` exits 0.
  - `docker run --rm --entrypoint /bin/sh kanban:latest -c '/usr/lib/postgresql/16/bin/postgres --version && ls /usr/share/postgresql/16/extension/vector.control && command -v setpriv'` prints Postgres 16.15, vector.control, and setpriv paths and exits 0.
- [x] No Secrets in Layers:
  - `docker history --no-trunc kanban:latest` output contains zero matches for `(?i)(password=|secret=|BEGIN [A-Z ]*PRIVATE KEY)`.
- [x] Build / Type / Lint Clean:
  - `docker run --rm -i hadolint/hadolint@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d < Dockerfile` exits 0 with zero warnings/errors.
  - `make check` exits 0 (ruff check 0 errors, ruff format check clean, mypy strict clean, lint-imports 1 kept 0 broken, check_no_dashes 0 hits).
- [x] Forensic Proof Packet Complete: All 6 required raw evidence files populated in `docs/qa/KANBA-22/`.
- [x] Visual Screenshots: N/A - Non-UI Ticket (container build and configuration infrastructure).

---

## 3. Forensic Artifacts Manifest

The following raw artifacts are provided in `docs/qa/KANBA-22/`:
1. `docs/qa/KANBA-22/git-diff.patch` - Unified git diff against pre-merge branch baseline.
2. `docs/qa/KANBA-22/unit-test-results.txt` - Output of `pytest tests/deploy/test_dockerfile.py -q` and verbose coverage report (99% coverage).
3. `docs/qa/KANBA-22/build-check.txt` - Raw logs of both docker build targets, hadolint, and make check.
4. `docs/qa/KANBA-22/runtime-checks.txt` - Raw logs and exit codes of all 4 runtime verification commands.
5. `docs/qa/KANBA-22/docker-history.txt` - Full output of `docker history --no-trunc` for `kanban:latest` and `kanban:runtime-slim`.
6. `docs/qa/KANBA-22/image-sizes.txt` - Output of `docker image ls kanban` showing 181 MB for `runtime-slim` and 526 MB for `latest`.
7. `docs/qa/KANBA-22/message-to-reality-checker.md` - This audit and traceability document.
