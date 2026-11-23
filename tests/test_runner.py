import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock

from src.crawler.crawl.actions import ActionCandidate
from src.crawler.crawl.actions.execution import check_locator, perform_action, radio_locator, select_locator, type_locator


@dataclass
class FakePage:
  waited: list[int]
  load_states: list[str]
  evaluate_calls: int = 0

  async def wait_for_timeout(self, ms: int) -> None:
    self.waited.append(ms)

  async def wait_for_load_state(self, state: str, timeout: int) -> None:
    self.load_states.append(state)

  async def evaluate(self, _script: str, *_args):
    self.evaluate_calls += 1
    if "MutationObserver" in _script:
      return "timeout"
    return {
      "ready_state": "complete",
      "url": "https://example.com/",
      "element_count": 5,
      "text_length": 123,
    }


class FakeRunnerLocator:
  def __init__(
    self,
    *,
    visible: bool = True,
    enabled: bool = True,
    checked: bool = False,
    options: list[str] | None = None,
    current_value: str = "",
  ):
    self._visible = visible
    self._enabled = enabled
    self._checked = checked
    self._options = options or []
    self._current_value = current_value
    self.filled_with: str | None = None
    self.selected_value: str | None = None
    self.check_called = False
    self.click_called = False
    self.page = FakePage(waited=[], load_states=[])

  async def is_visible(self) -> bool:
    return self._visible

  async def is_enabled(self) -> bool:
    return self._enabled

  async def is_checked(self) -> bool:
    return self._checked

  async def fill(self, value: str, timeout: int) -> None:
    self.filled_with = value

  async def evaluate(self, script: str):
    if "el.options" in script:
      return {"current": self._current_value, "values": self._options}
    if "is_radio_input" in script:
      return {"is_radio_input": True, "checked": self._checked}
    raise AssertionError(f"Unexpected evaluate script: {script}")

  async def select_option(self, value: str, timeout: int) -> None:
    self.selected_value = value

  async def check(self, timeout: int) -> None:
    self.check_called = True

  async def click(self, timeout: int) -> None:
    self.click_called = True


def test_type_locator_fills_and_waits():
  loc = FakeRunnerLocator()
  ok = asyncio.run(type_locator(loc, value="hello"))

  assert ok is True
  assert loc.filled_with == "hello"
  assert loc.page.load_states == ["domcontentloaded", "networkidle"]
  assert loc.page.evaluate_calls >= 1


def test_select_locator_chooses_non_current_option():
  loc = FakeRunnerLocator(options=["first", "second"], current_value="first")
  ok = asyncio.run(select_locator(loc))

  assert ok is True
  assert loc.selected_value == "second"
  assert loc.page.load_states == ["domcontentloaded", "networkidle"]
  assert loc.page.evaluate_calls >= 1


def test_check_locator_checks_when_unchecked():
  loc = FakeRunnerLocator(checked=False)
  ok = asyncio.run(check_locator(loc))

  assert ok is True
  assert loc.check_called is True
  assert loc.page.load_states == ["domcontentloaded", "networkidle"]
  assert loc.page.evaluate_calls >= 1


def test_check_locator_skips_when_already_checked():
  loc = FakeRunnerLocator(checked=True)
  ok = asyncio.run(check_locator(loc))

  assert ok is False
  assert loc.check_called is False
  assert loc.page.waited == []
  assert loc.page.load_states == []


def test_radio_locator_checks_unselected_radio():
  loc = FakeRunnerLocator(checked=False)
  ok = asyncio.run(radio_locator(loc))

  assert ok is True
  assert loc.check_called is True
  assert loc.click_called is False
  assert loc.page.load_states == ["domcontentloaded", "networkidle"]


def test_radio_locator_skips_already_checked_radio():
  loc = FakeRunnerLocator(checked=True)
  ok = asyncio.run(radio_locator(loc))

  assert ok is False
  assert loc.check_called is False
  assert loc.click_called is False
  assert loc.page.waited == []
  assert loc.page.load_states == []


def test_perform_action_dispatches_to_click(monkeypatch):
  from src.crawler.crawl.actions import execution as runner

  click_mock = AsyncMock(return_value=True)
  monkeypatch.setattr(runner, "click_locator", click_mock)

  loc = FakeRunnerLocator()
  cand = ActionCandidate(locator=loc, action_type="click", strategy_name="links")
  result = asyncio.run(perform_action(cand))

  assert result is True
  click_mock.assert_awaited_once()
