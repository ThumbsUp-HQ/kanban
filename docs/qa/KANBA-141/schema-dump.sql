-- Table definition: mcp_read_taint
  workspace_id uuid (nullable: NO, default: None)
  taint_key bytea (nullable: NO, default: None)
  key_kind text (nullable: NO, default: None)
  project_id uuid (nullable: NO, default: None)
  first_read_at timestamp with time zone (nullable: NO, default: clock_timestamp())
  expires_at timestamp with time zone (nullable: NO, default: None)

-- Primary key and constraints:
  mcp_read_taint_key_kind_check: CHECK ((key_kind = ANY (ARRAY['session'::text, 'credential'::text])))
  mcp_read_taint_pkey: PRIMARY KEY (taint_key, project_id)
  mcp_read_taint_project_id_fkey: FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
  mcp_read_taint_taint_key_check: CHECK ((octet_length(taint_key) = 32))
  mcp_read_taint_workspace_id_fkey: FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE

-- Indexes:
  mcp_read_taint_pkey: CREATE UNIQUE INDEX mcp_read_taint_pkey ON public.mcp_read_taint USING btree (taint_key, project_id)
  mcp_read_taint_workspace_idx: CREATE INDEX mcp_read_taint_workspace_idx ON public.mcp_read_taint USING btree (workspace_id)
  mcp_read_taint_expires_idx: CREATE INDEX mcp_read_taint_expires_idx ON public.mcp_read_taint USING btree (expires_at)

-- Row Level Security:
  rowsecurity: True, forcerowsecurity: True

-- Policies:
  mcp_read_taint_delete_rls (cmd: b'd', permissive: True): (workspace_id = app_current_workspace_id())
  mcp_read_taint_insert_rls (cmd: b'a', permissive: True): None
  mcp_read_taint_select_rls (cmd: b'r', permissive: True): ((app_current_workspace_id() IS NULL) OR (workspace_id = app_current_workspace_id()))
  mcp_read_taint_update_rls (cmd: b'w', permissive: True): ((app_current_workspace_id() IS NULL) OR (workspace_id = app_current_workspace_id()))