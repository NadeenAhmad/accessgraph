from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analysis.confirmation.models import (
  CALIBRATED_TEXT_PROMPT_VERSION,
  GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  ReviewBundle,
)
from src.analysis.confirmation.parser import ConfirmationParseError, parse_confirmation_response


def _bundle() -> ReviewBundle:
  run_dir = Path("runs/example").resolve()
  return ReviewBundle(
    run_dir=run_dir,
    source_path=run_dir / "candidates" / "candidates.jsonl",
    source_line_number=1,
    record={},
    candidate_id="cand_parse",
    candidate_type="page-title-not-descriptive",
    state_id="state_0001",
    element_refs=(),
    primary_element_ref=None,
    selection_reason=("page_title_with_route_and_content_context",),
    required_context=("page title",),
    evidence={"page": {"title": "Home"}},
    state_context={"url": "https://example.com/"},
    graph_context={},
    artifact_refs={},
    generator={"name": "offline_semantic_candidate_builder", "version": "1"},
  )


def _payload(**overrides):
  payload = {
    "candidate_id": "cand_parse",
    "candidate_type": "page-title-not-descriptive",
    "state_id": "state_0001",
    "decision": "uncertain",
    "confidence": 0.5,
    "reason": "The fake response is intentionally uncertain.",
    "supporting_evidence": ["page.title=Home"],
  }
  payload.update(overrides)
  return payload


def test_parser_accepts_raw_json():
  parsed = parse_confirmation_response(json.dumps(_payload()), bundle=_bundle())

  assert parsed.parse_status == "parsed"
  assert parsed.decision == "uncertain"
  assert parsed.confidence == 0.5
  assert parsed.supporting_evidence == ("page.title=Home",)


def test_parser_accepts_fenced_json():
  content = "```json\n" + json.dumps(_payload(decision="no_violation", confidence=0.8)) + "\n```"

  parsed = parse_confirmation_response(content, bundle=_bundle())

  assert parsed.parse_status == "parsed"
  assert parsed.decision == "no_violation"
  assert parsed.confidence == 0.8


def test_parser_converts_malformed_output_to_uncertain_by_default():
  parsed = parse_confirmation_response("not json", bundle=_bundle())

  assert parsed.decision == "uncertain"
  assert parsed.confidence == 0.0
  assert parsed.parse_status == "malformed_json"
  assert parsed.error


def test_parser_raises_for_malformed_output_in_strict_mode():
  with pytest.raises(ConfirmationParseError, match="not valid JSON"):
    parse_confirmation_response("not json", bundle=_bundle(), strict=True)


def test_parser_converts_id_mismatch_to_uncertain_by_default():
  parsed = parse_confirmation_response(json.dumps(_payload(candidate_id="other")), bundle=_bundle())

  assert parsed.decision == "uncertain"
  assert parsed.parse_status == "id_mismatch"
  assert parsed.confidence == 0.0


def test_parser_guided_response_uses_bundle_metadata():
  content = json.dumps(
    {
      "decision": "violation",
      "confidence": 0.82,
      "reason": "The saved evidence directly supports the candidate concern.",
      "supporting_evidence": ["page.title", "state_context.url"],
    }
  )

  parsed = parse_confirmation_response(
    content,
    bundle=_bundle(),
    prompt_version=GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  )

  assert parsed.parse_status == "parsed"
  assert parsed.candidate_id == "cand_parse"
  assert parsed.candidate_type == "page-title-not-descriptive"
  assert parsed.state_id == "state_0001"
  assert parsed.decision == "violation"
  assert parsed.confidence == 0.82


def test_parser_guided_response_ignores_echoed_identifier_fields():
  content = json.dumps(
    {
      "candidate_id": "state_0001",
      "candidate_type": "semantic_candidate",
      "state_id": "other_state",
      "decision": "violation",
      "confidence": 0.7,
      "reason": "The decision fields are valid; identifiers are runner metadata in this prompt version.",
      "supporting_evidence": ["page.title"],
    }
  )

  parsed = parse_confirmation_response(
    content,
    bundle=_bundle(),
    prompt_version=GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  )

  assert parsed.parse_status == "parsed"
  assert parsed.candidate_id == "cand_parse"
  assert parsed.candidate_type == "page-title-not-descriptive"
  assert parsed.state_id == "state_0001"


def test_parser_calibrated_text_response_uses_bundle_metadata_for_identifiers():
  content = json.dumps(
    _payload(
      candidate_id="state_0001",
      candidate_type="semantic_candidate",
      state_id="other_state",
      decision="violation",
      confidence=0.7,
    )
  )

  parsed = parse_confirmation_response(content, bundle=_bundle(), prompt_version=CALIBRATED_TEXT_PROMPT_VERSION)

  assert parsed.parse_status == "parsed"
  assert parsed.candidate_id == "cand_parse"
  assert parsed.candidate_type == "page-title-not-descriptive"
  assert parsed.state_id == "state_0001"
  assert parsed.decision == "violation"


def test_parser_rejects_invalid_confidence():
  parsed = parse_confirmation_response(json.dumps(_payload(confidence=1.5)), bundle=_bundle())

  assert parsed.decision == "uncertain"
  assert parsed.parse_status == "schema_error"

  with pytest.raises(ConfirmationParseError, match="confidence"):
    parse_confirmation_response(json.dumps(_payload(confidence=-0.1)), bundle=_bundle(), strict=True)
