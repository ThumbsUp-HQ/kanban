"""Decompression-bomb guards, EXIF/XMP/IPTC stripping, and raster re-encoding (S5.4)."""

from __future__ import annotations

import asyncio
import hashlib
import io
import warnings
from dataclasses import dataclass
from typing import Final

import anyio.to_thread
import defusedxml.ElementTree as DefusedET
from PIL import Image, ImageSequence

from kanban.api.problems import ProblemException
from kanban.attachments.sniff import MAX_ATTACHMENT_BYTES
from kanban.content.svg_dag import SvgSanitizeError
from kanban.content.svg_sanitizer import sanitize_svg

MAX_IMAGE_PIXELS: Final[int] = 40_000_000  # 40 MP exact
MAX_DIMENSION: Final[int] = 16_384  # 16,384 px max width or height
MAX_ANIMATED_FRAMES: Final[int] = 200  # 200 frames max
MAX_ANIMATED_TOTAL_PIXELS: Final[int] = 80_000_000  # 80 MP total area across frames

MAX_AVATAR_IMAGE_PIXELS: Final[int] = 16_000_000  # 16 MP exact
MAX_AVATAR_DIMENSION: Final[int] = 4096  # 4096 px max width or height
MAX_AVATAR_DOWNSCALE_DIMENSION: Final[int] = 1024  # 1024 px max downscale dimension
ALLOWED_AVATAR_PIL_FORMATS: Final[dict[str, str]] = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
}

# Set Pillow library cap
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

_RASTER_SEMAPHORE = asyncio.Semaphore(4)

PIL_FORMAT_MAP: Final[dict[str, str]] = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
    "image/gif": "GIF",
    "image/avif": "AVIF",
}


@dataclass(frozen=True, slots=True)
class ProcessedAttachment:
    """Sanitized attachment metadata and clean byte payload."""

    clean_bytes: bytes
    byte_size: int
    pixel_width: int | None
    pixel_height: int | None
    content_type: str
    blob_sha256: bytes


def _process_svg(raw_bytes: bytes) -> ProcessedAttachment:
    """Sanitize SVG XML, enforce byte size, and extract optional dimensions."""
    try:
        clean_svg_str = sanitize_svg(raw_bytes, max_bytes=MAX_ATTACHMENT_BYTES)
    except SvgSanitizeError as exc:
        raise ProblemException(
            code="SVG_UNSAFE",
            status=422,
            title="Unsafe SVG Content",
            detail=str(exc),
        ) from exc

    clean_bytes = clean_svg_str.encode("utf-8")
    if len(clean_bytes) > MAX_ATTACHMENT_BYTES:
        raise ProblemException(
            code="PAYLOAD_TOO_LARGE",
            status=413,
            title="Payload Too Large",
            detail="Sanitized SVG exceeds maximum 25 MiB limit",
        )

    pixel_w: int | None = None
    pixel_h: int | None = None
    try:
        root = DefusedET.fromstring(clean_svg_str)
        w_str = root.get("width", "").strip()
        h_str = root.get("height", "").strip()
        if w_str.isdigit() and int(w_str) > 0:
            pixel_w = int(w_str)
        if h_str.isdigit() and int(h_str) > 0:
            pixel_h = int(h_str)
    except Exception:  # noqa: BLE001, S110
        pass

    return ProcessedAttachment(
        clean_bytes=clean_bytes,
        byte_size=len(clean_bytes),
        pixel_width=pixel_w,
        pixel_height=pixel_h,
        content_type="image/svg+xml",
        blob_sha256=hashlib.sha256(clean_bytes).digest(),
    )


def _validate_image_dimensions(im: Image.Image) -> None:
    """Enforce header dimension limits against decompression bombs."""
    width, height = im.size
    total_pixels = width * height

    if (
        total_pixels > MAX_IMAGE_PIXELS
        or width > MAX_DIMENSION
        or height > MAX_DIMENSION
        or width <= 0
        or height <= 0
    ):
        raise ProblemException(
            code="IMAGE_DIMENSIONS_EXCEEDED",
            status=422,
            title="Image Dimensions Exceeded",
            detail=(
                f"Image dimensions ({width}x{height} = {total_pixels} px) exceed limits "
                f"(max {MAX_IMAGE_PIXELS} px, max dimension {MAX_DIMENSION} px)"
            ),
        )


