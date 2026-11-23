from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from ...graph.graph import StateGraph


@dataclass(frozen=True)
class PriorityRouteContext:
  current_route: str
  route_visit_counts: dict[str, int]
  route_pair_counts: dict[tuple[str, str], int]


def build_priority_route_context(graph: StateGraph, current_state_id: str) -> PriorityRouteContext:
  route_visit_counts: dict[str, int] = {}
  for node in graph.nodes.values():
    route = _state_route_value_from_node(node)
    route_visit_counts[route] = route_visit_counts.get(route, 0) + 1

  route_pair_counts: dict[tuple[str, str], int] = {}
  for edge in graph.edges:
    src_state_id = str(edge.get("from") or "")
    dst_state_id = str(edge.get("to") or "")
    if not src_state_id or not dst_state_id:
      continue
    pair = (
      state_route_value(graph, src_state_id),
      state_route_value(graph, dst_state_id),
    )
    route_pair_counts[pair] = route_pair_counts.get(pair, 0) + 1

  return PriorityRouteContext(
    current_route=state_route_value(graph, current_state_id),
    route_visit_counts=route_visit_counts,
    route_pair_counts=route_pair_counts,
  )


def state_route_value(graph: StateGraph, state_id: str) -> str:
  node = graph.nodes.get(state_id, {})
  if not isinstance(node, dict):
    return "/"
  return _state_route_value_from_node(node)


def _state_route_value_from_node(node: dict[str, object]) -> str:
  route = str(node.get("route") or "")
  if route:
    return route
  return urlparse(str(node.get("url") or "")).path or "/"
