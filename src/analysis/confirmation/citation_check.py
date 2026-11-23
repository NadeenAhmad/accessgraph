"""Cited-evidence check (C3, deterministic, no model call).

v5 prompts ask the judge to cite key paths into the candidate payload it saw (e.g.
`evidence.supporting.heading_scope.text_excerpt`, `graph_context.incoming_change_record_v1.flags[0]`; vision
prompts may also cite `screenshot`). Every cited item is resolved against that payload. Paths that do not exist
are flagged, and a `violation` that cites no existing path is turned into `uncertain`.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

from .models import ParsedConfirmation, V5_PROMPT_VERSIONS

PAYLOAD_MARKER = "Candidate payload:\n"
IMAGE_CITATIONS = {"screenshot", "attached_image", "image"}
_SEGMENT = re.compile(r"([^.\[\]]+)|\[(\d+)\]")
_PREFIXES = ("candidate_payload.", "candidate.", "payload.")


def prompt_payload(user_prompt: str) -> dict[str, Any] | None:
  if PAYLOAD_MARKER not in user_prompt:
    return None
  text = user_prompt.split(PAYLOAD_MARKER, 1)[1].strip()
  try:
    payload, _ = json.JSONDecoder().raw_decode(text)
  except ValueError:
    return None
  return payload if isinstance(payload, dict) else None


def resolve_path(payload: Any, path: str) -> bool:
  path = path.strip().strip("`").strip()
  for prefix in _PREFIXES:
    if path.startswith(prefix):
      path = path[len(prefix):]
  path = path.split("=", 1)[0].split(" ", 1)[0].rstrip(".,;:")
  if not path:
    return False
  node = payload
  for name, index in _SEGMENT.findall(path):
    if name:
      if not isinstance(node, dict) or name not in node:
        return False
      node = node[name]
    else:
      i = int(index)
      if not isinstance(node, list) or i >= len(node):
        return False
      node = node[i]
  return True


def check_citations(parsed: ParsedConfirmation, *, prompt_version: str, user_prompt: str,
                    vision: bool) -> ParsedConfirmation:
  if prompt_version not in V5_PROMPT_VERSIONS or parsed.parse_status != "parsed":
    return parsed
  payload = prompt_payload(user_prompt)
  if payload is None:
    return parsed
  valid, missing = [], []
  for item in parsed.supporting_evidence:
    cleaned = str(item).strip().strip("`")
    if vision and cleaned.lower() in IMAGE_CITATIONS:
      valid.append(cleaned)
    elif resolve_path(payload, cleaned):
      valid.append(cleaned)
    else:
      missing.append(cleaned)
  report = {"valid": valid, "missing": missing, "downgraded": False}
  if parsed.decision == "violation" and not valid:
    report["downgraded"] = True
    return replace(parsed, decision="uncertain",
                   reason=f"[citation check: no cited evidence path exists in the payload] {parsed.reason}",
                   citation_check=report)
  return replace(parsed, citation_check=report)
