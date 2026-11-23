from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_DISPLAY_ORDER = ("violation", "error", "uncertain", "no_violation")


def render_markdown_report(
  report: dict[str, Any],
  *,
  report_dir: Path,
  include_no_violation: bool,
) -> str:
  lines: list[str] = []
  source = _dict(report.get("source"))
  confirmation = _dict(report.get("confirmation"))
  summary = _dict(report.get("summary"))

  lines.append("# AccessGraph Developer Confirmation Report")
  lines.append("")
  lines.append("This report summarizes one offline confirmation run. It does not call an LLM, rerun confirmation, or invent remediation advice.")
  lines.append("")
  lines.append("## Run Metadata")
  lines.append("")
  lines.extend(
    _bullet_table(
      {
        "Report run": report.get("report_run_id"),
        "Generated": report.get("generated_at"),
        "Source run": source.get("run_dir"),
        "Confirmation run": source.get("confirmation_run_id"),
        "Provider": confirmation.get("provider"),
        "Model": confirmation.get("model"),
        "Prompt version": confirmation.get("prompt_version"),
        "Confidence": confirmation.get("confidence_semantics"),
      }
    )
  )
  lines.append("")

  lines.append("## Summary")
  lines.append("")
  lines.extend(_counts_table("Decision counts", _dict(summary.get("by_decision"))))
  lines.append("")
  lines.extend(_counts_table("Parse status counts", _dict(summary.get("parse_status_counts"))))
  lines.append("")
  lines.extend(_counts_table("Candidate type counts", _dict(summary.get("by_candidate_type"))))
  lines.append("")
  lines.extend(
    _bullet_table(
      {
        "Total records": summary.get("total_records"),
        "States": summary.get("state_count"),
        "Warnings": summary.get("warnings_count"),
      }
    )
  )
  lines.append("")

  lines.append("## State Summary")
  lines.append("")
  lines.extend(_state_summary_table(_list(report.get("states"))))
  lines.append("")

  lines.append("## Findings By State")
  lines.append("")
  findings = _list(report.get("findings"))
  by_state = _findings_by_state(findings)
  if not by_state:
    lines.append("No confirmation records were available.")
    lines.append("")
  for state in _list(report.get("states")):
    state_id = str(_dict(state).get("state_id") or "")
    state_findings = by_state.get(state_id, [])
    if not state_findings:
      continue
    lines.extend(_state_heading(_dict(state)))
    for category in _DISPLAY_ORDER:
      if category == "no_violation" and not include_no_violation:
        continue
      category_findings = [finding for finding in state_findings if _display_category(finding) == category]
      if not category_findings:
        continue
      lines.append(f"### {_category_title(category)}")
      lines.append("")
      for finding in sorted(category_findings, key=_finding_sort_key):
        lines.extend(_render_finding(finding, report_dir=report_dir, source_run_dir=Path(str(source.get("run_dir") or ""))))
        lines.append("")

  if not include_no_violation:
    no_violation_count = _dict(summary.get("by_decision")).get("no_violation", 0)
    lines.append("## No Violation Records")
    lines.append("")
    lines.append(f"`{no_violation_count}` records were classified as `no_violation`. Detailed no-violation entries are omitted from Markdown by default; rerun with `--include-no-violation` to include them.")
    lines.append("")

  warnings = _list(report.get("warnings"))
  if warnings:
    lines.append("## Warnings")
    lines.append("")
    for warning in warnings:
      warning_dict = _dict(warning)
      candidate = warning_dict.get("candidate_id") or "run"
      lines.append(f"- `{candidate}`: {warning_dict.get('message')}")
    lines.append("")

  return "\n".join(lines).rstrip() + "\n"


