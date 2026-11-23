from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

_DISPLAY_ORDER = ("violation", "error", "uncertain", "no_violation")


def render_html_report(
  report: dict[str, Any],
  *,
  report_dir: Path,
  include_no_violation: bool,
) -> str:
  source = _dict(report.get("source"))
  confirmation = _dict(report.get("confirmation"))
  summary = _dict(report.get("summary"))
  findings = _list(report.get("findings"))
  states = _list(report.get("states"))
  source_run_dir = Path(str(source.get("run_dir") or ""))

  body: list[str] = [
    "<!doctype html>",
    '<html lang="en">',
    "<head>",
    '  <meta charset="utf-8">',
    '  <meta name="viewport" content="width=device-width, initial-scale=1">',
    f"  <title>{_escape('AccessGraph Model Judgment Report')}</title>",
    "  <style>",
    _stylesheet(),
    "  </style>",
    "</head>",
    "<body>",
    "  <main>",
    "    <header>",
    "      <h1>AccessGraph Model Judgment Report</h1>",
    "      <p>This static report summarizes saved model-judgment records. These records are model judgments over saved context, not ground truth.</p>",
    "    </header>",
    _section("Run Metadata", _metadata_table({
      "Report run": report.get("report_run_id"),
      "Generated": report.get("generated_at"),
      "Source run": source.get("run_dir"),
      "Judgment run": source.get("confirmation_run_id"),
      "Provider": confirmation.get("provider"),
      "Model": confirmation.get("model"),
      "Prompt version": confirmation.get("prompt_version"),
      "Confidence": confirmation.get("confidence_semantics"),
    })),
    _section(
      "Summary",
      "\n".join([
        _counts_table("Decision Counts", _dict(summary.get("by_decision"))),
        _counts_table("Parse Status Counts", _dict(summary.get("parse_status_counts"))),
        _counts_table("Candidate Type Counts", _dict(summary.get("by_candidate_type"))),
        _metadata_table({
          "Total records": summary.get("total_records"),
          "States": summary.get("state_count"),
          "Warnings": summary.get("warnings_count"),
        }),
      ]),
    ),
    _section("State Summary", _state_summary_table(states)),
    '    <section class="findings">',
    "      <h2>Judgments By State</h2>",
  ]

  by_state = _findings_by_state(findings)
  if not by_state:
    body.append("      <p>No model-judgment records were available.</p>")
  for state in states:
    state_dict = _dict(state)
    state_id = str(state_dict.get("state_id") or "")
    state_findings = by_state.get(state_id, [])
    if not state_findings:
      continue
    body.extend(_render_state_findings(
      state_dict,
      state_findings,
      report_dir=report_dir,
      source_run_dir=source_run_dir,
      include_no_violation=include_no_violation,
    ))

  if not include_no_violation:
    no_violation_count = _dict(summary.get("by_decision")).get("no_violation", 0)
    body.extend([
      '      <section class="notice">',
      "        <h3>No Violation Records</h3>",
      f"        <p>{_escape(no_violation_count)} records were classified as <code>no_violation</code>. Detailed no-violation entries are omitted from HTML by default; rerun with <code>--include-no-violation</code> to include them.</p>",
      "      </section>",
    ])

  warnings = _list(report.get("warnings"))
  if warnings:
    body.extend([
      "    </section>",
      "    <section>",
      "      <h2>Warnings</h2>",
      "      <ul>",
    ])
    for warning in warnings:
      warning_dict = _dict(warning)
      candidate = warning_dict.get("candidate_id") or "run"
      body.append(f"        <li><code>{_escape(candidate)}</code>: {_escape(warning_dict.get('message'))}</li>")
    body.extend([
      "      </ul>",
      "    </section>",
    ])
  else:
    body.append("    </section>")

  body.extend([
    "  </main>",
    "</body>",
    "</html>",
  ])
  return "\n".join(body) + "\n"


def _render_state_findings(
  state: dict[str, Any],
  findings: list[dict[str, Any]],
  *,
  report_dir: Path,
  source_run_dir: Path,
  include_no_violation: bool,
) -> list[str]:
  state_id = state.get("state_id") or "unknown"
  lines = [
    '      <section class="state">',
    f"        <h3>State <code>{_escape(state_id)}</code></h3>",
    _metadata_table({
      "Title": state.get("title") or "(untitled)",
      "URL": state.get("url") or "(unknown URL)",
      "Route": state.get("route"),
      "Depth": state.get("depth"),
    }),
  ]
  for category in _DISPLAY_ORDER:
    if category == "no_violation" and not include_no_violation:
      continue
    category_findings = [finding for finding in findings if _display_category(finding) == category]
    if not category_findings:
      continue
    lines.append(f"        <h4>{_escape(_category_title(category))}</h4>")
    for finding in sorted(category_findings, key=_finding_sort_key):
      lines.extend(_render_finding(
        finding,
        report_dir=report_dir,
        source_run_dir=source_run_dir,
      ))
  lines.append("      </section>")
  return lines


