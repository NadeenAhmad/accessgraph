from __future__ import annotations

from dataclasses import dataclass
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
from ..models import RunState

LABEL_RELATIONSHIP_TYPES = {"labels", "labelledby"}
DESCRIPTION_RELATIONSHIP_TYPES = {"describes"}
FORM_RELATIONSHIP_TYPES = {"form_contains"}

_AUTOCOMPLETE_PURPOSES: dict[str, tuple[str, str]] = {
  "name": ("full name", "name"),
  "honorific-prefix": ("honorific prefix", "name"),
  "honorific-suffix": ("honorific suffix", "name"),
  "given-name": ("given name", "name"),
  "additional-name": ("additional name", "name"),
  "family-name": ("family name", "name"),
  "nickname": ("nickname", "name"),
  "organization-title": ("organization title", "organization"),
  "organization": ("organization", "organization"),
  "username": ("username", "authentication"),
  "new-password": ("new password", "authentication"),
  "current-password": ("current password", "authentication"),
  "one-time-code": ("one-time code", "authentication"),
  "street-address": ("street address", "address"),
  "address-line1": ("address line 1", "address"),
  "address-line2": ("address line 2", "address"),
  "address-line3": ("address line 3", "address"),
  "address-level1": ("address administrative level 1", "address"),
  "address-level2": ("address administrative level 2", "address"),
  "address-level3": ("address administrative level 3", "address"),
  "address-level4": ("address administrative level 4", "address"),
  "country": ("country code", "address"),
  "country-name": ("country name", "address"),
  "postal-code": ("postal code", "address"),
  "cc-name": ("payment card name", "payment"),
  "cc-given-name": ("payment card given name", "payment"),
  "cc-additional-name": ("payment card additional name", "payment"),
  "cc-family-name": ("payment card family name", "payment"),
  "cc-number": ("payment card number", "payment"),
  "cc-exp": ("payment card expiration", "payment"),
  "cc-exp-month": ("payment card expiration month", "payment"),
  "cc-exp-year": ("payment card expiration year", "payment"),
  "cc-csc": ("payment card security code", "payment"),
  "cc-type": ("payment card type", "payment"),
  "transaction-currency": ("transaction currency", "payment"),
  "transaction-amount": ("transaction amount", "payment"),
  "language": ("preferred language", "language"),
  "bday": ("birthday", "date"),
  "bday-day": ("birthday day", "date"),
  "bday-month": ("birthday month", "date"),
  "bday-year": ("birthday year", "date"),
  "sex": ("sex or gender identity", "demographic"),
  "url": ("URL", "url"),
  "photo": ("photo", "media"),
  "tel": ("telephone number", "tel"),
  "tel-country-code": ("telephone country code", "tel"),
  "tel-national": ("national telephone number", "tel"),
  "tel-area-code": ("telephone area code", "tel"),
  "tel-local": ("local telephone number", "tel"),
  "tel-local-prefix": ("local telephone prefix", "tel"),
  "tel-local-suffix": ("local telephone suffix", "tel"),
  "tel-extension": ("telephone extension", "tel"),
  "email": ("email address", "email"),
  "impp": ("instant messaging protocol address", "messaging"),
}
_AUTOCOMPLETE_CONTEXT_TOKENS = {"shipping", "billing", "home", "work", "mobile", "fax", "pager", "webauthn"}


@dataclass(frozen=True)
class FormControlEvidence:
  control: dict[str, Any]
  control_ref: dict[str, object]
  element_refs: list[dict[str, object]]
  labels: list[dict[str, object]]
  descriptions: list[dict[str, object]]
  relationships: list[dict[str, object]]
  parent_form: dict[str, object]
  context: dict[str, object]
  bounding_boxes: list[dict[str, object]]
  dom_snippets: list[dict[str, object]]


