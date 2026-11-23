from __future__ import annotations

from dataclasses import dataclass

from .context_policy import ADAPTIVE_CONTEXT_ISOLATED_TYPES
from .models import (
  CONTEXT_MODE_ADAPTIVE,
  CONTEXT_MODE_ADAPTIVE_V2,
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_HISTORY,
  CONTEXT_MODE_ISOLATED,
  ESCALATION_POLICIES,
  ESCALATION_POLICY_NONE,
  ESCALATION_POLICY_UNCERTAIN_GRAPH,
  ESCALATION_POLICY_UNCERTAIN_HISTORY,
  ConfirmationDecision,
  ConfirmationParseStatus,
)

ESCALATION_POLICY_VERSION_UNCERTAIN_GRAPH = "uncertain_graph_v1"
ESCALATION_POLICY_VERSION_UNCERTAIN_HISTORY = "uncertain_history_v1"

GRAPH_ESCALATION_ELIGIBLE_TYPES = ADAPTIVE_CONTEXT_ISOLATED_TYPES


@dataclass(frozen=True)
class EscalationDecision:
  escalation_policy: str
  escalation_policy_version: str | None
  eligible: bool
  triggered: bool
  retry_context_mode: str | None


def resolve_escalation_decision(
  *,
  candidate_type: str,
  initial_decision: ConfirmationDecision,
  initial_parse_status: ConfirmationParseStatus,
  escalation_policy: str,
  requested_context_mode: str,
  selected_context_mode: str,
  initial_context_mode: str,
) -> EscalationDecision:
  _validate_escalation_policy(escalation_policy)
  policy_version = escalation_policy_version_for_policy(escalation_policy)
  eligible = is_graph_escalation_eligible(
    candidate_type,
    escalation_policy,
    requested_context_mode=requested_context_mode,
    selected_context_mode=selected_context_mode,
    initial_context_mode=initial_context_mode,
  )
  triggered = should_escalate_confirmation(
    candidate_type=candidate_type,
    initial_decision=initial_decision,
    initial_parse_status=initial_parse_status,
    escalation_policy=escalation_policy,
    requested_context_mode=requested_context_mode,
    selected_context_mode=selected_context_mode,
    initial_context_mode=initial_context_mode,
  )
  return EscalationDecision(
    escalation_policy=escalation_policy,
    escalation_policy_version=policy_version,
    eligible=eligible,
    triggered=triggered,
    retry_context_mode=_retry_mode(escalation_policy) if triggered else None,
  )


def _retry_mode(escalation_policy: str) -> str:
  return CONTEXT_MODE_HISTORY if escalation_policy == ESCALATION_POLICY_UNCERTAIN_HISTORY else CONTEXT_MODE_GRAPH


def should_escalate_confirmation(
  *,
  candidate_type: str,
  initial_decision: ConfirmationDecision,
  initial_parse_status: ConfirmationParseStatus,
  escalation_policy: str,
  requested_context_mode: str,
  selected_context_mode: str,
  initial_context_mode: str,
) -> bool:
  _validate_escalation_policy(escalation_policy)
  if not is_graph_escalation_eligible(
    candidate_type,
    escalation_policy,
    requested_context_mode=requested_context_mode,
    selected_context_mode=selected_context_mode,
    initial_context_mode=initial_context_mode,
  ):
    return False
  if escalation_policy in (ESCALATION_POLICY_UNCERTAIN_GRAPH, ESCALATION_POLICY_UNCERTAIN_HISTORY):
    return (
      initial_parse_status == "parsed"
      and initial_decision == "uncertain"
    )
  return False


def resolve_retry_context_mode(
  *,
  candidate_type: str,
  initial_decision: ConfirmationDecision,
  initial_parse_status: ConfirmationParseStatus,
  escalation_policy: str,
  requested_context_mode: str,
  selected_context_mode: str,
  initial_context_mode: str,
) -> str | None:
  if should_escalate_confirmation(
    candidate_type=candidate_type,
    initial_decision=initial_decision,
    initial_parse_status=initial_parse_status,
    escalation_policy=escalation_policy,
    requested_context_mode=requested_context_mode,
    selected_context_mode=selected_context_mode,
    initial_context_mode=initial_context_mode,
  ):
    return _retry_mode(escalation_policy)
  return None


def is_graph_escalation_eligible(
  candidate_type: str,
  escalation_policy: str,
  *,
  requested_context_mode: str,
  selected_context_mode: str,
  initial_context_mode: str,
) -> bool:
  _validate_escalation_policy(escalation_policy)
  if escalation_policy == ESCALATION_POLICY_UNCERTAIN_HISTORY:
    # adaptive_v2: any uncertain verdict reached in isolation is re-judged with history.
    return (
      requested_context_mode == CONTEXT_MODE_ADAPTIVE_V2
      and selected_context_mode == CONTEXT_MODE_ISOLATED
      and initial_context_mode == CONTEXT_MODE_ISOLATED
    )
  return (
    escalation_policy == ESCALATION_POLICY_UNCERTAIN_GRAPH
    and candidate_type in GRAPH_ESCALATION_ELIGIBLE_TYPES
    and requested_context_mode == CONTEXT_MODE_ADAPTIVE
    and selected_context_mode == CONTEXT_MODE_ISOLATED
    and initial_context_mode == CONTEXT_MODE_ISOLATED
  )


def escalation_policy_version_for_policy(escalation_policy: str) -> str | None:
  _validate_escalation_policy(escalation_policy)
  if escalation_policy == ESCALATION_POLICY_UNCERTAIN_GRAPH:
    return ESCALATION_POLICY_VERSION_UNCERTAIN_GRAPH
  if escalation_policy == ESCALATION_POLICY_UNCERTAIN_HISTORY:
    return ESCALATION_POLICY_VERSION_UNCERTAIN_HISTORY
  return None


def _validate_escalation_policy(escalation_policy: str) -> None:
  if escalation_policy not in ESCALATION_POLICIES:
    allowed = ", ".join(ESCALATION_POLICIES)
    raise ValueError(
      f"Unsupported confirmation escalation_policy: {escalation_policy!r}. "
      f"Allowed values: {allowed}"
    )
