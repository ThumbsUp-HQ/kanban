# KANBA-28 (KB-P0-06) Handoff to reality-checker (Option B, full scope + docker-push, commit d4361ca)

Supersedes the earlier minimal single-job handoff (commit 52e14f9). User decision: implement the
full ticket scope plus the 6th `docker-push` job (commits `20a2586` and `d4361ca`).

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
- `docs/CI.md` rewritten for the 6-job layout; `.github/actionlint.yaml` declares `inferrence1`.
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
| `pytest -n auto` | `pytest` without `-n auto` | on Forgejo Run 28 (`d4361ca`), `-n auto` xdist workers collided on the single test DB during DDL migration and card rank rebalancing tests |
| (not in ticket) | `kanban/web/vitest.config.ts` `testTimeout` 5s -> 15s + `StandaloneStatusPanel.test.tsx` (`new Response('...')` string body + `await waitFor`) | heaviest jsdom route test timed out at 5s under coverage; Node 22 undici `new Response(new Blob(...))` threw `object.stream is not a function` on jsdom Blob in Run 29 |
| (not in ticket) | `.gitignore` adds `reports/` | pytest/coverage report output dir |

## Known limitations

- Dash keeps one log per (repo, sha); the six jobs read-then-append before POST, so a
  rare race can drop one job's section. A per-job artifact still holds every log.
- After Run 28 (`d4361ca`) exposed the `-n auto` DB collision (fixed in `628f622`, `python-tests`
  green on Run 29) and Run 29 exposed the Node 22 undici `new Response(new Blob(...))` jsdom error
  in `StandaloneStatusPanel.test.tsx`, both are fixed and re-verified locally; Worker 4 will update
  `dash-status.txt` with the green Run 30 (newest section is authoritative).
