# Verification Packet for KAN-17

## Ticket Summary
- **Ticket ID:** KAN-17 (`[KB-P3-AUDIT-11] Harden Script Sandbox (Wasm Manifest Hash, Admin test-execute, AST DoS Bounds), Add Global JSON Depth/Size Guard, and Publish Wiki Security Chapter (4 Problems)`)
- **Base Commit:** `887e7e029127b77b5868a4d7c35dd2b818d3a4e5`
- **Main Repo Branch:** `fix/KAN-17-rc1`
- **Wiki Repo Branch:** `feat/KAN-17` (Commit: `5f209c6df143ee802dd0b868d6ec064be98a40e0`)

---

## Detailed Problem Solutions

### 1. Problem 1: Wasm Manifest SHA-256 Binding, Admin test-execute, and Depth Guard
- **Manifest SHA-256 Binding (`manifest.py` & `service.py`):**
  - Updated `compute_field_manifest_sha256` to accept and serialize `wasm_module_sha256` in the canonical payload dictionary.
  - In `CustomFieldDefinitionService.create_definition` and `_apply_patch`, included `wasm_module_sha256` in digest computation.
  - In `_apply_patch`, updating `wasm_module_sha256` now explicitly sets `spec_changed = True`, ensuring that binary modifications trigger the PostgreSQL `custom_field_manifest_tamper_revoke` trigger and revoke escalated permissions.
- **Admin & AAL2 Gate for test-execute (`custom_field_execution.py`):**
  - Gated `POST /api/v1/projects/{project}/custom-fields/test-execute` behind `CustomFieldDefinitionService.require_admin_and_aal2(session, caller, proj)` (`PROJECT_ADMIN` + `AAL2`) instead of `Capability.VIEW`.
  - Added verification against `ApprovedWasmModule` registry: Wasm test execution requires the bytecode SHA-256 to exist as an approved module in the caller's workspace.
- **Script Depth Guard Middleware (`script_depth.py`):**
  - Added regex patterns for `/api/v1/projects/[^/]+/custom-fields/test-execute` and `/api/v1/projects/[^/]+/workflow-hooks/dry-run` to `_BLOCKED_PATH_PATTERNS` so custom field scripts and workflows cannot invoke execution or dry-run endpoints recursively.

### 2. Problem 2: Formula AST DoS Ceilings
- **AST Node and Depth Bounds (`executor.py`):**
  - Added `_check_formula_ast_bounds`: enforces total AST nodes `<= 64` and AST tree depth `<= 8`. Expressions exceeding either limit raise `FormulaSyntaxError("Formula AST exceeds safety limits")`.
- **Exponentiation and Sequence Multiplication Limits (`executor.py`):**
  - In `ast.Pow`, enforced `exponent <= 64` and `abs(base) <= 1_000_000`. Exceeding limits returns `None` safely.
  - In `ast.Mult`, bounded sequence repetition (string, list, tuple) to a maximum output length of 4096 elements. Exceeding limits returns `None` safely.
- **Attribute Access Lockdown & Unary Operator Support (`executor.py`):**
  - Restricted `ast.Attribute` strictly to dictionary key access (`ctx.get(node.attr)` if `isinstance(val, dict)`). Removed `getattr` fallback on arbitrary Python objects to eliminate introspection and attribute traversal attacks.
  - Added safe support for `ast.UnaryOp` (`ast.USub`, `ast.UAdd`, and `ast.Not`).

### 3. Problem 3: Global JSON Limits ASGI Middleware & Client-Side Hardening
- **Pure ASGI `JsonLimitsMiddleware` (`json_limits.py`):**
  - Streaming request body size caps: 2 MiB default cap, 25 MiB cap for file attachments and migration import routes (`/attachments`, `/import`, `/avatar`, `/upload`). Requests exceeding caps abort with HTTP 413 `REQUEST_TOO_LARGE`.
  - Content-Type scoping: Checks JSON structural bounds only when `content-type` is `application/json` or ends with `+json`. Multipart, form-data, SSE, and static asset routes pass through with zero buffering.
  - Structural limits: Uses an iterative, non-recursive tokenizer/depth parser enforcing `MAX_JSON_DEPTH = 32` and `MAX_JSON_KEYS = 5000`. Violations return HTTP 422 `JSON_TOO_DEEP` or `JSON_TOO_MANY_KEYS`.
  - UTF-16 surrogate rejection: Validates UTF-8 encoding and inspects for Unicode lone surrogates (`0xD800 <= ord(char) <= 0xDFFF`), returning HTTP 422 `INVALID_UTF8_SURROGATE`.
