from __future__ import annotations

from typing import Any

from ..evidence_helpers import evidence_items, first_present_text, is_visible, truncate_text
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload
from .structure_common import (
  bounding_box_ref,
  compact_landmark,
  compact_page,
  dom_snippet,
  has_landmark_context,
  landmark_ref,
  related_element_refs,
  relationships_for_element,
  visible_landmarks,
)

CANDIDATE_TYPE = "landmark-purpose-mismatch"
LANDMARK_IDENTITY_SCHEMA = "landmark_identity_v1"
LANDMARK_SCOPED_CONTENT_SCHEMA = "landmark_scoped_content_v1"
LANDMARK_SCOPED_TEXT_LIMIT = 900
LANDMARK_SCOPED_ITEM_TEXT_LIMIT = 160
LANDMARK_SCOPED_ITEM_LIMIT = 6
LANDMARK_RELATED_BUCKETS = (
  "headings",
  "links",
  "buttons",
  "form_controls",
  "forms",
  "referenced_elements",
)


def build_landmark_purpose_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  for landmark in visible_landmarks(state):
    element_id = str(landmark.get("element_id") or "")
    if not element_id:
      continue
    if not (landmark.get("role") or landmark.get("tag")):
      continue
    relationships = relationships_for_element(state, element_id)
    if not has_landmark_context(state, landmark, relationships):
      continue
    primary_ref = landmark_ref(landmark)
    related_refs = related_element_refs(state, relationships, exclude_element_id=element_id)
    snippet = dom_snippet(landmark)
    identity = _build_landmark_identity(state, landmark, relationships)
    scoped_content = _build_landmark_scoped_content(state, landmark, relationships, identity)
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        primary_element_ref=primary_ref,
        element_refs=[primary_ref, *related_refs],
        selection_reason=["visible_landmark_with_role_and_context_evidence"],
        required_context=["landmark purpose", "accessible name context", "contained content context"],
        evidence={
          "primary": {
            "landmark": compact_landmark(landmark),
          },
          "supporting": {
            "page": compact_page(state),
            "landmark_identity_v1": identity,
            "landmark_scoped_content_v1": scoped_content,
            "context": landmark.get("context") if isinstance(landmark.get("context"), dict) else {},
            "structure": landmark.get("structure") if isinstance(landmark.get("structure"), dict) else {},
            "relationships": relationships,
          },
          "bounding_boxes": [bounding_box_ref(landmark)],
          "dom_snippets": [snippet] if snippet else [],
        },
        graph_context=graph_context,
      )
    )
  return records


def _build_landmark_identity(
  state: RunState,
  landmark: dict[str, Any],
  relationships: list[dict[str, object]],
) -> dict[str, object]:
  aria_label = truncate_text(landmark.get("aria_label"))
  aria_labelledby = truncate_text(landmark.get("aria_labelledby"))
  title = truncate_text(landmark.get("title"))
  accessible_name = truncate_text(landmark.get("accessible_name"))
  labelledby_text = _labelledby_text(state, landmark, relationships)
  explicit_role = landmark.get("role")
  possible_role = _possible_exposed_role(landmark)

  label_source = ""
  if aria_label:
    label_source = "aria-label"
  elif aria_labelledby:
    label_source = "aria-labelledby"
  elif title:
    label_source = "title"
  elif accessible_name:
    label_source = "computed_accessible_name"

  exposure_reason = "structural landmark evidence"
  if possible_role == "region" and accessible_name:
    exposure_reason = "named section/region evidence"
  elif explicit_role:
    exposure_reason = "explicit role evidence"

  return {
    "schema_version": LANDMARK_IDENTITY_SCHEMA,
    "tag": str(landmark.get("tag") or ""),
    "explicit_role": explicit_role,
    "possible_exposed_role": possible_role,
    "accessible_name": accessible_name,
    "label_source": label_source,
    "aria_label": aria_label,
    "aria_labelledby": aria_labelledby,
    "labelledby_text": labelledby_text,
    "exposure_reason": exposure_reason,
  }


