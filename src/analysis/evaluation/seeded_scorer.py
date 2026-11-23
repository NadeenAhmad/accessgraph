from __future__ import annotations

import json
import platform
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.analysis.candidates.run_reader import load_run_artifacts
from src.analysis.evaluation.benchmark_registry import load_benchmark_registry
from src.analysis.evaluation.reader import load_confirmation_runs

SCHEMA_VERSION = "1"
GENERATOR_NAME = "seeded_experiment_scorer"
GENERATOR_VERSION = "1"
CONFIRMATION_GENERATOR_NAME = "seeded_confirmation_scorer"
CONFIRMATION_GENERATOR_VERSION = "1"
DEFAULT_REGISTRY_PATH = Path("benchmarks/registry/benchmark-case-registry.json")
ALLOWED_PRIMARY_EVIDENCE_KEYS = {
  "button",
  "form_control",
  "heading",
  "image",
  "landmark",
  "landmark_structure",
  "link",
  "widget",
  "semantic_element",
  "aria_state",
  "table",
  "error_message",
  "language_sample",
  "positive_tabindex_focusables",
  "page",
  "structural_element",
  "focus_traversal",
  "visual_cue",
  "video",
}
ARIA_STATE_ATTRIBUTE_FIELDS = {
  "aria_checked",
  "aria_current",
  "aria_expanded",
  "aria_pressed",
  "aria_selected",
}


@dataclass(frozen=True)
class SeededScorerOptions:
  run_dir: Path
  config_id: str
  registry_path: Path = DEFAULT_REGISTRY_PATH
  candidates_path: Path | None = None
  output_dir: Path | None = None
  score_run_id: str | None = None
  overwrite: bool = False
  argv: tuple[str, ...] = ()
  cwd: Path | None = None


@dataclass(frozen=True)
class SeededConfirmationScorerOptions:
  run_dir: Path
  config_id: str
  confirmation_run_id: str
  registry_path: Path = DEFAULT_REGISTRY_PATH
  candidates_path: Path | None = None
  output_dir: Path | None = None
  score_run_id: str | None = None
  candidate_id_output_path: Path | None = None
  overwrite: bool = False
  argv: tuple[str, ...] = ()
  cwd: Path | None = None


@dataclass(frozen=True)
class SeededScorerResult:
  score_run_id: str
  output_dir: Path
  manifest: dict[str, object]
  summary: dict[str, object]


@dataclass(frozen=True)
class SeededConfirmationScorerResult:
  score_run_id: str
  output_dir: Path
  manifest: dict[str, object]
  summary: dict[str, object]


@dataclass(frozen=True)
class CandidateRecord:
  record: dict[str, Any]
  line_number: int
  source_path: Path


def score_seeded_experiment(
  options: SeededScorerOptions,
  *,
  generated_at: datetime | None = None,
) -> SeededScorerResult:
  generated_at_dt = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  run_dir = options.run_dir.resolve()
  registry_path = options.registry_path.resolve()
  candidates_path = (options.candidates_path or (run_dir / "candidates" / "candidates.jsonl")).resolve()

  run = load_run_artifacts(run_dir)
  registry = _load_registry(registry_path)
  config, seeds = _resolve_config(registry, options.config_id)
  candidates = _load_candidates(candidates_path)

  score_run_id = options.score_run_id or _generate_score_run_id(generated_at=generated_at_dt)
  output_dir = (options.output_dir or (run_dir / "evaluation" / "seeded_recovery" / score_run_id)).resolve()
  _validate_output_dir(output_dir, run_dir=run_dir)
  _prepare_output_dir(output_dir, overwrite=options.overwrite)

  results = [
    _score_seed(seed, run_states=run.states, candidates=candidates)
    for seed in seeds
  ]
  summary = _build_summary(
    config=config,
    config_id=options.config_id,
    results=results,
    run_dir=run_dir,
    registry_path=registry_path,
    candidates_path=candidates_path,
    score_run_id=score_run_id,
    output_dir=output_dir,
    generated_at=generated_at_dt,
  )
  manifest = _build_manifest(
    options=options,
    summary=summary,
    score_run_id=score_run_id,
    run_dir=run_dir,
    registry_path=registry_path,
    candidates_path=candidates_path,
    output_dir=output_dir,
    generated_at=generated_at_dt,
  )
  _write_outputs(output_dir=output_dir, summary=summary, manifest=manifest)
  return SeededScorerResult(
    score_run_id=score_run_id,
    output_dir=output_dir,
    manifest=manifest,
    summary=summary,
  )


def score_seeded_confirmations(
  options: SeededConfirmationScorerOptions,
  *,
  generated_at: datetime | None = None,
) -> SeededConfirmationScorerResult:
  generated_at_dt = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  run_dir = options.run_dir.resolve()
  registry_path = options.registry_path.resolve()
  candidates_path = (options.candidates_path or (run_dir / "candidates" / "candidates.jsonl")).resolve()

  run = load_run_artifacts(run_dir)
  registry = _load_registry(registry_path)
  config, seeds = _resolve_config(registry, options.config_id)
  candidates = _load_candidates(candidates_path)
  confirmation_run = load_confirmation_runs(run_dir, (options.confirmation_run_id,))[0]

  score_run_id = options.score_run_id or _generate_confirmation_score_run_id(generated_at=generated_at_dt)
  output_dir = (options.output_dir or (run_dir / "evaluation" / "seeded_confirmation" / score_run_id)).resolve()
  _validate_output_dir(output_dir, run_dir=run_dir)
  if options.candidate_id_output_path:
    _validate_private_output_file(
      options.candidate_id_output_path,
      run_dir=run_dir,
      overwrite=options.overwrite,
    )
  _prepare_output_dir(output_dir, overwrite=options.overwrite)

  candidate_results = [
    _score_seed(seed, run_states=run.states, candidates=candidates)
    for seed in seeds
  ]
  confirmation_records_by_candidate_id = _confirmation_records_by_candidate_id(confirmation_run.records)
  results = [
    _score_seed_confirmation(
      seed=seed,
      candidate_result=candidate_result,
      confirmation_records_by_candidate_id=confirmation_records_by_candidate_id,
      confirmation_run_id=options.confirmation_run_id,
    )
    for seed, candidate_result in zip(seeds, candidate_results, strict=True)
  ]
  summary = _build_confirmation_summary(
    config=config,
    config_id=options.config_id,
    confirmation_run_id=options.confirmation_run_id,
    confirmation_manifest=confirmation_run.manifest,
    confirmation_records=confirmation_run.records,
    results=results,
    run_dir=run_dir,
    registry_path=registry_path,
    candidates_path=candidates_path,
    confirmation_dir=confirmation_run.confirmation_dir,
    confirmations_path=confirmation_run.confirmations_path,
    score_run_id=score_run_id,
    output_dir=output_dir,
    candidate_id_output_path=options.candidate_id_output_path,
    generated_at=generated_at_dt,
  )
  manifest = _build_confirmation_manifest(
    options=options,
    summary=summary,
    score_run_id=score_run_id,
    run_dir=run_dir,
    registry_path=registry_path,
    candidates_path=candidates_path,
    confirmation_dir=confirmation_run.confirmation_dir,
    confirmations_path=confirmation_run.confirmations_path,
    output_dir=output_dir,
    generated_at=generated_at_dt,
  )
  _write_confirmation_outputs(
    output_dir=output_dir,
    summary=summary,
    manifest=manifest,
    candidate_id_output_path=options.candidate_id_output_path,
    overwrite=options.overwrite,
  )
  return SeededConfirmationScorerResult(
    score_run_id=score_run_id,
    output_dir=output_dir,
    manifest=manifest,
    summary=summary,
  )


