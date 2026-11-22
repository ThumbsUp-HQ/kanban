-- Revert Migration p6_07: Content Provenance Trust Tiers and Untrusted Content Taint Tracking

ALTER TABLE mcp_read_taint
    DROP COLUMN IF EXISTS contains_untrusted_content,
    DROP COLUMN IF EXISTS untrusted_source_object_id;

ALTER TABLE stickies
    DROP COLUMN IF EXISTS is_untrusted_content,
    DROP COLUMN IF EXISTS provenance_tier;

ALTER TABLE pages
    DROP COLUMN IF EXISTS is_untrusted_content,
    DROP COLUMN IF EXISTS provenance_tier;

ALTER TABLE docs
    DROP COLUMN IF EXISTS is_untrusted_content,
    DROP COLUMN IF EXISTS provenance_tier;

ALTER TABLE issue_comments
    DROP COLUMN IF EXISTS is_untrusted_content,
    DROP COLUMN IF EXISTS provenance_tier;

ALTER TABLE issues
    DROP COLUMN IF EXISTS is_untrusted_content,
    DROP COLUMN IF EXISTS provenance_tier;
