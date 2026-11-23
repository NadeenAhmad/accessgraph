from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
  model_id: str
  input_usd_per_million_tokens: float
  output_usd_per_million_tokens: float

  @property
  def manifest_payload(self) -> dict[str, object]:
    return {
      "input_usd_per_million_tokens": self.input_usd_per_million_tokens,
      "output_usd_per_million_tokens": self.output_usd_per_million_tokens,
    }


MODEL_PRICING_USD: dict[str, ModelPricing] = {
  "gpt-5.4-mini": ModelPricing(
    model_id="gpt-5.4-mini",
    input_usd_per_million_tokens=0.75,
    output_usd_per_million_tokens=4.50,
  ),
  "gpt-5.4": ModelPricing(
    model_id="gpt-5.4",
    input_usd_per_million_tokens=2.50,
    output_usd_per_million_tokens=15.00,
  ),
}
SUPPORTED_OPENAI_TEXT_MODELS = ("gpt-5.4-mini", "gpt-5.4", "gpt-5.5")
SUPPORTED_OPENAI_VISION_MODELS = ("gpt-5.4-mini", "gpt-5.4", "gpt-5.5")


def require_supported_openai_model(model_id: str) -> str:
  normalized = model_id.strip()
  if normalized in SUPPORTED_OPENAI_TEXT_MODELS:
    return normalized
  supported = ", ".join(SUPPORTED_OPENAI_TEXT_MODELS)
  raise ValueError(f"Unsupported OpenAI confirmation model {model_id!r}. Supported models: {supported}")


def require_supported_openai_vision_model(model_id: str) -> str:
  normalized = model_id.strip()
  if normalized in SUPPORTED_OPENAI_VISION_MODELS:
    return normalized
  supported = ", ".join(SUPPORTED_OPENAI_VISION_MODELS)
  raise ValueError(
    f"Unsupported OpenAI vision confirmation model {model_id!r}. Supported models: {supported}"
  )


def estimate_model_cost_usd(
  *,
  input_tokens: int,
  output_tokens: int,
  pricing: ModelPricing,
) -> dict[str, float]:
  input_cost = input_tokens / 1_000_000 * pricing.input_usd_per_million_tokens
  output_cost = output_tokens / 1_000_000 * pricing.output_usd_per_million_tokens
  return {
    "input_cost_usd": input_cost,
    "output_cost_usd": output_cost,
    "total_cost_usd": input_cost + output_cost,
  }


def estimate_openai_model_cost_usd(
  *,
  model_id: str,
  input_tokens: int,
  output_tokens: int,
) -> dict[str, float]:
  model = model_id.strip()
  if model not in MODEL_PRICING_USD:
    raise ValueError(f"Unknown model pricing {model_id!r}")
  return estimate_model_cost_usd(
    input_tokens=input_tokens,
    output_tokens=output_tokens,
    pricing=MODEL_PRICING_USD[model],
  )
