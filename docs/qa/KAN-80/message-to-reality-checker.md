# KAN-80 Forensic QA Dossier: /llms.txt & /llms-skills/*.md Recommended Skills Catalog with Interactive 4-Axis Agent Onboarding Interview

## Overview
- Ticket ID: KAN-80
- Spec: [KB-LLMS-SKILLS-01] Add /llms.txt & /llms-skills/*.md Recommended Skills Catalog with Interactive 3-Axis Agent Onboarding Interview
- Branch: `feat/KAN-80-llms-skills-catalog`
- Base Commit (`main`): `043991e311037287943dc0d919d1fc5d5e8ad150` (`043991e3`)
- Workspace: `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan80-e9d49b1d`

## Forensic Summary of Solved Problems

### Problem 1: In-Memory Cached Zero-DB /llms.txt and /llms-full.txt
- Implemented `kanban/ops/llms_txt.py` with `@functools.lru_cache(maxsize=1)` static templates.
- Zero-DB queries and zero Host-header reflection: served directly from immutable frozen dataclasses (`SkillAsset`).
- Strict byte limits verified and enforced via hard runtime guards:
  - `/llms.txt`: 3,508 bytes (limit <= 12,288 bytes).
  - `/llms-full.txt`: 16,171 bytes (limit <= 65,536 bytes).
- Standardized HTTP semantics:
  - `Content-Type: text/plain; charset=utf-8`
  - `Cache-Control: public, max-age=300, must-revalidate`
  - `X-Content-Type-Options: nosniff`
  - SHA-256 ETag generation with `If-None-Match` returning `304 Not Modified` and zero body.
  - Complete `HEAD` method support with matching `ETag` and `Content-Length`.
  - Disallowed methods (`POST`, `PUT`, `DELETE`, etc.) return `405 Method Not Allowed` with `Allow: GET, HEAD`.
  - Malformed Host header with CRLF / control characters rejected with `400 Bad Request` RFC 7807 `ProblemDetails`.

### Problem 2: Recommended Skills Catalog and Markdown Endpoints
- Implemented `/llms-skills/{skill_slug}.md` route serving raw canonical markdown:
  - Allowed skills allowlist: `{"kanban-workflow-setup", "kanban-ticket", "kanban-agent-manager", "reality-checker"}`.
  - Strict byte budget: each skill is ~4,000 to ~6,000 bytes (limit <= 24,576 bytes).
  - `Content-Type: text/markdown; charset=utf-8`
  - ETag and 304 conditional validation.
  - Path traversal attempts, non-allowed slugs, or missing `.md` extensions immediately return `404 Not Found` RFC 7807 `ProblemDetails`.
- Implemented `/api/v1/system/skills` endpoint returning `LlmsSkillsCatalogResponse` containing complete metadata (`slug`, `title`, `summary`, `install_path`, `url`, `sha256`, `bytes`, `estimated_tokens`) and formatted 1-click agent onboarding prompt.

### Problem 3: Mandatory Interactive 4-Axis Agent Onboarding Interview
- Embodied the strict "Interview Before Writing Skills" workflow into `/llms.txt`, `/llms-full.txt`, and `kanban-workflow-setup.md`:
  - Axis 1 (Execution Topology): `[1A] Single-Threaded Agent (Solo Execution)`, `[1B] Teamwork (Coordinator + Sub-Agents) [Recommended]`, `[1C] Multi-Agent Swarm (Parallel Worktree Builders)`.
  - Axis 2 (Token Budget & Model Tier): `[2A] Quota-Sipping Flash 3.8 / Haiku [Recommended]`, `[2B] Balanced Hybrid (Sonnet / Argon + Flash / Haiku)`, `[2C] Unconstrained Sol MAX / Claude Ultra / Gemini Carbon`.
  - Axis 3 (QA, Coverage & CI Rigor): `[3A] Pragmatic Baseline (>=80%)`, `[3B] Clean-Room Forensic reality-checker + >=95% Coverage [Recommended]`.
  - Axis 4 (Persistence Scope): `[4A] Project Workspace Only`, `[4B] Global User Workstation`, `[4C] Both Project & Global [Recommended]`.

### Problem 4: Server Routing, Reverse Proxy, and Package Inclusion
- `kanban/app.py`: Mounted `mount_llms_routes(app)` prior to `PrecompressedSPAStaticApp` to prevent static catch-all intercept.
- `kanban/web_static.py`: Added `"/llms.txt"`, `"/llms-full.txt"`, and `"/llms-skills"` to `disallowed_prefixes`.
- `deploy/caddy/Caddyfile`: Added `handle /llms* { reverse_proxy kanban-api:8000 }` route.
- `kanban/pyproject.toml`: Updated wheel packaging to explicitly include markdown and text files: `include = ["*.py", "**/*.py", "*.md", "**/*.md", "*.txt", "**/*.txt"]`.

### Problem 5: Frontend UI Discovery Touchpoints & Ergonomics
- `AboutPage.tsx` & `AboutPage.css`: Added `about-llms-txt-card` with direct links to `/llms.txt` and `/llms-full.txt` and `copy-llms-onboarding-prompt-btn` with clipboard feedback.
- `McpAccessStudio.tsx` & `McpAccessStudio.css`: Added `mcp-llms-txt-callout` and `mcp-copy-llms-prompt-btn`.
- `McpConfigSnippetModal.tsx` & `McpConfigSnippetModal.css`: Added `mcp-llms-txt-callout` and `mcp-copy-llms-prompt-btn` with `promptCopied` state feedback.
- `DocsCenterPage.tsx` & `DocsCenterPage.css`: Added `docs-llms-txt-link` in the header bar.
- `kanban/api_docs.py`: Added `Agent /llms.txt` navigation links to Swagger UI topbar, Swagger spec-links, and ReDoc sidebar.
- Zero inline `style={{...}}` used; strict CSS classes utilized across all touchpoints.

### Security and Quality Invariants
- Zero non-ASCII em-dashes (U+2014) or en-dashes (U+2013) across all files (verified via `scripts.check_no_dashes --all`).
- Zero UTF-16 surrogates (U+D800..U+DFFF).
- Zero Host-header injection vulnerabilities.
- Strict RFC 7807 ProblemDetails compliance.
- 100% unit test coverage on `kanban/ops/llms_txt.py`.

## Verification Evidence & Test Artifacts
- Unit Test Log: `docs/qa/KAN-80/unit-test-results.txt` (7 backend pytest passed, 100% coverage on `kanban.ops.llms_txt`; 58 frontend vitest passed across `AboutPage`, `McpConfigSnippetModal`, and `DocsCenter`).
- Static Build & Linter Log: `docs/qa/KAN-80/build-or-typecheck.txt`:
  - Frontend typecheck (`tsc -b --noEmit`): clean
  - Frontend eslint (`eslint . --max-warnings 0`): 0 warnings, 0 errors
  - Frontend production build (`tsc -b && vite build`): clean build
  - Ruff check: 0 errors
  - Ruff format: 5 files checked and clean
  - Mypy: 4 source files checked and clean
  - No dashes check (`scripts.check_no_dashes --all`): 0 errors
- Git Diff Patch: `docs/qa/KAN-80/git-diff.patch`
- Manifest: `docs/qa/KAN-80/changed-files-manifest.txt`
