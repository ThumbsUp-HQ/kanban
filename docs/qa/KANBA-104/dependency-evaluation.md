# Dependency Evaluation: KANBA-104 (KB-P3-34)

## Ticket Overview
- **Ticket ID**: KANBA-104 (`KB-P3-34`: `[Phase 3 / Frontend] Breathable app shell: sidebar, topbar, breadcrumb, header emoji pills, router & Cmd+K palette`)
- **Status**: Pre-Flight Approved and Validated
- **Module**: `kanban/web`

---

## 1. Evaluated Dependencies

### `react-router`
- **Ecosystem**: Node / npm
- **Package**: `react-router`
- **Exact Version**: `7.18.5`
- **License**: MIT (100% Apache-2.0 compatible, permissive, zero copyleft)
- **Role**: Client-side data routing (`createBrowserRouter`, `createMemoryRouter`, `RouterProvider`), relative path matching, layout search param synchronization (`?layout=`), active navigation state (`NavLink`, `useLocation`), and route placeholder mounting for subsequent Phase 3 feature tickets.
- **Lockfile Integrity (SHA-512)**: `sha512-dTgvcXDOrLPrlLHrcZAqWveiK1hMSqN+rGAJzegP8HtmNkfRxOoshGWBNX3ZJ0cZjOHkRdlUJtaIhZMLLyGyPw==`
- **Package SHA-256 Digest**: `520a73d59a03e461c465b9171184d6850691819cde13aa766be1efb12c7b2b48` (`package.json`)
- **Transitive Dependencies**:
  * `cookie@1.1.1` (MIT)
  * `set-cookie-parser@2.7.3` (MIT)
- **Pre-Flight Swarm Approvals**:
  * Systems/Backend Architect (`arch-reviewer`): Board #558 (APPROVED)
  * UI/UX Architecture Specialist (`ui-specialist`): Board #561 (APPROVED)
  * Security Engineer (`sec-eng`): Board #563 (APPROVED)
  * Test & Build Quality Engineer (`qa-eng`): Board #555, #566 (APPROVED)

---

## 2. Supply-Chain and License Compliance

- **Permissive License Mandate**: `react-router` and all transitive dependencies are published under the MIT license, with zero copyleft (GPL, AGPL, SSPL, LGPL) clauses.
- **Supply-Chain Verification**:
  * Exact version pinning in `kanban/web/package.json` (`"react-router": "7.18.5"`).
  * Cryptographic SHA-512 and SHA-256 integrity hashes enforced by `pnpm-lock.yaml` (lockfile SHA-256: `3a452dd060d52e556c7aa4dc9cbf59b3343f2b4eda77bdcb374af082d273406e`).
  * Zero install lifecycle scripts (`preinstall`, `install`, `postinstall`) across direct and transitive packages, eliminating supply-chain execution vectors at `pnpm install` time.
  * `make license` (`uv run python -m scripts.license_gate`) validates clean permissive status (`SUMMARY python=112 node=1 violations=0`).
- **Zero Runtime Script/Style Injection**: Does not inject inline `<style>` or `<script>` tags, ensuring 100% adherence to Section 5.4 Content-Security-Policy (`script-src 'self'`, `style-src 'self'`).
- **Zero Telemetry / Zero Phone-Home**: Clean client library with no outbound analytics, tracking beacons, or telemetry.

---

## 3. Architectural Rationale & Alternatives Considered

1. **`react-router` (Selected)**:
   * **Selected**: Industry-standard data router offering declarative routing, nested `<Outlet />` layouts for preserving persistent shell chrome across view transitions, seamless search parameter synchronization (`?layout=`), accessible navigation primitives (`NavLink`), and robust memory router (`createMemoryRouter`) for deterministic unit testing in Vitest / jsdom.
   * **Alternative: `@tanstack/react-router` (MIT)**: Strong static typing but requires file-system route generation tooling, Vite plugins, and divergent routing conventions from the Plane-parity router spec in KB-P3-34.
   * **Alternative: Hand-rolled `history` / `popstate` Router**: Lacks nested layout outlets, parameter extraction regexes, transition lifecycles, and standard memory router test fixtures. High maintenance burden and defect risk.
   * **Alternative: `wouter` (ISC)**: Minimal footprint but lacks robust nested route layouts and out-of-the-box memory routing for Vitest.

---

## 4. Specialist Sign-Offs

- **Systems/Backend Architect (arch-reviewer)**: APPROVED (Board #558)
- **UI/UX Architecture Specialist (ui-specialist)**: APPROVED (Board #561)
- **Security Engineer (sec-eng)**: APPROVED (Board #563)
- **Test & Build Quality Engineer (qa-eng)**: APPROVED (Board #555, #566)
