# API Specialist Gate Independent Forensic Audit: APPROVED for KANBA-127 (KB-P4-08)

- Ticket: `KANBA-127` (`KB-P4-08`): `[Phase 4 / MCP] /mcp/docs surface: 6 knowledge & sticky tools`
- Auditor: `arch-reviewer` (Systems Architect & API Specialist Gate Auditor)
- Board Sign-Off: Message #842
- Date: 2026-11-13
- Worktree: `/tmp/kb-wt-KANBA-127` on branch `feat/KANBA-127`
- Scope: `mcp/surfaces/docs/` (`__init__.py`, `search_knowledge.py`, `read_doc.py`, `upsert_doc.py`, `manage_stickies.py`, `promote_sticky_to_doc.py`, `link_knowledge.py`), `mcp/markdown_sections.py`, `mcp/app.py`, `mcp/auth.py`, `mcp/errors.py`, `mcp/internal_client.py`, and `pyproject.toml`.

---

### 1. Architectural & Security Verification

1. **Zero Database Import Invariant in MCP:**
   - Forensic import analysis confirms that `mcp/` runtime holds zero PostgreSQL credentials and zero runtime imports from `database/`.
   - All tool invocations interact exclusively with the in-process FastAPI application via internal `KanbanApiClient` (`httpx.ASGITransport`), forwarding `X-KB-Subject-Token` and session context.
   - `lint-imports` validates all module boundaries: 2 contracts kept, 0 broken.

2. **Isolated Surface Scope Enforcement:**
   - `/mcp/docs` tools enforce strict scopes: `search_knowledge` and `read_doc` require `docs:read`; `upsert_doc`, `manage_stickies`, `promote_sticky_to_doc`, and `link_knowledge` require `docs:write`.
   - Callers presenting read-only keys are strictly rejected with `INSUFFICIENT_SCOPE` on mutating calls.
   - Cross-surface key isolation: Presenting `kb_doc_*` keys on `/mcp/agent` immediately fails closed with `403 SURFACE_KEY_MISMATCH`.

3. **Atomic Sticky-to-Doc Promotion & ACL Row Preservation:**
   - Promotion delegates to `POST /api/v1/stickies/{id}/promote-to-doc`, executing within a single PostgreSQL transaction.
   - Verbatim row-by-row ACL preservation: All `object_access_control` rows for the source sticky note are copied identically to the newly minted doc (`docs/qa/KANBA-127/acl-preservation-proof.txt` confirms 100% row-for-row match).
   - Typed object link `PROMOTED_TO_DOC` is registered.
   - Subsequent promotion attempts on the same sticky fail with `ALREADY_PROMOTED`.

4. **Section Patch State Machine (`mcp/markdown_sections.py`):**
   - ATX heading scanner ignores code blocks fenced with ``` and ~~~.
   - Exact case-sensitive match against `section_heading`. Missing heading raises `SECTION_NOT_FOUND`; duplicate identical headings at target scope raise `AMBIGUOUS_IDENTIFIER`.
   - Replacement correctly bounds up to the next heading of identical or higher level, or trailing EOF.

5. **Sanitization & Concurrency Controls:**
   - Optimistic concurrency: `if_match` (64-character SHA-256 hex) is required on updates; stale tokens reject with `CONFLICT_ETAG`.
   - Hidden DOM elements (`style="display:none"`) are safely stripped before persistence.
   - Anti-enumeration: Missing documents and documents in projects where caller lacks VIEW access return byte-identical `NOT_FOUND` error envelopes.

---

### 2. Verification Matrix

| Evaluation Dimension | Target Requirement | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **Tool Registration** | Exactly 6 tools on `/mcp/docs` | `DOCS_TOOL_NAMES`: search_knowledge, read_doc, upsert_doc, manage_stickies, promote_sticky_to_doc, link_knowledge | PASS |
| **Schema Token Budget** | <= 1,350 approximate tokens | Raw JSON: 4,709 bytes (~1,177 tokens, 173 tokens headroom) | PASS |
| **Section Patch Semantics** | Fenced code block exclusion, unambiguous headings | Verified across 7 dedicated test cases in `test_markdown_sections.py` | PASS |
| **Sticky Promotion** | Atomic transaction, ACL row equality, `PROMOTED_TO_DOC` link | Row-for-row match confirmed in `test_docs_tools.py` and `acl-preservation-proof.txt` | PASS |
| **Error Code Mapping** | `SECTION_NOT_FOUND`, `ALREADY_PROMOTED`, `LINK_TYPE_NOT_ALLOWED` | All typed error codes defined in `mcp/errors.py` and mapped in `internal_client.py` | PASS |
| **Anti-Enumeration** | Byte-identical 404 for unreadable / missing | Confirmed in `test_case_2_security_and_permission_isolation` | PASS |
| **CSRF Handling** | Automatic token acquisition on mutating methods | Handled in `KanbanApiClient._ensure_csrf_token` | PASS |
| **Test Coverage** | >= 95% unit test coverage | 22/22 tests passed in 5.35s; **96%** coverage across `mcp.surfaces.docs` and `mcp.markdown_sections` | PASS |
| **Linter / Type / Gate** | Zero warnings, strict mypy, 0 dash defects | `ruff check`, `ruff format --check`, `mypy --strict mcp`, `lint-imports` clean | PASS |

---

### 3. Recommendation
Implementation is fully verified, robust against hostile inputs, and satisfies all architectural invariants. **APPROVED**.
