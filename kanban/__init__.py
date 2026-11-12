"""Kanban core web application, REST/WS APIs, auth, and state machines."""

from kanban.app import create_app

__version__: str = "0.0.0"

__all__ = ["create_app"]
