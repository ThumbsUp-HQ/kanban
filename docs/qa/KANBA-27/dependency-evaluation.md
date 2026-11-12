# Dependency Evaluation: KANBA-27 (@playwright/test)

## Target Dependency Overview

- **Package:** `@playwright/test`
- **Version:** `1.65.0` (exact pin in `kanban/web/package.json`)
- **License:** `Apache-2.0` (Permissive; matches repository core license)
- **Scope:** `devDependencies` in `kanban/web/package.json` (Local & CI testing only; never shipped in production runtime image or bundle)
- **Integrity Hash (pnpm-lock.yaml):** `sha512-iGURLGuKDLakSEl7Pgfv8h7f+XLT+V861Wfhz0zlEl5nyFuKUopdkFBPKqTllTUp06aOwPuH8iuUEb3yp3MpbQ==`

---

## Supply-Chain & Architectural Evaluation

1. **Permissive Licensing Compliance:**
   - `@playwright/test` is licensed under `Apache-2.0`.
   - Zero copyleft risk: no GPL, AGPL, or SSPL transitive dependencies.
   - Pinned with an exact version string (no `^` or `~`) to ensure deterministic reproducible builds.

2. **Attack Surface & Test Sandbox Hardening:**
   - Isolated to development and test execution. Not included in client bundles (`dist/`) or backend Docker containers.
   - Operates out-of-process via Chrome DevTools Protocol (CDP) on headless Chromium.
   - Test harness enforces strict network sandboxing: all requests outside `http://127.0.0.1:4173` are aborted.
   - Fail-closed test guard verifies production Content-Security-Policy, catching any unauthorized network call or console error.
   - Screenshot and probe utilities enforce strict regex sanitization on ticket IDs and screenshot names to prevent path traversal attacks.

3. **Alternatives Considered:**
   - **Cypress (MIT):** Executes in-browser inside an iframe, creating severe constraints for multi-origin testing, CSP enforcement, and native viewport emulation without commercial addons.
   - **WebdriverIO (MIT):** Requires external WebDriver server bridges (e.g. chromedriver), resulting in slower execution times, larger setup boilerplate, and higher flakiness compared to Playwright direct CDP event loops.

---

## Verbatim Specialist Sign-Offs

### 1. Systems / Backend Architect (`arch-reviewer`, Message #30)

```text
[DEP-EVAL KANBA-27] Playwright E2E Test Harness
- Evaluator: Systems/Backend Architect (arch-reviewer)
- Scope: docs/tickets/KB-P3-32.md (KANBA-27 / KB-P3-32)
- Evaluated Package:
  * @playwright/test (Apache-2.0, exact pin in kanban/web devDependencies)

1. License and Compatibility:
@playwright/test is licensed under Apache-2.0. Matches the monorepo core license identically. 100% compliant with zero copyleft risk.

2. Supply-Chain and Attack Surface:
- Confined exclusively to frontend development and CI testing (devDependencies). Never included in production web artifacts or Docker runtime images.
- Pinned with an exact version in kanban/web/package.json with integrity hashes recorded in pnpm-lock.yaml.
- Operates out-of-process via Chrome DevTools Protocol (CDP) on headless Chromium, executing strictly against local preview servers (http://127.0.0.1:4173) with automatic blocking of off-origin requests.

3. Architectural Rationale and Alternatives Considered:
- @playwright/test vs. Cypress:
  * Cypress runs in-browser inside an iframe, imposing severe constraints on multi-origin testing, CSP enforcement, and native viewport resizing.
  * Playwright runs out-of-process, natively simulates multiple viewport tiers (desktop 1440x900, tablet 1024x768, mobile 390x844), supports strict mock API routing (page.route), and verifies CSP headers without compromising browser security settings.
- @playwright/test vs. WebdriverIO:
  * WebdriverIO requires intermediate WebDriver server binaries and suffers from higher latency and flake compared to Playwright direct CDP event loops.
  * Playwright provides seamless DOM annotation, computed-style probing, and screenshot capture required to generate indisputable visual verification artifacts for reality-checker QA gates.

4. Architectural Verdict:
APPROVED. High-performance, Apache-2.0 compliant E2E test harness for deterministic visual and functional verification.
```

