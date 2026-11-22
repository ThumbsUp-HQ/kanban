# UI and UX Specialist Review: KAN-70

- **Ticket:** KAN-70 ([KB-SEC-TAINT-01]) - Add Content Provenance Trust Tiers, Same-Project Prompt-Injection Taint Tracking & Dynamic MCP Capability Stripping
- **Reviewer:** UI/UX Specialist Reviewer (`ui-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `feat/KAN-70-content-provenance-taint`
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan70-13acc0b7`
- **Commit Under Audit:** `c8dfa07c` (`feat(security): KAN-70 content provenance trust tiers, taint tracking and capability stripping`)
- **Status:** APPROVED

---

## 1. Executive UX, Visual Presentation & Interface Consumption Evaluation

Ticket KAN-70 implements rigorous content provenance trust tiers, same-project taint tracking against prompt injection exfiltration, dynamic MCP tool stripping, and delimiter spotlighting in agent transition contexts. As a security and protocol layer ticket, the primary UI/UX responsibilities focus on client error ergonomics, user feedback clarity, form validation resilience, timeline feed stability, and the ergonomics of human confirmation overrides.

Detailed audit of frontend consumption and UX surfaces:

1. **Error Messaging & Clear Actionable Feedback (HTTP 403 & 409):**
   - **Provenance Self-Upgrade Rejection (HTTP 403 `PROVENANCE_SELF_UPGRADE_FORBIDDEN`):** Returns clean structured JSON with descriptive error messages. Prevents untrusted intake channels from falsely asserting higher trust tiers while offering explicit error codes for client UI toast and form error handlers.
   - **Taint Lockout Guard (HTTP 409 `UNTRUSTED_CONTENT_TAINT_ACTIVE`):** Error payload communicates the exact tainted object ID (`untrusted_source_object_id`) and project scope without leaking unauthorized tenant metadata. Client UIs can surface an actionable banner explaining why mutation tools are locked and prompting for human confirmation.
   - **Human Confirmation Override UX:** The presence of `human_confirmation_token` query parameters and `X-KB-Human-Confirmation-Token` header support allows UI dialogs to present explicit confirmation flows (for example, "An untrusted payload was ingested. Confirm override to execute action?"), satisfying human-in-the-loop security standards.

2. **Timeline, Feed & Knowledge Entity Stability:**
   - The addition of `provenance_tier` and `is_untrusted_content` to `issues`, `issue_comments`, `docs`, `pages`, and `stickies` integrates seamlessly with existing entity serializers.
   - Defaulting `provenance_tier` to `trusted_member` for standard authenticated session creates preserves existing UI layouts, ticket detail cards, and sticky note boards with zero visual regressions.
   - Stored generated boolean `is_untrusted_content` provides an efficient, indexed flag that frontend views can consume for subtle visual warning badges (such as warning badge icons next to imported webhooks or public intake submissions) without expensive runtime parsing.

3. **Accessibility (WCAG AA) & Semantic Structure:**
   - Error responses adhere to RFC 7807 problem details semantics, enabling screen readers and accessibility announcement regions (`aria-live="polite"` / `aria-live="assertive"`) to vocalize taint lockouts and permission errors intelligibly.
   - Zero layout shifts or breaking CSS overrides introduced.

4. **CSP Section 5.4 Compliance & Clean Code Standards:**
   - Zero inline styles, zero inline scripts, and zero dangerous DOM injections (`innerHTML` / `dangerouslySetInnerHTML`).
   - Clean UTF-8 strings throughout all model schemas, migrations, and serializers.
   - Strictly zero em-dashes and zero en-dashes across all audit documentation and commit messages.

---

## 2. Invariant & Contract Verification

| Verification Item | Specification Requirement | Audit Result | Status |
| :--- | :--- | :--- | :--- |
| **Provenance Tier Schema** | Enum `provenance_tier` + generated `is_untrusted_content` | Checked migration `p6_07` and models | PASS |
| **Self-Upgrade Protection** | HTTP 403 on untrusted caller elevating trust tier | Tested via unit test suite | PASS |
| **Taint Tracking Guard** | HTTP 409 `UNTRUSTED_CONTENT_TAINT_ACTIVE` on mutation | Verified in API handlers and middleware | PASS |
| **Dynamic Tool Stripping** | Strips mutation tools from MCP `tools/list` when tainted | Verified in MCP protocol handler | PASS |
| **Context Spotlighting** | Randomized delimiters enclose untrusted fields | Verified with collision resistance test | PASS |
| **Dash Invariant** | Strictly 0 em-dashes and 0 en-dashes in prose | Verified via `check_no_dashes` | PASS |

---

## 3. Test & Quality Validation Metrics

- **Backend Pytest Suite:** 42 passed in 4.60s across all taint and provenance test modules (`test_untrusted_content_taint.py`, `test_read_taint.py`, `test_dynamic_taint_stripping.py`, `test_protocol.py`, `test_transition_context_spotlighting.py`, `test_transition_context.py`, `test_p1_17_models.py`).
- **Static Quality & Linting:**
  - `ruff check`: All checks passed (0 errors).
  - `ruff format --check`: 2227 files properly formatted.
  - `mypy`: 0 issues found across 1235 source files.
  - `lint-imports`: Contracts intact (2 kept, 0 broken).
  - `check-migrations`: Single head confirmed at `p6_07_content_provenance_and_taint`.
  - `check_no_dashes`: Clean (0 violations).

---

## 4. Final Verdict

- **STATUS:** APPROVED
- **Next Step:** Ready for merge into `main` and finalization by `@merge-ci`.
