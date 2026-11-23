"""D3 (W3C ACT test cases) and D6 (Rampa's corrupted pairs): run AccessGraph in Rampa's harness, then score.

  python -m eval.d3d6 --dry-run      # build the pairs, list the pages, estimate the cost (no model calls)
  python -m eval.d3d6                # judge with AccessGraph (stage `external`), then score
  python -m eval.d3d6 --score-only

The cases come from the approved mapping (eval/mappings/external_act_rampa.yaml, frozen in FREEZE.json v2): the
ACT test cases of 7 rules and the pairs of 9 corruptors. Every other tool's results are the harness's stored raw
results (bench/results/2026-10-11; same pin, same ACT file), read with the harness's own readings:
`definite` (a definite failure on the criterion), `with review` (also review items), and for Rampa `with low`
(also findings below its threshold). Units, as in the harness: (test case, criterion); a failed example is
positive, a passed one negative; inapplicable examples are reported apart. Pairs: told apart when the corrupted
half is flagged under the pair's criterion and the intact half is not.
Output: results/d3d6/ (raw records, pages, pairs) and results/d3d6/SCORES.md, scores.json.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.adapters.rampa_state import browser_path  # noqa: E402
from eval.cost import CostLedger  # noqa: E402
from eval.external_check import verify  # noqa: E402
from eval.freeze import verify_freeze  # noqa: E402
from eval.runlog import RunLog, new_run_id  # noqa: E402
from eval.stats import wilson_ci  # noqa: E402

OUT = ROOT / "results" / "d3d6"
from eval.paths import RAMPA  # noqa: E402
STORED = RAMPA / "bench" / "results" / "2026-10-11"
MAPPING = ROOT / "eval" / "mappings" / "external_act_rampa.yaml"
STAGE = "external"
EST_PAGE_USD = 0.002
TOOLS = ("axe", "alfa", "qualweb", "ibm", "pa11y", "pa11y-axe", "rampa", "rampa-gemma", "rampa-probes", "accessgraph")


def run(dry_run: bool, *, subset: str = "all", stage: str = STAGE) -> None:
  if subset != "practice":  # practice runs are development; every other run must match FREEZE.json
    verify_freeze(root=ROOT)
  verify()
  mapping = yaml.safe_load(MAPPING.read_text(encoding="utf-8"))
  config = {"out": str(OUT), "rules": list(mapping["act"]), "keep": list(mapping["rampa_pairs"]["keep"]),
            "port": 8765, "workers": 2, "dryRun": dry_run}
  if subset != "all":  # only the ACT cases and the pairs (both halves) of one side of results/holdout_split.json
    split = json.loads((ROOT / "results" / "holdout_split.json").read_text())
    pair_ids = set(split["D6"][subset])
    pairs = json.loads((STORED / "pairs.json").read_text())["pairs"]
    config["only"] = sorted(set(split["D3"][subset]) | pair_ids
                            | {p["intactId"] for p in pairs if p["corruptedId"] in pair_ids})
  OUT.mkdir(parents=True, exist_ok=True)
  (OUT / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
  env = dict(os.environ, BENCH_BROWSER_PATH=browser_path(), ACCESSGRAPH_HOME=str(ROOT), ACCESSGRAPH_STAGE=stage,
             ACCESSGRAPH_DATASET="w4a-d3d6", ACCESSGRAPH_CACHE_ROUND=os.environ.get("ACCESSGRAPH_CACHE_ROUND", OUT.name),
             # Rampa's harness stops a page after 180 s (bench/lib/drive.mjs PAGE_TIMEOUT_MS); AccessGraph keeps its
             # judging inside that limit, with a margin for start-up
             ACCESSGRAPH_TIME_BUDGET_S="165")
  log = RunLog(ROOT / "results")
  row = None if dry_run else log.start(run_id=new_run_id("AG-main", "D3+D6"), stage=stage, system="AG-main",
                                        dataset="D3+D6", split=subset)
  ledger = CostLedger(ROOT / "results" / "cost_ledger.json")
  before = ledger.stage_total(stage)
  if not dry_run:
    ledger.check(stage, EST_PAGE_USD * (len(config.get("only") or []) or 190))
  done = subprocess.run(["node", str(ROOT / "eval/adapters/rampa_bench_d3d6.mjs"), str(OUT / "config.json")],
                        cwd=ROOT, env=env)
  pages = json.loads((OUT / "pages.json").read_text())
  print(f"{len(pages)} pages; estimate ${EST_PAGE_USD * len(pages):.2f} at ${EST_PAGE_USD}/page "
        f"(stage {stage}: ${ledger.stage_total(stage):.3f} of ${ledger.stage_caps[stage]} used)")
  if row is not None:
    ledger = CostLedger(ROOT / "results" / "cost_ledger.json")
    log.finish(row, status="done" if done.returncode == 0 else "failed", cost_usd=ledger.stage_total(stage) - before)


def _records(tool: str) -> dict[str, dict]:
  path = OUT / "raw" / "accessgraph.jsonl" if tool == "accessgraph" else STORED / "raw" / f"{tool}.jsonl"
  if not path.exists():
    return {}
  return {r["id"]: r for r in (json.loads(l) for l in path.read_text().splitlines() if l.strip())}


def _has(record: dict | None, key: str, criterion: str) -> bool:
  return bool(record and not record.get("error") and (record.get(key) or {}).get(criterion))


READINGS = {
  "definite": lambda r, c: _has(r, "fail", c),
  "with review": lambda r, c: _has(r, "fail", c) or _has(r, "review", c) or _has(r, "low", c),
  "with low": lambda r, c: _has(r, "fail", c) or _has(r, "low", c),
}


def _prf(tp, fp, fn):
  p = tp / (tp + fp) if tp + fp else None
  r = tp / (tp + fn) if tp + fn else None
  f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
  return p, r, f


def score(subset: str = "all") -> dict:
  mapping = yaml.safe_load(MAPPING.read_text(encoding="utf-8"))
  rules = mapping["act"]
  cases = [c for c in json.loads((STORED / "cases.json").read_text())["cases"] if c["ruleId"] in rules]
  pairs = json.loads((OUT / "pairs.json").read_text())["pairs"]
  if subset != "all":
    split = json.loads((ROOT / "results" / "holdout_split.json").read_text())
    cases = [c for c in cases if c["id"] in set(split["D3"][subset])]
    pairs = [p for p in pairs if p["corruptedId"] in set(split["D6"][subset])]
  out: dict = {"act_cases": len(cases), "pairs": len(pairs), "tools": {}}
  for tool in TOOLS:
    records = _records(tool)
    if not records:
      continue
    readings = ["definite", "with review"] + (["with low"] if tool.startswith("rampa") else [])
    entry = {}
    for reading in readings:
      flag = READINGS[reading]
      tp = fp = fn = tn = ia_flagged = ia = errors = 0
      per_rule = {}
      for case in cases:
        record = records.get(case["id"])
        if record is None or record.get("error"):
          errors += 1
        criterion = rules[case["ruleId"]]["criterion"]
        yes = flag(record, criterion)
        pr = per_rule.setdefault(case["ruleId"], {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
        if case["expected"] == "failed":
          tp, fn = tp + yes, fn + (not yes)
          pr["tp" if yes else "fn"] += 1
        elif case["expected"] == "passed":
          fp, tn = fp + yes, tn + (not yes)
          pr["fp" if yes else "tn"] += 1
        else:
          ia, ia_flagged = ia + 1, ia_flagged + yes
      p, r, f = _prf(tp, fp, fn)
      told = intact_flagged = corrupted_flagged = 0
      for pair in pairs:
        i = flag(records.get(pair["intactId"]), pair["criterion"])
        c = flag(records.get(pair["corruptedId"]), pair["criterion"])
        told += (c and not i)
        intact_flagged += i
        corrupted_flagged += c
      entry[reading] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": r, "f1": f,
                        "recall_ci": wilson_ci(tp, tp + fn), "inapplicable": ia, "inapplicable_flagged": ia_flagged,
                        "errors": errors, "per_rule": per_rule,
                        "pairs_told_apart": told, "pairs_intact_flagged": intact_flagged,
                        "pairs_corrupted_flagged": corrupted_flagged}
    out["tools"][tool] = entry
  ag = _records("accessgraph")
  out["accessgraph_cost_usd"] = round(sum((r.get("usage") or {}).get("costUsd", 0) for r in ag.values()), 4)
  (OUT / "scores.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
  fmt = lambda x: "–" if x is None else f"{x:.2f}"  # noqa: E731
  lines = ["# D3 (W3C ACT, 7 rules) and D6 (Rampa's pairs, 9 corruptors)", "",
           f"{len(cases)} ACT test cases; {len(pairs)} pairs. Other tools: stored results of Rampa's harness "
           f"(df32363, 2026-10-11). AccessGraph cost ${out['accessgraph_cost_usd']}.", "",
           "| Tool | Reading | P | R (95% CI) | F1 | FP | inapplicable flagged | errors | pairs told apart |",
           "|---|---|---|---|---|---|---|---|---|"]
  for tool, entry in out["tools"].items():
    for reading, m in entry.items():
      lo, hi = m["recall_ci"]
      lines.append(f"| {tool} | {reading} | {fmt(m['precision'])} | {fmt(m['recall'])} ({lo:.2f}–{hi:.2f}) | "
                   f"{fmt(m['f1'])} | {m['fp']} | {m['inapplicable_flagged']}/{m['inapplicable']} | {m['errors']} | "
                   f"{m['pairs_told_apart']}/{len(pairs)} |")
  (OUT / "SCORES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
  print("\n".join(lines))
  return out


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--score-only", action="store_true")
  parser.add_argument("--subset", choices=("all", "practice", "untouched"), default="all")
  parser.add_argument("--tag", default="", help="results/d3d6-<tag>: keeps a round apart, e.g. r2")
  parser.add_argument("--stage", default=STAGE)
  args = parser.parse_args(argv)
  global OUT
  if args.tag:
    OUT = ROOT / "results" / f"d3d6-{args.tag}"
  if not args.score_only:
    run(args.dry_run, subset=args.subset, stage=args.stage)
  if not args.dry_run:
    score(args.subset)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
