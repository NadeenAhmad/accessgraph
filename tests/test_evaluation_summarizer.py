from __future__ import annotations

from datetime import datetime, timezone

from src.analysis.evaluation.models import ConfirmationComparisonOptions
from src.analysis.evaluation.reader import load_confirmation_runs
from src.analysis.evaluation.summarizer import build_comparison_payload
from tests.evaluation_test_helpers import write_synthetic_evaluation_run


def test_summarizer_counts_decisions_parse_status_confidence_runtime_and_tokens(tmp_path):
  write_synthetic_evaluation_run(
    tmp_path,
    confirmation_run_id="run_a",
    shared_decision="violation",
    unique_suffix="a",
  )
  write_synthetic_evaluation_run(
    tmp_path,
    confirmation_run_id="run_b",
    context_mode="isolated_state",
    shared_decision="no_violation",
    unique_suffix="b",
  )
  loaded = load_confirmation_runs(tmp_path, ("run_a", "run_b"))

  comparison = build_comparison_payload(
    loaded,
    options=ConfirmationComparisonOptions(run_dir=tmp_path, confirmation_run_ids=("run_a", "run_b")),
    comparison_run_id="comparison_one",
    generated_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
  )

  assert comparison["summary"]["total_records"] == 6
  assert comparison["summary"]["by_decision"]["violation"] == 1
  assert comparison["summary"]["by_decision"]["no_violation"] == 1
  assert comparison["summary"]["by_decision"]["uncertain"] == 4
  assert comparison["parse_status_summary"]["id_mismatch"] == 2
  assert comparison["confidence_summary"]["count"] == 6
  assert comparison["runtime_summary"]["sum"] == 70
  assert comparison["token_summary"]["total_tokens_total"] == 550

  run_a = next(item for item in comparison["summary_by_run"] if item["confirmation_run_id"] == "run_a")
  run_b = next(item for item in comparison["summary_by_run"] if item["confirmation_run_id"] == "run_b")
  assert run_a["by_decision"]["violation"] == 1
  assert run_a["context_mode"] == "graph_context"
  assert run_b["context_mode"] == "isolated_state"
  assert run_a["parse_status_counts"]["id_mismatch"] == 1
  assert run_a["reason_present_count"] == 3
  assert run_a["supporting_evidence_count_summary"]["sum"] == 6

  image_summary = next(
    item for item in comparison["summary_by_candidate_type"] if item["candidate_type"] == "image-alt-not-descriptive"
  )
  assert image_summary["total_records"] == 2
  assert image_summary["by_decision"]["uncertain"] == 2


def test_summarizer_detects_candidate_level_disagreement_without_accuracy_metrics(tmp_path):
  write_synthetic_evaluation_run(
    tmp_path,
    confirmation_run_id="run_a",
    shared_decision="violation",
    unique_suffix="a",
  )
  write_synthetic_evaluation_run(
    tmp_path,
    confirmation_run_id="run_b",
    shared_decision="no_violation",
    unique_suffix="b",
  )
  loaded = load_confirmation_runs(tmp_path, ("run_a", "run_b"))

  comparison = build_comparison_payload(
    loaded,
    options=ConfirmationComparisonOptions(run_dir=tmp_path, confirmation_run_ids=("run_a", "run_b")),
    comparison_run_id="comparison_one",
  )

  assert comparison["summary"]["overlapping_candidate_count"] == 1
  assert comparison["summary"]["candidate_decision_disagreement_count"] == 1
  shared = comparison["candidate_comparisons"][0]
  assert shared["candidate_id"] == "cand_shared"
  assert shared["decision_agreement"] is False
  assert shared["decisions"] == ["no_violation", "violation"]
  assert {item["context_mode"] for item in shared["runs"]} == {"graph_context"}
  assert "accuracy" not in comparison


def test_summarizer_handles_no_overlap_case_clearly(tmp_path):
  write_synthetic_evaluation_run(
    tmp_path,
    confirmation_run_id="run_a",
    include_shared=False,
    unique_suffix="a",
  )
  write_synthetic_evaluation_run(
    tmp_path,
    confirmation_run_id="run_b",
    include_shared=False,
    unique_suffix="b",
  )
  loaded = load_confirmation_runs(tmp_path, ("run_a", "run_b"))

  comparison = build_comparison_payload(
    loaded,
    options=ConfirmationComparisonOptions(run_dir=tmp_path, confirmation_run_ids=("run_a", "run_b")),
    comparison_run_id="comparison_one",
  )

  assert comparison["summary"]["overlapping_candidate_count"] == 0
  assert comparison["candidate_comparisons"] == []
