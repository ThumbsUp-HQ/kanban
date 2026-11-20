# API Specialist Review: KAN-17 (KB-P3-AUDIT-11)

- Ticket: KAN-17
- Title: Harden Script Sandbox (Wasm Manifest Hash, Admin test-execute, AST DoS Bounds), Add Global JSON Depth/Size Guard, and Publish Wiki Security Chapter
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan17-95a5fbf6`
- Branch: `feat/KAN-17`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API and Security audit inspects the complete implementation for KAN-17 on branch `feat/KAN-17` (`72b4a82` off `887e7e0`). The ticket hardens the custom fields sandbox, enforces strict AST execution limits, implements pure ASGI JSON depth and size security guards, and unifies prototype-pollution protection across frontend JSON parsers.

All four architectural problems have been resolved with zero regressions, flawless static analysis, and zero em/en-dashes.

---

## 2. API Contract & Security Boundary Audit

### 2.1 WASM Manifest Hash Binding & Admin test-execute Gating (Problem 1)
- Manifest Cryptographic Binding:
  - `compute_field_manifest_sha256` in `kanban/custom_fields/manifest.py` incorporates `wasm_module_sha256` into the canonical JSON dictionary prior to hashing.
  - In `kanban/custom_fields/service.py`, `_apply_patch` compares `new_wasm` against `row.wasm_module_sha256` and flags `spec_changed = True` upon any change. This triggers the PostgreSQL `custom_field_manifest_tamper_revoke` trigger to revoke escalated approvals immediately upon bytecode tampering.
- Endpoint Protection:
  - `POST /api/v1/projects/{project}/custom-fields/test-execute` is strictly protected by `CustomFieldDefinitionService.require_admin_and_aal2(session, caller, proj)`, enforcing `PROJECT_ADMIN` authority and Authenticator Assurance Level 2 (AAL2).
  - WebAssembly tier checks look up the SHA-256 against `ApprovedWasmModule` for the caller's workspace, rejecting unapproved modules with 404 `WASM_MODULE_NOT_FOUND` or 422 `INVALID_WASM_SHA256`.
- Recursion Protection:
  - `ScriptDepthGuardMiddleware._BLOCKED_PATH_PATTERNS` adds regex rules blocking:
    - `^/api/v1/projects/[^/]+/custom-fields/test-execute(?:/.*)?$`
    - `^/api/v1/projects/[^/]+/workflow-hooks/dry-run(?:/.*)?$`
    Preventing nested or reentrant script invocation from inside sandbox execution.

### 2.2 AST Denial-of-Service Bounds in Formula Evaluation (Problem 2)
- Bounds Enforcement:
  - `_check_formula_ast_bounds`: Enforces AST node count `<= 64` and AST tree depth `<= 8`.
  - Power Operator Bounds (`ast.Pow`): Bounded to `abs(base) <= 1_000_000` and `abs(exponent) <= 64` with overflow catch.
  - Multiplication Bounds (`ast.Mult`): Sequence multiplication for strings, lists, or tuples is capped at `<= 4096` items, eliminating heap exhaustion vectors.
  - Attribute Access Introspection Prevention: `ast.Attribute` strictly accesses dictionary keys via `val.get(node.attr, "")`, completely preventing Python object introspection via `getattr`.
  - Unary Operators: Safe evaluation added for `ast.USub`, `ast.UAdd`, and `ast.Not`.

### 2.3 Global ASGI JSON Limits & Prototype Pollution Defense (Problem 3)
- ASGI Middleware (`JsonLimitsMiddleware`):
  - Added to `kanban/app.py` before route dispatch.
  - Default byte limit: 2 MiB; attachment/import paths (`/attachments`, `/imports`) permitted up to 25 MiB.
  - Enforces UTF-8 compliance and rejects UTF-16 lone surrogates (`0xD800..0xDFFF`) with 422 `INVALID_UTF8_SURROGATE`.
  - Iterative O(N) bracket depth pre-scan (`MAX_JSON_DEPTH = 32`) prevents CPython recursive parser stack overflow crashes.
  - Iterative heap-stack structure validation enforces depth `<= 32` (`JSON_DEPTH_EXCEEDED`) and total key count `<= 5000` (`JSON_KEYS_EXCEEDED`).
  - Standard RFC 7807/9457 `application/problem+json` error responses emitted across all violation conditions.
- Client-Side Protection:
  - `safeJsonParse` reviver function implemented in `kanban/web/src/utils/safeJson.ts`, stripping `__proto__`, `constructor`, and `prototype` keys recursively.
  - Integrated into `draftsStore.ts` and `CustomFieldDefinitionEditor.tsx`.
  - Unified `Trusted Types` in `trustedTypes.ts` ensures `DOMPurify.sanitize(html, { RETURN_TRUSTED_TYPE: false })` is invoked during `createHTML`.

### 2.4 Wiki Security Chapter (Problem 4)
- Verified `thumbs-up-kanban.wiki/Custom-Scripts-and-JSON-Security-Architecture.md` committed at `5f209c6` on branch `feat/KAN-17` with valid Mermaid architecture boundary diagram and linked in `_Sidebar.md`.
- Strict ASCII hyphens only (0 em-dashes / en-dashes).

---

## 3. Dependency, Layering & Code Cleanliness Audit

- Zero New External Dependencies: Inspected `pyproject.toml` and `package.json` (0 new packages).
- Unidirectional Layering: `uv run lint-imports` passed cleanly (2 kept, 0 broken).
- Static Analysis:
  - `uv run ruff check .`: 0 errors.
  - `uv run mypy`: 0 errors across 1095 source files.
  - `pnpm --dir kanban/web exec tsc -b --noEmit`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 errors, 0 warnings.
  - `python3 -m scripts.check_no_dashes --all`: 0 errors.
- Clean Patch Artifact: `docs/qa/KAN-17/git-diff.patch` contains zero `docs/qa/*` files.

---

## 4. Test Coverage Audit

- Pytest Suite:
  - 68 tests passing across custom fields, AST bounds, and JSON limits middleware.
  - `json_limits.py`: 96% coverage.
  - `script_depth.py`: 100% coverage.
  - `custom_field_execution.py`: 96% coverage.
  - `manifest.py`: 100% coverage.
  - `service.py`: 99% coverage.
- Vitest Suite:
  - 9 tests passing.
  - `safeJson.ts`: 100% coverage.
  - `trustedTypes.ts`: 100% coverage.

---

## 5. Verification Verdict

All API endpoints, security gates, AST DoS bounds, and ASGI limits are verified and approved.

STATUS: APPROVED
Reviewed by: api-spec-2
