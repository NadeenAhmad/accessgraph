from __future__ import annotations

from typing import Any

from ..destination_state_context import saved_html_attributes
from ..evidence_helpers import (
  bounding_box_ref,
  dom_snippet,
  element_ref,
  evidence_items,
  first_present_text,
  is_visible,
  truncate_text,
)
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload

CANDIDATE_TYPE = "image-alt-not-descriptive"
IMAGE_ALT_CONTEXT_SCHEMA_VERSION = "image_alt_context_v1"


def build_image_alt_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  for image in evidence_items(state, "images"):
    if not is_visible(image):
      continue
    name = first_present_text(image, ("alt", "accessible_name", "aria_label", "title", "text"))
    if not _has_present_text_alternative(image) or not name:
      continue
    snippet = dom_snippet(image)
    evidence = {
      "primary": {
        "image": _compact_image(image),
      },
      "supporting": {
        "context": image.get("context") if isinstance(image.get("context"), dict) else {},
        "structure": image.get("structure") if isinstance(image.get("structure"), dict) else {},
        "image_alt_context_v1": _build_image_alt_context(state, image),
      },
      "bounding_boxes": [bounding_box_ref(image)],
      "dom_snippets": [snippet] if snippet else [],
    }
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        element_refs=[element_ref("images", image)],
        selection_reason=["visible_image_with_text_alternative_and_context"],
        required_context=["visual image context", "nearby text context", "image purpose"],
        evidence=evidence,
        graph_context=graph_context,
      )
    )
  records.extend(_hidden_image_candidates(run, state, graph_context))
  records.extend(_lookalike_text_candidates(run, state, graph_context))
  return records


def _lookalike_text_candidates(run: RunArtifacts, state: RunState, graph_context: dict[str, object]) -> list[dict[str, object]]:
  """W4A round 5 (WCAG 1.1.1, Understanding: characters used for their visual shape are non-text content): text whose
  words mix Latin letters with look-alike Greek or Cyrillic letters (recorded as `lookalike_text`). Each word is
  spelled out letter by letter with its alphabet, so the judge sees what assistive technologies read."""
  import unicodedata
  records: list[dict[str, object]] = []
  for item in evidence_items(state, "lookalike_text"):
    words = [str(w) for w in item.get("words") or [] if str(w).strip()][:5]
    if not words:
      continue
    spelled = [{"word": w, "letters": [f"{ch} ({unicodedata.name(ch, 'unknown').split(' ')[0].title()})" for ch in w]}
               for w in words]
    snippet = dom_snippet(item)
    records.append(build_candidate_payload(
      run=run, state=state, candidate_type=CANDIDATE_TYPE, element_refs=[element_ref("lookalike_text", item)],
      selection_reason=["text_with_lookalike_letters_from_another_alphabet"],
      required_context=["the word sighted users see", "what assistive technologies read", "any text alternative"],
      evidence={
        "primary": {"text_element": {"tag": item.get("tag"), "text": item.get("text"),
                                     "accessible_name": item.get("accessible_name"), "aria_label": item.get("aria_label")},
                    "lookalike_characters": spelled},
        "supporting": {"context": item.get("context") if isinstance(item.get("context"), dict) else {},
                       "structure": item.get("structure") if isinstance(item.get("structure"), dict) else {}},
        "bounding_boxes": [bounding_box_ref(item)],
        "dom_snippets": [snippet] if snippet else [],
      },
      graph_context=graph_context,
    ))
  return records


def _hidden_image_candidates(run: RunArtifacts, state: RunState, graph_context: dict[str, object]) -> list[dict[str, object]]:
  """W4A round 4: images shown to sighted users but hidden from assistive technologies or marked decorative
  (recorded as `hidden_images`); the judge decides whether they carry information (WCAG 1.1.1). An image inside a
  link or button that has its own name is the usual correct pattern (the control is named) and is skipped."""
  records: list[dict[str, object]] = []
  for image in evidence_items(state, "hidden_images"):
    if image.get("inside_control") and truncate_text(image.get("control_name")):
      continue
    snippet = dom_snippet(image)
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        element_refs=[element_ref("hidden_images", image)],
        selection_reason=["visible_image_hidden_from_assistive_technology"],
        required_context=["visual image content", "nearby text context", "whether the image carries information"],
        evidence={
          "primary": {
            "image": {**_compact_image(image), "hidden_reason": str(image.get("hidden_reason") or ""),
                      "exposed_to_assistive_technology": False},
          },
          "supporting": {
            "context": image.get("context") if isinstance(image.get("context"), dict) else {},
            "structure": image.get("structure") if isinstance(image.get("structure"), dict) else {},
            "image_alt_context_v1": _build_image_alt_context(state, image),
          },
          "bounding_boxes": [bounding_box_ref(image)],
          "dom_snippets": [snippet] if snippet else [],
        },
        graph_context=graph_context,
      )
    )
  return records