def build_form_control_evidence(state: RunState, control: dict[str, Any]) -> FormControlEvidence:
  control_id = str(control.get("element_id") or "")
  relationships = _relationships_for_control(state, control_id)
  referenced_by_id = {
    str(item.get("element_id") or ""): item
    for item in evidence_items(state, "referenced_elements")
    if str(item.get("element_id") or "")
  }
  forms_by_id = {
    str(item.get("element_id") or ""): item
    for item in evidence_items(state, "forms")
    if str(item.get("element_id") or "")
  }

  element_refs = [
    {
      **element_ref("form_controls", control),
      "relationship_role": "control",
    }
  ]
  labels: list[dict[str, object]] = []
  descriptions: list[dict[str, object]] = []

  for relationship in relationships:
    relationship_type = str(relationship.get("type") or "")
    method = str(relationship.get("method") or "")
    source_id = str(relationship.get("from_element_id") or "")
    target_id = str(relationship.get("to_element_id") or "")

    if relationship_type in LABEL_RELATIONSHIP_TYPES and target_id == control_id:
      ref = referenced_by_id.get(source_id)
      if ref:
        labels.append(_compact_reference(ref, relationship=relationship))
        element_refs.append(
          {
            **element_ref("referenced_elements", ref),
            "relationship_role": "label",
            "relationship_type": relationship_type,
            "method": method,
          }
        )
    elif relationship_type in DESCRIPTION_RELATIONSHIP_TYPES and target_id == control_id:
      ref = referenced_by_id.get(source_id)
      if ref:
        descriptions.append(_compact_reference(ref, relationship=relationship))
        element_refs.append(
          {
            **element_ref("referenced_elements", ref),
            "relationship_role": "description",
            "relationship_type": relationship_type,
            "method": method,
          }
        )

  parent_form = _parent_form(control, forms_by_id)
  form_ref = parent_form.get("element_id")
  if form_ref:
    form = forms_by_id.get(str(form_ref))
    if form:
      element_refs.append(
        {
          **element_ref("forms", form),
          "relationship_role": "parent_form",
          "relationship_type": "form_contains",
          "method": "descendant",
        }
      )

  unique_refs = _dedupe_refs(element_refs)
  snippets = [snippet for snippet in [dom_snippet(control)] if snippet]
  return FormControlEvidence(
    control=control,
    control_ref=unique_refs[0],
    element_refs=unique_refs,
    labels=labels,
    descriptions=descriptions,
    relationships=relationships[:20],
    parent_form=parent_form,
    context=control.get("context") if isinstance(control.get("context"), dict) else {},
    bounding_boxes=[bounding_box_ref(control)],
    dom_snippets=snippets,
  )


def is_reviewable_control(control: dict[str, Any]) -> bool:
  return is_visible(control) and not bool(control.get("disabled"))


def has_label_or_name_evidence(evidence: FormControlEvidence) -> bool:
  control = evidence.control
  return bool(
    evidence.labels
    or first_present_text(
      control,
      (
        "label",
        "wrapping_label",
        "accessible_name",
        "aria_label",
        "aria_labelledby",
      ),
    )
  )


def has_context_evidence(evidence: FormControlEvidence) -> bool:
  control = evidence.control
  context = evidence.context
  return bool(
    evidence.descriptions
    or evidence.parent_form
    or first_present_text(control, ("placeholder", "type", "name"))
    or _context_text(context)
  )


def has_visible_label_evidence(evidence: FormControlEvidence) -> bool:
  control = evidence.control
  if first_present_text(control, ("label", "wrapping_label")):
    return True
  return any(
    label.get("relationship_type") == "labels"
    for label in evidence.labels
  )


def has_accessible_name_evidence(evidence: FormControlEvidence) -> bool:
  return bool(first_present_text(evidence.control, ("accessible_name", "aria_label", "aria_labelledby")))


def has_purpose_context(evidence: FormControlEvidence) -> bool:
  control = evidence.control
  return bool(
    has_label_or_name_evidence(evidence)
    or first_present_text(control, ("type", "name", "placeholder"))
    or evidence.parent_form
    or _context_text(evidence.context)
  )


