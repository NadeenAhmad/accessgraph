"""C1: LLM-guided exploration, fill-and-submit actions, storage reset and the network guard (fake provider only)."""
from __future__ import annotations

import asyncio
import json
import types
from pathlib import Path

import pytest

from scripts.development.serve_spa_fixtures import serve_fixture_root
from src.crawler.config.app_config import load_app_config
from src.crawler.crawl.entrypoint import CrawlConfig, run_crawl
from src.crawler.crawl.navigation.network_guard import NetworkGuard
from src.crawler.crawl.priority.llm_policy import LLMPolicyConfig

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "w4a_exploration"


def _cfg(**overrides) -> CrawlConfig:
  base = dict(max_states=12, max_depth=2, max_actions_per_state=6, back_timeout_ms=3_000, traversal_strategy="bfs",
              scope_policy="same_origin", enable_tile_screenshots=False, wait_timeout_ms=300)
  base.update(overrides)
  return CrawlConfig(**base)


async def _crawl(start_url: str, run_dir: Path, cfg: CrawlConfig, llm_client=None):
  playwright = pytest.importorskip("playwright.async_api")
  manager = await playwright.async_playwright().start()
  try:
    try:
      browser = await manager.chromium.launch(headless=True)
    except Exception as exc:
      pytest.skip(f"Playwright Chromium is unavailable: {exc}")
    try:
      page = await browser.new_page(viewport={"width": 1280, "height": 720})
      await page.goto(start_url, wait_until="domcontentloaded")
      return await run_crawl(page, start_url, run_dir, cfg, llm_client=llm_client)
    finally:
      await browser.close()
  finally:
    await manager.stop()


def _run(cfg: CrawlConfig, run_dir: Path, llm_client=None):
  with serve_fixture_root(FIXTURES) as server:
    return asyncio.run(_crawl(f"{server.base_url}/shop/", run_dir, cfg, llm_client))


def _edge_actions(graph) -> list[dict]:
  return [edge.get("action", {}) for edge in graph.edges]


def _log(run_dir: Path) -> list[dict]:
  path = run_dir / "exploration_log.jsonl"
  return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_default_crawl_never_fills_forms_or_removes_and_blocks_external_writes(tmp_path):
  graph = _run(_cfg(), tmp_path)
  actions = _edge_actions(graph)
  assert not any(a.get("type") == "fill_submit" for a in actions)
  assert not any("Remove" in str(a.get("text")) for a in actions)
  assert not (tmp_path / "exploration_log.jsonl").exists()
  blocked = [json.loads(l) for l in (tmp_path / "network_guard_blocked.jsonl").read_text().splitlines()]
  assert any("example.invalid" in b["url"] and b["method"] == "POST" for b in blocked)


def test_llm_policy_fake_provider_fills_forms_and_resets_storage_on_allowed_host(tmp_path):
  cfg = _cfg(action_policy="llm", llm_policy=LLMPolicyConfig(provider="fake"), submission_allow_hosts=("127.0.0.1",))
  graph = _run(cfg, tmp_path)
  actions = _edge_actions(graph)
  kinds = {a.get("value_set_kind") for a in actions if a.get("type") == "fill_submit"}
  assert {"valid", "invalid"} <= kinds, actions
  assert any(a.get("text", "").startswith("Remove Storm Shell") for a in actions)
  assert all(a.get("form_values") for a in actions if a.get("type") == "fill_submit")
  log = _log(tmp_path)
  assert any(r["event"] == "form_skipped" and r["reason"] == "password_input" for r in log)
  assert any(r["event"] == "plan" and r["source"] == "fake" for r in log)
  coverage = graph.metrics["coverage"]
  assert coverage["form_actions_attempted"] >= 2 and coverage["actions_changed_app_storage"] >= 1
  assert coverage["state_restore_storage_resets"] >= 1
  # the "thanks" state is only reachable by submitting valid values; it must have been expanded by replay
  thanks = [sid for sid, meta in graph.nodes.items() if "Thanks for subscribing" in json.dumps(meta)]
  thanks_dirs = [d for d in (tmp_path / "states").iterdir() if "Thanks for subscribing" in (d / "dom.html").read_text()]
  assert thanks_dirs, "valid form submission did not reach the confirmation state"


class _ScriptedPlanner:
  provider, model = "scripted", "scripted"

  def __init__(self, first_label: str | None = None, fail: bool = False):
    self.first_label, self.fail, self.calls = first_label, fail, 0
    self.max_actions_seen = 0

  def complete_json(self, *, system, user, schema, schema_name, image_data_urls):
    self.calls += 1
    if self.fail:
      raise RuntimeError("model unavailable")
    actions = json.loads(user.split("\n", 1)[1])["actions"]
    self.max_actions_seen = max(self.max_actions_seen, len(actions))
    first = [a["id"] for a in actions if self.first_label and self.first_label in a["action"]]
    rest = [a["id"] for a in actions if a["id"] not in first]
    return types.SimpleNamespace(raw_content=json.dumps({"rationale": "details first", "ranking": first + rest,
                                                         "forms": []}), estimated_cost_usd=0.0001)


