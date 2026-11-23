import asyncio
from types import SimpleNamespace

import pytest

from src.crawler.crawl.actions import ActionCandidate
from src.crawler.crawl.entrypoint import (
  CrawlConfig,
  run_crawl,
)
from src.crawler.state.hashing import html_hash, rendered_dom_identity_hash_for_page
from tests.crawler_test_helpers import FakePage, make_state_artifact


def test_head_only_same_url_drift_does_not_create_new_state(monkeypatch, tmp_path):
  class HeadDriftPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.variant = "a"

    async def content(self) -> str:
      if self.variant == "b":
        return "<html><head><meta name='b'><meta name='a'></head><body><main>same-body</main></body></html>"
      return "<html><head><meta name='a'><meta name='b'></head><body><main>same-body</main></body></html>"

  page = HeadDriftPage(url="https://example.com/home")

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    return await make_state_artifact(page_obj, state_id, route="/home", include_dom_identity_hash=True)

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 1
    return [
      ActionCandidate(
        locator=object(),
        action_type="click",
        strategy_name="buttons",
        text="Refresh",
        identity="button|refresh",
      )
    ]

  async def fake_perform_action(_candidate, *, wait_timeout_ms=2000):
    page.variant = "b"
    return True

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    page_obj.variant = "a"
    return True

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._navigate_to_url", fake_navigate_to_url)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=1),
    )
  )

  assert len(graph.nodes) == 1
  assert len(graph.edges) == 0
  assert graph.metrics["coverage"]["actions_no_state_change"] == 1


def test_perform_action_type_error_propagates_without_retry(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/home")
  candidate = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="Broken action",
    identity="button|broken",
  )
  perform_calls = {"count": 0}

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    return await make_state_artifact(page_obj, state_id, route="/home", include_dom_identity_hash=True)

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 1
    return [candidate]

  async def fake_perform_action(_candidate, *, wait_timeout_ms=2000):
    perform_calls["count"] += 1
    raise TypeError("perform action bug")

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)

  with pytest.raises(TypeError, match="perform action bug"):
    asyncio.run(
      run_crawl(
        page=page,
        start_url="https://example.com/home",
        run_dir=tmp_path,
        cfg=CrawlConfig(max_depth=1, max_actions_per_state=1),
      )
    )

  assert perform_calls["count"] == 1


def test_stable_same_url_revisit_hits_existing_state(monkeypatch, tmp_path):
  class RevisitPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "panel_a":
        return "<html><head><meta name='a'><meta name='b'></head><body><main>panel-body</main></body></html>"
      if self.view == "panel_b":
        return "<html><head><meta name='b'><meta name='a'></head><body><main>panel-body</main></body></html>"
      return "<html><head><meta name='root'></head><body><main>root-body</main></body></html>"

  page = RevisitPage(url="https://example.com/home")

  first = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Panel A",
    href="/panel",
    identity="link|panel-a",
  )
  second = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Panel B",
    href="/panel",
    identity="link|panel-b",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    route = "/panel" if page_obj.url.endswith("/panel") else "/home"
    return await make_state_artifact(page_obj, state_id, route=route, include_dom_identity_hash=True)

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 2
    if page.view == "root":
      return [first, second]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    page.url = "https://example.com/panel"
    if candidate.identity == first.identity:
      page.view = "panel_a"
      return True
    if candidate.identity == second.identity:
      page.view = "panel_b"
      return True
    return False

  async def fake_back(page_obj, _fallback_url, _timeout_ms):
    page_obj.url = "https://example.com/home"
    page_obj.view = "root"

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    page_obj.view = "root" if url.endswith("/home") else "panel_a"
    return True

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._navigate_to_url", fake_navigate_to_url)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=2),
    )
  )

  assert len(graph.nodes) == 2
  assert len(graph.edges) == 2
  assert graph.edges[0]["to"] == "state_0001"
  assert graph.edges[1]["to"] == "state_0001"
  assert graph.metrics["coverage"]["existing_state_hits"] == 1