### 2. Application & Supply-Chain Security Engineer (`sec-eng`, Message #29)

```text
[DEP-EVAL KANBA-27] Playwright E2E Harness: Viewports, CSP Preview, Mock API and Screenshots
- Evaluator: Application and Supply-Chain Security Engineer (sec-eng)
- Scope: docs/tickets/KB-P3-32.md (KANBA-27 / KB-P3-32)
- Target Packages: @playwright/test (Apache-2.0, exact devDependency)

1. License and Compatibility Audit:
- @playwright/test (Apache-2.0): Permissive browser automation and testing framework.
- License Compliance: 100% Apache-2.0 compliant. Zero copyleft contamination.

2. Supply-Chain and Test Sandbox Hardening:
- DevDependency Isolation: Scoped strictly to devDependencies in kanban/web/package.json for local and CI testing. Never packaged into production distribution artifacts.
- Egress and CSP Guarding: The Playwright test harness auto-fixture actively blocks all requests whose origin is not http://127.0.0.1:4173 and fails the test suite on any CSP violation, console error, or unexpected network call.
- Path Traversal Defense: annotatedScreenshot and styleProbe strictly validate QA_TICKET_ID and screenshot names against regexes (/^[0-9]{2}-[a-z0-9-]+$/), preventing file traversal or injection into arbitrary filesystem locations.
- Deterministic Mock API: mockApi isolates frontend tests from external or real backend networks, ensuring predictable, offline testing without network leakage.

3. Alternatives Evaluated:
- Cypress: Relies on in-browser iframe execution with limitations on multi-window testing, cross-origin security context handling, and strict CSP headers. Playwright uses native browser automation protocols with complete out-of-process isolation.
- WebdriverIO: Requires external driver management (chromedriver) and has slower execution, larger dependencies, and higher flakiness compared to Playwright.

4. Verdict:
- Role Sign-Off: APPROVED by sec-eng (Engineer #1, Application and Supply-Chain Security Engineer) for KANBA-27.
```

### 3. Test & Build Quality Engineer (`qa-eng`, Message #28)

```text
[DEP-EVAL KANBA-27] Playwright E2E Harness: 3 Viewports, CSP Guard, and Visual Proof (KB-P3-32)
- Target Dependencies:
  * @playwright/test (Apache-2.0, exact devDependency in kanban/web/package.json)

- Test and Build Quality Assessment:
  * @playwright/test: Premier end-to-end browser automation framework for modern web applications.
  * Multi-Viewport Matrix: Validates frontend rendering across desktop (1440x900), tablet (1024x768), and mobile (390x844) viewports in headless Chromium.
  * Built-in Security and Quality Assertion Guards: Custom test fixture catches browser console errors, unhandled page errors, and securitypolicyviolation events, immediately failing tests on CSP breaches.
  * Hermetic Test Sandboxing: Intercepts network calls via mockApi.ts, returning canned JSON fixtures and blocking unexpected network traffic with 599 statuses, ensuring test execution stays within the 20-second budget without needing a live backend.
  * Visual Verification Tooling: Provides annotatedScreenshot and probeStyles utilities to generate numbered overlay screenshots and computed style metrics directly into docs/qa/<TICKET_ID>/, supplying indisputable proof for the reality-checker QA gate.

- Alternatives Considered:
  * Cypress: Executes in-browser, has higher execution overhead, lacks multi-tab and native multi-viewport test matrix execution without paid addons, and exhibits higher memory consumption.
  * WebdriverIO: Requires external WebDriver bridges and more boilerplate setup, resulting in slower test feedback loops compared to Playwright direct CDP integration.

- Engineer #2 Sign-off: APPROVED
```
