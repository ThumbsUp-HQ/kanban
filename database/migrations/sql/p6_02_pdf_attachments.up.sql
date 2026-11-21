-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Widen content_type check constraint to include application/pdf
ALTER TABLE attachments DROP CONSTRAINT IF EXISTS attachments_content_type_check;

ALTER TABLE attachments ADD CONSTRAINT attachments_content_type_check CHECK (
    content_type IN (
        'image/png',
        'image/jpeg',
        'image/webp',
        'image/avif',
        'image/gif',
        'image/svg+xml',
        'application/pdf'
    )
);

-- Add nullable page_count column with positive integer check
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS page_count INTEGER;

ALTER TABLE attachments DROP CONSTRAINT IF EXISTS attachments_page_count_check;

ALTER TABLE attachments ADD CONSTRAINT attachments_page_count_check CHECK (
    page_count IS NULL OR page_count > 0
);
