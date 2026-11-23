# API Specialist Review & Verification: KAN-356

- **Ticket ID:** KAN-356
- **Reviewer Persona:** Senior Backend & API Architect (`@api-spec`)
- **Target Surfaces:** REST API Endpoints, WebSocket Realtime Subscriptions, Router Contracts, and MCP/Client Data Boundaries
- **Audit Date:** 2026-11-23
- **Verdict:** APPROVED (Zero REST or MCP Contract Deviations; Router and Data Invariants 100% Preserved)

---

## 1. Scope & System Topology Audit

A comprehensive forensic audit of all route and component modifications under KAN-356 was conducted:
- **Modified Shell & Navigation Routing Components:**
  - `kanban/web/src/app/AppShell.tsx`: Enforced `<main id="main">` landmark presence during authenticated and initial auth loading states. Preserved realtime WebSocket subscriptions (`project:${activeProjectKey}`, `workspace:${workspaceId}`) and topbar user query (`GET /api/v1/auth/me`).
  - `kanban/web/src/app/routes.tsx`: Standardized heading hierarchy across router placeholders, drafts, cycles, and modules views without modifying URL route paths, query parameters, or route-level guards.
  - `kanban/web/src/features/docs/DocsWorkspaceView.tsx`: Converted empty editor pane container from nested `<main>` to `<section aria-label="Page Editor">` while preserving page and tree fetching queries (`qk.docsTree`, `qk.page`).
  - `kanban/web/src/features/docs/PageEditorPane.tsx`: Dynamically adapted container element to `<section>` when nested within the AppShell `<main id="main">` landmark, preserving all title change, markdown edit, and blur autosave mutations (`PATCH /api/v1/pages/{id}`).
  - `kanban/web/src/features/docs-center/DocsCenterPage.tsx`: Added top-level skip link, `<h1 className="sr-only">`, and `<main id="main">` landmark without altering chapter manifest loading or static documentation indexing.
  - `kanban/web/src/features/auth/LoginPage.tsx`: Enclosed sign-in surface within `<main id="main">` with skip link, preserving multi-card authentication discovery (`GET /api/v1/auth/cards`) and credential verification (`POST /api/v1/auth/login`).
  - `kanban/web/src/features/auth/SetupClaimPage.tsx`: Enclosed first-boot installation claim within `<main id="main">` with skip link, preserving claim verification and server administrator provisioning.
  - `kanban/web/src/features/oauth/DeviceActivatePage.tsx`: Enclosed CLI device activation within `<main id="main">` with skip link, preserving token verification and device approval endpoints.
  - `kanban/web/src/features/admin-auth/AuthStudioPage.tsx`, `kanban/web/src/features/workflows/WorkflowStudioPage.tsx`, `kanban/web/src/features/admin/LinkAuditorStudio.tsx`, and `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`: Converted inner container elements from `<main>` to `<div>` or `<section>` to prevent duplicate active `<main>` regions inside AppShell.
- **Created Verification Test Suite:**
  - `kanban/web/src/features/a11y/landmarksAndHeadings.test.tsx`: Implemented automated unit test coverage across all 3 mandated test cases with 10 passing tests.

Zero backend Python files, database migration schemas, or MCP tool definitions required modification, confirming zero backward-incompatible wire breaking changes.

---

## 2. Protocol, Routing, and Data Invariant Verification

1. **REST API Endpoint Contracts:**
   - All REST API calls across target views (`/api/v1/auth/me`, `/api/v1/auth/cards`, `/api/v1/auth/login`, `/api/v1/projects/{key}/analytics/flow`, `/api/v1/projects/{key}/cycles`, `/api/v1/projects/{key}/modules`, `/api/v1/docs/*`) retain identical HTTP methods, query parameters, request bodies, and error response handling.
2. **WebSocket & Realtime Subscription Invariants:**
   - In `AppShell.tsx`, `useRealtimeSubscription` continues to track project and workspace channels without interruption or re-subscription thrashing.
3. **Data-TestId and Automation Selectors:**
   - All data attributes (`data-testid="app-shell-auth-loading"`, `data-testid="docs-center-page"`, `data-testid="login-page"`, `data-testid="setup-claim-page"`, `data-testid="device-activate-layout"`, `data-testid="create-cycle-form"`, `data-testid="edit-cycle-modal"`, `data-testid="create-module-form"`, `data-testid="edit-module-modal"`) remain identical, preserving 100% compatibility with automated E2E test suites and reality-checker probes.
4. **Router State & Navigation:**
   - Route parameters (`:projectKey`, `:pageId`, `:slug`), URL search parameters (`layout`, `peek`, `create`), and history navigation actions operate identically to previous releases.

---

## 3. Specialist Sign-Off

The changes for KAN-356 cleanly enforce WAI-ARIA 1.2 landmark and heading standards at the presentation layer without altering API contracts or client-server wire integrity. Status: APPROVED.
