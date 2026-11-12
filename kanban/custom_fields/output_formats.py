# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pydantic v2 schemas and validation for 7-format output_format_metadata (KB-P5-11, S13.1)."""

from __future__ import annotations

import math
import re
import unicodedata
import urllib.parse
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from kanban.content.normalize import normalize_to_markdown

MAX_BADGE_LABEL_LEN = 64
MAX_SEVERITY_SCORE = 10.0
MAX_SEVERITY_LABEL_LEN = 32

OUTPUT_FORMAT_TYPES = (
    "text",
    "number",
    "badge",
    "markdown_snippet",
    "url",
    "json_table",
    "severity_pill",
)

OutputFormatType = Literal[
    "text",
    "number",
    "badge",
    "markdown_snippet",
    "url",
    "json_table",
    "severity_pill",
]

_COLUMN_KEY_REGEX = re.compile(r"^[a-z0-9_]{1,32}$")
_BADGE_DISALLOWED_CSS = re.compile(r"[;{}#]|url\(|<[^>]*>", re.IGNORECASE)


class TableColumn(BaseModel):
    """Specification for a single column in json_table format."""

    model_config = ConfigDict(extra="forbid", strict=True)

    key: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_]{1,32}$")
    label: str = Field(min_length=1, max_length=64)


class TextFormatMetadata(BaseModel):
    """Configuration for text custom field output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    format: Literal["text"] = "text"
    max_length: int = Field(default=280, ge=1, le=280)
    prefix: str | None = Field(default=None, max_length=16)
    monospace: bool = False


class NumberFormatMetadata(BaseModel):
    """Configuration for numeric custom field output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    format: Literal["number"] = "number"
    maximum_fraction_digits: int = Field(default=2, ge=0, le=6)
    unit_suffix: str | None = Field(default=None, max_length=12)
    min_value: float | None = None
    max_value: float | None = None

    @field_validator("min_value", "max_value")
    @classmethod
    def check_finite(cls, v: float | None) -> float | None:
        """Reject non-finite float bounds."""
        if v is not None and not math.isfinite(v):
            msg = "Bound values must be finite numbers"
            raise ValueError(msg)
        return v


class BadgeFormatMetadata(BaseModel):
    """Configuration for colored badge custom field output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    format: Literal["badge"] = "badge"
    color_token: Literal["neutral", "info", "success", "warning", "danger", "accent"]
    allowed_labels: list[str] | None = Field(default=None, max_length=32)

    @field_validator("allowed_labels")
    @classmethod
    def check_allowed_labels(cls, labels: list[str] | None) -> list[str] | None:
        """Ensure allowed labels do not contain arbitrary CSS or script tags."""
        if labels is not None:
            for lbl in labels:
                if len(lbl) < 1 or len(lbl) > MAX_BADGE_LABEL_LEN:
                    msg = "Badge label length must be between 1 and 64 characters"
                    raise ValueError(msg)
                if _BADGE_DISALLOWED_CSS.search(lbl):
                    msg = f"Badge label '{lbl}' contains forbidden CSS or markup characters"
                    raise ValueError(msg)
        return labels


class MarkdownSnippetFormatMetadata(BaseModel):
    """Configuration for sanitized markdown snippet output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    format: Literal["markdown_snippet"] = "markdown_snippet"
    max_chars: int = Field(default=2000, ge=1, le=2000)


class UrlFormatMetadata(BaseModel):
    """Configuration for URL custom field output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    format: Literal["url"] = "url"
    allowed_schemes: list[Literal["https", "http"]] = Field(default=["https"])
    allowed_host_suffixes: list[str] | None = None


class JsonTableFormatMetadata(BaseModel):
    """Configuration for tabular JSON custom field output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    format: Literal["json_table"] = "json_table"
    columns: list[TableColumn] = Field(min_length=1, max_length=10)
    max_rows: int = Field(default=50, ge=1, le=50)


