from __future__ import annotations

from typing import Any

from ..destination_state_context import saved_html_attributes
from ..evidence_helpers import (
  bounding_box_ref,
  dom_snippet,
  element_ref,
  evidence_items,
  first_present_text,
  is_visible,
  truncate_text,
)
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload
from .structure_common import compact_headings, compact_page, relationships_for_element

CANDIDATE_TYPE = "aria-state-mismatch"
ARIA_STATE_CONTEXT_SCHEMA_VERSION = "aria_state_context_v1"
ARIA_STATE_ATTRIBUTES = (
  "aria-current",
  "aria-expanded",
  "aria-selected",
  "aria-checked",
  "aria-pressed",
)


def build_aria_state_mismatch_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  for bucket, element in _stateful_elements(state):
    attributes = _aria_state_attributes(element)
    if not attributes or not is_visible(element):
      continue
    relationships = relationships_for_element(state, str(element.get("element_id") or ""))
    snippet = dom_snippet(element)
    primary_ref = element_ref(bucket, element)
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        primary_element_ref=primary_ref,
        element_refs=[primary_ref, *_controlled_refs(state, relationships)],
        selection_reason=["element_with_observable_aria_state_attribute"],
        required_context=[
          "ARIA state or property value",
          "current rendered or interaction state",
          "controlled target or peer state where available",
        ],
        evidence={
          "primary": {"aria_state": _compact_aria_state_element(bucket, element, attributes)},
          "supporting": {
            "page": compact_page(state),
            "aria_state_context_v1": _build_aria_state_context(state, bucket, element, attributes, relationships),
            "context": element.get("context") if isinstance(element.get("context"), dict) else {},
            "structure": element.get("structure") if isinstance(element.get("structure"), dict) else {},
            "relationships": relationships,
          },
          "bounding_boxes": [bounding_box_ref(element)],
          "dom_snippets": [snippet] if snippet else [],
        },
        graph_context=graph_context,
      )
    )
  return records


def _stateful_elements(state: RunState) -> list[tuple[str, dict[str, Any]]]:
  sources: list[tuple[str, dict[str, Any]]] = []
  seen: set[str] = set()
  for bucket in ("links", "buttons", "form_controls", "focusables", "visual_cues"):
    for item in evidence_items(state, bucket):
      if not _aria_state_attributes(item):
        continue
      key = str(item.get("element_id") or "") or f"{bucket}|{item.get('selector') or ''}|{item.get('xpath') or ''}"
      if key in seen:
        continue
      seen.add(key)
      sources.append((bucket, item))
  return sources


def _aria_state_attributes(element: dict[str, Any]) -> dict[str, str]:
  raw_attrs = saved_html_attributes(element.get("raw_html"))
  cue_attrs = element.get("cue_attributes") if isinstance(element.get("cue_attributes"), dict) else {}
  values: dict[str, str] = {}
  for html_name in ARIA_STATE_ATTRIBUTES:
    python_name = html_name.replace("-", "_")
    value = element.get(python_name)
    if value in (None, ""):
      value = cue_attrs.get(python_name)
    if value in (None, ""):
      value = raw_attrs.get(html_name)
    value_text = truncate_text(value, max_length=80)
    if value_text:
      values[python_name] = value_text
  return values


def _compact_aria_state_element(
  bucket: str,
  element: dict[str, Any],
  attributes: dict[str, str],
) -> dict[str, object]:
  return {
    "bucket": bucket,
    "element_id": str(element.get("element_id") or ""),
    "tag": str(element.get("tag") or ""),
    "role": element.get("role"),
    "selector": str(element.get("selector") or ""),
    "text": truncate_text(element.get("text")),
    "accessible_name": truncate_text(element.get("accessible_name")),
    "aria_label": truncate_text(element.get("aria_label")),
    "href": truncate_text(element.get("href")),
    "state_attributes": attributes,
  }


def _build_aria_state_context(
  state: RunState,
  bucket: str,
  element: dict[str, Any],
  attributes: dict[str, str],
  relationships: list[dict[str, object]],
) -> dict[str, object]:
  return {
    "schema_version": ARIA_STATE_CONTEXT_SCHEMA_VERSION,
    "declared_state": attributes,
    "associated_element": _compact_aria_state_element(bucket, element, attributes),
    "labeling": {
      "visible_text": truncate_text(element.get("text")),
      "computed_accessible_name": truncate_text(element.get("accessible_name")),
      "aria_label": truncate_text(element.get("aria_label")),
      "title": truncate_text(element.get("title")),
    },
    "rendered_state_observations": {
      "is_visible": is_visible(element),
      "disabled": bool(element.get("disabled")),
      "native_checked": _optional_bool(element.get("checked")),
      "native_selected": _optional_bool(element.get("selected")),
      "value_state": _value_state(element),
      "computed_style": element.get("computed_style") if isinstance(element.get("computed_style"), dict) else {},
      "bounding_box": element.get("bounding_box") if isinstance(element.get("bounding_box"), dict) else {},
    },
    "current_item_context": _current_item_context(state, element, attributes),
    "controlled_targets": _controlled_targets(state, relationships),
    "peer_state_context": _peer_state_context(state, element),
    "local_context": element.get("context") if isinstance(element.get("context"), dict) else {},
  }


def _controlled_refs(state: RunState, relationships: list[dict[str, object]]) -> list[dict[str, object]]:
  refs: list[dict[str, object]] = []
  by_id = _elements_by_id(state)
  for relationship in relationships:
    if str(relationship.get("type") or "") != "controls":
      continue
    target = by_id.get(str(relationship.get("to_element_id") or ""))
    if target:
      bucket, item = target
      refs.append({**element_ref(bucket, item), "relationship_role": "controlled_target"})
  return refs[:6]


