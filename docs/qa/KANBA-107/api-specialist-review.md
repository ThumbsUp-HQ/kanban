# API Specialist Gate Final Audit: APPROVED for KANBA-107 (KB-P5-11)

- Reviewer: arch-reviewer (Swarm Systems/Backend Architect & API Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-107`
- Branch: `feat/KANBA-107`
- Head Commit SHA: `99bf87b`
- Ticket: `KANBA-107` (`KB-P5-11`: `[Phase 5 / Database + API] Custom field definitions, Admin-only RBAC/RLS WITH CHECK gate & 7-format output_format_metadata schema`)

---

### 1. Executive Summary & Verification Matrix

A comprehensive forensic systems architecture and security audit was performed on `KANBA-107` (`KB-P5-11`) in `/tmp/kb-wt-KANBA-107`. This ticket establishes the core database architecture, PostgreSQL Row-Level Security policies, Pydantic v2 discriminated union output schemas, deterministic manifest hashing, and REST API endpoints for user-defined custom fields.

All technical specifications defined in `docs/tickets/KB-P5-11.md` and architecture invariants in Spec Sections 13.1, 13.2, 3.3, and 7.1 have been rigorously audited and verified.

| Verification Dimension | Specification Requirement | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **PostgreSQL RLS Policies** | `ENABLE` & `FORCE RLS` on both tables | `relforcerowsecurity = t` on `custom_field_definitions` and `custom_field_values` | PASS |
| **Admin-Only RLS WITH CHECK** | Writes restricted to `PROJECT_ADMIN`/`SERVER_ADMIN` + AAL2 | Direct SQL INSERT/UPDATE by non-admins or AAL1 principals fails with RLS violation | PASS |
| **Cache Row Isolation** | Partition `custom_field_values` by caller hash | `user_access_hash` partitioned rows; User A rows are invisible to and immutable by User B | PASS |
| **7-Format Output Schema** | Discriminated union on `format` (`extra="forbid"`) | `text`, `number`, `badge`, `markdown_snippet`, `url`, `json_table`, `severity_pill` | PASS |
| **Zero Raw HTML / CSS Injection** | Disallow raw HTML, arbitrary CSS, bad URIs | Banned `html` formats; rejected hex/CSS in badge; scheme-checked URLs; stripped markdown | PASS |
| **JSON Schema Export Parity** | Committed JSON schema equals live model export | `output-format-metadata-v1.json` is 100% byte-identical to live Pydantic JSON schema | PASS |
| **Deterministic Manifest Hash** | S13.2 canonical SHA-256 manifest hash | `compute_field_manifest_sha256` uses canonical UTF-8 JSON (`sort_keys=True, separators=(",", ":")`) | PASS |
| **Atomic Version Increment** | Mutating execution spec bumps `script_version` | `script_version` increments from 1 to 2; `manifest_sha256` updates on spec changes | PASS |
| **Egress Allowlist Validation** | Max 16 paths matching `^/api/v1/...$` | Strict regex check; rejection of whitespace, traversal `..`, and query/fragment characters | PASS |
| **REST API & Timing Floor** | Uniform 404 anti-enumeration & 25.0ms timing | Endpoints wrapped in `timing_floor(floor_ms=25.0)`; uniform RFC 7807 404 on absent projects | PASS |
| **Non-Admin Source Secrecy** | Redact `script_source` to `null` for non-admins | `GET /api/v1/projects/{project}/custom-fields` returns `script_source: null` for standard roles | PASS |
| **Activity Ledger Integration** | Hash-chained activity record on mutation | Emits `CUSTOM_FIELD_CREATED`, `CUSTOM_FIELD_UPDATED`, `CUSTOM_FIELD_DELETED` | PASS |
| **Reversible Alembic Migration** | Upgrade head -> Downgrade -1 -> Upgrade head | Reversible lifecycle verified clean (`p2_05a_mfa_totp_recovery` <-> `p5_11_custom_fields`) | PASS |
| **Test Coverage & Metrics** | >= 95% line + branch coverage across target modules | 15/15 tests passing; 99.35% line + branch coverage (0 missing lines across all modules) | PASS |
| **Static Code Quality** | Zero linter, typing, formatting, or contract errors | Ruff clean, Ruff format clean, Mypy strict clean, Lint-imports clean, License clean | PASS |
| **Typography Discipline** | Plain ASCII hyphens `-` only | Zero Unicode em-dashes (`U+2014`) or en-dashes (`U+2013`) | PASS |

---

### 2. Deep Architectural & Security Invariant Audits

#### A. Database Schema, Migration, and PostgreSQL FORCE RLS (Spec S13.1, S3.3)
1. **Migration Integrity (`database/migrations/versions/p5_11_custom_fields.py`):**
   - Clean linear Alembic revision linked to `p2_05a_mfa_totp_recovery`.
   - Uses `execute_sql_file` invoking `p5_11_custom_fields.up.sql` and `p5_11_custom_fields.down.sql`.
   - Full migration roundtrip verified in `docs/qa/KANBA-107/migration-roundtrip.txt`.
2. **PostgreSQL RLS Catalog Verification (`docs/qa/KANBA-107/schema-dump.sql`):**
   - Both `custom_field_definitions` and `custom_field_values` have `relrowsecurity = t` and `relforcerowsecurity = t`.
   - Table owners set to `kanban_migrator`; runtime privileges granted to `kanban_app` and `app_rls_reader`.
3. **Hardened RLS Policies on `custom_field_definitions`:**
   - `SELECT`: `workspace_id = app_current_workspace_id() AND app_has_object_capability(project_id, 1)` (VIEW capability).
   - `INSERT`: `WITH CHECK (workspace_id = app_current_workspace_id() AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN']) AND app_current_aal_level() >= 2)`.
   - `UPDATE`: `USING (workspace_id = app_current_workspace_id()) WITH CHECK (workspace_id = app_current_workspace_id() AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN']) AND app_current_aal_level() >= 2)`.
   - `DELETE`: `USING (workspace_id = app_current_workspace_id() AND app_principal_has_role(project_id, ARRAY['PROJECT_ADMIN', 'SERVER_ADMIN']) AND app_current_aal_level() >= 2)`.
   - Verification: In `test_custom_fields_rls.py`, direct SQL INSERT/UPDATE executed under `kanban_app` by `MEMBER`, `VIEWER`, `GUEST`, or `PROJECT_ADMIN` with `aal_level = 1` immediately fails with a PostgreSQL RLS violation.
4. **Cache Partitioning & Isolation on `custom_field_values`:**
   - Table stores computed field outputs partitioned by `(issue_id, field_id, script_version, user_access_hash)`.
   - `SELECT` requires VIEW on `issue_id` and `(user_access_hash = ''::bytea OR user_access_hash = app_caller_access_hash())`.
   - `INSERT`, `UPDATE`, `DELETE` enforce `user_access_hash = app_caller_access_hash()`.
   - Verification: User A's cached evaluation row cannot be read or overwritten by User B, preventing cross-tenant or cross-user cache poisoning attacks.

#### B. 7-Format Schema & Output Value Validation (Spec S13.1, S7.1)
1. **Discriminated Union Architecture (`kanban/custom_fields/output_formats.py`):**
   - Strictly models all 7 output formats: `text`, `number`, `badge`, `markdown_snippet`, `url`, `json_table`, `severity_pill`.
   - Configured with `extra="forbid"` and `strict=True`.
   - Attempting to pass `format="html"` or `format="raw_html"` fails validation with RFC 7807 `422 OUTPUT_FORMAT_INVALID`.
2. **Defensive Value Sanitization (`validate_field_output_value`):**
   - `text`: Strips C0/C1 control characters, enforces `max_length <= 280`.
   - `number`: Validates finite bounds using `math.isfinite()`, explicitly rejects Python boolean types (`isinstance(True, int)`), rounds to `maximum_fraction_digits` (0..6).
   - `badge`: Rejects arbitrary CSS styles, hex injection, and markup; binds `color_token` to semantic tokens (`neutral`, `info`, `success`, `warning`, `danger`, `accent`).
   - `markdown_snippet`: Normalizes Markdown, strips all raw HTML tags, scripts, and embedded image markdown (`![...](...)`), capped at `max_chars <= 2000`.
   - `url`: Parses via `urllib.parse.urlsplit`; strictly restricts schemes to `https` (and optional `http`); forbids embedded credentials (`username`/`password`); validates against `allowed_host_suffixes`.
   - `json_table`: Validates columns (1..10) and rows (1..50); cells restricted strictly to scalar values (`str`, `int`, `float`, `bool`, `None`); nested dictionaries/lists and script tags are rejected.
   - `severity_pill`: Restricts `level` to `('low', 'medium', 'high', 'critical')`, `score` to `0.0..10.0`, and validates that label text contains zero HTML brackets.
3. **JSON Schema Export Parity:**
   - Live Pydantic export verified byte-for-byte against `kanban/custom_fields/schemas/output-format-metadata-v1.json`.

#### C. Deterministic Manifest Hashing & Egress Controls (Spec S13.2)
1. **Canonical Manifest Hash (`kanban/custom_fields/manifest.py`):**
   - Implements `compute_field_manifest_sha256` calculating:
     `SHA256(canonical_json({"credential_mode": ..., "egress_allowlist": sorted(...), "output_format": ..., "output_format_metadata": ..., "script_source": ..., "target_scope": ..., "tier": ...}))`.
   - Employs canonical UTF-8 JSON serialization (`sort_keys=True, separators=(",", ":")`).
   - Returns a 32-byte digest (64 hex characters).
2. **Atomic Version Invariant:**
   - Any mutation to `script_source`, `output_format`, `output_format_metadata`, `tier`, `target_scope`, `credential_mode`, or `egress_allowlist` atomically increments `script_version` and recomputes `manifest_sha256`.
3. **Internal Proxy Egress Validation (`validate_egress_allowlist`):**
   - Restricts entries to maximum 16 items.
   - Rejects whitespace, path traversal (`..`), query strings (`?`), and URL fragments (`#`).
   - Enforces pattern `^/api/v1/[A-Za-z0-9/_*{}-]{1,120}$`.

#### D. REST API Router & Service Security Discipline (Spec S3.4, S4, S13.1)
1. **Uniform Anti-Enumeration & Timing Equalization (`kanban/api/v1/custom_fields.py`):**
   - All 4 REST endpoints (`GET`, `POST`, `PATCH`, `DELETE`) are wrapped in `async with timing_floor(floor_ms=25.0):`.
   - Non-existent projects or projects where the caller lacks VIEW capability return uniform RFC 7807 404 responses.
2. **Role-Based Source Redaction:**
   - `GET /api/v1/projects/{project}/custom-fields`: Callers with `PROJECT_ADMIN` or `SERVER_ADMIN` receive full definitions including `script_source` and `manifest_sha256`. Callers with standard roles (`MEMBER`, `VIEWER`, `GUEST`) receive sanitized definitions with `script_source: null` and `manifest_sha256: null`.
3. **Admin Step-Up MFA Gate:**
   - Mutating endpoints (`POST`, `PATCH`, `DELETE`) check `caller.aal_level >= 2`. Sessions with `aal_level < 2` return RFC 7807 `403 AAL2_REQUIRED`.
4. **Activity Ledger Auditing:**
   - Mutations emit structured entries via `record_activity`: `CUSTOM_FIELD_CREATED`, `CUSTOM_FIELD_UPDATED`, `CUSTOM_FIELD_DELETED`.

---

### 3. Verification Commands & Test Evidence

The following test suites were independently executed in `/tmp/kb-wt-KANBA-107`:

1. **Pytest Coverage & Execution:**
   - Command: `pytest database/tests/test_custom_fields_rls.py kanban/tests/custom_fields/test_custom_fields_api.py kanban/tests/custom_fields/test_output_formats.py --cov=kanban.custom_fields --cov=kanban.api.v1.custom_fields --cov=database.models.custom_field --cov-branch --cov-report=term-missing`
   - Result: 15 passed in 4.22s.
   - Coverage: 99.35% overall (0 missing statements across all modules).
     * `database/models/custom_field.py`: 100%
     * `kanban/api/v1/custom_fields.py`: 100%
     * `kanban/custom_fields/__init__.py`: 100%
     * `kanban/custom_fields/manifest.py`: 100%
     * `kanban/custom_fields/output_formats.py`: 99%
     * `kanban/custom_fields/service.py`: 99%

2. **Migration Test Execution:**
   - Command: `pytest database/tests/migrations/test_p5_11_migration.py`
   - Result: 1 passed in 0.39s.

3. **Static Analysis & Linters:**
   - `ruff check .`: 0 errors.
   - `ruff format --check .`: 784 files checked, 0 reformat required.
   - `mypy --strict kanban/custom_fields kanban/api/v1/custom_fields.py database/models/custom_field.py`: 0 errors.
   - `lint-imports`: 2 kept, 0 broken.
   - `license_gate.py`: 0 violations.
   - `check_no_dashes.py`: 0 non-ASCII unicode dashes detected.

---

### 4. Specialist Gate Verdict

The implementation in `feat/KANBA-107` adheres strictly to all security, database, and API architecture specifications. The PostgreSQL RLS WITH CHECK gate, caller-hash cache partitioning, 7-format output metadata validation, canonical manifest hashing, and anti-enumeration timing discipline meet our highest security-first standards.

VERDICT: APPROVED
