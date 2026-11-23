"""Load completed crawl artifacts for offline candidate generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.crawler.evidence.accessibility_context_schema import ACCESSIBILITY_CONTEXT_SCHEMA_VERSION

from .models import RunArtifacts, RunState


def load_run_artifacts(run_dir: Path) -> RunArtifacts:
  run_dir = run_dir.resolve()
  if not run_dir.exists() or not run_dir.is_dir():
    raise FileNotFoundError(f"Run directory does not exist: {run_dir}")

  graph = _load_json(run_dir / "graph.json", default={})
  transitions = _load_json(run_dir / "transitions.json", default=[])
  if not isinstance(graph, dict):
    graph = {}
  if not isinstance(transitions, list):
    transitions = []

  states: list[RunState] = []
  missing_accessibility_context = 0
  unsupported_schema_version = 0
  states_dir = run_dir / "states"
  state_dirs = sorted(path for path in states_dir.glob("state_*") if path.is_dir()) if states_dir.exists() else []
  for state_dir in state_dirs:
    metadata = _load_json(state_dir / "metadata.json", default={})
    if not isinstance(metadata, dict):
      metadata = {}
    accessibility_context_path = _accessibility_context_path(state_dir)
    if accessibility_context_path is None:
      missing_accessibility_context += 1
      continue
    accessibility_context = _load_json(accessibility_context_path, default={})
    if not isinstance(accessibility_context, dict):
      unsupported_schema_version += 1
      continue
    if accessibility_context.get("schema_version") != ACCESSIBILITY_CONTEXT_SCHEMA_VERSION:
      unsupported_schema_version += 1
      continue
    states.append(
      RunState(
        state_id=str(metadata.get("state_id") or accessibility_context.get("state_id") or state_dir.name),
        state_dir=state_dir,
        metadata=metadata,
        accessibility_context=accessibility_context,
        accessibility_context_path=accessibility_context_path,
      )
    )

  return RunArtifacts(
    run_dir=run_dir,
    run_id=run_dir.name,
    graph=graph,
    transitions=transitions,
    states=tuple(states),
    missing_accessibility_context=missing_accessibility_context,
    unsupported_schema_version=unsupported_schema_version,
  )


def _load_json(path: Path, *, default: Any) -> Any:
  try:
    return json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    return default


def _accessibility_context_path(state_dir: Path) -> Path | None:
  for name in (
    "accessibility_context.json",
    "neutral_evidence.json",
    "semantic_elements.json",
  ):
    path = state_dir / name
    if path.exists():
      return path
  return None