def _compact_image(image: dict[str, Any]) -> dict[str, object]:
  return {
    "element_id": str(image.get("element_id") or ""),
    "tag": str(image.get("tag") or ""),
    "role": image.get("role"),
    "selector": str(image.get("selector") or ""),
    "text": str(image.get("text") or ""),
    "accessible_name": image.get("accessible_name"),
    "alt": image.get("alt"),
    "aria_label": image.get("aria_label"),
    "aria_labelledby": image.get("aria_labelledby"),
    "title": image.get("title"),
    "src": str(image.get("src") or ""),
    "text_alternative_present": _has_present_text_alternative(image),
  }


def _has_present_text_alternative(image: dict[str, Any]) -> bool:
  attrs = saved_html_attributes(image.get("raw_html"))
  if truncate_text(image.get("alt")) or truncate_text(attrs.get("alt")):
    return True
  tag = str(image.get("tag") or "").strip().lower()
  if tag == "img":
    return bool(first_present_text(image, ("aria_label", "aria_labelledby", "title")))
  return bool(first_present_text(image, ("accessible_name", "aria_label", "aria_labelledby", "title", "text")))


def _build_image_alt_context(state: RunState, image: dict[str, Any]) -> dict[str, object]:
  context = image.get("context") if isinstance(image.get("context"), dict) else {}
  structure = image.get("structure") if isinstance(image.get("structure"), dict) else {}
  nearest_heading = (
    structure.get("nearest_heading")
    if isinstance(structure.get("nearest_heading"), dict)
    else {}
  )
  nearest_landmark = (
    structure.get("nearest_landmark")
    if isinstance(structure.get("nearest_landmark"), dict)
    else {}
  )
  bounding_box = image.get("bounding_box") if isinstance(image.get("bounding_box"), dict) else {}
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  focused = (
    state.metadata.get("focused_acquisition")
    if isinstance(state.metadata.get("focused_acquisition"), dict)
    else {}
  )

  return {
    "schema_version": IMAGE_ALT_CONTEXT_SCHEMA_VERSION,
    "target_image": {
      "element_id": str(image.get("element_id") or ""),
      "tag": str(image.get("tag") or ""),
      "role": image.get("role"),
      "selector": str(image.get("selector") or ""),
      "xpath": str(image.get("xpath") or ""),
      "src": truncate_text(image.get("src")),
      "current_src": truncate_text(image.get("current_src")),
      "alt": truncate_text(image.get("alt")),
      "text_alternative_present": _has_present_text_alternative(image),
      "accessible_name": truncate_text(image.get("accessible_name")),
      "aria_label": truncate_text(image.get("aria_label")),
      "aria_labelledby": truncate_text(image.get("aria_labelledby")),
      "title": truncate_text(image.get("title")),
      "is_visible": image.get("visible") is not False,
      "bounding_box": bounding_box,
    },
    "text_alternative_sources": {
      "alt": truncate_text(image.get("alt")),
      "accessible_name": truncate_text(image.get("accessible_name")),
      "aria_label": truncate_text(image.get("aria_label")),
      "aria_labelledby": truncate_text(image.get("aria_labelledby")),
      "title": truncate_text(image.get("title")),
      "text": truncate_text(image.get("text")),
      "present": _has_present_text_alternative(image),
    },
    "local_context": {
      "nearby_text": truncate_text(context.get("nearby_text")),
      "parent_text": truncate_text(context.get("parent_text")),
      "section_heading": truncate_text(context.get("section_heading")),
      "nearest_heading": _structure_label(nearest_heading),
      "nearest_landmark": _structure_label(nearest_landmark),
    },
    "structure": {
      "parent_tag": structure.get("parent_tag"),
      "parent_role": structure.get("parent_role"),
      "ancestor_roles": (
        structure.get("ancestor_roles")
        if isinstance(structure.get("ancestor_roles"), list)
        else []
      ),
      "parent_form": (
        structure.get("parent_form")
        if isinstance(structure.get("parent_form"), dict)
        else structure.get("parent_form")
      ),
      "link_or_button_context": _link_or_button_context(structure),
    },
    "state_context": {
      "state_id": state.state_id,
      "route": str(page.get("route") or state.metadata.get("route") or ""),
      "title": str(page.get("title") or state.metadata.get("title") or ""),
      "benchmark_state": truncate_text(focused.get("benchmark_state_id"), max_length=80),
    },
    "visual_reference": {
      "bounding_box": bounding_box,
      "state_screenshot_available": bool(state.metadata.get("screenshot")),
      "target_crop_supported": bool(bounding_box),
      "highlighted_state_supported": bool(bounding_box),
    },
  }


def _structure_label(item: dict[str, Any]) -> str:
  return truncate_text(
    item.get("accessible_name")
    or item.get("text")
    or item.get("aria_label")
    or item.get("selector")
  )


def _link_or_button_context(structure: dict[str, Any]) -> object:
  for key in ("nearest_link", "nearest_button", "parent_link", "parent_button"):
    value = structure.get(key)
    if isinstance(value, dict):
      return {
        "kind": key,
        "selector": str(value.get("selector") or ""),
        "text": truncate_text(value.get("text")),
        "accessible_name": truncate_text(value.get("accessible_name")),
        "href": truncate_text(value.get("href")),
      }
  return None
