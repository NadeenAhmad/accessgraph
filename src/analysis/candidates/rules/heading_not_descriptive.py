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
from ..models import RunArtifacts, RunState, sanitize_action
from ..payload import build_candidate_payload

CANDIDATE_TYPE = "heading-not-descriptive"
HEADING_OUTLINE_SCHEMA_VERSION = "heading_outline_v1"
HEADING_SCOPE_SCHEMA_VERSION = "heading_scope_v1"
HEADING_SCOPED_CONTENT_SCHEMA_VERSION = "heading_scoped_content_v1"
TRANSITION_HEADING_CONTEXT_SCHEMA_VERSION = "transition_heading_context_v1"
HEADING_SCOPE_TEXT_LIMIT = 500
HEADING_SCOPED_CONTENT_TEXT_LIMIT = 700
HEADING_SCOPE_ITEM_LIMIT = 8
HEADING_SCOPE_ITEM_TEXT_LIMIT = 160
TRANSITION_HEADING_SCOPE_TEXT_LIMIT = 240
TRANSITION_HEADING_OUTLINE_LIMIT = 3


def build_heading_not_descriptive_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  headings = evidence_items(state, "headings")
  outline_headings = _outline_headings(headings)
  states_by_id = {run_state.state_id: run_state for run_state in run.states}
  for heading in headings:
    if not is_visible(heading):
      continue
    text = truncate_text(heading.get("text"))
    if not text:
      continue
    if not _has_level_or_tag(heading):
      continue
    if not _has_context(state, heading, graph_context):
      continue
    heading_ref = element_ref("headings", heading)
    snippet = dom_snippet(heading)
    heading_context = _sanitized_heading_context(heading)
    heading_structure = _sanitized_heading_structure(heading)
    supporting: dict[str, object] = {
      "page": _compact_page(state),
      "context": heading_context,
      "structure": heading_structure,
      "heading_outline": _build_heading_outline(outline_headings, heading),
    }
    heading_scope = _compact_heading_scope(heading)
    if heading_scope:
      supporting["heading_scope"] = heading_scope
    heading_scoped_content = _build_heading_scoped_content(state, heading)
    if heading_scoped_content:
      supporting["heading_scoped_content"] = heading_scoped_content
    candidate_graph_context = dict(graph_context)
    transition_heading_context = _build_transition_heading_context(
      states_by_id=states_by_id,
      state=state,
      graph_context=graph_context,
      current_heading=heading,
      current_outline_headings=outline_headings,
    )
    if transition_heading_context:
      candidate_graph_context["transition_heading_context"] = transition_heading_context
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        primary_element_ref=heading_ref,
        element_refs=[heading_ref],
        selection_reason=["heading_with_section_context_evidence"],
        required_context=["heading purpose", "page context", "section context"],
        evidence={
          "primary": {"heading": _compact_heading(heading)},
          "supporting": supporting,
          "bounding_boxes": [bounding_box_ref(heading)],
          "dom_snippets": [snippet] if snippet else [],
        },
        graph_context=candidate_graph_context,
      )
    )
  return records


def _has_level_or_tag(heading: dict[str, Any]) -> bool:
  return bool(heading.get("level") or str(heading.get("tag") or "").lower() in {"h1", "h2", "h3", "h4", "h5", "h6"})


def _has_context(state: RunState, heading: dict[str, Any], graph_context: dict[str, object]) -> bool:
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  heading_context = heading.get("context") if isinstance(heading.get("context"), dict) else {}
  return bool(
    first_present_text(page, ("title", "body_text_sample", "url"))
    or first_present_text(heading_context, ("nearby_text", "parent_text", "section_heading"))
    or graph_context.get("transition_path")
  )


def _outline_headings(headings: list[dict[str, Any]]) -> list[dict[str, Any]]:
  return [
    heading
    for heading in headings
    if is_visible(heading) and truncate_text(heading.get("text")) and _has_level_or_tag(heading)
  ]


