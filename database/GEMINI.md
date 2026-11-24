# Database Module Manifest (`kanban-database`)

## Responsibility
Universal Object Graph implementation for the Kanban platform (Issues, Stickies, Docs, Users, Projects, Cycles, Modules, Views, Pages) storing canonical UTF-8 Markdown only. Enforces PostgreSQL kernel-level Row-Level Security (FORCE RLS, NOBYPASSRLS), composite foreign keys, ltree hierarchical path queries, PL/pgSQL link audit routines, and SHA-256 hash-chained activity records. Testing harness probe schema `kb_harness` is reserved exclusively for test harness self-validation; later RLS catalog tests MUST exclude schema `kb_harness`.

## Depends On
None. This is the foundational leaf module in the workspace dependency hierarchy. Depends on external PostgreSQL 16+ engine with extensions (pgcrypto, ltree, pg_trgm, btree_gist, vector).

## Depended On By
- `kanban` (`kanban-core` web application and REST/WS server).

## Inbound Contracts
- Transactional database connections and async connection pools managed via SQLAlchemy 2.0 and asyncpg.
- Parameterized session configuration via SET LOCAL (app.principal_id, app.workspace_id, app.token_scopes, app.aal_level, app.user_access_hash) bound via RLSContext and bind_rls_context.
- RLSSessionFactory managing fail-closed RLSAsyncSession instances with verify_non_bypass_role startup validation.
- Schema migrations managed via Alembic under dedicated migration role.
- Test harness execution isolates probe entities within kb_harness schema, which must be ignored by production RLS catalog assertions.
- **Protected Pre-Production Database Boundary (`test kanban` / `inferrence1` / `192.168.1.101` / `k.hackedyour.info`):** Never run destructive database tests, schema resets (`dropdb`, `TRUNCATE`, `downgrade`), or unprompted mutations against the live `👍kanban` instance on `inferrence1` / `192.168.1.101` / `k.hackedyour.info`. That deployment is actively used by the user via human interfaces to validate project progression and will transition into production. Only interact with its database when explicitly asked by the user (e.g., diagnosing catastrophic database problems, login issues, or troubleshooting live examples), or via non-destructive application-level validation (creating an isolated test workspace/project/ticket/list/view/cycle/module/doc/sticky). All automated migration and RLS test suites must run strictly against local ephemeral test containers (`make testdb-up` / `SAVEPOINT` fixtures).

## Outbound Contracts
- database.models: 65 typed SQLAlchemy 2.0 DeclarativeBase models matching the Universal Object Graph (spine, principals, projects, issues, knowledge, activity, outbox, embeddings, auth, ratelimit, sessions, agent_definitions, attachments, local_admin_credentials, oidc_auth_requests, comment_reactions, totp_factors, recovery_codes, mcp_api_keys, ldap_group_mappings, notifications, webauthn_credentials, webauthn_challenges, custom_field_definitions, custom_field_values, custom_field_approvals, user_identities, identity_link_intents, setup_claim_tokens, oauth_clients, oauth_grants, oauth_authorization_codes, oauth_refresh_tokens, oauth_revoked_jtis, oauth_device_codes, import_entity_mappings, ai_provider_configs, ai_token_ledgers), custom LtreeType, and 5 PostgreSQL StrEnums.
- database.migrations: Alembic migrations including p6_16_oauth_confidential_clients updating oauth_clients with confidential client secret hash/prefix and check constraints, p5_12_custom_field_approvals with FORCE ROW LEVEL SECURITY and custom_field_manifest_tamper_revoke trigger on custom_field_definitions, p5_05a_ai_providers_and_ledgers with envelope-encrypted ai_provider_configs and atomic ai_token_ledgers, and p4_16_oauth_device_codes.
- database.session: RLSContext, bind_rls_context, RLSSessionFactory, create_rls_engine, and fail-closed security exceptions (RLSContextError, UnboundRLSSessionError, RLSRoleViolationError).
- database.repositories: BaseRepository generic base providing type-safe CRUD operations, bounded pagination (1..500), and mandatory RLS session verification.
- database.outbox: OutboxEnvelope, enqueue_outbox_event, topic_matches, RealtimeBroker, PgNotifyBroker, ValkeyBroker, and OutboxRelay (run via `python -m database.outbox.relay`).
- PL/pgSQL audit triggers detecting and recording broken object links.
- Postgres LISTEN/NOTIFY event streams for real-time state changes.

## Performance Budgets
- Sub-millisecond SAVEPOINT rollback isolation for clean-database unit tests.
- Index-backed single-object read latency < 5ms.
- Complex graph traversal and access-closure resolution < 18ms.
- RLS session context binding overhead < 1ms per transaction.

