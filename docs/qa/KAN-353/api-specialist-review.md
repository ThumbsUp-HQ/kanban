# API Specialist Review: KAN-353

**Ticket:** `KAN-353` (`[KB-DOCS-FEATURE-03] Author Zero-Trust Service Auth, Headless Workload OIDC, and CredentialBoundary Enforcement Guide (KAN-63, KAN-74)`)
**Reviewer:** `@api-spec` (Backend Architect & API Specialist)
**Status:** `APPROVED`

---

## 1. Scope Evaluation

This ticket authors the architectural reference and implementation guide for internal zero-trust service authentication, headless workload OIDC token exchange, and CredentialBoundary RLS isolation (`thumbs-up-kanban.wiki/Zero-Trust-Service-Auth-and-Workload-OIDC.md` and `kanban/tests/test_docs_service_auth_guide.py`), documenting features shipped under `KAN-63` and `KAN-74` (alongside `KAN-66` and `KAN-67`).

The chapter provides comprehensive, rigorous technical coverage of:
1. **Role-Bound HKDF-HMAC Internal Service Authentication (`KAN-63`):**
   - Key derivation using HKDF-SHA256 from system `master_kek` per principal (`kanban/security/service_auth.py`).
   - Canonical request envelope signing (`ts + principal + method + path + sha256(body)`).
   - Clock drift bounds (maximum 300 seconds) and constant-time HMAC comparison (`hmac.compare_digest`).
   - Extraction of verified client certificates directly from ASGI TLS connection scope (`scope["client_cert"]`), strictly forbidding raw HTTP identity headers.
2. **Headless Workload Identity Federation & RFC 8693 Token Exchange (`KAN-74`):**
   - OpenID Connect discovery and JWKS public key validation (`kanban/auth/oidc/workload.py`).
   - Enforcement of asymmetric cryptographic algorithms (`RS256`, `PS256`, `ES256`, `EdDSA`) and fail-closed rejection of `alg="none"` and symmetric `HS*`.
   - `POST /oauth/token` handling `grant_type=urn:ietf:params:oauth:grant-type:token-exchange` and issuing short-lived ephemeral tokens (`kb_eat_*`).
   - Database tables `workload_identity_policies` and `workload_jti_replays` preventing replay attacks with atomic `ON CONFLICT DO NOTHING`.
3. **CredentialBoundary Capability Bitmasks & RLS Isolation (`KAN-66`, `KAN-67`):**
   - Bitmask definitions (`READ_ISSUES`, `WRITE_ISSUES`, `TRANSITION_ISSUES`, `READ_DOCS`, `WRITE_DOCS`, `EXECUTE_AGENT`, `ADMIN_READ`).
   - Setting PostgreSQL GUC session variables (`app.current_principal_id`, `app.credential_boundary`) evaluated directly by PostgreSQL `FORCE RLS` policies.

---

## 2. API Contract & Invariant Verification

- **Security Protocol Accuracy:** Token exchange specifications adhere strictly to RFC 8693 and RFC 7519 standards.
- **Data Model Parity:** Table definitions and unique constraints in `workload_identity.py` and migration `p6_08_workload_identity_policies` match documented specifications.

---

## 3. Verdict

**`APPROVED`** (Cryptographic authentication protocols, RFC 8693 token exchange schemas, and RLS boundary contracts verified).
