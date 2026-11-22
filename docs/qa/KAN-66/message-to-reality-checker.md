# Reality-Checker Verification Packet: KAN-66 (KB-SEC-04)

## Ticket Overview
- **Ticket ID**: `KAN-66`
- **Spec Section**: `KB-SEC-04` (S11.4, S7.2, S4.2 item 1, S3.2 item 2, S13.2)
- **Title**: `[KB-SEC-04] Enforce Immutable CredentialBoundary Across REST Bearer Auth, Workspace/Project Allowlists, CIDR, Capability Mask, & Tool Scope`
- **Git Branch**: `main` (merged from `feat/KAN-66-rest-credential-boundary`)
- **Merged `main` Commit SHA**: `ea104737b3071af8b0d7331325dad31425cdff5c` (`ea104737`, merging `a5d23fb913ca87601c20d93b39a3a103d237c0df`)
- **Browser Screenshots**: `N/A - Non-UI Security & REST Bearer CredentialBoundary Ticket`
- **Workspace**: `/home/adamoutler/kanban`

---

## Technical Actions & File Manifest

### Action 1: Immutable CredentialBoundary Attachment & Model Invariants
- **File**: `kanban/security/boundary.py` (New module)
  - Implements `@dataclass(frozen=True, slots=True) class CredentialBoundary`.
  - Carries immutable attributes: `scope_tier`, `surface`, `workspace_allowlist`, `project_allowlist`, `capability_mask`, `allowed_tools`, `allowed_cidrs`, `execution_id`, and `has_aal2_provenance`.
  - In `__post_init__`, normalizes inputs defensively into immutable structures (`frozenset`, `tuple`, `uuid.UUID`).
  - Implements `from_introspection(intro: McpIntrospectionResult)` constructing an immutable boundary directly from token introspection records.
  - Implements `EmptyCapabilitySet(frozenset)`: empty set comparison helper that compares equal to `0`, `Capability.NONE`, and empty sets, ensuring seamless backwards compatibility across callers expecting bitmasks or collections.
- **File**: `kanban/api/deps.py`
  - Added `credential_boundary: CredentialBoundary | None = None` to `PrincipalContext`.
  - Type-safe, circular-import-safe typing under `if TYPE_CHECKING:`.
- **File**: `kanban/security/mcp_keys.py`
  - Added `credential_boundary: CredentialBoundary | None = None` to `McpIntrospectionResult`.
  - Constructed and attached `CredentialBoundary` across introspections for ephemeral tokens (`kb_agt_eph_*`, `kb_eat_*`), API keys (`kb_pat_*`), and OAuth Bearer tokens.
- **File**: `kanban/auth/sessions/resolver.py`
  - `SessionCookieResolver.resolve(...)` extracts or builds `CredentialBoundary.from_introspection(intro)` upon Bearer token resolution and attaches it to the resulting `PrincipalContext`.

### Action 2: REST Bearer Validation (CIDR, Workspace Scope, Surface Restrictions)
- **File**: `kanban/api/deps.py` & `kanban/security/boundary.py`
  - In `get_principal` (and `get_current_principal`), when `principal.credential_boundary` is present, `boundary.validate_request(request, principal.workspace_id)` is invoked prior to route execution.
  - **CIDR Allowlist Check**: Validates client IP against `boundary.allowed_cidrs`. If outside allowlist, raises HTTP 403 ProblemException `CIDR_NOT_ALLOWED`.
  - **Workspace Scope Allowlist Check**: Validates `boundary.allows_workspace(principal.workspace_id)`. If outside allowlist, raises HTTP 403 ProblemException `CREDENTIAL_SCOPE_VIOLATION`.
  - Also enforces workspace allowlist in `get_rls_session` when the `x-kb-scope-workspace` header is supplied.
  - **Surface Restrictions**:
    * Administrative isolation: credentials with `surface != "admin"` attempting `/api/v1/admin/*` are blocked with HTTP 403 `AAL2_REQUIRED`.
    * Docs surface isolation: credentials with `surface == "docs"` attempting mutation verbs (`POST`, `PUT`, `PATCH`, `DELETE`) on non-doc resources are blocked with HTTP 403 `INSUFFICIENT_SCOPE` (while permitting mutations on `/api/v1/docs`, `/api/v1/pages`, `/api/v1/stickies`, and read-only queries across issues).

### Action 3: Project Allowlists, Capability Mask & compute_effective_capabilities
- **File**: `kanban/security/permissions.py`
  - Implements `compute_effective_capabilities(rbac_caps, caller=None, project_id=None)`:
    * When `caller.credential_boundary` is present:
    * If `project_id` is specified and `not boundary.allows_project(project_id)`, returns `EmptyCapabilitySet()` (denies all access to projects outside `project_allowlist`).
    * Otherwise, intersects resolved RBAC capabilities with `boundary.effective_capabilities(rbac_caps)` (`capability_mask`).
  - In `evaluate_capabilities(session, principal_ctx, object_id)`:
    * Queries the object's `project_id`. If `principal_ctx.credential_boundary` is present and `not boundary.allows_project(target_proj_id)`, returns `Capability.NONE`.
    * Intersects effective capabilities with `boundary.capability_mask`.
    * Anti-enumeration invariant: `require_capability` raises HTTP 404 `NOT_FOUND` when an object belongs to an unallowed project, preventing resource existence discovery.

### Action 4: require_admin_aal2 Headless Token Rejection
- **File**: `kanban/auth/mfa/policy.py`
  - In `require_admin_aal2`, rejects headless API keys or ephemeral Bearer tokens unless the credential boundary carries `surface == "admin"` and verified `has_aal2_provenance == True`.
  - Prevents `kb_pat_` agent/docs tokens minted by an administrator from bypassing AAL2 multi-factor elevation on `/api/v1/admin/*`.
  - Headless admin credentials with verified AAL2 provenance pass without prompting for interactive user TOTP or WebAuthn enrollment.

---

## Verification & Quality Metrics

1. **Unit Test Suite & Coverage**:
   - Test files: `kanban/tests/security/test_credential_boundary_rest.py` (New), `kanban/tests/security/test_mcp_keys.py` (Extended).
   - Results: **20/20 test cases passed** in 0.93s.
   - Target Coverage on `kanban/security/boundary.py`: **100.00%** (120/120 statements, 56/56 branches, 0 missed).
   - Full security and auth test suites: **443/443 passed** in 53.16s (`uv run pytest kanban/tests/security/ kanban/tests/auth/`).

2. **Static & Build Checks**:
   - `ruff check .`: All checks passed (0 warnings, 0 errors).
   - `ruff format --check .`: Clean across 2127 files.
   - `mypy`: 0 errors across 1183 source files.
   - `lint-imports`: 2 module architecture contracts kept, 0 broken.
   - `check_no_dashes --all`: Clean (0 non-ASCII Unicode dashes repo-wide).
   - `check-migrations`: All 65 migrations valid, single head.

3. **Proof Artifacts**:
   - `docs/qa/KAN-66/git-diff.patch`
   - `docs/qa/KAN-66/unit-test-results.txt`
   - `docs/qa/KAN-66/build-check.txt`
   - `docs/qa/KAN-66/contract-sample.json`
   - `docs/qa/KAN-66/message-to-reality-checker.md`
