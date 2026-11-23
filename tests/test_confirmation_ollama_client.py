from __future__ import annotations

import json
import base64
from pathlib import Path
from urllib import error

import pytest

from src.analysis.confirmation.models import (
  CALIBRATED_TEXT_PROMPT_VERSION,
  CALIBRATED_VISION_PROMPT_VERSION,
  ConfirmationConfig,
  ReviewBundle,
)
from src.analysis.confirmation.providers.ollama import (
  ACCESSGRAPH_OLLAMA_BASE_URL_ENV,
  OLLAMA_BASE_URL_ENV,
  OllamaConfirmationClient,
  build_ollama_chat_payload,
  normalize_ollama_api_base_url,
  resolve_ollama_base_url,
)
from src.analysis.confirmation.providers.ollama_vision import OllamaVisionConfirmationClient
from src.analysis.confirmation.parser import ConfirmationParseError, parse_confirmation_response
from src.analysis.confirmation.prompt_builder import build_confirmation_prompt, load_prompt_templates
from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation


GEMMA_TEXT_MODEL = "gemma3n:e2b"
GEMMA_VISION_MODEL = "gemma3:4b"


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


def _candidate_record() -> dict[str, object]:
  return {
    "schema_version": "1",
    "candidate_id": "cand_title",
    "candidate_type": "page-title-not-descriptive",
    "state_id": "state_0001",
    "element_refs": [],
    "selection_reason": ["page title needs confirmation"],
    "required_context": ["page title", "route"],
    "evidence": {"page": {"title": "App"}},
    "state_context": {"url": "https://example.com", "title": "App"},
    "graph_context": {"transition_path": []},
    "artifact_refs": {"accessibility_context": "states/state_0001/accessibility_context.json"},
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


def _ollama_payload(content: str) -> dict[str, object]:
  return {
    "model": "qwen2.5:7b",
    "created_at": "2026-05-02T00:00:00Z",
    "message": {
      "role": "assistant",
      "content": content,
    },
    "done": True,
    "total_duration": 2_500_000_000,
    "load_duration": 100_000,
    "prompt_eval_count": 123,
    "prompt_eval_duration": 400_000_000,
    "eval_count": 45,
    "eval_duration": 1_900_000_000,
  }


def _valid_confirmation_content(bundle: ReviewBundle) -> str:
  return json.dumps(
    {
      "candidate_id": bundle.candidate_id,
      "candidate_type": bundle.candidate_type,
      "state_id": bundle.state_id,
      "decision": "uncertain",
      "confidence": 0.71,
      "reason": "Saved evidence is not enough to decide.",
      "supporting_evidence": ["page title is generic"],
    }
  )


def test_resolve_ollama_base_url_precedence(monkeypatch):
  monkeypatch.setenv(OLLAMA_BASE_URL_ENV, "http://fallback:11434")
  monkeypatch.setenv(ACCESSGRAPH_OLLAMA_BASE_URL_ENV, "http://project:11434/api")

  assert resolve_ollama_base_url("http://cli:11434") == "http://cli:11434/api"
  assert resolve_ollama_base_url(None) == "http://project:11434/api"

  monkeypatch.delenv(ACCESSGRAPH_OLLAMA_BASE_URL_ENV)
  assert resolve_ollama_base_url(None) == "http://fallback:11434/api"
  assert normalize_ollama_api_base_url("http://localhost:11434/api/") == "http://localhost:11434/api"


def test_ollama_client_request_body_and_success_response(monkeypatch):
  bundle = _bundle()
  prompt = build_confirmation_prompt(bundle)
  captured = {}

  def fake_urlopen(req, timeout):
    captured["url"] = req.full_url
    captured["timeout"] = timeout
    captured["body"] = json.loads(req.data.decode("utf-8"))
    return _FakeResponse(_ollama_payload(_valid_confirmation_content(bundle)))

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.ollama.urllib_request.urlopen",
    fake_urlopen,
  )

  client = OllamaConfirmationClient(
    ConfirmationConfig(
      provider="ollama",
      model=GEMMA_TEXT_MODEL,
      base_url="http://localhost:11434/api",
      temperature=0.2,
      timeout_seconds=7.0,
    )
  )
  response = client.confirm(prompt)
  parsed = parse_confirmation_response(response.raw_content, bundle=bundle)

  assert captured["url"] == "http://localhost:11434/api/chat"
  assert captured["timeout"] == 7.0
  assert captured["body"]["model"] == GEMMA_TEXT_MODEL
  assert captured["body"]["stream"] is False
  assert captured["body"]["format"]["type"] == "object"
  assert captured["body"]["format"]["additionalProperties"] is False
  assert captured["body"]["options"]["temperature"] == 0.2
  assert [message["role"] for message in captured["body"]["messages"]] == ["system", "user"]
  assert "images" not in captured["body"]["messages"][1]
  assert response.provider == "ollama"
  assert response.model == GEMMA_TEXT_MODEL
  assert response.runtime_ms == 2500
  assert response.estimated_cost_usd == 0.0
  assert response.token_usage["prompt_tokens"] == 123
  assert response.token_usage["completion_tokens"] == 45
  assert response.token_usage["total_tokens"] == 168
  assert response.provider_metadata["ollama_response"]["done"] is True
  assert parsed.decision == "uncertain"
  assert parsed.confidence == 0.71


