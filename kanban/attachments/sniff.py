"""Streaming payload limit and magic-byte media type sniffer (S5.4)."""

from __future__ import annotations

import re
from pathlib import PurePath
from typing import Final

from kanban.api.problems import ProblemException

MAX_ATTACHMENT_BYTES: Final[int] = 26_214_400  # 25 MiB exact
_SVG_LEN: Final[int] = 4
_MIN_BOX_HEADER: Final[int] = 12
_MIN_PDF_HEADER: Final[int] = 8

ALLOWED_MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/avif",
        "image/gif",
        "image/svg+xml",
        "application/pdf",
    }
)

EXTENSION_TO_MEDIA_TYPE: Final[dict[str, str]] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
}

MEDIA_TYPE_TO_DEFAULT_EXT: Final[dict[str, str]] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
    "application/pdf": ".pdf",
}


def _sniff_avif(header: bytes) -> str | None:
    """Detect AVIF image by inspecting ISO-BMFF ftyp brands."""
    if len(header) >= _MIN_BOX_HEADER and header[4:8] == b"ftyp":
        major_brand = header[8:12]
        if major_brand in (b"avif", b"avis"):
            return "image/avif"
        ftyp_len = int.from_bytes(header[0:4], "big")
        box_limit = min(len(header), ftyp_len if ftyp_len > 0 else 64)
        for offset in range(16, box_limit, 4):
            if header[offset : offset + 4] in (b"avif", b"avis"):
                return "image/avif"
    return None


def _sniff_raster(header: bytes) -> str | None:
    """Detect raster media type from signature bytes."""
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(header) >= _MIN_BOX_HEADER and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"

    return _sniff_avif(header)


def _sniff_svg(header: bytes) -> str | None:
    """Detect SVG markup from header prefix rejecting HTML vectors."""
    stripped = header.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith((b"<!DOCTYPE html", b"<html")):
        return None

    if stripped.startswith(b"<svg") and (
        len(stripped) == _SVG_LEN or stripped[4:5] in b" \t\r\n>/"
    ):
        return "image/svg+xml"

    if stripped.startswith(b"<?xml"):
        prefix = stripped[:2048].lower()
        if b"<!doctype html" in prefix or b"<html" in prefix:
            return None
        if b"<svg" in prefix:
            return "image/svg+xml"

    return None


def _sniff_pdf(header: bytes) -> str | None:
    """Detect PDF document from magic bytes strictly at offset 0."""
    if len(header) >= _MIN_PDF_HEADER and header.startswith((b"%PDF-1.", b"%PDF-2.")):
        return "application/pdf"
    return None


def _check_special_type_hints(
    detected: str,
    filename: str,
    declared_content_type: str | None,
) -> None:
    """Verify SVG or PDF has corresponding extension or declared Content-Type."""
    if detected in ("image/svg+xml", "application/pdf"):
        expected_ext = ".svg" if detected == "image/svg+xml" else ".pdf"
        lower_fn = filename.lower()
        has_ext = lower_fn.endswith(expected_ext)
        decl_match = (
            declared_content_type is not None
            and declared_content_type.strip().lower().split(";")[0] == detected
        )
        if not (has_ext or decl_match):
            label = "SVG" if detected == "image/svg+xml" else "PDF"
            raise ProblemException(
                code="MIME_MISMATCH_OR_UNSUPPORTED",
                status=415,
                title="Unsupported Media Type",
                detail=(
                    f"{label} content must have {expected_ext} extension or {detected} Content-Type"
                ),
            )


def sniff_media_type(
    header_bytes: bytes,
    declared_content_type: str | None,
    filename: str,
) -> str:
    """Sniff media type from magic bytes and enforce consistency with declared metadata.

    Raises:
        ProblemException(code='MIME_MISMATCH_OR_UNSUPPORTED', status=415):
            If magic bytes are unknown, or conflict with declared Content-Type or extension.

    """
    detected = _sniff_raster(header_bytes) or _sniff_svg(header_bytes) or _sniff_pdf(header_bytes)
    if detected is None or detected not in ALLOWED_MEDIA_TYPES:
        raise ProblemException(
            code="MIME_MISMATCH_OR_UNSUPPORTED",
            status=415,
            title="Unsupported Media Type",
            detail="File content does not match any supported media type",
        )

    _check_special_type_hints(detected, filename, declared_content_type)

    # Verify declared Content-Type consistency if provided
    if declared_content_type:
        clean_declared = declared_content_type.strip().lower().split(";")[0]
        if clean_declared in ALLOWED_MEDIA_TYPES and clean_declared != detected:
            raise ProblemException(
                code="MIME_MISMATCH_OR_UNSUPPORTED",
                status=415,
                title="Unsupported Media Type",
                detail=(
                    f"Declared Content-Type '{clean_declared}' conflicts with detected '{detected}'"
                ),
            )
        if clean_declared not in ALLOWED_MEDIA_TYPES:
            raise ProblemException(
                code="MIME_MISMATCH_OR_UNSUPPORTED",
                status=415,
                title="Unsupported Media Type",
                detail=f"Declared Content-Type '{clean_declared}' is unsupported",
            )

    # Verify filename extension consistency if present
    ext = PurePath(filename).suffix.lower()
    if ext in EXTENSION_TO_MEDIA_TYPE:
        expected_type = EXTENSION_TO_MEDIA_TYPE[ext]
        if expected_type != detected:
            raise ProblemException(
                code="MIME_MISMATCH_OR_UNSUPPORTED",
                status=415,
                title="Unsupported Media Type",
                detail=f"Extension '{ext}' conflicts with detected media type '{detected}'",
            )
    elif ext:
        raise ProblemException(
            code="MIME_MISMATCH_OR_UNSUPPORTED",
            status=415,
            title="Unsupported Media Type",
            detail=f"Filename extension '{ext}' is unsupported",
        )

    return detected


def sanitize_original_filename(raw_filename: str) -> str:
    """Sanitize user-provided filename for safe database storage (1..255 chars)."""
    clean = "".join(c for c in raw_filename if c.isprintable() and c != "\x00").strip()
    basename = clean.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not basename:
        basename = "attachment"
    return basename[:255]


def sanitize_content_disposition_filename(filename: str, content_type: str) -> str:
    r"""Generate safe ASCII-only filename for Content-Disposition header.

    Guarantees no '/', '\\', '..', control characters, or path traversal vectors.
    """
    clean = "".join(c for c in filename if c.isprintable() and c != "\x00").strip()
    basename = clean.replace("\\", "/").rsplit("/", 1)[-1].strip()
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", basename)
    safe = safe.strip("._")
    if not safe:
        safe = "attachment"

    expected_ext = MEDIA_TYPE_TO_DEFAULT_EXT.get(content_type, "")
    ext = PurePath(safe).suffix.lower()
    if ext not in EXTENSION_TO_MEDIA_TYPE or EXTENSION_TO_MEDIA_TYPE[ext] != content_type:
        safe = f"{PurePath(safe).stem}{expected_ext}"

    return safe[:120]
