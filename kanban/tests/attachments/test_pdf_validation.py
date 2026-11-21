# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and forensic tests for PDF attachment validation and active-content rejection (KAN-81)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zlib
from unittest.mock import MagicMock, patch

import pytest

from kanban.api.problems import ProblemException
from kanban.attachments.pdf import (
    MAX_DECOMPRESSED_STREAM_BYTES,
    MAX_DECOMPRESSED_TOTAL_BYTES,
    MAX_PDF_BYTES,
    _check_flate_bounds,
    _execute_subprocess,
    _run_subprocess_worker,
    check_uri_destination,
    decode_pdf_name,
    extract_and_scan_streams,
    extract_page_count,
    sanitize_and_validate_pdf,
    scan_and_validate_pdf_in_process,
)

SAMPLE_VALID_PDF = b"""%PDF-1.7
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
190
%%EOF"""


def _make_pdf_with_content(content: bytes, version: bytes = b"%PDF-1.7") -> bytes:
    """Generate minimal syntactically correct PDF document containing extra content."""
    return b"""%s
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 3 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R %s >>
endobj
xref
0 4
trailer
<< /Size 4 /Root 1 0 R >>
startxref
100
%%%%EOF""" % (version, content)


def test_decode_pdf_name_hex_sequences() -> None:
    """Verify decode_pdf_name decodes #XX hex sequences correctly."""
    assert decode_pdf_name(b"#4a#61#76#61#53#63#72#69#70#74") == b"JavaScript"
    assert decode_pdf_name(b"#4a#53") == b"JS"
    assert decode_pdf_name(b"#4c#61#75#6e#63#68") == b"Launch"
    assert decode_pdf_name(b"PlainName") == b"PlainName"
    assert decode_pdf_name(b"Name#20With#20Spaces") == b"Name With Spaces"


def test_extract_page_count_from_pages_dict_and_fallback() -> None:
    """Verify extract_page_count extracts maximum /Count or counts /Type /Page."""
    pdf_count_5 = b"""%PDF-1.4
1 0 obj
<< /Type /Pages /Count 5 >>
endobj
%%EOF"""
    assert extract_page_count(pdf_count_5) == 5

    pdf_multiple_pages = b"""%PDF-1.4
1 0 obj << /Type /Page >> endobj
2 0 obj << /Type /Page >> endobj
3 0 obj << /Type /Page >> endobj
%%EOF"""
    assert extract_page_count(pdf_multiple_pages) == 3

    assert extract_page_count(b"%PDF-1.4 empty") == 1


@pytest.mark.asyncio
async def test_valid_pdf_roundtrip_metadata() -> None:
    """Verify valid PDF returns 200/clean metadata with correct page count and sha256."""
    res = await sanitize_and_validate_pdf(SAMPLE_VALID_PDF)
    assert res.content_type == "application/pdf"
    assert res.byte_size == len(SAMPLE_VALID_PDF)
    assert res.page_count == 1
    assert len(res.blob_sha256) == 32
    assert res.clean_bytes == SAMPLE_VALID_PDF


@pytest.mark.asyncio
async def test_multi_page_pdf_page_count() -> None:
    """Verify multi-page PDF extracts verified page count."""
    doc = _make_pdf_with_content(b"")
    res = await sanitize_and_validate_pdf(doc)
    assert res.page_count == 3


@pytest.mark.asyncio
async def test_reject_javascript_active_content() -> None:
    """Verify /JS and /JavaScript dictionary keys are rejected with HTTP 422."""
    doc_js = _make_pdf_with_content(b"/JS (app.alert('pwn'))")
    with pytest.raises(ProblemException) as exc_info:
        await sanitize_and_validate_pdf(doc_js)
    assert exc_info.value.status == 422
    assert exc_info.value.code == "UNSAFE_PDF_CONTENT"
    assert "/JS" in str(exc_info.value.detail)

    doc_javascript = _make_pdf_with_content(b"/JavaScript 4 0 R")
    with pytest.raises(ProblemException) as exc_info2:
        await sanitize_and_validate_pdf(doc_javascript)
    assert exc_info2.value.status == 422
    assert "/JavaScript" in str(exc_info2.value.detail)


