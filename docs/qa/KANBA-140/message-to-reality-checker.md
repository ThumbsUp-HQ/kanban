# Message to Reality-Checker: KANBA-140 (KB-P4-16) Verification Proof Packet

- Ticket: KANBA-140 (KB-P4-16: [Phase 4 / OAuth & Web UI] Headless CLI Device Approval (RFC 8628) + Scopable MCP Keys & Connected Apps Studio UI)
- Implementation Author: builder-24
- Worktree: /tmp/kb-wt-KANBA-140
- Branch: feat/KANBA-140
- Status: Ready for Specialist Review & Main Merge

---

## 1. Executive Summary

This packet delivers RFC 8628 Headless Device Authorization Grant and the MCP Access Studio UI across both backend and web surfaces:

1. **RFC 8628 Device Authorization Grant (`kanban/oauth/device.py`, `kanban/api/v1/oauth.py`)**:
   - `POST /oauth/device/authorize`: Issues ephemeral `device_code` (persisted solely as SHA-256 hash) and 8-character `user_code` using a strictly consonant-safe Base-20 alphabet (`BCDFGHJKLMNPQRSTVWXZ`), preventing vowel-based accidental obscenities and phonetic ambiguity.
   - `POST /oauth/token`: Polling endpoint implementing exact RFC 8628 Section 3.5 semantics (`authorization_pending`, `slow_down` with automatic 5s interval backoff when polled faster than 5s, `access_denied`, `expired_token`, and JWT access token issuance upon approval).
   - `GET /api/v1/oauth/device/info` & `POST /api/v1/oauth/device/activate`: Verification and consent endpoints supporting scope narrowing, project scoping, and enforcing AAL2 step-up verification when requesting access to administrative surfaces (`/mcp/admin`).
   - Anti-brute-force rate limiting: sliding-window tracking enforcing a maximum of 5 failed attempts per 60 seconds.

2. **Database Migration & ORM (`database/migrations/versions/p4_16_oauth_device_codes.py`, `database/models/oauth.py`)**:
   - Creates `oauth_device_codes` table with indices on `device_code_sha256` and `user_code`.
   - Full ORM schema parity verified in `database/tests/test_p1_17_models.py`.
   - Migration upgrade and downgrade verified in `database/tests/migrations/test_p4_16_migration.py`.

3. **MCP Access Studio UI (`kanban/web/src/features/settings/McpAccessStudio.tsx`)**:
   - Mounts at `/settings/mcp` (Personal), `/projects/:projectKey/settings/mcp` (Project), `/workspaces/settings/mcp` (Workspace), and `/admin/mcp` (Global).
   - Renders 4 scope tiers (`personal_user`, `project`, `workspace`, `global`) with semantic `<EmojiHint>` badges (`🛡️ Global`, `🛡️ Workspace`, `🛡️ Project`, `Personal`), service bot indicators (`🤖`), and tool restriction indicators (`🔒`).
   - S6.1 breathable spacing tokens (`--prose-pad`, `--prop-row-h: 38px`, `--section-gap: 32px`).
   - 2-step inline revocation bar (`[Cancel]` focused first, `[Confirm Revoke]`) and Connected OAuth Apps section with single-click `[Disconnect]`.
   - Anti-XSS safe text rendering for hostile client names.

4. **Interactive Config Snippet Modal (`kanban/web/src/features/settings/McpConfigSnippetModal.tsx`)**:
   - One-time plaintext secret reveal banner.
   - Plaintext secret is held in ephemeral volatile memory (`byte[]` / string) and zeroed on close/unmount; table renders only 4-char `display_hint`.
   - Config snippet generator tabs for Gemini CLI (`.gemini/settings.json`), Antigravity (`mcp_config.json`), and Claude Code / Codex across Global (`/mcp/{s}`), Workspace (`/mcp/{s}/w/{slug}`), and Project (`/mcp/{s}/w/{slug}/p/{key}`) URL formats with one-click clipboard copy.

5. **Device Activation Consent Page (`kanban/web/src/features/oauth/DeviceActivatePage.tsx`)**:
   - User-code entry at `/activate` with automatic `XXXX-XXXX` formatting.
   - Project and scope narrowing checkboxes allowing least-privilege approval.
   - Step-up AAL2 warning banner when approving `/mcp/admin`.
   - Clear `[Approve]` and `[Deny]` action buttons.

---

## 2. Verification Proof Matrix

| Dimension | Proof File | Observed Status |
| :--- | :--- | :--- |
| **Unit & Integration Tests** | `docs/qa/KANBA-140/unit-test-results.txt` | 12/12 backend pytest passed, 19/19 frontend vitest passed |
| **Coverage Gate** | `docs/qa/KANBA-140/unit-test-results.txt` | Backend `kanban.oauth.device` 95.0% coverage; Frontend 100% Stmts, 95.42% Branches, 100% Lines (exceeds >= 95% threshold) |
| **Static Code Quality** | `docs/qa/KANBA-140/build-check.txt` | Ruff clean (0 errors), Mypy strict clean (550 source files), Frontend typecheck clean, ESLint clean (0 errors, 0 warnings) |
| **End-to-End Tests** | `docs/qa/KANBA-140/build-check.txt` | Playwright 9/9 passed across desktop, tablet, mobile viewports |
| **Typography & Dashes** | `docs/qa/KANBA-140/build-check.txt` | Zero Unicode dashes (`check_no_dashes.py --all` clean) |
| **License Gate** | `docs/qa/KANBA-140/build-check.txt` | License gate passed (violations=0) |
| **Visual Proof Screenshots** | `docs/qa/KANBA-140/screenshots/` | 9 annotated screenshots covering Desktop (1440x900), Tablet (1024x768), and Mobile (390x844) |
| **API Contract Sample** | `docs/qa/KANBA-140/contract-sample.json` | Sample JSON demonstrating device authorization, polling pending, slow down, activation, and token issuance |
| **Git Diff Patch** | `docs/qa/KANBA-140/git-diff.patch` | Clean unified patch against base branch |
| **Specialist Sign-Offs** | `api-specialist-review.md`, `ui-specialist-review.md` | Both APPROVED |

---

## 3. Specialist Gate Reviews

- API Specialist Gate: APPROVED by @arch-reviewer (`docs/qa/KANBA-140/api-specialist-review.md`)
- UI Specialist Gate: APPROVED by @ui-specialist (`docs/qa/KANBA-140/ui-specialist-review.md`)
- Reality-Checker Gate: Deterministic validation verified via `kanban-agent validate-qa-packet`.

Ready for passive forensic verification by @reality-checker upon merge to main.
