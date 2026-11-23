from __future__ import annotations

from dataclasses import dataclass, replace

from ..models import (
  CALIBRATED_TEXT_PROMPT_VERSION,
  CALIBRATED_VISION_PROMPT_VERSION,
  CONFIRM_V5_TEXT_PROMPT_VERSION,
  CONFIRM_V5_VISION_PROMPT_VERSION,
  ConfirmationConfig,
  GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  PROMPT_VERSION,
)
from .anthropic import SUPPORTED_ANTHROPIC_MODELS
from .base import ConfirmationClient
from .fake import FakeConfirmationClient
from .ollama import OllamaConfirmationClient, resolve_ollama_base_url
from .ollama_vision import OllamaVisionConfirmationClient
from .openai import OpenAIConfirmationClient
from .openai_pricing import SUPPORTED_OPENAI_TEXT_MODELS, SUPPORTED_OPENAI_VISION_MODELS
from .openai_vision import OpenAIVisionConfirmationClient


@dataclass(frozen=True)
class ConfirmationProviderSpec:
  name: str
  default_prompt_version: str
  compatible_prompt_versions: tuple[str, ...]
  input_mode: str
  input_modalities: tuple[str, ...]
  image_source: str | None = None
  model_required: bool = False
  screenshot_required: bool = False
  uses_ollama_api: bool = False
  requires_candidate_selection: bool = False
  supported_models: tuple[str, ...] = ()

  def prompt_version_for(self, configured_prompt_version: str) -> str:
    if configured_prompt_version in self.compatible_prompt_versions:
      return configured_prompt_version
    # Preserve the historical direct-API behavior for providers whose default
    # prompt is not the dataclass default.
    if configured_prompt_version == PROMPT_VERSION:
      return self.default_prompt_version
    raise ValueError(self.incompatible_prompt_version_message(configured_prompt_version))

  def incompatible_prompt_version_message(self, prompt_version: str) -> str:
    compatible = ", ".join(self.compatible_prompt_versions)
    return (
      f"--prompt-version {prompt_version!r} is incompatible with --provider {self.name!r}. "
      f"Compatible prompt versions: {compatible}"
    )

  def validate_model(self, model: str) -> str:
    if not self.supported_models:
      return model
    normalized = model.strip()
    if normalized in self.supported_models:
      return normalized
    supported = ", ".join(self.supported_models)
    raise ValueError(
      f"--model {model!r} is unsupported for --provider {self.name!r}. "
      f"Supported models: {supported}"
    )


