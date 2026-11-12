# Dependency Evaluation and Sign-Off: KANBA-16 (KB-P0-02)

This document contains the supply-chain security audit, permissive license verification, cryptographic lockfile hashes, and architectural evaluations for all dependencies introduced in ticket KANBA-16 (`ruff`, `mypy`, `pre-commit`, and `pre-commit-hooks`).

---

## 1. Cryptographic Hashes and Permissive License Audit

| Package | Version | License | Role | Source / Archive | SHA-256 Digest |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ruff` | `0.17.4` | MIT | Strict linter & code formatter | wheel (manylinux x86_64) | `2cd025509b2e15721b426fc70fd946d71f43b3db3b08e946dfec2d696d911690` |
| | | | | sdist: `ruff-0.17.4.tar.gz` | `f32d178b50e826e00f6c6c1be3f56333068acb9b67fe167143527fa9b81e890d` |
| `mypy` | `2.4.1` | MIT | Strict static type checker | wheel: `mypy-2.4.1-py3-none-any.whl` | `1784648d6ec8c2b5465e3f26241b845a0b3cb4e56c993c64abe16989e7698999` |
| | | | | sdist: `mypy-2.4.1.tar.gz` | `63b590965691e540a335fa74dadf31a7069142f6b72e234689bbd244edf55623` |
| `pre-commit` | `4.7.0` | MIT | Git hook lifecycle orchestrator | wheel: `pre_commit-4.7.0-py2.py3-none-any.whl` | `2e229038ad3656081b70c27913157e4b636ef306f643f024a8a8e3f0f7b2f877` |
| | | | | sdist: `pre_commit-4.7.0.tar.gz` | `1f3deee12b914c8fa184bd2b5953391c2e4f36763e403d4a23dc9983fa7c6e86` |
| `pre-commit-hooks` | `v5.0.0` | MIT | Git hygiene hooks (trailing ws, eof) | git rev: `v5.0.0` (`cef0300fd0fc4d2a87a85fa2093c6b283ea36f4b`) | Git SHA tag verified |

### Transitive Dependencies Audit
All transitive dependencies (`ast-serialize`, `cfgv`, `distlib`, `filelock`, `identify`, `librt`, `mypy-extensions`, `nodeenv`, `platformdirs`, `python-discovery`, `pyyaml`, `typing-extensions`, `virtualenv`) are licensed under MIT, PSF-2.0, or Apache-2.0. Zero GPL, AGPL, SSPL, or LGPL licenses exist.

---

## 2. Alternatives Considered and Rationale

- **`ruff` vs `flake8` + `black` + `isort`**: `flake8` and `black` require multiple separate Python tools and AST passes, leading to slow commit hooks, flaky plugin interactions, and inconsistent formatting. `ruff` unifies linting, formatting, and import sorting in a single Rust-native binary that runs in sub-second execution loops with `select = ["ALL"]`.
- **`mypy` vs `pyright`**: `pyright` requires a Node.js runtime environment, introducing unwanted cross-runtime dependencies into the Python toolchain. `mypy` is native Python, strictly adheres to PEP 484/526/561/695, and supports strict type analysis with zero external runtime overhead.
- **`pre-commit` vs custom git hook scripts**: `pre-commit` provides portable, version-pinned hook management across developer environments. Utilizing local `uv run` hook entries ensures all tools execute strictly from the pinned `uv.lock` environment, preventing skew between workstations and CI runners.

---

## 3. Specialist Evaluations and Verbatim Sign-Offs

### 3.1 Systems / Backend Architect Sign-Off
Reviewer: `arch-reviewer` (Systems/Backend Architect & API Specialist)
Source: Message #19
Status: SIGNED AND APPROVED

```
### [DEP-EVAL KANBA-16] Python Strict Lint/Type Toolchain and Pre-Commit

- Evaluator: Systems/Backend Architect (arch-reviewer)
- Scope: docs/tickets/KB-P0-02.md (KANBA-16 / KB-P0-02)
- Evaluated Dependencies:
  * ruff (MIT)
  * mypy (MIT)
  * pre-commit (MIT)
  * pre-commit/pre-commit-hooks (MIT)

1. License and Compatibility:
All components and transitive packages are licensed under the permissive MIT license. 100% compliant with the monorepo Apache-2.0 license policy. Zero copyleft (GPL, AGPL, SSPL, LGPL).

2. Supply-Chain and Attack Surface:
All four packages are scoped exclusively to the development toolchain (root pyproject.toml [dependency-groups] dev). They are never packaged into runtime distributions or production containers. All versions are strictly pinned (==) in pyproject.toml and cryptographically locked with sha256 hashes in uv.lock.

3. Architectural Rationale and Alternatives Considered:
- ruff vs. flake8 + black + isort:
  * Legacy Python linting relied on a fragmented chain of flake8, black, isort, and dozens of plugins. This introduced slow developer feedback loops, conflicting formatting rules, and complex dependency webs.
  * ruff unifies formatting and linting into a single Rust-native binary that executes 10x to 100x faster, enabling instantaneous feedback in pre-commit hooks and CI.
  * Configuring [tool.ruff.lint] select = ["ALL"] enforces strict defensive standards across all monorepo modules while requiring inline rationale comments for any exceptions.