def _build_heading_outline(headings: list[dict[str, Any]], current_heading: dict[str, Any]) -> dict[str, object]:
  current_index = _heading_index(headings, current_heading)
  normalized_text = _normalized_heading_text(current_heading.get("text"))
  duplicate_count = sum(
    1
    for heading in headings
    if normalized_text and _normalized_heading_text(heading.get("text")) == normalized_text
  )
  window: list[dict[str, object]] = []
  if current_index > 0:
    window.append(_compact_outline_heading(headings[current_index - 1], position="previous"))
  if current_index >= 0:
    window.append(_compact_outline_heading(headings[current_index], position="current"))
  if current_index >= 0 and current_index + 1 < len(headings):
    window.append(_compact_outline_heading(headings[current_index + 1], position="next"))
  return {
    "schema_version": HEADING_OUTLINE_SCHEMA_VERSION,
    "state_heading_count": len(headings),
    "normalized_text_duplicate_count": duplicate_count,
    "window": window,
  }


def _heading_index(headings: list[dict[str, Any]], current_heading: dict[str, Any]) -> int:
  current_element_id = str(current_heading.get("element_id") or "")
  current_selector = str(current_heading.get("selector") or "")
  current_xpath = str(current_heading.get("xpath") or "")
  for index, heading in enumerate(headings):
    if heading is current_heading:
      return index
    if current_element_id:
      if str(heading.get("element_id") or "") == current_element_id:
        return index
      continue
    if current_selector:
      if str(heading.get("selector") or "") == current_selector:
        return index
      continue
    if current_xpath and str(heading.get("xpath") or "") == current_xpath:
      return index
  return -1


def _compact_outline_heading(heading: dict[str, Any], *, position: str) -> dict[str, object]:
  item: dict[str, object] = {
    "position": position,
    "element_id": str(heading.get("element_id") or ""),
    "level": heading.get("level"),
    "tag": str(heading.get("tag") or ""),
    "text": truncate_text(heading.get("text")),
  }
  accessible_name = truncate_text(heading.get("accessible_name"))
  if accessible_name:
    item["accessible_name"] = accessible_name
  return item


def _normalized_heading_text(value: object) -> str:
  return " ".join(str(value or "").casefold().split())


def _sanitized_heading_context(heading: dict[str, Any]) -> dict[str, object]:
  context = heading.get("context") if isinstance(heading.get("context"), dict) else {}
  sanitized = dict(context)
  if _looks_like_previous_card_heading_context(heading):
    sanitized.pop("section_heading", None)
  return sanitized


def _sanitized_heading_structure(heading: dict[str, Any]) -> dict[str, object]:
  structure = heading.get("structure") if isinstance(heading.get("structure"), dict) else {}
  sanitized = dict(structure)
  if _looks_like_previous_card_heading_context(heading):
    nearest_heading = sanitized.get("nearest_heading")
    if isinstance(nearest_heading, dict):
      sanitized["nearest_heading"] = {}
  return sanitized


def _looks_like_previous_card_heading_context(heading: dict[str, Any]) -> bool:
  context = heading.get("context") if isinstance(heading.get("context"), dict) else {}
  structure = heading.get("structure") if isinstance(heading.get("structure"), dict) else {}
  nearest = structure.get("nearest_heading") if isinstance(structure.get("nearest_heading"), dict) else {}

  if str(structure.get("parent_tag") or "").lower() != "a":
    return False

  target_text = _normalized_heading_text(heading.get("text"))
  section_heading = _normalized_heading_text(context.get("section_heading"))
  nearest_text = _normalized_heading_text(nearest.get("text"))
  parent_text = _normalized_heading_text(context.get("parent_text"))

  if not target_text or not section_heading or not nearest_text or not parent_text:
    return False
  if section_heading != nearest_text or section_heading == target_text:
    return False
  return target_text in parent_text and section_heading not in parent_text


