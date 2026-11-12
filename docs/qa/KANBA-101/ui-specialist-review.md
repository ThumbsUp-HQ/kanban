# UI Specialist Gate Final Audit: APPROVED for KANBA-101 (KB-P3-09b)

- Auditor: ui-specialist (Swarm UI & UX Architecture Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-101`
- Branch: `feat/KANBA-101`
- Commit audited: `0a91a0a`
- Ticket: `KANBA-101` (`KB-P3-09b`: Delete with blast-radius preview, soft trash, restore & retention purge job)

---

### 1. Verification Matrix

| Dimension | Target | Observed | Verdict |
| :--- | :--- | :--- | :--- |
| Preview drives confirmation modal | Plain-text `summary_text` + exact counts | `summary_text` is built server-side from integer counts only (no user-controlled strings), with correct singular/plural (`1 sub-issue`, `1 inbound object_link`). Safe to render as a text node; zero HTML vector. | PASS |
| Structured counts for modal detail rows | `sub_issues_unparented`, `inbound_links_flagged`, `outbound_links`, `comments`, `attachments`, `retention_days` | All present in `BlastRadiusResponse` (`extra="forbid"`); counts are numbers only, never keys/ids of unreadable rows (no cross-tenant enumeration) | PASS |
| Delete bound to preview | `Kb-Blast-Hash` header, 428 when absent | `428 BLAST_HASH_REQUIRED` RFC 7807 body in contract sample | PASS |
| Stale-preview recovery | 412 with fresh preview | `412 BLAST_RADIUS_CHANGED` carries `current_preview` (full `BlastRadiusResponse` shape), so the modal can re-render updated counts and re-confirm without an extra GET | PASS |
| Trash list ergonomics | Keyset pagination, countdown data | `items[]` with `key`, `summary`, `deleted_at`, `purge_after`, `state`, `priority`, `capabilities`; `next_cursor` for infinite scroll; `limit` bounded 1..100 | PASS |
| Restore feedback | Return restored issue + sub-issue note | Returns `IssueResponse` with `note: "sub-issues remain unparented"` (verified in contract sample and `services/issue_delete.py:381`), allowing a toast that sets expectations | PASS |
| Expired restore | Clear error | `409 RETENTION_EXPIRED` RFC 7807, no traceback | PASS |
| Delete success payload | Undo / toast data | `{issue_key, deleted_at, purge_after}` supports "Moved to trash, restorable until <date>" toast | PASS |
| CSP / client safety | No inline style, no raw HTML | Pure JSON API; no HTML fields introduced | PASS |
| Screenshots | N/A - Non-UI Ticket | Confirmed per ticket proof item 8 | PASS |
| Typography | ASCII hyphens only | Zero U+2014 / U+2013 in changed source and QA files | PASS |
| Tests | >= 95% coverage | 14 passed, 96.61% branch+line | PASS |

---

### 2. Consumer UX Guidance (for the future frontend ticket)

1. **Confirmation modal:** call `GET /issues/{ref}/delete-preview`, render `summary_text` verbatim as a text node, and keep `blast_hash` in component state. The destructive button sends `Kb-Blast-Hash`.
2. **Stale hash:** on `412`, replace modal state with `current_preview` and show an inline "This issue changed since you opened this dialog" notice; require a fresh explicit confirm. Never auto-retry.
3. **Trash view:** display `purge_after` as a relative countdown; hide the Restore action for items lacking `DELETE` in `capabilities`.
4. **Restore toast:** surface `note` so users know children are not re-parented.

### 3. Non-Blocking Observation
- `cli-run.txt` shows an empty run (`issues_purged: 0`). The purge behavior itself is proven by unit tests (case 5, `INVALID_OBJECT_LINK_PURGED` and `ISSUE_PURGED` rows), so this is not a gate blocker. A populated fixture run is recommended next time.

---

### 4. Gate Sign-Off
The preview payload fully drives the confirmation modal text, the 412 recovery path is ergonomic, trash pagination carries the data a trash screen needs, and no information leaks across permission boundaries.

Verdict: APPROVED
