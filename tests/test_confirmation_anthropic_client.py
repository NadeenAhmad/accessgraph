from __future__ import annotations

import base64
import json
import types

import pytest

from src.analysis.confirmation.models import ConfirmationConfig
from src.analysis.confirmation.providers.anthropic import (
  AnthropicConfirmationClient,
  AnthropicVisionConfirmationClient,
  anthropic_schema,
  build_anthropic_request,
  estimate_anthropic_cost_usd,
)
from src.analysis.confirmation.providers.caching import CachingConfirmationClient, response_cache_key


def _prompt(prompt_hash: str = "h1", prompt_version: str = "confirm_v4_1_text"):
  bundle = types.SimpleNamespace(candidate_id="c1", candidate_type="button-label-mismatch", state_id="state_0001")
  return types.SimpleNamespace(bundle=bundle, prompt_version=prompt_version, prompt_hash=prompt_hash,
                               resolved_context_mode="isolated_state", system_prompt="SYSTEM", user_prompt="USER")


class _StubSDK:
  def __init__(self, decision="violation", stop_reason="end_turn"):
    self.calls = []
    self.decision, self.stop_reason = decision, stop_reason
    self.messages = self

  def create(self, **kwargs):
    self.calls.append(kwargs)
    text = json.dumps({"candidate_id": "c1", "candidate_type": "button-label-mismatch", "state_id": "state_0001",
                       "decision": self.decision, "confidence": 0.8, "reason": "r", "supporting_evidence": []})
    usage = types.SimpleNamespace(input_tokens=4000, output_tokens=200, cache_read_input_tokens=1000,
                                  cache_creation_input_tokens=0)
    return types.SimpleNamespace(id="msg_1", model=kwargs["model"], stop_reason=self.stop_reason, usage=usage,
                                 stop_details=types.SimpleNamespace(category="cyber"),
                                 content=[types.SimpleNamespace(type="thinking", thinking=""),
                                          types.SimpleNamespace(type="text", text=text)])


def _config(provider="anthropic", **extra):
  return ConfirmationConfig(provider=provider, model="claude-haiku-5-5", **extra)


def test_request_shape_has_no_sampling_params_and_cacheable_system():
  request = build_anthropic_request(model="claude-haiku-5-5", prompt=_prompt(), effort="low")
  assert "temperature" not in request and "top_p" not in request
  assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
  assert request["output_config"]["effort"] == "low"
  assert request["output_config"]["format"]["type"] == "json_schema"
  assert request["messages"][0]["content"] == [{"type": "text", "text": "USER"}]
  schema = json.dumps(anthropic_schema("confirm_v4_1_text"))
  assert "minimum" not in schema and "maximum" not in schema and '"additionalProperties": false' in schema


def test_cost_estimate_uses_cache_rates_and_long_prompt_tier():
  usage = {"input_tokens": 4000, "output_tokens": 200, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0}
  assert estimate_anthropic_cost_usd("claude-haiku-5-5", usage) == pytest.approx((4000 + 100) * 0.10 / 1e6 + 200 * 0.50 / 1e6)
  long_usage = {"input_tokens": 150_000, "output_tokens": 1000}
  assert estimate_anthropic_cost_usd("claude-haiku-5-5", long_usage) == pytest.approx((150_000 * 0.50 + 1000 * 2.50) / 1e6)
  assert estimate_anthropic_cost_usd("unknown-model", usage) is None


def test_client_returns_text_block_usage_and_cost():
  sdk = _StubSDK()
  client = AnthropicConfirmationClient(_config(), sdk_client=sdk)
  response = client.confirm(_prompt())
  assert json.loads(response.raw_content)["decision"] == "violation"
  assert response.token_usage["prompt_tokens"] == 5000 and response.estimated_cost_usd > 0
  assert response.provider_metadata["request"]["temperature_sent"] is False
  assert sdk.calls[0]["model"] == "claude-haiku-5-5"


def test_refusal_and_truncation_raise_so_the_runner_records_uncertain():
  with pytest.raises(RuntimeError, match="refusal"):
    AnthropicConfirmationClient(_config(), sdk_client=_StubSDK(stop_reason="refusal")).confirm(_prompt())
  with pytest.raises(RuntimeError, match="max_tokens"):
    AnthropicConfirmationClient(_config(), sdk_client=_StubSDK(stop_reason="max_tokens")).confirm(_prompt())


def test_unsupported_model_is_rejected():
  with pytest.raises(ValueError, match="Unsupported Anthropic"):
    AnthropicConfirmationClient(ConfirmationConfig(provider="anthropic", model="gpt-x"), sdk_client=_StubSDK())


def test_vision_client_sends_images_first(monkeypatch):
  image = types.SimpleNamespace(relative_path="states/s/screenshot.png", base64_data=base64.b64encode(b"png").decode())
  monkeypatch.setattr("src.analysis.confirmation.image_inputs.load_provider_image_inputs",
                      lambda bundle, provider, context_mode=None: [image])
  sdk = _StubSDK()
  AnthropicVisionConfirmationClient(_config("anthropic-vision"), sdk_client=sdk).confirm(_prompt())
  content = sdk.calls[0]["messages"][0]["content"]
  assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
  assert content[-1] == {"type": "text", "text": "USER"}


def test_response_cache_serves_identical_requests_for_free(tmp_path):
  sdk = _StubSDK()
  client = CachingConfirmationClient(AnthropicConfirmationClient(_config(), sdk_client=sdk), tmp_path)
  first, second = client.confirm(_prompt()), client.confirm(_prompt())
  assert len(sdk.calls) == 1 and client.hits == 1 and client.misses == 1
  assert second.raw_content == first.raw_content and second.estimated_cost_usd == 0.0
  assert second.provider_metadata["response_cache"]["original_cost_usd"] == first.estimated_cost_usd
  client.confirm(_prompt(prompt_hash="h2"))
  assert len(sdk.calls) == 2
  base = dict(provider="anthropic", model="claude-haiku-5-5")
  assert response_cache_key(_prompt(), **base) != response_cache_key(_prompt(), **base, parameters={"effort": "low"})
