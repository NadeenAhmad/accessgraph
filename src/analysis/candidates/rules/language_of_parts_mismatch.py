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
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload
from .language_common import infer_language_signal, marker_matches_by_language
from .structure_common import compact_page

CANDIDATE_TYPE = "language-of-parts-mismatch"
LANGUAGE_OF_PARTS_CONTEXT_SCHEMA_VERSION = "language_of_parts_context_v1"


def build_language_of_parts_mismatch_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  for sample in evidence_items(state, "language_samples"):
    if not is_visible(sample):
      continue
    if _is_page_language_scope_sample(sample):
      continue
    text = first_present_text(sample, ("language_text", "text"))
    local_lang = truncate_text(sample.get("local_lang"), max_length=80)
    if not text or not local_lang:
      continue
    snippet = dom_snippet(sample)
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        primary_element_ref=element_ref("language_samples", sample),
        element_refs=[element_ref("language_samples", sample)],
        selection_reason=["visible_passage_with_local_language_declaration"],
        required_context=[
          "passage text",
          "local language declaration",
          "surrounding language context",
        ],
        evidence={
          "primary": {"language_sample": _compact_language_sample(sample)},
          "supporting": {
            "page": compact_page(state),
            "language_of_parts_context_v1": _build_language_of_parts_context(sample),
            "context": sample.get("context") if isinstance(sample.get("context"), dict) else {},
            "structure": sample.get("structure") if isinstance(sample.get("structure"), dict) else {},
          },
          "bounding_boxes": [bounding_box_ref(sample)],
          "dom_snippets": [snippet] if snippet else [],
        },
        graph_context=graph_context,
      )
    )
  return records


def _compact_language_sample(sample: dict[str, Any]) -> dict[str, object]:
  return {
    "element_id": str(sample.get("element_id") or ""),
    "tag": str(sample.get("tag") or ""),
    "role": sample.get("role"),
    "selector": str(sample.get("selector") or ""),
    "text": truncate_text(sample.get("language_text") or sample.get("text")),
    "local_lang": truncate_text(sample.get("local_lang"), max_length=80),
    "ancestor_lang": truncate_text(sample.get("ancestor_lang"), max_length=80),
    "root_lang": truncate_text(sample.get("root_lang"), max_length=80),
    "body_lang": truncate_text(sample.get("body_lang"), max_length=80),
    "page_lang": truncate_text(sample.get("page_lang"), max_length=80),
    "effective_lang": truncate_text(sample.get("effective_lang"), max_length=80),
  }


def _is_page_language_scope_sample(sample: dict[str, Any]) -> bool:
  tag = truncate_text(sample.get("tag"), max_length=30).casefold()
  selector = truncate_text(sample.get("selector"), max_length=240).casefold()
  xpath = truncate_text(sample.get("xpath"), max_length=240).casefold()
  if tag in {"html", "body"}:
    return True
  if _is_page_language_scope_selector(selector):
    return True
  return xpath in {"/html[1]", "/html[1]/body[1]"}


def _is_page_language_scope_selector(selector: str) -> bool:
  return selector in {"html", "body"} or selector.startswith(
    ("html#", "html.", "html[", "html:", "body#", "body.", "body[", "body:")
  )


def _build_language_of_parts_context(sample: dict[str, Any]) -> dict[str, object]:
  text = truncate_text(sample.get("language_text") or sample.get("text"), max_length=240)
  hint, markers = infer_language_signal(text)
  return {
    "schema_version": LANGUAGE_OF_PARTS_CONTEXT_SCHEMA_VERSION,
    "declared_language": {
      "local_lang": truncate_text(sample.get("local_lang"), max_length=80),
      "ancestor_lang": truncate_text(sample.get("ancestor_lang"), max_length=80),
      "root_lang": truncate_text(sample.get("root_lang"), max_length=80),
      "body_lang": truncate_text(sample.get("body_lang"), max_length=80),
      "page_lang": truncate_text(sample.get("page_lang"), max_length=80),
      "effective_lang": truncate_text(sample.get("effective_lang"), max_length=80),
    },
    "passage_text_evidence": {
      "text_excerpt": text,
      "word_count": _as_int(sample.get("word_count")),
      "strongest_marker_language_hint": hint,
      "signal_method": "lightweight_marker_matching",
      "matched_markers": markers[:8],
      "matched_markers_by_language": {
        language: values
        for language, values in marker_matches_by_language(text).items()
        if values
      },
    },
    "local_context": sample.get("context") if isinstance(sample.get("context"), dict) else {},
  }


def _as_int(value: object) -> int | None:
  try:
    return int(str(value))
  except (TypeError, ValueError):
    return None