## Failure Modes
- Foreign key constraint violations on dangling link creation or deletion.
- RLS policy denial returning zero rows on unauthorized access attempts.
- UnboundRLSSessionError raised when queries are executed on sessions without active RLS context binding.
- RLSRoleViolationError raised when connected database role possesses SUPERUSER or BYPASSRLS privileges.
- RLSContextError raised when attempting RLS context binding outside an active transaction.
- Migration lock timeout during schema upgrades under active load.
- Fail-closed behavior on broken object links pending audit purge.

## Zero-Guesswork Schema Change & Migration Standard

### 1. Invariants & Rules
1. **Never hand-roll migration files or down_revision, and never edit already-merged `.up.sql` files:** Always generate new forward migrations at the current single Alembic head via `uv run kanban-ctl db new-migration <rev_id> --message "..."` (or `uv run python -m database.migrations.cli new-migration <rev_id> -m "..."`).
2. **Revision ID Rule:** Must strictly match `^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+$` (`sqlfile.NAME_PATTERN`).
3. **Linear Single-Head Alembic Chain:** Every migration must point its `down_revision` to the single current head returned by `ScriptDirectory.get_heads()`. Branching heads or detached revisions fail the gate.
4. **Paired SQL Files & Zero Historical Mutation:** Every revision must reference valid `.up.sql` and `.down.sql` files in `database/migrations/sql/`. Editing already-applied historical migrations is forbidden; all schema evolution is strictly append-only.

### 2. Copy-Pasteable SQL Templates

#### Template 1: Tenant-Scoped Table
Enforces kernel-level `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`, tenant isolation via `workspace_id = app_current_workspace_id()`, and explicit table grants for `kanban_app` and `app_rls_reader`:

```sql
CREATE TABLE IF NOT EXISTS {table} (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_{table}_workspace_id ON {table} (workspace_id);

ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

CREATE POLICY {table}_select_rls ON {table}
    FOR SELECT USING (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY {table}_insert_rls ON {table}
    FOR INSERT WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY {table}_update_rls ON {table}
    FOR UPDATE USING (
        workspace_id = app_current_workspace_id()
    ) WITH CHECK (
        workspace_id = app_current_workspace_id()
    );

CREATE POLICY {table}_delete_rls ON {table}
    FOR DELETE USING (
        workspace_id = app_current_workspace_id()
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO kanban_app;
GRANT SELECT ON TABLE {table} TO app_rls_reader;
```

#### Template 2: Isolated Table (`kb_auth_owner` / `kb_infra_owner`)
For credentials, sessions, and MFA factors. Completely revokes direct table access from `kanban_app` and `app_rls_reader`. Access is permitted exclusively via `SECURITY DEFINER` RPC routines owned by `kb_auth_owner`:

```sql
CREATE TABLE IF NOT EXISTS {table} (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    secret_payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE {table} OWNER TO kb_auth_owner;
REVOKE ALL ON {table} FROM PUBLIC, kanban_app, app_rls_reader;

ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

CREATE POLICY {table}_owner_all ON {table}
    FOR ALL TO kb_auth_owner USING (true) WITH CHECK (true);
```

#### Template 3: `SECURITY DEFINER` Function
Created in schema `kb_auth.*` or `kb_infra.*`, owned by `kb_auth_owner` (or `kb_infra_owner`), with hardened search path, revoked `PUBLIC` execute, and explicit execute grant to `kanban_app`:

```sql
CREATE OR REPLACE FUNCTION kb_auth.{func_name}(
    p_workspace_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF p_workspace_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'NULL_ARGUMENT';
    END IF;

    RETURN TRUE;
END;
$$;

ALTER FUNCTION kb_auth.{func_name}(UUID) OWNER TO kb_auth_owner;
REVOKE ALL ON FUNCTION kb_auth.{func_name}(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION kb_auth.{func_name}(UUID) TO kanban_app;
```

### 3. Five-Step Verification Checklist
1. **Scaffold:** Run `uv run kanban-ctl db new-migration <rev_id> --message "<message>" [--table <table>] [--template tenant|isolated|func]`
2. **Write SQL:** Edit `database/migrations/sql/<rev_id>.up.sql` and `database/migrations/sql/<rev_id>.down.sql`
3. **Synchronize ORM:** Update or add models in `database/models/*.py` and re-export in `database/models/__init__.py`
4. **Lifecycle Test:** Customize `database/tests/migrations/test_<rev_id>_migration.py` and run `uv run pytest database/tests/migrations/test_<rev_id>_migration.py`
5. **Static & Catalog Consistency Check:** Run `uv run kanban-ctl db check-migrations --static-only` and `uv run pytest database/tests/test_p1_17_models.py database/tests/test_p1_14_rls_catalog.py`
