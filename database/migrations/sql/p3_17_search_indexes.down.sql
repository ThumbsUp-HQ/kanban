-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Revert Migration: p3_17_search_indexes

DROP INDEX IF EXISTS stickies_body_trgm_gin;
DROP INDEX IF EXISTS stickies_search_tsv_gin;
DROP INDEX IF EXISTS pages_title_trgm_gin;
DROP INDEX IF EXISTS pages_search_tsv_gin;
DROP INDEX IF EXISTS docs_title_trgm_gin;
DROP INDEX IF EXISTS docs_search_tsv_gin;
DROP INDEX IF EXISTS issues_summary_trgm_gin;
DROP INDEX IF EXISTS issues_search_tsv_gin;

ALTER TABLE stickies DROP COLUMN IF EXISTS search_tsv;
ALTER TABLE pages DROP COLUMN IF EXISTS search_tsv;
ALTER TABLE docs DROP COLUMN IF EXISTS search_tsv;
