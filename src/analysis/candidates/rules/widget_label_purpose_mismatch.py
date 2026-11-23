from __future__ import annotations

from typing import Any

from ..destination_state_context import build_destination_state_context, saved_html_attributes
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
from .structure_common import compact_page, relationships_for_element

CANDIDATE_TYPE = "widget-label-purpose-mismatch"
WIDGET_LABEL_CONTEXT_SCHEMA_VERSION = "widget_label_purpose_context_v1"
WIDGET_ROLES = frozenset(
  {
    "tab",
    "tablist",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "treeitem",
    "option",
    "switch",
    "checkbox",
    "radio",
    "slider",
    "spinbutton",
    "combobox",
    "button",
  }
)
ARIA_WIDGET_ATTRIBUTES = (
  "aria-controls",
  "aria-expanded",
  "aria-selected",
  "aria-checked",
  "aria-pressed",
)


def build_widget_label_purpose_mismatch_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  for bucket, widget in _widget_sources(state):
    if not is_visible(widget):
      continue
    label = first_present_text(
      widget,
      ("accessible_name", "text", "aria_label", "label", "wrapping_label", "title", "value"),
    )
    if not label:
      continue
    relationships = relationships_for_element(state, str(widget.get("element_id") or ""))
    snippet = dom_snippet(widget)
    supporting: dict[str, object] = {
      "page": compact_page(state),
      "context": widget.get("context") if isinstance(widget.get("context"), dict) else {},
      "structure": widget.get("structure") if isinstance(widget.get("structure"), dict) else {},
      "relationships": relationships,
      "widget_label_purpose_context_v1": _build_widget_context(state, bucket, widget, relationships),
    }
    destination_context = build_destination_state_context(run, state, widget, bucket=bucket)
    if destination_context:
      supporting["destination_state_context_v1"] = destination_context
    primary_ref = element_ref(bucket, widget)
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        primary_element_ref=primary_ref,
        element_refs=[primary_ref, *_controlled_refs(state, relationships)],
        selection_reason=["interactive_widget_with_label_role_or_state_evidence"],
        required_context=[
          "widget label or accessible name",
          "widget role/type",
          "controlled content or resulting state when available",
        ],
        evidence={
          "primary": {"widget": _compact_widget(bucket, widget)},
          "supporting": supporting,
          "bounding_boxes": [bounding_box_ref(widget)],
          "dom_snippets": [snippet] if snippet else [],
        },
        graph_context=graph_context,
      )
    )
  return records


def _widget_sources(state: RunState) -> list[tuple[str, dict[str, Any]]]:
  sources: list[tuple[str, dict[str, Any]]] = []
  seen: set[str] = set()
  for bucket in ("buttons", "form_controls", "links", "focusables", "visual_cues"):
    for item in evidence_items(state, bucket):
      if not _is_widget_source(item):
        continue
      key = _identity_key(bucket, item)
      if key in seen:
        continue
      seen.add(key)
      sources.append((bucket, item))
  return sources


def _is_widget_source(item: dict[str, Any]) -> bool:
  attrs = saved_html_attributes(item.get("raw_html"))
  role = _role(item, attrs)
  if role in WIDGET_ROLES:
    return True
  if str(item.get("tag") or "").lower() == "summary":
    return True
  return any(attrs.get(name) or item.get(_python_attr_name(name)) for name in ARIA_WIDGET_ATTRIBUTES)


def _identity_key(bucket: str, item: dict[str, Any]) -> str:
  element_id = str(item.get("element_id") or "")
  if element_id:
    return element_id
  selector = str(item.get("selector") or "")
  xpath = str(item.get("xpath") or "")
  return f"{bucket}|{selector}|{xpath}"


def _role(item: dict[str, Any], attrs: dict[str, str]) -> str:
  return str(item.get("role") or attrs.get("role") or "").strip().lower()


def _python_attr_name(html_name: str) -> str:
  return html_name.replace("-", "_")


