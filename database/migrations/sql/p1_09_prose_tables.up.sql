-- Migration: p1_09_prose_tables (up)
-- Tables: issue_comments, docs, pages, page_versions, stickies (Markdown-only + STORED sha256)

-- 1. Table: issue_comments
CREATE TABLE issue_comments (
    id                 UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id       UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    issue_id           UUID NOT NULL REFERENCES issues(id) ON DELETE RESTRICT,
    parent_comment_id  UUID REFERENCES issue_comments(id) ON DELETE RESTRICT,
    author_id          UUID NOT NULL REFERENCES principals(id) ON DELETE RESTRICT,
    body_markdown      TEXT NOT NULL CHECK (octet_length(body_markdown) BETWEEN 1 AND 262144),
    body_sha256        BYTEA GENERATED ALWAYS AS (digest(body_markdown, 'sha256')) STORED,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    edited_at          TIMESTAMPTZ,
    deleted_at         TIMESTAMPTZ
);

CREATE INDEX issue_comments_issue_idx ON issue_comments (issue_id);
CREATE INDEX issue_comments_parent_idx ON issue_comments (parent_comment_id) WHERE parent_comment_id IS NOT NULL;
CREATE INDEX issue_comments_author_idx ON issue_comments (author_id);
CREATE INDEX issue_comments_workspace_idx ON issue_comments (workspace_id);

