from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..evidence_helpers import evidence_items, is_visible, truncate_text
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload
from .language_common import infer_language_signal, marker_matches_by_language

CANDIDATE_TYPE = "lang-mismatch"
_MAX_REPRESENTATIVE_SAMPLES = 2
_MAX_SCOPED_SAMPLES = 2
_SAMPLE_TEXT_LIMIT = 110
_BODY_TEXT_CONTEXT_LIMIT = 180
_TAG_PRIORITY = {
  "h1": 0,
  "h2": 0,
  "h3": 0,
  "h4": 0,
  "h5": 0,
  "h6": 0,
  "p": 1,
  "blockquote": 1,
  "figcaption": 1,
  "label": 2,
  "legend": 2,
  "li": 2,
  "td": 2,
  "th": 2,
}


def build_lang_mismatch_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  page = state.accessibility_context.get("page")
  if not isinstance(page, dict):
    return []

  html_lang = truncate_text(page.get("html_lang"))
  document_lang = truncate_text(page.get("document_lang"))
  body_lang = truncate_text(page.get("body_lang"))
  page_lang = truncate_text(page.get("page_lang"))
  body_text_sample = truncate_text(page.get("body_text_sample"))
  if not (html_lang or document_lang or body_lang or page_lang):
    return []
  # W4A round 4: a page whose only text is a text alternative (ACT ucwvc8) still has text to compare
  if not body_text_sample and not truncate_text(page.get("text_without_own_lang")):
    return []

  return [
    build_candidate_payload(
      run=run,
      state=state,
      candidate_type=CANDIDATE_TYPE,
      element_refs=[],
      selection_reason=["page_language_declaration_with_visible_text_evidence"],
      required_context=[
        "declared page language",
        "visible page text sample",
        "page purpose context",
      ],
      evidence={
        "primary": {
          "page": _compact_page(page, state),
        },
        "supporting": {
          "language_declaration": {
            "html_lang": html_lang,
            "document_lang": document_lang,
            "body_lang": body_lang,
            "page_lang": page_lang,
          },
          "body_text_sample": body_text_sample,
          "body_text_length": _body_text_length(page.get("body_text_length")),
          # 3.1.1 concerns the text that has no language of its own (W4A dev round 2)
          "text_without_own_lang": truncate_text(page.get("text_without_own_lang")),
          "lang_mismatch_context_v1": _lang_mismatch_context(
            state,
            page=page,
            body_text_sample=body_text_sample,
          ),
        },
        "bounding_boxes": [],
        "dom_snippets": [],
      },
      graph_context=graph_context,
    )
  ]


def _compact_page(page: dict[str, Any], state: RunState) -> dict[str, object]:
  return {
    "url": truncate_text(page.get("url") or state.metadata.get("url") or ""),
    "title": truncate_text(page.get("title")),
    "document_lang": truncate_text(page.get("document_lang")),
    "html_lang": truncate_text(page.get("html_lang")),
    "body_lang": truncate_text(page.get("body_lang")),
    "page_lang": truncate_text(page.get("page_lang")),
    "body_text_sample": truncate_text(page.get("body_text_sample")),
    "body_text_length": _body_text_length(page.get("body_text_length")),
  }


def _body_text_length(value: object) -> int | None:
  if isinstance(value, int):
    return value
  try:
    return int(str(value))
  except (TypeError, ValueError):
    return None