class SeverityPillFormatMetadata(BaseModel):
    """Configuration for vulnerability/incident severity pill output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    format: Literal["severity_pill"] = "severity_pill"


OutputFormatMetadata = Annotated[
    TextFormatMetadata
    | NumberFormatMetadata
    | BadgeFormatMetadata
    | MarkdownSnippetFormatMetadata
    | UrlFormatMetadata
    | JsonTableFormatMetadata
    | SeverityPillFormatMetadata,
    Field(discriminator="format"),
]

_METADATA_ADAPTER = TypeAdapter(OutputFormatMetadata)


def parse_output_format_metadata(
    output_format: str, raw_metadata: dict[str, Any]
) -> OutputFormatMetadata:
    """Parse and validate output format metadata against strict discriminated union."""
    if output_format not in OUTPUT_FORMAT_TYPES:
        msg = f"Invalid output_format '{output_format}'; must be one of {OUTPUT_FORMAT_TYPES}"
        raise ValueError(msg)

    # In case raw_metadata doesn't have format field, inject it for discriminator
    meta_dict = dict(raw_metadata)
    meta_dict["format"] = output_format
    return _METADATA_ADAPTER.validate_python(meta_dict)


def _strip_control_chars(text: str) -> str:
    """Strip C0 and C1 control characters except newline and tab."""
    return "".join(c for c in text if unicodedata.category(c)[0] != "C" or c in ("\t", "\n", "\r"))


def _validate_text(metadata: OutputFormatMetadata, value: object) -> str:
    if not isinstance(value, str):
        msg = f"Expected str for 'text' output format, got {type(value).__name__}"
        raise TypeError(msg)
    meta = cast("TextFormatMetadata", metadata)
    cleaned = _strip_control_chars(value)
    if len(cleaned) > meta.max_length:
        msg = f"Text length ({len(cleaned)}) exceeds configured max_length ({meta.max_length})"
        raise ValueError(msg)
    return cleaned


def _validate_number(metadata: OutputFormatMetadata, value: object) -> int | float:
    # Reject bool explicitly because isinstance(True, int) is True in Python
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        msg = f"Expected numeric value for 'number' output format, got {type(value).__name__}"
        raise TypeError(msg)
    if not math.isfinite(value):
        msg = f"Numeric value must be finite; rejected {value}"
        raise ValueError(msg)
    meta = cast("NumberFormatMetadata", metadata)
    if meta.min_value is not None and value < meta.min_value:
        msg = f"Value {value} is less than minimum allowed value {meta.min_value}"
        raise ValueError(msg)
    if meta.max_value is not None and value > meta.max_value:
        msg = f"Value {value} is greater than maximum allowed value {meta.max_value}"
        raise ValueError(msg)
    return round(value, meta.maximum_fraction_digits)


def _validate_badge(metadata: OutputFormatMetadata, value: object) -> str:
    if not isinstance(value, str):
        msg = f"Expected str for 'badge' output format, got {type(value).__name__}"
        raise TypeError(msg)
    lbl = value.strip()
    if len(lbl) < 1 or len(lbl) > MAX_BADGE_LABEL_LEN:
        msg = "Badge label length must be between 1 and 64 characters"
        raise ValueError(msg)
    if _BADGE_DISALLOWED_CSS.search(lbl):
        msg = f"Badge label '{lbl}' contains disallowed CSS or markup injection"
        raise ValueError(msg)
    meta = cast("BadgeFormatMetadata", metadata)
    if meta.allowed_labels is not None and lbl not in meta.allowed_labels:
        msg = f"Badge label '{lbl}' is not in allowed_labels: {meta.allowed_labels}"
        raise ValueError(msg)
    return lbl


def _validate_markdown_snippet(metadata: OutputFormatMetadata, value: object) -> str:
    if not isinstance(value, str):
        msg = f"Expected str for 'markdown_snippet' output format, got {type(value).__name__}"
        raise TypeError(msg)
    meta = cast("MarkdownSnippetFormatMetadata", metadata)
    norm = normalize_to_markdown(value)
    norm = re.sub(r"!\[.*?\]\(.*?\)", "", norm)
    norm = re.sub(r"<[^>]*>", "", norm).strip()
    if len(norm) > meta.max_chars:
        msg = f"Markdown snippet length ({len(norm)}) exceeds max_chars ({meta.max_chars})"
        raise ValueError(msg)
    return norm


def _validate_url(metadata: OutputFormatMetadata, value: object) -> str:
    if not isinstance(value, str):
        msg = f"Expected str for 'url' output format, got {type(value).__name__}"
        raise TypeError(msg)
    raw_url = value.strip()
    parsed = urllib.parse.urlsplit(raw_url)
    meta = cast("UrlFormatMetadata", metadata)
    if not parsed.scheme or parsed.scheme.lower() not in meta.allowed_schemes:
        msg = f"URL scheme '{parsed.scheme}' not allowed; allowed schemes: {meta.allowed_schemes}"
        raise ValueError(msg)
    if parsed.username or parsed.password:
        msg = "URL with embedded credentials is strictly prohibited"
        raise ValueError(msg)
    if not parsed.hostname:
        msg = "URL must include a valid hostname"
        raise ValueError(msg)
    if meta.allowed_host_suffixes:
        h = parsed.hostname.lower()
        matched = any(
            h == s.lower() or h.endswith("." + s.lower().lstrip("."))
            for s in meta.allowed_host_suffixes
        )
        if not matched:
            msg = (
                f"Hostname '{parsed.hostname}' does not match "
                f"allowed host suffixes: {meta.allowed_host_suffixes}"
            )
            raise ValueError(msg)
    return raw_url


def _clean_table_cell(k: str, v: object, idx: int) -> object:
    if isinstance(v, (dict, list)):
        msg = f"Row {idx} key '{k}' contains nested structure; only scalars permitted"
        raise TypeError(msg)
    if isinstance(v, float) and not math.isfinite(v):
        msg = f"Row {idx} key '{k}' contains non-finite float {v}"
        raise ValueError(msg)
    cell_val = v
    if isinstance(cell_val, str):
        if "<script" in cell_val.lower():
            msg = f"Row {idx} key '{k}' contains forbidden script tag"
            raise ValueError(msg)
        cell_val = _strip_control_chars(cell_val)
    return cell_val


def _validate_json_table(metadata: OutputFormatMetadata, value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        msg = f"Expected list of dicts for 'json_table' output format, got {type(value).__name__}"
        raise TypeError(msg)
    meta = cast("JsonTableFormatMetadata", metadata)
    if len(value) > meta.max_rows:
        msg = f"Row count ({len(value)}) exceeds configured max_rows ({meta.max_rows})"
        raise ValueError(msg)
    valid_keys = {col.key for col in meta.columns}
    cleaned_rows: list[dict[str, object]] = []
    for idx, row in enumerate(value):
        if not isinstance(row, dict):
            msg = f"Row {idx} must be a dict, got {type(row).__name__}"
            raise TypeError(msg)
        cleaned_row: dict[str, object] = {}
        for k, v in row.items():
            if k not in valid_keys:
                continue
            cleaned_row[k] = _clean_table_cell(k, v, idx)
        cleaned_rows.append(cleaned_row)
    return cleaned_rows


def _check_severity_score(score: object) -> float:
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        msg = f"Expected numeric score, got {type(score).__name__}"
        raise TypeError(msg)
    if not math.isfinite(score) or score < 0.0 or score > MAX_SEVERITY_SCORE:
        msg = f"Severity score must be finite and between 0.0 and 10.0, got {score}"
        raise ValueError(msg)
    return float(score)


def _check_severity_label(label: object) -> str:
    if not isinstance(label, str) or len(label) > MAX_SEVERITY_LABEL_LEN:
        msg = "Severity label must be a string of at most 32 characters"
        raise ValueError(msg)
    if "<" in label or ">" in label:
        msg = "Severity label cannot contain HTML markup"
        raise ValueError(msg)
    return label


def _validate_severity_pill(_metadata: OutputFormatMetadata, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"Expected dict for 'severity_pill' output format, got {type(value).__name__}"
        raise TypeError(msg)
    level = value.get("level")
    if level not in ("low", "medium", "high", "critical"):
        msg = (
            f"Invalid severity level '{level}'; "
            "must be one of ('low', 'medium', 'high', 'critical')"
        )
        raise ValueError(msg)
    res: dict[str, object] = {"level": level}
    if "score" in value and value["score"] is not None:
        res["score"] = _check_severity_score(value["score"])
    if "label" in value and value["label"] is not None:
        res["label"] = _check_severity_label(value["label"])
    return res


_VALIDATORS: dict[str, Callable[[OutputFormatMetadata, object], object]] = {
    "text": _validate_text,
    "number": _validate_number,
    "badge": _validate_badge,
    "markdown_snippet": _validate_markdown_snippet,
    "url": _validate_url,
    "json_table": _validate_json_table,
    "severity_pill": _validate_severity_pill,
}


def validate_field_output_value(
    output_format: str,
    metadata: OutputFormatMetadata,
    value: object,
) -> object:
    """Validate a computed custom field value against its configured metadata schema."""
    validator = _VALIDATORS.get(output_format)
    if validator is None:
        msg = f"Unsupported output format: '{output_format}'"
        raise ValueError(msg)
    return validator(metadata, value)
