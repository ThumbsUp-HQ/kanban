# KANBA-28 (KB-P0-06) Handoff to reality-checker (Option B, full scope)

Supersedes the earlier minimal single-job handoff (commit 52e14f9). User decision: implement the
full ticket scope.

## Delivered

- `.forgejo/workflows/ci.yml` and `.github/workflows/ci.yml` (byte-identical, enforced by test):
  jobs `lint-type`, `python-tests`, `web-tests`, `license-gate`, `docker-build` on `inferrence1`, plus a 6th job `docker-push` (orchestrator follow-up: `needs` all five, main pushes only, Docker Hub secrets scoped to that job, pinned login/build-push actions);
  `on: push` (all branches) and `pull_request`; `concurrency` cancel-in-progress; top-level
  `permissions: {contents: read}`; `timeout-minutes: 20` on every job; every `uses:` pinned to a
  40-char commit SHA with a `# vX.Y.Z` comment (SHAs peeled from `git ls-remote` tags).
- Every command step runs through `scripts/ci/run_and_log.sh` (unchanged). Each job ends with an
  `if: always()` Dash upload (`scripts/ci/upload_dash_log.sh`, new, best effort, token via `env:`,
  TLS verification on) followed by an `if: always()` `actions/upload-artifact` of `ci-logs/`
  (`ci-logs-<job>`); `python-tests` also uploads `reports/` (`coverage.xml`, `pytest.xml`).
- `pyyaml==6.0.3` explicit in the dev group and `uv.lock` (see `dependency-evaluation.md`).
- `docs/CI.md` rewritten for the 5-job layout; `.github/actionlint.yaml` declares `inferrence1`.
- Tests: `scripts/tests/test_ci_workflow.py` (21), `test_run_and_log.py` (8),
  `test_upload_dash_log.py` (6, loopback fake Dash server).

## Deviations from ticket text (deliberate, please grade knowingly)

| Ticket text | What was done | Why |
| :--- | :--- | :--- |
| `docker compose -f docker-compose.test.yml up -d --wait` | `make testdb-up` / `make testdb-down` | act_runner needs the sibling-container + shared-volume path in `scripts/testdb_up.sh` (proven on run 24) |
| pytest without marker filter | `-m "not container"` | runner has no nested Docker for container-marked tests (as before) |
| "No secrets referenced in any job" | `DASH_TOKEN` via step `env:` in every job; `DOCKERHUB_*` only inside `docker-push` | Dash upload and Docker Hub publish require them; orchestrator requirement; enforced by a test |
| `docker-build` build only | `docker-build` builds with `--load` only; publish moved to new `docker-push` job | keeps the old Docker Hub publish (`thumbs-up-kanban:latest`) without leaking `DOCKERHUB_*` into the 5 ticket jobs |
| `actionlint -color=never` | `-no-color` | `-color=never` is rejected by actionlint 1.7.7 |
| `upload-artifact` must succeed | `continue-on-error: true` on both artifact uploads | v4 artifacts are not universally supported by Forgejo runners (Dash llms.txt); Dash upload is the reliable channel |
| (not in ticket) | `kanban/web/vitest.config.ts` `testTimeout` 5s -> 15s | heaviest jsdom route test measured 5.1s alone with coverage, 13s under load, and timed out |
| (not in ticket) | `.gitignore` adds `reports/` | pytest/coverage report output dir |

## Known limitations

- Dash keeps one log per (repo, sha); the five parallel jobs read-then-append before POST, so a
  rare race can drop one job's section. A per-job artifact still holds every log.
- The run on the Forgejo runner for this commit has not happened yet at the time of writing;
  `dash-status.txt` holds the run-24 evidence for the previous single-job commit until the
  orchestrator appends the new run (if present, the newest section is authoritative).
- Full Python suite is clean with `-n 6` locally (2475 passed, 97.36%). With `-n auto` on the shared
  20-core host (load ~9-13) two timing-sensitive tests (`test_nsjail_runner` stdout-cap 3s wait,
  `test_local_login` enumeration timing) failed; both pass alone. CI uses `-n auto` per the ticket;
  if they flake on the runner, relax the worker count or file a follow-up. Tests not modified.
