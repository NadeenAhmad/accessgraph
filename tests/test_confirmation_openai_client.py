from __future__ import annotations

import io
import json
from pathlib import Path
from urllib import error

import pytest

from accessgraph import main as accessgraph_main
from src.analysis.confirmation.models import (
  CALIBRATED_TEXT_PROMPT_VERSION,
  CALIBRATED_VISION_PROMPT_VERSION,
  ConfirmationConfig,
  CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  ReviewBundle,
)
from src.analysis.confirmation.providers.openai import (
  DEFAULT_OPENAI_RESPONSES_URL,
  OPENAI_API_KEY_ENV,
  OpenAIConfirmationClient,
  build_openai_responses_payload,
)
from src.analysis.confirmation.providers.openai_vision import (
  OpenAIVisionConfirmationClient,
  build_openai_vision_responses_payload,
)
from src.analysis.confirmation.parser import parse_confirmation_response
from src.analysis.confirmation.prompt_builder import build_confirmation_prompt, load_prompt_templates
from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation


class _FakeResponse:
  def __init__(self, payload):
    self.payload = payload

  def read(self):
    return json.dumps(self.payload).encode("utf-8")

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc, tb):
    return False


def _bundle() -> ReviewBundle:
  record = _candidate_record()
  return ReviewBundle(
    run_dir=Path("runs/example"),
    source_path=Path("runs/example/candidates/candidates.jsonl"),
    source_line_number=1,
    record=record,
    candidate_id=record["candidate_id"],
    candidate_type=record["candidate_type"],
    state_id=record["state_id"],
    element_refs=tuple(record["element_refs"]),
    selection_reason=tuple(record["selection_reason"]),
    required_context=tuple(record["required_context"]),
    evidence=record["evidence"],
    state_context=record["state_context"],
    graph_context=record["graph_context"],
    artifact_refs=record["artifact_refs"],
    generator=record["generator"],
  )


def _candidate_record(
  *,
  candidate_id: str = "cand_title",
  candidate_type: str = "page-title-not-descriptive",
  state_id: str = "state_0001",
) -> dict[str, object]:
  return {
    "schema_version": "1",
    "candidate_id": candidate_id,
    "candidate_type": candidate_type,
    "state_id": state_id,
    "element_refs": [],
    "selection_reason": ["page title needs confirmation"],
    "required_context": ["page title", "route"],
    "evidence": {
      "page": {"title": "Products | Checkout Flow Benchmark"},
      "private_note": "co-sem-999-private-seed-marker",
      "supporting": {
        "dom_snippets": [
          {
            "element_id": "title-1",
            "selector": "title",
            "html": "<title>Products | Checkout Flow Benchmark</title>",
          }
        ]
      },
      "dom_snippets": [
        {
          "element_id": "title-1",
          "selector": "title",
          "html": "<title>Products | Checkout Flow Benchmark</title>",
        }
      ],
    },
    "state_context": {"url": "https://example.test/checkout/review", "title": "Products"},
    "graph_context": {"transition_path": []},
    "artifact_refs": {"accessibility_context": f"states/{state_id}/accessibility_context.json"},
    "generator": {"name": "offline_semantic_candidate_builder", "version": "1"},
  }


def _write_candidates(run_dir, records: list[dict[str, object]]) -> None:
  candidate_dir = run_dir / "candidates"
  candidate_dir.mkdir(parents=True)
  with (candidate_dir / "candidates.jsonl").open("w", encoding="utf-8") as handle:
    for record in records:
      handle.write(json.dumps(record) + "\n")


def _write_screenshot(run_dir: Path, *, state_id: str = "state_0001", data: bytes = b"fake-png") -> str:
  screenshot_path = run_dir / "states" / state_id / "screenshot.png"
  screenshot_path.parent.mkdir(parents=True)
  screenshot_path.write_bytes(data)
  return f"states/{state_id}/screenshot.png"


