import asyncio
from types import SimpleNamespace

from src.crawler.crawl.actions import ActionCandidate
from src.crawler.crawl.entrypoint import (
  CrawlConfig,
  run_crawl,
)
from src.crawler.crawl.navigation.restore import StateRestorer
from src.crawler.graph.graph import StateGraph
from src.crawler.state.hashing import html_hash, raw_html_state_identity_hash
from tests.crawler_test_helpers import FakePage


def test_replay_path_returns_none_for_cycle():
  graph = StateGraph()
  graph.add_state("root", "https://example.com/home", "root-hash", "root-restore", "root-key", "Root", "/home")
  graph.add_state("a", "https://example.com/a", "a-hash", "a-restore", "a-key", "A", "/a")
  graph.add_state("b", "https://example.com/b", "b-hash", "b-restore", "b-key", "B", "/b")
  graph.nodes["a"]["parent_state_id"] = "b"
  graph.nodes["a"]["incoming_action"] = {"type": "click", "strategy": "links", "text": "to-a"}
  graph.nodes["b"]["parent_state_id"] = "a"
  graph.nodes["b"]["incoming_action"] = {"type": "click", "strategy": "links", "text": "to-b"}

  async def fake_candidates(_page, _limit):
    return []

  async def fake_action(_candidate):
    return False

  async def fake_nav(_page, _url, _timeout):
    return True

  async def fake_back(_page, _url, _timeout):
    return None

  restorer = StateRestorer(
    page=FakePage(url="https://example.com/home"),
    graph=graph,
    start_url="https://example.com/home",
    back_timeout_ms=1000,
    replay_candidate_scan_limit=5,
    in_scope=lambda _url: True,
    root_state_id_getter=lambda: "root",
    increment_coverage=lambda _key, _amount=1: None,
    record_replay_attempt_metrics=lambda _result: None,
    record_replay_failure=lambda _result: None,
    get_action_candidates_fn=fake_candidates,
    perform_action_fn=fake_action,
    action_timeout_type=TimeoutError,
    navigate_to_url_fn=fake_nav,
    best_effort_back_fn=fake_back,
  )

  assert restorer._replay_path("a") is None

def test_crawl_records_transition_when_url_changes_even_if_html_hash_same(monkeypatch, tmp_path):
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
    return [
      ActionCandidate(
        locator=object(),
        action_type="click",
        strategy_name="links",
        text="Go next",
        href="/next",
      )
    ]

  async def fake_perform_action(_candidate, *, wait_timeout_ms=2000):
    page.url = "https://example.com/next"
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
      start_url="https://example.com/",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=1),
    )
  )

  # URL change should be treated as a distinct state even with same DOM hash.
  assert len(graph.edges) == 1
  assert graph.edges[0]["from"] == "state_0000"
  assert graph.edges[0]["to"] == "state_0001"
  assert graph.edges[0]["action"]["type"] == "click"
  assert len(graph.nodes) == 2


def test_crawl_bfs_records_transition_when_url_changes_even_if_html_hash_same(monkeypatch, tmp_path):
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
    return [
      ActionCandidate(
        locator=object(),
        action_type="click",
        strategy_name="links",
        text="Go next",
        href="/next",
      )
    ]

  async def fake_perform_action(_candidate, *, wait_timeout_ms=2000):
    page.url = "https://example.com/next"
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
      start_url="https://example.com/",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=1, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.edges) == 1
  assert graph.edges[0]["from"] == "state_0000"
  assert graph.edges[0]["to"] == "state_0001"
  assert graph.edges[0]["action"]["type"] == "click"
  assert len(graph.nodes) == 2


