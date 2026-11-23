# Menu and Navigation Consolidation Audit Matrix (KAN-318)

## 1. Executive Summary

This audit matrix documents the comprehensive examination of every navigation bar, dropdown menu, context menu, sidebar tree, view toolbar, and modal/drawer action bar across the entire web application (`kanban/web/src/`).

The primary goals of this epic are:
1. Eliminate navigation fragmentation, buried admin tools, and duplicate entry points.
2. Establish a unified Admin Studio Subnav across all 8 administrative surfaces.
3. Streamline the left sidebar project tree and consolidate project configuration into clean tabs.
4. Harmonize view toolbars across all 5 issue layouts (`list`, `board`, `table`, `calendar`, `timeline`).
5. Guarantee action parity between Drawer/Fullscreen headers and Master-Detail split-pane views.
6. Spawn tightly scoped child implementation tickets on project `KAN` adhering to the `kanban-ticket` standard.

---

## 2. Complete Menu Option Inventory and Consolidation Plan

| Current Menu / Surface | Option / Link | Action | Target Consolidated Surface | Child Ticket | Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Topbar Avatar Menu** | Personal Settings (`/settings/profile`) | Keep | Topbar Avatar Menu (Account Group) | `KAN-362` | Core user identity settings |
| **Topbar Avatar Menu** | Authentication & Passkeys (`/settings/profile#auth`) | Consolidate | Tab inside Personal Settings | `KAN-362` | Grouped under personal security |
| **Topbar Avatar Menu** | Scoped Bot API Keys & OAuth (`/settings/mcp`) | Keep | Topbar Avatar Menu (Developer Group) | `KAN-362` | Fast developer key access |
| **Topbar Avatar Menu** | Workspace Settings (`/workspaces/settings`) | Move / Dedup | Sidebar Workspace Header Gear | `KAN-363` | Eliminates topbar duplication |
| **Topbar Avatar Menu** | Workspace AI Studio (`/workspaces/settings/ai`) | Consolidate | Unified Admin Studio Subnav | `KAN-362`, `KAN-363` | Merged with Server AI surface |
| **Topbar Avatar Menu** | Diagnostics & Link Inspector (`/admin/link-auditor` -> `/admin/diagnostics`) | Consolidate | Unified Admin Studio Subnav & Hub | `KAN-362` | Elevated to top-level admin hub |
| **Topbar Avatar Menu** | Admin Auth Studio (`/admin/auth`) | Consolidate | Unified Admin Studio Subnav & Hub | `KAN-362` | Part of 8-studio admin hub |
| **Topbar Avatar Menu** | AI Providers & Token Caps (`/admin/ai`) | Consolidate | Unified Admin Studio Subnav & Hub | `KAN-362` | Part of 8-studio admin hub |
| **Topbar Avatar Menu** | Autonomous Agents (`/admin/agents`) | Consolidate | Unified Admin Studio Subnav & Hub | `KAN-362` | Merged under AI & Agents |
| **Topbar Avatar Menu** | Remote mTLS Runners (`/admin/agent-runners`) | Consolidate | Unified Admin Studio Subnav & Hub | `KAN-362` | Part of 8-studio admin hub |
| **Topbar Avatar Menu** | Standalone & Backup (`/admin/standalone`) | Consolidate | Unified Admin Studio Subnav & Hub | `KAN-362` | Part of 8-studio admin hub |
| **Topbar Avatar Menu** | (Missing) OAuth Apps (`/admin/oauth`) | Add to Hub | Unified Admin Studio Subnav & Hub | `KAN-362` | Was missing from topbar |
| **Topbar Avatar Menu** | (Missing) Plane Import Studio (`/admin/imports`) | Add to Hub | Unified Admin Studio Subnav & Hub | `KAN-362` | Was missing from topbar |
| **Topbar Avatar Menu** | Documentation (`/docs`) | Remove / Dedup | Topbar Header Pill & Sidebar Footer | `KAN-363` | Triple duplicate across UI |
| **Topbar Avatar Menu** | About 👍kanban (`/about`) | Keep / Clean | Topbar Avatar & Sidebar Footer | `KAN-363` | Clean modal/page entry |
| **Topbar Avatar Menu** | Sign Out | Keep | Topbar Avatar Footer | `KAN-362` | Standard exit action |
| **Topbar Header** | Docs Pill (`/docs`) | Keep | Topbar Header Right Pill | `KAN-363` | Visible 1-click global docs |
| **Topbar Header** | Notifications Bell | Keep | Topbar Header Right Action | `KAN-362` | Unread notification tray |
| **Topbar Header** | Theme Toggle | Keep | Topbar Header Right Action | `KAN-362` | Light/Dark/System switch |
| **Topbar Header** | Command Palette Trigger (`Cmd+K`) | Keep | Topbar Header Center Action | `KAN-362` | Global search & shortcut |
| **Topbar Header** | Quick Create (`+`) | Keep | Topbar Header Center Action | `KAN-362` | Universal issue creation |
| **Admin Studios Subnav** | Bot API Keys (`/admin/mcp`) | Expand | Unified 8-Studio Admin Subnav | `KAN-362` | Global MCP server governance |
| **Admin Studios Subnav** | OAuth 2.1 Clients (`/admin/oauth`) | Expand | Unified 8-Studio Admin Subnav | `KAN-362` | Client app governance |
| **Admin Studios Subnav** | Plane Migration Studio (`/admin/imports`) | Expand | Unified 8-Studio Admin Subnav | `KAN-362` | Migration and CSV importer |
| **Admin Studios Subnav** | (Missing) Auth Cards (`/admin/auth`) | Add | Unified 8-Studio Admin Subnav | `KAN-362` | Added to unified subnav |
| **Admin Studios Subnav** | (Missing) AI Providers (`/admin/ai`) | Add | Unified 8-Studio Admin Subnav | `KAN-362` | Added to unified subnav |
| **Admin Studios Subnav** | (Missing) Remote Runners (`/admin/runners`) | Add | Unified 8-Studio Admin Subnav | `KAN-362` | Added to unified subnav |
| **Admin Studios Subnav** | (Missing) Standalone Backup (`/admin/standalone`) | Add | Unified 8-Studio Admin Subnav | `KAN-362` | Added to unified subnav |
| **Admin Studios Subnav** | (Missing) Diagnostics (`/admin/diagnostics`) | Add | Unified 8-Studio Admin Subnav | `KAN-362` | Added to unified subnav |
| **Sidebar Workspace Section** | Workspace Switcher Dropdown | Keep | Sidebar Top Section | `KAN-363` | Tenant context selector |
| **Sidebar Workspace Section** | Workspace Settings (`/workspaces/settings`) | Keep | Sidebar Top Section (Gear Icon) | `KAN-363` | Canonical workspace config |
| **Sidebar Primary Nav** | Your Work (`/`) | Keep | Sidebar Primary Section | `KAN-364` | User assigned / created work |
| **Sidebar Primary Nav** | Sticky Notes (`/stickies`) | Keep | Sidebar Primary Section | `KAN-364` | Quick scratchpad & ideas |
| **Sidebar Primary Nav** | All Issues (`/issues`) | Keep | Sidebar Primary Section | `KAN-364` | Cross-project triage |
| **Sidebar Primary Nav** | Documentation (`/docs` line 766) | Remove / Dedup | Sidebar Footer Only | `KAN-363` | Eliminates sidebar duplicate |
| **Sidebar Project Tree** | Project Work Items (`/projects/:key/issues`) | Keep | Project Tree Root Node | `KAN-364` | Primary project navigation |
| **Sidebar Project Tree** | 5 Layout Sublinks (Board, List, Table, Cal, Timeline) | Consolidate | Layout Switcher Toolbar / Submenu | `KAN-364` | Replaces 5 vertical tree rows |
| **Sidebar Project Tree** | Cycles (`/projects/:key/cycles`) | Keep | Project Tree Sub-surface | `KAN-364` | Sprints and timeboxes |
| **Sidebar Project Tree** | Modules (`/projects/:key/modules`) | Keep (Conditional) | Project Tree Sub-surface | `KAN-364` | Hidden if modules disabled |
| **Sidebar Project Tree** | Docs (`/projects/:key/docs`) | Keep (Clarify) | Project Tree Sub-surface | `KAN-363`, `KAN-364` | Distinct from global `/docs` |
| **Sidebar Project Tree** | Analytics (`/projects/:key/analytics`) | Keep | Project Tree Sub-surface | `KAN-364` | Flow telemetry & metrics |
| **Sidebar Project Tree** | Workflows (`/projects/:key/settings/workflows`) | Move to Tab | Project Settings Sub-Tabs | `KAN-364` | Reduces project tree clutter |
| **Sidebar Project Tree** | Custom Fields (`/projects/:key/settings/custom-fields`) | Move to Tab | Project Settings Sub-Tabs | `KAN-364` | Reduces project tree clutter |
| **Sidebar Project Tree** | Project Settings (`/projects/:key/settings`) | Consolidate | Unified Project Settings Hub | `KAN-364` | Houses General, States, Workflows, Fields |
| **Sidebar Footer** | Documentation (`/docs`) | Keep | Sidebar Footer | `KAN-363` | Canonical sidebar docs link |
| **Sidebar Footer** | About 👍kanban (`/about`) | Keep | Sidebar Footer | `KAN-363` | Canonical sidebar about link |
| **View Toolbar (List)** | State Filter Popover | Standardize | Unified View Toolbar Across Layouts | `KAN-365` | Consistent across all 5 layouts |
| **View Toolbar (List)** | Search DSL Input (`IssueNavigatorBar`) | Standardize | Unified View Toolbar Across Layouts | `KAN-365` | Filter queries across layouts |
| **View Toolbar (List)** | Saved Views Dropdown | Standardize | Unified View Toolbar Across Layouts | `KAN-365` | View persistence across layouts |
| **View Toolbar (List)** | Export Actions (Reports, CSV) | Standardize | Unified View Toolbar Across Layouts | `KAN-365` | Unified export menu across layouts |
| **View Toolbar (Non-List)** | Display Popover (`FilterDisplayBar`) | Enhance | Unified View Toolbar Across Layouts | `KAN-365` | Adds display settings beyond 1 button |
| **Issue Header (Drawer)** | Back / Close Button | Keep | Drawer / Fullscreen Header | `KAN-366` | Navigation back to parent view |
| **Issue Header (Drawer)** | Fullscreen Toggle (`↗` / `↙`) | Keep | Drawer Header Right | `KAN-366` | Fast modal size expansion |
| **Issue Header (Drawer)** | Copy Key Button (`📋`) | Keep | Issue Key Group | `KAN-366` | Fast issue identifier copy |
| **Issue Header (Drawer)** | Copy Link Button (`🔗`) | Keep | Issue Key Group | `KAN-366` | Canonical web URL clipboard copy |
| **Issue Header (Drawer)** | Link Graph Trigger (`🔗` -> `🕸️`) | Disambiguate | Drawer Action Slots | `KAN-366` | Distinguish from Copy Link |
| **Issue Header (Drawer)** | Subscribe Action | Keep | Drawer Action Slots | `KAN-366` | In-app / email notification toggle |
| **Issue Header (Drawer)** | Overflow Menu (Copy, Archive, Delete) | Keep | Drawer Action Slots | `KAN-366` | Destructive & structural operations |
| **Split View Header** | Sequential Pager (`^` / `v`) | Keep | Split-Pane Header | `KAN-366` | Master-detail keyboard triage |
| **Split View Toolbar** | Edit Description | Keep | Split Action Toolbar | `KAN-366` | Fast inline edit |
| **Split View Toolbar** | Add Comment | Keep | Split Action Toolbar | `KAN-366` | Quick comment focus |
| **Split View Toolbar** | Assign to Me | Keep | Split Action Toolbar | `KAN-366` | 1-click self-assignment |
| **Split View Toolbar** | State Selector | Keep | Split Action Toolbar | `KAN-366` | Fast transition workflow |
| **Split View Toolbar** | Favorite Toggle | Keep | Split Action Toolbar | `KAN-366` | User star/favorite state |
| **Split View Toolbar** | Share / Export | Keep | Split Action Toolbar | `KAN-366` | Copy share link |
| **Split View Toolbar** | (Missing) Subscribe Action | Add | Split Action Toolbar Slots | `KAN-366` | Restored parity with drawer |
| **Split View Toolbar** | (Missing) Link Graph Action | Add | Split Action Toolbar Slots | `KAN-366` | Restored parity with drawer |
| **Split View Toolbar** | (Missing) Overflow Menu | Add | Split Action Toolbar Slots | `KAN-366` | Restored parity with drawer |

