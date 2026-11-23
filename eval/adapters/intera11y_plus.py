"""InterA11y+ (InterA11y with the extended rubrics 2.4.2 and 2.4.6) on recorded states (regime R2).

  python -m eval.adapters.intera11y_plus --cases co-sem-058,bs-sem-118 [--model openai/gpt-6-luna] [--stage dev_intera11y]

InterA11y's own runtime (`runtime/run-intera11y.cjs`, condition "full", effort high) on each case's state, served
at its own route with the app's scripts disabled (eval/adapters/recorded.py). Its native criteria cover image alt
(1.1.1), link text (2.4.4) and error messages (3.3.1); the W4A rubrics add page titles (2.4.2) and headings, form
labels and button names (2.4.6), written in InterA11y's format from WCAG and ACT only (eval/patches/
intera11y-8dcf06e-w4a-rubrics.patch). Landmark and widget names are not covered (reported as not covered).

Element cases point InterA11y at the case's element (its own targets mechanism); page-title cases at the page.
Plain InterA11y is reported as the subset of its native criteria (spec). Cost is what OpenRouter reports to
InterA11y; it is charged to the cost ledger. Results: results/<dataset>/intera11y_plus/<model>/<case>.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.adapters.recorded import items, serve_state  # noqa: E402
from eval.cost import CostLedger  # noqa: E402
from eval.intera11y_dev import INTERA11Y, _env, prediction  # noqa: E402

NATIVE = {"image-alt-not-descriptive": "1.1.1", "link-text-mismatch": "2.4.4", "error-message-mismatch": "3.3.1"}
ADDED = {"page-title-not-descriptive": "2.4.2", "heading-not-descriptive": "2.4.6", "form-label-mismatch": "2.4.6",
         "button-label-mismatch": "2.4.6"}
TYPE_TO_SC = {**NATIVE, **ADDED}
EST_CASE_USD = 0.012


def run_case(item: dict, model: str, stage: str, ledger: CostLedger, out_dir: Path) -> dict:
  out = out_dir / f"{item['case_id']}.json"
  if out.exists():
    return json.loads(out.read_text(encoding="utf-8"))
  sc = TYPE_TO_SC[item["candidate_type"]]
  if not item["state_id"]:
    result = {"case_id": item["case_id"], "sc": sc, "state": "no_state", "prediction": "not_applicable"}
  else:
    ledger.check(stage, EST_CASE_USD)
    targets = [{"scope": "page"}] if item["page_level"] else [{"scope": "element", "xpath": x} for x in item["xpaths"]]
    started = time.perf_counter()

    def run(url: str, env: dict) -> dict:
      payload = {"url": url, "sc": sc, "targets": targets, "condition": "full", "model": model,
                 "outputDir": str(out_dir / "artifacts" / item["case_id"]),
                 "options": {"model": model, "effort": "high", "llmConcurrency": 1}}
      process = subprocess.run(["node", "runtime/run-intera11y.cjs"], input=json.dumps(payload), text=True,
                               capture_output=True, cwd=INTERA11Y, env=env, timeout=1800)
      try:
        return json.loads(process.stdout.strip().splitlines()[-1])
      except (ValueError, IndexError):
        return {"state": "error", "flagged": False, "error": "no JSON: " + process.stderr[-600:]}

    raw, handover = None, item["handover"]
    live = item.get("live")  # {"base_url", "init_script"}: the app runs locally; every page InterA11y opens is
    if live:                 # replayed to the state (patch eval/patches/intera11y-8dcf06e-live-replay.patch)
      from eval.adapters.live_state import ReplayService, _graph
      service = ReplayService(ROOT / item["run_dir"], item["state_id"], live.get("base_url"))
      graph, _start, start_url = _graph(ROOT / item["run_dir"], live.get("base_url"))
      url = str(graph.nodes.get(item["state_id"], {}).get("url") or start_url)
      env = {**_env(), "W4A_REPLAY_URL": service.url, **({"W4A_INIT_SCRIPT": live["init_script"]}
                                                          if live.get("init_script") else {})}
      try:
        raw = run(url, env)
      finally:
        service.close()
      if raw.get("state") == "error" and "W4A replay failed" in str(raw.get("error")):
        print(f"{item['case_id']}: live handover failed ({str(raw.get('error'))[:160]}); static fallback", flush=True)
        raw, handover = None, "static-fallback"
      else:
        handover = "live"
    if raw is None:
      server, url = serve_state(item)
      try:
        raw = run(url, _env())
      finally:
        server.shutdown()
    usage = raw.get("usage") or {}
    cost = float(usage.get("costUsd") or 0.0)
    if cost:
      ledger.charge(stage, cost, run_id=f"intera11y-plus-{model}", note=f"intera11y+ {item['case_id']}")
    result = {"case_id": item["case_id"], "candidate_type": item["candidate_type"], "sc": sc,
              "rubric": "native" if item["candidate_type"] in NATIVE else "w4a", "handover": handover,
              "url_path": "/" + url.split("/", 3)[-1], "xpaths": item["xpaths"], "state": raw.get("state"),
              "flagged": bool(raw.get("flagged")), "prediction": prediction(raw), "verdict": raw.get("verdict"),
              "findings": [{k: f.get(k) for k in ("xpath", "status", "reason", "source")} for f in raw.get("findings") or []],
              "error": raw.get("error"), "cost_usd": cost, "calls": usage.get("calls"),
              "seconds": round(time.perf_counter() - started, 1)}
  out.parent.mkdir(parents=True, exist_ok=True)
  out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
  return result


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--cases", default="")
  parser.add_argument("--model", default="openai/gpt-6-luna")
  parser.add_argument("--stage", default="dev_intera11y")
  parser.add_argument("--dataset", default="dev")
  args = parser.parse_args(argv)
  wanted = set(filter(None, args.cases.split(",")))
  selected = [i for i in items(types=set(TYPE_TO_SC)) if not wanted or i["case_id"] in wanted]
  from eval.external_check import verify
  verify()  # the clones must carry exactly the frozen patches
  ledger = CostLedger(ROOT / "results" / "cost_ledger.json")
  out_dir = ROOT / "results" / args.dataset / "intera11y_plus" / args.model.replace("/", "-")
  for item in selected:
    result = run_case(item, args.model, args.stage, ledger, out_dir)
    print(item["case_id"], result.get("sc"), result.get("state"), result.get("prediction"),
          f"${result.get('cost_usd') or 0:.4f}", result.get("error") or "", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
