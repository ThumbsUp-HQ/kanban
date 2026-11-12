-- \sf purge_invalid_object_links
CREATE OR REPLACE FUNCTION public.purge_invalid_object_links(p_audit_ids uuid[], p_actor_id uuid, p_reason text)
 RETURNS TABLE(purged_audit_id uuid, purged_link_id uuid, activity_id uuid)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
#variable_conflict use_column
DECLARE
    v_sorted_ids uuid[];
    v_session_actor uuid;
    v_ws uuid;
    v_audit_count integer;
    v_link_ids uuid[];
    v_link_count integer;
    v_rec record;
    v_obj_id uuid;
    v_obj_type object_kind;
    v_audit_ids_for_link jsonb;
    v_reasons_for_link jsonb;
    v_act_id uuid;
    v_aud_id uuid;
BEGIN
    -- 1. Validation & Authorization (fail-closed before mutating any row)
    IF p_audit_ids IS NULL
       OR coalesce(array_length(p_audit_ids, 1), 0) < 1
       OR coalesce(array_length(p_audit_ids, 1), 0) > 1000
       OR array_position(p_audit_ids, NULL) IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PURGE_AUDIT_IDS_INVALID';
    END IF;

    -- Deduplicate p_audit_ids preserving deterministic UUID sort order
    SELECT array_agg(DISTINCT u ORDER BY u)
    INTO v_sorted_ids
    FROM unnest(p_audit_ids) AS u;

    IF p_reason IS NULL
       OR char_length(btrim(p_reason)) < 3
       OR char_length(btrim(p_reason)) > 1000 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PURGE_REASON_REQUIRED';
    END IF;

    v_session_actor := app_current_principal_id();
    v_ws := app_current_workspace_id();
    IF v_session_actor IS NULL OR v_ws IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'RLS_CONTEXT_REQUIRED';
    END IF;

    IF v_session_actor IS DISTINCT FROM p_actor_id THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PURGE_ACTOR_MISMATCH';
    END IF;

    IF NOT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN']) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PURGE_FORBIDDEN';
    END IF;

    -- 2. Lock invalid_object_link_audits rows matching id = ANY(v_sorted_ids) ordered by id FOR UPDATE
    PERFORM 1
    FROM invalid_object_link_audits a
    WHERE a.id = ANY(v_sorted_ids)
    ORDER BY a.id
    FOR UPDATE;
    GET DIAGNOSTICS v_audit_count = ROW_COUNT;

    IF v_audit_count < cardinality(v_sorted_ids) OR EXISTS (
        SELECT 1 FROM invalid_object_link_audits a
        WHERE a.id = ANY(v_sorted_ids) AND a.workspace_id <> v_ws
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PURGE_AUDIT_NOT_FOUND';
    END IF;

    IF EXISTS (
        SELECT 1 FROM invalid_object_link_audits a
        WHERE a.id = ANY(v_sorted_ids) AND a.purged_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PURGE_ALREADY_EXECUTED';
    END IF;

    IF EXISTS (
        SELECT 1 FROM invalid_object_link_audits a
        WHERE a.id = ANY(v_sorted_ids) AND a.resolved_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PURGE_AUDIT_RESOLVED';
    END IF;

    -- 3. Lock corresponding object_links rows ordered by id FOR UPDATE
    SELECT array_agg(DISTINCT a.link_id ORDER BY a.link_id)
    INTO v_link_ids
    FROM invalid_object_link_audits a
    WHERE a.id = ANY(v_sorted_ids);

    PERFORM 1
    FROM object_links ol
    WHERE ol.id = ANY(v_link_ids)
    ORDER BY ol.id
    FOR UPDATE;
    GET DIAGNOSTICS v_link_count = ROW_COUNT;

    IF v_link_count < cardinality(v_link_ids) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PURGE_LINK_MISSING';
    END IF;

    IF EXISTS (
        SELECT 1 FROM object_links ol
        WHERE ol.id = ANY(v_link_ids) AND ol.link_state <> 'FLAGGED_INVALID'
    ) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'PURGE_ACTIVE_LINK_REFUSED';
    END IF;

    -- 4. Delete flagged links under bypass setting
    PERFORM set_config('kb.in_audited_purge', 'on', true);

    -- Loop over links to collect metadata, delete, update audits, and record activity
    FOR v_rec IN
        SELECT ol.id, ol.source_id, ol.source_type, ol.target_id, ol.target_type,
               ol.source_key_snapshot, ol.target_key_snapshot
        FROM object_links ol
        WHERE ol.id = ANY(v_link_ids)
        ORDER BY ol.id
    LOOP
        DELETE FROM object_links WHERE id = v_rec.id;

        -- 5. Update all open invalid_object_link_audits rows on this link
        UPDATE invalid_object_link_audits
        SET purged_at = clock_timestamp(),
            purged_by_id = p_actor_id,
            purge_reason = btrim(p_reason)
        WHERE link_id = v_rec.id
          AND purged_at IS NULL
          AND resolved_at IS NULL;

        -- 6. Determine activity anchor (v_obj_id, v_obj_type)
        SELECT id, object_type INTO v_obj_id, v_obj_type
        FROM objects
        WHERE id = v_rec.source_id AND object_type = v_rec.source_type AND workspace_id = v_ws;

        IF NOT FOUND THEN
            SELECT id, object_type INTO v_obj_id, v_obj_type
            FROM objects
            WHERE id = v_rec.target_id AND object_type = v_rec.target_type AND workspace_id = v_ws;
            IF NOT FOUND THEN
                v_obj_id := NULL;
                v_obj_type := NULL;
            END IF;
        END IF;

        -- Aggregate audit_ids and reasons for this link
        SELECT jsonb_agg(a.id ORDER BY a.id),
               jsonb_agg(a.reason::text ORDER BY a.reason::text)
        INTO v_audit_ids_for_link, v_reasons_for_link
        FROM invalid_object_link_audits a
        WHERE a.link_id = v_rec.id
          AND a.purged_by_id = p_actor_id
          AND a.purge_reason = btrim(p_reason);

        v_act_id := append_activity(
            v_ws,
            v_obj_id,
            v_obj_type,
            p_actor_id,
            'INVALID_OBJECT_LINK_PURGED',
            jsonb_build_object(
                'audit_ids', v_audit_ids_for_link,
                'link_id', v_rec.id,
                'reasons', v_reasons_for_link,
                'purge_reason', btrim(p_reason),
                'source_key_snapshot', v_rec.source_key_snapshot,
                'target_key_snapshot', v_rec.target_key_snapshot
            )
        );

        FOR v_aud_id IN
            SELECT a.id FROM invalid_object_link_audits a
            WHERE a.link_id = v_rec.id
              AND a.purged_by_id = p_actor_id
              AND a.purge_reason = btrim(p_reason)
            ORDER BY a.id
        LOOP
            purged_audit_id := v_aud_id;
            purged_link_id := v_rec.id;
            activity_id := v_act_id;
            RETURN NEXT;
        END LOOP;
    END LOOP;

    PERFORM set_config('kb.in_audited_purge', '', true);

    RETURN;
END;
$function$
;

-- \sf object_links_flagged_delete_guard_bd
CREATE OR REPLACE FUNCTION public.object_links_flagged_delete_guard_bd()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF OLD.link_state = 'FLAGGED_INVALID'
       AND COALESCE(current_setting('kb.in_audited_purge', true), '') <> 'on' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'FLAGGED_LINK_REQUIRES_AUDITED_PURGE';
    END IF;
    RETURN OLD;
END;
$function$
;
