import asyncio
from types import SimpleNamespace

from src.crawler.crawl.actions import ActionCandidate
from src.crawler.crawl.entrypoint import (
  CrawlConfig,
  run_crawl,
)
from src.crawler.crawl.priority import _candidate_priority_score
from src.crawler.state.hashing import html_hash

class FakePage:
  def __init__(self, url: str):
    self.url = url

  async def content(self) -> str:
    # Intentionally constant so DOM hash does not change.
    return "<html><body>same-dom</body></html>"

  async def wait_for_load_state(self, *_args, **_kwargs) -> None:
    return None

def test_prioritize_action_candidates_uses_extended_candidate_window(monkeypatch, tmp_path):
  page = FakePage(url="https://reactrouter.com/home")
  seen_limits: list[int] = []
  executed: list[str] = []

  external = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="External",
    href="https://github.com/remix-run/react-router",
  )
  internal = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Changelog",
    href="/changelog",
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
    seen_limits.append(limit)
    if limit <= 1:
      return [external]
    return [external, internal]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
    if candidate.text == "Changelog":
      page.url = "https://reactrouter.com/changelog"
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
      start_url="https://reactrouter.com/home",
      run_dir=tmp_path,
      cfg=CrawlConfig(
        max_depth=1,
        max_actions_per_state=1,
        scope_policy="same_domain",
        prioritize_action_candidates=True,
      ),
    )
  )

  assert seen_limits and seen_limits[0] > 1
  assert executed == ["Changelog"]
  assert len(graph.edges) == 1
  assert graph.edges[0]["action"]["text"] == "Changelog"
  assert graph.edges[0]["action"]["priority_score"] > 0


def test_prioritize_action_candidates_prefers_dismiss_control_before_in_scope_link(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/home")
  executed: list[str] = []

  internal_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Documentation",
    href="/docs",
  )
  dismiss_button = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="Close banner",
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
    assert limit == 5
    return [internal_link, dismiss_button]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
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
      cfg=CrawlConfig(
        max_depth=1,
        max_actions_per_state=1,
        prioritize_action_candidates=True,
      ),
    )
  )

  assert executed == ["Close banner"]
  assert graph.metrics["coverage"]["actions_attempted"] == 1


def test_prioritize_action_candidates_prefers_collapsed_expander_before_in_scope_link(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/home")
  executed: list[str] = []

  internal_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Guides",
    href="/guides",
  )
  collapsed_menu = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="Open menu",
    aria_expanded="false",
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
    assert limit == 5
    return [internal_link, collapsed_menu]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
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
      cfg=CrawlConfig(
        max_depth=1,
        max_actions_per_state=1,
        prioritize_action_candidates=True,
      ),
    )
  )

  assert executed == ["Open menu"]
  assert graph.metrics["coverage"]["actions_attempted"] == 1


def test_prioritize_action_candidates_prefers_main_button_over_header_nav_link(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/home")
  executed: list[str] = []

  header_pricing = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Pricing",
    href="/pricing",
    in_header=True,
    in_nav=True,
    ancestor_tags=("nav", "header"),
  )
  demo_button = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="Open demo",
    in_main=True,
    ancestor_tags=("section", "main"),
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
    assert limit == 5
    return [header_pricing, demo_button]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
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
      cfg=CrawlConfig(
        max_depth=1,
        max_actions_per_state=1,
        prioritize_action_candidates=True,
      ),
    )
  )

  assert executed == ["Open demo"]
  assert graph.metrics["coverage"]["actions_attempted"] == 1


def test_prioritize_action_candidates_prefers_main_content_link_over_header_nav_link(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/home")
  executed: list[str] = []

  header_docs = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Docs",
    href="/docs",
    in_header=True,
    in_nav=True,
    aria_current="page",
    ancestor_tags=("nav", "header"),
  )
  main_changelog = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Changelog",
    href="/changelog",
    in_main=True,
    ancestor_tags=("article", "main"),
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
    assert limit == 5
    return [header_docs, main_changelog]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
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
      cfg=CrawlConfig(
        max_depth=1,
        max_actions_per_state=1,
        prioritize_action_candidates=True,
      ),
    )
  )

  assert executed == ["Changelog"]
  assert graph.metrics["coverage"]["actions_attempted"] == 1


