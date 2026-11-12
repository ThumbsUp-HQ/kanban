"""Comprehensive coverage boost tests for kanban/content.

Exercises edge cases, branching conditions, and secondary paths to ensure
>= 95% branch and statement test coverage across all content modules.
"""

from __future__ import annotations

from kanban.content.hidden_dom import (
    _check_color_and_clip,
    _check_opacity_and_font,
    _check_zero_box_and_position,
    _parse_hex_color,
    parse_css_color,
)
from kanban.content.html_to_gfm import (
    _attribute_filter,
    _extract_url_from_target,
    _url_relative_filter,
    disarm_dangerous_markdown_links,
    nh3_sanitize_and_serialize_gfm,
)
from kanban.content.normalize import (
    _detect_and_bypass_ide_wrapper,
    _extract_non_code_text,
    normalize_inspect,
    normalize_to_markdown,
)


def test_html_to_gfm_attribute_and_url_filters() -> None:
    """Exercise _attribute_filter and _url_relative_filter edge cases."""
    assert _attribute_filter("code", "class", "language-rust") == "language-rust"
    assert _attribute_filter("code", "class", "invalid class name!") is None
    assert _attribute_filter("input", "type", "checkbox") == "checkbox"
    assert _attribute_filter("input", "type", "text") is None
    assert _attribute_filter("a", "title", "some title") == "some title"

    assert _url_relative_filter("#heading") == "#heading"
    assert _url_relative_filter("/safe/path") == "/safe/path"
    assert _url_relative_filter("//evil.com") is None
    assert _url_relative_filter("/\\evil.com") is None
    assert _url_relative_filter("relative/path/no/slash") is None


def test_extract_url_from_target_variations() -> None:
    """Exercise _extract_url_from_target with angle brackets and titles."""
    assert _extract_url_from_target("<https://example.com/page>") == "https://example.com/page"
    assert _extract_url_from_target('https://example.com "title"') == "https://example.com"
    assert _extract_url_from_target("") == ""


def test_disarm_links_parenthesis_and_unclosed_brackets() -> None:
    """Exercise edge cases in markdown link scanning."""
    assert disarm_dangerous_markdown_links("Text [unclosed bracket")[0] == "Text [unclosed bracket"
    assert disarm_dangerous_markdown_links("Text [label](unclosed")[0] == "Text [label](unclosed"
    balanced = "Link [wiki](https://en.wikipedia.org/wiki/Foo_(bar)) is safe."
    out, count = disarm_dangerous_markdown_links(balanced)
    assert count == 0
    assert "(https://en.wikipedia.org/wiki/Foo_(bar))" in out


def test_disarm_links_with_tilde_fences() -> None:
    """Exercise tilde code fences in link disarmer."""
    md = "~~~python\n[bad](javascript:alert(1))\n~~~\n[bad](javascript:alert(2))"
    out, count = disarm_dangerous_markdown_links(md)
    assert count == 1
    assert "~~~python\n[bad](javascript:alert(1))\n~~~" in out
    assert "bad" in out


def test_html_to_gfm_inline_formatting_edge_cases() -> None:
    """Exercise inline elements: del, s, em, i, b, code with backticks."""
    html_input = (
        "<p>"
        "<b>bold1</b> and <strong>bold2</strong> "
        "<i>italic1</i> and <em>italic2</em> "
        "<del>del</del> and <s>strike</s> "
        "<code>plain_code</code> and <code>code with ` backtick</code>"
        "</p>"
    )
    gfm = nh3_sanitize_and_serialize_gfm(html_input)
    assert "**bold1**" in gfm
    assert "**bold2**" in gfm
    assert "*italic1*" in gfm
    assert "*italic2*" in gfm
    assert "~~del~~" in gfm
    assert "~~strike~~" in gfm
    assert "`plain_code`" in gfm
    assert "`` code with ` backtick ``" in gfm


