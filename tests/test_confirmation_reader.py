from __future__ import annotations

import json

import pytest

from src.analysis.confirmation.reader import iter_review_bundles, load_review_bundles


def _candidate_record(
  *,
  candidate_type: str = "button-label-mismatch",
  candidate_id: str = "cand_button",
  state_id: str = "state_0001",
) -> dict[str, object]:
  return {
    "schema_version": "1",
    "candidate_id": candidate_id,
    "candidate_type": candidate_type,
    "state_id": state_id,
    "element_refs": [
      {
        "bucket": "buttons",
        "element_id": "button-1",
        "selector": "#save",
        "xpath": "",
      }
    ],
    "primary_element_ref": {
      "bucket": "buttons",
      "element_id": "button-1",
      "selector": "#save",
      "xpath": "",
    },
    "selection_reason": ["visible_button_with_label_and_context_evidence"],
    "required_context": ["button label", "nearby text"],
    "evidence": {
      "button": {
        "label": "Save",
        "raw_html": "<button id=\"save\">Save</button>",
      }
    },
    "state_context": {
      "url": "https://example.com/settings",
      "title": "Settings",
      "depth": 1,
    },
    "graph_context": {
      "transition_path": [{"from": "state_0000", "to": state_id}],
    },
    "artifact_refs": {
      "screenshot": "states/state_0001/screenshot.png",
      "accessibility_context": "states/state_0001/accessibility_context.json",
    },
    "generator": {
      "name": "offline_semantic_candidate_builder",
      "version": "1",
    },
  }


def _write_candidates(run_dir, records: list[dict[str, object]]) -> None:
  candidate_dir = run_dir / "candidates"
  candidate_dir.mkdir(parents=True)
  with (candidate_dir / "candidates.jsonl").open("w", encoding="utf-8") as handle:
    for record in records:
      handle.write(json.dumps(record) + "\n")


def test_reader_reads_new_candidates_jsonl_and_tracks_line_numbers(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(candidate_id="cand_1", state_id="state_0001"),
      _candidate_record(candidate_id="cand_2", state_id="state_0002"),
    ],
  )

  bundles = load_review_bundles(tmp_path)

  assert [bundle.candidate_id for bundle in bundles] == ["cand_1", "cand_2"]
  assert [bundle.source_candidate_ref["line_number"] for bundle in bundles] == [1, 2]
  assert bundles[0].source_candidate_ref["path"] == "candidates/candidates.jsonl"
  assert bundles[0].candidate_type == "button-label-mismatch"
  assert bundles[0].primary_element_ref["bucket"] == "buttons"


def test_reader_filters_by_candidate_type(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(candidate_type="button-label-mismatch", candidate_id="cand_button"),
      _candidate_record(candidate_type="page-title-not-descriptive", candidate_id="cand_title"),
    ],
  )

  bundles = load_review_bundles(tmp_path, candidate_types=["page-title-not-descriptive"])

  assert [bundle.candidate_id for bundle in bundles] == ["cand_title"]


def test_reader_filters_by_candidate_id(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(candidate_id="cand_button_1"),
      _candidate_record(candidate_id="cand_button_2"),
      _candidate_record(candidate_id="cand_title", candidate_type="page-title-not-descriptive"),
    ],
  )

  bundles = load_review_bundles(tmp_path, candidate_ids=["cand_button_2", "cand_title"])

  assert [bundle.candidate_id for bundle in bundles] == ["cand_button_2", "cand_title"]


def test_reader_rejects_missing_requested_candidate_id(tmp_path):
  _write_candidates(tmp_path, [_candidate_record(candidate_id="cand_button")])

  with pytest.raises(ValueError, match="Requested candidate ids were not found.*cand_missing"):
    load_review_bundles(tmp_path, candidate_ids=["cand_button", "cand_missing"])


def test_reader_rejects_unsupported_filter_candidate_type(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(ValueError, match="Unsupported semantic candidate type"):
    list(iter_review_bundles(tmp_path, candidate_types=["unsupported-semantic-type"]))


def test_reader_rejects_unsupported_record_candidate_type(tmp_path):
  _write_candidates(
    tmp_path,
    [_candidate_record(candidate_type="unsupported-semantic-type")],
  )

  with pytest.raises(ValueError, match="Unsupported semantic candidate type"):
    load_review_bundles(tmp_path)


def test_reader_rejects_missing_required_field(tmp_path):
  record = _candidate_record()
  record.pop("evidence")
  _write_candidates(tmp_path, [record])

  with pytest.raises(ValueError, match="missing required field `evidence`"):
    load_review_bundles(tmp_path)


def test_reader_does_not_use_legacy_root_level_candidate_files(tmp_path):
  (tmp_path / "image_alt_candidates.jsonl").write_text(
    json.dumps(
      {
        "candidate_id": "legacy",
        "violation_target": "image-alt-not-descriptive",
        "state": {"state_id": "state_0001"},
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(FileNotFoundError, match="candidates.jsonl"):
    load_review_bundles(tmp_path)
