from __future__ import annotations

import pytest

from src.analysis.evaluation.reader import load_confirmation_runs
from tests.evaluation_test_helpers import write_synthetic_evaluation_run


def test_reader_loads_multiple_confirmation_runs(tmp_path):
  write_synthetic_evaluation_run(tmp_path, confirmation_run_id="run_a", unique_suffix="a")
  write_synthetic_evaluation_run(tmp_path, confirmation_run_id="run_b", unique_suffix="b")

  loaded = load_confirmation_runs(tmp_path, ("run_a", "run_b"))

  assert [run.confirmation_run_id for run in loaded] == ["run_a", "run_b"]
  assert loaded[0].manifest["model"] == "qwen2.5:7b"
  assert len(loaded[0].records) == 3
  assert loaded[0].records[0]["candidate_id"] == "cand_shared"


def test_reader_requires_at_least_one_unique_run_id(tmp_path):
  with pytest.raises(ValueError, match="At least one"):
    load_confirmation_runs(tmp_path, ())

  write_synthetic_evaluation_run(tmp_path, confirmation_run_id="run_a", unique_suffix="a")
  with pytest.raises(ValueError, match="unique"):
    load_confirmation_runs(tmp_path, ("run_a", "run_a"))


def test_reader_fails_when_confirmation_artifacts_are_missing(tmp_path):
  with pytest.raises(FileNotFoundError, match="Confirmation run directory"):
    load_confirmation_runs(tmp_path, ("missing",))