def _build_transition_heading_context(
  *,
  states_by_id: dict[str, RunState],
  state: RunState,
  graph_context: dict[str, object],
  current_heading: dict[str, Any],
  current_outline_headings: list[dict[str, Any]],
) -> dict[str, object] | None:
  previous_state_id = _previous_state_id(state, graph_context)
  if not previous_state_id:
    return None
  previous_state = states_by_id.get(previous_state_id)
  if not previous_state:
    return None
  previous_outline_headings = _outline_headings(evidence_items(previous_state, "headings"))
  if not previous_outline_headings:
    return None

  current_index = _heading_index(current_outline_headings, current_heading)
  previous_heading, matching_method = _match_previous_heading(
    previous_outline_headings,
    current_heading,
    current_index,
  )

  transition_context: dict[str, object] = {
    "schema_version": TRANSITION_HEADING_CONTEXT_SCHEMA_VERSION,
    "purpose": "neutral_before_after_visible_heading_context",
    "incoming_action": _incoming_action_for_transition(state, graph_context),
    "from_state_id": previous_state_id,
    "to_state_id": state.state_id,
    "matching_method": matching_method,
    "current_heading": _compact_transition_heading(current_heading),
    "current_heading_outline": _transition_outline_window(current_outline_headings, current_heading),
  }
  if previous_heading:
    transition_context["previous_heading"] = _compact_transition_heading(previous_heading)
    transition_context["previous_heading_outline"] = _transition_outline_window(
      previous_outline_headings,
      previous_heading,
    )
  else:
    transition_context["previous_heading"] = None
    transition_context["previous_heading_outline"] = _transition_outline_prefix(previous_outline_headings)
  return transition_context


def _previous_state_id(state: RunState, graph_context: dict[str, object]) -> str:
  parent = str(state.metadata.get("parent_state") or "")
  if parent:
    return parent
  state_context = state.accessibility_context.get("state_context")
  if isinstance(state_context, dict):
    parent = str(state_context.get("parent_state") or "")
    if parent:
      return parent
  transition_path = graph_context.get("transition_path")
  if isinstance(transition_path, list) and transition_path:
    last_transition = transition_path[-1]
    if isinstance(last_transition, dict):
      return str(last_transition.get("from") or "")
  return ""


def _incoming_action_for_transition(state: RunState, graph_context: dict[str, object]) -> dict[str, object]:
  graph_action = graph_context.get("incoming_action")
  if isinstance(graph_action, dict) and graph_action:
    return sanitize_action(graph_action)
  state_context = state.accessibility_context.get("state_context")
  context_action = state_context.get("action_from_parent") if isinstance(state_context, dict) else None
  return sanitize_action(state.metadata.get("action_from_parent") or context_action)


def _match_previous_heading(
  previous_headings: list[dict[str, Any]],
  current_heading: dict[str, Any],
  current_index: int,
) -> tuple[dict[str, Any] | None, str]:
  selector = str(current_heading.get("selector") or "")
  if selector:
    matched = _first_heading_with(previous_headings, "selector", selector)
    if matched:
      return matched, "same_selector"

  xpath = str(current_heading.get("xpath") or "")
  if xpath:
    matched = _first_heading_with(previous_headings, "xpath", xpath)
    if matched:
      return matched, "same_xpath"

  if 0 <= current_index < len(previous_headings):
    previous_at_position = previous_headings[current_index]
    if _heading_level(previous_at_position) == _heading_level(current_heading):
      return previous_at_position, "same_level_and_outline_position"

  normalized_text = _normalized_heading_text(current_heading.get("text"))
  if normalized_text:
    for previous_heading in previous_headings:
      if _normalized_heading_text(previous_heading.get("text")) == normalized_text:
        return previous_heading, "same_normalized_text"

  return None, "previous_outline_only"


def _first_heading_with(headings: list[dict[str, Any]], key: str, value: str) -> dict[str, Any] | None:
  for heading in headings:
    if str(heading.get(key) or "") == value:
      return heading
  return None


def _heading_level(heading: dict[str, Any]) -> int | None:
  raw_level = heading.get("level")
  if isinstance(raw_level, int):
    return raw_level
  try:
    return int(str(raw_level))
  except (TypeError, ValueError):
    return None


