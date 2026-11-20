# API Specialist Review: KAN-32 (KB-P3-AUDIT-26)

- Ticket: KAN-32
- Title: [KB-P3-AUDIT-26] Gate Custom Fields nsjail Sandbox in Standalone Mode, Fix tier_b_runner Wiring, and Publish Step-by-Step [Guide] How to Use Custom Fields (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan32-82da2d0f`
- Target Branch: `feat/KAN-32`
- Commit: `77044d53776c2e296577b24cc2a533f0c0ea382c`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-32 on branch `feat/KAN-32` (commit `77044d53`) and wiki repository (commit `bc6b15a`).

The ticket resolves three primary problems:
1. Backend Standalone `nsjail` Fail-Closed Gating & Multi-Container `tier_b_runner` Wiring:
   - Extended `SystemStatusResponse` in `kanban/api/v1/system_status.py` and `useSystemStatus.ts` with `supported_custom_field_tiers` (`["scalar", "formula", "wasm"]` in Standalone mode, and `["scalar", "formula", "wasm", "nsjail"]` in Multi-Container mode) and `sandbox_unavailable_reason` explaining that multi-container compose is required.
   - Enforced fail-closed validation in `CustomFieldDefinitionService.create_definition` and `update_definition` (`kanban/custom_fields/service.py`) and `POST /projects/{ref}/custom-fields/test-execute` (`kanban/api/v1/custom_field_execution.py`) rejecting `tier == "nsjail"` when `tier_b_sandbox_available == False` with HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE`.
   - Maintained backward compatibility and inspection safety by allowing pre-existing `nsjail` definitions imported from backup to update non-tier metadata (name, description, enabled) without error.
   - Fixed `CustomFieldExecutor(session, tier_b_runner=getattr(request.app.state, "tier_b_runner", None))` wiring across `list_custom_fields_for_issue`, `execute_custom_field_for_issue`, and `test_execute_custom_field`, ensuring multi-container deployments execute Tier B nsjail scripts properly.
2. Web UI Badging and Guidance for Unavailable `nsjail` Options:
   - Connected `CustomFieldDefinitionEditor.tsx`, `FlavorDecisionMatrix.tsx`, and `PresetGallery.tsx` to `useSystemStatus()`.
   - When `tier_b_sandbox_available === false`, renders the Standalone Guidance Callout (`standalone-guidance-callout`) with links to `/docs/Guide-Custom-Fields` and `/admin/standalone`, disables `nsjail` options in Field Flavor and Execution Sandbox selects with the badge `[Multi-Container Compose Required]`, disables `total-project-issues` and `git-pr-link` presets, and displays a warning banner when inspecting pre-existing `nsjail` definitions.
3. Published Step-by-Step Wiki Guide:
   - Authored `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Guide-Custom-Fields.md` starting with `# [Guide] How to Use Custom Fields`, linked in `_Sidebar.md`.
   - Documented where custom field values appear (Issue Properties Rail, Table View, Board Cards, Filters and Search), tier selection and Standalone gating, copy-paste examples with valid Python AST syntax and format metadata JSON schemas (`Priority SLA Days`, `Sub-Issue Progress %`, `CVSS Severity Pill`, `Total Project Issues Rollup`), all 7 output formats, safe formula AST execution context, and dual-control AAL2 scope escalation.

All API contracts, security invariants, error responses, database transaction boundaries, and test coverage requirements are verified and approved:
- Exact problem response structure: HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE` with clear remediation advice pointing callers toward `scalar`, `formula`, or `wasm` tiers.
- High test coverage: 26/26 Pytest tests pass in 28.31s with 98% overall statement coverage across touched backend files (`service.py` 99%, `custom_field_execution.py` 97%, `custom_fields.py` 100%). 165/165 Vitest tests pass across 10 test files with 100% lines coverage across touched components.
- Zero external runtime packages added (`Apache-2.0` compliant).
- Strict unidirectional layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- Strict 0 em-dashes and en-dashes across all code, tests, and documentation (`check_no_dashes` passed cleanly).

---

## 2. Detailed Contract & Security Verification

### 2.1 System Status Response Extension (`kanban/api/v1/system_status.py`)
- Source: `kanban/api/v1/system_status.py`
- Schema Definition:
  ```python
  class SystemStatusResponse(BaseModel):
      model_config = ConfigDict(extra="forbid")
      deployment_mode: str
      persistent_volume: bool
      data_mount_point: str | None = None
      data_mount_fstype: str | None = None
      tier_b_sandbox_available: bool
      air_gap_mode: bool
      local_llm_endpoint_host: str | None = None
      is_server_admin: bool
      allow_unlimited_mcp_keys: bool = True
      supported_custom_field_tiers: list[str] = Field(
          default_factory=lambda: ["scalar", "formula", "wasm", "nsjail"]
      )
      sandbox_unavailable_reason: str | None = None
  ```
- Endpoint Implementation (`get_system_status_endpoint`):
  - When `tier_b_sandbox_available` is `True`:
    - `supported_custom_field_tiers`: `["scalar", "formula", "wasm", "nsjail"]`
    - `sandbox_unavailable_reason`: `None`
  - When `tier_b_sandbox_available` is `False`:
    - `supported_custom_field_tiers`: `["scalar", "formula", "wasm"]`
    - `sandbox_unavailable_reason`: `"Isolated nsjail sandbox execution is unavailable in standalone mode. Multi-container compose deployment is required."`
- Frontend Alignment:
  - TypeScript interface `SystemStatus` in `kanban/web/src/app/useSystemStatus.ts` declared with identical readonly fields.
  - Safe query client fallback prevents crashes in unit test environments lacking `QueryClientContext`.

### 2.2 Fail-Closed Tier Validation (`kanban/custom_fields/service.py`)
- Source: `kanban/custom_fields/service.py` (`assert_tier_available`, `is_tier_b_available`)
- Implementation:
  ```python
  def assert_tier_available(
      tier: str,
      *,
      request: Request | None = None,
      tier_b_sandbox_available: bool | None = None,
  ) -> None:
      if tier == "nsjail" and not is_tier_b_available(
          request=request, override=tier_b_sandbox_available
      ):
          raise ProblemException(
              status=422,
              code="SANDBOX_UNAVAILABLE_IN_STANDALONE",
              title="Sandbox Unavailable In Standalone",
              detail=(
                  "Isolated nsjail sandbox execution is unavailable in standalone mode. "
                  "Use scalar, formula, or wasm execution tiers instead, "
                  "or promote to multi-container compose."
              ),
          )
  ```
- Application Points:
  1. `create_definition`: Calls `assert_tier_available(payload.tier, request=request)`. Rejects draft nsjail definitions in Standalone mode with HTTP 422.
  2. `update_definition`: Evaluates `if payload.tier is not None: assert_tier_available(payload.tier, request=request)`. Rejects changing tier to `nsjail` in Standalone mode with HTTP 422. Allows editing name, description, and enabled flag on imported pre-existing `nsjail` definitions without failing.
  3. `test_execute_custom_field`: Evaluates `if str(body.tier) == "nsjail": assert_tier_available("nsjail", request=request)`. Rejects draft nsjail test execution in Standalone mode with HTTP 422.

### 2.3 Tier-B Runner Wiring (`kanban/api/v1/custom_field_execution.py`)
- Source: `kanban/api/v1/custom_field_execution.py`
- Verification:
  - `list_custom_fields_for_issue`:
    ```python
    executor = CustomFieldExecutor(
        session,
        tier_b_runner=getattr(request.app.state, "tier_b_runner", None),
    )
    ```
  - `execute_custom_field_for_issue`:
    ```python
    executor = CustomFieldExecutor(
        session,
        tier_b_runner=getattr(request.app.state, "tier_b_runner", None),
    )
    ```
  - `test_execute_custom_field`:
    ```python
    executor = CustomFieldExecutor(
        session,
        tier_b_runner=getattr(request.app.state, "tier_b_runner", None),
    )
    ```
  - In `kanban/app.py`: `app.state.tier_b_runner = TierBNsjailRunner()` and `app.state.tier_b_sandbox_available = bool(standalone_status.get("tier_b_sandbox_available", True))` initialized during startup.

### 2.4 Published Wiki Documentation (`Guide-Custom-Fields.md`)
- File: `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Guide-Custom-Fields.md` (commit `bc6b15a`), linked in `_Sidebar.md`.
- Content Verification:
  - Section 1 (Where Values Appear): Detailed coverage of Issue Properties Rail, Table View, Board Cards, Filters and Search.
  - Section 2 (Choosing Between Execution Tiers): Comprehensive matrix comparing Scalar (<1ms), Safe Formula (<5ms), WebAssembly (<25ms), and Isolated Sandbox (<250ms), documenting Standalone fail-closed gating and promotion path to Multi-Container Compose.
  - Section 3 (Walkthroughs and Examples): Copy-paste examples with valid Python AST expressions matching `executor.py` AST evaluator:
    - `Priority SLA Days`: `1 if priority == 'URGENT' else 3 if priority == 'HIGH' else 7 if priority == 'MEDIUM' else 14` -> format `number` with unit `d`.
    - `Sub-Issue Progress %`: `round((completed_sub_issue_count * 100.0) / sub_issue_count, 1) if sub_issue_count > 0 else 100.0` -> format `number` with unit `%`.
    - `Incident Severity Pill`: Dynamic severity formula -> format `severity_pill`.
    - `Total Project Issues Rollup`: Wasm/nsjail rollup metric -> format `number`.
    - Complete format metadata JSON schemas for all 7 formats.
  - Section 4 (Safe Formula AST Context): Reference of issue keys (`state`, `state_group`, `priority`, `days_until_due`, `blocker_count`, `sub_issue_count`, `completed_sub_issue_count`) and allowlisted built-in functions.
  - Section 5 (Dry-Running and Approvals): Details `Test Execute` dry-run and dual-control AAL2 approval workflows for `WORKSPACE`/`SERVER` scope escalation.
  - Zero em-dashes and zero en-dashes (`check_no_dashes` passed cleanly).

### 2.5 Test Suites and Coverage Verification
- Backend Pytest Suite:
  - `kanban/tests/custom_fields/test_standalone_nsjail_gate.py`: 8/8 passed.
    - `test_create_custom_field_nsjail_rejected_in_standalone` (422 `SANDBOX_UNAVAILABLE_IN_STANDALONE`)
    - `test_create_custom_field_nsjail_succeeds_in_multicontainer` (201 Created)
    - `test_update_custom_field_nsjail_rejected_in_standalone` (422 `SANDBOX_UNAVAILABLE_IN_STANDALONE`)
    - `test_update_existing_nsjail_field_metadata_succeeds_in_standalone` (200 OK)
    - `test_test_execute_nsjail_rejected_in_standalone` (422 `SANDBOX_UNAVAILABLE_IN_STANDALONE`)
    - `test_test_execute_nsjail_succeeds_with_wired_tier_b_runner` (200 OK, MockTierBRunner)
    - `test_execute_custom_field_uses_wired_tier_b_runner` (200 OK, MockTierBRunner)
    - `test_service_assert_tier_available_logic` (unit test covering `assert_tier_available` and `is_tier_b_available`)
  - Full suite: 26/26 tests passed in 28.31s.
  - Statement coverage:
    - `kanban/custom_fields/service.py`: 99% (163 stmts, 0 miss, 42 branch, 2 brpart)
    - `kanban/api/v1/custom_field_execution.py`: 97% (120 stmts, 1 miss, 26 branch, 4 brpart)
    - `kanban/api/v1/custom_fields.py`: 100% (30 stmts, 0 miss)
    - Combined: 98% coverage on touched backend modules.
- Frontend Vitest Suite:
  - 165/165 tests passed across 10 test files in 5.61s.
  - Statement coverage:
    - `src/app/useSystemStatus.ts`: 100% statements, 100% lines
    - `src/features/custom-fields/CustomFieldDefinitionEditor.tsx`: 100% statements, 100% lines, 95.74% branch
    - `src/features/custom-fields/FlavorDecisionMatrix.tsx`: 100% statements, 100% lines, 92.3% branch
    - `src/features/custom-fields/PresetGallery.tsx`: 100% statements, 100% lines, 96.87% branch
  - Design tokens: `cssTokensAudit.test.ts` passed 4/4 (0 inline JSX style props).

### 2.6 Security, Architectural Boundary, and Code Style Compliance
- Dependency Invariant: Zero external runtime packages added (`Apache-2.0` compliant).
- Boundary Invariant: `lint-imports` confirms strict unidirectional layering (`agent -> mcp -> kanban -> database`), 2 kept, 0 broken.
- Static Typecheck: `mypy` passed across 7 touched source files with zero issues; `tsc -b --noEmit` passed with zero diagnostics.
- Linter: `ruff check` passed with zero errors; `eslint . --max-warnings 0` passed across entire frontend repository with zero warnings.
- Punctuation Standard: Zero em-dashes and zero en-dashes across all code, tests, and documentation (`check_no_dashes` clean).

---

## 3. Specialist Checklist

1. [x] `SystemStatusResponse` includes `supported_custom_field_tiers` and `sandbox_unavailable_reason`
2. [x] Standalone mode returns `["scalar", "formula", "wasm"]` without `nsjail`
3. [x] Multi-Container mode returns `["scalar", "formula", "wasm", "nsjail"]`
4. [x] Creating `nsjail` custom field in Standalone mode rejected with HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE`
5. [x] Patching `tier: "nsjail"` in Standalone mode rejected with HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE`
6. [x] Pre-existing `nsjail` definitions allow non-tier metadata updates without error
7. [x] `POST /custom-fields/test-execute` for `nsjail` rejected with HTTP 422 in Standalone mode
8. [x] `CustomFieldExecutor` initialized with `tier_b_runner` from `request.app.state`
9. [x] Web editor, decision matrix, and preset gallery badge and disable `nsjail` options when unavailable
10. [x] Step-by-step guide published on wiki (`Guide-Custom-Fields.md`) with valid AST formula examples
11. [x] 26/26 backend Pytest tests pass with 98% coverage on touched files
12. [x] 165/165 frontend Vitest tests pass with 100% lines coverage on touched files
13. [x] Design token compliance verified with zero inline JSX style props (`cssTokensAudit.test.ts` 4/4)
14. [x] Static typecheck and linting clean (`mypy`, `ruff`, `tsc`, `eslint`, `lint-imports`)
15. [x] Zero em-dashes or en-dashes across all code and documentation

---

## 4. Verdict & Certification

STATUS: APPROVED

Ticket KAN-32 is verified and approved on branch `feat/KAN-32` (commit `77044d53`) and wiki repository (commit `bc6b15a`). The implementation provides fail-closed security gating of `nsjail` container sandboxes in Standalone mode, wires `tier_b_runner` for multi-container compose execution, disables and badges unavailable UI presets, and publishes a complete, copy-paste step-by-step Custom Fields Guide. Ready for dual specialist signoff and merge into `main`.
