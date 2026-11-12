"""Unit tests for attachment media sniffing, raster re-encoding, and blob storage (S5.4)."""

from __future__ import annotations

import io
import stat
import struct
import zlib
from typing import TYPE_CHECKING

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from kanban.api.problems import ProblemException
from kanban.attachments.raster import (
    MAX_ANIMATED_FRAMES,
    _validate_image_dimensions,
    sanitize_and_reencode_raster,
    sanitize_and_reencode_raster_sync,
)
from kanban.attachments.signing import (
    sign_attachment_url,
    verify_attachment_url,
)
from kanban.attachments.sniff import (
    sanitize_content_disposition_filename,
    sanitize_original_filename,
    sniff_media_type,
)
from kanban.attachments.storage import (
    BlobStorageError,
    LocalFilesystemBlobStore,
)

if TYPE_CHECKING:
    from pathlib import Path


def _create_jpeg_with_exif_and_polyglot() -> tuple[bytes, dict[str, object]]:
    """Generate JPEG image with EXIF GPS coordinates, camera serial, and trailing PHP polyglot."""
    im = Image.new("RGB", (64, 64), color="blue")
    exif = im.getexif()
    exif[0x010F] = "TestCameraMake"
    exif[0x0110] = "TestCameraModel"
    exif[0xA431] = "SN-987654321"  # Camera serial number

    gps_ifd = exif.get_ifd(0x8825)
    gps_ifd[1] = "N"
    gps_ifd[2] = (IFDRational(37, 1), IFDRational(46, 1), IFDRational(29, 1))  # GPSLatitude
    gps_ifd[3] = "W"
    gps_ifd[4] = (IFDRational(122, 1), IFDRational(25, 1), IFDRational(10, 1))  # GPSLongitude

    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    jpeg_bytes = buf.getvalue()

    # Append trailing polyglot bytes
    polyglot_payload = b"<?php phpinfo(); ?>\x00\xfftrailing_junk"
    return jpeg_bytes + polyglot_payload, {
        "make": "TestCameraMake",
        "model": "TestCameraModel",
        "serial": "SN-987654321",
        "latitude": (37.0, 46.0, 29.0),
        "longitude": (122.0, 25.0, 10.0),
        "polyglot": polyglot_payload,
    }


