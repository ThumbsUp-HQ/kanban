# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Forensic and unit tests for POSIX resource limits on PDF active-content sanitizer (KAN-327)."""

from __future__ import annotations

import io
import json
import signal
import sys
import zlib
from unittest.mock import MagicMock, call, patch

import pytest

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]

from kanban.api.problems import ProblemException
from kanban.attachments.pdf import (
    DEFAULT_AS_LIMIT_BYTES,
    DEFAULT_CORE_LIMIT_BYTES,
    DEFAULT_CPU_LIMIT_SECONDS,
    DEFAULT_FSIZE_LIMIT_BYTES,
    DEFAULT_NOFILE_LIMIT,
    _decompress_and_scan_single_flate_stream,
    _execute_subprocess,
    _run_subprocess_worker,
    _set_posix_limits,
    sanitize_and_validate_pdf,
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


def test_set_posix_limits_sets_all_expected_rlimits() -> None:
    """Verify _set_posix_limits sets RLIMIT_AS, CPU, FSIZE, NOFILE, and CORE limits."""
    if resource is None:
        pytest.skip("resource module not available on this platform")

    with patch.object(resource, "setrlimit") as mock_setrlimit:
        _set_posix_limits()

        expected_calls = []
        if hasattr(resource, "RLIMIT_AS"):
            expected_calls.append(
                call(resource.RLIMIT_AS, (DEFAULT_AS_LIMIT_BYTES, DEFAULT_AS_LIMIT_BYTES))
            )
        if hasattr(resource, "RLIMIT_CPU"):
            expected_calls.append(
                call(resource.RLIMIT_CPU, (DEFAULT_CPU_LIMIT_SECONDS, DEFAULT_CPU_LIMIT_SECONDS))
            )
        if hasattr(resource, "RLIMIT_FSIZE"):
            expected_calls.append(
                call(
                    resource.RLIMIT_FSIZE,
                    (DEFAULT_FSIZE_LIMIT_BYTES, DEFAULT_FSIZE_LIMIT_BYTES),
                )
            )
        if hasattr(resource, "RLIMIT_NOFILE"):
            expected_calls.append(
                call(resource.RLIMIT_NOFILE, (DEFAULT_NOFILE_LIMIT, DEFAULT_NOFILE_LIMIT))
            )
        if hasattr(resource, "RLIMIT_CORE"):
            expected_calls.append(
                call(resource.RLIMIT_CORE, (DEFAULT_CORE_LIMIT_BYTES, DEFAULT_CORE_LIMIT_BYTES))
            )

        mock_setrlimit.assert_has_calls(expected_calls, any_order=False)


def test_set_posix_limits_custom_arguments() -> None:
    """Verify _set_posix_limits respects custom limit parameters."""
    if resource is None:
        pytest.skip("resource module not available on this platform")

    with patch.object(resource, "setrlimit") as mock_setrlimit:
        _set_posix_limits(
            as_limit_bytes=256 * 1024 * 1024,
            cpu_limit_seconds=10,
            fsize_limit_bytes=1024,
            nofile_limit=128,
        )

        expected_calls = []
        if hasattr(resource, "RLIMIT_AS"):
            expected_calls.append(call(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024)))
        if hasattr(resource, "RLIMIT_CPU"):
            expected_calls.append(call(resource.RLIMIT_CPU, (10, 10)))
        if hasattr(resource, "RLIMIT_FSIZE"):
            expected_calls.append(call(resource.RLIMIT_FSIZE, (1024, 1024)))
        if hasattr(resource, "RLIMIT_NOFILE"):
            expected_calls.append(call(resource.RLIMIT_NOFILE, (128, 128)))
        if hasattr(resource, "RLIMIT_CORE"):
            expected_calls.append(call(resource.RLIMIT_CORE, (0, 0)))

        mock_setrlimit.assert_has_calls(expected_calls, any_order=False)


def test_set_posix_limits_handles_exceptions_gracefully() -> None:
    """Verify _set_posix_limits swallows OSError and ValueError gracefully without aborting."""
    if resource is None:
        pytest.skip("resource module not available on this platform")

    with patch.object(resource, "setrlimit", side_effect=OSError("Operation not permitted")):
        _set_posix_limits()

    with patch.object(resource, "setrlimit", side_effect=ValueError("Invalid limit value")):
        _set_posix_limits()


def test_set_posix_limits_when_resource_module_is_none() -> None:
    """Verify _set_posix_limits returns silently when resource is None."""
    with patch("kanban.attachments.pdf.resource", None):
        _set_posix_limits()


