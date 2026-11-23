"""Evaluation entry point.

  python -m eval.run --tiny      end-to-end check of the whole harness, no paid calls, no network

--tiny writes a synthetic recorded run, judges it with AccessGraph's real confirmation runner through the
response cache and the budget guard (scripted offline model), turns the verdicts into case-level prediction
rows, scores them in every view, runs every statistic, and checks the freeze guard. Later stages add their
own subcommands here.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from src.analysis.confirmation.models import ConfirmationConfig, ConfirmationProviderResponse
from src.analysis.confirmation.providers.caching import CachingConfirmationClient
from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation

from . import stats
from .cost import BudgetedClient, BudgetExceeded, CostLedger
from .freeze import FrozenFileChanged, verify_freeze, write_freeze
from .matching import Finding, Locator, predict_cases
from .predictions import GoldCase, PredictionRow, check_complete, read_predictions, write_rows
from .runlog import RunLog, new_run_id
from .scoring import breakdown, join, score_cases


class ScriptedClient:
  """Offline stand-in model: returns a fixed decision per candidate id. provider='fake' = never charged."""
  provider = "fake"

  def __init__(self, decisions: dict[str, str], model: str = "scripted-tiny", cost: float | None = None):
    self.decisions, self.model, self.cost, self.calls = decisions, model, cost, 0

  def confirm(self, prompt):
    self.calls += 1
    bundle = prompt.bundle
    content = json.dumps({"candidate_id": bundle.candidate_id, "candidate_type": bundle.candidate_type,
                          "state_id": bundle.state_id, "decision": self.decisions[bundle.candidate_id],
                          "confidence": 0.9, "reason": "scripted", "supporting_evidence": ["candidate_type"]})
    return ConfirmationProviderResponse(provider=self.provider, model=self.model, raw_content=content,
                                        runtime_ms=0, token_usage=None, estimated_cost_usd=self.cost)


TINY_CASES = [  # case_id, app, type, expected, direction, subgroup, candidate_id, state, selector, decision
  ("t-01", "app-a", "heading-not-descriptive", "violation", "backward", "backward", "c01", "state_0002", "#h1", "violation"),
  ("t-02", "app-a", "heading-not-descriptive", "no_violation", "backward", "backward", "c02", "state_0003", "#h1", "no_violation"),
  ("t-03", "app-a", "button-label-mismatch", "violation", "forward", "forward-button-widget", "c03", "state_0001", "#b1", "uncertain"),
  ("t-04", "app-b", "link-text-mismatch", "violation", "forward", "forward-link", "c04", "state_0001", "#l1", "violation"),
  ("t-05", "app-b", "link-text-mismatch", "no_violation", "none", "", "c05", "state_0004", "#l2", "violation"),
  ("t-06", "app-b", "page-title-not-descriptive", "violation", "none", "", "c06", "state_0005", "", "no_violation"),
  ("t-07", "app-b", "image-alt-not-descriptive", "violation", "none", "", None, "state_0006", "#img", None),
]


def _candidate(candidate_id: str, candidate_type: str, state_id: str, selector: str) -> dict:
  return {
    "schema_version": "1", "candidate_id": candidate_id, "candidate_type": candidate_type, "state_id": state_id,
    "element_refs": [{"bucket": "buttons", "element_id": f"{candidate_id}-el", "selector": selector}],
    "selection_reason": ["tiny"], "required_context": ["element evidence"],
    "evidence": {"sample": {"text": candidate_type}, "dom_snippets": [{"element_id": f"{candidate_id}-el",
                 "selector": selector or "html", "html": "<span>x</span>"}]},
    "state_context": {"url": "http://127.0.0.1/", "title": "Tiny", "depth": 1},
    "graph_context": {"transition_path": []}, "artifact_refs": {},
    "generator": {"name": "offline_semantic_candidate_builder", "version": "1"},
  }


def run_tiny(workdir: Path) -> dict:
  results = workdir / "results"
  run_dir = workdir / "run"
  (run_dir / "candidates").mkdir(parents=True)
  with (run_dir / "candidates" / "candidates.jsonl").open("w", encoding="utf-8") as handle:
    for case in TINY_CASES:
      if case[6]:
        handle.write(json.dumps(_candidate(case[6], case[2], case[7], case[8])) + "\n")

  log, ledger = RunLog(results), CostLedger(results / "cost_ledger.json")
  decisions = {c[6]: c[9] for c in TINY_CASES if c[6]}
  report: dict = {}

  # 1. Judge twice through cache + budget guard: the second run must be served entirely from the cache.
  for attempt in (1, 2):
    run_id = new_run_id("ag-tiny", "tiny")
    entry = log.start(run_id=run_id, stage="tiny", system="ag-tiny", dataset="tiny", split="dev",
                      command="python -m eval.run --tiny")
    model = ScriptedClient(decisions)
    client = CachingConfirmationClient(BudgetedClient(model, ledger, "tiny", run_id=run_id), workdir / "cache")
    run_confirmation(config=ConfirmationConfig(provider="fake", model=model.model),
                     options=ConfirmationRunOptions(run_dir=run_dir, confirmation_run_id=f"tiny-{attempt}"),
                     client=client)
    log.finish(entry, status="ok")
    report[f"run{attempt}"] = {"model_calls": model.calls, "cache_hits": client.hits}
  assert report["run1"]["model_calls"] == 6 and report["run2"] == {"model_calls": 0, "cache_hits": 6}, report

  # 2. Verdicts -> findings -> one prediction per case (no candidate = not_applicable).
  records = [json.loads(l) for l in (run_dir / "confirmations" / "tiny-2" / "confirmations.jsonl").read_text().splitlines()]
  by_candidate = {r["candidate_id"]: r["decision"] for r in records}
  cases = {c[0]: Locator(c[7], c[2], selector=c[8]) for c in TINY_CASES}
  findings = [Finding(Locator(c[7], c[2], selector=c[8]), by_candidate[c[6]]) for c in TINY_CASES if c[6]]
  predicted = predict_cases(cases, findings, unmatched="not_applicable")
  gold = [GoldCase("tiny", c[0], c[1], c[2], c[3], direction=c[4], subgroup=c[5], split="dev",
                   page_level=c[2] == "page-title-not-descriptive") for c in TINY_CASES]
  rows = [PredictionRow(run_id="tiny-2", system="ag-tiny", config="scripted", model="scripted-tiny", run_idx=0,
                        regime="R2", dataset="tiny", case_id=cid, prediction=pred, evidence_scope="state")
          for cid, (pred, _) in predicted.items()]
  path = write_rows(results / "predictions" / "tiny.csv", rows)
  rows = read_predictions(path)
  problems = check_complete(gold, rows)
  assert not problems, problems
  log.exclude("tiny", "t-99", "example exclusion row (tiny check)", rule="tiny")

  # 3. Scores in every view, plus breakdowns.
  joined = join(gold, {r.case_id: r.prediction for r in rows})
  views = {v: score_cases(joined, v).as_dict() for v in ("strict", "selective", "triage", "coverage")}
  assert views["strict"]["tp"] == 2 and views["strict"]["fp"] == 1 and views["triage"]["tp"] == 3, views
  assert views["coverage"]["n_scored"] == 6 and predicted["t-07"][0] == "not_applicable", (views, predicted)
  report["scores"] = views
  report["by_subgroup"] = {k: m.recall for k, m in breakdown(joined, "subgroup").items()}

  # 4. Statistics on the same data (small replicate counts keep --tiny fast).
  recall = lambda items: score_cases(items).recall
  other = [(c, "violation" if c.expected == "violation" else "no_violation") for c, _ in joined]
  report["stats"] = {
    "wilson_recall": stats.wilson_ci(views["strict"]["tp"], views["strict"]["tp"] + views["strict"]["fn"]),
    "bootstrap_recall": stats.cluster_bootstrap(joined, lambda x: x[0].app, recall, replicates=200),
    "permutation": stats.paired_permutation_test(list(zip(joined, other)), recall, replicates=200),
    "mcnemar": stats.mcnemar_exact(1, 4),
    "holm": stats.holm({"h1": 0.01, "h2": 0.04, "h3": 0.03}),
    "fleiss": stats.fleiss_kappa([["v", "v", "n"], ["n", "n", "n"], ["v", "v", "v"]]),
    "cohen": stats.cohen_kappa(["v", "n", "v", "n"], ["v", "n", "n", "n"]),
  }

  # 5. Budget guard: a paid provider without a price, and a stage with no budget, are both refused.
  class Paid(ScriptedClient):
    provider = "anthropic"
  for client, label in ((BudgetedClient(Paid(decisions), ledger, "tiny"), "zero-cap stage"),):
    try:
      client.ledger.check("tiny", planned_usd=0.01)
      raise AssertionError(f"budget guard did not refuse: {label}")
    except BudgetExceeded:
      pass
  report["ledger_total_usd"] = ledger.total
  assert ledger.total == 0.0

  # 6. Freeze guard: a changed frozen file blocks test runs.
  frozen = workdir / "frozen"
  (frozen / "src").mkdir(parents=True)
  (frozen / "src" / "rule.py").write_text("A = 1\n")
  write_freeze(["src/*.py"], {"model": "scripted-tiny"}, root=frozen, path=frozen / "FREEZE.json")
  verify_freeze(root=frozen, path=frozen / "FREEZE.json")
  (frozen / "src" / "rule.py").write_text("A = 2\n")
  try:
    verify_freeze(root=frozen, path=frozen / "FREEZE.json")
    raise AssertionError("freeze guard did not detect a change")
  except FrozenFileChanged:
    report["freeze_guard"] = "ok"
  return report


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(prog="python -m eval.run", description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--tiny", action="store_true", help="offline end-to-end check of the harness")
  parser.add_argument("--workdir", type=Path, help="keep --tiny outputs here instead of a temp folder")
  args = parser.parse_args(argv)
  if not args.tiny:
    parser.print_help()
    return 2
  if args.workdir:
    args.workdir.mkdir(parents=True, exist_ok=False)
    report = run_tiny(args.workdir)
  else:
    with tempfile.TemporaryDirectory(prefix="eval-tiny-") as tmp:
      report = run_tiny(Path(tmp))
  print(json.dumps(report, indent=2, default=str))
  print("eval --tiny: PASS")
  return 0


if __name__ == "__main__":
  sys.exit(main())
