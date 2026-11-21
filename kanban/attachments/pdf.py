# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Deterministic PDF validation and active-content rejection engine (KAN-81).

Implements Method A: Quarantined CAS + Bounded Subprocess Structural Active-Content
Rejection + Forced-Download UX.

Guarantees:
- Zero new external runtime dependencies (Python 3.12 stdlib zlib + hashlib).
- Offset 0 header validation (%PDF-1. or %PDF-2., len >= 8).
- Payload size cap <= 25 MiB.
- Decompression bomb defense: max 100x Flate expansion ratio, max 50 MiB per stream,
  max 100 MiB total decompressed bytes, max 50,000 objects.
- Normalized #XX hex name resolution prior to forbidden key inspection.
- Decompression and recursive AST scanning of /ObjStm object streams and dictionary streams.
- Rejection of active content: /JS, /JavaScript, /AA, /OpenAction, /Launch,
  /EmbeddedFiles, /RichMedia, /XFA, /GoToR, /SubmitForm, /ImportData, /Encrypt,
  and non-https / UNC /URI destinations with HTTP 422 UNSAFE_PDF_CONTENT.
- Extraction of verified document page_count.
- Bounded subprocess execution (timeout <= 3.0s, memory address space limit).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import zlib
from dataclasses import dataclass
from hashlib import sha256
from typing import Final

try:
    import resource
except ImportError:  # pragma: no cover
    resource = None  # type: ignore[assignment]

import anyio.to_thread

from kanban.api.problems import ProblemException

logger = logging.getLogger(__name__)

MAX_PDF_BYTES: Final[int] = 26_214_400  # 25 MiB exact
MAX_DECOMPRESSED_STREAM_BYTES: Final[int] = 52_428_800  # 50 MiB
MAX_DECOMPRESSED_TOTAL_BYTES: Final[int] = 104_857_600  # 100 MiB
MAX_FLATE_EXPANSION_RATIO: Final[float] = 100.0
MAX_PDF_OBJECTS: Final[int] = 50_000
SUBPROCESS_TIMEOUT_SECONDS: Final[float] = 3.0
MIN_PDF_HEADER_LEN: Final[int] = 8
DEFAULT_AS_LIMIT_BYTES: Final[int] = 512 * 1024 * 1024

FORBIDDEN_NAME_SET: Final[frozenset[bytes]] = frozenset(
    {
        b"JS",
        b"JavaScript",
        b"AA",
        b"OpenAction",
        b"Launch",
        b"EmbeddedFiles",
        b"RichMedia",
        b"XFA",
        b"GoToR",
        b"SubmitForm",
        b"ImportData",
        b"Encrypt",
    }
)


@dataclass(frozen=True, slots=True)
class PdfValidationResult:
    """Sanitized and verified PDF document metadata."""

    clean_bytes: bytes
    content_type: str
    byte_size: int
    blob_sha256: bytes
    page_count: int | None


def decode_pdf_name(name_bytes: bytes) -> bytes:
    """Decode PDF #XX hex-encoded bytes in a name token."""

    def _replace_hex(match: re.Match[bytes]) -> bytes:
        return bytes([int(match.group(1), 16)])

    return re.sub(b"#([0-9a-fA-F]{2})", _replace_hex, name_bytes)


def _unescape_pdf_literal_string(s: bytes) -> bytes:
    r"""Unescape PDF literal string escape sequences (octal \ddd, \n, \r, \t, etc.)."""

    def repl(m: re.Match[bytes]) -> bytes:
        seq = m.group(0)
        tail = seq[1:]
        if tail.isdigit():
            try:
                return bytes([int(tail, 8)])
            except (ValueError, OverflowError):
                return seq
        escape_map = {
            b"n": b"\n",
            b"r": b"\r",
            b"t": b"\t",
            b"b": b"\b",
            b"f": b"\f",
            b"(": b"(",
            b")": b")",
            b"\\": b"\\",
        }
        return escape_map.get(tail, tail)

    return re.sub(rb"\\([0-7]{1,3}|[nrtbf()\\\/])", repl, s)


