-- Migration: p1_15_link_auditor (up)
-- audit_object_links() 6-reason detector, invalid_object_link_audits & incremental triggers

-- 1. Invalid link reason enum
CREATE TYPE invalid_link_reason AS ENUM (
    'DANGLING_SOURCE',
    'DANGLING_TARGET',
    'SOFT_DELETED_ENDPOINT',
    'ARCHIVED_POLICY_VIOLATION',
    'TYPE_MATRIX_VIOLATION',
    'CROSS_WORKSPACE_LEAK',
    'PERMISSION_SEVERED'
);

-- 2. invalid_object_link_audits table
CREATE TABLE invalid_object_link_audits (
    id               UUID PRIMARY KEY DEFAULT uuidv7(),
    workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
    link_id          UUID NOT NULL,
    reason           invalid_link_reason NOT NULL,
    link_snapshot    JSONB NOT NULL CHECK (jsonb_typeof(link_snapshot) = 'object'),
    source_snapshot  JSONB CHECK (source_snapshot IS NULL OR jsonb_typeof(source_snapshot) = 'object'),
    target_snapshot  JSONB CHECK (target_snapshot IS NULL OR jsonb_typeof(target_snapshot) = 'object'),
    detected_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    resolved_at      TIMESTAMPTZ,
    purged_at        TIMESTAMPTZ,
    purged_by_id     UUID REFERENCES principals(id) ON DELETE RESTRICT,
    purge_reason     TEXT CHECK (purge_reason IS NULL OR char_length(btrim(purge_reason)) BETWEEN 3 AND 1000)
);

CREATE UNIQUE INDEX invalid_link_audits_open_uq
    ON invalid_object_link_audits (link_id, reason)
    WHERE purged_at IS NULL AND resolved_at IS NULL;

CREATE INDEX invalid_link_audits_ws_open_idx
    ON invalid_object_link_audits (workspace_id, detected_at DESC)
    WHERE purged_at IS NULL AND resolved_at IS NULL;

ALTER TABLE invalid_object_link_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE invalid_object_link_audits FORCE ROW LEVEL SECURITY;

REVOKE INSERT, UPDATE, DELETE ON invalid_object_link_audits FROM kanban_app, app_rls_reader;
GRANT SELECT ON invalid_object_link_audits TO kanban_app, app_rls_reader;

CREATE POLICY invalid_link_audits_select_rls ON invalid_object_link_audits
FOR SELECT TO kanban_app, app_rls_reader
USING (
    workspace_id = app_current_workspace_id() AND (
        app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])
        OR (
            (source_snapshot->>'project_id') IS NOT NULL
            AND app_principal_has_role((source_snapshot->>'project_id')::uuid, ARRAY['PROJECT_ADMIN'])
        )
        OR (
            (target_snapshot->>'project_id') IS NOT NULL
            AND app_principal_has_role((target_snapshot->>'project_id')::uuid, ARRAY['PROJECT_ADMIN'])
        )
    )
);

-- 3. Immutability guard trigger on invalid_object_link_audits
CREATE OR REPLACE FUNCTION invalid_link_audits_guard_bud()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_AUDIT_RECORD_IMMUTABLE';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.id IS DISTINCT FROM OLD.id
           OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id
           OR NEW.link_id IS DISTINCT FROM OLD.link_id
           OR NEW.reason IS DISTINCT FROM OLD.reason
           OR NEW.link_snapshot IS DISTINCT FROM OLD.link_snapshot
           OR NEW.source_snapshot IS DISTINCT FROM OLD.source_snapshot
           OR NEW.target_snapshot IS DISTINCT FROM OLD.target_snapshot
           OR NEW.detected_at IS DISTINCT FROM OLD.detected_at THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LINK_AUDIT_SNAPSHOT_IMMUTABLE';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER invalid_link_audits_guard_bud_trg
BEFORE UPDATE OR DELETE ON invalid_object_link_audits
FOR EACH ROW
EXECUTE FUNCTION invalid_link_audits_guard_bud();

-- 4. Audit single object link helper function
CREATE OR REPLACE FUNCTION audit_single_object_link(
    p_link_id uuid,
    p_as_of timestamptz DEFAULT clock_timestamp()
)
RETURNS TABLE(audit_id uuid, link_id uuid, reason invalid_link_reason)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
#variable_conflict use_column
DECLARE
    ol object_links%ROWTYPE;
    ws workspaces%ROWTYPE;
    src objects%ROWTYPE;
    tgt objects%ROWTYPE;
    v_src_found boolean := false;
    v_tgt_found boolean := false;
    v_reasons invalid_link_reason[] := '{}';
    r invalid_link_reason;
    v_aid uuid;
    v_src_snap jsonb := NULL;
    v_tgt_snap jsonb := NULL;