def _lang_mismatch_context(
  state: RunState,
  *,
  page: dict[str, Any],
  body_text_sample: str,
) -> dict[str, object]:
  samples = _visible_language_samples(state)
  representative_samples = _representative_text_samples(samples)
  classified_count = sum(
    1 for sample in representative_samples if sample.get("language_hint")
  )
  body_hint, _ = infer_language_signal(body_text_sample)
  focused_acquisition = (
    state.metadata.get("focused_acquisition")
    if isinstance(state.metadata.get("focused_acquisition"), dict)
    else {}
  )
  return {
    "schema_version": "lang_mismatch_context_v1",
    "declared_page_language": _compact_non_empty(
      {
        "html_lang": truncate_text(page.get("html_lang"), max_length=80),
        "document_lang": truncate_text(page.get("document_lang"), max_length=80),
        "xml_lang": truncate_text(page.get("xml_lang"), max_length=80),
        "body_lang": truncate_text(page.get("body_lang"), max_length=80),
        "page_lang": truncate_text(page.get("page_lang"), max_length=80),
        "title": truncate_text(page.get("title") or state.metadata.get("title")),
        "route": _state_route(page, state),
      }
    ),
    "page_text_evidence": {
      "body_text_excerpt": truncate_text(
        body_text_sample, max_length=_BODY_TEXT_CONTEXT_LIMIT
      ),
      "body_text_length": _body_text_length(page.get("body_text_length")),
      "strongest_marker_language_hint": body_hint,
      "signal_method": "lightweight_marker_matching",
      "matched_markers_by_language": {
        language: markers
        for language, markers in marker_matches_by_language(body_text_sample).items()
        if markers
      },
      "representative_sample_count": len(representative_samples),
      "classified_sample_count": classified_count,
      "unclassified_sample_count": len(representative_samples) - classified_count,
    },
    "representative_text_samples": representative_samples,
    "local_language_scope": _local_language_scope(samples),
    "state_context": _compact_non_empty(
      {
        "state_id": state.state_id,
        "route": _state_route(page, state),
        "benchmark_state": truncate_text(
          focused_acquisition.get("benchmark_state_id"), max_length=80
        ),
      }
    ),
  }


def _visible_language_samples(state: RunState) -> list[dict[str, Any]]:
  samples: list[dict[str, Any]] = []
  for index, sample in enumerate(evidence_items(state, "language_samples")):
    tag = truncate_text(sample.get("tag"), max_length=30).casefold()
    text = truncate_text(sample.get("language_text") or sample.get("text"), max_length=2000)
    if not is_visible(sample) or tag in {"html", "body"} or len(text.split()) < 2:
      continue
    samples.append({**sample, "_source_index": index, "_normalized_text": text})
  return samples


def _representative_text_samples(samples: list[dict[str, Any]]) -> list[dict[str, object]]:
  ranked = sorted(
    samples,
    key=lambda sample: (
      _TAG_PRIORITY.get(truncate_text(sample.get("tag"), max_length=30).casefold(), 3),
      int(sample.get("_source_index") or 0),
    ),
  )
  headings = [sample for sample in ranked if _is_heading_sample(sample)]
  non_headings = sorted(
    (sample for sample in ranked if not _is_heading_sample(sample)),
    key=lambda sample: (
      -len(infer_language_signal(sample.get("_normalized_text"))[1]),
      -len(str(sample.get("_normalized_text") or "").split()),
      int(sample.get("_source_index") or 0),
    ),
  )
  ordered = [*headings[:1], *non_headings, *headings[1:]]
  records: list[dict[str, object]] = []
  seen_text: set[str] = set()
  for sample in ordered:
    text = str(sample.get("_normalized_text") or "")
    normalized = text.casefold()
    if not normalized or normalized in seen_text:
      continue
    seen_text.add(normalized)
    hint, markers = infer_language_signal(text)
    excerpt = truncate_text(text, max_length=_SAMPLE_TEXT_LIMIT)
    record: dict[str, object] = {
      "text_excerpt": excerpt,
      "selector": truncate_text(sample.get("selector"), max_length=240),
      "tag": truncate_text(sample.get("tag"), max_length=30),
      "is_visible": is_visible(sample),
      "declared_language_scope": _compact_non_empty(
        {
          "root_lang": truncate_text(sample.get("root_lang"), max_length=80),
          "body_lang": truncate_text(sample.get("body_lang"), max_length=80),
          "page_lang": truncate_text(sample.get("page_lang"), max_length=80),
          "local_lang": truncate_text(sample.get("local_lang"), max_length=80),
          "ancestor_lang": truncate_text(sample.get("ancestor_lang"), max_length=80),
          "effective_declared_lang": truncate_text(
            sample.get("effective_lang"), max_length=80
          ),
          "source": _declared_language_source(sample),
        }
      ),
    }
    if len(text) > len(excerpt):
      record["truncated"] = True
    if hint:
      record["language_hint"] = hint
      record["matched_markers"] = markers[:8]
    if isinstance(sample.get("bounding_box"), dict) and sample.get("bounding_box"):
      record["bounding_box"] = sample["bounding_box"]
    records.append(record)
    if len(records) >= _MAX_REPRESENTATIVE_SAMPLES:
      break
  return records


