---
id: KB-E0
title: "[Phase 0 / Epic] Monorepo, CI, Containers & Test Harness"
type: epic
children: [KB-P0-01, KB-P0-02, KB-P0-03, KB-P0-04, KB-P0-05, KB-P0-06, KB-P0-07, KB-P0-08, KB-P0-09, KB-P0-10, KB-P0-11, KB-P0-12, KB-P0-13]
spec_sections: ["2.1", "2.2", "2.3", "2.4", "2.5", "5.4", "10.1", "15.1", "15.2", "15.3", "15.4", "15.5"]
gates: [reality-checker]
state: Backlog
---

### Goal
Stand up the `[database, kanban, mcp, agent]` `uv` workspace, the `kanban/web` React 19 skeleton, the strict lint/type/license gates, the `tmpfs` PG16 clean-DB test harness, the multi-stage `Dockerfile` (`runtime-slim` + default `standalone`), the zero-config standalone entrypoint, the production `docker-compose.yml` + `Caddyfile`, the deterministic AI fixture layer, and the GitHub Actions + Dash CI pipeline, so every later phase lands on a green, reproducible, license-clean baseline.

### Scope Summary
- Workspace and module boundaries: root `pyproject.toml`, `uv.lock`, `import-linter` contract `agent -> mcp -> kanban -> database`, per-module `GEMINI.md` + `AGENTS.md` symlink.
- Quality gates: `ruff`, `mypy --strict`, `pre-commit`, ESLint, `tsc --noEmit`, `vitest` and `pytest` coverage thresholds of `95%`, `Apache-2.0` license gate.
- Test infrastructure: `docker-compose.test.yml` (`tmpfs` PG16), golden `kanban_template` DB, per-test `SAVEPOINT` rollback, `pytest-socket`, `FixtureLLMProvider` / `FixtureCLIRunner`, `kanban-agent` CLI skeleton.
- Containers and edge: 4-stage `Dockerfile`, `deploy/standalone/entrypoint.py`, first-boot keyring, ASGI app factory with CSP, `docker-compose.yml` network matrix, `deploy/caddy/Caddyfile`.
- CI: `.github/workflows/ci.yml` with always-uploaded logs, Dash `status` / `wait` / `logs` documented in `docs/CI.md`.

### Child Tickets
| ID | Title | Deps |
| :-- | :-- | :-- |
| KB-P0-01 | Monorepo `uv` workspace skeleton & module manifests | None |
| KB-P0-02 | Python strict lint/type toolchain & pre-commit | KB-P0-01 |
| KB-P0-03 | Frontend skeleton `kanban/web` (React 19 + Vite + TS strict) | KB-P0-01 |
| KB-P0-04 | `Apache-2.0` license gate | KB-P0-01, KB-P0-03 |
| KB-P0-05 | Fast clean-DB test harness (`tmpfs` PG16 + template + `SAVEPOINT`) | KB-P0-01 |
| KB-P0-06 | GitHub Actions CI pipeline + Dash integration | KB-P0-02, KB-P0-03, KB-P0-04, KB-P0-05 |
| KB-P0-07 | Multi-stage `Dockerfile` (`web-builder`, `py-builder`, `runtime-slim`, `standalone`) | KB-P0-01, KB-P0-03 |
| KB-P0-08 | Standalone entrypoint: embedded Unix-socket PG16 boot | KB-P0-07 |
| KB-P0-09 | Standalone first-boot keyring & ephemeral-storage detection | KB-P0-08 |
| KB-P0-10 | ASGI app factory, `PrecompressedSPAStaticApp` & security headers | KB-P0-01, KB-P0-03 |
| KB-P0-11 | Production `docker-compose.yml` + `Caddyfile` | KB-P0-07, KB-P0-10 |
| KB-P0-12 | `LLMProvider` protocol + `FixtureLLMProvider` + `FixtureCLIRunner` | KB-P0-01 |
| KB-P0-13 | `kanban-agent` CLI framework skeleton | KB-P0-12 |

### Epic Definition of Done
- [ ] All 13 child tickets (KB-P0-01 .. KB-P0-13) are in state `Done`, each closed only after a local `reality-checker` grade-A `READY` certification recorded in its `docs/qa/<TICKET_ID>/` bundle.
- [ ] Every child ticket tagged `[UI]` has `docs/qa/<TICKET_ID>/ui-specialist-review.md`; every child tagged `[API]` has both `api-specialist-review.md` and `ui-specialist-review.md`; every child tagged `[DEP]` has `dependency-evaluation.md`.
- [ ] Phase-level CI is green via Dash (`status` / `wait` / `logs`) on the `main` commit that closes the last child ticket, with all CI jobs passing and `--cov-fail-under=95` / `vitest` `95%` thresholds enforced.
- [ ] Zero open tickets labeled as gaps discovered during this phase remain unlinked to a follow-up ticket.

### Exit Criteria (Spec S15.5)
- Spec S15.5 item 1 (Phase 0): Root `LICENSE`, `[database, kanban, mcp, agent]` workspace, `Dockerfile` (`runtime-slim` + `standalone` Unix-socket PG16), `Caddyfile`, `tmpfs` `SAVEPOINT` test harness, `FixtureLLMProvider`, and Dash CI pipeline.
- `docker run -p 8080:8080 kanban:latest` (image built from `--target standalone`) boots to a listening `:8080` in `< 3s` with zero TCP PostgreSQL port (KB-P0-08 proof).
- 200 trivial DB tests execute in `< 5s` on the clean-DB harness (KB-P0-05 proof).
- CI workflow on `main` is green for all jobs: lint/type, python tests, web tests, license gate, docker build (KB-P0-06 proof).
