# Reality-Checker Forensic QA Report: KAN-21

## Executive Summary
- Ticket ID: KAN-21 ([KB-P3-AUDIT-15])
- Title: Upgrading AI Providers Backend: Private-LAN Base URLs, 5+ Cross-Tier Failover, Server Probing, and Atomic Reordering
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan21-39347c90`
- Target Branch: `feat/KAN-21`
- Reviewer: rc-gate-2 (Clean-Room Forensic QA Gate)
- Review Date: 2026-11-19
- Overall Quality Rating: A
- Production Readiness: READY

---

## Forensic Audit Verification Matrix

### Problem 1: Private-LAN HTTP Base URLs, SSRF Mitigation, and Air-Gap Classification
- Defect: Base URL validation previously required HTTPS universally, preventing integration with local or self-hosted models (Ollama, vLLM, llama.cpp) running on private LAN subnets or local loopback. Furthermore, air-gap mode blocked local OpenAI-compatible endpoints.
- Verification:
  - Inspected `kanban/ai_config/net_guard.py` and `agent/providers/net_guard.py`: `validate_base_url` allows `http://` for loopback (`127.0.0.1`, `::1`, `localhost`), RFC1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), IPv6 ULA (`fc00::/7`), and pinned private hostnames.
  - Fail-closed SSRF defense: Public hostnames strictly require `https://`. Link-local, AWS/cloud metadata (`169.254.0.0/16`, `fe80::/10`, `fd00:ec2::254/128`), carrier-grade NAT (`100.64.0.0/10`), loopback broadcast (`0.0.0.0/8`), and multicast ranges are blocked.
  - Inspected `agent/providers/openai_provider.py`: Allows empty or omitted `api_key` when targeting private LAN or loopback base URLs.
  - Inspected `agent/providers/gemini.py`: Supports custom `base_url` overrides.
  - Inspected `agent/providers/air_gap.py`: Local and private-LAN OpenAI endpoints are classified as local egress, allowing them to remain operational under air-gap mode.
  - Status: VERIFIED RESOLVED

### Problem 2: 5+ Multi-Provider Cross-Tier Failover
- Defect: The provider router previously limited failover candidates to 4 providers, restricting high-availability setups with 5 or more configured AI providers.
- Verification:
  - Inspected `agent/providers/router.py`: `MAX_FAILOVER_CANDIDATES = 8` (raised from 4).
  - Evaluates enabled providers strictly in ascending priority order (`priority ASC`) across residency tiers when `air_gap_mode=False`.
  - When `air_gap_mode=True`, locks failover candidates strictly to the primary provider residency tier.
  - Caller-specified `required_residency_tier` is strictly honored to isolate candidates to the target residency tier.
  - Status: VERIFIED RESOLVED

### Problem 3: Server-Side Live Model Probing and Test Connection
- Defect: Administrators had no server-side diagnostic mechanism to probe remote model catalogs or test provider reachability prior to saving configurations, leading to blind connection errors.
- Verification:
  - Inspected `kanban/api/v1/admin/ai_providers.py` and `kanban/ai_config/service.py`: Added 4 diagnostic endpoints protected by `Depends(require_admin_aal2)`:
    - `POST /api/v1/admin/ai/providers/probe-models`
    - `POST /api/v1/admin/ai/providers/{provider_id}/probe-models`
    - `POST /api/v1/admin/ai/providers/test-connection`
    - `POST /api/v1/admin/ai/providers/{provider_id}/test-connection`
  - Client configuration: `httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=5.0)` combined with `net_guard.resolve_and_pin()`.
  - Key memory hygiene: Envelope keys are unwrapped into mutable `bytearray` objects and zeroized in `finally` blocks.
  - Gemini header isolation: Gemini requests pass `x-goog-api-key` strictly via HTTP header, never leaking secret keys into URL query parameters.
  - Upstream probe targets: Ollama (`GET /api/tags`), OpenAI (`GET /v1/models` with fallback to `/models`), Gemini (`GET /v1beta/models`).
  - Structured response: Returns `{ ok, latency_ms, models, model_count, error_code, message }` returning HTTP 200 for upstream reachability or auth failures.
  - Status: VERIFIED RESOLVED

