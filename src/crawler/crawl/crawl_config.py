from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
  from .priority.llm_policy import LLMPolicyConfig

TraversalStrategy = Literal["dfs", "bfs"]
CrawlScopePolicy = Literal["any", "same_origin", "same_host", "same_domain"]
ActionPolicy = Literal["discovery", "heuristic", "llm"]
ACTION_POLICIES = ("discovery", "heuristic", "llm")


@dataclass
class CrawlConfig:
  max_states: int = 100
  max_depth: int = 5
  max_actions_per_state: int = 5
  back_timeout_ms: int = 10_000
  traversal_strategy: TraversalStrategy = "bfs"
  scope_policy: CrawlScopePolicy = "same_origin"
  prioritize_action_candidates: bool = False
  enable_tile_screenshots: bool = True
  wait_timeout_ms: int = 2_000
  # Action ordering: discovery order, the heuristic priority scorer, or an LLM ranking (one call per expansion).
  # None keeps the legacy switch: heuristic if prioritize_action_candidates else discovery.
  action_policy: ActionPolicy | None = None
  llm_policy: "LLMPolicyConfig | None" = None
  # Hosts the user allows the crawler to change (fill and submit forms; checkout/purchase/remove/delete
  # actions; storage reset on restore). Empty = none, which is the safe default for public sites.
  submission_allow_hosts: tuple[str, ...] = ()
  # Block every non-GET/HEAD/OPTIONS request to hosts outside submission_allow_hosts during exploration.
  network_guard: bool = True
  # W4A phase 1: elements the audit is about (XPaths). Their actions (and the forms that contain them) are tried
  # first in every state where they appear, so their outcome is recorded (a target-directed exploration, as a
  # checker given a target element does).
  focus_xpaths: tuple[str, ...] = ()
  # W4A phase 1: outcome completion. After exploration, each recorded state presses up to this many controls it has
  # not tried (links, buttons, widgets, hover, keys; discovery order, no LLM) and records where each leads, without
  # exploring further. Bounded by a total number of actions and of extra states. 0 = off.
  outcome_completion_per_state: int = 0
  outcome_completion_max_actions: int = 150
  outcome_completion_max_new_states: int = 50

  def resolved_action_policy(self) -> str:
    if self.action_policy is not None:
      if self.action_policy not in ACTION_POLICIES:
        raise ValueError(f"Unsupported crawl.action_policy: {self.action_policy}")
      return self.action_policy
    return "heuristic" if self.prioritize_action_candidates else "discovery"


__all__ = ["ACTION_POLICIES", "ActionPolicy", "CrawlConfig", "CrawlScopePolicy", "TraversalStrategy"]
