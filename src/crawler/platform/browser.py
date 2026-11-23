from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from playwright.async_api import Browser, BrowserContext, Page
else:
  Browser = BrowserContext = Page = Any

try:
  from playwright.async_api import TimeoutError as PlaywrightTimeoutError
  from playwright.async_api import async_playwright
except ImportError:
  PlaywrightTimeoutError = TimeoutError
  async_playwright = None

from ..exceptions import NavigationTimeout
from .readiness import wait_for_page_ready

DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
IGNORE_HTTPS_ERRORS = True
NAVIGATION_TIMEOUT_MS = 60_000
READINESS_TIMEOUT_MS = 5_000


async def _close_best_effort(obj: Any) -> None:
  if obj is None:
    return
  try:
    await obj.close()
  except Exception:
    return


class BrowserController:
  def __init__(self, headless: bool = True):
    self.headless = headless
    self._pw = None
    self.browser: Browser | None = None
    self.context: BrowserContext | None = None
    self.page: Page | None = None

  async def start(self) -> None:
    if async_playwright is None:
      raise RuntimeError(
        "Playwright is required for browser crawling. Install requirements and run `playwright install chromium`."
      )
    self._pw = await async_playwright().start()
    self.browser = await self._pw.chromium.launch(headless=self.headless)
    self.context = await self.browser.new_context(
      viewport=DEFAULT_VIEWPORT,
      ignore_https_errors=IGNORE_HTTPS_ERRORS,
    )
    self.page = await self.context.new_page()

  async def stop(self) -> None:
    try:
      await _close_best_effort(self.context)
    finally:
      try:
        await _close_best_effort(self.browser)
      finally:
        if self._pw is not None:
          await self._pw.stop()

  async def goto(self, url: str) -> None:
    if self.page is None:
      raise RuntimeError("BrowserController.start() must be called before goto()")
    try:
      await self.page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT_MS,
      )
      await wait_for_page_ready(self.page, timeout_ms=READINESS_TIMEOUT_MS)
    except PlaywrightTimeoutError as error:
      if "Timeout" in str(error):
        raise NavigationTimeout(f"Timeout while navigating to {url}") from error
      raise
