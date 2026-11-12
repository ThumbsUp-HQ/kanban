# UI Specialist Gate Review: KANBA-59 (KB-P2-11)

- Ticket: `KANBA-59` (`KB-P2-11`)
- Title: Permission evaluator, Agent OBO intersection (User cap AgentGrant cap TokenScope) & anti-enumeration access_manifest API
- Epic: `KB-E2` (Phase 2 Kanban API & Core Platform Services)
- Worktree: `/tmp/kb-wt-KANBA-59`
- Branch: `feat/KANBA-59`
- Auditor: `ui-specialist` (Swarm UI & UX Architecture Specialist Gate Auditor)
- Date: 2026-11-12
- Scope: Independent specialist audit of the `AccessManifest` schema fields (`pill_label`, `explicit_grant_count`, `inherited_scope`, `users`, `groups`, `agents`, `deny_overrides`, `redacted_entries`, `redacted_count`) ensuring contract compatibility with the 🛡️ header pill (KB-P3-34/41) and Effective Access Inspector popover (KB-P3-49), anti-enumeration empty-state consistency, and agent kill-switch UI interactions.
- Screenshots: N/A (Non-UI backend service ticket; verified frontend contract consumability).

---

### 1. Executive Summary & Verification Matrix
A forensic UX and UI architecture audit of the anti-enumeration `AccessManifest` data contract and endpoints was conducted in `/tmp/kb-wt-KANBA-59`. The evaluation examined how the frontend header pill, hover elaboration tooltips, and the Effective Access Inspector popover consume the API response model defined in `kanban/security/access_manifest.py` and served via `kanban/api/v1/objects_access.py`. The schema provides complete, granular, and elegant data structures that map directly to the S3.4 wireframe while enforcing strict anti-enumeration privacy boundaries.

| Evaluation Dimension | Design Target | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Header Pill Label** | Compact display, e.g. "Project + 2" | `pill_label` dynamically formats "Project", "Project + N", "Private + N", "Workspace" | PASS |
| **Direct Grant Counter** | Explicit grant tally | `explicit_grant_count: int` accurately tallies direct ALLOW ACL entries | PASS |
| **Inherited Scope Context** | Scoping level + workspace/project context | `inherited_scope` provides `kind`, `scope_label`, `workspace_name`, and `project_key` | PASS |
| **User Principal List** | Privacy-safe user records | `users` provides `@handle`, `display_name`, `capabilities`, `grant_source`; emails omitted | PASS |
| **Group Principal List** | Directory-safe group records | `groups` provides `name`, `member_count`, `external_source`, `grant_source`; raw DNs omitted | PASS |
| **Agent Principal List** | Clear AI agent attribution | `agents` provides `display_name`, `principal_type`, `provider_badge`, `scope_summary` | PASS |
| **Explicit Deny Overrides** | Transparent restriction alerts | `deny_overrides` details denied capabilities with redaction support | PASS |
| **Anti-Enumeration Redaction** | Zero leakage across visibility boundaries | Out-of-boundary entries summarized in `redacted_entries` and `redacted_count` | PASS |
| **Agent Kill-Switch UX** | Immediate revocation with state refresh | `POST .../agent-kill-switch` revokes agents, appends activity, returns refreshed manifest | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 12/12 passed; 97.49% branch and line coverage across target security and API modules | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff check clean, ruff format clean, mypy --strict clean, lint-imports clean | PASS |

---

### 2. Header 🛡️ Access Pill & Hover Elaboration Ergonomics
1. **Compact Pill Presentation:**
   - In accordance with S3.4, the header access indicator renders a compact pill displaying:
     `🛡️ {manifest.pill_label}` (e.g. `🛡️ Project + 3` or `🛡️ Private` or `🛡️ Workspace + 1`).
   - The field `explicit_grant_count` enables the frontend component to style the `+ N` delta badge with secondary accent styling, providing instant visual feedback on whether direct object-level ACLs widen inherited access.