def _is_heading_sample(sample: dict[str, Any]) -> bool:
  tag = truncate_text(sample.get("tag"), max_length=30).casefold()
  return tag in {"h1", "h2", "h3", "h4", "h5", "h6"}


def _local_language_scope(samples: list[dict[str, Any]]) -> dict[str, object]:
  local_samples = [
    sample
    for sample in samples
    if truncate_text(sample.get("local_lang"), max_length=80)
  ]
  ancestor_samples = [
    sample for sample in samples if truncate_text(sample.get("ancestor_lang"), max_length=80)
  ]
  unscoped_samples = [
    sample
    for sample in samples
    if not truncate_text(sample.get("local_lang"), max_length=80)
    and not truncate_text(sample.get("ancestor_lang"), max_length=80)
  ]
  declared_language_source_counts = _count_non_empty(
    _declared_language_source(sample) for sample in samples
  )
  effective_declared_language_counts = _count_non_empty(
    truncate_text(sample.get("effective_lang"), max_length=80) for sample in samples
  )
  scoped_samples: list[dict[str, object]] = []
  for sample in samples:
    local_lang = truncate_text(sample.get("local_lang"), max_length=80)
    ancestor_lang = truncate_text(sample.get("ancestor_lang"), max_length=80)
    if not (local_lang or ancestor_lang):
      continue
    scoped_samples.append(
      {
        "tag": truncate_text(sample.get("tag"), max_length=30),
        "selector": truncate_text(sample.get("selector"), max_length=240),
        "text_excerpt": truncate_text(
          sample.get("_normalized_text"), max_length=_SAMPLE_TEXT_LIMIT
        ),
        "local_lang": local_lang,
        "ancestor_lang": ancestor_lang,
        "effective_or_inherited_lang": truncate_text(
          sample.get("effective_lang"), max_length=80
        ),
      }
    )
    if len(scoped_samples) >= _MAX_SCOPED_SAMPLES:
      break
  return {
    "visible_sample_count": len(samples),
    "samples_with_local_lang_count": len(local_samples),
    "samples_with_ancestor_lang_count": len(ancestor_samples),
    "samples_without_local_or_ancestor_lang_count": len(unscoped_samples),
    "samples_inheriting_root_declared_lang_count": (
      declared_language_source_counts.get("root", 0)
    ),
    "samples_with_explicit_local_or_ancestor_lang_count": len(
      [
        sample
        for sample in samples
        if truncate_text(sample.get("local_lang"), max_length=80)
        or truncate_text(sample.get("ancestor_lang"), max_length=80)
      ]
    ),
    "declared_language_source_counts": declared_language_source_counts,
    "effective_declared_language_counts": effective_declared_language_counts,
    **({"scoped_samples": scoped_samples} if scoped_samples else {}),
  }


def _declared_language_source(sample: dict[str, Any]) -> str:
  if truncate_text(sample.get("local_lang"), max_length=80):
    return "local"
  if truncate_text(sample.get("ancestor_lang"), max_length=80):
    return "ancestor"
  if truncate_text(sample.get("root_lang"), max_length=80):
    return "root"
  if truncate_text(sample.get("page_lang"), max_length=80):
    return "page"
  if truncate_text(sample.get("effective_lang"), max_length=80):
    return "effective"
  return ""


def _count_non_empty(values: Iterable[object]) -> dict[str, int]:
  counts: dict[str, int] = {}
  for value in values:
    normalized = truncate_text(value, max_length=80)
    if normalized:
      counts[normalized] = counts.get(normalized, 0) + 1
  return dict(sorted(counts.items()))


def _state_route(page: dict[str, Any], state: RunState) -> str:
  return truncate_text(
    page.get("route")
    or state.metadata.get("route")
    or state.accessibility_context.get("route")
    or "",
    max_length=240,
  )


def _compact_non_empty(raw: dict[str, object]) -> dict[str, object]:
  compact: dict[str, object] = {}
  for key, value in raw.items():
    if value is None:
      continue
    if isinstance(value, str) and not value:
      continue
    if isinstance(value, dict) and not value:
      continue
    compact[key] = value
  return compact
