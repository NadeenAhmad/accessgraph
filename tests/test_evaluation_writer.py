from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.analysis.evaluation.models import ConfirmationComparisonOptions
from src.analysis.evaluation.runner import run_confirmation_comparison
from tests.evaluation_test_helpers import write_synthetic_evaluation_run


def test_writer_creates_markdown_json_and_manifest(tmp_path):
  write_synthetic_evaluation_run(tmp_path, confirmation_run_id="run_a", unique_suffix="a")
  write_synthetic_evaluation_run(tmp_path, confirmation_run_id="run_b", unique_suffix="b", shared_decision="no_violation")

  result = run_confirmation_comparison(
    options=ConfirmationComparisonOptions(
      run_dir=tmp_path,
      confirmation_run_ids=("run_a", "run_b"),
      comparison_run_id="comparison_one",
    ),
    generated_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
  )

  output_dir = result.output_dir
  markdown = (output_dir / "comparison.md").read_text(encoding="utf-8")
  comparison_json = json.loads((output_dir / "comparison.json").read_text(encoding="utf-8"))
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

  assert (output_dir / "comparison.md").exists()
  assert (output_dir / "comparison.json").exists()
  assert (output_dir / "manifest.json").exists()
  assert "AccessGraph Local Confirmation Comparison" in markdown
  assert "descriptive comparison" in markdown
  assert "accuracy" in markdown
  assert "cand_shared" in markdown
  assert comparison_json["summary"]["total_records"] == 6
  assert len(comparison_json["candidate_comparisons"]) == 1
  assert manifest["outputs"]["comparison_markdown"] == "comparison.md"
  assert manifest["counts"]["confirmation_run_count"] == 2
  assert manifest["warnings_count"] == 0
  assert "invocation" in manifest


def test_writer_markdown_states_when_no_candidate_overlap_exists(tmp_path):
  write_synthetic_evaluation_run(tmp_path, confirmation_run_id="run_a", include_shared=False, unique_suffix="a")
  write_synthetic_evaluation_run(tmp_path, confirmation_run_id="run_b", include_shared=False, unique_suffix="b")

  result = run_confirmation_comparison(
    options=ConfirmationComparisonOptions(
      run_dir=tmp_path,
      confirmation_run_ids=("run_a", "run_b"),
      comparison_run_id="comparison_one",
    )
  )

  markdown = (result.output_dir / "comparison.md").read_text(encoding="utf-8")

  assert "No overlapping `candidate_id` values were found" in markdown


def test_writer_prevents_overwrite_without_flag(tmp_path):
  write_synthetic_evaluation_run(tmp_path, confirmation_run_id="run_a", unique_suffix="a")
  run_confirmation_comparison(
    options=ConfirmationComparisonOptions(
      run_dir=tmp_path,
      confirmation_run_ids=("run_a",),
      comparison_run_id="comparison_one",
    )
  )

  with pytest.raises(FileExistsError, match="already exists"):
    run_confirmation_comparison(
      options=ConfirmationComparisonOptions(
        run_dir=tmp_path,
        confirmation_run_ids=("run_a",),
        comparison_run_id="comparison_one",
      )
    )


def test_writer_refuses_core_run_output_dir(tmp_path):
  write_synthetic_evaluation_run(tmp_path, confirmation_run_id="run_a", unique_suffix="a")

  with pytest.raises(ValueError, match="core run artifact"):
    run_confirmation_comparison(
      options=ConfirmationComparisonOptions(
        run_dir=tmp_path,
        confirmation_run_ids=("run_a",),
        output_dir=tmp_path,
        overwrite=True,
      )
    )
