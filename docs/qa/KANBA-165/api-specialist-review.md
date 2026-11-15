# API & Architecture Specialist Review - KANBA-165 (`KB-QA-04`)

- **Ticket:** `KANBA-165` (`KB-QA-04`: Live Issue Detail Drawer & Full-Screen Surface Persistence, ETag Concurrency & Properties Rail State Resolution)
- **Specialist Reviewer:** `arch-reviewer` (Swarm API & Architecture Specialist Gate Auditor)
- **Date:** 2026-11-15
- **Status:** **APPROVED (Grade A)**

---

## 1. Scope Audited

- `kanban/web/src/features/drawer/IssueSurface.tsx`
- `kanban/web/src/features/drawer/IssueSurface.css`
- `kanban/web/src/features/drawer/IssueSurface.test.tsx`
- `kanban/web/src/features/views/viewsApi.ts`

---

## 2. API Wire Contracts & Security Invariant Verification

1. **Live Issue Detail Normalization (`normalizeIssueDetail` in `IssueSurface.tsx`):**
   - When `IssueSurface` fetches `GET /api/v1/issues/{issue_key}` via `apiClient.get`, `normalizeIssueDetail` enriches the backend `IssueResponse` payload with `project_key` (derived from `raw.project_key`, route `projectKey`, or `key.split('-')[0]`), `object_id` (`raw.object_id ?? raw.id`), `etag` (`raw.etag ?? "\"<description_sha256>\""`), `label_ids`, and default capabilities while returning unit-test fixtures that already carry `project_key`/`object_id`/`etag` untouched.
   - Uniformly maps `403` and `404` `ApiProblem` errors to `"Issue ${issueKey} was not found or you do not have access."` without retry button, preventing cross-tenant existence leakage (S3.4).

2. **Optimistic Concurrency & Persistent Description Editing (`IssueSurface.tsx`):**
   - `handleSaveDescription` updates the TanStack Query cache optimistically and dispatches `PATCH /api/v1/issues/{issue_key}` via `apiClient.patch` with `{ description_markdown: nextMarkdown }` and `ifMatch: currentIssue.etag` (`If-Match` header).
   - Upon `200 OK`, it updates the query cache with the normalized server response (including the new `description_sha256` / `etag`) and dispatches `kb:issue-updated` so background board/list views stay synchronized.

3. **Live Workflow State Resolution for `PropertiesRail` (`IssueSurface.tsx`):**
   - Fetches `GET /api/v1/projects/${resolvedProjectForAux}/states` via `fetchProjectStates` and passes `projectMetadata.states` and `onIssueUpdate` to `RailSlotWithMeta`, enabling state transitions, priority updates, assignee changes, label updates, and comment creation in both peek drawer (`?peek=KAN-1`) and full-screen (`/projects/KAN/issues/KAN-1`) modes while preserving the zero-remount (`data-mount-id` / `data-mount-seq`) invariant.

---

## 3. Verification Proof Summary

- **Unit & Integration Tests:** `16 passed` test files (`159 passed` tests) in `docs/qa/KANBA-165/unit-test-results.txt`.
- **Static Analysis & Build:** `eslint --max-warnings 0`, `tsc -b --noEmit`, and `vite build` exit `0` in `docs/qa/KANBA-165/build-check.txt`.
- **Verdict:** **APPROVED** for merge and `reality-checker` audit.