def _vision_bundle(run_dir: Path, *, screenshot_ref: str | None = None) -> ReviewBundle:
  record = _candidate_record()
  record["artifact_refs"] = {
    **record["artifact_refs"],
    "screenshot": screenshot_ref or _write_screenshot(run_dir),
  }
  return ReviewBundle(
    run_dir=run_dir,
    source_path=run_dir / "candidates" / "candidates.jsonl",
    source_line_number=1,
    record=record,
    candidate_id=record["candidate_id"],
    candidate_type=record["candidate_type"],
    state_id=record["state_id"],
    element_refs=tuple(record["element_refs"]),
    selection_reason=tuple(record["selection_reason"]),
    required_context=tuple(record["required_context"]),
    evidence=record["evidence"],
    state_context=record["state_context"],
    graph_context=record["graph_context"],
    artifact_refs=record["artifact_refs"],
    generator=record["generator"],
  )


def _valid_confirmation_payload(bundle: ReviewBundle) -> dict[str, object]:
  return {
    "candidate_id": bundle.candidate_id,
    "candidate_type": bundle.candidate_type,
    "state_id": bundle.state_id,
    "decision": "violation",
    "confidence": 0.82,
    "reason": "The saved route and title evidence describe different page purposes.",
    "supporting_evidence": ["title=Products", "route=/checkout/review"],
  }


def _openai_payload(content: str, *, input_tokens: int = 1234, output_tokens: int = 56) -> dict[str, object]:
  return {
    "id": "resp_test",
    "object": "response",
    "status": "completed",
    "model": "gpt-5.4-mini",
    "output_text": content,
    "usage": {
      "input_tokens": input_tokens,
      "output_tokens": output_tokens,
      "total_tokens": input_tokens + output_tokens,
      "input_tokens_details": {"cached_tokens": 0},
      "output_tokens_details": {"reasoning_tokens": 0},
    },
  }


def _valid_confirmation_content(bundle: ReviewBundle) -> str:
  return json.dumps(_valid_confirmation_payload(bundle), ensure_ascii=False)


def test_openai_client_request_body_and_success_response(monkeypatch):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-test")
  bundle = _bundle()
  prompt = build_confirmation_prompt(bundle)
  captured = {}

  def fake_urlopen(req, timeout):
    captured["url"] = req.full_url
    captured["timeout"] = timeout
    captured["headers"] = dict(req.header_items())
    captured["body"] = json.loads(req.data.decode("utf-8"))
    return _FakeResponse(_openai_payload(_valid_confirmation_content(bundle)))

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.openai.urllib_request.urlopen",
    fake_urlopen,
  )

  client = OpenAIConfirmationClient(
    ConfirmationConfig(
      provider="openai",
      model="gpt-5.4-mini",
      temperature=0.0,
      timeout_seconds=9.0,
    )
  )
  response = client.confirm(prompt)
  parsed = parse_confirmation_response(response.raw_content, bundle=bundle)

  assert captured["url"] == DEFAULT_OPENAI_RESPONSES_URL
  assert captured["timeout"] == 9.0
  assert captured["headers"]["Authorization"] == "Bearer sk-test"
  assert captured["body"]["model"] == "gpt-5.4-mini"
  assert captured["body"]["instructions"] == prompt.system_prompt
  assert captured["body"]["input"] == prompt.user_prompt
  assert captured["body"]["store"] is False
  assert captured["body"]["temperature"] == 0.0
  text_format = captured["body"]["text"]["format"]
  assert text_format["type"] == "json_schema"
  assert text_format["strict"] is True
  assert text_format["schema"]["additionalProperties"] is False
  assert "candidate_id" in text_format["schema"]["required"]
  assert response.provider == "openai"
  assert response.model == "gpt-5.4-mini"
  assert response.token_usage["input_tokens"] == 1234
  assert response.token_usage["output_tokens"] == 56
  assert response.token_usage["total_tokens"] == 1290
  assert response.estimated_cost_usd == pytest.approx(0.0011775)
  assert response.provider_metadata["request"]["store"] is False
  assert response.provider_metadata["request"]["response_format"] == "json_schema"
  assert "sk-test" not in json.dumps(response.provider_metadata)
  assert parsed.decision == "violation"
  assert parsed.confidence == 0.82


