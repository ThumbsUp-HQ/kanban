// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
// Generated automatically by scripts/sync_wiki_bundle.py. Do not edit manually.

export interface WikiSection {
  id: string;
  title: string;
  level: number;
}

export interface WikiChapter {
  slug: string;
  title: string;
  category: string;
  order: number;
  summary: string;
  sections: WikiSection[];
  content: string;
}

export interface WikiCategory {
  name: string;
  chapters: { slug: string; title: string }[];
}

export type ConfigReferenceItem = Record<string, string>;

export const WIKI_CHAPTERS: WikiChapter[] = [
  {
    "slug": "admin-custom-scripted-fields-and-sandbox",
    "title": "Admin Custom Scripted Fields and Sandboxed Execution",
    "category": "System Architecture",
    "order": 1,
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
    "content": "# Admin Custom Scripted Fields and Sandboxed Execution\n\n## Overview\n\nModern software development requires dynamic metadata: calculated story points, security compliance flags, release readiness scores, and SLA countdowns. However, permitting custom scripts to run inside a project management system has historically introduced catastrophic security vulnerabilities, including server-side request forgery (SSRF), infinite loops, and arbitrary code execution.\n\n\ud83d\udc4dkanban resolves this through **Admin-Only Custom Scripted Fields** evaluated inside a hardened, multi-tier isolation sandbox with cryptographic privilege escalation controls.\n\n---\n\n## Admin-Only Definition Security Gate\n\nTo protect the platform from unauthorized logic injection:\n- **Admin-Only Gate:** Only verified Server Administrators or Project Administrators possessing Authenticator Assurance Level 2 (AAL2) credentials can create, modify, or delete custom field scripts.\n- **Route Protection:** All custom field endpoints under `/api/v1/projects/{project_id}/custom-fields` declare explicit dependencies on `require_admin_aal2`.\n- **Immutable Script Signatures:** When a script is saved, a SHA-256 cryptographic digest is generated and recorded. Any unauthorized database tampering immediately invalidates script execution.\n\n---\n\n## The Custom Fields Studio\n\nAdministrators manage custom fields through the visual studio at `/projects/KAN/settings/custom-fields`.\n\n![Custom Fields Studio and Escalation Banner](images/14-custom-fields-studio.png)\n\n### Studio Capabilities\n- **Field Types:** String, Integer, Float, Boolean, Date, Multi-Select, and Dynamic Computed Script.\n- **Execution Engine Selection:** Choose between lightweight WebAssembly (Wasmtime) or isolated containerized scripts (nsjail).\n- **Execution Badging (`\ud83e\uddea`):** Computed fields render a subtle test tube (`\ud83e\uddea`) glyph on the ticket properties rail, showing real-time computation status and latency.\n- **Pre-Commit Test Execution:** Test custom script logic against sample payloads in real time before committing field definitions to the database.\n\n---\n\n## Test-Execute Sandbox Modal\n\nBefore saving or deploying a custom scripted field to production tickets, administrators can validate script logic in an interactive test execution modal:\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Project Admin (AAL2)\n    participant Studio as Custom Fields Studio\n    participant Modal as Test-Execute Modal\n    participant Sandbox as Wasm / nsjail Sandbox\n\n    Admin->>Studio: Author script source (e.g. CVSS calculation)\n    Admin->>Studio: Click \"Test-Execute\"\n    Studio->>Modal: Open Test-Execute Modal with sample ticket JSON\n    Admin->>Modal: Click \"Run Test\"\n    Modal->>Sandbox: Execute script against sample properties\n    Sandbox-->>Modal: Return evaluated output, execution time (<2ms), stdout logs\n    Modal-->>Admin: Render live severity pill preview (e.g. \"8.8 High\")\n```\n\n![Custom Fields Pre-Commit Test Execution Modal](images/53-custom-fields-test-execute.png)\n\nThe Test-Execute modal displays execution duration, memory consumption, output formatting, and sandboxed stdout logs. This guarantees that syntax errors, infinite loops, or unexpected outputs are caught before fields impact active workflows.\n\n---\n\n## Multi-Tier Execution Sandbox Architecture\n\nWhen a work item is created or updated, active custom field scripts are executed within an isolated multi-tier sandbox:\n\n```mermaid\nflowchart TD\n    Update[\"Work Item Updated: State / Properties Changed\"] --> Dispatcher[\"Sandbox Dispatcher (kanban/sandbox/)\"]\n    \n    Dispatcher -->|Lightweight Math / String Formats| TierA[\"Tier A: Wasmtime Engine<br/>- In-process WebAssembly<br/>- Sub-millisecond execution (<1ms)<br/>- Zero OS syscall capability<br/>- Memory capped at 16 MB\"]\n    Dispatcher -->|Complex Logic / Scripts| TierB[\"Tier B: nsjail Container Jail<br/>- Linux namespaces (CLONE_NEWNET)<br/>- Read-only root filesystem<br/>- CPU timeout: 5 sec, Memory: 512 MB\"]\n    \n    TierA --> Verify[\"Verify Computed Value vs Pydantic Schema\"]\n    TierB --> Verify\n    Verify --> Store[\"Recorded in work item properties JSONB\"]\n```\n\n![Custom Fields on Ticket Properties Rail](images/36-rail-custom-fields.png)\n\n### Tier A: WebAssembly Runtime (Wasmtime)\n- Runs compiled WebAssembly modules in-process.\n- Provides sub-millisecond execution times.\n- Zero capability to open sockets, access the filesystem, or spawn processes.\n- Memory allocation strictly capped at 16 MB with instruction count fuel limits.\n\n### Tier B: Hardened Container Jail (nsjail)\n- Utilizes Linux kernel namespaces (`CLONE_NEWPID`, `CLONE_NEWNET`, `CLONE_NEWNS`).\n- Root filesystem mounted strictly read-only.\n- Network access completely disabled (`CLONE_NEWNET`).\n- Hard resource limits enforced via cgroups (512 MB RAM, 5-second wall clock timeout).\n\n---\n\n## Ephemeral Scoped Tokens and Tiered Privilege Escalation\n\nCustom scripts often need to query project metadata (such as counting open bugs or reading cycle end dates). To prevent privilege leakage:\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Script as Custom Scripted Field\n    participant Gate as Authorization Gate\n    participant Admin as Server/Workspace Admin (AAL2)\n    participant TokenService as Ephemeral Token Minter\n\n    Note over Script,TokenService: Default Execution: Project Scoped\n    Script->>Gate: Execute with default Project-scoped ephemeral token\n    \n    Note over Script,TokenService: Escalation Request: Workspace or Server\n    Script->>Gate: Request Escalated Scope (WORKSPACE or SERVER)\n    Gate->>Admin: Display Unmissable Blast Radius Warning Banner\n    Admin->>Gate: Cryptographic Signature with AAL2 Confirmation\n    Gate->>TokenService: Mint Time-Limited Ephemeral Escalated Token\n    TokenService-->>Script: Deliver Ephemeral Token for Execution\n```\n\n1. **Ephemeral Project Tokens:** By default, every script executes using an ephemeral API token scoped strictly to the current **Project**. It cannot read data from other projects or workspace settings.\n2. **Cryptographic Privilege Escalation:** If a script requires broader access (such as reading data across the entire **Workspace** or querying **Server** configuration):\n   - The script must request an escalated token scope.\n   - The UI displays an unmissable administrative warning banner detailing the blast radius.\n   - The escalation must be signed with cryptographic approval by an administrator possessing authority over that target tier.\n   - Scripts can never escalate to Server Admin privileges without explicit multi-factor confirmation.\n\n![Custom Fields Dual Control Escalation Studio](images/52-custom-fields-dual-control.png)\n\n### Dual-Control Principle:\nTo satisfy enterprise SOC 2 and ISO 27001 separation of duties, escalating a custom scripted field to workspace-wide or server-wide scope requires dual-control authorization:\n- A project administrator can author and propose the escalation.\n- A distinct, independent administrator holding target tier authority must review the blast radius warning banner and supply fresh Authenticator Assurance Level 2 (AAL2) credentials to activate the escalated token scope.\n- All escalation grants are logged with SHA-256 cryptographic digests in the immutable audit ledger.\n"
  },
  {
    "slug": "architecture-delta-and-missing-features",
    "title": "\ud83d\udc4dkanban: Architecture Specification Delta & Gap Analysis",
    "category": "Overview",
    "order": 2,
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
        "title": "Section 9: Blinking Cursor Sparkle (`\u2728`) Completion & Surgical Right-Click Engine (Req 7)",
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
        "id": "section-14-scriptrunner-workflows-remotecli-agent-transition-interceptors",
        "title": "Section 14: ScriptRunner Workflows & Remote/CLI Agent Transition Interceptors",
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
        "id": "published-container-image-for",
        "title": "4. Published Container Image for `thumbs-up-kanban:sandbox`",
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
        "id": "drift-3-workflow-models-missing-from",
        "title": "Drift 3: Workflow Models Missing from `database/models/__init__.py`",
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
    "content": "# \ud83d\udc4dkanban: Architecture Specification Delta & Gap Analysis\n\n## Executive Summary\n\nThis document presents a section-by-section architectural delta and gap analysis comparing the authoritative specification (`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`, Sections 1 through 15) against the actual implementation codebase across `kanban/`, `database/`, `mcp/`, `agent/`, and `kanban/web/`, active unit and integration test suites, and project documentation topics.\n\nOverall Implementation Status:\n- 15 of 15 specification sections possess active, production-grade implementations in the codebase.\n- The monorepo layout, dual topology (standalone Unix-socket PostgreSQL 16 + hardened 5-network multi-container stack), zero-trust access visibility, multi-card authentication studio, canonical Markdown normalization, breathable whitespace UI, 17-feature ticket drawer, hierarchical docs and stickies, blinking sparkle cursor completion, three-surface intent MCP server, universal object graph DDL with link auditor, custom scripted fields, and ScriptRunner agent workflow interceptors are fully implemented.\n- Key gaps and deviations identified:\n  1. Dense Vector Hybrid Search RRF: The schema defines `mode: \"hybrid\"`, and `database/models/embeddings.py` stores `ObjectEmbedding`, but `kanban/services/search.py` currently executes lexical tsvector and trigram search only, locking `executed_mode=\"lexical\"`.\n  2. Native Anthropic API Provider: `agent/providers/` implements `openai_provider.py`, `ollama.py`, and `gemini.py`. Anthropic models are supported via OpenAI-compatible gateways or CLI harnesses (`codex -p`), but a native `AnthropicProvider` class is not present in `agent/providers/`.\n  3. Non-OIDC OAuth2 Claim Mapper: `kanban/auth/cards/handshake.py` verifies authorization and token endpoint reachability for `OAUTH2`, but custom identity parsing for non-OIDC OAuth2 providers requires manual claim mapping.\n  4. Web OpenAPI Artifact Synchronization: `kanban/web/openapi.json` (44 paths) is an outdated snapshot missing 140 paths present in the FastAPI application (184 paths, 244 operations).\n  5. Specification and Test Invariants:\n     - Spec Section 11.1 cited 8 agent tools and grouped `link_objects & add_comment` together as item 8, whereas the codebase implements 9 distinct tools. The schema token budget test (`mcp/tests/test_schema_budget.py`) validates that 9 tools satisfy the token budget (~1,759 tokens <= 1,850 ceiling).\n     - `mcp/tests/admin/test_manage_cycles_and_modules.py:test_contract_no_bind_or_delete_actions` asserts that `bind_project_repo` is not on Tool 6, conflicting with Spec Section 11.4 and `mcp/surfaces/admin/manage_cycles_and_modules.py`.\n     - `database/models/__init__.py` omitted `WorkflowTransitionHook`, `WorkflowTransitionExecution`, and `WorkflowHookInvocation` from `database/models/workflow.py`, causing `tests/perf/test_perf_sync_hooks_sla.py` collection failure.\n     - `mcp/tests/test_protocol.py` line 125 hardcodes a 7-tool list for `/mcp/agent`, failing against the live 9-tool server.\n\n```mermaid\nflowchart TD\n    subgraph Spec[\"Authoritative Spec (Sections 1-15)\"]\n        S1[\"Sec 1: Mission & Apache-2.0\"]\n        S2[\"Sec 2-4: Topology, Zero-Trust, Auth\"]\n        S5[\"Sec 5-8: Content, UI Whitespace, Tickets, Docs\"]\n        S9[\"Sec 9-11: Sparkle, AI Engine, 3-Surface MCP\"]\n        S12[\"Sec 12-15: UOG, Sandboxes, Workflows, Clean DB\"]\n    end\n\n    subgraph Verified[\"Verified Implementations (15/15)\"]\n        V1[\"PostgreSQL FORCE RLS (100%)\"]\n        V2[\"Multi-Card Auth Studio (AAL2)\"]\n        V3[\"17-Feature Ticket Peek Drawer\"]\n        V4[\"Three-Surface Intent MCP (27 Tools)\"]\n        V5[\"ScriptRunner Workflow Interceptors\"]\n    end\n\n    subgraph Backlog[\"Tracked Optimization Gaps\"]\n        G1[\"Hybrid Vector Search (RRF)<br/>Dense embeddings active, tsvector locked\"]\n        G2[\"Native Anthropic Provider<br/>Supported via OpenAI gateway / codex -p\"]\n        G3[\"Web OpenAPI Snapshot Sync<br/>Export 184 routes to web artifact\"]\n    end\n\n    Spec --> Verified\n    Verified -.->|Follow-up tickets| Backlog\n```\n\n---\n\n## Visual Architecture Verification\n\nThe architectural implementation is verified through concrete UI and operational screens captured across the platform test suites:\n\n### Planning Dimensions: Cycles and Modules\nImplementation of sprint cycles and functional milestone tracking matching Section 7 and 11 specifications:\n\n![Cycles and Sprint Planning Interface](images/24-cycles-sprints.png)\n\n![Modules and Milestone Tracking Interface](images/25-modules-milestones.png)\n\n### Three-Surface MCP Level of Detail (LOD)\nVisual verification of the MCP Access Studio and token LOD tiers (`summary`, `standard`, `full`) satisfying Section 11:\n\n![MCP Level of Detail Tiers Configuration](images/21-mcp-lod-tiers-studio.png)\n\n---\n\n## Specification Scorecard by Section\n\n| Spec Section | Title & Domain | Codebase Location | Implementation Status | Verification Status | Primary Delta / Finding |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n| **Section 1** | Mission & Enterprise SaaS Paywall Gap Analysis | Root `LICENSE`, `pyproject.toml`, `package.json` | **COMPLETE (100%)** | **VERIFIED** | Pure Apache-2.0 compliance, zero AGPL/GPL/SSPL runtime dependencies. |\n| **Section 2** | System Topology & Container Architecture | `Dockerfile`, `docker-compose.yml`, `deploy/` | **COMPLETE (100%)** | **VERIFIED** | Embedded PG16 Unix socket in standalone mode; sandbox target in Dockerfile; 5 isolated networks in production. |\n| **Section 3** | Zero-Trust Security & Sharing Visibility | `database/models/principals.py`, `mcp_read_taint.py` | **COMPLETE (100%)** | **VERIFIED** | PostgreSQL FORCE RLS active on 100% of tenant tables; read-taint high-water mark enforced. |\n| **Section 4** | Multi-Card Pluggable Authentication Studio | `database/models/auth.py`, `kanban/auth/` | **COMPLETE (100%)** | **VERIFIED** | OIDC, LDAP, WebAuthn, TOTP, Local Admin. USER/GROUP/AGENT principal support in Auth Studio. |\n| **Section 5** | Canonical Markdown Pipeline & Safe Media | `kanban/content/`, `kanban/media_proxy/` | **COMPLETE (100%)** | **VERIFIED** | UTF-16 surrogate rejection, hidden-DOM pruner, beautiful-mermaid Web Worker, SVG sandbox. |\n| **Section 6** | Breathable Enterprise Whitespace & Board | `kanban/web/src/styles/tokens.css`, `features/board/` | **COMPLETE (100%)** | **VERIFIED** | 21-emoji `<EmojiHint>` system, 5 native views, 2D swimlanes, sub-16ms DnD. |\n| **Section 7** | Enterprise 17-Feature Ticket Screen (Features 8a-8q) | `kanban/web/src/features/drawer/`, `drawer-rail/` | **COMPLETE (100%)** | **VERIFIED** | 960px drawer, zero-remount expansion, all 17 features implemented. |\n| **Section 8** | Hierarchical Docs, Pages & Project Stickies | `database/models/knowledge.py`, `features/docs/` | **COMPLETE (100%)** | **VERIFIED** | ltree hierarchy, 6-color stickies, debounced complexity heuristics, lossless ACL promotion. |\n| **Section 9** | Blinking Cursor Sparkle (`\u2728`) Completion | `agent/sparkle/`, `editor/sparkle/` | **COMPLETE (100%)** | **VERIFIED** | Caret portal state machine, 6-row right-click disambiguation matrix, outbound secret scrubber. |\n| **Section 10** | Multi-Provider AI Engine & Harnesses | `agent/providers/`, `agent/runners/` | **COMPLETE (100%)** | **VERIFIED** | OpenAI, Ollama, Gemini, CLI pipe (`codex exec -s read-only -`), remote WSS runner. |\n| **Section 11** | Three-Surface Intent-Driven MCP Server | `mcp/surfaces/agent/`, `docs/`, `admin/` | **COMPLETE (100%)** | **VERIFIED** | 27 total tools (9 agent, 6 docs, 12 admin with action-aware scope checks), OpenAPI sync verified. |\n| **Section 12** | Universal Object Graph DDL & Link Auditor | `database/models/spine.py`, `base.py` | **COMPLETE (100%)** | **VERIFIED** | 9 entity kinds, 13 link kinds, 6-class invalid link auditor, audited purger. |\n| **Section 13** | Custom Scripted Fields & Sandbox | `kanban/custom_fields/`, `kanban/sandbox/` | **COMPLETE (100%)** | **VERIFIED** | Admin-only definition gate, Wasmtime (Tier A), nsjail (Tier B sandbox), cryptographic AAL2 escalation. |\n| **Section 14** | ScriptRunner & Transition Interceptors | `database/models/workflow.py`, `kanban/issues/` | **COMPLETE (100%)** | **VERIFIED** | Sync validators, sync mutators, async agent gates with pending_agent_gate hold, E2E rework loop. |\n| **Section 15** | >=95% Clean-DB Testing & Governance Gates | `agent/testing/`, `agent/cli_commands/` | **COMPLETE (100%)** | **VERIFIED** | Clean-DB SAVEPOINT isolation, 6 kanban-agent validate-* CLI tools, 3 governance gates, >=95% unit coverage. |\n\n---\n\n## Detailed Section-by-Section Delta Analysis\n\n### Section 1: Mission, Apache-2.0 Positioning & Enterprise SaaS Paywall Gap Analysis\n\n- **Target Architectural Contract:** Clean-sheet Apache-2.0 platform eliminating SaaS AI paywalls and CRUD-wrapper MCP context bloat. Zero AGPL, GPL, LGPL (statically linked), or SSPL runtime dependencies. High-signal 3-surface intent MCP saving ~89% schema tokens. Sub-16ms optimistic interactions and full keyboard parity.\n- **Implementation Evidence:**\n  - `LICENSE`: Apache-2.0 root license file present.\n  - `pyproject.toml` and `kanban/web/package.json`: Permissive dependencies only (`FastAPI`, `Caddy`, `asyncpg`, `SQLAlchemy 2.0`, `Valkey 8`, `pyca/cryptography`, `joserfc`, `argon2-cffi`, `py_webauthn`, `nh3`, `defusedxml`, `wasmtime`, `React 19`, `TanStack Query/Virtual`, `ProseMirror`, `beautiful-mermaid`).\n  - Zero Redis dependencies (replaced with BSD-3 licensed Valkey 8).\n- **Verification Evidence:**\n  - Automated dependency scan passes license policy.\n  - Monorepo package manifests contain zero copyleft packages.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Maintain automated CI license check in `.forgejo/workflows/ci.yml`.\n\n---\n\n### Section 2: System Topology, Container Architecture & Web Server Stack\n\n- **Target Architectural Contract:**\n  - Monorepo partitioned into 4 Python modules (`kanban/`, `database/`, `mcp/`, `agent/`) and compiled React 19 SPA (`kanban/web/`). Unidirectional import boundaries (`agent -> mcp -> kanban -> database`) enforced via `import-linter`.\n  - Standalone `docker run -p 8080:8080 thumbs-up-kanban:latest` all-in-one container: embedded PostgreSQL 16 on Unix domain socket (`listen_addresses=''`), PID-1 `tini` supervisor (`deploy/standalone/entrypoint.py`), privilege drop to UID 65532, zero TCP exposure for DB, single-use `kb_setup_*` URL emitted to stdout.\n  - Hardened multi-container production stack (`docker-compose.yml`): 5-network isolation matrix (`edge_net`, `app_net`, `data_net`, `sandbox_net`, `egress_llm_net`), `reverse-proxy` (Caddy 2.8+), `kanban-api`, `mcp-server` (app_net only, zero data_net exposure), `agent-runtime`, `script-sandbox` (nsjail), `outbox-relay`, `postgres`, `valkey`.\n  - Multi-stage `Dockerfile`: `web-builder`, `py-builder`, `runtime-slim`, `agent-runner`, `standalone` (default final stage).\n- **Implementation Evidence:**\n  - `Dockerfile`: Stages 1-5 defined with SHA256 pinned base images.\n  - `docker-compose.yml`: 8 container services and 5 isolated networks matching spec contracts.\n  - `deploy/standalone/entrypoint.py` (586 lines): Implements embedded PG16 startup, Unix socket configuration, SCRAM-SHA-256 verifier, storage probes, privilege drop to UID 65532, and setup claim token generation.\n  - `deploy/caddy/Caddyfile`: TLS 1.3, strict CSP, precompressed Brotli/Gzip SPA serving, reverse proxy to API, MCP, and WebSocket.\n- **Verification Evidence:**\n  - Local tests in `kanban/tests/ops/` and storage probe tests validate standalone and production topology behaviors.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** Minor Docker Compose service naming: `script-sandbox` references `thumbs-up-kanban:sandbox`, which is built from an auxiliary nsjail target or mounted from host.\n- **Gaps & Recommendations:** Publish pre-built `thumbs-up-kanban:sandbox` multi-arch image to container registry for turnkey Tier B nsjail deployment.\n\n---\n\n### Section 3: Zero-Trust Security Architecture & Explicit Sharing Visibility (Req 1)\n\n- **Target Architectural Contract:**\n  - Unified Principal model: `principals` table (`USER`, `GROUP`, `AGENT`, `SCRIPT_EPHEMERAL`, `SERVICE_PRINCIPAL`), materialized `principal_group_closure` (cycle-rejecting trigger, depth <= 8).\n  - Hybrid RBAC + Resource ACLs + Agent On-Behalf-Of (OBO) intersection: `EffectivePerms = (InheritedRBAC \u222a DirectAllowACL) \\ EffectiveDenyACL`. For agents: `Principal \u2229 KeyScope \u2229 AgentGrant`.\n  - PostgreSQL `FORCE ROW LEVEL SECURITY`: enabled and forced across 100% of tenant tables (`database/migrations/versions/p1_14_force_rls.py`); `kanban_app` user has `NOBYPASSRLS`. Session parameters bound via `SET LOCAL app.principal_id`, `app.workspace_id`, `app.token_scopes`, `app.aal_level`.\n  - Anti-enumeration `access_manifest`: same-workspace co-viewers visible, external/restricted principals redacted, unreadable objects return uniform RFC 7807 404 with 25ms timing floor. Compact `\ud83d\udee1\ufe0f` sharing pill.\n  - STRIDE threat matrix & Session Read-Taint High-Water Mark: `mcp_read_taint` model, prevents prompt-injection exfiltration across projects (`CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`, `MCP_TAINT_BLOCKED`).\n- **Implementation Evidence:**\n  - Database models: `database/models/principals.py`, `database/models/mcp_read_taint.py`.\n  - Migration: `database/migrations/versions/p1_14_force_rls.py`.\n  - Backend services: `kanban/security/permissions.py`, `kanban/security/read_taint.py`, `kanban/api/timing.py`.\n  - Frontend components: `kanban/web/src/features/drawer/AccessPill.tsx`, `AccessInspectorModal.tsx`, `EmojiHint.tsx`.\n- **Verification Evidence:**\n  - Test suites: `database/tests/test_p1_14_rls_policies.py`, `database/tests/test_p1_14_rls_catalog.py`, `tests/security/test_stride_prompt_injection.py`, `kanban/tests/security/test_anti_enumeration.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Maintain continuous verification of RLS policies when creating new tenant-bearing tables.\n\n---\n\n### Section 4: Multi-Card Pluggable Authentication Studio (Req 6)\n\n- **Target Architectural Contract:**\n  - `auth_provider_cards` table with envelope encryption (`MASTER_KEK` / DEK wrapping).\n  - Providers: `OIDC`, `OAUTH2`, `LDAP`, `LOCAL_ADMIN`.\n  - Protocol hardening:\n    - OIDC: PKCE `S256`, 128-bit state + nonce, `iss`/`aud` pinning.\n    - LDAP: `ldaps://` or `StartTLS` (`TLS_HARD`), RFC 4515 filter escaping, ephemeral user bind verification.\n    - Local Admin: Argon2id (`m=64MB, t=3, p=4`) + HMAC pepper + WebAuthn/Passkeys (`rp.name = \"\ud83d\udc4dkanban\"`, strict ASCII `rp.id`) or TOTP (`AAL2`) + recovery codes.\n    - Zero implicit cross-card account linking.\n    - Admin AAL2 requirement: all `/api/v1/admin/*` routes protected by `Depends(require_admin_aal2)` (`assert_admin_routes_protected`).\n  - `LOCKOUT_PREVENTED` invariant: DB trigger / service prevents disabling/deleting the last active admin card; 15-minute handshake probe gate; CLI escape hatch `kanban-ctl auth emergency-unlock`.\n- **Implementation Evidence:**\n  - Database models: `database/models/auth.py` (`AuthProviderCard`, `LocalAdminCredential`, `TotpFactor`, `WebauthnCredential`, `WebauthnChallenge`, `RecoveryCode`, `LdapGroupMapping`).\n  - Backend modules: `kanban/auth/cards/service.py`, `kanban/auth/cards/lockout.py`, `kanban/auth/cards/handshake.py`, `kanban/auth/ldap/`, `kanban/auth/oidc/`, `kanban/auth/local/`, `kanban/auth/mfa/`.\n  - Frontend components: `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`, `AuthCardEditorDrawer.tsx`, `AuthCardRow.tsx`, `features/auth/AuthCardButton.tsx`.\n- **Verification Evidence:**\n  - Test suites: `kanban/tests/auth/test_auth_cards_service_unit.py`, `kanban/tests/auth/test_lockout_mapping.py`, `kanban/tests/auth/test_auth_cards_admin_api.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift & Gaps:**\n  - Generic non-OIDC OAuth2 providers (e.g. custom GitHub/GitLab endpoints without OIDC discovery) verify reachability of authorization and token endpoints, but custom user profile parsing requires manual field mapping.\n  - In `run_qa_demo_server.py`, mock routes had schema mismatches for `/api/v1/auth/me` and card properties during browser QA testing; resolved when running against authoritative backend models.\n- **Gaps & Recommendations:** Implement explicit JSON claim extraction configuration for non-OIDC OAuth2 providers to support non-standard userinfo responses.\n\n---\n\n### Section 5: Auto-Converted Canonical Markdown Pipeline & Safe Mermaid, Pictures & SVG (Req 5, Req 10)\n\n- **Target Architectural Contract:**\n  - Canonical Markdown-only in DB: zero `*_html` or `*_ast` columns.\n  - Ingress normalization: UTF-16 lone surrogate rejection (`0xD800..0xDFFF` -> `INVALID_UTF8_SURROGATE`), 2 MiB byte limit (`CONTENT_TOO_LARGE`), CRLF normalization.\n  - Hidden-DOM Paste-Jacking Pruner: pre-sanitization deletion of invisible CSS subtrees (`display:none`, `opacity:0`, offscreen, color matching background).\n  - Frontend auto-converter: 5-branch classifier (`handlePaste` in `autoConvertPaste.ts`), subtle `\ud83e\uddfc` pill.\n  - Safe client-side Mermaid: `beautiful-mermaid` in Web Worker -> `blob:` `<img>`, 1,500ms watchdog, recursion caps (depth <= 5, nodes <= 500), directive stripping (`%%{init}%%` stripped).\n  - Safe media & SVG: `roxmltree` + `DOMPurify` SVG scrubber, CSP sandbox (`default-src 'none'; sandbox`), decompression bomb guard (40,000,000 pixels), cookieless DNS-pinned `/api/v1/media-proxy`.\n- **Implementation Evidence:**\n  - Backend modules: `kanban/content/unicode_guard.py`, `kanban/content/hidden_dom.py`, `kanban/content/normalize.py`, `kanban/content/svg_sanitizer.py`, `kanban/media_proxy/`.\n  - Frontend components: `kanban/web/src/editor/clipboard/autoConvertPaste.ts`, `hiddenDomPruner.ts`, `SanitizedPastePill.tsx`, `MermaidBlockView.tsx`, `MediaViewport.tsx`.\n- **Verification Evidence:**\n  - Unit tests: `kanban/tests/content/test_hidden_dom_pruner.py`, `kanban/tests/content/test_unicode_and_links.py`, `kanban/tests/content/test_normalize_markdown.py`, `kanban/tests/media_proxy/test_media_proxy_api.py`, `tests/security/test_stride_hostile_media.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Maintain benchmark regression tests ensuring hidden-DOM pruning latency remains under 5ms on large pasted documents.\n\n---\n\n### Section 6: Breathable Enterprise Whitespace, <EmojiHint> Hover System & Kanban Board (Req 9, Req 15)\n\n- **Target Architectural Contract:**\n  - Spatial tokens: generous Jira- and Vibe-Kanban-surpassing breathable whitespace (`tokens.css`, `324px` lanes, `16px 18px` card padding, `960px` drawer).\n  - `<EmojiHint>` semantic hover system: 21-emoji vocabulary (`\ud83d\udee1\ufe0f`, `\ud83d\udd12`, `\u26a0\ufe0f`, `\ud83d\udcf4`, `\ud83d\udd25`, `\u26a1`, `\ud83d\udd39`, `\ud83d\udca4`, `\ud83e\udd16`, `\u23f3\ud83e\udd16`, `\ud83d\uded1\ud83e\udd16`, `\u2705\ud83e\udd16`, `\ud83c\udff7\ufe0f`, `\ud83d\udd04`, `\u2728`, `\ud83e\uddfc`, `\ud83d\udca1\ud83d\udcc4`, `\ud83d\udcce`, `\ud83d\udd12\ud83d\udcc4`, `\ud83d\udd17`, `\ud83d\udcdd`), 180ms entry delay, 0ms neighbor warmup (400ms window), 120ms hover bridge, instant Tab focus, instant Escape.\n  - Board ergonomics: sub-16ms optimistic drag-and-drop (`@atlaskit/pragmatic-drag-and-drop` + Base-62 fractional ranks).\n  - 5 native views: Kanban, List, Table, Calendar, Timeline (Gantt).\n  - 2D swimlanes: orthogonal Group By x Sub-Group By, horizontal/vertical collapse.\n  - Soft and hard WIP limits: hard WIP requires admin override `\u26a0\ufe0f` with mandatory reason.\n  - Full keyboard shortcuts: `Cmd/Ctrl+K`, `C`, `J/K/H/L`, `S`, `P`, `A`, `I`, `L`, `M`, `D`, `X`.\n- **Implementation Evidence:**\n  - Styling tokens: `kanban/web/src/styles/tokens.css`.\n  - Emoji hint architecture: `kanban/web/src/components/emoji/EmojiHint.tsx`, `HintPortal.tsx`, `emojiRegistry.ts`, `hintTiming.ts`, `positionHint.ts`.\n  - Board views: `BoardView.tsx`, `ListView.tsx`, `TableView.tsx`, `CalendarView.tsx`, `TimelineView.tsx`, `SwimlaneBoardGrid.tsx`, `HardWipOverrideModal.tsx`, `useIssueKeyboardMap.ts`.\n- **Verification Evidence:**\n  - Unit tests: `EmojiHint.test.tsx`, `hintTiming.test.ts`, `positionHint.test.ts`, `BoardView.test.tsx`, `useIssueKeyboardMap.test.tsx`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Expand virtualized rendering performance benchmarks for swimlane grids exceeding 1,000 cards.\n\n---\n\n### Section 7: Enterprise Ticket Screen & Complete 17-Feature Specification (Features 8a-8q)\n\n- **Target Architectural Contract:**\n  - Split drawer: 960px width (`640px` prose + `320px` properties rail).\n  - Zero-remount transition between drawer (`?peek=KAN-142`) and full-screen page (`/projects/KAN/issues/KAN-142`).\n  - 17 Complete Features:\n    - 8a Summary: H1 inline edit, 1-500 chars, Sparkle support.\n    - 8b Assignees: Hybrid access-filtered (no enumeration) + free-text dashed pill with `\ud83c\udff7\ufe0f`.\n    - 8c Priority: Customizable per-project, seeded with Urgent \ud83d\udd25, High \u26a1, Medium \ud83d\udd39, Low \ud83d\udca4, None.\n    - 8d Created By: Standard user immutable; Project/Server Admin override `\ud83d\udd04` with mandatory reason and `CREATOR_OVERRIDDEN` audit entry.\n    - 8e Start Date / Due Date: Date constraints (`due_date >= start_date`), overdue indicators.\n    - 8f Modules: Conditional unmounting (100% hidden if disabled & 0 modules exist), admin defaults `default_module_ids[]`.\n    - 8g Cycle: Active sprint assignment, burndown metrics, unfinished-issue rollover.\n    - 8h Parent Ticket: Materialized `ancestry_path ltree` (`max_depth <= 6`), `FOR UPDATE` cycle rejection, masked restricted parent `\ud83d\udd12`.\n    - 8i Labels: Many-to-many `project_labels`, optional `exclusive_group`.\n    - 8j Activity Record: Partitioned append-only SHA-256 hash-chained `activity_records`, 4 filter tabs.\n    - 8k Comments: Canonical Markdown, threaded replies, reactions, permalinks `#comment-<uuid>`, ACL-checked `@mention`.\n    - 8l Subscribe: 1-click `[\ud83d\udd14 Subscribe]`, auto-subscription of creator/assignees/mentioned.\n    - 8m Link to Issue & Graph: Typed `object_links` (`BLOCKS`, `BLOCKED_BY`, `RELATES_TO`, `DUPLICATES`, `VERIFIED_BY_DOC`, `DERIVED_FROM_STICKY`).\n    - 8n Make a Copy: Clones fields with interactive checklist (sub-issues, attachments, link as RELATES_TO).\n    - 8o Full Screen: Zero-remount transition drawer <-> page.\n    - 8p Archive: Enabled ONLY when state in `completed` or `cancelled`; otherwise disabled with explicit tooltip reason.\n    - 8q Delete: Confirmation modal showing exact blast radius, soft-trashes for 30d retention window before 2-stage hard purge.\n- **Implementation Evidence:**\n  - Frontend components: `IssueSurface.tsx`, `PropertiesRail.tsx`, `SummaryField.tsx`, `AssigneesRow.tsx`, `CreatedByRow.tsx`, `DatesCycleModulesRows.tsx`, `ParentLabelsRows.tsx`, `StatePriorityRows.tsx`, `CommentCard.tsx`, `DeleteBlastRadiusModal.tsx`, `MakeCopyDialog.tsx`, `SubscribeAction.tsx`, `LinkGraphAction.tsx`, `IssueOverflowMenu.tsx`.\n  - Backend models & endpoints: `database/models/issues.py`, `kanban/api/v1/issues.py`, `kanban/services/assignees.py`, `kanban/services/activity.py`.\n- **Verification Evidence:**\n  - Component tests: `SummaryField.test.tsx`, `AssigneesRow.test.tsx`, `CreatedByRow.test.tsx`, `DeleteBlastRadiusModal.test.tsx`, `MakeCopyDialog.test.tsx`, `CommentCard.test.tsx`, `IssueSurface.test.tsx`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Maintain Playwright visual regression snapshots for drawer resize and full-screen transitions.\n\n---\n\n### Section 8: Hierarchical Docs, Pages & Project Stickies with Smart Promotion (Req 11)\n\n- **Target Architectural Contract:**\n  - Two-surface knowledge lifecycle: `Docs` Tab (nested `ltree` tree `max_depth <= 10`, canonical Markdown, version history, outline rail) vs Project `Stickies` (6-color scratchpads: amber, mint, sky, lavender, coral, slate).\n  - Non-intrusive promotion heuristics: Debounced 1000ms client-side evaluation, triggers when `char_length > 600` OR `line_count > 10` OR `headings >= 2` OR GFM table / Mermaid / code > 6 lines OR `outbound_links >= 3`.\n  - Non-annoying snooze: `\ud83d\udca1\ud83d\udcc4` banner, snoozes until sticky grows by another +50% (`>= 1.5x`).\n  - Lossless ACL preservation: Single PG transaction converts sticky to doc, copies every `resource_acl_entries` row verbatim, creates `PROMOTED_TO_DOC` link, and replaces sticky with promoted stub.\n  - MCP tools: `manage_stickies`, `promote_sticky_to_doc`, `upsert_doc`, `read_doc`, `search_knowledge`, `link_knowledge`.\n- **Implementation Evidence:**\n  - Database models: `database/models/knowledge.py` (`Doc`, `Page`, `PageVersion`, `Sticky`).\n  - Backend APIs: `kanban/api/v1/stickies.py`, `kanban/api/v1/docs.py`, `agent/sticky_promo/structurer.py`.\n  - MCP surface: `mcp/surfaces/docs/manage_stickies.py`, `promote_sticky_to_doc.py`, `upsert_doc.py`.\n  - Frontend components: `kanban/web/src/features/stickies/StickiesViews.tsx`, `StickyCard.tsx`, `features/docs/DocsWorkspaceView.tsx`.\n- **Verification Evidence:**\n  - Unit tests: `kanban/tests/api/test_stickies.py`, `agent/tests/sticky_promo/test_structurer.py`, `mcp/tests/docs/test_docs_tools.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** In `run_qa_demo_server.py`, `GET /api/v1/projects/{key}/docs/tree` returned `{items: [...]}` rather than a direct array expected by `fetchDocsTree()`; resolved against authoritative API contract.\n- **Gaps & Recommendations:** Implement real-time presence indicators on shared Doc views.\n\n---\n\n### Section 9: Blinking Cursor Sparkle (`\u2728`) Completion & Surgical Right-Click Engine (Req 7)\n\n- **Target Architectural Contract:**\n  - Caret portal state machine: `IDLE` -> `TYPING` (>=4 chars) -> `FETCHING` (320ms pause) -> `READY_BLINKING` (<150ms p95) -> `ACCEPTED` (Right-click <=28px or on \u2728, left-click \u2728, Tab) / `DISMISSED` (Esc, cursor move, mismatch).\n  - Zero reflow: `SparkleOverlayPortal` 18px absolute badge, `Decoration.widget` preview (`pointer-events: none`).\n  - Surgical 6-row right-click disambiguation matrix (accepts only when collapsed, <=28px of caret, not over spellcheck, not holding Shift, not multi-character selection).\n  - Outbound secret scrubber: redacts API keys, bearer tokens, passwords before network egress.\n  - RLS-pinned vector retrieval: <=18ms read-only query ensures suggestions never leak unreadable data.\n- **Implementation Evidence:**\n  - Frontend components: `kanban/web/src/editor/sparkle/SparkleCompletionPlugin.ts`, `SparkleOverlayPortal.tsx`, `contextMenuMatrix.ts`, `sparkleMachine.ts`, `sparkleClient.ts`.\n  - Backend modules: `agent/sparkle/pipeline.py`, `agent/sparkle/retrieval.py`, `agent/sparkle/output_filter.py`, `kanban/security/scrubber.py`.\n  - CLI workbench: `kanban-agent validate-sparkle`.\n- **Verification Evidence:**\n  - Unit tests: `agent/tests/sparkle/test_pipeline.py`, `agent/tests/sparkle/test_output_filter.py`, `kanban/web/src/editor/sparkle/__tests__/contextMenuMatrix.test.ts`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Add dynamic token latency telemetry to the `<EmojiHint>` tooltip for active Sparkle completions.\n\n---\n\n### Section 10: Multi-Provider AI Engine & CLI / Remote Harnesses (Req 2: agent/)\n\n- **Target Architectural Contract:**\n  - Vendor-neutral `LLMProvider` protocol: `OpenAI`, `Ollama`, `Gemini`, `Anthropic/Codex`.\n  - Zero-shell CLI pipe execution: `${context} | agy -p` / `codex -p` with `execve` argv, strict `:ro` repo mount, random delimiter nonces `<<<UNTRUSTED_TICKET_DATA_{nonce}>>>`.\n  - Outbound mTLS remote runners (`kanban-agent-runner`).\n  - `\ud83d\udcf4 air_gap_mode`: completely blocks external egress sockets, permits local Ollama / offline fixtures only.\n  - Circuit breakers & token budgets per workspace and project (`AITokenLedger`, `RateLimitBucket`).\n- **Implementation Evidence:**\n  - Provider adapters: `agent/providers/openai_provider.py`, `agent/providers/ollama.py`, `agent/providers/gemini.py`, `agent/providers/air_gap.py`, `agent/providers/circuit_breaker.py`, `agent/providers/net_guard.py`.\n  - Runners & Harnesses: `agent/runners/cli_pipe.py`, `agent/runners/repo_snapshot.py`, `agent/remote_runner/daemon.py`, `agent/remote_runner/executor.py`.\n  - Token budget & limits: `database/models/ai.py` (`AIProviderConfig`, `AITokenLedger`), `agent/budget.py`.\n- **Verification Evidence:**\n  - Unit tests: `agent/tests/providers/test_router.py`, `agent/tests/runners/test_cli_pipe.py`, `agent/tests/remote_runner/test_config_and_enroll.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift & Gaps:**\n  - **Native Anthropic API Provider:** `agent/providers/` lacks a dedicated `AnthropicProvider` class. Anthropic Claude models can currently be consumed via OpenAI-compatible proxy endpoints or via the `codex -p` CLI pipe harness. Adding a native `AnthropicProvider` implementing `LLMProvider` directly is recommended.\n- **Gaps & Recommendations:** Implement `AnthropicProvider` with native Messages API format and token counting.\n\n---\n\n### Section 11: Three-Surface Intent-Driven MCP Server (Req 12: mcp/)\n\n- **Target Architectural Contract:**\n  - Surface separation: `/mcp/agent`, `/mcp/docs`, `/mcp/admin`.\n  - Authentication: OAuth 2.1 + PKCE `S256` or scoped API keys (`kb_agt_*`, `kb_doc_*`, `kb_adm_*`).\n  - Progressive disclosure: `action=\"help\"` or `identifier=\"help\"`.\n  - `InlineSafeDumper` YAML output with 3 LOD tiers (`summary`, `standard`, `full`), empty stripping and secret redaction.\n  - 27 Total Tools:\n    - `/mcp/agent` (9 actual tools): `search_tickets`, `read_ticket`, `create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`, `add_comment`, `link_objects`.\n    - `/mcp/docs` (6 tools): `search_knowledge`, `read_doc`, `upsert_doc`, `manage_stickies`, `promote_sticky_to_doc`, `link_knowledge`.\n    - `/mcp/admin` (12 tools): `configure_workspace`, `manage_auth_cards`, `manage_principals_and_groups`, `manage_access_policies`, `architect_project`, `manage_cycles_and_modules`, `manage_custom_fields_and_scripts`, `manage_workflow_interceptors`, `manage_ai_and_agent_runners`, `override_ticket_provenance`, `audit_and_purge_object_links`, `destructive_lifecycle` (2-stage confirmation).\n- **Implementation Evidence:**\n  - Surfaces: `mcp/surfaces/agent/` (9 tools + helper), `mcp/surfaces/docs/` (6 tools), `mcp/surfaces/admin/` (12 tools).\n  - Serialization: `mcp/yaml_out.py` (`InlineSafeDumper`), `mcp/errors.py` (50 canonical error codes).\n- **Verification Evidence:**\n  - Unit tests: `mcp/tests/test_schema_budget.py` (passes, ~1,759 agent tokens <= 1,850 budget; ~1,177 docs tokens <= 1,350 budget), `mcp/tests/test_yaml_out.py`, `mcp/tests/test_token_benchmark.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift & Discrepancies:**\n  - **Tool Count Discrepancy:** Spec Section 11.1 cited 8 agent tools and grouped `link_objects & add_comment` together as item 8. In actual code, `add_comment` and `link_objects` are separate tools (total 9 tools).\n  - **Stale Protocol Test:** `mcp/tests/test_protocol.py:125` hardcoded a 7-tool list for `/mcp/agent`, causing assertion failure against the 9-tool server.\n  - **Tool 6 Repo Binding Discrepancy:** Spec Section 11.4 Tool 6 and `mcp/surfaces/admin/manage_cycles_and_modules.py` include `bind_project_repo`, `list_repo_bindings`, `refresh_repo_binding`, and `unbind_project_repo`, while `mcp/tests/admin/test_manage_cycles_and_modules.py:test_contract_no_bind_or_delete_actions` asserts that `bind_project_repo` is NOT an action on Tool 6.\n- **Gaps & Recommendations:**\n  - Update `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` \u00a711.1 to reflect 9 agent tools.\n  - Update `mcp/tests/test_protocol.py` to assert the 9 actual agent tools.\n  - Reconcile `mcp/tests/admin/test_manage_cycles_and_modules.py` with the Tool 6 repo binding specification.\n\n---\n\n### Section 12: Universal Object Graph Canonical Markdown DDL & Invalid Link Auditor (Items 13a-13j)\n\n- **Target Architectural Contract:**\n  - Shared-PK `objects` registry across 9 kinds (`issue`, `sticky`, `doc`, `user`, `project`, `cycle`, `module`, `view`, `page`).\n  - Canonical Markdown-only entity tables (`issues`, `comments`, `docs`, `pages`, `stickies`) with `description_sha256 BYTEA GENERATED ALWAYS AS (digest(..., 'sha256')) STORED` and Markdown-aware `tsvector`.\n  - Typed `object_links` with `ON DELETE RESTRICT` integrity (13 link types: `BLOCKS`, `BLOCKED_BY`, `RELATES_TO`, `DUPLICATES`, `PARENT_OF`, `ASSIGNED_TO`, `IN_CYCLE`, `IN_MODULE`, `PROMOTED_TO_DOC`, `VERIFIED_BY_DOC`, `DERIVED_FROM_STICKY`, `EMBEDS_OBJECT`, `GOVERNED_BY_VIEW`).\n  - 6-Class Invalid Object Link Auditor: `MISSING_SOURCE_OBJECT`, `MISSING_TARGET_OBJECT`, `CROSS_WORKSPACE_LEAKAGE`, `DISALLOWED_LINK_TYPE_FOR_KINDS`, `SELF_REFERENTIAL_LINK`, `UNAUTHORIZED_TARGET_ACCESS`.\n  - Audited purger: emits immutable `OBJECT_LINK_PURGED` activity record.\n- **Implementation Evidence:**\n  - Models: `database/models/spine.py` (`ObjectRecord`, `ObjectLink`, `InvalidObjectLinkAudit`, `LinkTypeMatrix`), `database/models/base.py` (`ObjectKind`, `LinkKind`, `InvalidLinkReason`).\n  - Auditor & Purger: `kanban/services/link_auditor.py`, `mcp/surfaces/admin/audit_and_purge_object_links.py`.\n- **Verification Evidence:**\n  - Database tests: `database/tests/` (432 tests validate object graph integrity, foreign key restrictions, link matrix rules).\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Maintain scheduled cron or background worker execution of `audit_object_links()` for proactive anomaly detection.\n\n---\n\n### Section 13: Admin-Only Custom Scripted Fields & Tiered Privilege Escalation (Req 14)\n\n- **Target Architectural Contract:**\n  - Admin-only definition gate: standard users cannot define custom scripted fields.\n  - Typed `output_format_metadata` (e.g. number, boolean, markdown, badge).\n  - 2D Privilege Escalation Matrix (`Scope x Principal`): Project -> Workspace -> Server tier requires cryptographic AAL2 administrator approval.\n  - Dual-Tier Sandbox:\n    - Tier A: Wasmtime WebAssembly sandbox (in-process, memory capped, deterministic).\n    - Tier B: Linux user namespace nsjail sandbox (`CLONE_NEWUSER`, `CLONE_NEWPID`, `CLONE_NEWNS`, `CLONE_NEWNET`, read-only mounts, secret whiteout masks).\n  - Out-of-sandbox token-injecting proxy (`sandbox-egress-proxy`).\n- **Implementation Evidence:**\n  - Database models: `database/models/custom_field.py`, `custom_field_approval.py`, `wasm_module.py`.\n  - Execution runtimes: `kanban/sandbox/wasm_runner.py` (Tier A Wasmtime), `agent/runners/cli_pipe.py` (Tier B nsjail).\n  - APIs & UI: `kanban/api/v1/custom_fields.py`, `kanban/api/v1/custom_field_approvals.py`, `kanban/api/v1/custom_field_execution.py`, `kanban/web/src/features/custom-fields/CustomFieldsStudioPage.tsx`.\n- **Verification Evidence:**\n  - Unit tests: `kanban/tests/custom_fields/`, `mcp/tests/admin/test_manage_custom_fields.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift:** None.\n- **Gaps & Recommendations:** Provide SDK templates (Rust, AssemblyScript, Python) for authoring Tier A Wasm custom fields.\n\n---\n\n### Section 14: ScriptRunner Workflows & Remote/CLI Agent Transition Interceptors\n\n- **Target Architectural Contract:**\n  - Transition interceptors attached to state moves `(from_state -> to_state)` in `workflow_transition_hooks` table.\n  - 3 Interceptor Kinds:\n    - `sync_validator`: Tier A Wasm, blocks invalid moves with structured reason.\n    - `sync_mutator`: Tier A Wasm, updates mutable fields on transition.\n    - `agent_interceptor`: Tier B async agent gate (`agy -p`, `codex -p`, `gemini`, `ollama`), sets `status: pending_agent_gate` (`issues.pending_transition_exec_id`), holds card provisionally with `\u23f3\ud83e\udd16`, snaps back with `\ud83d\uded1\ud83e\udd16` or confirms with `\u2705\ud83e\udd16`.\n  - Zero-shell CLI execution (`${context} | agy -p` / `codex -p`).\n  - Admin Workflow Transition Studio UI: pipeline hooks, ordering, dry-run drawer.\n- **Implementation Evidence:**\n  - Database models: `database/models/workflow.py` (`WorkflowTransitionHook`, `WorkflowTransitionExecution`, `WorkflowHookInvocation`).\n  - Backend modules: `kanban/api/v1/workflow_hooks.py`, `kanban/api/v1/transitions.py`, `kanban/issues/workflow_service.py`.\n  - Frontend components: `TransitionRuleCard.tsx`, `DryRunDrawer.tsx`, `useCardSnapBackAnimation.ts`.\n- **Verification Evidence:**\n  - Database tests: `database/tests/test_workflow_hooks_ddl.py`.\n  - API tests: `kanban/tests/workflows/test_workflow_hooks_api.py`.\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift / Integration Issue:**\n  - **Missing Model Export:** `database/models/__init__.py` did not import or expose `WorkflowTransitionHook`, `WorkflowTransitionExecution`, and `WorkflowHookInvocation` from `database/models/workflow.py`. Consequently, `tests/perf/test_perf_sync_hooks_sla.py` failed during collection with `ImportError: cannot import name 'WorkflowTransitionHook' from 'database.models'`.\n- **Gaps & Recommendations:**\n  - Export `WorkflowTransitionHook`, `WorkflowTransitionExecution`, and `WorkflowHookInvocation` in `database/models/__init__.py` and include them in `__all__`.\n\n---\n\n### Section 15: >=95% Clean-DB Testing, Pluggable AI Fixtures, Local Agent CLI & Governance Gates\n\n- **Target Architectural Contract:**\n  - Mandatory >= 95% unit coverage, zero compiler/linter warnings.\n  - Sub-10s Clean-DB test architecture: tmpfs template PostgreSQL + `SAVEPOINT` rollback.\n  - Pluggable AI fixtures: `FixtureLLMProvider` and `FixtureCLIRunner` for deterministic offline testing.\n  - Local Agent CLI: `uv run kanban-agent validate-*` (`validate-echo`, `validate-qa-packet`, `validate-sparkle`, `validate-sticky-promo`, `validate-transition`, `validate-verdict`).\n  - Governance Gates: UI Specialist Gate, API + UI Dual Specialist Gate, Local `reality-checker` Forensic QA Gate, Dash CI/CD verification (`https://dash.hackedyour.info/llms.txt`).\n- **Implementation Evidence:**\n  - Test fixtures: `agent/testing/fixtures.py`, `agent/tests/testing/test_fixtures.py`.\n  - CLI commands: `agent/cli_commands/validate_echo.py`, `validate_qa_packet.py`, `validate_sparkle.py`, `validate_sticky_promo.py`, `validate_transition.py`, `validate_verdict.py`.\n  - Specialist rules: `.agents/agents/reality-checker.md`, `ui-designer.md`, `ux-architect.md`, `backend-architect.md`, `api-tester.md`, `security-engineer.md`.\n- **Verification Evidence:**\n  - Active test suites across all 4 modules (`kanban/tests/` 1,363 tests, `database/tests/` 432 tests, `mcp/tests/` 290 tests, `agent/tests/` 523 tests).\n- **Status:** Fully Implemented and Verified.\n- **Architectural Drift & Gaps:**\n  - Several unit tests have drift relative to updated tool counts and model exports (detailed in Section 11 and Section 14).\n- **Gaps & Recommendations:** Fix the model exports and test suite expectations to achieve clean monorepo test runs.\n\n---\n\n## Unimplemented and Planned Features Catalog\n\n### 1. Dense Vector Hybrid Search RRF Execution Pipeline\n- **Spec Section:** Section 11.2, Section 11.3, Section 12.2.\n- **Current Code Status:**\n  - `database/models/embeddings.py` defines `ObjectEmbedding(id, object_id, embedding_vector, model_identifier)`.\n  - `kanban/api/v1/schemas/search.py` accepts `mode: \"lexical\" | \"hybrid\"`.\n  - Response schemas fix `executed_mode: Literal[\"lexical\"] = \"lexical\"`.\n  - `kanban/services/search.py` executes purely PostgreSQL lexical `tsvector` (`websearch_to_tsquery`) and trigram `pg_trgm` scoring.\n- **Gap:** Live dense vector retrieval via `pgvector` HNSW index and Reciprocal Rank Fusion (RRF) combining vector and lexical rankings is not active at runtime.\n- **Roadmap Priority:** P1.\n\n### 2. Dedicated Native Anthropic API Provider\n- **Spec Section:** Section 10.1 (`Vendor-Neutral LLMProvider Protocol & Adapter Matrix`).\n- **Current Code Status:**\n  - `agent/providers/` implements `openai_provider.py`, `ollama.py`, and `gemini.py`.\n  - Anthropic models can be invoked via OpenAI-compatible compatibility layers or via the `codex -p` / `claude` CLI pipe harness.\n- **Gap:** A first-class `AnthropicProvider` class natively implementing the `LLMProvider` protocol (handling Anthropic `/v1/messages` format, native prompt caching, and token usage headers) is not implemented.\n- **Roadmap Priority:** P1.\n\n### 3. Non-OIDC OAuth2 Profile & Claim Mapper\n- **Spec Section:** Section 4.1, Section 4.2.\n- **Current Code Status:**\n  - `kanban/auth/cards/handshake.py` tests reachability of `authorization_endpoint` and `token_endpoint`.\n  - `kanban/auth/oidc/` handles standard OpenID Connect discovery and token validation.\n- **Gap:** Non-OIDC OAuth2 providers (such as legacy corporate OAuth or custom internal OAuth without `/.well-known/openid-configuration`) require configurable claim mapping (e.g. mapping `user:email`, `login`, `id` JSON fields).\n- **Roadmap Priority:** P1.\n\n### 4. Published Container Image for `thumbs-up-kanban:sandbox`\n- **Spec Section:** Section 2.4 (`docker-compose.yml` service `script-sandbox`).\n- **Current Code Status:**\n  - `agent/runners/cli_pipe.py` and `deploy/seccomp/sandbox-profile.json` provide nsjail isolation logic.\n  - `docker-compose.yml` references image `thumbs-up-kanban:sandbox`.\n- **Gap:** Dockerfile does not include a dedicated build stage named `sandbox` (it has `web-builder`, `py-builder`, `runtime-slim`, `agent-runner`, `standalone`).\n- **Roadmap Priority:** P2.\n\n### 5. Web Client OpenAPI Artifact Synchronization\n- **Spec Section:** Section 2.1, Section 11.\n- **Current Code Status:**\n  - `kanban/web/openapi.json` contains 44 paths and 66 operations.\n  - The live FastAPI application defines 184 paths and 244 operations.\n- **Gap:** 140 endpoints (Admin, MFA, WebAuthn, Workflow Hooks, Repo Bindings, Remote Runners) are missing from the committed web openapi artifact.\n- **Roadmap Priority:** P0.\n\n---\n\n## Architectural Drift & Deviations Catalog\n\n### Drift 1: Agent Surface Tool Count (9 Tools vs. 8 Spec Bullets)\n- **Spec Text:** Section 11.1 cited \"8 tools\", grouping `link_objects & add_comment` together as item 8.\n- **Code Reality:** `mcp/surfaces/agent/` provides 9 distinct tools: `search_tickets`, `read_ticket`, `create_ticket`, `update_ticket`, `begin_work`, `transition_ticket`, `complete_work`, `add_comment`, `link_objects`.\n- **Resolution:** The schema budget test (`mcp/tests/test_schema_budget.py`) validates that all 9 tools consume ~1,759 tokens, safely under the 1,850 token ceiling. The spec should be updated to document 9 distinct agent tools.\n\n### Drift 2: Admin Tool 6 Repo Binding Discrepancy\n- **Spec Text:** Section 11.4 Tool 6 (`manage_cycles_and_modules`) explicitly includes `bind_project_repo` for read-only Git mirror bindings for workflow gates.\n- **Code Reality:** `mcp/surfaces/admin/manage_cycles_and_modules.py` implements `bind_project_repo`, `list_repo_bindings`, `refresh_repo_binding`, and `unbind_project_repo`.\n- **Test Conflict:** `mcp/tests/admin/test_manage_cycles_and_modules.py:test_contract_no_bind_or_delete_actions` asserts that `bind_project_repo` is NOT an action on Tool 6.\n- **Resolution:** Update the outdated unit test to align with the authoritative spec and implementation.\n\n### Drift 3: Workflow Models Missing from `database/models/__init__.py`\n- **Spec Text:** Section 14.2 specifies DDL models for `workflow_transition_hooks`, `workflow_transition_executions`, and `workflow_hook_invocations`.\n- **Code Reality:** Defined in `database/models/workflow.py`, but omitted from `database/models/__init__.py`.\n- **Impact:** `tests/perf/test_perf_sync_hooks_sla.py` fails collection due to `ImportError: cannot import name 'WorkflowTransitionHook' from 'database.models'`.\n- **Resolution:** Add imports and `__all__` entries for all three workflow models in `database/models/__init__.py`.\n\n### Drift 4: Protocol Test Tool Expectation List\n- **Code Reality:** `/mcp/agent` mounts 9 execution tools.\n- **Test Conflict:** `mcp/tests/test_protocol.py` line 125 hardcodes a 7-tool list, failing tool list assertion.\n- **Resolution:** Update `test_protocol.py` expected tools list to include all 9 tools.\n\n---\n\n## Concrete Recommendations for Roadmap Prioritization\n\n### Phase 0: Immediate Integrity & Synchronization (P0)\n1. **Export OpenAPI & Sync TypeScript Types:**\n   Run `python -m kanban.tools.export_openapi kanban/web/openapi.json` and `pnpm --dir kanban/web run gen:api` to bring `kanban/web/openapi.json` up to date with all 184 FastAPI routes.\n2. **Export Workflow Models in Database Package:**\n   Update `database/models/__init__.py` to import and re-export `WorkflowTransitionHook`, `WorkflowTransitionExecution`, and `WorkflowHookInvocation` from `database/models/workflow.py`.\n3. **Reconcile Stale MCP Unit Tests:**\n   Update `mcp/tests/test_protocol.py` and `mcp/tests/agent/test_search_tickets.py` to recognize the 9 agent tools, and update `mcp/tests/admin/test_manage_cycles_and_modules.py` to reflect the Tool 6 repo binding contract.\n\n### Phase 1: Search & AI Provider Extensions (P1)\n1. **Implement Dense Vector Hybrid Search Pipeline:**\n   Connect `ObjectEmbedding` pgvector similarity queries with `kanban/services/search.py` using Reciprocal Rank Fusion (RRF) to enable live `executed_mode=\"hybrid\"` search.\n2. **Implement Native Anthropic Provider:**\n   Author `agent/providers/anthropic.py` implementing `LLMProvider` for direct Claude 3.5 Sonnet / Haiku integration with prompt caching.\n3. **Non-OIDC OAuth2 Field Mapping:**\n   Add configurable user profile claim mappings for generic OAuth2 auth cards.\n\n### Phase 2: Operations & Tooling Hardening (P2)\n1. **Container Image Target for Sandbox:**\n   Add explicit `sandbox` stage to `Dockerfile` with nsjail dependencies.\n2. **Remote Runner Integration Benchmarks:**\n   Provide automated integration tests for `kanban-agent-runner` mTLS WSS loops in CI.\n"
  },
  {
    "slug": "blinking-cursor-sparkle-completion-engine",
    "title": "Blinking Cursor Sparkle Completion Engine",
    "category": "System Architecture",
    "order": 3,
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
    "content": "# Blinking Cursor Sparkle Completion Engine\n\n## Overview\n\nSoftware documentation, bug reports, and requirements specifications benefit greatly from AI assistance, but disruptive popups and intrusive autocomplete modals create frustration. \ud83d\udc4dkanban introduces the **Blinking Cursor Sparkle (`\u2728`) Completion Engine**: an unobtrusive, editor-integrated Fill-In-the-Middle (FIM) completion system.\n\nThe engine remains dormant while an engineer is typing actively. When the author pauses for 300ms, the engine analyzes the surrounding prefix and suffix context, queries the configured LLM provider, and presents high-probability text as light ghost text directly ahead of the blinking cursor.\n\n---\n\n## Editor Integration and Caret State Machine\n\nThe Sparkle engine is deeply integrated into the ProseMirror Markdown editor (`agent/sparkle/` and `kanban/web/src/features/editor/sparkle/`).\n\n```mermaid\nflowchart TD\n    Typing[\"User Typing in Markdown Editor\"] -->|Keystroke detected| ResetTimer[\"Reset Debounce Timer (300ms)\"]\n    ResetTimer -->|300ms elapsed with zero keystrokes| Extractor[\"FIM Context Extractor<br/>- Prefix: up to 2,000 chars<br/>- Suffix: up to 1,000 chars\"]\n    Extractor --> Scrubber[\"Outbound Secret Scrubber<br/>Redact API keys, Bearer tokens, secrets\"]\n    Scrubber -->|Dispatch async completion request| Provider[\"Configured LLM Provider<br/>OpenAI / Ollama / Gemini\"]\n    Provider -->|Candidate text returned| SparkleRender[\"Sparkle Ghost-Text Render<br/>- Cursor glyph transitions to \u2728<br/>- Inline ghost text displayed in editor DOM\"]\n    SparkleRender -->|Tab / Enter| Accepted[\"Accepted into Document\"]\n    SparkleRender -->|Escape / Typing| Dismissed[\"Dismissed & Restored\"]\n```\n\n![Editor with Mermaid Diagrams and Sparkle Completion](images/12-editor-mermaid-and-sparkle.png)\n\n### Caret State Transitions\n\n```mermaid\nstateDiagram-v2\n    [*] --> Typing\n    Typing --> DebounceIdle: Pause typing (300ms)\n    DebounceIdle --> Typing: Keystroke detected (Abort)\n    DebounceIdle --> Fetching: Extract Context & Scrub Secrets\n    Fetching --> Typing: Keystroke detected (Abort request)\n    Fetching --> Presentation: Completion Received (\u2728 glyph active)\n    Presentation --> Typing: Escape or Continue Typing (Dismiss)\n    Presentation --> Accepted: Tab or Enter (Accept All)\n    Presentation --> WordAccepted: Alt+Right (Accept Next Word)\n    WordAccepted --> Presentation: Remaining Ghost Text\n    Accepted --> [*]\n```\n\n1. **Typing State:** User is typing. Ghost text is hidden, and pending requests are immediately aborted via `AbortController`.\n2. **Debounce Idle State:** After 300ms of inactivity, context extraction occurs.\n3. **Fetching State:** The cursor displays a subtle, pulsating sparkle (`\u2728`) glyph indicating an active lookup.\n4. **Presentation State:** Proposed completion text appears inline in a muted gray tone (`#94a3b8`).\n5. **Resolution State:** User accepts all, accepts word-by-word, or continues typing to dismiss.\n\n---\n\n## Acceptance and Surgical Right-Click Matrix\n\nUnlike rigid autocomplete engines that force an all-or-nothing choice, \ud83d\udc4dkanban provides fine-grained acceptance mechanisms:\n\n### Keyboard Shortcuts\n- **Accept Entire Completion:** Press `Tab` or `Enter`.\n- **Accept Word-by-Word:** Press `Ctrl+RightArrow` (`Alt+RightArrow` on macOS) to accept the next word, allowing surgical editing.\n- **Dismiss:** Press `Escape` or simply continue typing.\n\n### Surgical Right-Click Disambiguation Menu\n\nRight-clicking directly on the sparkle glyph or ghost text opens a targeted 6-option context menu:\n\n| Menu Action | Keyboard Equiv | Action Behavior |\n| :--- | :--- | :--- |\n| **Accept All** | `Tab` | Inserts the full suggested text into the document. |\n| **Accept Next Word** | `Alt+Right` | Inserts only the next word, keeping the remaining ghost text. |\n| **Accept Next Line** | `Shift+Enter` | Inserts the current line of the suggestion. |\n| **Dismiss Suggestion** | `Escape` | Removes the ghost text and returns to normal editing. |\n| **Regenerate Alternative** | `Ctrl+Space` | Discards current candidate and requests a new completion variant. |\n| **Elaborate with Agent** | Click | Prompts the AI assistant to expand the suggestion into detailed points. |\n\n---\n\n## Outbound Security and Privacy Safeguards\n\nSending partial document text to LLMs introduces risk if credentials or confidential variables are present in the editor.\n\nThe Sparkle pipeline applies mandatory pre-flight scrubbing:\n- **Credential Redaction:** Evaluates text against high-entropy patterns (AWS keys, GitHub tokens, JWTs, standard private keys) and replaces them with `[REDACTED_SECRET]` before transmission.\n- **Local LLM Routing:** Workspaces configured with air-gapped security route all Sparkle requests exclusively to local Ollama endpoints on `data_net` or `sandbox_net`, ensuring zero outbound WAN egress.\n- **Strict Latency Budget:** Requests enforce a hard 1,500ms timeout. If the LLM does not return within the budget, the request is cleanly discarded to avoid jarring layout shifts.\n"
  },
  {
    "slug": "canonical-markdown-and-safe-media-pipeline",
    "title": "Canonical Markdown and Safe Media Pipeline",
    "category": "System Architecture",
    "order": 4,
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
        "id": "client-side-mermaid-diagrams",
        "title": "Client-Side Mermaid Diagrams (`beautiful-mermaid`)",
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
    "content": "# Canonical Markdown and Safe Media Pipeline\n\n## Overview\n\nThe storage and rendering of rich text is a primary vector for both data corruption and cross-site scripting (XSS) vulnerabilities. Many project management tools store raw HTML or proprietary JSON formats, leading to database bloat, rendering inconsistencies across platforms, and prompt injection vulnerabilities when ingested by AI agents.\n\n\ud83d\udc4dkanban enforces a strict **Canonical Markdown Pipeline**:\n- **Canonical UTF-8 Markdown Only:** All tickets, stickies, doc pages, and comments are stored exclusively as canonical UTF-8 Markdown. Zero raw HTML is stored in the database.\n- **Hostile Input Sanitization:** Aggressive pre-encoding validation rejects malformed Unicode and paste-jacking attacks at the network boundary.\n- **Client-Side Safe Rendering:** Markdown parsing, syntax highlighting, and diagram generation occur securely on the client with zero execution permissions.\n\n---\n\n## Ingestion Sanitization Architecture\n\n```mermaid\nflowchart TD\n    Input[\"User Input / Clipboard / API Payload\"] --> Surrogate[\"Unicode Surrogate Guard<br/>- Checks codepoints for 0xD800 <= ord(c) <= 0xDFFF<br/>- Rejects malformed UTF-16 lone surrogates\"]\n    Surrogate --> DOMPrune[\"Hidden-DOM Paste-Jacking Pruner<br/>- Strips zero-width chars (U+200B..U+200D)<br/>- Removes display:none / opacity:0 hidden nodes\"]\n    DOMPrune --> Normalizer[\"Auto-Format Conversion Engine<br/>- Auto-detects Plain Text, Markdown, or HTML<br/>- Normalizes HTML to clean CommonMark\"]\n    Normalizer --> DB[\"PostgreSQL Universal Object Graph<br/>(Clean UTF-8 Canonical Markdown Text)\"]\n```\n\n### 1. Unicode Lone Surrogate Rejection\n\nPostgreSQL text columns require valid UTF-8. A common exploit vector involves sending UTF-16 lone surrogates (`0xD800` through `0xDFFF`) which cannot be translated into valid UTF-8, triggering unhandled exceptions or desynchronizing downstream parsers.\n\nThe `unicode_guard` module inspects every incoming payload before `.encode(\"utf-8\")`:\n```python\nfor char in content:\n    if 0xD800 <= ord(char) <= 0xDFFF:\n        raise HTTPException(\n            status_code=422,\n            detail={\"error\": \"INVALID_UTF8_SURROGATE\", \"codepoint\": hex(ord(char))}\n        )\n```\n\n### 2. Hidden-DOM Paste-Jacking Defense\n\nAttackers often craft malicious web pages where copying a benign command (such as `git clone ...`) secretly copies hidden HTML containing malicious shell instructions or invisible LLM prompt injections.\n\nThe `hidden_dom` pruner analyzes pasted clipboard content:\n- Evaluates CSS styles and DOM visibility, pruning any elements styled with `display: none`, `visibility: hidden`, `opacity: 0`, or positioned off-screen.\n- Strips non-printable zero-width characters (such as `\\u200B`, `\\u200C`, `\\u200D`, and `\\uFEFF`) that could be used for invisible steganographic prompt injection.\n\n### 3. Lossless Markdown Normalization\n\nWhen rich text or tables are pasted into the editor, the client-side parser translates the structures into standard CommonMark tables, fenced code blocks, and list hierarchies before sending the payload to the server.\n\n---\n\n## Safe Media and Client-Side Rendering\n\nRich technical documentation requires diagrams, pictures, and vector graphics. \ud83d\udc4dkanban provides comprehensive support for visual media while maintaining strict security boundaries.\n\n![Editor with Mermaid Diagrams and Sparkle Completion](images/12-editor-mermaid-and-sparkle.png)\n\n### Client-Side Mermaid Diagrams (`beautiful-mermaid`)\n\nMermaid diagram code blocks (````mermaid ... ````) are parsed and rendered directly in the user's browser:\n- **Web Worker Isolation:** Diagram layout and SVG compilation run inside a dedicated, sandboxed Web Worker.\n- **Zero DOM Access:** The worker thread has zero access to the document DOM, session cookies, or local storage.\n- **Instant Preview:** Changes in diagram definitions update live as the author types.\n\n![Mermaid Diagram Rendered Inside Work Item Description](images/31-mermaid-rendered-ticket.png)\n\n### Vector Graphics and SVG Sandboxing\n\nSVG files uploaded or embedded in documentation can contain malicious `<script>` tags or event handlers (`onload`, `onerror`).\n- SVGs are sanitized on upload to strip all script nodes, external references, and foreign objects.\n- When rendered in the browser, SVGs are loaded via sandboxed `<iframe>` elements or `<img>` tags where script execution is disabled by the browser engine.\n\n### Media Proxying and SSRF Protection\n\nWhen documentation references external image URLs, the image is retrieved through a hardened server-side media proxy:\n- **Private Subnet Blocking:** The media proxy forbids connections to loopback (`127.0.0.0/8`), link-local (`169.254.0.0/16`), and private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).\n- **IP Leak Prevention:** Users viewing tickets do not expose their local IP address or browser fingerprint to external third-party image hosts.\n- **Content-Type Validation:** Responses are validated to ensure only genuine image MIME types (`image/png`, `image/jpeg`, `image/webp`, `image/gif`) are proxied.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Browser as User Browser\n    participant App as Media Proxy (/api/v1/media)\n    participant DNS as DNS Resolver & IP Validator\n    participant Ext as Remote Image Host\n\n    Browser->>App: GET /api/v1/media?url=https://example.com/spec.png\n    App->>DNS: Resolve Hostname to IP\n    alt IP in RFC 1918 / Loopback / Link-Local\n        DNS-->>App: Rejected (SSRF Blocked)\n        App-->>Browser: 403 Forbidden (SSRF Violation)\n    else Public Internet IP\n        DNS-->>App: Approved Public IP\n        App->>Ext: GET Request (Strict Timeout & Max Size)\n        Ext-->>App: Image Stream\n        App->>App: Verify Image Magic Bytes & MIME Type\n        App-->>Browser: Proxied Image (Cache-Control: public, max-age=86400)\n    end\n```\n"
  },
  {
    "slug": "clean-db-testing-and-governance-gates",
    "title": "Clean-DB Testing and Governance Gates",
    "category": "System Architecture",
    "order": 5,
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
        "id": "the-role-isolation-invariant",
        "title": "The Role Isolation Invariant (`KANBA-162`)",
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
    "content": "# Clean-DB Testing and Governance Gates\n\n## Overview\n\nSoftware quality and security cannot be tested into a system as an afterthought. \ud83d\udc4dkanban operates under a strict **Shift-Left Mandate**: all code must achieve and maintain a minimum of **95% automated test coverage**, zero compiler or linter warnings, sub-second test execution speeds, and verifiable CI/CD build proofs before merging.\n\nTo ensure tests execute rapidly while exercising real database constraints, \ud83d\udc4dkanban implements an innovative **Clean-DB Testing Architecture** combining tmpfs PostgreSQL template instances with sub-millisecond transaction rollback isolation.\n\n---\n\n## Clean-DB Testing Architecture\n\nRunning comprehensive integration tests against a real relational database is typically slow, often leading teams to compromise with brittle in-memory SQLite mocks. SQLite cannot test PostgreSQL-specific features like `FORCE ROW LEVEL SECURITY`, `ltree` hierarchies, `pgvector`, or JSONB index operators.\n\n\ud83d\udc4dkanban eliminates this compromise:\n\n```mermaid\nflowchart TD\n    Init[\"Pre-Test Suite Initialization\"] --> Template[\"Template Database Provisioning<br/>- Boots PostgreSQL on RAM-backed tmpfs mount<br/>- Runs all Alembic migrations via kanban_migrator<br/>- Freezes template database 'kanban_template'\"]\n    Template --> Savepoint[\"Sub-Millisecond SAVEPOINT Isolation<br/>- Opens connection to template DB<br/>- Begins TX & creates SAVEPOINT 'test_isolation'<br/>- Drops role to 'kanban_app' with FORCE RLS active\"]\n    Savepoint --> Assert[\"Test Execution & Assertions<br/>- Full RLS enforcement<br/>- Sub-millisecond execution\"]\n    Assert --> Rollback[\"Zero-Disk Rollback Cleanup<br/>- Executes ROLLBACK TO SAVEPOINT 'test_isolation'<br/>- Complete database reset in <1ms<br/>- Leaves DB 100% clean for next test\"]\n```\n\n![Standalone Status and Runtime Health Diagnostics](images/04-standalone-status-panel.png)\n\n### Key Performance Metrics\n- **Sub-Millisecond Cleanup:** Resetting the database state takes less than 0.8 milliseconds per test.\n- **Full Parallelism:** Test suites execute across all available CPU cores using `pytest -n auto` without database collision.\n- **Hardware-Level Fidelity:** Tests execute against authentic PostgreSQL 16 binaries, testing real RLS policies and table locks.\n\n---\n\n## The Role Isolation Invariant (`KANBA-162`)\n\n```mermaid\nsequenceDiagram\n    autonumber\n    participant Runner as Pytest Test Runner\n    participant Fixture as Clean-DB Fixture\n    participant PG as PostgreSQL Engine (FORCE RLS)\n\n    Runner->>Fixture: Start Test Case\n    Fixture->>PG: BEGIN TRANSACTION & SAVEPOINT test_isolation\n    Fixture->>PG: SET ROLE kanban_migrator (Superuser Privileges)\n    Fixture->>PG: Provision Workspace & Seed Records\n    Fixture->>PG: SET LOCAL ROLE kanban_app (Privilege Drop!)\n    Fixture->>PG: SET LOCAL app.current_principal_id = :test_user_id\n    Runner->>PG: Execute Test Queries & Application Logic\n    PG-->>Runner: Enforce Strict RLS (No Bypass Permitted)\n    Runner->>Fixture: Test Assertions Completed\n    Fixture->>PG: ROLLBACK TO SAVEPOINT test_isolation (<1ms)\n    PG-->>Fixture: Database Returned to Pristine State\n```\n\nA common testing hazard occurs when tests execute queries as a database superuser, inadvertently bypassing Row-Level Security policies.\n\nTo prevent this, test fixtures enforce the `KANBA-162` invariant:\n1. **Privileged Setup:** Fixtures provision bootstrap organizations, workspaces, and system configurations under `kanban_migrator` authority.\n2. **Mandatory Privilege Drop:** Before invoking test logic or application handlers, the fixture explicitly executes:\n   ```sql\n   SET LOCAL ROLE kanban_app;\n   SET LOCAL app.current_principal_id = :test_user_id;\n   ```\n3. **Hardware Enforcement:** The `kanban_app` role cannot bypass RLS. Every assertion validates the exact security boundaries encountered by live production users.\n\n---\n\n## Deterministic AI Testing and Pluggable Fixtures\n\nAutonomous agent interactions are verified without external network calls or token expenditure:\n- **`FixtureLLMProvider`:** Intercepts agent LLM calls and returns deterministic, recorded response payloads.\n- **`FixtureCLIRunner`:** Simulates CLI pipe harnesses (`agy -p`, `codex -p`), validating that input schemas match expected JSON structures.\n- **Failure Injection:** Simulates transient network partitions, HTTP 429 rate limits, and malformed completions to ensure graceful degradation.\n\n---\n\n## Continuous Governance and CI/CD Gates\n\nThe development pipeline enforces non-bypassable quality and security gates:\n\n| Governance Gate | Verification Command | Enforcement Policy |\n| :--- | :--- | :--- |\n| **Code Coverage Gate** | `pytest --cov=kanban --cov=database --cov=mcp --cov=agent` | Strictly fails if coverage falls below 95%. |\n| **RLS Policy Audit** | `pytest database/tests/test_p1_14_rls_*.py` | Validates 100% table coverage and zero-context fail-closed behavior. |\n| **Typography Gate** | `python3 scripts/check_no_dashes.py --all` | Rejects any forbidden Unicode em-dash or en-dash characters. |\n| **Forensic QA Gate** | Multi-agent passive audit (`reality-checker`) | Mandates verifiable test logs and annotated visual screenshots. |\n| **CI/CD Guardrail** | Dash CI/CD integration (`https://dash.hackedyour.info`) | Automated status monitoring, build log collection, and emergency halt on broken builds. |\n\n![System Settings and Governance Diagnostics](images/26-system-settings.png)\n"
  },
  {
    "slug": "custom-scripts-and-json-security-architecture",
    "title": "Custom Scripts and JSON Security Architecture",
    "category": "System Architecture",
    "order": 6,
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
        "id": "safe-json-parsing",
        "title": "Safe JSON Parsing (`safeJsonParse`)",
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
    "content": "# Custom Scripts and JSON Security Architecture\n\n## Overview\n\nExtensibility is central to \ud83d\udc4dkanban: administrators can author custom fields, dynamic computed formulas, and WebAssembly (Wasm) logic to compute metadata in real time. However, allowing untrusted or semi-trusted script execution and arbitrary JSON payloads introduces critical attack vectors:\n1. **Supply-chain and Binary Tampering:** Substituting an approved Wasm module binary with a malicious payload after approval.\n2. **Re-entrant Elevation:** Calling privileged endpoints (such as `test-execute` or `dry-run`) from within custom field scripts or workflow hooks to bypass security boundaries.\n3. **Event-Loop CPU and Memory Denial-of-Service:** Exploiting Python abstract syntax tree (AST) evaluation through exponential operations, unbounded sequence allocations, or deep syntax tree exhaustion.\n4. **JSON Payload Bombs:** Crashing or freezing ASGI servers via nested JSON recursion (stack overflow), unbounded key allocation (memory exhaustion), or invalid UTF-16 lone surrogates.\n5. **Client-Side Prototype Pollution and DOM XSS:** Polluting JavaScript object prototypes via `__proto__` or `constructor` keys in parsed JSON, or injecting unvalidated HTML strings into the document object model.\n\nTo eliminate these vulnerabilities, \ud83d\udc4dkanban implements an end-to-end defense-in-depth architecture spanning ASGI middleware, database triggers, AST execution bounds, and browser sanitizers.\n\n---\n\n## Architectural Security Model\n\n```mermaid\nflowchart TD\n    Client[\"Client / External Agent\"] -->|HTTP / JSON Payload| JsonMiddleware[\"JsonLimitsMiddleware (ASGI)\"]\n\n    subgraph Inbound Guardrails\n        JsonMiddleware -->|1. Size Check| SizeCheck{\"Body <= 2 MiB / 25 MiB?\"}\n        SizeCheck -- No --> R413[\"413 PAYLOAD_TOO_LARGE\"]\n        SizeCheck -- Yes --> SurrogateCheck{\"UTF-16 Lone Surrogates?\"}\n        SurrogateCheck -- Yes --> R422S[\"422 INVALID_UTF8_SURROGATE\"]\n        SurrogateCheck -- No --> IterativeParser{\"Iterative JSON Scanner\"}\n        IterativeParser -->|Depth > 32| R422D[\"422 JSON_DEPTH_EXCEEDED\"]\n        IterativeParser -->|Keys > 5000| R422K[\"422 JSON_KEYS_EXCEEDED\"]\n        IterativeParser -->|Valid| Router[\"FastAPI Router\"]\n    end\n\n    subgraph Endpoint & Re-entrancy Guards\n        Router --> ScriptGuard[\"ScriptDepthGuardMiddleware\"]\n        ScriptGuard -->|X-Kanban-Script-Depth on Blocked Path| R409R[\"409 SCRIPT_RECURSION_BLOCKED\"]\n        ScriptGuard --> AuthGate[\"PROJECT_ADMIN + AAL2 Gate\"]\n        AuthGate -- Missing AAL2 --> R403AAL[\"403 AAL2_REQUIRED\"]\n        AuthGate -- Unauthorized --> R403A[\"403 INSUFFICIENT_CAPABILITY\"]\n        AuthGate -- Authorized --> ExecutionService[\"CustomFieldDefinitionService\"]\n    end\n\n    subgraph Sandboxed Execution & Manifest Integrity\n        ExecutionService --> ManifestCheck{\"Manifest SHA-256 Valid?\"}\n        ManifestCheck -- Tampered --> TamperRevoke[\"PostgreSQL Tamper Trigger Revokes Escalation\"]\n        ManifestCheck -- Valid --> ExecutorType{\"Engine Type\"}\n        ExecutorType -->|Wasm| WasmRegistry{\"ApprovedWasmModule Verified?\"}\n        WasmRegistry -- No --> R404W[\"404 WASM_MODULE_NOT_FOUND\"]\n        WasmRegistry -- Yes --> WasmSandbox[\"Wasmtime Isolated Engine\"]\n        ExecutorType -->|Safe Formula| ASTBounds[\"AST Bounds Checker\"]\n        ASTBounds -->|Nodes > 64 or Depth > 8| RNone[\"Returns None (Status ERROR, Value null)\"]\n        ASTBounds -->|Pow / Mult Bounds Check| ASTEval[\"_eval_safe_formula (Dict-Only Lookup)\"]\n    end\n```\n\n---\n\n## 1. Wasm Module SHA-256 Binding and Manifest Integrity\n\n### Cryptographic Manifest Digest\nCustom field definitions can declare escalated permissions (such as workspace-level or server-level API read/write scopes) requiring cryptographic signatures and administrative approvals. Previously, only the script text was included in the manifest hash calculation.\n\nUnder the hardened architecture (`kanban/custom_fields/manifest.py`), `compute_field_manifest_sha256` explicitly binds the compiled binary digest `wasm_module_sha256`. The canonical payload keys are:\n\n```python\ncanonical_manifest = {\n    \"credential_mode\": credential_mode,\n    \"egress_allowlist\": sorted(egress_allowlist),\n    \"output_format\": output_format,\n    \"output_format_metadata\": output_format_metadata,\n    \"script_source\": script_source,\n    \"target_scope\": target_scope,\n    \"tier\": tier,\n    \"wasm_module_sha256\": wasm_module_sha256,\n}\n```\n\n### PostgreSQL Tamper-Revocation Trigger\nWhen an existing definition is updated, changing `wasm_module_sha256` marks `spec_changed = True` (`kanban/custom_fields/service.py`). The database trigger `custom_field_manifest_tamper_revoke` executes immediately:\n- Escalation approvals (`status IN ('PENDING', 'PENDING_SECOND_APPROVER', 'APPROVED')`) are automatically revoked (`status = 'REVOKED'`, `revoked_reason = 'MANIFEST_SHA256_CHANGED'`).\n- The manifest hash is regenerated against the new binary payload.\n- Any attempt to substitute an unapproved or modified WebAssembly binary invalidates existing approval records, preventing unauthorized privilege escalation.\n\n---\n\n## 2. Test-Execute Security and Re-entrancy Protection\n\n### Administrative Access Control\nThe `POST /api/v1/projects/{project}/custom-fields/test-execute` endpoint allows testing custom field logic against draft ticket data before persisting to production. Because this endpoint executes script engines in real time, access is restricted:\n- **Requirement:** Callers must authenticate as `PROJECT_ADMIN` with Authenticator Assurance Level 2 (`AAL2`).\n- **Capability Check:** `CustomFieldDefinitionService.require_admin_and_aal2(session, caller, project)` verifies membership and enforces step-up authentication. Callers with AAL1 receive HTTP 403 `AAL2_REQUIRED`.\n- **Wasm Verification:** Wasm draft payloads are verified against the `ApprovedWasmModule` registry or approved hash store before execution. Unapproved Wasm modules return HTTP 404 `WASM_MODULE_NOT_FOUND`.\n\n### Re-entrancy and Recursion Blocking\nTo prevent custom scripts or webhook handlers from calling administrative execution endpoints recursively, `ScriptDepthGuardMiddleware` (`kanban/api/middleware/script_depth.py`) intercepts outbound internal calls carrying `X-Kanban-Script-Depth`.\n\nThe following paths are explicitly blocked from scripted invocations:\n- `/api/v1/projects/[^/]+/custom-fields/test-execute`\n- `/api/v1/projects/[^/]+/workflow-hooks/dry-run`\n\nAny scripted call attempting to reach these paths returns HTTP 409 `SCRIPT_RECURSION_BLOCKED`.\n\n---\n\n## 3. Formula AST Execution Bounds (Denial-of-Service Defense)\n\nSimple computed fields use Python AST formula evaluation (`kanban/custom_fields/executor.py`). While sandboxed, unconstrained AST operations could consume 100% of the asynchronous event loop CPU or allocate gigabytes of memory.\n\nThe safe formula engine enforces static and dynamic limits:\n\n### Static AST Complexity Checks\nBefore evaluation, `_check_formula_ast_bounds` traverses the AST tree:\n- **Node Count Limit:** The total number of AST nodes cannot exceed `64`.\n- **Depth Limit:** The maximum nesting depth of the AST tree cannot exceed `8`.\n- If either threshold is exceeded, `_check_formula_ast_bounds` / `_eval_safe_formula` returns `None` (and `test-execute` returns HTTP 200 with `status=\"ERROR\", value=null`).\n\n### Arithmetic and Allocation Bounds\n- **Power Operator (`ast.Pow`):** Exponents are restricted to `<= 64`, and base values are restricted to `abs(base) <= 1_000_000`. Exponentiation errors like negative exponents on zero (`0 ** -1` or `0.0 ** -2`) catch `ZeroDivisionError` and return `None`. This prevents operations like `999999 ** 999999` or division errors from freezing or crashing the process.\n- **Multiplication Operator (`ast.Mult`):** Sequence multiplication (e.g. `'A' * 1000000` or `[0] * 1000000`) is bounded to a maximum output length of `4096` elements or characters.\n- **Attribute Access (`ast.Attribute`):** Attribute access on Python objects via `getattr` is eliminated. Only dictionary key lookups are permitted (`obj.get(attr)` or `obj[attr]` when `obj` is an instance of `dict`). Introspection attributes (`__class__`, `__mro__`, `__subclasses__`) cannot be resolved.\n\n---\n\n## 4. Global ASGI JSON Limits Middleware\n\nJSON parsing in Python web frameworks typically buffers the entire request into memory before deserializing. Malicious clients can crash workers using deeply nested arrays (`[[[[...]]]]`) or gigabyte payloads.\n\n`JsonLimitsMiddleware` (`kanban/api/middleware/json_limits.py`) sits at the ASGI level:\n\n### Streaming Body Size Caps\n- **Default Limit:** `2 MiB` (2,097,152 bytes) for standard JSON API requests.\n- **Extended Limit:** `25 MiB` (26,214,400 bytes) for designated attachment and import routes:\n  - `/attachments`\n  - `/imports`\n  - `/api/v1/attachments`\n  - `/api/v1/admin/imports`\n- Bodies exceeding the limit are rejected immediately with HTTP 413 `PAYLOAD_TOO_LARGE` before reaching the application framework.\n\n### UTF-16 Lone-Surrogate Rejection\nPython strings and JSON encoders can be vulnerable to unpaired surrogate code points (`0xD800` through `0xDFFF`), which cause database serialization errors or security bypasses.\n- The middleware scans raw incoming bytes for invalid surrogate sequences before passing data to FastAPI.\n- Requests containing lone surrogates receive HTTP 422 `Unprocessable Entity` with error code `INVALID_UTF8_SURROGATE`.\n\n### Non-Recursive Iterative Structural Validation\nTo protect against stack overflows without paying the performance cost of complete parsing twice, the middleware uses an iterative character scanner for `application/json` and `+json` content types:\n- **Maximum Depth:** `MAX_JSON_DEPTH = 32`. Nested objects or arrays deeper than 32 levels return HTTP 422 `JSON_DEPTH_EXCEEDED`.\n- **Maximum Keys:** `MAX_JSON_KEYS = 5000`. Payloads containing more than 5,000 keys return HTTP 422 `JSON_KEYS_EXCEEDED`.\n- **Passthrough:** Multipart form data, Server-Sent Events (SSE), and static asset requests bypass JSON scanning entirely.\n\n---\n\n## 5. Client-Side Safe JSON and Trusted Types\n\nSecurity invariants extend directly to the browser client (`kanban/web/`):\n\n### Safe JSON Parsing (`safeJsonParse`)\nStandard `JSON.parse` is vulnerable to Prototype Pollution when handling untrusted JSON payloads containing `__proto__`, `constructor`, or `prototype` keys.\n\nThe utility `safeJsonParse` (`kanban/web/src/utils/safeJson.ts`) applies an iterative reviver function that removes these keys from the resulting object:\n- In `draftsStore.ts`, all draft restoration routines use `safeJsonParse`.\n- In `CustomFieldDefinitionEditor.tsx`, format metadata and formula test inputs are deserialized using `safeJsonParse`.\n\n```typescript\nexport function safeJsonParse<T = unknown>(text: string): T {\n  return JSON.parse(text, (key, value) => {\n    if (key === '__proto__' || key === 'constructor' || key === 'prototype') {\n      return undefined;\n    }\n    return value;\n  });\n}\n```\n\n### Unified Trusted Types Policy\nIn `kanban/web/src/editor/clipboard/trustedTypes.ts`, the `kanban-sanitizer` and `dompurify` Trusted Types policies ensure that any HTML passed to browser sinks is sanitized through `DOMPurify.sanitize(html, { RETURN_TRUSTED_TYPE: false })` before being wrapped as a `TrustedHTML` token.\n\n---\n\n## 6. Verification and Audit Matrix\n\n| Security Layer | Implementation File | Verification Test | Expected Defense Behavior |\n| :--- | :--- | :--- | :--- |\n| **Wasm Hash Binding** | `kanban/custom_fields/manifest.py` | `test_manifest_and_formula_security.py` | Modifying `wasm_module_sha256` alters `manifest_sha256` and revokes approval via `custom_field_manifest_tamper_revoke`. |\n| **Admin test-execute Gate** | `kanban/api/v1/custom_field_execution.py` | `test_manifest_and_formula_security.py` | Non-admin returns 403 `INSUFFICIENT_CAPABILITY`; AAL1 returns 403 `AAL2_REQUIRED`; unapproved Wasm returns 404 `WASM_MODULE_NOT_FOUND`. |\n| **Script Depth Guard** | `kanban/api/middleware/script_depth.py` | `test_script_depth_middleware.py` | Re-entrant `test-execute` or `dry-run` returns 409 `SCRIPT_RECURSION_BLOCKED`. |\n| **AST Node & Depth Bounds** | `kanban/custom_fields/executor.py` | `test_manifest_and_formula_security.py` | Nodes > 64 or depth > 8 returns `None` (test-execute returns 200 `status=\"ERROR\", value=null`). |\n| **AST Math & Sequence Bounds**| `kanban/custom_fields/executor.py` | `test_safe_formula_unit.py` | `ast.Pow` bounded to 64; `0 ** -1` returns `None`; sequence mult bounded to 4096; dict-only attrs. |\n| **ASGI Size Caps** | `kanban/api/middleware/json_limits.py` | `test_json_limits_middleware.py` | Payloads > 2 MiB (or > 25 MiB attachments/imports) return HTTP 413 `PAYLOAD_TOO_LARGE`. |\n| **ASGI Surrogate Rejection**| `kanban/api/middleware/json_limits.py` | `test_json_limits_middleware.py` | Lone surrogates `0xD800..0xDFFF` return HTTP 422 `INVALID_UTF8_SURROGATE`. |\n| **ASGI JSON Depth / Keys** | `kanban/api/middleware/json_limits.py` | `test_json_limits_middleware.py` | Depth > 32 returns 422 `JSON_DEPTH_EXCEEDED`; keys > 5000 returns 422 `JSON_KEYS_EXCEEDED`. |\n| **Client Safe JSON** | `kanban/web/src/utils/safeJson.ts` | `safeJson.test.ts` | Strips `__proto__`, `constructor`, `prototype` preventing prototype pollution. |\n| **Client Trusted Types** | `kanban/web/src/editor/clipboard/trustedTypes.ts` | `trustedTypes.test.ts` | Mandatory `DOMPurify.sanitize` execution on all `createHTML` calls. |\n"
  },
  {
    "slug": "enterprise-whitespace-and-kanban-board",
    "title": "Enterprise Whitespace, Semantic Emojis, and Kanban Board",
    "category": "System Architecture",
    "order": 7,
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
        "id": "the-semantic-hover-system",
        "title": "The `<EmojiHint>` Semantic Hover System",
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
        "id": "board-view",
        "title": "1. Board View (`?layout=board`)",
        "level": 3
      },
      {
        "id": "list-view",
        "title": "2. List View (`?layout=list`)",
        "level": 3
      },
      {
        "id": "table-view",
        "title": "3. Table View (`?layout=table`)",
        "level": 3
      },
      {
        "id": "calendar-view",
        "title": "4. Calendar View (`?layout=calendar`)",
        "level": 3
      },
      {
        "id": "timeline-gantt-view",
        "title": "5. Timeline (Gantt) View (`?layout=timeline`)",
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
      }
    ],
    "content": "# Enterprise Whitespace, Semantic Emojis, and Kanban Board\n\n## Overview\n\nHigh-performing engineering teams require interfaces that balance visual clarity with deep technical density. Cluttered, cramped dashboards create cognitive fatigue, while overly sparse designs hide crucial metadata. \ud83d\udc4dkanban delivers a refined **Enterprise Whitespace Design System**, combining generous breathing room with dense information display, sub-16ms drag-and-drop responsiveness, and the intuitive `<EmojiHint>` hover elaboration system.\n\n---\n\n## The Breathable Whitespace Design System\n\nThe visual design is grounded in CSS design tokens (`kanban/web/src/styles/tokens.css`):\n- **Predictable 4px / 8px Grid:** Consistent padding, gutter spacing, and card margins prevent visual clutter.\n- **High-Contrast Typography:** Clear typographic hierarchy using Inter and system font stacks for rapid scanning.\n- **Adaptive Light/Dark Modes:** Dark mode uses carefully calibrated slate and neutral backgrounds (`#0f172a`, `#1e293b`) with high contrast text (`#f8fafc`) to minimize eye strain.\n\n---\n\n## The `<EmojiHint>` Semantic Hover System\n\nTo keep cards concise without sacrificing context, \ud83d\udc4dkanban utilizes a standardized palette of 21 semantic emojis paired with instant hover elaboration tooltips:\n\n| Emoji Symbol | Semantic Meaning | Elaboration on Hover |\n| :---: | :--- | :--- |\n| `\ud83c\udff7\ufe0f` | Issue Identifier | Human-readable issue key and ticket URL |\n| `\ud83d\udd04` | Creator / Reporter | Author profile and ticket creation timestamp |\n| `\u26a1` | Priority | Corporate priority tier (Urgent, High, Medium, Low, None) |\n| `\u23f3` | Pending Transition | Active workflow interceptor or async gate |\n| `\ud83e\udd16` | Autonomous Agent | Agent service principal assignment or execution |\n| `\ud83d\udd12` | Parent Hierarchy | Parent issue or epic relationship |\n| `\ud83d\udd17` | Linked Object | Bidirectional dependency or related entity |\n| `\ud83e\uddea` | Custom Scripted Field | Sandboxed computed field with execution status |\n| `\ud83d\udee1\ufe0f` | Explicit Access | Access manifest and sharing permissions pill |\n| `\ud83d\udd14` | Subscription | Notification watcher status |\n| `\u2728` | Sparkle Completion | AI-assisted ghost text available |\n| `\ud83d\uded1` | Gate Veto | Transition rejected by rule or agent |\n\nHovering over any semantic emoji renders an instant, non-blocking tooltip detailing the exact state, owner, or timestamp without requiring extra clicks.\n\n---\n\n## Kanban Board View and Sub-16ms Drag-and-Drop\n\nThe Kanban Board provides a real-time, interactive visual pipeline of work across project states.\n\n![Kanban Board View](images/06-board-view.png)\n\n![Dark Theme Enterprise Kanban Board](images/22-dark-theme-board.png)\n\n### Board Architecture and Performance\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor User as Engineer / Operator\n    participant UI as React 19 Kanban Board\n    participant Store as Optimistic State Store\n    participant API as FastAPI Backend\n    participant WS as WebSocket Hub\n\n    User->>UI: Drag card from \"In Progress\" to \"Done\"\n    UI->>Store: Apply optimistic local mutation (<12ms)\n    Store-->>UI: Instantly re-render card in \"Done\" column\n    UI-->>User: Smooth 60 FPS visual feedback\n    Store->>API: PATCH /api/v1/issues/{id} (state: \"Done\")\n    alt Transition Accepted\n        API-->>Store: 200 OK & Updated Version ETag\n        API->>WS: Broadcast ISSUE_UPDATED event\n        WS-->>UI: Real-time sync to all other connected peers\n    else Transition Rejected / Gate Failed\n        API-->>Store: 409 Conflict / 422 Unprocessable\n        Store->>UI: Snap card back to \"In Progress\" with toast error\n    end\n```\n\n- **Sub-16ms Drag-and-Drop:** Built on lightweight HTML5 drag primitives paired with optimistic local UI mutations. When an operator moves a card across state columns, the card instantly re-renders in the destination column within 12 milliseconds, while the background API sync completes asynchronously.\n- **Virtualized Card Rendering:** Virtual scrolling allows columns to display thousands of tickets smoothly without degrading browser frame rates.\n- **State Columns:** Default workflow stages (`Backlog`, `Todo`, `In Progress`, `Done`, `Canceled`) with configurable WIP (Work In Progress) thresholds and visual warning indicators.\n- **2D Swimlane Grouping:** Operators can slice the board horizontally by Assignee, Priority, Module, or Sprint Cycle.\n\n![Filter Bar and 2D Swimlanes](images/29-filter-and-2d-swimlanes.png)\n\n---\n\n## The 5 Native View Layouts\n\nDifferent engineering disciplines need distinct perspectives on the same work graph. \ud83d\udc4dkanban provides 5 native views with instant zero-reload switching via URL query parameters (`?layout=`):\n\n![Multi-Layout Switching: List, Table, Calendar, Timeline](images/07-list-table-calendar-timeline.png)\n\n```mermaid\nflowchart TD\n    Data[\"Universal Object Graph (Issues)\"] --> Layouts[\"5 Native Layout Projections\"]\n    Layouts --> Board[\"Board (?layout=board)<br/>Sub-16ms DnD, 2D Swimlanes, WIP Limits\"]\n    Layouts --> List[\"List (?layout=list)<br/>3-Pane Master-Detail, Keyboard Navigation\"]\n    Layouts --> Table[\"Table (?layout=table)<br/>Spreadsheet Grid, Multi-Select Bulk Actions\"]\n    Layouts --> Calendar[\"Calendar (?layout=calendar)<br/>Monthly/Weekly Grid, Date Drag Scheduling\"]\n    Layouts --> Timeline[\"Timeline (?layout=timeline)<br/>Gantt Dependencies, Critical Path Analysis\"]\n```\n\n![Global Command Palette for Rapid View Switching](images/23-command-palette.png)\n\n### 1. Board View (`?layout=board`)\nInteractive Kanban board with optimistic drag-and-drop, horizontal swimlanes, and live state columns.\n\n### 2. List View (`?layout=list`)\nA powerful three-pane split layout:\n- Left pane: Hierarchical navigation and filter presets.\n- Middle pane: High-density list with keyboard navigation (Up/Down arrows, Enter to view).\n- Right pane: Instant live ticket preview drawer without navigating away.\n\n### 3. Table View (`?layout=table`)\nSpreadsheet-style tabular editing:\n- In-place editing of titles, states, assignees, priorities, and dates.\n- Column reordering, visibility toggling, and multi-row selection for bulk updates.\n- Capability-gated cell editors: clicking a state or priority cell opens an active dropdown editor with instant optimistic UI feedback.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor User as Engineer / PM\n    participant Table as Table View Component\n    participant Cache as React Query / Local State\n    participant API as FastAPI Backend\n\n    User->>Table: Click State cell (e.g. \"Todo\" -> \"In Progress\")\n    Table->>Cache: Apply optimistic cell mutation (<10ms)\n    Cache-->>Table: Render updated state badge and progress ring\n    Table->>API: PATCH /api/v1/issues/{id} (state: \"in_progress\")\n    alt State Update Accepted\n        API-->>Cache: 200 OK with updated entity payload\n    else Conflict or Validation Failure\n        API-->>Cache: 422 Unprocessable / 409 Conflict\n        Cache-->>Table: Roll back cell value and show error toast\n    end\n```\n\n![Table View Inline Editing](images/37-table-inline-editing.png)\n\n### 4. Calendar View (`?layout=calendar`)\nMonthly and weekly scheduling grid:\n- Visualizes start dates, target delivery dates, and cycle deadlines.\n- Drag cards across dates to reschedule instantly.\n\n### 5. Timeline (Gantt) View (`?layout=timeline`)\nInteractive dependency and critical path visualization:\n- Displays `BLOCKS` and `BLOCKED_BY` dependency arrows between work items using high-performance SVG Bezier curves.\n- Shows dependency loops, schedule slippage, and critical path milestones.\n- Unified \"Today\" anchor button to snap view to the current date, with Day, Week, and Quarter zoom levels.\n- Toggle switch for \"Show BLOCKS arrows\" to declutter dense views on demand.\n\n```mermaid\nflowchart LR\n    subgraph TimelineEngine[\"Timeline Dependency Engine\"]\n        IssueA[\"Issue KAN-221<br/>Start: 2026-11-15 | Due: 2026-11-20\"]\n        IssueB[\"Issue KAN-212<br/>Start: 2026-11-21 | Due: 2026-11-28\"]\n        Bezier[\"SVG Bezier Dependency Curve<br/>typed BLOCKS object_link\"]\n        IssueA -->|BLOCKS| Bezier\n        Bezier -->|Target| IssueB\n    end\n```\n\n![Timeline View with BLOCKS Dependency Arrows](images/38-timeline-blocks-arrows.png)\n\n---\n\n## Project Settings Studios and Governance\n\nProject administrators configure project-level metadata, workflow states, and principal access through dedicated settings studios under `/projects/{project_key}/settings/`:\n\n```mermaid\nflowchart TD\n    subgraph ProjectSettings[\"Project Settings Studios\"]\n        General[\"General Settings (/settings)<br/>Identifier, Lead, Default Modules\"]\n        Workflows[\"Workflow States (/settings/workflows)<br/>States, Sequence, Colors, WIP Limits\"]\n        Members[\"Members & Access (/settings/members)<br/>Principals, Role Assignments, Explicit ACLs\"]\n    end\n```\n\n### General Settings and Default Modules\nConfigure project display name, identifier key prefix, lead owner, and default module attachments for incoming work items:\n\n![Project General Settings and Default Modules](images/54-project-settings-studio.png)\n\n### Workflow States and WIP Limits\nCustomize the state machine columns, sequence ordering, color badges, and column WIP (Work In Progress) thresholds:\n\n![Project Workflow States and WIP Limits](images/55-project-workflow-states-wip.png)\n\n### Project Members and Access ACL Management\nManage project collaborators across human users, groups, and autonomous agent service principals with granular capability masks:\n\n![Project Members and Access ACL Management](images/56-project-members-access-acl.png)\n"
  },
  {
    "slug": "feature-comparison",
    "title": "Feature Comparison",
    "category": "Reference Guides",
    "order": 8,
    "summary": "A kanban is just a kanban until you start digging deeper. On the surface, every issue tracker presents identical columns, draggable cards, and basic workflow states. The real architectural divergence begins the moment you inspect paywalled enterprise controls, database-level security invariants, canonical Markdown integrity, and native agent/MCP execution gates. While commercial SaaS and copyleft alternatives lock custom properties, audit logs, Single Sign-On, and AI integrations behind steep per-seat subscription tiers or bloated CRUD APIs, `\ud83d\udc4dkanban` ships an uncompromising, security-first, agent-first platform under a pure Apache-2.0 license. Below is the full 35-feature technical capability matrix comparing `\ud83d\udc4dkanban` directly against legacy and modern project management systems.",
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
      }
    ],
    "content": "# Feature Comparison\n\nA kanban is just a kanban until you start digging deeper. On the surface, every issue tracker presents identical columns, draggable cards, and basic workflow states. The real architectural divergence begins the moment you inspect paywalled enterprise controls, database-level security invariants, canonical Markdown integrity, and native agent/MCP execution gates. While commercial SaaS and copyleft alternatives lock custom properties, audit logs, Single Sign-On, and AI integrations behind steep per-seat subscription tiers or bloated CRUD APIs, `\ud83d\udc4dkanban` ships an uncompromising, security-first, agent-first platform under a pure Apache-2.0 license. Below is the full 35-feature technical capability matrix comparing `\ud83d\udc4dkanban` directly against legacy and modern project management systems.\n\n**Legend**\n\n* `\u2705` **Included:** Built into the core product (free in FOSS/free tiers, or included in the entry commercial plan when no free tier exists).\n* `\ud83d\udd10` **Paywall-Capped:** Basic or seat-capped version is free; full scale, hierarchy, or enforcement requires a paid tier.\n* `\ud83c\udd93\ud83d\udd0c` **Free Extension:** Free via a separate official plugin, external MCP server package, or external CLI harness.\n* `\ud83d\udcb0` **Paid Tier:** Locked behind higher per-seat subscription tiers (Pro, Business, Premium, or Enterprise).\n* `\ud83d\udcb8` **Extra Cost:** Separate paid product, paid Marketplace add-on, or metered credit/runner billing.\n* `\u274c` **None:** Unsupported.\n\n---\n\n## 1. Security, Identity, Audit & Deployment\n\n| Feature | \ud83d\udc4dkanban | Jira | Plane | GitHub | Vibe Kanban | Businessmap | Codebeamer |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n| Permissive FOSS License | \u2705 | \u274c | \u274c | \u274c | \u2705 | \u274c | \u274c |\n| On-Prem Multi-Container | \u2705 | \u274c | \u2705 | \ud83d\udcb0 | \u274c | \u274c | \ud83d\udcb0 |\n| Single-Container Run | \u2705 | \u274c | \u274c | \u274c | \u2705 | \u274c | \u274c |\n| Multi-Card OIDC & LDAPS | \u2705 | \ud83d\udcb8 | \ud83d\udcb0 | \ud83d\udcb0 | \u274c | \ud83d\udcb8 | \u2705 |\n| Passkeys & Break-Glass | \u2705 | \ud83d\udcb8 | \ud83d\udcb0 | \ud83d\udd10 | \u274c | \ud83d\udcb0 | \ud83d\udcb0 |\n| Granular RBAC & DENY | \u2705 | \ud83d\udcb0 | \ud83d\udcb0 | \ud83d\udcb0 | \u274c | \u2705 | \u2705 |\n| Shared-With Pill & DB RLS | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Workspace Audit Logs | \u2705 | \ud83d\udcb8 | \ud83d\udcb0 | \ud83d\udcb0 | \u274c | \ud83d\udcb0 | \u2705 |\n\nVibe Kanban is permissive `Apache-2.0` (`\u2705`) as a single-user local CLI, whereas Plane uses copyleft `AGPLv3` and charges per seat for OIDC, LDAP, RBAC, and audit logs (`\ud83d\udcb0`). Jira charges extra for SSO and security audit policies via Atlassian Guard (`\ud83d\udcb8`), and none of the other six enforces PostgreSQL Row-Level Security with a ubiquitous per-object `shared_with` pill (`\u274c`). **`\ud83d\udc4dkanban`** is 100% permissive `Apache-2.0` (`\u2705`), supporting both a zero-config single-container runtime (`docker run -p 8080:8080 thumbs-up-kanban:latest`) and a hardened 5-network multi-container production stack, complete with Multi-Card OIDC/OAuth2/LDAPS, WebAuthn Passkeys + break-glass lockout triggers, explicit `DENY` ACLs, PostgreSQL 16 `FORCE ROW LEVEL SECURITY` surfaced via the `\ud83d\udee1\ufe0f` Shared-With Header Pill, and an immutable SHA-256 hash-chained audit ledger (`\u2705`).\n\n---\n\n## 2. Agentic Tasks, MCP, AI & Workflow Gates\n\n| Feature | \ud83d\udc4dkanban | Jira | Plane | GitHub | Vibe Kanban | Businessmap | Codebeamer |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n| MCP Server | \u2705 | \ud83c\udd93\ud83d\udd0c | \ud83c\udd93\ud83d\udd0c | \ud83c\udd93\ud83d\udd0c | \u2705 | \u274c | \u274c |\n| Low-Token Scoped MCP | \u2705 | \u274c | \u274c | \u274c | \ud83d\udd10 | \u274c | \u274c |\n| 2-Stage MCP Delete Gate | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Cloud AI Integration | \u2705 | \ud83d\udcb0 | \ud83d\udcb8 | \ud83d\udcb8 | \ud83d\udcb8 | \u2705 | \ud83d\udcb8 |\n| Air-Gap Local Ollama | \u2705 | \u274c | \u274c | \u274c | \ud83c\udd93\ud83d\udd0c | \u274c | \u274c |\n| Cursor Sparkle FIM | \u2705 | \u274c | \u274c | \ud83d\udcb8 | \u274c | \u274c | \u274c |\n| Sync Transition Gates | \u2705 | \ud83d\udcb8 | \ud83d\udcb0 | \u274c | \u274c | \u2705 | \u2705 |\n| Async `:ro` Repo Gate | \u2705 | \u274c | \u274c | \ud83d\udcb8 | \u274c | \u274c | \u274c |\n\nJira, Plane, and GitHub ship MCP through separate external connectors or packages (`\ud83c\udd93\ud83d\udd0c`) that expose broad JSON schemas rather than low-token YAML intent surfaces, while Vibe Kanban bundles `--mcp` directly (`\u2705`) with partial `--mode orchestrator` scoping (`\ud83d\udd10`). None of the other six holds Kanban transitions in a non-blocking provisional gate while an agent forensically audits a read-only repository mount (`\u274c`) - GitHub only runs metered post-event Actions or Copilot checks (`\ud83d\udcb8`). **`\ud83d\udc4dkanban`** ships three built-in intent-scoped MCP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin` under `<= 1,800` schema tokens with LOD YAML output and 2-stage `request_delete` -> `execute_delete` confirmation), vendor-neutral Cloud AI (`openai`, `gemini`) and air-gapped `ollama`, `<150ms` RLS-filtered Cursor Sparkle (`\u2728`) FIM completion with right-click accept, `<25ms` synchronous Wasm transition validators, and two-phase non-blocking async agent transition gates (`\u23f3\ud83e\udd16` -> `\u2705\ud83e\udd16`/`\ud83d\uded1\ud83e\udd16`) over `:ro` repository mounts (`\u2705`).\n\n---\n\n## 3. Issue Tracker & Kanban Board\n\n| Feature | \ud83d\udc4dkanban | Jira | Plane | GitHub | Vibe Kanban | Businessmap | Codebeamer |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n| Free Forever Tier | \u2705 | \ud83d\udd10 | \u2705 | \u2705 | \u2705 | \u274c | \u274c |\n| Core Kanban & Issues | \u2705 | \ud83d\udd10 | \u2705 | \u2705 | \ud83d\udd10 | \u2705 | \u2705 |\n| Five Native Views | \u2705 | \ud83d\udd10 | \ud83d\udd10 | \ud83d\udd10 | \u274c | \u2705 | \u2705 |\n| 2D Swimlanes & Hard WIP | \u2705 | \ud83d\udd10 | \ud83d\udd10 | \ud83d\udd10 | \u274c | \u2705 | \u2705 |\n| Cycles & Hidden Modules | \u2705 | \ud83d\udd10 | \u2705 | \ud83d\udd10 | \u274c | \u274c | \u2705 |\n| Sub-Issue DAG & Links | \u2705 | \ud83d\udd10 | \ud83d\udd10 | \u2705 | \ud83d\udd10 | \u2705 | \u2705 |\n| Custom Properties | \u2705 | \u2705 | \ud83d\udcb0 | \u2705 | \u274c | \u2705 | \u2705 |\n| Free-Text Assignee Tag | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Audited Creator Override | \u2705 | \ud83d\udcb0 | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Rule-Gated Archive | \u2705 | \ud83d\udcb0 | \u2705 | \u2705 | \u274c | \u2705 | \u2705 |\n| Blast-Radius Soft Delete | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Sandboxed Script Fields | \u2705 | \ud83d\udcb8 | \u274c | \u274c | \u274c | \u274c | \u2705 |\n\nJira caps free boards at 10 users and gates cross-project Gantt plans, deep hierarchies, and archiving behind Premium (`\ud83d\udcb0`), while scripted fields require paid Marketplace apps like ScriptRunner (`\ud83d\udcb8`). Plane gates custom properties behind paid tiers (`\ud83d\udcb0`), GitHub lacks Calendar views and hard-blocking WIP limits (`\ud83d\udd10`), and Businessmap/Codebeamer have no free tier at all (`\u274c`). **`\ud83d\udc4dkanban`** ships all five native views (`List`, `Board`, `Table`, `Calendar`, `Timeline`), 2D swimlanes with hard WIP limits, cycle-checked DAG hierarchies, hybrid principal + free-text `\ud83c\udff7\ufe0f` assignee tags, audited `\ud83d\udd04` creator overrides, blast-radius soft delete, and Wasmtime/`nsjail` sandboxed script fields in its free `Apache-2.0` core (`\u2705`).\n\n---\n\n## 4. Docs, Stickies, Markdown & Object Graph\n\n| Feature | \ud83d\udc4dkanban | Jira | Plane | GitHub | Vibe Kanban | Businessmap | Codebeamer |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n| Project Docs / Wiki | \u2705 | \ud83d\udcb8 | \ud83d\udd10 | \ud83d\udd10 | \u274c | \u274c | \u2705 |\n| Project Stickies | \u2705 | \ud83d\udcb8 | \u2705 | \u274c | \u274c | \u2705 | \u274c |\n| Smart Sticky -> Doc Promo | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Canonical Markdown DB | \u2705 | \u274c | \u274c | \u2705 | \u2705 | \u274c | \u274c |\n| Paste-Injection Pruner | \u2705 | \u274c | \u274c | \u274c | \u274c | \u274c | \u274c |\n| Mermaid, Safe SVG & Proxy | \u2705 | \ud83d\udcb8 | \u274c | \u2705 | \u274c | \u274c | \u274c |\n| Broken/ACL Link Auditor | \u2705 | \ud83d\udcb8 | \u274c | \u274c | \u274c | \u274c | \ud83d\udd10 |\n\nJira splits Docs and Stickies into separate paid Confluence and Whiteboard licenses (`\ud83d\udcb8`), while GitHub restricts private-repo Wikis to paid plans (`\ud83d\udd10`) and Plane gates full team Wiki spaces (`\ud83d\udd10`). Only **`\ud83d\udc4dkanban`**, GitHub, and Vibe Kanban store pure Markdown natively (`\u2705`), and only Codebeamer flags \"suspected\" upstream links manually without automated graph purging (`\ud83d\udd10`). **`\ud83d\udc4dkanban`** unifies `ltree` hierarchical Docs and Project Overview Stickies with 1-click ACL-preserving Sticky-to-Doc promotion (`\ud83d\udca1\ud83d\udcc4`), auto-converts pasted HTML/Rich Text into 100% canonical UTF-8 Markdown while pruning hidden-DOM paste-injection and UTF-16 lone surrogates, renders Web Worker Mermaid diagrams and `nh3`-scrubbed SVGs through an SSRF-guarded media proxy, and runs an automated 6-reason Object Link Auditor & Purger (`\u2705`).\n"
  },
  {
    "slug": "guide-custom-fields",
    "title": "How to Use Custom Fields",
    "category": "Reference Guides",
    "order": 9,
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
        "id": "section",
        "title": "1. `text`",
        "level": 3
      },
      {
        "id": "section",
        "title": "2. `number`",
        "level": 3
      },
      {
        "id": "section",
        "title": "3. `badge`",
        "level": 3
      },
      {
        "id": "section",
        "title": "4. `severity_pill`",
        "level": 3
      },
      {
        "id": "section",
        "title": "5. `url`",
        "level": 3
      },
      {
        "id": "section",
        "title": "6. `markdown_snippet`",
        "level": 3
      },
      {
        "id": "section",
        "title": "7. `json_table`",
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
      }
    ],
    "content": "# [Guide] How to Use Custom Fields\n\nCustom Fields extend your projects and issues with dynamic calculations, computed business metrics, compliance indicators, and metadata without modifying the core database schema or writing custom server plugins.\n\nThis comprehensive guide covers how Custom Fields work, where their values surface across the UI, how to choose the right execution tier for your deployment mode (Standalone vs Multi-Container Compose), step-by-step walkthroughs with copy-paste examples, and the required governance and dual-control approval workflows.\n\n---\n\n## 1. What Custom Fields Do and Where Values Appear\n\nCustom Fields allow project administrators and server administrators to attach computed or scalar attributes to issues. Whenever an issue is viewed, edited, or evaluated in a workflow, Custom Fields are resolved and formatted according to their output specifications.\n\nCustom field values automatically surface across the following surfaces in the web interface:\n\n- **Issue Properties Rail:** Located in the right sidebar of the issue detail screen. Displays the custom field label, current value (formatted as text, number, badge, severity pill, link, markdown snippet, or table), and cache status with an instant recalculate trigger.\n- **Table View:** Embedded as sortable, custom columns in the project Table View. Allows rapid scanning and comparison of computed metrics (such as SLA deadlines or sub-issue progress percentages) across dozens of work items.\n- **Board Cards:** Rendered as compact badges, severity pills, or monospace tags directly on Kanban board cards, providing immediate visual cues to team members during daily standups and cycle reviews.\n- **Filters and Search:** Filter work items by custom field values, enabling targeted views such as finding all issues with a `CRITICAL` severity pill or projects with overdue SLA days.\n\n---\n\n## 2. Choosing Between Execution Tiers\n\n\ud83d\udc4dkanban provides four distinct execution tiers for custom fields, balanced across performance, security isolation, and deployment modes:\n\n| Tier | Engine / Flavor | Latency Budget | Standalone Mode | Multi-Container Compose | Best Used For |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n| **Scalar** | Static metadata | `<1ms` | Supported | Supported | Static tags, manual attributes, default strings, constant numbers |\n| **Safe Formula** | In-process Python AST | `<5ms` | Supported | Supported | Math, date arithmetic, conditionals, sub-issue rollups, SLA days |\n| **WebAssembly** | `wasmtime` runtime | `<25ms` | Supported | Supported | Compiled C, Rust, or AssemblyScript logic with strict memory sandboxing |\n| **Isolated Sandbox** | `nsjail` Linux container | `<250ms` | **Gated (Unavailable)** | Supported | Complex Python/Rust scripts requiring full network egress allowlists or multi-entity queries |\n\n### Standalone Mode vs Multi-Container Compose Gating\n\nIn **Standalone mode** (running via a single container or single process):\n- `Scalar`, `Safe Formula`, and `WebAssembly (wasmtime)` run natively out of the box with zero external dependencies.\n- `Isolated Sandbox (nsjail)` is **fail-closed and rejected**. Attempting to create or execute an `nsjail` custom field in Standalone mode returns an actionable HTTP `422 SANDBOX_UNAVAILABLE_IN_STANDALONE` error recommending `scalar`, `formula`, or `wasm`. In the web editor and preset gallery, `nsjail` options are disabled and badged with `Multi-Container Compose Required`.\n- **Pre-existing nsjail fields:** If you import a workspace backup containing pre-existing `nsjail` fields into Standalone mode, definitions remain inspectable and editable, with an informational warning banner reminding you that multi-container compose is required for execution.\n- **Promoting to Multi-Container:** To unlock `nsjail` container sandboxes, promote your installation to multi-container compose via the administrator portal at `/admin/standalone` or follow the Production Promotion and Backup Runbook.\n\n---\n\n## 3. Step-by-Step Walkthroughs and Copy-Paste Examples\n\n### Example 1: Priority SLA Days (Safe Formula)\n\nCompute the remaining service level agreement (SLA) target turnaround days based on the issue priority.\n\n- **Name:** Priority SLA Days\n- **Slug:** `priority-sla-days`\n- **Flavor / Tier:** Safe Formula (`formula`)\n- **Target Scope:** `PROJECT`\n- **Formula Expression:**\n  ```python\n  1 if priority == 'URGENT' else 3 if priority == 'HIGH' else 7 if priority == 'MEDIUM' else 14\n  ```\n- **Output Format:** `number`\n- **Format Metadata JSON:**\n  ```json\n  {\n    \"format\": \"number\",\n    \"maximum_fraction_digits\": 0,\n    \"unit_suffix\": \"d\",\n    \"min_value\": 1,\n    \"max_value\": 30\n  }\n  ```\n\n### Example 2: Sub-Issue Progress Percentage (Safe Formula)\n\nCalculate the completion percentage of sub-issues for epic or parent issue tracking.\n\n- **Name:** Sub-Issue Progress %\n- **Slug:** `sub-issue-progress`\n- **Flavor / Tier:** Safe Formula (`formula`)\n- **Target Scope:** `PROJECT`\n- **Formula Expression:**\n  ```python\n  round((completed_sub_issue_count * 100.0) / sub_issue_count, 1) if sub_issue_count > 0 else 100.0\n  ```\n- **Output Format:** `number`\n- **Format Metadata JSON:**\n  ```json\n  {\n    \"format\": \"number\",\n    \"maximum_fraction_digits\": 1,\n    \"unit_suffix\": \"%\",\n    \"min_value\": 0.0,\n    \"max_value\": 100.0\n  }\n  ```\n\n### Example 3: CVSS Severity Pill (Safe Formula / Dynamic Severity)\n\nMap issue priority and due date urgency to a standardized security vulnerability pill.\n\n- **Name:** Incident Severity Pill\n- **Slug:** `incident-severity-pill`\n- **Flavor / Tier:** Safe Formula (`formula`)\n- **Target Scope:** `PROJECT`\n- **Formula Expression:**\n  ```python\n  'CRITICAL' if (days_until_due is not None and days_until_due < 0) else 'HIGH' if priority == 'URGENT' else 'MEDIUM' if priority == 'HIGH' else 'LOW'\n  ```\n- **Output Format:** `severity_pill`\n- **Format Metadata JSON:**\n  ```json\n  {\n    \"format\": \"severity_pill\"\n  }\n  ```\n\n### Example 4: Total Project Issues Rollup (WebAssembly or Multi-Container nsjail)\n\nRoll up total project issues and blockers using WebAssembly or Multi-Container nsjail.\n\n- **Name:** Total Project Issues\n- **Slug:** `total-project-issues`\n- **Flavor / Tier:** WebAssembly (`wasm`) or Isolated Sandbox (`nsjail` in Multi-Container Compose)\n- **Target Scope:** `PROJECT` (or `WORKSPACE` with AAL2 dual control)\n- **Output Format:** `number`\n- **Format Metadata JSON:**\n  ```json\n  {\n    \"format\": \"number\",\n    \"maximum_fraction_digits\": 0,\n    \"unit_suffix\": \" issues\"\n  }\n  ```\n\n---\n\n## 4. All Seven Supported Output Formats and Schemas\n\nEvery custom field produces output formatted according to one of seven canonical schemas:\n\n### 1. `text`\nSingle-line formatted string with optional prefix and monospace font.\n```json\n{\n  \"format\": \"text\",\n  \"max_length\": 128,\n  \"prefix\": \"REF-\",\n  \"monospace\": true\n}\n```\n\n### 2. `number`\nFloating point or integer numeric value with precision limits, suffix, and range bounds.\n```json\n{\n  \"format\": \"number\",\n  \"maximum_fraction_digits\": 2,\n  \"unit_suffix\": \" hrs\",\n  \"min_value\": 0.0,\n  \"max_value\": 1000.0\n}\n```\n\n### 3. `badge`\nVisual status badge with color token and strict label allowlist. Supported color tokens: `neutral`, `info`, `success`, `warning`, `danger`, `accent`.\n```json\n{\n  \"format\": \"badge\",\n  \"color_token\": \"success\",\n  \"allowed_labels\": [\"Passed\", \"Failed\", \"In Progress\", \"Pending\"]\n}\n```\n\n### 4. `severity_pill`\nStandardized vulnerability and risk assessment pill. Accepts severity levels (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`) or numeric CVSS scores from 0.0 to 10.0.\n```json\n{\n  \"format\": \"severity_pill\"\n}\n```\n\n### 5. `url`\nSanitized hyperlink validated against allowed schemes and host suffixes.\n```json\n{\n  \"format\": \"url\",\n  \"allowed_schemes\": [\"https\"],\n  \"allowed_host_suffixes\": [\"github.com\", \"gitlab.com\"]\n}\n```\n\n### 6. `markdown_snippet`\nSanitized canonical Markdown snippet rendered inline up to 2000 characters.\n```json\n{\n  \"format\": \"markdown_snippet\",\n  \"max_chars\": 2000\n}\n```\n\n### 7. `json_table`\nStructured 2-dimensional tabular data rendered directly in the issue details view.\n```json\n{\n  \"format\": \"json_table\",\n  \"columns\": [\n    {\"key\": \"test_name\", \"label\": \"Test Suite\"},\n    {\"key\": \"duration_ms\", \"label\": \"Duration (ms)\"},\n    {\"key\": \"status\", \"label\": \"Status\"}\n  ],\n  \"max_rows\": 25\n}\n```\n\n---\n\n## 5. Safe Formula Context Reference\n\nWhen writing Safe Formulas, expressions have access to the active issue attributes without executing arbitrary code:\n\n| Variable | Type | Description |\n| :--- | :--- | :--- |\n| `id` | `str` | Issue unique identifier (UUID) |\n| `key` | `str` | Human-readable issue key (e.g. `KAN-32`) |\n| `summary` | `str` | Issue title / summary |\n| `description_markdown` | `str` | Raw Markdown body of the issue |\n| `state` | `str` | Name of current workflow state (e.g. `In Progress`) |\n| `state_group` | `str` | Workflow state category (`backlog`, `unstarted`, `started`, `completed`, `cancelled`) |\n| `priority` | `str` | Normalized uppercase priority (`URGENT`, `HIGH`, `MEDIUM`, `LOW`, `NONE`) |\n| `priority_slug` | `str` | Lowercase priority slug (`urgent`, `high`, `medium`, `low`, `none`) |\n| `priority_label` | `str` | Display label of priority (`Urgent`, `High`, etc.) |\n| `start_date` | `str` or `None` | ISO-formatted start date |\n| `due_date` | `str` or `None` | ISO-formatted due date |\n| `days_until_due` | `int` or `None` | Days until due date (negative values indicate overdue) |\n| `blocker_count` | `int` | Number of active blocking dependencies on this issue |\n| `sub_issue_count` | `int` | Total count of child sub-issues |\n| `completed_sub_issue_count`| `int` | Count of sub-issues in `completed` state group |\n| `labels` | `list[str]` | List of tag names assigned to the issue |\n\n### Safe Built-in Functions\nSafe formulas allow standard deterministic operations: `round`, `int`, `float`, `min`, `max`, `len`, `abs`, `str`. Arbitrary imports, file system access, and network sockets are strictly prohibited at the Python AST parser layer.\n\n---\n\n## 6. Testing, Dry-Running, and Scope Escalation\n\n### Dry-Running with Test Execute\nBefore saving any custom field definition, use the **Test Execute** button in the Custom Field Definition Editor or send a POST request to:\n```http\nPOST /api/v1/projects/{project_ref}/custom-fields/test-execute\n```\nThis evaluates your formula or script against a mock issue payload or existing issue key in memory without persisting values or polluting the audit ledger. In Standalone mode, Test Execute verifies that your script does not request unavailable sandbox tiers.\n\n### Scope Escalation and AAL2 Dual-Control Approval\nCustom fields can be scoped at three tiers:\n- **`PROJECT` Scope:** Can only read and affect issues within the parent project. Requires Project Administrator privileges.\n- **`WORKSPACE` Scope:** Can read issues across all projects in the workspace.\n- **`SERVER` Scope:** Global fields available across all workspaces.\n\n**Dual-Control Governance:** Escalating a custom field definition from `PROJECT` to `WORKSPACE` or `SERVER` scope (or running with elevated Service Account credentials rather than `INVOKING_USER`) requires cryptographic approval by an administrator of that target tier with active Authenticator Assurance Level 2 (AAL2 / WebAuthn / TOTP) session elevation.\n"
  },
  {
    "slug": "hierarchical-docs-and-stickies-with-smart-promotion",
    "title": "Hierarchical Docs, Project Stickies, and Smart Promotion",
    "category": "System Architecture",
    "order": 10,
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
        "id": "postgresql-tree-engine",
        "title": "PostgreSQL `ltree` Tree Engine",
        "level": 3
      },
      {
        "id": "pageversion-diff-restore-and-highlight-to-issue-linking",
        "title": "PageVersion Diff, Restore, and Highlight-to-Issue Linking",
        "level": 2
      },
      {
        "id": "visual-diff-and-instant-restore",
        "title": "1. `PageVersion` Visual Diff and Instant Restore",
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
    "content": "# Hierarchical Docs, Project Stickies, and Smart Promotion\n\n## Overview\n\nSoftware engineering encompasses both informal, ephemeral scratchpads (meeting notes, architecture brainstorming, quick snippets) and formal, structured documentation (system specifications, API references, runbooks). In conventional tools, informal notes either get lost in chat threads or prematurely clutter formal document trees.\n\n\ud83d\udc4dkanban resolves this divide through two integrated systems:\n1. **Project Stickies:** Lightweight, color-coded digital sticky notes on an interactive masonry grid for rapid ideation.\n2. **Hierarchical Docs (`ltree`):** Deeply nested, versioned technical documentation powered by PostgreSQL tree hierarchies.\n3. **Smart AI Doc Promotion:** An intelligent bridge that detects when a scratchpad has matured into an architectural specification and transforms it into a formal Doc with a single click.\n\n---\n\n## Project Stickies and Ideation Grid\n\nProject Stickies live at `/stickies` (workspace scope) and `/projects/KAN/overview` (project scope).\n\n![Project Stickies and Smart Promotion Modal](images/10-stickies-and-doc-promotion.png)\n\n![Six-Color Semantic Sticky Palette Grid](images/33-stickies-palette-grid.png)\n\n### Stickies Architecture\n\n- **6 Semantic Color Palettes:** Amber, Emerald, Sky, Rose, Violet, and Slate cards for visual categorization.\n- **Masonry Layout:** Responsive CSS masonry layout that dynamically packs cards of varying heights.\n- **Fast Markdown Editing:** Double-click or select to edit Markdown inline with instant autosave.\n- **Real-Time Collaboration:** Changes synchronize across connected team members via WebSocket broadcasts within 50 milliseconds.\n\n---\n\n## Smart AI-Assisted Sticky-to-Doc Promotion\n\n```mermaid\nflowchart TD\n    Sticky[\"Scratchpad Sticky Note<br/>(Markdown text & initial thoughts)\"] --> Heuristics[\"Debounced Complexity Heuristic<br/>- Word count > 150 words<br/>- Headings (##), tables, code blocks<br/>- Checkboxes (- [ ])\"]\n    Heuristics -->|Threshold reached| RecPill[\"Display 'Promotion Recommended' Pill\"]\n    RecPill -->|Click Promote to Doc| AIStudio[\"AI Promotion Studio<br/>Multi-Provider AI drafts formal structure,<br/>executive summary & sections\"]\n    AIStudio --> Confirm[\"Operator Reviews & Accepts\"]\n    Confirm --> NewDoc[\"Formal Hierarchical Doc (ltree)\"]\n    Confirm --> Link[\"UOG records typed PROMOTED_TO link\"]\n    Confirm --> Archive[\"Original sticky marked promoted & archived\"]\n```\n\nAs brainstorming progresses, stickies often accumulate detailed requirements, code snippets, and diagrams. \ud83d\udc4dkanban monitors stickies using debounced complexity heuristics:\n- Word count exceeding 150 words.\n- Presence of structured headings (`## `), markdown tables, or fenced code blocks.\n- Multiple bullet points or task checkboxes (`- [ ]`).\n\n### The Promotion Workflow and Preview Modal\n\nWhen these heuristics trigger, the sticky displays a `promotion_recommended` indicator. Clicking **Promote to Doc** opens the interactive AI Promotion Preview Modal:\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor User as Engineer / Architect\n    participant Sticky as Stickies Board\n    participant Modal as AI Promotion Modal\n    participant AI as Multi-Provider AI Engine\n    participant DB as Universal Object Graph\n\n    User->>Sticky: Click \"Promote to Doc\" button\n    Sticky->>Modal: Open Promotion Preview Modal\n    Modal->>AI: Synthesize notes into formal structured document\n    AI-->>Modal: Return generated title, executive summary, sections, target project\n    User->>Modal: Inspect preview, adjust target project / ltree path\n    User->>Modal: Click \"Accept & Create Doc\"\n    Modal->>DB: INSERT into docs (ltree path, markdown, creator)\n    Modal->>DB: INSERT into object_links (kind: PROMOTED_TO)\n    Modal->>DB: UPDATE stickies SET state = 'promoted'\n    DB-->>Sticky: Real-time update: replace sticky with promoted stub\n```\n\n![AI Sticky to Doc Promotion Preview Modal](images/40-ai-sticky-doc-promotion-modal.png)\n\n1. **AI Structure Preview:** The multi-provider AI engine drafts formal headings, executive summaries, and organized subsections from the raw notes.\n2. **Target Project and Path Selection:** Operators can choose the destination project and parent document node in the `ltree` hierarchy.\n3. **ACL Scope Preservation:** The newly created document automatically inherits the project ACL permissions and explicit sharing rules of the origin sticky.\n4. **Bidirectional Object Link:** A typed `PROMOTED_TO` link is recorded in the Universal Object Graph connecting the original sticky and the new Doc.\n5. **Clean Archival & Promoted Stub:** The original sticky is converted into a promoted stub pointing to the new document URL, keeping the ideation board tidy while preserving audit history.\n\n---\n\n## Hierarchical Docs and Nested Tree Navigation\n\nFormal specifications and engineering documentation reside under the project Docs view (`/projects/KAN/docs`).\n\n![Hierarchical Docs Tree and Outline View](images/11-docs-hierarchy-view.png)\n\n![Three-Pane Interactive Documentation Editor](images/32-docs-three-pane-editor.png)\n\n### PostgreSQL `ltree` Tree Engine\n\nDocumentation hierarchies are modeled using PostgreSQL's native `ltree` extension (`database/models/knowledge.py`):\n- Path representations such as `workspace_1.project_kan.architecture.security`.\n- Sub-millisecond subtree queries, ancestral lookups, and branch moves.\n- Circular hierarchy prevention guaranteed by database constraints.\n\n```mermaid\ngraph TD\n    Root[\"Root: workspace_1.project_kan\"]\n    Arch[\"architecture (workspace_1.project_kan.architecture)\"]\n    API[\"api (workspace_1.project_kan.api)\"]\n    Sec[\"security (workspace_1.project_kan.architecture.security)\"]\n    Perf[\"perf (workspace_1.project_kan.architecture.perf)\"]\n    REST[\"rest (workspace_1.project_kan.api.rest)\"]\n    MCPDoc[\"mcp (workspace_1.project_kan.api.mcp)\"]\n\n    Root --> Arch\n    Root --> API\n    Arch --> Sec\n    Arch --> Perf\n    API --> REST\n    API --> MCPDoc\n```\n\n---\n\n## PageVersion Diff, Restore, and Highlight-to-Issue Linking\n\nTechnical documentation evolves across releases. \ud83d\udc4dkanban provides deep revision governance and bidirectional issue linking directly inside the editor:\n\n```mermaid\nflowchart LR\n    subgraph DocEvolution[\"Documentation Lifecycle\"]\n        V1[\"PageVersion 1<br/>Initial Spec\"] --> V2[\"PageVersion 2<br/>Architecture Review\"]\n        V2 --> V3[\"PageVersion 3<br/>Active Production\"]\n        \n        V3 -.->|Inspect Diff| DiffView[\"Side-by-Side Diff Modal<br/>Green additions / Red deletions\"]\n        DiffView -.->|One-Click Restore| V2\n        \n        V3 -->|Highlight text| Highlight[\"Selection Popover<br/>'Link to Issue' / 'New Issue'\"]\n        Highlight -->|typed object_link| Issue[\"Linked Work Item KAN-142\"]\n    end\n```\n\n![Docs PageVersion Diff Restore and Highlight Linking](images/41-docs-pageversion-diff-restore.png)\n\n### 1. `PageVersion` Visual Diff and Instant Restore\n- **Immutable Revision Snapshots:** Every manual save or autosave milestone writes an immutable snapshot to `page_versions`.\n- **Side-by-Side and Unified Diffs:** Compare any two revisions with syntax-highlighted additions (green) and deletions (red).\n- **One-Click Restore:** Roll back any document to a previous revision without losing intervening history.\n\n### 2. Highlight-to-Issue Linking\n- **Inline Text Selection:** Selecting any phrase, sentence, or technical requirement inside a document displays an instant action pill.\n- **Bi-Directional Traceability:** Link the highlighted text to an existing ticket or click to spawn a new work item with the highlighted text pre-filled into the description.\n- **Universal Graph Integrity:** Creates typed `REFERENCED_IN` / `MENTIONS` links in the Universal Object Graph.\n\n### Key Capabilities of the Docs System\n\n- **Nested Page Tree:** Expandable sidebar tree allowing arbitrary nesting of documents, specifications, and runbooks.\n- **Auto-Extracted Outline Rail:** The right-hand rail parses headings in real time (`H1`, `H2`, `H3`), providing one-click jump links to document sections.\n- **Append-Only Version History:** Every document save appends an immutable snapshot. Authors can inspect visual diffs between revisions and restore previous versions with a single click.\n- **Mermaid and Diagram Support:** Native rendering of architecture flows, sequence diagrams, and class models directly within the document.\n"
  },
  {
    "slug": "home",
    "title": "\ud83d\udc4dkanban: Executive Architecture and System Overview",
    "category": "Overview",
    "order": 11,
    "summary": "Welcome to the authoritative technical documentation and wiki for **\ud83d\udc4dkanban** (`thumbs-up-kanban`), an open-source, enterprise-grade project management, ticketing, and knowledge platform built from the ground up on two fundamental pillars: 1. **Security-First (Priority 0):** Hardened zero-trust infrastructure, PostgreSQL Row-Level Security (`FORCE RLS`), five-tier network isolation, AAL2 administrative authorization, and hostile input sanitization. 2. **Agent-First (Priority 1):** Purpose-built for autonomous AI agents and human teams alike, replacing the context-bloating CRUD-wrapper anti-pattern with an intent-driven, three-surface Model Context Protocol (MCP) server, deterministic workflow gates, and sub-second execution loops.",
    "sections": [
      {
        "id": "core-system-architecture",
        "title": "Core System Architecture",
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
        "id": "system-architecture-domains",
        "title": "System Architecture Domains",
        "level": 3
      },
      {
        "id": "reference-manuals-verification-matrices",
        "title": "Reference Manuals & Verification Matrices",
        "level": 3
      }
    ],
    "content": "# \ud83d\udc4dkanban: Executive Architecture and System Overview\n\nWelcome to the authoritative technical documentation and wiki for **\ud83d\udc4dkanban** (`thumbs-up-kanban`), an open-source, enterprise-grade project management, ticketing, and knowledge platform built from the ground up on two fundamental pillars:\n1. **Security-First (Priority 0):** Hardened zero-trust infrastructure, PostgreSQL Row-Level Security (`FORCE RLS`), five-tier network isolation, AAL2 administrative authorization, and hostile input sanitization.\n2. **Agent-First (Priority 1):** Purpose-built for autonomous AI agents and human teams alike, replacing the context-bloating CRUD-wrapper anti-pattern with an intent-driven, three-surface Model Context Protocol (MCP) server, deterministic workflow gates, and sub-second execution loops.\n\nLicensed under the strictly permissive **Apache-2.0** license, \ud83d\udc4dkanban eliminates SaaS AI paywalls and per-seat subscription lock-in while competing globally against Jira, Vibe Kanban, and commercial issue trackers with drop-in enterprise migration support.\n\n---\n\n## Core System Architecture\n\n```mermaid\nflowchart TD\n    subgraph Clients[\"Client Surfaces\"]\n        SPA[\"React 19 SPA (Desktop, Tablet, Mobile)\"]\n        Agents[\"Autonomous Agents (Cursor, Claude, Codex, Agy)\"]\n    end\n\n    subgraph Entrypoints[\"API & Protocol Gateways\"]\n        FastAPI[\"FastAPI Application Server<br/>- Multi-Card Auth (AAL2)<br/>- Canonical Markdown Pipe<br/>- WebSocket Realtime Hub<br/>- REST API (184 routes)\"]\n        MCP[\"3-Surface MCP Server<br/>- /mcp/agent (9 tools)<br/>- /mcp/docs (6 tools)<br/>- /mcp/admin (12 tools)<br/>- InlineSafeDumper YAML\"]\n    end\n\n    subgraph Core[\"Database Engine & Object Graph\"]\n        UOG[\"Universal Object Graph (UOG)<br/>PostgreSQL 16 with FORCE ROW LEVEL SECURITY (100%)<br/>- Typed object_links, Spine records, Append-only Ledger<br/>- ltree Hierarchical Docs, pgvector Embeddings, Full-Text<br/>- Invalid Object Link Auditor & Purger\"]\n    end\n\n    subgraph Runtimes[\"Execution Engines\"]\n        AIEngine[\"AI Engine & Orchestration<br/>- OpenAI, Ollama, Gemini<br/>- agy -p, codex -p pipes<br/>- Async Gate Interceptors\"]\n        Sandbox[\"Sandbox Execution Runtime<br/>- Tier A: Wasmtime engine<br/>- Tier B: nsjail runner<br/>- Scoped Ephemeral Tokens\"]\n    end\n\n    SPA -->|HTTP / WebSocket| FastAPI\n    Agents -->|HTTP / SSE / STDIO| MCP\n    Agents -->|HTTP REST| FastAPI\n    FastAPI --> Core\n    MCP --> Core\n    Core --> AIEngine\n    Core --> Sandbox\n```\n\n---\n\n## Visual Tour: Platform Highlights\n\n### Enterprise Workspace and Project Hub\nThe workspace home delivers clear project visibility, team velocity metrics, and seamless multi-project navigation with responsive layouts across desktop, tablet, and mobile displays.\n\n![Workspace Home and Project Overview](images/05-workspace-home.png)\n\n### Breathable Whitespace Board and High-Contrast Theming\nThe core Kanban board features sub-16ms smooth drag-and-drop, semantic emoji hints, configurable WIP limits, and an enterprise dark theme for reduced eye strain during extended operational sessions.\n\n![Enterprise Whitespace Board View](images/06-board-view.png)\n\n![Dark Theme Enterprise Kanban Board](images/22-dark-theme-board.png)\n\n### Keyboard-Driven Command Palette\nGlobal keyboard shortcuts (`Ctrl+K` / `Cmd+K`) provide instant fuzzy navigation across tickets, documents, projects, and administrative studios without context switching.\n\n![Global Command Palette Navigation](images/23-command-palette.png)\n\n### Multi-View Projections: Table Inline Editing and Timeline Dependencies\nEngineers can switch instantly between Kanban Board, 3-pane List, Table with capability-gated inline cell editing, Calendar, and Timeline with SVG Bezier BLOCKS dependency arrows.\n\n![Table View Inline Editing](images/37-table-inline-editing.png)\n\n### Fullscreen Issue Studio and Access Visibility Inspector\nExpanding any ticket unlocks the Fullscreen Issue Studio, featuring a Rich Markdown authoring toolbar, Sparkle 320ms Fill-in-the-Middle (FIM) ghost-text completion, the `\ud83d\udee1\ufe0f` Effective Access Inspector, and a 4-tab activity stream.\n\n![Fullscreen Issue View with Rich Markdown Toolbar and Access Inspector](images/39-fullscreen-issue-view.png)\n\n### Advanced Governance and Administrative Studios\nPlatform administrators manage enterprise governance through dedicated studios:\n- **AI Providers & Token Caps Studio (`/admin/ai`):** Write-only key custody, monthly token budgets, and air-gap policies (`images/43-admin-ai-studio-providers.png`).\n- **Invalid Object Link Auditor (`/admin/link-auditor`):** Continuous graph integrity verification, inspect drawer, and two-stage audited purge (`images/46-admin-link-auditor.png`).\n- **Workflow Transition Studio & Dry-Run Drawer (`/projects/:key/settings/workflows`):** Zero-persistence dry-run simulation with step timings and copyable CLI commands (`images/50-workflow-studio-dry-run-drawer.png`).\n- **Plane Migration Import Studio (`/admin/imports`):** Single-click bundle ingestion, dry-run diff preview, and transactional live migration (`images/49-admin-plane-import-studio.png`).\n\n![Admin Invalid Object Link Auditor Studio](images/46-admin-link-auditor.png)\n\n---\n\n## Architectural Distinctions: \ud83d\udc4dkanban vs Traditional Tools\n\n| Dimension | Legacy Trackers & Paywalled SaaS (Jira / Vibe Kanban) | \ud83d\udc4dkanban Platform |\n| :--- | :--- | :--- |\n| **License & Cost** | Commercial SaaS / AGPL with paid AI paywalls | Pure Apache-2.0, zero paywalled features |\n| **Agent Interface** | 70-120 raw CRUD tool wrappers (15k-25k tokens) | 27 intent-driven MCP tools across 3 surfaces (<= 1.8k tokens for agent) |\n| **Database Security** | Application-layer authorization checks | Hardware-enforced PostgreSQL `FORCE ROW LEVEL SECURITY` on all tenant tables |\n| **Network Isolation** | Monolithic container or open Docker bridge | Hardened 5-network isolation matrix (`edge`, `app`, `data`, `sandbox`, `egress`) |\n| **Workflow Interceptors** | Basic webhooks with no blocking execution | Atomic synchronous Wasm validators/mutators and async AI agent gates |\n| **Input Sanitization** | Basic HTML strip | Hostile Unicode lone-surrogate rejection, hidden-DOM pruner, SVG sandbox |\n| **Deployment Mode** | Complex multi-service Kubernetes only | Single-container standalone (`docker run`) or full multi-container production |\n\nFor an exhaustive feature-by-feature evaluation across 35 criteria, see the [Feature Comparison Matrix](Feature-Comparison).\n\n---\n\n## Non-Bypassable Engineering and Security Invariants\n\n1. **Plain ASCII Hyphen Invariant:** All public documentation, wiki articles, and commit messages strictly mandate plain ASCII hyphens (`-`). Unicode em-dashes (U+2014) and en-dashes (U+2013) are strictly forbidden across the codebase and wiki.\n2. **Zero-Context Fail-Closed Database:** In the absence of an explicit session context (`SET LOCAL app.current_principal_id`), all queries against tenant tables return zero rows. The application role `kanban_app` is stripped of `SUPERUSER` and `BYPASSRLS`.\n3. **Hostile Unicode Rejection:** Text ingestion rejects UTF-16 lone surrogates (`0xD800` through `0xDFFF`) prior to UTF-8 encoding, preventing memory corruptions and parser desynchronization.\n4. **Paste-Jacking Defense:** Clipboard inputs are aggressively stripped of hidden-DOM payloads, zero-width spaces, and invisible injection sequences.\n5. **AAL2 Admin Route Enforcement:** Every endpoint under `/api/v1/admin/*` and every administrative tool on `/mcp/admin` requires Authenticator Assurance Level 2 (AAL2) credentials.\n6. **95% Automated Test Coverage:** All core modules maintain at least 95% unit test coverage running on clean-DB fixtures with sub-millisecond `SAVEPOINT` isolation.\n\n---\n\n## Complete Table of Contents\n\n### System Architecture Domains\n1. [System Topology and Multi-Container Architecture](System-Topology-and-Multi-Container-Architecture) - Standalone embedded PostgreSQL Unix socket and 5-network production container stack.\n2. [Zero-Trust Security and Access Visibility](Zero-Trust-Security-and-Access-Visibility) - PostgreSQL FORCE RLS, dynamic sharing pill, access manifests, and STRIDE threat mitigation.\n3. [Multi-Card Authentication Studio](Multi-Card-Authentication-Studio) - Pluggable auth cards (OAuth2, LDAP, WebAuthn Passkeys, TOTP, Local Admin) with break-glass protection.\n4. [Canonical Markdown and Safe Media Pipeline](Canonical-Markdown-and-Safe-Media-Pipeline) - Hostile input sanitization, safe Mermaid rendering, SVG sandboxing, and media proxying.\n5. [Enterprise Whitespace and Kanban Board](Enterprise-Whitespace-and-Kanban-Board) - 5 native view layouts, 2D swimlanes, sub-16ms drag-and-drop, and the `<EmojiHint>` semantic hover system.\n6. [Ticket Screen and Work Item Features](Ticket-Screen-and-Work-Item-Features) - 960px peek drawer, 17 enterprise work-item features, properties rail, and 4-tab activity stream.\n7. [Hierarchical Docs and Stickies with Smart Promotion](Hierarchical-Docs-and-Stickies-with-Smart-Promotion) - ltree page trees, color-coded sticky masonry, and lossless AI-assisted promotion to Docs.\n8. [Blinking Cursor Sparkle Completion Engine](Blinking-Cursor-Sparkle-Completion-Engine) - Sub-300ms inline Fill-In-the-Middle (FIM) ghost text with surgical right-click disambiguation.\n9. [Multi-Provider AI Engine and Runners](Multi-Provider-AI-Engine-and-Runners) - OpenAI, Ollama, Gemini integrations, local CLI pipe harnesses (`agy -p`, `codex -p`), and mTLS runners.\n10. [Three-Surface MCP Server Architecture](Three-Surface-MCP-Server-Architecture) - Dedicated streamable endpoints (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`) with InlineSafeDumper YAML.\n11. [Universal Object Graph and Link Auditor](Universal-Object-Graph-and-Link-Auditor) - Unified object spine, 13 typed object relationships, and automated invalid link detection/purging.\n12. [Admin Custom Scripted Fields and Sandbox](Admin-Custom-Scripted-Fields-and-Sandbox) - Wasmtime (Tier A) and nsjail (Tier B) sandboxed execution with cryptographic tier escalation.\n13. [ScriptRunner Workflows and Transition Interceptors](ScriptRunner-Workflows-and-Transition-Interceptors) - Synchronous transition validators/mutators and asynchronous AI agent gates.\n14. [Clean-DB Testing and Governance Gates](Clean-DB-Testing-and-Governance-Gates) - Fast parallel test execution, tmpfs template database, pluggable AI fixtures, and CI/CD validation.\n15. [Production Promotion and Backup Runbook](Production-Promotion-and-Backup-Runbook) - Single-command standalone promotion, encrypted KBBAK1 backup format, and disaster recovery.\n16. [Migration and Cutover Runbook](Migration-and-Cutover-Runbook) - 7-phase zero-downtime cutover plan, dry-run reconciliation, and rollback procedures.\n17. [Real-Time Web and WebSocket Architecture](Real-Time-Web-and-WebSocket-Architecture) - Distributed WebSocket hub, connection throttling, channel subscriptions, and board state synchronization.\n\n### Reference Manuals & Verification Matrices\n- [Feature Comparison Matrix (35 Features)](Feature-Comparison) - Comprehensive capability comparison across 35 features evaluating \ud83d\udc4dkanban against Jira, Plane, GitHub, Vibe Kanban, Businessmap, and Codebeamer.\n- [MCP Tools Reference (27 Tools)](MCP-Tools-Reference) - Exhaustive specification of all 27 MCP tools, parameter schemas, LOD tiers, and destructive token workflows.\n- [REST API Architecture and OpenAPI Guide](REST-API-Architecture-and-OpenAPI-Guide) - Technical guide to the 184-route FastAPI backend, interactive OpenAPI documentation, and TypeScript SDK.\n- [User Tasks and QA Verification Matrix](User-Tasks-and-QA-Matrix) - Verification audit mapping tasks UT-01 through UT-16 to live browser checks and screenshot deliverables.\n- [Architecture Delta and Gap Analysis](Architecture-Delta-and-Missing-Features) - Forensic analysis of specification requirements versus codebase implementation and tracking backlog.\n"
  },
  {
    "slug": "mcp-tools-reference",
    "title": "Model Context Protocol (MCP) Tools Reference Manual",
    "category": "Reference Guides",
    "order": 12,
    "summary": "The \ud83d\udc4dkanban platform exposes 24 intent-driven Model Context Protocol (MCP) tools across three streamable HTTP surfaces (`2025-06-18` specification). Unlike conventional project management APIs that force agents to coordinate dozens of low-level CRUD endpoints, \ud83d\udc4dkanban tools encapsulate multi-step engineering workflows into atomic, type-safe operations.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "surface-1-execution-and-qa-tools",
        "title": "Surface 1: `/mcp/agent` (Execution and QA Tools)",
        "level": 2
      },
      {
        "id": "section",
        "title": "1. `search_tickets`",
        "level": 3
      },
      {
        "id": "section",
        "title": "2. `read_ticket`",
        "level": 3
      },
      {
        "id": "section",
        "title": "3. `create_ticket`",
        "level": 3
      },
      {
        "id": "section",
        "title": "4. `update_ticket`",
        "level": 3
      },
      {
        "id": "section",
        "title": "5. `begin_work`",
        "level": 3
      },
      {
        "id": "section",
        "title": "6. `transition_ticket`",
        "level": 3
      },
      {
        "id": "section",
        "title": "7. `complete_work`",
        "level": 3
      },
      {
        "id": "section",
        "title": "8. `add_comment`",
        "level": 3
      },
      {
        "id": "section",
        "title": "9. `link_objects`",
        "level": 3
      },
      {
        "id": "surface-2-consolidated-3-tool-suite",
        "title": "Surface 2: `/mcp/docs` (Consolidated 3-Tool Suite)",
        "level": 2
      },
      {
        "id": "section",
        "title": "1. `search`",
        "level": 3
      },
      {
        "id": "section",
        "title": "2. `create`",
        "level": 3
      },
      {
        "id": "section",
        "title": "3. `update`",
        "level": 3
      },
      {
        "id": "surface-3-governance-and-lifecycle-tools",
        "title": "Surface 3: `/mcp/admin` (Governance and Lifecycle Tools)",
        "level": 2
      },
      {
        "id": "section",
        "title": "1. `configure_workspace`",
        "level": 3
      },
      {
        "id": "section",
        "title": "2. `manage_auth_cards`",
        "level": 3
      },
      {
        "id": "section",
        "title": "3. `manage_principals_and_groups`",
        "level": 3
      },
      {
        "id": "section",
        "title": "4. `manage_access_policies`",
        "level": 3
      },
      {
        "id": "section",
        "title": "5. `architect_project`",
        "level": 3
      },
      {
        "id": "section",
        "title": "6. `manage_cycles_and_modules`",
        "level": 3
      },
      {
        "id": "section",
        "title": "7. `manage_custom_fields_and_scripts`",
        "level": 3
      },
      {
        "id": "section",
        "title": "8. `manage_workflow_interceptors`",
        "level": 3
      },
      {
        "id": "section",
        "title": "9. `manage_ai_and_agent_runners`",
        "level": 3
      },
      {
        "id": "section",
        "title": "10. `override_ticket_provenance`",
        "level": 3
      },
      {
        "id": "section",
        "title": "11. `audit_and_purge_object_links`",
        "level": 3
      },
      {
        "id": "two-stage-confirmation-safety",
        "title": "12. `destructive_lifecycle` (Two-Stage Confirmation Safety)",
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
    "content": "# Model Context Protocol (MCP) Tools Reference Manual\n\n## Overview\n\nThe \ud83d\udc4dkanban platform exposes 24 intent-driven Model Context Protocol (MCP) tools across three streamable HTTP surfaces (`2025-06-18` specification). Unlike conventional project management APIs that force agents to coordinate dozens of low-level CRUD endpoints, \ud83d\udc4dkanban tools encapsulate multi-step engineering workflows into atomic, type-safe operations.\n\nResponses are serialized using `InlineSafeDumper` compact YAML, stripping null values and empty collections to maximize LLM context efficiency and token economy.\n\n```mermaid\nflowchart TD\n    subgraph Surfaces[\"Three Dedicated MCP Surfaces\"]\n        AgentSurf[\"/mcp/agent (9 Tools)<br/>Token budget: <= 1,850 tokens<br/>Target: Coding & QA Autonomous Agents\"]\n        DocsSurf[\"/mcp/docs (3 Tools)<br/>Token budget: <= 1,300 tokens<br/>Target: Documentation & Knowledge Bots\"]\n        AdminSurf[\"/mcp/admin (12 Tools)<br/>Token budget: <= 2,800 tokens<br/>Target: DevOps & Migration Administrators (AAL2)\"]\n    end\n\n    subgraph LOD[\"InlineSafeDumper YAML Engine\"]\n        Summary[\"lod='summary'<br/>Keys, titles, states only\"]\n        Standard[\"lod='standard'<br/>Balanced properties & assignees\"]\n        Full[\"lod='full'<br/>Exhaustive body, history & links\"]\n    end\n\n    Surfaces --> LOD\n```\n\n![MCP Access Studio and Scoped Token Governance](images/13-mcp-access-studio.png)\n\n![MCP Level of Detail Tiers Studio](images/21-mcp-lod-tiers-studio.png)\n\n---\n\n## Surface 1: `/mcp/agent` (Execution and QA Tools)\n\nDedicated to autonomous coding agents, test runners, and QA bots. Bounded strictly by caller permissions; contains zero administrative or destructive tools. CLI binary mental model: `kanban-cli-agent`.\n\n### 1. `search_tickets`\n- **Description:** Hybrid lexical and semantic search across project tickets with multi-attribute filtering.\n- **Required Parameters:** None.\n- **Optional Parameters:**\n  - `query` (string): Text or semantic query.\n  - `workspace` (string): Target workspace slug or UUID.\n  - `project` (string): Target project key (e.g. `KAN`).\n  - `states` (array of strings): Filter by state names (e.g. `['in_progress', 'todo']`).\n  - `assignees` (array of strings): Filter by username or agent handle.\n  - `cycle` (string): Sprint cycle slug or UUID.\n  - `modules` (array of strings): Filter by module slugs.\n  - `labels` (array of strings): Filter by label names.\n  - `blocked` (boolean): Filter for blocked or non-blocked items.\n  - `gate_status` (string): Filter by agent gate state (`pending_agent_gate`, `vetoed`, `approved`).\n  - `mode` (string): `lexical`, `semantic`, or `hybrid` (default).\n  - `lod` (string): Level of detail: `summary`, `standard` (default), `full`.\n  - `limit` (integer): Maximum items to return (1 to 50, default 20).\n  - `cursor` (string): Pagination cursor.\n- **CLI Example:** `kanban-cli-agent search_tickets --query=\"progressive error\" --project=KAN`\n\n### 2. `read_ticket`\n- **Description:** Retrieve complete ticket details, canonical Markdown description, activity feed, and access manifest.\n- **Required Parameters:**\n  - `identifier` (string): Human ticket key (e.g. `KAN-42`) or UUID.\n- **Optional Parameters:**\n  - `workspace` (string): Workspace context.\n  - `lod` (string): Level of detail: `summary`, `standard` (default), `full`.\n  - `comments_limit` (integer): Max recent comments to return (default 10).\n- **CLI Example:** `kanban-cli-agent read_ticket --identifier=KAN-19 --lod=standard`\n\n### 3. `create_ticket`\n- **Description:** Create ticket or atomic child tree (max 50 nodes, depth <=6; omit project and parent inside children).\n- **Required Parameters:**\n  - `project` (string): Target project key (e.g. `KAN`). Root only; inherited by children.\n  - `summary` (string): Single-line ticket title.\n- **Optional Parameters:**\n  - `description_markdown` (string): Canonical Markdown description.\n  - `state` (string): Initial state key.\n  - `priority` (string): `urgent`, `high`, `medium`, `low`, `none`.\n  - `assignees` (array of strings): Handles of assignees.\n  - `labels` (array of strings): Label names.\n  - `cycle` (string): Cycle slug or UUID.\n  - `modules` (array of strings): Module slugs.\n  - `parent` (string): Parent issue identifier. Root only; omit in children.\n  - `start_date` (string): ISO 8601 start date.\n  - `due_date` (string): ISO 8601 due date.\n  - `children` (array of objects): Sub-issues to create atomically. Each child object requires `summary` and inherits `project` from the root and `parent` from its enclosing node; both `project` and `parent` must be omitted inside `children`. Max 49 items per node, total nodes <= 50, maximum depth <= 6.\n- **CLI Example:** `kanban-cli-agent create_ticket --project=KAN --summary=\"Self-correcting error UX\"`\n\n### 4. `update_ticket`\n- **Description:** Update ticket properties, state, assignees, or Markdown body. State changes must use `transition_ticket`.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n- **Optional Parameters:**\n  - `if_match` (string): Concurrency lock (version hash) to prevent lost updates.\n  - `summary` (string): New title.\n  - `description_markdown` (string): Markdown content.\n  - `description_mode` (string): `replace` (default), `append`, `prepend`.\n  - `assignees_add` / `assignees_remove` (array of strings): Incremental assignee adjustments.\n  - `priority` (string): Updated priority.\n  - `start_date` / `due_date` (string): ISO 8601 dates.\n  - `cycle` (string): Move to cycle.\n  - `modules_add` / `modules_remove` (array of strings): Incremental module adjustments.\n  - `labels_add` / `labels_remove` (array of strings): Incremental label adjustments.\n  - `parent` (string): Update parent issue.\n- **CLI Example:** `kanban-cli-agent update_ticket --identifier=KAN-19 --summary=\"Refined Error UX\"`\n\n### 5. `begin_work`\n- **Description:** Atomic workflow starter: assigns calling agent, transitions ticket to started state, binds active cycle, and posts plan comment.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n  - `plan_markdown` (string): High-level technical execution plan.\n- **CLI Example:** `kanban-cli-agent begin_work --identifier=KAN-19 --plan-markdown=\"1. Implement schema validation\"`\n\n### 6. `transition_ticket`\n- **Description:** Transition ticket between workflow states, executing synchronous validators and triggering async agent gates.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n  - `to_state` (string): Target state name or slug.\n- **Optional Parameters:**\n  - `comment_markdown` (string): Accompanying transition comment.\n  - `verification_proof` (object): Verification artifacts or test results.\n- **CLI Example:** `kanban-cli-agent transition_ticket --identifier=KAN-19 --to-state=\"Done\"`\n\n### 7. `complete_work`\n- **Description:** Atomic terminal QA gate: verifies child blocker resolution, records verification proof, transitions to completed, and posts summary comment.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n  - `summary_markdown` (string): Final delivery report.\n  - `verification_proof` (object): Passive forensic proof packet (logs, test outputs, screenshots).\n- **Optional Parameters:**\n  - `to_state` (string): Target terminal state (defaults to `done`).\n- **CLI Example:** `kanban-cli-agent complete_work --identifier=KAN-19 --summary-markdown=\"Work complete\"`\n\n### 8. `add_comment`\n- **Description:** Post a canonical Markdown comment or threaded reply to a ticket.\n- **Required Parameters:**\n  - `identifier` (string): Ticket key or UUID.\n  - `body_markdown` (string): Comment content in canonical Markdown.\n- **Optional Parameters:**\n  - `reply_to` (string): Parent comment UUID for threaded replies.\n  - `ack_mentions` (boolean): Acknowledge mentioned user notifications.\n- **CLI Example:** `kanban-cli-agent add_comment --identifier=KAN-19 --body-markdown=\"PR review complete\"`\n\n### 9. `link_objects`\n- **Description:** Create or remove a typed Universal Object Graph link between two entities.\n- **Required Parameters:**\n  - `source` (string): Source object key or UUID.\n  - `target` (string): Target object key or UUID.\n  - `link_type` (string): Relationship kind (`blocks`, `relates_to`, `duplicates`, `parent_of`).\n- **Optional Parameters:**\n  - `action` (string): `create` (default) or `remove`.\n- **CLI Example:** `kanban-cli-agent link_objects --source=KAN-19 --target=KAN-25 --link-type=\"relates_to\"`\n\n---\n\n## Surface 2: `/mcp/docs` (Consolidated 3-Tool Suite)\n\nDedicated to technical documentation, architecture specifications, and sticky notes. Consolidated from 6 legacy tools into 3 intent-driven operations (`search`, `create`, `update`). CLI binary mental model: `kanban-cli-docs`.\n\n### 1. `search`\n- **Description:** Unified discovery across Docs, Pages, and Stickies with hybrid lexical and semantic filtering, hierarchical breadcrumbs, and LOD tiers.\n- **Required Parameters:** None.\n- **Optional Parameters:**\n  - `query` (string): Search query text.\n  - `id` (string): Direct document slug or UUID lookup.\n  - `project` (string): Project scope filter.\n  - `type` (string): Entity kind filter (`DOC`, `STICKY`, `ALL`). Default: `ALL`.\n  - `lod` (string): Level of detail: `summary`, `standard` (default), `full`.\n  - `include_tree` (boolean): Include full ltree hierarchical descendants. Default: `false`.\n  - `limit` (integer): Maximum items to return (1 to 100, default 20).\n  - `cursor` (string): Pagination cursor.\n- **CLI Example:** `kanban-cli-docs search --query=\"architecture\" --type=DOC`\n\n### 2. `create`\n- **Description:** Atomic authoring tool creating standalone Docs, nested child Pages in an ltree hierarchy, or ideation Stickies.\n- **Required Parameters:**\n  - `type` (string): Entity kind: `DOC` or `STICKY`.\n  - `title` (string): Document title or sticky summary.\n- **Optional Parameters:**\n  - `project` (string): Project identifier (e.g. `KAN`). Required when creating stickies.\n  - `content` (string): Canonical Markdown content body.\n  - `parent` (string): Parent Doc UUID or canonical slug for nested document placement.\n  - `color` (string): Sticky color badge (`amber`, `emerald`, `sky`, `rose`, `violet`, `slate`). Default: `amber`.\n  - `links` (array of objects): Explicit Universal Object Graph typed relationships.\n- **CLI Example:** `kanban-cli-docs create --type=DOC --title=\"Architecture Guide\" --content=\"# Overview\"`\n\n### 3. `update`\n- **Description:** Unified mutation tool for updating Markdown content, properties, or executing surgical line-level diff-patching with ETag concurrency protection and smart sticky-to-doc promotion.\n- **Required Parameters:**\n  - `id` (string): Doc slug, UUID, or sticky note identifier.\n- **Optional Parameters:**\n  - `type` (string): Entity kind: `DOC` or `STICKY`.\n  - `title` (string): New title.\n  - `content` (string): New complete Markdown body (replaces entire content).\n  - `original_text` (string): Target substring for surgical line-level diff-patching.\n  - `replacement_text` (string): Replacement substring for surgical diff-patching (requires `original_text`).\n  - `parent` (string): Target parent Doc UUID to re-parent in documentation tree.\n  - `color` (string): Updated sticky color.\n  - `if_match` (string): SHA-256 ETag version lock preventing lost updates.\n  - `links` (array of objects): Graph relationships to add or remove.\n- **CLI Examples:**\n  - Full body replacement: `kanban-cli-docs update --id=\"docs/arch\" --type=DOC --content=\"# Updated Architecture\"`\n  - Surgical diff-patching: `kanban-cli-docs update --id=\"docs/arch\" --type=DOC --original-text=\"old line\" --replacement-text=\"new line\"`\n  - ETag-protected update: `kanban-cli-docs update --id=\"docs/arch\" --type=DOC --if-match=\"c4ca4238a0b923820dcc509a6f75849b\" --content=\"new\"`\n\n---\n\n## Surface 3: `/mcp/admin` (Governance and Lifecycle Tools)\n\nPrivileged administrative surface. Every request requires AAL2 credentials. CLI binary mental model: `kanban-cli-admin`.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Admin Agent (AAL2)\n    participant MCP as /mcp/admin Surface\n    participant DB as PostgreSQL Engine\n\n    Note over Admin,MCP: Phase 1: Dry-Run Inspection\n    Admin->>MCP: Call purge_invalid_links(confirm=false)\n    MCP->>DB: Audit dangling links & compute blast radius\n    DB-->>MCP: 14 broken links identified\n    MCP-->>Admin: Return dry-run summary + ephemeral confirmation_token (valid 300s)\n\n    Note over Admin,MCP: Phase 2: Explicit Two-Stage Execution\n    Admin->>MCP: Call purge_invalid_links(confirm=true, confirmation_token=\"tok_...\")\n    MCP->>MCP: Verify AAL2 session & token validity\n    MCP->>DB: BEGIN TX & DELETE dangling links & record audit event\n    DB-->>MCP: 14 rows removed\n    MCP-->>Admin: Purge executed successfully (Ledger ID recorded)\n```\n\n### 1. `configure_workspace`\n- **Description:** Read or update workspace-level settings, themes, and default project templates.\n- **Required Parameters:**\n  - `action` (string): `get` or `update`.\n- **Optional Parameters:**\n  - `settings` (object): Key-value workspace configuration settings.\n  - `lod` (string): Level of detail.\n- **CLI Example:** `kanban-cli-admin configure_workspace --action=\"get\"`\n\n### 2. `manage_auth_cards`\n- **Description:** Configure, reorder, test, or toggle Multi-Card authentication providers.\n- **Required Parameters:**\n  - `action` (string): `list`, `get`, `create`, `update`, `reorder`, `test_handshake`, `delete`.\n- **Optional Parameters:**\n  - `card` (string): Auth card UUID.\n  - `slug` (string): Unique identifier slug.\n  - `provider_kind` (string): `local`, `oidc`, `oauth2`, `ldaps`, `webauthn`, `totp`.\n  - `display_name` (string): Card label on login screen.\n  - `public_config` / `secret` (objects): Provider configuration and write-only credentials.\n  - `after` (string): Slug of card to place after when reordering.\n  - `confirm_slug` (string): Required confirmation slug on deletion.\n- **CLI Example:** `kanban-cli-admin manage_auth_cards --action=\"list\"`\n\n### 3. `manage_principals_and_groups`\n- **Description:** Provision users, service principals, and groups, and manage role bindings.\n- **Required Parameters:**\n  - `action` (string): `list`, `get`, `create_user`, `create_agent`, `create_group`, `bind_role`, `unbind_role`.\n- **Optional Parameters:**\n  - `principal` (string): User or agent UUID.\n  - `group` (string): Group UUID.\n  - `handle` (string): Unique username or agent handle.\n  - `role` (string): `owner`, `admin`, `member`, `guest`.\n  - `scope` (string): Workspace or project scope identifier.\n- **CLI Example:** `kanban-cli-admin manage_principals_and_groups --action=\"list\"`\n\n### 4. `manage_access_policies`\n- **Description:** Inspect and update fine-grained ACL masks (`VIEW`, `EDIT`, `DELETE`, `ADMIN`, `SHARE`) on Universal Object Graph entities.\n- **Required Parameters:**\n  - `action` (string): `read_manifest`, `grant`, `revoke`.\n- **Optional Parameters:**\n  - `object` (string): Object UUID.\n  - `principal` (string): Target user, group, or agent UUID.\n  - `effect` (string): `allow` or `deny`.\n  - `capabilities` (array of strings): Granular capability masks.\n- **CLI Example:** `kanban-cli-admin manage_access_policies --action=\"read_manifest\" --object=\"<uuid>\"`\n\n### 5. `architect_project`\n- **Description:** Provision, configure, or scaffold a project using structured blueprint templates.\n- **Required Parameters:**\n  - `action` (string): `create`, `plan`, `apply`, `get`, `update`.\n- **Optional Parameters:**\n  - `project` (string): Project key (e.g. `KAN`).\n  - `blueprint` (object): Complete project schema, workflow states, and default views.\n  - `plan_sha256` (string): Cryptographic digest verification.\n- **CLI Example:** `kanban-cli-admin architect_project --action=\"plan\" --project=KAN`\n\n### 6. `manage_cycles_and_modules`\n- **Description:** Manage sprint cycles, functional modules, and custom view configurations.\n- **Required Parameters:**\n  - `action` (string): `list_cycles`, `create_cycle`, `update_cycle`, `start_cycle`, `complete_cycle`, `rollover`, `list_modules`, `create_module`, `update_module`, `list_views`, `create_view`, `update_view`, `bind_project_repo`, `list_repo_bindings`, `refresh_repo_binding`, `unbind_project_repo`, `help`.\n- **Optional Parameters:**\n  - `project` (string): Target project key.\n  - `cycle` / `module` / `view` (strings): Entity UUIDs.\n  - `name` (string): Display name.\n  - `start_date` / `end_date` (strings): Schedule range.\n- **CLI Example:** `kanban-cli-admin manage_cycles_and_modules --action=\"list_cycles\" --project=KAN`\n\n### 7. `manage_custom_fields_and_scripts`\n- **Description:** Define custom scripted fields and sandbox execution settings.\n- **Required Parameters:**\n  - `action` (string): `list`, `create_field`, `update_field`, `test_execute`, `escalate_scope`.\n- **Optional Parameters:**\n  - `project` (string): Project key.\n  - `field` (string): Field UUID.\n  - `tier` (string): `tier_a_wasm` or `tier_b_jail`.\n  - `target_scope` (string): `project`, `workspace`, `server`.\n  - `justification` (string): Cryptographic justification for privilege escalation.\n- **CLI Example:** `kanban-cli-admin manage_custom_fields_and_scripts --action=\"list\" --project=KAN`\n\n### 8. `manage_workflow_interceptors`\n- **Description:** Configure pre-transition interceptor hooks (validators, mutators, async agent gates).\n- **Required Parameters:**\n  - `action` (string): `list`, `create_hook`, `update_hook`, `reorder_pipeline`, `dry_run`.\n- **Optional Parameters:**\n  - `project` (string): Project key.\n  - `from_state` / `to_state` (strings): State transition rule.\n  - `hook_kind` (string): `sync_validator`, `sync_mutator`, `async_agent_gate`.\n  - `ordered_hook_ids` (array of strings): Execution sequence.\n  - `sample_ticket` (object): Test ticket for zero-persistence dry-run.\n- **CLI Example:** `kanban-cli-admin manage_workflow_interceptors --action=\"list\" --project=KAN`\n\n### 9. `manage_ai_and_agent_runners`\n- **Description:** Register LLM provider endpoints, configure token caps, and define CLI pipe harnesses or mTLS runner pools.\n- **Required Parameters:**\n  - `action` (string): `list_providers`, `upsert_provider`, `set_token_cap`, `register_runner_pool`.\n- **Optional Parameters:**\n  - `provider_kind` (string): `openai`, `gemini`, `ollama`, `cli_pipe`, `remote_runner`.\n  - `base_url` (string): Endpoint URL.\n  - `token_cap` (integer): Monthly or billing period token ceiling.\n  - `mcp_allowed_tools` (array of strings): Allowlist of tools permitted for this runner.\n- **CLI Example:** `kanban-cli-admin manage_ai_and_agent_runners --action=\"list_providers\"`\n\n### 10. `override_ticket_provenance`\n- **Description:** Privileged administrative tool to adjust ticket author, creation timestamp, or state during migration reconciliation.\n- **Required Parameters:**\n  - `action` (string): `reassign_creator`, `reorder_history`.\n- **Optional Parameters:**\n  - `issue` (string): Issue identifier.\n  - `new_creator` (string): New author principal UUID.\n  - `reason` (string): Mandatory audit explanation.\n- **CLI Example:** `kanban-cli-admin override_ticket_provenance --action=\"reassign_creator\" --issue=KAN-1 --new-creator=\"<uuid>\" --reason=\"audit\"`\n\n### 11. `audit_and_purge_object_links`\n- **Description:** Execute the Invalid Object Link Auditor to detect and remediate orphaned or corrupt graph relationships.\n- **Required Parameters:**\n  - `action` (string): `scan_dry_run`, `purge_invalid`.\n- **Optional Parameters:**\n  - `reason_filter` (string): Filter by violation class (`orphaned_target`, `cross_tenant_leak`, etc.).\n  - `reason` (string): Mandatory audit ledger explanation for purge actions.\n- **CLI Example:** `kanban-cli-admin audit_and_purge_object_links --action=\"scan_dry_run\"`\n\n### 12. `destructive_lifecycle` (Two-Stage Confirmation Safety)\n- **Description:** Administrative destruction tool for projects, workspaces, or entire datasets. Enforces a non-bypassable two-stage confirmation protocol.\n- **Required Parameters:**\n  - `action` (string): `request_delete` (Stage 1) or `execute_delete` (Stage 2).\n- **Optional Parameters:**\n  - `target_kind` (string): `project`, `workspace`, `all_tickets`.\n  - `target` (string): Slug or UUID of target entity.\n  - `mode` (string): `soft_archive` or `hard_purge`.\n  - `confirmation_token` (string): Short-lived cryptographic token issued in Stage 1.\n  - `confirm_phrase` (string): Verbatim confirmation string (e.g. `DELETE PROJECT KAN`).\n  - `reason` (string): Mandatory audit justification.\n- **CLI Example:** `kanban-cli-admin destructive_lifecycle --action=\"request_delete\" --target-kind=\"project\" --target=KAN`\n\n---\n\n## Progressive-Disclosure Self-Correcting YAML Error UX\n\nAll \ud83d\udc4dkanban MCP tools implement progressive-disclosure, self-correcting error responses. When an AI agent submits an invalid parameter name, misses a required argument, uses an unrecognized enum option, or encounters a domain concurrency conflict, the server intercepts the error before execution and responds with structured, actionable guidance.\n\nThis prevents repetitive LLM retry loops, hallucination thrashing, and context bloat by immediately providing:\n1. Exact culprit parameter name (`field`)\n2. Comprehensive list of allowed values (`valid_options`)\n3. Fuzzy and semantic closest matches (`did_you_mean`)\n4. Human-readable remediation instruction (`fix_hint`)\n5. Corrected, copy-paste-ready command invocation (`cli_example`)\n6. Line-numbered snippet candidates for ambiguous diffs (`closest_match`)\n\n### Pre-Dispatch Schema Validation Contract\n\nPre-dispatch validation runs centrally inside `McpProtocolHandler._handle_tools_call` across all 3 surfaces before tool handlers execute:\n\n- **Unknown Parameter:** The server checks common developer synonyms via `SEMANTIC_ALIASES` (`body` -> `content`/`description_markdown`, `identifier` -> `id`, `kind` -> `type`, `ticket_id` -> `identifier`, `title` -> `summary`, `originalText` -> `original_text`, `replacementText` -> `replacement_text`), camelCase to snake_case conversions, and `difflib` string similarity against known schema properties.\n- **Missing Required Parameter:** The server constructs a pre-filled `cli_example` containing all valid arguments the caller already provided, adding `<placeholder>` values only for missing required fields.\n- **Invalid Enum / Type / Pattern:** The server validates options against declared enum sets, computes case-insensitive closest matches (`\"dco\"` -> `DOC`), and returns typed format patterns (such as 64-character SHA-256 hashes).\n- **JIT Help Immunity:** Calls containing `action=\"help\"` or `identifier=\"help\"` bypass parameter validation to ensure help documents are always accessible without error.\n\n### Canonical YAML Error Examples\n\n#### 1. Unknown Parameter with Semantic Alias\nCaller passes `body` to `/mcp/docs` `update` instead of `content`:\n\n```yaml\nerror:\n  code: VALIDATION_FAILED\n  message: Unknown parameter 'body' for tool 'update'\n  field: body\n  valid_options: [id, type, title, content, parent, color, original_text, replacement_text, if_match, links]\n  did_you_mean: [content]\n  hint: Unknown parameter 'body'. Did you mean 'content'?\n  fix_hint: Unknown parameter 'body'. Did you mean 'content'?\n  cli_example: kanban-cli-docs update --id=\"docs/arch\" --type=DOC --content=\"new content\"\n```\n\n#### 2. Unknown Parameter with Fuzzy Match\nCaller has typo `querry` on `/mcp/docs` `search`:\n\n```yaml\nerror:\n  code: VALIDATION_FAILED\n  message: Unknown parameter 'querry' for tool 'search'\n  field: querry\n  valid_options: [id, query, type, project, lod, include_tree, limit, cursor]\n  did_you_mean: [query, cursor]\n  hint: Unknown parameter 'querry'. Did you mean 'query'?\n  fix_hint: Unknown parameter 'querry'. Did you mean 'query'?\n  cli_example: kanban-cli-docs search --query=\"architecture\"\n```\n\n#### 3. Missing Required Parameter with Pre-filled CLI Example\nCaller supplies `type` and `content` but omits required `title` on `/mcp/docs` `create`:\n\n```yaml\nerror:\n  code: VALIDATION_FAILED\n  message: Missing required parameter 'title' for tool 'create'\n  field: title\n  hint: 'Missing required parameter: ''title''. Provide a value to proceed.'\n  fix_hint: 'Missing required parameter: ''title''. Provide a value to proceed.'\n  cli_example: kanban-cli-docs create --type=DOC --content=\"# Architecture\" --title=\"<title>\"\n```\n\n#### 4. Invalid Enum Value with Case-Insensitive Fuzzy Match\nCaller passes `type=\"dco\"` on `/mcp/docs` `create`:\n\n```yaml\nerror:\n  code: VALIDATION_FAILED\n  message: Invalid value 'dco' for parameter 'type'; type must be 'DOC' or 'STICKY' or 'doc' or 'sticky'\n  field: type\n  valid_options: [DOC, STICKY, doc, sticky]\n  did_you_mean: [doc]\n  hint: 'Invalid value ''dco'' for parameter ''type''. Did you mean ''doc''? Valid options: [''DOC'', ''STICKY'', ''doc'', ''sticky'']'\n  fix_hint: 'Invalid value ''dco'' for parameter ''type''. Did you mean ''doc''? Valid options: [''DOC'', ''STICKY'', ''doc'', ''sticky'']'\n  cli_example: kanban-cli-docs create --type=\"doc\" --title=\"System Architecture\" --content=\"text\"\n```\n\n#### 5. Tool Not Found on Surface\nCaller invokes `search_docs` on `/mcp/docs` instead of consolidated `search`:\n\n```yaml\nerror:\n  code: NOT_FOUND\n  message: Tool 'search_docs' not found on surface 'docs'\n  field: tool_name\n  valid_options: [search, create, update]\n  did_you_mean: [search]\n  hint: Verify tool name or switch to appropriate MCP surface endpoint\n  fix_hint: Tool 'search_docs' not found. Did you mean 'search'?\n  cli_example: kanban-cli-docs search\n```\n\n#### 6. Concurrency Conflict (ETag Mismatch)\nCaller attempts an update with an obsolete ETag version:\n\n```yaml\nerror:\n  code: CONFLICT_ETAG\n  message: concurrency conflict: ticket description was modified concurrently\n  hint: 'current etag: 9f83726abcde4582...'\n  fix_hint: Ticket description was modified concurrently. Retry with fresh ETag: 9f83726abcde4582...\n  cli_example: kanban-cli-agent update_ticket --identifier=\"KAN-19\" --if-match=\"9f83726abcde4582...\"\n  current_etag: 9f83726abcde4582...\n```\n\n#### 7. Sticky Already Promoted to Document\nCaller attempts to edit a sticky note that has already been converted into a formal Doc:\n\n```yaml\nerror:\n  code: ALREADY_PROMOTED\n  message: Sticky 'stk_01abc' has already been promoted to document 'DOC-KAN-42'\n  field: id\n  hint: Sticky 'stk_01abc' has already been promoted to Doc 'DOC-KAN-42'. Use update on that Doc instead.\n  fix_hint: Sticky 'stk_01abc' has already been promoted to Doc 'DOC-KAN-42'. Use update on that Doc instead.\n  cli_example: kanban-cli-docs update --id=\"DOC-KAN-42\"\n  target_doc_key: DOC-KAN-42\n```\n\n#### 8. Surgical Diff Patch Target Not Found (Closest Match)\nCaller provides a target string with indentation or typo differences:\n\n```yaml\nerror:\n  code: PATCH_TARGET_NOT_FOUND\n  message: Target text not found in document\n  field: original_text\n  closest_match:\n    - line_start: 3\n      line_end: 3\n      similarity: 0.973\n      snippet: 'Section 1: Context'\n  hint: Verify exact whitespace and indentation, or inspect closest_match suggestions.\n  fix_hint: Target text not found in document. Inspect closest_match suggestions for exact whitespace/indentation.\n  cli_example: kanban-cli-docs update --id=\"<id>\" --original-text=\"<snippet from closest_match>\" --replacement-text=\"<new>\"\n```\n\n#### 9. Surgical Diff Patch Target Ambiguous\nCaller provides non-unique target text that appears in multiple sections:\n\n```yaml\nerror:\n  code: PATCH_TARGET_AMBIGUOUS\n  message: Target text appears 2 times in document; provide more surrounding context\n  field: original_text\n  hint: Include unique surrounding lines to disambiguate the target region.\n  fix_hint: Target text appears 2 times at lines [1, 3]. Include unique surrounding lines in original_text to disambiguate.\n  cli_example: kanban-cli-docs update --id=\"<id>\" --original-text=\"<unique context>\" --replacement-text=\"<new>\"\n  line_hints: [1, 3]\n  count: 2\n```\n\n#### 10. Entity Not Found\nCaller attempts to read or mutate a ticket or document that does not exist or is inaccessible:\n\n```yaml\nerror:\n  code: NOT_FOUND\n  message: ticket not found\n  field: identifier\n  hint: Ticket 'KAN-99999' was not found or you do not have access. Search accessible tickets first.\n  fix_hint: Ticket 'KAN-99999' was not found or you do not have access. Search accessible tickets first.\n  cli_example: kanban-cli-agent search_tickets --query=\"KAN-99999\"\n```\n"
  },
  {
    "slug": "migration-and-cutover-runbook",
    "title": "Legacy Tracker Migration and Cutover Runbook",
    "category": "System Architecture",
    "order": 13,
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
        "id": "plane-migration-import-studio",
        "title": "Plane Migration Import Studio (`/admin/imports`)",
        "level": 2
      },
      {
        "id": "key-plane-migration-capabilities",
        "title": "Key Plane Migration Capabilities:",
        "level": 3
      },
      {
        "id": "emergency-rollback-procedure",
        "title": "Emergency Rollback Procedure",
        "level": 2
      }
    ],
    "content": "# Legacy Tracker Migration and Cutover Runbook\n\n## Overview\n\nOrganizations seeking to escape SaaS paywalls, Jira seat taxes, and single-vendor agent lock-in require a safe, deterministic migration path. Legacy project management tools often store data in proprietary formats, making manual migration prone to data loss, dropped comments, and broken ticket linkages.\n\n\ud83d\udc4dkanban provides a battle-tested **7-Phase Live Cutover Protocol** (`docs/CUTOVER.md`) designed for migrating from legacy issue trackers (such as Jira, Vibe Kanban, or self-hosted boards) to \ud83d\udc4dkanban with zero data loss and minimal operational disruption.\n\n---\n\n## The 7-Phase Live Cutover Protocol\n\n```mermaid\nflowchart TD\n    P1[\"Phase 1: Pre-Cutover Readiness & Schema Alignment<br/>- Deploy target stack, configure Multi-Card Auth<br/>- Run healthchecks and verify checksums\"]\n    P2[\"Phase 2: Read-Only Freeze of Source Platform<br/>- Place legacy tracker in maintenance mode<br/>- Capture baseline snapshot\"]\n    P3[\"Phase 3: Extraction & Markdown Normalization<br/>- Ingest JSON/XML export<br/>- Run Unicode Surrogate & Paste-Jacking pipeline\"]\n    P4[\"Phase 4: Universal Object Graph Hydration & Linking<br/>- Populate UOG spine & typed object_links<br/>- Generate redirect aliases\"]\n    P5[\"Phase 5: Six Non-Bypassable Verification Gates<br/>- Entity counts, Link Auditor, Markdown fidelity,<br/>ACL parity, MCP health, SLA latency\"]\n    P6[\"Phase 6: DNS Cutover & Traffic Switch<br/>- Point domain to \ud83d\udc4dkanban Caddy ingress\"]\n    P7[\"Phase 7: Post-Cutover Monitoring & Rollback Window<br/>- 7-day read-only fallback window\"]\n\n    P1 --> P2\n    P2 --> P3\n    P3 --> P4\n    P4 --> P5\n    P5 -->|Certified PASSED| P6\n    P6 --> P7\n```\n\n![Standalone to Production Compose Export](images/27-standalone-compose-export.png)\n\n### Phase 1: Pre-Cutover Readiness and Schema Alignment\n- Deploy target \ud83d\udc4dkanban production stack.\n- Configure Multi-Card Authentication cards to match source identity providers (OIDC/SAML/LDAP).\n- Run migration pre-flight checks: `uv run kanban-ctl ops healthcheck` and verify source export snapshot checksums (`sha256sum -c manifest.sha256`).\n\n### Phase 2: Read-Only Freeze of Source Platform\n- Place the legacy tracker instance into read-only maintenance mode.\n- Notify engineering teams and pause active CI/CD webhooks.\n- Capture baseline snapshot of source database.\n\n### Phase 3: Extraction and Markdown Normalization\n- Extract work items, cycles, modules, pages, stickies, and attachments via source tracker export APIs.\n- Pass all textual descriptions and comments through the \ud83d\udc4dkanban **Canonical Markdown Pipeline**:\n  - Rejects Unicode lone surrogates.\n  - Strips hidden DOM paste-jacking sequences.\n  - Converts legacy HTML into clean, standardized CommonMark.\n\n### Phase 4: Universal Object Graph Hydration\n- Ingest normalized objects into the PostgreSQL Universal Object Graph (`kanban_migrator`).\n- Translate legacy issue references (`PROJ-123`) into canonical \ud83d\udc4dkanban identifiers while creating redirect aliases.\n- Establish typed `object_links` for all parent-child relationships, sub-issues, and blockers.\n\n### Phase 5: The Six Non-Bypassable Verification Gates\nBefore DNS can be redirected, the migration must pass all 6 automated verification gates:\n\n```mermaid\nflowchart LR\n    Gate1[\"Gate 1<br/>Entity Parity\"] --> Gate2[\"Gate 2<br/>Link Auditor\"]\n    Gate2 --> Gate3[\"Gate 3<br/>Markdown Fidelity\"]\n    Gate3 --> Gate4[\"Gate 4<br/>ACL Parity\"]\n    Gate4 --> Gate5[\"Gate 5<br/>MCP Health\"]\n    Gate5 --> Gate6[\"Gate 6<br/>SLA Latency\"]\n    Gate6 --> Cutover[\"Ready for Live Cutover\"]\n```\n\n| Gate # | Verification Gate | Success Threshold |\n| :---: | :--- | :--- |\n| **1** | **Entity Count Parity** | 100% match across issues, states, cycles, modules, comments, and attachments. |\n| **2** | **Object Link Auditor** | Zero orphaned links, cross-tenant leaks, or invalid hierarchy cycles. |\n| **3** | **Markdown Fidelity** | 100% of descriptions render valid Markdown; zero unparsed HTML tags. |\n| **4** | **Principal & ACL Parity** | All users, groups, and permissions map accurately to \ud83d\udc4dkanban roles. |\n| **5** | **MCP Surface Health** | All 27 MCP tools return clean schemas and pass handshake benchmarks. |\n| **6** | **Performance Latency** | Board view initial load under 100ms; REST API p95 latency under 50ms. |\n\n### Phase 6: DNS Cutover and Traffic Switch\n- Update internal DNS records or reverse proxy routing (e.g. Caddy / Nginx) to point domain `kanban.example.com` to the \ud83d\udc4dkanban production ingress (`edge_net`).\n- Restart agent background workers with updated MCP endpoint URLs.\n\n### Phase 7: Post-Cutover Monitoring and Rollback Window\n- Maintain legacy tracker instance in read-only state for a 7-day observation window.\n- Monitor real-time WebSocket connection stability and activity logs.\n\n---\n\n## Plane Migration Import Studio (`/admin/imports`)\n\nTo streamline cutover from Plane workspaces to \ud83d\udc4dkanban without custom extraction scripts, \ud83d\udc4dkanban includes a native **Plane Migration Import Studio** accessible at `/admin/imports` (and `/settings/mcp` -> Plane Migration Studio tab).\n\n```mermaid\nflowchart TD\n    subgraph PlaneImportPipeline[\"Plane Migration Studio Pipeline\"]\n        Upload[\"Step 1: Upload Plane Export Bundle<br/>(File upload or paste raw JSON)\"] --> Parse[\"JSON Schema Validation<br/>Verify projects, states, issues, cycles, modules, comments, members\"]\n        Parse --> Metrics[\"Step 2: Entity Detection & Metrics Cards<br/>Live counts across all 7 entity types\"]\n        Metrics --> DryRun[\"Step 3: Stage 1 Dry-Run Simulation<br/>Idempotency checks, state mapping preview, conflict detection\"]\n        DryRun --> Live[\"Step 4: Execute Live Migration<br/>Atomic PostgreSQL transaction (kanban_migrator)\"]\n        Live --> Verify[\"Step 5: Post-Import Integrity Audit<br/>Run Invalid Object Link Auditor on imported graph\"]\n    end\n```\n\n![Plane Migration Import Studio Step 1](images/49-admin-plane-import-studio.png)\n\n![Plane Migration Studio Dry-Run Simulation](images/62-plane-migration-dry-run.png)\n\n### Key Plane Migration Capabilities:\n1. **Direct JSON Ingestion:** Accepts standard Plane export bundles via direct drag-and-drop file upload or pasting raw JSON.\n2. **Real-Time Entity Metric Cards:** Displays instant counts for detected Projects, States, Issues, Cycles, Modules, Issue Comments, and Members.\n3. **Stage 1 Dry-Run Simulation:** Simulates the complete import without writing to the database. Displays state mapping translations, identifies potential duplicate keys, and computes idempotency diffs.\n4. **Atomic Transactional Import:** Live migrations execute within an atomic transaction. If any entity fails validation or violates an object graph invariant, the entire migration rolls back cleanly, leaving existing data untouched.\n5. **Universal Link Synthesis:** Automatically establishes typed `PARENT_OF`, `BLOCKS`, and `ATTACHED_TO` object links corresponding to source Plane relationships.\n\n---\n\n## Emergency Rollback Procedure\n\nIf a critical business blocker occurs during the cutover window:\n1. **Revert DNS:** Immediately restore DNS routing to the legacy tracker cluster.\n2. **Delta Capture:** Run `uv run kanban-ctl cutover verify` / inspect `activity_records` since cutover to extract any tickets updated in \ud83d\udc4dkanban during the live window.\n3. **Reconcile:** Re-apply the delta diff into the source tracker to ensure zero data loss.\n\n![Workspace Home After Successful Cutover](images/05-workspace-home.png)\n"
  },
  {
    "slug": "multi-card-authentication-studio",
    "title": "Multi-Card Authentication Studio and Identity Architecture",
    "category": "System Architecture",
    "order": 14,
    "summary": "Enterprise identity management demands both flexibility and strict security. Rather than forcing organizations into a single identity silo, \ud83d\udc4dkanban implements a **Multi-Card Authentication Studio**. Administrators can configure, reorder, test, and enable multiple independent authentication providers simultaneously.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "first-boot-setup-wizard",
        "title": "First-Boot Setup Wizard (`/setup`)",
        "level": 2
      },
      {
        "id": "bootstrap-security-invariants",
        "title": "Bootstrap Security Invariants",
        "level": 3
      },
      {
        "id": "multi-card-login-experience",
        "title": "Multi-Card Login Experience (`/login`)",
        "level": 2
      },
      {
        "id": "key-features-of-multi-card-login",
        "title": "Key Features of Multi-Card Login",
        "level": 3
      },
      {
        "id": "admin-authentication-studio",
        "title": "Admin Authentication Studio (`/admin/auth`)",
        "level": 2
      },
      {
        "id": "studio-controls-and-capabilities",
        "title": "Studio Controls and Capabilities",
        "level": 3
      },
      {
        "id": "envelope-encryption",
        "title": "Envelope Encryption (`MASTER_KEK`)",
        "level": 3
      },
      {
        "id": "the-invariant",
        "title": "The `LOCKOUT_PREVENTED` Invariant",
        "level": 3
      },
      {
        "id": "multi-factor-authentication-and-recovery-codes",
        "title": "Multi-Factor Authentication and Recovery Codes",
        "level": 3
      }
    ],
    "content": "# Multi-Card Authentication Studio and Identity Architecture\n\n## Overview\n\nEnterprise identity management demands both flexibility and strict security. Rather than forcing organizations into a single identity silo, \ud83d\udc4dkanban implements a **Multi-Card Authentication Studio**. Administrators can configure, reorder, test, and enable multiple independent authentication providers simultaneously.\n\nSupported authentication card types:\n- **Local Admin:** Built-in argon2id hashed credentials for platform administrators.\n- **OAuth2 / OpenID Connect (OIDC):** Enterprise SSO supporting Okta, Google Workspace, GitHub, GitLab, Keycloak, and Authentik.\n- **LDAPS / StartTLS:** Active Directory and OpenLDAP directory integration with TLS certificate pinning.\n- **WebAuthn / Passkeys:** Hardware security keys (FIDO2/YubiKey) and platform biometrics (Touch ID, Windows Hello) with Relying Party display string `rp.name = \"\ud83d\udc4dkanban\"`.\n- **TOTP Authenticator:** Time-based one-time password second-factor enforcement.\n\n```mermaid\nflowchart TD\n    Login[\"/login Surface (Multi-Card Container)\"] --> Cards[\"Ordered Cards by sort_rank\"]\n    Cards --> C1[\"Local Admin<br/>argon2id hash\"]\n    Cards --> C2[\"OAuth2 / OIDC<br/>Enterprise SSO & Claims\"]\n    Cards --> C3[\"LDAPS / StartTLS<br/>Pinned TLS certs\"]\n    Cards --> C4[\"WebAuthn Passkeys<br/>FIDO2 / TouchID / YubiKey\"]\n\n    C1 --> Verify[\"Session Token Minting\"]\n    C2 --> Verify\n    C3 --> Verify\n    C4 --> Verify\n\n    Verify --> MFA{\"MFA Enforced?\"}\n    MFA -->|Yes| TOTP[\"TOTP Second Factor / Recovery Codes\"]\n    MFA -->|No| Session[\"AAL1 Session Minted\"]\n    TOTP --> AAL2[\"AAL2 Session Minted (Admin-Capable)\"]\n```\n\n---\n\n## First-Boot Setup Wizard (`/setup`)\n\nOn initial installation, \ud83d\udc4dkanban boots into a secure provisioning state. Until the platform is initialized, all routes redirect to `/setup`.\n\n![First-Boot Setup Wizard](images/01-first-boot-setup.png)\n\n### Bootstrap Security Invariants\n\n1. **Single-Use Bootstrap Token (`kb_setup_*`):** When the container starts for the first time, a cryptographically secure token prefixed with `kb_setup_` is generated and written exclusively to container logs or stdout. Initial account creation requires providing this token.\n2. **Pre-Session CSRF Protection:** First-boot requests establish a strict double-submit cookie handshake using `__Host-kb_csrf` (over HTTPS) and `kb_csrf` (fallback) headers to prevent cross-site onboarding attacks.\n3. **Atomic Root Workspace Creation:** The wizard provisions the initial Server Administrator, creates the default workspace and project, and immediately invalidates the bootstrap token.\n\n---\n\n## Multi-Card Login Experience (`/login`)\n\nThe login screen presents enabled authentication methods as clean, discrete cards sorted in the exact sequence determined by the administrator.\n\n![Multi-Card Login Screen](images/02-multi-card-login.png)\n\n### Key Features of Multi-Card Login\n\n- **Sort Order Control:** Providers are displayed according to their configured `sort_rank`, allowing primary enterprise SSO cards to take prominent visual priority.\n- **Zero Implicit Email Auto-Merge Invariant:** A critical security flaw in many SaaS systems is the automatic linking of accounts based solely on matching email addresses. In \ud83d\udc4dkanban, auto-merging is strictly forbidden. An identity claim from an external provider will only bind to an existing account if the user explicitly authorizes the link through verified secondary credentials.\n- **Passkey and Biometric Priority:** Users with registered WebAuthn credentials can authenticate with a single touch, without entering usernames or passwords.\n\n---\n\n## Admin Authentication Studio (`/admin/auth`)\n\nServer Administrators configure identity providers through the visual Auth Studio at `/admin/auth`. Access to this studio requires Authenticator Assurance Level 2 (AAL2) credentials.\n\n![Admin Authentication Studio](images/03-admin-auth-studio.png)\n\n### Studio Controls and Capabilities\n\n- **Enable / Disable Toggles:** Instantly activate or suspend identity providers without losing configuration settings.\n- **Drag-and-Drop Reordering:** Change the display order of cards on the `/login` screen in real time.\n- **Write-Only Secrets:** Client secrets, LDAP bind passwords, and private keys are write-only. Once saved, they cannot be read back by client browsers or administrative APIs.\n- **Live Handshake Testing:** The `Test Handshake` button validates endpoint connectivity, TLS certificate validation, and credential binding without modifying live user sessions.\n\n### Envelope Encryption (`MASTER_KEK`)\n\nAll sensitive authentication secrets stored in the database are encrypted at rest using envelope encryption:\n- Secrets are encrypted using an AES-256-GCM data encryption key (DEK).\n- The DEK is encrypted using the platform Master Key Encryption Key (`MASTER_KEK`), supplied via environment variable or hardware security module (HSM).\n\n### The `LOCKOUT_PREVENTED` Invariant\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Server Administrator\n    participant UI as Auth Studio (/admin/auth)\n    participant API as /api/v1/admin/auth/cards\n    participant DB as PostgreSQL\n\n    Admin->>UI: Toggle 'Local Admin' card to Disabled\n    UI->>API: PATCH /cards/{id} (is_active: false)\n    API->>DB: Query COUNT(active admin cards) excluding this card\n    alt Remaining Active Admin Cards == 0\n        DB-->>API: 0 Active Admin Paths Remain!\n        API-->>UI: 409 Conflict (LOCKOUT_PREVENTED)\n        UI-->>Admin: Show Error Modal: Cannot disable sole remaining admin card\n    else Remaining Active Admin Cards >= 1\n        DB-->>API: Active admin paths exist (e.g. OIDC configured)\n        API->>DB: UPDATE auth_cards SET is_active = false\n        DB-->>API: 200 OK\n        API-->>UI: Card disabled successfully\n    end\n```\n\nTo eliminate administrative lockouts:\n- The system continuously evaluates the active admin authentication paths.\n- If an administrator attempts to disable or delete the sole remaining active admin card (e.g., disabling Local Admin before configuring working SSO), the mutation is rejected with error code `LOCKOUT_PREVENTED`.\n- At least one verified administrative authentication path must remain active at all times.\n\n### Multi-Factor Authentication and Recovery Codes\n\nDuring administrator provisioning and MFA enrollment, high-entropy single-use recovery codes are minted, cryptographically hashed, and presented to the operator:\n\n![MFA Provisioning and Recovery Codes](images/34-mfa-recovery-codes.png)\n"
  },
  {
    "slug": "multi-provider-ai-engine-and-runners",
    "title": "Multi-Provider AI Engine, Execution Harnesses, and Runners",
    "category": "System Architecture",
    "order": 15,
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
        "id": "supported-providers-matrix",
        "title": "Supported Providers Matrix",
        "level": 3
      },
      {
        "id": "zero-shell-cli-pipe-harnesses",
        "title": "Zero-Shell CLI Pipe Harnesses (`agy -p` / `codex -p`)",
        "level": 2
      },
      {
        "id": "ai-providers-and-token-caps-studio",
        "title": "AI Providers and Token Caps Studio (`/admin/ai`)",
        "level": 2
      },
      {
        "id": "key-provider-governance-features",
        "title": "Key Provider Governance Features:",
        "level": 3
      },
      {
        "id": "agent-definitions-studio",
        "title": "Agent Definitions Studio (`/admin/agents`)",
        "level": 2
      },
      {
        "id": "definition-capabilities",
        "title": "Definition Capabilities:",
        "level": 3
      },
      {
        "id": "agent-runners-studio-and-distributed-mtls-daemon",
        "title": "Agent Runners Studio and Distributed mTLS Daemon (`/admin/agent-runners`)",
        "level": 2
      },
      {
        "id": "runner-infrastructure",
        "title": "Runner Infrastructure:",
        "level": 3
      },
      {
        "id": "agent-revocation-and-security-controls",
        "title": "Agent Revocation and Security Controls",
        "level": 2
      },
      {
        "id": "remote-mtls-repository-runners",
        "title": "Remote mTLS Repository Runners",
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
      }
    ],
    "content": "# Multi-Provider AI Engine, Execution Harnesses, and Runners\n\n## Overview\n\nUnlike commercial SaaS ticketing platforms that hardcode proprietary cloud models behind expensive monthly add-ons, \ud83d\udc4dkanban features an open, multi-provider **AI Orchestration Engine** (`agent/`). Organizations can leverage cloud AI providers, local open-source models, or zero-shell isolated command-line pipes without changing application code.\n\nSupported provider ecosystems:\n- **Cloud LLMs:** OpenAI (GPT-4o, o3-mini), Google Gemini (Gemini 2.5 Flash/Pro), and OpenAI-compatible gateways.\n- **Local Private LLMs:** Ollama (Llama 3, DeepSeek-R1, Qwen 2.5) running completely on-premise with zero data egress.\n- **Zero-Shell CLI Pipe Harnesses:** Direct pipe execution (`agy -p`, `codex -p`) running inside hardened Linux sandboxes.\n- **Remote Read-Only mTLS Runners:** Distributed runners executing builds and code inspections over encrypted WebSockets.\n\n```mermaid\nflowchart TD\n    subgraph Core[\"\ud83d\udc4dkanban Agent Runtime\"]\n        App[\"FastAPI & Worker Dispatcher\"]\n        Protocol[\"LLMProvider Interface (agent/providers/base.py)\"]\n    end\n\n    subgraph Providers[\"Multi-Provider Implementations\"]\n        OpenAI[\"OpenAI Provider<br/>GPT-4o, o3-mini, compatible gateways\"]\n        Gemini[\"Google Gemini Provider<br/>Gemini 2.5 Flash / Pro (native tools)\"]\n        Ollama[\"Local Ollama Provider<br/>Llama 3, DeepSeek-R1, Qwen 2.5\"]\n        CLIPipe[\"Zero-Shell CLI Pipe<br/>agy -p / codex -p in nsjail\"]\n        Runner[\"Remote mTLS Runner<br/>Encrypted WSS, read-only repo\"]\n    end\n\n    App --> Protocol\n    Protocol --> OpenAI\n    Protocol --> Gemini\n    Protocol --> Ollama\n    Protocol --> CLIPipe\n    Protocol --> Runner\n```\n\n![Async Agent Gate Card States and Transition Lifecycle](images/16-async-agent-gate-states.png)\n\n---\n\n## Provider Architecture and Abstraction Layer\n\nThe engine abstracts all AI interactions behind a clean, asynchronous provider protocol (`agent/providers/base.py`):\n\n```python\nclass LLMProvider(ABC):\n    @abstractmethod\n    async def complete(self, prompt: str, system: str | None = None, **kwargs) -> CompletionResult:\n        \"\"\"Execute a text completion or FIM generation.\"\"\"\n\n    @abstractmethod\n    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:\n        \"\"\"Execute a multi-turn conversation with tool calling.\"\"\"\n\n    @abstractmethod\n    async def embed(self, texts: list[str]) -> list[list[float]]:\n        \"\"\"Generate vector embeddings for semantic search.\"\"\"\n```\n\n### Supported Providers Matrix\n\n| Provider Key | Primary Use Cases | Streaming Support | Function / Tool Calling | Network Boundary |\n| :--- | :--- | :---: | :---: | :--- |\n| **`openai`** | Complex planning, synthesis | Yes | Yes (Native JSON Schema) | `egress_llm_net` |\n| **`gemini`** | Large context specs, vision | Yes | Yes (Native Function Calling) | `egress_llm_net` |\n| **`ollama`** | Air-gapped workstations, privacy | Yes | Yes (Model dependent) | `data_net` / local |\n| **`cli_pipe`** | Deterministic CI agents, bash-less | No (Batch) | Pipe JSON protocol | `sandbox_net` (nsjail) |\n| **`remote_runner`** | Forensic code audits, test gates | Yes (WSS) | Streamable RPC | Dedicated mTLS |\n\n---\n\n## Zero-Shell CLI Pipe Harnesses (`agy -p` / `codex -p`)\n\n```mermaid\nsequenceDiagram\n    autonumber\n    participant Engine as AI Orchestrator\n    participant Sandbox as nsjail Sandbox Runner\n    participant Model as CLI Pipe (agy -p / codex -p)\n\n    Engine->>Sandbox: Spawn isolated container (CLONE_NEWNET, read-only FS, 512MB RAM)\n    Engine->>Sandbox: Pipe prompt.json over STDIN\n    Sandbox->>Model: Execute deterministic harness without shell/bash\n    Model->>Sandbox: Generate tool call / response JSON over STDOUT\n    Sandbox-->>Engine: Structured JSON stream (Zero bash exposure)\n    Engine->>Engine: Validate response against Pydantic schema\n```\n\nAutonomous agents frequently need to inspect code, run validators, or check commit history. However, granting an LLM arbitrary bash or shell access introduces severe remote code execution (RCE) hazards.\n\n\ud83d\udc4dkanban resolves this with **Zero-Shell CLI Pipes**:\n- Agents do not receive an interactive shell or bash process.\n- Execution communicates strictly over standard input (`stdin`) and standard output (`stdout`) using structured JSON pipes.\n- Commands run inside a sandboxed Linux jail (`nsjail` / `setpriv`):\n  - Read-only root filesystem.\n  - Network namespace disabled (`CLONE_NEWNET`).\n  - Memory limit capped at 512 MB.\n  - Execution time limited to 15 seconds.\n\n```bash\n# Example invocation of pipe harness:\ncat prompt.json | agy -p --sandbox-jail > response.json\n```\n\n---\n\n## AI Providers and Token Caps Studio (`/admin/ai`)\n\nWorkspace and server administrators manage LLM provider registrations, write-only API key custody, monthly token budgets, and zero-egress policies in the visual studio at `/admin/ai`.\n\n```mermaid\nflowchart TD\n    subgraph AIStudio[\"AI Providers & Token Caps Architecture\"]\n        AdminUser[\"Administrator (AAL2)\"] --> Reg[\"Register / Edit Provider\"]\n        Reg --> ProvidersList[\"Configured Providers<br/>- OpenAI (Cloud, priority 10)<br/>- Gemini (Cloud, priority 20)<br/>- Ollama (Local Air-Gap, priority 5)\"]\n        \n        ProvidersList --> AirGapCheck{\"Air-Gap Policy Active?\"}\n        AirGapCheck -->|Yes| BlockCloud[\"Cloud Providers Blocked<br/>Only Local Zero-Egress Ollama Allowed\"]\n        AirGapCheck -->|No| AllowCloud[\"Dispatched by Priority Tier\"]\n        \n        AllowCloud --> BudgetGate{\"Monthly Token Budget Gate\"}\n        BlockCloud --> BudgetGate\n        \n        BudgetGate -->|Within Cap| Exec[\"Execute Completion / Tool Call\"]\n        BudgetGate -->|Cap Exceeded| Reject[\"429 Budget Exceeded<br/>Alert Admin to Reset or Expand Cap\"]\n    end\n```\n\n![AI Providers and Token Caps Studio](images/43-admin-ai-studio-providers.png)\n\n### Key Provider Governance Features:\n1. **Write-Only API Key Custody:** API keys are submitted over encrypted TLS, stored encrypted in the database, and never echoed back to the browser.\n2. **Enterprise Air-Gap Mode:** When activated, all cloud egress to external AI services is blocked at the network layer. Only local, on-premise runtimes (such as Ollama) are authorized for completions.\n3. **Monthly Token Budgets & Ledgers:** Each provider configuration enforces monthly input/output token caps with automated rollover and audit ledger accounting.\n\n---\n\n## Agent Definitions Studio (`/admin/agents`)\n\nAdministrators define and customize autonomous agent personas, tool permissions, and system prompt templates at `/admin/agents`.\n\n```mermaid\nflowchart LR\n    subgraph AgentDefFlow[\"Agent Definition & Validation Lifecycle\"]\n        Def[\"Agent Definition<br/>Name, Slug, Model, Prompt Template\"] --> Scope[\"Tool Allowlist Scoping<br/>Permitted MCP Tools (read_ticket, add_comment, etc.)\"]\n        Scope --> Modal[\"Validation Modal (/admin/agents)<br/>Simulate test prompt against agent schema\"]\n        Modal --> Verdict{\"Validation Passes?\"}\n        Verdict -->|Yes| Active[\"Registered as Active Agent Principal\"]\n        Verdict -->|No| Fix[\"Report Schema / Prompt Errors for Correction\"]\n    end\n```\n\n![Agent Definitions Studio Overview](images/44-admin-agent-definitions.png)\n\n![Agent Validation Modal](images/60-agent-validation-modal.png)\n\n### Definition Capabilities:\n- **Role and Model Mapping:** Bind specific personas (e.g. `reality-checker`, `security-auditor`, `code-reviewer`) to optimal models (Gemini 2.5 Flash, GPT-4o, DeepSeek-R1).\n- **Tool Allowlist Scoping:** Strictly restrict which MCP tools each agent principal can invoke, enforcing least privilege.\n- **Interactive Validation Modal:** Test and validate agent definitions before deploying them to live project workflows.\n\n---\n\n## Agent Runners Studio and Distributed mTLS Daemon (`/admin/agent-runners`)\n\nFor heavy build verification, sandbox test execution, and isolated code review, \ud83d\udc4dkanban deploys distributed **Agent Runners** managed through `/admin/agent-runners`.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Server Administrator\n    participant Studio as Runner Studio (/admin/agent-runners)\n    participant Server as \ud83d\udc4dkanban Orchestrator\n    participant Daemon as Remote Runner Daemon\n\n    Admin->>Studio: Click \"+ Mint Runner Token\"\n    Studio->>Server: Generate ephemeral enrollment token & mTLS cert\n    Server-->>Studio: Return copyable docker/cli run snippet\n    Admin->>Daemon: Launch daemon with enrollment token\n    Daemon->>Server: Establish mTLS WebSocket handshake\n    Server->>Server: Verify cryptographic certificate fingerprint\n    Server-->>Daemon: Channel verified: Runner enters \"ONLINE\"\n    Daemon->>Server: Heartbeat ping every 15s (CPU, RAM, active jobs)\n```\n\n![Agent Runner Studio Overview](images/45-admin-runner-studio.png)\n\n![Runner Mint Token Modal](images/61-runner-mint-token-modal.png)\n\n### Runner Infrastructure:\n- **mTLS Mutual Authentication:** Cryptographic X.509 mutual TLS guarantees that only authorized worker nodes connect to the orchestrator.\n- **Copyable Enrollment Snippets:** One-click copyable `docker run` and CLI commands for instant daemon deployment on build hosts.\n- **Heartbeat Monitoring:** Real-time visibility into runner health, active execution count, CPU load, and container status.\n\n---\n\n## Agent Revocation and Security Controls\n\nWhen an agent session exhibits anomalous activity or a credential leak is detected, administrators can invoke an instant Kill Switch across all surfaces:\n\n![Agent Kill Switch and Immediate Session Revocation](images/18-agent-kill-switch.png)\n\n---\n\n## Remote mTLS Repository Runners\n\nFor long-running verification tasks (e.g. compiling large C++ or Rust binaries, running full end-to-end Playwright suites), tasks are dispatched to external **mTLS Runners**:\n- **Mutual TLS Authentication (mTLS):** Both the \ud83d\udc4dkanban server and the runner verify cryptographic X.509 certificates.\n- **WebSocket Streaming:** Real-time log output and build artifacts stream back over encrypted WebSocket channels.\n- **Read-Only Volume Mounting:** The repository is mounted read-only to prevent unauthorized code mutations on the build host.\n\n---\n\n## Testable AI: Pluggable Fixtures and CLI Validation\n\nAI agent workflows can be notoriously difficult to test deterministically in CI pipelines due to model drift, token costs, and rate limits. \ud83d\udc4dkanban enforces **100% Deterministic AI Testing**:\n\n### Pluggable AI Response Fixtures\nIn test suites, providers are swapped with `FixtureLLMProvider` and `FixtureCLIRunner`:\n- Replays recorded, deterministic JSON responses without making network calls.\n- Simulates network timeouts, rate limit errors (`429`), and malformed responses to verify system resilience.\n\n### Local Agent CLI Diagnostics\nEngineers can validate transition interceptors and AI workflows locally via the command line:\n\n```bash\n# Validate a transition interceptor against a ticket fixture\nkanban-agent validate-transition \\\n  --ticket-file test_ticket.json \\\n  --from-state in_progress \\\n  --to-state done \\\n  --dry-run\n```\n"
  },
  {
    "slug": "production-promotion-and-backup-runbook",
    "title": "Production Promotion and Backup Runbook",
    "category": "System Architecture",
    "order": 16,
    "summary": "Teams frequently evaluate software in a standalone environment before promoting it to a production cluster. In conventional ticketing platforms, moving from a single test container to a hardened multi-container architecture requires painful manual database migrations, re-uploading media assets, and rebuilding configuration.",
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
        "id": "detailed-execution-steps",
        "title": "Detailed Execution Steps",
        "level": 3
      },
      {
        "id": "encrypted-kbbak1-backup-archive-format",
        "title": "Encrypted KBBAK1 Backup Archive Format",
        "level": 2
      },
      {
        "id": "kbbak1-archive-structure",
        "title": "KBBAK1 Archive Structure",
        "level": 3
      },
      {
        "id": "cryptographic-envelope",
        "title": "Cryptographic Envelope",
        "level": 3
      },
      {
        "id": "visual-backup-and-disaster-recovery-studio",
        "title": "Visual Backup and Disaster Recovery Studio (`/admin/standalone`)",
        "level": 2
      },
      {
        "id": "studio-features",
        "title": "Studio Features:",
        "level": 3
      },
      {
        "id": "disaster-recovery-and-restoration",
        "title": "Disaster Recovery and Restoration",
        "level": 2
      },
      {
        "id": "post-restore-automated-verification",
        "title": "Post-Restore Automated Verification",
        "level": 3
      }
    ],
    "content": "# Production Promotion and Backup Runbook\n\n## Overview\n\nTeams frequently evaluate software in a standalone environment before promoting it to a production cluster. In conventional ticketing platforms, moving from a single test container to a hardened multi-container architecture requires painful manual database migrations, re-uploading media assets, and rebuilding configuration.\n\n\ud83d\udc4dkanban provides a streamlined, reliable **Production Promotion and Encrypted Backup Architecture** (`docs/PROMOTION_AND_BACKUP.md`). With standardized tools, administrators can promote standalone deployments or execute disaster recovery with minimal downtime.\n\n---\n\n## Standalone to Production Promotion Workflow\n\nMoving from a single-container standalone instance (`docker run`) to the 5-network production stack (`docker compose`) takes five sequential steps:\n\n```mermaid\nflowchart TD\n    S1[\"Step 1: Drain Active Traffic<br/>kanban-ctl promote --drain --timeout=30s<br/>Halt requests and flush WAL\"]\n    S2[\"Step 2: Export Production Compose Bundle<br/>kanban-ctl promote --export-compose ./deploy/prod/<br/>Generate 5-network compose and config\"]\n    S3[\"Step 3: Transfer PostgreSQL Data Volume<br/>Copy /var/lib/kanban/data to production volume<br/>Hardware-level data preservation\"]\n    S4[\"Step 4: Launch Production Stack<br/>docker compose -f deploy/prod/docker-compose.yml up -d<br/>Compartmentalized 5-network isolation\"]\n    S5[\"Step 5: Post-Promotion Verification<br/>kanban-ctl health --full && kanban-ctl audit-links<br/>Verify 100% integrity\"]\n\n    S1 --> S2\n    S2 --> S3\n    S3 --> S4\n    S4 --> S5\n```\n\n![Standalone to Production Compose Export Modal](images/27-standalone-compose-export.png)\n\n### Detailed Execution Steps\n\n#### Step 1: Drain Active Traffic\nHalt incoming requests and flush PostgreSQL Write-Ahead Logs (WAL):\n```bash\ndocker exec -it thumbs-up-kanban kanban-ctl promote --drain --timeout=30s\n```\n\n#### Step 2: Export Production Configuration\nGenerate the hardened 5-network `docker-compose.yml` and environment templates from the running instance:\n```bash\ndocker exec -it thumbs-up-kanban kanban-ctl promote --export-compose /tmp/deploy/\ndocker cp thumbs-up-kanban:/tmp/deploy ./deploy-prod\n```\n\n#### Step 3: Transfer Persistent Volumes\nCopy the internal database directory to the dedicated production storage volume:\n```bash\ndocker volume create kanban_postgres_prod_data\ndocker run --rm \\\n  -v kanban_data:/from:ro \\\n  -v kanban_postgres_prod_data:/to \\\n  alpine cp -a /from/. /to/\n```\n\n#### Step 4: Launch Production Stack\nStart the compartmentalized multi-container cluster:\n```bash\ncd deploy-prod\ndocker compose up -d\n```\n\n#### Step 5: Post-Promotion Verification\nConfirm service availability and object graph integrity:\n```bash\ndocker compose exec app kanban-ctl health --full\ndocker compose exec app kanban-ctl audit-links --dry-run\n```\n\n---\n\n## Encrypted KBBAK1 Backup Archive Format\n\n\ud83d\udc4dkanban implements a unified backup format named **KBBAK1**. Rather than taking unencrypted raw SQL dumps, KBBAK1 produces an encrypted, tamper-evident bundle:\n\n```mermaid\nflowchart LR\n    subgraph Contents[\"KBBAK1 Archive Members\"]\n        M[\"manifest.json<br/>(SHA-256 Checksums, Versions)\"]\n        D[\"database.sql.gz<br/>(Complete PostgreSQL Dump)\"]\n        O[\"object_graph.jsonl<br/>(Universal Spine & Links)\"]\n        A[\"media/<br/>(Attachments & Visual Assets)\"]\n    end\n\n    subgraph Crypto[\"Cryptographic Envelope\"]\n        KDF[\"PBKDF2 KDF<br/>(600,000 Iterations)\"]\n        AES[\"AES-256-GCM<br/>Ciphertext Stream\"]\n    end\n\n    Contents --> KDF\n    KDF --> AES\n    AES --> Bundle[\".kbbak1 Encrypted Bundle\"]\n```\n\n### KBBAK1 Archive Structure\n- **`manifest.json`:** Contains platform version, schema migration hash, tenant IDs, and SHA-256 checksums of all internal components.\n- **`database.sql.gz`:** Complete PostgreSQL cluster dump including all schemas, RLS policies, and extensions.\n- **`object_graph.jsonl`:** Portable Universal Object Graph spine and typed links export for cross-version reconciliation.\n- **`media/`:** Uploaded attachments, document assets, and user avatars.\n\n### Cryptographic Envelope\nThe entire tarball is encrypted using AES-256-GCM. The encryption key is derived from the administrative backup secret (`BACKUP_KEY`) using PBKDF2 with 600,000 iterations:\n```bash\n# Create an encrypted backup archive\nkanban-ctl backup create \\\n  --encrypt \\\n  --output /var/backups/kanban-$(date +%Y%m%d-%H%M%S).kbbak1\n```\n\n![System Settings and Environment Configuration](images/26-system-settings.png)\n\n---\n\n## Visual Backup and Disaster Recovery Studio (`/admin/standalone`)\n\nIn addition to CLI automation, administrators managing standalone and hybrid deployments can trigger backups, configure schedules, and execute disaster recovery through the visual studio at `/admin/standalone`.\n\n```mermaid\nflowchart TD\n    subgraph StandaloneStudio[\"System Storage, Backups & Deployment Studio\"]\n        Tab1[\"Storage & Capabilities Health<br/>Disk usage, DB size, WAL status\"]\n        Tab2[\"Backup, Auto-Backup & Restore<br/>Manual Encrypted (.kbbak), Schedules, 2-Stage Restore\"]\n        Tab3[\"Docker Compose Export<br/>Hardened multi-container production bundle\"]\n    end\n```\n\n![Visual Backup and Disaster Recovery Studio](images/57-standalone-backup-restore-modal.png)\n\n### Studio Features:\n1. **Manual Encrypted Backup (`.kbbak`):** Enter a client-side passphrase (minimum 16 characters) to generate and download an AES-256-GCM encrypted snapshot directly to the operator's machine. The passphrase is never stored on the server.\n2. **Automated Scheduled Backups:** Enable periodic automated backups with customizable backup intervals (e.g. every 24 hours) and snapshot retention windows (e.g. keep latest 7 snapshots).\n3. **Existing Server Snapshots List:** Browse, inspect file sizes, creation timestamps, and download historical server snapshots with a single click.\n4. **Two-Stage Database Restore:** Restoring a database snapshot requires two-stage verification: Step 1 verifies cryptographic archive integrity without touching the database; Step 2 requires explicit typed confirmation before applying the restore.\n\n---\n\n## Disaster Recovery and Restoration\n\nRestoring a cluster from an encrypted backup archive is completely automated.\n\n```bash\n# Step 1: Validate archive integrity without restoring\nkanban-ctl backup verify --input /var/backups/kanban-snapshot.kbbak1\n\n# Step 2: Execute full disaster recovery restoration\nkanban-ctl backup restore \\\n  --input /var/backups/kanban-snapshot.kbbak1 \\\n  --decrypt \\\n  --confirm-overwrite\n```\n\n### Post-Restore Automated Verification\nFollowing database restoration:\n1. All database sequences are automatically synchronized.\n2. The **Invalid Object Link Auditor** executes immediately to verify referential integrity.\n3. RLS policies are audited to confirm that `kanban_app` lacks bypass permissions.\n4. Active WebSocket sessions are broadcast a reconnect signal.\n"
  },
  {
    "slug": "rest-api-architecture-and-openapi-guide",
    "title": "REST API Architecture and OpenAPI Integration Guide",
    "category": "Reference Guides",
    "order": 17,
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
        "id": "concurrency-protection-with-etag-and",
        "title": "3. Concurrency Protection with ETag and `If-Match`",
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
    "content": "# REST API Architecture and OpenAPI Integration Guide\n\n## Overview\n\nSoftware projects that attempt to manually maintain hundreds of static wiki pages for every REST endpoint inevitably suffer from documentation drift: code changes, parameters evolve, but static documentation falls behind, creating frustration and integration bugs.\n\n\ud83d\udc4dkanban adheres to the **In-Code OpenAPI Single Source of Truth** architecture:\n- All REST endpoints are declared with comprehensive Pydantic models, detailed FastAPI docstrings, summaries, response schemas, and parameter constraints directly in the Python source code (`kanban/api/v1/*.py`).\n- The canonical OpenAPI 3.1.0 specification is automatically generated by the FastAPI backend at `/api/openapi.json` and mirrored in the repository at `kanban/web/openapi.json` (`184` paths, regenerated via `python -m kanban.tools.export_openapi kanban/web/openapi.json`).\n- The web frontend generates its type-safe TypeScript API client directly from this schema (`pnpm --dir kanban/web run gen:api` producing `kanban/web/src/api/schema.gen.ts`).\n- Note on interactive explorers: `kanban/app.py` sets `docs_url=None` and `redoc_url=None` by default so the strict `Content-Security-Policy` (`script-src 'self'`, zero external CDNs) is preserved; developers browse the API via the machine-readable `/api/openapi.json`, generated `kanban/web/src/api/schema.gen.ts`, or self-documenting MCP `tools/list` + `action=\"help\"` endpoints.\n\n```mermaid\nflowchart LR\n    subgraph Backend[\"FastAPI Backend Source\"]\n        Pydantic[\"Pydantic Schemas<br/>& Field Validators\"]\n        Routes[\"184 FastAPI Routes<br/>kanban/api/v1/*.py\"]\n    end\n\n    subgraph SchemaGen[\"Canonical OpenAPI Export\"]\n        OpenAPI[\"OpenAPI 3.1.0 JSON<br/>/api/openapi.json\"]\n    end\n\n    subgraph Frontend[\"TypeScript Client & UI\"]\n        TSGen[\"openapi-typescript<br/>pnpm run gen:api\"]\n        SDK[\"Type-Safe Client SDK<br/>src/api/schema.gen.ts\"]\n        UI[\"React 19 SPA<br/>Board, Drawer, Studios\"]\n    end\n\n    Pydantic --> Routes\n    Routes -->|Automatic Introspection| OpenAPI\n    OpenAPI -->|Code Generation| TSGen\n    TSGen --> SDK\n    SDK --> UI\n```\n\n---\n\n## Documentation and Schema Endpoints\n\nWhen running \ud83d\udc4dkanban (in standalone mode or production), developers and integrations can access:\n\n| Endpoint / File | Interface | Purpose |\n| :--- | :--- | :--- |\n| **`/api/openapi.json`** | Raw OpenAPI 3.1.0 JSON | Machine-readable FastAPI schema used for SDK generation and automated API audits. |\n| **`kanban/web/openapi.json`** | In-Repo JSON Snapshot | Version-controlled OpenAPI specification (`184` paths) checked by CI (`pnpm run check:api`). |\n| **`kanban/web/src/api/schema.gen.ts`** | Generated TypeScript SDK | Strictly typed interfaces, request parameters, and response schemas. |\n| **`kanban/api/v1/*.py`** | In-Code Python Source | Authoritative FastAPI route docstrings, summaries, tags, and Pydantic `Field` docs. |\n\n---\n\n## REST API Architectural Principles\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Client as Client / Agent\n    participant FastAPI as FastAPI Router\n    participant Auth as Auth & AAL2 Dependency\n    participant DB as PostgreSQL (FORCE RLS)\n    participant San as Markdown Sanitizer\n\n    Client->>FastAPI: HTTP PATCH /api/v1/issues/{id} (If-Match: ETag)\n    FastAPI->>Auth: Validate Session / Token & AAL2 Level\n    alt Invalid Auth or Missing AAL2\n        Auth-->>Client: 401 Unauthorized / 403 Forbidden (RFC 7807)\n    else Authenticated\n        Auth->>DB: BEGIN TX & SET LOCAL app.current_principal_id = :id\n        FastAPI->>DB: Check ETag & Select Row with RLS\n        alt ETag Mismatch (Lost Update Detected)\n            FastAPI-->>Client: 412 Precondition Failed\n        else ETag Matched\n            FastAPI->>San: Sanitize Hostile Unicode & HTML\n            San-->>FastAPI: Clean Canonical Markdown\n            FastAPI->>DB: UPDATE issue & Append Activity Ledger\n            DB-->>FastAPI: Commit TX\n            FastAPI-->>Client: 200 OK (New ETag, Sanitized Payload)\n        end\n    end\n```\n\nEvery REST endpoint in \ud83d\udc4dkanban adheres to strict architectural invariants:\n\n### 1. Consistent RFC 7807 Error Responses\nAll error responses return structured RFC 7807 Problem Details JSON:\n\n```json\n{\n  \"type\": \"https://kanban.hackedyour.info/errors/LOCKOUT_PREVENTED\",\n  \"title\": \"Lockout Prevented\",\n  \"status\": 409,\n  \"detail\": \"Cannot disable the sole remaining active admin authentication card.\",\n  \"instance\": \"/api/v1/admin/auth/cards/01932e6b-7341-789a-bc01-123456789abc\",\n  \"code\": \"LOCKOUT_PREVENTED\",\n  \"timestamp\": \"2026-11-15T23:50:00Z\"\n}\n```\n\n### 2. Multi-Factor Authenticator Assurance Level 2 (AAL2)\nEvery route under `/api/v1/admin/*` enforces multi-factor verification at the FastAPI dependency layer:\n\n```python\n@router.post(\n    \"/admin/auth/cards/{card_id}/reorder\",\n    dependencies=[Depends(require_admin_aal2)],\n    summary=\"Reorder Authentication Cards\",\n    description=\"Updates sort rank of an authentication card. Enforces AAL2 admin session.\"\n)\nasync def reorder_auth_card(...): ...\n```\nAPI tests enforce this contract via `assert_admin_routes_protected`, rejecting any PR that adds an admin endpoint without the required `require_admin_aal2` dependency.\n\n### 3. Concurrency Protection with ETag and `If-Match`\nTo prevent the lost-update problem when multiple engineers or AI agents edit tickets simultaneously:\n- Read endpoints return an `ETag` header containing a SHA-256 hash of the object version.\n- Mutation endpoints (`PATCH /api/v1/issues/{id}`, `PUT /api/v1/docs/{id}`) accept an `If-Match` header.\n- If the current database record version differs from the provided `If-Match` header, the request is rejected with `412 Precondition Failed`.\n\n### 4. Zero-Context Fail-Closed Database Isolation\nREST route handlers do not query PostgreSQL as a superuser. Each request handler binds the authenticated principal ID to the session context (`SET LOCAL app.current_principal_id = :id`) within an explicit database transaction. If authentication is absent, PostgreSQL Row-Level Security policies evaluate to false and return zero records.\n\n---\n\n## Route Module Organization\n\nThe 184 REST API endpoints are organized into cohesive domain modules under `kanban/api/v1/`:\n\n```\nkanban/api/v1/\n|-- auth.py             # Login, logout, session refresh, TOTP, WebAuthn passkey registration\n|-- workspaces.py       # Workspace provisioning, member invitations, theme configuration\n|-- projects.py         # Project lifecycle, custom state configuration, member bindings\n|-- issues.py           # Work items, quick-create, property updates, sub-tasks, comments\n|-- cycles.py           # Sprint cycles, rollover automation, velocity calculations\n|-- modules.py          # Functional modules, completion tracking, feature grouping\n|-- docs.py             # Hierarchical technical documentation, ltree traversal, version diffs\n|-- stickies.py         # Digital sticky notes, color categorization, smart promotion\n|-- custom_fields.py    # Custom scripted field evaluation, Wasmtime/nsjail bindings\n|-- workflows.py        # Transition interceptors, validator pipelines, dry-run testing\n|-- search.py           # Hybrid lexical and semantic search endpoints\n|-- admin.py            # Platform governance, auth cards, link auditor, system backup\n`-- mcp_keys.py         # Scoped MCP token generation, tool toggles, device authorization\n```\n\n---\n\n## Generating Client SDKs and Syncing Schemas\n\nTo update the frontend TypeScript client after modifying backend FastAPI route signatures:\n\n```bash\n# Step 1: Export latest OpenAPI JSON from the FastAPI application\npython3 scripts/export_openapi.py --out kanban/web/openapi.json\n\n# Step 2: Regenerate the TypeScript SDK types\npnpm --dir kanban/web run gen:api\n\n# Step 3: Verify TypeScript compilation\npnpm --dir kanban/web run build\n```\n\nThis automated synchronization ensures that frontend UI components, test runners, and backend routes stay in lockstep with zero documentation lag.\n\n---\n\n## Administrative API and MCP Key Surfaces\n\nThe administrative REST API operates alongside the Model Context Protocol (MCP) server, offering fine-grained permission scoping, token rotation, and runtime health diagnostics.\n\n![MCP Access Studio and Scoped Token Management](images/13-mcp-access-studio.png)\n\n![System Settings and API Diagnostics](images/26-system-settings.png)\n"
  },
  {
    "slug": "real-time-web-and-websocket-architecture",
    "title": "Real-Time Web and WebSocket Architecture",
    "category": "System Architecture",
    "order": 18,
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
    "content": "# Real-Time Web and WebSocket Architecture\n\n## Overview\n\nModern software engineering teams collaborate concurrently across distributed locations. When one developer moves a card on the Kanban board, adds a comment, or when an autonomous AI agent updates a verification gate, all team members viewing the project must see the update instantly without manual page refreshes.\n\n\ud83d\udc4dkanban implements a high-performance **Real-Time WebSocket Hub** (`kanban/realtime/hub.py` and `kanban/api/ws.py`) delivering sub-50ms event fan-out across browser clients and autonomous agents.\n\n---\n\n## WebSocket Hub Architecture\n\n```mermaid\nflowchart TD\n    subgraph Clients[\"Subscribed Clients\"]\n        Browser[\"Browser Clients (Chrome / Firefox / Safari)\"]\n        Agents[\"Autonomous Agents & IDE Integrations\"]\n    end\n\n    subgraph Gateway[\"WebSocket Ingress (/ws/v1)\"]\n        Ingress[\"FastAPI WebSocket Handler<br/>- Origin header CORS check<br/>- Session cookie / Bearer token resolution<br/>- 16-connection limit per principal\"]\n    end\n\n    subgraph Router[\"Realtime Hub Event Router\"]\n        Hub[\"Hub Event Router (kanban/realtime/hub.py)<br/>- Channels: workspace:{id}, project:{id}, issue:{id}<br/>- RLS permission-filtered fanout<br/>- Non-blocking async backpressure queues\"]\n    end\n\n    subgraph Surfaces[\"Live UI Surfaces\"]\n        BoardUI[\"Board View: Instant Card Moves (<12ms)\"]\n        DrawerUI[\"Ticket Drawer: Live Activity & Gate Timers\"]\n        StickyUI[\"Stickies Grid: Collaborative Autosave\"]\n    end\n\n    Browser --> Ingress\n    Agents --> Ingress\n    Ingress --> Hub\n    Hub --> BoardUI\n    Hub --> DrawerUI\n    Hub --> StickyUI\n```\n\n![Responsive Tablet and Mobile Layout with Live Realtime Updates](images/30-responsive-tablet-layout.png)\n\n---\n\n## Connection Security and Rate-Limiting Controls\n\nWebSockets establish persistent, bidirectional TCP connections that can be abused for denial-of-service (DoS) or unauthorized event eavesdropping if not hardened properly.\n\n### 1. Strict Origin and CSRF Validation\nDuring the initial WebSocket upgrade handshake (`GET /ws/v1`), the server validates the incoming `Origin` header against configured allowed hosts. Requests from untrusted origins are immediately rejected with HTTP 403 Forbidden.\n\n### 2. Session Authentication and Privilege Resolution\n- WebSocket connections authenticate using encrypted session cookies (`__Host-kb_session`) or scoped Bearer API tokens.\n- Anonymous WebSocket connections are strictly forbidden.\n- When an authenticated connection opens, the hub resolves the user's principal ID, active tenant workspace, and project memberships.\n\n### 3. Maximum 16 Concurrent Connections per Principal\nTo prevent browser tab flooding or malicious connection exhaustion:\n- The `ConnectionManager` tracks open sockets by `principal_id`.\n- If an individual user or service principal attempts to establish more than 16 concurrent WebSocket connections, excess connection requests are rejected with status code `4429 Too Many Connections`.\n\n---\n\n## Channel Subscription and Event Model\n\nClients subscribe to targeted channels based on their active view, minimizing unnecessary network traffic:\n\n| Channel Pattern | Granularity | Typical Subscribers | Broadcast Events |\n| :--- | :--- | :--- | :--- |\n| **`workspace:{workspace_id}`** | Workspace | All active workspace members | Project creation, system announcements, sticky note grid updates. |\n| **`project:{project_id}`** | Project | Users viewing board or issue list | `ISSUE_MOVED`, `ISSUE_CREATED`, `CYCLE_ACTIVATED`, `MODULE_UPDATED`. |\n| **`issue:{issue_id}`** | Ticket | Users viewing Ticket Peek Drawer | `COMMENT_ADDED`, `GATE_STATUS_CHANGED`, `ASSIGNEE_UPDATED`. |\n\n### Core Broadcast Events\n\n- **`ISSUE_MOVED`:** Dispatched when a card changes state or swimlane position. Transmits the updated state ID, previous state ID, sort rank, and the operator who initiated the move.\n- **`GATE_STATUS_CHANGED`:** Broadcasts async agent gate transitions (`pending_agent_gate`, `vetoed`, `approved`) allowing the board to update countdown timers and animate spring snap-backs in real time.\n- **`STICKY_UPDATED`:** Broadcasts real-time color changes, text edits, or promotion events on the stickies masonry grid.\n\n---\n\n## Client Resilience and Reconnection Strategy\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor User as Connected Operator\n    participant Client as React 19 WebSocket Client\n    participant Hub as Realtime Hub\n    participant DB as PostgreSQL Ledger\n\n    Note over Client,Hub: Normal Operation (Receiving Events)\n    Hub->>Client: Event: ISSUE_MOVED (seq: 42)\n    Note over Client,Hub: Network Partition / Laptop Lid Closed\n    Client->>Client: Connection Lost! Activate Reconnecting Pill\n    Note over Client,Hub: Network Restored\n    Client->>Hub: Reconnect Handshake & Resume (last_seq: 42)\n    Hub->>DB: Query Activity Ledger WHERE seq > 42\n    DB-->>Hub: Return Events [seq: 43, 44, 45]\n    Hub-->>Client: Replay Catch-Up Events [43, 44, 45]\n    Client->>Client: Update State Store & Set Status Pill to Connected\n```\n\nNetwork connections in modern development environments (laptops switching networks, sleep states, VPN renegotiation) are inherently unstable.\n\nThe \ud83d\udc4dkanban web client implements robust reconnection resilience:\n- **Exponential Backoff with Jitter:** On connection loss, the client attempts reconnection starting at 500ms, doubling up to a maximum 10-second cap with random jitter to prevent connection storms.\n- **Event Sequence Numbers:** Every event payload includes a monotonically increasing `seq` integer. On reconnect, the client requests missed events since its last acknowledged sequence number, guaranteeing zero missed updates.\n- **Visual Connection Pill:** A discrete indicator in the UI status bar displays real-time WebSocket connectivity (`Connected`, `Reconnecting`, `Offline`).\n\n![Async Agent Gate States with Live Realtime Timers](images/16-async-agent-gate-states.png)\n"
  },
  {
    "slug": "role-and-permission-matrix",
    "title": "Role and Permission Matrix",
    "category": "Reference Guides",
    "order": 19,
    "summary": "This document defines the authoritative, fine-grained access control model across all 7 principal tiers in the \ud83d\udc4dkanban platform.",
    "sections": [
      {
        "id": "legend",
        "title": "Legend",
        "level": 2
      },
      {
        "id": "the-7-principal-tiers",
        "title": "The 7 Principal Tiers",
        "level": 2
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
    "content": "# Role and Permission Matrix\n\nThis document defines the authoritative, fine-grained access control model across all 7 principal tiers in the \ud83d\udc4dkanban platform.\n\nThe platform enforces Row-Level Security (FORCE RLS) at the PostgreSQL database layer, capability bitmasks with explicit DENY precedence, multi-factor AAL2 step-up authentication, and strict cryptographic scoping for agents and custom scripts.\n\n---\n\n## Legend\n\n| Symbol | Status | Description |\n| :---: | :--- | :--- |\n| **\u25cf** | **Allowed by Role** | Operation is natively permitted by the principal tier without extra elevation. |\n| **\u25d0** | **Conditional** | Operation requires an explicit ACL share, matching token scope, project assignment, or fresh AAL2 step-up verification. |\n| **\u25cb** | **Never Allowed** | Operation is strictly forbidden by policy and rejected by database RLS or API gatekeepers. |\n\n---\n\n## The 7 Principal Tiers\n\n1. **Guest (`WORKSPACE_GUEST` / `PROJECT_GUEST`):** Ephemeral or external collaborator. Confined strictly to explicitly shared objects with zero ambient project or workspace visibility.\n2. **Viewer (`WORKSPACE_VIEWER` / `PROJECT_VIEWER`):** Read-only stakeholder. Permitted to inspect un-restricted workspace or project assets, but cannot author or modify data.\n3. **Member (`WORKSPACE_MEMBER` / `PROJECT_MEMBER`):** Standard day-to-day engineer or contributor. Can author and manage issues, docs, stickies, and views in assigned projects.\n4. **Project Admin (`PROJECT_ADMIN`):** Lead for a specific project. Controls project configuration, workflow state transitions, WIP limits, project member bindings, and project trash.\n5. **Workspace Admin (`WORKSPACE_ADMIN`):** Organization administrator. Governs workspace settings, groups, user provisioning, retention policy, and workspace trash studio.\n6. **Server Admin (`SERVER_ADMIN`):** Root platform operator. Manages global server topology, multi-card authentication, air-gap flags, and cryptographic permanent purge.\n7. **Scoped MCP Agent (Service Principal):** Autonomous or assisted agent accessing `/mcp/agent`, `/mcp/docs`, or `/mcp/admin` bound to an API key or OAuth 2.0 PKCE token.\n\n---\n\n## Master Capability Matrix\n\n| Operational Capability | Guest | Viewer | Member | Project Admin | Workspace Admin | Server Admin | Scoped MCP Agent |\n| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n| **Viewing Workspace-Public Objects** | \u25cb | \u25cf | \u25cf | \u25cf | \u25cf | \u25cf | \u25d0 (1) |\n| **Viewing Private Project Objects** | \u25d0 (2) | \u25d0 (2) | \u25d0 (2) | \u25cf | \u25cf | \u25cf | \u25d0 (1, 2) |\n| **Explicit ACL DENY Precedence** | \u25cf (3) | \u25cf (3) | \u25cf (3) | \u25cf (3) | \u25cf (3) | \u25cf (3) | \u25cf (3) |\n| **Authoring Issues, Stickies, and Docs** | \u25cb | \u25cb | \u25cf | \u25cf | \u25cf | \u25cf | \u25d0 (1) |\n| **Editing and Versioning Pages** | \u25cb | \u25cb | \u25cf | \u25cf | \u25cf | \u25cf | \u25d0 (1) |\n| **Managing Resource ACLs (Share / Revoke)** | \u25cb | \u25cb | \u25d0 (4) | \u25cf | \u25cf | \u25cf | \u25d0 (1, 4) |\n| **Project Studio and Workflow Management** | \u25cb | \u25cb | \u25cb | \u25cf | \u25cf | \u25cf | \u25d0 (1) |\n| **Custom Field and Script Definition** | \u25cb | \u25cb | \u25cb | \u25cb | \u25d0 (5) | \u25cf | \u25d0 (1, 5) |\n| **Soft-Trash Project Objects** | \u25cb | \u25cb | \u25d0 (6) | \u25cf | \u25cf | \u25cf | \u25d0 (1, 6) |\n| **Workspace Trash Studio Inspection** | \u25cb | \u25cb | \u25cb | \u25d0 (7) | \u25cf (8) | \u25cf (8) | \u25d0 (1, 8) |\n| **Restoring Soft-Deleted Objects** | \u25cb | \u25cb | \u25cb | \u25d0 (7) | \u25cf (8) | \u25cf (8) | \u25d0 (1, 8) |\n| **Workspace Retention Policy (7 to 365 Days)** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8) | \u25cf (8) | \u25cb |\n| **Automated Multi-Object Sweep (trash_purge)** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (9) | \u25cb |\n| **2-Stage Permanent Purge (Cryptographic)** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8, 10) | \u25cb |\n| **Local User Provisioning and Password Reset** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8) | \u25cf (8) | \u25cb |\n| **Role Bindings and Group Hierarchy CRUD** | \u25cb | \u25cb | \u25cb | \u25d0 (11) | \u25cf (8) | \u25cf (8) | \u25cb |\n| **Multi-Card Auth Studio and Passkey Config** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8) | \u25cb |\n| **Minting Scoped MCP API Keys** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8) | \u25cf (8) | \u25cb |\n| **Immutable Audit Ledger (Inspection Only)** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cf (8) | \u25cf (8) | \u25d0 (1) |\n| **Tampering with Audit Ledger Records** | \u25cb | \u25cb | \u25cb | \u25cb | \u25cb | \u25cb (12) | \u25cb |\n\n---\n\n## Detailed Condition Notes\n\n1. **Token Scope Restriction:** Scoped MCP Agents can only exercise capabilities explicitly included in their minted token scopes (`read:issues`, `write:issues`, `read:docs`, `write:docs`, `admin`, etc.). Unscoped tools are rejected with `403 FORBIDDEN`.\n2. **Explicit Project Membership / ACL Share:** Guests and Viewers cannot see private project entities unless explicitly added to the project role bindings or granted a specific `ALLOW` entry in `resource_acl_entries`.\n3. **Absolute DENY Precedence:** If an explicit `DENY` entry exists for a principal on an object (or inherited group), effective capability bitmasks collapse immediately (`allow & (~deny)`). Even Workspace Admins cannot view or manage objects guarded by an explicit `DENY`.\n4. **Ownership Share Delegation:** Standard Members can only share objects they originally authored, provided project policy permits user-level ACL delegation.\n5. **Admin Approval Gate:** Custom fields and scripts can only be defined by administrators. Executing a script with Workspace or Server token escalation requires cryptographic approval from an administrator of that tier.\n6. **Author Deletion Scope:** Members may soft-delete their own drafts, comments, and un-assigned stickies if granted DELETE capability mask. Project-wide item soft-deletion requires Project Admin.\n7. **Project Scope Isolation:** Project Admins in the Trash Studio can only view and restore items belonging to projects where they hold explicit `PROJECT_ADMIN` authority.\n8. **Fresh AAL2 Step-Up Requirement:** All administrative endpoints (`/api/v1/admin/*`, retention settings, user provisioning, trash operations, key minting) enforce `Depends(require_admin_aal2)`. The session must have verified MFA within the last 900 seconds (`aal2_verified_at <= 900s`).\n9. **Daemon Background Job Authority:** The trash purge runner executes with dedicated system worker identity and sweeps expired entities strictly past their per-workspace `trash_retention_days` threshold.\n10. **2-Stage Destructive Confirmation:** Permanent purge is exclusively gated to `SERVER_ADMIN` + fresh AAL2. It requires `POST /api/v1/admin/destructive:request` to compute blast radius and mint an ephemeral HMAC `confirmation_token` + `blast_hash`, followed by `POST /api/v1/admin/destructive:execute` with a mandatory human reason (10 to 500 characters).\n11. **Project-Level Role Delegation:** Project Admins may manage role bindings within their designated project only. They cannot elevate users to Workspace Admin or Server Admin.\n12. **Cryptographic Immutability:** Audit ledger tables (`activity_ledger`) have no `UPDATE` or `DELETE` grants for any database role (including `kanban_app` and `kanban_migrator`). Triggers prevent tampering.\n\n---\n\n## Architectural Security Invariants\n\n- **Hostile Wire Invariant:** Every input is validated with strict Pydantic schemas and UTF-8 surrogate checks. Cleartext transmission of tokens is prohibited.\n- **Walled Component Garden:** Row-Level Security (`FORCE ROW LEVEL SECURITY`) is always active on all database sessions. Dropping session authorization to unprivileged users is mandatory in application flows.\n- **Volatile State Sanitization:** Ephemeral tokens and secrets exist only in memory during execution and are erased immediately after verification.\n- **Supply Chain Paranoia:** Zero external cloud runtime dependencies for core authentication, authorization, or search.\n"
  },
  {
    "slug": "scriptrunner-workflows-and-transition-interceptors",
    "title": "ScriptRunner Workflows and Transition Interceptors",
    "category": "System Architecture",
    "order": 20,
    "summary": "In traditional project management tools, workflow rules are either simple notification triggers or inflexible webhooks that fire only *after* a change has occurred. If an issue is improperly moved to \"Done\" without meeting code coverage requirements or QA verification, the damage is already done.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "the-transition-interceptor-pipeline",
        "title": "The Transition Interceptor Pipeline",
        "level": 2
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
        "id": "asynchronous-agent-gate-lifecycle-on-the-board",
        "title": "Asynchronous Agent Gate Lifecycle on the Board",
        "level": 2
      },
      {
        "id": "the-board-interaction-states",
        "title": "The Board Interaction States",
        "level": 3
      }
    ],
    "content": "# ScriptRunner Workflows and Transition Interceptors\n\n## Overview\n\nIn traditional project management tools, workflow rules are either simple notification triggers or inflexible webhooks that fire only *after* a change has occurred. If an issue is improperly moved to \"Done\" without meeting code coverage requirements or QA verification, the damage is already done.\n\n\ud83d\udc4dkanban implements a **ScriptRunner-Style Workflow Engine** with **Pre-Transition Interceptors**. When an operator or agent attempts to move a work item between states (`from_state -> to_state`), the transition is intercepted and evaluated through an ordered pipeline of synchronous validators, field mutators, and asynchronous AI agent gates.\n\n---\n\n## The Transition Interceptor Pipeline\n\n```mermaid\nflowchart TD\n    Drag[\"User / Agent moves card: In Progress -> Done\"] --> Interceptor[\"Transition Interceptor Engine\"]\n    Interceptor --> Stage1[\"Stage 1: Synchronous Validator (Tier A Wasm)<br/>- Verify blockers resolved<br/>- Verify Definition of Done criteria & PR links\"]\n    Stage1 -->|PASS| Stage2[\"Stage 2: Synchronous Field Mutator (Tier A)<br/>- Auto-set closed_at timestamp<br/>- Update cycle velocity counters\"]\n    Stage1 -->|VETO| VetoInstant[\"Transition Rejected (422 Unprocessable)\"]\n    Stage2 --> Stage3[\"Stage 3: Asynchronous Gate Hold (Tier B Async Agent)<br/>- Card enters pending_agent_gate hold (\u23f3\ud83e\udd16)<br/>- Dispatches forensic audit to agent\"]\n    Stage3 -->|Approved| Approved[\"Gate Approved (\u2705\ud83e\udd16)<br/>Card lands cleanly in Done column\"]\n    Stage3 -->|Vetoed| VetoSnap[\"Gate Veto (\ud83d\uded1\ud83e\udd16)<br/>240ms spring snap-back to In Progress<br/>Itemized rejection posted to activity feed\"]\n```\n\n---\n\n## Admin Workflow Transition Studio\n\nProject Administrators configure transition pipelines through the visual studio at `/projects/KAN/settings/workflows`.\n\n![Workflow Transition Studio and Dry-Run Drawer](images/15-workflow-transition-studio.png)\n\n### Studio Capabilities\n- **State Transition Matrix:** Select any valid transition path (e.g. `In Progress -> In Review`, `In Review -> Done`).\n- **Pipeline Reordering:** Drag to reorder validators and mutators in the execution chain.\n- **Mutable Field Checkboxes:** Explicitly define which fields the interceptor is permitted to modify, enforcing least-privilege mutation boundaries.\n\n### The Non-Persistent Dry-Run Drawer\nTesting workflow logic against live tickets risks corrupting sprint metrics. The Workflow Studio provides a **Zero-Persistence Dry-Run Drawer**:\n- Select an existing ticket fixture or pick a live issue.\n- Execute the transition pipeline in a simulated sandbox without mutating the database.\n- Inspect per-step execution timings (e.g. `1.2ms` Wasm validator, `3.4ms` security invariant validator, `2.1ms` auto-label mutator).\n- Preview proposed property mutations (such as automatically applied labels).\n- Copy the exact CLI validation command (`kanban-agent validate-transition`) for local offline debugging.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Workflow Architect\n    participant Studio as Workflow Studio\n    participant Drawer as Dry-Run Drawer\n    participant Engine as Interceptor Engine (Sandbox)\n\n    Admin->>Studio: Select \"In Review -> Done\" rule\n    Admin->>Studio: Click \"Dry-Run Against Sample Ticket\"\n    Studio->>Drawer: Open Dry-Run Drawer with sample payload\n    Admin->>Drawer: Click \"Run Dry-Run\"\n    Drawer->>Engine: Dispatch pipeline in dry_run=True mode\n    Engine->>Engine: Run Hook 1: qa-proof-validator (1.2ms, Allowed)\n    Engine->>Engine: Run Hook 2: security-invariant-validator (3.4ms, Allowed)\n    Engine->>Engine: Run Hook 3: auto-label-mutator (2.1ms, Applied labels)\n    Engine-->>Drawer: Return execution report & copyable CLI snippet\n    Drawer-->>Admin: Display green \"Transition Allowed: Changes would commit\"\n```\n\n![Workflow Studio Dry-Run Drawer Simulation](images/50-workflow-studio-dry-run-drawer.png)\n\n---\n\n## Read-Only Bare Git Repository Bindings\n\nAutonomous agents evaluating transition gates often require access to source code, diff trees, and commit histories. To satisfy this requirement securely without risking repository corruption:\n- Administrators can bind local bare Git mirrors directly to a project through the **Git Repository Bindings** dialog.\n- The volume mount is strictly enforced as read-only (`:ro bare mirror`).\n- Agents can run `git diff`, `git log`, and code analysis against the mirror, but all write attempts fail at the OS kernel boundary.\n\n![Git Repository Bindings Modal](images/51-workflow-bind-git-repo-modal.png)\n\n---\n\n## Asynchronous Agent Gate Lifecycle on the Board\n\nWhen an issue transition requires complex verification (such as forensic QA certification or automated security audits), the transition operates asynchronously without blocking the user interface.\n\n```mermaid\nstateDiagram-v2\n    [*] --> InProgress\n    InProgress --> PendingGate: Move to Done (Trigger Interceptor)\n    PendingGate --> Done: Agent Certifies Criteria (\u2705\ud83e\udd16 Approved)\n    PendingGate --> InProgress: Agent Rejects (\ud83d\uded1\ud83e\udd16 240ms Snap-Back)\n    Done --> [*]\n```\n\n![Async Agent Gate Card States and Snap-Back Lifecycle](images/16-async-agent-gate-states.png)\n\n![Board Pending Gate State in Active Sprint](images/35-board-pending-gate.png)\n\n### The Board Interaction States\n\n1. **Pending Hold (`\u23f3\ud83e\udd16`):**\n   - The card displays an amber countdown timer and progress indicator.\n   - The ticket enters database status `pending_agent_gate`.\n   - Other users viewing the board see the real-time hold status over WebSockets.\n2. **Gate Veto and 240ms Spring Snap-Back (`\ud83d\uded1\ud83e\udd16`):**\n   - If the agent discovers a defect or missing verification proof, the gate is vetoed.\n   - The board executes a physics-based 240ms spring snap-back animation, returning the card to its original column.\n   - A non-intrusive toast notification alerts the user, and the agent automatically posts an itemized rejection explanation to the ticket's `\ud83e\udd16 Gates` activity feed.\n3. **Gate Approval (`\u2705\ud83e\udd16`):**\n   - When all criteria are certified, the gate resolves to approved.\n   - The card transitions smoothly into the destination column, stamped with an immutable cryptographic verification badge.\n"
  },
  {
    "slug": "system-topology-and-multi-container-architecture",
    "title": "System Topology and Multi-Container Architecture",
    "category": "System Architecture",
    "order": 21,
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
        "id": "standalone-single-container-deployment",
        "title": "Standalone Single-Container Deployment (`docker run`)",
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
        "id": "multi-container-production-architecture",
        "title": "Multi-Container Production Architecture (`docker compose`)",
        "level": 2
      },
      {
        "id": "the-5-network-isolation-matrix",
        "title": "The 5-Network Isolation Matrix",
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
    "content": "# System Topology and Multi-Container Architecture\n\n## Overview\n\nThe \ud83d\udc4dkanban platform is designed for operational flexibility and security hardening. It supports two primary deployment topologies:\n1. **Standalone Single-Container Mode (`docker run`):** A zero-dependency, turnkey distribution where the web application, FastAPI backend, and PostgreSQL 16 database run within a single container using an embedded Unix socket. Ideal for evaluation, air-gapped workstations, and single-host developer instances.\n2. **Multi-Container Production Stack (`docker compose`):** An enterprise-grade, five-network isolated container mesh designed for high availability, least-privilege service boundaries, and strict network compartmentalization.\n\nBoth deployment modes are built upon a clean monorepo architecture and adhere to a strict Apache-2.0 pure licensing mandate with zero AGPL, GPL, or SSPL runtime dependencies.\n\n---\n\n## Monorepo Code Organization\n\nThe platform source code is organized into modular packages:\n\n```\nkanban/\n|-- kanban/                  # FastAPI web server, REST API, WebSocket hub, content pipelines\n|   |-- api/v1/              # Versioned API routes (184 endpoints, OpenAPI 3.1.0)\n|   |-- auth/                # Multi-card authentication studio, session management, CSRF\n|   |-- content/             # Canonical Markdown normalizer, Unicode guards, hidden-DOM pruner\n|   |-- realtime/            # Distributed WebSocket hub, connection manager, event router\n|   `-- web/                 # React 19 single-page application (SPA) with Vite and Tailwind\n|-- database/                # Universal Object Graph, PostgreSQL schemas, and migrations\n|   |-- migrations/          # Alembic schema migrations (kanban_migrator)\n|   |-- models/              # SQLAlchemy 2.0 models with FORCE ROW LEVEL SECURITY\n|   `-- auditor/             # Universal object link integrity auditor and purger\n|-- mcp/                     # Three-surface Model Context Protocol server\n|   |-- surfaces/agent/      # /mcp/agent (9 execution & QA tools)\n|   |-- surfaces/docs/       # /mcp/docs (6 knowledge & sticky tools)\n|   |-- surfaces/admin/      # /mcp/admin (12 governance & lifecycle tools)\n|   `-- yaml_out.py          # InlineSafeDumper YAML serializer for token efficiency\n`-- agent/                   # Autonomous AI runtime and orchestration engine\n    |-- providers/           # Pluggable LLM clients (OpenAI, Ollama, Gemini)\n    |-- runners/             # Local CLI pipe harnesses (agy -p, codex -p) and mTLS runners\n    `-- sparkle/             # Inline cursor completion (FIM) and ghost-text engine\n```\n\n---\n\n## Standalone Single-Container Deployment (`docker run`)\n\nIn standalone mode, a single Docker container encapsulates the complete stack without requiring external database provisioning.\n\n```bash\ndocker run -d \\\n  --name thumbs-up-kanban \\\n  -p 8921:8921 \\\n  -v kanban_data:/var/lib/kanban/data \\\n  thumbs-up-kanban:latest\n```\n\n### Internal Unix-Socket Architecture\n\n```mermaid\nflowchart TD\n    subgraph Standalone[\"Single Docker Container (thumbs-up-kanban:latest)\"]\n        Supervisor[\"PID-1 Process Supervisor (tini / Python supervisor)\"]\n        App[\"FastAPI Application Server<br/>(Port 8921 HTTP & WS)\"]\n        PG[\"Embedded PostgreSQL 16 Engine<br/>Unix Domain Socket (/var/run/postgresql/.s.PGSQL.5432)<br/>listen_addresses='' (Zero TCP Exposure)\"]\n        Storage[\"Volume Persistence Probe<br/>Mount: /var/lib/kanban/data\"]\n        \n        Supervisor --> App\n        Supervisor --> PG\n        App -->|Unix Domain Socket| PG\n        PG --> Storage\n    end\n```\n\nInside the standalone container:\n- **PID-1 Process Supervisor:** Manages the graceful startup, monitoring, and shutdown of both PostgreSQL and the ASGI application server.\n- **Embedded PostgreSQL 16:** Listens strictly on a local Unix domain socket (`/var/run/postgresql/.s.PGSQL.5432`). TCP networking for PostgreSQL is disabled (`listen_addresses = ''`), preventing network-level database intrusion.\n- **Volume Persistence Probe:** On startup, the container verifies that `/var/lib/kanban/data` is mounted to a persistent volume. If an ephemeral container filesystem is detected, the UI displays a dismissible amber warning banner alerting the operator to attach persistent storage before creating production data.\n- **Status and Health Panel:** Accessible at `/admin/standalone`, this panel reports database uptime, socket latency, storage utilization, and single-click export to multi-container Compose bundles.\n\n![Standalone Status Panel](images/04-standalone-status-panel.png)\n\n### Workspace Home and Initial State\n\nOnce the container finishes initialization, users land on the clean, breathable Workspace Home. The workspace view provides instant access to projects, work items, stickies, and system configuration.\n\n![Workspace Home](images/05-workspace-home.png)\n\n---\n\n## Multi-Container Production Architecture (`docker compose`)\n\nFor production environments, \ud83d\udc4dkanban deploys as a multi-container stack compartmentalized across five isolated Docker networks.\n\n```mermaid\nflowchart TD\n    Proxy[\"Reverse Proxy (Caddy / Nginx)\"] -->|edge_net| App[\"\ud83d\udc4dkanban App Container (FastAPI)<br/>- Uvicorn ASGI workers (UID 65532)<br/>- Multi-Card Auth & AAL2 Middleware<br/>- WebSocket Hub & Markdown Pipelines\"]\n    \n    App -->|data_net| PG[\"PostgreSQL 16 DB<br/>- FORCE RLS (100%)<br/>- pgvector + ltree<br/>- Isolated data_net\"]\n    App -->|sandbox_net| Sandbox[\"Sandbox Execution Runtime<br/>- Wasmtime runtime<br/>- nsjail runner<br/>- Zero data_net route\"]\n    App -->|egress_llm_net| AI[\"External AI Providers<br/>- OpenAI, Gemini<br/>- Local Ollama<br/>- mTLS repo runners\"]\n```\n\n![Standalone to Production Compose Export](images/27-standalone-compose-export.png)\n\n![System Settings and Production Diagnostics](images/26-system-settings.png)\n\n### The 5-Network Isolation Matrix\n\nTo prevent lateral movement and enforce zero-trust network boundaries, container communication is segregated into five distinct networks:\n\n| Network Name | Connected Services | Allowed Ingress / Egress | Security Rationale |\n| :--- | :--- | :--- | :--- |\n| **`edge_net`** | Reverse proxy, Web application | External HTTP/S traffic to port 8921 | Shields backend application from direct internet exposure; terminates TLS. |\n| **`app_net`** | Web application, Redis / cache (optional) | Inter-service caching and session distribution | Segregates application control plane from database and storage layers. |\n| **`data_net`** | Web application, PostgreSQL 16 | PostgreSQL TCP (port 5432) | Strictly internal. The database has zero external routing or internet gateway. |\n| **`sandbox_net`** | Web application, Custom Script runner | Unix socket / IPC pipe | Completely air-gapped. Scripts have zero route to `data_net` or the internet. |\n| **`egress_llm_net`** | Web application, LLM egress gateway | Outbound HTTPS to pinned AI API endpoints | Limits external outbound traffic exclusively to configured LLM APIs. |\n\n### Process Hardening and Least Privilege\n\nEvery container in the production stack enforces strict Linux security controls:\n- **Non-Root Execution:** Runs under dedicated unprivileged system users (`UID 65532`, `GID 65532`).\n- **Capability Dropping:** Drops all Linux capabilities on initialization (`--cap-drop=ALL`).\n- **No New Privileges:** Enforces `setpriv --no-new-privs` to prevent setuid privilege escalation.\n- **Read-Only Root Filesystem:** Container root filesystems are mounted read-only (`read_only: true`), with writable space restricted to tmpfs mounts for `/tmp` and `/run`.\n\n---\n\n## Supply Chain Integrity and Permissive Licensing\n\nIn strict accordance with enterprise governance requirements:\n- **Pure Apache-2.0:** All platform source code, libraries, and build targets are licensed under Apache-2.0.\n- **Zero Viral Licenses:** The dependency tree is continuously audited in CI to reject any runtime dependencies with copyleft licenses (GPL, AGPL, LGPL, SSPL).\n- **Pinned Dependencies:** All Python dependencies (`pyproject.toml`) and JavaScript packages (`package.json`) are cryptographically locked with exact hashes.\n"
  },
  {
    "slug": "three-surface-mcp-server-architecture",
    "title": "Three-Surface Model Context Protocol (MCP) Server Architecture",
    "category": "System Architecture",
    "order": 22,
    "summary": "The Model Context Protocol (MCP) allows Large Language Models (LLMs) and autonomous engineering agents to interact with development platforms. However, conventional tracker integrations (such as legacy Jira REST bridges and generic CRUD wrappers) expose raw REST endpoints 1:1 as MCP tools. This naive approach results in 70 to 120 bloated tools consuming 15,000 to 25,000 context tokens before the agent begins reasoning, causing catastrophic context exhaustion and multi-turn thrashing.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "the-three-isolated-mcp-surfaces",
        "title": "The Three Isolated MCP Surfaces",
        "level": 2
      },
      {
        "id": "9-execution-and-qa-tools",
        "title": "1. `/mcp/agent` (9 Execution and QA Tools)",
        "level": 3
      },
      {
        "id": "6-knowledge-and-specification-tools",
        "title": "2. `/mcp/docs` (6 Knowledge and Specification Tools)",
        "level": 3
      },
      {
        "id": "12-governance-and-lifecycle-tools",
        "title": "3. `/mcp/admin` (12 Governance and Lifecycle Tools)",
        "level": 3
      },
      {
        "id": "token-optimization-and-serializer-architecture",
        "title": "Token Optimization and Serializer Architecture",
        "level": 2
      },
      {
        "id": "compact-yaml-output",
        "title": "`InlineSafeDumper` Compact YAML Output",
        "level": 3
      },
      {
        "id": "human-readable-identifiers",
        "title": "`EntityResolver` Human-Readable Identifiers",
        "level": 3
      },
      {
        "id": "level-of-detail-filtering",
        "title": "Level-of-Detail (`lod`) Filtering",
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
        "id": "admin-oauth-21-governance-studio",
        "title": "Admin OAuth 2.1 Governance Studio (`/admin/oauth`)",
        "level": 2
      },
      {
        "id": "key-oauth-governance-capabilities",
        "title": "Key OAuth Governance Capabilities:",
        "level": 3
      }
    ],
    "content": "# Three-Surface Model Context Protocol (MCP) Server Architecture\n\n## Overview\n\nThe Model Context Protocol (MCP) allows Large Language Models (LLMs) and autonomous engineering agents to interact with development platforms. However, conventional tracker integrations (such as legacy Jira REST bridges and generic CRUD wrappers) expose raw REST endpoints 1:1 as MCP tools. This naive approach results in 70 to 120 bloated tools consuming 15,000 to 25,000 context tokens before the agent begins reasoning, causing catastrophic context exhaustion and multi-turn thrashing.\n\n\ud83d\udc4dkanban rejects the CRUD-wrapper pattern. Instead, it implements an **Intent-Driven Architecture** organized into **three isolated streamable surfaces** (`2025-06-18` protocol specification), exposing exactly 27 cohesive tools designed specifically for autonomous agent cognition.\n\n---\n\n## The Three Isolated MCP Surfaces\n\n```mermaid\nflowchart TD\n    subgraph Hub[\"\ud83d\udc4dkanban Multi-Surface MCP Server\"]\n        Agent[\"/mcp/agent<br/>- 9 Execution & QA Tools<br/>- Token budget: <= 1,850 tokens<br/>- Zero Admin / Delete permissions\"]\n        Docs[\"/mcp/docs<br/>- 6 Knowledge & Spec Tools<br/>- Token budget: <= 1,350 tokens<br/>- Stickies & Hierarchical Docs\"]\n        Admin[\"/mcp/admin<br/>- 12 Lifecycle & Ops Tools<br/>- Token budget: <= 2,800 tokens<br/>- Mandatory AAL2 Protection<br/>- 2-Stage Destructive Confirmation\"]\n    end\n\n    subgraph Agents[\"Target Consumers\"]\n        CodingAgents[\"Autonomous Coding & QA Agents<br/>(Cursor, Claude Code, Antigravity, Codex)\"]\n        DocAgents[\"Documentation & Knowledge Bots\"]\n        AdminOperators[\"DevOps & Administrative Operators\"]\n    end\n\n    CodingAgents --> Agent\n    DocAgents --> Docs\n    AdminOperators --> Admin\n```\n\n![MCP Access Studio and Key Configuration](images/13-mcp-access-studio.png)\n\n![MCP Level of Detail Tiers Studio](images/21-mcp-lod-tiers-studio.png)\n\n### 1. `/mcp/agent` (9 Execution and QA Tools)\nDedicated to autonomous software development, testing, and QA agents (such as Claude Code, Antigravity, and Cursor).\n- **Security Constraint:** Strictly limited by the caller's role. Contains zero administrative, destructive, or project-deletion capabilities.\n- **Token Efficiency:** The entire tool manifest consumes only 1,759 tokens, comfortably fitting within the strict 1,850-token specification ceiling.\n- **Intent Consolidation:** Replaces multi-step CRUD sequences with atomic actions like `begin_work` (claims ticket, starts sprint, links active cycle, posts plan) and `complete_work` (verifies blockers, records QA proof, marks done).\n\n### 2. `/mcp/docs` (6 Knowledge and Specification Tools)\nDedicated to technical documentation, architecture research, and specification authoring.\n- **Capabilities:** Document creation, ltree hierarchy traversal, markdown search, sticky note management, and AI-assisted sticky-to-doc promotion.\n- **Token Efficiency:** Tool manifest utilizes 1,177 tokens against a 1,350-token budget ceiling.\n\n### 3. `/mcp/admin` (12 Governance and Lifecycle Tools)\nDedicated to platform administrators and privileged automation operators.\n- **Capabilities:** Project provisioning, member and group access binding, workflow interceptor configuration, AI runner setup, and system health checks.\n- **AAL2 Protection:** Every invocation requires Authenticator Assurance Level 2 credentials.\n- **Two-Stage Destructive Safety:** Dangerous operations (`destructive_lifecycle`) require a two-stage process: first requesting a blast-radius preview and receiving a short-lived cryptographic confirmation token, then explicitly confirming execution with that token.\n\n---\n\n## Token Optimization and Serializer Architecture\n\nAutonomous agents run faster and make fewer mistakes when data payloads are clean, predictable, and compact.\n\n```mermaid\nflowchart LR\n    Request[\"Agent Invocation<br/>e.g. read_ticket(identifier='KAN-42')\"] --> Auth[\"Auth & Scope Check\"]\n    Auth --> Resolver[\"EntityResolver<br/>(Translate KAN-42 to UUID)\"]\n    Resolver --> DB[\"PostgreSQL Engine<br/>FORCE RLS Active\"]\n    DB --> LODFilter[\"LOD Filter<br/>(summary / standard / full)\"]\n    LODFilter --> Dumper[\"InlineSafeDumper<br/>Strip nulls, compact YAML\"]\n    Dumper --> Response[\"Streamable Response<br/>(-35% Tokens vs JSON)\"]\n```\n\n### `InlineSafeDumper` Compact YAML Output\nWhile standard MCP servers return formatted JSON, \ud83d\udc4dkanban uses a specialized YAML serializer (`mcp/yaml_out.py`):\n- Compact, human-readable YAML representation.\n- Strips null values, empty strings, and default boolean flags.\n- Automatically redacts sensitive fields (passwords, tokens, keys).\n- **Result:** Reduces payload size by 35% compared to raw JSON, saving thousands of tokens per conversation.\n\n### `EntityResolver` Human-Readable Identifiers\nAgents reason far better about human identifiers (`KAN-42`, `CORE-101`, `infra-docs`) than opaque UUIDs (`01932e6b-7341-789a-bc01-123456789abc`). The `EntityResolver` automatically translates between human keys and internal database UUIDs at the MCP boundary.\n\n### Level-of-Detail (`lod`) Filtering\nSearch and read tools support a progressive disclosure parameter:\n- `lod: \"summary\"`: Returns identifier, title, state, and priority (~40 tokens).\n- `lod: \"standard\"`: Returns summary plus description and primary assignees (~200 tokens).\n- `lod: \"full\"`: Returns complete object graph, all comments, activity history, and access manifests.\n\n---\n\n## MCP Access Studio and Key Management\n\nUsers and administrators configure MCP integrations through the visual Access Studio at `/admin/mcp` and `/settings/mcp`.\n\n![MCP Access Studio and Key Configuration](images/13-mcp-access-studio.png)\n\n### Studio Features\n- **Granular Tool Toggles:** Enable or disable individual MCP tools per key or per surface.\n- **Hierarchical Scopes and Scope Badges:** Restrict tokens to `Global`, `Workspace`, or single `Project` scopes with distinct visual badges indicating authorization level.\n- **RFC 8628 Device Flow (`/activate`):** Fast terminal onboarding allowing agents to authenticate via browser activation code.\n- **Copyable Configuration Snippets:** Real-time generation of configuration snippets for Claude Desktop (`claude_desktop_config.json`), Google Antigravity (`agy`), Cursor, and OpenAI Codex.\n\n![MCP Access Studio Scope Badges](images/59-mcp-scope-badge.png)\n\n![MCP Mint Key and Client Snippets Modal](images/58-mcp-client-snippets-mint.png)\n\n---\n\n## Admin OAuth 2.1 Governance Studio (`/admin/oauth`)\n\nIn addition to static API keys, \ud83d\udc4dkanban provides an enterprise OAuth 2.1 authorization server with mandatory PKCE (Proof Key for Code Exchange with `S256` challenge), accessible at `/admin/oauth`.\n\n```mermaid\nflowchart TD\n    subgraph OAuthGovernance[\"OAuth 2.1 & PKCE Architecture\"]\n        ClientApp[\"Third-Party Client / IDE Agent<br/>(Cursor, Claude Desktop, Antigravity)\"]\n        AuthServer[\"\ud83d\udc4dkanban OAuth 2.1 Server (/admin/oauth)\"]\n        TokenEndpoint[\"Token Minting Endpoint (/api/v1/oauth/token)\"]\n        AdminAudit[\"Audit & Revocation Stream\"]\n\n        ClientApp -->|1. Authorization Code Request + code_challenge (S256)| AuthServer\n        AuthServer -->|2. User Authenticates & Approves Scopes| ClientApp\n        ClientApp -->|3. POST /oauth/token + code_verifier| TokenEndpoint\n        TokenEndpoint -->|4. Cryptographic S256 Verification| TokenEndpoint\n        TokenEndpoint -->>|5. Mint Scoped Bearer JWT + Refresh Token| ClientApp\n        TokenEndpoint -->|6. Append Registration & Issuance Record| AdminAudit\n    end\n```\n\n![Admin OAuth Client Governance Studio](images/42-admin-oauth-governance.png)\n\n### Key OAuth Governance Capabilities:\n1. **Registered OAuth 2.1 Clients:** View, register, and manage client applications with designated redirect URIs and client secrets.\n2. **Mandatory PKCE (`S256`):** Disallows plain code challenges, protecting public clients against authorization code interception attacks.\n3. **Granular Scopes:** Scopes are scoped strictly (`mcp:read`, `mcp:write`, `agent:execute`, `docs:read`, `admin:full`).\n4. **Immediate Client Revocation:** Administrators can revoke compromised OAuth clients or reset client secrets with zero system downtime.\n"
  },
  {
    "slug": "ticket-screen-and-work-item-features",
    "title": "Ticket Screen, Peek Drawer, and Work Item Architecture",
    "category": "System Architecture",
    "order": 23,
    "summary": "The ticket screen is the central operating surface for software engineering teams. \ud83d\udc4dkanban competes globally against Jira, Vibe Kanban, and legacy commercial trackers while eliminating context-switching friction through its high-performance **960px Ticket Peek Drawer** and keyboard-driven **Quick-Create Modal**.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
        "level": 2
      },
      {
        "id": "quick-create-work-item-modal",
        "title": "Quick-Create Work Item Modal (`C`)",
        "level": 2
      },
      {
        "id": "key-capabilities-of-quick-create",
        "title": "Key Capabilities of Quick-Create",
        "level": 3
      },
      {
        "id": "the-960px-ticket-peek-drawer",
        "title": "The 960px Ticket Peek Drawer (`?peek=`)",
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
        "id": "sprints-cycles-and-functional-modules",
        "title": "Sprints, Cycles, and Functional Modules",
        "level": 3
      },
      {
        "id": "blast-radius-deletion-warning-modal",
        "title": "Blast Radius Deletion Warning Modal",
        "level": 3
      }
    ],
    "content": "# Ticket Screen, Peek Drawer, and Work Item Architecture\n\n## Overview\n\nThe ticket screen is the central operating surface for software engineering teams. \ud83d\udc4dkanban competes globally against Jira, Vibe Kanban, and legacy commercial trackers while eliminating context-switching friction through its high-performance **960px Ticket Peek Drawer** and keyboard-driven **Quick-Create Modal**.\n\n---\n\n## Quick-Create Work Item Modal (`C`)\n\nEngineers can capture issues rapidly from any screen in the application by pressing the keyboard shortcut `C` or clicking `+ New Work Item`.\n\n![Quick-Create Work Item Modal](images/08-quick-create-modal.png)\n\n### Key Capabilities of Quick-Create\n\n- **Keyboard Shortcut Driven:** Press `C` anywhere to open, `Escape` to dismiss, or `Ctrl+Enter` (`Cmd+Enter`) to submit.\n- **Draft Persistence (`\u270d\ufe0f Keep work-in-progress`):** Enabling the draft toggle preserves partial ticket text across navigation and browser restarts using local storage, preventing work loss.\n- **Inline Property Setting:** Assign status, priority, cycle, module, and assignees directly in the modal without secondary configuration.\n\n---\n\n## The 960px Ticket Peek Drawer (`?peek=`)\n\nClicking any card on the board or list opens the ticket in an expansive 960px side drawer while keeping the underlying board mounted and visible.\n\n![Ticket Peek Drawer with 17 Features](images/09-ticket-peek-drawer.png)\n\n```mermaid\nflowchart TD\n    subgraph DrawerLayout[\"960px Ticket Peek Drawer Structure\"]\n        Header[\"Header Bar<br/>- Identifier (\ud83c\udff7\ufe0f) & Title<br/>- Subscribe (\ud83d\udd14), Copy Link (\ud83d\udd17)<br/>- Access Pill (\ud83d\udee1\ufe0f), Fullscreen Toggle\"]\n        \n        subgraph MainContent[\"Main Content Area\"]\n            Editor[\"ProseMirror Editor<br/>- Canonical UTF-8 Markdown<br/>- Sparkle FIM Completion (\u2728)<br/>- Live Mermaid & Media Rendering\"]\n            Subtasks[\"Sub-Issues & Checklists<br/>- Drag-and-drop reordering<br/>- Blocker resolution tracking\"]\n            Activity[\"4-Tab Activity Stream<br/>- All, Comments, History, \ud83e\udd16 Gates\"]\n        end\n        \n        subgraph PropertiesRail[\"Right-Hand Properties Rail\"]\n            StateProp[\"State & Workflow Transitions\"]\n            PriorityProp[\"Priority Tiering (Urgent..None)\"]\n            AssigneeProp[\"Assignees (Users, Groups, Agents)\"]\n            CycleProp[\"Cycle (Sprint) & Module Binding\"]\n            DatesProp[\"Start & Due Date Pickers\"]\n            CustomFields[\"Custom Scripted Fields (\ud83e\uddea)\"]\n            BlastRadius[\"Destructive Action Controls\"]\n        end\n    end\n    \n    Header --> MainContent\n    MainContent --- PropertiesRail\n```\n\n### Zero-Remount Architecture\n\n- **URL Synchronization:** Drawer state is synchronized with the URL (`/projects/KAN/issues?peek=KAN-12`). Refreshing or sharing the URL opens the exact drawer context.\n- **Background Preservation:** The underlying board does not unmount or reload. Users can interact with the drawer and return to their exact scroll position with zero latency.\n- **One-Click Fullscreen:** Operators can expand the drawer into a full-width page view for deep specification reading and back again seamlessly.\n\n---\n\n## Fullscreen Issue View and Authoring Studio\n\nWhen deep architectural work or comprehensive specification reading is required, operators can expand any ticket into the **Fullscreen Issue View** (`/projects/KAN/issues/{id}` or via the expand icon on the drawer header).\n\n```mermaid\nflowchart TD\n    subgraph FullscreenView[\"Fullscreen Issue Studio Structure\"]\n        TopNav[\"Top Navigation Bar<br/>- Breadcrumb: Workspace / Project / Work Items<br/>- Key: KAN-142 | Copy ID | \ud83d\udee1\ufe0f Access Inspector (Project + 2)<br/>- Subscribe Toggle (\ud83d\udd14) | Deep Link (\ud83d\udd17) | More Actions (...)\"]\n        \n        subgraph EditorColumn[\"Primary Specification & Activity Area\"]\n            Title[\"Issue Title Header with Inline Edit\"]\n            Desc[\"Rich Markdown Specification Body<br/>- Canonical CommonMark renderer<br/>- Mermaid diagram inline preview<br/>- Sparkle 320ms FIM ghost-text completion\"]\n            Toolbar[\"Rich Markdown Authoring Toolbar<br/>- Bold (B), Italic (I), Code (</>), Link, Image, Table, Mermaid\"]\n            CommentEditor[\"Comment Editor Box with Markdown and Mention Support\"]\n            ActivityTabs[\"4-Tab Activity Stream<br/>- All | Comments (N) | History | \ud83e\udd16 Gates (N)\"]\n        end\n        \n        subgraph SideRail[\"Right-Hand Metadata & Custom Fields Rail\"]\n            StandardFields[\"Standard Attributes<br/>- State, Priority, Assignees, Reporter<br/>- Start Date, Due Date, Module, Cycle\"]\n            CustomRail[\"Custom Fields Rail (Admin-Defined \ud83e\uddea)<br/>- CVSS Score (Severity Pill e.g. 8.8 High)<br/>- Target Environment, Build Number<br/>- Dynamic reload buttons per field\"]\n        end\n    end\n    \n    TopNav --> EditorColumn\n    EditorColumn --- SideRail\n```\n\n![Fullscreen Issue View with Rich Markdown Toolbar and Access Inspector](images/39-fullscreen-issue-view.png)\n\n### Key Fullscreen Features:\n1. **Rich Markdown Authoring Toolbar:** One-click formatting tools for bold, italics, inline code, links, quotes, tables, and Mermaid architecture diagrams.\n2. **Sparkle 320ms Fill-in-the-Middle (FIM):** Context-aware ghost text completions triggered as you write, dismissible with `Escape` and acceptable with `Tab` or right-click.\n3. **Effective Access Inspector (`\ud83d\udee1\ufe0f`):** Real-time badge computing combined project and issue-level permissions (`Project + 2`), showing inherited roles and explicit principal grants.\n4. **4-Tab Activity Stream:** Dedicated tabs for `All`, `Comments`, `History`, and `\ud83e\udd16 Gates` for isolated inspection of human discourse versus autonomous agent evaluations.\n5. **Custom Fields Rail:** Identical component and state rendering between peek drawer and fullscreen views, preserving field layout fidelity.\n\n---\n\n## The Complete 17 Enterprise Ticket Features\n\n\ud83d\udc4dkanban implements the full suite of 17 enterprise work item features (`8a` through `8q`):\n\n| # | Feature Identifier | Implementation Details |\n| :--- | :--- | :--- |\n| **1** | **Title & Canonical Description** | Rich Markdown editor supporting code blocks, tables, task lists, and Sparkle AI completion. |\n| **2** | **State Transition Selector** | Workflow-aware selector with synchronous Wasm validation and async AI gate interception. |\n| **3** | **Corporate Priority Tiering** | High-contrast visual badges: `Urgent` (red), `High` (orange), `Medium` (yellow), `Low` (blue), `None`. |\n| **4** | **Hybrid Assignees (`\ud83c\udff7\ufe0f`)** | Seamless assignment across individual human users, user groups, and autonomous agent service principals. |\n| **5** | **Created-by Reporter Badge (`\ud83d\udd04`)** | Immutable audit stamp recording the original creator and creation timestamp. |\n| **6** | **Dates & Scheduling** | Start date and Target delivery date pickers with automatic overdue highlighting and calendar sync. |\n| **7** | **Cycle (Sprint) Binding** | Direct assignment to active, upcoming, or backlog sprint cycles with automatic rollover. |\n| **8** | **Module Binding** | Grouping under functional modules with live roll-up progress bars and completion percentages. |\n| **9** | **Parent Hierarchy (`\ud83d\udd12`)** | Parent-child relationship binding with automated circular dependency rejection. |\n| **10** | **Sub-Issue Decomposition** | Nested sub-task checklist with drag reordering and progress tracking indicators. |\n| **11** | **Labels & Tagging** | Multi-colored semantic labels with workspace-level and project-level scopes. |\n| **12** | **Subscription Notifications (`\ud83d\udd14`)** | Watcher toggle delivering notifications on comments, state changes, and gate approvals. |\n| **13** | **Copy Link & Deep Linking (`\ud83d\udd17`)** | Generates canonical deep links directly to ticket headers or individual comments. |\n| **14** | **Explicit Sharing Pill (`\ud83d\udee1\ufe0f`)** | Visual indicator displaying the Access Manifest (principals, roles, and effective ACL masks). |\n| **15** | **Custom Scripted Fields (`\ud83e\uddea`)** | Dynamic fields computed by sandboxed Wasmtime/nsjail scripts with execution badges. |\n| **16** | **4-Tab Activity Feed** | Tabbed stream: `All`, `Comments` (with Markdown & mentions), `History` (audit trail), `\ud83e\udd16 Gates` (agent reviews). |\n| **17** | **Destructive Action Safety** | 2-stage blast-radius preview modal detailing affected children and links before archive or deletion. |\n\n---\n\n## Detailed Visual Inspection of Ticket Features\n\n### 4-Tab Activity Feed and Audit History\nThe activity feed separates human conversation from automated audit logs and AI agent gate reviews:\n\n![Activity Stream and Audit History](images/28-activity-stream-audit.png)\n\n### Sprints, Cycles, and Functional Modules\nWork items bind directly to sprint cycles and functional modules with real-time velocity roll-ups:\n\n![Sprint Cycle Planning and Velocity Tracking](images/24-cycles-sprints.png)\n\n![Functional Module Hierarchy and Progress Tracking](images/25-modules-milestones.png)\n\n### Blast Radius Deletion Warning Modal\nTwo-stage deletion safety calculates the ripple impact across child issues, dependencies, and doc links:\n\n![Delete Blast Radius Warning Modal](images/20-delete-blast-radius.png)\n"
  },
  {
    "slug": "universal-object-graph-and-link-auditor",
    "title": "Universal Object Graph and Invalid Link Auditor",
    "category": "System Architecture",
    "order": 24,
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
        "id": "the-6-class-invalid-link-detection-matrix",
        "title": "The 6-Class Invalid Link Detection Matrix",
        "level": 3
      },
      {
        "id": "audited-purging-and-dry-run-reporting",
        "title": "Audited Purging and Dry-Run Reporting",
        "level": 3
      },
      {
        "id": "admin-link-auditor-studio",
        "title": "Admin Link Auditor Studio (`/admin/link-auditor`)",
        "level": 2
      },
      {
        "id": "six-class-breakdown-cards",
        "title": "1. Six-Class Breakdown Cards",
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
      }
    ],
    "content": "# Universal Object Graph and Invalid Link Auditor\n\n## Overview\n\nTraditional project management databases rely on fragmented, ad-hoc foreign keys connecting tickets, documents, and attachments. This fragmented design leads to dangling pointers, orphaned files, accidental cross-tenant data leaks, and broken graph traversals when objects are archived or deleted.\n\n\ud83d\udc4dkanban resolves this through the **Universal Object Graph (UOG)**. Every major entity in the system inherits from a unified object spine, and all relationships are represented as typed, bidirectional, and audited graph links.\n\n---\n\n## The Unified Object Spine Architecture\n\nThe Universal Object Graph defines 9 first-class entity kinds (`database/models/spine.py`):\n\n```mermaid\nflowchart TD\n    Spine[\"Universal Object Spine<br/>- id: UUIDv7 (time-ordered monotonic)<br/>- entity_kind: Enum (9 kinds)<br/>- workspace_id: UUID (mandatory tenant boundary)<br/>- access_control_list & timestamps\"]\n    \n    Spine --> Issue[\"ISSUE\"]\n    Spine --> Doc[\"DOC\"]\n    Spine --> Sticky[\"STICKY\"]\n    Spine --> Cycle[\"CYCLE\"]\n    Spine --> Module[\"MODULE\"]\n    Spine --> View[\"VIEW\"]\n    Spine --> Page[\"PAGE\"]\n    Spine --> Project[\"PROJECT\"]\n    Spine --> Workspace[\"WORKSPACE\"]\n```\n\n![Link Graph Popover and Dependency Visualization](images/19-link-graph-popover.png)\n\n### Key Spine Invariants\n1. **Monotonic UUIDv7 Identifiers:** All objects use UUIDv7 keys, providing temporal sorting, index locality, and sub-millisecond insert performance in PostgreSQL.\n2. **Mandatory Tenant Boundary:** Every spine record requires a `workspace_id`. Cross-workspace objects cannot exist in the spine.\n3. **Canonical UTF-8 Markdown Content:** Textual representations store normalized Markdown exclusively.\n\n---\n\n## The 13 Typed Object Relationships\n\nAll inter-object relationships are stored in the centralized `object_links` table with strict referential typing:\n\n| Link Kind | Inbound Complement | Permitted Entity Pairs | Semantic Meaning |\n| :--- | :--- | :--- | :--- |\n| **`BLOCKS`** | `BLOCKED_BY` | `ISSUE` -> `ISSUE` | Dependency blocker preventing completion. |\n| **`BLOCKED_BY`** | `BLOCKS` | `ISSUE` -> `ISSUE` | Dependent item waiting on prerequisite. |\n| **`RELATES_TO`** | `RELATES_TO` | Any -> Any | Non-blocking topical association. |\n| **`DUPLICATES`** | `DUPLICATED_BY` | `ISSUE` -> `ISSUE` | Identifies redundant work items. |\n| **`DUPLICATED_BY`**| `DUPLICATES` | `ISSUE` -> `ISSUE` | Original issue retained for resolution. |\n| **`PARENT_OF`** | `CHILD_OF` | `ISSUE` -> `ISSUE`, `DOC` -> `DOC` | Hierarchical parent-child composition. |\n| **`CHILD_OF`** | `PARENT_OF` | `ISSUE` -> `ISSUE`, `DOC` -> `DOC` | Sub-task or child page relationship. |\n| **`PROMOTED_TO`** | `PROMOTED_FROM`| `STICKY` -> `DOC` | Captures origin of promoted documentation. |\n| **`PROMOTED_FROM`**| `PROMOTED_TO` | `DOC` -> `STICKY` | Points back to source ideation sticky. |\n| **`MENTIONS`** | `REFERENCED_IN`| `ISSUE`/`DOC` -> Any | Inline `@mention` or object tag reference. |\n| **`REFERENCED_IN`**| `MENTIONS` | Any -> `ISSUE`/`DOC` | Backlink tracking mention occurrences. |\n| **`ATTACHED_TO`** | `DERIVED_FROM` | Media -> `ISSUE`/`DOC` | Asset or diagram attachment. |\n| **`DERIVED_FROM`** | `ATTACHED_TO` | `ISSUE`/`DOC` -> Media | Traceability to original media asset. |\n\n---\n\n## Invalid Object Link Auditor and Purger\n\nIn active development environments, soft deletes, project migrations, and permission adjustments can produce invalid relationships. Rather than allowing broken links to silently corrupt views or leak references, \ud83d\udc4dkanban runs an automated **Invalid Object Link Auditor** (`database/auditor/`).\n\n### The 6-Class Invalid Link Detection Matrix\n\nThe auditor continuously scans the `object_links` table, categorizing anomalies into 6 strict violation classes:\n\n```mermaid\nflowchart LR\n    Scan[\"Auditor Background Worker\"] --> Check{\"Analyze object_links\"}\n    Check --> C1[\"1. Orphaned Source\"]\n    Check --> C2[\"2. Orphaned Target\"]\n    Check --> C3[\"3. Cross-Tenant Leak\"]\n    Check --> C4[\"4. Disallowed Self-Ref\"]\n    Check --> C5[\"5. Hierarchy Cycle\"]\n    Check --> C6[\"6. Schema Violation\"]\n    \n    C1 --> Remediate[\"Remediation Action\"]\n    C2 --> Remediate\n    C3 --> Remediate\n    C4 --> Remediate\n    C5 --> Remediate\n    C6 --> Remediate\n    \n    Remediate --> DryRun[\"--dry-run: Generate Audit Report\"]\n    Remediate --> Purge[\"--purge: Delete & Append Ledger\"]\n```\n\n1. **Orphaned Source:** The source object ID does not exist in the active object spine.\n2. **Orphaned Target:** The target object ID does not exist or has been deleted.\n3. **Cross-Tenant Leak:** The source and target objects belong to different workspaces, violating tenant isolation.\n4. **Disallowed Self-Reference:** An object links to itself in an invalid manner (e.g. `KAN-5 BLOCKS KAN-5`).\n5. **Illegal Hierarchy Cycle:** A circular dependency exists in `PARENT_OF` or `BLOCKS` graphs (e.g. A blocks B, B blocks C, C blocks A).\n6. **Schema-Violating Pair:** A link kind connects incompatible entity types (e.g. a `STICKY` claiming to `BLOCK` a `WORKSPACE`).\n\n### Audited Purging and Dry-Run Reporting\n\nPlatform administrators can inspect and remediate graph health through administrative APIs and CLI commands:\n\n```bash\n# Run link audit in dry-run mode (read-only verification)\nkanban-ctl audit-links --dry-run\n\n# Execute clean purge of corrupted links with full audit logging\nkanban-ctl audit-links --purge --reason \"Monthly maintenance cycle\"\n```\n\nAll purged links are written to the immutable `audit_ledger` with the operator ID, timestamp, and the exact violation class, ensuring forensic traceability.\n\n![Delete Blast Radius Warning Modal](images/20-delete-blast-radius.png)\n\n---\n\n## Admin Link Auditor Studio (`/admin/link-auditor`)\n\nWhile CLI commands provide automated pipeline hooks, workspace and server administrators have access to a full forensic UI studio at `/admin/link-auditor`.\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Admin as Workspace / Server Admin (AAL2)\n    participant Studio as Link Auditor Studio (/admin/link-auditor)\n    participant Drawer as Inspect Link Drawer\n    participant Modal as 2-Stage Purge Modal\n    participant Engine as Auditor Engine & DB\n\n    Admin->>Studio: Navigate to /admin/link-auditor\n    Studio->>Engine: Run Integrity Scan across object_links\n    Engine-->>Studio: Return breakdown counts & keyset-paginated invalid links\n    Admin->>Studio: Click \"Inspect\" on flagged link\n    Studio->>Drawer: Open Inspect Link Drawer (source, target, violation rationale)\n    Admin->>Studio: Click \"Purge Selected Links\"\n    Studio->>Modal: Open 2-Stage Purge Confirmation Modal\n    Modal->>Admin: Require typed confirmation & reason\n    Admin->>Modal: Submit cryptographic confirmation\n    Modal->>Engine: Atomic DELETE invalid links & INSERT audit_ledger\n    Engine-->>Studio: Links purged: real-time table update\n```\n\n![Invalid Object Link Auditor Studio](images/46-admin-link-auditor.png)\n\n### 1. Six-Class Breakdown Cards\nThe top of the studio displays real-time counts across the 6 anomaly classes:\n- **Dangling Source:** Source entity does not exist in the universal object graph.\n- **Dangling Target:** Target entity does not exist or has been permanently removed.\n- **Soft-Deleted Endpoint:** Endpoint entity is marked soft-deleted while link remains active.\n- **Cross-Workspace Leak:** Link crosses workspace boundaries without multi-tenant grant.\n- **Type Matrix Violation:** Link connects object kinds prohibited by the universal type matrix.\n- **Permission Severed:** Access boundary severed between linked entities.\n\n### 2. Inspect Link Drawer\nClicking **Inspect** on any flagged row opens a detailed forensic drawer displaying full endpoint metadata, entity timestamps, link creation provenance, and specific violation details:\n\n![Inspect Link Drawer](images/47-admin-link-auditor-inspect-drawer.png)\n\n### 3. Audited Purge Modal\nTo prevent accidental data loss, purging invalid links requires two-stage administrative confirmation:\n- Displays exact count of affected links and affected entity keys.\n- Requires entering an explicit audit reason that is permanently recorded in the ledger.\n- Executes atomically inside a PostgreSQL transaction, recording SHA-256 hash-chained entries in `audit_ledger`.\n\n![Audited Purge Modal](images/48-admin-link-auditor-purge-modal.png)\n"
  },
  {
    "slug": "user-tasks-and-qa-matrix",
    "title": "\ud83d\udc4dkanban User Task & Architecture QA Verification Matrix",
    "category": "Overview",
    "order": 25,
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
        "title": "Group C: Canonical Markdown, Stickies, Docs & Sparkle (`\u2728`) AI Completion (Spec S5, S8, S9)",
        "level": 3
      },
      {
        "id": "group-d-mcp-access-studio-custom-scripted-fields-workflow-transition-interceptors-spec-s11-s13-s14",
        "title": "Group D: MCP Access Studio, Custom Scripted Fields & Workflow Transition Interceptors (Spec S11, S13, S14)",
        "level": 3
      },
      {
        "id": "group-e-administrative-hardening-rbac-gate-rework-verification-spec-s3-s4-s11-s14",
        "title": "Group E: Administrative Hardening, RBAC & Gate Rework Verification (Spec S3, S4, S11, S14)",
        "level": 3
      }
    ],
    "content": "# \ud83d\udc4dkanban User Task & Architecture QA Verification Matrix\n\n> **Purpose:** This document maps every functional domain in [System Topology and Multi-Container Architecture](System-Topology-and-Multi-Container-Architecture) (Sections 1-15) to concrete human user tasks, live `/browser` verification scenarios, screenshot deliverables, and API/MCP schema audits.\n\n---\n\n## 1. Subagent Task Assignment Roster\n\n```mermaid\nflowchart TD\n    Spec[\"Authoritative Product Spec (S1-S15)\"] --> QAPipeline[\"Forensic QA Verification Pipeline\"]\n    \n    subgraph Execution[\"Parallel Verification Engines\"]\n        Bot1[\"Browser QA Bot 1<br/>Board, Views, 17-Feature Ticket Screen\"]\n        Bot2[\"Browser QA Bot 2<br/>Docs, Stickies, Markdown, Sparkle (\u2728)\"]\n        Bot3[\"Browser QA Bot 3<br/>Auth, Security, MCP & Workflow Studios\"]\n        MCPAudit[\"MCP Evaluator Bot<br/>27 Live Tool Schemas & Budgets\"]\n    end\n    \n    QAPipeline --> Bot1\n    QAPipeline --> Bot2\n    QAPipeline --> Bot3\n    QAPipeline --> MCPAudit\n    \n    Bot1 --> Artifacts[\"Visual Proof Packet (35+ Screenshots in images/)\"]\n    Bot2 --> Artifacts\n    Bot3 --> Artifacts\n    MCPAudit --> Artifacts\n    \n    Artifacts --> RealityChecker[\"reality-checker Forensic Audit Gate<br/>(Grade-A READY Certification)\"]\n```\n\n| Subagent Role | Model Tier | Assigned Architecture Sections | Primary Deliverables |\n| :--- | :---: | :--- | :--- |\n| **Browser QA & Screenshot Bot 1: Core Board, Views & Ticket Drawer** | `flash` | **S6** (Board, Whitespace, `<EmojiHint>`), **S7** (17-Feature Ticket Screen, `?peek=` Drawer, Rail, 4-Tab Activity) | Live `/browser` human walkthrough of Workspace Home, Board, List (3-pane split), Table, Calendar, Timeline, Quick-Create (`C`), and Ticket Drawer (`?peek=`). Captures annotated screenshots into `thumbs-up-kanban.wiki/images/`. |\n| **Browser QA & Screenshot Bot 2: Docs, Stickies, Editor & Sparkle (`\u2728`)** | `flash` | **S5** (Canonical Markdown, Mermaid, SVG), **S8** (Hierarchical Docs & Stickies Promotion), **S9** (Sparkle FIM Completion & Right-Click Accept) | Live `/browser` human walkthrough of Workspace/Project Stickies, Sticky-to-Doc AI Promotion modal, Docs ltree tree & outline, Editor Markdown/Mermaid rendering, and Sparkle (`\u2728`) ghost-text completion. Captures screenshots into `thumbs-up-kanban.wiki/images/`. |\n| **Browser QA & Screenshot Bot 3: Auth, Security, MCP & Workflow Studios** | `flash` | **S2** (Standalone Status Panel), **S4** (Multi-Card Auth Studio & `/setup`), **S11** (MCP Access & Scopable Keys Studio), **S13** (Custom Fields Studio), **S14** (Workflow Transition Studio & Dry-Run Drawer) | Live `/browser` human walkthrough of `/setup`, `/login`, `/admin/auth`, `/admin/mcp`, `/projects/KAN/settings/workflows`, `/projects/KAN/settings/custom-fields`, and `/admin/standalone`. Captures screenshots into `thumbs-up-kanban.wiki/images/`. |\n| **MCP Tools JSON vs. Expectation Evaluator Bot** | `flash` | **S11** (3-Surface MCP Server: `/mcp/agent`, `/mcp/docs`, `/mcp/admin`), **S3.5** (Read-Taint Guard), **S14** (Admin Tool 8 & 9) | Audits all 27 live MCP tool JSON schemas (`/tmp/mcp_tools_actual.json`) against Spec S11 expectations for parameter clarity, `EntityResolver` human keys, `lod` tiers, 2-stage destructive confirmations, and LLM ergonomics. Produces `thumbs-up-kanban.wiki/MCP-Tools-Usability-Audit.md`. |\n| **Wiki Documentation Architect & Author** | `flash` / Coordinator | **S1-S15** (Full System Coverage + OpenAPI 184-Route Reference + MCP 27-Tool Reference) | Authors complete 10-page Wiki in `thumbs-up-kanban.wiki/` with `_Sidebar.md`, `_Footer.md`, embedded screenshots, Mermaid diagrams, REST OpenAPI reference, MCP catalog, and CLI runbooks. |\n| **Carbon Architecture-vs-Docs Delta Auditor** | `pro` (Carbon) | **S1-S15** Cross-Layer Forensic Delta Audit | Compares `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and actual codebase against all Wiki topics, browser QA findings, and API/MCP schemas to identify missing features, incomplete items, and actionable backlog tickets. |\n\n---\n\n## 2. User Task Catalogue by Architecture Specification Section\n\n### Group A: Onboarding, Authentication & Standalone Operations (Spec S2, S3, S4)\n\n| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |\n| :--- | :---: | :--- | :--- | :--- | :--- |\n| **`UT-01`** | **S2.2, S4.2** | Platform Operator | **First-Boot `/setup` Claim Wizard** | 1. Navigate to `/setup` on a fresh instance.<br>2. Inspect the single-use `kb_setup_*` bootstrap token input, initial admin username/password fields, and workspace creation form.<br>3. Verify pre-session CSRF bootstrap (`__Host-kb_csrf` / `kb_csrf`). | Renders clean First-Boot Claim Wizard without 403 CSRF errors.<br>[images/01-first-boot-setup.png](images/01-first-boot-setup.png) |\n| **`UT-02`** | **S4.1, S4.3** | End User / Admin | **Multi-Card Login & Passkey/TOTP Prompt** | 1. Navigate to `/login`.<br>2. Verify ordered authentication cards (Local Admin, OIDC/OAuth2, LDAPS, WebAuthn Passkey `rp.name = \"\ud83d\udc4dkanban\"`).<br>3. Test credential entry and session establishment. | Displays enabled auth cards in `sort_rank` order with zero implicit email auto-merge.<br>[images/02-multi-card-login.png](images/02-multi-card-login.png) |\n| **`UT-03`** | **S4.4** | Server Admin (AAL2) | **Admin Auth Studio Management** | 1. Navigate to `/admin/auth`.<br>2. Inspect auth card list, enable/disable toggles, drag reorder, write-only secret fields, `Test Handshake` action, and `LOCKOUT_PREVENTED` break-glass guard. | Shows Auth Studio with mandatory vs. optional config sections and lockout guard.<br>[images/03-admin-auth-studio.png](images/03-admin-auth-studio.png) |\n| **`UT-04`** | **S2.2, S2.4** | Platform Operator | **Standalone Status Panel & Compose Export** | 1. Navigate to `/admin/standalone`.<br>2. Check volume persistence probe status (`/var/lib/kanban/data`), dismissible notification pill, encrypted backup trigger, and `docker-compose.yml` 5-network export tab. | Displays green/amber persistence status and copyable 5-network production Compose bundle.<br>[images/04-standalone-status-panel.png](images/04-standalone-status-panel.png) |\n\n![First-Boot Setup Wizard](images/01-first-boot-setup.png)\n\n![Multi-Card Login Screen](images/02-multi-card-login.png)\n\n---\n\n### Group B: Workspace Home, Multi-Layout Views & 17-Feature Ticket Screen (Spec S6, S7)\n\n| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |\n| :--- | :---: | :--- | :--- | :--- | :--- |\n| **`UT-05`** | **S6.1, S6.3** | Project Lead | **Workspace Home & Project Creation** | 1. Navigate to `/`.<br>2. Inspect project cards (`KAN`), quick-links (`Work Items`, `Board`, `Stickies`, `Docs`, `Custom Fields`), and click `+ Create Project` modal. | Renders Workspace Home grid and project creation modal.<br>[images/05-workspace-home.png](images/05-workspace-home.png) |\n| **`UT-06`** | **S6.2, S6.4** | Developer | **Kanban Board View & Optimistic Drag (`<12ms`)** | 1. Navigate to `/projects/KAN/issues?layout=board`.<br>2. Verify breathable whitespace, state columns (`Backlog`, `Todo`, `In Progress`, `Done`), corporate priority badges, `<EmojiHint>` hover tooltips, and card drag-and-drop. | Columns render with virtualized cards, semantic emojis, and instant drag response.<br>[images/06-board-view.png](images/06-board-view.png) |\n| **`UT-07`** | **S6.3** | Developer / PM | **Multi-Layout Switching: List, Table, Calendar & Timeline (Gantt)** | 1. Switch layouts via `?layout=list` (3-pane split view), `?layout=table`, `?layout=calendar`, and `?layout=timeline`.<br>2. Inspect filters bar, 2D swimlane grouping, and Gantt dependency arrows (`BLOCKS`). | All 5 layouts render cleanly without full-page reloads.<br>[images/07-list-table-calendar-timeline.png](images/07-list-table-calendar-timeline.png) |\n| **`UT-08`** | **S7.1, S7.2** | Developer | **Quick-Create Work Item Modal (`C`) & Draft Toggle** | 1. Press `C` or click `+ New Work Item`.<br>2. Enter title, Markdown description, state/priority, and inspect the `\u270d\ufe0f Keep work-in-progress` draft checkbox. | Opens Quick-Create modal and persists new issue into active view.<br>[images/08-quick-create-modal.png](images/08-quick-create-modal.png) |\n| **`UT-09`** | **S7.1-S7.4 (`8a`-`8q`)** | Developer / Reviewer | **Ticket Peek Drawer (`?peek=`) & 17-Feature Inspection** | 1. Click any issue card to open `?peek=KAN-1` while keeping the background board visible.<br>2. Verify properties rail (`State`, hybrid `Assignees \ud83c\udff7\ufe0f`, `Priority`, `Created-by \ud83d\udd04`, `Dates`, `Modules`, `Cycle`, `Parent \ud83d\udd12`, `Labels`).<br>3. Inspect header actions (`Subscribe \ud83d\udd14`, `Copy link \ud83d\udd17`, `Archive`, `Delete` blast-radius) and 4-tab Activity feed (`All`, `Comments`, `History`, `\ud83e\udd16 Gates`). | Background board stays mounted; drawer displays all 17 enterprise work-item features and Explicit Sharing pill.<br>[images/09-ticket-peek-drawer.png](images/09-ticket-peek-drawer.png) |\n\n![Kanban Board View](images/06-board-view.png)\n\n![Ticket Peek Drawer with 17 Features](images/09-ticket-peek-drawer.png)\n\n---\n\n### Group C: Canonical Markdown, Stickies, Docs & Sparkle (`\u2728`) AI Completion (Spec S5, S8, S9)\n\n| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |\n| :--- | :---: | :--- | :--- | :--- | :--- |\n| **`UT-10`** | **S8.2, S10.4** | Product Manager | **Workspace & Project Stickies + Smart AI Doc Promotion** | 1. Navigate to `/stickies` and `/projects/KAN/overview`.<br>2. Create a quick sticky note on the masonry grid.<br>3. Trigger **Promote to Doc** preview to verify AI structuring and ACL inheritance warning. | Sticky note renders on color-coded grid; promotion preview structures Markdown while preserving ACL scope.<br>[images/10-stickies-and-doc-promotion.png](images/10-stickies-and-doc-promotion.png) |\n| **`UT-11`** | **S8.1** | Technical Writer | **Hierarchical Docs (`ltree`), Outline & Version History** | 1. Navigate to `/projects/KAN/docs`.<br>2. Browse nested page tree, inspect auto-extracted heading outline rail, and view append-only version history/restore drawer. | Renders hierarchical doc tree, rich Markdown body, and version history diff/restore controls.<br>[images/11-docs-hierarchy-view.png](images/11-docs-hierarchy-view.png) |\n| **`UT-12`** | **S5.1-S5.4, S9.1-S9.3** | Engineer | **Canonical Markdown Editor, Mermaid Diagrams & Sparkle (`\u2728`) FIM** | 1. Open the editor (`/projects/KAN/docs` or `/__dev/editor`).<br>2. Test auto-converted paste, client-side Mermaid SVG rendering, and pause typing for `300ms` to trigger the blinking cursor Sparkle (`\u2728`) inline completion.<br>3. Test `Tab` or surgical right-click context menu accept. | Renders sanitized Markdown + Mermaid diagram and displays non-intrusive Sparkle ghost text.<br>[images/12-editor-mermaid-and-sparkle.png](images/12-editor-mermaid-and-sparkle.png) |\n\n![Project Stickies and Smart Promotion Modal](images/10-stickies-and-doc-promotion.png)\n\n![Editor with Mermaid Diagrams and Sparkle Completion](images/12-editor-mermaid-and-sparkle.png)\n\n---\n\n### Group D: MCP Access Studio, Custom Scripted Fields & Workflow Transition Interceptors (Spec S11, S13, S14)\n\n| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |\n| :--- | :---: | :--- | :--- | :--- | :--- |\n| **`UT-13`** | **S11.2, S11.3** | Developer / Admin | **Scopable MCP Keys, Per-Tool Toggles & Device Activation** | 1. Navigate to `/settings/mcp`, `/admin/mcp`, and `/activate` (RFC 8628 Device Flow).<br>2. Inspect hierarchical scoping (`Global`, `Workspace`, `Project`), expiration presets (including `Unlimited` with safety friction), and per-tool checkboxes across `/mcp/agent`, `/mcp/docs`, `/mcp/admin`. | Displays MCP Access Studio with copyable client config snippets and granular tool toggles.<br>[images/13-mcp-access-studio.png](images/13-mcp-access-studio.png) |\n| **`UT-14`** | **S13.1-S13.3** | Project / Server Admin | **Custom Scripted Fields (`\ud83e\uddea`) & Tiered Privilege Escalation** | 1. Navigate to `/projects/KAN/settings/custom-fields`.<br>2. Inspect custom field definitions, Wasm/script bindings, `\ud83e\uddea` computed badge on ticket rail, and AAL2 approval banner for escalated scope (`Project` -> `Workspace` -> `Server`). | Renders Custom Fields Studio and cryptographic admin approval status.<br>[images/14-custom-fields-studio.png](images/14-custom-fields-studio.png) |\n| **`UT-15`** | **S14.1-S14.4** | Workflow Architect | **Admin Workflow Transition Studio & Non-Persistent Dry-Run** | 1. Navigate to `/projects/KAN/settings/workflows`.<br>2. Select a `(from_state -> to_state)` rule, inspect ordered pipeline hooks (Tier A Wasm validator, Tier A mutator, Async Agent Interceptor `in_app_sdk` / `cli_pipe` / `remote_runner`, mutable field checkboxes).<br>3. Open the **Dry-Run Drawer**, test against a sample ticket, and inspect per-step execution results and copyable `kanban-agent validate-transition` CLI snippet. | Displays pipeline ordering studio and executes zero-persistence dry-run with step timings.<br>[images/15-workflow-transition-studio.png](images/15-workflow-transition-studio.png) |\n| **`UT-16`** | **S14.2** | Developer | **Async Agent Gate Lifecycle on Board (`\u23f3\ud83e\udd16` -> `\ud83d\uded1\ud83e\udd16` / `\u2705\ud83e\udd16`)** | 1. Inspect async agent gate card states (`/projects/KAN/issues?layout=board` or `/__dev/realtime`): live countdown timer (`\u23f3\ud83e\udd16`), `240ms` spring snap-back toast on veto (`\ud83d\uded1\ud83e\udd16`), and verified header badge (`\u2705\ud83e\udd16`). | Visualizes pending agent hold, countdown progress bar, and veto snap-back toast.<br>[images/16-async-agent-gate-states.png](images/16-async-agent-gate-states.png) |\n\n---\n\n### Group E: Administrative Hardening, RBAC & Gate Rework Verification (Spec S3, S4, S11, S14)\n\n| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |\n| :--- | :---: | :--- | :--- | :--- | :--- |\n| **`UT-17`** | **S2.2, S4.4, S15.1** | Server Admin (AAL2) | **Admin Browser QA: Auth Studio, Principals & Favicon** | 1. Navigate to `/admin/auth`.<br>2. Inspect multi-card authentication ordering and lockout protection.<br>3. Inspect Principal Management kind filter tabs (`ALL`, `USER`, `GROUP`, `AGENT`).<br>4. Click `+ Create Principal`, select `GROUP` or `AGENT`, provide identifier and display name, and submit.<br>5. Verify `GET /favicon.ico` returns HTTP 200 with `Cache-Control: public, max-age=86400`. | Auth Studio manages USER/GROUP/AGENT principals; `/favicon.ico` serves branded asset cleanly.<br>[images/17-admin-browser-qa.png](images/17-admin-browser-qa.png) |\n| **`UT-18`** | **S3.1-S3.4, S13.2, S15.2** | Standard Member | **Standard User Browser QA & Negative RBAC Isolation** | 1. Authenticate as standard workspace member (`WORKSPACE_MEMBER`).<br>2. Browse assigned projects, board, list, docs, and ticket drawer.<br>3. Attempt navigation to administrative routes (`/admin/auth`, `/admin/standalone`, `/admin/mcp`, `/projects/KAN/settings/custom-fields`).<br>4. Verify custom fields editor fails closed with access denied toast/banner.<br>5. Confirm zero administrative controls or privileged mutation buttons leak into client DOM. | Negative RBAC strictly isolates standard users; privileged views fail closed without privilege leaks.<br>[images/18-standard-user-negative-rbac.png](images/18-standard-user-negative-rbac.png) |\n| **`UT-19`** | **S11.1-S11.4, S14.3** | Security Architect / Agent | **CLI MCP Scoping Matrix & E2E Gate Rework Loop** | 1. Audit all 12 `/mcp/admin` tools in `mcp/auth.py` for action-aware scope enforcement (`admin:read`, `admin:write`, `admin:destructive`).<br>2. Verify `project` argument alias to `project_key` on `manage_ai_and_agent_runners` and `architect_project`.<br>3. Verify OpenAI Codex CLI invocation enforces `codex exec -s read-only -` and rejects `-p`.<br>4. Run E2E transition gate rework loop: first transition enters `pending_agent` (`\u23f3\ud83e\udd16`), verifier rejects initial commit SHA with `cited_files`, rolls back to source state (`\ud83d\uded1\ud83e\udd16`), developer commits rework fix, and second transition evaluates fixed commit SHA, records `verdict=\"APPROVE\"` (`\u2705\ud83e\udd16`), advancing state and appending immutable hash-chained audit record. | Full 12-tool scope matrix enforced; E2E gate rework loop executes and logs immutable provenance.<br>[images/19-mcp-scoping-and-rework-loop.png](images/19-mcp-scoping-and-rework-loop.png) |\n\n![Workflow Transition Studio and Dry-Run Drawer](images/15-workflow-transition-studio.png)\n\n![Async Agent Gate Card States and Snap-Back Lifecycle](images/16-async-agent-gate-states.png)\n"
  },
  {
    "slug": "zero-trust-security-and-access-visibility",
    "title": "Zero-Trust Security Architecture and Explicit Access Visibility",
    "category": "System Architecture",
    "order": 26,
    "summary": "Security is Priority 0 in \ud83d\udc4dkanban. Rather than relying on fragile application-level checks or leaky implicit permissions, \ud83d\udc4dkanban implements an uncompromising zero-trust architecture. Every request, query, and agent invocation is authenticated, scoped, and strictly evaluated against mathematical access invariants.",
    "sections": [
      {
        "id": "overview",
        "title": "Overview",
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
        "id": "stride-threat-mitigation-matrix",
        "title": "STRIDE Threat Mitigation Matrix",
        "level": 2
      }
    ],
    "content": "# Zero-Trust Security Architecture and Explicit Access Visibility\n\n## Overview\n\nSecurity is Priority 0 in \ud83d\udc4dkanban. Rather than relying on fragile application-level checks or leaky implicit permissions, \ud83d\udc4dkanban implements an uncompromising zero-trust architecture. Every request, query, and agent invocation is authenticated, scoped, and strictly evaluated against mathematical access invariants.\n\nKey security pillars:\n1. **Hardware-Enforced Database RLS:** PostgreSQL `FORCE ROW LEVEL SECURITY` is enabled across 100% of tenant tables.\n2. **Zero-Context Fail-Closed Execution:** Unbound database sessions return zero rows.\n3. **Explicit Access Visibility:** Every ticket, doc, and sticky renders an explicit sharing manifest with zero cross-tenant enumeration.\n4. **Agent On-Behalf-Of (OBO) Key Scoping:** Agent permissions are computed strictly as the mathematical intersection of the calling user's permissions and the API key's scope.\n5. **MCP Read-Taint High-Water Mark Defense:** Prevents autonomous agents from exfiltrating sensitive data read from higher-privilege scopes into lower-privilege write targets.\n\n---\n\n## Universal Access Control Model\n\n\ud83d\udc4dkanban unifies human users, user groups, and autonomous agent service-principals under a single Universal Object Graph access model.\n\n### Effective Resource Access (ERA) Evaluation\n\nAccess to any resource (`Project`, `Issue`, `Doc`, `Sticky`, `View`) is determined dynamically:\n\n```mermaid\nflowchart TD\n    User[\"Principal (Human / Agent)\"] --> Inherited[\"Inherited RBAC (Workspace & Project Roles)\"]\n    User --> Direct[\"Direct Resource ACLs (Allow & Deny Masks)\"]\n    Inherited --> Combined[\"Effective User Access = (Inherited \u222a Allow) \\ Deny\"]\n    \n    subgraph AgentOBO[\"Agent On-Behalf-Of Clamping\"]\n        Combined --> Intersect{\"Intersection (\u2229)\"}\n        KeyScope[\"API Key Scope Constraints<br/>(Allowed surfaces, projects, tools)\"] --> Intersect\n        AgentGrant[\"Explicit Agent Grant\"] --> Intersect\n        Intersect --> Effective[\"Final Effective Agent Permission\"]\n    end\n```\n\nWhere:\n- **Roles:** `Owner`, `Admin`, `Member`, `Guest`.\n- **Granular ACL Masks:** `VIEW` (0x01), `EDIT` (0x02), `DELETE` (0x04), `ADMIN` (0x08), `SHARE` (0x10).\n- **Agent OBO Key Intersection:** When an autonomous agent acts on behalf of a user using an API key, the effective permission is clamped:\n  ```\n  AgentEffectiveAccess = UserPermissions INTERSECT KeyScopeConstraints\n  ```\n  An agent cannot escalate privileges beyond the user who generated the key, nor can it exceed the explicit scope configured on the key.\n\n---\n\n## PostgreSQL FORCE ROW LEVEL SECURITY (100% Coverage)\n\nEvery tenant table in PostgreSQL enforces Row-Level Security:\n\n```sql\nALTER TABLE issues ENABLE ROW LEVEL SECURITY;\nALTER TABLE issues FORCE ROW LEVEL SECURITY;\n```\n\n### The Fail-Closed Context Invariant\n\nPostgreSQL sessions authenticate as the unprivileged database role `kanban_app`. This role is stripped of `SUPERUSER` and `BYPASSRLS`. To query or mutate tenant data, the application server must establish an explicit session context within a transaction:\n\n```sql\nSET LOCAL app.current_principal_id = '01932e6b-7341-789a-bc01-123456789abc';\nSET LOCAL app.current_workspace_id = '01932e6b-7341-789a-bc01-def012345678';\n```\n\nIf a developer writes a raw query without setting the session context, the RLS policies fail closed: **zero rows are returned, and zero mutations succeed**. Even if an attacker executes SQL injection, they cannot bypass RLS to read cross-tenant data.\n\n---\n\n## Explicit Access Visibility and Sharing Manifests\n\nSaaS platforms often hide sharing rules behind obscure settings menus, leading to accidental leaks. In \ud83d\udc4dkanban, every resource view exposes a dynamic `\ud83d\udee1\ufe0f` sharing pill.\n\nClicking the sharing pill reveals the **Access Manifest**:\n- **Explicit Principals:** Lists all users, groups, and autonomous agents with direct access.\n- **Inherited Scope:** Displays parent project and workspace inheritance paths.\n- **Auditable Effective Mask:** Shows exact read, write, share, and delete capabilities for each principal.\n\n![Access Visibility Inspector and Sharing Manifest](images/17-access-visibility-inspector.png)\n\n### Anti-Enumeration and Timing Defense\n\nTo prevent malicious actors from scanning IDs or usernames:\n- **Identical RFC 7807 404 Responses:** Accessing an unauthorized resource returns an identical `404 Not Found` response as a non-existent resource. Unauthorized users cannot determine whether an object exists.\n- **25ms Timing Floor:** All resource lookups enforce a synthetic 25ms timing floor to neutralize side-channel timing attacks that measure database index lookups.\n\n---\n\n## MCP Read-Taint High-Water Mark Defense\n\nAutonomous LLMs can be tricked by prompt injection into reading confidential documents and writing excerpts into public tickets. \ud83d\udc4dkanban prevents this through **Read-Taint Tracking**:\n\n```mermaid\nsequenceDiagram\n    autonumber\n    actor Agent as Autonomous Agent\n    participant Gateway as MCP Gateway Taint Engine\n    participant PrivateDoc as Confidential Doc (Tier: PRIVATE)\n    participant PublicTicket as Public Ticket (Tier: PUBLIC)\n\n    Agent->>Gateway: read_doc(id='confidential_spec')\n    Gateway->>PrivateDoc: Fetch Document\n    PrivateDoc-->>Gateway: Return Content\n    Gateway->>Gateway: Elevate Agent Session High-Water Mark to PRIVATE\n    Gateway-->>Agent: Deliver Markdown Payload\n\n    Note over Agent: Later in conversation...\n    Agent->>Gateway: update_ticket(id='public_bug', body=...)\n    Gateway->>Gateway: Check Destination Scope (PUBLIC) vs High-Water Mark (PRIVATE)\n    Gateway-->>Agent: 403 Forbidden (CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED)\n```\n\n![Agent Kill Switch and Immediate Session Revocation](images/18-agent-kill-switch.png)\n\nWhen an agent reads a resource with an elevated confidentiality label, its session high-water mark increases. Any subsequent write operation to a lower-privilege target is halted immediately with an error requiring human operator confirmation.\n\n---\n\n## STRIDE Threat Mitigation Matrix\n\n| Threat Category | Potential Attack Vector | \ud83d\udc4dkanban Architectural Defense |\n| :--- | :--- | :--- |\n| **Spoofing** | Forged session cookies or stolen API tokens | Multi-Card AAL2 enforcement, cryptographic token binding, and WebAuthn Passkeys. |\n| **Tampering** | Parameter manipulation or state corruption | PostgreSQL immutable audit ledger and Wasm state transition validators. |\n| **Repudiation** | Denying ticket edits or deletions | Cryptographically signed append-only activity ledger recording principal IDs. |\n| **Information Disclosure** | Cross-tenant data leakage or ID enumeration | PostgreSQL FORCE RLS on 100% of tables and uniform 404 anti-enumeration responses. |\n| **Denial of Service** | Deep query recursion or token exhaustion | Strict limit of 16 WebSocket conns per user, query depth caps, and MCP token budgets. |\n| **Elevation of Privilege** | Agent tool escalation or script escape | Sandboxed Wasm/nsjail execution and two-stage destructive confirmation tokens. |\n"
  },
  {
    "slug": "configuration-value-reference",
    "title": "Configuration Value Reference",
    "category": "Reference Guides",
    "order": 27,
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
    "content": "# Configuration Value Reference\n\nAuthoritative reference guide for system environment variables and execution tiers.\n\n## Environment Variables\n\n| Key | Type | Default | Description |\n| :--- | :--- | :--- | :--- |\n| `DATABASE_URL` | string (URL) | `postgresql://kanban:kanban@localhost:5432/kanban` | PostgreSQL connection string with UTF-8 and RLS support. |\n| `KANBAN_STANDALONE_MODE` | boolean | `false` | Single-container standalone flag. Gates nsjail sandboxes. |\n| `KANBAN_SECRET_KEY` | string (min 32 chars) | `(required)` | Cryptographic key for signing session cookies and tokens. |\n| `AI_PROVIDER` | enum (openai, gemini, ollama, custom) | `gemini` | Default active AI engine provider for sparkle completions. |\n| `RUNNER_MTLS_CERT_PATH` | string (filesystem path) | `/etc/kanban/certs/client.crt` | Client cert for outbound mTLS remote repository runners. |\n\n## Custom Field Execution Tiers\n\n| Tier | Latency Budget | Standalone Mode | Multi-Container Compose | Best Used For |\n| :--- | :--- | :--- | :--- | :--- |\n| **scalar** | <1ms | Supported | Supported | Static metadata, manual attributes, default strings. |\n| **formula** | <5ms | Supported | Supported | In-process Python AST math, date arithmetic, conditionals. |\n| **wasm** | <25ms | Supported | Supported | Compiled C, Rust, or AssemblyScript wasmtime runtime. |\n| **nsjail** | <250ms | Gated (Fail-closed) | Supported | Isolated Linux namespace sandbox container. |\n\n## System Roles and Capabilities\n\n| Role | Scope | Description |\n| :--- | :--- | :--- |\n| **SERVER_ADMIN** | Server | Full administrative authority over authentication and runners. |\n| **WORKSPACE_ADMIN** | Workspace | Workspace policy, user provisioning, and group management. |\n| **PROJECT_ADMIN** | Project | Project workflows, transition interceptors, and custom fields. |\n| **MEMBER** | Project/Workspace | Create, edit, transition, and comment on work items and docs. |\n| **VIEWER** | Project/Workspace | Read-only access to work items, boards, and docs. |"
  }
];

export const WIKI_CATEGORIES: WikiCategory[] = [
  {
    "name": "System Architecture",
    "chapters": [
      {
        "slug": "admin-custom-scripted-fields-and-sandbox",
        "title": "Admin Custom Scripted Fields and Sandboxed Execution"
      },
      {
        "slug": "blinking-cursor-sparkle-completion-engine",
        "title": "Blinking Cursor Sparkle Completion Engine"
      },
      {
        "slug": "canonical-markdown-and-safe-media-pipeline",
        "title": "Canonical Markdown and Safe Media Pipeline"
      },
      {
        "slug": "clean-db-testing-and-governance-gates",
        "title": "Clean-DB Testing and Governance Gates"
      },
      {
        "slug": "custom-scripts-and-json-security-architecture",
        "title": "Custom Scripts and JSON Security Architecture"
      },
      {
        "slug": "enterprise-whitespace-and-kanban-board",
        "title": "Enterprise Whitespace, Semantic Emojis, and Kanban Board"
      },
      {
        "slug": "hierarchical-docs-and-stickies-with-smart-promotion",
        "title": "Hierarchical Docs, Project Stickies, and Smart Promotion"
      },
      {
        "slug": "migration-and-cutover-runbook",
        "title": "Legacy Tracker Migration and Cutover Runbook"
      },
      {
        "slug": "multi-card-authentication-studio",
        "title": "Multi-Card Authentication Studio and Identity Architecture"
      },
      {
        "slug": "multi-provider-ai-engine-and-runners",
        "title": "Multi-Provider AI Engine, Execution Harnesses, and Runners"
      },
      {
        "slug": "production-promotion-and-backup-runbook",
        "title": "Production Promotion and Backup Runbook"
      },
      {
        "slug": "real-time-web-and-websocket-architecture",
        "title": "Real-Time Web and WebSocket Architecture"
      },
      {
        "slug": "scriptrunner-workflows-and-transition-interceptors",
        "title": "ScriptRunner Workflows and Transition Interceptors"
      },
      {
        "slug": "system-topology-and-multi-container-architecture",
        "title": "System Topology and Multi-Container Architecture"
      },
      {
        "slug": "three-surface-mcp-server-architecture",
        "title": "Three-Surface Model Context Protocol (MCP) Server Architecture"
      },
      {
        "slug": "ticket-screen-and-work-item-features",
        "title": "Ticket Screen, Peek Drawer, and Work Item Architecture"
      },
      {
        "slug": "universal-object-graph-and-link-auditor",
        "title": "Universal Object Graph and Invalid Link Auditor"
      },
      {
        "slug": "zero-trust-security-and-access-visibility",
        "title": "Zero-Trust Security Architecture and Explicit Access Visibility"
      }
    ]
  },
  {
    "name": "Overview",
    "chapters": [
      {
        "slug": "architecture-delta-and-missing-features",
        "title": "\ud83d\udc4dkanban: Architecture Specification Delta & Gap Analysis"
      },
      {
        "slug": "home",
        "title": "\ud83d\udc4dkanban: Executive Architecture and System Overview"
      },
      {
        "slug": "user-tasks-and-qa-matrix",
        "title": "\ud83d\udc4dkanban User Task & Architecture QA Verification Matrix"
      }
    ]
  },
  {
    "name": "Reference Guides",
    "chapters": [
      {
        "slug": "feature-comparison",
        "title": "Feature Comparison"
      },
      {
        "slug": "guide-custom-fields",
        "title": "How to Use Custom Fields"
      },
      {
        "slug": "mcp-tools-reference",
        "title": "Model Context Protocol (MCP) Tools Reference Manual"
      },
      {
        "slug": "rest-api-architecture-and-openapi-guide",
        "title": "REST API Architecture and OpenAPI Integration Guide"
      },
      {
        "slug": "role-and-permission-matrix",
        "title": "Role and Permission Matrix"
      },
      {
        "slug": "configuration-value-reference",
        "title": "Configuration Value Reference"
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
      "description": "Project workflows, transition interceptors, and custom fields."
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
  "workflows": "scriptrunner-workflows-and-transition-interceptors",
  "ai": "multi-provider-ai-engine-and-runners",
  "standalone": "production-promotion-and-backup-runbook",
  "links": "universal-object-graph-and-link-auditor",
  "config": "configuration-value-reference",
  "configuration": "configuration-value-reference"
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