def _score_seed(
  seed: dict[str, Any],
  *,
  run_states: tuple[Any, ...],
  candidates: tuple[CandidateRecord, ...],
) -> dict[str, object]:
  warnings: list[str] = []
  seed_id = str(seed.get("variant_id") or seed.get("seed_id") or "")
  candidate_type = _expected_candidate_type(seed)
  if not seed_id:
    warnings.append("Seed record is missing variant_id.")
  if not candidate_type:
    warnings.append("Seed record is missing expected candidate type.")

  if warnings:
    return {
      "seed_id": seed_id,
      "candidate_type": candidate_type,
      "status": "expectation_invalid",
      "state_status": "not_applicable",
      "evidence_status": "not_applicable",
      "candidate_status": "not_applicable",
      "confirmation_status": "not_scored",
      "report_status": "not_scored",
      "matched_states": [],
      "matched_evidence": [],
      "matched_candidates": [],
      "warnings": warnings,
    }

  expected_state = _expected_state(seed)
  expected_evidence_items = _expected_evidence_items(seed)
  has_expected_state_constraint = _has_expected_state_constraint(expected_state)
  matched_states = _matched_states(run_states, expected_state)
  matched_state_ids = {str(item["state_id"]) for item in matched_states}

  state_status = "state_acquired" if matched_states else "state_not_acquired"
  if has_expected_state_constraint and not matched_states:
    matched_evidence: list[dict[str, object]] = []
    matched_candidates: list[dict[str, object]] = []
    evidence_status = "not_applicable"
    candidate_status = "candidate_missing"
    status = "state_not_acquired"
  else:
    states_for_evidence = [
      state
      for state in run_states
      if not matched_state_ids or state.state_id in matched_state_ids
    ]
    matched_evidence_groups = [
      _matched_evidence(states_for_evidence, expected_evidence)
      for expected_evidence in expected_evidence_items
    ]
    matched_evidence = _dedupe_match_records(
      item
      for group in matched_evidence_groups
      for item in group
    )
    evidence_status = (
      "evidence_found"
      if matched_evidence_groups and all(matched_evidence_groups)
      else "evidence_missing"
    )
    matched_candidate_groups = []
    if evidence_status == "evidence_found":
      for expected_evidence, evidence_group in zip(
        expected_evidence_items,
        matched_evidence_groups,
        strict=True,
      ):
        matched_evidence_state_ids = {
          str(item["state_id"])
          for item in evidence_group
        }
        matched_candidate_groups.append(
          _matched_candidates(
            candidates,
            seed=seed,
            expected_state=expected_state,
            expected_evidence=expected_evidence,
            matched_state_ids=matched_state_ids,
            matched_evidence_state_ids=matched_evidence_state_ids,
          )
        )
    matched_candidates = _dedupe_match_records(
      item
      for group in matched_candidate_groups
      for item in group
    )
    candidate_status = (
      "candidate_recovered"
      if matched_candidate_groups and all(matched_candidate_groups)
      else "candidate_missing"
    )
    status = _overall_status(
      state_status=state_status,
      evidence_status=evidence_status,
      candidate_status=candidate_status,
    )

  return {
    "seed_id": seed_id,
    "candidate_type": candidate_type,
    "status": status,
    "state_status": state_status,
    "evidence_status": evidence_status,
    "candidate_status": candidate_status,
    "confirmation_status": "not_scored",
    "report_status": "not_scored",
    "matched_states": matched_states,
    "matched_evidence": matched_evidence,
    "matched_candidates": matched_candidates,
    "warnings": warnings,
  }


def _score_seed_confirmation(
  *,
  seed: dict[str, Any],
  candidate_result: dict[str, object],
  confirmation_records_by_candidate_id: dict[str, dict[str, Any]],
  confirmation_run_id: str,
) -> dict[str, object]:
  matched_candidates = (
    candidate_result.get("matched_candidates")
    if isinstance(candidate_result.get("matched_candidates"), list)
    else []
  )
  matched_candidate_ids = [
    str(candidate.get("candidate_id") or "")
    for candidate in matched_candidates
    if isinstance(candidate, dict) and str(candidate.get("candidate_id") or "").strip()
  ]
  matched_confirmation_records = [
    confirmation_records_by_candidate_id[candidate_id]
    for candidate_id in matched_candidate_ids
    if candidate_id in confirmation_records_by_candidate_id
  ]
  warnings = list(candidate_result.get("warnings") if isinstance(candidate_result.get("warnings"), list) else [])
  if len(matched_candidate_ids) > 1:
    warnings.append("Seed matched multiple candidate ids; confirmation status is counted once for the seed.")
  if len(matched_confirmation_records) > 1:
    warnings.append("Seed matched multiple confirmed candidate ids; the first matched confirmation is summarized.")

  confirmation_record = matched_confirmation_records[0] if matched_confirmation_records else None
  confirmation_status = _confirmation_status_for_seed(
    candidate_status=str(candidate_result.get("candidate_status") or ""),
    confirmation_record=confirmation_record,
  )
  scored_candidate_id = (
    str(confirmation_record.get("candidate_id") or "")
    if confirmation_record
    else (matched_candidate_ids[0] if matched_candidate_ids else "")
  )
  result = {
    "seed_id": candidate_result.get("seed_id", ""),
    "app": str(seed.get("app") or ""),
    "candidate_type": candidate_result.get("candidate_type", ""),
    "expected_human_judgment": str(seed.get("expected_human_judgment") or ""),
    "candidate_status": candidate_result.get("candidate_status", ""),
    "candidate_level_status": candidate_result.get("status", ""),
    "confirmation_status": confirmation_status,
    "matched_candidate_id": scored_candidate_id,
    "matched_candidate_ids": matched_candidate_ids,
    "confirmation_record_found": confirmation_record is not None,
    "confirmation_run_id": confirmation_run_id,
    "confirmation_id": str(confirmation_record.get("confirmation_id") or "") if confirmation_record else "",
    "decision": str(confirmation_record.get("decision") or "") if confirmation_record else "",
    "parse_status": str(confirmation_record.get("parse_status") or "") if confirmation_record else "",
    "confidence": confirmation_record.get("confidence") if confirmation_record else None,
    "error": confirmation_record.get("error") if confirmation_record else None,
    "context_mode": str(confirmation_record.get("context_mode") or "") if confirmation_record else "",
    "provider": str(confirmation_record.get("provider") or "") if confirmation_record else "",
    "model": str(confirmation_record.get("model") or "") if confirmation_record else "",
    "matched_states": candidate_result.get("matched_states", []),
    "matched_evidence": candidate_result.get("matched_evidence", []),
    "matched_candidates": matched_candidates,
    "warnings": warnings,
  }
  return result


def _confirmation_status_for_seed(
  *,
  candidate_status: str,
  confirmation_record: dict[str, Any] | None,
) -> str:
  if candidate_status != "candidate_recovered":
    return "candidate_missing"
  if confirmation_record is None:
    return "missing_confirmation"

  parse_status = str(confirmation_record.get("parse_status") or "")
  decision = str(confirmation_record.get("decision") or "")
  if parse_status == "client_error":
    return "provider_error"
  if parse_status != "parsed":
    return "parse_error"
  if decision in {"violation", "no_violation", "uncertain"}:
    return f"confirmed_{decision}"
  return "parse_error"


def _confirmation_records_by_candidate_id(records: tuple[dict[str, object], ...]) -> dict[str, dict[str, Any]]:
  by_candidate_id: dict[str, dict[str, Any]] = {}
  for index, record in enumerate(records, start=1):
    candidate_id = str(record.get("candidate_id") or "")
    if not candidate_id:
      raise ValueError(f"Confirmation record {index} is missing candidate_id.")
    if candidate_id in by_candidate_id:
      raise ValueError(f"Duplicate confirmation records for candidate_id: {candidate_id}")
    by_candidate_id[candidate_id] = dict(record)
  return by_candidate_id


def _overall_status(
  *,
  state_status: str,
  evidence_status: str,
  candidate_status: str,
) -> str:
  if candidate_status == "candidate_recovered":
    if state_status == "state_acquired" and evidence_status == "evidence_found":
      return "recovered_to_candidate"
    return "partial"
  if state_status == "state_not_acquired":
    return "state_not_acquired"
  if evidence_status == "evidence_missing":
    return "evidence_missing"
  return "candidate_missing"


def _matched_states(run_states: tuple[Any, ...], expected_state: dict[str, Any]) -> list[dict[str, object]]:
  routes = _string_list(expected_state.get("routes"))
  benchmark_state_ids = set(_string_list(expected_state.get("benchmark_state_ids")))
  matches: list[dict[str, object]] = []
  for state in run_states:
    route = _state_route(state)
    benchmark_state_id = _benchmark_state_id(state)
    route_matches = not routes or any(_route_matches(route, expected_route) for expected_route in routes)
    benchmark_matches = bool(benchmark_state_id and benchmark_state_id in benchmark_state_ids)
    if _state_matches_expected_constraints(
      has_routes=bool(routes),
      route_matches=route_matches,
      has_benchmark_state_ids=bool(benchmark_state_ids),
      benchmark_matches=benchmark_matches,
    ):
      matches.append(
        {
          "state_id": state.state_id,
          "route": route,
          "url": _state_url(state),
          "title": str(state.metadata.get("title") or state.accessibility_context.get("page", {}).get("title") or ""),
          "benchmark_state_id": benchmark_state_id,
          "focused_state_name": _focused_state_name(state),
        }
      )
  return matches