def _compact_widget(bucket: str, widget: dict[str, Any]) -> dict[str, object]:
  attrs = saved_html_attributes(widget.get("raw_html"))
  return {
    "bucket": bucket,
    "element_id": str(widget.get("element_id") or ""),
    "tag": str(widget.get("tag") or ""),
    "role": _role(widget, attrs) or None,
    "selector": str(widget.get("selector") or ""),
    "text": truncate_text(widget.get("text")),
    "accessible_name": truncate_text(widget.get("accessible_name")),
    "aria_label": truncate_text(widget.get("aria_label")),
    "aria_labelledby": truncate_text(widget.get("aria_labelledby")),
    "title": truncate_text(widget.get("title")),
    "href": truncate_text(widget.get("href")),
    "type": truncate_text(widget.get("type")),
    "aria_controls": _state_attr(widget, attrs, "aria-controls"),
    "aria_expanded": _state_attr(widget, attrs, "aria-expanded"),
    "aria_selected": _state_attr(widget, attrs, "aria-selected"),
    "aria_checked": _state_attr(widget, attrs, "aria-checked"),
    "aria_pressed": _state_attr(widget, attrs, "aria-pressed"),
  }


def _build_widget_context(
  state: RunState,
  bucket: str,
  widget: dict[str, Any],
  relationships: list[dict[str, object]],
) -> dict[str, object]:
  attrs = saved_html_attributes(widget.get("raw_html"))
  return {
    "schema_version": WIDGET_LABEL_CONTEXT_SCHEMA_VERSION,
    "widget": _compact_widget(bucket, widget),
    "labeling": {
      "visible_text": truncate_text(widget.get("text")),
      "computed_accessible_name": truncate_text(widget.get("accessible_name")),
      "aria_label": truncate_text(widget.get("aria_label")),
      "aria_labelledby": truncate_text(widget.get("aria_labelledby")),
      "title": truncate_text(widget.get("title")),
    },
    "state_attributes": {
      "aria_controls": _state_attr(widget, attrs, "aria-controls"),
      "aria_expanded": _state_attr(widget, attrs, "aria-expanded"),
      "aria_selected": _state_attr(widget, attrs, "aria-selected"),
      "aria_checked": _state_attr(widget, attrs, "aria-checked"),
      "aria_pressed": _state_attr(widget, attrs, "aria-pressed"),
    },
    "controlled_or_revealed_content": _controlled_content(state, relationships),
    "local_context": widget.get("context") if isinstance(widget.get("context"), dict) else {},
    "structure": widget.get("structure") if isinstance(widget.get("structure"), dict) else {},
  }


def _state_attr(widget: dict[str, Any], attrs: dict[str, str], html_name: str) -> str:
  direct = widget.get(_python_attr_name(html_name))
  if direct not in (None, ""):
    return truncate_text(direct, max_length=120)
  cue_attrs = widget.get("cue_attributes") if isinstance(widget.get("cue_attributes"), dict) else {}
  cue_value = cue_attrs.get(_python_attr_name(html_name))
  if cue_value not in (None, ""):
    return truncate_text(cue_value, max_length=120)
  return truncate_text(attrs.get(html_name), max_length=120)


def _controlled_refs(state: RunState, relationships: list[dict[str, object]]) -> list[dict[str, object]]:
  by_id = _elements_by_id(state)
  refs: list[dict[str, object]] = []
  for relationship in relationships:
    if str(relationship.get("type") or "") not in {"controls", "owns"}:
      continue
    target_id = str(relationship.get("to_element_id") or "")
    target = by_id.get(target_id)
    if target:
      bucket, item = target
      refs.append({**element_ref(bucket, item), "relationship_role": str(relationship.get("type") or "")})
  return refs[:8]


def _controlled_content(state: RunState, relationships: list[dict[str, object]]) -> list[dict[str, object]]:
  by_id = _elements_by_id(state)
  content: list[dict[str, object]] = []
  for relationship in relationships:
    if str(relationship.get("type") or "") not in {"controls", "owns"}:
      continue
    target_id = str(relationship.get("to_element_id") or "")
    target = by_id.get(target_id)
    if not target:
      continue
    bucket, item = target
    content.append(
      {
        "relationship_type": str(relationship.get("type") or ""),
        "bucket": bucket,
        "element_id": target_id,
        "tag": str(item.get("tag") or ""),
        "role": item.get("role"),
        "selector": str(item.get("selector") or ""),
        "text_excerpt": truncate_text(item.get("text") or item.get("text_sample") or item.get("accessible_name"), max_length=240),
        "visible": is_visible(item),
      }
    )
    if len(content) >= 8:
      break
  return content


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
