"""Unit tests for envelope encryption and key wrapping (KB-P2-03)."""

from __future__ import annotations

import base64
import logging
import os
import uuid

import pytest

from kanban.security.envelope import (
    BLOB_VERSION,
    MAX_PLAINTEXT_BYTES,
    EnvelopeDecryptError,
    EnvelopeInputError,
    StaticKekProvider,
    UnknownKekError,
    open_card_secret,
    rewrap_dek,
    seal_card_secret,
)
from kanban.security.keys import KeyMaterial


@pytest.fixture
def kek_provider() -> StaticKekProvider:
    """Fixture providing StaticKekProvider with kek-v1 and kek-v2."""
    k1 = os.urandom(32)
    k2 = os.urandom(32)
    return StaticKekProvider(
        keys={"kek-v1": k1, "kek-v2": k2},
        current="kek-v1",
    )


def test_01_positive_seal_and_open_round_trip(kek_provider: StaticKekProvider) -> None:
    """Test Case 1: Seal then open round-trips binary secret, validates prefixes and randomness."""
    card_id = uuid.uuid4()
    provider_kind = "OIDC"
    secret = b"client-secret-\x00\xff"

    sealed1 = seal_card_secret(card_id, provider_kind, secret, kek_provider)
    assert sealed1.dek_kid == "kek-v1"
    assert sealed1.encrypted_secret_blob[0] == BLOB_VERSION
    assert sealed1.wrapped_dek[0] == BLOB_VERSION

    # Two seals of the same secret must produce different ciphertexts due to fresh DEK & nonces
    sealed2 = seal_card_secret(card_id, provider_kind, secret, kek_provider)
    assert sealed1.encrypted_secret_blob != sealed2.encrypted_secret_blob
    assert sealed1.wrapped_dek != sealed2.wrapped_dek

    opened = open_card_secret(card_id, provider_kind, sealed1, kek_provider)
    assert isinstance(opened, bytearray)
    assert bytes(opened) == secret


def test_02_gcm_tag_tamper(kek_provider: StaticKekProvider) -> None:
    """Test Case 2: Bit flip in version, nonce, body, or tag raises EnvelopeDecryptError."""
    card_id = uuid.uuid4()
    provider_kind = "OIDC"
    secret = b"sensitive-ldap-password-12345"

    sealed = seal_card_secret(card_id, provider_kind, secret, kek_provider)

    def flip_bit(data: bytes, index: int) -> bytes:
        b = bytearray(data)
        b[index] ^= 0x01
        return bytes(b)

    # Test tampering on encrypted_secret_blob
    # 1. Version byte tamper (index 0) -> BAD_VERSION
    tampered_ver = flip_bit(sealed.encrypted_secret_blob, 0)
    with pytest.raises(EnvelopeDecryptError) as exc_info:
        open_card_secret(
            card_id,
            provider_kind,
            sealed.__class__(tampered_ver, sealed.wrapped_dek, sealed.dek_kid),
            kek_provider,
        )
    assert exc_info.value.code == "BAD_VERSION"

    # 2. Nonce tamper (index 5) -> TAG_MISMATCH
    tampered_nonce = flip_bit(sealed.encrypted_secret_blob, 5)
    with pytest.raises(EnvelopeDecryptError) as exc_info:
        open_card_secret(
            card_id,
            provider_kind,
            sealed.__class__(tampered_nonce, sealed.wrapped_dek, sealed.dek_kid),
            kek_provider,
        )
    assert exc_info.value.code == "TAG_MISMATCH"

    # 3. Ciphertext body tamper (index 15) -> TAG_MISMATCH
    tampered_ct = flip_bit(sealed.encrypted_secret_blob, 15)
    with pytest.raises(EnvelopeDecryptError) as exc_info:
        open_card_secret(
            card_id,
            provider_kind,
            sealed.__class__(tampered_ct, sealed.wrapped_dek, sealed.dek_kid),
            kek_provider,
        )
    assert exc_info.value.code == "TAG_MISMATCH"

    # 4. Last tag byte tamper -> TAG_MISMATCH
    tampered_tag = flip_bit(sealed.encrypted_secret_blob, len(sealed.encrypted_secret_blob) - 1)
    with pytest.raises(EnvelopeDecryptError) as exc_info:
        open_card_secret(
            card_id,
            provider_kind,
            sealed.__class__(tampered_tag, sealed.wrapped_dek, sealed.dek_kid),
            kek_provider,
        )
    assert exc_info.value.code == "TAG_MISMATCH"

    # Test tampering on wrapped_dek
    # 1. Wrapped DEK version byte tamper -> BAD_VERSION
    tampered_dek_ver = flip_bit(sealed.wrapped_dek, 0)
    with pytest.raises(EnvelopeDecryptError) as exc_info:
        open_card_secret(
            card_id,
            provider_kind,
            sealed.__class__(sealed.encrypted_secret_blob, tampered_dek_ver, sealed.dek_kid),
            kek_provider,
        )
    assert exc_info.value.code == "BAD_VERSION"

    # 2. Wrapped DEK nonce tamper -> TAG_MISMATCH
    tampered_dek_nonce = flip_bit(sealed.wrapped_dek, 5)
    with pytest.raises(EnvelopeDecryptError) as exc_info:
        open_card_secret(
            card_id,
            provider_kind,
            sealed.__class__(sealed.encrypted_secret_blob, tampered_dek_nonce, sealed.dek_kid),
            kek_provider,
        )
    assert exc_info.value.code == "TAG_MISMATCH"

    # 3. Wrapped DEK body tamper -> TAG_MISMATCH
    tampered_dek_ct = flip_bit(sealed.wrapped_dek, 15)
    with pytest.raises(EnvelopeDecryptError) as exc_info:
        open_card_secret(
            card_id,
            provider_kind,
            sealed.__class__(sealed.encrypted_secret_blob, tampered_dek_ct, sealed.dek_kid),
            kek_provider,
        )
    assert exc_info.value.code == "TAG_MISMATCH"

    # 4. Wrapped DEK last tag byte tamper -> TAG_MISMATCH
    tampered_dek_tag = flip_bit(sealed.wrapped_dek, len(sealed.wrapped_dek) - 1)
    with pytest.raises(EnvelopeDecryptError) as exc_info:
        open_card_secret(
            card_id,
            provider_kind,
            sealed.__class__(sealed.encrypted_secret_blob, tampered_dek_tag, sealed.dek_kid),
            kek_provider,
        )
    assert exc_info.value.code == "TAG_MISMATCH"


