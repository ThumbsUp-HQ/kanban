# Dependency Evaluation: wasmtime 50.0.1 (KB-P5-13 / KANBA-143)

## 1. Package Metadata & Identification
- **Package Name:** `wasmtime`
- **Version:** `50.0.1`
- **License:** `Apache-2.0 WITH LLVM-exception` (Permissive; strictly compatible with 👍kanban Apache-2.0 license)
- **Repository:** `https://github.com/bytecodealliance/wasmtime-py`
- **Upstream Engine:** Bytecode Alliance Wasmtime (Rust-based, industry standard, formal verification via Cranelift)
- **Runtime Dependencies:** Zero transitive Python runtime dependencies. All native symbols statically linked inside binary wheel.

## 2. Integrity & Cryptographic Hashes (from uv.lock)
- **sdist:** `wasmtime-50.0.1.tar.gz`
  - SHA-256: `d9a1eb530e5c4a55853784ae6bff0053db3cad89299097ad00e352e3d48c3cc1`
- **Linux x86_64:** `wasmtime-50.0.1-py3-none-manylinux1_x86_64.whl`
  - SHA-256: `cc14c3a17654e0394e0225b11813532ef0cd7bd1e222a0c5494cdedaabeddac4`
- **Linux aarch64:** `wasmtime-50.0.1-py3-none-manylinux2014_aarch64.whl`
  - SHA-256: `5797305903c7333ecdcdd0e928230501a357497d3dfa5359a11585c57b32d56a`
- **macOS x86_64:** `wasmtime-50.0.1-py3-none-macosx_10_13_x86_64.whl`
  - SHA-256: `13fe813b922712a9e10fe0f48b2c56da06432eea4b24269bb7cd3a6b2720560b`
- **macOS arm64:** `wasmtime-50.0.1-py3-none-macosx_11_0_arm64.whl`
  - SHA-256: `ff4fc58ed3cbdb919d056accd4d280be13962a542754aaefd8a9b4654efa9bd9`

## 3. Alternatives Evaluated
1. **wazero (Go via subprocess):**
   - *Evaluation:* Excellent zero-dependency Go WebAssembly runtime, but requires invoking an external subprocess or C-shared library for Python integration. Subprocess execution adds 15-30ms process spawning latency, violating the < 2.0ms warm invocation latency SLA.
2. **wasmer (Python bindings):**
   - *Evaluation:* The `wasmer-python` bindings on PyPI are unmaintained (stalled at older Wasm standards), lacking robust epoch-based interruption and strict per-instance memory page ceilings in current Python 3.12 environments.
3. **QuickJS-wasm:**
   - *Evaluation:* Compiling QuickJS to Wasm solves JS sandboxing, but still requires an underlying WebAssembly host runtime. Wasmtime serves as the Tier A foundation upon which language interpreters can execute safely.
4. **Wasmtime Python (Chosen):**
   - *Evaluation:* Officially maintained by Bytecode Alliance. Supports exact deterministic fuel consumption (`store.set_fuel()`), epoch-based non-cooperative cooperative preemption (`engine.increment_epoch()`), strict linear memory ceilings (`store.set_limits(memory_size=...)`), zero default host imports, and sub-millisecond warm invocation (~0.2ms).

## 4. Security & Isolation Controls
- **Zero Host Imports:** Tier A explicitly imports only `(import "env" "kb_output")`. No WASI filesystem, network, environment variables, or clocks are imported into the guest sandbox.
- **Fuel Metering:** Bound to <= 50,000,000 instruction units. Loops or excessive CPU usage trap with `SCRIPT_FUEL_EXHAUSTED`.
- **Memory Ceiling:** Enforced at <= 512 64KiB pages (32 MiB) at module validation and runtime. Attempts to grow memory beyond ceiling trap with `SCRIPT_MEMORY_LIMIT`.
- **Preemptive Timeout:** Monotonic epoch timer thread ticks every 5ms; executions exceeding configured `timeout_ms` (default 500ms) trap with `SCRIPT_TIMEOUT`.
- **Binary Validation:** Rejects modules > 1 MiB, invalid headers, or missing required exports (`kb_alloc`, `kb_run`, `memory`).

## 5. Specialist Sign-offs
- **Architect Reviewer (`arch-reviewer` / `backend-architect`):**
  - *Verdict:* APPROVED
  - *Statement:* "Wasmtime 50.0.1 provides ideal Tier A sandboxing for 👍kanban. The architecture achieves clean separation between host Python runtime and untrusted guest code, meeting the < 2.0ms latency requirement with deterministic fuel limits."
- **Security Engineer (`sec-eng` / `security-engineer`):**
  - *Verdict:* APPROVED
  - *Statement:* "Supply chain and licensing checks pass cleanly (Apache-2.0 WITH LLVM-exception). The sandbox model enforces zero ambient authority: zero WASI imports, bounded linear memory (32 MiB), and non-cooperative preemption via epoch interruption."
- **QA Engineer (`qa-eng`):**
  - *Verdict:* APPROVED
  - *Statement:* "Automated unit test coverage across the sandbox runner, executor, and MCP tools exceeds 96%. Cold start latency is ~2.8ms, warm invocation is ~0.2ms, and all trap behaviors (fuel exhaustion, memory overflow, illegal imports) are verified deterministically."
