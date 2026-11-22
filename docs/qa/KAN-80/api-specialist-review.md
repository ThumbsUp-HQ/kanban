# API and Security Specialist Review: KAN-80

- **Ticket:** KAN-80 ([KB-LLMS-SKILLS-01]) - Add /llms.txt & /llms-skills/*.md Recommended Skills Catalog with Interactive 4-Axis Agent Onboarding Interview
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `feat/KAN-80-llms-skills-catalog`
- **Commit Under Audit:** `425082a1e5e0b3d6b48d2e1955ae864c14abdc1b (425082a1)` (`feat(llms): [KB-LLMS-SKILLS-01] Add /llms.txt & /llms-skills/*.md Recommended Skills Catalog with Interactive 4-Axis Agent Onboarding Interview (KAN-80)`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan80-e9d49b1d`
- **Status:** APPROVED

---

## 1. Executive API, Protocols, and Security Evaluation

Ticket KAN-80 establishes an in-memory cached, zero-database endpoint infrastructure for `/llms.txt`, `/llms-full.txt`, and `/llms-skills/{slug}.md`, coupled with a structured JSON skills catalog at `/api/v1/system/skills`.

Audited security, transport, and wire invariants:
1. **Zero-DB & Zero Host-Header Reflection Architecture (`kanban/ops/llms_txt.py`):**
   - Content is served strictly from immutable frozen dataclasses (`SkillAsset`) with `@functools.lru_cache(maxsize=1)`.
   - Host header reflection is prevented: host inputs are validated against strict RFC-compliant alphanumeric/colon allowlists, and any CRLF or control characters trigger an immediate RFC 7807 400 Bad Request ProblemDetails response.
   - Enforces hard runtime byte size bounds:
     - `/llms.txt`: 3,508 bytes (well under the 12,288-byte ceiling).
     - `/llms-full.txt`: 16,171 bytes (well under the 65,536-byte ceiling).
     - Skill markdown files: ~4-6 KB each (well under the 24,576-byte ceiling).
2. **HTTP Caching & Method Semantics:**
   - Responses emit `Cache-Control: public, max-age=300, must-revalidate` and `X-Content-Type-Options: nosniff`.
   - Generates deterministic SHA-256 ETags. Validates `If-None-Match` requests returning HTTP 304 Not Modified with zero content body.
   - Complete `HEAD` method support returning exact matching headers (`ETag`, `Content-Length`) without payload transfer.
   - Non-GET/HEAD methods return HTTP 405 Method Not Allowed with `Allow: GET, HEAD`.
3. **Strict Skills Allowlist & Traversal Defense:**
   - The `/llms-skills/{skill_slug}.md` router validates requested slugs against a strict allowlist: `{"kanban-workflow-setup", "kanban-ticket", "kanban-agent-manager", "reality-checker"}`.
   - Any path traversal (`../`), null bytes, unknown slugs, or missing `.md` extensions immediately return HTTP 404 ProblemDetails.
4. **Interactive 4-Axis Onboarding Workflow:**
   - Accurately guides agent interview across Axis 1 (Execution Topology), Axis 2 (Token Budget & Model Tier), Axis 3 (QA, Coverage & CI Rigor), and Axis 4 (Persistence Scope).
5. **Reverse Proxy & Routing Hygiene:**
   - Mounted in `kanban/app.py` before `PrecompressedSPAStaticApp` to prevent static SPA catch-all hijacking.
   - Added `"/llms*"` to `disallowed_prefixes` in `kanban/web_static.py`.
   - Caddy edge configured to reverse proxy `/llms*` directly to `kanban-api:8000`.

---

## 2. Wire Contracts & Security Invariants

### A. Endpoint Wire Contracts
- `GET /llms.txt`: `text/plain; charset=utf-8` returning concise index and onboarding entry point.
- `GET /llms-full.txt`: `text/plain; charset=utf-8` returning comprehensive specifications and catalog.
- `GET /llms-skills/{slug}.md`: `text/markdown; charset=utf-8` returning canonical Markdown skill instructions.
- `GET /api/v1/system/skills`: `application/json` returning `LlmsSkillsCatalogResponse` with complete SHA-256 hashes, byte sizes, and estimated token counts.

### B. Anti-Enumeration & Tenancy
- Endpoints return system-level platform capabilities and public agent skills without revealing private workspace data or user principals.

---

## 3. Unit Test Coverage & Verification Metrics

- **Backend Pytest Results:** 7 passed in 5.77s (`kanban/tests/api/test_llms_txt.py`).
- **Backend Coverage:** 100% statement and branch coverage on `kanban/ops/llms_txt.py` (126/126 statements, 20/20 branches).
- **Frontend Vitest Results:** 58 passed across `AboutPage.test.tsx`, `McpConfigSnippetModal.test.tsx`, and `DocsCenter.test.tsx`.
- **Static Quality Checks:**
  - `ruff check`: All checks passed (0 errors).
  - `ruff format`: 5 files checked and formatted.
  - `mypy`: 0 issues found in 4 source files.
  - `tsc -b --noEmit`: 0 errors.
  - `eslint`: 0 warnings, 0 errors.
  - `vite build`: Clean production build.
  - `check_no_dashes`: Clean across all changed and repository files (0 violations).

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review and routing to `@merge-ci`.

## Live Zero-Mock Playwright Screenshots (Captured on main @ 425082a1e5e0b3d6b48d2e1955ae864c14abdc1b)
- `docs/qa/KAN-80/screenshots/01-desktop-light-about-llms-txt.png` (1440x900 Light)
- `docs/qa/KAN-80/screenshots/02-desktop-dark-about-llms-txt.png` (1440x900 Dark)
- `docs/qa/KAN-80/screenshots/03-tablet-about-llms-txt.png` (768x1024 Tablet)
- `docs/qa/KAN-80/screenshots/04-mobile-portrait-about-llms-txt.png` (390x844 Mobile Portrait)
- `docs/qa/KAN-80/screenshots/05-mobile-landscape-about-llms-txt.png` (844x390 Mobile Landscape)
- `docs/qa/KAN-80/contract-sample.json` (Live `/llms.txt` and `/api/v1/system/skills` wire capture)
