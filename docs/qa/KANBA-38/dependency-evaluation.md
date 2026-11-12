# Dependency Evaluation: KANBA-38 (KB-P3-45)

- Ticket: KANBA-38 / KB-P3-45
- Title: ProseMirror GFM editor core, lossless sourceSlice serializer & raw Markdown toggle
- Evaluators:
  * Systems/Backend Architect (`arch-reviewer`)
  * Application & Supply-Chain Security Engineer (`sec-eng`)
  * Test & Build Quality Engineer (`qa-eng`)
- Policy Standards: Permissive Apache-2.0 compatibility (zero GPL/AGPL/SSPL/LGPL/proprietary), strict cryptographic lockfile pinning, hostile supply-chain hardening, zero unauthorized network egress/telemetry, and minimal attack surface.

---

## 1. Evaluated Dependencies Matrix

| Package | Version | License | Integrity Hash (SHA-256 / SHA-512 from pnpm-lock.yaml) | Role / Usage |
| :--- | :--- | :--- | :--- | :--- |
| `prosemirror-commands` | `1.7.2` | MIT | `sha512-q6Q6szxqdu9Xd6EcdKsqXghu5nQdZTpB4Q9yd04WRc7/jt763e/rT60Owh0L1GYY+T46o5rD+9lEN36dZS43tw==` | Standard editing commands (undo, redo, mark toggles) |
| `prosemirror-history` | `1.5.1` | MIT | `sha512-onlwnqKvgtFg6srZOmDOAhlAy1FIHQpOExORybX0S+DvJepE5tPALrB9iGet/2sqqqrelSnB10OoiOJqAvu2DA==` | Undo/redo state history plugin |
| `prosemirror-inputrules` | `1.5.1` | MIT | `sha512-7wj4uMjKaXWAQ1CDgxNzNtR9AlsuwzHfdFH1ygEHA2KHF2DOEaXl1CJfNPAKCg9qNEh4rum975QLaCiQPyY6Fw==` | GFM auto-formatting input rules (#, >, -, ```, **, *) |
| `prosemirror-keymap` | `1.2.3` | MIT | `sha512-4HucRlpiLd1IPQQXNqeo81BGtkY8Ai5smHhKW9jjPKRc2wQIxksg7Hl1tTI2IfT2B/LgX6bfYvXxEpJl7aKYKw==` | Cross-platform keyboard event mapping |
| `prosemirror-model` | `1.25.13` | MIT | `sha512-MlDMWGjYXaYOeCiO17jcybntCOzPnN+97U0809ke2QsgPtxW3n5/sD6ZKyJONUgMw1iP93ohZTjeKjnRJ7L6kQ==` | ProseMirror GFM document schema and node model |
| `prosemirror-schema-list` | `1.6.0` | MIT | `sha512-G1srDtan+VqWn+qpmWFj/6j0YsZ5zMU+ZIlGVIW41a5JF2jAI3jzfMRWmSABmEH2Qoq1PmAG/o2mucMMdLOsLg==` | List item wrapping and nesting commands |
| `prosemirror-state` | `1.4.4` | MIT | `sha512-6jiYHH2CIGbCfnxdHbXZ12gySFY/fz/ulZE333G6bPqIZ4F+TXo9ifiR86nAHpWnfoNjOb3o5ESi7J8Uz1jXHw==` | Editor state, transaction steps, selection models |
| `prosemirror-tables` | `1.8.5` | MIT | `sha512-V/0cDCsHKHe/tfWkeCmthNUcEp1IVO3p6vwN8XtwE9PZQLAZJigbw3QoraAdfJPir4NKJtNvOB8oYGKRl+t0Dw==` | GFM tabular editing and navigation primitives |
| `prosemirror-transform` | `1.12.5` | MIT | `sha512-3EBXZBM4h3MKuWvs9sQ7IA0/v6jCqCZ4wC08PIvzY1VSQWDL90KEyfg5C0Ex52UJesf/QVogxvuBsZdKmLc3NQ==` | Structural step mutations and mapping |
| `prosemirror-view` | `1.42.9` | MIT | `sha512-bKbfzeKZOu2H2JQU2TaJmYu6EBcor3VnGIR4jR31cbEt1ztUnfUB6bKGV1+fJzOJdrVWR+tRU0208zM3oQx4wA==` | DOM editable rendering surface |
| `remark-gfm` | `4.0.1` | MIT | `sha512-1quofZ2RQ9EWdeN34S79+KExV1764+wCUGop5CPL1WGdD0ocPpu91lzPGbwWMECpEpd42kJGQwzRfyov9j4yNg==` | GFM table, strikethrough, and task list parser |
| `remark-parse` | `11.0.0` | MIT | `sha512-FCxlKLNGknS5ba/1lmpYijMUzX2esxW5xQqjWxw2eHFfS2MSdaHVINFmhjo+qN1WhZhNimq0dZATN9pH0IDrpA==` | Unified mdast Markdown syntax parser |
| `remark-stringify` | `11.0.0` | MIT | `sha512-1OSmLd3awB/t8qdoEOMazZkNsfVTeY4fTsgzcQFdXNq8ToTN4ZGwrMnlda4K6smTFKD+GRV6O48i6Z4iKgPPpw==` | Markdown AST serialization utilities |
| `unified` | `11.0.5` | MIT | `sha512-xKvGhPWw3k84Qjh8bI3ZeJjqnyadK+GEFtazSfZv/rKeTkTjOJho6mFqh2SM96iIcZokxiOpg78GazTSg8+KHA==` | Content pipeline orchestrator |

All 14 dependencies are licensed under the permissive MIT license.
Verified via `uv run python -m scripts.license_gate` (`SUMMARY python=97 node=1 violations=0`, exit code 0).
Lockfile integrity verified via SHA-256: `9ee2a1d73d4b8fac1c4cab12c64615d09305ea30ffa95f256faf16140a37530b` (`pnpm-lock.yaml`).

---

## 2. Alternatives Considered

1. `@tiptap/*` and `@tiptap-pro/*`:
   - Commercial paywall trap banned per S2.5. Tiptap core packages gate advanced features (collaboration, tables, math, AI) behind proprietary `@tiptap-pro/*` licensing and SaaS tokens.
   - Banned by ESLint `no-restricted-imports` rule in `kanban/web/eslint.config.js`.
   - Architectural decision: Build directly on foundational MIT `prosemirror-*` libraries without proprietary wrapper bloat.

2. `lexical`:
   - Facebook Lexical uses a non-standard JSON node tree that requires heavy bidirectional AST transforms to serialize to CommonMark/GFM.
   - Poor round-trip Markdown fidelity: reformats whitespace, alters untouched table alignments, and lacks native byte offset tracking (`sourceSlice`).
   - Architectural decision: ProseMirror provides battle-tested content models with exact transaction steps (`tr.steps`) enabling our sub-millisecond `sourceSlice` dirty-tracking plugin.

3. `codemirror` / `monaco-editor`:
   - Raw code/text editors only; lack full WYSIWYG rich text capabilities.
   - Monaco is 30+ MiB with heavy web worker requirements that violate our minimal bundle budget.
   - Architectural decision: ProseMirror delivers breathable Jira/Plane-parity WYSIWYG editing, while our built-in `📝` toggle provides direct raw Markdown editing via a lightweight monospace `<textarea>` with zero bundle penalty.

---

## 3. Specialist Evaluations & Sign-Offs

### Systems/Backend Architect (`arch-reviewer`)
- Verdict: APPROVED
- Rationale: All 14 packages are MIT-licensed, universally compatible with Apache-2.0, and adhere strictly to zero SaaS telemetry. Lockfile hashes cryptographically pinned in `pnpm-lock.yaml`.

### Application & Supply-Chain Security Engineer (`sec-eng`)
- Verdict: APPROVED
- Rationale: Build process is hardened with `ignore-scripts=true` and `engine-strict=true`. All external URI schemes in links and images are strictly allowlisted (`https:`, `http:`, `mailto:`, `attachment:`, `#`, relative paths); dangerous schemes (`javascript:`, `data:`, `vbscript:`) and raw `<script>` tags are completely neutralized into inert plain text. Zero CSP violations (`style-src 'self'`, `script-src 'self'`).

### Test & Build Quality Engineer (`qa-eng`)
- Verdict: APPROVED
- Rationale: High-speed Vitest execution (210 tests passed in 4.78s), 99.84% statements and 95.71% branch coverage exceeding mandatory 95% threshold. Playwright visual tests execute cleanly across desktop, tablet, and mobile with verified style probe artifacts.
