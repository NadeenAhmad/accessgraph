"""Budget guard (evaluation protocol: docs/evaluation.md).

A persistent ledger keeps the running total of real LLM spend across all runs. Paid calls stop at $18
(the last $2 of the $20 budget is reserve) and at each stage's cap; going past either needs the PI.
Cache hits cost nothing and are not charged.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOTAL_BUDGET_USD = 20.0
HARD_STOP_USD = 22.0  # PI 2026-11-19 ~16:35: raised from $18 to $22 (round 5 final runs)
STAGE_CAPS_USD: dict[str, float] = {
  "dev": 1.5,                  # Step 3: dev check and one round of fixes
  "dev_intera11y": 1.5,        # PI-approved 2026-11-13: early InterA11y comparison on dev, from the reserve
  "external": 1.5,             # D2, D3, D6
  "d5": 2.0,                   # explore 10 apps, judge 600
  "d1_explore": 1.5,
  "d1_accessgraph": 4.0,       # AG-main x3, ablations, re-judge, extra-findings sample
  "d1_baselines": 3.0,         # single-state baselines and Rampa
  "d1_intera11y_plus": 2.5,
  "dev_round2": 4.5,           # PI-approved 2026-11-16 ($3) and 2026-11-17 (+$1.5): fix rounds after the external runs (dev re-check,
                               # practice cases, re-runs of D2/D3/D6 with the improved system)
  "phase1_explore": 0.8,       # PI 2026-11-17: block A+B (exploring like a user, seeing everything): build checks
  "phase2_judge": 1.0,         # PI 2026-11-17: block C+D+E (judge with tools, logins, new types, axe row)
  "phase3_final": 6.5,         # PI 2026-11-17: fresh final runs with freeze v6 (D2 x3, D3/D6, D5)
  "fix_round4": 7.4,           # PI 2026-11-18 ~19:55: fixes 1-13 (+ test 14/15), checks on all sets, freeze v12 and
                               # final runs; run until the balance (~$7.37) runs out; the $18 hard stop still applies
  "fix_round5": 6.95,          # PI 2026-11-19 ~14:00: all round-5 fixes, checks and final runs; ~16:35 PI raised the
                               # hard stop to $22, so the stage may use what is left under it
  "d5_review": 0.3,            # PI 2026-11-23: one-sentence plain versions of the D5 verdict explanations (reveal step)
  "d5_final": 1.5,             # PI 2026-11-23 (option A): re-judge the D5 sample with the final version (v13)
  "tiny": 0.0,                 # --tiny never pays
}
# The eval scripts read the OpenRouter key from the file the PI created (outside the repo, never printed).
_KEY_FILE = Path.home() / ".config" / "w4a" / "openrouter.env"
if "OPENROUTER_API_KEY" not in os.environ and "OPENROUTER_ENV_FILE" not in os.environ and _KEY_FILE.exists():
  os.environ["OPENROUTER_ENV_FILE"] = str(_KEY_FILE)

DEFAULT_LEDGER = Path("results/cost_ledger.json")


class BudgetExceeded(RuntimeError):
  pass


@dataclass(frozen=True)
class Estimate:
  calls: int
  input_tokens_per_call: int
  output_tokens_per_call: int
  input_usd_per_million: float
  output_usd_per_million: float
  cache_hit_rate: float = 0.0

  @property
  def usd(self) -> float:
    per_call = (self.input_tokens_per_call * self.input_usd_per_million
                + self.output_tokens_per_call * self.output_usd_per_million) / 1_000_000
    return per_call * self.calls * (1.0 - self.cache_hit_rate)


class CostLedger:
  def __init__(self, path: Path = DEFAULT_LEDGER, *, hard_stop: float = HARD_STOP_USD,
               stage_caps: dict[str, float] | None = None):
    self.path = Path(path)
    self.hard_stop = hard_stop
    self.stage_caps = dict(STAGE_CAPS_USD if stage_caps is None else stage_caps)
    self.state: dict[str, Any] = {"total_usd": 0.0, "stages": {}, "entries": 0}
    self._reload()

  def _reload(self) -> None:
    """Re-read the shared ledger, so several processes (judge, explorer, InterA11y) never undercount."""
    if self.path.exists():
      self.state = json.loads(self.path.read_text(encoding="utf-8"))

  @property
  def total(self) -> float:
    return float(self.state["total_usd"])

  def stage_total(self, stage: str) -> float:
    return float(self.state["stages"].get(stage, 0.0))

  def remaining(self, stage: str) -> float:
    if stage not in self.stage_caps:
      raise BudgetExceeded(f"unknown stage {stage!r}; caps exist for {sorted(self.stage_caps)}")
    return max(0.0, min(self.hard_stop - self.total, self.stage_caps[stage] - self.stage_total(stage)))

  def check(self, stage: str, planned_usd: float = 0.0) -> None:
    self._reload()
    left = self.remaining(stage)
    if planned_usd > left + 1e-12 or (planned_usd == 0.0 and left <= 0.0):
      raise BudgetExceeded(
        f"stage {stage!r} would exceed its budget: planned ${planned_usd:.4f}, left ${left:.4f} "
        f"(stage ${self.stage_total(stage):.4f}/{self.stage_caps[stage]:.2f}, total ${self.total:.4f}/{self.hard_stop:.2f}). "
        "Stop and ask the PI."
      )

  def charge(self, stage: str, usd: float, *, run_id: str = "", note: str = "") -> None:
    if usd <= 0:
      return
    import fcntl
    self.path.parent.mkdir(parents=True, exist_ok=True)
    with self.path.with_suffix(".lock").open("a") as lock:
      fcntl.flock(lock, fcntl.LOCK_EX)
      self._reload()
      self._charge_locked(stage, usd, run_id=run_id, note=note)

  def _charge_locked(self, stage: str, usd: float, *, run_id: str, note: str) -> None:
    self.state["total_usd"] = self.total + usd
    self.state["stages"][stage] = self.stage_total(stage) + usd
    self.state["entries"] = int(self.state.get("entries", 0)) + 1
    self.state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = self.path.with_suffix(".tmp")
    tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(self.path)
    with self.path.with_name("cost_log.jsonl").open("a", encoding="utf-8") as log:
      log.write(json.dumps({"at": self.state["updated_at"], "stage": stage, "usd": usd, "run_id": run_id,
                            "note": note}) + "\n")

  def dry_run(self, stage: str, estimate: Estimate) -> str:
    left = self.remaining(stage)
    verdict = "OK" if estimate.usd <= left else "OVER BUDGET - ask the PI"
    return (f"[dry-run] stage={stage} calls={estimate.calls} est=${estimate.usd:.4f} left=${left:.4f} -> {verdict}")


class BudgetedClient:
  """Wraps any confirmation client: refuses to start a paid call once the stage or total budget is spent,
  and charges the ledger with each response's cost. Responses without a known cost are refused for paid
  providers, so spend can never go untracked."""

  def __init__(self, inner: Any, ledger: CostLedger, stage: str, *, run_id: str = "",
               max_call_usd: float = 0.05):
    self.inner = inner
    self.provider = inner.provider
    self.model = inner.model
    self.ledger = ledger
    self.stage = stage
    self.run_id = run_id
    self.max_call_usd = max_call_usd
    self.spent = 0.0
    self.calls = 0

  # W4A round 5: OpenRouter answers "servers overloaded" (HTTP 502/503/429) at busy times; such a call is retried
  # after a pause instead of becoming an "uncertain" verdict (infrastructure, not part of the frozen system)
  RETRY_PAUSES_S = (5, 10, 20, 30, 45, 60)

  def _confirm_with_retries(self, prompt):
    import re
    import time as _time
    for pause in (*self.RETRY_PAUSES_S, None):
      try:
        return self.inner.confirm(prompt)
      except RuntimeError as error:
        transient = re.search(r"HTTP error (429|50[0-4])\b", str(error)) or "overloaded" in str(error).lower()
        if pause is None or not transient:
          raise
        _time.sleep(pause)

  def confirm(self, prompt):
    paid = self.provider != "fake"
    if paid:
      self.ledger.check(self.stage, planned_usd=self.max_call_usd)
    response = self._confirm_with_retries(prompt)
    self.calls += 1
    cost = response.estimated_cost_usd
    cache = (response.provider_metadata or {}).get("response_cache") or {}
    if paid and cost is None and not cache.get("hit"):
      raise BudgetExceeded(f"{self.provider}/{self.model} returned no cost; add its price before paid runs")
    if cost:
      self.spent += cost
      self.ledger.charge(self.stage, cost, run_id=self.run_id, note=f"{self.provider}/{self.model}")
    return response


class TopUpNeeded(RuntimeError):
  """The OpenRouter balance is below what the next step needs: stop and ask the PI to top up."""


def preflight(ledger: CostLedger, stage: str, estimate_usd: float, *, balance: dict | None = None,
              margin: float = 1.2) -> str:
  """Check, before a paid step, both our budget (ledger) and the live OpenRouter balance (free call).

  Raises BudgetExceeded (our $18 / stage caps) or TopUpNeeded (account or key credit). Returns a summary line.
  """
  ledger.check(stage, planned_usd=estimate_usd)
  if balance is None:
    from src.analysis.confirmation.providers.openrouter import openrouter_balance

    balance = openrouter_balance()
  available = balance.get("available_usd")
  needed = estimate_usd * margin
  if available is not None and available < needed:
    raise TopUpNeeded(
      f"OpenRouter has ${available:.2f} available (account ${balance.get('account_remaining_usd') or 0:.2f}, "
      f"key ${balance.get('key_remaining_usd') or 0:.2f}); stage {stage!r} needs about ${needed:.2f}. "
      f"Top up at least ${needed - available:.2f} (and raise the key limit if the key is the limit)."
    )
  return (f"[preflight] stage={stage} estimate=${estimate_usd:.4f} budget_left=${ledger.remaining(stage):.4f} "
          f"openrouter_available=${available if available is not None else float('nan'):.2f} -> OK")


def rebuild_ledger_from_log(path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
  """Recompute the ledger totals from the append-only cost_log.jsonl (the source of truth for every charge)."""
  stages: dict[str, float] = {}
  entries = 0
  log = Path(path).with_name("cost_log.jsonl")
  for line in log.read_text(encoding="utf-8").splitlines() if log.exists() else []:
    if line.strip():
      row = json.loads(line)
      stages[row["stage"]] = stages.get(row["stage"], 0.0) + float(row["usd"])
      entries += 1
  state = {"total_usd": sum(stages.values()), "stages": stages, "entries": entries,
           "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rebuilt_from_log": True}
  import fcntl
  with Path(path).with_suffix(".lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    Path(path).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  return state
