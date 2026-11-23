"""Pre-record the D2 pages in parallel before the runs (optional; makes `python -m eval.d2 --run ...` fast).

  python -m eval.d2_prerecord --dataset expert|conformance [--workers 3] [--reverse] [--stage fix_round5]

Records each page (conformance: one exploration per page) or each case (expert: one exploration per case, directed
at its element) with the frozen code into the folders the InterA11y worker uses (runs/w4a-d2/pages/<slug>-<sha1[:8]>
and, for element-scoped cases, <...>--<case>), so the runs reuse them. Pages already recorded by the same code are
skipped (several copies, e.g. one --reverse, can run at once; a lock keeps them from recording the same page twice).
The explorer's model calls are paid and cached, under the given stage.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = "fix_round5"


def _folder(page: str, case: str = "", xpath: str = "") -> Path:
  slug = re.sub(r"[^A-Za-z0-9]+", "-", page).strip("-").lower()[-120:] + "-" + hashlib.sha1(page.encode()).hexdigest()[:8]
  run_dir = (ROOT / "runs/w4a-d2/pages" / slug).resolve()
  if xpath:
    run_dir = run_dir.parent / f"{run_dir.name}--{re.sub(r'[^A-Za-z0-9]+', '-', case).strip('-')[:60]}"
  return run_dir


def _one(job: tuple[str, str, str, str]) -> str:
  from eval.adapters.ag_single import record
  from eval.paths import INTERA11Y
  page, case, xpath, stage = job
  try:
    record((INTERA11Y / page).resolve().as_uri(), _folder(page, case, xpath), None, focus=[xpath] if xpath else [], stage=stage)
    return f"ok {case or page}"
  except Exception as error:  # a failed page is recorded again by the run itself
    return f"ERR {case or page} {type(error).__name__}: {str(error)[:150]}"


def main(argv: list[str] | None = None) -> int:
  from eval.d2 import kept
  from eval.paths import INTERA11Y
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--dataset", choices=("expert", "conformance"), required=True)
  parser.add_argument("--workers", type=int, default=3)
  parser.add_argument("--reverse", action="store_true", help="work from the end of the list (for a second copy)")
  parser.add_argument("--stage", default=STAGE)
  args = parser.parse_args(argv)
  ids = set(kept(args.dataset, scope="full"))
  rows = [r for r in csv.DictReader((INTERA11Y / f"datasets/{args.dataset}/elements.csv").open(encoding="utf-8")) if r["case_id"] in ids]
  if args.dataset == "expert":
    jobs = sorted({(r["page"], r["case_id"], r["xpath"] if r["scope"] == "element" else "", args.stage) for r in rows},
                  key=lambda j: j[1], reverse=args.reverse)
  else:
    jobs = sorted({(r["page"], "", "", args.stage) for r in rows}, reverse=args.reverse)
  print(len(jobs), "recordings", flush=True)
  with ProcessPoolExecutor(args.workers) as pool:
    for i, message in enumerate(pool.map(_one, jobs), 1):
      if message.startswith("ERR") or i % 25 == 0:
        print(i, message, flush=True)
  print("done", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
