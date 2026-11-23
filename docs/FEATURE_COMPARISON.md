# Feature Comparison

A kanban is just a kanban until you start digging deeper. On the surface, every issue tracker presents identical columns, draggable cards, and basic workflow states. The real architectural divergence begins the moment you inspect paywalled enterprise controls, database-level security invariants, canonical Markdown integrity, multi-agent concurrency primitives, and native agent/MCP execution gates. While commercial SaaS, copyleft boards, and external agent runners lock custom properties, audit logs, Single Sign-On, and AI integrations behind per-seat subscription tiers, 1:1 REST-wrapper MCP schemas, or headless external-tracker daemons, `👍kanban` ships a unified, security-first, agent-first platform under a pure Apache-2.0 license. Below is the full 46-feature technical capability matrix comparing `👍kanban` directly against legacy trackers, modern boards, and autonomous agent orchestrators, followed by an honest non-goal compatibility and routing guide.

**Legend**

* `✅` **Included:** Built into the core product (free in FOSS/free tiers, or included in the entry commercial plan when no free tier exists).
* `🎯✅` **Planned in Core:** Active roadmap target shipping free in the `Apache-2.0` core (never paywalled).
* `🔐` **Partial / Paywall-Capped:** Basic, single-node, or subset capability is included; full enforcement, scale, or hierarchy is missing or locked behind a paid tier.
* `🆓🔌` **Free Extension:** Free via a separate official plugin, external MCP server package, or external CLI harness.
* `💰` **Paid Tier:** Locked behind higher per-seat subscription tiers (Pro, Business, Premium, or Enterprise).
* `💸` **Extra Cost:** Separate paid product, paid Marketplace add-on, or metered credit/runner billing.
* `❌` **None:** Unsupported.

---

## 1. Security, Identity, Audit & Deployment

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Permissive FOSS License | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| On-Prem Multi-Container | ✅ | ❌ | ✅ | 💰 | ❌ | ❌ | ❌ | 💰 |
| Single-Container Run | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Multi-Card OIDC & LDAPS | ✅ | 💸 | 💰 | 💰 | ❌ | ❌ | 💸 | ✅ |
| Passkeys & Break-Glass | ✅ | 💸 | 💰 | 🔐 | ❌ | ❌ | 💰 | 💰 |
| Object RBAC & Explicit DENY | ✅ | 💰 | 💰 | 💰 | ❌ | ❌ | ✅ | ✅ |
| Workspace/Issue/Field RBAC | ✅ | 💸 | ❌ | ❌ | ❌ | ❌ | 💰 | ✅ |
| Shared-With Pill & DB RLS | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Workspace Audit Logs | ✅ | 💸 | 💰 | 💰 | ❌ | ❌ | 💰 | ✅ |

Vibe Kanban and OpenAI Symphony are permissive `Apache-2.0` (`✅`): Vibe Kanban runs as a single-user local CLI/container (`✅`), whereas OpenAI Symphony is documented as an engineering preview for trusted environments that runs as a host Elixir/OTP daemon or Burrito binary rather than OCI containers (`❌`), executes repo-local `WORKFLOW.md` hooks via `bash -lc`, omits multi-tenant auth/OIDC/Passkeys/RBAC (`❌`), and keeps no persistent database or immutable audit ledger (`❌`). Plane uses copyleft `AGPLv3`, charges per seat for OIDC, LDAP, coarse RBAC, and audit logs (`💰`), and omits field-level RBAC (`❌`); Jira charges extra for SSO/audit policies via Atlassian Guard (`💸`) and relies on paid Marketplace apps for per-field edit locks (`💸`); Businessmap gates custom role matrices behind Enterprise (`💰`); and only Codebeamer ships native per-field tracker RBAC (`✅`) - while none of the seven enforces PostgreSQL Row-Level Security with a ubiquitous per-object `shared_with` pill (`❌`). **`👍kanban`** is 100% permissive `Apache-2.0` (`✅`) across standalone (`docker run`) and 5-network production stacks, shipping Multi-Card OIDC/OAuth2/LDAPS, WebAuthn Passkeys + break-glass triggers, 7-tier Object RBAC + explicit `DENY` ACLs, PostgreSQL 16 `FORCE ROW LEVEL SECURITY` surfaced via the `🛡️` Shared-With Header Pill, an immutable SHA-256 hash-chained audit ledger, granular 30-permission Workspace, Issue, and Field-level RBAC across custom multi-role user labels (`KAN-83`, `database/migrations/sql/p6_12_granular_rbac_roles.up.sql`), HKDF-HMAC internal service authentication (`KAN-63`), and monotonic `CredentialBoundary` capability bitmasks and CIDR whitelisting across REST, RLS, and MCP (`KAN-66`, `KAN-67`, `KAN-68`) (`✅`).

