from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ...graph.graph import StateGraph

if TYPE_CHECKING:
  from ..crawl_config import CrawlConfig


def _utc_iso_now() -> str:
  return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _init_metrics(cfg: CrawlConfig) -> dict[str, object]:
  return {
    "status": "running",
    "started_at_utc": _utc_iso_now(),
    "coverage": {
      "candidate_scans": 0,
      "candidates_seen_total": 0,
      "actions_attempted": 0,
      "actions_succeeded": 0,
      "actions_failed": 0,
      "action_timeouts": 0,
      "actions_no_state_change": 0,
      "actions_skipped_previously_attempted": 0,
      "actions_skipped_out_of_scope_pre": 0,
      "actions_skipped_out_of_scope_post": 0,
      "new_states_discovered": 0,
      "existing_state_hits": 0,
      "state_restore_replay_attempts": 0,
      "state_restore_replay_first_attempts": 0,
      "state_restore_replay_successes": 0,
      "state_restore_replay_stable_successes": 0,
      "state_restore_replay_failures": 0,
      "state_restore_replay_failure_reasons": {
        "path_missing": 0,
        "root_navigation_failed": 0,
        "candidate_not_found": 0,
        "action_timeout": 0,
        "action_failed": 0,
        "out_of_scope": 0,
        "final_state_mismatch": 0,
      },
      "state_restore_replay_failure_stages": {
        "pre_replay": 0,
        "step": 0,
        "final_verification": 0,
      },
      "state_restore_replay_failure_step_indices": {},
      "state_restore_replay_path_lengths": {},
      "state_restore_replay_soft_matches": {
        "same_url": 0,
        "same_route": 0,
      },
      "state_restore_url_attempts": 0,
      "state_restore_url_first_attempts": 0,
      "state_restore_url_successes": 0,
      "state_restore_url_stable_successes": 0,
      "state_restore_url_failures": 0,
      "state_restore_url_fallbacks": 0,
      "states_total": 0,
      "edges_total": 0,
      "duration_seconds": 0.0,
      "new_states_per_minute": 0.0,
      "transition_success_rate": 0.0,
      "action_selection": {
        "by_strategy": {},
        "by_group": {},
        "by_region": {},
        "by_reason": {},
      },
    },
    "stop": {
      "traversal_strategy": cfg.traversal_strategy,
      "max_states": cfg.max_states,
      "max_depth": cfg.max_depth,
      "max_actions_per_state": cfg.max_actions_per_state,
      "wait_timeout_ms": cfg.wait_timeout_ms,
      "states_expanded": 0,
      "states_at_max_depth": 0,
      "states_at_max_states": 0,
      "state_expansion_stop_reasons": {
        "depth_limit": 0,
        "max_states": 0,
        "no_candidates": 0,
        "action_budget_exhausted": 0,
        "restore_failed": 0,
      },
      "termination_reason": "running",
      "frontier_exhausted": False,
    },
  }


def _coverage(metrics: dict[str, object]) -> dict[str, object]:
  raw = metrics.get("coverage")
  if not isinstance(raw, dict):
    raise ValueError("Invalid metrics coverage structure")
  return raw


def _stop(metrics: dict[str, object]) -> dict[str, object]:
  raw = metrics.get("stop")
  if not isinstance(raw, dict):
    raise ValueError("Invalid metrics stop structure")
  return raw


def _state_stop_reasons(stop_metrics: dict[str, object]) -> dict[str, int]:
  raw = stop_metrics.get("state_expansion_stop_reasons")
  if not isinstance(raw, dict):
    raise ValueError("Invalid state expansion stop reason structure")
  return raw


def _selection_metrics(coverage_metrics: dict[str, object]) -> dict[str, dict[str, int]]:
  raw = coverage_metrics.get("action_selection")
  if not isinstance(raw, dict):
    raise ValueError("Invalid action selection metrics structure")
  return raw  # type: ignore[return-value]


def _replay_failure_reason_metrics(coverage_metrics: dict[str, object]) -> dict[str, int]:
  raw = coverage_metrics.get("state_restore_replay_failure_reasons")
  if not isinstance(raw, dict):
    raise ValueError("Invalid replay failure reason metrics structure")
  return raw


def _replay_failure_stage_metrics(coverage_metrics: dict[str, object]) -> dict[str, int]:
  raw = coverage_metrics.get("state_restore_replay_failure_stages")
  if not isinstance(raw, dict):
    raise ValueError("Invalid replay failure stage metrics structure")
  return raw


def _replay_failure_step_metrics(coverage_metrics: dict[str, object]) -> dict[str, int]:
  raw = coverage_metrics.get("state_restore_replay_failure_step_indices")
  if not isinstance(raw, dict):
    raise ValueError("Invalid replay failure step metrics structure")
  return raw


def _replay_path_length_metrics(coverage_metrics: dict[str, object]) -> dict[str, int]:
  raw = coverage_metrics.get("state_restore_replay_path_lengths")
  if not isinstance(raw, dict):
    raise ValueError("Invalid replay path length metrics structure")
  return raw


def _replay_soft_match_metrics(coverage_metrics: dict[str, object]) -> dict[str, int]:
  raw = coverage_metrics.get("state_restore_replay_soft_matches")
  if not isinstance(raw, dict):
    raise ValueError("Invalid replay soft match metrics structure")
  return raw


def _increment_counter(bucket: dict[str, int], key: str) -> None:
  bucket[key] = int(bucket.get(key, 0)) + 1


def _finalize_metrics(metrics: dict[str, object], graph: StateGraph, crawl_started: float) -> None:
  coverage = _coverage(metrics)
  stop = _stop(metrics)
  reasons = _state_stop_reasons(stop)

  duration = time.perf_counter() - crawl_started
  new_states = int(coverage["new_states_discovered"])
  actions_attempted = int(coverage["actions_attempted"])
  actions_succeeded = int(coverage["actions_succeeded"])

  coverage["duration_seconds"] = round(duration, 3)
  coverage["states_total"] = len(graph.nodes)
  coverage["edges_total"] = len(graph.edges)
  coverage["new_states_per_minute"] = round(
    (new_states / (duration / 60.0)) if duration > 0 else 0.0,
    3,
  )
  coverage["transition_success_rate"] = round(
    (actions_succeeded / actions_attempted) if actions_attempted else 0.0,
    3,
  )

  if "depth_limit" not in reasons:
    reasons["depth_limit"] = 0
  if "no_candidates" not in reasons:
    reasons["no_candidates"] = 0
  if "max_states" not in reasons:
    reasons["max_states"] = 0
  if "action_budget_exhausted" not in reasons:
    reasons["action_budget_exhausted"] = 0
  if "restore_failed" not in reasons:
    reasons["restore_failed"] = 0

  metrics["status"] = "success"
  metrics["ended_at_utc"] = _utc_iso_now()
  stop["termination_reason"] = "frontier_exhausted"
  stop["frontier_exhausted"] = True