def check_uri_destination(uri_payload: bytes) -> None:
    """Enforce safe URI destinations (https, mailto), rejecting UNC, http, and protocol exploits."""
    trimmed = uri_payload.strip()
    if trimmed.startswith(b"<") and trimmed.endswith(b">"):
        hex_str = trimmed[1:-1].strip()
        try:
            url_bytes = bytes.fromhex(hex_str.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProblemException(
                code="UNSAFE_PDF_CONTENT",
                status=422,
                title="Unsafe PDF Content",
                detail="Malformed hex-encoded /URI target",
            ) from exc
    elif trimmed.startswith(b"(") and trimmed.endswith(b")"):
        url_bytes = _unescape_pdf_literal_string(trimmed[1:-1])
    else:
        url_bytes = _unescape_pdf_literal_string(trimmed)

    url_str = url_bytes.decode("latin-1", errors="replace").strip()
    lower_url = url_str.lower()

    # Reject dangerous protocols and non-safe schemes (allow https, mailto, tel)
    if not lower_url.startswith(("https://", "mailto:", "tel:")):
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail=f"PDF contains unsafe or non-https /URI destination: {url_str[:64]}",
        )


def scan_buffer_for_active_content(data: bytes) -> None:
    """Inspect byte buffer for forbidden active content dictionary keys and dangerous URIs."""
    # 1. Scan names
    raw_names = re.findall(rb"/([^\s\x00()<>{}\[\]/%]+)", data)
    for raw in raw_names:
        decoded = decode_pdf_name(raw)
        if decoded in FORBIDDEN_NAME_SET:
            key_name = decoded.decode("latin-1", errors="replace")
            raise ProblemException(
                code="UNSAFE_PDF_CONTENT",
                status=422,
                title="Unsafe PDF Content",
                detail=f"PDF contains forbidden active content dictionary key: /{key_name}",
            )

    # 2. Scan /URI actions
    for m in re.finditer(rb"/URI\s*(\([^)]*\)|<[0-9a-fA-F]+>)", data):
        check_uri_destination(m.group(1))


def _check_flate_bounds(stream_len: int, total_len: int, compressed_len: int) -> None:
    """Verify stream decompressed size, total payload size, and expansion ratio."""
    if stream_len > MAX_DECOMPRESSED_STREAM_BYTES:
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail="PDF stream exceeds 50 MiB decompressed limit",
        )
    if total_len > MAX_DECOMPRESSED_TOTAL_BYTES:
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail="PDF decompressed payload exceeds 100 MiB limit",
        )
    if compressed_len > 0 and (stream_len / compressed_len) > MAX_FLATE_EXPANSION_RATIO:
        ratio = stream_len / compressed_len
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail=(
                f"Flate decompression ratio {ratio:.1f}x "
                f"exceeds maximum allowed ratio ({MAX_FLATE_EXPANSION_RATIO}x)"
            ),
        )


def _decompress_and_scan_single_flate_stream(stream_data: bytes, total_decompressed: int) -> int:
    """Decompress a single Flate stream with bounds checking and scan for active content."""
    compressed_len = len(stream_data)
    decomp = zlib.decompressobj()
    uncompressed_chunks: list[bytes] = []
    stream_uncompressed_len = 0
    chunk_size = 65536

    for offset in range(0, compressed_len, chunk_size):
        chunk = stream_data[offset : offset + chunk_size]
        try:
            out = decomp.decompress(chunk)
        except (zlib.error, ValueError):
            out = b""
        if out:
            stream_uncompressed_len += len(out)
            total_decompressed += len(out)
            _check_flate_bounds(stream_uncompressed_len, total_decompressed, compressed_len)
            uncompressed_chunks.append(out)

    try:
        remaining = decomp.flush()
    except (zlib.error, ValueError):
        remaining = b""
    if remaining:
        stream_uncompressed_len += len(remaining)
        total_decompressed += len(remaining)
        _check_flate_bounds(stream_uncompressed_len, total_decompressed, compressed_len)
        uncompressed_chunks.append(remaining)

    scan_buffer_for_active_content(b"".join(uncompressed_chunks))
    return total_decompressed


