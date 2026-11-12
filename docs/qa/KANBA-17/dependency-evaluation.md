# Dependency Evaluation: KANBA-17 (KB-P0-03)

- Ticket: KANBA-17 / KB-P0-03
- Title: Frontend skeleton kanban/web (React 19 + Vite + TS strict)
- Evaluators:
  * Systems/Backend Architect (`arch-reviewer`)
  * Application & Supply-Chain Security Engineer (`sec-eng`)
  * Test & Build Quality Engineer (`qa-eng`)
- Policy Standards: Permissive Apache-2.0 compatibility (zero GPL/AGPL/SSPL/LGPL), strict cryptographic lockfile pinning, hostile supply-chain hardening, zero unauthorized network egress/telemetry, and minimal attack surface.

---

## 1. Evaluated Dependencies Matrix

| Package | Version | License | Integrity Hash (from pnpm-lock.yaml) | Role / Usage |
| :--- | :--- | :--- | :--- | :--- |
| `react` | `19.3.1` | MIT | `sha512-QNhWdt7nrgVWWQG58QuGsAR3jv3Hbe4mb4vz7w2csnHavciZJgda1CPNaldF6eVxv90ud3jUXpKlHL69gO38yw==` | Core UI rendering engine |
| `react-dom` | `19.3.1` | MIT | `sha512-Y0bARz53lhEC1NMCASs0/j+faB/zqt3R8hpvg1e8+61ZVJ4UL0UdC4cBbXfZMcIuhrfgeILTLe+ZeBCavQPtKQ==` | DOM bindings for React 19 |
| `vite` | `8.3.8` | MIT | `sha512-LzOn3h9rG/0vhLdXrV4yJ4QFA9eEoqCl+Yx+kGJd7aB9w6nfNgVHKSYwLPZUHrz4ZGa+t+kXjV9itvcHDLQouA==` | Next-generation frontend build tooling and dev server |
| `@vitejs/plugin-react` | `6.3.0` | MIT | `sha512-H9E955aVvD2F4zNHCw4eIZbIfF6xKldlh7MNu+hSU7xwQzh65lI/N+CJWqmfhi0PEjDXIt/H7T7J/4wU63KJiw==` | Fast Refresh and JSX transformation Vite plugin |
| `typescript` | `5.9.3` | Apache-2.0 | `sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw==` | Strict static typing system (matches monorepo license) |
| `eslint` | `10.14.0` | MIT | `sha512-T0pNsxkb9IKmtQjhpK3d7nWOpFv+YHuMbTJnSVMoQblF0onvXfErrtp4V1jHtsQPan7dKaGVD0q1WCXnzMF31A==` | Static analysis and linting engine |
| `typescript-eslint` | `8.72.2` | MIT | `sha512-c/+AKMW1KB81r28Sp0AAdcyXj5dzNmAsZFcsrxKbZTKmcBK2xIwBR31dcSYSDu3bKmzXe8GKrSxO+eDQ401Uzg==` | Type-aware linting rules (strictTypeChecked + stylisticTypeChecked) |
| `eslint-plugin-react-hooks` | `7.1.1` | MIT | `sha512-f2I7Gw6JbvCexzIInuSbZpfdQ44D7iqdWX01FKLvrPgqxoE7oMj8clOfto8U6vYiz4yd5oKu39rRSVOe1zRu0g==` | React hooks rules enforcement |
| `vitest` | `5.1.0` | MIT | `sha512-MzmNFnrwa8v8lF1bLxw3UJ4EREwVOVb75VqJZmUDRjJ6EluK/x9th7qTbaeDk41WxE1GxWqmTXcdsfobfH5sOA==` | Vite-native unit test runner |
| `@vitest/coverage-v8` | `5.1.0` | MIT | `sha512-OY9aShBQG5KOIw2zCo9fDoCHI9RHliNHJ//nM7m6jGg41Hyke9JOGWmeMlK74xYErsxMoK8mIB3gAeEyFVA7LA==` | Native v8 code coverage provider |
| `@testing-library/react` | `16.3.3` | MIT | `sha512-Uo193NgQbPMz6lrrhtRQQFcMC6Re/ELLFbbuVL30WDlZxlpZf9/lMHTAVxPRLw1q1iu9OJmR1c2BLiENRstdBg==` | DOM testing utilities adhering to user interaction |
| `jsdom` | `29.1.1` | MIT | `sha512-ECi4Fi2f7BdJtUKTflYRTiaMxIB0O6zfR1fX0GXpUrf6flp8QIYn1UT20YQqdSOfk2dfkCwS8LAFoJDEppNK5Q==` | Headless DOM environment for offline unit testing |

