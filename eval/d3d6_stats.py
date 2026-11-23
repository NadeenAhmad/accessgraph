"""D3/D6 statistics: AccessGraph vs Rampa+Gemma (both readings). Free (reads saved records only).

  python -m eval.d3d6_stats --tag v11

D3: F1 difference with a cluster bootstrap CI (ACT rules, then cases) and a paired permutation test. D6: pairs told
apart, exact McNemar on the discordant pairs. Holm-Bonferroni over the four comparisons on all cases. Also the
untouched halves (results/holdout_split.json). Output: results/d3d6-<tag>/STATS.md + stats.json.
"""
from __future__ import annotations

import argparse
import json

import yaml

from eval import d3d6
from eval.stats import cluster_bootstrap, holm, mcnemar_exact, paired_permutation_test


def _f1(items: list[tuple[bool, bool]]) -> float:
  tp = sum(1 for p, t in items if p and t)
  fp = sum(1 for p, t in items if p and not t)
  fn = sum(1 for p, t in items if not p and t)
  return 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--tag", default="v11")
  parser.add_argument("--replicates", type=int, default=10_000)
  args = parser.parse_args(argv)
  d3d6.OUT = d3d6.ROOT / "results" / f"d3d6-{args.tag}"
  rules = yaml.safe_load(d3d6.MAPPING.read_text(encoding="utf-8"))["act"]
  all_cases = [c for c in json.loads((d3d6.STORED / "cases.json").read_text())["cases"] if c["ruleId"] in rules]
  all_pairs = json.loads((d3d6.OUT / "pairs.json").read_text())["pairs"]
  split_file = d3d6.ROOT / "results" / "holdout_split.json"  # development split: not in the published repository
  split = json.loads(split_file.read_text()) if split_file.exists() else None
  ag, rg = d3d6._records("accessgraph"), d3d6._records("rampa-gemma")
  definite = d3d6.READINGS["definite"]
  lines = ["# D3/D6 statistics: AccessGraph vs Rampa+Gemma", "",
           f"AccessGraph tag `{args.tag}` (definite verdicts). D3: difference in F1 with a cluster bootstrap CI (ACT "
           f"rules, then cases; {args.replicates:,} replicates) and a paired permutation test; D6: pairs told apart, "
           "exact McNemar. Holm over the four comparisons on all cases.", "",
           "| Set | Rampa+Gemma reading | n | AG | Rampa+Gemma | Difference (95% CI) | p | p (Holm) |",
           "|---|---|---|---|---|---|---|---|"]
  results, family = [], {}
  for subset in ("all", "untouched") if split else ("all",):
    cases = all_cases if subset == "all" else [c for c in all_cases if c["id"] in set(split["D3"][subset])]
    pairs = all_pairs if subset == "all" else [p for p in all_pairs if p["corruptedId"] in set(split["D6"][subset])]
    cases = [c for c in cases if c["expected"] in ("failed", "passed")]
    for reading in ("definite", "with review"):
      flag = d3d6.READINGS[reading]
      items = [(c["ruleId"], definite(ag.get(c["id"]), rules[c["ruleId"]]["criterion"]),
                flag(rg.get(c["id"]), rules[c["ruleId"]]["criterion"]), c["expected"] == "failed") for c in cases]
      diff = lambda xs: _f1([(a, t) for _, a, _, t in xs]) - _f1([(b, t) for _, _, b, t in xs])  # noqa: E731
      point, lo, hi = cluster_bootstrap(items, lambda x: x[0], diff, replicates=args.replicates)
      _, p = paired_permutation_test([((a, t), (b, t)) for _, a, b, t in items], _f1, replicates=args.replicates)
      key = f"D3/{subset}/{reading}"
      results.append({"key": key, "n": len(items), "ag": _f1([(a, t) for _, a, _, t in items]),
                      "rampa_gemma": _f1([(b, t) for _, _, b, t in items]), "diff": point, "ci": [lo, hi], "p": p})
      told = lambda f, recs, pr: f(recs.get(pr["corruptedId"]), pr["criterion"]) and not f(  # noqa: E731
        recs.get(pr["intactId"]), pr["criterion"])
      a_told = [told(definite, ag, pr) for pr in pairs]
      b_told = [told(flag, rg, pr) for pr in pairs]
      only_a = sum(1 for x, y in zip(a_told, b_told) if x and not y)
      only_b = sum(1 for x, y in zip(a_told, b_told) if y and not x)
      key6 = f"D6/{subset}/{reading}"
      # difference in the share of pairs told apart, 95% CI by bootstrap over pairs (each pair its own cluster)
      pair_items = list(enumerate(zip(a_told, b_told)))
      share_diff = lambda xs: sum(a for _, (a, _) in xs) / len(xs) - sum(b for _, (_, b) in xs) / len(xs)  # noqa: E731
      d_point, d_lo, d_hi = cluster_bootstrap(pair_items, lambda x: x[0], share_diff, replicates=args.replicates)
      results.append({"key": key6, "n": len(pairs), "ag": sum(a_told), "rampa_gemma": sum(b_told),
                      "only_ag": only_a, "only_rampa_gemma": only_b, "p": mcnemar_exact(only_a, only_b),
                      "share_diff": d_point, "share_ci": [d_lo, d_hi]})
      if subset == "all":
        family[key], family[key6] = p, results[-1]["p"]
  adjusted = holm(family)
  for r in results:
    r["p_holm"] = adjusted.get(r["key"])
    holm_text = "–" if r["p_holm"] is None else f"{r['p_holm']:.3f}"
    dataset, subset, reading = r["key"].split("/")
    if dataset == "D3":
      lines.append(f"| D3 {subset} | {reading} | {r['n']} | F1 {r['ag']:.3f} | F1 {r['rampa_gemma']:.3f} | "
                   f"{r['diff']:+.3f} ({r['ci'][0]:+.3f} to {r['ci'][1]:+.3f}) | {r['p']:.3f} | {holm_text} |")
    else:
      lines.append(f"| D6 {subset} | {reading} | {r['n']} | {r['ag']} pairs | {r['rampa_gemma']} pairs | "
                   f"{r['ag'] - r['rampa_gemma']:+d} (only AG {r['only_ag']}, only R+G {r['only_rampa_gemma']}) | "
                   f"{r['p']:.3f} | {holm_text} |")
  (d3d6.OUT / "STATS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
  (d3d6.OUT / "stats.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
  print("\n".join(lines))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