def test_openai_payload_accepts_gpt55_before_request():
  bundle = _bundle()
  prompt = build_confirmation_prompt(bundle)

  payload = build_openai_responses_payload(
    model="gpt-5.5",
    prompt=prompt,
    temperature=0.0,
  )

  assert payload["model"] == "gpt-5.5"
  assert "temperature" not in payload


def test_openai_vision_payload_accepts_gpt55_before_request(tmp_path):
  bundle = _vision_bundle(tmp_path)
  templates = load_prompt_templates(CALIBRATED_VISION_PROMPT_VERSION)
  prompt = build_confirmation_prompt(bundle, templates=templates)

  payload = build_openai_vision_responses_payload(
    model="gpt-5.5",
    prompt=prompt,
    screenshot_data_url="data:image/png;base64,abc",
    temperature=0.0,
  )

  assert payload["model"] == "gpt-5.5"
  assert "temperature" not in payload


def test_openai_vision_payload_uses_minimal_schema_for_guided_html_screenshot_prompt(tmp_path):
  bundle = _vision_bundle(tmp_path)
  templates = load_prompt_templates(GUIDED_HTML_SCREENSHOT_PROMPT_VERSION)
  prompt = build_confirmation_prompt(
    bundle,
    templates=templates,
    context_mode=CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  )

  payload = build_openai_vision_responses_payload(
    model="gpt-5.4-mini",
    prompt=prompt,
    screenshot_data_url="data:image/png;base64,abc",
    temperature=0.0,
  )

  schema = payload["text"]["format"]["schema"]
  assert schema["required"] == ["decision", "confidence", "reason", "supporting_evidence"]
  assert "candidate_id" not in schema["properties"]
  assert "candidate_type" not in schema["properties"]
  assert "state_id" not in schema["properties"]


def test_openai_payload_keeps_full_schema_for_calibrated_prompt():
  bundle = _bundle()
  templates = load_prompt_templates(CALIBRATED_TEXT_PROMPT_VERSION)
  prompt = build_confirmation_prompt(bundle, templates=templates)

  payload = build_openai_responses_payload(
    model="gpt-5.4-mini",
    prompt=prompt,
    temperature=0.0,
  )

  schema = payload["text"]["format"]["schema"]
  assert "candidate_id" in schema["required"]
  assert "candidate_type" in schema["required"]
  assert "state_id" in schema["required"]
  assert "candidate_id" in schema["properties"]


def test_openai_client_missing_api_key_fails_clearly(monkeypatch):
  monkeypatch.delenv(OPENAI_API_KEY_ENV, raising=False)

  with pytest.raises(ValueError, match="OPENAI_API_KEY"):
    OpenAIConfirmationClient(
      ConfirmationConfig(
        provider="openai",
        model="gpt-5.4-mini",
      )
    )


