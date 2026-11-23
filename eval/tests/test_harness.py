"""Unit tests for the evaluation harness (offline, no paid calls)."""
from __future__ import annotations

import json
import re
import types
from pathlib import Path

import pytest

from eval import stats
from eval.cost import BudgetedClient, BudgetExceeded, CostLedger, Estimate
from eval.freeze import FrozenFileChanged, verify_freeze, write_freeze
from eval.matching import Finding, Locator, box_iou, predict_cases
from eval.predictions import GoldCase, PredictionRow, check_complete, read_predictions, write_rows
from eval.run import run_tiny
from eval.scoring import score
from src.analysis.confirmation.models import ConfirmationProviderResponse

REPO = Path(__file__).resolve().parents[2]


# --- matching ---------------------------------------------------------------------------------------------

def test_element_matching_order_and_rules():
  case = Locator("s1", "link-text-mismatch", selector="nav > a.more", xpath="/html/body/nav/a[2]",
                 role="link", name="Read more", bbox=(0, 0, 100, 20))
  assert predict_cases({"c": case}, [Finding(Locator("s1", "link-text-mismatch", selector="nav>a.more"))])["c"] == ("violation", "selector")
  assert predict_cases({"c": case}, [Finding(Locator("s1", "link-text-mismatch", xpath="/HTML/body/nav/a[2]/"))])["c"][1] == "xpath"
  assert predict_cases({"c": case}, [Finding(Locator("s1", "link-text-mismatch", role="LINK", name=" read  more "))])["c"][1] == "role_name"
  assert predict_cases({"c": case}, [Finding(Locator("s1", "link-text-mismatch", bbox=(10, 0, 100, 20)))])["c"][1] == "box_overlap"
  # wrong state, wrong type, too little overlap, visible text alone: no match
  for finding in (Locator("s2", "link-text-mismatch", selector="nav>a.more"),
                  Locator("s1", "button-label-mismatch", selector="nav>a.more"),
                  Locator("s1", "link-text-mismatch", bbox=(60, 0, 100, 20)),
                  Locator("s1", "link-text-mismatch", name="Read more")):
    assert predict_cases({"c": case}, [Finding(finding)])["c"] == ("no_violation", "")


def test_page_level_strongest_verdict_lenient_and_unmatched():
  case = Locator("s1", "page-title-not-descriptive", success_criteria=("2.4.2",))
  findings = [Finding(Locator("s1", "page-title-not-descriptive"), "uncertain"),
              Finding(Locator("s1", "page-title-not-descriptive"), "violation")]
  assert predict_cases({"c": case}, findings)["c"] == ("violation", "state")
  other_type = [Finding(Locator("s1", "x-title", success_criteria=("2.4.2",)))]
  assert predict_cases({"c": case}, other_type)["c"][0] == "no_violation"
  assert predict_cases({"c": case}, other_type, lenient=True)["c"][0] == "violation"
  assert predict_cases({"c": case}, [], unmatched="not_applicable")["c"] == ("not_applicable", "")
  assert box_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0 and box_iou(None, (0, 0, 1, 1)) == 0.0


# --- scoring ----------------------------------------------------------------------------------------------

def test_scoring_views():
  pairs = [("violation", "violation"), ("violation", "uncertain"), ("no_violation", "uncertain"),
           ("no_violation", "no_violation"), ("violation", "not_applicable"), ("no_violation", "violation")]
  strict, triage, selective, coverage = (score(pairs, v) for v in ("strict", "triage", "selective", "coverage"))
  assert (strict.tp, strict.fp, strict.fn, strict.tn) == (1, 1, 2, 2)
  assert (triage.tp, triage.fp, triage.fn, triage.tn) == (2, 2, 1, 1)
  assert selective.n_scored == 3 and selective.coverage == pytest.approx(0.5)
  assert coverage.n_scored == 5 and strict.abstention == pytest.approx(2 / 6)
  assert strict.fdr == pytest.approx(0.5) and strict.recall == pytest.approx(1 / 3)
  assert score([("violation", "no_violation")]).f1 == 0.0 and score([]).f1 is None


