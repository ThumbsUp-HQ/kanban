"""Unit tests for server-side SVG sanitizer (svg_sanitizer.py).

Verifies all 8 mandatory feature test case groups from KB-P2-14:
1. Positive clean diagram (Mermaid/architecture elements sanitize and re-parse as valid XML).
2. Active content strip (scripts, foreignObject, style, SMIL animations, on* event handlers).
3. External SSRF and tracking pixel strip (image tags, external href, data: URIs, external url()).
4. XXE and billion-laughs prevention (DOCTYPE, ENTITY, CDATA, xml-stylesheet rejected pre-parse).
5. Cycle detection in <use> graphs (self-reference and mutual cycles).
6. <use> reference depth boundary (depth 4 succeeds, depth 5 raises SVG_USE_DEPTH_EXCEEDED).
7. <use> expansion cap boundary (500 nodes succeeds, 501 raises SVG_EXPANSION_LIMIT_EXCEEDED).
8. Boundaries: size cap (2 MiB), UTF-16/32 BOMs, duplicate IDs, non-SVG root element.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
from xml.etree.ElementTree import Element

import defusedxml.common
import pytest
from defusedxml.ElementTree import fromstring

from kanban.content.svg_dag import (
    ERR_SVG_EXPANSION_LIMIT_EXCEEDED,
    ERR_SVG_USE_CYCLE,
    ERR_SVG_USE_DEPTH_EXCEEDED,
    SvgSanitizeError,
    _get_element_references,
    _get_local_tag,
)
from kanban.content.svg_sanitizer import (
    DEFAULT_MAX_SVG_BYTES,
    ERR_SVG_COMPLEXITY_EXCEEDED,
    ERR_SVG_DIMENSIONS_INVALID,
    ERR_SVG_DTD_OR_ENTITY_FORBIDDEN,
    ERR_SVG_DUPLICATE_ID,
    ERR_SVG_INVALID_UTF8,
    ERR_SVG_MALFORMED_XML,
    ERR_SVG_ROOT_INVALID,
    ERR_SVG_SIZE_INVALID,
    SvgSanitizeReport,
    _get_local_name,
    _parse_and_validate_xml_root,
    sanitize_svg,
    sanitize_svg_with_report,
)

# ---------------------------------------------------------------------------
# Case 1: Positive clean diagram
# ---------------------------------------------------------------------------


def test_case_1_positive_clean_diagram() -> None:
    """Mermaid-style SVG with allowed vector elements sanitizes and re-parses as valid XML."""
    clean_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 800 600" width="800" height="600">'
        "  <defs>"
        '    <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">'
        '      <stop offset="0%" stop-color="#ff0000" stop-opacity="1"/>'
        '      <stop offset="100%" stop-color="#0000ff" stop-opacity="1"/>'
        "    </linearGradient>"
        '    <clipPath id="clip1">'
        '      <rect x="0" y="0" width="100" height="100"/>'
        "    </clipPath>"
        '    <marker id="arrow" markerWidth="10" markerHeight="10" '
        'refX="5" refY="5" orient="auto">'
        '      <path d="M 0 0 L 10 5 L 0 10 z" fill="#000"/>'
        "    </marker>"
        '    <g id="node-box">'
        '      <rect width="120" height="40" rx="5" ry="5" fill="url(#grad1)"/>'
        '      <circle cx="10" cy="10" r="5" fill="#fff"/>'
        '      <text x="20" y="25" font-family="sans-serif" font-size="14">'
        "        Service Node"
        '        <tspan dx="5" font-weight="bold">v1</tspan>'
        "      </text>"
        "    </g>"
        "  </defs>"
        "  <title>Architecture Flow</title>"
        "  <desc>System interaction diagram</desc>"
        '  <g id="canvas" clip-path="url(#clip1)">'
        '    <use href="#node-box" x="50" y="50"/>'
        '    <path d="M 170 70 L 300 70" stroke="#333" stroke-width="2" '
        'marker-end="url(#arrow)"/>'
        '    <polyline points="0,0 50,25 50,75 0,100" stroke="#666" fill="none"/>'
        '    <polygon points="100,100 150,25 150,75 200,0" fill="#eee" stroke="#333"/>'
        '    <line x1="10" y1="10" x2="100" y2="100" stroke="#999"/>'
        "  </g>"
        "</svg>"
    )

    report = sanitize_svg_with_report(clean_svg)
    assert isinstance(report, SvgSanitizeReport)
    assert report.stripped_elements == 0
    assert report.stripped_attrs == 0
    assert report.max_use_depth == 1
    assert report.expanded_nodes < 50
    assert report.output_svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')

    # Re-parsing output verifies that it is strictly valid XML
    reparsed = fromstring(report.output_svg)
    assert reparsed.tag in ("svg", "{http://www.w3.org/2000/svg}svg")
    assert "viewBox" in reparsed.attrib


# ---------------------------------------------------------------------------
# Case 2: Security (active content strip)
# ---------------------------------------------------------------------------


def test_case_2_security_active_content_strip() -> None:
    """Scripts, foreignObjects, styles, SMIL animations, and on* handlers are stripped."""
    hostile_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '  <rect id="safe-sibling-1" width="100" height="100" fill="green"/>'
        "  <script>alert('xss-1')</script>"
        '  <foreignObject width="100" height="100">'
        '    <body xmlns="http://www.w3.org/1999/xhtml" onload="alert(\'xss-2\')">'
        "      <p>evil</p>"
        "    </body>"
        "  </foreignObject>"
        '  <iframe src="https://evil.example/payload"></iframe>'
        "  <style>@import url(https://evil.example/x.css); body { color: red; }</style>"
        '  <animate attributeName="href" to="javascript:alert(\'xss-3\')"/>'
        '  <set attributeName="fill" to="red"/>'
        "  <a href=\"javascript:alert('xss-4')\">"
        '    <rect id="evil-a-child" width="10" height="10"/>'
        "  </a>"
        '  <rect id="safe-sibling-2" width="50" height="50" '
        'onclick="alert(1)" onload="alert(2)"/>'
        "</svg>"
    )

    sanitized = sanitize_svg(hostile_svg)

    # All active scripting keywords and tags are completely absent
    assert "script" not in sanitized.lower()
    assert "foreignobject" not in sanitized.lower()
    assert "iframe" not in sanitized.lower()
    assert "style" not in sanitized.lower()
    assert "animate" not in sanitized.lower()
    assert "<set" not in sanitized.lower()
    assert "<a" not in sanitized.lower()
    assert "onclick" not in sanitized.lower()
    assert "onload" not in sanitized.lower()
    assert "alert" not in sanitized
    assert "javascript:" not in sanitized

    # Sibling safe geometry is preserved
    assert "safe-sibling-1" in sanitized
    assert "safe-sibling-2" in sanitized
    # Child of stripped <a> is also gone
    assert "evil-a-child" not in sanitized


# ---------------------------------------------------------------------------
# Case 3: Security (external SSRF / tracking pixel)
# ---------------------------------------------------------------------------


def test_case_3_security_external_ssrf_and_tracking_pixel() -> None:
    """External image references, sprite hrefs, and data URIs are completely stripped."""
    ssrf_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '  <image href="https://169.254.169.254/latest/meta-data" width="100" height="100"/>'
        '  <use xlink:href="https://evil.example/sprite.svg#x"/>'
        '  <use href="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="/>'
        '  <rect id="r1" width="100" height="100" fill="url(https://evil.example/p#g)"/>'
        "</svg>"
    )

    sanitized = sanitize_svg(ssrf_svg)

    # 0 occurrences of external network protocols, cloud IMDS, or data URIs
    # (excluding standard xmlns="http://www.w3.org/2000/svg" SVG namespace)
    non_ns_content = sanitized.replace("http://www.w3.org/2000/svg", "")
    assert "http" not in non_ns_content.lower()
    assert "169.254" not in non_ns_content
    assert "data:" not in non_ns_content
    assert "evil.example" not in non_ns_content
    assert "image" not in non_ns_content.lower()

    # The safe geometry element is preserved without the tainted fill
    assert 'id="r1"' in sanitized
    assert "fill=" not in sanitized


# ---------------------------------------------------------------------------
# Case 4: Security (XXE & XML billion laughs)
# ---------------------------------------------------------------------------


def test_case_4_security_xxe_and_entity_expansion_forbidden() -> None:
    """DOCTYPE and ENTITY declarations fail closed with SVG_DTD_OR_ENTITY_FORBIDDEN."""
    xxe_svg = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<!DOCTYPE svg ["
        '  <!ENTITY xxe SYSTEM "file:///etc/passwd">'
        "]>"
        '<svg xmlns="http://www.w3.org/2000/svg"><text>&xxe;</text></svg>'
    )
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(xxe_svg)
    assert exc_info.value.code == ERR_SVG_DTD_OR_ENTITY_FORBIDDEN

    quadratic_svg = (
        "<!DOCTYPE svg ["
        '  <!ENTITY lol "lol">'
        '  <!ENTITY lol2 "&lol;&lol;">'
        '  <!ENTITY lol3 "&lol2;&lol2;">'
        "]>"
        '<svg xmlns="http://www.w3.org/2000/svg"><text>&lol3;</text></svg>'
    )
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(quadratic_svg)
    assert exc_info.value.code == ERR_SVG_DTD_OR_ENTITY_FORBIDDEN

    cdata_svg = '<svg xmlns="http://www.w3.org/2000/svg"><![CDATA[test]]></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(cdata_svg)
    assert exc_info.value.code == ERR_SVG_DTD_OR_ENTITY_FORBIDDEN

    stylesheet_svg = '<?xml-stylesheet type="text/xsl" href="x.xsl"?><svg/>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(stylesheet_svg)
    assert exc_info.value.code == ERR_SVG_DTD_OR_ENTITY_FORBIDDEN


# ---------------------------------------------------------------------------
# Case 5: Security (<use> cycle)
# ---------------------------------------------------------------------------


def test_case_5_security_use_cycle_detected() -> None:
    """Direct self-reference and mutual cycles raise SVG_USE_CYCLE."""
    self_cycle_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">  <g id="a"><use href="#a"/></g></svg>'
    )
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(self_cycle_svg)
    assert exc_info.value.code == ERR_SVG_USE_CYCLE

    mutual_cycle_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '  <g id="a"><use href="#b"/></g>'
        '  <g id="b"><use href="#a"/></g>'
        "</svg>"
    )
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(mutual_cycle_svg)
    assert exc_info.value.code == ERR_SVG_USE_CYCLE


# ---------------------------------------------------------------------------
# Case 6: Boundary (<use> depth cap <= 4)
# ---------------------------------------------------------------------------


def test_case_6_boundary_use_depth_cap() -> None:
    """Chain u1->u2->u3->u4->rect with depth 4 passes; adding u0 raises SVG_USE_DEPTH_EXCEEDED."""
    depth_4_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        "  <defs>"
        '    <rect id="rect" width="10" height="10"/>'
        '    <use id="u4" href="#rect"/>'
        '    <use id="u3" href="#u4"/>'
        '    <use id="u2" href="#u3"/>'
        "  </defs>"
        '  <use id="u1" href="#u2"/>'
        "</svg>"
    )
    report = sanitize_svg_with_report(depth_4_svg)
    assert report.max_use_depth == 4

    depth_5_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        "  <defs>"
        '    <rect id="rect" width="10" height="10"/>'
        '    <use id="u4" href="#rect"/>'
        '    <use id="u3" href="#u4"/>'
        '    <use id="u2" href="#u3"/>'
        '    <use id="u1" href="#u2"/>'
        "  </defs>"
        '  <use id="u0" href="#u1"/>'
        "</svg>"
    )
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(depth_5_svg)
    assert exc_info.value.code == ERR_SVG_USE_DEPTH_EXCEEDED


# ---------------------------------------------------------------------------
# Case 7: Boundary (<use> expansion cap <= 500)
# ---------------------------------------------------------------------------


def test_case_7_boundary_use_expansion_cap() -> None:
    """Expansion bomb raises SVG_EXPANSION_LIMIT_EXCEEDED; exactly 500 succeeds; 501 raises."""
    five_l4 = "".join('<use href="#l4"/>' for _ in range(5))
    five_l3 = "".join('<use href="#l3"/>' for _ in range(5))
    five_l2 = "".join('<use href="#l2"/>' for _ in range(5))
    expansion_bomb_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        "  <defs>"
        '    <g id="l4"><rect width="1" height="1"/><rect width="1" height="1"/></g>'
        f'    <g id="l3">{five_l4}</g>'
        f'    <g id="l2">{five_l3}</g>'
        f'    <g id="l1">{five_l2}</g>'
        "  </defs>"
        '  <use href="#l1"/><use href="#l1"/>'
        "</svg>"
    )
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(expansion_bomb_svg)
    assert exc_info.value.code == ERR_SVG_EXPANSION_LIMIT_EXCEEDED

    # Exactly 500 nodes: 1 root + 499 rects
    rects_499 = "".join("<rect/>" for _ in range(499))
    svg_500 = f'<svg xmlns="http://www.w3.org/2000/svg">{rects_499}</svg>'
    report_500 = sanitize_svg_with_report(svg_500)
    assert report_500.expanded_nodes == 500

    # Exactly 501 nodes: 1 root + 500 rects -> raises
    rects_500 = "".join("<rect/>" for _ in range(500))
    svg_501 = f'<svg xmlns="http://www.w3.org/2000/svg">{rects_500}</svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(svg_501)
    assert exc_info.value.code == ERR_SVG_EXPANSION_LIMIT_EXCEEDED


# ---------------------------------------------------------------------------
# Case 8: Boundary (size, encoding & duplicate IDs)
# ---------------------------------------------------------------------------


def test_case_8_boundary_size_encoding_and_duplicate_ids() -> None:
    """Size cap (2 MiB), UTF-16 BOM, duplicate IDs, and non-SVG roots are rejected."""
    base_prefix = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/>'
    base_suffix = "</svg>"
    pad_needed = DEFAULT_MAX_SVG_BYTES - len(base_prefix.encode()) - len(base_suffix.encode())
    svg_exact_2mb = base_prefix + (" " * pad_needed) + base_suffix
    assert len(svg_exact_2mb.encode("utf-8")) == DEFAULT_MAX_SVG_BYTES
    report_2mb = sanitize_svg_with_report(svg_exact_2mb)
    assert report_2mb.input_bytes == DEFAULT_MAX_SVG_BYTES

    svg_oversize = svg_exact_2mb + " "
    assert len(svg_oversize.encode("utf-8")) == DEFAULT_MAX_SVG_BYTES + 1
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(svg_oversize)
    assert exc_info.value.code == ERR_SVG_SIZE_INVALID

    # Empty payload
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg("")
    assert exc_info.value.code == ERR_SVG_SIZE_INVALID

    # UTF-16 LE BOM
    utf16_bytes = b'\xff\xfe<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(utf16_bytes)
    assert exc_info.value.code == ERR_SVG_INVALID_UTF8

    # UTF-16 BE BOM
    utf16_be_bytes = b'\xfe\xff<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(utf16_be_bytes)
    assert exc_info.value.code == ERR_SVG_INVALID_UTF8

    # UTF-32 BOM
    utf32_bytes = b"\xff\xfe\x00\x00<svg></svg>"
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(utf32_bytes)
    assert exc_info.value.code == ERR_SVG_INVALID_UTF8

    # Two elements with duplicate ID
    duplicate_id_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '  <g id="dup"><rect width="10" height="10"/></g>'
        '  <g id="dup"><circle r="5"/></g>'
        "</svg>"
    )
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(duplicate_id_svg)
    assert exc_info.value.code == ERR_SVG_DUPLICATE_ID

    # Non-SVG root element
    html_root = "<html><body><svg><rect/></svg></body></html>"
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(html_root)
    assert exc_info.value.code == ERR_SVG_ROOT_INVALID

    # Foreign namespace root element
    xhtml_svg = '<svg xmlns="http://www.w3.org/1999/xhtml"><rect/></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(xhtml_svg)
    assert exc_info.value.code == ERR_SVG_ROOT_INVALID


# ---------------------------------------------------------------------------
# Hostile SVG Corpus Audit Suite
# ---------------------------------------------------------------------------


def test_hostile_svg_corpus_audit() -> None:
    """Validate all entries in hostile_svgs.json and verify expected strip or reject actions."""
    corpus_path = Path(__file__).parent / "corpus" / "hostile_svgs.json"
    assert corpus_path.is_file(), f"Hostile SVG corpus file not found at {corpus_path}"

    with corpus_path.open("r", encoding="utf-8") as f:
        corpus = json.load(f)

    results: list[dict[str, object]] = []

    for entry in corpus:
        entry_id = entry["id"]
        svg_content = entry["svg"]
        expected_action = entry["expected_action"]

        if expected_action == "reject":
            expected_error = entry["expected_error"]
            with pytest.raises(SvgSanitizeError) as exc_info:
                sanitize_svg(svg_content)
            actual_error = exc_info.value.code
            assert actual_error == expected_error, (
                f"[{entry_id}] Expected error code '{expected_error}', got '{actual_error}'"
            )
            results.append(
                {
                    "id": entry_id,
                    "action": "rejected",
                    "error_code": actual_error,
                    "status": "PASS",
                }
            )
        elif expected_action == "strip":
            report = sanitize_svg_with_report(svg_content)
            for forbidden in entry.get("forbidden_output_substrings", []):
                assert forbidden.lower() not in report.output_svg.lower(), (
                    f"[{entry_id}] Forbidden substring '{forbidden}' found in sanitized output"
                )
            results.append(
                {
                    "id": entry_id,
                    "action": "stripped",
                    "stripped_elements": report.stripped_elements,
                    "stripped_attrs": report.stripped_attrs,
                    "status": "PASS",
                }
            )

    assert len(results) == len(corpus)


# ---------------------------------------------------------------------------
# Dimension, Complexity & Structural Edge Cases
# ---------------------------------------------------------------------------


def test_excessive_viewbox_coordinates_rejected() -> None:
    """ViewBox with dimensions exceeding 32768 raises SVG_DIMENSIONS_INVALID."""
    bad_vb = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50000 50000"><rect/></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(bad_vb)
    assert exc_info.value.code == ERR_SVG_DIMENSIONS_INVALID

    malformed_vb = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100"><rect/></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(malformed_vb)
    assert exc_info.value.code == ERR_SVG_DIMENSIONS_INVALID

    non_numeric_vb = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 foo bar"><rect/></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(non_numeric_vb)
    assert exc_info.value.code == ERR_SVG_DIMENSIONS_INVALID

    negative_vb = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 -100 100"><rect/></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(negative_vb)
    assert exc_info.value.code == ERR_SVG_DIMENSIONS_INVALID


def test_excessive_width_height_coordinates_rejected() -> None:
    """Width or height attributes exceeding 32768 or negative raise SVG_DIMENSIONS_INVALID."""
    bad_w = '<svg xmlns="http://www.w3.org/2000/svg" width="40000"><rect/></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(bad_w)
    assert exc_info.value.code == ERR_SVG_DIMENSIONS_INVALID

    negative_h = '<svg xmlns="http://www.w3.org/2000/svg" height="-50"><rect/></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(negative_h)
    assert exc_info.value.code == ERR_SVG_DIMENSIONS_INVALID


def test_xml_nesting_depth_cap_exceeded() -> None:
    """Nesting depth > 64 raises SVG_COMPLEXITY_EXCEEDED."""
    opening = '<svg xmlns="http://www.w3.org/2000/svg">' + ("<g>" * 65)
    closing = ("</g>" * 65) + "</svg>"
    deep_svg = opening + "<rect/>" + closing
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(deep_svg)
    assert exc_info.value.code == ERR_SVG_COMPLEXITY_EXCEEDED


def test_xml_raw_element_count_cap_exceeded() -> None:
    """Raw element count > 5000 raises SVG_COMPLEXITY_EXCEEDED."""
    rects = "".join("<rect/>" for _ in range(5001))
    oversize_svg = f'<svg xmlns="http://www.w3.org/2000/svg">{rects}</svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(oversize_svg)
    assert exc_info.value.code == ERR_SVG_COMPLEXITY_EXCEEDED


def test_malformed_xml_syntax_raises() -> None:
    """Unclosed XML tags raise SVG_MALFORMED_XML."""
    broken_svg = '<svg xmlns="http://www.w3.org/2000/svg"><g><rect></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(broken_svg)
    assert exc_info.value.code == ERR_SVG_MALFORMED_XML


def test_unicode_surrogate_and_invisible_chars() -> None:
    """Surrogates raise SVG_INVALID_UTF8 while leading BOM and zero-width chars are cleaned."""
    surrogate_svg = '<svg xmlns="http://www.w3.org/2000/svg">\ud800</svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(surrogate_svg)
    assert exc_info.value.code == ERR_SVG_INVALID_UTF8

    bom_cleaned_svg = '\ufeff<svg xmlns="http://www.w3.org/2000/svg"><text>a\u200bb</text></svg>'
    sanitized = sanitize_svg(bom_cleaned_svg)
    assert "\ufeff" not in sanitized
    assert "\u200b" not in sanitized
    assert "ab" in sanitized


def test_invalid_id_format_stripped_safely() -> None:
    """Element with malformed id attribute has id stripped without rejecting document."""
    svg_with_bad_id = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<rect id="123 invalid id" width="10" height="10"/>'
        "</svg>"
    )
    report = sanitize_svg_with_report(svg_with_bad_id)
    assert report.stripped_attrs >= 1
    assert "123 invalid id" not in report.output_svg
    assert "<rect" in report.output_svg


def test_foreign_attribute_stripped() -> None:
    """Foreign namespace and disallowed attributes are stripped."""
    svg_foreign = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'inkscape:version="1.2" xml:base="/secret/" custom-attr="dangerous">'
        '  <rect width="10" height="10"/>'
        "</svg>"
    )
    report = sanitize_svg_with_report(svg_foreign)
    assert "inkscape" not in report.output_svg
    assert "xml:base" not in report.output_svg
    assert "custom-attr" not in report.output_svg


def test_bytes_input_handled_identically() -> None:
    """Bytes input produces identical report to string input."""
    raw_bytes = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
    report = sanitize_svg_with_report(raw_bytes)
    assert report.input_bytes == len(raw_bytes)
    assert "<rect" in report.output_svg


def test_coverage_edge_cases_encoding_and_dimensions() -> None:
    """Exercise encoding, dimensions, and viewBox edge cases."""
    # 1. Invalid UTF-8 raw bytes triggering UnicodeDecodeError
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(b"\x80\x81\x82")
    assert exc_info.value.code == ERR_SVG_INVALID_UTF8

    # 2. UTF-7 BOM signature
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(b"+/v8<svg></svg>")
    assert exc_info.value.code == ERR_SVG_INVALID_UTF8

    # 3. ViewBox width/height exceeding 32768
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50000 100"><rect/></svg>'
        )
    assert exc_info.value.code == ERR_SVG_DIMENSIONS_INVALID

    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50000"><rect/></svg>'
        )
    assert exc_info.value.code == ERR_SVG_DIMENSIONS_INVALID

    # 4. Dimension parsing unparseable string
    svg_bad_dim = '<svg xmlns="http://www.w3.org/2000/svg" width="not_a_number"><rect/></svg>'
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(svg_bad_dim)
    assert exc_info.value.code == ERR_SVG_DIMENSIONS_INVALID


def test_coverage_edge_cases_attributes_and_expansion() -> None:
    """Exercise attributes, namespace handling, and expansion limit branches."""
    # 1. href on element where href is forbidden (e.g. <rect href="#id"/>)
    svg_rect_href = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<rect id="r" href="#r" width="10" height="10"/>'
        "</svg>"
    )
    report = sanitize_svg_with_report(svg_rect_href)
    assert report.stripped_attrs >= 1
    assert "href" not in report.output_svg

    # 2. use with target not in id_map
    svg_use_missing = '<svg xmlns="http://www.w3.org/2000/svg"><use href="#nonexistent"/></svg>'
    report_missing = sanitize_svg_with_report(svg_use_missing)
    assert report_missing.stripped_attrs >= 1
    assert "href" not in report_missing.output_svg

    # 3. Paint attribute with forbidden CSS tokens (expression, javascript:, @import, image-set)
    svg_expr = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<rect fill="expression(alert(1))" stroke="javascript:void(0)"/>'
        "</svg>"
    )
    report_expr = sanitize_svg_with_report(svg_expr)
    assert report_expr.stripped_attrs >= 2
    assert "expression" not in report_expr.output_svg
    assert "javascript" not in report_expr.output_svg

    # 4. Paint attribute with url(#nonexistent) pointing to missing target
    svg_paint_missing = (
        '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(#missing_target)"/></svg>'
    )
    report_paint_missing = sanitize_svg_with_report(svg_paint_missing)
    assert report_paint_missing.stripped_attrs >= 1
    assert "fill" not in report_paint_missing.output_svg

    # 5. Foreign namespace attribute starting with {
    svg_foreign_ns_attr = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<rect xmlns:custom="http://custom.example" custom:attr="val"/>'
        "</svg>"
    )
    report_foreign = sanitize_svg_with_report(svg_foreign_ns_attr)
    assert report_foreign.stripped_attrs >= 1
    assert "custom" not in report_foreign.output_svg

    # 6. Expansion limit exceeded inside child expansion loop
    rects_child_overflow = "".join("<rect/>" for _ in range(505))
    svg_child_overflow = (
        f'<svg xmlns="http://www.w3.org/2000/svg"><g>{rects_child_overflow}</g></svg>'
    )
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(svg_child_overflow)
    assert exc_info.value.code == ERR_SVG_EXPANSION_LIMIT_EXCEEDED

    # 7. Expansion limit exceeded inside use target expansion loop
    rects_500 = "".join("<rect/>" for _ in range(500))
    svg_target_overflow = (
        f'<svg xmlns="http://www.w3.org/2000/svg"><defs><g id="big">{rects_500}</g></defs>'
        '<use href="#big"/></svg>'
    )
    with pytest.raises(SvgSanitizeError) as exc_info:
        sanitize_svg(svg_target_overflow)
    assert exc_info.value.code == ERR_SVG_EXPANSION_LIMIT_EXCEEDED

    # 12. Element having both href and xlink:href
    svg_both_href = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<defs><rect id="t1"/><rect id="t2"/></defs>'
        '<use href="#t1" xlink:href="#t2"/></svg>'
    )
    report_both = sanitize_svg_with_report(svg_both_href)
    assert 'href="#t1"' in report_both.output_svg

    # 13. Helper functions unit tests
    assert _get_local_name("{http://example.com/ns}custom") == "custom"
    assert _get_local_tag("{http://example.com/ns}rect") == "rect"

    # Test _get_element_references with missing target
    dummy_elem = Element("rect", {"fill": "url(#missing)"})
    refs = _get_element_references(dummy_elem, {})
    assert len(refs) == 0

    # Test defusedxml exception catching in _parse_and_validate_xml_root
    exc = defusedxml.common.DTDForbidden("foo", "bar", "baz")
    with patch("defusedxml.ElementTree.fromstring", side_effect=exc):
        with pytest.raises(SvgSanitizeError) as exc_info:
            _parse_and_validate_xml_root("<svg/>")
        assert exc_info.value.code == ERR_SVG_DTD_OR_ENTITY_FORBIDDEN