---

## 2. Agentic Tasks, MCP, AI & Workflow Gates

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MCP Server | ✅ | 🆓🔌 | 🆓🔌 | 🆓🔌 | ✅ | ❌ | ❌ | ❌ |
| Low-Token Scoped MCP | ✅ | ❌ | ❌ | ❌ | 🔐 | ❌ | ❌ | ❌ |
| 2-Stage MCP Delete Gate | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Cloud AI Integration | ✅ | 💰 | 💸 | 💸 | 💸 | 💸 | ✅ | 💸 |
| Air-Gap Local Ollama | ✅ | ❌ | ❌ | ❌ | 🆓🔌 | 🆓🔌 | ❌ | ❌ |
| Cursor Sparkle FIM | ✅ | ❌ | ❌ | 💸 | ❌ | ❌ | ❌ | ❌ |
| Sync Transition Gates | ✅ | 💸 | 💰 | ❌ | ❌ | ❌ | ✅ | ✅ |
| Async `:ro` Repo Gate | ✅ | ❌ | ❌ | 💸 | ❌ | ❌ | ❌ | ❌ |

Jira, Plane, and GitHub ship MCP through separate external connectors or packages (`🆓🔌`) that expose broad JSON schemas rather than low-token YAML intent surfaces, while Vibe Kanban bundles `--mcp` directly (`✅`) with partial `--mode orchestrator` scoping (`🔐`). OpenAI Symphony does not expose an MCP server (`❌`): it drives a `codex app-server` subprocess over stdio JSON-RPC (relying on metered OpenAI/Codex billing `💸` or external `codex --oss` Ollama configuration `🆓🔌`), passes through raw host-authenticated tracker tools (`linear_graphql`, `github_api`, `asana_api`) without project-boundary scoping or 2-stage delete gates (`❌`), and runs read-write workspace clones (`approval_policy: never`, `networkAccess: true`). None of the other seven holds Kanban transitions in a non-blocking provisional gate while an agent forensically audits a read-only repository mount (`❌`) - GitHub only runs metered post-event Actions or Copilot checks (`💸`). **`👍kanban`** ships three built-in intent-scoped MCP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin` under `<= 1,800` schema tokens with LOD YAML output and 2-stage `request_delete` -> `execute_delete` confirmation), vendor-neutral BYOK Cloud AI (`openai`, `gemini`) and native air-gapped `ollama`, `<150ms` RLS-filtered Cursor Sparkle (`✨`) FIM completion with right-click accept, `<25ms` synchronous Wasm transition validators, and two-phase non-blocking async agent transition gates (`⏳🤖` -> `✅🤖`/`🛑🤖`) over `:ro` repository mounts (`✅`). In addition, `👍kanban` delivers TTFD Summary LOD tier caching for `<50ms` first-token agent response times (`KAN-309`), the `/llms.txt` and `/llms-full.txt` machine discovery endpoint paired with the Agent Skills catalog (`KAN-80`), and dedicated per-issue agent workpad slots with rework circuit breakers (`KAN-71`).

---

## 3. Issue Tracker & Kanban Board

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
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

OpenAI Symphony is free `Apache-2.0` software (`✅`), but it is a headless polling orchestrator and Phoenix LiveView run monitor rather than an issue tracker - requiring an external board such as Linear, GitHub Issues, Jira Cloud, Asana, or GitLab (`❌` across all board, view, hierarchy, property, and lifecycle rows). Jira caps free boards at 10 users and gates cross-project Gantt plans, deep hierarchies, and archiving behind Premium (`💰`), while scripted fields require paid Marketplace apps like ScriptRunner (`💸`). Plane gates custom properties behind paid tiers (`💰`), GitHub lacks Calendar views and hard-blocking WIP limits (`🔐`), Vibe Kanban sunsetted its hosted issue/org cloud in May 2026 after `v0.1.44` - leaving local git-worktree execution (`npx vibe-kanban`) as its active surface (`🔐`), and Businessmap/Codebeamer have no free tier at all (`❌`). **`👍kanban`** ships all five native views (`List`, `Board`, `Table`, `Calendar`, `Timeline`), 2D swimlanes with hard WIP limits, cycle-checked DAG hierarchies, hybrid principal + free-text `🏷️` assignee tags, audited `🔄` creator overrides, blast-radius soft delete, and Wasmtime/`nsjail` sandboxed script fields in its free `Apache-2.0` core (`✅`). `👍kanban` also includes the Master-Detail Issue Navigator (`KAN-52`), Searchable State Filter Popovers with Active/All/None presets and cookie persistence (`KAN-308` / `KAN-84`), recipient-scoped realtime WS/SSE notifications with multi-tab synchronization (`KAN-310`), deterministic build version metadata `0.{release}.{commits}` with commit verification (`KAN-312` / `KAN-313`), and the Unified Admin Diagnostics & Link Inspector Studio at `/admin/diagnostics` (`KAN-307`).

---

## 4. Docs, Stickies, Markdown & Object Graph

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Project Docs / Wiki | ✅ | 💸 | 🔐 | 🔐 | ❌ | ❌ | ❌ | ✅ |
| Project Stickies | ✅ | 💸 | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Smart Sticky -> Doc Promo | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Canonical Markdown DB | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Paste-Injection Pruner | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Mermaid, Safe SVG & Proxy | ✅ | 💸 | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Broken/ACL Link Auditor | ✅ | 💸 | ❌ | ❌ | ❌ | ❌ | ❌ | 🔐 |

Jira splits Docs and Stickies into separate paid Confluence and Whiteboard licenses (`💸`), while GitHub restricts private-repo Wikis to paid plans (`🔐`), Plane gates full team Wiki spaces (`🔐`), and OpenAI Symphony is database-less - reading only a repo-local `WORKFLOW.md` YAML + Liquid prompt template with no Docs, Stickies, Markdown persistence DB, diagram pipeline, or link auditor (`❌`). Only **`👍kanban`**, GitHub, and Vibe Kanban store pure Markdown records natively (`✅`), and only Codebeamer flags "suspected" upstream links manually without automated graph purging (`🔐`). **`👍kanban`** unifies `ltree` hierarchical Docs and Project Overview Stickies with 1-click ACL-preserving Sticky-to-Doc promotion (`💡📄`), auto-converts pasted HTML/Rich Text into 100% canonical UTF-8 Markdown while pruning hidden-DOM paste-injection and UTF-16 lone surrogates, renders Web Worker Mermaid diagrams and `nh3`-scrubbed SVGs through an SSRF-guarded media proxy, and runs an automated 6-reason Object Link Auditor & Purger (`✅`). Strict Markdown-only prose persistence guarantees UTF-16 lone-surrogate rejection (`INVALID_UTF8_SURROGATE`) and DOM paste-jacking pruning across all ticket prose and document nodes (`KAN-81`).

---

## 5. Orchestration, Provenance & Day-2 Operations

| Feature | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Atomic Agent Lease & Fencing | ✅ | ❌ | ❌ | ❌ | 🔐 | 🔐 | ❌ | ❌ |
| Prompt-Injection Taint Gate | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Dedicated Agent Workpad Slot | ✅ | ❌ | ❌ | ❌ | 🔐 | 🆓🔌 | ❌ | ❌ |
| Pre-Write Secret Redaction | ✅ | 💸 | ❌ | 🔐 | ❌ | ❌ | ❌ | ❌ |
| Crypto-Shredded Audit Chain | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Ephemeral OIDC Agent Auth | ✅ | 💰 | ❌ | ✅ | ❌ | ❌ | ❌ | 💰 |
| Git Worktree / PR & Sig Gate | ✅ | 🆓🔌 | 🆓🔌 | ✅ | ✅ | 🆓🔌 | 🆓🔌 | ✅ |
| Lossless Import & Full Export | ✅ | 🔐 | 🔐 | ✅ | ❌ | ❌ | 💰 | ✅ |
| Deterministic JSON/Unix CLI | ✅ | 🆓🔌 | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Native CFD, Lead & Aging WIP | ✅ | 🔐 | 💰 | 🔐 | ❌ | ❌ | ✅ | 🔐 |

OpenAI Symphony tracks single-daemon claims in volatile memory (`🔐`) and relies on external `WORKFLOW.md` comment scraping (`🆓🔌`) with no Unix board CLI (`❌`), while GitHub gates private-repo secret push-protection (`🔐`), Businessmap leads on native Lean flow analytics (`✅`), and Codebeamer enforces ALM commit/release traceability (`✅`). **`👍kanban`** ships all ten Day-2 enterprise and fleet-scale capabilities directly in its free `Apache-2.0` core (`✅`): PostgreSQL-enforced `issue_leases` + monotonic `fencing_token` CAS (`KAN-69`, `database/migrations/sql/p6_05_issue_leases_and_fencing.up.sql`, `kanban/api/v1/issue_workflow.py`), per-block provenance tainting with dynamic MCP capability stripping (`KAN-70`, `kanban/security/taint.py`, `database/models/mcp_read_taint.py`), silent per-issue `issue_workpads` + rework loop circuit breakers (`KAN-71`, `database/migrations/sql/p6_10_issue_workpads_and_rework_breaker.up.sql`, `kanban/api/v1/issue_workpad.py`, `mcp/surfaces/agent/workpad.py`), synchronous pre-persistence Shannon-entropy secret push-protection (`KAN-72`, `kanban/security/push_protection.py`), envelope-encrypted `activity_record_keys` crypto-shredding (`KAN-73`, `database/migrations/sql/p6_08_crypto_shred_activity_chain.up.sql`, `kanban/security/crypto_shred.py`), RFC 8693 headless workload OIDC token exchange (`KAN-74`, `kanban/auth/workload_oidc.py`, `database/models/workload_identity.py`), SSRF-hardened SCM webhooks + `SSH`/`GPG`/`Sigstore` & SLSA attestation gates (`KAN-75`, `KAN-76`, `kanban/security/webhook_verifier.py`, `kanban/security/attestations.py`), Jira/GitHub/Linear/Plane-DB importers with legacy key alias redirects, streaming MinIO attachment ingestion, cross-project merge mode (`KANBA -> KAN`), CSV import/export, and deterministic `JSONL` + `.md` exports (`KAN-77`, `KAN-82`, `KAN-316`, `scripts/export_plane_db.py`, `PortableWorkspaceExporter`), schema-driven `kanban-ctl` and `kanban-cli --filter ... --json` backed by `hnsw.iterative_scan` RLS vector recall and hybrid search (`KAN-48`, `KAN-78`, `mcp/cli/schema_cli.py`, `kanban/services/search.py`), native CFD, Aging WIP, Cycle/Lead Time `p50`/`p85`/`p95` scatterplots, and 10,000-iteration Monte Carlo delivery forecasting (`KAN-79`, `kanban/api/v1/flow_metrics.py`, `kanban/web/src/features/analytics/FlowAnalyticsPage.tsx`), alongside Jinja2 multi-format PDF/CSV/Markdown compliance reporting (`KAN-317`, `database/migrations/sql/p6_14_jinja_report_templates.up.sql`, `kanban/services/report_engine.py`).

---

## 6. When 👍kanban Is Not the Right Fit (Intentional Non-Goals)

Because `👍kanban` makes deliberate, opinionated trade-offs around **zero-trust security (Priority #0)**, **agent-first MCP ergonomics (Priority #1)**, and **100% canonical Markdown persistence** (`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`), there are specific use cases it is **not** designed to fit. First is how the 8 compared platforms handle these 6 non-goal domains, followed by a routing guide showing whether to pair a companion tool alongside `👍kanban` (`🔗 Companion`) or adopt a dedicated system of record instead (`🧭 Dedicated`):

| Non-Goal Use Case | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Arbitrary Binary / DAM Hosting | ❌ | 🔐 | 🔐 | 🔐 | ❌ | ❌ | 🔐 | ✅ |
| WYSIWYG & Freeform Whiteboards | ❌ | 💸 | ❌ | ❌ | ❌ | ❌ | ✅ | 🔐 |
| Heavy ERP & Financial Billing | ❌ | 💸 | 💰 | ❌ | ❌ | ❌ | 🔐 | ❌ |
| Regulated Safety-Critical ALM | ❌ | 💸 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Customer Helpdesk / ITSM | ❌ | 💸 | 💰 | ❌ | ❌ | ❌ | ❌ | ❌ |
| Unreviewed Host Plugins / Iframes | ❌ | 🆓🔌 | ❌ | 🆓🔌 | ✅ | ✅ | ❌ | 🔐 |

* `🔗` **Companion:** Keep `👍kanban` as your hardened engineering and agentic hub, and bridge the specialized workload via links, safe SVG/PNG exports, REST, webhooks, or `/mcp/agent`.
* `🧭` **Dedicated:** Use a purpose-built platform as your primary system of record when this domain governs your daily workflow or regulatory boundary.

| Use Case | 👍kanban Fit | Recommended Tools (FOSS & Commercial) | How to Pair Alongside 👍kanban (or When to Replace) |
| --- | --- | --- | --- |
| **1. Binary / DAM Hosting** | 🔗 Companion | **FOSS:** SeaweedFS (`Apache-2.0`), Garage (`AGPLv3`), RustFS (`Apache-2.0`), Forgejo Releases, Immich, Nextcloud. **Commercial:** AWS S3, GitHub Releases/LFS, Artifactory, Bynder | Host large binaries, CAD, or raw video externally; attach immutable URLs in Markdown or `url`/`badge` custom fields, and embed `PNG`/`WebP`/`SVG` previews via `/api/v1/media-proxy`. |
| **2. WYSIWYG & Whiteboards** | 🔗 Companion | **FOSS:** Excalidraw (`MIT`), Penpot (`MPL-2.0`), BookStack (`MIT`), AFFiNE. **Commercial:** Businessmap Whiteboards, Miro, FigJam, Notion, Confluence | Sketch in Excalidraw/Penpot/Miro and paste exported `.svg`/`.png` snapshots into `👍kanban` (`nh3`-scrubbed), use Mermaid for architecture diagrams, and push action items via `/mcp/agent`. |
| **3. Heavy ERP & Billing** | 🔗 Companion | **FOSS:** Kimai (`AGPLv3`), ERPNext (`GPLv3`), Odoo CE. **Commercial:** Jira + Tempo, Harvest, NetSuite OpenAir, SAP S/4HANA | Run engineering delivery and `KAN-79` flow metrics in `👍kanban`, syncing issue keys and `activity_records` timestamps via REST or `KAN-75` webhooks; use an ERP directly if client billing is primary. |
| **4. Safety-Critical ALM** | 🧭 Dedicated | **FOSS:** StrictDoc (`Apache-2.0`), Doorstop, Tuleap. **Commercial:** PTC Codebeamer, Siemens Polarion ALM, Jama Connect | If auditors mandate single-tool DO-178C, ISO 26262, or FDA 21 CFR Part 11 qualification with ReqIF, FMEA, and e-signatures, choose Codebeamer/Polarion directly (or pair Git-backed `StrictDoc` for hybrid software delivery). |
| **5. Customer Helpdesk / ITSM** | 🔗 Companion | **FOSS:** Zammad (`AGPLv3`), Chatwoot (`MIT` CE), FreeScout, GLPI. **Commercial:** Jira Service Management, Zendesk, Freshdesk, ServiceNow | Keep public email intake, live chat, telephony/IVR, and SLA portals in Zammad/Chatwoot/JSM; escalate verified engineering bugs into `👍kanban` via REST or `/mcp/agent` `create_ticket` with `🏷️` external tags. |
| **6. Unreviewed Host Plugins** | 🧭 Dedicated | **FOSS:** Mattermost Plugins (`Apache-2.0` / `AGPLv3`), Discourse, Jenkins. **Commercial:** Jira Marketplace apps, GitHub Apps, Chrome Extensions | If arbitrary third-party JavaScript or host-level iframe execution inside your project management UI is an architectural prerequisite, choose commercial marketplaces directly; `👍kanban` intentionally restricts custom logic to sandboxed Wasmtime / `nsjail` engines with explicit cryptographic approvals. |
