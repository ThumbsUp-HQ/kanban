# Reality-Checker Verification Packet: KANBA-58 (KB-P2-03)

## Ticket Metadata
- Ticket ID: `KANBA-58`
- Spec Key: `KB-P2-03`
- Title: `[Phase 2 / Auth] auth_provider_cards DDL, kb_auth data boundary & AES-256-GCM envelope encryption with dek_kid rotation`
- Epic: `KB-E2` (Phase 2 Kanban API & Core Platform Services)
- Spec Sections: `4.1` (`auth_provider_cards` DDL, `encrypted_secret_blob`, `wrapped_dek`, `dek_kid`), `2.2` item 1 (`MASTER_KEK`), `2.5` (`pyca/cryptography`), Requirement `#6`
- Dependencies: `KB-P1-17`, `KB-P2-01` (uses `KeyMaterial` from `kanban/security/keys.py`)
- Gates: `reality-checker` (Passive Forensic Mode)
- Classification: N/A - Non-UI Ticket

---

## User Story
As a **security engineer operating the Multi-Card Auth Studio**, I need **every IdP client secret and LDAP bind password stored only as AES-256-GCM ciphertext under a per-card DEK wrapped by `MASTER_KEK`, with the auth tables unreachable from the general `kanban_app` role except through narrow `SECURITY DEFINER` functions** so that **a SQL injection, a database dump, or a serializer bug cannot disclose any auth secret, and a ciphertext moved between cards fails to decrypt**.

---

## Scoped Definition of Done Checklist
- [x] **File Existence & Implementation:** `database/migrations/versions/p2_03_auth_provider_cards.py`, `database/migrations/sql/p2_03_auth_provider_cards.up.sql`, `database/migrations/sql/p2_03_auth_provider_cards.down.sql`, `database/models/auth.py`, `kanban/security/envelope.py`, `kanban/auth/cards/repository.py`, and `kanban/auth/cards/schemas.py` exist and define `KekProvider`, `StaticKekProvider`, `SealedSecret`, `seal_card_secret`, `open_card_secret`, `rewrap_dek`, `EnvelopeDecryptError`, `AuthCardPublic`, `AuthCardAdmin`, `rewrap_all`, and the six `kb_auth.*` functions.
- [x] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/security/test_envelope.py kanban/tests/auth/test_card_repository.py database/tests/test_auth_provider_cards.py -q --cov=kanban/security/envelope.py --cov=kanban/auth/cards --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with all 10 mandatory cases present and 99.65% branch and line coverage.
- [x] **Migration Reversible:** `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` exits `0` (documented in `docs/qa/KANBA-58/migration-roundtrip.txt`).
- [x] **Build / Type / Lint Clean:** `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict kanban database && uv run lint-imports` exits `0` with zero warnings.
- [x] **Only AESGCM Used:** `grep -rn "AES\|Fernet\|ChaCha" kanban/security/envelope.py` shows only `AESGCM` imports and usages.
- [x] **No Forbidden Unicode Dashes:** Repository passes `uv run python -m scripts.check_no_dashes --all` with zero violations.
- [x] **Forensic Proof Packet Complete:** All required proof files exist under `docs/qa/KANBA-58/`.

---

## Mandatory Feature Unit Tests Matrix (10/10 Covered)

