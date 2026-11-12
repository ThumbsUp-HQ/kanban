# API Specialist Gate Independent Forensic Audit: KANBA-59 (KB-P2-11)

- Ticket: `KANBA-59` (`KB-P2-11`)
- Title: Permission evaluator, Agent OBO intersection (User cap AgentGrant cap TokenScope) & anti-enumeration access_manifest API
- Epic: `KB-E2` (Phase 2 Kanban API & Core Platform Services)
- Auditor: `arch-reviewer` (Swarm Systems/Backend Architect & API Specialist Gate Auditor)
- Date: 2026-11-12
- Worktree: `/tmp/kb-wt-KANBA-59` on branch `feat/KANBA-59` (commit `0a5c473`)
- Scope: Independent forensic audit of the `Capability` bitmask evaluator, explicit-deny precedence across principal group closures, On-Behalf-Of (OBO) three-way permission narrowing (`User ∩ AgentGrant ∩ TokenScope`), fail-closed principal status guards, S3.4 anti-enumeration 404 discipline, `access_manifest` visibility boundary redaction, and `POST /api/v1/objects/{id}/access/agent-kill-switch` endpoint.

---

### 1. Executive Summary & Verification Matrix

An independent forensic API and security architecture audit of `KANBA-59` (`KB-P2-11`) was conducted across `kanban/security/permissions.py`, `kanban/security/access_manifest.py`, `kanban/api/v1/objects_access.py`, `kanban/api/deps.py`, 12 comprehensive unit and security test suites, live contract captures in `contract-sample.json`, and statistical timing data in `timing-equalization.txt`.

The implementation satisfies all architectural, security, and protocol requirements of `docs/tickets/KB-P2-11.md` and `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` (S3.2, S3.4, S11.1).

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Capability Bitmask** | Granular IntFlag enum matching S3.2 bit positions (`VIEW=1` .. `DELETE=128`, `ALL=255`) | Implemented in `kanban/security/permissions.py`; `ALL=0xFF`; bit-exact mappings | PASS |
| **Token Scope Parsing** | Additive token scope parsing (`session`, `read`, `write`, `admin:write`, etc.) | `parse_token_scope_mask` maps scopes to capability bits; unknown scopes fail closed (`NONE`) | PASS |
| **Explicit-Deny Precedence** | Any DENY bit on principal or ancestor group clears allow bit | Evaluates `allow_mask & (~deny_mask)` across `PrincipalGroupClosure`; verified in test case 2 | PASS |
| **Three-Way OBO Intersection** | `User ∩ AgentGrant ∩ TokenScope` for delegated agent requests | Bitwise AND across human mask, agent mask, and token scope mask; cannot exceed human or agent perms | PASS |
| **Principal Status Guards** | Inactive or disabled principal returns `Capability.NONE` | Human status != 'ACTIVE' or agent status != 'ACTIVE' fails closed immediately | PASS |
| **Anti-Enumeration 404 Discipline** | Lacking VIEW raises 404 NOT_FOUND; holding VIEW but lacking required raises 403 | `require_capability` raises 404 for unreadable objects; raises 403 `INSUFFICIENT_CAPABILITY` only when VIEW present | PASS |
| **Timing Equalization Floor** | `TimingFloor(floor_ms=25.0)`; statistical delta `<= 5.0ms` | 100 alternating requests measured median delta of `0.152ms` (non-existent 28.80ms vs unreadable 28.95ms) | PASS |
| **Visibility Boundary Redaction** | Zero leakage of external UUIDs, email addresses, handles, or LDAP DNs | Out-of-boundary principals collapsed to `redacted_entries` (`1 External Collaborator`, `1 Restricted Principal`); verified in test case 6 | PASS |
| **Agent Kill-Switch Endpoint** | `POST /api/v1/objects/{id}/access/agent-kill-switch` | Requires SHARE or ADMIN; upserts explicit DENY ALL (255) for all active agents; triggers `rebuild_effective_access_for_workspace`; appends `AGENT_ACCESS_KILLED` | PASS |
| **PrincipalContext Backward Compatibility** | Add optional `agent_principal_id: UUID | None = None` | `kanban/api/deps.py` extended cleanly; preserves 100% backward compatibility for 5-arg callers | PASS |
| **Test Coverage & Quality** | 8 mandatory test cases; >=95% branch+line coverage | 12/12 tests pass in 4.18s; 97.49% line and branch coverage across touched modules; zero lint/type errors | PASS |

