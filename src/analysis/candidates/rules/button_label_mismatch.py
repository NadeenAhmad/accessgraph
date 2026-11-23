from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from ..destination_state_context import build_destination_state_context
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

CANDIDATE_TYPE = "button-label-mismatch"
BUTTON_ACTION_CONTEXT_SCHEMA_VERSION = "button_action_context_v1"
MATCHED_TRIGGER_KEYS = (
  "type",
  "selector",
  "data_testid",
  "dom_path",
  "text",
  "accessible_name",
  "button_type",
  "input_type",
  "role",
  "tag_name",
)


def build_button_label_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  for button in evidence_items(state, "buttons"):
    if not is_visible(button):
      continue
    name = first_present_text(button, ("text", "accessible_name", "aria_label", "title", "value"))
    if not name:
      continue
    relationships = _relationships_for(state, str(button.get("element_id") or ""))
    snippet = dom_snippet(button)
    button_action_context = _build_button_action_context(
      run,
      state,
      button,
      relationships,
    )
    supporting: dict[str, object] = {
      "context": button.get("context") if isinstance(button.get("context"), dict) else {},
      "structure": button.get("structure") if isinstance(button.get("structure"), dict) else {},
      "relationships": relationships,
      "button_action_context_v1": button_action_context,
    }
    destination_context = build_destination_state_context(run, state, button, bucket="buttons")
    if destination_context:
      supporting["destination_state_context_v1"] = destination_context
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        element_refs=[element_ref("buttons", button)],
        selection_reason=["visible_button_with_label_and_context_evidence"],
        required_context=["button purpose", "nearby text context", "interaction context"],
        evidence={
          "primary": {
            "button": _compact_button(button),
          },
          "supporting": supporting,
          "bounding_boxes": [bounding_box_ref(button)],
          "dom_snippets": [snippet] if snippet else [],
        },
        graph_context=graph_context,
      )
    )
  return records


def _relationships_for(state: RunState, element_id: str) -> list[dict[str, object]]:
  relationships = evidence_items(state, "relationships")
  return [
    relationship
    for relationship in relationships
    if relationship.get("from_element_id") == element_id or relationship.get("to_element_id") == element_id
  ][:10]


def _compact_button(button: dict[str, Any]) -> dict[str, object]:
  return {
    "element_id": str(button.get("element_id") or ""),
    "tag": str(button.get("tag") or ""),
    "role": button.get("role"),
    "selector": str(button.get("selector") or ""),
    "text": str(button.get("text") or ""),
    "accessible_name": button.get("accessible_name"),
    "aria_label": button.get("aria_label"),
    "aria_labelledby": button.get("aria_labelledby"),
    "aria_describedby": button.get("aria_describedby"),
    "title": button.get("title"),
    "type": button.get("type"),
    "disabled": bool(button.get("disabled")),
  }


