"""Values for the numbers (results/PAPER_NUMBERS.md), from saved results only (free).

  python -m eval.paper_values --tag v13

D2: AccessGraph + axe-core (union) per run on all cases as released, mean P/R/F1, run F1s, Fleiss' kappa and flip
rate over the runs (on the combined verdicts), differences from results/d2/stats-full-axe.json, the semantic subset
(AccessGraph alone) from results/d2/stats.json. D3/D6 from results/d3d6-<tag>/scores.json and stats.json. Writes
results/PAPER_VALUES-<tag>.md and prints it, with the wording each comparison earns under the pre-registered rule.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from eval.d2 import INTERA11Y, OUT, PRIVATE, kept
from eval.stats import fleiss_kappa, flip_rate

ROOT = Path(__file__).resolve().parents[1]


def _rows(path: Path) -> list[dict]:
  with path.open(encoding="utf-8", newline="") as stream:
    return list(csv.DictReader(stream))


def _wording(p_holm: float | None, ci: list[float]) -> str:
  return "outperforms" if p_holm is not None and p_holm < 0.05 and (ci[0] > 0 or ci[1] < 0) else "comparable"


def _fmt_ci(ci: list[float]) -> str:
  return f"{ci[0]:+.3f} to {ci[1]:+.3f}"


def _p(p: float | None) -> str:
  return "–" if p is None else ("< .001" if p < 0.001 else f"{p:.3f}".lstrip("0"))


def d2_values(tag: str) -> dict[str, str]:
  out: dict[str, str] = {}
  for dataset, key in (("expert", "exp"), ("conformance", "conf")):
    ids = kept(dataset, scope="full")
    elements = {r["case_id"]: r for r in _rows(INTERA11Y / "datasets" / dataset / "elements.csv")}
    saved = _rows(INTERA11Y / "results" / f"{dataset}-predictions.csv")
    axe = {r["case_id"]: r["flagged"] == "1" for r in saved if r["system"] == "axe" and r["model"] == "none"}
    runs = sorted(PRIVATE.glob(f"runs/{dataset}-{tag}-run-*"))
    preds = [{r["case_id"]: r["flagged"] == "1" for r in _rows(run / "predictions.csv")} for run in runs]
    combined = [[pred.get(c, False) or axe.get(c, False) for c in ids] for pred in preds]
    labels = [elements[c]["label"] == "1" for c in ids]
    ps, rs, fs = [], [], []
    for flags in combined:
      tp = sum(f and t for f, t in zip(flags, labels))
      fp = sum(f and not t for f, t in zip(flags, labels))
      fn = sum(t and not f for f, t in zip(flags, labels))
      p = tp / (tp + fp) if tp + fp else 0.0
      r = tp / (tp + fn) if tp + fn else 0.0
      ps.append(p), rs.append(r), fs.append(2 * p * r / (p + r) if p + r else 0.0)
    n = len(fs)
    out[f"D2.{key}.P"] = f"{sum(ps) / n:.3f}"
    out[f"D2.{key}.R"] = f"{sum(rs) / n:.3f}"
    out[f"D2.{key}.F1"] = f"{sum(fs) / n:.3f}"
    out[f"D2.{key}.runs"] = ", ".join(f"{f:.3f}" for f in fs)
    kappa = fleiss_kappa([[run[i] for run in combined] for i in range(len(ids))])
    out[f"D2.{key}.kappa"] = "–" if kappa is None else f"{kappa:.2f}"
    flip = flip_rate(combined)
    out[f"D2.{key}.flip"] = "–" if flip is None else f"{100 * flip:.1f}%"
    alone = [[pred.get(c, False) for c in ids] for pred in preds]  # AccessGraph alone, for comparison
    kappa_alone = fleiss_kappa([[run[i] for run in alone] for i in range(len(ids))])
    out[f"D2.{key}.kappa_alone"] = "–" if kappa_alone is None else f"{kappa_alone:.2f}"
  stats = json.loads((OUT / "stats-full-axe.json").read_text(encoding="utf-8"))["tests"]
  for test in stats:
    if test["subset"] != "all":
      continue
    key = {"expert/InterA11y": "exp.vsIA", "conformance/InterA11y": "conf.vsIA",
           "conformance/Lopez-Pereira": "conf.vsLP"}[f"{test['dataset']}/{test['baseline']}"]
    out[f"D2.{key}.diff"] = f"{test['diff']:+.3f}"
    out[f"D2.{key}.ci"] = _fmt_ci(test["ci"])
    out[f"D2.{key}.p"] = _p(test["p_holm"])
    out[f"D2.{key}.wording"] = _wording(test["p_holm"], test["ci"])
  semantic = json.loads((OUT / "stats.json").read_text(encoding="utf-8"))["tests"]
  for test in semantic:
    if test["subset"] == "all" and test["baseline"] == "InterA11y":
      out[f"D2.{'exp' if test['dataset'] == 'expert' else 'conf'}.sem.F1"] = f"{test['ag_f1']:.2f}"
  return out


def d3d6_values(tag: str) -> dict[str, str]:
  folder = ROOT / "results" / f"d3d6-{tag}"
  ag = json.loads((folder / "scores.json").read_text(encoding="utf-8"))["tools"]["accessgraph"]["definite"]
  out = {"D3.P": f"{ag['precision']:.2f}", "D3.R": f"{ag['recall']:.2f}",
         "D3.R.ci": f"{ag['recall_ci'][0]:.2f}–{ag['recall_ci'][1]:.2f}", "D3.F1": f"{ag['f1']:.2f}",
         "D3.inapp": f"{ag['inapplicable_flagged']}/{ag['inapplicable']}", "D6.pairs": str(ag["pairs_told_apart"])}
  for test in json.loads((folder / "stats.json").read_text(encoding="utf-8")):
    if "/all/" not in test["key"]:
      continue
    reading = "RG" if test["key"].endswith("definite") else "RGr"
    if test["key"].startswith("D3"):
      out[f"D3.vs{reading}.diff"] = f"{test['diff']:+.2f}"
      out[f"D3.vs{reading}.ci"] = f"{test['ci'][0]:+.2f} to {test['ci'][1]:+.2f}"
      out[f"D3.vs{reading}.p"] = _p(test["p_holm"])
      out[f"D3.vs{reading}.wording"] = _wording(test["p_holm"], test["ci"])
    else:
      out[f"D6.vs{reading}.p"] = _p(test["p_holm"])
      if reading == "RG":
        out["D6.vsRG.diff"] = f"{test['share_diff']:+.3f} of pairs"
        out["D6.vsRG.ci"] = _fmt_ci(test["share_ci"])
        out["D6.vsRG.wording"] = _wording(test["p_holm"], test["share_ci"])
  return out


def d5_values() -> dict[str, str]:
  """The real-SPA (D5) numbers, from results/d5/summary.json (descriptive; expert-confirmed shares come later)."""
  s = json.loads((ROOT / "results" / "d5" / "summary.json").read_text(encoding="utf-8"))
  apps = s["apps"].values()
  out = {"D5.apps": str(len(s["apps"])), "D5.states": str(sum(a["states"] for a in apps)),
         "D5.transitions": str(sum(a["transitions"] for a in apps)), "D5.candidates": f"{s['candidates']:,}",
         "D5.judged": str(s["sampled"])}
  for decision in ("violation", "no_violation", "uncertain"):
    out[f"D5.{decision}"] = str(s["decisions"].get(decision, 0))
  out["D5.weighted_violation"] = f"{100 * s['weighted_share_violation']:.1f}%"
  out["D5.violations_depth1plus"] = f"{100 * s['weighted_share_of_violations_depth_1plus']:.1f}%"
  out["D5.violations_transition"] = f"{100 * s['weighted_share_of_violations_transition_evidence']:.1f}%"
  return out


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--tag", default="v13")
  args = parser.parse_args(argv)
  values = {**d2_values(args.tag)}
  try:
    values.update(d5_values())
  except FileNotFoundError:
    pass
  try:
    values.update(d3d6_values(args.tag))
  except FileNotFoundError as error:
    values["D3/D6"] = f"missing ({error.filename})"
  lines = [f"# Paper values, tag `{args.tag}`", "", "| KEY | value |", "|---|---|"]
  lines += [f"| {k} | {v} |" for k, v in values.items()]
  text = "\n".join(lines) + "\n"
  (ROOT / "results" / f"PAPER_VALUES-{args.tag}.md").write_text(text, encoding="utf-8")
  print(text)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
