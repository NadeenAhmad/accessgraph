from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from playwright.async_api import Page, async_playwright

from scripts.benchmarks.case_metadata import BenchmarkCase, CaseConfigurationError
from scripts.benchmarks.booking.runner import open_booking_run
from scripts.benchmarks.booking.spa_process import open_booking_spa
from scripts.benchmarks.checkout.spa_process import (
  CONTROLLED_SUPPORT_ORIGIN,
  CONTROLLED_SUPPORT_RETURNS_URL,
  build_checkout_app,
  find_free_port,
  requires_controlled_support_destination,
  start_controlled_support_server,
  start_vite_preview,
  stop_process,
  wait_for_url,
)


CHECKOUT_APP = "checkout"
BOOKING_APP = "booking-scheduler"
SUPPORTED_EXPLORER_APPS = frozenset({CHECKOUT_APP, BOOKING_APP})
CHECKOUT_INITIAL_ROUTE = "/products"
CHECKOUT_PROFILE_GLOBAL = "__ACCESSGRAPH_CHECKOUT_PROFILE__"
CHECKOUT_SUPPORT_ORIGIN_GLOBAL = "__ACCESSGRAPH_CHECKOUT_SUPPORT_ORIGIN__"
VIEWPORT = {"width": 1280, "height": 720}
BOOKING_ROUTE_TO_STATE = {
  "/services": "services",
  "/schedule": "schedule",
  "/details": "details",
  "/review": "review",
  "/confirmation": "confirmation",
  "/help": "help",
}

SessionLogger = Callable[[str], None]
VariantRunner = Callable[
  [
    BenchmarkCase,
    bool,
    threading.Event,
    Callable[["SessionStatus"], None],
    SessionLogger,
  ],
  Awaitable[None],
]


class SessionError(Exception):
  """Base error for expected Explorer session failures."""


class CaseNotLaunchableError(SessionError):
  pass


class UnsupportedAppError(SessionError):
  pass


class LaunchError(SessionError):
  pass


@dataclass(frozen=True)
class SessionStatus:
  state: str
  case_id: str | None = None
  profile: str | None = None
  url: str | None = None
  support_url: str | None = None
  message: str | None = None

  def to_dict(self) -> dict[str, str | None]:
    data: dict[str, str | None] = {"state": self.state}
    for key in ("case_id", "profile", "url", "support_url", "message"):
      value = getattr(self, key)
      if value is not None:
        data[key] = value
    return data


@dataclass
class _ActiveSession:
  case_id: str
  profile: str
  stop_event: threading.Event
  ready_event: threading.Event
  done_event: threading.Event
  thread: threading.Thread
  error: BaseException | None = None


class BenchmarkExplorerSession:
  def __init__(
    self,
    *,
    skip_build: bool = False,
    logger: SessionLogger | None = None,
    variant_runner: VariantRunner | None = None,
    variant_runners: Mapping[str, VariantRunner] | None = None,
  ) -> None:
    if variant_runner is not None and variant_runners is not None:
      raise ValueError("Use variant_runner or variant_runners, not both.")
    self._skip_build = skip_build
    self._logger = logger or (lambda message: None)
    if variant_runner is not None:
      self._variant_runners = {
        app: variant_runner for app in SUPPORTED_EXPLORER_APPS
      }
    else:
      self._variant_runners = dict(
        variant_runners or {
          CHECKOUT_APP: run_checkout_variant,
          BOOKING_APP: run_booking_variant,
        }
      )
    self._lock = threading.RLock()
    self._status = SessionStatus(state="idle")
    self._active: _ActiveSession | None = None

  def status(self) -> SessionStatus:
    with self._lock:
      return self._status

  def open_case(self, benchmark_case: BenchmarkCase) -> SessionStatus:
    if not benchmark_case.is_launchable:
      raise CaseNotLaunchableError(
        f"Case {benchmark_case.case_id} is not launchable."
      )
    variant_runner = self._variant_runners.get(benchmark_case.app)
    if variant_runner is None:
      raise UnsupportedAppError(
        f"Explorer launcher is not available for app {benchmark_case.app!r} yet."
      )
    profile = benchmark_case.executable_profile
    if profile is None:
      raise CaseConfigurationError(
        f"Case {benchmark_case.case_id} has no executable benchmark profile."
      )

    self.stop()

    stop_event = threading.Event()
    ready_event = threading.Event()
    done_event = threading.Event()
    active = _ActiveSession(
      case_id=benchmark_case.case_id,
      profile=profile,
      stop_event=stop_event,
      ready_event=ready_event,
      done_event=done_event,
      thread=threading.Thread(),
    )

    def on_ready(status: SessionStatus) -> None:
      with self._lock:
        if self._active is active:
          self._status = status
      ready_event.set()

    def worker() -> None:
      try:
        asyncio.run(
          variant_runner(
            benchmark_case,
            self._skip_build,
            stop_event,
            on_ready,
            self._logger,
          )
        )
        with self._lock:
          if self._active is active and self._status.state != "error":
            self._status = SessionStatus(state="idle")
      except BaseException as exc:
        active.error = exc
        message = str(exc) or exc.__class__.__name__
        self._logger(f"Benchmark SPA Explorer launch failed: {message}")
        with self._lock:
          if self._active is active:
            self._status = SessionStatus(
              state="error",
              case_id=benchmark_case.case_id,
              profile=profile,
              message=message,
            )
        ready_event.set()
      finally:
        done_event.set()

    thread = threading.Thread(
      target=worker,
      name=f"benchmark-explorer-{benchmark_case.case_id}",
      daemon=True,
    )
    active.thread = thread
    with self._lock:
      self._active = active
      self._status = SessionStatus(
        state="starting",
        case_id=benchmark_case.case_id,
        profile=profile,
      )
    thread.start()

    if not ready_event.wait(timeout=180):
      self.stop()
      raise LaunchError(f"Timed out starting case {benchmark_case.case_id}.")
    if active.error is not None:
      raise LaunchError(str(active.error) or active.error.__class__.__name__)
    return self.status()

  def stop(self) -> SessionStatus:
    with self._lock:
      active = self._active
    if active is None:
      with self._lock:
        self._status = SessionStatus(state="idle")
      return self.status()

    active.stop_event.set()
    active.done_event.wait(timeout=30)
    if active.thread.is_alive():
      message = f"Timed out stopping case {active.case_id}."
      self._logger(message)
      with self._lock:
        self._status = SessionStatus(
          state="error",
          case_id=active.case_id,
          profile=active.profile,
          message=message,
        )
      raise LaunchError(message)

    with self._lock:
      if self._active is active:
        self._active = None
      self._status = SessionStatus(state="idle")
    return self.status()

  def shutdown(self) -> SessionStatus:
    return self.stop()


