# API Specialist Security & Architecture Audit Review: KAN-21

## Audit Metadata
- Ticket ID: KAN-21 ([KB-P3-AUDIT-15])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan21-39347c90`
- Target Branch: feat/KAN-21
- Base Commit: 3dd6b9d
- Head Commit: 7153b1d
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the backend architecture, cryptographic security controls, SSRF protections, failover routing, and administrative REST endpoints implemented for ticket KAN-21. The delivery resolves four core architectural and security limitations in the AI providers subsystem: permitting private-LAN HTTP endpoints while defending against cloud metadata SSRF, expanding multi-provider cross-tier failover to at least 8 candidates, providing server-side live model probing and connection testing with zeroized key custody, and implementing an atomic provider reordering API.

All changes adhere strictly to the authoritative specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and `kanban/GEMINI.md`.

---

## Detailed Contract & Security Verification

### 1. Private-LAN HTTP Base URLs, SSRF Mitigation, and Air-Gap Classification
- Files: `kanban/ai_config/net_guard.py`, `kanban/ai_config/service.py`, `agent/providers/net_guard.py`, `agent/providers/openai_provider.py`, `agent/providers/ollama.py`, `agent/providers/gemini.py`, `agent/providers/air_gap.py`
- Invariant: Private-LAN AI endpoints (such as local vLLM, Ollama, or llama.cpp) must be accessible over `http://` while strictly preventing SSRF attacks against link-local, cloud metadata, and internal infrastructure.
- Audit Findings:
  - `validate_base_url` allows `http://` for loopback (`127.0.0.1`, `::1`, `localhost`), RFC1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), IPv6 ULA (`fc00::/7`), and pinned private LAN hostnames resolved via `net_guard.resolve_and_pin()`.
  - Enforces `https://` for all public internet hostnames.
  - Fail-closed SSRF defense: blocks link-local/cloud metadata (`169.254.0.0/16`, `fe80::/10`, `100.64.0.0/10`, `0.0.0.0/8`, `::/128`, multicast `224.0.0.0/4`, `ff00::/8`, and AWS metadata IPv6 `fd00:ec2::254/128`).
  - `OpenAISettings` permits optional or empty `api_key` when targeting private LAN or loopback endpoints.
  - `GeminiSettings` supports custom `base_url` overrides.
  - Air-gap checks classify local and private LAN OpenAI endpoints as local egress, allowing them to remain operational in air-gap mode.

### 2. Multi-Provider Cross-Tier Failover
- File: `agent/providers/router.py`
- Invariant: When upstream providers fail or exceed quotas, the router must fail over across up to 8 enabled candidate providers in strict priority order.
- Audit Findings:
  - Raised `MAX_FAILOVER_CANDIDATES = 8`.
  - Evaluates enabled providers strictly in ascending priority order (`priority ASC`) across residency tiers when `air_gap_mode=False`.
  - When `air_gap_mode=True`, failover is strictly confined to the primary provider residency tier.
  - Honors caller-specified `required_residency_tier` when present.

### 3. Server-Side Model Probing and Test Connection
- Files: `kanban/api/v1/admin/ai_providers.py`, `kanban/api/v1/admin/ai_schemas.py`, `kanban/ai_config/service.py`
- Invariant: Endpoints must require admin AAL2 authentication, execute with aggressive timeouts, prevent SSRF, and eliminate in-memory key leakage.
- Audit Findings:
  - All four diagnostic endpoints declare `Depends(require_admin_aal2)`:
    - `POST /api/v1/admin/ai/providers/probe-models`
    - `POST /api/v1/admin/ai/providers/{provider_id}/probe-models`
    - `POST /api/v1/admin/ai/providers/test-connection`
    - `POST /api/v1/admin/ai/providers/{provider_id}/test-connection`
  - Client configuration: `httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=5.0)` combined with `net_guard.resolve_and_pin()`.
  - Gemini header isolation: Gemini requests pass `x-goog-api-key` strictly via HTTP header, never leaking secret keys into URL query parameters.
  - Key memory hygiene: Envelope keys are unwrapped into mutable `bytearray` objects and zeroized in `finally` blocks.
  - Returns structured diagnostic body `{ ok, latency_ms, models, model_count, error_code, message }` returning HTTP 200 for upstream errors.

