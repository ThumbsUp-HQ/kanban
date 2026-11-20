# Integration Agent Reality-Based Report: KAN-17 (`KB-P3-AUDIT-11`)

**Verdict: READY**
**Grade: A**

---

## 1. Reality Check Validation (Passive Clean-Room Forensic Audit)

- **Audit Mode:** Independent, fresh-context passive forensic read-only inspection of `/home/adamoutler/kanban`, `/home/adamoutler/kanban/thumbs-up-kanban.wiki`, and proof packet `/home/adamoutler/kanban/docs/qa/KAN-17/`.
- **Proof Bundle Inspected:**
  - [changed-files-manifest.txt](file:///home/adamoutler/kanban/docs/qa/KAN-17/changed-files-manifest.txt)
  - [git-diff.patch](file:///home/adamoutler/kanban/docs/qa/KAN-17/git-diff.patch) (2,600 lines; verified `0` `docs/qa/*` files inside patch)
  - [wiki-diff.patch](file:///home/adamoutler/kanban/docs/qa/KAN-17/wiki-diff.patch) (209 lines)
  - [unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KAN-17/unit-test-results.txt)
  - [build-or-typecheck.txt](file:///home/adamoutler/kanban/docs/qa/KAN-17/build-or-typecheck.txt)
  - [api-specialist-review.md](file:///home/adamoutler/kanban/docs/qa/KAN-17/api-specialist-review.md) (`STATUS: APPROVED`)
  - [ui-specialist-review.md](file:///home/adamoutler/kanban/docs/qa/KAN-17/ui-specialist-review.md) (`STATUS: APPROVED`)
  - [live-fullstack-proof.txt](file:///home/adamoutler/kanban/docs/qa/KAN-17/live-fullstack-proof.txt) (`OVERALL KAN-17 LIVE_STACK_VERDICT: PASS`)
  - [message-to-reality-checker.md](file:///home/adamoutler/kanban/docs/qa/KAN-17/message-to-reality-checker.md)
- **Implementation & Wiki Files Verified Directly on Disk:**
  - [manifest.py](file:///home/adamoutler/kanban/kanban/custom_fields/manifest.py)
  - [service.py](file:///home/adamoutler/kanban/kanban/custom_fields/service.py)
  - [custom_field_execution.py](file:///home/adamoutler/kanban/kanban/api/v1/custom_field_execution.py)
  - [script_depth.py](file:///home/adamoutler/kanban/kanban/api/middleware/script_depth.py)
  - [executor.py](file:///home/adamoutler/kanban/kanban/custom_fields/executor.py)
  - [json_limits.py](file:///home/adamoutler/kanban/kanban/api/middleware/json_limits.py)
  - [app.py](file:///home/adamoutler/kanban/kanban/app.py)
  - [safeJson.ts](file:///home/adamoutler/kanban/kanban/web/src/utils/safeJson.ts)
  - [trustedTypes.ts](file:///home/adamoutler/kanban/kanban/web/src/editor/clipboard/trustedTypes.ts)
  - [draftsStore.ts](file:///home/adamoutler/kanban/kanban/web/src/features/drafts/draftsStore.ts)
  - [CustomFieldDefinitionEditor.tsx](file:///home/adamoutler/kanban/kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx)
  - [Custom-Scripts-and-JSON-Security-Architecture.md](file:///home/adamoutler/kanban/thumbs-up-kanban.wiki/Custom-Scripts-and-JSON-Security-Architecture.md)
  - [_Sidebar.md](file:///home/adamoutler/kanban/thumbs-up-kanban.wiki/_Sidebar.md)
- **QA Cross-Validation:** Dual specialist gates (`api-spec-2` and `ui-spec-2`) are both `STATUS: APPROVED` and align with the code on disk, test outputs, and live-stack logs.

---

## 2. Specification Compliance Matrix (4 Problems)

### Problem 1: Wasm Manifest Hash Binding, Admin `test-execute` Gate, and Recursion Depth Guard - **PASS**
- **Manifest SHA-256 Binding:** [manifest.py](file:///home/adamoutler/kanban/kanban/custom_fields/manifest.py#L51-L94) adds `wasm_module_sha256: str | bytes | None = None` to `compute_field_manifest_sha256` and includes `"wasm_module_sha256"` in the canonical JSON payload before hashing. [service.py](file:///home/adamoutler/kanban/kanban/custom_fields/service.py#L217-L226) passes `wasm_module_sha256=wasm_bytes` on creation; `_apply_patch` ([service.py](file:///home/adamoutler/kanban/kanban/custom_fields/service.py#L309-L313)) compares `_parse_wasm_sha256(payload.wasm_module_sha256)` against `row.wasm_module_sha256` and sets `spec_changed = True`, triggering `compute_field_manifest_sha256(..., wasm_module_sha256=row.wasm_module_sha256)` ([service.py](file:///home/adamoutler/kanban/kanban/custom_fields/service.py#L355-L364)) and firing the PostgreSQL `custom_field_manifest_tamper_revoke` trigger. Verified end-to-end by `test_patch_wasm_module_sha256_revokes_approved_escalation` in [test_manifest_and_formula_security.py](file:///home/adamoutler/kanban/kanban/tests/custom_fields/test_manifest_and_formula_security.py).
- **Admin + AAL2 Gate & Approved Wasm Verification:** `POST /api/v1/projects/{project}/custom-fields/test-execute` in [custom_field_execution.py](file:///home/adamoutler/kanban/kanban/api/v1/custom_field_execution.py#L229-L289) enforces `CustomFieldDefinitionService.require_admin_and_aal2(session, caller, proj)` (403 `INSUFFICIENT_CAPABILITY` for non-admins; 403 `AAL2_REQUIRED` for AAL1). Non-interpreted `wasm` tier payloads verify `ApprovedWasmModule` in the caller's workspace and reject unapproved/missing modules with HTTP `404 WASM_MODULE_NOT_FOUND` (and `422 INVALID_WASM_SHA256` / `422 WASM_BINARY_INVALID` on malformed input).
- **Recursion Guard:** [script_depth.py](file:///home/adamoutler/kanban/kanban/api/middleware/script_depth.py#L16-L22) includes both `^/api/v1/projects/[^/]+/custom-fields/test-execute(?:/.*)?$` and `^/api/v1/projects/[^/]+/workflow-hooks/dry-run(?:/.*)?$` in `_BLOCKED_PATH_PATTERNS`, returning HTTP `409 SCRIPT_RECURSION_BLOCKED` when `X-Kanban-Script-Depth >= 1` or non-digit. Verified against live container in `live-fullstack-proof.txt`.

### Problem 2: `_eval_safe_formula` AST DoS Bounds - **PASS**
- **Node & Depth Ceilings:** [executor.py](file:///home/adamoutler/kanban/kanban/custom_fields/executor.py#L52-L70) enforces `_MAX_FORMULA_NODES = 64` and `_MAX_FORMULA_DEPTH = 8` via `_check_formula_ast_bounds` before AST evaluation.
- **Exponentiation & Multiplication Bounds:** [executor.py](file:///home/adamoutler/kanban/kanban/custom_fields/executor.py#L132-L160) enforces `ast.Pow` bounds (`abs(left) <= 1_000_000`, `-64 <= right <= 64`) and catches `(OverflowError, ValueError, ZeroDivisionError)` (plus `ZeroDivisionError` at line 195), safely returning `None` for `0 ** -1` and `0.0 ** -2` (live `test-execute` returns HTTP 200 `status="ERROR", value=null`). `ast.Mult` caps sequence repetition (`str`, `list`, `tuple`) at `_MAX_MULT_OUTPUT_LEN = 4096` and rejects negative multipliers.
- **Attribute Access Lockdown:** [executor.py](file:///home/adamoutler/kanban/kanban/custom_fields/executor.py#L108-L114) restricts `ast.Attribute` strictly to `isinstance(val, dict)` key lookup (`val.get(node.attr, "")`), eliminating `getattr` introspection.

### Problem 3: Global ASGI `JsonLimitsMiddleware` & Client-Side Hardening - **PASS**
- **ASGI Middleware:** [json_limits.py](file:///home/adamoutler/kanban/kanban/api/middleware/json_limits.py) registered in [app.py](file:///home/adamoutler/kanban/kanban/app.py#L443) enforces streaming byte caps (`2 MiB` default, `25 MiB` for `/attachments`, `/imports`, `/api/v1/attachments`, `/api/v1/admin/imports` -> `413 PAYLOAD_TOO_LARGE`), UTF-8/UTF-16 lone-surrogate rejection (`0xD800..0xDFFF` -> `422 INVALID_UTF8_SURROGATE`), iterative O(N) bracket depth pre-scan + heap-stack structural validator (`MAX_JSON_DEPTH = 32` -> `422 JSON_DEPTH_EXCEEDED`, `MAX_JSON_KEYS = 5000` -> `422 JSON_KEYS_EXCEEDED`), and zero-buffering passthrough for non-JSON content types.
- **Client `safeJsonParse`:** [safeJson.ts](file:///home/adamoutler/kanban/kanban/web/src/utils/safeJson.ts#L13-L21) strips `__proto__`, `constructor`, and `prototype` keys via reviver, integrated across [draftsStore.ts](file:///home/adamoutler/kanban/kanban/web/src/features/drafts/draftsStore.ts#L39) and all 3 parse sites in [CustomFieldDefinitionEditor.tsx](file:///home/adamoutler/kanban/kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx#L391-L807).
- **Trusted Types:** [trustedTypes.ts](file:///home/adamoutler/kanban/kanban/web/src/editor/clipboard/trustedTypes.ts#L44-L60) routes `createHTML` through `DOMPurify.sanitize(html, { RETURN_TRUSTED_TYPE: false })` on both `kanban-sanitizer` and `dompurify` policies.

### Problem 4: Standalone Wiki Security Chapter - **PASS**
- [Custom-Scripts-and-JSON-Security-Architecture.md](file:///home/adamoutler/kanban/thumbs-up-kanban.wiki/Custom-Scripts-and-JSON-Security-Architecture.md) and [_Sidebar.md](file:///home/adamoutler/kanban/thumbs-up-kanban.wiki/_Sidebar.md#L27) exist on disk and match [wiki-diff.patch](file:///home/adamoutler/kanban/docs/qa/KAN-17/wiki-diff.patch).
- Cross-checked all documented HTTP codes (`403 AAL2_REQUIRED`, `403 INSUFFICIENT_CAPABILITY`, `404 WASM_MODULE_NOT_FOUND`, `409 SCRIPT_RECURSION_BLOCKED`, `413 PAYLOAD_TOO_LARGE`, `422 INVALID_UTF8_SURROGATE`, `422 JSON_DEPTH_EXCEEDED`, `422 JSON_KEYS_EXCEEDED`), canonical manifest keys, `CustomFieldDefinitionService.require_admin_and_aal2(session, caller, project)` signature, AST limits (`64` nodes, `8` depth, `64` exponent, `1_000_000` base, `4096` mult), and byte limits (`2 MiB`, `25 MiB`) against implementation: 100% accurate.
- Valid Mermaid flowchart included; `0` em-dashes and `0` en-dashes across the wiki chapter and sidebar.

---

## 3. Complete Visual & Live-Stack Evidence

- **Zero-Mock Live Full-Stack Proof ([live-fullstack-proof.txt](file:///home/adamoutler/kanban/docs/qa/KAN-17/live-fullstack-proof.txt)):**
  - Executed against live container `kanban-liveqa-1` (`http://localhost:18951`) backed by PostgreSQL 16 (`FORCE RLS`), with `0` `mockApi` or `page.route` backend stubs.
  - Verified `@alice` (MEMBER) `test-execute` -> `403 INSUFFICIENT_CAPABILITY`; `@secadmin` (AAL1) escalation endpoints -> `403 AAL2_REQUIRED`; `@admin` (AAL2) `0 ** -1` -> `200 status="ERROR", value=null`; `1 + 2 * 3` -> `200 status="SUCCESS", value=7`; `X-Kanban-Script-Depth: 1` -> `409 SCRIPT_RECURSION_BLOCKED`; unapproved Wasm -> `404 WASM_MODULE_NOT_FOUND`; 40-deep JSON -> `422 JSON_DEPTH_EXCEEDED`; `2162730` bytes JSON -> `413 PAYLOAD_TOO_LARGE`; `\ud800` lone surrogate -> `422 INVALID_UTF8_SURROGATE`; and live doc rendering (`console.error: 0`, `pageerror: 0`, Mermaid blob SVG `w=206, h=520`).
- **Screenshot Visual Inspection (`docs/qa/KAN-17/screenshots/*.png`):**
  - [live-kan17-custom-fields-studio-desktop-dark.png](file:///home/adamoutler/kanban/docs/qa/KAN-17/screenshots/live-kan17-custom-fields-studio-desktop-dark.png): Crisp dark-mode studio editor showing Risk Formula, `SHA256: f27b47b3ebdf2cf5...`, Format Configuration Metadata JSON, and `formula: 1 + 2 * 3`.
  - [live-kan17-custom-fields-studio-desktop-light.png](file:///home/adamoutler/kanban/docs/qa/KAN-17/screenshots/live-kan17-custom-fields-studio-desktop-light.png): Crisp light-mode counterpart with clean spacing and contrast.
  - [live-kan17-wiki-security-doc-desktop-dark.png](file:///home/adamoutler/kanban/docs/qa/KAN-17/screenshots/live-kan17-wiki-security-doc-desktop-dark.png): Crisp dark-mode rendered security doc (Section 2, inline badges `403 AAL2_REQUIRED`, `404 WASM_MODULE_NOT_FOUND`, `409 SCRIPT_RECURSION_BLOCKED`, full right-hand Outline).
  - [live-kan17-wiki-security-doc-desktop-light.png](file:///home/adamoutler/kanban/docs/qa/KAN-17/screenshots/live-kan17-wiki-security-doc-desktop-light.png): Crisp light-mode counterpart.
  - [live-kan17-wiki-security-doc-mobile-light.png](file:///home/adamoutler/kanban/docs/qa/KAN-17/screenshots/live-kan17-wiki-security-doc-mobile-light.png): Clean 390x844 mobile layout (`scrollWidth: 390`, `innerWidth: 390`), zero horizontal overflow.

---

## 4. Test Coverage, Build & Hygiene Audit

- **Backend Unit Tests ([unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KAN-17/unit-test-results.txt)):** `74 passed in 26.38s`, `98%` overall coverage across touched files (all `>= 95%`: `json_limits.py` 96%, `script_depth.py` 100%, `custom_field_execution.py` 96%, `executor.py` 98%, `manifest.py` 100%, `service.py` 99%).
- **Frontend Unit Tests ([unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KAN-17/unit-test-results.txt)):** `48 passed in 3.22s`, `100%` Statements / `98.48%` Branches across touched files (`trustedTypes.ts` 100%/100%, `CustomFieldDefinitionEditor.tsx` 100%/97.95%, `draftsStore.ts` 100%/100%, `safeJson.ts` 100%/100%).
- **Static Analysis & Build ([build-or-typecheck.txt](file:///home/adamoutler/kanban/docs/qa/KAN-17/build-or-typecheck.txt)):** `ruff check .` (0 errors, 1880 files), `mypy` (0 errors, 1097 files), `lint-imports` (2 kept, 0 broken), `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 errors/warnings), `vite build` (clean in 1.24s), `python3 -m scripts.check_no_dashes --all` (0 em/en-dashes).
- **Non-Blocking Forensic Observations:**
  1. `trustedTypes.test.ts` verifies `createHTML('<b>test</b>')` passthrough on `kanban-sanitizer`, which exercises `DOMPurify.sanitize`, though adding an explicit XSS payload test (e.g., `<img src=x onerror=alert(1)>`) in a future pass would directly assert tag/attribute stripping.
  2. `api-specialist-review.md` and `ui-specialist-review.md` cite branch commit `85341a6` (wiki `fb83938`), while `live-fullstack-proof.txt` was refreshed on `53f7b6e` (wiki `b8853c3`); on-disk implementation and wiki files match `git-diff.patch` and `wiki-diff.patch` cleanly.

---

## 5. Final Certification

- **Overall Quality Rating:** A
- **System Completeness:** 100% of KAN-17 Problems 1-4 implemented, documented, and proven
- **Production Readiness:** READY
- **Verdict: READY**
- **Grade: A**