def _state_matches_expected_constraints(
  *,
  has_routes: bool,
  route_matches: bool,
  has_benchmark_state_ids: bool,
  benchmark_matches: bool,
) -> bool:
  if has_routes and has_benchmark_state_ids:
    return route_matches and benchmark_matches
  if has_routes:
    return route_matches
  if has_benchmark_state_ids:
    return benchmark_matches
  return False


def _has_expected_state_constraint(expected_state: dict[str, Any]) -> bool:
  return bool(
    _string_list(expected_state.get("routes"))
    or _string_list(expected_state.get("benchmark_state_ids"))
  )


def _matched_evidence(run_states: list[Any], expected_evidence: dict[str, Any]) -> list[dict[str, object]]:
  bucket = str(expected_evidence.get("bucket") or "form_controls")
  matches: list[dict[str, object]] = []
  for state in run_states:
    raw_items = state.accessibility_context.get(bucket)
    if bucket == "page":
      items = [raw_items] if isinstance(raw_items, dict) else []
    else:
      items = raw_items if isinstance(raw_items, list) else []
    for item in items:
      if not isinstance(item, dict):
        continue
      if not _element_matches_expected(item, expected_evidence):
        continue
      matches.append(
        {
          "state_id": state.state_id,
          "route": _state_route(state),
          "benchmark_state_id": _benchmark_state_id(state),
          "bucket": bucket,
          "element_id": str(item.get("element_id") or ""),
          "selector": str(item.get("selector") or ""),
          "id": str(item.get("id") or ""),
          "name": str(item.get("name") or ""),
          "text": item.get("text"),
          "level": item.get("level"),
          "accessible_name": item.get("accessible_name"),
          "aria_label": item.get("aria_label"),
          "aria_labelledby": item.get("aria_labelledby"),
          "aria_describedby": item.get("aria_describedby"),
          "alt": item.get("alt"),
          "src": item.get("src"),
          "type": item.get("type"),
          "tag": item.get("tag"),
          "role": item.get("role"),
          "autocomplete": item.get("autocomplete"),
          "href": item.get("href"),
          "target": item.get("target"),
          "title": item.get("title"),
          "url": item.get("url"),
          "document_lang": item.get("document_lang"),
          "html_lang": item.get("html_lang"),
          "language_text": item.get("language_text"),
          "root_lang": item.get("root_lang"),
          "local_lang": item.get("local_lang"),
          "ancestor_lang": item.get("ancestor_lang"),
          "effective_lang": item.get("effective_lang"),
          "inline_style": item.get("inline_style"),
          "has_inline_color": item.get("has_inline_color"),
          "computed_style": item.get("computed_style"),
          "parent_computed_style": item.get("parent_computed_style"),
          "cue_attributes": item.get("cue_attributes"),
          "tabindex": item.get("tabindex"),
          "tabindex_value": item.get("tabindex_value"),
          "dom_order_index": item.get("dom_order_index"),
          "aria_controls": item.get("aria_controls"),
          "aria_expanded": item.get("aria_expanded"),
          "aria_selected": item.get("aria_selected"),
          "aria_checked": item.get("aria_checked"),
          "aria_pressed": item.get("aria_pressed"),
          "checked": item.get("checked"),
          "selected": item.get("selected"),
          "caption": item.get("caption"),
          "header_count": item.get("header_count"),
          "data_cell_count": item.get("data_cell_count"),
        }
      )
  return matches


def _matched_candidates(
  candidates: tuple[CandidateRecord, ...],
  *,
  seed: dict[str, Any],
  expected_state: dict[str, Any],
  expected_evidence: dict[str, Any],
  matched_state_ids: set[str],
  matched_evidence_state_ids: set[str],
) -> list[dict[str, object]]:
  candidate_type = _expected_candidate_type(seed)
  expected_candidate = (
    seed.get("expected_candidate")
    if isinstance(seed.get("expected_candidate"), dict)
    else {}
  )
  routes = _string_list(expected_state.get("routes"))
  matches: list[dict[str, object]] = []
  for candidate in candidates:
    record = candidate.record
    if str(record.get("candidate_type") or "") != candidate_type:
      continue
    if matched_state_ids and str(record.get("state_id") or "") not in matched_state_ids:
      continue
    if matched_evidence_state_ids and str(record.get("state_id") or "") not in matched_evidence_state_ids:
      continue
    if routes and not _candidate_route_matches(record, routes):
      continue
    primary_element = _candidate_primary_element(record, expected_evidence)
    if not primary_element or not _element_matches_expected(primary_element, expected_evidence, record=record):
      continue
    if not _candidate_matches_expected_evidence(record, expected_evidence):
      continue
    if not _candidate_matches_expected_destination(record, expected_candidate):
      continue
    matches.append(
      {
        "candidate_id": str(record.get("candidate_id") or ""),
        "candidate_type": str(record.get("candidate_type") or ""),
        "state_id": str(record.get("state_id") or ""),
        "line_number": candidate.line_number,
        "source_path": _path_for_output(candidate.source_path),
        "primary_selector": str(primary_element.get("selector") or ""),
        "element_id": str(primary_element.get("element_id") or ""),
        "id": str(primary_element.get("id") or ""),
        "name": str(primary_element.get("name") or ""),
        "text": primary_element.get("text"),
        "level": primary_element.get("level"),
        "accessible_name": primary_element.get("accessible_name"),
        "aria_label": primary_element.get("aria_label"),
        "aria_labelledby": primary_element.get("aria_labelledby"),
        "aria_describedby": primary_element.get("aria_describedby"),
        "alt": primary_element.get("alt"),
        "src": primary_element.get("src"),
        "type": primary_element.get("type"),
        "tag": primary_element.get("tag"),
        "role": primary_element.get("role"),
        "autocomplete": primary_element.get("autocomplete"),
        "href": primary_element.get("href"),
        "target": primary_element.get("target"),
        "title": primary_element.get("title"),
        "url": primary_element.get("url"),
        "document_lang": primary_element.get("document_lang"),
        "html_lang": primary_element.get("html_lang"),
        "language_text": primary_element.get("language_text"),
        "root_lang": primary_element.get("root_lang"),
        "local_lang": primary_element.get("local_lang"),
        "ancestor_lang": primary_element.get("ancestor_lang"),
        "effective_lang": primary_element.get("effective_lang"),
        "inline_style": primary_element.get("inline_style"),
        "has_inline_color": primary_element.get("has_inline_color"),
        "computed_style": primary_element.get("computed_style"),
        "parent_computed_style": primary_element.get("parent_computed_style"),
        "cue_attributes": primary_element.get("cue_attributes"),
        "tabindex": primary_element.get("tabindex"),
        "tabindex_value": primary_element.get("tabindex_value"),
        "dom_order_index": primary_element.get("dom_order_index"),
        "aria_controls": primary_element.get("aria_controls"),
        "aria_expanded": primary_element.get("aria_expanded"),
        "aria_selected": primary_element.get("aria_selected"),
        "aria_checked": primary_element.get("aria_checked"),
        "aria_pressed": primary_element.get("aria_pressed"),
        "checked": primary_element.get("checked"),
        "selected": primary_element.get("selected"),
        "caption": primary_element.get("caption"),
        "header_count": primary_element.get("header_count"),
        "data_cell_count": primary_element.get("data_cell_count"),
      }
    )
  return matches


def _candidate_matches_expected_evidence(
  record: dict[str, Any],
  expected_evidence: dict[str, Any],
) -> bool:
  if "candidate_evidence" not in expected_evidence:
    return True
  required = expected_evidence.get("candidate_evidence")
  actual = record.get("evidence")
  if not isinstance(required, dict) or not isinstance(actual, dict):
    return False
  return _structured_value_contains(actual, required)


def _structured_value_contains(actual: object, expected: object) -> bool:
  if isinstance(expected, dict):
    if not isinstance(actual, dict):
      return False
    return all(
      key in actual and _structured_value_contains(actual[key], expected_value)
      for key, expected_value in expected.items()
    )

  if isinstance(expected, list):
    if not isinstance(actual, list):
      return False
    return all(
      any(_structured_value_contains(actual_item, expected_item) for actual_item in actual)
      for expected_item in expected
    )

  if isinstance(actual, (dict, list)):
    return False
  return actual == expected