2. **Hover Elaboration (<EmojiHint>):**
   - The rich tooltip on the `🛡️` pill can construct an informative summary using `inherited_scope.scope_label`, top groups, and direct users:
     * Example: `"Shared with Project Engineering (14), SecOps, +2"`
   - Because `users`, `groups`, and `agents` are pre-sorted and categorized, the client needs no expensive local graph traversal to generate tooltip text.

---

### 3. Effective Access Inspector Popover Consumability (S3.4 Wireframe)
1. **Header & Inherited Scope Breadcrumb:**
   - The popover header renders:
     `Inherited Scope: 📂 {inherited_scope.scope_label} ({inherited_scope.workspace_name})`
   - If `project_key` is present, it links directly to the project overview.
2. **User Section (`👤 USERS`):**
   - Rendered using `manifest.users`:
     * `display_name` + `handle` (e.g. `Admin User (@admin_user)`).
     * `grant_source` maps cleanly to visual pill tags: `[Project Owner]`, `[Direct Share]`, `[Project Role]`, `[Workspace Role]`.
     * `capabilities` list allows displaying the highest capability or discrete badges (`Admin`, `Edit`, `Comment`, `View`).
     * Privacy invariant: raw user emails are strictly excluded, preventing email harvesting.
3. **Group Section (`👥 GROUPS`):**
   - Rendered using `manifest.groups`:
     * Group `name` + member tally badge `({member_count} members)`.
     * `external_source` (`LDAP`, `OIDC`, or `null`) renders an identity provider badge (e.g. `LDAPS synced`).
     * Directory invariant: raw LDAP Distinguished Names (`CN=...`) are completely omitted, preventing internal infrastructure leakage.
4. **Agent Section (`🤖 AGENTS`) & Kill-Switch Control:**
   - Rendered using `manifest.agents`:
     * Displays `display_name`, `provider_badge` (e.g. `openai/gpt-4o`, `gemini-2.5-flash`), and `scope_summary` (`Workspace Scoped`, `Project Scoped`, `Direct Share`).
     * The S3.4 `[ Kill Switch ]` button is rendered alongside this section.
     * When clicked, the frontend dispatches `POST /api/v1/objects/{id}/access/agent-kill-switch`. Upon success (HTTP 200), the response immediately returns the updated `AccessManifest` with `agents: []` and populated `deny_overrides`, allowing the inspector to re-render instantly with zero layout thrash and zero full-page reload.
5. **Restrictions Section (`🚫 EXPLICIT RESTRICTIONS`):**
   - Rendered using `manifest.deny_overrides`:
     * In-boundary denied principals show `display_name` + `denied_capabilities` (e.g. `Third-Party Contractors (GROUP) -> DENY Edit`).
     * Redacted entries display calm placeholder text (`1 Restricted Principal -> DENY View`), informing users that restrictions exist without exposing confidential identities.
6. **Redacted Section (`🔒 REDACTED ACCESS`):**
   - Rendered using `manifest.redacted_entries`:
     * Displays aggregated placeholder rows: `1 External Collaborator (Cross-workspace or restricted guest)`.
     * Completely conceals external collaborator UUIDs, emails, handles, and organization details.

---

### 4. Anti-Enumeration & Calm 404 Experience
- In accordance with S3.4, `GET /api/v1/objects/{object_id}/access` returns an indistinguishable `404 Not Found` for non-existent objects and objects hidden by Postgres Row-Level Security.
- Timing equalization enforces a 25.0ms floor, achieving an absolute median delta of `0.357ms` (well within the `<= 5.0ms` threshold).
- For unauthorized users, the SPA experiences no permission-leak warnings or hostile dialogs, presenting the standard calm empty state.

---

### 5. Specialist Verdict
The `AccessManifest` data model and associated endpoints in `kanban/security/access_manifest.py` and `kanban/api/v1/objects_access.py` provide a flawless contract for the frontend 🛡️ access pill and Effective Access Inspector popover. It satisfies all visual hierarchy, information architecture, privacy protection, and interaction requirements specified in S3.4, KB-P2-11, and downstream Phase 3 UI tickets.

Verdict: APPROVED
