# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Quantizer and Matryoshka head projection adapters for agent embeddings."""

from __future__ import annotations

from kanban.services.synaptic_rescorer import (
    EmbeddedChunkPayload,
    MatryoshkaQuantizer,
    SynapticActivationResult,
    SynapticSeed,
    compute_binary_sign,
    dequantize_int8,
    exact_identifier_heading_maxsim,
    extract_heading_anchors,
    extract_matryoshka_head,
    int8_dot_product,
    quantize_int8,
    reciprocal_rank_fusion,
)

__all__ = [
    "EmbeddedChunkPayload",
    "MatryoshkaQuantizer",
    "SynapticActivationResult",
    "SynapticSeed",
    "compute_binary_sign",
    "dequantize_int8",
    "exact_identifier_heading_maxsim",
    "extract_heading_anchors",
    "extract_matryoshka_head",
    "int8_dot_product",
    "quantize_int8",
    "reciprocal_rank_fusion",
]
