from __future__ import annotations

from src.crawler.crawl.priority.route_context import build_priority_route_context, state_route_value
from src.crawler.graph.graph import StateGraph


def test_build_priority_route_context_counts_routes_and_route_pairs():
  graph = StateGraph()
  graph.add_state("state_0000", "https://example.test/docs", "dom-a", "restore-a", "key-a", route="/docs")
  graph.add_state("state_0001", "https://example.test/docs/details", "dom-b", "restore-b", "key-b", route="/docs/details")
  graph.add_state("state_0002", "https://example.test/docs?tab=more", "dom-c", "restore-c", "key-c", route="/docs")
  graph.add_edge("state_0000", "state_0001", action={"text": "Details"})
  graph.add_edge("state_0001", "state_0002", action={"text": "Back"})

  context = build_priority_route_context(graph, "state_0001")

  assert context.current_route == "/docs/details"
  assert context.route_visit_counts == {
    "/docs": 2,
    "/docs/details": 1,
  }
  assert context.route_pair_counts == {
    ("/docs", "/docs/details"): 1,
    ("/docs/details", "/docs"): 1,
  }


def test_state_route_value_falls_back_to_url_path():
  graph = StateGraph()
  graph.add_state("state_0000", "https://example.test/settings?panel=profile", "dom-a", "restore-a", "key-a")

  assert state_route_value(graph, "state_0000") == "/settings"
  assert state_route_value(graph, "missing") == "/"