def test_03_cut_and_paste_resistance(kek_provider: StaticKekProvider) -> None:
    """Test Case 3: AAD binding prevents cut-and-paste across cards and provider kinds."""
    card_a = uuid.uuid4()
    card_b = uuid.uuid4()
    secret = b"my-client-secret"

    sealed_a = seal_card_secret(card_a, "OIDC", secret, kek_provider)
    sealed_b = seal_card_secret(card_b, "OIDC", b"other-secret", kek_provider)

    # 1. Opened with Card B identifier -> TAG_MISMATCH
    with pytest.raises(EnvelopeDecryptError) as exc:
        open_card_secret(card_b, "OIDC", sealed_a, kek_provider)
    assert exc.value.code == "TAG_MISMATCH"

    # 2. Opened with different provider_kind -> TAG_MISMATCH
    with pytest.raises(EnvelopeDecryptError) as exc:
        open_card_secret(card_a, "LDAP", sealed_a, kek_provider)
    assert exc.value.code == "TAG_MISMATCH"

    # 3. Swapping wrapped_dek from Card B to Card A -> TAG_MISMATCH
    swapped = sealed_a.__class__(
        encrypted_secret_blob=sealed_a.encrypted_secret_blob,
        wrapped_dek=sealed_b.wrapped_dek,
        dek_kid=sealed_a.dek_kid,
    )
    with pytest.raises(EnvelopeDecryptError) as exc:
        open_card_secret(card_a, "OIDC", swapped, kek_provider)
    assert exc.value.code == "TAG_MISMATCH"


