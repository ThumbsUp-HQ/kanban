"""Unit tests for SVG <use> and gradient acyclic DAG validation (svg_dag.py).

Tests:
1. Acyclic DAG traversal with valid single and multi-level references.
2. Exact <use> reference depth boundary (depth=4 succeeds, depth=5 raises SVG_USE_DEPTH_EXCEEDED).
3. Exact rendered node expansion boundary (500 succeeds, 501 raises SVG_EXPANSION_LIMIT_EXCEEDED).
4. Cycle detection across self-references, mutual cycles, and ancestor containment.
5. Reference edges from href and paint url(#id) attributes.
6. SvgDagResult integer behavior and SvgSanitizeError exception contracts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from defusedxml.ElementTree import fromstring

from kanban.content.svg_dag import (
    ERR_SVG_EXPANSION_LIMIT_EXCEEDED,
    ERR_SVG_USE_CYCLE,
    ERR_SVG_USE_DEPTH_EXCEEDED,
    MAX_SVG_EXPANDED_NODES,
    MAX_SVG_USE_DEPTH,
    SvgDagResult,
    SvgSanitizeError,
    validate_svg_use_dag,
)

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


def _build_id_map(root: Element) -> dict[str, Element]:
    """Collect id to Element mapping across the tree."""
    return {elem.attrib["id"]: elem for elem in root.iter() if "id" in elem.attrib}


def test_svg_dag_result_integer_behavior() -> None:
    """SvgDagResult behaves as an integer while exposing DAG metrics."""
    result = SvgDagResult(expanded_nodes=42, max_use_depth=3)
    assert isinstance(result, int)
    assert result == 42
    assert result.expanded_nodes == 42
    assert result.max_use_depth == 3
    assert result < 50
    assert result + 8 == 50


def test_svg_sanitize_error_attributes() -> None:
    """SvgSanitizeError carries code, message, and string representation."""
    err = SvgSanitizeError("SVG_CUSTOM_CODE", "Custom error message")
    assert err.code == "SVG_CUSTOM_CODE"
    assert err.message == "Custom error message"
    assert str(err) == "Custom error message"

    err_default = SvgSanitizeError("SVG_DEFAULT_CODE")
    assert err_default.code == "SVG_DEFAULT_CODE"
    assert err_default.message == "SVG_DEFAULT_CODE"
    assert str(err_default) == "SVG_DEFAULT_CODE"


def test_clean_svg_without_references() -> None:
    """SVG with no <use> references returns node count and depth 0."""
    xml_data = "<svg><g><rect/><circle/></g><path/></svg>"
    root = fromstring(xml_data)
    result = validate_svg_use_dag(root)
    # root (1) + g (1) + rect (1) + circle (1) + path (1) = 5 nodes
    assert result == 5
    assert result.expanded_nodes == 5
    assert result.max_use_depth == 0


def test_clean_single_level_use_reference() -> None:
    """Single level <use href="#box"/> computes correct expansion and depth 1."""
    xml_data = (
        "<svg>"
        "  <defs>"
        '    <rect id="box" width="10" height="10"/>'
        "  </defs>"
        '  <use href="#box"/>'
        "</svg>"
    )
    root = fromstring(xml_data)
    id_map = _build_id_map(root)
    result = validate_svg_use_dag(root, id_map=id_map)
    # root(1) + defs(1) + box(1) + use(1 + box=1 -> 2) = 5 nodes
    assert result == 5
    assert result.max_use_depth == 1


def test_multiple_independent_uses_share_target() -> None:
    """Multiple <use> tags referencing the same target do not trigger cycles."""
    xml_data = (
        "<svg>"
        "  <defs>"
        '    <circle id="dot" r="5"/>'
        "  </defs>"
        '  <use href="#dot" x="10"/>'
        '  <use href="#dot" x="20"/>'
        '  <use href="#dot" x="30"/>'
        "</svg>"
    )
    root = fromstring(xml_data)
    result = validate_svg_use_dag(root)
    # root(1) + defs(1) + dot(1) + 3 * use(1 + 1 = 2) = 9 nodes
    assert result == 9
    assert result.max_use_depth == 1


def test_depth_chain_4_succeeds() -> None:
    """Chain u1 -> u2 -> u3 -> u4 -> rect with depth 4 passes boundary validation."""
    root = fromstring(
        "<svg>"
        "  <defs>"
        '    <rect id="target" width="10" height="10"/>'
        '    <use id="u3" href="#target"/>'
        '    <use id="u2" href="#u3"/>'
        '    <use id="u1" href="#u2"/>'
        "  </defs>"
        '  <use id="u0" href="#u1"/>'
        "</svg>"
    )
    result = validate_svg_use_dag(root, max_depth=4)
    # u0 (1) -> u1 (2) -> u2 (3) -> u3 (4) -> target (0)
    assert result.max_use_depth == 4


def test_depth_chain_5_raises_use_depth_exceeded() -> None:
    """Adding an additional hop to create depth 5 raises SVG_USE_DEPTH_EXCEEDED."""
    xml_data = (
        "<svg>"
        "  <defs>"
        '    <rect id="target" width="10" height="10"/>'
        '    <use id="u4" href="#target"/>'
        '    <use id="u3" href="#u4"/>'
        '    <use id="u2" href="#u3"/>'
        '    <use id="u1" href="#u2"/>'
        "  </defs>"
        '  <use id="u0" href="#u1"/>'
        "</svg>"
    )
    root = fromstring(xml_data)
    with pytest.raises(SvgSanitizeError) as exc_info:
        validate_svg_use_dag(root, max_depth=MAX_SVG_USE_DEPTH)
    assert exc_info.value.code == ERR_SVG_USE_DEPTH_EXCEEDED


def test_exact_500_expansion_succeeds() -> None:
    """SVG expanding to exactly 500 rendered nodes succeeds."""
    # root <svg> is 1 node. 499 child <rect/> elements make exactly 500 nodes.
    rects = "".join("<rect/>" for _ in range(499))
    xml_data = f"<svg>{rects}</svg>"
    root = fromstring(xml_data)
    result = validate_svg_use_dag(root, max_expanded_nodes=MAX_SVG_EXPANDED_NODES)
    assert result == 500
    assert result.expanded_nodes == 500


def test_501_expansion_raises_expansion_limit_exceeded() -> None:
    """SVG expanding to 501 rendered nodes raises SVG_EXPANSION_LIMIT_EXCEEDED."""
    # root <svg> is 1 node. 500 child <rect/> elements make 501 nodes.
    rects = "".join("<rect/>" for _ in range(500))
    xml_data = f"<svg>{rects}</svg>"
    root = fromstring(xml_data)
    with pytest.raises(SvgSanitizeError) as exc_info:
        validate_svg_use_dag(root, max_expanded_nodes=MAX_SVG_EXPANDED_NODES)
    assert exc_info.value.code == ERR_SVG_EXPANSION_LIMIT_EXCEEDED


def test_use_expansion_exact_500_nodes() -> None:
    """SVG using <use> tags expanding to exactly 500 nodes succeeds."""
    # defs (1) + target (1) = 2
    # root (1) + defs (2) = 3
    # Each <use href="#target"/> costs 1 + 1 = 2
    # Need 497 more nodes: 248 uses = 496, plus 1 rect = 497 -> total 500
    uses = "".join('<use href="#t"/>' for _ in range(248))
    xml_data = f'<svg>  <defs><rect id="t"/></defs>  {uses}  <rect/></svg>'
    root = fromstring(xml_data)
    result = validate_svg_use_dag(root, max_expanded_nodes=500)
    assert result == 500


def test_use_expansion_501_nodes_raises() -> None:
    """SVG using <use> tags expanding to 501 nodes raises SVG_EXPANSION_LIMIT_EXCEEDED."""
    uses = "".join('<use href="#t"/>' for _ in range(248))
    xml_data = f'<svg>  <defs><rect id="t"/></defs>  {uses}  <rect/>  <rect/></svg>'
    root = fromstring(xml_data)
    with pytest.raises(SvgSanitizeError) as exc_info:
        validate_svg_use_dag(root, max_expanded_nodes=500)
    assert exc_info.value.code == ERR_SVG_EXPANSION_LIMIT_EXCEEDED


def test_billion_laughs_expansion_bomb_rejected() -> None:
    """Quadratic / exponential branching <use> tree raises SVG_EXPANSION_LIMIT_EXCEEDED."""
    five_l4 = "".join('<use href="#l4"/>' for _ in range(5))
    five_l3 = "".join('<use href="#l3"/>' for _ in range(5))
    five_l2 = "".join('<use href="#l2"/>' for _ in range(5))
    xml_data = (
        "<svg>"
        "  <defs>"
        '    <g id="l4"><rect/><rect/></g>'
        f'    <g id="l3">{five_l4}</g>'
        f'    <g id="l2">{five_l3}</g>'
        f'    <g id="l1">{five_l2}</g>'
        "  </defs>"
        '  <use href="#l1"/>'
        "</svg>"
    )
    root = fromstring(xml_data)
    with pytest.raises(SvgSanitizeError) as exc_info:
        validate_svg_use_dag(root)
    assert exc_info.value.code == ERR_SVG_EXPANSION_LIMIT_EXCEEDED


def test_cycle_direct_self_reference() -> None:
    """Direct self-reference <g id="a"><use href="#a"/></g> raises SVG_USE_CYCLE."""
    xml_data = '<svg><g id="a"><use href="#a"/></g></svg>'
    root = fromstring(xml_data)
    with pytest.raises(SvgSanitizeError) as exc_info:
        validate_svg_use_dag(root)
    assert exc_info.value.code == ERR_SVG_USE_CYCLE


def test_cycle_mutual_two_nodes() -> None:
    """Mutual cycle a -> b -> a raises SVG_USE_CYCLE."""
    xml_data = '<svg>  <g id="a"><use href="#b"/></g>  <g id="b"><use href="#a"/></g></svg>'
    root = fromstring(xml_data)
    with pytest.raises(SvgSanitizeError) as exc_info:
        validate_svg_use_dag(root)
    assert exc_info.value.code == ERR_SVG_USE_CYCLE


def test_cycle_ancestor_containment() -> None:
    """Target that is an ancestor of the <use> tag raises SVG_USE_CYCLE."""
    xml_data = '<svg>  <g id="ancestor">    <g>      <use href="#ancestor"/>    </g>  </g></svg>'
    root = fromstring(xml_data)
    with pytest.raises(SvgSanitizeError) as exc_info:
        validate_svg_use_dag(root)
    assert exc_info.value.code == ERR_SVG_USE_CYCLE


def test_cycle_direct_use_self_loop() -> None:
    """<use id="x" href="#x"/> self-loop raises SVG_USE_CYCLE."""
    xml_data = '<svg><use id="x" href="#x"/></svg>'
    root = fromstring(xml_data)
    with pytest.raises(SvgSanitizeError) as exc_info:
        validate_svg_use_dag(root)
    assert exc_info.value.code == ERR_SVG_USE_CYCLE


def test_cycle_gradient_href_loop() -> None:
    """Cycle between linearGradient elements raises SVG_USE_CYCLE."""
    xml_data = (
        "<svg>"
        "  <defs>"
        '    <linearGradient id="g1" href="#g2"/>'
        '    <linearGradient id="g2" href="#g1"/>'
        "  </defs>"
        "</svg>"
    )
    root = fromstring(xml_data)
    with pytest.raises(SvgSanitizeError) as exc_info:
        validate_svg_use_dag(root)
    assert exc_info.value.code == ERR_SVG_USE_CYCLE


def test_cycle_clip_path_url_loop() -> None:
    """Cycle formed by url(#id) in clip-path attribute raises SVG_USE_CYCLE."""
    xml_data = (
        "<svg>"
        "  <defs>"
        '    <clipPath id="c1">'
        '      <rect clip-path="url(#c1)"/>'
        "    </clipPath>"
        "  </defs>"
        "</svg>"
    )
    root = fromstring(xml_data)
    with pytest.raises(SvgSanitizeError) as exc_info:
        validate_svg_use_dag(root)
    assert exc_info.value.code == ERR_SVG_USE_CYCLE


def test_missing_target_treated_safely() -> None:
    """Use element pointing to non-existent id does not crash or loop."""
    xml_data = '<svg><use href="#nonexistent"/></svg>'
    root = fromstring(xml_data)
    result = validate_svg_use_dag(root)
    # root(1) + use(1, target None) = 2
    assert result == 2
    assert result.max_use_depth == 1
