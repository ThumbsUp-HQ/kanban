# Reality-Checker Verification Packet: KANBA-67 (KB-P3-01a)

## Ticket Metadata
- Ticket ID: `KANBA-67`
- Spec Key: `KB-P3-01a`
- Title: `[Phase 3 / API] Project architect API (part a): projects CRUD, module defaults & shared activity/contract infrastructure`
- Epic: `KB-E3`
- Spec Sections: `7.2` (8c, 8f, 8p), `3.4` (access_manifest, 404-not-403), `12.2` (projects DDL)
- Dependencies: `KB-P2-11` (permission evaluator, OBO intersection, access_manifest serializer)
- Gates: `reality-checker` (Passive Forensic Mode), `api-specialist`, `ui-specialist`

---

## User Story
As a **Project Administrator using the web UI or an agent**, I need **REST endpoints to create, read, list and configure projects (including `modules_enabled`, `default_module_ids` and `auto_archive_days`)** so that **every later Phase 3 endpoint has a project container, a single activity-writing helper and a reusable contract-capture harness**.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** `kanban/api/v1/projects.py`, `kanban/api/v1/schemas/projects.py`, `kanban/services/projects.py`, `kanban/services/activity.py`, `kanban/tests/contract.py`, and `kanban/tests/api/conftest.py` exist and implement the 5 endpoints, `record_activity`, `register_activity_listener`, `emit_ephemeral_event`, `ActivityEventType`, and `ContractRecorder`.
- [x] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api/test_projects.py kanban/tests/services/test_activity.py kanban/tests/test_contract_recorder.py -q --cov=kanban.api.v1.projects --cov=kanban.services.projects --cov=kanban.services.activity --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with `0` failures and 99.29% coverage (surpassing the >= 95% mandate).
- [x] **Full Kanban Test Suite Passing:** `uv run pytest kanban/tests` runs cleanly with 231 passed in 19s.
- [x] **Build / Type / Lint Clean:** `uv run ruff check kanban && uv run ruff format --check kanban && uv run mypy --strict kanban database && uv run lint-imports && make license && uv run python -m scripts.check_no_dashes --all` all exit `0`.
- [x] **Contract Sample:** `docs/qa/KANBA-67/contract-sample.json` captured all 7 required exchanges: create `201`, get `200`, unreadable `404`, patch as viewer `403`, invalid identifier `422`, duplicate `409`, module defaults `200`.
- [x] **Specialist Gate Approvals:** Both `api-specialist-review.md` and `ui-specialist-review.md` exist and conclude with explicit `APPROVED` verdicts.
- [x] **No Forbidden Unicode Dashes:** Repository passes `uv run python -m scripts.check_no_dashes --all` with zero violations.
- [x] **Forensic Proof Packet Complete:** All required proof files exist under `docs/qa/KANBA-67/`.

---

## Mandatory Feature Unit Tests Matrix (7/7 Required Cases Covered across 21 Tests)

