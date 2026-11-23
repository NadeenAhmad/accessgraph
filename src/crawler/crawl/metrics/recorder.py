from __future__ import annotations

import time
from typing import TYPE_CHECKING, Sequence

from ...graph.graph import StateGraph
from ..actions import ActionCandidate
from .schema import (
  _coverage,
  _finalize_metrics,
  _increment_counter,
  _init_metrics,
  _replay_failure_reason_metrics,
  _replay_failure_stage_metrics,
  _replay_failure_step_metrics,
  _replay_path_length_metrics,
  _replay_soft_match_metrics,
  _selection_metrics,
  _state_stop_reasons,
  _stop,
)
from ..priority import CandidatePriorityEvaluation, _candidate_region, _candidate_selection_group

if TYPE_CHECKING:
  from ..crawl_config import CrawlConfig
  from ..navigation.restore import ReplayRestoreResult


class CrawlMetricsRecorder:
  """Own crawl metrics counters without changing crawl control flow."""

  def __init__(self, cfg: CrawlConfig) -> None:
    self.crawl_started = time.perf_counter()
    self.metrics = _init_metrics(cfg)
    self.coverage = _coverage(self.metrics)
    self.stop = _stop(self.metrics)
    self.stop_reasons = _state_stop_reasons(self.stop)

  def increment_coverage(self, key: str, amount: int = 1) -> None:
    # Counters outside the base schema (exploration, storage resets) appear only once used.
    self.coverage[key] = int(self.coverage.get(key, 0)) + amount

  def increment_stop(self, key: str, amount: int = 1) -> None:
    self.stop[key] = int(self.stop[key]) + amount

  def record_stop_reason(self, reason: str) -> None:
    self.stop_reasons[reason] = int(self.stop_reasons[reason]) + 1

  def record_replay_attempt_metrics(self, result: ReplayRestoreResult) -> None:
    path_lengths = _replay_path_length_metrics(self.coverage)
    _increment_counter(path_lengths, str(result.path_length))

  def record_replay_failure(self, result: ReplayRestoreResult) -> None:
    self.increment_coverage("state_restore_replay_failures")
    if result.failure_reason is not None:
      reasons = _replay_failure_reason_metrics(self.coverage)
      reasons[result.failure_reason] = int(reasons.get(result.failure_reason, 0)) + 1
    if result.failure_stage is not None:
      stages = _replay_failure_stage_metrics(self.coverage)
      stages[result.failure_stage] = int(stages.get(result.failure_stage, 0)) + 1
    if result.failed_step_index is not None:
      steps = _replay_failure_step_metrics(self.coverage)
      _increment_counter(steps, str(result.failed_step_index))
    soft_matches = _replay_soft_match_metrics(self.coverage)
    if result.same_url_soft_match:
      soft_matches["same_url"] = int(soft_matches.get("same_url", 0)) + 1
    if result.same_route_soft_match:
      soft_matches["same_route"] = int(soft_matches.get("same_route", 0)) + 1

  def record_selection_diagnostics(
    self,
    candidate: ActionCandidate,
    *,
    priority_evaluation: CandidatePriorityEvaluation | None = None,
    priority_reason_flags: Sequence[str] = (),
  ) -> None:
    selection = _selection_metrics(self.coverage)
    by_strategy = selection.get("by_strategy")
    by_group = selection.get("by_group")
    by_region = selection.get("by_region")
    by_reason = selection.get("by_reason")
    if not isinstance(by_strategy, dict) or not isinstance(by_group, dict) or not isinstance(by_region, dict) or not isinstance(by_reason, dict):
      raise ValueError("Invalid selection metrics buckets")

    group = priority_evaluation.group if priority_evaluation is not None else _candidate_selection_group(candidate)
    region = priority_evaluation.region if priority_evaluation is not None else _candidate_region(candidate)
    _increment_counter(by_strategy, candidate.strategy_name)
    _increment_counter(by_group, group)
    _increment_counter(by_region, region)
    for reason in priority_reason_flags:
      _increment_counter(by_reason, str(reason))

  def finalize(self, graph: StateGraph) -> None:
    _finalize_metrics(self.metrics, graph, self.crawl_started)
