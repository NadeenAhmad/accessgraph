from __future__ import annotations

import pytest

from src.analysis.confirmation.models import (
  CALIBRATED_TEXT_PROMPT_VERSION,
  CALIBRATED_VISION_PROMPT_VERSION,
  GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  PROMPT_VERSION,
  VISION_PROMPT_VERSION,
  ConfirmationConfig,
)
from src.analysis.confirmation.providers.fake import FakeConfirmationClient
from src.analysis.confirmation.providers.ollama import (
  DEFAULT_OLLAMA_API_BASE_URL,
  OllamaConfirmationClient,
)
from src.analysis.confirmation.providers.ollama_vision import OllamaVisionConfirmationClient
from src.analysis.confirmation.providers.openai import OPENAI_API_KEY_ENV, OpenAIConfirmationClient
from src.analysis.confirmation.providers.openai_vision import OpenAIVisionConfirmationClient
from src.analysis.confirmation.providers.registry import build_confirmation_client, resolve_confirmation_config


def test_build_confirmation_client_constructs_fake_client_with_configured_model():
  client = build_confirmation_client(ConfirmationConfig(provider="fake", model="fake-test-model"))

  assert isinstance(client, FakeConfirmationClient)
  assert client.model == "fake-test-model"


def test_build_confirmation_client_constructs_ollama_client():
  client = build_confirmation_client(
    ConfirmationConfig(
      provider="ollama",
      model="qwen2.5:7b",
      base_url=DEFAULT_OLLAMA_API_BASE_URL,
    )
  )

  assert isinstance(client, OllamaConfirmationClient)
  assert client.model == "qwen2.5:7b"
  assert client.base_url == DEFAULT_OLLAMA_API_BASE_URL


def test_build_confirmation_client_constructs_ollama_vision_client():
  client = build_confirmation_client(
    ConfirmationConfig(
      provider="ollama-vision",
      model="qwen2.5vl:7b",
      base_url=DEFAULT_OLLAMA_API_BASE_URL,
    )
  )

  assert isinstance(client, OllamaVisionConfirmationClient)
  assert client.model == "qwen2.5vl:7b"
  assert client.base_url == DEFAULT_OLLAMA_API_BASE_URL


def test_build_confirmation_client_constructs_openai_client(monkeypatch):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "test-key")

  client = build_confirmation_client(ConfirmationConfig(provider="openai", model="gpt-5.4-mini"))

  assert isinstance(client, OpenAIConfirmationClient)
  assert client.model == "gpt-5.4-mini"


def test_build_confirmation_client_constructs_openai_vision_client(monkeypatch):
  monkeypatch.setenv(OPENAI_API_KEY_ENV, "test-key")

  client = build_confirmation_client(ConfirmationConfig(provider="openai-vision", model="gpt-5.4-mini"))

  assert isinstance(client, OpenAIVisionConfirmationClient)
  assert client.model == "gpt-5.4-mini"


def test_build_confirmation_client_rejects_unsupported_provider():
  with pytest.raises(ValueError, match="Unsupported confirmation provider"):
    build_confirmation_client(ConfirmationConfig(provider="bogus", model="qwen2.5:7b"))


def test_resolve_confirmation_config_preserves_fake_defaults():
  config = ConfirmationConfig(provider="fake", model="")

  resolved = resolve_confirmation_config(config)

  assert resolved == config


def test_resolve_confirmation_config_preserves_explicit_calibrated_text_prompt():
  resolved = resolve_confirmation_config(
    ConfirmationConfig(provider="fake", prompt_version=CALIBRATED_TEXT_PROMPT_VERSION)
  )

  assert resolved.prompt_version == CALIBRATED_TEXT_PROMPT_VERSION


def test_resolve_confirmation_config_maps_default_prompt_to_vision_provider_default():
  resolved = resolve_confirmation_config(
    ConfirmationConfig(
      provider="ollama-vision",
      model="qwen2.5vl:7b",
      base_url=DEFAULT_OLLAMA_API_BASE_URL,
      prompt_version=PROMPT_VERSION,
    )
  )

  assert resolved.prompt_version == VISION_PROMPT_VERSION


def test_resolve_confirmation_config_preserves_explicit_calibrated_vision_prompt():
  resolved = resolve_confirmation_config(
    ConfirmationConfig(
      provider="ollama-vision",
      model="qwen2.5vl:7b",
      base_url=DEFAULT_OLLAMA_API_BASE_URL,
      prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
    )
  )

  assert resolved.prompt_version == CALIBRATED_VISION_PROMPT_VERSION