-- 2. Table: docs
CREATE TABLE docs (
    id               UUID PRIMARY KEY,
    object_type      object_kind NOT NULL DEFAULT 'doc' CHECK (object_type = 'doc'),
    workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id       UUID REFERENCES projects(id) ON DELETE RESTRICT,
    title            TEXT NOT NULL CHECK (char_length(btrim(title)) BETWEEN 1 AND 500),
    body_markdown    TEXT NOT NULL DEFAULT '' CHECK (octet_length(body_markdown) <= 1048576),
    body_sha256      BYTEA GENERATED ALWAYS AS (digest(body_markdown, 'sha256')) STORED,
    hierarchy_path   ltree NOT NULL,
    version_seq      INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (id, object_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT
);

CREATE INDEX docs_workspace_idx ON docs (workspace_id);
CREATE INDEX docs_project_idx ON docs (project_id) WHERE project_id IS NOT NULL;
CREATE INDEX docs_hierarchy_gist ON docs USING gist (hierarchy_path);

-- 3. Table: pages
CREATE TABLE pages (
    id               UUID PRIMARY KEY,
    object_type      object_kind NOT NULL DEFAULT 'page' CHECK (object_type = 'page'),
    workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    doc_id           UUID NOT NULL REFERENCES docs(id) ON DELETE RESTRICT,
    parent_page_id   UUID REFERENCES pages(id) ON DELETE RESTRICT,
    title            TEXT NOT NULL CHECK (char_length(btrim(title)) BETWEEN 1 AND 500),
    body_markdown    TEXT NOT NULL DEFAULT '' CHECK (octet_length(body_markdown) <= 1048576),
    body_sha256      BYTEA GENERATED ALWAYS AS (digest(body_markdown, 'sha256')) STORED,
    hierarchy_path   ltree NOT NULL CHECK (nlevel(hierarchy_path) BETWEEN 2 AND 11),
    version_seq      INTEGER NOT NULL DEFAULT 1,
    sort_rank        TEXT COLLATE "C" NOT NULL DEFAULT 'a0',
    FOREIGN KEY (id, object_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT
);

CREATE INDEX pages_hierarchy_gist ON pages USING gist (hierarchy_path);
CREATE INDEX pages_doc_idx ON pages (doc_id);
CREATE INDEX pages_parent_idx ON pages (parent_page_id) WHERE parent_page_id IS NOT NULL;
CREATE INDEX pages_workspace_idx ON pages (workspace_id);

-- 4. Table: page_versions
CREATE TABLE page_versions (
    page_id        UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    version_seq    INTEGER NOT NULL,
    workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    title          TEXT NOT NULL,
    body_markdown  TEXT NOT NULL CHECK (octet_length(body_markdown) <= 1048576),
    body_sha256    BYTEA GENERATED ALWAYS AS (digest(body_markdown, 'sha256')) STORED,
    created_by_id  UUID REFERENCES principals(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (page_id, version_seq)
);

CREATE INDEX page_versions_workspace_idx ON page_versions (workspace_id);

-- 5. Table: stickies
CREATE TABLE stickies (
    id                          UUID PRIMARY KEY,
    object_type                 object_kind NOT NULL DEFAULT 'sticky' CHECK (object_type = 'sticky'),
    workspace_id                UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    project_id                  UUID REFERENCES projects(id) ON DELETE RESTRICT,
    body_markdown               TEXT NOT NULL DEFAULT '' CHECK (octet_length(body_markdown) <= 65536),
    body_sha256                 BYTEA GENERATED ALWAYS AS (digest(body_markdown, 'sha256')) STORED,
    color_token                 TEXT NOT NULL DEFAULT 'amber'
                                CHECK (color_token IN ('amber', 'mint', 'sky', 'lavender', 'coral', 'slate')),
    promotion_recommended       BOOLEAN NOT NULL DEFAULT FALSE,
    promotion_snoozed_at_length INTEGER CHECK (promotion_snoozed_at_length IS NULL OR promotion_snoozed_at_length >= 0),
    promoted_to_doc_id          UUID REFERENCES docs(id) ON DELETE SET NULL,
    sort_rank                   TEXT COLLATE "C" NOT NULL DEFAULT 'a0',
    FOREIGN KEY (id, object_type) REFERENCES objects (id, object_type) ON DELETE RESTRICT
);

CREATE INDEX stickies_workspace_idx ON stickies (workspace_id);
CREATE INDEX stickies_project_idx ON stickies (project_id) WHERE project_id IS NOT NULL;
CREATE INDEX stickies_promoted_doc_idx ON stickies (promoted_to_doc_id) WHERE promoted_to_doc_id IS NOT NULL;

-- 6. Trigger Functions & Triggers

-- 6.1 issue_comments_workspace_biu
CREATE OR REPLACE FUNCTION issue_comments_workspace_biu() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_issue_ws uuid;
    v_parent_issue_id uuid;
BEGIN
    SELECT workspace_id INTO v_issue_ws FROM issues WHERE id = NEW.issue_id;
    IF v_issue_ws IS NULL THEN
        RAISE EXCEPTION 'ISSUE_NOT_FOUND' USING ERRCODE = 'P0001';
    END IF;

    NEW.workspace_id := v_issue_ws;

    IF NEW.parent_comment_id IS NOT NULL THEN
        SELECT issue_id INTO v_parent_issue_id FROM issue_comments WHERE id = NEW.parent_comment_id;
        IF v_parent_issue_id IS NULL OR v_parent_issue_id <> NEW.issue_id THEN
            RAISE EXCEPTION 'COMMENT_PARENT_MISMATCH' USING ERRCODE = 'P0001';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER issue_comments_workspace_biu_trg
BEFORE INSERT OR UPDATE ON issue_comments
FOR EACH ROW EXECUTE FUNCTION issue_comments_workspace_biu();

-- 6.2 docs_spine_match_biu
CREATE OR REPLACE FUNCTION docs_spine_match_biu() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_obj_ws uuid;
    v_obj_proj uuid;
BEGIN
    SELECT workspace_id, project_id INTO v_obj_ws, v_obj_proj
    FROM objects WHERE id = NEW.id AND object_type = NEW.object_type;

    IF v_obj_ws IS NULL THEN
        RAISE EXCEPTION 'OBJECT_NOT_FOUND' USING ERRCODE = 'P0001';
    END IF;

    IF v_obj_ws <> NEW.workspace_id OR (v_obj_proj IS DISTINCT FROM NEW.project_id) THEN
        RAISE EXCEPTION 'PROSE_SPINE_MISMATCH' USING ERRCODE = 'P0001';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER docs_spine_match_biu_trg
BEFORE INSERT OR UPDATE ON docs
FOR EACH ROW EXECUTE FUNCTION docs_spine_match_biu();

-- 6.3 pages_spine_match_biu
CREATE OR REPLACE FUNCTION pages_spine_match_biu() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_obj_ws uuid;
    v_obj_proj uuid;
    v_doc_proj uuid;
BEGIN
    SELECT workspace_id, project_id INTO v_obj_ws, v_obj_proj
    FROM objects WHERE id = NEW.id AND object_type = NEW.object_type;

    IF v_obj_ws IS NULL THEN
        RAISE EXCEPTION 'OBJECT_NOT_FOUND' USING ERRCODE = 'P0001';
    END IF;

    IF v_obj_ws <> NEW.workspace_id THEN
        RAISE EXCEPTION 'PROSE_SPINE_MISMATCH' USING ERRCODE = 'P0001';
    END IF;

    SELECT project_id INTO v_doc_proj FROM docs WHERE id = NEW.doc_id;
    IF v_obj_proj IS DISTINCT FROM v_doc_proj THEN
        RAISE EXCEPTION 'PROSE_SPINE_MISMATCH' USING ERRCODE = 'P0001';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER pages_spine_match_biu_trg
BEFORE INSERT OR UPDATE ON pages
FOR EACH ROW EXECUTE FUNCTION pages_spine_match_biu();

-- 6.4 stickies_spine_match_biu
CREATE OR REPLACE FUNCTION stickies_spine_match_biu() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_obj_ws uuid;
    v_obj_proj uuid;
BEGIN
    SELECT workspace_id, project_id INTO v_obj_ws, v_obj_proj
    FROM objects WHERE id = NEW.id AND object_type = NEW.object_type;

    IF v_obj_ws IS NULL THEN
        RAISE EXCEPTION 'OBJECT_NOT_FOUND' USING ERRCODE = 'P0001';
    END IF;

    IF v_obj_ws <> NEW.workspace_id OR (v_obj_proj IS DISTINCT FROM NEW.project_id) THEN
        RAISE EXCEPTION 'PROSE_SPINE_MISMATCH' USING ERRCODE = 'P0001';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER stickies_spine_match_biu_trg
BEFORE INSERT OR UPDATE ON stickies
FOR EACH ROW EXECUTE FUNCTION stickies_spine_match_biu();

-- 6.5 docs_hierarchy_bi
CREATE OR REPLACE FUNCTION docs_hierarchy_bi() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.hierarchy_path := text2ltree('d' || replace(NEW.id::text, '-', ''));
    RETURN NEW;
END;
$$;

CREATE TRIGGER docs_hierarchy_bi_trg
BEFORE INSERT ON docs
FOR EACH ROW EXECUTE FUNCTION docs_hierarchy_bi();

-- 6.6 pages_hierarchy_biu
CREATE OR REPLACE FUNCTION pages_hierarchy_biu() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_doc_path ltree;
    v_doc_ws uuid;
    v_parent_doc uuid;
    v_parent_ws uuid;
    v_parent_path ltree;
    v_subtree_height integer := 0;
    v_new_depth integer;
    v_page_label text;
BEGIN
    IF NEW.parent_page_id = NEW.id THEN
        RAISE EXCEPTION 'PAGE_CYCLE' USING ERRCODE = 'P0001';
    END IF;

    v_page_label := 'p' || replace(NEW.id::text, '-', '');

    IF NEW.parent_page_id IS NULL THEN
        SELECT hierarchy_path, workspace_id INTO v_doc_path, v_doc_ws FROM docs WHERE id = NEW.doc_id;
        IF v_doc_path IS NULL THEN
            RAISE EXCEPTION 'DOC_NOT_FOUND' USING ERRCODE = 'P0001';
        END IF;

        IF v_doc_ws <> NEW.workspace_id THEN
            RAISE EXCEPTION 'PAGE_PARENT_DOC_MISMATCH' USING ERRCODE = 'P0001';
        END IF;

        IF TG_OP = 'UPDATE' THEN
            SELECT COALESCE(max(nlevel(d.hierarchy_path)) - nlevel(OLD.hierarchy_path), 0)
            INTO v_subtree_height
            FROM pages d
            WHERE d.hierarchy_path <@ OLD.hierarchy_path;

            IF 1 + v_subtree_height > 10 THEN
                RAISE EXCEPTION 'PAGE_MAX_DEPTH_EXCEEDED' USING ERRCODE = 'P0001';
            END IF;
        END IF;

        NEW.hierarchy_path := v_doc_path || text2ltree(v_page_label);
    ELSE
        SELECT doc_id, workspace_id, hierarchy_path INTO v_parent_doc, v_parent_ws, v_parent_path
        FROM pages WHERE id = NEW.parent_page_id;

        IF v_parent_doc IS NULL THEN
            RAISE EXCEPTION 'PARENT_PAGE_NOT_FOUND' USING ERRCODE = 'P0001';
        END IF;

        IF v_parent_doc <> NEW.doc_id OR v_parent_ws <> NEW.workspace_id THEN
            RAISE EXCEPTION 'PAGE_PARENT_DOC_MISMATCH' USING ERRCODE = 'P0001';
        END IF;

        PERFORM 1 FROM pages
        WHERE hierarchy_path @> v_parent_path
        ORDER BY nlevel(hierarchy_path) FOR UPDATE;

        IF v_parent_path ~ ('*.' || v_page_label || '.*')::lquery THEN
            RAISE EXCEPTION 'PAGE_CYCLE' USING ERRCODE = 'P0001';
        END IF;

        IF TG_OP = 'UPDATE' THEN
            SELECT COALESCE(max(nlevel(d.hierarchy_path)) - nlevel(OLD.hierarchy_path), 0)
            INTO v_subtree_height
            FROM pages d
            WHERE d.hierarchy_path <@ OLD.hierarchy_path;
        END IF;

        v_new_depth := (nlevel(v_parent_path) - 1) + 1 + v_subtree_height;
        IF v_new_depth > 10 THEN
            RAISE EXCEPTION 'PAGE_MAX_DEPTH_EXCEEDED' USING ERRCODE = 'P0001';
        END IF;

        NEW.hierarchy_path := v_parent_path || text2ltree(v_page_label);
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER pages_hierarchy_biu_trg
BEFORE INSERT OR UPDATE OF parent_page_id, doc_id ON pages
FOR EACH ROW EXECUTE FUNCTION pages_hierarchy_biu();

-- 6.7 pages_hierarchy_au
CREATE OR REPLACE FUNCTION pages_hierarchy_au() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE pages
    SET hierarchy_path = NEW.hierarchy_path || subpath(hierarchy_path, nlevel(OLD.hierarchy_path))
    WHERE hierarchy_path <@ OLD.hierarchy_path AND id <> NEW.id;

    RETURN NEW;
END;
$$;

CREATE TRIGGER pages_hierarchy_au_trg
AFTER UPDATE OF parent_page_id, doc_id ON pages
FOR EACH ROW
WHEN (OLD.hierarchy_path IS DISTINCT FROM NEW.hierarchy_path)
EXECUTE FUNCTION pages_hierarchy_au();

-- 6.8 pages_versioning_bu
CREATE OR REPLACE FUNCTION pages_versioning_bu() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_actor uuid;
BEGIN
    IF NEW.version_seq IS DISTINCT FROM OLD.version_seq THEN
        RAISE EXCEPTION 'VERSION_SEQ_MANAGED' USING ERRCODE = 'P0001';
    END IF;

    IF NEW.title IS DISTINCT FROM OLD.title OR NEW.body_markdown IS DISTINCT FROM OLD.body_markdown THEN
        v_actor := app_current_principal_id();
        INSERT INTO page_versions (
            page_id, version_seq, workspace_id, title, body_markdown, created_by_id
        ) VALUES (
            OLD.id, OLD.version_seq, OLD.workspace_id, OLD.title, OLD.body_markdown, v_actor
        );
        NEW.version_seq := OLD.version_seq + 1;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER pages_versioning_bu_trg
BEFORE UPDATE ON pages
FOR EACH ROW EXECUTE FUNCTION pages_versioning_bu();

-- 6.9 docs_versioning_bu
CREATE OR REPLACE FUNCTION docs_versioning_bu() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.version_seq IS DISTINCT FROM OLD.version_seq THEN
        RAISE EXCEPTION 'VERSION_SEQ_MANAGED' USING ERRCODE = 'P0001';
    END IF;

    IF NEW.title IS DISTINCT FROM OLD.title OR NEW.body_markdown IS DISTINCT FROM OLD.body_markdown THEN
        NEW.version_seq := OLD.version_seq + 1;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER docs_versioning_bu_trg
BEFORE UPDATE ON docs
FOR EACH ROW EXECUTE FUNCTION docs_versioning_bu();

-- 6.10 page_versions_immutable_bud
CREATE OR REPLACE FUNCTION page_versions_immutable_bud() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'PAGE_VERSION_IMMUTABLE' USING ERRCODE = 'P0001';
END;
$$;

CREATE TRIGGER page_versions_immutable_bud_trg
BEFORE UPDATE OR DELETE ON page_versions
FOR EACH ROW EXECUTE FUNCTION page_versions_immutable_bud();

-- 6.11 stickies_promotion_guard_bu
CREATE OR REPLACE FUNCTION stickies_promotion_guard_bu() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_doc_ws uuid;
BEGIN
    IF NEW.promoted_to_doc_id IS DISTINCT FROM OLD.promoted_to_doc_id THEN
        IF OLD.promoted_to_doc_id IS NOT NULL THEN
            RAISE EXCEPTION 'STICKY_PROMOTION_INVALID' USING ERRCODE = 'P0001';
        END IF;

        IF NEW.promoted_to_doc_id IS NOT NULL THEN
            SELECT workspace_id INTO v_doc_ws FROM docs WHERE id = NEW.promoted_to_doc_id;
            IF v_doc_ws IS NULL OR v_doc_ws <> NEW.workspace_id THEN
                RAISE EXCEPTION 'STICKY_PROMOTION_INVALID' USING ERRCODE = 'P0001';
            END IF;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER stickies_promotion_guard_bu_trg
BEFORE UPDATE ON stickies
FOR EACH ROW EXECUTE FUNCTION stickies_promotion_guard_bu();

-- 7. Permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE issue_comments TO kanban_app;
GRANT SELECT ON TABLE issue_comments TO app_rls_reader;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE docs TO kanban_app;
GRANT SELECT ON TABLE docs TO app_rls_reader;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE pages TO kanban_app;
GRANT SELECT ON TABLE pages TO app_rls_reader;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE page_versions TO kanban_app;
GRANT SELECT ON TABLE page_versions TO app_rls_reader;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE stickies TO kanban_app;
GRANT SELECT ON TABLE stickies TO app_rls_reader;

GRANT EXECUTE ON FUNCTION issue_comments_workspace_biu() TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION docs_spine_match_biu() TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION pages_spine_match_biu() TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION stickies_spine_match_biu() TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION docs_hierarchy_bi() TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION pages_hierarchy_biu() TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION pages_hierarchy_au() TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION pages_versioning_bu() TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION docs_versioning_bu() TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION page_versions_immutable_bud() TO kanban_app, kanban_migrator;
GRANT EXECUTE ON FUNCTION stickies_promotion_guard_bu() TO kanban_app, kanban_migrator;
