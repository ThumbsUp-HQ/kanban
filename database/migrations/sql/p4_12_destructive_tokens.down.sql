-- KB-P4-12: Drop destructive confirmation tokens table

DROP TABLE IF EXISTS destructive_confirmation_tokens CASCADE;

CREATE OR REPLACE FUNCTION workflow_states_group_guard_bd() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_remaining INTEGER;
BEGIN
    IF OLD.state_group IN ('completed', 'cancelled') THEN
        SELECT count(*)
          INTO v_remaining
          FROM workflow_states
         WHERE project_id = OLD.project_id
           AND state_group = OLD.state_group
           AND id <> OLD.id;

        IF v_remaining = 0 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'LAST_TERMINAL_STATE_REQUIRED';
        END IF;
    END IF;
    RETURN OLD;
END;
$$;
