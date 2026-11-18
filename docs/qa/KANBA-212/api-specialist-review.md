# API Specialist Review: KANBA-212

## Review Information
- **Ticket ID**: KANBA-212
- **Title**: Fix Issue GET ETag 304 Stale Cache, Fullscreen Issue Route (/projects/undefined 404s), Hardcoded Mock Options, and Drafts Publish 403
- **Reviewer**: API Specialist / Backend Architect
- **Date**: 2026-11-18
- **Status**: STATUS: APPROVED

## Scope of API Audit
Comprehensive audit of backend and client API contracts touched in KANBA-212:
1. `GET /api/v1/issues/:key` ETag 304 computation and response headers.
2. `Created by` override `@handle` resolution, RBAC validation, and activity history diff payload enrichment.
3. Optimistic locking `If-Match` header propagation and `412 Precondition Failed` / `428 Precondition Required` response handling.
4. Client API client safety (`railApi.ts`, `viewsApi.ts`) guarding against invalid project keys (`undefined`, empty).
5. CSRF protection and live state resolution during `/drafts` publish.
6. Project label creation API payload (`color_hex` requirement).

## Audit Findings

### 1. Issue GET ETag Computation (`kanban/services/issues.py`, `kanban/api/v1/issues.py`)
- The backend `compute_issue_etag` function now computes a SHA-256 composite digest covering all serialized issue properties:
  - `id`, `key`, `project_id`, `created_by_id`, `start_date`, `due_date`, `state_id`, `priority`, `assignees`, `cycle_id`, `module_ids`, `labels`, `board_rank`, `access_manifest`, `description_sha256`, and `updated_at`.
- Edits to non-description properties (such as priority, assignees, workflow states, or dates) now produce a distinct strong ETag value.
- Subsequent `GET` requests with `If-None-Match` accurately return `200 OK` with updated payload instead of stale `304 Not Modified`.
- `IssueResponse` schema includes the computed `etag: str | None`.

### 2. Creator Override and Activity Feed (`kanban/services/issue_provenance.py`, `kanban/services/activity_feed.py`)
- `resolve_creator_override` cleanly accepts `@handle`, plain `handle`, or UUID without triggering 422 Unprocessable Entity errors.
- Activity feed enrichment (`_enrich_creator_override_payload`) resolves creator IDs to human-readable handles (e.g., `from @admin to @member`), eliminating generic `from Unknown to Unknown` strings in history diffs.
- Non-admin callers cannot override creator identities; access control is strictly enforced.

### 3. Optimistic Locking Protocol
- Client sends current issue ETag in the `If-Match` header on description and property updates.
- If concurrent modifications occur, the server returns `412 Precondition Failed`. If `If-Match` is omitted when required, `428 Precondition Required` is returned.
- Frontend catches 412/428, surfaces an actionable conflict banner, preserves user draft input, and allows manual conflict resolution.

### 4. Client API Route Guards
- `railApi.ts` and `viewsApi.ts` explicitly guard against missing or invalid project keys (`!projectKey || projectKey === 'undefined'`), eliminating unwanted `/api/v1/projects/undefined/...` 404 requests.
- `viewsApi.ts` safely parses both array and object responses from `/api/v1/projects/:key/issues`.

### 5. Drafts Publish CSRF and State Resolution
- `DraftsWorkspaceView` in `routes.tsx` uses `apiFetch` (which automatically injects `X-CSRF-Token` from cookies/session), resolving 403 Forbidden errors.
- Live project workflow states and modules are resolved before publishing to map draft states to valid UUIDs.

### 6. Inline Label Creation
- Inline label creation includes `color_hex` (defaulting to `#3b82f6`), satisfying FastAPI `LabelCreate` schema constraints and eliminating 422 validation errors.

## Test and Code Quality Verification
- Pytest: 23 passed, 96% coverage across touched files (`kanban/api/v1/issues.py`, `kanban/services/issue_provenance.py`, `kanban/services/issues.py`).
- Vitest: 151 passed across 12 touched test files with 100% pass rate.
- Ruff: 0 lint errors.
- MyPy: 0 type errors across all touched source files.

## Final Verdict
STATUS: APPROVED. The API implementation is robust, secure, and adheres strictly to the architectural standards.
