from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from scripts.development.serve_spa_fixtures import serve_fixture_root
from src.crawler.crawl.entrypoint import CrawlConfig, run_crawl


def _fixture_url(base_url: str, fixture_name: str) -> str:
  return f"{base_url}/{fixture_name}/"


def _crawl_config(
  *,
  max_depth: int = 1,
  max_actions_per_state: int = 1,
  wait_timeout_ms: int = 500,
) -> CrawlConfig:
  return CrawlConfig(
    max_states=12,
    max_depth=max_depth,
    max_actions_per_state=max_actions_per_state,
    back_timeout_ms=3_000,
    traversal_strategy="bfs",
    scope_policy="same_origin",
    prioritize_action_candidates=False,
    enable_tile_screenshots=False,
    wait_timeout_ms=wait_timeout_ms,
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


async def _crawl_fixture(
  browser: Any,
  *,
  base_url: str,
  fixture_name: str,
  run_root: Path,
  cfg: CrawlConfig,
):
  page = await browser.new_page(viewport={"width": 1280, "height": 720})
  start_url = _fixture_url(base_url, fixture_name)
  run_dir = run_root / fixture_name
  try:
    await page.goto(start_url, wait_until="domcontentloaded")
    graph = await run_crawl(page, start_url, run_dir, cfg)
    return graph, run_dir
  finally:
    await page.close()


def _state_dirs(run_dir: Path) -> list[Path]:
  return sorted(path for path in (run_dir / "states").iterdir() if path.is_dir())


def _saved_dom(run_dir: Path) -> str:
  return "\n".join(path.read_text(encoding="utf-8") for path in run_dir.glob("states/*/dom.html"))


def _edge_actions(graph) -> list[dict[str, object]]:
  return [
    edge.get("action", {})
    for edge in graph.edges
    if isinstance(edge.get("action", {}), dict)
  ]


def _edge_texts(graph) -> list[str]:
  return [str(action.get("text") or "") for action in _edge_actions(graph)]


def _coverage_value(graph, key: str) -> int:
  coverage = graph.metrics.get("coverage", {})
  return int(coverage.get(key, 0)) if isinstance(coverage, dict) else 0


def _assert_state_count(graph, run_dir: Path, expected: int) -> None:
  assert len(graph.nodes) == expected
  assert len(_state_dirs(run_dir)) == expected


def _assert_root_artifacts(run_dir: Path) -> None:
  root = run_dir / "states" / "state_0000"
  assert (root / "dom.html").exists()
  assert (root / "screenshot.png").exists()
  assert (root / "metadata.json").exists()
  assert (root / "accessibility_context.json").exists()
  assert not list(run_dir.rglob("*candidate*.jsonl"))


def test_required_spa_operation_fixtures(tmp_path):
  async def run(browser):
    configs = {
      "button_click": _crawl_config(),
      "role_button_click": _crawl_config(),
      "modal_open_close": _crawl_config(max_depth=2),
      "tab_switch": _crawl_config(max_depth=2, max_actions_per_state=2),
      "accordion_disclosure": _crawl_config(max_depth=2),
      "same_origin_link": _crawl_config(max_actions_per_state=2),
      "dropdown_select": _crawl_config(),
      "prefilled_form_submit": _crawl_config(max_actions_per_state=4),
      "async_dom_update": _crawl_config(wait_timeout_ms=1_000),
      "hidden_dom_ignored": _crawl_config(),
      "duplicate_state_loop": _crawl_config(max_depth=2),
      "visual_style_state": _crawl_config(),
    }

    with serve_fixture_root() as server:
      results = {
        fixture_name: await _crawl_fixture(
          browser,
          base_url=server.base_url,
          fixture_name=fixture_name,
          run_root=tmp_path,
          cfg=cfg,
        )
        for fixture_name, cfg in configs.items()
      }

      button_graph, button_dir = results["button_click"]
      _assert_root_artifacts(button_dir)
      _assert_state_count(button_graph, button_dir, 2)
      assert _edge_texts(button_graph) == ["Show button state"]
      assert "Button state visible" in _saved_dom(button_dir)

      role_graph, role_dir = results["role_button_click"]
      _assert_root_artifacts(role_dir)
      _assert_state_count(role_graph, role_dir, 2)
      assert _edge_texts(role_graph) == ["Open role state"]
      assert "Role button state visible" in _saved_dom(role_dir)

      modal_graph, modal_dir = results["modal_open_close"]
      _assert_root_artifacts(modal_dir)
      _assert_state_count(modal_graph, modal_dir, 2)
      assert "Open modal" in _edge_texts(modal_graph)
      assert any(
        edge["to"] == "state_0000" and edge.get("action", {}).get("text") == "Close modal"
        for edge in modal_graph.edges
      )
      assert _coverage_value(modal_graph, "existing_state_hits") >= 1

      tab_graph, tab_dir = results["tab_switch"]
      _assert_root_artifacts(tab_dir)
      _assert_state_count(tab_graph, tab_dir, 2)
      assert "Details tab" in _edge_texts(tab_graph)
      assert "Overview tab" in _edge_texts(tab_graph)
      assert _coverage_value(tab_graph, "existing_state_hits") >= 1

      accordion_graph, accordion_dir = results["accordion_disclosure"]
      _assert_root_artifacts(accordion_dir)
      _assert_state_count(accordion_graph, accordion_dir, 2)
      assert _edge_texts(accordion_graph).count("Expand disclosure") == 2
      assert _coverage_value(accordion_graph, "existing_state_hits") >= 1

      link_graph, link_dir = results["same_origin_link"]
      _assert_root_artifacts(link_dir)
      _assert_state_count(link_graph, link_dir, 2)
      node_urls = [str(node.get("url") or "") for node in link_graph.nodes.values()]
      start_origin = urlparse(_fixture_url(server.base_url, "same_origin_link")).netloc
      assert all(urlparse(url).netloc == start_origin for url in node_urls)
      assert any("/same_origin_link/about.html" in url for url in node_urls)
      assert not any("example.org" in url for url in node_urls)
      assert _coverage_value(link_graph, "actions_skipped_out_of_scope_pre") >= 1

      select_graph, select_dir = results["dropdown_select"]
      _assert_root_artifacts(select_dir)
      _assert_state_count(select_graph, select_dir, 2)
      assert any(
        action.get("type") == "select" and action.get("strategy") == "selects"
        for action in _edge_actions(select_graph)
      )
      assert "Selected alpha" in _saved_dom(select_dir)

      form_graph, form_dir = results["prefilled_form_submit"]
      _assert_root_artifacts(form_dir)
      _assert_state_count(form_graph, form_dir, 2)
      assert _edge_texts(form_graph) == ["Submit ready form"]
      assert "Ready form submitted" in _saved_dom(form_dir)
      assert "Submit empty form" not in _edge_texts(form_graph)
      assert "Login" not in _edge_texts(form_graph)
      assert "Upload file" not in _edge_texts(form_graph)
      assert "crawler_input" not in _saved_dom(form_dir)

      async_graph, async_dir = results["async_dom_update"]
      _assert_root_artifacts(async_dir)
      _assert_state_count(async_graph, async_dir, 2)
      assert _edge_texts(async_graph) == ["Start async update"]
      assert "Async state ready" in _saved_dom(async_dir)

      hidden_graph, hidden_dir = results["hidden_dom_ignored"]
      _assert_root_artifacts(hidden_dir)
      _assert_state_count(hidden_graph, hidden_dir, 1)
      assert hidden_graph.edges == []
      assert _coverage_value(hidden_graph, "actions_no_state_change") >= 1

      duplicate_graph, duplicate_dir = results["duplicate_state_loop"]
      _assert_root_artifacts(duplicate_dir)
      _assert_state_count(duplicate_graph, duplicate_dir, 2)
      assert "Go alternate" in _edge_texts(duplicate_graph)
      assert any(
        edge["to"] == "state_0000" and edge.get("action", {}).get("text") == "Back home"
        for edge in duplicate_graph.edges
      )
      assert _coverage_value(duplicate_graph, "existing_state_hits") >= 1

      visual_graph, visual_dir = results["visual_style_state"]
      _assert_root_artifacts(visual_dir)
      _assert_state_count(visual_graph, visual_dir, 2)
      assert _edge_texts(visual_graph) == ["Paint visual state"]

  asyncio.run(_with_chromium(run))
