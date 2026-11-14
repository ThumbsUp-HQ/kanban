# API Specialist Gate Review: KANBA-125 (KB-P3-44)

- **Ticket**: `KANBA-125` (`KB-P3-44`: `[Phase 3 / Frontend] Ticket audit & activity drawer (8j): 4 tabs (All, Comments, History, Gates), comment thread, reactions & hash chain inspect`)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist Auditor)
- **Worktree**: `/tmp/kb-wt-KANBA-125`
- **Branch**: `feat/KANBA-125`
- **Audit Date**: 2026-11-12
- **Applicable Specifications**: Section 7.2 Item 8j (Activity Feed API & Keyset Pagination), Section 7.2 Item 8k (Threaded Comments, Reactions, Concurrency & Mention Access Checks), Section 3.4 (Anti-Enumeration & Zero Silent ACL Escalation)

---

## 1. Executive Summary

A comprehensive architectural and API contract audit of `KANBA-125` was conducted across frontend API consumer clients, error parsing, concurrency guards, mention warning handling, and reaction encoding in `/tmp/kb-wt-KANBA-125`.

The implementation integrates seamlessly with backend endpoints established under `KB-P3-13` (Activity feed), `KB-P3-05` (Threaded comments & reactions), and `KB-P3-03` (Assignee suggestions):
1. **Activity Feed & Keyset Pagination (`activityApi.ts`, S7.2 8j)**:
   - `fetchActivity(issueKey, tab, cursor)` queries `GET /api/v1/issues/{key}/activity?tab=<tab>&cursor=<cursor>` with `Accept: application/json`.
   - Cursor-based pagination correctly forwards `next_cursor` tokens and renders an accessible `Load older activity` button without resetting feed state or remounting DOM trees.
   - All 4 filter tabs (`all`, `comments`, `history`, `gates`) correctly populate counts from `counts: { all, comments, history, gates }` and filter stream entries.
2. **Safe `@mention` Flow & Zero Silent ACL Widening (`409 MENTION_ACCESS_WARNING`, S3.4, S7.2 8k)**:
   - Autocomplete queries `GET /api/v1/projects/{projectKey}/assignee-suggestions?q=<prefix>&limit=10` scoped to project permissions, preventing cross-tenant or unauthenticated user discovery.
   - When a user submits `@maya` where `maya` lacks `VIEW` permissions, API responds with RFC 7807 problem details (`status: 409`, `code: 'MENTION_ACCESS_WARNING'`, `unauthorized_mentions: [{ handle, principal_id }]`).
   - The frontend preserves the user's draft text, maps `ApiProblem` data into `MentionAccessWarning`, and displays an inline alert banner.
   - Resubmission via `Post without granting access` transmits `acknowledge_mentions: [principal_id]`, which returns `201 Created` with `unnotified_mentions` documented on the response object. Zero ACLs are widened in the database.
3. **Concurrency Control & Optimistic Edit Guards (`ETag` / `If-Match`, S7.2 8k)**:
   - Author edit requests send `PATCH /api/v1/comments/{id}` with `If-Match: <etag>`.
   - On `412 Precondition Failed`, the inline editor remains open, prevents draft loss, and displays an inline conflict warning banner (`"This comment was edited elsewhere. Copy your changes and reload."`).
4. **Reactions Allowlist & URL Encoding (`KB-P3-05`)**:
   - Only the 8 frozen allowlist emojis (`👍`, `👎`, `😄`, `🎉`, `😕`, `❤️`, `🚀`, `👀`) can be selected.
   - Reaction endpoints use URL-encoded emoji path segments (`PUT /api/v1/comments/{id}/reactions/{encodeURIComponent(emoji)}` and `DELETE /api/v1/comments/{id}/reactions/{encodeURIComponent(emoji)}`), e.g., `%F0%9F%9A%80` for `🚀`.
   - Client manages optimistic increments and decrements, with rollback to previous state if the request fails.
5. **Payload Bounds & Error Handling**:
   - Comment body length is strictly bounded client-side to `1..262144` bytes before making network requests.
   - Error responses are parsed through `ApiProblem` mapping RFC 7807 details, titles, and status codes.

---

## 2. API Contract Verification Sample

All simulated exchanges documented in `docs/qa/KANBA-125/contract-sample.json` were audited and confirmed:
- `get_activity_tab_all_200`: Returns 4-category counts and items containing `AGENT_GATE` (`GATE_APPROVED`, `GATE_VETOED`) and `HISTORY` (`CREATOR_OVERRIDDEN`) records.
- `post_comment_unauthorized_mention_409`: Returns `409 Conflict` with `MENTION_ACCESS_WARNING` and unauthorized principal IDs.
- `post_comment_acknowledged_mention_201`: Resubmission with `acknowledge_mentions` returns `201 Created` and `etag`.
- `patch_comment_concurrency_conflict_412`: Stale ETag returns `412 Precondition Failed`.
- `patch_comment_success_200`: Valid ETag returns `200 OK` and updated ETag.
- `put_reaction_allowlist_rocket_200`: URL-encoded emoji `PUT` returns `200 OK`.
- `delete_reaction_allowlist_rocket_204`: URL-encoded emoji `DELETE` returns `204 No Content`.

---

## 3. Final Verdict

- **API Specialist Gate Decision**: **APPROVED**
- **Contract Compliance Grade**: **Grade A (100% compliant with S3.4, S7.2 8j/8k, KB-P3-13, KB-P3-05)**
- **Verification Signature**: `@arch-reviewer` (Systems/Backend Architect & API Specialist Auditor)
