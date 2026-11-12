"""Unit tests and benchmarks for outbound secret scrubber."""

from dataclasses import asdict
import json
from pathlib import Path
import time
import pytest

from kanban.security import (
    ScrubFinding,
    ScrubResult,
    SecretKind,
    outbound_secret_scrubber,
    scrub_text,
)


@pytest.fixture
def corpus_data() -> dict[str, list[dict[str, object]]]:
    """Load test cases from json fixture corpus."""
    corpus_file = Path(__file__).parent / "corpus" / "scrubber_cases.json"
    with open(corpus_file, "r", encoding="utf-8") as f:
        data: dict[str, list[dict[str, object]]] = json.load(f)
        return data


def test_case_1_positive_sk_variants() -> None:
    """Test Case 1: Positive sk-* variants (legacy, project, anthropic)."""
    raw_secrets = [
        "sk-abc123DEF456ghi789JKL012mno345PQR",
        "sk-proj-1234567890abcdefghijklmnopqrstuvwxyzAB",
        "sk-ant-api03-abcdef123456GHIJKL7890mnopqrstUV",
        "sk-live-0123456789abcdefghijklmnopqrstuvwxyzAB",
        "sk-test-0123456789abcdefghijklmnopqrstuvwxyzAB",
    ]
    for secret in raw_secrets:
        text = f"prefix text {secret} suffix text"
        res = outbound_secret_scrubber(text)
        assert res.redacted is True
        assert res.count == 1
        assert res.text == "prefix text [REDACTED:API_KEY] suffix text"
        assert res.findings[0].kind == SecretKind.API_KEY
        assert res.findings[0].placeholder == "[REDACTED:API_KEY]"
        assert secret not in res.text
        # Test helper
        assert scrub_text(text) == res.text


def test_case_2_positive_github_and_aws() -> None:
    """Test Case 2: Positive GitHub and AWS access key IDs."""
    github_tokens = [
        "ghp_" + "a" * 36,
        "gho_" + "b" * 40,
        "ghu_" + "c" * 36,
        "ghs_" + "d" * 50,
        "ghr_" + "e" * 36,
        "github_pat_" + "f" * 22,
    ]
    for token in github_tokens:
        text = f"token: {token}"
        res = outbound_secret_scrubber(text)
        assert res.redacted is True
        assert res.count == 1
        assert res.text == "token: [REDACTED:GITHUB_TOKEN]"
        assert res.findings[0].kind == SecretKind.GITHUB_TOKEN
        assert token not in res.text

    aws_keys = [
        "AKIAIOSFODNN7EXAMPLE",
        "ASIAI44QH8DHBEXAMPLE",
    ]
    for key in aws_keys:
        text = f"aws key: {key}"
        res = outbound_secret_scrubber(text)
        assert res.redacted is True
        assert res.count == 1
        assert res.text == "aws key: [REDACTED:AWS_ACCESS_KEY]"
        assert res.findings[0].kind == SecretKind.AWS_ACCESS_KEY
        assert key not in res.text