def test_existing_state_hit_does_not_reassign_root_parent(monkeypatch, tmp_path):
  class ToggleRootPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "panel":
        return "<html><head><meta name='panel'></head><body><main>panel-open</main></body></html>"
      return "<html><head><meta name='root'></head><body><main>root-closed</main></body></html>"

  page = ToggleRootPage(url="https://example.com/guide")

  open_panel = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="summary",
    text="Open details",
    identity="summary|open-details",
  )
  close_panel = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="summary",
    text="Close details",
    identity="summary|close-details",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    return await make_state_artifact(page_obj, state_id, route="/guide", include_dom_identity_hash=True)

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit >= 1
    if page.view == "root":
      return [open_panel]
    return [close_panel]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == open_panel.identity:
      page.view = "panel"
      return True
    if candidate.identity == close_panel.identity:
      page.view = "root"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    page_obj.view = "root"
    return True

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._navigate_to_url", fake_navigate_to_url)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/guide",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 2
  assert len(graph.edges) == 2
  assert graph.edges[0]["from"] == "state_0000"
  assert graph.edges[0]["to"] == "state_0001"
  assert graph.edges[1]["from"] == "state_0001"
  assert graph.edges[1]["to"] == "state_0000"
  assert graph.nodes["state_0000"]["parent_state_id"] is None
  assert graph.nodes["state_0000"]["incoming_action"] is None
  assert graph.nodes["state_0001"]["parent_state_id"] == "state_0000"
  assert graph.nodes["state_0001"]["incoming_action"]["text"] == "Open details"
  assert graph.metrics["coverage"]["existing_state_hits"] == 1


def test_bfs_root_restore_reuses_current_page_when_it_already_matches(monkeypatch, tmp_path):
  class RootPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "drifted":
        return "<html><body>drifted-root</body></html>"
      return "<html><body>stable-root</body></html>"

  page = RootPage(url="https://example.com/home")

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    return await make_state_artifact(page_obj, state_id, route="/home", include_dom_identity_hash=True)

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 1
    return [
      ActionCandidate(
        locator=object(),
        action_type="click",
        strategy_name="links",
        text="Next",
        href="/next",
      )
    ]

  async def fake_perform_action(_candidate, *, wait_timeout_ms=2000):
    page.url = "https://example.com/next"
    page.view = "drifted"
    return True

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    page_obj.view = "drifted"
    return True

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._navigate_to_url", fake_navigate_to_url)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 2
  assert len(graph.edges) == 1
  assert graph.edges[0]["from"] == "state_0000"
  assert graph.edges[0]["to"] == "state_0001"
  assert graph.metrics["stop"]["state_expansion_stop_reasons"]["restore_failed"] == 0


def test_no_change_action_restores_canonical_state(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/home")
  restore_calls = {"count": 0}

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/home",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 1
    return [
      ActionCandidate(
        locator=object(),
        action_type="click",
        strategy_name="links",
        text="Self link",
        href="/home",
      )
    ]

  async def fake_perform_action(_candidate, *, wait_timeout_ms=2000):
    # Intentional no-op: same URL and same DOM hash.
    return True

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    restore_calls["count"] += 1
    page_obj.url = url
    return True

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._navigate_to_url", fake_navigate_to_url)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=1),
    )
  )

  assert len(graph.edges) == 0
  assert restore_calls["count"] == 1


