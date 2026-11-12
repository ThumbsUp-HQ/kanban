"""Local acyclic DAG and complexity validator for SVG <use> and gradient references.

Enforces:
1. Cycle-free references across containment and href/url() links (SVG_USE_CYCLE).
2. Maximum <use> reference chain depth <= 4 (SVG_USE_DEPTH_EXCEEDED).
3. Maximum rendered DOM node expansion <= 500 (SVG_EXPANSION_LIMIT_EXCEEDED).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

# Maximum allowable <use> chain depth per Section 5.4
MAX_SVG_USE_DEPTH: int = 4

# Maximum allowable rendered DOM nodes after <use> expansion per Section 5.4
MAX_SVG_EXPANDED_NODES: int = 500

# Error code constants
ERR_SVG_USE_CYCLE: str = "SVG_USE_CYCLE"
ERR_SVG_USE_DEPTH_EXCEEDED: str = "SVG_USE_DEPTH_EXCEEDED"
ERR_SVG_EXPANSION_LIMIT_EXCEEDED: str = "SVG_EXPANSION_LIMIT_EXCEEDED"

# DFS cycle detection node states
_STATE_UNVISITED: int = 0
_STATE_IN_STACK: int = 1
_STATE_DONE: int = 2

# Pattern for valid local url(#id) reference
_URL_TARGET_RE: re.Pattern[str] = re.compile(r"^url\(#([A-Za-z_][A-Za-z0-9_.-]{0,127})\)$")

# Reference attributes that may point to other elements via url(#id)
_REF_ATTRS: tuple[str, ...] = (
    "fill",
    "stroke",
    "clip-path",
    "marker-start",
    "marker-mid",
    "marker-end",
)


class SvgSanitizeError(Exception):
    """Raised when SVG sanitization or safety checks fail."""

    def __init__(self, code: str, message: str | None = None) -> None:
        """Initialize with machine-readable error code and optional message."""
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class SvgDagResult(int):
    """Result of SVG DAG validation, carrying expansion count and max use depth."""

    expanded_nodes: int
    max_use_depth: int

    def __new__(cls, expanded_nodes: int, max_use_depth: int) -> Self:
        """Create new SvgDagResult behaving as integer total node expansion."""
        obj = super().__new__(cls, expanded_nodes)
        obj.expanded_nodes = expanded_nodes
        obj.max_use_depth = max_use_depth
        return obj


def _get_local_tag(tag: str) -> str:
    """Return local XML tag name without namespace."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _get_use_target(elem: ET.Element, id_map: dict[str, ET.Element]) -> ET.Element | None:
    """Return target element referenced by href or xlink:href if present in id_map."""
    href = elem.attrib.get("href") or elem.attrib.get("{http://www.w3.org/1999/xlink}href")
    if href and href.startswith("#"):
        return id_map.get(href[1:])
    return None


def _get_element_references(elem: ET.Element, id_map: dict[str, ET.Element]) -> list[ET.Element]:
    """Return all target elements referenced by elem via href or url(#id)."""
    refs: list[ET.Element] = []
    target = _get_use_target(elem, id_map)
    if target is not None:
        refs.append(target)

    for attr in _REF_ATTRS:
        val = elem.attrib.get(attr)
        if val:
            match = _URL_TARGET_RE.match(val.strip())
            if match:
                ref_target = id_map.get(match.group(1))
                if ref_target is not None:
                    refs.append(ref_target)
    return refs


def _detect_cycles(root: ET.Element, id_map: dict[str, ET.Element]) -> None:
    """Detect cycles across containment and reference edges via DFS."""
    state: dict[int, int] = {}

    def check_cycles(elem: ET.Element) -> None:
        elem_id = id(elem)
        st = state.get(elem_id, _STATE_UNVISITED)
        if st == _STATE_IN_STACK:
            raise SvgSanitizeError(ERR_SVG_USE_CYCLE)
        if st == _STATE_DONE:
            return

        state[elem_id] = _STATE_IN_STACK

        for child in elem:
            check_cycles(child)

        for ref_target in _get_element_references(elem, id_map):
            check_cycles(ref_target)

        state[elem_id] = _STATE_DONE

    for elem in root.iter():
        if state.get(id(elem), _STATE_UNVISITED) == _STATE_UNVISITED:
            check_cycles(elem)


