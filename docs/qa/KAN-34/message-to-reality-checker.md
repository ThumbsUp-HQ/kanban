# Forensic Verification Packet: KAN-34

**Ticket:** KAN-34 (`[KB-ABOUT-SBOM] Add Buried About 👍kanban Page (/about) with Tagline, Swagger/ReDoc API Docs Links, Apache-2.0 License, and CycloneDX 1.5 SBOM`)  
**Target Branch:** `feat/KAN-34` (branched from base commit `23ae056d`)  
**Author:** `@b-kan34`  
**Status:** READY FOR QA GATE AUDIT  

---

## 1. Executive Summary & Problem Resolution

KAN-34 addresses all 4 scoped problems defined in the ticket specification:

1. **Problem 1: Standalone SBOM Generator (`kanban/ops/sbom.py`):**
   - Implemented runtime discovery of Python distributions via stdlib `importlib.metadata.distributions()`.
   - Extracted SPDX expressions, normalized license classifiers, and `WITH` license exception expressions.
   - Evaluated components against `ALLOW_SET` and `license-allowlist.toml` (returning `ALLOW`, `ALLOWLISTED`, `DENY`, or `UNKNOWN`).
   - Integrated web frontend dependencies from build-time `dist/sbom-web.json` (generated via Vite plugin `generateSbomWebPlugin`), with clean fallback to `package.json` + `pnpm-lock.yaml`.
   - Serialized valid CycloneDX 1.5 JSON (`bomFormat="CycloneDX"`, `specVersion="1.5"`).
   - Generated package PURLs: `pkg:pypi/{name}@{version}` for Python and `pkg:npm/{name}@{version}` (with percent-encoded scopes like `%40tanstack/react-query`) for Node.
   - Verified reading of verbatim repository `LICENSE` and `NOTICE` files with clean empty-string fallback.
   - Updated `Dockerfile` runtime-slim stage to `COPY --chown=65532:65532 LICENSE NOTICE license-allowlist.toml /opt/kanban/`.

2. **Problem 2: Authenticated REST System API Endpoints (`kanban/api/v1/system.py`):**
   - Added `GET /api/v1/system/about` requiring authenticated principal (`Depends(get_principal)` -> HTTP 401 on unauthenticated access).
   - Returns platform metadata:
     * `platform="👍kanban"`
     * `slug="thumbs-up-kanban"`
     * `tagline="The difference between a swarm and an Agile team is a kanban."`
     * `version="2.0.0"`
     * `license_spdx="Apache-2.0"`
     * `api_docs_urls={"swagger_ui": "/api/docs", "redoc": "/api/redoc", "openapi_json": "/api/openapi.json"}`
     * `license` (verbatim Apache-2.0 text)
     * `notice` (verbatim third-party notice text)
     * `sbom_summary` (totals, ecosystem counts, license verdict counts)
     * `components[]` (name, version, ecosystem, purl, license, verdict, scope, description)
   - Added `GET /api/v1/system/sbom` returning valid CycloneDX 1.5 JSON with `X-Content-Type-Options: nosniff`. When `?download=true` is requested, sets `Content-Disposition: attachment; filename="thumbs-up-kanban-sbom-cdx-1.5.json"`.
   - Verified in `kanban/app.py` that `/api/docs` (Swagger UI), `/api/redoc` (ReDoc), and `/api/openapi.json` (OpenAPI Spec) all resolve HTTP 200 on the live application.
   - Mounted `system_router` alongside `system_status_router` in `kanban/api/v1/__init__.py` without route collisions.

3. **Problem 3: Buried Navigation Entry Points & Route Registration:**
   - Registered `/about` (`<AboutPage />`) and `/settings/about` (`<Navigate to="/about" replace />`) in `kanban/web/src/app/routes.tsx` inside `RootShellLayout`.
   - Updated `computeCurrentSection` in `kanban/web/src/app/AppShell.tsx` to map `/about` to `'About'` breadcrumb.
   - Added buried navigation links visible to authenticated users:
     * `Topbar.tsx`: `ℹ️ About 👍kanban` (`data-testid="topbar-about-link"`) placed directly above the final logout divider.
     * `Sidebar.tsx`: `.kb-sidebar-footer` with muted `ℹ️ v2.0.0` link (`data-testid="sidebar-about-link"`).
     * `CommandPalette.tsx`: `About 👍kanban (License, API Docs & SBOM)` navigation command (`category: 'navigate'`).
     * `PersonalSettingsPage.tsx`: Muted footer link to `/about` (`data-testid="personal-settings-about-link"`).