def test_execute_subprocess_wires_default_preexec_fn() -> None:
    """Verify _execute_subprocess supplies _set_posix_limits as preexec_fn on POSIX systems."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    payload = json.dumps({"status": "ok", "page_count": 1, "sha256": "aabb"}).encode()
    mock_proc.stdout = payload
    mock_proc.stderr = b""

    with patch("kanban.attachments.pdf.subprocess.run", return_value=mock_proc) as mock_run:
        result = _execute_subprocess(SAMPLE_VALID_PDF)
        assert result.get("status") == "ok"
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        if sys.platform != "win32":
            assert kwargs.get("preexec_fn") == _set_posix_limits
        else:
            assert kwargs.get("preexec_fn") is None


def test_execute_subprocess_accepts_custom_preexec_fn() -> None:
    """Verify _execute_subprocess uses an explicitly provided preexec_fn callable."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    payload = json.dumps({"status": "ok", "page_count": 1, "sha256": "aabb"}).encode()
    mock_proc.stdout = payload
    mock_proc.stderr = b""

    custom_called = False

    def custom_preexec() -> None:
        nonlocal custom_called
        custom_called = True

    with patch("kanban.attachments.pdf.subprocess.run", return_value=mock_proc) as mock_run:
        result = _execute_subprocess(SAMPLE_VALID_PDF, preexec_fn=custom_preexec)
        assert result.get("status") == "ok"
        _, kwargs = mock_run.call_args
        assert kwargs.get("preexec_fn") == custom_preexec


def test_execute_subprocess_terminated_by_sigxcpu() -> None:
    """Verify _execute_subprocess handles child killed by SIGXCPU (CPU time limit exceeded)."""
    mock_proc = MagicMock()
    mock_proc.returncode = -int(signal.SIGXCPU)
    mock_proc.stdout = b""
    mock_proc.stderr = b""

    with patch("kanban.attachments.pdf.subprocess.run", return_value=mock_proc):
        with pytest.raises(ProblemException) as exc_info:
            _execute_subprocess(SAMPLE_VALID_PDF)

        assert exc_info.value.status == 422
        assert exc_info.value.code == "UNSAFE_PDF_CONTENT"
        assert f"signal {int(signal.SIGXCPU)}" in str(exc_info.value.detail)


def test_execute_subprocess_terminated_by_sigkill() -> None:
    """Verify _execute_subprocess handles child killed by SIGKILL (memory ceiling / OOM)."""
    mock_proc = MagicMock()
    mock_proc.returncode = -int(signal.SIGKILL)
    mock_proc.stdout = b""
    mock_proc.stderr = b""

    with patch("kanban.attachments.pdf.subprocess.run", return_value=mock_proc):
        with pytest.raises(ProblemException) as exc_info:
            _execute_subprocess(SAMPLE_VALID_PDF)

        assert exc_info.value.status == 422
        assert exc_info.value.code == "UNSAFE_PDF_CONTENT"
        assert f"signal {int(signal.SIGKILL)}" in str(exc_info.value.detail)


def test_run_subprocess_worker_calls_set_posix_limits() -> None:
    """Verify _run_subprocess_worker invokes _set_posix_limits before reading stdin."""
    with (
        patch("kanban.attachments.pdf._set_posix_limits") as mock_limits,
        patch("sys.stdin", io.TextIOWrapper(io.BytesIO(SAMPLE_VALID_PDF))),
        patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
        pytest.raises(SystemExit) as exc_info,
    ):
        _run_subprocess_worker()

    assert exc_info.value.code == 0
    mock_limits.assert_called_once()
    payload = json.loads(mock_stdout.getvalue())
    assert payload.get("status") == "ok"
    assert payload.get("page_count") == 1


@pytest.mark.asyncio
async def test_valid_pdf_end_to_end_with_posix_resource_limits() -> None:
    """Integration: sanitize_and_validate_pdf executes subprocess with live POSIX limits."""
    result = await sanitize_and_validate_pdf(SAMPLE_VALID_PDF)
    assert result.content_type == "application/pdf"
    assert result.byte_size == len(SAMPLE_VALID_PDF)
    assert result.page_count == 1
    assert len(result.blob_sha256) == 32


def test_set_posix_limits_partial_resource_attributes() -> None:
    """Verify _set_posix_limits handles resource modules lacking some RLIMIT constants."""

    class DummyResource:
        pass

    with patch("kanban.attachments.pdf.resource", DummyResource()):
        _set_posix_limits()


def test_flate_flush_decompression_error() -> None:
    """Verify decompression handles error on flush."""
    mock_decomp = MagicMock()
    mock_decomp.decompress.return_value = b""
    mock_decomp.flush.side_effect = zlib.error("corrupted flush")

    with patch("zlib.decompressobj", return_value=mock_decomp):
        with pytest.raises(ProblemException) as exc_info:
            _decompress_and_scan_single_flate_stream(b"dummy", 0)
        assert exc_info.value.code == "UNSAFE_PDF_CONTENT"
        assert "Flate decompression flush error" in str(exc_info.value.detail)