@pytest.mark.asyncio
async def test_reject_hex_obfuscated_active_content() -> None:
    """Verify #XX hex-encoded names (e.g. /#4a#61...) are normalized and rejected."""
    obfuscated_js = _make_pdf_with_content(b"/#4a#61#76#61#53#63#72#69#70#74 (malicious())")
    with pytest.raises(ProblemException) as exc_info:
        await sanitize_and_validate_pdf(obfuscated_js)
    assert exc_info.value.status == 422
    assert "/JavaScript" in str(exc_info.value.detail)

    obfuscated_launch = _make_pdf_with_content(b"/#4c#61#75#6e#63#68 (cmd.exe)")
    with pytest.raises(ProblemException) as exc_info2:
        await sanitize_and_validate_pdf(obfuscated_launch)
    assert exc_info2.value.status == 422
    assert "/Launch" in str(exc_info2.value.detail)


@pytest.mark.asyncio
async def test_reject_active_triggers_and_launch() -> None:
    """Verify /AA, /OpenAction, and /Launch actions are rejected."""
    for key in (b"/AA", b"/OpenAction", b"/Launch"):
        doc = _make_pdf_with_content(b"%s << >>" % key)
        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_validate_pdf(doc)
        assert exc_info.value.status == 422
        assert exc_info.value.code == "UNSAFE_PDF_CONTENT"


@pytest.mark.asyncio
async def test_reject_embedded_files_rich_media_xfa_and_encrypt() -> None:
    """Verify /EmbeddedFiles, /RichMedia, /XFA, /SubmitForm, /GoToR, /Encrypt are rejected."""
    dangerous_keys = (
        b"/EmbeddedFiles",
        b"/RichMedia",
        b"/XFA",
        b"/SubmitForm",
        b"/ImportData",
        b"/GoToR",
        b"/Encrypt",
    )
    for key in dangerous_keys:
        doc = _make_pdf_with_content(b"%s << >>" % key)
        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_validate_pdf(doc)
        assert exc_info.value.status == 422
        assert exc_info.value.code == "UNSAFE_PDF_CONTENT"


@pytest.mark.asyncio
async def test_reject_unsafe_uri_schemes() -> None:
    """Verify non-https and UNC /URI destinations are rejected."""
    unsafe_uris = (
        b"/URI (http://insecure.example.com)",
        b"/URI (file:///etc/passwd)",
        b"/URI (javascript:alert(1))",
        b"/URI (data:text/html,evil)",
        b"/URI (\\\\evil-host\\share)",
        b"/URI <687474703a2f2f6576696c2e636f6d>",  # hex for http://evil.com
    )
    for uri in unsafe_uris:
        doc = _make_pdf_with_content(uri)
        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_validate_pdf(doc)
        assert exc_info.value.status == 422
        assert exc_info.value.code == "UNSAFE_PDF_CONTENT"


@pytest.mark.asyncio
async def test_accept_safe_https_uri() -> None:
    """Verify https /URI destinations pass validation."""
    doc_https = _make_pdf_with_content(b"/URI (https://example.com/docs)")
    res = await sanitize_and_validate_pdf(doc_https)
    assert res.page_count == 3

    # Hex-encoded https://example.com
    hex_https = b"/URI <68747470733a2f2f6578616d706c652e636f6d>"
    doc_hex = _make_pdf_with_content(hex_https)
    res_hex = await sanitize_and_validate_pdf(doc_hex)
    assert res_hex.page_count == 3


@pytest.mark.asyncio
async def test_flate_stream_and_objstm_decompression() -> None:
    """Verify object streams and Flate compressed streams are decompressed and scanned."""
    # 1. Clean compressed stream passes
    clean_stream_payload = b"1 0 obj << /Type /Page >> endobj"
    compressed_clean = zlib.compress(clean_stream_payload)
    doc_stream = (
        b"%PDF-1.5\n"
        b"4 0 obj\n"
        b"<< /Type /ObjStm /Filter /FlateDecode /Length "
        + str(len(compressed_clean)).encode()
        + b" >>\nstream\n"
        + compressed_clean
        + b"\nendstream\nendobj\n"
        + SAMPLE_VALID_PDF[9:]
    )
    res = await sanitize_and_validate_pdf(doc_stream)
    assert res.content_type == "application/pdf"
    # Also verify in-process scan directly
    scan_and_validate_pdf_in_process(doc_stream)

    # 2. Compressed stream hiding /JavaScript is decompressed and caught
    hidden_js_payload = b"1 0 obj << /Type /ObjStm /JS (evil()) >> endobj"
    compressed_js = zlib.compress(hidden_js_payload)
    doc_hidden_js = (
        b"%PDF-1.5\n"
        b"4 0 obj\n"
        b"<< /Type /ObjStm /Filter /FlateDecode /Length "
        + str(len(compressed_js)).encode()
        + b" >>\nstream\n"
        + compressed_js
        + b"\nendstream\nendobj\n"
        + SAMPLE_VALID_PDF[9:]
    )
    with pytest.raises(ProblemException) as exc_info:
        await sanitize_and_validate_pdf(doc_hidden_js)
    assert exc_info.value.status == 422
    assert "/JS" in str(exc_info.value.detail)

    with pytest.raises(ProblemException) as exc_inproc:
        scan_and_validate_pdf_in_process(doc_hidden_js)
    assert exc_inproc.value.status == 422