### Problem 4: Atomic Provider Priority Reordering API & Air-Gap Endpoint Path Fix
- Defect: Priority reassignment lacked an atomic API endpoint, risking duplicate priorities during manual updates. Furthermore, the frontend `fetchAirGapMode` requested a non-existent API path (`/api/v1/workspaces/settings`).
- Verification:
  - Inspected `kanban/api/v1/admin/ai_providers.py`: Implemented `PUT /api/v1/admin/ai/providers/order` protected by `Depends(require_admin_aal2)`.
  - Employs `SELECT ... FOR UPDATE` row locks and enforces full set membership of all workspace provider configs.
  - Assigns clean priorities in increments of 10 (`10, 20, 30, ...`).
  - Emits `ActivityEventType.AI_PROVIDER_REORDERED` audit record with before and after priority assignments.
  - Inspected `kanban/web/src/features/admin-ai/aiAdminApi.ts`: Corrected `fetchAirGapMode` path to `GET /api/v1/admin/workspace-settings`.
  - Status: VERIFIED RESOLVED

---

## Automated Test & Static Analysis Evidence

1. Unit & Integration Tests:
   - Python Pytest: 205 passed in 17.69s.
   - Coverage: Combined 97% across touched modules, with every touched file exceeding the >= 95.10% threshold (`agent/providers/air_gap.py` 100%, `agent/providers/errors.py` 100%, `agent/providers/gemini.py` 97%, `agent/providers/net_guard.py` 100%, `agent/providers/ollama.py` 96%, `agent/providers/openai_provider.py` 96%, `agent/providers/router.py` 97%, `kanban/ai_config/net_guard.py` 97%, `kanban/ai_config/service.py` 97%, `kanban/api/v1/admin/ai_providers.py` 99%).
   - Frontend Vitest: 5/5 tests passed in 0.92s with 100% coverage on `aiAdminApi.ts`.
   - Raw output logged in `docs/qa/KAN-21/unit-test-results.txt`.

2. Static Analysis & Type Checking:
   - Ruff check: clean (All checks passed).
   - Ruff format check: 30 files verified clean.
   - Mypy check: Success, no issues found in 17 source files.
   - Import Linter: 2 contracts kept, 0 broken (`agent -> mcp -> kanban -> database` strictly preserved).
   - TypeScript compiler (`tsc -b --noEmit`): 0 errors.
   - ESLint: 0 warnings, 0 errors.
   - Strict ASCII character check: Zero `\u2014` em-dashes and zero `\u2013` en-dashes across all modified files.
   - Raw output logged in `docs/qa/KAN-21/build-or-typecheck.txt`.

---

## Dual Specialist Gate Audits

1. API Specialist Audit:
   - File: `docs/qa/KAN-21/api-specialist-review.md`
   - Reviewer: `api-spec-2`
   - Status: APPROVED
   - Findings: Verified private-LAN HTTP validation, SSRF cloud metadata mitigation, failover router limits, zeroized key custody, and admin AAL2 policy enforcement.

2. UI/UX Specialist Audit:
   - File: `docs/qa/KAN-21/ui-specialist-review.md`
   - Reviewer: `ui-spec-2`
   - Status: APPROVED
   - Findings: Verified API-to-UI consumer contracts, `fetchAirGapMode` path correction, typed reordering and diagnostic probe helpers, and non-UI ticket declaration in `docs/qa/KAN-21/screenshots/README.md`.

---

## Visual Proof & Artifacts

- Artifacts verified in `docs/qa/KAN-21/`:
  - `git-diff.patch`
  - `changed-files-manifest.txt`
  - `unit-test-results.txt`
  - `build-or-typecheck.txt`
  - `message-to-reality-checker.md`
  - `artifacts/admin-ai-openapi.json`
  - `screenshots/README.md` (Confirmed non-UI ticket; 1-line API path fix verified via unit and Vitest tests)

---

## Final Gate Certification
- Overall Quality Rating: A
- Production Readiness: READY
- Recommendation: Proceed to merge into `main` branch.
