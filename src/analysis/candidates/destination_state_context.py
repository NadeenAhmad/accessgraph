"""Offline destination-state evidence for link and button candidates."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from .evidence_helpers import evidence_items, first_present_text, is_visible, truncate_text
from .models import RunArtifacts, RunState
from .payload import artifact_refs

DESTINATION_STATE_CONTEXT_SCHEMA_VERSION = "destination_state_context_v1"
DEFAULT_DESTINATION_IDENTIFIER_ORDER = ("element_id", "data_testid", "identity", "selector", "dom_path")
LINK_DESTINATION_IDENTIFIER_ORDER = (*DEFAULT_DESTINATION_IDENTIFIER_ORDER, "href")
MAX_DESTINATION_HEADINGS = 5
MAX_DESTINATION_LANDMARKS = 5
MAX_DESTINATION_STATUS_TEXTS = 5
MAX_DESTINATION_TEXT_EXCERPT = 280
MAX_DESTINATION_ACTION_TEXT = 160
MAX_DESTINATION_ELEMENTS = 40
DESTINATION_ELEMENT_BUCKETS = (
  "visual_cues",
  "form_controls",
  "buttons",
  "links",
  "tables",
  "images",
  "videos",
  "forms",
  "headings",
  "landmarks",
  "language_samples",
  "referenced_elements",
)
COMPACT_TRIGGER_KEYS = (
  "element_id",
  "type",
  "selector",
  "identity",
  "data_testid",
  "dom_path",
  "href",
  "target_url",
  "text",
  "accessible_name",
  "button_type",
  "input_type",
  "role",
  "tag_name",
)


def build_destination_state_context(
  run: RunArtifacts,
  source_state: RunState,
  element: dict[str, Any],
  *,
  bucket: str,
  identifier_order: tuple[str, ...] = DEFAULT_DESTINATION_IDENTIFIER_ORDER,
) -> dict[str, object]:
  """Return compact target-state evidence for a matched outgoing transition.

  The match is intentionally conservative: the candidate element must have a
  stable identifier that is unique within the source-state bucket, and that same
  identifier must appear in the saved transition action or primary trigger.
  Visible text alone is never used to associate a candidate with a transition.
  """

  outgoing = _saved_outgoing_transitions(run, source_state.state_id)
  if not outgoing:
    return {}

  html_attributes = saved_html_attributes(element.get("raw_html"))
  for identifier in identifier_order:
    value = _element_identifier_value(element, html_attributes, identifier)
    if not value or not _identifier_is_unique(source_state, bucket, identifier, value):
      continue

    matches = [
      edge
      for edge in outgoing
      if _trigger_identifier_value(_trigger_for_edge(edge), identifier) == value
    ]
    if not matches:
      continue

    destinations = _unique_captured_destinations(run, matches)
    if not destinations:
      continue

    return {
      "schema_version": DESTINATION_STATE_CONTEXT_SCHEMA_VERSION,
      "source_state_id": source_state.state_id,
      "match_basis": [identifier],
      "match_count": len(destinations),
      "destinations": [
        {**_destination_summary(run, edge, target_state),
         "form_value_changes": _form_value_changes(source_state, target_state)}
        for edge, target_state in destinations
      ],
    }

  return {}


def saved_html_attributes(raw_html: object) -> dict[str, str]:
  html = str(raw_html or "")
  if not html:
    return {}
  parser = _FirstElementAttributeParser()
  try:
    parser.feed(html)
  except (TypeError, ValueError):
    return {}
  return parser.attributes


def _form_value_changes(source: RunState, target: RunState) -> dict[str, list[dict[str, str]]]:
  """W4A round 4: fields whose value changed with the action, and fields that kept a non-empty value, matched by
  XPath (the judge checks a control's result against them, e.g. 'Reset filters' that leaves a filter set)."""
  def values(state: RunState) -> dict[str, tuple[str, str]]:
    out = {}
    for control in evidence_items(state, "form_controls"):
      xpath, value = str(control.get("xpath") or ""), control.get("current_value")
      if xpath and value is not None:
        label = truncate_text(control.get("label") or control.get("wrapping_label") or control.get("accessible_name")
                              or control.get("name") or control.get("placeholder"), max_length=80)
        out[xpath] = (label, truncate_text(value, max_length=120))
    return out
  before, after = values(source), values(target)
  changed, kept = [], []
  for xpath, (label, value) in after.items():
    if xpath not in before:
      continue
    if before[xpath][1] != value:
      changed.append({"field": label, "before": before[xpath][1], "after": value})
    elif value and value != "not checked":
      kept.append({"field": label, "value": value})
  return {"changed": changed[:12], "kept_non_empty": kept[:12]}


def _saved_outgoing_transitions(run: RunArtifacts, state_id: str) -> list[dict[str, Any]]:
  return [
    edge
    for edge in _saved_transitions(run)
    if str(edge.get("from") or "") == state_id
    and isinstance(edge.get("action"), dict)
    and _trigger_for_edge(edge)
  ]


def _saved_transitions(run: RunArtifacts) -> list[dict[str, Any]]:
  transitions = run.transitions
  if not transitions and isinstance(run.graph.get("edges"), list):
    transitions = run.graph["edges"]
  return [edge for edge in transitions if isinstance(edge, dict)]


def _trigger_for_edge(edge: dict[str, Any]) -> dict[str, Any]:
  action = edge.get("action")
  if not isinstance(action, dict):
    return {}
  primary_trigger = action.get("primary_trigger")
  if isinstance(primary_trigger, dict) and primary_trigger:
    return primary_trigger
  return action


def _element_identifier_value(
  element: dict[str, Any],
  html_attributes: dict[str, str],
  identifier: str,
) -> str:
  if identifier == "element_id":
    return str(element.get("element_id") or "")
  if identifier == "data_testid":
    return _data_testid(element, html_attributes)
  if identifier == "href":
    return str(element.get("href") or html_attributes.get("href") or "")
  if identifier == "selector":
    return str(element.get("selector") or "")
  if identifier == "dom_path":
    return str(element.get("dom_path") or "")
  return str(element.get(identifier) or "")


def _trigger_identifier_value(trigger: dict[str, Any], identifier: str) -> str:
  if identifier == "data_testid":
    return str(
      trigger.get("data_testid")
      or trigger.get("data-testid")
      or trigger.get("data_test_id")
      or ""
    )
  return str(trigger.get(identifier) or "")


def _identifier_is_unique(
  state: RunState,
  bucket: str,
  identifier: str,
  value: str,
) -> bool:
  matches = 0
  for saved_element in evidence_items(state, bucket):
    saved_attributes = saved_html_attributes(saved_element.get("raw_html"))
    if _element_identifier_value(saved_element, saved_attributes, identifier) == value:
      matches += 1
  return matches == 1


def _data_testid(element: dict[str, Any], html_attributes: dict[str, str]) -> str:
  return str(
    element.get("data_testid")
    or element.get("data-testid")
    or element.get("data_test_id")
    or html_attributes.get("data-testid")
    or html_attributes.get("data-test-id")
    or ""
  )


def _unique_captured_destinations(
  run: RunArtifacts,
  matches: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], RunState]]:
  by_target_id: dict[str, tuple[dict[str, Any], RunState]] = {}
  for edge in matches:
    target_state_id = str(edge.get("to") or edge.get("target_state_id") or "")
    target_state = _state_by_id(run, target_state_id)
    if target_state is None:
      continue
    by_target_id.setdefault(target_state.state_id, (edge, target_state))
  return [by_target_id[target_state_id] for target_state_id in sorted(by_target_id)]


