"""Shared helpers for compacting Accessibility context into candidate records."""

from __future__ import annotations

from typing import Any

from .models import MAX_SNIPPET_LENGTH, RunState


def evidence_items(state: RunState, key: str) -> list[dict[str, Any]]:
  raw = state.accessibility_context.get(key)
  return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def truncate_text(value: object, *, max_length: int = MAX_SNIPPET_LENGTH) -> str:
  normalized = " ".join(str(value or "").split())
  return normalized[:max_length]


def optional_text(value: object, *, max_length: int = MAX_SNIPPET_LENGTH) -> str:
  return truncate_text(value, max_length=max_length)


def is_visible(item: dict[str, Any]) -> bool:
  return item.get("visible") is not False


def first_present_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
  for key in keys:
    value = optional_text(item.get(key))
    if value:
      return value
  return ""


def element_ref(bucket: str, item: dict[str, Any]) -> dict[str, object]:
  return {
    "bucket": bucket,
    "element_id": str(item.get("element_id") or ""),
    "selector": str(item.get("selector") or ""),
    "xpath": str(item.get("xpath") or ""),
  }


def bounding_box_ref(item: dict[str, Any]) -> dict[str, object]:
  return {
    "element_id": str(item.get("element_id") or ""),
    "selector": str(item.get("selector") or ""),
    "bounding_box": item.get("bounding_box") if isinstance(item.get("bounding_box"), dict) else {},
  }


def dom_snippet(item: dict[str, Any]) -> dict[str, object] | None:
  raw_html = truncate_text(item.get("raw_html"))
  if not raw_html:
    return None
  return {
    "element_id": str(item.get("element_id") or ""),
    "selector": str(item.get("selector") or ""),
    "html": raw_html,
  }
