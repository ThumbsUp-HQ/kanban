# Clean-Room API Specialist Review: KAN-50

**Reviewer:** `api-spec-2` (Clean-Room Backend, API, MCP, and Security Specialist)  
**Date:** 2026-11-20  
**Branch:** `feat/KAN-50`  
**Commit:** `04bcefb53ec0932fb6c4a8d15090b6a37402db61`  
**Status:** APPROVED  

---

## 1. Executive Summary

This clean-room audit evaluates ticket **KAN-50** (`[KB-AGENT-SEQ-02] Expose skip_loaded_sequence_numbers in Project/Workspace REST API and Settings UI`) on branch `feat/KAN-50` at commit `04bcefb5`.

The implementation exposes the agent-safe sequence numbering toggle (`skip_loaded_sequence_numbers`) across the Project and Workspace Settings REST APIs and frontend settings surfaces. When enabled, culturally loaded and distracting issue sequence numbers (13, 69, 88, 404, 420, 666, 1337, 1488) are safely skipped during issue creation (implemented in KAN-49).

The audit confirms that:
1. REST schemas for Project creation, patching, and serialization expose `skip_loaded_sequence_numbers` cleanly.
2. Workspace-level default inheritance is implemented safely: omitting the setting on project creation inherits `workspace_settings.default_skip_loaded_sequence_numbers`, while explicit booleans override the default.
3. Activity ledger diffs accurately record changes to `skip_loaded_sequence_numbers` in `PROJECT_UPDATED` and `WORKSPACE_SETTINGS_UPDATED` events.
4. Sibling isolation is strictly observed: zero edits to `WorkspaceSettingsPage.tsx` (owned by `KAN-30-rc2`), and zero edits to sequence generation core (owned by `KAN-49`).
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
  * Verified: Omitted field (`None`) correctly queries `WorkspaceSettings` for the calling workspace.
- **Activity Ledger Diff Tracking**:
  * In `update_project`:
    ```python
    if "skip_loaded_sequence_numbers" in fields ...:
        changes["skip_loaded_sequence_numbers"] = {
            "old": project.skip_loaded_sequence_numbers,
            "new": body.skip_loaded_sequence_numbers,
        }
        project.skip_loaded_sequence_numbers = body.skip_loaded_sequence_numbers
    ```
    Recorded under `ActivityEventType.PROJECT_UPDATED`.
  * In `update_workspace_settings`:
    Recorded under `ActivityEventType.WORKSPACE_SETTINGS_UPDATED`.

### 2.3. Sibling Boundaries & Conflict Avoidance
- Sibling worker `b-kan30-rc2` touched `WorkspaceSettingsPage.tsx` and `destructive.py`. `b-kan50` made zero edits to `WorkspaceSettingsPage.tsx`.
- Sibling worker `b-kan49` created migration `p4_24_agent_safe_sequences` and sequence calculation functions. `b-kan50` builds upon the existing database schema without introducing migration conflicts.
- Untracked files `.backup_schedule.json` and `backups/` strictly unstaged.

---

## 3. Test Suites, Coverage, and Static Analysis Verification

### 3.1. Backend Pytest Suite
- Command: `uv run pytest kanban/tests/api/test_projects.py kanban/tests/api/test_workspace_settings.py --cov=kanban/services/projects --cov=kanban/api/v1/schemas/projects --cov=kanban/api/v1/admin/workspace_settings --cov-report=term-missing`
- Results: 28/28 tests passed in 19.79s.
- Coverage Breakdown on Touched Files:
  * `kanban/services/projects.py`: 99% (194/195 statements, 1 missed line 262)
  * `kanban/api/v1/schemas/projects.py`: 100% (67/67 statements)
  * `kanban/api/v1/admin/workspace_settings.py`: 95% (161/163 statements)
- Validated scenarios:
  1. Default workspace inheritance when `skip_loaded_sequence_numbers` is omitted.
  2. Explicit `skip_loaded_sequence_numbers=True` override on `POST /api/v1/projects`.
  3. Toggle via `PATCH /api/v1/projects/{key}` and activity diff recording.
  4. End-to-end REST sequence skipping (skipping 13 to 14 with `SEQUENCE_SKIPPED` ledger event).
  5. GET and PATCH on `/api/v1/admin/workspace-settings` for `default_skip_loaded_sequence_numbers`.

### 3.2. Frontend Vitest Suite
- Results: 58/58 unit tests passed across 4 test files in 4.45s with 0 `act(...)` warnings.
- Coverage:
  * `CreateProjectModal.tsx`: 100% statements, 91.83% branch, 100% lines
  * `ProjectSettingsPage.tsx`: 99.55% statements, 95.45% branch, 100% lines
  * `emojiRegistry.ts`: 100% across statements, branches, functions, lines
- `cssTokensAudit.test.ts`: 4/4 passed (0 inline JSX style properties).

### 3.3. Static Gates & Security Checks
- `kanban-ctl db check-migrations`: All 63 migrations valid, single head `p4_24_agent_safe_sequences`.
- `uv run ruff check`: Clean (All checks passed).
- `uv run ruff format --check`: Clean (1007 files already formatted).
- `uv run mypy`: Clean (Success: 999 source files).
- `uv run lint-imports`: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database`).
- `tsc -b --noEmit`: Clean (0 errors).
- `eslint . --max-warnings 0`: Clean (0 warnings).
- `vite build`: Production build clean in 1.14s (720 modules).
- `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes across codebase and wiki).

---

## 4. Security & Architecture Invariants

| Check / Requirement | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Workspace Boundary** | Query scoped to caller workspace | `where(WorkspaceSettings.workspace_id == caller.workspace_id)` | PASS |
| **Inheritance Safety** | Omitted project setting inherits workspace default | Fallback logic executes when `body.skip_loaded_sequence_numbers is None` | PASS |
| **Activity Ledger** | Modifying setting emits audit record | Diffs recorded in `PROJECT_UPDATED` and `WORKSPACE_SETTINGS_UPDATED` | PASS |
| **Emoji Registry** | Preserves 21-key core invariant | Added to `EXTENDED_EMOJI_REGISTRY` (`agentSafeNumbering`: '🔢') | PASS |
| **Import Layering** | Unidirectional module layering | `agent -> mcp -> kanban -> database` maintained | PASS |
| **Typography Standards** | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 5. Certification Signoff

STATUS: APPROVED

All REST endpoints, schemas, service inheritance logic, activity ledger diffs, and unit tests for KAN-50 have been audited and certified. Sibling boundaries are respected, and test coverage exceeds 95% on all touched files. KAN-50 is certified ready for reality-checker QA gate on `feat/KAN-50`.