def test_case_3_positive_and_boundary_pem_private_keys() -> None:
    """Test Case 3: Positive & boundary PEM private keys (full and truncated)."""
    full_openssh = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABlwAAAAdzc2gtcn\n"
        "NhAAAAAwEAAQAAAYEA0ABCDEF1234567890abcdefghijklmnopqrstuvwxyzAB==\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )
    full_rsa = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEogIBAAKCAQEA0ABCDEF1234567890abcdefghijklmnopqrstuvwxyzAB==\n"
        "-----END RSA PRIVATE KEY-----"
    )
    full_ec = (
        "-----BEGIN EC PRIVATE KEY-----\n"
        "MHcCAQEEIABCDEF1234567890abcdefghijklmnopqrstuvwxyzAB==\n"
        "-----END EC PRIVATE KEY-----"
    )
    full_generic = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQD0ABCDEF==\n"
        "-----END PRIVATE KEY-----"
    )
    full_pgp = (
        "-----BEGIN PGP PRIVATE KEY BLOCK-----\n"
        "lQO+BF2X==\n"
        "-----END PGP PRIVATE KEY BLOCK-----"
    )

    for pem in [full_openssh, full_rsa, full_ec, full_generic, full_pgp]:
        text = f"Config key:\n{pem}\nEnd of config."
        res = outbound_secret_scrubber(text)
        assert res.redacted is True
        assert res.count == 1
        assert res.text == "Config key:\n[REDACTED:PRIVATE_KEY]\nEnd of config."
        assert res.findings[0].kind == SecretKind.PRIVATE_KEY

    # Unclosed PEM key truncated at exactly 1,500 chars (Sparkle prefix truncation)
    long_b64 = "MIIEogIBAAKCAQEA" * 120
    truncated_pem = (f"-----BEGIN RSA PRIVATE KEY-----\n{long_b64}\n")[:1500]
    assert len(truncated_pem) == 1500
    res_trunc = outbound_secret_scrubber(truncated_pem)
    assert res_trunc.redacted is True
    assert res_trunc.count == 1
    assert res_trunc.text == "[REDACTED:PRIVATE_KEY]"
    assert "MIIE" not in res_trunc.text

    # Truncated PEM followed by normal prose
    mixed_truncated = truncated_pem + "\nNormal prose starts here."
    res_mixed = outbound_secret_scrubber(mixed_truncated)
    assert res_mixed.redacted is True
    assert res_mixed.count == 1
    assert res_mixed.text == "[REDACTED:PRIVATE_KEY]\nNormal prose starts here."
    assert "MIIE" not in res_mixed.text

    # PEM with OpenSSL headers (Proc-Type / DEK-Info)
    pem_with_headers = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "Proc-Type: 4,ENCRYPTED\n"
        "DEK-Info: AES-128-CBC,F1B2C3D4E5F6A7B8\n"
        "\n"
        "MIIEogIBAAKCAQEA0ABCDEF1234567890abcdefghijklmnopqrstuvwxyzAB==\n"
        "-----END RSA PRIVATE KEY-----"
    )
    res_hdrs = outbound_secret_scrubber(pem_with_headers)
    assert res_hdrs.redacted is True
    assert res_hdrs.text == "[REDACTED:PRIVATE_KEY]"

    # Unclosed PEM with OpenSSL headers followed by prose
    unclosed_with_hdrs = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "Proc-Type: 4,ENCRYPTED\n"
        "DEK-Info: AES-128-CBC,F1B2C3D4E5F6A7B8\n"
        "\n"
        "MIIEogIBAAKCAQEA0ABCDEF1234567890abcdefghijklmnopqrstuvwxyzAB==\n"
        "Ticket description follows here."
    )
    res_unclosed = outbound_secret_scrubber(unclosed_with_hdrs)
    assert res_unclosed.redacted is True
    assert "Ticket description follows here." in res_unclosed.text
    assert "MIIE" not in res_unclosed.text


def test_case_4_positive_bearer_jwt_and_kanban_keys() -> None:
    """Test Case 4: Positive Bearer, JWT, and kb_* keys."""
    # Bearer with JWT
    bearer_jwt = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    res1 = outbound_secret_scrubber(bearer_jwt)
    assert res1.redacted is True
    assert res1.count == 1
    assert res1.text == "Authorization: Bearer [REDACTED:BEARER_TOKEN]"
    assert res1.findings[0].kind == SecretKind.BEARER_TOKEN

    # Bearer with lowercase keyword and opaque token
    bearer_opaque = "bearer opaque_tok_1234567890abcdefghij"
    res2 = outbound_secret_scrubber(bearer_opaque)
    assert res2.redacted is True
    assert res2.count == 1
    assert res2.text == "bearer [REDACTED:BEARER_TOKEN]"
    assert res2.findings[0].kind == SecretKind.BEARER_TOKEN

    # Standalone 3-segment JWT
    standalone_jwt = "Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U in body"
    res3 = outbound_secret_scrubber(standalone_jwt)
    assert res3.redacted is True
    assert res3.count == 1
    assert res3.text == "Token: [REDACTED:JWT] in body"
    assert res3.findings[0].kind == SecretKind.JWT

    # Kanban platform keys (kb_agt_, kb_agt_eph_, kb_doc_, kb_adm_, kb_setup_)
    kb_tokens = [
        "kb_agt_0123456789abcdef",
        "kb_agt_eph_0123456789abcdef",
        "kb_doc_0123456789abcdef",
        "kb_adm_0123456789abcdef",
        "kb_setup_0123456789abcdef",
    ]
    for kb_tok in kb_tokens:
        text = f"Platform key: {kb_tok}"
        res = outbound_secret_scrubber(text)
        assert res.redacted is True
        assert res.count == 1
        assert res.text == "Platform key: [REDACTED:KANBAN_KEY]"
        assert res.findings[0].kind == SecretKind.KANBAN_KEY


