# Reality-Checker Verification Packet: KANBA-107 (KB-P5-11)

- **Ticket:** `KANBA-107` (`KB-P5-11`: `[Phase 5 / Database + API] Custom field definitions, Admin-only RBAC/RLS WITH CHECK gate & 7-format output_format_metadata schema`)
- **Branch:** `feat/KANBA-107`
- **Linear Alembic Chain:** `p2_05a_mfa_totp_recovery` -> `p5_11_custom_fields`
- **Module Coverage:** 99.35% line + branch (exceeds 95% threshold)
- **Static Analysis:** All clean (Ruff, Ruff format, Mypy strict, Lint-imports, License gate, Check-no-dashes)

---

### 1. Verification Matrix & Scoped DoD Criteria

| Requirement / Criterion | Status | Evidence File / Command |
| :--- | :--- | :--- |
| **DDL & Migration:** `custom_field_definitions` & `custom_field_values` with ENABLE & FORCE RLS | PASS | `docs/qa/KANBA-107/schema-dump.sql`<br>`database/migrations/versions/p5_11_custom_fields.py` |
| **Alembic Reversible Lifecycle:** Upgrade head -> Downgrade -1 -> Upgrade head | PASS | `docs/qa/KANBA-107/migration-roundtrip.txt` |
| **RLS WITH CHECK Gate:** Admin-only mutation, AAL2 session gate, caller hash partition | PASS | `database/tests/test_custom_fields_rls.py`<br>`docs/qa/KANBA-107/unit-test-results.txt` |
| **7-Format Metadata Schema & Output Validation:** text, number, badge, markdown_snippet, url, json_table, severity_pill | PASS | `kanban/custom_fields/output_formats.py`<br>`kanban/tests/custom_fields/test_output_formats.py` |
| **Schema Parity:** Committed JSON schema equals live Pydantic JSON Schema export | PASS | `kanban/custom_fields/schemas/output-format-metadata-v1.json` |
| **Manifest Computation & Egress Validation:** S13.2 canonical SHA-256 manifest hash | PASS | `kanban/custom_fields/manifest.py` |
| **REST Router & CRUD Lifecycle:** GET, POST, PATCH, DELETE with timing floor 25.0ms | PASS | `kanban/api/v1/custom_fields.py`<br>`kanban/custom_fields/service.py`<br>`kanban/tests/custom_fields/test_custom_fields_api.py` |
| **Activity Ledger:** CUSTOM_FIELD_CREATED, CUSTOM_FIELD_UPDATED, CUSTOM_FIELD_DELETED | PASS | `kanban/services/activity.py` |
| **Wire Sample Capture:** RFC 7807 problem details & wire exchanges | PASS | `docs/qa/KANBA-107/contract-sample.json` |
| **Specialist Gates:** API & UI reviews | PENDING | `docs/qa/KANBA-107/api-specialist-review.md`<br>`docs/qa/KANBA-107/ui-specialist-review.md` |

---

### 2. Security Invariants Preserved
1. **Admin-Only RBAC/RLS Gate:** Direct SQL INSERT/UPDATE on `custom_field_definitions` requires `PROJECT_ADMIN` or `SERVER_ADMIN` AND `app_current_aal_level() >= 2`. Attempted writes by `MEMBER`, `VIEWER`, `GUEST`, or `AAL1` principals fail with a PostgreSQL RLS violation.
2. **Cache Row Isolation:** `custom_field_values` rows partitioned by `user_access_hash` ensure User A's cache row cannot be read or poisoned by User B.
3. **Zero HTML/CSS Injection:** Strict validators reject `html`/`raw_html` formats, arbitrary CSS in badge labels/colors, dangerous URL schemes (`javascript:`, `data:`), non-finite floats in numbers/tables, and strip scripts/images in markdown snippets.
4. **Manifest Tamper-Resistance:** Any modification to `script_source`, `output_format`, `output_format_metadata`, `tier`, `target_scope`, `credential_mode`, or `egress_allowlist` atomically increments `script_version` and recomputes `manifest_sha256`.
5. **Anti-Enumeration & Source Secrecy:** Non-admin callers receive field definitions with `script_source` redacted to `null`; non-existent or inaccessible projects return 404 with uniform 25.0ms timing floor.

---

### 3. Test & Verification Artifacts
- `unit-test-results.txt`: 14/14 tests passing with 99.35% branch+line coverage across target modules.
- `build-check.txt`: Ruff clean, Ruff format clean, Mypy strict clean (340 files), Lint-imports clean (2 kept, 0 broken), License gate clean (0 violations), Check-no-dashes clean (0 non-ASCII dashes).
- `schema-dump.sql`: Complete DDL, `relforcerowsecurity = t`, and full RLS policies.
- `migration-roundtrip.txt`: Clean Alembic migration roundtrip verification.
- `contract-sample.json`: Wire exchanges for 201 created, 200 list/patch, 204 delete, 403 AAL2 required, 422 invalid format.
- `git-diff.patch`: Full unified diff against `main`.
