-- Migration p6_07: Content Provenance Trust Tiers and Untrusted Content Taint Tracking (KB-SEC-TAINT-01)

-- 1. Add provenance_tier and is_untrusted_content to issues
ALTER TABLE issues
    ADD COLUMN provenance_tier TEXT NOT NULL DEFAULT 'trusted_member'
        CHECK (provenance_tier IN ('trusted_member', 'verified_agent', 'imported', 'external_webhook', 'public_reporter', 'untrusted_intake')),
    ADD COLUMN is_untrusted_content BOOLEAN GENERATED ALWAYS AS (
        provenance_tier IN ('imported', 'external_webhook', 'public_reporter', 'untrusted_intake')
    ) STORED;

-- 2. Add provenance_tier and is_untrusted_content to issue_comments
ALTER TABLE issue_comments
    ADD COLUMN provenance_tier TEXT NOT NULL DEFAULT 'trusted_member'
        CHECK (provenance_tier IN ('trusted_member', 'verified_agent', 'imported', 'external_webhook', 'public_reporter', 'untrusted_intake')),
    ADD COLUMN is_untrusted_content BOOLEAN GENERATED ALWAYS AS (
        provenance_tier IN ('imported', 'external_webhook', 'public_reporter', 'untrusted_intake')
    ) STORED;

-- 3. Add provenance_tier and is_untrusted_content to docs
ALTER TABLE docs
    ADD COLUMN provenance_tier TEXT NOT NULL DEFAULT 'trusted_member'
        CHECK (provenance_tier IN ('trusted_member', 'verified_agent', 'imported', 'external_webhook', 'public_reporter', 'untrusted_intake')),
    ADD COLUMN is_untrusted_content BOOLEAN GENERATED ALWAYS AS (
        provenance_tier IN ('imported', 'external_webhook', 'public_reporter', 'untrusted_intake')
    ) STORED;

-- 4. Add provenance_tier and is_untrusted_content to pages
ALTER TABLE pages
    ADD COLUMN provenance_tier TEXT NOT NULL DEFAULT 'trusted_member'
        CHECK (provenance_tier IN ('trusted_member', 'verified_agent', 'imported', 'external_webhook', 'public_reporter', 'untrusted_intake')),
    ADD COLUMN is_untrusted_content BOOLEAN GENERATED ALWAYS AS (
        provenance_tier IN ('imported', 'external_webhook', 'public_reporter', 'untrusted_intake')
    ) STORED;

-- 5. Add provenance_tier and is_untrusted_content to stickies
ALTER TABLE stickies
    ADD COLUMN provenance_tier TEXT NOT NULL DEFAULT 'trusted_member'
        CHECK (provenance_tier IN ('trusted_member', 'verified_agent', 'imported', 'external_webhook', 'public_reporter', 'untrusted_intake')),
    ADD COLUMN is_untrusted_content BOOLEAN GENERATED ALWAYS AS (
        provenance_tier IN ('imported', 'external_webhook', 'public_reporter', 'untrusted_intake')
    ) STORED;

-- 6. Extend mcp_read_taint table with untrusted content tracking
ALTER TABLE mcp_read_taint
    ADD COLUMN untrusted_source_object_id UUID NULL,
    ADD COLUMN contains_untrusted_content BOOLEAN NOT NULL DEFAULT FALSE;