def test_04_kid_downgrade_and_tampering(kek_provider: StaticKekProvider) -> None:
    """Test Case 4: Altering dek_kid raises UNKNOWN_KID or TAG_MISMATCH due to AAD."""
    card_id = uuid.uuid4()
    secret = b"key-rotation-secret"
    sealed = seal_card_secret(card_id, "OAUTH2", secret, kek_provider)

    # 1. Unknown KID -> UNKNOWN_KID
    downgraded_unknown = sealed.__class__(
        encrypted_secret_blob=sealed.encrypted_secret_blob,
        wrapped_dek=sealed.wrapped_dek,
        dek_kid="kek-v0",
    )
    with pytest.raises(EnvelopeDecryptError) as exc:
        open_card_secret(card_id, "OAUTH2", downgraded_unknown, kek_provider)
    assert exc.value.code == "UNKNOWN_KID"

    # 2. Known alternate KID -> TAG_MISMATCH (since kid is bound into wrapped DEK AAD)
    swapped_known = sealed.__class__(
        encrypted_secret_blob=sealed.encrypted_secret_blob,
        wrapped_dek=sealed.wrapped_dek,
        dek_kid="kek-v2",
    )
    with pytest.raises(EnvelopeDecryptError) as exc:
        open_card_secret(card_id, "OAUTH2", swapped_known, kek_provider)
    assert exc.value.code == "TAG_MISMATCH"


def test_05_boundaries_and_limits(kek_provider: StaticKekProvider) -> None:
    """Test Case 5: Truncated blobs reject (<29 bytes) and plaintext cap at 16384 bytes."""
    card_id = uuid.uuid4()

    # Truncated blob of 28 bytes -> TRUNCATED
    short_blob = bytes([BLOB_VERSION]) + os.urandom(27)
    assert len(short_blob) == 28

    valid_sealed = seal_card_secret(card_id, "OIDC", b"test", kek_provider)

    truncated_secret = valid_sealed.__class__(
        encrypted_secret_blob=short_blob,
        wrapped_dek=valid_sealed.wrapped_dek,
        dek_kid=valid_sealed.dek_kid,
    )
    with pytest.raises(EnvelopeDecryptError) as exc:
        open_card_secret(card_id, "OIDC", truncated_secret, kek_provider)
    assert exc.value.code == "TRUNCATED"

    truncated_dek = valid_sealed.__class__(
        encrypted_secret_blob=valid_sealed.encrypted_secret_blob,
        wrapped_dek=short_blob,
        dek_kid=valid_sealed.dek_kid,
    )
    with pytest.raises(EnvelopeDecryptError) as exc:
        open_card_secret(card_id, "OIDC", truncated_dek, kek_provider)
    assert exc.value.code == "TRUNCATED"

    # Exact max plaintext: 16384 bytes
    max_payload = b"A" * MAX_PLAINTEXT_BYTES
    sealed_max = seal_card_secret(card_id, "LOCAL_ADMIN", max_payload, kek_provider)
    opened_max = open_card_secret(card_id, "LOCAL_ADMIN", sealed_max, kek_provider)
    assert bytes(opened_max) == max_payload

    # Exceeding limit: 16385 bytes -> EnvelopeInputError
    with pytest.raises(EnvelopeInputError):
        seal_card_secret(card_id, "LOCAL_ADMIN", b"B" * (MAX_PLAINTEXT_BYTES + 1), kek_provider)


