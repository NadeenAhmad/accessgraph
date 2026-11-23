from __future__ import annotations

"""Candidate ordering and selection helpers built on priority scores."""

from dataclasses import dataclass
from typing import Callable, Sequence
from urllib.parse import urljoin

from ..actions import ActionCandidate
from .common import (
  ActionKey,
  CandidatePriorityContext,
  CandidatePriorityEvaluation,
  RoutePair,
  _candidate_region,
  _candidate_selection_group,
  _evaluated_selection_group,
  _is_promotable_main_control,
)
from .scoring import _build_priority_evaluator


@dataclass(frozen=True)
class CandidateSelectionPolicy:
  evaluator: Callable[[ActionCandidate], CandidatePriorityEvaluation] | None = None
  reserve_route_link: bool = False
  route_link_predicate: Callable[[ActionCandidate], bool] | None = None


def _sort_candidates_by_priority(
  candidates: list[ActionCandidate],
  *,
  page_url: str,
  start_url: str,
  in_scope: Callable[[str], bool],
) -> list[ActionCandidate]:
  evaluator = _build_priority_evaluator(
    CandidatePriorityContext(
      page_url=page_url,
      start_url=start_url,
      in_scope=in_scope,
      candidates=candidates,
    )
  )
  return sorted(candidates, key=lambda candidate: (-evaluator(candidate).score,))


def _is_preferred_route_link(
  candidate: ActionCandidate,
  *,
  page_url: str,
  in_scope: Callable[[str], bool],
) -> bool:
  return (
    candidate.action_type == "click"
    and bool(candidate.href)
    and not (candidate.href or "").startswith("#")
    and candidate.aria_current not in {"page", "step", "location", "true"}
    and in_scope(urljoin(page_url, candidate.href or ""))
  )


def _should_reserve_route_link(
  candidates: Sequence[ActionCandidate],
  *,
  page_url: str,
  start_url: str,
  in_scope: Callable[[str], bool],
  attempted_group_counts: dict[str, int],
) -> bool:
  if attempted_group_counts.get("main_link", 0) > 0 or attempted_group_counts.get("section_nav_link", 0) > 0 or attempted_group_counts.get("link", 0) > 0:
    return False

  promotable_main_control_count = sum(1 for candidate in candidates if _is_promotable_main_control(candidate))
  if promotable_main_control_count <= 3:
    return False

  return any(
    _evaluated_selection_group(candidate, page_url=page_url, start_url=start_url) in {"main_link", "section_nav_link", "link"}
    and _is_preferred_route_link(candidate, page_url=page_url, in_scope=in_scope)
    for candidate in candidates
  )


def _action_key(candidate: ActionCandidate) -> ActionKey:
  if candidate.identity:
    return ("identity", candidate.identity)

  return (
    "candidate",
    candidate.action_type,
    candidate.strategy_name,
    candidate.href or "",
    candidate.text[:80],
    candidate.input_type or "",
  )


def _build_priority_selection_policy(
  candidates: Sequence[ActionCandidate],
  *,
  page_url: str,
  start_url: str,
  in_scope: Callable[[str], bool],
  current_route: str | None = None,
  attempted_group_counts: dict[str, int] | None = None,
  attempted_strategy_counts: dict[str, int] | None = None,
  route_visit_counts: dict[str, int] | None = None,
  route_pair_counts: dict[RoutePair, int] | None = None,
) -> CandidateSelectionPolicy:
  context = CandidatePriorityContext(
    page_url=page_url,
    start_url=start_url,
    in_scope=in_scope,
    current_route=current_route or "/",
    candidates=candidates,
    attempted_group_counts=attempted_group_counts,
    attempted_strategy_counts=attempted_strategy_counts,
    route_visit_counts=route_visit_counts,
    route_pair_counts=route_pair_counts,
  )
  return CandidateSelectionPolicy(
    evaluator=_build_priority_evaluator(context),
    reserve_route_link=_should_reserve_route_link(
      candidates,
      page_url=page_url,
      start_url=start_url,
      in_scope=in_scope,
      attempted_group_counts=attempted_group_counts or {},
    ),
    route_link_predicate=lambda candidate: _is_preferred_route_link(
      candidate,
      page_url=page_url,
      in_scope=in_scope,
    ),
  )


def _select_candidate(
  candidates: list[ActionCandidate],
  attempted: set[ActionKey],
  *,
  evaluator: Callable[[ActionCandidate], CandidatePriorityEvaluation] | None = None,
  reserve_route_link: bool = False,
  route_link_predicate: Callable[[ActionCandidate], bool] | None = None,
) -> tuple[int, ActionCandidate, ActionKey, CandidatePriorityEvaluation | None] | None:
  best: tuple[int, ActionCandidate, ActionKey, CandidatePriorityEvaluation | None] | None = None
  best_route_link: tuple[int, ActionCandidate, ActionKey, CandidatePriorityEvaluation | None] | None = None

  for index, candidate in enumerate(candidates):
    key = _action_key(candidate)
    if key in attempted:
      continue
    if evaluator is None:
      return index, candidate, key, None

    evaluation = evaluator(candidate)
    best_score = best[3].score if best and best[3] is not None else None
    if best is None or best_score is None or evaluation.score > best_score:
      best = (index, candidate, key, evaluation)

    if reserve_route_link:
      if (
        evaluation.group in {"main_link", "section_nav_link", "link"}
        and route_link_predicate is not None
        and route_link_predicate(candidate)
      ):
        best_route_score = best_route_link[3].score if best_route_link and best_route_link[3] is not None else None
        if best_route_link is None or best_route_score is None or evaluation.score > best_route_score:
          best_route_link = (index, candidate, key, evaluation)

  return best_route_link or best


def _action_meta(
  candidate: ActionCandidate,
  index: int,
  *,
  priority_evaluation: CandidatePriorityEvaluation | None = None,
) -> dict[str, object]:
  region = priority_evaluation.region if priority_evaluation is not None else _candidate_region(candidate)
  group = priority_evaluation.group if priority_evaluation is not None else _candidate_selection_group(candidate)
  meta: dict[str, object] = {
    "type": candidate.action_type,
    "strategy": candidate.strategy_name,
    "text": candidate.text[:80],
    "selector": candidate.selector or None,
    "href": candidate.href,
    "identity": candidate.identity or None,
    "index": index,
    "candidate_region": region,
    "selection_group": group,
  }
  if candidate.input_type:
    meta["input_type"] = candidate.input_type
  if candidate.action_type == "key" and candidate.key:
    meta["key"] = candidate.key
  if candidate.action_type == "fill_submit":
    meta["form_values"] = [list(pair) for pair in candidate.form_values]
    meta["value_set_kind"] = candidate.value_set_kind
    meta["form_submit_selector"] = candidate.form_submit_selector
  if candidate.data_testid:
    meta["data_testid"] = candidate.data_testid
  if candidate.dom_path:
    meta["dom_path"] = candidate.dom_path
  if candidate.tag_name:
    meta["tag_name"] = candidate.tag_name
  if candidate.button_type:
    meta["button_type"] = candidate.button_type
  if candidate.role:
    meta["role"] = candidate.role
  if candidate.aria_label:
    meta["accessible_name"] = candidate.aria_label
  if priority_evaluation is not None:
    meta["priority_score"] = priority_evaluation.score
    if priority_evaluation.reason_flags:
      meta["priority_reason_flags"] = list(priority_evaluation.reason_flags)
  return meta