def test_prediction_rows_roundtrip_and_completeness(tmp_path):
  gold = [GoldCase("d1", "a", "app", "heading-not-descriptive", "violation", direction="backward"),
          GoldCase("d1", "b", "app", "heading-not-descriptive", "no_violation", direction="backward")]
  rows = [PredictionRow("r1", "ag", "main", "m", 0, "R2", "d1", "a", "violation", "incoming", 0.001, 1.5, "fh")]
  path = write_rows(tmp_path / "p.csv", rows)
  back = read_predictions(path)
  assert back == rows
  assert check_complete(gold, back) == ["('r1', 'ag', 0): 1 gold cases without a prediction"]
  with pytest.raises(ValueError):
    PredictionRow("r1", "ag", "main", "m", 0, "R2", "d1", "a", "maybe")
  with pytest.raises(ValueError):
    GoldCase("d1", "c", "app", "t", "violation", direction="sideways")


# --- statistics -------------------------------------------------------------------------------------------

def test_statistics_known_values():
  lo, hi = stats.wilson_ci(2, 5)
  assert lo == pytest.approx(0.1176, abs=1e-4) and hi == pytest.approx(0.7693, abs=1e-4)
  assert stats.wilson_ci(0, 0) is None
  assert stats.mcnemar_exact(1, 4) == pytest.approx(0.375)
  assert stats.mcnemar_exact(0, 0) == 1.0
  assert stats.holm({"a": 0.01, "b": 0.04, "c": 0.03}) == {"a": 0.03, "c": 0.06, "b": 0.06}
  assert stats.cohen_kappa("vnvn", "vnnn") == pytest.approx(0.5)
  assert stats.fleiss_kappa([["v", "v", "n"], ["n", "n", "n"], ["v", "v", "v"]]) == pytest.approx(0.55)
  assert stats.flip_rate([["v", "n", "v"], ["v", "v", "v"]]) == pytest.approx(1 / 3)
  assert stats.jaccard({1, 2}, {2, 3}) == pytest.approx(1 / 3)
  mean, sd = stats.mean_sd([1.0, 2.0, 3.0])
  assert mean == 2.0 and sd == pytest.approx(1.0)


def test_permutation_and_bootstrap_are_seeded_and_sensible():
  mean = lambda xs: sum(xs) / len(xs) if xs else None
  same = [(1, 1)] * 20
  assert stats.paired_permutation_test(same, mean, replicates=500)[1] == 1.0
  better = [(1, 0)] * 15 + [(0, 0)] * 5
  diff, p = stats.paired_permutation_test(better, mean, replicates=2000)
  assert diff == pytest.approx(0.75) and p < 0.001
  items = [("a", 1), ("a", 0), ("b", 1), ("b", 1), ("c", 0)]
  first = stats.cluster_bootstrap(items, lambda x: x[0], lambda xs: mean([v for _, v in xs]), replicates=300)
  again = stats.cluster_bootstrap(items, lambda x: x[0], lambda xs: mean([v for _, v in xs]), replicates=300)
  assert first == again and first[1] <= first[0] <= first[2]


# --- budget guard, cache, freeze --------------------------------------------------------------------------

class _PaidStub:
  provider, model = "anthropic", "claude-haiku-5-5"

  def __init__(self, cost):
    self.cost = cost

  def confirm(self, prompt):
    return ConfirmationProviderResponse(self.provider, self.model, "{}", estimated_cost_usd=self.cost)


