"""Kanban core web application, REST/WS APIs, auth, and state machines."""

from typing import Any

__version__: str = "0.0.0"

__all__ = ["create_app"]


def __getattr__(name: str) -> Any:  # noqa: ANN401
    if name == "create_app":
        from kanban.app import create_app  # noqa: PLC0415

        return create_app
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