BEGIN
    SELECT * INTO ol FROM object_links WHERE id = p_link_id;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF ol.link_state = 'PURGED' THEN
        RETURN;
    END IF;

    -- Permission check
    IF pg_trigger_depth() = 0 THEN
        IF session_user IN ('kanban_app', 'app_rls_reader') OR current_user IN ('kanban_app', 'app_rls_reader') THEN
            IF app_current_workspace_id() IS DISTINCT FROM ol.workspace_id
               OR NOT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']) THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'AUDIT_LINKS_FORBIDDEN';
            END IF;
        END IF;
    END IF;

    SELECT * INTO ws FROM workspaces WHERE id = ol.workspace_id;

    SELECT * INTO src FROM objects WHERE id = ol.source_id;
    IF FOUND THEN
        v_src_found := true;
        v_src_snap := to_jsonb(src);
    END IF;

    SELECT * INTO tgt FROM objects WHERE id = ol.target_id;
    IF FOUND THEN
        v_tgt_found := true;
        v_tgt_snap := to_jsonb(tgt);
    END IF;

    -- Class 1: Dangling source or target
    IF NOT v_src_found OR src.object_type <> ol.source_type THEN
        v_reasons := array_append(v_reasons, 'DANGLING_SOURCE'::invalid_link_reason);
    END IF;
    IF NOT v_tgt_found OR tgt.object_type <> ol.target_type THEN
        v_reasons := array_append(v_reasons, 'DANGLING_TARGET'::invalid_link_reason);
    END IF;

    -- Class 2: Soft deleted endpoint past trash retention
    IF (v_src_found AND src.deleted_at IS NOT NULL
        AND src.deleted_at <= (p_as_of - make_interval(days => ws.trash_retention_days)))
       OR
       (v_tgt_found AND tgt.deleted_at IS NOT NULL
        AND tgt.deleted_at <= (p_as_of - make_interval(days => ws.trash_retention_days))) THEN
        v_reasons := array_append(v_reasons, 'SOFT_DELETED_ENDPOINT'::invalid_link_reason);
    END IF;

    -- Class 3: Archived policy violation
    IF v_src_found AND v_tgt_found THEN
        IF (ol.link_type = 'BLOCKS' AND src.archived_at IS NOT NULL AND tgt.archived_at IS NULL AND tgt.deleted_at IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM issues i
                JOIN workflow_states s ON s.id = i.state_id
                WHERE i.id = tgt.id AND s.state_group IN ('completed', 'cancelled')
            ))
           OR
           (ol.link_type = 'BLOCKED_BY' AND tgt.archived_at IS NOT NULL AND src.archived_at IS NULL AND src.deleted_at IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM issues i
                JOIN workflow_states s ON s.id = i.state_id
                WHERE i.id = src.id AND s.state_group IN ('completed', 'cancelled')
            )) THEN
            v_reasons := array_append(v_reasons, 'ARCHIVED_POLICY_VIOLATION'::invalid_link_reason);
        END IF;
    END IF;

    -- Class 4: Type matrix violation
    IF NOT EXISTS (
        SELECT 1 FROM link_type_matrix m
        WHERE m.source_type = ol.source_type
          AND m.link_type = ol.link_type
          AND m.target_type = ol.target_type
    ) THEN
        v_reasons := array_append(v_reasons, 'TYPE_MATRIX_VIOLATION'::invalid_link_reason);
    END IF;

    -- Class 5: Cross workspace leak
    IF v_src_found AND v_tgt_found THEN
        IF src.workspace_id <> tgt.workspace_id OR src.workspace_id <> ol.workspace_id THEN
            v_reasons := array_append(v_reasons, 'CROSS_WORKSPACE_LEAK'::invalid_link_reason);
        END IF;
    END IF;

    -- Class 6: Permission severed
    IF v_src_found AND v_tgt_found THEN
        IF NOT EXISTS (
            SELECT 1
            FROM effective_resource_access es
            JOIN effective_resource_access et ON es.principal_id = et.principal_id
            WHERE es.object_id = ol.source_id
              AND et.object_id = ol.target_id
              AND es.principal_id = ol.created_by_id
              AND (es.effective_mask & 1) = 1
              AND (et.effective_mask & 1) = 1
        ) THEN
            v_reasons := array_append(v_reasons, 'PERMISSION_SEVERED'::invalid_link_reason);
        END IF;
    END IF;

    -- State transition & snapshot creation
    IF array_length(v_reasons, 1) > 0 THEN
        IF ol.link_state <> 'FLAGGED_INVALID' AND ol.link_state <> 'PURGED' THEN
            BEGIN
                UPDATE object_links SET link_state = 'FLAGGED_INVALID' WHERE id = ol.id;
            EXCEPTION WHEN foreign_key_violation THEN
                NULL;
            END;
        END IF;

        FOREACH r IN ARRAY v_reasons LOOP
            INSERT INTO invalid_object_link_audits (
                workspace_id, link_id, reason, link_snapshot, source_snapshot, target_snapshot, detected_at
            ) VALUES (
                ol.workspace_id, ol.id, r, to_jsonb(ol), v_src_snap, v_tgt_snap, p_as_of
            )
            ON CONFLICT (link_id, reason) WHERE purged_at IS NULL AND resolved_at IS NULL
            DO NOTHING;

            SELECT a.id INTO v_aid
              FROM invalid_object_link_audits a
             WHERE a.link_id = ol.id
               AND a.reason = r
               AND a.purged_at IS NULL
               AND a.resolved_at IS NULL;

            audit_id := v_aid;
            link_id := ol.id;
            reason := r;
            RETURN NEXT;
        END LOOP;

        -- Auto-heal any previously flagged reasons for this link that no longer hold
        UPDATE invalid_object_link_audits
           SET resolved_at = p_as_of
         WHERE invalid_object_link_audits.link_id = ol.id
           AND invalid_object_link_audits.purged_at IS NULL
           AND invalid_object_link_audits.resolved_at IS NULL
           AND invalid_object_link_audits.reason <> ALL(v_reasons);
    ELSE
        -- No violations: auto-heal all open audits for this link
        UPDATE invalid_object_link_audits
           SET resolved_at = p_as_of
         WHERE invalid_object_link_audits.link_id = ol.id
           AND invalid_object_link_audits.purged_at IS NULL
           AND invalid_object_link_audits.resolved_at IS NULL;

        IF ol.link_state = 'FLAGGED_INVALID' THEN
            UPDATE object_links SET link_state = 'ACTIVE' WHERE id = ol.id;
        END IF;
    END IF;

    RETURN;
