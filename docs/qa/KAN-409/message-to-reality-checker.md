# KAN-409 Verification Guide & Message to Reality-Checker

## 1. Executive Summary & Scope

- **Ticket:** `KAN-409` (`[SLICE-1-P4][KB-AUTH-DOCS] Phase 4: Publish Verified Multi-Card Auth, AD/LDAP, OIDC & RBAC Wiki + In-App Docs Guides`)
- **Parent Epic:** `KAN-405` (`[EPIC][SLICE-1-AUTH-RBAC]`)
- **Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/9e0717fe-81d4-4260-b1a8-c35c5f951afb/swarm-b-kan409-6ed6f24d`
- **Branch:** `docs/KAN-409-slice1-auth-docs`
- **Worktree Commit:** `2f7b45c6` (HEAD of `docs/KAN-409-slice1-auth-docs`)
- **Wiki Commit:** `8195469` (HEAD of `docs/KAN-409-slice1-auth-docs` in `./thumbs-up-kanban.wiki` and `/home/adamoutler/kanban/thumbs-up-kanban.wiki`)
- **Deliverable Manifest:** `docs/workouts/slice-1-auth-rbac/04-published-docs-manifest.md`

---

## 2. Published Wiki Chapters & Visual Assets

1. **`Multi-Card-Authentication-Studio.md`:**
   - Documented First-Boot Setup Wizard, single-use bootstrap tokens (`kb_setup_*`), pre-session CSRF protection (`__Host-kb_csrf`), zero implicit email auto-merge invariant, drag-and-drop sort rank reordering, envelope encryption (`MASTER_KEK` / AES-256-GCM DEK).
   - Documented Active Directory & LDAPS / StartTLS configuration, CA certificate pinning, service account binds, recursive `memberOf` group search filters, and draft handshake testing (`POST /api/v1/admin/auth-cards/test-handshake`). SPKI certificate pinning (`spki_sha256_pins`) documented strictly as an administrative API parameter.
   - Documented OpenID Connect / Google Workspace SSO, discovery endpoint resolution, verified email claim enforcement (`email_verified: true` -> 403 `EMAIL_NOT_VERIFIED`), allowed email domains, and Google OAuth JSON quick importer. Scopes documented as `list[str]` in API and comma-separated in drawer UI.
   - Documented WebAuthn Passkeys (`rp.name = "👍kanban"`, strict ASCII FQDN `rp.id`), TOTP authenticator app enrollment, 10 single-use recovery codes (`RECOVERY_CODE_COUNT = 10`), Argon2id password security, AAL2 step-up verification, WebSudo replay, and anti-lockout protection (`LOCKOUT_PREVENTED`, 15-minute interactive `SERVER_ADMIN` login requirement vs test handshakes).
   - Embedded verified screenshots: `slice1-desktop-1440x900-dark.png`, `slice1-desktop-1024x768.png`, `slice1-tablet-portrait-768x1024.png`, `slice1-mobile-portrait-390x844.png`, `slice1-desktop-1440x900-light.png`, `slice1-ldap-test-draft-success.png`, `slice1-oidc-verified-claim-linked.png`, `slice1-passkey-webauthn-registered.png`, `slice1-websudo-replay-active.png`.
2. **`Role-and-Permission-Matrix.md`:**
   - Documented 7 canonical principal tiers: Guest, Viewer, Member, Project Admin, Workspace Admin, Server Admin, and Scoped MCP Agent.
   - Documented Workspace-Level roles, additive role inheritance, and Granular RBAC Policy Builder.
   - Documented narrative policy header sentence configuration, tri-state checkboxes (Inherit / Allow / Deny), and step-by-step custom role authoring.
   - Documented the 30-permission granular engine across Workspace (8), Issue (10), and Field (12) tiers.
   - Documented the 8-bit `Capability(IntFlag)` bitmask (`NONE=0..ALL=255`) and absolute DENY precedence (`effective = allow & (~deny)`).
   - Embedded verified screenshot: `slice1-custom-rbac-policy-builder.png`.
3. **`Studio-Configuration-Reference.md` (Section 5 ONLY):**
   - Parallel-safe update strictly confined to Section 5 (Multi-Card Authentication Studio).
   - 44 settings documented across 5 structured tables + setting-by-setting technical paragraphs detailing allowed values, formats, defaults, and backend security contracts.
4. **Offline Wiki Bundle & Visual Assets:**
   - Bundled 11 verified screenshots into `thumbs-up-kanban.wiki/images/slice1-*.png` and `kanban/web/public/docs-images/`.
   - Synchronized 34 chapters into `wikiManifest.ts` (608,321 bytes, 106 images).

---

## 3. Formatting & In-App Anchor Invariants

- **Zero Unicode Dashes:** Plain ASCII hyphens (`-`) only (`python3 scripts/check_no_dashes.py --all` exits 0, check on target wiki files exits 0).
- **Zero Backticks in Bold Wrappers:** Confirmed 0 nested backticks inside `**...**` bold tokens across all wiki chapters.
- **Zero Sub-Bullets in Numbered Lists:** All step-by-step operator guides flattened to 1..N numbered lists, completely eliminating `DocMarkdownViewer` flattening artifacts.
- **100% In-App Anchor Resolution:** Real `##` and `###` Markdown headings slugify via `slugifyAnchor()` to every `docHref` `#anchor` across `AuthStudioPage.tsx`, `AuthCardEditorDrawer.tsx`, `RbacPolicyBuilder.tsx`, `PersonalSettingsPage.tsx`, `WorkspaceSettingsPage.tsx`, and `errorHelpCatalog.ts`. Asserted via automated unit test in `DocsCenter.test.tsx` (71 passed, 96.15% branch coverage).
- **Zero Mermaid `<br/>` HTML Tags:** Flowchart node labels use ` - ` separators and quoted labels.
- **Playwright Docs Screenshots:** 16 PNGs captured across 5 standard viewports (Desktop 1440x900 light/dark, Tablet 1024x768 landscape, Tablet 768x1024 portrait, Mobile 390x844 portrait, and Mermaid SVG diagram) using static preview server on loopback port 18409 serving compiled production build (`pnpm build`). Port 18409 cleanly shut down. Every PNG visually inspected via `read_file`.

---

## 4. Test & Build Verification Summary

- **Pytest:** 7 passed in 0.14s (`test_wiki_bundle_sync.py`, 0 orphan images, 0 collisions).
- **Vitest:** 71 passed in 8.06s (`DocsCenter.test.tsx`, `DocsCenterImages.test.tsx`, 96.15% branch coverage across all components).
- **Typecheck:** Clean (0 TypeScript errors).
- **ESLint:** Clean (0 warnings).
- **Vite Build:** Clean production bundle compiled in 1.39s.

---

## 5. Dual Specialist Approvals

- **UI Specialist:** Signed and APPROVED by `@ui-spec` in `docs/qa/KAN-409/ui-specialist-review.md` (commit `292949e1`).
- **API Specialist:** Signed and APPROVED by `@api-spec` in `docs/qa/KAN-409/api-specialist-review.md` (commit `2f7b45c6`).
