# CI Pipeline (KB-P0-06)

CI runs on the project Forgejo runner `inferrence1`. The workflow lives at
`.forgejo/workflows/ci.yml` and is mirrored byte-for-byte at `.github/workflows/ci.yml`
(a unit test fails if the two drift). Triggers: `push` (all branches) and `pull_request`
(never `pull_request_target`). Concurrent runs on the same ref are cancelled. The token
permissions are `contents: read` only, every job has `timeout-minutes: 20`, and every
`uses:` is pinned to a full 40-character commit SHA with a trailing `# vX.Y.Z` comment.

## Jobs

| Job id | Commands (each wrapped by `scripts/ci/run_and_log.sh`) |
| :--- | :--- |
| `lint-type` | `uv sync --locked && make check` |
| `python-tests` | `make testdb-up`; `uv run pytest -n auto -m "not container" --cov=database --cov=kanban --cov=mcp --cov=agent --cov=scripts --cov-branch --cov-report=term-missing --cov-report=xml:reports/coverage.xml --cov-fail-under=95 --junitxml=reports/pytest.xml`; `make testdb-down` (`if: always()`) |
| `web-tests` | `pnpm install --frozen-lockfile --ignore-scripts`; `pnpm --dir kanban/web typecheck`; `lint`; `test:unit --coverage`; `build` |
| `license-gate` | `uv sync --locked && pnpm install --frozen-lockfile --ignore-scripts && make license` |
| `docker-build` | `docker buildx build --target runtime-slim -t kanban:runtime-slim --load .`; same for `--target standalone`; `docker image ls kanban` |
| `docker-push` | `needs` all five jobs above; runs only for `push` to `refs/heads/main`; `docker/login-action` then `docker/build-push-action` push `<DOCKERHUB_USERNAME>/thumbs-up-kanban:latest` |

Deviations from the original ticket text, kept deliberately because they are what works on
the `inferrence1` act_runner:

- `python-tests` starts the database with `make testdb-up` (sibling container sharing the
  workspace volume) instead of `docker compose`, and runs `-m "not container"` because the
  runner has no nested Docker for container-marked tests.
- `docker-build` builds both image targets locally and never pushes. Publishing is isolated in
  `docker-push`, which keeps the pre-existing Docker Hub publish behavior but only on main
  pushes after every other job is green. `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` are
  referenced only inside `docker-push` (via the pinned login/build-push actions), never in a
  `run:` body; `DASH_TOKEN` is referenced only in each job's Dash upload step `env:`. A test
  enforces this scoping.

## Reading Logs

`scripts/ci/run_and_log.sh <logname> -- <command...>` runs the command as an argv vector
(no `eval`), tees combined stdout and stderr, and exits with the command's exit code.
Log names must match `^[a-z0-9-]+$` (otherwise exit `64`, nothing written). Per wrapped step
it writes under `ci-logs/<job-id>/`: `<logname>.log` (output) and `<logname>.exit` (exit code).

Every job (including `docker-push`) ends with two `if: always()` steps:

1. `scripts/ci/upload_dash_log.sh <job-id>` POSTs the job's logs to Dash
   (`/api/logs?provider=forgejo&owner=AI&repo=thumbs-up-kanban&sha=<sha>`), prefixing any log
   already stored for that SHA because the five jobs share one Dash log slot. Certificate
   verification is on. A missing `DASH_TOKEN` or a Dash outage never fails the job. The
   token is passed through `env:` and never printed.
2. `actions/upload-artifact` uploads `ci-logs/` as `ci-logs-<job-id>` (14 days). `python-tests`
   also uploads `reports/` (`coverage.xml`, `pytest.xml`) as `ci-reports-python-tests`. Artifact
   uploads use `continue-on-error: true` because upload-artifact v4 is not universally
   supported by Forgejo runners; the Dash upload is the reliable channel.

Artifact names: `ci-logs-lint-type`, `ci-logs-python-tests`, `ci-logs-web-tests`,
`ci-logs-license-gate`, `ci-logs-docker-build`, `ci-logs-docker-push` (main pushes only),
`ci-reports-python-tests`.

## Dash Verification

Follow the flow from <https://dash.hackedyour.info/llms.txt> with the Dash MCP tools:

1. After `git push`, call Dash `status` for the repo (pin to the pushed SHA).
2. Call Dash `wait` until the run completes. Never poll with manual `sleep` loops.
3. On failure, call Dash `logs` and read the uploaded log (look for the failing
   `=== ci-logs/<job>/<step>.log (exit N) ===` section) before changing code.

A red `main` is an emergency: halt all other work and fix it before anything else
(AGENTS.md, Broken Build Taboo).

## Local validation

```bash
uv run pytest scripts/tests/test_ci_workflow.py scripts/tests/test_run_and_log.py \
  scripts/tests/test_upload_dash_log.py -q
docker run --rm -v "$PWD:/repo" -w /repo \
  rhysd/actionlint@sha256:887a259a5a534f3c4f36cb02dca341673c6089431057242cdc931e9f133147e9 \
  -no-color .github/workflows/ci.yml .forgejo/workflows/ci.yml
```

The runner label `inferrence1` is declared in `.github/actionlint.yaml`.

## Updating pinned actions

Resolve the new tag to a commit SHA (peel annotated tags: use the `^{}` line from
`git ls-remote --tags https://github.com/<owner>/<repo>.git`), update every occurrence in
both workflow files together, keep the `# vX.Y.Z` comment, and re-run the tests above.
