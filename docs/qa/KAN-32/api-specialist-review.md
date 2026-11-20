# API Specialist Review: KAN-32 (KB-P3-AUDIT-26)

- Ticket: KAN-32
- Title: [KB-P3-AUDIT-26] Gate Custom Fields nsjail Sandbox in Standalone Mode, Fix tier_b_runner Wiring, and Publish Step-by-Step [Guide] How to Use Custom Fields (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Target Directory: `/home/adamoutler/kanban/docs/qa/KAN-32`
- Branch: `main`
- Commit: `837f657d079ebcb8ee88eec86ad2f6df41c1eb33` (short: `837f657d`)
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-32 on `main` at commit `837f657d`, incorporating verified evidence from the zero-mock live container execution (`live-fullstack-proof.txt` run on `http://127.0.0.1:18961`, container `kanban-liveqa-1`), all 6 live visual screenshots in `docs/qa/KAN-32/screenshots/`, unit test logs (`unit-test-results.txt`), and static build outputs (`build-or-typecheck.txt`).

The ticket resolves three primary problems:
1. Backend Standalone `nsjail` Fail-Closed Gating & Multi-Container `tier_b_runner` Wiring:
   - Extended `SystemStatusResponse` in `kanban/api/v1/system_status.py` and `useSystemStatus.ts` with `supported_custom_field_tiers` (`["scalar", "formula", "wasm"]` in Standalone mode, and `["scalar", "formula", "wasm", "nsjail"]` in Multi-Container mode) and `sandbox_unavailable_reason` explaining that multi-container compose is required.
   - Enforced fail-closed validation in `CustomFieldDefinitionService.create_definition` and `update_definition` (`kanban/custom_fields/service.py`) and `POST /projects/{ref}/custom-fields/test-execute` (`kanban/api/v1/custom_field_execution.py`) rejecting `tier == "nsjail"` when `tier_b_sandbox_available == False` with HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE`.
   - Maintained backward compatibility and inspection safety by allowing pre-existing `nsjail` definitions imported from backup to update non-tier metadata (name, description, enabled) without error.
   - Fixed `CustomFieldExecutor(session, tier_b_runner=getattr(request.app.state, "tier_b_runner", None))` wiring across `list_custom_fields_for_issue`, `execute_custom_field_for_issue`, and `test_execute_custom_field`, ensuring multi-container deployments execute Tier B nsjail scripts properly.
2. Built-in Wasm Fallback & Web UI Badging for Unavailable `nsjail` Options:
   - Added built-in Wasm module fallback (`kanban/custom_fields/builtin_wasm.py`) enabling starter presets like `cvss-score` (`echo_cvss.wasm`) to execute successfully in fresh projects with zero rows in `approved_wasm_modules`.
   - Connected `CustomFieldDefinitionEditor.tsx`, `FlavorDecisionMatrix.tsx`, and `PresetGallery.tsx` to `useSystemStatus()`.
   - When `tier_b_sandbox_available === false`, renders the Standalone Guidance Callout (`standalone-guidance-callout`) with links to `/docs/Guide-Custom-Fields` and `/admin/standalone`, disables `nsjail` options in Field Flavor and Execution Sandbox selects with the badge `[Multi-Container Compose Required]`, disables `total-project-issues` and `git-pr-link` presets, and displays a warning banner when inspecting pre-existing `nsjail` definitions.
3. Published Step-by-Step Wiki Guide:
   - Authored `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Guide-Custom-Fields.md` starting with `# [Guide] How to Use Custom Fields`, linked in `_Sidebar.md` and accessible at `/docs/Guide-Custom-Fields`.
   - Documented where custom field values appear (Issue Properties Rail, Table View, Board Cards, Filters and Search), tier selection and Standalone gating, copy-paste examples with valid Python AST syntax and format metadata JSON schemas (`Priority SLA Days`, `Sub-Issue Progress %`, `CVSS Severity Pill`, `Total Project Issues Rollup`), all 7 output formats, safe formula AST execution context, and dual-control AAL2 scope escalation.

All API contracts, security invariants, error responses, database transaction boundaries, and test coverage requirements are verified and approved:
- Exact problem response structure: HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE` with clear remediation advice pointing callers toward `scalar`, `formula`, or `wasm` tiers.
- High test coverage: 33/33 Pytest tests pass in 23.24s with 99% overall statement coverage across touched backend files (`service.py` 99%, `builtin_wasm.py` 100%, `custom_field_execution.py` 98%, `custom_fields.py` 100%). 165/165 Vitest tests pass across 10 test files in 6.61s with 100% lines coverage across touched components.
- Zero external runtime packages added (`Apache-2.0` compliant).
- Strict unidirectional layering (`agent -> mcp -> kanban -> database`) verified via `import-linter` (2 kept, 0 broken).
- Strict 0 em-dashes and en-dashes across all code, tests, and documentation (`check_no_dashes` clean).

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
  - `list_custom_fields_for_issue`: Passes `tier_b_runner=getattr(request.app.state, "tier_b_runner", None)`.
  - `execute_custom_field_for_issue`: Passes `tier_b_runner=getattr(request.app.state, "tier_b_runner", None)`.
  - `test_execute_custom_field`: Passes `tier_b_runner=getattr(request.app.state, "tier_b_runner", None)`.
  - In `kanban/app.py`: `app.state.tier_b_runner = TierBNsjailRunner()` and `app.state.tier_b_sandbox_available = bool(standalone_status.get("tier_b_sandbox_available", True))` initialized during startup.

### 2.4 Built-in Wasm Module Fallback (`kanban/custom_fields/builtin_wasm.py`)
- Source: `kanban/custom_fields/builtin_wasm.py`
- Fallback Invariant:
  - When executing or test-executing a Wasm custom field definition (such as `cvss-score`), the executor looks up the approved module in `approved_wasm_modules`.
  - If no module is found in the database (e.g., in fresh workspaces or standalone installs before manual upload), `load_builtin_wasm_module(module_name)` loads the built-in fallback binary (`echo_cvss.wasm`), enabling presets to work immediately out-of-the-box.

---

## 3. Live Full-Stack Proof Verification (`live-fullstack-proof.txt`)

Verbatim inspection of `/home/adamoutler/kanban/docs/qa/KAN-32/live-fullstack-proof.txt` on target container `kanban-liveqa-1` (`http://127.0.0.1:18961`) at commit `837f657d`:
1. Standalone System Status & Fail-Closed nsjail 422 Gating:
   - `GET /api/v1/system/status` -> HTTP 200 (6ms):
     * `deployment_mode: "standalone_embedded_pg"`
     * `tier_b_sandbox_available: false`
     * `supported_custom_field_tiers: ["scalar", "formula", "wasm"]`
     * `sandbox_unavailable_reason: "Isolated nsjail sandbox execution is unavailable in standalone mode. Multi-container compose deployment is required."`
   - Provisioned fresh project `SEC2` (with zero rows in `approved_wasm_modules`) and issue `SEC2-3` -> HTTP 201.
   - Fail-Closed Negative Gating Checks:
     * `POST /api/v1/projects/SEC2/custom-fields` (tier=nsjail) -> HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE` (request_id: `27f29aa0fa854d958dbead75ebe7d296`).
     * `POST /api/v1/projects/SEC2/custom-fields/test-execute` (tier=nsjail) -> HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE` (request_id: `8cf279f3e7bc46ed91115595a70ded98`).
2. Custom Fields Studio UI & Built-in Wasm Fallback:
   - Loaded `/projects/SEC2/settings/custom-fields` (819ms).
   - `[data-testid="standalone-guidance-callout"]` rendered cleanly:
     "💡 Standalone Mode Active: Scalar (<1ms), Formula (<5ms), and WebAssembly (<25ms) work out of the box in Standalone mode. [Guide] How to Use Custom Fields → Promote to Multi-Container →"
   - Disabled `nsjail` option verified in both Basic Flavor select and Advanced Execution Tier select with "Multi-Container Compose Required" badge.
   - Applied Starter Preset "cvss-score" (`data-testid="use-preset-btn-cvss-score"`) and saved -> `POST /api/v1/projects/SEC2/custom-fields` -> HTTP 201 (61ms).
   - Selected saved field item and clicked `Test Execute` on `SEC2-3` (with 0 manually uploaded Wasm modules):
     * `POST /api/v1/projects/SEC2/custom-fields/test-execute` -> HTTP 200 (62ms).
     * Output: `{"output_format":"severity_pill","value":{"level":"high","score":8.8,"label":"8.8 High"},"latency_ms":10,"logs":"Draft test execution on SEC2-3 (flavor=wasm)\nExecuted Wasm module: fuel=7\nSuccess: validated format severity_pill\n","status":"SUCCESS","error":null}`.
   - `GET /api/v1/issues/SEC2-3/custom-fields` -> HTTP 200 (30ms) returning computed severity pill.
3. Dark Mode WCAG AA Contrast, Log Wrapping & Viewport Verification:
   - `pre.custom-field-test-logs` metrics: `scrollWidth=742 == clientWidth=742`, `overflowsSelf=false`, `overflowsCard=false`, `whiteSpace="pre-wrap"`, `overflowWrap="anywhere"`.
   - Dark mode `.custom-fields-def-item--selected` computed styles: `backgroundColor="rgba(37, 99, 235, 0.25)"`, `borderColor="rgba(96, 165, 250, 0.4)"`, `textColor="rgb(249, 250, 251)"` (WCAG AA compliant contrast, zero light-mode bleed).
   - Viewport checks: Tablet (768x1024, `scrollWidth=768`), Mobile (390x844, `scrollWidth=390`), zero horizontal overflow.
4. Step-by-Step Guide Verification:
   - Loaded `/docs/Guide-Custom-Fields` (877ms), `hasExpectedContent=true`.
   - Screenshot: `screenshots/live-guide-custom-fields-desktop-light.png`.
5. All 6 Live Screenshots Verified on Disk:
   - `live-desktop-dark.png`
   - `live-desktop-light.png`
   - `live-desktop-test-exec.png`
   - `live-guide-custom-fields-desktop-light.png`
   - `live-mobile.png`
   - `live-tablet.png`
6. Telemetry & Stability: Console errors: 0, Page errors: 0, HTTP 5xx server errors: 0. `LIVE_STACK_VERDICT: PASS`.

---

## 4. Test Suite & Coverage Verification

- Backend Pytest Suite (`unit-test-results.txt`):
  - `kanban/tests/custom_fields/test_standalone_nsjail_gate.py`: 8 passed.
  - `kanban/tests/custom_fields/test_custom_fields_api.py`: 7 passed.
  - `kanban/tests/custom_fields/test_execution_api.py`: 3 passed.
  - `kanban/tests/custom_fields/test_manifest_and_formula_security.py`: 8 passed.
  - `kanban/tests/custom_fields/test_builtin_wasm_preset.py`: 7 passed.
  - Total: 33 passed in 23.24s.
  - Statement coverage across touched files:
    - `kanban/api/v1/custom_field_execution.py`: 98%
    - `kanban/api/v1/custom_fields.py`: 100%
    - `kanban/custom_fields/builtin_wasm.py`: 100%
    - `kanban/custom_fields/service.py`: 99%
    - Combined coverage: 99% (369 stmts, 0 miss).
- Frontend Vitest Suite (`unit-test-results.txt`):
  - 165 passed across 10 test files in 6.61s.
  - Statement coverage:
    - `src/app/useSystemStatus.ts`: 100% statements, 100% lines
    - `src/features/custom-fields/CustomFieldDefinitionEditor.tsx`: 100% statements, 100% lines, 95.74% branch
    - `src/features/custom-fields/FlavorDecisionMatrix.tsx`: 100% statements, 100% lines, 92.3% branch
    - `src/features/custom-fields/PresetGallery.tsx`: 100% statements, 100% lines, 96.87% branch
  - Design tokens: `cssTokensAudit.test.ts` passed 4/4 in 13ms (0 inline JSX style props).
- Static Analysis (`build-or-typecheck.txt`):
  - `uv run ruff check .`: Clean (All checks passed).
  - `uv run ruff format --check .`: Clean (1942 files already formatted).
  - `uv run mypy`: Clean (Success: no issues found in 1115 source files).
  - `uv run lint-imports`: Clean (Contracts: 2 kept, 0 broken).
  - `pnpm --dir kanban/web typecheck` (`tsc -b`): Clean (0 errors).
  - `pnpm --dir kanban/web lint` (`eslint`): Clean (0 warnings).
  - `pnpm --dir kanban/web build` (`vite build`): Clean in 1.48s (0 errors).
  - `python3 -m scripts.check_no_dashes`: Clean (0 em/en-dashes found).

---

## 5. Security & Isolation Matrix

| Capability / Concern | Specification Standard | Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| Standalone Tiers Listing | Omits nsjail when standalone | `supported_custom_field_tiers: ["scalar", "formula", "wasm"]` | PASS |
| Fail-Closed Gating | Rejects nsjail draft creation in standalone | HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE` | PASS |
| Test Execute Gating | Rejects nsjail test execution in standalone | HTTP 422 `SANDBOX_UNAVAILABLE_IN_STANDALONE` | PASS |
| Built-in Wasm Fallback | Fallback for echo_cvss.wasm preset | `load_builtin_wasm_module` enables 0-config test | PASS |
| Tier-B Runner Wiring | Passes `tier_b_runner` to `CustomFieldExecutor` | Wired in execution endpoints | PASS |
| Dark Mode Contrast | WCAG AA compliant selected item contrast | `rgba(37, 99, 235, 0.25)` and `rgb(249, 250, 251)` | PASS |
| Test Log Wrapping | No horizontal card clipping from test logs | `pre.custom-field-test-logs` with `whiteSpace: pre-wrap` | PASS |
| Published Guide | Step-by-step guide published | Rendered at `/docs/Guide-Custom-Fields` | PASS |
| Style Compliance | 0 em-dashes and 0 en-dashes | Checked with `scripts.check_no_dashes` | PASS |

---

## 6. Verdict & Signoff

STATUS: APPROVED

All API endpoints, fail-closed nsjail gating, built-in Wasm fallbacks, tier_b_runner wiring, Custom Fields Studio UI adaptations, and unit test suites for KAN-32 on `main` at commit `837f657d` have been thoroughly audited, verified against live container `kanban-liveqa-1`, and certified. All 6 live visual screenshots in `docs/qa/KAN-32/screenshots/` are verified. Ready for Clean-Room Reality-Checker QA.
