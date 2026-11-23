# Forensic QA Handoff: KAN-325

## Overview & User Story
- Ticket ID: KAN-325 ([KB-SEC-MODEL-02] Add Bounded-Lifetime Expiration Timestamp (exp) to Media Proxy Signed URLs)
- Classification: N/A - Non-UI Security Ticket
- Branch: feat/KAN-324-328
- Touched Files:
  - `kanban/media_proxy/__init__.py`
  - `kanban/media_proxy/signing.py`
  - `kanban/api/v1/media_proxy.py`
  - `kanban/tests/api/test_media_proxy.py`
  - `tests/security/test_stride_hostile_media.py`

## User Story
As a security architect, I require all external media proxy signed URLs to incorporate an explicit, bounded expiration timestamp (`exp`) into the HMAC cryptographic payload so that external media links cannot be indefinitely replayed or harvested for unauthorized proxy bandwidth.

---

## Evidence Manifest
1. `git-diff.patch`: Unified diff showing `DEFAULT_MEDIA_PROXY_TTL_SECONDS = 86400`, `MAX_MEDIA_PROXY_TTL_SECONDS = 604800`, `f"{exp}:{url}"` payload signing, and `exp` query parameter validation.
2. `unit-test-results.txt`: 30 passed tests across media proxy suites (`test_media_proxy.py`, `test_media_proxy_api.py`, `test_stride_hostile_media.py`).
3. `build-check.txt`: Clean static gate checks (`make check` exited 0).
4. `api-specialist-review.md`: Backend architect sign-off on HMAC contract and replay defense.
5. `ui-specialist-review.md`: Confirmed N/A - Non-UI Ticket.
6. `changed-files-manifest.txt`: Cryptographic SHA-256 manifest verified with `sha256sum -c`.
