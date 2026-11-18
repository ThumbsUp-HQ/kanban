# API Specialist Review: KANBA-207

## Reviewer: API Specialist (`backend-architect` / `api-tester`)
## Target: `KANBA-207` (Setup Claim API, MFA Isolation Gate, and TOTP Aliasing)

### Technical Evaluation
1. **Setup Claim Endpoint:**
   - Evaluated `kanban/api/v1/auth_setup.py` and `kanban/auth/setup.py`.
   - `SetupClaimRequest` accepts workspace and initial project configurations.
   - `claim_initial_admin()` correctly provisions initial project record in both `objects` spine and `projects` table using deterministic `uuidv7()`.
2. **MFA Isolation:**
   - Evaluated `kanban/api/deps.py` and `kanban/auth/sessions/resolver.py`.
   - When a session has `mfa_pending: true`, `get_principal()` and `require_full_session()` reject all protected routes with `status=401, code="MFA_REQUIRED"`.
   - Tokenless redirection to `/setup` is blocked; pending sessions are forced into MFA challenge on `/login` or cancelled explicitly via logout.
3. **TOTP Confirmation & Verify Alias:**
   - `auth_mfa.py` wires TOTP verification correctly to `/confirm` and exposes `/totp/verify` alias returning `200 OK` (tested via `test_totp.py`).
4. **Specialist Verdict:** APPROVED (Grade: A).