4. **Problem 4: Frontend `AboutPage.tsx` & `AboutPage.css`:**
   - 0 inline styles (`style={...}`); 100% canonical CSS tokens (`cssTokensAudit.test.ts` passed 4/4).
   - Hero card: `[👍] 👍kanban`, version badge, `Apache-2.0` badge, prominent tagline `"The difference between a swarm and an Agile team is a kanban."` (`data-testid="about-tagline"`), and `Download CycloneDX 1.5 SBOM` button (`data-testid="download-sbom-btn"`).
   - REST API & OpenAPI Documentation section (`data-testid="about-api-docs-section"`):
     * Swagger UI (`/api/docs`) link (`data-testid="about-swagger-link"`) with `target="_blank"` and `rel="noopener noreferrer"`.
     * ReDoc (`/api/redoc`) link (`data-testid="about-redoc-link"`) with `target="_blank"` and `rel="noopener noreferrer"`.
     * OpenAPI Spec (`/api/openapi.json`) link (`data-testid="about-openapi-link"`) with `target="_blank"` and `rel="noopener noreferrer"`.
   - Supply-Chain metrics summary cards (total, python, web, permissive, allowlisted, denied).
   - Interactive SBOM table:
     * Search input filtering by package name, license, or PURL (`data-testid="sbom-search-input"`).
     * Ecosystem tabs (`All`, `Python`, `Web`).
     * Scope toggle (`Scope: Runtime Only` / `Scope: All (Inc. Dev)`).
     * Verdict pill indicators (`ALLOW`, `ALLOWLISTED`, `DENY`, `UNKNOWN`).
   - Verbatim License & Notice Viewer:
     * Tabs switching between `Apache-2.0 License` and `Third-Party NOTICE` (`data-testid="tab-apache-license"`, `data-testid="tab-third-party-notice"`).
     * `Copy License` button (`data-testid="copy-license-btn"`) with temporary `"Copied!"` indicator.

---

## 2. Verification Artifacts & Evidence Checklist

All raw forensic proofs are saved in `docs/qa/KAN-34/`:

| Artifact | Description | Status |
|:---|:---|:---:|
| `docs/qa/KAN-34/unit-test-results.txt` | Verbatim Pytest (29 passed, 97% cov) and Vitest (25 passed, 100% lines cov) logs | PASS |
| `docs/qa/KAN-34/build-or-typecheck.txt` | Verbatim ruff, mypy, lint-imports, license gate, check_no_dashes, tsc -b, eslint, vite build logs | PASS |
| `docs/qa/KAN-34/changed-files-manifest.txt` | Comprehensive manifest of all created/modified files | PASS |
| `docs/qa/KAN-34/git-diff.patch` | Scoped git diff against base commit 23ae056d (127 KiB) | PASS |
| `docs/qa/KAN-34/message-to-reality-checker.md` | This verification packet (0 em/en-dashes) | PASS |

---

## 3. Test Coverage & Quality Gates

### A. Python Backend (Pytest + Coverage)
- **Suite:** `kanban/tests/ops/test_sbom.py` (22 tests) + `kanban/tests/api/test_system_about.py` (7 tests) = **29 tests passed in 15.38s**.
- **Coverage:**
  * `kanban/api/v1/system.py`: **100%** coverage (115/115 statements, 2/2 branches).
  * `kanban/ops/sbom.py`: **97%** coverage (333/339 statements, 116/126 branches).
  * Combined: **97%** coverage (threshold is >=95%).

### B. Web Frontend (Vitest + Coverage)
- **Suite:** `aboutApi.test.ts` (2 tests), `AboutPage.test.tsx` (7 tests), `sbom.test.ts` (7 tests), `AboutNavigation.test.tsx` (5 tests), `cssTokensAudit.test.ts` (4 tests) = **25 tests passed in 4.19s**.
- **Coverage:**
  * `kanban/web/build/sbom.ts`: **100%** Stmts, **100%** Branch, **100%** Funcs, **100%** Lines.
  * `kanban/web/src/features/about/AboutPage.tsx`: **100%** Stmts, **95.45%** Branch, **100%** Funcs, **100%** Lines.
  * `kanban/web/src/features/about/aboutApi.ts`: **100%** Stmts, **100%** Branch, **100%** Funcs, **100%** Lines.
  * Combined: **100%** Statements, **97.63%** Branch, **100%** Funcs, **100%** Lines (threshold is >=95%).
- **Warning Count:** 0 `act(...)` stderr warnings, 0 console errors.

### C. Static & Architecture Quality Gates
1. **Ruff Linter:** `uv run ruff check .` -> `All checks passed!` (0 errors).
2. **Ruff Formatter:** `uv run ruff format --check .` -> `1920 files already formatted` (0 reformats needed).
3. **Mypy Typechecker:** `uv run mypy kanban/ops/sbom.py kanban/api/v1/system.py kanban/tests/ops/test_sbom.py kanban/tests/api/test_system_about.py` -> `Success: no issues found in 4 source files`.
4. **Import Layering Contracts:** `uv run lint-imports` -> `Contracts: 2 kept, 0 broken` (agent -> mcp -> kanban -> database).
5. **License Gate:** `uv run python -m scripts.license_gate` -> `SUMMARY python=116 node=1 violations=0` (0 new dependencies, 0 copyleft violations).
6. **No-Dashes Audit:** `python3 -m scripts.check_no_dashes --all` -> 0 violations.
7. **TypeScript Build:** `pnpm --dir kanban/web exec tsc -b --noEmit` -> 0 errors.
8. **ESLint:** `pnpm --dir kanban/web exec eslint ... --max-warnings 0` -> 0 errors, 0 warnings.
9. **CSS Tokens Audit:** `src/styles/__tests__/cssTokensAudit.test.ts` -> 4/4 passed (100% canonical tokens, 0 inline styles).
10. **Vite Production Build:** `pnpm --dir kanban/web build` -> built in 1.65s, generated `dist/sbom-web.json` (13 KiB).

---

## 4. Definition of Done Attestation

The implementation satisfies all criteria:
- [x] Zero external runtime dependencies introduced.
- [x] Zero em-dashes or en-dashes present in code, comments, or documentation.
- [x] All 4 scoped problems implemented with >=95% unit test coverage.
- [x] CycloneDX 1.5 JSON spec compliant with Content-Disposition attachment download.
- [x] Verbatim build and test logs recorded in `docs/qa/KAN-34/`.
