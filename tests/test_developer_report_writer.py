from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.analysis.reporting.models import ConfirmationReportOptions
from src.analysis.reporting.runner import run_confirmation_report
from tests.developer_report_test_helpers import write_synthetic_confirmation_run


def test_writer_creates_markdown_html_json_and_manifest(tmp_path):
  write_synthetic_confirmation_run(tmp_path)

  result = run_confirmation_report(
    options=ConfirmationReportOptions(
      run_dir=tmp_path,
      confirmation_run_id="confirm_report_source",
      report_run_id="developer_report",
    ),
    generated_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
  )

  report_dir = result.output_dir
  markdown = (report_dir / "report.md").read_text(encoding="utf-8")
  html = (report_dir / "report.html").read_text(encoding="utf-8")
  report_json = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
  manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))

  assert (report_dir / "report.md").exists()
  assert (report_dir / "report.html").exists()
  assert (report_dir / "report.json").exists()
  assert (report_dir / "manifest.json").exists()
  assert report_json["summary"]["total_records"] == 4
  assert len(report_json["findings"]) == 4
  assert manifest["outputs"]["report_markdown"] == "report.md"
  assert manifest["outputs"]["report_html"] == "report.html"
  assert manifest["confirmation_run_id"] == "confirm_report_source"
  assert manifest["confirmation_dir"].endswith("/confirmations/confirm_report_source")
  assert manifest["inputs"]["confirmation_manifest"] == "confirmations/confirm_report_source/manifest.json"
  assert manifest["inputs"]["confirmations"] == "confirmations/confirm_report_source/confirmations.jsonl"
  assert manifest["options"]["include_no_violation"] is False
  assert manifest["options"]["load_source_candidates"] is True
  assert manifest["options"]["verify_artifacts"] is True
  assert manifest["summary"]["total_records"] == 4
  assert manifest["summary"]["warnings_count"] == 0
  assert manifest["generator"]["name"] == "developer_confirmation_report"
  assert "invocation" in manifest
  assert "AccessGraph Developer Confirmation Report" in markdown
  assert "AccessGraph Model Judgment Report" in html


def test_markdown_excludes_no_violation_details_by_default_but_json_keeps_them(tmp_path):
  write_synthetic_confirmation_run(tmp_path)

  result = run_confirmation_report(
    options=ConfirmationReportOptions(
      run_dir=tmp_path,
      confirmation_run_id="confirm_report_source",
      report_run_id="developer_report",
    )
  )

  markdown = (result.output_dir / "report.md").read_text(encoding="utf-8")
  html = (result.output_dir / "report.html").read_text(encoding="utf-8")
  report_json = json.loads((result.output_dir / "report.json").read_text(encoding="utf-8"))

  assert "cand_no_violation" not in markdown
  assert "cand_no_violation" not in html
  assert "`1` records were classified as `no_violation`" in markdown
  assert "records were classified as <code>no_violation</code>" in html
  assert any(finding["candidate_id"] == "cand_no_violation" for finding in report_json["findings"])


def test_markdown_include_no_violation_adds_no_violation_details(tmp_path):
  write_synthetic_confirmation_run(tmp_path)

  result = run_confirmation_report(
    options=ConfirmationReportOptions(
      run_dir=tmp_path,
      confirmation_run_id="confirm_report_source",
      report_run_id="developer_report",
      include_no_violation=True,
    )
  )

  markdown = (result.output_dir / "report.md").read_text(encoding="utf-8")
  html = (result.output_dir / "report.html").read_text(encoding="utf-8")

  assert "No Violation Appendix" in markdown
  assert "cand_no_violation" in markdown
  assert "cand_no_violation" in html


def test_html_contains_core_fields_artifact_links_and_escaped_content(tmp_path):
  confirmation_dir = write_synthetic_confirmation_run(tmp_path)
  confirmations_path = confirmation_dir / "confirmations.jsonl"
  records = [
    json.loads(line)
    for line in confirmations_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
  ]
  records[0]["reason"] = '<script>alert("x")</script>'
  records[0]["supporting_evidence"] = ["<img src=x onerror=alert(1)>"]
  records[0]["escalation_triggered"] = True
  records[0]["attempt_count"] = 2
  records[0]["selected_context_mode"] = "isolated_state"
  records[0]["resolved_context_mode"] = "graph_context"
  confirmations_path.write_text(
    "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
    encoding="utf-8",
  )

  result = run_confirmation_report(
    options=ConfirmationReportOptions(
      run_dir=tmp_path,
      confirmation_run_id="confirm_report_source",
      report_run_id="developer_report",
    )
  )

  html = (result.output_dir / "report.html").read_text(encoding="utf-8")
  report_json = json.loads((result.output_dir / "report.json").read_text(encoding="utf-8"))
  violation = next(finding for finding in report_json["findings"] if finding["candidate_id"] == "cand_violation")

  assert "<script>" not in html
  assert "&lt;script&gt;alert(\"x\")&lt;/script&gt;" in html
  assert "&lt;img src=x onerror=alert(1)&gt;" in html
  assert "cand_violation" in html
  assert "button-label-mismatch" in html
  assert "state_0001" in html
  assert "violation" in html
  assert "states/state_0001/screenshot.png" in html
  assert "../../states/state_0001/screenshot.png" in html
  assert violation["context"]["requested_context_mode"] == "adaptive_context"
  assert violation["context"]["selected_context_mode"] == "isolated_state"
  assert violation["context"]["resolved_context_mode"] == "graph_context"
  assert violation["context"]["adaptive_fallback_triggered"] is True
  assert violation["context"]["attempt_count"] == 2


def test_markdown_surfaces_uncertain_errors_and_artifact_links(tmp_path):
  write_synthetic_confirmation_run(tmp_path)

  result = run_confirmation_report(
    options=ConfirmationReportOptions(
      run_dir=tmp_path,
      confirmation_run_id="confirm_report_source",
      report_run_id="developer_report",
    )
  )

  markdown = (result.output_dir / "report.md").read_text(encoding="utf-8")

  assert "Uncertain Records" in markdown
  assert "Errors And Non-Parsed Records" in markdown
  assert "cand_uncertain" in markdown
  assert "cand_error" in markdown
  assert "[states/state_0001/screenshot.png](../../states/state_0001/screenshot.png)" in markdown
  assert "```html" in markdown
  assert "...[truncated]" in markdown
  assert "fix suggestion" not in markdown.lower()


def test_writer_prevents_overwrite_without_flag(tmp_path):
  write_synthetic_confirmation_run(tmp_path)
  run_confirmation_report(
    options=ConfirmationReportOptions(
      run_dir=tmp_path,
      confirmation_run_id="confirm_report_source",
      report_run_id="developer_report",
    )
  )

  with pytest.raises(FileExistsError, match="already exists"):
    run_confirmation_report(
      options=ConfirmationReportOptions(
        run_dir=tmp_path,
        confirmation_run_id="confirm_report_source",
        report_run_id="developer_report",
      )
    )


def test_writer_refuses_core_run_artifact_output_dir(tmp_path):
  write_synthetic_confirmation_run(tmp_path)

  with pytest.raises(ValueError, match="core run artifact"):
    run_confirmation_report(
      options=ConfirmationReportOptions(
        run_dir=tmp_path,
        confirmation_run_id="confirm_report_source",
        output_dir=tmp_path,
        overwrite=True,
      )
    )
