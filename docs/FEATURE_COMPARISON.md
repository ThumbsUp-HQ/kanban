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
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Permissive FOSS License | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| On-Prem Multi-Container | ✅ | ❌ | ✅ | 💰 | ❌ | ❌ | ❌ | 💰 |
| Single-Container Run | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Multi-Card OIDC & LDAPS | ✅ | 💸 | 💰 | 💰 | ❌ | ❌ | 💸 | ✅ |
| Passkeys & Break-Glass | ✅ | 💸 | 💰 | 🔐 | ❌ | ❌ | 💰 | 💰 |
| Object RBAC & Explicit DENY | ✅ | 💰 | 💰 | 💰 | ❌ | ❌ | ✅ | ✅ |
| Workspace/Issue/Field RBAC | 🎯✅ | 💸 | ❌ | ❌ | ❌ | ❌ | 💰 | ✅ |
| Shared-With Pill & DB RLS | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Workspace Audit Logs | ✅ | 💸 | 💰 | 💰 | ❌ | ❌ | 💰 | ✅ |

Vibe Kanban and OpenAI Symphony are permissive `Apache-2.0` (`✅`): Vibe Kanban runs as a single-user local CLI/container (`✅`), whereas OpenAI Symphony is documented as an engineering preview for trusted environments that runs as a host Elixir/OTP daemon or Burrito binary rather than OCI containers (`❌`), executes repo-local `WORKFLOW.md` hooks via `bash -lc`, omits multi-tenant auth/OIDC/Passkeys/RBAC (`❌`), and keeps no persistent database or immutable audit ledger (`❌`). Plane uses copyleft `AGPLv3`, charges per seat for OIDC, LDAP, coarse RBAC, and audit logs (`💰`), and omits field-level RBAC (`❌`); Jira charges extra for SSO/audit policies via Atlassian Guard (`💸`) and relies on paid Marketplace apps for per-field edit locks (`💸`); Businessmap gates custom role matrices behind Enterprise (`💰`); and only Codebeamer ships native per-field tracker RBAC (`✅`) - while none of the seven enforces PostgreSQL Row-Level Security with a ubiquitous per-object `shared_with` pill (`❌`). **`👍kanban`** is 100% permissive `Apache-2.0` (`✅`) across standalone (`docker run`) and 5-network production stacks, shipping Multi-Card OIDC/OAuth2/LDAPS, WebAuthn Passkeys + break-glass triggers, 7-tier Object RBAC + explicit `DENY` ACLs, PostgreSQL 16 `FORCE ROW LEVEL SECURITY` surfaced via the `🛡️` Shared-With Header Pill, an immutable SHA-256 hash-chained audit ledger (`✅`), and active `KAN-83` expansion adding 30-permission Workspace, Issue, and Field-level RBAC across custom multi-role user labels (`🎯✅`).

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

OpenAI Symphony is free `Apache-2.0` software (`✅`), but it is a headless polling orchestrator and Phoenix LiveView run monitor rather than an issue tracker - requiring an external board such as Linear, GitHub Issues, Jira Cloud, Asana, or GitLab (`❌` across all board, view, hierarchy, property, and lifecycle rows). Jira caps free boards at 10 users and gates cross-project Gantt plans, deep hierarchies, and archiving behind Premium (`💰`), while scripted fields require paid Marketplace apps like ScriptRunner (`💸`). Plane gates custom properties behind paid tiers (`💰`), GitHub lacks Calendar views and hard-blocking WIP limits (`🔐`), Vibe Kanban sunsetted its hosted issue/org cloud in May 2026 after `v0.1.44` - leaving local git-worktree execution (`npx vibe-kanban`) as its active surface (`🔐`), and Businessmap/Codebeamer have no free tier at all (`❌`). **`👍kanban`** ships all five native views (`List`, `Board`, `Table`, `Calendar`, `Timeline`), 2D swimlanes with hard WIP limits, cycle-checked DAG hierarchies, hybrid principal + free-text `🏷️` assignee tags, audited `🔄` creator overrides, blast-radius soft delete, and Wasmtime/`nsjail` sandboxed script fields in its free `Apache-2.0` core (`✅`).

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

---

## 6. When 👍kanban Is Not the Right Fit (Intentional Non-Goals)

