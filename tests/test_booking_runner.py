from __future__ import annotations

import asyncio

import pytest

from scripts.benchmarks.booking import runner as booking_runner
from scripts.benchmarks.booking.runner import (
  BOOKING_CLEAN_PROFILE,
  BOOKING_PROFILE_GLOBAL,
  BookingRunnerError,
  open_booking_run,
)
from scripts.benchmarks.booking.spa_process import open_booking_spa


@pytest.fixture(scope="module")
def booking_spa():
  with open_booking_spa() as server:
    yield server


@pytest.fixture(scope="module")
def booking_browser():
  playwright = pytest.importorskip("playwright.async_api")
  loop = asyncio.new_event_loop()
  manager = None
  browser = None
  try:
    manager = loop.run_until_complete(playwright.async_playwright().start())
    browser = loop.run_until_complete(manager.chromium.launch(headless=True))
  except Exception as exc:
    if manager is not None:
      loop.run_until_complete(manager.stop())
    loop.close()
    pytest.skip(f"Playwright Chromium is unavailable: {exc}")

  try:
    yield loop, browser
  finally:
    loop.run_until_complete(browser.close())
    loop.run_until_complete(manager.stop())
    loop.close()


def run_async(booking_browser, coroutine):
  loop, _ = booking_browser
  return loop.run_until_complete(coroutine)


@pytest.mark.parametrize(
  ("target_state", "route", "heading", "marker", "marker_text"),
  [
    ("services", "/services", "Select service", "route-services", None),
    (
      "schedule",
      "/schedule",
      "Schedule appointment",
      "summary-service",
      "Consultation",
    ),
    (
      "details",
      "/details",
      "Booking details",
      "summary-slot",
      "09:00",
    ),
    (
      "review",
      "/review",
      "Review appointment",
      "review-customer-full-name",
      "Jordan Lee",
    ),
    (
      "confirmation",
      "/confirmation",
      "Booking confirmed",
      "confirmation-reference",
      "BKG-20260616-0900-CONSULTATION",
    ),
    (
      "help",
      "/help",
      "Help & policies",
      "help-provider-name",
      "Harbor Point Clinic",
    ),
  ],
)
def test_runner_reaches_each_supported_functional_state(
  booking_spa,
  booking_browser,
  target_state,
  route,
  heading,
  marker,
  marker_text,
):
  async def verify():
    _, browser = booking_browser
    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile=BOOKING_CLEAN_PROFILE,
      target_state=target_state,
    ) as run:
      assert run.requested_state == target_state
      assert run.reached_route == route
      assert run.profile == BOOKING_CLEAN_PROFILE
      assert await run.page.get_by_role(
        "heading",
        name=heading,
        level=1,
        exact=True,
      ).is_visible()
      locator = run.page.locator(f'[data-testid="{marker}"]')
      assert await locator.is_visible()
      if marker_text is not None:
        assert (await locator.inner_text()).strip() == marker_text

  run_async(booking_browser, verify())


def test_profile_is_injected_before_startup_and_persists_across_navigation_and_reload(
  booking_spa,
  booking_browser,
):
  async def verify():
    _, browser = booking_browser

    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile=None,
      target_state="services",
    ) as run:
      assert await run.page.evaluate(
        f"Object.hasOwn(window, {BOOKING_PROFILE_GLOBAL!r})"
      )
      assert await run.page.evaluate(BOOKING_PROFILE_GLOBAL) is None

    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile=BOOKING_CLEAN_PROFILE,
      target_state="schedule",
    ) as run:
      assert await run.page.evaluate(BOOKING_PROFILE_GLOBAL) == BOOKING_CLEAN_PROFILE
      await run.page.reload(wait_until="domcontentloaded")
      await run.page.locator('[data-testid="booking-scheduler-app"]').wait_for()
      assert await run.page.evaluate(BOOKING_PROFILE_GLOBAL) == BOOKING_CLEAN_PROFILE
      assert run.page.url.endswith("/services")

  run_async(booking_browser, verify())


def test_unknown_profile_failure_does_not_poison_later_run(
  booking_spa,
  booking_browser,
):
  async def verify():
    _, browser = booking_browser
    with pytest.raises(BookingRunnerError) as error:
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile="booking-does-not-exist",
        target_state="services",
      ):
        pass

    message = str(error.value)
    assert "app=Booking" in message
    assert "booking-does-not-exist" in message
    assert "requested_state='services'" in message
    assert "Unknown Booking benchmark profile" in message

    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile=BOOKING_CLEAN_PROFILE,
      target_state="services",
    ) as run:
      assert run.reached_route == "/services"

  run_async(booking_browser, verify())


