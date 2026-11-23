from __future__ import annotations

from typing import Any

from ..evidence_helpers import (
  bounding_box_ref,
  dom_snippet,
  element_ref,
  evidence_items,
  first_present_text,
  is_visible,
  truncate_text,
)
from ..models import RunState

STRUCTURAL_LANDMARK_ROLES = {
  "banner",
  "complementary",
  "contentinfo",
  "main",
  "navigation",
  "region",
  "search",
}

NATIVE_LANDMARK_TAGS_BY_ROLE = {
  "banner": {"header"},
  "complementary": {"aside"},
  "contentinfo": {"footer"},
  "main": {"main"},
  "navigation": {"nav"},
  "region": {"section"},
  "search": {"search"},
}


def visible_landmarks(state: RunState) -> list[dict[str, Any]]:
  return [landmark for landmark in evidence_items(state, "landmarks") if is_visible(landmark)]


def landmark_relationships(state: RunState) -> list[dict[str, object]]:
  return [
    relationship
    for relationship in evidence_items(state, "relationships")
    if str(relationship.get("type") or "") == "landmark_contains"
  ]


def relationships_for_element(state: RunState, element_id: str, *, limit: int = 30) -> list[dict[str, object]]:
  relationships = evidence_items(state, "relationships")
  return [
    relationship
    for relationship in relationships
    if relationship.get("from_element_id") == element_id or relationship.get("to_element_id") == element_id
  ][:limit]


def has_landmark_context(state: RunState, landmark: dict[str, Any], relationships: list[dict[str, object]]) -> bool:
  page = compact_page(state)
  context = landmark.get("context") if isinstance(landmark.get("context"), dict) else {}
  return bool(
    first_present_text(
      landmark,
      (
        "accessible_name",
        "aria_label",
        "aria_labelledby",
        "title",
        "text",
        "text_sample",
      ),
    )
    or first_present_text(context, ("nearby_text", "parent_text", "section_heading"))
    or first_present_text(page, ("title", "body_text_sample"))
    or relationships
  )


def landmark_ref(landmark: dict[str, Any], *, relationship_role: str = "landmark") -> dict[str, object]:
  return {
    **element_ref("landmarks", landmark),
    "relationship_role": relationship_role,
  }


def compact_landmark(landmark: dict[str, Any]) -> dict[str, object]:
  return {
    "element_id": str(landmark.get("element_id") or ""),
    "kind": str(landmark.get("kind") or ""),
    "tag": str(landmark.get("tag") or ""),
    "role": landmark.get("role"),
    "selector": str(landmark.get("selector") or ""),
    "text": truncate_text(landmark.get("text")),
    "text_sample": truncate_text(landmark.get("text_sample")),
    "accessible_name": landmark.get("accessible_name"),
    "aria_label": landmark.get("aria_label"),
    "aria_labelledby": landmark.get("aria_labelledby"),
    "aria_describedby": landmark.get("aria_describedby"),
    "title": landmark.get("title"),
  }


def compact_page(state: RunState) -> dict[str, object]:
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  return {
    "url": str(page.get("url") or state.metadata.get("url") or ""),
    "title": truncate_text(page.get("title") or state.metadata.get("title")),
    "body_text_sample": truncate_text(page.get("body_text_sample")),
    "document_lang": str(page.get("document_lang") or ""),
    "html_lang": page.get("html_lang"),
  }


def compact_headings(state: RunState, *, limit: int = 10) -> list[dict[str, object]]:
  headings: list[dict[str, object]] = []
  for heading in evidence_items(state, "headings"):
    text = truncate_text(heading.get("text"))
    if not text:
      continue
    headings.append(
      {
        "element_id": str(heading.get("element_id") or ""),
        "tag": str(heading.get("tag") or ""),
        "level": heading.get("level"),
        "text": text,
        "selector": str(heading.get("selector") or ""),
      }
    )
    if len(headings) >= limit:
      break
  return headings


def related_element_refs(
  state: RunState,
  relationships: list[dict[str, object]],
  *,
  exclude_element_id: str,
  limit: int = 12,
) -> list[dict[str, object]]:
  by_id = _elements_by_id(state)
  refs: list[dict[str, object]] = []
  seen: set[tuple[str, str, str]] = set()
  for relationship in relationships:
    related_ids = [
      str(relationship.get("from_element_id") or ""),
      str(relationship.get("to_element_id") or ""),
    ]
    for element_id in related_ids:
      if not element_id or element_id == exclude_element_id:
        continue
      item = by_id.get(element_id)
      if not item:
        continue
      bucket, element = item
      key = (bucket, element_id, str(relationship.get("type") or "related"))
      if key in seen:
        continue
      seen.add(key)
      refs.append(
        {
          **element_ref(bucket, element),
          "relationship_role": "related",
          "relationship_type": str(relationship.get("type") or ""),
          "method": str(relationship.get("method") or ""),
        }
      )
      if len(refs) >= limit:
        return refs
  return refs


def bounding_boxes_for(items_to_box: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, object]]:
  return [bounding_box_ref(item) for item in items_to_box[:limit]]


def dom_snippets_for(items_to_snip: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, object]]:
  snippets = [dom_snippet(item) for item in items_to_snip[:limit]]
  return [snippet for snippet in snippets if snippet]


def structural_role(landmark: dict[str, Any]) -> str:
  return str(landmark.get("role") or "").strip().lower()


def has_non_native_structural_role(landmark: dict[str, Any]) -> bool:
  role = structural_role(landmark)
  tag = str(landmark.get("tag") or "").strip().lower()
  if role not in STRUCTURAL_LANDMARK_ROLES:
    return False
  return tag not in NATIVE_LANDMARK_TAGS_BY_ROLE.get(role, set())


def _elements_by_id(state: RunState) -> dict[str, tuple[str, dict[str, Any]]]:
  buckets = (
    "referenced_elements",
    "images",
    "videos",
    "links",
    "buttons",
    "forms",
    "form_controls",
    "headings",
    "landmarks",
    "tables",
    "visual_cues",
    "focusables",
  )
  by_id: dict[str, tuple[str, dict[str, Any]]] = {}
  for bucket in buckets:
    for item in evidence_items(state, bucket):
      element_id = str(item.get("element_id") or "")
      if element_id:
        by_id[element_id] = (bucket, item)
  return by_id
