"""Server-side SVG sanitizer enforcing geometry allowlists and safe presentation attributes.

Hardens uploaded .svg diagrams and media against:
- XXE and entity expansion bombs via pre-parse byte scanners and defusedxml.
- XSS and active scripts by stripping <script>, <foreignObject>, <style>, and on* handlers.
- SSRF and external leaks by stripping <image> and external href / url() references.
- Billion-laughs and recursive reference bombs via local acyclic DAG validation (svg_dag.py).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import defusedxml.common
import defusedxml.ElementTree

from kanban.content.svg_dag import (
    MAX_SVG_EXPANDED_NODES,
    MAX_SVG_USE_DEPTH,
    SvgDagResult,
    SvgSanitizeError,
    validate_svg_use_dag,
)
from kanban.content.unicode_guard import (
    SURROGATE_MAX,
    SURROGATE_MIN,
    ContentNormalizeError,
    strip_invisible_and_control_chars,
)

# Maximum input payload size per Section 5.4 (2 MiB default)
DEFAULT_MAX_SVG_BYTES: int = 2_097_152

# Maximum allowable XML tree nesting depth
MAX_XML_DEPTH: int = 64

# Maximum allowable raw XML elements
MAX_RAW_ELEMENTS: int = 5000

# Maximum viewport coordinate dimension to prevent canvas exhaustion
MAX_COORDINATE_DIMENSION: float = 32768.0

# Error code constants
ERR_SVG_SIZE_INVALID: str = "SVG_SIZE_INVALID"
ERR_SVG_INVALID_UTF8: str = "SVG_INVALID_UTF8"
ERR_SVG_DTD_OR_ENTITY_FORBIDDEN: str = "SVG_DTD_OR_ENTITY_FORBIDDEN"
ERR_SVG_MALFORMED_XML: str = "SVG_MALFORMED_XML"
ERR_SVG_ROOT_INVALID: str = "SVG_ROOT_INVALID"
ERR_SVG_COMPLEXITY_EXCEEDED: str = "SVG_COMPLEXITY_EXCEEDED"
ERR_SVG_DUPLICATE_ID: str = "SVG_DUPLICATE_ID"
ERR_SVG_DIMENSIONS_INVALID: str = "SVG_DIMENSIONS_INVALID"

# Allowed vector geometry and structural elements per Section 5.4 line 398
ALLOWED_SVG_ELEMENTS: frozenset[str] = frozenset(
    {
        "svg",
        "g",
        "path",
        "rect",
        "circle",
        "ellipse",
        "line",
        "polyline",
        "polygon",
        "text",
        "tspan",
        "defs",
        "symbol",
        "use",
        "linearGradient",
        "radialGradient",
        "stop",
        "clipPath",
        "marker",
        "title",
        "desc",
    }
)

# Allowed safe geometry and presentation attributes per Section 5.4
ALLOWED_SVG_ATTRS: frozenset[str] = frozenset(
    {
        "id",
        "viewBox",
        "preserveAspectRatio",
        "width",
        "height",
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "d",
        "points",
        "transform",
        "gradientUnits",
        "gradientTransform",
        "spreadMethod",
        "offset",
        "stop-color",
        "stop-opacity",
        "clipPathUnits",
        "markerUnits",
        "markerWidth",
        "markerHeight",
        "refX",
        "refY",
        "orient",
        "fill",
        "fill-opacity",
        "fill-rule",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "stroke-dasharray",
        "stroke-dashoffset",
        "stroke-opacity",
        "opacity",
        "color",
        "font-family",
        "font-size",
        "font-weight",
        "font-style",
        "text-anchor",
        "dominant-baseline",
        "dx",
        "dy",
        "clip-path",
        "marker-start",
        "marker-mid",
        "marker-end",
        "href",
    }
)

# Pre-parse scanner pattern rejecting DTD, entity declarations, CDATA, and stylesheets
_FORBIDDEN_PREPARSE_PATTERN: re.Pattern[str] = re.compile(
    r"<!\s*(?:doctype|entity|\[\s*cdata\s*\[)|\<\?\s*xml-stylesheet",
    re.IGNORECASE,
)

# Valid XML ID pattern per Section 5.4
_ID_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")

# Valid local href pattern pointing to local #id
_HREF_PATTERN: re.Pattern[str] = re.compile(r"^#[A-Za-z_][A-Za-z0-9_.-]{0,127}$")

# Valid local paint/clip/marker url(#id) pattern
_URL_REF_PATTERN: re.Pattern[str] = re.compile(r"^url\(#([A-Za-z_][A-Za-z0-9_.-]{0,127})\)$")

# Dimension numeric parser supporting optional units (px, %, em, etc.)
_DIM_PATTERN: re.Pattern[str] = re.compile(
    r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))(?:px|%|em|rem|pt|pc|in|cm|mm)?$",
    re.IGNORECASE,
)

# Elements permitted to hold local href targets
_HREF_PERMITTED_ELEMENTS: frozenset[str] = frozenset({"use", "linearGradient", "radialGradient"})

# Paint and reference attributes that can hold url(#id) values
_PAINT_REF_ATTRS: frozenset[str] = frozenset(
    {"fill", "stroke", "clip-path", "marker-start", "marker-mid", "marker-end"}
)

# Dangerous tokens forbidden inside presentation attributes
_FORBIDDEN_CSS_TOKENS: tuple[str, ...] = (
    "expression(",
    "javascript:",
    "@import",
    "image-set(",
)


@dataclass(frozen=True)
class SvgSanitizeReport:
    """Detailed audit metrics and canonical output of SVG sanitization."""

    input_bytes: int
    output_bytes: int
    stripped_elements: int
    stripped_attrs: int
    expanded_nodes: int
    max_use_depth: int
    output_svg: str


def _get_local_name(tag: str) -> str:
    """Return local XML tag name without namespace."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _get_tag_namespace_and_local(tag: str) -> tuple[str, str]:
    """Return tuple of (namespace, local_tag)."""
    if tag.startswith("{"):
        ns, local = tag[1:].split("}", 1)
        return ns, local
    return "", tag


