# Verification Audit Narrative: KANBA-117 (KB-P3-52)

- **Ticket**: `KANBA-117` (`KB-P3-52`: Standalone status panel: volume persistence, encrypted backup trigger & docker-compose.yml export)
- **Author**: `builder-20`
- **Worktree**: `/tmp/kb-wt-KANBA-117`
- **Base Commit**: `d7aca24` (`main`)
- **Branch**: `feat/KANBA-117`
- **Specialist Reviews**:
  - API Specialist Gate: `docs/qa/KANBA-117/api-specialist-review.md` (APPROVED)
  - UI Specialist Gate: `docs/qa/KANBA-117/ui-specialist-review.md` (APPROVED)

---

### 1. Implementation Summary & Invariants

1. **Backend Status & Redaction (`kanban/api/v1/system_status.py`, `kanban/standalone/export_service.py`)**:
   - `GET /api/v1/system/status` returns deployment mode, persistence indicators, and sandbox status.
   - For `SERVER_ADMIN` callers: returns full host details (`data_mount_point`, `data_mount_fstype`, `local_llm_endpoint_host`).
   - For non-admin callers: redacts `data_mount_point`, `data_mount_fstype`, and `local_llm_endpoint_host` to `null` to eliminate infrastructure enumeration.
2. **Encrypted Backup Trigger (`POST /api/v1/admin/standalone/backup`)**:
   - Requires `SERVER_ADMIN` and active `AAL2` session (`assert_admin_routes_protected` verified).
   - Rejects non-standalone deployment modes with RFC 7807 409 `NOT_STANDALONE_MODE`.
   - Validates passphrase length (min 16 characters).
   - Executes zero-shell `/usr/bin/pg_dump` via `asyncio.create_subprocess_exec`.
   - Encrypts dump into authenticated `.kbkp` envelope (AES-256-GCM, PBKDF2-HMAC-SHA256 with 600,000 iterations or HKDF with MASTER_KEK).
   - Records `STANDALONE_BACKUP_EXPORTED` in system activity ledger.
   - Streams `.kbkp` attachment with timestamped filename.
3. **Secret-Free Compose Export (`GET /api/v1/admin/standalone/compose-export`)**:
   - Requires `SERVER_ADMIN`.
   - Generates production `docker-compose.yml` with isolated internal networks: `edge_net`, `app_net`, `data_net` (internal), `sandbox_net` (internal), `egress_llm_net`.
   - Enforces invariant: `mcp-server` and `sandbox` do NOT attach to `data_net`.
   - Zero hardcoded secrets; provides variable substitution and `.env` template.
   - Monospace 4-step promotion checklist for PostgreSQL 16 migration.
4. **Frontend Accessible Panel (`kanban/web/src/features/standalone/`)**:
   - Registered as `'standalone'` in `AppShell.tsx` via `registerShellPanel`.
   - Opened by clicking `⚠️` HeaderPill.
   - Full keyboard focus trap inside dialog; `Escape` key closes dialog and returns focus to `⚠️` HeaderPill.
   - Ephemeral storage warning banner (amber, WCAG contrast > 7:1) with 1-click copy command.
   - Calm green persistent storage badge.
   - Server-admin encrypted backup form with 16-char validation and immediate `blob:` URL revocation.
   - Non-admin callers see calm guidance notice with zero backup/compose controls or host paths.
   - Strict CSP compliance: zero inline JSX `style={{...}}`.

---

### 2. Forensic Proof Bundle Checklist

| Artifact | Description | Status |
| :--- | :--- | :--- |
| `docs/qa/KANBA-117/unit-test-results.txt` | Vitest (16/16 passed, >=95% coverage) + Pytest (9/9 passed, 98% coverage) | PASS |
| `docs/qa/KANBA-117/build-check.txt` | Typecheck, ESLint, Vite build, Ruff check, Mypy strict (all 0 errors) | PASS |
| `docs/qa/KANBA-117/e2e-results.txt` | Playwright test output across desktop, tablet, mobile (9/9 passed) | PASS |
| `docs/qa/KANBA-117/contract-sample.json` | Sample JSON responses for admin, member, and compose-export | PASS |
| `docs/qa/KANBA-117/computed-styles-*.json` | Style probes for desktop, tablet, mobile (24px padding, 24px gap, 24x24 pill) | PASS |
| `docs/qa/KANBA-117/screenshots/` | 9 annotated viewport screenshots across desktop, tablet, mobile | PASS |
| `docs/qa/KANBA-117/api-specialist-review.md` | API Specialist Gate approval by `@arch-reviewer` | PASS |
| `docs/qa/KANBA-117/ui-specialist-review.md` | UI Specialist Gate approval by `@ui-specialist` | PASS |
| `docs/qa/KANBA-117/git-diff.patch` | Clean git diff against main commit `d7aca24` | PASS |

---

### 3. Coverage Summary

- **Frontend (`src/features/standalone/`)**:
  - Statements: 98.68% (threshold: >= 95%)
  - Branches: 95.00% (threshold: >= 95%)
  - Functions: 95.45% (threshold: >= 95%)
  - Lines: 100.00% (threshold: >= 95%)
- **Backend (`kanban/api/v1/system_status.py`, `kanban/standalone/`)**:
  - `kanban/api/v1/system_status.py`: 100% line & branch coverage
  - `kanban/standalone/__init__.py`: 100% line & branch coverage
  - `kanban/standalone/export_service.py`: 98% line & branch coverage
  - Total backend coverage: 98.47% (threshold: >= 95%)
