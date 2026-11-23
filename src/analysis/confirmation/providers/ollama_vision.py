from __future__ import annotations

import time
from typing import Any

from ..image_inputs import (
  combined_image_source,
  image_input_metadata,
  load_provider_image_inputs,
)
from ..models import ConfirmationConfig, ConfirmationPrompt, ConfirmationProviderResponse
from ..response_schema import confirmation_response_json_schema
from .ollama import (
  _ollama_runtime_ms,
  _ollama_token_usage,
  join_ollama_api_url,
  post_ollama_json,
  resolve_ollama_base_url,
)


class OllamaVisionConfirmationClient:
  provider = "ollama-vision"

  def __init__(self, config: ConfirmationConfig):
    if config.provider != self.provider:
      raise ValueError(f"Ollama vision client requires provider='ollama-vision', got {config.provider!r}")
    if not config.model.strip():
      raise ValueError("Ollama vision client requires a non-empty model")
    self.model = config.model
    self.base_url = resolve_ollama_base_url(config.base_url)
    self.timeout_seconds = config.timeout_seconds
    self.temperature = config.temperature

  def confirm(self, prompt: ConfirmationPrompt) -> ConfirmationProviderResponse:
    image_inputs = load_provider_image_inputs(
      prompt.bundle,
      provider=self.provider,
      context_mode=prompt.resolved_context_mode,
    )
    request_url = join_ollama_api_url(self.base_url, "chat")
    payload = build_ollama_vision_chat_payload(
      model=self.model,
      prompt=prompt,
      image_base64_values=[image_input.base64_data for image_input in image_inputs],
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
        "input_modalities": ["text", "image"],
        "image_source": combined_image_source(image_inputs),
        "image_input": image_input_metadata(image_inputs[0]),
        "image_inputs": [image_input_metadata(image_input) for image_input in image_inputs],
        "request": {
          "url": request_url,
          "base_url": self.base_url,
          "timeout_seconds": self.timeout_seconds,
          "stream": False,
          "format": "json_schema",
          "image_count": len(image_inputs),
        },
      },
    )


def build_ollama_vision_chat_payload(
  *,
  model: str,
  prompt: ConfirmationPrompt,
  temperature: float,
  screenshot_base64: str | None = None,
  image_base64_values: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
  resolved_images = list(image_base64_values or ())
  if not resolved_images and screenshot_base64:
    resolved_images = [screenshot_base64]
  if not resolved_images:
    raise ValueError("Ollama vision confirmation requires at least one image input")
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
        "images": resolved_images,
      },
    ],
    "options": {
      "temperature": temperature,
    },
  }