def _get_xml_depth(elem: ET.Element, current_depth: int = 1) -> int:
    """Return maximum XML nesting depth of the element subtree."""
    return max(
        (_get_xml_depth(child, current_depth + 1) for child in elem),
        default=current_depth,
    )


def _parse_dimension_value(val: str) -> float | None:
    """Parse numeric portion of a dimension string."""
    match = _DIM_PATTERN.match(val)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _validate_dimension_coordinates(elem: ET.Element) -> None:
    """Validate viewBox, width, and height attributes to reject canvas bombs."""
    if "viewBox" in elem.attrib:
        raw_vb = elem.attrib["viewBox"].strip()
        parts = [p for p in re.split(r"[\s,]+", raw_vb) if p]
        coord_count = 4
        if len(parts) != coord_count:
            raise SvgSanitizeError(ERR_SVG_DIMENSIONS_INVALID)
        try:
            coords = [float(p) for p in parts]
        except ValueError as exc:
            raise SvgSanitizeError(ERR_SVG_DIMENSIONS_INVALID) from exc

        if any(abs(c) > MAX_COORDINATE_DIMENSION for c in coords):
            raise SvgSanitizeError(ERR_SVG_DIMENSIONS_INVALID)
        width_idx = 2
        height_idx = 3
        if coords[width_idx] < 0 or coords[height_idx] < 0:
            raise SvgSanitizeError(ERR_SVG_DIMENSIONS_INVALID)

    for dim in ("width", "height"):
        if dim in elem.attrib:
            val = elem.attrib[dim].strip()
            num = _parse_dimension_value(val)
            if num is None or num < 0 or num > MAX_COORDINATE_DIMENSION:
                raise SvgSanitizeError(ERR_SVG_DIMENSIONS_INVALID)


def _decode_and_guard_input(svg_input: str | bytes, max_bytes: int) -> tuple[bytes, str]:
    """Validate encoding, size, and unicode characteristics of raw SVG input."""
    if isinstance(svg_input, str):
        for char in svg_input:
            cp = ord(char)
            if SURROGATE_MIN <= cp <= SURROGATE_MAX:
                raise SvgSanitizeError(ERR_SVG_INVALID_UTF8)
        raw_bytes = svg_input.encode("utf-8")
    else:
        raw_bytes = svg_input

    if len(raw_bytes) < 1 or len(raw_bytes) > max_bytes:
        raise SvgSanitizeError(ERR_SVG_SIZE_INVALID)

    # Reject non-UTF-8 BOM signatures
    if raw_bytes.startswith(
        (
            b"\xff\xfe\x00\x00",
            b"\x00\x00\xfe\xff",
            b"\xff\xfe",
            b"\xfe\xff",
            b"\x2b\x2f\x76",
        )
    ):
        raise SvgSanitizeError(ERR_SVG_INVALID_UTF8)

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SvgSanitizeError(ERR_SVG_INVALID_UTF8) from exc

    text = text.removeprefix("\ufeff")

    try:
        text, _, _ = strip_invisible_and_control_chars(text, max_input_bytes=max_bytes)
    except ContentNormalizeError as exc:
        if exc.code == "CONTENT_TOO_LARGE":
            raise SvgSanitizeError(ERR_SVG_SIZE_INVALID) from exc
        raise SvgSanitizeError(ERR_SVG_INVALID_UTF8) from exc

    return raw_bytes, text