def test_candidate_priority_score_penalizes_global_nav_clusters():
  nav_a = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Pricing",
    href="/pricing",
    in_header=True,
    in_nav=True,
  )
  nav_b = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Blog",
    href="/blog",
    in_header=True,
    in_nav=True,
  )
  nav_c = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Customers",
    href="/customers",
    in_header=True,
    in_nav=True,
  )

  clustered_score = _candidate_priority_score(
    nav_a,
    page_url="https://example.com/home",
    start_url="https://example.com/home",
    in_scope=lambda _url: True,
    candidates=[nav_a, nav_b, nav_c],
  )
  isolated_score = _candidate_priority_score(
    nav_a,
    page_url="https://example.com/home",
    start_url="https://example.com/home",
    in_scope=lambda _url: True,
    candidates=[nav_a],
  )

  assert clustered_score < isolated_score


def test_candidate_priority_score_applies_diversity_penalty_after_same_group_attempt():
  nav_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Docs",
    href="/docs",
    in_header=True,
    in_nav=True,
  )

  fresh_score = _candidate_priority_score(
    nav_link,
    page_url="https://example.com/home",
    start_url="https://example.com/home",
    in_scope=lambda _url: True,
    candidates=[nav_link],
    attempted_group_counts={},
  )
  repeated_group_score = _candidate_priority_score(
    nav_link,
    page_url="https://example.com/home",
    start_url="https://example.com/home",
    in_scope=lambda _url: True,
    candidates=[nav_link],
    attempted_group_counts={"global_nav_link": 1},
  )

  assert repeated_group_score < fresh_score


def test_candidate_priority_score_prefers_seed_subtree_over_same_domain_drift():
  local_docs = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Testing",
    href="/docs/components/concepts/testing",
    in_main=True,
  )
  drift_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Showcase",
    href="/showcase",
    in_main=True,
  )

  local_score = _candidate_priority_score(
    local_docs,
    page_url="https://chakra-ui.com/docs/components/concepts/overview",
    start_url="https://chakra-ui.com/docs/components/concepts/overview",
    in_scope=lambda _url: True,
    candidates=[local_docs, drift_link],
  )
  drift_score = _candidate_priority_score(
    drift_link,
    page_url="https://chakra-ui.com/docs/components/concepts/overview",
    start_url="https://chakra-ui.com/docs/components/concepts/overview",
    in_scope=lambda _url: True,
    candidates=[local_docs, drift_link],
  )

  assert local_score > drift_score


def test_candidate_priority_score_prefers_structured_main_control_over_main_link():
  main_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="API reference",
    href="/docs/api",
    in_main=True,
  )
  summary_control = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="summary",
    text="More details",
    tag_name="summary",
    in_main=True,
  )

  control_score = _candidate_priority_score(
    summary_control,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[main_link, summary_control],
  )
  link_score = _candidate_priority_score(
    main_link,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[main_link, summary_control],
  )

  assert control_score > link_score


def test_candidate_priority_score_prefers_main_link_over_generic_main_button():
  main_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="API reference",
    href="/docs/api",
    in_main=True,
  )
  generic_button = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="Button",
    in_main=True,
  )

  link_score = _candidate_priority_score(
    main_link,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[main_link, generic_button],
  )
  button_score = _candidate_priority_score(
    generic_button,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[main_link, generic_button],
  )

  assert link_score > button_score


def test_candidate_priority_score_prefers_section_nav_link_over_header_search_control():
  section_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Get Started",
    href="/docs/get-started/installation",
    in_nav=True,
    in_header=True,
  )
  search_button = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="Search",
    in_header=True,
    aria_expanded="false",
  )

  section_score = _candidate_priority_score(
    section_link,
    page_url="https://chakra-ui.com/docs/components/concepts/overview",
    start_url="https://chakra-ui.com/docs/components/concepts/overview",
    in_scope=lambda _url: True,
    candidates=[section_link, search_button],
  )
  search_score = _candidate_priority_score(
    search_button,
    page_url="https://chakra-ui.com/docs/components/concepts/overview",
    start_url="https://chakra-ui.com/docs/components/concepts/overview",
    in_scope=lambda _url: True,
    candidates=[section_link, search_button],
  )

  assert section_score > search_score


