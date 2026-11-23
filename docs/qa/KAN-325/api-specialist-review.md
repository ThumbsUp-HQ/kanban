# API Specialist Review: KAN-325

## Audit Metadata
- Ticket ID: KAN-325 ([KB-SEC-MODEL-02])
- Title: Add Bounded-Lifetime Expiration Timestamp (exp) to Media Proxy Signed URLs
- Reviewer: backend-architect (API Specialist)
- Date: 2026-11-23
- Status: APPROVED

---

## 1. Scope & Objective
Ticket KAN-325 hardens external media proxy signed URLs by introducing a mandatory, bounded-lifetime expiration timestamp (`exp`). Previously, signed URLs used HMAC over `url` alone without expiration, permitting replay attacks.

---

## 2. API & Cryptographic Signature Verification
1. **Bounded Lifetime Invariants:**
   - Default TTL: `DEFAULT_MEDIA_PROXY_TTL_SECONDS = 86400` (24 hours).
   - Maximum TTL: `MAX_MEDIA_PROXY_TTL_SECONDS = 604800` (7 days).
   - Expiration validation rejects expired timestamps (`exp < now_ts`) and unreasonable far-future timestamps (`exp > now_ts + MAX_MEDIA_PROXY_TTL_SECONDS + 300`).
2. **HMAC Signing Envelope:**
   - Payload format: `f"{exp}:{url}".encode()`.
   - Subkey derivation: `derive_subkey(key_material.session_hmac_key, "media-proxy/url")`.
   - Constant-time verification: `hmac.compare_digest(candidate_digest, expected_digest)`.
   - Verification executes BEFORE URL parsing or DNS resolution to eliminate unauthenticated work and SSRF probing vectors.
3. **Endpoint Query Interface:**
   - Route: `GET /api/v1/media-proxy?u=<encoded_url>&exp=<int_ts>&sig=<hmac_sig>`.
   - Parameter `exp: int | None = Query(default=None)`: explicitly validated, missing `exp` immediately returns 403 `INVALID_SIGNATURE`.
   - Tampered `exp` or `u` or `sig` returns 403 `INVALID_SIGNATURE`.

---

## 3. Test Coverage & Quality Gate
- `kanban/tests/api/test_media_proxy.py`: 9 comprehensive unit tests covering bounded TTLs, replay attack rejection, tampering checks, and live ASGI integration.
- `kanban/tests/media_proxy/test_media_proxy_api.py`: 17 tests passed.
- `tests/security/test_stride_hostile_media.py`: 4 tests passed.
- Coverage on `kanban.media_proxy.signing`: 97%.
- Coverage on `kanban.media_proxy.client`: 96%.
- Total media proxy test suite: 100% pass rate.

---

## 4. Conclusion
The media proxy signed URL architecture satisfies all security invariants, bounds replay vulnerability windows, and preserves fast constant-time verification. Approved for ticket closure.