def test_case_5_multi_secret_and_overlapping_spans() -> None:
    """Test Case 5: Multi-secret and overlapping span resolution."""
    raw_bearer_jwt = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    raw_ghp = "ghp_111122223333444455556666777788889999"
    raw_kb = "kb_adm_0123456789abcdef"

    paragraph = (
        f"Header `{raw_bearer_jwt}`, alongside GitHub token `{raw_ghp}` "
        f"and administration token `{raw_kb}`."
    )
    res = outbound_secret_scrubber(paragraph)
    assert res.redacted is True
    assert res.count == 3
    expected_text = (
        "Header `Bearer [REDACTED:BEARER_TOKEN]`, alongside GitHub token `[REDACTED:GITHUB_TOKEN]` "
        "and administration token `[REDACTED:KANBAN_KEY]`."
    )
    assert res.text == expected_text

    # Verify idempotency on second pass
    res_second = outbound_secret_scrubber(res.text)
    assert res_second.redacted is False
    assert res_second.count == 0
    assert res_second.text == res.text
    assert res_second.findings == ()


def test_case_6_false_positive_guard_corpus(
    corpus_data: dict[str, list[dict[str, object]]],
) -> None:
    """Test Case 6: False positive guard corpus must return redacted=False."""
    cases = corpus_data["false_positive_cases"]
    for c in cases:
        input_text = str(c["input"])
        res = outbound_secret_scrubber(input_text)
        assert res.redacted is False, f"False positive triggered on case: {c['id']}"
        assert res.count == 0
        assert res.text == input_text
        assert res.findings == ()

    # Explicit additional false-positive checks
    addl_false_positives = [
        "01965a8e-7c12-7000-8000-112233445566",
        "9f2c8b1e4d3a7c6b5e0f1a2b3c4d5e6f7a8b9c0d",
        "KAN-142",
        "KB-P2-17",
        "AKIA-12",
        "--sk-primary-button-background",
        "sk-short123",
        "task_list_item_identifier_name",
        "bearer_of_bad_news = True",
        "/home/user/kanban/security/scrubber.py",
        "https://kanban.hackedyour.info/kanban/projects/KAN/issues/142",
        (
            "-----BEGIN CERTIFICATE-----\n"
            "MIIDXTCCAkWgAwIBAgIJALabcdef1234567890==\n"
            "-----END CERTIFICATE-----"
        ),
        (
            "-----BEGIN PUBLIC KEY-----\n"
            "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0ABCDEF==\n"
            "-----END PUBLIC KEY-----"
        ),
    ]
    for text in addl_false_positives:
        res = outbound_secret_scrubber(text)
        assert res.redacted is False, f"False positive triggered on: {text}"
        assert res.count == 0
        assert res.text == text


def test_case_7_secret_non_retention_in_metadata() -> None:
    """Test Case 7: Secret non-retention in metadata (findings, repr, asdict)."""
    sample_secrets = [
        "sk-proj-1234567890abcdefghijklmnopqrstuvwxyzAB",
        "ghp_111122223333444455556666777788889999",
        "AKIAIOSFODNN7EXAMPLE",
        "kb_adm_0123456789abcdef",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    ]
    for secret in sample_secrets:
        text = f"Sample secret data: {secret}"
        res = outbound_secret_scrubber(text)
        assert res.redacted is True

        findings_repr = repr(res.findings)
        result_repr = repr(res)

        assert secret not in findings_repr, f"Secret leaked in findings repr: {secret}"
        assert (
            secret not in result_repr
        ), f"Secret leaked in ScrubResult repr: {secret}"

        for f in res.findings:
            f_dict = asdict(f)
            f_dict_str = str(f_dict)
            assert (
                secret not in f_dict_str
            ), f"Secret leaked in finding asdict: {secret}"


