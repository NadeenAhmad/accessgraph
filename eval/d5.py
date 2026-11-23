"""D5: real open-source SPAs (evaluation protocol: docs/evaluation.md). Explore, build candidates, sample 600, judge, export.

  python -m eval.d5 serve APP                  # start the app locally and wait (manual check)
  python -m eval.d5 explore APP [APP ...]      # main explorer (frozen config), stage `d5`
  python -m eval.d5 build                      # candidates for every explored app (free)
  python -m eval.d5 sample                     # stratified random sample of 600 candidates (seeded)
  python -m eval.d5 judge                      # AG-main on the sample, stage `d5`
  python -m eval.d5 export                     # ~300 items for the experts, with review packages

Apps are cloned under the D5 apps folder (eval/paths.py) at the commits in eval/d5_apps.yaml (pinned at setup, 2026-11-16) and
run locally only. Exploration uses the frozen main explorer (eval/freeze_params.json): LLM policy, n_max 100,
d_max 5, k_max 5, same origin, forms and destructive actions only on 127.0.0.1/localhost, network guard on (an app
that reads an external API can read it; every write to another host is blocked).

Sample: strata = type x depth (0 vs >= 1) x direction (backward = incoming change record; forward-link and
forward-button/widget = outgoing outcome; state-local). Allocation proportional to the square root of the stratum
size, at least one per non-empty stratum; sampling weight = stratum size / sampled. Seed 20261116.
Export: every `violation` in the sample (up to 150) plus a random sample of the rest, about 300 in total, with
inclusion weights; each item gets a review package (screenshots, evidence, change record, outcome, replay path).
AccessGraph's verdicts are kept out of the annotators' sheet.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import random
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.cost import CostLedger  # noqa: E402
from eval.freeze import verify_freeze  # noqa: E402
from eval.runlog import RunLog, new_run_id  # noqa: E402

APPS_FILE = ROOT / "eval" / "d5_apps.yaml"
from eval.paths import D5_APPS as APPS_DIR  # noqa: E402
RUNS = ROOT / "runs" / "w4a-d5"
OUT = ROOT / "results" / "d5"
STAGE = "d5"
SEED = 20261116
SAMPLE_SIZE = 600
EXPORT_SIZE = 300
EXPORT_VIOLATIONS_MAX = 150
CONFIRMATION_RUN_ID = "d5-ag-main"


def apps() -> dict[str, dict]:
  return yaml.safe_load(APPS_FILE.read_text(encoding="utf-8"))["apps"]


def _ready(url: str) -> bool:
  try:
    with urllib.request.urlopen(url, timeout=5) as response:
      return response.status < 500
  except Exception:
    return False


@contextmanager
def serve(name: str, timeout: float = 600):
  """Start the app's processes (each in its own process group), wait for its start URL, stop them afterwards."""
  spec = apps()[name]
  procs, logs = [], []
  log_dir = RUNS / name / "server-logs"
  log_dir.mkdir(parents=True, exist_ok=True)
  try:
    for i, step in enumerate(spec["serve"]):
      log = open(log_dir / f"serve-{i}.log", "w")
      logs.append(log)
      env = dict(os.environ, **{k: str(v) for k, v in (step.get("env") or {}).items()})
      procs.append(subprocess.Popen(step["cmd"], cwd=APPS_DIR / spec["dir"] / step.get("cwd", "."), env=env,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                    shell=isinstance(step["cmd"], str)))
      if step.get("ready"):
        _wait(step["ready"], timeout, procs[-1])
    start = f"http://127.0.0.1:{spec['port']}{spec['start']}"
    _wait(start, timeout, procs[-1])
    yield start
  finally:
    for proc in procs:
      try:
        os.killpg(proc.pid, signal.SIGTERM)
      except ProcessLookupError:
        pass
    for proc in procs:
      try:
        proc.wait(timeout=20)
      except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
    for log in logs:
      log.close()


def _wait(url: str, timeout: float, proc) -> None:
  deadline = time.time() + timeout
  while time.time() < deadline:
    if _ready(url):
      return
    if proc.poll() is not None:
      raise RuntimeError(f"server exited with {proc.returncode} before {url} answered")
    time.sleep(2)
  raise TimeoutError(f"{url} did not answer within {timeout:.0f} s")


