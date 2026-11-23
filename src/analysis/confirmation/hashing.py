from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import ConfirmationConfig


def stable_json_dumps(value: Any) -> str:
  return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(value: str | bytes) -> str:
  data = value if isinstance(value, bytes) else value.encode("utf-8", errors="ignore")
  return hashlib.sha256(data).hexdigest()


def short_hash(value: str | bytes, *, length: int = 8) -> str:
  return sha256_hex(value)[:length]


def hash_payload(value: Any) -> str:
  return sha256_hex(stable_json_dumps(value))


def config_hash(config: ConfirmationConfig) -> str:
  return hash_payload(config.decision_affecting_payload())


def candidate_record_hash(record: dict[str, Any]) -> str:
  return hash_payload(record)
