from __future__ import annotations

import pytest

from src.analysis.confirmation.escalation_policy import (
  ESCALATION_POLICY_VERSION_UNCERTAIN_GRAPH,
  GRAPH_ESCALATION_ELIGIBLE_TYPES,
  escalation_policy_version_for_policy,
  is_graph_escalation_eligible,
  resolve_escalation_decision,
  resolve_retry_context_mode,
  should_escalate_confirmation,
)
from src.analysis.confirmation.models import (
  CONTEXT_MODE_ADAPTIVE,
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_ISOLATED,
  ESCALATION_POLICY_NONE,
  ESCALATION_POLICY_UNCERTAIN_GRAPH,
)


def test_uncertain_graph_policy_marks_adaptive_isolated_types_eligible():
  expected = {
    "autocomplete-purpose-mismatch",
    "button-label-mismatch",
    "form-label-mismatch",
    "image-alt-not-descriptive",
    "language-of-parts-mismatch",
    "landmark-purpose-mismatch",
    "lang-mismatch",
    "link-text-mismatch",
    "aria-state-mismatch",
    "table-header-association-mismatch",
    "error-message-mismatch",
  }
  assert GRAPH_ESCALATION_ELIGIBLE_TYPES == expected
  for candidate_type in expected:
    assert is_graph_escalation_eligible(
      candidate_type,
      ESCALATION_POLICY_UNCERTAIN_GRAPH,
      requested_context_mode=CONTEXT_MODE_ADAPTIVE,
      selected_context_mode=CONTEXT_MODE_ISOLATED,
      initial_context_mode=CONTEXT_MODE_ISOLATED,
    )


def test_uncertain_graph_policy_keeps_graph_context_types_ineligible():
  for candidate_type in {"page-title-not-descriptive", "heading-not-descriptive", "widget-label-purpose-mismatch"}:
    assert not is_graph_escalation_eligible(
      candidate_type,
      ESCALATION_POLICY_UNCERTAIN_GRAPH,
      requested_context_mode=CONTEXT_MODE_ADAPTIVE,
      selected_context_mode=CONTEXT_MODE_GRAPH,
      initial_context_mode=CONTEXT_MODE_GRAPH,
    )

  assert not is_graph_escalation_eligible(
    "page-title-not-descriptive",
    ESCALATION_POLICY_UNCERTAIN_GRAPH,
    requested_context_mode=CONTEXT_MODE_ADAPTIVE,
    selected_context_mode=CONTEXT_MODE_ISOLATED,
    initial_context_mode=CONTEXT_MODE_ISOLATED,
  )


def test_fixed_context_modes_and_none_policy_do_not_retry():
  decision = resolve_escalation_decision(
    candidate_type="button-label-mismatch",
    initial_decision="uncertain",
    initial_parse_status="parsed",
    escalation_policy=ESCALATION_POLICY_UNCERTAIN_GRAPH,
    requested_context_mode=CONTEXT_MODE_ISOLATED,
    selected_context_mode=CONTEXT_MODE_ISOLATED,
    initial_context_mode=CONTEXT_MODE_ISOLATED,
  )
  assert decision.eligible is False
  assert decision.triggered is False
  assert decision.retry_context_mode is None

  assert not should_escalate_confirmation(
    candidate_type="button-label-mismatch",
    initial_decision="uncertain",
    initial_parse_status="parsed",
    escalation_policy=ESCALATION_POLICY_NONE,
    requested_context_mode=CONTEXT_MODE_ADAPTIVE,
    selected_context_mode=CONTEXT_MODE_ISOLATED,
    initial_context_mode=CONTEXT_MODE_ISOLATED,
  )


def test_uncertain_graph_policy_retries_only_parsed_uncertain_adaptive_isolated_context():
  assert should_escalate_confirmation(
    candidate_type="button-label-mismatch",
    initial_decision="uncertain",
    initial_parse_status="parsed",
    escalation_policy=ESCALATION_POLICY_UNCERTAIN_GRAPH,
    requested_context_mode=CONTEXT_MODE_ADAPTIVE,
    selected_context_mode=CONTEXT_MODE_ISOLATED,
    initial_context_mode=CONTEXT_MODE_ISOLATED,
  )
  assert not should_escalate_confirmation(
    candidate_type="button-label-mismatch",
    initial_decision="violation",
    initial_parse_status="parsed",
    escalation_policy=ESCALATION_POLICY_UNCERTAIN_GRAPH,
    requested_context_mode=CONTEXT_MODE_ADAPTIVE,
    selected_context_mode=CONTEXT_MODE_ISOLATED,
    initial_context_mode=CONTEXT_MODE_ISOLATED,
  )
  assert not should_escalate_confirmation(
    candidate_type="button-label-mismatch",
    initial_decision="uncertain",
    initial_parse_status="schema_error",
    escalation_policy=ESCALATION_POLICY_UNCERTAIN_GRAPH,
    requested_context_mode=CONTEXT_MODE_ADAPTIVE,
    selected_context_mode=CONTEXT_MODE_ISOLATED,
    initial_context_mode=CONTEXT_MODE_ISOLATED,
  )


def test_retry_context_and_policy_version():
  assert resolve_retry_context_mode(
    candidate_type="button-label-mismatch",
    initial_decision="uncertain",
    initial_parse_status="parsed",
    escalation_policy=ESCALATION_POLICY_UNCERTAIN_GRAPH,
    requested_context_mode=CONTEXT_MODE_ADAPTIVE,
    selected_context_mode=CONTEXT_MODE_ISOLATED,
    initial_context_mode=CONTEXT_MODE_ISOLATED,
  ) == CONTEXT_MODE_GRAPH
  assert escalation_policy_version_for_policy(ESCALATION_POLICY_NONE) is None
  assert escalation_policy_version_for_policy(ESCALATION_POLICY_UNCERTAIN_GRAPH) == ESCALATION_POLICY_VERSION_UNCERTAIN_GRAPH


def test_invalid_escalation_policy_fails_clearly():
  with pytest.raises(ValueError, match="Unsupported confirmation escalation_policy"):
    should_escalate_confirmation(
      candidate_type="page-title-not-descriptive",
      initial_decision="uncertain",
      initial_parse_status="parsed",
      escalation_policy="retry_everything",
      requested_context_mode=CONTEXT_MODE_ADAPTIVE,
      selected_context_mode=CONTEXT_MODE_ISOLATED,
      initial_context_mode=CONTEXT_MODE_ISOLATED,
    )