def _build_button_action_context(
  run: RunArtifacts,
  state: RunState,
  button: dict[str, Any],
  relationships: list[dict[str, object]],
) -> dict[str, object]:
  context = button.get("context") if isinstance(button.get("context"), dict) else {}
  structure = button.get("structure") if isinstance(button.get("structure"), dict) else {}
  nearest_heading = structure.get("nearest_heading") if isinstance(structure.get("nearest_heading"), dict) else {}
  nearest_landmark = (
    structure.get("nearest_landmark")
    if isinstance(structure.get("nearest_landmark"), dict)
    else {}
  )
  bounding_box = button.get("bounding_box") if isinstance(button.get("bounding_box"), dict) else {}
  button_id = str(button.get("element_id") or "")
  html_attributes = _saved_html_attributes(button.get("raw_html"))
  transition_context = _matched_outgoing_transition_context(
    run,
    state,
    button,
    html_attributes,
  )

  return {
    "schema_version": BUTTON_ACTION_CONTEXT_SCHEMA_VERSION,
    "button": {
      "element_id": button_id,
      "selector": str(button.get("selector") or ""),
      "html": truncate_text(button.get("raw_html")),
      "tag": str(button.get("tag") or ""),
      "role": button.get("role"),
      "type": button.get("type"),
      "disabled": bool(button.get("disabled")),
    },
    "labeling": {
      "visible_text": truncate_text(button.get("text")),
      "computed_accessible_name": truncate_text(button.get("accessible_name")),
      "aria_label": truncate_text(button.get("aria_label")),
      "aria_labelledby": button.get("aria_labelledby"),
      "aria_labelledby_text": _relationship_text(
        state,
        relationships,
        button_id=button_id,
        relationship_types={"labelledby", "labels"},
      ),
      "aria_describedby": button.get("aria_describedby"),
      "describedby_text": _relationship_text(
        state,
        relationships,
        button_id=button_id,
        relationship_types={"describes"},
      ),
      "title": truncate_text(button.get("title")),
      "value": truncate_text(button.get("value")),
    },
    "visual_content": {
      "icon_text": truncate_text(button.get("icon_text")),
      "image_alt": truncate_text(button.get("image_alt")),
      "svg_title": truncate_text(button.get("svg_title")),
      "screenshot_reference": f"states/{state.state_id}/screenshot.png",
      "bounding_box": bounding_box,
      "has_bounding_box": bool(bounding_box),
    },
    "local_context": {
      "nearby_text": truncate_text(context.get("nearby_text")),
      "parent_text": truncate_text(context.get("parent_text")),
      "section_heading": truncate_text(context.get("section_heading")),
      "parent_tag": structure.get("parent_tag"),
      "parent_role": structure.get("parent_role"),
      "ancestor_roles": structure.get("ancestor_roles") if isinstance(structure.get("ancestor_roles"), list) else [],
      "nearest_heading": _compact_structure_ref(nearest_heading),
      "nearest_landmark": _compact_structure_ref(nearest_landmark),
    },
    "action_evidence": {
      "button_type": button.get("type"),
      "data_action": (
        button.get("data_action")
        or button.get("data-action")
        or html_attributes.get("data-action")
      ),
      "data_testid": (
        button.get("data_testid")
        or button.get("data-testid")
        or button.get("data_test_id")
        or html_attributes.get("data-testid")
        or html_attributes.get("data-test-id")
      ),
      "form_context": structure.get("parent_form") if isinstance(structure.get("parent_form"), dict) else {},
      "dialog_context": _dialog_context(button, structure, nearest_heading),
      "relationship_types": sorted(
        {
          str(relationship.get("type") or "")
          for relationship in relationships
          if str(relationship.get("type") or "")
        }
      ),
      **transition_context,
    },
  }


def _matched_outgoing_transition_context(
  run: RunArtifacts,
  state: RunState,
  button: dict[str, Any],
  html_attributes: dict[str, str],
) -> dict[str, object]:
  outgoing = [
    edge
    for edge in _saved_transitions(run)
    if str(edge.get("from") or "") == state.state_id
    and isinstance(edge.get("action"), dict)
    and isinstance(edge["action"].get("primary_trigger"), dict)
  ]
  if not outgoing:
    return {}

  candidate_identifiers = {
    "data_testid": _button_data_testid(button, html_attributes),
    "selector": str(button.get("selector") or ""),
    "dom_path": str(button.get("dom_path") or ""),
  }
  for identifier in ("data_testid", "selector", "dom_path"):
    value = candidate_identifiers[identifier]
    if not value or not _button_identifier_is_unique(state, identifier, value):
      continue
    matches = [
      edge
      for edge in outgoing
      if str(_primary_trigger(edge).get(identifier) or "") == value
    ]
    if len(matches) > 1:
      return {}
    if len(matches) != 1:
      continue
    edge = matches[0]
    matched: dict[str, object] = {
      "matched_outgoing_transition": {
        "from_state": state.state_id,
        "to_state": str(edge.get("to") or ""),
        "match_basis": [identifier],
        "trigger": _compact_primary_trigger(_primary_trigger(edge)),
      }
    }
    result_state = _state_by_id(run, str(edge.get("to") or ""))
    if result_state is not None:
      matched["result_state_context"] = _result_state_context(result_state)
    return matched
  return {}


def _saved_transitions(run: RunArtifacts) -> list[dict[str, Any]]:
  transitions = run.transitions
  if not transitions and isinstance(run.graph.get("edges"), list):
    transitions = run.graph["edges"]
  return [edge for edge in transitions if isinstance(edge, dict)]


def _primary_trigger(edge: dict[str, Any]) -> dict[str, Any]:
  action = edge.get("action")
  if not isinstance(action, dict):
    return {}
  trigger = action.get("primary_trigger")
  return trigger if isinstance(trigger, dict) else {}


def _button_identifier_is_unique(state: RunState, identifier: str, value: str) -> bool:
  matches = 0
  for saved_button in evidence_items(state, "buttons"):
    saved_attributes = _saved_html_attributes(saved_button.get("raw_html"))
    saved_value = (
      _button_data_testid(saved_button, saved_attributes)
      if identifier == "data_testid"
      else str(saved_button.get(identifier) or "")
    )
    if saved_value == value:
      matches += 1
  return matches == 1


