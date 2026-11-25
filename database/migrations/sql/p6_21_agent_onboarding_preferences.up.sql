-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

ALTER TABLE public.user_preferences
    ADD COLUMN IF NOT EXISTS agent_onboarding_prefs_json JSONB NOT NULL DEFAULT '{}'::jsonb;
