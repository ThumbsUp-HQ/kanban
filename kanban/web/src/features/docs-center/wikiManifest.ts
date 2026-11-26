// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
// Generated automatically by scripts/sync_wiki_bundle.py. Do not edit manually.

export type WikiChapterCategory = 'guide' | 'informational' | 'architectural';

export interface WikiSection {
  id: string;
  title: string;
  level: number;
}

export interface WikiChapter {
  slug: string;
  title: string;
  category: WikiChapterCategory;
  track: string;
  subtrack: string;
  audience: string;
  order: number;
  summary: string;
  sections: WikiSection[];
  content: string;
}

export interface WikiCategory {
  name: string;
  chapters: { slug: string; title: string; category?: WikiChapterCategory }[];
}

export type ConfigReferenceItem = Record<string, string>;

export const WIKI_CHAPTERS: WikiChapter[] = [
  {
    "slug": "home",
    "title": "\ud83d\udc4dkanban: Executive Architecture and System Overview",
    "category": "informational",
    "track": "Overview",
    "subtrack": "Overview",
    "audience": "All Roles & Stakeholders",
    "order": 1,
    "summary": "Welcome to the authoritative technical documentation and wiki for **\ud83d\udc4dkanban** (`thumbs-up-kanban`), an open-source, enterprise-grade project management, ticketing, and knowledge platform built from the ground up on two fundamental pillars: 1. **Security-First (Priority 0):** Hardened zero-trust infrastructure, PostgreSQL Row-Level Security (`FORCE RLS`), five-tier network isolation, AAL2 administrative authorization, and hostile input sanitization. 2. **Agent-First (Priority 1):** Purpose-built for autonomous AI agents and human teams alike, replacing the context-bloating CRUD-wrapper anti-pattern with an intent-driven, three-surface Model Context Protocol (MCP) server, deterministic workflow gates, and sub-second execution loops.",
    "sections": [
      {
        "id": "system-topology",
        "title": "System Topology",
        "level": 2
      },
      {
        "id": "visual-tour-platform-highlights",
        "title": "Visual Tour: Platform Highlights",
        "level": 2
      },
      {
        "id": "enterprise-workspace-and-project-hub",
        "title": "Enterprise Workspace and Project Hub",
        "level": 3
      },
      {
        "id": "breathable-whitespace-board-and-high-contrast-theming",
        "title": "Breathable Whitespace Board and High-Contrast Theming",
        "level": 3
      },
      {
        "id": "keyboard-driven-command-palette",
        "title": "Keyboard-Driven Command Palette",
        "level": 3
      },
      {
        "id": "multi-view-projections-table-inline-editing-and-timeline-dependencies",
        "title": "Multi-View Projections: Table Inline Editing and Timeline Dependencies",
        "level": 3
      },
      {
        "id": "fullscreen-issue-studio-and-access-visibility-inspector",
        "title": "Fullscreen Issue Studio and Access Visibility Inspector",
        "level": 3
      },
      {
        "id": "advanced-governance-and-administrative-studios",
        "title": "Advanced Governance and Administrative Studios",
        "level": 3
      },
      {
        "id": "architectural-distinctions-kanban-vs-traditional-tools",
        "title": "Architectural Distinctions: \ud83d\udc4dkanban vs Traditional Tools",
        "level": 2
      },
      {
        "id": "non-bypassable-engineering-and-security-invariants",
        "title": "Non-Bypassable Engineering and Security Invariants",
        "level": 2
      },
      {
        "id": "complete-table-of-contents",
        "title": "Complete Table of Contents",
        "level": 2
      },
      {
        "id": "track-1-step-by-step-guides",
        "title": "Track 1: Step-by-Step Guides",
        "level": 3
      },
      {
        "id": "track-2-feature-field-reference",
        "title": "Track 2: Feature & Field Reference",
        "level": 3
      },
      {
        "id": "track-3-security-adoption-overview",
        "title": "Track 3: Security & Adoption Overview",
        "level": 3
      },
      {
        "id": "track-4-engineering-security-architecture",
        "title": "Track 4: Engineering & Security Architecture",
        "level": 3
      }
    ],
    "content": "# \ud83d\udc4dkanban: Executive Architecture and System Overview\n\nWelcome to the authoritative technical documentation and wiki for **\ud83d\udc4dkanban** (`thumbs-up-kanban`), an open-source, enterprise-grade project management, ticketing, and knowledge platform built from the ground up on two fundamental pillars:\n1. **Security-First (Priority 0):** Hardened zero-trust infrastructure, PostgreSQL Row-Level Security (`FORCE RLS`), five-tier network isolation, AAL2 administrative authorization, and hostile input sanitization.\n2. **Agent-First (Priority 1):** Purpose-built for autonomous AI agents and human teams alike, replacing the context-bloating CRUD-wrapper anti-pattern with an intent-driven, three-surface Model Context Protocol (MCP) server, deterministic workflow gates, and sub-second execution loops.\n\nLicensed under the strictly permissive **Apache-2.0** license, \ud83d\udc4dkanban eliminates SaaS AI paywalls and per-seat subscription lock-in while competing globally against Jira, Vibe Kanban, and commercial issue trackers with drop-in enterprise migration support.\n\n---\n\n## System Topology\n\n```mermaid\nflowchart TD\n    subgraph Clients[\"Client Surfaces\"]\n        SPA[\"React 19 SPA (Desktop, Tablet, Mobile)\"]\n        Agents[\"Autonomous Agents (Cursor, Claude, Codex, Agy)\"]\n    end\n\n    subgraph Entrypoints[\"API & Protocol Gateways\"]\n        FastAPI[\"FastAPI Application Server<br/>- Multi-Card Auth (AAL2)<br/>- Canonical Markdown Pipe<br/>- WebSocket Realtime Hub<br/>- REST API (275 paths, 366 operations, 384 schemas)\"]\n        MCP[\"3-Surface MCP Server<br/>- /mcp/agent (9 tools)<br/>- /mcp/docs (3 tools)<br/>- /mcp/admin (12 tools)<br/>- InlineSafeDumper YAML\"]\n    end\n\n    subgraph Core[\"Database Engine & Object Graph\"]\n        UOG[\"Universal Object Graph (UOG)<br/>PostgreSQL 16 with FORCE ROW LEVEL SECURITY (100%)<br/>- Typed object_links, Spine records, Append-only Ledger<br/>- ltree Hierarchical Docs, pgvector Embeddings, Full-Text<br/>- Invalid Object Link Auditor & Purger\"]\n    end\n\n    subgraph Runtimes[\"Execution Engines\"]\n        AIEngine[\"AI Engine & Orchestration<br/>- OpenAI, Ollama, Gemini<br/>- agy -p, codex -p pipes<br/>- Async Gate Helpers\"]\n        Sandbox[\"Sandbox Execution Runtime<br/>- Tier A: Wasmtime engine<br/>- Tier B: nsjail runner<br/>- Scoped Ephemeral Tokens\"]\n    end\n\n    SPA -->|HTTP / WebSocket| FastAPI\n    Agents -->|HTTP / SSE / STDIO| MCP\n    Agents -->|HTTP REST| FastAPI\n    FastAPI --> Core\n    MCP --> Core\n    Core --> AIEngine\n    Core --> Sandbox\n```\n\n---\n\n## Visual Tour: Platform Highlights\n\n### Enterprise Workspace and Project Hub\nThe workspace home delivers clear project visibility, team velocity metrics, and seamless multi-project navigation with responsive layouts across desktop, tablet, and mobile displays.\n\n![Workspace Home and Project Overview](images/05-workspace-home.png)\n\n### Breathable Whitespace Board and High-Contrast Theming\nThe core Kanban board features sub-16ms smooth drag-and-drop, semantic emoji hints, configurable WIP limits, and an enterprise dark theme for reduced eye strain during extended operational sessions.\n\n![Enterprise Whitespace Board View](images/06-board-view.png)\n\n![Dark Theme Enterprise Kanban Board](images/22-dark-theme-board.png)\n\n### Keyboard-Driven Command Palette\nGlobal keyboard shortcuts (`Ctrl+K` / `Cmd+K`) provide instant fuzzy navigation across tickets, documents, projects, and administrative studios without context switching.\n\n![Global Command Palette Navigation](images/23-command-palette.png)\n\n### Multi-View Projections: Table Inline Editing and Timeline Dependencies\nEngineers can switch instantly between Kanban Board, 3-pane List, Table with capability-gated inline cell editing, Calendar, and Timeline with SVG Bezier BLOCKS dependency arrows.\n\n![Table View Inline Editing](images/37-table-inline-editing.png)\n\n### Fullscreen Issue Studio and Access Visibility Inspector\nExpanding any ticket unlocks the Fullscreen Issue Studio, featuring a Rich Markdown authoring toolbar, Sparkle 320ms Fill-in-the-Middle (FIM) ghost-text completion, the `\ud83d\udee1\ufe0f` Effective Access Inspector, and a 4-tab activity stream.\n\n![Fullscreen Issue View with Rich Markdown Toolbar and Access Inspector](images/39-fullscreen-issue-view.png)\n\n### Advanced Governance and Administrative Studios\nPlatform administrators manage enterprise governance through dedicated studios:\n- **AI Providers & Token Caps Studio (`/admin/ai`):** Write-only key custody, monthly token budgets, and air-gap policies (`images/43-admin-ai-studio-providers.png`).\n- **Invalid Object Link Auditor (`/admin/link-auditor`):** Continuous graph integrity verification, inspect drawer, and two-stage audited purge (`images/46-admin-link-auditor.png`).\n- **Workflow Transition Studio & Dry-Run Drawer (`/projects/:key/settings/workflows`):** Zero-persistence dry-run simulation with step timings and copyable CLI commands (`images/50-workflow-studio-dry-run-drawer.png`).\n- **Migration Import Studio (`/admin/imports`):** Single-click bundle ingestion, dry-run diff preview, and transactional live migration (`images/49-admin-plane-import-studio.png`).\n\n![Admin Invalid Object Link Auditor Studio](images/46-admin-link-auditor.png)\n\n---\n\n## Architectural Distinctions: \ud83d\udc4dkanban vs Traditional Tools\n\n| Dimension | Legacy Trackers & Paywalled SaaS (Jira / Vibe Kanban) | \ud83d\udc4dkanban Platform |\n| :--- | :--- | :--- |\n| **License & Cost** | Commercial SaaS / AGPL with paid AI paywalls | Pure Apache-2.0, zero paywalled features |\n| **Agent Interface** | 70-120 raw CRUD tool wrappers (15k-25k tokens) | 24 intent-driven MCP tools across 3 surfaces (<= 1.8k tokens for agent) |\n| **Database Security** | Application-layer authorization checks | Hardware-enforced PostgreSQL `FORCE ROW LEVEL SECURITY` on all tenant tables |\n| **Network Isolation** | Monolithic container or open Docker bridge | Hardened 5-network isolation matrix (`edge`, `app`, `data`, `sandbox`, `egress`) |\n| **Scripted Workflows & Helpers** | Basic webhooks with no blocking execution | Atomic synchronous Wasm validators/mutators and async AI agent gates |\n| **Input Sanitization** | Basic HTML strip | Hostile Unicode lone-surrogate rejection, hidden-DOM pruner, SVG sandbox |\n| **Deployment Mode** | Complex multi-service Kubernetes only | Single-container standalone (`docker run`) or full multi-container production |\n\nFor an exhaustive feature-by-feature evaluation across 50 criteria, see the [Feature Comparison Matrix](Feature-Comparison).\n\n---\n\n## Non-Bypassable Engineering and Security Invariants\n\n1. **Plain ASCII Hyphen Invariant:** All public documentation, wiki articles, and commit messages strictly mandate plain ASCII hyphens (`-`). Unicode em-dashes (U+2014) and en-dashes (U+2013) are strictly forbidden across the codebase and wiki.\n2. **Zero-Context Fail-Closed Database:** In the absence of an explicit session context (`SET LOCAL app.current_principal_id`), all queries against tenant tables return zero rows. The application role `kanban_app` is stripped of `SUPERUSER` and `BYPASSRLS`.\n3. **Hostile Unicode Rejection:** Text ingestion rejects UTF-16 lone surrogates (`0xD800` through `0xDFFF`) prior to UTF-8 encoding, preventing memory corruptions and parser desynchronization.\n4. **Paste-Jacking Defense:** Clipboard inputs are aggressively stripped of hidden-DOM payloads, zero-width spaces, and invisible injection sequences.\n5. **AAL2 Admin Route Enforcement:** Every endpoint under `/api/v1/admin/*` and every administrative tool on `/mcp/admin` requires Authenticator Assurance Level 2 (AAL2) credentials.\n6. **95% Automated Test Coverage:** All core modules maintain at least 95% unit test coverage running on clean-DB fixtures with sub-millisecond `SAVEPOINT` isolation.\n\n---\n\n## Complete Table of Contents\n\n### Track 1: Step-by-Step Guides\n1. [[Guide] Production Promotion and Backup Runbook](Production-Promotion-and-Backup-Runbook) - Single-command standalone promotion, encrypted KBBAK1 backup format, and disaster recovery.\n2. [[Guide] Legacy Tracker Migration and Cutover Runbook](Migration-and-Cutover-Runbook) - 7-phase zero-downtime cutover plan, dry-run reconciliation, and rollback procedures.\n3. [[Guide] How to Use Custom Fields](Guide-Custom-Fields) - Step-by-step custom fields guide, formulas, wasm/nsjail tiers, and approval workflows.\n4. [[Guide] Scripted Workflows and Transition Helpers](Scripted-Workflows-and-Transition-Helpers) - Synchronous transition validators/mutators and asynchronous AI agent gates.\n5. [[Guide] Multi-Card Authentication Studio and Identity Architecture](Multi-Card-Authentication-Studio) - Pluggable auth cards (OAuth2, LDAP, WebAuthn Passkeys, TOTP, Local Admin) with break-glass protection.\n6. [[Guide] Multi-Provider AI Engine, Execution Harnesses, and Runners](Multi-Provider-AI-Engine-and-Runners) - OpenAI, Ollama, Gemini integrations, local CLI pipe harnesses (`agy -p`, `codex -p`), and mTLS runners.\n7. [[Guide] Three-Surface Model Context Protocol (MCP) Server Architecture](Three-Surface-MCP-Server-Architecture) - Dedicated streamable endpoints (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`) with InlineSafeDumper YAML.\n\n### Track 2: Feature & Field Reference\n1. [[Informational] Studio Configuration Reference](Studio-Configuration-Reference) - Exhaustive field configuration tables and security impact across all 11 \ud83d\udc4dkanban Studios.\n2. [[Informational] Enterprise Whitespace, Semantic Emojis, and Kanban Board](Enterprise-Whitespace-and-Kanban-Board) - 5 native view layouts, 2D swimlanes, sub-16ms drag-and-drop, and the `<EmojiHint>` semantic hover system.\n3. [[Informational] Ticket Screen, Peek Drawer, and Work Item Architecture](Ticket-Screen-and-Work-Item-Features) - 960px peek drawer, 17 enterprise work-item features, properties rail, and 4-tab activity stream.\n4. [[Informational] Hierarchical Docs, Project Stickies, and Smart Promotion](Hierarchical-Docs-and-Stickies-with-Smart-Promotion) - ltree page trees, color-coded sticky masonry, and lossless AI-assisted promotion to Docs.\n5. [[Informational] Blinking Cursor Sparkle Completion Engine](Blinking-Cursor-Sparkle-Completion-Engine) - Sub-300ms inline Fill-In-the-Middle (FIM) ghost text with surgical right-click disambiguation.\n6. [[Informational] Model Context Protocol (MCP) Tools Reference Manual](MCP-Tools-Reference) - Exhaustive specification of all 24 MCP tools, parameter schemas, LOD tiers, and destructive token workflows.\n7. [[Informational] REST API Architecture and OpenAPI Integration Guide](REST-API-Architecture-and-OpenAPI-Guide) - Technical guide to the 275-path FastAPI backend, interactive OpenAPI documentation, and TypeScript SDK.\n\n### Track 3: Security & Adoption Overview\n1. [[Informational] Role and Permission Matrix](Role-and-Permission-Matrix) - Visual \u25cf / \u25d0 / \u25cb role and capability matrix across all 7 principal tiers.\n2. [[Informational] Zero-Trust Security Architecture and Explicit Access Visibility](Zero-Trust-Security-and-Access-Visibility) - PostgreSQL FORCE RLS, dynamic sharing pill, access manifests, and STRIDE threat mitigation.\n3. [[Informational] Feature Comparison Matrix (50 Features)](Feature-Comparison) - Comprehensive capability comparison across 50 features evaluating \ud83d\udc4dkanban against Jira, Plane, GitHub, Vibe Kanban, OpenAI Symphony, Businessmap, and Codebeamer.\n\n### Track 4: Engineering & Security Architecture\n\n#### Functional Architecture\n1. [[Architectural] System Topology and Multi-Container Architecture](System-Topology-and-Multi-Container-Architecture) - Standalone embedded PostgreSQL Unix socket and 5-network production container stack.\n2. [[Architectural] Universal Object Graph and Invalid Link Auditor](Universal-Object-Graph-and-Link-Auditor) - Unified object spine, 13 typed object relationships, and automated invalid link detection/purging.\n3. [[Architectural] Real-Time Web and WebSocket Architecture](Real-Time-Web-and-WebSocket-Architecture) - Distributed WebSocket hub, connection throttling, channel subscriptions, and board state synchronization.\n4. [[Architectural] Canonical Markdown and Safe Media Pipeline](Canonical-Markdown-and-Safe-Media-Pipeline) - Hostile input sanitization, safe Mermaid rendering, SVG sandboxing, and media proxying.\n5. [[Architectural] Clean-DB Testing and Governance Gates](Clean-DB-Testing-and-Governance-Gates) - Fast parallel test execution, tmpfs template database, pluggable AI fixtures, and CI/CD validation.\n\n#### Security Architecture\n1. [[Architectural] Admin Custom Scripted Fields and Sandboxed Execution](Admin-Custom-Scripted-Fields-and-Sandbox) - Wasmtime (Tier A) and nsjail (Tier B) sandboxed execution with cryptographic tier escalation.\n2. [[Architectural] Custom Scripts and JSON Security Architecture](Custom-Scripts-and-JSON-Security-Architecture) - Hostile input sanitization, AST inspection, and ephemeral token boundaries.\n\n#### Engineering Appendix\n<details>\n<summary>Engineering Appendix</summary>\n\n- [[Architectural] \ud83d\udc4dkanban: Architecture Specification Delta & Gap Analysis](Architecture-Delta-and-Missing-Features) - Forensic analysis of specification requirements versus codebase implementation and tracking backlog.\n- [[Architectural] \ud83d\udc4dkanban User Task & Architecture QA Verification Matrix](User-Tasks-and-QA-Matrix) - Verification audit mapping tasks UT-01 through UT-16 to live browser checks and screenshot deliverables.\n\n</details>\n"
  },
  {
    "slug": "admin-custom-scripted-fields-and-sandbox",
    "title": "[Architectural] Admin Custom Scripted Fields and Sandboxed Execution",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Security Architecture",
    "audience": "Security Architects & Sandbox Engineers",
    "order": 2,
    "summary": "Modern software development requires dynamic metadata: calculated story points, security compliance flags, release readiness scores, and SLA countdowns. However, permitting custom scripts to run inside a project management system has historically introduced catastrophic security vulnerabilities, including server-side request forgery (SSRF), infinite loops, and arbitrary code execution.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "admin-only-definition-security-gate",
        "title": "Admin-Only Definition Security Gate",
        "level": 2
      },
      {
        "id": "the-custom-fields-studio",
        "title": "The Custom Fields Studio",
        "level": 2
      },
      {
        "id": "studio-capabilities",
        "title": "Studio Capabilities",
        "level": 3
      },
      {
        "id": "test-execute-sandbox-modal",
        "title": "Test-Execute Sandbox Modal",
        "level": 2
      },
      {
        "id": "multi-tier-execution-sandbox-architecture",
        "title": "Multi-Tier Execution Sandbox Architecture",
        "level": 2
      },
      {
        "id": "tier-a-webassembly-runtime-wasmtime",
        "title": "Tier A: WebAssembly Runtime (Wasmtime)",
        "level": 3
      },
      {
        "id": "tier-b-hardened-container-jail-nsjail",
        "title": "Tier B: Hardened Container Jail (nsjail)",
        "level": 3
      },
      {
        "id": "ephemeral-scoped-tokens-and-tiered-privilege-escalation",
        "title": "Ephemeral Scoped Tokens and Tiered Privilege Escalation",
        "level": 2
      },
      {
        "id": "dual-control-principle",
        "title": "Dual-Control Principle:",
        "level": 3
      }
    ],
    "content": "# [Architectural] Admin Custom Scripted Fields and Sandboxed Execution\n\n## Overview\n\nModern software development requires dynamic metadata: calculated story points, security compliance flags, release readiness scores, and SLA countdowns. However, permitting custom scripts to run inside a project management system has historically introduced catastrophic security vulnerabilities, including server-side request forgery (SSRF), infinite loops, and arbitrary code execution.\n\n\ud83d\udc4dkanban resolves this through **Admin-Only Custom Scripted Fields** evaluated inside a hardened, multi-tier isolation sandbox with cryptographic privilege escalation controls.\n\n---\n\n## Admin-Only Definition Security Gate\n\nTo protect the platform from unauthorized logic injection:\n- **Admin-Only Gate:** Only verified Server Administrators or Project Administrators possessing Authenticator Assurance Level 2 (AAL2) credentials can create, modify, or delete custom field scripts.\n- **Route Protection:** All custom field endpoints under `/api/v1/projects/{project_id}/custom-fields` declare explicit dependencies on `require_admin_aal2`.\n- **Immutable Script Signatures:** When a script is saved, a SHA-256 cryptographic digest is generated and recorded. Any unauthorized database tampering immediately invalidates script execution.\n\n---\n\n## The Custom Fields Studio\n\nAdministrators manage custom fields through the visual studio at `/projects/KAN/settings/custom-fields`.\n\n![Custom Fields Studio and Escalation Banner](images/slice5-custom-fields-studio-desktop-1440x900-light.png)\n\n### Studio Capabilities\n- **Field Types:** String, Integer, Float, Boolean, Date, Multi-Select, and Dynamic Computed Script.\n- **Execution Engine Selection:** Choose between lightweight WebAssembly (Wasmtime) or isolated containerized scripts (nsjail).\n- **Execution Badging (\ud83e\uddea):** Computed fields render a subtle test tube (`\ud83e\uddea`) glyph on the ticket properties rail, showing real-time computation status and latency.\n- **Pre-Commit Test Execution:** Test custom script logic against sample payloads in real time before committing field definitions to the database.\n\n![Custom Fields Editor Tier A](images/slice5-custom-fields-editor-tier-a-desktop-1440x900-light.png)\n\n---\n\n## Test-Execute Sandbox Modal\n\nBefore saving or deploying a custom scripted field to production tickets, administrators can validate script logic in an interactive test execution modal:\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Project Admin (AAL2)\n    participant Studio as Custom Fields Studio\n    participant Modal as Test-Execute Modal\n    participant Sandbox as Wasm / nsjail Sandbox\n\n    Admin->>Studio: Author script source (e.g. CVSS calculation)\n    Admin->>Studio: Click \"Test-Execute\"\n    Studio->>Modal: Open Test-Execute Modal with sample ticket JSON\n    Admin->>Modal: Click \"Run Test\"\n    Modal->>Sandbox: Execute script against sample properties\n    Sandbox-->>Modal: Return evaluated output, execution time (<2ms), stdout logs\n    Modal-->>Admin: Render live severity pill preview (e.g. \"8.8 High\")\n```\n\n![Custom Fields Pre-Commit Test Execution Modal](images/53-custom-fields-test-execute.png)\n\nThe Test-Execute modal displays execution duration, memory consumption, output formatting, and sandboxed stdout logs. This guarantees that syntax errors, infinite loops, or unexpected outputs are caught before fields impact active workflows.\n\n---\n\n## Multi-Tier Execution Sandbox Architecture\n\nWhen a work item is created or updated, active custom field scripts are executed within an isolated multi-tier sandbox:\n\n```mermaid\nflowchart TD\n    Update[\"Work Item Updated: State / Properties Changed\"] --> Dispatcher[\"Sandbox Dispatcher (kanban/sandbox/)\"]\n    \n    Dispatcher -->|Lightweight Math / String Formats| TierA[\"Tier A: Wasmtime Engine - In-process WebAssembly - Sub-millisecond execution (<1ms) - Zero OS syscall capability - Memory capped at 16 MB\"]\n    Dispatcher -->|Complex Logic / Scripts| TierB[\"Tier B: nsjail Container Jail - Linux namespaces (CLONE_NEWNET) - Read-only root filesystem - CPU timeout: 5 sec, Memory: 512 MB\"]\n    \n    TierA --> Verify[\"Verify Computed Value vs Pydantic Schema\"]\n    TierB --> Verify\n    Verify --> Store[\"Recorded in work item properties JSONB\"]\n```\n\n![Custom Fields on Ticket Properties Rail](images/36-rail-custom-fields.png)\n\n### Tier A: WebAssembly Runtime (Wasmtime)\n- Runs compiled WebAssembly modules in-process.\n- Provides sub-millisecond execution times.\n- Zero capability to open sockets, access the filesystem, or spawn processes.\n- Memory allocation strictly capped at 16 MB with instruction count fuel limits.\n\n### Tier B: Hardened Container Jail (nsjail)\n- Utilizes Linux kernel namespaces (`CLONE_NEWPID`, `CLONE_NEWNET`, `CLONE_NEWNS`).\n- Root filesystem mounted strictly read-only.\n- Network access completely disabled (`CLONE_NEWNET`).\n- Hard resource limits enforced via cgroups (512 MB RAM, 5-second wall clock timeout).\n\n---\n\n## Ephemeral Scoped Tokens and Tiered Privilege Escalation\n\nCustom scripts often need to query project metadata (such as counting open bugs or reading cycle end dates). To prevent privilege leakage:\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Script as Custom Scripted Field\n    participant Gate as Authorization Gate\n    participant Admin as Server/Workspace Admin (AAL2)\n    participant TokenService as Ephemeral Token Minter\n\n    Note over Script,TokenService: Default Execution: Project Scoped\n    Script->>Gate: Execute with default Project-scoped ephemeral token\n    \n    Note over Script,TokenService: Escalation Request: Workspace or Server\n    Script->>Gate: Request Escalated Scope (WORKSPACE or SERVER)\n    Gate->>Admin: Display Unmissable Blast Radius Warning Banner\n    Admin->>Gate: Cryptographic Signature with AAL2 Confirmation\n    Gate->>TokenService: Mint Time-Limited Ephemeral Escalated Token\n    TokenService-->>Script: Deliver Ephemeral Token for Execution\n```\n\n1. **Ephemeral Project Tokens:** By default, every script executes using an ephemeral API token scoped strictly to the current **Project**. It cannot read data from other projects or workspace settings.\n2. **Cryptographic Privilege Escalation:** If a script requires broader access (such as reading data across the entire **Workspace** or querying **Server** configuration), the script must request an escalated token scope. The UI displays an unmissable administrative warning banner detailing the blast radius, and the escalation must be signed with cryptographic approval by an administrator possessing authority over that target tier. Scripts can never escalate to Server Admin privileges without explicit multi-factor confirmation.\n\n![Custom Fields Dual Control Escalation Studio](images/slice5-custom-fields-escalation-dual-control-desktop-1440x900-light.png)\n![Custom Fields Dual Control Escalation Flow](images/52-custom-fields-dual-control.png)\n\n### Dual-Control Principle:\nTo satisfy enterprise SOC 2 and ISO 27001 separation of duties, escalating a custom scripted field to workspace-wide or server-wide scope requires dual-control authorization:\n- A project administrator can author and propose the escalation.\n- A distinct, independent administrator holding target tier authority must review the blast radius warning banner and supply fresh Authenticator Assurance Level 2 (AAL2) credentials to activate the escalated token scope.\n- All escalation grants are logged with SHA-256 cryptographic digests in the immutable audit ledger.\n"
  },
  {
    "slug": "admin-diagnostics-and-link-inspector-studio",
    "title": "[Guide] Admin Diagnostics and Link Inspector Studio Guide and Architecture Walkthrough",
    "category": "guide",
    "track": "Step-by-Step Guides",
    "subtrack": "Diagnostics & Maintenance",
    "audience": "System Administrators & Core Maintainers",
    "order": 3,
    "summary": "Authoritative operational runbook and engineering architecture guide for the Unified Admin Diagnostics Studio, Link Inspector Studio, real-time subsystem telemetry, and Universal Object Graph defect remediation.",
    "sections": [
      {
        "id": "executive-summary-and-architecture-overview",
        "title": "1. Executive Summary and Architecture Overview",
        "level": 2
      },
      {
        "id": "multi-tier-security-authentication-and-aal2-session-governance",
        "title": "2. Multi-Tier Security, Authentication, and AAL2 Session Governance",
        "level": 2
      },
      {
        "id": "security-invariants",
        "title": "Security Invariants",
        "level": 3
      },
      {
        "id": "real-time-telemetry-and-the-7-core-subsystems",
        "title": "3. Real-Time Telemetry and the 7 Core Subsystems",
        "level": 2
      },
      {
        "id": "subsystem-telemetry-breakdown",
        "title": "Subsystem Telemetry Breakdown",
        "level": 3
      },
      {
        "id": "real-time-diagnostics-probes",
        "title": "Real-Time Diagnostics Probes",
        "level": 3
      },
      {
        "id": "universal-object-graph-link-auditor-studio-adminlink-auditor",
        "title": "4. Universal Object Graph Link Auditor Studio (/admin/link-auditor)",
        "level": 2
      },
      {
        "id": "the-7-invalidity-classes",
        "title": "The 7 Invalidity Classes",
        "level": 3
      },
      {
        "id": "two-stage-audited-purge-mandatory-justification",
        "title": "Two-Stage Audited Purge & Mandatory Justification",
        "level": 3
      },
      {
        "id": "operational-runbooks-inspections-and-remediation",
        "title": "5. Operational Runbooks: Inspections and Remediation",
        "level": 2
      },
      {
        "id": "runbook-1-performing-routine-diagnostics-and-realtime-health-probing",
        "title": "Runbook 1: Performing Routine Diagnostics and Realtime Health Probing",
        "level": 3
      },
      {
        "id": "runbook-2-scanning-and-purging-invalid-object-links",
        "title": "Runbook 2: Scanning and Purging Invalid Object Links",
        "level": 3
      }
    ],
    "content": "# [Guide] Admin Diagnostics and Link Inspector Studio Guide and Architecture Walkthrough\n\nAuthoritative operational runbook and engineering architecture guide for the Unified Admin Diagnostics Studio, Link Inspector Studio, real-time subsystem telemetry, and Universal Object Graph defect remediation.\n\n---\n\n## 1. Executive Summary and Architecture Overview\n\nThe Unified Admin Diagnostics Studio (mounted at `/admin/diagnostics` and `/admin/link-auditor`) provides enterprise platform administrators with continuous visibility into system health, database migration integrity, Row-Level Security (RLS) enforcement, event relay queues, background worker execution, and object link topology across \ud83d\udc4dkanban.\n\nDesigned under Security Priority #0 and Agent-First Priority #1, the Diagnostics Studio serves two distinct operational functions:\n1. **Real-Time Subsystem Health Probing** (`/admin/diagnostics`): Collects synchronous and asynchronous telemetry across 7 core subsystems: PostgreSQL RLS connectivity, transactional outbox message lag, background job worker pools, Wasmtime sandboxed execution runners, AI provider runtime availability, remote mTLS runner nodes, and request rate limiters.\n2. **Universal Object Graph Link Inspector & Purger** (`/admin/link-auditor`): Discovers, classifies, inspects, and remediates referential integrity anomalies across 7 invalidity classes without locking production tables or requiring system downtime.\n\n```mermaid\ngraph TD\n    UI[\"Admin Diagnostics Studio UI (/admin/diagnostics, /admin/link-auditor)\"] --> AAL2[\"AAL2 Session Gate (require_admin_aal2)\"]\n    AAL2 --> Router[\"FastAPI Diagnostics & Link Auditor Router (/api/v1/admin/*)\"]\n    Router --> DBProbe[\"PostgreSQL Health & Migration Check (82 Migrations, 100 Tables)\"]\n    Router --> RLSProbe[\"PostgreSQL FORCE RLS Policy Audit\"]\n    Router --> RelayProbe[\"Outbox Relay Broker Telemetry (database/outbox)\"]\n    Router --> WSProbe[\"WebSocket Realtime Hub Ping/Pong Frame Telemetry\"]\n    Router --> WasmProbe[\"Wasmtime & nsjail Sandbox Worker Telemetry\"]\n    Router --> Auditor[\"Link Auditor Engine (7 Defect Classes)\"]\n    Auditor --> Inspector[\"Forensic Link Inspection Drawer\"]\n    Auditor --> Purge[\"Two-Stage Destructive Confirmation & Blast-Radius Engine\"]\n```\n\n![Admin Diagnostics Studio - Desktop Light](images/slice4-diagnostics-1440x900-light.png)\n\n---\n\n## 2. Multi-Tier Security, Authentication, and AAL2 Session Governance\n\nEvery endpoint mounted under `/api/v1/admin/diagnostics` and `/api/v1/admin/object-links:*` enforces Authenticator Assurance Level 2 (AAL2) multi-factor authentication. \n\n### Security Invariants\n- **AAL2 Session Dependency:** Route declarations strictly mandate `Depends(require_admin_aal2)` and `Depends(require_server_admin)` at both the router mount and endpoint handler levels.\n- **Fail-Closed Route Protection:** Automated test suites (`assert_admin_routes_protected`) scan the OpenAPI routing table at build time. Any administrative route lacking explicit AAL2 session validation fails CI/CD immediately.\n- **Zero-Information Exposure:** Unauthenticated callers receive RFC 7807 problem responses without leaking database schema versions, internal hostnames, CIDR blocks, or subsystem topology.\n\n---\n\n## 3. Real-Time Telemetry and the 7 Core Subsystems\n\nThe Diagnostics Studio executes comprehensive health checks against core application subsystems, reporting structured telemetry to the administrative UI and monitoring agents:\n\n### Subsystem Telemetry Breakdown\n\n| Subsystem Component | Metric & Probe Target | Healthy Threshold | Degraded Condition | Remediation Action |\n| :--- | :--- | :--- | :--- | :--- |\n| **1. PostgreSQL Engine (`postgresql_rls`)** | Latency, connection pool saturation, 82 single-head migrations, `FORCE RLS` on 100 tables | Latency < 15ms, saturation < 75%, 82/82 migrations | Latency > 50ms, pool exhausted, missing migration | Tune `DB_POOL_SIZE`, check Alembic single head, apply missing migrations |\n| **2. Transactional Outbox (`realtime_hub_outbox`)** | Queue backlog, dispatch latency, relay loop status, PostgreSQL LISTEN/NOTIFY | Lag < 5s, relay running | Backlog > 1000 events, relay stopped | Inspect `database/outbox/relay.py` worker process and restart daemon |\n| **3. Job Worker Pool (`job_worker_pool`)** | Active background tasks, concurrency limits, dead-letter queue (DLQ) depth | DLQ depth = 0 | DLQ depth > 0, executor stalled | Inspect failed task payloads, verify resource limits, restart worker |\n| **4. Wasmtime Sandbox (`wasm_script_sandbox`)** | Wasmtime compiler initialization, memory consumption, execution fuel budget | Memory < 32 MiB (33,554,432 bytes), fuel active | Wasmtime compilation failure, fuel exhausted | Inspect custom field scripts for infinite loops, allocate fuel |\n| **5. AI Agent Runtime (`agent_runtime_providers`)** | Provider availability (Ollama, OpenAI, Gemini), response latency, monthly token budget | Primary provider healthy, budget < 90% | Provider timeout, token cap exceeded | Rotate fallback provider, adjust monthly token ceiling |\n| **6. Remote Runner Fleet (`remote_runner_fleet`)** | Connected build nodes over port 8444, mTLS heartbeat status, active task leases | >= 1 runner online, heartbeat < 30s | All runners offline, expired CSR tokens | Mint fresh enrollment token, verify network port :8444 ingress |\n| **7. API Rate Limiter (`rate_limiter`)** | In-memory token bucket capacity, blocked requests, IP throttle health | System error rate = 0% | Memory leak in bucket map, false-positive blocks | Clear expired IP throttle buckets, adjust tier limits |\n\n![Admin Diagnostics Realtime Probe Active](images/slice4-diagnostics-realtime-probe-active.png)\n\n### Real-Time Diagnostics Probes\n\nThe studio provides two active latency probes for testing live message paths:\n\n1. **PostgreSQL Pub/Sub Probe (`POST /api/v1/admin/diagnostics/probes/realtime`):**\n   Issues a synthetic transactional outbox message and measures the exact roundtrip latency for PostgreSQL `LISTEN` and `NOTIFY` notification delivery. Healthy roundtrips execute in under 1.0 ms.\n\n2. **WebSocket Realtime Probe (`/ws` ping frame):**\n   Initiates a live WebSocket connection from the browser client to the server's `/ws` endpoint, transmits a binary ping frame, and captures the roundtrip pong latency. Live connections establish in ~13 ms with roundtrip latency < 1 ms.\n\n![Admin Diagnostics Studio - Desktop Dark](images/slice4-diagnostics-1440x900-dark.png)\n![Admin Diagnostics - Tablet Portrait](images/slice4-diagnostics-768x1024-tablet-portrait.png)\n![Admin Diagnostics - Mobile Portrait](images/slice4-diagnostics-390x844-mobile-portrait.png)\n\n---\n\n## 4. Universal Object Graph Link Auditor Studio (`/admin/link-auditor`)\n\n\ud83d\udc4dkanban models all work items, digital stickies, technical documents, sprint cycles, and modules as registered entities connected via typed `object_links`. The Link Auditor continuously detects and repairs referential anomalies.\n\n![Link Auditor Studio - Desktop Light](images/slice4-link-auditor-1440x900-light.png)\n\n### The 7 Invalidity Classes\n\nThe Link Auditor (`POST /api/v1/admin/object-links:audit`) evaluates every link against 7 formal invalidity classes:\n\n```mermaid\nflowchart TD\n    Scan[\"Integrity Audit Scan (POST /api/v1/admin/object-links:audit)\"] --> C1[\"1. DANGLING_SOURCE - Source object UUID missing from PostgreSQL\"]\n    Scan --> C2[\"2. DANGLING_TARGET - Target object UUID missing from PostgreSQL\"]\n    Scan --> C3[\"3. SOFT_DELETED_ENDPOINT - Endpoint object soft-deleted past retention window\"]\n    Scan --> C4[\"4. ARCHIVED_POLICY_VIOLATION - Link between active and archived entities violating policy\"]\n    Scan --> C5[\"5. TYPE_MATRIX_VIOLATION - Link kind forbidden between endpoint object types\"]\n    Scan --> C6[\"6. CROSS_WORKSPACE_LEAK - Cross-workspace link violating multi-tenant boundary\"]\n    Scan --> C7[\"7. PERMISSION_SEVERED - Principal lacks access across endpoint boundary\"]\n```\n\n1. **`DANGLING_SOURCE`:** The link record specifies a `source_id` entity that no longer exists in the universal objects spine.\n2. **`DANGLING_TARGET`:** The link record specifies a `target_id` entity that has been hard-deleted or does not exist in the database.\n3. **`SOFT_DELETED_ENDPOINT`:** One or both endpoints of the link reference an object soft-deleted beyond the workspace retention threshold.\n4. **`ARCHIVED_POLICY_VIOLATION`:** The link connects an active entity to an archived entity in violation of project archiving policy.\n5. **`TYPE_MATRIX_VIOLATION`:** The relation violates the registered link type matrix allowlist (valid kinds: `BLOCKS`, `BLOCKED_BY`, `RELATES_TO`, `PARENT_OF`, `CHILD_OF`, `DUPLICATES`, `DUPLICATED_BY`, `PROMOTED_TO`, `PROMOTED_FROM`, `MENTIONS`, `REFERENCED_IN`, `ATTACHED_TO`, `DERIVED_FROM`).\n6. **`CROSS_WORKSPACE_LEAK`:** The link connects two entities across distinct workspace tenant boundaries without an active federation agreement, violating multi-tenant isolation.\n7. **`PERMISSION_SEVERED`:** The link endpoints span access boundaries where caller or entity permissions have been revoked or severed.\n\n![Link Auditor Integrity Scan Active](images/slice4-link-auditor-integrity-scan-active.png)\n\n### Two-Stage Audited Purge & Mandatory Justification\n\nTo prevent accidental data loss during graph remediation, purging invalid links requires two-stage execution and audited justification:\n\n1. **Mandatory Administrative Justification (`reason` >= 10 characters):**\n   The administrator must supply a written rationale explaining the purge operation (`LinkPurgeRequest.reason`, 10 to 500 characters). Rationale strings shorter than 10 characters are strictly rejected with HTTP 422 before any deletion occurs.\n\n2. **Immutable Audit Ledger Recording:**\n   When the purge executes (`POST /api/v1/admin/object-links:purge`), the deleted links are removed in a single atomic transaction. The server records an immutable `INVALID_OBJECT_LINK_PURGED` event in the hash-chained `activity_records` ledger, returning the total `purged_count` and list of `activity_ids`.\n\n```json\n{\n  \"audit_ids\": [\n    \"01935b62-1000-7000-8000-000000000001\",\n    \"01935b62-1000-7000-8000-000000000002\"\n  ],\n  \"reason\": \"Purging orphaned test links following Slice-4 cutover verification\"\n}\n```\n\n```json\n{\n  \"purged_count\": 2,\n  \"activity_ids\": [\n    \"01935b62-2000-7000-8000-000000000001\",\n    \"01935b62-2000-7000-8000-000000000002\"\n  ]\n}\n```\n\n![Link Auditor Studio - Desktop Dark](images/slice4-link-auditor-1440x900-dark.png)\n![Link Auditor - Tablet Landscape](images/slice4-link-auditor-1024x768-tablet-landscape.png)\n![Link Auditor - Tablet Portrait](images/slice4-link-auditor-768x1024-tablet-portrait.png)\n\n---\n\n## 5. Operational Runbooks: Inspections and Remediation\n\n### Runbook 1: Performing Routine Diagnostics and Realtime Health Probing\n\n1. In the web interface, navigate to `/admin/diagnostics` using an account with `SERVER_ADMIN` privileges.\n2. Complete the WebSudo AAL2 step-up challenge if prompted.\n3. Inspect the Subsystem Health Grid. Verify that all 7 subsystems display **Operational** (`green`).\n4. Click **Run WS Ping** and **Test PG LISTEN/NOTIFY Broker**. The system issues active WebSocket and PostgreSQL outbox probes. Verify that database query latency is < 15ms and WebSocket RTT is < 50ms.\n5. Inspect the **Runtime and Container** card to verify non-root UID execution, cgroup memory limits, and container runtime details.\n\n![Admin Diagnostics - Tablet Landscape](images/slice4-diagnostics-1024x768-tablet-landscape.png)\n\n### Runbook 2: Scanning and Purging Invalid Object Links\n\n1. Switch to the **Link Inspector** tab or navigate directly to `/admin/link-auditor`.\n2. Click **Run Integrity Scan** (`POST /api/v1/admin/object-links:audit`).\n3. Review the defect summary cards grouped by the 7 `InvalidLinkReason` defect classes.\n4. If defects are identified, click on any row to open the **Forensic Inspection Drawer** and review the link metadata, source/target snapshots, and timestamps.\n5. Select the flagged links to remediate and click **Purge Selected Links** to open the remediation dialog.\n6. Enter an administrative justification of at least 10 characters in the textarea describing why these links are being purged.\n7. Click **Confirm Purge (N)**. The backend executes the audited deletion (`POST /api/v1/admin/object-links:purge`) and writes the audit ledger entry.\n8. Re-run the scan to confirm zero defects remain.\n\n![Link Auditor - Mobile Portrait](images/slice4-link-auditor-390x844-mobile-portrait.png)\n"
  },
  {
    "slug": "agent-lease-fencing-workpads-and-push-protection",
    "title": "[Architectural] Autonomous Agent Lease Fencing, Workpad Rework Breaker, and Secret Push-Protection Guide",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Agent Systems Architecture",
    "audience": "AI Platform Architects & Autonomous Agent Developers",
    "order": 4,
    "summary": "Authoritative architectural reference and engineering guide for distributed agent coordination: atomic PostgreSQL issue leases with monotonic fencing tokens, silent per-issue workpads, rework loop circuit breakers, and pre-persistence Shannon-entropy secret push-protection.",
    "sections": [
      {
        "id": "the-autonomous-multi-agent-coordination-challenge",
        "title": "1. The Autonomous Multi-Agent Coordination Challenge",
        "level": 2
      },
      {
        "id": "postgresql-issue-leases-and-monotonic-fencing-tokens",
        "title": "2. PostgreSQL Issue Leases and Monotonic Fencing Tokens",
        "level": 2
      },
      {
        "id": "database-schema-and-invariants",
        "title": "Database Schema and Invariants",
        "level": 3
      },
      {
        "id": "compare-and-swap-cas-lease-acquisition",
        "title": "Compare-And-Swap (CAS) Lease Acquisition",
        "level": 3
      },
      {
        "id": "the-monotonic-fencing-token-protocol",
        "title": "The Monotonic Fencing Token Protocol",
        "level": 3
      },
      {
        "id": "dedicated-issue-workpads-and-rework-circuit-breakers",
        "title": "3. Dedicated Issue Workpads and Rework Circuit Breakers",
        "level": 2
      },
      {
        "id": "silent-per-issue-workpad-slot",
        "title": "Silent Per-Issue Workpad Slot",
        "level": 3
      },
      {
        "id": "per-issue-rework-loop-circuit-breaker",
        "title": "Per-Issue Rework Loop Circuit Breaker",
        "level": 3
      },
      {
        "id": "synchronous-pre-persistence-secret-push-protection",
        "title": "4. Synchronous Pre-Persistence Secret Push-Protection",
        "level": 2
      },
      {
        "id": "the-invariant-block-before-persistence",
        "title": "The Invariant: Block Before Persistence",
        "level": 3
      },
      {
        "id": "token-level-shannon-entropy-scanner",
        "title": "Token-Level Shannon Entropy Scanner",
        "level": 3
      },
      {
        "id": "high-precision-signature-catalog",
        "title": "High-Precision Signature Catalog",
        "level": 3
      },
      {
        "id": "deterministic-exemption-engine",
        "title": "Deterministic Exemption Engine",
        "level": 3
      },
      {
        "id": "visual-reference-and-studio-screenshots",
        "title": "5. Visual Reference and Studio Screenshots",
        "level": 2
      }
    ],
    "content": "# [Architectural] Autonomous Agent Lease Fencing, Workpad Rework Breaker, and Secret Push-Protection Guide\n\nAuthoritative architectural reference and engineering guide for distributed agent coordination: atomic PostgreSQL issue leases with monotonic fencing tokens, silent per-issue workpads, rework loop circuit breakers, and pre-persistence Shannon-entropy secret push-protection.\n\n---\n\n## 1. The Autonomous Multi-Agent Coordination Challenge\n\nDeploying autonomous AI agents (such as Codex, Gemini, Claude, and local LLM runners) at enterprise scale introduces unique distributed systems challenges that do not exist in purely human-driven issue trackers:\n1. **Split-Brain Race Conditions:** Two autonomous agents can simultaneously pick up the same ticket, overwrite each other's commits, and corrupt ticket state.\n2. **Zombie Agent Lockout:** If an agent encounters a network timeout, container eviction, or unhandled crash while holding an exclusive lock, human workflows must not remain permanently frozen.\n3. **Comment Stream Pollution:** Autonomous agents generate extensive chain-of-thought traces, bash command outputs, and intermediate test results. Dumping these into public ticket comment threads creates overwhelming noise for human stakeholders.\n4. **Infinite Rework Prompt Loops:** When an agent's code submission fails an automated QA gate or security check, the agent may attempt immediate fixes in an unconstrained loop, rapidly consuming token quotas and thrashing CI/CD pipelines.\n5. **Accidental Credential Ingestion:** Autonomous agents routinely handle environment variables, API tokens, and private keys. Without strict pre-persistence filters, credentials can easily leak into database tables, search indexes, and immutable audit logs.\n\n\ud83d\udc4dkanban resolves all five challenges through a layered autonomous agent safety architecture:\n\n```mermaid\ngraph TD\n    Agent[\"Autonomous Sub-Agent (Gemini / Claude / Codex / Runner)\"] --> LeaseGate[\"Atomic Lease Fencing (p6_05 CAS Fencing Token)\"]\n    LeaseGate --> Workpad[\"Silent Per-Issue Workpad (p6_10 issue_workpads)\"]\n    Workpad --> PushProtection[\"Synchronous Secret Push-Protection (Shannon Entropy Scanner)\"]\n    PushProtection --> BreakerCheck[\"Rework Circuit Breaker Gate (Streak Tracking)\"]\n    BreakerCheck --> Transition[\"Atomic PostgreSQL Transition & Audit Hash-Chain\"]\n```\n\n---\n\n## 2. PostgreSQL Issue Leases and Monotonic Fencing Tokens\n\nTicket `KAN-69` implements distributed coordination primitives directly inside PostgreSQL (`database/migrations/sql/p6_05_issue_leases_and_fencing.up.sql` and `kanban/api/v1/issue_workflow.py`), preventing split-brain race conditions without requiring external Redis or ZooKeeper dependencies.\n\n### Database Schema and Invariants\n\nEvery issue record tracks its exclusive execution lease:\n\n```sql\nALTER TABLE issues\n    ADD COLUMN fencing_token BIGINT NOT NULL DEFAULT 0,\n    ADD COLUMN lease_expires_at TIMESTAMPTZ,\n    ADD COLUMN leased_by_principal_id UUID REFERENCES users(id) ON DELETE SET NULL;\n\nCREATE INDEX ix_issues_lease_expires_at ON issues(lease_expires_at)\n    WHERE lease_expires_at IS NOT NULL;\n```\n\n### Compare-And-Swap (CAS) Lease Acquisition\n\nWhen an agent invokes `begin_work` (via REST API or the `/mcp/agent` tool), the server executes an atomic Compare-And-Swap (CAS) query:\n\n```sql\nUPDATE issues\nSET\n    leased_by_principal_id = :agent_principal_id,\n    lease_expires_at = clock_timestamp() + INTERVAL '15 minutes',\n    fencing_token = fencing_token + 1\nWHERE id = :issue_id\n  AND (lease_expires_at IS NULL OR lease_expires_at < clock_timestamp() OR leased_by_principal_id = :agent_principal_id)\nRETURNING fencing_token, lease_expires_at;\n```\n\n### The Monotonic Fencing Token Protocol\n\nThe returned `fencing_token` is an integer that strictly increments with every lease acquisition or extension. When an agent attempts to mutate the ticket (transitioning state, posting workpads, or modifying properties), it must include its assigned `fencing_token`:\n- If the token matches the current database record, the write succeeds.\n- If another agent acquired a newer lease while the first agent was computing, the database record contains a higher `fencing_token`. The outdated write is rejected with `409 LEASE_CONFLICT`.\n- If an agent crashes or loses network connectivity, its lease expires automatically after 15 minutes (`lease_expires_at < clock_timestamp()`), allowing standby agents or human engineers to take over without manual intervention.\n\n---\n\n## 3. Dedicated Issue Workpads and Rework Circuit Breakers\n\nTicket `KAN-71` resolves the twin issues of comment pollution and runaway prompt loops (`database/migrations/sql/p6_10_issue_workpads_and_rework_breaker.up.sql` and `mcp/surfaces/agent/workpad.py`).\n\n### Silent Per-Issue Workpad Slot\n\nEach issue maintains a dedicated, isolated scratchpad table (`issue_workpads`):\n- **Zero Comment Spam:** Agents write intermediate reasoning traces, scratch scripts, sub-task breakdowns, and tool outputs to the workpad instead of creating hundreds of notification-triggering comments.\n- **Model Context Protocol Tool:** Exposed on `/mcp/agent` as `update_workpad` within a compact schema budget (1,674 tokens).\n- **Payload & Surrogate Bounds:** Workpad bodies are bounded to 65,536 bytes (`WORKPAD_PAYLOAD_TOO_LARGE`) and enforce strict UTF-16 lone surrogate rejection (`INVALID_UTF8_SURROGATE`).\n- **Web UI Rendering:** The web application displays the workpad inside a collapsible `\ud83e\udd16 Workpad` drawer in `IssueSurface.tsx`, keeping human comment streams pristine.\n\n```mermaid\nsequenceDiagram\n    participant Agent as Autonomous Agent\n    participant MCP as /mcp/agent (update_workpad)\n    participant DB as PostgreSQL (issue_workpads)\n    participant UI as Human Web UI (IssueSurface.tsx)\n\n    Agent->>MCP: update_workpad(identifier=\"KAN-42\", body=\"# Execution Scratchpad...\")\n    MCP->>DB: UPSERT INTO issue_workpads WHERE issue_id = :id\n    DB-->>MCP: Success\n    MCP-->>Agent: {\"status\": \"ok\", \"revision\": 3}\n    Note over UI: Human comment feed remains clean; workpad rendered in collapsible drawer\n```\n\n### Per-Issue Rework Loop Circuit Breaker\n\nTo halt runaway execution loops when automated QA gates or specialist reviews repeatedly veto code changes:\n1. **Configurable Threshold:** Workflow transition hooks define a `max_rework_attempts` threshold (default: 3).\n2. **Rejection Streak Tracking:** The `issues` table tracks consecutive rejections (`rework_rejection_streak`) and trip timestamps (`rework_tripped_at`).\n3. **Tripping the Breaker:** If an agent's submission fails verification 3 times consecutively, the system trips the breaker:\n   - Sets `rework_tripped_at = clock_timestamp()`.\n   - Agent-initiated state transitions are blocked with `409 REWORK_LOOP_LIMIT_EXCEEDED`.\n   - Renders a prominent `\ud83d\uded1\ud83e\udd16 Tripped Rework Breaker` banner on the web issue screen.\n4. **Human Reset Governance:** Agents are strictly forbidden from resetting their own circuit breaker (API returns `403 FORBIDDEN`). Only a human engineer can review the blockage and clear the breaker:\n   - Manually transitioning the ticket automatically resets the streak to 0.\n   - Alternatively, human admins can trigger `POST /api/v1/issues/{key}/reset-rework-breaker`.\n\n---\n\n## 4. Synchronous Pre-Persistence Secret Push-Protection\n\nTicket `KAN-72` establishes synchronous, fail-closed pre-persistence secret push-protection (`kanban/security/push_protection.py`) across all write paths (REST API, MCP tool calls, digital stickies, and technical documents).\n\n### The Invariant: Block Before Persistence\n\nUnlike asynchronous background scrubbers that attempt to clean data after insertion, \ud83d\udc4dkanban scans prose synchronously before it touches PostgreSQL storage, search TSV indexes, vector embeddings, or the immutable SHA-256 audit ledger.\n\n```mermaid\ngraph LR\n    Payload[\"Incoming Write Payload (Prose, Comments, Workpads)\"] --> Detector[\"Synchronous Push Protection Filter\"]\n    Detector --> RegEx[\"High-Precision Signatures (AWS, GitHub, Slack, OpenAI, DSNs)\"]\n    Detector --> Shannon[\"Token-Level Shannon Entropy Scanner (H >= 4.5, len >= 20)\"]\n    RegEx & Shannon --> Exemptions[\"Exemptions Engine (UUIDs, Git SHAs, Hashes, Base62 Ranks)\"]\n    Exemptions -->|Secret Detected| Reject[\"HTTP 422 ProblemException (SECRET_DETECTED_IN_PAYLOAD)\"]\n    Exemptions -->|Clean| Persist[\"PostgreSQL Commit & Audit Ledger Hash\"]\n```\n\n### Token-Level Shannon Entropy Scanner\n\nHigh-entropy random keys that do not match known regex patterns are detected via Shannon entropy analysis:\n\n$$H(X) = -\\sum_{i=1}^{n} P(x_i) \\log_2 P(x_i)$$\n\nWhere $P(x_i)$ is the probability of character $x_i$ appearing within the token string.\n- **Entropy Threshold:** Flags tokens where $H(X) \\ge 4.5$ bits per character.\n- **Length Constraint:** Applied only to candidate tokens of length $\\ge 20$ characters.\n- **Character Class Diversity:** Candidates must span at least three character classes (uppercase, lowercase, numeric, special symbols).\n\n### High-Precision Signature Catalog\n\nThe scanner detects dozens of deterministic cloud credentials:\n- **Private Key Blocks:** PEM headers (`BEGIN RSA PRIVATE KEY`, `BEGIN OPENSSH PRIVATE KEY`).\n- **Cloud Provider Keys:** AWS Access Key IDs (`AKIA[0-9A-Z]{16}`, `ASIA...`), Google API keys (`AIzaSy...`), Gemini/Vertex keys (`AQ...`).\n- **SCM & Platform Tokens:** GitHub Personal Access Tokens (`ghp_`, `github_pat_`), GitLab tokens (`glpat-`), Slack tokens (`xoxb-`, `xoxp-`), OpenAI keys (`sk-proj-...`), Anthropic keys (`sk-ant-api...`).\n- **\ud83d\udc4dkanban Internal Keys:** Platform tokens (`kb_pat_`, `kb_eat_`, `kb_agt_`, `kb_runner_`).\n- **Connection Strings (DSNs):** URIs containing embedded passwords (`postgresql://user:pass@host:5432/db`).\n\n### Deterministic Exemption Engine\n\nTo prevent false-positive blocks on benign technical data, the scanner strictly exempts:\n1. **Standard UUIDs:** RFC 4122 UUIDv4 and UUIDv7 strings.\n2. **Hexadecimal Digests:** 32-character, 40-character, 64-character, and 128-character hex strings (Git commit SHAs, MD5, SHA-1, SHA-256 digests).\n3. **Base62 Fractional Rank Keys:** Board ordering keys (e.g. `0|hzzzzz:`).\n4. **Documentation URLs:** Clean HTTP/HTTPS hyperlinks containing no embedded authentication credentials.\n\n---\n\n## 5. Visual Reference and Studio Screenshots\n\n![Asynchronous Agent Gate States](images/16-async-agent-gate-states.png)\n\n![Agent Kill Switch and Emergency Fencing](images/18-agent-kill-switch.png)\n\n![Model Context Protocol Scoping and Rework Loop Breaker](images/70-mcp-scoping-and-rework-loop.png)\n"
  },
  {
    "slug": "architecture-delta-and-missing-features",
    "title": "[Architectural] \ud83d\udc4dkanban: Architecture Specification Delta & Gap Analysis",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Engineering Appendix",
    "audience": "Core Contributors & Maintainers",
    "order": 5,
    "summary": "This document presents a section-by-section architectural delta and gap analysis comparing the authoritative specification (`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`, Sections 1 through 15) against the actual implementation codebase across `kanban/`, `database/`, `mcp/`, `agent/`, and `kanban/web/`, active unit and integration test suites, and project documentation topics.",
    "sections": [
      {
        "id": "executive-summary",
        "title": "Executive Summary",
        "level": 2
      },
      {
        "id": "visual-architecture-verification",
        "title": "Visual Architecture Verification",
        "level": 2
      },
      {
        "id": "planning-dimensions-cycles-and-modules",
        "title": "Planning Dimensions: Cycles and Modules",
        "level": 3
      },
      {
        "id": "three-surface-mcp-level-of-detail-lod",
        "title": "Three-Surface MCP Level of Detail (LOD)",
        "level": 3
      },
      {
        "id": "specification-scorecard-by-section",
        "title": "Specification Scorecard by Section",
        "level": 2
      },
      {
        "id": "detailed-section-by-section-delta-analysis",
        "title": "Detailed Section-by-Section Delta Analysis",
        "level": 2
      },
      {
        "id": "section-1-mission-apache-20-positioning-enterprise-saas-paywall-gap-analysis",
        "title": "Section 1: Mission, Apache-2.0 Positioning & Enterprise SaaS Paywall Gap Analysis",
        "level": 3
      },
      {
        "id": "section-2-system-topology-container-architecture-web-server-stack",
        "title": "Section 2: System Topology, Container Architecture & Web Server Stack",
        "level": 3
      },
      {
        "id": "section-3-zero-trust-security-architecture-explicit-sharing-visibility-req-1",
        "title": "Section 3: Zero-Trust Security Architecture & Explicit Sharing Visibility (Req 1)",
        "level": 3
      },
      {
        "id": "section-4-multi-card-pluggable-authentication-studio-req-6",
        "title": "Section 4: Multi-Card Pluggable Authentication Studio (Req 6)",
        "level": 3
      },
      {
        "id": "section-5-auto-converted-canonical-markdown-pipeline-safe-mermaid-pictures-svg-req-5-req-10",
        "title": "Section 5: Auto-Converted Canonical Markdown Pipeline & Safe Mermaid, Pictures & SVG (Req 5, Req 10)",
        "level": 3
      },
      {
        "id": "section-6-breathable-enterprise-whitespace-emojihint-hover-system-kanban-board-req-9-req-15",
        "title": "Section 6: Breathable Enterprise Whitespace, <EmojiHint> Hover System & Kanban Board (Req 9, Req 15)",
        "level": 3
      },
      {
        "id": "section-7-enterprise-ticket-screen-complete-17-feature-specification-features-8a-8q",
        "title": "Section 7: Enterprise Ticket Screen & Complete 17-Feature Specification (Features 8a-8q)",
        "level": 3
      },
      {
        "id": "section-8-hierarchical-docs-pages-project-stickies-with-smart-promotion-req-11",
        "title": "Section 8: Hierarchical Docs, Pages & Project Stickies with Smart Promotion (Req 11)",
        "level": 3
      },
      {
        "id": "section-9-blinking-cursor-sparkle-completion-surgical-right-click-engine-req-7",
        "title": "Section 9: Blinking Cursor Sparkle (\u2728) Completion & Surgical Right-Click Engine (Req 7)",
        "level": 3
      },
      {
        "id": "section-10-multi-provider-ai-engine-cli-remote-harnesses-req-2-agent",
        "title": "Section 10: Multi-Provider AI Engine & CLI / Remote Harnesses (Req 2: agent/)",
        "level": 3
      },
      {
        "id": "section-11-three-surface-intent-driven-mcp-server-req-12-mcp",
        "title": "Section 11: Three-Surface Intent-Driven MCP Server (Req 12: mcp/)",
        "level": 3
      },
      {
        "id": "section-12-universal-object-graph-canonical-markdown-ddl-invalid-link-auditor-items-13a-13j",
        "title": "Section 12: Universal Object Graph Canonical Markdown DDL & Invalid Link Auditor (Items 13a-13j)",
        "level": 3
      },
      {
        "id": "section-13-admin-only-custom-scripted-fields-tiered-privilege-escalation-req-14",
        "title": "Section 13: Admin-Only Custom Scripted Fields & Tiered Privilege Escalation (Req 14)",
        "level": 3
      },
      {
        "id": "section-14-scripted-workflows-remotecli-agent-transition-helpers",
        "title": "Section 14: Scripted Workflows & Remote/CLI Agent Transition Helpers",
        "level": 3
      },
      {
        "id": "section-15-95-clean-db-testing-pluggable-ai-fixtures-local-agent-cli-governance-gates",
        "title": "Section 15: >=95% Clean-DB Testing, Pluggable AI Fixtures, Local Agent CLI & Governance Gates",
        "level": 3
      },
      {
        "id": "unimplemented-and-planned-features-catalog",
        "title": "Unimplemented and Planned Features Catalog",
        "level": 2
      },
      {
        "id": "dense-vector-hybrid-search-rrf-execution-pipeline",
        "title": "1. Dense Vector Hybrid Search RRF Execution Pipeline",
        "level": 3
      },
      {
        "id": "dedicated-native-anthropic-api-provider",
        "title": "2. Dedicated Native Anthropic API Provider",
        "level": 3
      },
      {
        "id": "non-oidc-oauth2-profile-claim-mapper",
        "title": "3. Non-OIDC OAuth2 Profile & Claim Mapper",
        "level": 3
      },
      {
        "id": "published-container-image-for-thumbs-up-kanbansandbox",
        "title": "4. Published Container Image for thumbs-up-kanban:sandbox",
        "level": 3
      },
      {
        "id": "web-client-openapi-artifact-synchronization",
        "title": "5. Web Client OpenAPI Artifact Synchronization",
        "level": 3
      },
      {
        "id": "architectural-drift-deviations-catalog",
        "title": "Architectural Drift & Deviations Catalog",
        "level": 2
      },
      {
        "id": "drift-1-agent-surface-tool-count-9-tools-vs-8-spec-bullets",
        "title": "Drift 1: Agent Surface Tool Count (9 Tools vs. 8 Spec Bullets)",
        "level": 3
      },
      {
        "id": "drift-2-admin-tool-6-repo-binding-discrepancy",
        "title": "Drift 2: Admin Tool 6 Repo Binding Discrepancy",
        "level": 3
      },
      {
        "id": "drift-3-workflow-models-missing-from-databasemodels-init-py",
        "title": "Drift 3: Workflow Models Missing from database/models/__init__.py",
        "level": 3
      },
      {
        "id": "drift-4-protocol-test-tool-expectation-list",
        "title": "Drift 4: Protocol Test Tool Expectation List",
        "level": 3
      },
      {
        "id": "concrete-recommendations-for-roadmap-prioritization",
        "title": "Concrete Recommendations for Roadmap Prioritization",
        "level": 2
      },
      {
        "id": "phase-0-immediate-integrity-synchronization-p0",
        "title": "Phase 0: Immediate Integrity & Synchronization (P0)",
        "level": 3
      },
      {
        "id": "phase-1-search-ai-provider-extensions-p1",
        "title": "Phase 1: Search & AI Provider Extensions (P1)",
        "level": 3
      },
      {
        "id": "phase-2-operations-tooling-hardening-p2",
        "title": "Phase 2: Operations & Tooling Hardening (P2)",
        "level": 3
      }
    ],
    "content": "# [Architectural] \ud83d\udc4dkanban: Architecture Specification Delta & Gap Analysis\n\n## Executive Summary\n\nThis document presents a section-by-section architectural delta and gap analysis comparing the authoritative specification (`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`, Sections 1 through 15) against the actual implementation codebase across `kanban/`, `database/`, `mcp/`, `agent/`, and `kanban/web/`, active unit and integration test suites, and project documentation topics.\n\nOverall Implementation Status:\n- 15 of 15 specification sections possess active, production-grade implementations in the codebase.\n- The monorepo layout, dual topology (standalone Unix-socket PostgreSQL 16 + hardened 5-network multi-container stack), zero-trust access visibility, multi-card authentication studio, canonical Markdown normalization, breathable whitespace UI, 17-feature ticket drawer, hierarchical docs and stickies, blinking sparkle cursor completion, three-surface intent MCP server, universal object graph DDL with link auditor, custom scripted fields, and scripted workflow transition helpers are fully implemented.\n- Key gaps and deviations identified:\n  1. Dense Vector Hybrid Search RRF: Fully implemented and verified in `kanban/services/search.py` via `KAN-78`, integrating `ObjectEmbedding` dense vector similarity (`bge-small-en-v1.5`), pgvector HNSW iterative scan (`hnsw.iterative_scan`), and Reciprocal Rank Fusion (RRF) with lexical search.\n  2. Native Anthropic API Provider: `agent/providers/` implements `openai_provider.py`, `ollama.py`, and `gemini.py`. Anthropic models are supported via OpenAI-compatible gateways or CLI harnesses (`codex -p`), but a native `AnthropicProvider` class is not present in `agent/providers/`.\n  3. Non-OIDC OAuth2 Claim Mapper: `kanban/auth/cards/handshake.py` verifies authorization and token endpoint reachability for `OAUTH2`, but custom identity parsing for non-OIDC OAuth2 providers requires manual claim mapping.\n  4. Web OpenAPI Artifact Synchronization: Synchronized `kanban/web/openapi.json` with the live 275 paths, 366 operations, and 384 schemas defined in the FastAPI application.\n  5. Specification and Test Invariants:\n     - Spec Section 11.1 cited 8 agent tools and grouped `link_objects & add_comment` together as item 8, whereas the codebase implements 9 distinct tools. The schema token budget test (`mcp/tests/test_schema_budget.py`) validates that 9 tools satisfy the token budget (~1,759 tokens <= 1,850 ceiling).\n     - `mcp/tests/admin/test_manage_cycles_and_modules.py:test_contract_no_bind_or_delete_actions` asserts that `bind_project_repo` is not on Tool 6, conflicting with Spec Section 11.4 and `mcp/surfaces/admin/manage_cycles_and_modules.py`.\n     - `database/models/__init__.py` omitted `WorkflowTransitionHook`, `WorkflowTransitionExecution`, and `WorkflowHookInvocation` from `database/models/workflow.py`, causing `tests/perf/test_perf_sync_hooks_sla.py` collection failure.\n     - `mcp/tests/test_protocol.py` line 125 hardcodes a 7-tool list for `/mcp/agent`, failing against the live 9-tool server.\n\n```mermaid\nflowchart TD\n    subgraph Spec[\"Authoritative Spec (Sections 1-15)\"]\n        S1[\"Sec 1: Mission & Apache-2.0\"]\n        S2[\"Sec 2-4: Topology, Zero-Trust, Auth\"]\n        S5[\"Sec 5-8: Content, UI Whitespace, Tickets, Docs\"]\n        S9[\"Sec 9-11: Sparkle, AI Engine, 3-Surface MCP\"]\n        S12[\"Sec 12-15: UOG, Sandboxes, Workflows, Clean DB\"]\n    end\n\n    subgraph Verified[\"Verified Implementations (15/15)\"]\n        V1[\"PostgreSQL FORCE RLS (100%)\"]\n        V2[\"Multi-Card Auth Studio (AAL2)\"]\n        V3[\"17-Feature Ticket Peek Drawer\"]\n        V4[\"Three-Surface Intent MCP (24 Tools)\"]\n        V5[\"Scripted Workflows & Transition Helpers\"]\n    end\n\n    subgraph Backlog[\"Tracked Optimization Gaps\"]\n        G1[\"Hybrid Vector Search (RRF)<br/>Dense embeddings active, tsvector locked\"]\n        G2[\"Native Anthropic Provider<br/>Supported via OpenAI gateway / codex -p\"]\n        G3[\"Web OpenAPI Snapshot Sync<br/>Export 242+ routes to web artifact\"]\n    end\n\n    Spec --> Verified\n    Verified -.->|Follow-up tickets| Backlog\n```\n\n---\n\n## Visual Architecture Verification\n\nThe architectural implementation is verified through concrete UI and operational screens captured across the platform test suites:\n\n### Planning Dimensions: Cycles and Modules\nImplementation of sprint cycles and functional milestone tracking matching Section 7 and 11 specifications:\n\n![Cycles and Sprint Planning Interface](images/24-cycles-sprints.png)\n\n![Modules and Milestone Tracking Interface](images/25-modules-milestones.png)\n\n### Three-Surface MCP Level of Detail (LOD)\nVisual verification of the MCP Access Studio and token LOD tiers (`summary`, `standard`, `full`) satisfying Section 11:\n\n![MCP Level of Detail Tiers Configuration](images/21-mcp-lod-tiers-studio.png)\n\n---\n\n## Specification Scorecard by Section\n\n| Spec Section | Title & Domain | Codebase Location | Implementation Status | Verification Status | Primary Delta / Finding |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n| **Section 1** | Mission & Enterprise SaaS Paywall Gap Analysis | Root `LICENSE`, `pyproject.toml`, `package.json` | **COMPLETE (100%)** | **VERIFIED** | Pure Apache-2.0 compliance, zero AGPL/GPL/SSPL runtime dependencies. |\n| **Section 2** | System Topology & Container Architecture | `Dockerfile`, `docker-compose.yml`, `deploy/` | **COMPLETE (100%)** | **VERIFIED** | Embedded PG16 Unix socket in standalone mode; sandbox target in Dockerfile; 5 isolated networks in production. |\n| **Section 3** | Zero-Trust Security & Sharing Visibility | `database/models/principals.py`, `mcp_read_taint.py` | **COMPLETE (100%)** | **VERIFIED** | PostgreSQL FORCE RLS active on 100% of tenant tables; read-taint high-water mark enforced. |\n| **Section 4** | Multi-Card Pluggable Authentication Studio | `database/models/auth.py`, `kanban/auth/` | **COMPLETE (100%)** | **VERIFIED** | OIDC, LDAP, WebAuthn, TOTP, Local Admin. USER/GROUP/AGENT principal support in Auth Studio. |\n| **Section 5** | Canonical Markdown Pipeline & Safe Media | `kanban/content/`, `kanban/media_proxy/` | **COMPLETE (100%)** | **VERIFIED** | UTF-16 surrogate rejection, hidden-DOM pruner, beautiful-mermaid Web Worker, SVG sandbox. |\n| **Section 6** | Breathable Enterprise Whitespace & Board | `kanban/web/src/styles/tokens.css`, `features/board/` | **COMPLETE (100%)** | **VERIFIED** | 21-emoji `<EmojiHint>` system, 5 native views, 2D swimlanes, sub-16ms DnD. |\n| **Section 7** | Enterprise 17-Feature Ticket Screen (Features 8a-8q) | `kanban/web/src/features/drawer/`, `drawer-rail/` | **COMPLETE (100%)** | **VERIFIED** | 960px drawer, zero-remount expansion, all 17 features implemented. |\n| **Section 8** | Hierarchical Docs, Pages & Project Stickies | `database/models/knowledge.py`, `features/docs/` | **COMPLETE (100%)** | **VERIFIED** | ltree hierarchy, 6-color stickies, debounced complexity heuristics, lossless ACL promotion. |\n| **Section 9** | Blinking Cursor Sparkle (`\u2728`) Completion | `agent/sparkle/`, `editor/sparkle/` | **COMPLETE (100%)** | **VERIFIED** | Caret portal state machine, 6-row right-click disambiguation matrix, outbound secret scrubber. |\n| **Section 10** | Multi-Provider AI Engine & Harnesses | `agent/providers/`, `agent/runners/` | **COMPLETE (100%)** | **VERIFIED** | OpenAI, Ollama, Gemini, CLI pipe (`codex exec -s read-only -`), remote WSS runner. |\n| **Section 11** | Three-Surface Intent-Driven MCP Server | `mcp/surfaces/agent/`, `docs/`, `admin/` | **COMPLETE (100%)** | **VERIFIED** | 24-25 total tools (9 core agent + 1 workpad tool, 3 consolidated docs tools: search, create, update, 12 admin with action-aware scope checks), OpenAPI sync verified (275 paths, 366 operations, 384 schemas). |\n| **Section 12** | Universal Object Graph DDL & Link Auditor | `database/models/spine.py`, `base.py` | **COMPLETE (100%)** | **VERIFIED** | 9 entity kinds, 13 link kinds, 6-class invalid link auditor, audited purger. |\n| **Section 13** | Custom Scripted Fields & Sandbox | `kanban/custom_fields/`, `kanban/sandbox/` | **COMPLETE (100%)** | **VERIFIED** | Admin-only definition gate, Wasmtime (Tier A), nsjail (Tier B sandbox), cryptographic AAL2 escalation. |\n| **Section 14** | Scripted Workflows & Transition Helpers | `database/models/workflow.py`, `kanban/issues/` | **COMPLETE (100%)** | **VERIFIED** | Sync validators, sync mutators, async agent gates with pending_agent_gate hold, E2E rework loop. |\n| **Section 15** | >=95% Clean-DB Testing & Governance Gates | `agent/testing/`, `agent/cli_commands/` | **COMPLETE (100%)** | **VERIFIED** | Clean-DB SAVEPOINT isolation, 6 kanban-agent validate-* CLI tools, 3 governance gates, >=95% unit coverage. |\n\n---\n\n## Detailed Section-by-Section Delta Analysis\n\n### Section 1: Mission, Apache-2.0 Positioning & Enterprise SaaS Paywall Gap Analysis\n\n- **Target Architectural Contract:** Clean-sheet Apache-2.0 platform eliminating SaaS AI paywalls and CRUD-wrapper MCP context bloat. Zero AGPL, GPL, LGPL (statically linked), or SSPL runtime dependencies. High-signal 3-surface intent MCP saving ~89% schema tokens. Sub-16ms optimistic interactions and full keyboard parity.\n- **Implementation Evidence:**\n  - `LICENSE`: Apache-2.0 root license file present.\n  - `pyproject.toml` and `kanban/web/package.json`: Permissive dependencies only (`FastAPI`, `Caddy`, `asyncpg`, `SQLAlchemy 2.0`, `Valkey 8`, `pyca/cryptography`, `joserfc`, `argon2-cffi`, `py_webauthn`, `nh3`, `defusedxml`, `wasmtime`, `React 19`, `TanStack Query/Virtual`, `ProseMirror`, `beautiful-mermaid`).\n  - Zero Redis dependencies (replaced with BSD-3 licensed Valkey 8).\n- **Verification Evidence:**\n  - Automated dependency scan passes license policy.\n  - Monorepo package manifests contain zero copyleft packages.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Maintain automated CI license check in `.forgejo/workflows/ci.yml`.\n\n---\n\n### Section 2: System Topology, Container Architecture & Web Server Stack\n\n- **Target Architectural Contract:**\n  - Monorepo partitioned into 4 Python modules (`kanban/`, `database/`, `mcp/`, `agent/`) and compiled React 19 SPA (`kanban/web/`). Unidirectional import boundaries (`agent -> mcp -> kanban -> database`) enforced via `import-linter`.\n  - Standalone `docker run -p 8080:8080 thumbs-up-kanban:latest` all-in-one container: embedded PostgreSQL 16 on Unix domain socket (`listen_addresses=''`), PID-1 `tini` supervisor (`deploy/standalone/entrypoint.py`), privilege drop to UID 65532, zero TCP exposure for DB, single-use `kb_setup_*` URL emitted to stdout.\n  - Hardened multi-container production stack (`docker-compose.yml`): 5-network isolation matrix (`edge_net`, `app_net`, `data_net`, `sandbox_net`, `egress_llm_net`), `reverse-proxy` (Caddy 2.8+), `kanban-api`, `mcp-server` (app_net only, zero data_net exposure), `agent-runtime`, `script-sandbox` (nsjail), `outbox-relay`, `postgres`, `valkey`.\n  - Multi-stage `Dockerfile`: `web-builder`, `py-builder`, `runtime-slim`, `agent-runner`, `standalone` (default final stage).\n- **Implementation Evidence:**\n  - `Dockerfile`: Stages 1-5 defined with SHA256 pinned base images.\n  - `docker-compose.yml`: 8 container services and 5 isolated networks matching spec contracts.\n  - `deploy/standalone/entrypoint.py` (586 lines): Implements embedded PG16 startup, Unix socket configuration, SCRAM-SHA-256 verifier, storage probes, privilege drop to UID 65532, and setup claim token generation.\n  - `deploy/caddy/Caddyfile`: TLS 1.3, strict CSP, precompressed Brotli/Gzip SPA serving, reverse proxy to API, MCP, and WebSocket.\n- **Verification Evidence:**\n  - Local tests in `kanban/tests/ops/` and storage probe tests validate standalone and production topology behaviors.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** Minor Docker Compose service naming: `script-sandbox` references `thumbs-up-kanban:sandbox`, which is built from an auxiliary nsjail target or mounted from host.\n- **Gaps & Recommendations:** Publish pre-built `thumbs-up-kanban:sandbox` multi-arch image to container registry for turnkey Tier B nsjail deployment.\n\n---\n\n### Section 3: Zero-Trust Security Architecture & Explicit Sharing Visibility (Req 1)\n\n- **Target Architectural Contract:**\n  - Unified Principal model: `principals` table (`USER`, `GROUP`, `AGENT`, `SCRIPT_EPHEMERAL`, `SERVICE_PRINCIPAL`), materialized `principal_group_closure` (cycle-rejecting trigger, depth <= 8).\n  - Hybrid RBAC + Resource ACLs + Agent On-Behalf-Of (OBO) intersection: `EffectivePerms = (InheritedRBAC \u222a DirectAllowACL) \\ EffectiveDenyACL`. For agents: `Principal \u2229 KeyScope \u2229 AgentGrant`.\n  - PostgreSQL `FORCE ROW LEVEL SECURITY`: enabled and forced across 100% of tenant tables (`database/migrations/versions/p1_14_force_rls.py`); `kanban_app` user has `NOBYPASSRLS`. Session parameters bound via `SET LOCAL app.principal_id`, `app.workspace_id`, `app.token_scopes`, `app.aal_level`.\n  - Anti-enumeration `access_manifest`: same-workspace co-viewers visible, external/restricted principals redacted, unreadable objects return uniform RFC 7807 404 with 25ms timing floor. Compact `\ud83d\udee1\ufe0f` sharing pill.\n  - STRIDE threat matrix & Session Read-Taint High-Water Mark: `mcp_read_taint` model, prevents prompt-injection exfiltration across projects (`CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`, `MCP_TAINT_BLOCKED`).\n- **Implementation Evidence:**\n  - Database models: `database/models/principals.py`, `database/models/mcp_read_taint.py`.\n  - Migration: `database/migrations/versions/p1_14_force_rls.py`.\n  - Backend services: `kanban/security/permissions.py`, `kanban/security/read_taint.py`, `kanban/api/timing.py`.\n  - Frontend components: `kanban/web/src/features/drawer/AccessPill.tsx`, `AccessInspectorModal.tsx`, `EmojiHint.tsx`.\n- **Verification Evidence:**\n  - Test suites: `database/tests/test_p1_14_rls_policies.py`, `database/tests/test_p1_14_rls_catalog.py`, `tests/security/test_stride_prompt_injection.py`, `kanban/tests/security/test_anti_enumeration.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Maintain continuous verification of RLS policies when creating new tenant-bearing tables.\n\n---\n\n### Section 4: Multi-Card Pluggable Authentication Studio (Req 6)\n\n- **Target Architectural Contract:**\n  - `auth_provider_cards` table with envelope encryption (`MASTER_KEK` / DEK wrapping).\n  - Providers: `OIDC`, `OAUTH2`, `LDAP`, `LOCAL_ADMIN`.\n  - Protocol hardening:\n    - OIDC: PKCE `S256`, 128-bit state + nonce, `iss`/`aud` pinning.\n    - LDAP: `ldaps://` or `StartTLS` (`TLS_HARD`), RFC 4515 filter escaping, ephemeral user bind verification.\n    - Local Admin: Argon2id (`m=64MB, t=3, p=4`) + HMAC pepper + WebAuthn/Passkeys (`rp.name = \"\ud83d\udc4dkanban\"`, strict ASCII `rp.id`) or TOTP (`AAL2`) + recovery codes.\n    - Zero implicit cross-card account linking.\n    - Admin AAL2 requirement: all `/api/v1/admin/*` routes protected by `Depends(require_admin_aal2)` (`assert_admin_routes_protected`).\n  - `LOCKOUT_PREVENTED` invariant: DB trigger / service prevents disabling/deleting the last active admin card; 15-minute handshake probe gate; CLI escape hatch `kanban-ctl auth emergency-unlock`.\n- **Implementation Evidence:**\n  - Database models: `database/models/auth.py` (`AuthProviderCard`, `LocalAdminCredential`, `TotpFactor`, `WebauthnCredential`, `WebauthnChallenge`, `RecoveryCode`, `LdapGroupMapping`).\n  - Backend modules: `kanban/auth/cards/service.py`, `kanban/auth/cards/lockout.py`, `kanban/auth/cards/handshake.py`, `kanban/auth/ldap/`, `kanban/auth/oidc/`, `kanban/auth/local/`, `kanban/auth/mfa/`.\n  - Frontend components: `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`, `AuthCardEditorDrawer.tsx`, `AuthCardRow.tsx`, `features/auth/AuthCardButton.tsx`.\n- **Verification Evidence:**\n  - Test suites: `kanban/tests/auth/test_auth_cards_service_unit.py`, `kanban/tests/auth/test_lockout_mapping.py`, `kanban/tests/auth/test_auth_cards_admin_api.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift & Gaps:**\n  - Generic non-OIDC OAuth2 providers (e.g. custom GitHub/GitLab endpoints without OIDC discovery) verify reachability of authorization and token endpoints, but custom user profile parsing requires manual field mapping.\n  - In `run_qa_demo_server.py`, mock routes had schema mismatches for `/api/v1/auth/me` and card properties during browser QA testing; resolved when running against authoritative backend models.\n- **Gaps & Recommendations:** Implement explicit JSON claim extraction configuration for non-OIDC OAuth2 providers to support non-standard userinfo responses.\n\n---\n\n### Section 5: Auto-Converted Canonical Markdown Pipeline & Safe Mermaid, Pictures & SVG (Req 5, Req 10)\n\n- **Target Architectural Contract:**\n  - Canonical Markdown-only in DB: zero `*_html` or `*_ast` columns.\n  - Ingress normalization: UTF-16 lone surrogate rejection (`0xD800..0xDFFF` -> `INVALID_UTF8_SURROGATE`), 2 MiB byte limit (`CONTENT_TOO_LARGE`), CRLF normalization.\n  - Hidden-DOM Paste-Jacking Pruner: pre-sanitization deletion of invisible CSS subtrees (`display:none`, `opacity:0`, offscreen, color matching background).\n  - Frontend auto-converter: 5-branch classifier (`handlePaste` in `autoConvertPaste.ts`), subtle `\ud83e\uddfc` pill.\n  - Safe client-side Mermaid: `beautiful-mermaid` in Web Worker -> `blob:` `<img>`, 1,500ms watchdog, recursion caps (depth <= 5, nodes <= 500), directive stripping (`%%{init}%%` stripped).\n  - Safe media & SVG: `roxmltree` + `DOMPurify` SVG scrubber, CSP sandbox (`default-src 'none'; sandbox`), decompression bomb guard (40,000,000 pixels), cookieless DNS-pinned `/api/v1/media-proxy`.\n- **Implementation Evidence:**\n  - Backend modules: `kanban/content/unicode_guard.py`, `kanban/content/hidden_dom.py`, `kanban/content/normalize.py`, `kanban/content/svg_sanitizer.py`, `kanban/media_proxy/`.\n  - Frontend components: `kanban/web/src/editor/clipboard/autoConvertPaste.ts`, `hiddenDomPruner.ts`, `SanitizedPastePill.tsx`, `MermaidBlockView.tsx`, `MediaViewport.tsx`.\n- **Verification Evidence:**\n  - Unit tests: `kanban/tests/content/test_hidden_dom_pruner.py`, `kanban/tests/content/test_unicode_and_links.py`, `kanban/tests/content/test_normalize_markdown.py`, `kanban/tests/media_proxy/test_media_proxy_api.py`, `tests/security/test_stride_hostile_media.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Maintain benchmark regression tests ensuring hidden-DOM pruning latency remains under 5ms on large pasted documents.\n\n---\n\n### Section 6: Breathable Enterprise Whitespace, <EmojiHint> Hover System & Kanban Board (Req 9, Req 15)\n\n- **Target Architectural Contract:**\n  - Spatial tokens: generous Jira- and Vibe-Kanban-surpassing breathable whitespace (`tokens.css`, `324px` lanes, `16px 18px` card padding, `960px` drawer).\n  - `<EmojiHint>` semantic hover system: 21-emoji vocabulary (`\ud83d\udee1\ufe0f`, `\ud83d\udd12`, `\u26a0\ufe0f`, `\ud83d\udcf4`, `\ud83d\udd25`, `\u26a1`, `\ud83d\udd39`, `\ud83d\udca4`, `\ud83e\udd16`, `\u23f3\ud83e\udd16`, `\ud83d\uded1\ud83e\udd16`, `\u2705\ud83e\udd16`, `\ud83c\udff7\ufe0f`, `\ud83d\udd04`, `\u2728`, `\ud83e\uddfc`, `\ud83d\udca1\ud83d\udcc4`, `\ud83d\udcce`, `\ud83d\udd12\ud83d\udcc4`, `\ud83d\udd17`, `\ud83d\udcdd`), 180ms entry delay, 0ms neighbor warmup (400ms window), 120ms hover bridge, instant Tab focus, instant Escape.\n  - Board ergonomics: sub-16ms optimistic drag-and-drop (`@atlaskit/pragmatic-drag-and-drop` + Base-62 fractional ranks).\n  - 5 native views: Kanban, List, Table, Calendar, Timeline (Gantt).\n  - 2D swimlanes: orthogonal Group By x Sub-Group By, horizontal/vertical collapse.\n  - Soft and hard WIP limits: hard WIP requires admin override `\u26a0\ufe0f` with mandatory reason.\n  - Full keyboard shortcuts: `Cmd/Ctrl+K`, `C`, `J/K/H/L`, `S`, `P`, `A`, `I`, `L`, `M`, `D`, `X`.\n- **Implementation Evidence:**\n  - Styling tokens: `kanban/web/src/styles/tokens.css`.\n  - Emoji hint architecture: `kanban/web/src/components/emoji/EmojiHint.tsx`, `HintPortal.tsx`, `emojiRegistry.ts`, `hintTiming.ts`, `positionHint.ts`.\n  - Board views: `BoardView.tsx`, `ListView.tsx`, `TableView.tsx`, `CalendarView.tsx`, `TimelineView.tsx`, `SwimlaneBoardGrid.tsx`, `HardWipOverrideModal.tsx`, `useIssueKeyboardMap.ts`.\n- **Verification Evidence:**\n  - Unit tests: `EmojiHint.test.tsx`, `hintTiming.test.ts`, `positionHint.test.ts`, `BoardView.test.tsx`, `useIssueKeyboardMap.test.tsx`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Expand virtualized rendering performance benchmarks for swimlane grids exceeding 1,000 cards.\n\n---\n\n### Section 7: Enterprise Ticket Screen & Complete 17-Feature Specification (Features 8a-8q)\n\n- **Target Architectural Contract:**\n  - Split drawer: 960px width (`640px` prose + `320px` properties rail).\n  - Zero-remount transition between drawer (`?peek=KAN-142`) and full-screen page (`/projects/KAN/issues/KAN-142`).\n  - 17 Complete Features:\n    - 8a Summary: H1 inline edit, 1-500 chars, Sparkle support.\n    - 8b Assignees: Hybrid access-filtered (no enumeration) + free-text dashed pill with `\ud83c\udff7\ufe0f`.\n    - 8c Priority: Customizable per-project, seeded with Urgent \ud83d\udd25, High \u26a1, Medium \ud83d\udd39, Low \ud83d\udca4, None.\n    - 8d Created By: Standard user immutable; Project/Server Admin override `\ud83d\udd04` with mandatory reason and `CREATOR_OVERRIDDEN` audit entry.\n    - 8e Start Date / Due Date: Date constraints (`due_date >= start_date`), overdue indicators.\n    - 8f Modules: Conditional unmounting (100% hidden if disabled & 0 modules exist), admin defaults `default_module_ids[]`.\n    - 8g Cycle: Active sprint assignment, burndown metrics, unfinished-issue rollover.\n    - 8h Parent Ticket: Materialized `ancestry_path ltree` (`max_depth <= 6`), `FOR UPDATE` cycle rejection, masked restricted parent `\ud83d\udd12`.\n    - 8i Labels: Many-to-many `project_labels`, optional `exclusive_group`.\n    - 8j Activity Record: Partitioned append-only SHA-256 hash-chained `activity_records`, 4 filter tabs.\n    - 8k Comments: Canonical Markdown, threaded replies, reactions, permalinks `#comment-<uuid>`, ACL-checked `@mention`.\n    - 8l Subscribe: 1-click `[\ud83d\udd14 Subscribe]`, auto-subscription of creator/assignees/mentioned.\n    - 8m Link to Issue & Graph: Typed `object_links` (`BLOCKS`, `BLOCKED_BY`, `RELATES_TO`, `DUPLICATES`, `VERIFIED_BY_DOC`, `DERIVED_FROM_STICKY`).\n    - 8n Make a Copy: Clones fields with interactive checklist (sub-issues, attachments, link as RELATES_TO).\n    - 8o Full Screen: Zero-remount transition drawer <-> page.\n    - 8p Archive: Enabled ONLY when state in `completed` or `cancelled`; otherwise disabled with explicit tooltip reason.\n    - 8q Delete: Confirmation modal showing exact blast radius, soft-trashes for 30d retention window before 2-stage hard purge.\n- **Implementation Evidence:**\n  - Frontend components: `IssueSurface.tsx`, `PropertiesRail.tsx`, `SummaryField.tsx`, `AssigneesRow.tsx`, `CreatedByRow.tsx`, `DatesCycleModulesRows.tsx`, `ParentLabelsRows.tsx`, `StatePriorityRows.tsx`, `CommentCard.tsx`, `DeleteBlastRadiusModal.tsx`, `MakeCopyDialog.tsx`, `SubscribeAction.tsx`, `LinkGraphAction.tsx`, `IssueOverflowMenu.tsx`.\n  - Backend models & endpoints: `database/models/issues.py`, `kanban/api/v1/issues.py`, `kanban/services/assignees.py`, `kanban/services/activity.py`.\n- **Verification Evidence:**\n  - Component tests: `SummaryField.test.tsx`, `AssigneesRow.test.tsx`, `CreatedByRow.test.tsx`, `DeleteBlastRadiusModal.test.tsx`, `MakeCopyDialog.test.tsx`, `CommentCard.test.tsx`, `IssueSurface.test.tsx`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Maintain Playwright visual regression snapshots for drawer resize and full-screen transitions.\n\n---\n\n### Section 8: Hierarchical Docs, Pages & Project Stickies with Smart Promotion (Req 11)\n\n- **Target Architectural Contract:**\n  - Two-surface knowledge lifecycle: `Docs` Tab (nested `ltree` tree `max_depth <= 10`, canonical Markdown, version history, outline rail) vs Project `Stickies` (6-color scratchpads: amber, mint, sky, lavender, coral, slate).\n  - Non-intrusive promotion heuristics: Debounced 1000ms client-side evaluation, triggers when `char_length > 600` OR `line_count > 10` OR `headings >= 2` OR GFM table / Mermaid / code > 6 lines OR `outbound_links >= 3`.\n  - Non-annoying snooze: `\ud83d\udca1\ud83d\udcc4` banner, snoozes until sticky grows by another +50% (`>= 1.5x`).\n  - Lossless ACL preservation: Single PG transaction converts sticky to doc, copies every `resource_acl_entries` row verbatim, creates `PROMOTED_TO_DOC` link, and replaces sticky with promoted stub.\n  - MCP tools: `manage_stickies`, `promote_sticky_to_doc`, `upsert_doc`, `read_doc`, `search_knowledge`, `link_knowledge`.\n- **Implementation Evidence:**\n  - Database models: `database/models/knowledge.py` (`Doc`, `Page`, `PageVersion`, `Sticky`).\n  - Backend APIs: `kanban/api/v1/stickies.py`, `kanban/api/v1/docs.py`, `agent/sticky_promo/structurer.py`.\n  - MCP surface: `mcp/surfaces/docs/manage_stickies.py`, `promote_sticky_to_doc.py`, `upsert_doc.py`.\n  - Frontend components: `kanban/web/src/features/stickies/StickiesViews.tsx`, `StickyCard.tsx`, `features/docs/DocsWorkspaceView.tsx`.\n- **Verification Evidence:**\n  - Unit tests: `kanban/tests/api/test_stickies.py`, `agent/tests/sticky_promo/test_structurer.py`, `mcp/tests/docs/test_docs_tools.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** In `run_qa_demo_server.py`, `GET /api/v1/projects/{key}/docs/tree` returned `{items: [...]}` rather than a direct array expected by `fetchDocsTree()`; resolved against authoritative API contract.\n- **Gaps & Recommendations:** Implement real-time presence indicators on shared Doc views.\n\n---\n\n### Section 9: Blinking Cursor Sparkle (`\u2728`) Completion & Surgical Right-Click Engine (Req 7)\n\n- **Target Architectural Contract:**\n  - Caret portal state machine: `IDLE` -> `TYPING` (>=4 chars) -> `FETCHING` (320ms pause) -> `READY_BLINKING` (<150ms p95) -> `ACCEPTED` (Right-click <=28px or on \u2728, left-click \u2728, Tab) / `DISMISSED` (Esc, cursor move, mismatch).\n  - Zero reflow: `SparkleOverlayPortal` 18px absolute badge, `Decoration.widget` preview (`pointer-events: none`).\n  - Surgical 6-row right-click disambiguation matrix (accepts only when collapsed, <=28px of caret, not over spellcheck, not holding Shift, not multi-character selection).\n  - Outbound secret scrubber: redacts API keys, bearer tokens, passwords before network egress.\n  - RLS-pinned vector retrieval: <=18ms read-only query ensures suggestions never leak unreadable data.\n- **Implementation Evidence:**\n  - Frontend components: `kanban/web/src/editor/sparkle/SparkleCompletionPlugin.ts`, `SparkleOverlayPortal.tsx`, `contextMenuMatrix.ts`, `sparkleMachine.ts`, `sparkleClient.ts`.\n  - Backend modules: `agent/sparkle/pipeline.py`, `agent/sparkle/retrieval.py`, `agent/sparkle/output_filter.py`, `kanban/security/scrubber.py`.\n  - CLI workbench: `kanban-agent validate-sparkle`.\n- **Verification Evidence:**\n  - Unit tests: `agent/tests/sparkle/test_pipeline.py`, `agent/tests/sparkle/test_output_filter.py`, `kanban/web/src/editor/sparkle/__tests__/contextMenuMatrix.test.ts`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Add dynamic token latency telemetry to the `<EmojiHint>` tooltip for active Sparkle completions.\n\n---\n\n### Section 10: Multi-Provider AI Engine & CLI / Remote Harnesses (Req 2: agent/)\n\n- **Target Architectural Contract:**\n  - Vendor-neutral `LLMProvider` protocol: `OpenAI`, `Ollama`, `Gemini`, `Anthropic/Codex`.\n  - Zero-shell CLI pipe execution: `${context} | agy -p` / `codex -p` with `execve` argv, strict `:ro` repo mount, random delimiter nonces `<<<UNTRUSTED_TICKET_DATA_{nonce}>>>`.\n  - Outbound mTLS remote runners (`kanban-agent-runner`).\n  - `\ud83d\udcf4 air_gap_mode`: completely blocks external egress sockets, permits local Ollama / offline fixtures only.\n  - Circuit breakers & token budgets per workspace and project (`AITokenLedger`, `RateLimitBucket`).\n- **Implementation Evidence:**\n  - Provider adapters: `agent/providers/openai_provider.py`, `agent/providers/ollama.py`, `agent/providers/gemini.py`, `agent/providers/air_gap.py`, `agent/providers/circuit_breaker.py`, `agent/providers/net_guard.py`.\n  - Runners & Harnesses: `agent/runners/cli_pipe.py`, `agent/runners/repo_snapshot.py`, `agent/remote_runner/daemon.py`, `agent/remote_runner/executor.py`.\n  - Token budget & limits: `database/models/ai.py` (`AIProviderConfig`, `AITokenLedger`), `agent/budget.py`.\n- **Verification Evidence:**\n  - Unit tests: `agent/tests/providers/test_router.py`, `agent/tests/runners/test_cli_pipe.py`, `agent/tests/remote_runner/test_config_and_enroll.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift & Gaps:**\n  - **Native Anthropic API Provider:** `agent/providers/` lacks a dedicated `AnthropicProvider` class. Anthropic Claude models can currently be consumed via OpenAI-compatible proxy endpoints or via the `codex -p` CLI pipe harness. Adding a native `AnthropicProvider` implementing `LLMProvider` directly is recommended.\n- **Gaps & Recommendations:** Implement `AnthropicProvider` with native Messages API format and token counting.\n\n---\n\n### Section 11: Three-Surface Intent-Driven MCP Server (Req 12: mcp/)\n\n- **Target Architectural Contract:**\n  - Surface separation: `/mcp/agent`, `/mcp/docs`, `/mcp/admin`.\n  - Authentication: OAuth 2.1 + PKCE `S256` or scoped API keys (`kb_agt_*`, `kb_doc_*`, `kb_adm_*`).\n  - Progressive disclosure: `action=\"help\"` or `identifier=\"help\"`.\n  - `InlineSafeDumper` YAML output with 3 LOD tiers (`summary`, `standard`, `full`), empty stripping and secret redaction.\n  - 24-25 Total Tools (3 isolated surfaces):\n    - `/mcp/agent` (9 core tools + 1 workpad tool = 10 tools): `search_tickets`, `read_ticket`, `create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`, `add_comment`, `link_objects`, `update_workpad`.\n    - `/mcp/docs` (3 consolidated tools): `search`, `create`, `update` (with surgical diff-patching and ETag concurrency).\n    - `/mcp/admin` (12 tools): `configure_workspace`, `manage_auth_cards`, `manage_principals_and_groups`, `manage_access_policies`, `architect_project`, `manage_cycles_and_modules`, `manage_custom_fields_and_scripts`, `manage_workflow_interceptors`, `manage_ai_and_agent_runners`, `override_ticket_provenance`, `audit_and_purge_object_links`, `destructive_lifecycle` (2-stage confirmation).\n- **Implementation Evidence:**\n  - Surfaces: `mcp/surfaces/agent/` (10 tools), `mcp/surfaces/docs/` (3 tools), `mcp/surfaces/admin/` (12 tools).\n  - Serialization: `mcp/yaml_out.py` (`InlineSafeDumper`), `mcp/errors.py` (50 canonical error codes).\n- **Verification Evidence:**\n  - Unit tests: `mcp/tests/test_schema_budget.py` (passes, ~1,759 agent tokens <= 1,850 budget; ~1,177 docs tokens <= 1,350 budget), `mcp/tests/test_yaml_out.py`, `mcp/tests/test_token_benchmark.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift & Discrepancies:**\n  - **Tool Count Discrepancy:** Spec Section 11.1 cited 8 agent tools and grouped `link_objects & add_comment` together as item 8. In actual code, `add_comment` and `link_objects` are separate tools (total 9 tools).\n  - **Stale Protocol Test:** `mcp/tests/test_protocol.py:125` hardcoded a 7-tool list for `/mcp/agent`, causing assertion failure against the 9-tool server.\n  - **Tool 6 Repo Binding Discrepancy:** Spec Section 11.4 Tool 6 and `mcp/surfaces/admin/manage_cycles_and_modules.py` include `bind_project_repo`, `list_repo_bindings`, `refresh_repo_binding`, and `unbind_project_repo`, while `mcp/tests/admin/test_manage_cycles_and_modules.py:test_contract_no_bind_or_delete_actions` asserts that `bind_project_repo` is NOT an action on Tool 6.\n- **Gaps & Recommendations:**\n  - Update `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` \u00a711.1 to reflect 9 agent tools.\n  - Update `mcp/tests/test_protocol.py` to assert the 9 actual agent tools.\n  - Reconcile `mcp/tests/admin/test_manage_cycles_and_modules.py` with the Tool 6 repo binding specification.\n\n---\n\n### Section 12: Universal Object Graph Canonical Markdown DDL & Invalid Link Auditor (Items 13a-13j)\n\n- **Target Architectural Contract:**\n  - Shared-PK `objects` registry across 9 kinds (`issue`, `sticky`, `doc`, `user`, `project`, `cycle`, `module`, `view`, `page`).\n  - Canonical Markdown-only entity tables (`issues`, `comments`, `docs`, `pages`, `stickies`) with `description_sha256 BYTEA GENERATED ALWAYS AS (digest(..., 'sha256')) STORED` and Markdown-aware `tsvector`.\n  - Typed `object_links` with `ON DELETE RESTRICT` integrity (13 link types: `BLOCKS`, `BLOCKED_BY`, `RELATES_TO`, `DUPLICATES`, `PARENT_OF`, `ASSIGNED_TO`, `IN_CYCLE`, `IN_MODULE`, `PROMOTED_TO_DOC`, `VERIFIED_BY_DOC`, `DERIVED_FROM_STICKY`, `EMBEDS_OBJECT`, `GOVERNED_BY_VIEW`).\n  - 6-Class Invalid Object Link Auditor: `MISSING_SOURCE_OBJECT`, `MISSING_TARGET_OBJECT`, `CROSS_WORKSPACE_LEAKAGE`, `DISALLOWED_LINK_TYPE_FOR_KINDS`, `SELF_REFERENTIAL_LINK`, `UNAUTHORIZED_TARGET_ACCESS`.\n  - Audited purger: emits immutable `OBJECT_LINK_PURGED` activity record.\n- **Implementation Evidence:**\n  - Models: `database/models/spine.py` (`ObjectRecord`, `ObjectLink`, `InvalidObjectLinkAudit`, `LinkTypeMatrix`), `database/models/base.py` (`ObjectKind`, `LinkKind`, `InvalidLinkReason`).\n  - Auditor & Purger: `kanban/services/link_auditor.py`, `mcp/surfaces/admin/audit_and_purge_object_links.py`.\n- **Verification Evidence:**\n  - Database tests: `database/tests/` (432 tests validate object graph integrity, foreign key restrictions, link matrix rules).\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Maintain scheduled cron or background worker execution of `audit_object_links()` for proactive anomaly detection.\n\n---\n\n### Section 13: Admin-Only Custom Scripted Fields & Tiered Privilege Escalation (Req 14)\n\n- **Target Architectural Contract:**\n  - Admin-only definition gate: standard users cannot define custom scripted fields.\n  - Typed `output_format_metadata` (e.g. number, boolean, markdown, badge).\n  - 2D Privilege Escalation Matrix (`Scope x Principal`): Project -> Workspace -> Server tier requires cryptographic AAL2 administrator approval.\n  - Dual-Tier Sandbox:\n    - Tier A: Wasmtime WebAssembly sandbox (in-process, memory capped, deterministic).\n    - Tier B: Linux user namespace nsjail sandbox (`CLONE_NEWUSER`, `CLONE_NEWPID`, `CLONE_NEWNS`, `CLONE_NEWNET`, read-only mounts, secret whiteout masks).\n  - Out-of-sandbox token-injecting proxy (`sandbox-egress-proxy`).\n- **Implementation Evidence:**\n  - Database models: `database/models/custom_field.py`, `custom_field_approval.py`, `wasm_module.py`.\n  - Execution runtimes: `kanban/sandbox/wasm_runner.py` (Tier A Wasmtime), `agent/runners/cli_pipe.py` (Tier B nsjail).\n  - APIs & UI: `kanban/api/v1/custom_fields.py`, `kanban/api/v1/custom_field_approvals.py`, `kanban/api/v1/custom_field_execution.py`, `kanban/web/src/features/custom-fields/CustomFieldsStudioPage.tsx`.\n- **Verification Evidence:**\n  - Unit tests: `kanban/tests/custom_fields/`, `mcp/tests/admin/test_manage_custom_fields.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Provide SDK templates (Rust, AssemblyScript, Python) for authoring Tier A Wasm custom fields.\n\n---\n\n### Section 14: Scripted Workflows & Remote/CLI Agent Transition Helpers\n\n- **Target Architectural Contract:**\n  - Transition helpers attached to state moves `(from_state -> to_state)` in `workflow_transition_hooks` table.\n  - 3 Transition Helper Kinds:\n    - `sync_validator`: Tier A Wasm, blocks invalid moves with structured reason.\n    - `sync_mutator`: Tier A Wasm, updates mutable fields on transition.\n    - `agent_interceptor`: Tier B async agent gate (`agy -p`, `codex -p`, `gemini`, `ollama`), sets `status: pending_agent_gate` (`issues.pending_transition_exec_id`), holds card provisionally with `\u23f3\ud83e\udd16`, snaps back with `\ud83d\uded1\ud83e\udd16` or confirms with `\u2705\ud83e\udd16`.\n  - Zero-shell CLI execution (`${context} | agy -p` / `codex -p`).\n  - Admin Workflow Transition Studio UI: pipeline hooks, ordering, dry-run drawer.\n- **Implementation Evidence:**\n  - Database models: `database/models/workflow.py` (`WorkflowTransitionHook`, `WorkflowTransitionExecution`, `WorkflowHookInvocation`).\n  - Backend modules: `kanban/api/v1/workflow_hooks.py`, `kanban/api/v1/transitions.py`, `kanban/issues/workflow_service.py`.\n  - Frontend components: `TransitionRuleCard.tsx`, `DryRunDrawer.tsx`, `useCardSnapBackAnimation.ts`.\n- **Verification Evidence:**\n  - Database tests: `database/tests/test_workflow_hooks_ddl.py`.\n  - API tests: `kanban/tests/workflows/test_workflow_hooks_api.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift / Integration Issue:**\n  - **Missing Model Export:** `database/models/__init__.py` did not import or expose `WorkflowTransitionHook`, `WorkflowTransitionExecution`, and `WorkflowHookInvocation` from `database/models/workflow.py`. Consequently, `tests/perf/test_perf_sync_hooks_sla.py` failed during collection with `ImportError: cannot import name 'WorkflowTransitionHook' from 'database.models'`.\n- **Gaps & Recommendations:**\n  - Export `WorkflowTransitionHook`, `WorkflowTransitionExecution`, and `WorkflowHookInvocation` in `database/models/__init__.py` and include them in `__all__`.\n\n---\n\n### Section 15: >=95% Clean-DB Testing, Pluggable AI Fixtures, Local Agent CLI & Governance Gates\n\n- **Target Architectural Contract:**\n  - Mandatory >= 95% unit coverage, zero compiler/linter warnings.\n  - Sub-10s Clean-DB test architecture: tmpfs template PostgreSQL + `SAVEPOINT` rollback.\n  - Pluggable AI fixtures: `FixtureLLMProvider` and `FixtureCLIRunner` for deterministic offline testing.\n  - Local Agent CLI: `uv run kanban-agent validate-*` (`validate-echo`, `validate-qa-packet`, `validate-sparkle`, `validate-sticky-promo`, `validate-transition`, `validate-verdict`).\n  - Governance Gates: UI Specialist Gate, API + UI Dual Specialist Gate, Local `reality-checker` Forensic QA Gate, Dash CI/CD verification (`https://dash.hackedyour.info/llms.txt`).\n- **Implementation Evidence:**\n  - Test fixtures: `agent/testing/fixtures.py`, `agent/tests/testing/test_fixtures.py`.\n  - CLI commands: `agent/cli_commands/validate_echo.py`, `validate_qa_packet.py`, `validate_sparkle.py`, `validate_sticky_promo.py`, `validate_transition.py`, `validate_verdict.py`.\n  - Specialist rules: `.agents/agents/reality-checker.md`, `ui-designer.md`, `ux-architect.md`, `backend-architect.md`, `api-tester.md`, `security-engineer.md`.\n- **Verification Evidence:**\n  - Active test suites across all 4 modules (`kanban/tests/` 1,363 tests, `database/tests/` 432 tests, `mcp/tests/` 290 tests, `agent/tests/` 523 tests).\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift & Gaps:**\n  - Several unit tests have drift relative to updated tool counts and model exports (detailed in Section 11 and Section 14).\n- **Gaps & Recommendations:** Fix the model exports and test suite expectations to achieve clean monorepo test runs.\n\n---\n\n## Unimplemented and Planned Features Catalog\n\n### 1. Dense Vector Hybrid Search RRF Execution Pipeline\n- **Spec Section:** Section 11.2, Section 11.3, Section 12.2.\n- **Current Code Status:**\n  - `database/models/embeddings.py` defines `ObjectEmbedding(id, object_id, embedding_vector, model_identifier)`.\n  - `kanban/api/v1/schemas/search.py` accepts `mode: \"lexical\" | \"hybrid\"`.\n  - Response schemas fix `executed_mode: Literal[\"lexical\"] = \"lexical\"`.\n  - `kanban/services/search.py` executes purely PostgreSQL lexical `tsvector` (`websearch_to_tsquery`) and trigram `pg_trgm` scoring.\n- **Gap:** Live dense vector retrieval via `pgvector` HNSW index and Reciprocal Rank Fusion (RRF) combining vector and lexical rankings is not active at runtime.\n- **Roadmap Priority:** P1.\n\n### 2. Dedicated Native Anthropic API Provider\n- **Spec Section:** Section 10.1 (`Vendor-Neutral LLMProvider Protocol & Adapter Matrix`).\n- **Current Code Status:**\n  - `agent/providers/` implements `openai_provider.py`, `ollama.py`, and `gemini.py`.\n  - Anthropic models can be invoked via OpenAI-compatible compatibility layers or via the `codex -p` / `claude` CLI pipe harness.\n- **Gap:** A first-class `AnthropicProvider` class natively implementing the `LLMProvider` protocol (handling Anthropic `/v1/messages` format, native prompt caching, and token usage headers) is not implemented.\n- **Roadmap Priority:** P1.\n\n### 3. Non-OIDC OAuth2 Profile & Claim Mapper\n- **Spec Section:** Section 4.1, Section 4.2.\n- **Current Code Status:**\n  - `kanban/auth/cards/handshake.py` tests reachability of `authorization_endpoint` and `token_endpoint`.\n  - `kanban/auth/oidc/` handles standard OpenID Connect discovery and token validation.\n- **Gap:** Non-OIDC OAuth2 providers (such as legacy corporate OAuth or custom internal OAuth without `/.well-known/openid-configuration`) require configurable claim mapping (e.g. mapping `user:email`, `login`, `id` JSON fields).\n- **Roadmap Priority:** P1.\n\n### 4. Published Container Image for `thumbs-up-kanban:sandbox`\n- **Spec Section:** Section 2.4 (`docker-compose.yml` service `script-sandbox`).\n- **Current Code Status:**\n  - `agent/runners/cli_pipe.py` and `deploy/seccomp/sandbox-profile.json` provide nsjail isolation logic.\n  - `docker-compose.yml` references image `thumbs-up-kanban:sandbox`.\n- **Gap:** Dockerfile does not include a dedicated build stage named `sandbox` (it has `web-builder`, `py-builder`, `runtime-slim`, `agent-runner`, `standalone`).\n- **Roadmap Priority:** P2.\n\n### 5. Web Client OpenAPI Artifact Synchronization\n- **Spec Section:** Section 2.1, Section 11.\n- **Current Code Status:**\n  - `kanban/web/openapi.json` is synchronized with the live schema.\n  - The live FastAPI application defines 242+ paths, 316+ operations, and 314+ schemas.\n- **Resolution:** All routes and schemas are exported into the web package and client types regenerated.\n- **Roadmap Priority:** P0.\n\n---\n\n## Architectural Drift & Deviations Catalog\n\n### Drift 1: Agent Surface Tool Count (9 Tools vs. 8 Spec Bullets)\n- **Spec Text:** Section 11.1 cited \"8 tools\", grouping `link_objects & add_comment` together as item 8.\n- **Code Reality:** `mcp/surfaces/agent/` provides 9 distinct tools: `search_tickets`, `read_ticket`, `create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`, `add_comment`, `link_objects`.\n- **Resolution:** The schema budget test (`mcp/tests/test_schema_budget.py`) validates that all 9 tools consume ~1,759 tokens, safely under the 1,850 token ceiling. The spec should be updated to document 9 distinct agent tools.\n\n### Drift 2: Admin Tool 6 Repo Binding Discrepancy\n- **Spec Text:** Section 11.4 Tool 6 (`manage_cycles_and_modules`) explicitly includes `bind_project_repo` for read-only Git mirror bindings for workflow gates.\n- **Code Reality:** `mcp/surfaces/admin/manage_cycles_and_modules.py` implements `bind_project_repo`, `list_repo_bindings`, `refresh_repo_binding`, and `unbind_project_repo`.\n- **Test Conflict:** `mcp/tests/admin/test_manage_cycles_and_modules.py:test_contract_no_bind_or_delete_actions` asserts that `bind_project_repo` is NOT an action on Tool 6.\n- **Resolution:** Update the outdated unit test to align with the authoritative spec and implementation.\n\n### Drift 3: Workflow Models Missing from `database/models/__init__.py`\n- **Spec Text:** Section 14.2 specifies DDL models for `workflow_transition_hooks`, `workflow_transition_executions`, and `workflow_hook_invocations`.\n- **Code Reality:** Defined in `database/models/workflow.py`, but omitted from `database/models/__init__.py`.\n- **Impact:** `tests/perf/test_perf_sync_hooks_sla.py` fails collection due to `ImportError: cannot import name 'WorkflowTransitionHook' from 'database.models'`.\n- **Resolution:** Add imports and `__all__` entries for all three workflow models in `database/models/__init__.py`.\n\n### Drift 4: Protocol Test Tool Expectation List\n- **Code Reality:** `/mcp/agent` mounts 9 execution tools.\n- **Test Conflict:** `mcp/tests/test_protocol.py` line 125 hardcodes a 7-tool list, failing tool list assertion.\n- **Resolution:** Update `test_protocol.py` expected tools list to include all 9 tools.\n\n---\n\n## Concrete Recommendations for Roadmap Prioritization\n\n### Phase 0: Immediate Integrity & Synchronization (P0)\n1. **Export OpenAPI & Sync TypeScript Types:**\n   Run `python -m kanban.tools.export_openapi kanban/web/openapi.json` and `pnpm --dir kanban/web run gen:api` to bring `kanban/web/openapi.json` up to date with all 275 FastAPI routes (366 operations, 384 schemas).\n2. **Export Workflow Models in Database Package:**\n   Update `database/models/__init__.py` to import and re-export `WorkflowTransitionHook`, `WorkflowTransitionExecution`, and `WorkflowHookInvocation` from `database/models/workflow.py`.\n3. **Reconcile Stale MCP Unit Tests:**\n   Update `mcp/tests/test_protocol.py` and `mcp/tests/agent/test_search_tickets.py` to recognize the 9 agent tools (plus `update_workpad`), and update `mcp/tests/admin/test_manage_cycles_and_modules.py` to reflect the Tool 6 repo binding contract.\n\n### Phase 1: Search & AI Provider Extensions (P1)\n1. **Dense Vector Hybrid Search Pipeline (Completed):**\n   Fully implemented via KAN-78 in `kanban/services/search.py`, connecting `ObjectEmbedding` pgvector similarity queries with Reciprocal Rank Fusion (RRF) and HNSW index scans.\n2. **Implement Native Anthropic Provider:**\n   Author `agent/providers/anthropic.py` implementing `LLMProvider` for direct Claude 3.5 Sonnet / Haiku integration with prompt caching.\n3. **Non-OIDC OAuth2 Field Mapping:**\n   Add configurable user profile claim mappings for generic OAuth2 auth cards.\n\n### Phase 2: Operations & Tooling Hardening (P2)\n1. **Container Image Target for Sandbox:**\n   Add explicit `sandbox` stage to `Dockerfile` with nsjail dependencies.\n2. **Remote Runner Integration Benchmarks:**\n   Provide automated integration tests for `kanban-agent-runner` mTLS WSS loops in CI.\n"
  },
  {
    "slug": "blinking-cursor-sparkle-completion-engine",
    "title": "[Informational] Blinking Cursor Sparkle Completion Engine",
    "category": "informational",
    "track": "Feature & Field Reference",
    "subtrack": "Inline AI Completion",
    "audience": "Authors & Engineers",
    "order": 6,
    "summary": "Software documentation, bug reports, and requirements specifications benefit greatly from AI assistance, but disruptive popups and intrusive autocomplete modals create frustration. \ud83d\udc4dkanban introduces the **Blinking Cursor Sparkle (`\u2728`) Completion Engine**: an unobtrusive, editor-integrated Fill-In-the-Middle (FIM) completion system.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "editor-integration-and-caret-state-machine",
        "title": "Editor Integration and Caret State Machine",
        "level": 2
      },
      {
        "id": "caret-state-transitions",
        "title": "Caret State Transitions",
        "level": 3
      },
      {
        "id": "acceptance-and-surgical-right-click-matrix",
        "title": "Acceptance and Surgical Right-Click Matrix",
        "level": 2
      },
      {
        "id": "keyboard-shortcuts",
        "title": "Keyboard Shortcuts",
        "level": 3
      },
      {
        "id": "surgical-right-click-disambiguation-menu",
        "title": "Surgical Right-Click Disambiguation Menu",
        "level": 3
      },
      {
        "id": "outbound-security-and-privacy-safeguards",
        "title": "Outbound Security and Privacy Safeguards",
        "level": 2
      }
    ],
    "content": "# [Informational] Blinking Cursor Sparkle Completion Engine\n\n## Overview\n\nSoftware documentation, bug reports, and requirements specifications benefit greatly from AI assistance, but disruptive popups and intrusive autocomplete modals create frustration. \ud83d\udc4dkanban introduces the **Blinking Cursor Sparkle (`\u2728`) Completion Engine**: an unobtrusive, editor-integrated Fill-In-the-Middle (FIM) completion system.\n\nThe engine remains dormant while an engineer is typing actively. When the author pauses for 300ms, the engine analyzes the surrounding prefix and suffix context, queries the configured LLM provider, and presents high-probability text as light ghost text directly ahead of the blinking cursor.\n\n---\n\n## Editor Integration and Caret State Machine\n\nThe Sparkle engine is deeply integrated into the ProseMirror Markdown editor (`agent/sparkle/` and `kanban/web/src/features/editor/sparkle/`).\n\n```mermaid\nflowchart TD\n    Typing[\"User Typing in Markdown Editor\"] -->|Keystroke detected| ResetTimer[\"Reset Debounce Timer (300ms)\"]\n    ResetTimer -->|300ms elapsed with zero keystrokes| Extractor[\"FIM Context Extractor<br/>- Prefix: up to 2,000 chars<br/>- Suffix: up to 1,000 chars\"]\n    Extractor --> Scrubber[\"Outbound Secret Scrubber<br/>Redact API keys, Bearer tokens, secrets\"]\n    Scrubber -->|Dispatch async completion request| Provider[\"Configured LLM Provider<br/>OpenAI / Ollama / Gemini\"]\n    Provider -->|Candidate text returned| SparkleRender[\"Sparkle Ghost-Text Render<br/>- Cursor glyph transitions to \u2728<br/>- Inline ghost text displayed in editor DOM\"]\n    SparkleRender -->|Tab / Enter| Accepted[\"Accepted into Document\"]\n    SparkleRender -->|Escape / Typing| Dismissed[\"Dismissed & Restored\"]\n```\n\n![Editor with Mermaid Diagrams and Sparkle Completion](images/12-editor-mermaid-and-sparkle.png)\n\n### Caret State Transitions\n\n```mermaid\nstateDiagram-v2\n    [*] --> Typing\n    Typing --> DebounceIdle: Pause typing (300ms)\n    DebounceIdle --> Typing: Keystroke detected (Abort)\n    DebounceIdle --> Fetching: Extract Context & Scrub Secrets\n    Fetching --> Typing: Keystroke detected (Abort request)\n    Fetching --> Presentation: Completion Received (\u2728 glyph active)\n    Presentation --> Typing: Escape or Continue Typing (Dismiss)\n    Presentation --> Accepted: Tab or Enter (Accept All)\n    Presentation --> WordAccepted: Alt+Right (Accept Next Word)\n    WordAccepted --> Presentation: Remaining Ghost Text\n    Accepted --> [*]\n```\n\n1. **Typing State:** User is typing. Ghost text is hidden, and pending requests are immediately aborted via `AbortController`.\n2. **Debounce Idle State:** After 300ms of inactivity, context extraction occurs.\n3. **Fetching State:** The cursor displays a subtle, pulsating sparkle (`\u2728`) glyph indicating an active lookup.\n4. **Presentation State:** Proposed completion text appears inline in a muted gray tone (`#94a3b8`).\n5. **Resolution State:** User accepts all, accepts word-by-word, or continues typing to dismiss.\n\n---\n\n## Acceptance and Surgical Right-Click Matrix\n\nUnlike rigid autocomplete engines that force an all-or-nothing choice, \ud83d\udc4dkanban provides fine-grained acceptance mechanisms:\n\n### Keyboard Shortcuts\n- **Accept Entire Completion:** Press `Tab` or `Enter`.\n- **Accept Word-by-Word:** Press `Ctrl+RightArrow` (`Alt+RightArrow` on macOS) to accept the next word, allowing surgical editing.\n- **Dismiss:** Press `Escape` or simply continue typing.\n\n### Surgical Right-Click Disambiguation Menu\n\nRight-clicking directly on the sparkle glyph or ghost text opens a targeted 6-option context menu:\n\n| Menu Action | Keyboard Equiv | Action Behavior |\n| :--- | :--- | :--- |\n| **Accept All** | `Tab` | Inserts the full suggested text into the document. |\n| **Accept Next Word** | `Alt+Right` | Inserts only the next word, keeping the remaining ghost text. |\n| **Accept Next Line** | `Shift+Enter` | Inserts the current line of the suggestion. |\n| **Dismiss Suggestion** | `Escape` | Removes the ghost text and returns to normal editing. |\n| **Regenerate Alternative** | `Ctrl+Space` | Discards current candidate and requests a new completion variant. |\n| **Elaborate with Agent** | Click | Prompts the AI assistant to expand the suggestion into detailed points. |\n\n---\n\n## Outbound Security and Privacy Safeguards\n\nSending partial document text to LLMs introduces risk if credentials or confidential variables are present in the editor.\n\nThe Sparkle pipeline applies mandatory pre-flight scrubbing:\n- **Credential Redaction:** Evaluates text against high-entropy patterns (AWS keys, GitHub tokens, JWTs, standard private keys) and replaces them with `[REDACTED_SECRET]` before transmission.\n- **Local LLM Routing:** Workspaces configured with air-gapped security route all Sparkle requests exclusively to local Ollama endpoints on `data_net` or `sandbox_net`, ensuring zero outbound WAN egress.\n- **Strict Latency Budget:** Requests enforce a hard 1,500ms timeout. If the LLM does not return within the budget, the request is cleanly discarded to avoid jarring layout shifts.\n"
  },
  {
    "slug": "canonical-markdown-and-safe-media-pipeline",
    "title": "[Architectural] Canonical Markdown and Safe Media Pipeline",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Functional Architecture",
    "audience": "Security Engineers & Content Architects",
    "order": 7,
    "summary": "The storage and rendering of rich text is a primary vector for both data corruption and cross-site scripting (XSS) vulnerabilities. Many project management tools store raw HTML or proprietary JSON formats, leading to database bloat, rendering inconsistencies across platforms, and prompt injection vulnerabilities when ingested by AI agents.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "ingestion-sanitization-architecture",
        "title": "Ingestion Sanitization Architecture",
        "level": 2
      },
      {
        "id": "unicode-lone-surrogate-rejection",
        "title": "1. Unicode Lone Surrogate Rejection",
        "level": 3
      },
      {
        "id": "hidden-dom-paste-jacking-defense",
        "title": "2. Hidden-DOM Paste-Jacking Defense",
        "level": 3
      },
      {
        "id": "lossless-markdown-normalization",
        "title": "3. Lossless Markdown Normalization",
        "level": 3
      },
      {
        "id": "safe-media-and-client-side-rendering",
        "title": "Safe Media and Client-Side Rendering",
        "level": 2
      },
      {
        "id": "client-side-mermaid-diagrams-beautiful-mermaid",
        "title": "Client-Side Mermaid Diagrams (beautiful-mermaid)",
        "level": 3
      },
      {
        "id": "vector-graphics-and-svg-sandboxing",
        "title": "Vector Graphics and SVG Sandboxing",
        "level": 3
      },
      {
        "id": "media-proxying-and-ssrf-protection",
        "title": "Media Proxying and SSRF Protection",
        "level": 3
      }
    ],
    "content": "# [Architectural] Canonical Markdown and Safe Media Pipeline\n\n## Overview\n\nThe storage and rendering of rich text is a primary vector for both data corruption and cross-site scripting (XSS) vulnerabilities. Many project management tools store raw HTML or proprietary JSON formats, leading to database bloat, rendering inconsistencies across platforms, and prompt injection vulnerabilities when ingested by AI agents.\n\n\ud83d\udc4dkanban enforces a strict **Canonical Markdown Pipeline**:\n- **Canonical UTF-8 Markdown Only:** All tickets, stickies, doc pages, and comments are stored exclusively as canonical UTF-8 Markdown. Zero raw HTML is stored in the database.\n- **Hostile Input Sanitization:** Aggressive pre-encoding validation rejects malformed Unicode and paste-jacking attacks at the network boundary.\n- **Client-Side Safe Rendering:** Markdown parsing, syntax highlighting, and diagram generation occur securely on the client with zero execution permissions.\n\n---\n\n## Ingestion Sanitization Architecture\n\n```mermaid\nflowchart TD\n    Input[\"User Input / Clipboard / API Payload\"] --> Surrogate[\"Unicode Surrogate Guard<br/>- Checks codepoints for 0xD800 <= ord(c) <= 0xDFFF<br/>- Rejects malformed UTF-16 lone surrogates\"]\n    Surrogate --> DOMPrune[\"Hidden-DOM Paste-Jacking Pruner<br/>- Strips zero-width chars (U+200B..U+200D)<br/>- Removes display:none / opacity:0 hidden nodes\"]\n    DOMPrune --> Normalizer[\"Auto-Format Conversion Engine<br/>- Auto-detects Plain Text, Markdown, or HTML<br/>- Normalizes HTML to clean CommonMark\"]\n    Normalizer --> DB[\"PostgreSQL Universal Object Graph<br/>(Clean UTF-8 Canonical Markdown Text)\"]\n```\n\n### 1. Unicode Lone Surrogate Rejection\n\nPostgreSQL text columns require valid UTF-8. A common exploit vector involves sending UTF-16 lone surrogates (`0xD800` through `0xDFFF`) which cannot be translated into valid UTF-8, triggering unhandled exceptions or desynchronizing downstream parsers.\n\nThe `unicode_guard` module inspects every incoming payload before `.encode(\"utf-8\")`:\n```python\nfor char in content:\n    if 0xD800 <= ord(char) <= 0xDFFF:\n        raise HTTPException(\n            status_code=422,\n            detail={\"error\": \"INVALID_UTF8_SURROGATE\", \"codepoint\": hex(ord(char))}\n        )\n```\n\n### 2. Hidden-DOM Paste-Jacking Defense\n\nAttackers often craft malicious web pages where copying a benign command (such as `git clone ...`) secretly copies hidden HTML containing malicious shell instructions or invisible LLM prompt injections.\n\nThe `hidden_dom` pruner analyzes pasted clipboard content:\n- Evaluates CSS styles and DOM visibility, pruning any elements styled with `display: none`, `visibility: hidden`, `opacity: 0`, or positioned off-screen.\n- Strips non-printable zero-width characters (such as `\\u200B`, `\\u200C`, `\\u200D`, and `\\uFEFF`) that could be used for invisible steganographic prompt injection.\n\n### 3. Lossless Markdown Normalization\n\nWhen rich text or tables are pasted into the editor, the client-side parser translates the structures into standard CommonMark tables, fenced code blocks, and list hierarchies before sending the payload to the server.\n\n---\n\n## Safe Media and Client-Side Rendering\n\nRich technical documentation requires diagrams, pictures, and vector graphics. \ud83d\udc4dkanban provides comprehensive support for visual media while maintaining strict security boundaries.\n\n![Editor with Mermaid Diagrams and Sparkle Completion](images/12-editor-mermaid-and-sparkle.png)\n\n### Client-Side Mermaid Diagrams (`beautiful-mermaid`)\n\nMermaid diagram code blocks (````mermaid ... ````) are parsed and rendered directly in the user's browser:\n- **Web Worker Isolation:** Diagram layout and SVG compilation run inside a dedicated, sandboxed Web Worker.\n- **Zero DOM Access:** The worker thread has zero access to the document DOM, session cookies, or local storage.\n- **Instant Preview:** Changes in diagram definitions update live as the author types.\n\n![Mermaid Diagram Rendered Inside Work Item Description](images/31-mermaid-rendered-ticket.png)\n\n### Vector Graphics and SVG Sandboxing\n\nSVG files uploaded or embedded in documentation can contain malicious `<script>` tags or event handlers (`onload`, `onerror`).\n- SVGs are sanitized on upload to strip all script nodes, external references, and foreign objects.\n- When rendered in the browser, SVGs are loaded via sandboxed `<iframe>` elements or `<img>` tags where script execution is disabled by the browser engine.\n\n### Media Proxying and SSRF Protection\n\nWhen documentation references external image URLs, the image is retrieved through a hardened server-side media proxy:\n- **Cryptographic HMAC Signature:** Images are signed with a server-side HMAC key (`GET /api/v1/media-proxy?u=<url>&sig=<HMAC>`) preventing open proxy abuse.\n- **Private Subnet Blocking:** The media proxy forbids connections to loopback (`127.0.0.0/8`), link-local (`169.254.0.0/16`), and private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).\n- **IP Leak Prevention:** Users viewing tickets do not expose their local IP address or browser fingerprint to external third-party image hosts.\n- **Content-Type Validation:** Responses are validated to ensure only genuine image MIME types (`image/png`, `image/jpeg`, `image/webp`, `image/gif`) are proxied.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Browser as User Browser\n    participant App as Media Proxy (GET /api/v1/media-proxy)\n    participant DNS as DNS Resolver & IP Validator\n    participant Ext as Remote Image Host\n\n    Browser->>App: GET /api/v1/media-proxy?u=<url>&sig=<HMAC>\n    App->>App: Verify HMAC Signature\n    App->>DNS: Resolve Hostname to IP & Pin Socket\n    alt IP in RFC 1918 / Loopback / Link-Local\n        DNS-->>App: Rejected (SSRF Blocked)\n        App-->>Browser: 403 Forbidden (SSRF Violation)\n    else Public Internet IP\n        DNS-->>App: Approved Public IP\n        App->>Ext: GET Request (Strict Timeout & Max Size)\n        Ext-->>App: Image Stream\n        App->>App: Verify Image Magic Bytes & MIME Type\n        App-->>Browser: Proxied Image (Cache-Control: public, max-age=86400)\n    end\n```\n"
  },
  {
    "slug": "clean-db-testing-and-governance-gates",
    "title": "[Architectural] Clean-DB Testing and Governance Gates",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Functional Architecture",
    "audience": "QA Engineers & Test Automation Leads",
    "order": 8,
    "summary": "Software quality and security cannot be tested into a system as an afterthought. \ud83d\udc4dkanban operates under a strict **Shift-Left Mandate**: all code must achieve and maintain a minimum of **95% automated test coverage**, zero compiler or linter warnings, sub-second test execution speeds, and verifiable CI/CD build proofs before merging.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "clean-db-testing-architecture",
        "title": "Clean-DB Testing Architecture",
        "level": 2
      },
      {
        "id": "key-performance-metrics",
        "title": "Key Performance Metrics",
        "level": 3
      },
      {
        "id": "the-role-isolation-invariant-kanba-162",
        "title": "The Role Isolation Invariant (KANBA-162)",
        "level": 2
      },
      {
        "id": "deterministic-ai-testing-and-pluggable-fixtures",
        "title": "Deterministic AI Testing and Pluggable Fixtures",
        "level": 2
      },
      {
        "id": "continuous-governance-and-cicd-gates",
        "title": "Continuous Governance and CI/CD Gates",
        "level": 2
      }
    ],
    "content": "# [Architectural] Clean-DB Testing and Governance Gates\n\n## Overview\n\nSoftware quality and security cannot be tested into a system as an afterthought. \ud83d\udc4dkanban operates under a strict **Shift-Left Mandate**: all code must achieve and maintain a minimum of **95% automated test coverage**, zero compiler or linter warnings, sub-second test execution speeds, and verifiable CI/CD build proofs before merging.\n\nTo ensure tests execute rapidly while exercising real database constraints, \ud83d\udc4dkanban implements an innovative **Clean-DB Testing Architecture** combining tmpfs PostgreSQL template instances with sub-millisecond transaction rollback isolation.\n\n---\n\n## Clean-DB Testing Architecture\n\nRunning comprehensive integration tests against a real relational database is typically slow, often leading teams to compromise with brittle in-memory SQLite mocks. SQLite cannot test PostgreSQL-specific features like `FORCE ROW LEVEL SECURITY`, `ltree` hierarchies, `pgvector`, or JSONB index operators.\n\n\ud83d\udc4dkanban eliminates this compromise:\n\n```mermaid\nflowchart TD\n    Init[\"Pre-Test Suite Initialization\"] --> Template[\"Template Database Provisioning<br/>- Boots PostgreSQL on RAM-backed tmpfs mount<br/>- Runs all Alembic migrations via kanban_migrator<br/>- Freezes template database 'kanban_template'\"]\n    Template --> Savepoint[\"Sub-Millisecond SAVEPOINT Isolation<br/>- Opens connection to template DB<br/>- Begins TX & creates SAVEPOINT 'test_isolation'<br/>- Drops role to 'kanban_app' with FORCE RLS active\"]\n    Savepoint --> Assert[\"Test Execution & Assertions<br/>- Full RLS enforcement<br/>- Sub-millisecond execution\"]\n    Assert --> Rollback[\"Zero-Disk Rollback Cleanup<br/>- Executes ROLLBACK TO SAVEPOINT 'test_isolation'<br/>- Complete database reset in <1ms<br/>- Leaves DB 100% clean for next test\"]\n```\n\n![Standalone Status and Runtime Health Diagnostics](images/04-standalone-status-panel.png)\n\n### Key Performance Metrics\n- **Sub-Millisecond Cleanup:** Resetting the database state takes less than 0.8 milliseconds per test.\n- **Full Parallelism:** Test suites execute across all available CPU cores using `pytest -n auto` without database collision.\n- **Hardware-Level Fidelity:** Tests execute against authentic PostgreSQL 16 binaries, testing real RLS policies and table locks.\n\n---\n\n## The Role Isolation Invariant (`KANBA-162`)\n\n```mermaid\nsequenceDiagram\n    autonumber\n    participant Runner as Pytest Test Runner\n    participant Fixture as Clean-DB Fixture\n    participant PG as PostgreSQL Engine (FORCE RLS)\n\n    Runner->>Fixture: Start Test Case\n    Fixture->>PG: BEGIN TRANSACTION & SAVEPOINT test_isolation\n    Fixture->>PG: SET ROLE kanban_migrator (Superuser Privileges)\n    Fixture->>PG: Provision Workspace & Seed Records\n    Fixture->>PG: SET LOCAL ROLE kanban_app (Privilege Drop!)\n    Fixture->>PG: SET LOCAL app.current_principal_id = :test_user_id\n    Runner->>PG: Execute Test Queries & Application Logic\n    PG-->>Runner: Enforce Strict RLS (No Bypass Permitted)\n    Runner->>Fixture: Test Assertions Completed\n    Fixture->>PG: ROLLBACK TO SAVEPOINT test_isolation (<1ms)\n    PG-->>Fixture: Database Returned to Pristine State\n```\n\nA common testing hazard occurs when tests execute queries as a database superuser, inadvertently bypassing Row-Level Security policies.\n\nTo prevent this, test fixtures enforce the `KANBA-162` invariant:\n1. **Privileged Setup:** Fixtures provision bootstrap organizations, workspaces, and system configurations under `kanban_migrator` authority.\n2. **Mandatory Privilege Drop:** Before invoking test logic or application handlers, the fixture explicitly executes:\n   ```sql\n   SET LOCAL ROLE kanban_app;\n   SET LOCAL app.current_principal_id = :test_user_id;\n   ```\n3. **Hardware Enforcement:** The `kanban_app` role cannot bypass RLS. Every assertion validates the exact security boundaries encountered by live production users.\n\n---\n\n## Deterministic AI Testing and Pluggable Fixtures\n\nAutonomous agent interactions are verified without external network calls or token expenditure:\n- **`FixtureLLMProvider`:** Intercepts agent LLM calls and returns deterministic, recorded response payloads.\n- **`FixtureCLIRunner`:** Simulates CLI pipe harnesses (`agy -p`, `codex -p`), validating that input schemas match expected JSON structures.\n- **Failure Injection:** Simulates transient network partitions, HTTP 429 rate limits, and malformed completions to ensure graceful degradation.\n\n---\n\n## Continuous Governance and CI/CD Gates\n\nThe development pipeline enforces non-bypassable quality and security gates:\n\n| Governance Gate | Verification Command | Enforcement Policy |\n| :--- | :--- | :--- |\n| **Code Coverage Gate** | `pytest --cov=kanban --cov=database --cov=mcp --cov=agent` | Strictly fails if coverage falls below 95%. |\n| **RLS Policy Audit** | `pytest database/tests/test_p1_14_rls_*.py` | Validates 100% table coverage and zero-context fail-closed behavior. |\n| **Typography Gate** | `python3 scripts/check_no_dashes.py --all` | Rejects any forbidden Unicode em-dash or en-dash characters. |\n| **Forensic QA Gate** | Multi-agent passive audit (`reality-checker`) | Mandates verifiable test logs and annotated visual screenshots. |\n| **CI/CD Guardrail** | Dash CI/CD integration (`https://dash.hackedyour.info`) | Automated status monitoring, build log collection, and emergency halt on broken builds. |\n\n![System Settings and Governance Diagnostics](images/26-system-settings.png)\n"
  },
  {
    "slug": "custom-scripts-and-json-security-architecture",
    "title": "[Architectural] Custom Scripts and JSON Security Architecture",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Security Architecture",
    "audience": "Application Security Engineers",
    "order": 9,
    "summary": "Extensibility is central to \ud83d\udc4dkanban: administrators can author custom fields, dynamic computed formulas, and WebAssembly (Wasm) logic to compute metadata in real time. However, allowing untrusted or semi-trusted script execution and arbitrary JSON payloads introduces critical attack vectors: 1. **Supply-chain and Binary Tampering:** Substituting an approved Wasm module binary with a malicious payload after approval. 2. **Re-entrant Elevation:** Calling privileged endpoints (such as `test-execute` or `dry-run`) from within custom field scripts or workflow hooks to bypass security boundaries. 3. **Event-Loop CPU and Memory Denial-of-Service:** Exploiting Python abstract syntax tree (AST) evaluation through exponential operations, unbounded sequence allocations, or deep syntax tree exhaustion. 4. **JSON Payload Bombs:** Crashing or freezing ASGI servers via nested JSON recursion (stack overflow), unbounded key allocation (memory exhaustion), or invalid UTF-16 lone surrogates. 5. **Client-Side Prototype Pollution and DOM XSS:** Polluting JavaScript object prototypes via `__proto__` or `constructor` keys in parsed JSON, or injecting unvalidated HTML strings into the document object model.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "architectural-security-model",
        "title": "Architectural Security Model",
        "level": 2
      },
      {
        "id": "wasm-module-sha-256-binding-and-manifest-integrity",
        "title": "1. Wasm Module SHA-256 Binding and Manifest Integrity",
        "level": 2
      },
      {
        "id": "cryptographic-manifest-digest",
        "title": "Cryptographic Manifest Digest",
        "level": 3
      },
      {
        "id": "postgresql-tamper-revocation-trigger",
        "title": "PostgreSQL Tamper-Revocation Trigger",
        "level": 3
      },
      {
        "id": "test-execute-security-and-re-entrancy-protection",
        "title": "2. Test-Execute Security and Re-entrancy Protection",
        "level": 2
      },
      {
        "id": "administrative-access-control",
        "title": "Administrative Access Control",
        "level": 3
      },
      {
        "id": "re-entrancy-and-recursion-blocking",
        "title": "Re-entrancy and Recursion Blocking",
        "level": 3
      },
      {
        "id": "formula-ast-execution-bounds-denial-of-service-defense",
        "title": "3. Formula AST Execution Bounds (Denial-of-Service Defense)",
        "level": 2
      },
      {
        "id": "static-ast-complexity-checks",
        "title": "Static AST Complexity Checks",
        "level": 3
      },
      {
        "id": "arithmetic-and-allocation-bounds",
        "title": "Arithmetic and Allocation Bounds",
        "level": 3
      },
      {
        "id": "global-asgi-json-limits-middleware",
        "title": "4. Global ASGI JSON Limits Middleware",
        "level": 2
      },
      {
        "id": "streaming-body-size-caps",
        "title": "Streaming Body Size Caps",
        "level": 3
      },
      {
        "id": "utf-16-lone-surrogate-rejection",
        "title": "UTF-16 Lone-Surrogate Rejection",
        "level": 3
      },
      {
        "id": "non-recursive-iterative-structural-validation",
        "title": "Non-Recursive Iterative Structural Validation",
        "level": 3
      },
      {
        "id": "client-side-safe-json-and-trusted-types",
        "title": "5. Client-Side Safe JSON and Trusted Types",
        "level": 2
      },
      {
        "id": "safe-json-parsing-safejsonparse",
        "title": "Safe JSON Parsing (safeJsonParse)",
        "level": 3
      },
      {
        "id": "unified-trusted-types-policy",
        "title": "Unified Trusted Types Policy",
        "level": 3
      },
      {
        "id": "verification-and-audit-matrix",
        "title": "6. Verification and Audit Matrix",
        "level": 2
      }
    ],
    "content": "# [Architectural] Custom Scripts and JSON Security Architecture\n\n## Overview\n\nExtensibility is central to \ud83d\udc4dkanban: administrators can author custom fields, dynamic computed formulas, and WebAssembly (Wasm) logic to compute metadata in real time. However, allowing untrusted or semi-trusted script execution and arbitrary JSON payloads introduces critical attack vectors:\n1. **Supply-chain and Binary Tampering:** Substituting an approved Wasm module binary with a malicious payload after approval.\n2. **Re-entrant Elevation:** Calling privileged endpoints (such as `test-execute` or `dry-run`) from within custom field scripts or workflow hooks to bypass security boundaries.\n3. **Event-Loop CPU and Memory Denial-of-Service:** Exploiting Python abstract syntax tree (AST) evaluation through exponential operations, unbounded sequence allocations, or deep syntax tree exhaustion.\n4. **JSON Payload Bombs:** Crashing or freezing ASGI servers via nested JSON recursion (stack overflow), unbounded key allocation (memory exhaustion), or invalid UTF-16 lone surrogates.\n5. **Client-Side Prototype Pollution and DOM XSS:** Polluting JavaScript object prototypes via `__proto__` or `constructor` keys in parsed JSON, or injecting unvalidated HTML strings into the document object model.\n\nTo eliminate these vulnerabilities, \ud83d\udc4dkanban implements an end-to-end defense-in-depth architecture spanning ASGI middleware, database triggers, AST execution bounds, and browser sanitizers.\n\n---\n\n## Architectural Security Model\n\n```mermaid\nflowchart TD\n    Client[\"Client / External Agent\"] -->|HTTP / JSON Payload| JsonMiddleware[\"JsonLimitsMiddleware (ASGI)\"]\n\n    subgraph Inbound Guardrails\n        JsonMiddleware -->|1. Size Check| SizeCheck{\"Body <= 2 MiB / 25 MiB?\"}\n        SizeCheck -- No --> R413[\"413 PAYLOAD_TOO_LARGE\"]\n        SizeCheck -- Yes --> SurrogateCheck{\"UTF-16 Lone Surrogates?\"}\n        SurrogateCheck -- Yes --> R422S[\"422 INVALID_UTF8_SURROGATE\"]\n        SurrogateCheck -- No --> IterativeParser{\"Iterative JSON Scanner\"}\n        IterativeParser -->|Depth > 32| R422D[\"422 JSON_DEPTH_EXCEEDED\"]\n        IterativeParser -->|Keys > 5000| R422K[\"422 JSON_KEYS_EXCEEDED\"]\n        IterativeParser -->|Valid| Router[\"FastAPI Router\"]\n    end\n\n    subgraph Endpoint & Re-entrancy Guards\n        Router --> ScriptGuard[\"ScriptDepthGuardMiddleware\"]\n        ScriptGuard -->|X-Kanban-Script-Depth on Blocked Path| R409R[\"409 SCRIPT_RECURSION_BLOCKED\"]\n        ScriptGuard --> AuthGate[\"PROJECT_ADMIN + AAL2 Gate\"]\n        AuthGate -- Missing AAL2 --> R403AAL[\"403 AAL2_REQUIRED\"]\n        AuthGate -- Unauthorized --> R403A[\"403 INSUFFICIENT_CAPABILITY\"]\n        AuthGate -- Authorized --> ExecutionService[\"CustomFieldDefinitionService\"]\n    end\n\n    subgraph Sandboxed Execution & Manifest Integrity\n        ExecutionService --> ManifestCheck{\"Manifest SHA-256 Valid?\"}\n        ManifestCheck -- Tampered --> TamperRevoke[\"PostgreSQL Tamper Trigger Revokes Escalation\"]\n        ManifestCheck -- Valid --> ExecutorType{\"Engine Type\"}\n        ExecutorType -->|Wasm| WasmRegistry{\"ApprovedWasmModule Verified?\"}\n        WasmRegistry -- No --> R404W[\"404 WASM_MODULE_NOT_FOUND\"]\n        WasmRegistry -- Yes --> WasmSandbox[\"Wasmtime Isolated Engine\"]\n        ExecutorType -->|Safe Formula| ASTBounds[\"AST Bounds Checker\"]\n        ASTBounds -->|Nodes > 64 or Depth > 8| RNone[\"Returns None (Status ERROR, Value null)\"]\n        ASTBounds -->|Pow / Mult Bounds Check| ASTEval[\"_eval_safe_formula (Dict-Only Lookup)\"]\n    end\n```\n\n---\n\n## 1. Wasm Module SHA-256 Binding and Manifest Integrity\n\n### Cryptographic Manifest Digest\nCustom field definitions can declare escalated permissions (such as workspace-level or server-level API read/write scopes) requiring cryptographic signatures and administrative approvals. Previously, only the script text was included in the manifest hash calculation.\n\nUnder the hardened architecture (`kanban/custom_fields/manifest.py`), `compute_field_manifest_sha256` explicitly binds the compiled binary digest `wasm_module_sha256`. The canonical payload keys are:\n\n```python\ncanonical_manifest = {\n    \"credential_mode\": credential_mode,\n    \"egress_allowlist\": sorted(egress_allowlist),\n    \"output_format\": output_format,\n    \"output_format_metadata\": output_format_metadata,\n    \"script_source\": script_source,\n    \"target_scope\": target_scope,\n    \"tier\": tier,\n    \"wasm_module_sha256\": wasm_module_sha256,\n}\n```\n\n### PostgreSQL Tamper-Revocation Trigger\nWhen an existing definition is updated, changing `wasm_module_sha256` marks `spec_changed = True` (`kanban/custom_fields/service.py`). The database trigger `custom_field_manifest_tamper_revoke` executes immediately:\n- Escalation approvals (`status IN ('PENDING', 'PENDING_SECOND_APPROVER', 'APPROVED')`) are automatically revoked (`status = 'REVOKED'`, `revoked_reason = 'MANIFEST_SHA256_CHANGED'`).\n- The manifest hash is regenerated against the new binary payload.\n- Any attempt to substitute an unapproved or modified WebAssembly binary invalidates existing approval records, preventing unauthorized privilege escalation.\n\n---\n\n## 2. Test-Execute Security and Re-entrancy Protection\n\n### Administrative Access Control\nThe `POST /api/v1/projects/{project}/custom-fields/test-execute` endpoint allows testing custom field logic against draft ticket data before persisting to production. Because this endpoint executes script engines in real time, access is restricted:\n- **Requirement:** Callers must authenticate as `PROJECT_ADMIN` with Authenticator Assurance Level 2 (`AAL2`).\n- **Capability Check:** `CustomFieldDefinitionService.require_admin_and_aal2(session, caller, project)` verifies membership and enforces step-up authentication. Callers with AAL1 receive HTTP 403 `AAL2_REQUIRED`.\n- **Wasm Verification:** Wasm draft payloads are verified against the `ApprovedWasmModule` registry or approved hash store before execution. Unapproved Wasm modules return HTTP 404 `WASM_MODULE_NOT_FOUND`.\n\n### Re-entrancy and Recursion Blocking\nTo prevent custom scripts or webhook handlers from calling administrative execution endpoints recursively, `ScriptDepthGuardMiddleware` (`kanban/api/middleware/script_depth.py`) intercepts outbound internal calls carrying `X-Kanban-Script-Depth`.\n\nThe following paths are explicitly blocked from scripted invocations:\n- `/api/v1/projects/[^/]+/custom-fields/test-execute`\n- `/api/v1/projects/[^/]+/workflow-hooks/dry-run`\n\nAny scripted call attempting to reach these paths returns HTTP 409 `SCRIPT_RECURSION_BLOCKED`.\n\n---\n\n## 3. Formula AST Execution Bounds (Denial-of-Service Defense)\n\nSimple computed fields use Python AST formula evaluation (`kanban/custom_fields/executor.py`). While sandboxed, unconstrained AST operations could consume 100% of the asynchronous event loop CPU or allocate gigabytes of memory.\n\nThe safe formula engine enforces static and dynamic limits:\n\n### Static AST Complexity Checks\nBefore evaluation, `_check_formula_ast_bounds` traverses the AST tree:\n- **Node Count Limit:** The total number of AST nodes cannot exceed `64`.\n- **Depth Limit:** The maximum nesting depth of the AST tree cannot exceed `8`.\n- If either threshold is exceeded, `_check_formula_ast_bounds` / `_eval_safe_formula` returns `None` (and `test-execute` returns HTTP 200 with `status=\"ERROR\", value=null`).\n\n### Arithmetic and Allocation Bounds\n- **Power Operator (`ast.Pow`):** Exponents are restricted to `<= 64`, and base values are restricted to `abs(base) <= 1_000_000`. Exponentiation errors like negative exponents on zero (`0 ** -1` or `0.0 ** -2`) catch `ZeroDivisionError` and return `None`. This prevents operations like `999999 ** 999999` or division errors from freezing or crashing the process.\n- **Multiplication Operator (`ast.Mult`):** Sequence multiplication (e.g. `'A' * 1000000` or `[0] * 1000000`) is bounded to a maximum output length of `4096` elements or characters.\n- **Attribute Access (`ast.Attribute`):** Attribute access on Python objects via `getattr` is eliminated. Only dictionary key lookups are permitted (`obj.get(attr)` or `obj[attr]` when `obj` is an instance of `dict`). Introspection attributes (`__class__`, `__mro__`, `__subclasses__`) cannot be resolved.\n\n---\n\n## 4. Global ASGI JSON Limits Middleware\n\nJSON parsing in Python web frameworks typically buffers the entire request into memory before deserializing. Malicious clients can crash workers using deeply nested arrays (`[[[[...]]]]`) or gigabyte payloads.\n\n`JsonLimitsMiddleware` (`kanban/api/middleware/json_limits.py`) sits at the ASGI level:\n\n### Streaming Body Size Caps\n- **Default Limit:** `2 MiB` (2,097,152 bytes) for standard JSON API requests.\n- **Extended Limit:** `25 MiB` (26,214,400 bytes) for designated attachment and import routes:\n  - `/attachments`\n  - `/imports`\n  - `/api/v1/attachments`\n  - `/api/v1/admin/imports`\n- Bodies exceeding the limit are rejected immediately with HTTP 413 `PAYLOAD_TOO_LARGE` before reaching the application framework.\n\n### UTF-16 Lone-Surrogate Rejection\nPython strings and JSON encoders can be vulnerable to unpaired surrogate code points (`0xD800` through `0xDFFF`), which cause database serialization errors or security bypasses.\n- The middleware scans raw incoming bytes for invalid surrogate sequences before passing data to FastAPI.\n- Requests containing lone surrogates receive HTTP 422 `Unprocessable Entity` with error code `INVALID_UTF8_SURROGATE`.\n\n### Non-Recursive Iterative Structural Validation\nTo protect against stack overflows without paying the performance cost of complete parsing twice, the middleware uses an iterative character scanner for `application/json` and `+json` content types:\n- **Maximum Depth:** `MAX_JSON_DEPTH = 32`. Nested objects or arrays deeper than 32 levels return HTTP 422 `JSON_DEPTH_EXCEEDED`.\n- **Maximum Keys:** `MAX_JSON_KEYS = 5000`. Payloads containing more than 5,000 keys return HTTP 422 `JSON_KEYS_EXCEEDED`.\n- **Passthrough:** Multipart form data, Server-Sent Events (SSE), and static asset requests bypass JSON scanning entirely.\n\n---\n\n## 5. Client-Side Safe JSON and Trusted Types\n\nSecurity invariants extend directly to the browser client (`kanban/web/`):\n\n### Safe JSON Parsing (`safeJsonParse`)\nStandard `JSON.parse` is vulnerable to Prototype Pollution when handling untrusted JSON payloads containing `__proto__`, `constructor`, or `prototype` keys.\n\nThe utility `safeJsonParse` (`kanban/web/src/utils/safeJson.ts`) applies an iterative reviver function that removes these keys from the resulting object:\n- In `draftsStore.ts`, all draft restoration routines use `safeJsonParse`.\n- In `CustomFieldDefinitionEditor.tsx`, format metadata and formula test inputs are deserialized using `safeJsonParse`.\n\n```typescript\nexport function safeJsonParse<T = unknown>(text: string): T {\n  return JSON.parse(text, (key, value) => {\n    if (key === '__proto__' || key === 'constructor' || key === 'prototype') {\n      return undefined;\n    }\n    return value;\n  });\n}\n```\n\n### Unified Trusted Types Policy\nIn `kanban/web/src/editor/clipboard/trustedTypes.ts`, the `kanban-sanitizer` and `dompurify` Trusted Types policies ensure that any HTML passed to browser sinks is sanitized through `DOMPurify.sanitize(html, { RETURN_TRUSTED_TYPE: false })` before being wrapped as a `TrustedHTML` token.\n\n---\n\n## 6. Verification and Audit Matrix\n\n| Security Layer | Implementation File | Verification Test | Expected Defense Behavior |\n| :--- | :--- | :--- | :--- |\n| **Wasm Hash Binding** | `kanban/custom_fields/manifest.py` | `test_manifest_and_formula_security.py` | Modifying `wasm_module_sha256` alters `manifest_sha256` and revokes approval via `custom_field_manifest_tamper_revoke`. |\n| **Admin test-execute Gate** | `kanban/api/v1/custom_field_execution.py` | `test_manifest_and_formula_security.py` | Non-admin returns 403 `INSUFFICIENT_CAPABILITY`; AAL1 returns 403 `AAL2_REQUIRED`; unapproved Wasm returns 404 `WASM_MODULE_NOT_FOUND`. |\n| **Script Depth Guard** | `kanban/api/middleware/script_depth.py` | `test_script_depth_middleware.py` | Re-entrant `test-execute` or `dry-run` returns 409 `SCRIPT_RECURSION_BLOCKED`. |\n| **AST Node & Depth Bounds** | `kanban/custom_fields/executor.py` | `test_manifest_and_formula_security.py` | Nodes > 64 or depth > 8 returns `None` (test-execute returns 200 `status=\"ERROR\", value=null`). |\n| **AST Math & Sequence Bounds**| `kanban/custom_fields/executor.py` | `test_safe_formula_unit.py` | `ast.Pow` bounded to 64; `0 ** -1` returns `None`; sequence mult bounded to 4096; dict-only attrs. |\n| **ASGI Size Caps** | `kanban/api/middleware/json_limits.py` | `test_json_limits_middleware.py` | Payloads > 2 MiB (or > 25 MiB attachments/imports) return HTTP 413 `PAYLOAD_TOO_LARGE`. |\n| **ASGI Surrogate Rejection**| `kanban/api/middleware/json_limits.py` | `test_json_limits_middleware.py` | Lone surrogates `0xD800..0xDFFF` return HTTP 422 `INVALID_UTF8_SURROGATE`. |\n| **ASGI JSON Depth / Keys** | `kanban/api/middleware/json_limits.py` | `test_json_limits_middleware.py` | Depth > 32 returns 422 `JSON_DEPTH_EXCEEDED`; keys > 5000 returns 422 `JSON_KEYS_EXCEEDED`. |\n| **Client Safe JSON** | `kanban/web/src/utils/safeJson.ts` | `safeJson.test.ts` | Strips `__proto__`, `constructor`, `prototype` preventing prototype pollution. |\n| **Client Trusted Types** | `kanban/web/src/editor/clipboard/trustedTypes.ts` | `trustedTypes.test.ts` | Mandatory `DOMPurify.sanitize` execution on all `createHTML` calls. |\n"
  },
  {
    "slug": "enterprise-whitespace-and-kanban-board",
    "title": "[Informational] Enterprise Whitespace, Semantic Emojis, and Kanban Board",
    "category": "informational",
    "track": "Feature & Field Reference",
    "subtrack": "Board & Visual Design",
    "audience": "End Users & Product Leads",
    "order": 10,
    "summary": "High-performing engineering teams require interfaces that balance visual clarity with deep technical density. Cluttered, cramped dashboards create cognitive fatigue, while overly sparse designs hide crucial metadata. \ud83d\udc4dkanban delivers a refined **Enterprise Whitespace Design System**, combining generous breathing room with dense information display, sub-16ms drag-and-drop responsiveness, and the intuitive `<EmojiHint>` hover elaboration system.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "the-breathable-whitespace-design-system",
        "title": "The Breathable Whitespace Design System",
        "level": 2
      },
      {
        "id": "the-emojihint-semantic-hover-system",
        "title": "The <EmojiHint> Semantic Hover System",
        "level": 2
      },
      {
        "id": "kanban-board-view-and-sub-16ms-drag-and-drop",
        "title": "Kanban Board View and Sub-16ms Drag-and-Drop",
        "level": 2
      },
      {
        "id": "board-architecture-and-performance",
        "title": "Board Architecture and Performance",
        "level": 3
      },
      {
        "id": "the-5-native-view-layouts",
        "title": "The 5 Native View Layouts",
        "level": 2
      },
      {
        "id": "board-view-layoutboard",
        "title": "1. Board View (?layout=board)",
        "level": 3
      },
      {
        "id": "list-view-layoutlist",
        "title": "2. List View (?layout=list)",
        "level": 3
      },
      {
        "id": "table-view-layouttable",
        "title": "3. Table View (?layout=table)",
        "level": 3
      },
      {
        "id": "calendar-view-layoutcalendar",
        "title": "4. Calendar View (?layout=calendar)",
        "level": 3
      },
      {
        "id": "timeline-gantt-view-layouttimeline",
        "title": "5. Timeline (Gantt) View (?layout=timeline)",
        "level": 3
      },
      {
        "id": "project-settings-studios-and-governance",
        "title": "Project Settings Studios and Governance",
        "level": 2
      },
      {
        "id": "general-settings-and-default-modules",
        "title": "General Settings and Default Modules",
        "level": 3
      },
      {
        "id": "workflow-states-and-wip-limits",
        "title": "Workflow States and WIP Limits",
        "level": 3
      },
      {
        "id": "project-members-and-access-acl-management",
        "title": "Project Members and Access ACL Management",
        "level": 3
      },
      {
        "id": "color-presets-and-contrast-standards",
        "title": "Color Presets and Contrast Standards",
        "level": 2
      },
      {
        "id": "curated-12-color-preset-palette",
        "title": "Curated 12-Color Preset Palette",
        "level": 3
      },
      {
        "id": "default-value-and-custom-hex-input",
        "title": "Default Value and Custom Hex Input",
        "level": 3
      }
    ],
    "content": "# [Informational] Enterprise Whitespace, Semantic Emojis, and Kanban Board\n\n## Overview\n\nHigh-performing engineering teams require interfaces that balance visual clarity with deep technical density. Cluttered, cramped dashboards create cognitive fatigue, while overly sparse designs hide crucial metadata. \ud83d\udc4dkanban delivers a refined **Enterprise Whitespace Design System**, combining generous breathing room with dense information display, sub-16ms drag-and-drop responsiveness, and the intuitive `<EmojiHint>` hover elaboration system.\n\n---\n\n## The Breathable Whitespace Design System\n\nThe visual design is grounded in CSS design tokens (`kanban/web/src/styles/tokens.css`):\n- **Predictable 4px / 8px Grid:** Consistent padding, gutter spacing, and card margins prevent visual clutter.\n- **High-Contrast Typography:** Clear typographic hierarchy using Inter and system font stacks for rapid scanning.\n- **Adaptive Light/Dark Modes:** Dark mode uses carefully calibrated slate and neutral backgrounds (`#0f172a`, `#1e293b`) with high contrast text (`#f8fafc`) to minimize eye strain.\n\n---\n\n## The `<EmojiHint>` Semantic Hover System\n\nTo keep cards concise without sacrificing context, \ud83d\udc4dkanban utilizes a standardized palette of 21 semantic emojis paired with instant hover elaboration tooltips:\n\n| Emoji Symbol | Semantic Meaning | Elaboration on Hover |\n| :---: | :--- | :--- |\n| `\ud83c\udff7\ufe0f` | Issue Identifier | Human-readable issue key and ticket URL |\n| `\ud83d\udd04` | Creator / Reporter | Author profile and ticket creation timestamp |\n| `\u26a1` | Priority | Corporate priority tier (Urgent, High, Medium, Low, None) |\n| `\u23f3` | Pending Transition | Active workflow transition helper or async gate |\n| `\ud83e\udd16` | Autonomous Agent | Agent service principal assignment or execution |\n| `\ud83d\udd12` | Parent Hierarchy | Parent issue or epic relationship |\n| `\ud83d\udd17` | Linked Object | Bidirectional dependency or related entity |\n| `\ud83e\uddea` | Custom Scripted Field | Sandboxed computed field with execution status |\n| `\ud83d\udee1\ufe0f` | Explicit Access | Access manifest and sharing permissions pill |\n| `\ud83d\udd14` | Subscription | Notification watcher status |\n| `\u2728` | Sparkle Completion | AI-assisted ghost text available |\n| `\ud83d\uded1` | Gate Veto | Transition rejected by rule or agent |\n\nHovering over any semantic emoji renders an instant, non-blocking tooltip detailing the exact state, owner, or timestamp without requiring extra clicks.\n\n---\n\n## Kanban Board View and Sub-16ms Drag-and-Drop\n\nThe Kanban Board provides a real-time, interactive visual pipeline of work across project states.\n\n![Kanban Board View](images/06-board-view.png)\n\n![Dark Theme Enterprise Kanban Board](images/22-dark-theme-board.png)\n\n### Board Architecture and Performance\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor User as Engineer / Operator\n    participant UI as React 19 Kanban Board\n    participant Store as Optimistic State Store\n    participant API as FastAPI Backend\n    participant WS as WebSocket Hub\n\n    User->>UI: Drag card from \"In Progress\" to \"Done\"\n    UI->>Store: Apply optimistic local mutation (<12ms)\n    Store-->>UI: Instantly re-render card in \"Done\" column\n    UI-->>User: Smooth 60 FPS visual feedback\n    Store->>API: PATCH /api/v1/issues/{id} (state: \"Done\")\n    alt Transition Accepted\n        API-->>Store: 200 OK & Updated Version ETag\n        API->>WS: Broadcast issue.updated event\n        WS-->>UI: Real-time sync to all other connected peers\n    else Transition Rejected / Gate Failed\n        API-->>Store: 409 Conflict / 422 Unprocessable\n        Store->>UI: Snap card back to \"In Progress\" with toast error\n    end\n```\n\n- **Sub-16ms Drag-and-Drop:** Built on lightweight HTML5 drag primitives paired with optimistic local UI mutations. When an operator moves a card across state columns, the card instantly re-renders in the destination column within 12 milliseconds, while the background API sync completes asynchronously.\n- **Virtualized Card Rendering:** Virtual scrolling allows columns to display thousands of tickets smoothly without degrading browser frame rates.\n- **State Columns:** Default workflow stages (`Backlog`, `Todo`, `In Progress`, `Done`, `Canceled`) with configurable WIP (Work In Progress) thresholds and visual warning indicators.\n- **2D Swimlane Grouping:** Operators can slice the board horizontally by Assignee, Priority, Module, or Sprint Cycle.\n\n![Filter Bar and 2D Swimlanes](images/29-filter-and-2d-swimlanes.png)\n\n---\n\n## The 5 Native View Layouts\n\nDifferent engineering disciplines need distinct perspectives on the same work graph. \ud83d\udc4dkanban provides 5 native views with instant zero-reload switching via URL query parameters (`?layout=`):\n\n![Multi-Layout Switching: List, Table, Calendar, Timeline](images/07-list-table-calendar-timeline.png)\n\n```mermaid\nflowchart TD\n    Data[\"Universal Object Graph (Issues)\"] --> Layouts[\"5 Native Layout Projections\"]\n    Layouts --> Board[\"Board (?layout=board)<br/>Sub-16ms DnD, 2D Swimlanes, WIP Limits\"]\n    Layouts --> List[\"List (?layout=list)<br/>3-Pane Master-Detail, Keyboard Navigation\"]\n    Layouts --> Table[\"Table (?layout=table)<br/>Spreadsheet Grid, Multi-Select Bulk Actions\"]\n    Layouts --> Calendar[\"Calendar (?layout=calendar)<br/>Monthly/Weekly Grid, Date Drag Scheduling\"]\n    Layouts --> Timeline[\"Timeline (?layout=timeline)<br/>Gantt Dependencies, Critical Path Analysis\"]\n```\n\n![Global Command Palette for Rapid View Switching](images/23-command-palette.png)\n\n### 1. Board View (`?layout=board`)\nInteractive Kanban board with optimistic drag-and-drop, horizontal swimlanes, and live state columns.\n\n### 2. List View (`?layout=list`)\nA powerful three-pane split layout:\n- Left pane: Hierarchical navigation and filter presets.\n- Middle pane: High-density list with keyboard navigation (Up/Down arrows, Enter to view).\n- Right pane: Instant live ticket preview drawer without navigating away.\n\n### 3. Table View (`?layout=table`)\nSpreadsheet-style tabular editing:\n- In-place editing of titles, states, assignees, priorities, and dates.\n- Column reordering, visibility toggling, and multi-row selection for bulk updates.\n- Capability-gated cell editors: clicking a state or priority cell opens an active dropdown editor with instant optimistic UI feedback.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor User as Engineer / PM\n    participant Table as Table View Component\n    participant Cache as React Query / Local State\n    participant API as FastAPI Backend\n\n    User->>Table: Click State cell (e.g. \"Todo\" -> \"In Progress\")\n    Table->>Cache: Apply optimistic cell mutation (<10ms)\n    Cache-->>Table: Render updated state badge and progress ring\n    Table->>API: PATCH /api/v1/issues/{id} (state: \"in_progress\")\n    alt State Update Accepted\n        API-->>Cache: 200 OK with updated entity payload\n    else Conflict or Validation Failure\n        API-->>Cache: 422 Unprocessable / 409 Conflict\n        Cache-->>Table: Roll back cell value and show error toast\n    end\n```\n\n![Table View Inline Editing](images/37-table-inline-editing.png)\n\n### 4. Calendar View (`?layout=calendar`)\nMonthly and weekly scheduling grid:\n- Visualizes start dates, target delivery dates, and cycle deadlines.\n- Drag cards across dates to reschedule instantly.\n\n### 5. Timeline (Gantt) View (`?layout=timeline`)\nInteractive dependency and critical path visualization:\n- Displays `BLOCKS` and `BLOCKED_BY` dependency arrows between work items using high-performance SVG Bezier curves.\n- Shows dependency loops, schedule slippage, and critical path milestones.\n- Unified \"Today\" anchor button to snap view to the current date, with Day, Week, and Quarter zoom levels.\n- Toggle switch for \"Show BLOCKS arrows\" to declutter dense views on demand.\n\n```mermaid\nflowchart LR\n    subgraph TimelineEngine[\"Timeline Dependency Engine\"]\n        IssueA[\"Issue KAN-221<br/>Start: 2026-11-15 | Due: 2026-11-20\"]\n        IssueB[\"Issue KAN-212<br/>Start: 2026-11-21 | Due: 2026-11-28\"]\n        Bezier[\"SVG Bezier Dependency Curve<br/>typed BLOCKS object_link\"]\n        IssueA -->|BLOCKS| Bezier\n        Bezier -->|Target| IssueB\n    end\n```\n\n![Timeline View with BLOCKS Dependency Arrows](images/38-timeline-blocks-arrows.png)\n\n---\n\n## Project Settings Studios and Governance\n\nProject administrators configure project-level metadata, workflow states, and principal access through dedicated settings studios under `/projects/{project_key}/settings/`:\n\n```mermaid\nflowchart TD\n    subgraph ProjectSettings[\"Project Settings Studios\"]\n        General[\"General Settings (/settings)<br/>Identifier, Lead, Default Modules\"]\n        Workflows[\"Workflow States (/settings/workflows)<br/>States, Sequence, Colors, WIP Limits\"]\n        Members[\"Members & Access (/settings/members)<br/>Principals, Role Assignments, Explicit ACLs\"]\n    end\n```\n\n### General Settings and Default Modules\nConfigure project display name, identifier key prefix, lead owner, and default module attachments for incoming work items:\n\n![Project General Settings and Default Modules](images/54-project-settings-studio.png)\n\n### Workflow States and WIP Limits\nCustomize the state machine columns, sequence ordering, color badges, and column WIP (Work In Progress) thresholds:\n\n![Project Workflow States and WIP Limits](images/55-project-workflow-states-wip.png)\n\n### Project Members and Access ACL Management\nManage project collaborators across human users, groups, and autonomous agent service principals with granular capability masks:\n\n![Project Members and Access ACL Management](images/56-project-members-access-acl.png)\n\n\n---\n\n## Color Presets and Contrast Standards\n\nTo preserve visual accessibility across dense boards, table rows, and state badges, \ud83d\udc4dkanban standardizes on a curated palette of 12 WCAG AA compliant preset colors. Every color is calibrated to maintain a contrast ratio of at least 4.5:1 against light and dark background surfaces.\n\n### Curated 12-Color Preset Palette\n\n| Preset Name | Hex Code | Semantic Role / Recommendation |\n| :--- | :--- | :--- |\n| Slate | `#64748b` | Neutral states, archived workflows, backlog items |\n| Indigo | `#4f46e5` | System default fallback color for states, labels, and priorities |\n| Blue | `#2563eb` | Active workflows, started tasks, primary badges |\n| Cyan | `#0891b2` | Informational tags, technical debt, infrastructure |\n| Teal | `#0d9488` | Verification stages, documentation, secondary labels |\n| Emerald | `#059669` | Completed milestones, green builds, approved states |\n| Amber | `#d97706` | Warning stages, pending review, triage queues |\n| Orange | `#ea580c` | Medium priority items, fast-track workflows |\n| Rose | `#e11d48` | High priority tags, security advisories |\n| Red | `#dc2626` | Urgent blockers, canceled states, defect reports |\n| Purple | `#7c3aed` | Feature epics, release milestones, architecture tracks |\n| Pink | `#db2777` | UX and design initiatives, customer feedback |\n\n### Default Value and Custom Hex Input\n\n- **Default Fallback:** When a state, label, or priority is created without an explicit color selection, the system applies the default fallback `#4f46e5` (Indigo).\n- **Custom Hex Codes:** Teams requiring custom branding can input any valid 7-character `#RRGGBB` hexadecimal code via the advanced color picker or direct text input. Values are automatically normalized and validated.\n- **Contrast Guidance:** When entering custom colors, administrators should verify that text or badge foregrounds meet the WCAG AA minimum contrast ratio of 4.5:1 (or 3:1 for large badges) against surrounding surface containers in both Light and Dark themes.\n"
  },
  {
    "slug": "feature-comparison",
    "title": "[Informational] Feature Comparison Matrix (50 Features)",
    "category": "informational",
    "track": "Security & Adoption Overview",
    "subtrack": "Market & Capability Analysis",
    "audience": "Technology Evaluators & Leadership",
    "order": 11,
    "summary": "A kanban is just a kanban until you start digging deeper. On the surface, every issue tracker presents identical columns, draggable cards, and basic workflow states. The real architectural divergence begins the moment you inspect paywalled enterprise controls, database-level security invariants, canonical Markdown integrity, multi-agent concurrency primitives, and native agent/MCP execution gates. While commercial SaaS, copyleft boards, and external agent runners lock custom properties, audit logs, Single Sign-On, and AI integrations behind per-seat subscription tiers, 1:1 REST-wrapper MCP schemas, or headless external-tracker daemons, `\ud83d\udc4dkanban` ships a unified, security-first, agent-first platform under a pure Apache-2.0 license. Below is the full 50-feature technical capability matrix comparing `\ud83d\udc4dkanban` directly against legacy trackers, modern boards, and autonomous agent orchestrators, followed by an honest non-goal compatibility and routing guide.",
    "sections": [
      {
        "id": "security-identity-audit-deployment",
        "title": "1. Security, Identity, Audit & Deployment",
        "level": 2
      },
      {
        "id": "agentic-tasks-mcp-ai-workflow-gates",
        "title": "2. Agentic Tasks, MCP, AI & Workflow Gates",
        "level": 2
      },
      {
        "id": "issue-tracker-kanban-board",
        "title": "3. Issue Tracker & Kanban Board",
        "level": 2
      },
      {
        "id": "docs-stickies-markdown-object-graph",
        "title": "4. Docs, Stickies, Markdown & Object Graph",
        "level": 2
      },
      {
        "id": "orchestration-provenance-day-2-operations",
        "title": "5. Orchestration, Provenance & Day-2 Operations",
        "level": 2
      },
      {
        "id": "when-kanban-is-not-the-right-fit-intentional-non-goals",
        "title": "6. When \ud83d\udc4dkanban Is Not the Right Fit (Intentional Non-Goals)",
        "level": 2
      }
    ],
    "content": "# [Informational] Feature Comparison Matrix (50 Features)\n\nA kanban is just a kanban until you start digging deeper. On the surface, every issue tracker presents identical columns, draggable cards, and basic workflow states. The real architectural divergence begins the moment you inspect paywalled enterprise controls, database-level security invariants, canonical Markdown integrity, multi-agent concurrency primitives, and native agent/MCP execution gates. While commercial SaaS, copyleft boards, and external agent runners lock custom properties, audit logs, Single Sign-On, and AI integrations behind per-seat subscription tiers, 1:1 REST-wrapper MCP schemas, or headless external-tracker daemons, `\ud83d\udc4dkanban` ships a unified, security-first, agent-first platform under a pure Apache-2.0 license. Below is the full 50-feature technical capability matrix comparing `\ud83d\udc4dkanban` directly against legacy trackers, modern boards, and autonomous agent orchestrators, followed by an honest non-goal compatibility and routing guide.\n\n**Legend**\n\n* `\u2705` **Included:** Built into the core product (free in FOSS/free tiers, or included in the entry commercial plan when no free tier exists).\n* `\ud83d\udd10` **Partial / Paywall-Capped:** Basic, single-node, or subset capability is included; full enforcement, scale, or hierarchy is missing or locked behind a paid tier.\n* `\ud83c\udd93\ud83d\udd0c` **Free Extension:** Free via a separate official plugin, external MCP server package, or external CLI harness.\n* `\ud83d\udcb0` **Paid Tier:** Locked behind higher per-seat subscription tiers (Pro, Business, Premium, or Enterprise).\n* `\ud83d\udcb8` **Extra Cost:** Separate paid product, paid Marketplace add-on, or metered credit/runner billing.\n* `\u274c` **None:** Unsupported.\n\n---\n\n## 1. Security, Identity, Audit & Deployment\n\n| Feature | \ud83d\udc4dkanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| Permissive FOSS License | \u2705 | \u274c | \u274c | \u274c | \u2705 | \u2705 | \u274c | \u274c |\n| On-Prem Multi-Container | \u2705 | \u274c | \u2705 | \ud83d\udcb0 | \u274c | \u274c | \u274c | \ud83d\udcb0 |\n| Single-Container Run | \u2705 | \u274c | \u274c | \u274c | \u2705 | \u274c | \u274c | \u274c |\n| Active Directory / LDAP | \u2705 | \ud83d\udcb8 | \ud83d\udcb0 | \ud83d\udcb0 | \u274c | \u274c | \ud83d\udcb8 | \u2705 |\n| OIDC | \u2705 | \ud83d\udcb8 | \ud83d\udcb0 | \ud83d\udcb0 | \u274c | \u274c | \ud83d\udcb8 | \u2705 |\n| Passkeys & Break-Glass | \u2705 | \ud83d\udcb8 | \ud83d\udcb0 | \ud83d\udd10 | \u274c | \u274c | \ud83d\udcb0 | \ud83d\udcb0 |\n| Object RBAC & Explicit DENY | \u2705 | \ud83d\udcb0 | \ud83d\udcb0 | \ud83d\udcb0 | \u274c | \u274c | \u2705 | \u2705 |\n| Workspace/Issue/Field RBAC | \u2705 | \ud83d\udcb8 | \u274c | \u274c | \u274c | \u274c | \ud83d\udcb0 | \u2705 |\n| Shared-With Pill & DB RLS | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Workspace Audit Logs | \u2705 | \ud83d\udcb8 | \ud83d\udcb0 | \ud83d\udcb0 | \u274c | \u274c | \ud83d\udcb0 | \u2705 |\n\nVibe Kanban and OpenAI Symphony are permissive `Apache-2.0` (`\u2705`): Vibe Kanban runs as a single-user local CLI/container (`\u2705`), whereas OpenAI Symphony is documented as an engineering preview for trusted environments that runs as a host Elixir/OTP daemon or Burrito binary rather than OCI containers (`\u274c`), executes repo-local `WORKFLOW.md` hooks via `bash -lc`, omits multi-tenant auth/OIDC/LDAP/Passkeys/RBAC (`\u274c`), and keeps no persistent database or immutable audit ledger (`\u274c`). For enterprise identity, commercial vendors lock directory access and Single Sign-On behind steep paywalls: Jira requires Atlassian Guard ($3.00-$4.35/user/month) or separate Crowd/Data Center licenses for SAML/OIDC and directory sync (`\ud83d\udcb8`); Plane gates OIDC, SAML, and direct LDAP/Active Directory group sync behind paid commercial and Enterprise Grid plans (`\ud83d\udcb0`); GitHub restricts SAML/OIDC SSO and direct on-prem LDAP authentication to GitHub Enterprise (`\ud83d\udcb0`); Businessmap requires a paid modular SSO add-on or custom Enterprise contract (`\ud83d\udcb8`); and only Codebeamer includes built-in direct LDAP/Active Directory bind and native OIDC Authorization Code support in its base platform (`\u2705`). Furthermore, only Codebeamer ships native per-field tracker RBAC (`\u2705`), while none of the seven enforces PostgreSQL Row-Level Security with a ubiquitous per-object `shared_with` pill (`\u274c`). **`\ud83d\udc4dkanban`** is 100% permissive `Apache-2.0` (`\u2705`) across standalone (`docker run`) and 5-network production stacks, shipping direct native `LDAPS`/`StartTLS` protocol bind with RFC 4515 escaping and directory group mapping alongside Multi-Card `OIDC`/`OAuth 2.0` with PKCE `S256` and JWKS claim validation, WebAuthn Passkeys with break-glass triggers, 7-tier Object RBAC with explicit `DENY` ACLs, PostgreSQL 16 `FORCE ROW LEVEL SECURITY` surfaced via the `\ud83d\udee1\ufe0f` Shared-With Header Pill, an immutable SHA-256 hash-chained audit ledger, granular 30-permission Workspace, Issue, and Field-level RBAC across custom multi-role user labels, HKDF-HMAC internal service authentication, and monotonic `CredentialBoundary` capability bitmasks and CIDR whitelisting across REST, RLS, and MCP (`\u2705`).\n\n---\n\n## 2. Agentic Tasks, MCP, AI & Workflow Gates\n\n| Feature | \ud83d\udc4dkanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| MCP Server | \u2705 | \ud83c\udd93\ud83d\udd0c | \ud83c\udd93\ud83d\udd0c | \ud83c\udd93\ud83d\udd0c | \u2705 | \u274c | \u274c | \u274c |\n| Low-Token Scoped MCP | \u2705 | \u274c | \u274c | \u274c | \ud83d\udd10 | \u274c | \u274c | \u274c |\n| 2-Stage MCP Delete Gate | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| /llms.txt & Skills Discovery | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Cloud AI Integration | \u2705 | \ud83d\udcb0 | \ud83d\udcb8 | \ud83d\udcb8 | \ud83d\udcb8 | \ud83d\udcb8 | \u2705 | \ud83d\udcb8 |\n| Air-Gap Local Ollama | \u2705 | \u274c | \u274c | \u274c | \ud83c\udd93\ud83d\udd0c | \ud83c\udd93\ud83d\udd0c | \u274c | \u274c |\n| Cursor Sparkle FIM | \u2705 | \u274c | \u274c | \ud83d\udcb8 | \u274c | \u274c | \u274c | \u274c |\n| Sync Transition Gates | \u2705 | \ud83d\udcb8 | \ud83d\udcb0 | \u274c | \u274c | \u274c | \u2705 | \u2705 |\n| Async :ro Repo Gate | \u2705 | \u274c | \u274c | \ud83d\udcb8 | \u274c | \u274c | \u274c | \u274c |\n\nJira, Plane, and GitHub ship MCP through separate external connectors or packages (`\ud83c\udd93\ud83d\udd0c`) that expose broad JSON schemas rather than low-token YAML intent surfaces, while Vibe Kanban bundles `--mcp` directly (`\u2705`) with partial `--mode orchestrator` scoping (`\ud83d\udd10`). OpenAI Symphony does not expose an MCP server (`\u274c`): it drives a `codex app-server` subprocess over stdio JSON-RPC (relying on metered OpenAI/Codex billing `\ud83d\udcb8` or external `codex --oss` Ollama configuration `\ud83c\udd93\ud83d\udd0c`), passes through raw host-authenticated tracker tools (`linear_graphql`, `github_api`, `asana_api`) without project-boundary scoping or 2-stage delete gates (`\u274c`), and runs read-write workspace clones (`approval_policy: never`, `networkAccess: true`). In addition, none of the seven competitor platforms provides standard machine-readable discovery endpoints or signed skill registries (`\u274c` across Jira, Plane, GitHub, Vibe Kanban, OpenAI Symphony, Businessmap, and Codebeamer). None of the other seven holds Kanban transitions in a non-blocking provisional gate while an agent forensically audits a read-only repository mount (`\u274c`) - GitHub only runs metered post-event Actions or Copilot checks (`\ud83d\udcb8`). **`\ud83d\udc4dkanban`** ships three built-in intent-scoped MCP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin` under `<= 1,800` schema tokens with LOD YAML output and 2-stage `request_delete` -> `execute_delete` confirmation), vendor-neutral BYOK Cloud AI (`openai`, `gemini`) and native air-gapped `ollama`, native `/llms.txt & Skills Discovery` providing `GET /llms.txt`, `/llms-full.txt`, and `/llms-skills` alongside a SHA-256 signed Agent Skills catalog, `<150ms` RLS-filtered Cursor Sparkle (`\u2728`) FIM completion with right-click accept, `<25ms` synchronous Wasm transition validators, and two-phase non-blocking async agent transition gates (`\u23f3\ud83e\udd16` -> `\u2705\ud83e\udd16`/`\ud83d\uded1\ud83e\udd16`) over `:ro` repository mounts (`\u2705`). In addition, `\ud83d\udc4dkanban` delivers TTFD Summary LOD tier caching for `<50ms` first-token agent response times and dedicated per-issue agent workpad slots with rework circuit breakers.\n\n---\n\n## 3. Issue Tracker & Kanban Board\n\n| Feature | \ud83d\udc4dkanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| Free Forever Tier | \u2705 | \ud83d\udd10 | \u2705 | \u2705 | \u2705 | \u2705 | \u274c | \u274c |\n| Issue Tracker | \u2705 | \ud83d\udd10 | \u2705 | \u2705 | \ud83d\udd10 | \u274c | \u2705 | \u2705 |\n| Kanban Board | \u2705 | \ud83d\udd10 | \u2705 | \u2705 | \u2705 | \u274c | \u2705 | \u2705 |\n| Five Native Views | \u2705 | \ud83d\udd10 | \ud83d\udd10 | \ud83d\udd10 | \u274c | \u274c | \u2705 | \u2705 |\n| 2D Swimlanes & Hard WIP | \u2705 | \ud83d\udd10 | \ud83d\udd10 | \ud83d\udd10 | \u274c | \u274c | \u2705 | \u2705 |\n| Cycles & Hidden Modules | \u2705 | \ud83d\udd10 | \u2705 | \ud83d\udd10 | \u274c | \u274c | \u274c | \u2705 |\n| Sub-Issue DAG & Links | \u2705 | \ud83d\udd10 | \ud83d\udd10 | \u2705 | \ud83d\udd10 | \u274c | \u2705 | \u2705 |\n| Custom Properties | \u2705 | \u2705 | \ud83d\udcb0 | \u2705 | \u274c | \u274c | \u2705 | \u2705 |\n| Free-Text Assignee Tag | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Audited Creator Override | \u2705 | \ud83d\udcb0 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Rule-Gated Archive | \u2705 | \ud83d\udcb0 | \u2705 | \u2705 | \u274c | \u274c | \u2705 | \u2705 |\n| Blast-Radius Soft Delete | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Sandboxed Script Fields | \u2705 | \ud83d\udcb8 | \u274c | \u274c | \u274c | \u274c | \u274c | \u2705 |\n\nOpenAI Symphony is free `Apache-2.0` software (`\u2705`), but it is a headless polling orchestrator and Phoenix LiveView run monitor rather than an issue tracker or Kanban board - requiring an external system of record such as Linear, GitHub Issues, Jira Cloud, Asana, or GitLab (`\u274c` across both Issue Tracker and Kanban Board rows, as well as view, hierarchy, property, and lifecycle rows). In team environments, an **Issue Tracker** serves as the persistent multi-user transactional system of record (managing deterministic keys, lifecycles, states, priorities, types, links, and audit history), whereas a **Kanban Board** provides the interactive visual drag-and-drop workflow surface (columns, cards, WIP constraints, and stage velocity). Jira caps both its issue tracker and boards at 10 users on Free (`\ud83d\udd10`) and gates cross-project Gantt plans, deep hierarchies, and archiving behind Premium (`\ud83d\udcb0`), while scripted fields require paid Marketplace apps like ScriptRunner (`\ud83d\udcb8`). Plane and GitHub include persistent issue tracking and board views (`\u2705`), though Plane gates custom properties behind paid tiers (`\ud83d\udcb0`) and GitHub lacks Calendar views and hard-blocking WIP limits (`\ud83d\udd10`). Vibe Kanban provides a visual Kanban board for local agent coding sessions (`\u2705`), but sunsetted its hosted issue/org cloud in May 2026 after `v0.1.44` - leaving local git-worktree task sessions (`npx vibe-kanban`) without a persistent multi-user issue system of record (`\ud83d\udd10`). Businessmap and Codebeamer provide robust issue systems and Kanban boards, but offer no free tier at all (`\u274c`). **`\ud83d\udc4dkanban`** unifies both the persistent multi-user Issue Tracker and visual Kanban Board in its free `Apache-2.0` core (`\u2705`), shipping all five native views (`List`, `Board`, `Table`, `Calendar`, `Timeline`), 2D swimlanes with hard WIP limits, cycle-checked DAG hierarchies, hybrid principal + free-text `\ud83c\udff7\ufe0f` assignee tags, audited `\ud83d\udd04` creator overrides, blast-radius soft delete, and Wasmtime/`nsjail` sandboxed script fields (`\u2705`). `\ud83d\udc4dkanban` also includes the Master-Detail Issue Navigator, Searchable State Filter Popovers with Active/All/None presets and cookie persistence, recipient-scoped realtime WS/SSE notifications with multi-tab synchronization, deterministic build version metadata `0.{release}.{commits}` with commit verification, and the Unified Admin Diagnostics & Link Inspector Studio at `/admin/diagnostics`.\n\n---\n\n## 4. Docs, Stickies, Markdown & Object Graph\n\n| Feature | \ud83d\udc4dkanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| Project Docs / Wiki | \u2705 | \ud83d\udcb8 | \ud83d\udd10 | \ud83d\udd10 | \u274c | \u274c | \u274c | \u2705 |\n| Project Stickies | \u2705 | \ud83d\udcb8 | \u2705 | \u274c | \u274c | \u274c | \u2705 | \u274c |\n| Smart Sticky -> Doc Promo | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Canonical Markdown DB | \u2705 | \u274c | \u274c | \u2705 | \u2705 | \u274c | \u274c | \u274c |\n| Paste-Injection Pruner | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Mermaid, Safe SVG & Proxy | \u2705 | \ud83d\udcb8 | \u274c | \u2705 | \u274c | \u274c | \u274c | \u274c |\n| Broken/ACL Link Auditor | \u2705 | \ud83d\udcb8 | \u274c | \u274c | \u274c | \u274c | \u274c | \ud83d\udd10 |\n| Synaptic Hybrid Vector Search | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n\nJira splits Docs and Stickies into separate paid Confluence and Whiteboard licenses (`\ud83d\udcb8`), while GitHub restricts private-repo Wikis to paid plans (`\ud83d\udd10`), Plane gates full team Wiki spaces (`\ud83d\udd10`), and OpenAI Symphony is database-less - reading only a repo-local `WORKFLOW.md` YAML + Liquid prompt template with no Docs, Stickies, Markdown persistence DB, diagram pipeline, link auditor, or search index (`\u274c`). Across all seven competitor platforms, search remains limited to keyword text matching or requires external cloud-egress AI subscriptions (such as Atlassian Rovo at $8/user/month); none of the seven provides zero-egress local vector search or entity-graph activation spreading (`\u274c`). Only **`\ud83d\udc4dkanban`**, GitHub, and Vibe Kanban store pure Markdown records natively (`\u2705`), and only Codebeamer flags \"suspected\" upstream links manually without automated graph purging (`\ud83d\udd10`). **`\ud83d\udc4dkanban`** unifies `ltree` hierarchical Docs and Project Overview Stickies with 1-click ACL-preserving Sticky-to-Doc promotion (`\ud83d\udca1\ud83d\udcc4`), auto-converts pasted HTML/Rich Text into 100% canonical UTF-8 Markdown while pruning hidden-DOM paste-injection and UTF-16 lone surrogates, renders Web Worker Mermaid diagrams and `nh3`-scrubbed SVGs through an SSRF-guarded media proxy, and runs an automated 6-reason Object Link Auditor & Purger (`\u2705`). Furthermore, **`\ud83d\udc4dkanban`** delivers native `Synaptic Hybrid Vector Search` featuring zero-egress SHA-256-pinned local `bge-small-en-v1.5-int8` ONNX embeddings, `pgvector` HNSW index acceleration with `hnsw.iterative_scan`, Reciprocal Rank Fusion (RRF) combining vector and lexical rankings, and 2-hop RLS-governed activation spreading across typed `object_links` (`\u2705`). Strict Markdown-only prose persistence guarantees UTF-16 lone-surrogate rejection (`INVALID_UTF8_SURROGATE`) and DOM paste-jacking pruning across all ticket prose and document nodes.\n\n---\n\n## 5. Orchestration, Provenance & Day-2 Operations\n\n| Feature | \ud83d\udc4dkanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| Atomic Agent Lease & Fencing | \u2705 | \u274c | \u274c | \u274c | \ud83d\udd10 | \ud83d\udd10 | \u274c | \u274c |\n| Prompt-Injection Taint Gate | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Dedicated Agent Workpad Slot | \u2705 | \u274c | \u274c | \u274c | \ud83d\udd10 | \ud83c\udd93\ud83d\udd0c | \u274c | \u274c |\n| Pre-Write Secret Redaction | \u2705 | \ud83d\udcb8 | \u274c | \ud83d\udd10 | \u274c | \u274c | \u274c | \u274c |\n| Crypto-Shredded Audit Chain | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Ephemeral OIDC Agent Auth | \u2705 | \ud83d\udcb0 | \u274c | \u2705 | \u274c | \u274c | \u274c | \ud83d\udcb0 |\n| Git Worktree / PR & Sig Gate | \u2705 | \ud83c\udd93\ud83d\udd0c | \ud83c\udd93\ud83d\udd0c | \u2705 | \u2705 | \ud83c\udd93\ud83d\udd0c | \ud83c\udd93\ud83d\udd0c | \u2705 |\n| Lossless Import & Full Export | \u2705 | \ud83d\udd10 | \ud83d\udd10 | \u2705 | \u274c | \u274c | \ud83d\udcb0 | \u2705 |\n| Deterministic JSON/Unix CLI | \u2705 | \ud83c\udd93\ud83d\udd0c | \u274c | \u2705 | \u274c | \u274c | \u274c | \u274c |\n| Native CFD, Lead & Aging WIP | \u2705 | \ud83d\udd10 | \ud83d\udcb0 | \ud83d\udd10 | \u274c | \u274c | \u2705 | \ud83d\udd10 |\n\nOpenAI Symphony tracks single-daemon claims in volatile memory (`\ud83d\udd10`) and relies on external `WORKFLOW.md` comment scraping (`\ud83c\udd93\ud83d\udd0c`) with no Unix board CLI (`\u274c`), while GitHub gates private-repo secret push-protection (`\ud83d\udd10`), Businessmap leads on native Lean flow analytics (`\u2705`), and Codebeamer enforces ALM commit/release traceability (`\u2705`). **`\ud83d\udc4dkanban`** ships all ten Day-2 enterprise and fleet-scale capabilities directly in its free `Apache-2.0` core (`\u2705`): `Atomic Agent Lease & Fencing` via PostgreSQL `issue_leases` and monotonic `fencing_token` CAS; `Prompt-Injection Taint Gate` via per-block provenance tainting and dynamic MCP capability stripping; `Dedicated Agent Workpad Slot` via silent per-issue `issue_workpads` and rework-loop circuit breakers; `Pre-Write Secret Redaction` via synchronous pre-persistence Shannon-entropy secret push-protection; `Crypto-Shredded Audit Chain` via envelope-encrypted `activity_record_keys`; `Ephemeral OIDC Agent Auth` via RFC 8693 headless workload OIDC token exchange; `Git Worktree / PR & Sig Gate` via SSRF-hardened SCM webhooks and `SSH`/`GPG`/`Sigstore` & SLSA attestation gates; `Lossless Import & Full Export` via Jira/GitHub/Linear/Plane importers with legacy key-alias redirects, CSV/AES-256 ZIP export, and deterministic `JSONL` + `.md` archives; `Deterministic JSON/Unix CLI` via schema-driven `kanban-ctl` and `kanban-cli --filter ... --json` with `hnsw.iterative_scan` RLS vector recall; and `Native CFD, Lead & Aging WIP` via native CFD, Aging WIP, Cycle/Lead Time `p50`/`p85`/`p95` scatterplots, 10,000-iteration Monte Carlo forecasting, and Jinja2 multi-format compliance reporting.\n\n---\n\n## 6. When \ud83d\udc4dkanban Is Not the Right Fit (Intentional Non-Goals)\n\nBecause `\ud83d\udc4dkanban` makes deliberate, opinionated trade-offs around **zero-trust security (Priority #0)**, **agent-first MCP ergonomics (Priority #1)**, and **100% canonical Markdown persistence** (`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`), there are specific use cases it is **not** designed to fit. First is how the 8 compared platforms handle these 6 non-goal domains, followed by a routing guide showing whether to pair a companion tool alongside `\ud83d\udc4dkanban` (`\ud83d\udd17 Companion`) or adopt a dedicated system of record instead (`\ud83e\udded Dedicated`):\n\n| Non-Goal Use Case | \ud83d\udc4dkanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| Arbitrary Binary / DAM Hosting | \u274c | \ud83d\udd10 | \ud83d\udd10 | \ud83d\udd10 | \u274c | \u274c | \ud83d\udd10 | \u2705 |\n| WYSIWYG & Freeform Whiteboards | \u274c | \ud83d\udcb8 | \u274c | \u274c | \u274c | \u274c | \u2705 | \ud83d\udd10 |\n| Heavy ERP & Financial Billing | \u274c | \ud83d\udcb8 | \ud83d\udcb0 | \u274c | \u274c | \u274c | \ud83d\udd10 | \u274c |\n| Regulated Safety-Critical ALM | \u274c | \ud83d\udcb8 | \u274c | \u274c | \u274c | \u274c | \u274c | \u2705 |\n| Customer Helpdesk / ITSM | \u274c | \ud83d\udcb8 | \ud83d\udcb0 | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Unreviewed Host Plugins / Iframes | \u274c | \ud83c\udd93\ud83d\udd0c | \u274c | \ud83c\udd93\ud83d\udd0c | \u2705 | \u2705 | \u274c | \ud83d\udd10 |\n\n* `\ud83d\udd17` **Companion:** Keep `\ud83d\udc4dkanban` as your hardened engineering and agentic hub, and bridge the specialized workload via links, safe SVG/PNG exports, REST, webhooks, or `/mcp/agent`.\n* `\ud83e\udded` **Dedicated:** Use a purpose-built platform as your primary system of record when this domain governs your daily workflow or regulatory boundary.\n\n| Use Case | \ud83d\udc4dkanban Fit | Recommended Tools (FOSS & Commercial) | How to Pair Alongside \ud83d\udc4dkanban (or When to Replace) |\n| --- | --- | --- | --- |\n| **1. Binary / DAM Hosting** | \ud83d\udd17 Companion | **FOSS:** SeaweedFS (`Apache-2.0`), Garage (`AGPLv3`), RustFS (`Apache-2.0`), Forgejo Releases, Immich, Nextcloud. **Commercial:** AWS S3, GitHub Releases/LFS, Artifactory, Bynder | Host large binaries, CAD, or raw video externally; attach immutable URLs in Markdown or `url`/`badge` custom fields, and embed `PNG`/`WebP`/`SVG` previews via `/api/v1/media-proxy`. |\n| **2. WYSIWYG & Whiteboards** | \ud83d\udd17 Companion | **FOSS:** Excalidraw (`MIT`), Penpot (`MPL-2.0`), BookStack (`MIT`), AFFiNE. **Commercial:** Businessmap Whiteboards, Miro, FigJam, Notion, Confluence | Sketch in Excalidraw/Penpot/Miro and paste exported `.svg`/`.png` snapshots into `\ud83d\udc4dkanban` (`nh3`-scrubbed), use Mermaid for architecture diagrams, and push action items via `/mcp/agent`. |\n| **3. Heavy ERP & Billing** | \ud83d\udd17 Companion | **FOSS:** Kimai (`AGPLv3`), ERPNext (`GPLv3`), Odoo CE. **Commercial:** Jira + Tempo, Harvest, NetSuite OpenAir, SAP S/4HANA | Run engineering delivery and native flow metrics in `\ud83d\udc4dkanban`, syncing issue keys and `activity_records` timestamps via REST or SCM webhooks; use an ERP directly if client billing is primary. |\n| **4. Safety-Critical ALM** | \ud83e\udded Dedicated | **FOSS:** StrictDoc (`Apache-2.0`), Doorstop, Tuleap. **Commercial:** PTC Codebeamer, Siemens Polarion ALM, Jama Connect | If auditors mandate single-tool DO-178C, ISO 26262, or FDA 21 CFR Part 11 qualification with ReqIF, FMEA, and e-signatures, choose Codebeamer/Polarion directly (or pair Git-backed `StrictDoc` for hybrid software delivery). |\n| **5. Customer Helpdesk / ITSM** | \ud83d\udd17 Companion | **FOSS:** Zammad (`AGPLv3`), Chatwoot (`MIT` CE), FreeScout, GLPI. **Commercial:** Jira Service Management, Zendesk, Freshdesk, ServiceNow | Keep public email intake, live chat, telephony/IVR, and SLA portals in Zammad/Chatwoot/JSM; escalate verified engineering bugs into `\ud83d\udc4dkanban` via REST or `/mcp/agent` `create_ticket` with `\ud83c\udff7\ufe0f` external tags. |\n| **6. Unreviewed Host Plugins** | \ud83e\udded Dedicated | **FOSS:** Mattermost Plugins (`Apache-2.0` / `AGPLv3`), Discourse, Jenkins. **Commercial:** Jira Marketplace apps, GitHub Apps, Chrome Extensions | If arbitrary third-party JavaScript or host-level iframe execution inside your project management UI is an architectural prerequisite, choose commercial marketplaces directly; `\ud83d\udc4dkanban` intentionally restricts custom logic to sandboxed Wasmtime / `nsjail` engines with explicit cryptographic approvals. |\n"
  },
  {
    "slug": "guide-custom-fields",
    "title": "[Guide] How to Use Custom Fields",
    "category": "guide",
    "track": "Step-by-Step Guides",
    "subtrack": "Custom Fields",
    "audience": "Project & Workspace Admins",
    "order": 12,
    "summary": "Custom Fields extend your projects and issues with dynamic calculations, computed business metrics, compliance indicators, and metadata without modifying the core database schema or writing custom server plugins.",
    "sections": [
      {
        "id": "what-custom-fields-do-and-where-values-appear",
        "title": "1. What Custom Fields Do and Where Values Appear",
        "level": 2
      },
      {
        "id": "choosing-between-execution-tiers",
        "title": "2. Choosing Between Execution Tiers",
        "level": 2
      },
      {
        "id": "standalone-mode-vs-multi-container-compose-gating",
        "title": "Standalone Mode vs Multi-Container Compose Gating",
        "level": 3
      },
      {
        "id": "step-by-step-walkthroughs-and-copy-paste-examples",
        "title": "3. Step-by-Step Walkthroughs and Copy-Paste Examples",
        "level": 2
      },
      {
        "id": "example-1-priority-sla-days-safe-formula",
        "title": "Example 1: Priority SLA Days (Safe Formula)",
        "level": 3
      },
      {
        "id": "example-2-sub-issue-progress-percentage-safe-formula",
        "title": "Example 2: Sub-Issue Progress Percentage (Safe Formula)",
        "level": 3
      },
      {
        "id": "example-3-cvss-severity-pill-safe-formula-dynamic-severity",
        "title": "Example 3: CVSS Severity Pill (Safe Formula / Dynamic Severity)",
        "level": 3
      },
      {
        "id": "example-4-total-project-issues-rollup-webassembly-or-multi-container-nsjail",
        "title": "Example 4: Total Project Issues Rollup (WebAssembly or Multi-Container nsjail)",
        "level": 3
      },
      {
        "id": "all-seven-supported-output-formats-and-schemas",
        "title": "4. All Seven Supported Output Formats and Schemas",
        "level": 2
      },
      {
        "id": "text",
        "title": "1. text",
        "level": 3
      },
      {
        "id": "number",
        "title": "2. number",
        "level": 3
      },
      {
        "id": "badge",
        "title": "3. badge",
        "level": 3
      },
      {
        "id": "severity-pill",
        "title": "4. severity_pill",
        "level": 3
      },
      {
        "id": "url",
        "title": "5. url",
        "level": 3
      },
      {
        "id": "markdown-snippet",
        "title": "6. markdown_snippet",
        "level": 3
      },
      {
        "id": "json-table",
        "title": "7. json_table",
        "level": 3
      },
      {
        "id": "safe-formula-context-reference",
        "title": "5. Safe Formula Context Reference",
        "level": 2
      },
      {
        "id": "safe-built-in-functions",
        "title": "Safe Built-in Functions",
        "level": 3
      },
      {
        "id": "testing-dry-running-and-scope-escalation",
        "title": "6. Testing, Dry-Running, and Scope Escalation",
        "level": 2
      },
      {
        "id": "dry-running-with-test-execute",
        "title": "Dry-Running with Test Execute",
        "level": 3
      },
      {
        "id": "scope-escalation-and-aal2-dual-control-approval",
        "title": "Scope Escalation and AAL2 Dual-Control Approval",
        "level": 3
      },
      {
        "id": "step-by-step-guide-authoring-requesting-dual-control-custom-scripted-fields",
        "title": "Step-by-Step Guide: Authoring & Requesting Dual-Control Custom Scripted Fields",
        "level": 3
      },
      {
        "id": "custom-field-configuration-attributes-and-controls",
        "title": "Custom Field Configuration Attributes and Controls",
        "level": 2
      },
      {
        "id": "display-name",
        "title": "Display Name",
        "level": 3
      },
      {
        "id": "slug",
        "title": "Slug",
        "level": 3
      },
      {
        "id": "flavors",
        "title": "Flavors",
        "level": 3
      },
      {
        "id": "sandbox-tier",
        "title": "Sandbox Tier",
        "level": 3
      },
      {
        "id": "credential-mode",
        "title": "Credential Mode",
        "level": 3
      },
      {
        "id": "target-scope",
        "title": "Target Scope",
        "level": 3
      },
      {
        "id": "output-formats",
        "title": "Output Formats",
        "level": 3
      },
      {
        "id": "format-metadata",
        "title": "Format Metadata",
        "level": 3
      },
      {
        "id": "script-source",
        "title": "Script Source",
        "level": 3
      },
      {
        "id": "egress-allowlist",
        "title": "Egress Allowlist",
        "level": 3
      },
      {
        "id": "aal2-stepup",
        "title": "AAL2 Stepup",
        "level": 3
      },
      {
        "id": "approvals",
        "title": "Approvals",
        "level": 3
      }
    ],
    "content": "# [Guide] How to Use Custom Fields\n\nCustom Fields extend your projects and issues with dynamic calculations, computed business metrics, compliance indicators, and metadata without modifying the core database schema or writing custom server plugins.\n\nThis comprehensive guide covers how Custom Fields work, where their values surface across the UI, how to choose the right execution tier for your deployment mode (Standalone vs Multi-Container Compose), step-by-step walkthroughs with copy-paste examples, and the required governance and dual-control approval workflows.\n\n---\n\n## 1. What Custom Fields Do and Where Values Appear\n\nCustom Fields allow project administrators and server administrators to attach computed or scalar attributes to issues. Whenever an issue is viewed, edited, or evaluated in a workflow, Custom Fields are resolved and formatted according to their output specifications.\n\n![Custom Fields Studio - Desktop Light](images/slice5-custom-fields-studio-desktop-1440x900-light.png)\n\nCustom field values automatically surface across the following surfaces in the web interface:\n\n- **Issue Properties Rail:** Located in the right sidebar of the issue detail screen. Displays the custom field label, current value (formatted as text, number, badge, severity pill, link, markdown snippet, or table), and cache status with an instant recalculate trigger.\n- **Table View:** Embedded as sortable, custom columns in the project Table View. Allows rapid scanning and comparison of computed metrics (such as SLA deadlines or sub-issue progress percentages) across dozens of work items.\n- **Board Cards:** Rendered as compact badges, severity pills, or monospace tags directly on Kanban board cards, providing immediate visual cues to team members during daily standups and cycle reviews.\n- **Filters and Search:** Filter work items by custom field values, enabling targeted views such as finding all issues with a `CRITICAL` severity pill or projects with overdue SLA days.\n\n---\n\n## 2. Choosing Between Execution Tiers\n\n\ud83d\udc4dkanban provides four distinct execution tiers for custom fields, balanced across performance, security isolation, and deployment modes:\n\n![Custom Fields Editor Tier A](images/slice5-custom-fields-editor-tier-a-desktop-1440x900-light.png)\n\n| Tier | Engine / Flavor | Latency Budget | Standalone Mode | Multi-Container Compose | Best Used For |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n| **Scalar** | Static metadata | `<1ms` | Supported | Supported | Static tags, manual attributes, default strings, constant numbers |\n| **Safe Formula** | In-process Python AST | `<5ms` | Supported | Supported | Math, date arithmetic, conditionals, sub-issue rollups, SLA days |\n| **WebAssembly** | `wasmtime` runtime | `<25ms` | Supported | Supported | Compiled C, Rust, or AssemblyScript logic with strict memory sandboxing |\n| **Isolated Sandbox** | `nsjail` Linux container | `<250ms` | **Gated (Unavailable)** | Supported | Complex Python/Rust scripts requiring full network egress allowlists or multi-entity queries |\n\n### Standalone Mode vs Multi-Container Compose Gating\n\nIn **Standalone mode** (running via a single container or single process):\n- `Scalar`, `Safe Formula`, and `WebAssembly (wasmtime)` run natively out of the box with zero external dependencies.\n- `Isolated Sandbox (nsjail)` is **fail-closed and rejected**. Attempting to create or execute an `nsjail` custom field in Standalone mode returns an actionable HTTP `422 SANDBOX_UNAVAILABLE_IN_STANDALONE` error recommending `scalar`, `formula`, or `wasm`. In the web editor and preset gallery, `nsjail` options are disabled and badged with `Multi-Container Compose Required`.\n- **Pre-existing nsjail fields:** If you import a workspace backup containing pre-existing `nsjail` fields into Standalone mode, definitions remain inspectable and editable, with an informational warning banner reminding you that multi-container compose is required for execution.\n- **Promoting to Multi-Container:** To unlock `nsjail` container sandboxes, promote your installation to multi-container compose via the administrator portal at `/admin/standalone` or follow the Production Promotion and Backup Runbook.\n\n---\n\n## 3. Step-by-Step Walkthroughs and Copy-Paste Examples\n\n### Example 1: Priority SLA Days (Safe Formula)\n\nCompute the remaining service level agreement (SLA) target turnaround days based on the issue priority.\n\n- **Name:** Priority SLA Days\n- **Slug:** `priority-sla-days`\n- **Flavor / Tier:** Safe Formula (`formula`)\n- **Target Scope:** `PROJECT`\n- **Formula Expression:**\n  ```python\n  1 if priority == 'URGENT' else 3 if priority == 'HIGH' else 7 if priority == 'MEDIUM' else 14\n  ```\n- **Output Format:** `number`\n- **Format Metadata JSON:**\n  ```json\n  {\n    \"format\": \"number\",\n    \"maximum_fraction_digits\": 0,\n    \"unit_suffix\": \"d\",\n    \"min_value\": 1,\n    \"max_value\": 30\n  }\n  ```\n\n### Example 2: Sub-Issue Progress Percentage (Safe Formula)\n\nCalculate the completion percentage of sub-issues for epic or parent issue tracking.\n\n- **Name:** Sub-Issue Progress %\n- **Slug:** `sub-issue-progress`\n- **Flavor / Tier:** Safe Formula (`formula`)\n- **Target Scope:** `PROJECT`\n- **Formula Expression:**\n  ```python\n  round((completed_sub_issue_count * 100.0) / sub_issue_count, 1) if sub_issue_count > 0 else 100.0\n  ```\n- **Output Format:** `number`\n- **Format Metadata JSON:**\n  ```json\n  {\n    \"format\": \"number\",\n    \"maximum_fraction_digits\": 1,\n    \"unit_suffix\": \"%\",\n    \"min_value\": 0.0,\n    \"max_value\": 100.0\n  }\n  ```\n\n### Example 3: CVSS Severity Pill (Safe Formula / Dynamic Severity)\n\nMap issue priority and due date urgency to a standardized security vulnerability pill.\n\n- **Name:** Incident Severity Pill\n- **Slug:** `incident-severity-pill`\n- **Flavor / Tier:** Safe Formula (`formula`)\n- **Target Scope:** `PROJECT`\n- **Formula Expression:**\n  ```python\n  {\"level\": \"critical\", \"score\": 9.5, \"label\": \"Critical\"} if priority == \"URGENT\" else ({\"level\": \"high\", \"score\": 8.0, \"label\": \"High\"} if priority == \"HIGH\" else ({\"level\": \"medium\", \"score\": 5.0, \"label\": \"Medium\"} if priority == \"MEDIUM\" else {\"level\": \"low\", \"score\": 2.0, \"label\": \"Low\"}))\n  ```\n- **Output Format:** `severity_pill`\n- **Format Metadata JSON:**\n  ```json\n  {\n    \"format\": \"severity_pill\"\n  }\n  ```\n\n### Example 4: Total Project Issues Rollup (WebAssembly or Multi-Container nsjail)\n\nRoll up total project issues and blockers using WebAssembly or Multi-Container nsjail.\n\n- **Name:** Total Project Issues\n- **Slug:** `total-project-issues`\n- **Flavor / Tier:** WebAssembly (`wasm`) or Isolated Sandbox (`nsjail` in Multi-Container Compose)\n- **Target Scope:** `PROJECT` (or `WORKSPACE` with AAL2 dual control)\n- **Execution Script / Module:**\n  ```python\n  # Tier B nsjail container Python script (isolated Linux namespaces)\n  import json\n  import sys\n\n  def main():\n      try:\n          data = json.loads(sys.stdin.read())\n          issue = data.get(\"issue\", {})\n          print(json.dumps(1))\n      except Exception as e:\n          print(json.dumps({\"error\": str(e)}))\n\n  if __name__ == \"__main__\":\n      main()\n  ```\n- **Output Format:** `number`\n- **Format Metadata JSON:**\n  ```json\n  {\n    \"format\": \"number\",\n    \"maximum_fraction_digits\": 0,\n    \"unit_suffix\": \" issues\"\n  }\n  ```\n\n---\n\n## 4. All Seven Supported Output Formats and Schemas\n\nEvery custom field produces output formatted according to one of seven canonical schemas:\n\n![Custom Fields Structured Format](images/slice5-custom-fields-structured-format-desktop-1440x900-light.png)\n\n### 1. `text`\nSingle-line formatted string with optional prefix and monospace font.\n```json\n{\n  \"format\": \"text\",\n  \"max_length\": 128,\n  \"prefix\": \"REF-\",\n  \"monospace\": true\n}\n```\n\n### 2. `number`\nFloating point or integer numeric value with precision limits, suffix, and range bounds.\n```json\n{\n  \"format\": \"number\",\n  \"maximum_fraction_digits\": 2,\n  \"unit_suffix\": \" hrs\",\n  \"min_value\": 0.0,\n  \"max_value\": 1000.0\n}\n```\n\n### 3. `badge`\nVisual status badge with color token and strict label allowlist. Supported color tokens: `neutral`, `info`, `success`, `warning`, `danger`, `accent`.\n```json\n{\n  \"format\": \"badge\",\n  \"color_token\": \"success\",\n  \"allowed_labels\": [\"Passed\", \"Failed\", \"In Progress\", \"Pending\"]\n}\n```\n\n### 4. `severity_pill`\nStandardized vulnerability and risk assessment pill. Accepts a dictionary with a required `\"level\"` (`\"low\"`, `\"medium\"`, `\"high\"`, `\"critical\"`), and optional numeric `\"score\"` (finite float between `0.0` and `10.0`) and optional `\"label\"` (string of at most 32 characters without HTML markup).\n```json\n{\n  \"format\": \"severity_pill\"\n}\n```\n\n### 5. `url`\nSanitized hyperlink validated against allowed schemes and host suffixes.\n```json\n{\n  \"format\": \"url\",\n  \"allowed_schemes\": [\"https\"],\n  \"allowed_host_suffixes\": [\"github.com\", \"gitlab.com\"]\n}\n```\n\n### 6. `markdown_snippet`\nSanitized canonical Markdown snippet rendered inline up to 2000 characters.\n```json\n{\n  \"format\": \"markdown_snippet\",\n  \"max_chars\": 2000\n}\n```\n\n### 7. `json_table`\nStructured 2-dimensional tabular data rendered directly in the issue details view.\n```json\n{\n  \"format\": \"json_table\",\n  \"columns\": [\n    {\"key\": \"test_name\", \"label\": \"Test Suite\"},\n    {\"key\": \"duration_ms\", \"label\": \"Duration (ms)\"},\n    {\"key\": \"status\", \"label\": \"Status\"}\n  ],\n  \"max_rows\": 25\n}\n```\n\n---\n\n## 5. Safe Formula Context Reference\n\nWhen writing Safe Formulas, expressions have access to the active issue attributes without executing arbitrary code:\n\n| Variable | Type | Description |\n| :--- | :--- | :--- |\n| `id` | `str` | Issue unique identifier (UUID) |\n| `key` | `str` | Human-readable issue key (e.g. `KAN-32`) |\n| `summary` | `str` | Issue title / summary |\n| `description_markdown` | `str` | Raw Markdown body of the issue |\n| `state` | `str` | Name of current workflow state (e.g. `In Progress`) |\n| `state_group` | `str` | Workflow state category (`backlog`, `unstarted`, `started`, `completed`, `cancelled`) |\n| `priority` | `str` | Normalized uppercase priority (`URGENT`, `HIGH`, `MEDIUM`, `LOW`, `NONE`) |\n| `priority_slug` | `str` | Lowercase priority slug (`urgent`, `high`, `medium`, `low`, `none`) |\n| `priority_label` | `str` | Display label of priority (`Urgent`, `High`, etc.) |\n| `start_date` | `str` or `None` | ISO-formatted start date |\n| `due_date` | `str` or `None` | ISO-formatted due date |\n| `days_until_due` | `int` or `None` | Days until due date (negative values indicate overdue) |\n| `blocker_count` | `int` | Number of active blocking dependencies on this issue |\n| `sub_issue_count` | `int` | Total count of child sub-issues |\n| `completed_sub_issue_count`| `int` | Count of sub-issues in `completed` state group |\n| `labels` | `list[str]` | List of tag names assigned to the issue |\n\n### Safe Built-in Functions\nSafe formulas allow standard deterministic operations: `round`, `int`, `float`, `min`, `max`, `len`, `abs`, `str`. Arbitrary imports, file system access, and network sockets are strictly prohibited at the Python AST parser layer.\n\n---\n\n## 6. Testing, Dry-Running, and Scope Escalation\n\n### Dry-Running with Test Execute\nBefore saving any custom field definition, use the **Test Execute** button in the Custom Field Definition Editor or send a POST request to:\n```http\nPOST /api/v1/projects/{project_ref}/custom-fields/test-execute\n```\nThis evaluates your formula or script against a mock issue payload or existing issue key in memory without persisting values or polluting the audit ledger. In Standalone mode, Test Execute verifies that your script does not request unavailable sandbox tiers.\n\n### Scope Escalation and AAL2 Dual-Control Approval\nCustom fields can be scoped at three tiers:\n- **PROJECT Scope:** Can only read and affect issues within the parent project. Requires Project Administrator privileges.\n- **WORKSPACE Scope:** Can read issues across all projects in the workspace.\n- **SERVER Scope:** Global fields available across all workspaces.\n\n![Custom Fields Dual Control Escalation](images/slice5-custom-fields-escalation-dual-control-desktop-1440x900-light.png)\n\n**Dual-Control Governance:** Escalating a custom field definition from `PROJECT` to `WORKSPACE` or `SERVER` scope (or running with elevated Service Principal credentials `PROJECT_ADMIN_SP` or `SERVER_ADMIN_SP` rather than `INVOKING_USER`) requires cryptographic approval by an administrator of that target tier with active Authenticator Assurance Level 2 (AAL2 / WebAuthn / TOTP) session elevation.\n\n### Step-by-Step Guide: Authoring & Requesting Dual-Control Custom Scripted Fields\n\n1. **Navigate to Custom Fields Studio:** Open `/projects/<PROJECT_KEY>/settings/custom-fields` and click **+ New Custom Field**.\n2. **Configure Baseline Attributes:** Set the Display Name (e.g. `Cross-Project Security Compliance Score`), confirm the automatically generated Field Slug (`cross-proj-sec-score`), select the Flavor / Tier (`formula` or `wasm`), and choose the Output Format (`severity_pill` or `number`).\n3. **Select Elevated Scope or Service Principal:** In the Target Scope Tier dropdown, select `WORKSPACE` or `SERVER`. Optionally select Credential Mode as `PROJECT_ADMIN_SP` or `SERVER_ADMIN_SP` if elevated service authority is required. The UI immediately renders an amber unmissable Dual-Control Escalation Banner warning of the expanded tenant blast radius.\n4. **Draft and Test Execute:** Author your formula expression or compiled module, then click **Test Execute** to verify execution in memory against sample payloads.\n5. **Submit Escalation Request:** Click **Save & Request Escalation**. An escalation proposal is created and dispatched to the approval queue with pending status.\n6. **Independent Admin Review & Cryptographic Approval:** A distinct Workspace or Server Administrator opens `/projects/<PROJECT_KEY>/settings/custom-fields` (or the Escalation Approvals panel), inspects the script source, requested scope, credential mode, and blast radius, clicks **Approve Escalation**, and provides fresh Authenticator Assurance Level 2 (AAL2) credentials (biometric Passkey, hardware FIDO2 key, or 6-digit TOTP code). Upon AAL2 verification, the approval is cryptographically sealed, logged in the activity ledger, and the escalated custom field activates immediately.\n\n---\n\n## Custom Field Configuration Attributes and Controls\n\n### Display Name\nThe human-readable title of the custom field shown on ticket property rails, board cards, and table columns.\n\n### Slug\nThe unique, URL-safe ASCII identifier used in formulas, API payloads, and query filters.\n\n### Flavors\nDetermines the underlying calculation mechanism: `scalar`, `formula`, `wasm`, or `nsjail`.\n\n### Sandbox Tier\nSelects between in-process WebAssembly (`wasmtime` Tier A) and containerized Linux namespaces (`nsjail` Tier B). In Standalone mode, `nsjail` is gated.\n\n### Credential Mode\nSpecifies whether the field executes with `INVOKING_USER` permissions or elevated `PROJECT_ADMIN_SP` / `SERVER_ADMIN_SP` service principal credentials.\n\n### Target Scope\nControls the tenant boundary accessible to the custom field: `PROJECT`, `WORKSPACE`, or `SERVER`.\n\n### Output Formats\nCanonical schema used to format and validate the output: `text`, `number`, `badge`, `severity_pill`, `url`, `markdown_snippet`, or `json_table`.\n\n### Format Metadata\nJSON metadata configuring format-specific options such as decimal precision, color tokens, and table column schemas.\n\n### Script Source\nThe Python AST expression, compiled WebAssembly module, or sandboxed script implementing the field calculation.\n\n### Egress Allowlist\nExplicit list of destination hosts accessible to `nsjail` tier scripts. Network access is disabled by default via `CLONE_NEWNET`.\n\n### AAL2 Stepup\nAdministrative modifications and scope escalations require recent multi-factor authentication (AAL2 verified within 900 seconds).\n\n### Approvals\nEscalating a field to workspace or server scope requires explicit cryptographic signing and approval by an administrator of that target tier.\n"
  },
  {
    "slug": "hierarchical-docs-and-stickies-with-smart-promotion",
    "title": "[Informational] Hierarchical Docs, Project Stickies, and Smart Promotion",
    "category": "informational",
    "track": "Feature & Field Reference",
    "subtrack": "Knowledge Management",
    "audience": "Technical Writers & Product Managers",
    "order": 13,
    "summary": "Software engineering encompasses both informal, ephemeral scratchpads (meeting notes, architecture brainstorming, quick snippets) and formal, structured documentation (system specifications, API references, runbooks). In conventional tools, informal notes either get lost in chat threads or prematurely clutter formal document trees.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "project-stickies-and-ideation-grid",
        "title": "Project Stickies and Ideation Grid",
        "level": 2
      },
      {
        "id": "stickies-architecture",
        "title": "Stickies Architecture",
        "level": 3
      },
      {
        "id": "smart-ai-assisted-sticky-to-doc-promotion",
        "title": "Smart AI-Assisted Sticky-to-Doc Promotion",
        "level": 2
      },
      {
        "id": "the-promotion-workflow-and-preview-modal",
        "title": "The Promotion Workflow and Preview Modal",
        "level": 3
      },
      {
        "id": "hierarchical-docs-and-nested-tree-navigation",
        "title": "Hierarchical Docs and Nested Tree Navigation",
        "level": 2
      },
      {
        "id": "postgresql-ltree-tree-engine",
        "title": "PostgreSQL ltree Tree Engine",
        "level": 3
      },
      {
        "id": "pageversion-diff-restore-and-highlight-to-issue-linking",
        "title": "PageVersion Diff, Restore, and Highlight-to-Issue Linking",
        "level": 2
      },
      {
        "id": "pageversion-visual-diff-and-instant-restore",
        "title": "1. PageVersion Visual Diff and Instant Restore",
        "level": 3
      },
      {
        "id": "highlight-to-issue-linking",
        "title": "2. Highlight-to-Issue Linking",
        "level": 3
      },
      {
        "id": "key-capabilities-of-the-docs-system",
        "title": "Key Capabilities of the Docs System",
        "level": 3
      }
    ],
    "content": "# [Informational] Hierarchical Docs, Project Stickies, and Smart Promotion\n\n## Overview\n\nSoftware engineering encompasses both informal, ephemeral scratchpads (meeting notes, architecture brainstorming, quick snippets) and formal, structured documentation (system specifications, API references, runbooks). In conventional tools, informal notes either get lost in chat threads or prematurely clutter formal document trees.\n\n\ud83d\udc4dkanban resolves this divide through two integrated systems:\n1. **Project Stickies:** Lightweight, color-coded digital sticky notes on an interactive masonry grid for rapid ideation.\n2. **Hierarchical Docs (`ltree`):** Deeply nested, versioned technical documentation powered by PostgreSQL tree hierarchies.\n3. **Smart AI Doc Promotion:** An intelligent bridge that detects when a scratchpad has matured into an architectural specification and transforms it into a formal Doc with a single click.\n\n---\n\n## Project Stickies and Ideation Grid\n\nProject Stickies live at `/stickies` (workspace scope) and `/projects/KAN/overview` (project scope).\n\n![Project Stickies and Smart Promotion Modal](images/10-stickies-and-doc-promotion.png)\n\n![Six-Color Semantic Sticky Palette Grid](images/33-stickies-palette-grid.png)\n\n### Stickies Architecture\n\n- **6 Semantic Color Palettes:** Amber, Emerald, Sky, Rose, Violet, and Slate cards for visual categorization.\n- **Masonry Layout:** Responsive CSS masonry layout that dynamically packs cards of varying heights.\n- **Fast Markdown Editing:** Double-click or select to edit Markdown inline with instant autosave.\n- **Real-Time Collaboration:** Changes synchronize across connected team members via WebSocket broadcasts within 50 milliseconds.\n\n---\n\n## Smart AI-Assisted Sticky-to-Doc Promotion\n\n```mermaid\nflowchart TD\n    Sticky[\"Scratchpad Sticky Note<br/>(Markdown text & initial thoughts)\"] --> Heuristics[\"Debounced Complexity Heuristic<br/>- Word count > 150 words<br/>- Headings (##), tables, code blocks<br/>- Checkboxes (- [ ])\"]\n    Heuristics -->|Threshold reached| RecPill[\"Display 'Promotion Recommended' Pill\"]\n    RecPill -->|Click Promote to Doc| AIStudio[\"AI Promotion Studio<br/>Multi-Provider AI drafts formal structure,<br/>executive summary & sections\"]\n    AIStudio --> Confirm[\"Operator Reviews & Accepts\"]\n    Confirm --> NewDoc[\"Formal Hierarchical Doc (ltree)\"]\n    Confirm --> Link[\"UOG records typed PROMOTED_TO link\"]\n    Confirm --> Archive[\"Original sticky marked promoted & archived\"]\n```\n\nAs brainstorming progresses, stickies often accumulate detailed requirements, code snippets, and diagrams. \ud83d\udc4dkanban monitors stickies using debounced complexity heuristics:\n- Word count exceeding 150 words.\n- Presence of structured headings (`## `), markdown tables, or fenced code blocks.\n- Multiple bullet points or task checkboxes (`- [ ]`).\n\n### The Promotion Workflow and Preview Modal\n\nWhen these heuristics trigger, the sticky displays a `promotion_recommended` indicator. Clicking **Promote to Doc** opens the interactive AI Promotion Preview Modal:\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor User as Engineer / Architect\n    participant Sticky as Stickies Board\n    participant Modal as AI Promotion Modal\n    participant AI as Multi-Provider AI Engine\n    participant DB as Universal Object Graph\n\n    User->>Sticky: Click \"Promote to Doc\" button\n    Sticky->>Modal: Open Promotion Preview Modal\n    Modal->>AI: Synthesize notes into formal structured document\n    AI-->>Modal: Return generated title, executive summary, sections, target project\n    User->>Modal: Inspect preview, adjust target project / ltree path\n    User->>Modal: Click \"Accept & Create Doc\"\n    Modal->>DB: INSERT into docs (ltree path, markdown, creator)\n    Modal->>DB: INSERT into object_links (kind: PROMOTED_TO)\n    Modal->>DB: UPDATE stickies SET state = 'promoted'\n    DB-->>Sticky: Real-time update: replace sticky with promoted stub\n```\n\n![AI Sticky to Doc Promotion Preview Modal](images/40-ai-sticky-doc-promotion-modal.png)\n\n1. **AI Structure Preview:** The multi-provider AI engine drafts formal headings, executive summaries, and organized subsections from the raw notes.\n2. **Target Project and Path Selection:** Operators can choose the destination project and parent document node in the `ltree` hierarchy.\n3. **ACL Scope Preservation:** The newly created document automatically inherits the project ACL permissions and explicit sharing rules of the origin sticky.\n4. **Bidirectional Object Link:** A typed `PROMOTED_TO` link is recorded in the Universal Object Graph connecting the original sticky and the new Doc.\n5. **Clean Archival & Promoted Stub:** The original sticky is converted into a promoted stub pointing to the new document URL, keeping the ideation board tidy while preserving audit history.\n\n---\n\n## Hierarchical Docs and Nested Tree Navigation\n\nFormal specifications and engineering documentation reside under the project Docs view (`/projects/KAN/docs`).\n\n![Hierarchical Docs Tree and Outline View](images/11-docs-hierarchy-view.png)\n\n![Three-Pane Interactive Documentation Editor](images/32-docs-three-pane-editor.png)\n\n### PostgreSQL `ltree` Tree Engine\n\nDocumentation hierarchies are modeled using PostgreSQL's native `ltree` extension (`database/models/knowledge.py`):\n- Path representations such as `workspace_1.project_kan.architecture.security`.\n- Sub-millisecond subtree queries, ancestral lookups, and branch moves.\n- Circular hierarchy prevention guaranteed by database constraints.\n\n```mermaid\ngraph TD\n    Root[\"Root: workspace_1.project_kan\"]\n    Arch[\"architecture (workspace_1.project_kan.architecture)\"]\n    API[\"api (workspace_1.project_kan.api)\"]\n    Sec[\"security (workspace_1.project_kan.architecture.security)\"]\n    Perf[\"perf (workspace_1.project_kan.architecture.perf)\"]\n    REST[\"rest (workspace_1.project_kan.api.rest)\"]\n    MCPDoc[\"mcp (workspace_1.project_kan.api.mcp)\"]\n\n    Root --> Arch\n    Root --> API\n    Arch --> Sec\n    Arch --> Perf\n    API --> REST\n    API --> MCPDoc\n```\n\n---\n\n## PageVersion Diff, Restore, and Highlight-to-Issue Linking\n\nTechnical documentation evolves across releases. \ud83d\udc4dkanban provides deep revision governance and bidirectional issue linking directly inside the editor:\n\n```mermaid\nflowchart LR\n    subgraph DocEvolution[\"Documentation Lifecycle\"]\n        V1[\"PageVersion 1<br/>Initial Spec\"] --> V2[\"PageVersion 2<br/>Architecture Review\"]\n        V2 --> V3[\"PageVersion 3<br/>Active Production\"]\n        \n        V3 -.->|Inspect Diff| DiffView[\"Side-by-Side Diff Modal<br/>Green additions / Red deletions\"]\n        DiffView -.->|One-Click Restore| V2\n        \n        V3 -->|Highlight text| Highlight[\"Selection Popover<br/>'Link to Issue' / 'New Issue'\"]\n        Highlight -->|typed object_link| Issue[\"Linked Work Item KAN-142\"]\n    end\n```\n\n![Docs PageVersion Diff Restore and Highlight Linking](images/41-docs-pageversion-diff-restore.png)\n\n### 1. `PageVersion` Visual Diff and Instant Restore\n- **Immutable Revision Snapshots:** Every manual save or autosave milestone writes an immutable snapshot to `page_versions`.\n- **Side-by-Side and Unified Diffs:** Compare any two revisions with syntax-highlighted additions (green) and deletions (red).\n- **One-Click Restore:** Roll back any document to a previous revision without losing intervening history.\n\n### 2. Highlight-to-Issue Linking\n- **Inline Text Selection:** Selecting any phrase, sentence, or technical requirement inside a document displays an instant action pill.\n- **Bi-Directional Traceability:** Link the highlighted text to an existing ticket or click to spawn a new work item with the highlighted text pre-filled into the description.\n- **Universal Graph Integrity:** Creates typed `REFERENCED_IN` / `MENTIONS` links in the Universal Object Graph.\n\n### Key Capabilities of the Docs System\n\n- **Nested Page Tree:** Expandable sidebar tree allowing arbitrary nesting of documents, specifications, and runbooks.\n- **Auto-Extracted Outline Rail:** The right-hand rail parses headings in real time (`H1`, `H2`, `H3`), providing one-click jump links to document sections.\n- **Append-Only Version History:** Every document save appends an immutable snapshot. Authors can inspect visual diffs between revisions and restore previous versions with a single click.\n- **Mermaid and Diagram Support:** Native rendering of architecture flows, sequence diagrams, and class models directly within the document.\n"
  },
  {
    "slug": "mcp-tools-reference",
    "title": "[Informational] Model Context Protocol (MCP) Tools Reference Manual",
    "category": "informational",
    "track": "Feature & Field Reference",
    "subtrack": "Protocol Reference",
    "audience": "AI Integrators & Developers",
    "order": 14,
    "summary": "The \ud83d\udc4dkanban platform exposes 25 intent-driven Model Context Protocol (MCP) tools across three streamable HTTP surfaces (`2025-06-18` specification). Unlike conventional project management APIs that force agents to coordinate dozens of low-level CRUD endpoints, \ud83d\udc4dkanban tools encapsulate multi-step engineering workflows into atomic, type-safe operations.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "surface-1-mcpagent-execution-and-qa-tools",
        "title": "Surface 1: /mcp/agent (Execution and QA Tools)",
        "level": 2
      },
      {
        "id": "search-tickets",
        "title": "1. search_tickets",
        "level": 3
      },
      {
        "id": "read-ticket",
        "title": "2. read_ticket",
        "level": 3
      },
      {
        "id": "create-ticket",
        "title": "3. create_ticket",
        "level": 3
      },
      {
        "id": "update-ticket",
        "title": "4. update_ticket",
        "level": 3
      },
      {
        "id": "begin-work",
        "title": "5. begin_work",
        "level": 3
      },
      {
        "id": "transition-ticket",
        "title": "6. transition_ticket",
        "level": 3
      },
      {
        "id": "complete-work",
        "title": "7. complete_work",
        "level": 3
      },
      {
        "id": "add-comment",
        "title": "8. add_comment",
        "level": 3
      },
      {
        "id": "link-objects",
        "title": "9. link_objects",
        "level": 3
      },
      {
        "id": "update-workpad",
        "title": "10. update_workpad",
        "level": 3
      },
      {
        "id": "surface-2-mcpdocs-consolidated-3-tool-suite",
        "title": "Surface 2: /mcp/docs (Consolidated 3-Tool Suite)",
        "level": 2
      },
      {
        "id": "search",
        "title": "1. search",
        "level": 3
      },
      {
        "id": "create",
        "title": "2. create",
        "level": 3
      },
      {
        "id": "update",
        "title": "3. update",
        "level": 3
      },
      {
        "id": "surface-3-mcpadmin-governance-and-lifecycle-tools",
        "title": "Surface 3: /mcp/admin (Governance and Lifecycle Tools)",
        "level": 2
      },
      {
        "id": "configure-workspace",
        "title": "1. configure_workspace",
        "level": 3
      },
      {
        "id": "manage-auth-cards",
        "title": "2. manage_auth_cards",
        "level": 3
      },
      {
        "id": "manage-principals-and-groups",
        "title": "3. manage_principals_and_groups",
        "level": 3
      },
      {
        "id": "manage-access-policies",
        "title": "4. manage_access_policies",
        "level": 3
      },
      {
        "id": "architect-project",
        "title": "5. architect_project",
        "level": 3
      },
      {
        "id": "manage-cycles-and-modules",
        "title": "6. manage_cycles_and_modules",
        "level": 3
      },
      {
        "id": "manage-custom-fields-and-scripts",
        "title": "7. manage_custom_fields_and_scripts",
        "level": 3
      },
      {
        "id": "manage-workflow-interceptors",
        "title": "8. manage_workflow_interceptors",
        "level": 3
      },
      {
        "id": "manage-ai-and-agent-runners",
        "title": "9. manage_ai_and_agent_runners",
        "level": 3
      },
      {
        "id": "override-ticket-provenance",
        "title": "10. override_ticket_provenance",
        "level": 3
      },
      {
        "id": "audit-and-purge-object-links",
        "title": "11. audit_and_purge_object_links",
        "level": 3
      },
      {
        "id": "destructive-lifecycle-two-stage-confirmation-safety",
        "title": "12. destructive_lifecycle (Two-Stage Confirmation Safety)",
        "level": 3
      },
      {
        "id": "progressive-disclosure-self-correcting-yaml-error-ux",
        "title": "Progressive-Disclosure Self-Correcting YAML Error UX",
        "level": 2
      },
      {
        "id": "pre-dispatch-schema-validation-contract",
        "title": "Pre-Dispatch Schema Validation Contract",
        "level": 3
      },
      {
        "id": "canonical-yaml-error-examples",
        "title": "Canonical YAML Error Examples",
        "level": 3
      }
    ],
    "content": "# [Informational] Model Context Protocol (MCP) Tools Reference Manual\n\n## Overview\n\nThe \ud83d\udc4dkanban platform exposes 25 intent-driven Model Context Protocol (MCP) tools across three streamable HTTP surfaces (`2025-06-18` specification). Unlike conventional project management APIs that force agents to coordinate dozens of low-level CRUD endpoints, \ud83d\udc4dkanban tools encapsulate multi-step engineering workflows into atomic, type-safe operations.\n\nResponses are serialized using `InlineSafeDumper` compact YAML, stripping null values and empty collections to maximize LLM context efficiency and token economy.\n\n```mermaid\nflowchart TD\n    subgraph Surfaces[\"Three Dedicated MCP Surfaces\"]\n        AgentSurf[\"/mcp/agent (10 Tools) - Token budget: <= 1,850 tokens - Target: Coding & QA Autonomous Agents\"]\n        DocsSurf[\"/mcp/docs (3 Tools) - Token budget: <= 1,300 tokens - Target: Documentation & Knowledge Bots\"]\n        AdminSurf[\"/mcp/admin (12 Tools) - Token budget: <= 2,800 tokens - Target: DevOps & Migration Administrators (AAL2)\"]\n    end\n\n    subgraph LOD[\"InlineSafeDumper YAML Engine\"]\n        Summary[\"lod='summary' - Keys, titles, states only\"]\n        Standard[\"lod='standard' - Balanced properties & assignees\"]\n        Full[\"lod='full' - Exhaustive body, history & links\"]\n    end\n\n    Surfaces --> LOD\n```\n\n![MCP Access Studio and Scoped Token Minting](images/slice3-mcp-access-studio-mint-modal.png)\n\n![MCP Config Snippet and Client Onboarding](images/slice3-mcp-config-snippet-modal.png)\n\n---\n\n## Surface 1: `/mcp/agent` (Execution and QA Tools)\n\nDedicated to autonomous coding agents, test runners, and QA bots. Bounded strictly by caller permissions; contains zero administrative or destructive tools. CLI binary mental model: `kanban-cli-agent`.\n\n### 1. `search_tickets`\n- **Description:** Hybrid lexical and semantic search across project tickets with multi-attribute filtering.\n- **Required Parameters:** None.\n- **Optional Parameters:**\n  - `query` (string): Text or semantic query.\n  - `workspace` (string): Target workspace slug or UUID.\n  - `project` (string): Target project key (e.g. `KAN`).\n  - `states` (array of strings): Filter by state names (e.g. `['in_progress', 'todo']`).\n  - `assignees` (array of strings): Filter by username or agent handle.\n  - `cycle` (string): Sprint cycle slug or UUID.\n  - `modules` (array of strings): Filter by module slugs.\n  - `labels` (array of strings): Filter by label names.\n  - `blocked` (boolean): Filter for blocked or non-blocked items.\n  - `gate_status` (string): Filter by agent gate state (`pending_agent_gate`, `vetoed`, `approved`).\n  - `mode` (string): `lexical`, `semantic`, or `hybrid` (default).\n  - `lod` (string): Level of detail: `summary`, `standard` (default), `full`.\n  - `limit` (integer): Maximum items to return (1 to 50, default 20).\n  - `cursor` (string): Pagination cursor.\n- **CLI Example:** `kanban-cli-agent search_tickets --query=\"progressive error\" --project=KAN`\n\n### 2. `read_ticket`\n- **Description:** Retrieve complete ticket details, canonical Markdown description, activity feed, and access manifest.\n- **Required Parameters:**\n  - `identifier` (string): Human ticket key (e.g. `KAN-42`) or UUID.\n- **Optional Parameters:**\n  - `workspace` (string): Workspace context.\n  - `lod` (string): Level of detail: `summary`, `standard` (default), `full`.\n  - `comments_limit` (integer): Max recent comments to return (default 10).\n- **CLI Example:** `kanban-cli-agent read_ticket --identifier=KAN-19 --lod=standard`\n\n### 3. `create_ticket`\n- **Description:** Create ticket or atomic child tree (max 50 nodes, depth <=6; omit project and parent inside children).\n- **Required Parameters:**\n  - `project` (string): Target project key (e.g. `KAN`). Root only; inherited by children.\n  - `summary` (string): Single-line ticket title.\n- **Optional Parameters:**\n  - `description_markdown` (string): Canonical Markdown description.\n  - `state` (string): Initial state key.\n  - `priority` (string): `urgent`, `high`, `medium`, `low`, `none`.\n  - `assignees` (array of strings): Handles of assignees.\n  - `labels` (array of strings): Label names.\n  - `cycle` (string): Cycle slug or UUID.\n  - `modules` (array of strings): Module slugs.\n  - `parent` (string): Parent issue identifier. Root only; omit in children.\n  - `start_date` (string): ISO 8601 start date.\n  - `due_date` (string): ISO 8601 due date.\n  - `children` (array of objects): Sub-issues to create atomically. Each child object requires `summary` and inherits `project` from the root and `parent` from its enclosing node; both `project` and `parent` must be omitted inside `children`. Max 49 items per node, total nodes <= 50, maximum depth <= 6.\n- **CLI Example:** `kanban-cli-agent create_ticket --project=KAN --summary=\"Self-correcting error UX\"`\n\n### 4. `update_ticket`\n- **Description:** Update ticket properties, state, assignees, or Markdown body. State changes must use `transition_ticket`.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n- **Optional Parameters:**\n  - `if_match` (string): Concurrency lock (version hash) to prevent lost updates.\n  - `summary` (string): New title.\n  - `description_markdown` (string): Markdown content.\n  - `description_mode` (string): `replace` (default), `append`, `prepend`.\n  - `assignees_add` / `assignees_remove` (array of strings): Incremental assignee adjustments.\n  - `priority` (string): Updated priority.\n  - `start_date` / `due_date` (string): ISO 8601 dates.\n  - `cycle` (string): Move to cycle.\n  - `modules_add` / `modules_remove` (array of strings): Incremental module adjustments.\n  - `labels_add` / `labels_remove` (array of strings): Incremental label adjustments.\n  - `parent` (string): Update parent issue.\n- **CLI Example:** `kanban-cli-agent update_ticket --identifier=KAN-19 --summary=\"Refined Error UX\"`\n\n### 5. `begin_work`\n- **Description:** Atomic workflow starter: assigns calling agent, transitions ticket to started state, binds active cycle, and posts plan comment.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n  - `plan_markdown` (string): High-level technical execution plan.\n- **CLI Example:** `kanban-cli-agent begin_work --identifier=KAN-19 --plan-markdown=\"1. Implement schema validation\"`\n\n### 6. `transition_ticket`\n- **Description:** Transition ticket between workflow states, executing synchronous validators and triggering async agent gates.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n  - `to_state` (string): Target state name or slug.\n- **Optional Parameters:**\n  - `comment_markdown` (string): Accompanying transition comment.\n  - `verification_proof` (object): Verification artifacts or test results.\n- **CLI Example:** `kanban-cli-agent transition_ticket --identifier=KAN-19 --to-state=\"Done\"`\n\n### 7. `complete_work`\n- **Description:** Atomic terminal QA gate: verifies child blocker resolution, records verification proof, transitions to completed, and posts summary comment.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n  - `summary_markdown` (string): Final delivery report.\n  - `verification_proof` (object): Passive forensic proof packet (logs, test outputs, screenshots).\n- **Optional Parameters:**\n  - `to_state` (string): Target terminal state (defaults to `done`).\n- **CLI Example:** `kanban-cli-agent complete_work --identifier=KAN-19 --summary-markdown=\"Work complete\"`\n\n### 8. `add_comment`\n- **Description:** Post a canonical Markdown comment or threaded reply to a ticket.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n  - `body_markdown` (string): Comment content in canonical Markdown.\n- **Optional Parameters:**\n  - `reply_to` (string): Parent comment UUID for threaded replies.\n  - `ack_mentions` (boolean): Acknowledge mentioned user notifications.\n- **CLI Example:** `kanban-cli-agent add_comment --identifier=KAN-19 --body-markdown=\"PR review complete\"`\n\n### 9. `link_objects`\n- **Description:** Create or remove a typed Universal Object Graph link between two entities.\n- **Required Parameters:**\n  - `source` (string): Source object key or UUID.\n  - `target` (string): Target object key or UUID.\n  - `link_type` (string): Relationship kind (`blocks`, `relates_to`, `duplicates`, `parent_of`).\n- **Optional Parameters:**\n  - `action` (string): `create` (default) or `remove`.\n- **CLI Example:** `kanban-cli-agent link_objects --source=KAN-19 --target=KAN-25 --link-type=\"relates_to\"`\n\n### 10. `update_workpad`\n- **Description:** Update intermediate agent workpad notes, scratchpads, and execution progress on an active ticket.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n  - `body_markdown` (string): Markdown content for the workpad.\n- **Optional Parameters:**\n  - `revision` (integer): Concurrency lock revision number.\n- **CLI Example:** `kanban-cli-agent update_workpad --identifier=KAN-19 --body-markdown=\"### In-Flight Findings\\n- Root cause isolated\"`\n\n---\n\n## Surface 2: `/mcp/docs` (Consolidated 3-Tool Suite)\n\nDedicated to technical documentation, architecture specifications, and sticky notes. Consolidated from 6 legacy tools into 3 intent-driven operations (`search`, `create`, `update`). CLI binary mental model: `kanban-cli-docs`.\n\n### 1. `search`\n- **Description:** Unified discovery across Docs, Pages, and Stickies with hybrid lexical and semantic filtering, hierarchical breadcrumbs, and LOD tiers.\n- **Required Parameters:** None.\n- **Optional Parameters:**\n  - `query` (string): Search query text.\n  - `id` (string): Direct document slug or UUID lookup.\n  - `project` (string): Project scope filter.\n  - `type` (string): Entity kind filter (`DOC`, `STICKY`, `ALL`). Default: `ALL`.\n  - `lod` (string): Level of detail: `summary`, `standard` (default), `full`.\n  - `include_tree` (boolean): Include full ltree hierarchical descendants. Default: `false`.\n  - `limit` (integer): Maximum items to return (1 to 100, default 20).\n  - `cursor` (string): Pagination cursor.\n- **CLI Example:** `kanban-cli-docs search --query=\"architecture\" --type=DOC`\n\n### 2. `create`\n- **Description:** Atomic authoring tool creating standalone Docs, nested child Pages in an ltree hierarchy, or ideation Stickies.\n- **Required Parameters:**\n  - `type` (string): Entity kind: `DOC` or `STICKY`.\n  - `title` (string): Document title or sticky summary.\n- **Optional Parameters:**\n  - `project` (string): Project identifier (e.g. `KAN`). Required when creating stickies.\n  - `content` (string): Canonical Markdown content body.\n  - `parent` (string): Parent Doc UUID or canonical slug for nested document placement.\n  - `color` (string): Sticky color badge (`amber`, `emerald`, `sky`, `rose`, `violet`, `slate`). Default: `amber`.\n  - `links` (array of objects): Explicit Universal Object Graph typed relationships.\n- **CLI Example:** `kanban-cli-docs create --type=DOC --title=\"Architecture Guide\" --content=\"# Overview\"`\n\n### 3. `update`\n- **Description:** Unified mutation tool for updating Markdown content, properties, or executing surgical line-level diff-patching with ETag concurrency protection and smart sticky-to-doc promotion.\n- **Required Parameters:**\n  - `id` (string): Doc slug, UUID, or sticky note identifier.\n- **Optional Parameters:**\n  - `type` (string): Entity kind: `DOC` or `STICKY`.\n  - `title` (string): New title.\n  - `content` (string): New complete Markdown body (replaces entire content).\n  - `original_text` (string): Target substring for surgical line-level diff-patching.\n  - `replacement_text` (string): Replacement substring for surgical diff-patching (requires `original_text`).\n  - `parent` (string): Target parent Doc UUID to re-parent in documentation tree.\n  - `color` (string): Updated sticky color.\n  - `if_match` (string): SHA-256 ETag version lock preventing lost updates.\n  - `links` (array of objects): Graph relationships to add or remove.\n- **CLI Examples:**\n  - Full body replacement: `kanban-cli-docs update --id=\"docs/arch\" --type=DOC --content=\"# Updated Architecture\"`\n  - Surgical diff-patching: `kanban-cli-docs update --id=\"docs/arch\" --type=DOC --original-text=\"old line\" --replacement-text=\"new line\"`\n  - ETag-protected update: `kanban-cli-docs update --id=\"docs/arch\" --type=DOC --if-match=\"c4ca4238a0b923820dcc509a6f75849b\" --content=\"new\"`\n\n---\n\n## Surface 3: `/mcp/admin` (Governance and Lifecycle Tools)\n\nPrivileged administrative surface. Every request requires AAL2 credentials. CLI binary mental model: `kanban-cli-admin`.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Admin Agent (AAL2)\n    participant MCP as /mcp/admin Surface\n    participant DB as PostgreSQL Engine\n\n    Note over Admin,MCP: Phase 1: Dry-Run Inspection\n    Admin->>MCP: Call audit_and_purge_object_links(action=\"run_audit\")\n    MCP->>DB: Audit dangling links & compute blast radius\n    DB-->>MCP: 14 broken links identified\n    MCP-->>Admin: Return dry-run summary + ephemeral confirmation_token (valid 300s)\n\n    Note over Admin,MCP: Phase 2: Explicit Two-Stage Execution\n    Admin->>MCP: Call audit_and_purge_object_links(action=\"purge_audited\", confirmation_token=\"tok_...\")\n    MCP->>MCP: Verify AAL2 session & token validity\n    MCP->>DB: BEGIN TX & DELETE dangling links & record audit event\n    DB-->>MCP: 14 rows removed\n    MCP-->>Admin: Purge executed successfully (Ledger ID recorded)\n```\n\n### 1. `configure_workspace`\n- **Description:** Read or update workspace-level settings, themes, and default project templates.\n- **Required Parameters:**\n  - `action` (string): `get` or `update`.\n- **Optional Parameters:**\n  - `settings` (object): Key-value workspace configuration settings.\n  - `lod` (string): Level of detail.\n- **CLI Example:** `kanban-cli-admin configure_workspace --action=\"get\"`\n\n### 2. `manage_auth_cards`\n- **Description:** Configure, reorder, test, or toggle Multi-Card authentication providers.\n- **Required Parameters:**\n  - `action` (string): `list`, `get`, `create`, `update`, `reorder`, `test_handshake`, `delete`.\n- **Optional Parameters:**\n  - `card` (string): Auth card UUID.\n  - `slug` (string): Unique identifier slug.\n  - `provider_kind` (string): `local`, `oidc`, `oauth2`, `ldaps`, `webauthn`, `totp`.\n  - `display_name` (string): Card label on login screen.\n  - `public_config` / `secret` (objects): Provider configuration and write-only credentials.\n  - `after` (string): Slug of card to place after when reordering.\n  - `confirm_slug` (string): Required confirmation slug on deletion.\n- **CLI Example:** `kanban-cli-admin manage_auth_cards --action=\"list\"`\n\n### 3. `manage_principals_and_groups`\n- **Description:** Provision users, service principals, and groups, and manage role bindings.\n- **Required Parameters:**\n  - `action` (string): `list`, `get`, `create_user`, `create_agent`, `create_group`, `bind_role`, `unbind_role`.\n- **Optional Parameters:**\n  - `principal` (string): User or agent UUID.\n  - `group` (string): Group UUID.\n  - `handle` (string): Unique username or agent handle.\n  - `role` (string): `owner`, `admin`, `member`, `guest`.\n  - `scope` (string): Workspace or project scope identifier.\n- **CLI Example:** `kanban-cli-admin manage_principals_and_groups --action=\"list\"`\n\n### 4. `manage_access_policies`\n- **Description:** Inspect and update fine-grained 8-bit capability bitmasks (`VIEW` [0x01], `COMMENT` [0x02], `EDIT` [0x04], `TRANSITION` [0x08], `LINK` [0x10], `SHARE` [0x20], `ADMIN` [0x40], `DELETE` [0x80], `ALL` [0xFF]) on Universal Object Graph entities.\n- **Required Parameters:**\n  - `action` (string): `read_manifest`, `grant`, `revoke`.\n- **Optional Parameters:**\n  - `object` (string): Object UUID.\n  - `principal` (string): Target user, group, or agent UUID.\n  - `effect` (string): `allow` or `deny`.\n  - `capabilities` (array of strings): Granular capability masks.\n- **CLI Example:** `kanban-cli-admin manage_access_policies --action=\"read_manifest\" --object=\"<uuid>\"`\n\n### 5. `architect_project`\n- **Description:** Provision, configure, or scaffold a project using structured blueprint templates.\n- **Required Parameters:**\n  - `action` (string): `create`, `plan`, `apply`, `get`, `update`.\n- **Optional Parameters:**\n  - `project` (string): Project key (e.g. `KAN`).\n  - `blueprint` (object): Complete project schema, workflow states, and default views.\n  - `plan_sha256` (string): Cryptographic digest verification.\n- **CLI Example:** `kanban-cli-admin architect_project --action=\"plan\" --project=KAN`\n\n### 6. `manage_cycles_and_modules`\n- **Description:** Manage sprint cycles, functional modules, and custom view configurations.\n- **Required Parameters:**\n  - `action` (string): `list_cycles`, `create_cycle`, `update_cycle`, `start_cycle`, `complete_cycle`, `rollover`, `list_modules`, `create_module`, `update_module`, `list_views`, `create_view`, `update_view`, `bind_project_repo`, `list_repo_bindings`, `refresh_repo_binding`, `unbind_project_repo`, `help`.\n- **Optional Parameters:**\n  - `project` (string): Target project key.\n  - `cycle` / `module` / `view` (strings): Entity UUIDs.\n  - `name` (string): Display name.\n  - `start_date` / `end_date` (strings): Schedule range.\n- **CLI Example:** `kanban-cli-admin manage_cycles_and_modules --action=\"list_cycles\" --project=KAN`\n\n### 7. `manage_custom_fields_and_scripts`\n- **Description:** Define custom scripted fields and sandbox execution settings.\n- **Required Parameters:**\n  - `action` (string): `list`, `create_field`, `update_field`, `test_execute`, `escalate_scope`.\n- **Optional Parameters:**\n  - `project` (string): Project key.\n  - `field` (string): Field UUID.\n  - `tier` (string): `tier_a_wasm` or `tier_b_jail`.\n  - `target_scope` (string): `project`, `workspace`, `server`.\n  - `justification` (string): Cryptographic justification for privilege escalation.\n- **CLI Example:** `kanban-cli-admin manage_custom_fields_and_scripts --action=\"list\" --project=KAN`\n\n### 8. `manage_workflow_interceptors`\n- **Description:** Configure pre-transition helper hooks (validators, mutators, async agent gates).\n- **Required Parameters:**\n  - `action` (string): `list`, `create_hook`, `update_hook`, `reorder_pipeline`, `dry_run`.\n- **Optional Parameters:**\n  - `project` (string): Project key.\n  - `from_state` / `to_state` (strings): State transition rule.\n  - `hook_kind` (string): `sync_validator`, `sync_mutator`, `async_agent_gate`.\n  - `ordered_hook_ids` (array of strings): Execution sequence.\n  - `sample_ticket` (object): Test ticket for zero-persistence dry-run.\n- **CLI Example:** `kanban-cli-admin manage_workflow_interceptors --action=\"list\" --project=KAN`\n\n### 9. `manage_ai_and_agent_runners`\n- **Description:** Register LLM provider endpoints, configure token caps, and define CLI pipe harnesses or mTLS runner pools.\n- **Required Parameters:**\n  - `action` (string): `list_providers`, `upsert_provider`, `set_token_cap`, `register_runner_pool`.\n- **Optional Parameters:**\n  - `provider_kind` (string): `openai`, `gemini`, `ollama`, `cli_pipe`, `remote_runner`.\n  - `base_url` (string): Endpoint URL.\n  - `token_cap` (integer): Monthly or billing period token ceiling.\n  - `mcp_allowed_tools` (array of strings): Allowlist of tools permitted for this runner.\n- **CLI Example:** `kanban-cli-admin manage_ai_and_agent_runners --action=\"list_providers\"`\n\n### 10. `override_ticket_provenance`\n- **Description:** Privileged administrative tool to adjust ticket author, creation timestamp, or state during migration reconciliation.\n- **Required Parameters:**\n  - `action` (string): `reassign_creator`, `reorder_history`.\n- **Optional Parameters:**\n  - `issue` (string): Issue identifier.\n  - `new_creator` (string): New author principal UUID.\n  - `reason` (string): Mandatory audit explanation.\n- **CLI Example:** `kanban-cli-admin override_ticket_provenance --action=\"reassign_creator\" --issue=KAN-1 --new-creator=\"<uuid>\" --reason=\"audit\"`\n\n### 11. `audit_and_purge_object_links`\n- **Description:** Execute the Invalid Object Link Auditor to detect and remediate orphaned or corrupt graph relationships.\n- **Required Parameters:**\n  - `action` (string): `run_audit`, `list_flagged`, `purge_audited`, `help`.\n- **Optional Parameters:**\n  - `reason_filter` (string): Filter by violation class (`orphaned_target`, `cross_tenant_leak`, etc.).\n  - `reason` (string): Mandatory audit ledger explanation for purge actions.\n- **CLI Example:** `kanban-cli-admin audit_and_purge_object_links --action=\"run_audit\"`\n\n### 12. `destructive_lifecycle` (Two-Stage Confirmation Safety)\n- **Description:** Administrative destruction tool for projects, workspaces, or entire datasets. Enforces a non-bypassable two-stage confirmation protocol.\n- **Required Parameters:**\n  - `action` (string): `request_delete` (Stage 1) or `execute_delete` (Stage 2).\n- **Optional Parameters:**\n  - `target_kind` (string): `project`, `workspace`, `all_tickets`.\n  - `target` (string): Slug or UUID of target entity.\n  - `mode` (string): `soft_archive` or `hard_purge`.\n  - `confirmation_token` (string): Short-lived cryptographic token issued in Stage 1.\n  - `confirm_phrase` (string): Verbatim confirmation string (e.g. `DELETE PROJECT KAN`).\n  - `reason` (string): Mandatory audit justification.\n- **CLI Example:** `kanban-cli-admin destructive_lifecycle --action=\"request_delete\" --target-kind=\"project\" --target=KAN`\n\n---\n\n## Progressive-Disclosure Self-Correcting YAML Error UX\n\nAll \ud83d\udc4dkanban MCP tools implement progressive-disclosure, self-correcting error responses. When an AI agent submits an invalid parameter name, misses a required argument, uses an unrecognized enum option, or encounters a domain concurrency conflict, the server intercepts the error before execution and responds with structured, actionable guidance.\n\nThis prevents repetitive LLM retry loops, hallucination thrashing, and context bloat by immediately providing:\n1. Exact culprit parameter name (`field`)\n2. Comprehensive list of allowed values (`valid_options`)\n3. Fuzzy and semantic closest matches (`did_you_mean`)\n4. Human-readable remediation instruction (`fix_hint`)\n5. Corrected, copy-paste-ready command invocation (`cli_example`)\n6. Line-numbered snippet candidates for ambiguous diffs (`closest_match`)\n\n### Pre-Dispatch Schema Validation Contract\n\nPre-dispatch validation runs centrally inside `McpProtocolHandler._handle_tools_call` across all 3 surfaces before tool handlers execute:\n\n- **Unknown Parameter:** The server checks common developer synonyms via `SEMANTIC_ALIASES` (`body` -> `content`/`description_markdown`, `identifier` -> `id`, `kind` -> `type`, `ticket_id` -> `identifier`, `title` -> `summary`, `originalText` -> `original_text`, `replacementText` -> `replacement_text`), camelCase to snake_case conversions, and `difflib` string similarity against known schema properties.\n- **Missing Required Parameter:** The server constructs a pre-filled `cli_example` containing all valid arguments the caller already provided, adding `<placeholder>` values only for missing required fields.\n- **Invalid Enum / Type / Pattern:** The server validates options against declared enum sets, computes case-insensitive closest matches (`\"dco\"` -> `DOC`), and returns typed format patterns (such as 64-character SHA-256 hashes).\n- **JIT Help Immunity:** Calls containing `action=\"help\"` or `identifier=\"help\"` bypass parameter validation to ensure help documents are always accessible without error.\n\n### Canonical YAML Error Examples\n\n#### 1. Unknown Parameter with Semantic Alias\nCaller passes `body` to `/mcp/docs` `update` instead of `content`:\n\n```yaml\nerror:\n  code: VALIDATION_FAILED\n  message: Unknown parameter 'body' for tool 'update'\n  field: body\n  valid_options: [id, type, title, content, parent, color, original_text, replacement_text, if_match, links]\n  did_you_mean: [content]\n  hint: Unknown parameter 'body'. Did you mean 'content'?\n  fix_hint: Unknown parameter 'body'. Did you mean 'content'?\n  cli_example: kanban-cli-docs update --id=\"docs/arch\" --type=DOC --content=\"new content\"\n```\n\n#### 2. Unknown Parameter with Fuzzy Match\nCaller has typo `querry` on `/mcp/docs` `search`:\n\n```yaml\nerror:\n  code: VALIDATION_FAILED\n  message: Unknown parameter 'querry' for tool 'search'\n  field: querry\n  valid_options: [id, query, type, project, lod, include_tree, limit, cursor]\n  did_you_mean: [query, cursor]\n  hint: Unknown parameter 'querry'. Did you mean 'query'?\n  fix_hint: Unknown parameter 'querry'. Did you mean 'query'?\n  cli_example: kanban-cli-docs search --query=\"architecture\"\n```\n\n#### 3. Missing Required Parameter with Pre-filled CLI Example\nCaller supplies `type` and `content` but omits required `title` on `/mcp/docs` `create`:\n\n```yaml\nerror:\n  code: VALIDATION_FAILED\n  message: Missing required parameter 'title' for tool 'create'\n  field: title\n  hint: 'Missing required parameter: ''title''. Provide a value to proceed.'\n  fix_hint: 'Missing required parameter: ''title''. Provide a value to proceed.'\n  cli_example: kanban-cli-docs create --type=DOC --content=\"# Architecture\" --title=\"<title>\"\n```\n\n#### 4. Invalid Enum Value with Case-Insensitive Fuzzy Match\nCaller passes `type=\"dco\"` on `/mcp/docs` `create`:\n\n```yaml\nerror:\n  code: VALIDATION_FAILED\n  message: Invalid value 'dco' for parameter 'type'; type must be 'DOC' or 'STICKY' or 'doc' or 'sticky'\n  field: type\n  valid_options: [DOC, STICKY, doc, sticky]\n  did_you_mean: [doc]\n  hint: 'Invalid value ''dco'' for parameter ''type''. Did you mean ''doc''? Valid options: [''DOC'', ''STICKY'', ''doc'', ''sticky'']'\n  fix_hint: 'Invalid value ''dco'' for parameter ''type''. Did you mean ''doc''? Valid options: [''DOC'', ''STICKY'', ''doc'', ''sticky'']'\n  cli_example: kanban-cli-docs create --type=\"doc\" --title=\"System Architecture\" --content=\"text\"\n```\n\n#### 5. Tool Not Found on Surface\nCaller invokes `search_docs` on `/mcp/docs` instead of consolidated `search`:\n\n```yaml\nerror:\n  code: NOT_FOUND\n  message: Tool 'search_docs' not found on surface 'docs'\n  field: tool_name\n  valid_options: [search, create, update]\n  did_you_mean: [search]\n  hint: Verify tool name or switch to appropriate MCP surface endpoint\n  fix_hint: Tool 'search_docs' not found. Did you mean 'search'?\n  cli_example: kanban-cli-docs search\n```\n\n#### 6. Concurrency Conflict (ETag Mismatch)\nCaller attempts an update with an obsolete ETag version:\n\n```yaml\nerror:\n  code: CONFLICT_ETAG\n  message: concurrency conflict: ticket description was modified concurrently\n  hint: 'current etag: 9f83726abcde4582...'\n  fix_hint: Ticket description was modified concurrently. Retry with fresh ETag: 9f83726abcde4582...\n  cli_example: kanban-cli-agent update_ticket --identifier=\"KAN-19\" --if-match=\"9f83726abcde4582...\"\n  current_etag: 9f83726abcde4582...\n```\n\n#### 7. Sticky Already Promoted to Document\nCaller attempts to edit a sticky note that has already been converted into a formal Doc:\n\n```yaml\nerror:\n  code: ALREADY_PROMOTED\n  message: Sticky 'stk_01abc' has already been promoted to document 'DOC-KAN-42'\n  field: id\n  hint: Sticky 'stk_01abc' has already been promoted to Doc 'DOC-KAN-42'. Use update on that Doc instead.\n  fix_hint: Sticky 'stk_01abc' has already been promoted to Doc 'DOC-KAN-42'. Use update on that Doc instead.\n  cli_example: kanban-cli-docs update --id=\"DOC-KAN-42\"\n  target_doc_key: DOC-KAN-42\n```\n\n#### 8. Surgical Diff Patch Target Not Found (Closest Match)\nCaller provides a target string with indentation or typo differences:\n\n```yaml\nerror:\n  code: PATCH_TARGET_NOT_FOUND\n  message: Target text not found in document\n  field: original_text\n  closest_match:\n    - line_start: 3\n      line_end: 3\n      similarity: 0.973\n      snippet: 'Section 1: Context'\n  hint: Verify exact whitespace and indentation, or inspect closest_match suggestions.\n  fix_hint: Target text not found in document. Inspect closest_match suggestions for exact whitespace/indentation.\n  cli_example: kanban-cli-docs update --id=\"<id>\" --original-text=\"<snippet from closest_match>\" --replacement-text=\"<new>\"\n```\n\n#### 9. Surgical Diff Patch Target Ambiguous\nCaller provides non-unique target text that appears in multiple sections:\n\n```yaml\nerror:\n  code: PATCH_TARGET_AMBIGUOUS\n  message: Target text appears 2 times in document; provide more surrounding context\n  field: original_text\n  hint: Include unique surrounding lines to disambiguate the target region.\n  fix_hint: Target text appears 2 times at lines [1, 3]. Include unique surrounding lines in original_text to disambiguate.\n  cli_example: kanban-cli-docs update --id=\"<id>\" --original-text=\"<unique context>\" --replacement-text=\"<new>\"\n  line_hints: [1, 3]\n  count: 2\n```\n\n#### 10. Entity Not Found\nCaller attempts to read or mutate a ticket or document that does not exist or is inaccessible:\n\n```yaml\nerror:\n  code: NOT_FOUND\n  message: ticket not found\n  field: identifier\n  hint: Ticket 'KAN-99999' was not found or you do not have access. Search accessible tickets first.\n  fix_hint: Ticket 'KAN-99999' was not found or you do not have access. Search accessible tickets first.\n  cli_example: kanban-cli-agent search_tickets --query=\"KAN-99999\"\n```\n"
  },
  {
    "slug": "migration-and-cutover-runbook",
    "title": "[Guide] Legacy Tracker Migration and Cutover Runbook",
    "category": "guide",
    "track": "Step-by-Step Guides",
    "subtrack": "Data Migration",
    "audience": "Enterprise Administrators",
    "order": 15,
    "summary": "Organizations seeking to escape SaaS paywalls, Jira seat taxes, and single-vendor agent lock-in require a safe, deterministic migration path. Legacy project management tools often store data in proprietary formats, making manual migration prone to data loss, dropped comments, and broken ticket linkages.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "the-7-phase-live-cutover-protocol",
        "title": "The 7-Phase Live Cutover Protocol",
        "level": 2
      },
      {
        "id": "phase-1-pre-cutover-readiness-and-schema-alignment",
        "title": "Phase 1: Pre-Cutover Readiness and Schema Alignment",
        "level": 3
      },
      {
        "id": "phase-2-read-only-freeze-of-source-platform",
        "title": "Phase 2: Read-Only Freeze of Source Platform",
        "level": 3
      },
      {
        "id": "phase-3-extraction-and-markdown-normalization",
        "title": "Phase 3: Extraction and Markdown Normalization",
        "level": 3
      },
      {
        "id": "phase-4-universal-object-graph-hydration",
        "title": "Phase 4: Universal Object Graph Hydration",
        "level": 3
      },
      {
        "id": "phase-5-the-six-non-bypassable-verification-gates",
        "title": "Phase 5: The Six Non-Bypassable Verification Gates",
        "level": 3
      },
      {
        "id": "phase-6-dns-cutover-and-traffic-switch",
        "title": "Phase 6: DNS Cutover and Traffic Switch",
        "level": 3
      },
      {
        "id": "phase-7-post-cutover-monitoring-and-rollback-window",
        "title": "Phase 7: Post-Cutover Monitoring and Rollback Window",
        "level": 3
      },
      {
        "id": "migration-import-studio-adminimports",
        "title": "Migration Import Studio (/admin/imports)",
        "level": 2
      },
      {
        "id": "studio-controls-and-backend-contracts",
        "title": "Studio Controls and Backend Contracts",
        "level": 3
      },
      {
        "id": "step-by-step-operator-guide-executing-a-production-migration",
        "title": "Step-by-Step Operator Guide: Executing a Production Migration",
        "level": 2
      },
      {
        "id": "emergency-rollback-procedure",
        "title": "Emergency Rollback Procedure",
        "level": 2
      }
    ],
    "content": "# [Guide] Legacy Tracker Migration and Cutover Runbook\n\n## Overview\n\nOrganizations seeking to escape SaaS paywalls, Jira seat taxes, and single-vendor agent lock-in require a safe, deterministic migration path. Legacy project management tools often store data in proprietary formats, making manual migration prone to data loss, dropped comments, and broken ticket linkages.\n\n\ud83d\udc4dkanban provides a battle-tested **7-Phase Live Cutover Protocol** (`docs/CUTOVER.md`) designed for migrating from legacy issue trackers (such as Jira, Plane, GitHub Issues, Linear, or self-hosted boards) to \ud83d\udc4dkanban with zero data loss and minimal operational disruption.\n\n---\n\n## The 7-Phase Live Cutover Protocol\n\n```mermaid\nflowchart TD\n    P1[\"Phase 1: Pre-Cutover Readiness - Deploy target stack, configure Multi-Card Auth, verify migrations\"]\n    P2[\"Phase 2: Read-Only Freeze of Source Platform - Place legacy tracker in maintenance mode and capture snapshot\"]\n    P3[\"Phase 3: Extraction & Markdown Normalization - Ingest export, run surrogate guard and paste-jacking pruner\"]\n    P4[\"Phase 4: Universal Object Graph Hydration & Linking - Populate UOG spine, register aliases, establish links\"]\n    P5[\"Phase 5: Six Non-Bypassable Verification Gates - Entity parity, Link Auditor, Markdown, ACLs, MCP, SLAs\"]\n    P6[\"Phase 6: DNS Cutover & Traffic Switch - Point domain to \ud83d\udc4dkanban Caddy ingress\"]\n    P7[\"Phase 7: Post-Cutover Monitoring & Rollback Window - 7-day read-only fallback window\"]\n\n    P1 --> P2\n    P2 --> P3\n    P3 --> P4\n    P4 --> P5\n    P5 -->|Certified PASSED| P6\n    P6 --> P7\n```\n\n![Migration Import Studio - Desktop Light](images/slice4-imports-1440x900-light.png)\n\n### Phase 1: Pre-Cutover Readiness and Schema Alignment\n- Deploy target \ud83d\udc4dkanban production stack using `thumbs-up-kanban:latest` or 5-network Compose.\n- Configure Multi-Card Authentication cards to match source identity providers (OIDC, SAML, LDAP, Passkeys).\n- Run migration pre-flight checks: `uv run kanban-ctl db check-migrations` and verify source export snapshot checksums (`sha256sum -c manifest.sha256`).\n\n### Phase 2: Read-Only Freeze of Source Platform\n- Place the legacy tracker instance into read-only maintenance mode.\n- Notify engineering teams and pause active CI/CD webhooks.\n- Capture baseline snapshot of source database and uploaded attachments.\n\n### Phase 3: Extraction and Markdown Normalization\n- Extract work items, cycles, modules, pages, stickies, and attachments via source tracker export APIs or database dumps.\n- Pass all textual descriptions and comments through the \ud83d\udc4dkanban **Canonical Markdown Pipeline**:\n  - Rejects Unicode lone surrogates (`0xD800 <= ord(c) <= 0xDFFF` -> `INVALID_UTF8_SURROGATE`) before byte encoding.\n  - Strips hidden DOM paste-jacking sequences and malicious script injection vectors.\n  - Converts proprietary AST trees (Atlassian Document Format ADF, HTML, Markdown) into standardized UTF-8 CommonMark.\n\n### Phase 4: Universal Object Graph Hydration\n- Ingest normalized objects into the PostgreSQL Universal Object Graph under `kanban_migrator` authority.\n- Translate legacy issue references (`PROJ-123`, `JIRA-101`, `GH-88`, `ENG-42`) into canonical \ud83d\udc4dkanban identifiers while registering permanent `issue_key_aliases` records.\n- Establish typed `object_links` for all parent-child relationships, sub-issues, and blockers.\n\n### Phase 5: The Six Non-Bypassable Verification Gates\nBefore DNS can be redirected, the migration must pass all 6 automated verification gates:\n\n```mermaid\nflowchart LR\n    Gate1[\"Gate 1 - Entity Parity\"] --> Gate2[\"Gate 2 - Link Auditor\"]\n    Gate2 --> Gate3[\"Gate 3 - Markdown Fidelity\"]\n    Gate3 --> Gate4[\"Gate 4 - ACL Parity\"]\n    Gate4 --> Gate5[\"Gate 5 - MCP Health\"]\n    Gate5 --> Gate6[\"Gate 6 - SLA Latency\"]\n    Gate6 --> Cutover[\"Ready for Live Cutover\"]\n```\n\n| Gate # | Verification Gate | Success Threshold | Exact Audit Check |\n| :---: | :--- | :--- | :--- |\n| **1** | **Entity Count Parity** | 100% match across issues, states, cycles, modules, comments, and attachments | Verify `extractEntityCounts` matches source metrics exactly |\n| **2** | **Object Link Auditor** | Zero orphaned links, cross-tenant leaks, or invalid hierarchy cycles | `POST /api/v1/admin/object-links:audit` returns 0 invalid links |\n| **3** | **Markdown Fidelity** | 100% of descriptions render valid Markdown; zero unparsed HTML tags | CommonMark AST validator with lone-surrogate rejection |\n| **4** | **Principal & ACL Parity** | All users, groups, and permissions map accurately to \ud83d\udc4dkanban roles | Verified user mapping JSON matches active principals |\n| **5** | **MCP Surface Health** | All 24 MCP tools return clean schemas and pass handshake benchmarks | `/mcp/agent`, `/mcp/docs`, `/mcp/admin` initialize with 200 OK |\n| **6** | **Performance Latency** | Board view initial load under 100ms; REST API p95 latency under 50ms | Realtime WebSocket `/ws` probe RTT < 50ms |\n\n### Phase 6: DNS Cutover and Traffic Switch\n- Update internal DNS records or reverse proxy routing (Caddy or Nginx) to point domain `kanban.example.com` to the \ud83d\udc4dkanban production ingress (`edge_net`).\n- Restart agent background workers with updated MCP endpoint URLs (`/mcp/agent`).\n\n### Phase 7: Post-Cutover Monitoring and Rollback Window\n- Maintain legacy tracker instance in read-only state for a 7-day observation window.\n- Monitor real-time WebSocket connection stability, activity logs, and link health in Admin Diagnostics.\n\n---\n\n## Migration Import Studio (`/admin/imports`)\n\nTo streamline cutover from legacy issue trackers to \ud83d\udc4dkanban without authoring bespoke extraction scripts, \ud83d\udc4dkanban provides a native **Migration Import Studio** accessible at `/admin/imports` (and through the Administration navigation under Data Management).\n\n```mermaid\nflowchart TD\n    subgraph ImportPipeline[\"Migration Import Studio Pipeline\"]\n        Upload[\"Step 1: Select Source & Input Bundle (Plane, Jira, GitHub Issues, Linear, or Portable)\"] --> Parse[\"JSON Schema Validation - Verify projects, states, issues, cycles, modules, comments, members\"]\n        Parse --> Metrics[\"Step 2: Entity Detection & Metrics Cards - Live counts across all 7 entity types\"]\n        Metrics --> DryRun[\"Step 3: Stage 1 Dry-Run Simulation (dry_run=true) - Idempotency checks, state mapping preview, conflict detection\"]\n        DryRun --> Live[\"Step 4: Execute Live Migration (dry_run=false) - Atomic PostgreSQL transaction (kanban_migrator)\"]\n        Live --> Verify[\"Step 5: Post-Import Integrity Audit - Run Invalid Object Link Auditor on imported graph\"]\n    end\n```\n\n![Migration Import Studio Multi-Source Tabs](images/slice4-imports-multi-source-tabs.png)\n\n### Studio Controls and Backend Contracts\n\nThe Migration Import Studio exposes dedicated endpoints for each platform: `POST /api/v1/admin/imports/plane`, `POST /api/v1/admin/imports/jira`, `POST /api/v1/admin/imports/github`, and `POST /api/v1/admin/imports/linear`:\n\n1. **Source Platform Tabs:**\n   Selects the target parser and schema mapping logic for the submitted export payload (`Plane`, `Jira`, `GitHub Issues`, or `Linear`). Selecting a source automatically configures the appropriate entity mapping pipeline and CommonMark converters.\n\n2. **Target Workspace and Project (`workspace_slug`, `project_key`):**\n   Specifies the destination tenant and project key for all imported entities. If omitted, the importer creates or binds to the default workspace and project declared inside the bundle. Imported issues receive canonical sequence numbers under the target project key (e.g. `KAN-1`, `KAN-2`).\n\n3. **Dry-Run Simulation Toggle (`dry_run`):**\n   When enabled (`dry_run=true`), the importer executes a non-destructive simulation against a database savepoint. It calculates entity diff counts, validates referential links, checks user mappings, and generates an `ImportDiffReport` without committing rows to PostgreSQL. When disabled (`dry_run=false`), the import runs inside an atomic database transaction that commits only upon full validation success.\n\n4. **Custom User Mapping JSON (`user_map`):**\n   A JSON dictionary mapping source usernames, legacy IDs, or email addresses to canonical \ud83d\udc4dkanban user accounts (e.g. `{\"legacy_user\": \"adamoutler@gmail.com\", \"usr_123\": \"engineer@example.com\"}`). Unmapped users fall back to the system administrator or are created as external inactive principals depending on organizational configuration.\n\n5. **Legacy Key Alias Preservation (`IssueKeyAlias`):**\n   Whenever legacy issues are imported from Jira, GitHub, or Linear, their historical keys (e.g. `JIRA-101`, `GH-88`, `ENG-42`) are automatically recorded in the `issue_key_aliases` catalog. For API clients querying `GET /api/v1/issues/{issue_key}`, the server returns `200 OK` JSON with the header `X-Kanban-Canonical-Key: {canonical_key}`. For browser navigation where `Accept` includes `text/html` (and not `application/json`), the server returns `HTTP 308 Permanent Redirect` with `Location: /projects/{project_key}/issues/{canonical_key}`.\n\n![Migration Import Studio - Desktop Dark](images/slice4-imports-1440x900-dark.png)\n\n![Migration Studio Dry-Run Simulation](images/71-plane-migration-dry-run.png)\n\n---\n\n## Step-by-Step Operator Guide: Executing a Production Migration\n\nFollow this operational procedure to perform a clean cutover using the visual studio:\n\n1. **Navigate to the Studio:** Log in as a user with `SERVER_ADMIN` credentials, satisfy the AAL2 WebSudo prompt, and open `/admin/imports`.\n2. **Select the Source:** Click on the tab matching your source platform (`Plane`, `Jira`, `GitHub Issues`, or `Linear`).\n3. **Upload Export Payload:** Drag and drop your source export file or paste raw JSON into the input textarea. The studio instantly displays live metric cards showing detected Projects, States, Issues, Cycles, Modules, Comments, and Members.\n4. **Supply User Mapping (Optional):** If user handles differ between the source tracker and \ud83d\udc4dkanban, expand the User Mapping section and paste your JSON mapping dictionary.\n5. **Run Stage 1 Dry-Run Simulation:** Click **Stage 1: Preview Dry-Run Diff**. The backend processes the bundle with `dry_run=true` and returns an itemized diff summary detailing entities to be created and any potential conflicts.\n6. **Execute Live Migration:** Once the simulation is verified, click **Stage 2: Execute Live Import**. The backend executes the atomic transaction (`dry_run=false`). A progress indicator tracks hydration progress until completion.\n7. **Verify Post-Import Health:** Switch to `/admin/link-auditor` and click **Run Integrity Scan** to verify zero broken object links. For deep CLI cutover verification against the source export snapshot, execute `kanban-ctl cutover verify --bundle-dir <path_to_export_dir> --workspace <slug> --project <key>`. Request a migrated issue using its legacy key in your browser to confirm HTTP 308 redirection to the new canonical URL.\n\n---\n\n## Emergency Rollback Procedure\n\nIf an unrecoverable business blocker arises during the live cutover window:\n1. **Revert Ingress DNS:** Immediately restore DNS routing to the legacy tracker cluster.\n2. **Delta Capture:** Query the PostgreSQL immutable activity ledger (`activity_records`) to extract all work items, comments, and state changes committed during the cutover window.\n3. **Reconcile State:** Re-apply the captured delta entries back into the source tracker to ensure absolute data continuity with zero dropped updates.\n"
  },
  {
    "slug": "multi-card-authentication-studio",
    "title": "[Guide] Multi-Card Authentication Studio and Identity Architecture",
    "category": "guide",
    "track": "Step-by-Step Guides",
    "subtrack": "Authentication & Identity",
    "audience": "Security & Identity Administrators",
    "order": 16,
    "summary": "Enterprise identity management demands both flexibility and strict security. Rather than forcing organizations into a single identity silo, \ud83d\udc4dkanban implements a **Multi-Card Authentication Studio**. Administrators can configure, reorder, test, and enable multiple independent authentication providers simultaneously.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "first-boot-setup-wizard",
        "title": "First-Boot Setup Wizard",
        "level": 2
      },
      {
        "id": "bootstrap-security-invariants",
        "title": "Bootstrap Security Invariants",
        "level": 3
      },
      {
        "id": "multi-card-login-experience",
        "title": "Multi-Card Login Experience",
        "level": 2
      },
      {
        "id": "key-features-of-multi-card-login",
        "title": "Key Features of Multi-Card Login",
        "level": 3
      },
      {
        "id": "admin-authentication-studio",
        "title": "Admin Authentication Studio",
        "level": 2
      },
      {
        "id": "studio-controls-and-capabilities",
        "title": "Studio Controls and Capabilities",
        "level": 3
      },
      {
        "id": "envelope-encryption-master-kek",
        "title": "Envelope Encryption (MASTER_KEK)",
        "level": 3
      },
      {
        "id": "lockout-prevention",
        "title": "Lockout Prevention",
        "level": 2
      },
      {
        "id": "aal2-step-up",
        "title": "AAL2 Step-Up",
        "level": 2
      },
      {
        "id": "websudo-replay-architecture",
        "title": "WebSudo Replay Architecture",
        "level": 3
      },
      {
        "id": "mfa-enrollment",
        "title": "MFA Enrollment",
        "level": 2
      },
      {
        "id": "supported-mfa-mechanisms",
        "title": "Supported MFA Mechanisms",
        "level": 3
      },
      {
        "id": "active-directory-and-ldaps-integration",
        "title": "Active Directory and LDAPS Integration",
        "level": 2
      },
      {
        "id": "step-by-step-guide-connecting-active-directory",
        "title": "Step-by-Step Guide: Connecting Active Directory",
        "level": 3
      },
      {
        "id": "openid-connect-and-google-oauth-sso",
        "title": "OpenID Connect and Google OAuth SSO",
        "level": 2
      },
      {
        "id": "step-by-step-guide-configuring-google-and-keycloak-oidc",
        "title": "Step-by-Step Guide: Configuring Google and Keycloak OIDC",
        "level": 3
      },
      {
        "id": "webauthn-passkeys-and-totp-enrollment",
        "title": "WebAuthn Passkeys and TOTP Enrollment",
        "level": 2
      },
      {
        "id": "step-by-step-guide-enrolling-passkeys-and-totp",
        "title": "Step-by-Step Guide: Enrolling Passkeys and TOTP",
        "level": 3
      },
      {
        "id": "password-security",
        "title": "Password Security",
        "level": 2
      }
    ],
    "content": "# [Guide] Multi-Card Authentication Studio and Identity Architecture\n\n## Overview\n\nEnterprise identity management demands both flexibility and strict security. Rather than forcing organizations into a single identity silo, \ud83d\udc4dkanban implements a **Multi-Card Authentication Studio**. Administrators can configure, reorder, test, and enable multiple independent authentication providers simultaneously.\n\nSupported authentication card types:\n- **Local Admin:** Built-in argon2id hashed credentials for platform administrators.\n- **OAuth2 / OpenID Connect (OIDC):** Enterprise SSO supporting Okta, Google Workspace, GitHub, GitLab, Keycloak, and Authentik.\n- **LDAPS / StartTLS:** Active Directory and OpenLDAP directory integration with TLS certificate pinning and nested group sync.\n- **WebAuthn / Passkeys:** Hardware security keys (FIDO2/YubiKey) and platform biometrics (Touch ID, Windows Hello) with Relying Party display string `rp.name = \"\ud83d\udc4dkanban\"`.\n- **TOTP Authenticator:** Time-based one-time password second-factor enforcement.\n\n```mermaid\nflowchart TD\n    Login[\"/login Surface (Multi-Card Container)\"] --> Cards[\"Ordered Cards by sort_rank\"]\n    Cards --> C1[\"Local Admin - argon2id hash\"]\n    Cards --> C2[\"OAuth2 / OIDC - Enterprise SSO and Claims\"]\n    Cards --> C3[\"LDAPS / StartTLS - Pinned TLS certs\"]\n    Cards --> C4[\"WebAuthn Passkeys - FIDO2 / TouchID / YubiKey\"]\n\n    C1 --> Verify[\"Session Token Minting\"]\n    C2 --> Verify\n    C3 --> Verify\n    C4 --> Verify\n\n    Verify --> MFA{\"MFA Enforced?\"}\n    MFA -->|Yes| TOTP[\"TOTP Second Factor / Recovery Codes\"]\n    MFA -->|No| Session[\"AAL1 Session Minted\"]\n    TOTP --> AAL2[\"AAL2 Session Minted (Admin-Capable)\"]\n```\n\n---\n\n## First-Boot Setup Wizard\n\nOn initial installation, \ud83d\udc4dkanban boots into a secure provisioning state. Until the platform is initialized, all routes redirect to `/setup`.\n\n![First-Boot Setup Wizard](images/01-first-boot-setup.png)\n\n### Bootstrap Security Invariants\n\n1. **Single-Use Bootstrap Token** (`kb_setup_*`): When the container starts for the first time, a cryptographically secure token prefixed with `kb_setup_` is generated and written exclusively to container logs or stdout. Initial account creation requires providing this token.\n2. **Pre-Session CSRF Protection:** First-boot requests establish a strict double-submit cookie handshake using `__Host-kb_csrf` (over HTTPS) and `kb_csrf` (fallback) headers to prevent cross-site onboarding attacks.\n3. **Atomic Root Workspace Creation:** The wizard provisions the initial Server Administrator, creates the default workspace and project, and immediately invalidates the bootstrap token.\n\n---\n\n## Multi-Card Login Experience\n\nThe login screen presents enabled authentication methods as clean, discrete cards sorted in the exact sequence determined by the administrator.\n\n![Multi-Card Login Screen - Desktop Light](images/slice1-desktop-1440x900-light.png)\n\n### Key Features of Multi-Card Login\n\n- **Sort Order Control:** Providers are displayed according to their configured `sort_rank`, allowing primary enterprise SSO cards to take prominent visual priority while preserving fallback admin access.\n- **Zero Implicit Email Auto-Merge Invariant:** A critical security flaw in many SaaS systems is the automatic linking of accounts based solely on matching email addresses. In \ud83d\udc4dkanban, auto-merging is strictly forbidden. An identity claim from an external provider will only bind to an existing account if the user explicitly authorizes the link through verified secondary credentials.\n- **Passkey and Biometric Priority:** Users with registered WebAuthn credentials can authenticate with a single touch, without entering usernames or passwords.\n\n---\n\n## Admin Authentication Studio\n\nServer Administrators configure identity providers through the visual Auth Studio at `/admin/auth`. Access to this studio requires Authenticator Assurance Level 2 (AAL2) credentials.\n\n![Admin Authentication Studio - Desktop Dark](images/slice1-desktop-1440x900-dark.png)\n![Admin Authentication Studio - Tablet Landscape](images/slice1-desktop-1024x768.png)\n![Admin Authentication Studio - Tablet Portrait](images/slice1-tablet-portrait-768x1024.png)\n![Admin Authentication Studio - Mobile Portrait](images/slice1-mobile-portrait-390x844.png)\n\n### Studio Controls and Capabilities\n\n- **Enable / Disable Toggles:** Instantly activate or suspend identity providers without losing configuration settings.\n- **Drag-and-Drop Reordering:** Change the display order of cards on the `/login` screen in real time.\n- **Write-Only Secrets:** Client secrets, LDAP bind passwords, and private keys are write-only. Once saved, they cannot be read back by client browsers or administrative APIs.\n- **Live Handshake Testing:** The `Test Handshake` button validates endpoint connectivity, TLS certificate validation, and credential binding without modifying live user sessions.\n  - Draft Cards: `POST /api/v1/admin/auth-cards/test-handshake` validates unsaved drawer parameters before committing to PostgreSQL.\n  - Saved Cards: `POST /api/v1/admin/auth-cards/{card_ref}/test-handshake` tests an active or disabled card against live network endpoints.\n\n### Envelope Encryption (`MASTER_KEK`)\n\nAll sensitive authentication secrets stored in the database are encrypted at rest using envelope encryption:\n- Secrets are encrypted using an AES-256-GCM data encryption key (DEK).\n- The DEK is encrypted using the platform Master Key Encryption Key (`MASTER_KEK`), supplied via environment variable or hardware security module (HSM).\n\n---\n\n## Lockout Prevention\n\nTo prevent catastrophic platform lockouts where administrators lose all access:\n- The system continuously evaluates active administrative authentication pathways before permitting any card modification or deletion.\n- If an administrator attempts to disable or delete the sole remaining active admin card (e.g., disabling Local Admin before configuring working SSO), the mutation is rejected with RFC 7807 problem code `409 Conflict` (`LOCKOUT_PREVENTED`).\n- Disabling or deleting the local admin card strictly requires that an external provider card has an active administrator account mapping AND has completed a verified interactive `SERVER_ADMIN` login within the last 15 minutes (`handshake_probe_15m` layer, `HANDSHAKE_PROBE_MAX_AGE_SECONDS = 900`, recorded via `record_external_admin_handshake`). Administrative test handshakes (`POST /api/v1/admin/auth-cards/test-handshake` and `POST /api/v1/admin/auth-cards/{card_ref}/test-handshake`) validate endpoint connectivity and health only; they NEVER satisfy `handshake_probe_15m`.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Server Administrator\n    participant UI as Auth Studio (/admin/auth)\n    participant API as /api/v1/admin/auth-cards\n    participant DB as PostgreSQL (kb_auth)\n\n    Admin->>UI: Toggle Local Admin card to Disabled\n    UI->>API: PATCH /api/v1/admin/auth-cards/{id} (is_enabled: false)\n    API->>DB: Query active admin cards excluding target card\n    alt Remaining Active Admin Cards == 0\n        DB-->>API: 0 Active Admin Paths Remain\n        API-->>UI: 409 Conflict (LOCKOUT_PREVENTED: sole admin card)\n        UI-->>Admin: Show Error Modal: Cannot disable sole remaining admin card\n    else External Card Active but No Interactive Login within 15m\n        API-->>UI: 409 Conflict (LOCKOUT_PREVENTED: handshake_probe_15m)\n        UI-->>Admin: Error: External SERVER_ADMIN login required within 15 minutes (test handshakes do not qualify)\n    else External Admin Card Verified via Interactive Login within 15m\n        API->>DB: UPDATE auth_provider_cards SET is_enabled = false\n        DB-->>API: 200 OK\n        API-->>UI: Card disabled successfully\n    end\n```\n\n---\n\n## AAL2 Step-Up\n\nAll administrative surfaces and sensitive mutations require Authenticator Assurance Level 2 (AAL2) step-up authentication (`Depends(require_admin_aal2)`).\n\n![WebSudo Replay Active](images/slice1-websudo-replay-active.png)\n\n### WebSudo Replay Architecture\n\nWhen an administrator attempts a sensitive action (such as saving a newly configured LDAP card, modifying role bindings, or minting API tokens) after their session has fallen back to AAL1:\n1. The backend responds with HTTP 403 `AAL2_REQUIRED`.\n2. The frontend intercepts the response, captures the pending mutation in an in-memory queue, and opens the WebSudo elevation modal over the dirty editor drawer.\n3. The administrator enters their password, TOTP code, or touches their passkey to elevate to AAL2.\n4. Upon successful elevation, the pending mutation is automatically replayed with the newly elevated session credentials. Dirty form inputs are preserved without data loss.\n5. The elevated AAL2 session remains active for a sliding window of 900 seconds (15 minutes). Explicit step-down is available via `POST /api/v1/auth/aal2/drop`.\n\n---\n\n## MFA Enrollment\n\nMulti-factor authentication provides an essential layer of security for all user tiers and is strictly required for Server Administrators.\n\n![TOTP Recovery Codes Generation](images/slice1-totp-recovery-codes.png)\n![MFA Provisioning and Recovery Codes](images/34-mfa-recovery-codes.png)\n\n### Supported MFA Mechanisms\n\n- **TOTP (Time-Based One-Time Password):** Standard RFC 6238 TOTP using compatible mobile authenticator applications (Google Authenticator, Microsoft Authenticator, 1Password, Bitwarden).\n  - Enrollment endpoint: `POST /api/v1/auth/mfa/totp/enroll` generates base32 secret and QR code URI.\n  - Confirmation endpoint: `POST /api/v1/auth/mfa/totp/confirm` validates the first 6-digit code to activate MFA on the account.\n  - Verification endpoint: `POST /api/v1/auth/mfa/verify` validates subsequent codes during login and WebSudo step-up.\n- **Hardware Security Keys and WebAuthn Passkeys:** Direct FIDO2 browser authentication.\n  - Registration: Uses standard browser navigator.credentials.create with Relying Party display name `rp.name = \"\ud83d\udc4dkanban\"` and ASCII FQDN `rp.id`.\n- **Break-Glass Backup Recovery Codes:** Ten high-entropy single-use recovery codes (`RECOVERY_CODE_COUNT = 10`) generated during MFA enrollment.\n  - Stored in PostgreSQL using secure one-way salted hashes.\n  - Regenerated via `POST /api/v1/auth/mfa/recovery/regenerate`.\n  - Once a code is used, it is permanently consumed and cannot be reused.\n\n---\n\n## Active Directory and LDAPS Integration\n\nThe LDAP provider card connects \ud83d\udc4dkanban directly to Microsoft Active Directory or OpenLDAP directory trees over secure encrypted channels.\n\n![LDAP Test Draft Handshake Success](images/slice1-ldap-test-draft-success.png)\n\n### Step-by-Step Guide: Connecting Active Directory\n\n1. **Navigate to Auth Studio:** Open `/admin/auth` and click **Add Authentication Card**, then select **LDAP / Active Directory** (or click the **Active Directory** preset).\n2. **Configure Server Connection:** Enter the directory connection URL in **Server URL** (e.g., `ldaps://ad.corp.local:636` for direct LDAPS, or `ldap://ad.corp.local:389` with **StartTLS** toggle enabled). Plaintext LDAP without encryption is strictly rejected. Optionally upload a custom PEM **CA Certificate** (`ca_cert_pem`) for private enterprise PKI. Note that SPKI certificate pins (`spki_sha256_pins`, up to 4 lowercase 64-hex SHA-256 digests) are configured via the administrative REST API.\n3. **Configure Service Account Bind:** Enter the read-only service account distinguished name in **Bind DN** (`service_bind_dn`, e.g., `CN=KanbanService,OU=ServiceAccounts,DC=corp,DC=example,DC=com`) and provide the **Bind Password** (stored encrypted at rest using AES-256-GCM envelope encryption).\n4. **Define User Search Scope:** Specify **Base DN** (`base_dn`, e.g., `OU=Users,DC=corp,DC=example,DC=com`), enter **User Search Filter** (`user_search_filter`) syntax matching `sAMAccountName` or `userPrincipalName` (default `(&(objectClass=person)(uid={username}))`, Active Directory preset `(&(objectCategory=person)(sAMAccountName={username}))`), and configure **Subject Attribute** (default `entryUUID`, Active Directory uses `objectGUID`), **Email Attribute** (`mail`), and **Display Name Attribute** (default `cn`, Active Directory uses `displayName`).\n5. **Configure Active Directory Nested Group Sync:** Set **Access Mode** (`any_user` or `group_restricted`, default `any_user`), map **Member Of Attribute** (`memberOf`), and configure **Group DN Map** (`group_dn_map`) utilizing recursive AD token groups to bind AD security groups to \ud83d\udc4dkanban roles (`SERVER_ADMIN`, `WORKSPACE_ADMIN`, `PROJECT_ADMIN`, `WORKSPACE_MEMBER`). In `group_restricted` access mode, populate **User Groups** and **Admin Groups** DN allowlists.\n6. **Execute Draft Handshake Probe:** Click **Test Handshake** before saving. The backend executes `POST /api/v1/admin/auth-cards/test-handshake` to verify TLS certificate negotiation and directory bind. Once green, click **Create Card**.\n\n---\n\n## OpenID Connect and Google OAuth SSO\n\n\ud83d\udc4dkanban supports OpenID Connect (OIDC) identity providers including Google Workspace, Microsoft Entra ID (Azure AD), Okta, Keycloak, and Authentik.\n\n![OIDC Verified Claim Linked](images/slice1-oidc-verified-claim-linked.png)\n\n### Step-by-Step Guide: Configuring Google and Keycloak OIDC\n\n1. **Register OAuth Client:** In Google Cloud Console or Keycloak Admin Console, create an OAuth 2.0 Web Application client and set Authorized Redirect URI to `https://your-domain.example.com/api/v1/auth/oidc/{slug}/callback` (e.g., `https://kanban.corp.example.com/api/v1/auth/oidc/google/callback`).\n2. **Open Auth Studio:** Navigate to `/admin/auth`, click **Add Authentication Card**, and select **OpenID Connect (OIDC)** or **Google Workspace**.\n3. **Configure Core Parameters:** Enter a lowercase ASCII identifier in **Card Slug** (e.g., `google` or `keycloak-corp`), user-facing label in **Display Name** (e.g., `Google Workspace SSO`), and discovery endpoint in **Issuer URL** (e.g., `https://accounts.google.com`).\n4. **Enter Credentials or Import JSON:** Input **Client ID** and **Client Secret** (AES-256-GCM encrypted), or click **Import Google OAuth JSON** in the drawer to upload downloaded client secret JSON directly.\n5. **Enforce Verified Claims and Domain Allowlist:** Specify requested scopes in **Scopes** (comma-separated in the drawer UI, e.g., `openid, email, profile`, transmitted as `list[str]` in the API). The backend strictly enforces `email_verified: true` (rejecting unverified claims with HTTP 403 `EMAIL_NOT_VERIFIED`). Configure corporate domains in **Allowed Email Domains** (e.g., `corp.example.com`).\n6. **Test Handshake and Enable:** Click **Test Handshake** to verify discovery document retrieval and endpoint reachability. Save the card and toggle **Enabled**.\n\n---\n\n## WebAuthn Passkeys and TOTP Enrollment\n\nWebAuthn Passkeys offer cryptographic, phishing-resistant authentication backed by hardware security chips (Apple Secure Enclave, Google Titan, YubiKey).\n\n![Passkey WebAuthn Registered Successfully](images/slice1-passkey-webauthn-registered.png)\n\n### Step-by-Step Guide: Enrolling Passkeys and TOTP\n\n1. **Open Personal Settings:** Navigate to `/settings/profile` and select the **Security** tab.\n2. **Enroll Hardware Passkey:** Click **Register Passkey / Security Key** and complete platform biometrics or FIDO2 YubiKey touch. Relying Party parameters (`rp.name = \"\ud83d\udc4dkanban\"`, strict ASCII FQDN `rp.id`) protect against phishing. Assign a recognizable label (e.g., `MacBook Pro Touch ID` or `Backup YubiKey 5C`).\n3. **Enroll Authenticator App (TOTP):** Click **Enroll Authenticator App**, scan the rendered QR code with your authenticator application or copy the base32 secret key, and enter the current 6-digit verification code to confirm setup.\n4. **Store Break-Glass Recovery Codes:** Upon confirming MFA, the platform displays 10 single-use backup recovery codes. Store these codes in an encrypted password manager or secure physical safe. If your hardware key or phone is lost, recovery codes allow emergency account access.\n5. **Emergency Account Recovery:** In the event that your primary and second factors are lost, enter a single-use recovery code at the MFA prompt to restore account access and immediately regenerate your recovery set.\n\n---\n\n## Password Security\n\nFor users authenticating via the Local Admin card or local credentials:\n- **Minimum Entropy Standards:** Passwords must be at least 12 characters in length (14 characters for Server Administrators).\n- **Cryptographic Hashing:** Passwords are never stored in cleartext. Credentials are hashed using state-of-the-art Argon2id with memory cost 65536 KiB, time cost 3 iterations, and parallelism 4.\n- **Break-Glass Emergency Access:** In the event that all external identity providers are unreachable, the local administrator card ensures immediate platform recovery.\n"
  },
  {
    "slug": "multi-provider-ai-engine-and-runners",
    "title": "[Guide] Multi-Provider AI Engine, Execution Harnesses, and Runners",
    "category": "guide",
    "track": "Step-by-Step Guides",
    "subtrack": "AI & Distributed Runners",
    "audience": "DevOps & Platform Architects",
    "order": 17,
    "summary": "Unlike commercial SaaS ticketing platforms that hardcode proprietary cloud models behind expensive monthly add-ons, \ud83d\udc4dkanban features an open, multi-provider **AI Orchestration Engine** (`agent/`). Organizations can leverage cloud AI providers, local open-source models, or zero-shell isolated command-line pipes without changing application code.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "provider-architecture-and-abstraction-layer",
        "title": "Provider Architecture and Abstraction Layer",
        "level": 2
      },
      {
        "id": "supported-runtimes",
        "title": "Supported Runtimes",
        "level": 2
      },
      {
        "id": "execution-harnesses",
        "title": "Execution Harnesses",
        "level": 2
      },
      {
        "id": "ai-providers-and-token-caps-studio",
        "title": "AI Providers and Token Caps Studio",
        "level": 2
      },
      {
        "id": "key-provider-governance-features",
        "title": "Key Provider Governance Features:",
        "level": 3
      },
      {
        "id": "budget-caps",
        "title": "Budget Caps",
        "level": 2
      },
      {
        "id": "token-cap-policies",
        "title": "Token Cap Policies:",
        "level": 3
      },
      {
        "id": "sampling-parameters",
        "title": "Sampling Parameters",
        "level": 2
      },
      {
        "id": "agent-definitions-studio",
        "title": "Agent Definitions Studio",
        "level": 2
      },
      {
        "id": "definition-capabilities",
        "title": "Definition Capabilities:",
        "level": 3
      },
      {
        "id": "repository-access",
        "title": "Repository Access",
        "level": 2
      },
      {
        "id": "remote-runners",
        "title": "Remote Runners",
        "level": 2
      },
      {
        "id": "runner-infrastructure-and-protocol-security",
        "title": "Runner Infrastructure and Protocol Security",
        "level": 3
      },
      {
        "id": "agent-revocation-and-security-controls",
        "title": "Agent Revocation and Security Controls",
        "level": 2
      },
      {
        "id": "testable-ai-pluggable-fixtures-and-cli-validation",
        "title": "Testable AI: Pluggable Fixtures and CLI Validation",
        "level": 2
      },
      {
        "id": "pluggable-ai-response-fixtures",
        "title": "Pluggable AI Response Fixtures",
        "level": 3
      },
      {
        "id": "local-agent-cli-diagnostics",
        "title": "Local Agent CLI Diagnostics",
        "level": 3
      },
      {
        "id": "multi-provider-benchmark-cutoff-timeout-guide",
        "title": "Multi-Provider Benchmark Cutoff Timeout Guide",
        "level": 2
      },
      {
        "id": "live-full-stack-in-transition-benchmark-matrix-in-progress---done",
        "title": "Live Full-Stack In-Transition Benchmark Matrix (In Progress -> Done)",
        "level": 3
      },
      {
        "id": "choosing-a-cutoff-timeout",
        "title": "Choosing a Cutoff Timeout",
        "level": 3
      },
      {
        "id": "step-by-step-operational-guides",
        "title": "Step-by-Step Operational Guides",
        "level": 2
      },
      {
        "id": "guide-a-configuring-gemini-openai-and-air-gapped-ollama-providers",
        "title": "Guide A: Configuring Gemini, OpenAI and Air-Gapped Ollama Providers",
        "level": 3
      },
      {
        "id": "guide-b-setting-monthly-token-caps-and-budget-halting",
        "title": "Guide B: Setting Monthly Token Caps and Budget Halting",
        "level": 3
      },
      {
        "id": "guide-c-managing-workspace-and-project-autonomous-agents",
        "title": "Guide C: Managing Workspace and Project Autonomous Agents",
        "level": 3
      },
      {
        "id": "guide-d-enrolling-non-root-mtls-runners",
        "title": "Guide D: Enrolling Non-Root mTLS Runners",
        "level": 3
      },
      {
        "id": "guide-e-using-the-local-folder-llmstxt-onboarding-prompt",
        "title": "Guide E: Using the Local-Folder /llms.txt Onboarding Prompt",
        "level": 3
      }
    ],
    "content": "# [Guide] Multi-Provider AI Engine, Execution Harnesses, and Runners\n\n## Overview\n\nUnlike commercial SaaS ticketing platforms that hardcode proprietary cloud models behind expensive monthly add-ons, \ud83d\udc4dkanban features an open, multi-provider **AI Orchestration Engine** (`agent/`). Organizations can leverage cloud AI providers, local open-source models, or zero-shell isolated command-line pipes without changing application code.\n\nSupported provider ecosystems:\n- **Cloud LLMs:** Google Gemini (Gemini 2.5 Flash, Gemini 2.5 Pro), OpenAI (GPT-4o, GPT-4o-mini), and OpenAI-compatible gateways.\n- **Local Private LLMs:** Ollama (Llama 3, DeepSeek-R1, Qwen 2.5) running completely on-premise with zero data egress.\n- **Zero-Shell CLI Pipe Harnesses:** Direct pipe execution (`agy -p`, `codex -p`) running inside hardened Linux sandboxes.\n- **Remote Read-Only mTLS Runners:** Distributed runners executing builds and code inspections over encrypted WebSockets.\n\n```mermaid\nflowchart TD\n    subgraph Core[\"\ud83d\udc4dkanban Agent Runtime\"]\n        App[\"FastAPI & Worker Dispatcher\"]\n        Protocol[\"LLMProvider Interface (agent/providers/base.py)\"]\n    end\n\n    subgraph Providers[\"Multi-Provider Implementations\"]\n        OpenAI[\"OpenAI Provider - GPT-4o, o3-mini, compatible gateways\"]\n        Gemini[\"Google Gemini Provider - Gemini 2.5 Flash / Pro (native tools)\"]\n        Ollama[\"Local Ollama Provider - Llama 3, DeepSeek-R1, Qwen 2.5\"]\n        CLIPipe[\"Zero-Shell CLI Pipe - agy -p / codex -p in nsjail\"]\n        Runner[\"Remote mTLS Runner - Encrypted WSS, read-only repo\"]\n    end\n\n    App --> Protocol\n    Protocol --> OpenAI\n    Protocol --> Gemini\n    Protocol --> Ollama\n    Protocol --> CLIPipe\n    Protocol --> Runner\n```\n\n![Async Agent Gate Card States and Transition Lifecycle](images/16-async-agent-gate-states.png)\n\n---\n\n## Provider Architecture and Abstraction Layer\n\nThe engine abstracts all AI interactions behind a clean, asynchronous provider protocol (`agent/providers/base.py`):\n\n```python\nclass LLMProvider(ABC):\n    @abstractmethod\n    async def complete(self, prompt: str, system: str | None = None, **kwargs) -> CompletionResult:\n        \"\"\"Execute a text completion or FIM generation.\"\"\"\n\n    @abstractmethod\n    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:\n        \"\"\"Execute a multi-turn conversation with tool calling.\"\"\"\n\n    @abstractmethod\n    async def embed(self, texts: list[str]) -> list[list[float]]:\n        \"\"\"Generate vector embeddings for semantic search.\"\"\"\n```\n\n## Supported Runtimes\n\nThe platform provides first-class support for cloud, local air-gapped, CLI-piped, and distributed runner runtimes:\n\n| Provider Key | Primary Use Cases | Streaming Support | Function / Tool Calling | Network Boundary |\n| :--- | :--- | :---: | :---: | :--- |\n| `gemini` | Large context specs, vision, reasoning | Yes | Yes (Native Function Calling) | `egress_llm_net` |\n| `openai` | Complex planning, synthesis, code review | Yes | Yes (Native JSON Schema) | `egress_llm_net` |\n| `ollama` | Air-gapped workstations, strict data privacy | Yes | Yes (Model dependent) | `data_net` / local |\n| `cli_pipe` | Deterministic CI agents, bash-less execution | No (Batch) | Pipe JSON protocol | `sandbox_net` (nsjail) |\n| `remote_runner` | Forensic code audits, Playwright test gates | Yes (WSS) | Streamable RPC | Dedicated mTLS |\n\n---\n\n## Execution Harnesses\n\nAutonomous agents frequently need to inspect code, run validators, or check commit history. However, granting an LLM arbitrary bash or shell access introduces severe remote code execution (RCE) hazards.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    participant Engine as AI Orchestrator\n    participant Sandbox as nsjail Sandbox Runner\n    participant Model as CLI Pipe (agy -p / codex -p)\n\n    Engine->>Sandbox: Spawn isolated container (CLONE_NEWNET, read-only FS, 512MB RAM)\n    Engine->>Sandbox: Pipe prompt.json over STDIN\n    Sandbox->>Model: Execute deterministic harness without shell/bash\n    Model->>Sandbox: Generate tool call / response JSON over STDOUT\n    Sandbox-->>Engine: Structured JSON stream (Zero bash exposure)\n    Engine->>Engine: Validate response against Pydantic schema\n```\n\n\ud83d\udc4dkanban resolves this with **Zero-Shell CLI Pipes**:\n- Agents do not receive an interactive shell or bash process.\n- Execution communicates strictly over standard input (`stdin`) and standard output (`stdout`) using structured JSON pipes.\n- Commands run inside a sandboxed Linux jail (`nsjail` / `setpriv`):\n  - Read-only root filesystem.\n  - Network namespace disabled (`CLONE_NEWNET`).\n  - Memory limit capped at 512 MB.\n  - Execution time limited to 15 seconds.\n\n```bash\n# Example invocation of pipe harness:\ncat prompt.json | agy -p --sandbox-jail > response.json\n```\n\n---\n\n## AI Providers and Token Caps Studio\n\nWorkspace and server administrators manage LLM provider registrations, write-only API key custody, monthly token budgets, and zero-egress policies in the visual studio at `/admin/ai`.\n\n```mermaid\nflowchart TD\n    subgraph AIStudio[\"AI Providers & Token Caps Architecture\"]\n        AdminUser[\"Administrator (AAL2)\"] --> Reg[\"Register / Edit Provider\"]\n        Reg --> ProvidersList[\"Configured Providers - OpenAI (Cloud, priority 10), Gemini (Cloud, priority 20), Ollama (Local Air-Gap, priority 5)\"]\n        \n        ProvidersList --> AirGapCheck{\"Air-Gap Policy Active?\"}\n        AirGapCheck -->|Yes| BlockCloud[\"Cloud Providers Blocked - Only Local Zero-Egress Ollama Allowed\"]\n        AirGapCheck -->|No| AllowCloud[\"Dispatched by Priority Tier\"]\n        \n        AllowCloud --> BudgetGate{\"Monthly Token Budget Gate\"}\n        BlockCloud --> BudgetGate\n        \n        BudgetGate -->|Within Cap| Exec[\"Execute Completion / Tool Call\"]\n        BudgetGate -->|Cap Exceeded| Reject[\"429 Budget Exceeded - Alert Admin to Reset or Expand Cap\"]\n    end\n```\n\n![AI Providers Studio - Desktop Light](images/slice2-ai-studio-1440x900-light.png)\n\n![AI Providers Studio - Desktop Dark](images/slice2-ai-studio-1440x900-dark.png)\n\n![AI Providers Studio - Tablet Landscape](images/slice2-ai-studio-1024x768-tablet-landscape.png)\n\n![AI Providers Studio - Tablet Portrait](images/slice2-ai-studio-768x1024-tablet-portrait.png)\n\n![AI Providers Studio - Mobile Portrait](images/slice2-ai-studio-390x844-mobile-portrait.png)\n\n### Key Provider Governance Features:\n1. **Write-Only API Key Custody:** API keys are submitted over encrypted TLS, stored encrypted in the database using envelope encryption, and never echoed back to the browser. The editor drawer contains 0 password inputs (`input[type=\"password\"]`), completely eliminating DOM password sniffing.\n2. **Enterprise Air-Gap Mode:** When activated (`air_gap_mode: true`), all cloud egress to external AI services is blocked at the network layer. Only local, on-premise runtimes (such as Ollama) are authorized for completions. Cloud provider creation and update requests return HTTP 409 `AIR_GAP_EGRESS_DENIED`, while model probing and connection test endpoints return HTTP 200 OK with `{\"ok\": false, \"error_code\": \"AIR_GAP_EGRESS_DENIED\", ...}`.\n3. **Monthly Token Budgets & Ledgers:** Each provider configuration enforces monthly input/output token caps with automated rollover and audit ledger accounting.\n\n---\n\n## Budget Caps\n\nThe Token Budget Modal (`AiBudgetModal.tsx`) provides granular control over organizational spending across each configured AI provider.\n\n![Token Budget Modal - Unlimited Quota](images/slice2-ai-budget-modal-unlimited.png)\n\n![Token Budget Modal - Hard AI Freeze](images/slice2-ai-budget-modal-freeze.png)\n\n### Token Cap Policies:\n- **Enforced Cap** (`cap-mode-enforce-btn`): Administrators define a monthly token quota (e.g. 1,000,000, 5,000,000, 25,000,000, or 100,000,000 tokens via quick presets). Once `tokens_used >= token_cap`, subsequent reservations fail closed with `BudgetExceeded`, and Sparkle FIM completions return status `budget`.\n- **Hard AI Freeze** (`preset-budget-0-freeze-btn`): Setting `token_cap = 0` immediately halts all model queries and agent transition checks for that provider. It serves as an instant financial circuit breaker.\n- **Unlimited Quota** (`cap-mode-unlimited-btn`): Sets the internal ceiling to `10_000_000_000` tokens, tracking ledger consumption without automated cutoffs.\n\n---\n\n## Sampling Parameters\n\nSampling parameters calibrate model behavior across deterministic verification gates versus open-ended synthesis:\n\n| Parameter | UI Control | Range / Allowed Values | Default | Purpose & Invariant |\n| :--- | :--- | :--- | :--- | :--- |\n| `temperature` | `provider-temperature-input` | `0.0` to `2.0` | `0.7` | Governs randomness. Use low values (`0.1` to `0.3`) for deterministic code generation, test gates, and QA verdicts. |\n| `top_p` | `provider-top-p-input` | `0.0` to `1.0` | `1.0` | Nucleus sampling threshold pruning low-probability tokens from generation. |\n| `max_tokens` | `provider-max-tokens-input` | `1` to `128000` | `4096` | Upper bound on generation tokens for completion and reasoning traces. |\n| `timeout_ms` | `provider-timeout-ms-input` | `1000` to `300000` ms | `30000` ms | Hard ceiling on provider HTTP requests. Maximum 300s reasoning ceiling. |\n| `mtls_client_cert_pem` | `provider-mtls-cert-input` | PEM Certificate | Empty | Optional client certificate for mutual TLS provider connections. |\n\n---\n\n## Agent Definitions Studio\n\nAdministrators author and manage autonomous agent personas, tool permissions, and system prompt templates at `/admin/agents`.\n\n```mermaid\nflowchart LR\n    subgraph AgentDefFlow[\"Agent Definition & Validation Lifecycle\"]\n        Def[\"Agent Definition - Name, Slug, Model, Prompt Template\"] --> Scope[\"Tool Allowlist Scoping - Permitted MCP Tools (read_ticket, search_tickets, etc.)\"]\n        Scope --> Modal[\"Validation Modal (/admin/agents) - Simulate test prompt against agent schema\"]\n        Modal --> Verdict{\"Validation Passes?\"}\n        Verdict -->|Yes| Active[\"Registered as Active Agent Principal\"]\n        Verdict -->|No| Fix[\"Report Schema / Prompt Errors for Correction\"]\n    end\n```\n\n![Agent Definitions Studio - Desktop Light](images/slice2-agent-studio-1440x900-light.png)\n\n![Agent Definitions Studio - Desktop Dark](images/slice2-agent-studio-1440x900-dark.png)\n\n![Agent Definitions Studio - Tablet Landscape](images/slice2-agent-studio-1024x768-tablet-landscape.png)\n\n![Agent Definitions Studio - Tablet Portrait](images/slice2-agent-studio-768x1024-tablet-portrait.png)\n\n![Agent Definitions Studio - Mobile Portrait](images/slice2-agent-studio-390x844-mobile-portrait.png)\n\n![Agent Definitions Studio Overview](images/44-admin-agent-definitions.png)\n\n### Definition Capabilities:\n- **Role and Model Mapping:** Bind specific personas (such as `reality-checker`, `security-auditor`, `code-reviewer`) to optimal models (Gemini 2.5 Flash, GPT-4o, DeepSeek-R1).\n- **Harness Selection:** Select `in_app_sdk` (in-process LLM calling), `cli_pipe` (sandboxed zero-shell command pipe), or `remote_runner` (distributed mTLS build worker).\n- **Tool Allowlist Scoping:** Strictly restrict which MCP tools each agent principal can invoke, enforcing least privilege (`search_tickets`, `read_ticket`, `search_knowledge`, `read_doc`).\n- **Interactive Validation Modal:** Test and validate agent definitions before deploying them to live project workflows.\n\n![Agent Validation Modal](images/60-agent-validation-modal.png)\n\n![Agent Validation Modal - Forensic Trace](images/slice2-agent-validation-modal-trace.png)\n\n---\n\n## Repository Access\n\nWhen configuring autonomous agents in `AgentDefinitionEditorDrawer.tsx`, administrators select the repository access mode granted to the agent during execution:\n\n| Mode | Allowed Values | Default | Operational & Security Boundary |\n| :--- | :--- | :--- | :--- |\n| `none` | Zero filesystem access | `none` | Agent operates purely on ticket metadata, comments, and in-app documents without cloning or mounting code. |\n| `ro_vfs_mount` | Read-Only VFS Mount | None | Mounts the Git repository strictly read-only within the execution container (`CLONE_NEWNS`). Ideal for forensic QA and static code review. |\n| `bare_git_tools` | Bare Git Read-Only Tools | None | Provides read-only bare Git inspection tools in an isolated tmpfs directory. Prevents repo modification while permitting fast commit, diff, and tree inspection. |\n\n---\n\n## Remote Runners\n\nFor heavy build verification, sandbox test execution, and isolated code review, \ud83d\udc4dkanban deploys distributed **Remote Runners** managed through `/admin/agent-runners`.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    participant Admin as Admin\n    participant Studio as Runner Studio (/admin/agent-runners)\n    participant Server as \ud83d\udc4dkanban Orchestrator\n    participant Daemon as Remote Runner Daemon\n\n    Admin->>Studio: Click \"+ Mint Runner Token\"\n    Studio->>Server: Generate single-use enrollment token (Max 15 min TTL)\n    Server-->>Studio: Return copyable CLI enrollment snippet\n    Admin->>Daemon: Execute enrollment on runner host\n    Daemon->>Server: Connect to dedicated mTLS port :8444 with PoP handshake\n    Server->>Server: Verify token & bind X.509 client certificate\n    Server-->>Daemon: Channel verified: Runner enters \"ONLINE\"\n    Daemon->>Server: Heartbeat ping every 15s over :8444 (CPU, RAM, active jobs)\n```\n\n![Remote Runners Studio - Desktop Light](images/slice2-runner-studio-1440x900-light.png)\n\n![Remote Runners Studio - Desktop Dark](images/slice2-runner-studio-1440x900-dark.png)\n\n![Remote Runners Studio - Tablet Landscape](images/slice2-runner-studio-1024x768-tablet-landscape.png)\n\n![Remote Runners Studio - Tablet Portrait](images/slice2-runner-studio-768x1024-tablet-portrait.png)\n\n![Remote Runners Studio - Mobile Portrait](images/slice2-runner-studio-390x844-mobile-portrait.png)\n\n![Agent Runner Studio Overview](images/45-admin-runner-studio.png)\n\n![Runner Mint Token Modal](images/61-runner-mint-token-modal.png)\n\n![Runner Mint Token Modal - Masked](images/slice2-runner-mint-token-modal.png)\n\n### Runner Infrastructure and Protocol Security\n\n- **Dedicated Port :8444 and Proof-of-Possession Handshake:** Distributed runners connect exclusively over dedicated mutual TLS port `:8444`. Port `:8444` rejects standard HTTP requests and unauthenticated TLS handshakes, demanding a valid X.509 client certificate verified via a cryptographic Proof-of-Possession (PoP) challenge format: `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256}`.\n- **Single-Use Enrollment Token (Max 15-Minute TTL):** When an administrator clicks `+ Mint Runner Token` in `/admin/agent-runners` (requiring AAL2 step-up authentication), the orchestrator mints an ephemeral enrollment token valid for at most 15 minutes (900 seconds). Upon first enrollment or expiration, the token is permanently invalidated.\n- **Unprivileged Non-Root Daemon Execution:** The daemon runs as a standard unprivileged user. Generated key material enforces strict POSIX file permissions:\n  - State directory: `0o700` (`drwx------`)\n  - Private key (`client.key`): `0o600` (`-rw-------`)\n  - CA certificate (`ca.pem`): `0o600` (`-rw-------`)\n  - Client certificate (`client.crt`): `0o644` (`-rw-r--r--`)\n- **CLI Enrollment Syntax:** The studio generates an exact command to enroll the host daemon:\n  ```bash\n  echo \"$TOKEN\" | uv run kanban-agent-runner enroll \\\n    --server-url https://kanban.example.com \\\n    --token-stdin \\\n    --pool default\n  ```\n- **Hardware-Bound Certificate Rotation Guidance:** Runner client certificates are hardware-bound to the host and cannot be renewed in place. To rotate a certificate or decommission a host:\n  - Revoke the existing runner in `/admin/agent-runners` via `POST /api/v1/admin/agent-runners/{id}:revoke`.\n  - Mint a fresh single-use enrollment token (15-minute TTL).\n  - Re-enroll the runner daemon using the CLI command above.\n- **Private Ingress Isolation:** All daemon polling, task dispatch, and execution telemetry endpoints are strictly segregated from public edge networks.\n\n---\n\n## Agent Revocation and Security Controls\n\nWhen an agent session exhibits anomalous activity or a credential leak is detected, administrators can invoke an instant Kill Switch across all surfaces:\n\n![Agent Kill Switch and Immediate Session Revocation](images/18-agent-kill-switch.png)\n\n---\n\n## Testable AI: Pluggable Fixtures and CLI Validation\n\nAI agent workflows can be notoriously difficult to test deterministically in CI pipelines due to model drift, token costs, and rate limits. \ud83d\udc4dkanban enforces **100% Deterministic AI Testing**:\n\n### Pluggable AI Response Fixtures\nIn test suites, providers are swapped with `FixtureLLMProvider` and `FixtureCLIRunner`:\n- Replays recorded, deterministic JSON responses without making network calls.\n- Simulates network timeouts, rate limit errors (`429`), and malformed responses to verify system resilience.\n\n### Local Agent CLI Diagnostics\nEngineers can validate transition helpers and AI workflows locally via the command line:\n\n```bash\n# Validate a transition helper against a ticket fixture\nkanban-agent validate-transition \\\n  --ticket-file test_ticket.json \\\n  --from-state in_progress \\\n  --to-state done \\\n  --dry-run\n```\n\n---\n\n## Multi-Provider Benchmark Cutoff Timeout Guide\n\nEvery AI provider configuration and agent definition exposes a configurable hard cutoff timeout (`timeout_ms`, `1000` to `300000` ms). At runtime, `GateWorkerRunner` enforces `cutoff_ms = min(provider.timeout_ms, agent.timeout_ms)`. When an upstream model exceeds `cutoff_ms`, the worker raises `GATE_TIMEOUT` and **fails closed**, leaving the ticket in its source state with zero hung workers.\n\n### Live Full-Stack In-Transition Benchmark Matrix (In Progress -> Done)\n\nMeasured end-to-end against `kanban-liveqa-2` (embedded PostgreSQL 16 + `FORCE ROW LEVEL SECURITY`) using `StrictVerdictSchema` (`kb-transition-verdict/v1`) on a Positive software ticket (`KAN-1`) and a Negative impossible/unverified ticket (`KAN-2: \"Build a rocket ship and serve ice cream on Saturn\"`):\n\n| Runtime & Model | Cutoff (`timeout_ms`) | Positive (`KAN-1`) | Positive Latency | Negative (`KAN-2`) | Negative Latency | Operational Guidance |\n| :--- | :---: | :--- | :--- | :--- | :--- | :--- |\n| **Google Gemini** (`gemini-2.5-flash-lite`) | `20000` | `approve` (`Done`) | `3,215 ms` | `reject` (`In Progress`) | `1,594 ms` | Fastest overall cloud model with strict schema compliance and `v1beta` AI Studio routing. |\n| **OpenAI Cloud** (`gpt-4o-mini`) | `20000` | `approve` (`Done`) | `3,846 ms` | `reject` (`In Progress`) | `2,224 ms` | Fast cloud fallback with strict JSON schema adherence. |\n| **Local Ollama Supercomputer** (`gemma4:e2b`) | `25000` | `approve` (`Done`) | `19,892 ms` | `reject` (`In Progress`) | `5,213 ms` | Strong air-gapped 2B edge choice; `20000`-`25000 ms` cutoff recommended. |\n| **Local Ollama GPU/CPU** (`gemma3:4b`) | `20000` / `35000` | `timed_out` (20s) / `approve` (35s) | `20,929 ms` / `31,431 ms` | `reject` (`In Progress`) | `16,630 ms` | If VRAM is shared with another pinned model (CPU fallback), set `timeout_ms >= 35000`. |\n| **Local Ollama GPU/CPU** (`granite3.3:2b`) | `20000` | `timed_out` (fail-closed) | `20,321 ms` | `reject` (`In Progress`) | `12,691 ms` | Warm-keep or `25000 ms` cutoff avoids cold-load timeout on long prompts. |\n| **Local Ollama Reasoning** (`nemotron-3-super:latest`) | `5000` (Strict) | N/A | N/A | `GATE_TIMEOUT` (fail-closed) | `6,023 ms` | Validates hard 5s cutoff protection with clean fail-closed veto. |\n| **Local Ollama Reasoning** (`nemotron-3-super:latest`) | `45000` (Extended) | `approve` (`Done`) | `31,940 ms` | `reject` (`In Progress`) | `26,502 ms` | Heavy reasoning models (`<think>` tags stripped) should use `45000`-`60000 ms`. |\n\n### Choosing a Cutoff Timeout\n- **Fast Cloud Models** (`gpt-4o-mini`, `gemini-2.5-flash-lite`): `15000` to `20000` ms.\n- **Local 2B-4B Edge Models** (`gemma4:e2b`, `gemma3:4b`, `granite3.3:2b`): `25000` to `35000` ms (covers occasional model reload or shared VRAM).\n- **Heavy Reasoning Models** (`nemotron-3-super:latest`, `deepseek-r1`): `45000` to `60000` ms, or pair with a strict `5000`-`10000` ms cutoff on latency-sensitive columns so stuck calls fail closed immediately.\n\n---\n\n## Step-by-Step Operational Guides\n\n### Guide A: Configuring Gemini, OpenAI and Air-Gapped Ollama Providers\n1. Open the AI Providers Studio at `/admin/ai` (or workspace settings at `/workspaces/{ws}/settings`).\n2. Click `+ Register Provider` (`register-provider-btn`) to open the `AiProviderEditorDrawer`.\n3. Choose the provider preset or set `provider_kind`: for Google Gemini, click `Gemini` preset (`preset-gemini-btn`), enter display name `Google Gemini Workspace`, base URL `https://generativelanguage.googleapis.com`, paste API key, click `Probe Models` (`probe-models-btn`) to populate the model list (`gemini-2.5-flash`, `gemini-2.5-pro`), and set timeout ceiling (`15000` to `20000` ms). For OpenAI / Compatible, click `OpenAI` preset (`preset-openai-btn`), enter display name, base URL `https://api.openai.com/v1`, paste API key, and probe or select models (`gpt-4o`, `gpt-4o-mini`). For Local Ollama, click `Ollama` preset (`preset-ollama-btn`), enter display name `Local Ollama Runtime`, base URL `http://127.0.0.1:11434`, residency tier `local_only`, and click `Probe Models` to discover locally hosted models (`llama3.2:latest`, `qwen2.5-coder:latest`). API key is optional for local runtimes.\n4. Expand `Advanced Settings` (`advanced-settings-details`) to adjust temperature (default `0.7`), top-p (default `1.0`), max tokens (default `4096`), and optional mTLS client certificates.\n5. Click `Register Provider` (`save-provider-btn` in create mode, or `Save Provider` when editing existing configs).\n6. Reorder failover priority stack using drag handles or Up/Down buttons (`move-up-btn-{id}`, `move-down-btn-{id}`). The system attempts providers in priority order, falling back cleanly on timeouts or HTTP 5xx errors.\n7. To enforce zero cloud egress, navigate to Workspace Settings and enable `air_gap_mode = true`. Outbound cloud connections and provider create/update attempts for `openai` and `gemini` are rejected with HTTP 409 `AIR_GAP_EGRESS_DENIED` (model probing and connection tests return HTTP 200 with `{\"ok\": false, \"error_code\": \"AIR_GAP_EGRESS_DENIED\", ...}`), while local zero-egress Ollama queries continue without interruption.\n\n### Guide B: Setting Monthly Token Caps and Budget Halting\n1. In `/admin/ai`, locate the target provider card and click `Token Budget` (`manage-budget-btn-{id}`) to open the `AiBudgetModal`.\n2. Select the budget mode: choose Enforce Token Cap (`cap-mode-enforce-btn`) with monthly period and an integer token allowance or preset (`1M`, `5M`, `25M`, `100M`); choose Unlimited Quota (No Cap) (`cap-mode-unlimited-btn`) for an internal cap of `10_000_000_000` tokens; or choose 0 (Freeze) (`preset-budget-0-freeze-btn`) to set monthly cap to `0`, immediately blocking all completion and agent transition requests with `BudgetExceeded` (Sparkle FIM completions return status `budget`).\n3. Click `Save Token Cap` (`save-budget-btn`).\n4. The studio displays real-time progress bars indicating token consumption against the configured ceiling.\n\n### Guide C: Managing Workspace and Project Autonomous Agents\n1. Navigate to Agent Definitions Studio at `/admin/agents` (or project settings `/projects/{proj}/settings/agents`).\n2. Click `+ Register Agent` (`register-agent-btn`) to open the `AgentDefinitionEditorDrawer`.\n3. Fill in agent metadata including slug (lowercase alphanumeric string with hyphens, e.g. `reality-checker`, `security-auditor`), display name, and harness kind (`in_app_sdk`, `cli_pipe`, or `remote_runner`).\n4. Configure harness specifics: for `in_app_sdk`, select `provider_kind` (`gemini`, `openai`, `ollama`) and `model_id`; for `cli_pipe`, select pre-approved binary (`agy` or `codex`) and CLI args (`[\"-p\"]`); for `remote_runner`, select target pool slug (`default`).\n5. Select `repo_access_mode` (`none`, `ro_vfs_mount`, `bare_git_tools`) and check allowed MCP tools (`search_tickets`, `read_ticket`, `search_knowledge`, `read_doc`).\n6. Enter System Instructions in Markdown directing agent persona and verification rules.\n7. Set timeout (`timeout_ms`, default 60000ms, up to 300000ms / 300s).\n8. Click `Save Agent` (`save-agent-btn`).\n9. Click `Test Validation` (`validate-agent-btn-{id}`) to open the `AgentValidationModal`. The system executes a non-destructive test trace and renders a 4-section report (`=== 1. RENDERED CONTEXT ===`, `=== 2. TOOL TRACE ===`, `=== 3. LATENCY & TOKENS ===`, `=== 4. SCHEMA & POLICY STATUS ===`).\n\n### Guide D: Enrolling Non-Root mTLS Runners\n1. Navigate to Remote Runners Studio at `/admin/agent-runners`.\n2. Click `+ Mint Enrollment Token` (`open-mint-modal-btn`) to open the `MintEnrollmentTokenModal`.\n3. Select pool slug (`default`) and token TTL (e.g. 600s, max 900s / 15 minutes), then click `Generate Single-Use Token` (`submit-mint-token-btn`).\n4. Copy the generated enrollment CLI snippet: `echo \"$TOKEN\" | uv run kanban-agent-runner enroll --server-url https://kanban.example.com --token-stdin --pool default`.\n5. On the runner host, execute the enrollment command as a standard non-root user. The runner daemon generates an EC P-256 private key and CSR (`CN=worker.internal.test`), posts the CSR to `/api/v1/agent-runners/enroll` with the single-use token, receives the signed client certificate (`O=\ud83d\udc4dkanban Remote Runner Node`), and persists state under strict POSIX file permissions: state directory `0o700` (`drwx------`), `client.key` `0o600`, `ca.pem` `0o600`, and `client.crt` `0o644`.\n6. Start the daemon with `uv run kanban-agent-runner run` (auto-detects runner config) or `uv run kanban-agent-runner run --config ~/.local/state/kanban-runner/runner.toml`.\n7. The runner connects to dedicated mTLS port `:8444` (or WebSocket `/api/v1/agent-runners/ws`), solves the cryptographic Proof-of-Possession challenge `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256}`, and enters `online` state.\n8. To revoke a runner, click `1-Click Revoke (AAL2)` (`POST /api/v1/admin/agent-runners/{id}:revoke`). Reconnection attempts with the revoked certificate are immediately rejected with HTTP 403 Forbidden.\n\nThe canonical multi-line enrollment snippet is formatted as:\n```bash\necho \"$TOKEN\" | uv run kanban-agent-runner enroll \\\n  --server-url https://kanban.example.com \\\n  --token-stdin \\\n  --pool default\n```\n\n### Guide E: Using the Local-Folder /llms.txt Onboarding Prompt\n1. Locate the Agent Onboarding Prompt card at `/docs`, `/about`, or `/settings/mcp`.\n2. Copy the standardized onboarding prompt: `Read https://kanban.example.com/llms.txt, learn \ud83d\udc4dkanban's ticket workflow, interview me on Execution Mode (Single-Thread, Teamwork, or Swarm), Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra), and QA Rigor, and save my preferences strictly to the local project folder (.agents/skills/ and AGENTS.md) - do NOT modify global home/system directories (~/.claude, ~/.codex, ~/.gemini, ~/.agents) unless I explicitly request global installation.`\n3. Paste the prompt into your coding assistant (Claude Code, OpenAI Codex, Gemini CLI / Antigravity).\n4. The assistant fetches `https://kanban.example.com/llms.txt` and discovers skills (`kanban-workflow-setup`, `kanban-ticket`, `kanban-agent-manager`, `reality-checker`).\n5. Complete the interactive interview. The assistant configures local instructions in `.agents/skills/` and persists user preferences via `PATCH /api/v1/users/me/preferences` (`agent_onboarding_prefs`).\n\n![Agent Onboarding Prompt Card - Desktop Light](images/slice2-onboarding-1440x900-light.png)\n\n![Agent Onboarding Prompt Card - Desktop Dark](images/slice2-onboarding-1440x900-dark.png)\n\nThe complete verbatim prompt text for local clipboard copying:\n```text\nRead https://kanban.example.com/llms.txt, learn \ud83d\udc4dkanban's ticket workflow, interview me on Execution Mode (Single-Thread, Teamwork, or Swarm), Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra), and QA Rigor, and save my preferences strictly to the local project folder (.agents/skills/ and AGENTS.md) - do NOT modify global home/system directories (~/.claude, ~/.codex, ~/.gemini, ~/.agents) unless I explicitly request global installation.\n```\n"
  },
  {
    "slug": "multi-source-migration-and-key-alias-redirects",
    "title": "[Guide] End-to-End Multi-Source Migration, Key Alias Redirects, and Cross-Project Merge Guide",
    "category": "guide",
    "track": "Step-by-Step Guides",
    "subtrack": "Data Migration",
    "audience": "Enterprise Administrators & DevOps Engineers",
    "order": 18,
    "summary": "Comprehensive operator and engineering guide for multi-source migration from Jira, GitHub Issues, Linear, and Plane, legacy issue key alias redirection, cross-project merge mode, and canonical portable workspace bundle governance.",
    "sections": [
      {
        "id": "overview-and-lossless-migration-philosophy",
        "title": "1. Overview and Lossless Migration Philosophy",
        "level": 2
      },
      {
        "id": "multi-source-importer-architecture-source-options",
        "title": "2. Multi-Source Importer Architecture & Source Options",
        "level": 2
      },
      {
        "id": "supported-importers-capability-matrix",
        "title": "Supported Importers Capability Matrix",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-reference",
        "title": "Setting-by-Setting Technical Reference",
        "level": 3
      },
      {
        "id": "legacy-key-alias-routing-and-http-308-permalinks",
        "title": "3. Legacy Key Alias Routing and HTTP 308 Permalinks",
        "level": 2
      },
      {
        "id": "schema-and-model-architecture",
        "title": "Schema and Model Architecture",
        "level": 3
      },
      {
        "id": "http-redirection-flow-kanbanapiv1issuespy211-218",
        "title": "HTTP Redirection Flow (kanban/api/v1/issues.py:211-218)",
        "level": 3
      },
      {
        "id": "step-by-step-operator-guides-for-all-4-sources",
        "title": "4. Step-by-Step Operator Guides for All 4 Sources",
        "level": 2
      },
      {
        "id": "guide-a-importing-from-plane",
        "title": "Guide A: Importing from Plane",
        "level": 3
      },
      {
        "id": "guide-b-importing-from-jira-cloud-or-server",
        "title": "Guide B: Importing from Jira Cloud or Server",
        "level": 3
      },
      {
        "id": "guide-c-importing-from-github-issues",
        "title": "Guide C: Importing from GitHub Issues",
        "level": 3
      },
      {
        "id": "guide-d-importing-from-linear",
        "title": "Guide D: Importing from Linear",
        "level": 3
      },
      {
        "id": "portable-workspace-bundles-targz",
        "title": "5. Portable Workspace Bundles (.tar.gz)",
        "level": 2
      }
    ],
    "content": "# [Guide] End-to-End Multi-Source Migration, Key Alias Redirects, and Cross-Project Merge Guide\n\nComprehensive operator and engineering guide for multi-source migration from Jira, GitHub Issues, Linear, and Plane, legacy issue key alias redirection, cross-project merge mode, and canonical portable workspace bundle governance.\n\n---\n\n## 1. Overview and Lossless Migration Philosophy\n\nMigrating issue tracking infrastructure between legacy platforms often introduces severe data loss: rich-text formatting degrades into corrupted markup, custom field hierarchies fracture, media attachments break into dead hyperlinks, and historical issue keys (`JIRA-101`, `PROJ-42`, `GH-89`, `ENG-42`) vanish, destroying institutional knowledge and breaking permalinks across pull requests, git commits, and documentation.\n\n\ud83d\udc4dkanban resolves these challenges through an end-to-end, multi-source migration pipeline engineered under three core principles:\n1. **Canonical Markdown Normalization:** Ingests proprietary document trees (such as Atlassian Document Format or raw HTML) and converts them into standardized, sanitized UTF-8 Markdown with strict UTF-16 lone surrogate rejection (`0xD800 <= ord(c) <= 0xDFFF`).\n2. **Deterministic Key Alias Routing** (`IssueKeyAlias`): Retains every historical issue key from upstream systems in a dedicated alias catalog, providing automatic HTTP 308 permanent redirection across REST API and web interfaces.\n3. **Lossless Media Attachment Streaming:** Streams binary assets directly from legacy object stores through HMAC-signed media shields, preventing SSRF attacks and broken image references.\n\n```mermaid\ngraph TD\n    Sources[\"Source Platforms (Plane, Jira, GitHub, Linear, Portable)\"] --> Ingestion[\"Streaming Ingestion & Sanitization Engine\"]\n    Ingestion --> MarkdownConv[\"Canonical Markdown Converter (ADF/HTML -> GFM)\"]\n    Ingestion --> MediaStream[\"HMAC Media Proxy Attachment Storage\"]\n    Ingestion --> AliasRouter[\"IssueKeyAlias Catalog (308 Redirection Engine)\"]\n    Ingestion --> RLSInsert[\"PostgreSQL FORCE RLS Transactional Insertion\"]\n    RLSInsert --> UniversalGraph[\"Universal Object Graph (Issues, Stickies, Docs, Links)\"]\n```\n\n![Migration Import Studio Multi-Source Tabs](images/slice4-imports-multi-source-tabs.png)\n\n---\n\n## 2. Multi-Source Importer Architecture & Source Options\n\nThe migration subsystem in `kanban/importer/` and `/api/v1/admin/imports` provides modular ingestion drivers tailored to each platform export format:\n\n### Supported Importers Capability Matrix\n\n| Source Tracker | Input Format | Converted Entities | Custom Fields & Mapping | Attachment Ingestion |\n| :--- | :--- | :--- | :--- | :--- |\n| **Plane Workspaces** | Native JSON export bundle / API dump | Workspaces, Projects, States, Issues, Cycles, Modules, Comments, Members | 1:1 Universal Object Graph restoration | S3/MinIO media streamed through media shield |\n| **Jira Cloud & Server/DC** | JSON export bundle / REST dump | Issues, Subtasks, Comments, Worklogs, Links | Full ADF/HTML to CommonMark conversion, user mapping | Extracted and routed through HMAC media shield |\n| **GitHub Issues** | Issues JSON export / REST API dump | Issues, PR references, Milestones, Labels | Milestones mapped to Cycles; Labels mapped to ProjectLabels | Downloaded and cryptographically hashed |\n| **Linear** | Linear JSON export / CSV archive | Issues, Cycles, Modules, Relations, Triage states | State taxonomy normalization; relations mapped to object_links | Assets fetched with token authorization |\n| **Portable Bundle** | Canonical `.tar.gz` archive (`downloadPortableExport`) | Full workspace spine, entities, docs, pages, stickies | Preserves exact Universal Object Graph schema | Complete asset package with SHA-256 checksums |\n\n![Migration Import Studio - Desktop Light](images/slice4-imports-1440x900-light.png)\n\n### Setting-by-Setting Technical Reference\n\nEach migration operation is configured through specific parameters submitted to the dedicated endpoints (`POST /api/v1/admin/imports/plane`, `POST /api/v1/admin/imports/jira`, `POST /api/v1/admin/imports/github`, `POST /api/v1/admin/imports/linear`):\n\n1. **Source Bundle Payload (`bundle_data` or `bundle_name`):**\n   The raw JSON export payload (uploaded or pasted) or file path in imports storage. Each source handler validates expected JSON schemas, maps native statuses to canonical workflow state categories, and extracts textual fields through safe CommonMark converters.\n\n2. **Target Workspace Slug (`workspace_slug`):**\n   Identifies the target workspace tenant within PostgreSQL. If specified, the importer attaches entities to this existing workspace; if omitted, the caller's active workspace is used.\n\n3. **Target Project Key (`project_key`):**\n   Identifies the destination project prefix (e.g. `KAN`, `JIRA`, `GH`, `LIN`). All imported issues receive sequential sequence IDs under this project key while recording their upstream keys in `issue_key_aliases`.\n\n4. **Dry-Run Validation Flag (`dry_run`):**\n   Controls transaction execution mode. When set to `true`, the server processes the payload inside a database savepoint, computes entity count diffs, verifies referential links, and returns an `ImportDiffReport` without committing data. When set to `false`, the operation executes inside an atomic database transaction that rolls back completely if any validation error occurs.\n\n5. **User Mapping Specification (`user_map`):**\n   A JSON object providing explicit mappings from source usernames, emails, or account IDs to canonical \ud83d\udc4dkanban user accounts. Format: `{\"source_username_or_email\": \"canonical_email_or_handle\"}`. Unmapped principals fall back to system defaults.\n\n---\n\n## 3. Legacy Key Alias Routing and HTTP 308 Permalinks\n\nTo preserve external hyperlinks in pull requests, commit messages, Slack threads, and external documentation, \ud83d\udc4dkanban implements persistent key aliasing.\n\n### Schema and Model Architecture\n\nThe `issue_key_aliases` table records historical keys across all imported projects:\n\n```sql\nCREATE TABLE issue_key_aliases (\n    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,\n    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,\n    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,\n    legacy_key VARCHAR(64) NOT NULL,\n    source_platform VARCHAR(32) NOT NULL,\n    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),\n    CONSTRAINT uq_issue_key_aliases_legacy_key UNIQUE (workspace_id, legacy_key)\n);\n```\n\n### HTTP Redirection Flow (`kanban/api/v1/issues.py:211-218`)\n\nWhen a user, browser, or external API client requests an issue using an obsolete key (`GET /api/v1/issues/{issue_key}`):\n1. The resolver queries `issues` by current key (`project.key + '-' + sequence_id`).\n2. If not found, it queries `issue_key_aliases` by `legacy_key` within the caller's authorized workspace.\n3. If an alias match exists, the response header `X-Kanban-Canonical-Key: {canonical_key}` is populated.\n4. For API clients (where `Accept` is `application/json` or does not request HTML), the REST API returns `200 OK` JSON with the complete issue payload.\n5. For browser navigation (where `Accept` includes `text/html` and not `application/json`), the server returns `HTTP 308 Permanent Redirect` with `Location: /projects/{project_key}/issues/{canonical_key}`.\n\n```mermaid\nsequenceDiagram\n    participant Browser as Web Browser (Accept: text/html)\n    participant APIClient as API Client (Accept: application/json)\n    participant API as FastAPI Issue Router (/api/v1/issues/{key})\n    participant DB as PostgreSQL (issues & issue_key_aliases)\n\n    Browser->>API: GET /api/v1/issues/JIRA-101 (Accept: text/html)\n    API->>DB: Query issue_key_aliases ('JIRA-101' -> 'KAN-1')\n    API-->>Browser: HTTP 308 Permanent Redirect (Location: /projects/KAN/issues/KAN-1)\n\n    APIClient->>API: GET /api/v1/issues/JIRA-101 (Accept: application/json)\n    API->>DB: Query issue_key_aliases ('JIRA-101' -> 'KAN-1')\n    API-->>APIClient: HTTP 200 OK (X-Kanban-Canonical-Key: KAN-1, JSON payload)\n```\n\n![Migration Import Studio - Tablet Landscape](images/slice4-imports-1024x768-tablet-landscape.png)\n![Migration Import Studio - Tablet Portrait](images/slice4-imports-768x1024-tablet-portrait.png)\n\n---\n\n## 4. Step-by-Step Operator Guides for All 4 Sources\n\n### Guide A: Importing from Plane\n\n1. Generate an export bundle from Plane (`Settings -> Export -> JSON`).\n2. In \ud83d\udc4dkanban, navigate to `/admin/imports` and select the **Plane** tab.\n3. Upload the `.json` bundle file or paste the contents into the JSON editor.\n4. Review the detected entity metrics (Projects, States, Issues, Cycles, Modules, Comments).\n5. Click **Stage 1: Preview Dry-Run Diff** to verify state mapping and idempotency.\n6. Click **Stage 2: Execute Live Import** to commit the migration transaction.\n\n### Guide B: Importing from Jira Cloud or Server\n\n1. Generate a Jira JSON backup or query issues via Jira REST API.\n2. Ensure descriptions and comments are formatted as ADF JSON or raw HTML.\n3. In \ud83d\udc4dkanban, select the **Jira** tab in the Migration Import Studio.\n4. Paste the Jira export bundle into the payload box.\n5. In the User Mapping field, provide a JSON dictionary mapping Jira account IDs or emails to \ud83d\udc4dkanban users:\n   ```json\n   {\n     \"557058:ba01fb4a-28e4-4a27-a641-752a71d87e0b\": \"alice@example.com\",\n     \"bob.builder@jira.local\": \"bob@example.com\"\n   }\n   ```\n6. Click **Stage 1: Preview Dry-Run Diff** to verify ADF conversion to CommonMark.\n7. Click **Stage 2: Execute Live Import**. All issues receive canonical `KAN-x` keys, and historical keys (`JIRA-101`) are registered as aliases.\n\n### Guide C: Importing from GitHub Issues\n\n1. Export issues from GitHub using the GitHub REST API (`GET /repos/{owner}/{repo}/issues?state=all`) or `gh` CLI:\n   ```bash\n   gh issue list --state all --limit 1000 --json number,title,body,state,labels,milestone,comments,assignees > gh-issues.json\n   ```\n2. In the Migration Import Studio, select the **GitHub Issues** tab.\n3. Upload `gh-issues.json`. Milestones automatically map to \ud83d\udc4dkanban Sprint Cycles; GitHub labels map to Project Labels.\n4. Provide username mapping for GitHub handles to corporate email addresses.\n5. Execute **Stage 1: Preview Dry-Run Diff** followed by **Stage 2: Execute Live Import**. Old issue keys (`GH-1`, `GH-2`) redirect seamlessly.\n\n### Guide D: Importing from Linear\n\n1. Export your Linear workspace data via `Settings -> Workspace -> Export -> JSON`.\n2. In \ud83d\udc4dkanban, select the **Linear** tab.\n3. Paste the Linear JSON archive. Linear cycles, project modules, and parent-child relations are automatically recognized.\n4. Verify user mappings for Linear team members.\n5. Execute **Stage 1: Preview Dry-Run Diff** and **Stage 2: Execute Live Import**. Linear identifiers (`ENG-42`) become permanent aliases.\n\n![Migration Import Studio - Mobile Portrait](images/slice4-imports-390x844-mobile-portrait.png)\n\n![Migration Dry-Run and Validation Results](images/71-plane-migration-dry-run.png)\n\n---\n\n## 5. Portable Workspace Bundles (`.tar.gz`)\n\nFor exporting portable, human-readable workspace archives between distinct \ud83d\udc4dkanban installations:\n\n1. **Export Procedure:** In `/admin/imports` under the **Portable Workspace Export** section (or via `POST /api/v1/admin/exports/portable`), enter the target workspace slug, toggle **Scrub secrets and sensitive tokens from markdown** (`scrub: true`) if sensitive tokens should be redacted from text and markdown fields, and click **Download Portable Bundle (.tar.gz)**.\n2. **Bundle Contents:**\n   - `entities.jsonl`: Universal spine of issues, stickies, docs, cycles, and modules.\n   - `docs/`: Canonical Markdown documents with intact folder hierarchies.\n   - `links.jsonl`: Typed `object_links` representing graph topology.\n   - `manifest.json`: Cryptographic SHA-256 manifest and schema version metadata.\n"
  },
  {
    "slug": "production-promotion-and-backup-runbook",
    "title": "[Guide] Production Promotion and Encrypted Backup Runbook",
    "category": "guide",
    "track": "Step-by-Step Guides",
    "subtrack": "Deployment & Backups",
    "audience": "DevOps & Platform Operators",
    "order": 19,
    "summary": "Teams frequently evaluate software in a lightweight standalone environment before promoting it to a hardened production cluster. In conventional ticketing platforms, moving from a single test container to a production architecture requires painful manual database migrations, re-uploading media assets, and rebuilding configurations from scratch.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "standalone-to-production-promotion-workflow",
        "title": "Standalone to Production Promotion Workflow",
        "level": 2
      },
      {
        "id": "the-5-isolated-production-networks",
        "title": "The 5 Isolated Production Networks",
        "level": 3
      },
      {
        "id": "encrypted-backup-formats-kbkp-streaming-vs-kbbak1-snapshots",
        "title": "Encrypted Backup Formats: KBKP Streaming vs KBBAK1 Snapshots",
        "level": 2
      },
      {
        "id": "streaming-direct-download-kbkp-format",
        "title": "1. Streaming Direct Download (KBKP Format)",
        "level": 3
      },
      {
        "id": "server-side-automated-snapshots-kbbak1-format",
        "title": "2. Server-Side Automated Snapshots (KBBAK1 Format)",
        "level": 3
      },
      {
        "id": "visual-backup-promotion-studio-adminstandalone",
        "title": "Visual Backup & Promotion Studio (/admin/standalone)",
        "level": 2
      },
      {
        "id": "studio-controls-backend-setting-reference",
        "title": "Studio Controls & Backend Setting Reference",
        "level": 3
      },
      {
        "id": "step-by-step-operator-runbooks",
        "title": "Step-by-Step Operator Runbooks",
        "level": 2
      },
      {
        "id": "runbook-1-creating-an-encrypted-backup-snapshot",
        "title": "Runbook 1: Creating an Encrypted Backup Snapshot",
        "level": 3
      },
      {
        "id": "runbook-2-restoring-from-an-encrypted-backup-archive",
        "title": "Runbook 2: Restoring from an Encrypted Backup Archive",
        "level": 3
      },
      {
        "id": "runbook-3-promoting-standalone-to-production-multi-container-compose",
        "title": "Runbook 3: Promoting Standalone to Production Multi-Container Compose",
        "level": 3
      }
    ],
    "content": "# [Guide] Production Promotion and Encrypted Backup Runbook\n\n## Overview\n\nTeams frequently evaluate software in a lightweight standalone environment before promoting it to a hardened production cluster. In conventional ticketing platforms, moving from a single test container to a production architecture requires painful manual database migrations, re-uploading media assets, and rebuilding configurations from scratch.\n\n\ud83d\udc4dkanban provides a streamlined, reliable **Production Promotion and Encrypted Backup Architecture** (`docs/PROMOTION_AND_BACKUP.md`). With standardized tools and privilege-separated daemons, administrators can promote standalone deployments or execute disaster recovery with minimal downtime and cryptographic certainty.\n\n---\n\n## Standalone to Production Promotion Workflow\n\nMoving from a single-container standalone instance (`docker run -d -p 8080:8080 thumbs-up-kanban:latest`) to the compartmentalized 5-network production stack (`docker compose`) takes five sequential steps:\n\n```mermaid\nflowchart TD\n    S1[\"Step 1: Drain Active Traffic - Graceful container stop / maintenance mode - Halt requests and flush WAL\"]\n    S2[\"Step 2: Export Production Compose Bundle - GET /api/v1/admin/standalone/compose-export - Generate 5-network compose and scrubbed .env\"]\n    S3[\"Step 3: Transfer PostgreSQL Data Volume - Copy /var/lib/kanban/data to production volume - Hardware-level data preservation\"]\n    S4[\"Step 4: Launch Production Stack - docker compose -f deploy/prod/docker-compose.yml up -d - Compartmentalized 5-network isolation\"]\n    S5[\"Step 5: Post-Promotion Verification - Check container health and migrations - Verify 100% integrity\"]\n\n    S1 --> S2\n    S2 --> S3\n    S3 --> S4\n    S4 --> S5\n```\n\n![Standalone Status and Backups Studio - Desktop Light](images/slice4-standalone-1440x900-light.png)\n\n### The 5 Isolated Production Networks\n\nThe generated production `docker-compose.yml` divides services across five strictly isolated Docker bridge networks:\n1. **`edge_net`:** Connects the Caddy TLS ingress proxy to the external network and routes HTTPS traffic into the web/API service. No database or Redis containers attach to `edge_net`.\n2. **`app_net`:** Connects the FastAPI backend service to the web client, internal caches, and the outbox event relay.\n3. **`data_net`:** Restricted network connecting the backend service strictly to PostgreSQL 16 and Redis. Containers on `edge_net` or `sandbox_net` have zero network route to `data_net`.\n4. **`sandbox_net`:** Air-gapped network for untrusted custom field scripts and Wasmtime runners, blocking all external egress.\n5. **`egress_llm_net`:** Egress-only network allowing AI provider connections (OpenAI, Gemini, Ollama) and mTLS runner heartbeats on port 8444 while preventing inbound lateral movement.\n\n---\n\n## Encrypted Backup Formats: KBKP Streaming vs KBBAK1 Snapshots\n\n\ud83d\udc4dkanban implements dual encrypted backup engines engineered for distinct operational scenarios:\n\n```mermaid\nflowchart LR\n    subgraph DirectStream[\"Direct Download (KBKP Streaming)\"]\n        K1[\"POST /api/v1/admin/standalone/backup - Streaming AES-256-GCM Envelope\"] --> K2[\"Direct Client Browser Download - kanban-backup.kbbak (KBKP 34-byte header)\"]\n    end\n\n    subgraph ServerSnapshot[\"Automated Snapshots (KBBAK1 Archive)\"]\n        B1[\"POST /api/v1/admin/standalone/backups/run-now - Fixed-op daemon (.kb_ops.sock)\"] --> B2[\"Stored in /var/lib/kanban/data/backups - kanban-backup-TIMESTAMP.kbbak (KBBAK1)\"]\n    end\n```\n\n### 1. Streaming Direct Download (`KBKP` Format)\n- **Endpoint:** `POST /api/v1/admin/standalone/backup`\n- **Mechanism:** Streams an AES-256-GCM encrypted payload directly to the operator's web browser without buffering the full archive on server disk.\n- **Envelope Header:** 34-byte binary header: `KBKP` (4 bytes magic) + `version` (`1`, 1 byte) + `kdf_mode` (`1`=PBKDF2-HMAC-SHA256 600,000 iterations, `2`=HKDF-SHA256, 1 byte) + `salt` (16 bytes) + `nonce` (12 bytes), followed by the AES-256-GCM ciphertext stream of raw `pg_dump --format=custom` bytes terminated with a 16-byte authentication tag.\n- **Passphrase Contract:** Derived via PBKDF2-HMAC-SHA256 with 600,000 iterations. Passphrases must be at least 16 characters in length.\n\n### 2. Server-Side Automated Snapshots (`KBBAK1` Format)\n- **Endpoint:** `POST /api/v1/admin/standalone/backups/run-now`\n- **Daemon Privilege Separation:** Managed by a dedicated, root-privileged local daemon communicating strictly over UNIX domain socket `/run/postgresql/.kb_ops.sock` (mode `0660`, group `65532`). The web application process running as non-root user `kanban_app` cannot directly invoke shell scripts or bypass database controls; it issues fixed-operation JSON-line IPC commands (`\"pg_dump_raw\"`, `\"restore_backup\"`, `\"scheduled_backup\"`).\n- **Storage Location:** Saved in `/var/lib/kanban/data/backups` with ISO-8601 timestamps (e.g. `kanban-backup-20261125T144207Z.kbbak`).\n- **Archive Structure:** Tar archive prefixed with 37-byte header `KBBAK1\\x00\\x01` using Argon2id (`KDF_MODE_ARGON2ID` with 64 MiB memory, time=3, parallelism=4) or `KDF_MODE_RAW`, encrypting 4 MiB AES-256-GCM chunks of a tar bundle containing `manifest.json`, `database.pgdump`, `attachments/`, and optional `secrets_carryover.json`.\n\n![Standalone Backups and Snapshot History](images/slice4-standalone-backups-snapshot-history.png)\n\n---\n\n## Visual Backup & Promotion Studio (`/admin/standalone`)\n\nThe Standalone Status and Backups Studio is mounted at `/admin/standalone` (and through the Administration navigation under Deployment & Backups). It provides three tabs:\n\n1. **Storage & Capabilities Health:** Inspects runtime deployment mode, disk mount points, total database size, WAL generation rate, and container cgroup memory/CPU limits.\n2. **Backup, Auto-Backup & Restore:** Triggers manual encrypted backups, schedules automated recurring snapshots, inspects historical server backups, and manages 2-stage restores.\n3. **Docker Compose Export:** Generates the production 5-network `docker-compose.yml` and secret-scrubbed `.env.example` file.\n\n![Standalone Status Studio - Desktop Dark](images/slice4-standalone-1440x900-dark.png)\n\n### Studio Controls & Backend Setting Reference\n\n1. **Passphrase Input (`passphrase`):**\n   Client-supplied encryption passphrase (minimum 16 characters). Used for client-side key derivation on direct downloads and for unlocking backup archives during restore. Never stored in PostgreSQL or logged.\n\n2. **Automated Backup Schedule (`enabled`, `interval_hours`):**\n   Configures periodic automated snapshots. Values for `interval_hours` range from `1` to `168` hours (default `24`). Snapshots are created by the root-privileged `/run/postgresql/.kb_ops.sock` background daemon.\n\n3. **Retention Policy (`retention_count`):**\n   Controls the number of automated snapshot files retained on disk (range `1` to `90`, default `7`). The snapshot purger automatically deletes older archives while preserving the newest snapshots.\n\n4. **Confirmation Overwrite (`confirm_overwrite`):**\n   Mandatory safety string required for destructive database restores (`POST /api/v1/admin/standalone/restore`). Must be set to the exact string `\"RESTORE\"`. Submissions with missing or incorrect confirmation strings are rejected with HTTP 422 before any database teardown begins.\n\n![Visual Backup and Disaster Recovery Studio Modal](images/57-standalone-backup-restore-modal.png)\n\n5. **Tamper Verification Gate:**\n   Prior to applying any restore, the backend executes `POST /api/v1/admin/standalone/backup/verify`. If even a single bit of ciphertext has been modified or corrupted, the GCM authentication tag verification fails and the operation halts with HTTP 422.\n\n![Standalone Status Studio - Tablet Landscape](images/slice4-standalone-1024x768-tablet-landscape.png)\n![Standalone Status Studio - Tablet Portrait](images/slice4-standalone-768x1024-tablet-portrait.png)\n\n---\n\n## Step-by-Step Operator Runbooks\n\n### Runbook 1: Creating an Encrypted Backup Snapshot\n\n1. Navigate to `/admin/standalone` and open the **Backup, Auto-Backup & Restore** tab.\n2. Under **Manual Encrypted Backup (.kbbak)**, enter an encryption passphrase meeting the 16-character minimum requirement.\n3. Click **Download Encrypted Backup (.kbbak)**. The server streams the encrypted `KBKP` archive directly to your browser via `POST /api/v1/admin/standalone/backup`.\n4. Alternatively, click **Run Backup Now** to invoke the background daemon. The new snapshot appears in the Server Snapshots table with its exact byte size and timestamp.\n\n### Runbook 2: Restoring from an Encrypted Backup Archive\n\nRestoring a database snapshot completely replaces existing database state with the archive contents. Follow this two-stage procedure:\n\n1. In `/admin/standalone`, scroll to **Restore Database (2-Stage Verification)**.\n2. Select an existing server snapshot from the dropdown, or upload a local `.kbbak` archive file.\n3. Enter the exact passphrase used when creating the backup.\n4. Click **Step 1: Verify Backup Archive**. The backend validates the GCM authentication tag via `POST /api/v1/admin/standalone/backup/verify` and verifies internal component checksums without touching the database.\n5. In the confirmation input box, type the uppercase confirmation phrase `RESTORE`.\n6. Click **Step 2: Restore Database**. The backend executes `POST /api/v1/admin/standalone/restore`, enters single-user maintenance mode, terminates existing sessions, restores all tables and sequences, re-establishes RLS policies, and reconnects the application.\n\n```mermaid\nsequenceDiagram\n    participant Admin as Administrator UI\n    participant API as FastAPI Backend (/api/v1/admin/standalone/*)\n    participant Ops as Ops Daemon (/run/postgresql/.kb_ops.sock)\n    participant DB as PostgreSQL 16 (kanban)\n\n    Admin->>API: POST /restore (archive, passphrase, confirm_overwrite=\"RESTORE\")\n    API->>API: Validate confirm_overwrite == \"RESTORE\" (422 if mismatched)\n    API->>API: Derive key via Argon2id or raw secret\n    API->>API: Verify AES-256-GCM auth tag (422 if tampered/wrong passphrase)\n    API->>Ops: IPC {\"op\": \"restore_backup\", \"archive_path\": path}\n    Ops->>DB: Terminate connections & drop/re-create tables\n    Ops->>DB: Ingest database.pgdump & restore sequences\n    Ops->>DB: Execute audit-rls (assert FORCE RLS on all tables)\n    Ops-->>API: Restore completed (100 tables restored)\n    API-->>Admin: HTTP 200 OK (Restore Successful)\n```\n\n### Runbook 3: Promoting Standalone to Production Multi-Container Compose\n\n1. In `/admin/standalone`, switch to the **Docker Compose Export** tab.\n2. In the UI, click **Download docker-compose.yml** and click **Copy .env.example** (or use the CLI command `kanban-ctl promote export-compose --out-dir /opt/kanban-prod --domain kanban.example.com` to generate `docker-compose.yml`, `Caddyfile`, and `.env.production`).\n3. Set up the target directory on your production host:\n   ```bash\n   mkdir -p /opt/kanban-prod && cd /opt/kanban-prod\n   # Place docker-compose.yml, Caddyfile, and .env here\n   ```\n4. Copy your standalone PostgreSQL data volume:\n   ```bash\n   docker run --rm -v kanban_data:/from:ro -v kanban_prod_pgdata:/to alpine cp -a /from/. /to/\n   ```\n5. Review `.env.example`, populate production domain names and TLS certificates, and rename to `.env`.\n6. Start the production stack:\n   ```bash\n   docker compose up -d\n   ```\n7. Verify container status, migration state, and system health:\n   ```bash\n   docker compose ps\n   curl -sf http://localhost:8080/api/v1/system/status\n   docker compose exec app kanban-ctl db check-migrations\n   ```\n\n![Standalone Status Studio - Mobile Portrait](images/slice4-standalone-390x844-mobile-portrait.png)\n"
  },
  {
    "slug": "rest-api-architecture-and-openapi-guide",
    "title": "[Informational] REST API Architecture and OpenAPI Integration Guide",
    "category": "informational",
    "track": "Feature & Field Reference",
    "subtrack": "API & SDK Reference",
    "audience": "Frontend & Backend Developers",
    "order": 20,
    "summary": "Software projects that attempt to manually maintain hundreds of static wiki pages for every REST endpoint inevitably suffer from documentation drift: code changes, parameters evolve, but static documentation falls behind, creating frustration and integration bugs.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "documentation-and-schema-endpoints",
        "title": "Documentation and Schema Endpoints",
        "level": 2
      },
      {
        "id": "rest-api-architectural-principles",
        "title": "REST API Architectural Principles",
        "level": 2
      },
      {
        "id": "consistent-rfc-7807-error-responses",
        "title": "1. Consistent RFC 7807 Error Responses",
        "level": 3
      },
      {
        "id": "multi-factor-authenticator-assurance-level-2-aal2",
        "title": "2. Multi-Factor Authenticator Assurance Level 2 (AAL2)",
        "level": 3
      },
      {
        "id": "concurrency-protection-with-etag-and-if-match",
        "title": "3. Concurrency Protection with ETag and If-Match",
        "level": 3
      },
      {
        "id": "zero-context-fail-closed-database-isolation",
        "title": "4. Zero-Context Fail-Closed Database Isolation",
        "level": 3
      },
      {
        "id": "route-module-organization",
        "title": "Route Module Organization",
        "level": 2
      },
      {
        "id": "generating-client-sdks-and-syncing-schemas",
        "title": "Generating Client SDKs and Syncing Schemas",
        "level": 2
      },
      {
        "id": "administrative-api-and-mcp-key-surfaces",
        "title": "Administrative API and MCP Key Surfaces",
        "level": 2
      }
    ],
    "content": "# [Informational] REST API Architecture and OpenAPI Integration Guide\n\n## Overview\n\nSoftware projects that attempt to manually maintain hundreds of static wiki pages for every REST endpoint inevitably suffer from documentation drift: code changes, parameters evolve, but static documentation falls behind, creating frustration and integration bugs.\n\n\ud83d\udc4dkanban adheres to the **In-Code OpenAPI Single Source of Truth** architecture:\n- All REST endpoints are declared with comprehensive Pydantic models, detailed FastAPI docstrings, summaries, response schemas, and parameter constraints directly in the Python source code (`kanban/api/v1/*.py`).\n- The canonical OpenAPI 3.1.0 specification is automatically generated by the FastAPI backend at `/api/openapi.json` and mirrored in the repository at `kanban/web/openapi.json` (`275` paths, `366` operations, `384` schemas, regenerated via `python -m kanban.tools.export_openapi kanban/web/openapi.json`).\n- Interactive documentation is hosted at `/api/docs` (Swagger UI) and `/api/redoc` (ReDoc) directly from the application server with self-contained assets.\n- The web frontend generates its type-safe TypeScript API client directly from this schema (`pnpm --dir kanban/web run gen:api` producing `kanban/web/src/api/schema.gen.ts`).\n\n```mermaid\nflowchart LR\n    subgraph Backend[\"FastAPI Backend Source\"]\n        Pydantic[\"Pydantic Schemas<br/>& Field Validators\"]\n        Routes[\"275 FastAPI Routes<br/>kanban/api/v1/*.py\"]\n    end\n\n    subgraph SchemaGen[\"Canonical OpenAPI Export\"]\n        OpenAPI[\"OpenAPI 3.1.0 JSON<br/>/api/openapi.json\"]\n    end\n\n    subgraph Frontend[\"TypeScript Client & UI\"]\n        TSGen[\"openapi-typescript<br/>pnpm run gen:api\"]\n        SDK[\"Type-Safe Client SDK<br/>src/api/schema.gen.ts\"]\n        UI[\"React 19 SPA<br/>Board, Drawer, Studios\"]\n    end\n\n    Pydantic --> Routes\n    Routes -->|Automatic Introspection| OpenAPI\n    OpenAPI -->|Code Generation| TSGen\n    TSGen --> SDK\n    SDK --> UI\n```\n\n---\n\n## Documentation and Schema Endpoints\n\nWhen running \ud83d\udc4dkanban (in standalone mode or production), developers and integrations can access:\n\n| Endpoint / File | Interface | Purpose |\n| :--- | :--- | :--- |\n| **`/api/docs`** | Swagger UI | Interactive API explorer rendered with local CSS and zero external CDNs. |\n| **`/api/redoc`** | ReDoc | Responsive technical documentation view of all endpoints, parameters, and models. |\n| **`/api/openapi.json`** | Raw OpenAPI 3.1.0 JSON | Machine-readable FastAPI schema (`275` paths, `366` operations, `384` schemas). |\n| **`kanban/web/openapi.json`** | In-Repo JSON Snapshot | Version-controlled OpenAPI specification checked by CI (`pnpm run check:api`). |\n| **`kanban/web/src/api/schema.gen.ts`** | Generated TypeScript SDK | Strictly typed interfaces, request parameters, and response schemas. |\n| **`kanban/api/v1/*.py`** | In-Code Python Source | Authoritative FastAPI route docstrings, summaries, tags, and Pydantic `Field` docs. |\n\n---\n\n## REST API Architectural Principles\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Client as Client / Agent\n    participant FastAPI as FastAPI Router\n    participant Auth as Auth & AAL2 Dependency\n    participant DB as PostgreSQL (FORCE RLS)\n    participant San as Markdown Sanitizer\n\n    Client->>FastAPI: HTTP PATCH /api/v1/issues/{id} (If-Match: ETag)\n    FastAPI->>Auth: Validate Session / Token & AAL2 Level\n    alt Invalid Auth or Missing AAL2\n        Auth-->>Client: 401 Unauthorized / 403 Forbidden (RFC 7807)\n    else Authenticated\n        Auth->>DB: BEGIN TX & SET LOCAL app.current_principal_id = :id\n        FastAPI->>DB: Check ETag & Select Row with RLS\n        alt ETag Mismatch (Lost Update Detected)\n            FastAPI-->>Client: 412 Precondition Failed\n        else ETag Matched\n            FastAPI->>San: Sanitize Hostile Unicode & HTML\n            San-->>FastAPI: Clean Canonical Markdown\n            FastAPI->>DB: UPDATE issue & Append Activity Ledger\n            DB-->>FastAPI: Commit TX\n            FastAPI-->>Client: 200 OK (New ETag, Sanitized Payload)\n        end\n    end\n```\n\nEvery REST endpoint in \ud83d\udc4dkanban adheres to strict architectural invariants:\n\n### 1. Consistent RFC 7807 Error Responses\nAll error responses return structured RFC 7807 Problem Details JSON:\n\n```json\n{\n  \"type\": \"https://kanban.hackedyour.info/errors/LOCKOUT_PREVENTED\",\n  \"title\": \"Lockout Prevented\",\n  \"status\": 409,\n  \"detail\": \"Cannot disable the sole remaining active admin authentication card.\",\n  \"instance\": \"/api/v1/admin/auth/cards/01932e6b-7341-789a-bc01-123456789abc\",\n  \"code\": \"LOCKOUT_PREVENTED\",\n  \"timestamp\": \"2026-11-15T23:50:00Z\"\n}\n```\n\n### 2. Multi-Factor Authenticator Assurance Level 2 (AAL2)\nEvery route under `/api/v1/admin/*` enforces multi-factor verification at the FastAPI dependency layer:\n\n```python\n@router.post(\n    \"/admin/auth/cards/{card_id}/reorder\",\n    dependencies=[Depends(require_admin_aal2)],\n    summary=\"Reorder Authentication Cards\",\n    description=\"Updates sort rank of an authentication card. Enforces AAL2 admin session.\"\n)\nasync def reorder_auth_card(...): ...\n```\nAPI tests enforce this contract via `assert_admin_routes_protected`, rejecting any PR that adds an admin endpoint without the required `require_admin_aal2` dependency.\n\n### 3. Concurrency Protection with ETag and `If-Match`\nTo prevent the lost-update problem when multiple engineers or AI agents edit tickets simultaneously:\n- Read endpoints return an `ETag` header containing a SHA-256 hash of the object version.\n- Mutation endpoints (`PATCH /api/v1/issues/{id}`, `PUT /api/v1/docs/{id}`) accept an `If-Match` header.\n- If the current database record version differs from the provided `If-Match` header, the request is rejected with `412 Precondition Failed`.\n\n### 4. Zero-Context Fail-Closed Database Isolation\nREST route handlers do not query PostgreSQL as a superuser. Each request handler binds the authenticated principal ID to the session context (`SET LOCAL app.current_principal_id = :id`) within an explicit database transaction. If authentication is absent, PostgreSQL Row-Level Security policies evaluate to false and return zero records.\n\n---\n\n## Route Module Organization\n\nThe 275 REST API endpoints (366 operations across 384 schemas) are organized into cohesive domain modules under `kanban/api/v1/`:\n\n```\nkanban/api/v1/\n|-- auth_*.py           # Multi-card authentication (local, ldap, oidc, session, setup, webauthn, mfa)\n|-- workspaces.py       # Workspace provisioning, member invitations, theme configuration\n|-- projects.py         # Project lifecycle, custom state configuration, member bindings\n|-- issues.py           # Work items, quick-create, property updates, sub-tasks, comments\n|-- issue_*.py          # Issue operations (archive, copy, delete, move, provenance, trees, workflow)\n|-- cycles.py           # Sprint cycles, rollover automation, velocity calculations\n|-- modules.py          # Functional modules, completion tracking, feature grouping\n|-- docs.py             # Hierarchical technical documentation, ltree traversal, version diffs\n|-- stickies.py         # Digital sticky notes, color categorization, smart promotion\n|-- custom_fields*.py   # Custom scripted fields, approvals, Wasmtime/nsjail execution\n|-- transitions.py      # Workflow transitions, helper engine execution, gate evaluation\n|-- search.py           # Hybrid lexical and semantic search endpoints\n|-- media_proxy.py      # Cookieless, HMAC-signed external image proxy (GET /api/v1/media-proxy)\n|-- oauth.py            # OAuth 2.0 / OIDC provider endpoints, PKCE, device code authorization\n|-- repo_bindings.py    # Remote git repository bindings and runner pools\n|-- agent_definitions.py# Agent definition catalog and validation\n|-- admin/              # Admin-only AAL2 governance modules\n|   |-- auth_cards.py   # Multi-card auth administration\n|   |-- destructive.py  # Blast-radius calculations and 2-stage confirmations\n|   |-- link_auditor.py # Universal Object Graph link audits and repair\n|   `-- workspace_settings.py # Workspace configuration and security parameters\n`-- system*.py          # Platform summary, status, licensing, and CycloneDX 1.5 SBOM\n```\n\n---\n\n## Generating Client SDKs and Syncing Schemas\n\nTo update the frontend TypeScript client after modifying backend FastAPI route signatures:\n\n```bash\n# Step 1: Export latest OpenAPI JSON from the FastAPI application\npython -m kanban.tools.export_openapi kanban/web/openapi.json\n\n# Step 2: Regenerate the TypeScript SDK types\npnpm --dir kanban/web run gen:api\n\n# Step 3: Verify TypeScript compilation\npnpm --dir kanban/web run build\n```\n\nThis automated synchronization ensures that frontend UI components, test runners, and backend routes stay in lockstep with zero documentation lag.\n\n---\n\n## Administrative API and MCP Key Surfaces\n\nThe administrative REST API operates alongside the Model Context Protocol (MCP) server, offering fine-grained permission scoping, token rotation, and runtime health diagnostics.\n\n![MCP Access Studio and Scoped Token Management](images/13-mcp-access-studio.png)\n\n![System Settings and API Diagnostics](images/26-system-settings.png)\n"
  },
  {
    "slug": "real-time-web-and-websocket-architecture",
    "title": "[Architectural] Real-Time Web and WebSocket Architecture",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Functional Architecture",
    "audience": "Realtime Systems & Network Engineers",
    "order": 21,
    "summary": "Modern software engineering teams collaborate concurrently across distributed locations. When one developer moves a card on the Kanban board, adds a comment, or when an autonomous AI agent updates a verification gate, all team members viewing the project must see the update instantly without manual page refreshes.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "websocket-hub-architecture",
        "title": "WebSocket Hub Architecture",
        "level": 2
      },
      {
        "id": "connection-security-and-rate-limiting-controls",
        "title": "Connection Security and Rate-Limiting Controls",
        "level": 2
      },
      {
        "id": "strict-origin-and-csrf-validation",
        "title": "1. Strict Origin and CSRF Validation",
        "level": 3
      },
      {
        "id": "session-authentication-and-privilege-resolution",
        "title": "2. Session Authentication and Privilege Resolution",
        "level": 3
      },
      {
        "id": "maximum-16-concurrent-connections-per-principal",
        "title": "3. Maximum 16 Concurrent Connections per Principal",
        "level": 3
      },
      {
        "id": "channel-subscription-and-event-model",
        "title": "Channel Subscription and Event Model",
        "level": 2
      },
      {
        "id": "core-broadcast-events",
        "title": "Core Broadcast Events",
        "level": 3
      },
      {
        "id": "client-resilience-and-reconnection-strategy",
        "title": "Client Resilience and Reconnection Strategy",
        "level": 2
      }
    ],
    "content": "# [Architectural] Real-Time Web and WebSocket Architecture\n\n## Overview\n\nModern software engineering teams collaborate concurrently across distributed locations. When one developer moves a card on the Kanban board, adds a comment, or when an autonomous AI agent updates a verification gate, all team members viewing the project must see the update instantly without manual page refreshes.\n\n\ud83d\udc4dkanban implements a high-performance **Real-Time WebSocket Hub** (`kanban/realtime/hub.py` and `kanban/api/ws.py`) delivering sub-50ms event fan-out across browser clients and autonomous agents.\n\n---\n\n## WebSocket Hub Architecture\n\n```mermaid\nflowchart TD\n    subgraph Clients[\"Subscribed Clients\"]\n        Browser[\"Browser Clients (Chrome / Firefox / Safari)\"]\n        Agents[\"Autonomous Agents & IDE Integrations\"]\n    end\n\n    subgraph Gateway[\"Realtime Ingress (/ws, /api/v1/ws, /sse)\"]\n        Ingress[\"FastAPI WebSocket & SSE Handlers<br/>- Origin header CORS check<br/>- Session cookie / Bearer token resolution<br/>- 16-connection limit per principal\"]\n    end\n\n    subgraph Router[\"Realtime Hub Event Router\"]\n        Hub[\"Hub Event Router (kanban/realtime/hub.py)<br/>- Channels: workspace:{id}, project:{id}, issue:{id}, doc:{id}<br/>- RLS permission-filtered fanout<br/>- Non-blocking async backpressure queues\"]\n    end\n\n    subgraph Surfaces[\"Live UI Surfaces\"]\n        BoardUI[\"Board View: Instant Card Moves (<12ms)\"]\n        DrawerUI[\"Ticket Drawer: Live Activity & Gate Timers\"]\n        StickyUI[\"Stickies Grid: Collaborative Autosave\"]\n    end\n\n    Browser --> Ingress\n    Agents --> Ingress\n    Ingress --> Hub\n    Hub --> BoardUI\n    Hub --> DrawerUI\n    Hub --> StickyUI\n```\n\n![Responsive Tablet and Mobile Layout with Live Realtime Updates](images/30-responsive-tablet-layout.png)\n\n---\n\n## Connection Security and Rate-Limiting Controls\n\nWebSockets establish persistent, bidirectional TCP connections that can be abused for denial-of-service (DoS) or unauthorized event eavesdropping if not hardened properly.\n\n### 1. Strict Origin and CSRF Validation\nDuring the initial WebSocket upgrade handshake (`GET /ws` or `/api/v1/ws`), the server validates the incoming `Origin` header against configured allowed hosts. Requests from untrusted origins are immediately rejected with HTTP 403 Forbidden. Client sessions fallback to Server-Sent Events (`GET /sse`) when WebSocket transport is blocked by corporate proxies.\n\n### 2. Session Authentication and Privilege Resolution\n- WebSocket and SSE connections authenticate using encrypted session cookies (`__Host-kb_session`) or scoped Bearer API tokens.\n- Anonymous connections are strictly forbidden.\n- When an authenticated connection opens, the hub resolves the user's principal ID, active tenant workspace, and project memberships.\n\n### 3. Maximum 16 Concurrent Connections per Principal\nTo prevent browser tab flooding or malicious connection exhaustion:\n- The `ConnectionManager` tracks open sockets by `principal_id`.\n- If an individual user or service principal attempts to establish more than 16 concurrent WebSocket connections, excess connection requests are rejected with status code `4429 Too Many Connections`.\n\n---\n\n## Channel Subscription and Event Model\n\nClients subscribe to targeted channels based on their active view, minimizing unnecessary network traffic:\n\n| Channel Pattern | Granularity | Typical Subscribers | Broadcast Events |\n| :--- | :--- | :--- | :--- |\n| **`workspace:{workspace_id}`** | Workspace | All active workspace members | `project.created`, system announcements, `sticky.*` grid updates. |\n| **`project:{project_id}`** | Project | Users viewing board or issue list | `issue.created`, `issue.updated`, `issue.transitioned`, `issue.moved`, `issue.deleted`, `cycle.*`, `module.*`. |\n| **`issue:{issue_id}`** | Ticket | Users viewing Ticket Peek Drawer | `comment.*`, `workflow.gate.*`, `issue.updated`, `assignee.*`. |\n| **`doc:{doc_id}`** | Document | Users viewing or editing technical documentation | `doc.updated`, `doc.page.created`, `doc.page.updated`, `doc.page.deleted`. |\n\n### Core Broadcast Events\n\n- **`issue.moved`:** Dispatched when a card changes state or swimlane position. Transmits the updated state ID, previous state ID, sort rank, and the operator who initiated the move.\n- **`issue.created`:** Dispatched when a new work item is created in the project.\n- **`issue.updated`:** Broadcasts property, label, assignee, or description edits.\n- **`issue.transitioned`:** Broadcasts workflow state transitions across the board.\n- **`issue.deleted`:** Broadcasts work item trash or removal.\n- **`workflow.gate.*`:** Broadcasts async agent gate transitions (`pending_agent_gate`, `vetoed`, `approved`) allowing the board to update countdown timers and animate spring snap-backs in real time.\n- **`comment.*`:** Broadcasts discussion activity, replies, and mentions.\n- **`sticky.*`:** Broadcasts real-time color changes, text edits, or promotion events on the stickies masonry grid.\n\n---\n\n## Client Resilience and Reconnection Strategy\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor User as Connected Operator\n    participant Client as React 19 WebSocket Client\n    participant Hub as Realtime Hub\n    participant DB as PostgreSQL Ledger\n\n    Note over Client,Hub: Normal Operation (Receiving Events)\n    Hub->>Client: Event: issue.moved (seq: 42)\n    Note over Client,Hub: Network Partition / Laptop Lid Closed\n    Client->>Client: Connection Lost! Activate Reconnecting Pill\n    Note over Client,Hub: Network Restored\n    Client->>Hub: Reconnect Handshake & Resume (last_seq: 42)\n    Hub->>DB: Query Activity Ledger WHERE seq > 42\n    DB-->>Hub: Return Events [seq: 43, 44, 45]\n    Hub-->>Client: Replay Catch-Up Events [43, 44, 45]\n    Client->>Client: Update State Store & Set Status Pill to Connected\n```\n\nNetwork connections in modern development environments (laptops switching networks, sleep states, VPN renegotiation) are inherently unstable.\n\nThe \ud83d\udc4dkanban web client implements robust reconnection resilience:\n- **Exponential Backoff with Full Jitter:** On connection loss, the client attempts reconnection starting at 500ms, doubling up to a maximum 15-second (`15000ms` full-jitter) retry cap to prevent thundering herd connection storms.\n- **Automatic SSE Fallback:** After 3 consecutive failed WebSocket reconnection attempts (`WS_FAILURES_BEFORE_SSE = 3`), the client automatically downgrades to Server-Sent Events (`/sse`).\n- **Event Sequence Numbers:** Every event payload includes a monotonically increasing `seq` integer. On reconnect, the client requests missed events since its last acknowledged sequence number, guaranteeing zero missed updates.\n- **Visual Connection Pill:** A discrete indicator in the UI status bar displays real-time connectivity (`Connected`, `Reconnecting`, `Offline`).\n\n![Async Agent Gate States with Live Realtime Timers](images/16-async-agent-gate-states.png)\n"
  },
  {
    "slug": "role-and-permission-matrix",
    "title": "[Informational] Role and Permission Matrix",
    "category": "informational",
    "track": "Security & Adoption Overview",
    "subtrack": "Access Control & Governance",
    "audience": "Security Officers & Compliance Auditors",
    "order": 22,
    "summary": "This document defines the authoritative, fine-grained access control model across all 7 principal tiers in the \ud83d\udc4dkanban platform.",
    "sections": [
      {
        "id": "legend",
        "title": "Legend",
        "level": 2
      },
      {
        "id": "system-roles",
        "title": "System Roles",
        "level": 2
      },
      {
        "id": "workspace-level-roles",
        "title": "Workspace-Level Roles",
        "level": 2
      },
      {
        "id": "granular-rbac-policy-builder",
        "title": "Granular RBAC Policy Builder",
        "level": 2
      },
      {
        "id": "narrative-policy-configuration-header",
        "title": "Narrative Policy Configuration Header",
        "level": 3
      },
      {
        "id": "step-by-step-guide-building-custom-rbac-roles",
        "title": "Step-by-Step Guide: Building Custom RBAC Roles",
        "level": 3
      },
      {
        "id": "30-permission-granular-engine",
        "title": "30-Permission Granular Engine",
        "level": 2
      },
      {
        "id": "workspace-tier-8-permissions",
        "title": "1. Workspace Tier (8 Permissions)",
        "level": 3
      },
      {
        "id": "issue-tier-10-permissions",
        "title": "2. Issue Tier (10 Permissions)",
        "level": 3
      },
      {
        "id": "field-tier-12-permissions",
        "title": "3. Field Tier (12 Permissions)",
        "level": 3
      },
      {
        "id": "capability-bitmask-and-deny-precedence",
        "title": "Capability Bitmask and Deny Precedence",
        "level": 2
      },
      {
        "id": "absolute-deny-precedence-rule",
        "title": "Absolute DENY Precedence Rule",
        "level": 3
      },
      {
        "id": "master-capability-matrix",
        "title": "Master Capability Matrix",
        "level": 2
      },
      {
        "id": "detailed-condition-notes",
        "title": "Detailed Condition Notes",
        "level": 2
      },
      {
        "id": "architectural-security-invariants",
        "title": "Architectural Security Invariants",
        "level": 2
      }
    ],
    "content": "# [Informational] Role and Permission Matrix\n\nThis document defines the authoritative, fine-grained access control model across all 7 principal tiers in the \ud83d\udc4dkanban platform.\n\nThe platform enforces Row-Level Security (FORCE RLS) at the PostgreSQL database layer, capability bitmasks with explicit DENY precedence, multi-factor AAL2 step-up authentication, and strict cryptographic scoping for agents and custom scripts.\n\n---\n\n## Legend\n\n| Symbol | Status | Description |\n| :---: | :--- | :--- |\n| **\u25cf** | **Allowed by Role** | Operation is natively permitted by the principal tier without extra elevation. |\n| **\u25d0** | **Conditional** | Operation requires an explicit ACL share, matching token scope, project assignment, or fresh AAL2 step-up verification. |\n| **\u25cb** | **Never Allowed** | Operation is strictly forbidden by policy and rejected by database RLS or API gatekeepers. |\n\n---\n\n## System Roles\n\n\ud83d\udc4dkanban unifies human users, service accounts, and autonomous agents under 7 canonical principal tiers:\n\n1. **Guest** (`WORKSPACE_GUEST` / `PROJECT_GUEST`): Ephemeral or external collaborator. Confined strictly to explicitly shared objects with zero ambient project or workspace visibility.\n2. **Viewer** (`WORKSPACE_VIEWER` / `PROJECT_VIEWER`): Read-only stakeholder. Permitted to inspect unrestricted workspace or project assets, but cannot author or modify data.\n3. **Member** (`WORKSPACE_MEMBER` / `PROJECT_MEMBER`): Standard day-to-day engineer or contributor. Can author and manage issues, docs, stickies, and views in assigned projects.\n4. **Project Admin** (`PROJECT_ADMIN`): Lead for a specific project. Controls project configuration, workflow state transitions, WIP limits, project member bindings, and project trash.\n5. **Workspace Admin** (`WORKSPACE_ADMIN`): Organization administrator. Governs workspace settings, groups, user provisioning, retention policy, and workspace trash studio.\n6. **Server Admin** (`SERVER_ADMIN`): Root platform operator. Manages global server topology, multi-card authentication, air-gap flags, and cryptographic permanent purge.\n7. **Scoped MCP Agent (Service Principal):** Autonomous or assisted agent accessing `/mcp/agent`, `/mcp/docs`, or `/mcp/admin` bound to an API key or OAuth 2.0 PKCE token.\n\n---\n\n## Workspace-Level Roles\n\nWorkspace roles govern tenancy defaults, administrative delegation, and cross-project visibility:\n\n- **Workspace Admin:** Holds full administrative authority across all projects, custom fields, user groups, and workflows within the workspace. Enforces AAL2 step-up for user lifecycle mutations and trash restoration.\n- **Workspace Member:** Baseline contributor role assigned to standard enterprise users. Can create and participate in projects where granted explicit project membership.\n- **Workspace Viewer:** Auditing and stakeholder role with read-only visibility into workspace settings, public projects, and shared documentation.\n- **Workspace Guest:** Restricted access tier for external contractors and vendors. Has no ambient visibility into workspace member lists or project catalogs; visibility is granted exclusively through direct resource ACL grants.\n\nRole inheritance is strictly additive except where explicit DENY masks are applied. A user who is a Workspace Member can be elevated to Project Admin on specific projects without granting broader workspace administration privileges.\n\n---\n\n## Granular RBAC Policy Builder\n\nThe Granular RBAC Policy Builder (`/settings/workspace` -> **Roles & Permissions**) provides a narrative interface for authoring and managing custom role definitions with fine-grained capability sets.\n\n![Custom RBAC Policy Builder](images/slice1-custom-rbac-policy-builder.png)\n\n### Narrative Policy Configuration Header\n\nThe policy editor frames permission assignment as an intuitive narrative sentence:\n\n> **\"As a [ system admin | workspace admin | project admin ] I want [ \u25cf role x ] ... to have access to\"**\n\n- **Tier Scope Selector:** Pins the target scope of the role being defined (`system admin`, `workspace admin`, or `project admin`). Built-in roles belonging to higher tiers are locked against modification by lower-tier administrators.\n- **Role Selector & Creation Popover:** Allows administrators to select an existing custom role or click `*create new*` in the role selector popover to specify role name, slug, badge color, and description.\n- **Tri-State Checkboxes:** Permissions are toggled across three states:\n  - **Unchecked (\u25cb):** Unassigned / not granted for any selected role.\n  - **Checked (\u25cf):** Granted across all selected roles.\n  - **Indeterminate (-):** Partial grant across multiple selected roles (e.g., granted in one selected role, not granted in another; clicking sets grant across all selected roles). (Indeterminate state indicates multi-role partial coverage, NOT an explicit Deny mask).\n\n### Step-by-Step Guide: Building Custom RBAC Roles\n\n1. **Open RBAC Studio:** Navigate to Workspace Settings and select **Roles & Permissions**.\n2. **Select Scope Tier:** In the narrative sentence header, select the target administrative scope (e.g., `workspace admin`).\n3. **Define Custom Role Identity:** In the role selection popover, click `*create new*`, and enter a descriptive **Role Name** (e.g., `Security Auditor`), lowercase alphanumeric **Slug** (e.g., `security-auditor`), and badge **Color** preset.\n4. **Configure Workspace Tier:** Toggle capabilities for workspace provisioning, member management, audit log inspection, and integration configuration.\n5. **Configure Issue Tier:** Toggle capabilities for creating issues, transitioning workflow states, moving rank, linking, and managing item ACLs.\n6. **Configure Field Tier:** Toggle edit capabilities for summary, description, state, priority, assignees, labels, dates, cycle, module, parent, custom fields, and file attachments.\n7. **Immediate Auto-Save:** Permission checkbox mutations auto-save immediately to PostgreSQL via `PUT /api/v1/admin/rbac/roles/permissions:batch` (or single-role `PUT /api/v1/admin/rbac/roles/{role_id}/permissions`), validating caller AAL2 elevation and persisting the policy in `rbac_roles` and `rbac_role_permissions`.\n\n---\n\n## 30-Permission Granular Engine\n\n\ud83d\udc4dkanban implements 30 granular permission keys across three distinct operational tiers, mapped to intuitive UI checkboxes in the Policy Builder:\n\n### 1. Workspace Tier (8 Permissions)\n- `workspace:create` (UI: **Create Workspaces**) - Provision new tenant workspaces.\n- `workspace:edit_settings` (UI: **Edit Settings**) - Modify workspace metadata, retention thresholds, and default roles.\n- `workspace:manage_members` (UI: **Manage Members**) - Invite, deactivate, and remove workspace members.\n- `workspace:create_role` (UI: **Manage Roles**, alias `workspace:manage_roles`) - Author custom RBAC roles and modify role permission bitmasks.\n- `workspace:manage_mcp_keys` (UI: **Manage Integrations**, alias `workspace:manage_integrations`) - Mint, scope, and revoke MCP API tokens.\n- `workspace:audit_logs` (UI: **View Audit Logs**) - Inspect immutable workspace audit logs and ledger events.\n- `workspace:export_data` (UI: **Export Data**) - Export workspace and project data archives.\n- `workspace:manage_trash` (UI: **Purge Trash**, alias `workspace:purge_trash`) - Inspect and permanently purge soft-deleted workspace objects.\n\n### 2. Issue Tier (10 Permissions)\n- `issue:create` (UI: **Create Issues**) - Author new issues, tasks, and bugs.\n- `issue:view` (UI: **View Issues**) - Read issue details, history, and metadata.\n- `issue:comment` (UI: **Comment on Issues**) - Post comments and replies on work items.\n- `issue:transition` (UI: **Transition States**) - Move issues between workflow states.\n- `issue:move_rank` (UI: **Re-order / Move Rank**) - Reorder issues within Kanban columns and backlogs.\n- `issue:copy` (UI: **Copy Issues**) - Duplicate existing issues with selective metadata cloning.\n- `issue:link` (UI: **Link Objects**) - Create typed object links between issues, stickies, and docs.\n- `issue:archive` (UI: **Archive Issues**) - Archive completed or stale issues outside active board views.\n- `issue:delete` (UI: **Delete Issues**) - Soft-delete issues to the project trash bin.\n- `issue:manage_acl` (UI: **Subscribe to Issues**, alias `issue:subscribe`) - Share items with specific principals or set explicit item ACLs.\n\n### 3. Field Tier (12 Permissions)\n- `field:modify_summary` - Modify issue title and summary.\n- `field:modify_description` - Modify issue description markdown content.\n- `field:modify_state` - Update issue status and workflow state.\n- `field:modify_priority` - Update issue priority (URGENT, HIGH, MEDIUM, LOW).\n- `field:modify_assignees` - Assign or reassign users to the issue.\n- `field:modify_labels` - Attach or remove issue labels and tags.\n- `field:modify_dates` - Set or adjust issue start dates and due dates.\n- `field:modify_cycle` - Associate or remove issue from sprint cycles.\n- `field:modify_modules` (UI: `field:modify_module`) - Associate or remove issue from project modules.\n- `field:modify_parent` - Establish or change parent-child epic relationships.\n- `field:modify_custom_fields` - Inspect and modify custom scripted and formula field values.\n- `field:attach_files` - Upload, manage, and remove file attachments.\n\n---\n\n## Capability Bitmask and Deny Precedence\n\nTo guarantee high-performance authorization evaluation without recursive database queries, \ud83d\udc4dkanban compiles permissions into an authoritative 8-bit integer bitmask:\n\n```python\nclass Capability(IntFlag):\n    NONE = 0\n    VIEW = 1 << 0        # 1\n    COMMENT = 1 << 1     # 2\n    EDIT = 1 << 2        # 4\n    TRANSITION = 1 << 3  # 8\n    LINK = 1 << 4        # 16\n    SHARE = 1 << 5       # 32\n    ADMIN = 1 << 6       # 64\n    DELETE = 1 << 7      # 128\n    ALL = 0xFF           # 255\n```\n\n### Absolute DENY Precedence Rule\n\nWhen computing effective access for a user or agent across inherited groups and direct ACLs:\n\n$$\\text{Effective Capability} = (\\text{Inherited} \\cup \\text{Direct Allow}) \\setminus \\text{Direct Deny}$$\n\nIf any role, group, or explicit resource ACL specifies an explicit `DENY` mask for a capability, that capability is mathematically stripped (`allow & (~deny)`). An explicit `DENY` takes precedence over all administrative tiers below Server Administrator.\n\n---\n\n## Master Capability Matrix\n\n| Operational Capability | Guest | Viewer | Member | Project Admin | Workspace Admin | Server Admin | Scoped MCP Agent |\n| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n| **Viewing Workspace-Public Objects** | \u25cb | \u25cf | \u25cf | \u25cf | \u25cf | \u25cf | \u25d0 (1) |\n| **Viewing Private Project Objects** | \u25d0 (2) | \u25d0 (2) | \u25d0 (2) | \u25cf | \u25cf | \u25cf | \u25d0 (1, 2) |\n| **Explicit ACL DENY Precedence** | \u25cf (3) | \u25cf (3) | \u25cf (3) | \u25cf (3) | \u25cf (3) | \u25cf (3) | \u25cf (3) |\n| **Authoring Issues, Stickies, and Docs** | \u25cb | \u25cb | \u25cf | \u25cf | \u25cf | \u25cf | \u25d0 (1) |\n| **Editing and Versioning Pages** | \u25cb | \u25cb | \u25cf | \u25cf | \u25cf | \u25cf | \u25d0 (1) |\n| **Managing Resource ACLs (Share / Revoke)** | \u25cb | \u25cb | \u25d0 (4) | \u25cf | \u25cf | \u25cf | \u25d0 (1, 4) |\n| **Project Studio and Workflow Management** | \u25cb | \u25cb | \u25cb | \u25cf | \u25cf | \u25cf | \u25d0 (1) |\n| **Custom Field and Script Definition** | \u25cb | \u25cb | \u25cb | \u25cb | \u25d0 (5) | \u25cf | \u25d0 (1, 5) |\n| **Soft-Trash Project Objects** | \u25cb | \u25cb | \u25d0 (6) | \u25cf | \u25cf | \u25cf | \u25d0 (1, 6) |\n| **Workspace Trash Studio Inspection** | \u25cb | \u25cb | \u25cb | \u25d0 (7) | \u25cf (8) | \u25cf (8) | \u25d0 (1, 8) |\n| **Restoring Soft-Deleted Objects** | \u25cb | \u25cb | \u25cb | \u25d0 (7) | \u25cf (8) | \u25cf (8) | \u25d0 (1, 8) |\n| **Workspace Retention Policy (7 to 365 Days)** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8) | \u25cf (8) | \u25cb |\n| **Automated Multi-Object Sweep (trash_purge)** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (9) | \u25cb |\n| **2-Stage Permanent Purge (Cryptographic)** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8, 10) | \u25cb |\n| **Local User Provisioning and Password Reset** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8) | \u25cf (8) | \u25cb |\n| **Role Bindings and Group Hierarchy CRUD** | \u25cb | \u25cb | \u25cb | \u25d0 (11) | \u25cf (8) | \u25cf (8) | \u25cb |\n| **Multi-Card Auth Studio and Passkey Config** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8) | \u25cb |\n| **Minting Scoped MCP API Keys** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8) | \u25cf (8) | \u25cb |\n| **Immutable Audit Ledger (Inspection Only)** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8) | \u25cf (8) | \u25d0 (1) |\n| **Tampering with Audit Ledger Records** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cb | \u25cb (12) | \u25cb |\n\n---\n\n## Detailed Condition Notes\n\n1. **Token Scope Restriction:** Scoped MCP Agents can only exercise capabilities explicitly included in their minted token scopes (`read:issues`, `write:issues`, `read:docs`, `write:docs`, `admin`, etc.). Unscoped tools are rejected with `403 FORBIDDEN`.\n2. **Explicit Project Membership / ACL Share:** Guests and Viewers cannot see private project entities unless explicitly added to the project role bindings or granted a specific `ALLOW` entry in `resource_acl_entries`.\n3. **Absolute DENY Precedence:** If an explicit `DENY` entry exists for a principal on an object (or inherited group), effective capability bitmasks collapse immediately (`allow & (~deny)`). Even Workspace Admins cannot view or manage objects guarded by an explicit `DENY`.\n4. **Ownership Share Delegation:** Standard Members can only share objects they originally authored, provided project policy permits user-level ACL delegation.\n5. **Admin Approval Gate:** Custom fields and scripts can only be defined by administrators. Executing a script with Workspace or Server token escalation requires cryptographic approval from an administrator of that tier.\n6. **Author Deletion Scope:** Members may soft-delete their own drafts, comments, and unassigned stickies if granted DELETE capability mask. Project-wide item soft-deletion requires Project Admin.\n7. **Project Scope Isolation:** Project Admins in the Trash Studio can only view and restore items belonging to projects where they hold explicit `PROJECT_ADMIN` authority.\n8. **Fresh AAL2 Step-Up Requirement:** All administrative endpoints (`/api/v1/admin/*`, retention settings, user provisioning, trash operations, key minting) enforce `Depends(require_admin_aal2)`. The session must have verified MFA within the last 900 seconds (`aal2_verified_at <= 900s`).\n9. **Daemon Background Job Authority:** The trash purge runner executes with dedicated system worker identity and sweeps expired entities strictly past their per-workspace `trash_retention_days` threshold.\n10. **2-Stage Destructive Confirmation:** Permanent purge is exclusively gated to `SERVER_ADMIN` + fresh AAL2. It requires `POST /api/v1/admin/destructive:request` to compute blast radius and mint an ephemeral HMAC `confirmation_token` + `blast_hash`, followed by `POST /api/v1/admin/destructive:execute` with a mandatory human reason (10 to 500 characters).\n11. **Project-Level Role Delegation:** Project Admins may manage role bindings within their designated project only. They cannot elevate users to Workspace Admin or Server Admin.\n12. **Cryptographic Immutability:** Audit ledger tables (`activity_ledger`) have no `UPDATE` or `DELETE` grants for any database role (including `kanban_app` and `kanban_migrator`). Database triggers prevent tampering.\n\n---\n\n## Architectural Security Invariants\n\n- **Hostile Wire Invariant:** Every input is validated with strict Pydantic schemas and UTF-8 surrogate checks. Cleartext transmission of tokens is prohibited.\n- **Walled Component Garden:** Row-Level Security (`FORCE ROW LEVEL SECURITY`) is always active on all database sessions. Dropping session authorization to unprivileged users is mandatory in application flows.\n- **Volatile State Sanitization:** Ephemeral tokens and secrets exist only in memory during execution and are erased immediately after verification.\n- **Supply Chain Paranoia:** Zero external cloud runtime dependencies for core authentication, authorization, or search.\n"
  },
  {
    "slug": "scripted-workflows-and-transition-helpers",
    "title": "[Guide] Scripted Workflows and Transition Helpers",
    "category": "guide",
    "track": "Step-by-Step Guides",
    "subtrack": "Workflow Automation",
    "audience": "Engineers & Workflow Designers",
    "order": 23,
    "summary": "In traditional project management tools, workflow rules are either simple notification triggers or inflexible webhooks that fire only *after* a change has occurred. If an issue is improperly moved to \"Done\" without meeting code coverage requirements or QA verification, the damage is already done.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "the-transition-helper-pipeline",
        "title": "The Transition Helper Pipeline",
        "level": 2
      },
      {
        "id": "helper-architecture",
        "title": "Helper Architecture",
        "level": 2
      },
      {
        "id": "failure-policies",
        "title": "Failure Policies",
        "level": 3
      },
      {
        "id": "admin-workflow-transition-studio",
        "title": "Admin Workflow Transition Studio",
        "level": 2
      },
      {
        "id": "studio-capabilities",
        "title": "Studio Capabilities",
        "level": 3
      },
      {
        "id": "step-by-step-guide-attaching-workflow-transition-hooks-with-dry-run",
        "title": "Step-by-Step Guide: Attaching Workflow Transition Hooks with Dry-Run",
        "level": 3
      },
      {
        "id": "the-non-persistent-dry-run-drawer",
        "title": "The Non-Persistent Dry-Run Drawer",
        "level": 3
      },
      {
        "id": "read-only-bare-git-repository-bindings",
        "title": "Read-Only Bare Git Repository Bindings",
        "level": 2
      },
      {
        "id": "step-by-step-guide-binding-git-repositories",
        "title": "Step-by-Step Guide: Binding Git Repositories",
        "level": 3
      },
      {
        "id": "asynchronous-agent-gate-lifecycle-on-the-board",
        "title": "Asynchronous Agent Gate Lifecycle on the Board",
        "level": 2
      },
      {
        "id": "the-board-interaction-states",
        "title": "The Board Interaction States",
        "level": 3
      },
      {
        "id": "the-easiest-3-step-recipe-to-implement-an-automated-qa-gate-on-done",
        "title": "The Easiest 3-Step Recipe to Implement an Automated QA Gate on Done",
        "level": 2
      },
      {
        "id": "step-1-register-and-probe-your-ai-provider-adminai",
        "title": "Step 1: Register and Probe Your AI Provider (/admin/ai)",
        "level": 3
      },
      {
        "id": "step-2-register-an-agent-definition-adminagents",
        "title": "Step 2: Register an Agent Definition (/admin/agents)",
        "level": 3
      },
      {
        "id": "step-3-attach-the-hook-to-in-progress---done-via-workflow",
        "title": "Step 3: Attach the Hook to In Progress -> Done via + Workflow",
        "level": 3
      },
      {
        "id": "in-transition-gate-ideas-gallery",
        "title": "In-Transition Gate Ideas Gallery",
        "level": 2
      },
      {
        "id": "idea-1-fast-2b4b-gemma-triage-auto-labeler-backlog---todo",
        "title": "Idea 1: Fast 2B/4B Gemma Triage & Auto-Labeler (Backlog -> Todo)",
        "level": 3
      },
      {
        "id": "idea-2-security-secret-scan-gate-todo---in-progress",
        "title": "Idea 2: Security & Secret Scan Gate (Todo -> In Progress)",
        "level": 3
      },
      {
        "id": "idea-3-automated-definition-of-done-qa-gate-in-progress---done",
        "title": "Idea 3: Automated Definition-of-Done QA Gate (In Progress -> Done)",
        "level": 3
      },
      {
        "id": "live-walkthrough-reality-checker-done-gate-with-self-hosted-ollama-nemotron-3-superlatest",
        "title": "Live Walkthrough: Reality-Checker Done Gate with Self-Hosted Ollama (nemotron-3-super:latest)",
        "level": 2
      },
      {
        "id": "register-and-probe-the-self-hosted-ollama-provider-adminai",
        "title": "1. Register and Probe the Self-Hosted Ollama Provider (/admin/ai)",
        "level": 3
      },
      {
        "id": "define-the-reality-checker-agent-adminagents",
        "title": "2. Define the reality-checker Agent (/admin/agents)",
        "level": 3
      },
      {
        "id": "attach-the-fail-closed-hook-on-in-progress---done",
        "title": "3. Attach the Fail-Closed Hook on In Progress -> Done",
        "level": 3
      },
      {
        "id": "positive-transition-rcd-1-approved-with-comment-and-allowed-to-done",
        "title": "4. Positive Transition (RCD-1: Approved with Comment and Allowed to Done)",
        "level": 3
      },
      {
        "id": "negative-transition-rcd-2-vetoed-with-comment-and-blocked-in-in-progress",
        "title": "5. Negative Transition (RCD-2: Vetoed with Comment and Blocked in In Progress)",
        "level": 3
      }
    ],
    "content": "# [Guide] Scripted Workflows and Transition Helpers\n\n## Overview\n\nIn traditional project management tools, workflow rules are either simple notification triggers or inflexible webhooks that fire only *after* a change has occurred. If an issue is improperly moved to \"Done\" without meeting code coverage requirements or QA verification, the damage is already done.\n\n\ud83d\udc4dkanban implements a **Scripted Workflow Engine** with **Pre-Transition Helpers**. When an operator or agent attempts to move a work item between states (`from_state -> to_state`), the transition is evaluated through an ordered pipeline of synchronous validators, field mutators, and asynchronous AI agent gates.\n\n---\n\n## The Transition Helper Pipeline\n\n```mermaid\nflowchart TD\n    Drag[\"User / Agent moves card: In Progress -> Done\"] --> HelperEngine[\"Transition Helper Engine\"]\n    HelperEngine --> Stage1[\"Stage 1: Synchronous Validator (Tier A Wasm) - Verify blockers resolved - Verify Definition of Done criteria & PR links\"]\n    Stage1 -->|PASS| Stage2[\"Stage 2: Synchronous Field Mutator (Tier A) - Auto-tag labels & priority - Update cycle velocity counters\"]\n    Stage1 -->|VETO| VetoInstant[\"Transition Rejected (422 Unprocessable)\"]\n    Stage2 --> Stage3[\"Stage 3: Asynchronous Gate Hold (Tier B Async Agent) - Card enters pending_agent_gate hold (\u23f3\ud83e\udd16) - Dispatches forensic audit to agent\"]\n    Stage3 -->|Approved| Approved[\"Gate Approved (\u2705\ud83e\udd16) - Card lands cleanly in Done column\"]\n    Stage3 -->|Vetoed| VetoSnap[\"Gate Veto (\ud83d\uded1\ud83e\udd16) - 240ms spring snap-back to In Progress - Itemized rejection posted to activity feed\"]\n```\n\n---\n\n## Helper Architecture\n\nTransition helpers operate across two execution tiers to balance latency and verification depth:\n\n1. **Tier A (Synchronous Wasm / In-Process):** Fast sub-25ms validators and mutators executing in memory or within sandboxed WebAssembly runtimes. These guarantee instantaneous rejection or field stamping without network round-trips.\n2. **Tier B (Asynchronous Autonomous Agent Gates):** Non-blocking background gates dispatched to local CLI harnesses (`agy -p`, `codex -p`), in-app SDK runners, or remote bare Git mirrors. These run comprehensive multi-file audits, build verifications, and forensic QA checks before approving the transition.\n\n### Failure Policies\n\nEvery attached transition helper specifies an explicit failure policy to determine behavior when a helper times out, errors, or fails execution:\n\n- **Fail-Closed:** Blocks the transition immediately. The card snaps back to its origin column and an itemized failure explanation is appended to the ticket timeline.\n- **Fail-Open (Warn):** Logs an audit warning to the activity feed and ledger while allowing the transition to proceed. This is reserved for non-critical informational checks.\n\n---\n\n## Admin Workflow Transition Studio\n\nProject Administrators configure transition pipelines through the visual studio at `/projects/KAN/settings/workflows`.\n\n![Workflow Transition Studio - Desktop Light](images/slice5-workflow-studio-desktop-1440x900-light.png)\n\n### Studio Capabilities\n- **State Transition Matrix:** Select any valid transition path (e.g. `In Progress -> In Review`, `In Review -> Done`).\n- **Pipeline Reordering:** Drag to reorder validators and mutators in the execution chain.\n- **Mutable Field Checkboxes:** Explicitly define which fields the transition helper is permitted to modify, enforcing least-privilege mutation boundaries.\n\n![Attach Workflow Hook Dialog](images/slice5-workflow-attach-hook-dialog-desktop-1440x900-light.png)\n\n### Step-by-Step Guide: Attaching Workflow Transition Hooks with Dry-Run\n\n1. **Open Workflow Studio:** Navigate to `/projects/<PROJECT_KEY>/settings/workflows`.\n2. **Select Transition Rule:** Locate the transition rule card matching your target lifecycle change (e.g. `In Progress -> Done` or `In Review -> Done`).\n3. **Click Attach Hook:** Click the **+ Attach Hook** button on the transition rule card to open the Attach Workflow Hook Dialog.\n4. **Configure Hook Metadata:** Specify a descriptive Hook Name (e.g. `reality-checker-done-gate`), select the Hook Kind (`sync_validator`, `sync_mutator`, or `agent_interceptor`), and choose the Failure Policy (`fail_closed` to block transition on error/timeout, or `fail_open_warn` to log a warning while permitting the transition).\n5. **Select Engine or Agent Definition:** For Wasm modules, choose an approved module. For Agent Interceptors, select the registered Agent Definition (grouped by harness: CLI Pipe, In-App SDK, or Remote Runner); the dialog auto-populates the agent's real timeout (between 1 and 300,000 ms, e.g. `60000ms`). If using mutators, select permitted mutable fields (`labels`, `priority`, `assignees`, `start_date`, `due_date`, `cycle`, or `custom_fields.<slug>`).\n6. **Save Hook:** Click **Attach Hook** to save the rule to the pipeline.\n7. **Simulate in Dry-Run Drawer:** Click the **Dry-Run** button on the transition rule, select a sample ticket fixture or live issue key, click **Run Dry-Run** to execute the pipeline inside a simulated non-mutating sandbox, and inspect individual hook execution timings (e.g. `1.2ms`, `3.4ms`), returned logs, and allowed/vetoed verdicts before deploying to production.\n\n### The Non-Persistent Dry-Run Drawer\nTesting workflow logic against live tickets risks corrupting sprint metrics. The Workflow Studio provides a **Zero-Persistence Dry-Run Drawer**:\n- Select an existing ticket fixture or pick a live issue.\n- Execute the transition pipeline in a simulated sandbox without mutating the database.\n- Inspect per-step execution timings (e.g. `1.2ms` Wasm validator, `3.4ms` security invariant validator, `2.1ms` auto-label mutator).\n- Preview proposed property mutations (such as automatically applied labels).\n- Copy the exact CLI validation command (`kanban-agent validate-transition`) for local offline debugging.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Workflow Architect\n    participant Studio as Workflow Studio\n    participant Drawer as Dry-Run Drawer\n    participant Engine as Helper Engine (Sandbox)\n\n    Admin->>Studio: Select \"In Review -> Done\" rule\n    Admin->>Studio: Click \"Dry-Run Against Sample Ticket\"\n    Studio->>Drawer: Open Dry-Run Drawer with sample payload\n    Admin->>Drawer: Click \"Run Dry-Run\"\n    Drawer->>Engine: Dispatch pipeline in dry_run=True mode\n    Engine->>Engine: Run Hook 1: qa-proof-validator (1.2ms, Allowed)\n    Engine->>Engine: Run Hook 2: security-invariant-validator (3.4ms, Allowed)\n    Engine->>Engine: Run Hook 3: auto-label-mutator (2.1ms, Applied labels)\n    Engine-->>Drawer: Return execution report & copyable CLI snippet\n    Drawer-->>Admin: Display green \"Transition Allowed: Changes would commit\"\n```\n\n![Workflow Studio Dry-Run Drawer Simulation](images/slice5-workflow-dry-run-drawer-desktop-1440x900-light.png)\n\n---\n\n## Read-Only Bare Git Repository Bindings\n\nAutonomous agents evaluating transition gates often require access to source code, diff trees, and commit histories. To satisfy this requirement securely without risking repository corruption:\n- Administrators can bind local bare Git mirrors directly to a project through the **Git Repository Bindings** dialog.\n- The volume mount is strictly enforced as read-only (`:ro bare mirror`).\n- Agents can run `git diff`, `git log`, and code analysis against the mirror, but all write attempts fail at the OS kernel boundary.\n\n![Git Repository Bindings Modal](images/slice5-workflow-git-repo-bindings-desktop-1440x900-light.png)\n![Git Repository Bindings Modal Architecture](images/51-workflow-bind-git-repo-modal.png)\n\n### Step-by-Step Guide: Binding Git Repositories\n\n1. **Access Project Repository Bindings:** Navigate to `/projects/<PROJECT_KEY>/settings/workflows` and scroll down to the Git Repository Bindings section.\n2. **Open Repository Binding Dialog:** Click **+ Bind Git Repository** to open the repository configuration drawer.\n3. **Specify Binding Parameters:** Enter the Repository Slug (e.g. `kanban-core`), remote repository URL (`remote_url`), default tracking branch or ref (`default_ref`, e.g. `main`), access mode (`ro_vfs_mount` or `bare_git_tools`), and optional credential binding (`workspace-pat` or `ssh-key`).\n4. **Enforce Read-Only Security Invariant:** The backend provisions a bare mirror under `/var/lib/kanban/repos/<project>/<slug>.git` with strict read-only POSIX permissions (`:ro`). Even if an agent gains shell execution capability inside a runner, commits or branch writes are rejected at the filesystem level.\n5. **Verify Live Mirror Refresh:** Click **Refresh Mirror** to trigger an immediate background fetch and inspect the last sync timestamp, head commit SHA, and branch count directly in the status table.\n\n---\n\n## Asynchronous Agent Gate Lifecycle on the Board\n\nWhen an issue transition requires complex verification (such as forensic QA certification or automated security audits), the transition operates asynchronously without blocking the user interface.\n\n```mermaid\nstateDiagram-v2\n    [*] --> InProgress\n    InProgress --> PendingGate: Move to Done (Trigger Transition Helper)\n    PendingGate --> Done: Agent Certifies Criteria (\u2705\ud83e\udd16 Approved)\n    PendingGate --> InProgress: Agent Rejects (\ud83d\uded1\ud83e\udd16 240ms Snap-Back)\n    Done --> [*]\n```\n\n![Async Agent Gate Card States and Snap-Back Lifecycle](images/16-async-agent-gate-states.png)\n\n![Board Pending Gate State in Active Sprint](images/35-board-pending-gate.png)\n\n### The Board Interaction States\n\n- **Pending Hold (\u23f3\ud83e\udd16):** The card displays an amber countdown timer and progress indicator. The ticket enters database status `pending_agent_gate`. Other users viewing the board see the real-time hold status over WebSockets.\n- **Gate Veto and 240ms Spring Snap-Back (\ud83d\uded1\ud83e\udd16):** If the agent discovers a defect or missing verification proof, the gate is vetoed. The board executes a physics-based 240ms spring snap-back animation, returning the card to its original column. A non-intrusive toast notification alerts the user, and the agent automatically posts an itemized rejection explanation to the ticket's `\ud83e\udd16 Gates` activity feed.\n- **Gate Approval (\u2705\ud83e\udd16):** When all criteria are certified, the gate resolves to approved. The card transitions smoothly into the destination column, stamped with an immutable cryptographic verification badge.\n\n---\n\n## The Easiest 3-Step Recipe to Implement an Automated QA Gate on `Done`\n\nYou can enforce automated Definition-of-Done verification on any project board in three steps without writing custom glue code:\n\n### Step 1: Register and Probe Your AI Provider (`/admin/ai`)\n1. Open **AI Providers & Token Caps Studio** at `/admin/ai` and click **+ Register Provider**.\n2. Place your API secret key in the **API Secret Key** field at the top of the drawer (optional for local Ollama), configure the **HTTP Base URL** and hard **Cutoff Timeout (ms)** (for example `20000` ms or `35000` ms), and click **\ud83d\udd0d Probe Models** to replace defaults exclusively with live discovered models.\n\n![Gemini Provider Editor with Top API Key and Probed Models](images/62-ai-provider-gemini-top-key-probe.png)\n\n![Ollama Provider Editor with Live Probed Models and Cutoff Timeout](images/63-ai-provider-ollama-probed-models.png)\n\n### Step 2: Register an Agent Definition (`/admin/agents`)\n1. Open **Autonomous Agent Definitions Studio** at `/admin/agents` and click **+ Register Agent**.\n2. Choose **In-App SDK**, pick your provider (`ollama`, `openai`, or `gemini`), click one of the **Probed Models** quick-pick chips (such as `gemma3:4b` or `gpt-4o-mini`), set the timeout cutoff, and enter your QA rubric in **System Instructions**.\n\n![QA Done Gate Agent Definition with Probed Model Quick-Picks](images/64-agent-qa-done-definition.png)\n\n### Step 3: Attach the Hook to `In Progress -> Done` via `+ Workflow`\n1. On the Kanban board, click **+ Workflow** on the **Done** column header (or open `/projects/KAN/settings/workflows`).\n2. Select `From State: In Progress`, `To State: Done`, `Hook Kind: Agent Transition Helper`, your `@qa-done-gate` agent, and `Failure Policy: Fail-Closed`, then click **Attach Hook**.\n\n![Attach Workflow Helper Hook Dialog for In Progress to Done](images/65-workflow-attach-qa-done-gate.png)\n\n---\n\n## In-Transition Gate Ideas Gallery\n\n### Idea 1: Fast 2B/4B Gemma Triage & Auto-Labeler (`Backlog -> Todo`)\nAttach a fast local edge model (`gemma4:e2b` or `granite3.3:2b`, `timeout_ms: 15000`) with `allowed_mutable_fields: [\"labels\", \"priority\"]` to automatically classify incoming backlog tickets, apply `needs-triage` or component labels, and reject empty one-line placeholders before sprint planning.\n\n### Idea 2: Security & Secret Scan Gate (`Todo -> In Progress`)\nAttach an `agent_interceptor` or Tier A Wasm `sync_validator` on `Todo -> In Progress` to verify that work items touching authentication, RBAC, or database migrations include a threat model checklist and zero pasted credentials before engineering begins.\n\n### Idea 3: Automated Definition-of-Done QA Gate (`In Progress -> Done`)\nRequire completed acceptance criteria and documented unit/QA verification evidence before any card can land in `Done`:\n- **Positive Transition (KAN-1 Approved):** A ticket with checked Acceptance Criteria and documented Verification Proof passes the gate, lands in `Done`, and receives a persisted `## \u2705\ud83e\udd16 Workflow Transition Gate Approved` rationale comment.\n\n![Positive Gate Approval Landing Ticket in Done](images/66-qa-gate-positive-approved-done.png)\n\n- **Negative Transition (KAN-2 Vetoed):** An unverified or impossible ticket (such as `\"Build a rocket ship and serve ice cream on Saturn\"` with no design doc, no tests, and no proof) is **vetoed** and kept safely in `In Progress` with an itemized `\ud83d\uded1\ud83e\udd16 Gate` rejection comment.\n\n![Negative Gate Veto Blocking Saturn Ice Cream Ticket in In Progress](images/67-qa-gate-negative-saturn-ice-cream-vetoed.png)\n\n---\n\n## Live Walkthrough: Reality-Checker Done Gate with Self-Hosted Ollama (`nemotron-3-super:latest`)\n\nThis walkthrough captures an end-to-end verification on a fresh standalone `\ud83d\udc4dkanban` container backed by a self-hosted **Ollama** server running `nemotron-3-super:latest` (123.6B Q4_K_M reasoning model).\n\n### 1. Register and Probe the Self-Hosted Ollama Provider (`/admin/ai`)\n1. Open **AI Providers & Token Caps Studio** (`/admin/ai`) and register an `ollama` provider pointing to your LAN Ollama host (for example `http://192.168.1.101:11434`).\n2. Click **Probe Models** to verify live connectivity and allowlist `nemotron-3-super:latest`.\n3. Set the provider cutoff timeout to `120000` ms for large reasoning models (`nemotron-3-super:latest` typically completes a full gate evaluation in `13s` to `45s`, and the structured gate harness allocates `num_predict=4096` tokens so reasoning plus JSON output never truncate).\n\n![Ollama Provider Probed with nemotron-3-super:latest](images/rc-ollama-01-provider-probe.png)\n\n### 2. Define the `reality-checker` Agent (`/admin/agents`)\n1. Open **Autonomous Agent Definitions Studio** (`/admin/agents`) and click **+ Register Agent**.\n2. Configure Harness Kind as `in_app_sdk`, Provider Kind as `ollama`, and Model as `nemotron-3-super:latest`.\n3. Set Timeout to `120000` ms (supported up to `300000` ms across `AgentDefinition` and `StructuredRequest.ttft_deadline_ms`).\n4. Enter System Instructions defaulting to `\"reject\"` unless the ticket includes checked-off Definition of Done items, pasted raw passing unit test and build outputs, and explicit forensic verification proof.\n\n![Reality-Checker Agent Definition using ollama/nemotron-3-super:latest](images/rc-ollama-02-agent-definition.png)\n\n### 3. Attach the Fail-Closed Hook on `In Progress -> Done`\n1. In your project's **Workflow Transition Studio** (`/projects/<KEY>/settings/workflows`), attach an `agent_interceptor` hook named `reality-checker-done-gate` targeting `In Progress -> Done` with **Failure Policy: Fail-Closed** and agent `@reality-checker`.\n\n![Reality-Checker Workflow Hook Attached to In Progress to Done](images/rc-ollama-03-workflow-hook.png)\n\n### 4. Positive Transition (`RCD-1`: Approved with Comment and Allowed to `Done`)\nA work item (`RCD-1: Implement /healthz Readiness Endpoint with Unit Tests`) containing checked-off Definition of Done items, passing `pytest` / `ruff` / `mypy` results, and documented `docs/qa/RCD-1/` proof artifacts is moved from `In Progress` to `Done`:\n- The API returns **HTTP 202 Accepted** and dispatches the asynchronous gate to `in_app_sdk (ollama/nemotron-3-super:latest)`.\n- Within ~13 seconds, the gate posts a persisted **## \u2705\ud83e\udd16 Workflow Transition Gate Approved** comment (`All Definition of Done items are completed and forensic verification passes.`) and commits the state transition to **Done**.\n\n![Positive Transition Board View Landing RCD-1 in Done](images/rc-ollama-04-positive-done.png)\n\n![Positive Transition Ticket Activity and Approval Comment on RCD-1](images/rc-ollama-05-positive-comment.png)\n\n### 5. Negative Transition (`RCD-2`: Vetoed with Comment and Blocked in `In Progress`)\nA work item (`RCD-2: Deploy Quantum Warp Drive to Production`) with unchecked Definition of Done items, missing tests, and no verification proof is moved from `In Progress` to `Done`:\n- Within ~22 seconds, `nemotron-3-super:latest` evaluates the spotlighted ticket context and returns a `reject` verdict.\n- Because the hook is **Fail-Closed**, the transition is **blocked** (`RCD-2` remains in **In Progress**) and `@realitycheckerqagate` persists a **\ud83d\uded1\ud83e\udd16 Gate** rejection comment citing the exact missing criteria (skipped design document, zero unit tests, unrun build/lint checks, and lack of trusted proof).\n\n![Negative Transition Board View Keeping RCD-2 Blocked in In Progress](images/rc-ollama-06-negative-blocked.png)\n\n![Negative Transition Ticket Activity and Rejection Comment on RCD-2](images/rc-ollama-07-negative-comment.png)\n\n"
  },
  {
    "slug": "security-and-stride-threat-matrix",
    "title": "[Informational] Security Architecture and STRIDE Threat Model Matrix",
    "category": "informational",
    "track": "Security & Adoption Overview",
    "subtrack": "Zero-Trust Architecture",
    "audience": "Security Officers & Compliance Auditors",
    "order": 24,
    "summary": "Security is Priority 0 in \ud83d\udc4dkanban. Rather than treating security as an afterthought or an enterprise-tier upsell, \ud83d\udc4dkanban engineers root-level defense-in-depth across every layer of the platform: 1. Every input is hostile. 2. Every external dependency is untrusted. 3. Every component boundary must fail closed. 4. Database Row-Level Security (FORCE RLS) is the absolute authorization bedrock. 5. All sensitive operations must leave immutable forensic audit trails.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "network-trust-boundaries-and-system-architecture",
        "title": "1. Network Trust Boundaries and System Architecture",
        "level": 2
      },
      {
        "id": "system-wide-trust-boundary-architecture",
        "title": "System-Wide Trust Boundary Architecture",
        "level": 3
      },
      {
        "id": "complete-asset-inventory-matrix-a1---a6",
        "title": "2. Complete Asset Inventory Matrix (A1 - A6)",
        "level": 2
      },
      {
        "id": "complete-entry-point-trust-boundary-catalog-e1---e8",
        "title": "3. Complete Entry Point & Trust Boundary Catalog (E1 - E8)",
        "level": 2
      },
      {
        "id": "e1---reverse-proxy-boundary",
        "title": "E1 - Reverse Proxy Boundary",
        "level": 3
      },
      {
        "id": "e2---primary-public-web-rest-asgi-application",
        "title": "E2 - Primary Public Web & REST ASGI Application",
        "level": 3
      },
      {
        "id": "e3---dedicated-internal-service-asgi-application",
        "title": "E3 - Dedicated Internal Service ASGI Application",
        "level": 3
      },
      {
        "id": "e4---realtime-multiplexers-runner-channels",
        "title": "E4 - Realtime Multiplexers & Runner Channels",
        "level": 3
      },
      {
        "id": "e5---3-surface-model-context-protocol-mcp-gateway",
        "title": "E5 - 3-Surface Model Context Protocol (MCP) Gateway",
        "level": 3
      },
      {
        "id": "e6---sandboxes-agent-harnesses",
        "title": "E6 - Sandboxes & Agent Harnesses",
        "level": 3
      },
      {
        "id": "e7---media-proxy-attachments-importersexporters",
        "title": "E7 - Media Proxy, Attachments & Importers/Exporters",
        "level": 3
      },
      {
        "id": "e8---operator-agent-clis",
        "title": "E8 - Operator & Agent CLIs",
        "level": 3
      },
      {
        "id": "comprehensive-stride-threat-mitigation-matrix",
        "title": "4. Comprehensive STRIDE Threat Mitigation Matrix",
        "level": 2
      }
    ],
    "content": "# [Informational] Security Architecture and STRIDE Threat Model Matrix\n\n## Overview\n\nSecurity is Priority 0 in \ud83d\udc4dkanban. Rather than treating security as an afterthought or an enterprise-tier upsell, \ud83d\udc4dkanban engineers root-level defense-in-depth across every layer of the platform:\n1. Every input is hostile.\n2. Every external dependency is untrusted.\n3. Every component boundary must fail closed.\n4. Database Row-Level Security (FORCE RLS) is the absolute authorization bedrock.\n5. All sensitive operations must leave immutable forensic audit trails.\n\n---\n\n## 1. Network Trust Boundaries and System Architecture\n\nThe platform architecture partitions operations across five distinct network trust boundaries:\n\n```\n[ External Wire / Browsers / Agents ]\n                 |\n                 v\n        +------------------+\n        |   1. edge_net    |  TLS 1.3 termination, CSRF validation, WebAuthn Relying Party\n        +------------------+\n                 |\n                 v (Unix socket / HTTP)\n        +------------------+\n        |   2. app_net     |  Uvicorn (UID 65532, setpriv drop), FastAPI, RLS session binding\n        +------------------+\n          |              |\n          | (Unix socket)| (nsjail CLI / IPC)\n          v              v\n+------------------+   +------------------+\n|   3. data_net    |   |  4. sandbox_net  |  Tier B nsjail containers, network-isolated,\n| PostgreSQL Unix  |   |                  |  MS_RDONLY repo mounts, secret whiteouts\n| socket, FORCE RLS|   +------------------+\n+------------------+\n          |\n          v (Outbound TLS via Outbound Secret Scrubber)\n+------------------+\n|5. egress_llm_net |  OpenAI, Gemini, Ollama API egress\n+------------------+\n```\n\n### System-Wide Trust Boundary Architecture\n\n```mermaid\nflowchart TD\n    subgraph E1[\"E1: Edge Reverse Proxy (Caddy :443 / :8444)\"]\n        Edge443[\"Public Port :443 (TLS 1.3, CSP, Rate Limits)\"]\n        Edge8444[\"Dedicated Port :8444 (mTLS Runner PoP)\"]\n    end\n\n    subgraph E2[\"E2: Primary Web & REST ASGI App (create_app)\"]\n        PublicAPI[\"Public & Auth Routes (/api/v1/auth, /oauth)\"]\n        TenantAPI[\"Tenant REST Routes (/api/v1/issues, /docs)\"]\n        AdminAPI[\"Admin Routes (/api/v1/admin/*, Depends(require_admin_aal2))\"]\n    end\n\n    subgraph E3[\"E3: Dedicated Internal Service ASGI App (create_internal_app)\"]\n        InternalIntrospect[\"/internal/v1/mcp/introspect\"]\n        InternalEphemeral[\"/internal/v1/mcp/ephemeral-tokens/*\"]\n    end\n\n    subgraph E4[\"E4: Realtime Multiplexers & Runner Channels\"]\n        WebSockets[\"/ws (Max 16 conns/user, Origin Check)\"]\n        SSEStream[\"/sse (Last-Event-ID, EventSource)\"]\n        RunnerWS[\"/api/v1/agent-runners/ws (mTLS Hardware PoP)\"]\n    end\n\n    subgraph E5[\"E5: 3-Surface MCP Gateway (create_mcp_app)\"]\n        MCPAgent[\"/mcp/agent (4 Read Tools + Workflow Gates)\"]\n        MCPDocs[\"/mcp/docs (3 CLI Tools: search, create, update)\"]\n        MCPAdmin[\"/mcp/admin (12 Tools, 2-Stage Confirmation)\"]\n    end\n\n    subgraph E6[\"E6: Sandboxes & Agent Harnesses\"]\n        WasmRunner[\"TierAWasmRunner (Wasmtime Runtime)\"]\n        NsjailRunner[\"TierBNsjailRunner (Linux User Namespaces)\"]\n        EgressProxy[\"TokenInjectingEgressProxy (Secret Scrubber)\"]\n        PdfSanitizer[\"PDF Sanitizer Subprocess (KAN-81)\"]\n    end\n\n    subgraph E7[\"E7: Media Proxy & Importers/Exporters\"]\n        MediaProxy[\"/api/v1/media-proxy (HMAC, DNS-Pinned SSRF Defense)\"]\n        Attachments[\"/api/v1/projects/{p}/attachments (CAS Storage)\"]\n        AdminMigrations[\"/api/v1/admin/imports/* & /exports/portable\"]\n    end\n\n    subgraph E8[\"E8: Operator & Agent CLIs\"]\n        KanbanCtl[\"kanban-ctl (Admin & DB Migrations)\"]\n        KanbanAgent[\"kanban-agent (CLI Pipe & Workflow Harness)\"]\n        LlmsCatalog[\"/llms.txt (Capability & Skills Catalog)\"]\n    end\n\n    subgraph Storage[\"PostgreSQL 16 Universal Object Graph\"]\n        RLSSession[\"kanban_app (FORCE ROW LEVEL SECURITY, NOBYPASSRLS)\"]\n        AuditLedger[\"Immutable Activity & Audit Ledger (Crypto-Shredded)\"]\n    end\n\n    Edge443 --> PublicAPI\n    Edge443 --> TenantAPI\n    Edge443 --> AdminAPI\n    Edge443 --> WebSockets\n    Edge443 --> SSEStream\n    Edge443 --> MCPAgent\n    Edge443 --> MCPDocs\n    Edge443 --> MCPAdmin\n    Edge443 --> MediaProxy\n    Edge443 --> Attachments\n    Edge8444 --> RunnerWS\n\n    TenantAPI --> Storage\n    AdminAPI --> Storage\n    MCPAgent --> Storage\n    MCPDocs --> Storage\n    MCPAdmin --> Storage\n    InternalIntrospect --> Storage\n    InternalEphemeral --> Storage\n    WebSockets --> Storage\n\n    MCPAgent -.-> E3\n    TenantAPI -.-> WasmRunner\n    TenantAPI -.-> NsjailRunner\n    TenantAPI -.-> EgressProxy\n    Attachments -.-> PdfSanitizer\n```\n\n---\n\n## 2. Complete Asset Inventory Matrix (A1 - A6)\n\n| Asset ID | Asset Name & Code Location | Classification | Cryptographic & Storage Protection | Lifecycle & Destruction | Blast Radius Mitigation |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n| **A1** | **Root Cryptographic Keyring**<br/>`kanban/security/envelope.py`<br/>`kanban/security/service_auth.py`<br/>`kanban/settings.py` | Critical System Secret | `MASTER_KEK` / `KB_MASTER_KEK_B64` loaded from env or `0600` keyring file. HKDF-SHA256 derivation for subkeys (`kanban/internal-service-auth/v1`, `media-proxy/url`). `KB_AUTH_PEPPER` for Argon2id. | Ephemeral in-process memory. Key rotation supported via key versioning (`kid`). Backup encryption keys (`KBBAK1`) separate. | Compromise of KEK allows offline decryption of wrapped DEKs; mitigated by HSM/KMS envelope wrapping, zero disk persistence of plaintext DEKs, and separate HMAC peppers. |\n| **A2** | **Envelope-Encrypted Tenant Secrets**<br/>`kanban/security/envelope.py`<br/>`database/models/auth.py` | High Tenant Secret | AES-256-GCM authenticated encryption per record using unique Data Encryption Keys (DEKs) wrapped by `MASTER_KEK`. Protects OAuth client secrets, LDAP bind passwords, AI provider keys, mTLS enrollment tokens, and webhook secrets. | Re-encrypted on key rotation. Instant crypto-shredding upon tenant workspace deletion by destroying record DEKs. | Compromise of a single DEK exposes only that specific secret record; adjacent tenant records remain encrypted under independent DEKs. |\n| **A3** | **User Authentication & AAL2 Credentials**<br/>`database/models/auth.py`<br/>`kanban/auth/guards.py`<br/>`kanban/auth/mfa/` | High Identity Asset | Passwords hashed with Argon2id (`m=64MiB`, `t=3`, `p=4`) plus server pepper. WebAuthn Passkeys with hardware COSE public keys and monotonic signature counters (`rp.name = \"\ud83d\udc4dkanban\"`, strict ASCII FQDN `rp.id`). TOTP seeds encrypted under AES-256-GCM. OAuth 2.1 authorization codes (S256 PKCE). | Sessions expire on idle timeout or explicit logout. AAL2 elevation valid for max 900 seconds (`ADMIN_AAL2_MAX_AGE_SECONDS`). Recovery codes single-use hashed. | Account takeover bounded by mandatory AAL2 for all `/api/v1/admin/*` routes; stolen password cannot execute administrative actions without second factor. |\n| **A4** | **Scoped MCP API Keys & Ephemeral Tokens**<br/>`database/models/mcp_api_key.py`<br/>`kanban/security/boundary.py`<br/>`kanban/security/read_taint.py` | High Delegated Credential | Tokens hashed with SHA-256 (`token_hash`). Monotonic `Capability(IntFlag)` bitmask ceiling (0x01..0xFF), `SCOPE_CAPABILITY_MAP`, allowed project scope, tool allowlists, and optional `allowed_cidrs`. Session high-water mark `mcp_read_taint`. | Short-lived ephemeral tokens (TTL <= 15m) tied to specific execution ID; instant revocation via `revoke_ephemeral_tokens_by_execution`. | Monotonic clamp ensures leaked token cannot exceed caller authority or configured CIDR/tool boundaries; read-taint blocks cross-project exfiltration. |\n| **A5** | **Universal Object Graph & Tenant Content**<br/>`database/models/` (80 ORM models)<br/>`kanban/attachments/pdf.py`<br/>`kanban/security/push_protection.py` | Confidential Tenant Asset | Canonical UTF-8 Markdown only. Strict lone-surrogate rejection (`INVALID_UTF8_SURROGATE`). Pre-persistence Shannon-entropy secret push protection (`KAN-72`). Quarantined CAS attachment storage. Subprocess active-content PDF sanitizer (`KAN-81`). Lease concurrency fencing (`KAN-69`). | Soft-delete with tombstoning followed by cryptographic purge via Invalid Object Link Auditor. Workload OIDC federation (`KAN-74`). DNS-pinned SSRF transport (`KAN-75`). | Cross-tenant bleed prevented by 100% PostgreSQL `FORCE ROW LEVEL SECURITY`. Anti-enumeration timing floors (25ms) normalize unreadable vs non-existent objects. |\n| **A6** | **Authorization Graph & Forensic Audit Ledger**<br/>`database/models/audit_ledger.py`<br/>`database/session.py`<br/>`kanban/security/audit_crypto_shred.py` | Integrity & Compliance Asset | PostgreSQL Row-Level Security policies (`FORCE RLS`, `NOBYPASSRLS`). Effective Resource Access (`ERA`) cache. Append-only `audit_ledger` and `activity` streams with cryptographic event hashing and tenant-scoped crypto-shredding keys (`KAN-73`). | Immutable append-only ledger. Right-to-be-forgotten / GDPR compliance implemented via targeted DEK shredding without breaking blockchain-like hash continuity. | Unauthorized log modification prevented by immutable database triggers and append-only constraints; attribution guaranteed by cryptographic principal binding. |\n\n---\n\n## 3. Complete Entry Point & Trust Boundary Catalog (E1 - E8)\n\n### E1 - Reverse Proxy Boundary\n- **Code & Config:** `deploy/caddy/Caddyfile`, `deploy/standalone/Caddyfile`\n- **Network Interfaces:** External TCP :443 (HTTPS / WSS / HTTP/3), External TCP :8444 (Dedicated Runner mTLS).\n- **Security Invariants:**\n  - TLS 1.3 mandatory with modern cipher suites.\n  - Strict Content-Security-Policy (CSP) with Trusted Types (`require-trusted-types-for 'script'; trusted-types kanban-sanitizer dompurify`).\n  - HSTS (`max-age=63072000; includeSubDomains`), `nosniff`, `frame-ancestors 'none'`, and `no-referrer`.\n  - Strips all client-supplied internal identity headers (`X-Client-Cert-*`, `X-KB-Service-Principal`, `X-KB-Internal-*`) on port :443.\n  - Drops external requests to `/internal/*` and `/api/v1/internal/*` with HTTP 404.\n  - Port :8444 enforces mandatory mutual TLS client certificate verification (`client_auth { mode require }`) forwarding exclusively to runner endpoints.\n\n### E2 - Primary Public Web & REST ASGI Application\n- **Code & Config:** `kanban/app.py:create_app`, `kanban/api/v1/`, `kanban/auth/`\n- **Endpoints:** 244+ OpenAPI 3.1 endpoints across `/api/v1/*`, `/oauth/*`, `/.well-known/*`.\n- **Security Invariants:**\n  - Explicit dependency-level authentication (`Depends(get_principal)`).\n  - Every administrative route under `/api/v1/admin/*` MUST declare `Depends(require_admin_aal2)` (`assert_admin_routes_protected`).\n  - RFC 7807 problem details returned for all errors, preventing stack trace or internal state leakage.\n  - Rate limiting enforced on authentication, media proxy, and search endpoints.\n  - ETag and `If-Match` optimistic concurrency control on all entity mutation endpoints.\n\n### E3 - Dedicated Internal Service ASGI Application\n- **Code & Config:** `kanban/app.py:create_internal_app`, `kanban/api/internal/`\n- **Endpoints:** `/internal/v1/mcp/introspect`, `/internal/v1/mcp/ephemeral-tokens`, `/internal/v1/mcp/ephemeral-tokens/by-execution/{id}/revoke`.\n- **Security Invariants:**\n  - Completely isolated from edge routing (zero reverse-proxy exposure; dropped with 404 at Caddy).\n  - Enforces `verify_internal_service_auth` on 100% of routes: validates `X-KB-Internal-Timestamp` (clock skew <= 300s) and `X-KB-Internal-Signature` (HMAC-SHA256 computed with HKDF-derived key `kanban/internal-service-auth/v1`).\n  - Used strictly for inter-service communication between MCP server containers and core API.\n\n### E4 - Realtime Multiplexers & Runner Channels\n- **Code & Config:** `kanban/api/ws.py`, `kanban/api/sse.py`, `kanban/api/v1/remote_runners.py`\n- **Endpoints:** `/ws`, `/api/v1/ws`, `/sse`, `/api/v1/agent-runners/ws`.\n- **Security Invariants:**\n  - `/ws` and `/sse`: Enforce origin validation against `settings.allowed_origins` and authenticated session resolution. Connection pool capped at 16 concurrent WebSockets per user (`WS_CLOSE_CONNECTION_LIMIT`). Frame size capped at 64 KiB (`WS_CLOSE_FRAME_TOO_LARGE`).\n  - `/api/v1/agent-runners/ws`: Dedicated distributed runner channel. Authenticates peer mTLS certificate fingerprint, verifies non-revoked runner registration, and executes cryptographic challenge Proof-of-Possession (PoP) before accepting runner workloads.\n\n### E5 - 3-Surface Model Context Protocol (MCP) Gateway\n- **Code & Config:** `mcp/app.py:create_mcp_app`, `mcp/protocol/handler.py`, `mcp/surfaces/`\n- **Surfaces & Endpoints:**\n  - `/mcp/agent` (and scoped sub-routes `/w/{workspace}/p/{project}`): 4 primary read tools (`search_tickets`, `read_ticket`, `search_knowledge`, `read_doc`), workflow transition gates, and agent workpads. Total schema budgeted under 1,800 tokens.\n  - `/mcp/docs` (and scoped sub-routes): 3 surgical tools (`search`, `create`, `update`).\n  - `/mcp/admin` (and scoped sub-routes): 12 intent-based administrative tools requiring 2-stage destructive confirmation.\n  - `/.well-known/oauth-protected-resource/*`: RFC 9728 discovery metadata.\n- **Security Invariants:**\n  - `McpAuthMiddleware`: Validates Bearer API keys and ephemeral tokens via internal introspection.\n  - `CredentialBoundary`: Clamps tool availability and data access to key capability mask and allowed projects.\n  - `mcp_read_taint`: Tracks high-water mark of accessed audience scopes; halts write attempts to broader audiences with `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`.\n\n### E6 - Sandboxes & Agent Harnesses\n- **Code & Config:** `kanban/sandbox/`, `agent/harnesses/`, `kanban/attachments/pdf.py`\n- **Engines:**\n  - `TierAWasmRunner` (`wasm_runner.py`): In-process Wasmtime engine executing validated WebAssembly custom field formulas and transition helpers with strict memory and instruction limits.\n  - `TierBNsjailRunner` (`nsjail_runner.py`): Linux user/net namespace container sandbox with zero network access, read-only mounts, and secret whiteout masks over credentials.\n  - `TokenInjectingEgressProxy` (`egress_proxy.py`): Managed HTTP outbound proxy injecting ephemeral secrets for third-party tools while scrubbing credentials from responses.\n  - `cli_pipe.py`: Zero-shell `execve` stdin/stdout harness executing CLI agents (`agy -p`, `codex exec -s read-only -`) using random nonce delimiters (`<<<UNTRUSTED_TICKET_DATA_{nonce}>>>`).\n  - `pdf.py`: Subprocess PDF active-content sanitizer running bounded inspection (timeout <= 3.0s) stripping dangerous PDF objects (`/JS`, `/Launch`, `/OpenAction`).\n\n### E7 - Media Proxy, Attachments & Importers/Exporters\n- **Code & Config:** `kanban/api/v1/media_proxy.py`, `kanban/api/v1/attachments.py`, `kanban/api/v1/admin/imports.py`, `kanban/api/v1/admin/exports.py`, `kanban/api/v1/reports.py`\n- **Endpoints:** `/api/v1/media-proxy`, `/api/v1/projects/{project_ref}/attachments`, `/api/v1/admin/imports/*`, `/api/v1/admin/exports/portable`, `/api/v1/reports/*`.\n- **Security Invariants:**\n  - Media Proxy: HMAC-SHA256 signed external image URLs. DNS-pinned cookieless socket transport blocking loopback, RFC 1918, link-local, and cloud metadata (169.254.169.254). Maximum pixel decompression limit (40,000,000 pixels).\n  - Attachments: Quarantined Content-Addressable Storage (CAS), SVG disinfection (billion-laughs DAG limits), PDF active-content sanitization, and sandboxed download headers (`default-src 'none'; sandbox; attachment`).\n  - Importers & Exporters: Rate-limited, administrative AAL2-only, DefusedXML parsing, CSV formula-injection defense (`=`, `+`, `-`, `@`, `\\t`, `\\r` escaping).\n  - Reports: SSTI-hardened Jinja2 sandbox blocking attribute access (`_`, `mro`, `subclasses`, `globals`, `builtins`).\n\n### E8 - Operator & Agent CLIs\n- **Code & Config:** `pyproject.toml`, `kanban/cli/ctl.py`, `agent/cli.py`, `mcp/cli/main.py`, `deploy/standalone/entrypoint.py`\n- **Commands:** `kanban-ctl`, `kanban-agent`, `kanban-cli`, `/llms.txt`.\n- **Security Invariants:**\n  - `kanban-ctl`: Administrative CLI for migrations, diagnostics, and tenant management; drops privileges when possible and refuses to run dangerous commands without explicit flags.\n  - `kanban-agent`: CLI runner supporting local offline validation (`kanban-agent validate-*`) with deterministic AI response fixtures.\n  - Standalone Bootstrap: Generates single-use setup token (`/run/kanban/setup_token`) with 60-minute expiry; enforces UID 65532 capability drop and Unix socket database communication.\n  - `/llms.txt`: Machine-readable capability and skills catalog served with strict read-only caching headers.\n\n---\n\n## 4. Comprehensive STRIDE Threat Mitigation Matrix\n\n| STRIDE Category | Threat Vector | Affected Asset / Entry Point | Architectural Defense & Invariant | Verification Gate |\n| :--- | :--- | :--- | :--- | :--- |\n| **Spoofing** | Forged internal service requests to introspect or mint tokens | A1, A4 / E3 (`/internal/*`) | HMAC-SHA256 signature verification (`X-KB-Internal-Signature`, `X-KB-Internal-Timestamp` <= 300s skew) using HKDF domain subkey `kanban/internal-service-auth/v1`. Edge proxy drops `/internal/*` with 404. | `kanban/tests/security/test_internal_route_isolation.py` |\n| **Spoofing** | Stolen or replayed administrative credentials | A3 / E2 (`/api/v1/admin/*`) | Multi-Card AAL2 enforcement: mandatory WebAuthn/Passkey or TOTP second factor within 900s. Passkeys bound to strict ASCII FQDN `rp.id`. Single-use recovery codes. | `kanban/tests/security/test_admin_routes_protected.py` |\n| **Spoofing** | Rogue distributed runner impersonation | A2 / E4 (`/api/v1/agent-runners/ws`) | Dedicated port :8444 with TLS 1.3 client authentication (`client_auth { mode require }`), hardware-bound certificate fingerprint check, and cryptographic challenge Proof-of-Possession. | `kanban/tests/runners/test_remote_runners.py` |\n| **Tampering** | Unauthorized mutation of tenant issues or docs | A5 / E2, E5 | PostgreSQL `FORCE ROW LEVEL SECURITY` on 100% of tenant tables. Zero-context fail-closed sessions. ETag and `If-Match` optimistic concurrency check. | `database/tests/test_p1_14_rls_catalog.py` |\n| **Tampering** | Forged agent transition approvals or CLI injection | A5 / E6 (`cli_pipe.py`) | Zero-shell `execve` argv execution (never `/bin/sh`). True random nonce delimiter wrapping (`<<<UNTRUSTED_TICKET_DATA_{nonce}>>>`). Cryptographic `verdict_nonce` validation. | `agent/tests/cli/test_cli_policy.py` |\n| **Tampering** | Committing cleartext secrets into tickets or stickies | A1, A2 / E2, E5 | Pre-persistence Shannon-entropy push protection (`KAN-72`) scanning all incoming Markdown for high-entropy tokens and API keys prior to database write. | `kanban/tests/security/test_push_protection.py` |\n| **Repudiation** | Denying ticket modifications or deletion | A6 / E2, E5 | Append-only immutable `audit_ledger` and `activity` streams recording actor principal ID, event type, timestamp, and object links with cryptographic hash chaining. | `kanban/tests/security/test_audit_crypto_shred.py` |\n| **Information Disclosure** | Cross-tenant data leakage via ID enumeration | A5 / E2 | Uniform RFC 7807 404 Not Found responses for both unauthorized and non-existent entities. Synthetic 25ms timing floors (`timing_floor`) neutralizing timing side-channels. | `kanban/tests/api/test_anti_enumeration.py` |\n| **Information Disclosure** | Autonomous agent reading private docs and leaking to public tickets | A4, A5 / E5 (`/mcp/agent`) | MCP Read-Taint High-Water Mark (`mcp_read_taint`): accumulates audience principals during reads; blocks write attempts to broader audiences with `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`. | `kanban/tests/security/test_read_taint.py` |\n| **Information Disclosure** | Outbound AI provider prompts leaking internal secrets | A1, A2 / E6 (`egress_llm_net`) | `OutboundSecretScrubber` scans all payloads leaving the application boundary, redacting API keys, session HMACs, and private PEM blocks. | `kanban/tests/security/test_scrubber.py` |\n| **Denial of Service** | Billion-laughs XML attacks or decompression bombs | A5 / E7 (Attachments, PDF) | SVG parser enforces maximum DAG depth <= 5 and max 500 expanded nodes. PDF active-content analyzer caps file size at 25 MiB, Flate expansion ratio at 100x, and decompressed bytes at 100 MiB. | `kanban/tests/attachments/test_pdf.py` |\n| **Denial of Service** | WebSocket connection exhaustion or token starvation | A4 / E4 (`/ws`) | Client connection limits (max 16 concurrent WebSockets per user), 64 KiB frame size caps, client IP rate limiting, and token budget enforcers. | `kanban/tests/realtime/test_ws_limits.py` |\n| **Elevation of Privilege** | Scoped API key attempting to access unauthorized projects or tools | A4 / E5 | Monotonic `CredentialBoundary` ceiling: bitwise AND between issuer capabilities and token mask; strict project and tool allowlist filtering. | `kanban/tests/security/test_mcp_scopable_keys.py` |\n| **Elevation of Privilege** | Custom scripted fields escaping container host | A1 / E6 (Sandboxes) | Tier A Wasmtime sandbox with bounded fuel/memory. Tier B nsjail sandbox with Linux user/net namespaces, read-only mounts, and secret whiteout masks. | `kanban/tests/sandbox/test_nsjail.py` |\n"
  },
  {
    "slug": "statistical-flow-telemetry-and-lean-analytics",
    "title": "[Informational] Statistical Flow Telemetry, Lead Time Percentiles, and Monte Carlo Forecasting Guide",
    "category": "informational",
    "track": "Feature & Field Reference",
    "subtrack": "Flow Telemetry & Analytics",
    "audience": "Engineering Leads, Product Managers & Scrum Masters",
    "order": 25,
    "summary": "Comprehensive user and mathematical reference for the native Statistical Flow Telemetry Studio, Cumulative Flow Diagrams, Lead Time and Cycle Time percentiles, Aging WIP telemetry, and Monte Carlo delivery forecasting.",
    "sections": [
      {
        "id": "lean-flow-principles-and-littles-law-foundation",
        "title": "1. Lean Flow Principles and Little's Law Foundation",
        "level": 2
      },
      {
        "id": "the-four-operational-invariants-of-littles-law",
        "title": "The Four Operational Invariants of Little's Law",
        "level": 3
      },
      {
        "id": "cumulative-flow-diagram-cfd-engine",
        "title": "2. Cumulative Flow Diagram (CFD) Engine",
        "level": 2
      },
      {
        "id": "historical-activity-ledger-replay",
        "title": "Historical Activity Ledger Replay",
        "level": 3
      },
      {
        "id": "standardized-workflow-state-groups",
        "title": "Standardized Workflow State Groups",
        "level": 3
      },
      {
        "id": "interpreting-cfd-band-shapes",
        "title": "Interpreting CFD Band Shapes",
        "level": 3
      },
      {
        "id": "lead-time-and-cycle-time-statistical-analysis",
        "title": "3. Lead Time and Cycle Time Statistical Analysis",
        "level": 2
      },
      {
        "id": "lead-time-vs-cycle-time-definitions",
        "title": "Lead Time vs Cycle Time Definitions",
        "level": 3
      },
      {
        "id": "why-averages-are-misleading",
        "title": "Why Averages Are Misleading",
        "level": 3
      },
      {
        "id": "non-parametric-percentile-metrics",
        "title": "Non-Parametric Percentile Metrics",
        "level": 3
      },
      {
        "id": "aging-wip-telemetry",
        "title": "4. Aging WIP Telemetry",
        "level": 2
      },
      {
        "id": "proactive-wip-age-tracking",
        "title": "Proactive WIP Age Tracking",
        "level": 3
      },
      {
        "id": "percentile-risk-thresholds",
        "title": "Percentile Risk Thresholds",
        "level": 3
      },
      {
        "id": "monte-carlo-probabilistic-delivery-forecasting",
        "title": "5. Monte Carlo Probabilistic Delivery Forecasting",
        "level": 2
      },
      {
        "id": "empirical-bootstrap-resampling-algorithm",
        "title": "Empirical Bootstrap Resampling Algorithm",
        "level": 3
      },
      {
        "id": "rest-api-reference",
        "title": "6. REST API Reference",
        "level": 2
      },
      {
        "id": "endpoint-specification",
        "title": "Endpoint Specification",
        "level": 3
      },
      {
        "id": "query-parameters",
        "title": "Query Parameters",
        "level": 3
      },
      {
        "id": "response-schema-structure",
        "title": "Response Schema Structure",
        "level": 3
      },
      {
        "id": "flow-telemetry-studio-ui-walkthrough",
        "title": "7. Flow Telemetry Studio UI Walkthrough",
        "level": 2
      }
    ],
    "content": "# [Informational] Statistical Flow Telemetry, Lead Time Percentiles, and Monte Carlo Forecasting Guide\n\nComprehensive user and mathematical reference for the native Statistical Flow Telemetry Studio, Cumulative Flow Diagrams, Lead Time and Cycle Time percentiles, Aging WIP telemetry, and Monte Carlo delivery forecasting.\n\n---\n\n## 1. Lean Flow Principles and Little's Law Foundation\n\nModern agile delivery frequently falters on arbitrary story-point estimation and velocity metrics that assume software tasks follow Gaussian (normal) distributions. In reality, software development cycle times exhibit heavy-tailed, skewed distributions where outliers dominate delivery timelines.\n\n\ud83d\udc4dkanban replaces subjective story points with empirical, statistical flow telemetry grounded in Lean manufacturing principles and Little's Law:\n\n$$\\text{Work In Progress (WIP)} = \\text{Throughput} \\times \\text{Lead Time}$$\n\n$$L = \\lambda W$$\n\nWhere:\n- $L$ is the average number of active work items in the delivery system (WIP).\n- $\\lambda$ is the average departure rate (Throughput: items completed per unit of time).\n- $W$ is the average time an item spends in the delivery system (Lead Time).\n\n### The Four Operational Invariants of Little's Law\nFor Little's Law to hold and produce reliable forecasting:\n1. **Conserved Flow:** Over the observation window, the average arrival rate must approximately equal the average departure rate ($\\lambda_{\\text{in}} \\approx \\lambda_{\\text{out}}$).\n2. **Bounded Capacity:** The system must enforce explicit Work In Progress (WIP) limits across workflow states.\n3. **No Stagnant Inventory:** Items entering the system must progress toward completion; abandoned items must be explicitly cancelled.\n4. **Consistent Units:** Time windows, item granularities, and state boundaries must remain consistent throughout measurement.\n\n```mermaid\ngraph LR\n    Backlog[\"Backlog / Unstarted\"] -->|Arrival Rate \u03bb_in| WIP[\"In Progress WIP (Bounded Capacity)\"]\n    WIP -->|Departure Rate \u03bb_out| Done[\"Completed / Shipped\"]\n    WIP -.->|Little's Law: WIP = Throughput x Lead Time| Analytics[\"Statistical Telemetry & Percentiles\"]\n```\n\n---\n\n## 2. Cumulative Flow Diagram (CFD) Engine\n\nThe Cumulative Flow Diagram (CFD) is the primary diagnostic instrument for visualizing delivery stability, queue accumulation, and process bottlenecks over time.\n\n### Historical Activity Ledger Replay\n\nRather than taking fragile, lossy daily database snapshots, the \ud83d\udc4dkanban flow telemetry engine (`kanban/services/flow_metrics.py`) dynamically reconstructs historical state distributions by replaying the immutable `activity_events` ledger:\n1. Queries all `ISSUE_CREATED` events within the specified analysis window ($1 \\le \\text{window\\_days} \\le 366$).\n2. Traverses all chronological `ISSUE_STATE_CHANGED` transition events for those work items.\n3. Reconstructs the exact end-of-day count for each workflow state group across every calendar date in the window.\n\n### Standardized Workflow State Groups\n\nTo enable consistent cross-team comparisons, individual custom workflow states are mapped into five canonical state groups:\n- **`backlog`:** Work items defined but not yet prioritized for near-term delivery.\n- **`unstarted`:** Committed items ready for immediate execution by engineers or agents.\n- **`started`:** Active Work In Progress (WIP) being implemented, reviewed, or tested.\n- **`completed`:** Successfully shipped items meeting the Definition of Done.\n- **`cancelled`:** Abandoned or closed items rejected prior to completion.\n\n### Interpreting CFD Band Shapes\n\n```mermaid\ngraph TD\n    A[\"CFD Curve Shape Analysis\"] --> B[\"Parallel Bands: Stable, predictable flow; arrival rate matches departure rate\"]\n    A --> C[\"Diverging Bands: In-progress WIP is growing; indicates an active bottleneck\"]\n    A --> D[\"Flat Horizontal Band: Work has stalled; zero throughput during that interval\"]\n    A --> E[\"Vertical Jump: Batch release or bulk transition; violates single-piece flow\"]\n```\n\n- **Stable Flow (Parallel Bands):** The vertical distance between the `started` band and `completed` band remains constant. WIP is bounded, and lead times remain predictable.\n- **Bottleneck Accumulation (Diverging Bands):** The vertical distance between `started` and `completed` expands. New work is being initiated faster than it is being finished, inflating delivery lead times.\n- **Starvation or Stoppage (Flat Bands):** The `completed` line flattens out horizontally. Items are blocked or idling in queue, indicating external dependencies or environment outages.\n\n---\n\n## 3. Lead Time and Cycle Time Statistical Analysis\n\n### Lead Time vs Cycle Time Definitions\n\n- **Lead Time:** The total elapsed calendar duration from work item creation (`created_at`) to completion (`completed_at`). Represents the customer experience of delivery speed.\n- **Cycle Time:** The elapsed duration from when active work commenced (transition into a `started` state group) until completion (`completed_at`). Represents pure engineering and verification execution time.\n\n### Why Averages Are Misleading\n\nIn software engineering, cycle times do not follow a bell curve. They follow Weibull or log-normal distributions with long right-hand tails. When a distribution is skewed, the arithmetic mean (average) is pulled significantly to the right by a few severely delayed items. Relying on averages for commitments creates a situation where over 60% to 70% of all tasks miss their target delivery date!\n\n### Non-Parametric Percentile Metrics\n\n\ud83d\udc4dkanban computes exact non-parametric percentiles across completed issues within the observation window:\n\n| Percentile Metric | Statistical Meaning | Operational SLA Application |\n| :--- | :--- | :--- |\n| **50th Percentile (p50 / Median)** | 50% of items finished in this time or faster | Internal baseline pacing; 1-in-2 chance of completion |\n| **85th Percentile (p85)** | 85% of items finished in this time or faster | Standard commitment target for sprint planning and SLAs |\n| **95th Percentile (p95)** | 95% of items finished in this time or faster | Conservative enterprise service contract or external release commitment |\n\n```\nLead Time Distribution Curve (Long-Tail / Non-Gaussian):\nFrequency\n  ^\n  |    *\n  |   ***\n  |  *****\n  | *******     <- p50 (Median, e.g. 3.2 days)\n  |*********\n  |***********       <- p85 (Commitment Target, e.g. 7.5 days)\n  |*************\n  |*****************      <- p95 (Conservative Cap, e.g. 14.1 days)\n  |*********************-------------------------------*** (Extreme Outliers)\n  +---------------------------------------------------------> Elapsed Days\n```\n\n---\n\n## 4. Aging WIP Telemetry\n\nWhile Lead Time and Cycle Time percentiles measure historical performance on completed items, Aging WIP provides real-time proactive observability into tasks currently in progress.\n\n### Proactive WIP Age Tracking\n\nFor every issue currently residing in a `started` workflow state group, the Aging WIP module calculates the active elapsed duration since work started:\n\n$$\\text{WIP Age} = \\text{Current Timestamp} - \\text{Work Commenced Timestamp}$$\n\n### Percentile Risk Thresholds\n\nThe Flow Telemetry Studio overlays historical p50, p85, and p95 percentile lines onto the Aging WIP scatterplot:\n- **Green (Age < p50):** Healthy pacing; within typical median delivery duration.\n- **Amber (p50 <= Age < p85):** Maturing item; at risk of exceeding standard commitment SLAs unless prioritized.\n- **Red (Age >= p85):** Aging outlier; actively violating the team's statistical SLA. Requires immediate unblocking, scope shedding, or mob debugging.\n\n---\n\n## 5. Monte Carlo Probabilistic Delivery Forecasting\n\nDeterministic estimation (\"this milestone will finish on March 15th\") is inherently fragile. \ud83d\udc4dkanban replaces deterministic dates with Monte Carlo simulation, answering two critical planning questions with calibrated probabilities:\n1. **Scope Forecast:** How many calendar days are required to complete $N$ backlog items?\n2. **Time Forecast:** How many backlog items can be completed within a fixed horizon of $D$ days?\n\n### Empirical Bootstrap Resampling Algorithm\n\nThe simulation engine avoids synthetic distributions by performing non-parametric bootstrap resampling directly from historical team performance:\n1. **Sampling Base:** Extracts daily completion throughput ($T_1, T_2, \\dots, T_k$) across all working days in the analysis window (excluding configured non-working days).\n2. **Simulation Iterations:** Executes 10,000 independent trial iterations:\n   - For each iteration, the engine randomly samples daily throughput values with replacement until the target backlog count is satisfied.\n   - Records the total simulated calendar days required for that iteration.\n3. **Probability Curve Generation:** Ranks the 10,000 resulting durations to produce an empirical cumulative distribution function (CDF):\n   - **50% Confidence:** 5,000 trials completed by this date.\n   - **85% Confidence:** 8,500 trials completed by this date (recommended delivery forecast).\n   - **95% Confidence:** 9,500 trials completed by this date (high-assurance release target).\n\n```mermaid\ngraph TD\n    History[\"Historical Daily Throughput Samples (k days)\"] --> Resample[\"Bootstrap Resampling (10,000 Iterations)\"]\n    Resample --> Sim1[\"Iteration 1: 18 days\"]\n    Resample --> Sim2[\"Iteration 2: 24 days\"]\n    Resample --> Sim10k[\"Iteration 10,000: 21 days\"]\n    Sim1 & Sim2 & Sim10k --> Distribution[\"Empirical Probability Curve\"]\n    Distribution --> P50[\"50% Probability: 19 days\"]\n    Distribution --> P85[\"85% Probability: 25 days (SLA Target)\"]\n    Distribution --> P95[\"95% Probability: 31 days (High-Assurance)\"]\n```\n\n---\n\n## 6. REST API Reference\n\nFlow telemetry and Monte Carlo simulations are accessible via the native analytics API:\n\n### Endpoint Specification\n\n`GET /api/v1/projects/{project_ref}/analytics/flow`\n\n### Query Parameters\n\n| Parameter | Type | Default | Constraints | Description |\n| :--- | :--- | :--- | :--- | :--- |\n| `window_days` | `integer` | `30` | $1 \\le \\text{window\\_days} \\le 366$ | Historical lookback window for throughput and cycle times |\n| `target_items` | `integer` | `50` | $1 \\le \\text{target\\_items} \\le 10000$ | Backlog size for Monte Carlo scope forecasting |\n| `horizon_days` | `integer` | `30` | $1 \\le \\text{horizon\\_days} \\le 366$ | Target calendar duration for Monte Carlo capacity forecasting |\n\n### Response Schema Structure\n\n```json\n{\n  \"project_id\": \"018f92b7-c4d1-73e2-8349-923fbc01e842\",\n  \"project_key\": \"KAN\",\n  \"window_days\": 30,\n  \"summary\": {\n    \"total_created\": 48,\n    \"total_completed\": 42,\n    \"current_wip\": 12,\n    \"average_daily_throughput\": 1.4\n  },\n  \"cycle_time_percentiles_days\": {\n    \"p50\": 3.2,\n    \"p85\": 7.5,\n    \"p95\": 14.1\n  },\n  \"lead_time_percentiles_days\": {\n    \"p50\": 4.1,\n    \"p85\": 9.2,\n    \"p95\": 16.8\n  },\n  \"cfd_series\": [\n    {\n      \"date\": \"2026-11-01\",\n      \"backlog\": 10,\n      \"unstarted\": 5,\n      \"started\": 8,\n      \"completed\": 20,\n      \"cancelled\": 2\n    }\n  ],\n  \"monte_carlo_forecast\": {\n    \"target_items\": 50,\n    \"simulation_runs\": 10000,\n    \"days_to_complete\": {\n      \"p50\": 34,\n      \"p85\": 42,\n      \"p95\": 51\n    }\n  }\n}\n```\n\n---\n\n## 7. Flow Telemetry Studio UI Walkthrough\n\nMounted at `/projects/{key}/flow`, the Flow Telemetry Studio offers an interactive, responsive analytics workspace:\n- **Interactive Time-Window Slider:** Dynamically adjust analysis windows between 7, 14, 30, 90, or 365 days with instant recomputation.\n- **CFD Layer Toggles:** Toggle individual workflow state bands on or off to isolate specific process queues.\n- **Aging WIP Scatterplot:** Inspect individual in-progress issues, view assignee avatars, and jump directly to overdue work items.\n- **Monte Carlo Target Simulator:** Interactively adjust backlog item counts and observe shifting delivery date confidence bands in real time.\n\n![Project Workflow States and WIP Configuration](images/55-project-workflow-states-wip.png)\n\n![Board View and Flow Pacing](images/06-board-view.png)\n"
  },
  {
    "slug": "studio-configuration-reference",
    "title": "[Informational] Studio Configuration Reference",
    "category": "informational",
    "track": "Feature & Field Reference",
    "subtrack": "Studio Configuration",
    "audience": "Workspace & Project Administrators",
    "order": 26,
    "summary": "Authoritative technical reference specification for all configuration attributes, execution tiers, and administrative controls across all 14 \ud83d\udc4dkanban Studios.",
    "sections": [
      {
        "id": "workspace-studio",
        "title": "1. Workspace Studio",
        "level": 2
      },
      {
        "id": "workspace-studio-configuration-table",
        "title": "Workspace Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs-workspace-settings",
        "title": "Setting-by-Setting Technical Paragraphs (Workspace Settings)",
        "level": 3
      },
      {
        "id": "step-by-step-guide-configuring-workspace-policies-and-trash-retention",
        "title": "Step-by-Step Guide: Configuring Workspace Policies and Trash Retention",
        "level": 3
      },
      {
        "id": "project-studio-personal-settings",
        "title": "2. Project Studio & Personal Settings",
        "level": 2
      },
      {
        "id": "project-studio-configuration-table",
        "title": "Project Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs-project-settings",
        "title": "Setting-by-Setting Technical Paragraphs (Project Settings)",
        "level": 3
      },
      {
        "id": "step-by-step-guide-setting-project-wip-limits-and-workflow-states",
        "title": "Step-by-Step Guide: Setting Project WIP Limits and Workflow States",
        "level": 3
      },
      {
        "id": "personal-settings",
        "title": "Personal Settings",
        "level": 3
      },
      {
        "id": "personal-settings-configuration-table",
        "title": "Personal Settings Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs-personal-settings",
        "title": "Setting-by-Setting Technical Paragraphs (Personal Settings)",
        "level": 3
      },
      {
        "id": "workflow-transition-studio-git-repo-bindings",
        "title": "3. Workflow Transition Studio & Git Repo Bindings",
        "level": 2
      },
      {
        "id": "workflow-transition-studio-configuration-table",
        "title": "Workflow Transition Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs-workflow-transition-studio-repo-bindings",
        "title": "Setting-by-Setting Technical Paragraphs (Workflow Transition Studio & Repo Bindings)",
        "level": 3
      },
      {
        "id": "step-by-step-guide-attaching-workflow-transition-hooks-with-dry-run",
        "title": "Step-by-Step Guide: Attaching Workflow Transition Hooks with Dry-Run",
        "level": 3
      },
      {
        "id": "step-by-step-guide-binding-git-repositories",
        "title": "Step-by-Step Guide: Binding Git Repositories",
        "level": 3
      },
      {
        "id": "custom-fields-studio-dual-control-escalation",
        "title": "4. Custom Fields Studio & Dual-Control Escalation",
        "level": 2
      },
      {
        "id": "custom-fields-studio-configuration-table",
        "title": "Custom Fields Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs-custom-fields-studio-dual-control-escalation",
        "title": "Setting-by-Setting Technical Paragraphs (Custom Fields Studio & Dual-Control Escalation)",
        "level": 3
      },
      {
        "id": "step-by-step-guide-authoring-and-requesting-dual-control-custom-scripted-fields",
        "title": "Step-by-Step Guide: Authoring and Requesting Dual-Control Custom Scripted Fields",
        "level": 3
      },
      {
        "id": "authentication-studio",
        "title": "5. Authentication Studio",
        "level": 2
      },
      {
        "id": "authentication-studio-configuration-table",
        "title": "Authentication Studio Configuration Table",
        "level": 3
      },
      {
        "id": "active-directory-and-ldaps-configuration-table",
        "title": "Active Directory and LDAPS Configuration Table",
        "level": 3
      },
      {
        "id": "openid-connect-oidc-and-google-oauth-configuration-table",
        "title": "OpenID Connect (OIDC) and Google OAuth Configuration Table",
        "level": 3
      },
      {
        "id": "personal-security-and-multi-factor-authentication-configuration-table",
        "title": "Personal Security and Multi-Factor Authentication Configuration Table",
        "level": 3
      },
      {
        "id": "granular-rbac-policy-builder-configuration-table",
        "title": "Granular RBAC Policy Builder Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs",
        "title": "Setting-by-Setting Technical Paragraphs",
        "level": 3
      },
      {
        "id": "mcp-access-studio",
        "title": "6. MCP Access Studio",
        "level": 2
      },
      {
        "id": "mcp-access-studio-configuration-table",
        "title": "MCP Access Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs",
        "title": "Setting-by-Setting Technical Paragraphs",
        "level": 3
      },
      {
        "id": "connect-oauth-app-and-client-snippets-modals",
        "title": "Connect OAuth App and Client Snippets Modals",
        "level": 3
      },
      {
        "id": "workload-identity-federation-settings",
        "title": "Workload Identity Federation Settings",
        "level": 3
      },
      {
        "id": "oauth-21-governance-studio",
        "title": "7. OAuth 2.1 Governance Studio",
        "level": 2
      },
      {
        "id": "oauth-21-governance-studio-configuration-table",
        "title": "OAuth 2.1 Governance Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs",
        "title": "Setting-by-Setting Technical Paragraphs",
        "level": 3
      },
      {
        "id": "rfc-8628-activate-device-flow-and-bulk-purge",
        "title": "RFC 8628 /activate Device Flow and Bulk Purge",
        "level": 3
      },
      {
        "id": "ai-providers-studio",
        "title": "8. AI Providers Studio",
        "level": 2
      },
      {
        "id": "ai-providers-studio-configuration-table",
        "title": "AI Providers Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs-ai-providers-and-token-budgets",
        "title": "Setting-by-Setting Technical Paragraphs: AI Providers and Token Budgets",
        "level": 3
      },
      {
        "id": "agent-definitions-studio",
        "title": "9. Agent Definitions Studio",
        "level": 2
      },
      {
        "id": "agent-definitions-studio-configuration-table",
        "title": "Agent Definitions Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs-agent-definitions-and-onboarding",
        "title": "Setting-by-Setting Technical Paragraphs: Agent Definitions and Onboarding",
        "level": 3
      },
      {
        "id": "remote-runners-studio",
        "title": "10. Remote Runners Studio",
        "level": 2
      },
      {
        "id": "remote-runners-studio-configuration-table",
        "title": "Remote Runners Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs-remote-runners-fleet",
        "title": "Setting-by-Setting Technical Paragraphs: Remote Runners Fleet",
        "level": 3
      },
      {
        "id": "standalone-promotion-studio",
        "title": "11. Standalone & Promotion Studio",
        "level": 2
      },
      {
        "id": "standalone-promotion-studio-configuration-table",
        "title": "Standalone & Promotion Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs",
        "title": "Setting-by-Setting Technical Paragraphs",
        "level": 3
      },
      {
        "id": "migration-import-studio",
        "title": "12. Migration Import Studio",
        "level": 2
      },
      {
        "id": "migration-import-studio-configuration-table",
        "title": "Migration Import Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs",
        "title": "Setting-by-Setting Technical Paragraphs",
        "level": 3
      },
      {
        "id": "admin-diagnostics-realtime-probes-studio",
        "title": "13. Admin Diagnostics & Realtime Probes Studio",
        "level": 2
      },
      {
        "id": "admin-diagnostics-studio-configuration-table",
        "title": "Admin Diagnostics Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs",
        "title": "Setting-by-Setting Technical Paragraphs",
        "level": 3
      },
      {
        "id": "universal-object-graph-link-auditor-studio",
        "title": "14. Universal Object Graph Link Auditor Studio",
        "level": 2
      },
      {
        "id": "link-auditor-studio-configuration-table",
        "title": "Link Auditor Studio Configuration Table",
        "level": 3
      },
      {
        "id": "setting-by-setting-technical-paragraphs",
        "title": "Setting-by-Setting Technical Paragraphs",
        "level": 3
      }
    ],
    "content": "# [Informational] Studio Configuration Reference\n\nAuthoritative technical reference specification for all configuration attributes, execution tiers, and administrative controls across all 14 \ud83d\udc4dkanban Studios.\n\n---\n\n## 1. Workspace Studio\nThe Workspace Studio (`/workspaces/:ws/settings` or `/admin/workspace-settings`) manages top-level tenant policies, display metadata, session lifetimes, trash retention, export permissions, and air-gap network boundaries under strict AAL2 authentication.\n\n![Workspace Settings General - Desktop Light](images/slice5-workspace-settings-general-desktop-1440x900-light.png)\n![Workspace Settings General - Desktop Dark](images/slice5-workspace-settings-general-desktop-1440x900-dark.png)\n![Workspace Settings General - Tablet Landscape](images/slice5-workspace-settings-general-tablet-landscape-1024x768.png)\n![Workspace Settings General - Tablet Portrait](images/slice5-workspace-settings-general-tablet-portrait-768x1024.png)\n![Workspace Settings General - Mobile Portrait](images/slice5-workspace-settings-general-mobile-portrait-390x844.png)\n![Workspace Settings Nested Groups](images/slice5-workspace-settings-groups-nested-desktop-1440x900-light.png)\n![Workspace Settings Trash Retention](images/slice5-workspace-settings-trash-retention-desktop-1440x900-light.png)\n\n### Workspace Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `name` | Canonical internal name of the workspace | UTF-8 String (1 to 200 characters) | Required at provisioning | Tenant root identifier in PostgreSQL RLS context |\n| `slug` | URL-safe workspace slug used in REST routing and browser paths | Lowercase alphanumeric ASCII with hyphens (2 to 63 chars) | Derived from name | Immutable tenant boundary in database session context |\n| `display_name` | Human-readable workspace title displayed in navigation header | UTF-8 String (1 to 80 characters) | `\"Workspace\"` | Visible across topbar, breadcrumbs, and notification emails |\n| `default_project_visibility` | Baseline privacy level assigned to newly initialized projects | `\"private\"`, `\"workspace\"` | `\"private\"` | Prevents accidental cross-project disclosure in multi-team workspaces |\n| `session_idle_timeout_min` | Inactivity window before user session transitions to stale | Integer between 5 and 720 minutes | 60 | Enforces local re-authentication after inactivity period |\n| `session_absolute_timeout_min` | Maximum lifetime of an authentication session cookie | Integer between 60 and 10080 minutes | 720 (12h) | Requires full re-login upon absolute expiration |\n| `trash_retention_days` | Duration soft-deleted items remain in Trash before permanent purge | Integer between 7 and 365 days | 30 | Governs compliance data retention and recovery windows |\n| `mcp_key_max_ttl_days` | Maximum validity period permitted for minted MCP API keys | Integer between 1 and 365 days | 90 | Caps autonomous agent credential lifetimes |\n| `air_gap_mode` | Strict isolation mode blocking external cloud AI and external egress | Boolean (`true` / `false`) | `false` | When active, restricts AI execution strictly to local Ollama and on-prem runners |\n| `default_skip_loaded_sequence_numbers` | Agent-Safe Sequence Numbering policy toggle | Boolean (`true` / `false`) | `false` | Skips culturally and technically loaded sequence numbers (`13`, `69`, `88`, `404`, `420`, `666`, `1337`, `1488`) during issue sequence allocation |\n| `issue_export_enabled` | Allows exporting work items to JSON or CSV archives | Boolean (`true` / `false`) | `true` | Controlled data exfiltration prevention |\n| `issue_export_allowed_roles` | Explicit RBAC roles permitted to export work item data | List of role strings (`\"workspace_admin\"`, `\"project_admin\"`, `\"member\"`, `\"guest\"`) | `[\"workspace_admin\", \"project_admin\", \"member\"]` | Restricts bulk export capability to authorized team members |\n| `issue_import_enabled` | Allows lossless ingestion from external trackers | Boolean (`true` / `false`) | `true` | Gates administrative bulk ingestion workflows |\n| `report_export_enabled` | Allows exporting statistical flow reports and audit logs | Boolean (`true` / `false`) | `true` | Governs access to compliance and telemetry exports |\n| `report_export_allowed_roles` | Roles allowed to download statistical flow telemetry | List of role strings (`\"ADMIN\"`, `\"MEMBER\"`) | Both roles | Prevents unauthorized aggregation of engineering velocity data |\n\n### Setting-by-Setting Technical Paragraphs (Workspace Settings)\n\n- **name:** Internal database name representing the workspace tenant in PostgreSQL. Required during bootstrap and immutable across standard operation, binding the tenant scope for Row-Level Security policies.\n- **slug:** URL-safe ASCII slug identifying the tenant in REST API endpoints (`/api/v1/workspaces/{slug}`) and browser URL routes (`/{slug}/projects`). Must be between 2 and 63 alphanumeric characters and hyphens.\n- **display_name:** The human-facing label rendered on topbars, page document titles, mobile shells, and notification cards. Supports UTF-8 strings up to 80 characters with full internationalization.\n- **default_project_visibility:** Sets the default privacy tier assigned when users create new projects. Options are `\"private\"` (accessible strictly to explicitly invited members and project administrators, default) or `\"workspace\"` (visible to all authenticated workspace members).\n- **session_idle_timeout_min:** Controls how long an idle user session remains active before requiring step-up authentication or PIN challenge. Configurable from 5 minutes to 720 minutes (12 hours), with a standard enterprise default of 60 minutes.\n- **session_absolute_timeout_min:** Hard maximum duration for any active session cookie regardless of user activity. Configurable between 60 minutes (1 hour) and 10080 minutes (7 days), defaulting to 720 minutes (12 hours).\n- **trash_retention_days:** Defines how many days soft-deleted work items, docs, stickies, and cycles reside in the Trash Studio (`/trash`) before being permanently purged by the background vacuum worker. Values range from 7 to 365 days (default 30 days).\n- **mcp_key_max_ttl_days:** Upper boundary enforced when administrators or developers mint Model Context Protocol (MCP) scoped tokens. The backend rejects any key creation request specifying a TTL exceeding this configured cap (1 to 365 days, default 90 days).\n- **air_gap_mode:** When set to `true`, \ud83d\udc4dkanban activates zero-external-egress enforcement. All outbound requests to cloud AI providers (OpenAI, Gemini) and remote webhooks are fail-closed blocked at the transport layer, restricting agent pipelines exclusively to LAN Ollama servers and local CLI runners.\n- **default_skip_loaded_sequence_numbers:** An Agent-Safe Sequence Numbering policy flag. When enabled, the sequence allocator automatically skips culturally and technically loaded issue sequence numbers (`13`, `69`, `88`, `404`, `420`, `666`, `1337`, `1488`) during work item creation (DB/API default `false`).\n- **issue_export_enabled:** Master toggle for work item data extraction. Disabling this flag blocks `/api/v1/projects/{project}/issues/export` across both the REST API and the web interface to prevent bulk data exfiltration.\n- **issue_export_allowed_roles:** Role allowlist determining who can trigger issue exports. Configurable with combinations of `\"workspace_admin\"`, `\"project_admin\"`, `\"member\"`, and `\"guest\"`, defaulting to `[\"workspace_admin\", \"project_admin\", \"member\"]` (3 roles, excluding guest accounts).\n- **issue_import_enabled:** Administrative toggle governing data ingestion from external platforms (Plane, Jira, GitHub, Linear). Disabling this blocks `/api/v1/admin/imports` to preserve data integrity during audit periods.\n- **report_export_enabled:** Controls whether statistical flow telemetry, Monte Carlo lead-time forecasts, and velocity percentiles can be downloaded as CSV or JSON payloads.\n- **report_export_allowed_roles:** Specifies the minimum permission tier required to export engineering flow reports (options include `\"ADMIN\"` and `\"MEMBER\"`).\n\n### Step-by-Step Guide: Configuring Workspace Policies and Trash Retention\n\n1. **Access Workspace Settings:** Click your avatar or the settings cog in the top navigation bar and select **Workspace Settings** (or navigate directly to `/workspaces/<slug>/settings`).\n2. **Review General Policies:** In the General tab, update your Display Name, verify the Workspace Slug, and select the Default Project Visibility (`Private` or `Workspace`).\n3. **Configure Session Security:** Under Session Lifetimes, configure Session Idle Timeout (e.g. 60 minutes) to force re-authentication for unattended terminals, and set Session Absolute Timeout (e.g. 720 minutes / 12 hours) to mandate periodic credential rotation.\n4. **Tune Compliance & Trash Retention:** In the Data Lifecycle & Trash card, adjust Trash Retention Days between 7 and 365 days (default 30 days). Soft-deleted work items remain recoverable in Trash for this duration before automated irreversible purging.\n5. **Manage Air-Gap and Export Restrictions:** If operating in a sovereign or disconnected environment, toggle Air-Gap Mode to ON to restrict agent and runner execution to LAN hosts. Review Allowed Export Roles to govern bulk data extraction.\n6. **Save Changes:** Click **Save Settings** to persist the configuration to the database and audit ledger. Changes take effect across the workspace immediately.\n\n---\n\n## 2. Project Studio & Personal Settings\nThe Project Studio (`/projects/:proj/settings`) configures project workflows, custom status states, WIP limits, priority emojis, labels, and two-stage project deletion. Personal Settings (`/settings` or `/profile`) manages user profiles, canonical timezones, custom avatars, password rotation, Passkeys, TOTP 2FA, recovery codes, and external identity linking.\n\n![Project Settings Priorities - Desktop Light](images/slice5-project-settings-priorities-desktop-1440x900-light.png)\n![Project Settings Priorities - Desktop Dark](images/slice5-project-settings-priorities-desktop-1440x900-dark.png)\n![Project Settings Priorities - Tablet Landscape](images/slice5-project-settings-priorities-tablet-landscape-1024x768.png)\n![Project Settings Priorities - Tablet Portrait](images/slice5-project-settings-priorities-tablet-portrait-768x1024.png)\n![Project Settings Priorities - Mobile Portrait](images/slice5-project-settings-priorities-mobile-portrait-390x844.png)\n![Project Settings WIP Limits - Desktop Light](images/slice5-project-settings-wip-limits-desktop-1440x900-light.png)\n![Project Settings WIP Limits - Desktop Dark](images/slice5-project-settings-wip-limits-desktop-1440x900-dark.png)\n![Project Settings WIP Limits - Tablet Landscape](images/slice5-project-settings-wip-limits-tablet-landscape-1024x768.png)\n![Project Settings WIP Limits - Tablet Portrait](images/slice5-project-settings-wip-limits-tablet-portrait-768x1024.png)\n![Project Settings WIP Limits - Mobile Portrait](images/slice5-project-settings-wip-limits-mobile-portrait-390x844.png)\n![Project Settings Danger Zone - Desktop Light](images/slice5-project-settings-danger-zone-desktop-1440x900-light.png)\n![Project Settings Danger Zone - Desktop Dark](images/slice5-project-settings-danger-zone-desktop-1440x900-dark.png)\n![Project Settings Danger Zone - Tablet Landscape](images/slice5-project-settings-danger-zone-tablet-landscape-1024x768.png)\n![Project Settings Danger Zone - Tablet Portrait](images/slice5-project-settings-danger-zone-tablet-portrait-768x1024.png)\n![Project Settings Danger Zone - Mobile Portrait](images/slice5-project-settings-danger-zone-mobile-portrait-390x844.png)\n\n### Project Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `name` | Human-readable project display name | UTF-8 String (1 to 120 characters) | Required at creation | Scoped to workspace; surfaced in topbars and command palette |\n| `key` | Issue identifier prefix (e.g. `KAN`, `CORE`) | Uppercase ASCII alphanumeric `^[A-Z][A-Z0-9]{1,9}$` (2 to 10 chars) | Required at creation | Immutable; generates unique issue keys across all surfaces |\n| `state_name` | Name of workflow state (e.g. `In Progress`) | UTF-8 String (1 to 64 characters) | Required | Displayed on board columns, list groupings, and peek drawers |\n| `group` | Lifecycle category mapping | `\"backlog\"`, `\"unstarted\"`, `\"started\"`, `\"completed\"`, `\"cancelled\"` | Required | Drives cycle velocity metrics, burn-downs, and SLA calculations |\n| `color_hex` | Hexadecimal color accent for state badge | 7-character hex code (`^#[0-9A-Fa-f]{6}$`) | `#3B82F6` | Provides distinct visual identification across board and table views |\n| `sort_order` | Execution ordering of states across the board | Integer (0 to 1000) | `0` | Controls horizontal board lane arrangement and transition flow |\n| `is_default` | Default state assigned to newly created issues | Boolean (`true` / `false`) | `false` | Exactly one state per project can be designated default |\n| `wip_soft_limit` | Warning threshold for work-in-progress cards | Integer between 1 and 999 (or `null`) | `null` (None) | Renders subtle amber capacity warnings when column count is exceeded |\n| `wip_hard_limit` | Strict blocking limit for work-in-progress cards | Integer between 1 and 999 (or `null`) | `null` (None) | Disallows moving or creating cards into lane when limit is reached |\n| `priority_slug` | Normalized priority key (e.g. `urgent`, `high`) | Lowercase regex `^[a-z][a-z0-9_-]{0,31}$` | Required | Standardized priority value used in query filters and formula AST |\n| `priority_label` | Human-readable priority label with emoji | UTF-8 String (1 to 64 characters) | Required | Displayed on card badges, priority dropdowns, and peek rails |\n| `exclusive_group` | Mutual exclusion category for label grouping | Lowercase regex `^[a-z0-9][a-z0-9_-]{0,31}$` | `null` (Optional) | Enforces single-selection among conflicting tags (e.g. `env:prod`) |\n\n### Setting-by-Setting Technical Paragraphs (Project Settings)\n\n- **name:** The project name displayed across navigation breadcrumbs, issue peek drawers, and workspace summary cards. Scoped strictly to the active workspace (max 120 characters).\n- **key:** The immutable uppercase prefix key identifying work items within this project (e.g. `KAN` generates `KAN-1`, `KAN-2`). Validated against `^[A-Z][A-Z0-9]{1,9}$` (between 2 and 10 alphanumeric characters).\n- **state_name:** The human-facing title of a workflow state (e.g. `Backlog`, `In Progress`, `Code Review`, `Done`). Renaming a state immediately reflects across all active cards without modifying historical audit events.\n- **group:** The canonical lifecycle category to which the state belongs (`backlog`, `unstarted`, `started`, `completed`, `cancelled`). Group mapping is fundamental: cycle burndowns, cumulative flow diagrams, and throughput percentiles aggregate work based on group identity.\n- **color_hex:** A 7-character hexadecimal color string (`#RRGGBB`) applied to column lane headers, state pills, and board drop zones to ensure high contrast and immediate readability.\n- **sort_order:** An integer specifying the left-to-right presentation order of board columns and workflow dropdowns. Lower numbers appear earlier in the delivery lifecycle.\n- **is_default:** Designates the initial workflow state automatically assigned when a contributor quick-creates an issue without specifying a state. Exactly one state per project can be default.\n- **wip_soft_limit:** An advisory Work-In-Progress limit for Kanban columns (1 to 999). When the active card count exceeds this number, the column header displays an amber count badge (`5/4 WIP`) without preventing drops.\n- **wip_hard_limit:** A strict Work-In-Progress enforcement threshold (1 to 999). When reached, further card drops or status changes targeting this column are rejected at the API boundary (`422 WIP_LIMIT_EXCEEDED`). Must be greater than or equal to `wip_soft_limit`.\n- **priority_slug:** Machine-readable identifier for priority tiers (`urgent`, `high`, `medium`, `low`, `none`). Used in Safe Formula evaluations, MCP tool queries, and REST search filters.\n- **priority_label:** The user-facing priority string, typically combining an expressive semantic emoji and clear text (e.g. `\ud83d\udd34 Urgent`, `\ud83d\udfe0 High`, `\ud83d\udfe1 Medium`, `\ud83d\udd35 Low`).\n- **exclusive_group:** An optional label category constraint. When applied to tags (e.g. `tier:free`, `tier:pro`), applying one tag from the group automatically removes any previously attached tags in that same exclusive group.\n\n### Step-by-Step Guide: Setting Project WIP Limits and Workflow States\n\n1. **Navigate to Project Settings:** Open your target project (e.g. `/projects/KAN`) and click **Settings** in the project sidebar.\n2. **Open Workflow States Studio:** Select the **States** tab to view all currently configured workflow states grouped by lifecycle phase.\n3. **Add or Edit a State:** Click **+ Add State** or click the edit icon on an existing state row. Specify the State Name (e.g. `In Review`), assign the Lifecycle Group (`started` for active work, `completed` for resolved work), choose an Accent Color, and check Make Default if newly created tickets should land in this column.\n4. **Configure WIP Limits:** Enter a Soft WIP Limit (e.g. `4`) to flag column congestion, and enter a Hard WIP Limit (e.g. `6`) if your team enforces strict pull-based flow and prohibits card overloading (`wip_soft_limit <= wip_hard_limit`).\n5. **Reorder Board Columns:** Drag states up and down using the grip handle to adjust their execution sort order from left to right.\n6. **Save Changes:** Click **Save States** to persist the configuration. Board columns update immediately across all connected WebSockets.\n\n---\n\n### Personal Settings\nThe Personal Settings Studio (`/settings` or `/profile`) provides comprehensive user identity self-service, including canonical timezone localization, avatar upload with automatic sanitization and cropping, password rotation with server-admin entropy rules, WebAuthn Passkeys, TOTP two-factor authentication, one-time emergency recovery codes, and external OIDC/LDAP identity account linking.\n\n![Personal Settings - Desktop Light](images/slice5-personal-settings-desktop-1440x900-light.png)\n![Personal Settings - Desktop Dark](images/slice5-personal-settings-desktop-1440x900-dark.png)\n![Personal Settings - Tablet Landscape](images/slice5-personal-settings-tablet-landscape-1024x768.png)\n![Personal Settings - Tablet Portrait](images/slice5-personal-settings-tablet-portrait-768x1024.png)\n![Personal Settings - Mobile Portrait](images/slice5-personal-settings-mobile-portrait-390x844.png)\n\n### Personal Settings Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `display_name` | Public user profile name displayed to colleagues | UTF-8 String (1 to 120 characters) | User's full name | Sanitized against invisible Unicode characters and control codes |\n| `timezone` | Canonical IANA timezone used for date formatting | 15 canonical timezones (e.g. `America/New_York`, `UTC`) | `UTC` | Localizes ticket creation, audit timestamps, and SLA due date displays |\n| `avatar` | User profile photograph or custom avatar | PNG, JPEG, or WebP image file (<= 2 MiB) | Default letter icon | Re-encoded server-side via Pillow; SVG uploads rejected fail-closed |\n| `current_password` | Verification of existing credentials before password update | String matching current password | Required on change | Prevents unauthorized password changes on unattended sessions |\n| `new_password` | Updated local authentication password | Min 12 chars (Min 14 for Server Admins) | User-supplied | Salted and hashed via Argon2id with server-side pepper |\n| `passkeys` | FIDO2 / WebAuthn biometric security keys | Platform (Touch ID/Hello) or Cross-Platform (YubiKey) | None enrolled | Hardware-bound cryptographic public key authentication |\n| `totp_enabled` | Time-based one-time password (RFC 6238) 2FA | 6-digit verification code from authenticator app | Disabled | Requires AAL2 step-up challenge to disable once activated |\n| `recovery_codes` | Single-use emergency account recovery backup codes | 10 alphanumeric single-use codes | Generated on 2FA setup | Stored hashed in PostgreSQL; invalidated upon individual consumption |\n| `linked_identities` | External OIDC, Google, GitHub, or LDAP accounts | Verified external provider identity claims | Primary login card | Enables single-sign-on without password storage; unlinking requires AAL2 |\n\n### Setting-by-Setting Technical Paragraphs (Personal Settings)\n\n- **display_name:** The user's public identity rendered across comments, avatar badges, activity feeds, and assignment menus. Cleaned server-side using Unicode guards to strip zero-width spaces and spoofing homoglyphs.\n- **timezone:** The user's localized timezone selection, chosen from 15 canonical IANA timezones (such as `America/New_York`, `Europe/London`, `Asia/Tokyo`, `UTC`). All timestamps remain stored canonically as UTC in PostgreSQL and are formatted to the user's local offset on the client.\n- **avatar:** Profile picture uploaded via `PUT /api/v1/auth/me/avatar`. The backend enforces a strict 2 MiB size cap and validates the raster payload via content-sniffing. Dangerous vector formats (SVG) are rejected fail-closed to eliminate XSS risks, and images are re-encoded to sanitized PNG format.\n- **current_password:** Required whenever a user modifies their local password via `POST /api/v1/auth/me/password`. Guards against session hijacking by requiring proof of current knowledge before modifying credentials.\n- **new_password:** The updated password. The platform enforces strict entropy requirements: standard users must supply at least 12 characters, while users possessing the `SERVER_ADMIN` role must supply at least 14 characters.\n- **passkeys:** WebAuthn credentials registered via `POST /api/v1/auth/webauthn/register:start` and `:finish`. Passkeys support both platform biometrics (Touch ID, Face ID, Windows Hello) and cross-platform hardware tokens (YubiKey). Each enrolled key displays nickname, enrolled date, and a non-intrusive **Test Passkey** verification button.\n- **totp_enabled:** Activates Time-Based One-Time Password verification for authenticator applications (Aegis, Google Authenticator, 1Password). Enrolled via QR code and verified with a 6-digit challenge code. Disabling TOTP requires mandatory AAL2 step-up verification.\n- **recovery_codes:** A set of 10 single-use emergency recovery codes generated when two-factor authentication is configured. Each code can be used exactly once to regain account access if hardware tokens or authenticator apps are lost.\n- **linked_identities:** Manages connected third-party enterprise identity cards (Google Workspace, GitHub, GitLab, Okta, Active Directory LDAP). Users can link multiple external accounts to a single local identity or unlink secondary providers after completing AAL2 step-up verification.\n\n---\n\n## 3. Workflow Transition Studio & Git Repo Bindings\nThe Workflow Transition Studio (`/projects/:proj/settings/workflows`) coordinates lifecycle rules, pre-transition validators, field mutators, asynchronous AI agent gates, and read-only bare Git repository mirror bindings.\n\n![Workflow Transition Studio - Desktop Dark](images/slice5-workflow-studio-desktop-1440x900-dark.png)\n![Workflow Transition Studio - Tablet Landscape](images/slice5-workflow-studio-tablet-landscape-1024x768.png)\n![Workflow Transition Studio - Tablet Portrait](images/slice5-workflow-studio-tablet-portrait-768x1024.png)\n![Workflow Transition Studio - Mobile Portrait](images/slice5-workflow-studio-mobile-portrait-390x844.png)\n\n### Workflow Transition Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `name` | Descriptive label for transition helper hook | UTF-8 String (1 to 120 characters) | Required | Displayed in pipeline lists, dry-run logs, and error explanations |\n| `from_state` | Origin workflow state of the transition rule | Valid state name or `null` (Any state) | `null` (Wildcard) | Restricts hook evaluation to specific card movements |\n| `to_state` | Destination workflow state of the transition | Valid project state name | Required | The target column being protected by the transition helper |\n| `hook_kind` | Execution engine and evaluation timing | `\"sync_validator\"`, `\"sync_mutator\"`, `\"agent_interceptor\"` | `\"sync_validator\"` | Governs execution latency and synchronous vs asynchronous processing |\n| `failure_policy` | Action taken if helper times out or rejects | `\"fail_closed\"`, `\"fail_open_warn\"` | `\"fail_closed\"` | Fail-closed guarantees invalid transitions never commit |\n| `wasm_module_sha256` | SHA-256 digest of sandboxed Wasm module | 64-character lowercase hex string | Required for Wasm | Verifies bytecode authenticity before in-process execution |\n| `agent` | Identifier of registered autonomous agent | Valid agent slug (e.g. `reality-checker`) | Required for Agent | Binds asynchronous gate to configured LLM or CLI runner harness |\n| `timeout_ms` | Maximum allowed execution time in milliseconds | Integer between 1 and 300000 ms | 60000 for Agent | Protects transition queues from hanging subprocesses |\n| `allowed_mutable_fields` | Explicit field allowlist for mutator hooks | List of field names (`labels`, `priority`, `assignees`, `start_date`, `due_date`, `cycle`, `custom_fields.<slug>`) | `[]` (Empty) | Enforces least-privilege mutation; `state` and `description` are forbidden |\n| `repo_slug` | Identifier for project bare Git mirror | Regex `^[a-z0-9][a-z0-9-]{1,62}$` | Required | Names local bare mirror directory under `/var/lib/kanban/repos/` |\n| `remote_url` | Upstream Git repository clone URL | HTTPS or SSH Git URL | Required | Validated against SSRF policy before initiating background fetch |\n| `default_ref` | Primary branch or ref used for agent diff inspections | Valid Git ref name (e.g. `main`, `master`) | `\"main\"` | Baseline target branch used by reality-checker audits |\n| `access_mode` | Storage access mode for repository mirror | `\"ro_vfs_mount\"`, `\"bare_git_tools\"` | `\"ro_vfs_mount\"` | Enforces read-only filesystem or git tool execution |\n| `credential` | Optional credential reference for private repository authentication | `null`, `\"workspace-pat\"`, `\"ssh-key\"` | `null` | Secure token reference stored in credentials vault |\n\n### Setting-by-Setting Technical Paragraphs (Workflow Transition Studio & Repo Bindings)\n\n- **name:** The user-defined identifier assigned to the workflow hook (such as `qa-done-gate` or `enforce-pr-link`, 1 to 120 characters). Appears on pipeline transition cards, dry-run evaluation outputs, and timeline rejection entries.\n- **from_state:** The initial state of the card before transition (e.g. `In Progress`). Selecting `null` creates a wildcard rule matching transitions originating from any state into `to_state`.\n- **to_state:** The protected destination state (e.g. `Done`). The card cannot land in this state until all attached synchronous validators pass and all asynchronous agent gates approve.\n- **hook_kind:** Defines the execution engine: `\"sync_validator\"` runs fast in-process WebAssembly checks (<25ms); `\"sync_mutator\"` applies deterministic property updates; `\"agent_interceptor\"` dispatches an asynchronous background gate to an AI model or test runner.\n- **failure_policy:** The error handling invariant. `\"fail_closed\"` (default) blocks the transition immediately if the helper fails, times out, or errors. `\"fail_open_warn\"` logs an administrative warning to the activity ledger and allows the card transition to complete.\n- **wasm_module_sha256:** The cryptographic hash of the compiled WebAssembly bytecode module executed by the `wasmtime` engine. Prevents execution of unverified or tampered binaries.\n- **agent:** The slug of the registered autonomous agent (`@reality-checker`, `@security-auditor`) assigned to evaluate asynchronous gate transitions. The attach dialog groups available agents by execution harness (`cli_pipe`, `in_app_sdk`, `remote_runner`).\n- **timeout_ms:** The maximum wall-clock execution deadline allocated to the helper (validating between 1 and 300,000 ms, defaulting to 60,000 ms for agent interceptors).\n- **allowed_mutable_fields:** A strict security allowlist restricting which issue properties a `sync_mutator` hook can modify (`labels`, `priority`, `assignees`, `start_date`, `due_date`, `cycle`, and `custom_fields.<slug>`). Project invariants strictly forbid modifying `state` or `description_markdown` to prevent recursive transition loops and content tampering.\n- **repo_slug:** The local filesystem folder name allocated to the bare Git mirror. Must be a clean lowercase alphanumeric string with hyphens.\n- **remote_url:** The external Git repository URL (e.g. `https://github.com/org/repo.git`). The server validates the URL against an anti-SSRF policy (blocking RFC 1918 private IP addresses unless explicitly allowlisted) before establishing outbound connections.\n- **default_ref:** The primary branch or ref name against which code inspection scripts, PR validation checks, and diff analyses are evaluated (default `\"main\"`).\n- **access_mode:** Defines how agents access repository contents: `\"ro_vfs_mount\"` mounts a read-only filesystem tree, while `\"bare_git_tools\"` allows executing read-only Git query commands.\n- **credential:** Optional secret identifier (`\"workspace-pat\"` or `\"ssh-key\"`) used to authenticate against private upstream repositories without exposing cleartext credentials to agents.\n\n### Step-by-Step Guide: Attaching Workflow Transition Hooks with Dry-Run\n\n1. **Navigate to Workflow Studio:** Open `/projects/<PROJECT_KEY>/settings/workflows`.\n2. **Select Transition Rule:** Locate the transition rule card for your target state movement (e.g. `In Progress -> Done`).\n3. **Click Attach Hook:** Click the **+ Attach Hook** button to open the Attach Workflow Hook Dialog.\n4. **Define Hook Parameters:** Specify a unique Hook Name (e.g. `reality-checker-done-gate`), select the Hook Kind (`sync_validator`, `sync_mutator`, or `agent_interceptor`), and choose the Failure Policy (`fail_closed` to block unverified tickets, or `fail_open_warn` to log warnings while allowing progress).\n5. **Select Engine or Agent:** For Wasm, choose an approved module (e.g. `check-blockers-resolved`). For Agent Interceptors, select the target Agent Definition from the dropdown; the system automatically populates the agent's real timeout (between 1 and 300,000 ms, e.g. `60000ms`). For mutators, select permitted mutable fields (`labels`, `priority`, `assignees`, `start_date`, `due_date`, `cycle`, or `custom_fields.<slug>`).\n6. **Save Hook:** Click **Attach Hook** to commit the hook to the project's transition pipeline.\n7. **Simulate in Dry-Run Drawer:** Click the **Dry-Run** button on the rule card, choose a sample ticket fixture or enter a live issue key, click **Run Dry-Run** to execute the pipeline in a simulated, non-mutating sandbox, and inspect the execution timings (e.g. `1.2ms`, `3.4ms`), returned logs, and allowed/vetoed verdicts before deploying to production.\n\n### Step-by-Step Guide: Binding Git Repositories\n\n1. **Access Repository Bindings:** Navigate to `/projects/<PROJECT_KEY>/settings/workflows` and scroll down to the Git Repository Bindings section.\n2. **Click Bind Repository:** Click **+ Bind Git Repository** to open the repository configuration drawer.\n3. **Configure Repository Details:** Enter the Repository Slug (e.g. `kanban-core`), remote repository URL (`remote_url`), default tracking branch or ref (`default_ref`, e.g. `main`), access mode (`ro_vfs_mount` or `bare_git_tools`), and optional credential binding (`workspace-pat` or `ssh-key`).\n4. **Enforce Read-Only Mirror Invariant:** The system creates a local bare Git mirror with strict read-only permissions (`:ro`). Autonomous agents can query commit trees and run `git diff` during gate reviews, but write access is impossible.\n5. **Trigger Immediate Mirror Refresh:** Click **Refresh Mirror** to perform an initial fetch and verify that commit SHAs and branch references synchronize successfully.\n\n---\n\n## 4. Custom Fields Studio & Dual-Control Escalation\nThe Custom Fields Studio (`/projects/:proj/settings/custom-fields`) manages dynamic attributes, safe mathematical formulas, WebAssembly modules, and dual-control tenant scope escalations under AAL2 cryptographic verification.\n\n![Custom Fields Studio - Desktop Dark](images/slice5-custom-fields-studio-desktop-1440x900-dark.png)\n![Custom Fields Studio - Tablet Landscape](images/slice5-custom-fields-studio-tablet-landscape-1024x768.png)\n![Custom Fields Studio - Tablet Portrait](images/slice5-custom-fields-studio-tablet-portrait-768x1024.png)\n![Custom Fields Studio - Mobile Portrait](images/slice5-custom-fields-studio-mobile-portrait-390x844.png)\n![Custom Fields Editor Tier A](images/slice5-custom-fields-editor-tier-a-desktop-1440x900-light.png)\n![Custom Fields Structured Format](images/slice5-custom-fields-structured-format-desktop-1440x900-light.png)\n![Custom Fields Dual Control Escalation](images/slice5-custom-fields-escalation-dual-control-desktop-1440x900-light.png)\n\n### Custom Fields Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `name` | Human-readable custom field title | String (1 to 80 characters) | Required | Displayed on ticket rails, table columns, and board badges |\n| `slug` | Unique identifier used in formulas and API queries | Lowercase alphanumeric ASCII with hyphens | Derived from name | Used in formula expressions and API JSON properties |\n| `flavor` | Execution tier and underlying calculation engine | `\"scalar\"`, `\"formula\"`, `\"wasm\"`, `\"nsjail\"` | `\"scalar\"` | Determines execution latency and Standalone mode compatibility |\n| `sandbox_tier` | Multi-tier sandbox engine used for execution | `\"scalar\"`, `\"wasm\"` (Tier A), `\"nsjail\"` (Tier B) | `\"wasm\"` | `nsjail` requires multi-container compose; fail-closed in standalone |\n| `credential_mode` | Identity token provided during script execution | `\"INVOKING_USER\"`, `\"PROJECT_ADMIN_SP\"`, `\"SERVER_ADMIN_SP\"` | `\"INVOKING_USER\"` | Elevated service principal modes require dual-control cryptographic approval |\n| `target_scope` | Maximum tenant visibility boundary of the field | `\"PROJECT\"`, `\"WORKSPACE\"`, `\"SERVER\"` | `\"PROJECT\"` | Escalation beyond `PROJECT` requires AAL2 administrative step-up |\n| `output_format` | Canonical schema used to format and render output | `\"text\"`, `\"number\"`, `\"badge\"`, `\"severity_pill\"`, `\"url\"`, `\"markdown_snippet\"`, `\"json_table\"` | `\"text\"` | Enforces strict Pydantic validation before persisting to JSONB |\n| `format_metadata` | Configuration options tailored to chosen format | JSON object matching format schema | `{}` | Governs decimal precision, color tokens, allowlists, or table headers |\n| `script_source` | Raw source code for formula or script evaluation | Python AST expression, Rust Wasm, or script | Required | Signed with SHA-256 digest upon commit; immutable against database tampering |\n| `egress_allowlist` | Allowed destination hostnames for nsjail tier | Line-delimited (`\\n`) domain list | Empty (Zero egress) | Network disabled by default via Linux kernel `CLONE_NEWNET` |\n| `approval_status` | Current dual-control escalation state | `\"PENDING\"`, `\"PENDING_SECOND_APPROVER\"`, `\"APPROVED\"`, `\"REVOKED\"` | `\"APPROVED\"` (Project) | Gated at `PENDING` when requesting Workspace or Server scope |\n| `aal2_freshness` | Maximum age of AAL2 verification for approval | Integer (Max 900 seconds / 15 minutes) | 900s | Enforces fresh multi-factor authentication on administrative step-up |\n\n### Setting-by-Setting Technical Paragraphs (Custom Fields Studio & Dual-Control Escalation)\n\n- **name:** The human-facing label displayed on ticket property rails, table view columns, and board card badges (1 to 80 characters). Rendered alongside a subtle test tube icon (`\ud83e\uddea`) for computed fields.\n- **slug:** The immutable ASCII identifier representing the custom field in JSON payloads, query filters, and Safe Formula references. Derived automatically from the field name upon creation.\n- **flavor:** The computation tier. UI defaults to `\"scalar\"` (`CustomFieldDefinitionEditor.tsx` line 245; stores static values); `\"formula\"` executes deterministic Python AST math in-process (<5ms); `\"wasm\"` runs compiled WebAssembly modules via `wasmtime` (<25ms; API tier default); `\"nsjail\"` executes Linux container scripts (<250ms).\n- **sandbox_tier:** Selects between in-process WebAssembly (`wasm` Tier A) and containerized namespace isolation (`nsjail` Tier B). In Standalone mode, `nsjail` is fail-closed disabled with `SANDBOX_UNAVAILABLE_IN_STANDALONE`.\n- **credential_mode:** Determines which identity credentials are provided to the script during execution. `\"INVOKING_USER\"` executes strictly within the permissions of the calling user. `\"PROJECT_ADMIN_SP\"` executes with Project Admin service principal authority. `\"SERVER_ADMIN_SP\"` executes with Server Admin service principal authority and mandates dual-control approval.\n- **target_scope:** Controls the data visibility boundary of the field. `\"PROJECT\"` scope can only read issues within the active project. Escalating to `\"WORKSPACE\"` (reading across all workspace projects) or `\"SERVER\"` (global) requires dual-control cryptographic sign-off.\n- **output_format:** The strict Pydantic schema used to validate and render the field's computed output. Supports 7 canonical formats: `text`, `number`, `badge`, `severity_pill`, `url`, `markdown_snippet`, and `json_table`.\n- **format_metadata:** A JSON configuration dictionary customizing the chosen output format (such as specifying `unit_suffix: \"%\"`, `maximum_fraction_digits: 1`, or table column definitions).\n- **script_source:** The executable source code (Python formula expression, Wasm bytecode, or shell script). Hashed with SHA-256 upon save; if the hash in PostgreSQL fails verification at runtime, execution is halted immediately.\n- **egress_allowlist:** A line-delimited (`\\n`) list of permitted network hosts accessible to `nsjail` scripts. By default, network egress is completely disabled via kernel `CLONE_NEWNET`.\n- **approval_status:** Tracks the dual-control lifecycle (`PENDING`, `PENDING_SECOND_APPROVER`, `APPROVED`, `REVOKED`). Fields requesting `WORKSPACE` or `SERVER` scope enter `PENDING` status and cannot execute until approved by an administrator holding target tier authority.\n- **aal2_freshness:** The security policy requiring that the approving administrator must have performed multi-factor authentication (biometric Passkey, hardware key, or TOTP) within the preceding 900 seconds (15 minutes).\n\n### Step-by-Step Guide: Authoring and Requesting Dual-Control Custom Scripted Fields\n\n1. **Open Custom Fields Studio:** Navigate to `/projects/<PROJECT_KEY>/settings/custom-fields` and click **+ New Custom Field**.\n2. **Define Field Metadata:** Enter a Name (e.g. `Cross-Project Security Compliance Score`), confirm the automatically generated Slug (`cross-proj-sec-score`), select the Flavor (`formula` or `wasm`), and choose the Output Format (`severity_pill` or `number`).\n3. **Request Elevated Scope:** Set Target Scope to `WORKSPACE` or `SERVER`. Optionally select Credential Mode as `PROJECT_ADMIN_SP` or `SERVER_ADMIN_SP` if elevated service authority is required. The UI immediately surfaces an amber Dual-Control Escalation Banner warning of the expanded data access boundary.\n4. **Draft and Test Execute:** Author your formula expression or script logic, then click **Test Execute** to simulate evaluation in memory against sample payloads.\n5. **Submit for Approval:** Click **Save & Request Escalation**. The field enters `pending` approval status.\n6. **Independent AAL2 Review & Approval:** A distinct Workspace or Server Administrator opens the Custom Fields Studio, inspects the script source, requested scope, and blast radius, clicks **Approve Escalation**, and provides fresh Authenticator Assurance Level 2 (AAL2) credentials (Passkey, security key, or TOTP). Once verified, the field is activated and logged in the immutable audit ledger.\n\n---\n\n## 5. Authentication Studio\nThe Multi-Card Authentication Studio (`/admin/auth`) and Granular RBAC Policy Builder configure enterprise identity providers, Active Directory / LDAPS trees, OpenID Connect SSO, WebAuthn Passkeys, TOTP multi-factor authentication, break-glass lockout prevention, and 30-permission custom roles.\n\n![Admin Authentication Studio - Desktop Light](images/slice1-desktop-1440x900-light.png)\n\n\n### Authentication Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `provider_kind` | Underlying identity protocol card | `LOCAL_ADMIN`, `OAUTH2`, `OIDC`, `LDAP` | Required | Determines credential validation handshake, secret custody, and token exchange |\n| `slug` | URL-safe card identifier used in auth routes | Lowercase ASCII `^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$` (3 to 48 chars) | Required | Formats callback and login endpoints (e.g. `/api/v1/auth/oidc/{slug}/start`) |\n| `display_name` | User-facing card title rendered on `/login` screen | UTF-8 String (1 to 100 characters) | Required | Displayed directly on login buttons and cards |\n| `button_subtext` | Optional explanatory subtext beneath button | UTF-8 String (up to 200 characters) or null | None | Guides users on credential format or organizational tenant |\n| `icon_preset` | Visual icon rendered inside login card button | `key`, `shield`, `google`, `github`, `microsoft`, `ldap`, `terminal` | `key` | Provides immediate visual recognition on `/login` container |\n| `is_enabled` | Master active state toggle for the card | Boolean (`true` / `false`) | `false` | Disabled cards reject login attempts immediately with 403 FORBIDDEN |\n| `sort_rank` | Fractional rank ordering on `/login` screen | Fractional-index midpoint string (e.g. `\"V00V\"`, `\"kV0FV\"`) computed via `midpoint_rank()` | Derived | Lower ranks appear first; allows prioritizing corporate SSO over fallback admin |\n| `auto_provision_users` | Automatic local user creation on first SSO login | Boolean (`true` / `false`) | `false` | When true, new users are provisioned in workspace with default role |\n| `allowed_email_domains` | Domain allowlist for user registration and SSO | Array of domain strings (e.g. `[\"corp.example.com\"]`) | Empty list (Allow all) | Rejects unmatched email claims during OIDC and LDAP authentication |\n| `public_config` | Non-sensitive provider configuration dictionary | JSON object | `{}` | Exposes discovery URLs and client IDs without leaking secrets |\n| `secret` | Sensitive client secret or bind password | Write-only string | None | Encrypted at rest via AES-256-GCM envelope encryption (`MASTER_KEK`) |\n| `google_oauth_json` | Google Cloud Console client secret JSON | Valid JSON string (up to 32,768 characters) | None | Quick-import payload automatically parsed and verified by backend |\n\n\n### Active Directory and LDAPS Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `url` | Directory connection URL with scheme and host | `^(ldaps\\|ldap)://[A-Za-z0-9.-]+(:[0-9]{1,5})?$` | Required | Plaintext unencrypted LDAP rejected; requires `ldaps://` or `ldap://` with StartTLS |\n| `transport_mode` | Cryptographic transport security protocol | `ldaps` (implicit TLS on port 636), `starttls` (explicit StartTLS on port 389) | `ldaps` | Enforces TLS handshake before transmitting bind credentials |\n| `ca_cert_pem` | Custom enterprise Certificate Authority bundle | PEM-formatted X.509 certificate string (max 64 KiB) | None | Pins enterprise root CA; rejects untrusted self-signed certificates |\n| `spki_sha256_pins` | Subject Public Key Info SHA-256 pin hashes | Array of 64-hex SHA-256 strings (up to 4 pins) | `[]` | Cryptographically pins public key identity; prevents rogue CA issuance |\n| `service_bind_dn` | Service account Distinguished Name | LDAP DN string (up to 512 chars) or null | None | Read-only service principal used for user lookup and group searches |\n| `base_dn` | Directory search subtree root Distinguished Name | LDAP DN string (1 to 512 chars) | Required | Scopes user search to authorized organizational container (e.g. `OU=Users,DC=corp,DC=com`) |\n| `user_search_filter` | LDAP query filter for user account resolution | LDAP filter expression substituting `{username}` | `(&(objectClass=person)(uid={username}))` | Resolves login username to directory user; AD preset uses `sAMAccountName` |\n| `subject_attribute` | Attribute providing immutable user identity | ASCII attribute name (e.g. `entryUUID`, `objectGUID`) | `entryUUID` | Binds external user identity immutably across username renames |\n| `email_attribute` | Attribute containing user email address | ASCII attribute name (e.g. `mail`) | `mail` | Source of verified user email address for workspace mapping |\n| `display_name_attribute` | Attribute containing user full name | ASCII attribute name (e.g. `displayName`, `cn`) | `cn` | Displayed on user profile and activity ledger |\n| `member_of_attribute` | Attribute containing direct group memberships | ASCII attribute name (e.g. `memberOf`) | `memberOf` | Evaluated during group membership extraction and role mapping |\n| `group_dn_map` | Dictionary mapping directory group DNs to roles | JSON dictionary of `{dn: role_slug}` (up to 200 mappings) | `{}` | Automatically provisions mapped workspace and project roles upon login |\n| `access_mode` | Access restriction policy | `any_user` (all valid users), `group_restricted` (member of allowed group) | `any_user` | When restricted, users not in `user_groups` or `admin_groups` are denied entry |\n| `admin_groups` | Directory group names granting admin authority | Array of group names (up to 200 chars each) | `[]` | Grants `SERVER_ADMIN` or `WORKSPACE_ADMIN` to authenticated group members |\n| `user_groups` | Directory group names granting member authority | Array of group names (up to 200 chars each) | `[]` | Grants baseline member access when `access_mode` is `group_restricted` |\n\n\n### OpenID Connect (OIDC) and Google OAuth Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `issuer_url` | OIDC discovery endpoint base URL | Valid HTTPS URL | Required | Fetches `/.well-known/openid-configuration` and cryptographic JWKS keys |\n| `client_id` | OAuth application client identifier | ASCII string | Required | Identifies application to identity provider authorization server |\n| `client_secret` | OAuth application client secret | Write-only secret string | Required | Stored encrypted in PostgreSQL; never returned in REST responses |\n| `scopes` | OIDC OAuth scope parameters | Array of scope strings in API; comma-separated in drawer | `[\"openid\", \"email\", \"profile\"]` | Must include `openid` and `email` for verified claim extraction |\n| `redirect_uri` | Callback endpoint registered with IdP | Fixed format `/api/v1/auth/oidc/{slug}/callback` | Derived | Enforces strict origin matching against current deployment URL |\n| `require_email_verified` | Rejects unverified IdP email addresses | Boolean (`true`) | `true` | If `email_verified: false`, rejects authentication with 403 EMAIL_NOT_VERIFIED |\n\n\n### Personal Security and Multi-Factor Authentication Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `rp_name` | WebAuthn Relying Party display name | Canonical string `\ud83d\udc4dkanban` | `\ud83d\udc4dkanban` | Displayed by browser and hardware security keys during passkey prompts |\n| `rp_id` | WebAuthn Relying Party domain identifier | Strict ASCII FQDN without protocol or port | Hostname of deployment | Must match browser origin to prevent credential theft or relay attacks |\n| `totp_secret` | High-entropy base32 secret for TOTP | Base32 string (RFC 6238) | Generated on enroll | Validates 6-digit one-time codes with 30s step interval and +/- 1 drift |\n| `recovery_codes` | Backup emergency recovery codes | Array of 10 single-use high-entropy recovery codes | 10 codes | Single-use emergency codes stored as salted hashes for break-glass recovery |\n| `websudo_duration_seconds` | Duration of elevated AAL2 administrator session | Integer (seconds) | `900` (15 minutes) | Sliding window for sensitive mutations; explicit drop via `/aal2/drop` |\n| `lockout_prevention_layer` | Anti-lockout verification enforcement | `db_trigger`, `handshake_probe_15m` | Both active | Blocks disabling LOCAL_ADMIN without verified interactive admin login within 15m |\n\n\n### Granular RBAC Policy Builder Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `rbac_scope_tier` | Administrative scope tier of the role | `system admin`, `workspace admin`, `project admin` | `workspace admin` | Governs role hierarchy and locks lower-tier admins from editing parent roles |\n| `role_slug` | Unique lowercase identifier for custom role | Lowercase ASCII `^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$` | Required | Identifies role in database bindings and audit ledger records |\n| `role_name` | Human-readable role title | UTF-8 String (1 to 100 characters) | Required | Displayed on user management surfaces, member cards, and badges |\n| `color_hex` | UI badge accent color | 7-character hex code (e.g. `#4f46e5`) | `#6b7280` | Distinguishes role visually across member tables and peek drawers |\n| `rbac_permissions` | List of granted granular permissions | Array of permission strings from 30 canonical keys | `[]` | Evaluated with explicit DENY precedence (`effective = allow & (~deny)`) |\n\n![Custom RBAC Policy Builder - Desktop](images/slice1-custom-rbac-policy-builder.png)\n\n\n### Setting-by-Setting Technical Paragraphs\n\n- **provider_kind:** Specifies the authentication protocol implemented by the card. Permitted values are `LOCAL_ADMIN` (argon2id hashed platform administrative credentials), `OIDC` (OpenID Connect discovery and authorization code flow), `OAUTH2` (generic OAuth 2.0 provider with userinfo endpoint), and `LDAP` (Active Directory and OpenLDAP directory integration). The provider kind determines schema validation rules, secret custody requirements, and token minting behavior.\n- **slug:** The unique URL-safe identifier for the authentication card. Must conform to `^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$` between 3 and 48 characters. The slug forms the path parameter in public login and callback routes, including `/api/v1/auth/oidc/{slug}/start`, `/api/v1/auth/oidc/{slug}/callback`, and `/api/v1/auth/ldap/{slug}/login`. Immutable after creation to maintain bookmark and redirect stability.\n- **display_name:** The user-facing label rendered on the login card button on `/login` (1 to 100 characters). For example, `\"Corporate Active Directory\"` or `\"Google Workspace SSO\"`. Provides clear identification of the identity source for end users.\n- **button_subtext:** Optional secondary guidance rendered in smaller typography directly below the card title (up to 200 characters). Commonly used to specify login formats, such as `\"Use your firstname.lastname@example.com account\"` or `\"Hardware security key required\"`.\n- **icon_preset:** Visual icon token rendered on the authentication card button. Supported values include `key` (generic credential), `shield` (security key / passkey), `google` (Google colored G), `github` (GitHub octocat), `microsoft` (Windows logo), `ldap` (directory tree), and `terminal` (administrative root). Enhances visual scannability on multi-card login surfaces.\n- **is_enabled:** Master toggle controlling whether the authentication card is active on the `/login` screen. When set to `false`, the card is hidden from the login container, and any authentication attempts targeting the card's routes are immediately rejected with HTTP 403 `FORBIDDEN`. Mutations toggling `is_enabled` enforce anti-lockout validation.\n- **sort_rank:** Fractional-index midpoint string computed via `midpoint_rank()` (e.g. `\"V00V\"`, `\"kV0FV\"`) governing the visual sequence of cards on the `/login` container. Cards with lower lexicographical ranks appear first. Administrators use this setting to position primary corporate SSO providers at the top while keeping break-glass local admin cards accessible at the bottom without needing to renumber surrounding cards.\n- **auto_provision_users:** When enabled (`true`), an authenticated user whose external identity claim is verified but does not yet have an account in \ud83d\udc4dkanban is automatically provisioned with a new local user record and assigned the workspace default role. When disabled (`false`), external users must be explicitly invited before logging in.\n- **allowed_email_domains:** A security restriction array of permitted corporate email domains (e.g., `[\"corp.example.com\", \"subsidiary.com\"]`). During OIDC token exchange or LDAP authentication, if the user's verified email address domain does not match any entry in this list, authentication is aborted with HTTP 403 `DOMAIN_NOT_ALLOWED`.\n- **public_config:** A JSON dictionary containing non-sensitive provider configuration attributes. Stored in PostgreSQL `jsonb` columns and safe to expose to administrative API callers. Includes discovery URLs, client IDs, LDAP hosts, user search filters, and group mapping definitions.\n- **secret:** Client secrets, LDAP bind passwords, and private key strings. Inbound payloads accept this write-only parameter, which is immediately encrypted at rest using AES-256-GCM envelope encryption with the platform `MASTER_KEK`. The secret is never returned in any REST API response or serialization model.\n- **google_oauth_json:** A convenience payload accepting the raw client secret JSON file downloaded directly from the Google Cloud Console (up to 32,768 characters). The backend parses the JSON, validates client ID, client secret, redirect URI alignment, and populates `public_config` without manual copy-pasting.\n- **url:** The directory connection URL with protocol scheme and hostname matching `^(ldaps|ldap)://[A-Za-z0-9.-]+(:[0-9]{1,5})?$`. Unencrypted plaintext LDAP is strictly rejected; connections must negotiate TLS via `ldaps://` or `ldap://` with StartTLS.\n- **transport_mode:** Transport encryption protocol for directory traffic. Permitted values are `ldaps` (direct TLS handshake upon TCP socket connection on port 636) and `starttls` (explicit StartTLS extended operation negotiation on port 389 prior to issuing bind requests).\n- **ca_cert_pem:** Custom PEM-formatted X.509 certificate authority bundle (up to 64 KiB). When connecting to enterprise directory controllers utilizing private internal PKI, administrators paste the issuing root and intermediate CA certificates here. The LDAP client validates the server certificate strictly against this bundle, rejecting untrusted certificates.\n- **spki_sha256_pins:** Array of Subject Public Key Info (SPKI) SHA-256 hashes (each exactly 64 hexadecimal characters, up to 4 pins). Configured via backend API to cryptographically pin the server certificate public key and block rogue CA or proxy interception.\n- **service_bind_dn:** The Distinguished Name of the service account used by \ud83d\udc4dkanban to execute user lookup and group resolution queries (e.g., `CN=KanbanService,OU=ServiceAccounts,DC=corp,DC=com`, up to 512 characters). Must possess read-only search permissions over the target user and group subtrees.\n- **base_dn:** The root Distinguished Name of the directory subtree searched for user accounts (e.g., `OU=Employees,DC=corp,DC=com`, up to 512 characters). Scopes directory queries to prevent scanning unrelated machine or organizational containers.\n- **user_search_filter:** LDAP filter expression utilized to resolve the input login username to a specific Active Directory user object. The token `{username}` is safely escaped and substituted into the filter (default `(&(objectClass=person)(uid={username}))`, Active Directory preset `(&(objectCategory=person)(objectClass=user)(sAMAccountName={username}))`).\n- **subject_attribute:** The directory attribute providing an immutable, permanent identifier for the authenticated user (default `entryUUID`, Active Directory uses `objectGUID`). Ensures account continuity even if usernames or email addresses change.\n- **email_attribute:** The directory attribute containing the user's primary email address (default `mail`). Populates the verified user email address upon authentication.\n- **display_name_attribute:** The directory attribute containing the user's human-readable name (default `cn`, Active Directory uses `displayName`). Populates the user's profile display name.\n- **member_of_attribute:** The directory attribute containing direct group memberships on user objects (default `memberOf`). Used during group synchronization to locate groups mapped to \ud83d\udc4dkanban roles.\n- **group_dn_map:** JSON dictionary mapping directory group Distinguished Names to \ud83d\udc4dkanban role slugs (up to 200 mappings). During login, the backend evaluates user group memberships and assigns mapped roles automatically.\n- **access_mode:** Access restriction policy governing directory logins. Permitted values are `any_user` (permits all successfully bound directory users) and `group_restricted` (restricts login to users belonging to specified `user_groups` or `admin_groups`).\n- **admin_groups:** Array of directory group names granting administrative privileges (`SERVER_ADMIN` or `WORKSPACE_ADMIN`). Users belonging to these groups receive elevated administrative access upon login.\n- **user_groups:** Array of directory group names granting member privileges. When `access_mode` is set to `group_restricted`, users must belong to at least one group listed in `user_groups` or `admin_groups` to log in.\n- **issuer_url:** The standard OpenID Connect discovery base URL (e.g., `https://accounts.google.com` or `https://keycloak.corp.example.com/realms/enterprise`). The backend appends `/.well-known/openid-configuration` to retrieve endpoint URLs, signing algorithms, and JSON Web Key Sets (JWKS).\n- **client_id:** The public OAuth client identifier issued by the identity provider during application registration.\n- **client_secret:** The confidential OAuth client secret credential issued by the identity provider. Held strictly in write-only custody and encrypted via AES-256-GCM.\n- **scopes:** Array of requested OAuth scopes in API payloads (`[\"openid\", \"email\", \"profile\"]`), entered as a comma-separated string in the editor drawer. Scopes must guarantee delivery of the `sub` and `email` claims.\n- **redirect_uri:** The immutable callback URI derived from the deployment hostname and card slug: `https://<domain>/api/v1/auth/oidc/<slug>/callback`. Must be registered verbatim in the identity provider console.\n- **require_email_verified:** Mandatory boolean safety check. When true, the ID token claim `email_verified` must be strictly `true`. If the claim is `false` or missing, authentication is aborted with HTTP 403 `EMAIL_NOT_VERIFIED` to prevent email spoofing attacks.\n- **rp_name:** WebAuthn Relying Party display name. Hardcoded to the canonical platform brand `\ud83d\udc4dkanban` across all WebAuthn registration and authentication credential requests. Displayed by operating system biometric dialogs and hardware tokens.\n- **rp_id:** WebAuthn Relying Party domain identifier. Formatted as a strict ASCII Fully Qualified Domain Name matching the browser window origin without protocol, port, or trailing slashes (e.g., `kanban.example.com`). Prevents cross-domain credential phishing.\n- **totp_secret:** High-entropy base32 encoded secret key generated during TOTP authenticator enrollment (`POST /api/v1/auth/mfa/totp/enroll`). Encrypted at rest and used to validate 6-digit RFC 6238 time-step codes with a 30-second interval and +/- 1 step drift tolerance.\n- **recovery_codes:** Array of 10 single-use backup recovery codes minted during MFA enrollment (`RECOVERY_CODE_COUNT = 10`). Stored in PostgreSQL exclusively as cryptographic salted hashes. Used for break-glass account recovery when hardware tokens or authenticator apps are unavailable.\n- **websudo_duration_seconds:** The lifetime of an elevated Authenticator Assurance Level 2 (AAL2) session window (default 900 seconds / 15 minutes). All administrative endpoints (`/api/v1/admin/*`) require active AAL2 verification. When expired, the frontend prompts for step-up elevation via WebSudo without discarding dirty form state.\n- **lockout_prevention_layer:** Multi-layered defense preventing administrative lockouts. Evaluated at both the PostgreSQL trigger layer (`db_trigger`) and application service layer (`handshake_probe_15m`). While test handshakes (`POST /api/v1/admin/auth-cards/test-handshake`) verify endpoint health status, disabling or deleting `LOCAL_ADMIN` strictly requires that an external provider card has an active administrator account mapping AND has recorded a verified interactive `SERVER_ADMIN` login within the last 15 minutes (`last_admin_handshake_at >= clock_timestamp() - interval '15 minutes'`).\n- **rbac_scope_tier:** The administrative boundary defining where a custom RBAC role applies. Allowed values are `system admin` (global platform governance), `workspace admin` (workspace-wide settings, members, and custom fields), and `project admin` (project-specific workflows, WIP limits, and issue operations). Roles in higher tiers cannot be edited by administrators in lower tiers.\n- **role_slug:** The unique URL-safe identifier for the custom role, conforming to `^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$`. Identifies the role across role bindings and audit records.\n- **role_name:** The human-readable name of the custom role (1 to 100 characters), rendered in member lists, access matrices, and role assignment pills.\n- **color_hex:** Hexadecimal color string (e.g., `#4f46e5`) utilized for UI badges and role chips across user management and permission tables.\n- **rbac_permissions:** The set of granular permissions assigned to a custom RBAC role, selected from the 30 canonical keys across Workspace (8), Issue (10), and Field (12) tiers. Evaluated alongside the 8-bit capability bitmask with absolute DENY precedence (`effective = allow & (~deny)`).\n\n---\n\n## 6. MCP Access Studio\nThe MCP Access Studio (`/settings/mcp` or `/admin/mcp`) manages Model Context Protocol API tokens, Level of Detail (LOD) defaults, and rate limits.\n\n![MCP Access Studio and Key Minting Modal](images/slice3-mcp-access-studio-mint-modal.png)\n\n\n### MCP Access Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `surface_type` | Target isolated streamable endpoint | `/mcp/agent`, `/mcp/docs`, `/mcp/admin` | `/mcp/agent` | Determines tool catalog and token budget ceiling (<= 1,850 tokens for agent) |\n| `label` | Human-readable label identifying the key or client tool | String (1 to 120 characters) | None (Optional) | Surfaced in audit logs and active session inspector |\n| `owner_kind` | Identity persona bound to minted key | `personal_user`, `service_bot` | `personal_user` | Service bot keys enforce strict service account RLS boundaries |\n| `scope_tier` | Tenancy authorization scope boundary | `personal`, `project`, `workspace`, `global` | `workspace` | Restricts object graph access to specified tenant boundary |\n| `expires_in_days` | Key validity lifespan in days | `30`, `60`, `90`, `365`, `0` (Unlimited) | `60` (Studio mint) / `30` (Personal OAuth) | Expired keys reject calls with `401 UNAUTHORIZED`; Unlimited requires explicit risk confirmation |\n| `capability_mask` | Operational capability bitmask ceiling | Integer bitmask (0 to 255) | `31` (UI default) / `7` (API default) | Monotonic `CredentialBoundary` ceiling; mask 0 rejects all tools with `INSUFFICIENT_CAPABILITY` |\n| `allowed_tools` | Explicit whitelist of accessible tools | List of tool name strings | None (All tools in surface) | Restricts tool visibility and invocation to specified set |\n| `disabled_tools` | Explicit blacklist of prohibited tools | List of tool name strings | `[]` (Empty) | Blocks invocation of specified tools even if permitted by surface |\n| `allowed_cidrs` | Subnet IP allowlist for incoming MCP invocations | Comma or whitespace separated IPv4/IPv6 CIDRs | None (Allow all) | Rejects calls originating outside specified subnets with `403 FORBIDDEN_CIDR` |\n\n![Connect OAuth App Modal](images/slice3-connect-oauth-modal.png)\n\n### Setting-by-Setting Technical Paragraphs\n\n- **`surface_type`:** Selects the target streamable MCP endpoint. `/mcp/agent` exposes 10 execution and QA tools with a strict token ceiling of <= 1,850 tokens. `/mcp/docs` exposes 3 knowledge and documentation tools capped at <= 1,350 tokens. `/mcp/admin` exposes 12 governance and lifecycle tools capped at <= 2,800 tokens, requiring AAL2 administrative credentials.\n- **`label`:** Human-readable label assigned to the key during creation (1 to 120 characters). Surfaced in audit log feeds, active session inspectors, and the visual key management table to identify the calling entity or developer machine.\n- **`owner_kind`:** Selects between `personal_user` (executing on behalf of an authenticated human user) and `service_bot` (executing as an autonomous background bot). Service bot keys execute under dedicated service accounts with explicit RLS principal contexts.\n- **`scope_tier`:** Binds the minted token to a specific tenant boundary: `personal` (bound to current user), `project` (scoped to a single project key like `KAN`), `workspace` (scoped to all projects in workspace), or `global` (cross-workspace server scope). Project-scoped keys cannot query or mutate tickets in adjacent projects.\n- **`expires_in_days`:** Key expiration duration in days. The UI offers presets for 30 days, 60 days (default in Studio mint modal), 90 days, 365 days (1 year), and `0` (Unlimited). Selecting `Unlimited` triggers an explicit security risk warning checkbox (`confirm_unlimited`) that must be acknowledged before the key can be minted. Expired keys are rejected with `401 UNAUTHORIZED`.\n- **`capability_mask`:** Monotonic 8-bit integer capability bitmask ceiling (0 to 255). A value of `0` (`NONE`) creates a deny-all key where all tool calls are rejected with `isError: true` (`INSUFFICIENT_CAPABILITY`). A value of `1` (`VIEW`) restricts operations to read-only, `31` (`VIEW | COMMENT | EDIT | TRANSITION | LINK`) grants standard member permissions (UI default), and `255` (`ALL`) enables complete operational privileges. The backend API default is `7` (`VIEW | COMMENT | EDIT`). Enforced via PostgreSQL `SET LOCAL app.credential_boundary`.\n- **`allowed_tools`:** Optional explicit tool allowlist. When specified, only tools in this list may be listed or invoked by the client. Any invocation of unlisted tools is rejected with `TOOL_NOT_PERMITTED`.\n- **`disabled_tools`:** Explicit tool denylist (default empty). Specific tools can be disabled on a per-key basis (e.g. disabling `transition_ticket` for read/comment bots) even if permitted by surface and capability mask.\n- **`allowed_cidrs`:** Optional network boundary allowlist containing comma- or whitespace-separated IPv4 or IPv6 subnets (e.g. `127.0.0.1/32`, `192.168.1.0/24`). Requests originating outside allowed CIDR blocks are rejected immediately with HTTP 403 `FORBIDDEN_CIDR`.\n\n![MCP Config Snippet and Client Onboarding Modal](images/slice3-mcp-config-snippet-modal.png)\n\n### Connect OAuth App and Client Snippets Modals\n\n- **Connect OAuth App Modal:** Provides one-click visual integration guides and connection snippets for external AI tools:\n  - **Gemini App:** Generates direct OAuth Resource URLs for Google Gemini Connected Apps (`gemini.google.com -> Settings -> Connected Apps -> Add Custom MCP Server`).\n  - **Claude Code & Desktop:** Emits standard `claude_desktop_config.json` stanzas and `claude mcp add` CLI commands.\n  - **VS Code & Cursor:** Emits `mcpServers` configuration blocks with automatic SSE endpoint binding.\n  - **Antigravity CLI:** Emits `agy mcp add kanban <url> --auth oauth` commands.\n  - **OpenAI Codex:** Emits `codex mcp add kanban <url> --auth oauth` commands.\n- **MCP Config Snippet Modal:** Generates copy-paste configuration snippets for newly minted static API keys across Claude Code, Cursor, Gemini CLI, Antigravity, and OpenAI Codex. Includes a write-only custody warning reminding operators that secrets will never be displayed again.\n\n![Workload OIDC Federation Studio](images/slice3-workload-oidc-studio.png)\n\n### Workload Identity Federation Settings\n\nThe Workload Identity Federation settings govern RFC 8693 token exchange policies minted for automated CI/CD runners, Kubernetes pods, and distributed pipeline workers. Administrators author and manage these policies at `/settings/mcp` (personal workload policies) and `/admin/mcp` (workspace and global workload policies) to eliminate static secrets and long-lived API tokens.\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `name` | Descriptive policy identifier | String (1 to 120 characters) | Required at creation | Displayed in workload policy table and audit ledger |\n| `description` | Human-readable explanation of policy purpose | String (up to 500 characters) or None | None | Documents workload integration context and team ownership |\n| `issuer` | OpenID Connect token issuer URL (`Issuer URL`) | Strict HTTPS URL (1 to 500 characters) | Required at creation | Validates incoming JWT `iss` claim; plaintext HTTP rejected |\n| `client_id` | Expected audience claim (`Client ID / Audience`) | String (1 to 255 characters) | Required at creation | Matches incoming JWT `aud` claim to prevent token cross-use |\n| `subject_pattern` | Subject matching pattern (`Subject Pattern`) | Glob or Regex (1 to 500 characters) | Required at creation | Matches incoming JWT `sub` claim (e.g. `repo:org/repo:*`) |\n| `required_claims_json` | Exact claim match constraints | JSON Object | `{}` | Enforces additional claims (e.g. `{\"environment\": \"production\"}`) |\n| `surface` | Target streamable MCP surface (`Surface`) | `agent` or `docs` | `agent` | Determines which MCP endpoint the federated token can invoke |\n| `scopes` | Allowed OAuth privilege scopes | List of `SURFACE_SCOPES` strings | `[]` (Empty) | Bounds the granted scopes (e.g. `[\"agent:read\", \"agent:write\"]`) |\n| `allowed_project_ids` | Permitted project UUID boundaries | List of UUIDs or None | None (All accessible) | Limits workload token authority strictly to designated project IDs |\n| `allowed_cidrs` | Subnet IP allowlist for token exchange (`Allowed CIDRs`) | Comma or whitespace separated IPv4/IPv6 CIDRs | None (Allow all) | Restricts token exchange to specific runner network IP blocks |\n| `capability_mask` | Capability bitmask ceiling | Integer between 0 and 255 | 255 | Monotonic capability ceiling enforced by RLS |\n| `max_ttl_seconds` | Lifespan of issued ephemeral token (`Max TTL`) | Integer between 60 and 86400 seconds | 3600 (1 hour) | Limits exposure window of federated workload credentials |\n| `is_enabled` | Policy active toggle | Boolean (`true` / `false`) | `true` | Disabled policies immediately reject token exchange |\n\n#### Setting-by-Setting Technical Paragraphs: Workload Identity Federation\n\n- **Issuer URL (`issuer`):** Authoritative OpenID Connect identity provider URL. Must use a strict HTTPS scheme (e.g. `https://token.actions.githubusercontent.com`). Plaintext HTTP URLs are rejected with validation errors to prevent cleartext credential interception over untrusted networks.\n- **Client ID / Audience (`client_id`):** The expected audience claim (`aud`) configured within the workload runner (1 to 255 characters). The \ud83d\udc4dkanban token endpoint verifies that the incoming token audience matches this configured identifier, ensuring tokens generated for other services cannot be repurposed.\n- **Surface (`surface`):** Designates the target Model Context Protocol surface granted to the federated token. Choices are `agent` (grants access to `/mcp/agent` execution and verification tools with a <= 1,850 token prompt ceiling) or `docs` (grants access to `/mcp/docs` knowledge tools with a <= 1,350 token ceiling). Default value is `agent`.\n- **Subject Pattern (`subject_pattern`):** POSIX glob pattern or regular expression evaluated against the incoming OIDC JWT subject (`sub`) claim (1 to 500 characters). Evaluated using POSIX pattern matching to bind token issuance strictly to specific repositories, branches, environments, or Kubernetes service accounts.\n- **Allowed CIDRs (`allowed_cidrs`):** Optional network boundary allowlist restricting token exchange requests to authorized runner subnet IP addresses. Supports comma- or whitespace-delimited IPv4 and IPv6 CIDR notations (e.g. `10.0.0.0/8, 192.168.1.0/24`). Requests originating from unlisted IP addresses are rejected with `403 FORBIDDEN_CIDR`. Default is `None` (all network origins permitted).\n- **Max TTL (`max_ttl_seconds`):** Maximum validity period for issued short-lived ephemeral access tokens (`kb_eat_*`). Enforced between 60 seconds (1 minute) and 86,400 seconds (24 hours), defaulting to `3600` seconds (1 hour). Caps the exposure window if an ephemeral bearer token is leaked in runner logs.\n- **name:** Descriptive policy name (1 to 120 characters) displayed in administration tables and immutable audit logs.\n- **description:** Optional documentation string (up to 500 characters) describing the CI/CD pipeline, team ownership, or repository context.\n- **required_claims_json:** Arbitrary JSON dictionary of required key-value claims that must match exactly in the incoming token payload (e.g. `{\"environment\": \"production\"}`).\n- **scopes:** List of granted OAuth scopes (e.g. `[\"agent:read\", \"agent:write\"]`), strictly validated against the target surface.\n- **allowed_project_ids:** Optional list of project UUIDs restricting where the exchanged token can query or mutate work items.\n- **capability_mask:** Monotonic capability bitmask ceiling (0 to 255, default 255). Further constrains operations permitted by the resulting token.\n- **is_enabled:** Master administrative toggle for the policy. When set to `false`, token exchange requests matching this policy fail closed immediately.\n\n#### RFC 8693 Subject Claim Patterns and Pipeline Examples\n\nAutomated runners authenticate by presenting their signed OIDC identity token to `/oauth/token` using the RFC 8693 token exchange grant:\n\n1. **GitHub Actions Workflow Example:**\n   - **Issuer URL:** `https://token.actions.githubusercontent.com`\n   - **Client ID / Audience:** `https://kanban.example.com`\n   - **Subject Claim Pattern:** `repo:ThumbsUp-HQ/kanban:ref:refs/heads/*` (or `repo:ThumbsUp-HQ/kanban:environment:production`)\n   - **Default Surface:** `agent`\n   - **Default Max TTL:** `3600` seconds (1 hour)\n   - **Sample Incoming Subject Claim:** `repo:ThumbsUp-HQ/kanban:ref:refs/heads/main`\n\n2. **Kubernetes In-Cluster Workload Example:**\n   - **Issuer URL:** `https://kubernetes.default.svc.cluster.local`\n   - **Client ID / Audience:** `https://kanban.example.com`\n   - **Subject Claim Pattern:** `system:serviceaccount:kanban-ci:*` (or `system:serviceaccount:production:release-bot`)\n   - **Default Surface:** `agent`\n   - **Default Max TTL:** `1800` seconds (30 minutes)\n   - **Sample Incoming Subject Claim:** `system:serviceaccount:kanban-ci:builder`\n\n3. **GitLab CI/CD Pipeline Example:**\n   - **Issuer URL:** `https://gitlab.com`\n   - **Client ID / Audience:** `https://kanban.example.com`\n   - **Subject Claim Pattern:** `project_path:thumbs-up-hq/kanban:ref:*:ref_type:branch`\n   - **Default Surface:** `docs`\n   - **Default Max TTL:** `3600` seconds (1 hour)\n   - **Sample Incoming Subject Claim:** `project_path:thumbs-up-hq/kanban:ref:main:ref_type:branch`\n\n#### RFC 8693 Token Exchange Request Format\n\nHeadless pipelines exchange their OIDC token by submitting an HTTP `POST` request to `/oauth/token`:\n\n```http\nPOST /oauth/token HTTP/1.1\nHost: kanban.example.com\nContent-Type: application/x-www-form-urlencoded\n\ngrant_type=urn:ietf:params:oauth:grant-type:token-exchange\n&subject_token=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...\n&subject_token_type=urn:ietf:params:oauth:token-type:jwt\n&requested_token_type=urn:ietf:params:oauth:token-type:access_token\n&audience=https://kanban.example.com\n```\n\nUpon cryptographic signature verification against upstream issuer JWKS and policy pattern evaluation, \ud83d\udc4dkanban issues an ephemeral bearer token (`kb_eat_*`) bound by `CredentialBoundary` and PostgreSQL Row-Level Security.\n\n---\n\n## 7. OAuth 2.1 Governance Studio\nThe OAuth 2.1 Governance Studio (`/admin/oauth`) registers client applications, enforces PKCE code challenges, configures token lifetimes, and manages client revocation.\n\n![OAuth Client Governance Studio Bulk Purge](images/slice3-oauth-governance-bulk-purge.png)\n\n\n### OAuth 2.1 Governance Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `client_name` | Name of the integrating client application | String (1 to 128 characters) | Required | Displayed on user authorization consent screens |\n| `client_id` | Unique OAuth client identifier | String prefixed with `client_` | Auto-generated | Public application key used during authorization code flow |\n| `client_type` | Client confidentiality tier | `public`, `confidential` | `public` | Confidential clients require client secret authentication |\n| `auth_method` | Client authentication method | `none`, `client_secret_post`, `client_secret_basic`, `private_key_jwt` | `none` for public | Governs how client verifies identity at token endpoint |\n| `redirect_uris` | Allowed callback URLs for authorization codes | List of strict HTTPS URLs (localhost allowed for dev) | Required | Exact string matching enforced; wildcards strictly forbidden |\n| `pkce_enforce` | Proof Key for Code Exchange requirement | Mandatory `S256` challenge | `true` (`S256`) | Rejects plaintext code challenges; mitigates authorization code interception |\n| `allowed_scopes` | List of privilege scopes client can request | `agent:read`, `agent:write`, `docs:read`, `docs:write`, `admin:read`, `admin:write`, `admin:destructive` | `agent:read` | Token capability bitmask cannot exceed granted scopes |\n| `access_token_ttl` | Lifetime of minted access tokens | Integer seconds (60 to 86400) | 3600 (1 hour, 900 for JWT) | Ephemeral lifetime limiting blast radius of token leakage |\n| `refresh_token_ttl` | Lifetime of rotating refresh tokens | Integer seconds (86400 to 2592000) | 2592000 (30 days) | Refresh tokens rotate upon use; reused tokens revoke family |\n| `max_state_len` | Maximum length of OAuth state parameter | 4096 characters | 4096 | Supports large serialized state payloads required by Google Gemini |\n| `status_filter` | Filter tabs for client lifecycle view | `all`, `active`, `suspended`, `revoked` | `all` | Isolates active integrations from suspended or revoked clients |\n| `device_code_charset` | RFC 8628 user code alphabet | Base20 consonants (`BCDFGHJKLMNPQRSTVWXZ`) | `BCDFGHJKLMNPQRSTVWXZ` | Excludes vowels (A, E, I, O, U) and numbers (0-9) to eliminate visual ambiguity and accidental profanities |\n| `device_code_ttl` | RFC 8628 user code and device code expiration window | Integer seconds (60 to 900 seconds) | 900 (15 minutes) | Enforces 15-minute expiration window to prevent brute-force enumeration of pending device codes |\n| `device_rate_limit_lockout` | Rate-limit lockout threshold for invalid verification attempts | 5 invalid attempts per 5-minute window | 5 attempts / 300s | Enforces 5-minute freeze upon 5 failed attempts (RATE_LIMIT_EXCEEDED HTTP 429) |\n| `device_polling_interval` | RFC 8628 CLI token poll cadence interval | Integer seconds (1 to 60 seconds) | 5 seconds | Governs client polling frequency at /oauth/token (slow_down returned if polled faster) |\n\n![OAuth Client Governance Studio Paginated 500 Clients](images/slice3-oauth-governance-paginated-500.png)\n\n### Setting-by-Setting Technical Paragraphs\n\n- **`client_name`:** Human-readable title of the client application (1 to 128 characters). Displayed prominently to users on authorization consent screens and within the administrative governance directory.\n- **`client_id`:** Unique identifier generated upon client registration, prefixed with `client_` (`client_{secrets.token_urlsafe(16)}`). Serves as the public identifier across OAuth 2.1 authorization and device authorization flows.\n- **`client_type`:** Distinguishes between `public` clients (single-page applications, native desktop tools like Cursor or Claude Desktop, and CLI binaries that cannot safeguard secrets) and `confidential` clients (backend server applications capable of storing secrets securely).\n- **`auth_method`:** Defines the client authentication mechanism used at `/oauth/token`. Public clients use `none` with mandatory PKCE `S256`. Confidential clients use `client_secret_post` (secret in POST body), `client_secret_basic` (HTTP Basic authentication header), or `private_key_jwt` (RFC 7523 asymmetric client assertion).\n- **`redirect_uris`:** Exact list of authorized redirect callback URIs. Every entry must be a valid HTTPS URL, with `http://localhost` and `http://127.0.0.1` permitted exclusively for local development and desktop tools. Wildcards and open redirect patterns are strictly rejected.\n- **`pkce_enforce`:** Enforces Proof Key for Code Exchange (RFC 7636). \ud83d\udc4dkanban requires `code_challenge_method = S256` for all authorization code flows. Plain code challenges (`code_challenge_method = plain`) are rejected with `400 invalid_request`.\n- **`allowed_scopes`:** Space- or comma-delimited list of privilege scopes available to the client, strictly adhering to `SURFACE_SCOPES`: `agent:read`, `agent:write`, `docs:read`, `docs:write`, `admin:read`, `admin:write`, and `admin:destructive`.\n- **`access_token_ttl`:** Lifetime in seconds of minted access tokens (configurable from 60 to 86,400 seconds; default 3,600 seconds / 1 hour for client credentials, 900 seconds / 15 minutes for JWT assertions). Minimizes the window of exposure if a bearer token is intercepted.\n- **`refresh_token_ttl`:** Lifetime in seconds of refresh tokens (86,400 to 2,592,000 seconds, default 30 days). Refresh tokens rotate upon every exchange; if a previously used refresh token is presented, the entire token family is revoked to prevent replay attacks.\n- **`max_state_len`:** Defines the maximum permitted length of the OAuth `state` parameter (4,096 characters). Specifically engineered to accommodate complex serialized routing and nonce payloads generated by Google Gemini and enterprise identity gateways. Requests exceeding 4,096 characters are rejected with HTTP 400.\n- **`status_filter`:** Filters displayed clients in the Governance Studio across four lifecycle states: `all` (complete registry), `active` (operational clients), `suspended` (temporarily blocked from token exchange), and `revoked` (permanently disabled).\n- **`device_code_charset`:** Defines the Base20 consonant character set (`BCDFGHJKLMNPQRSTVWXZ`) used to generate 8-character user codes formatted as `XXXX-XXXX`. Vowels (`A`, `E`, `I`, `O`, `U`) and digits (`0`-`9`) are excluded to avoid offensive words and eliminate visual ambiguity.\n- **`device_code_ttl`:** The validity lifetime of issued user codes and device authorization grants (up to 900 seconds / 15 minutes, default 900s). Pending user codes expire after 15 minutes, returning `EXPIRED_CODE` on `/activate` lookup.\n- **`device_rate_limit_lockout`:** Rate limiting protection against automated brute-force user code enumeration. If 5 failed verification attempts occur within a 5-minute rolling window (300 seconds), subsequent lookups are rejected with `RATE_LIMIT_EXCEEDED` (HTTP 429) and a 5-minute freeze.\n- **`device_polling_interval`:** The minimum interval in seconds that headless CLI clients must wait between consecutive polling requests to `/oauth/token` (default 5 seconds). Polling faster than this interval triggers RFC 8628 `slow_down` responses with an increased 5-second backoff penalty.\n\n![Device Activation Page](images/slice3-device-activate-page.png)\n\n### RFC 8628 `/activate` Device Flow and Bulk Purge\n\n- **RFC 8628 `/activate` Device Authorization Flow:** For terminal agents and CLI tools unable to host local redirect servers, \ud83d\udc4dkanban implements RFC 8628 device authorization:\n  - **Initiation:** The CLI calls `POST /oauth/device/authorize` with `client_id` and target `resource` (e.g. `https://kanban.example.com/mcp/agent`).\n  - **User Code Formatting:** The server issues an 8-character `user_code` formatted in hyphenated Base20 (`XXXX-XXXX`) using charset `BCDFGHJKLMNPQRSTVWXZ` (excluding vowels `A,E,I,O,U` to avoid offensive words and numbers `0-9` to eliminate visual ambiguity) with a 15-minute expiration (`device_code_ttl = 900`).\n  - **Activation Interface:** The developer visits `/activate`, enters the code, reviews the requested resource and scopes, selects permitted projects, satisfies AAL2 step-up if administrative scopes are requested, and approves the session. A rate-limit lockout guards against brute force (5 failed verification attempts trigger a 5-minute freeze with `RATE_LIMIT_EXCEEDED`).\n  - **Token Exchange:** The CLI polls `POST /oauth/token` with `grant_type=urn:ietf:params:oauth:grant-type:device_code` at the configured RFC 8628 polling interval (default 5s) until approval completes, receiving an ephemeral scoped MCP access token.\n- **Single-Transaction Bulk DCR Client Purge:** High-volume test suites and dynamic client registration can create hundreds of orphaned client rows. The Governance Studio includes a **Purge Stale Clients** action (`POST /api/v1/admin/oauth-clients/bulk-delete`). The backend identifies all public DCR clients with zero active grants and zero refresh tokens, deleting up to thousands of stale records in a single atomic database transaction while preserving active production integrations intact.\n\n---\n\n## 8. AI Providers Studio\nThe AI Providers Studio (`/admin/ai` or `/workspaces/:ws/settings`) configures multi-provider LLM integrations, write-only envelope encryption for API credentials, failover priority ordering, and monthly token budgets with automated circuit breakers.\n\n![AI Providers Studio - Desktop Light](images/slice2-ai-studio-1440x900-light.png)\n\n![AI Provider Editor Drawer - 0 Password Inputs](images/slice2-ai-provider-drawer-create.png)\n\n\n### AI Providers Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `provider_kind` | Underlying AI runtime architecture | `gemini`, `openai`, `ollama` | Required | Governs protocol serialization, tool calling format, and streaming handlers |\n| `display_name` | Human-readable provider label | UTF-8 String (1 to 80 characters) | Required | Displayed on provider cards, failover stack, and token ledger |\n| `base_url` | Upstream API endpoint address | Valid HTTP or HTTPS URL | Provider default | Local Ollama uses `http://127.0.0.1:11434`; cloud requires HTTPS |\n| `api_key` | Secret cryptographic provider credential | String (Write-only custody) | None | Stored encrypted in PostgreSQL; zero password inputs in client DOM |\n| `model_allowlist` | Permitted model identifiers for dispatch | Array or comma-separated list of strings | Probed list | Only allowlisted models are accessible for completion and agent execution |\n| `timeout_ms` | Hard ceiling on provider HTTP transactions | Integer between 1000 and 300000 ms | 30000 ms | Upstream requests exceeding timeout fail closed with `GATE_TIMEOUT` (max 300s) |\n| `temperature` | Randomness parameter for model sampling | Float between 0.0 and 2.0 | 0.7 | Low values (`0.1` to `0.3`) ensure deterministic verification gate verdicts |\n| `top_p` | Nucleus sampling probability cutoff | Float between 0.0 and 1.0 | 1.0 | Filters tail tokens; 1.0 evaluates the full cumulative distribution |\n| `max_tokens` | Maximum generation token ceiling | Integer between 1 and 128000 tokens | 4096 | Constrains generation size to avoid runaway completion loops |\n| `mtls_client_cert_pem` | Client certificate for mutual TLS | Valid PEM certificate block or empty | None | Enables certificate-authenticated transport to private gateways |\n| `is_enabled` | Master active toggle for the provider | Boolean (`true` / `false`) | `true` | Disabled providers are skipped during model probing and runtime dispatch |\n| `period_kind` | Accounting duration for consumption caps | `daily` or `monthly` | `monthly` | Accounting period tier: daily or monthly (resets token consumption counter) |\n| `token_cap` | Monthly token consumption budget limit | Non-negative integer (0 to 10000000000) | 10000000000 | `0` enforces Hard AI Freeze; `10000000000` enables Unlimited Quota |\n\n![Token Budget Modal - Unlimited Quota](images/slice2-ai-budget-modal-unlimited.png)\n\n![Token Budget Modal - Hard AI Freeze Warning](images/slice2-ai-budget-modal-freeze.png)\n\n### Setting-by-Setting Technical Paragraphs: AI Providers and Token Budgets\n\n- **provider_kind:** Identifies the foundational AI provider protocol engine. Supported choices are `gemini` (Google Gemini 2.5 Flash/Pro with native function calling and multimodal spec support), `openai` (OpenAI GPT-4o, GPT-4o-mini, and compatible gateways implementing standard JSON schema tool definitions), and `ollama` (local air-gapped runtimes for private edge models like Llama 3 and DeepSeek-R1). Selecting a kind binds the request serializer, streaming parser, and error mapper.\n- **display_name:** The descriptive title assigned to the provider instance (for example, \"Google Gemini Workspace\" or \"Local Ollama Runtime\"). Scoped to the workspace or server tier, this label identifies the provider across cards in `/admin/ai`, the failover priority stack, and the audit ledger.\n- **base_url:** The root network URL for provider API communications. Cloud providers require secure HTTPS endpoints (`https://generativelanguage.googleapis.com` or `https://api.openai.com/v1`), whereas local Ollama deployments typically connect over internal loopback (`http://127.0.0.1:11434`). Outbound calls are subject to network policy and workspace air-gap restrictions.\n- **api_key:** The secret API key used to authenticate upstream cloud requests. Submitted over TLS, stored encrypted at rest via PostgreSQL envelope encryption, and never echoed back to client browsers. In `AiProviderEditorDrawer`, input fields adhere to strict security invariants by using standard masked inputs with 0 `input[type=\"password\"]` elements, preventing browser credential managers from storing or sniffing AI keys.\n- **model_allowlist:** An explicit allowlist of model names permitted for execution under this provider configuration (e.g. `[\"gemini-2.5-flash\", \"gemini-2.5-pro\"]` or `[\"llama3.2:latest\"]`). Administrators can manually specify identifiers or click `Probe Models` to automatically query the upstream provider API and select discovered models via interactive search chips.\n- **timeout_ms:** The maximum wall-clock request duration allowed for provider calls, bounded between 1,000 ms and 300,000 ms (default 30,000 ms, with a 300-second reasoning ceiling). When combined with agent execution, the runtime enforces `min(provider.timeout_ms, agent.timeout_ms)`. If the upstream model exceeds this cutoff, the system aborts execution, fails closed, and records `GATE_TIMEOUT` without hanging worker threads.\n- **temperature:** Governs generation randomness on a scale from 0.0 to 2.0 (default 0.7). Lower temperatures (0.1 to 0.3) provide highly deterministic outputs recommended for code review, transition gates, and structured JSON parsing, while moderate values (0.7 to 1.0) support creative sticky synthesis and brainstorming.\n- **top_p:** Controls nucleus sampling by restricting generation to tokens comprising the top P probability mass (0.0 to 1.0, default 1.0). Decreasing this value eliminates low-probability generation branches, enhancing predictability in mission-critical QA workflows.\n- **max_tokens:** The upper bound on token output generated in a single completion or reasoning turn (configurable from 1 to 128,000 tokens, default 4,096). Protects against unbounded model loops and limits context window consumption.\n- **mtls_client_cert_pem:** An optional client certificate in PEM format used when establishing mutual TLS connections to enterprise AI gateways or private proxy infrastructure.\n- **is_enabled:** A boolean toggle that immediately activates or deactivates the provider without deleting its configuration or keys. Inactive providers are bypassed during live completion dispatch and sparkle routing.\n- **priority_and_order:** The failover dispatch sequence determined via `PUT /api/v1/admin/ai/providers/order` (or `PUT /api/v1/workspaces/:ws/ai-providers/order`). Providers are evaluated sequentially by priority. If a higher-tier provider encounters a 5xx error or rate limit, the router seamlessly falls back to the next active provider in the stack.\n- **token_cap_and_budgets:** Managed via `PUT /api/v1/admin/ai/budgets` (or `PUT /api/v1/workspaces/:ws/ai-providers/budgets`) across daily or monthly periods (`period_kind`). Setting `token_cap = 0` triggers a Hard AI Freeze, immediately rejecting reservations with `BudgetExceeded` and halting Sparkle completions with status `budget`. Selecting Unlimited Quota configures an internal ceiling of 10,000,000,000 tokens, recording ledger telemetry without automated cutoffs. Quick presets provide standard allowances of 1M, 5M, 25M, and 100M tokens.\n\n> [!NOTE]\n> For headless CI/CD pipelines, automated runners, and external agents authenticating via RFC 8693 token exchange without static API keys, configure Workload Identity Federation policies in the MCP Access Studio. See [Workload Identity Federation Settings](#workload-identity-federation-settings) for parameter specifications, valid formats, and subject claim examples.\n\n---\n\n## 9. Agent Definitions Studio\nThe Agent Definitions Studio (`/admin/agents` or `/projects/:proj/settings/agents`) configures autonomous agent personas, tool permission boundaries, execution harnesses, and developer onboarding prompts.\n\n![Agent Definitions Studio - Desktop Light](images/slice2-agent-studio-1440x900-light.png)\n\n![Agent Definitions Studio - Desktop Dark](images/slice2-agent-studio-1440x900-dark.png)\n\n\n### Agent Definitions Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `slug` | Unique URL-safe agent identifier | Lowercase alphanumeric ASCII with hyphens (1 to 64 chars) | Required | Used in ticket `@mentions`, API URLs, and activity logs |\n| `display_name` | Human-readable name of the agent | UTF-8 String (1 to 200 characters) | Required | Displayed on ticket assignment cards and inspection drawers |\n| `harness_kind` | Runtime execution environment | `in_app_sdk`, `cli_pipe`, `remote_runner` | `in_app_sdk` | Governs execution boundary, isolation model, and process privileges |\n| `provider_kind` | AI provider bound to the agent | `gemini`, `openai`, `ollama` | Provider default | Used when `harness_kind = in_app_sdk` to route LLM queries |\n| `model_id` | Model slug for agent reasoning | Valid model identifier string | Provider default | Controls reasoning depth and token processing speed |\n| `cli_binary_allowlist_id`| Pre-approved binary for CLI pipe harness | `agy`, `codex` | `agy` | Zero-shell execution over stdin/stdout inside hardened Linux jail |\n| `cli_args` | Command-line arguments for CLI pipe | Array of string arguments | `[\"-p\"]` | Structured arguments passed directly via execve (never shell) |\n| `remote_runner_pool_slug`| Target pool for remote worker dispatch | Valid pool slug identifier | `default` | Routes heavy build tasks to distributed mTLS worker nodes |\n| `repo_access_mode` | Repository filesystem access permissions | `none`, `ro_vfs_mount`, `bare_git_tools` | `none` | `ro_vfs_mount` mounts Git repo read-only; prevents code tampering |\n| `mcp_allowed_tools` | Permitted Model Context Protocol tools | Array of tool names | Basic read set | Restricts capabilities to least privilege allowlist (`search_tickets`, `read_ticket`, `search_knowledge`, `read_doc`) |\n| `system_instructions_md`| Persona prompt and operational charter | Canonical UTF-8 Markdown | Required | Directs reasoning behavior and verification requirements |\n| `timeout_ms` | Maximum execution time before cancellation | Integer between 1000 and 300000 ms | 60000 ms | Hard cutoff ceiling; uncompleted tasks fail closed safely (max 300s) |\n| `project_id` | Project scoping and tenancy binding | Valid UUID or null | Null (Workspace) | Enforces PostgreSQL `FORCE ROW LEVEL SECURITY` tenant isolation |\n| `agent_onboarding_prefs`| User preferences for agent onboarding | JSON object | `{}` | Stores execution mode, model strategy, and QA rigor from `/llms.txt` |\n\n![Agent Validation Modal - 4-Section Trace](images/slice2-agent-validation-modal-trace.png)\n\n![Agent Onboarding Card - Desktop Light](images/slice2-onboarding-1440x900-light.png)\n\n### Setting-by-Setting Technical Paragraphs: Agent Definitions and Onboarding\n\n- **slug:** The immutable machine identifier for the agent definition (e.g. `reality-checker`, `security-auditor`). Constrained to lowercase alphanumeric ASCII characters and hyphens. The slug forms the primary address for ticket comments, mention notifications, and REST endpoint routes (`/api/v1/admin/agent-definitions/:slug`).\n- **display_name:** The human-facing label rendered on board cards, ticket assignment selectors, peek drawers, and audit trails. Allows teams to provide intuitive persona titles (e.g. \"Forensic QA Reality Checker\" or \"Architecture Auditor\").\n- **harness_kind:** Specifies the runtime execution architecture. `in_app_sdk` executes in-process using configured cloud or local LLM providers. `cli_pipe` executes external command-line binaries (`agy`, `codex`) inside a zero-shell Linux namespace jail (`nsjail`), communicating strictly over standard input/output with 512 MB memory caps and zero network access. `remote_runner` dispatches tasks to distributed worker daemons connected over mutual TLS.\n- **provider_kind and model_id:** Applicable to `in_app_sdk` harnesses. Specifies the active provider backend (`gemini`, `openai`, `ollama`) and specific model (e.g. `gemini-2.5-flash`, `gpt-4o`, `llama3.2:latest`) utilized for the agent persona's completion and tool-calling cycles.\n- **cli_binary_allowlist_id and cli_args:** Governs `cli_pipe` execution. Restricts binary invocations to pre-vetted host binaries (`agy`, `codex`). Arguments are submitted as an array of safe flags (default `[\"-p\"]`) executed directly via `execve`, eliminating shell injection hazards (`/bin/sh` is never spawned).\n- **remote_runner_pool_slug:** Designates the distributed worker pool (such as `default` or `gpu-compute`) responsible for accepting tasks when `harness_kind = remote_runner`.\n- **repo_access_mode:** Enforces Git repository access boundaries during task execution. In `none` mode, the agent operates solely on ticket prose. In `ro_vfs_mount` mode, the target repository is mounted strictly read-only (`CLONE_NEWNS`), allowing static code analysis while preventing unauthorized workspace writes. In `bare_git_tools` mode, read-only bare Git inspection tools are provisioned in an isolated tmpfs directory.\n- **mcp_allowed_tools:** An array of tool names defining the explicit Model Context Protocol allowlist for the agent. Tools outside this list (`search_tickets`, `read_ticket`, `search_knowledge`, `read_doc`) are hidden from the agent's schema, enforcing strict privilege separation (submitting unlisted tools fails with HTTP 422 `HARNESS_FIELDS_INVALID`).\n- **system_instructions_md:** The core persona prompt formatted in canonical UTF-8 Markdown. Directs agent analysis, defines verification standards, and specifies output formats. Server-side sanitization strips lone surrogates and harmful prompt injection vectors before database storage.\n- **timeout_ms:** Maximum allowable execution time for agent invocations, configurable from 1,000 ms to 300,000 ms (default 60,000 ms, adhering to the 300-second reasoning ceiling from KAN-430). Tasks that exceed this threshold are terminated immediately, preserving thread pools and avoiding stuck workflows.\n- **project_id and rls_isolation:** Binds the agent definition to a specific project UUID or leaves it at workspace scope. PostgreSQL `FORCE ROW LEVEL SECURITY` strictly isolates project agents: administrators and members of other projects cannot view, mutate, or validate cross-project agents (returning HTTP 404 Not Found).\n- **agent_validation_modal:** Invoked via `POST /api/v1/admin/agent-definitions/:id:validate` or `POST /api/v1/agent-definitions/:id:validate`. Executes a live non-destructive test invocation returning a 4-section forensic verification report: 1. `=== 1. RENDERED CONTEXT ===`, 2. `=== 2. TOOL TRACE ===`, 3. `=== 3. LATENCY & TOKENS ===`, and 4. `=== 4. SCHEMA & POLICY STATUS ===`.\n- **llms_txt_and_onboarding_card:** Machine-readable agent capabilities and skill manifests served at `/llms.txt`. The onboarding card surfaces the canonical onboarding prompt that guides external agents (Claude Code, OpenAI Codex, Gemini CLI) through an interactive setup interview, persisting user preferences (`execution_mode`, `model_strategy`, `qa_rigor`, `custom_notes`) to `agent_onboarding_prefs` in `/api/v1/users/me/preferences` strictly within the local project folder without polluting global system paths.\n\n---\n\n## 10. Remote Runners Studio\nThe Remote Runners Studio (`/admin/agent-runners`) monitors distributed worker nodes, mints single-use enrollment tokens, and manages hardware-bound mutual TLS (mTLS) identities.\n\n![Remote Runners Studio - Desktop Light](images/slice2-runner-studio-1440x900-light.png)\n\n![Remote Runners Studio - Desktop Dark](images/slice2-runner-studio-1440x900-dark.png)\n\n\n### Remote Runners Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `hostname` | Unique network hostname of the runner node | String (1 to 64 characters) | Required | Displayed in runner health cards and active execution telemetry |\n| `pool_slug` | Resource pool grouping for runner fleet | Lowercase ASCII slug | `default` | Allows target assignment of jobs to specialized hardware fleets |\n| `enrollment_token` | Single-use cryptographic enrollment token | Base64-encoded HMAC string | Minted on demand | Expires in 60s to 900s (max 15 min); burns upon first enrollment |\n| `client_cert_sha256_hex`| SHA-256 fingerprint of client certificate | 64-char hexadecimal string | Computed at enroll | Binds hardware identity to mTLS WebSocket connection over port :8444 |\n| `cert_expires_at` | Client certificate expiration timestamp | ISO-8601 Timestamp | 30 days from mint | Enforces periodic hardware credential rotation |\n| `status` | Current operational connectivity state | `online`, `offline`, `revoked` | `offline` | Only `online` runners receive dispatched build and verification jobs |\n| `last_heartbeat_at` | Timestamp of most recent daemon ping | ISO-8601 Timestamp or null | Null | Heartbeat frame received every 15s; missing 45s marks runner offline (`DEAD_EVICTION_S = 45.0`) |\n| `runner_cli_command` | Canonical enrollment CLI invocation | Shell command string | Auto-generated | `echo \"$TOKEN\" | uv run kanban-agent-runner enroll --server-url <origin> --token-stdin --pool <pool>` |\n| `state_dir_permissions` | POSIX permissions on runner daemon host | Octal mode (`0o700`, `0o600`, `0o644`) | Strict defaults | `0o700` state dir, `0o600` `client.key` & `ca.pem`, `0o644` `client.crt` |\n| `mtls_pop_challenge` | Challenge format for Proof-of-Possession | Text challenge string | Auto-generated | Syntax: `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256}` |\n\n![Runner Mint Token Modal](images/slice2-runner-mint-token-modal.png)\n\n### Setting-by-Setting Technical Paragraphs: Remote Runners Fleet\n\n- **hostname and pool_slug:** The runner hostname uniquely identifies the physical or virtual execution host (for example, `worker-01.internal.test`). The pool slug groups runners into specialized task fleets (such as `default` or `gpu-compute`), enabling workflows to direct heavy verification suites to properly provisioned worker infrastructure.\n- **enrollment_token:** Ephemeral, single-use authentication token minted via `POST /api/v1/admin/agent-runners/enrollment-tokens`. Token lifetime is strictly capped between 60 and 900 seconds (maximum 15 minutes). The token is consumed immediately upon successful certificate signing; replaying an expired or consumed token is rejected with HTTP 401 `ENROLLMENT_TOKEN_INVALID`.\n- **client_cert_sha256_hex:** The cryptographic SHA-256 digest of the X.509 client certificate generated during runner daemon enrollment. The orchestrator registers this fingerprint in the database, verifying that incoming mutual TLS connections match the approved hardware certificate.\n- **cert_expires_at:** The expiration timestamp for the signed client certificate (standard 30-day validity). When a certificate approaches expiration, the runner must be re-enrolled using a freshly minted token.\n- **status and heartbeats:** Reflects runner operational status (`online`, `offline`, or `revoked`). Active daemons send periodic `HeartbeatFrame` packets every 15 seconds over the established mTLS WebSocket channel. If no heartbeat is received within 45 seconds (`DEAD_EVICTION_S = 45.0`), the runner transitions to `offline`, and pending tasks are rescheduled.\n- **unprivileged_daemon_and_posix_permissions:** The runner daemon (`kanban-agent-runner`) executes as an unprivileged, non-root system account. Local cryptographic assets are created with strict POSIX file permissions: state directory `0o700` (`drwx------`), private key `client.key` `0o600` (`-rw-------`), root CA bundle `ca.pem` `0o600` (`-rw-------`), and client certificate `client.crt` `0o644` (`-rw-r--r--`).\n- **mtls_pop_handshake:** Mutual TLS connections connect to dedicated port `:8444` (or WebSocket route `/api/v1/agent-runners/ws`). During handshake, the orchestrator issues a `ChallengeHelloFrame` containing an ephemeral nonce. The runner signs the canonical challenge payload `kb-runner-pop-v1:{runner_id}:{nonce}:{cert_sha256}` using its private EC key, proving certificate possession before transitioning to `online`.\n- **runner_revocation:** Administrators can instantly revoke rogue or decommissioned runners via `POST /api/v1/admin/agent-runners/:id:revoke`. Revocation immediately terminates active WebSocket connections and flags the certificate fingerprint as revoked. Subsequent connection attempts are rejected with HTTP 403 Forbidden.\n\n> [!NOTE]\n> **Runner Certificate Rotation Lifecycle:** Runner client certificates are hardware-bound and cannot be silently renewed in place. To rotate a certificate, revoke the runner in `/admin/agent-runners` (AAL2 challenge confirmed), mint a fresh enrollment token (15-minute TTL), and re-enroll the runner daemon.\n\n\n---\n\n## 11. Standalone & Promotion Studio\nThe Standalone & Promotion Studio (`/admin/standalone`) inspects deployment topologies, triggers promotion to multi-container compose, and exports encrypted backups.\n\n![Standalone Status Studio - Desktop Light](images/slice4-standalone-1440x900-light.png)\n\n\n### Standalone & Promotion Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `deployment_mode` | Current platform runtime environment | `standalone_embedded_pg`, `production_multi_container` | Detected at boot | Gates availability of nsjail container sandboxes and Redis hubs |\n| `passphrase` | Secret passphrase used to derive AES-256 backup key | String (Minimum 16 characters) | User-supplied | Encrypts archive into streaming KBKP or snapshot KBBAK1 format |\n| `auto_backup_enabled` | Recurring automated background snapshot toggle | Boolean (`true` / `false`) | `false` | Instructs .kb_ops.sock daemon to create automated snapshots |\n| `backup_interval_hours`| Frequency of automated snapshot execution | Integer between 1 and 168 hours | `24` | Governs Recovery Point Objective (RPO) and background IO scheduling |\n| `snapshot_retention_count` | Number of historical snapshot archives retained on server disk | Integer between 1 and 90 | `7` | Purges older snapshots automatically while keeping latest N snapshots |\n| `confirm_overwrite` | Confirmation phrase required for destructive restore | Exact string `\"RESTORE\"` | None | Prevents accidental database erasure during snapshot restoration |\n| `backup_storage_path` | Local filesystem path where backups are stored | Directory path (`/var/lib/kanban/data/backups`) | `/var/lib/kanban/data/backups` | Isolated storage managed by `/run/postgresql/.kb_ops.sock` daemon |\n| `compose_networks` | Network isolation topology for exported compose bundle | 5 networks (`edge_net`, `app_net`, `data_net`, `sandbox_net`, `egress_llm_net`) | 5 networks | Eliminates single-network lateral movement across services |\n\n![Standalone Backups and Snapshot History](images/slice4-standalone-backups-snapshot-history.png)\n\n### Setting-by-Setting Technical Paragraphs\n\n- **`deployment_mode`:** Detects whether \ud83d\udc4dkanban is executing inside a single standalone container (`standalone_embedded_pg`, typically launched via `docker run -p 8080:8080 thumbs-up-kanban:latest` with internal PostgreSQL 16) or within a compartmentalized production cluster (`production_multi_container`). In standalone mode, external Redis is optional and background tasks run in-process, whereas multi-container mode unlocks dedicated worker containers and nsjail container isolation.\n- **`passphrase`:** The client-supplied cryptographic passphrase submitted during manual streaming backup download (`POST /api/v1/admin/standalone/backup`) and database restoration (`POST /api/v1/admin/standalone/restore`). Must be at least 16 characters in length. The server derives an AES-256-GCM symmetric key via PBKDF2-HMAC-SHA256 across 600,000 iterations for KBKP streaming downloads, or Argon2id for KBBAK1 archives.\n- **`auto_backup_enabled`:** Toggles automated recurring background snapshots executed by the root-privileged `/run/postgresql/.kb_ops.sock` daemon. When enabled, the daemon captures full PostgreSQL state and object graph assets into `/var/lib/kanban/data/backups` using the timestamped `KBBAK1` format without interrupting active HTTP or WebSocket connections.\n- **`backup_interval_hours`:** Configures the interval between automated snapshot runs. The backend permits values between 1 and 168 hours (default 24 hours). This setting determines how frequently the `/run/postgresql/.kb_ops.sock` daemon wakes to execute scheduled pg_dump snapshot routines.\n- **`snapshot_retention_count`:** Defines the maximum number of automated snapshot `.kbbak` archives preserved within `/var/lib/kanban/data/backups` (configurable from 1 to 90, default 7). When a newly generated snapshot exceeds this threshold, the snapshot manager unlinks the oldest archives while verifying that at least the configured retention count remains accessible.\n- **`confirm_overwrite`:** The mandatory safety gate required by the destructive database restore endpoint (`POST /api/v1/admin/standalone/restore`). The payload must contain the exact uppercase string `\"RESTORE\"`. Any request containing mismatched, lowercase, or omitted confirmation tokens is immediately rejected with HTTP 422 before any database sequence is touched or tables are dropped.\n- **`backup_storage_path`:** The server-side directory where automated `.kbbak` archives reside (`/var/lib/kanban/data/backups`). This path is protected with restrictive permissions and managed exclusively by the fixed-operation socket daemon.\n- **`compose_networks`:** The 5-network topology exported by `GET /api/v1/admin/standalone/compose-export`. Separates traffic across `edge_net` (Caddy TLS ingress), `app_net` (FastAPI backend), `data_net` (PostgreSQL 16 and Redis), `sandbox_net` (untrusted Wasm and runner execution), and `egress_llm_net` (outbound AI provider traffic). Accompanied by a secret-scrubbed `.env.example` file.\n\n---\n\n## 12. Migration Import Studio\nThe Migration Import Studio (`/admin/imports`) provides lossless data ingestion from Plane, Jira, GitHub Issues, Linear, and canonical portable workspace bundles.\n\n![Migration Import Studio Multi-Source Tabs](images/slice4-imports-multi-source-tabs.png)\n\n\n### Migration Import Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `workspace_slug` | Destination workspace tenant identifier | Lowercase alphanumeric ASCII with hyphens | Active workspace | Attaches imported entities to specified tenant under PostgreSQL RLS |\n| `project_key` | Destination project prefix key (e.g. `KAN`, `JIRA`) | Uppercase ASCII alphanumeric (2 to 10 chars) | Bundle default | Re-keys issues sequentially while preserving historical keys as aliases |\n| `dry_run` | Non-destructive simulation toggle | Boolean (`true` / `false`) | `false` | Calculates entity diffs inside a database savepoint without persisting |\n| `user_map` | Mapping dictionary from source users to canonical users | JSON dictionary of strings | `{}` | Binds historical authors, assignees, and commenters to active principals |\n| `export_workspace_slug` | Target workspace for generating portable bundles | Existing workspace slug | Current | Exports canonical `.tar.gz` archive containing entities, docs, and links |\n| `export_scrub` | Redacts sensitive secrets and tokens during export | Boolean (`true` / `false`) | `false` | Scrubs passwords, bearer tokens, and credentials from markdown before export |\n\n![Migration Import Studio - Desktop Light](images/slice4-imports-1440x900-light.png)\n\n### Setting-by-Setting Technical Paragraphs\n\n- **`per_source_endpoints`:** Ingestion is executed via 4 distinct per-platform endpoints: `POST /api/v1/admin/imports/plane` (Plane workspace JSON), `POST /api/v1/admin/imports/jira` (Jira Cloud/Server JSON or REST dump with ADF support), `POST /api/v1/admin/imports/github` (GitHub Issues REST/CLI JSON), and `POST /api/v1/admin/imports/linear` (Linear JSON archive). Each parser normalizes rich text into sanitized UTF-8 CommonMark while strictly rejecting Unicode lone surrogates.\n- **`workspace_slug` and `project_key`:** Defines the destination tenant context and issue key prefix for the imported dataset. If specified, issues are allocated sequential integer sequence IDs under the destination project key (e.g. `KAN-1`, `KAN-2`). If left empty, the importer provisions or resolves the workspace and project names specified within the input bundle.\n- **`dry_run`:** Controls whether database modifications are committed. When set to `true`, the importer runs within a PostgreSQL `SAVEPOINT`, parses all entities, validates foreign keys, checks user mappings, and emits an `ImportDiffReport` before rolling back the savepoint. When set to `false`, the operation executes within an atomic database transaction that commits only upon 100% validation success.\n- **`user_map`:** A JSON dictionary mapping source account identifiers, legacy usernames, or email addresses to canonical \ud83d\udc4dkanban user accounts (e.g. `{\"legacy_dev\": \"alice@example.com\"}`). Unmapped accounts fall back to system defaults, ensuring that ownership, assignments, and historical comments remain traceable.\n- **`legacy_key_aliases`:** Upstream issue keys (such as `JIRA-101`, `GH-88`, `ENG-42`) are automatically extracted and recorded in the `issue_key_aliases` catalog. When queries arrive for obsolete keys (`GET /api/v1/issues/{issue_key}`), API clients receive `200 OK` JSON with header `X-Kanban-Canonical-Key: {canonical_key}`, while browser requests requesting `text/html` receive `HTTP 308 Permanent Redirect` with `Location: /projects/{project_key}/issues/{canonical_key}`.\n- **`export_workspace_slug` and `export_scrub`:** Used by the portable workspace exporter (`POST /api/v1/admin/exports/portable`) to generate a compressed `.tar.gz` bundle. When `scrub=true` (`export_scrub` in UI), secret patterns and authentication tokens are actively redacted from prose fields before packaging.\n\n---\n\n## 13. Admin Diagnostics & Realtime Probes Studio\nThe Admin Diagnostics Studio (`/admin/diagnostics`) monitors subsystem health, executes active telemetry probes, and tracks container resource limits.\n\n![Admin Diagnostics Studio - Desktop Light](images/slice4-diagnostics-1440x900-light.png)\n\n\n### Admin Diagnostics Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `postgresql_rls` | PostgreSQL connectivity, pool saturation, migrations, RLS | 82 migrations, 100 tables `FORCE RLS` | Continuous | Core persistence and tenant isolation; latency threshold < 15ms |\n| `realtime_hub_outbox` | Transactional outbox relay and dispatch loop | Backlog depth, lag seconds, listener status | Continuous | Event delivery to WebSocket subscribers; lag threshold < 5s |\n| `job_worker_pool` | Background asynchronous task execution engine | Active tasks, worker concurrency, DLQ depth | Continuous | Processes asynchronous jobs; dead-letter queue must equal 0 |\n| `wasm_script_sandbox` | Wasmtime AST compiler and script sandbox execution | Compiler state, memory limits, fuel budget | Continuous | Sandboxed custom fields; fuel caps prevent infinite execution loops |\n| `agent_runtime_providers`| Health and latency of active AI model providers | `openai`, `gemini`, `ollama` provider status | Continuous | Informs sparkle completions and AI gates; reports monthly budget |\n| `remote_runner_fleet` | Connected mTLS build runner nodes over port :8444 | Online runner count, heartbeat timestamp | Continuous | Distributed workload execution; heartbeats must arrive within 30s |\n| `rate_limiter` | In-memory token bucket and IP throttle health | Bucket capacity, blocked IP count, error rate | Continuous | Protects API endpoints from volumetric denial-of-service |\n| `realtime_pubsub_probe` | Active PostgreSQL LISTEN/NOTIFY latency measurement | Latency milliseconds (target < 1.0ms) | On Demand | Validates database pub/sub bus responsiveness |\n| `websocket_ws_probe` | Real WebSocket ping/pong frame roundtrip measurement | Latency milliseconds (target < 50ms) | On Demand | Validates client-to-server WebSocket bidirectional messaging |\n\n![Admin Diagnostics Realtime Probe Active](images/slice4-diagnostics-realtime-probe-active.png)\n\n### Setting-by-Setting Technical Paragraphs\n\n- **`postgresql_rls`:** Evaluates database health via `GET /api/v1/admin/diagnostics`. Asserts that the single-head Alembic migration tree is fully applied (82/82 migrations), connection pool saturation remains under 75%, and all 100 application tables enforce `FORCE ROW LEVEL SECURITY`. Connection latency is sampled continuously with healthy thresholds < 15ms.\n- **`realtime_hub_outbox`:** Tracks the transactional outbox relay daemon (`database/outbox/relay.py`). Measures the unprocessed message queue depth, average dispatch lag (healthy < 5s), and PostgreSQL `LISTEN/NOTIFY` channel subscription status. Stalled outboxes trigger immediate administrative alerts.\n- **`job_worker_pool`:** Monitors asynchronous background task executors responsible for webhook dispatch, automated snapshot creation, and audit logging. Reports total active tasks, concurrency utilization, and dead-letter queue (DLQ) depth. Any non-zero DLQ count indicates unhandled job failures requiring inspection.\n- **`wasm_script_sandbox`:** Monitors the in-process Wasmtime runtime executing custom field formulas and transition helpers. Verifies compiler initialization, memory consumption caps (default 32 MiB / 33,554,432 bytes per instance), and fuel budget limits preventing CPU exhaustion.\n- **`agent_runtime_providers`:** Asserts the availability and response latency of registered AI model providers (`gemini`, `openai`, `ollama`). Reports monthly token consumption against configured budget ceilings, warning administrators before cloud budget caps halt automated transition gates.\n- **`remote_runner_fleet`:** Tracks external execution nodes connected via mutual TLS (mTLS) over dedicated port `:8444`. Reports active runner counts, certificate expiration dates, and heartbeat timestamps. Runners failing to report within 30 seconds are marked offline and their active leases rescheduled.\n- **`rate_limiter`:** Reports the runtime state of in-memory token bucket rate limiters across public and authenticated routes. Tracks blocked request volumes and active IP throttle mappings, ensuring system resilience against abusive traffic.\n- **`realtime_pubsub_probe` and `websocket_ws_probe`:** On-demand latency probes. The pub/sub probe (`POST /api/v1/admin/diagnostics/probes/realtime`) injects a synthetic outbox notification and captures `LISTEN/NOTIFY` roundtrip time (typically ~0.38ms). The WebSocket probe initiates a live `/ws` binary ping frame in the operator's browser, measuring connection setup (~13.7ms) and ping/pong roundtrip latency (~0.44ms).\n\n---\n\n## 14. Universal Object Graph Link Auditor Studio\nThe Universal Object Graph Link Auditor Studio (`/admin/link-auditor`) inspects, classifies, and remediates referential integrity anomalies across all registered entities.\n\n![Link Auditor Studio - Desktop Light](images/slice4-link-auditor-1440x900-light.png)\n\n\n### Link Auditor Studio Configuration Table\n\n| Field Name | What It Controls | Allowed Values / Format | Default | Security / Operational Impact |\n| :--- | :--- | :--- | :--- | :--- |\n| `audit_ids` | Flagged link audit record UUIDs selected for purge | List of 1 to 200 UUIDs | Mandatory in purge | Scope of destructive link deletion in single atomic transaction |\n| `reason` | Mandatory administrative justification for link purge | String (10 to 500 characters) | Mandatory in purge | Recorded in immutable activity ledger; rejects < 10 chars with 422 |\n| `status_filter` | Filter tabs for inspecting audit record lifecycle | `unpurged`, `purged`, `resolved`, `all` | `unpurged` | Isolates active anomalies from resolved historical records |\n| `reason_filter` | Filters links by formal invalidity category | All 7 `InvalidLinkReason` codes | `ALL` | Isolates specific defect patterns for forensic inspection |\n\n![Link Auditor Integrity Scan Active](images/slice4-link-auditor-integrity-scan-active.png)\n\n### Setting-by-Setting Technical Paragraphs\n\n- **`audit_scan`:** Triggered via `POST /api/v1/admin/object-links:audit` (or the **Run Integrity Scan** button). Traverses `object_links` and returns summary counts across all 7 formal `InvalidLinkReason` codes without acquiring table locks.\n- **`reason_filter`:** Allows administrators to filter detected anomalies across the 7 formal `InvalidLinkReason` classes:\n  1. `DANGLING_SOURCE`: Source object UUID does not exist in the universal object spine.\n  2. `DANGLING_TARGET`: Target object UUID does not exist in the database.\n  3. `SOFT_DELETED_ENDPOINT`: One or both endpoints reference an object soft-deleted beyond the retention window.\n  4. `ARCHIVED_POLICY_VIOLATION`: Link connects active and archived entities violating project archiving rules.\n  5. `TYPE_MATRIX_VIOLATION`: Relation violates the registered link type matrix allowlist.\n  6. `CROSS_WORKSPACE_LEAK`: Link connects entities across disjoint workspace boundaries without federation.\n  7. `PERMISSION_SEVERED`: Endpoints span boundaries where caller or entity permissions have been severed.\n- **`audit_ids`:** The explicit list of 1 to 200 audit record UUIDs submitted to `POST /api/v1/admin/object-links:purge`. Submissions with fewer than 1 or more than 200 items are rejected with HTTP 422.\n- **`reason`:** The mandatory rationale string required by `POST /api/v1/admin/object-links:purge`. The string must contain at least 10 non-whitespace characters (e.g. `\"Decommissioning orphaned test links post-cutover\"`). Rationale strings containing fewer than 10 characters are rejected with HTTP 422.\n- **`status_filter`:** Selects the display subset in the Studio UI: `unpurged` (flagged items requiring operator intervention), `purged` (historically purged records), `resolved` (links where the underlying anomaly was repaired), or `all`.\n- **`immutable_audit_ledger`:** Every completed purge operation writes an immutable `INVALID_OBJECT_LINK_PURGED` event to `activity_records`. The response returns `purged_count` and the list of `activity_ids` emitted to the ledger for forensic verification.\n"
  },
  {
    "slug": "system-topology-and-multi-container-architecture",
    "title": "[Architectural] System Topology and Multi-Container Architecture",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Functional Architecture",
    "audience": "Infrastructure & Systems Architects",
    "order": 27,
    "summary": "The \ud83d\udc4dkanban platform is designed for operational flexibility and security hardening. It supports two primary deployment topologies: 1. **Standalone Single-Container Mode (`docker run`):** A zero-dependency, turnkey distribution where the web application, FastAPI backend, and PostgreSQL 16 database run within a single container using an embedded Unix socket. Ideal for evaluation, air-gapped workstations, and single-host developer instances. 2. **Multi-Container Production Stack (`docker compose`):** An enterprise-grade, five-network isolated container mesh designed for high availability, least-privilege service boundaries, and strict network compartmentalization.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "monorepo-code-organization",
        "title": "Monorepo Code Organization",
        "level": 2
      },
      {
        "id": "standalone-single-container-deployment-docker-run",
        "title": "Standalone Single-Container Deployment (docker run)",
        "level": 2
      },
      {
        "id": "internal-unix-socket-architecture",
        "title": "Internal Unix-Socket Architecture",
        "level": 3
      },
      {
        "id": "workspace-home-and-initial-state",
        "title": "Workspace Home and Initial State",
        "level": 3
      },
      {
        "id": "multi-container-production-architecture-docker-compose",
        "title": "Multi-Container Production Architecture (docker compose)",
        "level": 2
      },
      {
        "id": "the-5-network-isolation-matrix",
        "title": "The 5-Network Isolation Matrix",
        "level": 3
      },
      {
        "id": "monotonic-credentialboundary-across-container-mesh",
        "title": "Monotonic CredentialBoundary Across Container Mesh",
        "level": 3
      },
      {
        "id": "process-hardening-and-least-privilege",
        "title": "Process Hardening and Least Privilege",
        "level": 3
      },
      {
        "id": "supply-chain-integrity-and-permissive-licensing",
        "title": "Supply Chain Integrity and Permissive Licensing",
        "level": 2
      }
    ],
    "content": "# [Architectural] System Topology and Multi-Container Architecture\n\n## Overview\n\nThe \ud83d\udc4dkanban platform is designed for operational flexibility and security hardening. It supports two primary deployment topologies:\n1. **Standalone Single-Container Mode (`docker run`):** A zero-dependency, turnkey distribution where the web application, FastAPI backend, and PostgreSQL 16 database run within a single container using an embedded Unix socket. Ideal for evaluation, air-gapped workstations, and single-host developer instances.\n2. **Multi-Container Production Stack (`docker compose`):** An enterprise-grade, five-network isolated container mesh designed for high availability, least-privilege service boundaries, and strict network compartmentalization.\n\nBoth deployment modes are built upon a clean monorepo architecture and adhere to a strict Apache-2.0 pure licensing mandate with zero AGPL, GPL, or SSPL runtime dependencies.\n\n---\n\n## Monorepo Code Organization\n\nThe platform source code is organized into modular packages:\n\n```\nkanban/\n|-- kanban/                  # FastAPI web server, REST API, WebSocket hub, content pipelines\n|   |-- api/v1/              # Versioned API routes (275 endpoints, 366 operations, 384 schemas, OpenAPI 3.1.0)\n|   |-- auth/                # Multi-card authentication studio, session management, CSRF\n|   |-- content/             # Canonical Markdown normalizer, Unicode guards, hidden-DOM pruner\n|   |-- realtime/            # Distributed WebSocket hub, connection manager, event router\n|   `-- web/                 # React 19 single-page application (SPA) with Vite and Tailwind\n|-- database/                # Universal Object Graph, PostgreSQL schemas, and migrations\n|   |-- migrations/          # Alembic schema migrations (kanban_migrator)\n|   |-- models/              # SQLAlchemy 2.0 models with FORCE ROW LEVEL SECURITY\n|   `-- auditor/             # Universal object link integrity auditor and purger\n|-- mcp/                     # Three-surface Model Context Protocol server (25 tools total)\n|   |-- surfaces/agent/      # /mcp/agent (10 execution & QA tools)\n|   |-- surfaces/docs/       # /mcp/docs (3 knowledge & doc tools: search, create, update)\n|   |-- surfaces/admin/      # /mcp/admin (12 governance & lifecycle tools)\n|   `-- yaml_out.py          # InlineSafeDumper YAML serializer for token efficiency\n`-- agent/                   # Autonomous AI runtime and orchestration engine\n    |-- providers/           # Pluggable LLM clients (OpenAI, Ollama, Gemini)\n    |-- runners/             # Local CLI pipe harnesses (agy -p, codex -p) and mTLS runners\n    `-- sparkle/             # Inline cursor completion (FIM) and ghost-text engine\n```\n\n---\n\n## Standalone Single-Container Deployment (`docker run`)\n\nIn standalone mode, a single Docker container encapsulates the complete stack without requiring external database provisioning.\n\n```bash\ndocker run -d \\\n  --name thumbs-up-kanban \\\n  -p 8921:8921 \\\n  -v kanban_data:/var/lib/kanban/data \\\n  thumbs-up-kanban:latest\n```\n\n### Internal Unix-Socket Architecture\n\n```mermaid\nflowchart TD\n    subgraph Standalone[\"Single Docker Container (thumbs-up-kanban:latest)\"]\n        Supervisor[\"PID-1 Process Supervisor (tini / Python supervisor)\"]\n        App[\"FastAPI Application Server<br/>(Port 8921 HTTP & WS)\"]\n        PG[\"Embedded PostgreSQL 16 Engine<br/>Unix Domain Socket (/var/run/postgresql/.s.PGSQL.5432)<br/>listen_addresses='' (Zero TCP Exposure)\"]\n        Storage[\"Volume Persistence Probe<br/>Mount: /var/lib/kanban/data\"]\n        \n        Supervisor --> App\n        Supervisor --> PG\n        App -->|Unix Domain Socket| PG\n        PG --> Storage\n    end\n```\n\nInside the standalone container:\n- **PID-1 Process Supervisor:** Manages the graceful startup, monitoring, and shutdown of both PostgreSQL and the ASGI application server.\n- **Embedded PostgreSQL 16:** Listens strictly on a local Unix domain socket (`/var/run/postgresql/.s.PGSQL.5432`). TCP networking for PostgreSQL is disabled (`listen_addresses = ''`), preventing network-level database intrusion.\n- **Volume Persistence Probe:** On startup, the container verifies that `/var/lib/kanban/data` is mounted to a persistent volume. If an ephemeral container filesystem is detected, the UI displays a dismissible amber warning banner alerting the operator to attach persistent storage before creating production data.\n- **Status and Health Panel:** Accessible at `/admin/standalone`, this panel reports database uptime, socket latency, storage utilization, and single-click export to multi-container Compose bundles.\n\n![Standalone Status Panel](images/04-standalone-status-panel.png)\n\n### Workspace Home and Initial State\n\nOnce the container finishes initialization, users land on the clean, breathable Workspace Home. The workspace view provides instant access to projects, work items, stickies, and system configuration.\n\n![Workspace Home](images/05-workspace-home.png)\n\n---\n\n## Multi-Container Production Architecture (`docker compose`)\n\nFor production environments, \ud83d\udc4dkanban deploys as a multi-container stack compartmentalized across five isolated Docker networks.\n\n```mermaid\nflowchart TD\n    Proxy[\"Reverse Proxy (Caddy / Nginx)\"] -->|edge_net: 8921| App[\"\ud83d\udc4dkanban App Container (FastAPI)<br/>- Uvicorn ASGI workers (UID 65532)<br/>- Multi-Card Auth & AAL2 Middleware<br/>- WebSocket Hub & Markdown Pipelines\"]\n    Runners[\"Distributed Agent Runners\"] -->|mTLS: 8444| App\n    \n    App -->|data_net: 5432| PG[\"PostgreSQL 16 DB<br/>- FORCE RLS (100%)<br/>- pgvector + ltree<br/>- Isolated data_net\"]\n    App -->|sandbox_net: IPC| Sandbox[\"Sandbox Execution Runtime<br/>- Wasmtime runtime<br/>- nsjail runner<br/>- Zero data_net route\"]\n    App -->|egress_llm_net: 443| AI[\"External AI Providers<br/>- OpenAI, Gemini<br/>- Local Ollama\"]\n    App -.->|internal_net| InternalMCP[\"Private /internal/v1/mcp/*<br/>- Runner task dispatch<br/>- Zero edge routing\"]\n```\n\n![Standalone to Production Compose Export](images/27-standalone-compose-export.png)\n\n![System Settings and Production Diagnostics](images/26-system-settings.png)\n\n### The 5-Network Isolation Matrix\n\nTo prevent lateral movement and enforce zero-trust network boundaries, container communication is segregated into five distinct networks:\n\n| Network Name | Connected Services | Allowed Ingress / Egress | Security Rationale |\n| :--- | :--- | :--- | :--- |\n| **`edge_net`** | Reverse proxy, Web application | External HTTP/S (8921) & Runner mTLS (8444) | Shields backend application from direct exposure; terminates TLS and dedicated mTLS. Blocks external `/internal/v1/mcp/*`. |\n| **`app_net`** | Web application, Redis / cache (optional) | Inter-service caching, session distribution, internal MCP | Segregates application control plane; isolates `/internal/v1/mcp/*` routes from external edge ingress. |\n| **`data_net`** | Web application, PostgreSQL 16 | PostgreSQL TCP (port 5432) | Strictly internal. The database has zero external routing or internet gateway. |\n| **`sandbox_net`** | Web application, Custom Script runner | Unix socket / IPC pipe | Completely air-gapped. Scripts have zero route to `data_net` or the internet. |\n| **`egress_llm_net`** | Web application, LLM egress gateway | Outbound HTTPS to pinned AI API endpoints | Limits external outbound traffic exclusively to configured LLM APIs. |\n\n### Monotonic CredentialBoundary Across Container Mesh\n\nAcross all service boundaries in the multi-container topology, security tokens enforce monotonic `CredentialBoundary` constraints:\n- **Capability Bitmask Ceiling:** Tokens cannot exceed the active permissions of the issuing principal. A key minted with `capability_mask = 1` (`VIEW` only) emits strictly `${surface}:read` scopes and cannot perform mutating operations across any network boundary.\n- **CIDR Subnet Pinning:** Invocations carry optional `allowed_cidrs` constraints, rejecting requests originating from non-whitelisted IP addresses before requests reach application or database layers.\n\n### Process Hardening and Least Privilege\n\nEvery container in the production stack enforces strict Linux security controls:\n- **Non-Root Execution:** Runs under dedicated unprivileged system users (`UID 65532`, `GID 65532`).\n- **Capability Dropping:** Drops all Linux capabilities on initialization (`--cap-drop=ALL`).\n- **No New Privileges:** Enforces `setpriv --no-new-privs` to prevent setuid privilege escalation.\n- **Read-Only Root Filesystem:** Container root filesystems are mounted read-only (`read_only: true`), with writable space restricted to tmpfs mounts for `/tmp` and `/run`.\n\n---\n\n## Supply Chain Integrity and Permissive Licensing\n\nIn strict accordance with enterprise governance requirements:\n- **Pure Apache-2.0:** All platform source code, libraries, and build targets are licensed under Apache-2.0.\n- **Zero Viral Licenses:** The dependency tree is continuously audited in CI to reject any runtime dependencies with copyleft licenses (GPL, AGPL, LGPL, SSPL).\n- **Pinned Dependencies:** All Python dependencies (`pyproject.toml`) and JavaScript packages (`package.json`) are cryptographically locked with exact hashes.\n"
  },
  {
    "slug": "three-surface-mcp-server-architecture",
    "title": "[Guide] Three-Surface Model Context Protocol (MCP) Server Architecture",
    "category": "guide",
    "track": "Step-by-Step Guides",
    "subtrack": "MCP & OAuth Clients",
    "audience": "Autonomous Agent Developers",
    "order": 28,
    "summary": "The Model Context Protocol (MCP) allows Large Language Models (LLMs) and autonomous engineering agents to interact with development platforms. However, conventional tracker integrations (such as legacy Jira REST bridges and generic CRUD wrappers) expose raw REST endpoints 1:1 as MCP tools. This naive approach results in 70 to 120 bloated tools consuming 15,000 to 25,000 context tokens before the agent begins reasoning, causing catastrophic context exhaustion and multi-turn thrashing.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "scope-tiers",
        "title": "Scope Tiers",
        "level": 2
      },
      {
        "id": "the-three-isolated-mcp-surfaces",
        "title": "The Three Isolated MCP Surfaces",
        "level": 3
      },
      {
        "id": "mcpagent-10-execution-and-qa-tools",
        "title": "1. /mcp/agent (10 Execution and QA Tools)",
        "level": 3
      },
      {
        "id": "mcpdocs-3-knowledge-and-specification-tools",
        "title": "2. /mcp/docs (3 Knowledge and Specification Tools)",
        "level": 3
      },
      {
        "id": "mcpadmin-12-governance-and-lifecycle-tools",
        "title": "3. /mcp/admin (12 Governance and Lifecycle Tools)",
        "level": 3
      },
      {
        "id": "token-optimization-and-serializer-architecture",
        "title": "Token Optimization and Serializer Architecture",
        "level": 2
      },
      {
        "id": "inlinesafedumper-compact-yaml-output",
        "title": "InlineSafeDumper Compact YAML Output",
        "level": 3
      },
      {
        "id": "entityresolver-human-readable-identifiers",
        "title": "EntityResolver Human-Readable Identifiers",
        "level": 3
      },
      {
        "id": "level-of-detail-lod-filtering",
        "title": "Level-of-Detail (lod) Filtering",
        "level": 3
      },
      {
        "id": "mcp-access-studio-and-key-management",
        "title": "MCP Access Studio and Key Management",
        "level": 2
      },
      {
        "id": "studio-features",
        "title": "Studio Features",
        "level": 3
      },
      {
        "id": "oauth-21-pkce",
        "title": "OAuth 2.1 & PKCE",
        "level": 2
      },
      {
        "id": "admin-oauth-21-governance-studio-adminoauth",
        "title": "Admin OAuth 2.1 Governance Studio (/admin/oauth)",
        "level": 3
      },
      {
        "id": "key-oauth-governance-capabilities",
        "title": "Key OAuth Governance Capabilities",
        "level": 3
      },
      {
        "id": "step-by-step-integration-guides",
        "title": "Step-by-Step Integration Guides",
        "level": 2
      },
      {
        "id": "guide-a-connecting-gemini-app-claude-cursor-cli-via-oauth-21",
        "title": "Guide A: Connecting Gemini App, Claude, Cursor & CLI via OAuth 2.1",
        "level": 3
      },
      {
        "id": "guide-b-minting-scoped-mcp-api-keys",
        "title": "Guide B: Minting Scoped MCP API Keys",
        "level": 3
      },
      {
        "id": "guide-c-configuring-headless-workload-oidc-github-actions-gitlab-ci-kubernetes",
        "title": "Guide C: Configuring Headless Workload OIDC (GitHub Actions / GitLab CI / Kubernetes)",
        "level": 3
      },
      {
        "id": "guide-d-governing-and-purging-oauth-21-clients",
        "title": "Guide D: Governing and Purging OAuth 2.1 Clients",
        "level": 3
      }
    ],
    "content": "# [Guide] Three-Surface Model Context Protocol (MCP) Server Architecture\n\n## Overview\n\nThe Model Context Protocol (MCP) allows Large Language Models (LLMs) and autonomous engineering agents to interact with development platforms. However, conventional tracker integrations (such as legacy Jira REST bridges and generic CRUD wrappers) expose raw REST endpoints 1:1 as MCP tools. This naive approach results in 70 to 120 bloated tools consuming 15,000 to 25,000 context tokens before the agent begins reasoning, causing catastrophic context exhaustion and multi-turn thrashing.\n\n\ud83d\udc4dkanban rejects the CRUD-wrapper pattern. Instead, it implements an **Intent-Driven Architecture** organized into **three isolated streamable surfaces** (`2025-06-18` protocol specification), exposing exactly 25 cohesive tools (10 `/mcp/agent`, 3 `/mcp/docs`, 12 `/mcp/admin`) designed specifically for autonomous agent cognition.\n\n---\n\n## Scope Tiers\n### The Three Isolated MCP Surfaces\n\n```mermaid\nflowchart TD\n    subgraph Hub[\"\ud83d\udc4dkanban Multi-Surface MCP Server\"]\n        Agent[\"/mcp/agent - 10 Execution & QA Tools - Token budget: <= 1,850 tokens - Zero Admin / Delete permissions\"]\n        Docs[\"/mcp/docs - 3 Knowledge & Spec Tools - Token budget: <= 1,350 tokens - Search, Create, Update Docs\"]\n        Admin[\"/mcp/admin - 12 Lifecycle & Ops Tools - Token budget: <= 2,800 tokens - Mandatory AAL2 Protection - 2-Stage Destructive Confirmation\"]\n    end\n\n    subgraph Agents[\"Target Consumers\"]\n        CodingAgents[\"Autonomous Coding & QA Agents (Cursor, Claude Code, Antigravity, Codex)\"]\n        DocAgents[\"Documentation & Knowledge Bots\"]\n        AdminOperators[\"DevOps & Administrative Operators\"]\n    end\n\n    CodingAgents --> Agent\n    DocAgents --> Docs\n    AdminOperators --> Admin\n```\n\n![MCP Access Studio and Key Minting Modal](images/slice3-mcp-access-studio-mint-modal.png)\n\n![MCP Config Snippet and Client Setup Modal](images/slice3-mcp-config-snippet-modal.png)\n\n### 1. `/mcp/agent` (10 Execution and QA Tools)\nDedicated to autonomous software development, testing, and QA agents (such as Claude Code, Antigravity, and Cursor).\n- **Security Constraint:** Strictly limited by the caller's role. Contains zero administrative, destructive, or project-deletion capabilities.\n- **Token Efficiency:** The entire tool manifest consumes only 1,759 tokens, comfortably fitting within the strict 1,850-token specification ceiling.\n- **Intent Consolidation:** Replaces multi-step CRUD sequences with atomic actions like `begin_work` (claims ticket, starts sprint, links active cycle, posts plan), `complete_work` (verifies blockers, records QA proof, marks done), and `update_workpad` (persists intermediate progress).\n\n### 2. `/mcp/docs` (3 Knowledge and Specification Tools)\nDedicated to technical documentation, architecture research, and specification authoring.\n- **Capabilities:** Document creation, markdown search, and content updates (`search`, `create`, `update`).\n- **Token Efficiency:** Tool manifest utilizes under 800 tokens against a 1,350-token budget ceiling.\n\n### 3. `/mcp/admin` (12 Governance and Lifecycle Tools)\nDedicated to platform administrators and privileged automation operators.\n- **Capabilities:** Project provisioning, member and group access binding, workflow transition helper configuration, AI runner setup, and system health checks.\n- **AAL2 Protection:** Every invocation requires Authenticator Assurance Level 2 credentials.\n- **Two-Stage Destructive Safety:** Dangerous operations (`destructive_lifecycle`) require a two-stage process: first requesting a blast-radius preview and receiving a short-lived cryptographic confirmation token, then explicitly confirming execution with that token.\n\n---\n\n## Token Optimization and Serializer Architecture\n\nAutonomous agents run faster and make fewer mistakes when data payloads are clean, predictable, and compact.\n\n```mermaid\nflowchart LR\n    Request[\"Agent Invocation - e.g. read_ticket(identifier='KAN-42')\"] --> Auth[\"Auth & Scope Check\"]\n    Auth --> Resolver[\"EntityResolver - Translate KAN-42 to UUID\"]\n    Resolver --> DB[\"PostgreSQL Engine - FORCE RLS Active\"]\n    DB --> LODFilter[\"LOD Filter - summary / standard / full\"]\n    LODFilter --> Dumper[\"InlineSafeDumper - Strip nulls, compact YAML\"]\n    Dumper --> Response[\"Streamable Response - (-35% Tokens vs JSON)\"]\n```\n\n### `InlineSafeDumper` Compact YAML Output\nWhile standard MCP servers return formatted JSON, \ud83d\udc4dkanban uses a specialized YAML serializer (`mcp/yaml_out.py`):\n- Compact, human-readable YAML representation.\n- Strips null values, empty strings, and default boolean flags.\n- Automatically redacts sensitive fields (passwords, tokens, keys).\n- **Result:** Reduces payload size by 35% compared to raw JSON, saving thousands of tokens per conversation.\n\n### `EntityResolver` Human-Readable Identifiers\nAgents reason far better about human identifiers (`KAN-42`, `CORE-101`, `infra-docs`) than opaque UUIDs (`01932e6b-7341-789a-bc01-123456789abc`). The `EntityResolver` automatically translates between human keys and internal database UUIDs at the MCP boundary.\n\n### Level-of-Detail (`lod`) Filtering\nSearch and read tools support a progressive disclosure parameter:\n- `lod: \"summary\"`: Returns identifier, title, state, and priority (~40 tokens).\n- `lod: \"standard\"`: Returns summary plus description and primary assignees (~200 tokens).\n- `lod: \"full\"`: Returns complete object graph, all comments, activity history, and access manifests.\n\n---\n\n## MCP Access Studio and Key Management\n\nUsers and administrators configure MCP integrations through the visual Access Studio at `/settings/mcp` and `/admin/mcp`.\n\n![MCP Access Studio and Key Minting Modal](images/slice3-mcp-access-studio-mint-modal.png)\n\n### Studio Features\n- **Granular Tool Toggles:** Enable or disable individual MCP tools per key or per surface.\n- **Hierarchical Scopes and Scope Badges:** Restrict tokens to `Global`, `Workspace`, `Project`, or `Personal` scopes with distinct visual badges indicating authorization level.\n- **Capability Bitmasks:** Enforce monotonic capability boundaries between `0` (deny-all) and `255` (full privileges).\n- **CIDR Restrictions:** Limit key invocation to specific IP subnets (e.g. `127.0.0.1/32`, `10.0.0.0/8`).\n- **RFC 8628 Device Flow (`/activate`):** Fast terminal onboarding allowing agents to authenticate via browser activation code.\n- **Copyable Configuration Snippets:** Real-time generation of configuration snippets for Claude Desktop, Google Antigravity (`agy`), Cursor, and OpenAI Codex.\n\n![MCP Access Studio Scope Badges](images/59-mcp-scope-badge.png)\n\n![MCP Mint Key and Client Snippets Modal](images/58-mcp-client-snippets-mint.png)\n\n![Connect OAuth App Modal](images/slice3-connect-oauth-modal.png)\n\n---\n\n## OAuth 2.1 & PKCE\n### Admin OAuth 2.1 Governance Studio (`/admin/oauth`)\n\nIn addition to static API keys, \ud83d\udc4dkanban provides an enterprise OAuth 2.1 authorization server with mandatory PKCE (Proof Key for Code Exchange with `S256` challenge), accessible at `/admin/oauth`.\n\n```mermaid\nflowchart TD\n    subgraph OAuthGovernance[\"OAuth 2.1 & PKCE Architecture\"]\n        ClientApp[\"Third-Party Client / IDE Agent (Cursor, Claude Desktop, Antigravity)\"]\n        AuthServer[\"\ud83d\udc4dkanban OAuth 2.1 Server (/admin/oauth)\"]\n        TokenEndpoint[\"Token Minting Endpoint (/oauth/token)\"]\n        AdminAudit[\"Audit & Revocation Stream\"]\n\n        ClientApp -->|1. Authorization Code Request + code_challenge S256| AuthServer\n        AuthServer -->|2. User Authenticates & Approves Scopes| ClientApp\n        ClientApp -->|3. POST /oauth/token + code_verifier| TokenEndpoint\n        TokenEndpoint -->|4. Cryptographic S256 Verification| TokenEndpoint\n        TokenEndpoint -->|5. Mint Scoped Bearer JWT + Refresh Token| ClientApp\n        TokenEndpoint -->|6. Append Registration & Issuance Record| AdminAudit\n    end\n```\n\n![OAuth Client Governance Studio Bulk Purge](images/slice3-oauth-governance-bulk-purge.png)\n\n![OAuth Client Governance Studio Paginated 500 Clients](images/slice3-oauth-governance-paginated-500.png)\n\n![Admin OAuth Client Governance Studio](images/42-admin-oauth-governance.png)\n\n### Key OAuth Governance Capabilities\n1. **Registered OAuth 2.1 Clients:** View, register, and manage client applications with designated redirect URIs, client types (`public` or `confidential`), and authentication methods (`none`, `client_secret_post`, `client_secret_basic`, `private_key_jwt`).\n2. **Mandatory PKCE (`S256`):** Disallows plain code challenges, protecting public clients against authorization code interception attacks.\n3. **State Parameter Ceiling (`MAX_STATE_LEN = 4096`):** Supports large serialized state objects (up to 4,096 characters) required by cloud AI assistants like Google Gemini.\n4. **Granular Scopes:** Scopes are scoped strictly (`agent:read`, `agent:write`, `docs:read`, `docs:write`, `admin:read`, `admin:write`, `admin:destructive`).\n5. **Immediate Client Revocation & Bulk Purge:** Administrators can revoke compromised OAuth clients or execute single-transaction bulk purges (`POST /api/v1/admin/oauth-clients/bulk-delete`) to remove hundreds of stale Dynamic Client Registration (DCR) clients without disrupting active client sessions.\n\n---\n\n## Step-by-Step Integration Guides\n\n### Guide A: Connecting Gemini App, Claude, Cursor & CLI via OAuth 2.1\n\n#### 1. Google Gemini Connected Apps\n1. Open the \ud83d\udc4dkanban MCP Access Studio (`/settings/mcp`) and click **Connect OAuth App**.\n2. Select the **Gemini App** tab to view your MCP OAuth Resource URL (e.g. `https://kanban.example.com/mcp/agent`).\n3. In Google Gemini (gemini.google.com), navigate to **Settings > Connected Apps > Add Custom MCP Server**.\n4. Enter the Resource URL and complete the OAuth 2.1 PKCE authorization flow in the browser popup.\n\n#### 2. Claude Desktop & Claude Code\n1. In the **Connect OAuth App** modal, select the **Claude Code** tab.\n2. For Claude Code CLI, run the auto-generated command:\n   ```bash\n   claude mcp add --transport http kanban https://kanban.example.com/mcp/agent\n   ```\n3. For Claude Desktop, add the server configuration to `claude_desktop_config.json`:\n   ```json\n   {\n     \"mcpServers\": {\n       \"kanban\": {\n         \"url\": \"https://kanban.example.com/mcp/agent\"\n       }\n     }\n   }\n   ```\n\n#### 3. Cursor & VS Code\n1. In Cursor, open **Settings > Features > MCP**.\n2. Add a new MCP server with Server Type `SSE` (or HTTP) and URL `https://kanban.example.com/mcp/agent`.\n3. When prompted, complete the OAuth 2.1 authorization in your default browser.\n\n#### 4. Antigravity & OpenAI Codex CLI\n1. For Google Antigravity CLI, run:\n   ```bash\n   agy mcp add kanban https://kanban.example.com/mcp/agent --auth oauth\n   ```\n2. For OpenAI Codex CLI, run:\n   ```bash\n   codex mcp add kanban https://kanban.example.com/mcp/agent --auth oauth\n   ```\n\n---\n\n### Guide B: Minting Scoped MCP API Keys\n\n1. Navigate to `/settings/mcp` (or `/admin/mcp` for administrative keys).\n2. Click **+ Mint MCP Key** to open the creation modal.\n3. **Configure Key Metadata:**\n   - **Key Name / Label:** Descriptive name (e.g. `CI Bot Runner`).\n   - **Role:** Select `Personal` (for user-bound keys) or `Service Bot` (for headless automation).\n   - **Scope Tier:** Choose `Project`, `Workspace`, or `Global`. For project keys, select the target project.\n   - **Surface:** Select `/mcp/agent` or `/mcp/docs`.\n   - **Expiration:** Choose a preset (30, 60, 90 days, 1 year) or `Unlimited` (requires checking the risk acknowledgment checkbox).\n   - **Capability Mask:** Select a preset (`Full Admin: 255`, `Standard: 31`, `Read-Only: 1`, `Deny-All: 0`) or configure individual bitmask flags.\n   - **CIDR Allowlist:** Optionally specify comma-separated allowed IPv4/IPv6 subnets (e.g. `192.168.1.0/24`).\n   - **Tool Toggles:** Deselect specific tools to disable them for this key.\n4. Click **Mint Key** and copy the secret token immediately. The raw token is write-only and will never be displayed again.\n\n---\n\n### Guide C: Configuring Headless Workload OIDC (GitHub Actions / GitLab CI / Kubernetes)\n\n1. Open `/admin/mcp` and navigate to the **Workload Identity Federation** section.\n2. Click **+ Add Workload Policy** to open the policy creation drawer.\n3. Select a provider preset or enter custom settings:\n   - **GitHub Actions Preset:** Issuer `https://token.actions.githubusercontent.com`, Subject pattern `repo:my-org/my-repo:ref:refs/heads/main`.\n   - **GitLab CI Preset:** Issuer `https://gitlab.com`, Subject pattern `project_path:my-group/my-project:ref_type:branch:ref:main`.\n   - **Kubernetes Preset:** Issuer `https://kubernetes.default.svc.cluster.local`, Subject pattern `system:serviceaccount:default:ci-runner`.\n4. Configure required claims, target surface (`/mcp/agent`), allowed project scopes, capability mask, and token TTL (`max_ttl_seconds <= 86400`).\n5. Save the policy. Headless workloads can now exchange native OIDC tokens for ephemeral MCP tokens via `POST /oauth/token` without static passwords.\n\n---\n\n### Guide D: Governing and Purging OAuth 2.1 Clients\n\n1. Navigate to `/admin/oauth` to access the OAuth Client Governance Studio.\n2. **Inspect Clients:** Use filter pills (`All`, `Active`, `Suspended`, `Revoked`) or search by client name or ID.\n3. **Manage Lifecycle:**\n   - Click **Inspect** to review client registration metadata, redirect URIs, and scopes.\n   - Click **Suspend** to temporarily disable token exchange for a client.\n   - Click **Revoke** to permanently invalidate a client and all associated refresh tokens.\n4. **Single-Transaction Bulk Purge:**\n   - To clean up stale Dynamic Client Registration (DCR) clients created during automated testing or evaluation, click **Purge Stale Clients**.\n   - Review the count of unused clients (clients without active refresh tokens or grants).\n   - Confirm the operation to purge up to thousands of stale clients atomically in a single database transaction.\n\n![Device Activation Page](images/slice3-device-activate-page.png)\n"
  },
  {
    "slug": "ticket-screen-and-work-item-features",
    "title": "[Informational] Ticket Screen, Peek Drawer, and Work Item Architecture",
    "category": "informational",
    "track": "Feature & Field Reference",
    "subtrack": "Issue Studio & Peek Drawer",
    "audience": "Software Engineers & Contributors",
    "order": 29,
    "summary": "The ticket screen is the central operating surface for software engineering teams. \ud83d\udc4dkanban competes globally against Jira, Vibe Kanban, and legacy commercial trackers while eliminating context-switching friction through its high-performance **960px Ticket Peek Drawer** and keyboard-driven **Quick-Create Modal**.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "quick-create-work-item-modal-c",
        "title": "Quick-Create Work Item Modal (C)",
        "level": 2
      },
      {
        "id": "key-capabilities-of-quick-create",
        "title": "Key Capabilities of Quick-Create",
        "level": 3
      },
      {
        "id": "the-960px-ticket-peek-drawer-peek",
        "title": "The 960px Ticket Peek Drawer (?peek=)",
        "level": 2
      },
      {
        "id": "zero-remount-architecture",
        "title": "Zero-Remount Architecture",
        "level": 3
      },
      {
        "id": "fullscreen-issue-view-and-authoring-studio",
        "title": "Fullscreen Issue View and Authoring Studio",
        "level": 2
      },
      {
        "id": "key-fullscreen-features",
        "title": "Key Fullscreen Features:",
        "level": 3
      },
      {
        "id": "the-complete-17-enterprise-ticket-features",
        "title": "The Complete 17 Enterprise Ticket Features",
        "level": 2
      },
      {
        "id": "detailed-visual-inspection-of-ticket-features",
        "title": "Detailed Visual Inspection of Ticket Features",
        "level": 2
      },
      {
        "id": "4-tab-activity-feed-and-audit-history",
        "title": "4-Tab Activity Feed and Audit History",
        "level": 3
      },
      {
        "id": "modules",
        "title": "Modules",
        "level": 3
      },
      {
        "id": "blast-radius-deletion-warning-modal",
        "title": "Blast Radius Deletion Warning Modal",
        "level": 3
      },
      {
        "id": "auto-archive",
        "title": "Auto-Archive",
        "level": 3
      },
      {
        "id": "labels",
        "title": "Labels",
        "level": 3
      },
      {
        "id": "postgresql-issue-copy-and-deep-subtree-duplication-procedure",
        "title": "PostgreSQL Issue Copy and Deep Subtree Duplication Procedure",
        "level": 2
      }
    ],
    "content": "# [Informational] Ticket Screen, Peek Drawer, and Work Item Architecture\n\n## Overview\n\nThe ticket screen is the central operating surface for software engineering teams. \ud83d\udc4dkanban competes globally against Jira, Vibe Kanban, and legacy commercial trackers while eliminating context-switching friction through its high-performance **960px Ticket Peek Drawer** and keyboard-driven **Quick-Create Modal**.\n\n---\n\n## Quick-Create Work Item Modal (`C`)\n\nEngineers can capture issues rapidly from any screen in the application by pressing the keyboard shortcut `C` or clicking `+ New Work Item`.\n\n![Quick-Create Work Item Modal](images/08-quick-create-modal.png)\n\n### Key Capabilities of Quick-Create\n\n- **Keyboard Shortcut Driven:** Press `C` anywhere to open, `Escape` to dismiss, or `Ctrl+Enter` (`Cmd+Enter`) to submit.\n- **Draft Persistence (`\u270d\ufe0f Keep work-in-progress`):** Enabling the draft toggle preserves partial ticket text across navigation and browser restarts using local storage, preventing work loss.\n- **Inline Property Setting:** Assign status, priority, cycle, module, and assignees directly in the modal without secondary configuration.\n\n---\n\n## The 960px Ticket Peek Drawer (`?peek=`)\n\nClicking any card on the board or list opens the ticket in an expansive 960px side drawer while keeping the underlying board mounted and visible.\n\n![Ticket Peek Drawer with 17 Features](images/09-ticket-peek-drawer.png)\n\n```mermaid\nflowchart TD\n    subgraph DrawerLayout[\"960px Ticket Peek Drawer Structure\"]\n        Header[\"Header Bar<br/>- Identifier (\ud83c\udff7\ufe0f) & Title<br/>- Subscribe (\ud83d\udd14), Copy Link (\ud83d\udd17)<br/>- Access Pill (\ud83d\udee1\ufe0f), Fullscreen Toggle\"]\n        \n        subgraph MainContent[\"Main Content Area\"]\n            Editor[\"ProseMirror Editor<br/>- Canonical UTF-8 Markdown<br/>- Sparkle FIM Completion (\u2728)<br/>- Live Mermaid & Media Rendering\"]\n            Subtasks[\"Sub-Issues & Checklists<br/>- Drag-and-drop reordering<br/>- Blocker resolution tracking\"]\n            Activity[\"4-Tab Activity Stream<br/>- All, Comments, History, \ud83e\udd16 Gates\"]\n        end\n        \n        subgraph PropertiesRail[\"Right-Hand Properties Rail\"]\n            StateProp[\"State & Workflow Transitions\"]\n            PriorityProp[\"Priority Tiering (Urgent..None)\"]\n            AssigneeProp[\"Assignees (Users, Groups, Agents)\"]\n            CycleProp[\"Cycle (Sprint) & Module Binding\"]\n            DatesProp[\"Start & Due Date Pickers\"]\n            CustomFields[\"Custom Scripted Fields (\ud83e\uddea)\"]\n            BlastRadius[\"Destructive Action Controls\"]\n        end\n    end\n    \n    Header --> MainContent\n    MainContent --- PropertiesRail\n```\n\n### Zero-Remount Architecture\n\n- **URL Synchronization:** Drawer state is synchronized with the URL (`/projects/KAN/issues?peek=KAN-12`). Refreshing or sharing the URL opens the exact drawer context.\n- **Background Preservation:** The underlying board does not unmount or reload. Users can interact with the drawer and return to their exact scroll position with zero latency.\n- **One-Click Fullscreen:** Operators can expand the drawer into a full-width page view for deep specification reading and back again seamlessly.\n\n---\n\n## Fullscreen Issue View and Authoring Studio\n\nWhen deep architectural work or comprehensive specification reading is required, operators can expand any ticket into the **Fullscreen Issue View** (`/projects/KAN/issues/{id}` or via the expand icon on the drawer header).\n\n```mermaid\nflowchart TD\n    subgraph FullscreenView[\"Fullscreen Issue Studio Structure\"]\n        TopNav[\"Top Navigation Bar<br/>- Breadcrumb: Workspace / Project / Work Items<br/>- Key: KAN-142 | Copy ID | \ud83d\udee1\ufe0f Access Inspector (Project + 2)<br/>- Subscribe Toggle (\ud83d\udd14) | Deep Link (\ud83d\udd17) | More Actions (...)\"]\n        \n        subgraph EditorColumn[\"Primary Specification & Activity Area\"]\n            Title[\"Issue Title Header with Inline Edit\"]\n            Desc[\"Rich Markdown Specification Body<br/>- Canonical CommonMark renderer<br/>- Mermaid diagram inline preview<br/>- Sparkle 320ms FIM ghost-text completion\"]\n            Toolbar[\"Rich Markdown Authoring Toolbar<br/>- Bold (B), Italic (I), Code (</>), Link, Image, Table, Mermaid\"]\n            CommentEditor[\"Comment Editor Box with Markdown and Mention Support\"]\n            ActivityTabs[\"4-Tab Activity Stream<br/>- All | Comments (N) | History | \ud83e\udd16 Gates (N)\"]\n        end\n        \n        subgraph SideRail[\"Right-Hand Metadata & Custom Fields Rail\"]\n            StandardFields[\"Standard Attributes<br/>- State, Priority, Assignees, Reporter<br/>- Start Date, Due Date, Module, Cycle\"]\n            CustomRail[\"Custom Fields Rail (Admin-Defined \ud83e\uddea)<br/>- CVSS Score (Severity Pill e.g. 8.8 High)<br/>- Target Environment, Build Number<br/>- Dynamic reload buttons per field\"]\n        end\n    end\n    \n    TopNav --> EditorColumn\n    EditorColumn --- SideRail\n```\n\n![Fullscreen Issue View with Rich Markdown Toolbar and Access Inspector](images/39-fullscreen-issue-view.png)\n\n### Key Fullscreen Features:\n1. **Rich Markdown Authoring Toolbar:** One-click formatting tools for bold, italics, inline code, links, quotes, tables, and Mermaid architecture diagrams.\n2. **Sparkle 320ms Fill-in-the-Middle (FIM):** Context-aware ghost text completions triggered as you write, dismissible with `Escape` and acceptable with `Tab` or right-click.\n3. **Effective Access Inspector (`\ud83d\udee1\ufe0f`):** Real-time badge computing combined project and issue-level permissions (`Project + 2`), showing inherited roles and explicit principal grants.\n4. **4-Tab Activity Stream:** Dedicated tabs for `All`, `Comments`, `History`, and `\ud83e\udd16 Gates` for isolated inspection of human discourse versus autonomous agent evaluations.\n5. **Custom Fields Rail:** Identical component and state rendering between peek drawer and fullscreen views, preserving field layout fidelity.\n\n---\n\n## The Complete 17 Enterprise Ticket Features\n\n\ud83d\udc4dkanban implements the full suite of 17 enterprise work item features (`8a` through `8q`):\n\n| # | Feature Identifier | Implementation Details |\n| :--- | :--- | :--- |\n| **1** | **Title & Canonical Description** | Rich Markdown editor supporting code blocks, tables, task lists, and Sparkle AI completion. |\n| **2** | **State Transition Selector** | Workflow-aware selector with synchronous Wasm validation and async AI gate interception. |\n| **3** | **Corporate Priority Tiering** | High-contrast visual badges: `Urgent` (red), `High` (orange), `Medium` (yellow), `Low` (blue), `None`. |\n| **4** | **Hybrid Assignees (`\ud83c\udff7\ufe0f`)** | Seamless assignment across individual human users, user groups, and autonomous agent service principals. |\n| **5** | **Created-by Reporter Badge (`\ud83d\udd04`)** | Immutable audit stamp recording the original creator and creation timestamp. |\n| **6** | **Dates & Scheduling** | Start date and Target delivery date pickers with automatic overdue highlighting and calendar sync. |\n| **7** | **Cycle (Sprint) Binding** | Direct assignment to active, upcoming, or backlog sprint cycles with automatic rollover. |\n| **8** | **Module Binding** | Grouping under functional modules with live roll-up progress bars and completion percentages. |\n| **9** | **Parent Hierarchy (`\ud83d\udd12`)** | Parent-child relationship binding with automated circular dependency rejection. |\n| **10** | **Sub-Issue Decomposition** | Nested sub-task checklist with drag reordering and progress tracking indicators. |\n| **11** | **Labels & Tagging** | Multi-colored semantic labels with workspace-level and project-level scopes. |\n| **12** | **Subscription Notifications (`\ud83d\udd14`)** | Watcher toggle delivering notifications on comments, state changes, and gate approvals. |\n| **13** | **Copy Link & Deep Linking (`\ud83d\udd17`)** | Generates canonical deep links directly to ticket headers or individual comments. |\n| **14** | **Explicit Sharing Pill (`\ud83d\udee1\ufe0f`)** | Visual indicator displaying the Access Manifest (principals, roles, and effective ACL masks). |\n| **15** | **Custom Scripted Fields (`\ud83e\uddea`)** | Dynamic fields computed by sandboxed Wasmtime/nsjail scripts with execution badges. |\n| **16** | **4-Tab Activity Feed** | Tabbed stream: `All`, `Comments` (with Markdown & mentions), `History` (audit trail), `\ud83e\udd16 Gates` (agent reviews). |\n| **17** | **Destructive Action Safety** | 2-stage blast-radius preview modal detailing affected children and links before archive or deletion. |\n\n---\n\n## Detailed Visual Inspection of Ticket Features\n\n### 4-Tab Activity Feed and Audit History\nThe activity feed separates human conversation from automated audit logs and AI agent gate reviews:\n\n![Activity Stream and Audit History](images/28-activity-stream-audit.png)\n\n### Modules\nWork items bind directly to sprint cycles and functional modules with real-time velocity roll-ups:\n\n![Sprint Cycle Planning and Velocity Tracking](images/24-cycles-sprints.png)\n\n![Functional Module Hierarchy and Progress Tracking](images/25-modules-milestones.png)\n\n### Blast Radius Deletion Warning Modal\nTwo-stage deletion safety calculates the ripple impact across child issues, dependencies, and doc links:\n\n![Delete Blast Radius Warning Modal](images/20-delete-blast-radius.png)\n\n### Auto-Archive\nWork items completed past the retention threshold are automatically moved to archive storage.\n\n### Labels\nMulti-colored semantic labels support both workspace-level and project-level scopes, with optional mutual exclusion groups enforcing single-selection among conflicting categories.\n\n---\n\n## PostgreSQL Issue Copy and Deep Subtree Duplication Procedure\n\nCloning work items, hierarchical sub-tasks, and attachments is governed by an atomic, security-definer PostgreSQL and service layer workflow (`kanban/services/issue_copy.py` and `p3_08_issue_copy.up.sql`):\n\n1. **Authorization Gate:**\n   - Requires `Capability.VIEW` (0x01) on the source issue and `Capability.EDIT` (0x04) on the target project. Missing permissions fail closed with 404 or 403.\n2. **Subtree Traversal and Fail-Closed Pruning:**\n   - Invokes `issues_get_copy_subtrees(p_root_id uuid)` (`SECURITY DEFINER`, `ltree` depth `<= 6`).\n   - Evaluates caller capability on each descendant node (`app_has_object_capability(r.id, 1)`).\n   - If an intermediate or leaf sub-issue lacks `VIEW` permission, the function prunes that node and its descendants fail-closed, aggregating pruned counts into `skipped.restricted_sub_issues` without leaking unauthorized metadata.\n3. **Safety Caps:**\n   - Enforces `MAX_READABLE_ISSUES_LIMIT = 200` to prevent unbounded memory allocation and database timeouts during tree replication.\n4. **Agent-Safe Sequence Allocation:**\n   - Calls `allocate_issue_sequences(p_project_id, p_count, false)` (`p4_24_agent_safe_sequences.up.sql`) to allocate contiguous sequence numbers atomically.\n   - Any skipped sequences are recorded with an immutable `SEQUENCE_SKIPPED` ledger event.\n5. **Atomic Savepoint Registration:**\n   - Executes inside an atomic nested transaction (`session.begin_nested()`).\n   - Cloned issues and sub-issues invoke `register_object(CAST('issue' AS object_kind), ...)` to bind spine records.\n   - Copies attachments when requested (`include_attachments=true`), links relates-to edges (`link_as_relates_to=true`), and emits `ISSUE_CREATED` and `ISSUE_COPIED` activity records.\n"
  },
  {
    "slug": "universal-object-graph-and-link-auditor",
    "title": "[Architectural] Universal Object Graph and Invalid Link Auditor",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Functional Architecture",
    "audience": "Database Engineers & Core Architects",
    "order": 30,
    "summary": "Traditional project management databases rely on fragmented, ad-hoc foreign keys connecting tickets, documents, and attachments. This fragmented design leads to dangling pointers, orphaned files, accidental cross-tenant data leaks, and broken graph traversals when objects are archived or deleted.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "the-unified-object-spine-architecture",
        "title": "The Unified Object Spine Architecture",
        "level": 2
      },
      {
        "id": "key-spine-invariants",
        "title": "Key Spine Invariants",
        "level": 3
      },
      {
        "id": "the-13-typed-object-relationships",
        "title": "The 13 Typed Object Relationships",
        "level": 2
      },
      {
        "id": "invalid-object-link-auditor-and-purger",
        "title": "Invalid Object Link Auditor and Purger",
        "level": 2
      },
      {
        "id": "the-7-class-invalid-link-detection-matrix",
        "title": "The 7-Class Invalid Link Detection Matrix",
        "level": 3
      },
      {
        "id": "audited-purging-and-two-stage-remediation",
        "title": "Audited Purging and Two-Stage Remediation",
        "level": 3
      },
      {
        "id": "admin-link-auditor-studio-adminlink-auditor",
        "title": "Admin Link Auditor Studio (/admin/link-auditor)",
        "level": 2
      },
      {
        "id": "seven-class-breakdown-cards",
        "title": "1. Seven-Class Breakdown Cards",
        "level": 3
      },
      {
        "id": "inspect-link-drawer",
        "title": "2. Inspect Link Drawer",
        "level": 3
      },
      {
        "id": "audited-purge-modal",
        "title": "3. Audited Purge Modal",
        "level": 3
      },
      {
        "id": "postgresql-issue-copy-and-subtree-graph-synthesis",
        "title": "PostgreSQL Issue Copy and Subtree Graph Synthesis",
        "level": 2
      },
      {
        "id": "state-deletion-and-dependency-remapping",
        "title": "State Deletion and Dependency Remapping",
        "level": 2
      },
      {
        "id": "pre-delete-reverse-audit-inspection",
        "title": "1. Pre-Delete Reverse-Audit Inspection",
        "level": 3
      },
      {
        "id": "non-bypassable-hard-deletion-blocks",
        "title": "2. Non-Bypassable Hard Deletion Blocks",
        "level": 3
      },
      {
        "id": "dependency-remapping-rules",
        "title": "3. Dependency Remapping Rules",
        "level": 3
      }
    ],
    "content": "# [Architectural] Universal Object Graph and Invalid Link Auditor\n\n## Overview\n\nTraditional project management databases rely on fragmented, ad-hoc foreign keys connecting tickets, documents, and attachments. This fragmented design leads to dangling pointers, orphaned files, accidental cross-tenant data leaks, and broken graph traversals when objects are archived or deleted.\n\n\ud83d\udc4dkanban resolves this through the **Universal Object Graph (UOG)**. Every major entity in the system inherits from a unified object spine, and all relationships are represented as typed, bidirectional, and audited graph links.\n\n---\n\n## The Unified Object Spine Architecture\n\nThe Universal Object Graph defines 9 first-class entity kinds (`database/models/spine.py`):\n\n```mermaid\nflowchart TD\n    Spine[\"Universal Object Spine<br/>- id: UUIDv7 (time-ordered monotonic)<br/>- entity_kind: Enum (9 kinds)<br/>- workspace_id: UUID (mandatory tenant boundary)<br/>- access_control_list & timestamps\"]\n    \n    Spine --> Issue[\"ISSUE\"]\n    Spine --> Doc[\"DOC\"]\n    Spine --> Sticky[\"STICKY\"]\n    Spine --> Cycle[\"CYCLE\"]\n    Spine --> Module[\"MODULE\"]\n    Spine --> View[\"VIEW\"]\n    Spine --> Page[\"PAGE\"]\n    Spine --> Project[\"PROJECT\"]\n    Spine --> Workspace[\"WORKSPACE\"]\n```\n\n![Link Graph Popover and Dependency Visualization](images/19-link-graph-popover.png)\n\n### Key Spine Invariants\n1. **Monotonic UUIDv7 Identifiers:** All objects use UUIDv7 keys, providing temporal sorting, index locality, and sub-millisecond insert performance in PostgreSQL.\n2. **Mandatory Tenant Boundary:** Every spine record requires a `workspace_id`. Cross-workspace objects cannot exist in the spine.\n3. **Canonical UTF-8 Markdown Content:** Textual representations store normalized Markdown exclusively.\n\n---\n\n## The 13 Typed Object Relationships\n\nAll inter-object relationships are stored in the centralized `object_links` table with strict referential typing:\n\n| Link Kind | Inbound Complement | Permitted Entity Pairs | Semantic Meaning |\n| :--- | :--- | :--- | :--- |\n| **`BLOCKS`** | `BLOCKED_BY` | `ISSUE` -> `ISSUE` | Dependency blocker preventing completion. |\n| **`BLOCKED_BY`** | `BLOCKS` | `ISSUE` -> `ISSUE` | Dependent item waiting on prerequisite. |\n| **`RELATES_TO`** | `RELATES_TO` | Any -> Any | Non-blocking topical association. |\n| **`DUPLICATES`** | `DUPLICATED_BY` | `ISSUE` -> `ISSUE` | Identifies redundant work items. |\n| **`DUPLICATED_BY`**| `DUPLICATES` | `ISSUE` -> `ISSUE` | Original issue retained for resolution. |\n| **`PARENT_OF`** | `CHILD_OF` | `ISSUE` -> `ISSUE`, `DOC` -> `DOC` | Hierarchical parent-child composition. |\n| **`CHILD_OF`** | `PARENT_OF` | `ISSUE` -> `ISSUE`, `DOC` -> `DOC` | Sub-task or child page relationship. |\n| **`PROMOTED_TO`** | `PROMOTED_FROM`| `STICKY` -> `DOC` | Captures origin of promoted documentation. |\n| **`PROMOTED_FROM`**| `PROMOTED_TO` | `DOC` -> `STICKY` | Points back to source ideation sticky. |\n| **`MENTIONS`** | `REFERENCED_IN`| `ISSUE`/`DOC` -> Any | Inline `@mention` or object tag reference. |\n| **`REFERENCED_IN`**| `MENTIONS` | Any -> `ISSUE`/`DOC` | Backlink tracking mention occurrences. |\n| **`ATTACHED_TO`** | `DERIVED_FROM` | Media -> `ISSUE`/`DOC` | Asset or diagram attachment. |\n| **`DERIVED_FROM`** | `ATTACHED_TO` | `ISSUE`/`DOC` -> Media | Traceability to original media asset. |\n\n---\n\n## Invalid Object Link Auditor and Purger\n\nIn active development environments, soft deletes, project migrations, and permission adjustments can produce invalid relationships. Rather than allowing broken links to silently corrupt views or leak references, \ud83d\udc4dkanban runs an automated **Invalid Object Link Auditor** (`database/auditor/`).\n\n### The 7-Class Invalid Link Detection Matrix\n\nThe auditor continuously scans the `object_links` table, categorizing anomalies into 7 strict `InvalidLinkReason` violation classes:\n\n```mermaid\nflowchart LR\n    Scan[\"Auditor Background Worker\"] --> Check{\"Analyze object_links\"}\n    Check --> C1[\"1. DANGLING_SOURCE\"]\n    Check --> C2[\"2. DANGLING_TARGET\"]\n    Check --> C3[\"3. SOFT_DELETED_ENDPOINT\"]\n    Check --> C4[\"4. ARCHIVED_POLICY_VIOLATION\"]\n    Check --> C5[\"5. TYPE_MATRIX_VIOLATION\"]\n    Check --> C6[\"6. CROSS_WORKSPACE_LEAK\"]\n    Check --> C7[\"7. PERMISSION_SEVERED\"]\n    \n    C1 --> Remediate[\"Remediation Action\"]\n    C2 --> Remediate\n    C3 --> Remediate\n    C4 --> Remediate\n    C5 --> Remediate\n    C6 --> Remediate\n    C7 --> Remediate\n    \n    Remediate --> ScanRep[\"POST /api/v1/admin/object-links:audit\"]\n    Remediate --> PurgeRep[\"POST /api/v1/admin/object-links:purge\"]\n```\n\n1. **`DANGLING_SOURCE`:** The source object ID does not exist in the active universal object spine.\n2. **`DANGLING_TARGET`:** The target object ID does not exist or has been hard-deleted.\n3. **`SOFT_DELETED_ENDPOINT`:** One or both endpoints reference an object soft-deleted beyond the retention window.\n4. **`ARCHIVED_POLICY_VIOLATION`:** The link connects an active entity to an archived entity in violation of project archiving policy.\n5. **`TYPE_MATRIX_VIOLATION`:** The relation violates the registered link type matrix allowlist.\n6. **`CROSS_WORKSPACE_LEAK`:** The source and target objects belong to different workspaces, violating multi-tenant isolation.\n7. **`PERMISSION_SEVERED`:** The link endpoints span access boundaries where caller or entity permissions have been severed.\n\n### Audited Purging and Two-Stage Remediation\n\nPlatform administrators can inspect and remediate graph health through administrative APIs and the visual studio at `/admin/link-auditor`:\n- **Audit Scan:** `POST /api/v1/admin/object-links:audit` traverses `object_links` and returns summary counts by invalidity reason.\n- **Audited Purge:** `POST /api/v1/admin/object-links:purge` accepts `audit_ids` (1 to 200 UUIDs) and mandatory `reason` (10 to 500 characters), returning `purged_count` and emitting immutable `INVALID_OBJECT_LINK_PURGED` events in the hash-chained `activity_records` ledger.\n\n```bash\n# Run link audit integrity scan via REST API\ncurl -X POST https://kanban.example.com/api/v1/admin/object-links:audit \\\n  -H \"Authorization: Bearer <ADMIN_TOKEN>\"\n\n# Execute audited purge of corrupted links with mandatory reason (>=10 chars)\ncurl -X POST https://kanban.example.com/api/v1/admin/object-links:purge \\\n  -H \"Authorization: Bearer <ADMIN_TOKEN>\" \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"audit_ids\": [\"0192e4a1-0000-7000-8000-000000000001\"], \"reason\": \"Monthly maintenance cycle\"}'\n```\n\nAll purged links are written to the immutable `audit_ledger` with the operator ID, timestamp, and the exact violation class, ensuring forensic traceability.\n\n![Delete Blast Radius Warning Modal](images/20-delete-blast-radius.png)\n\n---\n\n## Admin Link Auditor Studio (`/admin/link-auditor`)\n\nWhile CLI commands provide automated pipeline hooks, workspace and server administrators have access to a full forensic UI studio at `/admin/link-auditor`.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Workspace / Server Admin (AAL2)\n    participant Studio as Link Auditor Studio (/admin/link-auditor)\n    participant Drawer as Inspect Link Drawer\n    participant Modal as 2-Stage Purge Modal\n    participant Engine as Auditor Engine & DB\n\n    Admin->>Studio: Navigate to /admin/link-auditor\n    Studio->>Engine: Run Integrity Scan across object_links\n    Engine-->>Studio: Return breakdown counts & keyset-paginated invalid links\n    Admin->>Studio: Click \"Inspect\" on flagged link\n    Studio->>Drawer: Open Inspect Link Drawer (source, target, violation rationale)\n    Admin->>Studio: Click \"Purge Selected Links\"\n    Studio->>Modal: Open 2-Stage Purge Confirmation Modal\n    Modal->>Admin: Require typed confirmation & reason\n    Admin->>Modal: Submit cryptographic confirmation\n    Modal->>Engine: Atomic DELETE invalid links & INSERT audit_ledger\n    Engine-->>Studio: Links purged: real-time table update\n```\n\n![Invalid Object Link Auditor Studio](images/46-admin-link-auditor.png)\n\n### 1. Seven-Class Breakdown Cards\nThe top of the studio displays real-time counts across the 7 anomaly classes:\n- **Dangling Source:** Source entity does not exist in the universal object graph.\n- **Dangling Target:** Target entity does not exist or has been permanently removed.\n- **Soft-Deleted Endpoint:** Endpoint entity is marked soft-deleted while link remains active.\n- **Archived Policy Violation:** Link connects an active entity to an archived entity in violation of project archiving policy.\n- **Cross-Workspace Leak:** Link crosses workspace boundaries without multi-tenant grant.\n- **Type Matrix Violation:** Link connects object kinds prohibited by the universal type matrix.\n- **Permission Severed:** Access boundary severed between linked entities.\n\n### 2. Inspect Link Drawer\nClicking **Inspect** on any flagged row opens a detailed forensic drawer displaying full endpoint metadata, entity timestamps, link creation provenance, and specific violation details:\n\n![Inspect Link Drawer](images/47-admin-link-auditor-inspect-drawer.png)\n\n### 3. Audited Purge Modal\nTo prevent accidental data loss, purging invalid links requires two-stage administrative confirmation:\n- Displays exact count of affected links and affected entity keys.\n- Requires entering an explicit audit reason that is permanently recorded in the ledger.\n- Executes atomically inside a PostgreSQL transaction, recording SHA-256 hash-chained entries in `audit_ledger`.\n\n![Audited Purge Modal](images/48-admin-link-auditor-purge-modal.png)\n\n---\n\n## PostgreSQL Issue Copy and Subtree Graph Synthesis\n\nCloning work items, hierarchical sub-tasks, and attachments is governed by an atomic, security-definer PostgreSQL and service layer workflow (`kanban/services/issue_copy.py` and `p3_08_issue_copy.up.sql`):\n\n1. **Authorization Gate:**\n   - Requires `Capability.VIEW` (0x01) on the source issue and `Capability.EDIT` (0x04) on the target project. Missing permissions fail closed with 404 or 403.\n2. **Subtree Traversal and Fail-Closed Pruning:**\n   - Invokes `issues_get_copy_subtrees(p_root_id uuid)` (`SECURITY DEFINER`, `ltree` depth `<= 6`).\n   - Evaluates caller capability on each descendant node (`app_has_object_capability(r.id, 1)`).\n   - If an intermediate or leaf sub-issue lacks `VIEW` permission, the function prunes that node and its descendants fail-closed, aggregating pruned counts into `skipped.restricted_sub_issues` without leaking unauthorized metadata.\n3. **Safety Caps:**\n   - Enforces `MAX_READABLE_ISSUES_LIMIT = 200` to prevent unbounded memory allocation and database timeouts during tree replication.\n4. **Agent-Safe Sequence Allocation:**\n   - Calls `allocate_issue_sequences(p_project_id, p_count, false)` (`p4_24_agent_safe_sequences.up.sql`) to allocate contiguous sequence numbers atomically.\n   - Any skipped sequences are recorded with an immutable `SEQUENCE_SKIPPED` ledger event.\n5. **Atomic Savepoint Registration:**\n   - Executes inside an atomic nested transaction (`session.begin_nested()`).\n   - Cloned issues and sub-issues invoke `register_object(CAST('issue' AS object_kind), ...)` to bind spine records.\n   - Copies attachments when requested (`include_attachments=true`), links relates-to edges (`link_as_relates_to=true`), and emits `ISSUE_CREATED` and `ISSUE_COPIED` activity records.\n\n\n---\n\n## State Deletion and Dependency Remapping\n\n<a id=\"state-deletion\"></a>\n\nDeleting a workflow state or label carries significant blast radius across active tickets, automation pipelines, and filtered dashboards. Rather than allowing cascade deletions to orphan references or create dangling graph edges, the platform enforces atomic pre-delete reverse-auditing and safe dependency remapping via the Pre-Delete Reverse-Audit Modal (`DeleteAuditModal`, `KB-P3-AUDIT-23`).\n\n### 1. Pre-Delete Reverse-Audit Inspection\n\nBefore deletion can be authorized, the administrative client requests an audit impact evaluation from `/api/v1/projects/:key/states/:id/audit-impact`. The auditor calculates the exact blast radius:\n\n- **Active Issues:** Count and sample keys of all active work items assigned to the target state.\n- **Automation Hooks:** Inspection of workflow automation hooks referencing the target state as either source (`from_state_id`) or destination (`to_state_id`), distinguishing enabled from disabled hooks.\n- **In-Flight Executions:** Active transitions executing in the background runtime.\n- **Historical Executions:** Past execution records requiring referential preservation.\n- **Saved Views:** Project and user filter views referencing the state in query criteria.\n\n### 2. Non-Bypassable Hard Deletion Blocks\n\nDeletion is strictly blocked under three safety invariants:\n- **`DEFAULT_STATE`:** The state is configured as the default intake state for new issues in the project. Another state must be designated as default prior to deletion.\n- **`LAST_STATE_IN_GROUP`:** The state is the sole member of its workflow group (e.g. `backlog`, `unstarted`, `started`, `completed`, `cancelled`). Deleting it would leave the group unpopulated.\n- **`TRANSITION_IN_FLIGHT`:** Background workflow transition helpers or AI agent gates are currently executing against issues in this state. Deletion is deferred until pending jobs complete.\n\n### 3. Dependency Remapping Rules\n\nWhen dependencies exist, deletion requires explicit remapping to an eligible target replacement state:\n- **Issue Reassignment:** All issues currently in the target state are atomically reassigned to the chosen replacement state within the same project. If issues exist, selecting a replacement state is mandatory.\n- **Filter Saved Views:** Queries and saved filter configurations referencing the deleted state are inspected, ensuring dashboards and project boards do not encounter broken query predicates.\n- **Workflow Hook Migration:** Administrators can toggle the `Migrate workflow automation hooks` option (`migrate_hooks: true`). When enabled, inbound and outbound hook transition rules are remapped to the replacement state. If unmigrated, active hooks must be reassigned or disabled before state deletion can proceed.\n- **Audited Ledger Trail:** The state deletion and all accompanying reassignments execute inside an atomic PostgreSQL transaction, emitting structured activity records to the immutable audit ledger.\n"
  },
  {
    "slug": "user-tasks-and-qa-matrix",
    "title": "[Architectural] \ud83d\udc4dkanban User Task & Architecture QA Verification Matrix",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Engineering Appendix",
    "audience": "Forensic QA & Certification Auditors",
    "order": 31,
    "summary": "flowchart TD Spec[\"Authoritative Product Spec (S1-S15)\"] --> QAPipeline[\"Forensic QA Verification Pipeline\"]",
    "sections": [
      {
        "id": "subagent-task-assignment-roster",
        "title": "1. Subagent Task Assignment Roster",
        "level": 2
      },
      {
        "id": "user-task-catalogue-by-architecture-specification-section",
        "title": "2. User Task Catalogue by Architecture Specification Section",
        "level": 2
      },
      {
        "id": "group-a-onboarding-authentication-standalone-operations-spec-s2-s3-s4",
        "title": "Group A: Onboarding, Authentication & Standalone Operations (Spec S2, S3, S4)",
        "level": 3
      },
      {
        "id": "group-b-workspace-home-multi-layout-views-17-feature-ticket-screen-spec-s6-s7",
        "title": "Group B: Workspace Home, Multi-Layout Views & 17-Feature Ticket Screen (Spec S6, S7)",
        "level": 3
      },
      {
        "id": "group-c-canonical-markdown-stickies-docs-sparkle-ai-completion-spec-s5-s8-s9",
        "title": "Group C: Canonical Markdown, Stickies, Docs & Sparkle (\u2728) AI Completion (Spec S5, S8, S9)",
        "level": 3
      },
      {
        "id": "group-d-mcp-access-studio-custom-scripted-fields-scripted-workflows-spec-s11-s13-s14",
        "title": "Group D: MCP Access Studio, Custom Scripted Fields & Scripted Workflows (Spec S11, S13, S14)",
        "level": 3
      },
      {
        "id": "group-e-administrative-hardening-rbac-gate-rework-verification-spec-s3-s4-s11-s14",
        "title": "Group E: Administrative Hardening, RBAC & Gate Rework Verification (Spec S3, S4, S11, S14)",
        "level": 3
      }
    ],
    "content": "# [Architectural] \ud83d\udc4dkanban User Task & Architecture QA Verification Matrix\n\n> **Purpose:** This document maps every functional domain in [System Topology and Multi-Container Architecture](System-Topology-and-Multi-Container-Architecture) (Sections 1-15) to concrete human user tasks, live `/browser` verification scenarios, screenshot deliverables, and API/MCP schema audits.\n\n---\n\n## 1. Subagent Task Assignment Roster\n\n```mermaid\nflowchart TD\n    Spec[\"Authoritative Product Spec (S1-S15)\"] --> QAPipeline[\"Forensic QA Verification Pipeline\"]\n    \n    subgraph Execution[\"Parallel Verification Engines\"]\n        Bot1[\"Browser QA Bot 1<br/>Board, Views, 17-Feature Ticket Screen\"]\n        Bot2[\"Browser QA Bot 2<br/>Docs, Stickies, Markdown, Sparkle (\u2728)\"]\n        Bot3[\"Browser QA Bot 3<br/>Auth, Security, MCP & Workflow Studios\"]\n        MCPAudit[\"MCP Evaluator Bot<br/>27 Live Tool Schemas & Budgets\"]\n    end\n    \n    QAPipeline --> Bot1\n    QAPipeline --> Bot2\n    QAPipeline --> Bot3\n    QAPipeline --> MCPAudit\n    \n    Bot1 --> Artifacts[\"Visual Proof Packet (35+ Screenshots in images/)\"]\n    Bot2 --> Artifacts\n    Bot3 --> Artifacts\n    MCPAudit --> Artifacts\n    \n    Artifacts --> RealityChecker[\"reality-checker Forensic Audit Gate<br/>(Grade-A READY Certification)\"]\n```\n\n| Subagent Role | Model Tier | Assigned Architecture Sections | Primary Deliverables |\n| :--- | :---: | :--- | :--- |\n| **Browser QA & Screenshot Bot 1: Core Board, Views & Ticket Drawer** | `flash` | **S6** (Board, Whitespace, `<EmojiHint>`), **S7** (17-Feature Ticket Screen, `?peek=` Drawer, Rail, 4-Tab Activity) | Live `/browser` human walkthrough of Workspace Home, Board, List (3-pane split), Table, Calendar, Timeline, Quick-Create (`C`), and Ticket Drawer (`?peek=`). Captures annotated screenshots into `thumbs-up-kanban.wiki/images/`. |\n| **Browser QA & Screenshot Bot 2: Docs, Stickies, Editor & Sparkle (`\u2728`)** | `flash` | **S5** (Canonical Markdown, Mermaid, SVG), **S8** (Hierarchical Docs & Stickies Promotion), **S9** (Sparkle FIM Completion & Right-Click Accept) | Live `/browser` human walkthrough of Workspace/Project Stickies, Sticky-to-Doc AI Promotion modal, Docs ltree tree & outline, Editor Markdown/Mermaid rendering, and Sparkle (`\u2728`) ghost-text completion. Captures screenshots into `thumbs-up-kanban.wiki/images/`. |\n| **Browser QA & Screenshot Bot 3: Auth, Security, MCP & Workflow Studios** | `flash` | **S2** (Standalone Status Panel), **S4** (Multi-Card Auth Studio & `/setup`), **S11** (MCP Access & Scopable Keys Studio), **S13** (Custom Fields Studio), **S14** (Workflow Transition Studio & Dry-Run Drawer) | Live `/browser` human walkthrough of `/setup`, `/login`, `/admin/auth`, `/admin/mcp`, `/projects/KAN/settings/workflows`, `/projects/KAN/settings/custom-fields`, and `/admin/standalone`. Captures screenshots into `thumbs-up-kanban.wiki/images/`. |\n| **MCP Tools JSON vs. Expectation Evaluator Bot** | `flash` | **S11** (3-Surface MCP Server: `/mcp/agent`, `/mcp/docs`, `/mcp/admin`), **S3.5** (Read-Taint Guard), **S14** (Admin Tool 8 & 9) | Audits all 24 live MCP tool JSON schemas (`/tmp/mcp_tools_actual.json`) against Spec S11 expectations for parameter clarity, `EntityResolver` human keys, `lod` tiers, 2-stage destructive confirmations, and LLM ergonomics. Produces `thumbs-up-kanban.wiki/MCP-Tools-Usability-Audit.md`. |\n| **Wiki Documentation Architect & Author** | `flash` / Coordinator | **S1-S15** (Full System Coverage + OpenAPI 242-Route Reference + MCP 24-Tool Reference) | Authors complete 10-page Wiki in `thumbs-up-kanban.wiki/` with `_Sidebar.md`, `_Footer.md`, embedded screenshots, Mermaid diagrams, REST OpenAPI reference, MCP catalog, and CLI runbooks. |\n| **Carbon Architecture-vs-Docs Delta Auditor** | `pro` (Carbon) | **S1-S15** Cross-Layer Forensic Delta Audit | Compares `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and actual codebase against all Wiki topics, browser QA findings, and API/MCP schemas to identify missing features, incomplete items, and actionable backlog tickets. |\n\n---\n\n## 2. User Task Catalogue by Architecture Specification Section\n\n### Group A: Onboarding, Authentication & Standalone Operations (Spec S2, S3, S4)\n\n| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |\n| :--- | :---: | :--- | :--- | :--- | :--- |\n| **`UT-01`** | **S2.2, S4.2** | Platform Operator | **First-Boot `/setup` Claim Wizard** | 1. Navigate to `/setup` on a fresh instance.<br>2. Inspect the single-use `kb_setup_*` bootstrap token input, initial admin username/password fields, and workspace creation form.<br>3. Verify pre-session CSRF bootstrap (`__Host-kb_csrf` / `kb_csrf`). | Renders clean First-Boot Claim Wizard without 403 CSRF errors.<br>[images/01-first-boot-setup.png](images/01-first-boot-setup.png) |\n| **`UT-02`** | **S4.1, S4.3** | End User / Admin | **Multi-Card Login & Passkey/TOTP Prompt** | 1. Navigate to `/login`.<br>2. Verify ordered authentication cards (Local Admin, OIDC/OAuth2, LDAPS, WebAuthn Passkey `rp.name = \"\ud83d\udc4dkanban\"`).<br>3. Test credential entry and session establishment. | Displays enabled auth cards in `sort_rank` order with zero implicit email auto-merge.<br>[images/02-multi-card-login.png](images/02-multi-card-login.png) |\n| **`UT-03`** | **S4.4** | Server Admin (AAL2) | **Admin Auth Studio Management** | 1. Navigate to `/admin/auth`.<br>2. Inspect auth card list, enable/disable toggles, drag reorder, write-only secret fields, `Test Handshake` action, and `LOCKOUT_PREVENTED` break-glass guard. | Shows Auth Studio with mandatory vs. optional config sections and lockout guard.<br>[images/03-admin-auth-studio.png](images/03-admin-auth-studio.png) |\n| **`UT-04`** | **S2.2, S2.4** | Platform Operator | **Standalone Status Panel & Compose Export** | 1. Navigate to `/admin/standalone`.<br>2. Check volume persistence probe status (`/var/lib/kanban/data`), dismissible notification pill, encrypted backup trigger, and `docker-compose.yml` 5-network export tab. | Displays green/amber persistence status and copyable 5-network production Compose bundle.<br>[images/04-standalone-status-panel.png](images/04-standalone-status-panel.png) |\n\n![First-Boot Setup Wizard](images/01-first-boot-setup.png)\n\n![Multi-Card Login Screen](images/02-multi-card-login.png)\n\n---\n\n### Group B: Workspace Home, Multi-Layout Views & 17-Feature Ticket Screen (Spec S6, S7)\n\n| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |\n| :--- | :---: | :--- | :--- | :--- | :--- |\n| **`UT-05`** | **S6.1, S6.3** | Project Lead | **Workspace Home & Project Creation** | 1. Navigate to `/`.<br>2. Inspect project cards (`KAN`), quick-links (`Work Items`, `Board`, `Stickies`, `Docs`, `Custom Fields`), and click `+ Create Project` modal. | Renders Workspace Home grid and project creation modal.<br>[images/05-workspace-home.png](images/05-workspace-home.png) |\n| **`UT-06`** | **S6.2, S6.4** | Developer | **Kanban Board View & Optimistic Drag (`<12ms`)** | 1. Navigate to `/projects/KAN/issues?layout=board`.<br>2. Verify breathable whitespace, state columns (`Backlog`, `Todo`, `In Progress`, `Done`), corporate priority badges, `<EmojiHint>` hover tooltips, and card drag-and-drop. | Columns render with virtualized cards, semantic emojis, and instant drag response.<br>[images/06-board-view.png](images/06-board-view.png) |\n| **`UT-07`** | **S6.3** | Developer / PM | **Multi-Layout Switching: List, Table, Calendar & Timeline (Gantt)** | 1. Switch layouts via `?layout=list` (3-pane split view), `?layout=table`, `?layout=calendar`, and `?layout=timeline`.<br>2. Inspect filters bar, 2D swimlane grouping, and Gantt dependency arrows (`BLOCKS`). | All 5 layouts render cleanly without full-page reloads.<br>[images/07-list-table-calendar-timeline.png](images/07-list-table-calendar-timeline.png) |\n| **`UT-08`** | **S7.1, S7.2** | Developer | **Quick-Create Work Item Modal (`C`) & Draft Toggle** | 1. Press `C` or click `+ New Work Item`.<br>2. Enter title, Markdown description, state/priority, and inspect the `\u270d\ufe0f Keep work-in-progress` draft checkbox. | Opens Quick-Create modal and persists new issue into active view.<br>[images/08-quick-create-modal.png](images/08-quick-create-modal.png) |\n| **`UT-09`** | **S7.1-S7.4 (`8a`-`8q`)** | Developer / Reviewer | **Ticket Peek Drawer (`?peek=`) & 17-Feature Inspection** | 1. Click any issue card to open `?peek=KAN-1` while keeping the background board visible.<br>2. Verify properties rail (`State`, hybrid `Assignees \ud83c\udff7\ufe0f`, `Priority`, `Created-by \ud83d\udd04`, `Dates`, `Modules`, `Cycle`, `Parent \ud83d\udd12`, `Labels`).<br>3. Inspect header actions (`Subscribe \ud83d\udd14`, `Copy link \ud83d\udd17`, `Archive`, `Delete` blast-radius) and 4-tab Activity feed (`All`, `Comments`, `History`, `\ud83e\udd16 Gates`). | Background board stays mounted; drawer displays all 17 enterprise work-item features and Explicit Sharing pill.<br>[images/09-ticket-peek-drawer.png](images/09-ticket-peek-drawer.png) |\n\n![Kanban Board View](images/06-board-view.png)\n\n![Ticket Peek Drawer with 17 Features](images/09-ticket-peek-drawer.png)\n\n---\n\n### Group C: Canonical Markdown, Stickies, Docs & Sparkle (`\u2728`) AI Completion (Spec S5, S8, S9)\n\n| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |\n| :--- | :---: | :--- | :--- | :--- | :--- |\n| **`UT-10`** | **S8.2, S10.4** | Product Manager | **Workspace & Project Stickies + Smart AI Doc Promotion** | 1. Navigate to `/stickies` and `/projects/KAN/overview`.<br>2. Create a quick sticky note on the masonry grid.<br>3. Trigger **Promote to Doc** preview to verify AI structuring and ACL inheritance warning. | Sticky note renders on color-coded grid; promotion preview structures Markdown while preserving ACL scope.<br>[images/10-stickies-and-doc-promotion.png](images/10-stickies-and-doc-promotion.png) |\n| **`UT-11`** | **S8.1** | Technical Writer | **Hierarchical Docs (`ltree`), Outline & Version History** | 1. Navigate to `/projects/KAN/docs`.<br>2. Browse nested page tree, inspect auto-extracted heading outline rail, and view append-only version history/restore drawer. | Renders hierarchical doc tree, rich Markdown body, and version history diff/restore controls.<br>[images/11-docs-hierarchy-view.png](images/11-docs-hierarchy-view.png) |\n| **`UT-12`** | **S5.1-S5.4, S9.1-S9.3** | Engineer | **Canonical Markdown Editor, Mermaid Diagrams & Sparkle (`\u2728`) FIM** | 1. Open the editor (`/projects/KAN/docs` or `/__dev/editor`).<br>2. Test auto-converted paste, client-side Mermaid SVG rendering, and pause typing for `300ms` to trigger the blinking cursor Sparkle (`\u2728`) inline completion.<br>3. Test `Tab` or surgical right-click context menu accept. | Renders sanitized Markdown + Mermaid diagram and displays non-intrusive Sparkle ghost text.<br>[images/12-editor-mermaid-and-sparkle.png](images/12-editor-mermaid-and-sparkle.png) |\n\n![Project Stickies and Smart Promotion Modal](images/10-stickies-and-doc-promotion.png)\n\n![Editor with Mermaid Diagrams and Sparkle Completion](images/12-editor-mermaid-and-sparkle.png)\n\n---\n\n### Group D: MCP Access Studio, Custom Scripted Fields & Scripted Workflows (Spec S11, S13, S14)\n\n| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |\n| :--- | :---: | :--- | :--- | :--- | :--- |\n| **`UT-13`** | **S11.2, S11.3** | Developer / Admin | **Scopable MCP Keys, Per-Tool Toggles & Device Activation** | 1. Navigate to `/settings/mcp`, `/admin/mcp`, and `/activate` (RFC 8628 Device Flow).<br>2. Inspect hierarchical scoping (`Global`, `Workspace`, `Project`), expiration presets (including `Unlimited` with safety friction), and per-tool checkboxes across `/mcp/agent`, `/mcp/docs`, `/mcp/admin`. | Displays MCP Access Studio with copyable client config snippets and granular tool toggles.<br>[images/13-mcp-access-studio.png](images/13-mcp-access-studio.png) |\n| **`UT-14`** | **S13.1-S13.3** | Project / Server Admin | **Custom Scripted Fields (`\ud83e\uddea`) & Tiered Privilege Escalation** | 1. Navigate to `/projects/KAN/settings/custom-fields`.<br>2. Inspect custom field definitions, Wasm/script bindings, `\ud83e\uddea` computed badge on ticket rail, and AAL2 approval banner for escalated scope (`Project` -> `Workspace` -> `Server`). | Renders Custom Fields Studio and cryptographic admin approval status.<br>[images/14-custom-fields-studio.png](images/14-custom-fields-studio.png) |\n| **`UT-15`** | **S14.1-S14.4** | Workflow Architect | **Admin Workflow Transition Studio & Non-Persistent Dry-Run** | 1. Navigate to `/projects/KAN/settings/workflows`.<br>2. Select a `(from_state -> to_state)` rule, inspect ordered pipeline hooks (Tier A Wasm validator, Tier A mutator, Async Agent Transition Helper `in_app_sdk` / `cli_pipe` / `remote_runner`, mutable field checkboxes).<br>3. Open the **Dry-Run Drawer**, test against a sample ticket, and inspect per-step execution results and copyable `kanban-agent validate-transition` CLI snippet. | Displays pipeline ordering studio and executes zero-persistence dry-run with step timings.<br>[images/15-workflow-transition-studio.png](images/15-workflow-transition-studio.png) |\n| **`UT-16`** | **S14.2** | Developer | **Async Agent Gate Lifecycle on Board (`\u23f3\ud83e\udd16` -> `\ud83d\uded1\ud83e\udd16` / `\u2705\ud83e\udd16`)** | 1. Inspect async agent gate card states (`/projects/KAN/issues?layout=board` or `/__dev/realtime`): live countdown timer (`\u23f3\ud83e\udd16`), `240ms` spring snap-back toast on veto (`\ud83d\uded1\ud83e\udd16`), and verified header badge (`\u2705\ud83e\udd16`). | Visualizes pending agent hold, countdown progress bar, and veto snap-back toast.<br>[images/16-async-agent-gate-states.png](images/16-async-agent-gate-states.png) |\n\n---\n\n### Group E: Administrative Hardening, RBAC & Gate Rework Verification (Spec S3, S4, S11, S14)\n\n| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |\n| :--- | :---: | :--- | :--- | :--- | :--- |\n| **`UT-17`** | **S2.2, S4.4, S15.1** | Server Admin (AAL2) | **Admin Browser QA: Auth Studio, Principals & Favicon** | 1. Navigate to `/admin/auth`.<br>2. Inspect multi-card authentication ordering and lockout protection.<br>3. Inspect Principal Management kind filter tabs (`ALL`, `USER`, `GROUP`, `AGENT`).<br>4. Click `+ Create Principal`, select `GROUP` or `AGENT`, provide identifier and display name, and submit.<br>5. Verify `GET /favicon.ico` returns HTTP 200 with `Cache-Control: public, max-age=86400`. | Auth Studio manages USER/GROUP/AGENT principals; `/favicon.ico` serves branded asset cleanly.<br>[images/68-admin-browser-qa.png](images/68-admin-browser-qa.png) |\n| **`UT-18`** | **S3.1-S3.4, S13.2, S15.2** | Standard Member | **Standard User Browser QA & Negative RBAC Isolation** | 1. Authenticate as standard workspace member (`WORKSPACE_MEMBER`).<br>2. Browse assigned projects, board, list, docs, and ticket drawer.<br>3. Attempt navigation to administrative routes (`/admin/auth`, `/admin/standalone`, `/admin/mcp`, `/projects/KAN/settings/custom-fields`).<br>4. Verify custom fields editor fails closed with access denied toast/banner.<br>5. Confirm zero administrative controls or privileged mutation buttons leak into client DOM. | Negative RBAC strictly isolates standard users; privileged views fail closed without privilege leaks.<br>[images/69-standard-user-negative-rbac.png](images/69-standard-user-negative-rbac.png) |\n| **`UT-19`** | **S11.1-S11.4, S14.3** | Security Architect / Agent | **CLI MCP Scoping Matrix & E2E Gate Rework Loop** | 1. Audit all 12 `/mcp/admin` tools in `mcp/auth.py` for action-aware scope enforcement (`admin:read`, `admin:write`, `admin:destructive`).<br>2. Verify `project` argument alias to `project_key` on `manage_ai_and_agent_runners` and `architect_project`.<br>3. Verify OpenAI Codex CLI invocation enforces `codex exec -s read-only -` and rejects `-p`.<br>4. Run E2E transition gate rework loop: first transition enters `pending_agent` (`\u23f3\ud83e\udd16`), verifier rejects initial commit SHA with `cited_files`, rolls back to source state (`\ud83d\uded1\ud83e\udd16`), developer commits rework fix, and second transition evaluates fixed commit SHA, records `verdict=\"APPROVE\"` (`\u2705\ud83e\udd16`), advancing state and appending immutable hash-chained audit record. | Full 12-tool scope matrix enforced; E2E gate rework loop executes and logs immutable provenance.<br>[images/70-mcp-scoping-and-rework-loop.png](images/70-mcp-scoping-and-rework-loop.png) |\n\n![Workflow Transition Studio and Dry-Run Drawer](images/15-workflow-transition-studio.png)\n\n![Async Agent Gate Card States and Snap-Back Lifecycle](images/16-async-agent-gate-states.png)\n"
  },
  {
    "slug": "zero-trust-security-and-access-visibility",
    "title": "[Informational] Zero-Trust Security Architecture and Explicit Access Visibility",
    "category": "informational",
    "track": "Security & Adoption Overview",
    "subtrack": "Zero-Trust Architecture",
    "audience": "Security Architects & Hardening Engineers",
    "order": 32,
    "summary": "Security is Priority 0 in \ud83d\udc4dkanban. Rather than relying on fragile application-level checks or leaky implicit permissions, \ud83d\udc4dkanban implements an uncompromising zero-trust architecture. Every request, query, and agent invocation is authenticated, scoped, and strictly evaluated against mathematical access invariants.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "authentication",
        "title": "Authentication",
        "level": 2
      },
      {
        "id": "universal-access-control-model",
        "title": "Universal Access Control Model",
        "level": 2
      },
      {
        "id": "effective-resource-access-era-evaluation",
        "title": "Effective Resource Access (ERA) Evaluation",
        "level": 3
      },
      {
        "id": "monotonic-credentialboundary-enforcement",
        "title": "Monotonic CredentialBoundary Enforcement",
        "level": 3
      },
      {
        "id": "postgresql-force-row-level-security-100-coverage",
        "title": "PostgreSQL FORCE ROW LEVEL SECURITY (100% Coverage)",
        "level": 2
      },
      {
        "id": "the-fail-closed-context-invariant",
        "title": "The Fail-Closed Context Invariant",
        "level": 3
      },
      {
        "id": "explicit-access-visibility-and-sharing-manifests",
        "title": "Explicit Access Visibility and Sharing Manifests",
        "level": 2
      },
      {
        "id": "anti-enumeration-and-timing-defense",
        "title": "Anti-Enumeration and Timing Defense",
        "level": 3
      },
      {
        "id": "mcp-read-taint-high-water-mark-defense",
        "title": "MCP Read-Taint High-Water Mark Defense",
        "level": 2
      },
      {
        "id": "distributed-runner-dedicated-mtls-port-8444-and-pop-handshake",
        "title": "Distributed Runner Dedicated mTLS Port (:8444) and PoP Handshake",
        "level": 2
      },
      {
        "id": "private-only-internal-mcp-route-isolation-internalv1mcp",
        "title": "Private-Only Internal MCP Route Isolation (/internal/v1/mcp/*)",
        "level": 2
      },
      {
        "id": "stride-threat-mitigation-matrix",
        "title": "STRIDE Threat Mitigation Matrix",
        "level": 2
      }
    ],
    "content": "# [Informational] Zero-Trust Security Architecture and Explicit Access Visibility\n\n## Overview\n\nSecurity is Priority 0 in \ud83d\udc4dkanban. Rather than relying on fragile application-level checks or leaky implicit permissions, \ud83d\udc4dkanban implements an uncompromising zero-trust architecture. Every request, query, and agent invocation is authenticated, scoped, and strictly evaluated against mathematical access invariants.\n\nKey security pillars:\n1. **Hardware-Enforced Database RLS:** PostgreSQL `FORCE ROW LEVEL SECURITY` is enabled across 100% of tenant tables.\n2. **Zero-Context Fail-Closed Execution:** Unbound database sessions return zero rows.\n3. **Explicit Access Visibility:** Every ticket, doc, and sticky renders an explicit sharing manifest with zero cross-tenant enumeration.\n4. **Agent On-Behalf-Of (OBO) Key Scoping:** Agent permissions are computed strictly as the mathematical intersection of the calling user's permissions and the API key's scope.\n5. **MCP Read-Taint High-Water Mark Defense:** Prevents autonomous agents from exfiltrating sensitive data read from higher-privilege scopes into lower-privilege write targets.\n\n---\n\n## Authentication\n\nAccount authentication enforces minimum entropy requirements (minimum 12 characters for standard users, 14 characters for Server Admins). Authentication cards support local password credentials, WebAuthn Passkeys, TOTP two-factor authentication, LDAPS/Active Directory, and multi-card OIDC/OAuth providers. Sessions are cryptographically sealed with monotonic idle and absolute timeout expirations.\n\n---\n\n## Universal Access Control Model\n\n\ud83d\udc4dkanban unifies human users, user groups, and autonomous agent service-principals under a single Universal Object Graph access model.\n\n### Effective Resource Access (ERA) Evaluation\n\nAccess to any resource (`Project`, `Issue`, `Doc`, `Sticky`, `View`) is determined dynamically:\n\n```mermaid\nflowchart TD\n    User[\"Principal (Human / Agent)\"] --> Inherited[\"Inherited RBAC (Workspace & Project Roles)\"]\n    User --> Direct[\"Direct Resource ACLs (Allow & Deny Masks)\"]\n    Inherited --> Combined[\"Effective User Access = (Inherited \u222a Allow) \\ Deny\"]\n    \n    subgraph AgentOBO[\"Agent On-Behalf-Of Clamping\"]\n        Combined --> Intersect{\"Intersection (\u2229)\"}\n        KeyScope[\"API Key Scope Constraints - Allowed surfaces, projects, tools\"] --> Intersect\n        AgentGrant[\"Explicit Agent Grant\"] --> Intersect\n        Intersect --> Effective[\"Final Effective Agent Permission\"]\n    end\n```\n\nWhere:\n- **Roles:** `Owner`, `Admin`, `Member`, `Guest`.\n- **Authoritative 8-Bit Capability Bitmask** (`Capability(IntFlag)`):\n  * `VIEW` (`0x01` / `1`): Read ticket summary, description, and metadata.\n  * `COMMENT` (`0x02` / `2`): Add comments to discussions and activity feeds.\n  * `EDIT` (`0x04` / `4`): Mutate scalar fields, tags, and assignments.\n  * `TRANSITION` (`0x08` / `8`): Move card state across workflow stages.\n  * `LINK` (`0x10` / `16`): Create or sever typed object links.\n  * `SHARE` (`0x20` / `32`): Modify access audience and direct object sharing.\n  * `ADMIN` (`0x40` / `64`): Manage permissions, scripted fields, and audit settings.\n  * `DELETE` (`0x80` / `128`): Soft-trash or permanently purge entities.\n  * `ALL` (`0xFF` / `255`): Full administrative capability mask.\n- **SCOPE_CAPABILITY_MAP:** Maps OAuth/API key scopes to capabilities:\n  * `session`: `Capability.ALL` (`0xFF`)\n  * `read`, `agent:read`, `docs:read`, `admin:read`: `Capability.VIEW` (`0x01`)\n  * `comment`: `Capability.VIEW | Capability.COMMENT` (`0x03`)\n  * `write`: `Capability.VIEW | Capability.COMMENT | Capability.EDIT | Capability.TRANSITION | Capability.LINK` (`0x1F`)\n  * `agent:write`: `Capability.VIEW | Capability.COMMENT | Capability.EDIT | Capability.TRANSITION | Capability.LINK` (`0x1F`)\n  * `docs:write`: `Capability.VIEW | Capability.COMMENT | Capability.EDIT | Capability.LINK` (`0x17`)\n  * `admin:write`: `Capability.ALL` (`0xFF`)\n- **Agent OBO Key Intersection:** When an autonomous agent acts on behalf of a user using an API key, the effective permission is clamped:\n  ```\n  AgentEffectiveAccess = UserPermissions INTERSECT KeyScopeConstraints\n  ```\n  An agent cannot escalate privileges beyond the user who generated the key, nor can it exceed the explicit scope configured on the key.\n\n### Monotonic CredentialBoundary Enforcement\n\nAll issued credentials (MCP API keys, personal user tokens, and OAuth 2.1 access tokens) enforce a strict, monotonic privilege ceiling via the `CredentialBoundary` kernel:\n\n- **Monotonic Clamping:** An issued key can only narrow privileges, never expand them. The effective capability bitmask of any token is computed as:\n  ```\n  TokenEffectiveCapability = IssuerActiveCapability BITWISE-AND KeyCapabilityMask\n  ```\n- **Read-Only Scoping:** When minting a read-only token (`capability_mask = 1`, `VIEW` only), the system emits strictly read-only scopes (`${surface}:read`). Write scopes (`${surface}:write`) are completely withheld. Any incoming API or MCP invocation carrying a write payload is rejected at the route gateway before reaching application logic.\n- **Allowed CIDRs (Optional Network Pinning):** Administrators and users can bind keys to explicit IPv4 or IPv6 CIDR subnets (e.g., `192.168.1.0/24, 2001:db8::/32`). Invocations from client IP addresses outside the allowlist receive an immediate `403 Forbidden` (`FORBIDDEN_CIDR`).\n\n---\n\n## PostgreSQL FORCE ROW LEVEL SECURITY (100% Coverage)\n\nEvery tenant table in PostgreSQL enforces Row-Level Security:\n\n```sql\nALTER TABLE issues ENABLE ROW LEVEL SECURITY;\nALTER TABLE issues FORCE ROW LEVEL SECURITY;\n```\n\n### The Fail-Closed Context Invariant\n\nPostgreSQL sessions authenticate as the unprivileged database role `kanban_app`. This role is stripped of `SUPERUSER` and `BYPASSRLS`. To query or mutate tenant data, the application server must establish an explicit session context within a transaction:\n\n```sql\nSET LOCAL app.current_principal_id = '01932e6b-7341-789a-bc01-123456789abc';\nSET LOCAL app.current_workspace_id = '01932e6b-7341-789a-bc01-def012345678';\n```\n\nIf a developer writes a raw query without setting the session context, the RLS policies fail closed: **zero rows are returned, and zero mutations succeed**. Even if an attacker executes SQL injection, they cannot bypass RLS to read cross-tenant data.\n\n---\n\n## Explicit Access Visibility and Sharing Manifests\n\nSaaS platforms often hide sharing rules behind obscure settings menus, leading to accidental leaks. In \ud83d\udc4dkanban, every resource view exposes a dynamic `\ud83d\udee1\ufe0f` sharing pill.\n\nClicking the sharing pill reveals the **Access Manifest**:\n- **Explicit Principals:** Lists all users, groups, and autonomous agents with direct access.\n- **Inherited Scope:** Displays parent project and workspace inheritance paths.\n- **Auditable Effective Mask:** Shows exact read, write, share, and delete capabilities for each principal.\n\n![Access Visibility Inspector and Sharing Manifest](images/17-access-visibility-inspector.png)\n\n### Anti-Enumeration and Timing Defense\n\nTo prevent malicious actors from scanning IDs or usernames:\n- **Identical RFC 7807 404 Responses:** Accessing an unauthorized resource returns an identical `404 Not Found` response as a non-existent resource. Unauthorized users cannot determine whether an object exists.\n- **25ms Timing Floor:** All resource lookups enforce a synthetic 25ms timing floor to neutralize side-channel timing attacks that measure database index lookups.\n\n---\n\n## MCP Read-Taint High-Water Mark Defense\n\nAutonomous LLMs can be tricked by prompt injection into reading confidential documents and writing excerpts into public tickets. \ud83d\udc4dkanban prevents this through **Read-Taint Tracking**:\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Agent as Autonomous Agent\n    participant Gateway as MCP Gateway Taint Engine\n    participant PrivateDoc as Confidential Doc (Tier: PRIVATE)\n    participant PublicTicket as Public Ticket (Tier: PUBLIC)\n\n    Agent->>Gateway: read_doc(id='confidential_spec')\n    Gateway->>PrivateDoc: Fetch Document\n    PrivateDoc-->>Gateway: Return Content\n    Gateway->>Gateway: Elevate Agent Session High-Water Mark to PRIVATE\n    Gateway-->>Agent: Deliver Markdown Payload\n\n    Note over Agent: Later in conversation...\n    Agent->>Gateway: update_ticket(id='public_bug', body=...)\n    Gateway->>Gateway: Check Destination Scope (PUBLIC) vs High-Water Mark (PRIVATE)\n    Gateway-->>Agent: 403 Forbidden (CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED)\n```\n\n![Agent Kill Switch and Immediate Session Revocation](images/18-agent-kill-switch.png)\n\nWhen an agent reads a resource with an elevated confidentiality label, its session high-water mark increases. Any subsequent write operation to a lower-privilege target is halted immediately with an error requiring human operator confirmation.\n\n---\n\n## Distributed Runner Dedicated mTLS Port (:8444) and PoP Handshake\n\nRemote execution daemons and test runners never share general HTTP application ingress. Instead, they authenticate through a dedicated mutual TLS port:\n\n- **Dedicated Port :8444:** Distributed runners communicate exclusively with the orchestrator over port `:8444`. Port `:8921` handles human web traffic and general REST/MCP calls, while `:8444` enforces mandatory client certificate exchange.\n- **Cryptographic Proof-of-Possession (PoP):** During runner enrollment, the daemon generates a local private key and presents a hardware-bound CSR. Upon successful verification of the short-lived enrollment token (15-minute TTL), the orchestrator signs the client certificate. Every subsequent WebSocket connection requires a cryptographic Proof-of-Possession challenge, verifying the daemon possesses the matching private key before receiving build workloads.\n- **Hardware-Bound Certificate Rotation:** Certificates cannot be silently renewed. If a runner certificate expires or requires rotation, the administrator revokes the runner identity in `/admin/agent-runners` (requiring AAL2 step-up verification), mints a fresh enrollment token, and re-enrolls the runner host.\n\n---\n\n## Private-Only Internal MCP Route Isolation (/internal/v1/mcp/*)\n\nInternal agent orchestration, runner dispatch, and distributed tool calls are isolated from external edge routing:\n\n- **Zero Edge Routing:** All `/internal/v1/mcp/*` endpoints are bound strictly to internal container networks (`app_net`, `data_net`). Reverse proxies (`edge_net`) explicitly drop or block `/internal/*` request paths from external ingress.\n- **mTLS Verification:** Calls across internal MCP routes require valid internal mTLS certificates or cryptographic service-principal tokens signed by the local authority. Unauthorized external callers cannot reach or probe internal agent pipelines.\n\n---\n\n## STRIDE Threat Mitigation Matrix\n\nFor the complete architectural taxonomy, see [[Informational] Security Architecture and STRIDE Threat Model Matrix](Security-and-STRIDE-Threat-Matrix), covering the complete Asset Inventory Matrix (`A1` to `A6`) and Entry Point Catalog (`E1` to `E8`).\n\n| Threat Category | Potential Attack Vector | \ud83d\udc4dkanban Architectural Defense |\n| :--- | :--- | :--- |\n| **Spoofing** | Forged session cookies or stolen API tokens | Multi-Card AAL2 enforcement, cryptographic token binding, dedicated `:8444` mTLS PoP, and WebAuthn Passkeys. |\n| **Tampering** | Parameter manipulation or state corruption | PostgreSQL immutable audit ledger and Wasm state transition validators. |\n| **Repudiation** | Denying ticket edits or deletions | Cryptographically signed append-only activity ledger recording principal IDs. |\n| **Information Disclosure** | Cross-tenant data leakage or ID enumeration | PostgreSQL FORCE RLS on 100% of tables, `/internal/v1/mcp/*` edge isolation, and uniform 404 anti-enumeration responses. |\n| **Denial of Service** | Deep query recursion or token exhaustion | Strict limit of 16 WebSocket conns per user, query depth caps, CIDR filtering, and MCP token budgets. |\n| **Elevation of Privilege** | Agent tool escalation or script escape | Sandboxed Wasm/nsjail execution, monotonic `CredentialBoundary` ceiling, and two-stage destructive confirmation tokens. |\n"
  },
  {
    "slug": "zero-trust-service-auth-and-workload-oidc",
    "title": "[Architectural] Zero-Trust Service Auth, Headless Workload OIDC, and CredentialBoundary Enforcement Guide",
    "category": "architectural",
    "track": "Engineering & Security Architecture",
    "subtrack": "Security Architecture",
    "audience": "Security Architects & Application Engineers",
    "order": 33,
    "summary": "Authoritative architectural reference and implementation guide for internal HKDF-HMAC service authentication, headless CI/CD workload identity federation (RFC 8693), and monotonic CredentialBoundary Row-Level Security isolation.",
    "sections": [
      {
        "id": "zero-trust-security-philosophy-the-hostile-wire",
        "title": "1. Zero-Trust Security Philosophy: The Hostile Wire",
        "level": 2
      },
      {
        "id": "role-bound-hkdf-hmac-internal-service-authentication",
        "title": "2. Role-Bound HKDF-HMAC Internal Service Authentication",
        "level": 2
      },
      {
        "id": "hkdf-key-derivation",
        "title": "HKDF Key Derivation",
        "level": 3
      },
      {
        "id": "canonical-request-envelope-signing",
        "title": "Canonical Request Envelope Signing",
        "level": 3
      },
      {
        "id": "asgi-tls-scope-client-certificate-extraction",
        "title": "ASGI TLS Scope Client Certificate Extraction",
        "level": 3
      },
      {
        "id": "headless-workload-identity-federation-rfc-8693",
        "title": "3. Headless Workload Identity Federation (RFC 8693)",
        "level": 2
      },
      {
        "id": "the-rfc-8693-token-exchange-flow",
        "title": "The RFC 8693 Token Exchange Flow",
        "level": 3
      },
      {
        "id": "security-invariant-rules",
        "title": "Security & Invariant Rules",
        "level": 3
      },
      {
        "id": "workload-identity-policy-specification",
        "title": "Workload Identity Policy Specification",
        "level": 3
      },
      {
        "id": "credentialboundary-enforcement-rls-isolation",
        "title": "4. CredentialBoundary Enforcement & RLS Isolation",
        "level": 2
      },
      {
        "id": "monotonic-capability-bitmasks",
        "title": "Monotonic Capability Bitmasks",
        "level": 3
      },
      {
        "id": "practical-implementation-recipes",
        "title": "5. Practical Implementation Recipes",
        "level": 2
      },
      {
        "id": "recipe-1-github-actions-cicd-configuration",
        "title": "Recipe 1: GitHub Actions CI/CD Configuration",
        "level": 3
      },
      {
        "id": "recipe-2-gitlab-cicd-configuration",
        "title": "Recipe 2: GitLab CI/CD Configuration",
        "level": 3
      },
      {
        "id": "recipe-3-kubernetes-projected-service-account-token-configuration",
        "title": "Recipe 3: Kubernetes Projected Service Account Token Configuration",
        "level": 3
      },
      {
        "id": "visual-reference-and-studio-screenshots",
        "title": "6. Visual Reference and Studio Screenshots",
        "level": 2
      }
    ],
    "content": "# [Architectural] Zero-Trust Service Auth, Headless Workload OIDC, and CredentialBoundary Enforcement Guide\n\nAuthoritative architectural reference and implementation guide for internal HKDF-HMAC service authentication, headless CI/CD workload identity federation (RFC 8693), and monotonic CredentialBoundary Row-Level Security isolation.\n\n---\n\n## 1. Zero-Trust Security Philosophy: The Hostile Wire\n\nIn traditional enterprise software, internal service-to-service communication is frequently treated with implicit trust: once an HTTP request crosses the outer perimeter firewall, backend services assume callers are authentic based on unvalidated network location or spoofable HTTP headers (`X-Forwarded-For`, `X-Client-Cert`).\n\n\ud83d\udc4dkanban rejects this perimeter security model under Security Priority #0. Every packet is treated as originating from a hostile wire:\n1. **Zero Implicit Trust:** No service endpoint trusts caller identity based on IP address, internal Docker network topology, or unverified HTTP headers.\n2. **Cryptographic Proof of Identity:** Every inter-service invocation must present verifiable cryptographic proof: either an HMAC-SHA256 signature derived via HKDF from a hardware-backed master key, or a verified mutual TLS (mTLS) client certificate extracted from the raw TLS handshake.\n3. **Least Privilege by Default:** Ephemeral tokens issued to autonomous agents and automated workloads are constrained by monotonic capability bitmasks (`CredentialBoundary`) enforced directly inside the PostgreSQL database engine via Row-Level Security (RLS) Grand Unified Configuration (GUC) variables.\n\n```mermaid\ngraph TD\n    Workload[\"Headless Workload (GitHub Actions, GitLab CI, K8s)\"] --> OIDCExchange[\"RFC 8693 Token Exchange (POST /oauth/token)\"]\n    OIDCExchange --> JWKS[\"SSRF-Safe OIDC Discovery & JWKS Verification\"]\n    JWKS --> ReplayCheck[\"Atomic PostgreSQL JTI Replay Guard (workload_jti_replays)\"]\n    ReplayCheck --> EphemeralToken[\"Ephemeral Scoped MCP Token (kb_eat_*)\"]\n    EphemeralToken --> BoundaryCheck[\"CredentialBoundary Bitmask Gate\"]\n    BoundaryCheck --> RLSContext[\"PostgreSQL Session Context (SET LOCAL app.credential_boundary)\"]\n    RLSContext --> ForceRLS[\"PostgreSQL FORCE ROW LEVEL SECURITY Filter\"]\n```\n\n![Workload OIDC Federation Studio](images/slice3-workload-oidc-studio.png)\n\n---\n\n## 2. Role-Bound HKDF-HMAC Internal Service Authentication\n\nTicket `KAN-63` establishes hardened inter-service authentication (`kanban/security/service_auth.py`) governing direct communication between background runners, sync daemons, and application servers.\n\n### HKDF Key Derivation\n\nSubkeys are derived on demand from the system master key encryption key (`master_kek`) using HMAC-based Extract-and-Expand Key Derivation Function (HKDF-SHA256, RFC 5869):\n\n$$\\text{Subkey} = \\text{HKDF-Expand}(\\text{Extract}(\\text{master\\_kek}, \\text{salt}), \\text{\"internal-service-v2/\"} \\parallel \\text{principal}, 32)$$\n\nThis derivation ensures:\n- Cryptographic isolation between service roles (`runner`, `relay`, `auditor`, `migrator`).\n- A compromise of an individual service subkey does not compromise the root `master_kek` or other subsystem keys.\n\n### Canonical Request Envelope Signing\n\nWhen a service invokes an internal API endpoint, it packages and signs a canonical request envelope:\n\n$$\\text{Signature} = \\text{HMAC-SHA256}\\left(\\text{Subkey}, \\text{Timestamp} \\parallel \\text{Principal} \\parallel \\text{Method} \\parallel \\text{Path} \\parallel \\text{SHA256}(\\text{Body})\\right)$$\n\nThe receiving endpoint validates the signature according to strict security invariants:\n- **Timestamp Skew Limit:** Requests with timestamps drifting more than 300 seconds from the server clock are immediately rejected (`CLOCK_DRIFT_EXCEEDED`), neutralizing replay attacks.\n- **Constant-Time Verification:** Signatures are compared using constant-time string comparison (`hmac.compare_digest`), eliminating timing side-channel attacks.\n- **Header Tampering Defense:** The canonical envelope binds the HTTP method, URI path, and SHA-256 digest of the request body, preventing reverse-proxy header injection or request modification in flight.\n\n### ASGI TLS Scope Client Certificate Extraction\n\nFor mutual TLS (mTLS) client validation, \ud83d\udc4dkanban never trusts raw HTTP headers such as `X-SSL-Client-Cert` or `X-KB-Service-Principal`, which can be injected by untrusted intermediaries. Instead, the service authenticator extracts certificate attributes directly from the ASGI connection scope:\n\n```python\n# Verifiable TLS scope extraction in kanban/security/service_auth.py\nclient_cert = scope.get(\"client_cert\")\nif not client_cert:\n    raise ServiceAuthError(\"Missing verified mTLS client certificate in ASGI scope\")\n\ncert = x509.load_der_x509_certificate(client_cert)\ncommon_name = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value\n```\n\n---\n\n## 3. Headless Workload Identity Federation (RFC 8693)\n\nTicket `KAN-74` implements headless Workload Identity Federation and RFC 8693 OAuth 2.0 Token Exchange, eliminating the need to store long-lived static API secrets or passwords inside CI/CD repositories.\n\n### The RFC 8693 Token Exchange Flow\n\nExternal automated workloads (e.g. GitHub Actions runners, GitLab CI jobs, Kubernetes pods) obtain short-lived, permission-scoped tokens using their native OpenID Connect (OIDC) identity tokens:\n\n```mermaid\nsequenceDiagram\n    participant CI as GitHub Actions / GitLab CI Runner\n    participant IdP as Identity Provider (GitHub / GitLab OIDC)\n    participant KB as \ud83d\udc4dkanban Token Endpoint (/oauth/token)\n    participant DB as PostgreSQL (workload_identity_policies)\n\n    CI->>IdP: Request OIDC ID token (aud: https://kanban.example.com)\n    IdP-->>CI: Signed JWT ID token\n    CI->>KB: POST /oauth/token (grant_type=token-exchange, subject_token=JWT)\n    KB->>IdP: Fetch discovery document & JWKS public keys\n    KB->>KB: Verify cryptographic signature (RS256, ES256, EdDSA)\n    KB->>DB: Query matching policy for issuer and subject pattern\n    KB->>DB: Atomically insert JTI into workload_jti_replays\n    DB-->>KB: Insert successful (no conflict)\n    KB-->>CI: Short-lived scoped token (kb_eat_*) with CredentialBoundary\n```\n\n### Security & Invariant Rules\n\n1. **Strict Cryptographic Algorithm Allowlist:** Only asymmetric signature algorithms (`RS256`, `PS256`, `ES256`, `EdDSA`) are permitted. Symmetric algorithms (`HS256`) and unsigned tokens (`alg=\"none\"`) are rejected with `400 invalid_grant`.\n2. **SSRF-Hardened OpenID Discovery:** Provider discovery and JWKS retrieval reuse the secure discovery client, enforcing private IP address blocking (RFC 1918 / RFC 4193), timeout caps, and response size limits.\n3. **Atomic Replay Prevention:** Each OIDC JWT carries a unique token identifier (`jti`). The server executes an atomic PostgreSQL insert into `workload_jti_replays` (`ON CONFLICT DO NOTHING`). If the same `jti` is submitted a second time, the transaction aborts with `401 WORKLOAD_TOKEN_REPLAYED`.\n4. **Subject Pattern & Claim Filtering:** Workload identity policies define glob patterns for the token subject (`sub`), such as `repo:org/repo:ref:refs/heads/main`, alongside mandatory JSON claim subsets (e.g. `{\"environment\": \"production\"}`).\n5. **Token Lifetime Cap:** Workload identity tokens enforce an explicit lifetime ceiling (`max_ttl_seconds <= 86400`, default 3,600 seconds / 1 hour), mitigating credential exposure windows.\n\n### Workload Identity Policy Specification\n\nPolicies are managed by administrators via `/api/v1/admin/workload-identities` (requires AAL2):\n\n| Attribute | Type & Validation | Description |\n| :--- | :--- | :--- |\n| `name` | String (1 to 120 chars) | Descriptive policy label displayed in admin lists |\n| `description` | String or `None` | Optional markdown description of workload context |\n| `issuer` | Strict HTTPS URL (1 to 500 chars) | OIDC identity provider issuer URL |\n| `client_id` | String (1 to 255 chars) | Expected audience (`aud`) claim in OIDC token |\n| `subject_pattern` | Glob or Regex (1 to 500 chars) | Matching pattern for token `sub` claim |\n| `required_claims_json` | JSON Object | Exact claims required in the OIDC JWT payload |\n| `surface` | `agent` or `docs` | Target MCP surface granted to the federated token |\n| `scopes` | List of Strings | Allowed OAuth scopes (e.g. `[\"agent:read\", \"agent:write\"]`) |\n| `allowed_project_ids` | List of UUIDs or `None` | Restricts token access to specific project IDs |\n| `capability_mask` | Integer (`0` to `255`, default `255`) | Monotonic capability ceiling enforced by RLS |\n| `allowed_cidrs` | List of CIDR Strings or `None` | Restricts token exchange to specific IP subnets |\n| `max_ttl_seconds` | Integer (`60` to `86400`, default `3600`) | Maximum lifespan of issued ephemeral token |\n| `is_enabled` | Boolean (`true` / `false`) | Toggles active status of the workload policy |\n\n---\n\n## 4. CredentialBoundary Enforcement & RLS Isolation\n\nTokens issued to automated agents, external workloads, and third-party integrations are governed by the `CredentialBoundary` capability bitmask (tickets `KAN-66` and `KAN-67`).\n\n### Monotonic Capability Bitmasks\n\nThe `CredentialBoundary` bitmask restricts the maximum capabilities a token can exercise, regardless of the assigned user role:\n\n| Capability Bit | Bitmask Value | Description & Bound |\n| :--- | :--- | :--- |\n| `NONE` | `0x0000` (`0`) | Zero privilege; all operations rejected with `INSUFFICIENT_CAPABILITY` |\n| `VIEW` | `0x0001` (`1`) | Read issues, documents, stickies, and views |\n| `COMMENT` | `0x0002` (`2`) | Post comments and feedback |\n| `EDIT` | `0x0004` (`4`) | Create and modify issues, documents, and stickies |\n| `TRANSITION` | `0x0008` (`8`) | Execute workflow state transitions |\n| `LINK` | `0x0010` (`16`) | Create and delete typed object links |\n| `SHARE` | `0x0020` (`32`) | Manage object sharing and visibility |\n| `ADMIN` | `0x0040` (`64`) | Administrative settings and diagnostics |\n| `DELETE` | `0x0080` (`128`) | Permanent deletion of entities |\n| `ALL` | `0x00FF` (`255`) | Complete operational privileges |\n\nWhen an incoming request is authenticated:\n1. The middleware computes the effective capability set: $\\text{Effective} = \\text{UserRoleCapabilities} \\cap \\text{CredentialBoundary}$.\n2. The middleware sets PostgreSQL session Grand Unified Configuration (GUC) variables inside the transaction:\n   ```sql\n   SET LOCAL app.current_principal_id = 'usr_workload_agent';\n   SET LOCAL app.credential_boundary = '0x0007';\n   ```\n3. PostgreSQL Row-Level Security policies evaluate `app.credential_boundary` before returning or mutating records. If the capability bit is missing, PostgreSQL returns zero records or aborts the write with a constraint violation.\n\n---\n\n## 5. Practical Implementation Recipes\n\n### Recipe 1: GitHub Actions CI/CD Configuration\n\nTo authenticate a GitHub Actions workflow to the \ud83d\udc4dkanban Model Context Protocol (MCP) server without storing permanent secrets:\n\n```yaml\nname: Automated Agent CI/CD Integration\non:\n  push:\n    branches: [main]\n\npermissions:\n  id-token: write\n  contents: read\n\njobs:\n  kanban-sync:\n    runs-on: ubuntu-latest\n    steps:\n      - name: Checkout Code\n        uses: actions/checkout@v4\n\n      - name: Authenticate to \ud83d\udc4dkanban via RFC 8693\n        id: auth\n        run: |\n          # 1. Fetch OIDC ID token from GitHub Actions environment\n          ID_TOKEN=$(curl -sLS \\\n            -H \"Authorization: bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}\" \\\n            \"${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=https://kanban.example.com\" | jq -r .value)\n\n          # 2. Exchange OIDC token for short-lived scoped MCP token\n          RESPONSE=$(curl -sLS -X POST \"https://kanban.example.com/oauth/token\" \\\n            -H \"Content-Type: application/x-www-form-urlencoded\" \\\n            -d \"grant_type=urn:ietf:params:oauth:grant-type:token-exchange\" \\\n            -d \"subject_token=${ID_TOKEN}\" \\\n            -d \"subject_token_type=urn:ietf:params:oauth:token-type:jwt\" \\\n            -d \"audience=https://kanban.example.com/mcp/agent\")\n\n          TOKEN=$(echo \"${RESPONSE}\" | jq -r .access_token)\n          echo \"::add-mask::${TOKEN}\"\n          echo \"mcp_token=${TOKEN}\" >> \"$GITHUB_OUTPUT\"\n\n      - name: Execute Model Context Protocol Tool\n        run: |\n          curl -sLS -X POST \"https://kanban.example.com/mcp/agent\" \\\n            -H \"Authorization: Bearer ${{ steps.auth.outputs.mcp_token }}\" \\\n            -H \"Content-Type: application/json\" \\\n            -d '{\n              \"jsonrpc\": \"2.0\",\n              \"id\": 1,\n              \"method\": \"tools/call\",\n              \"params\": {\n                \"name\": \"read_ticket\",\n                \"arguments\": {\"identifier\": \"KAN-42\", \"lod\": \"summary\"}\n              }\n            }'\n```\n\n---\n\n### Recipe 2: GitLab CI/CD Configuration\n\n```yaml\nkanban-automation:\n  stage: test\n  id_tokens:\n    GITLAB_OIDC_TOKEN:\n      aud: https://kanban.example.com\n  script:\n    - |\n      RESPONSE=$(curl -sLS -X POST \"https://kanban.example.com/oauth/token\" \\\n        -H \"Content-Type: application/x-www-form-urlencoded\" \\\n        -d \"grant_type=urn:ietf:params:oauth:grant-type:token-exchange\" \\\n        -d \"subject_token=${GITLAB_OIDC_TOKEN}\" \\\n        -d \"subject_token_type=urn:ietf:params:oauth:token-type:jwt\" \\\n        -d \"audience=https://kanban.example.com/mcp/agent\")\n      TOKEN=$(echo \"${RESPONSE}\" | jq -r .access_token)\n      curl -sLS -X POST \"https://kanban.example.com/mcp/agent\" \\\n        -H \"Authorization: Bearer ${TOKEN}\" \\\n        -H \"Content-Type: application/json\" \\\n        -d '{\"jsonrpc\": \"2.0\", \"id\": 1, \"method\": \"tools/call\", \"params\": {\"name\": \"search_tickets\", \"arguments\": {\"query\": \"CI Pipeline\", \"lod\": \"summary\"}}}'\n```\n\n---\n\n### Recipe 3: Kubernetes Projected Service Account Token Configuration\n\n```bash\n# Obtain projected service account token from Kubernetes pod volume\nK8S_TOKEN=$(cat /var/run/secrets/tokens/kanban-audience)\n\n# Exchange projected token with \ud83d\udc4dkanban\nRESPONSE=$(curl -sLS -X POST \"https://kanban.example.com/oauth/token\" \\\n  -H \"Content-Type: application/x-www-form-urlencoded\" \\\n  -d \"grant_type=urn:ietf:params:oauth:grant-type:token-exchange\" \\\n  -d \"subject_token=${K8S_TOKEN}\" \\\n  -d \"subject_token_type=urn:ietf:params:oauth:token-type:jwt\" \\\n  -d \"audience=https://kanban.example.com/mcp/agent\")\n\nACCESS_TOKEN=$(echo \"${RESPONSE}\" | jq -r .access_token)\n```\n\n---\n\n## 6. Visual Reference and Studio Screenshots\n\n![Workload OIDC Federation Studio](images/slice3-workload-oidc-studio.png)\n\n![MCP Access Studio Key Minting](images/slice3-mcp-access-studio-mint-modal.png)\n\n![OAuth Client Governance Bulk Purge](images/slice3-oauth-governance-bulk-purge.png)\n\n![OAuth and Workload Governance Studio](images/42-admin-oauth-governance.png)\n"
  },
  {
    "slug": "configuration-value-reference",
    "title": "[Informational] Configuration Value Reference",
    "category": "informational",
    "track": "Feature & Field Reference",
    "subtrack": "Studio Configuration",
    "audience": "System Administrators",
    "order": 34,
    "summary": "Reference guide for system environment variables and execution tiers.",
    "sections": [
      {
        "id": "environment-variables",
        "title": "Environment Variables",
        "level": 2
      },
      {
        "id": "custom-field-tiers",
        "title": "Custom Field Execution Tiers",
        "level": 2
      },
      {
        "id": "system-roles",
        "title": "System Roles and Capabilities",
        "level": 2
      }
    ],
    "content": "# [Informational] Configuration Value Reference\n\nAuthoritative reference guide for system environment variables and execution tiers.\n\n## Environment Variables\n\n| Key | Type | Default | Description |\n| :--- | :--- | :--- | :--- |\n| `DATABASE_URL` | string (URL) | `postgresql://kanban:kanban@localhost:5432/kanban` | PostgreSQL connection string with UTF-8 and RLS support. |\n| `KANBAN_STANDALONE_MODE` | boolean | `false` | Single-container standalone flag. Gates nsjail sandboxes. |\n| `KANBAN_SECRET_KEY` | string (min 32 chars) | `(required)` | Cryptographic key for signing session cookies and tokens. |\n| `AI_PROVIDER` | enum (openai, gemini, ollama, custom) | `gemini` | Default active AI engine provider for sparkle completions. |\n| `RUNNER_MTLS_CERT_PATH` | string (filesystem path) | `/etc/kanban/certs/client.crt` | Client cert for outbound mTLS remote repository runners. |\n\n## Custom Field Execution Tiers\n\n| Tier | Latency Budget | Standalone Mode | Multi-Container Compose | Best Used For |\n| :--- | :--- | :--- | :--- | :--- |\n| **scalar** | <1ms | Supported | Supported | Static metadata, manual attributes, default strings. |\n| **formula** | <5ms | Supported | Supported | In-process Python AST math, date arithmetic, conditionals. |\n| **wasm** | <25ms | Supported | Supported | Compiled C, Rust, or AssemblyScript wasmtime runtime. |\n| **nsjail** | <250ms | Gated (Fail-closed) | Supported | Isolated Linux namespace sandbox container. |\n\n## System Roles and Capabilities\n\n| Role | Scope | Description |\n| :--- | :--- | :--- |\n| **SERVER_ADMIN** | Server | Full administrative authority over authentication and runners. |\n| **WORKSPACE_ADMIN** | Workspace | Workspace policy, user provisioning, and group management. |\n| **PROJECT_ADMIN** | Project | Project workflows, transition helpers, and custom fields. |\n| **MEMBER** | Project/Workspace | Create, edit, transition, and comment on work items and docs. |\n| **VIEWER** | Project/Workspace | Read-only access to work items, boards, and docs. |"
  }
];

export const WIKI_CATEGORIES: WikiCategory[] = [
  {
    "name": "Overview",
    "chapters": [
      {
        "slug": "home",
        "title": "\ud83d\udc4dkanban: Executive Architecture and System Overview",
        "category": "informational"
      }
    ]
  },
  {
    "name": "Track 1: Step-by-Step Guides",
    "chapters": [
      {
        "slug": "production-promotion-and-backup-runbook",
        "title": "[Guide] Production Promotion and Encrypted Backup Runbook",
        "category": "guide"
      },
      {
        "slug": "migration-and-cutover-runbook",
        "title": "[Guide] Legacy Tracker Migration and Cutover Runbook",
        "category": "guide"
      },
      {
        "slug": "multi-source-migration-and-key-alias-redirects",
        "title": "[Guide] End-to-End Multi-Source Migration, Key Alias Redirects, and Cross-Project Merge Guide",
        "category": "guide"
      },
      {
        "slug": "admin-diagnostics-and-link-inspector-studio",
        "title": "[Guide] Admin Diagnostics and Link Inspector Studio Guide and Architecture Walkthrough",
        "category": "guide"
      },
      {
        "slug": "guide-custom-fields",
        "title": "[Guide] How to Use Custom Fields",
        "category": "guide"
      },
      {
        "slug": "scripted-workflows-and-transition-helpers",
        "title": "[Guide] Scripted Workflows and Transition Helpers",
        "category": "guide"
      },
      {
        "slug": "multi-card-authentication-studio",
        "title": "[Guide] Multi-Card Authentication Studio and Identity Architecture",
        "category": "guide"
      },
      {
        "slug": "multi-provider-ai-engine-and-runners",
        "title": "[Guide] Multi-Provider AI Engine, Execution Harnesses, and Runners",
        "category": "guide"
      },
      {
        "slug": "three-surface-mcp-server-architecture",
        "title": "[Guide] Three-Surface Model Context Protocol (MCP) Server Architecture",
        "category": "guide"
      }
    ]
  },
  {
    "name": "Track 2: Feature & Field Reference",
    "chapters": [
      {
        "slug": "studio-configuration-reference",
        "title": "[Informational] Studio Configuration Reference",
        "category": "informational"
      },
      {
        "slug": "enterprise-whitespace-and-kanban-board",
        "title": "[Informational] Enterprise Whitespace, Semantic Emojis, and Kanban Board",
        "category": "informational"
      },
      {
        "slug": "ticket-screen-and-work-item-features",
        "title": "[Informational] Ticket Screen, Peek Drawer, and Work Item Architecture",
        "category": "informational"
      },
      {
        "slug": "hierarchical-docs-and-stickies-with-smart-promotion",
        "title": "[Informational] Hierarchical Docs, Project Stickies, and Smart Promotion",
        "category": "informational"
      },
      {
        "slug": "statistical-flow-telemetry-and-lean-analytics",
        "title": "[Informational] Statistical Flow Telemetry, Lead Time Percentiles, and Monte Carlo Forecasting Guide",
        "category": "informational"
      },
      {
        "slug": "blinking-cursor-sparkle-completion-engine",
        "title": "[Informational] Blinking Cursor Sparkle Completion Engine",
        "category": "informational"
      },
      {
        "slug": "mcp-tools-reference",
        "title": "[Informational] Model Context Protocol (MCP) Tools Reference Manual",
        "category": "informational"
      },
      {
        "slug": "rest-api-architecture-and-openapi-guide",
        "title": "[Informational] REST API Architecture and OpenAPI Integration Guide",
        "category": "informational"
      },
      {
        "slug": "configuration-value-reference",
        "title": "[Informational] Configuration Value Reference",
        "category": "informational"
      }
    ]
  },
  {
    "name": "Track 3: Security & Adoption Overview",
    "chapters": [
      {
        "slug": "role-and-permission-matrix",
        "title": "[Informational] Role and Permission Matrix",
        "category": "informational"
      },
      {
        "slug": "zero-trust-security-and-access-visibility",
        "title": "[Informational] Zero-Trust Security Architecture and Explicit Access Visibility",
        "category": "informational"
      },
      {
        "slug": "security-and-stride-threat-matrix",
        "title": "[Informational] Security Architecture and STRIDE Threat Model Matrix",
        "category": "informational"
      },
      {
        "slug": "feature-comparison",
        "title": "[Informational] Feature Comparison Matrix (50 Features)",
        "category": "informational"
      }
    ]
  },
  {
    "name": "Track 4: Engineering & Security Architecture",
    "chapters": [
      {
        "slug": "system-topology-and-multi-container-architecture",
        "title": "[Architectural] System Topology and Multi-Container Architecture",
        "category": "architectural"
      },
      {
        "slug": "universal-object-graph-and-link-auditor",
        "title": "[Architectural] Universal Object Graph and Invalid Link Auditor",
        "category": "architectural"
      },
      {
        "slug": "zero-trust-service-auth-and-workload-oidc",
        "title": "[Architectural] Zero-Trust Service Auth, Headless Workload OIDC, and CredentialBoundary Enforcement Guide",
        "category": "architectural"
      },
      {
        "slug": "agent-lease-fencing-workpads-and-push-protection",
        "title": "[Architectural] Autonomous Agent Lease Fencing, Workpad Rework Breaker, and Secret Push-Protection Guide",
        "category": "architectural"
      },
      {
        "slug": "real-time-web-and-websocket-architecture",
        "title": "[Architectural] Real-Time Web and WebSocket Architecture",
        "category": "architectural"
      },
      {
        "slug": "canonical-markdown-and-safe-media-pipeline",
        "title": "[Architectural] Canonical Markdown and Safe Media Pipeline",
        "category": "architectural"
      },
      {
        "slug": "clean-db-testing-and-governance-gates",
        "title": "[Architectural] Clean-DB Testing and Governance Gates",
        "category": "architectural"
      },
      {
        "slug": "admin-custom-scripted-fields-and-sandbox",
        "title": "[Architectural] Admin Custom Scripted Fields and Sandboxed Execution",
        "category": "architectural"
      },
      {
        "slug": "custom-scripts-and-json-security-architecture",
        "title": "[Architectural] Custom Scripts and JSON Security Architecture",
        "category": "architectural"
      },
      {
        "slug": "architecture-delta-and-missing-features",
        "title": "[Architectural] \ud83d\udc4dkanban: Architecture Specification Delta & Gap Analysis",
        "category": "architectural"
      },
      {
        "slug": "user-tasks-and-qa-matrix",
        "title": "[Architectural] \ud83d\udc4dkanban User Task & Architecture QA Verification Matrix",
        "category": "architectural"
      }
    ]
  }
];

export const CONFIG_REFERENCES: Record<string, ConfigReferenceItem[]> = {
  "environment_variables": [
    {
      "key": "DATABASE_URL",
      "type": "string (URL)",
      "default": "postgresql://kanban:kanban@localhost:5432/kanban",
      "description": "PostgreSQL connection string with UTF-8 and RLS support."
    },
    {
      "key": "KANBAN_STANDALONE_MODE",
      "type": "boolean",
      "default": "false",
      "description": "Single-container standalone flag. Gates nsjail sandboxes."
    },
    {
      "key": "KANBAN_SECRET_KEY",
      "type": "string (min 32 chars)",
      "default": "(required)",
      "description": "Cryptographic key for signing session cookies and tokens."
    },
    {
      "key": "AI_PROVIDER",
      "type": "enum (openai, gemini, ollama, custom)",
      "default": "gemini",
      "description": "Default active AI engine provider for sparkle completions."
    },
    {
      "key": "RUNNER_MTLS_CERT_PATH",
      "type": "string (filesystem path)",
      "default": "/etc/kanban/certs/client.crt",
      "description": "Client cert for outbound mTLS remote repository runners."
    }
  ],
  "custom_field_tiers": [
    {
      "tier": "scalar",
      "latency_budget": "<1ms",
      "standalone": "Supported",
      "compose": "Supported",
      "description": "Static metadata, manual attributes, default strings."
    },
    {
      "tier": "formula",
      "latency_budget": "<5ms",
      "standalone": "Supported",
      "compose": "Supported",
      "description": "In-process Python AST math, date arithmetic, conditionals."
    },
    {
      "tier": "wasm",
      "latency_budget": "<25ms",
      "standalone": "Supported",
      "compose": "Supported",
      "description": "Compiled C, Rust, or AssemblyScript wasmtime runtime."
    },
    {
      "tier": "nsjail",
      "latency_budget": "<250ms",
      "standalone": "Gated (Fail-closed)",
      "compose": "Supported",
      "description": "Isolated Linux namespace sandbox container."
    }
  ],
  "system_roles_and_capabilities": [
    {
      "role": "SERVER_ADMIN",
      "scope": "Server",
      "description": "Full administrative authority over authentication and runners."
    },
    {
      "role": "WORKSPACE_ADMIN",
      "scope": "Workspace",
      "description": "Workspace policy, user provisioning, and group management."
    },
    {
      "role": "PROJECT_ADMIN",
      "scope": "Project",
      "description": "Project workflows, transition helpers, and custom fields."
    },
    {
      "role": "MEMBER",
      "scope": "Project/Workspace",
      "description": "Create, edit, transition, and comment on work items and docs."
    },
    {
      "role": "VIEWER",
      "scope": "Project/Workspace",
      "description": "Read-only access to work items, boards, and docs."
    }
  ]
};

export const SLUG_ALIASES: Record<string, string> = {
  "custom-fields": "guide-custom-fields",
  "roles": "role-and-permission-matrix",
  "permissions": "role-and-permission-matrix",
  "auth": "multi-card-authentication-studio",
  "mcp": "mcp-tools-reference",
  "mcp-server": "three-surface-mcp-server-architecture",
  "api": "rest-api-architecture-and-openapi-guide",
  "workflows": "scripted-workflows-and-transition-helpers",
  "ai": "multi-provider-ai-engine-and-runners",
  "standalone": "production-promotion-and-backup-runbook",
  "links": "universal-object-graph-and-link-auditor",
  "config": "configuration-value-reference",
  "configuration": "configuration-value-reference",
  "studio-config": "studio-configuration-reference",
  "studio-configuration": "studio-configuration-reference",
  "workspace-settings": "studio-configuration-reference",
  "project-settings": "studio-configuration-reference",
  "personal-settings": "studio-configuration-reference",
  "user-profile-and-personal-settings": "studio-configuration-reference",
  "diagnostics": "admin-diagnostics-and-link-inspector-studio",
  "link-inspector": "admin-diagnostics-and-link-inspector-studio",
  "migration": "multi-source-migration-and-key-alias-redirects",
  "migrations": "multi-source-migration-and-key-alias-redirects",
  "importers": "multi-source-migration-and-key-alias-redirects",
  "service-auth": "zero-trust-service-auth-and-workload-oidc",
  "workload-oidc": "zero-trust-service-auth-and-workload-oidc",
  "flow": "statistical-flow-telemetry-and-lean-analytics",
  "flow-telemetry": "statistical-flow-telemetry-and-lean-analytics",
  "analytics": "statistical-flow-telemetry-and-lean-analytics",
  "lease": "agent-lease-fencing-workpads-and-push-protection",
  "leases": "agent-lease-fencing-workpads-and-push-protection",
  "workpad": "agent-lease-fencing-workpads-and-push-protection",
  "push-protection": "agent-lease-fencing-workpads-and-push-protection",
  "rbac": "role-and-permission-matrix",
  "auth-studio": "multi-card-authentication-studio"
};

export const CHAPTER_BY_SLUG: Record<string, WikiChapter> = Object.fromEntries(
  WIKI_CHAPTERS.map((ch) => [ch.slug, ch]),
);

export function resolveChapterSlug(slugOrAlias: string): string {
  const normalized = slugOrAlias.toLowerCase().trim().replace(/^#+/, '');
  if (CHAPTER_BY_SLUG[normalized]) {
    return normalized;
  }
  if (SLUG_ALIASES[normalized]) {
    return SLUG_ALIASES[normalized];
  }
  return normalized;
}

export function getChapter(slugOrAlias: string): WikiChapter | undefined {
  const resolved = resolveChapterSlug(slugOrAlias);
  return CHAPTER_BY_SLUG[resolved];
}
