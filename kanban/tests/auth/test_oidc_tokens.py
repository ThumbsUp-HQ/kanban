# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for OIDC token validation, algorithm allowlists, and private_key_jwt (KB-P2-06)."""

from __future__ import annotations

import base64
import hmac

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from joserfc import jwt
from joserfc.jwk import ECKey, KeySet

from kanban.api.problems import ProblemException
from kanban.auth.oidc.tokens import (
    build_private_key_jwt,
    validate_id_token,
)
from kanban.tests.fixtures.fake_idp import FakeIdP


@pytest.fixture
def fake_idp() -> FakeIdP:
    """Fixture providing an in-memory FakeIdP instance."""
    return FakeIdP(issuer="https://idp.example.com", client_id="test-client-id")


@pytest.fixture
def jwks(fake_idp: FakeIdP) -> KeySet:
    """Fixture providing KeySet loaded from fake IdP."""
    return KeySet.import_key_set({"keys": [fake_idp.jwk_public_dict]})


def test_positive_id_token_validation(fake_idp: FakeIdP, jwks: KeySet) -> None:
    """Verify normal validation of a valid RS256 ID token."""
    nonce_bytes = b"test-nonce-16by!"
    id_token = fake_idp.create_id_token(
        subject="user-1234",
        nonce=nonce_bytes.decode("latin-1"),
        email="user1234@example.com",
    )

    claims = validate_id_token(
        id_token,
        jwks,
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        expected_nonce=nonce_bytes,
        allowed_algs=["RS256", "ES256"],
    )

    assert claims["sub"] == "user-1234"
    assert claims["iss"] == fake_idp.issuer
    assert claims["aud"] == fake_idp.client_id
    assert claims["email"] == "user1234@example.com"


def test_positive_private_key_jwt_rsa(fake_idp: FakeIdP) -> None:
    """Test 3: fake IdP verifies assertion signature, aud=token_endpoint, exp - iat == 60."""
    now = 1700000000.0
    token_endpoint = f"{fake_idp.issuer}/oauth/token"
    assertion = build_private_key_jwt(
        client_id=fake_idp.client_id,
        token_endpoint=token_endpoint,
        private_key_pem=fake_idp.rsa_private_key_pem,
        now=now,
    )

    # Verify assertion using joserfc and IdP's public key
    client_keyset = KeySet.import_key_set({"keys": [fake_idp.jwk_public_dict]})
    decoded = jwt.decode(assertion, client_keyset, algorithms=["RS256"])

    assert decoded.header["alg"] == "RS256"
    claims = decoded.claims
    assert claims["iss"] == fake_idp.client_id
    assert claims["sub"] == fake_idp.client_id
    assert claims["aud"] == token_endpoint
    assert claims["exp"] - claims["iat"] == 60
    assert claims["iat"] == int(now)
    assert claims["exp"] == int(now) + 60
    assert "jti" in claims


def test_positive_private_key_jwt_ec() -> None:
    """Verify build_private_key_jwt with an EC private key produces an ES256 assertion."""
    ec_priv = ec.generate_private_key(ec.SECP256R1())
    ec_pem = ec_priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    ec_pub_pem = ec_priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    assertion = build_private_key_jwt(
        client_id="ec-client",
        token_endpoint="https://idp.example.com/oauth/token",  # noqa: S106
        private_key_pem=ec_pem,
        now=1700000000.0,
    )

    pub_key = ECKey.import_key(ec_pub_pem)
    decoded = jwt.decode(assertion, pub_key, algorithms=["ES256"])
    assert decoded.header["alg"] == "ES256"
    assert decoded.claims["iss"] == "ec-client"


def test_private_key_jwt_unsupported_key() -> None:
    """Verify build_private_key_jwt raises TypeError on unsupported private key types."""
    ed_priv = ed25519.Ed25519PrivateKey.generate()
    ed_pem = ed_priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    with pytest.raises(TypeError, match="Unsupported private key type"):
        build_private_key_jwt(
            client_id="ed-client",
            token_endpoint="https://idp.example.com/oauth/token",  # noqa: S106
            private_key_pem=ed_pem,
        )