---

## 3. Spawned Child Ticket Hierarchy Ledger

All child tickets have been created on project `KAN` with `parent: "KAN-318"` and `state: "Todo"`:

1. **`KAN-362`**: `[KB-MENU-TOPBAR-ADMIN] Topbar Avatar Menu Consolidation & Unified Admin Studio Hub Subnav`
   - **Target Files:** `kanban/web/src/app/Topbar.tsx`, `kanban/web/src/app/routes.tsx`, `kanban/web/src/features/admin/AdminStudioSubnav.tsx`, `kanban/web/src/features/settings/McpAccessStudio.tsx`
   - **Domain:** Topbar Avatar Menu and unified 8-studio admin navigation hub.

2. **`KAN-363`**: `[KB-MENU-DEDUP-GLOBAL] Eliminate Duplicate Docs, About, Workspace Settings, and AI Studio Navigation Links`
   - **Target Files:** `kanban/web/src/app/Topbar.tsx`, `kanban/web/src/app/Sidebar.tsx`, `kanban/web/src/features/settings/PersonalSettingsPage.tsx`
   - **Domain:** Elimination of redundant `/docs`, `/about`, and `/workspaces/settings` entries while clarifying project `/projects/:key/docs` distinction.

3. **`KAN-364`**: `[KB-MENU-SIDEBAR-PROJECT] Sidebar Project Tree & LayoutSwitcher Consolidation with Project Settings Tabs`
   - **Target Files:** `kanban/web/src/app/Sidebar.tsx`, `kanban/web/src/app/LayoutSwitcher.tsx`, `kanban/web/src/features/settings/ProjectSettingsPage.tsx`, `kanban/web/src/app/AppShell.tsx`
   - **Domain:** Streamlined project tree in sidebar, layout switcher enablement, and consolidation of Workflows and Custom Fields into Project Settings tabs.