def test_06_kek_rotation_via_rewrap_dek(kek_provider: StaticKekProvider) -> None:
    """Test Case 6: Rewrapping DEK to kek-v2 preserves encrypted_secret_blob and allows opening."""
    card_id = uuid.uuid4()
    secret = b"rotate-me-please"

    sealed_v1 = seal_card_secret(card_id, "OIDC", secret, kek_provider)
    assert sealed_v1.dek_kid == "kek-v1"

    sealed_v2 = rewrap_dek(card_id, sealed_v1, kek_provider, "kek-v2")
    assert sealed_v2.dek_kid == "kek-v2"
    # The secret blob bytes must be identical before and after rewrap
    assert sealed_v2.encrypted_secret_blob == sealed_v1.encrypted_secret_blob
    assert sealed_v2.wrapped_dek != sealed_v1.wrapped_dek

    # Opened with provider having both keys -> succeeds
    opened = open_card_secret(card_id, "OIDC", sealed_v2, kek_provider)
    assert bytes(opened) == secret

    # Provider having only kek-v1 fails with UNKNOWN_KID on sealed_v2
    kek_only_v1 = StaticKekProvider(keys={"kek-v1": kek_provider.get("kek-v1")}, current="kek-v1")
    with pytest.raises(EnvelopeDecryptError) as exc:
        open_card_secret(card_id, "OIDC", sealed_v2, kek_only_v1)
    assert exc.value.code == "UNKNOWN_KID"

    # rewrap_dek with truncated wrapped_dek -> TRUNCATED
    short_dek = bytes([BLOB_VERSION]) + os.urandom(27)
    with pytest.raises(EnvelopeDecryptError) as exc:
        rewrap_dek(
            card_id,
            sealed_v1.__class__(sealed_v1.encrypted_secret_blob, short_dek, "kek-v1"),
            kek_provider,
            "kek-v2",
        )
    assert exc.value.code == "TRUNCATED"

    # rewrap_dek with bad version -> BAD_VERSION
    bad_ver_dek = bytes([0x02]) + os.urandom(28)
    with pytest.raises(EnvelopeDecryptError) as exc:
        rewrap_dek(
            card_id,
            sealed_v1.__class__(sealed_v1.encrypted_secret_blob, bad_ver_dek, "kek-v1"),
            kek_provider,
            "kek-v2",
        )
    assert exc.value.code == "BAD_VERSION"

    # rewrap_dek with tampered wrapped_dek -> TAG_MISMATCH
    tampered_dek = bytearray(sealed_v1.wrapped_dek)
    tampered_dek[len(tampered_dek) - 1] ^= 0x01
    with pytest.raises(EnvelopeDecryptError) as exc:
        rewrap_dek(
            card_id,
            sealed_v1.__class__(sealed_v1.encrypted_secret_blob, bytes(tampered_dek), "kek-v1"),
            kek_provider,
            "kek-v2",
        )
    assert exc.value.code == "TAG_MISMATCH"

    # rewrap_dek with unknown old or new kid -> UNKNOWN_KID
    with pytest.raises(EnvelopeDecryptError) as exc:
        rewrap_dek(card_id, sealed_v1, kek_provider, "nonexistent-kek")
    assert exc.value.code == "UNKNOWN_KID"

    with pytest.raises(EnvelopeDecryptError) as exc:
        rewrap_dek(
            card_id,
            sealed_v1.__class__(sealed_v1.encrypted_secret_blob, sealed_v1.wrapped_dek, "bad-old"),
            kek_provider,
            "kek-v2",
        )
    assert exc.value.code == "UNKNOWN_KID"


def test_10_logging_zero_leakage(
    kek_provider: StaticKekProvider, caplog: pytest.LogCaptureFixture
) -> None:
    """Test Case 10: Full seal/open/rewrap emits zero records containing plaintext or keys."""
    caplog.set_level(logging.DEBUG)

    card_id = uuid.uuid4()
    secret = b"super-confidential-credential-xyz987"
    k1 = kek_provider.get("kek-v1")

    sealed = seal_card_secret(card_id, "OIDC", secret, kek_provider)
    opened = open_card_secret(card_id, "OIDC", sealed, kek_provider)
    assert bytes(opened) == secret
    rewrapped = rewrap_dek(card_id, sealed, kek_provider, "kek-v2")
    assert rewrapped.dek_kid == "kek-v2"

    secret_b64 = base64.b64encode(secret).decode("ascii")
    secret_hex = secret.hex()
    k1_b64 = base64.b64encode(k1).decode("ascii")
    k1_hex = k1.hex()

    for record in caplog.records:
        msg = record.getMessage()
        assert secret.decode("ascii") not in msg
        assert secret_b64 not in msg
        assert secret_hex not in msg
        assert k1_b64 not in msg
        assert k1_hex not in msg


def test_static_kek_provider_validations() -> None:
    """Test StaticKekProvider initialization validations."""
    km = KeyMaterial(
        master_kek=os.urandom(32),
        auth_pepper=os.urandom(32),
        session_hmac_key=os.urandom(32),
        master_kek_kid="kek-custom",
    )
    p_km = StaticKekProvider.from_key_material(km)
    assert p_km.current_kid() == "kek-custom"
    assert p_km.get("kek-custom") == km.master_kek

    with pytest.raises(ValueError, match="Key map cannot be empty"):
        StaticKekProvider(keys={}, current="kek-v1")

    with pytest.raises(ValueError, match="not in provided keys"):
        StaticKekProvider(keys={"kek-v1": os.urandom(32)}, current="kek-v2")

    with pytest.raises(ValueError, match="must be 32 bytes"):
        StaticKekProvider(keys={"kek-v1": b"short"}, current="kek-v1")

    p = StaticKekProvider(keys={"kek-v1": os.urandom(32)}, current="kek-v1")
    assert p.current_kid() == "kek-v1"
    with pytest.raises(UnknownKekError):
        p.get("unknown")
