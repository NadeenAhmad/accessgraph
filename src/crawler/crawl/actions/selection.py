from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any

from ...graph.graph import StateGraph
from .discovery import ActionCandidate
from ..crawl_config import CrawlConfig
from ..metrics.recorder import CrawlMetricsRecorder
from ..priority import (
  ActionKey,
  CandidatePriorityEvaluation,
  CandidateSelectionPolicy,
  _action_key,
  _build_priority_selection_policy,
  _candidate_scan_limit,
  _candidate_selection_group,
  _select_candidate,
  _sort_candidates_by_priority,
)
from ..priority.route_context import build_priority_route_context
from ..state_tracking.recorder import CrawlStateRecorder


class ActionSelectionPlanner:
  """Fetch and select crawler action candidates for a single crawl session."""

  def __init__(
    self,
    *,
    page: Page,
    start_url: str,
    cfg: CrawlConfig,
    graph_getter: Callable[[], StateGraph],
    in_scope: Callable[[str], bool],
    metrics_recorder: CrawlMetricsRecorder,
    state_recorder: CrawlStateRecorder,
    get_action_candidates_fn: Callable[..., Awaitable[list[ActionCandidate]]],
  ) -> None:
    self.page = page
    self.start_url = start_url
    self.cfg = cfg
    self._graph_getter = graph_getter
    self.in_scope = in_scope
    self.metrics_recorder = metrics_recorder
    self.state_recorder = state_recorder
    self.get_action_candidates = get_action_candidates_fn

  @property
  def graph(self) -> StateGraph:
    return self._graph_getter()

  async def get_candidates(self) -> list[ActionCandidate]:
    candidates = await self.get_action_candidates(self.page, limit=_candidate_scan_limit(self.cfg))
    self.metrics_recorder.increment_coverage("candidate_scans")
    self.metrics_recorder.increment_coverage("candidates_seen_total", len(candidates))

    if self.cfg.prioritize_action_candidates:
      return _sort_candidates_by_priority(
        candidates,
        page_url=self.page.url,
        start_url=self.start_url,
        in_scope=self.in_scope,
      )
    return candidates

  def record_previously_attempted_candidates(
    self,
    candidates: list[ActionCandidate],
    persisted_attempted_action_keys: set[ActionKey],
    counted_previously_attempted_keys: set[ActionKey],
  ) -> None:
    previously_attempted_keys = {
      _action_key(candidate)
      for candidate in candidates
      if _action_key(candidate) in persisted_attempted_action_keys
    }
    new_previously_attempted_keys = previously_attempted_keys - counted_previously_attempted_keys
    if not new_previously_attempted_keys:
      return

    self.metrics_recorder.increment_coverage("actions_skipped_previously_attempted", len(new_previously_attempted_keys))
    counted_previously_attempted_keys.update(new_previously_attempted_keys)

  def selection_policy_for_state(
    self,
    *,
    current_state_id: str,
    candidates: list[ActionCandidate],
    attempted_group_counts: dict[str, int],
    attempted_strategy_counts: dict[str, int],
  ) -> CandidateSelectionPolicy | None:
    if not self.cfg.prioritize_action_candidates:
      return None

    route_context = build_priority_route_context(self.graph, current_state_id)
    return _build_priority_selection_policy(
      candidates,
      page_url=self.page.url,
      start_url=self.start_url,
      in_scope=self.in_scope,
      current_route=route_context.current_route,
      attempted_group_counts=attempted_group_counts,
      attempted_strategy_counts=attempted_strategy_counts,
      route_visit_counts=route_context.route_visit_counts,
      route_pair_counts=route_context.route_pair_counts,
    )

  def select_candidate_for_state(
    self,
    *,
    candidates: list[ActionCandidate],
    attempted_action_keys: set[ActionKey],
    selection_policy: CandidateSelectionPolicy | None,
  ) -> tuple[int, ActionCandidate, ActionKey, CandidatePriorityEvaluation | None] | None:
    return _select_candidate(
      candidates,
      attempted_action_keys,
      evaluator=selection_policy.evaluator if selection_policy is not None else None,
      reserve_route_link=selection_policy.reserve_route_link if selection_policy is not None else False,
      route_link_predicate=selection_policy.route_link_predicate if selection_policy is not None else None,
    )

  def record_action_attempt(
    self,
    *,
    current_state_id: str,
    selected_candidate: ActionCandidate,
    selected_key: ActionKey,
    attempted_action_keys: set[ActionKey],
    attempted_group_counts: dict[str, int],
    attempted_strategy_counts: dict[str, int],
    priority_evaluation: CandidatePriorityEvaluation | None,
    priority_reason_flags: tuple[str, ...],
  ) -> None:
    attempted_action_keys.add(selected_key)
    self.state_recorder.record_attempted_action(current_state_id, selected_key)
    if self.cfg.prioritize_action_candidates:
      group = priority_evaluation.group if priority_evaluation is not None else _candidate_selection_group(selected_candidate)
      attempted_group_counts[group] = attempted_group_counts.get(group, 0) + 1
      attempted_strategy_counts[selected_candidate.strategy_name] = (
        attempted_strategy_counts.get(selected_candidate.strategy_name, 0) + 1
      )
    self.metrics_recorder.record_selection_diagnostics(
      selected_candidate,
      priority_evaluation=priority_evaluation,
      priority_reason_flags=priority_reason_flags,
    )
    self.metrics_recorder.increment_coverage("actions_attempted")
