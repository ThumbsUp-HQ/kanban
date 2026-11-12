-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Migration: p3_17_search_indexes
-- Description: tsvector generated columns on docs, pages, stickies and GIN indexes across search surfaces

-- 1. Generated tsvector columns
ALTER TABLE docs ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(build_markdown_tsvector(body_markdown), 'B')
) STORED;

ALTER TABLE pages ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(build_markdown_tsvector(body_markdown), 'B')
) STORED;

ALTER TABLE stickies ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (
    build_markdown_tsvector(body_markdown)
) STORED;

-- 2. GIN full-text and trigram indexes
CREATE INDEX IF NOT EXISTS issues_search_tsv_gin ON issues USING gin (search_tsv);
CREATE INDEX IF NOT EXISTS issues_summary_trgm_gin ON issues USING gin (summary gin_trgm_ops);
CREATE INDEX IF NOT EXISTS docs_search_tsv_gin ON docs USING gin (search_tsv);
CREATE INDEX IF NOT EXISTS docs_title_trgm_gin ON docs USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS pages_search_tsv_gin ON pages USING gin (search_tsv);
CREATE INDEX IF NOT EXISTS pages_title_trgm_gin ON pages USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS stickies_search_tsv_gin ON stickies USING gin (search_tsv);
CREATE INDEX IF NOT EXISTS stickies_body_trgm_gin ON stickies USING gin (body_markdown gin_trgm_ops);