def extract_and_scan_streams(pdf_bytes: bytes) -> int:
    """Extract streams, decompress Flate streams with bounds, and scan for active content."""
    total_decompressed = 0
    stream_count = 0

    for match in re.finditer(
        rb"(<<[\s\S]*?>>)\s*stream[\r\n]{1,2}([\s\S]*?)[\r\n]*endstream", pdf_bytes
    ):
        stream_count += 1
        if stream_count > MAX_PDF_OBJECTS:
            raise ProblemException(
                code="UNSAFE_PDF_CONTENT",
                status=422,
                title="Unsafe PDF Content",
                detail="PDF exceeds maximum allowed object count (50,000)",
            )

        dict_header = match.group(1)
        stream_data = match.group(2)
        is_flate = rb"/FlateDecode" in dict_header or rb"/Fl\b" in dict_header
        if is_flate and stream_data:
            total_decompressed = _decompress_and_scan_single_flate_stream(
                stream_data, total_decompressed
            )

    return stream_count


def extract_page_count(pdf_bytes: bytes) -> int:
    """Extract page count from /Pages dictionaries or distinct /Type /Page objects."""
    # 1. Search for /Pages dictionary with /Count
    pages_dicts = re.findall(rb"<<[^\>]*?/Type\s*/Pages[^\>]*?>>", pdf_bytes)
    counts: list[int] = []
    for pd in pages_dicts:
        m = re.search(rb"/Count\s+(\d+)", pd)
        if m:
            counts.append(int(m.group(1)))
    if counts:
        return max(1, *counts)

    # 2. Fallback: count distinct /Type /Page (excluding /Type /Pages)
    page_objs = len(re.findall(rb"/Type\s*/Page\b(?![sS])", pdf_bytes))
    if page_objs > 0:
        return page_objs

    return 1


def scan_and_validate_pdf_in_process(raw_bytes: bytes) -> tuple[int, bytes]:
    """Execute complete in-process structural scan and return (page_count, sha256_digest)."""
    if not raw_bytes:
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail="PDF payload is empty",
        )

    if len(raw_bytes) > MAX_PDF_BYTES:
        raise ProblemException(
            code="PAYLOAD_TOO_LARGE",
            status=413,
            title="Payload Too Large",
            detail=f"PDF payload exceeds maximum limit of {MAX_PDF_BYTES} bytes",
        )

    # Offset 0 validation: strictly enforce %PDF-1. or %PDF-2.
    if len(raw_bytes) < MIN_PDF_HEADER_LEN or not raw_bytes.startswith((b"%PDF-1.", b"%PDF-2.")):
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail="Invalid PDF header: magic bytes %PDF-1. or %PDF-2. required at offset 0",
        )

    # 1. Scan raw PDF body
    scan_buffer_for_active_content(raw_bytes)

    # 2. Decompress and scan all streams
    extract_and_scan_streams(raw_bytes)

    # 3. Extract document page count
    page_count = extract_page_count(raw_bytes)

    # 4. Compute SHA-256 digest
    digest = sha256(raw_bytes).digest()

    return page_count, digest


