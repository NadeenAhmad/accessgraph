"""Canonical semantic taxonomy exposure for AccessGraph candidate generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SEMANTIC_CATEGORY = "semantic"
SYNTAX_CATEGORY = "syntax"
LAYOUT_CATEGORY = "layout"

TAXONOMY_PATH = Path(__file__).resolve().parents[3] / "SEMANTIC_VIOLATION_TAXONOMY.json"


def load_semantic_taxonomy_entries(path: Path = TAXONOMY_PATH) -> tuple[dict[str, Any], ...]:
  raw = json.loads(path.read_text(encoding="utf-8-sig"))
  if not isinstance(raw, list):
    raise ValueError(f"Semantic taxonomy must be a JSON list: {path}")

  entries: list[dict[str, Any]] = []
  seen: set[str] = set()
  for index, entry in enumerate(raw):
    if not isinstance(entry, dict):
      raise ValueError(f"Semantic taxonomy entry {index} must be an object: {path}")
    candidate_type = normalize_candidate_type(str(entry.get("violation_name") or ""))
    if not candidate_type:
      raise ValueError(f"Semantic taxonomy entry {index} is missing violation_name: {path}")
    if candidate_type in seen:
      raise ValueError(f"Duplicate semantic taxonomy type {candidate_type!r}: {path}")
    seen.add(candidate_type)
    entries.append({**entry, "violation_name": candidate_type})
  return tuple(entries)


def normalize_candidate_type(value: str) -> str:
  return str(value or "").strip().lower().replace("_", "-")


SEMANTIC_TAXONOMY_ENTRIES: tuple[dict[str, Any], ...] = load_semantic_taxonomy_entries()
ALL_SEMANTIC_TYPES: tuple[str, ...] = tuple(
  str(entry["violation_name"])
  for entry in SEMANTIC_TAXONOMY_ENTRIES
)

TEMPORARY_LEGACY_IMPLEMENTATION_TYPES: tuple[str, ...] = ()
UNSUPPORTED_CURRENT_PIPELINE_TYPES: tuple[str, ...] = ()
CURRENT_REUSABLE_CANDIDATE_TYPES: tuple[str, ...] = tuple(
  candidate_type
  for candidate_type in ALL_SEMANTIC_TYPES
  if candidate_type not in UNSUPPORTED_CURRENT_PIPELINE_TYPES
)
SUPPORTED_CANDIDATE_TYPES: tuple[str, ...] = CURRENT_REUSABLE_CANDIDATE_TYPES

OUT_OF_SCOPE_CURRENT_SEMANTIC_TYPES: tuple[str, ...] = ()

REMOVED_OLD_SEMANTIC_TYPES: tuple[str, ...] = (
  "video-captions-not-descriptive",
  "missing-lang-tag",
  "landmark-structural-violation",
  "label-name-mismatch",
  "incorrect-semantic-tag",
  "ambiguous-heading",
)

EXCLUDED_SYNTAX_TYPES: tuple[str, ...] = (
  "image-alt",
  "button-name",
  "link-name",
  "label",
  "autocomplete-valid",
  "document-title",
  "meta-viewport",
  "tabindex",
  "html-has-lang",
  "valid-lang",
  "missing-lang-tag",
)

EXCLUDED_LAYOUT_TYPES: tuple[str, ...] = (
  "color-contrast",
)


def is_semantic_taxonomy_type(value: str) -> bool:
  return normalize_candidate_type(value) in ALL_SEMANTIC_TYPES


def is_supported_candidate_type(value: str) -> bool:
  return normalize_candidate_type(value) in SUPPORTED_CANDIDATE_TYPES


def is_temporary_legacy_implementation_type(value: str) -> bool:
  return normalize_candidate_type(value) in TEMPORARY_LEGACY_IMPLEMENTATION_TYPES


def is_excluded_taxonomy_type(value: str) -> bool:
  normalized = normalize_candidate_type(value)
  return (
    normalized in EXCLUDED_SYNTAX_TYPES
    or normalized in EXCLUDED_LAYOUT_TYPES
    or normalized in OUT_OF_SCOPE_CURRENT_SEMANTIC_TYPES
    or normalized in REMOVED_OLD_SEMANTIC_TYPES
  )


def require_supported_candidate_type(value: str) -> str:
  normalized = normalize_candidate_type(value)
  if normalized not in SUPPORTED_CANDIDATE_TYPES:
    raise ValueError(f"Unsupported semantic candidate type: {value}")
  return normalized
