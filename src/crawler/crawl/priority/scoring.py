from __future__ import annotations

"""Candidate priority scoring and diagnostic helpers."""

from typing import Callable, Mapping, Sequence
from urllib.parse import urljoin

from ..actions import ActionCandidate
from .common import (
  CLIPBOARD_TOKENS,
  CandidatePriorityContext,
  CandidatePriorityEvaluation,
  DEMO_TOKENS,
  DISCOVERY_TOKENS,
  GENERIC_LINK_TEXT,
  NAVIGATION_LABELS,
  PROGRESSION_TOKENS,
  RoutePair,
  STRUCTURED_CONTROL_STRATEGIES,
  UTILITY_SEARCH_TOKENS,
  WIDGET_CONTROL_ROLES,
  _candidate_path_relevance_diagnostics,
  _candidate_region,
  _candidate_selection_group,
  _evaluated_selection_group,
  _is_promotable_main_control,
  _normalized_candidate_text,
  _route_for_url,
  _same_document_target,
  _text_contains_any,
)


def _candidate_repetition_diagnostics(
  candidate: ActionCandidate,
  *,
  candidates: Sequence[ActionCandidate],
  page_url: str,
  start_url: str,
) -> tuple[int, tuple[str, ...]]:
  penalty = 0
  flags: list[str] = []
  text = _normalized_candidate_text(candidate)
  group = _evaluated_selection_group(candidate, page_url=page_url, start_url=start_url)

  if text:
    same_text_count = sum(1 for other in candidates if _normalized_candidate_text(other) == text)
    if same_text_count > 1:
      penalty += min((same_text_count - 1) * 4, 12)
      flags.append("repeated_text")
      if group == "global_nav_link":
        penalty += min((same_text_count - 1) * 5, 15)
        flags.append("repeated_nav_text")

  if candidate.action_type == "click" and candidate.href:
    target_url = urljoin(page_url, candidate.href)
    same_target_count = sum(
      1
      for other in candidates
      if other.action_type == "click" and other.href and urljoin(page_url, other.href) == target_url
    )
    if same_target_count > 1:
      penalty += min((same_target_count - 1) * 4, 12)
      flags.append("repeated_target")

  if group == "global_nav_link":
    nav_cluster_count = sum(
      1
      for other in candidates
      if _evaluated_selection_group(other, page_url=page_url, start_url=start_url) == "global_nav_link"
    )
    if nav_cluster_count > 2:
      penalty += min((nav_cluster_count - 2) * 5, 15)
      flags.append("nav_cluster")

  return penalty, tuple(flags)


def _candidate_diversity_diagnostics(
  *,
  group: str,
  attempted_group_counts: dict[str, int],
) -> tuple[int, tuple[str, ...]]:
  prior_attempts = attempted_group_counts.get(group, 0)
  if prior_attempts <= 0:
    return 0, ()
  if group == "global_nav_link":
    return prior_attempts * 18, ("repeat_group_penalty", "repeat_nav_group")
  if group in {"main_link", "section_nav_link", "link"}:
    return prior_attempts * 8, ("repeat_group_penalty",)
  if group in {"main_control", "control"}:
    return prior_attempts * 6, ("repeat_group_penalty",)
  return prior_attempts * 4, ("repeat_group_penalty",)


def _candidate_strategy_diversity_diagnostics(
  candidate: ActionCandidate,
  *,
  candidates: Sequence[ActionCandidate],
  attempted_strategy_counts: dict[str, int],
  route_link_count: int,
) -> tuple[int, tuple[str, ...]]:
  prior_attempts = attempted_strategy_counts.get(candidate.strategy_name, 0)
  if prior_attempts <= 0:
    return 0, ()
  if candidate.action_type != "click" or candidate.href:
    return 0, ()

  same_strategy_cluster = sum(
    1
    for other in candidates
    if other.action_type == "click" and not other.href and other.strategy_name == candidate.strategy_name
  )
  if same_strategy_cluster <= 2:
    return 0, ()

  penalty = prior_attempts * 10 + min((same_strategy_cluster - 2) * 4, 12)
  flags = ["repeat_strategy_cluster"]
  if route_link_count > 0:
    penalty += min(route_link_count * 3, 9)
    flags.append("route_links_still_available")
  return penalty, tuple(flags)


