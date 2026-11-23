from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.analysis.candidates.taxonomy import SUPPORTED_CANDIDATE_TYPES

from .models import (
  CONTEXT_MODE_ADAPTIVE,
  CONTEXT_MODE_ADAPTIVE_V2,
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_HISTORY,
  CONTEXT_MODE_ISOLATED,
  CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  CONTEXT_MODES,
)

ADAPTIVE_CONTEXT_POLICY_VERSION = "adaptive_v1_4"
ADAPTIVE_V2_CONTEXT_POLICY_VERSION = "adaptive_v2"
# The seven types whose violations can depend on a transition (backward: title, heading, landmark, form
# label; forward: button, link, widget). adaptive_v2 judges them with history, the others in isolation.
TRANSITION_CAPABLE_TYPES = frozenset({
  "page-title-not-descriptive", "heading-not-descriptive", "landmark-purpose-mismatch", "form-label-mismatch",
  "button-label-mismatch", "link-text-mismatch", "widget-label-purpose-mismatch",
})
GRAPH_CONTEXT_OMITTED_EMPTY = "empty_graph_context"
_GRAPH_CONTEXT_IGNORED_KEYS = frozenset(
  {
    "depth",
    "incoming_action",
    "related_state_refs",
    "transition_path",
    "transition_path_limit",
    "transition_path_truncated",
  }
)
_GRAPH_CONTEXT_METADATA_KEYS = frozenset(
  {
    "schema_version",
    "purpose",
    "source",
    "strategy",
    "matching_method",
  }
)

ADAPTIVE_CONTEXT_GRAPH_TYPES = frozenset(
  {
    "page-title-not-descriptive",
    "heading-not-descriptive",
    "widget-label-purpose-mismatch",
  }
)

ADAPTIVE_CONTEXT_ISOLATED_TYPES = frozenset(SUPPORTED_CANDIDATE_TYPES) - ADAPTIVE_CONTEXT_GRAPH_TYPES


@dataclass(frozen=True)
class ContextModeResolution:
  requested_context_mode: str
  selected_context_mode: str
  resolved_context_mode: str
  context_policy_version: str | None
  graph_context_omitted_reason: str | None


def resolve_confirmation_context_mode(
  candidate_type: str,
  requested_context_mode: str,
  candidate_record: Mapping[str, Any] | None = None,
) -> ContextModeResolution:
  if requested_context_mode not in CONTEXT_MODES:
    allowed = ", ".join(CONTEXT_MODES)
    raise ValueError(
      f"Unsupported confirmation context_mode: {requested_context_mode!r}. "
      f"Allowed values: {allowed}"
    )

  if requested_context_mode == CONTEXT_MODE_ADAPTIVE_V2:
    selected_context_mode = (
      CONTEXT_MODE_HISTORY if candidate_type in TRANSITION_CAPABLE_TYPES else CONTEXT_MODE_ISOLATED
    )
    omitted_reason = _graph_context_omitted_reason(candidate_record, selected_context_mode=selected_context_mode)
    return ContextModeResolution(
      requested_context_mode=requested_context_mode,
      selected_context_mode=selected_context_mode,
      resolved_context_mode=CONTEXT_MODE_ISOLATED if omitted_reason else selected_context_mode,
      context_policy_version=ADAPTIVE_V2_CONTEXT_POLICY_VERSION,
      graph_context_omitted_reason=omitted_reason,
    )
  if requested_context_mode != CONTEXT_MODE_ADAPTIVE:
    selected_context_mode = requested_context_mode
    resolved_context_mode = requested_context_mode
    omitted_reason = _graph_context_omitted_reason(
      candidate_record,
      selected_context_mode=selected_context_mode,
    )
    if omitted_reason:
      resolved_context_mode = CONTEXT_MODE_ISOLATED
    return ContextModeResolution(
      requested_context_mode=requested_context_mode,
      selected_context_mode=selected_context_mode,
      resolved_context_mode=resolved_context_mode,
      context_policy_version=context_policy_version_for_context_mode(requested_context_mode),
      graph_context_omitted_reason=omitted_reason,
    )

  selected_context_mode = _resolve_adaptive_context(candidate_type, candidate_record)
  omitted_reason = _graph_context_omitted_reason(
    candidate_record,
    selected_context_mode=selected_context_mode,
  )
  return ContextModeResolution(
    requested_context_mode=requested_context_mode,
    selected_context_mode=selected_context_mode,
    resolved_context_mode=CONTEXT_MODE_ISOLATED if omitted_reason else selected_context_mode,
    context_policy_version=ADAPTIVE_CONTEXT_POLICY_VERSION,
    graph_context_omitted_reason=omitted_reason,
  )