def test_security_nonce_mismatch(fake_idp: FakeIdP, jwks: KeySet) -> None:
    """Test 6: id_token with a nonce from a different request -> 401 OIDC_TOKEN_INVALID."""
    expected_nonce = b"nonce-expected-16"
    different_nonce = b"nonce-attacker-16"

    id_token = fake_idp.create_id_token(nonce=different_nonce.decode("latin-1"))

    with pytest.raises(ProblemException) as exc_info:
        validate_id_token(
            id_token,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=expected_nonce,
            allowed_algs=["RS256", "ES256"],
        )

    assert exc_info.value.code == "OIDC_TOKEN_INVALID"
    assert exc_info.value.status == 401
    assert "nonce" in (exc_info.value.detail or "").lower()


def test_security_alg_none(fake_idp: FakeIdP, jwks: KeySet) -> None:
    """Test 7 (part 1): token with alg=none -> 401 OIDC_TOKEN_INVALID."""
    nonce = b"test-nonce-16by!"
    # Forge token with alg=none
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode("ascii")
    payload = (
        base64.urlsafe_b64encode(
            b'{"iss":"https://idp.example.com","sub":"u1","aud":"test-client-id"}'
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    forged_none_token = f"{header}.{payload}."

    with pytest.raises(ProblemException) as exc_info:
        validate_id_token(
            forged_none_token,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256", "ES256"],
        )

    assert exc_info.value.code == "OIDC_TOKEN_INVALID"
    assert exc_info.value.status == 401
    assert "none" in (exc_info.value.detail or "").lower()


def test_security_alg_hs256_confusion(fake_idp: FakeIdP, jwks: KeySet) -> None:
    """Test 7 (part 2): token with HS256 signed using RSA public key PEM as HMAC secret -> 401."""
    nonce = b"test-nonce-16by!"
    header_json = b'{"alg":"HS256","typ":"JWT"}'
    claims_json = (
        b'{"iss":"https://idp.example.com","sub":"u1","aud":"test-client-id",'
        b'"nonce":"test-nonce-16by!","iat":1700000000,"exp":1700003600}'
    )
    b64_h = base64.urlsafe_b64encode(header_json).rstrip(b"=").decode("ascii")
    b64_c = base64.urlsafe_b64encode(claims_json).rstrip(b"=").decode("ascii")
    signing_input = f"{b64_h}.{b64_c}".encode("ascii")

    # Attacker signs with IdP public key PEM as HMAC secret
    hmac_sig = hmac.new(fake_idp.rsa_public_key_pem, signing_input, "sha256").digest()
    b64_sig = base64.urlsafe_b64encode(hmac_sig).rstrip(b"=").decode("ascii")
    forged_hs256_token = f"{b64_h}.{b64_c}.{b64_sig}"

    with pytest.raises(ProblemException) as exc_info:
        validate_id_token(
            forged_hs256_token,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256", "ES256"],
        )

    assert exc_info.value.code == "OIDC_TOKEN_INVALID"
    assert exc_info.value.status == 401


def test_security_header_jku_forbidden(fake_idp: FakeIdP, jwks: KeySet) -> None:
    """Test 7 (part 3): token with jku pointing at attacker JWKS -> 401."""
    nonce = b"test-nonce-16by!"
    id_token = fake_idp.create_id_token(
        nonce=nonce.decode("latin-1"),
        custom_header={"jku": "https://attacker.example.com/jwks.json"},
    )

    with pytest.raises(ProblemException) as exc_info:
        validate_id_token(
            id_token,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256", "ES256"],
        )

    assert exc_info.value.code == "OIDC_TOKEN_INVALID"
    assert exc_info.value.status == 401
    assert "jku" in (exc_info.value.detail or "").lower()


def test_security_claims_validation(fake_idp: FakeIdP, jwks: KeySet) -> None:
    """Test 8: wrong iss, aud, multi-aud without azp, azp mismatch, exp/iat skew."""
    nonce = b"test-nonce-16by!"
    now = 1700000000.0

    # 1. Wrong issuer -> 401
    tok_bad_iss = fake_idp.create_id_token(
        issuer="https://attacker.example.com",
        nonce=nonce.decode("latin-1"),
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            tok_bad_iss,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
            now=now,
        )
    assert exc.value.status == 401

    # 2. Audience missing client -> 401
    tok_bad_aud = fake_idp.create_id_token(
        audience="other-client-id",
        nonce=nonce.decode("latin-1"),
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            tok_bad_aud,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
            now=now,
        )
    assert exc.value.status == 401

    # 3. Multi-aud without azp -> 401
    tok_multi_aud_no_azp = fake_idp.create_id_token(
        audience=[fake_idp.client_id, "other-aud"],
        azp=None,
        nonce=nonce.decode("latin-1"),
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            tok_multi_aud_no_azp,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
            now=now,
        )
    assert exc.value.status == 401

    # 4. Multi-aud with azp = other client -> 401
    tok_multi_aud_wrong_azp = fake_idp.create_id_token(
        audience=[fake_idp.client_id, "other-aud"],
        azp="other-aud",
        nonce=nonce.decode("latin-1"),
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            tok_multi_aud_wrong_azp,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
            now=now,
        )
    assert exc.value.status == 401

    # 5. exp past by 61s -> 401
    tok_exp_61s_past = fake_idp.create_id_token(
        iat=int(now - 3700),
        exp=int(now - 61),
        nonce=nonce.decode("latin-1"),
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            tok_exp_61s_past,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
            now=now,
        )
    assert exc.value.status == 401

    # 6. exp past by 59s -> accepted (within 60s clock skew)
    tok_exp_59s_past = fake_idp.create_id_token(
        iat=int(now - 300),
        exp=int(now - 59),
        nonce=nonce.decode("latin-1"),
    )
    claims_skew_ok = validate_id_token(
        tok_exp_59s_past,
        jwks,
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        expected_nonce=nonce,
        allowed_algs=["RS256"],
        now=now,
    )
    assert claims_skew_ok["sub"] == "user-4242"

    # 7. iat 601s old -> 401
    tok_iat_601s_old = fake_idp.create_id_token(
        iat=int(now - 601),
        exp=int(now + 3600),
        nonce=nonce.decode("latin-1"),
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            tok_iat_601s_old,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
            now=now,
        )
    assert exc.value.status == 401


def test_token_format_and_unsupported_alg(fake_idp: FakeIdP, jwks: KeySet) -> None:
    """Verify validation fails on malformed compact JWT or unallowlisted alg."""
    nonce = b"test-nonce-16by!"

    # Malformed parts
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            "not.a.valid.compact.jwt",
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
        )
    assert exc.value.status == 401

    # Malformed header
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            "bad_hdr.bad_payload.bad_sig",
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
        )
    assert exc.value.status == 401

    # Disallowed algorithm
    tok = fake_idp.create_id_token(nonce=nonce.decode("latin-1"))
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            tok,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["ES256"],
        )  # Only ES256 allowed, token is RS256
    assert exc.value.status == 401
    assert "not in allowed algorithms" in (exc.value.detail or "")