def _build_landmark_scoped_content(
  state: RunState,
  landmark: dict[str, Any],
  relationships: list[dict[str, object]],
  identity: dict[str, object],
) -> dict[str, object]:
  sampled_items = _sample_related_content_items(state, landmark, relationships)
  grouped_items = _group_scoped_items(sampled_items)
  label_text = str(identity.get("accessible_name") or "")
  content_parts: list[str] = []
  source_truncated = False
  for value in (
    landmark.get("text_sample"),
    landmark.get("text"),
  ):
    source_truncated = (
      _append_unique_text(content_parts, value, max_length=LANDMARK_SCOPED_TEXT_LIMIT) or source_truncated
    )
  context = landmark.get("context") if isinstance(landmark.get("context"), dict) else {}
  section_heading = truncate_text(context.get("section_heading"), max_length=LANDMARK_SCOPED_ITEM_TEXT_LIMIT)
  if section_heading:
    _append_unique_scoped_item(
      grouped_items["contained_headings"],
      {
        "kind": "heading",
        "bucket": "context",
        "element_id": "",
        "selector": "",
        "tag": "",
        "text": section_heading,
      },
    )
    source_truncated = (
      _append_unique_text(content_parts, section_heading, max_length=LANDMARK_SCOPED_TEXT_LIMIT) or source_truncated
    )
  for item in sampled_items:
    source_truncated = (
      _append_unique_text(content_parts, item.get("text"), max_length=LANDMARK_SCOPED_TEXT_LIMIT) or source_truncated
    )

  full_excerpt = " ".join(content_parts).strip()
  contained_excerpt = truncate_text(full_excerpt, max_length=LANDMARK_SCOPED_TEXT_LIMIT)

  content_counts: dict[str, int] = {}
  for key, items in grouped_items.items():
    if items:
      content_counts[key.removeprefix("contained_")] = len(items)

  source = "landmark_text_sample"
  if relationships and sampled_items:
    source = "landmark_text_sample_and_related_elements"
  elif context:
    source = "landmark_text_sample_and_context"

  return {
    "schema_version": LANDMARK_SCOPED_CONTENT_SCHEMA,
    "source": source,
    "source_element_ref": {
      "bucket": "landmarks",
      "element_id": str(landmark.get("element_id") or ""),
      "selector": str(landmark.get("selector") or ""),
      "tag": str(landmark.get("tag") or ""),
      "role": landmark.get("role"),
    },
    "label_text": label_text,
    "contained_content_excerpt": contained_excerpt,
    "text_excerpt": contained_excerpt,
    "contained_headings": grouped_items["contained_headings"],
    "contained_text_blocks": grouped_items["contained_text_blocks"],
    "contained_controls": grouped_items["contained_controls"],
    "contained_links": grouped_items["contained_links"],
    "truncated": source_truncated or len(full_excerpt) > len(contained_excerpt),
    "content_counts": content_counts,
    "sampled_items": sampled_items[:LANDMARK_SCOPED_ITEM_LIMIT],
  }


def _sample_related_content_items(
  state: RunState,
  landmark: dict[str, Any],
  relationships: list[dict[str, object]],
) -> list[dict[str, object]]:
  landmark_id = str(landmark.get("element_id") or "")
  if not landmark_id:
    return []
  related_ids: list[str] = []
  for relationship in relationships:
    if str(relationship.get("type") or "") == "labelledby":
      continue
    for key in ("from_element_id", "to_element_id"):
      element_id = str(relationship.get(key) or "")
      if element_id and element_id != landmark_id and element_id not in related_ids:
        related_ids.append(element_id)

  elements = _content_elements_by_id(state)
  sampled: list[dict[str, object]] = []
  for element_id in related_ids:
    item = elements.get(element_id)
    if not item:
      continue
    bucket, element = item
    text = _content_item_text(element)
    if not text:
      continue
    sampled.append(
      {
        "kind": _content_kind(bucket, element),
        "bucket": bucket,
        "element_id": element_id,
        "selector": str(element.get("selector") or ""),
        "tag": str(element.get("tag") or ""),
        "text": truncate_text(text, max_length=LANDMARK_SCOPED_ITEM_TEXT_LIMIT),
      }
    )
    if len(sampled) >= LANDMARK_SCOPED_ITEM_LIMIT:
      break
  return sampled