def explore(names: list[str]) -> None:
  from playwright.async_api import async_playwright
  from src.crawler.crawl.crawl_config import CrawlConfig
  from src.crawler.crawl.entrypoint import run_crawl
  from src.crawler.crawl.priority.llm_policy import LLMPolicyConfig, _build_client
  from eval.dev_explore import BudgetedJsonClient

  verify_freeze(root=ROOT)
  frozen = json.loads((ROOT / "eval" / "freeze_params.json").read_text())["explorer"]
  ledger = CostLedger(ROOT / "results" / "cost_ledger.json")
  log = RunLog(ROOT / "results")
  for name in names:
    run_dir = RUNS / name / "explore"
    if (run_dir / "graph.json").exists():
      print(f"{name}: explored before, skipped")
      continue
    llm_cfg = LLMPolicyConfig(provider=frozen["llm_provider"], model=frozen["llm_model"])
    cfg = CrawlConfig(max_states=frozen["max_states"], max_depth=frozen["max_depth"],
                      max_actions_per_state=frozen["max_actions_per_state"], traversal_strategy=frozen["traversal_strategy"],
                      scope_policy=frozen["scope_policy"], action_policy=frozen["policy"], llm_policy=llm_cfg,
                      submission_allow_hosts=tuple(frozen["submission_allow_hosts"]), network_guard=frozen["network_guard"],
                      outcome_completion_per_state=frozen["outcome_completion_per_state"],
                      outcome_completion_max_actions=frozen["outcome_completion_max_actions"],
                      outcome_completion_max_new_states=frozen["outcome_completion_max_new_states"],
                      enable_tile_screenshots=False)
    run_id = new_run_id("explore-llm", f"D5-{name}")
    client = BudgetedJsonClient(_build_client(llm_cfg), ledger, run_id, stage=STAGE)
    ledger.check(STAGE, 0.05)
    row = log.start(run_id=run_id, stage=STAGE, system="explorer-llm", dataset=f"D5-{name}", split="test",
                    command=f"python -m eval.d5 explore {name}")
    if run_dir.exists():
      shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    started = time.perf_counter()

    async def crawl(start: str):
      async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
          context = await browser.new_context(viewport={"width": 1280, "height": 800})
          storage = apps()[name].get("init_storage") or {}
          if storage:
            await context.add_init_script("".join(
              f"if (localStorage.getItem({json.dumps(k)}) === null) localStorage.setItem({json.dumps(k)}, {json.dumps(v)});"
              for k, v in storage.items()))
          page = await context.new_page()
          await page.goto(start, wait_until="networkidle", timeout=120_000)
          graph = await run_crawl(page, start, run_dir, cfg, llm_client=client)
          graph.save_json(run_dir / "graph.json")
          return graph
        finally:
          await browser.close()

    try:
      with serve(name) as start:
        graph = asyncio.run(crawl(start))
    except Exception as exc:
      log.finish(row, status="failed", cost_usd=client.spent, notes=f"{type(exc).__name__}: {str(exc)[:200]}")
      print(f"{name}: FAILED {type(exc).__name__}: {str(exc)[:300]}", flush=True)
      continue
    log.finish(row, status="done", cost_usd=client.spent,
               notes=f"states {len(graph.nodes)}, {time.perf_counter() - started:.0f}s, cache hits {client.hits}")
    print(f"{name}: {len(graph.nodes)} states, {len(graph.edges)} edges, ${client.spent:.4f}, "
          f"{time.perf_counter() - started:.0f}s", flush=True)


def _candidates(run_dir: Path) -> list[dict]:
  path = run_dir / "candidates" / "candidates.jsonl"
  return [json.loads(l) for l in path.read_text(encoding="utf-8").split("\n") if l.strip()]


def build() -> None:
  from src.analysis.candidates import build_semantic_candidates
  for name in apps():
    run_dir = RUNS / name / "explore"
    if not (run_dir / "graph.json").exists():
      continue
    summary = build_semantic_candidates(run_dir)
    print(name, len(_candidates(run_dir)), "candidates", summary.output_dir.relative_to(ROOT), flush=True)


