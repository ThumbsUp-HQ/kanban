# Copyright 2026 Kanban Platform Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Agent ASGI application factory composing core Kanban app with agent routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.sparkle.router import router as sparkle_router
from kanban.app import create_app

if TYPE_CHECKING:
    from fastapi import FastAPI

    from kanban.settings import Settings

__all__ = ["create_agent_app"]


def create_agent_app(settings: Settings | None = None) -> FastAPI:
    """Create canonical Kanban ASGI application composed with Agent sparkle routes.

    Preserves unidirectional dependency layering: agent -> mcp -> kanban -> database.
    """
    app = create_app(settings)

    # Position sparkle_router ahead of the fallback catch-all /api/{full_path:path} route
    # if not already mounted
    if not any(getattr(route, "path", "").startswith("/api/v1/sparkle") for route in app.routes):
        fallback_idx = None
        for i, route in enumerate(app.router.routes):
            orig = getattr(route, "original_router", None)
            if orig and any("{full_path:path}" in getattr(sub, "path", "") for sub in orig.routes):
                fallback_idx = i
                break

        app.include_router(sparkle_router)
        if fallback_idx is not None:
            sparkle_entry = app.router.routes.pop()
            app.router.routes.insert(fallback_idx, sparkle_entry)

    return app
