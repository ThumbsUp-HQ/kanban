-- === PG_DUMP VIEWS TABLE ===
--
-- PostgreSQL database dump
--

\restrict JbeaE2jEE03FrvbDcNKtGU2WSdkyCiZNIPHx7oXlsdYVxotaLKVxFZIDYlZe4Cy

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg12+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: views; Type: TABLE; Schema: public; Owner: kanban_migrator
--

CREATE TABLE public.views (
    id uuid NOT NULL,
    object_type public.object_kind DEFAULT 'view'::public.object_kind NOT NULL,
    workspace_id uuid NOT NULL,
    project_id uuid,
    owner_principal_id uuid NOT NULL,
    visibility text DEFAULT 'project'::text NOT NULL,
    name text NOT NULL,
    summary_markdown text DEFAULT ''::text NOT NULL,
    summary_sha256 bytea GENERATED ALWAYS AS (public.digest(summary_markdown, 'sha256'::text)) STORED,
    layout public.view_layout DEFAULT 'board'::public.view_layout NOT NULL,
    group_by text,
    sub_group_by text,
    filters_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    display_props_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    wip_limits_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    sort_rank text DEFAULT 'a0'::text NOT NULL COLLATE pg_catalog."C",
    CONSTRAINT views_check CHECK (((visibility <> 'project'::text) OR (project_id IS NOT NULL))),
    CONSTRAINT views_check1 CHECK (((group_by IS NULL) OR (sub_group_by IS NULL) OR (group_by <> sub_group_by))),
    CONSTRAINT views_display_props_json_check CHECK (((jsonb_typeof(display_props_json) = 'object'::text) AND (octet_length((display_props_json)::text) <= 8192))),
    CONSTRAINT views_filters_json_check CHECK (public.validate_view_filters_json(filters_json)),
    CONSTRAINT views_group_by_check CHECK (((group_by IS NULL) OR (group_by = ANY (ARRAY['state'::text, 'priority'::text, 'assignee'::text, 'cycle'::text, 'module'::text, 'label'::text, 'project'::text])))),
    CONSTRAINT views_name_check CHECK (((char_length(btrim(name)) >= 1) AND (char_length(btrim(name)) <= 200))),
    CONSTRAINT views_object_type_check CHECK ((object_type = 'view'::public.object_kind)),
    CONSTRAINT views_sub_group_by_check CHECK (((sub_group_by IS NULL) OR (sub_group_by = ANY (ARRAY['assignee'::text, 'priority'::text, 'cycle'::text, 'module'::text, 'label'::text, 'state'::text])))),
    CONSTRAINT views_summary_markdown_check CHECK ((octet_length(summary_markdown) <= 65536)),
    CONSTRAINT views_visibility_check CHECK ((visibility = ANY (ARRAY['private'::text, 'project'::text, 'workspace'::text]))),
    CONSTRAINT views_wip_limits_json_check CHECK (public.validate_view_wip_limits_json(wip_limits_json))
);


ALTER TABLE public.views OWNER TO kanban_migrator;

--
-- Name: views views_pkey; Type: CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.views
    ADD CONSTRAINT views_pkey PRIMARY KEY (id);


--
-- Name: views_project_rank_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX views_project_rank_idx ON public.views USING btree (project_id, sort_rank) WHERE (project_id IS NOT NULL);


--
-- Name: views_ws_owner_idx; Type: INDEX; Schema: public; Owner: kanban_migrator
--

CREATE INDEX views_ws_owner_idx ON public.views USING btree (workspace_id, owner_principal_id);


--
-- Name: views views_spine_match_biu_trg; Type: TRIGGER; Schema: public; Owner: kanban_migrator
--

CREATE TRIGGER views_spine_match_biu_trg BEFORE INSERT OR UPDATE ON public.views FOR EACH ROW EXECUTE FUNCTION public.views_spine_match_biu();


--
-- Name: views views_id_object_type_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.views
    ADD CONSTRAINT views_id_object_type_fkey FOREIGN KEY (id, object_type) REFERENCES public.objects(id, object_type) ON DELETE RESTRICT;


--
-- Name: views views_owner_principal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.views
    ADD CONSTRAINT views_owner_principal_id_fkey FOREIGN KEY (owner_principal_id) REFERENCES public.principals(id) ON DELETE RESTRICT;


