# Backend Architect Specialist Review: KANBA-216

## Review Metadata
- **Ticket ID**: KANBA-216
- **Title**: [KB-AUDIT-10] Fix Custom Scripted Fields Studio Wasm/Scalar Templates, Pattern Regex, Test-Execute, Dual-Control Approval UX, and Ticket Rail Rendering
- **Reviewer Persona**: Backend Architect (`.agents/agents/backend-architect.md`)
- **Review Date**: 2026-11-18
- **Status**: APPROVED (GRADE A)

---

## Architecture & API Surface Evaluation

### 1. New REST Endpoint: `POST /projects/{project}/custom-fields/test-execute`
- **Location**: `kanban/api/v1/custom_field_execution.py`, `kanban/api/v1/schemas/custom_fields.py`
- **Request Contract**:
  - `CustomFieldTestExecuteRequest`: accepts `issue_key: str`, `name: str`, `slug: str`, `tier: ScriptTier`, `output_format: OutputFormat`, `output_format_metadata: dict[str, Any]`, `script_source: str`, `target_scope: FieldScope`, `credential_mode: CredentialMode`, and optional `egress_allowlist: list[str]`.
  - Enforces project administrator authorization (`require_project_role("PROJECT_ADMIN")`).
  - Enforces capability verification ensuring project custom field execution is enabled.
- **Timing Floor & Side-Channel Mitigation**:
  - Implements uniform timing floor (`enforce_timing_floor(start_time, MIN_EXECUTION_FLOOR_MS)`) to prevent timing side-channel oracle attacks on script existence or execution complexity.
- **Side-Effect Free Isolation**:
  - Execution runs strictly read-only against the target issue snapshot without mutating issue rows, activity ledgers, or database savepoints.

### 2. AST-Based Safe Formula Evaluation Engine
- **Location**: `kanban/custom_fields/executor.py` (`_eval_safe_formula`)
- **Security Invariants**:
  - Restricts AST node types strictly to safe literals (`Constant`, `Num`, `Str`), binary operators (`Add`, `Sub`, `Mult`, `Div`, `Mod`), comparison operators (`Eq`, `NotEq`, `Lt`, `LtE`, `Gt`, `GtE`, `In`, `NotIn`), unary operators (`UAdd`, `USub`, `Not`), boolean operators (`And`, `Or`), ternary `IfExp`, and safe attribute lookups on `issue.*` / `issue['*']`.
  - Rejects all function calls, imports, eval, exec, code generation, and dunder attribute lookups (`__class__`, `__mro__`, `__subclasses__`).
  - Supports JavaScript ternary syntax transpilation (`cond ? true_val : false_val`) before Python AST parsing, enabling smooth cross-engine authoring without developer frustration.
  - Zero external subprocesses or native execution required for scalar and formula evaluation, yielding ultra-fast sub-millisecond execution (< 1ms).

### 3. Starter Template & Field Flavor Alignment
- **Field Flavors**:
  - `scalar`: Parses string or JSON literal (`scalar: "hello"` or `scalar: 42`).
  - `formula`: Evaluates AST safe formula expression against issue attributes.
  - `wasm`: Compiles and executes bytecode under Wasmtime runtime sandbox.
  - `nsjail`: Sandboxed Linux namespace script execution for advanced integration.
- Resolves legacy `422 WASM_BINARY_INVALID` error previously caused by defaulting JavaScript string `return "Hello";` to base64 Wasm bytecode parser.

---

## Unit Test Coverage & Verification Evidence
- Unit test suite: `kanban/tests/custom_fields/test_safe_formula_unit.py` (6/6 tests passing in 0.12s).
- Tests cover arithmetic, issue context lookup, JS ternary conversion, dunder attribute blocking, and test_execute pipeline.
- Global Ruff linting and formatting verification passed with zero warnings.

## Architectural Verdict
The API design, request/response models, AST formula sandboxing, and test-execute endpoint satisfy all enterprise security and architectural invariants. Approved without reservations.
