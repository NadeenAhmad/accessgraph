from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable

from .models import (
  GENERATOR_NAME,
  GENERATOR_VERSION,
  SCHEMA_VERSION,
  ConfirmationComparisonOptions,
  LoadedConfirmationRun,
)

_DECISIONS = ("violation", "no_violation", "uncertain")
_PARSE_STATUSES = (
  "parsed",
  "malformed_json",
  "schema_error",
  "id_mismatch",
  "client_error",
)


def build_comparison_payload(
  loaded_runs: tuple[LoadedConfirmationRun, ...],
  *,
  options: ConfirmationComparisonOptions,
  comparison_run_id: str,
  generated_at: datetime | None = None,
) -> dict[str, Any]:
  generated = _format_utc(generated_at or datetime.now(timezone.utc))
  warnings = _build_warnings(loaded_runs)
  flat_records = _flatten_records(loaded_runs)
  candidate_comparisons = _candidate_comparisons(flat_records)

  return {
    "schema_version": SCHEMA_VERSION,
    "comparison_run_id": comparison_run_id,
    "generated_at": generated,
    "generator": {
      "name": GENERATOR_NAME,
      "version": GENERATOR_VERSION,
    },
    "source_run_dir": options.run_dir.resolve().as_posix(),
    "included_confirmation_runs": [_included_run_payload(run) for run in loaded_runs],
    "summary": _overall_summary(flat_records, candidate_comparisons, warnings),
    "summary_by_run": [_run_summary(run) for run in loaded_runs],
    "summary_by_candidate_type": _group_summary(
      flat_records,
      key_name="candidate_type",
      key_func=lambda item: _string(item["record"].get("candidate_type")),
    ),
    "summary_by_model": _group_summary(
      flat_records,
      key_name="model_key",
      key_func=lambda item: _model_key(item["record"]),
      metadata_func=_model_metadata,
    ),
    "parse_status_summary": _count_field((item["record"] for item in flat_records), "parse_status", _PARSE_STATUSES),
    "confidence_summary": _numeric_summary(_numeric_values(item["record"].get("confidence") for item in flat_records)),
    "runtime_summary": _numeric_summary(_numeric_values(item["record"].get("runtime_ms") for item in flat_records)),
    "token_summary": _token_summary(item["record"] for item in flat_records),
    "candidate_comparisons": candidate_comparisons,
    "warnings": warnings,
  }


def _included_run_payload(run: LoadedConfirmationRun) -> dict[str, Any]:
  manifest = run.manifest
  return {
    "confirmation_run_id": run.confirmation_run_id,
    "confirmation_dir": run.confirmation_dir.as_posix(),
    "manifest_path": _relative_or_posix(run.manifest_path, run.run_dir),
    "confirmations_path": _relative_or_posix(run.confirmations_path, run.run_dir),
    "provider": manifest.get("provider"),
    "model": manifest.get("model"),
    "context_mode": _manifest_context_mode(manifest),
    "prompt_version": manifest.get("prompt_version"),
    "prompt_template_hash": manifest.get("prompt_template_hash"),
    "config_hash": manifest.get("config_hash"),
    "record_count": len(run.records),
    "manifest_duration_ms": manifest.get("duration_ms"),
  }


def _run_summary(run: LoadedConfirmationRun) -> dict[str, Any]:
  records = tuple(run.records)
  return {
    **_included_run_payload(run),
    "total_records": len(records),
    "by_decision": _count_field(records, "decision", _DECISIONS),
    "parse_status_counts": _count_field(records, "parse_status", _PARSE_STATUSES),
    "by_candidate_type": _count_field(records, "candidate_type"),
    "state_count": len({_string(record.get("state_id")) for record in records}),
    "reason_present_count": sum(1 for record in records if _string(record.get("reason")).strip()),
    "supporting_evidence_count_summary": _numeric_summary(
      [len(record.get("supporting_evidence")) for record in records if isinstance(record.get("supporting_evidence"), list)]
    ),
    "confidence_summary": _numeric_summary(_numeric_values(record.get("confidence") for record in records)),
    "runtime_summary": _numeric_summary(_numeric_values(record.get("runtime_ms") for record in records)),
    "token_summary": _token_summary(records),
  }


