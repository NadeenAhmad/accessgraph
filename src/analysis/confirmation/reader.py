from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from src.analysis.candidates.taxonomy import require_supported_candidate_type

from .models import ReviewBundle

_REQUIRED_FIELDS = (
  "candidate_id",
  "candidate_type",
  "state_id",
  "element_refs",
  "selection_reason",
  "required_context",
  "evidence",
  "state_context",
  "graph_context",
  "artifact_refs",
  "generator",
)


def candidate_bundle_path(run_dir: Path) -> Path:
  return run_dir / "candidates" / "candidates.jsonl"


def load_review_bundles(
  run_dir: Path,
  *,
  candidate_types: Iterable[str] | None = None,
  candidate_ids: Iterable[str] | None = None,
) -> list[ReviewBundle]:
  return list(iter_review_bundles(run_dir, candidate_types=candidate_types, candidate_ids=candidate_ids))


def iter_review_bundles(
  run_dir: Path,
  *,
  candidate_types: Iterable[str] | None = None,
  candidate_ids: Iterable[str] | None = None,
) -> Iterator[ReviewBundle]:
  run_dir = run_dir.resolve()
  requested_types = _normalize_requested_types(candidate_types)
  requested_ids = _normalize_requested_ids(candidate_ids)
  seen_requested_ids: set[str] = set()
  bundle_path = candidate_bundle_path(run_dir)
  if not bundle_path.exists() or not bundle_path.is_file():
    raise FileNotFoundError(f"Candidate bundle file does not exist: {bundle_path}")

  with bundle_path.open("r", encoding="utf-8") as handle:
    for line_number, line in enumerate(handle, start=1):
      if not line.strip():
        continue
      raw = _parse_candidate_line(line, bundle_path, line_number)
      candidate_id = _required_string(raw, "candidate_id", bundle_path, line_number)
      candidate_type = require_supported_candidate_type(
        _required_string(raw, "candidate_type", bundle_path, line_number)
      )
      if requested_ids is not None:
        if candidate_id in requested_ids:
          seen_requested_ids.add(candidate_id)
        else:
          continue
      if requested_types is not None and candidate_type not in requested_types:
        continue
      yield _build_review_bundle(
        run_dir=run_dir,
        source_path=bundle_path,
        line_number=line_number,
        raw=raw,
        candidate_type=candidate_type,
      )
  if requested_ids is not None:
    missing_ids = requested_ids - seen_requested_ids
    if missing_ids:
      missing_display = ", ".join(sorted(missing_ids))
      raise ValueError(f"Requested candidate ids were not found in {bundle_path}: {missing_display}")


def _normalize_requested_types(candidate_types: Iterable[str] | None) -> set[str] | None:
  if candidate_types is None:
    return None
  return {
    require_supported_candidate_type(candidate_type)
    for candidate_type in candidate_types
  }


def _normalize_requested_ids(candidate_ids: Iterable[str] | None) -> set[str] | None:
  if candidate_ids is None:
    return None
  normalized = {
    str(candidate_id).strip()
    for candidate_id in candidate_ids
    if str(candidate_id).strip()
  }
  return normalized or None


def _parse_candidate_line(line: str, path: Path, line_number: int) -> dict[str, Any]:
  try:
    raw = json.loads(line)
  except json.JSONDecodeError as exc:
    raise ValueError(f"Candidate record at {path}:{line_number} is not valid JSON") from exc
  if not isinstance(raw, dict):
    raise ValueError(f"Candidate record at {path}:{line_number} is not a JSON object")
  return raw


def _build_review_bundle(
  *,
  run_dir: Path,
  source_path: Path,
  line_number: int,
  raw: dict[str, Any],
  candidate_type: str,
) -> ReviewBundle:
  _validate_required_fields(raw, source_path, line_number)
  primary_element_ref = raw.get("primary_element_ref")
  if primary_element_ref is not None and not isinstance(primary_element_ref, dict):
    raise ValueError(f"Candidate record at {source_path}:{line_number} has non-object `primary_element_ref`")

  return ReviewBundle(
    run_dir=run_dir,
    source_path=source_path,
    source_line_number=line_number,
    record=raw,
    candidate_id=_required_string(raw, "candidate_id", source_path, line_number),
    candidate_type=candidate_type,
    state_id=_required_string(raw, "state_id", source_path, line_number),
    element_refs=tuple(_required_list(raw, "element_refs", source_path, line_number)),
    selection_reason=tuple(str(item) for item in _required_list(raw, "selection_reason", source_path, line_number)),
    required_context=tuple(str(item) for item in _required_list(raw, "required_context", source_path, line_number)),
    evidence=_required_dict(raw, "evidence", source_path, line_number),
    state_context=_required_dict(raw, "state_context", source_path, line_number),
    graph_context=_required_dict(raw, "graph_context", source_path, line_number),
    artifact_refs=_required_dict(raw, "artifact_refs", source_path, line_number),
    generator=_required_dict(raw, "generator", source_path, line_number),
    primary_element_ref=primary_element_ref,
  )


def _validate_required_fields(raw: dict[str, Any], path: Path, line_number: int) -> None:
  for field in _REQUIRED_FIELDS:
    if field not in raw:
      raise ValueError(f"Candidate record at {path}:{line_number} is missing required field `{field}`")


def _required_string(raw: dict[str, Any], key: str, path: Path, line_number: int) -> str:
  value = raw.get(key)
  if isinstance(value, str) and value.strip():
    return value
  raise ValueError(f"Candidate record at {path}:{line_number} has invalid `{key}`; expected non-empty string")


def _required_list(raw: dict[str, Any], key: str, path: Path, line_number: int) -> list[Any]:
  value = raw.get(key)
  if isinstance(value, list):
    return value
  raise ValueError(f"Candidate record at {path}:{line_number} has invalid `{key}`; expected array")


def _required_dict(raw: dict[str, Any], key: str, path: Path, line_number: int) -> dict[str, Any]:
  value = raw.get(key)
  if isinstance(value, dict):
    return value
  raise ValueError(f"Candidate record at {path}:{line_number} has invalid `{key}`; expected object")