_PROVIDER_SPECS: dict[str, ConfirmationProviderSpec] = {
  "fake": ConfirmationProviderSpec(
    name="fake",
    default_prompt_version=CALIBRATED_TEXT_PROMPT_VERSION,
    compatible_prompt_versions=(CALIBRATED_TEXT_PROMPT_VERSION, CONFIRM_V5_TEXT_PROMPT_VERSION),
    input_mode="fake",
    input_modalities=("text",),
  ),
  "ollama": ConfirmationProviderSpec(
    name="ollama",
    default_prompt_version=CALIBRATED_TEXT_PROMPT_VERSION,
    compatible_prompt_versions=(CALIBRATED_TEXT_PROMPT_VERSION, CONFIRM_V5_TEXT_PROMPT_VERSION),
    input_mode="text",
    input_modalities=("text",),
    model_required=True,
    uses_ollama_api=True,
    requires_candidate_selection=True,
  ),
  "ollama-vision": ConfirmationProviderSpec(
    name="ollama-vision",
    default_prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
    compatible_prompt_versions=(
      CALIBRATED_VISION_PROMPT_VERSION,
      GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
      CONFIRM_V5_VISION_PROMPT_VERSION,
    ),
    input_mode="vision",
    input_modalities=("text", "image"),
    image_source="state_screenshot",
    model_required=True,
    screenshot_required=True,
    uses_ollama_api=True,
    requires_candidate_selection=True,
  ),
  "openai": ConfirmationProviderSpec(
    name="openai",
    default_prompt_version=CALIBRATED_TEXT_PROMPT_VERSION,
    compatible_prompt_versions=(CALIBRATED_TEXT_PROMPT_VERSION, CONFIRM_V5_TEXT_PROMPT_VERSION),
    input_mode="text",
    input_modalities=("text",),
    model_required=True,
    requires_candidate_selection=True,
    supported_models=SUPPORTED_OPENAI_TEXT_MODELS,
  ),
  "openai-vision": ConfirmationProviderSpec(
    name="openai-vision",
    default_prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
    compatible_prompt_versions=(
      CALIBRATED_VISION_PROMPT_VERSION,
      GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
      CONFIRM_V5_VISION_PROMPT_VERSION,
    ),
    input_mode="vision",
    input_modalities=("text", "image"),
    image_source="state_screenshot",
    model_required=True,
    screenshot_required=True,
    requires_candidate_selection=True,
    supported_models=SUPPORTED_OPENAI_VISION_MODELS,
  ),
  "anthropic": ConfirmationProviderSpec(
    name="anthropic",
    default_prompt_version=CALIBRATED_TEXT_PROMPT_VERSION,
    compatible_prompt_versions=(CALIBRATED_TEXT_PROMPT_VERSION, CONFIRM_V5_TEXT_PROMPT_VERSION),
    input_mode="text",
    input_modalities=("text",),
    model_required=True,
    requires_candidate_selection=True,
    supported_models=SUPPORTED_ANTHROPIC_MODELS,
  ),
  "anthropic-vision": ConfirmationProviderSpec(
    name="anthropic-vision",
    default_prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
    compatible_prompt_versions=(
      CALIBRATED_VISION_PROMPT_VERSION,
      GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
      CONFIRM_V5_VISION_PROMPT_VERSION,
    ),
    input_mode="vision",
    input_modalities=("text", "image"),
    image_source="state_screenshot",
    model_required=True,
    screenshot_required=True,
    requires_candidate_selection=True,
    supported_models=SUPPORTED_ANTHROPIC_MODELS,
  ),
  # OpenRouter reaches many models with one key; model ids are explicit, e.g. anthropic/claude-haiku-5.5.
  "openrouter": ConfirmationProviderSpec(
    name="openrouter",
    default_prompt_version=CALIBRATED_TEXT_PROMPT_VERSION,
    compatible_prompt_versions=(CALIBRATED_TEXT_PROMPT_VERSION, CONFIRM_V5_TEXT_PROMPT_VERSION),
    input_mode="text",
    input_modalities=("text",),
    model_required=True,
    requires_candidate_selection=True,
  ),
  "openrouter-vision": ConfirmationProviderSpec(
    name="openrouter-vision",
    default_prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
    compatible_prompt_versions=(
      CALIBRATED_VISION_PROMPT_VERSION,
      GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
      CONFIRM_V5_VISION_PROMPT_VERSION,
    ),
    input_mode="vision",
    input_modalities=("text", "image"),
    image_source="state_screenshot",
    model_required=True,
    screenshot_required=True,
    requires_candidate_selection=True,
  ),
}

SUPPORTED_CONFIRMATION_PROVIDERS = tuple(_PROVIDER_SPECS)


def get_confirmation_provider_spec(provider: str) -> ConfirmationProviderSpec:
  try:
    return _PROVIDER_SPECS[provider]
  except KeyError as exc:
    raise ValueError(f"Unsupported confirmation provider for MVP: {provider}") from exc


def resolve_confirmation_config(config: ConfirmationConfig) -> ConfirmationConfig:
  provider_spec = get_confirmation_provider_spec(config.provider)
  if config.timeout_seconds <= 0:
    raise ValueError("Confirmation timeout must be greater than zero")
  resolved = replace(
    config,
    prompt_version=provider_spec.prompt_version_for(config.prompt_version),
  )
  if provider_spec.model_required:
    if not config.model.strip():
      raise ValueError(f"{config.provider} confirmation requires a non-empty model")
    resolved = replace(resolved, model=provider_spec.validate_model(config.model))
  if provider_spec.uses_ollama_api:
    resolved = replace(resolved, base_url=resolve_ollama_base_url(config.base_url))
  return resolved


def build_confirmation_client(config: ConfirmationConfig) -> ConfirmationClient:
  get_confirmation_provider_spec(config.provider)
  if config.provider == "fake":
    return FakeConfirmationClient(model=config.model)
  if config.provider == "ollama-vision":
    return OllamaVisionConfirmationClient(config)
  if config.provider == "openai":
    return OpenAIConfirmationClient(config)
  if config.provider == "openai-vision":
    return OpenAIVisionConfirmationClient(config)
  if config.provider in ("anthropic", "anthropic-vision"):
    from .anthropic import AnthropicConfirmationClient, AnthropicVisionConfirmationClient

    return (AnthropicVisionConfirmationClient if config.provider == "anthropic-vision" else AnthropicConfirmationClient)(config)
  if config.provider in ("openrouter", "openrouter-vision"):
    from .openrouter import OpenRouterConfirmationClient, OpenRouterVisionConfirmationClient

    return (OpenRouterVisionConfirmationClient if config.provider == "openrouter-vision" else OpenRouterConfirmationClient)(config)
  return OllamaConfirmationClient(config)