def _group_summary(
  flat_records: tuple[dict[str, Any], ...],
  *,
  key_name: str,
  key_func,
  metadata_func=None,
) -> list[dict[str, Any]]:
  groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for item in flat_records:
    groups[key_func(item)].append(item)

  summaries = []
  for key in sorted(groups):
    records = tuple(item["record"] for item in groups[key])
    payload: dict[str, Any] = {
      key_name: key,
      "total_records": len(records),
      "by_decision": _count_field(records, "decision", _DECISIONS),
      "parse_status_counts": _count_field(records, "parse_status", _PARSE_STATUSES),
      "state_count": len({_string(record.get("state_id")) for record in records}),
      "confidence_summary": _numeric_summary(_numeric_values(record.get("confidence") for record in records)),
      "runtime_summary": _numeric_summary(_numeric_values(record.get("runtime_ms") for record in records)),
      "token_summary": _token_summary(records),
    }
    if metadata_func is not None:
      payload.update(metadata_func(records))
    summaries.append(payload)
  return summaries


def _overall_summary(
  flat_records: tuple[dict[str, Any], ...],
  candidate_comparisons: list[dict[str, Any]],
  warnings: list[dict[str, str]],
) -> dict[str, Any]:
  records = tuple(item["record"] for item in flat_records)
  return {
    "confirmation_run_count": len({item["confirmation_run_id"] for item in flat_records}),
    "total_records": len(records),
    "unique_candidate_count": len({_string(record.get("candidate_id")) for record in records}),
    "overlapping_candidate_count": len(candidate_comparisons),
    "candidate_decision_disagreement_count": sum(
      1 for comparison in candidate_comparisons if not comparison["decision_agreement"]
    ),
    "candidate_parse_status_disagreement_count": sum(
      1 for comparison in candidate_comparisons if not comparison["parse_status_agreement"]
    ),
    "by_decision": _count_field(records, "decision", _DECISIONS),
    "parse_status_counts": _count_field(records, "parse_status", _PARSE_STATUSES),
    "by_candidate_type": _count_field(records, "candidate_type"),
    "warnings_count": len(warnings),
  }


