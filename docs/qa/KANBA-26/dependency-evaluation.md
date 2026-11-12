# Dependency Evaluation: KANBA-26 (KB-P3-30)

## Target Vendored Assets
1. **Inter Variable Font**
   - Path: `kanban/web/public/fonts/InterVariable.woff2`
   - License: SIL Open Font License 1.1 (SIL OFL-1.1)
   - Upstream Tag: `v4.1` (https://github.com/rsms/inter)
   - File Size: 352,240 bytes
   - SHA-256: `693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3`
   - License File: `kanban/web/public/fonts/OFL-Inter.txt` (SHA-256: `262481e844521b326f5ecd053e59b98c8b2da78c8ee1bdbb6e8174305e54935a`)

2. **JetBrains Mono Variable Font**
   - Path: `kanban/web/public/fonts/JetBrainsMonoVariable.woff2`
   - License: SIL Open Font License 1.1 (SIL OFL-1.1)
   - Upstream Tag: `v2.304` (https://github.com/JetBrains/JetBrainsMono)
   - File Size: 113,552 bytes
   - SHA-256: `54f9232d056c60a63c16357cd93a196ea0f0332845e831f94d6c1e42aebb46d5`
   - License File: `kanban/web/public/fonts/OFL-JetBrainsMono.txt` (SHA-256: `30f0c136e3c88e422d0791acd97238870f9054a9729bc34cf2ff0d4ed8cac4ad`)

---

## License Governance & Compatibility
- **License Expression:** `OFL-1.1`
- **Permissibility Assessment:**
  Per AGENTS.md and ARCHITECTURE_AND_PRODUCT_SPEC.md S2.5, SIL OFL-1.1 is strictly approved for vendored static binary font assets (`.woff2`) and is never used for compiled or linked application source code.
- **License Gate Integration:**
  Both font assets are explicitly registered in `license-allowlist.toml` under the `node` ecosystem with justifications exceeding 20 characters:
  * `inter-variable-font`: "Vendored static variable font assets for self-hosted UI typography under S6.1; no code execution."
  * `jetbrains-mono-variable-font`: "Vendored static variable font assets for tabular issue keys under S6.1; no code execution."
  The automated license gate (`make license` via `scripts/license_gate.py`) verifies zero violations.

---

## Supply-Chain Security & Attack Surface Analysis
- **Hermetic CSP Compliance:**
  Serving fonts from local paths (`/fonts/InterVariable.woff2` and `/fonts/JetBrainsMonoVariable.woff2`) fulfills Content-Security-Policy `font-src 'self'`.
- **Zero Third-Party Network Telemetry:**
  Eliminates remote CDN calls to Google Fonts or Typekit, preventing client IP harvesting, tracking cookies, and external service outage dependencies.
- **Zero Code Execution Risk:**
  Static `.woff2` font files contain glyph vector outlines and OpenType tables only; they contain no executable JavaScript or WebAssembly payloads.

---

## Architectural Rationale & Alternatives Considered
- **Self-Hosted Variable Fonts vs. System Font Stack Only:**
  * System fonts (`-apple-system`, `Segoe UI`, `Roboto`) introduce wide variance in glyph advance widths, ascender/descender metrics, and numeral kerning across operating systems (Linux, macOS, Windows, Android).
  * System font stacks fail to provide reliable `tabular-nums` support for monospaced issue keys (`KAN-142`) across non-Apple platforms.
  * Vendoring Inter Variable and JetBrains Mono Variable guarantees deterministic, cross-platform typographic baseline alignment and S6.1 whitespace fidelity.

---

## Pre-Flight Specialist Sign-offs (Verbatim from Swarm Board)

### 1. Test and Build Quality Engineer (`qa-eng`, Board Message #28)
```
### [DEP-EVAL KANBA-26] Vendored Inter and JetBrains Mono Variable Fonts (KB-P3-30)

- Target Assets:
  * InterVariable.woff2 (SIL OFL-1.1)
  * JetBrainsMonoVariable.woff2 (SIL OFL-1.1)
  * Stored in kanban/web/public/fonts/

- Test and Build Quality Assessment:
  * Static Asset Integrity: Both font files are vendored as static binary assets. Fulfills the strict Content-Security-Policy directive font-src 'self' without requiring external network fetches or CDN dependencies.
  * Deterministic Typographic Rendering: Variable font axes (wght 100-900 for Inter, 100-800 for JetBrains Mono) provide complete typographic coverage across headings, technical prose, and tabular numerals with two single asset files, eliminating layout shifts and network font waterfall latency.
  * Governance and Allowlist: Permitted under S2.5 and registered in license-allowlist.toml with SHA-256 checksums and exact upstream release tags. make license verifies zero violations.

- Alternatives Considered:
  * System font stack only: Causes cross-platform glyph metric divergence across Linux, macOS, and Windows. Variable fonts provide predictable pixel-exact alignment necessary for Kanban lane headers, card titles, and tabular issue keys.
  * Static per-weight WOFF2 bundles: Would require 10+ individual font files, increasing HTTP request volume and precompression overhead.

- Engineer #2 Sign-off: APPROVED
```

### 2. Security Engineer (`sec-eng`, Board Message #29)
```
### [DEP-EVAL KANBA-26] Vendored Inter and JetBrains Mono Variable Fonts
- Component: kanban/web/public/fonts/{InterVariable.woff2, JetBrainsMonoVariable.woff2}
- License: SIL Open Font License 1.1 (OFL-1.1)
- Security Assessment:
  * License Risk: Low. OFL-1.1 is approved for static font resources and does not apply copyleft conditions to linked or accompanying software. Recorded in license-allowlist.toml with explicit justification.
  * Supply-Chain Risk: Zero runtime network exposure. Eliminates dynamic external CDN requests (e.g. Google Fonts) and complies with the hardened font-src 'self' CSP directive.
  * Attack Surface: Negligible. Static font files contain no executable code and are served directly by the static file handler.
- Verdict: APPROVED
```

### 3. Systems/Backend Architect (`arch-reviewer`, Board Message #30)
```
### [DEP-EVAL KANBA-26] Vendored Inter and JetBrains Mono Variable Fonts

- Evaluator: Systems/Backend Architect (arch-reviewer)
- Scope: docs/tickets/KB-P3-30.md (KANBA-26 / KB-P3-30)
- Evaluated Assets:
  * InterVariable.woff2 (SIL Open Font License 1.1)
  * JetBrainsMonoVariable.woff2 (SIL Open Font License 1.1)
  * Stored in kanban/web/public/fonts/

1. License and Compatibility:
- Both font files are licensed under the SIL Open Font License 1.1 (SIL OFL-1.1).
- OFL-1.1 is an OSI-approved license. Per repository governance rules (AGENTS.md, S2.5), OFL-1.1 is strictly permitted for static font assets (.woff2) and is never permitted for linked or compiled software code.
- Recorded and justified in license-allowlist.toml with exact version tags and cryptographic SHA-256 digests.

2. Supply-Chain and Attack Surface:
- Self-hosting font assets locally under kanban/web/public/fonts/ ensures that no external network requests are made to third-party CDNs (such as Google Fonts). This complies with the strict font-src 'self' Content-Security-Policy and prevents client IP tracking and data leakage.
- Static .woff2 files are binary assets processed directly by the browser layout engine with zero JavaScript or executable code.

3. Architectural Rationale and Alternatives Considered:
- Self-hosted variable fonts vs. system font stack only:
  * While a system font stack avoids vendoring binary assets, system fonts suffer from significant cross-platform metric variations (glyph width, line heights, numeral widths) across Linux, macOS, Windows, and Android.
  * Standardizing on Inter Variable for body copy and JetBrains Mono Variable for tabular data, issue keys (e.g. KAN-142), and timestamps ensures consistent visual layout and prevents cumulative layout shifts across client devices.

4. Architectural Verdict:
APPROVED. Delivers self-hosted, CSP-compliant typography with consistent cross-platform typographic metrics.
```
