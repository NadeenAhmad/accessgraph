"""Run AccessGraph on your own single-page application with the configuration used in the paper: explore, propose
candidates, judge them, and write a report.

  export OPENROUTER_API_KEY=...            # judge and explorer: openai/gpt-6-luna via OpenRouter
  python scripts/run_accessgraph.py --url http://127.0.0.1:5173/ --out runs/my-app
  python scripts/run_accessgraph.py --url http://127.0.0.1:5173/ --out runs/my-app-smoke --fake   # free check

The explorer and the judge are configured exactly as frozen for the paper (eval/freeze_params.json): breadth-first,
at most 100 states, depth 5, 5 actions per state, LLM action policy, outcome completion (3 more controls per state,
at most 150 actions and 50 extra states), and the judge with history-aware context, uncertain verdicts re-judged with
follow-up evidence. Forms are filled and destructive actions are tried only on the hosts in --allow-hosts (default:
127.0.0.1 and localhost, i.e. a local copy of your app); every write to another host is blocked.

--fake runs the whole pipeline for free: discovery-order exploration (no LLM) and the fake judge (placeholder
verdicts), to check the setup. The report is written to <out>/reports/.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))
RUN_ID = "accessgraph"


def explore(url: str, out: Path, allow_hosts: tuple[str, ...], fake: bool) -> None:
  from playwright.async_api import async_playwright
  from src.crawler.crawl.crawl_config import CrawlConfig
  from src.crawler.crawl.entrypoint import run_crawl
  from src.crawler.crawl.priority.llm_policy import LLMPolicyConfig, _build_client
  frozen = json.loads((ROOT / "eval" / "freeze_params.json").read_text(encoding="utf-8"))["explorer"]
  llm_cfg = None if fake else LLMPolicyConfig(provider=frozen["llm_provider"], model=frozen["llm_model"])
  cfg = CrawlConfig(max_states=frozen["max_states"], max_depth=frozen["max_depth"],
                    max_actions_per_state=frozen["max_actions_per_state"], traversal_strategy=frozen["traversal_strategy"],
                    scope_policy=frozen["scope_policy"], action_policy="discovery" if fake else frozen["policy"],
                    llm_policy=llm_cfg, submission_allow_hosts=allow_hosts, network_guard=frozen["network_guard"],
                    outcome_completion_per_state=frozen["outcome_completion_per_state"],
                    outcome_completion_max_actions=frozen["outcome_completion_max_actions"],
                    outcome_completion_max_new_states=frozen["outcome_completion_max_new_states"],
                    enable_tile_screenshots=False)
  client = None if fake else _build_client(llm_cfg)

  async def crawl():
    async with async_playwright() as playwright:
      browser = await playwright.chromium.launch(headless=True)
      try:
        page = await (await browser.new_context(viewport={"width": 1280, "height": 800})).new_page()
        await page.goto(url, wait_until="networkidle", timeout=120_000)
        graph = await run_crawl(page, url, out, cfg, llm_client=client)
        graph.save_json(out / "graph.json")
        print(f"explored: {len(graph.nodes)} states, {len(graph.edges)} transitions", flush=True)
      finally:
        await browser.close()

  out.mkdir(parents=True, exist_ok=True)
  asyncio.run(crawl())


def judge(out: Path, allow_hosts: tuple[str, ...], fake: bool, limit: int | None) -> None:
  from src.analysis.confirmation.providers.registry import build_confirmation_client
  from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation
  from eval.dev_judge import _config
  frozen = json.loads((ROOT / "eval" / "freeze_params.json").read_text(encoding="utf-8"))["ag_main"]
  config = _config("AG-main", "fake" if fake else frozen["provider"], "fake" if fake else frozen["model"], frozen["effort"])
  ids = [json.loads(line)["candidate_id"] for line in (out / "candidates" / "candidates.jsonl").read_text(encoding="utf-8").split("\n") if line.strip()]
  ids = ids[:limit] if limit else ids
  client = build_confirmation_client(config)
  run_confirmation(config=config, client=client, options=ConfirmationRunOptions(
    run_dir=out, confirmation_run_id=RUN_ID, candidate_ids=tuple(ids), overwrite=True,
    save_prompts=True, save_raw_responses=True, fail_fast=False))
  if not fake:  # uncertain verdicts: follow-up evidence from the running app, then the majority of three re-judgements
    from src.analysis.confirmation.uncertain_followup import follow_up

    def rejudge(run_id: str, candidate_ids: tuple[str, ...], sample: int) -> None:
      run_confirmation(config=config, client=client, options=ConfirmationRunOptions(
        run_dir=out, confirmation_run_id=run_id, candidate_ids=candidate_ids, overwrite=True,
        save_prompts=True, save_raw_responses=True, fail_fast=False))
    urls = {n["state_id"]: n.get("url") for n in json.loads((out / "graph.json").read_text())["nodes"]}
    follow_up(out, first_run_id=RUN_ID, judge=rejudge, state_url=urls.get, allow_hosts=allow_hosts)
  print(f"judged: {len(ids)} candidates", flush=True)


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--url", required=True, help="start URL of the running app")
  parser.add_argument("--out", type=Path, required=True, help="output folder (a new run directory)")
  parser.add_argument("--allow-hosts", default="127.0.0.1,localhost",
                      help="hosts on which forms may be filled and destructive actions tried (comma-separated)")
  parser.add_argument("--limit", type=int, help="judge only the first N candidates (to try it cheaply)")
  parser.add_argument("--fake", action="store_true", help="free check: no LLM, placeholder verdicts")
  args = parser.parse_args(argv)
  allow_hosts = tuple(h.strip() for h in args.allow_hosts.split(",") if h.strip())
  from src.analysis.candidates.builder import build_semantic_candidates
  explore(args.url, args.out, allow_hosts, args.fake)
  build_semantic_candidates(args.out)
  print("candidates:", sum(1 for _ in (args.out / "candidates" / "candidates.jsonl").open(encoding="utf-8")), flush=True)
  judge(args.out, allow_hosts, args.fake, args.limit)
  subprocess.run([sys.executable, str(ROOT / "accessgraph.py"), "report", "--run", str(args.out),
                  "--judgment-run-id", RUN_ID, "--overwrite"], check=True)
  print(f"report: {args.out / 'reports'}", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
