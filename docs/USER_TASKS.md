# 👍kanban User Task & Architecture QA Verification Matrix

> **Purpose:** This document maps every functional domain in [`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`](./ARCHITECTURE_AND_PRODUCT_SPEC.md) (Sections 1-15) to concrete human user tasks, live `/browser` verification scenarios, screenshot deliverables, and API/MCP schema audits.

---

## 1. Subagent Task Assignment Roster

| Subagent Role | Model Tier | Assigned Architecture Sections | Primary Deliverables |
| :--- | :---: | :--- | :--- |
| **Browser QA & Screenshot Bot 1: Core Board, Views & Ticket Drawer** | `flash` | **S6** (Board, Whitespace, `<EmojiHint>`), **S7** (17-Feature Ticket Screen, `?peek=` Drawer, Rail, 4-Tab Activity) | Live `/browser` human walkthrough of Workspace Home, Board, List (3-pane split), Table, Calendar, Timeline, Quick-Create (`C`), and Ticket Drawer (`?peek=`). Captures annotated screenshots into `thumbs-up-kanban.wiki/images/`. |
| **Browser QA & Screenshot Bot 2: Docs, Stickies, Editor & Sparkle (`✨`)** | `flash` | **S5** (Canonical Markdown, Mermaid, SVG), **S8** (Hierarchical Docs & Stickies Promotion), **S9** (Sparkle FIM Completion & Right-Click Accept) | Live `/browser` human walkthrough of Workspace/Project Stickies, Sticky-to-Doc AI Promotion modal, Docs ltree tree & outline, Editor Markdown/Mermaid rendering, and Sparkle (`✨`) ghost-text completion. Captures screenshots into `thumbs-up-kanban.wiki/images/`. |
| **Browser QA & Screenshot Bot 3: Auth, Security, MCP & Workflow Studios** | `flash` | **S2** (Standalone Status Panel), **S4** (Multi-Card Auth Studio & `/setup`), **S11** (MCP Access & Scopable Keys Studio), **S13** (Custom Fields Studio), **S14** (Workflow Transition Studio & Dry-Run Drawer) | Live `/browser` human walkthrough of `/setup`, `/login`, `/admin/auth`, `/admin/mcp`, `/projects/KAN/settings/workflows`, `/projects/KAN/settings/custom-fields`, and `/admin/standalone`. Captures screenshots into `thumbs-up-kanban.wiki/images/`. |
| **MCP Tools JSON vs. Expectation Evaluator Bot** | `flash` | **S11** (3-Surface MCP Server: `/mcp/agent`, `/mcp/docs`, `/mcp/admin`), **S3.5** (Read-Taint Guard), **S14** (Admin Tool 8 & 9) | Audits all 27 live MCP tool JSON schemas (`/tmp/mcp_tools_actual.json`) against Spec S11 expectations for parameter clarity, `EntityResolver` human keys, `lod` tiers, 2-stage destructive confirmations, and LLM ergonomics. Produces `thumbs-up-kanban.wiki/MCP-Tools-Usability-Audit.md`. |
| **Wiki Documentation Architect & Author** | `flash` / Coordinator | **S1-S15** (Full System Coverage + OpenAPI 184-Route Reference + MCP 27-Tool Reference) | Authors complete 10-page Wiki in `thumbs-up-kanban.wiki/` with `_Sidebar.md`, `_Footer.md`, embedded screenshots, Mermaid diagrams, REST OpenAPI reference, MCP catalog, and CLI runbooks. |
| **Carbon Architecture-vs-Docs Delta Auditor** | `pro` (Carbon) | **S1-S15** Cross-Layer Forensic Delta Audit | Compares `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and actual codebase against all Wiki topics, browser QA findings, and API/MCP schemas to identify missing features, incomplete items, and actionable backlog tickets. |

---

## 2. User Task Catalogue by Architecture Specification Section

### Group A: Onboarding, Authentication & Standalone Operations (Spec S2, S3, S4)

| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **`UT-01`** | **S2.2, S4.2** | Platform Operator | **First-Boot `/setup` Claim Wizard** | 1. Navigate to `/setup` on a fresh instance.<br>2. Inspect the single-use `kb_setup_*` bootstrap token input, initial admin username/password fields, and workspace creation form.<br>3. Verify pre-session CSRF bootstrap (`__Host-kb_csrf` / `kb_csrf`). | Renders clean First-Boot Claim Wizard without 403 CSRF errors.<br>`images/01-first-boot-setup.png` |
| **`UT-02`** | **S4.1, S4.3** | End User / Admin | **Multi-Card Login & Passkey/TOTP Prompt** | 1. Navigate to `/login`.<br>2. Verify ordered authentication cards (Local Admin, OIDC/OAuth2, LDAPS, WebAuthn Passkey `rp.name = "👍kanban"`).<br>3. Test credential entry and session establishment. | Displays enabled auth cards in `sort_rank` order with zero implicit email auto-merge.<br>`images/02-multi-card-login.png` |
| **`UT-03`** | **S4.4** | Server Admin (AAL2) | **Admin Auth Studio Management** | 1. Navigate to `/admin/auth`.<br>2. Inspect auth card list, enable/disable toggles, drag reorder, write-only secret fields, `Test Handshake` action, and `LOCKOUT_PREVENTED` break-glass guard. | Shows Auth Studio with mandatory vs. optional config sections and lockout guard.<br>`images/03-admin-auth-studio.png` |
| **`UT-04`** | **S2.2, S2.4** | Platform Operator | **Standalone Status Panel & Compose Export** | 1. Navigate to `/admin/standalone`.<br>2. Check volume persistence probe status (`/var/lib/kanban/data`), dismissible notification pill, encrypted backup trigger, and `docker-compose.yml` 5-network export tab. | Displays green/amber persistence status and copyable 5-network production Compose bundle.<br>`images/04-standalone-status-panel.png` |

---

### Group B: Workspace Home, Multi-Layout Views & 17-Feature Ticket Screen (Spec S6, S7)

| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **`UT-05`** | **S6.1, S6.3** | Project Lead | **Workspace Home & Project Creation** | 1. Navigate to `/`.<br>2. Inspect project cards (`KAN`), quick-links (`Work Items`, `Board`, `Stickies`, `Docs`, `Custom Fields`), and click `+ Create Project` modal. | Renders Workspace Home grid and project creation modal.<br>`images/05-workspace-home.png` |
| **`UT-06`** | **S6.2, S6.4** | Developer | **Kanban Board View & Optimistic Drag (`<12ms`)** | 1. Navigate to `/projects/KAN/issues?layout=board`.<br>2. Verify breathable whitespace, state columns (`Backlog`, `Todo`, `In Progress`, `Done`), corporate priority badges, `<EmojiHint>` hover tooltips, and card drag-and-drop. | Columns render with virtualized cards, semantic emojis, and instant drag response.<br>`images/06-board-view.png` |
| **`UT-07`** | **S6.3** | Developer / PM | **Multi-Layout Switching: List, Table, Calendar & Timeline (Gantt)** | 1. Switch layouts via `?layout=list` (3-pane split view), `?layout=table`, `?layout=calendar`, and `?layout=timeline`.<br>2. Inspect filters bar, 2D swimlane grouping, and Gantt dependency arrows (`BLOCKS`). | All 5 layouts render cleanly without full-page reloads.<br>`images/07-list-table-calendar-timeline.png` |
| **`UT-08`** | **S7.1, S7.2** | Developer | **Quick-Create Work Item Modal (`C`) & Draft Toggle** | 1. Press `C` or click `+ New Work Item`.<br>2. Enter title, Markdown description, state/priority, and inspect the `✍️ Keep work-in-progress` draft checkbox. | Opens Quick-Create modal and persists new issue into active view.<br>`images/08-quick-create-modal.png` |
| **`UT-09`** | **S7.1-S7.4 (`#8a`-#8q`)** | Developer / Reviewer | **Ticket Peek Drawer (`?peek=`) & 17-Feature Inspection** | 1. Click any issue card to open `?peek=KAN-1` while keeping the background board visible.<br>2. Verify properties rail (`State`, hybrid `Assignees 🏷️`, `Priority`, `Created-by 🔄`, `Dates`, `Modules`, `Cycle`, `Parent 🔒`, `Labels`).<br>3. Inspect header actions (`Subscribe 🔔`, `Copy link 🔗`, `Archive`, `Delete` blast-radius) and 4-tab Activity feed (`All`, `Comments`, `History`, `🤖 Gates`). | Background board stays mounted; drawer displays all 17 enterprise work-item features and Explicit Sharing pill.<br>`images/09-ticket-peek-drawer.png` |

