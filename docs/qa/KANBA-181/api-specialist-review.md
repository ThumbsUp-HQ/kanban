# Backend Architect / API Specialist Review: KANBA-181

- **Reviewer:** Backend Architect / API Specialist (`arch-reviewer`)
- **Date:** 2026-11-15
- **Ticket:** KANBA-181 ([CI/CD / Release] Prepare Repository for GitHub Publishing: Dual-Track CI with Neutered Public GitHub Actions and Preserved Self-Hosted Dash CI)
- **Scope Inspected:**
  - `.github/workflows/ci.yml`
  - `scripts/ci/upload_dash_log.sh`
  - `kanban/tests/ci/__init__.py`
  - `kanban/tests/ci/test_github_workflows.py`
  - `docs/qa/KANBA-181/message-to-reality-checker.md`
  - `docs/qa/KANBA-181/unit-test-results.txt`
  - `docs/qa/KANBA-181/build-check.txt`
  - `docs/qa/KANBA-181/workflow-audit.json`
  - `docs/qa/KANBA-181/git-diff.patch`

---

## 1. Architectural & Security Evaluation

### A. Dual-Track Pipeline Topology & Runner Isolation
- The architectural separation between the internal self-hosted pipeline (`.forgejo/workflows/ci.yml`) and public GitHub Actions (`.github/workflows/ci.yml`) is completely enforced and cleanly decoupled.
- All public GitHub Actions jobs (`lint-and-syntax`, `web-smoke`, `docker-smoke`, `docker-publish`) explicitly declare `runs-on: ubuntu-latest`. Zero references to internal runners (`inferrence1`) exist in `.github/workflows/`.
- The self-hosted runner infrastructure, internal PostgreSQL test database fixtures, and private network telemetry remain strictly confined to Forgejo CI.

### B. Action Pinning & Principle of Least Privilege
- Every GitHub Action step utilizing external actions (`actions/checkout`, `actions/setup-python`, `astral-sh/setup-uv`, `pnpm/action-setup`, `actions/setup-node`, `docker/setup-buildx-action`, `docker/login-action`, `docker/build-push-action`) is strictly pinned to an immutable 40-character hexadecimal commit SHA.
- Top-level workflow permissions are strictly set to `permissions: contents: read`, adhering to the principle of least privilege.
- Every job defines an explicit timeout bound (`timeout-minutes: 15` or `20`), preventing runner hang exhaustion.
- Concurrency group `ci-${{ github.ref }}` with `cancel-in-progress: true` prevents redundant runs and race conditions on PR branches.

### C. Graceful Credential Gating & Fork Compatibility
- The `docker-publish` job properly checks for the presence of `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`. In public contributor PRs or forks where repository secrets are not provisioned, the step detects missing credentials and gracefully skips publishing without failing the pipeline.
- In `scripts/ci/upload_dash_log.sh`, parameterization of `DASH_ENDPOINT` with graceful fallback to `DASH_URL` and a strict null-check guard ensures that executions in unauthenticated or public environments cleanly output a notice and exit with status code `0`. A telemetry outage or missing secret will never fail a build.

### D. Leakage & Boundary Audit
- Scanned `.github/` directory for RFC 1918 private IPv4 blocks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`). Zero private network addresses or internal endpoints leak into public workflow files.
- No production application APIs or backend models were altered; the change is purely operational infrastructure and validation suites.

---

## 2. Test Suite & Verification Results
- Executed `uv run pytest kanban/tests/ci/test_github_workflows.py scripts/tests/test_ci_workflow.py -v`:
  - 26 tests collected and passed in 0.14s.
  - Confirmed 100% pass rate across YAML schema validation, runner assertions, Dash upload fallback behavior, private network isolation, and Forgejo/GitHub workflow invariant checks.
- Code quality validations:
  - `uv run ruff check kanban/tests/ci/ scripts/ci/` passed with zero errors.
  - `uv run ruff format --check kanban/tests/ci/` confirmed clean formatting.
  - `uv run python -m scripts.check_no_dashes --all` passed cleanly (no em-dash / en-dash violations).

---

## 3. Findings & Defect Summary
- **Critical Defects:** 0
- **Security Vulnerabilities:** 0
- **Schema / Invariant Violations:** 0
- **Regressions:** 0

All backend, CI/CD, and security invariants specified in `AGENTS.md` and `KANBA-181` are fully met.

---

**Verdict:** APPROVED