def _button_data_testid(button: dict[str, Any], html_attributes: dict[str, str]) -> str:
  return str(
    button.get("data_testid")
    or button.get("data-testid")
    or button.get("data_test_id")
    or html_attributes.get("data-testid")
    or html_attributes.get("data-test-id")
    or ""
  )


def _compact_primary_trigger(trigger: dict[str, Any]) -> dict[str, object]:
  return {
    key: trigger[key]
    for key in MATCHED_TRIGGER_KEYS
    if key in trigger and trigger[key] not in (None, "", [], {})
  }


def _state_by_id(run: RunArtifacts, state_id: str) -> RunState | None:
  return next((item for item in run.states if item.state_id == state_id), None)


def _result_state_context(state: RunState) -> dict[str, object]:
  page = state.accessibility_context.get("page")
  page = page if isinstance(page, dict) else {}
  headings = _unique_texts(evidence_items(state, "headings"), limit=8)
  status_texts = _unique_texts(
    [
      item
      for item in evidence_items(state, "visual_cues")
      if str(item.get("role") or "").lower() in {"alert", "status"}
      or bool(item.get("aria_live"))
    ],
    limit=6,
  )
  landmarks = _unique_texts(evidence_items(state, "landmarks"), limit=6)
  return {
    "state_id": state.state_id,
    "route": state.metadata.get("route") or page.get("route"),
    "title": state.metadata.get("title") or page.get("title"),
    "headings": headings,
    "status_texts": status_texts,
    "body_text_excerpt": truncate_text(page.get("body_text_sample")),
    "landmarks": landmarks,
  }


def _unique_texts(items: list[dict[str, Any]], *, limit: int) -> list[str]:
  texts: list[str] = []
  for item in items:
    text = first_present_text(item, ("text", "accessible_name", "aria_label", "title"))
    text = truncate_text(text, max_length=160)
    if text and text not in texts:
      texts.append(text)
    if len(texts) >= limit:
      break
  return texts


def _relationship_text(
  state: RunState,
  relationships: list[dict[str, object]],
  *,
  button_id: str,
  relationship_types: set[str],
) -> str:
  referenced_by_id = {
    str(item.get("element_id") or ""): item
    for item in evidence_items(state, "referenced_elements")
    if str(item.get("element_id") or "")
  }
  texts: list[str] = []
  for relationship in relationships:
    if str(relationship.get("type") or "") not in relationship_types:
      continue
    if str(relationship.get("to_element_id") or "") != button_id:
      continue
    source = referenced_by_id.get(str(relationship.get("from_element_id") or ""))
    if not source:
      continue
    text = first_present_text(source, ("text", "accessible_name", "aria_label", "title"))
    if text and text not in texts:
      texts.append(text)
  return truncate_text(" ".join(texts))


def _compact_structure_ref(value: dict[str, Any]) -> dict[str, object]:
  if not value:
    return {}
  return {
    "element_id": str(value.get("element_id") or ""),
    "selector": str(value.get("selector") or ""),
    "tag": str(value.get("tag") or ""),
    "role": value.get("role"),
    "text": truncate_text(value.get("text")),
    "accessible_name": truncate_text(value.get("accessible_name")),
  }


def _dialog_context(
  button: dict[str, Any],
  structure: dict[str, Any],
  nearest_heading: dict[str, Any],
) -> dict[str, object]:
  xpath = str(button.get("xpath") or "")
  ancestor_roles = structure.get("ancestor_roles") if isinstance(structure.get("ancestor_roles"), list) else []
  if "/dialog[" not in xpath.lower() and not any(
    str(role).lower() in {"dialog", "alertdialog"}
    for role in ancestor_roles
  ):
    return {}
  return {
    "scope_type": "dialog",
    "scope_detection": "native_dialog_xpath" if "/dialog[" in xpath.lower() else "ancestor_role",
    "heading": _compact_structure_ref(nearest_heading),
  }


def _saved_html_attributes(raw_html: object) -> dict[str, str]:
  html = str(raw_html or "")
  if not html:
    return {}
  parser = _FirstElementAttributeParser()
  try:
    parser.feed(html)
  except (TypeError, ValueError):
    return {}
  return parser.attributes


class _FirstElementAttributeParser(HTMLParser):
  def __init__(self) -> None:
    super().__init__(convert_charrefs=True)
    self.attributes: dict[str, str] = {}
    self._captured = False

  def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
    if self._captured:
      return
    self._captured = True
    self.attributes = {
      str(name): str(value or "")
      for name, value in attrs
    }

  def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
    self.handle_starttag(tag, attrs)
