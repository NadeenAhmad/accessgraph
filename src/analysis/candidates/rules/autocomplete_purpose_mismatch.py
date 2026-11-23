from __future__ import annotations

from ..evidence_helpers import evidence_items, first_present_text
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload
from .form_common import (
  build_autocomplete_purpose_context,
  build_form_control_evidence,
  compact_form_control,
  has_purpose_context,
  is_reviewable_control,
  supporting_payload,
)

CANDIDATE_TYPE = "autocomplete-purpose-mismatch"


def build_autocomplete_purpose_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  for control in evidence_items(state, "form_controls"):
    if not is_reviewable_control(control):
      continue
    if not first_present_text(control, ("autocomplete",)):
      continue
    evidence = build_form_control_evidence(state, control)
    if not has_purpose_context(evidence):
      continue
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        primary_element_ref=evidence.control_ref,
        element_refs=evidence.element_refs,
        selection_reason=["control_with_autocomplete_and_purpose_context"],
        required_context=["autocomplete value", "control purpose", "label and form context"],
        evidence={
          "primary": {"form_control": compact_form_control(control)},
          "supporting": {
            **supporting_payload(evidence),
            "autocomplete_purpose_context_v1": build_autocomplete_purpose_context(state, evidence),
          },
          "bounding_boxes": evidence.bounding_boxes,
          "dom_snippets": evidence.dom_snippets,
        },
        graph_context=graph_context,
      )
    )
  return records
