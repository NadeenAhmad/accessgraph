from __future__ import annotations

import pytest

from src.analysis.reporting.reader import load_confirmation_run
from tests.developer_report_test_helpers import write_synthetic_confirmation_run


def test_reader_loads_confirmation_manifest_and_jsonl(tmp_path):
  write_synthetic_confirmation_run(tmp_path)

  loaded = load_confirmation_run(tmp_path, "confirm_report_source")

  assert loaded.confirmation_run_id == "confirm_report_source"
  assert loaded.manifest["provider"] == "fake"
  assert len(loaded.records) == 4
  assert loaded.records[0]["candidate_id"] == "cand_violation"


def test_reader_requires_manifest_and_confirmations_jsonl(tmp_path):
  confirmation_dir = tmp_path / "confirmations" / "missing"
  confirmation_dir.mkdir(parents=True)

  with pytest.raises(FileNotFoundError, match="manifest"):
    load_confirmation_run(tmp_path, "missing")
