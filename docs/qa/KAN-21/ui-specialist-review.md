# UI/UX Specialist Review: KAN-21

## Audit Metadata
- Ticket ID: KAN-21 ([KB-P3-AUDIT-15])
- Reviewer: ui-spec-2 (Clean-Room UI/UX Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan21-39347c90`
- Target Branch: feat/KAN-21
- STATUS: APPROVED

---

## Executive Summary
This review verifies the API-to-UI consumer contracts, client-side TypeScript bindings, and state alignment for ticket KAN-21. While KAN-21 is primarily a backend architecture ticket for AI provider networking, SSRF defense, failover routing, and server-side model probing, it directly resolves an API path defect in the frontend AI client (`fetchAirGapMode` in `aiAdminApi.ts`) and provides typed API helpers for provider reordering and diagnostic model probing.

The OpenAPI schema specifications in `docs/qa/KAN-21/artifacts/admin-ai-openapi.json`, frontend client implementation in `kanban/web/src/features/admin-ai/aiAdminApi.ts`, and corresponding Vitest test suite (`aiAdminApi.test.ts`) were audited.

---

## API-to-UI Contract & State Alignment Verification

### 1. Air-Gap Mode Path Resolution
- Component: `kanban/web/src/features/admin-ai/aiAdminApi.ts:125-135` (`fetchAirGapMode`)
- Issue Resolved: `fetchAirGapMode` previously requested `/api/v1/workspaces/settings`, a non-existent route that always caught an exception and returned a false negative (`false`).
- Resolution: Corrected endpoint path to `GET /api/v1/admin/workspace-settings`.
- UI/UX Impact: The AI Admin Studio accurately detects whether the active workspace operates in air-gap mode, dynamically filtering online providers and displaying the air-gap banner to administrators.

### 2. Atomic Reordering Client Contract
- Helper: `reorderAiProviders(orderedIds: string[])`
- Endpoint: `PUT /api/v1/admin/ai/providers/order`
- Contract Invariant: Sends `{ ordered_ids: string[] }` and receives updated `ProviderConfigPublic[]` list with recalculated sequential priorities (10, 20, 30, ...).
- UI/UX Ergonomics: Enables drag-and-drop or rank-order list interfaces in the AI Admin Studio to atomically commit reordered priorities in a single transaction without race conditions or partial updates.

### 3. Server-Side Model Probing & Connection Test Schema
- Helpers: `probeAiModels` and `testAiConnection`
- Endpoints:
  - `POST /api/v1/admin/ai/providers/probe-models` (unsaved draft probe)
  - `POST /api/v1/admin/ai/providers/{provider_id}/probe-models` (saved provider probe)
  - `POST /api/v1/admin/ai/providers/test-connection` (unsaved draft test)
  - `POST /api/v1/admin/ai/providers/{provider_id}/test-connection` (saved provider test)
- Structured Response: Returns `{ ok, latency_ms, models, model_count, error_code, message }`.
- UI/UX Impact:
  - Upstream connectivity failures return HTTP 200 with `ok: false` and structured `message` / `error_code`, allowing the frontend modal to display contextual inline troubleshooting hints without generic 500 error banners.
  - Successful probes return discovered `models` array, allowing dropdown inputs to be pre-populated automatically with valid model identifiers.

---

## Code Quality & Standards

### 1. Content Security Policy (CSP) Compliance
- Zero inline `style={...}` JSX attributes added (zero JSX modifications).
- All changes in `aiAdminApi.ts` are strongly typed TypeScript functions and interfaces.

### 2. Nullish Coalescing & Type Safety
- All interfaces in `aiAdminApi.ts` define nullable properties with strict optional chaining and safe typing: `base_url?: string | null`, `api_key?: string | null`, `settings_json?: Record<string, unknown> | null`.
- Satisfies `@typescript-eslint/prefer-nullish-coalescing`.

### 3. Punctuation & Style Standard
- Zero em-dashes (`\u2014`) or en-dashes (`\u2013`) in code, tests, or documentation. All punctuation uses standard ASCII hyphens (-).

---

## Final Verification Checklist

1. [x] OpenAPI schema validated in `docs/qa/KAN-21/artifacts/admin-ai-openapi.json`
2. [x] `fetchAirGapMode` endpoint path corrected to `/api/v1/admin/workspace-settings`
3. [x] Typed `reorderAiProviders`, `probeAiModels`, and `testAiConnection` helpers verified
4. [x] Vitest test suite achieves 100% coverage on touched `aiAdminApi.ts`
5. [x] Non-UI declaration confirmed in `docs/qa/KAN-21/screenshots/README.md`
6. [x] Zero inline `style={...}` attributes (CSP compliant)
7. [x] Strict ASCII hyphenation verified (0 em/en-dashes)

---

## Verdict & Certification
STATUS: APPROVED

All API-to-UI consumer contracts, error semantics, and frontend client bindings have been verified and certified. Handoff to `@rc-gate-2` for forensic QA gate review.