def direction(candidate: dict) -> str:
  scope = candidate.get("evidence_scope")
  if scope == "incoming":
    return "backward"
  if scope == "outgoing":
    return "forward-link" if candidate["candidate_type"] == "link-text-mismatch" else "forward-button/widget"
  return "state-local"


def sample() -> None:
  pool = []
  for name in apps():
    run_dir = RUNS / name / "explore"
    if not (run_dir / "candidates" / "candidates.jsonl").exists():
      continue
    depth = {n["state_id"]: n.get("depth", 0) for n in json.loads((run_dir / "graph.json").read_text())["nodes"]}
    for c in _candidates(run_dir):
      d = depth.get(c["state_id"], 0)
      pool.append({"candidate_id": c["candidate_id"], "app": name, "type": c["candidate_type"], "state_id": c["state_id"],
                   "depth": d, "direction": direction(c),
                   "stratum": f"{c['candidate_type']}|{'0' if d == 0 else '1+'}|{direction(c)}"})
  strata = defaultdict(list)
  for item in pool:
    strata[item["stratum"]].append(item)
  size = min(SAMPLE_SIZE, len(pool))
  root = {s: math.sqrt(len(v)) for s, v in strata.items()}
  alloc = {s: min(len(strata[s]), max(1, round(size * r / sum(root.values())))) for s, r in root.items()}
  while sum(alloc.values()) > size:  # trim the largest allocations
    s = max(alloc, key=lambda k: (alloc[k], k))
    alloc[s] -= 1
  while sum(alloc.values()) < size:  # fill strata that still have candidates, largest first
    s = max((k for k in alloc if alloc[k] < len(strata[k])), key=lambda k: (len(strata[k]) - alloc[k], k))
    alloc[s] += 1
  rng = random.Random(SEED)
  chosen = []
  for s in sorted(strata):
    for item in rng.sample(sorted(strata[s], key=lambda x: (x["app"], x["candidate_id"])), alloc[s]):
      chosen.append({**item, "stratum_size": len(strata[s]), "stratum_sampled": alloc[s],
                     "weight": len(strata[s]) / alloc[s]})
  OUT.mkdir(parents=True, exist_ok=True)
  with (OUT / "sample.csv").open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(chosen[0]))
    writer.writeheader()
    writer.writerows(chosen)
  (OUT / "population.json").write_text(json.dumps({
    "candidates": len(pool), "by_app": Counter(p["app"] for p in pool), "strata": {s: len(v) for s, v in strata.items()},
    "sampled": len(chosen), "seed": SEED, "allocation": "sqrt(stratum size), min 1"}, indent=2) + "\n")
  print(f"{len(pool)} candidates in {len(strata)} strata; sampled {len(chosen)}", flush=True)


def _sample_rows() -> list[dict]:
  with (OUT / "sample.csv").open(encoding="utf-8") as stream:
    return list(csv.DictReader(stream))


def judge() -> None:
  from src.analysis.confirmation.providers.caching import CachingConfirmationClient
  from src.analysis.confirmation.providers.registry import build_confirmation_client
  from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation
  from eval.cost import BudgetedClient
  from eval.dev_judge import _config

  verify_freeze(root=ROOT)
  frozen = json.loads((ROOT / "eval" / "freeze_params.json").read_text())["ag_main"]
  config = _config("AG-main", frozen["provider"], frozen["model"], frozen["effort"])
  ledger = CostLedger(ROOT / "results" / "cost_ledger.json")
  log = RunLog(ROOT / "results")
  run_id = new_run_id("AG-main", "D5")
  rows = _sample_rows()
  ledger.check(STAGE, 0.0015 * len(rows))
  budgeted = BudgetedClient(build_confirmation_client(config), ledger, STAGE, run_id=run_id)
  client = CachingConfirmationClient(budgeted, ROOT / "results" / "cache", parameters={"effort": config.effort})
  row = log.start(run_id=run_id, stage=STAGE, system="AG-main", dataset="D5", split="test",
                  command="python -m eval.d5 judge")
  by_app = defaultdict(list)
  for r in rows:
    by_app[r["app"]].append(r["candidate_id"])
  try:
    for name, ids in sorted(by_app.items()):
      run_dir = RUNS / name / "explore"
      run_confirmation(config=config, client=client, options=ConfirmationRunOptions(
        run_dir=run_dir, confirmation_run_id=CONFIRMATION_RUN_ID, candidate_ids=tuple(sorted(ids)),
        overwrite=True, save_prompts=True, save_raw_responses=True, fail_fast=False))
      _follow_up(run_dir, config, budgeted)
      print(f"{name}: {len(ids)} judged (paid {client.misses}, ${budgeted.spent:.4f} so far)", flush=True)
  except Exception as exc:
    log.finish(row, status="failed", cost_usd=budgeted.spent, notes=str(exc)[:200])
    raise
  log.finish(row, status="done", cost_usd=budgeted.spent, notes=f"{len(rows)} candidates")


def _follow_up(run_dir: Path, config, budgeted) -> None:
  """W4A phase 2: uncertain verdicts get follow-up evidence and a majority of three re-judgements (same as
  single-page mode). Pressing happens on a fresh load of the state's URL, on the local app only."""
  from src.analysis.confirmation.providers.caching import CachingConfirmationClient
  from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation
  from src.analysis.confirmation.uncertain_followup import follow_up, read_decisions
  if not any(r.get("decision") == "uncertain" for r in read_decisions(run_dir, CONFIRMATION_RUN_ID).values()):
    return
  urls = {n["state_id"]: n.get("url") for n in json.loads((run_dir / "graph.json").read_text())["nodes"]}

  def rejudge(run_id: str, ids: tuple[str, ...], sample: int) -> None:
    client = CachingConfirmationClient(budgeted, ROOT / "results" / "cache",
                                       parameters={"effort": config.effort, "followup_sample": sample})
    run_confirmation(config=config, client=client, options=ConfirmationRunOptions(
      run_dir=run_dir, confirmation_run_id=run_id, candidate_ids=ids, overwrite=True, save_prompts=True,
      save_raw_responses=True, fail_fast=False))

  # the follow-up loads each state's page (destination, pressed element, image), so the local app must be running
  with serve(run_dir.parent.name):
    follow_up(run_dir, first_run_id=CONFIRMATION_RUN_ID, judge=rejudge, state_url=urls.get,
              allow_hosts=("127.0.0.1", "localhost"))


def _verdicts() -> dict[tuple[str, str], dict]:
  """First-run verdicts with the follow-up majority applied to the uncertain ones, keyed by (app, candidate_id):
  candidate ids are hashes of state, type and element, so the same id can occur in two apps."""
  from src.analysis.confirmation.uncertain_followup import final_decisions
  out = {}
  for name in apps():
    run_dir = RUNS / name / "explore"
    final = final_decisions(run_dir, CONFIRMATION_RUN_ID) if (run_dir / "confirmations").exists() else {}
    path = run_dir / "confirmations" / CONFIRMATION_RUN_ID / "confirmations.jsonl"
    if path.exists():
      for line in path.read_text(encoding="utf-8").split("\n"):  # not splitlines: U+2028 may occur in text
        if line.strip():
          r = json.loads(line)
          if r["candidate_id"] in final and final[r["candidate_id"]] != r.get("decision"):
            r = {**r, "first_decision": r.get("decision"), "decision": final[r["candidate_id"]], "followed_up": True}
          out[(name, r["candidate_id"])] = r
  return out


def _replay_path(graph: dict, state_id: str) -> list[dict]:
  nodes = {n["state_id"]: n for n in graph["nodes"]}
  path, current = [], nodes.get(state_id)
  while current and current.get("parent_state_id"):
    path.append({"from": current["parent_state_id"], "to": current["state_id"], "action": current.get("incoming_action")})
    current = nodes.get(current["parent_state_id"])
  return list(reversed(path))


