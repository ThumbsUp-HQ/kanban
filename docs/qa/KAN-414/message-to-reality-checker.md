# Message to Reality-Checker: Forensic Audit Guide for KAN-414

**Author / Swarm Worker:** `b-kan414`  
**Target Ticket:** `KAN-414` (`[SLICE-2-P4][KB-AI-DOCS] Phase 4: Publish Verified AI Providers, Agents, mTLS Runners & Local Onboarding Wiki + In-App Docs`)  
**Parent Epic:** `KAN-410` (`[EPIC][SLICE-2-AI-AGENTS-RUNNERS]`) (Grade-A `READY` Certified on Round 1)  
**Upstream Phase Tickets:** `KAN-411` (Audit & Foundation), `KAN-412` (UI Workflows & Drawer Wiring), `KAN-413` (Live Workouts)  
**Branch:** `docs/KAN-414-slice2-ai-docs` (branched from `main` and merged with main `342bfdb6`)  
**Target Commit:** `3e215f87` (HEAD of `docs/KAN-414-slice2-ai-docs`)  
**Wiki Branch:** `docs/KAN-414-slice2-ai-docs` inside `./thumbs-up-kanban.wiki` (Commit: `ab0fd22`) and fetched into `/home/adamoutler/kanban/thumbs-up-kanban.wiki`  
**Zero Schema Mutations:** No database migrations added or modified in Phase 4.  
**Pre-Prod Safety Invariant:** Absolute zero-mutation on protected pre-production (`192.168.1.101` / `k.hackedyour.info`).  

---

## 1. Executive Summary & Forensic Scope

Ticket `KAN-414` delivers Phase 4 of Slice 2, completing authoritative documentation, wiki synchronization, and client-side help integration for the Multi-Provider AI Engine, Token Budgets, Autonomous Agents, Remote mTLS Runners, and Local `/llms.txt` Onboarding systems.

Every endpoint, parameter, button label, bitmask ceiling, and error response documented in this release was audited directly against source code in:
- `kanban/api/v1/admin/ai_providers.py` (`/probe-models`, `/test-connection`, `PUT /api/v1/admin/ai/providers/order`, `PUT /api/v1/admin/ai/budgets` with `token_cap=0` Hard AI Freeze vs `10_000_000_000` Unlimited Quota)
- `kanban/agents/schemas.py` (`ALLOWED_MCP_TOOLS` strictly 4 read-only tools: `search_tickets`, `read_ticket`, `search_knowledge`, `read_doc`; `display_name` 1 to 200 chars; `repo_access_mode` `none`, `ro_vfs_mount`, `bare_git_tools`)
- `kanban/api/v1/agent_definitions.py` (`:validate` 4-section trace: `=== 1. RENDERED CONTEXT ===`, `=== 2. TOOL TRACE ===`, `=== 3. LATENCY & TOKENS ===`, `=== 4. SCHEMA & POLICY STATUS ===`; `timeout_ms <= 300000` 300s ceiling from KAN-430)
- `kanban/runners/hub.py` (`DEAD_EVICTION_S = 45.0` seconds eviction)
- `kanban/api/v1/remote_runners.py` (`enrollment-tokens`, `:revoke`, mTLS PoP `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256}`)
- `agent/remote_runner/cli.py` (`0o700` state dir, `0o600` `client.key` & `ca.pem`, `0o644` `client.crt`; `kanban-agent-runner run` CLI)
- `kanban/ops/llms_txt.py` (`generate_llms_txt`, `generate_llms_full_txt`, onboarding prompt)
- `AiStudioPage.tsx`, `AiProviderEditorDrawer.tsx`, `AiBudgetModal.tsx`
- `AgentStudioPage.tsx`, `AgentDefinitionEditorDrawer.tsx`, `AgentValidationModal.tsx`
- `RunnerStudioPage.tsx`, `MintEnrollmentTokenModal.tsx`

