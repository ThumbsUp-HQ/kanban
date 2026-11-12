# Copyright 2026 Kanban Platform Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Sparkle FIM output filter: HTML stripping, secret scrubbing, and prompt override defense."""

from __future__ import annotations

import html
import re
from typing import Final

from kanban.security.scrubber import outbound_secret_scrubber

__all__ = ["filter_completion"]

# Zero-width spaces, joiners, bi-directional overrides, and unicode tag plane
_RE_ZERO_WIDTH_AND_TAGS: Final[re.Pattern[str]] = re.compile(
    r"[\u200B-\u200F\U000E0000-\U000E007F]"
)

# HTML tag matcher (greedy across multi-attributes, handles unclosed tags up to end of string)
_RE_HTML_TAGS: Final[re.Pattern[str]] = re.compile(r"<[^>]*>?")

# Prompt override / jailbreak patterns (case-insensitive)
_RE_PROMPT_OVERRIDES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above)\s+instructions",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(?:system|assistant)\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"BEGIN SYSTEM PROMPT", re.IGNORECASE),
    re.compile(r"\byou are now\b", re.IGNORECASE),
)

# Whitespace or punctuation tokenization boundary for capping token counts
_RE_TOKEN: Final[re.Pattern[str]] = re.compile(r"\s*\S+")


def filter_completion(
    raw_text: str,
    *,
    max_tokens: int = 48,
    max_chars: int = 400,
) -> str:
    """Sanitize and validate raw FIM completion output.

    Applies the following defense-in-depth filters in order:
    1. Removes invisible zero-width and unicode tag plane characters.
    2. Strips all HTML tags and entity-decoded markup (<...>).
    3. Rejects prompt-injection and instruction-override attempts.
    4. Scans for echoed credentials via outbound_secret_scrubber, dropping the
       completion if any secrets or tokens are detected.
    5. Enforces hard maximum bounds on character length (400) and token count (48).

    Returns:
        Sanitized completion string, or an empty string if rejected or empty.

    """
    if not raw_text:
        return ""

    # Step 1: Strip zero-width and unicode tag plane characters
    cleaned = _RE_ZERO_WIDTH_AND_TAGS.sub("", raw_text)

    # Step 2: Unescape HTML entities
    unescaped = html.unescape(cleaned)

    # Step 3: Check for prompt override / jailbreak patterns BEFORE tag stripping
    # (so tokens like <|im_start|> are caught before being stripped as tags)
    for pattern in _RE_PROMPT_OVERRIDES:
        if pattern.search(unescaped):
            return ""

    # Step 4: Strip all HTML tags
    text_no_html = _RE_HTML_TAGS.sub("", unescaped)

    # Step 5: Scan with outbound secret scrubber; echoed secrets drop completion
    scrub_result = outbound_secret_scrubber(text_no_html)
    if scrub_result.redacted:
        return ""

    # Step 6: Enforce character cap
    if len(text_no_html) > max_chars:
        text_no_html = text_no_html[:max_chars]

    # Step 7: Enforce token cap
    token_matches = list(_RE_TOKEN.finditer(text_no_html))
    if len(token_matches) > max_tokens:
        cutoff = token_matches[max_tokens - 1].end()
        text_no_html = text_no_html[:cutoff]

    return text_no_html
