# API Specialist Gate Review: KANBA-119 (KB-P6-01) - Lossless Plane Importer

- Ticket: KANBA-119 (KB-P6-01)
- Spec: Lossless Plane importer (kanban-ctl import plane & admin preview API) with KANBA-* key continuity
- Status: APPROVED
- Reviewer: arch-reviewer (Swarm Architectural & API Specialist Gate)

---

## 1. Architectural & Security Verification

1. **Exact Sequence Continuity & Key Integrity (Spec S1.3, S15.5)**:
   - Evaluated `kanban.importer.plane_importer.PlaneImporter`. Ingests issues in exact sequence order (`sequence_id`), preserving any gaps without renumbering or compaction.
   - Project sequence counter (`projects.issue_seq_counter`) is atomically updated via `UPDATE projects SET issue_seq_counter = GREATEST(issue_seq_counter, :max_seq) WHERE id = :pid` within the import transaction.

2. **Idempotency Ledger & RLS Isolation (Spec S1.3, S15.5)**:
   - Migration `p6_01_import_entity_mappings` provisions `import_entity_mappings` with compound primary key `(workspace_id, source_system, source_kind, source_id)`.
   - Table enforces `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` (`relforcerowsecurity = t`).
   - Re-running the import on an identical bundle results in zero duplicate object creations (`to_create = 0`), zero duplicate link creations, and full fidelity updates (`unchanged = 32`).

3. **SSRF Defense Matrix (Spec S15.5)**:
   - `validate_target_url` enforces:
     * Rejection of plaintext `http://` for non-loopback addresses (`PlaneSecurityError`).
     * Hostname resolution and rejection of RFC 1918 private, link-local, multicast, and loopback IP spaces when targeting remote instances.
     * Hard 25 MiB cap (`MAX_PAGE_BYTES`) per payload and per attachment.
     * Rejection of HTTP 3xx redirects (`follow_redirects = False`) to prevent redirect-based SSRF bypasses.

4. **Sanitization & Anti-Hostile Defense (Spec S5.2, S15.1)**:
   - Plaintext and HTML body contents are normalized to canonical Markdown via `normalize_to_markdown()`.
   - Script tags, event handlers, and active payloads are stripped.
   - SVGs are sanitized via `sanitize_svg()`, removing `foreignObject`, inline JavaScript, and external image references.
   - Raster images are re-encoded via `sanitize_and_reencode_raster()`, stripping malicious EXIF metadata.

5. **Topological Parent DAG Sorting & Cycle Defense (Spec S7.2 8h)**:
   - `PlaneMapper.sort_issues_topologically` orders issues root-first.
   - Detects cycles and hierarchy exceeding depth > 6, failing fast before database mutation with `ImportIntegrityError`.

6. **Admin REST API & AAL2 Wall**:
   - `POST /api/v1/admin/imports/plane` is mounted under `/admin` with `Depends(require_admin_aal2)` and `require_server_admin`.
   - Strict path traversal defenses (`SAFE_BUNDLE_NAME_RE` and realpath confinement) prevent directory escape.
   - Supports atomic dry-run previews with full rollback.

---

## 2. Test Coverage & Quality Verification
- Target test suite: 33/33 tests passing in 5.91s across importer engine, CLI, REST API, and migration lifecycle.
- Line and branch coverage: 95.79% across target modules (`kanban.importer`, `kanban.cli.import_plane`, `kanban.api.v1.admin.imports`).
- Static analysis: Zero errors across Ruff, Ruff format, Mypy strict (8 source files), and Import Linter (2 kept, 0 broken).
- Typography: Zero Unicode dashes (`check_no_dashes.py` 0 violations).

## 3. Verdict
APPROVED. The implementation satisfies all API and architectural invariants for Phase 6 cutover.
