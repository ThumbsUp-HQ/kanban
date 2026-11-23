# Message to Reality-Checker: KAN-335 (`[KB-REDTEAM-04]`)

## Ticket Scope & Browser Screenshot Classification
- **Ticket:** `KAN-335` - `[KB-REDTEAM-04] Re-Execute SET LOCAL GUC Context on Transaction Re-Begin in RLSSessionFactory`
- **Branch:** `feat/KAN-329-336`
- **Browser Screenshots:** `N/A - Non-UI Security Ticket` (Database Session Lifecycle, PostgreSQL GUCs, and RLS)
- **Owned Slice Modified:**
  - `database/rls/context.py`
  - `database/session.py`
  - `database/tests/test_rls_session_rebegin.py`
  - `docs/qa/KAN-335/*`

## Requirement-to-Evidence Mapping

1. **Re-Execute SET LOCAL GUC Context on Transaction Re-Begin:**
   - **Implementation:** Added `bind_rls_context_sync` in `database/rls/context.py` and attached `_rebind_on_begin` event listener to `after_begin` on `Session` in `database/session.py`.
   - **Evidence:** `docs/qa/KAN-335/git-diff.patch` and `database/session.py`.

2. **Verify Persistence Across Commit, Rollback, and Multi-Transaction Sequences:**
   - **Implementation:** Comprehensive test suite in `database/tests/test_rls_session_rebegin.py` validating that GUC variables (`request.jwt.claim.sub`, `request.jwt.claim.workspace_id`, etc.) persist after `await session.commit()`, `await session.rollback()`, and across successive transactions.
   - **Evidence:** `database/tests/test_rls_session_rebegin.py` (3/3 tests pass).

3. **Mandatory Quality & Code Hygiene:**
   - Zero em-dashes or en-dashes (`uv run python -m scripts.check_no_dashes --all` exits 0).
   - Full static validation passed (`make check` exits 0).

All artifacts and checksums are verified in `docs/qa/KAN-335/changed-files-manifest.txt`.
