# Dependency Evaluation: dompurify (KB-P3-48 / KANBA-78)

- **Target Ticket:** `KANBA-78` (`KB-P3-48`: `[Phase 3 / Frontend] Client safe SVG blob sanitizer, <MediaViewport> pan/zoom lightbox & external media shield badge`)
- **Evaluated Package:** `dompurify@3.4.17`
- **Companion Types:** `@types/dompurify@3.2.0`
- **License:** `Apache-2.0 OR MPL-2.0` (Dual licensed, file-level permissive; zero GPL/AGPL runtime viral infection)
- **Repo License Gate Status:** PASS (Zero license violations reported by `uv run python -m scripts.license_gate`)
- **Lockfile Checksum:** `pnpm-lock.yaml` SHA-256 `a595db411768d7424814230f8c358d44baea0194af56b32501d815fb5d0d5617`

---

## 1. Architectural Justification & Context

Section S5.4 of `ARCHITECTURE_AND_PRODUCT_SPEC.md` mandates dual-layer sanitization for untrusted SVG vector content:
1. Server-side validation via Rust `roxmltree` on attachment upload.
2. Client-side sanitization via `createSafeSvgBlobUrl()` before mounting any SVG into `<MediaViewport>`.

Client vector sanitization requires a hardened, battle-tested sanitization engine capable of operating under strict browser Content Security Policy (`default-src 'none'; script-src 'self'; worker-src 'self'; style-src 'self'; img-src 'self' blob: data:image/png data:image/webp; font-src 'self'; connect-src 'self' wss:; media-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; require-trusted-types-for 'script'; trusted-types kanban-sanitizer dompurify`).

`dompurify` provides the primary DOM sanitization layer, which is combined with our secondary DAG guard in `safeSvg.ts` to enforce acyclic local `<use>` references (max depth 4, max 500 expanded nodes) and sandboxed `blob:` URLs for rendering via standard `<img>` tags (zero inline `<svg>` in document DOM).

---

## 2. Alternatives Considered

1. **In-house Regex / Pure XML Parser:**
   - *Evaluation:* Parsing XML/SVG with regex or simple DOM walkers is notoriously susceptible to parser-differential attacks (e.g. namespace confusion, CDATA tricks, entity expansion, encoding edge cases).
   - *Verdict:* REJECTED. Security-critical vector sanitization requires a dedicated, battle-tested sanitization library.

2. **`sanitize-html`:**
   - *Evaluation:* Heavyweight Node.js-centric package designed for server-side HTML cleanup. Pulls in large transitive dependency trees (`htmlparser2`, `postcss`, etc.) and has poor client-side tree-shaking and SVG profile controls.
   - *Verdict:* REJECTED. Violates our minimal dependency and zero-bloat mandates.

3. **`dompurify`:**
   - *Evaluation:* Industry standard for client-side HTML and SVG sanitization with zero runtime dependencies. Provides a dedicated SVG profile (`USE_PROFILES: { svg: true, svgFilters: false }`), explicit tag and attribute allowlists, and first-class W3C Trusted Types policy support.
   - *Verdict:* APPROVED. Exactly fulfills the S5.4 architectural specification.

---

## 3. Supply Chain Security & Risk Assessment

- **Transitive Dependencies:** 0 runtime dependencies. Pure client-side library.
- **Supply Chain Pinning:** Pinned to exact version `3.4.17` in `kanban/web/package.json` (no caret or tilde ranges). Cryptographic integrity verified via pnpm lockfile SHA-512 tarball integrity.
- **Attack Surface:** `dompurify` executes strictly in the user browser before generating `blob:` URLs. Because all output is rendered via `<img src="blob:...">`, script execution, foreignObject nesting, and CSS bleeding are blocked at both the sanitizer level and the browser C++ image decoder level.
- **Trusted Types Integration:** Compatible with `kanban-sanitizer` and `dompurify` Trusted Types policies enforced by `require-trusted-types-for 'script'`.

---

## 4. Swarm Consensus & Formal Sign-offs

In accordance with the Paranoiac Security Mandate and Swarm Collaboration standards, introduction of this new dependency was submitted for specialist review and approved:

1. **Security Architect Sign-off (Board Message #167):**
   - Verified Apache-2.0 / MPL-2.0 permissive licensing with zero viral copyleft restrictions.
   - Verified strict SVG profile configuration (`svg: true`, `svgFilters: false`) and removal of `<foreignObject>`, `<iframe>`, `<style>`, and SMIL animation vectors.

2. **Frontend Architect Sign-off (Board Message #170):**
   - Confirmed zero runtime dependencies and compatibility with Vite, TypeScript 5.9, and React 19.
   - Verified that `dompurify` operates cleanly inside `createSafeSvgBlobUrl()` and produces revokable `blob:` URLs for `<MediaViewport>`.

3. **Principal Systems Engineer Sign-off (Board Message #178):**
   - Confirmed exact pinning in `package.json` (`3.4.17`) and verified clean execution of `uv run python -m scripts.license_gate`.
   - Verified that client CSP `require-trusted-types-for 'script'; trusted-types kanban-sanitizer dompurify` permits policy initialization without runtime violations.
