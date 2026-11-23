from __future__ import annotations

import base64
import json
import types

import pytest

from src.analysis.confirmation.models import ConfirmationConfig
from src.analysis.confirmation.providers import openrouter as openrouter_module
from src.analysis.confirmation.providers.base import ProviderOutOfCredits
from src.analysis.confirmation.providers.openrouter import (
  OpenRouterConfirmationClient,
  OpenRouterVisionConfirmationClient,
  build_openrouter_payload,
  resolve_openrouter_api_key,
)


def _prompt():
  bundle = types.SimpleNamespace(candidate_id="c1", candidate_type="link-text-mismatch", state_id="state_0001")
  return types.SimpleNamespace(bundle=bundle, prompt_version="confirm_v4_1_text", prompt_hash="h",
                               resolved_context_mode="isolated_state", system_prompt="SYSTEM", user_prompt="USER")


def _result(content="{}", finish="stop", cost=0.00042):
  return {"id": "gen-1", "model": "anthropic/claude-haiku-5.5", "provider": "Anthropic",
          "choices": [{"finish_reason": finish, "message": {"content": content}}],
          "usage": {"prompt_tokens": 3000, "completion_tokens": 120, "total_tokens": 3120, "cost": cost,
                    "completion_tokens_details": {"reasoning_tokens": 40}}}


@pytest.fixture
def key(monkeypatch):
  monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")


def _client(cls=OpenRouterConfirmationClient, provider="openrouter", model="anthropic/claude-haiku-5.5", **extra):
  return cls(ConfirmationConfig(provider=provider, model=model, **extra))


def test_payload_is_strict_schema_without_fallbacks_or_sampling_for_claude():
  payload = build_openrouter_payload(model="anthropic/claude-haiku-5.5", prompt=_prompt(), temperature=0.0)
  assert payload["response_format"]["json_schema"]["strict"] is True
  assert payload["provider"] == {"allow_fallbacks": False, "require_parameters": True}
  assert payload["usage"] == {"include": True} and "temperature" not in payload
  other = build_openrouter_payload(model="some/other-model", prompt=_prompt(), temperature=0.0, reasoning_effort="high")
  assert other["temperature"] == 0.0 and other["reasoning"] == {"effort": "high"}


def test_confirm_uses_provider_reported_cost(key, monkeypatch):
  seen = {}

  def fake_post(*, url, payload, api_key, timeout_seconds):
    seen.update(url=url, payload=payload)
    return _result(content=json.dumps({"decision": "violation"}))

  monkeypatch.setattr(openrouter_module, "post_openai_json", fake_post)
  response = _client().confirm(_prompt())
  assert seen["url"].endswith("/chat/completions") and json.loads(response.raw_content)["decision"] == "violation"
  assert response.estimated_cost_usd == pytest.approx(0.00042)
  assert response.token_usage["reasoning_tokens"] == 40
  assert response.provider_metadata["request"]["allow_fallbacks"] is False


def test_out_of_credits_is_a_distinct_error_and_key_is_redacted(key, monkeypatch):
  def broke(**_):
    raise RuntimeError('OpenAI HTTP error 402: {"error":{"message":"Insufficient credits"}} sk-or-test-key')

  monkeypatch.setattr(openrouter_module, "post_openai_json", broke)
  with pytest.raises(ProviderOutOfCredits) as info:
    _client().confirm(_prompt())
  assert "sk-or-test-key" not in str(info.value)

  def other(**_):
    raise RuntimeError("OpenAI HTTP error 500: boom")

  monkeypatch.setattr(openrouter_module, "post_openai_json", other)
  with pytest.raises(RuntimeError, match="OpenRouter HTTP error 500"):
    _client().confirm(_prompt())


def test_truncated_or_refused_answers_raise(key, monkeypatch):
  for finish in ("length", "content_filter"):
    monkeypatch.setattr(openrouter_module, "post_openai_json", lambda finish=finish, **_: _result(finish=finish))
    with pytest.raises(RuntimeError):
      _client().confirm(_prompt())


def test_vision_sends_data_urls(key, monkeypatch):
  image = types.SimpleNamespace(relative_path="s/screenshot.png", base64_data=base64.b64encode(b"x").decode())
  monkeypatch.setattr("src.analysis.confirmation.image_inputs.load_provider_image_inputs",
                      lambda bundle, provider, context_mode=None: [image])
  seen = {}
  monkeypatch.setattr(openrouter_module, "post_openai_json",
                      lambda *, url, payload, api_key, timeout_seconds: seen.update(payload=payload) or _result())
  _client(OpenRouterVisionConfirmationClient, "openrouter-vision").confirm(_prompt())
  parts = seen["payload"]["messages"][1]["content"]
  assert parts[0]["type"] == "text" and parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_key_from_env_file_and_model_id_validation(tmp_path, monkeypatch):
  monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
  env_file = tmp_path / "openrouter.env"
  env_file.write_text("OPENROUTER_API_KEY=sk-or-file\n")
  monkeypatch.setenv("OPENROUTER_ENV_FILE", str(env_file))
  assert resolve_openrouter_api_key() == "sk-or-file"
  with pytest.raises(ValueError, match="explicit model id"):
    _client(model="claude-haiku")
  monkeypatch.delenv("OPENROUTER_ENV_FILE")
  with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
    resolve_openrouter_api_key()


def test_runner_stops_on_out_of_credits_instead_of_recording_uncertain(tmp_path):
  from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation
  from src.analysis.confirmation.providers.registry import (
    SUPPORTED_CONFIRMATION_PROVIDERS,
    get_confirmation_provider_spec,
  )

  (tmp_path / "candidates").mkdir()
  record = {"schema_version": "1", "candidate_id": "c1", "candidate_type": "link-text-mismatch",
            "state_id": "state_0001", "element_refs": [{"bucket": "links", "element_id": "a1"}],
            "selection_reason": ["x"], "required_context": ["element evidence"],
            "evidence": {"sample": {"text": "x"}}, "state_context": {"url": "http://127.0.0.1/", "title": "T"},
            "graph_context": {"transition_path": []}, "artifact_refs": {},
            "generator": {"name": "offline_semantic_candidate_builder", "version": "1"}}
  (tmp_path / "candidates" / "candidates.jsonl").write_text(json.dumps(record) + "\n")

  class Broke:
    provider, model = "fake", "fake-confirmation-model"

    def confirm(self, prompt):
      raise ProviderOutOfCredits("out of credits")

  with pytest.raises(ProviderOutOfCredits):
    run_confirmation(config=ConfirmationConfig(), options=ConfirmationRunOptions(run_dir=tmp_path, confirmation_run_id="r"),
                     client=Broke())
  assert {"anthropic", "anthropic-vision", "openrouter", "openrouter-vision"} <= set(SUPPORTED_CONFIRMATION_PROVIDERS)
  assert get_confirmation_provider_spec("openrouter-vision").screenshot_required
  assert get_confirmation_provider_spec("anthropic").validate_model("claude-haiku-5-5") == "claude-haiku-5-5"


def test_effort_only_changes_config_hash_when_set():
  from src.analysis.confirmation.hashing import config_hash

  assert "effort" not in ConfirmationConfig().decision_affecting_payload()
  assert config_hash(ConfirmationConfig(effort="low")) != config_hash(ConfirmationConfig())