def _candidate_comparisons(flat_records: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
  by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for item in flat_records:
    candidate_id = _string(item["record"].get("candidate_id"))
    if candidate_id:
      by_candidate[candidate_id].append(item)

  comparisons: list[dict[str, Any]] = []
  for candidate_id in sorted(by_candidate):
    items = by_candidate[candidate_id]
    if len(items) < 2:
      continue
    records = [item["record"] for item in items]
    decisions = sorted({_string(record.get("decision")) for record in records})
    parse_statuses = sorted({_string(record.get("parse_status")) for record in records})
    comparisons.append(
      {
        "candidate_id": candidate_id,
        "candidate_types": sorted({_string(record.get("candidate_type")) for record in records}),
        "state_ids": sorted({_string(record.get("state_id")) for record in records}),
        "decision_agreement": len(decisions) <= 1,
        "parse_status_agreement": len(parse_statuses) <= 1,
        "decisions": decisions,
        "parse_statuses": parse_statuses,
        "runs": [
          {
            "confirmation_run_id": item["confirmation_run_id"],
            "provider": _string(record.get("provider")),
            "model": _string(record.get("model")),
            "context_mode": _context_mode(item),
            "decision": _string(record.get("decision")),
            "confidence": _float_or_none(record.get("confidence")),
            "parse_status": _string(record.get("parse_status")),
            "candidate_type": _string(record.get("candidate_type")),
            "state_id": _string(record.get("state_id")),
          }
          for item, record in zip(items, records)
        ],
      }
    )
  return comparisons


def _build_warnings(loaded_runs: tuple[LoadedConfirmationRun, ...]) -> list[dict[str, str]]:
  warnings: list[dict[str, str]] = []
  for run in loaded_runs:
    if not run.records:
      warnings.append({"scope": run.confirmation_run_id, "message": "confirmation run has no records"})
    manifest_run_id = run.manifest.get("confirmation_run_id")
    if manifest_run_id and manifest_run_id != run.confirmation_run_id:
      warnings.append(
        {
          "scope": run.confirmation_run_id,
          "message": f"manifest confirmation_run_id differs: {manifest_run_id}",
        }
      )
    for index, record in enumerate(run.records, start=1):
      record_run_id = record.get("confirmation_run_id")
      if record_run_id and record_run_id != run.confirmation_run_id:
        warnings.append(
          {
            "scope": run.confirmation_run_id,
            "message": f"record {index} confirmation_run_id differs: {record_run_id}",
          }
        )
  return warnings


def _flatten_records(loaded_runs: tuple[LoadedConfirmationRun, ...]) -> tuple[dict[str, Any], ...]:
  items: list[dict[str, Any]] = []
  for run in loaded_runs:
    for record in run.records:
      items.append({"confirmation_run_id": run.confirmation_run_id, "manifest": run.manifest, "record": record})
  return tuple(items)


def _count_field(
  records: Iterable[dict[str, Any]],
  field: str,
  zero_keys: tuple[str, ...] = (),
) -> dict[str, int]:
  counter = Counter(_string(record.get(field)) for record in records)
  payload = {key: 0 for key in zero_keys}
  payload.update(dict(sorted(counter.items())))
  return payload


def _numeric_summary(values: Iterable[float]) -> dict[str, Any]:
  numeric = list(values)
  if not numeric:
    return {"count": 0, "min": None, "max": None, "mean": None, "sum": 0}
  return {
    "count": len(numeric),
    "min": min(numeric),
    "max": max(numeric),
    "mean": round(mean(numeric), 4),
    "sum": round(sum(numeric), 4),
  }


def _numeric_values(values: Iterable[Any]) -> list[float]:
  return [float(value) for value in values if isinstance(value, (int, float))]


def _token_summary(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
  records_list = list(records)
  records_with_usage = 0
  prompt_tokens = 0
  completion_tokens = 0
  total_tokens = 0
  estimated_cost = 0.0
  records_with_cost = 0

  for record in records_list:
    usage = record.get("token_usage")
    if isinstance(usage, dict):
      records_with_usage += 1
      prompt_tokens += _int_or_zero(usage.get("prompt_tokens"))
      completion_tokens += _int_or_zero(usage.get("completion_tokens"))
      total_tokens += _int_or_zero(usage.get("total_tokens"))
    cost = record.get("estimated_cost_usd")
    if isinstance(cost, (int, float)):
      records_with_cost += 1
      estimated_cost += float(cost)

  return {
    "records_with_token_usage": records_with_usage,
    "records_missing_token_usage": len(records_list) - records_with_usage,
    "prompt_tokens_total": prompt_tokens,
    "completion_tokens_total": completion_tokens,
    "total_tokens_total": total_tokens,
    "records_with_estimated_cost": records_with_cost,
    "estimated_cost_usd_total": round(estimated_cost, 8),
  }


def _model_key(record: dict[str, Any]) -> str:
  return f"{_string(record.get('provider'))}/{_string(record.get('model'))}"


def _model_metadata(records: tuple[dict[str, Any], ...]) -> dict[str, str]:
  first = records[0] if records else {}
  return {
    "provider": _string(first.get("provider")),
    "model": _string(first.get("model")),
  }


def _context_mode(item: dict[str, Any]) -> str:
  record = item.get("record") if isinstance(item.get("record"), dict) else {}
  manifest = item.get("manifest") if isinstance(item.get("manifest"), dict) else {}
  return _string(record.get("context_mode") or _manifest_context_mode(manifest))


def _manifest_context_mode(manifest: dict[str, Any]) -> str:
  config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
  return _string(manifest.get("context_mode") or config.get("context_mode"))


def _string(value: Any) -> str:
  return str(value) if value is not None else ""


def _float_or_none(value: Any) -> float | None:
  if isinstance(value, (int, float)):
    return float(value)
  return None


def _int_or_zero(value: Any) -> int:
  if isinstance(value, int):
    return value
  if isinstance(value, float):
    return int(value)
  return 0


def _relative_or_posix(path: Any, base: Any) -> str:
  try:
    return path.relative_to(base).as_posix()
  except ValueError:
    return path.as_posix()


def _format_utc(value: datetime) -> str:
  return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
