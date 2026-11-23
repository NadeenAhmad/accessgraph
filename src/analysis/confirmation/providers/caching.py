"""Response cache for any confirmation client.

Wraps a client so that an identical request (same provider, model, prompt, images and decision-affecting
parameters) is answered from disk instead of calling the model again. A cache hit costs nothing and returns
the stored response unchanged, which makes re-runs free and lets published results be rebuilt exactly.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..hashing import hash_payload
from ..models import ConfirmationPrompt, ConfirmationProviderResponse

CACHE_SCHEMA_VERSION = "1"


def prompt_image_hashes(prompt: ConfirmationPrompt, *, provider: str) -> list[str]:
  """Hashes of the images a vision provider would send for this prompt (empty for text providers)."""
  if "vision" not in provider:
    return []
  from ..image_inputs import load_provider_image_inputs

  try:
    inputs = load_provider_image_inputs(prompt.bundle, provider=provider, context_mode=prompt.resolved_context_mode)
  except Exception:  # the inner client reports missing images itself
    return []
  return [hashlib.sha256(item.base64_data.encode("ascii")).hexdigest() for item in inputs]


def response_cache_key(
  prompt: ConfirmationPrompt,
  *,
  provider: str,
  model: str,
  parameters: dict[str, Any] | None = None,
) -> str:
  return hash_payload(
    {
      "cache_schema_version": CACHE_SCHEMA_VERSION,
      "provider": provider,
      "model": model,
      "prompt_version": prompt.prompt_version,
      "prompt_hash": prompt.prompt_hash,
      "resolved_context_mode": prompt.resolved_context_mode,
      "image_hashes": prompt_image_hashes(prompt, provider=provider),
      "parameters": parameters or {},
    }
  )


class CachingConfirmationClient:
  """Delegates to `inner` on a miss and stores the response; serves hits from `cache_dir` at zero cost."""

  def __init__(self, inner: Any, cache_dir: Path, *, parameters: dict[str, Any] | None = None):
    self.inner = inner
    self.provider = inner.provider
    self.model = inner.model
    self.cache_dir = Path(cache_dir)
    self.parameters = dict(parameters or {})
    self.hits = 0
    self.misses = 0

  def _path(self, key: str) -> Path:
    return self.cache_dir / key[:2] / f"{key}.json"

  def confirm(self, prompt: ConfirmationPrompt) -> ConfirmationProviderResponse:
    key = response_cache_key(prompt, provider=self.provider, model=self.model, parameters=self.parameters)
    path = self._path(key)
    if path.exists():
      stored = json.loads(path.read_text(encoding="utf-8"))
      self.hits += 1
      metadata = dict(stored.get("provider_metadata") or {})
      metadata["response_cache"] = {"hit": True, "key": key, "original_cost_usd": stored.get("estimated_cost_usd")}
      return ConfirmationProviderResponse(
        provider=stored["provider"],
        model=stored["model"],
        raw_content=stored["raw_content"],
        runtime_ms=0,
        token_usage=stored.get("token_usage"),
        estimated_cost_usd=0.0,
        provider_metadata=metadata,
      )
    response = self.inner.confirm(prompt)
    self.misses += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
      json.dumps(
        {
          "cache_schema_version": CACHE_SCHEMA_VERSION,
          "key": key,
          "provider": response.provider,
          "model": response.model,
          "raw_content": response.raw_content,
          "runtime_ms": response.runtime_ms,
          "token_usage": response.token_usage,
          "estimated_cost_usd": response.estimated_cost_usd,
          "provider_metadata": response.provider_metadata,
        },
        ensure_ascii=False,
        sort_keys=True,
      ),
      encoding="utf-8",
    )
    tmp.replace(path)
    metadata = dict(response.provider_metadata or {})
    metadata["response_cache"] = {"hit": False, "key": key}
    return replace(response, provider_metadata=metadata)
