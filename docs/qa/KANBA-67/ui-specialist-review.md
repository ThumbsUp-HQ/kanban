# UI Specialist Gate Review: KANBA-67 (KB-P3-01a)

- Ticket: `KANBA-67` (`KB-P3-01a`)
- Title: Project architect API (part a): projects CRUD, module defaults & shared activity/contract infrastructure
- Epic: `KB-E3` (Phase 3 Frontend Web SPA & Design System)
- Worktree: `/tmp/kb-wt-KANBA-67`
- Branch: `feat/KANBA-67`
- Auditor: `ui-specialist` (Swarm UI & UX Architecture Specialist Gate Auditor)
- Date: 2026-11-12
- Scope: Independent specialist audit of the Project CRUD API response contracts, evaluation of the `capabilities` array for UI control and button state gating in the Project Settings view, verification of error `code` values for inline form validation and alert banners, and validation of the full `AccessManifest` model for header pill and inspector rendering.
- Screenshots: N/A (Non-UI backend service ticket; verified API consumability for Project Settings UI).

---

### 1. Executive Summary & Verification Matrix
A forensic UX and UI architecture audit of the Project Architect API endpoints was conducted in `/tmp/kb-wt-KANBA-67`. The review focused on the direct consumption of `ProjectResponse` and related error models by the future Project Settings SPA screens (general settings, module configuration, auto-archive policies, and access controls). The API design provides an exceptional developer experience for frontend components: caller permissions are explicitly exposed in `capabilities`, error codes map 1:1 to form fields and warning banners, and the full `AccessManifest` model provides all necessary data for topbar pill and access inspector rendering.

| Evaluation Dimension | Design Target | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Caller Capability Gating** | Explicit capabilities array for UI controls | `capabilities: list[str]` returned in every project read/write | PASS |
| **Error Code Granularity** | Stable machine-readable codes for form binding | `PROJECT_IDENTIFIER_TAKEN`, `MODULES_IN_USE`, `MODULES_DISABLED`, `MODULE_NOT_IN_PROJECT`, `IDENTIFIER_IMMUTABLE`, `DESCRIPTION_TOO_LARGE` | PASS |
| **Access Manifest Model** | Rich S3.4 metadata for Settings & Header Pill | Full `AccessManifest` (including structured `inherited_scope`, `users`, `groups`, `agents`, `deny_overrides`) | PASS |
| **Creation Admin Boundary** | Protect project container creation | 403 `INSUFFICIENT_CAPABILITY` on non-admin tokens or delegated OBO agents | PASS |
| **Calm 404 Anti-Enumeration** | Unified empty state for missing/unreadable | Jitter-equalized 404 with identical body and status for unreadable projects | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 21/21 passed; 99.29% branch and line coverage across target API and service modules | PASS |
| **Build & Lint Cleanliness** | Zero-Tolerance Quality Mandate | Ruff check clean, ruff format clean, mypy --strict clean, lint-imports clean | PASS |

---

### 2. UI Control & Form Field State Gating via `capabilities`
1. **Button & Input State Management:**
   - Every `ProjectResponse` returns the caller's effective capabilities computed dynamically via PostgreSQL RLS and capability bitmasks:
     * `capabilities: ["VIEW", "COMMENT", "EDIT", "TRANSITION", "LINK", "SHARE", "ADMIN", "DELETE"]`
   - In the Project Settings UI, this enables clean client-side conditional rendering without guessing or re-implementing ACL closure logic:
     * **Project Name & Description:** If `ADMIN` is in `capabilities`, inputs are editable; otherwise rendered in a disabled/read-only state with an explanatory `<EmojiHint>` tooltip.
     * **Modules Toggle:** If `ADMIN` is present, the toggle switch is interactive; otherwise locked.
     * **Module Defaults Card:** If `ADMIN` is present, multi-select dropdown and save actions are enabled.
     * **Save Changes & Delete Project Buttons:** Primary mutation buttons are hidden or disabled when `ADMIN` is absent, preventing confusing 403 round-trips for unauthorized members.
     * **Access Management:** Presence of `SHARE` or `ADMIN` gates the `[ Manage Access ]` and `[ Kill Switch ]` actions in the Effective Access Inspector.

---

### 3. Error `code` Mapping for Inline Form Validation & Banners
The RFC 7807 problem documents returned by the endpoints provide granular, machine-readable `code` members that map directly to form inputs, modal dialogs, and alert toasts:
1. `409 PROJECT_IDENTIFIER_TAKEN`:
   - Maps directly to the `identifier` input in the "Create Project" modal.
   - Frontend renders an inline field error (`aria-invalid="true"`): *"Identifier KAN is already in use. Please select a unique project slug."*
2. `409 MODULES_IN_USE`:
   - Occurs when an administrator attempts to disable modules on a project that still contains active module records.
   - Frontend presents an alert modal: *"Cannot disable modules while modules are in use. Please delete or migrate existing modules before disabling the feature."*
3. `422 MODULES_DISABLED`:
   - Occurs on `PUT /api/v1/projects/{ref}/module-defaults` if modules are disabled.
   - Frontend safely prevents opening the module defaults drawer when the feature toggle is off.
4. `422 MODULE_NOT_IN_PROJECT`:
   - Occurs if a selected module UUID belongs to another project container.
   - Frontend multi-select flags the offending token directly in the UI.
5. `422 IDENTIFIER_IMMUTABLE`:
   - Confirms that the project identifier is permanently locked after creation; settings UI marks the slug field as read-only.
6. `422 DESCRIPTION_TOO_LARGE`:
   - Maps to the description editor, enabling real-time byte count warnings if exceeding 512 KiB.
7. `403 INSUFFICIENT_CAPABILITY`:
   - Dispatches a standard toast notification explaining permission limitations without breaking UI state.

---

### 4. Review Points Scrutiny & Architectural Feedback
1. **Full `AccessManifest` Object in Response:**
   - *Author Inquiry:* In `ProjectResponse`, `access_manifest` is the full `AccessManifest` object (with structured `inherited_scope`), rather than the simplified string in the draft example.
   - *Verdict:* **Fully approved and strongly preferred.** Downstream UI components (specifically the topbar `🛡️` header pill in KB-P3-34/41 and the Effective Access Inspector popover in KB-P3-49) require `inherited_scope.kind`, `workspace_name`, and `workspace_id` to render scope breadcrumbs. Retaining the complete structured model eliminates secondary network queries and ensures seamless state synchronization between project settings and header access pills.
2. **Denying Project Creation for OBO Agents and Non-Admin Tokens:**
   - *Author Inquiry:* `POST /api/v1/projects` is denied with 403 for delegated OBO agents and tokens lacking `Capability.ADMIN`.
   - *Verdict:* **Fully approved.** Top-level project container creation is an administrative human action. Preventing delegated agents from creating arbitrary project hierarchies protects system resource quotas, prevents clutter, and maintains strict security boundaries.
3. **Coverage Concurrency Configuration:**
   - Adding `concurrency = ["greenlet", "thread"]` to `pyproject.toml` accurately resolves async SQLAlchemy coverage tracking across awaits, ensuring verified 99.29% coverage.

---

### 5. Specialist Verdict
The Project CRUD API, activity logging infrastructure, and error handling contracts in `kanban/api/v1/projects.py`, `kanban/api/v1/schemas/projects.py`, and `kanban/services/projects.py` perfectly fulfill all UI consumption requirements for the Project Settings interface. The data models, error codes, and permission arrays provide a cohesive, robust foundation for Phase 3 frontend components.

Verdict: APPROVED
