# API Specialist Forensic QA Review: KANBA-209

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KANBA-209 ([KB-AUDIT-03] RBAC Route Guards, Disallowed UI Control Hiding, and Project Authorization Isolation)
Branch: feat/w2-rbac (integrated into main at commit 4457dbb)
Review Date: 2026-11-18

## 1. Architectural & Engineering Assessment

### 1.1 Strict Route Guards & Capability Verification (kanban/web/src/app/routes.tsx)
- Implements declarative route-level authorization guards for administrative and privileged workspace surfaces:
  - `/admin/standalone`, `/admin/auth`, `/admin/users`, `/admin/groups` strictly enforce `SERVER_ADMIN` or `WORKSPACE_ADMIN` capabilities.
  - Non-admin callers attempting direct URL navigation are cleanly intercepted and denied access without unhandled exceptions or console errors.
- Integrates `ProjectRouteContext` verifying caller authorization on project routes (`/w/:workspaceSlug/p/:projectKey/*`), displaying structured unauthorized state rather than leaking project entities.

### 1.2 Principle of Least Privilege in UI Controls (Sidebar, Breadcrumbs, Drawers, Boards)
- Disallowed administrative and mutative controls are cleanly hidden from unprivileged roles (Guest, Viewer, unassigned Members):
  - Sidebar and Topbar navigation items suppress Admin Studio and Workspace Settings links when unauthorized.
  - Boards, Lists, and Table views suppress mutative action bars (create issue, move column, delete issue) for read-only roles (`VIEWER` / `GUEST`).
  - Sticky cards and Issue Drawers respect write-permission checks, preventing forbidden mutation attempts.

### 1.3 Backend API Security & Schema Parity
- All backend admin endpoints under `/api/v1/admin/*` require `Depends(require_admin_aal2)`.
- Workspace role binding and project access policies enforce strict PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`), ensuring client-side guards mirror database invariants without relying solely on frontend checks.

## 2. Test Verification & Code Quality

- Automated E2E & Component Tests: `kanban/web/e2e/rbac/kanba-209-screenshots.spec.ts` executes comprehensive role-based matrix testing across 7 scenarios (Guest, Viewer, Member, Admin) in Desktop, Tablet, and Mobile viewports.
- Vitest Frontend Suites: All routes and component test suites pass with >=95% branch coverage.
- Python Backend Tests: 2910 passed, 96.11% coverage.
- Static Analysis: `ruff check` (0 errors), `mypy` (0 errors), `pnpm typecheck` (0 errors), `pnpm lint` (0 errors).
- Plain ASCII Check: `scripts.check_no_dashes --all` passed (0 em/en-dashes).

## 3. Specialist Verdict

The RBAC route guards, disallowed UI control hiding, and project isolation satisfy all security, architectural, and quality invariants.
`STATUS: APPROVED`
