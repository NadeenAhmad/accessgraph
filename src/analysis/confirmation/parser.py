from __future__ import annotations

import json
import re
from typing import Any

from .models import ConfirmationParseStatus, ParsedConfirmation, ReviewBundle
from .response_schema import confirmation_response_uses_bundle_metadata

_FENCED_JSON_RE = re.compile(r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


class ConfirmationParseError(ValueError):
  def __init__(self, message: str, *, parse_status: ConfirmationParseStatus):
    super().__init__(message)
    self.parse_status = parse_status


def parse_confirmation_response(
  content: Any,
  *,
  bundle: ReviewBundle,
  strict: bool = False,
  prompt_version: str | None = None,
) -> ParsedConfirmation:
  try:
    payload = _parse_payload(content)
    return _build_parsed_confirmation(
      payload,
      bundle,
      use_bundle_metadata=_use_bundle_metadata(prompt_version),
    )
  except ConfirmationParseError as exc:
    if strict:
      raise
    return _uncertain_from_error(bundle, parse_status=exc.parse_status, error=str(exc))


def _parse_payload(content: Any) -> dict[str, Any]:
  if isinstance(content, dict):
    payload = content
  elif isinstance(content, str):
    payload = _parse_string_payload(content)
  else:
    raise ConfirmationParseError(
      "Confirmation response must be JSON object text or a JSON object",
      parse_status="malformed_json",
    )
  if not isinstance(payload, dict):
    raise ConfirmationParseError("Confirmation response JSON must be an object", parse_status="schema_error")
  return payload


def _parse_string_payload(content: str) -> Any:
  stripped = content.strip()
  fenced = _FENCED_JSON_RE.match(stripped)
  if fenced:
    stripped = fenced.group("body").strip()
  try:
    return json.loads(stripped)
  except json.JSONDecodeError as exc:
    raise ConfirmationParseError(
      f"Confirmation response is not valid JSON: {str(exc)}",
      parse_status="malformed_json",
    ) from exc


def _use_bundle_metadata(prompt_version: str | None) -> bool:
  return bool(prompt_version and confirmation_response_uses_bundle_metadata(prompt_version))


def _build_parsed_confirmation(
  payload: dict[str, Any],
  bundle: ReviewBundle,
  *,
  use_bundle_metadata: bool,
) -> ParsedConfirmation:
  if use_bundle_metadata:
    candidate_id = bundle.candidate_id
    candidate_type = bundle.candidate_type
    state_id = bundle.state_id
  else:
    candidate_id = _required_string(payload, "candidate_id")
    candidate_type = _required_string(payload, "candidate_type")
    state_id = _required_string(payload, "state_id")
    if candidate_id != bundle.candidate_id or candidate_type != bundle.candidate_type or state_id != bundle.state_id:
      raise ConfirmationParseError(
        "Confirmation response ids do not match the source candidate",
        parse_status="id_mismatch",
      )

  decision = _required_string(payload, "decision")
  if decision not in {"violation", "no_violation", "uncertain"}:
    raise ConfirmationParseError(f"Unsupported confirmation decision: {decision}", parse_status="schema_error")

  confidence = payload.get("confidence")
  if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0.0 <= float(confidence) <= 1.0:
    raise ConfirmationParseError("Confirmation confidence must be a number from 0.0 to 1.0", parse_status="schema_error")

  supporting_evidence = payload.get("supporting_evidence")
  if not isinstance(supporting_evidence, list):
    raise ConfirmationParseError("Confirmation supporting_evidence must be an array", parse_status="schema_error")

  return ParsedConfirmation(
    candidate_id=candidate_id,
    candidate_type=candidate_type,
    state_id=state_id,
    decision=decision,
    confidence=float(confidence),
    reason=_required_string(payload, "reason"),
    supporting_evidence=tuple(str(item) for item in supporting_evidence),
    parse_status="parsed",
    error=None,
  )


def _required_string(payload: dict[str, Any], key: str) -> str:
  value = payload.get(key)
  if isinstance(value, str) and value.strip():
    return value
  raise ConfirmationParseError(f"Confirmation response is missing `{key}`", parse_status="schema_error")


def _uncertain_from_error(
  bundle: ReviewBundle,
  *,
  parse_status: ConfirmationParseStatus,
  error: str,
) -> ParsedConfirmation:
  return ParsedConfirmation(
    candidate_id=bundle.candidate_id,
    candidate_type=bundle.candidate_type,
    state_id=bundle.state_id,
    decision="uncertain",
    confidence=0.0,
    reason=f"Confirmation response could not be parsed: {error}",
    supporting_evidence=(),
    parse_status=parse_status,
    error=error,
  )
