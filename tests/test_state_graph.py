import json

from src.crawler.graph.graph import StateGraph, state_node_dom_identity_hash, state_node_html_hash


def test_add_state_records_expected_node_shape():
  graph = StateGraph()

  graph.add_state(
    "state_0000",
    "https://example.test/app",
    "html-hash",
    "dom-identity-hash",
    "stable-key",
    "Example App",
    "/app",
  )

  assert graph.nodes["state_0000"] == {
    "state_id": "state_0000",
    "url": "https://example.test/app",
    "route": "/app",
    "title": "Example App",
    "html_hash": "html-hash",
    "dom_identity_hash": "dom-identity-hash",
    "stable_state_key": "stable-key",
    "parent_state_id": None,
    "incoming_action": None,
  }


def test_add_state_does_not_overwrite_duplicate_state_id():
  graph = StateGraph()

  graph.add_state("state_0000", "https://example.test/one", "first-hash")
  graph.add_state("state_0000", "https://example.test/two", "second-hash")

  assert graph.nodes["state_0000"]["url"] == "https://example.test/one"
  assert graph.nodes["state_0000"]["html_hash"] == "first-hash"


def test_state_node_hash_helpers_tolerate_legacy_field_names():
  legacy_node = {
    "dom_hash": "legacy-html-hash",
    "restore_hash": "legacy-dom-identity-hash",
  }

  assert state_node_html_hash(legacy_node) == "legacy-html-hash"
  assert state_node_dom_identity_hash(legacy_node) == "legacy-dom-identity-hash"


def test_state_node_dom_identity_hash_falls_back_to_html_hash():
  node = {"html_hash": "html-only-hash"}

  assert state_node_dom_identity_hash(node) == "html-only-hash"


def test_set_state_parent_records_first_parent_and_incoming_action():
  graph = StateGraph()
  action = {"type": "click", "text": "Open details"}

  graph.add_state("state_0000", "https://example.test", "root-hash")
  graph.add_state("state_0001", "https://example.test/details", "details-hash")
  graph.set_state_parent("state_0001", "state_0000", action)

  assert graph.nodes["state_0001"]["parent_state_id"] == "state_0000"
  assert graph.nodes["state_0001"]["incoming_action"] == action


def test_set_state_parent_keeps_first_parent():
  graph = StateGraph()

  graph.add_state("state_0000", "https://example.test", "root-hash")
  graph.add_state("state_0001", "https://example.test/details", "details-hash")
  graph.add_state("state_0002", "https://example.test/alternate", "alternate-hash")
  graph.set_state_parent("state_0001", "state_0000", {"text": "first"})
  graph.set_state_parent("state_0001", "state_0002", {"text": "second"})

  assert graph.nodes["state_0001"]["parent_state_id"] == "state_0000"
  assert graph.nodes["state_0001"]["incoming_action"] == {"text": "first"}


def test_set_state_parent_ignores_missing_state():
  graph = StateGraph()

  graph.set_state_parent("missing", "state_0000", {"text": "ignored"})

  assert graph.nodes == {}


def test_add_edge_preserves_transition_action_metadata():
  graph = StateGraph()
  action = {"type": "click", "strategy": "role_button", "text": "Next"}

  graph.add_edge("state_0000", "state_0001", action)

  assert graph.edges == [
    {
      "from": "state_0000",
      "to": "state_0001",
      "action": action,
    }
  ]


def test_to_dict_uses_insertion_order_for_start_state_and_omits_empty_metrics():
  graph = StateGraph()
  graph.add_state("state_0000", "https://example.test", "root-hash")
  graph.add_state("state_0001", "https://example.test/details", "details-hash")
  graph.add_edge("state_0000", "state_0001", {"text": "Details"})

  payload = graph.to_dict()

  assert payload["start_state"] == "state_0000"
  assert payload["states"] == ["state_0000", "state_0001"]
  assert payload["nodes"] == list(graph.nodes.values())
  assert payload["edges"] == graph.edges
  assert "metrics" not in payload


def test_to_dict_includes_metrics_when_present():
  graph = StateGraph(metrics={"status": "success"})

  assert graph.to_dict()["metrics"] == {"status": "success"}


def test_save_json_writes_full_graph_payload(tmp_path):
  graph = StateGraph(metrics={"states_total": 1})
  graph.add_state("state_0000", "https://example.test", "root-hash")
  path = tmp_path / "graph.json"

  graph.save_json(path)

  assert json.loads(path.read_text(encoding="utf-8")) == graph.to_dict()


def test_save_transitions_json_writes_only_edges(tmp_path):
  graph = StateGraph()
  graph.add_edge("state_0000", "state_0001", {"text": "Open"})
  path = tmp_path / "transitions.json"

  graph.save_transitions_json(path)

  assert json.loads(path.read_text(encoding="utf-8")) == graph.edges
