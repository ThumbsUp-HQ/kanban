# Dependency Evaluation: KANBA-111 (KB-P3-37)

## Ticket Overview
- **Ticket ID**: KANBA-111 (`KB-P3-37`: `[Phase 3 / Frontend] Kanban Board view with Pragmatic DnD, column virtualization, <12ms optimistic move & Soft/Hard WIP visuals`)
- **Status**: Pre-Flight Approved and Validated
- **Module**: `kanban/web`

---

## 1. Evaluated Dependencies

### `@atlaskit/pragmatic-drag-and-drop`
- **Ecosystem**: Node / npm
- **Package**: `@atlaskit/pragmatic-drag-and-drop`
- **Exact Version**: `4.0.0`
- **License**: Apache-2.0 (100% project-compatible, permissive)
- **Role**: Headless HTML5 drag-and-drop primitives (`draggable`, `dropTargetForElements`, `monitorForElements`) powering board card moves between 324px lanes with sub-12ms optimistic update budget.
- **Lockfile Integrity (SHA-512)**: `sha512-pyDo2B5NiaExoKGmgeXKGNUL4aR4UzzSZm8QWWjYTEyBLVqSqKyKUwtVxMw2YEkakagOGFONUdHM32LAH2nPug==`
- **Direct Dependencies**:
  * `raf-schd@^4.0.3` (MIT)
  * `@babel/runtime@^7.0.0` (MIT)
  * `bind-event-listener@^3.0.0` (MIT / Apache-2.0)
- **Install Scripts**: Zero `preinstall` or `postinstall` lifecycle hooks.
- **Pre-Flight Swarm Approvals**:
  * Systems/Backend Architect (`arch-reviewer`): Board #620 (APPROVED)
  * UI/UX Specialist (`ui-specialist`): Board #619 (APPROVED)
  * Security Engineer (`sec-eng`): Board #659 (APPROVED)

### `@tanstack/react-virtual`
- **Ecosystem**: Node / npm
- **Package**: `@tanstack/react-virtual`
- **Exact Version**: `3.14.26`
- **License**: MIT (100% project-compatible, permissive)
- **Role**: Vertical column virtualization (`useVirtualizer`) ensuring 500-card lanes mount <= 25 DOM elements at 900px viewport height.
- **Lockfile Integrity (SHA-512)**: `sha512-HUDlfsrYH6ko5xH56L62Mcl/uzT+AGVNMHFuDNqDJMdZWc1AQa2oeVKNUvZ/RWBZQ4TYtyQerFrNvLnp39h65A==`
- **Direct Dependencies**:
  * `@tanstack/virtual-core@3.19.11` (MIT)
- **Install Scripts**: Zero `preinstall` or `postinstall` lifecycle hooks.
- **Publisher Attestation**: Trusted GitHub Actions OIDC publisher.
- **Pre-Flight Swarm Approvals**:
  * Systems/Backend Architect (`arch-reviewer`): Board #620 (APPROVED)
  * UI/UX Specialist (`ui-specialist`): Board #619 (APPROVED)
  * Security Engineer (`sec-eng`): Board #659 (APPROVED)

---

## 2. Supply-Chain and License Compliance Audit

- **Permissive License Mandate**:
  * `@atlaskit/pragmatic-drag-and-drop@4.0.0` is licensed under `Apache-2.0`.
  * `@tanstack/react-virtual@3.14.26` is licensed under `MIT`.
  * All transitive dependencies (`raf-schd`, `@babel/runtime`, `bind-event-listener`, `@tanstack/virtual-core`) are published under permissive MIT or Apache-2.0 licenses.
  * Zero copyleft licenses (`GPL`, `AGPL`, `LGPL`, `SSPL`) exist in the transitive dependency tree.
- **Supply-Chain Verification**:
  * Exact version pinning in `kanban/web/package.json`.
  * Cryptographic SHA-512 integrity hashes enforced by `pnpm-lock.yaml`.
  * Zero post-install or pre-install build execution hooks in tarballs.
- **Strict Content-Security-Policy (CSP) Invariant**:
  * Application enforces `script-src 'self'` and `style-src 'self'`.
  * Neither package injects inline `<script>` tags, inline `<style>` blocks, or dynamically eval-ed strings.
  * Virtual item translation offsets and container dimensions are applied exclusively via direct CSSOM refs (`el.style.transform`, `el.style.height`) within `useLayoutEffect`, never JSX inline `style={{...}}` strings.

---

## 3. Architectural Rationale and Alternatives Considered

1. **`@atlaskit/pragmatic-drag-and-drop`**:
   - **Selected**: Headless, lightweight event listeners attached directly to DOM refs. Decouples drag gesture tracking from React render cycles, enabling synchronous Base-62 fractional rank calculation and immediate 1-row cache updates within the sub-12ms budget.
   - **Alternative: `@dnd-kit/core` (MIT)**: Rejected due to heavier synthetic coordinate sensor loops, continuous layout polling, and deep React context wrappers that introduce latency into the optimistic mutation path.
   - **Alternative: `react-beautiful-dnd` (Apache-2.0)**: Rejected. Officially deprecated by Atlassian in favor of Pragmatic DnD; lacks React 19 concurrent mode compatibility and list virtualization support.
   - **Alternative: Hand-Rolled HTML5 Drag-and-Drop**: Rejected due to fragile cross-browser preview handling, edge cases in Safari/Firefox, and high ongoing maintenance burden.

2. **`@tanstack/react-virtual`**:
   - **Selected**: Production-proven vertical virtualization with dynamic measurement (`measureElement`). Restricts DOM node count to <= 25 cards per lane in large boards (500+ items), preventing mobile scroll jank and layout recalculation pauses.
   - **Alternative: `react-window` (MIT)**: Rejected. Unmaintained, lacks robust dynamic item height measurement (`measureElement`), and requires external polyfills for concurrent React 19.
   - **Alternative: Full Unvirtualized DOM Rendering**: Rejected. Mounting 500 cards across multiple lanes generates thousands of DOM nodes, exceeding browser layout budgets and causing severe dropped frames during active drag gestures.

---

## 4. Specialist Sign-Offs

- **Security Engineer (`sec-eng`)**: APPROVED (Board #659)
- **Systems/Backend Architect (`arch-reviewer`)**: APPROVED (Board #620)
- **UI/UX Specialist (`ui-specialist`)**: APPROVED (Board #619)
