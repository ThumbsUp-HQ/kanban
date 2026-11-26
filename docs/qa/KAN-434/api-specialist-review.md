# API Specialist Review - KAN-434

- **Ticket:** KAN-434 (`[BUG][ADMIN-AI-UI] Fix Empty Immediate Refetch After POST /ai-providers and New Work Item Description Editor Input Sync`)
- **Worktree / Branch:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan434-52f6dbd3` (`fix/KAN-434-ai-providers-refetch-and-quick-create-sync`, base `7c5d632c`)
- **Reviewer Role:** Backend Architect / API Specialist (`.agents/agents/backend-architect.md`)

## 1. Root Cause & Explicit Commit Lifecycle Verification

In `database/session.py` (`RLSSessionFactory.session`, lines 140-174), the `AsyncSession` yielded by `get_rls_session` (`kanban/api/deps.py:154-223`) normally commits inside the async context manager's `else` block after FastAPI dependency teardown. Dependency teardown runs after the route handler returns the HTTP response, creating a race window where a client receiving `201 Created` (or `200 OK` / `204 No Content`) and immediately issuing `GET /api/v1/workspaces/current/ai-providers` could execute against a separate DB connection before the mutating transaction committed.

Verified that `await session.commit()` now precedes HTTP response return across all **12 mutating route handlers** (13 decorated route paths) in `kanban/api/v1/admin/ai_providers.py`:

### `/admin/ai/*` Router (`prefix="/admin/ai"`, 6 mutating routes)
1. `PUT /admin/ai/providers/order` (`reorder_providers`) - `await session.commit()` at line 271, before `return [_to_public_config(config_map[uid]) for uid in body.ordered_ids]` (line 272).
2. `POST /admin/ai/providers` (`create_provider`) - `await session.commit()` at line 490, before setting `Location` header and returning `_to_public_config(config)` (lines 491-492).
3. `PATCH /admin/ai/providers/{provider_id}` (`update_provider`) - `await session.commit()` at line 571, before `return _to_public_config(updated)` (line 572).
4. `POST /admin/ai/providers/{provider_id}:disable` (`disable_provider`) - `await session.commit()` at line 610, before `return _to_public_config(disabled)` (line 611).
5. `DELETE /admin/ai/providers/{provider_id}` (`delete_provider`) - `await session.commit()` at line 650, before `return Response(status_code=status.HTTP_204_NO_CONTENT)` (line 651).
6. `PUT /admin/ai/budgets` (`set_budget`) - `await session.commit()` at line 753, before `return BudgetRecord(...)` (lines 754-760).

### `/workspaces/{workspace}/ai-providers` Router (`workspace_router`, 6 mutating handlers / 7 paths)
7. `POST /workspaces/{workspace}/ai-providers` (`workspace_create_provider`) - `await session.commit()` at line 889, before setting `Location` header and returning `_to_public_config(config)` (lines 890-891).
8. `PUT /workspaces/{workspace}/ai-providers/order` (`workspace_reorder_providers`) - `await session.commit()` at line 965, before `return [_to_public_config(config_map[uid]) for uid in body.ordered_ids]` (line 966).
9. `PUT /workspaces/{workspace}/ai-providers/budgets` (`workspace_set_budget`) - `await session.commit()` at line 1124, before `return BudgetRecord(...)` (lines 1125-1131).
10. `PATCH /workspaces/{workspace}/ai-providers/{provider_id}` (`workspace_update_provider`) - `await session.commit()` at line 1252, before `return _to_public_config(updated)` (line 1253).
11. `DELETE /workspaces/{workspace}/ai-providers/{provider_id}` (`workspace_delete_provider`) - `await session.commit()` at line 1294, before `return Response(status_code=status.HTTP_204_NO_CONTENT)` (line 1295).
12. `POST /workspaces/{workspace}/ai-providers/{provider_id}:disable` and `POST /workspaces/{workspace}/ai-providers/{provider_id}/disable` (`workspace_disable_provider`) - `await session.commit()` at line 1342, before `return _to_public_config(disabled)` (line 1343).

All remaining routes in `kanban/api/v1/admin/ai_providers.py` are read-only `GET` endpoints or non-mutating `POST` probe/connection-test endpoints. Furthermore, `RLSSessionFactory` configures `expire_on_commit=False` (`database/session.py:98`) and checks `if sess.in_transaction(): await sess.commit()` on exit (`database/session.py:167-168`), so post-commit serialization in `_to_public_config` and `BudgetRecord` triggers no lazy-load queries and dependency teardown avoids double-commit errors.

## 2. `workspace_list_providers`, `include_projects`, and Immediate Refetch Contract

- `workspace_list_providers` (`kanban/api/v1/admin/ai_providers.py:794-818`) now exposes `include_projects: Annotated[bool, Query()] = False` and invokes `service.list_configs(workspace_id=caller.workspace_id, project_id=project_id, include_projects=include_projects if project_id is None else True)`.
- In `kanban/ai_config/service.py` (`list_configs`, lines 494-509), when `project_id is None` and `include_projects=False`, `AIProviderConfig.project_id.is_(None)` is filtered cleanly; when `include_projects=True`, all workspace and project-scoped configs in the workspace are returned; when `project_id` is specified, `AIProviderConfig.project_id == project_id` is filtered.
- Frontend contract in `kanban/web/src/features/admin-ai/aiAdminApi.ts` (`fetchAiProviders`, lines 59-68) calls `GET /api/v1/workspaces/${workspace}/ai-providers` (with optional `?project_id=...`), matching the backend query parameter contract and `ProviderConfigPublic` schema.
- Integration test `kanban/tests/api/test_ai_providers_commit_sync.py` (`test_post_ai_provider_immediate_refetch_sync`, marked `pytest.mark.committed_db`) proves `POST /api/v1/workspaces/current/ai-providers` (`201 Created`) followed immediately by `GET /api/v1/workspaces/current/ai-providers` (`200 OK`) returns the newly created provider config, validates `?include_projects=false`, and verifies immediate persistence across `PATCH`, `GET /{provider_id}`, `:disable`, `DELETE`, and post-delete `GET`.

## 3. Security Invariants Audit

- **`require_admin_aal2` on `/admin/*`:** `router` (`kanban/api/v1/admin/ai_providers.py:45-49`) declares `dependencies=[Depends(require_admin_aal2)]` at the router level, reinforced by `Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]` (`line 51`) and `_assert_admin_for_scope` (`lines 121-175`) across every `/admin/ai/*` route. `workspace_router` enforces `get_principal`, `_verify_workspace`, and `_assert_admin_for_scope` on all workspace AI provider routes.
- **RLS Session Binding:** Every endpoint uses `Session = Annotated[AsyncSession, Depends(get_rls_session)]` (`line 52`), binding `RLSContext` via `RLSSessionFactory.session` (`database/session.py:140-174`) and `bind_rls_context` (`SET LOCAL`) inside the active transaction. Because `await session.commit()` occurs only after all DB writes and `record_activity(...)` calls, no unbound post-commit ORM queries execute.
- **Secret Redaction on `ProviderConfigPublic`:** `ProviderConfigPublic` (`kanban/api/v1/admin/ai_schemas.py:16-47`) enforces `extra="forbid"` and exposes only `api_key_set: bool`. `_to_public_config` (`kanban/api/v1/admin/ai_providers.py:90-105`) omits `wrapped_api_key`, `api_key_nonce`, `wrapped_dek`, and `dek_kid`, and safely reads `config.__dict__.get("wrapped_api_key")` to avoid triggering deferred-column lazy-loading on `AIProviderConfig` (`database/models/ai.py:80-82`) after commit.
- **Formatting & Hygiene:** Verified zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) in the reviewed patch and this review.

## 4. Verification Evidence Reviewed

- `docs/qa/KAN-434/git-diff.patch` (407 lines): scoped cleanly to `kanban/api/v1/admin/ai_providers.py` and frontend optimistic-cache / input-sync components.
- `docs/qa/KAN-434/unit-test-results.txt`: `kanban/tests/api/test_ai_providers_commit_sync.py` passed (`1 passed in 0.83s`); 5 Vitest files / 134 tests passed; touched frontend files all >= 95% line coverage (`AiProviderEditorDrawer.tsx` 99.62%, `AiStudioPage.tsx` 97.07%, `QuickCreateIssueModal.tsx` 96.29%).
- `docs/qa/KAN-434/build-check.txt`: ruff/mypy (`Success: no issues found in 2 source files`), `tsc -b --noEmit`, `eslint . --max-warnings 0`, and `vite build` all passed cleanly.

Verdict: APPROVED