def compact_form_control(control: dict[str, Any]) -> dict[str, object]:
  return {
    "element_id": str(control.get("element_id") or ""),
    "tag": str(control.get("tag") or ""),
    "role": control.get("role"),
    "selector": str(control.get("selector") or ""),
    "text": truncate_text(control.get("text")),
    "accessible_name": control.get("accessible_name"),
    "aria_label": control.get("aria_label"),
    "aria_labelledby": control.get("aria_labelledby"),
    "aria_describedby": control.get("aria_describedby"),
    "label": control.get("label"),
    "wrapping_label": control.get("wrapping_label"),
    "type": control.get("type"),
    "name": control.get("name"),
    "id": control.get("id"),
    "placeholder": control.get("placeholder"),
    "autocomplete": control.get("autocomplete"),
    "required": bool(control.get("required")),
    "disabled": bool(control.get("disabled")),
    "readonly": bool(control.get("readonly")),
    "aria_invalid": control.get("aria_invalid"),
    "browser_description": control.get("browser_description"),
    "aria_controls": control.get("aria_controls"),
    "aria_expanded": control.get("aria_expanded"),
    "aria_selected": control.get("aria_selected"),
    "aria_checked": control.get("aria_checked"),
    "aria_pressed": control.get("aria_pressed"),
    "invalid": bool(control.get("invalid")),
    "native_validity": control.get("native_validity") if isinstance(control.get("native_validity"), dict) else {},
    "checked": control.get("checked"),
    "selected": control.get("selected"),
    "has_value": bool(control.get("has_value")),
  }


def supporting_payload(evidence: FormControlEvidence) -> dict[str, object]:
  return {
    "labels": evidence.labels,
    "descriptions": evidence.descriptions,
    "relationships": evidence.relationships,
    "parent_form": evidence.parent_form,
    "context": evidence.context,
    "structure": evidence.control.get("structure") if isinstance(evidence.control.get("structure"), dict) else {},
  }


def build_form_label_context(state: RunState, evidence: FormControlEvidence) -> dict[str, object]:
  control = evidence.control
  label_texts = [
    str(label.get("text") or "")
    for label in evidence.labels
    if str(label.get("text") or "")
  ]
  aria_labelledby_texts = [
    str(label.get("text") or "")
    for label in evidence.labels
    if label.get("relationship_type") == "labelledby" and str(label.get("text") or "")
  ]
  visible_label = (label_texts[0] if label_texts else "") or first_present_text(
    control,
    ("label", "wrapping_label"),
  )
  accessible_name = first_present_text(control, ("accessible_name", "aria_label", "aria_labelledby"))
  state_context = state.accessibility_context.get("state_context")
  if not isinstance(state_context, dict):
    state_context = {}
  route_context = {
    "url": state.metadata.get("url") or state_context.get("url"),
    "route": state.metadata.get("route") or state_context.get("route"),
    "title": state.metadata.get("title") or state_context.get("title"),
  }
  section_heading = (
    truncate_text(evidence.context.get("section_heading"))
    if isinstance(evidence.context, dict)
    else ""
  )
  label_boxes = [
    {
      "element_id": str(label.get("element_id") or ""),
      "selector": str(label.get("selector") or ""),
      "bounding_box": label.get("bounding_box") if isinstance(label.get("bounding_box"), dict) else {},
    }
    for label in evidence.labels
    if isinstance(label.get("bounding_box"), dict)
  ]
  return {
    "schema_version": "form_label_context_v1",
    "control": {
      "element_id": str(control.get("element_id") or ""),
      "selector": str(control.get("selector") or ""),
      "html": truncate_text(control.get("raw_html")),
      "tag": str(control.get("tag") or ""),
      "role": control.get("role"),
      "type": control.get("type"),
      "name": control.get("name"),
      "id": control.get("id"),
      "autocomplete": control.get("autocomplete"),
      "placeholder": control.get("placeholder"),
      "required": bool(control.get("required")),
      "disabled": bool(control.get("disabled")),
      "readonly": bool(control.get("readonly")),
      "aria_invalid": control.get("aria_invalid"),
      "native_validity": control.get("native_validity") if isinstance(control.get("native_validity"), dict) else {},
      "value_state": _value_state(control),
    },
    "labeling": {
      "visible_label": visible_label,
      "computed_accessible_name": accessible_name,
      "label_element_text": " ".join(label_texts),
      "label_sources": _label_sources(evidence.labels),
      "aria_label": control.get("aria_label"),
      "aria_labelledby": control.get("aria_labelledby"),
      "aria_labelledby_text": " ".join(aria_labelledby_texts),
      "title": control.get("title"),
      "visible_label_in_accessible_name": _contains_normalized(
        haystack=accessible_name,
        needle=visible_label,
      ),
    },
    "field_purpose_evidence": {
      "type": control.get("type"),
      "name": control.get("name"),
      "id": control.get("id"),
      "autocomplete": control.get("autocomplete"),
      "placeholder": control.get("placeholder"),
      "nearby_instructions": _nearby_instruction_text(evidence),
      "descriptions": evidence.descriptions,
      "fieldset_or_group": _fieldset_or_group_text(evidence),
      "form_context": evidence.parent_form,
      "form_step_or_route_context": {
        **route_context,
        "section_heading": section_heading,
      },
    },
    "visual_pairing": {
      "has_bounding_box": isinstance(control.get("bounding_box"), dict),
      "control_box": control.get("bounding_box") if isinstance(control.get("bounding_box"), dict) else {},
      "label_boxes": label_boxes,
      "screenshot_reference": f"states/{state.state_id}/screenshot.png",
      "pairing_evidence": "control_and_label_boxes" if label_boxes else "control_box_only",
    },
  }


