CREATE TYPE link_kind AS ENUM (
    'BLOCKS', 'BLOCKED_BY', 'RELATES_TO', 'DUPLICATES', 'PARENT_OF',
    'ASSIGNED_TO', 'IN_CYCLE', 'IN_MODULE', 'PROMOTED_TO_DOC',
    'VERIFIED_BY_DOC', 'DERIVED_FROM_STICKY', 'EMBEDS_OBJECT', 'GOVERNED_BY_VIEW'
);

CREATE TABLE object_links (
    id                  UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id        UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    source_id           UUID NOT NULL,
    source_type         object_kind NOT NULL,
    target_id           UUID NOT NULL,
    target_type         object_kind NOT NULL,
    link_type           link_kind NOT NULL,
    link_state          TEXT NOT NULL DEFAULT 'ACTIVE'
                        CHECK (link_state IN ('ACTIVE', 'FLAGGED_INVALID')),
    source_key_snapshot TEXT NOT NULL,
    target_key_snapshot TEXT NOT NULL,
    created_by_id       UUID NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (source_id <> target_id),
    UNIQUE (source_id, target_id, link_type),
    FOREIGN KEY (source_id, source_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT,
    FOREIGN KEY (target_id, target_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT
);

CREATE INDEX object_links_source_idx ON object_links (source_id, link_state);
CREATE INDEX object_links_target_idx ON object_links (target_id, link_state);
CREATE INDEX object_links_ws_state_idx ON object_links (workspace_id, link_state);

CREATE TABLE link_type_matrix (
    source_type       object_kind NOT NULL,
    link_type         link_kind   NOT NULL,
    target_type       object_kind NOT NULL,
    is_user_creatable BOOLEAN     NOT NULL DEFAULT FALSE,
    PRIMARY KEY (source_type, link_type, target_type)
);

REVOKE INSERT, UPDATE, DELETE ON link_type_matrix FROM kanban_app;

-- Seed user-creatable link kinds (is_user_creatable = TRUE)
-- 1. ('issue', k, 'issue') for k IN ('BLOCKS', 'BLOCKED_BY', 'DUPLICATES')
INSERT INTO link_type_matrix (source_type, link_type, target_type, is_user_creatable) VALUES
('issue', 'BLOCKS', 'issue', TRUE),
('issue', 'BLOCKED_BY', 'issue', TRUE),
('issue', 'DUPLICATES', 'issue', TRUE);

-- 2. (s, 'RELATES_TO', t) for all pairs s, t IN ('issue', 'sticky', 'doc', 'page', 'cycle', 'module', 'view')
INSERT INTO link_type_matrix (source_type, link_type, target_type, is_user_creatable)
SELECT s.t::object_kind, 'RELATES_TO'::link_kind, t.t::object_kind, TRUE
FROM (VALUES ('issue'), ('sticky'), ('doc'), ('page'), ('cycle'), ('module'), ('view')) AS s(t)
CROSS JOIN (VALUES ('issue'), ('sticky'), ('doc'), ('page'), ('cycle'), ('module'), ('view')) AS t(t);

-- 3. ('issue', 'VERIFIED_BY_DOC', t) for t IN ('doc', 'page')
INSERT INTO link_type_matrix (source_type, link_type, target_type, is_user_creatable) VALUES
('issue', 'VERIFIED_BY_DOC', 'doc', TRUE),
('issue', 'VERIFIED_BY_DOC', 'page', TRUE);

-- 4. (s, 'DERIVED_FROM_STICKY', 'sticky') for s IN ('issue', 'doc', 'page')
INSERT INTO link_type_matrix (source_type, link_type, target_type, is_user_creatable) VALUES
('issue', 'DERIVED_FROM_STICKY', 'sticky', TRUE),
('doc', 'DERIVED_FROM_STICKY', 'sticky', TRUE),
('page', 'DERIVED_FROM_STICKY', 'sticky', TRUE);

-- Seed system-managed link kinds (is_user_creatable = FALSE)
-- 5. ('sticky', 'PROMOTED_TO_DOC', 'doc')
INSERT INTO link_type_matrix (source_type, link_type, target_type, is_user_creatable) VALUES
('sticky', 'PROMOTED_TO_DOC', 'doc', FALSE),
('issue', 'PARENT_OF', 'issue', FALSE),
('doc', 'PARENT_OF', 'page', FALSE),
('page', 'PARENT_OF', 'page', FALSE),
('issue', 'ASSIGNED_TO', 'user', FALSE),
('issue', 'IN_CYCLE', 'cycle', FALSE),
('issue', 'IN_MODULE', 'module', FALSE);

-- 6. (s, 'EMBEDS_OBJECT', t) for s IN ('issue', 'sticky', 'doc', 'page') and t IN ('issue', 'sticky', 'doc', 'page', 'view', 'cycle', 'module')
INSERT INTO link_type_matrix (source_type, link_type, target_type, is_user_creatable)
SELECT s.t::object_kind, 'EMBEDS_OBJECT'::link_kind, t.t::object_kind, FALSE
FROM (VALUES ('issue'), ('sticky'), ('doc'), ('page')) AS s(t)
CROSS JOIN (VALUES ('issue'), ('sticky'), ('doc'), ('page'), ('view'), ('cycle'), ('module')) AS t(t);

-- 7. (s, 'GOVERNED_BY_VIEW', 'view') for s IN ('project', 'issue', 'cycle', 'module')
INSERT INTO link_type_matrix (source_type, link_type, target_type, is_user_creatable) VALUES
('project', 'GOVERNED_BY_VIEW', 'view', FALSE),
('issue', 'GOVERNED_BY_VIEW', 'view', FALSE),
('cycle', 'GOVERNED_BY_VIEW', 'view', FALSE),
('module', 'GOVERNED_BY_VIEW', 'view', FALSE);

-- Triggers for object_links
CREATE FUNCTION object_links_validate_bi() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_src_ws   uuid;
    v_src_key  text;
    v_tgt_ws   uuid;
    v_tgt_key  text;
BEGIN
    -- 1. Check link_type_matrix allowlist
    IF NOT EXISTS (
        SELECT 1 FROM link_type_matrix
        WHERE source_type = NEW.source_type
          AND link_type = NEW.link_type
          AND target_type = NEW.target_type
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_TYPE_NOT_ALLOWED';
    END IF;

    -- 2. Fetch source object
    SELECT workspace_id, canonical_key
    INTO v_src_ws, v_src_key
    FROM objects
    WHERE id = NEW.source_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_ENDPOINT_NOT_FOUND';
    END IF;

    -- Fetch target object
    SELECT workspace_id, canonical_key
    INTO v_tgt_ws, v_tgt_key
    FROM objects
    WHERE id = NEW.target_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_ENDPOINT_NOT_FOUND';
    END IF;

    -- Assert both endpoints belong to NEW.workspace_id
    IF v_src_ws <> NEW.workspace_id OR v_tgt_ws <> NEW.workspace_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_CROSS_WORKSPACE_FORBIDDEN';
    END IF;

    -- 3. Force authoritative snapshots and active state
    NEW.source_key_snapshot := v_src_key;
    NEW.target_key_snapshot := v_tgt_key;
    NEW.link_state := 'ACTIVE';

    RETURN NEW;
END $$;

CREATE TRIGGER object_links_validate_bi_trg
BEFORE INSERT ON object_links
FOR EACH ROW EXECUTE FUNCTION object_links_validate_bi();

CREATE FUNCTION object_links_guard_bu() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id
       OR NEW.source_id IS DISTINCT FROM OLD.source_id
       OR NEW.source_type IS DISTINCT FROM OLD.source_type
       OR NEW.target_id IS DISTINCT FROM OLD.target_id
       OR NEW.target_type IS DISTINCT FROM OLD.target_type
       OR NEW.link_type IS DISTINCT FROM OLD.link_type
       OR NEW.source_key_snapshot IS DISTINCT FROM OLD.source_key_snapshot
       OR NEW.target_key_snapshot IS DISTINCT FROM OLD.target_key_snapshot
       OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'OBJECT_LINK_IMMUTABLE';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER object_links_guard_bu_trg
BEFORE UPDATE ON object_links
FOR EACH ROW EXECUTE FUNCTION object_links_guard_bu();
