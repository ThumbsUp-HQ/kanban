-- Migration: p1_09_prose_tables (down)
-- Revert prose tables, versioning, hierarchy, and immutability triggers.

DROP TRIGGER IF EXISTS stickies_promotion_guard_bu_trg ON stickies;
DROP FUNCTION IF EXISTS stickies_promotion_guard_bu();

DROP TRIGGER IF EXISTS page_versions_immutable_bud_trg ON page_versions;
DROP FUNCTION IF EXISTS page_versions_immutable_bud();

DROP TRIGGER IF EXISTS docs_versioning_bu_trg ON docs;
DROP FUNCTION IF EXISTS docs_versioning_bu();

DROP TRIGGER IF EXISTS pages_versioning_bu_trg ON pages;
DROP FUNCTION IF EXISTS pages_versioning_bu();

DROP TRIGGER IF EXISTS pages_hierarchy_au_trg ON pages;
DROP FUNCTION IF EXISTS pages_hierarchy_au();

DROP TRIGGER IF EXISTS pages_hierarchy_biu_trg ON pages;
DROP FUNCTION IF EXISTS pages_hierarchy_biu();

DROP TRIGGER IF EXISTS docs_hierarchy_bi_trg ON docs;
DROP FUNCTION IF EXISTS docs_hierarchy_bi();

DROP TRIGGER IF EXISTS stickies_spine_match_biu_trg ON stickies;
DROP FUNCTION IF EXISTS stickies_spine_match_biu();

DROP TRIGGER IF EXISTS pages_spine_match_biu_trg ON pages;
DROP FUNCTION IF EXISTS pages_spine_match_biu();

DROP TRIGGER IF EXISTS docs_spine_match_biu_trg ON docs;
DROP FUNCTION IF EXISTS docs_spine_match_biu();

DROP TRIGGER IF EXISTS issue_comments_workspace_biu_trg ON issue_comments;
DROP FUNCTION IF EXISTS issue_comments_workspace_biu();

DROP TABLE IF EXISTS page_versions CASCADE;
DROP TABLE IF EXISTS stickies CASCADE;
DROP TABLE IF EXISTS pages CASCADE;
DROP TABLE IF EXISTS docs CASCADE;
DROP TABLE IF EXISTS issue_comments CASCADE;