def _candidate_graph_diagnostics(
  candidate: ActionCandidate,
  *,
  context: CandidatePriorityContext,
  group: str,
  route_link_count: int,
) -> tuple[int, tuple[str, ...]]:
  score = 0
  flags: list[str] = []
  route_visit_counts = context.route_visit_counts or {}
  route_pair_counts = context.route_pair_counts or {}
  current_route = context.current_route or _route_for_url(context.page_url)

  current_route_visits = int(route_visit_counts.get(current_route, 0))
  if (
    candidate.action_type == "click"
    and not candidate.href
    and not candidate.in_main
    and current_route_visits >= 4
  ):
    score -= min((current_route_visits - 3) * 6, 18)
    flags.append("overexplored_route_non_main_control")

  if candidate.action_type != "click" or not candidate.href:
    return score, tuple(flags)

  target_route = _route_for_url(urljoin(context.page_url, candidate.href))
  target_route_visits = int(route_visit_counts.get(target_route, 0))
  route_pair_repeats = int(route_pair_counts.get((current_route, target_route), 0))

  if target_route_visits <= 0:
    score += 4
    flags.append("unseen_route")
  elif target_route_visits >= 3:
    score -= min((target_route_visits - 2) * 6, 24)
    flags.append("overexplored_route")

  if route_pair_repeats > 0:
    score -= min(route_pair_repeats * 8, 24)
    flags.append("repeat_route_pair")

  if target_route == current_route and route_link_count > 0:
    score -= 10
    flags.append("same_route_link")

  if (
    group == "global_nav_link"
    and target_route in {"/", "/login"}
    and current_route not in {"/", "/login"}
    and route_link_count > 0
  ):
    score -= 18
    flags.append("global_nav_detour")

  return score, tuple(flags)


def _evaluate_candidate_priority_in_context(
  candidate: ActionCandidate,
  *,
  context: CandidatePriorityContext,
) -> CandidatePriorityEvaluation:
  return _evaluate_candidate_priority(
    candidate,
    page_url=context.page_url,
    start_url=context.start_url,
    in_scope=context.in_scope,
    current_route=context.current_route,
    candidates=context.candidates,
    attempted_group_counts=context.attempted_group_counts,
    attempted_strategy_counts=context.attempted_strategy_counts,
    route_visit_counts=context.route_visit_counts,
    route_pair_counts=context.route_pair_counts,
  )


def _build_priority_evaluator(
  context: CandidatePriorityContext,
) -> Callable[[ActionCandidate], CandidatePriorityEvaluation]:
  return lambda candidate: _evaluate_candidate_priority_in_context(candidate, context=context)