def test_bfs_replays_same_url_state_before_expansion(monkeypatch, tmp_path):
  class ReplayPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "menu":
        return "<html><body>menu-open</body></html>"
      if self.view == "item":
        return "<html><body>item-page</body></html>"
      return "<html><body>root</body></html>"

  page = ReplayPage(url="https://example.com/home")

  open_menu = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|open-menu",
    text="Open menu",
  )
  open_item = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|open-item",
    text="Item details",
    href="/item",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    route = "/item" if page_obj.view == "item" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      return [open_menu]
    if page.view == "menu":
      assert limit >= 1
      return [open_item]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == open_menu.identity:
      page.view = "menu"
      return True
    if candidate.identity == open_item.identity:
      page.view = "item"
      page.url = "https://example.com/item"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    if url == "https://example.com/item":
      page_obj.view = "item"
    else:
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 3
  assert len(graph.edges) == 2
  assert graph.edges[0]["action"]["text"] == "Open menu"
  assert graph.edges[1]["action"]["text"] == "Item details"
  assert graph.metrics["coverage"]["state_restore_replay_first_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_first_attempts"] == 0


def test_bfs_replay_accepts_stable_same_url_restore_match(monkeypatch, tmp_path):
  class ReplayStablePage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"
      self.menu_render_count = 0

    async def content(self) -> str:
      if self.view == "menu":
        if self.menu_render_count <= 1:
          return "<html><head><meta name='a'><meta name='b'></head><body><div>menu-open</div></body></html>"
        return "<html><head><meta name='b'><meta name='a'></head><body><div>menu-open</div></body></html>"
      if self.view == "item":
        return "<html><head><meta name='x'></head><body><div>item-page</div></body></html>"
      return "<html><head><meta name='root'></head><body><div>root</div></body></html>"

  page = ReplayStablePage(url="https://example.com/home")

  open_menu = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|open-menu",
    text="Open menu",
  )
  open_item = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|open-item",
    text="Item details",
    href="/item",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    html = await page_obj.content()
    state_hash = html_hash(html)
    route = "/item" if page_obj.view == "item" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=raw_html_state_identity_hash(html),
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      return [open_menu]
    if page.view == "menu":
      assert limit >= 1
      return [open_item]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == open_menu.identity:
      page.view = "menu"
      page.menu_render_count += 1
      return True
    if candidate.identity == open_item.identity:
      page.view = "item"
      page.url = "https://example.com/item"
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 3
  assert len(graph.edges) == 2
  assert graph.edges[1]["action"]["text"] == "Item details"
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_stable_successes"] >= 1


def test_bfs_uses_url_first_restore_for_url_changing_link_state(monkeypatch, tmp_path):
  class ReplayFallbackPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "step-two":
        return "<html><body>step-two</body></html>"
      if self.view == "done":
        return "<html><body>done</body></html>"
      return "<html><body>root</body></html>"

  page = ReplayFallbackPage(url="https://example.com/home")
  root_candidate_visible = {"value": True}

  go_to_step_two = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|to-step-two",
    text="Step two",
    href="/step-two",
  )
  finish = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|finish",
    text="Finish",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    route = "/step-two" if page_obj.view == "step-two" else "/done" if page_obj.view == "done" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      if root_candidate_visible["value"]:
        return [go_to_step_two]
      return []
    if page.view == "step-two":
      assert limit >= 1
      return [finish]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == go_to_step_two.identity:
      page.view = "step-two"
      page.url = "https://example.com/step-two"
      root_candidate_visible["value"] = False
      return True
    if candidate.identity == finish.identity:
      page.view = "done"
      page.url = "https://example.com/done"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    if url == "https://example.com/step-two":
      page_obj.view = "step-two"
    elif url == "https://example.com/done":
      page_obj.view = "done"
    else:
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 3
  assert len(graph.edges) == 2
  assert graph.edges[1]["action"]["text"] == "Finish"
  assert graph.metrics["coverage"]["state_restore_url_first_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_first_attempts"] == 0
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] == 0


