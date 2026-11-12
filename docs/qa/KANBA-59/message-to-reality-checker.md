# Reality-Checker Verification Packet: KANBA-59 (KB-P2-11)

## Ticket Metadata
- Ticket ID: `KANBA-59`
- Spec Key: `KB-P2-11`
- Title: `[Phase 2 / Security] Permission evaluator, Agent OBO intersection (User cap AgentGrant cap TokenScope) & anti-enumeration access_manifest API`
- Epic: `KB-E2` (Phase 2 Kanban API & Core Platform Services)
- Spec Sections: `3.2` (capabilities `VIEW..DELETE`, explicit deny precedence, delegated OBO intersection `EffectivePerms(u, r) ∩ AgentGrant(a, r) ∩ TokenScope(t)`), `3.4` (`access_manifest`, same-workspace co-viewers vs redacted `{ "redacted": true, "label": "1 External Collaborator" }`, indistinguishable `404` `<= 5.0ms` jitter), `3.1` (`principals`, `groups`), `3.3` (bitmask alignments)
- Dependencies: `KB-P1-13` (`resource_acl_entries`, RBAC role bindings, `effective_resource_access`), `KB-P2-01` (`PrincipalContext`, `get_rls_session`, `load_or_404`, `timing_floor`)
- Gate: `reality-checker` (Passive Forensic Mode), `api-specialist`, `ui-specialist`

---

## User Story
As a **workspace user, administrator, or delegated MCP/CLI agent**, I need **a single capability bitmask evaluator enforcing explicit-deny precedence and On-Behalf-Of (`User ∩ AgentGrant ∩ TokenScope`) narrowing, paired with an anti-enumeration `access_manifest` serializer and `GET /api/v1/objects/{id}/access` endpoint** so that **every object surfaces transparent sharing metadata (`Users`, `Groups`, `Agents`, `Inherited Scope`, `Explicit DENY`) without leaking principals across visibility boundaries or elevating an agent above its invoking human**.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** `kanban/security/permissions.py`, `kanban/security/access_manifest.py`, `kanban/api/deps.py`, and `kanban/api/v1/objects_access.py` exist and define `Capability(IntFlag)`, `SCOPE_CAPABILITY_MAP`, `parse_token_scope_mask`, `capabilities_to_names`, `evaluate_capabilities`, `require_capability`, `AccessManifest`, `build_access_manifest`, `GET /api/v1/objects/{object_id}/access`, and `POST /api/v1/objects/{object_id}/access/agent-kill-switch`.
- [x] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/security/test_permissions_and_obo.py kanban/tests/security/test_access_manifest.py kanban/tests/api/test_objects_access_endpoint.py -v --cov=kanban.security.permissions --cov=kanban.security.access_manifest --cov=kanban.api.v1.objects_access --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with all 12 cases passing and 97.49% branch+line coverage (surpassing the >= 95% mandate).
- [x] **Build / Type / Lint Clean:** `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict kanban database && uv run lint-imports && uv run python -m scripts.check_no_dashes --all` exits `0`.
- [x] **Timing Equalization Statistical Verification:** 100 alternating requests (50 Class A non-existent, 50 Class B unreadable) demonstrate median delta of 0.055 ms, well within the <= 5.0 ms jitter mandate.
- [x] **No Forbidden Unicode Dashes:** Repository passes `uv run python -m scripts.check_no_dashes --all` with zero violations.
- [x] **Dual Specialist Sign-Offs:** Reviewed and approved by API Specialist (`@arch-reviewer`) and UI Specialist (`@ui-specialist`) on the swarm message board.
- [x] **Forensic Proof Packet Complete:** All required proof files exist under `docs/qa/KANBA-59/`.

---

## Mandatory Feature Unit Tests Matrix (8/8 Required Cases Covered across 12 Tests)