def test_ledger_caps_and_hard_stop(tmp_path):
  ledger = CostLedger(tmp_path / "ledger.json", stage_caps={"dev": 1.0, "d5": 5.0}, hard_stop=1.5)
  client = BudgetedClient(_PaidStub(0.4), ledger, "dev", max_call_usd=0.05)
  client.confirm(None)
  client.confirm(None)
  assert ledger.total == pytest.approx(0.8)
  assert CostLedger(tmp_path / "ledger.json").total == pytest.approx(0.8)  # persisted
  client.confirm(None)  # 1.2 > stage cap only after the call; the next one is refused
  with pytest.raises(BudgetExceeded):
    client.confirm(None)
  with pytest.raises(BudgetExceeded):  # hard stop: 1.2 spent, 0.3 left overall, stage d5 has room
    ledger.check("d5", planned_usd=0.5)
  with pytest.raises(BudgetExceeded):
    ledger.check("unknown-stage")
  with pytest.raises(BudgetExceeded):  # paid response without a price is never accepted
    BudgetedClient(_PaidStub(None), CostLedger(tmp_path / "l2.json"), "dev").confirm(None)
  assert "OVER BUDGET" in ledger.dry_run("dev", Estimate(1000, 5000, 300, 0.10, 0.50))
  assert Estimate(1000, 5000, 300, 0.10, 0.50, cache_hit_rate=0.5).usd == pytest.approx(0.325)


def test_freeze_detects_changed_missing_and_added(tmp_path):
  (tmp_path / "src").mkdir()
  (tmp_path / "src" / "a.py").write_text("1")
  record = write_freeze(["src/*.py"], {"model": "m"}, root=tmp_path, path=tmp_path / "F.json")
  assert verify_freeze(root=tmp_path, path=tmp_path / "F.json") == record["freeze_hash"]
  (tmp_path / "src" / "b.py").write_text("2")
  with pytest.raises(FrozenFileChanged, match="added: src/b.py"):
    verify_freeze(root=tmp_path, path=tmp_path / "F.json")


def test_tiny_end_to_end(tmp_path):
  report = run_tiny(tmp_path)
  assert report["run2"] == {"model_calls": 0, "cache_hits": 6}
  assert report["freeze_guard"] == "ok" and report["ledger_total_usd"] == 0.0
  assert (tmp_path / "results" / "run_log.csv").read_text().count(",ok,") == 2


# --- tool code stays generic ------------------------------------------------------------------------------

TOOL_DIRS = ("src/crawler", "src/analysis/candidates", "src/analysis/confirmation")
FORBIDDEN = re.compile(r"(co|bk|cp|fp)-sem-\d|checkout-flow|booking-scheduler|course-portal|finance-portal|"
                       r"benchmark-case-registry|variant_id|expected_human_judgment|__ACCESSGRAPH_|"
                       r"^\s*(from|import)\s+eval\b", re.IGNORECASE | re.MULTILINE)


def test_tool_code_has_no_benchmark_knowledge():
  offenders = []
  for directory in TOOL_DIRS:
    for path in (REPO / directory).rglob("*"):
      if path.suffix in {".py", ".json", ".txt", ".md"} and "__pycache__" not in path.parts:
        for match in FORBIDDEN.finditer(path.read_text(encoding="utf-8", errors="ignore")):
          offenders.append(f"{path.relative_to(REPO)}: {match.group(0).strip()}")
  assert not offenders, "benchmark-specific references in tool code:\n" + "\n".join(offenders)


def test_preflight_checks_budget_and_live_balance(tmp_path):
  from eval.cost import TopUpNeeded, preflight

  ledger = CostLedger(tmp_path / "ledger.json")
  ok = preflight(ledger, "dev", 0.5, balance={"available_usd": 9.86, "account_remaining_usd": 9.86, "key_remaining_usd": 10.05})
  assert ok.endswith("OK")
  with pytest.raises(TopUpNeeded, match="Top up at least"):
    preflight(ledger, "d5", 1.9, balance={"available_usd": 1.0, "account_remaining_usd": 1.0, "key_remaining_usd": 10.0})
  with pytest.raises(BudgetExceeded):
    preflight(ledger, "dev", 5.0, balance={"available_usd": 100.0})


def test_ledger_instances_never_overwrite_each_other(tmp_path):
  from eval.cost import CostLedger
  a, b = CostLedger(tmp_path / "ledger.json"), CostLedger(tmp_path / "ledger.json")
  a.charge("dev", 0.25)
  b.charge("dev", 0.5)  # b was created before a's charge; it must not drop it
  a.charge("dev_intera11y", 0.125)
  fresh = CostLedger(tmp_path / "ledger.json")
  assert fresh.total == 0.875 and fresh.stage_total("dev") == 0.75 and fresh.state["entries"] == 3