def test_bfs_url_first_restore_uses_replay_when_url_restore_misses_state(monkeypatch, tmp_path):
  class ReplayFallbackPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "step-two":
        return "<html><body>step-two</body></html>"
      if self.view == "done":
        return "<html><body>done</body></html>"
      return "<html><body>root</body></html>"

  page = ReplayFallbackPage(url="https://example.com/home")

  go_to_step_two = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|to-step-two",
    text="Step two",
    href="/step-two",
  )
  finish = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|finish",
    text="Finish",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    route = "/step-two" if page_obj.view == "step-two" else "/done" if page_obj.view == "done" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      return [go_to_step_two]
    if page.view == "step-two":
      assert limit >= 1
      return [finish]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == go_to_step_two.identity:
      page.view = "step-two"
      page.url = "https://example.com/step-two"
      return True
    if candidate.identity == finish.identity:
      page.view = "done"
      page.url = "https://example.com/done"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    if url == "https://example.com/done":
      page_obj.view = "done"
    else:
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 3
  assert len(graph.edges) == 2
  assert graph.edges[1]["action"]["text"] == "Finish"
  assert graph.metrics["coverage"]["state_restore_url_first_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_first_attempts"] == 0


def test_bfs_url_first_restore_accepts_stable_match(monkeypatch, tmp_path):
  class ReplayStableUrlPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"
      self.step_two_render_count = 0

    async def content(self) -> str:
      if self.view == "step-two":
        if self.step_two_render_count <= 1:
          return "<html><head><meta name='a'><meta name='b'></head><body><div>step-two</div></body></html>"
        return "<html><head><meta name='b'><meta name='a'></head><body><div>step-two</div></body></html>"
      if self.view == "done":
        return "<html><head><meta name='done'></head><body><div>done</div></body></html>"
      return "<html><head><meta name='root'></head><body><div>root</div></body></html>"

  page = ReplayStableUrlPage(url="https://example.com/home")

  go_to_step_two = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|to-step-two",
    text="Step two",
    href="/step-two",
  )
  finish = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|finish",
    text="Finish",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    html = await page_obj.content()
    state_hash = html_hash(html)
    route = "/step-two" if page_obj.view == "step-two" else "/done" if page_obj.view == "done" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=raw_html_state_identity_hash(html),
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      return [go_to_step_two]
    if page.view == "step-two":
      assert limit >= 1
      return [finish]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == go_to_step_two.identity:
      page.view = "step-two"
      page.url = "https://example.com/step-two"
      page.step_two_render_count += 1
      return True
    if candidate.identity == finish.identity:
      page.view = "done"
      page.url = "https://example.com/done"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    if url == "https://example.com/step-two":
      page_obj.view = "step-two"
      page_obj.step_two_render_count += 1
    elif url == "https://example.com/done":
      page_obj.view = "done"
    else:
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 3
  assert len(graph.edges) == 2
  assert graph.edges[1]["action"]["text"] == "Finish"
  assert graph.metrics["coverage"]["state_restore_url_first_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_stable_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] == 0


def test_bfs_url_first_restore_accepts_url_and_title_match_for_route_state(monkeypatch, tmp_path):
  class ReplayTitleSoftMatchPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"
      self.docs_render_count = 0

    async def content(self) -> str:
      if self.view == "docs":
        if self.docs_render_count <= 1:
          return (
            "<html><head><title>Docs</title></head><body>"
            "<div>core docs content</div>"
            "<aside><div>Featured: Query</div></aside>"
            "</body></html>"
          )
        return (
          "<html><head><title>Docs</title></head><body>"
          "<div>core docs content</div>"
          "<aside><div>Featured: DB</div></aside>"
          "</body></html>"
        )
      if self.view == "done":
        return "<html><head><title>Done</title></head><body><div>done</div></body></html>"
      return "<html><head><title>Root</title></head><body><div>root</div></body></html>"

  page = ReplayTitleSoftMatchPage(url="https://example.com/home")

  go_to_docs = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|to-docs",
    text="Docs",
    href="/docs",
  )
  finish = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|finish",
    text="Finish",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id=None, **_kwargs):
    html = await page_obj.content()
    route = "/docs" if page_obj.view == "docs" else "/done" if page_obj.view == "done" else "/home"
    title = "Docs" if page_obj.view == "docs" else "Done" if page_obj.view == "done" else "Root"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=html_hash(html),
      dom_identity_hash=raw_html_state_identity_hash(html),
      title=title,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      return [go_to_docs]
    if page.view == "docs":
      assert limit >= 1
      return [finish]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == go_to_docs.identity:
      page.view = "docs"
      page.url = "https://example.com/docs"
      page.docs_render_count += 1
      return True
    if candidate.identity == finish.identity:
      page.view = "done"
      page.url = "https://example.com/done"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    if url == "https://example.com/docs":
      page_obj.view = "docs"
      page_obj.docs_render_count += 1
    elif url == "https://example.com/done":
      page_obj.view = "done"
    else:
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 3
  assert len(graph.edges) == 2
  assert graph.edges[1]["action"]["text"] == "Finish"
  assert graph.metrics["coverage"]["state_restore_url_first_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] == 0


def test_same_url_button_state_does_not_accept_url_and_title_match():
  class MenuVariantPage(FakePage):
    async def content(self) -> str:
      return (
        "<html><head><title>Dashboard</title></head><body>"
        "<div>menu-open</div><aside><div>variant-b</div></aside>"
        "</body></html>"
      )

  graph = StateGraph()
  root_html = "<html><head><title>Dashboard</title></head><body><div>root</div></body></html>"
  menu_html = (
    "<html><head><title>Dashboard</title></head><body>"
    "<div>menu-open</div><aside><div>variant-a</div></aside>"
    "</body></html>"
  )
  graph.add_state(
    "root",
    "https://example.com/home",
    html_hash(root_html),
    raw_html_state_identity_hash(root_html),
    "root-key",
    "Dashboard",
    "/home",
  )
  graph.add_state(
    "menu",
    "https://example.com/home",
    html_hash(menu_html),
    raw_html_state_identity_hash(menu_html),
    "menu-key",
    "Dashboard",
    "/home",
  )
  graph.nodes["menu"]["parent_state_id"] = "root"
  graph.nodes["menu"]["incoming_action"] = {
    "type": "click",
    "strategy": "buttons",
    "text": "Open menu",
    "href": None,
  }

  async def fake_candidates(_page, _limit):
    return []

  async def fake_action(_candidate):
    return False

  async def fake_nav(_page, _url, _timeout):
    return True

  async def fake_back(_page, _url, _timeout):
    return None

  restorer = StateRestorer(
    page=MenuVariantPage(url="https://example.com/home"),
    graph=graph,
    start_url="https://example.com/home",
    back_timeout_ms=1000,
    replay_candidate_scan_limit=5,
    in_scope=lambda _url: True,
    root_state_id_getter=lambda: "root",
    increment_coverage=lambda _key, _amount=1: None,
    record_replay_attempt_metrics=lambda _result: None,
    record_replay_failure=lambda _result: None,
    get_action_candidates_fn=fake_candidates,
    perform_action_fn=fake_action,
    action_timeout_type=TimeoutError,
    navigate_to_url_fn=fake_nav,
    best_effort_back_fn=fake_back,
  )

  match = asyncio.run(restorer._current_page_restore_match("menu"))

  assert restorer._should_allow_url_title_restore_match("menu") is False
  assert match.matched is False


def test_open_modal_page_does_not_soft_match_plain_route_state():
  root_html = (
    "<html><head><title>Task Manager</title></head><body>"
    "<main><h1>Task Manager</h1><button>Create task</button></main>"
    "</body></html>"
  )
  modal_html = (
    "<html><head><title>Task Manager</title></head><body>"
    "<main><h1>Task Manager</h1><button>Create task</button></main>"
    "<dialog open aria-modal=\"true\"><h2>Create task</h2></dialog>"
    "</body></html>"
  )

  class ModalOpenPage(FakePage):
    async def content(self) -> str:
      return modal_html

    async def evaluate(self, script, *_args):
      if "dialog[open]" in script or "aria-modal" in script:
        return True
      return (
        "<body><main><h1>Task Manager</h1><button>Create task</button></main>"
        "<dialog open=\"\" aria-modal=\"true\"><h2>Create task</h2></dialog></body>"
      )

  graph = StateGraph()
  graph.add_state(
    "root",
    "https://example.com/tasks",
    html_hash(root_html),
    raw_html_state_identity_hash(root_html),
    "root-key",
    "Task Manager",
    "/tasks",
  )

  async def fake_candidates(_page, _limit):
    return []

  async def fake_action(_candidate):
    return False

  async def fake_nav(_page, _url, _timeout):
    return True

  async def fake_back(_page, _url, _timeout):
    return None

  restorer = StateRestorer(
    page=ModalOpenPage(url="https://example.com/tasks"),
    graph=graph,
    start_url="https://example.com/tasks",
    back_timeout_ms=1000,
    replay_candidate_scan_limit=5,
    in_scope=lambda _url: True,
    root_state_id_getter=lambda: "root",
    increment_coverage=lambda _key, _amount=1: None,
    record_replay_attempt_metrics=lambda _result: None,
    record_replay_failure=lambda _result: None,
    get_action_candidates_fn=fake_candidates,
    perform_action_fn=fake_action,
    action_timeout_type=TimeoutError,
    navigate_to_url_fn=fake_nav,
    best_effort_back_fn=fake_back,
  )

  match = asyncio.run(restorer._current_page_restore_match("root"))

  assert restorer._should_allow_url_title_restore_match("root") is True
  assert match.matched is False


def test_open_modal_page_can_strict_match_modal_target_state():
  modal_html = (
    "<html><head><title>Task Manager</title></head><body>"
    "<main><h1>Task Manager</h1><button>Create task</button></main>"
    "<dialog open aria-modal=\"true\"><h2>Create task</h2></dialog>"
    "</body></html>"
  )

  class ModalTargetPage(FakePage):
    async def content(self) -> str:
      return modal_html

  graph = StateGraph()
  graph.add_state(
    "dialog",
    "https://example.com/tasks",
    html_hash(modal_html),
    raw_html_state_identity_hash(modal_html),
    "dialog-key",
    "Task Manager",
    "/tasks",
  )

  async def fake_candidates(_page, _limit):
    return []

  async def fake_action(_candidate):
    return False

  async def fake_nav(_page, _url, _timeout):
    return True

  async def fake_back(_page, _url, _timeout):
    return None

  restorer = StateRestorer(
    page=ModalTargetPage(url="https://example.com/tasks"),
    graph=graph,
    start_url="https://example.com/tasks",
    back_timeout_ms=1000,
    replay_candidate_scan_limit=5,
    in_scope=lambda _url: True,
    root_state_id_getter=lambda: "dialog",
    increment_coverage=lambda _key, _amount=1: None,
    record_replay_attempt_metrics=lambda _result: None,
    record_replay_failure=lambda _result: None,
    get_action_candidates_fn=fake_candidates,
    perform_action_fn=fake_action,
    action_timeout_type=TimeoutError,
    navigate_to_url_fn=fake_nav,
    best_effort_back_fn=fake_back,
  )

  match = asyncio.run(restorer._current_page_restore_match("dialog"))

  assert match.matched is True
  assert match.strict is True


def test_bfs_replay_records_candidate_not_found_after_url_first_mismatch(monkeypatch, tmp_path):
  class ReplayFallbackPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "step-two":
        return "<html><body>step-two</body></html>"
      if self.view == "done":
        return "<html><body>done</body></html>"
      return "<html><body>root</body></html>"

  page = ReplayFallbackPage(url="https://example.com/home")
  root_candidate_visible = {"value": True}

  go_to_step_two = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|to-step-two",
    text="Step two",
    href="/step-two",
  )
  finish = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|finish",
    text="Finish",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    route = "/step-two" if page_obj.view == "step-two" else "/done" if page_obj.view == "done" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      if root_candidate_visible["value"]:
        return [go_to_step_two]
      return []
    if page.view == "step-two":
      assert limit >= 1
      return [finish]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == go_to_step_two.identity:
      page.view = "step-two"
      page.url = "https://example.com/step-two"
      root_candidate_visible["value"] = False
      return True
    if candidate.identity == finish.identity:
      page.view = "done"
      page.url = "https://example.com/done"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    if url == "https://example.com/done":
      page_obj.view = "done"
    else:
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 2
  assert len(graph.edges) == 1
  assert graph.metrics["coverage"]["state_restore_url_first_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failures"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_reasons"]["candidate_not_found"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_stages"]["step"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_step_indices"]["1"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_path_lengths"]["1"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_fallbacks"] == 0


def test_bfs_replay_records_action_timeout_failure_reason(monkeypatch, tmp_path):
  class ReplayTimeoutPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "step-two":
        return "<html><body>step-two</body></html>"
      if self.view == "done":
        return "<html><body>done</body></html>"
      return "<html><body>root</body></html>"

  page = ReplayTimeoutPage(url="https://example.com/home")
  go_to_step_two_calls = {"count": 0}

  go_to_step_two = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|to-step-two",
    text="Step two",
    href="/step-two",
  )
  finish = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|finish",
    text="Finish",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    route = "/step-two" if page_obj.view == "step-two" else "/done" if page_obj.view == "done" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      return [go_to_step_two]
    if page.view == "step-two":
      assert limit >= 1
      return [finish]
    return []

  async def fake_perform_action_with_timeout(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == go_to_step_two.identity:
      go_to_step_two_calls["count"] += 1
      if go_to_step_two_calls["count"] >= 2:
        from src.crawler.crawl.actions.execution import ActionTimeout
        raise ActionTimeout("replay timed out")
      page.view = "step-two"
      page.url = "https://example.com/step-two"
      return True
    if candidate.identity == finish.identity:
      page.view = "done"
      page.url = "https://example.com/done"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    if url == "https://example.com/done":
      page_obj.view = "done"
    else:
      page_obj.view = "root"
    return True

  monkeypatch.setattr("src.crawler.crawl.crawl_session.capture_state_artifacts", fake_capture_state_artifacts)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.get_action_candidates", fake_get_action_candidates)
  monkeypatch.setattr("src.crawler.crawl.crawl_session.perform_action", fake_perform_action_with_timeout)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._best_effort_back", fake_back)
  monkeypatch.setattr("src.crawler.crawl.crawl_session._navigate_to_url", fake_navigate_to_url)

  graph = asyncio.run(
    run_crawl(
      page=page,
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=3, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 2
  assert len(graph.edges) == 1
  assert graph.metrics["coverage"]["state_restore_url_first_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failures"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_reasons"]["action_timeout"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_stages"]["step"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_step_indices"]["1"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_path_lengths"]["1"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_fallbacks"] == 0


def test_bfs_replay_records_final_state_mismatch_failure_reason(monkeypatch, tmp_path):
  class ReplayMismatchPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "step-two":
        return "<html><body>step-two</body></html>"
      if self.view == "step-two-drift":
        return "<html><body>step-two-drift</body></html>"
      if self.view == "done":
        return "<html><body>done</body></html>"
      return "<html><body>root</body></html>"

  page = ReplayMismatchPage(url="https://example.com/home")
  go_to_step_two_calls = {"count": 0}

  go_to_step_two = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|to-step-two",
    text="Step two",
    href="/step-two",
  )
  finish = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|finish",
    text="Finish",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    route = "/step-two" if page_obj.view in {"step-two", "step-two-drift"} else "/done" if page_obj.view == "done" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      return [go_to_step_two]
    if page.view in {"step-two", "step-two-drift"}:
      assert limit >= 1
      return [finish]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == go_to_step_two.identity:
      go_to_step_two_calls["count"] += 1
      if go_to_step_two_calls["count"] == 1:
        page.view = "step-two"
      else:
        page.view = "step-two-drift"
      page.url = "https://example.com/step-two"
      return True
    if candidate.identity == finish.identity:
      page.view = "done"
      page.url = "https://example.com/done"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    if url == "https://example.com/done":
      page_obj.view = "done"
    else:
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=3, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 2
  assert len(graph.edges) == 1
  assert graph.metrics["coverage"]["state_restore_url_first_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failures"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_reasons"]["final_state_mismatch"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_stages"]["final_verification"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_step_indices"]["1"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_path_lengths"]["1"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_soft_matches"]["same_url"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_soft_matches"]["same_route"] == 0
  assert graph.metrics["coverage"]["state_restore_url_fallbacks"] == 0


def test_bfs_replay_records_same_route_soft_match(monkeypatch, tmp_path):
  class ReplayRouteSoftMatchPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "step-two":
        return "<html><body>step-two</body></html>"
      if self.view == "step-two-drift":
        return "<html><body>step-two-drift</body></html>"
      if self.view == "done":
        return "<html><body>done</body></html>"
      return "<html><body>root</body></html>"

  page = ReplayRouteSoftMatchPage(url="https://example.com/home")
  go_to_step_two_calls = {"count": 0}

  go_to_step_two = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|to-step-two",
    text="Step two",
    href="/step-two",
  )
  finish = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|finish",
    text="Finish",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    route = "/step-two" if page_obj.view in {"step-two", "step-two-drift"} else "/done" if page_obj.view == "done" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      return [go_to_step_two]
    if page.view in {"step-two", "step-two-drift"}:
      assert limit >= 1
      return [finish]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == go_to_step_two.identity:
      go_to_step_two_calls["count"] += 1
      if go_to_step_two_calls["count"] == 1:
        page.view = "step-two"
        page.url = "https://example.com/step-two"
      else:
        page.view = "step-two-drift"
        page.url = "https://example.com/step-two?variant=2"
      return True
    if candidate.identity == finish.identity:
      page.view = "done"
      page.url = "https://example.com/done"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    if url == "https://example.com/done":
      page_obj.view = "done"
    else:
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=3, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 2
  assert len(graph.edges) == 1
  assert graph.metrics["coverage"]["state_restore_url_first_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failures"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_reasons"]["final_state_mismatch"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_stages"]["final_verification"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_soft_matches"]["same_url"] == 0
  assert graph.metrics["coverage"]["state_restore_replay_soft_matches"]["same_route"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_fallbacks"] == 0


def test_bfs_replay_records_second_step_failure_index(monkeypatch, tmp_path):
  class ReplaySecondStepPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"
      self.item_visible = True

    async def content(self) -> str:
      if self.view == "menu":
        return "<html><body>menu-open</body></html>"
      if self.view == "item":
        return "<html><body>item-page</body></html>"
      return "<html><body>root</body></html>"

  page = ReplaySecondStepPage(url="https://example.com/home")

  open_menu = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|open-menu",
    text="Open menu",
  )
  open_item = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|open-item",
    text="Item details",
    href="/item",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    route = "/item" if page_obj.view == "item" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      return [open_menu]
    if page.view == "menu":
      assert limit >= 1
      if page.item_visible:
        return [open_item]
      return []
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == open_menu.identity:
      page.view = "menu"
      return True
    if candidate.identity == open_item.identity:
      page.view = "item"
      page.url = "https://example.com/item"
      page.item_visible = False
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=3, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 3
  assert len(graph.edges) == 2
  assert graph.metrics["coverage"]["state_restore_url_first_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_successes"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failures"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_reasons"]["candidate_not_found"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_stages"]["step"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_failure_step_indices"]["2"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_path_lengths"]["2"] >= 1
  assert graph.metrics["coverage"]["state_restore_url_fallbacks"] == 0


def test_bfs_replay_uses_wider_candidate_window_than_normal_budget(monkeypatch, tmp_path):
  class ReplayWindowPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"
      self.root_revisit_count = 0

    async def content(self) -> str:
      if self.view == "panel":
        return "<html><body>panel-open</body></html>"
      if self.view == "done":
        return "<html><body>done</body></html>"
      return "<html><body>root</body></html>"

  page = ReplayWindowPage(url="https://example.com/home")

  open_panel = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|open-panel",
    text="Open panel",
  )
  decoy = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|decoy",
    text="Ignore me",
  )
  finish = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|finish",
    text="Finish",
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
    if page.view == "root":
      page.root_revisit_count += 1
      if page.root_revisit_count == 1:
        assert limit == 1
        return [open_panel]
      assert limit > 1
      return [decoy, open_panel]
    if page.view == "panel":
      assert limit == 1
      return [finish]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == open_panel.identity:
      page.view = "panel"
      return True
    if candidate.identity == finish.identity:
      page.view = "done"
      page.url = "https://example.com/home"
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=1, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 3
  assert len(graph.edges) == 2
  assert graph.edges[0]["action"]["text"] == "Open panel"
  assert graph.edges[1]["action"]["text"] == "Finish"
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_successes"] >= 1


def test_bfs_replay_prefers_exact_identity_over_same_text_fallback(monkeypatch, tmp_path):
  class ReplayIdentityPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "menu":
        return "<html><body>menu-open</body></html>"
      if self.view == "wrong":
        return "<html><body>wrong-details</body></html>"
      if self.view == "right":
        return "<html><body>right-details</body></html>"
      if self.view == "done":
        return "<html><body>done</body></html>"
      return "<html><body>root</body></html>"

  page = ReplayIdentityPage(url="https://example.com/home")

  open_menu = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|open-menu",
    text="Open menu",
  )
  wrong_details = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|details-wrong",
    text="Open details",
  )
  right_details = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|details-right",
    text="Open details",
  )
  finish = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|finish",
    text="Finish",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/home" if page_obj.view != "done" else "/done",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 1
      return [open_menu]
    if page.view == "menu":
      assert limit >= 2
      return [wrong_details, right_details]
    if page.view == "right":
      assert limit >= 1
      return [finish]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == open_menu.identity:
      page.view = "menu"
      return True
    if candidate.identity == wrong_details.identity:
      page.view = "wrong"
      return True
    if candidate.identity == right_details.identity:
      page.view = "right"
      return True
    if candidate.identity == finish.identity:
      page.view = "done"
      page.url = "https://example.com/done"
      return True
    return False

  async def fake_back(_page_obj, _fallback_url, _timeout_ms):
    return None

  async def fake_navigate_to_url(page_obj, url, _timeout_ms):
    page_obj.url = url
    if url == "https://example.com/done":
      page_obj.view = "done"
    else:
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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=3, max_actions_per_state=2, traversal_strategy="bfs"),
    )
  )

  assert len(graph.nodes) == 5
  assert len(graph.edges) == 4
  assert graph.edges[2]["action"]["identity"] == right_details.identity
  assert graph.edges[3]["action"]["text"] == "Finish"
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_successes"] >= 1


