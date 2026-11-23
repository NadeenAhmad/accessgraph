"""C5 explorer choice on dev: `llm` vs `discovery`, one crawl each on the two dev apps, then expected-state reach.

  python -m eval.dev_explore --policy discovery
  python -m eval.dev_explore --policy llm --model anthropic/claude-haiku-5.5 [--dry-run]
  python -m eval.dev_explore --reach-only

Both crawls use the paper's bounds (n_max 100, d_max 5, k_max 5), breadth-first order, the clean profile, local
hosts allowed for form submission and remove/delete/checkout, and the network guard. The LLM explorer uses the
text provider (no screenshot), so its answers are cacheable: every plan is stored under results/cache/explorer and
a re-run repeats no paid call. Spend is charged to stage `dev` (the C5 check is part of the dev budget).

Reach (offline, free): a dev case's expected state counts as reached when an explored state has the same route,
contains every key selector the student's focused capture validated for that state, and contains the case's
target element (its data-testid or HTML id). Written to results/dev/explore/reach.json.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.cost import BudgetExceeded, CostLedger, TopUpNeeded, preflight  # noqa: E402
from eval.runlog import RunLog, new_run_id  # noqa: E402

RESULTS = ROOT / "results"
DEV = RESULTS / "dev"
RUNS = ROOT / "runs" / "w4a-dev" / "explore"
CACHE = RESULTS / "cache" / "explorer"
STAGE = "dev"
BOUNDS = dict(max_states=100, max_depth=5, max_actions_per_state=5)
APPS = {
  "checkout-flow": {"start": "/products", "global": "__ACCESSGRAPH_CHECKOUT_PROFILE__", "profile": "checkout-clean-v1"},
  "booking-scheduler": {"start": "/services", "global": "__ACCESSGRAPH_BOOKING_PROFILE__", "profile": "booking-clean"},
}
EST_CALL_USD = 0.0012  # ~6k input tokens + 600 output tokens at $0.10 / $0.50 per million


class BudgetedJsonClient:
  """complete_json with a disk cache (key: model, prompts, schema, images) and the budget guard."""

  def __init__(self, inner, ledger: CostLedger, run_id: str, max_call_usd: float = 0.02, stage: str = STAGE):
    self.inner, self.ledger, self.run_id, self.max_call_usd = inner, ledger, run_id, max_call_usd
    self.stage = stage
    self.provider, self.model = inner.provider, inner.model
    self.hits = self.misses = 0
    self.spent = 0.0

  def complete_json(self, *, system, user, schema, schema_name, image_data_urls):
    key = hashlib.sha256(json.dumps([self.provider, self.model, system, user, schema_name, schema,
                                     [hashlib.sha256(u.encode()).hexdigest() for u in image_data_urls or []]],
                                    sort_keys=True).encode()).hexdigest()
    path = CACHE / key[:2] / f"{key}.json"
    if path.exists():
      self.hits += 1
      saved = json.loads(path.read_text(encoding="utf-8"))
      return SimpleNamespace(raw_content=saved["raw_content"], estimated_cost_usd=0.0)
    self.ledger.check(self.stage, planned_usd=self.max_call_usd)
    response = self.inner.complete_json(system=system, user=user, schema=schema, schema_name=schema_name,
                                        image_data_urls=image_data_urls)
    cost = getattr(response, "estimated_cost_usd", None)
    if cost is None:
      raise BudgetExceeded(f"{self.provider}/{self.model} returned no cost")
    self.misses += 1
    self.spent += cost
    self.ledger.charge(self.stage, cost, run_id=self.run_id, note=f"explorer {self.model}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": self.model, "raw_content": response.raw_content, "cost_usd": cost}) + "\n",
                    encoding="utf-8")
    return response


# Fixed ports: the explorer prompt lists the URLs it has seen, so a fixed origin keeps prompts (and cache keys)
# identical across runs.
PORTS = {"checkout-flow": 4311, "booking-scheduler": 4312}
# Settings compared on dev in phase 1 (2026-11-17); each gets its own ports so they can run in parallel.
SETTINGS = {
  "base": dict(max_states=100, max_depth=5, max_actions_per_state=5, outcome_completion_per_state=0, port_offset=10),
  "complete3": dict(max_states=100, max_depth=5, max_actions_per_state=5, outcome_completion_per_state=3, port_offset=20),
  "wide": dict(max_states=200, max_depth=6, max_actions_per_state=8, outcome_completion_per_state=3, port_offset=30),
}
_PORT_OFFSET = 0


@contextmanager
def app_server(app: str):
  if app == "checkout-flow":
    from scripts.benchmarks.checkout import spa_process
    port = PORTS[app] + _PORT_OFFSET
    spa_process.assert_port_available(host="127.0.0.1", port=port)
    preview = spa_process.start_vite_preview(port=port)
    base = f"http://127.0.0.1:{port}"
    try:
      spa_process.wait_for_url(f"{base}/products", timeout_seconds=20)
      yield base
    finally:
      spa_process.stop_process(preview)
  else:
    from scripts.benchmarks.booking.spa_process import open_booking_spa
    with open_booking_spa(port=PORTS[app] + _PORT_OFFSET, build=False) as server:
      yield server.base_url


async def _crawl(app: str, base: str, run_dir: Path, cfg, llm_client):
  from playwright.async_api import async_playwright
  from src.crawler.crawl.entrypoint import run_crawl
  spec = APPS[app]
  async with async_playwright() as playwright:
    browser = await playwright.chromium.launch(headless=True)
    try:
      context = await browser.new_context(viewport={"width": 1280, "height": 800})
      await context.add_init_script(f"window[{json.dumps(spec['global'])}] = {json.dumps(spec['profile'])};")
      page = await context.new_page()
      start = base + spec["start"]
      await page.goto(start, wait_until="networkidle")
      graph = await run_crawl(page, start, run_dir, cfg, llm_client=llm_client)
      graph.save_json(run_dir / "graph.json")
      return graph
    finally:
      await browser.close()


def explore(policy: str, model: str | None, apps: list[str], setting: str | None = None, stage: str = STAGE) -> None:
  from src.crawler.crawl.crawl_config import CrawlConfig
  from src.crawler.crawl.priority.llm_policy import LLMPolicyConfig, _build_client

  ledger = CostLedger(RESULTS / "cost_ledger.json")
  log = RunLog(RESULTS)
  for app in apps:
    run_dir = RUNS / f"{app}__{policy}{'__' + model.replace('/', '-') if model else ''}{'__' + setting if setting else ''}"
    if (run_dir / "graph.json").exists():
      print(f"{run_dir.name}: done before, skipped")
      continue
    llm_cfg = LLMPolicyConfig(provider="openrouter", model=model) if policy == "llm" else None
    bounds = {k: v for k, v in SETTINGS[setting].items() if k != "port_offset"} if setting else BOUNDS
    cfg = CrawlConfig(**bounds, traversal_strategy="bfs", scope_policy="same_origin", action_policy=policy,
                      llm_policy=llm_cfg, submission_allow_hosts=("127.0.0.1", "localhost"), network_guard=True,
                      enable_tile_screenshots=False)
    run_id = new_run_id(f"explore-{policy}", "dev")
    client = BudgetedJsonClient(_build_client(llm_cfg), ledger, run_id, stage=stage) if llm_cfg else None
    row = log.start(run_id=run_id, stage=stage, system=f"explorer-{policy}", dataset="dev", split="dev",
                    command=f"python -m eval.dev_explore --policy {policy} --model {model} ({app})")
    started = time.perf_counter()
    if run_dir.exists():
      import shutil
      shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    try:
      with app_server(app) as base:
        graph = asyncio.run(_crawl(app, base, run_dir, cfg, client))
    except Exception as exc:
      from src.analysis.confirmation.providers.base import ProviderOutOfCredits
      status = "stopped_out_of_credits" if isinstance(exc, ProviderOutOfCredits) else "failed"
      log.finish(row, status=status, cost_usd=client.spent if client else 0.0, notes=str(exc)[:200])
      raise
    spent = client.spent if client else 0.0
    log.finish(row, status="done", cost_usd=spent, notes=f"states {len(graph.nodes)}, "
               f"{time.perf_counter() - started:.0f}s, cache hits {client.hits if client else 0}")
    print(f"{run_dir.name}: {len(graph.nodes)} states, {len(graph.edges)} edges, ${spent:.4f}, "
          f"{time.perf_counter() - started:.0f}s")


def _identity(raw_html: str) -> list[str]:
  out = []
  for attr in ("data-testid", "id"):
    match = re.search(rf'\b{attr}="([^"]+)"', raw_html or "")
    if match:
      out.append(f'{attr}="{match.group(1)}"')
  return out[:1]


def _selector_markers(selector: str) -> list[str]:
  markers = re.findall(r'\[data-testid="([^"]+)"\]', selector)
  if markers:
    return [f'data-testid="{m}"' for m in markers]
  ids = re.findall(r"#([A-Za-z][\w-]*)", selector)
  return [f'id="{i}"' for i in ids]


def reach() -> dict:
  """Which dev cases' expected states each explored graph reached (see module docstring)."""
  links = [json.loads(l) for l in (DEV / "links.jsonl").read_text().splitlines() if l]
  seeded = [l for l in links if l["kind"] == "seeded"]
  explored = {}
  for run_dir in sorted(RUNS.glob("*__*")):
    if not (run_dir / "graph.json").exists():
      continue
    app, policy = run_dir.name.split("__")[0], run_dir.name.split("__", 1)[1]
    states = []
    for state in (run_dir / "states").iterdir():
      meta_path, dom_path = state / "metadata.json", state / "dom.html"
      if meta_path.exists() and dom_path.exists():
        meta = json.loads(meta_path.read_text())
        route = re.sub(r"^https?://[^/]+", "", meta.get("url") or "").split("?")[0].split("#")[0]
        states.append((route, dom_path.read_text(encoding="utf-8")))
    explored.setdefault(policy, {})[app] = states
  result = {"cases": len(seeded), "by_policy": {}}
  for policy, by_app in explored.items():
    reached, detail = 0, {}
    for link in seeded:
      run_dir = ROOT / link["run_dir"]
      app = "checkout-flow" if "/checkout/" in link["run_dir"] else "booking-scheduler"
      if app not in by_app or not link["candidate_ids"]:
        detail[link["case_id"]] = None if app not in by_app else False
        continue
      cands = {c["candidate_id"]: c for c in (json.loads(x) for x in
                                              (run_dir / "candidates/candidates.jsonl").read_text().splitlines() if x)}
      cand = cands[link["candidate_ids"][0]]
      meta = json.loads((run_dir / "states" / cand["state_id"] / "metadata.json").read_text())
      route = meta.get("route") or ""
      markers = [m for s in (meta.get("focused_acquisition") or {}).get("key_validated_selectors") or []
                 for m in _selector_markers(s)]
      ctx = json.loads((run_dir / "states" / cand["state_id"] / "accessibility_context.json").read_text())
      ref = (cand.get("element_refs") or [{}])[0]
      element = next((e for e in ctx.get(ref.get("bucket"), []) if e.get("element_id") == ref.get("element_id")), {})
      markers += _identity(element.get("raw_html") or "")
      hit = any(r == route and all(m in dom for m in markers) for r, dom in by_app[app])
      detail[link["case_id"]] = hit
      reached += hit
    apps_covered = sorted(by_app)
    considered = [k for k, v in detail.items() if v is not None]
    result["by_policy"][policy] = {"apps": apps_covered, "cases_considered": len(considered), "reached": reached,
                                   "reach_rate": round(reached / len(considered), 3) if considered else None,
                                   "states": {a: len(s) for a, s in by_app.items()}, "per_case": detail}
  (DEV / "explore").mkdir(parents=True, exist_ok=True)
  (DEV / "explore" / "reach.json").write_text(json.dumps(result, indent=2) + "\n")
  return result


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--policy", choices=("discovery", "llm"))
  parser.add_argument("--model", default=None)
  parser.add_argument("--apps", nargs="*", default=list(APPS))
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--reach-only", action="store_true")
  parser.add_argument("--setting", choices=sorted(SETTINGS), default=None)
  parser.add_argument("--stage", default=STAGE)
  args = parser.parse_args(argv)
  global _PORT_OFFSET
  if args.setting:
    _PORT_OFFSET = SETTINGS[args.setting]["port_offset"]
  if not args.reach_only:
    if args.policy == "llm":
      if not args.model:
        parser.error("--model is required for --policy llm")
      est = BOUNDS["max_states"] * len(args.apps) * EST_CALL_USD
      ledger = CostLedger(RESULTS / "cost_ledger.json")
      print(f"[dry-run] stage={STAGE} explorer calls<= {BOUNDS['max_states'] * len(args.apps)} est<=${est:.3f} "
            f"left=${ledger.remaining(STAGE):.3f}")
      if args.dry_run:
        return 0
      try:
        print(preflight(ledger, STAGE, est))
      except TopUpNeeded as exc:
        print(f"STOP: {exc}")
        return 3
    explore(args.policy, args.model if args.policy == "llm" else None, args.apps, args.setting, args.stage)
  summary = reach()
  for policy, data in summary["by_policy"].items():
    print(f"{policy}: reached {data['reached']}/{data['cases_considered']} ({data['reach_rate']}), states {data['states']}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
