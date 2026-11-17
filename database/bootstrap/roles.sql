DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kanban_migrator') THEN
    CREATE ROLE kanban_migrator LOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kanban_app') THEN
    CREATE ROLE kanban_app LOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rls_reader') THEN
    CREATE ROLE app_rls_reader LOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kb_infra_owner') THEN
    CREATE ROLE kb_infra_owner NOLOGIN NOINHERIT NOBYPASSRLS; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kb_auth_owner') THEN
    CREATE ROLE kb_auth_owner NOLOGIN NOINHERIT NOBYPASSRLS; END IF;
END $$;
-- Always re-assert attributes (a pre-existing role must be downgraded, never trusted):
ALTER ROLE kanban_migrator NOSUPERUSER NOCREATEDB CREATEROLE NOREPLICATION BYPASSRLS;
ALTER ROLE kanban_app      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE app_rls_reader  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE app_rls_reader  SET default_transaction_read_only = on;
ALTER ROLE kb_infra_owner  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE kb_auth_owner   NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT kb_infra_owner TO kanban_migrator;
GRANT kb_auth_owner TO kanban_migrator WITH SET TRUE, INHERIT TRUE;
GRANT USAGE, CREATE ON SCHEMA public TO kb_infra_owner;

DO $$
BEGIN
    EXECUTE format('GRANT CREATE, TEMPORARY ON DATABASE %I TO kanban_migrator', current_database());
END
$$;