---

### Group C: Canonical Markdown, Stickies, Docs & Sparkle (`✨`) AI Completion (Spec S5, S8, S9)

| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **`UT-10`** | **S8.2, S10.4** | Product Manager | **Workspace & Project Stickies + Smart AI Doc Promotion** | 1. Navigate to `/stickies` and `/projects/KAN/overview`.<br>2. Create a quick sticky note on the masonry grid.<br>3. Trigger **Promote to Doc** preview to verify AI structuring and ACL inheritance warning. | Sticky note renders on color-coded grid; promotion preview structures Markdown while preserving ACL scope.<br>`images/10-stickies-and-doc-promotion.png` |
| **`UT-11`** | **S8.1** | Technical Writer | **Hierarchical Docs (`ltree`), Outline & Version History** | 1. Navigate to `/projects/KAN/docs`.<br>2. Browse nested page tree, inspect auto-extracted heading outline rail, and view append-only version history/restore drawer. | Renders hierarchical doc tree, rich Markdown body, and version history diff/restore controls.<br>`images/11-docs-hierarchy-view.png` |
| **`UT-12`** | **S5.1-S5.4, S9.1-S9.3** | Engineer | **Canonical Markdown Editor, Mermaid Diagrams & Sparkle (`✨`) FIM** | 1. Open the editor (`/projects/KAN/docs` or `/__dev/editor`).<br>2. Test auto-converted paste, client-side Mermaid SVG rendering, and pause typing for `300ms` to trigger the blinking cursor Sparkle (`✨`) inline completion.<br>3. Test `Tab` or surgical right-click context menu accept. | Renders sanitized Markdown + Mermaid diagram and displays non-intrusive Sparkle ghost text.<br>`images/12-editor-mermaid-and-sparkle.png` |

