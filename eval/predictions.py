"""Case-level prediction rows and gold cases (evaluation protocol: docs/evaluation.md).

Every reported number is computed from these CSV files, so each one traces back to a run id.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Iterable

PREDICTIONS = ("violation", "no_violation", "uncertain", "not_applicable", "error")
EXPECTED = ("violation", "no_violation")
DIRECTIONS = ("none", "backward", "forward")
EVIDENCE_SCOPES = ("", "state", "incoming", "outgoing")
REGIMES = ("", "R1", "R2")
SPLITS = ("dev", "test", "external")


@dataclass(frozen=True)
class PredictionRow:
  run_id: str
  system: str
  config: str
  model: str
  run_idx: int
  regime: str
  dataset: str
  case_id: str
  prediction: str
  evidence_scope: str = ""
  cost_usd: float = 0.0
  latency_s: float = 0.0
  freeze_hash: str = ""

  def __post_init__(self) -> None:
    if self.prediction not in PREDICTIONS:
      raise ValueError(f"{self.case_id}: prediction {self.prediction!r} not in {PREDICTIONS}")
    if self.evidence_scope not in EVIDENCE_SCOPES:
      raise ValueError(f"{self.case_id}: evidence_scope {self.evidence_scope!r} not in {EVIDENCE_SCOPES}")
    if self.regime not in REGIMES:
      raise ValueError(f"{self.case_id}: regime {self.regime!r} not in {REGIMES}")


@dataclass(frozen=True)
class GoldCase:
  """One labelled benchmark item. `subgroup` refines direction (e.g. forward-link vs forward-button-widget)."""
  dataset: str
  case_id: str
  app: str
  candidate_type: str
  expected: str
  direction: str = "none"
  subgroup: str = ""
  case_kind: str = ""
  requires_input: bool = False
  depth: int = 0
  split: str = "test"
  page_level: bool = False

  def __post_init__(self) -> None:
    if self.expected not in EXPECTED:
      raise ValueError(f"{self.case_id}: expected {self.expected!r} not in {EXPECTED}")
    if self.direction not in DIRECTIONS:
      raise ValueError(f"{self.case_id}: direction {self.direction!r} not in {DIRECTIONS}")
    if self.split not in SPLITS:
      raise ValueError(f"{self.case_id}: split {self.split!r} not in {SPLITS}")


def _coerce(cls, row: dict[str, str]):
  kwargs = {}
  for f in fields(cls):
    if f.name not in row:
      continue
    value = row[f.name]
    if f.type in ("int", int):
      kwargs[f.name] = int(value or 0)
    elif f.type in ("float", float):
      kwargs[f.name] = float(value or 0.0)
    elif f.type in ("bool", bool):
      kwargs[f.name] = str(value).strip().lower() in {"1", "true", "yes"}
    else:
      kwargs[f.name] = value
  return cls(**kwargs)


def write_rows(path: Path, rows: Iterable[PredictionRow | GoldCase]) -> Path:
  rows = list(rows)
  path.parent.mkdir(parents=True, exist_ok=True)
  cls = type(rows[0]) if rows else PredictionRow
  with path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=[f.name for f in fields(cls)])
    writer.writeheader()
    for row in rows:
      writer.writerow(asdict(row))
  return path


def read_predictions(path: Path) -> list[PredictionRow]:
  with path.open(encoding="utf-8", newline="") as handle:
    return [_coerce(PredictionRow, row) for row in csv.DictReader(handle)]


def read_gold(path: Path) -> list[GoldCase]:
  with path.open(encoding="utf-8", newline="") as handle:
    return [_coerce(GoldCase, row) for row in csv.DictReader(handle)]


def check_complete(gold: list[GoldCase], rows: list[PredictionRow]) -> list[str]:
  """Problems that would make a score misleading: missing, duplicate or unknown case ids per run."""
  problems: list[str] = []
  gold_ids = {g.case_id for g in gold}
  by_run: dict[tuple[str, str, int], list[str]] = {}
  for row in rows:
    by_run.setdefault((row.run_id, row.system, row.run_idx), []).append(row.case_id)
  for key, ids in sorted(by_run.items()):
    seen = set(ids)
    if len(seen) != len(ids):
      problems.append(f"{key}: duplicate case ids")
    if missing := gold_ids - seen:
      problems.append(f"{key}: {len(missing)} gold cases without a prediction")
    if unknown := seen - gold_ids:
      problems.append(f"{key}: {len(unknown)} predictions for unknown cases")
  return problems
