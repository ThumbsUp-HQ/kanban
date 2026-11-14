# UI Specialist Gate Review: KANBA-120 (KB-P2-10)

- **Ticket**: `KANBA-120` (`KB-P2-10`: Auth card admin API: CRUD, toggle, COLLATE "C" fractional reorder, live test-handshake & public enabled-cards endpoint)
- **Reviewer**: `@ui-specialist` (Frontend & UI/UX Specialist)
- **Branch**: `feat/KB-P2-10`
- **Worktree**: `/tmp/kb-wt-KB-P2-10`
- **Scope**: Downstream UI consumption contracts for `KB-P3-35` (Public Multi-Card Login) and `KB-P3-36` (Admin Auth Settings)
- **Board Ref**: Approved by `@ui-specialist` in Swarm Message #771

---

### 1. Consumer UX & Frontend Ergonomics Audit

#### A. Public Login View Consumption (`KB-P3-35`, Spec S4.3)
- **Deterministic Sort Ordering**: `GET /api/v1/auth/cards` returns cards strictly pre-ordered by `sort_rank COLLATE "C" ASC, id ASC`. The frontend consumer (`KB-P3-35`) can render cards sequentially without client-side re-sorting.
- **Button Presentation Metadata**: Each card projection contains `id`, `slug`, `display_name`, `button_subtext`, `icon_preset`, and `provider_kind`.
  - `display_name` provides the primary button title.
  - `button_subtext` allows secondary descriptive text (e.g. "Enterprise Directory Credentials").
  - `icon_preset` cleanly maps to client SVG icons (`google`, `github`, `gitlab`, `keycloak`, `azure`, `okta`, `ldap`, `local`).
- **Zero Configuration Leakage**: Complete exclusion of secret keys, client IDs, and discovery URLs protects public users and avoids client DOM bloat.
- **Start Navigation Ergonomics**: `GET /api/v1/auth/cards/{slug}/start?next=...` supports seamless single-click redirect for OIDC/OAuth2 authentication.

#### B. Admin Auth Studio Management (`KB-P3-36`, Spec S4.1, S4.2)
- **Drag & Drop Reordering**: The endpoint `POST /api/v1/admin/auth-cards/{card_ref}/reorder` accepting `{after: "<slug_or_id>" | null}` provides seamless integration with `@atlaskit/pragmatic-drag-and-drop` and keyboard reorder controls. The fractional base-62 rank assignment guarantees sub-millisecond updates without full table rewrites.
- **Auto-Rebalancing**: Transparent re-spacing when rank strings grow beyond 32 characters ensures long-term operational stability without manual admin intervention.
- **Live Health Diagnostics**: `POST /api/v1/admin/auth-cards/{card_ref}/test-handshake` provides instant admin verification with latency in milliseconds (`latency_ms`), status (`OK` vs `FAILED:<CODE>`), and actionable error details for display in admin toast notifications.
- **Anti-Lockout Dialogs**: Clear RFC 7807 problem payloads with `layer="db_trigger"` or `layer="handshake_probe_15m"` provide exact explanatory copy for frontend modal dialogs, preventing accidental administrator lockouts.
- **Destructive Deletion Confirmation**: The requirement for `{confirm_slug: "<slug>"}` on deletion matches Jira/GitHub destructive confirmation dialog patterns, preventing accidental removal.

---

### 2. Specialist Sign-Off
- **Verdict**: APPROVED. All response schemas, ordering guarantees, error structures, and validation boundaries perfectly fulfill the UX and design system contracts required by `KB-P3-35` and `KB-P3-36`.
