"""D2: AccessGraph on InterA11y's datasets, inside InterA11y's harness, scored by InterA11y's own `parse`.

  python -m eval.d2 --run 1 [--dataset expert|conformance|all]   # judge (stage `external`), one run
  python -m eval.d2 --score                                        # their parse + our cross-check -> SCORES.md

Cases: the in-scope cases of eval/d2_filter.py (results/d2/scope.csv). AccessGraph runs as the system
`accessgraph` (eval/patches/intera11y-8dcf06e-accessgraph-system.patch) with the main model, one condition per run
(run-1..run-3). InterA11y and the other systems are not re-run: their saved predictions (results/<dataset>-
predictions.csv in InterA11y's repository) are scored on the same cases. Primary scorer: `intera11y.py parse` with
the labels limited to the in-scope cases; cross-check: the same counts computed here. InterA11y's data are not
redistributed: the limited label files stay under runs/ (ignored by git).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.cost import CostLedger  # noqa: E402
from eval.external_check import verify  # noqa: E402
from eval.freeze import verify_freeze  # noqa: E402
from eval.runlog import RunLog, new_run_id  # noqa: E402

from eval.paths import INTERA11Y  # noqa: E402
SCOPE = ROOT / "results" / "d2" / "scope.csv"
OUT = ROOT / "results" / "d2"
PRIVATE = ROOT / "runs" / "w4a-d2"            # InterA11y's data stay out of git
EXPERIMENT = {"expert": "expert-evaluation", "conformance": "conformance-evaluation"}
STAGE = "external"
EST_CASE_USD = {"expert": 0.004, "conformance": 0.002}


def kept(dataset: str, subset: str = "all", scope: str = "semantic") -> list[str]:
  """In-scope cases (scope "semantic"), or every case of the shared criteria as released (scope "full", PI decision
  2026-11-18: datasets are reported as released); `subset` practice/untouched follows results/holdout_split.json."""
  with SCOPE.open(encoding="utf-8") as stream:
    ids = [r["case_id"] for r in csv.DictReader(stream)
           if r["dataset"] == dataset and (scope == "full" or r["keep"] == "1")]
  split_file = ROOT / "results" / "holdout_split.json"
  if subset == "all":
    return ids
  if not split_file.exists():  # the development split is not part of the published repository
    return []
  split = json.loads(split_file.read_text())[f"D2-{dataset}"]
  return [i for i in ids if i in set(split[subset])]


def run(run_idx: int, datasets: list[str], *, subset: str = "all", tag: str = "", stage: str = STAGE,
        scope: str = "semantic") -> None:
  if subset != "practice":  # practice runs are development; every other run must match FREEZE.json
    verify_freeze(root=ROOT)
  verify()
  ledger = CostLedger(ROOT / "results" / "cost_ledger.json")
  log = RunLog(ROOT / "results")
  env = dict(os.environ, ACCESSGRAPH_HOME=str(ROOT), ACCESSGRAPH_STAGE=stage,
             ACCESSGRAPH_CACHE_ROUND=os.environ.get("ACCESSGRAPH_CACHE_ROUND", tag))  # tag = fresh answers per round
  for dataset in datasets:
    cases = kept(dataset, subset, scope)
    if not cases:
      continue
    estimate = EST_CASE_USD[dataset] * len(cases)
    print(f"[estimate] {dataset} run {run_idx}: {len(cases)} cases, about ${estimate:.2f} "
          f"(stage {stage}: ${ledger.stage_total(stage):.3f} of ${ledger.stage_caps[stage]} used)", flush=True)
    ledger.check(stage, estimate)
    before = ledger.stage_total(stage)
    row = log.start(run_id=new_run_id("AG-main", f"D2-{dataset}{'-' + tag if tag else ''}"), stage=stage,
                    system="AG-main", dataset=f"D2-{dataset}", split=subset)
    out = PRIVATE / "runs" / f"{dataset}{'-' + tag if tag else ''}-run-{run_idx}"
    done = subprocess.run([str(INTERA11Y / ".venv/bin/python"), "intera11y.py", "run", "--experiment", EXPERIMENT[dataset],
                           "--systems", "accessgraph", "--models", "luna", "--condition", f"run-{run_idx}",
                           "--cases", ",".join(cases), "--workers", "4", "--output", str(out)],
                          cwd=INTERA11Y, env=env, capture_output=True, text=True)
    summary = done.stdout.strip().splitlines()[-6:]
    print("\n".join(summary), flush=True)
    ledger = CostLedger(ROOT / "results" / "cost_ledger.json")
    log.finish(row, status="done" if done.returncode == 0 else "failed", cost_usd=ledger.stage_total(stage) - before,
               notes=f"cases={len(cases)} out={out.relative_to(ROOT)}")


def _rows(path: Path) -> list[dict]:
  with path.open(encoding="utf-8", newline="") as stream:
    return list(csv.DictReader(stream))


def score(scope: str = "semantic") -> None:
  suffix = "" if scope == "semantic" else "-full"
  lines = [f"# D2: InterA11y's datasets, {'in-scope cases only' if scope == 'semantic' else 'all cases as released'}", "",
           ("Scored with InterA11y's own `parse` on the cases eval/d2_filter.py keeps; other systems are their saved "
            if scope == "semantic" else "Scored with InterA11y's own `parse` on every case of the shared criteria; other "
            "systems are their saved ") + 
           "predictions on the same cases. Flagged = a definite finding (uncertain counts as not flagged).", ""]
  summary = {}
  for dataset, experiment in EXPERIMENT.items():
    ids = set(kept(dataset, scope=scope))
    if not ids:
      continue
    elements = [r for r in _rows(INTERA11Y / "datasets" / dataset / "elements.csv") if r["case_id"] in ids]
    PRIVATE.mkdir(parents=True, exist_ok=True)
    labels = PRIVATE / f"labels-{dataset}-inscope{suffix}.csv"
    with labels.open("w", newline="", encoding="utf-8") as stream:
      writer = csv.DictWriter(stream, fieldnames=list(elements[0]))
      writer.writeheader()
      writer.writerows(elements)
    theirs = [r for r in _rows(INTERA11Y / "results" / f"{dataset}-predictions.csv") if r["case_id"] in ids]
    ours = []
    for run_dir in sorted((PRIVATE / "runs").glob(f"{dataset}-*run-*")):
      if (run_dir / "predictions.csv").exists():
        tag = run_dir.name[len(dataset) + 1:].rsplit("run-", 1)[0].rstrip("-")  # "" for round 1, e.g. "r2" after
        for r in _rows(run_dir / "predictions.csv"):
          if r["case_id"] in ids:
            ours.append({**r, "condition": f"{tag}-{r['condition']}" if tag else r["condition"]})
    fields = list(theirs[0]) if theirs else ["case_id", "system", "condition", "model", "flagged", "state"]
    predictions = PRIVATE / f"predictions-{dataset}-inscope{suffix}.csv"
    with predictions.open("w", newline="", encoding="utf-8") as stream:
      writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
      writer.writeheader()
      for r in theirs + ours:
        writer.writerow({k: r.get(k, "") for k in fields})
    parse_out = OUT / f"parse-{dataset}{suffix}"
    done = subprocess.run([str(INTERA11Y / ".venv/bin/python"), "intera11y.py", "parse", "--experiment", experiment,
                           "--predictions", str(predictions), "--labels", str(labels), "--output", str(parse_out)],
                          cwd=INTERA11Y, capture_output=True, text=True)
    if done.returncode:
      raise RuntimeError(done.stderr[-800:])
    metrics = json.loads((parse_out / "metrics.json").read_text())
    # cross-check: the same counts computed here from the two files
    label = {r["case_id"]: r["label"] == "1" for r in elements}
    mine = defaultdict(lambda: [0, 0, 0, 0])
    for r in theirs + ours:
      t, f = label[r["case_id"]], r["flagged"] == "1"
      mine[(r["system"], r["condition"], r["model"])][(0 if f else 2) + (0 if t else 1)] += 1
    mismatches = [m for m in metrics["per_model"] if m["scope"] == "All"
                  and tuple(mine[(m["system"], m["condition"], m["model"])]) != (m["TP"], m["FP"], m["FN"], m["TN"])
                  and (m["system"], m["condition"], m["model"]) in mine]
    pos = sum(label.values())
    lines += [f"## {dataset}: {len(ids)} in-scope cases ({pos} violations, {len(ids) - pos} no violation)", "",
              f"Cross-check with our own count: {'all equal' if not mismatches else f'{len(mismatches)} differ'}.", "",
              "| System | Condition | Model | P | R | F1 | FP | missing/failed |", "|---|---|---|---|---|---|---|---|"]
    fmt = lambda x: "–" if x is None else f"{x:.3f}"  # noqa: E731
    for m in sorted(metrics["per_model"], key=lambda m: (m["system"] != "accessgraph", m["system"], m["condition"], m["model"])):
      if m["scope"] != "All":
        continue
      bad = sum(v for k, v in m["states"].items() if k not in ("complete", "partial", "not_applicable"))
      lines.append(f"| {m['system']} | {m['condition']} | {m['model']} | {fmt(m['precision'])} | {fmt(m['recall'])} | "
                   f"{fmt(m['f1'])} | {m['FP']} | {bad} |")
    lines.append("")
    summary[dataset] = {"cases": len(ids), "positives": pos, "parse": str(parse_out.relative_to(ROOT))}
  (OUT / f"SCORES{suffix}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
  (OUT / f"summary{suffix}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
  print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--run", type=int, choices=(1, 2, 3))
  parser.add_argument("--dataset", choices=("expert", "conformance", "all"), default="all")
  parser.add_argument("--score", action="store_true")
  parser.add_argument("--subset", choices=("all", "practice", "untouched"), default="all")
  parser.add_argument("--tag", default="", help="keeps a round's runs apart, e.g. r2")
  parser.add_argument("--stage", default=STAGE)
  parser.add_argument("--full", action="store_true", help="every case of the shared criteria, as released")
  args = parser.parse_args(argv)
  scope = "full" if args.full else "semantic"
  if args.run:
    run(args.run, ["expert", "conformance"] if args.dataset == "all" else [args.dataset], subset=args.subset,
        tag=args.tag, stage=args.stage, scope=scope)
  if args.score:
    score(scope)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
