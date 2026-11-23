from __future__ import annotations

import functools
import hashlib
import json
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Sequence
from urllib.parse import urljoin

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any

from ..graph.graph import StateGraph
from ..state.hashing import rendered_dom_identity_hash_for_page, state_dedup_key, wait_for_page_settled
from ..state.state_extractor import capture_state_artifacts
from .actions.selection import ActionSelectionPlanner
from .actions import ActionCandidate, get_action_candidates
from .crawl_config import CrawlConfig
from .metrics.recorder import CrawlMetricsRecorder
from .navigation.scope import CrawlScope
from .state_tracking.recorder import CrawlStateRecorder
from .state_tracking.registry import StateRegistry
from .priority import (
  ActionKey,
  _action_meta,
  _replay_candidate_scan_limit,
)
from .navigation.restore import StateRestorer, _best_effort_back, _navigate_to_url
from .navigation.network_guard import NetworkGuard
from .actions.execution import ActionTimeout, perform_action
from .actions.forms import discover_forms, fill_submit_candidate, host_allowed
from .priority.selection import CandidateSelectionPolicy

STORAGE_FINGERPRINT_JS = """() => {
  const dump = (s) => { const o = {}; try { for (let i = 0; i < s.length; i++) { const k = s.key(i); o[k] = s.getItem(k); } } catch (e) {} return o; };
  return JSON.stringify([dump(localStorage), dump(sessionStorage), document.cookie]);
}"""


@dataclass(frozen=True)
class _ActionExecutionResult:
  timed_out: bool
  succeeded: bool | None