def test_candidate_priority_score_does_not_treat_local_docs_nav_as_generic_global_nav():
  docs_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Docs",
    href="/docs/components/installation",
    in_nav=True,
    in_header=True,
  )

  local_section_score = _candidate_priority_score(
    docs_link,
    page_url="https://example.com/docs/components/concepts/overview",
    start_url="https://example.com/docs/components/concepts/overview",
    in_scope=lambda _url: True,
    candidates=[docs_link],
  )
  global_nav_score = _candidate_priority_score(
    docs_link,
    page_url="https://example.com/home",
    start_url="https://example.com/home",
    in_scope=lambda _url: True,
    candidates=[docs_link],
  )

  assert local_section_score > global_nav_score


def test_candidate_priority_score_penalizes_same_document_links_below_section_nav():
  same_document_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Components",
    href="/docs/components/concepts/overview",
    in_nav=True,
    in_header=True,
    aria_current="page",
  )
  section_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Charts",
    href="/docs/charts/installation",
    in_nav=True,
    in_header=True,
  )

  same_document_score = _candidate_priority_score(
    same_document_link,
    page_url="https://chakra-ui.com/docs/components/concepts/overview",
    start_url="https://chakra-ui.com/docs/components/concepts/overview",
    in_scope=lambda _url: True,
    candidates=[same_document_link, section_link],
  )
  section_score = _candidate_priority_score(
    section_link,
    page_url="https://chakra-ui.com/docs/components/concepts/overview",
    start_url="https://chakra-ui.com/docs/components/concepts/overview",
    in_scope=lambda _url: True,
    candidates=[same_document_link, section_link],
  )

  assert section_score > same_document_score


def test_candidate_priority_score_prefers_main_link_when_control_cluster_is_large():
  main_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="API reference",
    href="/docs/api",
    in_main=True,
  )
  tab_controls = [
    ActionCandidate(
      locator=object(),
      action_type="click",
      strategy_name="role_tab",
      text=f"Preview {idx}",
      role="tab",
      in_main=True,
    )
    for idx in range(4)
  ]

  link_score = _candidate_priority_score(
    main_link,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[main_link, *tab_controls],
  )
  control_score = _candidate_priority_score(
    tab_controls[0],
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[main_link, *tab_controls],
  )

  assert link_score > control_score


def test_candidate_priority_score_penalizes_repeated_same_page_control_strategy_when_links_exist():
  main_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="API reference",
    href="/docs/api",
    in_main=True,
  )
  summary_controls = [
    ActionCandidate(
      locator=object(),
      action_type="click",
      strategy_name="summary",
      text=f"Section {idx}",
      tag_name="summary",
    )
    for idx in range(4)
  ]

  link_score = _candidate_priority_score(
    main_link,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[main_link, *summary_controls],
    attempted_strategy_counts={"summary": 1},
  )
  summary_score = _candidate_priority_score(
    summary_controls[0],
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[main_link, *summary_controls],
    attempted_strategy_counts={"summary": 1},
  )

  assert link_score > summary_score


def test_candidate_priority_score_penalizes_clipboard_like_control_when_route_link_exists():
  route_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Get Started",
    href="/docs/get-started",
    in_nav=True,
    in_header=True,
  )
  copy_control = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="Copy Page",
    in_main=True,
  )

  route_score = _candidate_priority_score(
    route_link,
    page_url="https://example.com/docs/components/concepts/overview",
    start_url="https://example.com/docs/components/concepts/overview",
    in_scope=lambda _url: True,
    candidates=[route_link, copy_control],
  )
  copy_score = _candidate_priority_score(
    copy_control,
    page_url="https://example.com/docs/components/concepts/overview",
    start_url="https://example.com/docs/components/concepts/overview",
    in_scope=lambda _url: True,
    candidates=[route_link, copy_control],
  )

  assert route_score > copy_score