4. **`KAN-365`**: `[KB-MENU-VIEW-TOOLBAR] Unified Filter, View, and Export Toolbar Architecture Across All Layouts`
   - **Target Files:** `kanban/web/src/features/views/IssueNavigatorBar.tsx`, `kanban/web/src/features/views/FilterDisplayBar.tsx`, `kanban/web/src/features/views/viewRegistry.tsx`
   - **Domain:** Unified filter, search, saved view, and report/CSV export toolbar across all 5 layouts.

5. **`KAN-366`**: `[KB-MENU-ISSUE-ACTIONS] Issue Header & Split-Pane Action Bar Parity with Duplicate Control Elimination`
   - **Target Files:** `kanban/web/src/features/drawer/IssueHeader.tsx`, `kanban/web/src/features/drawer/IssueSurface.tsx`, `kanban/web/src/features/drawer-actions/LinkGraphAction.tsx`, `kanban/web/src/features/drawer-actions/IssueOverflowMenu.tsx`
   - **Domain:** Full action parity in split-pane view (Subscribe, Link Graph, Overflow) and deduplication of adjacent link icons and fullscreen toggles.

---

## 4. Verification and Forensic Strategy

1. **Automated Unit Testing (`kanban/web/src/app/__tests__/MenuConsolidation.test.tsx`):**
   - Verifies Topbar avatar menu items for admin vs standard roles.
   - Verifies AdminStudioSubnav highlights active studio and supports all 8 admin destinations.
   - Verifies Split-Pane IssueSurface renders SubscribeSlot, LinkSlot, and OverflowSlot.
   - Verifies LinkGraphAction and Copy Link buttons render distinct visual cues and accessible labels.
   - Verifies `/admin/mcp` route mounts cleanly with server scope.
   - Coverage target: `>=95%` on all new and modified navigation components.

2. **Responsive Browser Verification (5 Viewports):**
   - Desktop Light (`1440x900`): Full navigation bar, Topbar avatar dropdown, unified toolbar.
   - Desktop Dark (`1440x900`): Dark theme contrast, unclipped popovers, clean styling tokens.
   - Tablet Portrait (`768x1024`): Responsive layout reflow, touch-accessible tap targets.
   - Mobile Portrait (`390x844`): Collapsible sidebar drawer, overflow menu actions.
   - Mobile Landscape (`844x390`): Vertical containment, scrollable action menus.

3. **Passive Forensic Packet (`docs/qa/KAN-318/`):**
   - Raw diffs, unit test outputs, build/typecheck logs, screenshots, and dual specialist audits.
