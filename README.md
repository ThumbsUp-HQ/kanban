# 👍kanban (`thumbs-up-kanban`)

**`👍kanban`** is an open-source (`Apache-2.0`), **Security-First (Priority #0), Agent-First (Priority #1)** Kanban, Ticketing, and Knowledge Platform built to replace seat-taxed AI paywalls and CRUD-wrapper MCP context bloat.

---

## Feature Comparison: `👍kanban` vs Legacy & Modern Trackers

> **"A kanban is just a kanban until you start digging deeper."**
>
> On the surface, every tracker presents identical columns, draggable cards, and basic workflow states. The real architectural divergence begins the moment you inspect paywalled enterprise controls, database-level security invariants, canonical Markdown integrity, and native agent/MCP execution gates. While commercial SaaS and copyleft alternatives lock custom properties, audit logs, Single Sign-On, and AI integrations behind steep per-seat subscription tiers or bloated CRUD APIs, `👍kanban` ships an uncompromising, security-first, agent-first platform under a pure Apache-2.0 license.

See the complete 46-feature technical evaluation matrix comparing `👍kanban` against Jira, Plane, GitHub, Vibe Kanban, OpenAI Symphony, Businessmap, and Codebeamer across Security/Identity/Audit, Agentic MCP/AI Workflows, Issue Tracking, Docs/Stickies/Markdown, and Orchestration/Provenance/Day-2 Operations:
- **Repository Specification (46-Feature Matrix & Intentional Non-Goals):** [`docs/FEATURE_COMPARISON.md`](./docs/FEATURE_COMPARISON.md)
- **Project Wiki:** [Feature Comparison Matrix](https://git.adamoutler.com/AI/thumbs-up-kanban/wiki/Feature-Comparison)

---

## GitHub Issue #1 Resolution: The 4 Core Architectural Pillars

Addressing **GitHub Issue #1** ("World-Class Kanban Platform: Security-First, Agent-First"), `👍kanban` provides full enterprise competitive parity and superiority over legacy tools (Jira, Plane, Vibe Kanban) across four uncompromising pillars:

- **Pillar 1: Native Agent-First Architecture (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`):** Three isolated intent-driven MCP surfaces replace context-collapsing CRUD-wrapper schemas (slashing schema size from 45,000+ tokens to <= 1,800 tokens). Structured Level of Detail (LOD) tiers (`summary`, `standard`, `full`) ensure summary tool responses stay strictly under 1,000 tokens (< 4,000 characters) to prevent context exhaustion in autonomous coding agents (Claude Code, OpenAI Codex, Gemini CLI / Antigravity). Supports zero-shell stdin CLI pipes (`agy -p`, `codex exec -s read-only -`), vendor-neutral LLM providers (`openai`, `ollama`, `gemini`), and outbound mTLS remote repo runners.
- **Pillar 2: Priority #0 Hardened Security:** Hardware-enforced PostgreSQL 16 `FORCE ROW LEVEL SECURITY` (`NOBYPASSRLS`) across all tenant tables, fail-closed zero-context queries, hostile Unicode UTF-16 lone-surrogate rejection (`0xD800 <= ord(c) <= 0xDFFF`), hidden-DOM paste-jacking pruning, zero plaintext secrets (AES-256-GCM envelope encryption with ephemeral in-memory zeroing), `Depends(require_admin_aal2)` on all admin routes, and strict `Content-Security-Policy`.
- **Pillar 3: Friction-Free FOSS Deployment:** Permissive `Apache-2.0` license with zero commercial AI paywalls, zero seat taxes, and zero cloud telemetry. Delivers both a 1-command zero-config single-container standalone runtime (`docker run -p 8080:8080 thumbs-up-kanban:latest` with embedded Unix-socket PostgreSQL 16 and sub-3-second cold start) and a hardened production 5-network container stack (`docker compose up -d`).
- **Pillar 4: Enterprise Whitespace & High-Ergonomics UI:** 3-pane split view, sub-16ms optimistic drag-and-drop state transitions, breathable enterprise spatial layout (52px topbar, 324px columns, 46px list rows, 960px peek drawer with 640px prose + 320px properties rail), standardized 21-emoji `<EmojiHint>` hover tooltips, 100% canonical UTF-8 Markdown storage, and inline blinking Sparkle (`✨`) completion with surgical right-click contextmenu accept.

---

## Monorepo Module Topology (`[kanban, database, mcp, agent]`)

| Module | Responsibility | Manifest |
| :--- | :--- | :--- |
| [`database/`](./database/) | Universal Object Graph (`objects` UUIDv7 spine, 13 typed `object_links`, `audit_object_links()` & Purger), canonical Markdown DDL, `FORCE RLS`, and SHA-256 `activity_records`. | [`database/GEMINI.md`](./database/GEMINI.md) |
| [`kanban/`](./kanban/) | FastAPI (`title="👍kanban API"`) REST/WS/SSE server, Multi-Card Auth Studio, Rust `nh3` + SVG sanitizer, `/api/v1/media-proxy`, and Vite + React 19 SPA (`kanban/web/`). | [`kanban/GEMINI.md`](./kanban/GEMINI.md) |
| [`mcp/`](./mcp/) | Three isolated MCP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`), OAuth 2.1 + PKCE `S256` + scoped `kb_*` keys, `EntityResolver`, and LOD YAML serialization. | [`mcp/GEMINI.md`](./mcp/GEMINI.md) |
| [`agent/`](./agent/) | Vendor-neutral `LLMProvider` (`openai`, `ollama`, `gemini`), deterministic `FixtureLLMProvider` / `FixtureCLIRunner` cassettes, Sparkle FIM, and `kanban-agent` CLI workbench. | [`agent/GEMINI.md`](./agent/GEMINI.md) |

Boundary enforcement (`agent -> mcp -> kanban -> database` and `mcp -/-> database`) is verified via `uv run lint-imports`.

---

## Quickstart

### 1. Zero-Config Standalone Container (Evaluation / Homelab)

Runs embedded Unix-socket PostgreSQL 16 + `pgvector` and Uvicorn (`PrecompressedSPAStaticApp`) inside a single container with zero external services and first-boot CSPRNG keyring generation:

```bash
docker run -d \
  --name thumbs-up-kanban \
  -p 8080:8080 \
  -v kanban_data:/var/lib/kanban/data \
  thumbs-up-kanban:latest

# Retrieve the single-use first-boot setup URL (never uses default passwords):
docker logs thumbs-up-kanban | grep "First-boot setup URL"
```

> **Note:** Standalone single-container mode displays a `⚠️` header indicator and can be promoted losslessly to the hardened multi-container PostgreSQL 16 stack via `kanban-ctl` (`KBBAK1` AES-256-GCM encrypted backup archive). See [`docs/PROMOTION_AND_BACKUP.md`](./docs/PROMOTION_AND_BACKUP.md).

### 2. Hardened Multi-Container Production Stack

```bash
docker compose up -d
```

Enforces the 5-network isolation matrix (`edge_net`, `app_net`, internal `data_net`, internal `sandbox_net`, and `egress_llm_net`) behind Caddy 2.8+ TLS 1.3.

---

## Local Development, `>=95%` Clean-DB Testing & CLI Validation

```bash
# Install locked Python and frontend workspaces
uv sync --locked
pnpm --dir kanban/web install --frozen-lockfile

# Run strict static analysis, mypy, import-linter, license gate, and no-dash check
make check
make license

# Boot RAM-backed tmpfs PostgreSQL 16 test harness and run unit suites (>=95% coverage)
make testdb-up
uv run pytest
pnpm --dir kanban/web test:unit --coverage

# Validate AI workflows locally against deterministic fixtures or live providers
uv run kanban-agent validate-sparkle --help
uv run kanban-agent validate-qa-packet --help
```

---

## Authoritative Documentation

- **Feature Comparison Matrix (46 Capabilities):** [`docs/FEATURE_COMPARISON.md`](./docs/FEATURE_COMPARISON.md) ([Wiki](https://git.adamoutler.com/AI/thumbs-up-kanban/wiki/Feature-Comparison))
- **Architecture & Product Specification (v2):** [`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`](./docs/ARCHITECTURE_AND_PRODUCT_SPEC.md)
- **Production Promotion & Encrypted Backup Runbook (`KBBAK1`):** [`docs/PROMOTION_AND_BACKUP.md`](./docs/PROMOTION_AND_BACKUP.md)
- **Topological Ticket Index & Execution Waves:** [`docs/tickets/INDEX.md`](./docs/tickets/INDEX.md)
- **Agent & QA Gate Governance Rules:** [`AGENTS.md`](./AGENTS.md)
- **License:** [`LICENSE`](./LICENSE) (`Apache-2.0`)
