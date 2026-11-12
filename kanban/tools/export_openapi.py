"""Export canonical OpenAPI 3.1 specification document from FastAPI app factory."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from kanban.app import create_app


def export_openapi() -> str:
    """Generate deterministic, formatted OpenAPI JSON document with sorted keys."""
    app = create_app()
    openapi_doc: dict[str, Any] = app.openapi()
    return json.dumps(openapi_doc, indent=2, sort_keys=True) + "\n"


def main() -> None:
    """CLI entrypoint printing OpenAPI document to stdout or target file path."""
    output = export_openapi()
    if len(sys.argv) > 1:
        target_path = Path(sys.argv[1])
        target_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
