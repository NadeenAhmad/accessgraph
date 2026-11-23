from __future__ import annotations

from ..evidence_helpers import evidence_items, first_present_text, truncate_text
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload
from .form_common import (
  build_form_control_evidence,
  compact_form_control,
  is_reviewable_control,
  supporting_payload,
)
from .structure_common import compact_page

CANDIDATE_TYPE = "error-message-mismatch"
ERROR_MESSAGE_CONTEXT_SCHEMA_VERSION = "error_message_context_v1"


def build_error_message_mismatch_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  with_message: set[str] = set()
  for control in evidence_items(state, "form_controls"):
    if not is_reviewable_control(control):
      continue
    evidence = build_form_control_evidence(state, control)
    if not _has_invalid_state(control) or not _has_associated_error_message(evidence.descriptions):
      continue
    with_message.add(str(control.get("xpath") or ""))
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        primary_element_ref=evidence.control_ref,
        element_refs=evidence.element_refs,
        selection_reason=["invalid_form_control_with_associated_message_evidence"],
        required_context=[
          "form control and label",
          "current invalid or validation state",
          "associated error message",
        ],
        evidence={
          "primary": {
            "form_control": compact_form_control(control),
            "error_message": _primary_error_message(evidence.descriptions),
          },
          "supporting": {
            **supporting_payload(evidence),
            "page": compact_page(state),
            "error_message_context_v1": _build_error_message_context(control, evidence.descriptions),
          },
          "bounding_boxes": evidence.bounding_boxes,
          "dom_snippets": evidence.dom_snippets,
        },
        graph_context=graph_context,
      )
    )
  records.extend(_invalid_without_text_candidates(run, state, graph_context, with_message=with_message))
  records.extend(_page_error_text_candidates(run, state, graph_context, with_message=with_message))
  records.extend(_hidden_error_text_candidates(run, state, graph_context))
  return records


def _hidden_error_text_candidates(run: RunArtifacts, state: RunState, graph_context: dict[str, object]) -> list[dict[str, object]]:
  """W4A round 5 (WCAG 3.3.1): an error message referenced by a field or its submit control but not shown
  (recorded as `page.hidden_error_texts`, with the form's current values), only when some field of the form holds a
  filled-in value; the judge decides whether that value fails the requirement the hidden message states. One
  candidate per form, on the first filled-in field."""
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  hidden = [t for t in page.get("hidden_error_texts") or [] if isinstance(t, dict) and t.get("text")]
  controls = {str(c.get("xpath") or ""): c for c in evidence_items(state, "form_controls") if is_reviewable_control(c)}
  out, seen_forms = [], set()
  for text in hidden:
    form = str(text.get("form_xpath") or "")
    if form in seen_forms:
      continue
    filled = [v for v in text.get("form_values") or [] if isinstance(v, dict)
              and str(v.get("value") or "").strip() not in {"", "not checked"} and str(v.get("xpath") or "") in controls]
    if not filled:
      continue
    seen_forms.add(form)
    control = controls[str(filled[0]["xpath"])]
    evidence = build_form_control_evidence(state, control)
    texts = [t for t in hidden if str(t.get("form_xpath") or "") == form]
    out.append(build_candidate_payload(
      run=run, state=state, candidate_type=CANDIDATE_TYPE, primary_element_ref=evidence.control_ref,
      element_refs=evidence.element_refs, selection_reason=["error_message_not_shown_while_a_field_is_filled_in"],
      required_context=["form fields and their current values", "the hidden error message", "whether a value fails it"],
      evidence={
        "primary": {"hidden_error_messages": [{k: t.get(k) for k in ("text", "referenced_by", "xpath")} for t in texts],
                    "form_values": text.get("form_values") or []},
        "supporting": {**supporting_payload(evidence), "page": compact_page(state)},
        "bounding_boxes": evidence.bounding_boxes,
        "dom_snippets": evidence.dom_snippets,
      },
      graph_context=graph_context,
    ))
  return out


def _invalid_without_text_candidates(run: RunArtifacts, state: RunState, graph_context: dict[str, object], *,
                                     with_message: set[str]) -> list[dict[str, object]]:
  """W4A round 3: a field marked invalid whose error is not described in associated text (only an icon, an icon
  label such as 'Invalid input', or nothing) is a 3.3.1 question too."""
  out = []
  texts = _page_error_texts(state)
  for control in evidence_items(state, "form_controls"):
    # W4A round 4: a field shown in error only visually (class, icon, red border) is the same question (F81)
    if not is_reviewable_control(control) or not (_has_invalid_state(control) or control.get("visual_error_signals")):
      continue
    if str(control.get("xpath") or "") in with_message:
      continue
    evidence = build_form_control_evidence(state, control)
    out.append(build_candidate_payload(
      run=run, state=state, candidate_type=CANDIDATE_TYPE, primary_element_ref=evidence.control_ref,
      element_refs=evidence.element_refs, selection_reason=["invalid_form_control_without_associated_text_message"],
      required_context=["form control and label", "current invalid or validation state", "how the error is described"],
      evidence={
        "primary": {"form_control": compact_form_control(control),
                    "visual_error_signals": control.get("visual_error_signals") or [],
                    "announced_description": control.get("browser_description"),
                    "page_error_texts": texts},
        "supporting": {**supporting_payload(evidence), "page": compact_page(state)},
        "bounding_boxes": evidence.bounding_boxes,
        "dom_snippets": evidence.dom_snippets,
      },
      graph_context=graph_context,
    ))
  return out


def _short_hash(text: str) -> str:
  import hashlib
  return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:10]