### 4. Atomic Reorder API and Air-Gap Path Fix
- Files: `kanban/api/v1/admin/ai_providers.py`, `kanban/api/v1/admin/ai_schemas.py`, `kanban/services/activity.py`, `kanban/web/src/features/admin-ai/aiAdminApi.ts`
- Invariant: Reordering provider priorities must be atomic, prevent duplicate priorities, validate full set membership, and emit an audit trail.
- Audit Findings:
  - `PUT /api/v1/admin/ai/providers/order` is gated with `Depends(require_admin_aal2)`.
  - Uses `SELECT ... FOR UPDATE` row locks and enforces that `ordered_ids` contains every configured provider in the workspace.
  - Assigns clean priorities in increments of 10 (`10, 20, 30, ...`).
  - Emits `ActivityEventType.AI_PROVIDER_REORDERED` audit record with before/after priority mappings.
  - In `aiAdminApi.ts`, `fetchAirGapMode` updated to call `GET /api/v1/admin/workspace-settings`.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: All `/api/v1/admin/*` routes maintain mandatory `Depends(require_admin_aal2)`. Verified by `kanban/tests/auth/test_aal2_policy.py`.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Coverage:
   - Backend: 205 unit and integration tests passing (`test_net_guard.py`, `test_service.py`, `test_ai_providers_api.py`, `agent/tests/providers/`).
   - Combined coverage: 97% across touched modules, with every individual touched file exceeding >= 95.10%.
   - Frontend: 5 vitest tests passing in `aiAdminApi.test.ts` (100% coverage).
5. [x] Static Analysis: `ruff check`, `ruff format --check`, `mypy` (17 source files), `tsc -b --noEmit`, and `eslint` pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, `artifacts/admin-ai-openapi.json`, and `message-to-reality-checker.md` verified in `docs/qa/KAN-21/`.

---

## 5. Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-15)

- Target Branch: `fix/KAN-21-liveqa`
- Remediation Head Commit: `d62fb30`
- Remediation Scope:
  1. Zero DNS-Rebinding TOCTOU Defense:
     - In `kanban/ai_config/net_guard.py`: Added and exported `LOCAL_AND_PRIVATE_CIDRS` and `SSRFBlockedError(EgressDeniedError)`.
     - In `kanban/ai_config/service.py`: Enforced that `http://` endpoints are restricted to `LOCAL_AND_PRIVATE_CIDRS` and verified with `is_local_or_private_ip(pinned_ip)` prior to opening network sockets.
     - Captured `pinned_ip = await resolve_and_pin(...)` and reconstructed the HTTP target using the literal pinned IP (`pinned_base_url = f"{parsed.scheme}://{host_repr}{port_suffix}{base_path}"`).
     - Passed explicit `Host` header and `extensions={"sni_hostname": host}` (for HTTPS), guaranteeing zero DNS rebinding on subsequent request execution.
  2. Coverage & Measurement Verification:
     - Eliminated coverage warnings by running source-scoped test execution, achieving 97% total coverage across 1898 statements in `kanban.ai_config` and `agent.providers`.
     - Verified 197 passing tests, including explicit tests for pinned IP reconstruction, `Host` header propagation, and pre-socket SSRF rejection of public HTTP domains.
  3. Static Analysis & Gate Cleanliness:
     - Zero new dependencies.
     - Strict 0 em/en-dashes verified.
     - `ruff check`, `mypy`, and `lint-imports` clean.

---

## Verdict & Handoff
STATUS: APPROVED

The API contracts, security invariants, and test evidence are verified clean. Handoff to `@ui-spec-2` for API-to-UI contract verification (backend-only ticket; 1-line API path fix in `aiAdminApi.ts` verified via unit/Vitest tests).

