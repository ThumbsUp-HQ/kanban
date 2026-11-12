-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

DROP POLICY IF EXISTS comment_reactions_delete_rls ON comment_reactions;
DROP POLICY IF EXISTS comment_reactions_insert_rls ON comment_reactions;
DROP POLICY IF EXISTS comment_reactions_select_rls ON comment_reactions;
DROP TABLE IF EXISTS comment_reactions CASCADE;
