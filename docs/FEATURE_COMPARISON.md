# Feature Comparison

A kanban is just a kanban until you start digging deeper. On the surface, every issue tracker presents identical columns, draggable cards, and basic workflow states. The real architectural divergence begins the moment you inspect paywalled enterprise controls, database-level security invariants, canonical Markdown integrity, and native agent/MCP execution gates. While commercial SaaS and copyleft alternatives lock custom properties, audit logs, Single Sign-On, and AI integrations behind steep per-seat subscription tiers or bloated CRUD APIs, `👍kanban` ships an uncompromising, security-first, agent-first platform under a pure Apache-2.0 license. Below is the full 35-feature technical capability matrix comparing `👍kanban` directly against legacy and modern project management systems.

**Legend**

* `✅` **Included:** Built into the core product (free in FOSS/free tiers, or included in the entry commercial plan when no free tier exists).
* `🔐` **Paywall-Capped:** Basic or seat-capped version is free; full scale, hierarchy, or enforcement requires a paid tier.
* `🆓🔌` **Free Extension:** Free via a separate official plugin, external MCP server package, or external CLI harness.
* `💰` **Paid Tier:** Locked behind higher per-seat subscription tiers (Pro, Business, Premium, or Enterprise).
* `💸` **Extra Cost:** Separate paid product, paid Marketplace add-on, or metered credit/runner billing.
* `❌` **None:** Unsupported.

---

## 1. Security, Identity, Audit & Deployment

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Permissive FOSS License | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| On-Prem Multi-Container | ✅ | ❌ | ✅ | 💰 | ❌ | ❌ | 💰 |
| Single-Container Run | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Multi-Card OIDC & LDAPS | ✅ | 💸 | 💰 | 💰 | ❌ | 💸 | ✅ |
| Passkeys & Break-Glass | ✅ | 💸 | 💰 | 🔐 | ❌ | 💰 | 💰 |
| Granular RBAC & DENY | ✅ | 💰 | 💰 | 💰 | ❌ | ✅ | ✅ |
| Shared-With Pill & DB RLS | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Workspace Audit Logs | ✅ | 💸 | 💰 | 💰 | ❌ | 💰 | ✅ |

Vibe Kanban is permissive `Apache-2.0` (`✅`) as a single-user local CLI, whereas Plane uses copyleft `AGPLv3` and charges per seat for OIDC, LDAP, RBAC, and audit logs (`💰`). Jira charges extra for SSO and security audit policies via Atlassian Guard (`💸`), and none of the other six enforces PostgreSQL Row-Level Security with a ubiquitous per-object `shared_with` pill (`❌`). **`👍kanban`** is 100% permissive `Apache-2.0` (`✅`), supporting both a zero-config single-container runtime (`docker run -p 8080:8080 thumbs-up-kanban:latest`) and a hardened 5-network multi-container production stack, complete with Multi-Card OIDC/OAuth2/LDAPS, WebAuthn Passkeys + break-glass lockout triggers, explicit `DENY` ACLs, PostgreSQL 16 `FORCE ROW LEVEL SECURITY` surfaced via the `🛡️` Shared-With Header Pill, and an immutable SHA-256 hash-chained audit ledger (`✅`).

---

## 2. Agentic Tasks, MCP, AI & Workflow Gates

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MCP Server | ✅ | 🆓🔌 | 🆓🔌 | 🆓🔌 | ✅ | ❌ | ❌ |
| Low-Token Scoped MCP | ✅ | ❌ | ❌ | ❌ | 🔐 | ❌ | ❌ |
| 2-Stage MCP Delete Gate | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Cloud AI Integration | ✅ | 💰 | 💸 | 💸 | 💸 | ✅ | 💸 |
| Air-Gap Local Ollama | ✅ | ❌ | ❌ | ❌ | 🆓🔌 | ❌ | ❌ |
| Cursor Sparkle FIM | ✅ | ❌ | ❌ | 💸 | ❌ | ❌ | ❌ |
| Sync Transition Gates | ✅ | 💸 | 💰 | ❌ | ❌ | ✅ | ✅ |
| Async `:ro` Repo Gate | ✅ | ❌ | ❌ | 💸 | ❌ | ❌ | ❌ |