def test_openai_vision_client_request_body_includes_image_without_logging_it(monkeypatch, tmp_path):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-test")
  screenshot_bytes = b"\x89PNG\r\nopenai-vision-test"
  screenshot_ref = _write_screenshot(tmp_path, data=screenshot_bytes)
  expected_data_url = "data:image/png;base64,iVBORw0Kb3BlbmFpLXZpc2lvbi10ZXN0"
  bundle = _vision_bundle(tmp_path, screenshot_ref=screenshot_ref)
  templates = load_prompt_templates(CALIBRATED_VISION_PROMPT_VERSION)
  prompt = build_confirmation_prompt(bundle, templates=templates)
  captured = {}

  def fake_post_openai_json(*, url, payload, api_key, timeout_seconds):
    captured["url"] = url
    captured["payload"] = payload
    captured["api_key"] = api_key
    captured["timeout_seconds"] = timeout_seconds
    return _openai_payload(_valid_confirmation_content(bundle), input_tokens=3000, output_tokens=120)

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.openai_vision.post_openai_json",
    fake_post_openai_json,
  )

  client = OpenAIVisionConfirmationClient(
    ConfirmationConfig(
      provider="openai-vision",
      model="gpt-5.4-mini",
      prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
      timeout_seconds=11.0,
    )
  )
  response = client.confirm(prompt)
  parsed = parse_confirmation_response(response.raw_content, bundle=bundle)

  assert captured["url"] == DEFAULT_OPENAI_RESPONSES_URL
  assert captured["api_key"] == "sk-test"
  assert captured["timeout_seconds"] == 11.0
  assert captured["payload"]["model"] == "gpt-5.4-mini"
  assert captured["payload"]["instructions"] == prompt.system_prompt
  message = captured["payload"]["input"][0]
  assert message["role"] == "user"
  assert message["content"][0] == {"type": "input_text", "text": prompt.user_prompt}
  assert message["content"][1] == {
    "type": "input_image",
    "image_url": expected_data_url,
  }
  assert captured["payload"]["text"]["format"]["schema"]["additionalProperties"] is False
  assert response.provider == "openai-vision"
  assert response.model == "gpt-5.4-mini"
  assert response.provider_metadata["input_modalities"] == ["text", "image"]
  assert response.provider_metadata["image_source"] == "state_screenshot"
  assert response.provider_metadata["image_input"]["screenshot"] == screenshot_ref
  assert response.provider_metadata["image_input"]["byte_length"] == len(screenshot_bytes)
  assert response.provider_metadata["request"]["image_count"] == 1
  assert expected_data_url not in json.dumps(response.provider_metadata)
  assert "sk-test" not in json.dumps(response.provider_metadata)
  assert parsed.decision == "violation"


def test_openai_vision_guided_html_screenshot_uses_state_screenshot(monkeypatch, tmp_path):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-test")
  screenshot_bytes = b"\x89PNG\r\nminimal-state"
  screenshot_ref = _write_screenshot(tmp_path, data=screenshot_bytes)
  crop_path = tmp_path / "confirmations" / "old-run" / "visual_context" / "cand_title" / "target_crop.png"
  crop_path.parent.mkdir(parents=True)
  crop_path.write_bytes(b"\x89PNG\r\nnot-the-state-screenshot")
  bundle = _vision_bundle(tmp_path, screenshot_ref=screenshot_ref)
  bundle = ReviewBundle(
    run_dir=bundle.run_dir,
    source_path=bundle.source_path,
    source_line_number=bundle.source_line_number,
    record=bundle.record,
    candidate_id=bundle.candidate_id,
    candidate_type=bundle.candidate_type,
    state_id=bundle.state_id,
    element_refs=bundle.element_refs,
    selection_reason=bundle.selection_reason,
    required_context=bundle.required_context,
    evidence=bundle.evidence,
    state_context=bundle.state_context,
    graph_context=bundle.graph_context,
    artifact_refs={
      **bundle.artifact_refs,
      "visual_context": {
        "target_crop": "confirmations/old-run/visual_context/cand_title/target_crop.png",
      },
    },
    generator=bundle.generator,
  )
  templates = load_prompt_templates(GUIDED_HTML_SCREENSHOT_PROMPT_VERSION)
  prompt = build_confirmation_prompt(
    bundle,
    templates=templates,
    context_mode=CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  )
  expected_data_url = "data:image/png;base64,iVBORw0KbWluaW1hbC1zdGF0ZQ=="
  captured = {}

  def fake_post_openai_json(*, url, payload, api_key, timeout_seconds):
    captured["payload"] = payload
    return _openai_payload(
      json.dumps(
        {
          "decision": "uncertain",
          "confidence": 0.45,
          "reason": "The supplied HTML and screenshot do not provide enough information.",
          "supporting_evidence": ["candidate HTML", "attached screenshot"],
        }
      )
    )

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.openai_vision.post_openai_json",
    fake_post_openai_json,
  )

  client = OpenAIVisionConfirmationClient(
    ConfirmationConfig(
      provider="openai-vision",
      model="gpt-5.4-mini",
      prompt_version=GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
    )
  )
  response = client.confirm(prompt)
  parsed = parse_confirmation_response(
    response.raw_content,
    bundle=bundle,
    prompt_version=GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  )

  assert captured["payload"]["input"][0]["content"][1] == {
    "type": "input_image",
    "image_url": expected_data_url,
  }
  assert response.provider_metadata["image_source"] == "state_screenshot"
  assert response.provider_metadata["image_input"]["screenshot"] == screenshot_ref
  assert response.provider_metadata["request"]["image_count"] == 1
  assert parsed.parse_status == "parsed"
  assert parsed.candidate_id == bundle.candidate_id
  assert parsed.decision == "uncertain"


