"""After the D5 re-judging with the final version (PI 2026-11-23, option A), the 165 expert items are drawn again and
get new item ids. Items whose candidate was already captured reuse that capture (the screens do not depend on the
verdict); the others are listed for a new capture. Free.

  python -m eval.d5_review_remap      # prints the item ids that still need `python -m eval.d5_review capture`

Old captures: results/d5/review-v12/items (keyed by the v12 export ids, mapped through results/d5-v12/export165).
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_KEY = ROOT / "results" / "d5-v12" / "export165" / "key_do_not_share.csv"
OLD_CAPTURES = ROOT / "results" / "d5" / "review-v12" / "items"
NEW_KEY = ROOT / "results" / "d5" / "export165" / "key_do_not_share.csv"
CAPTURED = ROOT / "results" / "d5" / "review" / "items"


def main() -> int:
  old = {(r["app"], r["candidate_id"]): r["item_id"] for r in csv.DictReader(OLD_KEY.open(encoding="utf-8"))}
  CAPTURED.mkdir(parents=True, exist_ok=True)
  missing = []
  for r in csv.DictReader(NEW_KEY.open(encoding="utf-8")):
    previous = old.get((r["app"], r["candidate_id"]))
    target = CAPTURED / r["item_id"]
    if previous and (OLD_CAPTURES / previous / "meta.json").exists():
      if target.exists():
        shutil.rmtree(target)
      shutil.copytree(OLD_CAPTURES / previous, target)
      meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
      meta.update({"item_id": r["item_id"], "reused_from": previous})
      (target / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
      missing.append(r["item_id"])
  print(" ".join(missing))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
