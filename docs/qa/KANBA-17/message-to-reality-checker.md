# Forensic Message to Reality-Checker: KANBA-17

- Ticket: KANBA-17 (KB-P0-03: `[Phase 0 / Web] Frontend skeleton kanban/web (React 19 + Vite + TS strict)`)
- Worktree Branch: `feat/KANBA-17` inside isolated worktree `/tmp/kb-wt-KANBA-17`
- Target Commit Baseline: `7a479bd19769c2e0ac053b85d5e19c4f38adbd62`
- Node Environment: `node v22.22.1` (satisfies `engines.node: ">=22 <23"`)
- Package Manager: `pnpm@10.30.0` (pinned via root `package.json` `"packageManager"`)

---

## 1. Node Runtime & Engine Resolution Note

- Root `package.json` enforces `engines.node: ">=22 <23"`.
- The current workstation runtime is `node v22.22.1`.
- In `.npmrc`, `engine-strict=true` is enabled.
- `jsdom@30+` requires `node >= 22.22.2` (a minor patch bump ahead of `22.22.1`).
- `jsdom@29.1.1` was pinned with exact versioning because its engine requirement is `^20.19.0 || ^22.13.0 || >=24.0.0`, which strictly and cleanly matches `node v22.22.1` without warnings or engine errors.
- All other 11 dependencies from `new_dependencies` match the latest approved versions.

---

## 2. Implemented Target Files

All target files specified in `KB-P0-03.md` exist and are implemented strictly:
1. Root Workspace:
   - `package.json` (private, `packageManager: pnpm@10.30.0`, `engines.node: ">=22 <23"`)
   - `pnpm-workspace.yaml` (`packages: ["kanban/web"]`)
   - `pnpm-lock.yaml` (cryptographic integrity hashes for all dependencies)
   - `.npmrc` (`engine-strict=true`, `ignore-scripts=true`, `save-exact=true`)
2. `kanban/web/` Configuration & Build:
   - `package.json` (exact scripts: `dev`, `build`, `preview`, `typecheck`, `lint`, `test:unit`; exact versions without `^` or `~`)
   - `tsconfig.json` (`strict: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true`, `noImplicitOverride: true`, `noFallthroughCasesInSwitch: true`, `verbatimModuleSyntax: true`, `jsx: "react-jsx"`, `target: "ES2022"`)
   - `tsconfig.node.json` (strict Node configuration for build and config files)
   - `eslint.config.js` (flat config with `typescript-eslint` `strictTypeChecked` + `stylisticTypeChecked`, `eslint-plugin-react-hooks`, banned runtime CSS-in-JS imports)
   - `vite.config.ts` (`outDir: "dist"`, `assetsDir: "assets"`, `sourcemap: false`, plugins `react()` and `precompress()`)
   - `vitest.config.ts` (`environment: "jsdom"`, provider `v8`, thresholds 95% across lines, functions, branches, statements)
   - `index.html` (zero inline `<script>` or `<style>` blocks)
3. Plugin & App Sources:
   - `build/precompress.ts` (local Vite plugin emitting `.br`, `.gz`, `sri-manifest.json` with pure helpers `shouldCompress` and `sriHash`)
   - `build/precompress.test.ts` (12 comprehensive unit tests covering all required test vectors)
   - `src/main.tsx` (React 19 root bootstrap)
   - `src/App.tsx` (exports `App(): JSX.Element` rendering `<main data-testid="app-root"><h1>Kanban</h1></main>`)
   - `src/App.css` (static CSS module styling root element; no runtime CSS-in-JS)
   - `src/App.test.tsx` (positive render test verifying `app-root` and `Kanban` heading)

---

## 3. Scoped Definition of Done Audit

- [x] Target Files Exist: All files created and verified.
- [x] Unit Tests & Coverage: 13 passed out of 13 tests; 100% Statements, 100% Branch, 100% Functions, 100% Lines.
- [x] Build / Type / Lint Clean: `pnpm install --frozen-lockfile --ignore-scripts`, `typecheck`, `lint`, and `build` all exit `0` with `0` warnings and `0` errors.
- [x] Build Artifacts: Emitted `kanban/web/dist/index.html`, `dist/assets/*.js.br`, `dist/assets/*.js.gz`, `dist/sri-manifest.json`.
- [x] No Inline Scripts / Styles: Literal `<script>` count is 0, `<style` count is 0 in `dist/index.html`.
- [x] Visual Proof: 3 headless Chromium screenshots captured from `preview` server (`desktop-1440x900.png`, `tablet-820x1180.png`, `mobile-390x844.png`) and annotated in `ANNOTATIONS.md`.
- [x] Dependency Evaluations: Evaluated and signed off with APPROVED by `arch-reviewer`, `sec-eng`, and `qa-eng`.
- [x] UI Specialist Gate: Requested from `@ui-specialist` and awaiting verdict.