def _candidate_matches_expected_destination(
  record: dict[str, Any],
  expected_candidate: dict[str, Any],
) -> bool:
  expected_route = str(expected_candidate.get("destination_route") or "").strip()
  expected_heading = str(expected_candidate.get("destination_heading") or "").strip()
  raw_expected_elements = expected_candidate.get("destination_elements")
  has_expected_elements = "destination_elements" in expected_candidate
  if has_expected_elements and (
    not isinstance(raw_expected_elements, list)
    or any(
      not isinstance(item, dict) or not item
      for item in raw_expected_elements
    )
  ):
    return False
  expected_elements = (
    [item for item in raw_expected_elements if isinstance(item, dict)]
    if isinstance(raw_expected_elements, list)
    else []
  )
  if not expected_route and not expected_heading and not expected_elements:
    return True

  for destination in _candidate_destinations(record):
    if expected_route and not _destination_route_matches(
      str(destination.get("target_route") or ""),
      expected_route,
    ):
      continue
    if expected_heading and not _destination_heading_matches(destination, expected_heading):
      continue
    if expected_elements and not _destination_elements_match(
      destination,
      expected_elements,
    ):
      continue
    return True
  return False


def _candidate_destinations(record: dict[str, Any]) -> list[dict[str, Any]]:
  evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
  supporting = evidence.get("supporting") if isinstance(evidence.get("supporting"), dict) else {}
  context = (
    supporting.get("destination_state_context_v1")
    if isinstance(supporting.get("destination_state_context_v1"), dict)
    else {}
  )
  destinations = context.get("destinations") if isinstance(context.get("destinations"), list) else []
  observations = [item for item in destinations if isinstance(item, dict)]

  for candidate_context in supporting.values():
    if not isinstance(candidate_context, dict):
      continue
    action_evidence = (
      candidate_context.get("action_evidence")
      if isinstance(candidate_context.get("action_evidence"), dict)
      else {}
    )
    result_context = (
      action_evidence.get("result_state_context")
      if isinstance(action_evidence.get("result_state_context"), dict)
      else {}
    )
    if not result_context:
      continue
    headings = (
      result_context.get("headings")
      if isinstance(result_context.get("headings"), list)
      else []
    )
    observations.append(
      {
        "target_state_id": result_context.get("state_id"),
        "target_route": result_context.get("route"),
        "target_title": result_context.get("title"),
        "target_primary_headings": [
          {"text": str(heading)}
          for heading in headings
          if str(heading or "").strip()
        ],
      }
    )
  return observations


def _destination_route_matches(actual: str, expected: str) -> bool:
  if not actual or not expected:
    return False
  return _normalize_route_path(_path_from_url(actual)) == _normalize_route_path(
    _path_from_url(expected)
  )


def _destination_heading_matches(destination: dict[str, Any], expected: str) -> bool:
  headings = (
    destination.get("target_primary_headings")
    if isinstance(destination.get("target_primary_headings"), list)
    else []
  )
  return any(
    str(heading.get(key) or "").strip() == expected
    for heading in headings
    if isinstance(heading, dict)
    for key in ("text", "accessible_name")
  )


def _destination_elements_match(
  destination: dict[str, Any],
  expected_elements: list[dict[str, Any]],
) -> bool:
  observed_elements = (
    destination.get("target_elements")
    if isinstance(destination.get("target_elements"), list)
    else []
  )
  observed_elements = [
    item
    for item in observed_elements
    if isinstance(item, dict)
  ]
  if not observed_elements:
    return False
  return all(
    any(
      _destination_element_matches(observed, expected)
      for observed in observed_elements
    )
    for expected in expected_elements
  )


def _destination_element_matches(
  observed: dict[str, Any],
  expected: dict[str, Any],
) -> bool:
  for key, expected_value in expected.items():
    if key not in observed:
      return False
    observed_value = observed[key]
    if isinstance(expected_value, str):
      if _normalize_destination_element_text(observed_value) != (
        _normalize_destination_element_text(expected_value)
      ):
        return False
    elif observed_value != expected_value:
      return False
  return True


def _normalize_destination_element_text(value: object) -> str:
  return " ".join(str(value or "").split())


def _element_matches_expected(
  item: dict[str, Any],
  expected_evidence: dict[str, Any],
  *,
  record: dict[str, Any] | None = None,
) -> bool:
  attributes = expected_evidence.get("attributes") if isinstance(expected_evidence.get("attributes"), dict) else {}
  for key, expected_value in attributes.items():
    actual_value = item.get(str(key))
    actual_text = "" if actual_value is None else str(actual_value)
    if actual_text != str(expected_value):
      return False

  attribute_contains = (
    expected_evidence.get("attribute_contains")
    if isinstance(expected_evidence.get("attribute_contains"), dict)
    else {}
  )
  for key, expected_value in attribute_contains.items():
    actual_value = item.get(str(key))
    actual_text = "" if actual_value is None else str(actual_value)
    if str(expected_value) not in actual_text:
      return False

  if not _state_attributes_match_expected(item, expected_evidence):
    return False

  peer_state = (
    expected_evidence.get("peer_state")
    if isinstance(expected_evidence.get("peer_state"), dict)
    else {}
  )
  if (
    peer_state
    and record is not None
    and not _contains_matching_aria_state_peer(record, peer_state)
  ):
    return False

  data_cell = expected_evidence.get("data_cell") if isinstance(expected_evidence.get("data_cell"), dict) else {}
  if data_cell and not _contains_matching_data_cell(item, data_cell, record=record):
    return False

  control = expected_evidence.get("control") if isinstance(expected_evidence.get("control"), dict) else {}
  expected_id = str(control.get("id") or "")
  expected_name = str(control.get("name") or "")
  selector_hint = str(expected_evidence.get("selector_hint") or "")
  data_testid = _selector_hint_testid(selector_hint)

  id_matches = bool(expected_id and str(item.get("id") or "") == expected_id)
  name_matches = bool(expected_name and str(item.get("name") or "") == expected_name)
  selector_matches = bool(selector_hint and selector_hint == str(item.get("selector") or ""))
  testid_matches = bool(data_testid and _text_contains_testid(_combined_item_text(item, record), data_testid))
  selector_id_matches = bool(expected_id and str(item.get("selector") or "").endswith(f"#{expected_id}"))

  has_identity_hint = bool(expected_id or expected_name or selector_hint or data_testid)
  if not has_identity_hint:
    return True
  return id_matches or name_matches or selector_matches or testid_matches or selector_id_matches


def _state_attributes_match_expected(
  item: dict[str, Any],
  expected_evidence: dict[str, Any],
) -> bool:
  expected_state_attributes = (
    expected_evidence.get("state_attributes")
    if isinstance(expected_evidence.get("state_attributes"), dict)
    else {}
  )
  for key, expected_value in expected_state_attributes.items():
    field = str(key)
    if field not in ARIA_STATE_ATTRIBUTE_FIELDS:
      return False
    actual_value = _state_attribute_value(item, field)
    if actual_value is None or str(actual_value) != str(expected_value):
      return False

  absent_state_attributes = expected_evidence.get("absent_state_attributes")
  if not isinstance(absent_state_attributes, list):
    absent_state_attributes = []
  for key in absent_state_attributes:
    field = str(key)
    if field not in ARIA_STATE_ATTRIBUTE_FIELDS:
      return False
    if _state_attribute_value(item, field) not in (None, ""):
      return False
  return True


def _state_attribute_value(item: dict[str, Any], field: str) -> Any:
  state_attributes = item.get("state_attributes") if isinstance(item.get("state_attributes"), dict) else {}
  if field in state_attributes:
    return state_attributes.get(field)
  cue_attributes = item.get("cue_attributes") if isinstance(item.get("cue_attributes"), dict) else {}
  if field in cue_attributes:
    return cue_attributes.get(field)
  return item.get(field)


def _contains_matching_aria_state_peer(
  record: dict[str, Any],
  expected_peer: dict[str, Any],
) -> bool:
  return any(
    _element_matches_expected(peer, expected_peer)
    for peer in _aria_state_peer_items(record)
  )