@pytest.mark.asyncio
async def test_flate_decompression_bomb_ratio_defense() -> None:
    """Verify high-ratio Flate streams (>100x expansion) are rejected as decompression bombs."""
    bomb_raw = b"A" * 2_000_000  # 2 MB uncompressed
    compressed_bomb = zlib.compress(bomb_raw, level=9)  # ~2 KB compressed (>1000x ratio)
    assert (len(bomb_raw) / len(compressed_bomb)) > 100.0

    doc_bomb = (
        b"%PDF-1.4\n"
        b"5 0 obj\n"
        b"<< /Filter /FlateDecode /Length "
        + str(len(compressed_bomb)).encode()
        + b" >>\nstream\n"
        + compressed_bomb
        + b"\nendstream\nendobj\n"
        + SAMPLE_VALID_PDF[9:]
    )

    with pytest.raises(ProblemException) as exc_info:
        await sanitize_and_validate_pdf(doc_bomb)
    assert exc_info.value.status == 422
    assert "ratio" in str(exc_info.value.detail).lower()

    with pytest.raises(ProblemException) as exc_bomb_inproc:
        scan_and_validate_pdf_in_process(doc_bomb)
    assert exc_bomb_inproc.value.status == 422

    # Corrupt flate stream handles zlib error gracefully
    corrupted_stream = (
        b"%PDF-1.5\n"
        b"4 0 obj\n"
        b"<< /Filter /FlateDecode /Length 10 >>\nstream\n"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\nendstream\nendobj\n" + SAMPLE_VALID_PDF[9:]
    )
    scan_and_validate_pdf_in_process(corrupted_stream)


@pytest.mark.asyncio
async def test_reject_offset_shifted_polyglots_and_invalid_magic() -> None:
    """Verify strict %PDF-1. or %PDF-2. at offset 0 rejects HTML/JS polyglot prefixes."""
    # Prefix space
    with pytest.raises(ProblemException) as exc_1:
        await sanitize_and_validate_pdf(b" " + SAMPLE_VALID_PDF)
    assert exc_1.value.status == 422

    # HTML polyglot prefix
    with pytest.raises(ProblemException) as exc_2:
        await sanitize_and_validate_pdf(b"<html>" + SAMPLE_VALID_PDF)
    assert exc_2.value.status == 422

    # Invalid header
    with pytest.raises(ProblemException) as exc_3:
        await sanitize_and_validate_pdf(b"%DOC-1.4\n1 0 obj\n%%EOF")
    assert exc_3.value.status == 422

    # Empty
    with pytest.raises(ProblemException) as exc_4:
        await sanitize_and_validate_pdf(b"")
    assert exc_4.value.status == 422


@pytest.mark.asyncio
async def test_reject_payload_exceeding_25_mib() -> None:
    """Verify payload > 25 MiB raises HTTP 413 PAYLOAD_TOO_LARGE."""
    oversized = b"%PDF-1.4\n" + b"X" * (MAX_PDF_BYTES + 10)
    with pytest.raises(ProblemException) as exc_info:
        await sanitize_and_validate_pdf(oversized)
    assert exc_info.value.status == 413
    assert exc_info.value.code == "PAYLOAD_TOO_LARGE"


def test_scan_and_validate_pdf_in_process_direct() -> None:
    """Verify in-process scanner executes cleanly directly."""
    page_count, digest = scan_and_validate_pdf_in_process(SAMPLE_VALID_PDF)
    assert page_count == 1
    assert len(digest) == 32


