"""Build offline semantic candidate records from completed crawl artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import json

from .candidate_graph_context import build_candidate_graph_context
from .change_record import ChangeRecordIndex, attach_change_records
from .models import RunArtifacts, RunState
from .run_reader import load_run_artifacts
from .taxonomy import SUPPORTED_CANDIDATE_TYPES, require_supported_candidate_type
from .writer import write_candidate_outputs
from .rules.aria_state_mismatch import build_aria_state_mismatch_candidates
from .rules.autocomplete_purpose_mismatch import build_autocomplete_purpose_candidates
from .rules.button_label_mismatch import build_button_label_candidates
from .rules.error_message_mismatch import build_error_message_mismatch_candidates
from .rules.form_label_mismatch import build_form_label_candidates
from .rules.heading_not_descriptive import build_heading_not_descriptive_candidates
from .rules.image_alt_not_descriptive import build_image_alt_candidates
from .rules.landmark_purpose_mismatch import build_landmark_purpose_candidates
from .rules.lang_mismatch import build_lang_mismatch_candidates
from .rules.language_of_parts_mismatch import build_language_of_parts_mismatch_candidates
from .rules.link_text_mismatch import build_link_text_candidates
from .rules.page_title_not_descriptive import build_page_title_candidates
from .rules.table_header_association_mismatch import build_table_header_association_mismatch_candidates
from .rules.video_captions_inaccurate import build_video_caption_candidates
from .rules.widget_label_purpose_mismatch import build_widget_label_purpose_mismatch_candidates

CandidateRule = Callable[[RunArtifacts, RunState, dict[str, object]], list[dict[str, object]]]

_RULES: dict[str, CandidateRule] = {
  "image-alt-not-descriptive": build_image_alt_candidates,
  "lang-mismatch": build_lang_mismatch_candidates,
  "language-of-parts-mismatch": build_language_of_parts_mismatch_candidates,
  "link-text-mismatch": build_link_text_candidates,
  "button-label-mismatch": build_button_label_candidates,
  "form-label-mismatch": build_form_label_candidates,
  "widget-label-purpose-mismatch": build_widget_label_purpose_mismatch_candidates,
  "heading-not-descriptive": build_heading_not_descriptive_candidates,
  "landmark-purpose-mismatch": build_landmark_purpose_candidates,
  "page-title-not-descriptive": build_page_title_candidates,
  "autocomplete-purpose-mismatch": build_autocomplete_purpose_candidates,
  "aria-state-mismatch": build_aria_state_mismatch_candidates,
  "table-header-association-mismatch": build_table_header_association_mismatch_candidates,
  "error-message-mismatch": build_error_message_mismatch_candidates,
  "video-captions-inaccurate": build_video_caption_candidates,
}


@dataclass(frozen=True)
class CandidateBuildSummary:
  run_dir: Path
  output_dir: Path
  manifest: dict[str, object]


def build_semantic_candidates(
  run_dir: Path,
  *,
  candidate_types: list[str] | tuple[str, ...] | None = None,
) -> CandidateBuildSummary:
  run = load_run_artifacts(run_dir)
  requested_types = tuple(
    require_supported_candidate_type(candidate_type)
    for candidate_type in (candidate_types or SUPPORTED_CANDIDATE_TYPES)
  )

  missing_rules = sorted(set(requested_types) - set(_RULES))
  if missing_rules:
    raise ValueError(f"No candidate rule is registered for: {', '.join(missing_rules)}")

  candidates: list[dict[str, object]] = []
  no_available_evidence = 0
  for state in run.states:
    graph_context = build_candidate_graph_context(run, state)
    for candidate_type in requested_types:
      rule = _RULES[candidate_type]
      records = rule(run, state, graph_context)
      if not records:
        no_available_evidence += 1
      candidates.extend(records)

  # C2: change records per edge; backward candidates get one record per distinct incoming edge (max 3),
  # forward candidates get a change record per destination. Every candidate states its evidence scope.
  change_index = ChangeRecordIndex(run)
  candidates = attach_change_records(candidates, change_index)

  candidates.sort(
    key=lambda candidate: (
      str(candidate.get("candidate_type") or ""),
      str(candidate.get("state_id") or ""),
      str(candidate.get("candidate_id") or ""),
    )
  )

  skipped = {
    "missing_accessibility_context": run.missing_accessibility_context,
    "unsupported_schema_version": run.unsupported_schema_version,
    "no_available_evidence": no_available_evidence,
  }
  manifest = write_candidate_outputs(
    run_dir=run.run_dir,
    candidates=candidates,
    skipped=skipped,
    states_seen=len(run.states) + run.missing_accessibility_context + run.unsupported_schema_version,
    accessibility_context_seen=len(run.states),
  )
  change_records = change_index.all_records()
  with (run.run_dir / "candidates" / "change_records.jsonl").open("w", encoding="utf-8") as handle:
    for record in change_records:
      handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
  manifest["change_records"] = {"path": "change_records.jsonl", "count": len(change_records)}
  return CandidateBuildSummary(
    run_dir=run.run_dir,
    output_dir=run.run_dir / "candidates",
    manifest=manifest,
  )