def test_no_change_menu_action_does_not_leak_hidden_links(monkeypatch, tmp_path):
  class MenuPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      # Deliberately keep the state identity stable between the closed and
      # opened menu views. This reproduces a drawer/menu action that mutates
      # the live interaction context without creating a recorded state.
      if self.view in {"root", "menu"}:
        return "<html><body><main>same-route</main></body></html>"
      return "<html><body><main>about</main></body></html>"

  page = MenuPage(url="https://example.com/home")
  executed: list[str] = []
  restore_calls = {"count": 0}
  menu = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="menu",
    identity="button|menu",
  )
  about = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="About",
    href="/about",
    identity="link|about",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    html = await page_obj.content()
    dom_identity_hash = await rendered_dom_identity_hash_for_page(page_obj)
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=html_hash(html),
      dom_identity_hash=dom_identity_hash,
      title=state_id,
      route="/home",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 2
    if page.view == "menu":
      return [about]
    if menu.identity in page_attempted:
      return []
    return [menu]

  page_attempted: set[str] = set()

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
    if candidate.identity:
      page_attempted.add(candidate.identity)
    if candidate.text == "menu":
      page.view = "menu"
      return True
    if candidate.text == "About":
      page.view = "about"
      page.url = "https://example.com/about"
      return True
    return False

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    restore_calls["count"] += 1
    page_obj.url = url
    page_obj.view = "root"
    return True

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._navigate_to_url", fake_navigate_to_url)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=2),
    )
  )

  assert executed == ["menu"]
  assert restore_calls["count"] == 1
  assert len(graph.edges) == 0


def test_menu_open_state_exposes_hidden_link_from_menu_state(monkeypatch, tmp_path):
  class MenuPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "about":
        return "<html><body><main>about</main></body></html>"
      return "<html><body><main>same-route</main></body></html>"

    async def evaluate(self, script):
      if "normalizeNode" not in str(script):
        return await self.content()
      if self.view == "menu":
        return "same-route\n@@interactive:menu-open-about-visible"
      if self.view == "about":
        return "about"
      return "same-route\n@@interactive:menu-closed"

  page = MenuPage(url="https://example.com/home")
  executed: list[str] = []
  menu = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="menu",
    identity="button|menu",
  )
  about = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="About",
    href="/about",
    identity="link|about",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    html = await page_obj.content()
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=html_hash(html),
      dom_identity_hash=await rendered_dom_identity_hash_for_page(page_obj),
      title=state_id,
      route="/about" if page_obj.view == "about" else "/home",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit >= 2
    if page.view == "menu":
      return [about]
    if page.view == "about":
      return []
    return [menu]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
    if candidate.text == "menu":
      page.view = "menu"
      return True
    if candidate.text == "About":
      page.view = "about"
      page.url = "https://example.com/about"
      return True
    return False

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    page_obj.view = "root"
    return True

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._navigate_to_url", fake_navigate_to_url)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=2),
    )
  )

  assert executed.count("menu") >= 1
  assert executed.count("About") >= 1
  assert len(graph.nodes) == 3
  assert [(edge["from"], edge["action"]["text"], edge["to"]) for edge in graph.edges] == [
    ("state_0000", "menu", "state_0001"),
    ("state_0001", "About", "state_0002"),
  ]


def test_candidates_are_refreshed_between_attempts(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/home")
  calls = {"get_candidates": 0}
  executed: list[str] = []

  cand_a = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="A",
    href="/home",
  )
  cand_b = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="B",
    href="/b",
  )
  cand_c = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="C",
    href="/c",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/home",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 2
    calls["get_candidates"] += 1
    if calls["get_candidates"] == 1:
      return [cand_a, cand_b]
    return [cand_c]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
    if candidate.text == "C":
      page.url = "https://example.com/c"
    return True

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    return True

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._navigate_to_url", fake_navigate_to_url)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=2),
    )
  )

  # Fresh candidate fetch should be used on the second attempt.
  assert calls["get_candidates"] >= 2
  assert executed == ["A", "C"]
  assert len(graph.edges) == 1
  assert graph.edges[0]["action"]["text"] == "C"


def test_distinct_candidate_identities_are_not_collapsed_within_one_state(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/home")
  executed: list[str] = []

  first = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|Read more|main>section:nth-of-type(1)>button:nth-of-type(1)",
    text="Read more",
    href="/details",
  )
  second = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|Read more|main>section:nth-of-type(2)>button:nth-of-type(1)",
    text="Read more",
    href="/details",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/home",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 2
    return [first, second]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.identity)
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=2),
    )
  )

  assert executed == [first.identity, second.identity]
  assert graph.metrics["coverage"]["actions_attempted"] == 2


