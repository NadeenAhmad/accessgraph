from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
  GENERATOR_NAME,
  GENERATOR_VERSION,
  SCHEMA_VERSION,
  ConfirmationReportOptions,
  LoadedConfirmationRun,
)

HTML_SNIPPET_LIMIT = 600
EVIDENCE_PREVIEW_LIMIT = 360

_DECISIONS = ("violation", "no_violation", "uncertain")
_PARSE_STATUSES = (
  "parsed",
  "malformed_json",
  "schema_error",
  "id_mismatch",
  "client_error",
)


def build_report_payload(
  loaded: LoadedConfirmationRun,
  *,
  options: ConfirmationReportOptions,
  report_run_id: str,
  generated_at: datetime | None = None,
) -> dict[str, Any]:
  generated = _format_utc(generated_at or datetime.now(timezone.utc))
  report_warnings: list[dict[str, str]] = []
  findings: list[dict[str, Any]] = []

  for record in loaded.records:
    finding_warnings: list[str] = []
    source_excerpt: dict[str, Any] | None = None
    if options.load_source_candidates:
      source_excerpt = _load_source_candidate_excerpt(
        run_dir=loaded.run_dir,
        record=record,
        warnings=finding_warnings,
      )

    state_context = _state_context_from_source(source_excerpt)
    state_context = _merge_state_metadata(
      run_dir=loaded.run_dir,
      record=record,
      state_context=state_context,
      warnings=finding_warnings,
    )
    artifact_status = _artifact_status(
      run_dir=loaded.run_dir,
      record=record,
      verify_artifacts=options.verify_artifacts,
      warnings=finding_warnings,
    )

    finding = _finding_from_record(
      record=record,
      source_excerpt=source_excerpt,
      state_context=state_context,
      artifact_status=artifact_status,
      warnings=finding_warnings,
    )
    findings.append(finding)
    for message in finding_warnings:
      report_warnings.append(
        {
          "scope": "finding",
          "confirmation_id": str(finding.get("confirmation_id") or ""),
          "candidate_id": str(finding.get("candidate_id") or ""),
          "message": message,
        }
      )

  states = _build_states(findings)
  summary = _summary(findings=tuple(findings), warnings=tuple(report_warnings))
  manifest = loaded.manifest

  return {
    "schema_version": SCHEMA_VERSION,
    "report_run_id": report_run_id,
    "generated_at": generated,
    "generator": {
      "name": GENERATOR_NAME,
      "version": GENERATOR_VERSION,
    },
    "source": {
      "run_dir": loaded.run_dir.as_posix(),
      "confirmation_run_id": loaded.confirmation_run_id,
      "confirmation_dir": loaded.confirmation_dir.as_posix(),
      "confirmation_manifest": _relative_or_posix(loaded.manifest_path, loaded.run_dir),
      "confirmations_path": _relative_or_posix(loaded.confirmations_path, loaded.run_dir),
    },
    "confirmation": {
      "provider": manifest.get("provider"),
      "model": manifest.get("model"),
      "prompt_version": manifest.get("prompt_version"),
      "prompt_template_hash": manifest.get("prompt_template_hash"),
      "config_hash": manifest.get("config_hash"),
      "confidence_semantics": _first_confidence_semantics(findings),
      "raw_logging": manifest.get("raw_logging"),
    },
    "options": {
      "include_no_violation": options.include_no_violation,
      "load_source_candidates": options.load_source_candidates,
      "verify_artifacts": options.verify_artifacts,
    },
    "summary": summary,
    "states": states,
    "findings": findings,
    "warnings": report_warnings,
  }


def _finding_from_record(
  *,
  record: dict[str, Any],
  source_excerpt: dict[str, Any] | None,
  state_context: dict[str, Any],
  artifact_status: dict[str, str],
  warnings: list[str],
) -> dict[str, Any]:
  return {
    "confirmation_id": str(record.get("confirmation_id") or ""),
    "confirmation_run_id": str(record.get("confirmation_run_id") or ""),
    "candidate_id": str(record.get("candidate_id") or ""),
    "candidate_type": str(record.get("candidate_type") or ""),
    "state_id": str(record.get("state_id") or ""),
    "decision": str(record.get("decision") or ""),
    "confidence": _float_or_none(record.get("confidence")),
    "confidence_semantics": record.get("confidence_semantics"),
    "parse_status": str(record.get("parse_status") or ""),
    "error": record.get("error"),
    "reason": str(record.get("reason") or ""),
    "supporting_evidence": _string_list(record.get("supporting_evidence")),
    "context": _context_metadata(record),
    "candidate_summary": record.get("candidate_summary") if isinstance(record.get("candidate_summary"), dict) else {},
    "source_candidate_excerpt": source_excerpt,
    "source_candidate_ref": record.get("source_candidate_ref") if isinstance(record.get("source_candidate_ref"), dict) else {},
    "artifact_refs": record.get("artifact_refs") if isinstance(record.get("artifact_refs"), dict) else {},
    "artifact_status": artifact_status,
    "state": state_context,
    "warnings": warnings,
  }


