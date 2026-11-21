# Feature Comparison

A kanban is just a kanban until you start digging deeper. On the surface, every issue tracker presents identical columns, draggable cards, and basic workflow states. The real architectural divergence begins the moment you inspect paywalled enterprise controls, database-level security invariants, canonical Markdown integrity, multi-agent concurrency primitives, and native agent/MCP execution gates. While commercial SaaS, copyleft boards, and external agent runners lock custom properties, audit logs, Single Sign-On, and AI integrations behind per-seat subscription tiers, 1:1 REST-wrapper MCP schemas, or headless external-tracker daemons, `👍kanban` ships a unified, security-first, agent-first platform under a pure Apache-2.0 license. Below is the full 45-feature technical capability matrix comparing `👍kanban` directly against legacy trackers, modern boards, and autonomous agent orchestrators.

**Legend**

* `✅` **Included:** Built into the core product (free in FOSS/free tiers, or included in the entry commercial plan when no free tier exists).
* `🎯✅` **Planned in Core:** Active roadmap target shipping free in the `Apache-2.0` core (never paywalled).
* `🔐` **Paywall-Capped:** Basic or seat-capped version is free; full scale, hierarchy, or enforcement requires a paid tier.
* `🆓🔌` **Free Extension:** Free via a separate official plugin, external MCP server package, or external CLI harness.
* `💰` **Paid Tier:** Locked behind higher per-seat subscription tiers (Pro, Business, Premium, or Enterprise).
* `💸` **Extra Cost:** Separate paid product, paid Marketplace add-on, or metered credit/runner billing.
* `❌` **None:** Unsupported.

---

## 1. Security, Identity, Audit & Deployment

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Permissive FOSS License | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| On-Prem Multi-Container | ✅ | ❌ | ✅ | 💰 | ❌ | ❌ | ❌ | 💰 |
| Single-Container Run | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Multi-Card OIDC & LDAPS | ✅ | 💸 | 💰 | 💰 | ❌ | ❌ | 💸 | ✅ |
| Passkeys & Break-Glass | ✅ | 💸 | 💰 | 🔐 | ❌ | ❌ | 💰 | 💰 |
| Granular RBAC & DENY | ✅ | 💰 | 💰 | 💰 | ❌ | ❌ | ✅ | ✅ |
| Shared-With Pill & DB RLS | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Workspace Audit Logs | ✅ | 💸 | 💰 | 💰 | ❌ | ❌ | 💰 | ✅ |

Vibe Kanban and OpenAI Symphony are permissive `Apache-2.0` (`✅`): Vibe Kanban runs as a single-user local CLI/container (`✅`), whereas OpenAI Symphony is documented as an engineering preview for trusted environments that runs as a host Elixir/OTP daemon or Burrito binary rather than OCI containers (`❌`), executes repo-local `WORKFLOW.md` hooks via `bash -lc`, omits multi-tenant auth/OIDC/Passkeys/RBAC (`❌`), and keeps no persistent database or immutable audit ledger (`❌`). Plane uses copyleft `AGPLv3` and charges per seat for OIDC, LDAP, RBAC, and audit logs (`💰`), Jira charges extra for SSO and security audit policies via Atlassian Guard (`💸`), and none of the other seven enforces PostgreSQL Row-Level Security with a ubiquitous per-object `shared_with` pill (`❌`). **`👍kanban`** is 100% permissive `Apache-2.0` (`✅`), supporting both a zero-config single-container runtime (`docker run -p 8080:8080 thumbs-up-kanban:latest`) and a hardened 5-network multi-container production stack, complete with Multi-Card OIDC/OAuth2/LDAPS, WebAuthn Passkeys + break-glass lockout triggers, explicit `DENY` ACLs, PostgreSQL 16 `FORCE ROW LEVEL SECURITY` surfaced via the `🛡️` Shared-With Header Pill, and an immutable SHA-256 hash-chained audit ledger (`✅`).

---

## 2. Agentic Tasks, MCP, AI & Workflow Gates

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MCP Server | ✅ | 🆓🔌 | 🆓🔌 | 🆓🔌 | ✅ | ❌ | ❌ | ❌ |
| Low-Token Scoped MCP | ✅ | ❌ | ❌ | ❌ | 🔐 | ❌ | ❌ | ❌ |
| 2-Stage MCP Delete Gate | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Cloud AI Integration | ✅ | 💰 | 💸 | 💸 | 💸 | 💸 | ✅ | 💸 |
| Air-Gap Local Ollama | ✅ | ❌ | ❌ | ❌ | 🆓🔌 | 🆓🔌 | ❌ | ❌ |
| Cursor Sparkle FIM | ✅ | ❌ | ❌ | 💸 | ❌ | ❌ | ❌ | ❌ |
| Sync Transition Gates | ✅ | 💸 | 💰 | ❌ | ❌ | ❌ | ✅ | ✅ |
| Async `:ro` Repo Gate | ✅ | ❌ | ❌ | 💸 | ❌ | ❌ | ❌ | ❌ |