### Core Source Code Parity Truths Verified
1. **Multi-Provider AI Architecture & Protocols:**
   - Unified `LLMProvider` interface (`agent/providers/base.py`) supporting Google Gemini (`gemini-2.5-flash`, `gemini-2.5-pro`), OpenAI (`gpt-4o`, `gpt-4o-mini`, compatible endpoints), and Air-Gapped Ollama (`llama3`, `deepseek-r1`, `qwen2.5`).
   - Secure server-side credential storage with zero browser exposure of raw API keys (0 `input[type="password"]` in client DOM).
   - Air-gap controls: provider creation and update requests for `openai` and `gemini` return HTTP 409 `AIR_GAP_EGRESS_DENIED`, while model probing and connection test endpoints return HTTP 200 OK with `{"ok": false, "error_code": "AIR_GAP_EGRESS_DENIED", ...}`.
   - Endpoint probe contracts: `POST /api/v1/admin/ai/providers/probe-models` (discovers model catalogs via secure backend proxy) and `POST /api/v1/admin/ai/providers/test-connection` (validates API reachability and latency).
   - Priority ordering managed via `PUT /api/v1/admin/ai/providers/order` (or `PUT /api/v1/workspaces/{ws}/ai-providers/order`).
   - Client certificate field: `mtls_client_cert_pem`.
   - Provider `display_name` bounds: `1 to 80 characters`.
2. **Token Budgets & Hard Freeze Boundaries:**
   - Granular monthly/daily token limits managed via `PUT /api/v1/admin/ai/budgets` (or `PUT /api/v1/workspaces/{ws}/ai-providers/budgets`).
   - Exact boundary values: `token_cap=0` triggers **Hard AI Freeze** (all agent operations halt immediately with `BudgetExceeded` until reset or incremented); `token_cap=10_000_000_000` represents **Unlimited Quota (No Cap)**.
   - Presets provide 1M, 5M, 25M, and 100M tokens. Exact button labels: `Enforce Token Cap`, `Unlimited Quota (No Cap)`, `0 (Freeze)`, `Save Token Cap`.
3. **Autonomous Agent Definitions & Validation Sandbox:**
   - Agent definitions support Workspace-scoped and Project-scoped execution with `display_name` bounded to `1 to 200 characters`.
   - Repository access modes strictly enforced: `none` (zero filesystem access), `ro_vfs_mount` (read-only mount in Linux namespace `CLONE_NEWNS`), and `bare_git_tools` (isolated read-only bare Git inspection tools).
   - Least-privilege MCP tool allowlist: strictly 4 read-only tools: `search_tickets`, `read_ticket`, `search_knowledge`, `read_doc` (zero `add_comment`; submitting unlisted tools fails schema validation with HTTP 422 `HARNESS_FIELDS_INVALID`).
   - Validation endpoint `POST /api/v1/agent-definitions/{id}:validate` executes a dry-run test returning an atomic 4-section trace:
     1. `=== 1. RENDERED CONTEXT ===`
     2. `=== 2. TOOL TRACE ===`
     3. `=== 3. LATENCY & TOKENS ===`
     4. `=== 4. SCHEMA & POLICY STATUS ===`
   - Strict reasoning ceiling enforced per `KAN-430`: `timeout_ms <= 300000` (300 seconds). Action button: `Test Validation`.
4. **Remote mTLS Runners Architecture & Cryptographic Security:**
   - Dedicated mTLS port `:8444` terminating mutual TLS handshakes.
   - Single-use enrollment tokens minted via `POST /api/v1/admin/agent-runners/enrollment-tokens` with maximum 15-minute TTL (`max_ttl_seconds <= 900`). Action button: `Generate Single-Use Token`.
   - Cryptographic Proof-of-Possession (PoP) header: `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256}`.
   - Nonce validation enforces 300s replay window (`abs(now - ts) <= 300`) with single-use nonce consumption.
   - File permission boundaries enforced by daemon: directory `0o700`, private key and CA bundle `0o600`, certificate `0o644`.
   - Heartbeat eviction in `hub.py`: `DEAD_EVICTION_S = 45.0` (`45 seconds`, missing marks runner offline).
   - Daemon start invocation: `uv run kanban-agent-runner run` (auto-detects runner config) or `uv run kanban-agent-runner run --config ~/.local/state/kanban-runner/runner.toml`.
   - Immediate runner revocation via `POST /api/v1/admin/agent-runners/{id}:revoke`. Action button: `1-Click Revoke (AAL2)`.
5. **Local-Folder `/llms.txt` Onboarding:**
   - Standard RFC-style discovery endpoint `/llms.txt` and full manifest `/llms-full.txt`.
   - Local onboarding prompt embeds quick-start instructions for Cursor, Windsurf, Claude Code, and Antigravity CLI (`agy`).
   - User preferences persisted via `PATCH /api/v1/users/me/preferences` (`agent_onboarding_prefs`) strictly within local project folder without modifying global user environments.