def test_subprocess_cli_worker_execution() -> None:
    """Verify python -m kanban.attachments.pdf child worker stdin/stdout protocol."""
    # Successful execution
    proc = subprocess.run(
        [sys.executable, "-m", "kanban.attachments.pdf"],
        input=SAMPLE_VALID_PDF,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert b'"status": "ok"' in proc.stdout
    assert b'"page_count": 1' in proc.stdout

    # Failure execution on malicious active content
    malicious_pdf = _make_pdf_with_content(b"/JS (alert(1))")
    proc_err = subprocess.run(
        [sys.executable, "-m", "kanban.attachments.pdf"],
        input=malicious_pdf,
        capture_output=True,
        check=False,
    )
    assert proc_err.returncode == 2
    assert b'"status": "error"' in proc_err.stdout
    assert b'"code": "UNSAFE_PDF_CONTENT"' in proc_err.stdout


def test_in_process_scan_rejects_active_content_and_polyglots() -> None:
    """Verify in-process structural scanner rejects all active keys and bad headers."""
    # Polyglot / bad header
    with pytest.raises(ProblemException) as exc_head:
        scan_and_validate_pdf_in_process(b"%INVALID-HEADER")
    assert exc_head.value.code == "UNSAFE_PDF_CONTENT"

    # Empty payload
    with pytest.raises(ProblemException) as exc_empty:
        scan_and_validate_pdf_in_process(b"")
    assert exc_empty.value.code == "UNSAFE_PDF_CONTENT"

    # Active content keys
    active_keys = (
        b"/JS",
        b"/JavaScript",
        b"/AA",
        b"/OpenAction",
        b"/Launch",
        b"/EmbeddedFiles",
        b"/RichMedia",
        b"/XFA",
        b"/SubmitForm",
        b"/ImportData",
        b"/GoToR",
        b"/Encrypt",
    )
    for key in active_keys:
        bad_doc = _make_pdf_with_content(b"%s << >>" % key)
        with pytest.raises(ProblemException) as exc_key:
            scan_and_validate_pdf_in_process(bad_doc)
        assert exc_key.value.code == "UNSAFE_PDF_CONTENT"

    # Oversized payload
    with pytest.raises(ProblemException) as exc_large:
        scan_and_validate_pdf_in_process(b"%PDF-1.4\n" + b"X" * (MAX_PDF_BYTES + 10))
    assert exc_large.value.code == "PAYLOAD_TOO_LARGE"


def test_check_uri_destination_edge_cases() -> None:
    """Verify check_uri_destination rejects malformed hex and accepts bare https."""
    # Malformed hex in <...>
    with pytest.raises(ProblemException) as exc_hex:
        check_uri_destination(b"<invalid_hex>")
    assert exc_hex.value.code == "UNSAFE_PDF_CONTENT"
    assert "Malformed hex-encoded" in str(exc_hex.value.detail)

    # Parens format passes
    check_uri_destination(b"(https://example.com/spec)")

    # Bare https (no parens) passes
    check_uri_destination(b"https://example.com/spec")

    # Bare non-https fails
    with pytest.raises(ProblemException) as exc_bare:
        check_uri_destination(b"ftp://example.com/spec")
    assert exc_bare.value.code == "UNSAFE_PDF_CONTENT"


def test_flate_bounds_checks() -> None:
    """Verify _check_flate_bounds enforces stream size, total payload size, and expansion ratio."""
    # Stream too large
    with pytest.raises(ProblemException) as exc_stream:
        _check_flate_bounds(MAX_DECOMPRESSED_STREAM_BYTES + 1, 100, 100)
    assert exc_stream.value.code == "UNSAFE_PDF_CONTENT"
    assert "50 MiB" in str(exc_stream.value.detail)

    # Total payload too large
    with pytest.raises(ProblemException) as exc_total:
        _check_flate_bounds(100, MAX_DECOMPRESSED_TOTAL_BYTES + 1, 100)
    assert exc_total.value.code == "UNSAFE_PDF_CONTENT"
    assert "100 MiB" in str(exc_total.value.detail)

    # Normal bounds pass
    _check_flate_bounds(1000, 2000, 100)


def test_extract_and_scan_streams_max_objects_cap() -> None:
    """Verify extract_and_scan_streams enforces MAX_PDF_OBJECTS limit."""
    mock_pdf = b"%PDF-1.4\n"
    # Create stream block that exceeds 50,000 objects
    with patch("kanban.attachments.pdf.MAX_PDF_OBJECTS", 2):
        doc = (
            mock_pdf
            + b"1 0 obj << >> stream\nABC\nendstream endobj\n"
            + b"2 0 obj << >> stream\nDEF\nendstream endobj\n"
            + b"3 0 obj << >> stream\nGHI\nendstream endobj\n"
        )
        with pytest.raises(ProblemException) as exc_obj:
            extract_and_scan_streams(doc)
        assert exc_obj.value.code == "UNSAFE_PDF_CONTENT"
        assert "maximum allowed object count" in str(exc_obj.value.detail)


def test_execute_subprocess_failure_modes() -> None:
    """Verify _execute_subprocess handles timeout, empty output, and invalid JSON."""
    # Timeout
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["test"], timeout=3.0)):
        with pytest.raises(ProblemException) as exc_to:
            _execute_subprocess(SAMPLE_VALID_PDF)
        assert exc_to.value.code == "UNSAFE_PDF_CONTENT"
        assert "timed out" in str(exc_to.value.detail)

    # Empty stdout with stderr
    mock_proc_empty = MagicMock(stdout=b"", stderr=b"fatal worker error")
    with patch("subprocess.run", return_value=mock_proc_empty):
        with pytest.raises(ProblemException) as exc_empty:
            _execute_subprocess(SAMPLE_VALID_PDF)
        assert exc_empty.value.code == "UNSAFE_PDF_CONTENT"
        assert "fatal worker error" in str(exc_empty.value.detail)

    # Invalid JSON
    mock_proc_bad_json = MagicMock(stdout=b"NOT_JSON", stderr=b"")
    with patch("subprocess.run", return_value=mock_proc_bad_json):
        with pytest.raises(ProblemException) as exc_json:
            _execute_subprocess(SAMPLE_VALID_PDF)
        assert exc_json.value.code == "UNSAFE_PDF_CONTENT"
        assert "Failed to parse" in str(exc_json.value.detail)

    # Non-dictionary JSON
    mock_proc_list_json = MagicMock(stdout=b"[1, 2, 3]", stderr=b"")
    with patch("subprocess.run", return_value=mock_proc_list_json):
        with pytest.raises(ProblemException) as exc_dict:
            _execute_subprocess(SAMPLE_VALID_PDF)
        assert exc_dict.value.code == "UNSAFE_PDF_CONTENT"
        assert "not a dictionary" in str(exc_dict.value.detail)


