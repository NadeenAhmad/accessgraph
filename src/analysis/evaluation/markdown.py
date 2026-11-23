from __future__ import annotations

from typing import Any


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
  lines: list[str] = [
    "# AccessGraph Local Confirmation Comparison",
    "",
    "This is a descriptive comparison of existing confirmation runs. It does not call providers, attach labels, or compute accuracy, precision, recall, or F1.",
    "",
    "## Overview",
    "",
    f"- Comparison run: `{comparison.get('comparison_run_id')}`",
    f"- Generated: {comparison.get('generated_at')}",
    f"- Source run: {comparison.get('source_run_dir')}",
  ]
  summary = comparison.get("summary") if isinstance(comparison.get("summary"), dict) else {}
  lines.extend(
    [
      f"- Confirmation runs: {summary.get('confirmation_run_count', 0)}",
      f"- Total records: {summary.get('total_records', 0)}",
      f"- Unique candidates: {summary.get('unique_candidate_count', 0)}",
      f"- Overlapping candidates: {summary.get('overlapping_candidate_count', 0)}",
      f"- Warnings: {summary.get('warnings_count', 0)}",
      "",
    ]
  )

  _append_compared_runs(lines, comparison)
  _append_decision_by_run(lines, comparison)
  _append_parse_by_run(lines, comparison)
  _append_candidate_type_distribution(lines, comparison)
  _append_decision_by_candidate_type(lines, comparison)
  _append_confidence_summary(lines, comparison)
  _append_runtime_token_summary(lines, comparison)
  _append_candidate_comparisons(lines, comparison)
  _append_warnings(lines, comparison)
  return "\n".join(lines).rstrip() + "\n"


def _append_compared_runs(lines: list[str], comparison: dict[str, Any]) -> None:
  runs = _list(comparison.get("included_confirmation_runs"))
  lines.extend(["## Compared Runs", ""])
  lines.extend(
    _table(
      ["Run", "Provider", "Model", "Prompt", "Records", "Duration ms"],
      [
        [
          f"`{run.get('confirmation_run_id')}`",
          run.get("provider"),
          run.get("model"),
          run.get("prompt_version"),
          run.get("record_count"),
          run.get("manifest_duration_ms"),
        ]
        for run in runs
      ],
    )
  )
  lines.append("")


def _append_decision_by_run(lines: list[str], comparison: dict[str, Any]) -> None:
  lines.extend(["## Decision Distribution By Run", ""])
  rows = []
  for item in _list(comparison.get("summary_by_run")):
    counts = _dict(item.get("by_decision"))
    rows.append(
      [
        f"`{item.get('confirmation_run_id')}`",
        counts.get("violation", 0),
        counts.get("uncertain", 0),
        counts.get("no_violation", 0),
        item.get("total_records", 0),
      ]
    )
  lines.extend(_table(["Run", "Violation", "Uncertain", "No violation", "Total"], rows))
  lines.append("")


def _append_parse_by_run(lines: list[str], comparison: dict[str, Any]) -> None:
  lines.extend(["## Parse Status By Run", ""])
  rows = []
  for item in _list(comparison.get("summary_by_run")):
    counts = _dict(item.get("parse_status_counts"))
    rows.append(
      [
        f"`{item.get('confirmation_run_id')}`",
        counts.get("parsed", 0),
        counts.get("id_mismatch", 0),
        counts.get("malformed_json", 0),
        counts.get("schema_error", 0),
        counts.get("client_error", 0),
      ]
    )
  lines.extend(_table(["Run", "Parsed", "ID mismatch", "Malformed", "Schema", "Client"], rows))
  lines.append("")


def _append_candidate_type_distribution(lines: list[str], comparison: dict[str, Any]) -> None:
  lines.extend(["## Candidate Type Distribution", ""])
  rows = [
    [f"`{item.get('candidate_type')}`", item.get("total_records", 0), item.get("state_count", 0)]
    for item in _list(comparison.get("summary_by_candidate_type"))
  ]
  lines.extend(_table(["Candidate type", "Records", "States"], rows))
  lines.append("")


def _append_decision_by_candidate_type(lines: list[str], comparison: dict[str, Any]) -> None:
  lines.extend(["## Decision Distribution By Candidate Type", ""])
  rows = []
  for item in _list(comparison.get("summary_by_candidate_type")):
    counts = _dict(item.get("by_decision"))
    rows.append(
      [
        f"`{item.get('candidate_type')}`",
        counts.get("violation", 0),
        counts.get("uncertain", 0),
        counts.get("no_violation", 0),
        item.get("total_records", 0),
      ]
    )
  lines.extend(_table(["Candidate type", "Violation", "Uncertain", "No violation", "Total"], rows))
  lines.append("")