def build_label_name_context(state: RunState, evidence: FormControlEvidence) -> dict[str, object]:
  control = evidence.control
  visible_label_sources = [
    label
    for label in evidence.labels
    if label.get("relationship_type") == "labels"
  ]
  labelledby_sources = [
    label
    for label in evidence.labels
    if label.get("relationship_type") == "labelledby"
  ]
  visible_label_texts = _dedupe_texts(
    [label.get("text") for label in visible_label_sources]
    if visible_label_sources
    else [control.get("label"), control.get("wrapping_label")]
  )
  visible_label = truncate_text(" ".join(visible_label_texts))
  accessible_name = first_present_text(control, ("accessible_name", "aria_label", "aria_labelledby"))
  labelledby_text = truncate_text(" ".join(_dedupe_texts([
    label.get("text")
    for label in labelledby_sources
  ])))
  state_context = state.accessibility_context.get("state_context")
  if not isinstance(state_context, dict):
    state_context = {}
  label_boxes = [
    {
      "element_id": str(label.get("element_id") or ""),
      "selector": str(label.get("selector") or ""),
      "bounding_box": label.get("bounding_box") if isinstance(label.get("bounding_box"), dict) else {},
    }
    for label in visible_label_sources
    if isinstance(label.get("bounding_box"), dict)
  ]
  return {
    "schema_version": "label_name_context_v1",
    "control": {
      "element_id": str(control.get("element_id") or ""),
      "selector": str(control.get("selector") or ""),
      "html": truncate_text(control.get("raw_html")),
      "tag": str(control.get("tag") or ""),
      "role": control.get("role"),
      "type": control.get("type"),
      "id": control.get("id"),
      "name": control.get("name"),
      "text_content": truncate_text(control.get("text")),
      "placeholder": control.get("placeholder"),
      "title": control.get("title"),
      "aria_label": control.get("aria_label"),
      "aria_labelledby": control.get("aria_labelledby"),
      "aria_describedby": control.get("aria_describedby"),
      "value_state": _value_state(control),
    },
    "visible_label": {
      "text": visible_label,
      "source": _visible_label_source(control, visible_label_sources),
      "label_element_text": truncate_text(" ".join(_dedupe_texts([
        label.get("text")
        for label in visible_label_sources
      ]))),
      "rendered_text": visible_label,
      "associated_label_for": control.get("id") if any(
        label.get("method") == "for"
        for label in visible_label_sources
      ) else None,
      "visible_text_tokens": _text_tokens(visible_label),
      "normalized_visible_text": _normalize_text_words(visible_label),
    },
    "accessible_name": {
      "computed_name": accessible_name,
      "name_source": _accessible_name_source(control, visible_label_sources),
      "aria_label": control.get("aria_label"),
      "aria_labelledby": control.get("aria_labelledby"),
      "aria_labelledby_text": labelledby_text,
      "label_element_text": truncate_text(" ".join(_dedupe_texts([
        label.get("text")
        for label in visible_label_sources
      ]))),
      "title": control.get("title"),
      "content_text": truncate_text(control.get("text")),
      "accessible_name_tokens": _text_tokens(accessible_name),
      "normalized_accessible_name": _normalize_text_words(accessible_name),
    },
    "relationship_evidence": {
      "label_sources": _label_sources(visible_label_sources),
      "label_for_matches_control_id": True if any(
        label.get("method") == "for"
        for label in visible_label_sources
      ) else None,
      "label_wraps_control": any(
        label.get("method") == "wrapper"
        for label in visible_label_sources
      ),
      "aria_labelledby_targets": [
        target
        for target in str(control.get("aria_labelledby") or "").split()
        if target
      ],
      "aria_labelledby_sources": _label_sources(labelledby_sources),
      "nearby_text": truncate_text(_context_text(evidence.context)),
      "group_or_step_context": _fieldset_or_group_text(evidence),
      "form_context": evidence.parent_form,
      "route_context": {
        "url": state.metadata.get("url") or state_context.get("url"),
        "route": state.metadata.get("route") or state_context.get("route"),
        "title": state.metadata.get("title") or state_context.get("title"),
      },
    },
    "visual_pairing": {
      "has_bounding_box": isinstance(control.get("bounding_box"), dict),
      "control_box": control.get("bounding_box") if isinstance(control.get("bounding_box"), dict) else {},
      "label_boxes": label_boxes,
      "screenshot_reference": f"states/{state.state_id}/screenshot.png",
      "pairing_evidence": "control_and_label_boxes" if label_boxes else "control_box_only",
    },
  }


