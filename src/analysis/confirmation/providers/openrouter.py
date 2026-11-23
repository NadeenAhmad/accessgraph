"""OpenRouter confirmation providers: `openrouter` (text) and `openrouter-vision` (text + screenshots).

One key reaches many models (e.g. `anthropic/claude-haiku-5.5`, `openai/gpt-6-luna`). Requests use the
OpenAI-compatible chat endpoint with a strict JSON schema, no provider fallbacks (the named model only), and
OpenRouter's own usage accounting, so `estimated_cost_usd` is the cost OpenRouter actually charged.
The key is read from OPENROUTER_API_KEY, or from the file named by OPENROUTER_ENV_FILE.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path, PurePosixPath
from typing import Any

from ..models import ConfirmationConfig, ConfirmationPrompt, ConfirmationProviderResponse
from ..response_schema import confirmation_response_json_schema
from .base import ProviderOutOfCredits
from .openai import post_openai_json

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_ENV_FILE_ENV = "OPENROUTER_ENV_FILE"
# Model families that reject non-default sampling parameters: temperature is not sent for them.
NO_SAMPLING_PREFIXES = ("anthropic/", "openai/gpt-5.5", "openai/gpt-6")
REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")


def resolve_openrouter_api_key() -> str:
  key = os.environ.get(OPENROUTER_API_KEY_ENV, "").strip()
  env_file = os.environ.get(OPENROUTER_ENV_FILE_ENV, "").strip()
  if not key and env_file and Path(env_file).expanduser().exists():
    for line in Path(env_file).expanduser().read_text(encoding="utf-8").splitlines():
      name, _, value = line.partition("=")
      if name.strip() == OPENROUTER_API_KEY_ENV:
        key = value.strip().strip("\"'")
  if not key:
    raise ValueError(f"OpenRouter confirmation requires {OPENROUTER_API_KEY_ENV} (or {OPENROUTER_ENV_FILE_ENV})")
  return key


def build_openrouter_payload(
  *,
  model: str,
  prompt: ConfirmationPrompt,
  temperature: float,
  image_data_urls: list[str] | None = None,
  reasoning_effort: str | None = None,
) -> dict[str, Any]:
  return build_chat_payload(
    model=model, system=prompt.system_prompt, user=prompt.user_prompt,
    schema=confirmation_response_json_schema(prompt.prompt_version), schema_name="accessgraph_confirmation",
    temperature=temperature, image_data_urls=image_data_urls, reasoning_effort=reasoning_effort,
  )


def build_chat_payload(
  *,
  model: str,
  system: str,
  user: str,
  schema: dict[str, Any],
  schema_name: str,
  temperature: float,
  image_data_urls: list[str] | None = None,
  reasoning_effort: str | None = None,
) -> dict[str, Any]:
  user_content: Any = user
  if image_data_urls:
    user_content = [{"type": "text", "text": user},
                    *({"type": "image_url", "image_url": {"url": url}} for url in image_data_urls)]
  payload: dict[str, Any] = {
    "model": model,
    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
    "response_format": {
      "type": "json_schema",
      "json_schema": {"name": schema_name, "strict": True, "schema": schema},
    },
    "stream": False,
    "usage": {"include": True},
    "provider": {"allow_fallbacks": False, "require_parameters": True},
  }
  if not model.startswith(NO_SAMPLING_PREFIXES):
    payload["temperature"] = temperature
  if reasoning_effort:
    payload["reasoning"] = {"effort": reasoning_effort}
  return payload


def _data_url(relative_path: str, base64_data: str) -> str:
  suffix = PurePosixPath(relative_path).suffix.lower()
  mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "image/png")
  return f"data:{mime};base64,{base64_data}"


def _usage(payload: dict[str, Any]) -> dict[str, Any] | None:
  usage = payload.get("usage")
  if not isinstance(usage, dict):
    return None
  prompt_details = usage.get("prompt_tokens_details") or {}
  output_details = usage.get("completion_tokens_details") or {}
  return {
    "prompt_tokens": usage.get("prompt_tokens"),
    "completion_tokens": usage.get("completion_tokens"),
    "total_tokens": usage.get("total_tokens"),
    "input_tokens": usage.get("prompt_tokens"),
    "output_tokens": usage.get("completion_tokens"),
    "reasoning_tokens": output_details.get("reasoning_tokens"),
    "cached_input_tokens": prompt_details.get("cached_tokens"),
    "cost_usd": usage.get("cost"),
  }


class OpenRouterConfirmationClient:
  provider = "openrouter"

  def __init__(self, config: ConfirmationConfig):
    if config.provider != self.provider:
      raise ValueError(f"{type(self).__name__} requires provider={self.provider!r}, got {config.provider!r}")
    self.model = require_openrouter_model_id(config.model)
    self.api_key = resolve_openrouter_api_key()
    self.timeout_seconds = config.timeout_seconds
    self.temperature = config.temperature
    self.effort = getattr(config, "effort", None)
    if self.effort is not None and self.effort not in REASONING_EFFORTS:
      raise ValueError(f"Unsupported effort {self.effort!r}; use one of {', '.join(REASONING_EFFORTS)}")

  def _image_urls(self, prompt: ConfirmationPrompt) -> list[str]:
    return []

  def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
    try:
      try:
        return post_openai_json(url=f"{OPENROUTER_BASE_URL}/chat/completions", payload=payload,
                                api_key=self.api_key, timeout_seconds=self.timeout_seconds)
      except RuntimeError as exc:
        if "timed out" not in str(exc):
          raise
        # a stalled request is retried once (normal answers take seconds; a stall is a transport fault)
        return post_openai_json(url=f"{OPENROUTER_BASE_URL}/chat/completions", payload=payload,
                                api_key=self.api_key, timeout_seconds=self.timeout_seconds)
    except RuntimeError as exc:
      message = str(exc).replace(self.api_key, "[redacted]")
      if re.search(r"HTTP error 402\b", message) or "insufficient credits" in message.lower():
        raise ProviderOutOfCredits(f"OpenRouter: out of credits ({message[:200]})") from None
      raise RuntimeError(message.replace("OpenAI", "OpenRouter")) from None

  def confirm(self, prompt: ConfirmationPrompt) -> ConfirmationProviderResponse:
    images = self._image_urls(prompt)
    payload = build_openrouter_payload(model=self.model, prompt=prompt, temperature=self.temperature,
                                       image_data_urls=images, reasoning_effort=self.effort)
    return self._send(payload, images)

  def complete_json(self, *, system: str, user: str, schema: dict[str, Any], schema_name: str = "accessgraph_json",
                    image_data_urls: list[str] | None = None) -> ConfirmationProviderResponse:
    """Generic schema-constrained JSON completion (used by the LLM exploration policy)."""
    images = list(image_data_urls or [])
    payload = build_chat_payload(model=self.model, system=system, user=user, schema=schema, schema_name=schema_name,
                                 temperature=self.temperature, image_data_urls=images, reasoning_effort=self.effort)
    return self._send(payload, images)

  def _send(self, payload: dict[str, Any], images: list[str]) -> ConfirmationProviderResponse:
    started = time.perf_counter()
    result = self._post(payload)
    runtime_ms = int((time.perf_counter() - started) * 1000)
    if result.get("error"):
      raise RuntimeError(f"OpenRouter response error: {result['error']}")
    choices = result.get("choices") or []
    if not choices:
      raise ValueError("OpenRouter returned no choices")
    choice = choices[0]
    finish = choice.get("finish_reason") or choice.get("native_finish_reason")
    if finish in {"length", "max_tokens"}:
      raise RuntimeError("OpenRouter response was cut off (max tokens)")
    if finish in {"content_filter", "refusal"}:
      raise RuntimeError(f"OpenRouter response refused ({finish})")
    content = (choice.get("message") or {}).get("content")
    if isinstance(content, list):
      content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
      raise ValueError("OpenRouter response did not include output text")
    usage = _usage(result)
    cost = usage.get("cost_usd") if usage else None
    return ConfirmationProviderResponse(
      provider=self.provider,
      model=self.model,
      raw_content=content,
      runtime_ms=runtime_ms,
      token_usage=usage,
      estimated_cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
      provider_metadata={
        "openrouter_response": {"id": result.get("id"), "model": result.get("model"),
                                "provider": result.get("provider"), "finish_reason": finish},
        "input_modalities": ["text", "image"] if images else ["text"],
        "request": {"url": f"{OPENROUTER_BASE_URL}/chat/completions", "timeout_seconds": self.timeout_seconds,
                    "temperature_sent": "temperature" in payload, "reasoning_effort": self.effort,
                    "allow_fallbacks": False, "response_format": "json_schema", "image_count": len(images)},
      },
    )


class OpenRouterVisionConfirmationClient(OpenRouterConfirmationClient):
  provider = "openrouter-vision"

  def _image_urls(self, prompt: ConfirmationPrompt) -> list[str]:
    from ..image_inputs import load_provider_image_inputs

    inputs = load_provider_image_inputs(prompt.bundle, provider=self.provider, context_mode=prompt.resolved_context_mode)
    if not inputs:
      raise ValueError("OpenRouter vision confirmation requires at least one image input")
    return [_data_url(item.relative_path, item.base64_data) for item in inputs]


def require_openrouter_model_id(model_id: str) -> str:
  normalized = model_id.strip()
  if "/" not in normalized or normalized.startswith(("http:", "https:")):
    raise ValueError(f"OpenRouter model must be an explicit model id like 'anthropic/claude-haiku-5.5', got {model_id!r}")
  return normalized


def openrouter_balance(api_key: str | None = None, *, timeout_seconds: float = 20.0) -> dict[str, float | None]:
  """Remaining credit for the key and the account (free call, no model is run)."""
  from urllib import request as urllib_request

  key = api_key or resolve_openrouter_api_key()

  def get(path: str) -> dict[str, Any]:
    req = urllib_request.Request(f"{OPENROUTER_BASE_URL}{path}", headers={"Authorization": f"Bearer {key}"})
    with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
      return (json.loads(response.read().decode("utf-8")) or {}).get("data") or {}

  key_info, credits = get("/key"), get("/credits")
  account_left = None
  if credits.get("total_credits") is not None:
    account_left = float(credits["total_credits"]) - float(credits.get("total_usage") or 0.0)
  key_left = key_info.get("limit_remaining")
  candidates = [v for v in (account_left, key_left) if isinstance(v, (int, float))]
  return {"account_remaining_usd": account_left, "key_remaining_usd": key_left,
          "available_usd": min(candidates) if candidates else None}