| Case | Category | Test Target | Verification Description |
| :--- | :--- | :--- | :--- |
| **Case 1** | Positive RBAC + ACL Union | `test_permissions_and_obo.py::test_case_1_rbac_and_direct_acl_union` | User with project `VIEW \| COMMENT` plus direct `EDIT` ACL on issue evaluates to `VIEW \| COMMENT \| EDIT`. |
| **Case 2** | Security (Explicit Deny) | `test_permissions_and_obo.py::test_case_2_explicit_deny_precedence_and_group_closure` | User in `Core Backend` (`ALLOW VIEW\|EDIT`) AND `Contractors` (`DENY EDIT`) evaluates to `VIEW` only; nested group `SubContractors -> Contractors` inherits `DENY EDIT` via `principal_group_closure`. |
| **Case 3** | Security (OBO Intersection) | `test_permissions_and_obo.py::test_case_3_obo_intersection_narrowing` | User (`VIEW\|EDIT\|DELETE`) + Agent (`VIEW\|EDIT`) + Token (`agent:read`) -> `VIEW` only; Token (`agent:write`) -> `VIEW\|EDIT` (never `DELETE`); OBO on unreadable confidential project returns `Capability.NONE` (`404 NOT_FOUND`). |
| **Case 4** | Security (Disabled/Unknown) | `test_permissions_and_obo.py::test_case_4_disabled_principal_and_unknown_scope` | OBO with `DISABLED` agent principal returns `Capability.NONE`; `token_scopes=("unknown:scope",)` returns `Capability.NONE` (fails closed). |
| **Case 5** | Positive `access_manifest` | `test_access_manifest.py::test_case_5_positive_access_manifest` | Project with 2 direct users, 2 groups (`Core Backend` LDAP 11 members, `SecOps` OIDC 4 members), 1 service `AGENT`, and 1 `DENY` group produces `pill_label` ("Project + 2"), accurate member counts, agents, and deny overrides matching S3.4 wireframe. |
| **Case 6** | Security (Anti-Enumeration) | `test_access_manifest.py::test_case_6_anti_enumeration_redaction` | Out-of-boundary collaborator (`secret@partner.example`, `@secret_ext`, LDAP DN `CN=Secret,OU=Partner,DC=corp`) on issue produces `redacted_count >= 1`, `{"redacted": true, "label": "1 External Collaborator"}`, and zero occurrences of secret metadata or external UUID; in-boundary LDAP group omits `external_id`. |
| **Case 7** | Security (404 vs 403) | `test_permissions_and_obo.py::test_case_7_404_vs_403_discipline` | `require_capability(..., Capability.EDIT)` raises `404 NOT_FOUND` when caller lacks `VIEW`, and `403 INSUFFICIENT_CAPABILITY` when caller holds `VIEW` only. |
| **Case 8** | Endpoint, Kill-Switch & Timing | `test_objects_access_endpoint.py::test_case_8_objects_access_and_kill_switch` | `GET /api/v1/objects/{id}/access` returns 200 for co-viewer; `POST /api/v1/objects/{id}/access/agent-kill-switch` returns 403 for VIEW-only caller, and for ADMIN caller atomically revokes agent access (`agents == []`), appends `AGENT_ACCESS_KILLED` to `activity_records`, and causes subsequent agent reads to return 404; 100 alternating requests prove `status` (404), headers, and body identical with `median_delta <= 5.0ms`. |

---

## Technical Actions & Implementation Matrix

| Component | Target Location | Description |
| :--- | :--- | :--- |
| **Capability Bitmask & OBO Evaluator** | `kanban/security/permissions.py` | `Capability(IntFlag)`, `SCOPE_CAPABILITY_MAP`, `parse_token_scope_mask`, `capabilities_to_names`, `evaluate_capabilities` (aggregating `effective_resource_access` for principal closure and enforcing explicit-deny precedence and three-way OBO intersection), `require_capability`. |
| **Anti-Enumeration Access Manifest** | `kanban/security/access_manifest.py` | `AccessManifest`, `InheritedScope`, `ManifestUser`, `ManifestGroup`, `ManifestAgent`, `ManifestDenyOverride`, `ManifestRedactedEntry`, and `build_access_manifest` resolving inherited scopes, distinct group candidate evaluation, member counts, agent summaries, and out-of-boundary redaction. |
| **Principal Context Extension** | `kanban/api/deps.py` | Extended `PrincipalContext` with optional `agent_principal_id: uuid.UUID | None = None` for OBO delegation without breaking existing callers. |
| **Access Manifest & Kill-Switch Endpoints** | `kanban/api/v1/objects_access.py` | `GET /api/v1/objects/{object_id}/access` executing inside `timing_floor(floor_ms=25.0)` and `POST /api/v1/objects/{object_id}/access/agent-kill-switch` requiring `SHARE` or `ADMIN`, upserting `DENY` records for active agents, appending `AGENT_ACCESS_KILLED` activity record, and rebuilding ERA. |
| **Router Mount** | `kanban/api/v1/__init__.py` | Registered `objects_access_router` into `/api/v1`. |
| **Security Module Exports** | `kanban/security/__init__.py` | Cleanly re-exports `Capability`, `SCOPE_CAPABILITY_MAP`, `parse_token_scope_mask`, `capabilities_to_names`, `evaluate_capabilities`, `require_capability`, `AccessManifest`, and `build_access_manifest`. |

---

## Forensic Proof Artifacts in `docs/qa/KANBA-59/`
1. `git-diff.patch`: Complete unified `git diff` for this ticket against base commit.
2. `unit-test-results.txt`: Raw output and exit code of `pytest kanban/tests/security/test_permissions_and_obo.py kanban/tests/security/test_access_manifest.py kanban/tests/api/test_objects_access_endpoint.py` (12 passed in 4.10s, 97.49% coverage, EXIT=0).
3. `build-check.txt`: Raw output of `ruff check .`, `ruff format --check .`, `mypy --strict kanban database`, `lint-imports`, and `check_no_dashes --all` (all checks passed, 140 source files clean, 2 contracts kept 0 broken, EXIT=0).
4. `contract-sample.json`: Captured live HTTP responses for `200 OK` (complete manifest with users, groups, agents, deny overrides, redacted entries), `403 INSUFFICIENT_CAPABILITY` problem document, and `404 NOT_FOUND` anti-enumeration problem document.
5. `timing-equalization.txt`: Empirical measurement report of 100 alternating requests (50 Class A non-existent, 50 Class B unreadable) showing median delta of `0.055ms` (well below the `<= 5.0ms` threshold).
6. `api-specialist-review.md`: Verbatim review and sign-off by API Specialist (`@arch-reviewer`).
7. `ui-specialist-review.md`: Verbatim review and sign-off by UI Specialist (`@ui-specialist`).
8. `message-to-reality-checker.md`: This forensic sign-off document.
