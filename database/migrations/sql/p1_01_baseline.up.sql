CREATE FUNCTION uuidv7() RETURNS uuid LANGUAGE plpgsql VOLATILE PARALLEL SAFE AS $$
DECLARE
  unix_ms bigint := floor(extract(epoch FROM clock_timestamp()) * 1000);
  b bytea := gen_random_bytes(16);
BEGIN
  b := overlay(b PLACING substring(int8send(unix_ms) FROM 3) FROM 1 FOR 6);
  b := set_byte(b, 6, (get_byte(b, 6) & 15) | 112);   -- version 7
  b := set_byte(b, 8, (get_byte(b, 8) & 63) | 128);   -- RFC 9562 variant 10xx
  RETURN encode(b, 'hex')::uuid;
END $$;

CREATE FUNCTION app_current_principal_id() RETURNS uuid LANGUAGE sql STABLE PARALLEL SAFE AS
  $$ SELECT NULLIF(current_setting('app.principal_id', true), '')::uuid $$;
CREATE FUNCTION app_current_workspace_id() RETURNS uuid LANGUAGE sql STABLE PARALLEL SAFE AS
  $$ SELECT NULLIF(current_setting('app.workspace_id', true), '')::uuid $$;

CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS
  $$ BEGIN NEW.updated_at := clock_timestamp(); RETURN NEW; END $$;

ALTER DEFAULT PRIVILEGES FOR ROLE kanban_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO kanban_app;
ALTER DEFAULT PRIVILEGES FOR ROLE kanban_migrator IN SCHEMA public
  GRANT SELECT ON TABLES TO app_rls_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE kanban_migrator IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
GRANT EXECUTE ON FUNCTION uuidv7(), app_current_principal_id(), app_current_workspace_id() TO kanban_app, app_rls_reader;
