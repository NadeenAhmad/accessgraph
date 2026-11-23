from __future__ import annotations

import time
from pathlib import PurePosixPath
from typing import Any

from ..image_inputs import (
  combined_image_source,
  image_input_metadata,
  load_provider_image_inputs,
)
from ..models import ConfirmationConfig, ConfirmationPrompt, ConfirmationProviderResponse
from ..response_schema import confirmation_response_json_schema
from .openai import (
  DEFAULT_OPENAI_RESPONSES_URL,
  OPENAI_TEMPERATURE_UNSUPPORTED_MODELS,
  extract_openai_response_text,
  openai_estimated_cost_usd,
  openai_token_usage,
  post_openai_json,
  resolve_openai_api_key,
)
from .openai_pricing import require_supported_openai_vision_model


class OpenAIVisionConfirmationClient:
  provider = "openai-vision"

  def __init__(self, config: ConfirmationConfig):
    if config.provider != self.provider:
      raise ValueError(f"OpenAI vision client requires provider='openai-vision', got {config.provider!r}")
    self.model = require_supported_openai_vision_model(config.model)
    self.api_key = resolve_openai_api_key()
    self.timeout_seconds = config.timeout_seconds
    self.temperature = config.temperature

  def confirm(self, prompt: ConfirmationPrompt) -> ConfirmationProviderResponse:
    image_inputs = load_provider_image_inputs(
      prompt.bundle,
      provider=self.provider,
      context_mode=prompt.resolved_context_mode,
    )
    payload = build_openai_vision_responses_payload(
      model=self.model,
      prompt=prompt,
      image_data_urls=[
        _screenshot_data_url(
          relative_path=image_input.relative_path,
          base64_data=image_input.base64_data,
        )
        for image_input in image_inputs
      ],
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
        "input_modalities": ["text", "image"],
        "image_source": combined_image_source(image_inputs),
        "image_input": image_input_metadata(image_inputs[0]),
        "image_inputs": [image_input_metadata(image_input) for image_input in image_inputs],
        "request": {
          "url": DEFAULT_OPENAI_RESPONSES_URL,
          "timeout_seconds": self.timeout_seconds,
          "store": False,
          "stream": False,
          "response_format": "json_schema",
          "image_count": len(image_inputs),
          "image_transport": "base64_data_url",
        },
      },
    )


def build_openai_vision_responses_payload(
  *,
  model: str,
  prompt: ConfirmationPrompt,
  temperature: float,
  screenshot_data_url: str | None = None,
  image_data_urls: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
  resolved_image_data_urls = list(image_data_urls or ())
  if not resolved_image_data_urls and screenshot_data_url:
    resolved_image_data_urls = [screenshot_data_url]
  if not resolved_image_data_urls:
    raise ValueError("OpenAI vision confirmation requires at least one image input")
  payload: dict[str, Any] = {
    "model": require_supported_openai_vision_model(model),
    "instructions": prompt.system_prompt,
    "input": [
      {
        "role": "user",
        "content": [
          {
            "type": "input_text",
            "text": prompt.user_prompt,
          },
          *[
            {
              "type": "input_image",
              "image_url": image_data_url,
            }
            for image_data_url in resolved_image_data_urls
          ],
        ],
      }
    ],
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


def _screenshot_data_url(*, relative_path: str, base64_data: str) -> str:
  return f"{_mime_type_for_path(relative_path)};base64,{base64_data}"


def _mime_type_for_path(relative_path: str) -> str:
  suffix = PurePosixPath(relative_path).suffix.lower()
  if suffix in {".jpg", ".jpeg"}:
    return "data:image/jpeg"
  if suffix == ".webp":
    return "data:image/webp"
  return "data:image/png"