def build_autocomplete_purpose_context(state: RunState, evidence: FormControlEvidence) -> dict[str, object]:
  control = evidence.control
  label_texts = [
    str(label.get("text") or "")
    for label in evidence.labels
    if str(label.get("text") or "")
  ]
  aria_labelledby_texts = [
    str(label.get("text") or "")
    for label in evidence.labels
    if label.get("relationship_type") == "labelledby" and str(label.get("text") or "")
  ]
  visible_label = (label_texts[0] if label_texts else "") or first_present_text(
    control,
    ("label", "wrapping_label"),
  )
  accessible_name = first_present_text(control, ("accessible_name", "aria_label", "aria_labelledby"))
  raw_autocomplete = first_present_text(control, ("autocomplete",))
  tokens = _autocomplete_tokens(raw_autocomplete)
  purpose_token = next((token for token in reversed(tokens) if token in _AUTOCOMPLETE_PURPOSES), "")
  recognized_purpose, token_category = _AUTOCOMPLETE_PURPOSES.get(purpose_token, ("", "unknown"))
  context_tokens = [token for token in tokens if token in _AUTOCOMPLETE_CONTEXT_TOKENS]
  section_tokens = [token for token in tokens if token.startswith("section-") and len(token) > len("section-")]
  recognized_tokens = set(_AUTOCOMPLETE_PURPOSES) | _AUTOCOMPLETE_CONTEXT_TOKENS | {"on", "off"}
  unknown_tokens = [
    token
    for token in tokens
    if token not in recognized_tokens and not token.startswith("section-")
  ]
  state_context = state.accessibility_context.get("state_context")
  if not isinstance(state_context, dict):
    state_context = {}
  label_boxes = [
    {
      "element_id": str(label.get("element_id") or ""),
      "selector": str(label.get("selector") or ""),
      "bounding_box": label.get("bounding_box") if isinstance(label.get("bounding_box"), dict) else {},
    }
    for label in evidence.labels
    if isinstance(label.get("bounding_box"), dict)
  ]
  return {
    "schema_version": "autocomplete_purpose_context_v1",
    "control": {
      "element_id": str(control.get("element_id") or ""),
      "selector": str(control.get("selector") or ""),
      "html": truncate_text(control.get("raw_html")),
      "tag": str(control.get("tag") or ""),
      "role": control.get("role"),
      "type": control.get("type"),
      "name": control.get("name"),
      "id": control.get("id"),
      "autocomplete": control.get("autocomplete"),
      "placeholder": control.get("placeholder"),
      "required": bool(control.get("required")),
      "value_state": _value_state(control),
    },
    "labeling": {
      "visible_label": visible_label,
      "computed_accessible_name": accessible_name,
      "label_element_text": " ".join(label_texts),
      "label_sources": _label_sources(evidence.labels),
      "aria_label": control.get("aria_label"),
      "aria_labelledby": control.get("aria_labelledby"),
      "aria_labelledby_text": " ".join(aria_labelledby_texts),
      "title": control.get("title"),
    },
    "field_purpose_evidence": {
      "visible_label": visible_label,
      "computed_accessible_name": accessible_name,
      "input_type": control.get("type"),
      "name": control.get("name"),
      "id": control.get("id"),
      "placeholder": control.get("placeholder"),
      "nearby_instructions": _nearby_instruction_text(evidence),
      "fieldset_or_group": _fieldset_or_group_text(evidence),
      "form_context": evidence.parent_form,
      "form_step_or_route_context": {
        "url": state.metadata.get("url") or state_context.get("url"),
        "route": state.metadata.get("route") or state_context.get("route"),
        "title": state.metadata.get("title") or state_context.get("title"),
        "section_heading": truncate_text(evidence.context.get("section_heading")),
      },
    },
    "autocomplete_evidence": {
      "raw_value": raw_autocomplete,
      "tokens": tokens,
      "section_tokens": section_tokens,
      "context_tokens": context_tokens,
      "purpose_token": purpose_token,
      "recognized_purpose": recognized_purpose,
      "token_category": token_category,
      "is_known_token": bool(purpose_token),
      "unknown_tokens": unknown_tokens,
    },
    "visual_pairing": {
      "has_bounding_box": isinstance(control.get("bounding_box"), dict),
      "control_box": control.get("bounding_box") if isinstance(control.get("bounding_box"), dict) else {},
      "label_boxes": label_boxes,
      "screenshot_reference": f"states/{state.state_id}/screenshot.png",
      "pairing_evidence": "control_and_label_boxes" if label_boxes else "control_box_only",
    },
  }


