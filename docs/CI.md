# CI Pipeline (KB-P0-06)

CI runs on the project Forgejo runner `inferrence1` (workflow
`.forgejo/workflows/ci.yml`, mirrored byte-for-byte at `.github/workflows/ci.yml`; a unit
test fails if the two drift). It is a single job, `build-test-push`.

## Jobs

| Job id | Step | Command (wrapped by `scripts/ci/run_and_log.sh`) | Log name |
| :--- | :--- | :--- | :--- |
| `build-test-push` | Run lint and checks | `uv sync --locked && make check && make license` | `lint-type-license` |
| `build-test-push` | Start test database | `make testdb-up` | `testdb-up` |
| `build-test-push` | Run tests | `uv run pytest -q -m "not container"` | `unit-tests` |
| `build-test-push` | Stop test database (`if: always()`) | `make testdb-down` | `testdb-down` |
| `build-test-push` | Docker Buildx build and push | `docker/build-push-action` | (not captured) |
| `build-test-push` | Upload logs to Dash (`if: always()`, last step) | `curl` POST of all step logs | n/a |

The workflow triggers on `push` to `main` and on `pull_request`. It never uses
`pull_request_target`. The only secrets referenced are `DOCKERHUB_USERNAME`,
`DOCKERHUB_TOKEN` and `DASH_TOKEN`; `DASH_TOKEN` is passed through `env:` and never
interpolated into the script body.

## Reading Logs

`scripts/ci/run_and_log.sh <logname> -- <command...>` runs the command as an argv vector
(no `eval`), tees combined stdout and stderr, and exits with the command's exit code.
Log names must match `^[a-z0-9-]+$` (otherwise exit `64`, nothing written).

For each wrapped step it writes, under `ci-logs/build-test-push/`:

- `<logname>.log`: combined stdout and stderr
- `<logname>.exit`: the exit code

The final `Upload logs to Dash` step concatenates every `ci-logs/*/*.log` (each prefixed
with a `=== <path> (exit <n>) ===` header) into `build.log` and POSTs it to
`https://dash.hackedyour.info/api/logs?provider=forgejo&owner=AI&repo=thumbs-up-kanban`.
A missing `DASH_TOKEN` or an upload error never fails the job. Retrieve the uploaded log
with the Dash `logs` tool (see below).

## Dash Verification

Follow the flow from <https://dash.hackedyour.info/llms.txt> with the Dash MCP tools:

1. After `git push`, call Dash `status` for the repo to see the run for the pushed SHA.
2. Call Dash `wait` until the run completes. Never poll with manual `sleep` loops.
3. On failure, call Dash `logs` and read the uploaded `build.log` (look for the failing
   `=== ci-logs/... (exit N) ===` section) before changing code.

A red `main` is an emergency: halt all other work and fix it before anything else
(AGENTS.md, Broken Build Taboo).

## Local validation

```bash
uv run pytest scripts/tests/test_ci_workflow.py scripts/tests/test_run_and_log.py -q
docker run --rm -v "$PWD:/repo" -w /repo \
  rhysd/actionlint@sha256:887a259a5a534f3c4f36cb02dca341673c6089431057242cdc931e9f133147e9 \
  -no-color .github/workflows/ci.yml .forgejo/workflows/ci.yml
```

The runner label `inferrence1` is declared in `.github/actionlint.yaml`.

## Known gaps (follow-ups)

- `uses:` references are tag-pinned (`@v4`), not 40-char SHA-pinned.
- The Dash upload uses `curl -k` (certificate verification off), inherited from the original workflow.
- The workflow is single-job; the multi-job split (web tests, docker build matrix) is not done.
