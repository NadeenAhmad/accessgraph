"""Candidate payload construction helpers.

The functions in this module assemble offline candidate-generation records from
saved accessibility context. They do not perform crawler-time detection or LLM
judgment.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .models import (
  CANDIDATE_SCHEMA_VERSION,
  GENERATOR_NAME,
  GENERATOR_VERSION,
  RunArtifacts,
  RunState,
  sanitize_action,
)


def stable_candidate_id(
  *,
  run_id: str,
  state_id: str,
  candidate_type: str,
  element_ids: list[str],
) -> str:
  parts = [run_id, state_id, candidate_type, *sorted(str(item) for item in element_ids)]
  digest = hashlib.sha256("|".join(parts).encode("utf-8", errors="ignore")).hexdigest()[:12]
  return f"cand_{digest}"


def state_context_payload(state: RunState) -> dict[str, object]:
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  state_context = (
    state.accessibility_context.get("state_context")
    if isinstance(state.accessibility_context.get("state_context"), dict)
    else {}
  )
  return {
    "url": str(page.get("url") or state.metadata.get("url") or ""),
    "title": str(page.get("title") or state.metadata.get("title") or ""),
    "depth": int(state_context.get("depth") or state.metadata.get("depth") or 0),
    "parent_state": state_context.get("parent_state") or state.metadata.get("parent_state"),
    "action_from_parent": sanitize_action(
      state_context.get("action_from_parent") or state.metadata.get("action_from_parent")
    ),
  }


def artifact_refs(run_dir: Path, state: RunState) -> dict[str, str]:
  def rel(path: Path) -> str:
    try:
      return path.relative_to(run_dir).as_posix()
    except ValueError:
      return path.as_posix()

  return {
    "state_dir": rel(state.state_dir),
    "dom_html": rel(state.state_dir / "dom.html"),
    "screenshot": rel(state.state_dir / "screenshot.png"),
    "metadata": rel(state.state_dir / "metadata.json"),
    "accessibility_context": rel(state.accessibility_context_path),
  }


def generator_payload() -> dict[str, str]:
  return {
    "name": GENERATOR_NAME,
    "version": GENERATOR_VERSION,
  }


def build_candidate_payload(
  *,
  run: RunArtifacts,
  state: RunState,
  candidate_type: str,
  element_refs: list[dict[str, object]],
  selection_reason: list[str],
  required_context: list[str],
  evidence: dict[str, object],
  graph_context: dict[str, object],
  primary_element_ref: dict[str, object] | None = None,
) -> dict[str, object]:
  element_ids = [
    str(ref.get("element_id") or "")
    for ref in element_refs
    if str(ref.get("element_id") or "")
  ]
  return {
    "schema_version": CANDIDATE_SCHEMA_VERSION,
    "candidate_id": stable_candidate_id(
      run_id=run.run_id,
      state_id=state.state_id,
      candidate_type=candidate_type,
      element_ids=element_ids,
    ),
    "candidate_type": candidate_type,
    "state_id": state.state_id,
    "element_refs": element_refs,
    **({"primary_element_ref": primary_element_ref} if primary_element_ref else {}),
    "selection_reason": selection_reason,
    "required_context": required_context,
    "evidence": evidence,
    "state_context": state_context_payload(state),
    "graph_context": graph_context,
    "artifact_refs": artifact_refs(run.run_dir, state),
    "generator": generator_payload(),
  }