def test_candidate_priority_score_penalizes_utility_search_control_when_route_link_exists():
  route_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Changelog",
    href="/docs/changelog",
    in_main=True,
  )
  search_control = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="Search",
    in_header=True,
    aria_expanded="false",
  )

  route_score = _candidate_priority_score(
    route_link,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[route_link, search_control],
  )
  search_score = _candidate_priority_score(
    search_control,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[route_link, search_control],
  )

  assert route_score > search_score


def test_candidate_priority_score_prefers_route_link_over_non_main_generic_expander():
  route_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="TanStack",
    href="/",
  )
  generic_expander = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="React",
    aria_expanded="false",
  )

  route_score = _candidate_priority_score(
    route_link,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[route_link, generic_expander],
  )
  expander_score = _candidate_priority_score(
    generic_expander,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    candidates=[route_link, generic_expander],
  )

  assert route_score > expander_score


def test_candidate_priority_score_boosts_unseen_route_over_revisited_route():
  unseen_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Advanced Guides",
    href="/docs/advanced",
    in_main=True,
  )
  revisited_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Overview",
    href="/docs/overview",
    in_main=True,
  )

  unseen_score = _candidate_priority_score(
    unseen_link,
    page_url="https://example.com/docs/get-started",
    start_url="https://example.com/docs/get-started",
    in_scope=lambda _url: True,
    current_route="/docs/get-started",
    candidates=[unseen_link, revisited_link],
    route_visit_counts={
      "/docs/get-started": 4,
      "/docs/overview": 5,
    },
  )
  revisited_score = _candidate_priority_score(
    revisited_link,
    page_url="https://example.com/docs/get-started",
    start_url="https://example.com/docs/get-started",
    in_scope=lambda _url: True,
    current_route="/docs/get-started",
    candidates=[unseen_link, revisited_link],
    route_visit_counts={
      "/docs/get-started": 4,
      "/docs/overview": 5,
    },
  )

  assert unseen_score > revisited_score


def test_candidate_priority_score_penalizes_global_nav_detour_on_repeated_docs_route():
  home_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Home",
    href="/",
    in_header=True,
    in_nav=True,
  )
  docs_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Getting Started",
    href="/docs/get-started",
    in_header=True,
    in_nav=True,
  )

  detour_score = _candidate_priority_score(
    home_link,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    current_route="/docs/overview",
    candidates=[home_link, docs_link],
    route_visit_counts={
      "/docs/overview": 4,
      "/": 5,
    },
    route_pair_counts={
      ("/docs/overview", "/"): 2,
    },
  )
  docs_score = _candidate_priority_score(
    docs_link,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    current_route="/docs/overview",
    candidates=[home_link, docs_link],
    route_visit_counts={
      "/docs/overview": 4,
      "/": 5,
    },
    route_pair_counts={
      ("/docs/overview", "/"): 2,
    },
  )

  assert docs_score > detour_score


def test_candidate_priority_score_penalizes_non_main_control_on_overexplored_route():
  expander = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="React",
    aria_expanded="false",
  )

  fresh_score = _candidate_priority_score(
    expander,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    current_route="/docs/overview",
    candidates=[expander],
    route_visit_counts={"/docs/overview": 1},
  )
  overexplored_score = _candidate_priority_score(
    expander,
    page_url="https://example.com/docs/overview",
    start_url="https://example.com/docs/overview",
    in_scope=lambda _url: True,
    current_route="/docs/overview",
    candidates=[expander],
    route_visit_counts={"/docs/overview": 5},
  )

  assert overexplored_score < fresh_score


