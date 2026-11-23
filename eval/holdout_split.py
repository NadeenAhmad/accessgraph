"""Practice / untouched split of the external test cases (decided 2026-11-16, before any case-level error analysis).

  python -m eval.holdout_split

After the first D2/D3/D6 runs, the PI decided to fix AccessGraph's general weaknesses found there. So that the paper
can show the fixes are general, half of the cases not yet inspected one by one are set aside now and not looked at
until the final runs: D2 conformance (stratified by criterion), D3 ACT test cases (by rule and expected outcome),
D6 pairs (by corruptor). D2 expert cases were already inspected (the link misses) and are all practice.
Fixed seed; the file is committed before any further analysis. Output: results/holdout_split.json.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 202611161
OUT = ROOT / "results" / "holdout_split.json"


def _split(items: list[tuple[str, str]], rng: random.Random) -> tuple[list[str], list[str]]:
  groups = defaultdict(list)
  for case_id, stratum in sorted(items):
    groups[stratum].append(case_id)
  practice, held = [], []
  for stratum in sorted(groups):
    ids = groups[stratum]
    rng.shuffle(ids)
    half = len(ids) // 2
    practice += ids[:half]
    held += ids[half:]
  return sorted(practice), sorted(held)


def main() -> int:
  if OUT.exists():
    print(f"{OUT} exists; the split is fixed and is never redrawn")
    return 1
  rng = random.Random(SEED)
  with (ROOT / "results/d2/scope.csv").open(encoding="utf-8") as stream:
    scope = [r for r in csv.DictReader(stream) if r["keep"] == "1"]
  d2_conf = _split([(r["case_id"], r["sc"]) for r in scope if r["dataset"] == "conformance"], rng)
  from eval.paths import RAMPA
  stored = RAMPA / "bench/results/2026-10-11/cases.json"
  rules = ("qt1vmo", "5effbb", "b49b2e", "c4a8a4", "ucwvc8", "off6ek", "36b590")
  act = [c for c in json.loads(stored.read_text())["cases"] if c["ruleId"] in rules]
  d3 = _split([(c["id"], f"{c['ruleId']}|{c['expected']}") for c in act], rng)
  pairs = json.loads((ROOT / "results/d3d6/pairs.json").read_text())["pairs"]
  d6 = _split([(p["corruptedId"], p["corruptor"]) for p in pairs], rng)
  split = {
    "seed": SEED, "decided": "2026-11-16, before case-level error analysis of these sets",
    "D2-expert": {"practice": sorted(r["case_id"] for r in scope if r["dataset"] == "expert"), "untouched": []},
    "D2-conformance": {"practice": d2_conf[0], "untouched": d2_conf[1]},
    "D3": {"practice": d3[0], "untouched": d3[1]},
    "D6": {"practice": d6[0], "untouched": d6[1], "unit": "pair (corrupted id)"},
  }
  OUT.write_text(json.dumps(split, indent=1) + "\n", encoding="utf-8")
  for k, v in split.items():
    if isinstance(v, dict):
      print(k, "practice", len(v["practice"]), "untouched", len(v["untouched"]))
  return 0


if __name__ == "__main__":
  sys.exit(main())