def _render_finding(
  finding: dict[str, Any],
  *,
  report_dir: Path,
  source_run_dir: Path,
) -> list[str]:
  source_excerpt = _dict(finding.get("source_candidate_excerpt"))
  context = _dict(finding.get("context"))
  lines = [
    '        <article class="finding">',
    f"          <h5><code>{_escape(finding.get('candidate_type'))}</code> - <code>{_escape(finding.get('candidate_id'))}</code></h5>",
    _metadata_table({
      "Decision": _code(finding.get("decision")),
      "Confidence": finding.get("confidence"),
      "Parse status": _code(finding.get("parse_status")),
      "State": _code(finding.get("state_id")),
      "Judgment id": _code(finding.get("confirmation_id")),
    }, escape_values=False),
  ]
  if context:
    lines.append(_metadata_table({
      "Requested context": _code(context.get("requested_context_mode")),
      "Selected context": _code(context.get("selected_context_mode")),
      "Resolved context": _code(context.get("resolved_context_mode") or context.get("context_mode")),
      "Graph context included": context.get("graph_context_included"),
      "Adaptive fallback": context.get("adaptive_fallback_triggered"),
      "Attempt count": context.get("attempt_count"),
      "Final decision source": _code(context.get("final_decision_source")),
    }, title="Context", escape_values=False))
  if finding.get("error"):
    lines.append(f'          <p class="error"><strong>Error:</strong> {_escape(finding.get("error"))}</p>')

  lines.extend([
    "          <h6>Reason</h6>",
    f"          <p>{_escape(finding.get('reason') or '(none)')}</p>",
    "          <h6>Supporting Evidence</h6>",
  ])
  supporting = _list(finding.get("supporting_evidence"))
  if supporting:
    lines.append("          <ul>")
    for item in supporting:
      lines.append(f"            <li>{_escape(item)}</li>")
    lines.append("          </ul>")
  else:
    lines.append("          <p>(none)</p>")

  affected_html = source_excerpt.get("affected_html")
  if affected_html:
    lines.extend([
      "          <h6>Affected HTML Snippet</h6>",
      f"          <pre><code>{_escape(affected_html)}</code></pre>",
    ])

  if source_excerpt:
    primary_ref = source_excerpt.get("primary_element_ref")
    lines.append(_metadata_table({
      "Selection reason": ", ".join(str(item) for item in _list(source_excerpt.get("selection_reason"))),
      "Required context": ", ".join(str(item) for item in _list(source_excerpt.get("required_context"))),
      "Element refs": source_excerpt.get("element_ref_count"),
      "Evidence keys": ", ".join(str(item) for item in _list(source_excerpt.get("evidence_keys"))),
      "Primary element": json.dumps(primary_ref, ensure_ascii=False, sort_keys=True) if primary_ref else None,
    }, title="Source Candidate Excerpt"))

  source_ref = _dict(finding.get("source_candidate_ref"))
  if source_ref:
    path = str(source_ref.get("path") or "")
    line_number = source_ref.get("line_number")
    lines.append(f"          <p>Source candidate: <code>{_escape(path)}:{_escape(line_number)}</code></p>")

  artifact_refs = _dict(finding.get("artifact_refs"))
  if artifact_refs:
    lines.extend([
      "          <h6>Artifacts</h6>",
      "          <ul>",
    ])
    status_by_key = _dict(finding.get("artifact_status"))
    for key, value in sorted(artifact_refs.items()):
      if isinstance(value, str) and value.strip():
        link = _artifact_link(value, report_dir=report_dir, source_run_dir=source_run_dir)
        status = status_by_key.get(key)
        lines.append(
          f'            <li><code>{_escape(key)}</code>: <a href="{_attribute(link)}">{_escape(value)}</a> ({_escape(status)})</li>'
        )
      else:
        lines.append(f"            <li><code>{_escape(key)}</code>: invalid ref</li>")
    lines.append("          </ul>")

  warnings = _list(finding.get("warnings"))
  if warnings:
    lines.extend([
      "          <h6>Warnings</h6>",
      "          <ul>",
    ])
    for warning in warnings:
      lines.append(f"            <li>{_escape(warning)}</li>")
    lines.append("          </ul>")

  lines.append("        </article>")
  return lines


