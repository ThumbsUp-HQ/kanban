# Forensic QA Verification Packet: KANBA-106 (KB-P4-14)

## Executive Summary
- **Ticket ID:** `KANBA-106` (`KB-P4-14`)
- **Title:** `[Phase 4 / MCP] Hierarchical Scopable Keys: Global, Per-Workspace, Per-Project & Per-User Self-Service Keys + Capability/Tool Narrowing`
- **Author:** `p4-106` (Agent Worker)
- **Status:** READY for Forensic QA Audit by `reality-checker`
- **Branch/Worktree:** `swarm-p4-106-d88e3656` -> synced to `/home/adamoutler/kanban`

---

## 1. Scope & Implementation Overview

This change delivers the complete hierarchical MCP key infrastructure across the database, core security engine, REST API layers, MCP server protocol handler, and React web client:

### A. Database Layer (`database/`)
1. **Migration `p4_14_mcp_scopable_keys`:**
   - Modified `mcp_api_keys` to allow nullable `workspace_id` and nullable `expires_at`.
   - Added `scope_tier` (`global`, `workspace`, `project`), `owner_kind` (`personal_user`, `service_bot`), `project_id`, `allowed_workspace_ids`, `allowed_project_ids`, `capability_mask`, `allowed_tools`, `disabled_tools`, and `allowed_cidrs`.
   - Enforced database-level check constraint `mcp_keys_tier_shape_chk` requiring strict tier foreign-key shapes.
   - Enforced `mcp_api_keys_expires_at_check` allowing `NULL` only for unlimited keys, otherwise capped at 365 days.
   - Updated `FORCE ROW LEVEL SECURITY` policies (`select`, `insert`, `update`, `delete`) with server-admin, workspace-admin, project-admin, and personal-user ownership boundaries.
   - Updated `introspect_mcp_api_key(BYTEA)` Security Definer SQL function returning 20 columns.
2. **SQLAlchemy Model (`database/models/mcp_api_key.py`):**
   - Mapped all new columns, check constraints, foreign keys, and indexes.

### B. Security & Backend APIs (`kanban/`)
1. **Security Engine (`kanban/security/mcp_keys.py`):**
   - Implemented `mint_mcp_api_key`, `introspect_subject_token`, and `evaluate_key_boundary`.
   - Validates tier shape, IP CIDR boundaries (`allowed_cidrs`), capability masks (1 to 255), and explicit friction confirmation for unlimited keys.
2. **Personal Keys Self-Service API (`kanban/api/v1/auth_mcp_keys.py`):**
   - Endpoints: `POST /api/v1/auth/mcp-keys`, `GET /api/v1/auth/mcp-keys`, `DELETE /api/v1/auth/mcp-keys/{key_id}`.
   - Bound to authenticated user session (`owner_kind="personal_user"`), enforcing 100% test coverage.
3. **Admin Keys API (`kanban/api/v1/admin/mcp_keys.py`):**
   - Protected with `Depends(require_admin_aal2)`.
   - Supports minting and managing `global`, `workspace`, and `project` keys with IP CIDR constraints and global key deletion protections.
4. **Settings & System Status (`kanban/settings.py` & `kanban/api/v1/system_status.py`):**
   - Environment flags `KANBAN_DISABLE_UNLIMITED_MCP_KEYS` / `KB_DISABLE_UNLIMITED_MCP_KEYS`.
   - Exposes `allow_unlimited_mcp_keys: bool` on `GET /api/v1/system/status`.
   - Returns `422 UNLIMITED_KEY_FORBIDDEN` if server policy blocks unlimited keys, and `422 UNLIMITED_CONFIRMATION_REQUIRED` if client omits confirmation.

### C. Protocol & Middleware (`mcp/`)
1. **Authentication Middleware (`mcp/auth.py`):**
   - Inspects client IP address against `auth_context.allowed_cidrs` and rejects unauthorized addresses with `McpErrorCode.INTERNAL_ERROR` / `FORBIDDEN_CIDR`.
2. **Protocol Tool Narrowing (`mcp/protocol.py`):**
   - `tools/list`: filters out any tools listed in `auth_context.disabled_tools` or missing from `auth_context.allowed_tools`.
   - `tools/call`: actively blocks invocation of disabled tools with `McpErrorCode.INSUFFICIENT_SCOPE`.

### D. Frontend Web Client (`kanban/web/`)
1. **McpAccessStudio (`McpAccessStudio.tsx` & `McpAccessStudio.css`):**
   - Renders hierarchical scope badges (`Global`, `Workspace`, `Project`, `Personal`).
   - "Expires" column renders `Never (Unlimited)` badge when `expires_at` is null.
   - Exposes `"Unlimited (not recommended)"` option in expiration dropdown (dynamically hidden when `allow_unlimited_mcp_keys` is false).
   - High-visibility friction warning banner and explicit confirmation checkbox.
   - Granular tool disabling grid (`data-testid="tools-selection-grid"`) with checkboxes for all surface tools.

---

## 2. Forensic Proof Inventory

All forensic artifacts are generated and verified in `docs/qa/KANBA-106/`:

| Artifact | Description |
| :--- | :--- |
| `git-diff.patch` | Complete unified patch against base (164 KB) |
| `unit-test-results.txt` | Pytest (14 passed, 98% coverage) + Vitest (15 passed) + Playwright (9 passed) |
| `build-check.txt` | Clean Ruff check, Ruff format check, Mypy (0 issues), ESLint (0 warnings), Vite build |
| `schema-dump.sql` | Exact PostgreSQL table definition, constraints, indexes, RLS policies, and SQL functions |
| `contract-sample.json` | Sample JSON payloads for minting, introspection, system status, and error envelopes |
| `mcp-transcript.txt` | MCP protocol transcript showing tool listing pruning, execution, and denied calls |
| `screenshots/` | 9 annotated responsive Playwright screenshots (Desktop, Tablet, Mobile) |
| `message-to-reality-checker.md` | This authoritative forensic QA packet |

### Responsive Annotated Screenshot Proofs:
1. `screenshots/01-mcp-studio-hierarchical-overview-desktop.png`
2. `screenshots/01-mcp-studio-hierarchical-overview-tablet.png`
3. `screenshots/01-mcp-studio-hierarchical-overview-mobile.png`
4. `screenshots/02-mint-modal-unlimited-warning-desktop.png`
5. `screenshots/02-mint-modal-unlimited-warning-tablet.png`
6. `screenshots/02-mint-modal-unlimited-warning-mobile.png`
7. `screenshots/03-mint-modal-tool-narrowing-desktop.png`
8. `screenshots/03-mint-modal-tool-narrowing-tablet.png`
9. `screenshots/03-mint-modal-tool-narrowing-mobile.png`

---

## 3. Test Coverage Summary
- `kanban/api/v1/auth_mcp_keys.py`: **100% statement coverage**
- `kanban/api/v1/admin/mcp_keys.py`: **97% statement coverage**
- Combined modified API surface: **98% statement coverage** (exceeds 95% project threshold)

---

## 4. Invariant Verification Checklist
- [x] Zero compilation or linter warnings across Python and TypeScript.
- [x] Strict safe typing in both backend and frontend.
- [x] Check constraint `mcp_keys_tier_shape_chk` rejects invalid scope/foreign-key tuples.
- [x] RLS policies enforced under `FORCE ROW LEVEL SECURITY`.
- [x] Plain ASCII characters used exclusively for punctuation in external copy (no em-dashes).
- [x] Code and forensic proof files synchronized to `/home/adamoutler/kanban`.
- [x] Dual specialist reviews (@api-specialist and @ui-specialist) requested on swarm board.