---

### 2. Detailed Technical & Security Review

#### A. Capability Evaluation & OBO Delegation (`kanban/security/permissions.py`)
1. **Explicit-Deny Precedence:**
   - Evaluates PostgreSQL `EffectiveResourceAccess` across the caller's direct ID and all ancestor group IDs retrieved via `PrincipalGroupClosure`.
   - Computes `allow_mask` via `func.bit_or` and `deny_mask` via `func.bit_or`.
   - Resolves effective permissions as `Capability(allow_mask & (~deny_mask))`. Any DENY bit on the principal or any inherited group unconditionally overrides any ALLOW grant.
2. **Three-Way OBO Intersection:**
   - When `principal_ctx.agent_principal_id` is present, the evaluator resolves `human_mask`, `agent_mask`, and `token_mask` independently.
   - Computes effective capabilities as `Capability(human_mask & agent_mask & token_mask)`.
   - Guarantees an autonomous or delegated agent can never exercise capabilities beyond what the user possesses, what the agent is granted on the resource, and what the token scope permits.
3. **Fail-Closed Status Invariants:**
   - Validates `Principal.status == 'ACTIVE'` for the human caller.
   - For delegated agent requests, additionally validates `Principal.status == 'ACTIVE'` for the agent principal.
   - Any non-active status (`DISABLED`, `SUSPENDED`, `DELETED`) immediately returns `Capability.NONE`.

#### B. Anti-Enumeration Discipline (S3.4)
1. **Timing-Equalized 404 vs 403:**
   - In `require_capability(session, principal_ctx, object_id, required)`:
     - If `Capability.VIEW not in caps`: raises 404 NOT_FOUND via `not_found()` (never 403, preventing resource enumeration side-channels).
     - If `Capability.VIEW in caps` but `(caps & required) != required`: raises 403 `INSUFFICIENT_CAPABILITY`.
2. **Timing Floor Execution:**
   - `GET /api/v1/objects/{object_id}/access` wraps execution inside `async with timing_floor(floor_ms=25.0):`.
   - Measured statistical distribution across 100 alternating requests in `docs/qa/KANBA-59/timing-equalization.txt` yields a median delta of `0.152ms` (well below the `<= 5.0ms` mandate).

#### C. Access Manifest Visibility Boundary (`kanban/security/access_manifest.py`)
1. **Sanitized Sharing Representation:**
   - Normalizes handles to `@canonical_key` or `@email_prefix` without exposing full email addresses or internal system identifiers.
   - Masks external identity provider metadata: LDAP groups expose only their common name and member count, suppressing raw LDAP distinguished names (`DN`).
2. **Out-of-Boundary Redaction:**
   - Principals belonging to external workspaces, guest roles (`WORKSPACE_GUEST`), or ephemeral scripts (`SCRIPT_EPHEMERAL`) are filtered out of `users`, `groups`, `agents`, and `deny_overrides`.
   - Replaced by generic summary placeholders in `redacted_entries` (e.g. `1 External Collaborator`, `1 Restricted Principal`), exposing only the aggregated `redacted_count`.

#### D. Agent Kill-Switch Endpoint (`kanban/api/v1/objects_access.py`)
1. **Authorization & Operation:**
   - Validates caller possesses `Capability.SHARE` or `Capability.ADMIN` on the target object; callers lacking VIEW receive 404; callers holding VIEW without admin/share receive 403.
   - Identifies all active `AGENT` and `SERVICE_PRINCIPAL` identities holding access on the object.
   - Inserts/updates `resource_acl_entries` setting `effect = 'DENY'` and `capability_mask = 255` (`Capability.ALL`).
   - Invokes database function `rebuild_effective_access_for_workspace(ws_id)` to atomically re-index access tables.
   - Records audit entry `AGENT_ACCESS_KILLED` into `activity_records` via `append_activity` with cryptographic hash chaining.
   - Returns the refreshed, updated `AccessManifest`.

---

### 3. Verdict

The implementation of `KANBA-59` (`KB-P2-11`) is architecturally sound, mathematically robust in its bitmask evaluations, strictly adheres to S3.2 and S3.4 security invariants, and completely meets all criteria set forth in the ticket specification.

**Gate Verdict:** **`APPROVED`**
