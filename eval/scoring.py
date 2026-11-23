"""Metrics on case-level predictions (evaluation protocol: docs/evaluation.md).

Uncertain is reported three ways: strict (uncertain = negative), selective (metrics on committed verdicts only,
plus coverage) and triage (uncertain = positive). not_applicable and error count as negative in the overall
view and are excluded in the coverage view; coverage is always reported.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Callable, Iterable

from .predictions import GoldCase

VIEWS = ("strict", "selective", "triage", "coverage")


@dataclass(frozen=True)
class Metrics:
  n: int
  n_scored: int
  tp: int
  fp: int
  fn: int
  tn: int
  precision: float | None
  recall: float | None
  f1: float | None
  fdr: float | None
  abstention: float | None
  coverage: float | None

  def as_dict(self) -> dict:
    return asdict(self)


def _ratio(num: int, den: int) -> float | None:
  return num / den if den else None


def positive_under(prediction: str, view: str) -> bool | None:
  """True/False = scored as positive/negative; None = left out of this view."""
  if prediction == "violation":
    return True
  if prediction == "no_violation":
    return False
  if prediction == "uncertain":
    return {"strict": False, "triage": True, "selective": None, "coverage": False}[view]
  # not_applicable / error
  return None if view in ("coverage", "selective") else False


def score(pairs: Iterable[tuple[str, str]], view: str = "strict") -> Metrics:
  """`pairs` = (expected, prediction) per case."""
  if view not in VIEWS:
    raise ValueError(f"view must be one of {VIEWS}")
  tp = fp = fn = tn = n = n_scored = uncertain = committed = 0
  for expected, prediction in pairs:
    n += 1
    uncertain += prediction == "uncertain"
    committed += prediction in ("violation", "no_violation")
    pos = positive_under(prediction, view)
    if pos is None:
      continue
    n_scored += 1
    truth = expected == "violation"
    tp += pos and truth
    fp += pos and not truth
    fn += (not pos) and truth
    tn += (not pos) and not truth
  precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
  f1 = (2 * precision * recall / (precision + recall)) if precision and recall else (0.0 if tp + fp + fn else None)
  return Metrics(n, n_scored, tp, fp, fn, tn, precision, recall, f1, _ratio(fp, tp + fp),
                 _ratio(uncertain, n), _ratio(committed, n))


def join(gold: list[GoldCase], predictions: dict[str, str]) -> list[tuple[GoldCase, str]]:
  """Pair every gold case with its prediction; a missing prediction is an error, never silently dropped."""
  return [(case, predictions.get(case.case_id, "error")) for case in gold]


def score_cases(joined: list[tuple[GoldCase, str]], view: str = "strict") -> Metrics:
  return score(((case.expected, prediction) for case, prediction in joined), view)


BREAKDOWNS: dict[str, Callable[[GoldCase], str]] = {
  "type": lambda c: c.candidate_type,
  "direction": lambda c: c.direction,
  "subgroup": lambda c: c.subgroup or c.direction,
  "requires_input": lambda c: "requires_input" if c.requires_input else "no_input",
  "depth": lambda c: "depth_0" if c.depth == 0 else ("depth_1" if c.depth == 1 else "depth_2+"),
  "app": lambda c: c.app,
}


def breakdown(joined: list[tuple[GoldCase, str]], by: str, view: str = "strict") -> dict[str, Metrics]:
  groups: dict[str, list[tuple[GoldCase, str]]] = defaultdict(list)
  for case, prediction in joined:
    groups[BREAKDOWNS[by](case)].append((case, prediction))
  return {key: score_cases(items, view) for key, items in sorted(groups.items())}


def recall_on_positives(joined: list[tuple[GoldCase, str]], view: str = "strict") -> float | None:
  return score_cases([(c, p) for c, p in joined if c.expected == "violation"], view).recall
