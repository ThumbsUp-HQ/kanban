# Reality-Checker Audit Note: KANBA-76 (KB-P3-02)

## Architectural Scope & Workflow Implementation
This ticket (`KANBA-76` / `KB-P3-02`: `[Phase 3 / API] Issues CRUD API with description ETag / If-Match concurrency`) implements the full issues REST API with strong description ETag concurrency, keyset pagination, and fine-grained activity logging:

1. **Target Files**:
   - `kanban/api/v1/issues.py`: 4 REST endpoints mounted on `build_v1_router()` wrapped with `timing_floor(floor_ms=25.0)`.
   - `kanban/api/v1/schemas/issues.py`: Pydantic request/response schemas with `ConfigDict(extra="forbid")`, supporting `NormalParentSummary` and `RestrictedParentSummary`.
   - `kanban/services/issues.py`: Full issues service logic handling sequence allocation via `objects_allocate_sequence`, Base-62 initial board rank calculation (`"a" + base62(seq).rjust(6, "0")`), parent DAG cycle/depth validation, exclusive label group replacement, project module defaults, RLS security, and scalar/description/state/label activity ledger emission.
   - `kanban/services/issue_keys.py`: `resolve_issue_ref()` resolving human-readable `<IDENTIFIER>-<sequence_id>` or UUID strings under RLS.
   - `kanban/services/activity.py`: Added 5 issue event types (`ISSUE_CREATED`, `ISSUE_FIELD_CHANGED`, `ISSUE_DESCRIPTION_CHANGED`, `ISSUE_STATE_CHANGED`, `ISSUE_LABELS_CHANGED`).
   - `kanban/api/problems.py`: Added `current_etag`, `field`, and `candidates` problem payload attributes.

2. **Concurrency & Security Invariants**:
   - **ETag & Preconditions**: Strong `ETag: "<lowercase sha256 hex>"`. Description patches without `If-Match` reject with `428 PRECONDITION_REQUIRED`. Stale ETags reject with `412 PRECONDITION_FAILED` carrying `current_etag`. Concurrency check runs atomically in DB (`UPDATE ... WHERE id=:id AND description_sha256=:expected`), eliminating TOCTOU race windows.
   - **Restricted Parent Masking**: If a user lacks `VIEW` permission on a parent issue, it serializes strictly as `{"restricted": true, "label": "🔒 Restricted Parent Issue"}` with zero ID, key, or summary leakage.
   - **Sanitization**: Descriptions pass through `normalize_to_markdown()`, stripping hidden HTML and untrusted payloads; summaries strip zero-width characters and enforce 1..500 length bounds.
   - **Exclusive Label Groups**: Requesting two labels in the same exclusive group returns `422 EXCLUSIVE_GROUP_CONFLICT`; patching with a new label from an exclusive group replaces the existing label from that group.

3. **Verification & Quality Status**:
   - **Unit Tests**: 15/15 passed in 14.80s with **99.17%** branch + line coverage (`kanban.api.v1.issues` 100%, `kanban.services.issue_keys` 100%, `kanban.services.issues` 99%).
   - **Static Checks**: Ruff check clean, Ruff format clean, Mypy strict clean (122 source files), Lint-imports clean (2 kept, 0 broken), Zero non-ASCII dashes repo-wide.
   - **Contract Proof**: `contract-sample.json` captures all 7 required HTTP wire exchanges (`create_issue_201`, `get_issue_304`, `patch_description_428`, `patch_description_412`, `get_unreadable_issue_404`, `create_invalid_parent_422`, `get_restricted_parent_200`).