- mypy vs. pyright:
  * pyright requires a Node.js runtime or npm distribution wrapper, introducing an unwanted runtime dependency into the Python toolchain.
  * mypy is the reference type checker for Python (PEP 484/526/561). Running mypy with strict = true and warn_unreachable = true guarantees complete type safety, eliminating dynamic attribute access and implicit Any types across database, kanban, mcp, and agent modules.
- pre-commit vs. custom git hooks:
  * pre-commit provides standardized, portable hook lifecycle management across developer environments. Utilizing local uv run entries ensures hooks execute strictly against the pinned uv.lock environment, preventing drift between local hooks and CI.

4. Architectural Verdict:
APPROVED. Essential for enforcing the zero-warning and strict-typing gate across the platform.
```

---

### 3.2 Security Engineer (#1) Sign-Off
Reviewer: `sec-eng` (Engineer #1, Application & Supply-Chain Security Engineer)
Source: Message #20
Status: SIGNED AND APPROVED

```
### [DEP-EVAL KANBA-16] Python Strict Lint/Type Toolchain and Pre-Commit

- Evaluator: Application and Supply-Chain Security Engineer (sec-eng)
- Scope: docs/tickets/KB-P0-02.md (KANBA-16 / KB-P0-02)
- Target Packages: ruff, mypy, pre-commit, pre-commit/pre-commit-hooks

1. License and Compatibility Audit:
- ruff (MIT): Permissive. Pure Rust binary distribution, zero transitive runtime dependencies.
- mypy (MIT): Permissive. Transitive dependencies: typing-extensions (PSF-2.0), mypy-extensions (MIT), pathspec (MPL-2.0). All permissive.
- pre-commit (MIT): Permissive. Transitive dependencies: cfgv (MIT), identify (MIT), nodeenv (MIT), pyyaml (MIT), virtualenv (MIT). All permissive.
- pre-commit/pre-commit-hooks (MIT): Permissive repository hooks pinned to immutable git tag revision in .pre-commit-config.yaml.
- License Compliance: 100% permissive. Zero GPL, AGPL, SSPL, or LGPL licenses present.

2. Supply-Chain and Tamper Resistance:
- Version Pinning: All dependencies pinned with exact equality (==) in root pyproject.toml [dependency-groups] dev.
- Cryptographic Integrity: Dual SHA-256 wheel/sdist hashes recorded in uv.lock.
- Local Execution: Hooks in .pre-commit-config.yaml execute via repo: local with entry: uv run ..., preventing arbitrary network downloads during git commit hooks.
- Execution Sandbox: Zero phone-home beacons, zero analytics telemetry. Both ruff and mypy execute exclusively within local memory and local filesystem bounds.

3. Alternatives Evaluated:
- flake8 + black: Rejected. Slower execution speed, fragmented plugin ecosystem with inconsistent AST parsing, sprawling transitive dependency footprint, and higher maintenance surface compared to unified Rust-based ruff.
- pyright: Rejected. Requires Node.js runtime environment or wrapper layer, introducing unnecessary cross-runtime supply-chain dependencies into a pure Python toolchain. Mypy is native Python with robust PEP 484/561/695 support and deterministic type validation.

4. Verdict:
- Role Sign-Off: APPROVED by sec-eng (Engineer #1, Application and Supply-Chain Security Engineer) for KANBA-16.
```

---

### 3.3 Test and Build Quality Engineer (#2) Sign-Off
Reviewer: `qa-eng` (Engineer #2, Test & Build Quality Engineer)
Source: Message #21
Status: SIGNED AND APPROVED

```
### [DEP-EVAL KANBA-16] Python Strict Lint/Type Toolchain and Pre-Commit (KB-P0-02)

- Target Dependencies:
  * ruff (MIT, build and lint toolchain)
  * mypy (MIT, static type checker)
  * pre-commit (MIT, local git hook orchestration)
  * pre-commit/pre-commit-hooks (MIT, git commit hygiene hooks)

- Test and Build Quality Assessment:
  * ruff: High-performance Rust-based engine consolidating linting, formatting, and style checking into sub-second execution loops. Replaces fragmented Python tooling and enables exhaustive linting (select = ["ALL"] with justified inline overrides) without slowing local commit hooks or CI pipelines. Ensures style and docstring consistency across all monorepo modules. Zero runtime dependency; isolated in dev dependency group.
  * mypy: Strict static type checking (strict = true, warn_unreachable = true, enable_error_code = ["ignore-without-code", "redundant-expr", "truthy-bool"]). Eliminates type errors, None dereferences, and signature mismatches statically prior to test execution. Guarantees type stability across all workspace packages and support scripts.
  * pre-commit and pre-commit-hooks: Deterministic hook orchestrator pinned to immutable git revision tags. Leverages local repo hooks via "uv run" to execute tool binaries directly from uv.lock, preventing version skew between local developer workstations and CI runners. Enforces trailing whitespace removal, end-of-file formatting, merge conflict detection, file size limits, and local unicode dash verification before commits are created.

- Alternatives Considered:
  * flake8 and black: Multiple distinct tools with separate AST parsers, slow Python startup overhead, and plugin version conflicts that trigger flaky CI runs. Ruff provides unified, order-of-magnitude faster, deterministic linting and formatting.
  * pyright: Fast and strict type checking, but introduces a Node.js dependency into the Python toolchain. Mypy is the native Python typing benchmark with seamless PEP 561 package compliance.

- Engineer #2 Sign-off: APPROVED
```