def _compact_transition_heading(heading: dict[str, Any]) -> dict[str, object]:
  compact: dict[str, object] = {
    "visible_text": truncate_text(heading.get("text")),
    "level": heading.get("level"),
    "tag": str(heading.get("tag") or ""),
    "selector": str(heading.get("selector") or ""),
  }
  xpath = truncate_text(heading.get("xpath"), max_length=HEADING_SCOPE_ITEM_TEXT_LIMIT)
  if xpath and not compact["selector"]:
    compact["xpath"] = xpath
  heading_scope_excerpt = _transition_heading_scope_excerpt(heading)
  if heading_scope_excerpt:
    compact["heading_scope_excerpt"] = heading_scope_excerpt
  return compact


def _transition_heading_scope_excerpt(heading: dict[str, Any]) -> str:
  raw_scope = heading.get("heading_scope")
  if not isinstance(raw_scope, dict):
    return ""
  excerpt, _ = _truncated_text_with_flag(
    raw_scope.get("text_excerpt") or raw_scope.get("text"),
    max_length=TRANSITION_HEADING_SCOPE_TEXT_LIMIT,
  )
  return excerpt


def _transition_outline_window(
  headings: list[dict[str, Any]],
  current_heading: dict[str, Any],
) -> list[dict[str, object]]:
  current_index = _heading_index(headings, current_heading)
  if current_index < 0:
    return _transition_outline_prefix(headings)
  window: list[dict[str, object]] = []
  if current_index > 0:
    window.append(_compact_transition_outline_heading(headings[current_index - 1], position="previous"))
  window.append(_compact_transition_outline_heading(headings[current_index], position="current"))
  if current_index + 1 < len(headings):
    window.append(_compact_transition_outline_heading(headings[current_index + 1], position="next"))
  return window


def _transition_outline_prefix(headings: list[dict[str, Any]]) -> list[dict[str, object]]:
  return [
    _compact_transition_outline_heading(heading, position="previous_state")
    for heading in headings[:TRANSITION_HEADING_OUTLINE_LIMIT]
  ]


def _compact_transition_outline_heading(heading: dict[str, Any], *, position: str) -> dict[str, object]:
  return {
    "position": position,
    "visible_text": truncate_text(heading.get("text")),
    "level": heading.get("level"),
    "tag": str(heading.get("tag") or ""),
    "selector": str(heading.get("selector") or ""),
  }


def _compact_heading_scope(heading: dict[str, Any]) -> dict[str, object] | None:
  raw_scope = heading.get("heading_scope")
  if not isinstance(raw_scope, dict):
    return None

  text_excerpt, text_truncated = _truncated_text_with_flag(raw_scope.get("text_excerpt") or raw_scope.get("text"))
  compact: dict[str, object] = {
    "schema_version": str(raw_scope.get("schema_version") or HEADING_SCOPE_SCHEMA_VERSION),
    "strategy": str(raw_scope.get("strategy") or "provided_by_accessibility_context"),
    "text_excerpt": text_excerpt,
    "truncated": bool(raw_scope.get("truncated")) or text_truncated,
  }

  content_counts = raw_scope.get("content_counts")
  if isinstance(content_counts, dict):
    compact["content_counts"] = {
      str(key): value
      for key, value in content_counts.items()
      if isinstance(value, (int, float)) and not isinstance(value, bool)
    }

  sampled_items = raw_scope.get("sampled_items")
  if isinstance(sampled_items, list):
    compact_items = []
    for item in sampled_items[:HEADING_SCOPE_ITEM_LIMIT]:
      if not isinstance(item, dict):
        continue
      compact_item = _compact_heading_scope_item(item)
      if compact_item:
        compact_items.append(compact_item)
    if compact_items:
      compact["sampled_items"] = compact_items

  return compact


def _compact_heading_scope_item(item: dict[str, Any]) -> dict[str, object]:
  compact: dict[str, object] = {}
  for key in ("kind", "element_id", "tag", "role", "selector"):
    value = truncate_text(item.get(key), max_length=HEADING_SCOPE_ITEM_TEXT_LIMIT)
    if value:
      compact[key] = value
  text = truncate_text(item.get("text"), max_length=HEADING_SCOPE_ITEM_TEXT_LIMIT)
  if text:
    compact["text"] = text
  return compact