def _context_metadata(record: dict[str, Any]) -> dict[str, Any]:
  keys = (
    "context_mode",
    "requested_context_mode",
    "selected_context_mode",
    "resolved_context_mode",
    "context_policy_version",
    "graph_context_included",
    "graph_context_omitted_reason",
    "attempt_count",
    "escalation_triggered",
    "final_decision_source",
    "final_attempt_index",
    "initial_context_mode",
    "initial_decision",
    "initial_parse_status",
    "retry_context_mode",
    "retry_decision",
    "retry_parse_status",
    "retry_error",
  )
  context: dict[str, Any] = {}
  for key in keys:
    if key in record:
      context[key] = record.get(key)
  if "escalation_triggered" in context:
    context["adaptive_fallback_triggered"] = bool(context["escalation_triggered"])
  return context


def _load_source_candidate_excerpt(
  *,
  run_dir: Path,
  record: dict[str, Any],
  warnings: list[str],
) -> dict[str, Any] | None:
  ref = record.get("source_candidate_ref")
  if not isinstance(ref, dict):
    warnings.append("source_candidate_ref is missing or invalid")
    return None

  path_value = ref.get("path")
  line_number = ref.get("line_number")
  if not isinstance(path_value, str) or not path_value.strip():
    warnings.append("source_candidate_ref.path is missing or invalid")
    return None
  if not isinstance(line_number, int) or line_number < 1:
    warnings.append("source_candidate_ref.line_number is missing or invalid")
    return None

  candidate_path = _resolve_run_path(run_dir, path_value)
  if not candidate_path.exists() or not candidate_path.is_file():
    warnings.append(f"source candidate file is missing: {path_value}")
    return None

  try:
    with candidate_path.open("r", encoding="utf-8") as handle:
      for current_line, line in enumerate(handle, start=1):
        if current_line == line_number:
          candidate = json.loads(line)
          break
      else:
        warnings.append(f"source candidate line does not exist: {path_value}:{line_number}")
        return None
  except json.JSONDecodeError:
    warnings.append(f"source candidate line is invalid JSON: {path_value}:{line_number}")
    return None

  if not isinstance(candidate, dict):
    warnings.append(f"source candidate line is not a JSON object: {path_value}:{line_number}")
    return None

  if candidate.get("candidate_id") != record.get("candidate_id"):
    warnings.append("source candidate candidate_id does not match confirmation record")

  return _candidate_excerpt(candidate)


def _candidate_excerpt(candidate: dict[str, Any]) -> dict[str, Any]:
  evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
  element_refs = candidate.get("element_refs") if isinstance(candidate.get("element_refs"), list) else []
  excerpt: dict[str, Any] = {
    "selection_reason": _string_list(candidate.get("selection_reason")),
    "required_context": _string_list(candidate.get("required_context")),
    "element_ref_count": len(element_refs),
    "primary_element_ref": candidate.get("primary_element_ref")
    if isinstance(candidate.get("primary_element_ref"), dict)
    else None,
    "evidence_keys": sorted(str(key) for key in evidence.keys()),
  }
  evidence_preview = _evidence_preview(evidence)
  if evidence_preview:
    excerpt["evidence_preview"] = evidence_preview
  affected_html = _find_html_snippet(evidence)
  if affected_html:
    excerpt["affected_html"] = _truncate_text(affected_html, HTML_SNIPPET_LIMIT)
    excerpt["affected_html_truncated"] = len(affected_html) > HTML_SNIPPET_LIMIT
  state_context = candidate.get("state_context")
  if isinstance(state_context, dict):
    excerpt["state_context"] = {
      key: state_context.get(key)
      for key in ("url", "title", "route", "depth", "parent_state")
      if key in state_context
    }
  return excerpt


def _state_context_from_source(source_excerpt: dict[str, Any] | None) -> dict[str, Any]:
  if not source_excerpt:
    return {}
  state_context = source_excerpt.get("state_context")
  if isinstance(state_context, dict):
    return dict(state_context)
  return {}


def _merge_state_metadata(
  *,
  run_dir: Path,
  record: dict[str, Any],
  state_context: dict[str, Any],
  warnings: list[str],
) -> dict[str, Any]:
  refs = record.get("artifact_refs")
  if not isinstance(refs, dict):
    return state_context
  metadata_ref = refs.get("metadata")
  if not isinstance(metadata_ref, str) or not metadata_ref.strip():
    return state_context
  metadata_path = _resolve_run_path(run_dir, metadata_ref)
  if not metadata_path.exists() or not metadata_path.is_file():
    warnings.append(f"state metadata artifact is missing: {metadata_ref}")
    return state_context
  try:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
  except json.JSONDecodeError:
    warnings.append(f"state metadata artifact is invalid JSON: {metadata_ref}")
    return state_context
  if not isinstance(metadata, dict):
    warnings.append(f"state metadata artifact is not a JSON object: {metadata_ref}")
    return state_context

  merged = dict(state_context)
  for key in ("url", "title", "route", "depth", "parent_state"):
    if key in metadata and key not in merged:
      merged[key] = metadata[key]
  return merged