def _page_error_texts(state: RunState) -> list[dict[str, object]]:
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  return [t for t in page.get("error_texts") or [] if isinstance(t, dict) and t.get("text")]


def _page_error_text_candidates(run: RunArtifacts, state: RunState, graph_context: dict[str, object], *,
                                with_message: set[str]) -> list[dict[str, object]]:
  """W4A dev round 2: 3.3.1 also fails when an error text on the page is not tied to the field in error or not
  available to assistive technologies, which the associated-message rule above cannot see. One candidate per form
  (or page) that shows such a text, on its invalid control or else its first reviewable control."""
  loose = [t for t in _page_error_texts(state) if not t.get("referenced_by_a_field") or t.get("hidden_from_assistive_technology")]
  # W4A round 3: error summaries and alerts are checked against the fields even when the fields have their own
  # messages (a summary can count or describe the errors wrongly)
  if not loose:
    return []
  controls = [c for c in evidence_items(state, "form_controls") if is_reviewable_control(c)]
  if not controls:
    return []
  by_form: dict[str, list[dict[str, object]]] = {}
  seen_texts: set[str] = set()
  for text in loose:  # one candidate per page: the same summary can appear in and outside the form
    key = " ".join(str(text.get("text") or "").lower().split())
    if key in seen_texts:
      continue
    seen_texts.add(key)
    by_form.setdefault("", []).append(text)
  out = []
  for form_xpath, texts in by_form.items():
    in_form = [c for c in controls if form_xpath and str(c.get("xpath") or "").startswith(form_xpath + "/")] or controls
    invalid = [c for c in in_form if _has_invalid_state(c)]
    control = (invalid or in_form)[0]
    evidence = build_form_control_evidence(state, control)
    summary_refs = [{"bucket": "page_error_texts", "element_id": "errtext_" + _short_hash(str(t.get("xpath") or t.get("text"))),
                     "xpath": t.get("xpath")} for t in texts]
    out.append(build_candidate_payload(
      run=run, state=state, candidate_type=CANDIDATE_TYPE, primary_element_ref=summary_refs[0],
      element_refs=summary_refs, selection_reason=["error_text_not_tied_to_a_field_or_hidden"],
      required_context=["form controls and labels", "error texts on the page", "which field each text concerns"],
      evidence={
        "primary": {"page_error_texts": texts, "first_invalid_or_first_field": compact_form_control(control)},
        "supporting": {
          **supporting_payload(evidence),
          "page": compact_page(state),
          "form_controls_in_scope": [{**compact_form_control(c), "invalid": _has_invalid_state(c),
                                      "value_present": bool(c.get("value_present") or c.get("has_value"))}
                                     for c in in_form[:12]],
        },
        "bounding_boxes": evidence.bounding_boxes,
        "dom_snippets": evidence.dom_snippets,
      },
      graph_context=graph_context,
    ))
  return out


def _has_invalid_state(control: dict[str, object]) -> bool:
  if control.get("invalid") is True:
    return True
  if str(control.get("aria_invalid") or "").strip().lower() in {"true", "grammar", "spelling"}:
    return True
  native = control.get("native_validity") if isinstance(control.get("native_validity"), dict) else {}
  return native.get("valid") is False


def _has_associated_error_message(descriptions: list[dict[str, object]]) -> bool:
  return bool(_description_texts(descriptions))


def _primary_error_message(descriptions: list[dict[str, object]]) -> dict[str, object]:
  for description in descriptions:
    text = truncate_text(description.get("text"), max_length=240)
    if text:
      return {
        "element_id": str(description.get("element_id") or ""),
        "selector": str(description.get("selector") or ""),
        "text": text,
        "relationship_type": description.get("relationship_type"),
        "method": description.get("method"),
      }
  return {}


def _build_error_message_context(
  control: dict[str, object],
  descriptions: list[dict[str, object]],
) -> dict[str, object]:
  native = control.get("native_validity") if isinstance(control.get("native_validity"), dict) else {}
  return {
    "schema_version": ERROR_MESSAGE_CONTEXT_SCHEMA_VERSION,
    "control": {
      "element_id": str(control.get("element_id") or ""),
      "selector": str(control.get("selector") or ""),
      "tag": str(control.get("tag") or ""),
      "role": control.get("role"),
      "type": control.get("type"),
      "name": control.get("name"),
      "id": control.get("id"),
      "label": first_present_text(control, ("label", "wrapping_label", "accessible_name", "aria_label")),
      "aria_invalid": control.get("aria_invalid"),
      "invalid": control.get("invalid"),
      "value_state": _value_state(control),
      "native_validity": native,
    },
    "associated_error_messages": [
      {
        "element_id": str(description.get("element_id") or ""),
        "selector": str(description.get("selector") or ""),
        "text": truncate_text(description.get("text"), max_length=240),
        "relationship_type": description.get("relationship_type"),
        "method": description.get("method"),
      }
      for description in descriptions
      if truncate_text(description.get("text"), max_length=240)
    ],
    "validation_state_observations": {
      "aria_invalid": control.get("aria_invalid"),
      "native_validity": native,
      "has_value": control.get("has_value"),
      "value_content_recorded": False,
    },
  }


def _description_texts(descriptions: list[dict[str, object]]) -> list[str]:
  return [
    text
    for description in descriptions
    if (text := truncate_text(description.get("text"), max_length=240))
  ]


def _value_state(control: dict[str, object]) -> str:
  has_value = control.get("has_value")
  if has_value is True:
    return "filled"
  if has_value is False:
    return "empty"
  return "unknown"
