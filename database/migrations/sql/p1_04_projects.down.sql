ALTER TABLE objects DROP CONSTRAINT IF EXISTS objects_project_fk;

DROP TRIGGER IF EXISTS workflow_states_group_guard_bd_trg ON workflow_states;
DROP FUNCTION IF EXISTS workflow_states_group_guard_bd();

DROP TRIGGER IF EXISTS projects_seed_defaults_ai_trg ON projects;
DROP FUNCTION IF EXISTS projects_seed_defaults_ai();

DROP TRIGGER IF EXISTS project_labels_workspace_match_biu_trg ON project_labels;
DROP FUNCTION IF EXISTS project_labels_workspace_match_biu();
DROP TABLE IF EXISTS project_labels CASCADE;

DROP TRIGGER IF EXISTS project_priorities_workspace_match_biu_trg ON project_priorities;
DROP FUNCTION IF EXISTS project_priorities_workspace_match_biu();
DROP TABLE IF EXISTS project_priorities CASCADE;

DROP TRIGGER IF EXISTS workflow_states_workspace_match_biu_trg ON workflow_states;
DROP FUNCTION IF EXISTS workflow_states_workspace_match_biu();
DROP TABLE IF EXISTS workflow_states CASCADE;

DROP TRIGGER IF EXISTS projects_seq_guard_bu_trg ON projects;
DROP FUNCTION IF EXISTS projects_seq_guard_bu();

DROP TRIGGER IF EXISTS projects_spine_match_biu_trg ON projects;
DROP FUNCTION IF EXISTS projects_spine_match_biu();

DROP TABLE IF EXISTS projects CASCADE;