def _state_by_id(run: RunArtifacts, state_id: str) -> RunState | None:
  return next((item for item in run.states if item.state_id == state_id), None)


def _destination_summary(
  run: RunArtifacts,
  edge: dict[str, Any],
  target_state: RunState,
) -> dict[str, object]:
  trigger = _trigger_for_edge(edge)
  action = edge.get("action") if isinstance(edge.get("action"), dict) else {}
  page = target_state.accessibility_context.get("page")
  page = page if isinstance(page, dict) else {}
  return {
    "target_state_id": target_state.state_id,
    "target_url": str(page.get("url") or target_state.metadata.get("url") or ""),
    "target_route": str(target_state.metadata.get("route") or page.get("route") or ""),
    "target_title": str(page.get("title") or target_state.metadata.get("title") or ""),
    "action_type": str(trigger.get("type") or action.get("type") or ""),
    "action_text": truncate_text(
      trigger.get("text") or trigger.get("accessible_name") or action.get("text"),
      max_length=MAX_DESTINATION_ACTION_TEXT,
    ),
    "trigger": _compact_trigger(trigger),
    "target_primary_headings": _compact_headings(target_state),
    "target_landmarks": _compact_landmarks(target_state),
    "target_elements": compact_destination_elements(target_state),
    "target_status_texts": _unique_texts(
      [
        item
        for item in evidence_items(target_state, "visual_cues")
        if str(item.get("role") or "").lower() in {"alert", "status"}
        or bool(item.get("aria_live"))
      ],
      limit=MAX_DESTINATION_STATUS_TEXTS,
    ),
    "target_visible_text_excerpt": truncate_text(
      page.get("body_text_sample"),
      max_length=MAX_DESTINATION_TEXT_EXCERPT,
    ),
    "artifact_refs": artifact_refs(run.run_dir, target_state),
  }


