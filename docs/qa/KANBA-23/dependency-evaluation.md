# Dependency Evaluation: ASGI App Factory, Static Server & Security Headers (KANBA-23 / KB-P0-10)

## 1. Scope & Target Dependencies
This document records the architectural, security, and quality evaluations for external runtime and test dependencies introduced for Ticket `KANBA-23` (`KB-P0-10`).
In accordance with repository governance invariants (`AGENTS.md`, `S2.5`), all dependencies are strictly permissive (`Apache-2.0`, `MIT`, or `BSD-3-Clause`) with zero viral copyleft (`GPL`, `AGPL`, `SSPL`, or static `LGPL`) and are cryptographically pinned in `uv.lock`.

### Evaluated Packages
- `fastapi==0.162.5`
  - License: MIT
  - Ecosystem: Python Web Framework
  - Wheel SHA-256: `sha256:5303c67415fde762889ca337db79d27b755b8bd09cef314fa7a4340bb30bfd2b`
  - Source Dist SHA-256: `sha256:1ca37f64f61c99cebd38636e67525fb721c5e8c1169f07f2a35d73b0a63265d4`
- `starlette==1.10.0` (transitive of FastAPI)
  - License: BSD-3-Clause
  - Ecosystem: Core ASGI Toolkit
  - Wheel SHA-256: `sha256:478c0ab3b4ced6e82719849c118fa406f0278a3499c1a898cd15cd31bdc38ce4`
  - Source Dist SHA-256: `sha256:b8399098d4c1e3522734f7235dc79b1fc967f96cf139c81e0fa30479e0685f9b`
- `uvicorn[standard]==0.54.0` (includes `uvloop==0.22.1`, `httptools==0.7.1`)
  - License: BSD-3-Clause (uvloop: MIT / Apache-2.0 dual; httptools: MIT)
  - Ecosystem: Production ASGI Runtime
  - Wheel SHA-256: `sha256:505bdb0f318731d45f1f712071fc781a8981f6847a31c902c9f5e652d4f67faf`
  - Source Dist SHA-256: `sha256:a2e33cbfaa0306f8e6b0c13e0cb89d7d7a2da3e62b90c66e18c33d9807b28620`
- `pydantic-settings==2.16.2`
  - License: MIT
  - Ecosystem: Type-Safe Environment Configuration
  - Wheel SHA-256: `sha256:8d523e5c129b097686bde019bd6109bff53f4c8c3f63f1ddf9933ffa42e5ab4f`
  - Source Dist SHA-256: `sha256:3dc08ffabed2bbd5dc2dd55ead7b78b4e4c5cd776aecd04310db5f1224caaf46`
- `httpx==0.28.1` (scoped strictly to root pyproject.toml dev group)
  - License: BSD-3-Clause
  - Ecosystem: Async In-Memory ASGI Test Client
  - Wheel SHA-256: `sha256:d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad`
  - Source Dist SHA-256: `sha256:75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc`

---

## 2. Alternatives Evaluated
1. **Raw Starlette vs FastAPI:**
   - Raw Starlette provides the foundational ASGI protocol handler, but lacks typed route decorators, automatic parameter validation, standard OpenAPI schema reflection (`/api/openapi.json`), and standardized RFC 9457 Problem Details error generation required for future API and MCP expansion.
   - FastAPI builds directly on Starlette with zero performance penalty while enforcing structured typing.
2. **Granian vs Uvicorn[standard]:**
   - Granian is a Rust-based HTTP server for Python. While promising in raw benchmarks, Uvicorn is the battle-tested industry standard with full support for Unix domain socket binding, zero-downtime reloads, and ASGI lifespan events across minimal Linux container environments.
3. **Requests / Urllib vs HTTPX:**
   - Standard requests or urllib require opening live loopback TCP sockets, incurring port contention and flake in concurrent CI runs.
   - HTTPX provides native `ASGITransport(app)` executing full HTTP request/response lifecycles in-memory with sub-millisecond execution times and zero socket allocation.

---

## 3. Specialist Evaluations & Sign-Offs