async def run_checkout_variant(
  benchmark_case: BenchmarkCase,
  skip_build: bool,
  stop_event: threading.Event,
  on_ready: Callable[[SessionStatus], None],
  logger: SessionLogger,
) -> None:
  profile = benchmark_case.executable_profile
  if profile is None:
    raise CaseConfigurationError(
      f"Case {benchmark_case.case_id} has no executable Checkout profile."
    )

  support_server = None
  preview = None
  playwright = None
  browser = None
  context = None
  try:
    if not skip_build:
      build_checkout_app()

    needs_support_server = requires_controlled_support_destination(profile)
    if needs_support_server:
      support_server = start_controlled_support_server()
      wait_for_url(CONTROLLED_SUPPORT_RETURNS_URL, timeout_seconds=20)

    port = find_free_port()
    preview = start_vite_preview(port=port)
    initial_url = f"http://127.0.0.1:{port}{CHECKOUT_INITIAL_ROUTE}"
    wait_for_url(initial_url, timeout_seconds=20)

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(viewport=VIEWPORT)
    await context.add_init_script(
      f"window[{json.dumps(CHECKOUT_PROFILE_GLOBAL)}] = {json.dumps(profile)};"
    )
    support_url = None
    if needs_support_server:
      support_url = CONTROLLED_SUPPORT_RETURNS_URL
      await context.add_init_script(
        f"window[{json.dumps(CHECKOUT_SUPPORT_ORIGIN_GLOBAL)}] = "
        f"{json.dumps(CONTROLLED_SUPPORT_ORIGIN)};"
      )
    page = await context.new_page()
    await page.goto(initial_url, wait_until="networkidle")
    on_ready(
      SessionStatus(
        state="running",
        case_id=benchmark_case.case_id,
        profile=profile,
        url=initial_url,
        support_url=support_url,
      )
    )

    while not stop_event.is_set():
      await asyncio.sleep(0.25)
  finally:
    await _close_context(context, logger)
    await _close_browser(browser, logger)
    if playwright is not None:
      await playwright.stop()
    if preview is not None:
      stop_process(preview)
    if support_server is not None:
      stop_process(support_server)


def booking_target_state(benchmark_case: BenchmarkCase) -> str:
  if len(benchmark_case.expected_routes) != 1:
    raise CaseConfigurationError(
      f"Booking case {benchmark_case.case_id} must declare exactly one expected route."
    )
  route = benchmark_case.expected_routes[0]
  target_state = BOOKING_ROUTE_TO_STATE.get(route)
  if target_state is None:
    supported = ", ".join(sorted(BOOKING_ROUTE_TO_STATE))
    raise CaseConfigurationError(
      f"Booking case {benchmark_case.case_id} uses unsupported route {route!r}; "
      f"expected one of: {supported}."
    )
  return target_state


async def run_booking_variant(
  benchmark_case: BenchmarkCase,
  skip_build: bool,
  stop_event: threading.Event,
  on_ready: Callable[[SessionStatus], None],
  logger: SessionLogger,
) -> None:
  profile = benchmark_case.executable_profile
  if profile is None:
    raise CaseConfigurationError(
      f"Case {benchmark_case.case_id} has no executable Booking profile."
    )
  target_state = booking_target_state(benchmark_case)

  playwright = None
  browser = None
  with open_booking_spa(build=not skip_build) as spa:
    try:
      playwright = await async_playwright().start()
      browser = await playwright.chromium.launch(headless=False)
      async with open_booking_run(
        browser,
        base_url=spa.base_url,
        profile=profile,
        target_state=target_state,
      ) as booking_run:
        on_ready(
          SessionStatus(
            state="running",
            case_id=benchmark_case.case_id,
            profile=profile,
            url=booking_run.page.url,
          )
        )
        while not stop_event.is_set():
          await asyncio.sleep(0.25)
    finally:
      await _close_browser(browser, logger)
      if playwright is not None:
        await playwright.stop()


async def _close_context(context, logger: SessionLogger) -> None:
  if context is None:
    return
  try:
    await context.close()
  except Exception as exc:
    logger(f"Benchmark SPA Explorer context cleanup warning: {exc}")


async def _close_browser(browser, logger: SessionLogger) -> None:
  if browser is None:
    return
  try:
    await browser.close()
  except Exception as exc:
    logger(f"Benchmark SPA Explorer browser cleanup warning: {exc}")