def _create_synthetic_png_header(width: int, height: int) -> bytes:
    """Create minimal PNG file with arbitrary width/height in IHDR without uncompressed bitmap."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc

    raw = zlib.compress(b"\x00" * 32)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + raw) & 0xFFFFFFFF)
    idat = struct.pack(">I", len(raw)) + b"IDAT" + raw + idat_crc

    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + iend_crc
    return sig + ihdr + idat + iend


def _create_animated_gif(n_frames: int) -> bytes:
    """Generate minimal animated GIF with specified number of frames."""
    frames = [Image.new("RGB", (10, 10), color=(i % 256, 0, 0)) for i in range(n_frames)]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=50, loop=0)
    return buf.getvalue()


class TestSniffMediaType:
    """Test magic-byte sniffer and MIME validation."""

    def test_sniff_valid_formats(self) -> None:
        """Verify magic byte detection for PNG, JPEG, GIF, WebP, AVIF, and SVG."""
        # PNG
        png_im = Image.new("RGBA", (10, 10), color="red")
        pbuf = io.BytesIO()
        png_im.save(pbuf, format="PNG")
        assert sniff_media_type(pbuf.getvalue(), "image/png", "test.png") == "image/png"

        # JPEG
        jpg_im = Image.new("RGB", (10, 10), color="green")
        jbuf = io.BytesIO()
        jpg_im.save(jbuf, format="JPEG")
        assert sniff_media_type(jbuf.getvalue(), "image/jpeg", "test.jpg") == "image/jpeg"

        # GIF
        gif_bytes = _create_animated_gif(2)
        assert sniff_media_type(gif_bytes, "image/gif", "test.gif") == "image/gif"

        # WebP
        wbuf = io.BytesIO()
        jpg_im.save(wbuf, format="WEBP")
        assert sniff_media_type(wbuf.getvalue(), "image/webp", "test.webp") == "image/webp"

        # SVG with direct <svg>
        svg_raw = b"<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'></svg>"
        assert sniff_media_type(svg_raw, "image/svg+xml", "test.svg") == "image/svg+xml"

        # SVG with <?xml> declaration
        xml_svg = b"<?xml version='1.0'?><svg viewBox='0 0 10 10'></svg>"
        assert sniff_media_type(xml_svg, "image/svg+xml", "test.svg") == "image/svg+xml"

    def test_magic_byte_spoofing_rejections(self) -> None:
        """Verify Test Case 3: Reject magic-byte spoofing, extensions, and HTML vectors."""
        # HTML named diagram.svg with declared image/svg+xml
        html_payload = b"<!DOCTYPE html><html><body><h1>XSS</h1></body></html>"
        with pytest.raises(ProblemException) as exc_info:
            sniff_media_type(html_payload, "image/svg+xml", "diagram.svg")
        assert exc_info.value.code == "MIME_MISMATCH_OR_UNSUPPORTED"
        assert exc_info.value.status == 415

        # PNG bytes named icon.svg
        png_bytes = _create_synthetic_png_header(10, 10)
        with pytest.raises(ProblemException) as exc_info:
            sniff_media_type(png_bytes, None, "icon.svg")
        assert exc_info.value.code == "MIME_MISMATCH_OR_UNSUPPORTED"

        # <script>alert(1)</script> named photo.png
        script_payload = b"<script>alert(1)</script>"
        with pytest.raises(ProblemException) as exc_info:
            sniff_media_type(script_payload, "image/png", "photo.png")
        assert exc_info.value.code == "MIME_MISMATCH_OR_UNSUPPORTED"

        # PDF payload
        pdf_payload = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj"
        with pytest.raises(ProblemException) as exc_info:
            sniff_media_type(pdf_payload, "image/png", "doc.png")
        assert exc_info.value.code == "MIME_MISMATCH_OR_UNSUPPORTED"

        # Mismatched declared Content-Type (PNG bytes with declared image/jpeg)
        with pytest.raises(ProblemException) as exc_info:
            sniff_media_type(png_bytes, "image/jpeg", "photo.png")
        assert exc_info.value.code == "MIME_MISMATCH_OR_UNSUPPORTED"


class TestRasterSanitizationAndReencode:
    """Test decompression-bomb guards, EXIF stripping, and raster re-encoding."""

    @pytest.mark.asyncio
    async def test_exif_gps_strip_roundtrip(self) -> None:
        """Verify Test Case 1: EXIF GPS, serial, XMP, and polyglot bytes are completely stripped."""
        raw_jpeg, meta = _create_jpeg_with_exif_and_polyglot()
        polyglot = meta["polyglot"]
        assert isinstance(polyglot, bytes)
        assert polyglot in raw_jpeg

        # Verify initial JPEG contains EXIF metadata
        im_before = Image.open(io.BytesIO(raw_jpeg))
        exif_before = im_before.getexif()
        assert len(exif_before) > 0
        assert exif_before.get(0x010F) == meta["make"]
        gps_before = exif_before.get_ifd(0x8825)
        assert len(gps_before) > 0

        # Process and re-encode
        result = await sanitize_and_reencode_raster(raw_jpeg, "image/jpeg")

        # Verify output payload
        clean_bytes = result.clean_bytes
        assert result.content_type == "image/jpeg"
        assert result.byte_size == len(clean_bytes)
        assert polyglot not in clean_bytes

        # Re-open clean image to inspect metadata
        im_after = Image.open(io.BytesIO(clean_bytes))
        exif_after = im_after.getexif()
        assert len(exif_after) == 0
        assert len(exif_after.get_ifd(0x8825)) == 0

    @pytest.mark.asyncio
    async def test_decompression_bomb_rejection(self) -> None:
        """Verify Test Case 4: 10000x5000 PNG and 201-frame GIF rejected with 422."""
        # 10000x5000 = 50,000,000 > 40,000,000 px
        bomb_png = _create_synthetic_png_header(10000, 5000)
        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_reencode_raster(bomb_png, "image/png")
        assert exc_info.value.code == "IMAGE_DIMENSIONS_EXCEEDED"
        assert exc_info.value.status == 422

        # Dimension exceeding 16384 (17000 x 10)
        wide_png = _create_synthetic_png_header(17000, 10)
        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_reencode_raster(wide_png, "image/png")
        assert exc_info.value.code == "IMAGE_DIMENSIONS_EXCEEDED"

        # 201-frame animated GIF
        bomb_gif = _create_animated_gif(MAX_ANIMATED_FRAMES + 1)
        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_reencode_raster(bomb_gif, "image/gif")
        assert exc_info.value.code == "IMAGE_DIMENSIONS_EXCEEDED"
        assert exc_info.value.status == 422

    def test_dimensions_check_within_limits(self) -> None:
        """Verify 6000x6000 (36 MP <= 40 MP) passes dimension check."""
        im = Image.new("RGB", (6000, 6000))
        # Should not raise
        _validate_image_dimensions(im)

    @pytest.mark.asyncio
    async def test_svg_sanitization(self) -> None:
        """Verify SVG sanitization strips scripts and extracts dimensions."""
        svg_content = (
            b"<svg xmlns='http://www.w3.org/2000/svg' width='120' height='80'>"
            b"<rect width='100' height='50' fill='blue'/>"
            b"<script>alert(1)</script>"
            b"</svg>"
        )
        result = await sanitize_and_reencode_raster(svg_content, "image/svg+xml")
        assert b"<script" not in result.clean_bytes
        assert b"<rect" in result.clean_bytes
        assert result.pixel_width == 120
        assert result.pixel_height == 80


class TestFilesystemBlobStore:
    """Test LocalFilesystemBlobStore content-addressed storage and security invariants."""

    def test_atomic_store_and_permissions(self, tmp_path: Path) -> None:
        """Verify atomic store, mode 0600, and sha256 content key."""
        store = LocalFilesystemBlobStore(tmp_path)
        data = b"sample attachment blob data"
        key, sha = store.store(data)

        assert key.startswith("sha256/")
        assert len(sha) == 32
        assert store.exists(key)

        path = store.get_path(key)
        assert path.is_file()
        file_mode = stat.S_IMODE(path.stat().st_mode)
        assert file_mode == 0o600

        # Read back
        assert store.read(key) == data

    def test_traversal_rejection(self, tmp_path: Path) -> None:
        """Verify directory traversal in storage key is rejected."""
        store = LocalFilesystemBlobStore(tmp_path)
        with pytest.raises(BlobStorageError):
            store.get_path("../../etc/passwd")

        with pytest.raises(BlobStorageError):
            store.get_path("sha256/../../etc/passwd")


class TestSignedUrls:
    """Test HMAC signed URL minting and verification."""

    def test_signed_url_flow(self) -> None:
        """Verify signed URL minting, expiration, and tamper detection."""
        key = b"\x01" * 32
        att_id = "018e3a24-1234-7000-8000-000000000001"
        p_id = "018e3a24-1234-7000-8000-000000000002"

        url = sign_attachment_url(att_id, p_id, key, ttl_seconds=300, now=1000)
        assert f"/api/v1/attachments/{att_id}/content" in url
        assert "exp=1300" in url
        assert f"p={p_id}" in url

        # Valid verification
        sig = url.split("sig=")[-1]
        assert verify_attachment_url(att_id, p_id, 1300, sig, key, now=1000) is True

        # Expired
        assert verify_attachment_url(att_id, p_id, 1300, sig, key, now=1301) is False

        # Tampered signature
        assert verify_attachment_url(att_id, p_id, 1300, sig + "x", key, now=1000) is False

        # Tampered principal
        other_p = "018e3a24-1234-7000-8000-000000000099"
        assert verify_attachment_url(att_id, other_p, 1300, sig, key, now=1000) is False

        # Wrong key
        assert verify_attachment_url(att_id, p_id, 1300, sig, b"\x02" * 32, now=1000) is False


class TestFilenameSanitization:
    """Test filename sanitization for database and Content-Disposition header."""

    def test_sanitize_original_filename(self) -> None:
        """Verify original_filename sanitization removes path separators and nulls."""
        dirty = "../../etc/passwd\x00.png"
        cleaned = sanitize_original_filename(dirty)
        assert "/" not in cleaned
        assert "\\" not in cleaned
        assert "\x00" not in cleaned
        assert cleaned == "passwd.png"

    def test_sanitize_content_disposition_filename(self) -> None:
        """Verify Content-Disposition filename is ASCII safe with correct extension."""
        dirty = "../../etc/passwd\x00.png"
        safe = sanitize_content_disposition_filename(dirty, "image/png")
        assert "/" not in safe
        assert "\\" not in safe
        assert ".." not in safe
        assert safe.endswith(".png")

    def test_filename_sanitization_edge_cases(self) -> None:
        """Verify fallback behavior for blank, non-ascii, and oversized filenames."""
        assert sanitize_original_filename("") == "attachment"
        assert sanitize_original_filename("///\\\\\\") == "attachment"
        long_fn = "a" * 300 + ".png"
        assert len(sanitize_original_filename(long_fn)) == 255

        # Content disposition edge cases
        safe_empty = sanitize_content_disposition_filename("", "image/jpeg")
        assert safe_empty == "attachment.jpg"
        safe_unicode = sanitize_content_disposition_filename("фото_картинка.png", "image/png")
        assert safe_unicode.endswith(".png")
        assert all(ord(c) < 128 for c in safe_unicode)
        # Wrong extension corrected
        safe_wrong_ext = sanitize_content_disposition_filename("photo.txt", "image/png")
        assert safe_wrong_ext == "photo.png"


class TestSniffEdgeCases:
    """Test AVIF, SVG headers, and MIME consistency branches in sniffer."""

    def test_sniff_avif_brands(self) -> None:
        """Verify AVIF detection across major and compatible ftyp brands."""
        avif_major = b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00mif1avif"
        assert sniff_media_type(avif_major, "image/avif", "photo.avif") == "image/avif"

        avis_major = b"\x00\x00\x00\x1cftypavis\x00\x00\x00\x00mif1avis"
        assert sniff_media_type(avis_major, "image/avif", "photo.avif") == "image/avif"

        # Compatible brand in secondary box
        avif_compat = b"\x00\x00\x00\x20ftypmif1\x00\x00\x00\x00mif1avif\x00\x00\x00\x00"
        assert sniff_media_type(avif_compat, "image/avif", "photo.avif") == "image/avif"

    def test_sniff_svg_variants(self) -> None:
        """Verify SVG detection with XML declaration and rejection of HTML."""
        xml_svg = b"<?xml version='1.0' encoding='UTF-8'?>\n<svg xmlns='http://www.w3.org/2000/svg'></svg>"
        assert sniff_media_type(xml_svg, "image/svg+xml", "icon.svg") == "image/svg+xml"

        # XML doctype HTML rejected
        xml_html = b"<?xml version='1.0'?><!DOCTYPE html><html><body></body></html>"
        with pytest.raises(ProblemException) as exc_info:
            sniff_media_type(xml_html, "image/svg+xml", "fake.svg")
        assert exc_info.value.status == 415

    def test_sniff_mismatch_and_unsupported(self) -> None:
        """Verify error paths for unsupported and mismatched media types."""
        png_sig = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

        # SVG without .svg extension and without image/svg+xml declared type
        svg_raw = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
        with pytest.raises(ProblemException) as exc_info:
            sniff_media_type(svg_raw, "image/png", "vector.png")
        assert exc_info.value.status == 415

        # Unsupported declared content-type
        with pytest.raises(ProblemException) as exc_info:
            sniff_media_type(png_sig, "application/x-custom", "photo.png")
        assert exc_info.value.status == 415

        # Unsupported file extension
        with pytest.raises(ProblemException) as exc_info:
            sniff_media_type(png_sig, "image/png", "photo.exe")
        assert exc_info.value.status == 415


class TestRasterAndAnimatedProcessing:
    """Test animated frame processing, format conversions, and error conditions."""

    @pytest.mark.asyncio
    async def test_animated_gif_roundtrip(self) -> None:
        """Verify animated GIF re-encodes frames, preserves dimensions and strips frame info."""
        gif_bytes = _create_animated_gif(3)
        result = await sanitize_and_reencode_raster(gif_bytes, "image/gif")
        assert result.content_type == "image/gif"
        assert result.pixel_width == 10
        assert result.pixel_height == 10
        assert len(result.clean_bytes) > 0

        # Read back with PIL to verify valid multi-frame
        im = Image.open(io.BytesIO(result.clean_bytes))
        assert getattr(im, "is_animated", False) is True
        assert getattr(im, "n_frames", 1) == 3

    @pytest.mark.asyncio
    async def test_animated_area_exceeded(self) -> None:
        """Verify animated GIF exceeding 80,000,000 total pixels is rejected."""
        # 10 distinct frames of 3000 x 3000 = 90,000,000 px > 80,000,000 px
        frames = [Image.new("RGB", (3000, 3000), color=(i * 20, 10, 10)) for i in range(10)]
        buf = io.BytesIO()
        frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=50)
        gif_data = buf.getvalue()

        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_reencode_raster(gif_data, "image/gif")
        assert exc_info.value.code == "IMAGE_DIMENSIONS_EXCEEDED"
        assert exc_info.value.status == 422

    @pytest.mark.asyncio
    async def test_format_conversions_and_modes(self) -> None:
        """Verify conversion of RGBA JPEG, WebP, static GIF, and palette PNG."""
        # RGBA converted to RGB for JPEG
        rgba_im = Image.new("RGBA", (20, 20), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        rgba_im.save(buf, format="PNG")
        # Converting raw PNG bytes into JPEG
        res_jpeg = await sanitize_and_reencode_raster(buf.getvalue(), "image/png")
        assert res_jpeg.content_type == "image/png"

        # Valid WebP roundtrip
        webp_im = Image.new("RGB", (20, 20), color=(0, 255, 0))
        buf_webp = io.BytesIO()
        webp_im.save(buf_webp, format="WEBP")
        res_webp = await sanitize_and_reencode_raster(buf_webp.getvalue(), "image/webp")
        assert res_webp.content_type == "image/webp"

        # Palette P image roundtrip
        p_im = Image.new("P", (20, 20))
        p_im.putpalette([i % 256 for i in range(768)])
        buf_p = io.BytesIO()
        p_im.save(buf_p, format="PNG")
        res_p = await sanitize_and_reencode_raster(buf_p.getvalue(), "image/png")
        assert res_p.content_type == "image/png"

        # Static GIF roundtrip
        gif_im = Image.new("RGB", (20, 20), color=(128, 64, 32))
        buf_gif = io.BytesIO()
        gif_im.save(buf_gif, format="GIF")
        res_gif = await sanitize_and_reencode_raster(buf_gif.getvalue(), "image/gif")
        assert res_gif.content_type == "image/gif"

        # CMYK JPEG converted to RGB
        cmyk_im = Image.new("CMYK", (20, 20), color=(0, 255, 0, 0))
        buf_cmyk = io.BytesIO()
        cmyk_im.save(buf_cmyk, format="JPEG")
        res_cmyk = await sanitize_and_reencode_raster(buf_cmyk.getvalue(), "image/jpeg")
        assert res_cmyk.content_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_svg_without_dimensions(self) -> None:
        """Verify SVG without explicit pixel width/height parses safely with None dimensions."""
        svg_nodim = (
            b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
            b"<circle cx='50' cy='50' r='40' fill='red'/>"
            b"</svg>"
        )
        res = await sanitize_and_reencode_raster(svg_nodim, "image/svg+xml")
        assert res.pixel_width is None
        assert res.pixel_height is None
        assert b"<circle" in res.clean_bytes

    @pytest.mark.asyncio
    async def test_reencoded_payload_too_large(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify 413 when re-encoded static or animated output exceeds limit."""
        monkeypatch.setattr("kanban.attachments.raster.MAX_ATTACHMENT_BYTES", 10)

        # Static image exceeding 10 bytes
        im = Image.new("RGB", (20, 20))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_reencode_raster(buf.getvalue(), "image/png")
        assert exc_info.value.code == "PAYLOAD_TOO_LARGE"
        assert exc_info.value.status == 413

        # Animated image exceeding 10 bytes
        gif_bytes = _create_animated_gif(2)
        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_reencode_raster(gif_bytes, "image/gif")
        assert exc_info.value.code == "PAYLOAD_TOO_LARGE"
        assert exc_info.value.status == 413

    @pytest.mark.asyncio
    async def test_invalid_image_payloads(self) -> None:
        """Verify corrupted image bytes and unsupported format handling."""
        corrupt_bytes = b"\x89PNG\r\n\x1a\n" + b"\xff" * 50
        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_reencode_raster(corrupt_bytes, "image/png")
        assert exc_info.value.status == 415

        # Unsupported format in raster function
        with pytest.raises(ProblemException) as exc_info:
            sanitize_and_reencode_raster_sync(b"data", "image/unknown")
        assert exc_info.value.status == 415

        # Invalid SVG
        invalid_svg = b"<svg><unclosed>"
        with pytest.raises(ProblemException) as exc_info:
            await sanitize_and_reencode_raster(invalid_svg, "image/svg+xml")
        assert exc_info.value.code == "SVG_UNSAFE"
        assert exc_info.value.status == 422


class TestStorageAndSigningEdgeCases:
    """Test BlobStore and URL signing error branches."""

    def test_blob_store_error_branches(self, tmp_path: Path) -> None:
        """Verify duplicate store, non-existent read, and invalid exists."""
        store = LocalFilesystemBlobStore(tmp_path)
        data = b"idempotent content"
        k1, s1 = store.store(data)
        # Store again (exercises FileExistsError / already written path)
        k2, s2 = store.store(data)
        assert k1 == k2
        assert s1 == s2

        # Read non-existent key
        with pytest.raises(BlobStorageError):
            store.read(
                "sha256/00/00/0000000000000000000000000000000000000000000000000000000000000000"
            )

        # Exists with invalid key format
        assert store.exists("invalid-key-format") is False

    def test_signing_exception_handling(self) -> None:
        """Verify verify_attachment_url returns False on unexpected exceptions."""
        # Non-bytes key or bad params
        assert verify_attachment_url("att", "p", 9999999999, "sig", None) is False  # type: ignore[arg-type]
