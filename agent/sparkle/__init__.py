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
"""Sparkle FIM completion engine package."""

from agent.sparkle.output_filter import filter_completion
from agent.sparkle.pipeline import (
    SparkleRequest,
    SparkleResult,
    SparkleStatus,
    run_sparkle_pipeline,
)
from agent.sparkle.retrieval import retrieve_context
from agent.sparkle.router import router as sparkle_router

__all__ = [
    "SparkleRequest",
    "SparkleResult",
    "SparkleStatus",
    "filter_completion",
    "retrieve_context",
    "run_sparkle_pipeline",
    "sparkle_router",
]
