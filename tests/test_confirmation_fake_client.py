from __future__ import annotations

from pathlib import Path

from src.analysis.candidates.taxonomy import SUPPORTED_CANDIDATE_TYPES
from src.analysis.confirmation.providers.fake import DEFAULT_FAKE_MODEL, FakeConfirmationClient
from src.analysis.confirmation.models import ReviewBundle
from src.analysis.confirmation.parser import parse_confirmation_response
from src.analysis.confirmation.prompt_builder import build_confirmation_prompt


def _bundle(candidate_type: str = "image-alt-not-descriptive") -> ReviewBundle:
  run_dir = Path("runs/example").resolve()
  return ReviewBundle(
    run_dir=run_dir,
    source_path=run_dir / "candidates" / "candidates.jsonl",
    source_line_number=1,
    record={},
    candidate_id=f"cand_{candidate_type.replace('-', '_')}",
    candidate_type=candidate_type,
    state_id="state_0001",
    element_refs=({"bucket": "images", "element_id": "image-1", "selector": "img"},),
    primary_element_ref=None,
    selection_reason=("foundation_fake_test",),
    required_context=("candidate evidence",),
    evidence={"sample": {"text": candidate_type}},
    state_context={"url": "https://example.com/"},
    graph_context={},
    artifact_refs={"accessibility_context": "states/state_0001/accessibility_context.json"},
    generator={"name": "offline_semantic_candidate_builder", "version": "1"},
  )


def test_fake_client_returns_default_uncertain_confirmation():
  prompt = build_confirmation_prompt(_bundle())
  response = FakeConfirmationClient().confirm(prompt)
  parsed = parse_confirmation_response(response.raw_content, bundle=prompt.bundle)

  assert response.provider == "fake"
  assert response.model == DEFAULT_FAKE_MODEL
  assert parsed.parse_status == "parsed"
  assert parsed.decision == "uncertain"
  assert parsed.confidence == 0.5


def test_fake_client_is_deterministic():
  prompt = build_confirmation_prompt(_bundle("button-label-mismatch"))
  client = FakeConfirmationClient()

  first = client.confirm(prompt)
  second = client.confirm(prompt)

  assert first.raw_content == second.raw_content


def test_fake_client_structurally_supports_all_current_candidate_types():
  client = FakeConfirmationClient()

  for candidate_type in SUPPORTED_CANDIDATE_TYPES:
    prompt = build_confirmation_prompt(_bundle(candidate_type))
    response = client.confirm(prompt)
    parsed = parse_confirmation_response(response.raw_content, bundle=prompt.bundle)
    assert parsed.candidate_type == candidate_type
    assert parsed.decision == "uncertain"
    assert parsed.confidence == 0.5


def test_fake_client_can_simulate_malformed_response_for_tests():
  prompt = build_confirmation_prompt(_bundle("link-text-mismatch"))
  response = FakeConfirmationClient(malformed_response=True).confirm(prompt)
  parsed = parse_confirmation_response(response.raw_content, bundle=prompt.bundle)

  assert parsed.decision == "uncertain"
  assert parsed.confidence == 0.0
  assert parsed.parse_status == "malformed_json"
