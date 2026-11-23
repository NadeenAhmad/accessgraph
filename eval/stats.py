"""Statistics for the paper (evaluation protocol: docs/evaluation.md). Pure Python, seeded, so every number is reproducible.

Wilson CIs, two-stage cluster bootstrap (apps, then cases), paired permutation tests, exact McNemar,
Holm-Bonferroni, Cohen's and Fleiss' kappa, flip rate and Jaccard overlap.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Callable, Hashable, Sequence, TypeVar

T = TypeVar("T")
DEFAULT_REPLICATES = 10_000
DEFAULT_SEED = 20270101


def wilson_ci(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
  if n == 0:
    return None
  p = successes / n
  denom = 1 + z * z / n
  centre = (p + z * z / (2 * n)) / denom
  half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
  return max(0.0, centre - half), min(1.0, centre + half)


def _percentile(sorted_values: Sequence[float], q: float) -> float:
  if not sorted_values:
    return float("nan")
  pos = q * (len(sorted_values) - 1)
  lo, hi = math.floor(pos), math.ceil(pos)
  return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def cluster_bootstrap(
  items: Sequence[T],
  cluster_of: Callable[[T], Hashable],
  statistic: Callable[[list[T]], float | None],
  *,
  replicates: int = DEFAULT_REPLICATES,
  seed: int = DEFAULT_SEED,
  alpha: float = 0.05,
) -> tuple[float | None, float, float]:
  """Point estimate and percentile CI: resample clusters (apps) with replacement, then items within each."""
  clusters: dict[Hashable, list[T]] = defaultdict(list)
  for item in items:
    clusters[cluster_of(item)].append(item)
  keys = sorted(clusters, key=str)
  rng = random.Random(seed)
  values: list[float] = []
  for _ in range(replicates):
    sample: list[T] = []
    for key in (rng.choice(keys) for _ in keys):
      members = clusters[key]
      sample.extend(rng.choice(members) for _ in members)
    value = statistic(sample)
    if value is not None and not math.isnan(value):
      values.append(value)
  values.sort()
  return statistic(list(items)), _percentile(values, alpha / 2), _percentile(values, 1 - alpha / 2)


def paired_permutation_test(
  pairs: Sequence[tuple[T, T]],
  statistic: Callable[[list[T]], float | None],
  *,
  replicates: int = DEFAULT_REPLICATES,
  seed: int = DEFAULT_SEED,
) -> tuple[float, float]:
  """Two-sided test of statistic(A) - statistic(B) on paired per-case outcomes, swapping A/B per case.

  `pairs` holds (outcome_A, outcome_B) for the same case. Returns (observed difference, p-value).
  """
  def diff(a_items: list[T], b_items: list[T]) -> float:
    a, b = statistic(a_items), statistic(b_items)
    return (a or 0.0) - (b or 0.0)

  observed = diff([a for a, _ in pairs], [b for _, b in pairs])
  rng = random.Random(seed)
  extreme = 0
  for _ in range(replicates):
    a_items, b_items = [], []
    for a, b in pairs:
      if rng.random() < 0.5:
        a, b = b, a
      a_items.append(a)
      b_items.append(b)
    if abs(diff(a_items, b_items)) >= abs(observed) - 1e-12:
      extreme += 1
  return observed, (extreme + 1) / (replicates + 1)


def mcnemar_exact(b: int, c: int) -> float:
  """Two-sided exact McNemar p-value; b and c are the two discordant counts."""
  n = b + c
  if n == 0:
    return 1.0
  k = min(b, c)
  tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
  return min(1.0, 2 * tail)


def holm(pvalues: dict[str, float]) -> dict[str, float]:
  """Holm-Bonferroni adjusted p-values (monotone), within one hypothesis family."""
  ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
  m, running, adjusted = len(ordered), 0.0, {}
  for rank, (name, p) in enumerate(ordered):
    running = max(running, min(1.0, (m - rank) * p))
    adjusted[name] = running
  return adjusted


def cohen_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> float | None:
  if len(a) != len(b) or not a:
    return None
  n = len(a)
  labels = set(a) | set(b)
  observed = sum(x == y for x, y in zip(a, b)) / n
  expected = sum((list(a).count(l) / n) * (list(b).count(l) / n) for l in labels)
  return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def fleiss_kappa(ratings: Sequence[Sequence[Hashable]]) -> float | None:
  """`ratings[i]` = the labels the raters gave item i (same number of raters per item)."""
  if not ratings:
    return None
  raters = len(ratings[0])
  if raters < 2 or any(len(r) != raters for r in ratings):
    return None
  labels = sorted({l for r in ratings for l in r}, key=str)
  n_items = len(ratings)
  p_items, totals = [], defaultdict(int)
  for r in ratings:
    counts = [list(r).count(l) for l in labels]
    for l, c in zip(labels, counts):
      totals[l] += c
    p_items.append((sum(c * c for c in counts) - raters) / (raters * (raters - 1)))
  p_bar = sum(p_items) / n_items
  p_e = sum((totals[l] / (n_items * raters)) ** 2 for l in labels)
  return 1.0 if p_e == 1 else (p_bar - p_e) / (1 - p_e)


def flip_rate(runs: Sequence[Sequence[Hashable]]) -> float | None:
  """Share of items whose label is not identical across all runs."""
  if not runs or not runs[0]:
    return None
  return sum(len(set(labels)) > 1 for labels in zip(*runs)) / len(runs[0])


def jaccard(a: set, b: set) -> float | None:
  union = a | b
  return len(a & b) / len(union) if union else None


def mean_sd(values: Sequence[float]) -> tuple[float, float] | None:
  if not values:
    return None
  mean = sum(values) / len(values)
  if len(values) < 2:
    return mean, 0.0
  return mean, math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
