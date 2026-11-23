from __future__ import annotations

from typing import Protocol

from ..models import ConfirmationPrompt, ConfirmationProviderResponse


class ConfirmationClient(Protocol):
  provider: str
  model: str

  def confirm(self, prompt: ConfirmationPrompt) -> ConfirmationProviderResponse:
    ...


class ProviderOutOfCredits(RuntimeError):
  """The provider account or key has no credit left.

  The confirmation runner re-raises this instead of recording an `uncertain` verdict, so a run that runs out
  of credit stops at once and can be resumed after a top-up (cached answers are not paid twice).
  """
