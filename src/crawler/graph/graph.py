from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GraphNode = dict[str, Any]
GraphEdge = dict[str, Any]


def state_node_html_hash(node: GraphNode) -> str:
  """Return serialized-HTML hash, accepting legacy graph node field names."""
  value = node.get("html_hash")
  if isinstance(value, str) and value:
    return value
  legacy_value = node.get("dom_hash")
  return legacy_value if isinstance(legacy_value, str) else ""


def state_node_dom_identity_hash(node: GraphNode) -> str:
  """Return rendered-DOM identity hash, accepting legacy graph node field names."""
  value = node.get("dom_identity_hash")
  if isinstance(value, str) and value:
    return value
  legacy_value = node.get("restore_hash")
  if isinstance(legacy_value, str) and legacy_value:
    return legacy_value
  return state_node_html_hash(node)


@dataclass
class StateGraph:
  """In-memory representation of discovered crawl states and transitions."""

  nodes: dict[str, GraphNode] = field(default_factory=dict)
  edges: list[GraphEdge] = field(default_factory=list)
  metrics: dict[str, Any] = field(default_factory=dict)

  def add_state(
    self,
    state_id: str,
    url: str,
    html_hash: str,
    dom_identity_hash: str = "",
    stable_state_key: str = "",
    title: str = "",
    route: str = "",
  ) -> None:
    """Add a state node once; duplicate state IDs keep their original metadata."""
    if state_id in self.nodes:
      return

    self.nodes[state_id] = {
      "state_id": state_id,
      "url": url,
      "route": route,
      "title": title,
      "html_hash": html_hash,
      "dom_identity_hash": dom_identity_hash,
      "stable_state_key": stable_state_key,
      "parent_state_id": None,
      "incoming_action": None,
    }

  def set_state_parent(self, state_id: str, parent_state_id: str, incoming_action: GraphEdge | None = None) -> None:
    """Record the first-discovery tree parent without replacing an existing parent."""
    node = self.nodes.get(state_id)
    if not node:
      return
    if node.get("parent_state_id") is not None:
      return
    node["parent_state_id"] = parent_state_id
    node["incoming_action"] = incoming_action or {}

  def add_edge(self, src: str, dst: str, action: GraphEdge | None = None) -> None:
    """Record an observed transition; edges are the transition source of truth."""
    self.edges.append(
      {
        "from": src,
        "to": dst,
        "action": action or {},
      }
    )

  def to_dict(self) -> dict[str, Any]:
    state_ids = list(self.nodes)
    payload: dict[str, Any] = {
      "start_state": state_ids[0] if state_ids else None,
      "states": state_ids,
      "nodes": list(self.nodes.values()),
      "edges": self.edges,
    }
    if self.metrics:
      payload["metrics"] = self.metrics
    return payload

  def save_json(self, path: Path) -> None:
    path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

  def save_transitions_json(self, path: Path) -> None:
    path.write_text(json.dumps(self.edges, ensure_ascii=False, indent=2), encoding="utf-8")