def test_html_to_gfm_headings_all_levels() -> None:
    """Exercise headings h1 through h6."""
    html_input = "<h1>H1</h1><h2>H2</h2><h3>H3</h3><h4>H4</h4><h5>H5</h5><h6>H6</h6>"
    gfm = nh3_sanitize_and_serialize_gfm(html_input)
    assert "# H1" in gfm
    assert "## H2" in gfm
    assert "### H3" in gfm
    assert "#### H4" in gfm
    assert "##### H5" in gfm
    assert "###### H6" in gfm


def test_html_to_gfm_pre_without_code_class() -> None:
    """Exercise <pre> blocks without class or language."""
    html_input = "<pre>raw unformatted pre text</pre>"
    gfm = nh3_sanitize_and_serialize_gfm(html_input)
    assert "```\nraw unformatted pre text\n```" in gfm

    html_with_code = "<pre><code>print('hello')</code></pre>"
    gfm2 = nh3_sanitize_and_serialize_gfm(html_with_code)
    assert "```\nprint('hello')\n```" in gfm2


def test_html_to_gfm_details_and_summary() -> None:
    """Exercise <details> and <summary> conversion."""
    html_input = (
        "<details><summary>Technical Details</summary><p>Detailed explanation here.</p></details>"
    )
    gfm = nh3_sanitize_and_serialize_gfm(html_input)
    assert "<details>" in gfm
    assert "<summary>Technical Details</summary>" in gfm
    assert "Detailed explanation here." in gfm
    assert "</details>" in gfm


def test_html_to_gfm_images_and_links() -> None:
    """Exercise images with safe vs unsafe schemes and links without href."""
    html_input = (
        '<p><img src="https://example.com/logo.png" alt="Logo">'
        '<img src="javascript:alert(1)" alt="Malicious">'
        '<img alt="No src">'
        '<a href="https://example.com">Safe Link</a>'
        '<a href="javascript:alert(1)">Unsafe Link</a>'
        "<a>Link with no href</a></p>"
    )
    gfm = nh3_sanitize_and_serialize_gfm(html_input)
    assert "![Logo](https://example.com/logo.png)" in gfm
    assert "javascript:" not in gfm
    assert "[Safe Link](https://example.com)" in gfm
    assert "Unsafe Link" in gfm
    assert "Link with no href" in gfm


def test_html_to_gfm_table_empty_and_no_header() -> None:
    """Exercise empty tables and tables without thead."""
    html_empty = "<table></table>"
    assert nh3_sanitize_and_serialize_gfm(html_empty) == ""

    html_no_head = "<table><tr><td>Cell 1</td><td>Cell 2</td></tr></table>"
    gfm = nh3_sanitize_and_serialize_gfm(html_no_head)
    assert "| Cell 1 | Cell 2 |" in gfm
    assert "| --- | --- |" in gfm


def test_html_to_gfm_ordered_lists_and_tasks() -> None:
    """Exercise ordered lists and task checkboxes."""
    html_input = (
        "<ol>"
        "<li>First</li>"
        "<li>Second</li>"
        "</ol>"
        "<ul>"
        "<li><input type='checkbox'> Unchecked</li>"
        "<li><input type='checkbox' checked> Checked</li>"
        "</ul>"
    )
    gfm = nh3_sanitize_and_serialize_gfm(html_input)
    assert "1. First" in gfm
    assert "2. Second" in gfm
    assert "- [ ] Unchecked" in gfm
    assert "- [x] Checked" in gfm


def test_ide_detector_negative_cases() -> None:
    """Exercise negative branch conditions in _detect_and_bypass_ide_wrapper."""
    is_ide, _ = _detect_and_bypass_ide_wrapper("<div>1</div><div>2</div>")
    assert not is_ide

    is_ide, _ = _detect_and_bypass_ide_wrapper("<p><span>text</span></p>")
    assert not is_ide

    is_ide, _ = _detect_and_bypass_ide_wrapper("<div><span>text</span><a href='#'>link</a></div>")
    assert not is_ide

    is_ide, _ = _detect_and_bypass_ide_wrapper("<div><span>text</span><section>s</section></div>")
    assert not is_ide


