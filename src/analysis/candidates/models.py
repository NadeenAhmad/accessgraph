"""Shared candidate-generation data models and contract constants."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

CANDIDATE_SCHEMA_VERSION = "1"
GENERATOR_NAME = "offline_semantic_candidate_builder"
GENERATOR_VERSION = "1"
MAX_SNIPPET_LENGTH = 500
TRANSITION_PATH_LIMIT = 5

FORBIDDEN_CANDIDATE_KEYS: tuple[str, ...] = (
  "violation",
  "severity",
  "confidence",
  "wcag_result",
  "llm_judgment",
  "precheck",
)

JUDGMENTAL_SELECTION_WORDS: tuple[str, ...] = (
  "bad",
  "unclear",
  "generic",
  "incorrect",
  "mismatch",
)

ALLOWED_ACTION_KEYS: tuple[str, ...] = (
  "type",
  "selector",
  "text",
  "href",
  "input_type",
  "index",
)


@dataclass(frozen=True)
class RunState:
  state_id: str
  state_dir: Path
  metadata: dict[str, Any]
  accessibility_context: dict[str, Any]
  accessibility_context_path: Path


@dataclass(frozen=True)
class RunArtifacts:
  run_dir: Path
  run_id: str
  graph: dict[str, Any]
  transitions: list[dict[str, Any]]
  states: tuple[RunState, ...]
  missing_accessibility_context: int = 0
  unsupported_schema_version: int = 0


def sanitize_action(raw: object) -> dict[str, object]:
  if not isinstance(raw, dict):
    return {}
  sanitized: dict[str, object] = {}
  for key in ALLOWED_ACTION_KEYS:
    if key in raw and raw[key] not in (None, ""):
      sanitized[key] = raw[key]
  return sanitized