def _evaluate_candidate_priority(
  candidate: ActionCandidate,
  *,
  page_url: str,
  start_url: str,
  in_scope: Callable[[str], bool],
  current_route: str | None = None,
  candidates: Sequence[ActionCandidate] | None = None,
  attempted_group_counts: Mapping[str, int] | None = None,
  attempted_strategy_counts: Mapping[str, int] | None = None,
  route_visit_counts: Mapping[str, int] | None = None,
  route_pair_counts: Mapping[RoutePair, int] | None = None,
) -> CandidatePriorityEvaluation:
  flags: list[str] = []
  text = _normalized_candidate_text(candidate)
  region = _candidate_region(candidate)
  group = _evaluated_selection_group(candidate, page_url=page_url, start_url=start_url)
  flags.append(f"region:{region}")
  flags.append(f"group:{group}")
  score = 0
  promotable_main_control_count = 0
  route_link_count = 0
  if candidates is not None:
    promotable_main_control_count = sum(1 for other in candidates if _is_promotable_main_control(other))
    route_link_count = sum(
      1
      for other in candidates
      if _evaluated_selection_group(other, page_url=page_url, start_url=start_url) in {"main_link", "section_nav_link", "link"}
    )

  if candidate.action_type == "click" and candidate.href:
    target_url = urljoin(page_url, candidate.href)
    if in_scope(target_url):
      flags.append("in_scope_link")
      score += 18
    else:
      flags.append("out_of_scope_link")
      score -= 20
    if candidate.href.startswith("#"):
      flags.append("fragment_link")
      score -= 10
    if _same_document_target(page_url, target_url):
      flags.append("same_document_link")
      score -= 35

    path_score, path_flags = _candidate_path_relevance_diagnostics(
      candidate,
      page_url=page_url,
      start_url=start_url,
    )
    score += path_score
    flags.extend(path_flags)

  if candidate.in_main:
    flags.append("main_content")
    score += 20
  if candidate.in_header:
    flags.append("header_region")
    score -= 10
  if candidate.in_nav:
    flags.append("nav_region")
    score -= 16
  if candidate.in_footer:
    flags.append("footer_region")
    score -= 14
  if group == "section_nav_link":
    flags.append("section_nav")
    score += 30

  graph_score, graph_flags = _candidate_graph_diagnostics(
    candidate,
    context=CandidatePriorityContext(
      page_url=page_url,
      start_url=start_url,
      in_scope=in_scope,
      current_route=current_route or _route_for_url(page_url),
      route_visit_counts=route_visit_counts,
      route_pair_counts=route_pair_counts,
      candidates=candidates,
      attempted_group_counts=attempted_group_counts,
      attempted_strategy_counts=attempted_strategy_counts,
    ),
    group=group,
    route_link_count=route_link_count,
  )
  score += graph_score
  flags.extend(graph_flags)

  if candidate.strategy_name in {"buttons", "role_button", "button_inputs"}:
    flags.append("button_strategy")
    score += 6
    if candidate.in_main and candidate.action_type != "type":
      flags.append("main_content_button")
      score += 6

  if candidate.strategy_name in STRUCTURED_CONTROL_STRATEGIES or candidate.role in WIDGET_CONTROL_ROLES:
    flags.append("structured_widget_control")
    score += 24
    if candidate.in_main and candidate.action_type != "type":
      flags.append("main_widget_control")
      score += 18

  if candidate.strategy_name == "contenteditable":
    flags.append("editable_control")
    score += 6
    if candidate.in_main:
      flags.append("main_editable_control")
      score += 6

  if candidate.action_type == "click" and not candidate.href:
    flags.append("control_without_href")
    score += 4
    if candidate.in_main and candidate.action_type != "type":
      score += 4
  if candidate.action_type == "click" and candidate.href and candidate.in_main:
    flags.append("main_content_link")
    score += 8

  if _is_promotable_main_control(candidate) and route_link_count > 0:
    if promotable_main_control_count <= 3:
      flags.append("preferred_control_over_links")
      score += min(route_link_count * 4, 12)
  if group == "main_control" and not _is_promotable_main_control(candidate) and route_link_count > 0:
    flags.append("generic_control_with_links_available")
    score -= min(route_link_count * 5, 15)
  if group == "main_control" and route_link_count > 0 and promotable_main_control_count > 3:
    flags.append("control_cluster_with_links_available")
    score -= min((promotable_main_control_count - 3) * 14, 28)
  if group in {"main_link", "section_nav_link"} and 0 < promotable_main_control_count <= 3:
    flags.append("controls_available_in_main")
    score -= min(promotable_main_control_count * 6, 18)

  if candidate.action_type == "click" and not candidate.href and route_link_count > 0:
    if _text_contains_any(text, CLIPBOARD_TOKENS):
      flags.append("clipboard_like_control")
      score -= 24
    if _text_contains_any(text, UTILITY_SEARCH_TOKENS) and not candidate.in_main:
      flags.append("utility_search_control")
      score -= 28
    if (
      candidate.aria_expanded == "false"
      and not candidate.in_main
      and not _text_contains_any(text, DISCOVERY_TOKENS | UTILITY_SEARCH_TOKENS | PROGRESSION_TOKENS)
    ):
      flags.append("generic_expander_with_links_available")
      score -= min(route_link_count * 16, 36)

  if candidate.aria_current in {"page", "step", "location", "true"}:
    flags.append("aria_current")
    score -= 18
  if candidate.aria_expanded == "false":
    flags.append("collapsed_expander")
    if candidate.in_main:
      score += 35
    elif "search" in text:
      score += 8
    else:
      score += 22

  if _text_contains_any(text, {"dismiss", "close", "accept", "agree", "allow", "consent"}):
    flags.append("dismiss_control")
    score += 60
  if _text_contains_any(text, DISCOVERY_TOKENS):
    flags.append("discovery_control")
    score += 25
  if _text_contains_any(text, PROGRESSION_TOKENS):
    flags.append("progression_control")
    score += 20
  if candidate.in_main and candidate.action_type != "type" and _text_contains_any(text, DEMO_TOKENS):
    flags.append("demo_control")
    score += 24
  if group == "global_nav_link" and text in NAVIGATION_LABELS:
    flags.append("generic_nav_label")
    score -= 20
  if text in GENERIC_LINK_TEXT:
    flags.append("generic_link_text")
    score -= 5

  if candidate.action_type == "type" and not text and (candidate.input_type or "") in {
    "text",
    "email",
    "search",
    "password",
  }:
    score -= 5

  repetition_penalty = 0
  if candidates is not None:
    repetition_penalty, repetition_flags = _candidate_repetition_diagnostics(
      candidate,
      candidates=candidates,
      page_url=page_url,
      start_url=start_url,
    )
    flags.extend(repetition_flags)
    score -= repetition_penalty

  diversity_penalty = 0
  if attempted_group_counts is not None:
    diversity_penalty, diversity_flags = _candidate_diversity_diagnostics(
      group=group,
      attempted_group_counts=attempted_group_counts,
    )
    flags.extend(diversity_flags)
    score -= diversity_penalty

  if candidates is not None and attempted_strategy_counts is not None:
    strategy_penalty, strategy_flags = _candidate_strategy_diversity_diagnostics(
      candidate,
      candidates=candidates,
      attempted_strategy_counts=attempted_strategy_counts,
      route_link_count=route_link_count,
    )
    flags.extend(strategy_flags)
    score -= strategy_penalty

  return CandidatePriorityEvaluation(
    score=score,
    group=group,
    region=region,
    reason_flags=tuple(dict.fromkeys(flags)),
    repetition_penalty=repetition_penalty,
    diversity_penalty=diversity_penalty,
  )


