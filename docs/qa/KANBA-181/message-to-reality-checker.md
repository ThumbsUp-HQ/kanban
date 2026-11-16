# KANBA-181: Verification Packet for Reality-Checker

## 1. Ticket Overview
- **Ticket ID:** KANBA-181
- **Title:** [CI/CD / Release] Prepare Repository for GitHub Publishing: Dual-Track CI with Neutered Public GitHub Actions and Preserved Self-Hosted Dash CI
- **Scope & Ownership:**
  - Strictly owned files:
    - `.github/workflows/ci.yml`
    - `scripts/ci/upload_dash_log.sh`
    - `kanban/tests/ci/__init__.py`
    - `kanban/tests/ci/test_github_workflows.py`
    - `docs/qa/KANBA-181/*`
  - Unmodified & Preserved:
    - `.forgejo/workflows/ci.yml` (preserved intact for self-hosted `inferrence1` runner execution with Dash reporting and PostgreSQL fixtures)
    - Zero changes to application, wiki, or frontend files.

## 2. Implemented Architecture & Dual-Track Topology

### A. Public GitHub Actions (`.github/workflows/ci.yml`)
1. **Public Runner Isolation (`ubuntu-latest`):**
   - Every job (`lint-and-syntax`, `web-smoke`, `docker-smoke`, `docker-publish`) explicitly declares `runs-on: ubuntu-latest`.
   - Zero dependencies on self-hosted runners (`inferrence1`), private network endpoints, or secret hardware.
2. **Shift-Left Fast Gates:**
   - `lint-and-syntax`: Executes `uv run ruff check`, `uv run ruff format --check`, dash-check, and fast smoke unit tests (`scripts/tests/test_ci_workflow.py`, `tests/test_workspace_layout.py`, `kanban/tests/ci/test_github_workflows.py`) in < 2 seconds without external DB.
   - `web-smoke`: Executes `pnpm --dir kanban/web lint`, `pnpm --dir kanban/web typecheck`, and `pnpm --dir kanban/web build`.
   - `docker-smoke`: Builds `runtime-slim` and `standalone` container images without pushing.
3. **Graceful Credential Gating:**
   - `docker-publish`: Step `check-auth` checks `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`; skips without error (`exit 0`) if missing.
4. **Hardened Security Boundaries:**
   - Permissions: Strictly `contents: read`.
   - Concurrency: `cancel-in-progress: true` keyed by ref.
   - Pinning: All GitHub actions pinned to 40-character commit SHAs.
   - Zero private network references (no RFC 1918 IPs, zero Dash secrets or internal endpoints).

### B. Hardened Dash Upload Fallback (`scripts/ci/upload_dash_log.sh`)
- Parameterized `DASH_ENDPOINT` via environment variables with safe defaults/guards:
  `DASH_ENDPOINT="${DASH_ENDPOINT:-${DASH_URL:-https://dash.hackedyour.info}}"`
- Added strict skip guard:
  `if [ -z "${DASH_TOKEN:-}" ] || [ -z "${DASH_ENDPOINT:-}" ]; then`
  Exits cleanly with return code `0` and diagnostic notice when tokens or endpoints are missing (e.g. public forks, unauthenticated runners, local dev).

### C. Test Verification Suite (`kanban/tests/ci/test_github_workflows.py`)
- `test_workflow_syntax_and_runner_targets`: Parses `.github/workflows/*.yml` via PyYAML, asserting valid syntax, `runs-on: ubuntu-latest` on all jobs, timeout bounds (<= 20m), and 40-char SHA action pinning.
- `test_dash_upload_graceful_fallback`: Tests `upload_dash_log.sh` with missing `DASH_TOKEN`, empty `DASH_ENDPOINT`, and both unset; asserts exit code `0` and fallback notice.
- `test_zero_private_network_leaks`: Recursively scans all files in `.github/` asserting zero RFC 1918 private IPv4 addresses (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
- `test_github_workflow_secrets_isolation`: Asserts zero occurrences of `inferrence1`, `DASH_TOKEN`, `dash.hackedyour.info`, or `upload_dash_log.sh` in GitHub workflows.

## 3. Passive Forensic Artifacts Manifest
- `docs/qa/KANBA-181/git-diff.patch`: Exact patch of all KANBA-181 changes.
- `docs/qa/KANBA-181/changed-files-manifest.txt`: List of touched files.
- `docs/qa/KANBA-181/unit-test-results.txt`: Verbatim output of `uv run pytest kanban/tests/ci/test_github_workflows.py scripts/tests/test_ci_workflow.py -v` (26 passed).
- `docs/qa/KANBA-181/build-check.txt`: Verbatim output of `ruff check`, `ruff format --check`, YAML parsing, and bash syntax checks.
- `docs/qa/KANBA-181/workflow-audit.json`: Structured JSON audit of GitHub Actions and Forgejo CI topologies, runners, triggers, and secret guards.

## 4. Verification Proof Summary
- **Pytest:** 26 passed in 0.12s (`20` existing CI workflow tests + `6` new GitHub workflow verification tests).
- **Linter/Formatter:** Zero ruff errors, zero format discrepancies.
- **Syntaxes:** YAML and Bash syntax validated.
