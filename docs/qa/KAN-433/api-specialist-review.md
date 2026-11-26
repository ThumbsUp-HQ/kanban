# API Specialist Review - KAN-433

**Target:** `KAN-433` - Persist `system_instructions_md` in Agent Definitions API and Stop Infinite `/api/v1/auth/session` Request Storm on `/workspaces/settings/agents`
**Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan433-943bd920` (branch `fix/KAN-433-agent-instructions-and-session-storm`, base `7c5d632c`)
**Reviewer Role:** API Specialist (`backend-architect`)

---

## 1. Scope & Files Verified

- `docs/qa/KAN-433/git-diff.patch` (lines 1-1212)
- `kanban/api/v1/agent_definitions.py` (lines 1-331)
- `kanban/agents/service.py` (lines 1-375)
- `kanban/agents/schemas.py` (lines 1-287)
- `database/models/agent_definition.py` (lines 1-64)
- `database/session.py` (lines 1-174)
- `kanban/api/deps.py` (lines 1-234)
- `kanban/web/src/api/client.ts` (lines 1-476)
- `kanban/web/src/features/admin/AdminStudioSubnav.tsx` (lines 1-140)
- `kanban/tests/api/test_agent_definitions.py` (lines 1-196)
- `kanban/web/src/api/__tests__/websudoReplay.test.tsx` (lines 1010-1070)
- `docs/qa/KAN-433/unit-test-results.txt` (lines 1-89)
- `docs/qa/KAN-433/build-check.txt` (lines 1-39)

---

## 2. Explicit Transaction Commit Verification (`kanban/api/v1/agent_definitions.py`)

Verified why explicit commits were required: `get_rls_session` (`kanban/api/deps.py` + `database/session.py`) yields `RLSAsyncSession` and runs `await sess.commit()` only in its dependency teardown block after the endpoint returns, which can race with immediate follow-up `GET` requests from the frontend (`refreshAgents()`).

All mutating routes in both `router` and `admin_router` now execute `await session.commit()` before returning the HTTP response:

- **Workspace `router`:**
  - `POST /workspaces/{workspace}/agent-definitions` (`create_agent_definition`, lines 53-64): calls `AgentDefinitionService.create(...)`, executes `await session.commit()` (line 62), sets `Location` header, and returns `result`.
  - `PATCH /agent-definitions/{agent}` (`patch_agent_definition`, lines 104-114): calls `AgentDefinitionService.patch(...)`, executes `await session.commit()` (line 113) inside `timing_floor(floor_ms=25.0)`, and returns `result`.
  - `DELETE /agent-definitions/{agent}` (`delete_agent_definition`, lines 122-131): calls `AgentDefinitionService.delete(...)`, executes `await session.commit()` (line 130) inside `timing_floor(floor_ms=25.0)`, and returns `Response(status_code=status.HTTP_204_NO_CONTENT)`.
- **Admin `admin_router` (`/admin/agent-definitions`):**
  - `POST ""` (`admin_create_agent_definition`, lines 269-279): calls `AgentDefinitionService.create(...)`, executes `await session.commit()` (line 277), sets `Location` header, and returns `result`.
  - `PATCH "/{agent}"` (`admin_patch_agent_definition`, lines 291-300): calls `AgentDefinitionService.patch(...)`, executes `await session.commit()` (line 299), and returns `result`.
  - `DELETE "/{agent}"` (`admin_delete_agent_definition`, lines 304-310): calls `AgentDefinitionService.delete(...)`, executes `await session.commit()` (line 309), and returns `Response(status_code=status.HTTP_204_NO_CONTENT)`.
- **Non-mutating routes:** `list_agent_definitions`, `get_agent_definition`, `validate_agent_definition`, `admin_list_agent_definitions`, `admin_get_agent_definition`, and `admin_validate_agent_definition` perform read/validation operations only and require no commit.

---

## 3. `system_instructions_md` Persistence & Round-Trip Verification

- **Schema (`kanban/agents/schemas.py`):**
  - `AgentDefinitionCreate.system_instructions_md` (line 44) and `AgentDefinitionPatch.system_instructions_md` (line 196) accept `system_instructions_md`, validate UTF-8 encoding (rejecting surrogates with HTTP 422 `CLI_ARGS_INVALID`), enforce `MAX_INSTRUCTIONS_BYTES = 65536`, and canonicalize via `normalize_to_markdown`.
  - `AgentDefinitionResponse.system_instructions_md` (line 286) exposes the stored string.
- **Service & ORM (`kanban/agents/service.py`, `database/models/agent_definition.py`):**
  - `AgentDefinitionService.create` (line 199) stores `payload.system_instructions_md` on `AgentDefinition`.
  - `_apply_patch_fields` (line 108) updates `agent.system_instructions_md` when `patch.system_instructions_md is not None`.
  - `_serialize` (line 71) populates `system_instructions_md=agent.system_instructions_md` for `create`, `get`, `list_definitions`, and `patch`.
- **Committed-DB API Integration Tests (`kanban/tests/api/test_agent_definitions.py`):**
  - `test_create_agent_definition_persists_custom_system_instructions` verifies round-trip durability across `POST /api/v1/workspaces/{workspace}/agent-definitions` -> `GET` list -> `GET` detail by UUID -> `GET` detail by slug -> `PATCH /api/v1/agent-definitions/{agent}` -> `GET` verify -> `DELETE` -> `GET` 404.
  - `test_admin_agent_definitions_commit_durability` verifies the same durability cycle across `/api/v1/admin/agent-definitions` under enrolled TOTP and `aal_level=2`.

---

## 4. `/api/v1/auth/session` Request Storm Suppression (`kanban/web/src/api/client.ts`)

- In `executeRequest` (`kanban/web/src/api/client.ts`):
  - Line 274 defines `const isAuthSession = path === '/api/v1/auth/session' || resolved.startsWith('/api/v1/auth/session');`.
  - Line 276 gates initial `kb:aal2-expires-at` event dispatch with `if (initialExpiresAt && !isAuthSession && typeof window !== 'undefined')`.
  - Line 336 gates post-step-up replay `kb:aal2-expires-at` event dispatch with `if (replayExpiresAt && !isAuthSession && typeof window !== 'undefined')`.
- **Non-regression on other routes:** All non-session routes (`isAuthSession === false`) continue to read `x-kb-aal2-expires-at` and dispatch `kb:aal2-expires-at` on both initial responses and AAL2 step-up replays.
- **Loop closure in consumer (`AdminStudioSubnav.tsx`, lines 82-100):** `onExpiresAt` no longer invokes `load()` (`GET /api/v1/auth/session`) and short-circuits state updates when `prev?.aal2_active && prev.aal2_expires_at === expiresAt`.
- **Unit Test Coverage:** `kanban/web/src/api/__tests__/websudoReplay.test.tsx` explicitly tests both `GET /api/v1/users/me` dispatching `kb:aal2-expires-at` (lines 1021-1042) and `GET /api/v1/auth/session` suppressing dispatch (lines 1044-1065).

---

## 5. Security Invariants Check

- **RLS Enforcement:** All routes inject `Session` via `Depends(get_rls_session)` (`kanban/api/deps.py`), which binds `RLSContext` via `RLSSessionFactory` (`database/session.py`). `AgentDefinitionService` additionally scopes queries by `AgentDefinition.workspace_id == caller.workspace_id`, verifies workspace membership (`verify_workspace`), and enforces `app_principal_has_role` (`require_admin_role`).
- **Admin AAL2 Dependency Protection:** `admin_router` (`kanban/api/v1/agent_definitions.py`, lines 248-253) declares `dependencies=[Depends(require_admin_aal2)]` at the router level and injects `AdminCaller = Annotated[PrincipalContext, Depends(require_admin_aal2)]` on all `/admin/agent-definitions*` endpoints.
- **Hostile Input Sanitization:** `AgentDefinitionCreate` and `AgentDefinitionPatch` validate UTF-8 (rejecting lone surrogates), enforce the 65536-byte limit, normalize markdown through `normalize_to_markdown`, enforce `ConfigDict(extra="forbid")`, validate `slug` against `^[a-z0-9][a-z0-9-]{1,62}$`, enforce `ALLOWED_MCP_TOOLS`, and run `validate_cli_args` against `BINARY_ALLOWLIST`.
- **Timing Equalization:** `get_agent_definition`, `patch_agent_definition`, `delete_agent_definition`, and `validate_agent_definition` preserve `async with timing_floor(floor_ms=25.0)` to prevent existence-oracle timing leaks.
- **Zero Unicode Em/En Dashes:** Inspected `docs/qa/KAN-433/git-diff.patch` (lines 1-1212) and the reviewed source files; zero `U+2014` em-dashes or `U+2013` en-dashes are present.

---

## 6. Observed Test & Build Results

- **Backend Pytest (`docs/qa/KAN-433/unit-test-results.txt`):** `kanban/tests/api/test_agent_definitions.py` - `2 passed in 1.13s`.
- **Frontend Vitest (`docs/qa/KAN-433/unit-test-results.txt`):** `vitest run src/features/admin-agents src/features/admin src/api` - `24` test files passed, `523` tests passed (including `src/api/client.test.ts`, `src/api/__tests__/websudoReplay.test.tsx`, `AgentDefinitionEditorDrawer.test.tsx`, and `AgentStudioPage.test.tsx`).
- **Static Checks & Build (`docs/qa/KAN-433/build-check.txt`):**
  - `ruff check`: `All checks passed!`
  - `ruff format --check`: `2878 files already formatted`
  - `mypy`: `Success: no issues found in 1373 source files`
  - `tsc -b --noEmit`: passed with 0 errors
  - `eslint . --max-warnings 0`: passed with 0 warnings
  - `vite build`: succeeded in `1.27s`
  - `NO DASHES CHECK`: clean (no matches reported)

---

## 7. Non-Blocking Observation

- In `kanban/web/src/api/client.ts` line 274, `resolved.startsWith('/api/v1/auth/session')` cleanly covers `/api/v1/auth/session` and `/api/v1/auth/session?...`. No sibling route sharing that prefix (such as `/api/v1/auth/session-*`) exists in the client surface today, though an exact path or `?/|` boundary match (`resolved === '/api/v1/auth/session' || resolved.startsWith('/api/v1/auth/session?')`) would be even stricter if future `/api/v1/auth/session-*` endpoints are ever added. Not a defect today.

Verdict: APPROVED
