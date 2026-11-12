# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Identity assertions and resolver protocols for external authentication cards (KB-P2-06)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    import uuid

    from starlette.requests import Request

MAX_SUBJECT_LENGTH: Final[int] = 255


@dataclass(frozen=True, slots=True)
class ExternalIdentityAssertion:
    """External identity claims asserted by an IdP card (S4.2, KB-P2-06).

    Never used for implicit account linking via email.
    """

    card_id: uuid.UUID
    subject: str
    email: str | None
    email_verified: bool
    display_name: str | None
    groups: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate invariant constraints on identity assertion."""
        if not self.subject or len(self.subject) > MAX_SUBJECT_LENGTH:
            msg = f"Assertion subject must be non-empty and at most {MAX_SUBJECT_LENGTH} characters"
            raise ValueError(msg)
        raw_groups: object = self.groups
        if not isinstance(raw_groups, tuple):
            if not hasattr(raw_groups, "__iter__"):
                msg = f"Groups must be an iterable (got {type(raw_groups).__name__})"
                raise TypeError(msg)
            converted: tuple[str, ...] = tuple(str(g) for g in raw_groups)
            object.__setattr__(self, "groups", converted)


@dataclass(frozen=True, slots=True)
class ResolvedLogin:
    """Resolved user principal and workspace for issuing an authenticated session."""

    principal_id: uuid.UUID
    workspace_id: uuid.UUID
    aal_level: int = 1
    mfa_pending: bool = False


class IdentityResolver(Protocol):
    """Protocol for resolving an external identity assertion to an existing or provisioned user."""

    async def resolve(
        self,
        assertion: ExternalIdentityAssertion,
        request: Request,
        link_intent_id: uuid.UUID | None,
    ) -> ResolvedLogin:
        """Resolve external identity assertion, or raise ProblemException."""
        ...


class RejectAllIdentityResolver:
    """Default fail-closed resolver active until full auto-provisioning (KB-P2-08) is installed."""

    async def resolve(
        self,
        assertion: ExternalIdentityAssertion,
        request: Request,
        link_intent_id: uuid.UUID | None,
    ) -> ResolvedLogin:
        """Reject all assertions with 403 IDENTITY_NOT_PROVISIONED."""
        del assertion, request, link_intent_id
        raise ProblemException(
            code="IDENTITY_NOT_PROVISIONED",
            status=403,
            title="Identity Not Provisioned",
            detail="External identity is not provisioned in this workspace",
        )