def _parse_and_validate_xml_root(text: str) -> ET.Element:
    """Perform pre-parse scan and safe XML parsing with defusedxml."""
    if _FORBIDDEN_PREPARSE_PATTERN.search(text):
        raise SvgSanitizeError(ERR_SVG_DTD_OR_ENTITY_FORBIDDEN)

    try:
        root = defusedxml.ElementTree.fromstring(
            text,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except defusedxml.common.DefusedXmlException as exc:
        raise SvgSanitizeError(ERR_SVG_DTD_OR_ENTITY_FORBIDDEN) from exc
    except (ET.ParseError, ValueError) as exc:
        raise SvgSanitizeError(ERR_SVG_MALFORMED_XML) from exc

    root_ns, root_local = _get_tag_namespace_and_local(root.tag)
    if root_local != "svg":
        raise SvgSanitizeError(ERR_SVG_ROOT_INVALID)
    if root_ns and root_ns != "http://www.w3.org/2000/svg":
        raise SvgSanitizeError(ERR_SVG_ROOT_INVALID)

    raw_element_count = sum(1 for _ in root.iter())
    if raw_element_count > MAX_RAW_ELEMENTS:
        raise SvgSanitizeError(ERR_SVG_COMPLEXITY_EXCEEDED)
    if _get_xml_depth(root) > MAX_XML_DEPTH:
        raise SvgSanitizeError(ERR_SVG_COMPLEXITY_EXCEEDED)

    return root


def _prune_disallowed_subtrees(parent: ET.Element) -> int:
    """Recursively remove subtrees of non-allowed elements, preserving tail text."""
    stripped_count = 0
    for child in list(parent):
        _, local_tag = _get_tag_namespace_and_local(child.tag)
        if local_tag not in ALLOWED_SVG_ELEMENTS:
            idx = list(parent).index(child)
            if child.tail:
                if idx > 0:
                    prev = parent[idx - 1]
                    prev.tail = (prev.tail or "") + child.tail
                else:
                    parent.text = (parent.text or "") + child.tail
            parent.remove(child)
            stripped_count += 1
        else:
            stripped_count += _prune_disallowed_subtrees(child)
    return stripped_count


def _collect_and_validate_ids(
    root: ET.Element,
) -> tuple[dict[str, ET.Element], int]:
    """Collect valid IDs and assert uniqueness across the document."""
    seen_ids: set[str] = set()
    id_map: dict[str, ET.Element] = {}
    stripped_attrs = 0

    for elem in root.iter():
        elem_id = elem.attrib.get("id")
        if elem_id is not None:
            if not _ID_PATTERN.match(elem_id):
                del elem.attrib["id"]
                stripped_attrs += 1
            elif elem_id in seen_ids:
                raise SvgSanitizeError(ERR_SVG_DUPLICATE_ID)
            else:
                seen_ids.add(elem_id)
                id_map[elem_id] = elem

    return id_map, stripped_attrs


def _sanitize_href_attr(elem: ET.Element, id_map: dict[str, ET.Element]) -> int:
    """Validate and filter href attribute on an element."""
    if "href" not in elem.attrib:
        return 0

    local_tag = _get_local_name(elem.tag)
    if local_tag not in _HREF_PERMITTED_ELEMENTS:
        del elem.attrib["href"]
        return 1

    href_val = elem.attrib["href"]
    if not _HREF_PATTERN.match(href_val):
        del elem.attrib["href"]
        return 1

    target_id = href_val[1:]
    if target_id not in id_map:
        del elem.attrib["href"]
        return 1

    return 0


def _sanitize_paint_attrs(elem: ET.Element, id_map: dict[str, ET.Element]) -> int:
    """Validate paint and reference attributes on an element."""
    stripped = 0
    for paint_attr in _PAINT_REF_ATTRS:
        if paint_attr in elem.attrib:
            val = elem.attrib[paint_attr].strip()
            lower_val = val.lower()
            if any(tok in lower_val for tok in _FORBIDDEN_CSS_TOKENS):
                del elem.attrib[paint_attr]
                stripped += 1
                continue
            if "url(" in lower_val:
                match = _URL_REF_PATTERN.match(val)
                if match:
                    ref_target_id = match.group(1)
                    if ref_target_id not in id_map:
                        del elem.attrib[paint_attr]
                        stripped += 1
                else:
                    del elem.attrib[paint_attr]
                    stripped += 1
    return stripped


def _sanitize_element_attributes(root: ET.Element, id_map: dict[str, ET.Element]) -> int:
    """Sanitize all attributes across allowed elements in the document."""
    stripped_attrs = 0

    for elem in root.iter():
        xlink_key = "{http://www.w3.org/1999/xlink}href"
        if xlink_key in elem.attrib:
            xlink_val = elem.attrib.pop(xlink_key)
            if "href" not in elem.attrib:
                elem.attrib["href"] = xlink_val

        for attr in list(elem.attrib.keys()):
            if attr.startswith("{"):
                del elem.attrib[attr]
                stripped_attrs += 1
                continue
            lower_attr = attr.lower()
            if lower_attr in ("xmlns:xlink", "xml:base", "style") or lower_attr.startswith("on"):
                del elem.attrib[attr]
                stripped_attrs += 1
                continue
            if attr not in ALLOWED_SVG_ATTRS:
                del elem.attrib[attr]
                stripped_attrs += 1
                continue

        stripped_attrs += _sanitize_href_attr(elem, id_map)
        stripped_attrs += _sanitize_paint_attrs(elem, id_map)
        _validate_dimension_coordinates(elem)

    return stripped_attrs


def _serialize_clean_svg(root: ET.Element) -> str:
    """Canonical XML serialization with deterministic attribute order."""
    for elem in root.iter():
        elem.tag = _get_local_name(elem.tag)
        if elem is root:
            clean_attrib: dict[str, str] = {"xmlns": "http://www.w3.org/2000/svg"}
            for k in sorted(elem.attrib.keys()):
                if k != "xmlns":
                    clean_attrib[k] = elem.attrib[k]
            elem.attrib = clean_attrib
        else:
            elem.attrib = {k: elem.attrib[k] for k in sorted(elem.attrib.keys())}

    return ET.tostring(root, encoding="unicode")


def sanitize_svg_with_report(
    svg_input: str | bytes,
    max_bytes: int = DEFAULT_MAX_SVG_BYTES,
) -> SvgSanitizeReport:
    """Sanitize raw SVG input and produce a comprehensive audit report.

    Args:
        svg_input: Raw SVG content as str or bytes.
        max_bytes: Maximum allowed byte length (default 2 MiB).

    Returns:
        SvgSanitizeReport containing metrics and sanitized SVG XML string.

    Raises:
        SvgSanitizeError: If the SVG violates security boundaries or limits.

    """
    raw_bytes, text = _decode_and_guard_input(svg_input, max_bytes)
    root = _parse_and_validate_xml_root(text)

    stripped_elements = _prune_disallowed_subtrees(root)
    id_map, stripped_id_attrs = _collect_and_validate_ids(root)
    stripped_other_attrs = _sanitize_element_attributes(root, id_map)
    total_stripped_attrs = stripped_id_attrs + stripped_other_attrs

    dag_result: SvgDagResult = validate_svg_use_dag(
        root=root,
        id_map=id_map,
        max_depth=MAX_SVG_USE_DEPTH,
        max_expanded_nodes=MAX_SVG_EXPANDED_NODES,
    )

    output_svg = _serialize_clean_svg(root)
    output_bytes = len(output_svg.encode("utf-8"))

    return SvgSanitizeReport(
        input_bytes=len(raw_bytes),
        output_bytes=output_bytes,
        stripped_elements=stripped_elements,
        stripped_attrs=total_stripped_attrs,
        expanded_nodes=dag_result.expanded_nodes,
        max_use_depth=dag_result.max_use_depth,
        output_svg=output_svg,
    )


def sanitize_svg(
    svg_input: str | bytes,
    max_bytes: int = DEFAULT_MAX_SVG_BYTES,
) -> str:
    """Sanitize raw SVG input and return safe canonical SVG string.

    Args:
        svg_input: Raw SVG content as str or bytes.
        max_bytes: Maximum allowed byte length (default 2 MiB).

    Returns:
        Sanitized SVG XML string.

    Raises:
        SvgSanitizeError: If SVG violates safety policies or bounds.

    """
    report = sanitize_svg_with_report(svg_input, max_bytes=max_bytes)
    return report.output_svg
