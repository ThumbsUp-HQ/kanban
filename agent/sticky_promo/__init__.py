# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Sticky -> Doc AI structuring proposal schemas, serialization, and pipeline (KB-P5-26)."""

from __future__ import annotations

from agent.sticky_promo.schemas import (
    DocSection,
    StickyDocProposal,
    render_canonical_doc_markdown,
)

__all__ = [
    "DocSection",
    "StickyDocProposal",
    "render_canonical_doc_markdown",
]
