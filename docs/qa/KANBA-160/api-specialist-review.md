# Backend & Security Specialist Review: KANBA-160

**Ticket ID:** `KANBA-160`  
**Ticket Name:** `[Phase 6 / Hardening] Cross-layer STRIDE security regression suite (S3.5 threat matrix) & docs/SECURITY.md`  
**Reviewer:** API & Security Specialist (`api-specialist`)  
**Persona Invariant Rubric:** `.agents/agents/backend-architect.md` and `.agents/agents/api-tester.md`  
**Target Git Branch / Commit:** `main` (synchronized)  
**Date of Audit:** 2026-11-15  

---

## 1. Executive Summary & Review Scope

Ticket `KANBA-160` (KB-P6-03) delivers the definitive Priority #0 cross-layer STRIDE automated security regression suite and formal security architecture documentation for the 👍kanban platform (Product Spec S3.5, S3.3, S5.2, S5.4, S14.3, S2.2).

The audited deliverables encompass:
1. **STRIDE Threat Matrix Test Suites (`tests/security/`):**
   - `test_stride_prompt_injection.py`: Spec S3.5 Row 1 (Indirect prompt injection, ingestion pruner, MCP read-taint high-water mark, outbound secret scrubber).
   - `test_stride_hostile_media.py`: Spec S3.5 Row 2 (Hostile SVG sanitization, billion-laughs DAG bomb protection, media proxy SSRF/DNS-rebinding prevention, decompression pixel bomb guards).
   - `test_stride_cli_pipe_injection.py`: Spec S3.5 Row 3 (Zero-shell `execve` `argv` isolation, dynamic delimiter framing, banned CLI flags, nsjail read-only mounts and secret whiteouts).
   - `test_stride_standalone_misconfig.py`: Spec S3.5 Row 4 (Dockerfile zero-hardcoded secrets, keyring 0600 mode, single-use `kb_setup_*` token, Unix domain socket-only PG, Uvicorn `setpriv` privilege drop, nsjail standalone fail-closed).
   - `test_stride_rls_and_invariants.py`: Priority #0 cross-cutting invariants (100% tenant table `FORCE RLS` catalog audit, zero-context fail-closed, pure Markdown UTF-8 schema, zero database imports in `mcp`, byte-identical 404 anti-enumeration).
2. **Security Architecture Documentation (`docs/SECURITY.md`):**
   - Complete STRIDE threat matrix, 5 network trust boundaries (`edge_net`, `app_net`, `data_net`, `sandbox_net`, `egress_llm_net`), RLS/OBO capability equations, and vulnerability disclosure policies.
   - Strict typography: Verified 0 forbidden unicode dashes (`check_no_dashes.py --all` clean).
3. **CI/CD Security Gate (`.github/workflows/ci.yml`):**
   - Dedicated `stride-security-gate` job running `uv run pytest tests/security -v` wired as a blocking prerequisite for release builds.

---

## 2. Security Invariants & Defensive Architecture Audit

### 2.1 Spec S3.5 Row 1 - Prompt Injection & Cross-Project Taint Exfiltration
- **Ingestion Pruner:** Tested across all 5 prose entities (`issues`, `issue_comments`, `docs`, `pages`, `stickies`). Payloads concealing canary instructions within `<div style="display:none">`, `<span style="opacity:0">`, `font-size:0`, `color:transparent`, HTML comments `<!-- ... -->`, zero-width spaces (`U+200B..U+200F`), and Unicode tags (`U+E0000..U+E007F`) are completely pruned, resulting in exactly 0 hidden instruction bytes in PostgreSQL.
- **MCP Read-Taint High-Water Mark:** Verified that reading from restricted scope `SEC` taints both the session and credential. Subsequent write attempts to public scope `PUB` across all 5 write operations (`add_comment`, `update_ticket`, `create_ticket`, `transition_ticket`, `link_objects`) are rejected with `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`, creating 0 rows in `PUB` and logging `MCP_TAINT_BLOCKED` in the immutable activity ledger.
- **Outbound Secret Scrubber:** Verified redaction of all major secret token families (`sk-...`, `ghp_...`, `AKIA...`, PEM private keys, session cookies) before outbound transmission to AI providers or CLI runner standard input.

### 2.2 Spec S3.5 Row 2 - Hostile Media, SVG, SSRF & Decompression Bombs
- **Hostile SVG Sanitization:** Scripts, `foreignObject`, `@import`, SMIL animation events, `onload`, and `javascript:` URIs are sanitized. XML entity expansion bombs exceeding depth 5 or 500 expanded nodes are rejected (422).
- **Download Headers & Sandboxing:** Direct SVG retrieval enforces `Content-Security-Policy: default-src 'none'; sandbox`, `X-Content-Type-Options: nosniff`, and `Content-Disposition: attachment` when `Sec-Fetch-Dest != "image"`.
- **Media Proxy SSRF Defenses:** Blocks AWS/GCP cloud metadata (`169.254.169.254`), loopback (`127.0.0.1`, `::1`), RFC1918 private subnets, IPv6 ULA (`fd00::1`), DNS-rebinding attacks via socket pinning, 302 redirects, HTML MIME responses, invalid HMAC signatures, and payloads `> 10 MiB`.
- **Decompression Pixel Bombs:** Images exceeding 40,000,000 pixels (e.g. 8000x6000) are rejected with 422 before image decoding in memory.