6. **Parallel-Safe Wiki Governance:**
   - Edits to `thumbs-up-kanban.wiki/Studio-Configuration-Reference.md` are strictly confined to Sections 8, 9, and 10 (lines 145-280).
   - Zero overlap with parallel Slices 1, 3, 4, or 5.
7. **Formatting & Visual Standards:**
   - Zero Unicode dashes (all em-dashes and en-dashes replaced with standard ASCII `-`).
   - Zero Mermaid `<br/>` tags in diagram node labels.
   - Zero backticks nested inside `**bold**` Markdown headings.
   - Numbered `1. 2. 3.` lists in Guides are completely uninterrupted by standalone code blocks or images, preventing `<ol>` list resets.

---

## 2. In-App Anchor Resolution & DocsCenter Verification

Per Coordinator directive #507, `DocMarkdownViewer.tsx` strips raw HTML `<a id="..."></a>` anchor tags and generates DOM element IDs strictly via `slugifyAnchor(rawTitle)` on Markdown `##` and `###` headings.

All 7 Slice-2 `StudioDocLink` and `FieldHelpHint` `docHref` anchors, plus all 3 Studio Configuration Reference section anchors, resolve with 100% fidelity:
1. `Multi-Provider-AI-Engine-and-Runners.md#supported-runtimes` -> resolves to `## Supported Runtimes`
2. `Multi-Provider-AI-Engine-and-Runners.md#execution-harnesses` -> resolves to `## Execution Harnesses`
3. `Multi-Provider-AI-Engine-and-Runners.md#remote-runners` -> resolves to `## Remote Runners`
4. `Multi-Provider-AI-Engine-and-Runners.md#repository-access` -> resolves to `## Repository Access`
5. `Multi-Provider-AI-Engine-and-Runners.md#budget-caps` -> resolves to `## Budget Caps`
6. `Multi-Provider-AI-Engine-and-Runners.md#multi-provider-benchmark-cutoff-timeout-guide` -> resolves to `## Multi-Provider Benchmark Cutoff Timeout Guide`
7. `Multi-Provider-AI-Engine-and-Runners.md#sampling-parameters` -> resolves to `## Sampling Parameters`
8. `Studio-Configuration-Reference.md#8-ai-providers-studio` -> resolves to `## 8. AI Providers Studio`
9. `Studio-Configuration-Reference.md#9-agent-definitions-studio` -> resolves to `## 9. Agent Definitions Studio`
10. `Studio-Configuration-Reference.md#10-remote-runners-studio` -> resolves to `## 10. Remote Runners Studio`

This is verified by automated unit tests `asserts resolveSectionElement resolves all Slice-2 AI and Runner docHref anchors` and `asserts resolveSectionElement resolves Studio-Configuration-Reference Slice-2 section anchors` in `kanban/web/src/features/docs-center/__tests__/DocsCenter.test.tsx` which passed with 0 errors.

---

## 3. Automated Test & Static Build Evidence

### Pytest Verification (`kanban/tests/test_wiki_bundle_sync.py`)
- **Total Tests:** 7 passed in 0.14s
- **Checks Verified:**
  - `test_wiki_and_public_images_sha256_parity`: 1:1 cryptographic parity between wiki and public images.
  - `test_zero_duplicate_numeric_prefix_collisions`: zero image prefix collisions.
  - `test_every_markdown_image_reference_resolves`: all markdown image references resolve to existing files.
  - `test_reject_external_image_links_in_wiki`: zero unapproved external image links.
  - `test_reject_unreferenced_orphan_images`: zero orphan images in `thumbs-up-kanban.wiki/images/`.
  - `test_sync_wiki_bundle_execution`: manifest generation and asset copying.
  - `test_feature_comparison_day2_clean_and_synced`: comparison matrix clean.

### Vitest Verification (`DocsCenter.test.tsx` & `DocsCenterImages.test.tsx`)
- **Total Tests:** 72 passed across 2 test files in 7.10s (DocsCenter: 51 tests; DocsCenterImages: 21 tests)
- **Branch Coverage:** 96.74% across `src/features/docs-center/` (Statements: 99.6%, Functions: 100%, Lines: 100%)
- **Zero Failures:** 100% passing.

