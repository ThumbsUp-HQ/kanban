CREATE TABLE principals (
    id              UUID PRIMARY KEY DEFAULT uuidv7(),
    principal_type  TEXT NOT NULL CHECK (principal_type IN
                      ('USER','GROUP','AGENT','SCRIPT_EPHEMERAL','SERVICE_PRINCIPAL')),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    status          TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
    display_name    TEXT NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 1 AND 200),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (id, principal_type)
);

CREATE TABLE users (
    id              UUID PRIMARY KEY,
    object_type     object_kind NOT NULL DEFAULT 'user' CHECK (object_type = 'user'),
    principal_type  TEXT NOT NULL DEFAULT 'USER' CHECK (principal_type = 'USER'),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    email           TEXT NOT NULL CHECK (char_length(email) BETWEEN 3 AND 320 AND email ~ '^[^@\s]+@[^@\s]+$'),
    FOREIGN KEY (id, principal_type) REFERENCES principals (id, principal_type) ON DELETE RESTRICT,
    FOREIGN KEY (id, object_type)    REFERENCES objects (id, object_type)       ON DELETE RESTRICT
);

CREATE UNIQUE INDEX users_ws_email_uq ON users (workspace_id, lower(email));

CREATE TABLE groups (
    id              UUID PRIMARY KEY,
    principal_type  TEXT NOT NULL DEFAULT 'GROUP' CHECK (principal_type = 'GROUP'),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    name            TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 200),
    external_source TEXT CHECK (external_source IN ('LDAP','OIDC')),
    external_id     TEXT CHECK (external_id IS NULL OR char_length(external_id) <= 1024),
    UNIQUE (workspace_id, name),
    FOREIGN KEY (id, principal_type) REFERENCES principals (id, principal_type) ON DELETE RESTRICT
);

CREATE TABLE principal_group_edges (
    member_id     UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
    group_id      UUID NOT NULL REFERENCES groups(id)     ON DELETE RESTRICT,
    workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (member_id, group_id),
    CHECK (member_id <> group_id)
);

CREATE INDEX pge_workspace_group_idx ON principal_group_edges (workspace_id, group_id);

CREATE TABLE principal_group_closure (
    member_id          UUID NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
    ancestor_group_id  UUID NOT NULL REFERENCES groups(id)     ON DELETE CASCADE,
    workspace_id       UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    depth              SMALLINT NOT NULL CHECK (depth BETWEEN 1 AND 8),
    PRIMARY KEY (member_id, ancestor_group_id)
);

CREATE INDEX pgc_ancestor_idx ON principal_group_closure (ancestor_group_id, member_id);
CREATE INDEX pgc_workspace_idx ON principal_group_closure (workspace_id);

CREATE FUNCTION users_workspace_match_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_principal_ws uuid;
    v_object_ws uuid;
BEGIN
    SELECT workspace_id INTO v_principal_ws FROM principals WHERE id = NEW.id;
    IF v_principal_ws IS NULL OR NEW.workspace_id <> v_principal_ws THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PRINCIPAL_WORKSPACE_MISMATCH';
    END IF;

    SELECT workspace_id INTO v_object_ws FROM objects WHERE id = NEW.id;
    IF v_object_ws IS NULL OR NEW.workspace_id <> v_object_ws THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PRINCIPAL_WORKSPACE_MISMATCH';
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER users_workspace_match_biu_trg
BEFORE INSERT OR UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION users_workspace_match_biu();

CREATE FUNCTION groups_workspace_match_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_principal_ws uuid;
BEGIN
    SELECT workspace_id INTO v_principal_ws FROM principals WHERE id = NEW.id;
    IF v_principal_ws IS NULL OR NEW.workspace_id <> v_principal_ws THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PRINCIPAL_WORKSPACE_MISMATCH';
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER groups_workspace_match_biu_trg
BEFORE INSERT OR UPDATE ON groups
FOR EACH ROW EXECUTE FUNCTION groups_workspace_match_biu();

CREATE FUNCTION principal_group_edges_guard_biu() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_member_ws uuid;
    v_group_ws uuid;
