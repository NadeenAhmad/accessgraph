"""Rule engines on recorded states, through the runners in Rampa's harness (spec Section 5, Baselines; regime R2).

  python -m eval.adapters.rule_tools_state --cases bs-sem-114,co-sem-058 [--tools axe,alfa,qualweb,ibm,pa11y]

Each case's state is served at its own route with the app's scripts disabled (eval/adapters/recorded.py), and
Rampa's bench (`bench/lib/drive.mjs`, pinned df32363) runs each rule engine over those pages exactly as in its own
benchmark: same modules, same versions, same reading of definite failures and review items. No model, no cost.

The bench's records keep, per page, the criteria a tool failed (with its rule ids), not the elements. A case counts
as flagged by a tool when the tool reports a definite failure on one of the case's criteria on the case's page
(a coarser, more generous test than element matching; used for H5, "cases no rule tool flags").
Results: results/<dataset>/rule_tools/<tool>.jsonl (the bench's records) and <tool>.csv (one row per case).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.adapters.rampa_state import browser_path  # noqa: E402
from eval.adapters.recorded import items, serve_state  # noqa: E402

from eval.paths import RAMPA  # noqa: E402
BENCH = RAMPA / "bench"
TOOLS = ("axe", "alfa", "qualweb", "ibm", "pa11y")


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--cases", default="")
  parser.add_argument("--tools", default=",".join(TOOLS))
  parser.add_argument("--dataset", default="dev")
  args = parser.parse_args(argv)
  wanted = set(filter(None, args.cases.split(",")))
  selected = [i for i in items() if i["state_id"] and (not wanted or i["case_id"] in wanted)]
  out_dir = ROOT / "results" / args.dataset / "rule_tools"
  out_dir.mkdir(parents=True, exist_ok=True)
  servers, pages = [], []
  try:
    for item in selected:
      server, url = serve_state(item)
      servers.append(server)
      pages.append({"id": item["case_id"], "url": url, "kind": "w4a-state"})
    pages_file = out_dir / "pages.json"
    pages_file.write_text(json.dumps(pages), encoding="utf-8")
    env = dict(os.environ, BENCH_BROWSER_PATH=browser_path())
    for tool in filter(None, args.tools.split(",")):
      records = out_dir / f"{tool}.jsonl"
      records.unlink(missing_ok=True)  # pages are re-served on new ports each time: no resume across runs
      done = subprocess.run(["node", "lib/drive.mjs", tool, "--pages", str(pages_file), "--out", str(records),
                             "--meta", str(out_dir / f"{tool}.meta.json"), "--workers", "2"],
                            cwd=BENCH, env=env, capture_output=True, text=True, timeout=3600)
      by_id = {}
      if records.exists():
        by_id = {r["id"]: r for r in (json.loads(l) for l in records.read_text().splitlines() if l.strip())}
      with (out_dir / f"{tool}.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("case_id", "tool", "flagged", "review", "rules", "error"))
        writer.writeheader()
        for item in selected:
          r = by_id.get(item["case_id"]) or {"error": f"no record (exit {done.returncode})"}
          fail, review = r.get("fail") or {}, r.get("review") or {}
          writer.writerow({"case_id": item["case_id"], "tool": tool,
                           "flagged": int(any(fail.get(sc) for sc in item["criteria"])),
                           "review": int(any(review.get(sc) for sc in item["criteria"])),
                           "rules": ";".join(sorted({x for sc in item["criteria"] for x in fail.get(sc, [])})),
                           "error": r.get("error") or ""})
      errors = sum(1 for r in by_id.values() if r.get("error"))
      print(tool, f"records {len(by_id)}/{len(selected)}", f"errors {errors}", done.stderr.strip()[-300:], flush=True)
  finally:
    for server in servers:
      server.shutdown()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
