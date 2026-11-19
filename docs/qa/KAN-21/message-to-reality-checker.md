# Reality Checker Evidence Packet: KAN-21 (KB-P3-AUDIT-15)

## Executive Summary
This packet provides comprehensive forensic verification for KAN-21: Upgrading AI Providers Backend.
All four scoped problems have been completely implemented, verified via unit/ASGI/Vitest tests, and confirmed to have zero architectural boundary violations and zero em/en-dashes.

## Scoped Problems and Implementations

### Problem 1: Private-LAN HTTP Base URLs and Air-Gap Classification
- **Files Modified/Added**: `kanban/ai_config/net_guard.py`, `kanban/ai_config/service.py`, `agent/providers/net_guard.py`, `agent/providers/openai_provider.py`, `agent/providers/ollama.py`, `agent/providers/gemini.py`, `agent/providers/air_gap.py`
- **Implementation**:
  - `validate_base_url` allows `http://` for loopback (`127.0.0.1`, `::1`, `localhost`), RFC1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), IPv6 ULA (`fc00::/7`), and pinned private LAN hostnames.
  - Enforces `https://` for all public internet endpoints.
  - Rejects link-local/cloud metadata SSRF (`169.254.0.0/16`, `fe80::/10`, `100.64.0.0/10`, `0.0.0.0/8`, `::/128`, multicast `224.0.0.0/4`, `ff00::/8`, and AWS metadata IPv6 `fd00:ec2::254/128`).
  - `OllamaSettings.allowed_ollama_cidrs` automatically includes admin-configured Ollama host IPs.
  - `OpenAISettings` permits empty/optional `api_key` when targeting private LAN / loopback base URLs.
  - `GeminiSettings` supports custom `base_url` override.
  - Air-gap checks classify local/private LAN OpenAI endpoints as local egress, allowing them to function in air-gap mode.

### Problem 2: 5+ Provider Cross-Tier Failover
- **Files Modified**: `agent/providers/router.py`
- **Implementation**:
  - `MAX_FAILOVER_CANDIDATES = 8` (raised from 4).
  - Evaluates enabled providers strictly in ascending priority order (`priority ASC`) across residency tiers when `air_gap_mode=False`.
  - When `air_gap_mode=True`, locks failover to the primary provider's residency tier.
  - Honors caller-specified `required_residency_tier` to isolate candidates to the target tier.

### Problem 3: Server-Side Model Probing and Test Connection
- **Files Modified**: `kanban/api/v1/admin/ai_providers.py`, `kanban/api/v1/admin/ai_schemas.py`, `kanban/ai_config/service.py`
- **Implementation**:
  - Added endpoints protected by `Depends(require_admin_aal2)`:
    - `POST /api/v1/admin/ai/providers/probe-models`
    - `POST /api/v1/admin/ai/providers/{provider_id}/probe-models`
    - `POST /api/v1/admin/ai/providers/test-connection`
    - `POST /api/v1/admin/ai/providers/{provider_id}/test-connection`
  - Utilizes `httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=5.0)` combined with `net_guard.resolve_and_pin()`.
  - Upstream endpoints:
    - Ollama: `GET {base_url}/api/tags`
    - OpenAI: `GET {base_url}/v1/models` (with fallback to `{base_url}/models` on 404)
    - Gemini: `GET {base_url}/v1beta/models` using `x-goog-api-key` header ONLY (never in URL query params)
  - Key custody: stored envelope API key unwrapped into a mutable `bytearray`, and securely zeroized in a `finally` block.
  - Returns structured diagnostic body `{ ok, latency_ms, models, model_count, error_code, message }`. Upstream reachability, auth, and network failures return HTTP 200 diagnostic responses.

### Problem 4: Atomic Reorder API and Air-Gap Path Fix
- **Files Modified**: `kanban/api/v1/admin/ai_providers.py`, `kanban/api/v1/admin/ai_schemas.py`, `kanban/services/activity.py`, `kanban/web/src/features/admin-ai/aiAdminApi.ts`
- **Implementation**:
  - Implemented `PUT /api/v1/admin/ai/providers/order` protected by `Depends(require_admin_aal2)`.
  - Uses `SELECT ... FOR UPDATE` row locks and validates full set membership of all workspace provider configs.
  - Reassigns priorities in increments of 10 (`10, 20, 30, ...`).
  - Emits `ActivityEventType.AI_PROVIDER_REORDERED` audit record with event payload `{"ordered_ids": [...], "assigned_priorities": {...}}`.
  - Fixed `fetchAirGapMode` in `aiAdminApi.ts` from invalid path to `GET /api/v1/admin/workspace-settings`.

## Verification and Coverage Evidence
- **Pytest Suite**: 205 passed in 17.69s (`KB_TEST_DB_PREFIX="kan21"`).
- **Unit & Branch Coverage**: Combined 97% across all touched modules (all touched files exceed `>= 95.10%` threshold):
  - `agent/providers/air_gap.py`: 100%
  - `agent/providers/errors.py`: 100%
  - `agent/providers/gemini.py`: 97%
  - `agent/providers/net_guard.py`: 100%
  - `agent/providers/ollama.py`: 96%
  - `agent/providers/openai_provider.py`: 96%
  - `agent/providers/router.py`: 97%
  - `kanban/ai_config/__init__.py`: 100%
  - `kanban/ai_config/net_guard.py`: 97%
  - `kanban/ai_config/service.py`: 97%
  - `kanban/api/v1/admin/ai_providers.py`: 99%
  - `kanban/api/v1/admin/ai_schemas.py`: 96%
- **Frontend Vitest Suite**: 5/5 tests passed (100% coverage on `aiAdminApi.ts`).
- **AAL2 Admin Policy Check**: `assert_admin_routes_protected` passed 100%.
- **OpenAPI Schema Export**: Generated and saved in `docs/qa/KAN-21/artifacts/admin-ai-openapi.json`.
- **Static Analysis & Linters**:
  - `uv run ruff check`: All checks passed (0 errors).
  - `uv run ruff format --check`: 30 files already formatted (0 differences).
  - `uv run mypy`: Success, 0 issues found in 17 source files.
  - `uv run lint-imports`: 2 kept, 0 broken. Unidirectional layer boundary `kanban` -> `agent` strictly maintained.
  - `python3 -m scripts.check_no_dashes --all`: Passed, 0 dashes found.
  - `pnpm run typecheck` (`tsc -b --noEmit`): Passed (0 errors).
  - `pnpm run lint` (`eslint . --max-warnings 0`): Passed (0 warnings, 0 errors).
- **UI Screenshots Note**: `N/A - Non-UI Ticket (1-line API path fix in aiAdminApi.ts verified via Vitest + ASGI tests)`.