def _aria_state_peer_items(record: dict[str, Any]) -> list[dict[str, Any]]:
  evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
  supporting = evidence.get("supporting") if isinstance(evidence.get("supporting"), dict) else {}
  aria_state_context = (
    supporting.get("aria_state_context_v1")
    if isinstance(supporting.get("aria_state_context_v1"), dict)
    else {}
  )
  current_item_context = (
    aria_state_context.get("current_item_context")
    if isinstance(aria_state_context.get("current_item_context"), dict)
    else {}
  )
  peer_sources = (
    current_item_context.get("peer_items"),
    aria_state_context.get("peer_state_context"),
  )
  peers: list[dict[str, Any]] = []
  seen_identities: set[tuple[str, str]] = set()
  for peer_source in peer_sources:
    if not isinstance(peer_source, list):
      continue
    for peer in peer_source:
      if not isinstance(peer, dict):
        continue
      identity = _aria_state_peer_identity(peer)
      if identity and identity in seen_identities:
        continue
      if identity:
        seen_identities.add(identity)
      peers.append(peer)
  return peers


def _aria_state_peer_identity(peer: dict[str, Any]) -> tuple[str, str] | None:
  element_id = str(peer.get("element_id") or "").strip()
  if element_id:
    return ("element_id", element_id)
  selector = str(peer.get("selector") or "").strip()
  if selector:
    return ("selector", selector)
  return None


def _contains_matching_data_cell(
  item: dict[str, Any],
  expected_data_cell: dict[str, Any],
  *,
  record: dict[str, Any] | None = None,
) -> bool:
  return any(
    _data_cell_matches_expected(cell, expected_data_cell)
    for cell in _table_data_cells(item, record=record)
  )