Jira, Plane, and GitHub ship MCP through separate external connectors or packages (`🆓🔌`) that expose broad JSON schemas rather than low-token YAML intent surfaces, while Vibe Kanban bundles `--mcp` directly (`✅`) with partial `--mode orchestrator` scoping (`🔐`). None of the other six holds Kanban transitions in a non-blocking provisional gate while an agent forensically audits a read-only repository mount (`❌`) - GitHub only runs metered post-event Actions or Copilot checks (`💸`). **`👍kanban`** ships three built-in intent-scoped MCP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin` under `<= 1,800` schema tokens with LOD YAML output and 2-stage `request_delete` -> `execute_delete` confirmation), vendor-neutral Cloud AI (`openai`, `gemini`) and air-gapped `ollama`, `<150ms` RLS-filtered Cursor Sparkle (`✨`) FIM completion with right-click accept, `<25ms` synchronous Wasm transition validators, and two-phase non-blocking async agent transition gates (`⏳🤖` -> `✅🤖`/`🛑🤖`) over `:ro` repository mounts (`✅`).

---

## 3. Issue Tracker & Kanban Board

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Free Forever Tier | ✅ | 🔐 | ✅ | ✅ | ✅ | ❌ | ❌ |
| Core Kanban & Issues | ✅ | 🔐 | ✅ | ✅ | 🔐 | ✅ | ✅ |
| Five Native Views | ✅ | 🔐 | 🔐 | 🔐 | ❌ | ✅ | ✅ |
| 2D Swimlanes & Hard WIP | ✅ | 🔐 | 🔐 | 🔐 | ❌ | ✅ | ✅ |
| Cycles & Hidden Modules | ✅ | 🔐 | ✅ | 🔐 | ❌ | ❌ | ✅ |
| Sub-Issue DAG & Links | ✅ | 🔐 | 🔐 | ✅ | 🔐 | ✅ | ✅ |
| Custom Properties | ✅ | ✅ | 💰 | ✅ | ❌ | ✅ | ✅ |
| Free-Text Assignee Tag | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Audited Creator Override | ✅ | 💰 | ❌ | ❌ | ❌ | ❌ | ❌ |
| Rule-Gated Archive | ✅ | 💰 | ✅ | ✅ | ❌ | ✅ | ✅ |
| Blast-Radius Soft Delete | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Sandboxed Script Fields | ✅ | 💸 | ❌ | ❌ | ❌ | ❌ | ✅ |

Jira caps free boards at 10 users and gates cross-project Gantt plans, deep hierarchies, and archiving behind Premium (`💰`), while scripted fields require paid Marketplace apps like ScriptRunner (`💸`). Plane gates custom properties behind paid tiers (`💰`), GitHub lacks Calendar views and hard-blocking WIP limits (`🔐`), and Businessmap/Codebeamer have no free tier at all (`❌`). **`👍kanban`** ships all five native views (`List`, `Board`, `Table`, `Calendar`, `Timeline`), 2D swimlanes with hard WIP limits, cycle-checked DAG hierarchies, hybrid principal + free-text `🏷️` assignee tags, audited `🔄` creator overrides, blast-radius soft delete, and Wasmtime/`nsjail` sandboxed script fields in its free `Apache-2.0` core (`✅`).

---

## 4. Docs, Stickies, Markdown & Object Graph

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Project Docs / Wiki | ✅ | 💸 | 🔐 | 🔐 | ❌ | ❌ | ✅ |
| Project Stickies | ✅ | 💸 | ✅ | ❌ | ❌ | ✅ | ❌ |
| Smart Sticky -> Doc Promo | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Canonical Markdown DB | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| Paste-Injection Pruner | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Mermaid, Safe SVG & Proxy | ✅ | 💸 | ❌ | ✅ | ❌ | ❌ | ❌ |
| Broken/ACL Link Auditor | ✅ | 💸 | ❌ | ❌ | ❌ | ❌ | 🔐 |

Jira splits Docs and Stickies into separate paid Confluence and Whiteboard licenses (`💸`), while GitHub restricts private-repo Wikis to paid plans (`🔐`) and Plane gates full team Wiki spaces (`🔐`). Only **`👍kanban`**, GitHub, and Vibe Kanban store pure Markdown natively (`✅`), and only Codebeamer flags "suspected" upstream links manually without automated graph purging (`🔐`). **`👍kanban`** unifies `ltree` hierarchical Docs and Project Overview Stickies with 1-click ACL-preserving Sticky-to-Doc promotion (`💡📄`), auto-converts pasted HTML/Rich Text into 100% canonical UTF-8 Markdown while pruning hidden-DOM paste-injection and UTF-16 lone surrogates, renders Web Worker Mermaid diagrams and `nh3`-scrubbed SVGs through an SSRF-guarded media proxy, and runs an automated 6-reason Object Link Auditor & Purger (`✅`).
