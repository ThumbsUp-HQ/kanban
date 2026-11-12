# Dependency Evaluation: beautiful-mermaid (KB-P3-47 / KANBA-94)

- **Target Ticket:** `KANBA-94` (`KB-P3-47`: `[Phase 3 / Frontend] Isolated Mermaid Web Worker renderer with directive firewall, resource caps & 1500ms watchdog`)
- **Evaluated Package:** `beautiful-mermaid@1.1.3`
- **License:** `MIT` (Permissive; 100% Apache-2.0 distribution compliant; zero GPL/AGPL copyleft viral infection)
- **Transitive Dependencies:**
  * `elkjs@0.11.1` (`EPL-2.0` layout-engine exception documented in `license-allowlist.toml`)
  * `entities@7.0.1` (`BSD-2-Clause` permissive)
- **Lockfile Checksum:** `pnpm-lock.yaml` SHA-512 `sha512-TItrtrAyHp1vwFfFVYauWGrquouk/6SS21Aq3RsxindSYZODcN4xYrPZD6BiZRU+o5mKJzDPz9MUSMvELdylyg==`
- **Package SHA-256 Digest:** `54acbb8c0d458bfed51bd5e116eb64d475390ac1893bc25a31148646fd9a2c39` (dist/index.js)
- **Repo License Gate Status:** PASS (Zero violations reported by `uv run python -m scripts.license_gate`)

---

## 1. Architectural Justification & Context

Section S5.3 of `ARCHITECTURE_AND_PRODUCT_SPEC.md` mandates safe client-side Mermaid rendering with directive stripping, resource caps (<= 64 KB, <= 400 nodes, <= 1,000 edges), and off-main-thread Web Worker execution with a 1,500 ms watchdog.

Standard `mermaid.js` requires a live browser DOM (`document.createElement`), uses `foreignObject` HTML tags, and dynamically mutates inline CSS rules inside the host document. This directly violates Section 5.4 Content Security Policy (`style-src 'self'`, `worker-src 'self'`, and `require-trusted-types-for 'script'`).

`beautiful-mermaid` (authored by Craft Docs under MIT) provides an ultra-fast, headless TypeScript SVG layout engine:
- Zero DOM dependency: runs pure Sugiyama/ELK graph layout in Web Worker context.
- Zero `<foreignObject>` HTML output: generates pure SVG vector elements (`<rect>`, `<path>`, `<text>`, `<polygon>`).
- Zero dynamic CSS injection: styles elements via resolved CSS variables or SVG presentation attributes.
- Memory hygiene: operates cleanly inside dedicated module workers and passes through `createSafeSvgBlobUrl()` for safe `<img src="blob:...">` sandboxing inside `<MediaViewport>`.

---

## 2. Alternatives Considered

1. **Standard `mermaid` core (`@mermaid-js/mermaid`):**
   - *Evaluation:* Heavyweight (> 2.5 MB bundle), requires DOM/JSDOM for SVG generation, injects inline `<style>` and `<foreignObject>` containing HTML, breaking CSP `style-src 'self'` and opening XSS injection vectors.
   - *Verdict:* REJECTED. Incompatible with security invariants and CSP requirements.

2. **Server-side CLI rendering (`mermaid-cli` / Puppeteer):**
   - *Evaluation:* High CPU overhead per ticket/comment render, requires server process forks and headless Chrome daemons, introduces network hops and latency for interactive editing.
   - *Verdict:* REJECTED. Violates client-side zero-latency responsive editing requirements.

3. **`beautiful-mermaid` (MIT):**
   - *Evaluation:* Pure TypeScript SVG renderer with zero DOM requirements, fully compatible with Web Workers, generates pure SVG without `<foreignObject>`, and accepts theme CSS variable overrides.
   - *Verdict:* APPROVED. Exactly fulfills the S5.3 architectural specification.

---

## 3. Supply Chain Security & Risk Assessment

- **Attack Surface:** Runs inside dedicated module Web Worker (`worker-src 'self'`). Because worker has zero DOM access and emits string SVGs which are parsed and sanitized by `createSafeSvgBlobUrl()` before mounting via `<img>`, any malformed or malicious markup is defanged at the worker, sanitizer, and image decoder levels.
- **Resource Constraints:** Paired with `mermaidFirewall.ts` enforcing 64 KB source size, 400 node limit, 1,000 edge limit, directive stripping, and 1,500 ms `worker.terminate()` watchdog fallback.
- **License Allowlist:** `elkjs@0.11.1` under EPL-2.0 is an unmodified runtime layout bundle covered by an explicit exception entry in `license-allowlist.toml`.

---

## 4. Swarm Consensus & Formal Sign-offs

In accordance with the Paranoiac Security Mandate and Swarm Collaboration standards, introduction of this new dependency was submitted for specialist review and approved:

1. **Test & Build Quality Engineer Sign-off (Board Message #351):**
   - Verified deterministic reproducibility via exact SHA-512 lockfile integrity digest.
   - Confirmed permissive licensing (MIT + transitives) and clean license gate validation.
   - Verified worker isolation and testability with fast, deterministic Vitest suites.
   - Verdict: APPROVED.

2. **Security Engineer Sign-off (Board Message #353):**
   - Verified MIT and BSD-2-Clause permissive licensing, with EPL-2.0 layout bundle exception.
   - Verified zero DOM access, zero foreignObject HTML, and elimination of DOM XSS vectors.
   - Verified alignment with strict CSP style-src 'self' (zero dynamic style injection).
   - Confirmed zero telemetry or outbound network side-effects.
   - Verdict: APPROVED.

3. **Systems/Backend Architect Sign-off (Board Messages #167, #354):**
   - Verified MIT license compatibility with Apache-2.0 distribution standards.
   - Confirmed headless Web Worker isolation (worker-src 'self') and zero main-thread hangs.
   - Verified lockfile integrity digest.
   - Re-confirmed architectural approval over standard mermaid core.
   - Verdict: APPROVED.
