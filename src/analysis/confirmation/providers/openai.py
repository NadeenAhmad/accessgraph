from __future__ import annotations

import json
import os
import time
from socket import timeout as SocketTimeout
from typing import Any
from urllib import error, request as urllib_request

from ..models import ConfirmationConfig, ConfirmationPrompt, ConfirmationProviderResponse
from ..response_schema import confirmation_response_json_schema
from .openai_pricing import (
  estimate_openai_model_cost_usd,
  require_supported_openai_model,
)

DEFAULT_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_TEMPERATURE_UNSUPPORTED_MODELS = ("gpt-5.5",)


class OpenAIConfirmationClient:
  provider = "openai"

  def __init__(self, config: ConfirmationConfig):
    if config.provider != self.provider:
      raise ValueError(f"OpenAI client requires provider='openai', got {config.provider!r}")
    self.model = require_supported_openai_model(config.model)
    self.api_key = resolve_openai_api_key()
    self.timeout_seconds = config.timeout_seconds
    self.temperature = config.temperature

  def confirm(self, prompt: ConfirmationPrompt) -> ConfirmationProviderResponse:
    payload = build_openai_responses_payload(
      model=self.model,
      prompt=prompt,
      temperature=self.temperature,
    )
    started = time.perf_counter()
    response_payload = post_openai_json(
      url=DEFAULT_OPENAI_RESPONSES_URL,
      payload=payload,
      api_key=self.api_key,
      timeout_seconds=self.timeout_seconds,
    )
    measured_runtime_ms = int((time.perf_counter() - started) * 1000)
    content = extract_openai_response_text(response_payload)
    token_usage = openai_token_usage(response_payload)

    return ConfirmationProviderResponse(
      provider=self.provider,
      model=self.model,
      raw_content=content,
      runtime_ms=measured_runtime_ms,
      token_usage=token_usage,
      estimated_cost_usd=openai_estimated_cost_usd(model=self.model, token_usage=token_usage),
      provider_metadata={
        "openai_response": response_payload,
        "request": {
          "url": DEFAULT_OPENAI_RESPONSES_URL,
          "timeout_seconds": self.timeout_seconds,
          "store": False,
          "stream": False,
          "response_format": "json_schema",
        },
      },
    )


def resolve_openai_api_key() -> str:
  api_key = os.environ.get(OPENAI_API_KEY_ENV, "").strip()
  if not api_key:
    raise ValueError(f"OpenAI confirmation requires {OPENAI_API_KEY_ENV} to be set")
  return api_key


def build_openai_responses_payload(
  *,
  model: str,
  prompt: ConfirmationPrompt,
  temperature: float,
) -> dict[str, Any]:
  payload = {
    "model": require_supported_openai_model(model),
    "instructions": prompt.system_prompt,
    "input": prompt.user_prompt,
    "store": False,
    "text": {
      "format": {
        "type": "json_schema",
        "name": "accessgraph_confirmation",
        "description": "Strict JSON confirmation decision for one AccessGraph review-bundle candidate.",
        "strict": True,
        "schema": confirmation_response_json_schema(prompt.prompt_version),
      },
    },
  }
  if model not in OPENAI_TEMPERATURE_UNSUPPORTED_MODELS:
    payload["temperature"] = temperature
  return payload


def post_openai_json(
  *,
  url: str,
  payload: dict[str, Any],
  api_key: str,
  timeout_seconds: float,
) -> dict[str, Any]:
  encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
  request = urllib_request.Request(
    url,
    data=encoded,
    headers={
      "Content-Type": "application/json",
      "Authorization": f"Bearer {api_key}",
    },
    method="POST",
  )
  # timeout_seconds bounds the whole request, not only each socket read: a response that keeps trickling in (e.g.
  # keep-alive bytes while the provider waits) would otherwise never time out
  deadline = time.monotonic() + timeout_seconds
  try:
    with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
      read1 = getattr(response, "read1", None)
      if read1 is None:
        raw_body = response.read().decode("utf-8")
      else:
        parts: list[bytes] = []
        while True:
          chunk = read1(65536)
          if not chunk:
            break
          parts.append(chunk)
          if time.monotonic() > deadline:
            raise TimeoutError
        raw_body = b"".join(parts).decode("utf-8")
  except error.HTTPError as exc:
    body = exc.read().decode("utf-8", errors="replace")
    raise RuntimeError(f"OpenAI HTTP error {exc.code}: {body}") from exc
  except (SocketTimeout, TimeoutError) as exc:
    raise RuntimeError(f"OpenAI request timed out after {timeout_seconds} seconds") from exc
  except error.URLError as exc:
    raise RuntimeError(f"Failed to reach OpenAI at {url}: {exc.reason}") from exc

  try:
    parsed = json.loads(raw_body)
  except json.JSONDecodeError as exc:
    raise ValueError(f"OpenAI returned invalid JSON: {raw_body[:200]}") from exc
  if not isinstance(parsed, dict):
    raise ValueError("OpenAI returned a non-object JSON response")
  return parsed


def extract_openai_response_text(response_payload: dict[str, Any]) -> str:
  error_payload = response_payload.get("error")
  if isinstance(error_payload, dict):
    message = error_payload.get("message")
    raise RuntimeError(f"OpenAI response error: {message or error_payload}")

  status = response_payload.get("status")
  if isinstance(status, str) and status not in {"completed", ""}:
    incomplete_details = response_payload.get("incomplete_details")
    raise RuntimeError(f"OpenAI response status was {status}: {incomplete_details}")

  output_text = response_payload.get("output_text")
  if isinstance(output_text, str) and output_text.strip():
    return output_text

  chunks: list[str] = []
  output = response_payload.get("output")
  if isinstance(output, list):
    for output_item in output:
      if not isinstance(output_item, dict):
        continue
      content_items = output_item.get("content")
      if not isinstance(content_items, list):
        continue
      for content_item in content_items:
        if not isinstance(content_item, dict):
          continue
        text = content_item.get("text")
        if isinstance(text, str):
          chunks.append(text)
  combined = "".join(chunks).strip()
  if combined:
    return combined
  raise ValueError("OpenAI response did not include output text")


def openai_token_usage(response_payload: dict[str, Any]) -> dict[str, Any] | None:
  usage = response_payload.get("usage")
  if not isinstance(usage, dict):
    return None
  input_tokens = _optional_int(usage.get("input_tokens"))
  output_tokens = _optional_int(usage.get("output_tokens"))
  total_tokens = _optional_int(usage.get("total_tokens"))
  if total_tokens is None and input_tokens is not None and output_tokens is not None:
    total_tokens = input_tokens + output_tokens
  return {
    "prompt_tokens": input_tokens,
    "completion_tokens": output_tokens,
    "total_tokens": total_tokens,
    "input_tokens": input_tokens,
    "output_tokens": output_tokens,
    "openai": {
      "input_tokens_details": usage.get("input_tokens_details"),
      "output_tokens_details": usage.get("output_tokens_details"),
    },
  }


def openai_estimated_cost_usd(
  *,
  model: str,
  token_usage: dict[str, Any] | None,
) -> float | None:
  if not token_usage:
    return None
  input_tokens = token_usage.get("input_tokens")
  output_tokens = token_usage.get("output_tokens")
  if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
    return None
  try:
    return estimate_openai_model_cost_usd(
      model_id=model,
      input_tokens=input_tokens,
      output_tokens=output_tokens,
    )["total_cost_usd"]
  except ValueError:
    return None


def _optional_int(value: Any) -> int | None:
  if isinstance(value, int) and not isinstance(value, bool):
    return value
  return None
