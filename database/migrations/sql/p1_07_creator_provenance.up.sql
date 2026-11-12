CREATE OR REPLACE FUNCTION issues_creator_insert_bi()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.original_created_by_id := NEW.created_by_id;
    NEW.creator_modified_by_id := NULL;
    NEW.creator_modified_at := NULL;
    RETURN NEW;
END;
$$;

GRANT EXECUTE ON FUNCTION issues_creator_insert_bi() TO kanban_app;

CREATE TRIGGER issues_creator_insert_bi_trg
BEFORE INSERT ON issues
FOR EACH ROW
EXECUTE FUNCTION issues_creator_insert_bi();

CREATE OR REPLACE FUNCTION issues_creator_provenance_bu()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_actor uuid;
    v_target_ws uuid;
BEGIN
    IF NEW.original_created_by_id IS DISTINCT FROM OLD.original_created_by_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'CREATOR_PROVENANCE_IMMUTABLE';
    END IF;

    IF NEW.created_by_id IS NOT DISTINCT FROM OLD.created_by_id THEN
        IF NEW.creator_modified_by_id IS DISTINCT FROM OLD.creator_modified_by_id
           OR NEW.creator_modified_at IS DISTINCT FROM OLD.creator_modified_at THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'CREATOR_PROVENANCE_IMMUTABLE';
        END IF;
        RETURN NEW;
    END IF;

    v_actor := app_current_principal_id();
    IF v_actor IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'RLS_CONTEXT_REQUIRED';
    END IF;

    IF NOT app_principal_has_role(NEW.project_id, ARRAY['PROJECT_ADMIN','SERVER_ADMIN']) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'CREATOR_OVERRIDE_FORBIDDEN';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM users WHERE id = v_actor) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'CREATOR_OVERRIDE_ACTOR_NOT_USER';
    END IF;

    SELECT workspace_id INTO v_target_ws FROM users WHERE id = NEW.created_by_id;
    IF NOT FOUND OR v_target_ws <> NEW.workspace_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'CREATOR_OVERRIDE_WORKSPACE_MISMATCH';
    END IF;

    NEW.creator_modified_by_id := v_actor;
    NEW.creator_modified_at := clock_timestamp();

    UPDATE objects SET created_by_id = NEW.created_by_id WHERE id = NEW.id;

    PERFORM append_activity(
        NEW.workspace_id,
        NEW.id,
        'issue'::object_kind,
        v_actor,
        'CREATOR_OVERRIDDEN',
        jsonb_build_object(
            'from_user_id', OLD.created_by_id,
            'to_user_id', NEW.created_by_id,
            'original_created_by_id', OLD.original_created_by_id
        )
    );

    RETURN NEW;
END;
$$;

GRANT EXECUTE ON FUNCTION issues_creator_provenance_bu() TO kanban_app;

CREATE TRIGGER issues_creator_provenance_bu_trg
BEFORE UPDATE OF created_by_id, original_created_by_id, creator_modified_by_id, creator_modified_at ON issues
FOR EACH ROW
EXECUTE FUNCTION issues_creator_provenance_bu();