def test_dfs_replays_same_url_state_when_back_loses_dynamic_context(monkeypatch, tmp_path):
  class DfsReplayPage(FakePage):
    def __init__(self, url: str):
      super().__init__(url)
      self.view = "root"

    async def content(self) -> str:
      if self.view == "menu":
        return "<html><body>menu-open</body></html>"
      if self.view == "item-a":
        return "<html><body>item-a</body></html>"
      if self.view == "item-b":
        return "<html><body>item-b</body></html>"
      return "<html><body>root</body></html>"

  page = DfsReplayPage(url="https://example.com/home")

  open_menu = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="button|open-menu",
    text="Open menu",
  )
  open_item_a = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|item-a",
    text="Item A",
    href="/a",
  )
  open_item_b = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    identity="link|item-b",
    text="Item B",
    href="/b",
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    route = "/a" if page_obj.view == "item-a" else "/b" if page_obj.view == "item-b" else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    if page.view == "root":
      assert limit >= 2
      return [open_menu]
    if page.view == "menu":
      assert limit >= 2
      return [open_item_a, open_item_b]
    return []

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.identity == open_menu.identity:
      page.view = "menu"
      return True
    if candidate.identity == open_item_a.identity:
      page.view = "item-a"
      page.url = "https://example.com/a"
      return True
    if candidate.identity == open_item_b.identity:
      page.view = "item-b"
      page.url = "https://example.com/b"
      return True
    return False

  async def fake_back(page_obj, fallback_url, _timeout_ms):
    page_obj.url = fallback_url
    page_obj.view = "root"

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
      start_url="https://example.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(max_depth=2, max_actions_per_state=2, traversal_strategy="dfs"),
    )
  )

  assert len(graph.nodes) == 4
  assert len(graph.edges) == 3
  assert graph.edges[0]["action"]["text"] == "Open menu"
  assert graph.edges[1]["action"]["text"] == "Item A"
  assert graph.edges[2]["action"]["text"] == "Item B"
  assert graph.metrics["coverage"]["state_restore_replay_attempts"] >= 1
  assert graph.metrics["coverage"]["state_restore_replay_successes"] >= 1