| Case | Category | Test Target | Verification Description |
| :--- | :--- | :--- | :--- |
| **Case 1** | Positive Create & Seed | `test_projects.py::test_case_1_admin_create_seeds_defaults_and_activity` | Workspace admin `POST /api/v1/projects` returns 201, `Location` header, 5 seeded states, 5 seeded priorities with `None` as default, one `PROJECT_CREATED` activity row. |
| **Case 2** | Security (Anti-Enumeration & Perms) | `test_projects.py::test_case_2_unreadable_404_and_viewer_patch_403` | User with no `VIEW` on project `SEC` receives 404 with body byte-identical to `GET /api/v1/projects/NOPE`; `VIEW`-only user `PATCH` receives 403 `INSUFFICIENT_CAPABILITY`. |
| **Case 3** | Validation & Conflict | `test_projects.py::test_case_3_validation_and_conflict` | Identifiers `kan`, `K`, `KANBANPROJECT1` return 422; duplicate identifier returns 409 `PROJECT_IDENTIFIER_TAKEN`; unknown body keys return 422. |
| **Case 4** | Boundaries | `test_projects.py::test_case_4_boundaries` | `auto_archive_days` 0 and 366 return 422; 1 and 365 succeed; `limit=0` and `limit=101` return 422. |
| **Case 5** | Module Rules | `test_projects.py::test_case_5_module_rules` | `PUT .../module-defaults` with `modules_enabled=false` returns 422 `MODULES_DISABLED`; foreign module UUID returns 422 `MODULE_NOT_IN_PROJECT`; disabling modules while in use returns 409 `MODULES_IN_USE`. |
| **Case 6** | Activity Helper & Listener | `test_activity.py::test_case_6a_payload_over_cap_raises`, `test_case_6b_raising_listener_rolls_back_insert`, `test_every_event_type_has_a_category` | Payload over 16384 bytes raises `ActivityPayloadTooLarge`; raising listener rolls back insert; all `ActivityEventType` members mapped in `EVENT_CATEGORY`. |
| **Case 7** | Contract Recorder Redaction | `test_contract_recorder.py::test_case_7_redacts_credentials_and_writes_valid_json` | Credential headers (`Cookie`, `Set-Cookie`, `X-CSRF-Token`, `Authorization`) are redacted to `"<redacted>"` and valid JSON is produced. |

---

## Technical Actions & Implementation Matrix

| Component | Target Location | Description |
| :--- | :--- | :--- |
| **Activity Service Layer** | `kanban/services/activity.py` | `ActivityCategory`, `ActivityEventType`, `EVENT_CATEGORY`, `record_activity` (16 KiB serialized JSON cap, hash-chained `append_activity`, fail-closed listeners within SAVEPOINT), `register_activity_listener`, `emit_ephemeral_event`. |
| **Project Schemas** | `kanban/api/v1/schemas/projects.py` | Pydantic v2 schemas: `ProjectCreate`, `ProjectPatch`, `ModuleDefaultsPut`, `ProjectResponse`, `ProjectList` with `extra="forbid"`, regex identifiers, trimmed names, bounded auto-archive days. |
| **Project Service Layer** | `kanban/services/projects.py` | Keyset pagination, `create_project` (admin gating, object registration, role binding, defaults, activity), `update_project` (immutable identifier, module-in-use guard, SHA-256 markdown diffs), `replace_module_defaults`, `get_project_or_404`. |
| **Project API Router** | `kanban/api/v1/projects.py` | 5 endpoints mounted at `/api/v1/projects` with 25.0ms timing floor on object retrieval and updates. |
| **Router Mount** | `kanban/api/v1/__init__.py` | Mounted `projects_router` into canonical v1 API router tree. |
| **Contract Recorder** | `kanban/tests/contract.py` | `ContractRecorder`, `redact_headers`, `KB_CONTRACT_OUT`, `KB_TICKET_ID`. |
| **Shared API Fixtures** | `kanban/tests/api/conftest.py` | Fixtures `api_env`, `as_principal`, `make_user`, `make_project`, `make_module`, `contract_recorder`. |
| **Coverage Concurrency** | `pyproject.toml` | Added `concurrency = ["greenlet", "thread"]` to enable coverage.py tracking across SQLAlchemy async greenlet frames. |

---

## Forensic Proof Artifacts in `docs/qa/KANBA-67/`
1. `git-diff.patch`: Complete unified git diff against base commit.
2. `unit-test-results.txt`: Test suite output and exit code for 21 target tests (99.29% coverage, EXIT: 0).
3. `build-check.txt`: Static analysis and build check results (ruff, format, mypy, lint-imports, license, check_no_dashes all EXIT: 0).
4. `contract-sample.json`: Captured HTTP wire exchanges for all 7 required paths.
5. `api-specialist-review.md`: Independent audit and approval from API Specialist (`@arch-reviewer`).
6. `ui-specialist-review.md`: Independent audit and approval from UI Specialist (`@ui-specialist`).
7. `message-to-reality-checker.md`: This forensic sign-off document.