def test_ide_detector_div_lines() -> None:
    """Exercise nested div line extraction in IDE detector."""
    html_input = "<div><div>line 1</div><div>line 2</div><br><div>line 3</div></div>"
    is_ide, code = _detect_and_bypass_ide_wrapper(html_input)
    assert is_ide
    assert "line 1\nline 2\n\nline 3" in code


def test_normalize_markdown_with_tilde_fences() -> None:
    """Exercise markdown mode with tilde code fences and inline spans."""
    md = (
        "Text outside\n"
        "~~~python\n"
        "def foo():\n"
        "    return '<script>safe inside code</script>'\n"
        "~~~\n"
        "Back outside with `inline <tag> code` and <b>bold HTML</b>."
    )
    report = normalize_inspect(md, mode="markdown")
    assert "<script>safe inside code</script>" in report.output_markdown
    assert "`inline <tag> code`" in report.output_markdown
    assert "bold HTML" in report.output_markdown


def test_normalize_modes_explicit() -> None:
    """Exercise explicit mode='html' and mode='markdown'."""
    html_input = "<h2>Title</h2><p>Paragraph</p>"
    md_out = normalize_to_markdown(html_input, mode="html")
    assert "## Title" in md_out

    plain_md = "# Title\n\nParagraph text."
    md_out2 = normalize_to_markdown(plain_md, mode="markdown")
    assert "# Title" in md_out2


def test_html_to_gfm_blockquote_and_breaks() -> None:
    """Exercise blockquotes, br, hr, and nested block elements."""
    html_input = (
        "<blockquote><p>First line</p><p>Second line</p></blockquote>"
        "<p>Before break<br>After break</p>"
        "<hr>"
    )
    gfm = nh3_sanitize_and_serialize_gfm(html_input)
    assert "> First line" in gfm
    assert "> Second line" in gfm
    assert "Before break\nAfter break" in gfm
    assert "---" in gfm


def test_extract_non_code_text_with_inline_and_fenced() -> None:
    """Exercise _extract_non_code_text with inline backtick spans and code blocks."""
    text = (
        "Here is text with `inline code` and ``double backtick`` span.\n"
        "```python\n"
        "<div hidden>CANARY</div>\n"
        "```\n"
        "Final text after fence with `span`."
    )
    non_code = _extract_non_code_text(text)
    assert "inline code" not in non_code
    assert "<div hidden>" not in non_code
    assert "Here is text with" in non_code
    assert "Final text after fence" in non_code


def test_hidden_dom_color_and_font_branches() -> None:
    """Exercise internal helper branches in hidden_dom."""
    assert _parse_hex_color("12345") is None

    assert parse_css_color("currentcolor") is None
    assert parse_css_color("inherit") is None
    assert parse_css_color("initial") is None
    assert parse_css_color("") is None

    is_bad, _ = _check_opacity_and_font({"opacity": "50%"})
    assert not is_bad

    is_bad, _ = _check_opacity_and_font({"font-size": "14px"})
    assert not is_bad

    is_bad, _ = _check_color_and_clip({"color": "rgba(0,0,0,0.8)"})
    assert not is_bad

    is_bad, _ = _check_color_and_clip({"color": "rgba(0,0,0,80%)"})
    assert not is_bad

    is_bad, _ = _check_color_and_clip({"clip-path": "inset(10%)"})
    assert not is_bad

    is_bad, _ = _check_zero_box_and_position({"height": "100px", "overflow": "hidden"})
    assert not is_bad

    is_bad, _ = _check_zero_box_and_position({"left": "50px", "top": "100px"})
    assert not is_bad
