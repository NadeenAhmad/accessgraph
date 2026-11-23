"""Run log and exclusions (evaluation protocol: docs/evaluation.md).

Every run that is started is logged, including failed ones; no case is ever dropped without a row in
results/exclusions.csv saying why.
"""
from __future__ import annotations

import csv
import secrets
from datetime import datetime, timezone
from pathlib import Path

RUN_LOG_FIELDS = ("run_id", "started_at", "finished_at", "status", "stage", "system", "dataset", "split",
                  "cost_usd", "freeze_hash", "command", "notes")
EXCLUSION_FIELDS = ("dataset", "case_id", "reason", "rule", "logged_at")


def _now() -> str:
  return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id(system: str, dataset: str) -> str:
  stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  return f"{dataset}-{system}-{stamp}-{secrets.token_hex(3)}"


def _append(path: Path, fields: tuple[str, ...], row: dict) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  new = not path.exists()
  with path.open("a", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    if new:
      writer.writeheader()
    writer.writerow({k: row.get(k, "") for k in fields})


class RunLog:
  def __init__(self, results_dir: Path = Path("results")):
    self.path = Path(results_dir) / "run_log.csv"
    self.exclusions = Path(results_dir) / "exclusions.csv"

  def start(self, **row) -> dict:
    row = {**row, "started_at": _now(), "status": "started"}
    _append(self.path, RUN_LOG_FIELDS, row)
    return row

  def finish(self, row: dict, *, status: str, cost_usd: float = 0.0, notes: str = "") -> None:
    _append(self.path, RUN_LOG_FIELDS, {**row, "finished_at": _now(), "status": status,
                                        "cost_usd": f"{cost_usd:.6f}", "notes": notes})

  def exclude(self, dataset: str, case_id: str, reason: str, rule: str = "") -> None:
    _append(self.exclusions, EXCLUSION_FIELDS, {"dataset": dataset, "case_id": case_id, "reason": reason,
                                                "rule": rule, "logged_at": _now()})
