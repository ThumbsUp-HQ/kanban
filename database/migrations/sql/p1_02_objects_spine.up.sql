CREATE TABLE workspaces (
    id                    UUID PRIMARY KEY DEFAULT uuidv7(),
    slug                  TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
    name                  TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
    trash_retention_days  INTEGER NOT NULL DEFAULT 30 CHECK (trash_retention_days BETWEEN 1 AND 3650),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TYPE object_kind AS ENUM (
    'issue', 'sticky', 'doc', 'user', 'project', 'cycle', 'module', 'view', 'page'
);

CREATE TABLE objects (
    id              UUID PRIMARY KEY DEFAULT uuidv7(),
    object_type     object_kind NOT NULL,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id      UUID,
    canonical_key   TEXT NOT NULL CHECK (char_length(canonical_key) BETWEEN 1 AND 200),
    display_title   TEXT NOT NULL CHECK (char_length(display_title) BETWEEN 1 AND 500),
    created_by_id   UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    archived_at     TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    UNIQUE (id, object_type),
    UNIQUE (workspace_id, object_type, canonical_key)
);

CREATE INDEX objects_project_idx ON objects (project_id) WHERE project_id IS NOT NULL;
CREATE INDEX objects_ws_type_live_idx ON objects (workspace_id, object_type) WHERE deleted_at IS NULL;

CREATE TRIGGER objects_set_updated_at BEFORE UPDATE ON objects FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER workspaces_set_updated_at BEFORE UPDATE ON workspaces FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE FUNCTION objects_guard_bu() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.object_type IS DISTINCT FROM OLD.object_type THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'OBJECT_TYPE_IMMUTABLE';
  END IF;
  IF NEW.id IS DISTINCT FROM OLD.id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'OBJECT_ID_IMMUTABLE';
  END IF;
  IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'OBJECT_CREATED_AT_IMMUTABLE';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER objects_guard_bu_trg BEFORE UPDATE ON objects FOR EACH ROW EXECUTE FUNCTION objects_guard_bu();

CREATE FUNCTION register_object(
    p_object_type object_kind,
    p_workspace_id uuid,
    p_project_id uuid,
    p_canonical_key text,
    p_display_title text,
    p_created_by_id uuid,
    p_id uuid DEFAULT NULL
) RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY INVOKER AS $$
DECLARE
    v_id uuid;
BEGIN
    IF p_workspace_id IS NULL OR p_canonical_key IS NULL OR p_display_title IS NULL OR p_created_by_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'REGISTER_OBJECT_NULL_ARGUMENT';
    END IF;

    IF p_object_type IN ('project', 'user') AND p_project_id IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'REGISTER_OBJECT_PROJECT_NOT_ALLOWED';
    END IF;

    v_id := COALESCE(p_id, uuidv7());

    INSERT INTO objects (
        id, object_type, workspace_id, project_id, canonical_key, display_title, created_by_id
    ) VALUES (
        v_id, p_object_type, p_workspace_id, p_project_id, p_canonical_key, p_display_title, p_created_by_id
    );

    RETURN v_id;
END $$;

GRANT EXECUTE ON FUNCTION register_object(object_kind, uuid, uuid, text, text, uuid, uuid) TO kanban_app;
