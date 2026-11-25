-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

ALTER TABLE public.user_preferences
    DROP COLUMN IF EXISTS agent_onboarding_prefs_json;
