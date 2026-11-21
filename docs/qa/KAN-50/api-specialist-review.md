# Clean-Room API Specialist Review: KAN-50

- **Ticket:** KAN-50
- **Title:** [KB-AGENT-SEQ-02] Expose skip_loaded_sequence_numbers in Project/Workspace REST API and Settings UI
- **Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)  
- **Date:** 2026-11-20  
- **Target Directory:** `/home/adamoutler/kanban/docs/qa/KAN-50`
- **Branch:** `main` (commit `9b163f07`)  
- **Container Environment:** `http://127.0.0.1:18963` (container: `kanban-liveqa-3`)  
- **Live Stack Status:** `LIVE_STACK_VERDICT: PASS`  
- **Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates ticket **KAN-50** (`[KB-AGENT-SEQ-02] Expose skip_loaded_sequence_numbers in Project/Workspace REST API and Settings UI`) on branch `main` at commit `9b163f07`. The review incorporates empirical proof from zero-mock Live Full-Stack QA execution against container `kanban-liveqa-3` (`http://127.0.0.1:18963`, PostgreSQL 16 + FORCE RLS) documented in `docs/qa/KAN-50/live-fullstack-proof.txt`, visual screenshots in `docs/qa/KAN-50/screenshots/`, backend unit test and coverage reports (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

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
  * In `update_project`: records old and new values in `changes["skip_loaded_sequence_numbers"]` upon mutation.
  * In `update_workspace_settings`: records old and new values in `changes["default_skip_loaded_sequence_numbers"]`.

### 2.3. Frontend UX & Accessibility Touchpoints
- In `CreateProjectModal.tsx`: Added checkbox toggle with label and tooltip hint.
- In `ProjectSettingsPage.tsx`: Added project-level toggle with instantaneous update and undo support.
- In `WorkspaceSettingsPage.tsx`: Added workspace-level default toggle with admin-only controls.
- In `EmojiHint.tsx`: Fixed `.emoji-hint-popup` with `z-index: 10050` floating cleanly above modals (`z-index: 9999`). Placed hint button outside `<label>` to prevent click bubbling.

---

## 3. Test Suites & Coverage Verification

### 3.1. Backend API & Service Tests (`unit-test-results.txt`)
- Command: `python3 -c "import numpy, sys, pytest; sys.exit(pytest.main(['kanban/tests/api/test_projects.py', 'kanban/tests/api/test_workspace_settings.py', ...]))"`
- Results: 28/28 passed in 18.97s.
- Coverage Breakdown on Touched Files:
  * `kanban/api/v1/admin/workspace_settings.py`: 95%
  * `kanban/api/v1/projects.py`: 100%
  * `kanban/api/v1/schemas/projects.py`: 100%
  * `kanban/services/projects.py`: 99%
  * **TOTAL: 98% coverage across 477 statements**

### 3.2. Frontend Vitest Suite (`unit-test-results.txt`)
- Results: 96/96 unit tests passed across 5 test files in 4.47s with 0 `act(...)` warnings.
- Coverage Breakdown:
  * `CreateProjectModal.tsx`: 100% statements, 98.11% branch, 100% lines
  * `ProjectSettingsPage.tsx`: 99.78% statements, 95.11% branch, 100% lines
  * `WorkspaceSettingsPage.tsx`: 99.41% statements, 94.78% branch, 100% lines
  * `emojiRegistry.ts`: 100% across statements, branches, functions, lines
  * `cssTokensAudit.test.ts`: 4/4 passed (0 inline JSX style properties).
  * **TOTAL: 99.6% statements, 95.1% branch, 100% functions, 99.91% lines**

### 3.3. Static Quality Gates (Commit `9b163f07`)
- `uv run kanban-ctl db check-migrations`: Clean (All 63 migrations valid, single head: `p4_24_agent_safe_sequences`).
- `uv run ruff check .`: Clean across 2027 files.
- `uv run ruff format --check .`: Clean across 2027 files.
- `uv run mypy database kanban mcp agent`: Clean (Success: 997 source files).
- `uv run lint-imports`: Contracts: 2 kept, 0 broken (`agent -> mcp -> kanban -> database`).
- `pnpm --dir kanban/web run typecheck`: Clean (0 type errors).
- `pnpm --dir kanban/web run lint`: Clean (0 errors, 0 warnings).
- `pnpm --dir kanban/web run build`: Clean production build.
- `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes).

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

Ticket KAN-50 is fully verified on `main` at commit `9b163f07` against live container `kanban-liveqa-3` (`:18963`, `LIVE_STACK_VERDICT: PASS`). Project and workspace settings REST endpoints, default inheritance logic, activity ledger recording, settings UI controls, EmojiHint z-index elevation, and unit test suites are certified ready for reality-checker QA gate closure.