--
-- Name: views views_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.views
    ADD CONSTRAINT views_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: views views_workspace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: kanban_migrator
--

ALTER TABLE ONLY public.views
    ADD CONSTRAINT views_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE RESTRICT;


--
-- Name: TABLE views; Type: ACL; Schema: public; Owner: kanban_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.views TO kanban_app;
GRANT SELECT ON TABLE public.views TO app_rls_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict JbeaE2jEE03FrvbDcNKtGU2WSdkyCiZNIPHx7oXlsdYVxotaLKVxFZIDYlZe4Cy


-- === \dT+ view_layout ===
                                             List of data types
 Schema |    Name     | Internal name | Size | Elements |      Owner      | Access privileges | Description 
--------+-------------+---------------+------+----------+-----------------+-------------------+-------------
 public | view_layout | view_layout   | 4    | list    +| kanban_migrator |                   | 
        |             |               |      | board   +|                 |                   | 
        |             |               |      | table   +|                 |                   | 
        |             |               |      | calendar+|                 |                   | 
        |             |               |      | timeline |                 |                   | 
(1 row)


-- === \sf validate_view_wip_limits_json ===
CREATE OR REPLACE FUNCTION public.validate_view_wip_limits_json(p_doc jsonb)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE PARALLEL SAFE
AS $function$
DECLARE
    v_k text;
    v_v jsonb;
    v_prop_k text;
    v_soft_present boolean;
    v_hard_present boolean;
    v_soft_val int;
    v_hard_val int;
    v_num_val numeric;
BEGIN
    IF p_doc IS NULL THEN
        RETURN FALSE;
    END IF;
    IF jsonb_typeof(p_doc) <> 'object' THEN
        RETURN FALSE;
    END IF;
    IF octet_length(p_doc::text) > 8192 THEN
        RETURN FALSE;
    END IF;

    FOR v_k, v_v IN SELECT * FROM jsonb_each(p_doc) LOOP
        -- Key must be valid UUID string
        IF v_k !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN
            RETURN FALSE;
        END IF;

        -- Value must be a JSON object
        IF jsonb_typeof(v_v) <> 'object' THEN
            RETURN FALSE;
        END IF;

        v_soft_present := FALSE;
        v_hard_present := FALSE;
        v_soft_val := NULL;
        v_hard_val := NULL;

        -- Keys of v_v must be subset of ('soft', 'hard')
        FOR v_prop_k IN SELECT jsonb_object_keys(v_v) LOOP
            IF v_prop_k NOT IN ('soft', 'hard') THEN
                RETURN FALSE;
            END IF;
        END LOOP;

        -- Check 'soft' if present
        IF v_v ? 'soft' AND jsonb_typeof(v_v->'soft') <> 'null' THEN
            IF jsonb_typeof(v_v->'soft') <> 'number' THEN
                RETURN FALSE;
            END IF;
            BEGIN
                v_num_val := (v_v->>'soft')::numeric;
                IF v_num_val <> trunc(v_num_val) OR v_num_val < 1 OR v_num_val > 10000 THEN
                    RETURN FALSE;
                END IF;
                v_soft_val := v_num_val::int;
                v_soft_present := TRUE;
            EXCEPTION WHEN OTHERS THEN
                RETURN FALSE;
            END;
        END IF;

        -- Check 'hard' if present
        IF v_v ? 'hard' AND jsonb_typeof(v_v->'hard') <> 'null' THEN
            IF jsonb_typeof(v_v->'hard') <> 'number' THEN
                RETURN FALSE;
            END IF;
            BEGIN
                v_num_val := (v_v->>'hard')::numeric;
                IF v_num_val <> trunc(v_num_val) OR v_num_val < 1 OR v_num_val > 10000 THEN
                    RETURN FALSE;
                END IF;
                v_hard_val := v_num_val::int;
                v_hard_present := TRUE;
            EXCEPTION WHEN OTHERS THEN
                RETURN FALSE;
            END;
        END IF;

        -- When both soft and hard are non-null: hard >= soft
        IF v_soft_present AND v_hard_present THEN
            IF v_hard_val < v_soft_val THEN
                RETURN FALSE;
            END IF;
        END IF;

    END LOOP;

    RETURN TRUE;
END;
$function$