def _section(title: str, inner_html: str) -> str:
  return f"    <section>\n      <h2>{_escape(title)}</h2>\n{inner_html}\n    </section>"


def _metadata_table(
  values: dict[str, Any],
  *,
  title: str | None = None,
  escape_values: bool = True,
) -> str:
  rows: list[str] = []
  for key, value in values.items():
    if value is None or value == "":
      continue
    rendered = _escape(value) if escape_values else str(value)
    rows.append(f"            <tr><th>{_escape(key)}</th><td>{rendered}</td></tr>")
  if not rows:
    return ""
  heading = f"          <h6>{_escape(title)}</h6>\n" if title else ""
  return f"{heading}          <table>\n{chr(10).join(rows)}\n          </table>"


def _counts_table(title: str, counts: dict[str, Any]) -> str:
  rows = [
    f"            <tr><td><code>{_escape(key)}</code></td><td>{_escape(value)}</td></tr>"
    for key, value in sorted(counts.items())
  ]
  return (
    f"          <h3>{_escape(title)}</h3>\n"
    "          <table>\n"
    "            <tr><th>Key</th><th>Count</th></tr>\n"
    f"{chr(10).join(rows)}\n"
    "          </table>"
  )


def _state_summary_table(states: list[Any]) -> str:
  rows = [
    "            <tr><th>State</th><th>Title</th><th>URL</th><th>Violations</th><th>Errors</th><th>Uncertain</th><th>No violation</th></tr>"
  ]
  for state in states:
    state_dict = _dict(state)
    counts = _dict(_dict(state_dict.get("counts")).get("by_decision"))
    parse_counts = _dict(_dict(state_dict.get("counts")).get("parse_status_counts"))
    errors = sum(int(parse_counts.get(key, 0) or 0) for key in ("malformed_json", "schema_error", "id_mismatch", "client_error"))
    rows.append(
      "            <tr>"
      f"<td><code>{_escape(state_dict.get('state_id'))}</code></td>"
      f"<td>{_escape(state_dict.get('title') or '')}</td>"
      f"<td>{_escape(state_dict.get('url') or '')}</td>"
      f"<td>{_escape(counts.get('violation', 0))}</td>"
      f"<td>{_escape(errors)}</td>"
      f"<td>{_escape(counts.get('uncertain', 0))}</td>"
      f"<td>{_escape(counts.get('no_violation', 0))}</td>"
      "</tr>"
    )
  return f"          <table>\n{chr(10).join(rows)}\n          </table>"


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


def _code(value: Any) -> str:
  if value is None or value == "":
    return ""
  return f"<code>{_escape(value)}</code>"


def _dict(value: Any) -> dict[str, Any]:
  return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
  return value if isinstance(value, list) else []


def _attribute(value: Any) -> str:
  return html.escape(str(value), quote=True)


def _escape(value: Any) -> str:
  return html.escape(str(value), quote=False)


def _stylesheet() -> str:
  return """
    :root { color-scheme: light; font-family: Arial, sans-serif; line-height: 1.45; }
    body { margin: 0; background: #f6f7f9; color: #111827; }
    main { max-width: 1160px; margin: 0 auto; padding: 32px 20px 56px; }
    header, section, article { background: #fff; border: 1px solid #d7dce2; border-radius: 6px; }
    header { padding: 24px; margin-bottom: 16px; }
    section { padding: 20px; margin: 16px 0; }
    article { padding: 16px; margin: 12px 0; }
    h1, h2, h3, h4, h5, h6 { margin: 0 0 12px; line-height: 1.25; }
    h1 { font-size: 1.8rem; }
    h2 { font-size: 1.35rem; }
    h3 { font-size: 1.1rem; }
    h4, h5, h6 { font-size: 1rem; }
    p { margin: 0 0 12px; }
    table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; font-size: 0.95rem; }
    th, td { border: 1px solid #d7dce2; padding: 7px 9px; text-align: left; vertical-align: top; }
    th { background: #eef1f5; font-weight: 600; width: 28%; }
    code { background: #eef1f5; border-radius: 4px; padding: 1px 4px; }
    pre { background: #111827; color: #f9fafb; border-radius: 6px; padding: 12px; overflow: auto; }
    pre code { background: transparent; color: inherit; padding: 0; }
    a { color: #0f5e9c; }
    .state { background: #fbfcfd; }
    .finding { background: #fff; }
    .notice { background: #fff8e5; border-color: #e6c86e; }
    .error { color: #9f1239; }
  """.strip()