| Case | Category | Test Target | Verification Description |
| :--- | :--- | :--- | :--- |
| **Case 1** | Positive Smoke | `kanban/tests/security/test_envelope.py::test_01_positive_seal_and_open_round_trip` | Seal then open round-trips binary secret `b"client-secret-\x00\xff"`; validates `0x01` prefix and nonce/DEK randomness between two seals of identical plaintext. |
| **Case 2** | Security (GCM Tamper) | `kanban/tests/security/test_envelope.py::test_02_gcm_tag_tamper` | 1-bit flips in version byte, nonce, ciphertext body, or tag raise `EnvelopeDecryptError` with expected `BAD_VERSION` or `TAG_MISMATCH`. |
| **Case 3** | Security (Cut-and-Paste) | `kanban/tests/security/test_envelope.py::test_03_cut_and_paste_resistance` | Opening card A secret with card B UUID fails (`TAG_MISMATCH`); opening OIDC secret with provider_kind="LDAP" fails (`TAG_MISMATCH`); swapping wrapped_dek between cards fails (`TAG_MISMATCH`). |
| **Case 4** | Security (KID Downgrade) | `kanban/tests/security/test_envelope.py::test_04_kid_downgrade_and_tamper` | Unknown `dek_kid` raises `UNKNOWN_KID`; altering `dek_kid` to another known key raises `TAG_MISMATCH` because KID is cryptographically bound in wrapped DEK AAD. |
| **Case 5** | Boundary Limits | `kanban/tests/security/test_envelope.py::test_05_blob_length_and_plaintext_boundaries` | Truncated blob (< 29 bytes) raises `TRUNCATED`; 16384-byte plaintext seals cleanly; 16385-byte plaintext raises `EnvelopeInputError`. |
| **Case 6** | Key Rotation | `kanban/tests/security/test_envelope.py::test_06_rotation_and_rewrap` | DEK rewrapped from `kek-v1` to `kek-v2`; decrypted plaintext matches; `encrypted_secret_blob` bytes remain unchanged; old single-key provider fails with `UNKNOWN_KID`. |
| **Case 7** | DB Role Boundary | `database/tests/test_auth_provider_cards.py::test_07_db_boundary_and_privileges` | `kanban_app` direct `SELECT * FROM auth_provider_cards` raises `42501`; `SELECT encrypted_secret_blob FROM kb_auth.card_list_enabled_public()` raises `42703` (undefined column); `card_admin_list()` without SERVER_ADMIN or with AAL1 raises `42501`; with SERVER_ADMIN + AAL2 returns rows. |
| **Case 8** | DDL Checks & Search Path | `database/tests/test_auth_provider_cards.py::test_08_db_ddl_constraints_and_search_path` | Rejected slugs (`-bad`, `a`, `UPPER`, 49 chars) raise `23514`; `provider_kind='SAML'` raises `23514`; secret without wrapped DEK raises `23514`; shadow `public.lower()` hijack attempt does not alter function execution. |
| **Case 9** | Serializer Invariant | `kanban/tests/auth/test_card_repository.py::test_09_serializer_and_model_invariants` | `AuthCardPublic` and `AuthCardAdmin` JSON schemas never expose `encrypted_secret_blob`, `wrapped_dek`, `client_secret`, `bind_password`, or `secret`; `repr()` and `str()` of `AuthProviderCard` mask ciphertext; dumped JSON contains no secret bytes. |
| **Case 10** | Debug Log Non-Leakage | `kanban/tests/security/test_envelope.py::test_10_logging_sanitization` | Full seal/open/rewrap lifecycle under `DEBUG` logging records zero plaintext bytes, DEK bytes, or KEK bytes in raw, hex, or base64 format. |

---

## Technical Actions & Implementation Matrix

| Component | Target Location | Description |
| :--- | :--- | :--- |
| **Alembic Migration** | `database/migrations/versions/p2_03_auth_provider_cards.py` | Migration revision `p2_03_auth_provider_cards` chaining from `p1_18_outbox`. Executes SQL files online under `kanban_migrator`. |
| **Migration SQL Up** | `database/migrations/sql/p2_03_auth_provider_cards.up.sql` | DDL for role `kb_auth_owner`, schema `kb_auth`, table `auth_provider_cards` with `FORCE ROW LEVEL SECURITY`, and six `SECURITY DEFINER` functions with `search_path = pg_catalog, public`. |
| **Migration SQL Down** | `database/migrations/sql/p2_03_auth_provider_cards.down.sql` | Fully reversible teardown cleanly dropping functions, table, schema, and role. |
| **Declarative ORM Model** | `database/models/auth.py` | `AuthProviderCard` model with sanitized `__repr__`/`__str__` masking secret ciphertext. Exported via `database/models/__init__.py` (table count: 35). |
| **Envelope Encryption Engine** | `kanban/security/envelope.py` | `pyca/cryptography` AESGCM envelope encryption, `KekProvider`, `StaticKekProvider`, `SealedSecret`, `seal_card_secret`, `open_card_secret`, and `rewrap_dek` with ephemeral DEK zeroization. |
| **Pydantic Schemas** | `kanban/auth/cards/schemas.py` | `AuthCardPublic` (public login view) and `AuthCardAdmin` (Studio administration with `has_secret` flag), both with `extra="forbid"` and zero secret columns. |
| **Card Repository** | `kanban/auth/cards/repository.py` | Async repository calling only `kb_auth.*` functions via `text()` parameters, plus `rewrap_all()` bulk rotation function. |

---

## Cryptographic Envelope Specification
- **Algorithm:** AES-256-GCM exclusively via `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
- **Wire Format (both secret blob and wrapped DEK):**
  `version (1 byte = 0x01) || nonce (12 bytes, os.urandom) || ciphertext || tag (16 bytes)`
- **AAD Bindings:**
  - Secret Blob AAD: `b"kanban/card-secret/v1|" + card_id.bytes + b"|" + provider_kind.encode("utf-8")`
  - Wrapped DEK AAD: `b"kanban/card-dek/v1|" + card_id.bytes + b"|" + dek_kid.encode("utf-8")`
- **Volatile State Sanitization:**
  - DEK is allocated in a mutable `bytearray`, used inside a `try` block, and wiped to zeros (`dek[i] = 0`) inside a `finally` block.
  - `open_card_secret()` returns a mutable `bytearray` allowing callers to zeroize decrypted material.
