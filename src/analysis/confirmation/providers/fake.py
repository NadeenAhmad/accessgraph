from __future__ import annotations

import json

from src.analysis.candidates.taxonomy import require_supported_candidate_type

from ..models import ConfirmationPrompt, ConfirmationProviderResponse

DEFAULT_FAKE_MODEL = "fake-confirmation-model"


class FakeConfirmationClient:
  provider = "fake"

  def __init__(self, *, model: str = DEFAULT_FAKE_MODEL, malformed_response: bool = False):
    self.model = model
    self.malformed_response = malformed_response

  def confirm(self, prompt: ConfirmationPrompt) -> ConfirmationProviderResponse:
    require_supported_candidate_type(prompt.bundle.candidate_type)
    if self.malformed_response:
      raw_content = "{not valid json"
    else:
      raw_content = json.dumps(
        {
          "candidate_id": prompt.bundle.candidate_id,
          "candidate_type": prompt.bundle.candidate_type,
          "state_id": prompt.bundle.state_id,
          "decision": "uncertain",
          "confidence": 0.5,
          "reason": "Fake confirmation provider returns a deterministic uncertain decision for foundation tests.",
          "supporting_evidence": [
            f"candidate_type={prompt.bundle.candidate_type}",
            "fake_provider_default_uncertain",
          ],
        },
        ensure_ascii=False,
        sort_keys=True,
      )
    return ConfirmationProviderResponse(
      provider=self.provider,
      model=self.model,
      raw_content=raw_content,
      runtime_ms=0,
      token_usage=None,
      estimated_cost_usd=None,
    )