def _compact_trigger(trigger: dict[str, Any]) -> dict[str, object]:
  return {
    key: trigger[key]
    for key in COMPACT_TRIGGER_KEYS
    if key in trigger and trigger[key] not in (None, "", [], {})
  }


def _compact_headings(state: RunState) -> list[dict[str, object]]:
  compact: list[dict[str, object]] = []
  for heading in evidence_items(state, "headings"):
    if not is_visible(heading):
      continue
    compact.append(
      {
        "element_id": str(heading.get("element_id") or ""),
        "level": heading.get("level"),
        "tag": str(heading.get("tag") or ""),
        "text": truncate_text(heading.get("text"), max_length=160),
        "accessible_name": truncate_text(heading.get("accessible_name"), max_length=160),
      }
    )
    if len(compact) >= MAX_DESTINATION_HEADINGS:
      break
  return compact


def _compact_landmarks(state: RunState) -> list[dict[str, object]]:
  compact: list[dict[str, object]] = []
  for landmark in evidence_items(state, "landmarks"):
    if not is_visible(landmark):
      continue
    compact.append(
      {
        "element_id": str(landmark.get("element_id") or ""),
        "tag": str(landmark.get("tag") or ""),
        "role": landmark.get("role"),
        "text": truncate_text(landmark.get("text"), max_length=160),
        "accessible_name": truncate_text(landmark.get("accessible_name"), max_length=160),
        "selector": str(landmark.get("selector") or ""),
      }
    )
    if len(compact) >= MAX_DESTINATION_LANDMARKS:
      break
  return compact


def compact_destination_elements(
  state: RunState,
  *,
  limit: int = MAX_DESTINATION_ELEMENTS,
) -> list[dict[str, object]]:
  """Return a bounded, neutral view of visible destination-state elements."""

  compact: list[dict[str, object]] = []
  for bucket in DESTINATION_ELEMENT_BUCKETS:
    for element in evidence_items(state, bucket):
      if not is_visible(element):
        continue
      observation = {
        "bucket": bucket,
        "element_id": str(element.get("element_id") or ""),
        "kind": str(element.get("kind") or ""),
        "tag": str(element.get("tag") or ""),
        "role": element.get("role"),
        "selector": str(element.get("selector") or ""),
        "text": truncate_text(element.get("text"), max_length=160),
        "accessible_name": truncate_text(
          element.get("accessible_name"),
          max_length=160,
        ),
      }
      compact.append(
        {
          key: value
          for key, value in observation.items()
          if value not in (None, "")
        }
      )
      if len(compact) >= limit:
        return compact
  return compact


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