def test_resolve_confirmation_config_preserves_explicit_guided_html_screenshot_prompt():
  resolved = resolve_confirmation_config(
    ConfirmationConfig(
      provider="openai-vision",
      model="gpt-5.4-mini",
      prompt_version=GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
    )
  )

  assert resolved.prompt_version == GUIDED_HTML_SCREENSHOT_PROMPT_VERSION


def test_resolve_confirmation_config_maps_default_prompt_to_openai_vision_default():
  resolved = resolve_confirmation_config(
    ConfirmationConfig(
      provider="openai-vision",
      model="gpt-5.4-mini",
      prompt_version=PROMPT_VERSION,
    )
  )

  assert resolved.prompt_version == CALIBRATED_VISION_PROMPT_VERSION


def test_resolve_confirmation_config_preserves_explicit_openai_calibrated_vision_prompt():
  resolved = resolve_confirmation_config(
    ConfirmationConfig(
      provider="openai-vision",
      model="gpt-5.4-mini",
      prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
    )
  )

  assert resolved.prompt_version == CALIBRATED_VISION_PROMPT_VERSION


def test_resolve_confirmation_config_rejects_incompatible_prompt_version():
  with pytest.raises(ValueError, match="incompatible"):
    resolve_confirmation_config(
      ConfirmationConfig(
        provider="ollama",
        model="qwen2.5:7b",
        base_url=DEFAULT_OLLAMA_API_BASE_URL,
        prompt_version=VISION_PROMPT_VERSION,
      )
    )


@pytest.mark.parametrize(
  "obsolete_prompt",
  [
    "confirm_v1",
    "confirm_v3_text",
    "confirm_v4_text",
    "confirm_v4_2_text",
  ],
)
def test_resolve_confirmation_config_rejects_obsolete_text_prompts(obsolete_prompt):
  with pytest.raises(ValueError, match="incompatible"):
    resolve_confirmation_config(
      ConfirmationConfig(
        provider="ollama",
        model="qwen2.5:7b",
        base_url=DEFAULT_OLLAMA_API_BASE_URL,
        prompt_version=obsolete_prompt,
      )
    )


@pytest.mark.parametrize(
  "obsolete_prompt",
  [
    "confirm_v2_vision",
    "confirm_v3_vision",
    "confirm_v4_vision",
  ],
)
def test_resolve_confirmation_config_rejects_obsolete_vision_prompts(obsolete_prompt):
  with pytest.raises(ValueError, match="incompatible"):
    resolve_confirmation_config(
      ConfirmationConfig(
        provider="ollama-vision",
        model="qwen2.5vl:7b",
        base_url=DEFAULT_OLLAMA_API_BASE_URL,
        prompt_version=obsolete_prompt,
      )
    )


def test_resolve_confirmation_config_requires_model_for_real_provider():
  with pytest.raises(ValueError, match="requires a non-empty model"):
    resolve_confirmation_config(
      ConfirmationConfig(
        provider="ollama",
        model=" ",
        base_url=DEFAULT_OLLAMA_API_BASE_URL,
      )
    )


def test_resolve_confirmation_config_validates_openai_model():
  resolved = resolve_confirmation_config(ConfirmationConfig(provider="openai", model=" gpt-5.4-mini "))

  assert resolved.model == "gpt-5.4-mini"


def test_resolve_confirmation_config_rejects_unsupported_openai_model():
  with pytest.raises(ValueError, match="unsupported for --provider 'openai'"):
    resolve_confirmation_config(ConfirmationConfig(provider="openai", model="not-a-model"))


def test_resolve_confirmation_config_rejects_unsupported_openai_vision_model():
  with pytest.raises(ValueError, match="unsupported for --provider 'openai-vision'"):
    resolve_confirmation_config(ConfirmationConfig(provider="openai-vision", model="not-a-model"))


def test_resolve_confirmation_config_normalizes_ollama_base_url():
  resolved = resolve_confirmation_config(
    ConfirmationConfig(
      provider="ollama",
      model="qwen2.5:7b",
      base_url="http://localhost:11434",
    )
  )

  assert resolved.base_url == DEFAULT_OLLAMA_API_BASE_URL


def test_resolve_confirmation_config_rejects_non_positive_timeout():
  with pytest.raises(ValueError, match="timeout must be greater than zero"):
    resolve_confirmation_config(ConfirmationConfig(timeout_seconds=0))