def _artifact_status(
  *,
  run_dir: Path,
  record: dict[str, Any],
  verify_artifacts: bool,
  warnings: list[str],
) -> dict[str, str]:
  refs = record.get("artifact_refs")
  if not isinstance(refs, dict):
    return {}
  status: dict[str, str] = {}
  for key, value in sorted(refs.items()):
    if not isinstance(value, str) or not value.strip():
      status[str(key)] = "invalid_ref"
      warnings.append(f"artifact ref {key} is missing or invalid")
      continue
    if not verify_artifacts:
      status[str(key)] = "not_checked"
      continue
    artifact_path = _resolve_run_path(run_dir, value)
    if artifact_path.exists():
      status[str(key)] = "exists"
    else:
      status[str(key)] = "missing"
      warnings.append(f"artifact {key} is missing: {value}")
  return status


def _build_states(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
  buckets: dict[str, dict[str, Any]] = {}
  for finding in findings:
    state_id = str(finding.get("state_id") or "")
    bucket = buckets.setdefault(
      state_id,
      {
        "state_id": state_id,
        "url": None,
        "title": None,
        "route": None,
        "depth": None,
        "counts": {
          "by_decision": _zero_counts(_DECISIONS),
          "parse_status_counts": _zero_counts(_PARSE_STATUSES),
          "by_candidate_type": {},
          "total": 0,
        },
        "findings": [],
      },
    )
    state = finding.get("state")
    if isinstance(state, dict):
      for key in ("url", "title", "route", "depth"):
        if bucket.get(key) is None and state.get(key) is not None:
          bucket[key] = state.get(key)
    bucket["findings"].append(finding.get("confirmation_id"))
    counts = bucket["counts"]
    counts["total"] += 1
    decision = str(finding.get("decision") or "")
    parse_status = str(finding.get("parse_status") or "")
    candidate_type = str(finding.get("candidate_type") or "")
    counts["by_decision"][decision] = counts["by_decision"].get(decision, 0) + 1
    counts["parse_status_counts"][parse_status] = counts["parse_status_counts"].get(parse_status, 0) + 1
    counts["by_candidate_type"][candidate_type] = counts["by_candidate_type"].get(candidate_type, 0) + 1

  return sorted(buckets.values(), key=lambda item: str(item["state_id"]))


def _summary(*, findings: tuple[dict[str, Any], ...], warnings: tuple[dict[str, str], ...]) -> dict[str, Any]:
  decisions = Counter(str(finding.get("decision") or "") for finding in findings)
  parse_statuses = Counter(str(finding.get("parse_status") or "") for finding in findings)
  candidate_types = Counter(str(finding.get("candidate_type") or "") for finding in findings)
  state_ids = {str(finding.get("state_id") or "") for finding in findings}
  return {
    "total_records": len(findings),
    "by_decision": _with_zero_counts(decisions, _DECISIONS),
    "parse_status_counts": _with_zero_counts(parse_statuses, _PARSE_STATUSES),
    "by_candidate_type": dict(sorted(candidate_types.items())),
    "state_count": len(state_ids),
    "warnings_count": len(warnings),
  }


def _evidence_preview(evidence: dict[str, Any]) -> str | None:
  if not evidence:
    return None
  preview = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
  return _truncate_text(preview, EVIDENCE_PREVIEW_LIMIT)


def _find_html_snippet(value: Any) -> str | None:
  if isinstance(value, dict):
    for key in sorted(value):
      child = value[key]
      if key in {"html", "raw_html", "affected_html"} and isinstance(child, str) and child.strip():
        return child.strip()
      found = _find_html_snippet(child)
      if found:
        return found
  if isinstance(value, list):
    for child in value:
      found = _find_html_snippet(child)
      if found:
        return found
  return None


def _truncate_text(value: str, limit: int) -> str:
  if len(value) <= limit:
    return value
  suffix = "...[truncated]"
  if limit <= len(suffix):
    return value[:limit]
  return f"{value[: limit - len(suffix)]}{suffix}"


def _resolve_run_path(run_dir: Path, value: str) -> Path:
  path = Path(value)
  if path.is_absolute():
    return path
  return run_dir / path


def _relative_or_posix(path: Path, base: Path) -> str:
  try:
    return path.relative_to(base).as_posix()
  except ValueError:
    return path.as_posix()


def _format_utc(value: datetime) -> str:
  return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _float_or_none(value: Any) -> float | None:
  if isinstance(value, (int, float)):
    return float(value)
  return None


def _string_list(value: Any) -> list[str]:
  if not isinstance(value, list):
    return []
  return [str(item) for item in value]


def _zero_counts(keys: tuple[str, ...]) -> dict[str, int]:
  return {key: 0 for key in keys}


def _with_zero_counts(counter: Counter[str], keys: tuple[str, ...]) -> dict[str, int]:
  payload = _zero_counts(keys)
  payload.update(dict(sorted(counter.items())))
  return payload


def _first_confidence_semantics(findings: list[dict[str, Any]]) -> Any:
  for finding in findings:
    value = finding.get("confidence_semantics")
    if value:
      return value
  return None
