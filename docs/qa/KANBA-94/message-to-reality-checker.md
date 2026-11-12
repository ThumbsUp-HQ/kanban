# Forensic QA Verification Packet: Isolated Mermaid Web Worker Renderer (KB-P3-47)

- **Ticket:** `KANBA-94` (`KB-P3-47`: `[Phase 3 / Frontend] Isolated Mermaid Web Worker renderer with directive firewall, resource caps & 1500ms watchdog`)
- **Git Worktree:** `/tmp/kb-wt-KANBA-94`
- **Branch:** `feat/KANBA-94` (base: `7242005`)
- **Author:** `builder-17` (Swarm Implementation Author)
- **Target Audience:** `@reality-checker` (Passive Forensic QA Gate)

---

## 1. Executive Summary & Verification Matrix

Wave W15 ticket `KANBA-94` (`KB-P3-47`) implements an isolated Web Worker renderer for Mermaid diagrams with an AST directive firewall, strict resource caps (64KB source limit, 400 node limit, 1,000 edge limit), a 1,500ms watchdog timer, in-flight request deduplication, and an LRU cache of 64 rendered SVG strings. Rendered SVGs are converted to sandboxed `blob:` URLs via `safeSvg.ts` (`createSafeSvgBlobUrl`), mounted inside the existing `MediaViewport` component as `<img src="blob:...">`, and guaranteed to introduce strictly zero inline `<svg>` or `<foreignObject>` DOM elements into the ProseMirror editor surface.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Worker Isolation & Sandboxing** | Off-thread rendering in dedicated Web Worker | Handled off-thread in `mermaid.worker.ts`; zero blocking on main UI thread | PASS |
| **Directive & Threat Firewall** | Strip `%%{init...}%%`, directives, `@import`, JS clicks | Enforced in `mermaidFirewall.ts` with AST switch statements and state transitions | PASS |
| **Resource Boundaries** | 64 KiB source, 400 nodes, 1000 edges | Validated in `mermaidFirewall.ts` pre-render and defense-in-depth inside worker | PASS |
| **Watchdog Timer & Termination** | 1,500ms watchdog timer with worker termination | Implemented in `mermaidClient.ts`; terminates worker and cancels pending queue | PASS |
| **Zero Inline SVG DOM Execution** | ProseMirror DOM contains 0 `<svg>` / `<foreignObject>` | Verified in E2E tests: diagrams mounted strictly as `<img src="blob:...">` | PASS |
| **Strict CSP & Trusted Types** | Allowlisted `kanban-sanitizer` policy | Wrapped `window.Worker` with `toTrustedScriptUrl()`; 0 CSP violations | PASS |
| **Live Theme Synchronization** | Synchronize with document `data-theme` / `.dark` | MutationObserver triggers live re-render with semantic tokens; prior blob revoked | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95% all 4 metrics) | 58/58 passed in 3.39s; 100% Stmts, 96.49% Branch, 98.30% Funcs, 100% Lines | PASS |
| **Playwright E2E Verification** | 3 scenarios across Desktop, Tablet, Mobile (9 PNGs) | 9/9 passed in 13.7s; annotated screenshots and style probes captured | PASS |
| **Build, Typecheck & Quality** | Zero-Tolerance Quality Mandate (0 errors, 0 warnings) | `typecheck`, `eslint`, and `build` clean; 0 non-ASCII dashes repo-wide | PASS |

---

## 2. Supply-Chain & License Allowlist Verification

- **Direct Dependency:** `beautiful-mermaid@1.1.3` (MIT license, exact pin).
- **Transitive Dependency:** `elkjs@0.11.1` (EPL-2.0 license, exact pin).
- **Allowlist Exception:** Added exact exception for `elkjs@0.11.1` under `[allowlist.exceptions]` in `license-allowlist.toml` documenting build/runtime parity.
- **Architect & Security Approvals:**
  * `@qa-eng` sign-off: Swarm Board post #351.
  * `@sec-eng` sign-off: Swarm Board post #353.
  * `@arch-reviewer` sign-off: Swarm Board post #354.
  * Detailed supply-chain analysis recorded in `docs/qa/KANBA-94/dependency-evaluation.md`.

---

## 3. Mandatory Specialist Review Gates

1. **Dependency Evaluation Gate:** Unanimous sign-off from `@qa-eng`, `@sec-eng`, and `@arch-reviewer` captured in `docs/qa/KANBA-94/dependency-evaluation.md`.
2. **UI Specialist Gate:** Audit requested from `@ui-specialist` via swarm board post. Verbatim review recorded in `docs/qa/KANBA-94/ui-specialist-review.md`.

---

## 4. Forensic Evidence Manifest (`docs/qa/KANBA-94/`)

- `unit-test-results.txt`: Full Vitest run with v8 coverage report (58/58 passed, >=95% coverage across all metrics).
- `e2e-results.txt`: Playwright E2E execution log across 3 viewports (9 passed in 13.7s under strict CSP).
- `build-check.txt`: Clean output from `pnpm typecheck && pnpm lint && pnpm build`.
- `computed-styles-{desktop,tablet,mobile}.json`: Recorded computed CSS properties verifying containment and max-height caps.
- `screenshots/`: 9 annotated PNG screenshots (`01-mermaid-light-*`, `02-mermaid-dark-theme-sync-*`, `03-mermaid-watchdog-fallback-*`).
- `screenshots/ANNOTATIONS.md`: Comprehensive callout descriptions and viewport verification matrix.
- `dependency-evaluation.md`: Supply-chain security audit, vulnerability analysis, and license compliance documentation.
- `git-diff.patch`: Complete git diff against base `7242005`.
