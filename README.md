# 👍kanban (`thumbs-up-kanban`)

**`👍kanban`** is an open-source (`Apache-2.0`), **Security-First (Priority #0), Agent-First (Priority #1)** Kanban, Ticketing, and Knowledge Platform built to replace seat-taxed AI paywalls and CRUD-wrapper MCP context bloat.

---

## Core Architectural Pillars

- **Priority #0 - Kernel-Level Security & Access Transparency:** PostgreSQL 16 `FORCE ROW LEVEL SECURITY` (`NOBYPASSRLS`) across 31+ tables, materialized `effective_resource_access`, ubiquitous `🛡️` Shared-With visibility pills, Multi-Card Auth (`OIDC` PKCE `S256`, `LDAPS` `TLS_HARD`, `Argon2id` + `WebAuthn` Passkeys / `TOTP` `AAL2`, and `LOCKOUT_PREVENTED` safeguards), and monthly-partitioned SHA-256 hash-chained `activity_records`.
- **Priority #1 - Native Agent-First MCP & ScriptRunner Workflows:** Three isolated intent-driven MCP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`) with `InlineSafeDumper` YAML and hierarchical scopable `kb_*` keys, plus multi-provider AI (`openai`, `ollama`, `gemini`, and zero-shell CLI pipes `agy -p` / `codex -p`) powering `<150ms` `✨` cursor completions and ScriptRunner transition gates.
- **Priority #2 - Breathable Whitespace & `<EmojiHint>` UX:** Plane-parity spatial layout (`52px` topbar, `324px` columns, `46px` list rows, `960px` drawer), standardized 21-emoji `<EmojiHint>` hover/focus elaboration, 100% canonical UTF-8 Markdown storage (auto-converted from HTML/Rich Text with hidden-DOM paste-jacking pruning), isolated `beautiful-mermaid` Web Worker diagrams, and scrubbed SVGs under strict `Content-Security-Policy`.

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

- **Architecture & Product Specification (v2):** [`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`](./docs/ARCHITECTURE_AND_PRODUCT_SPEC.md)
- **Production Promotion & Encrypted Backup Runbook (`KBBAK1`):** [`docs/PROMOTION_AND_BACKUP.md`](./docs/PROMOTION_AND_BACKUP.md)
- **Topological Ticket Index & Execution Waves:** [`docs/tickets/INDEX.md`](./docs/tickets/INDEX.md)
- **Agent & QA Gate Governance Rules:** [`AGENTS.md`](./AGENTS.md)
- **License:** [`LICENSE`](./LICENSE) (`Apache-2.0`)