def _append_confidence_summary(lines: list[str], comparison: dict[str, Any]) -> None:
  lines.extend(["## Confidence Summary", ""])
  rows = []
  for item in _list(comparison.get("summary_by_run")):
    summary = _dict(item.get("confidence_summary"))
    rows.append(
      [
        f"`{item.get('confirmation_run_id')}`",
        summary.get("count", 0),
        _format_number(summary.get("min")),
        _format_number(summary.get("mean")),
        _format_number(summary.get("max")),
      ]
    )
  lines.extend(_table(["Run", "Count", "Min", "Mean", "Max"], rows))
  lines.append("")


def _append_runtime_token_summary(lines: list[str], comparison: dict[str, Any]) -> None:
  lines.extend(["## Runtime / Token / Cost Summary", ""])
  rows = []
  for item in _list(comparison.get("summary_by_run")):
    runtime = _dict(item.get("runtime_summary"))
    tokens = _dict(item.get("token_summary"))
    rows.append(
      [
        f"`{item.get('confirmation_run_id')}`",
        item.get("manifest_duration_ms"),
        _format_number(runtime.get("sum")),
        _format_number(runtime.get("mean")),
        tokens.get("prompt_tokens_total", 0),
        tokens.get("completion_tokens_total", 0),
        tokens.get("total_tokens_total", 0),
        _format_number(tokens.get("estimated_cost_usd_total")),
      ]
    )
  lines.extend(
    _table(
      ["Run", "Manifest ms", "Runtime ms total", "Runtime ms mean", "Prompt tok", "Completion tok", "Total tok", "Est. cost USD"],
      rows,
    )
  )
  lines.append("")


def _append_candidate_comparisons(lines: list[str], comparison: dict[str, Any]) -> None:
  comparisons = _list(comparison.get("candidate_comparisons"))
  lines.extend(["## Candidate-Level Agreement / Disagreement", ""])
  if not comparisons:
    lines.extend(["No overlapping `candidate_id` values were found across the compared runs.", ""])
    return
  rows = []
  for item in comparisons:
    rows.append(
      [
        f"`{item.get('candidate_id')}`",
        ", ".join(f"`{value}`" for value in _list(item.get("candidate_types"))),
        ", ".join(f"`{value}`" for value in _list(item.get("state_ids"))),
        "yes" if item.get("decision_agreement") else "no",
        ", ".join(f"`{value}`" for value in _list(item.get("decisions"))),
        "yes" if item.get("parse_status_agreement") else "no",
        ", ".join(f"`{value}`" for value in _list(item.get("parse_statuses"))),
      ]
    )
  lines.extend(
    _table(
      ["Candidate", "Types", "States", "Decision agreement", "Decisions", "Parse agreement", "Parse statuses"],
      rows,
    )
  )
  lines.append("")


def _append_warnings(lines: list[str], comparison: dict[str, Any]) -> None:
  warnings = _list(comparison.get("warnings"))
  lines.extend(["## Warnings / Limitations", ""])
  lines.append("- This comparison is descriptive only; no labels or ground-truth metrics are used.")
  lines.append("- `confirmations.jsonl` is the canonical input for each compared run.")
  if warnings:
    for warning in warnings:
      if isinstance(warning, dict):
        lines.append(f"- `{warning.get('scope', '')}`: {warning.get('message', '')}")
      else:
        lines.append(f"- {warning}")
  else:
    lines.append("- No structural warnings were recorded.")
  lines.append("")


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
  if not rows:
    rows = [["" for _ in headers]]
  lines = [
    "| " + " | ".join(_escape_cell(header) for header in headers) + " |",
    "| " + " | ".join("---" for _ in headers) + " |",
  ]
  for row in rows:
    lines.append("| " + " | ".join(_escape_cell(value) for value in row) + " |")
  return lines


def _escape_cell(value: Any) -> str:
  if value is None:
    return ""
  return str(value).replace("|", "\\|").replace("\n", " ")


def _format_number(value: Any) -> str:
  if value is None:
    return ""
  if isinstance(value, float):
    return f"{value:.4f}".rstrip("0").rstrip(".")
  return str(value)


def _list(value: Any) -> list[Any]:
  return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
  return value if isinstance(value, dict) else {}
