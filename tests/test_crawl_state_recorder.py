from __future__ import annotations

from types import SimpleNamespace

from src.crawler.crawl.crawl_config import CrawlConfig
from src.crawler.crawl.metrics.recorder import CrawlMetricsRecorder
from src.crawler.crawl.state_tracking.recorder import CrawlStateRecorder
from src.crawler.crawl.state_tracking.registry import StateRegistry
from src.crawler.graph.graph import StateGraph
from src.crawler.state.hashing import state_dedup_key


def _recorder(
  *,
  graph_ref: dict[str, StateGraph],
  registry: StateRegistry | None = None,
  metrics: CrawlMetricsRecorder | None = None,
  capture_state_artifacts_fn=None,
) -> CrawlStateRecorder:
  async def default_capture_state_artifacts(_page, _run_dir, *, state_id, **_kwargs):
    return SimpleNamespace(
      url=f"https://example.test/{state_id}",
      html_hash=f"html-{state_id}",
      dom_identity_hash=f"identity-{state_id}",
      title=state_id,
      route=f"/{state_id}",
    )

  return CrawlStateRecorder(
    page=object(),  # type: ignore[arg-type]
    run_dir=object(),  # type: ignore[arg-type]
    cfg=CrawlConfig(),
    graph_getter=lambda: graph_ref["graph"],
    state_registry=registry or StateRegistry(),
    metrics_recorder=metrics or CrawlMetricsRecorder(CrawlConfig()),
    capture_state_artifacts_fn=capture_state_artifacts_fn or default_capture_state_artifacts,
  )


def test_save_state_registers_graph_metadata_and_dedupe_key():
  graph_ref = {"graph": StateGraph()}
  registry = StateRegistry()
  metrics = CrawlMetricsRecorder(CrawlConfig())
  recorder = _recorder(graph_ref=graph_ref, registry=registry, metrics=metrics)

  import asyncio

  key = asyncio.run(
    recorder.save_state(
      "state_0000",
      depth=0,
      parent_state=None,
      action_from_parent=None,
      active_root_state_id="state_0000",
    )
  )

  expected_key = state_dedup_key(
    dom_identity_hash="identity-state_0000",
    url="https://example.test/state_0000",
  )
  assert key == expected_key
  node = graph_ref["graph"].nodes["state_0000"]
  assert node["html_hash"] == "html-state_0000"
  assert node["dom_identity_hash"] == "identity-state_0000"
  assert "dom_hash" not in node
  assert "restore_hash" not in node
  assert registry.state_for_key(expected_key) == "state_0000"
  assert registry.attempted_actions_for_state("state_0000") == set()
  assert graph_ref["graph"].nodes["state_0000"]["seed_root_state_id"] == "state_0000"
  assert graph_ref["graph"].nodes["state_0000"]["imported"] is False
  assert graph_ref["graph"].nodes["state_0000"]["attempted_action_keys"] == []
  assert metrics.coverage["new_states_discovered"] == 1


def test_record_attempted_action_serializes_unique_action_keys():
  graph_ref = {"graph": StateGraph()}
  recorder = _recorder(graph_ref=graph_ref)
  graph_ref["graph"].add_state("state_0000", "https://example.test/", "dom", "restore", "key")

  recorder.record_attempted_action("state_0000", ("click", "button", "Save"))
  recorder.record_attempted_action("state_0000", ("click", "button", "Save"))

  assert graph_ref["graph"].nodes["state_0000"]["attempted_action_keys"] == [["click", "button", "Save"]]


def test_record_action_transition_updates_edge_parent_seed_and_metrics():
  graph_ref = {"graph": StateGraph()}
  metrics = CrawlMetricsRecorder(CrawlConfig())
  recorder = _recorder(graph_ref=graph_ref, metrics=metrics)
  graph_ref["graph"].add_state("state_0000", "https://example.test/", "dom-a", "restore-a", "key-a")
  graph_ref["graph"].nodes["state_0000"]["seed_root_state_id"] = "state_0000"
  graph_ref["graph"].add_state("state_0001", "https://example.test/next", "dom-b", "restore-b", "key-b")

  transition_id = recorder.record_action_transition(
    current_state_id="state_0000",
    next_state_id="state_0001",
    action_meta={"text": "Next"},
    discovered_new_state=True,
  )

  assert transition_id == "transition_0000"
  assert graph_ref["graph"].edges == [
    {"from": "state_0000", "to": "state_0001", "action": {"text": "Next"}}
  ]
  assert graph_ref["graph"].nodes["state_0001"]["parent_state_id"] == "state_0000"
  assert graph_ref["graph"].nodes["state_0001"]["incoming_action"] == {"text": "Next"}
  assert graph_ref["graph"].nodes["state_0001"]["seed_root_state_id"] == "state_0000"
  assert metrics.coverage["actions_succeeded"] == 1


def test_recorder_uses_current_graph_from_getter_after_graph_swap():
  initial_graph = StateGraph()
  updated_graph = StateGraph()
  updated_graph.add_state("state_0000", "https://example.test/", "dom", "restore", "key")
  graph_ref = {"graph": initial_graph}
  recorder = _recorder(graph_ref=graph_ref)

  graph_ref["graph"] = updated_graph
  recorder.set_state_metadata("state_0000", imported=True)

  assert "state_0000" not in initial_graph.nodes
  assert updated_graph.nodes["state_0000"]["imported"] is True
