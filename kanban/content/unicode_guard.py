"""Unicode, invisible character, and control character guard.

Enforces input byte size limits, rejects UTF-8 surrogates, normalizes newlines,
and strips zero-width, BiDi override, Plane-14 tag, and C0/C1 control characters.
"""

from __future__ import annotations

# Code point constants for invisible / zero-width characters
SOFT_HYPHEN = 0x00AD
ZW_MIN = 0x200B
ZW_MAX = 0x200F
BIDI_OVERRIDE_MIN = 0x202A
BIDI_OVERRIDE_MAX = 0x202E
MATH_INVISIBLE_MIN = 0x2060
MATH_INVISIBLE_MAX = 0x2064
BIDI_ISOLATE_MIN = 0x2066
BIDI_ISOLATE_MAX = 0x2069
BOM_CHAR = 0xFEFF
PLANE_14_TAG_MIN = 0xE0000
PLANE_14_TAG_MAX = 0xE007F

# Control character boundaries
C0_CTRL_MIN = 0x0000
C0_PRE_TAB = 0x0008
C0_POST_LF = 0x000B
C0_CTRL_MAX = 0x001F
C1_CTRL_MIN = 0x007F
C1_CTRL_MAX = 0x009F

# Surrogate code point boundaries
SURROGATE_MIN = 0xD800
SURROGATE_MAX = 0xDFFF


class ContentNormalizeError(Exception):
    """Raised when content normalization fails a security, size, or complexity boundary."""

    def __init__(self, code: str, message: str | None = None) -> None:
        """Initialize normalization error with error code and optional message."""
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def is_zero_width_or_invisible(cp: int) -> bool:
    """Return True if code point is an invisible, BiDi override, or tag character."""
    if cp in (SOFT_HYPHEN, BOM_CHAR):
        return True
    return (
        ZW_MIN <= cp <= ZW_MAX
        or BIDI_OVERRIDE_MIN <= cp <= BIDI_OVERRIDE_MAX
        or MATH_INVISIBLE_MIN <= cp <= MATH_INVISIBLE_MAX
        or BIDI_ISOLATE_MIN <= cp <= BIDI_ISOLATE_MAX
        or PLANE_14_TAG_MIN <= cp <= PLANE_14_TAG_MAX
    )


def is_c0_c1_control(cp: int) -> bool:
    """Return True if code point is a C0 or C1 control character, excluding TAB and LF."""
    if C0_CTRL_MIN <= cp <= C0_PRE_TAB or C0_POST_LF <= cp <= C0_CTRL_MAX:
        return True
    return C1_CTRL_MIN <= cp <= C1_CTRL_MAX


def strip_invisible_and_control_chars(
    text: str,
    max_input_bytes: int = 2_097_152,
) -> tuple[str, int, int]:
    """Validate byte length, check surrogates, and strip invisible and control characters.

    Args:
        text: Input raw string.
        max_input_bytes: Maximum allowed UTF-8 byte length (default 2 MiB).

    Returns:
        Tuple of (sanitized_text, zero_width_stripped_count, control_chars_stripped_count).

    Raises:
        ContentNormalizeError: If text exceeds max_input_bytes or contains surrogates.

    """
    for char in text:
        cp = ord(char)
        if SURROGATE_MIN <= cp <= SURROGATE_MAX:
            surr_code = "INVALID_UTF8_SURROGATE"
            raise ContentNormalizeError(surr_code)

    encoded_len = len(text.encode("utf-8"))
    if encoded_len > max_input_bytes:
        too_large_code = "CONTENT_TOO_LARGE"
        raise ContentNormalizeError(too_large_code)

    # Normalize CRLF and CR to LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    out_chars: list[str] = []
    zero_width_count = 0
    control_count = 0

    for char in text:
        cp = ord(char)
        if is_zero_width_or_invisible(cp):
            zero_width_count += 1
            continue
        if is_c0_c1_control(cp):
            control_count += 1
            continue
        out_chars.append(char)

    return "".join(out_chars), zero_width_count, control_count
