from __future__ import annotations

from ..evidence_helpers import evidence_items
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload
from .form_common import (
  build_form_label_context,
  build_form_control_evidence,
  compact_form_control,
  has_context_evidence,
  has_label_or_name_evidence,
  is_reviewable_control,
  supporting_payload,
)

CANDIDATE_TYPE = "form-label-mismatch"


def build_form_label_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  for control in evidence_items(state, "form_controls"):
    if not is_reviewable_control(control):
      continue
    evidence = build_form_control_evidence(state, control)
    if not has_label_or_name_evidence(evidence) or not has_context_evidence(evidence):
      continue
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        primary_element_ref=evidence.control_ref,
        element_refs=evidence.element_refs,
        selection_reason=["form_control_with_label_and_context_evidence"],
        required_context=["control purpose", "label text", "form and section context"],
        evidence={
          "primary": {"form_control": compact_form_control(control)},
          "supporting": {
            **supporting_payload(evidence),
            "form_label_context_v1": build_form_label_context(state, evidence),
          },
          "bounding_boxes": evidence.bounding_boxes,
          "dom_snippets": evidence.dom_snippets,
        },
        graph_context=graph_context,
      )
    )
  return records