def test_out_of_scope_href_is_skipped_before_click(monkeypatch, tmp_path):
  page = FakePage(url="https://reactrouter.com/home")
  perform_calls = {"count": 0}
  back_calls = {"count": 0}

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/home",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 1
    return [
      ActionCandidate(
        locator=object(),
        action_type="click",
        strategy_name="links",
        text="GitHub",
        href="https://github.com/remix-run/react-router",
      )
    ]

  async def fake_perform_action(_candidate, *, wait_timeout_ms=2000):
    perform_calls["count"] += 1
    return True

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    back_calls["count"] += 1

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://reactrouter.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=1, scope_policy="same_domain", traversal_strategy="dfs"),
    )
  )

  assert len(graph.edges) == 0
  assert perform_calls["count"] == 0
  assert back_calls["count"] == 0


def test_out_of_scope_navigation_is_reverted_after_action(monkeypatch, tmp_path):
  page = FakePage(url="https://reactrouter.com/home")
  back_calls = {"count": 0}

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/home",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 1
    return [
      ActionCandidate(
        locator=object(),
        action_type="type",
        strategy_name="inputs",
        text="Search",
        href=None,
      )
    ]

  async def fake_perform_action(_candidate, *, wait_timeout_ms=2000):
    page.url = "https://github.com/remix-run/react-router"
    return True

  async def fake_back(page_obj, fallback_url, _timeout_ms):
    back_calls["count"] += 1
    page_obj.url = fallback_url

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://reactrouter.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=1, scope_policy="same_domain", traversal_strategy="dfs"),
    )
  )

  assert len(graph.edges) == 0
  assert back_calls["count"] == 1
  assert page.url == "https://reactrouter.com/home"


def test_tracking_query_only_change_is_treated_as_same_state(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/docs?utm_source=newsletter")

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/docs",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 1
    return [
      ActionCandidate(
        locator=object(),
        action_type="click",
        strategy_name="links",
        text="Campaign variant",
        href="/docs?utm_source=twitter",
      )
    ]

  async def fake_perform_action(_candidate, *, wait_timeout_ms=2000):
    page.url = "https://example.com/docs?utm_source=twitter"
    return True

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/docs?utm_source=newsletter",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=1),
    )
  )

  assert len(graph.edges) == 0
  assert len(graph.nodes) == 1


def test_crawl_populates_coverage_and_stop_metrics(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/")

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 1
    return []

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=1),
    )
  )

  metrics = graph.metrics
  coverage = metrics["coverage"]
  stop = metrics["stop"]

  assert metrics["status"] == "success"
  assert coverage["new_states_discovered"] == 1
  assert coverage["states_total"] == 1
  assert coverage["edges_total"] == 0
  assert coverage["candidate_scans"] >= 1
  assert stop["states_expanded"] == 1
  assert stop["state_expansion_stop_reasons"]["no_candidates"] == 1
  assert stop["termination_reason"] == "frontier_exhausted"
  assert stop["frontier_exhausted"] is True


def test_stop_metrics_capture_action_budget_exhaustion(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/")
  call_count = {"n": 0}

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 2
    call_count["n"] += 1
    return [
      ActionCandidate(
        locator=object(),
        action_type="click",
        strategy_name="links",
        text=f"Try {call_count['n']}",
        href=f"/try-{call_count['n']}",
      )
    ]

  async def fake_perform_action(_candidate, *, wait_timeout_ms=2000):
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=2),
    )
  )

  stop = graph.metrics["stop"]
  coverage = graph.metrics["coverage"]
  assert stop["state_expansion_stop_reasons"]["action_budget_exhausted"] == 1
  assert coverage["actions_attempted"] == 2
