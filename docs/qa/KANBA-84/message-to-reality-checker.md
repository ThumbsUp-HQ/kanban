# Forensic Audit Context: KANBA-84 (KB-P3-04)

## Overview and Scope
- Ticket: `KANBA-84` (`KB-P3-04`: `[Phase 3 / API] Created-by admin override endpoint & provenance serializer`)
- Worktree: `/tmp/kb-wt-KANBA-84` on branch `feat/KANBA-84` (branched from `feat/KANBA-76`)
- Test Coverage: `kanban.api.v1.issue_provenance` (100.00%) and `kanban.services.issue_provenance` (100.00%), combined 100.00% statement and branch coverage (114/114 stmts, 28/28 branches).

## Implementation Summary
1. **Target Files**:
   - `kanban/api/v1/issue_provenance.py`: Registered `PATCH /api/v1/issues/{issue_ref}/created-by` endpoint wrapped in `timing_floor(floor_ms=25.0)`.
   - `kanban/api/v1/schemas/issue_provenance.py`: Pydantic models `IssueOverrideCreatorRequest`, `IssueProvenance`, `CreatorPrincipalSummary`, `RedactedCreatorSummary`, `CreatorSummary` (all with `extra="forbid"`).
   - `kanban/services/issue_provenance.py`: Core business logic implementing `resolve_creator_summary`, `build_issue_provenance`, and `override_issue_created_by`.
   - `kanban/api/v1/schemas/issues.py`: Extended `IssueResponse` to include `provenance: IssueProvenance`.
   - `kanban/services/issues.py`: Updated `serialize_issue` to populate `provenance = await build_issue_provenance(session, issue)`.
   - `kanban/services/activity.py`: Added `CREATOR_OVERRIDDEN` to `ActivityEventType` with category `HISTORY`.
   - `database/migrations/sql/p3_04_creator_override_reason.up.sql`: Replaced `issues_creator_provenance_bu` trigger function to include `'reason'`, `'old_created_by_id'`, and `'new_created_by_id'` in the `CREATOR_OVERRIDDEN` activity payload.
   - `database/migrations/sql/p3_04_creator_override_reason.down.sql`: Reverts trigger function back to `p1_07` baseline.
   - `database/migrations/versions/p3_04_creator_override_reason.py`: Chained Alembic revision from `p2_02_sessions`.
   - `database/tests/migrations/test_p3_04_migration.py`: Lifecycle migration test verifying upgrade -> downgrade -> upgrade.

2. **Authorization Order & Enforcement Invariants**:
   - (a) Lacks `VIEW` capability -> `404 NOT_FOUND` (timing equalized via `timing_floor`).
   - (b) Lacks `PROJECT_ADMIN` on project and `SERVER_ADMIN` -> `403 INSUFFICIENT_CAPABILITY`.
   - (c) Session `app.aal_level < 2` -> `403 AAL2_REQUIRED`.
   - Validation bounds: `reason` between 10 and 500 characters (`422 REASON_REQUIRED`); `created_by` active `USER` principal eligible to view the project (`422 CREATOR_NOT_ELIGIBLE`); unchanged creator (`422 CREATOR_UNCHANGED`).
   - RLS Transaction: Sets `SELECT set_config('app.override_reason', :reason, true)` then updates `issues`. Trigger function `issues_creator_provenance_bu` enforces admin role, sets `creator_modified_by_id`/`creator_modified_at`, preserves `original_created_by_id`, and writes the single `CREATOR_OVERRIDDEN` ledger entry. The API never writes a duplicate activity row.
   - Identity map refresh: After raw update, `session.refresh(issue)` ensures cached ORM attributes reflect database state before serialization.
   - Redaction per S3.4: Users outside caller visibility boundary serialize as `{"redacted": true, "label": "1 External Collaborator"}`.

3. **Specialist Review & Gate Status**:
   - `ui-specialist-review.md`: Dual specialist gate for UI ergonomics and frontend tooltip feeding (`🔄`).
   - `api-specialist-review.md`: Dual specialist gate for REST API schema and security authorization.
