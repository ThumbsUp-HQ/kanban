# API Specialist Review: KANBA-230

## Reviewer: API Specialist (`backend-architect` / `api-tester`)
## Target: `KANBA-230` (CSRF Cookie Lifecycle, Origin Normalization, and Startup Migration Gate)

### Technical Evaluation
1. **CSRF Lifecycle & Cookie Invariants:**
   - Evaluated `kanban/auth/sessions/csrf.py` and `kanban/api/v1/auth_session.py`.
   - Verified that unresolvable or expired session cookies falling back to `PRE_SESSION_ID` properly append `Max-Age=0` clearing headers and reissue fresh pre-session CSRF tokens, preventing browser stale token wedges.
   - Evaluated `client.ts` retry logic: single retry on `403 CSRF_REJECTED` for unsafe auth endpoints (`/api/v1/auth/local/login` and `/api/v1/setup/claim`) after refreshing `bootstrapCsrfToken()`.
2. **Origin Parsing:**
   - Normalization of `KANBAN_PUBLIC_ORIGIN` / `KB_PUBLIC_ORIGIN` using `urllib.parse.urlsplit` to `scheme://netloc` eliminates false-positive CSRF rejections on subpath deployments.
3. **Migration Orchestration:**
   - `kanban-migrate` service in `docker-compose.yml` runs with least privileges (user `65532:65532`, cap_drop `ALL`, `data_net`) and blocks dependent services (`kanban-api`, `outbox-relay`) until head is reached.
   - `verify_schema_head()` in `kanban/app.py` enforces fast fail-safe diagnostic logging (`❌`) if database Alembic revision is behind code head.
4. **Specialist Verdict:** APPROVED (Grade: A).