Because `👍kanban` makes deliberate, opinionated trade-offs around **zero-trust security (Priority #0)**, **agent-first MCP ergonomics (Priority #1)**, and **100% canonical Markdown persistence** (`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`), there are specific use cases it is **not** designed to fit. First is how the 8 compared platforms handle these 6 non-goal domains, followed by a routing guide showing whether to pair a companion tool alongside `👍kanban` (`🔗 Companion`) or adopt a dedicated system of record instead (`🧭 Dedicated`):

| Non-Goal Use Case | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
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
| **6. Host-Level Automation** | 🔗 Companion | **FOSS:** Node-RED (`Apache-2.0`), Activepieces (`MIT` CE), Windmill, OpenAI Symphony (`Apache-2.0`). **Commercial:** GitHub Actions, Zapier, Make | Keep in-platform `👍kanban` scripts AAL2-signed inside Wasmtime/`nsjail`; run unrestricted SaaS orchestration or host runners externally against scoped `/mcp/agent` tokens and `KAN-75` webhooks. |

### 1. Arbitrary Binary / DAM / Non-Document File Hosting
* **Why it does not fit:** The attachment pipeline (`kanban/attachments/sniff.py`, `database/models/attachments.py`) enforces a strict `25 MiB` cap (`26,214,400` bytes), magic-byte validation, Pillow pixel re-encoding (stripping EXIF/metadata), SVG AST scrubbing, and bounded-subprocess active-content-stripped PDFs (`KAN-81`).
* **Bad fit for:** Digital Asset Management (DAM), CAD/3D design workflows, raw video/audio review boards, or attaching large binaries (`.zip`, `.apk`, `.iso`, raw crash dumps, or executable build artifacts).

### 2. Pixel-Precise WYSIWYG Publishing & Freeform Visual Whiteboarding
* **Why it does not fit:** Every issue, comment, sticky, and doc is converted at ingestion into **100% canonical UTF-8 Markdown** (stripping custom HTML/CSS, inline styles, fonts, and arbitrary DOM widgets via `nh3` and hidden-DOM pruning). Project Stickies are structured text cards that promote into `ltree` Docs (`💡📄`), not an infinite 2D spatial canvas.
* **Bad fit for:** Marketing/design teams needing custom-styled HTML pages, Notion-style embedded database blocks/iframes, or Miro/FigJam-style freeform drawing and wireframing.

### 3. Heavy ERP / Financial Project Accounting & Resource Management
* **Why it does not fit:** `👍kanban` covers engineering delivery views (`List`, `Board`, `Table`, `Calendar`, `Timeline/Gantt`, 2D swimlanes, cycles, modules, and statistical flow metrics in `KAN-79`), but intentionally omits financial and HR machinery.
* **Bad fit for:** Billable time-tracking and timesheet approvals, CapEx/OpEx budget accounting, resource utilization heatmaps across hourly billing rates, or client invoicing.

### 4. Regulated Hardware / Safety-Critical ALM (DO-178C, ISO 26262, FDA 21 CFR Part 11)
* **Why it does not fit:** While `👍kanban` has an immutable SHA-256 hash-chained audit ledger (`activity_records`) and scripted transition gates (compared against Codebeamer in [Section 1](#1-security-identity-audit--deployment) and [Section 5](#5-orchestration-provenance--day-2-operations)), it is not a certified medical/automotive/avionics Application Lifecycle Management (ALM) suite.
* **Bad fit for:** Hardware/embedded compliance requiring formal ReqIF interchange, parameterized test-case execution matrices, FMEA/hazard analysis tables, or legally certified e-signature compliance packs out of the box.

### 5. Customer-Facing Helpdesk / Omnichannel ITSM (Zendesk / Jira Service Management)
* **Why it does not fit:** Access is built around authenticated workspace principals, explicit `🛡️` RBAC/ACL visibility, and PostgreSQL `FORCE ROW LEVEL SECURITY`.
* **Bad fit for:** Public anonymous email-to-ticket intake queues, live customer chat widgets, multi-tiered customer SLA/contract entitlement portals, or telephony/IVR call-center ticketing.

### 6. Low-Trust "Run Arbitrary Unreviewed Host Plugins" Automation
* **Why it does not fit:** Custom fields and workflow scripts are locked behind `SERVER_ADMIN` AAL2 cryptographic approvals (`manifest_sha256`), Wasmtime (`<25ms`) or `nsjail` (`128 MiB` RAM, `3s` timeout, isolated netns, GET-only token-injecting egress proxy), and strict `Content-Security-Policy` (`object-src 'none'`, `frame-ancestors 'none'`).
* **Bad fit for:** Teams that want non-admin users to install arbitrary third-party UI plugins, embed external SaaS iframes inside tickets, or trigger unrestricted outbound shell/network scripts from card transitions.