def _compute_use_depth(
    root: ET.Element,
    id_map: dict[str, ET.Element],
    max_depth: int,
) -> int:
    """Compute maximum <use> reference chain depth across the document."""
    depth_memo: dict[int, int] = {}

    def get_use_depth(elem: ET.Element) -> int:
        elem_id = id(elem)
        if elem_id in depth_memo:
            return depth_memo[elem_id]

        local_tag = _get_local_tag(elem.tag)
        child_max = max((get_use_depth(child) for child in elem), default=0)

        if local_tag == "use":
            target = _get_use_target(elem, id_map)
            target_depth = get_use_depth(target) if target is not None else 0
            total_d = max(1 + target_depth, child_max)
        else:
            total_d = child_max

        depth_memo[elem_id] = total_d
        return total_d

    max_doc_depth = max((get_use_depth(e) for e in root.iter()), default=0)
    if max_doc_depth > max_depth:
        raise SvgSanitizeError(ERR_SVG_USE_DEPTH_EXCEEDED)
    return max_doc_depth


def _compute_expansion_cost(
    root: ET.Element,
    id_map: dict[str, ET.Element],
    max_expanded_nodes: int,
) -> int:
    """Compute rendered node expansion cost via bottom-up memoized count."""
    cost_memo: dict[int, int] = {}

    def get_node_cost(elem: ET.Element) -> int:
        elem_id = id(elem)
        if elem_id in cost_memo:
            return cost_memo[elem_id]

        cost = 1
        for child in elem:
            cost += get_node_cost(child)
            if cost > max_expanded_nodes:
                raise SvgSanitizeError(ERR_SVG_EXPANSION_LIMIT_EXCEEDED)

        local_tag = _get_local_tag(elem.tag)
        if local_tag == "use":
            target = _get_use_target(elem, id_map)
            if target is not None:
                cost += get_node_cost(target)
                if cost > max_expanded_nodes:
                    raise SvgSanitizeError(ERR_SVG_EXPANSION_LIMIT_EXCEEDED)

        cost_memo[elem_id] = cost
        return cost

    total_expanded_nodes = get_node_cost(root)
    if total_expanded_nodes > max_expanded_nodes:
        raise SvgSanitizeError(ERR_SVG_EXPANSION_LIMIT_EXCEEDED)
    return total_expanded_nodes


def validate_svg_use_dag(
    root: ET.Element,
    id_map: dict[str, ET.Element] | None = None,
    max_depth: int = MAX_SVG_USE_DEPTH,
    max_expanded_nodes: int = MAX_SVG_EXPANDED_NODES,
) -> SvgDagResult:
    """Validate that SVG use and gradient references form an acyclic DAG within limits.

    Args:
        root: Root XML element of the sanitized SVG.
        id_map: Mapping of element id to Element instance. If None, built from root.
        max_depth: Maximum permitted <use> reference chain depth (default 4).
        max_expanded_nodes: Maximum permitted rendered nodes after expansion (default 500).

    Returns:
        SvgDagResult carrying expanded_nodes count and max_use_depth.

    Raises:
        SvgSanitizeError: If a cycle, excessive depth, or excessive expansion is detected.

    """
    if id_map is None:
        id_map = {}
        for elem in root.iter():
            elem_id = elem.attrib.get("id")
            if elem_id:
                id_map[elem_id] = elem

    # 1. Detect cycles via DFS
    _detect_cycles(root, id_map)

    # 2. Compute maximum <use> chain depth
    max_doc_depth = _compute_use_depth(root, id_map, max_depth)

    # 3. Compute rendered node expansion cost
    total_expanded_nodes = _compute_expansion_cost(root, id_map, max_expanded_nodes)

    return SvgDagResult(
        expanded_nodes=total_expanded_nodes,
        max_use_depth=max_doc_depth,
    )
