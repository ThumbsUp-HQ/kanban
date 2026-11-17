# 👍kanban: Agent-First, Security-First Kanban Platform (`[kanban, database, mcp, agent]`)

## Architecture & Mission

This repository implements **`👍kanban`** (`thumbs-up-kanban`), an open-source, **Security-First (Priority #0), Agent-First (Priority #1)** Kanban, Ticketing, and Knowledge Platform designed to eliminate SaaS AI paywalls and CRUD-wrapper MCP context bloat.

- **Public Brand & Namespace Convention:** User-facing surfaces, HTML document titles (`<title>👍kanban</title>`), OpenAPI specifications (`title="👍kanban API"`), and WebAuthn Relying Party display strings (`rp.name = "👍kanban"`, paired with strict ASCII FQDN `rp.id`) use **`👍kanban`**. Upstream repository and container image slugs use `thumbs-up-kanban` (`thumbs-up-kanban:latest`), while internal Python workspace root packages remain `kanban` (`@kanban/web` for frontend).
- **License:** `Apache-2.0` (Strictly permissive; zero `GPL`, `AGPL`, `LGPL`, or `SSPL` runtime dependencies permitted)
- **Initial Tracking Board:** `https://kanban.hackedyour.info/kanban/` (`workspace: kanban`, `project: KANBA`)
- **Authoritative Specifications:** [`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`](./docs/ARCHITECTURE_AND_PRODUCT_SPEC.md) and [`docs/PROMOTION_AND_BACKUP.md`](./docs/PROMOTION_AND_BACKUP.md)
- **Top-Level Module Topology:**
  - `kanban/` - Web UI & HTTP/WebSocket application server (Enterprise multi-layout board & 17-feature ticket screen competing globally against Jira and Vibe Kanban, breathable whitespace + semantic emojis with hover elaboration, Multi-Card OAuth/LDAP/Local authentication, blinking cursor Sparkle completion + right-click accept, auto-detected & auto-converted canonical Markdown with Mermaid/Pictures/SVG rendering, Project Stickies with smart Doc promotion, and standalone `docker run` + multi-container deployment modes).
  - `database/` - PostgreSQL Universal Object Graph (`Issues`, `Stickies`, `Docs`, `Users`, `Projects`, `Cycles`, `Modules`, `Views`, `Pages`) storing canonical UTF-8 Markdown only, typed `object_links`, Invalid Object Link Auditor & Purger, Row-Level Security (`FORCE RLS`), and immutable Activity & Audit Ledger.
  - `mcp/` - Multi-surface Model Context Protocol server (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`) with OAuth 2.0 + PKCE (`S256`) + scoped API keys, `EntityResolver` human-readable keys, LOD tiers (`summary`, `standard`, `full`), compact `InlineSafeDumper` YAML output, and refined 12-tool intent-based Admin catalog with 2-stage destructive confirmation.
  - `agent/` - Native multi-provider LLM & autonomous agent runtime (`openai`, `ollama`, `gemini`, plus zero-shell CLI pipe harnesses `agy -p` / `codex -p` and outbound mTLS remote read-only repo runners) powering ScriptRunner-style workflow transition interceptors, permission-filtered inline cursor completions, sticky-to-doc synthesis, and semantic search.

---

## Mandatory Specialist & QA Gates (Zero Exceptions)

Every ticket managed under [`.agents/skills/kanban-ticket/SKILL.md`](./.agents/skills/kanban-ticket/SKILL.md) and [`.agents/skills/kanban-agent-manager/SKILL.md`](./.agents/skills/kanban-agent-manager/SKILL.md) MUST pass the following project-local specialist gates before ticket closure:

1. **UI Specialist Gate (All UI Changes):**
   - Any ticket or diff modifying UI layout, components, styles, themes, editors, or client interactions MUST be reviewed and approved by a project-local UI specialist ([`.agents/agents/ui-designer.md`](./.agents/agents/ui-designer.md) or [`.agents/agents/ux-architect.md`](./.agents/agents/ux-architect.md)) prior to completion.
   - The verbatim specialist audit MUST be written to `docs/qa/<TICKET_ID>/ui-specialist-review.md` alongside annotated Playwright desktop/tablet/mobile screenshots in `docs/qa/<TICKET_ID>/screenshots/`.

2. **API + UI Dual Specialist Gate (All API & MCP Changes):**
   - Any ticket or diff introducing or modifying REST endpoints, WebSocket events, custom script bindings, or MCP tool schemas/responses MUST be reviewed and approved by **both**:
     - An **API Specialist** ([`.agents/agents/backend-architect.md`](./.agents/agents/backend-architect.md) or [`.agents/agents/api-tester.md`](./.agents/agents/api-tester.md)) -> saved to `docs/qa/<TICKET_ID>/api-specialist-review.md`.
     - A **UI Specialist** ([`.agents/agents/ui-designer.md`](./.agents/agents/ui-designer.md) or [`.agents/agents/ux-architect.md`](./.agents/agents/ux-architect.md)) verifying frontend/UX consumption, whitespace/ergonomics, and state alignment -> saved to `docs/qa/<TICKET_ID>/ui-specialist-review.md`.

3. **Local `reality-checker` Forensic QA Gate (All Tickets Before Closure):**
   - Before closing **any** ticket (`complete_work`), all changes, raw test/build logs, specialist review files, and screenshots in `docs/qa/<TICKET_ID>/` MUST be audited by the project-local QA agent at [`.agents/agents/reality-checker.md`](./.agents/agents/reality-checker.md) (mirrored in [`.agents/skills/kanban-agent-manager/references/reality-checker.md`](./.agents/skills/kanban-agent-manager/references/reality-checker.md)) running in passive forensic mode on a fast model.
   - Only a **grade-A `READY`** certification permits closing the ticket.

---

## Core Security & Engineering Invariants

1. **Transparent Access Visibility:** Every object (`Project`, `Issue`, `Sticky`, `Doc`, `Page`, `View`) must compute and expose explicit sharing metadata (`Users`, `Groups`, `Agents`, `Inherited Scope`) without cross-tenant or unauthorized principal enumeration.
2. **Hostile Input & Sanitization:** Auto-detect Plain Text, Markdown, and HTML at ingestion; enforce UTF-16 lone-surrogate rejection (`0xD800 <= ord(c) <= 0xDFFF` -> `INVALID_UTF8_SURROGATE`) prior to `.encode("utf-8")`, hidden-DOM paste-jacking pruning, and server-side allowlist sanitization (stripping scripts, event handlers, dangerous URI schemes, SVG/MathML vectors, and hidden prompt-injection payloads) paired with a strict `Content-Security-Policy`.
3. **Multi-Card Auth & Admin AAL2 Integrity:** Support multiple OAuth2/OIDC, LDAPS/StartTLS, WebAuthn/Passkeys (`rp.name = "👍kanban"` with strict ASCII FQDN `rp.id`), TOTP, and Local Admin auth cards with enable/disable and ordering controls, break-glass lockout prevention, and verified-claim account linking (zero implicit email auto-merge). Every `/api/v1/admin/*` route MUST declare `Depends(require_admin_aal2)` at the router/route dependency layer (`assert_admin_routes_protected`).
4. **Hardened Custom Script Boundaries:** Only Admins may define custom fields or scripts. Script execution defaults to an ephemeral API token scoped strictly to the current **Project** inside an isolated sandbox; escalating token scope to **Workspace** or **Server** (or running under Project/Server Admin credentials instead of invoking User credentials) requires explicit cryptographic approval by an administrator of that target tier.
5. **Universal Object Graph Integrity:** Every entity is a registered Object; every relationship is a typed `object_link`. Broken, orphaned, or policy-invalid links must never fail silently - they must be surfaced by the Object Link Auditor for forensic inspection and explicit audited deletion.
6. **Quality, `>=95%` Coverage, Clean-DB RLS Speed & Testable AI Agents:**
   - Maintain **`>=95%` automated unit test coverage**, zero compiler/linter warnings, fast parallel execution (`tmpfs` Postgres template DB + sub-millisecond `SAVEPOINT` rollback isolation providing a 100% clean database per test), and verified CI/CD builds via Dash (`https://dash.hackedyour.info/llms.txt`).
   - Database test fixtures MUST provision bootstrap workspace/admin rows under `kanban_migrator`/superuser authority and immediately drop session authorization back to `kanban_app` with `FORCE ROW LEVEL SECURITY` active before executing test assertions (`KANBA-162` invariant). Non-top-level `conftest.py` files MUST NOT declare `pytest_plugins` (forbidden by Pytest 9.2+).
   - All AI agent workflows (`agent/`) MUST support pluggable deterministic **AI Response Fixtures** (`FixtureLLMProvider` / `FixtureCLIRunner`) for fast offline tests AND direct **local manual CLI validation** (`kanban-agent validate-*`) given explicit input parameters/files.
   - Before introducing **any** new external dependency, consult at least 1 architect sub-agent and multiple engineer sub-agents to verify `Apache-2.0` license compatibility, evaluate supply-chain risk, and check native alternatives.
   - Maintain self-describing `GEMINI.md` (and cross-harness `AGENTS.md` symlink) manifests inside each top-level module (`kanban/`, `database/`, `mcp/`, `agent/`) documenting module responsibilities, inbound/outbound contracts, performance budgets, and failure modes. All database migrations and schema changes MUST strictly follow the Zero-Guesswork Database Migration & Schema Consistency Standard documented in `database/GEMINI.md` (linear single-head chain, `kanban-ctl db new-migration`, `check-migrations`, and column-level ORM parity).