def context_policy_version_for_context_mode(requested_context_mode: str) -> str | None:
  if requested_context_mode not in CONTEXT_MODES:
    allowed = ", ".join(CONTEXT_MODES)
    raise ValueError(
      f"Unsupported confirmation context_mode: {requested_context_mode!r}. "
      f"Allowed values: {allowed}"
    )
  if requested_context_mode in {CONTEXT_MODE_ADAPTIVE, CONTEXT_MODE_GRAPH}:
    return ADAPTIVE_CONTEXT_POLICY_VERSION
  if requested_context_mode in {CONTEXT_MODE_ADAPTIVE_V2, CONTEXT_MODE_HISTORY}:
    return ADAPTIVE_V2_CONTEXT_POLICY_VERSION
  if requested_context_mode == CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT:
    return None
  return None


def _resolve_adaptive_context(
  candidate_type: str,
  candidate_record: Mapping[str, Any] | None,
) -> str:
  if candidate_type in ADAPTIVE_CONTEXT_GRAPH_TYPES:
    return CONTEXT_MODE_GRAPH
  return CONTEXT_MODE_ISOLATED


def _graph_context_omitted_reason(
  candidate_record: Mapping[str, Any] | None,
  *,
  selected_context_mode: str,
) -> str | None:
  if selected_context_mode not in (CONTEXT_MODE_GRAPH, CONTEXT_MODE_HISTORY):
    return None
  if candidate_record is None:
    return None
  if _has_meaningful_graph_context(candidate_record):
    return None
  return GRAPH_CONTEXT_OMITTED_EMPTY


def _has_meaningful_graph_context(candidate_record: Mapping[str, Any]) -> bool:
  if not isinstance(candidate_record, Mapping):
    return False

  state_context = candidate_record.get("state_context")
  if not isinstance(state_context, Mapping):
    state_context = {}
  if _is_meaningful_scalar(state_context.get("parent_state")):
    return True
  if _is_meaningful_graph_value(state_context.get("action_from_parent")):
    return True

  graph_context = candidate_record.get("graph_context")
  if not isinstance(graph_context, Mapping):
    return False
  if _is_meaningful_graph_value(graph_context.get("transition_path")):
    return True
  if _is_meaningful_graph_value(graph_context.get("incoming_action")):
    return True
  if _is_meaningful_graph_value(graph_context.get("related_state_refs")):
    return True
  return any(
    _is_meaningful_graph_value(value)
    for key, value in graph_context.items()
    if key not in _GRAPH_CONTEXT_IGNORED_KEYS
  )


def _is_meaningful_graph_value(value: Any) -> bool:
  if isinstance(value, Mapping):
    meaningful_items = {
      key: item
      for key, item in value.items()
      if key not in _GRAPH_CONTEXT_METADATA_KEYS
    }
    return any(_is_meaningful_graph_value(item) for item in meaningful_items.values())
  if isinstance(value, (list, tuple)):
    return any(_is_meaningful_graph_value(item) for item in value)
  return _is_meaningful_scalar(value)


def _is_meaningful_scalar(value: Any) -> bool:
  if value is None:
    return False
  if isinstance(value, bool):
    return value
  if isinstance(value, (int, float)):
    return value != 0
  if isinstance(value, str):
    return bool(value.strip())
  return bool(value)