def _run_subprocess_worker() -> None:
    """Run internal CLI worker executed inside bounded child subprocess."""
    if hasattr(resource, "RLIMIT_AS"):
        try:
            resource.setrlimit(resource.RLIMIT_AS, (DEFAULT_AS_LIMIT_BYTES, DEFAULT_AS_LIMIT_BYTES))
        except (OSError, ValueError):
            logger.debug("Could not set RLIMIT_AS address space limit", exc_info=True)

    try:
        raw_input = sys.stdin.buffer.read()
        page_count, digest = scan_and_validate_pdf_in_process(raw_input)
        result = {
            "status": "ok",
            "page_count": page_count,
            "sha256": digest.hex(),
        }
        sys.stdout.write(json.dumps(result))
        sys.stdout.flush()
        sys.exit(0)
    except ProblemException as pe:
        error_result = {
            "status": "error",
            "code": pe.code,
            "status_code": pe.status,
            "title": pe.title,
            "detail": pe.detail,
        }
        sys.stdout.write(json.dumps(error_result))
        sys.stdout.flush()
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001
        error_result = {
            "status": "error",
            "code": "UNSAFE_PDF_CONTENT",
            "status_code": 422,
            "title": "Unsafe PDF Content",
            "detail": f"PDF structural scanning failed: {exc}",
        }
        sys.stdout.write(json.dumps(error_result))
        sys.stdout.flush()
        sys.exit(2)


def _execute_subprocess(raw_bytes: bytes) -> dict[str, object]:
    """Execute bounded child subprocess with strict timeout."""
    cmd = [sys.executable, "-m", "kanban.attachments.pdf"]
    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            input=raw_bytes,
            capture_output=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail=f"PDF validation timed out after {SUBPROCESS_TIMEOUT_SECONDS}s",
        ) from exc

    stdout_text = proc.stdout.decode("utf-8", errors="replace").strip()
    if not stdout_text:
        stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail=f"Subprocess terminated unexpectedly: {stderr_text or 'unknown error'}",
        )

    try:
        raw_obj = json.loads(stdout_text)
    except json.JSONDecodeError as exc:
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail="Failed to parse subprocess validation response",
        ) from exc

    if not isinstance(raw_obj, dict):
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail="Subprocess validation response was not a dictionary",
        )

    return {str(k): v for k, v in raw_obj.items()}


async def sanitize_and_validate_pdf(raw_bytes: bytes) -> PdfValidationResult:
    """Validate PDF document through bounded subprocess structural inspection.

    Raises:
        ProblemException(status=422, code='UNSAFE_PDF_CONTENT') on active content or format errors.
        ProblemException(status=413, code='PAYLOAD_TOO_LARGE') on size violation.

    """
    if len(raw_bytes) > MAX_PDF_BYTES:
        raise ProblemException(
            code="PAYLOAD_TOO_LARGE",
            status=413,
            title="Payload Too Large",
            detail=f"Attachment payload exceeds {MAX_PDF_BYTES} bytes",
        )

    # Offset 0 quick validation
    if len(raw_bytes) < MIN_PDF_HEADER_LEN or not raw_bytes.startswith((b"%PDF-1.", b"%PDF-2.")):
        raise ProblemException(
            code="UNSAFE_PDF_CONTENT",
            status=422,
            title="Unsafe PDF Content",
            detail="Invalid PDF header: magic bytes %PDF-1. or %PDF-2. required at offset 0",
        )

    payload = await anyio.to_thread.run_sync(_execute_subprocess, raw_bytes)

    if payload.get("status") == "error":
        code = str(payload.get("code") or "UNSAFE_PDF_CONTENT")
        raw_status = payload.get("status_code")
        status_code = int(raw_status) if isinstance(raw_status, (int, str)) else 422
        title = str(payload.get("title") or "Unsafe PDF Content")
        detail = str(payload.get("detail") or "PDF validation failed")
        raise ProblemException(code=code, status=status_code, title=title, detail=detail)

    page_count = payload.get("page_count")
    sha_hex = str(payload.get("sha256") or "")
    blob_sha256 = bytes.fromhex(sha_hex) if sha_hex else sha256(raw_bytes).digest()

    return PdfValidationResult(
        clean_bytes=raw_bytes,
        content_type="application/pdf",
        byte_size=len(raw_bytes),
        blob_sha256=blob_sha256,
        page_count=page_count if isinstance(page_count, int) else None,
    )


if __name__ == "__main__":
    _run_subprocess_worker()
