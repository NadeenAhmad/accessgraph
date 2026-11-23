from __future__ import annotations

from src.crawler.crawl.actions import ActionCandidate
from src.crawler.crawl.crawl_config import CrawlConfig
from src.crawler.crawl.metrics.recorder import CrawlMetricsRecorder
from src.crawler.crawl.navigation.restore import ReplayRestoreResult
from src.crawler.graph.graph import StateGraph


def test_metrics_recorder_records_replay_and_selection_diagnostics():
  recorder = CrawlMetricsRecorder(CrawlConfig())
  result = ReplayRestoreResult(
    success=False,
    failure_reason="candidate_not_found",
    failure_stage="step",
    failed_step_index=2,
    path_length=3,
    same_url_soft_match=True,
  )

  recorder.record_replay_attempt_metrics(result)
  recorder.record_replay_failure(result)
  recorder.record_selection_diagnostics(
    ActionCandidate(
      locator=object(),
      action_type="click",
      strategy_name="buttons",
      text="Open details",
      in_main=True,
    ),
    priority_reason_flags=("main_control",),
  )

  coverage = recorder.metrics["coverage"]
  assert coverage["state_restore_replay_path_lengths"]["3"] == 1
  assert coverage["state_restore_replay_failures"] == 1
  assert coverage["state_restore_replay_failure_reasons"]["candidate_not_found"] == 1
  assert coverage["state_restore_replay_failure_stages"]["step"] == 1
  assert coverage["state_restore_replay_failure_step_indices"]["2"] == 1
  assert coverage["state_restore_replay_soft_matches"]["same_url"] == 1
  assert coverage["state_restore_replay_soft_matches"]["same_route"] == 0
  assert coverage["action_selection"]["by_strategy"]["buttons"] == 1
  assert coverage["action_selection"]["by_group"]["main_control"] == 1
  assert coverage["action_selection"]["by_region"]["main"] == 1
  assert coverage["action_selection"]["by_reason"]["main_control"] == 1


def test_metrics_recorder_finalizes_graph_totals_and_stop_status():
  recorder = CrawlMetricsRecorder(CrawlConfig())
  graph = StateGraph()
  graph.add_state("state_0000", "https://example.test/", "dom-a", "restore-a", "key-a")
  graph.add_state("state_0001", "https://example.test/next", "dom-b", "restore-b", "key-b")
  graph.add_edge("state_0000", "state_0001", action={"type": "click"})

  recorder.increment_coverage("new_states_discovered", 2)
  recorder.increment_coverage("actions_attempted", 1)
  recorder.increment_coverage("actions_succeeded", 1)
  recorder.increment_stop("states_expanded")
  recorder.record_stop_reason("no_candidates")
  recorder.finalize(graph)

  coverage = recorder.metrics["coverage"]
  stop = recorder.metrics["stop"]
  assert recorder.metrics["status"] == "success"
  assert coverage["states_total"] == 2
  assert coverage["edges_total"] == 1
  assert coverage["transition_success_rate"] == 1.0
  assert stop["states_expanded"] == 1
  assert stop["state_expansion_stop_reasons"]["no_candidates"] == 1
  assert stop["termination_reason"] == "frontier_exhausted"
  assert stop["frontier_exhausted"] is True