def _group_scoped_items(sampled_items: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
  groups: dict[str, list[dict[str, object]]] = {
    "contained_headings": [],
    "contained_text_blocks": [],
    "contained_controls": [],
    "contained_links": [],
  }
  for item in sampled_items:
    kind = str(item.get("kind") or "")
    if kind == "heading":
      _append_unique_scoped_item(groups["contained_headings"], item)
    elif kind == "link":
      _append_unique_scoped_item(groups["contained_links"], item)
    elif kind in {"button", "form_control", "form"}:
      _append_unique_scoped_item(groups["contained_controls"], item)
    else:
      _append_unique_scoped_item(groups["contained_text_blocks"], item)
  return groups


def _append_unique_scoped_item(items: list[dict[str, object]], item: dict[str, object]) -> None:
  key = (str(item.get("kind") or ""), str(item.get("text") or ""))
  for existing in items:
    existing_key = (
      str(existing.get("kind") or ""),
      str(existing.get("text") or ""),
    )
    if existing_key == key:
      return
  items.append(item)


def _content_elements_by_id(
  state: RunState,
  *,
  include_hidden: bool = False,
) -> dict[str, tuple[str, dict[str, Any]]]:
  by_id: dict[str, tuple[str, dict[str, Any]]] = {}
  for bucket in LANDMARK_RELATED_BUCKETS:
    for item in evidence_items(state, bucket):
      if not include_hidden and not is_visible(item):
        continue
      element_id = str(item.get("element_id") or "")
      if element_id:
        by_id[element_id] = (bucket, item)
  return by_id


def _labelledby_text(
  state: RunState,
  landmark: dict[str, Any],
  relationships: list[dict[str, object]],
) -> str:
  landmark_id = str(landmark.get("element_id") or "")
  if not landmark_id:
    return ""
  elements = _content_elements_by_id(state, include_hidden=True)
  texts: list[str] = []
  for relationship in relationships:
    if str(relationship.get("type") or "") != "labelledby":
      continue
    related_ids = [
      str(relationship.get("from_element_id") or ""),
      str(relationship.get("to_element_id") or ""),
    ]
    for element_id in related_ids:
      if not element_id or element_id == landmark_id:
        continue
      item = elements.get(element_id)
      if not item:
        continue
      text = _content_item_text(item[1])
      if text and text not in texts:
        texts.append(text)
  return truncate_text(" ".join(texts), max_length=LANDMARK_SCOPED_ITEM_TEXT_LIMIT)


def _possible_exposed_role(landmark: dict[str, Any]) -> str:
  explicit_role = str(landmark.get("role") or "").strip()
  if explicit_role:
    return explicit_role
  tag = str(landmark.get("tag") or "").strip().lower()
  accessible_name = truncate_text(landmark.get("accessible_name"))
  if tag == "main":
    return "main"
  if tag == "nav":
    return "navigation"
  if tag == "aside":
    return "complementary"
  if tag == "footer":
    return "contentinfo"
  if tag == "header":
    return "banner"
  if tag == "section" and accessible_name:
    return "region"
  return ""


def _content_item_text(item: dict[str, Any]) -> str:
  return first_present_text(
    item,
    (
      "text",
      "text_sample",
      "accessible_name",
      "aria_label",
      "alt",
      "title",
      "placeholder",
      "value",
      "name",
    ),
  )


def _content_kind(bucket: str, item: dict[str, Any]) -> str:
  if bucket == "headings":
    return "heading"
  if bucket == "links":
    return "link"
  if bucket == "buttons":
    return "button"
  if bucket == "form_controls":
    return "form_control"
  if bucket == "forms":
    return "form"
  tag = str(item.get("tag") or "").lower()
  if tag in {"p", "li", "dt", "dd"}:
    return "text_block"
  return "other_text"


def _append_unique_text(text_parts: list[str], value: object, *, max_length: int) -> bool:
  normalized = " ".join(str(value or "").split())
  text = truncate_text(value, max_length=max_length)
  if text and text not in text_parts:
    text_parts.append(text)
  return len(normalized) > len(text)