---

### Group D: MCP Access Studio, Custom Scripted Fields & Workflow Transition Interceptors (Spec S11, S13, S14)

| Task ID | Spec Ref | User Persona | Task Title | Step-by-Step Human / Browser Verification Actions | Expected Outcome & Screenshot Target |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **`UT-13`** | **S11.2, S11.3** | Developer / Admin | **Scopable MCP Keys, Per-Tool Toggles & Device Activation** | 1. Navigate to `/settings/mcp`, `/admin/mcp`, and `/activate` (RFC 8628 Device Flow).<br>2. Inspect hierarchical scoping (`Global`, `Workspace`, `Project`), expiration presets (including `Unlimited` with safety friction), and per-tool checkboxes across `/mcp/agent`, `/mcp/docs`, `/mcp/admin`. | Displays MCP Access Studio with copyable client config snippets and granular tool toggles.<br>`images/13-mcp-access-studio.png` |
| **`UT-14`** | **S13.1-S13.3** | Project / Server Admin | **Custom Scripted Fields (`🧪`) & Tiered Privilege Escalation** | 1. Navigate to `/projects/KAN/settings/custom-fields`.<br>2. Inspect custom field definitions, Wasm/script bindings, `🧪` computed badge on ticket rail, and AAL2 approval banner for escalated scope (`Project` -> `Workspace` -> `Server`). | Renders Custom Fields Studio and cryptographic admin approval status.<br>`images/14-custom-fields-studio.png` |
| **`UT-15`** | **S14.1-S14.4** | Workflow Architect | **Admin Workflow Transition Studio & Non-Persistent Dry-Run** | 1. Navigate to `/projects/KAN/settings/workflows`.<br>2. Select a `(from_state -> to_state)` rule, inspect ordered pipeline hooks (Tier A Wasm validator, Tier A mutator, Async Agent Interceptor `in_app_sdk` / `cli_pipe` / `remote_runner`, mutable field checkboxes).<br>3. Open the **Dry-Run Drawer**, test against a sample ticket, and inspect per-step execution results and copyable `kanban-agent validate-transition` CLI snippet. | Displays pipeline ordering studio and executes zero-persistence dry-run with step timings.<br>`images/15-workflow-transition-studio.png` |
| **`UT-16`** | **S14.2** | Developer | **Async Agent Gate Lifecycle on Board (`⏳🤖` -> `🛑🤖` / `✅🤖`)** | 1. Inspect async agent gate card states (`/projects/KAN/issues?layout=board` or `/__dev/realtime`): live countdown timer (`⏳🤖`), `240ms` spring snap-back toast on veto (`🛑🤖`), and verified header badge (`✅🤖`). | Visualizes pending agent hold, countdown progress bar, and veto snap-back toast.<br>`images/16-async-agent-gate-states.png` |
