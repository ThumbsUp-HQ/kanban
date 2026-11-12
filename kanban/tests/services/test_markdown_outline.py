# Copyright 2026 Kanban Platform Contributors
"""Unit tests for Markdown heading outline extractor (S8.1, S12.2)."""

from __future__ import annotations

from kanban.services.markdown_outline import (
    OutlineEntry,
    extract_markdown_outline,
)


def test_empty_markdown() -> None:
    """Empty or whitespace-only markdown produces empty outline."""
    assert extract_markdown_outline("") == []
    assert extract_markdown_outline("   \n\n  ") == []


def test_atx_heading_levels() -> None:
    """Headings from level 1 to level 6 are extracted with correct level and line numbers."""
    md = """# Level 1
Some paragraph text.

## Level 2
### Level 3
#### Level 4
##### Level 5
###### Level 6
####### Not a heading (7 hashes)
"""
    outline = extract_markdown_outline(md)
    assert len(outline) == 6
    assert [e.level for e in outline] == [1, 2, 3, 4, 5, 6]
    assert [e.text for e in outline] == [
        "Level 1",
        "Level 2",
        "Level 3",
        "Level 4",
        "Level 5",
        "Level 6",
    ]
    assert [e.anchor for e in outline] == [
        "level-1",
        "level-2",
        "level-3",
        "level-4",
        "level-5",
        "level-6",
    ]
    assert [e.start_line for e in outline] == [1, 4, 5, 6, 7, 8]


def test_duplicate_slug_deduplication() -> None:
    """Duplicate heading titles append monotonic numeric suffix (GitHub slug convention)."""
    md = """# H1
## PKCE (S256)
## PKCE (S256)
## PKCE (S256)
"""
    outline = extract_markdown_outline(md)
    assert len(outline) == 4
    assert outline[0].text == "H1"
    assert outline[0].anchor == "h1"
    assert outline[1].text == "PKCE (S256)"
    assert outline[1].anchor == "pkce-s256"
    assert outline[2].text == "PKCE (S256)"
    assert outline[2].anchor == "pkce-s256-1"
    assert outline[3].text == "PKCE (S256)"
    assert outline[3].anchor == "pkce-s256-2"


def test_fenced_code_blocks_ignored() -> None:
    """Headings inside backtick and tilde fences are ignored, including variable fence lengths."""
    md = """# Real Heading

```python
# This is a comment, not an outline heading
## Neither is this
```

## Another Real Heading

~~~~markdown
# Inside tilde fence
~~~~

````markdown
```
# Inside nested fence
```
````

### Final Heading
"""
    outline = extract_markdown_outline(md)
    assert len(outline) == 3
    assert [e.text for e in outline] == ["Real Heading", "Another Real Heading", "Final Heading"]
    assert [e.anchor for e in outline] == ["real-heading", "another-real-heading", "final-heading"]
    assert [e.start_line for e in outline] == [1, 8, 20]


def test_html_comments_ignored() -> None:
    """Headings inside single-line and multiline HTML comments are ignored."""
    md = """# Start

<!-- # Single Line Comment Heading -->

<!--
# Multi Line Comment Heading
## Another Hidden
-->

## End
"""
    outline = extract_markdown_outline(md)
    assert len(outline) == 2
    assert [e.text for e in outline] == ["Start", "End"]
    assert [e.anchor for e in outline] == ["start", "end"]
    assert [e.start_line for e in outline] == [1, 10]


def test_inline_formatting_stripped_from_display_and_slug() -> None:
    """Inline code, bold, italic, strikethrough, links, and images are stripped."""
    md = """# Heading with `inline code`
## Heading with **bold** and *italic* text
### Heading with ~~strikethrough~~
#### The [OAuth 2.0 Spec](https://tools.ietf.org/html/rfc6749) Guide
##### Logo ![Icon](https://example.com/icon.png) Overview
## Trailing Hashes Heading ##
"""
    outline = extract_markdown_outline(md)
    assert len(outline) == 6
    assert outline[0].text == "Heading with inline code"
    assert outline[0].anchor == "heading-with-inline-code"
    assert outline[1].text == "Heading with bold and italic text"
    assert outline[1].anchor == "heading-with-bold-and-italic-text"
    assert outline[2].text == "Heading with strikethrough"
    assert outline[2].anchor == "heading-with-strikethrough"
    assert outline[3].text == "The OAuth 2.0 Spec Guide"
    assert outline[3].anchor == "the-oauth-20-spec-guide"
    assert outline[4].text == "Logo Icon Overview"
    assert outline[4].anchor == "logo-icon-overview"
    assert outline[5].text == "Trailing Hashes Heading"
    assert outline[5].anchor == "trailing-hashes-heading"


def test_fallback_slug_for_non_alphanumeric() -> None:
    """Titles with only symbols/formatting fall back to 'section' slug."""
    md = """# !!! ???
# @@@ ###
"""
    outline = extract_markdown_outline(md)
    assert len(outline) == 2
    assert outline[0].anchor == "section"
    assert outline[1].anchor == "section-1"


def test_outline_entry_to_dict() -> None:
    """OutlineEntry converts cleanly to dictionary representation."""
    entry = OutlineEntry(level=2, text="Overview", anchor="overview", start_line=14)
    data = entry.to_dict()
    assert data == {
        "level": 2,
        "text": "Overview",
        "anchor": "overview",
        "start_line": 14,
    }
