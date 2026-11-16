"""Pydantic schemas for object links and canonical URLs.

Traceability: Spec S7.2 8m, S12.1.
"""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class LinkCreateRequest(BaseModel):
    """Payload for creating a directed typed link from an object to a target."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Target object reference (UUID, canonical key, or project identifier)",
    )
    link_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="User-creatable link kind (e.g. BLOCKS, RELATES_TO, DUPLICATES)",
    )


class UnrestrictedEndpointOut(BaseModel):
    """Visible far endpoint details when readable by the caller."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Unique entity identifier (UUIDv7)")
    type: str = Field(description="Entity object kind (e.g. issue, doc, sticky)")
    key: str = Field(description="Canonical entity key (e.g. KAN-142)")
    title: str = Field(description="Display title of the object")


class RestrictedEndpointOut(BaseModel):
    """Masked far endpoint details when unreadable under the caller's RLS session."""

    model_config = ConfigDict(extra="forbid")

    restricted: Literal[True] = Field(
        default=True, description="Indicates the far object is restricted"
    )
    label: Literal["🔒 Restricted Object"] = Field(
        default="🔒 Restricted Object", description="Static non-leaking label"
    )


type EndpointOut = Annotated[
    RestrictedEndpointOut | UnrestrictedEndpointOut,
    Field(
        union_mode="left_to_right",
        description="Link endpoint representation (unrestricted or masked restricted placeholder)",
    ),
]


class OutboundLinkOut(BaseModel):
    """Outbound link representation directed from queried object to target."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Unique object link identifier")
    link_type: str = Field(description="Typed relationship kind")
    link_state: str = Field(description="State of the link: ACTIVE or FLAGGED_INVALID")
    target: EndpointOut = Field(description="Target endpoint (unrestricted or masked)")


class InboundLinkOut(BaseModel):
    """Inbound link representation directed from source to queried object."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Unique object link identifier")
    link_type: str = Field(description="Typed relationship kind")
    link_state: str = Field(description="State of the link: ACTIVE or FLAGGED_INVALID")
    source: EndpointOut = Field(description="Source endpoint (unrestricted or masked)")


class LinksListResponse(BaseModel):
    """Response containing inbound and outbound typed links for an object."""

    model_config = ConfigDict(extra="forbid")

    outbound: list[OutboundLinkOut] = Field(
        default_factory=list, description="Outbound links from queried object"
    )
    inbound: list[InboundLinkOut] = Field(
        default_factory=list, description="Inbound links to queried object"
    )
    truncated: bool = Field(default=False, description="True if link count exceeded 500 cap")


class CanonicalUrlResponse(BaseModel):
    """Canonical URL and safe Markdown link representation."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(description="Server-authoritative canonical URL")
    markdown: str = Field(description="Escaped Markdown link representation")