Jira, Plane, and GitHub ship MCP through separate external connectors or packages (`🆓🔌`) that expose broad JSON schemas rather than low-token YAML intent surfaces, while Vibe Kanban bundles `--mcp` directly (`✅`) with partial `--mode orchestrator` scoping (`🔐`). OpenAI Symphony does not expose an MCP server (`❌`): it drives a `codex app-server` subprocess over stdio JSON-RPC (relying on metered OpenAI/Codex billing `💸` or external `codex --oss` Ollama configuration `🆓🔌`), passes through raw host-authenticated tracker tools (`linear_graphql`, `github_api`, `asana_api`) without project-boundary scoping or 2-stage delete gates (`❌`), and runs read-write workspace clones (`approval_policy: never`, `networkAccess: true`). None of the other seven holds Kanban transitions in a non-blocking provisional gate while an agent forensically audits a read-only repository mount (`❌`) - GitHub only runs metered post-event Actions or Copilot checks (`💸`). **`👍kanban`** ships three built-in intent-scoped MCP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin` under `<= 1,800` schema tokens with LOD YAML output and 2-stage `request_delete` -> `execute_delete` confirmation), vendor-neutral BYOK Cloud AI (`openai`, `gemini`) and native air-gapped `ollama`, `<150ms` RLS-filtered Cursor Sparkle (`✨`) FIM completion with right-click accept, `<25ms` synchronous Wasm transition validators, and two-phase non-blocking async agent transition gates (`⏳🤖` -> `✅🤖`/`🛑🤖`) over `:ro` repository mounts (`✅`).

---

## 3. Issue Tracker & Kanban Board

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Free Forever Tier | ✅ | 🔐 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Core Kanban & Issues | ✅ | 🔐 | ✅ | ✅ | 🔐 | ❌ | ✅ | ✅ |
| Five Native Views | ✅ | 🔐 | 🔐 | 🔐 | ❌ | ❌ | ✅ | ✅ |
| 2D Swimlanes & Hard WIP | ✅ | 🔐 | 🔐 | 🔐 | ❌ | ❌ | ✅ | ✅ |
| Cycles & Hidden Modules | ✅ | 🔐 | ✅ | 🔐 | ❌ | ❌ | ❌ | ✅ |
| Sub-Issue DAG & Links | ✅ | 🔐 | 🔐 | ✅ | 🔐 | ❌ | ✅ | ✅ |
| Custom Properties | ✅ | ✅ | 💰 | ✅ | ❌ | ❌ | ✅ | ✅ |
| Free-Text Assignee Tag | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Audited Creator Override | ✅ | 💰 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Rule-Gated Archive | ✅ | 💰 | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ |
| Blast-Radius Soft Delete | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Sandboxed Script Fields | ✅ | 💸 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

OpenAI Symphony is free `Apache-2.0` software (`✅`), but it is a headless polling orchestrator and Phoenix LiveView run monitor rather than an issue tracker - requiring an external board such as Linear, GitHub Issues, Jira Cloud, Asana, or GitLab (`❌` across all board, view, hierarchy, property, and lifecycle rows). Jira caps free boards at 10 users and gates cross-project Gantt plans, deep hierarchies, and archiving behind Premium (`💰`), while scripted fields require paid Marketplace apps like ScriptRunner (`💸`). Plane gates custom properties behind paid tiers (`💰`), GitHub lacks Calendar views and hard-blocking WIP limits (`🔐`), and Businessmap/Codebeamer have no free tier at all (`❌`). **`👍kanban`** ships all five native views (`List`, `Board`, `Table`, `Calendar`, `Timeline`), 2D swimlanes with hard WIP limits, cycle-checked DAG hierarchies, hybrid principal + free-text `🏷️` assignee tags, audited `🔄` creator overrides, blast-radius soft delete, and Wasmtime/`nsjail` sandboxed script fields in its free `Apache-2.0` core (`✅`).

---

## 4. Docs, Stickies, Markdown & Object Graph

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Project Docs / Wiki | ✅ | 💸 | 🔐 | 🔐 | ❌ | ❌ | ❌ | ✅ |
| Project Stickies | ✅ | 💸 | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Smart Sticky -> Doc Promo | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Canonical Markdown DB | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Paste-Injection Pruner | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Mermaid, Safe SVG & Proxy | ✅ | 💸 | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Broken/ACL Link Auditor | ✅ | 💸 | ❌ | ❌ | ❌ | ❌ | ❌ | 🔐 |

Jira splits Docs and Stickies into separate paid Confluence and Whiteboard licenses (`💸`), while GitHub restricts private-repo Wikis to paid plans (`🔐`), Plane gates full team Wiki spaces (`🔐`), and OpenAI Symphony is database-less - reading only a repo-local `WORKFLOW.md` YAML + Liquid prompt template with no Docs, Stickies, Markdown persistence DB, diagram pipeline, or link auditor (`❌`). Only **`👍kanban`**, GitHub, and Vibe Kanban store pure Markdown records natively (`✅`), and only Codebeamer flags "suspected" upstream links manually without automated graph purging (`🔐`). **`👍kanban`** unifies `ltree` hierarchical Docs and Project Overview Stickies with 1-click ACL-preserving Sticky-to-Doc promotion (`💡📄`), auto-converts pasted HTML/Rich Text into 100% canonical UTF-8 Markdown while pruning hidden-DOM paste-injection and UTF-16 lone surrogates, renders Web Worker Mermaid diagrams and `nh3`-scrubbed SVGs through an SSRF-guarded media proxy, and runs an automated 6-reason Object Link Auditor & Purger (`✅`).

---

## 5. Orchestration, Provenance & Day-2 Operations

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Atomic Agent Lease & Fencing | 🎯✅ | ❌ | ❌ | ❌ | 🔐 | 🔐 | ❌ | ❌ |
| Prompt-Injection Taint Gate | 🎯✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Dedicated Agent Workpad Slot | 🎯✅ | ❌ | ❌ | ❌ | 🔐 | 🆓🔌 | ❌ | ❌ |
| Pre-Write Secret Redaction | 🎯✅ | 💸 | ❌ | 🔐 | ❌ | ❌ | ❌ | ❌ |
| Crypto-Shredded Audit Chain | 🎯✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Ephemeral OIDC Agent Auth | 🎯✅ | 💰 | ❌ | ✅ | ❌ | ❌ | ❌ | 💰 |
| Git Worktree / PR & Sig Gate | 🎯✅ | 🆓🔌 | 🆓🔌 | ✅ | ✅ | 🆓🔌 | 🆓🔌 | ✅ |
| Lossless Import & Full Export | 🎯✅ | 🔐 | 🔐 | ✅ | ❌ | ❌ | 💰 | ✅ |
| Deterministic JSON/Unix CLI | 🎯✅ | 🆓🔌 | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Native CFD, Lead & Aging WIP | 🎯✅ | 🔐 | 💰 | 🔐 | ❌ | ❌ | ✅ | 🔐 |

OpenAI Symphony tracks single-daemon claims in volatile memory (`🔐`) and relies on external `WORKFLOW.md` comment scraping (`🆓🔌`) with no Unix board CLI (`❌`), while GitHub gates private-repo secret push-protection (`🔐`), Businessmap leads on native Lean flow analytics (`✅`), and Codebeamer enforces ALM commit/release traceability (`✅`). **`👍kanban`** already ships foundational substrates - cross-project `mcp_read_taint` exfiltration guards, outbound secret scrubbing on LLM/FIM prompts, DNS-pinned `:ro` Git mirrors, transactional `PlaneImporter` + `KBBAK1` encrypted backups, `kanban-ctl` / `kanban-agent` CLIs, and immutable `activity_records` transition timestamps - and actively tracks all ten Day-2 enterprise & fleet-scale expansions in its free `Apache-2.0` core (`🎯✅`): PostgreSQL-enforced `issue_leases` + monotonic `fencing_token` CAS (`KAN-69`), per-block provenance tainting with dynamic MCP capability stripping (`KAN-70`), silent per-issue `issue_workpads` + rework loop circuit breakers (`KAN-71`), synchronous pre-persistence Shannon-entropy secret push-protection (`KAN-72`), envelope-encrypted `activity_record_keys` crypto-shredding (`KAN-73`), RFC 8693 headless workload OIDC token exchange (`KAN-74`), SSRF-hardened SCM webhooks + `SSH`/`GPG`/`Sigstore` & SLSA attestation gates (`KAN-75`, `KAN-76`), Jira/GitHub/Linear importers with legacy key alias redirects and deterministic `JSONL` + `.md` exports (`KAN-77`), schema-driven `kanban-cli --filter ... --json` backed by `hnsw.iterative_scan` RLS vector recall (`KAN-48`, `KAN-78`), and native CFD, Aging WIP, Cycle/Lead Time `p50`/`p85`/`p95` scatterplots, and Monte Carlo forecasting (`KAN-79`).
