from __future__ import annotations

import pytest

from src.analysis.candidates.taxonomy import SUPPORTED_CANDIDATE_TYPES
from src.analysis.confirmation.context_policy import (
  ADAPTIVE_CONTEXT_GRAPH_TYPES,
  ADAPTIVE_CONTEXT_ISOLATED_TYPES,
  ADAPTIVE_CONTEXT_POLICY_VERSION,
  GRAPH_CONTEXT_OMITTED_EMPTY,
  context_policy_version_for_context_mode,
  resolve_confirmation_context_mode,
)
from src.analysis.confirmation.models import (
  CONTEXT_MODE_ADAPTIVE,
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_ISOLATED,
  CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
)


def test_adaptive_context_policy_covers_all_supported_candidate_types_once():
  assert ADAPTIVE_CONTEXT_ISOLATED_TYPES.isdisjoint(ADAPTIVE_CONTEXT_GRAPH_TYPES)
  assert ADAPTIVE_CONTEXT_ISOLATED_TYPES | ADAPTIVE_CONTEXT_GRAPH_TYPES == set(SUPPORTED_CANDIDATE_TYPES)


def test_current_types_default_to_isolated_context_except_graph_preferring_types():
  expected = {
    "autocomplete-purpose-mismatch",
    "button-label-mismatch",
    "form-label-mismatch",
    "image-alt-not-descriptive",
    "video-captions-inaccurate",
    "language-of-parts-mismatch",
    "landmark-purpose-mismatch",
    "lang-mismatch",
    "link-text-mismatch",
    "aria-state-mismatch",
    "table-header-association-mismatch",
    "error-message-mismatch",
  }
  assert ADAPTIVE_CONTEXT_ISOLATED_TYPES == expected
  for candidate_type in expected:
    resolution = resolve_confirmation_context_mode(candidate_type, CONTEXT_MODE_ADAPTIVE)
    assert resolution.requested_context_mode == CONTEXT_MODE_ADAPTIVE
    assert resolution.selected_context_mode == CONTEXT_MODE_ISOLATED
    assert resolution.resolved_context_mode == CONTEXT_MODE_ISOLATED
    assert resolution.context_policy_version == ADAPTIVE_CONTEXT_POLICY_VERSION

  video_resolution = resolve_confirmation_context_mode(
    "video-captions-inaccurate",
    CONTEXT_MODE_ADAPTIVE,
  )
  assert video_resolution.resolved_context_mode == CONTEXT_MODE_ISOLATED


def test_graph_context_types_include_state_dependent_current_types():
  assert ADAPTIVE_CONTEXT_GRAPH_TYPES == {
    "page-title-not-descriptive",
    "heading-not-descriptive",
    "widget-label-purpose-mismatch",
  }


def test_explicit_graph_context_falls_back_to_isolated_when_graph_context_is_empty():
  resolution = resolve_confirmation_context_mode(
    "page-title-not-descriptive",
    CONTEXT_MODE_GRAPH,
    candidate_record={
      "candidate_type": "page-title-not-descriptive",
      "state_context": {"depth": 0, "parent_state": None, "action_from_parent": {}},
      "graph_context": {"depth": 0, "transition_path": [], "incoming_action": {}, "related_state_refs": []},
    },
  )
  assert resolution.selected_context_mode == CONTEXT_MODE_GRAPH
  assert resolution.resolved_context_mode == CONTEXT_MODE_ISOLATED
  assert resolution.graph_context_omitted_reason == GRAPH_CONTEXT_OMITTED_EMPTY


def test_context_policy_defaults_unknown_candidate_types_to_isolated_state():
  resolution = resolve_confirmation_context_mode("future-semantic-type", CONTEXT_MODE_ADAPTIVE)
  assert resolution.resolved_context_mode == CONTEXT_MODE_ISOLATED
  assert resolution.context_policy_version == ADAPTIVE_CONTEXT_POLICY_VERSION


def test_fixed_context_modes_and_policy_versions():
  isolated = resolve_confirmation_context_mode("page-title-not-descriptive", CONTEXT_MODE_ISOLATED)
  minimal = resolve_confirmation_context_mode("page-title-not-descriptive", CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT)
  graph = resolve_confirmation_context_mode("button-label-mismatch", CONTEXT_MODE_GRAPH)

  assert isolated.resolved_context_mode == CONTEXT_MODE_ISOLATED
  assert isolated.context_policy_version is None
  assert minimal.resolved_context_mode == CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT
  assert minimal.context_policy_version is None
  assert graph.resolved_context_mode == CONTEXT_MODE_GRAPH
  assert graph.context_policy_version == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert context_policy_version_for_context_mode(CONTEXT_MODE_ADAPTIVE) == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert context_policy_version_for_context_mode(CONTEXT_MODE_GRAPH) == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert context_policy_version_for_context_mode(CONTEXT_MODE_ISOLATED) is None
  assert context_policy_version_for_context_mode(CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT) is None


def test_invalid_requested_context_mode_fails_clearly():
  with pytest.raises(ValueError, match="Unsupported confirmation context_mode"):
    resolve_confirmation_context_mode("button-label-mismatch", "broad_context")
