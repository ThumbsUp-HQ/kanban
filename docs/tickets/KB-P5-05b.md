---
id: KB-P5-05b
title: '[Phase 5 / API + MCP] AI provider & budget admin REST API + /mcp/admin manage_ai_and_agent_runners (providers + budgets
  actions)'
epic: KB-E5
depends_on: [KB-P5-05a, KB-P4-09a, KB-P4-09b]
spec_sections: ['10.2', '11.4']
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: second half of manifest row `KB-P5-05`. `agent_definitions` actions of tool 9 belong to `KB-P5-16`; runner enrollment actions belong to `KB-P5-22`.

### User Story
As a **Workspace or Project Admin (human or MCP admin agent)**, I need **REST endpoints and the `/mcp/admin` tool 9 `manage_ai_and_agent_runners` providers/budgets actions to list, create, update and disable provider configs and set/read token caps** so that **AI provider governance is fully scriptable through one intent tool without ever exposing key material**.

**Requirement Traceability:** `S10.2`, `S11.4 tool 9 (manage_ai_and_agent_runners)`, original requirements `#2`, `#12` | **Dependencies:** `KB-P5-05a`, `KB-P4-09`

### Scoped Technical Actions
1. **Target Files:**
   - `kanban/api/v1/admin/ai_providers.py` (new router)
   - `kanban/api/v1/admin/ai_schemas.py` (new Pydantic request/response models)
   - `mcp/admin/tools/manage_ai_and_agent_runners.py` (new)
   - `mcp/admin/registry.py` (modify: register tool 9)
   - `kanban/GEMINI.md`, `mcp/GEMINI.md` (update)
2. **REST endpoints (all require session + CSRF from KB-P2-02, admin capability on the target workspace/project, RFC 7807 errors from KB-P2-01):**
   - `GET /api/v1/admin/ai/providers?project_id=` -> list of `ProviderConfigPublic {id, provider_kind, display_name, base_url, model_allowlist, residency_tier, priority, settings, api_key_set, is_enabled, project_id}`.
   - `POST /api/v1/admin/ai/providers` body `ProviderConfigCreate` (`api_key` write-only `SecretStr`, max `512` chars) -> `201`.
   - `PATCH /api/v1/admin/ai/providers/{id}` -> `200`; `api_key` omitted = unchanged, `api_key: null` = remove key.
   - `POST /api/v1/admin/ai/providers/{id}:disable` -> `200`.
   - `GET /api/v1/admin/ai/budgets?provider_config_id=` -> `{period_kind, period_start, token_cap, tokens_used, tokens_reserved}` rows.
   - `PUT /api/v1/admin/ai/budgets` body `{provider_config_id, project_id?, period_kind, token_cap}` (`0 <= token_cap <= 10,000,000,000`) -> upsert current-period row and future rows inherit cap.
   - Error codes: `AIR_GAP_EGRESS_DENIED` (`409`), `INVALID_BASE_URL` (`422`), `NOT_FOUND` (`404`, timing-equalized helper from KB-P2-01 for unreadable ids), `FORBIDDEN` (`403` only when the caller can read but not administer).
   - Response bodies never contain `api_key`, ciphertext, nonce, DEK or kid (enforced by response model `extra="forbid"` and a test scanning serialized JSON for the submitted key string).
   - Every mutation writes an `activity_records` entry (`AI_PROVIDER_CONFIG_CREATED|UPDATED|DISABLED`, `AI_BUDGET_SET`) with key material excluded.
3. **MCP tool 9 `manage_ai_and_agent_runners` (providers + budgets actions only):**
   - Input discriminated union on `action`: `list_providers`, `upsert_provider`, `disable_provider`, `set_budget`, `get_budget_usage`. Actions `upsert_agent_definition`, `list_agent_definitions`, `mint_runner_enrollment_token` return structured error `ACTION_NOT_AVAILABLE` until KB-P5-16 / KB-P5-22 land (documented in tool `help`).
   - Requires a `kb_adm_*` key or admin OAuth token (KB-P4-02 surface binding); calls the same `AIProviderConfigService` (no duplicated logic) through the kanban service layer (no `mcp -> agent` import).
   - Output via `InlineSafeDumper` YAML (KB-P4-03), LOD `summary|standard|full`; `api_key` accepted only in `upsert_provider` input and never echoed.

