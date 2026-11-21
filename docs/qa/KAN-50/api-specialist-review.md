# Clean-Room API Specialist Review: KAN-50

- **Ticket:** KAN-50
- **Title:** [KB-AGENT-SEQ-02] Expose skip_loaded_sequence_numbers in Project/Workspace REST API and Settings UI
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)  
- **Date:** 2026-11-20  
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-50`
- **Branch:** `main` (commit `78074a1d`)  
- **Container Environment:** `http://127.0.0.1:18963` (container: `kanban-liveqa-3`)  
- **Live Stack Status:** `LIVE_STACK_VERDICT: PASS`  
- **Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates ticket **KAN-50** (`[KB-AGENT-SEQ-02] Expose skip_loaded_sequence_numbers in Project/Workspace REST API and Settings UI`) on branch `main` at commit `78074a1d`. The review incorporates empirical proof from zero-mock Live Full-Stack QA execution against container `kanban-liveqa-3` (`http://127.0.0.1:18963`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-50/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-50/screenshots/`, backend unit test and coverage reports (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The implementation exposes the agent-safe sequence numbering toggle (`skip_loaded_sequence_numbers`) across the Project and Workspace Settings REST APIs and frontend settings surfaces. When enabled, culturally loaded and distracting issue sequence numbers (13, 69, 88, 404, 420, 666, 1337, 1488) are safely skipped during issue creation (implemented in KAN-49).

The audit confirms that:
1. REST schemas for Project creation, patching, and serialization expose `skip_loaded_sequence_numbers` cleanly.
2. Workspace-level default inheritance is implemented safely: omitting the setting on project creation inherits `workspace_settings.default_skip_loaded_sequence_numbers`, while explicit booleans override the default.
3. Activity ledger diffs accurately record changes to `skip_loaded_sequence_numbers` in `PROJECT_UPDATED` and `WORKSPACE_SETTINGS_UPDATED` events.
4. Sibling isolation is strictly observed: zero edits to sequence generation core (owned by `KAN-49`).
5. All touched backend modules achieve >=95% unit test coverage, and all static gates pass with zero warnings and zero em/en-dashes.

---

## 2. Technical and Security Audit

### 2.1. Schema and Contract Parity
- **Project Schemas (`kanban/api/v1/schemas/projects.py`)**:
  * `ProjectCreate`: `skip_loaded_sequence_numbers: bool | None = Field(default=None, ...)`
  * `ProjectPatch`: `skip_loaded_sequence_numbers: bool | None = Field(default=None, ...)`
  * `ProjectResponse`: `skip_loaded_sequence_numbers: bool = Field(...)`
  * Additive and non-breaking for existing callers.
- **Workspace Settings Schemas (`kanban/api/v1/admin/workspace_settings.py`)**:
  * `WorkspaceSettingsResponse`: `default_skip_loaded_sequence_numbers: bool = False`
  * `WorkspaceSettingsUpdate`: `default_skip_loaded_sequence_numbers: bool | None = None`
  * Additive and backward-compatible.

### 2.2. Service Logic and Inheritance (`kanban/services/projects.py`)
- **Default Inheritance on Project Creation**:
  ```python
  skip_seq = body.skip_loaded_sequence_numbers
  if skip_seq is None:
      ws_settings_stmt = select(WorkspaceSettings.default_skip_loaded_sequence_numbers).where(
          WorkspaceSettings.workspace_id == caller.workspace_id
      )
      ws_skip = (await session.execute(ws_settings_stmt)).scalar_one_or_none()
      skip_seq = bool(ws_skip) if ws_skip is not None else False
  ```
  * Verified: Explicit `True` or `False` in `ProjectCreate` overrides workspace default.
  * Verified: Omitted field (`None`) correctly queries `WorkspaceSettings` for calling workspace.
- **Activity Ledger Diff Tracking**:
  * In `update_project`:
    ```python
    if "skip_loaded_sequence_numbers" in fields:
        changes["skip_loaded_sequence_numbers"] = {
            "old": project.skip_loaded_sequence_numbers,
            "new": body.skip_loaded_sequence_numbers,
        }
        project.skip_loaded_sequence_numbers = body.skip_loaded_sequence_numbers
    ```
    Recorded under `ActivityEventType.PROJECT_UPDATED`.
  * In `update_workspace_settings`:
    Recorded under `ActivityEventType.WORKSPACE_SETTINGS_UPDATED`.

### 2.3. Live Stack Execution on Container `kanban-liveqa-3` (`:18963`, Commit `78074a1d`)
1. **Immediate 0ms Workspace Settings Inheritance via REST:**
   - `PATCH /api/v1/admin/workspace-settings` (`{"default_skip_loaded_sequence_numbers": true}`) -> HTTP 200 OK.
   - Immediate 0ms `POST /api/v1/projects` (omitting `skip_loaded_sequence_numbers`) -> HTTP 201 Created with `skip_loaded_sequence_numbers=true` on the very first project creation.
2. **PATCH /api/v1/projects/SAFE & Activity Ledger Diffs:**
   - Toggled false -> true: `PROJECT_UPDATED` activity diff rows emitted in PostgreSQL `activity_records`:
     `56|PROJECT_UPDATED|{"changes": {"skip_loaded_sequence_numbers": {"new": false, "old": true}}}`
     `57|PROJECT_UPDATED|{"changes": {"skip_loaded_sequence_numbers": {"new": true, "old": false}}}`.
3. **WorkspaceSettingsPage UI + Reload Persistence + EmojiHint:**
   - Checkbox `[data-testid="workspace-default-skip-loaded-seq-checkbox"]` toggled ON, saved, reloaded, persisted checked.
   - `<EmojiHint kind="agentSafeNumbering" />` renders OUTSIDE `<label>` (`emojiOutsideLabel=true`) and opens popup cleanly across Desktop Light/Dark, Tablet, Mobile.
   - Load times: desktop-light 678ms, desktop-dark 706ms, tablet-light 681ms, mobile-light 697ms.
4. **CreateProjectModal UI Inheritance + EmojiHint z-index Layering:**
   - Pre-hydrated checked (true) from `WorkspaceSettings`.
   - EmojiHint renders OUTSIDE `<label>` and renders ON TOP OF modal scrim across all 4 viewports:
     `popupZIndex="10050" > scrimZIndex="9999"`, `occludedByModal=false` (`topElementTag="DIV.emoji-hint-popup-content"`).
   - Created project UISAF4 without touching checkbox -> HTTP 201 Created with `skip_loaded_sequence_numbers=true`.
5. **ProjectSettingsPage General Tab + Toggle Reload Persistence:**
   - Concise label + EmojiHint OUTSIDE `<label>`.
   - Toggled OFF -> saved -> reloaded -> persisted false; toggled ON -> saved -> reloaded -> persisted true.
   - Load times: desktop-light 834ms, desktop-dark 947ms, tablet-light 868ms, mobile-light 881ms.
   - Zero overflow, 0 console errors, 0 page errors, 0 bad responses.

---

## 3. Test Suites, Coverage, and Static Analysis Verification

### 3.1. Backend Pytest Suite
- Command: `uv run pytest kanban/tests/api/test_projects.py kanban/tests/api/test_workspace_settings.py --cov=kanban/services/projects --cov=kanban/api/v1/schemas/projects --cov=kanban/api/v1/admin/workspace_settings --cov-report=term-missing`
- Results: 28/28 tests passed in 19.79s.
- Coverage Breakdown on Touched Files:
  * `kanban/services/projects.py`: 99% (194/195 statements, 1 missed line 262)
  * `kanban/api/v1/schemas/projects.py`: 100% (67/67 statements)
  * `kanban/api/v1/admin/workspace_settings.py`: 95% (161/163 statements)

### 3.2. Frontend Vitest Suite
- Command: `pnpm --dir kanban/web exec vitest run src/components/emoji/emojiRegistry.test.ts src/features/projects/CreateProjectModal.test.tsx src/features/settings/__tests__/ProjectSettingsPage.test.tsx src/styles/__tests__/cssTokensAudit.test.ts --coverage`
- Results: 58/58 unit tests passed across 4 test files in 4.45s with 0 `act(...)` warnings.
- Coverage Breakdown:
  * `CreateProjectModal.tsx`: 100% statements, 91.83% branch, 100% lines
  * `ProjectSettingsPage.tsx`: 99.55% statements, 95.45% branch, 100% lines
  * `emojiRegistry.ts`: 100% across statements, branches, functions, lines
  * `cssTokensAudit.test.ts`: 4/4 passed (0 inline JSX style properties).

### 3.3. Static Quality Gates (Commit `78074a1d`)
- `uv run kanban-ctl db check-migrations`: Clean (All 63 migrations valid, single head: `p4_24_agent_safe_sequences`).
- `uv run ruff check .`: Clean across 2023 files.
- `uv run ruff format --check .`: Clean across 2023 files.
- `uv run mypy database kanban mcp agent`: Clean (Success: 995 source files).
- `uv run lint-imports`: Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- `pnpm --dir kanban/web run typecheck`: Clean (0 type errors).
- `pnpm --dir kanban/web run lint`: Clean (0 errors, 0 warnings).
- `pnpm --dir kanban/web run build`: Production bundle built in 1.15s.
- `python3 -m scripts.check_no_dashes --all` and `thumbs-up-kanban.wiki`: 0 forbidden dashes.

---

## 4. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **REST Schema Parity** | Expose optional boolean on create/patch | `ProjectCreate`, `ProjectPatch`, `ProjectResponse` | PASS |
| **Workspace Default Fallback** | Inherit from `workspace_settings` when omitted | SELECT `default_skip_loaded_sequence_numbers` | PASS |
| **Explicit Override** | Explicit true/false overrides workspace default | Checked in `create_project` | PASS |
| **Activity Ledger Diff** | Record old and new boolean values in changes | `PROJECT_UPDATED` & `WORKSPACE_SETTINGS_UPDATED` | PASS |
| **EmojiHint Z-Index** | Float above modal scrims (`z-index: 9999`) | `.emoji-hint-popup` set to `z-index: 10050` | PASS |
| **Label Structure** | EmojiHint placed outside `<label>` element | Prevents double toggle on hint click | PASS |
| **Unidirectional Layering** | `agent -> mcp -> kanban -> database` | Verified via `lint-imports` (2 kept, 0 broken) | PASS |
| **Style Compliance** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Certification Signoff

STATUS: APPROVED

Ticket KAN-50 is fully verified on `main` at commit `78074a1d` against live container `kanban-liveqa-3` (`:18963`, `LIVE_STACK_VERDICT: PASS`). Project and workspace settings REST endpoints, default inheritance logic, activity ledger recording, settings UI controls, EmojiHint z-index elevation, and unit test suites are certified ready for reality-checker QA gate closure.