END;
$$;

-- 5. audit_object_links() workspace-level detector
CREATE OR REPLACE FUNCTION audit_object_links(
    p_workspace_id uuid,
    p_as_of timestamptz DEFAULT clock_timestamp()
)
RETURNS TABLE(audit_id uuid, link_id uuid, reason invalid_link_reason)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
#variable_conflict use_column
DECLARE
    v_lid uuid;
BEGIN
    -- Permission check
    IF pg_trigger_depth() = 0 THEN
        IF session_user IN ('kanban_app', 'app_rls_reader') OR current_user IN ('kanban_app', 'app_rls_reader') THEN
            IF app_current_workspace_id() IS DISTINCT FROM p_workspace_id
               OR NOT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']) THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'AUDIT_LINKS_FORBIDDEN';
            END IF;
        END IF;
    END IF;

    FOR v_lid IN
        SELECT id FROM object_links WHERE workspace_id = p_workspace_id AND link_state <> 'PURGED'
    LOOP
        RETURN QUERY
        SELECT * FROM audit_single_object_link(v_lid, p_as_of);
    END LOOP;

    RETURN;
END;
$$;

-- 6. audit_object_links_for_object() incremental detector
CREATE OR REPLACE FUNCTION audit_object_links_for_object(p_object_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_lid uuid;
BEGIN
    FOR v_lid IN
        SELECT id FROM object_links
         WHERE (source_id = p_object_id OR target_id = p_object_id)
           AND link_state <> 'PURGED'
    LOOP
        PERFORM audit_single_object_link(v_lid, clock_timestamp());
    END LOOP;
END;
$$;

-- 7. Incremental triggers
CREATE OR REPLACE FUNCTION objects_link_audit_trg_fn()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    PERFORM audit_object_links_for_object(NEW.id);
    RETURN NEW;
END;
$$;

CREATE TRIGGER objects_link_audit_trg
AFTER UPDATE OF archived_at, deleted_at, workspace_id ON objects
FOR EACH ROW
EXECUTE FUNCTION objects_link_audit_trg_fn();

CREATE OR REPLACE FUNCTION resource_acl_link_audit_trg_fn()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM audit_object_links_for_object(OLD.object_id);
    ELSE
        PERFORM audit_object_links_for_object(NEW.object_id);
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER z_resource_acl_link_audit_trg
AFTER INSERT OR UPDATE OR DELETE ON resource_acl_entries
FOR EACH ROW
EXECUTE FUNCTION resource_acl_link_audit_trg_fn();

CREATE OR REPLACE FUNCTION role_bindings_link_audit_trg_fn()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_oid uuid;
BEGIN
    IF (TG_OP = 'DELETE' AND OLD.project_id IS NOT NULL) THEN
        FOR v_oid IN SELECT id FROM objects WHERE project_id = OLD.project_id LOOP
            PERFORM audit_object_links_for_object(v_oid);
        END LOOP;
    ELSIF (TG_OP <> 'DELETE' AND NEW.project_id IS NOT NULL) THEN
        FOR v_oid IN SELECT id FROM objects WHERE project_id = NEW.project_id LOOP
            PERFORM audit_object_links_for_object(v_oid);
        END LOOP;
    ELSIF (TG_OP = 'DELETE') THEN
        PERFORM audit_object_links(OLD.workspace_id, clock_timestamp());
    ELSE
        PERFORM audit_object_links(NEW.workspace_id, clock_timestamp());
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER z_role_bindings_link_audit_trg
AFTER INSERT OR UPDATE OR DELETE ON role_bindings
FOR EACH ROW
EXECUTE FUNCTION role_bindings_link_audit_trg_fn();

GRANT EXECUTE ON FUNCTION audit_single_object_link(uuid, timestamptz) TO kanban_app;
GRANT EXECUTE ON FUNCTION audit_object_links(uuid, timestamptz) TO kanban_app;
GRANT EXECUTE ON FUNCTION audit_object_links_for_object(uuid) TO kanban_app;
