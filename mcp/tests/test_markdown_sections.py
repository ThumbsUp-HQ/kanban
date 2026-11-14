# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for ATX heading extraction and surgical section patching (KB-P4-08)."""

from __future__ import annotations

import pytest

from mcp.errors import KbMcpError, McpErrorCode
from mcp.markdown_sections import extract_atx_headings, patch_markdown_section


def test_extract_atx_headings_ignores_fenced_blocks() -> None:
    """Verify extract_atx_headings ignores headings inside ``` and ~~~ blocks."""
    doc = """# Document Title

Intro text

```python
# This is a comment, not a heading
def foo():
    pass
```

## Section 1

Some content

~~~
# Another comment in tilde fence
~~~

### Sub Section

Details here
"""
    headings = extract_atx_headings(doc)
    assert len(headings) == 3
    assert headings[0].level == 1
    assert headings[0].text == "Document Title"
    assert headings[1].level == 2
    assert headings[1].text == "Section 1"
    assert headings[2].level == 3
    assert headings[2].text == "Sub Section"


def test_patch_markdown_section_normal_body() -> None:
    """Verify patching a middle section replaces old content."""
    doc = """# Architecture

Introductory text.

## PKCE
Old PKCE content with details.
### Implementation
Old implementation details.

## Auth Flow
Auth flow content.
"""
    patched = patch_markdown_section(doc, "PKCE", "New PKCE implementation using S256.")
    assert "## PKCE" in patched
    assert "New PKCE implementation using S256." in patched
    assert "Old PKCE content with details." not in patched
    assert "Old implementation details." not in patched
    assert "## Auth Flow" in patched
    assert "Auth flow content." in patched


def test_patch_markdown_section_with_replacement_heading() -> None:
    """Verify patching with explicit heading avoids duplicating heading."""
    doc = """# Architecture

## PKCE
Old content.

## Auth Flow
Auth content.
"""
    replacement = "## PKCE\nUpdated S256 with 128-bit state."
    patched = patch_markdown_section(doc, "## PKCE", replacement)
    assert "Updated S256 with 128-bit state." in patched
    assert "Old content." not in patched
    assert "## Auth Flow" in patched
    # Ensure heading is not duplicated
    assert patched.count("## PKCE") == 1


def test_patch_markdown_section_last_section() -> None:
    """Verify patching the last section replaces up to EOF."""
    doc = """# Architecture

## Overview
Some overview.

## Final Notes
Old final notes.
More trailing text.
"""
    patched = patch_markdown_section(doc, "Final Notes", "Brand new final notes.")
    assert "## Overview\nSome overview." in patched
    assert "## Final Notes" in patched
    assert "Brand new final notes." in patched
    assert "Old final notes." not in patched


def test_patch_markdown_section_not_found() -> None:
    """Verify missing heading raises SECTION_NOT_FOUND."""
    doc = """# Architecture

## Overview
Text
"""
    with pytest.raises(KbMcpError) as exc_info:
        patch_markdown_section(doc, "NonExistentSection", "New text")
    assert exc_info.value.code == McpErrorCode.SECTION_NOT_FOUND


def test_patch_markdown_section_ambiguous_identifier() -> None:
    """Verify duplicate headings raise AMBIGUOUS_IDENTIFIER."""
    doc = """# Architecture

## Details
First details.

## Details
Second details.
"""
    with pytest.raises(KbMcpError) as exc_info:
        patch_markdown_section(doc, "Details", "New text")
    assert exc_info.value.code == McpErrorCode.AMBIGUOUS_IDENTIFIER


def test_patch_markdown_section_case_sensitive() -> None:
    """Verify heading matching is case sensitive."""
    doc = """# Architecture

## pkce
Lower case text.
"""
    with pytest.raises(KbMcpError) as exc_info:
        patch_markdown_section(doc, "PKCE", "New text")
    assert exc_info.value.code == McpErrorCode.SECTION_NOT_FOUND