def test_openai_runner_writes_confirmation_record_with_usage_and_cost(monkeypatch, tmp_path):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-test")
  _write_candidates(tmp_path, [_candidate_record()])

  def fake_urlopen(req, timeout):
    bundle = _bundle()
    return _FakeResponse(_openai_payload(_valid_confirmation_content(bundle), input_tokens=2000, output_tokens=100))

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.openai.urllib_request.urlopen",
    fake_urlopen,
  )

  run_confirmation(
    config=ConfirmationConfig(
      provider="openai",
      model="gpt-5.4",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="openai-success",
      candidate_ids=("cand_title",),
      save_prompts=True,
      save_raw_responses=True,
    ),
  )

  output_dir = tmp_path / "confirmations" / "openai-success"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  record = json.loads((output_dir / "confirmations.jsonl").read_text(encoding="utf-8"))
  raw_response = json.loads(next((output_dir / "raw_responses").glob("*.json")).read_text(encoding="utf-8"))
  serialized_outputs = json.dumps(manifest, sort_keys=True) + json.dumps(record, sort_keys=True)

  assert manifest["provider"] == "openai"
  assert manifest["model"] == "gpt-5.4"
  assert manifest["input_mode"] == "text"
  assert manifest["input_modalities"] == ["text"]
  assert manifest["inputs"]["selected_candidate_ids"] == ["cand_title"]
  assert record["decision"] == "violation"
  assert record["parse_status"] == "parsed"
  assert record["token_usage"]["input_tokens"] == 2000
  assert record["token_usage"]["output_tokens"] == 100
  assert record["estimated_cost_usd"] == pytest.approx(0.0065)
  assert "sk-test" not in json.dumps(raw_response)
  assert "co-sem-999-private-seed-marker" not in serialized_outputs
  assert "bs-sem-" not in serialized_outputs
  assert "tm-sem-" not in serialized_outputs