Note: `jsdom@29.1.1` was selected because `jsdom@30+` requires `node >= 22.22.2` whereas our workspace Node runtime is `v22.22.1`. Under `.npmrc` `engine-strict=true`, `jsdom@29.1.1` matches `node: ^20.19.0 || ^22.13.0 || >=24.0.0` perfectly with 0 warnings.

---

## 2. Alternatives Considered

- Local `node:zlib` plugin vs. `vite-plugin-compression`:
  * External third-party compression plugins pull in unvetted transitive dependencies and increase supply-chain attack surface.
  * Our local `kanban/web/build/precompress.ts` plugin uses built-in standard Node.js modules (`node:zlib` and `node:crypto`) with zero third-party runtime dependencies. It natively enforces path-traversal prevention (`..` rejection), Brotli quality 11, gzip level 9, and SHA-384 Subresource Integrity manifest generation.
- `vitest` vs. `jest`:
  * `jest` requires complex Babel or ts-jest transformation layers, separate configuration schemas, and duplicate module resolution logic.
  * `vitest` shares Vite configuration, plugin pipelines, and ES module resolution natively, yielding sub-second test execution and seamless v8 branch coverage enforcement.
- Static CSS modules vs. runtime CSS-in-JS (`styled-components` / `@emotion/*`):
  * Runtime CSS-in-JS is strictly banned per S2.5. It injects dynamic `<style>` elements into the DOM at runtime, violating strict Content-Security-Policy (CSP) `style-src 'self'`.
  * Static CSS files imported at compile time emit clean separate `.css` assets loaded via `<link rel="stylesheet">`, satisfying CSP with zero inline style tags.

---

## 3. Specialist Evaluations & Sign-Offs

### Systems/Backend Architect (`arch-reviewer`)
- Verdict: APPROVED
- License & Compatibility: All dependencies are licensed under permissive licenses (MIT or Apache-2.0). 100% compliant with project licensing invariants. Zero GPL, AGPL, SSPL, or LGPL components.
- Supply-Chain & Attack Surface: Managed under a dedicated pnpm workspace (`kanban/web`) with `engine-strict=true` and `ignore-scripts=true` in `.npmrc`. Production build emits static assets only; zero Node.js runtime dependencies are introduced into production deployments.

### Application & Supply-Chain Security Engineer (`sec-eng`)
- Verdict: APPROVED
- Supply-Chain & Tamper Resistance: Lockfile integrity verified with SHA-512 hashes recorded in `pnpm-lock.yaml`. Hardened `.npmrc` configuration (`ignore-scripts=true`, `save-exact=true`) strictly neutralizes arbitrary lifecycle execution during installation.
- CSP & SRI Compliance: Zero runtime CSS-in-JS injection. Production build emits static precompressed Brotli (`.br`) and gzip (`.gz`) assets with `dist/sri-manifest.json` containing SHA-384 hashes. Zero inline scripts or styles in `dist/index.html` ensures strict adherence to `script-src 'self'` and `style-src 'self'`.

### Test & Build Quality Engineer (`qa-eng`)
- Verdict: APPROVED
- Test & Build Quality Assessment: TypeScript strict configuration verified with all required compiler options. ESLint configured with type-checked rules and banned imports. Vitest configured with 95% thresholds across lines, functions, branches, and statements, achieving 100% coverage on tested modules with sub-second execution speeds.
