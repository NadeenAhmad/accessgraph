from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from scripts.development.serve_spa_fixtures import serve_fixture_root
from src.crawler.crawl.entrypoint import CrawlConfig, run_crawl
from src.crawler.state.hashing import rendered_dom_identity_hash_for_page


def _fixture_url(base_url: str, fixture_name: str) -> str:
  return f"{base_url}/{fixture_name}/"


def _crawl_config(
  *,
  max_depth: int,
  max_actions_per_state: int,
  max_states: int = 20,
) -> CrawlConfig:
  return CrawlConfig(
    max_states=max_states,
    max_depth=max_depth,
    max_actions_per_state=max_actions_per_state,
    back_timeout_ms=3_000,
    traversal_strategy="bfs",
    scope_policy="same_origin",
    prioritize_action_candidates=False,
    enable_tile_screenshots=False,
    wait_timeout_ms=300,
  )


async def _with_chromium(callback):
  playwright = pytest.importorskip("playwright.async_api")
  try:
    manager = await playwright.async_playwright().start()
  except Exception as exc:
    pytest.skip(f"Playwright could not start in this environment: {exc}")
  browser = None
  try:
    try:
      browser = await manager.chromium.launch(headless=True)
    except Exception as exc:
      pytest.skip(f"Playwright Chromium is unavailable: {exc}")
    return await callback(browser)
  finally:
    if browser is not None:
      await browser.close()
    await manager.stop()


async def _crawl_fixture(start_url: str, run_dir: Path, cfg: CrawlConfig):
  async def run(browser):
    page = await browser.new_page(viewport={"width": 1280, "height": 720})
    await page.goto(start_url, wait_until="domcontentloaded")
    return await run_crawl(page, start_url, run_dir, cfg)

  return await _with_chromium(run)


def _state_dirs(run_dir: Path) -> list[Path]:
  return sorted(path for path in (run_dir / "states").iterdir() if path.is_dir())


def _edge_texts(graph) -> list[str]:
  return [
    str(edge.get("action", {}).get("text") or "")
    for edge in graph.edges
  ]


def _coverage_value(graph, key: str) -> int:
  coverage = graph.metrics.get("coverage", {})
  return int(coverage.get(key, 0)) if isinstance(coverage, dict) else 0


def test_fixture_crawl_writes_artifacts_and_duplicate_transition(tmp_path):
  with serve_fixture_root() as server:
    run_dir = tmp_path / "deterministic-run"
    graph = asyncio.run(
      _crawl_fixture(
        _fixture_url(server.base_url, "deterministic"),
        run_dir,
        _crawl_config(max_depth=2, max_actions_per_state=5),
      )
    )

  states = _state_dirs(run_dir)
  assert len(states) == len(graph.nodes)
  assert (run_dir / "states" / "state_0000" / "dom.html").exists()
  assert (run_dir / "states" / "state_0000" / "screenshot.png").exists()
  assert (run_dir / "states" / "state_0000" / "metadata.json").exists()
  assert (run_dir / "states" / "state_0000" / "accessibility_context.json").exists()

  root_metadata = json.loads((run_dir / "states" / "state_0000" / "metadata.json").read_text(encoding="utf-8"))
  assert root_metadata["depth"] == 0
  assert root_metadata["parent_state"] is None
  assert root_metadata["action_from_parent"] is None

  child_metadata = [
    json.loads((state_dir / "metadata.json").read_text(encoding="utf-8"))
    for state_dir in states
    if state_dir.name != "state_0000"
  ]
  assert child_metadata
  assert all("html_hash" in metadata for metadata in child_metadata)
  assert all("dom_identity_hash" in metadata for metadata in child_metadata)
  assert any(metadata["parent_state"] == "state_0000" for metadata in child_metadata)

  assert any(edge["from"] != edge["to"] and edge["to"] == "state_0000" for edge in graph.edges)
  assert _coverage_value(graph, "existing_state_hits") >= 1
  assert _coverage_value(graph, "actions_no_state_change") >= 1
  assert not list(run_dir.rglob("*candidate*.jsonl"))
  assert not (run_dir / "crawl_resume").exists()


def test_fixture_crawl_enforces_same_origin_links(tmp_path):
  with serve_fixture_root() as server:
    start_url = _fixture_url(server.base_url, "links")
    run_dir = tmp_path / "links-run"
    graph = asyncio.run(
      _crawl_fixture(
        start_url,
        run_dir,
        _crawl_config(max_depth=1, max_actions_per_state=3),
      )
    )

  start_origin = urlparse(start_url).netloc
  node_urls = [str(node.get("url") or "") for node in graph.nodes.values()]
  assert len(node_urls) == 2
  assert all(urlparse(url).netloc == start_origin for url in node_urls)
  assert not any("example.org" in url for url in node_urls)
  assert any("/links/about.html" in url for url in node_urls)
  assert _coverage_value(graph, "actions_skipped_out_of_scope_pre") >= 1


def test_fixture_crawl_submits_only_safe_prefilled_forms(tmp_path):
  with serve_fixture_root() as server:
    run_dir = tmp_path / "forms-run"
    graph = asyncio.run(
      _crawl_fixture(
        _fixture_url(server.base_url, "forms"),
        run_dir,
        _crawl_config(max_depth=1, max_actions_per_state=5),
      )
    )

  texts = _edge_texts(graph)
  assert texts == ["Save preference"]
  assert len(_state_dirs(run_dir)) == 2
  assert "Login" not in texts
  assert "Submit empty form" not in texts
  assert "Upload file" not in texts

  saved_dom = "\n".join(path.read_text(encoding="utf-8") for path in run_dir.glob("states/*/dom.html"))
  assert "Preference saved" in saved_dom
  assert "crawler_input" not in saved_dom
  assert "checked=\"\"" not in saved_dom
  assert not list(run_dir.rglob("*candidate*.jsonl"))


def test_fixture_browser_hash_normalization_policy():
  async def run_hash_check(browser):
    page = await browser.new_page(viewport={"width": 1280, "height": 720})
    with serve_fixture_root() as server:
      await page.goto(_fixture_url(server.base_url, "deterministic"), wait_until="domcontentloaded")
      initial_hash = await rendered_dom_identity_hash_for_page(page)

      await page.click("#hidden-noise")
      assert await rendered_dom_identity_hash_for_page(page) == initial_hash

      await page.click("#animate-only")
      assert await rendered_dom_identity_hash_for_page(page) == initial_hash

      await page.click("#paint-status")
      assert await rendered_dom_identity_hash_for_page(page) != initial_hash

  asyncio.run(_with_chromium(run_hash_check))
