# KANBA-28 (KB-P0-06) Handoff to reality-checker

Commit under audit: `dc1dcc5` (pushed to origin/main). Ticket: `docs/tickets/KB-P0-06.md`.

## Scope actually delivered (minimal, single-job)

Per coordinator and orchestrator instruction, the existing Forgejo `build-test-push` workflow
on runner `inferrence1` was REUSED, not replaced by the ticket's 5-job design. Delivered:

- `scripts/ci/run_and_log.sh`: argv-only wrapper, logs to `ci-logs/<job>/<name>.log|.exit`,
  rejects names outside `^[a-z0-9-]+$` with exit 64.
- `.forgejo/workflows/ci.yml` and `.github/workflows/ci.yml` (byte-identical, enforced by test):
  lint, test-DB and test steps wrapped by `run_and_log.sh`; final `if: always()` step uploads all
  step logs to Dash `/api/logs`, token via `env:`.
- `docs/CI.md` (`## Jobs`, `## Reading Logs`, `## Dash Verification`), `.github/actionlint.yaml`.
- Tests: `scripts/tests/test_ci_workflow.py`, `scripts/tests/test_run_and_log.py` (21 pass).

## Ticket items intentionally NOT met (do not grade as done)

| Ticket requirement | Status |
| :--- | :--- |
| 5 jobs (`lint-type`, `python-tests`, `web-tests`, `license-gate`, `docker-build`) | NOT DONE: single job retained |
| Every `uses:` pinned to 40-char SHA | NOT DONE: tags (`@v4`) retained |
| Top-level `permissions: contents: read`, per-job `timeout-minutes <= 20` | NOT DONE |
| `upload-artifact` of `ci-logs/` and `reports/`; `ci-artifact-listing.txt`, `ci-logs/` copies | N/A: logs go to Dash, not artifacts |
| `pyyaml` explicit dev dependency in `pyproject.toml`/`uv.lock` | NOT DONE: already locked transitively; no manifest change (see `dependency-evaluation.md`) |
| `--cov=scripts.ci --cov-fail-under=95` | CANNOT PASS: `scripts/ci` is bash; documented in `unit-test-results.txt` |
| `actionlint -color=never` | Flag invalid in 1.7.7; `-no-color` used, digest pinned, exit 0 |
| "Never reference secrets" | Workflow still references `DOCKERHUB_*` (pre-existing) and `DASH_TOKEN` (required for upload) |
| Remote CI green (Dash `wait`) | See `dash-status.txt` (written by orchestrator worker 4); builder could not produce it |

Known gaps are also listed in `docs/CI.md`. Follow-up tickets are recommended for the
multi-job split, SHA pinning, least-privilege `permissions`, and removing `curl -k`.

## Artifacts

`git-diff.patch`, `unit-test-results.txt`, `build-check.txt` (make check exit 0, actionlint exit 0),
`dependency-evaluation.md`, `dash-status.txt`, this file.