### Mandatory Feature Unit Tests
- **Test File(s):** `kanban/tests/api/admin/test_ai_providers_api.py`, `mcp/tests/admin/test_manage_ai_and_agent_runners.py`
- **Cassettes:** N/A for LLM calls (no provider is invoked by this ticket); budget usage values seeded from `tests/fixtures/ai/budget_usage_48_tokens.yaml` via `BudgetEnforcer.settle` in setup to keep numbers consistent with KB-P5-05a.
- **Required Test Cases:**
  1. Positive: admin creates `ollama` config, lists it, sets daily cap `100000`, reads usage `tokens_used=48`.
  2. Positive: MCP `upsert_provider` then `list_providers` returns the same `id`; YAML output omits null fields.
  3. Security: response JSON and MCP YAML never contain the submitted API key string (substring scan) nor `wrapped_` fields.
  4. Security: `MEMBER` principal -> `404` for unreadable workspace config, `403` where readable-not-admin; `kb_agt_*` key on tool 9 -> rejected by surface binding.
  5. Security: POST without CSRF token -> `403`; `gemini` create under `air_gap_mode` -> `409 AIR_GAP_EGRESS_DENIED`.
  6. Negative: `base_url` `http://169.254.169.254` for `ollama` -> `422 INVALID_BASE_URL`; `token_cap` negative -> `422`.
  7. Boundary: `api_key` length `512` accepted, `513` rejected; `PATCH` with omitted key keeps `api_key_set: true`; `api_key: null` -> `false`.
  8. Fault: `ACTION_NOT_AVAILABLE` for `mint_runner_enrollment_token`.
  9. Audit: each mutation produces exactly one `activity_records` row with no key material.
- **Coverage:** `>= 95%` line + branch for the 3 new source files.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** the router, schemas and MCP tool files exist and implement the endpoints and 5 actions listed.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/api/admin/test_ai_providers_api.py mcp/tests/admin/test_manage_ai_and_agent_runners.py -q -p no:cacheprovider --cov=kanban.api.v1.admin.ai_providers --cov=kanban.api.v1.admin.ai_schemas --cov=mcp.admin.tools.manage_ai_and_agent_runners --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with all 9 cases present.
- [ ] **Build / Type / Lint Clean:** `uv run mypy --strict kanban mcp`, `uv run ruff check .`, `uv run lint-imports` each exit `0`.
- [ ] **Contract Samples:** `contract-sample.json` and `mcp-sample.yaml` exist and contain no key material.
- [ ] **Specialist Reviews:** `api-specialist-review.md` and `ui-specialist-review.md` exist with explicit approval lines.
- [ ] **Forensic Proof Packet Complete:** All files below exist.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
The implementing sub-agent MUST populate `docs/qa/<TICKET_ID>/` with the following raw, unedited artifacts (no summaries) so `reality-checker` can audit the ticket without executing commands:
1. `docs/qa/<TICKET_ID>/git-diff.patch` - Complete unified `git diff`.
2. `docs/qa/<TICKET_ID>/unit-test-results.txt` - Full output and exit code of the DoD pytest command.
3. `docs/qa/<TICKET_ID>/build-check.txt` - Full output of mypy, ruff, lint-imports.
4. `docs/qa/<TICKET_ID>/contract-sample.json` - Captured request/response pairs for each REST endpoint from the test run.
5. `docs/qa/<TICKET_ID>/mcp-sample.yaml` - Captured tool 9 input/output for each of the 5 actions plus one `ACTION_NOT_AVAILABLE`.
6. `docs/qa/<TICKET_ID>/api-specialist-review.md` - Raw audit and sign-off from `.agents/agents/backend-architect.md` or `.agents/agents/api-tester.md`.
7. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - Raw audit from `.agents/agents/ui-designer.md` or `.agents/agents/ux-architect.md` covering frontend consumption of the response shapes (write-only key UX, error codes).
8. Screenshots: N/A - Non-UI Ticket (API only; the admin UI is out of scope).
