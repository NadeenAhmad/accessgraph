"""AccessGuru, as published (through InterA11y's adapter), on recorded states (regime R2; spec Section 5).

  python -m eval.adapters.accessguru_state --cases bs-sem-114,co-sem-058 [--model openai/gpt-6-luna] [--stage dev]

One AccessGuru run per recorded state (its own design: one model call over the page's HTML and screenshot, plus
axe-core), the state served at its own route with the app's scripts disabled (eval/adapters/recorded.py). Each case
in the state is then decided from the findings: a finding counts when it names one of the case's criteria on the
case's element (or, for page-level types, anywhere). Cost is what OpenRouter reports; it is charged to the ledger.
Results: results/<dataset>/accessguru/<model>/<case>.json and states/<state>.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.adapters.recorded import finding_matches, items, serve_state  # noqa: E402
from eval.cost import CostLedger  # noqa: E402
from eval.intera11y_dev import INTERA11Y, _env  # noqa: E402

EST_STATE_USD = 0.01


def _env_with_driver() -> dict:
  """InterA11y's environment, with a ChromeDriver that matches the installed Chrome first on PATH.

  The machine's /usr/local/bin/chromedriver is older than its Chrome; Selenium Manager (bundled with Selenium)
  fetches the matching driver once and caches it.
  """
  manager = next((INTERA11Y / ".venv" / "lib").glob("python*/site-packages/selenium/webdriver/common/*/selenium-manager"))
  done = subprocess.run([str(manager), "--browser", "chrome", "--skip-driver-in-path", "--output", "json"],
                        capture_output=True, text=True, timeout=300)
  driver = json.loads(done.stdout)["result"]["driver_path"]
  env = _env()
  env["PATH"] = f"{Path(driver).parent}:{env.get('PATH', '')}"
  return env


def run_state(item: dict, model: str, out: Path) -> dict:
  if out.exists():
    return json.loads(out.read_text(encoding="utf-8"))
  server, url = serve_state(item)
  started = time.perf_counter()
  try:
    with tempfile.TemporaryDirectory(prefix="accessguru-") as tmp:
      request, result_file = Path(tmp) / "request.json", Path(tmp) / "result.json"
      entry = {"case_id": item["state_key"], "sc": "", "url": url, "scope": "page", "xpath": ""}
      request.write_text(json.dumps({"entry": entry, "options": {
        "model": model, "effort": "high", "output_dir": str(out.parent / "artifacts" / item["state_key"])}}))
      (out.parent / "artifacts" / item["state_key"]).mkdir(parents=True, exist_ok=True)
      done = subprocess.run([str(INTERA11Y / ".venv" / "bin" / "python"), str(ROOT / "eval/adapters/_accessguru_worker.py"),
                             str(request), str(result_file)], cwd=INTERA11Y, env=_env_with_driver(), capture_output=True,
                            text=True, timeout=1800)
      raw = json.loads(result_file.read_text()) if result_file.exists() else {
        "state": "error", "rows": [], "error": done.stderr[-800:]}
  finally:
    server.shutdown()
  usage = raw.get("usage") or {}
  result = {"state_key": item["state_key"], "url_path": "/" + url.split("/", 3)[-1], "state": raw.get("state"),
            "error": raw.get("error"), "rows": [{"sc": r.get("sc"), "xpath": r.get("xpath"), "ruleId": r.get("ruleId"),
                                                 "reason": str(r.get("reason") or "")[:300]} for r in raw.get("rows") or []],
            "cost_usd": float(usage.get("reportedApiCostUsd") or usage.get("apiCostUsd") or 0.0),
            "calls": usage.get("calls"), "seconds": round(time.perf_counter() - started, 1)}
  out.parent.mkdir(parents=True, exist_ok=True)
  out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
  return result


def decide(item: dict, state: dict) -> str:
  if state.get("state") != "complete":
    return "error"
  for row in state["rows"]:
    scs = row["sc"] if isinstance(row["sc"], list) else [row["sc"]]
    if any(finding_matches(item, str(sc), row.get("xpath")) for sc in scs):
      return "violation"
  return "no_violation"


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--cases", default="")
  parser.add_argument("--model", default="openai/gpt-6-luna")
  parser.add_argument("--stage", default="dev")
  parser.add_argument("--dataset", default="dev")
  args = parser.parse_args(argv)
  wanted = set(filter(None, args.cases.split(",")))
  from eval.external_check import verify
  verify()  # the clones must carry exactly the frozen patches
  ledger = CostLedger(ROOT / "results" / "cost_ledger.json")
  out_dir = ROOT / "results" / args.dataset / "accessguru" / args.model.replace("/", "-")
  by_state = defaultdict(list)
  for item in items():
    if (not wanted or item["case_id"] in wanted) and item["state_id"]:
      item["state_key"] = hashlib.sha1(f"{item['run_dir']}|{item['state_id']}".encode()).hexdigest()[:12]
      by_state[item["state_key"]].append(item)
  for key, group in by_state.items():
    path = out_dir / "states" / f"{key}.json"
    fresh = not path.exists()
    if fresh:
      ledger.check(args.stage, EST_STATE_USD)
    state = run_state(group[0], args.model, path)
    if fresh and state["cost_usd"]:
      ledger.charge(args.stage, state["cost_usd"], run_id=f"accessguru-{args.model}", note=f"accessguru state {key}")
    for item in group:
      result = {"case_id": item["case_id"], "candidate_type": item["candidate_type"], "state_key": key,
                "handover": item["handover"], "prediction": decide(item, state),
                "cost_usd": state["cost_usd"] / len(group)}
      (out_dir / f"{item['case_id']}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
      print(item["case_id"], result["prediction"], f"state ${state['cost_usd']:.4f}", state.get("error") or "", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
