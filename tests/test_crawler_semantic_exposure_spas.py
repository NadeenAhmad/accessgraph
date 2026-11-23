from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.development.serve_spa_fixtures import serve_fixture_root
from src.crawler.crawl.entrypoint import CrawlConfig, run_crawl


def _fixture_url(base_url: str, fixture_name: str) -> str:
  return f"{base_url}/semantic_exposure/{fixture_name}/"


def _crawl_config(
  *,
  max_depth: int = 1,
  max_actions_per_state: int = 1,
) -> CrawlConfig:
  return CrawlConfig(
    max_states=10,
    max_depth=max_depth,
    max_actions_per_state=max_actions_per_state,
    back_timeout_ms=3_000,
    traversal_strategy="bfs",
    scope_policy="same_origin",
    prioritize_action_candidates=False,
    enable_tile_screenshots=False,
    wait_timeout_ms=500,
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


def _dom_by_state(run_dir: Path) -> dict[str, str]:
  return {
    state_dir.name: (state_dir / "dom.html").read_text(encoding="utf-8")
    for state_dir in _state_dirs(run_dir)
  }


def _semantic_by_state(run_dir: Path) -> dict[str, dict[str, Any]]:
  return {
    state_dir.name: json.loads((state_dir / "accessibility_context.json").read_text(encoding="utf-8"))
    for state_dir in _state_dirs(run_dir)
  }


def _edge_texts(graph) -> list[str]:
  return [
    str(edge.get("action", {}).get("text") or "")
    for edge in graph.edges
  ]


def _items(payloads: dict[str, dict[str, Any]], key: str) -> list[dict[str, Any]]:
  out: list[dict[str, Any]] = []
  for payload in payloads.values():
    raw = payload.get(key, [])
    if isinstance(raw, list):
      out.extend(item for item in raw if isinstance(item, dict))
  return out


def _body_text_samples(payloads: dict[str, dict[str, Any]]) -> str:
  samples: list[str] = []
  for payload in payloads.values():
    page = payload.get("page", {})
    if isinstance(page, dict):
      samples.append(str(page.get("body_text_sample") or ""))
  return "\n".join(samples)


def _assert_state_count(graph, run_dir: Path, expected: int) -> None:
  assert len(graph.nodes) == expected
  assert len(_state_dirs(run_dir)) == expected


def _assert_state_artifacts(run_dir: Path) -> None:
  for state_dir in _state_dirs(run_dir):
    assert (state_dir / "dom.html").exists()
    assert (state_dir / "screenshot.png").exists()
    assert (state_dir / "metadata.json").exists()
    assert (state_dir / "accessibility_context.json").exists()
  assert not list(run_dir.rglob("*candidate*.jsonl"))


def _assert_neutral_payloads(payloads: dict[str, dict[str, Any]]) -> None:
  forbidden_key_parts = ("candidate", "violation", "issue", "severity", "wcag", "confidence", "classification")

  def walk(value: Any) -> None:
    if isinstance(value, dict):
      for key, child in value.items():
        lowered = str(key).lower()
        assert not any(part in lowered for part in forbidden_key_parts)
        walk(child)
    elif isinstance(value, list):
      for child in value:
        walk(child)

  for payload in payloads.values():
    assert payload.get("schema_version") == "1"
    assert isinstance(payload.get("state_context"), dict)
    assert isinstance(payload.get("page"), dict)
    assert payload.get("extraction_metadata", {}).get("status") == "success"
    for key in (
      "referenced_elements",
      "images",
      "videos",
      "links",
      "buttons",
      "forms",
      "form_controls",
      "headings",
      "landmarks",
      "focusables",
      "focus_order",
      "relationships",
    ):
      assert isinstance(payload.get(key), list)
    walk(payload)


def test_semantic_exposure_fixtures_reach_evidence_states(tmp_path):
  async def run(browser):
    configs = {
      "dynamic_route_title": _crawl_config(),
      "language_switcher": _crawl_config(),
      "form_mode_switcher": _crawl_config(max_actions_per_state=2),
      "nav_landmark_toggle": _crawl_config(),
      "image_gallery_modal": _crawl_config(),
      "validation_color_only": _crawl_config(),
      "keyboard_focus_order": _crawl_config(),
      "media_player_panel": _crawl_config(),
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

    route_graph, route_dir = results["dynamic_route_title"]
    _assert_state_artifacts(route_dir)
    _assert_state_count(route_graph, route_dir, 2)
    route_doms = _dom_by_state(route_dir)
    route_semantic = _semantic_by_state(route_dir)
    _assert_neutral_payloads(route_semantic)
    assert _edge_texts(route_graph) == ["Open project route"]
    assert any("Project overview" in dom for dom in route_doms.values())
    assert any("/semantic_exposure/dynamic_route_title/project?view=overview#summary" in str(node.get("url") or "") for node in route_graph.nodes.values())
    assert any(item.get("text") == "Project overview" for item in _items(route_semantic, "headings"))

    language_graph, language_dir = results["language_switcher"]
    _assert_state_artifacts(language_dir)
    _assert_state_count(language_graph, language_dir, 2)
    language_doms = _dom_by_state(language_dir)
    language_semantic = _semantic_by_state(language_dir)
    _assert_neutral_payloads(language_semantic)
    assert _edge_texts(language_graph) == ["Switch language"]
    assert any('lang="es"' in dom and "Bienvenido al panel" in dom for dom in language_doms.values())
    assert "Bienvenido al panel" in _body_text_samples(language_semantic)
    language_samples = _items(language_semantic, "language_samples")
    assert any(
      item.get("language_text") == "Bienvenido al panel"
      and item.get("local_lang") == ""
      and item.get("ancestor_lang") == "es"
      for item in language_samples
    )

    form_graph, form_dir = results["form_mode_switcher"]
    _assert_state_artifacts(form_dir)
    _assert_state_count(form_graph, form_dir, 3)
    form_doms = _dom_by_state(form_dir)
    form_semantic = _semantic_by_state(form_dir)
    _assert_neutral_payloads(form_semantic)
    assert _edge_texts(form_graph) == ["Show contact form", "Show profile form"]
    assert any("Contact form" in dom for dom in form_doms.values())
    assert any("Profile form" in dom for dom in form_doms.values())
    form_controls = _items(form_semantic, "form_controls")
    assert any(control.get("autocomplete") == "email" for control in form_controls)
    assert any(control.get("autocomplete") == "organization" for control in form_controls)
    assert any(control.get("label") == "Email address" for control in form_controls)
    assert any(item.get("type") == "form_contains" for item in _items(form_semantic, "relationships"))

    nav_graph, nav_dir = results["nav_landmark_toggle"]
    _assert_state_artifacts(nav_dir)
    _assert_state_count(nav_graph, nav_dir, 2)
    nav_semantic = _semantic_by_state(nav_dir)
    _assert_neutral_payloads(nav_semantic)
    assert _edge_texts(nav_graph) == ["Open navigation regions"]
    landmarks = _items(nav_semantic, "landmarks")
    links = _items(nav_semantic, "links")
    assert any(item.get("tag") == "nav" and item.get("aria_label") == "Primary navigation" for item in landmarks)
    assert any(item.get("role") == "complementary" for item in landmarks)
    assert any(item.get("text") == "Contact support" for item in links)
    assert any(item.get("type") == "landmark_contains" for item in _items(nav_semantic, "relationships"))

    image_graph, image_dir = results["image_gallery_modal"]
    _assert_state_artifacts(image_dir)
    _assert_state_count(image_graph, image_dir, 2)
    image_semantic = _semantic_by_state(image_dir)
    _assert_neutral_payloads(image_semantic)
    assert _edge_texts(image_graph) == ["Open image detail"]
    assert any(item.get("alt") == "Team planning board" for item in _items(image_semantic, "images"))
    assert any(item.get("text") == "Related image story" for item in _items(image_semantic, "links"))
    assert any(item.get("text") == "Close image detail" for item in _items(image_semantic, "buttons"))

    validation_graph, validation_dir = results["validation_color_only"]
    _assert_state_artifacts(validation_dir)
    _assert_state_count(validation_graph, validation_dir, 2)
    validation_doms = _dom_by_state(validation_dir)
    validation_semantic = _semantic_by_state(validation_dir)
    _assert_neutral_payloads(validation_semantic)
    assert _edge_texts(validation_graph) == ["Validate profile"]
    assert any("Validation status displayed." in dom and "background-color" in dom for dom in validation_doms.values())
    assert any(control.get("label") == "Account email" for control in _items(validation_semantic, "form_controls"))
    visual_cues = _items(validation_semantic, "visual_cues")
    assert any(
      item.get("text") == "Validation status displayed."
      and item.get("has_inline_color") is True
      for item in visual_cues
    )

    focus_graph, focus_dir = results["keyboard_focus_order"]
    _assert_state_artifacts(focus_dir)
    _assert_state_count(focus_graph, focus_dir, 2)
    focus_semantic = _semantic_by_state(focus_dir)
    _assert_neutral_payloads(focus_semantic)
    assert _edge_texts(focus_graph) == ["Show focus layout"]
    focusable = _items(focus_semantic, "focusables")
    assert any(item.get("text") == "Third visually" for item in focusable)
    assert any(item.get("text") == "First visually" for item in focusable)
    assert any(item.get("type") == "" and item.get("tag") == "input" for item in focusable)
    traversal = _items(focus_semantic, "focus_traversal")
    traversal_texts = [item.get("text") for item in traversal]
    layout_start = traversal_texts.index("Third visually")
    assert traversal_texts[layout_start:layout_start + 3] == [
      "Third visually",
      "First visually",
      "",
    ]

    media_graph, media_dir = results["media_player_panel"]
    _assert_state_artifacts(media_dir)
    _assert_state_count(media_graph, media_dir, 2)
    media_doms = _dom_by_state(media_dir)
    media_semantic = _semantic_by_state(media_dir)
    _assert_neutral_payloads(media_semantic)
    assert _edge_texts(media_graph) == ["Show media player"]
    assert any("<video" in dom and "Transcript" in dom for dom in media_doms.values())
    media_videos = _items(media_semantic, "videos")
    assert any(any(track.get("kind") == "captions" for track in video.get("tracks", [])) for video in media_videos)
    assert any("training video explains" in str(video.get("nearby_transcript_text") or "") for video in media_videos)
    assert any((state_dir / "screenshot.png").exists() for state_dir in _state_dirs(media_dir))

  asyncio.run(_with_chromium(run))
