# Forensic Verification Packet: KANBA-160 (KB-P6-03)

## Ticket Overview
- **Ticket ID:** `KANBA-160` (`docs/tickets/KB-P6-03.md`)
- **Title:** `[Phase 6 / Hardening] Cross-layer STRIDE security regression suite (S3.5 threat matrix) & docs/SECURITY.md`
- **Module Scope:** `tests/security/`, `docs/SECURITY.md`, `.github/workflows/ci.yml`, `database/`
- **Quality / Security Classification:** Priority #0 Security Hardening & Forensic Verification Suite

---

## Deliverables Summary

1. **STRIDE Threat Matrix Test Suites (`tests/security/`):**
   - `test_stride_prompt_injection.py` (Spec S3.5 Row 1):
     - Ingestion pruner: Hidden-DOM paste-jacking (`display:none`, `opacity:0`, HTML comments, zero-width spaces, and Unicode tags `U+E0000..U+E007F`) pruned with 0 hidden canary bytes in database across all 5 prose models (`issues`, `comments`, `docs`, `pages`, `stickies`).
     - MCP Read-Taint High-Water Mark: Cross-project exfiltration blocked across all 5 write operations (`add_comment`, `update_ticket`, `create_ticket`, `transition_ticket`, `link_objects`) with `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED` and immutable `MCP_TAINT_BLOCKED` activity ledger events.
     - Outbound Secret Scrubber: Redacts `sk-...`, `ghp_...`, `AKIA...`, PEM keys, and session tokens before dispatch to AI provider runners.
   - `test_stride_hostile_media.py` (Spec S3.5 Row 2):
     - Hostile SVG sanitization and billion-laughs DAG bomb protection (depth <= 5, expanded nodes <= 500).
     - Download sandboxing headers (`Content-Security-Policy: default-src 'none'; sandbox`, `X-Content-Type-Options: nosniff`, `Content-Disposition: attachment`).
     - Media proxy SSRF prevention: Blocks loopback (`127.0.0.1`, `::1`), RFC1918 (`10.0.0.1`, `172.16.0.1`, `192.168.1.1`), cloud metadata (`169.254.169.254`), IPv6 ULA (`fd00::1`), DNS-rebinding socket pinning, and air-gap mode.
     - Pixel decompression bomb rejection (> 40,000,000 pixels).
   - `test_stride_cli_pipe_injection.py` (Spec S3.5 Row 3):
     - Shell metacharacters inert in zero-shell `execve` `argv`.
     - Delimiter escape and forged nonce verdict rejection (`VERDICT_NONCE_MISMATCH`).
     - Banned CLI flags (`--yolo`, `--dangerously-skip-permissions`, `--full-auto`, `--allow-all-tools`) blocked at save and runtime.
     - Codex sandbox override protection (`-s read-only` mandatory).
     - Nsjail `:ro` mount with 0000 tmpfs overlays on secret files (`.env`, `tls.key`, `.git/config`, `id_rsa.pem`).
   - `test_stride_standalone_misconfig.py` (Spec S3.5 Row 4):
     - Dockerfile zero hardcoded secrets.
     - Standalone keyring `0600` mode fail-closed (`KeyringError` on `0644`).
     - Fresh database has 0 default users; single-use `kb_setup_*` token stored only as HMAC-SHA256 with 60-minute expiry.
     - Unix domain socket-only PostgreSQL (`listen_addresses = ''`, zero host lines in `pg_hba.conf`).
     - Uvicorn `setpriv` privilege drop (`--reuid=65532 --inh-caps=-all --no-new-privs`).
     - Tier B `nsjail` fail-closed with `SANDBOX_UNAVAILABLE_IN_STANDALONE` when user namespaces are absent.
   - `test_stride_rls_and_invariants.py` (Cross-Cutting Invariants):
     - Catalog check: 100% of public tenant tables and partitions have `ENABLE` and `FORCE ROW LEVEL SECURITY`.
     - Role check: Role `kanban_app` has `rolbypassrls = false` and `rolsuper = false`.
     - Zero-context fail-closed: `SELECT count(*)` as `kanban_app` with unset session context returns 0 rows across all tenant tables.
     - Presentation state hygiene: 0 columns ending in `_html` or `_ast` exist in database.
     - Architectural boundaries: `mcp` has 0 direct imports from `database` (`lint-imports`).
     - Anti-enumeration discipline: Unreadable vs nonexistent UUIDs across `/api/v1/issues`, `/docs`, `/pages`, `/stickies`, `/views` return byte-identical RFC 7807 404 responses.

2. **Security Architecture Documentation (`docs/SECURITY.md`):**
   - Documents the complete STRIDE threat model (Rows 1-4).
   - Details 5 network trust boundaries: `edge_net`, `app_net`, `data_net`, `sandbox_net`, `egress_llm_net`.
   - Explains RLS and On-Behalf-Of (OBO) capability equations.
   - Explains MCP read-taint high-water mark invariant.
   - Outlines local audit commands and vulnerability disclosure policy.
   - Strictly conforms to plain ASCII hyphens (0 `U+2014` or `U+2013` dash characters).

3. **CI/CD Security Gate (`.github/workflows/ci.yml`):**
   - Added dedicated `stride-security-gate` job running `uv run pytest tests/security -q`.
   - Included in `docker-push` dependency requirements (`needs: [..., stride-security-gate]`).

---

## Forensic Evidence Artifacts

1. `docs/qa/KANBA-160/unit-test-results.txt`
   - Complete output of `uv run pytest tests/security -v`: 21 passed in 3.11s.
2. `docs/qa/KANBA-160/build-check.txt`
   - Clean verification logs for ruff check, ruff format, mypy --strict, lint-imports, no-dashes check, and YAML syntax validation.
3. `docs/qa/KANBA-160/rls-catalog-audit.txt`
   - Raw PostgreSQL catalog query output verifying 100% of tenant tables enforce `relrowsecurity = t` and `relforcerowsecurity = t`, and `kanban_app` has `rolbypassrls = f`.
4. `docs/qa/KANBA-160/git-diff.patch`
   - Git patch of all modifications for KANBA-160.
5. Screenshots:
   - N/A (Non-UI security hardening ticket).

---

## Verification Commands for Auditor

```bash
# 1. Run all STRIDE security regression tests
uv run pytest tests/security -v

# 2. Run static analysis and linting
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict database kanban mcp agent
uv run lint-imports

# 3. Verify zero forbidden unicode dashes
python3 scripts/check_no_dashes.py --all
```