def test_case_8_redos_and_linear_time_boundary() -> None:
    """Test Case 8: ReDoS and linear-time boundary benchmarks."""
    # 1 MiB adversarial input containing 1,000 unclosed PEM private key blocks
    # and a long Bearer prefix
    unclosed_block = (
        "-----BEGIN RSA PRIVATE KEY-----\n" + "MIIEogIBAAKCAQEA" * 65 + "\n"
    )
    adversarial_payload = (unclosed_block * 1000) + ("Bearer " + "a" * 60000)
    assert len(adversarial_payload) >= 1_048_576

    t0 = time.perf_counter()
    res_large = outbound_secret_scrubber(adversarial_payload)
    elapsed_large_ms = (time.perf_counter() - t0) * 1000.0

    assert res_large.redacted is True
    # Must complete in < 250 ms (and typically <= 50 ms)
    assert (
        elapsed_large_ms < 250.0
    ), f"1 MiB payload took {elapsed_large_ms:.2f} ms (budget < 250 ms)"

    # 2,000-char Sparkle window benchmark (1,500 prefix + 500 suffix)
    sparkle_window = (
        "def compute_hash(payload: str) -> str:\n"
        "    # Context prefix for inline completion\n"
        + "    x = 42\n" * 70
        + "    token = 'kb_agt_0123456789abcdef'\n"
        + "    return 'done'\n"
    )[:2000]

    measurements: list[float] = []
    for _ in range(50):
        t_start = time.perf_counter()
        _ = outbound_secret_scrubber(sparkle_window)
        measurements.append((time.perf_counter() - t_start) * 1000.0)

    measurements.sort()
    median_ms = measurements[len(measurements) // 2]
    # Median must be <= 1.0 ms and single run < 5.0 ms
    assert (
        median_ms <= 1.0
    ), f"Sparkle window median latency {median_ms:.4f} ms exceeded 1.0 ms"
    assert (
        measurements[-1] < 5.0
    ), f"Sparkle window max latency {measurements[-1]:.4f} ms exceeded 5.0 ms"


def test_edge_cases_and_branch_coverage() -> None:
    """Test edge cases to guarantee >=95% branch coverage."""
    # Empty string
    assert outbound_secret_scrubber("").redacted is False
    assert outbound_secret_scrubber("").count == 0
    assert outbound_secret_scrubber("").findings == ()

    # No secrets in text
    res_clean = outbound_secret_scrubber("Hello world! Simple issue description.")
    assert res_clean.redacted is False
    assert res_clean.count == 0
    assert res_clean.findings == ()

    # Incomplete PEM header (no closing dashes or line too long)
    incomplete_pem = "-----BEGIN " + "A" * 150 + "-----"
    res_inc = outbound_secret_scrubber(incomplete_pem)
    assert res_inc.redacted is False

    # PEM with non-private-key label
    cert_text = "-----BEGIN X509 CRL-----\nMIIB...-----\n-----END X509 CRL-----"
    res_cert = outbound_secret_scrubber(cert_text)
    assert res_cert.redacted is False

    # PEM truncated with empty lines
    empty_lines_pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n\n\n\n\nprose without base64"
    )
    res_empty_lines = outbound_secret_scrubber(empty_lines_pem)
    assert res_empty_lines.redacted is True
    assert res_empty_lines.count == 1
    assert "prose without base64" in res_empty_lines.text

    # PEM with inline base64 and no newline
    inline_pem = (
        "-----BEGIN RSA PRIVATE KEY-----MIIEogIBAAKCAQEA0ABCDEF+== trailing text"
    )
    res_inline = outbound_secret_scrubber(inline_pem)
    assert res_inline.redacted is True
    assert res_inline.text == "[REDACTED:PRIVATE_KEY] trailing text"

    # PEM truncated right at end of string without body
    only_header = "-----BEGIN RSA PRIVATE KEY-----"
    res_header_only = outbound_secret_scrubber(only_header)
    assert res_header_only.redacted is True
    assert res_header_only.text == "[REDACTED:PRIVATE_KEY]"

    # sk- key that is all lowercase without digits (e.g. English words)
    non_secret_sk = "sk-this-is-an-ordinary-english-identifier-without-digits"
    res_non_sec = outbound_secret_scrubber(non_secret_sk)
    assert res_non_sec.redacted is False

    # sk- key with uppercase and lowercase (mixed-case) without digits
    mixed_sk = "sk-AbCdEfGhIjKlMnOpQrStUvWxYz"
    res_mixed = outbound_secret_scrubber(mixed_sk)
    assert res_mixed.redacted is True
    assert res_mixed.text == "[REDACTED:API_KEY]"