def test_ollama_payload_keeps_full_schema_for_calibrated_prompt():
  bundle = _bundle()
  templates = load_prompt_templates(CALIBRATED_TEXT_PROMPT_VERSION)
  prompt = build_confirmation_prompt(bundle, templates=templates)

  payload = build_ollama_chat_payload(
    model=GEMMA_TEXT_MODEL,
    prompt=prompt,
    temperature=0.0,
  )

  schema = payload["format"]
  assert "candidate_id" in schema["required"]
  assert "candidate_type" in schema["required"]
  assert "state_id" in schema["required"]
  assert "candidate_id" in schema["properties"]


def test_ollama_vision_request_body_includes_base64_image_without_logging_it(monkeypatch, tmp_path):
  screenshot_bytes = b"\x89PNG\r\nvision-test"
  screenshot_ref = _write_screenshot(tmp_path, data=screenshot_bytes)
  bundle = _vision_bundle(tmp_path, screenshot_ref=screenshot_ref)
  templates = load_prompt_templates(CALIBRATED_VISION_PROMPT_VERSION)
  prompt = build_confirmation_prompt(bundle, templates=templates)
  expected_image = base64.b64encode(screenshot_bytes).decode("ascii")
  captured = {}

  def fake_urlopen(req, timeout):
    captured["body"] = json.loads(req.data.decode("utf-8"))
    captured["timeout"] = timeout
    return _FakeResponse(_ollama_payload(_valid_confirmation_content(bundle)))

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.ollama.urllib_request.urlopen",
    fake_urlopen,
  )

  client = OllamaVisionConfirmationClient(
    ConfirmationConfig(
      provider="ollama-vision",
      model=GEMMA_VISION_MODEL,
      base_url="http://localhost:11434/api",
      temperature=0.0,
      timeout_seconds=11.0,
    )
  )
  response = client.confirm(prompt)
  parsed = parse_confirmation_response(response.raw_content, bundle=bundle)

  user_message = captured["body"]["messages"][1]
  assert captured["body"]["model"] == GEMMA_VISION_MODEL
  assert captured["body"]["stream"] is False
  assert captured["body"]["format"]["type"] == "object"
  assert captured["timeout"] == 11.0
  assert user_message["content"] == prompt.user_prompt
  assert user_message["images"] == [expected_image]
  assert response.provider == "ollama-vision"
  assert response.provider_metadata["input_modalities"] == ["text", "image"]
  assert response.provider_metadata["image_source"] == "state_screenshot"
  assert response.provider_metadata["image_input"]["screenshot"] == screenshot_ref
  assert response.provider_metadata["image_input"]["byte_length"] == len(screenshot_bytes)
  assert "image_count" in response.provider_metadata["request"]
  assert expected_image not in json.dumps(response.provider_metadata)
  assert parsed.parse_status == "parsed"


def test_ollama_vision_missing_screenshot_becomes_client_error_in_runner(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  run_confirmation(
    config=ConfirmationConfig(
      provider="ollama-vision",
      model=GEMMA_VISION_MODEL,
      base_url="http://localhost:11434/api",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="vision-missing-screenshot",
      limit=1,
    ),
  )

  record = json.loads(
    (tmp_path / "confirmations" / "vision-missing-screenshot" / "confirmations.jsonl").read_text(
      encoding="utf-8"
    )
  )
  assert record["decision"] == "uncertain"
  assert record["parse_status"] == "client_error"
  assert "artifact_refs.screenshot" in record["error"]
  assert record["input_modalities"] == ["text", "image"]
  assert record["image_source"] == "state_screenshot"


def test_ollama_vision_path_traversal_screenshot_ref_is_rejected(tmp_path):
  record = _candidate_record()
  record["artifact_refs"] = {**record["artifact_refs"], "screenshot": "../outside.png"}
  _write_candidates(tmp_path, [record])

  run_confirmation(
    config=ConfirmationConfig(
      provider="ollama-vision",
      model=GEMMA_VISION_MODEL,
      base_url="http://localhost:11434/api",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="vision-traversal",
      limit=1,
    ),
  )

  record = json.loads(
    (tmp_path / "confirmations" / "vision-traversal" / "confirmations.jsonl").read_text(encoding="utf-8")
  )
  assert record["decision"] == "uncertain"
  assert record["parse_status"] == "client_error"
  assert "outside run_dir" in record["error"]


def test_ollama_vision_fail_fast_raises_on_missing_screenshot(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(ValueError, match="artifact_refs.screenshot"):
    run_confirmation(
      config=ConfirmationConfig(
        provider="ollama-vision",
        model="qwen2.5vl:7b",
        base_url="http://localhost:11434/api",
      ),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="vision-missing-screenshot-fast",
        limit=1,
        fail_fast=True,
      ),
    )


def test_ollama_vision_runner_writes_vision_metadata_without_raw_image(monkeypatch, tmp_path):
  screenshot_ref = _write_screenshot(tmp_path, data=b"vision-runner-image")
  record = _candidate_record()
  record["artifact_refs"] = {**record["artifact_refs"], "screenshot": screenshot_ref}
  _write_candidates(tmp_path, [record])

  def fake_urlopen(req, timeout):
    return _FakeResponse(_ollama_payload(_valid_confirmation_content(_vision_bundle(tmp_path, screenshot_ref=screenshot_ref))))

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.ollama.urllib_request.urlopen",
    fake_urlopen,
  )

  run_confirmation(
    config=ConfirmationConfig(
      provider="ollama-vision",
      model=GEMMA_VISION_MODEL,
      base_url="http://localhost:11434/api",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="vision-success",
      limit=1,
      save_prompts=True,
      save_raw_responses=True,
    ),
  )

  output_dir = tmp_path / "confirmations" / "vision-success"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  record = json.loads((output_dir / "confirmations.jsonl").read_text(encoding="utf-8"))
  raw_response = json.loads(next((output_dir / "raw_responses").glob("*.json")).read_text(encoding="utf-8"))

  assert manifest["provider"] == "ollama-vision"
  assert manifest["model"] == GEMMA_VISION_MODEL
  assert manifest["prompt_version"] == CALIBRATED_VISION_PROMPT_VERSION
  assert manifest["input_mode"] == "vision"
  assert manifest["input_modalities"] == ["text", "image"]
  assert manifest["image_source"] == "state_screenshot"
  assert manifest["raw_logging"]["save_raw_images"] is False
  assert record["input_modalities"] == ["text", "image"]
  assert record["image_source"] == "state_screenshot"
  assert record["image_input"]["screenshot"] == screenshot_ref
  assert record["image_inputs"] == [record["image_input"]]
  assert "sha256" in record["image_input"]
  assert "base64" not in json.dumps(raw_response).lower()


