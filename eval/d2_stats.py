"""D2 statistics for H3: F1 difference AccessGraph - baseline with a page-cluster bootstrap CI and a paired
permutation test, plus cost and time per case. Free (reads saved predictions only).

  python -m eval.d2_stats --tag v11

AccessGraph = the mean F1 over its runs with `--tag` (each case carries the tuple of its run predictions; a
permutation swaps that tuple with the baseline's prediction repeated). Baselines: InterA11y (full) and
Lopez-Pereira, both with GPT-6 Luna, from InterA11y's saved predictions. Clusters = the page a case is on.
Holm-Bonferroni over the comparisons on all cases (the H3 family). Output: results/d2/STATS.md + stats.json.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from eval.d2 import INTERA11Y, OUT, PRIVATE, kept
from eval.stats import cluster_bootstrap, holm, paired_permutation_test

LUNA_USD_PER_TOKEN = {"input": 0.10e-6, "output": 0.50e-6}  # OpenRouter list price, openai/gpt-6-luna, 2026-11-18
BASELINES = {"expert": [("InterA11y", "intera11y", "full")],
             "conformance": [("InterA11y", "intera11y", "full"), ("Lopez-Pereira", "lopez-pereira", "default")]}


def _rows(path: Path) -> list[dict]:
  with path.open(encoding="utf-8", newline="") as stream:
    return list(csv.DictReader(stream))


def _f1(pairs: list[tuple[bool, bool]]) -> float:
  tp = sum(1 for p, t in pairs if p and t)
  fp = sum(1 for p, t in pairs if p and not t)
  fn = sum(1 for p, t in pairs if not p and t)
  return 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)


def _mean_f1(items: list[tuple[tuple[bool, ...], bool]]) -> float:
  runs = len(items[0][0])
  return sum(_f1([(preds[r], label) for preds, label in items]) for r in range(runs)) / runs


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--tag", default="v11")
  parser.add_argument("--replicates", type=int, default=10_000)
  parser.add_argument("--full", action="store_true", help="every case of the shared criteria, as released")
  parser.add_argument("--with-axe", action="store_true", help="AccessGraph + axe-core (union), as in d2_combined")
  args = parser.parse_args(argv)
  scope = "full" if args.full else "semantic"
  lines = ["# D2 statistics (H3)", "",
           f"AccessGraph = mean F1 over the `{args.tag}` runs; baselines with the same model (GPT-6 Luna). "
           "Difference = AccessGraph - baseline; 95% CI from a cluster bootstrap (pages, then cases), "
           f"{args.replicates:,} replicates; p from a paired permutation test ({args.replicates:,}); "
           "Holm-adjusted over the comparisons on all cases.", "",
           "| Set | Cases | Baseline | AG F1 | Baseline F1 | Difference (95% CI) | p | p (Holm) |",
           "|---|---|---|---|---|---|---|---|"]
  results, family = [], {}
  for dataset, baselines in BASELINES.items():
    elements = {r["case_id"]: r for r in _rows(INTERA11Y / "datasets" / dataset / "elements.csv")}
    saved = _rows(INTERA11Y / "results" / f"{dataset}-predictions.csv")
    runs = sorted(PRIVATE.glob(f"runs/{dataset}-{args.tag}-run-*"))
    ag = [{r["case_id"]: r["flagged"] == "1" for r in _rows(run / "predictions.csv")} for run in runs]
    if args.with_axe:
      axe = {r["case_id"]: r["flagged"] == "1" for r in saved if r["system"] == "axe" and r["model"] == "none"}
      ag = [{c: v or axe.get(c, False) for c, v in run.items()} for run in ag]
    for subset in ("all", "practice", "untouched"):
      ids = kept(dataset, subset, scope)
      if not ids or (dataset == "expert" and subset != "all") or (scope == "full" and subset != "all"):
        continue
      for name, system, condition in baselines:
        base = {r["case_id"]: r["flagged"] == "1" for r in saved
                if r["system"] == system and r["condition"] == condition and r["model"] == "luna"}
        items = [(c, tuple(run.get(c, False) for run in ag), base.get(c, False), elements[c]["label"] == "1")
                 for c in ids]
        diff = lambda xs: _mean_f1([(a, t) for _, a, _, t in xs]) - _f1([(b, t) for _, _, b, t in xs])  # noqa: E731
        point, lo, hi = cluster_bootstrap(items, lambda x: elements[x[0]]["page"], diff,
                                          replicates=args.replicates)
        k = len(ag)
        pairs = [((a, t), ((b,) * k, t)) for _, a, b, t in items]
        _, p = paired_permutation_test(pairs, _mean_f1, replicates=args.replicates)
        key = f"{dataset}/{subset}/{name}"
        if subset == "all":
          family[key] = p
        results.append({"key": key, "dataset": dataset, "subset": subset, "baseline": name, "cases": len(ids),
                        "ag_f1": _mean_f1([(a, t) for _, a, _, t in items]),
                        "baseline_f1": _f1([(b, t) for _, _, b, t in items]),
                        "diff": point, "ci": [lo, hi], "p": p})
  adjusted = holm(family)
  for r in results:
    r["p_holm"] = adjusted.get(r["key"])
    holm_text = "–" if r["p_holm"] is None else f"{r['p_holm']:.3f}"
    lines.append(f"| {r['dataset']} {r['subset']} | {r['cases']} | {r['baseline']} | {r['ag_f1']:.3f} | "
                 f"{r['baseline_f1']:.3f} | {r['diff']:+.3f} ({r['ci'][0]:+.3f} to {r['ci'][1]:+.3f}) | "
                 f"{r['p']:.3f} | {holm_text} |")

  # cost and time per case: AccessGraph's billed cost on fully paid runs; InterA11y's recorded tokens at list price
  lines += ["", "## Cost and time per case", "",
            "AccessGraph: billed cost (OpenRouter, incl. its prompt-cache discount) of runs whose calls were all paid; "
            "time = wall time per case in single-page mode (recording + judging). InterA11y: its recorded tokens at "
            "the list price; time = its recorded total seconds.", "",
            "| Set | System | Cases | USD per case | Mean s per case | Median s per case |", "|---|---|---|---|---|---|"]
  cost = {}
  for dataset in BASELINES:
    ids = set(kept(dataset, scope=scope))
    for run in sorted(PRIVATE.glob(f"runs/{dataset}-{args.tag}-run-*")):
      if not (run / "results.json").exists():  # published runs keep only predictions.csv; cost needs the run details
        continue
      rows = [r for r in json.loads((run / "results.json").read_text()) if r["case_id"] in ids]
      calls = sum((r.get("raw") or {}).get("calls", 0) for r in rows)
      paid = sum((r.get("raw") or {}).get("paid_calls", 0) for r in rows)
      if paid < calls:
        continue
      secs = sorted((r.get("raw") or {}).get("seconds", 0.0) for r in rows)
      usd = sum((r.get("raw") or {}).get("cost_usd", 0.0) for r in rows) / len(rows)
      cost[f"{dataset}/AccessGraph/{run.name}"] = usd
      lines.append(f"| {dataset} | AccessGraph ({run.name}) | {len(rows)} | {usd:.4f} | "
                   f"{sum(secs) / len(secs):.1f} | {secs[len(secs) // 2]:.1f} |")
    res = [r for r in _rows(INTERA11Y / "results" / "resources.csv") if r["case_id"] in ids
           and r["system"] == "intera11y" and r["condition"] == "full" and r["model"] == "luna"]
    if not res:  # InterA11y records resources for the expert cases only
      continue
    usd =sum(float(r["input_tokens"] or 0) * LUNA_USD_PER_TOKEN["input"]
              + float(r["output_tokens"] or 0) * LUNA_USD_PER_TOKEN["output"] for r in res) / len(res)
    secs = sorted(float(r["total_seconds"]) for r in res if r["total_seconds"])
    cost[f"{dataset}/InterA11y"] = usd
    lines.append(f"| {dataset} | InterA11y (full) | {len(res)} | {usd:.4f} | "
                 f"{sum(secs) / len(secs):.1f} | {secs[len(secs) // 2]:.1f} |")
  name = f"STATS{'-full' if args.full else ''}{'-axe' if args.with_axe else ''}"
  (OUT / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
  (OUT / f"{name.lower()}.json").write_text(json.dumps({"tests": results, "cost_per_case_usd": cost}, indent=2) + "\n",
                                  encoding="utf-8")
  print("\n".join(lines))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