def test_llm_ranking_decides_order_once_per_expansion(tmp_path):
  planner = _ScriptedPlanner(first_label="Show details")
  cfg = _cfg(action_policy="llm", llm_policy=LLMPolicyConfig(provider="openrouter", model="x/y"), max_depth=1)
  graph = _run(cfg, tmp_path, llm_client=planner)
  root_edges = [e for e in graph.edges if e.get("from") == "state_0000" or e.get("source") == "state_0000"] or graph.edges
  assert "Show details" in str(root_edges[0].get("action", {}).get("text"))
  plans = [r for r in _log(tmp_path) if r["event"] == "plan"]
  assert len(plans) == planner.calls == len({r["state_id"] for r in plans})
  assert all(r["rationale"] == "details first" for r in plans)
  assert graph.metrics["exploration_llm_cost_usd"] == pytest.approx(0.0001 * planner.calls)


def test_llm_failure_falls_back_to_discovery_order(tmp_path):
  planner = _ScriptedPlanner(fail=True)
  cfg = _cfg(action_policy="llm", llm_policy=LLMPolicyConfig(provider="openrouter", model="x/y"), max_depth=1)
  graph = _run(cfg, tmp_path, llm_client=planner)
  assert graph.metrics["coverage"]["llm_plan_fallbacks"] >= 1 and len(graph.nodes) > 1
  assert all(r["source"] == "fallback" for r in _log(tmp_path) if r["event"] == "plan")


def test_network_guard_rules():
  guard = NetworkGuard(allow_hosts=("127.0.0.1",))
  assert guard.allows("GET", "https://example.com/x") and guard.allows("HEAD", "https://example.com/x")
  assert not guard.allows("POST", "https://api.example.com/articles")
  assert guard.allows("POST", "http://127.0.0.1:8000/api")
  assert not NetworkGuard().allows("DELETE", "http://127.0.0.1:8000/api")


def test_app_config_reads_exploration_settings(tmp_path):
  path = tmp_path / "cfg.json"
  path.write_text(json.dumps({"url": "http://127.0.0.1:4200/", "crawl": {
    "action_policy": "llm", "llm_policy": {"provider": "openrouter", "model": "anthropic/claude-haiku-5.5", "timeout_s": 30},
    "submission": {"allow_hosts": ["localhost", "127.0.0.1"]}, "network_guard": True}}))
  cfg = load_app_config(path).crawl
  assert cfg.resolved_action_policy() == "llm" and cfg.llm_policy.model == "anthropic/claude-haiku-5.5"
  assert cfg.submission_allow_hosts == ("localhost", "127.0.0.1") and cfg.network_guard
  assert CrawlConfig().resolved_action_policy() == "discovery"
  assert CrawlConfig(prioritize_action_candidates=True).resolved_action_policy() == "heuristic"
  with pytest.raises(ValueError):
    path.write_text(json.dumps({"crawl": {"action_policy": "random"}}))
    load_app_config(path)


def test_llm_policy_ranks_beyond_the_action_budget():
  from src.crawler.crawl.priority.common import _candidate_scan_limit
  # Algorithm 1: rank all safe actions, then execute the top k_max; discovery order keeps its k_max window
  assert _candidate_scan_limit(CrawlConfig(max_actions_per_state=5)) == 5
  assert _candidate_scan_limit(CrawlConfig(max_actions_per_state=5, action_policy="llm")) == 25
  assert _candidate_scan_limit(CrawlConfig(max_actions_per_state=5, prioritize_action_candidates=True)) == 25


def test_formless_fields_are_filled_without_submit_on_allowed_hosts(tmp_path):
  from src.crawler.crawl.actions.forms import discover_forms, fill_submit_candidate, perform_fill_submit

  async def check(base_url: str):
    playwright = pytest.importorskip("playwright.async_api")
    manager = await playwright.async_playwright().start()
    try:
      browser = await manager.chromium.launch(headless=True)
      page = await browser.new_page()
      await page.goto(f"{base_url}/formless/", wait_until="domcontentloaded")
      none, _ = await discover_forms(page, allow_hosts=())
      groups, skips = await discover_forms(page, allow_hosts=("127.0.0.1",))
      assert none == [] and not skips
      assert len(groups) == 2 and all(g.formless and not g.submit_selector for g in groups)
      date_group = next(g for g in groups if g.fields[0].type == "date")
      candidate = fill_submit_candidate(page, date_group, "valid", {date_group.fields[0].selector: "2026-06-16"})
      assert await perform_fill_submit(page, candidate, timeout_ms=3_000)
      assert await page.locator("#slot").count() == 1  # the page reacted; nothing was submitted
      await browser.close()
    finally:
      await manager.stop()

  with serve_fixture_root(FIXTURES) as server:
    asyncio.run(check(server.base_url))