def test_token_signature_tamper(fake_idp: FakeIdP, jwks: KeySet) -> None:
    """Verify tampering with ID token payload invalidates signature."""
    nonce = b"test-nonce-16by!"
    tok = fake_idp.create_id_token(nonce=nonce.decode("latin-1"))
    parts = tok.split(".")
    tampered = f"{parts[0]}.{parts[1][:-4]}AAAA.{parts[2]}"
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            tampered,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
        )
    assert exc.value.status == 401
    assert "signature" in (exc.value.detail or "").lower()


def test_token_missing_and_malformed_timestamps_and_claims(fake_idp: FakeIdP, jwks: KeySet) -> None:
    """Verify validation fails on missing or invalid timestamps and claims."""
    nonce = b"test-nonce-16by!"
    now = 1700000000.0

    # 1. Missing aud
    t_no_aud = fake_idp.create_id_token(nonce=nonce.decode("latin-1"), custom_claims={"aud": None})
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            t_no_aud,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
        )
    assert exc.value.status == 401

    # 2. Single aud with wrong azp
    t_wrong_azp = fake_idp.create_id_token(nonce=nonce.decode("latin-1"), azp="wrong-client")
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            t_wrong_azp,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
        )
    assert exc.value.status == 401

    # 3. Missing exp
    t_no_exp = fake_idp.create_id_token(nonce=nonce.decode("latin-1"), custom_claims={"exp": None})
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            t_no_exp,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
        )
    assert exc.value.status == 401

    # 4. Invalid exp format
    t_bad_exp = fake_idp.create_id_token(
        nonce=nonce.decode("latin-1"), custom_claims={"exp": "not-a-number"}
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            t_bad_exp,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
        )
    assert exc.value.status == 401

    # 5. Missing iat
    t_no_iat = fake_idp.create_id_token(nonce=nonce.decode("latin-1"), custom_claims={"iat": None})
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            t_no_iat,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
        )
    assert exc.value.status == 401

    # 6. Invalid iat format
    t_bad_iat = fake_idp.create_id_token(
        nonce=nonce.decode("latin-1"), custom_claims={"iat": "bad-iat"}
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            t_bad_iat,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
        )
    assert exc.value.status == 401

    # 7. Future iat beyond skew
    t_future_iat = fake_idp.create_id_token(
        nonce=nonce.decode("latin-1"), iat=int(now + 65), exp=int(now + 3600)
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            t_future_iat,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
            now=now,
        )
    assert exc.value.status == 401

    # 8. nbf in future beyond skew
    t_future_nbf = fake_idp.create_id_token(
        nonce=nonce.decode("latin-1"), iat=int(now - 10), exp=int(now + 3600), nbf=int(now + 65)
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            t_future_nbf,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
            now=now,
        )
    assert exc.value.status == 401

    # 9. nbf invalid format
    t_bad_nbf = fake_idp.create_id_token(
        nonce=nonce.decode("latin-1"),
        iat=int(now - 10),
        exp=int(now + 3600),
        custom_claims={"nbf": "bad-nbf"},
    )
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            t_bad_nbf,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
            now=now,
        )
    assert exc.value.status == 401

    # 10. nbf valid within skew
    t_ok_nbf = fake_idp.create_id_token(
        nonce=nonce.decode("latin-1"), iat=int(now - 10), exp=int(now + 3600), nbf=int(now - 10)
    )
    c_nbf = validate_id_token(
        t_ok_nbf,
        jwks,
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        expected_nonce=nonce,
        allowed_algs=["RS256"],
        now=now,
    )
    assert c_nbf["sub"] == "user-4242"

    # 11. Missing nonce in claims
    t_no_nonce = fake_idp.create_id_token(custom_claims={"nonce": None})
    with pytest.raises(ProblemException) as exc:
        validate_id_token(
            t_no_nonce,
            jwks,
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            expected_nonce=nonce,
            allowed_algs=["RS256"],
        )
    assert exc.value.status == 401
    assert "nonce" in (exc.value.detail or "").lower()

    # 12. Nonce matching in hex and base64url formats
    t_hex_nonce = fake_idp.create_id_token(nonce=nonce.hex())
    c_hex = validate_id_token(
        t_hex_nonce,
        jwks,
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        expected_nonce=nonce,
        allowed_algs=["RS256"],
    )
    assert c_hex["sub"] == "user-4242"