### Static Gates & Linter Output
- `python3 scripts/check_no_dashes.py --all`: Clean (0 dashes found).
- `python3 scripts/check_no_dashes.py thumbs-up-kanban.wiki/Multi-Provider-AI-Engine-and-Runners.md thumbs-up-kanban.wiki/Studio-Configuration-Reference.md`: Clean (0 dashes found).
- `pnpm --dir kanban/web typecheck`: 0 errors.
- `pnpm --dir kanban/web lint`: 0 warnings, 0 errors.
- `pnpm --dir kanban/web build`: Clean production client in 1.29s.

---

## 4. Multi-Viewport Visual Verification (`docs/qa/KAN-414/screenshots/`)

All 15 screenshots were captured via Playwright against a live production build served on loopback port `18414` (serving compiled static bundle with zero mock routes) and audited via `read_file`:

| # | Screenshot Filename | Dimensions & Theme | Rendered Surface & Invariant Verification |
| :-: | :--- | :--- | :--- |
| 1 | `01-multi-provider-ai-engine-1440x900-desktop-light.png` | 1440x900 Light | Chapter 17: Multi-Provider AI Engine overview, breadcrumbs, tags, and TOC. |
| 2 | `01-multi-provider-ai-engine-1440x900-desktop-dark.png` | 1440x900 Dark | Chapter 17: Dark theme contrast, clean typography, right-side TOC navigation. |
| 3 | `01-multi-provider-ai-engine-1024x768-tablet-landscape.png` | 1024x768 Landscape | Tablet view with responsive sidebar and readable code callouts. |
| 4 | `01-multi-provider-ai-engine-768x1024-tablet-portrait.png` | 768x1024 Portrait | Portrait view with top drawer controls, collapsible chapter list. |
| 5 | `01-multi-provider-ai-engine-390x844-mobile-portrait.png` | 390x844 Mobile | Mobile portrait layout with wrap-safe code blocks and zero horizontal overflow. |
| 6 | `02-studio-config-ref-slice2-1440x900-desktop-light.png` | 1440x900 Light | Chapter 32: Section 8 AI Providers Studio configuration reference table centered. |
| 7 | `02-studio-config-ref-slice2-1440x900-desktop-dark.png` | 1440x900 Dark | Chapter 32: Section 8 dark theme table rendering with high contrast borders. |
| 8 | `02-studio-config-ref-slice2-1024x768-tablet-landscape.png` | 1024x768 Landscape | Tablet landscape layout with responsive table columns. |
| 9 | `02-studio-config-ref-slice2-768x1024-tablet-portrait.png` | 768x1024 Portrait | Tablet portrait layout with touch-accessible table rows. |
| 10 | `02-studio-config-ref-slice2-390x844-mobile-portrait.png` | 390x844 Mobile | Mobile portrait view with horizontally scrollable table container. |
| 11 | `03-slice2-mermaid-diagram-rendered-1440x900.png` | 1440x900 Light | Multi-Provider Engine Mermaid flowchart cleanly rendered with zero `<br/>` tags and zero box clipping. |
| 12 | `04-slice2-embedded-images-rendered-1440x900.png` | 1440x900 Light | Scrolled view: Budget Caps heading and embedded slice2 workout images rendered with full fidelity. |
| 13 | `05-studio-config-ref-section9-1440x900.png` | 1440x900 Light | Section 9 Agent Definitions Studio table cleanly centered, displaying `1 to 200 characters` and `none`, `ro_vfs_mount`, `bare_git_tools`. |
| 14 | `06-studio-config-ref-section10-1440x900.png` | 1440x900 Light | Section 10 Remote Runners Studio table cleanly centered, displaying `DEAD_EVICTION_S = 45.0`. |
| 15 | `07-multi-provider-ai-repo-access-table-1440x900.png` | 1440x900 Light | Scrolled view: Repository Access table and Remote Runner sequence diagram with Admin alias and zero text overlap. |

---

## 5. Specialist Reviews & Sign-Off Readiness

- **Dual Specialist Reviews:**
  - `@ui-spec` requested to audit documentation typography, contrast, responsive layouts, embedded image fidelity, list continuity, and `#anchor` UX navigation.
  - `@api-spec` requested to audit protocol accuracy, REST endpoints (`/probe-models`, `/test-connection`, `PUT /api/v1/admin/ai/providers/order`, `PUT /api/v1/admin/ai/budgets`, `:validate`, `enrollment-tokens`, `:revoke`), mTLS PoP header formats, and token boundaries.
- **Ready for Reality-Checker:** Upon specialist approvals, KAN-414 is 100% prepared for Grade-A `READY` certification.
