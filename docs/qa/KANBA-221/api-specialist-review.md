# API Specialist Forensic QA Review: KANBA-221

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KANBA-221 (Implement Live Your Work Hub, Global Cmd+K Hybrid Search, In-App Notifications, Saved Views Persistence, Table Inline Editing, and Timeline BLOCKS Arrows)
Branch: feat/w5-hubs (integrated into main at commit 423313f)
Review Date: 2026-11-19

## 1. Architectural & Engineering Assessment

### 1.1 Live Your Work Hub API Integration (kanban/web/src/features/your-work/YourWorkView.tsx)
- Replaces static `/projects/KAN/issues` mockup with live, authenticated queries to `/api/v1/issues`:
  - Assigned to Me: queries issues with `assignee_id: currentPrincipal.id` across accessible projects.
  - Created by Me: queries issues with `created_by_id: currentPrincipal.id`.
  - Subscribed: queries active subscription events and watched items.
- Preserves PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`), ensuring tenants cannot enumerate cross-tenant or unassigned issues.
- Integrated `?peek=` drawer queries cleanly without full-page navigation.

### 1.2 Global Hybrid Search & Command Palette (kanban/web/src/app/CommandPalette.tsx)
- Dispatches search queries against `/api/v1/search` and active workspace entity catalogs (Issues, Docs, Pages, Stickies).
- Enforces input debouncing (200ms) and minimum query length, mitigating backend search load spikes while maintaining snappy UX.
- Correctly formats search result metadata and suppresses unauthorized entity results.

### 1.3 Notifications Bell Integration (kanban/web/src/features/notifications/NotificationsBell.tsx)
- Connects to notification feed endpoints and WebSocket realtime channel `notifications:<principal_id>`.
- Supports batch and item-level read mutations (`POST /api/v1/notifications/{id}/read` and `POST /api/v1/notifications/read-all`).
- Preserves anti-enumeration principles by strictly scoping notification streams to authenticated principal sessions.

### 1.4 Saved Views Persistence & Views Route (kanban/web/src/features/views/)
- Wires `POST /api/v1/projects/{project_ref}/views` and `DELETE /api/v1/projects/{project_ref}/views/{view_id}`.
- Serializes layout configuration, column ordering, filter criteria, and grouping tokens into validated JSON payloads.
- Eliminates 404 redirections on `/projects/:key/views`, rendering the saved views manager page with direct view activation and deletion.

### 1.5 Table Inline Editing & Timeline Dependency Serialization
- Table view inline cell mutations dispatch typed `PATCH /api/v1/issues/{id}` requests with `If-Match` ETags.
- Mutations are capability-gated on client and server: unprivileged roles (`VIEWER` / `GUEST`) are blocked from editing.
- Timeline dependency visualization parses object links with link type `BLOCKS` and renders SVG Bezier curves without schema mutations.

## 2. Test Verification & Code Quality

- Frontend Vitest Suites: 2518 unit tests pass with >=95% branch coverage.
- Python Backend Tests: 2918 passed, 96.07% coverage.
- Architecture Contracts & Migrations: `lint-imports` passed; single linear head migration confirmed.
- Static Analysis: `ruff check` (0 errors), `mypy` (0 errors), `pnpm typecheck` (0 errors), `pnpm lint` (0 errors).
- Plain ASCII Check: `scripts.check_no_dashes --all` passed (0 em/en-dashes).

## 3. Wave 5 Sibling Ticket Verification (KANBA-222 and KANBA-214)

- `KANBA-222` (`docs/qa/KANBA-222/api-specialist-review.md`): Verified STATUS: APPROVED. Sparkle FIM completion (`/api/v1/sparkle/complete`), 25 MiB attachment upload with SVG sanitization, and consonant device code activation satisfy all security invariants.
- `KANBA-214` (`docs/qa/KANBA-214/api-specialist-review.md`): Verified STATUS: APPROVED. Project danger zone trash contract (`mode: "trash"`), `SERVER_ADMIN`-only permanent purge, restore actions, and trash-items querying satisfy all RLS and schema invariants.

## 4. Specialist Verdict

The Your Work hub API consumption, hybrid search integration, notifications tray, saved views persistence, and inline editing satisfy all architectural, reliability, and security invariants.
`STATUS: APPROVED`