BEGIN
    SELECT workspace_id INTO v_member_ws FROM principals WHERE id = NEW.member_id;
    SELECT workspace_id INTO v_group_ws FROM groups WHERE id = NEW.group_id;

    IF v_member_ws IS NULL OR v_group_ws IS NULL OR v_member_ws <> NEW.workspace_id OR v_group_ws <> NEW.workspace_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'GROUP_EDGE_WORKSPACE_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1 FROM principal_group_closure
        WHERE member_id = NEW.group_id AND ancestor_group_id = NEW.member_id
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'GROUP_CYCLE_REJECTED';
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER principal_group_edges_guard_biu_trg
BEFORE INSERT OR UPDATE ON principal_group_edges
FOR EACH ROW EXECUTE FUNCTION principal_group_edges_guard_biu();

CREATE FUNCTION rebuild_group_closure(p_workspace_id uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    v_has_cycle boolean;
    v_max_depth int;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('group_closure:' || p_workspace_id::text, 0));

    WITH RECURSIVE walk(member_id, ancestor_group_id, depth) AS (
        SELECT e.member_id, e.group_id, 1
        FROM principal_group_edges e
        WHERE e.workspace_id = p_workspace_id
      UNION ALL
        SELECT e.member_id, w.ancestor_group_id, w.depth + 1
        FROM walk w
        JOIN principal_group_edges e ON e.group_id = w.member_id
        WHERE e.workspace_id = p_workspace_id
          AND w.depth <= 8
    )
    CYCLE member_id SET is_cycle USING path
    SELECT
        coalesce(bool_or(is_cycle), false),
        coalesce(max(depth), 0)
    INTO v_has_cycle, v_max_depth
    FROM walk;

    IF v_has_cycle THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'GROUP_CYCLE_REJECTED';
    END IF;

    IF v_max_depth > 8 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'GROUP_DEPTH_EXCEEDED';
    END IF;

    DELETE FROM principal_group_closure WHERE workspace_id = p_workspace_id;

    WITH RECURSIVE walk(member_id, ancestor_group_id, depth) AS (
        SELECT e.member_id, e.group_id, 1
        FROM principal_group_edges e
        WHERE e.workspace_id = p_workspace_id
      UNION ALL
        SELECT e.member_id, w.ancestor_group_id, w.depth + 1
        FROM walk w
        JOIN principal_group_edges e ON e.group_id = w.member_id
        WHERE e.workspace_id = p_workspace_id
          AND w.depth <= 8
    )
    CYCLE member_id SET is_cycle USING path
    INSERT INTO principal_group_closure (member_id, ancestor_group_id, workspace_id, depth)
    SELECT member_id, ancestor_group_id, p_workspace_id, min(depth)::smallint
    FROM walk
    GROUP BY member_id, ancestor_group_id;
END $$;

CREATE FUNCTION principal_group_edges_closure_aiud() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM rebuild_group_closure(OLD.workspace_id);
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.workspace_id <> NEW.workspace_id THEN
            PERFORM rebuild_group_closure(OLD.workspace_id);
        END IF;
        PERFORM rebuild_group_closure(NEW.workspace_id);
        RETURN NEW;
    ELSE
        PERFORM rebuild_group_closure(NEW.workspace_id);
        RETURN NEW;
    END IF;
END $$;

CREATE TRIGGER principal_group_edges_closure_aiud_trg
AFTER INSERT OR UPDATE OR DELETE ON principal_group_edges
FOR EACH ROW EXECUTE FUNCTION principal_group_edges_closure_aiud();

GRANT EXECUTE ON FUNCTION rebuild_group_closure(uuid) TO kanban_app;
GRANT EXECUTE ON FUNCTION users_workspace_match_biu() TO kanban_app;
GRANT EXECUTE ON FUNCTION groups_workspace_match_biu() TO kanban_app;
GRANT EXECUTE ON FUNCTION principal_group_edges_guard_biu() TO kanban_app;
GRANT EXECUTE ON FUNCTION principal_group_edges_closure_aiud() TO kanban_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE principals, users, groups, principal_group_edges TO kanban_app;
GRANT SELECT ON TABLE principal_group_closure TO kanban_app;
REVOKE INSERT, UPDATE, DELETE ON TABLE principal_group_closure FROM kanban_app;

GRANT SELECT ON TABLE principals, users, groups, principal_group_edges, principal_group_closure TO app_rls_reader;
