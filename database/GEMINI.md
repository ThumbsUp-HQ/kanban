# Database Module Manifest (`kanban-database`)

## Responsibility
Universal Object Graph implementation for the Kanban platform (Issues, Stickies, Docs, Users, Projects, Cycles, Modules, Views, Pages) storing canonical UTF-8 Markdown only. Enforces PostgreSQL kernel-level Row-Level Security (FORCE RLS, NOBYPASSRLS), composite foreign keys, ltree hierarchical path queries, PL/pgSQL link audit routines, and SHA-256 hash-chained activity records. Testing harness probe schema `kb_harness` is reserved exclusively for test harness self-validation; later RLS catalog tests MUST exclude schema `kb_harness`.

## Depends On
None. This is the foundational leaf module in the workspace dependency hierarchy. Depends on external PostgreSQL 16+ engine with extensions (pgcrypto, ltree, pg_trgm, btree_gist, vector).

## Depended On By
- `kanban` (`kanban-core` web application and REST/WS server).

## Inbound Contracts
- Transactional database connections and async connection pools managed via SQLAlchemy 2.0 and asyncpg.
- Parameterized session configuration via SET LOCAL (app.principal_id, app.workspace_id, app.token_scopes, app.aal_level) bound via RLSContext and bind_rls_context.
- RLSSessionFactory managing fail-closed RLSAsyncSession instances with verify_non_bypass_role startup validation.
- Schema migrations managed via Alembic under dedicated migration role.
- Test harness execution isolates probe entities within kb_harness schema, which must be ignored by production RLS catalog assertions.

## Outbound Contracts
- database.models: 43 typed SQLAlchemy 2.0 DeclarativeBase models matching the Universal Object Graph (spine, principals, projects, issues, knowledge, activity, outbox, embeddings, auth, ratelimit, sessions, agent_definitions, attachments, local_admin_credentials, oidc_auth_requests, comment_reactions), custom LtreeType, and 5 PostgreSQL StrEnums.
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
