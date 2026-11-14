# API Specialist Gate Review: KANBA-144 (KB-P5-05b)

- **Ticket**: `KANBA-144` (`KB-P5-05b`: `[Phase 5 / API + MCP] AI provider & budget admin REST API + /mcp/admin manage_ai_and_agent_runners (providers + budgets actions)`)
- **Reviewer**: `@arch-reviewer` (Backend Architect & API Specialist)
- **Worktree**: `/tmp/kb-wt-KANBA-144`
- **Branch**: `feat/KANBA-144`
- **Scope**:
  - `kanban/api/v1/admin/ai_schemas.py`
  - `kanban/api/v1/admin/ai_providers.py`
  - `kanban/api/v1/__init__.py`
  - `mcp/admin/tools/manage_ai_and_agent_runners.py`
  - `mcp/surfaces/admin/manage_ai_and_agent_runners.py`
  - `mcp/surfaces/admin/__init__.py`
  - `mcp/auth.py`
  - `mcp/errors.py`
  - `mcp/yaml_out.py`
  - `kanban/services/activity.py`
  - `kanban/tests/api/admin/test_ai_providers_api.py`
  - `mcp/tests/admin/test_manage_ai_and_agent_runners.py`

---

### 1. Architectural & Security Evaluation

#### A. Administrative Protection & AAL2 MFA Policy (Spec S4.3, S10.2)
- All `/api/v1/admin/ai/*` routes declare `Depends(require_admin_aal2)` at the router level and via explicit caller dependency injection.
- Unauthenticated or non-admin callers receive HTTP 403 `FORBIDDEN` or `MFA_ENROLLMENT_REQUIRED` / `AAL2_REQUIRED`.
- Compliance with `assert_admin_routes_protected` is verified.

#### B. Anti-Enumeration & Timing-Equalized 404 Defense (Spec S14.3)
- `timing_floor(floor_ms=25.0)` wraps all endpoint handlers.
- When an AI provider config ID does not exist, or belongs to a workspace/project unreadable to the caller under PostgreSQL RLS, the endpoint returns a timing-equalized HTTP 404 `NOT_FOUND` response with identical timing profile and byte structure, preventing ID enumeration.

#### C. Write-Only Key Custody & Envelope Encryption (Spec S10.1, S10.2)
- REST request schemas (`ProviderConfigCreate`, `ProviderConfigUpdate`) accept optional `api_key: SecretStr` bounded at 512 characters.
- Public responses (`ProviderConfigPublic`) project `api_key_set: bool` and strictly omit all plaintext keys, `wrapped_api_key`, `api_key_nonce`, and `wrapped_dek`.
- Database column-level privilege isolation: `wrapped_api_key`, `api_key_nonce`, and `wrapped_dek` are revoked from `kanban_app` and `app_rls_reader`, with ORM deferred loading preventing accidental exposure.
- `mcp/yaml_out.py`: Added `"api_key"`, `"wrapped_api_key"`, `"api_key_nonce"` to `_SECRET_KEY_NAMES` for defense-in-depth YAML scrubbing.

#### D. Air-Gap Mode Outbound Egress Enforcement (Spec S10.1)
- `_is_air_gap_active` evaluates both workspace-level `air_gap_mode` setting and environment variable `KANBAN_AIR_GAP_MODE`.
- When air-gap mode is active, creating or enabling an external cloud provider (`openai`, `gemini`) immediately halts and returns HTTP 409 `AIR_GAP_EGRESS_DENIED`. Local providers (`ollama`, `fixture`) remain available.

#### E. SSRF Defense & Base URL Validation (Spec S10.2)
- Base URLs are parsed and strictly restricted to `http` or `https` schemes with zero userinfo or query strings.
- Hostnames resolving to loopback (`127.0.0.1`, `::1`, `localhost`) are permitted exclusively for `ollama` and `fixture` kinds.
- Cloud metadata service IP (`169.254.169.254`) and link-local ranges (`169.254.0.0/16`) are strictly rejected with HTTP 422 `INVALID_BASE_URL`.

#### F. MCP Tool 9: manage_ai_and_agent_runners (Spec S11.4)
- Implements 5 operational actions: `list_providers`, `upsert_provider`, `disable_provider`, `set_budget`, `get_budget_usage`.
- Surface key binding: non-admin keys (e.g. `kb_agt_*`) are rejected with HTTP 403 `SURFACE_KEY_MISMATCH`.
- Scoped authorization: read actions require `admin:read` (or `admin:write`/`admin:destructive`), mutation actions require `admin:write` (or `admin:destructive`).
- LOD projection: outputs compact, schema-aligned YAML omitting null fields across `summary`, `standard`, and `full` tiers.
- Deferred actions (`upsert_agent_definition`, `list_agent_definitions`, `mint_runner_enrollment_token`) cleanly return structured fault `ACTION_NOT_AVAILABLE` with reserved implementation notices.

#### G. Immutable Activity Audit Ledger (Spec S12.2)
- Mutations record immutable SHA-256 hash-chained entries: `AI_PROVIDER_CONFIG_CREATED`, `AI_PROVIDER_CONFIG_UPDATED`, `AI_PROVIDER_CONFIG_DISABLED`, and `AI_BUDGET_SET`.
- Audit payloads record IDs, kinds, and timestamps while strictly suppressing key material.

---

### 2. Verification & Test Metrics

- **Unit Tests**: 15/15 tests passing across `test_ai_providers_api.py` and `test_manage_ai_and_agent_runners.py` covering all 9 required ticket test cases.
- **Coverage**:
  - `kanban/api/v1/admin/ai_providers.py`: 100%
  - `kanban/api/v1/admin/ai_schemas.py`: 100%
  - `mcp/admin/tools/manage_ai_and_agent_runners.py`: 97%
  - **Combined Coverage**: **98.86%** (exceeds >= 95% mandate).
- **Static Quality**:
  - `ruff check .`: PASS (0 errors)
  - `ruff format --check .`: PASS (1197 files clean)
  - `mypy --strict kanban mcp database agent`: PASS (0 issues across 693 files)
  - `lint-imports`: PASS (2/2 contracts kept, zero layering violations)
  - `license_gate.py`: PASS (0 violations)
  - `check_no_dashes.py --all`: PASS (0 violations)

---

### 3. Verdict

**Verdict: APPROVED**
The REST API router, schemas, activity logging, and MCP Tool 9 satisfy all architectural, security, and test requirements.
