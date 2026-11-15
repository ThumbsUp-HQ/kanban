# Integration Agent Reality-Based Report

**Ticket:** `KANBA-28` (`KB-P0-06`) - `[Phase 0 / CI] GitHub Actions CI pipeline + Dash integration` (Full Option B + `docker-push` pipeline)
**Audited Commits on `main` / `origin/main`:** `20a2586`, `d4361ca`, `628f622`, `ca18c90`
**Remote CI Run Verified:** Forgejo Run `30` / Dash Run `845` on runner `inferrence1` (`status: success`, all 6 jobs green)

---

## 1. Evidence & DoD Verification Matrix

| DoD / Security Criterion | Forensic Evidence Inspected | Result |
| :--- | :--- | :--- |
| **Workflow Topology & Byte-Identical Parity** | `.github/workflows/ci.yml` and `.forgejo/workflows/ci.yml` define `lint-type`, `python-tests`, `web-tests`, `license-gate`, `docker-build`, and `docker-push` on `[inferrence1]`. `test_workflow_copies_are_identical` asserts zero drift. | **PASS** |
| **Hardened Action Pinning & Least Privilege** | Top-level `permissions: { contents: read }`, `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }`, `timeout-minutes: 20` on all 6 jobs, zero `pull_request_target`, and every `uses:` pinned to a full 40-hex commit SHA with `# vX.Y.Z` comment (`checkout@34e1148...`, `setup-python@a26af69...`, `setup-uv@d4b2f3b...`, `action-setup@fc06bc1...`, `setup-node@49933ea...`, `setup-buildx-action@8d2750c...`, `login-action@c94ce9f...`, `build-push-action@ca052bb...`, `upload-artifact@ea165f8...`). | **PASS** |
| **Secret Isolation & `docker-push` Gating** | `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` exist strictly inside `docker-push` (`needs: [lint-type, python-tests, web-tests, license-gate, docker-build]`, `if: github.ref == 'refs/heads/main' && github.event_name == 'push'`). `DASH_TOKEN` is passed strictly via step `env:` (never interpolated in `run:` scripts, never echoed). TLS verification stays ON in `upload_dash_log.sh` (no `curl -k`). | **PASS** |
| **Command Wrapping & `if: always()` Log Upload** | `scripts/ci/run_and_log.sh` uses `set -euo pipefail`, validates `^[a-z0-9-]+$` (exit `64` on traversal/invalid), executes argv directly without `eval`, and writes `.log` + `.exit`. Every job ends with `if: always()` `scripts/ci/upload_dash_log.sh <job>` and `if: always()` `actions/upload-artifact` (`ci-logs-${{ github.job }}`), plus `reports/` artifact upload on `python-tests`. | **PASS** |
| **Feature & Full-Suite Unit Tests** | `scripts/tests/test_ci_workflow.py` (21), `test_run_and_log.py` (8), `test_upload_dash_log.py` (6): `35 passed` (`exit: 0`). Full Python suite: `2,475 passed` locally (`97.36%` branch coverage >= `95%`) and `2,463 passed` in CI Run 30. Web suite: `163` files / `1,691 passed` (`95.32%` branch coverage). | **PASS** |
| **Static Analysis, Actionlint & License Gate** | `make check` (`ruff check`, `ruff format --check`, `mypy` strict across 964 files, `lint-imports` 2/2 contracts kept, `check_no_dashes --all`): `exit: 0`. Digest-pinned `rhysd/actionlint@sha256:887a259a...`: `exit: 0`. `make license`: `SUMMARY python=116 node=1 violations=0` (`exit: 0`). | **PASS** |
| **Remote CI Green & Dash Logs Uploaded (Run 30 / Dash 845)** | `docs/qa/KANBA-28/dash-status.txt` (4,417 lines) captures raw Dash JSON (`status: "success"`, Run ID `845`, Forgejo Run `30` for commit `ca18c90814f5d991ccdebf7bd1a2dfbdcb77dca4`) and all 6 job log headers (`##### job: lint-type #####`, `python-tests`, `web-tests`, `license-gate`, `docker-build`, `docker-push`) with 15 step logs all exiting `(exit 0)`. | **PASS** |
| **Dependency Evaluation (`pyyaml==6.0.3`)** | `docs/qa/KANBA-28/dependency-evaluation.md` documents MIT license (`violations=0`), pinned `pyyaml==6.0.3` with `sha256:d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f` (promoted from existing locked transitive dependency in `uv.lock` to explicit `dev` group), and strict `yaml.safe_load`-only usage. | **PASS** |

---

## 2. Audited & Approved Runner Adaptations

All operational adaptations documented in `docs/qa/KANBA-28/message-to-reality-checker.md` and `docs/CI.md` are verified sound and necessary for the self-hosted Forgejo `inferrence1` runner:
1. **`make testdb-up` / `make testdb-down` and serial pytest (`-m "not container"`, no `-n auto`):** Avoids nested-Docker limitations and shared-DB DDL/card-rank collisions observed in Run 28.
2. **6th `docker-push` job:** Preserves `docker-build` as a secret-free local `--load` verification of both `runtime-slim` and `standalone` targets while isolating Docker Hub publication (`thumbs-up-kanban:latest`) behind all 5 quality gates on `main` pushes.
3. **Dual log channels (`upload_dash_log.sh` + `upload-artifact` with `continue-on-error: true`):** Satisfies the ticket's `actions/upload-artifact` step requirement while ensuring Forgejo runner artifact-API limitations never mask logs or fail builds, because full per-job logs are reliably streamed to Dash `/api/logs` (and embedded verbatim in `dash-status.txt` in lieu of separate GitHub API artifact downloads).
4. **Web test stability fixes (`vitest.config.ts` `testTimeout: 15000` and string body in `StandaloneStatusPanel.test.tsx`):** Resolves Node 22 `undici` + `jsdom` `Blob.stream()` incompatibility exposed in Run 29.

---

## 3. Verdict

- **Overall Quality Rating:** **Grade A**
- **Production Readiness:** **READY**
