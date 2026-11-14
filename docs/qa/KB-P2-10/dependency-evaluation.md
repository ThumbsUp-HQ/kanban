# Dependency Evaluation: Zero New Dependencies (KANBA-120 / KB-P2-10)

## Summary of Dependency Evaluation

- **Ticket**: `KANBA-120` (`KB-P2-10`: `[Phase 2 / Auth] Auth card admin API: CRUD, toggle, COLLATE "C" fractional reorder, live test-handshake & public enabled-cards endpoint`)
- **New Runtime Dependencies**: None (`[]`)
- **New Build/Dev Dependencies**: None (`[]`)
- **License Compatibility**: 100% compliant with Apache-2.0. Verified via `scripts/license_gate.py` (`violations=0`).

---

## Architectural Rationale & Threat Modeling

1. **Standard Library & Existing Primitives**:
   - Fractional base-62 ordering implemented in `kanban/util/fractional_rank.py` using native Python string operations and mathematical midpoints (`0-9A-Za-z`). Zero external dependencies required.
   - Pydantic models in `kanban/auth/cards/schemas.py` leverage existing in-tree Pydantic v2 core schemas.
   - Live handshake probes in `kanban/auth/cards/handshake.py` leverage existing in-tree HTTP client (`httpx`), LDAP client (`kanban/auth/ldap`), and cryptography primitives (`argon2-cffi`, `cryptography`).
   - Anti-lockout safeguards in `kanban/auth/cards/lockout.py` and `database/migrations/sql/p2_10_auth_card_admin_ops.up.sql` enforce constraints entirely within PostgreSQL and Python domain logic.

2. **Supply Chain Security**:
   - Zero additions to `pyproject.toml` or `uv.lock`.
   - Zero additions to `kanban/web/package.json` or `pnpm-lock.yaml`.
   - No external network downloads required during build or test execution.
