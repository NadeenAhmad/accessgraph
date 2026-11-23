"""Neutral accessibility evidence extraction package."""

from __future__ import annotations

from typing import Any

__all__ = [
  "extract_accessibility_context",
  "write_accessibility_context",
]


def __getattr__(name: str) -> Any:
  if name in __all__:
    from .extractor import extract_accessibility_context, write_accessibility_context

    exports = {
      "extract_accessibility_context": extract_accessibility_context,
      "write_accessibility_context": write_accessibility_context,
    }
    return exports[name]
  raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