def _autocomplete_tokens(value: object) -> list[str]:
  return [token.lower() for token in str(value or "").split() if token]


def _relationships_for_control(state: RunState, control_id: str) -> list[dict[str, object]]:
  relationships = evidence_items(state, "relationships")
  return [
    relationship
    for relationship in relationships
    if relationship.get("from_element_id") == control_id or relationship.get("to_element_id") == control_id
  ]


def _compact_reference(ref: dict[str, Any], *, relationship: dict[str, object]) -> dict[str, object]:
  compacted: dict[str, object] = {
    "element_id": str(ref.get("element_id") or ""),
    "tag": str(ref.get("tag") or ""),
    "role": ref.get("role"),
    "selector": str(ref.get("selector") or ""),
    "text": truncate_text(ref.get("text")),
    "accessible_name": ref.get("accessible_name"),
    "reference_type": ref.get("reference_type"),
    "relationship_type": relationship.get("type"),
    "method": relationship.get("method"),
    "bounding_box": ref.get("bounding_box") if isinstance(ref.get("bounding_box"), dict) else {},
  }
  text_segments = ref.get("text_segments")
  if isinstance(text_segments, list):
    compacted["text_segments"] = [
      str(segment)
      for segment in text_segments
      if str(segment)
    ]
  return compacted


def _parent_form(control: dict[str, Any], forms_by_id: dict[str, dict[str, Any]]) -> dict[str, object]:
  raw_parent = control.get("parent_form")
  if isinstance(raw_parent, dict) and raw_parent.get("element_id"):
    form = forms_by_id.get(str(raw_parent.get("element_id")))
    return {
      "element_id": str(raw_parent.get("element_id") or ""),
      "selector": str(raw_parent.get("selector") or ""),
      "accessible_name": raw_parent.get("accessible_name") or (form or {}).get("accessible_name"),
    }
  return {}


def _context_text(context: dict[str, Any]) -> str:
  return first_present_text(
    context,
    (
      "nearby_text",
      "parent_text",
      "section_heading",
    ),
  )


