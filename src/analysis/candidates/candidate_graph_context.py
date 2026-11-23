"""Build compact graph-derived context for semantic candidate records.

This module does not create or mutate the crawler graph. It reads the saved
graph/transitions artifacts for a completed run and derives a bounded context
excerpt that can travel with each candidate as the `graph_context` payload.
"""

from __future__ import annotations

from typing import Any

from .models import RunArtifacts, RunState, TRANSITION_PATH_LIMIT, sanitize_action


def build_candidate_graph_context(run: RunArtifacts, state: RunState) -> dict[str, object]:
  """Return the bounded graph/history context attached to one candidate."""
  nodes_by_state_id = _nodes_by_state_id(run.graph)
  parent_by_state_id = _parent_by_state_id(run, nodes_by_state_id)
  edges_by_state_pair = _edges_by_state_pair(run)

  full_transition_path = _transition_path_to_state(
    state_id=state.state_id,
    parent_by_state_id=parent_by_state_id,
    edges_by_state_pair=edges_by_state_pair,
  )
  truncated = len(full_transition_path) > TRANSITION_PATH_LIMIT
  transition_path = full_transition_path[-TRANSITION_PATH_LIMIT:] if truncated else full_transition_path

  return {
    "transition_path": transition_path,
    "transition_path_limit": TRANSITION_PATH_LIMIT,
    "transition_path_truncated": truncated,
    "incoming_action": _incoming_action_for_state(run, state, nodes_by_state_id),
    "related_state_refs": [],
  }


def _nodes_by_state_id(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
  raw_nodes = graph.get("nodes")
  if not isinstance(raw_nodes, list):
    return {}
  nodes: dict[str, dict[str, Any]] = {}
  for raw in raw_nodes:
    if not isinstance(raw, dict):
      continue
    state_id = str(raw.get("state_id") or "")
    if state_id:
      nodes[state_id] = raw
  return nodes


def _parent_by_state_id(run: RunArtifacts, nodes: dict[str, dict[str, Any]]) -> dict[str, str]:
  parents: dict[str, str] = {}
  for state in run.states:
    parent = str(state.metadata.get("parent_state") or "")
    if parent:
      parents[state.state_id] = parent
  for state_id, node in nodes.items():
    parent = str(node.get("parent_state_id") or "")
    if parent:
      parents[state_id] = parent
  return parents


def _edges_by_state_pair(run: RunArtifacts) -> dict[tuple[str, str], dict[str, Any]]:
  edges = run.transitions
  if not edges and isinstance(run.graph.get("edges"), list):
    edges = run.graph["edges"]
  by_pair: dict[tuple[str, str], dict[str, Any]] = {}
  for raw in edges:
    if not isinstance(raw, dict):
      continue
    src = str(raw.get("from") or "")
    dst = str(raw.get("to") or "")
    if src and dst:
      by_pair[(src, dst)] = raw
  return by_pair


def _transition_path_to_state(
  *,
  state_id: str,
  parent_by_state_id: dict[str, str],
  edges_by_state_pair: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, object]]:
  reversed_edges: list[dict[str, object]] = []
  current = state_id
  seen: set[str] = set()
  while current and current not in seen:
    seen.add(current)
    parent = parent_by_state_id.get(current)
    if not parent:
      break
    raw_edge = edges_by_state_pair.get((parent, current), {})
    reversed_edges.append(
      {
        "from": parent,
        "to": current,
        "action": sanitize_action(raw_edge.get("action") if isinstance(raw_edge, dict) else {}),
      }
    )
    current = parent
  return list(reversed(reversed_edges))


def _incoming_action_for_state(
  run: RunArtifacts,
  state: RunState,
  nodes: dict[str, dict[str, Any]],
) -> dict[str, object]:
  node = nodes.get(state.state_id, {})
  return sanitize_action(
    state.metadata.get("action_from_parent")
    or node.get("incoming_action")
    or state.accessibility_context.get("state_context", {}).get("action_from_parent")
  )


__all__ = ["build_candidate_graph_context"]
