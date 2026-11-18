# Copyright 2026 Kanban Platform Contributors
"""InlineSafeDumper YAML serializer with flow style scalars and literal block strings."""

from __future__ import annotations

from typing import Final

import yaml

from kanban.security.scrubber import scrub_text

__all__ = [
    "InlineSafeDumper",
    "dump_yaml",
    "redact_secrets",
    "strip_empty",
]

_MAX_FLOW_DICT_LEN: Final[int] = 4

_SECRET_KEY_NAMES: Final[frozenset[str]] = frozenset(
    {
        "secret",
        "client_secret",
        "bind_dn_password",
        "encrypted_secret_blob",
        "wrapped_dek",
        "api_key",
        "wrapped_api_key",
        "api_key_nonce",
    }
)


def redact_secrets(val: object) -> object:
    """Recursively replace secret fields with '***' and scrub free-text strings."""
    if isinstance(val, dict):
        cleaned_dict: dict[object, object] = {}
        for k, v in val.items():
            if isinstance(k, str) and k.lower() in _SECRET_KEY_NAMES:
                cleaned_dict[k] = "***"
            else:
                cleaned_dict[k] = redact_secrets(v)
        return cleaned_dict

    if isinstance(val, list):
        return [redact_secrets(item) for item in val]

    if isinstance(val, str):
        return scrub_text(val)

    return val


def strip_empty(val: object) -> object:
    """Recursively remove None, [], {}, and '' while preserving 0 and False."""
    if val is None or val in ("", [], {}):
        return None

    if isinstance(val, dict):
        cleaned_dict: dict[object, object] = {}
        for k, v in val.items():
            cleaned_v = strip_empty(v)
            if cleaned_v is not None:
                cleaned_dict[k] = cleaned_v
        return cleaned_dict or None

    if isinstance(val, list):
        cleaned_list: list[object] = []
        for item in val:
            cleaned_item = strip_empty(item)
            if cleaned_item is not None:
                cleaned_list.append(cleaned_item)
        return cleaned_list or None

    return val


def _is_scalar(val: object) -> bool:
    """Return True if val is a scalar without newlines."""
    if isinstance(val, str):
        return "\n" not in val
    return isinstance(val, (int, float, bool))


def _is_small_scalar_dict(val: object) -> bool:
    """Return True if val is a dict with <= 4 scalar values."""
    if not isinstance(val, dict) or len(val) > _MAX_FLOW_DICT_LEN:
        return False
    return all(_is_scalar(k) and _is_scalar(v) for k, v in val.items())


class InlineSafeDumper(yaml.SafeDumper):
    """Custom YAML SafeDumper formatting small collections inline and literal blocks."""


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    """Represent strings with newlines using literal block style |."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _represent_list(dumper: yaml.SafeDumper, data: list[object]) -> yaml.Node:
    """Represent empty lists, scalar lists, and small dict lists with flow style."""
    flow = (
        len(data) == 0
        or all(_is_scalar(x) for x in data)
        or (len(data) <= _MAX_FLOW_DICT_LEN and all(_is_small_scalar_dict(x) for x in data))
    )
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow or None)


def _represent_dict(dumper: yaml.SafeDumper, data: dict[object, object]) -> yaml.Node:
    """Represent small nested dicts with flow style while keeping root in block style."""
    is_root = len(dumper.represented_objects) == 0
    flow = False if is_root else (True if _is_small_scalar_dict(data) else None)
    return dumper.represent_mapping("tag:yaml.org,2002:map", data, flow_style=flow)


def _reject_non_primitive(dumper: yaml.SafeDumper, data: object) -> yaml.Node:
    """Disallow dumping non-primitive types or Python tags."""
    del dumper
    msg = f"Cannot dump non-primitive type: {type(data).__name__}"
    raise TypeError(msg)


InlineSafeDumper.add_representer(str, _represent_str)
InlineSafeDumper.add_representer(list, _represent_list)
InlineSafeDumper.add_representer(dict, _represent_dict)
InlineSafeDumper.add_representer(set, _reject_non_primitive)
InlineSafeDumper.add_representer(frozenset, _reject_non_primitive)
InlineSafeDumper.add_representer(None, _reject_non_primitive)  # type: ignore[arg-type]


def dump_yaml(data: object, *, strip_nulls: bool = True) -> str:
    """Serialize data into canonical YAML using InlineSafeDumper.

    Optionally strips empty fields (None, '', [], {}) while preserving 0 and False.
    Secret fields (secret, client_secret, bind_dn_password) are redacted with '***'.
    """
    if data is None:
        return ""

    sanitized = redact_secrets(data)
    to_dump = strip_empty(sanitized) if strip_nulls else sanitized
    if to_dump is None:
        if isinstance(data, dict):
            return "{}\n"
        return "[]\n" if isinstance(data, list) else ""

    if to_dump == {}:
        return "{}\n"
    if to_dump == []:
        return "[]\n"

    return yaml.dump(
        to_dump,
        Dumper=InlineSafeDumper,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )
