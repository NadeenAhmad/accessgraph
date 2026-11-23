"""Early InterA11y comparison on dev (Phase 3): InterA11y judges the same recorded states as AccessGraph.

  python -m eval.intera11y_dev --model anthropic/claude-haiku-5.5 --dry-run
  python -m eval.intera11y_dev --model anthropic/claude-haiku-5.5 [--limit 3]

Cases: the dev gold rows (seeded and clean twin) whose type maps to a criterion InterA11y has natively
(`external.intera11y` in eval/mappings/taxonomy_sc_rules.yaml: 1.1.1, 2.4.4, 3.3.1).

How a state is handed over: the recorded state's DOM is served over HTTP next to the app's built assets, with the
app's scripts disabled so the SPA does not re-render (evaluation protocol, "Handing a recorded state to a live
tool", fallback 3). This is the setting of InterA11y's own Expert evaluation (saved webpages). InterA11y gets the
page URL, the criterion and the case's element XPath(s) as targets, exactly like its `run` command
(`runtime/run-intera11y.cjs`, condition `full`, reasoning effort high, its defaults). A case is flagged when
InterA11y reports a finding within a target, as in its own scoring.

Results: one JSON per case and model under results/dev/intera11y/<model>/ (committed; re-runs skip finished
cases), InterA11y's traces under runs/w4a-dev/intera11y-artifacts/ (local). Costs are InterA11y's own
OpenRouter-reported costs, charged to stage `dev_intera11y`.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from eval.cost import CostLedger, TopUpNeeded, preflight  # noqa: E402
from eval.predictions import PredictionRow, read_gold, write_rows  # noqa: E402
from eval.runlog import RunLog, new_run_id  # noqa: E402
from eval.scoring import breakdown, join, score_cases  # noqa: E402

from eval.paths import INTERA11Y  # noqa: E402
KEY_FILE = Path(os.environ.get("OPENROUTER_ENV_FILE", Path.home() / ".config" / "w4a" / "openrouter.env"))
RESULTS = ROOT / "results"
DEV = RESULTS / "dev"
STAGING = ROOT / "runs" / "w4a-dev" / "intera11y-pages"
ARTIFACTS = ROOT / "runs" / "w4a-dev" / "intera11y-artifacts"
APP_DIST = {"checkout-flow": ROOT / "benchmarks/local-spas/checkout-flow/dist",
            "booking-scheduler": ROOT / "benchmarks/local-spas/booking-scheduler/dist"}
STAGE = "dev_intera11y"
EST_CASE_USD = 0.012          # spec: about $0.009 per case; margin for reasoning tokens
# InterA11y reports 3.3.1 on the form field; our error-message candidates point at the message and the field.
FIELD_BUCKETS = ("forms", "form_controls", "inputs", "form_fields", "controls")


def type_to_sc() -> dict[str, str]:
  mapping = yaml.safe_load((ROOT / "eval/mappings/taxonomy_sc_rules.yaml").read_text(encoding="utf-8"))
  return {ctype: sc for sc, ctype in (mapping.get("external") or {}).get("intera11y", {}).items()}


def _slug(text: str) -> str:
  return "".join(ch if ch.isalnum() else "-" for ch in text).strip("-").lower()


def _candidates(run_dir: Path) -> dict[str, dict]:
  path = run_dir / "candidates" / "candidates.jsonl"
  return {c["candidate_id"]: c for c in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l)}


def _states(run_dir: Path) -> dict[str, dict]:
  return {s["state_id"]: s for s in json.loads((run_dir / "run_metadata.json").read_text())["states"]}


def _xpaths(candidate: dict, ctype: str) -> list[str]:
  refs = candidate.get("element_refs") or []
  paths = [refs[0].get("xpath")] if refs else []
  if ctype == "error-message-mismatch":
    paths += [r.get("xpath") for r in refs[1:] if r.get("bucket") in FIELD_BUCKETS]
  return [p for p in dict.fromkeys(paths) if p]


def targets() -> list[dict]:
  """One item per gold row of a shared type: the run, state and XPath(s) InterA11y is pointed at."""
  sc_by_type = type_to_sc()
  links = {l["case_id"]: l for l in (json.loads(x) for x in (DEV / "links.jsonl").read_text().splitlines() if x)}
  items = []
  for case in read_gold(DEV / "gold.csv"):
    if case.candidate_type not in sc_by_type:
      continue
    link = links[case.case_id]
    run_dir = ROOT / link["run_dir"]
    cands = _candidates(run_dir)
    source, state_id = None, None
    if link["candidate_ids"]:
      source = cands[link["candidate_ids"][0]]
      state_id = source["state_id"]
    elif case.case_kind == "clean_twin":  # no candidate on the clean element: point at the seeded element's place
      seeded = links[case.case_id.split("~")[0]]
      if seeded["candidate_ids"]:
        seeded_dir = ROOT / seeded["run_dir"]
        source = _candidates(seeded_dir)[seeded["candidate_ids"][0]]
        want = _states(seeded_dir)[source["state_id"]]
        state_id = next((sid for sid, s in _states(run_dir).items()
                         if s.get("benchmark_state_id") == want.get("benchmark_state_id")
                         and s.get("focused_state_name") == want.get("focused_state_name")), None)
    items.append({"case_id": case.case_id, "app": case.app, "candidate_type": case.candidate_type,
                  "sc": sc_by_type[case.candidate_type], "run_dir": link["run_dir"], "state_id": state_id,
                  "xpaths": _xpaths(source, case.candidate_type) if source else []})
  return items


def stage_page(item: dict) -> str:
  """Copy the state's DOM next to the app's built assets with the app scripts disabled; return its path."""
  root = STAGING / item["app"]
  if not (root / "assets").exists():
    shutil.copytree(APP_DIST[item["app"]], root, dirs_exist_ok=True)
  dom = (ROOT / item["run_dir"] / "states" / item["state_id"] / "dom.html").read_text(encoding="utf-8")
  # the first `type` attribute wins in HTML, so this disables every script without moving any element
  dom = re.sub(r"<script\b", '<script type="text/plain" data-w4a-disabled=""', dom, flags=re.IGNORECASE)
  name = f"w4a/{_slug(item['case_id'])}.html"
  (root / "w4a").mkdir(parents=True, exist_ok=True)
  (root / name).write_text(dom, encoding="utf-8")
  return name


class _Quiet(SimpleHTTPRequestHandler):
  def log_message(self, *args):
    pass


def serve(app: str) -> tuple[ThreadingHTTPServer, str]:
  (STAGING / app).mkdir(parents=True, exist_ok=True)
  server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(STAGING / app)))
  threading.Thread(target=server.serve_forever, daemon=True).start()
  return server, f"http://127.0.0.1:{server.server_address[1]}"


def _env() -> dict:
  env = dict(os.environ)
  # Haiku 5.5 and GPT-6 Luna reject temperature, and InterA11y requires every parameter it sends, so OpenRouter
  # refuses all its calls. Local patch eval/patches/intera11y-8dcf06e-omit-temperature.patch drops temperature
  # when this is set (our judge sends none either).
  env["W4A_OMIT_TEMPERATURE"] = "1"
  if "OPENROUTER_API_KEY" not in env and KEY_FILE.exists():
    for line in KEY_FILE.read_text().splitlines():
      if line.startswith("OPENROUTER_API_KEY="):
        env["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
  return env


def run_case(item: dict, url: str, model: str, out_dir: Path) -> dict:
  payload = {"url": url, "sc": item["sc"], "targets": [{"scope": "element", "xpath": x} for x in item["xpaths"]],
             "condition": "full", "model": model, "outputDir": str(out_dir),
             "options": {"model": model, "effort": "high", "llmConcurrency": 1}}
  started = time.perf_counter()
  process = subprocess.run(["node", "runtime/run-intera11y.cjs"], input=json.dumps(payload), text=True,
                           capture_output=True, cwd=INTERA11Y, env=_env(), timeout=1800)
  try:
    result = json.loads(process.stdout.strip().splitlines()[-1])
  except (ValueError, IndexError):
    result = {"state": "error", "flagged": False, "error": "no JSON: " + process.stderr[-600:]}
  usage = result.get("usage") or {}
  return {"case_id": item["case_id"], "sc": item["sc"], "model": model, "url_path": url.split("/", 3)[-1],
          "xpaths": item["xpaths"], "state": result.get("state"), "flagged": bool(result.get("flagged")),
          "verdict": result.get("verdict"), "findings": [{k: f.get(k) for k in ("xpath", "status", "reason", "source")}
                                                        for f in result.get("findings") or []],
          "error": result.get("error"), "cost_usd": usage.get("costUsd"), "calls": usage.get("calls"),
          "input_tokens": usage.get("inputTokens"), "output_tokens": usage.get("outputTokens"),
          "wall_seconds": round(time.perf_counter() - started, 1)}


def _out_of_credits(text: str | None) -> bool:
  return bool(text) and bool(re.search(r"\b402\b|insufficient credits|out of credits", text, re.IGNORECASE))


def prediction(result: dict | None) -> str:
  if not result:
    return "error"
  if result.get("state") == "error":
    return "error"
  return "violation" if result.get("flagged") else "no_violation"


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--model", required=True)
  parser.add_argument("--limit", type=int, default=None)
  parser.add_argument("--cases", nargs="*", default=None)
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--score-only", action="store_true")
  parser.add_argument("--workers", type=int, default=1, help="cases run at the same time (one browser each)")
  args = parser.parse_args(argv)

  items = [i for i in targets() if not args.cases or i["case_id"] in args.cases]
  out_root = DEV / "intera11y" / _slug(args.model)
  out_root.mkdir(parents=True, exist_ok=True)
  todo = [i for i in items if not (out_root / f"{_slug(i['case_id'])}.json").exists()]
  if args.limit:
    todo = todo[:args.limit]
  runnable = [i for i in todo if i["state_id"] and i["xpaths"]]
  ledger = CostLedger(RESULTS / "cost_ledger.json")
  log = RunLog(RESULTS)
  if not args.score_only:
    est = len(runnable) * EST_CASE_USD
    print(f"[dry-run] stage={STAGE} cases={len(items)} to_run={len(runnable)} (no target: "
          f"{len(todo) - len(runnable)}) est=${est:.3f} left=${ledger.remaining(STAGE):.3f}")
    if args.dry_run:
      return 0
    try:
      print(preflight(ledger, STAGE, est))
    except TopUpNeeded as exc:
      print(f"STOP: {exc}")
      return 3
    run_id = new_run_id("intera11y", "dev")
    row = log.start(run_id=run_id, stage=STAGE, system="InterA11y", dataset="dev", split="dev",
                    command=" ".join(["python -m eval.intera11y_dev", *(argv or sys.argv[1:])]))
    servers = {}
    state = {"spent": 0.0, "status": "done"}
    lock = threading.Lock()

    def one(item: dict) -> None:
      if state["status"] != "done":
        return
      if not (item["state_id"] and item["xpaths"]):
        log.exclude("dev", item["case_id"], "InterA11y: no recorded state or target element", rule="intera11y_dev")
        (out_root / f"{_slug(item['case_id'])}.json").write_text(json.dumps(
          {"case_id": item["case_id"], "state": "no_target", "flagged": False}, indent=2) + "\n")
        return
      ledger.check(STAGE, planned_usd=0.05)
      with lock:
        url = f"{servers[item['app']][1]}/{stage_page(item)}"
      result = run_case(item, url, args.model, ARTIFACTS / _slug(args.model) / _slug(item["case_id"]))
      cost = result.get("cost_usd")
      if cost is None and result.get("input_tokens"):
        cost = (result["input_tokens"] * 0.10 + (result.get("output_tokens") or 0) * 0.50) / 1e6
      if cost:
        ledger.charge(STAGE, cost, run_id=run_id, note=f"intera11y {args.model} {item['case_id']}")
        with lock:
          state["spent"] += cost
      if _out_of_credits(result.get("error")):
        state["status"] = "stopped_out_of_credits"
        print("STOP: OpenRouter is out of credits; top up and re-run the same command.", flush=True)
        return
      (out_root / f"{_slug(item['case_id'])}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
      print(f"  {item['case_id']} {item['sc']}: state={result['state']} flagged={result['flagged']} "
            f"${cost or 0:.4f} {result['wall_seconds']}s", flush=True)

    try:
      for app in sorted({i["app"] for i in todo}):
        servers[app] = serve(app)
      from concurrent.futures import ThreadPoolExecutor
      with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for future in [pool.submit(one, item) for item in todo]:
          future.result()
    except Exception as exc:
      state["status"] = "failed"
      print(f"STOP (failed): {type(exc).__name__}: {exc}")
    finally:
      for server, _ in servers.values():
        server.shutdown()
      log.finish(row, status=state["status"], cost_usd=state["spent"])
    status = state["status"]
    if status != "done":
      return 2
  # score on the shared-type gold rows
  gold = [g for g in read_gold(DEV / "gold.csv") if g.case_id in {i["case_id"] for i in items}]
  results = {}
  for item in items:
    path = out_root / f"{_slug(item['case_id'])}.json"
    results[item["case_id"]] = json.loads(path.read_text()) if path.exists() else None
  rows = [PredictionRow(run_id="intera11y-dev", system="InterA11y", config="full-effort-high-static-page", model=args.model,
                        run_idx=0, regime="R2", dataset="dev", case_id=cid, prediction=prediction(r),
                        cost_usd=float((r or {}).get("cost_usd") or 0.0)) for cid, r in results.items()]
  write_rows(DEV / "predictions" / f"intera11y__{_slug(args.model)}.csv", rows)
  joined = join(gold, {r.case_id: r.prediction for r in rows})
  summary = {"system": "InterA11y", "model": args.model, "cases": len(gold),
             "views": {v: score_cases(joined, v).as_dict() for v in ("strict", "selective", "triage")},
             "by_type": {k: m.as_dict() for k, m in breakdown(joined, "type").items()},
             "cost_usd": round(sum(r.cost_usd for r in rows), 4),
             "missing": sum(r is None for r in results.values())}
  (DEV / "scores").mkdir(parents=True, exist_ok=True)
  (DEV / "scores" / f"intera11y__{_slug(args.model)}.json").write_text(json.dumps(summary, indent=2) + "\n")
  s = summary["views"]["strict"]
  print(f"InterA11y {args.model}: P={s['precision']} R={s['recall']} F1={s['f1']} cost=${summary['cost_usd']}"
        f" missing={summary['missing']}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