### 2.3 Spec S3.5 Row 3 - CLI Pipe & Sandbox Injection
- **Zero-Shell Execution:** Shell metacharacters (`$(curl ...)`, backticks, semicolons) in ticket titles or descriptions remain completely inert. Execution utilizes direct `execve` with allowlisted binary paths, never `/bin/sh` or `sh -c`.
- **True Random Delimiters:** Standard input is wrapped with cryptographically random delimiters. Forged verdicts lacking the matching execution `verdict_nonce` fail with `VERDICT_NONCE_MISMATCH`.
- **Banned CLI Flags:** CLI flag injection (`--yolo`, `--dangerously-skip-permissions`, `--dangerously-bypass-approvals-and-sandbox`, `--full-auto`, `--allow-all-tools`) is blocked at both REST schema validation and execution time.
- **Nsjail Sandboxing:** Repository worktrees are mounted with `MS_RDONLY | MS_NOEXEC | MS_NOSUID | MS_NODEV`, with `0000` tmpfs whiteout masks obscuring sensitive files (`.env`, `.env.production`, `id_rsa.pem`, `tls.key`, `.git/config`, `.git/hooks`).

### 2.4 Spec S3.5 Row 4 - Standalone Container & Process Hardening
- **Image Hygiene:** Zero hardcoded secrets or environment passwords in `Dockerfile`.
- **Keyring Permissions:** Keyring storage requires `0600` permissions; world/group-readable files (`0644`), symlinks, or corrupted JSON fail closed with `KeyringError`.
- **Zero Default Credentials:** Fresh databases contain 0 pre-provisioned user accounts (no default `admin/admin`). Setup claim tokens (`kb_setup_*`) are stored only as HMAC-SHA256, single-use, and expire after 60 minutes.
- **PostgreSQL Socket Isolation:** Standalone database configuration sets `listen_addresses = ''` and contains 0 `host` lines in `pg_hba.conf`, binding exclusively to a local Unix domain socket.
- **Capability Drop:** Uvicorn drops all Linux capabilities via `setpriv --reuid=65532 --inh-caps=-all --no-new-privs`.
- **Sandbox Fail-Closed:** Standalone deployments without unprivileged user namespaces fail closed with `SANDBOX_UNAVAILABLE_IN_STANDALONE`.

### 2.5 Cross-Cutting Schema & Anti-Enumeration Invariants
- **PostgreSQL Catalog Audit:** [rls-catalog-audit.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-160/rls-catalog-audit.txt) verifies that 100% of public tenant tables and partitions enforce `relrowsecurity = t` and `relforcerowsecurity = t`. Role `kanban_app` has `rolbypassrls = false` and `rolsuper = false`.
- **Unset-Context Zero-Row Guarantee:** Executing `SELECT count(*)` as `kanban_app` with unset session context returns exactly 0 rows across every tenant table.
- **Pure Markdown UTF-8 Storage:** Verified that 0 columns ending in `_html` or `_ast` exist in the database.
- **Architectural Boundary:** `lint-imports` confirms that `mcp` has zero imports from `database`.
- **Anti-Enumeration Uniformity:** Unreadable versus nonexistent UUIDs across `/api/v1/issues`, `/docs`, `/pages`, `/stickies`, and `/views` return byte-identical RFC 7807 404 responses.

---

## 3. Test Execution & Coverage Audit

The automated STRIDE security regression suite was executed:
- **Total Tests Passed:** 21 / 21 tests in 2.83s.
- **Static Analysis & Linters:**
  - `ruff check .`: 0 errors.
  - `ruff format --check .`: Clean across 1,434 files.
  - `mypy --strict database kanban mcp agent`: Clean across 834 source files.
  - `lint-imports`: 2 kept, 0 broken.
  - `python3 scripts/check_no_dashes.py --all`: 0 forbidden dashes found.
  - YAML workflow syntax: Valid.

---

## 4. Verification Evidence Inventory

The forensic verification bundle in `docs/qa/KANBA-160/` has been verified:
- [git-diff.patch](file:///home/adamoutler/kanban/docs/qa/KANBA-160/git-diff.patch) (86 KB unified diff)
- [unit-test-results.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-160/unit-test-results.txt) (21 passed in 3.11s)
- [build-check.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-160/build-check.txt) (clean ruff, format, mypy, lint-imports, no-dashes check)
- [rls-catalog-audit.txt](file:///home/adamoutler/kanban/docs/qa/KANBA-160/rls-catalog-audit.txt) (raw PostgreSQL catalog RLS audit)
- [message-to-reality-checker.md](file:///home/adamoutler/kanban/docs/qa/KANBA-160/message-to-reality-checker.md) (handoff summary)
- [SECURITY.md](file:///home/adamoutler/kanban/docs/SECURITY.md) (comprehensive STRIDE threat model and boundary documentation)

---

## 5. Specialist Sign-Off

The cross-layer STRIDE security regression suite, database RLS catalog gate, and security architecture documentation for `KANBA-160` satisfy all Priority #0 security invariants. The platform's defenses hold under adversarial conditions.

**STATUS: APPROVED**
