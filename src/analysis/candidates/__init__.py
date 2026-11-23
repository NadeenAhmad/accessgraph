"""Offline semantic candidate generation package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from .builder import CandidateBuildSummary, build_semantic_candidates

__all__ = ["CandidateBuildSummary", "build_semantic_candidates"]


def __getattr__(name: str) -> Any:
  if name in __all__:
    from .builder import CandidateBuildSummary, build_semantic_candidates

    exports = {
      "CandidateBuildSummary": CandidateBuildSummary,
      "build_semantic_candidates": build_semantic_candidates,
    }
    return exports[name]
  raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