def test_ollama_malformed_assistant_content_becomes_uncertain_in_runner(monkeypatch, tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  def fake_urlopen(req, timeout):
    return _FakeResponse(_ollama_payload("{not valid json"))

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.ollama.urllib_request.urlopen",
    fake_urlopen,
  )

  run_confirmation(
    config=ConfirmationConfig(
      provider="ollama",
      model="qwen2.5:7b",
      base_url="http://localhost:11434/api",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="ollama-malformed",
      limit=1,
    ),
  )

  record = json.loads(
    (tmp_path / "confirmations" / "ollama-malformed" / "confirmations.jsonl").read_text(encoding="utf-8")
  )
  assert record["decision"] == "uncertain"
  assert record["confidence"] == 0.0
  assert record["parse_status"] == "malformed_json"
  assert not (tmp_path / "confirmations" / "ollama-malformed" / "raw_responses").exists()


def test_ollama_strict_parse_fails_on_malformed_assistant_content(monkeypatch, tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  def fake_urlopen(req, timeout):
    return _FakeResponse(_ollama_payload("{not valid json"))

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.ollama.urllib_request.urlopen",
    fake_urlopen,
  )

  with pytest.raises(ConfirmationParseError):
    run_confirmation(
      config=ConfirmationConfig(
        provider="ollama",
        model="qwen2.5:7b",
        base_url="http://localhost:11434/api",
        strict_parse=True,
      ),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="ollama-strict-malformed",
        limit=1,
      ),
    )


def test_ollama_transport_error_becomes_client_error_in_runner(monkeypatch, tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  def fake_urlopen(req, timeout):
    raise error.URLError("connection refused")

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.ollama.urllib_request.urlopen",
    fake_urlopen,
  )

  run_confirmation(
    config=ConfirmationConfig(
      provider="ollama",
      model="qwen2.5:7b",
      base_url="http://localhost:11434/api",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="ollama-transport-error",
      limit=1,
    ),
  )

  record = json.loads(
    (tmp_path / "confirmations" / "ollama-transport-error" / "confirmations.jsonl").read_text(encoding="utf-8")
  )
  assert record["decision"] == "uncertain"
  assert record["parse_status"] == "client_error"
  assert "Failed to reach Ollama" in record["error"]


def test_ollama_timeout_error_mentions_timeout(monkeypatch):
  bundle = _bundle()
  prompt = build_confirmation_prompt(bundle)

  def fake_urlopen(req, timeout):
    raise TimeoutError("timed out")

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.ollama.urllib_request.urlopen",
    fake_urlopen,
  )

  client = OllamaConfirmationClient(
    ConfirmationConfig(
      provider="ollama",
      model="qwen2.5:7b",
      base_url="http://localhost:11434/api",
      timeout_seconds=3.0,
    )
  )

  with pytest.raises(RuntimeError, match="timed out after 3.0 seconds"):
    client.confirm(prompt)


def test_ollama_provider_requires_type_or_limit(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(ValueError, match="requires --candidate-type, --candidate-id, --candidate-id-file, or --limit"):
    run_confirmation(
      config=ConfirmationConfig(
        provider="ollama",
        model="qwen2.5:7b",
        base_url="http://localhost:11434/api",
      ),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="unsafe",
      ),
    )
