"""D5 expert set of 165 items (PI decision 2026-11-20): every item AccessGraph judged a violation (65) plus a seeded
random 100 of the other exported items. Free.

  python -m eval.d5_export165

Reads results/d5/export (300 items: all violations of the 600-candidate sample plus 235 of the 535 others) and writes
results/d5/export165 with the same item folders and IDs. Weights: violations keep export_weight 1; for the others the
export weight becomes (others in the sample) / 100, so the 100 stand for all 535 non-violation verdicts of the sample
(sample_weight then scales the sample to all candidates). `order` is the shuffled order experts see them in;
`double` marks the 50 items for the second labeller (30 violations + 20 others, seeded).
"""
from __future__ import annotations

import csv
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "d5" / "export"
OUT = ROOT / "results" / "d5" / "export165"
SEED = 20261120
N_OTHERS, DOUBLE_V, DOUBLE_O = 100, 30, 20


def _rows(path: Path) -> list[dict]:
  with path.open(encoding="utf-8", newline="") as stream:
    return list(csv.DictReader(stream))


def main() -> int:
  key = _rows(SRC / "key_do_not_share.csv")
  rng = random.Random(SEED)
  violations = [r for r in key if r["ag_decision"] == "violation"]
  others = [r for r in key if r["ag_decision"] != "violation"]
  others_in_sample = round(float(others[0]["export_weight"]) * len(others))  # 535: all non-violations of the 600
  take = rng.sample(others, N_OTHERS)
  chosen = violations + take
  rng.shuffle(chosen)
  double = set(r["item_id"] for r in rng.sample(violations, DOUBLE_V)) | set(r["item_id"] for r in rng.sample(take, DOUBLE_O))
  if OUT.exists():
    shutil.rmtree(OUT)
  (OUT / "items").mkdir(parents=True)
  sheet = {r["item_id"]: r for r in _rows(SRC / "labelling_sheet.csv")}
  new_key, new_sheet = [], []
  for order, r in enumerate(chosen, 1):
    shutil.copytree(SRC / "items" / r["item_id"], OUT / "items" / r["item_id"])
    weight = 1.0 if r in violations else others_in_sample / N_OTHERS
    new_key.append({**r, "order": order, "export_weight": weight, "double": int(r["item_id"] in double)})
    new_sheet.append({**sheet[r["item_id"]], "order": order, "double": int(r["item_id"] in double)})
  for name, data in (("key_do_not_share.csv", new_key), ("labelling_sheet.csv", new_sheet)):
    with (OUT / name).open("w", newline="", encoding="utf-8") as stream:
      writer = csv.DictWriter(stream, fieldnames=list(data[0]))
      writer.writeheader()
      writer.writerows(data)
  print(f"{len(chosen)} items: {len(violations)} violations + {len(take)} of {len(others)} others "
        f"(others stand for {others_in_sample}); {len(double)} double-labelled")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
