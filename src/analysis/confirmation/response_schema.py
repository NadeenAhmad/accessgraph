from __future__ import annotations

from typing import Any

from .models import (
  CALIBRATED_TEXT_PROMPT_VERSION,
  CONFIRM_V5_TEXT_PROMPT_VERSION,
  GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  PROMPT_VERSION,
)


MINIMAL_RESPONSE_PROMPT_VERSIONS = (
  GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
)
BUNDLE_METADATA_RESPONSE_PROMPT_VERSIONS = (
  CALIBRATED_TEXT_PROMPT_VERSION,
  CONFIRM_V5_TEXT_PROMPT_VERSION,
  GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
)


def confirmation_response_uses_bundle_metadata(prompt_version: str) -> bool:
  return prompt_version in BUNDLE_METADATA_RESPONSE_PROMPT_VERSIONS


def confirmation_response_json_schema(prompt_version: str = PROMPT_VERSION) -> dict[str, Any]:
  if prompt_version in MINIMAL_RESPONSE_PROMPT_VERSIONS:
    return _minimal_confirmation_response_json_schema()
  return _full_confirmation_response_json_schema()


def _full_confirmation_response_json_schema() -> dict[str, Any]:
  return {
    "type": "object",
    "additionalProperties": False,
    "required": [
      "candidate_id",
      "candidate_type",
      "state_id",
      "decision",
      "confidence",
      "reason",
      "supporting_evidence",
    ],
    "properties": {
      "candidate_id": {"type": "string"},
      "candidate_type": {"type": "string"},
      "state_id": {"type": "string"},
      "decision": {
        "type": "string",
        "enum": ["violation", "no_violation", "uncertain"],
      },
      "confidence": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
      },
      "reason": {"type": "string"},
      "supporting_evidence": {
        "type": "array",
        "items": {"type": "string"},
      },
    },
  }


def _minimal_confirmation_response_json_schema() -> dict[str, Any]:
  return {
    "type": "object",
    "additionalProperties": False,
    "required": [
      "decision",
      "confidence",
      "reason",
      "supporting_evidence",
    ],
    "properties": {
      "decision": {
        "type": "string",
        "enum": ["violation", "no_violation", "uncertain"],
      },
      "confidence": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
      },
      "reason": {"type": "string"},
      "supporting_evidence": {
        "type": "array",
        "items": {"type": "string"},
      },
    },
  }
