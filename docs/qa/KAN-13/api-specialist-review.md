# API Specialist Security & Architecture Audit Review: KAN-13

## Audit Metadata
- Ticket ID: KAN-13 ([KB-P3-AUDIT-07])
- Reviewer: api-spec-2 (Clean-Room Backend/API Specialist)
- Date: 2026-11-19
- Target Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan13-rcfix-11eb4f77`
- Target Branch: fix/KAN-13-rc2
- Base Commit: 036216b
- Head Commit: 3fccf21
- STATUS: APPROVED

---

## Executive Summary
This clean-room audit evaluates the API contracts, Content Security Policy (CSP) enforcement boundaries, vector SVG sanitization, and modules endpoint consumption for ticket KAN-13 and its Clean-Room Reality-Checker Round 2 surgical remediation ([KB-P3-AUDIT-07]). The implementation eliminates Chromium CSP `style-src 'self'` policy violations during Mermaid SVG rendering, prevents 404 `MODULES_DISABLED` console errors on issue detail surfaces, and removes inline CSS styles across client components.

All changes adhere strictly to the authoritative specifications in `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` and `kanban/GEMINI.md`.

---

## Detailed Contract & Security Verification

### 1. Chromium CSP `style-src 'self'` Enforcement & Vector SVG Conversion
- Files: `kanban/web/src/editor/mermaid/mermaid.worker.ts`, `kanban/web/src/editor/media/safeSvg.ts`, `kanban/web/src/features/drawer/IssueSurface.tsx`
- Security Invariant: The application operates under a strict Content Security Policy (`style-src 'self'`). Inline `<style>` elements or `style="..."` attributes generated dynamically by third-party libraries (e.g. Mermaid) violate CSP and trigger browser console security errors.
- Audit Findings:
  - In `mermaid.worker.ts` (`inlineThemeColors`): Converted presentation style properties (`font-family`, `font-size`, `font-weight`, `fill`, `stroke`, `stroke-width`, `stroke-dasharray`, `opacity`, `text-anchor`, `dominant-baseline`, `letter-spacing`) into pure SVG XML presentation attributes.
  - Stripped all `<style>...</style>` tags and inline `style="..."` attributes in the worker output before returning the serialized SVG string to the main thread.
  - In `safeSvg.ts`: Pre-stripped `<style>` elements and `style` attributes on the isolated `rawDoc` (`image/svg+xml`) before serializing and passing to `DOMPurify.sanitize()`, preventing Chromium from evaluating inline styles against the document CSP header at template parse time.
  - In `IssueSurface.tsx`: Replaced inline `style={{ display: 'none' }}` on hidden file inputs with `.surface__hidden-file-input` in `IssueSurface.css`.

### 2. Modules API Contract & 404 Elimination on Issue Surfaces
- Files: `kanban/web/src/features/drawer/IssueSurface.tsx`, `kanban/web/src/features/drawer-rail/PropertiesRail.tsx`
- Contract Invariant: Projects where modules are disabled (`modules_enabled: false`) return RFC 7807 404 `MODULES_DISABLED` when querying `GET /api/v1/projects/:key/modules`. Client components must not issue unneeded requests or leak 404 console errors.
- Audit Findings:
  - In `IssueSurface.tsx`: Removed hardcoded `modules_enabled: true` in `projectMetadata` (leaving property undefined so it derives from fetched project metadata).
  - In `PropertiesRail.tsx`: Guarded `fetchProjectMetadata(projectKey)` when `resolvedMeta?.modules_enabled === undefined`, and strictly gated `fetchProjectModules(projectKey)` behind `resolvedMeta?.modules_enabled === true`. Projects with modules disabled no longer query the modules endpoint, preventing unhandled 404 network errors.

---

## Clean-Room Reality-Checker Remediation Audit (KB-P3-AUDIT-07 Round 2)

- Target Branch: `fix/KAN-13-rc2`
- Remediation Head Commit: `3fccf21`
- Remediations Verified:
  1. Converted Mermaid presentation styles into SVG XML presentation attributes and purged inline styles in `mermaid.worker.ts`.
  2. Isolated SVG sanitization in `safeSvg.ts` to prevent Chromium CSP `style-src` evaluation violations.
  3. Replaced inline styles on hidden file inputs in `IssueSurface.tsx` with canonical CSS classes.
  4. Gated modules endpoint requests behind `resolvedMeta?.modules_enabled === true` in `PropertiesRail.tsx`.
  5. 134 Vitest unit tests passing across touched suites with 99.81% statements and 95.12% branch coverage.
  6. Static analysis: `tsc -b --noEmit` (0 errors), `eslint . --max-warnings 0` (0 warnings/errors), `vite build` (clean in 2.05s), `cssTokensAudit.test.ts` (4/4 passed).
  7. Strict punctuation: 0 em-dashes and 0 en-dashes across all code, tests, and documentation.
  8. Clean evidence packet: `git-diff.patch` generated against `31aca8e` with zero `docs/qa/` files included.

---

## Gate & Invariant Checklist

1. [x] Zero New Dependencies: No additions to `pyproject.toml` or `package.json`.
2. [x] Admin Route Security: Mandatory `Depends(require_admin_aal2)` maintained across all `/api/v1/admin/*` endpoints.
3. [x] Architectural Layering: `uv run lint-imports` verified 2 kept contracts, 0 broken (`agent -> mcp -> kanban -> database`).
4. [x] Test Coverage: Touched frontend modules achieved 99.81% statement and 95.12% branch coverage (134 vitest tests passing).
5. [x] Static Analysis: `tsc -b --noEmit`, `eslint`, and `vite build` pass with 0 errors and 0 warnings.
6. [x] Zero Em/En-Dashes: Clean verification across code, tests, docs, and review markdown (0 em/en-dashes).
7. [x] Evidence Packet Complete: `git-diff.patch`, `changed-files-manifest.txt`, `unit-test-results.txt`, `build-or-typecheck.txt`, and screenshots verified in `docs/qa/KAN-13/`.

---

## Verdict & Handoff
STATUS: APPROVED

The CSP enforcement, SVG sanitization, and modules API contract alignments are verified clean. Ready for final coordinator merge into `main`.
