from __future__ import annotations

import asyncio

from src.crawler.crawl.actions.selection import ActionSelectionPlanner
from src.crawler.crawl.actions import ActionCandidate
from src.crawler.crawl.crawl_config import CrawlConfig
from src.crawler.crawl.metrics.recorder import CrawlMetricsRecorder
from src.crawler.crawl.priority import _action_meta
from src.crawler.graph.graph import StateGraph


class FakePage:
  def __init__(self, url: str = "https://example.test/") -> None:
    self.url = url


class FakeStateRecorder:
  def __init__(self) -> None:
    self.recorded_attempts: list[tuple[str, tuple[str, ...]]] = []

  def record_attempted_action(self, state_id: str, action_key: tuple[str, ...]) -> None:
    self.recorded_attempts.append((state_id, action_key))


def _planner(
  *,
  candidates: list[ActionCandidate] | None = None,
  cfg: CrawlConfig | None = None,
) -> tuple[ActionSelectionPlanner, CrawlMetricsRecorder, FakeStateRecorder, list[int]]:
  page = FakePage()
  graph = StateGraph()
  metrics = CrawlMetricsRecorder(cfg or CrawlConfig(max_actions_per_state=2))
  state_recorder = FakeStateRecorder()
  seen_limits: list[int] = []

  async def fake_get_action_candidates(_page: FakePage, *, limit: int) -> list[ActionCandidate]:
    seen_limits.append(limit)
    return list(candidates or [])

  return (
    ActionSelectionPlanner(
      page=page,
      start_url=page.url,
      cfg=cfg or CrawlConfig(max_actions_per_state=2),
      graph_getter=lambda: graph,
      in_scope=lambda _url: True,
      metrics_recorder=metrics,
      state_recorder=state_recorder,  # type: ignore[arg-type]
      get_action_candidates_fn=fake_get_action_candidates,
    ),
    metrics,
    state_recorder,
    seen_limits,
  )


def test_action_selection_fetches_candidates_with_scan_metrics() -> None:
  candidates = [
    ActionCandidate(locator=object(), action_type="click", strategy_name="buttons", text="Open"),
    ActionCandidate(locator=object(), action_type="click", strategy_name="links", text="Docs", href="/docs"),
  ]
  planner, metrics, _state_recorder, seen_limits = _planner(candidates=candidates)

  result = asyncio.run(planner.get_candidates())

  assert result == candidates
  assert seen_limits == [2]
  assert metrics.metrics["coverage"]["candidate_scans"] == 1
  assert metrics.metrics["coverage"]["candidates_seen_total"] == 2


def test_action_selection_counts_previously_attempted_candidates_once() -> None:
  candidates = [
    ActionCandidate(locator=object(), action_type="click", strategy_name="buttons", identity="open", text="Open"),
    ActionCandidate(locator=object(), action_type="click", strategy_name="buttons", identity="close", text="Close"),
  ]
  planner, metrics, _state_recorder, _seen_limits = _planner(candidates=candidates)
  persisted = {("identity", "open")}
  counted: set[tuple[str, ...]] = set()

  planner.record_previously_attempted_candidates(candidates, persisted, counted)
  planner.record_previously_attempted_candidates(candidates, persisted, counted)

  assert metrics.metrics["coverage"]["actions_skipped_previously_attempted"] == 1
  assert counted == {("identity", "open")}


def test_action_selection_records_action_attempt_and_diagnostics() -> None:
  candidate = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    identity="save",
    text="Save",
    in_main=True,
  )
  planner, metrics, state_recorder, _seen_limits = _planner(candidates=[candidate])
  attempted: set[tuple[str, ...]] = set()

  selected = planner.select_candidate_for_state(
    candidates=[candidate],
    attempted_action_keys=attempted,
    selection_policy=None,
  )
  assert selected is not None
  _selected_index, selected_candidate, selected_key, priority_evaluation = selected

  planner.record_action_attempt(
    current_state_id="state_0000",
    selected_candidate=selected_candidate,
    selected_key=selected_key,
    attempted_action_keys=attempted,
    attempted_group_counts={},
    attempted_strategy_counts={},
    priority_evaluation=priority_evaluation,
    priority_reason_flags=(),
  )

  assert attempted == {("identity", "save")}
  assert state_recorder.recorded_attempts == [("state_0000", ("identity", "save"))]
  coverage = metrics.metrics["coverage"]
  assert coverage["actions_attempted"] == 1
  assert coverage["action_selection"]["by_strategy"]["buttons"] == 1
  assert coverage["action_selection"]["by_region"]["main"] == 1


def test_action_meta_preserves_stable_trigger_identity() -> None:
  candidate = ActionCandidate(
    locator=object(),
    action_type="click",
    strategy_name="buttons",
    text="Save",
    tag_name="button",
    button_type="button",
    aria_label="Save booking",
    data_testid="save-booking",
    dom_path='div#root>main>button[data-testid="save-booking"]',
    selector="button:nth-of-type(1)",
  )

  meta = _action_meta(candidate, index=2)

  assert meta["data_testid"] == "save-booking"
  assert meta["dom_path"] == 'div#root>main>button[data-testid="save-booking"]'
  assert meta["tag_name"] == "button"
  assert meta["button_type"] == "button"
  assert meta["accessible_name"] == "Save booking"


def test_action_meta_preserves_radio_trigger_identity() -> None:
  candidate = ActionCandidate(
    locator=object(),
    action_type="radio",
    strategy_name="radios",
    identity="input|plan-a|radio||radio|plan|audit|main>fieldset>input:nth-of-type(2)",
    text="select radio: Accessibility audit",
    tag_name="input",
    input_type="radio",
    data_testid="plan-audit",
    dom_path='main>fieldset>input[data-testid="plan-audit"]',
    selector="input#audit",
    in_main=True,
  )

  meta = _action_meta(candidate, index=3)

  assert meta["type"] == "radio"
  assert meta["strategy"] == "radios"
  assert meta["text"] == "select radio: Accessibility audit"
  assert meta["input_type"] == "radio"
  assert meta["data_testid"] == "plan-audit"
  assert meta["dom_path"] == 'main>fieldset>input[data-testid="plan-audit"]'
  assert meta["tag_name"] == "input"
