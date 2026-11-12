# Audit Manifest: KANBA-30 (KB-P0-11)

- **Ticket ID**: `KANBA-30` (`KB-P0-11`)
- **Title**: `[Phase 0 / Deploy] Production docker-compose.yml + Caddyfile with isolated network matrix`
- **Epic**: `KB-E0`
- **Branch**: `feat/KANBA-30` (isolated worktree at `/tmp/kb-wt-KANBA-30`)
- **Spec Sections**: Section 2.3, Section 2.4, Section 5.4

---

## 1. Executive Summary

This ticket delivers the production multi-container deployment infrastructure for the hardened Kanban platform in strict compliance with Section 2.3, Section 2.4, and Section 5.4 of the Authoritative Specification:
1. `docker-compose.yml`: Implements the exact 8-service and 5-network isolation matrix defined in Section 2.4. Services connect strictly to their designated networks, with `mcp-server` isolated to `app_net` (zero network route to `data_net` and no database credentials). Only `reverse-proxy` publishes external host ports (80, 443 TCP/UDP). Every service enforces `cap_drop: [ALL]`, `security_opt: ["no-new-privileges:true"]`, `read_only: true` with tmpfs mounts, non-root execution (`user: "65532:65532"` on application services), and secrets loaded via Docker Compose secrets without cleartext values.
2. `deploy/caddy/Caddyfile`: Implements the production reverse-proxy configuration with TLS 1.3 enforcement (`protocols tls1.3`), modern protocol negotiation (`h1 h2 h3`), unbuffered proxy streaming (`flush_interval -1`) for `/ws`, `/sse*`, and `/mcp/*`, precompressed Brotli and Gzip static file delivery, and security headers matching Section 5.4 with byte-identical `Content-Security-Policy` matching `kanban.security.headers.CSP_POLICY`.
3. `scripts/check_compose_networks.py`: Provides automated CLI validation asserting all 7 architectural invariants across services, networks, internal flags, port publishing, security options, plaintext secrets prevention, and profile isolation.
4. `scripts/tests/test_check_compose_networks.py`: Comprehensive test suite verifying all positive, negative/security mutation, and boundary scenarios with 97.33% branch and line coverage (exceeding the 95% threshold).
5. `tests/deploy/test_caddyfile.py`: Static assertion test suite validating TLS 1.3, unbuffered streaming handlers, precompressed static assets, and byte-identical CSP header injection.
6. `deploy/README.md`: Operator documentation covering 256-bit secrets generation, network isolation topology, and operational runbook.
7. `Makefile`: Added `compose-check` target ensuring placeholder secrets exist, verifying compose syntax, and running network isolation assertions.

---

## 2. Requirement Traceability Matrix

| Requirement | Implementation Artifact | Verification Method |
| :--- | :--- | :--- |
| Section 2.4: 5-Network Isolation Matrix | `docker-compose.yml` (`edge_net`, `app_net`, `data_net`, `sandbox_net`, `egress_llm_net`) | `scripts/check_compose_networks.py` + `test_check_compose_networks.py` |
| Section 2.4: Service Attachment Invariants | `docker-compose.yml` (8 services per Section 2.4) | `scripts/check_compose_networks.py` (exit code 0) |
| Section 2.4: mcp-server database isolation | `docker-compose.yml` (`mcp-server` on `app_net` only, zero db secrets) | `test_negative_mcp_server_joins_data_net` (exit code 1) |
| Section 2.4: Port publishing restricted to edge | `docker-compose.yml` (ports 80, 443 on `reverse-proxy` only) | `test_negative_postgres_publishes_ports` (exit code 1) |
| Section 2.4: Hardening flags across services | `docker-compose.yml` (`cap_drop: [ALL]`, `no-new-privileges:true`) | `test_negative_missing_cap_drop_and_no_new_privileges` (exit code 1) |
| Section 2.4: Zero plaintext secrets | `docker-compose.yml` (`secrets:`, `POSTGRES_PASSWORD_FILE`, `MASTER_KEK_FILE`) | `test_negative_plaintext_secret_environment` (exit code 1) |
| Section 2.3: TLS 1.3 enforcement | `deploy/caddy/Caddyfile` (`protocols tls1.3`) | `test_tls13_enforcement` (exit code 0) |
| Section 2.3: Unbuffered streaming | `deploy/caddy/Caddyfile` (`flush_interval -1` on `/ws`, `/sse*`, `/mcp/*`) | `test_flush_interval_unbuffered_streaming` (exit code 0) |
| Section 2.3: Precompressed static delivery | `deploy/caddy/Caddyfile` (`precompressed br gzip`) | `test_precompressed_static_serving` (exit code 0) |
| Section 5.4: Byte-identical CSP Policy | `deploy/caddy/Caddyfile` (identical to `CSP_POLICY`) | `test_csp_policy_matches_codebase` (exit code 0) |
| Ticket Scope: Secrets directory gitignored | `.gitignore` (`deploy/secrets/`) | `git status` verifies `deploy/secrets/` ignored |
| Ticket Scope: Makefile target `compose-check` | `Makefile` (`compose-check` target added to `.PHONY`) | `make compose-check` exits 0 |

---

## 3. Passive Forensic Proof Artifacts

All verification artifacts are stored under `docs/qa/KANBA-30/`:
1. `docs/qa/KANBA-30/unit-test-results.txt`:
   - Command: `uv run pytest scripts/tests/test_check_compose_networks.py tests/deploy/test_caddyfile.py -q --cov=scripts.check_compose_networks --cov-branch --cov-report=term-missing --cov-fail-under=95`
   - Result: 28 passed in 0.71s, 97.33% total coverage, exit code 0.
2. `docs/qa/KANBA-30/build-check.txt`:
   - Command: `make check`
   - Result: ruff check clean, ruff format check clean, mypy strict clean (71 source files), import contracts 1 kept 0 broken, check_no_dashes clean, exit code 0.
3. `docs/qa/KANBA-30/compose-config.json`:
   - Command: `docker compose -f docker-compose.yml --profile sandbox config --format json`
   - Result: Complete validated JSON configuration representing all 8 services, 5 networks, secrets, and volumes.
4. `docs/qa/KANBA-30/network-assertions.txt`:
   - Command: `uv run python -m scripts.check_compose_networks`
   - Result: `PASS: Docker Compose network isolation and hardening policies verified.`, exit code 0.
5. `docs/qa/KANBA-30/caddy-validate.txt`:
   - Command: `docker run --rm -e KB_DOMAIN=kanban.example.test -v "$PWD/deploy/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.8-alpine@sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`
   - Result: `Valid configuration`, exit code 0.
6. `docs/qa/KANBA-30/git-diff.patch`:
   - Unified git diff showing all changes in this ticket.

---

## 4. Unicode Character Verification

Verified zero Unicode dash characters (`U+2014` em-dash or `U+2013` en-dash) across the entire repository and all proof documents via `uv run python -m scripts.check_no_dashes --all`.
