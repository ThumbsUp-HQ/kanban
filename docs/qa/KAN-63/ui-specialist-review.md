# UI & UX Specialist Review: KAN-63 (`[KB-SEC-CODEX-01]`)

- **Reviewer Persona:** `ux-architect` / `ui-designer` (UI/UX Specialist Reviewer)
- **Ticket:** `KAN-63` (`[KB-SEC-CODEX-01] De-Expose Public /api/v1/internal MCP Routes, Enforce Role-Bound HMAC Service Auth, & Bind Ephemeral Minting to Active Executions (CWE-290/345/862)`)
- **Audited Commit (`HEAD`):** `882b800923188414a984939148f63902b30beeff` (`882b8009`, merging `fb3b87ae996bc49b57b2faa7321074321dfb7b93`)
- **Audited Branch:** `main` (merged from `feat/KAN-63-internal-service-auth`)
- **Reviewed Artifacts:**
  - `docs/qa/KAN-63/git-diff.patch`
  - `docs/qa/KAN-63/contract-sample.json`
  - `docs/qa/KAN-63/unit-test-results.txt`
  - `docs/qa/KAN-63/build-check.txt`
  - `docs/qa/KAN-63/api-specialist-review.md`
  - `docs/qa/KAN-63/message-to-reality-checker.md`
- **Reviewed Frontend API Contracts & Client Schemas:**
  - `kanban/web/openapi.json`
  - `kanban/web/src/api/schema.gen.ts`
  - `kanban/api/v1/__init__.py`
  - `kanban/app.py`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-63` hardens internal service-to-service MCP communication channels by removing internal routes from the public FastAPI application, enforcing role-bound HKDF-HMAC service authentication, and binding ephemeral token minting to active workflow executions.

From a UI/UX, client schema, and frontend surface perspective:
1. **Clean Public API Surface & OpenAPI Parity:** Internal service endpoints (`/internal/v1/mcp/*`, `/api/v1/internal/*`) have been cleanly removed from the public OpenAPI documentation (`kanban/web/openapi.json`) and TypeScript schema definitions (`kanban/web/src/api/schema.gen.ts`). Running `pnpm --dir kanban/web run check:api` confirms 0 differences and 0 stale internal definitions.
2. **Zero Client Breaking Changes:** Public web application features (boards, views, notifications, settings, and OAuth/auth cards) have zero dependencies on internal service routes. Client typecheck (`pnpm typecheck`), linting (`pnpm lint`), and production build (`pnpm build`) execute cleanly with 0 errors.
3. **Consistent Error Presentation:** Public access attempts to `/internal` or `/internal/*` routes return standardized RFC 9457 `404 Not Found` JSON payloads, preventing information disclosure or unintended route probing from the browser console.
4. **Security & Content Policy Alignment:** Complies fully with strict Content Security Policy invariants. Zero inline styles, zero `dangerouslySetInnerHTML`, and zero unauthenticated client surface leakage.
5. **Typography & Prose Hygiene:** Zero em-dashes or en-dashes (U+2014 / U+2013) exist in documentation or client schemas.

---

## 2. Frontend Contract & Schema Audit

### 2.1 Public OpenAPI Specification (`kanban/web/openapi.json`)
- Verified that all paths beginning with `/api/v1/internal/` and `/internal/` have been excised from the public contract specification.
- Public developer documentation (`/docs`, `/redoc`) and API consumers cannot observe internal service endpoints or their parameter schemas.

### 2.2 Generated TypeScript Types (`kanban/web/src/api/schema.gen.ts`)
- The generated TypeScript type interfaces match the pruned OpenAPI schema exactly.
- No unused internal types pollute the client build, maintaining a lean bundle size.

---

## 3. Test Coverage & Verification

- **Pytest Suite Execution:** 42 passed in 14.41s across all security suites (internal route isolation, ephemeral token minting, MCP internal client auth).
- **Module Coverage:** 97% total coverage across all touched modules (service_auth 99%, ephemeral_mcp_tokens 97%, mcp_ephemeral 96%, mcp_introspect 99%).
- **Frontend Checks:**
  - `pnpm --dir kanban/web run check:api`: 0 errors
  - `pnpm --dir kanban/web run build`: 0 errors (clean Vite/Rolldown production build)
  - `uv run python -m scripts.check_no_dashes --all`: 0 errors (0 em/en-dashes)

---

## 4. Review Sign-Off

The internal route isolation, OpenAPI contract pruning, client type generation, and security boundaries satisfy all UI/UX and architectural requirements.

**STATUS: APPROVED**
