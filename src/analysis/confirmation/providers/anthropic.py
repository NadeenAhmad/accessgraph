"""Anthropic (Claude) confirmation providers: `anthropic` (text) and `anthropic-vision` (text + screenshots).

Uses the official `anthropic` Python SDK (imported lazily, so other providers work without it). Credentials
are resolved by the SDK (ANTHROPIC_API_KEY, or an `ant auth login` profile). The response is constrained with
structured outputs to the same JSON schema the other providers use.

Notes on current Claude models: they reject non-default sampling parameters, so `temperature` is never sent
(determinism comes from the response cache, see caching.py); thinking is adaptive and its depth is set with
`effort` (None = the model's default).
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from ..models import ConfirmationConfig, ConfirmationPrompt, ConfirmationProviderResponse
from ..response_schema import confirmation_response_json_schema

DEFAULT_MAX_TOKENS = 16000
UNSUPPORTED_SCHEMA_KEYWORDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
                               "minLength", "maxLength")


@dataclass(frozen=True)
class AnthropicPricing:
  """USD per million tokens. `long_*` apply when the whole prompt exceeds `long_prompt_threshold` tokens."""
  input: float
  output: float
  long_prompt_threshold: int | None = None
  long_input: float | None = None
  long_output: float | None = None
  cache_read_multiplier: float = 0.1
  cache_write_multiplier: float = 1.25  # 5-minute cache writes


# Claude API first-party list prices (checked 2026-11-13; see eval/prices_2026-11-13.yaml).
ANTHROPIC_PRICING_USD: dict[str, AnthropicPricing] = {
  "claude-haiku-5-5": AnthropicPricing(0.10, 0.50, long_prompt_threshold=100_000, long_input=0.50, long_output=2.50),
  "claude-sonnet-5-5": AnthropicPricing(2.00, 10.00),
  "claude-opus-5-5": AnthropicPricing(4.00, 20.00),
}
SUPPORTED_ANTHROPIC_MODELS = tuple(ANTHROPIC_PRICING_USD)
ANTHROPIC_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def anthropic_schema(prompt_version: str) -> dict[str, Any]:
  """The shared confirmation schema without keywords structured outputs do not accept (checked by the parser)."""
  schema = copy.deepcopy(confirmation_response_json_schema(prompt_version))

  def strip(node: Any) -> None:
    if isinstance(node, dict):
      for key in UNSUPPORTED_SCHEMA_KEYWORDS:
        node.pop(key, None)
      for value in node.values():
        strip(value)
    elif isinstance(node, list):
      for value in node:
        strip(value)

  strip(schema)
  return schema


def estimate_anthropic_cost_usd(model: str, usage: dict[str, Any] | None) -> float | None:
  pricing = ANTHROPIC_PRICING_USD.get(model)
  if pricing is None or not usage:
    return None
  plain = int(usage.get("input_tokens") or 0)
  cache_read = int(usage.get("cache_read_input_tokens") or 0)
  cache_write = int(usage.get("cache_creation_input_tokens") or 0)
  output = int(usage.get("output_tokens") or 0)
  in_rate, out_rate = pricing.input, pricing.output
  if pricing.long_prompt_threshold and plain + cache_read + cache_write > pricing.long_prompt_threshold:
    in_rate, out_rate = pricing.long_input or in_rate, pricing.long_output or out_rate
  input_cost = (plain + cache_read * pricing.cache_read_multiplier + cache_write * pricing.cache_write_multiplier) * in_rate
  return (input_cost + output * out_rate) / 1_000_000


def build_anthropic_request(
  *,
  model: str,
  prompt: ConfirmationPrompt,
  images: list[tuple[str, str]] | None = None,
  effort: str | None = None,
  max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
  """Keyword arguments for `client.messages.create`. `images` is a list of (media_type, base64_data)."""
  return build_anthropic_json_request(model=model, system=prompt.system_prompt, user=prompt.user_prompt,
                                      schema=anthropic_schema(prompt.prompt_version), images=images, effort=effort,
                                      max_tokens=max_tokens)


def strip_unsupported_schema_keywords(schema: dict[str, Any]) -> dict[str, Any]:
  schema = copy.deepcopy(schema)

  def strip(node: Any) -> None:
    if isinstance(node, dict):
      for key in UNSUPPORTED_SCHEMA_KEYWORDS:
        node.pop(key, None)
      for value in node.values():
        strip(value)
    elif isinstance(node, list):
      for value in node:
        strip(value)

  strip(schema)
  return schema


def build_anthropic_json_request(
  *,
  model: str,
  system: str,
  user: str,
  schema: dict[str, Any],
  images: list[tuple[str, str]] | None = None,
  effort: str | None = None,
  max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
  content: list[dict[str, Any]] = [
    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
    for media_type, data in (images or [])
  ]
  content.append({"type": "text", "text": user})
  output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": strip_unsupported_schema_keywords(schema)}}
  if effort:
    output_config["effort"] = effort
  return {
    "model": model,
    "max_tokens": max_tokens,
    # The system prompt is identical for every candidate: mark it cacheable (no effect below the model's minimum).
    "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
    "messages": [{"role": "user", "content": content}],
    "output_config": output_config,
  }


def _media_type(relative_path: str) -> str:
  suffix = PurePosixPath(relative_path).suffix.lower()
  return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}.get(suffix, "image/png")


def _usage_dict(usage: Any) -> dict[str, Any] | None:
  if usage is None:
    return None
  fields = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
  values = {name: getattr(usage, name, None) for name in fields}
  values = {k: (int(v) if isinstance(v, int) else 0) for k, v in values.items()}
  values["prompt_tokens"] = values["input_tokens"] + values["cache_read_input_tokens"] + values["cache_creation_input_tokens"]
  values["completion_tokens"] = values["output_tokens"]
  values["total_tokens"] = values["prompt_tokens"] + values["output_tokens"]
  return values


class AnthropicConfirmationClient:
  provider = "anthropic"
  uses_images = False

  def __init__(self, config: ConfirmationConfig, *, sdk_client: Any | None = None):
    if config.provider != self.provider:
      raise ValueError(f"{type(self).__name__} requires provider={self.provider!r}, got {config.provider!r}")
    self.model = require_supported_anthropic_model(config.model)
    self.effort = getattr(config, "effort", None)
    if self.effort is not None and self.effort not in ANTHROPIC_EFFORT_LEVELS:
      raise ValueError(f"Unsupported effort {self.effort!r}; use one of {', '.join(ANTHROPIC_EFFORT_LEVELS)}")
    self.timeout_seconds = config.timeout_seconds
    if sdk_client is None:
      try:
        import anthropic
      except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ValueError("The anthropic provider needs the `anthropic` package: pip install anthropic") from exc
      sdk_client = anthropic.Anthropic(timeout=self.timeout_seconds, max_retries=2)
    self._sdk = sdk_client

  def _images(self, prompt: ConfirmationPrompt) -> list[tuple[str, str]]:
    return []

  def confirm(self, prompt: ConfirmationPrompt) -> ConfirmationProviderResponse:
    images = self._images(prompt)
    request = build_anthropic_request(model=self.model, prompt=prompt, images=images, effort=self.effort)
    return self._send(request, images)

  def complete_json(self, *, system: str, user: str, schema: dict[str, Any], schema_name: str = "accessgraph_json",
                    image_data_urls: list[str] | None = None) -> ConfirmationProviderResponse:
    """Generic schema-constrained JSON completion (used by the LLM exploration policy)."""
    images = []
    for url in image_data_urls or []:
      head, _, data = url.partition(",")
      images.append((head.removeprefix("data:").removesuffix(";base64") or "image/png", data))
    request = build_anthropic_json_request(model=self.model, system=system, user=user, schema=schema,
                                           images=images, effort=self.effort)
    return self._send(request, images)

  def _send(self, request: dict[str, Any], images: list[tuple[str, str]]) -> ConfirmationProviderResponse:
    started = time.perf_counter()
    response = self._sdk.messages.create(**request)
    runtime_ms = int((time.perf_counter() - started) * 1000)
    usage = _usage_dict(getattr(response, "usage", None))
    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason == "refusal":
      details = getattr(response, "stop_details", None)
      raise RuntimeError(f"Anthropic refusal: {getattr(details, 'category', None)}")
    if stop_reason == "max_tokens":
      raise RuntimeError(f"Anthropic response hit max_tokens={request['max_tokens']}")
    text = next((block.text for block in response.content if getattr(block, "type", None) == "text"), "")
    if not text.strip():
      raise ValueError("Anthropic response did not include output text")
    return ConfirmationProviderResponse(
      provider=self.provider,
      model=self.model,
      raw_content=text,
      runtime_ms=runtime_ms,
      token_usage=usage,
      estimated_cost_usd=estimate_anthropic_cost_usd(self.model, usage),
      provider_metadata={
        "anthropic_response": {"id": getattr(response, "id", None), "stop_reason": stop_reason,
                               "model": getattr(response, "model", None)},
        "input_modalities": ["text", "image"] if images else ["text"],
        "request": {"max_tokens": request["max_tokens"], "effort": self.effort, "temperature_sent": False,
                    "response_format": "json_schema", "image_count": len(images)},
      },
    )


class AnthropicVisionConfirmationClient(AnthropicConfirmationClient):
  provider = "anthropic-vision"
  uses_images = True

  def _images(self, prompt: ConfirmationPrompt) -> list[tuple[str, str]]:
    from ..image_inputs import load_provider_image_inputs

    inputs = load_provider_image_inputs(prompt.bundle, provider=self.provider, context_mode=prompt.resolved_context_mode)
    if not inputs:
      raise ValueError("Anthropic vision confirmation requires at least one image input")
    return [(_media_type(item.relative_path), item.base64_data) for item in inputs]


def require_supported_anthropic_model(model_id: str) -> str:
  normalized = model_id.strip()
  if normalized in SUPPORTED_ANTHROPIC_MODELS:
    return normalized
  raise ValueError(
    f"Unsupported Anthropic confirmation model {model_id!r}. Supported models: {', '.join(SUPPORTED_ANTHROPIC_MODELS)}"
  )
