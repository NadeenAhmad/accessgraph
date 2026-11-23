import asyncio

from src.crawler.platform.readiness import wait_after_action, wait_for_page_ready


class FakePage:
  def __init__(self, *, snapshot: dict[str, object] | None = None, fail: bool = False) -> None:
    self.snapshot = snapshot or {
      "ready_state": "complete",
      "url": "https://example.test/",
      "element_count": 4,
      "text_length": 42,
    }
    self.fail = fail
    self.calls: list[str] = []
    self.evaluate_calls = 0
    self.waits: list[int] = []

  async def wait_for_load_state(self, state: str, timeout: int) -> None:
    self.calls.append(f"load:{state}:{timeout}")
    if self.fail:
      raise RuntimeError("load failed")

  async def wait_for_timeout(self, ms: int) -> None:
    self.calls.append(f"timeout:{ms}")
    self.waits.append(ms)
    if self.fail:
      raise RuntimeError("timeout failed")

  async def evaluate(self, script: str, *_args):
    self.evaluate_calls += 1
    if "MutationObserver" in script:
      self.calls.append("evaluate:mutation")
      if self.fail:
        raise RuntimeError("mutation failed")
      return "timeout"

    self.calls.append("evaluate:settle")
    if self.fail:
      raise RuntimeError("settle failed")
    return dict(self.snapshot)


def test_wait_for_page_ready_requires_two_stable_repeats_by_default() -> None:
  page = FakePage()

  asyncio.run(wait_for_page_ready(page, timeout_ms=1_000, poll_interval_ms=10))

  assert page.calls[:2] == ["load:domcontentloaded:1000", "load:networkidle:1000"]
  assert page.evaluate_calls == 3
  assert page.waits == [10, 10]


def test_wait_after_action_waits_for_mutation_before_page_settle() -> None:
  page = FakePage()

  asyncio.run(
    wait_after_action(
      page,
      mutation_timeout_ms=250,
      settle_timeout_ms=1_000,
      network_idle_timeout_ms=400,
      poll_interval_ms=10,
    )
  )

  assert page.calls[0] == "evaluate:mutation"
  assert page.calls[1:3] == ["load:domcontentloaded:1000", "load:networkidle:400"]
  assert page.calls.count("evaluate:settle") == 3


def test_wait_after_action_failures_are_non_fatal() -> None:
  page = FakePage(fail=True)

  asyncio.run(wait_after_action(page))

  assert "evaluate:mutation" in page.calls
  assert any(call.startswith("load:domcontentloaded") for call in page.calls)
