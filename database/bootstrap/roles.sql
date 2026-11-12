DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kanban_migrator') THEN
    CREATE ROLE kanban_migrator LOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kanban_app') THEN
    CREATE ROLE kanban_app LOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rls_reader') THEN
    CREATE ROLE app_rls_reader LOGIN; END IF;
END $$;
-- Always re-assert attributes (a pre-existing role must be downgraded, never trusted):
ALTER ROLE kanban_migrator NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS;
ALTER ROLE kanban_app      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE app_rls_reader  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE app_rls_reader  SET default_transaction_read_only = on;