def _table_data_cells(
  item: dict[str, Any],
  *,
  record: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
  cells: list[dict[str, Any]] = []
  item_cells = item.get("data_cells") if isinstance(item.get("data_cells"), list) else []
  cells.extend(cell for cell in item_cells if isinstance(cell, dict))

  if record:
    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    supporting = evidence.get("supporting") if isinstance(evidence.get("supporting"), dict) else {}
    table_context = (
      supporting.get("table_header_association_context_v1")
      if isinstance(supporting.get("table_header_association_context_v1"), dict)
      else {}
    )
    context_cells = (
      table_context.get("associated_data_cells")
      if isinstance(table_context.get("associated_data_cells"), list)
      else []
    )
    relationship_summary = (
      table_context.get("relationship_summary")
      if isinstance(table_context.get("relationship_summary"), dict)
      else {}
    )
    all_included_associations_resolved = relationship_summary.get(
      "all_included_associations_resolved"
    )
    for cell in context_cells:
      if not isinstance(cell, dict):
        continue
      normalized_cell = dict(cell)
      if (
        "headers_all_resolved" not in normalized_cell
        and isinstance(all_included_associations_resolved, bool)
      ):
        normalized_cell["headers_all_resolved"] = all_included_associations_resolved
      cells.append(normalized_cell)

  return cells


def _data_cell_matches_expected(
  cell: dict[str, Any],
  expected_data_cell: dict[str, Any],
) -> bool:
  if "text" in expected_data_cell and str(cell.get("text") or "") != str(expected_data_cell.get("text") or ""):
    return False

  if "selector" in expected_data_cell and str(cell.get("selector") or "") != str(expected_data_cell.get("selector") or ""):
    return False

  if "headers_all_resolved" in expected_data_cell:
    if cell.get("headers_all_resolved") is not expected_data_cell.get("headers_all_resolved"):
      return False

  for key in ("row_index", "column_index"):
    if key in expected_data_cell and not _optional_int_matches(cell.get(key), expected_data_cell.get(key)):
      return False

  if "header_ids" in expected_data_cell:
    if set(_string_list(cell.get("header_ids"))) != set(_string_list(expected_data_cell.get("header_ids"))):
      return False

  return True


def _optional_int_matches(actual: object, expected: object) -> bool:
  try:
    return int(str(actual)) == int(str(expected))
  except (TypeError, ValueError):
    return False


def _candidate_primary_element(record: dict[str, Any], expected_evidence: dict[str, Any]) -> dict[str, Any]:
  evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
  primary = evidence.get("primary") if isinstance(evidence.get("primary"), dict) else {}
  primary_key = _candidate_primary_key(expected_evidence)
  primary_element = primary.get(primary_key) if primary_key else {}
  if isinstance(primary_element, list):
    return _matching_primary_list_item(
      primary_element,
      expected_evidence,
      record=record,
    )
  if primary_key == "landmark_structure" and isinstance(primary_element, dict):
    return _matching_landmark_structure_landmark(
      primary_element,
      expected_evidence,
      record=record,
    )
  return primary_element if isinstance(primary_element, dict) else {}


def _matching_primary_list_item(
  items: list[Any],
  expected_evidence: dict[str, Any],
  *,
  record: dict[str, Any] | None = None,
) -> dict[str, Any]:
  first_item: dict[str, Any] = {}
  for item in items:
    if not isinstance(item, dict):
      continue
    if not first_item:
      first_item = item
    if _element_matches_expected(item, expected_evidence, record=record):
      return item
  return first_item


def _matching_landmark_structure_landmark(
  landmark_structure: dict[str, Any],
  expected_evidence: dict[str, Any],
  *,
  record: dict[str, Any] | None = None,
) -> dict[str, Any]:
  landmarks = landmark_structure.get("landmarks")
  if not isinstance(landmarks, list):
    return {}
  for landmark in landmarks:
    if not isinstance(landmark, dict):
      continue
    if _element_matches_expected(landmark, expected_evidence, record=record):
      return landmark
  return {}


def _candidate_primary_key(expected_evidence: dict[str, Any]) -> str:
  override = str(expected_evidence.get("primary_evidence_key") or "")
  if override in ALLOWED_PRIMARY_EVIDENCE_KEYS:
    return override

  bucket = str(expected_evidence.get("bucket") or "form_controls")
  return {
    "form_controls": "form_control",
    "buttons": "button",
    "page": "page",
    "links": "link",
    "images": "image",
    "headings": "heading",
    "landmarks": "landmark",
    "language_samples": "language_sample",
    "visual_cues": "visual_cue",
    "focusables": "positive_tabindex_focusables",
    "focus_traversal": "focus_traversal",
    "tables": "table",
  }.get(bucket, "")


def _candidate_route_matches(record: dict[str, Any], routes: list[str]) -> bool:
  state_context = record.get("state_context") if isinstance(record.get("state_context"), dict) else {}
  url = str(state_context.get("url") or "")
  path = _path_from_url(url) or url
  return any(_route_matches(path, route) or _route_matches(url, route) for route in routes)


def _combined_item_text(item: dict[str, Any], record: dict[str, Any] | None) -> str:
  chunks = [
    str(item.get("selector") or ""),
    str(item.get("raw_html") or ""),
    str(item.get("id") or ""),
    str(item.get("name") or ""),
  ]
  if record:
    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    snippets = evidence.get("dom_snippets") if isinstance(evidence.get("dom_snippets"), list) else []
    for snippet in snippets:
      if isinstance(snippet, dict):
        chunks.append(str(snippet.get("html") or ""))
        chunks.append(str(snippet.get("selector") or ""))
  return "\n".join(chunks)


def _selector_hint_testid(selector_hint: str) -> str:
  match = re.search(r"""data-testid\s*=\s*["']([^"']+)["']""", selector_hint)
  return match.group(1) if match else ""


def _text_contains_testid(text: str, data_testid: str) -> bool:
  return (
    f'data-testid="{data_testid}"' in text
    or f"data-testid='{data_testid}'" in text
    or data_testid in text
  )


def _expected_candidate_type(seed: dict[str, Any]) -> str:
  expected = seed.get("expected_candidate") if isinstance(seed.get("expected_candidate"), dict) else {}
  return str(expected.get("type") or expected.get("candidate_type") or seed.get("candidate_type") or "")


def _expected_state(seed: dict[str, Any]) -> dict[str, Any]:
  expected = seed.get("expected_state") if isinstance(seed.get("expected_state"), dict) else {}
  if expected:
    return expected
  route = _route_from_workflow_state(str(seed.get("workflow_state") or ""))
  return {"routes": [route]} if route else {}


def _expected_evidence(seed: dict[str, Any]) -> dict[str, Any]:
  expected = seed.get("expected_evidence") if isinstance(seed.get("expected_evidence"), dict) else {}
  if expected:
    return expected
  candidate = seed.get("expected_candidate") if isinstance(seed.get("expected_candidate"), dict) else {}
  fallback: dict[str, Any] = {
    "bucket": "form_controls",
    "selector_hint": candidate.get("selector_hint"),
    "attributes": {},
  }
  if candidate.get("autocomplete"):
    fallback["attributes"] = {"autocomplete": candidate.get("autocomplete")}
  return fallback


def _expected_evidence_items(seed: dict[str, Any]) -> list[dict[str, Any]]:
  expected = _expected_evidence(seed)
  all_of = expected.get("all_of")
  if isinstance(all_of, list):
    items = [item for item in all_of if isinstance(item, dict)]
    if items:
      return items
  return [expected]


def _dedupe_match_records(records: Any) -> list[dict[str, object]]:
  deduped: list[dict[str, object]] = []
  seen: set[str] = set()
  for record in records:
    if not isinstance(record, dict):
      continue
    key = json.dumps(record, sort_keys=True, default=str)
    if key in seen:
      continue
    seen.add(key)
    deduped.append(record)
  return deduped


def _route_from_workflow_state(value: str) -> str:
  for part in value.split():
    if part.startswith("/"):
      return part
  return ""


def _state_route(state: Any) -> str:
  route = str(state.metadata.get("route") or "")
  if route:
    return route
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  return _path_from_url(str(page.get("url") or state.metadata.get("url") or ""))


def _state_url(state: Any) -> str:
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  return str(page.get("url") or state.metadata.get("url") or "")


def _benchmark_state_id(state: Any) -> str:
  focused = state.metadata.get("focused_acquisition")
  if isinstance(focused, dict):
    return str(focused.get("benchmark_state_id") or "")
  return ""


def _focused_state_name(state: Any) -> str:
  focused = state.metadata.get("focused_acquisition")
  if isinstance(focused, dict):
    return str(focused.get("focused_state_name") or "")
  return ""


def _path_from_url(value: str) -> str:
  try:
    parsed = urlparse(value)
  except Exception:
    return value
  return parsed.path or value


def _route_matches(actual: str, expected: str) -> bool:
  if not actual or not expected:
    return False
  actual_path = _normalize_route_path(_path_from_url(actual))
  expected_path = _normalize_route_path(_path_from_url(expected))
  return actual_path == expected_path or actual_path.startswith(f"{expected_path}/")


def _normalize_route_path(value: str) -> str:
  path = value.strip()
  if not path:
    return ""
  if not path.startswith("/"):
    path = f"/{path}"
  return path.rstrip("/") or "/"


def _string_list(value: object) -> list[str]:
  if isinstance(value, list):
    return [str(item) for item in value if str(item or "").strip()]
  if isinstance(value, str) and value.strip():
    return [value]
  return []


def _build_summary(
  *,
  config: dict[str, Any],
  config_id: str,
  results: list[dict[str, object]],
  run_dir: Path,
  registry_path: Path,
  candidates_path: Path,
  score_run_id: str,
  output_dir: Path,
  generated_at: datetime,
) -> dict[str, object]:
  seed_count = len(results)
  recovered = sum(1 for result in results if result.get("candidate_status") == "candidate_recovered")
  state_acquired = sum(1 for result in results if result.get("state_status") == "state_acquired")
  evidence_found = sum(1 for result in results if result.get("evidence_status") == "evidence_found")
  expectation_invalid = sum(1 for result in results if result.get("status") == "expectation_invalid")
  matched_candidate_count = sum(
    len(result.get("matched_candidates", []))
    for result in results
    if isinstance(result.get("matched_candidates"), list)
  )
  return {
    "schema_version": SCHEMA_VERSION,
    "score_run_id": score_run_id,
    "generated_at_utc": _format_utc(generated_at),
    "config_id": config_id,
    "app": str(config.get("app") or ""),
    "seed_count": seed_count,
    "counts": {
      "expected_seeds": seed_count,
      "state_acquired": state_acquired,
      "evidence_found": evidence_found,
      "candidate_recovered": recovered,
      "recovered_seeds": recovered,
      "matched_candidates": matched_candidate_count,
      "expectation_invalid": expectation_invalid,
      "confirmation_scored": 0,
      "report_scored": 0,
    },
    "rates": {
      "candidate_recovery_rate": (recovered / seed_count) if seed_count else 0.0,
      "confirmation_recovery_rate": None,
      "report_recovery_rate": None,
    },
    "inputs": {
      "run_dir": run_dir.as_posix(),
      "registry": registry_path.as_posix(),
      "candidates": candidates_path.as_posix(),
    },
    "outputs": {
      "output_dir": output_dir.as_posix(),
      "manifest": "manifest.json",
      "summary_json": "seeded_recovery_summary.json",
      "summary_markdown": "seeded_recovery_summary.md",
    },
    "notes": [
      "Candidate-level recovery is counted per seed, not per matched state or candidate.",
      "Confirmation, report, static-baseline, graph-ablation, and baseline-negative scoring are not included in this MVP.",
      "This private evaluation output may contain seed IDs and expected labels; do not copy it into crawler artifacts, candidates, review packets, confirmations, or reports.",
    ],
    "results": results,
  }


def _build_confirmation_summary(
  *,
  config: dict[str, Any],
  config_id: str,
  confirmation_run_id: str,
  confirmation_manifest: dict[str, object],
  confirmation_records: tuple[dict[str, object], ...],
  results: list[dict[str, object]],
  run_dir: Path,
  registry_path: Path,
  candidates_path: Path,
  confirmation_dir: Path,
  confirmations_path: Path,
  score_run_id: str,
  output_dir: Path,
  candidate_id_output_path: Path | None,
  generated_at: datetime,
) -> dict[str, object]:
  counts = _confirmation_counts(results, confirmation_records)
  seed_count = counts["total_expected_seeds"]
  recovered = counts["candidate_level_recovered"]
  confirmation_records_found = counts["confirmation_records_found"]
  unscored_confirmation_records = _unscored_confirmation_records(results, confirmation_records)
  counts["unscored_confirmation_records"] = len(unscored_confirmation_records)
  return {
    "schema_version": SCHEMA_VERSION,
    "score_run_id": score_run_id,
    "generated_at_utc": _format_utc(generated_at),
    "config_id": config_id,
    "app": str(config.get("app") or ""),
    "confirmation_run_id": confirmation_run_id,
    "confirmation_context_mode": _confirmation_context_mode(confirmation_manifest),
    "counts": counts,
    "rates": {
      "candidate_level_seeded_recovery_rate": (recovered / seed_count) if seed_count else 0.0,
      "confirmation_record_rate_among_recovered": (
        confirmation_records_found / recovered
      ) if recovered else 0.0,
      "confirmed_violation_rate_among_expected": (
        counts["confirmed_violation"] / seed_count
      ) if seed_count else 0.0,
    },
    "inputs": {
      "run_dir": run_dir.as_posix(),
      "registry": registry_path.as_posix(),
      "candidates": candidates_path.as_posix(),
      "confirmation_dir": confirmation_dir.as_posix(),
      "confirmations": confirmations_path.as_posix(),
      "confirmation_run_id": confirmation_run_id,
    },
    "outputs": {
      "output_dir": output_dir.as_posix(),
      "manifest": "manifest.json",
      "summary_json": "seeded_confirmation_summary.json",
      "summary_markdown": "seeded_confirmation_summary.md",
      "candidate_id_file": _path_for_output(candidate_id_output_path) if candidate_id_output_path else None,
    },
    "by_app": _group_confirmation_counts(results, key="app"),
    "by_candidate_type": _group_confirmation_counts(results, key="candidate_type"),
    "unscored_confirmation_records": unscored_confirmation_records,
    "notes": [
      "This is private confirmation-level seeded recovery over documented seeded known positives.",
      "It is not general recall, public-web precision/F1, or exhaustive accessibility coverage.",
      "Seed IDs and expected labels may appear here, but must stay out of crawler artifacts, candidates, prompts, normal confirmations, review packets, and reports.",
    ],
    "results": results,
  }


def _confirmation_counts(
  results: list[dict[str, object]],
  confirmation_records: tuple[dict[str, object], ...],
) -> dict[str, int]:
  counts = _empty_confirmation_counts()
  counts["total_expected_seeds"] = len(results)
  counts["expected_seeds"] = len(results)
  counts["confirmation_records_total"] = len(confirmation_records)
  for result in results:
    candidate_status = str(result.get("candidate_status") or "")
    confirmation_status = str(result.get("confirmation_status") or "")
    if candidate_status == "candidate_recovered":
      counts["candidate_level_recovered"] += 1
    else:
      counts["candidate_missing"] += 1
    if result.get("confirmation_record_found"):
      counts["confirmation_records_found"] += 1
    if confirmation_status in counts:
      counts[confirmation_status] += 1
  return counts


def _empty_confirmation_counts() -> dict[str, int]:
  return {
    "total_expected_seeds": 0,
    "expected_seeds": 0,
    "candidate_level_recovered": 0,
    "confirmation_records_found": 0,
    "confirmed_violation": 0,
    "confirmed_no_violation": 0,
    "confirmed_uncertain": 0,
    "parse_error": 0,
    "provider_error": 0,
    "missing_confirmation": 0,
    "candidate_missing": 0,
    "confirmation_records_total": 0,
    "unscored_confirmation_records": 0,
  }


def _group_confirmation_counts(results: list[dict[str, object]], *, key: str) -> dict[str, dict[str, int]]:
  grouped: dict[str, dict[str, int]] = {}
  for result in results:
    group_key = str(result.get(key) or "")
    if not group_key:
      group_key = "unknown"
    if group_key not in grouped:
      grouped[group_key] = _empty_confirmation_counts()
    counts = grouped[group_key]
    counts["total_expected_seeds"] += 1
    counts["expected_seeds"] += 1
    candidate_status = str(result.get("candidate_status") or "")
    confirmation_status = str(result.get("confirmation_status") or "")
    if candidate_status == "candidate_recovered":
      counts["candidate_level_recovered"] += 1
    else:
      counts["candidate_missing"] += 1
    if result.get("confirmation_record_found"):
      counts["confirmation_records_found"] += 1
    if confirmation_status in counts:
      counts[confirmation_status] += 1
  return dict(sorted(grouped.items()))


def _unscored_confirmation_records(
  results: list[dict[str, object]],
  confirmation_records: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
  scored_candidate_ids = {
    str(candidate_id)
    for result in results
    for candidate_id in (
      result.get("matched_candidate_ids")
      if isinstance(result.get("matched_candidate_ids"), list)
      else []
    )
    if str(candidate_id)
  }
  unscored: list[dict[str, object]] = []
  for record in confirmation_records:
    candidate_id = str(record.get("candidate_id") or "")
    if candidate_id in scored_candidate_ids:
      continue
    unscored.append(
      {
        "candidate_id": candidate_id,
        "candidate_type": str(record.get("candidate_type") or ""),
        "state_id": str(record.get("state_id") or ""),
        "decision": str(record.get("decision") or ""),
        "parse_status": str(record.get("parse_status") or ""),
        "confirmation_id": str(record.get("confirmation_id") or ""),
      }
    )
  return unscored


def _confirmation_context_mode(manifest: dict[str, object]) -> str:
  config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
  return str(manifest.get("context_mode") or config.get("context_mode") or "")


def _build_manifest(
  *,
  options: SeededScorerOptions,
  summary: dict[str, object],
  score_run_id: str,
  run_dir: Path,
  registry_path: Path,
  candidates_path: Path,
  output_dir: Path,
  generated_at: datetime,
) -> dict[str, object]:
  counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
  return {
    "schema_version": SCHEMA_VERSION,
    "score_run_id": score_run_id,
    "generated_at_utc": _format_utc(generated_at),
    "run_dir": run_dir.as_posix(),
    "output_dir": output_dir.as_posix(),
    "config_id": options.config_id,
    "inputs": {
      "registry": registry_path.as_posix(),
      "candidates": candidates_path.as_posix(),
      "states_dir": (run_dir / "states").as_posix(),
    },
    "outputs": {
      "manifest": "manifest.json",
      "summary_json": "seeded_recovery_summary.json",
      "summary_markdown": "seeded_recovery_summary.md",
    },
    "counts": counts,
    "generator": {
      "name": GENERATOR_NAME,
      "version": GENERATOR_VERSION,
    },
    "invocation": {
      "argv": list(options.argv),
      "cwd": str(options.cwd or Path.cwd()),
      "python_version": sys.version,
      "platform": platform.platform(),
    },
  }


def _build_confirmation_manifest(
  *,
  options: SeededConfirmationScorerOptions,
  summary: dict[str, object],
  score_run_id: str,
  run_dir: Path,
  registry_path: Path,
  candidates_path: Path,
  confirmation_dir: Path,
  confirmations_path: Path,
  output_dir: Path,
  generated_at: datetime,
) -> dict[str, object]:
  counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
  return {
    "schema_version": SCHEMA_VERSION,
    "score_run_id": score_run_id,
    "generated_at_utc": _format_utc(generated_at),
    "run_dir": run_dir.as_posix(),
    "output_dir": output_dir.as_posix(),
    "config_id": options.config_id,
    "confirmation_run_id": options.confirmation_run_id,
    "inputs": {
      "registry": registry_path.as_posix(),
      "candidates": candidates_path.as_posix(),
      "states_dir": (run_dir / "states").as_posix(),
      "confirmation_dir": confirmation_dir.as_posix(),
      "confirmations": confirmations_path.as_posix(),
    },
    "outputs": {
      "manifest": "manifest.json",
      "summary_json": "seeded_confirmation_summary.json",
      "summary_markdown": "seeded_confirmation_summary.md",
      "candidate_id_file": _path_for_output(options.candidate_id_output_path)
      if options.candidate_id_output_path
      else None,
    },
    "counts": counts,
    "generator": {
      "name": CONFIRMATION_GENERATOR_NAME,
      "version": CONFIRMATION_GENERATOR_VERSION,
    },
    "invocation": {
      "argv": list(options.argv),
      "cwd": str(options.cwd or Path.cwd()),
      "python_version": sys.version,
      "platform": platform.platform(),
    },
  }


def _write_outputs(
  *,
  output_dir: Path,
  summary: dict[str, object],
  manifest: dict[str, object],
) -> None:
  (output_dir / "seeded_recovery_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
    encoding="utf-8",
  )
  (output_dir / "seeded_recovery_summary.md").write_text(
    _render_markdown(summary),
    encoding="utf-8",
  )
  (output_dir / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
    encoding="utf-8",
  )


def _write_confirmation_outputs(
  *,
  output_dir: Path,
  summary: dict[str, object],
  manifest: dict[str, object],
  candidate_id_output_path: Path | None,
  overwrite: bool,
) -> None:
  (output_dir / "seeded_confirmation_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
    encoding="utf-8",
  )
  (output_dir / "seeded_confirmation_summary.md").write_text(
    _render_confirmation_markdown(summary),
    encoding="utf-8",
  )
  (output_dir / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
    encoding="utf-8",
  )
  if candidate_id_output_path:
    _write_candidate_id_file(
      path=candidate_id_output_path,
      candidate_ids=_recovered_seed_candidate_ids(summary),
      overwrite=overwrite,
    )


def _render_markdown(summary: dict[str, object]) -> str:
  counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
  rates = summary.get("rates") if isinstance(summary.get("rates"), dict) else {}
  results = summary.get("results") if isinstance(summary.get("results"), list) else []
  lines = [
    "# Seeded Recovery Summary",
    "",
    f"- Config: `{summary.get('config_id')}`",
    f"- App: `{summary.get('app')}`",
    f"- Expected seeds: {counts.get('expected_seeds', 0)}",
    f"- Recovered seeds: {counts.get('recovered_seeds', 0)}",
    f"- Matched candidates: {counts.get('matched_candidates', 0)}",
    f"- Candidate recovery rate: {_format_rate(rates.get('candidate_recovery_rate'))}",
    "",
    "This is private evaluation output for known seeded cases. It is not a general recall metric.",
    "",
    "## Seed Results",
    "",
    "| Seed | Type | Status | State | Evidence | Candidate | Matches |",
    "| --- | --- | --- | --- | --- | --- | ---: |",
  ]
  for result in results:
    if not isinstance(result, dict):
      continue
    matched_candidates = result.get("matched_candidates") if isinstance(result.get("matched_candidates"), list) else []
    lines.append(
      "| "
      f"`{result.get('seed_id', '')}` | "
      f"`{result.get('candidate_type', '')}` | "
      f"`{result.get('status', '')}` | "
      f"`{result.get('state_status', '')}` | "
      f"`{result.get('evidence_status', '')}` | "
      f"`{result.get('candidate_status', '')}` | "
      f"{len(matched_candidates)} |"
    )
  lines.extend(
    [
      "",
      "## Boundaries",
      "",
      "- Candidate-level recovery is counted once per seed.",
      "- Confirmation, report, static-baseline, graph-ablation, and baseline-negative scoring are not included.",
      "- Seed IDs and expected labels must stay out of crawler artifacts, candidates, review packets, confirmations, and reports.",
      "",
    ]
  )
  return "\n".join(lines)


def _render_confirmation_markdown(summary: dict[str, object]) -> str:
  counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
  results = summary.get("results") if isinstance(summary.get("results"), list) else []
  lines = [
    "# Seeded Confirmation Summary",
    "",
    f"- Config: `{summary.get('config_id')}`",
    f"- App: `{summary.get('app')}`",
    f"- Confirmation run: `{summary.get('confirmation_run_id')}`",
    f"- Context mode: `{summary.get('confirmation_context_mode')}`",
    f"- Expected seeded known positives: {counts.get('total_expected_seeds', 0)}",
    f"- Candidate-level recovered: {counts.get('candidate_level_recovered', 0)}",
    f"- Confirmation records found: {counts.get('confirmation_records_found', 0)}",
    f"- Confirmed violation: {counts.get('confirmed_violation', 0)}",
    f"- Confirmed no violation: {counts.get('confirmed_no_violation', 0)}",
    f"- Confirmed uncertain: {counts.get('confirmed_uncertain', 0)}",
    f"- Parse error: {counts.get('parse_error', 0)}",
    f"- Provider error: {counts.get('provider_error', 0)}",
    f"- Missing confirmation: {counts.get('missing_confirmation', 0)}",
    "",
    "This is private confirmation-level seeded recovery over documented seeded known positives. It is not general recall, public-web precision/F1, or exhaustive accessibility coverage.",
    "",
    "## Seed Results",
    "",
    "| Seed | Type | Candidate | Confirmation status | Decision | Parse | Confidence |",
    "| --- | --- | --- | --- | --- | --- | ---: |",
  ]
  for result in results:
    if not isinstance(result, dict):
      continue
    lines.append(
      "| "
      f"`{result.get('seed_id', '')}` | "
      f"`{result.get('candidate_type', '')}` | "
      f"`{result.get('matched_candidate_id', '')}` | "
      f"`{result.get('confirmation_status', '')}` | "
      f"`{result.get('decision', '')}` | "
      f"`{result.get('parse_status', '')}` | "
      f"{_format_number(result.get('confidence'))} |"
    )
  lines.extend(
    [
      "",
      "## Boundaries",
      "",
      "- Seed IDs and expected labels are private evaluation metadata.",
      "- This scorer reads normal candidates and confirmations but does not modify them.",
      "- Use candidate IDs, not seed IDs, for confirmation run selection.",
      "",
    ]
  )
  return "\n".join(lines)


def _recovered_seed_candidate_ids(summary: dict[str, object]) -> tuple[str, ...]:
  results = summary.get("results") if isinstance(summary.get("results"), list) else []
  candidate_ids: list[str] = []
  seen: set[str] = set()
  for result in results:
    if not isinstance(result, dict):
      continue
    if result.get("candidate_status") != "candidate_recovered":
      continue
    matched_candidate_ids = (
      result.get("matched_candidate_ids")
      if isinstance(result.get("matched_candidate_ids"), list)
      else []
    )
    for candidate_id in matched_candidate_ids:
      candidate_id_text = str(candidate_id)
      if not candidate_id_text or candidate_id_text in seen:
        continue
      seen.add(candidate_id_text)
      candidate_ids.append(candidate_id_text)
  return tuple(candidate_ids)


def _write_candidate_id_file(
  *,
  path: Path,
  candidate_ids: tuple[str, ...],
  overwrite: bool,
) -> None:
  resolved_path = path.resolve()
  if resolved_path.exists() and not overwrite:
    raise FileExistsError(f"Candidate id output file already exists: {resolved_path}. Use --overwrite to replace it.")
  resolved_path.parent.mkdir(parents=True, exist_ok=True)
  resolved_path.write_text(
    "".join(f"{candidate_id}\n" for candidate_id in candidate_ids),
    encoding="utf-8",
  )


def _format_rate(value: object) -> str:
  if isinstance(value, int | float):
    return f"{value:.3f}"
  return "not scored"


def _format_number(value: object) -> str:
  if value is None:
    return ""
  if isinstance(value, float):
    return f"{value:.4f}".rstrip("0").rstrip(".")
  return str(value)


def _load_registry(path: Path) -> dict[str, Any]:
  return load_benchmark_registry(path)


def _resolve_config(registry: dict[str, Any], config_id: str) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
  configs = registry.get("seeded_configurations")
  if not isinstance(configs, list):
    raise ValueError("Seed expectation registry is missing `seeded_configurations`.")
  config = next(
    (
      item
      for item in configs
      if isinstance(item, dict) and item.get("configuration_id") == config_id
    ),
    None,
  )
  if config is None:
    raise ValueError(f"Seeded configuration not found: {config_id}")

  variants = registry.get("variants")
  if not isinstance(variants, list):
    raise ValueError("Seed expectation registry is missing `variants`.")
  variants_by_id = {
    str(item.get("variant_id")): item
    for item in variants
    if isinstance(item, dict) and item.get("variant_id")
  }
  seed_ids = _string_list(config.get("seed_ids"))
  if not seed_ids:
    raise ValueError(f"Seeded configuration has no seed_ids: {config_id}")
  missing = [seed_id for seed_id in seed_ids if seed_id not in variants_by_id]
  if missing:
    raise ValueError(f"Seeded configuration references unknown seed ids: {', '.join(missing)}")
  return config, tuple(variants_by_id[seed_id] for seed_id in seed_ids)


def _load_candidates(path: Path) -> tuple[CandidateRecord, ...]:
  if not path.exists() or not path.is_file():
    raise FileNotFoundError(
      f"Candidate JSONL not found: {path}. Run python accessgraph.py candidates --run <run_dir> first."
    )
  records: list[CandidateRecord] = []
  with path.open("r", encoding="utf-8") as handle:
    for line_number, line in enumerate(handle, start=1):
      stripped = line.strip()
      if not stripped:
        continue
      payload = json.loads(stripped)
      if not isinstance(payload, dict):
        raise ValueError(f"Candidate record at {path}:{line_number} is not a JSON object")
      records.append(CandidateRecord(record=payload, line_number=line_number, source_path=path))
  return tuple(records)


def _prepare_output_dir(output_dir: Path, *, overwrite: bool = False) -> None:
  if output_dir.exists():
    if not overwrite:
      raise FileExistsError(
        f"Seeded recovery output directory already exists: {output_dir}. Use --overwrite to replace it."
      )
    if not output_dir.is_dir():
      raise FileExistsError(f"Seeded recovery output path exists and is not a directory: {output_dir}")
    shutil.rmtree(output_dir)
  output_dir.mkdir(parents=True)


def _validate_output_dir(output_dir: Path, *, run_dir: Path) -> None:
  resolved_output = output_dir.resolve()
  resolved_run = run_dir.resolve()
  forbidden_exact = {resolved_run}
  forbidden_trees = {
    (run_dir / "states").resolve(),
    (run_dir / "candidates").resolve(),
    (run_dir / "confirmations").resolve(),
    (run_dir / "reports").resolve(),
  }
  if resolved_output in forbidden_exact or any(_is_relative_to(resolved_output, path) for path in forbidden_trees):
    raise ValueError(f"Refusing to write seeded recovery output over core run artifact directory: {output_dir}")


def _validate_private_output_file(path: Path, *, run_dir: Path, overwrite: bool) -> None:
  resolved_path = path.resolve()
  forbidden_trees = {
    (run_dir / "states").resolve(),
    (run_dir / "candidates").resolve(),
    (run_dir / "confirmations").resolve(),
    (run_dir / "reports").resolve(),
  }
  if any(_is_relative_to(resolved_path, forbidden) for forbidden in forbidden_trees):
    raise ValueError(f"Refusing to write seeded scorer output under core run artifact directory: {path}")
  if resolved_path.exists() and not overwrite:
    raise FileExistsError(f"Candidate id output file already exists: {resolved_path}. Use --overwrite to replace it.")


def _generate_score_run_id(*, generated_at: datetime | None = None) -> str:
  generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  return _sanitize_run_id(f"seeded_recovery_{generated.strftime('%Y%m%d_%H%M%S')}")


def _generate_confirmation_score_run_id(*, generated_at: datetime | None = None) -> str:
  generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  return _sanitize_run_id(f"seeded_confirmation_{generated.strftime('%Y%m%d_%H%M%S')}")


def _sanitize_run_id(value: str) -> str:
  sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
  sanitized = sanitized.strip("._-")
  return sanitized or "seeded_recovery"


def _format_utc(value: datetime) -> str:
  return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _path_for_output(path: Path) -> str:
  return path.as_posix()


def _is_relative_to(path: Path, parent: Path) -> bool:
  try:
    path.relative_to(parent)
    return True
  except ValueError:
    return False
