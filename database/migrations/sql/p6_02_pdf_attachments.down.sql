-- Copyright 2026 Kanban Platform Contributors
-- Apache-2.0 License. See LICENSE for details.

-- Drop page_count check constraint and column
ALTER TABLE attachments DROP CONSTRAINT IF EXISTS attachments_page_count_check;
ALTER TABLE attachments DROP COLUMN IF EXISTS page_count;

-- Restore original attachments_content_type_check
ALTER TABLE attachments DROP CONSTRAINT IF EXISTS attachments_content_type_check;

ALTER TABLE attachments ADD CONSTRAINT attachments_content_type_check CHECK (
    content_type IN (
        'image/png',
        'image/jpeg',
        'image/webp',
        'image/avif',
        'image/gif',
        'image/svg+xml'
    )
);
