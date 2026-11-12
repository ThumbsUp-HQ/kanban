---
id: KB-P3-01a
title: "[Phase 3 / API] Project architect API (part a): projects CRUD, module defaults & shared activity/contract infrastructure"
epic: KB-E3
depends_on: [KB-P2-11]
spec_sections: ["7.2", "3.4", "12.2"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: manifest row `KB-P3-01` is split into `KB-P3-01a` (projects, module defaults, shared API infrastructure) and `KB-P3-01b` (states, priorities, labels, WIP limits).

### User Story
As a **Project Administrator using the web UI or an agent**, I need **REST endpoints to create, read, list and configure projects (including `modules_enabled`, `default_module_ids` and `auto_archive_days`)** so that **every later Phase 3 endpoint has a project container, a single activity-writing helper and a reusable contract-capture harness**.

**Requirement Traceability:** Spec S7.2 `8c`, `8f`, `8p`; S3.4 (`access_manifest`, 404-not-403); S12.2 (`projects` DDL); requirements `#8f`, `#8p`, `#1` | **Dependencies:** `KB-P2-11`

### Scoped Technical Actions
1. **Target Files:**
   - `kanban/api/v1/projects.py` (router)
   - `kanban/api/v1/schemas/projects.py` (Pydantic v2 request/response models, `model_config = ConfigDict(extra="forbid")`)
   - `kanban/services/projects.py` (business logic, runs inside the KB-P2-01 `get_rls_session` transaction)
   - `kanban/services/activity.py` (shared activity helper used by every Phase 3 ticket)
   - `kanban/tests/contract.py` (shared `ContractRecorder`)
   - `kanban/tests/api/conftest.py` (shared fixtures `as_principal`, `make_user`, `make_project`, `contract_recorder`)
2. **Shared activity helper (`kanban/services/activity.py`):**
   - `class ActivityCategory(StrEnum)`: `COMMENT`, `HISTORY`, `GATE`, `SYSTEM`.
   - `class ActivityEventType(StrEnum)` with an attached category map `EVENT_CATEGORY: Final[Mapping[ActivityEventType, ActivityCategory]]`. This ticket registers: `PROJECT_CREATED`, `PROJECT_UPDATED`, `MODULE_DEFAULTS_CHANGED` (all `HISTORY`). Later tickets append members; a unit test asserts every member has a category.
   - `async def record_activity(session, *, workspace_id: UUID, object_id: UUID, actor_principal_id: UUID, event_type: ActivityEventType, payload: Mapping[str, JSONValue]) -> UUID` inserting one row into the KB-P1-12 `activity_records` table in the caller's transaction and returning the row id. Payload is size-capped at `16384` bytes of serialized JSON (raise `ActivityPayloadTooLarge`). Payloads MUST NOT contain Markdown bodies; bodies are referenced by `sha256` hex only.
   - In-transaction listener registry: `register_activity_listener(fn: Callable[[AsyncSession, ActivityEnvelope], Awaitable[None]]) -> None`, invoked after each `record_activity` insert in registration order. Also `async def emit_ephemeral_event(session, envelope: EphemeralEnvelope) -> None` that calls listeners without writing `activity_records` (used later for rank-only moves). Listener exceptions propagate and abort the transaction (fail closed).
3. **Endpoints (all JSON, base `/api/v1`, errors are RFC 7807 `application/problem+json` from KB-P2-01 with a stable `code` member):**

   | Method + Path | Capability | Success | Errors |
   | :-- | :-- | :-- | :-- |
   | `POST /api/v1/projects` | Workspace admin or `SERVER_ADMIN` role | `201` + `Location: /api/v1/projects/{identifier}` | `422 VALIDATION_FAILED`, `409 PROJECT_IDENTIFIER_TAKEN`, `403 INSUFFICIENT_CAPABILITY` |
   | `GET /api/v1/projects?cursor=&limit=` | `VIEW` (RLS filtered) | `200` | `422` bad cursor/limit |
   | `GET /api/v1/projects/{project_ref}` | `VIEW` | `200` | `404 NOT_FOUND` (unreadable or absent, identical body, KB-P2-01 jitter-equalized) |
   | `PATCH /api/v1/projects/{project_ref}` | `ADMIN` on project | `200` | `404`, `403 INSUFFICIENT_CAPABILITY` (readable but not admin), `422`, `409 MODULES_IN_USE` |
   | `PUT /api/v1/projects/{project_ref}/module-defaults` | `ADMIN` on project | `200` | `404`, `403`, `422 MODULES_DISABLED`, `422 MODULE_NOT_IN_PROJECT` |

   - `project_ref` accepts the `identifier` (`^[A-Z][A-Z0-9]{1,9}$`) or a UUID.
   - `limit` range `1..100`, default `50`; `cursor` is an opaque base64url string of `(identifier)`; any undecodable cursor returns `422 INVALID_CURSOR`.
   - Create body: `{"identifier": "KAN", "name": "Platform Core", "description_markdown": "...", "modules_enabled": false, "auto_archive_days": null}`. `name` `1..120` chars after `btrim`; `description_markdown` passed through `kanban.content.normalize` from KB-P2-13 only if KB-P2-13 is merged; otherwise stored after the DB `octet_length <= 524288` CHECK (map CHECK violation to `422 DESCRIPTION_TOO_LARGE`). `auto_archive_days` is `null` or `1..365`.
   - Create runs in one transaction: register `objects` row (`object_type='project'`, `canonical_key=identifier`), insert `projects`, seed workflow states `Backlog (backlog, default)`, `Todo (unstarted)`, `In Progress (started)`, `Done (completed)`, `Cancelled (cancelled)` and priorities `Urgent 🔥`, `High ⚡`, `Medium 🔹`, `Low 💤`, `None (is_default)` exactly per S7.2 `8c` (reuse the KB-P1-04 seeding function if it exists), grant creator project `ADMIN`, write `PROJECT_CREATED`.
   - `PATCH` allowed fields: `name`, `description_markdown`, `modules_enabled`, `auto_archive_days`. `identifier` is immutable (`422 IDENTIFIER_IMMUTABLE`). Setting `modules_enabled=false` while `modules` rows exist for the project returns `409 MODULES_IN_USE` (S7.2 `8f`: hidden only when `FALSE` and `0` modules).
   - `PUT .../module-defaults` body `{"module_ids": ["<uuid>", ...]}` (max `20`, unique) replaces `project_module_defaults` rows.
   - Response shape (all project reads/writes):
     ```json
     {"id": "0193...", "identifier": "KAN", "name": "Platform Core",
      "description_markdown": "", "modules_enabled": false,
      "default_module_ids": [], "auto_archive_days": null,
      "access_manifest": {"inherited_scope": "Workspace: Engineering", "users": [], "groups": [], "agents": []},
      "capabilities": ["VIEW", "EDIT", "ADMIN"]}
     ```
     `access_manifest` comes from the KB-P2-11 serializer (redaction preserved). `capabilities` lists the caller's effective capabilities so the UI can disable controls without guessing.
4. **Activity events emitted:** `PROJECT_CREATED {identifier}`, `PROJECT_UPDATED {changes: {field: {old, new}}}` (for `description_markdown` record `old_sha256`/`new_sha256` only), `MODULE_DEFAULTS_CHANGED {old_module_ids, new_module_ids}`.
5. **Contract capture harness (`kanban/tests/contract.py`):** `ContractRecorder.record(name, request, response)` collects exchanges; on session end, if env `KB_CONTRACT_OUT` is set, writes `{"ticket": "<value of KB_TICKET_ID>", "exchanges": [{"name", "request": {"method", "path", "headers", "body"}, "response": {"status", "headers", "body"}}]}` with `Cookie`, `Set-Cookie`, `X-CSRF-Token`, `Authorization` header values replaced by `"<redacted>"`. Exposed as pytest fixture `contract_recorder` in `kanban/tests/api/conftest.py`.
6. **Security invariants:** all reads use the RLS session (no `kanban_migrator` connections); 404 path uses the KB-P2-01 equalization helper; no enumeration of other projects' identifiers in `409 PROJECT_IDENTIFIER_TAKEN` beyond the submitted value.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/api/test_projects.py`, `kanban/tests/services/test_activity.py`, `kanban/tests/test_contract_recorder.py`
- **Required Test Cases:**
  1. Positive: workspace admin `POST /api/v1/projects` returns `201`, `Location` header, 5 seeded states, 5 seeded priorities with `None` as default, one `PROJECT_CREATED` activity row.
  2. Negative/security: a user with no `VIEW` on project `SEC` receives `404` with a body byte-identical (ignoring `instance`/request id) to `GET /api/v1/projects/NOPE`; a `VIEW`-only user `PATCH` receives `403 INSUFFICIENT_CAPABILITY`.
  3. Negative: identifier `kan`, `K`, `KANBANPROJECT1` each return `422`; duplicate identifier returns `409 PROJECT_IDENTIFIER_TAKEN`; unknown body key returns `422`.
  4. Boundary: `auto_archive_days` `0` and `366` return `422`; `1` and `365` succeed; `limit=0` and `limit=101` return `422`.
  5. Module rules: `PUT .../module-defaults` on a project with `modules_enabled=false` returns `422 MODULES_DISABLED`; a module UUID from another project returns `422 MODULE_NOT_IN_PROJECT`; disabling modules while a module exists returns `409 MODULES_IN_USE`.
  6. Activity helper: payload over `16384` bytes raises `ActivityPayloadTooLarge`; a raising listener rolls back the activity insert; every `ActivityEventType` member has an `EVENT_CATEGORY` entry.
  7. Contract recorder: redacts `Cookie`/`Set-Cookie`/`X-CSRF-Token`/`Authorization` values and writes valid JSON.
- Uses the clean-DB `SAVEPOINT` harness from KB-P0-05. Touched-module coverage `>= 95%`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** `kanban/api/v1/projects.py`, `kanban/api/v1/schemas/projects.py`, `kanban/services/projects.py`, `kanban/services/activity.py`, `kanban/tests/contract.py`, `kanban/tests/api/conftest.py` exist and implement the 5 endpoints, `record_activity`, `register_activity_listener`, `emit_ephemeral_event`, `ActivityEventType`, `ContractRecorder`.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api/test_projects.py kanban/tests/services/test_activity.py kanban/tests/test_contract_recorder.py -q --cov=kanban.api.v1.projects --cov=kanban.services.projects --cov=kanban.services.activity --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with `0` failures.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check kanban && uv run mypy --strict kanban && uv run lint-imports` exits `0`.
- [ ] **Contract Sample:** `docs/qa/<TICKET_ID>/contract-sample.json` contains at least these exchanges: create `201`, get `200`, get unreadable `404`, patch as viewer `403`, invalid identifier `422`, duplicate `409`, module defaults `200`.
- [ ] **Specialist Reviews:** `docs/qa/<TICKET_ID>/api-specialist-review.md` and `docs/qa/<TICKET_ID>/ui-specialist-review.md` exist and end with an explicit `APPROVED` line.
- [ ] **Forensic Proof Packet Complete:** all files listed below exist.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
The implementing sub-agent MUST populate `docs/qa/<TICKET_ID>/` with the following raw, unedited artifacts (no summaries):
1. `docs/qa/<TICKET_ID>/git-diff.patch` - complete unified `git diff` for this ticket.
2. `docs/qa/<TICKET_ID>/unit-test-results.txt` - full stdout/stderr and exit code of the pytest command above.
3. `docs/qa/<TICKET_ID>/build-check.txt` - full output of `uv run ruff check kanban && uv run mypy --strict kanban && uv run lint-imports`.
4. `docs/qa/<TICKET_ID>/contract-sample.json` - generated by `KB_TICKET_ID=<TICKET_ID> KB_CONTRACT_OUT=docs/qa/<TICKET_ID>/contract-sample.json uv run pytest kanban/tests/api/test_projects.py -q`.
5. `docs/qa/<TICKET_ID>/api-specialist-review.md` - raw audit from `.agents/agents/api-tester.md` or `.agents/agents/backend-architect.md`.
6. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - raw audit from `.agents/agents/ux-architect.md` or `.agents/agents/ui-designer.md` confirming the `capabilities` array and error `code` values are sufficient for the project settings UI.
7. Screenshots: N/A - Non-UI Ticket (API only; UI consumption reviewed in `ui-specialist-review.md`).