def _render_finding(finding: dict[str, Any], *, report_dir: Path, source_run_dir: Path) -> list[str]:
  source_excerpt = _dict(finding.get("source_candidate_excerpt"))
  lines = [
    f"#### `{finding.get('candidate_type')}` - `{finding.get('candidate_id')}`",
    "",
  ]
  lines.extend(
    _bullet_table(
      {
        "Decision": f"`{finding.get('decision')}`",
        "Confidence": finding.get("confidence"),
        "Parse status": f"`{finding.get('parse_status')}`",
        "Confirmation id": f"`{finding.get('confirmation_id')}`",
        "State": f"`{finding.get('state_id')}`",
      }
    )
  )
  if finding.get("error"):
    lines.append(f"- Error: {finding.get('error')}")
  lines.append("")
  lines.append("**Reason**")
  lines.append("")
  lines.append(str(finding.get("reason") or "(none)"))
  lines.append("")
  lines.append("**Supporting Evidence**")
  lines.append("")
  supporting = _list(finding.get("supporting_evidence"))
  if supporting:
    for item in supporting:
      lines.append(f"- {item}")
  else:
    lines.append("- (none)")

  affected_html = source_excerpt.get("affected_html")
  if affected_html:
    lines.append("")
    lines.append("**Affected HTML Snippet**")
    lines.append("")
    lines.append("```html")
    lines.append(str(affected_html))
    lines.append("```")

  if source_excerpt:
    lines.append("")
    lines.append("**Source Candidate Excerpt**")
    lines.append("")
    primary_ref = source_excerpt.get("primary_element_ref")
    lines.extend(
      _bullet_table(
        {
          "Selection reason": ", ".join(_list(source_excerpt.get("selection_reason"))),
          "Required context": ", ".join(_list(source_excerpt.get("required_context"))),
          "Element refs": source_excerpt.get("element_ref_count"),
          "Evidence keys": ", ".join(_list(source_excerpt.get("evidence_keys"))),
          "Primary element": _compact_json(primary_ref) if primary_ref else None,
        }
      )
    )

  source_ref = _dict(finding.get("source_candidate_ref"))
  if source_ref:
    lines.append("")
    path = str(source_ref.get("path") or "")
    line = source_ref.get("line_number")
    lines.append(f"Source candidate: `{path}:{line}`")

  artifact_refs = _dict(finding.get("artifact_refs"))
  if artifact_refs:
    lines.append("")
    lines.append("**Artifacts**")
    lines.append("")
    for key, value in sorted(artifact_refs.items()):
      if isinstance(value, str) and value.strip():
        link = _artifact_link(value, report_dir=report_dir, source_run_dir=source_run_dir)
        status = _dict(finding.get("artifact_status")).get(key)
        lines.append(f"- `{key}`: [{value}]({link}) ({status})")
      else:
        lines.append(f"- `{key}`: invalid ref")

  warnings = _list(finding.get("warnings"))
  if warnings:
    lines.append("")
    lines.append("**Warnings**")
    lines.append("")
    for warning in warnings:
      lines.append(f"- {warning}")

  return lines


def _state_heading(state: dict[str, Any]) -> list[str]:
  state_id = state.get("state_id") or "unknown"
  title = state.get("title") or "(untitled)"
  url = state.get("url") or "(unknown URL)"
  return [
    f"### State `{state_id}`",
    "",
    f"- Title: {title}",
    f"- URL: {url}",
    "",
  ]


def _state_summary_table(states: list[Any]) -> list[str]:
  lines = ["| State | Title | URL | Violations | Errors | Uncertain | No violation |", "| --- | --- | --- | ---: | ---: | ---: | ---: |"]
  for state in states:
    state_dict = _dict(state)
    counts = _dict(_dict(state_dict.get("counts")).get("by_decision"))
    parse_counts = _dict(_dict(state_dict.get("counts")).get("parse_status_counts"))
    errors = sum(int(parse_counts.get(key, 0) or 0) for key in ("malformed_json", "schema_error", "id_mismatch", "client_error"))
    lines.append(
      "| "
      f"`{state_dict.get('state_id')}` | "
      f"{_escape_pipes(state_dict.get('title') or '')} | "
      f"{_escape_pipes(state_dict.get('url') or '')} | "
      f"{counts.get('violation', 0)} | "
      f"{errors} | "
      f"{counts.get('uncertain', 0)} | "
      f"{counts.get('no_violation', 0)} |"
    )
  return lines


def _counts_table(title: str, counts: dict[str, Any]) -> list[str]:
  lines = [f"**{title}**", "", "| Key | Count |", "| --- | ---: |"]
  for key, value in sorted(counts.items()):
    lines.append(f"| `{key}` | {value} |")
  return lines


def _bullet_table(values: dict[str, Any]) -> list[str]:
  lines: list[str] = []
  for key, value in values.items():
    if value is None or value == "":
      continue
    lines.append(f"- {key}: {value}")
  return lines


def _findings_by_state(findings: list[Any]) -> dict[str, list[dict[str, Any]]]:
  buckets: dict[str, list[dict[str, Any]]] = {}
  for finding in findings:
    finding_dict = _dict(finding)
    buckets.setdefault(str(finding_dict.get("state_id") or ""), []).append(finding_dict)
  return buckets


def _display_category(finding: dict[str, Any]) -> str:
  if finding.get("parse_status") != "parsed":
    return "error"
  return str(finding.get("decision") or "")


def _category_title(category: str) -> str:
  return {
    "violation": "Likely Violations",
    "error": "Errors And Non-Parsed Records",
    "uncertain": "Uncertain Records",
    "no_violation": "No Violation Appendix",
  }.get(category, category)


def _finding_sort_key(finding: dict[str, Any]) -> tuple[str, float, str]:
  confidence = finding.get("confidence")
  if not isinstance(confidence, (int, float)):
    confidence = -1.0
  return (
    str(finding.get("candidate_type") or ""),
    -float(confidence),
    str(finding.get("candidate_id") or ""),
  )


def _artifact_link(value: str, *, report_dir: Path, source_run_dir: Path) -> str:
  target = Path(value)
  if not target.is_absolute():
    target = source_run_dir / target
  try:
    return Path(os.path.relpath(target, report_dir)).as_posix()
  except ValueError:
    return target.as_posix()


def _compact_json(value: Any) -> str:
  import json

  return "`" + json.dumps(value, ensure_ascii=False, sort_keys=True) + "`"


def _escape_pipes(value: Any) -> str:
  return str(value).replace("|", "\\|")


def _dict(value: Any) -> dict[str, Any]:
  return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
  return value if isinstance(value, list) else []
