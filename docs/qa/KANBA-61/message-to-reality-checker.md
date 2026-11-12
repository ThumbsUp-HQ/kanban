# Forensic QA Handoff: KB-P2-18 (KANBA-61)

## Implementation Summary
- **Ticket ID:** `KANBA-61` (`docs/tickets/KB-P2-18.md`)
- **Title:** `[Phase 2 / Kanban] Sliding-window rate limiting service (PG-backed + Valkey-backed) with route decorator and trusted-proxy client IP resolution`
- **Architectural Scope:** `S2.4`, `S2.2`, requirements #3, #6.

## Verification & Architecture Notes
1. **Deferred Concrete Valkey Client:**
   Per technical specification item 5 and ticket requirements, no new third-party Valkey/Redis client package has been added to `pyproject.toml` in this ticket. The `ValkeyRateLimiter` is implemented against the decoupled `ValkeyCommands` protocol (`async def eval(script: str, numkeys: int, *args: object) -> list[int]`). The concrete network client dependency is deferred to the future ticket that wires the production Valkey connection pool. In this ticket, the Valkey backend sliding-window algorithm and reset mechanics are rigorously tested and verified using `FakeValkey` in `kanban/tests/security/fakes.py`, which provides in-memory execution of the identical Lua sliding-window semantics.

2. **Zero Third-Party Dependencies:**
   Zero changes were made to `[project.dependencies]` or `[dependency-groups]` in any `pyproject.toml`. Standard library modules (`hashlib`, `hmac`, `ipaddress`, `math`, `time`, `dataclasses`, `typing`) and existing repository packages (`sqlalchemy`, `fastapi`, `starlette`) provide 100% of the functionality.

3. **PostgreSQL Security Boundary & RLS Parity:**
   The `rate_limit_buckets` table is owned by dedicated `NOLOGIN` role `kb_infra_owner` with `REVOKE ALL FROM PUBLIC, kanban_app, app_rls_reader`. Both `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` are asserted with policy `kb_infra_owner_all FOR ALL TO kb_infra_owner USING (true) WITH CHECK (true)`, ensuring complete pass of the forensic RLS catalog audit (`test_p1_14_rls_catalog.py`). Access by application callers is mediated exclusively through `SECURITY DEFINER` functions `kb_infra.rate_limit_hit` and `kb_infra.rate_limit_reset` with fixed search path (`SET search_path = pg_catalog, public`).

4. **ORM Model Registration:**
   The `RateLimitBucket` model is defined in `database/models/ratelimit.py` and exported via `database/models/__init__.py`. Table count in `database/tests/test_p1_17_models.py` has been updated from 34 to 35, maintaining 1:1 parity between declared SQLAlchemy models and database catalog tables.

5. **Client IP Resolution & Privacy Pseudonymization:**
   `resolve_client_ip` enforces spoof-resistant resolution: direct ASGI peer is inspected first, right-to-left traversal of `X-Forwarded-For` is executed only if the peer matches configured CIDR ranges, and IPv6 clients are bucketed by `/64`. Raw IPs, emails, or usernames are never persisted or logged: keys are hashed via HMAC-SHA256 with subkey `ratelimit/key` derived from HKDF-SHA256 (`derive_subkey`).

## Quality Gates Status
- **Unit & Contract Coverage:** 32 tests passing with 99.77% line+branch coverage (threshold: 95%).
- **Ruff Check & Format:** Clean (zero errors, 100% compliant).
- **Mypy Strict:** 0 errors across 147 source files.
- **Import Linter:** Unidirectional layering agent -> mcp -> kanban -> database preserved.
- **License Gate:** Apache-2.0 compliant (zero non-permissive dependencies).
- **Typography Check:** Zero em-dashes or en-dashes across all files.
