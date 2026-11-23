"""Dev comparison table: every scored system on the full dev set and on the cases it shares with InterA11y.

  python -m eval.dev_compare

Reads results/dev/predictions/*.csv and results/dev/gold.csv; writes results/dev/COMPARISON.md. The shared subset
is the gold rows of the types InterA11y covers natively (1.1.1, 2.4.4, 3.3.1). Paired test on that subset: exact
McNemar on per-case correctness (strict view), AccessGraph vs InterA11y with the same model.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.intera11y_dev import type_to_sc  # noqa: E402
from eval.predictions import read_gold, read_predictions  # noqa: E402
from eval.scoring import join, score_cases  # noqa: E402
from eval.stats import mcnemar_exact, wilson_ci  # noqa: E402

DEV = ROOT / "results" / "dev"
POSITIVE = {"violation"}


def _correct(expected: str, prediction: str) -> bool:
  return (prediction in POSITIVE) == (expected == "violation")


def _fmt(x) -> str:
  return "–" if x is None else f"{x:.3f}"


def main() -> int:
  gold = read_gold(DEV / "gold.csv")
  shared_types = set(type_to_sc())
  shared = [g for g in gold if g.candidate_type in shared_types]
  systems = {}
  for path in sorted((DEV / "predictions").glob("*.csv")):
    rows = read_predictions(path)
    if rows:
      systems[path.stem] = ({r.case_id: r.prediction for r in rows}, {r.case_id: r.cost_usd for r in rows}, rows[0])
  lines = ["# Dev comparison (137 thesis variants + clean twins)", "",
           "Strict view (uncertain = negative). Cost = judge cost of the run over the cases it judged.", ""]
  for title, cases in (("All dev cases", gold), ("Cases InterA11y covers (1.1.1, 2.4.4, 3.3.1)", shared)):
    ids = {c.case_id for c in cases}
    pos = sum(c.expected == "violation" for c in cases)
    lines += [f"## {title}: {len(cases)} cases ({pos} violations, {len(cases) - pos} clean)", "",
              "| Run | Model | P | R (95% CI) | F1 | FP | uncertain | cost |", "|---|---|---|---|---|---|---|---|"]
    for name, (preds, cost, first) in systems.items():
      if not ids <= set(preds):
        continue
      joined = join(cases, preds)
      m = score_cases(joined, "strict")
      lo, hi = wilson_ci(m.tp, m.tp + m.fn)
      unc = sum(preds[c.case_id] == "uncertain" for c in cases)
      subset_cost = sum(cost.get(c.case_id, 0.0) for c in cases)
      lines.append(f"| {name} | {first.model} | {_fmt(m.precision)} | {_fmt(m.recall)} ({lo:.2f}–{hi:.2f}) | "
                   f"{_fmt(m.f1)} | {m.fp} | {unc} | ${subset_cost:.3f} |")
    lines.append("")
  # paired tests on the shared subset: each AccessGraph run vs each InterA11y run with the same model
  lines += ["## Paired test on the shared cases (exact McNemar, strict correctness)", "",
            "| AccessGraph run | InterA11y run | AG right, IA wrong | AG wrong, IA right | p |", "|---|---|---|---|---|"]
  ids = [c.case_id for c in shared]
  expected = {c.case_id: c.expected for c in shared}
  for ag, (ag_p, _, ag_first) in systems.items():
    if ag.startswith("intera11y") or not set(ids) <= set(ag_p):
      continue
    for ia, (ia_p, _, ia_first) in systems.items():
      if not ia.startswith("intera11y") or ia_first.model != ag_first.model or not set(ids) <= set(ia_p):
        continue
      b = sum(_correct(expected[i], ag_p[i]) and not _correct(expected[i], ia_p[i]) for i in ids)
      c = sum(not _correct(expected[i], ag_p[i]) and _correct(expected[i], ia_p[i]) for i in ids)
      lines.append(f"| {ag} | {ia} | {b} | {c} | {mcnemar_exact(b, c):.3f} |")
  (DEV / "COMPARISON.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
  print("\n".join(lines))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