class CrawlSession:
  def __init__(
    self,
    *,
    page: Page,
    start_url: str,
    run_dir: Path,
    cfg: CrawlConfig,
    llm_client: Any | None = None,
  ) -> None:
    self.page = page
    self.start_url = start_url
    self.run_dir = run_dir
    self.action_policy = cfg.resolved_action_policy()
    # The planner's heuristic scorer is on exactly when the heuristic policy is chosen.
    if cfg.prioritize_action_candidates != (self.action_policy == "heuristic"):
      cfg = replace(cfg, prioritize_action_candidates=self.action_policy == "heuristic")
    self.cfg = cfg
    self.allow_hosts = tuple(cfg.submission_allow_hosts)
    candidates_fn = (
      functools.partial(get_action_candidates, allow_hosts=self.allow_hosts) if self.allow_hosts else get_action_candidates
    )
    self.network_guard: NetworkGuard | None = None
    self.llm_policy = None
    if self.action_policy == "llm":
      from .priority.llm_policy import LLMExplorationPolicy, LLMPolicyConfig

      self.llm_policy = LLMExplorationPolicy(
        cfg.llm_policy or LLMPolicyConfig(), client=llm_client, log_path=run_dir / "exploration_log.jsonl"
      )
    self._tried_labels: dict[str, list[str]] = {}
    self._form_skips_logged: set[str] = set()

    self.graph = StateGraph()
    self.metrics_recorder = CrawlMetricsRecorder(cfg)
    self.state_registry = StateRegistry()
    self.state_recorder = CrawlStateRecorder(
      page=self.page,
      run_dir=self.run_dir,
      cfg=self.cfg,
      graph_getter=lambda: self.graph,
      state_registry=self.state_registry,
      metrics_recorder=self.metrics_recorder,
      capture_state_artifacts_fn=capture_state_artifacts,
    )
    self.action_selection = ActionSelectionPlanner(
      page=self.page,
      start_url=self.start_url,
      cfg=self.cfg,
      graph_getter=lambda: self.graph,
      in_scope=self.in_scope,
      metrics_recorder=self.metrics_recorder,
      state_recorder=self.state_recorder,
      get_action_candidates_fn=candidates_fn,
    )
    self.root_state_id: str | None = None
    self.active_root_state_id: str | None = None
    self.scope = CrawlScope.from_start_url(start_url, cfg.scope_policy)
    # AccessGraph boundary: the crawler discovers states and writes raw
    # artifacts/graph data. Taxonomy-specific candidate generation belongs to
    # the later semantic analysis stage, not the live crawl loop.
    self.restorer = StateRestorer(
      page=self.page,
      graph=self.graph,
      state_html_loader=self._saved_state_html,
      start_url=self.start_url,
      back_timeout_ms=self.cfg.back_timeout_ms,
      replay_candidate_scan_limit=_replay_candidate_scan_limit(self.cfg),
      in_scope=self.in_scope,
      root_state_id_getter=lambda: self.active_root_state_id,
      increment_coverage=self.metrics_recorder.increment_coverage,
      record_replay_attempt_metrics=self.metrics_recorder.record_replay_attempt_metrics,
      record_replay_failure=self.metrics_recorder.record_replay_failure,
      get_action_candidates_fn=candidates_fn,
      perform_action_fn=perform_action,
      action_timeout_type=ActionTimeout,
      navigate_to_url_fn=_navigate_to_url,
      best_effort_back_fn=_best_effort_back,
    )
    if self.allow_hosts:
      self.restorer.storage_reset_allowed = lambda url: host_allowed(url, self.allow_hosts)

  def _log_exploration(self, record: dict[str, object]) -> None:
    if self.llm_policy is not None:
      self.llm_policy.log_event(record)
    elif self.allow_hosts:
      path = self.run_dir / "exploration_log.jsonl"
      path.parent.mkdir(parents=True, exist_ok=True)
      with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

  async def _storage_fingerprint(self) -> str | None:
    if not self.allow_hosts or not host_allowed(self.page.url, self.allow_hosts):
      return None
    try:
      return hashlib.sha256(str(await self.page.evaluate(STORAGE_FINGERPRINT_JS)).encode("utf-8")).hexdigest()
    except Exception:
      return None

  async def _plan_with_llm(
    self, current_state_id: str, candidates: list[ActionCandidate]
  ) -> tuple[list[ActionCandidate], CandidateSelectionPolicy | None]:
    """LLM ranking for this expansion (one call, cached) plus one fill_submit action per form value set."""
    forms, skips = await discover_forms(self.page, allow_hosts=self.allow_hosts)
    if current_state_id not in self._form_skips_logged:
      self._form_skips_logged.add(current_state_id)
      for skip in skips:
        self.metrics_recorder.increment_coverage("forms_skipped")
        self._log_exploration({"event": "form_skipped", "state_id": current_state_id, "form": skip.form_selector,
                               "reason": skip.reason})
      if self.allow_hosts and not host_allowed(self.page.url, self.allow_hosts):
        self._log_exploration({"event": "forms_not_allowed_host", "state_id": current_state_id, "url": self.page.url})
    seen = sorted({f"{meta.get('url', '')} | {meta.get('title', '')}" for meta in self.graph.nodes.values()})
    plan = await self.llm_policy.plan(
      self.page, state_id=current_state_id, candidates=candidates, forms=forms,
      tried=self._tried_labels.get(current_state_id, []), seen=seen,
    )
    form_candidates = [
      fill_submit_candidate(self.page, form, kind, values)
      for form in forms
      for kind, values in plan.value_sets.get(form.selector, [])
    ]
    merged = candidates + [c for c in form_candidates if c is not None]
    policy = CandidateSelectionPolicy(evaluator=plan.evaluator()) if plan.source == "llm" else None
    return merged, policy

  async def _with_focus(
    self, candidates: list[ActionCandidate], policy: CandidateSelectionPolicy | None
  ) -> CandidateSelectionPolicy:
    """W4A phase 1: actions on a focus element, inside it, or containing it (and forms that contain it) first."""
    focus = [_xpath_key(x) for x in self.cfg.focus_xpaths if x]
    hits: set[int] = set()
    for candidate in candidates:
      try:
        if candidate.action_type == "fill_submit":
          inside = await candidate.locator.evaluate(_FORM_CONTAINS_JS, list(self.cfg.focus_xpaths))
          if inside:
            hits.add(id(candidate))
          continue
        xpath = _xpath_key(await candidate.locator.evaluate(_ELEMENT_XPATH_JS))
      except Exception:
        continue
      if any(xpath == f or xpath.startswith(f + "/") or f.startswith(xpath + "/") for f in focus):
        hits.add(id(candidate))
    base = policy.evaluator if policy is not None and policy.evaluator is not None else None
    from .priority.common import CandidatePriorityEvaluation

    def evaluate(candidate: ActionCandidate):
      inner = base(candidate) if base is not None else CandidatePriorityEvaluation(
        score=0, group="discovery", region="", reason_flags=())
      if id(candidate) in hits:
        return replace(inner, score=inner.score + 1_000_000, reason_flags=(*inner.reason_flags, "focus_element"))
      return inner

    return CandidateSelectionPolicy(evaluator=evaluate,
                                    reserve_route_link=policy.reserve_route_link if policy else False,
                                    route_link_predicate=policy.route_link_predicate if policy else None)

  def in_scope(self, url: str) -> bool:
    return self.scope.contains(url)

  async def _initialize_root_state(self) -> str:
    root_id = self.state_registry.next_state_id()
    self.root_state_id = root_id
    self.active_root_state_id = root_id
    await self.state_recorder.save_state(
      root_id,
      depth=0,
      parent_state=None,
      action_from_parent=None,
      active_root_state_id=root_id,
    )
    return root_id

  def _skip_out_of_scope_href_before_action(
    self,
    *,
    current_state_id: str,
    selected_candidate: ActionCandidate,
    selected_key: ActionKey,
    attempted_action_keys: set[ActionKey],
  ) -> bool:
    if selected_candidate.action_type != "click" or not selected_candidate.href:
      return False

    target_url = urljoin(self.page.url, selected_candidate.href)
    attempted_action_keys.add(selected_key)
    self.state_recorder.record_attempted_action(current_state_id, selected_key)
    if self.in_scope(target_url):
      return False

    self.metrics_recorder.increment_coverage("actions_skipped_out_of_scope_pre")
    return True

  async def _perform_selected_action(self, selected_candidate: ActionCandidate) -> _ActionExecutionResult:
    since = await self._watch_transient_messages()
    try:
      result = _ActionExecutionResult(
        timed_out=False,
        succeeded=await perform_action(
          selected_candidate,
          wait_timeout_ms=self.cfg.wait_timeout_ms,
        ),
      )
    except ActionTimeout:
      self.metrics_recorder.increment_coverage("action_timeouts")
      return _ActionExecutionResult(timed_out=True, succeeded=None)
    self._last_transient_messages = await self._transient_messages_since(since)
    return result

  async def _watch_transient_messages(self) -> float | None:
    """W4A phase 1: record messages that appear briefly after an action (toasts, alerts, status and live regions),
    which a state captured later may no longer show. Returns the page time before the action."""
    self._last_transient_messages = []
    try:
      if not getattr(self, "_transient_init_installed", False):
        await self.page.context.add_init_script(TRANSIENT_MESSAGES_JS)
        self._transient_init_installed = True
      await self.page.evaluate(TRANSIENT_MESSAGES_JS)
      return float(await self.page.evaluate("Date.now()"))
    except Exception:
      return None

  async def _transient_messages_since(self, since: float | None) -> list[dict[str, object]]:
    if since is None:
      return []
    try:
      messages = await self.page.evaluate(
        "(since) => (window.__w4aTransient || []).filter((m) => m.t >= since).slice(-10)", since)
      return [m for m in messages if isinstance(m, dict)]
    except Exception:
      return []

  async def _restore_after_action(
    self,
    *,
    current_url_for_back: str,
    restore_current_state: Callable[[], Awaitable[bool]] | None,
  ) -> bool:
    if restore_current_state is not None:
      return await restore_current_state()

    await _best_effort_back(self.page, current_url_for_back, self.cfg.back_timeout_ms)
    return True

  async def _restore_after_no_change_action(
    self,
    *,
    current_url_for_back: str,
    restore_current_state: Callable[[], Awaitable[bool]] | None,
  ) -> bool:
    if restore_current_state is not None:
      return await restore_current_state()

    await _best_effort_back(self.page, current_url_for_back, self.cfg.back_timeout_ms)
    return True

  def _record_failed_action(self) -> None:
    self.metrics_recorder.increment_coverage("actions_failed")

  def _record_out_of_scope_after_action(self) -> None:
    self.metrics_recorder.increment_coverage("actions_skipped_out_of_scope_post")

  def _record_no_state_change(self) -> None:
    self.metrics_recorder.increment_coverage("actions_no_state_change")

  async def _expand_state(
    self,
    current_state_id: str,
    current_depth: int,
    current_url_for_back: str,
    on_child_state: Callable[[str, int, str], Awaitable[None]],
    restore_current_state: Callable[[], Awaitable[bool]] | None = None,
    restore_current_state_after_no_change: Callable[[], Awaitable[bool]] | None = None,
  ) -> None:
    if current_depth >= self.cfg.max_depth:
      self.metrics_recorder.increment_stop("states_at_max_depth")
      self.metrics_recorder.record_stop_reason("depth_limit")
      self.state_recorder.record_state_expansion_result(current_state_id, depth=current_depth, stop_reason="depth_limit")
      return

    self.metrics_recorder.increment_stop("states_expanded")

    persisted_attempted_action_keys = set(self.state_registry.attempted_actions_for_state(current_state_id))
    attempted_action_keys: set[ActionKey] = set(persisted_attempted_action_keys)
    counted_previously_attempted_keys: set[ActionKey] = set()
    attempted_group_counts: dict[str, int] = {}
    attempted_strategy_counts: dict[str, int] = {}
    budget_used = 0
    stop_reason = "no_candidates"

    while budget_used < self.cfg.max_actions_per_state:
      if len(self.graph.nodes) >= self.cfg.max_states:
        self.metrics_recorder.increment_stop("states_at_max_states")
        stop_reason = "max_states"
        break

      candidates = await self.action_selection.get_candidates()
      self.action_selection.record_previously_attempted_candidates(
        candidates,
        persisted_attempted_action_keys,
        counted_previously_attempted_keys,
      )
      if self.llm_policy is not None:
        candidates, selection_policy = await self._plan_with_llm(current_state_id, candidates)
      else:
        selection_policy = self.action_selection.selection_policy_for_state(
          current_state_id=current_state_id,
          candidates=candidates,
          attempted_group_counts=attempted_group_counts,
          attempted_strategy_counts=attempted_strategy_counts,
        )
      if self.cfg.focus_xpaths:
        selection_policy = await self._with_focus(candidates, selection_policy)
      selected = self.action_selection.select_candidate_for_state(
        candidates=candidates,
        attempted_action_keys=attempted_action_keys,
        selection_policy=selection_policy,
      )
      if selected is None:
        stop_reason = "no_candidates"
        break

      selected_idx, selected_candidate, selected_key, priority_evaluation = selected
      priority_reason_flags: tuple[str, ...] = priority_evaluation.reason_flags if priority_evaluation is not None else ()
      action_meta = _action_meta(
        selected_candidate,
        selected_idx,
        priority_evaluation=priority_evaluation,
      )

      if self._skip_out_of_scope_href_before_action(
        current_state_id=current_state_id,
        selected_candidate=selected_candidate,
        selected_key=selected_key,
        attempted_action_keys=attempted_action_keys,
      ):
        continue

      before_dom_identity_hash = await rendered_dom_identity_hash_for_page(self.page)
      before_url = self.page.url

      self.action_selection.record_action_attempt(
        current_state_id=current_state_id,
        selected_candidate=selected_candidate,
        selected_key=selected_key,
        attempted_action_keys=attempted_action_keys,
        attempted_group_counts=attempted_group_counts,
        attempted_strategy_counts=attempted_strategy_counts,
        priority_evaluation=priority_evaluation,
        priority_reason_flags=priority_reason_flags,
      )
      budget_used += 1
      storage_before = await self._storage_fingerprint()
      if self.llm_policy is not None or self.allow_hosts:
        from .priority.llm_policy import action_label

        label = action_label(selected_candidate)
        self._tried_labels.setdefault(current_state_id, []).append(label)
        self._log_exploration({"event": "select", "state_id": current_state_id, "policy": self.action_policy,
                               "action": label, "identity": selected_candidate.identity,
                               "reason_flags": list(priority_reason_flags)})
      if selected_candidate.action_type == "fill_submit":
        self.metrics_recorder.increment_coverage("form_actions_attempted")
      result = await self._perform_selected_action(selected_candidate)
      if getattr(self, "_last_transient_messages", None):  # W4A phase 1
        action_meta = {**action_meta, "transient_messages": self._last_transient_messages}
      if result.succeeded and (
        selected_candidate.action_type == "fill_submit"
        or (storage_before is not None and storage_before != await self._storage_fingerprint())
      ) and self.allow_hosts and host_allowed(self.page.url, self.allow_hosts):
        self.restorer.storage_dirty = True
        self.metrics_recorder.increment_coverage("actions_changed_app_storage")
      if result.timed_out:
        continue

      if not result.succeeded:
        self._record_failed_action()
        continue

      await wait_for_page_settled(self.page)  # decide new vs known state on the settled page, as it is recorded
      after_dom_identity_hash = await rendered_dom_identity_hash_for_page(self.page)
      after_url = self.page.url
      before_key = state_dedup_key(dom_identity_hash=before_dom_identity_hash, url=before_url)
      after_key = state_dedup_key(dom_identity_hash=after_dom_identity_hash, url=after_url)

      if not self.in_scope(after_url):
        self._record_out_of_scope_after_action()
        if not await self._restore_after_action(
          current_url_for_back=current_url_for_back,
          restore_current_state=restore_current_state,
        ):
          stop_reason = "restore_failed"
          break
        continue

      if before_key == after_key:
        self._record_no_state_change()
        if not await self._restore_after_no_change_action(
          current_url_for_back=current_url_for_back,
          restore_current_state=restore_current_state_after_no_change,
        ):
          stop_reason = "restore_failed"
          break
        continue

      discovered_new_state = False
      existing_state_id = self.state_registry.state_for_key(after_key)
      if existing_state_id is not None:
        next_state_id = existing_state_id
        if next_state_id == current_state_id:
          self._record_no_state_change()
          if not await self._restore_after_no_change_action(
            current_url_for_back=current_url_for_back,
            restore_current_state=restore_current_state_after_no_change,
          ):
            stop_reason = "restore_failed"
            break
          continue
        self.metrics_recorder.increment_coverage("existing_state_hits")
        budget_used -= 1
      else:
        if len(self.graph.nodes) >= self.cfg.max_states:
          self.metrics_recorder.increment_stop("states_at_max_states")
          stop_reason = "max_states"
          break
        next_state_id = await self.state_recorder.save_new_state_from_action(
          current_state_id=current_state_id,
          current_depth=current_depth,
          action_meta=action_meta,
          active_root_state_id=self.active_root_state_id,
        )
        discovered_new_state = True

      self.state_recorder.record_action_transition(
        current_state_id=current_state_id,
        next_state_id=next_state_id,
        action_meta=action_meta,
        discovered_new_state=discovered_new_state,
      )

      child_parent_url = self.page.url
      await on_child_state(next_state_id, current_depth + 1, child_parent_url)
      if not await self._restore_after_action(
        current_url_for_back=current_url_for_back,
        restore_current_state=restore_current_state,
      ):
        stop_reason = "restore_failed"
        break

    if budget_used >= self.cfg.max_actions_per_state:
      stop_reason = "action_budget_exhausted"
    self.metrics_recorder.record_stop_reason(stop_reason)
    self.state_recorder.record_state_expansion_result(current_state_id, depth=current_depth, stop_reason=stop_reason)

  async def _run_dfs(self, seed_state_ids: Sequence[str]) -> None:
    async def dfs(current_state_id: str, current_depth: int, current_url_for_back: str) -> None:
      self.active_root_state_id = self.state_recorder.seed_root_for_state(current_state_id)

      async def on_child(next_state_id: str, child_depth: int, child_parent_url: str) -> None:
        await dfs(next_state_id, child_depth, child_parent_url)

      async def restore_current_state() -> bool:
        return await self.restorer.restore_state_with_back_fallback(current_state_id, current_url_for_back)

      async def restore_current_state_after_no_change() -> bool:
        return await self.restorer.restore_state(current_state_id, current_url_for_back, force=True)

      await self._expand_state(
        current_state_id,
        current_depth,
        current_url_for_back,
        on_child,
        restore_current_state=restore_current_state,
        restore_current_state_after_no_change=restore_current_state_after_no_change,
      )

    for seed_state_id in seed_state_ids:
      seed_meta = self.graph.nodes.get(seed_state_id, {})
      seed_url = str(seed_meta.get("url") or self.start_url)
      if not self.in_scope(seed_url):
        continue
      await dfs(seed_state_id, 0, seed_url)

  async def _run_bfs(self, seed_state_ids: Sequence[str]) -> None:
    queue: deque[tuple[str, int]] = deque((seed_state_id, 0) for seed_state_id in seed_state_ids)
    queued: set[str] = set(seed_state_ids)
    expanded: set[str] = set()

    while queue:
      current_state_id, current_depth = queue.popleft()
      queued.discard(current_state_id)

      if current_state_id in expanded:
        continue
      expanded.add(current_state_id)

      if current_depth >= self.cfg.max_depth:
        self.metrics_recorder.increment_stop("states_at_max_depth")
        self.metrics_recorder.record_stop_reason("depth_limit")
        self.state_recorder.record_state_expansion_result(current_state_id, depth=current_depth, stop_reason="depth_limit")
        continue

      state_meta = self.graph.nodes.get(current_state_id, {})
      state_url = str(state_meta.get("url") or self.start_url)
      if not self.in_scope(state_url):
        continue
      self.active_root_state_id = self.state_recorder.seed_root_for_state(current_state_id)
      if not await self.restorer.restore_state(current_state_id, state_url):
        self.metrics_recorder.record_stop_reason("restore_failed")
        self.state_recorder.record_state_expansion_result(current_state_id, depth=current_depth, stop_reason="restore_failed")
        continue

      async def on_child(next_state_id: str, child_depth: int, _child_parent_url: str) -> None:
        if child_depth > self.cfg.max_depth:
          return
        if next_state_id in expanded or next_state_id in queued:
          return
        queue.append((next_state_id, child_depth))
        queued.add(next_state_id)

      async def restore_current_state() -> bool:
        return await self.restorer.restore_state(current_state_id, state_url)

      async def restore_current_state_after_no_change() -> bool:
        return await self.restorer.restore_state(current_state_id, state_url, force=True)

      await self._expand_state(
        current_state_id,
        current_depth,
        state_url,
        on_child,
        restore_current_state=restore_current_state,
        restore_current_state_after_no_change=restore_current_state_after_no_change,
      )

  def _saved_state_html(self, state_id: str) -> str | None:
    try:
      return (Path(self.run_dir) / "states" / state_id / "dom.html").read_text(encoding="utf-8", errors="replace")
    except OSError:
      return None

  async def _complete_outcomes(self) -> None:
    """W4A phase 1: press, in each recorded state, controls the exploration did not try, so every link, button and
    widget the judge sees has an observed outcome where possible. New states are recorded, not expanded."""
    base_cfg, base_policy = self.cfg, self.llm_policy
    budget_total = self.cfg.outcome_completion_max_actions
    state_cap = len(self.graph.nodes) + self.cfg.outcome_completion_max_new_states
    self.cfg = replace(base_cfg, max_actions_per_state=base_cfg.outcome_completion_per_state, max_states=state_cap,
                       max_depth=10_000, action_policy="discovery", llm_policy=None, outcome_completion_per_state=0)
    self.llm_policy = None
    planner_cfg = self.action_selection.cfg
    self.action_selection.cfg = replace(planner_cfg, max_actions_per_state=base_cfg.outcome_completion_per_state,
                                        action_policy="discovery", llm_policy=None, prioritize_action_candidates=False)
    try:
      for state_id in list(self.graph.nodes):
        if budget_total <= 0 or len(self.graph.nodes) >= state_cap:
          break
        meta = self.graph.nodes.get(state_id, {})
        state_url = str(meta.get("url") or self.start_url)
        if not self.in_scope(state_url):
          continue
        if not await self.restorer.restore_state(state_id, state_url):
          continue
        before = self.metrics_recorder.metrics.get("coverage", {}).get("actions_attempted", 0) \
          if isinstance(self.metrics_recorder.metrics, dict) else 0

        async def no_children(_next: str, _depth: int, _url: str) -> None:
          return None

        async def restore_here(sid: str = state_id, url: str = state_url) -> bool:
          return await self.restorer.restore_state(sid, url)

        async def restore_here_forced(sid: str = state_id, url: str = state_url) -> bool:
          return await self.restorer.restore_state(sid, url, force=True)

        await self._expand_state(state_id, int(meta.get("depth") or 0), state_url, no_children,
                                 restore_current_state=restore_here,
                                 restore_current_state_after_no_change=restore_here_forced)
        after = self.metrics_recorder.metrics.get("coverage", {}).get("actions_attempted", 0) \
          if isinstance(self.metrics_recorder.metrics, dict) else 0
        budget_total -= max(1, int(after) - int(before))
        self.metrics_recorder.increment_coverage("outcome_completion_states")
    finally:
      self.cfg, self.llm_policy = base_cfg, base_policy
      self.action_selection.cfg = planner_cfg

  async def _install_network_guard(self) -> None:
    if not self.cfg.network_guard:
      return
    guard = NetworkGuard(allow_hosts=self.allow_hosts)
    try:
      await guard.install(self.page)
      self.network_guard = guard
    except Exception:
      self.network_guard = None

  def _finish_network_guard(self) -> None:
    if self.network_guard is None or not self.network_guard.blocked:
      return
    self.metrics_recorder.increment_coverage("network_requests_blocked", len(self.network_guard.blocked))
    path = self.run_dir / "network_guard_blocked.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
      for record in self.network_guard.blocked:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

  def _finish_exploration_counters(self) -> None:
    if self.llm_policy is None:
      return
    counters = self.llm_policy.counters
    self.metrics_recorder.increment_coverage("llm_plan_calls", int(counters["llm_calls"]))
    self.metrics_recorder.increment_coverage("llm_plan_fallbacks", int(counters["llm_fallbacks"]))
    self.metrics_recorder.increment_coverage("llm_form_value_sets", int(counters["form_value_sets"]))
    self.metrics_recorder.metrics["exploration_llm_cost_usd"] = round(float(counters["cost_usd"]), 6)

  async def crawl(self) -> StateGraph:
    await self._install_network_guard()
    root_id = await self._initialize_root_state()
    seed_state_ids = [root_id]

    if self.cfg.traversal_strategy == "dfs":
      await self._run_dfs(seed_state_ids)
    elif self.cfg.traversal_strategy == "bfs":
      await self._run_bfs(seed_state_ids)
    else:
      raise ValueError(f"Unsupported traversal strategy: {self.cfg.traversal_strategy}")

    if self.cfg.outcome_completion_per_state > 0:
      await self._complete_outcomes()

    self._finish_network_guard()
    self._finish_exploration_counters()
    self.metrics_recorder.finalize(self.graph)
    self.graph.metrics = self.metrics_recorder.metrics
    return self.graph