def test_openai_vision_runner_writes_image_metadata_without_raw_image(monkeypatch, tmp_path):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-test")
  screenshot_bytes = b"\x89PNG\r\nrunner-openai-vision"
  screenshot_ref = _write_screenshot(tmp_path, data=screenshot_bytes)
  record = _candidate_record()
  record["artifact_refs"] = {
    **record["artifact_refs"],
    "screenshot": screenshot_ref,
  }
  _write_candidates(tmp_path, [record])
  bundle = _vision_bundle(tmp_path, screenshot_ref=screenshot_ref)
  expected_data_url = "data:image/png;base64,iVBORw0KcnVubmVyLW9wZW5haS12aXNpb24="
  captured = {}

  def fake_post_openai_json(*, url, payload, api_key, timeout_seconds):
    captured["payload"] = payload
    return _openai_payload(_valid_confirmation_content(bundle), input_tokens=5000, output_tokens=200)

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.openai_vision.post_openai_json",
    fake_post_openai_json,
  )

  run_confirmation(
    config=ConfirmationConfig(
      provider="openai-vision",
      model="gpt-5.4-mini",
      prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="openai-vision-success",
      candidate_ids=("cand_title",),
      save_prompts=True,
      save_raw_responses=True,
    ),
  )

  output_dir = tmp_path / "confirmations" / "openai-vision-success"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  confirmation_record = json.loads((output_dir / "confirmations.jsonl").read_text(encoding="utf-8"))
  attempt_record = json.loads((output_dir / "confirmation_attempts.jsonl").read_text(encoding="utf-8"))
  raw_response = json.loads(next((output_dir / "raw_responses").glob("*.json")).read_text(encoding="utf-8"))
  serialized_outputs = (
    json.dumps(manifest, sort_keys=True)
    + json.dumps(confirmation_record, sort_keys=True)
    + json.dumps(attempt_record, sort_keys=True)
    + json.dumps(raw_response, sort_keys=True)
  )

  assert manifest["provider"] == "openai-vision"
  assert manifest["input_mode"] == "vision"
  assert manifest["input_modalities"] == ["text", "image"]
  assert manifest["image_source"] == "state_screenshot"
  assert manifest["raw_logging"]["save_raw_images"] is False
  assert confirmation_record["input_modalities"] == ["text", "image"]
  assert confirmation_record["image_source"] == "state_screenshot"
  assert confirmation_record["image_input"]["screenshot"] == screenshot_ref
  assert confirmation_record["image_inputs"] == [confirmation_record["image_input"]]
  assert "sha256" in confirmation_record["image_input"]
  assert confirmation_record["token_usage"]["input_tokens"] == 5000
  assert confirmation_record["estimated_cost_usd"] == pytest.approx(0.00465)
  assert attempt_record["provider"] == "openai-vision"
  assert expected_data_url == captured["payload"]["input"][0]["content"][1]["image_url"]
  assert expected_data_url not in serialized_outputs
  assert "sk-test" not in serialized_outputs


def test_openai_vision_missing_screenshot_becomes_client_error_in_runner(monkeypatch, tmp_path):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-test")
  _write_candidates(tmp_path, [_candidate_record()])

  run_confirmation(
    config=ConfirmationConfig(
      provider="openai-vision",
      model="gpt-5.4-mini",
      prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="openai-vision-missing-screenshot",
      candidate_ids=("cand_title",),
    ),
  )

  record = json.loads(
    (
      tmp_path
      / "confirmations"
      / "openai-vision-missing-screenshot"
      / "confirmations.jsonl"
    ).read_text(encoding="utf-8")
  )
  assert record["decision"] == "uncertain"
  assert record["parse_status"] == "client_error"
  assert "artifact_refs.screenshot is missing" in record["error"]
  assert record["input_modalities"] == ["text", "image"]
  assert record["image_source"] == "state_screenshot"
  assert "image_input" not in record


def test_openai_vision_guided_html_screenshot_missing_screenshot_is_client_error(monkeypatch, tmp_path):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-test")
  _write_candidates(tmp_path, [_candidate_record()])

  run_confirmation(
    config=ConfirmationConfig(
      provider="openai-vision",
      model="gpt-5.4-mini",
      prompt_version=GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
      context_mode=CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="openai-vision-minimal-missing-screenshot",
      candidate_ids=("cand_title",),
    ),
  )

  record = json.loads(
    (
      tmp_path
      / "confirmations"
      / "openai-vision-minimal-missing-screenshot"
      / "confirmations.jsonl"
    ).read_text(encoding="utf-8")
  )
  assert record["decision"] == "uncertain"
  assert record["parse_status"] == "client_error"
  assert "artifact_refs.screenshot is missing" in record["error"]
  assert record["input_modalities"] == ["text", "image"]
  assert record["image_source"] == "state_screenshot"
  assert "image_input" not in record


