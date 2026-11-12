# Dependency Evaluation: KANBA-92 (KB-P3-33)

## Ticket Overview
- **Ticket ID**: KANBA-92 (`KB-P3-33`: `[Phase 3 / Frontend] Typed OpenAPI client, TanStack Query keys, optimistic mutations & realtime WS/SSE client`)
- **Status**: Pre-Flight Approved and Validated
- **Module**: `kanban/web`

---

## 1. Evaluated Dependencies

### `@tanstack/react-query`
- **Ecosystem**: Node / npm
- **Package**: `@tanstack/react-query`
- **Exact Version**: `5.67.1`
- **License**: MIT (100% Apache-2.0 compatible, permissive)
- **Role**: Runtime asynchronous server-state cache, optimistic mutations, query lifecycle coordination, and realtime cache invalidation.
- **Lockfile Integrity (SHA-512)**: `sha512-fH5u4JLwB6A+wLFdi8wWBWAYoJV5deYif2OveJ26ktAWjU499uvVFS1wPWnyEyq5LvZX1MZInvv9QRaIZANRaQ==`
- **Pre-Flight Swarm Approvals**:
  * Architect Reviewer: Board #116, #167 (APPROVED)
  * Security Engineer: Board #118, #170 (APPROVED)
  * QA / Build Engineer: Board #120, #178 (APPROVED)

### `openapi-typescript`
- **Ecosystem**: Node / npm (devDependencies)
- **Package**: `openapi-typescript`
- **Exact Version**: `7.6.1`
- **License**: MIT (100% Apache-2.0 compatible, permissive)
- **Role**: Build-time static TypeScript interface generator converting FastAPI `openapi.json` into type-safe contract definitions in `src/api/schema.gen.ts`.
- **Lockfile Integrity (SHA-512)**: `sha512-F7RXEeo/heF3O9lOXo2bNjCOtfp7u+D6W3a3VNEH2xE6v+fxLtn5nq0uvUcA1F5aT+CMhNeC5Uqtg5tlXFX/ag==`
- **Pre-Flight Swarm Approvals**:
  * Architect Reviewer: Board #116, #167 (APPROVED)
  * Security Engineer: Board #118, #170 (APPROVED)
  * QA / Build Engineer: Board #120, #178 (APPROVED)

---

## 2. Supply-Chain and License Compliance

- **Permissive License Mandate**: Both packages are published under the MIT license, with zero copyleft (GPL, AGPL, SSPL, LGPL) clauses.
- **Supply-Chain Verification**:
  * Exact version pinning in `kanban/web/package.json`.
  * Cryptographic SHA-512 integrity hashes enforced by `pnpm-lock.yaml`.
  * `make license` (`uv run python -m scripts.license_gate`) validates clean permissive status (`violations=0`).
- **Zero Runtime Script/Style Injection**: Neither dependency injects inline `<style>` or `<script>` tags, ensuring 100% adherence to the application's strict `Content-Security-Policy`.

---

## 3. Architectural Rationale & Alternatives Considered

1. **`@tanstack/react-query`**:
   * **Selected**: Industry-standard server-state manager offering structured cache keys (`queryKeys.ts`), optimistic mutation rollbacks with snapshot restoration, window focus refetching, and seamless integration with custom WebSocket/SSE clients.
   * **Alternative: Hand-written `fetch` Cache**: Lacks unified stale-while-revalidate semantics, window-focus revalidation, automatic deduping of concurrent in-flight requests, and robust mutation rollback lifecycles. High risk of state desynchronization and race conditions.
   * **Alternative: `swr` (MIT)**: Lacks first-class mutation lifecycles (`onMutate`, `onError`, `onSettled`), query key factory structures, and explicit cache snapshotting necessary for sub-12ms optimistic board updates.
   * **Alternative: `orval` (MIT)**: Couples client generation with TanStack Query hooks generation, creating complex intermediate build layers and inflexible hook signatures compared to decoupled openapi-typescript + typed apiFetch.

2. **`openapi-typescript`**:
   * **Selected**: Pure type generator producing zero runtime JavaScript bundle overhead. Converts JSON Schema/OpenAPI 3.1 definitions directly into high-fidelity TypeScript AST types (`schema.gen.ts`).
   * **Alternative: OpenAPI Generator CLI (Java)**: Requires heavy Java JRE runtime dependencies in development containers and CI.
   * **Alternative: Swagger Codegen / Restful-React**: Generates bulky runtime fetch clients with opinionated wrappers that break CSRF cookie handling and custom error mapping.

---

## 4. Specialist Sign-Offs

- **Security Engineer (sec-eng)**: APPROVED (Board #118, #170)
- **Systems/Backend Architect (arch-reviewer)**: APPROVED (Board #116, #167)
- **Test & Build Quality Engineer (qa-eng)**: APPROVED (Board #120, #178)