- **Client-Side Prototype Pollution Defense (`safeJson.ts`):**
  - Implemented `safeJsonParse` with a JSON reviver function that removes `__proto__`, `constructor`, and `prototype` keys from deserialized objects.
  - Replaced native `JSON.parse` with `safeJsonParse` in `draftsStore.ts` and `CustomFieldDefinitionEditor.tsx`.
- **Unified Trusted Types Sanitization (`trustedTypes.ts`):**
  - In `createHTML` policy for both `kanban-sanitizer` and fallback policies, hooked `DOMPurify.sanitize(html, { RETURN_TRUSTED_TYPE: false })` to ensure all HTML strings pass through sanitization before conversion to `TrustedHTML`.

### 4. Problem 4: Standalone Wiki Security Documentation
- **Wiki Chapter Authoring:**
  - Authored comprehensive documentation in `thumbs-up-kanban.wiki/Custom-Scripts-and-JSON-Security-Architecture.md` describing the multi-tier sandbox model, manifest hashing, AST bounds, JSON middleware limits, and Trusted Types architecture.
  - Included a valid mermaid boundary diagram illustrating data flow and security controls.
  - Linked new chapter into `thumbs-up-kanban.wiki/_Sidebar.md`.
  - Confirmed 0 em-dashes and 0 en-dashes across the wiki chapter.
  - Committed on branch `feat/KAN-17` in the wiki repository (`5f209c6df143ee802dd0b868d6ec064be98a40e0`).
  - Saved patch: `docs/qa/KAN-17/wiki-diff.patch`.

---

## Forensic Evidence & Verification Artifacts

1. **Unit Test Suite & Coverage:**
   - Saved report: `docs/qa/KAN-17/unit-test-results.txt`
   - Backend tests (Pytest): 73 passed (100% pass rate).
     - `json_limits.py`: 96% coverage
     - `script_depth.py`: 100% coverage
     - `custom_field_execution.py`: 96% coverage
     - `manifest.py`: 100% coverage
     - `service.py`: 99% coverage
     - `executor.py`: 98% coverage
     - TOTAL Backend: 97% overall statement & branch coverage across all touched Python files
   - Frontend tests (Vitest): 48 passed (100% pass rate).
     - `safeJson.ts`: 100% Statements, 100% Branches, 100% Functions, 100% Lines
     - `trustedTypes.ts`: 100% Statements, 100% Branches, 100% Functions, 100% Lines
     - `draftsStore.ts`: 100% Statements, 100% Branches, 100% Functions, 100% Lines
     - `CustomFieldDefinitionEditor.tsx`: 100% Statements, 97.95% Branches, 100% Functions, 100% Lines
     - TOTAL Frontend: 100% Statements, 98.48% Branches across all tested frontend files

2. **Static Analysis & Build Verification:**
   - Saved report: `docs/qa/KAN-17/build-or-typecheck.txt`
   - `uv run ruff check .`: Clean (0 errors across 1879 files)
   - `uv run mypy`: Clean (0 errors across 1097 source files)
   - `uv run lint-imports`: Clean (2 kept, 0 broken across 959 files)
   - `npm run typecheck`: Clean (0 errors)
   - `npm run lint`: Clean (0 errors, 0 warnings)
   - `npm run build`: Clean production build (Vite 8.3.8)
   - `python3 -m scripts.check_no_dashes --all`: Clean (0 em/en-dashes)

3. **Live Full-Stack Proof & Visual Artifacts:**
   - `docs/qa/KAN-17/live-fullstack-proof.txt`: Verbatim live server execution logs and API probe proof (0 product defects).
   - Screenshots in `docs/qa/KAN-17/screenshots/`:
     - `live-kan17-custom-fields-studio-desktop-dark.png`
     - `live-kan17-custom-fields-studio-desktop-light.png`
     - `live-kan17-wiki-security-doc-desktop-dark.png`
     - `live-kan17-wiki-security-doc-desktop-light.png`
     - `live-kan17-wiki-security-doc-mobile-light.png`

4. **Diff Artifacts:**
   - `docs/qa/KAN-17/git-diff.patch`: Clean patch against `887e7e0` across all 17 code/test files (0 `docs/qa/*` files inside).
   - `docs/qa/KAN-17/wiki-diff.patch`: Clean patch against wiki `main` (0 em/en-dashes).
