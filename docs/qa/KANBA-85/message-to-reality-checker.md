# Message to Reality-Checker: KANBA-85 (KB-P3-05)

## Overview
- **Ticket**: KANBA-85 (`KB-P3-05`: `[Phase 3 / API] Threaded comments, reactions, permalinks & access-checked @mentions`)
- **Status**: Ready for Forensic QA Audit
- **Branch**: `feat/KANBA-85` in worktree `/tmp/kb-wt-KANBA-85`

## Schema and Migration Analysis (KB-P1-09 vs. KB-P3-05)
Per Scoped Technical Actions item 2:
> "Add `issue_comments.parent_comment_id UUID REFERENCES issue_comments(id)`, `edited_at TIMESTAMPTZ`, `deleted_at TIMESTAMPTZ` only if KB-P1-09 did not create them (record which columns were added in message-to-reality-checker.md)."

### Forensic Audit of `issue_comments` Columns
Inspection of `database/migrations/sql/p1_09_prose_tables.up.sql` confirmed that KB-P1-09 already created all 10 canonical columns:
1. `id` UUID PRIMARY KEY DEFAULT uuidv7()
2. `workspace_id` UUID NOT NULL REFERENCES workspaces(id)
3. `issue_id` UUID NOT NULL REFERENCES issues(id)
4. `parent_comment_id` UUID REFERENCES issue_comments(id) [Already created by KB-P1-09]
5. `author_id` UUID NOT NULL REFERENCES principals(id)
6. `body_markdown` TEXT NOT NULL CHECK (octet_length between 1 and 262144)
7. `body_sha256` BYTEA GENERATED ALWAYS AS (digest(body_markdown, 'sha256')) STORED
8. `created_at` TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
9. `edited_at` TIMESTAMPTZ [Already created by KB-P1-09]
10. `deleted_at` TIMESTAMPTZ [Already created by KB-P1-09]

Therefore, migration `p3_05_comment_threads_reactions`:
- Did **not** add any columns to `issue_comments` because `parent_comment_id`, `edited_at`, and `deleted_at` were already established by KB-P1-09.
- Created `comment_reactions(comment_id, principal_id, emoji, created_at)` with `ENABLE` + `FORCE ROW LEVEL SECURITY`.
- Configured RLS policies `comment_reactions_select_rls`, `comment_reactions_insert_rls`, `comment_reactions_delete_rls` delegating to parent issue `VIEW` capability with write check on `principal_id`.
- Granted permissions to `kanban_app` (SELECT, INSERT, UPDATE, DELETE) and `app_rls_reader` (SELECT).

## Implemented API Endpoints (Mounted under `/api/v1`)
1. `GET /api/v1/issues/{issue_ref}/comments?cursor=&limit=` (VIEW required, keyset pagination, nested replies up to 200)
2. `POST /api/v1/issues/{issue_ref}/comments` (COMMENT required, 201 + ETag + Location permalink, mention access warning gate)
3. `PATCH /api/v1/comments/{comment_id}` (Author-only, 200 + ETag, If-Match required, mention access warning gate)
4. `DELETE /api/v1/comments/{comment_id}` (Author or project ADMIN, 204 soft-delete)
5. `PUT /api/v1/comments/{comment_id}/reactions/{emoji}` (COMMENT required, 200 idempotent, NFC 8-emoji allowlist)
6. `DELETE /api/v1/comments/{comment_id}/reactions/{emoji}` (COMMENT required, 204 idempotent)

## Quality and Verification Summary
- **Unit Tests**: 11/11 passed across `kanban/tests/api/test_comments.py` and `kanban/tests/services/test_mentions.py`.
- **Test Coverage**: 96.86% line + branch coverage (exceeds >= 95% threshold).
- **Anti-Enumeration & Zero ACL Widening**: Mentions never insert rows into `resource_acl_entries`. Unreadable entities return 404.
- **Contract Samples**: 7 verified exchanges in `docs/qa/KANBA-85/contract-sample.json`.
- **Schema Dump**: Verified in `docs/qa/KANBA-85/schema-dump.sql`.