def _candidate_priority_reason_flags(
  candidate: ActionCandidate,
  *,
  page_url: str,
  start_url: str,
  in_scope: Callable[[str], bool],
  current_route: str | None = None,
  candidates: Sequence[ActionCandidate] | None = None,
  attempted_group_counts: Mapping[str, int] | None = None,
  attempted_strategy_counts: Mapping[str, int] | None = None,
  route_visit_counts: Mapping[str, int] | None = None,
  route_pair_counts: Mapping[RoutePair, int] | None = None,
) -> tuple[str, ...]:
  return _evaluate_candidate_priority(
    candidate,
    page_url=page_url,
    start_url=start_url,
    in_scope=in_scope,
    current_route=current_route,
    candidates=candidates,
    attempted_group_counts=attempted_group_counts,
    attempted_strategy_counts=attempted_strategy_counts,
    route_visit_counts=route_visit_counts,
    route_pair_counts=route_pair_counts,
  ).reason_flags


def _candidate_priority_score(
  candidate: ActionCandidate,
  *,
  page_url: str,
  start_url: str,
  in_scope: Callable[[str], bool],
  current_route: str | None = None,
  candidates: Sequence[ActionCandidate] | None = None,
  attempted_group_counts: Mapping[str, int] | None = None,
  attempted_strategy_counts: Mapping[str, int] | None = None,
  route_visit_counts: Mapping[str, int] | None = None,
  route_pair_counts: Mapping[RoutePair, int] | None = None,
) -> int:
  return _evaluate_candidate_priority(
    candidate,
    page_url=page_url,
    start_url=start_url,
    in_scope=in_scope,
    current_route=current_route,
    candidates=candidates,
    attempted_group_counts=attempted_group_counts,
    attempted_strategy_counts=attempted_strategy_counts,
    route_visit_counts=route_visit_counts,
    route_pair_counts=route_pair_counts,
  ).score
