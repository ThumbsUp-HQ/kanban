# API Specialist Review: KANBA-214

- Ticket: KANBA-214 ([KB-AUDIT-08] Fix Project Danger Zone Trash 422 and Implement Project Trash/Restore, Server Permanent Purge, and Project Workflow States/WIP/Priorities/Labels Settings)
- Reviewer Persona: API Specialist / Backend Architect
- Status: APPROVED
- Date: 2026-11-19

## Summary of Backend & API Contract Changes
1. Endpoint: `GET /api/v1/projects/{project_ref}/trash-items`
   - Location: `kanban/api/v1/issue_delete.py`, `kanban/api/v1/schemas/issue_delete.py`, `kanban/services/issue_delete.py`
   - Functionality: Retrieves soft-deleted entities scoped to a project, including issues, cycles, modules, stickies, and docs/pages.
   - Parameters: Supports optional query parameter `kind` (`issue`, `cycle`, `module`, `sticky`, `doc`, `page`, or omitted for all).
   - Response Schema: `ProjectTrashItemsResponse` returning `items: list[ProjectTrashItemOut]` with `id`, `key`, `kind`, `title`, `deleted_at`, `purge_after`, and calculated `remaining_days`.
   - Security: Scoped strictly to project boundaries with `FORCE ROW LEVEL SECURITY` active; unauthorized tenants cannot query cross-project deleted entities.

2. Destructive Actions API Contract Alignment:
   - Request Endpoint: `POST /api/v1/admin/destructive:request`
     - Validated payload `{ target_kind: "project", target: project_key, mode: "trash" | "permanent_purge" }`.
     - Returns cryptographic `confirmation_token`, `confirm_phrase`, `expires_in_sec`, and structured `blast_summary`.
     - Prevents 422 Unprocessable Entity error caused by missing or invalid mode values.
   - Execution Endpoint: `POST /api/v1/admin/destructive:execute`
     - Validates `confirmation_token`, matching `confirm_phrase`, and optional audit `reason`.
     - Restricts `permanent_purge` mode to principals possessing `SERVER_ADMIN` capability.

3. Restore Actions API Contract:
   - Endpoint: `POST /api/v1/issues/{issue_key}/restore` and `POST /api/v1/admin/destructive:restore`
   - Validates CSRF token header (`X-CSRF-Token`) and restores soft-deleted entity back to active status, clearing `deleted_at` timestamp.

## Test Validation
- Backend Unit Tests: `kanban/tests/api/test_issue_delete.py` (8/8 passed in 8.52s).
- Covers soft-deletion, restoration, trash-items query with kind filtering, and permission enforcement.
- Clean database isolation verified under `tmpfs` PostgreSQL with `FORCE ROW LEVEL SECURITY`.

## Verdict
Approved with Grade A. Schema definitions, error handling, parameter validation, and RLS contracts are fully compliant with platform security standards.
