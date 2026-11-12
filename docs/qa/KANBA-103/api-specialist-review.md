# API Specialist Gate Review: KANBA-103 (KB-P3-15)

- **Ticket**: `KANBA-103` (`KB-P3-15`: Stickies API, complexity heuristic, >=1.5x snooze & atomic ACL-preserving promote-to-doc)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist)
- **Branch**: `feat/KANBA-103` (`HEAD: f9ddcfe`)
- **Worktree**: `/tmp/kb-wt-KANBA-103`
- **Scope**: `kanban/api/v1/stickies.py`, `kanban/api/v1/schemas/stickies.py`, `kanban/services/stickies.py`, `kanban/services/sticky_heuristic.py`, `kanban/services/activity.py`

---

### 1. Architectural & Security Evaluation

#### A. REST API Endpoints & Timing Equalization (S3.4, S12.2)
- All mutating routes (`create_sticky`, `update_sticky`, `delete_sticky`, `snooze_sticky_promotion`, `promote_sticky_to_doc`, `unarchive_sticky_copy`) are wrapped in `timing_floor(floor_ms=25.0)`.
- Retrieval endpoints (`GET /projects/{project_ref}/stickies`, `GET /stickies`, `GET /stickies/{id}`) enforce strict capability checks (`VIEW` on project/workspace/sticky). Nonexistent or unreadable stickies return uniform HTTP 404 responses with zero principal or object enumeration side channels.
- Workspace listing implements HMAC/keyset pagination with cursor validation (`422 INVALID_CURSOR`).
- Activity events are mapped to `ActivityCategory.HISTORY`: `STICKY_CREATED`, `STICKY_UPDATED`, `STICKY_RECOLORED`, `STICKY_PROMOTION_SNOOZED`, `STICKY_PROMOTED_TO_DOC`, `STICKY_UNARCHIVED_COPY`, `STICKY_TRASHED`.

#### B. Optimistic Concurrency & ETag Semantics (S1.3, S7.2)
- ETag values are generated as quoted SHA-256 digests over sticky content.
- `GET /stickies/{id}` honors `If-None-Match`, returning HTTP 304 Not Modified when matching.
- `PATCH /stickies/{id}` requires an `If-Match` header (`428 PRECONDITION_REQUIRED` when absent, `412 PRECONDITION_FAILED` on conflict).
- Promoted stickies reject body modifications with HTTP 409 `STICKY_PROMOTED_READONLY`.

#### C. Complexity Heuristics & Integer Snooze Math (S8.1, S8.2)
- `evaluate_sticky_promotion` parses Markdown line-by-line outside fenced code blocks, correctly isolating inner code constructs:
  1. `char_length`: `len(body_markdown) > 600` (code points).
  2. `line_count`: `line_count > 10`.
  3. `headings`: ATX headings count (`^#{1,6}\s+\S`) `>= 2` outside fences.
  4. `structured_block`: GFM table delimiter matching (`| --- |`), Mermaid diagram fences (` ```mermaid `), SVG image references, and code fences with `> 6` inner lines.
  5. `outbound_links`: Markdown links, autolinks, and bracketed issue keys (`[KEY-123]`) `>= 3` outside fences.
- Snooze calculation implements exact integer arithmetic: `(char_len * 2) >= (snoozed_at_length * 3)` (`>= 1.5x`), completely avoiding floating-point rounding errors.
- Promoted stickies suppress promotion signals unconditionally (`recommended = False`, `triggers = []`, `snoozed = False`).

#### D. Atomic Promotion & Verbatim ACL Preservation (S8.2, S3.4)
- `promote_sticky_to_doc` executes under an explicit `SELECT ... FOR UPDATE` row lock on `stickies`, preventing double-promotion race conditions.
- Already-promoted notes immediately abort with HTTP 409 `ALREADY_PROMOTED`.
- Cross-scope protection: `parent_doc.project_id != sticky.project_id` rejects with HTTP 422 `CROSS_SCOPE_PROMOTION_FORBIDDEN`, ensuring project ACL inheritance cannot widen privileges across boundaries.
- Direct ACL preservation: all direct `resource_acl_entries` (`ALLOW` and `DENY` bitmasks across all principal types) on the source sticky are copied verbatim to the newly created `Doc` and `Page`. `effective_resource_access` (ERA) is re-materialized with identical access bitmasks.
- Universal Object Graph linkage: registers typed `object_links(PROMOTED_TO_DOC)` connecting the sticky to the newly minted Doc.
- Promoted stub serialization: returns `is_promoted_stub: true` with `promoted_to_doc` summary metadata.
- `unarchive_sticky_copy` clones content, color token, and ACL entries into a fresh unpromoted sticky note.

#### E. Input Validation & Boundaries
- Color tokens are strictly validated against the 6-color palette (`amber`, `mint`, `sky`, `lavender`, `coral`, `slate`); invalid values reject with HTTP 422.
- Maximum body size is capped at 65,536 bytes (`422 STICKY_TOO_LARGE`).
- Markdown content is normalized via `normalize_to_markdown()`.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 15/15 pytest passed in 5.72s across `test_sticky_heuristic.py` and `test_stickies.py`.
- **Coverage**: 96.88% branch+line across touched modules:
  - `kanban/api/v1/stickies.py`: 100%
  - `kanban/services/sticky_heuristic.py`: 100%
  - `kanban/services/stickies.py`: 95%
- **Static Analysis**: Ruff check clean, Ruff format clean, Mypy strict clean (196 files), ImportLinter 2/2 kept, License gate 0 violations, zero Unicode dashes.
- **Forensic Bundle**: Complete forensic proof bundle (`acl-preservation-proof.txt`, `contract-sample.json`, `unit-test-results.txt`, `build-check.txt`, `git-diff.patch`).

---

### 3. Gate Verdict

The Stickies API, Markdown complexity heuristic engine, integer snooze logic, atomic promote-to-doc pipeline, and verbatim ACL preservation comply with all architectural, security, and quality invariants.

**VERDICT: APPROVED**
