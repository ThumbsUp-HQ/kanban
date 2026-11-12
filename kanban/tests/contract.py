"""Shared contract-capture harness for API tests (KB-P3-01a).

``ContractRecorder`` collects request/response exchanges and, when ``KB_CONTRACT_OUT`` is set,
writes them as JSON for the reality-checker proof packet. Credential-bearing header values
(``Cookie``, ``Set-Cookie``, ``X-CSRF-Token``, ``Authorization``) are always replaced by
``"<redacted>"`` before they are stored, so a recorded contract can never leak a credential.

Failure modes: ``write`` raises ``OSError`` if the destination is not writable; ``record`` never
raises for non-JSON bodies (they are stored as decoded text, or ``None`` when empty).
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import httpx

REDACTED: Final[str] = "<redacted>"
SENSITIVE_HEADERS: Final[frozenset[str]] = frozenset(
    {"cookie", "set-cookie", "x-csrf-token", "authorization"}
)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of ``headers`` with credential-bearing values redacted."""
    return {k: (REDACTED if k.lower() in SENSITIVE_HEADERS else v) for k, v in headers.items()}


def _decode_body(content: bytes) -> Any:  # noqa: ANN401  # Arbitrary JSON document
    """Decode an HTTP body as JSON, falling back to text, or ``None`` when empty."""
    if not content:
        return None
    try:
        return json.loads(content)
    except ValueError:
        return content.decode("utf-8", errors="replace")


class ContractRecorder:
    """Collects named HTTP exchanges for contract documentation."""

    def __init__(self, ticket: str | None = None) -> None:
        """Create an empty recorder for ``ticket`` (defaults to ``KB_TICKET_ID``)."""
        self.ticket = ticket if ticket is not None else os.environ.get("KB_TICKET_ID", "")
        self.exchanges: list[dict[str, Any]] = []

    def record(self, name: str, request: httpx.Request, response: httpx.Response) -> None:
        """Store one exchange with sensitive header values redacted."""
        self.exchanges.append(
            {
                "name": name,
                "request": {
                    "method": request.method,
                    "path": request.url.raw_path.decode("ascii"),
                    "headers": redact_headers(dict(request.headers)),
                    "body": _decode_body(request.content),
                },
                "response": {
                    "status": response.status_code,
                    "headers": redact_headers(dict(response.headers)),
                    "body": _decode_body(response.content),
                },
            }
        )

    def to_document(self) -> dict[str, Any]:
        """Return the JSON-serializable contract document."""
        return {"ticket": self.ticket, "exchanges": list(self.exchanges)}

    def write(self, path: Path) -> None:
        """Write the contract document to ``path`` as indented JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_document(), indent=2) + "\n", encoding="utf-8")

    def write_if_configured(self) -> bool:
        """Write to ``KB_CONTRACT_OUT`` when set; return True if a file was written."""
        from pathlib import Path  # noqa: PLC0415  # Runtime-only import (TYPE_CHECKING above)

        out = os.environ.get("KB_CONTRACT_OUT")
        if not out:
            return False
        self.write(Path(out))
        return True
