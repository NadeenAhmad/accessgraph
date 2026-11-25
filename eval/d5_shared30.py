"""D5 shared set (PI decision 2026-11-25): one labeller (main) labels all items, and three further labellers label the
same 30 items, so that agreement is measured among four people. Free.

  python -m eval.d5_shared30

The 30 are a seeded random subset of the 50 items first marked for a single second labeller (`double`): 18 of its 30
items AccessGraph judged violations and 12 of its 20 others, keeping the 60/40 split. Adds the column `shared` (1 for
the 30) to results/d5/export165/key_do_not_share.csv and labelling_sheet.csv; `double` stays as it was. Re-running
gives the same 30.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "d5" / "export165"
SEED = 20261125
SHARED_V, SHARED_O = 18, 12


def _rows(path: Path) -> list[dict]:
  with path.open(encoding="utf-8", newline="") as stream:
    return list(csv.DictReader(stream))


def _write(path: Path, rows: list[dict], shared: set[str]) -> None:
  fields = [f for f in rows[0] if f != "shared"] + ["shared"]
  with path.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows({**r, "shared": int(r["item_id"] in shared)} for r in rows)


def main() -> int:
  key = sorted(_rows(OUT / "key_do_not_share.csv"), key=lambda r: int(r["order"]))
  double = [r for r in key if r["double"] == "1"]
  violations = [r["item_id"] for r in double if r["ag_decision"] == "violation"]
  others = [r["item_id"] for r in double if r["ag_decision"] != "violation"]
  if len(violations) < SHARED_V or len(others) < SHARED_O:
    raise SystemExit(f"double set has {len(violations)} violations / {len(others)} others; need {SHARED_V} / {SHARED_O}")
  rng = random.Random(SEED)
  shared = set(rng.sample(violations, SHARED_V)) | set(rng.sample(others, SHARED_O))
  _write(OUT / "key_do_not_share.csv", key, shared)
  _write(OUT / "labelling_sheet.csv", sorted(_rows(OUT / "labelling_sheet.csv"), key=lambda r: int(r["order"])), shared)
  print(f"shared: {len(shared)} items ({SHARED_V} violations + {SHARED_O} others) of the {len(double)} double-labelled")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