@patch("kanban.attachments.pdf.resource.setrlimit")
def test_run_subprocess_worker_direct(mock_setrlimit: MagicMock) -> None:
    """Verify _run_subprocess_worker handles success, ProblemException, and unhandled errors."""
    mock_setrlimit.side_effect = OSError("permission denied")
    # Success branch
    stdin_mock = io.BytesIO(SAMPLE_VALID_PDF)
    stdout_mock = io.StringIO()
    with (
        patch("sys.stdin", io.TextIOWrapper(stdin_mock)),
        patch("sys.stdout", stdout_mock),
        pytest.raises(SystemExit) as exit_ok,
    ):
        _run_subprocess_worker()
    assert exit_ok.value.code == 0
    res_ok = json.loads(stdout_mock.getvalue())
    assert res_ok["status"] == "ok"
    assert res_ok["page_count"] == 1

    # ProblemException branch
    mock_setrlimit.side_effect = None
    bad_pdf = _make_pdf_with_content(b"/JS (alert(1))")
    stdin_err = io.BytesIO(bad_pdf)
    stdout_err = io.StringIO()
    with (
        patch("sys.stdin", io.TextIOWrapper(stdin_err)),
        patch("sys.stdout", stdout_err),
        pytest.raises(SystemExit) as exit_err,
    ):
        _run_subprocess_worker()
    assert exit_err.value.code == 2
    res_err = json.loads(stdout_err.getvalue())
    assert res_err["status"] == "error"
    assert res_err["code"] == "UNSAFE_PDF_CONTENT"

    # Unexpected exception branch
    stdin_fatal = io.BytesIO(SAMPLE_VALID_PDF)
    stdout_fatal = io.StringIO()
    with (
        patch("sys.stdin", io.TextIOWrapper(stdin_fatal)),
        patch("sys.stdout", stdout_fatal),
        patch(
            "kanban.attachments.pdf.scan_and_validate_pdf_in_process",
            side_effect=RuntimeError("simulated crash"),
        ),
        pytest.raises(SystemExit) as exit_fatal,
    ):
        _run_subprocess_worker()
    assert exit_fatal.value.code == 2
    res_fatal = json.loads(stdout_fatal.getvalue())
    assert res_fatal["status"] == "error"
    assert "simulated crash" in res_fatal["detail"]