def test_prioritize_action_candidates_prefers_local_path_family_over_store_drift(monkeypatch, tmp_path):
  page = FakePage(url="https://mui.com/material-ui/getting-started/overview/")
  executed: list[str] = []

  local_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Button",
    href="/material-ui/react-button/",
    in_main=True,
  )
  store_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Buy it now",
    href="/store/templates/",
    in_main=True,
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/material-ui/getting-started/overview/",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 5
    return [store_link, local_link]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
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
      start_url="https://mui.com/material-ui/getting-started/overview/",
      run_dir=tmp_path,
      cfg=CrawlConfig(
        max_depth=1,
        max_actions_per_state=1,
        prioritize_action_candidates=True,
      ),
    )
  )

  assert executed == ["Button"]
  assert graph.metrics["coverage"]["actions_attempted"] == 1


def test_prioritize_action_candidates_prefers_main_tab_control_over_main_link(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/components/tabs")
  executed: list[str] = []

  docs_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="API reference",
    href="/components/tabs/api",
    in_main=True,
  )
  preview_tab = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="role_tab",
    text="Preview",
    role="tab",
    in_main=True,
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/components/tabs",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 5
    return [docs_link, preview_tab]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
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
      start_url="https://example.com/components/tabs",
      run_dir=tmp_path,
      cfg=CrawlConfig(
        max_depth=1,
        max_actions_per_state=1,
        prioritize_action_candidates=True,
      ),
    )
  )

  assert executed == ["Preview"]
  assert graph.metrics["coverage"]["actions_attempted"] == 1


def test_prioritize_action_candidates_reserves_best_route_link_on_control_cluster(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/components/tabs")
  executed: list[str] = []

  docs_link = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="API reference",
    href="/components/tabs/api",
    in_main=True,
  )
  tab_controls = [
    ActionCandidate(
      locator=object(),
      action_type="click",
      strategy_name="role_tab",
      text=f"Preview {idx}",
      role="tab",
      in_main=True,
    )
    for idx in range(4)
  ]

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route="/components/tabs",
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 5
    return [*tab_controls, docs_link]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    executed.append(candidate.text)
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
      start_url="https://example.com/components/tabs",
      run_dir=tmp_path,
      cfg=CrawlConfig(
        max_depth=1,
        max_actions_per_state=1,
        prioritize_action_candidates=True,
      ),
    )
  )

  assert executed == ["API reference"]
  assert graph.metrics["coverage"]["actions_attempted"] == 1


def test_prioritize_action_candidates_records_selection_diagnostics(monkeypatch, tmp_path):
  page = FakePage(url="https://example.com/home")

  header_nav = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="links",
    text="Pricing",
    href="/pricing",
    in_header=True,
    in_nav=True,
  )
  demo_button = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="Open demo",
    in_main=True,
    ancestor_tags=("section", "main"),
  )

  async def fake_capture_state_artifacts(page_obj, _run_dir, state_id, **_kwargs):
    state_hash = html_hash(await page_obj.content())
    route = "/demo" if page_obj.url.endswith("/demo") else "/home"
    return SimpleNamespace(
      url=page_obj.url,
      html_hash=state_hash,
      dom_identity_hash=state_hash,
      title=state_id,
      route=route,
    )

  async def fake_get_action_candidates(_page_obj, limit):
    assert limit == 5
    return [header_nav, demo_button]

  async def fake_perform_action(candidate, *, wait_timeout_ms=2000):
    if candidate.text == "Open demo":
      page.url = "https://example.com/demo"
      return True
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
      cfg=CrawlConfig(
        max_depth=1,
        max_actions_per_state=1,
        prioritize_action_candidates=True,
      ),
    )
  )

  action = graph.edges[0]["action"]
  selection = graph.metrics["coverage"]["action_selection"]

  assert action["text"] == "Open demo"
  assert action["candidate_region"] == "main"
  assert action["selection_group"] == "main_control"
  assert "main_content" in action["priority_reason_flags"]
  assert "button_strategy" in action["priority_reason_flags"]
  assert "demo_control" in action["priority_reason_flags"]

  assert selection["by_strategy"]["buttons"] == 1
  assert selection["by_group"]["main_control"] == 1
  assert selection["by_region"]["main"] == 1
  assert selection["by_reason"]["main_content"] >= 1
  assert selection["by_reason"]["button_strategy"] >= 1