def _process_animated(
    im: Image.Image,
    pil_format: str,
    content_type: str,
) -> ProcessedAttachment:
    """Re-encode multi-frame animated media stripping all frame metadata."""
    n_frames = int(getattr(im, "n_frames", 1))
    if n_frames > MAX_ANIMATED_FRAMES:
        raise ProblemException(
            code="IMAGE_DIMENSIONS_EXCEEDED",
            status=422,
            title="Image Dimensions Exceeded",
            detail=f"Animated image contains {n_frames} frames (max {MAX_ANIMATED_FRAMES})",
        )

    total_anim_area = 0
    frames: list[Image.Image] = []
    durations: list[int] = []

    for idx, frame in enumerate(ImageSequence.Iterator(im)):
        if idx >= MAX_ANIMATED_FRAMES:
            raise ProblemException(
                code="IMAGE_DIMENSIONS_EXCEEDED",
                status=422,
                title="Image Dimensions Exceeded",
                detail=f"Animated image exceeds {MAX_ANIMATED_FRAMES} frames",
            )
        fw, fh = frame.size
        total_anim_area += fw * fh
        if total_anim_area > MAX_ANIMATED_TOTAL_PIXELS:
            raise ProblemException(
                code="IMAGE_DIMENSIONS_EXCEEDED",
                status=422,
                title="Image Dimensions Exceeded",
                detail=(
                    f"Total animated area ({total_anim_area} px) "
                    f"exceeds {MAX_ANIMATED_TOTAL_PIXELS} px"
                ),
            )

        clean_frame = Image.new(frame.mode, frame.size)
        palette = frame.getpalette()
        if frame.mode == "P" and palette is not None:
            clean_frame.putpalette(palette)
        clean_frame.paste(frame)
        frames.append(clean_frame)
        durations.append(int(frame.info.get("duration", 100)))

    out_bio = io.BytesIO()
    save_kwargs: dict[str, object] = {
        "save_all": True,
        "append_images": frames[1:] if len(frames) > 1 else [],
        "duration": durations,
        "loop": int(im.info.get("loop", 0)),
    }
    frames[0].save(out_bio, format=pil_format, **save_kwargs)
    clean_bytes = out_bio.getvalue()

    if len(clean_bytes) > MAX_ATTACHMENT_BYTES:
        raise ProblemException(
            code="PAYLOAD_TOO_LARGE",
            status=413,
            title="Payload Too Large",
            detail=f"Re-encoded image exceeds maximum {MAX_ATTACHMENT_BYTES} bytes",
        )

    return ProcessedAttachment(
        clean_bytes=clean_bytes,
        byte_size=len(clean_bytes),
        pixel_width=im.width,
        pixel_height=im.height,
        content_type=content_type,
        blob_sha256=hashlib.sha256(clean_bytes).digest(),
    )


def _process_static(
    im: Image.Image,
    pil_format: str,
    content_type: str,
) -> ProcessedAttachment:
    """Re-encode single-frame raster media into a pristine image matrix."""
    clean_mode = im.mode
    if pil_format == "JPEG" and clean_mode not in ("RGB", "L"):
        clean_mode = "RGB"

    clean_im = Image.new(clean_mode, im.size)
    palette = im.getpalette()
    if clean_mode == "P" and palette is not None:
        clean_im.putpalette(palette)

    clean_im.paste(im)

    out_bio = io.BytesIO()
    if pil_format == "JPEG":
        clean_im.save(out_bio, format="JPEG", quality=95, optimize=True)
    elif pil_format == "PNG":
        clean_im.save(out_bio, format="PNG", optimize=True)
    elif pil_format in ("WEBP", "AVIF"):
        clean_im.save(out_bio, format=pil_format, quality=95)
    elif pil_format == "GIF":
        clean_im.save(out_bio, format="GIF")
    else:
        clean_im.save(out_bio, format=pil_format)

    clean_bytes = out_bio.getvalue()

    if len(clean_bytes) > MAX_ATTACHMENT_BYTES:
        raise ProblemException(
            code="PAYLOAD_TOO_LARGE",
            status=413,
            title="Payload Too Large",
            detail=f"Re-encoded image exceeds maximum {MAX_ATTACHMENT_BYTES} bytes",
        )

    return ProcessedAttachment(
        clean_bytes=clean_bytes,
        byte_size=len(clean_bytes),
        pixel_width=im.width,
        pixel_height=im.height,
        content_type=content_type,
        blob_sha256=hashlib.sha256(clean_bytes).digest(),
    )


def sanitize_and_reencode_raster_sync(
    raw_bytes: bytes,
    content_type: str,
) -> ProcessedAttachment:
    """Re-encode and sanitize raster or SVG media dropping 100% of untrusted metadata."""
    if content_type == "image/svg+xml":
        return _process_svg(raw_bytes)

    pil_format = PIL_FORMAT_MAP.get(content_type)
    if not pil_format:
        raise ProblemException(
            code="MIME_MISMATCH_OR_UNSUPPORTED",
            status=415,
            title="Unsupported Media Type",
            detail=f"Unsupported raster media type: {content_type}",
        )

    bio = io.BytesIO(raw_bytes)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            im = Image.open(bio)
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ProblemException(
                code="IMAGE_DIMENSIONS_EXCEEDED",
                status=422,
                title="Image Dimensions Exceeded",
                detail="Decompression bomb detected in image header",
            ) from exc
        except Exception as exc:
            raise ProblemException(
                code="MIME_MISMATCH_OR_UNSUPPORTED",
                status=415,
                title="Unsupported Media Type",
                detail=f"Corrupt or invalid image payload: {exc}",
            ) from exc

        _validate_image_dimensions(im)

        is_animated = bool(getattr(im, "is_animated", False))
        n_frames = int(getattr(im, "n_frames", 1))

        if is_animated or n_frames > 1:
            return _process_animated(im, pil_format, content_type)

        return _process_static(im, pil_format, content_type)