def _controlled_targets(state: RunState, relationships: list[dict[str, object]]) -> list[dict[str, object]]:
  by_id = _elements_by_id(state)
  targets: list[dict[str, object]] = []
  for relationship in relationships:
    if str(relationship.get("type") or "") != "controls":
      continue
    target_id = str(relationship.get("to_element_id") or "")
    target = by_id.get(target_id)
    if not target:
      continue
    bucket, item = target
    targets.append(
      {
        "bucket": bucket,
        "element_id": target_id,
        "selector": str(item.get("selector") or ""),
        "tag": str(item.get("tag") or ""),
        "role": item.get("role"),
        "text_excerpt": truncate_text(item.get("text") or item.get("text_sample") or item.get("accessible_name"), max_length=240),
        "visible": is_visible(item),
        "computed_style": item.get("computed_style") if isinstance(item.get("computed_style"), dict) else {},
      }
    )
    if len(targets) >= 6:
      break
  return targets


def _peer_state_context(state: RunState, element: dict[str, Any]) -> list[dict[str, object]]:
  role = truncate_text(element.get("role"), max_length=80).casefold()
  if role not in {"tab", "option", "radio", "checkbox", "switch", "button"}:
    return []
  peers: list[dict[str, object]] = []
  for bucket in ("links", "buttons", "form_controls", "focusables", "visual_cues"):
    for peer in evidence_items(state, bucket):
      if truncate_text(peer.get("role"), max_length=80).casefold() != role:
        continue
      attrs = _aria_state_attributes(peer)
      if not attrs:
        continue
      peers.append(
        {
          "bucket": bucket,
          "element_id": str(peer.get("element_id") or ""),
          "selector": str(peer.get("selector") or ""),
          "text": truncate_text(peer.get("text")),
          "accessible_name": truncate_text(peer.get("accessible_name")),
          "state_attributes": attrs,
        }
      )
      if len(peers) >= 8:
        return peers
  return peers


def _current_item_context(
  state: RunState,
  element: dict[str, Any],
  attributes: dict[str, str],
) -> dict[str, object]:
  if "aria_current" not in attributes:
    return {}

  return {
    "page": compact_page(state),
    "headings": compact_headings(state, limit=4),
    "current_item": _compact_current_item(element, attributes),
    "peer_items": _current_peer_items(state, element),
  }


def _compact_current_item(
  element: dict[str, Any],
  attributes: dict[str, str],
) -> dict[str, object]:
  return {
    "element_id": str(element.get("element_id") or ""),
    "tag": str(element.get("tag") or ""),
    "role": element.get("role"),
    "selector": str(element.get("selector") or ""),
    "text": truncate_text(element.get("text")),
    "accessible_name": truncate_text(element.get("accessible_name")),
    "href": truncate_text(element.get("href")),
    "state_attributes": attributes,
  }


def _current_peer_items(
  state: RunState,
  element: dict[str, Any],
  *,
  limit: int = 8,
) -> list[dict[str, object]]:
  element_id = str(element.get("element_id") or "")
  landmark_key = _nearest_landmark_key(element)
  tag = str(element.get("tag") or "").casefold()
  peers: list[dict[str, object]] = []
  peer_buckets = (
    "links",
    "buttons",
    "focusables",
    "visual_cues",
  )
  if landmark_key and tag == "li":
    peer_buckets = (*peer_buckets, "language_samples")
  for bucket in peer_buckets:
    for peer in evidence_items(state, bucket):
      if str(peer.get("element_id") or "") == element_id:
        continue
      if landmark_key and _nearest_landmark_key(peer) != landmark_key:
        continue
      peer_text = first_present_text(peer, ("text", "accessible_name", "aria_label"))
      if not peer_text:
        continue
      peers.append(
        {
          "bucket": bucket,
          "element_id": str(peer.get("element_id") or ""),
          "tag": str(peer.get("tag") or ""),
          "role": peer.get("role"),
          "selector": str(peer.get("selector") or ""),
          "raw_html": truncate_text(peer.get("raw_html"), max_length=500),
          "text": truncate_text(peer.get("text")),
          "accessible_name": truncate_text(peer.get("accessible_name")),
          "href": truncate_text(peer.get("href")),
          "state_attributes": _aria_state_attributes(peer),
        }
      )
      if len(peers) >= limit:
        return peers
  return peers


def _nearest_landmark_key(element: dict[str, Any]) -> str:
  structure = element.get("structure") if isinstance(element.get("structure"), dict) else {}
  landmark = structure.get("nearest_landmark") if isinstance(structure.get("nearest_landmark"), dict) else {}
  return str(landmark.get("element_id") or landmark.get("selector") or "")


def _elements_by_id(state: RunState) -> dict[str, tuple[str, dict[str, Any]]]:
  by_id: dict[str, tuple[str, dict[str, Any]]] = {}
  for bucket in (
    "referenced_elements",
    "links",
    "buttons",
    "forms",
    "form_controls",
    "headings",
    "landmarks",
    "focusables",
    "visual_cues",
  ):
    for item in evidence_items(state, bucket):
      element_id = str(item.get("element_id") or "")
      if element_id:
        by_id[element_id] = (bucket, item)
  return by_id


def _optional_bool(value: object) -> bool | None:
  if isinstance(value, bool):
    return value
  return None


def _value_state(element: dict[str, Any]) -> str:
  has_value = element.get("has_value")
  if has_value is True:
    return "filled"
  if has_value is False:
    return "empty"
  return "unknown"