def export() -> None:
  rows, verdicts = _sample_rows(), _verdicts()
  rng = random.Random(SEED + 1)
  violations = [r for r in rows if (verdicts.get((r["app"], r["candidate_id"])) or {}).get("decision") == "violation"]
  rest = [r for r in rows if r not in violations]
  take_v = rng.sample(violations, min(EXPORT_VIOLATIONS_MAX, len(violations)))
  take_r = rng.sample(rest, min(len(rest), EXPORT_SIZE - len(take_v)))
  export_dir = OUT / "export"
  if export_dir.exists():
    shutil.rmtree(export_dir)
  (export_dir / "items").mkdir(parents=True)
  sheet, key = [], []
  order = take_v + take_r
  rng.shuffle(order)
  graphs, cands = {}, {}
  for i, r in enumerate(order, 1):
    item_id = f"D5-{i:03d}"
    run_dir = RUNS / r["app"] / "explore"
    if r["app"] not in graphs:
      graphs[r["app"]] = json.loads((run_dir / "graph.json").read_text())
      cands[r["app"]] = {c["candidate_id"]: c for c in _candidates(run_dir)}
    c = cands[r["app"]][r["candidate_id"]]
    item = export_dir / "items" / item_id
    item.mkdir()
    states = {c["state_id"]}
    graph_ctx = c.get("graph_context") or {}
    record = graph_ctx.get("incoming_change_record_v1") or {}
    states.update(x for x in (record.get("from_state"), record.get("to_state")) if x)  # backward: before and after
    for step in graph_ctx.get("transition_path") or []:
      if isinstance(step, dict) and step.get("to") == c["state_id"] and step.get("from"):
        states.add(step["from"])
    supporting = (c.get("evidence") or {}).get("supporting") or {}
    destination = supporting.get("destination_state_context_v1") or {}
    for t in destination.get("transitions") or destination.get("destinations") or []:
      if isinstance(t, dict):  # forward: the states the control led to
        states.update(x for x in (t.get("to_state"), t.get("target_state_id"), t.get("state_id")) if x)
    for sid in sorted(states):
      shot = run_dir / "states" / sid / "screenshot.png"
      if shot.exists():
        role = "judged-state" if sid == c["state_id"] else ("before" if sid == record.get("from_state") else "related")
        shutil.copy(shot, item / f"{sid}-{role}.png")
    (item / "evidence.json").write_text(json.dumps({k: c.get(k) for k in (
      "candidate_type", "state_id", "element_refs", "evidence", "state_context", "graph_context", "evidence_scope")},
      indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    start = graphs[r["app"]]["nodes"][0].get("url")
    (item / "replay.json").write_text(json.dumps({"start_url": start, "app": r["app"],
                                                  "steps": _replay_path(graphs[r["app"]], c["state_id"])},
                                                 indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    weight_export = (len(violations) / len(take_v)) if r in take_v else (len(rest) / len(take_r))
    sheet.append({"item_id": item_id, "app": r["app"], "type": r["type"], "direction": r["direction"],
                  "question": f"Is this a {r['type']} violation (WCAG)? See evidence.json and the screenshots.",
                  "label": "", "annotator": "", "notes": ""})
    key.append({"item_id": item_id, "candidate_id": r["candidate_id"], "app": r["app"], "type": r["type"],
                "depth": r["depth"], "direction": r["direction"], "stratum": r["stratum"],
                "sample_weight": r["weight"], "export_weight": weight_export,
                "ag_decision": (verdicts.get((r["app"], r["candidate_id"])) or {}).get("decision", "not_judged")})
  for name, data in (("labelling_sheet.csv", sheet), ("key_do_not_share.csv", key)):
    with (export_dir / name).open("w", newline="", encoding="utf-8") as stream:
      writer = csv.DictWriter(stream, fieldnames=list(data[0]))
      writer.writeheader()
      writer.writerows(data)
  print(f"exported {len(order)} items ({len(take_v)} of {len(violations)} violations, {len(take_r)} others)")


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("step", choices=("serve", "explore", "build", "sample", "judge", "export"))
  parser.add_argument("apps", nargs="*")
  parser.add_argument("--stage", default="d5", help="budget line in results/cost_ledger.json (re-runs: phase3_final)")
  args = parser.parse_args(argv)
  global STAGE
  STAGE = args.stage
  if args.step == "serve":
    with serve(args.apps[0]) as start:
      print("ready:", start, flush=True)
      input("press Enter to stop ")
  elif args.step == "explore":
    explore(args.apps or list(apps()))
  else:
    {"build": build, "sample": sample, "judge": judge, "export": export}[args.step]()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