def test_openai_http_error_becomes_client_error_in_runner(monkeypatch, tmp_path):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-test")
  _write_candidates(tmp_path, [_candidate_record()])

  def fake_urlopen(req, timeout):
    raise error.HTTPError(
      req.full_url,
      429,
      "Too Many Requests",
      hdrs=None,
      fp=io.BytesIO(b'{"error":{"message":"rate limited"}}'),
    )

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.openai.urllib_request.urlopen",
    fake_urlopen,
  )

  run_confirmation(
    config=ConfirmationConfig(
      provider="openai",
      model="gpt-5.4-mini",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="openai-http-error",
      candidate_ids=("cand_title",),
    ),
  )

  record = json.loads(
    (tmp_path / "confirmations" / "openai-http-error" / "confirmations.jsonl").read_text(
      encoding="utf-8"
    )
  )
  assert record["decision"] == "uncertain"
  assert record["parse_status"] == "client_error"
  assert "OpenAI HTTP error 429" in record["error"]


def test_openai_malformed_json_becomes_uncertain_in_runner(monkeypatch, tmp_path):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "sk-test")
  _write_candidates(tmp_path, [_candidate_record()])

  def fake_urlopen(req, timeout):
    return _FakeResponse(_openai_payload("{not valid json"))

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.openai.urllib_request.urlopen",
    fake_urlopen,
  )

  run_confirmation(
    config=ConfirmationConfig(
      provider="openai",
      model="gpt-5.4-mini",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="openai-malformed",
      candidate_ids=("cand_title",),
    ),
  )

  record = json.loads(
    (tmp_path / "confirmations" / "openai-malformed" / "confirmations.jsonl").read_text(encoding="utf-8")
  )
  assert record["decision"] == "uncertain"
  assert record["parse_status"] == "malformed_json"


def test_openai_provider_requires_explicit_candidate_selection(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(ValueError, match="requires --candidate-type, --candidate-id, --candidate-id-file, or --limit"):
    run_confirmation(
      config=ConfirmationConfig(
        provider="openai",
        model="gpt-5.4-mini",
      ),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="openai-unsafe",
        dry_run=True,
      ),
    )


def test_openai_unsupported_model_fails_before_api_key_or_request(monkeypatch, tmp_path):
  monkeypatch.delenv(OPENAI_API_KEY_ENV, raising=False)
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(ValueError, match="not-a-model"):
    run_confirmation(
      config=ConfirmationConfig(
        provider="openai",
        model="not-a-model",
      ),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="openai-unsupported",
        candidate_ids=("cand_title",),
        dry_run=True,
      ),
    )


def test_accessgraph_judge_accepts_openai_models_in_dry_run(tmp_path, capsys):
  _write_candidates(tmp_path, [_candidate_record()])

  for model in ("gpt-5.4-mini", "gpt-5.4", "gpt-5.5"):
    exit_code = accessgraph_main(
      [
        "judge",
        "--run",
        str(tmp_path),
        "--provider",
        "openai",
        "--model",
        model,
        "--candidate-id",
        "cand_title",
        "--judgment-run-id",
        f"dry-{model}",
        "--dry-run",
      ]
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "Dry run" in out
    assert not (tmp_path / "confirmations" / f"dry-{model}").exists()


def test_accessgraph_judge_rejects_unknown_openai_model(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(SystemExit):
    accessgraph_main(
      [
        "judge",
        "--run",
        str(tmp_path),
        "--provider",
        "openai",
        "--model",
        "not-a-model",
        "--candidate-id",
        "cand_title",
        "--dry-run",
      ]
    )


def test_accessgraph_judge_enforces_openai_safety_rule(tmp_path, capsys):
  _write_candidates(tmp_path, [_candidate_record()])

  exit_code = accessgraph_main(
    [
      "judge",
      "--run",
      str(tmp_path),
      "--provider",
      "openai",
      "--model",
      "gpt-5.4-mini",
      "--dry-run",
    ]
  )
  err = capsys.readouterr().err

  assert exit_code == 1
  assert "requires --candidate-type, --candidate-id, --candidate-id-file, or --limit" in err
