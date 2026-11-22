# CI Pipeline (KB-P0-06 / KANBA-28)

The project employs a dual-workflow topology to support both internal self-hosted continuous integration and public GitHub publishing:

1. **Self-Hosted Forgejo CI (`.forgejo/workflows/ci.yml`):** Runs on the project Forgejo runner `inferrence1`. Triggers: `push` (all branches) and `pull_request` (never `pull_request_target`). Executes the complete security, test, and performance verification suite against local Postgres test containers, uploading step logs to Dash (`dash.hackedyour.info`).
2. **Public GitHub Actions CI (`.github/workflows/ci.yml`):** Runs on standard GitHub-hosted runners (`ubuntu-latest`) for public pushes and pull requests. Provides lightweight, neutered verification (syntax checks, web smoke builds, Docker smoke builds, and optional container publishing when credentials are configured) without hanging on private runners or leaking internal endpoints.

Both pipelines enforce `contents: read` token permissions, bounded timeouts (`<= 20` minutes), cancel-in-progress concurrency, and fully SHA-pinned actions (`owner/repo@<40-hex> # vX.Y.Z`).

## Jobs

### Forgejo Pipeline (`inferrence1`)

| Job id | Commands (each wrapped by `scripts/ci/run_and_log.sh`) |
| :--- | :--- |
| `lint-type` | `uv sync --locked && make check` |
| `python-tests` | `make testdb-up`; `uv run pytest -m "not container" --cov=database --cov=kanban --cov=mcp --cov=agent --cov=scripts --cov-branch --cov-report=term-missing --cov-report=xml:reports/coverage.xml --cov-fail-under=95 --junitxml=reports/pytest.xml`; `make testdb-down` (`if: always()`) |
| `stride-security-gate` | `make testdb-up`; `uv run pytest tests/security -q`; `make testdb-down` (`if: always()`) |
| `web-tests` | `pnpm install --frozen-lockfile --ignore-scripts`; `pnpm --dir kanban/web typecheck`; `lint`; `test:unit --coverage`; `build` |
| `license-gate` | `uv sync --locked && pnpm install --frozen-lockfile --ignore-scripts && make license` |
| `docker-build` | `docker buildx build --target runtime-slim -t kanban:runtime-slim --load .`; same for `--target standalone`; `docker image ls kanban` |
| `perf-budgets` | `make testdb-up`; `uv run python scripts/perf_budget_gate.py --report-out docs/qa/KANBA-151/perf-report.json`; `make testdb-down` (`if: always()`) |
| `docker-push` | `needs` all seven jobs above; runs only for `push` to `refs/heads/main`; `docker/login-action` then `docker/build-push-action` push `<DOCKERHUB_USERNAME>/thumbs-up-kanban:latest` |

### GitHub Actions Pipeline (`ubuntu-latest`)

| Job id | Commands |
| :--- | :--- |
| `lint-and-syntax` | `uv sync --locked`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run python -m scripts.check_no_dashes --all` |
| `web-smoke` | `pnpm install --frozen-lockfile --ignore-scripts`; `pnpm --dir kanban/web typecheck`; `pnpm --dir kanban/web build` |
| `docker-smoke` | `docker buildx build --target runtime-slim -t kanban:runtime-slim --load .`; `docker buildx build --target standalone -t kanban:standalone --load .`; `docker image ls kanban` |
| `docker-publish` | `needs` smoke jobs above; checks if `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` are set; publishes `<DOCKERHUB_USERNAME>/thumbs-up-kanban:latest` if configured |

## Reading Logs

For Forgejo runs, `scripts/ci/run_and_log.sh <logname> -- <command...>` runs the command as an argv vector (no `eval`), tees combined stdout and stderr, and exits with the command's exit code. Log names must match `^[a-z0-9-]+$` (otherwise exit `64`, nothing written). Per wrapped step it writes under `ci-logs/<job-id>/`: `<logname>.log` (output) and `<logname>.exit` (exit code).

Every Forgejo job ends with two `if: always()` steps:
1. `scripts/ci/upload_dash_log.sh <job-id>` POSTs the job's logs to Dash (`/api/logs?provider=forgejo&owner=ThumbsUp-HQ&repo=kanban&sha=<sha>`), prefixing any log already stored for that SHA. A missing `DASH_TOKEN` or a Dash outage never fails the job.
2. `actions/upload-artifact` uploads `ci-logs/` as `ci-logs-<job-id>` (14 days). `python-tests` also uploads `reports/` (`coverage.xml`, `pytest.xml`) as `ci-reports-python-tests`.

Artifact names: `ci-logs-lint-type`, `ci-logs-python-tests`, `ci-logs-stride-security-gate`, `ci-logs-web-tests`, `ci-logs-license-gate`, `ci-logs-docker-build`, `ci-logs-perf-budgets`, `ci-logs-docker-push`, `ci-reports-python-tests`.

## Dash Verification

Follow the flow from <https://dash.hackedyour.info/llms.txt> with the Dash MCP tools:

1. After `git push`, call Dash `status` for the repo (pin to the pushed SHA).
2. Call Dash `wait` until the run completes. Never poll with manual `sleep` loops.
3. On failure, call Dash `logs` and read the uploaded log (look for the failing `=== ci-logs/<job>/<step>.log (exit N) ===` section) before changing code.

A red `main` is an emergency: halt all other work and fix it before anything else (AGENTS.md, Broken Build Taboo).

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

Resolve the new tag to a commit SHA (peel annotated tags: use the `^{}` line from `git ls-remote --tags https://github.com/<owner>/<repo>.git`), update every occurrence in both workflow files together, keep the `# vX.Y.Z` comment, and re-run the tests above.
