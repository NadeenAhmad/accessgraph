from __future__ import annotations

import json
import os
import time
from socket import timeout as SocketTimeout
from typing import Any
from urllib import error, request as urllib_request

from ..models import ConfirmationConfig, ConfirmationPrompt, ConfirmationProviderResponse
from ..response_schema import confirmation_response_json_schema

DEFAULT_OLLAMA_API_BASE_URL = "http://localhost:11434/api"
ACCESSGRAPH_OLLAMA_BASE_URL_ENV = "ACCESSGRAPH_OLLAMA_BASE_URL"
OLLAMA_BASE_URL_ENV = "OLLAMA_BASE_URL"


class OllamaConfirmationClient:
  provider = "ollama"

  def __init__(self, config: ConfirmationConfig):
    if config.provider != self.provider:
      raise ValueError(f"Ollama client requires provider='ollama', got {config.provider!r}")
    if not config.model.strip():
      raise ValueError("Ollama client requires a non-empty model")
    self.model = config.model
    self.base_url = resolve_ollama_base_url(config.base_url)
    self.timeout_seconds = config.timeout_seconds
    self.temperature = config.temperature

  def confirm(self, prompt: ConfirmationPrompt) -> ConfirmationProviderResponse:
    request_url = join_ollama_api_url(self.base_url, "chat")
    payload = build_ollama_chat_payload(
      model=self.model,
      prompt=prompt,
      temperature=self.temperature,
    )
    started = time.perf_counter()
    response_payload = post_ollama_json(
      url=request_url,
      payload=payload,
      timeout_seconds=self.timeout_seconds,
    )
    measured_runtime_ms = int((time.perf_counter() - started) * 1000)
    message = response_payload.get("message")
    if not isinstance(message, dict):
      raise ValueError("Ollama response did not include a `message` object")
    content = message.get("content")
    if not isinstance(content, str):
      raise ValueError("Ollama response message did not include string `content`")

    return ConfirmationProviderResponse(
      provider=self.provider,
      model=self.model,
      raw_content=content,
      runtime_ms=_ollama_runtime_ms(response_payload, fallback_runtime_ms=measured_runtime_ms),
      token_usage=_ollama_token_usage(response_payload),
      estimated_cost_usd=0.0,
      provider_metadata={
        "ollama_response": response_payload,
        "request": {
          "url": request_url,
          "base_url": self.base_url,
          "timeout_seconds": self.timeout_seconds,
          "stream": False,
          "format": "json_schema",
        },
      },
    )


def resolve_ollama_base_url(explicit_base_url: str | None = None) -> str:
  raw_base_url = (
    explicit_base_url
    or os.environ.get(ACCESSGRAPH_OLLAMA_BASE_URL_ENV)
    or os.environ.get(OLLAMA_BASE_URL_ENV)
    or DEFAULT_OLLAMA_API_BASE_URL
  )
  return normalize_ollama_api_base_url(raw_base_url)


def normalize_ollama_api_base_url(base_url: str) -> str:
  normalized = base_url.strip().rstrip("/")
  if not normalized:
    raise ValueError("Ollama base URL must not be empty")
  if normalized.endswith("/api"):
    return normalized
  return f"{normalized}/api"


def join_ollama_api_url(base_url: str, endpoint: str) -> str:
  return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def build_ollama_chat_payload(
  *,
  model: str,
  prompt: ConfirmationPrompt,
  temperature: float,
) -> dict[str, Any]:
  return {
    "model": model,
    "stream": False,
    "format": confirmation_response_json_schema(prompt.prompt_version),
    "messages": [
      {
        "role": "system",
        "content": prompt.system_prompt,
      },
      {
        "role": "user",
        "content": prompt.user_prompt,
      },
    ],
    "options": {
      "temperature": temperature,
    },
  }


def post_ollama_json(
  *,
  url: str,
  payload: dict[str, Any],
  timeout_seconds: float,
) -> dict[str, Any]:
  encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
  request = urllib_request.Request(
    url,
    data=encoded,
    headers={"Content-Type": "application/json"},
    method="POST",
  )
  try:
    with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
      raw_body = response.read().decode("utf-8")
  except error.HTTPError as exc:
    body = exc.read().decode("utf-8", errors="replace")
    raise RuntimeError(f"Ollama HTTP error {exc.code}: {body}") from exc
  except (SocketTimeout, TimeoutError) as exc:
    raise RuntimeError(f"Ollama request timed out after {timeout_seconds} seconds") from exc
  except error.URLError as exc:
    raise RuntimeError(f"Failed to reach Ollama at {url}: {exc.reason}") from exc

  try:
    parsed = json.loads(raw_body)
  except json.JSONDecodeError as exc:
    raise ValueError(f"Ollama returned invalid JSON: {raw_body[:200]}") from exc
  if not isinstance(parsed, dict):
    raise ValueError("Ollama returned a non-object JSON response")
  return parsed


def _ollama_runtime_ms(response_payload: dict[str, Any], *, fallback_runtime_ms: int) -> int:
  total_duration = response_payload.get("total_duration")
  if isinstance(total_duration, (int, float)) and not isinstance(total_duration, bool):
    return int(total_duration / 1_000_000)
  return fallback_runtime_ms


def _ollama_token_usage(response_payload: dict[str, Any]) -> dict[str, Any]:
  prompt_tokens = _optional_int(response_payload.get("prompt_eval_count"))
  completion_tokens = _optional_int(response_payload.get("eval_count"))
  total_tokens = (
    prompt_tokens + completion_tokens
    if prompt_tokens is not None and completion_tokens is not None
    else None
  )
  return {
    "prompt_tokens": prompt_tokens,
    "completion_tokens": completion_tokens,
    "total_tokens": total_tokens,
    "ollama": {
      "total_duration": response_payload.get("total_duration"),
      "load_duration": response_payload.get("load_duration"),
      "prompt_eval_duration": response_payload.get("prompt_eval_duration"),
      "eval_duration": response_payload.get("eval_duration"),
      "prompt_eval_count": prompt_tokens,
      "eval_count": completion_tokens,
    },
  }


def _optional_int(value: Any) -> int | None:
  if isinstance(value, int) and not isinstance(value, bool):
    return value
  return None
