"""Turn a system's findings into one prediction per benchmark case (evaluation protocol: docs/evaluation.md).

- Page-level types (page title, page language) match by state.
- Element-level types match by selector or XPath, else role + accessible name, else box overlap (IoU >= 0.5).
- Forward cases match on the control in the source state (the case's locator already points there).
- Type match: strict = same mapped type (primary); lenient = same WCAG success criterion (secondary).
Several findings on one case keep the strongest verdict: violation > uncertain > no_violation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PAGE_LEVEL_TYPES = frozenset({"page-title-not-descriptive", "lang-mismatch"})
STRENGTH = {"violation": 3, "uncertain": 2, "no_violation": 1, "error": 0, "not_applicable": 0}
BOX_OVERLAP_THRESHOLD = 0.5


@dataclass(frozen=True)
class Locator:
  state_key: str
  candidate_type: str
  success_criteria: tuple[str, ...] = ()
  selector: str = ""
  xpath: str = ""
  role: str = ""
  name: str = ""
  bbox: tuple[float, float, float, float] | None = None  # x, y, width, height


@dataclass(frozen=True)
class Finding:
  locator: Locator
  verdict: str = "violation"


def _norm_space(text: str) -> str:
  return re.sub(r"\s+", " ", text or "").strip()


def normalize_selector(selector: str) -> str:
  return re.sub(r"\s*([>+~])\s*", r"\1", _norm_space(selector))


def normalize_xpath(xpath: str) -> str:
  value = _norm_space(xpath).lower().replace("[1]", "")
  return value.rstrip("/")


def normalize_name(name: str) -> str:
  return _norm_space(name).casefold()


def box_iou(a, b) -> float:
  if not a or not b:
    return 0.0
  ax, ay, aw, ah = a
  bx, by, bw, bh = b
  ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
  iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
  inter = ix * iy
  union = aw * ah + bw * bh - inter
  return inter / union if union > 0 else 0.0


def types_match(case: Locator, finding: Locator, *, lenient: bool = False) -> bool:
  if case.candidate_type and case.candidate_type == finding.candidate_type:
    return True
  if lenient:
    return bool(set(case.success_criteria) & set(finding.success_criteria))
  return False


def element_match(case: Locator, finding: Locator) -> str | None:
  """Name of the rule that matched, or None. Rules are tried in the order the spec gives."""
  if case.selector and finding.selector and normalize_selector(case.selector) == normalize_selector(finding.selector):
    return "selector"
  if case.xpath and finding.xpath and normalize_xpath(case.xpath) == normalize_xpath(finding.xpath):
    return "xpath"
  if (case.role and case.name and finding.role and finding.name
      and case.role.lower() == finding.role.lower() and normalize_name(case.name) == normalize_name(finding.name)):
    return "role_name"
  if box_iou(case.bbox, finding.bbox) >= BOX_OVERLAP_THRESHOLD:
    return "box_overlap"
  return None


def matches(case: Locator, finding: Locator, *, lenient: bool = False) -> str | None:
  if case.state_key != finding.state_key or not types_match(case, finding, lenient=lenient):
    return None
  if case.candidate_type in PAGE_LEVEL_TYPES:
    return "state"
  return element_match(case, finding)


def predict_cases(
  cases: dict[str, Locator],
  findings: list[Finding],
  *,
  lenient: bool = False,
  unmatched: str = "no_violation",
) -> dict[str, tuple[str, str]]:
  """case_id -> (prediction, matched_by). `unmatched` is no_violation for tools that only report findings,
  not_applicable for systems that judge per candidate (no candidate = the case was never judged)."""
  result: dict[str, tuple[str, str]] = {}
  for case_id, locator in cases.items():
    best, how = unmatched, ""
    for finding in findings:
      rule = matches(locator, finding.locator, lenient=lenient)
      if rule and STRENGTH.get(finding.verdict, 0) > STRENGTH.get(best, 0):
        best, how = finding.verdict, rule
    result[case_id] = (best, how)
  return result
