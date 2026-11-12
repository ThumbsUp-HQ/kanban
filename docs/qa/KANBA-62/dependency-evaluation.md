# Dependency Evaluation: KANBA-62 (MCP Server Skeleton)

## 1. Executive Summary
Ticket KANBA-62 introduces internal HTTP/2 mTLS client communication between the MCP server (`kanban-mcp`) and the core application (`kanban-api`). Two new Python runtime dependencies are added to `mcp/pyproject.toml` and pinned in `uv.lock`:
1. `httpx == 0.28.1` (BSD-3-Clause)
2. `h2 == 4.4.1` (MIT)

Strict mandate compliance: The official Python MCP SDK (`mcp` on PyPI) is deliberately EXCLUDED to eliminate the critical package namespace collision with the local workspace package directory `mcp/` and to avoid unnecessary SaaS abstraction bloat. The MCP Streamable HTTP JSON-RPC 2.0 protocol is implemented natively in `mcp/protocol.py`.

## 2. Dependency Audit & Cryptographic Hashes

### Package: `httpx`
- **Version:** `0.28.1`
- **License:** `BSD-3-Clause` (Permissive, Apache-2.0 compatible)
- **Source:** PyPI
- **sdist:** `httpx-0.28.1.tar.gz`
  - SHA256: `75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc`
- **Purpose:** Internal HTTP client supporting HTTP/2, mTLS certificates (`internal_ca_path`, `client_cert_path`, `client_key_path`), streaming response limits, and in-process `ASGITransport` for tests and single-container deployments.

### Package: `h2`
- **Version:** `4.4.1`
- **License:** `MIT` (Permissive, Apache-2.0 compatible)
- **Source:** PyPI
- **sdist:** `h2-4.4.1.tar.gz`
  - SHA256: `4e866ffb1a869ae14dd9b5e6beb5c24a13da0495ad72b65925ded182521c1516`
- **wheel:** `h2-4.4.1-py3-none-any.whl`
  - SHA256: `0e25f1462b23c9cb82d9eb02e28bc706dac2a68cb457c6a0d74d63c8a2a5d0e6`
- **Transitive Dependencies:** `hpack == 4.2.0` (BSD-3-Clause), `hyperframe == 6.1.0` (MIT)
- **Purpose:** Pure-Python HTTP/2 state machine enabling `httpx.AsyncClient(http2=True)`.

## 3. Exclusion Rationale: PyPI `mcp` SDK
- **Namespace Collision:** Installing the PyPI package `mcp` causes Python's module resolution to collide with the repository root package directory `mcp/`.
- **Minimal Surface:** The platform requires only 5 JSON-RPC methods (`initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`) over Streamable HTTP. The official SDK carries large transport abstractions (stdio, SSE, websockets) not needed for the Streamable HTTP standard (`2025-06-18`).
- **Security & Control:** In-house implementation in `mcp/protocol.py` guarantees strict 1 MiB body limits, batch rejection, explicit DNS rebinding origin validation, and zero direct database access.

## 4. Alternatives Considered
1. **`aiohttp`:**
   - Pros: Mature async HTTP library.
   - Cons: Does not support HTTP/2 without experimental extensions; lacks native `ASGITransport` support for in-process testing. Rejected.
2. **Standard Library `urllib.request` / `http.client`:**
   - Pros: Zero external dependencies.
   - Cons: Synchronous only; lacks HTTP/2 multiplexing, modern connection pooling, and clean async integration with Starlette event loops. Rejected.
3. **`httpx` + `h2` (Selected):**
   - Pros: Unified async API, first-class HTTP/2 via `h2`, built-in mTLS and `ASGITransport` support, permissive BSD/MIT licensing. Approved.

## 5. Specialist Consultations & Swarm Sign-Offs
The dependencies and architecture were reviewed and approved by specialist peers on the swarm message board:
- **Architect Reviewer (`arch-reviewer`):** Sign-off in board post #116 approving `httpx` + `h2` and namespace-safe custom Streamable HTTP handler.
- **Security Engineer (`sec-eng`):** Sign-off in board post #118 validating cryptographic pinning, mTLS validation, zero plain-text wire transmission, and absence of database access.
- **QA Engineer (`qa-eng`):** Sign-off in board post #120 confirming testability with `ASGITransport` and `MockTransport`, transcript capture, and test coverage mandates.
