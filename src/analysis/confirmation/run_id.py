from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import ConfirmationConfig

_UNSAFE_RUN_ID_CHARS = re.compile(r"[^a-z0-9]+")


def sanitize_run_id_component(value: object) -> str:
  normalized = _UNSAFE_RUN_ID_CHARS.sub("-", str(value or "").lower()).strip("-")
  return normalized or "unknown"


def generate_confirmation_run_id(
  *,
  config: ConfirmationConfig,
  config_hash: str,
  created_at: datetime | None = None,
) -> str:
  timestamp = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  provider = sanitize_run_id_component(config.provider)
  model = sanitize_run_id_component(config.model)
  prompt = sanitize_run_id_component(config.prompt_version)
  return f"{timestamp}_{provider}_{model}_{prompt}_{config_hash[:8]}"
