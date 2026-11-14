# UI Specialist Gate Review: KANBA-148 (KB-P5-26)

- **Ticket**: `KANBA-148` (`KB-P5-26`: `[Phase 5 / Agent + API + CLI] Sticky -> Doc AI structuring preview, ACL-preserving confirm contract & kanban-agent validate-sticky-promo`)
- **Reviewer**: UI Specialist (`ux-architect` persona)
- **Status**: APPROVED

---

## 1. Ergonomics & Contract Consumption

The UI specialist audit evaluates the contract shapes, preview latency, and state transition mechanics from the perspective of the frontend and autonomous agent consumers:

1. **Two-Stage Preview and Confirm Workflow**:
   - `POST /api/v1/stickies/{id}/promote-preview` provides a zero-write preview modal experience:
     - The frontend scratchpad displays the generated document outline (`proposed_title`, `summary_markdown`, section breakdown) before any database write occurs.
     - Users and agents can inspect the rendered Markdown preview, action item checklist, and ACL inheritance forecast side-by-side with the original sticky note.
   - `POST /api/v1/stickies/{id}/promote-to-doc` accepts the approved `structured_body_markdown` and `expected_sticky_sha256`.
     - The TOCTOU guard provides immediate, non-destructive feedback (HTTP 409 `STICKY_MODIFIED_SINCE_PREVIEW`) if another user or background process edited the sticky while the preview was being reviewed.
     - When confirmed, the sticky smoothly morphs into a promoted stub (`is_promoted_stub: true`) with direct link to the newly created Doc.

2. **Visual Hierarchy & Diagram Preservation**:
   - Technical stickies containing Mermaid sequence diagrams and architecture sketches are preserved verbatim.
   - The preview response guarantees that Mermaid syntax blocks are intact, allowing instant client-side rendering via the standard SVG/Mermaid pipeline.
   - Any model truncation is caught by `FENCED_BLOCK_MODIFIED` warnings, preventing silent data loss in user documentation.

3. **Whitespace & Typography Standards**:
   - Strict ASCII hyphens (`-`) used exclusively across all schemas, headings, and report outputs (zero em/en dashes).
   - Clean Markdown formatting with standard H2/H3 section hierarchy and task list checkboxes (`- [ ]`).

---

## 2. CLI Tooling & Developer Experience

The `kanban-agent validate-sticky-promo` command provides an ergonomic local workbench:
- Standard 4-section report (`RENDERED CONTEXT`, `TOOL TRACE`, `LATENCY & TOKENS`, `SCHEMA & POLICY STATUS`).
- Clear visual indicator for air-gap status (`AIR_GAP_EGRESS_DENIED` cleanly flagged without stack dumps).
- Deterministic exit codes (`0` ok, `1` runtime error, `2` schema/policy failure) enabling CI integration and local developer iteration.

Approved for production integration.