def _nearby_instruction_text(evidence: FormControlEvidence) -> str:
  description_text = " ".join(
    str(description.get("text") or "")
    for description in evidence.descriptions
    if str(description.get("text") or "")
  )
  return truncate_text(
    " ".join(
      text
      for text in [
        _context_text(evidence.context),
        description_text,
      ]
      if text
    )
  )


def _fieldset_or_group_text(evidence: FormControlEvidence) -> str:
  structure = evidence.control.get("structure") if isinstance(evidence.control.get("structure"), dict) else {}
  nearest_heading = structure.get("nearest_heading") if isinstance(structure.get("nearest_heading"), dict) else {}
  parent_form_name = str(evidence.parent_form.get("accessible_name") or "")
  return truncate_text(" ".join(
    _dedupe_texts([
      nearest_heading.get("text"),
      evidence.context.get("section_heading") if isinstance(evidence.context, dict) else "",
      parent_form_name,
    ])
  ))


def _dedupe_texts(values: list[object]) -> list[str]:
  deduped: list[str] = []
  seen: set[str] = set()
  for value in values:
    text = truncate_text(value)
    if not text:
      continue
    key = _normalize_label_text(text)
    if key in seen:
      continue
    seen.add(key)
    deduped.append(text)
  return deduped


def _label_sources(labels: list[dict[str, object]]) -> list[dict[str, object]]:
  sources: list[dict[str, object]] = []
  for label in labels:
    source: dict[str, object] = {
      "element_id": str(label.get("element_id") or ""),
      "selector": str(label.get("selector") or ""),
      "text": str(label.get("text") or ""),
      "reference_type": label.get("reference_type"),
      "relationship_type": label.get("relationship_type"),
      "method": label.get("method"),
    }
    text_segments = label.get("text_segments")
    if isinstance(text_segments, list):
      source["text_segments"] = text_segments
    sources.append(source)
  return sources


def _contains_normalized(*, haystack: str, needle: str) -> bool | None:
  normalized_haystack = _normalize_label_text(haystack)
  normalized_needle = _normalize_label_text(needle)
  if not normalized_haystack or not normalized_needle:
    return None
  return normalized_needle in normalized_haystack


def _normalize_label_text(value: object) -> str:
  return "".join(char.lower() for char in str(value or "") if char.isalnum())


def _text_tokens(value: object) -> list[str]:
  normalized = "".join(
    char.lower() if char.isalnum() else " "
    for char in str(value or "")
  )
  return normalized.split()


def _normalize_text_words(value: object) -> str:
  return " ".join(_text_tokens(value))


def _visible_label_source(
  control: dict[str, Any],
  visible_label_sources: list[dict[str, object]],
) -> str:
  if any(label.get("method") == "for" for label in visible_label_sources):
    return "associated_label"
  if any(label.get("method") == "wrapper" for label in visible_label_sources):
    return "wrapping_label"
  if first_present_text(control, ("label",)):
    return "saved_label_text"
  if first_present_text(control, ("wrapping_label",)):
    return "saved_wrapping_label_text"
  return "unknown"


def _accessible_name_source(
  control: dict[str, Any],
  visible_label_sources: list[dict[str, object]],
) -> str:
  if first_present_text(control, ("aria_label",)):
    return "aria-label"
  if first_present_text(control, ("aria_labelledby",)):
    return "aria-labelledby"
  if visible_label_sources or first_present_text(control, ("label", "wrapping_label")):
    return "label"
  if first_present_text(control, ("title",)):
    return "title"
  if first_present_text(control, ("text",)):
    return "contents"
  return "unknown"


def _value_state(control: dict[str, Any]) -> str:
  has_value = control.get("has_value")
  if has_value is True:
    return "filled"
  if has_value is False:
    return "empty"
  return "unknown"


def _dedupe_refs(refs: list[dict[str, object]]) -> list[dict[str, object]]:
  deduped: list[dict[str, object]] = []
  seen: set[tuple[str, str, str]] = set()
  for ref in refs:
    key = (
      str(ref.get("bucket") or ""),
      str(ref.get("element_id") or ""),
      str(ref.get("relationship_role") or ""),
    )
    if key in seen:
      continue
    seen.add(key)
    deduped.append(ref)
  return deduped
