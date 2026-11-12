# API Specialist Gate Independent Audit: KANBA-67 (KB-P3-01a)

- Ticket: `KANBA-67` (`KB-P3-01a`): Project architect API (part a): projects CRUD, module defaults, shared activity/contract infrastructure
- Auditor: `arch-reviewer` (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Date: 2026-11-12
- Worktree: `/tmp/kb-wt-KANBA-67`, branch `feat/KANBA-67`, commit `aa37866`
- Scope: `kanban/api/v1/projects.py`, `kanban/services/projects.py`, `kanban/services/activity.py`, `kanban/tests/contract.py`, `contract-sample.json`, root `pyproject.toml` coverage change.

## Verification Matrix

| Dimension | Target | Observed | Verdict |
| :--- | :--- | :--- | :--- |
| Endpoints | POST/GET list/GET one/PATCH/PUT module-defaults under `/api/v1/projects` | All 5 present, mounted in `build_v1_router()`, response models set | PASS |
| Authn/authz order | RLS session, then VIEW (404), then capability (403) | `get_project_or_404` through RLS, then `require_capability(ADMIN)`; unreadable and absent are identical 404 inside `timing_floor(25ms)` | PASS |
| Create authorization | workspace/server admin, token scope includes ADMIN | `_require_project_creator`: role check via `app_principal_has_role`, token mask must contain ADMIN, OBO agents refused (403). Stricter than ticket, in the safe direction | PASS |
| Atomic create | project row, object registry row, creator PROJECT_ADMIN binding, activity | Single nested savepoint; unique violation (SQLSTATE 23505) mapped to 409 `PROJECT_IDENTIFIER_TAKEN`; no raw driver text returned | PASS |
| Input validation | `extra="forbid"`, identifier `^[A-Z][A-Z0-9]{1,9}$`, immutable identifier, description cap 524288 bytes | Enforced; description passes through `normalize_to_markdown`; lone surrogate mapped to 422 `INVALID_CONTENT` | PASS |
| Cursor | opaque, validated | base64url of identifier, re-validated against identifier regex on decode, `422 INVALID_CURSOR` on any malformed input | PASS |
| Activity helper | 16384 byte cap, hash chain via `append_activity`, no Markdown bodies, fail-closed listeners | Sizes checked before insert, descriptions recorded as sha256 only, insert and listeners share one savepoint | PASS |
| Contract recorder | redacts Cookie, Set-Cookie, X-CSRF-Token, Authorization | Header redaction verified; `contract-sample.json` has 7 exchanges, no credential values | PASS |
| Gates | ruff, mypy --strict, lint-imports, license, dashes | Reported clean; 21 target tests re-run by me: 21 passed, 99% line+branch | PASS |

## Answers to author questions

1. `access_manifest.inherited_scope` as an object: acceptable and preferable. It is the KB-P2-11 contract already approved; the ticket example string would force a second shape. Keep the object; the UI review should confirm.
2. Create denied for OBO agents and non-ADMIN token scopes: correct least-privilege behaviour. Keep.
3. `concurrency = ["greenlet","thread"]` in `[tool.coverage.run]`: correct and necessary for SQLAlchemy async; it fixes under-reporting, it does not weaken any gate. Keep. Consider noting it in `kanban/GEMINI.md`.
4. `normalize_inspect` encodes before its surrogate guard: confirmed as a defect in KB-P2-13 code. The local `UnicodeEncodeError` catch is a sound containment. Open a follow-up ticket to move the guard ahead of the encode so `ContentNormalizeError` is raised uniformly.

## Non-blocking advisories

- A1 (MEDIUM, follow-up ticket): `list_projects` calls `serialize_project` per row, which runs `build_access_manifest` plus `evaluate_capabilities` each time. At `limit=100` this is on the order of thousands of queries per request and an authenticated amplification vector. Before the Phase 3 UI consumes the list, either return a slim list item (identifier, name, capabilities, pill label) or cap list `limit` for the full shape.
- A2 (LOW): `ContractRecorder` redacts headers only. Later auth tickets will record bodies containing `kb_*` tokens and setup URLs. Add body scrubbing with the same `kb_[a-z_]+_[A-Za-z0-9_-]{20,}` pattern used in the MCP transcript fixture before KB-P2-04 reuses it.
- A3 (INFO): `PROJECT_IDENTIFIER_TAKEN` echoes the caller-supplied identifier in `detail`. It is regex-validated first and the caller is an admin, so this is safe; keep the validation order.

## Verdict

The API surface is correctly layered (RLS, 404 before 403, timing floor), fail-closed on content and cursor input, and the shared activity and contract infrastructure meets its contract. Advisories A1 and A2 are tracked, not blocking.

APPROVED