__all__ = ["CrawlSession"]

_ELEMENT_XPATH_JS = """(el) => {
  const steps = [];
  for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
    let index = 1;
    for (let sib = node.previousElementSibling; sib; sib = sib.previousElementSibling)
      if (sib.localName === node.localName) index++;
    steps.unshift(`${node.localName}[${index}]`);
  }
  return '/' + steps.join('/');
}"""

_FORM_CONTAINS_JS = """(el, xpaths) => {
  const form = el.closest('form') || el.parentElement;
  return !!form && xpaths.some((x) => {
    const local = x.split('/').filter(Boolean).map((s) => /^[A-Za-z][\\w-]*(\\[\\d+\\])?$/.test(s)
      ? `*[local-name()='${s.replace(/\\[.*$/, '').toLowerCase()}']${(s.match(/\\[\\d+\\]$/) || [''])[0]}` : s).join('/');
    let target = null;
    try { target = document.evaluate('/' + local, document, null, 9, null).singleNodeValue; } catch (e) { target = null; }
    return !!target && form.contains(target);
  });
}"""


def _xpath_key(xpath: str | None) -> str:
  import re
  return re.sub(r"\[1\](?=/|$)", "", str(xpath or "").strip()).lower()


# Messages that appear in alerts, status and live regions, or in elements named like toasts/notifications, with the
# page time they appeared (kept per document, at most 100).
TRANSIENT_MESSAGES_JS = """(() => {
  if (window.__w4aTransientInstalled) return;
  window.__w4aTransientInstalled = true;
  window.__w4aTransient = window.__w4aTransient || [];
  const named = /(toast|snackbar|notification|notice|flash|alert|status|message)/i;
  const hostOf = (el) => el.closest && (el.closest('[role="alert"], [role="status"], [role="log"], [aria-live]')
    || (named.test(`${el.id || ''} ${typeof el.className === 'string' ? el.className : ''}`) ? el : null));
  const note = (el) => {
    if (!el || el.nodeType !== 1) return;
    const host = hostOf(el);
    if (!host) return;
    const text = String(host.innerText || host.textContent || '').replace(/\\s+/g, ' ').trim();
    if (!text || text.length > 300) return;
    const last = window.__w4aTransient[window.__w4aTransient.length - 1];
    if (last && last.text === text) return;
    window.__w4aTransient.push({ t: Date.now(), text, role: host.getAttribute('role'), live: host.getAttribute('aria-live') });
    if (window.__w4aTransient.length > 100) window.__w4aTransient.shift();
  };
  new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === 'childList') m.addedNodes.forEach((n) => note(n.nodeType === 1 ? n : n.parentElement));
      else if (m.target && m.target.parentElement) note(m.target.parentElement);
    }
  }).observe(document, { subtree: true, childList: true, characterData: true });
})()"""