async def sanitize_and_reencode_raster(
    raw_bytes: bytes,
    content_type: str,
) -> ProcessedAttachment:
    """Process and sanitize media behind worker thread pool and concurrency semaphore."""
    async with _RASTER_SEMAPHORE:
        return await anyio.to_thread.run_sync(
            sanitize_and_reencode_raster_sync,
            raw_bytes,
            content_type,
        )


def sanitize_and_reencode_avatar_sync(  # noqa: C901
    raw_bytes: bytes,
    content_type: str,
) -> ProcessedAttachment:
    """Re-encode avatar raster dropping metadata, enforcing single-frame, and downscaling."""
    pil_format = ALLOWED_AVATAR_PIL_FORMATS.get(content_type)
    if not pil_format:
        raise ProblemException(
            code="UNSUPPORTED_MEDIA_TYPE",
            status=415,
            title="Unsupported Media Type",
            detail=(
                f"Unsupported avatar media type: {content_type}. "
                "Only PNG, JPEG, and WebP are allowed."
            ),
        )

    bio = io.BytesIO(raw_bytes)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            im = Image.open(bio)
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ProblemException(
                code="IMAGE_DIMENSIONS_EXCEEDED",
                status=422,
                title="Image Dimensions Exceeded",
                detail="Decompression bomb detected in image header.",
            ) from exc
        except Exception as exc:
            raise ProblemException(
                code="MIME_MISMATCH_OR_UNSUPPORTED",
                status=415,
                title="Unsupported Media Type",
                detail=f"Corrupt or invalid image payload: {exc}",
            ) from exc

        width, height = im.size
        total_pixels = width * height
        if (
            total_pixels > MAX_AVATAR_IMAGE_PIXELS
            or width > MAX_AVATAR_DIMENSION
            or height > MAX_AVATAR_DIMENSION
            or width <= 0
            or height <= 0
        ):
            raise ProblemException(
                code="IMAGE_DIMENSIONS_EXCEEDED",
                status=422,
                title="Image Dimensions Exceeded",
                detail=(
                    f"Avatar dimensions ({width}x{height} = {total_pixels} px) exceed limits "
                    f"(max {MAX_AVATAR_IMAGE_PIXELS} px, max dimension {MAX_AVATAR_DIMENSION} px)."
                ),
            )

        is_animated = bool(getattr(im, "is_animated", False))
        n_frames = int(getattr(im, "n_frames", 1))
        if is_animated or n_frames > 1:
            raise ProblemException(
                code="ANIMATED_AVATAR_NOT_ALLOWED",
                status=422,
                title="Animated Avatar Not Allowed",
                detail="Only single-frame static PNG, JPEG, and WebP avatars are allowed.",
            )

        # Downscale oversized images <= 1024x1024
        working_im: Image.Image = im
        if width > MAX_AVATAR_DOWNSCALE_DIMENSION or height > MAX_AVATAR_DOWNSCALE_DIMENSION:
            working_im = im.copy()
            working_im.thumbnail(
                (MAX_AVATAR_DOWNSCALE_DIMENSION, MAX_AVATAR_DOWNSCALE_DIMENSION),
                Image.Resampling.LANCZOS,
            )

        clean_mode = working_im.mode
        if pil_format == "JPEG" and clean_mode not in ("RGB", "L"):
            clean_mode = "RGB"

        clean_im = Image.new(clean_mode, working_im.size)
        palette = working_im.getpalette()
        if clean_mode == "P" and palette is not None:
            clean_im.putpalette(palette)

        clean_im.paste(working_im)

        out_bio = io.BytesIO()
        if pil_format == "JPEG":
            clean_im.save(out_bio, format="JPEG", quality=95, optimize=True)
        elif pil_format == "PNG":
            clean_im.save(out_bio, format="PNG", optimize=True)
        elif pil_format == "WEBP":
            clean_im.save(out_bio, format="WEBP", quality=95)
        else:
            clean_im.save(out_bio, format=pil_format)

        clean_bytes = out_bio.getvalue()
        return ProcessedAttachment(
            clean_bytes=clean_bytes,
            byte_size=len(clean_bytes),
            pixel_width=clean_im.width,
            pixel_height=clean_im.height,
            content_type=content_type,
            blob_sha256=hashlib.sha256(clean_bytes).digest(),
        )


async def sanitize_and_reencode_avatar(
    raw_bytes: bytes,
    content_type: str,
) -> ProcessedAttachment:
    """Process and sanitize avatar media behind worker thread pool and concurrency semaphore."""
    async with _RASTER_SEMAPHORE:
        return await anyio.to_thread.run_sync(
            sanitize_and_reencode_avatar_sync,
            raw_bytes,
            content_type,
        )
