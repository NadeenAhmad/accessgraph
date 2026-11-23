from __future__ import annotations

from datetime import datetime, timezone

from src.analysis.reporting.builder import build_report_payload
from src.analysis.reporting.models import ConfirmationReportOptions
from src.analysis.reporting.reader import load_confirmation_run
from tests.developer_report_test_helpers import write_synthetic_confirmation_run


def test_builder_groups_by_state_and_counts_all_records(tmp_path):
  write_synthetic_confirmation_run(tmp_path)
  loaded = load_confirmation_run(tmp_path, "confirm_report_source")
  report = build_report_payload(
    loaded,
    options=ConfirmationReportOptions(
      run_dir=tmp_path,
      confirmation_run_id="confirm_report_source",
    ),
    report_run_id="report_one",
    generated_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
  )

  assert report["summary"]["total_records"] == 4
  assert report["summary"]["by_decision"]["violation"] == 1
  assert report["summary"]["by_decision"]["no_violation"] == 1
  assert report["summary"]["parse_status_counts"]["id_mismatch"] == 1
  assert report["summary"]["state_count"] == 2
  assert [state["state_id"] for state in report["states"]] == ["state_0001", "state_0002"]
  assert report["states"][0]["counts"]["total"] == 3


def test_builder_includes_compact_source_excerpt_and_truncated_affected_html(tmp_path):
  write_synthetic_confirmation_run(tmp_path)
  loaded = load_confirmation_run(tmp_path, "confirm_report_source")
  report = build_report_payload(
    loaded,
    options=ConfirmationReportOptions(
      run_dir=tmp_path,
      confirmation_run_id="confirm_report_source",
    ),
    report_run_id="report_one",
  )

  finding = next(item for item in report["findings"] if item["candidate_id"] == "cand_violation")
  excerpt = finding["source_candidate_excerpt"]

  assert excerpt["selection_reason"] == ["test_reason"]
  assert excerpt["required_context"] == ["label purpose", "section context"]
  assert excerpt["element_ref_count"] == 1
  assert excerpt["primary_element_ref"]["selector"] == "#target"
  assert "primary" in excerpt["evidence_keys"]
  assert excerpt["affected_html"].endswith("...[truncated]")
  assert len(excerpt["affected_html"]) <= 600


def test_builder_warns_but_continues_when_source_candidates_or_artifacts_are_missing(tmp_path):
  write_synthetic_confirmation_run(tmp_path, include_missing_refs=True)
  loaded = load_confirmation_run(tmp_path, "confirm_report_source")
  report = build_report_payload(
    loaded,
    options=ConfirmationReportOptions(
      run_dir=tmp_path,
      confirmation_run_id="confirm_report_source",
    ),
    report_run_id="report_one",
  )

  missing = next(item for item in report["findings"] if item["candidate_id"] == "cand_missing")

  assert missing["source_candidate_excerpt"] is None
  assert any("source candidate file is missing" in warning for warning in missing["warnings"])
  assert any("artifact metadata is missing" in warning for warning in missing["warnings"])
  assert report["summary"]["warnings_count"] >= 2


def test_builder_can_skip_source_loading_and_artifact_verification(tmp_path):
  write_synthetic_confirmation_run(tmp_path)
  loaded = load_confirmation_run(tmp_path, "confirm_report_source")
  report = build_report_payload(
    loaded,
    options=ConfirmationReportOptions(
      run_dir=tmp_path,
      confirmation_run_id="confirm_report_source",
      load_source_candidates=False,
      verify_artifacts=False,
    ),
    report_run_id="report_one",
  )

  finding = report["findings"][0]

  assert finding["source_candidate_excerpt"] is None
  assert set(finding["artifact_status"].values()) == {"not_checked"}