def _build_heading_scoped_content(state: RunState, heading: dict[str, Any]) -> dict[str, object] | None:
  heading_id = str(heading.get("element_id") or "")
  if not heading_id:
    return None

  landmark, source = _labelledby_landmark_for_heading(state, heading_id)
  if not landmark:
    landmark = _nearest_landmark_for_heading(state, heading)
    source = "nearest_landmark_text_sample" if landmark else ""
  if not landmark:
    return None

  text = landmark.get("text_sample") or landmark.get("text")
  text_excerpt, truncated = _truncated_text_with_flag(
    text,
    max_length=HEADING_SCOPED_CONTENT_TEXT_LIMIT,
  )
  if not text_excerpt:
    return None

  return {
    "schema_version": HEADING_SCOPED_CONTENT_SCHEMA_VERSION,
    "source": source,
    "source_element_ref": _scoped_content_source_ref(landmark),
    "text_excerpt": text_excerpt,
    "truncated": truncated,
  }


def _labelledby_landmark_for_heading(
  state: RunState,
  heading_id: str,
) -> tuple[dict[str, Any] | None, str]:
  landmarks_by_id = _elements_by_id(evidence_items(state, "landmarks"))
  for relationship in evidence_items(state, "relationships"):
    if not isinstance(relationship, dict):
      continue
    if str(relationship.get("type") or "") != "labelledby":
      continue
    if str(relationship.get("from_element_id") or "") != heading_id:
      continue
    landmark = landmarks_by_id.get(str(relationship.get("to_element_id") or ""))
    if landmark:
      return landmark, "labelledby_landmark_text_sample"
  return None, ""


def _nearest_landmark_for_heading(state: RunState, heading: dict[str, Any]) -> dict[str, Any] | None:
  structure = heading.get("structure") if isinstance(heading.get("structure"), dict) else {}
  nearest_landmark = structure.get("nearest_landmark") if isinstance(structure.get("nearest_landmark"), dict) else {}
  landmark_id = str(nearest_landmark.get("element_id") or "")
  if not landmark_id:
    return None
  return _elements_by_id(evidence_items(state, "landmarks")).get(landmark_id)


def _elements_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
  return {
    str(item.get("element_id") or ""): item
    for item in items
    if isinstance(item, dict) and str(item.get("element_id") or "")
  }


def _scoped_content_source_ref(landmark: dict[str, Any]) -> dict[str, object]:
  ref: dict[str, object] = {
    "bucket": "landmarks",
    "element_id": str(landmark.get("element_id") or ""),
    "selector": str(landmark.get("selector") or ""),
    "tag": str(landmark.get("tag") or ""),
  }
  role = truncate_text(landmark.get("role"), max_length=HEADING_SCOPE_ITEM_TEXT_LIMIT)
  if role:
    ref["role"] = role
  return ref


def _truncated_text_with_flag(value: object, *, max_length: int = HEADING_SCOPE_TEXT_LIMIT) -> tuple[str, bool]:
  normalized = " ".join(str(value or "").split())
  if len(normalized) <= max_length:
    return normalized, False
  return normalized[:max_length], True


def _compact_heading(heading: dict[str, Any]) -> dict[str, object]:
  return {
    "element_id": str(heading.get("element_id") or ""),
    "tag": str(heading.get("tag") or ""),
    "role": heading.get("role"),
    "selector": str(heading.get("selector") or ""),
    "text": truncate_text(heading.get("text")),
    "level": heading.get("level"),
    "accessible_name": heading.get("accessible_name"),
  }


def _compact_page(state: RunState) -> dict[str, object]:
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  return {
    "url": str(page.get("url") or state.metadata.get("url") or ""),
    "title": truncate_text(page.get("title") or state.metadata.get("title")),
    "body_text_sample": truncate_text(page.get("body_text_sample")),
  }
