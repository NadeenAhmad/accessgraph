"""D2 with AccessGraph integrated into an existing rule tool: AccessGraph + axe-core on ALL cases of the shared
criteria (1.1.1, 2.4.4, 3.3.1), including the syntactic cases AccessGraph leaves to rule tools.

  python -m eval.d2_combined [--tag v3]

A case is flagged by "AccessGraph + axe" when AccessGraph flags it (in-scope cases; AccessGraph is not run on the
others) or axe-core flags it (InterA11y's saved axe-core predictions on the same pages, same harness). Compared on
the same cases with InterA11y (full, GPT-6 Luna), axe-core alone and AccessGraph alone. Counting as in
InterA11y's `parse` (flagged vs label; missing predictions count as not flagged). Writes results/d2/COMBINED.md.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from eval.paths import INTERA11Y  # noqa: E402
PRIVATE = ROOT / "runs" / "w4a-d2" / "runs"
CRITERIA = ("1.1.1", "2.4.4", "3.3.1")


def _rows(path: Path) -> list[dict]:
  with path.open(encoding="utf-8", newline="") as stream:
    return list(csv.DictReader(stream))


def _metrics(flags: dict[str, bool], labels: dict[str, bool]) -> str:
  tp = sum(1 for c, pos in labels.items() if pos and flags.get(c))
  fp = sum(1 for c, pos in labels.items() if not pos and flags.get(c))
  fn = sum(1 for c, pos in labels.items() if pos and not flags.get(c))
  p = tp / (tp + fp) if tp + fp else 0.0
  r = tp / (tp + fn) if tp + fn else 0.0
  f = 2 * p * r / (p + r) if p + r else 0.0
  return f"| {p:.3f} | {r:.3f} | {f:.3f} | {tp} | {fp} | {fn} |"


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--tag", default="v3")
  args = parser.parse_args(argv)
  lines = ["# D2, all cases of the shared criteria: AccessGraph integrated with axe-core", "",
           "AccessGraph judges the semantic (in-scope) cases; axe-core's saved results cover all cases. "
           f"AccessGraph runs: tag `{args.tag}`.", ""]
  for dataset in ("expert", "conformance"):
    labels_rows = [r for r in _rows(INTERA11Y / "datasets" / dataset / "elements.csv") if r["sc"] in CRITERIA]
    labels = {r["case_id"]: r["label"] == "1" for r in labels_rows}
    saved = _rows(INTERA11Y / "results" / f"{dataset}-predictions.csv")
    pick = lambda system, model, condition=None: {  # noqa: E731
      r["case_id"]: r["flagged"] == "1" for r in saved
      if r["system"] == system and r["model"] == model and (condition is None or r["condition"] == condition)
      and r["case_id"] in labels}
    axe = pick("axe", "none")
    intera11y = pick("intera11y", "luna", "full")
    runs = sorted(PRIVATE.glob(f"{dataset}-{args.tag}-run-*"))
    pos = sum(labels.values())
    lines += [f"## {dataset}: {len(labels)} cases ({pos} violations)", "",
              "| System | P | R | F1 | TP | FP | FN |", "|---|---|---|---|---|---|---|",
              f"| InterA11y (full, GPT-6 Luna) {_metrics(intera11y, labels)}",
              f"| axe-core {_metrics(axe, labels)}"]
    for run in runs:
      if not (run / "predictions.csv").exists():
        continue
      ag = {r["case_id"]: r["flagged"] == "1" for r in _rows(run / "predictions.csv") if r["case_id"] in labels}
      combined = {c: bool(ag.get(c) or axe.get(c)) for c in labels}
      lines.append(f"| AccessGraph alone ({run.name}) {_metrics(ag, labels)}")
      lines.append(f"| AccessGraph + axe-core ({run.name}) {_metrics(combined, labels)}")
    lines.append("")
  out = ROOT / "results" / "d2" / "COMBINED.md"
  out.write_text("\n".join(lines) + "\n", encoding="utf-8")
  print("\n".join(lines))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
