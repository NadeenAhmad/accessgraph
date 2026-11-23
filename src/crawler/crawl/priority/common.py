from __future__ import annotations

"""Shared priority types, constants, and low-level helpers."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Mapping, Sequence
from urllib.parse import urljoin, urlparse

from ..actions import ActionCandidate

if TYPE_CHECKING:
  from ..crawl_config import CrawlConfig

ActionKey = tuple[str, ...]
RoutePair = tuple[str, str]
DISMISS_TOKENS = {"dismiss", "close", "accept", "agree", "allow", "consent"}
DISCOVERY_TOKENS = {"menu", "expand", "show", "open", "details", "filter"}
PROGRESSION_TOKENS = {"submit", "apply", "next", "continue", "proceed"}
DEMO_TOKENS = {"demo", "example", "playground", "try"}
CLIPBOARD_TOKENS = {"copy", "copy page", "copy link", "copy url", "share", "share link"}
UTILITY_SEARCH_TOKENS = {"search"}
GENERIC_LINK_TEXT = {"read more", "learn more", "more", "click here"}
NAVIGATION_LABELS = {
  "about",
  "about us",
  "blog",
  "company",
  "customers",
  "docs",
  "documentation",
  "features",
  "home",
  "pricing",
}
CONTROL_BUTTON_STRATEGIES = {"buttons", "role_button", "button_inputs"}
STRUCTURED_CONTROL_STRATEGIES = {"summary", "role_tab", "role_menuitem"}
WIDGET_CONTROL_ROLES = {"tab", "menuitem"}


@dataclass(frozen=True)
class CandidatePriorityEvaluation:
  score: int
  group: str
  region: str
  reason_flags: tuple[str, ...]
  repetition_penalty: int = 0
  diversity_penalty: int = 0


@dataclass(frozen=True)
class CandidatePriorityContext:
  page_url: str
  start_url: str
  in_scope: Callable[[str], bool]
  current_route: str = "/"
  candidates: Sequence[ActionCandidate] | None = None
  attempted_group_counts: Mapping[str, int] | None = None
  attempted_strategy_counts: Mapping[str, int] | None = None
  route_visit_counts: Mapping[str, int] | None = None
  route_pair_counts: Mapping[RoutePair, int] | None = None


def _candidate_scan_limit(cfg: CrawlConfig) -> int:
  # The heuristic scorer and the LLM policy rank actions, so they look beyond the action budget and can promote
  # useful candidates discovered later (Algorithm 1: rank SafeActions, execute the top k_max). Discovery order
  # keeps the original window.
  ranked = cfg.prioritize_action_candidates or cfg.resolved_action_policy() == "llm"
  if not ranked:
    return cfg.max_actions_per_state
  return max(cfg.max_actions_per_state * 5, cfg.max_actions_per_state)


def _replay_candidate_scan_limit(cfg: CrawlConfig) -> int:
  """
  Replay is matching one known action, not choosing among many.
  Use a wider scan window so restore does not fail just because the control
  moved later in the DOM than the normal action budget window.
  """
  return max(_candidate_scan_limit(cfg), cfg.max_actions_per_state * 10, 25)


def _text_contains_any(text: str, phrases: set[str]) -> bool:
  return any(phrase in text for phrase in phrases)


def _normalized_candidate_text(candidate: ActionCandidate) -> str:
  return " ".join(candidate.text.lower().split())


def _candidate_selection_group(candidate: ActionCandidate) -> str:
  is_link_like = candidate.action_type == "click" and (candidate.href or candidate.role == "link")
  if is_link_like and (candidate.in_header or candidate.in_nav or candidate.in_footer):
    return "global_nav_link"
  if candidate.in_main and is_link_like:
    return "main_link"
  if candidate.in_main and candidate.action_type in {"click", "select", "check", "radio"}:
    return "main_control"
  if is_link_like:
    return "link"
  if candidate.action_type == "click":
    return "control"
  return candidate.action_type


def _candidate_region(candidate: ActionCandidate) -> str:
  if candidate.in_nav:
    return "nav"
  if candidate.in_header:
    return "header"
  if candidate.in_main:
    return "main"
  if candidate.in_footer:
    return "footer"
  return "other"


def _path_segments(url: str) -> tuple[str, ...]:
  path = (urlparse(url).path or "/").strip("/")
  if not path:
    return ()
  return tuple(segment for segment in path.split("/") if segment)


def _same_document_target(page_url: str, target_url: str) -> bool:
  page_parts = urlparse(page_url)
  target_parts = urlparse(target_url)
  return (
    page_parts.scheme,
    page_parts.netloc,
    page_parts.path,
    page_parts.query,
  ) == (
    target_parts.scheme,
    target_parts.netloc,
    target_parts.path,
    target_parts.query,
  )


def _route_for_url(url: str) -> str:
  return urlparse(url).path or "/"


def _shared_path_prefix_len(left: tuple[str, ...], right: tuple[str, ...]) -> int:
  shared = 0
  for left_part, right_part in zip(left, right):
    if left_part != right_part:
      break
    shared += 1
  return shared


def _candidate_path_relevance_diagnostics(
  candidate: ActionCandidate,
  *,
  page_url: str,
  start_url: str,
) -> tuple[int, tuple[str, ...]]:
  if candidate.action_type != "click" or not candidate.href:
    return 0, ()

  target_url = urljoin(page_url, candidate.href)
  target_segments = _path_segments(target_url)
  start_segments = _path_segments(start_url)
  page_segments = _path_segments(page_url)

  if not target_segments:
    return 0, ()

  score = 0
  flags: list[str] = []

  start_shared = _shared_path_prefix_len(target_segments, start_segments)
  page_shared = _shared_path_prefix_len(target_segments, page_segments)

  if start_segments:
    if start_shared >= 3:
      score += 24
      flags.append("seed_subtree")
    elif start_shared == 2:
      score += 16
      flags.append("seed_path_family")
    elif start_shared == 1:
      score += 6
      flags.append("seed_section")
    elif len(start_segments) >= 2 and target_segments[0] != start_segments[0]:
      score -= 14
      flags.append("outside_seed_section")

  if page_segments:
    if page_shared >= 3:
      score += 18
      flags.append("current_subtree")
    elif page_shared == 2:
      score += 12
      flags.append("current_path_family")
    elif page_shared == 1 and page_segments[0] == target_segments[0]:
      score += 5
      flags.append("current_section")
    elif len(page_segments) >= 2 and target_segments[0] != page_segments[0]:
      score -= 8
      flags.append("outside_current_section")

  return score, tuple(flags)


def _evaluated_selection_group(
  candidate: ActionCandidate,
  *,
  page_url: str,
  start_url: str,
) -> str:
  group = _candidate_selection_group(candidate)
  if group != "global_nav_link" or not candidate.href:
    return group

  path_score, path_flags = _candidate_path_relevance_diagnostics(
    candidate,
    page_url=page_url,
    start_url=start_url,
  )
  local_flags = {
    "seed_subtree",
    "seed_path_family",
    "seed_section",
    "current_subtree",
    "current_path_family",
    "current_section",
  }
  outside_flags = {"outside_seed_section", "outside_current_section"}
  if path_score >= 10 and any(flag in local_flags for flag in path_flags) and not any(
    flag in outside_flags for flag in path_flags
  ):
    return "section_nav_link"
  return group


def _is_promotable_main_control(candidate: ActionCandidate) -> bool:
  if not candidate.in_main:
    return False
  if _candidate_selection_group(candidate) != "main_control":
    return False

  text = _normalized_candidate_text(candidate)
  if candidate.strategy_name in STRUCTURED_CONTROL_STRATEGIES:
    return True
  if candidate.role in WIDGET_CONTROL_ROLES:
    return True
  if candidate.aria_expanded == "false":
    return True
  if candidate.action_type in {"select", "check", "radio"}:
    return True
  if _text_contains_any(text, DISMISS_TOKENS | DISCOVERY_TOKENS | PROGRESSION_TOKENS | DEMO_TOKENS):
    return True
  return False