### A. Test and Build Quality Engineer (`qa-eng`, Board Post #28)
- **Role:** Engineer #2, Test and Build Quality Engineer
- **Evaluation:**
  - `fastapi` and `starlette`: High-performance ASGI framework enabling in-process testing via `httpx.ASGITransport(app)` and Starlette `TestClient`. In-process execution bypasses TCP loopback sockets and port allocation overhead, allowing full HTTP request and response cycle validation with sub-millisecond execution times and zero socket flakiness.
  - `uvicorn[standard]`: Production-grade ASGI runtime with Rust/C-accelerated event loops (`uvloop`) and HTTP parsing (`httptools`). Provides robust connection handling and deterministic lifecycle events.
  - `pydantic-settings`: Strict, environment-driven configuration model (`Settings`) validating environment variable prefixes (`KB_`), paths (`web_dist`), and security modes before server binding. Fails closed immediately on invalid configuration.
  - `httpx`: Essential async test client providing native ASGI transport support for integration test suites without spawning background server processes.
  - Security and Performance Integration: Delivers precompressed SPA asset negotiation (`.br` / `.gz`) and attaches strict Content-Security-Policy and hardening headers to all responses while remaining within latency SLAs.
- **Verdict:** `APPROVED`

### B. Application and Supply-Chain Security Engineer (`sec-eng`, Board Post #29)
- **Role:** Engineer #1, Application and Supply-Chain Security Engineer
- **Evaluation:**
  - License Compliance: 100% permissive (`MIT`, `BSD-3-Clause`, `Apache-2.0`). Zero viral copyleft.
  - Attack Surface Minimization: `docs_url=None` and `redoc_url=None` are enforced by default, preventing unauthorized exploration of interactive API documentation in production environments.
  - Content Security Policy (CSP): Enforces byte-identical S5.4 production policy on every response, forbidding inline scripts/styles, requiring trusted types, and restricting resource origins to self.
  - Hardening Headers: Applies `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy: same-origin`, and production HSTS (`Strict-Transport-Security: max-age=63072000; includeSubDomains`).
  - Path Traversal and DoS Defense: `PrecompressedSPAStaticApp` enforces single percent-decoding, rejects null bytes, backslashes, and `..` segments, and validates absolute paths against `dist_dir.resolve()` to prevent symlink traversal escapes. File streaming is capped at 50 MiB in 64 KiB chunks to prevent memory exhaustion attacks.
  - Cleartext Network Prevention: Standalone mode rejects cleartext HTTP requests from non-loopback hosts with 403 `CLEARTEXT_HTTP_BLOCKED`, requiring reverse-proxy TLS termination.
- **Verdict:** `APPROVED`

### C. Systems/Backend Architect (`arch-reviewer`, Board Post #30)
- **Role:** Systems/Backend Architect
- **Evaluation:**
  - License and Compatibility: All components and transitive dependencies (`fastapi`, `starlette`, `uvicorn`, `uvloop`, `httptools`, `pydantic-settings`, `httpx`) are licensed under MIT, BSD-3-Clause, or Apache-2.0. Completely permissive, zero copyleft. 100% compliant with repository license invariants.
  - Supply-Chain and Attack Surface: `fastapi`, `starlette`, `uvicorn`, and `pydantic-settings` form the core ASGI server layer for the unified kanban application. `uvicorn[standard]` utilizes high-performance C-based event loops (`uvloop`) and HTTP parsers (`httptools`) to guard against slowloris and HTTP parsing vulnerabilities. `PrecompressedSPAStaticApp` enforces strict path-traversal prevention and serves pre-compressed Brotli (`.br`) and gzip (`.gz`) assets with immutable caching.
  - Architectural Rationale: `fastapi` builds directly on Starlette, providing automatic OpenAPI documentation (`/api/openapi.json`), robust parameter validation, and standard problem+json error formatting required for the unified REST and MCP API gateways. `uvicorn` is the mature industry standard with seamless support for Unix domain socket binding, reload hooks, and ASGI lifespan events across diverse Linux container environments.
- **Verdict:** `APPROVED`