def test_confirmation_is_terminal_only_within_its_fresh_context(
  booking_spa,
  booking_browser,
):
  async def verify():
    _, browser = booking_browser
    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile=BOOKING_CLEAN_PROFILE,
      target_state="confirmation",
    ) as run:
      await run.page.evaluate(
        """() => {
          window.history.pushState({}, "", "/review");
          window.dispatchEvent(new PopStateEvent("popstate"));
        }"""
      )
      await run.page.wait_for_url("**/confirmation")
      assert await run.page.locator(
        '[data-testid="confirmation-reference"]'
      ).inner_text() == "BKG-20260616-0900-CONSULTATION"

    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile=BOOKING_CLEAN_PROFILE,
      target_state="services",
    ) as run:
      assert run.reached_route == "/services"
      assert await run.page.locator('input[name="service"]:checked').count() == 0
      assert await run.page.locator(
        '[data-testid="confirmation-reference"]'
      ).count() == 0
      assert await run.page.locator('[data-testid="details-full-name"]').count() == 0

  run_async(booking_browser, verify())


def test_unsupported_target_fails_before_browser_context_creation():
  class BrowserThatMustNotBeUsed:
    async def new_context(self, **kwargs):
      raise AssertionError("Unsupported state should fail before context creation")

  async def verify():
    with pytest.raises(BookingRunnerError, match="Unsupported functional state"):
      async with open_booking_run(
        BrowserThatMustNotBeUsed(),
        base_url="http://127.0.0.1:4173",
        profile=BOOKING_CLEAN_PROFILE,
        target_state="details-validation-error",
      ):
        pass

  asyncio.run(verify())


class FakeRunnerPage:
  url = "http://127.0.0.1:4173/services"

  def set_default_timeout(self, timeout):
    pass

  def set_default_navigation_timeout(self, timeout):
    pass

  def on(self, event, callback):
    pass

  async def evaluate(self, expression):
    return BOOKING_CLEAN_PROFILE


class FailingCloseContext:
  def __init__(self):
    self.page = FakeRunnerPage()

  async def add_init_script(self, **kwargs):
    pass

  async def new_page(self):
    return self.page

  async def close(self):
    raise RuntimeError("context close failed")


class FakeRunnerBrowser:
  def __init__(self):
    self.context = FailingCloseContext()

  async def new_context(self, **kwargs):
    return self.context


def test_runner_preserves_setup_error_when_context_cleanup_fails(monkeypatch):
  async def fail_setup(page, base_url):
    raise ValueError("state setup failed")

  monkeypatch.setitem(booking_runner.STATE_SETUP, "services", fail_setup)

  async def verify():
    with pytest.raises(BookingRunnerError) as error:
      async with open_booking_run(
        FakeRunnerBrowser(),
        base_url="http://127.0.0.1:4173",
        profile=BOOKING_CLEAN_PROFILE,
        target_state="services",
      ):
        pass

    assert "state setup failed" in str(error.value)
    assert any(
      "browser-context cleanup also failed: context close failed" in note
      for note in getattr(error.value, "__notes__", [])
    )

  asyncio.run(verify())


@pytest.mark.parametrize("setup_fails", [False, True])
def test_state_setup_surfaces_page_error_before_or_during_failure(
  monkeypatch,
  setup_fails,
):
  async def setup(page, base_url):
    if setup_fails:
      raise ValueError("interaction failed")

  monkeypatch.setitem(booking_runner.STATE_SETUP, "services", setup)
  page_errors = ["Booking page crashed"]
  page_error_event = asyncio.Event()
  page_error_event.set()

  async def verify():
    with pytest.raises(RuntimeError, match="Booking page crashed"):
      await booking_runner._run_state_setup(
        FakeRunnerPage(),
        "http://127.0.0.1:4173",
        "services",
        page_errors,
        page_error_event,
      )

  asyncio.run(verify())


def test_runner_surfaces_context_cleanup_only_failure(monkeypatch):
  async def successful_setup(page, base_url):
    pass

  monkeypatch.setitem(booking_runner.STATE_SETUP, "services", successful_setup)

  async def verify():
    with pytest.raises(RuntimeError, match="context close failed"):
      async with open_booking_run(
        FakeRunnerBrowser(),
        base_url="http://127.0.0.1:4173",
        profile=BOOKING_CLEAN_PROFILE,
        target_state="services",
      ):
        pass

  asyncio.run(verify())
