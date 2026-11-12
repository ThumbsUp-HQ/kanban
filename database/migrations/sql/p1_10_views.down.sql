-- Migration: p1_10_views (down)
-- Revert views table, view_layout enum, and filter/WIP JSON validators.

DROP TRIGGER IF EXISTS views_spine_match_biu_trg ON views;
DROP FUNCTION IF EXISTS views_spine_match_biu();
DROP TABLE IF EXISTS views CASCADE;
DROP TYPE IF EXISTS view_layout;
DROP FUNCTION IF EXISTS validate_view_wip_limits_json(jsonb);
DROP FUNCTION IF EXISTS validate_view_filters_json(jsonb);
