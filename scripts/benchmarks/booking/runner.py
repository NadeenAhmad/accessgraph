from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator
from urllib.parse import urlsplit

from playwright.async_api import Browser, BrowserContext, Page


BOOKING_PROFILE_GLOBAL = "__ACCESSGRAPH_BOOKING_PROFILE__"
BOOKING_CLEAN_PROFILE = "booking-clean"
SUPPORTED_FUNCTIONAL_STATES = (
  "services",
  "schedule",
  "details",
  "review",
  "confirmation",
  "help",
)
ACTION_TIMEOUT_MS = 10_000
VIEWPORT = {"width": 1280, "height": 800}

CANONICAL_SERVICE_ID = "svc-consultation"
CANONICAL_SERVICE_NAME = "Consultation"
CANONICAL_DATE = "2026-06-16"
CANONICAL_DATE_LABEL = "June 16, 2026"
CANONICAL_TIME = "09:00"
CANONICAL_CUSTOMER_NAME = "Jordan Lee"
CANONICAL_CUSTOMER_EMAIL = "jordan.lee@example.test"
CANONICAL_CUSTOMER_PHONE = "555-0134"
CANONICAL_CONFIRMATION_REFERENCE = "BKG-20260616-0900-CONSULTATION"


class BookingRunnerError(RuntimeError):
  """Raised when a Booking run cannot establish its requested live state."""


class _BookingPageError(RuntimeError):
  pass


@dataclass(frozen=True)
class BookingRunSession:
  page: Page
  context: BrowserContext
  base_url: str
  profile: str | None
  requested_state: str
  reached_route: str


def _run_error(
  *,
  profile: str | None,
  target_state: str,
  base_url: str,
  reason: object,
) -> BookingRunnerError:
  return BookingRunnerError(
    "Booking runner failed "
    f"(app=Booking, profile={profile!r}, requested_state={target_state!r}, "
    f"server_url={base_url!r}): {reason}"
  )


def _route_url(base_url: str, route: str) -> str:
  return f"{base_url.rstrip('/')}/{route.lstrip('/')}"


async def _navigate(
  page: Page,
  base_url: str,
  route: str,
) -> None:
  await page.goto(
    _route_url(base_url, route),
    wait_until="domcontentloaded",
    timeout=ACTION_TIMEOUT_MS,
  )
  await page.locator('[data-testid="booking-scheduler-app"]').wait_for(
    state="visible",
    timeout=ACTION_TIMEOUT_MS,
  )


async def _expect_route(page: Page, route: str) -> None:
  actual = urlsplit(page.url).path
  if actual != route:
    raise AssertionError(f"Expected Booking route {route!r}, got {actual!r}")


async def _expect_text(page: Page, selector: str, expected: str) -> None:
  actual = (await page.locator(selector).inner_text(timeout=ACTION_TIMEOUT_MS)).strip()
  if actual != expected:
    raise AssertionError(
      f"Expected {selector} to contain exactly {expected!r}, got {actual!r}"
    )


async def _expect_h1(page: Page, expected: str) -> None:
  await _expect_text(page, "h1", expected)


async def _expect_visible(page: Page, selector: str) -> None:
  await page.locator(selector).wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)


async def reach_services(
  page: Page,
  base_url: str,
) -> None:
  await _navigate(page, base_url, "/services")
  await _expect_route(page, "/services")
  await _expect_h1(page, "Select service")
  await _expect_visible(page, '[data-testid="route-services"]')

  selected_services = page.locator('input[name="service"]:checked')
  if await selected_services.count() != 0:
    raise AssertionError("Services state should start without a selected service")
  if not await page.locator('[data-testid="continue-to-schedule"]').is_disabled():
    raise AssertionError("Continue to schedule should be disabled initially")


async def reach_schedule(
  page: Page,
  base_url: str,
) -> None:
  await reach_services(page, base_url)
  await page.locator(
    f'[data-testid="service-radio-{CANONICAL_SERVICE_ID}"]'
  ).check()
  await page.locator('[data-testid="continue-to-schedule"]').click()
  await page.wait_for_url("**/schedule", timeout=ACTION_TIMEOUT_MS)

  await _expect_route(page, "/schedule")
  await _expect_h1(page, "Schedule appointment")
  await _expect_visible(page, '[data-testid="route-schedule"]')
  await _expect_text(
    page,
    '[data-testid="summary-service"]',
    CANONICAL_SERVICE_NAME,
  )
  if await page.locator('[data-testid="schedule-date-input"]').input_value() != "":
    raise AssertionError("Schedule state should start with an empty date")
  if await page.locator('[data-testid="continue-to-details"]').count() != 0:
    raise AssertionError("Details continuation should require a selected appointment")


async def reach_details(
  page: Page,
  base_url: str,
) -> None:
  await reach_schedule(page, base_url)
  await page.locator('[data-testid="schedule-date-input"]').fill(CANONICAL_DATE)
  slot = page.locator('[data-testid="slot-button-0900"]')
  await slot.wait_for(state="visible", timeout=ACTION_TIMEOUT_MS)
  await slot.click()
  await page.locator('[data-testid="continue-to-details"]').click()
  await page.wait_for_url("**/details", timeout=ACTION_TIMEOUT_MS)

  await _expect_route(page, "/details")
  await _expect_h1(page, "Booking details")
  await _expect_visible(page, '[data-testid="details-form"]')
  await _expect_text(
    page,
    '[data-testid="summary-service"]',
    CANONICAL_SERVICE_NAME,
  )
  await _expect_text(page, '[data-testid="summary-date"]', CANONICAL_DATE_LABEL)
  await _expect_text(page, '[data-testid="summary-slot"]', CANONICAL_TIME)


async def reach_review(
  page: Page,
  base_url: str,
) -> None:
  await reach_details(page, base_url)
  await page.locator('[data-testid="details-full-name"]').fill(
    CANONICAL_CUSTOMER_NAME
  )
  await page.locator('[data-testid="details-email"]').fill(
    CANONICAL_CUSTOMER_EMAIL
  )
  await page.locator('[data-testid="details-phone"]').fill(
    CANONICAL_CUSTOMER_PHONE
  )
  await page.locator('[data-testid="details-submit"]').click()
  await page.wait_for_url("**/review", timeout=ACTION_TIMEOUT_MS)

  await _expect_route(page, "/review")
  await _expect_h1(page, "Review appointment")
  await _expect_visible(page, '[data-testid="review-only-note"]')
  await _expect_text(
    page,
    '[data-testid="review-service-name"]',
    CANONICAL_SERVICE_NAME,
  )
  await _expect_text(page, '[data-testid="review-date"]', CANONICAL_DATE_LABEL)
  await _expect_text(page, '[data-testid="review-slot"]', CANONICAL_TIME)
  await _expect_text(
    page,
    '[data-testid="review-customer-full-name"]',
    CANONICAL_CUSTOMER_NAME,
  )
  await _expect_text(
    page,
    '[data-testid="review-customer-email"]',
    CANONICAL_CUSTOMER_EMAIL,
  )
  await _expect_text(
    page,
    '[data-testid="review-customer-phone"]',
    CANONICAL_CUSTOMER_PHONE,
  )


async def reach_confirmation(
  page: Page,
  base_url: str,
) -> None:
  await reach_review(page, base_url)
  await page.get_by_role("button", name="Confirm booking", exact=True).click()
  await page.wait_for_url("**/confirmation", timeout=ACTION_TIMEOUT_MS)

  await _expect_route(page, "/confirmation")
  await _expect_h1(page, "Booking confirmed")
  await _expect_visible(page, '[data-testid="confirmation-message"]')
  await _expect_text(
    page,
    '[data-testid="confirmation-reference"]',
    CANONICAL_CONFIRMATION_REFERENCE,
  )


async def reach_help(
  page: Page,
  base_url: str,
) -> None:
  await _navigate(page, base_url, "/help")
  await _expect_route(page, "/help")
  await _expect_h1(page, "Help & policies")
  await _expect_visible(page, '[data-testid="help-content"]')
  await _expect_text(
    page,
    '[data-testid="help-provider-name"]',
    "Harbor Point Clinic",
  )


STATE_SETUP = {
  "services": reach_services,
  "schedule": reach_schedule,
  "details": reach_details,
  "review": reach_review,
  "confirmation": reach_confirmation,
  "help": reach_help,
}


async def _run_state_setup(
  page: Page,
  base_url: str,
  target_state: str,
  page_errors: list[str],
  page_error_event: asyncio.Event,
) -> None:
  setup_task = asyncio.create_task(STATE_SETUP[target_state](page, base_url))
  error_task = asyncio.create_task(page_error_event.wait())
  try:
    await asyncio.wait(
      {setup_task, error_task},
      return_when=asyncio.FIRST_COMPLETED,
    )
    if page_errors:
      raise _BookingPageError("; ".join(page_errors))
    await setup_task
    if page_errors:
      raise _BookingPageError("; ".join(page_errors))
  finally:
    for task in (setup_task, error_task):
      if not task.done():
        task.cancel()
    await asyncio.gather(setup_task, error_task, return_exceptions=True)


@asynccontextmanager
async def open_booking_run(
  browser: Browser,
  *,
  base_url: str,
  profile: str | None = None,
  target_state: str = "services",
) -> AsyncIterator[BookingRunSession]:
  """Prepare a live Booking state in an isolated browser context.

  Deep states depend on in-memory workflow prerequisites and are not
  URL-restorable autonomous-crawl roots; Services remains the safe crawl root.
  """
  if target_state not in SUPPORTED_FUNCTIONAL_STATES:
    supported = ", ".join(SUPPORTED_FUNCTIONAL_STATES)
    raise _run_error(
      profile=profile,
      target_state=target_state,
      base_url=base_url,
      reason=f"Unsupported functional state; expected one of: {supported}",
    )

  context = await browser.new_context(viewport=VIEWPORT)
  primary_error: BaseException | None = None
  try:
    await context.add_init_script(
      script=(
        f"window[{json.dumps(BOOKING_PROFILE_GLOBAL)}] = "
        f"{json.dumps(profile)};"
      )
    )
    page = await context.new_page()
    page.set_default_timeout(ACTION_TIMEOUT_MS)
    page.set_default_navigation_timeout(ACTION_TIMEOUT_MS)

    page_errors: list[str] = []
    page_error_event = asyncio.Event()

    def record_page_error(error: object) -> None:
      page_errors.append(str(error))
      page_error_event.set()

    page.on("pageerror", record_page_error)

    try:
      await _run_state_setup(
        page,
        base_url,
        target_state,
        page_errors,
        page_error_event,
      )
      actual_profile = await page.evaluate(
        f"window[{json.dumps(BOOKING_PROFILE_GLOBAL)}]"
      )
      if page_errors:
        raise _BookingPageError("; ".join(page_errors))
      if actual_profile != profile:
        raise AssertionError(
          "Injected Booking profile changed during state setup: "
          f"expected {profile!r}, got {actual_profile!r}"
        )
    except Exception as exc:
      reason = "; ".join(page_errors) if page_errors else str(exc)
      raise _run_error(
        profile=profile,
        target_state=target_state,
        base_url=base_url,
        reason=reason,
      ) from exc

    yield BookingRunSession(
      page=page,
      context=context,
      base_url=base_url.rstrip("/"),
      profile=profile,
      requested_state=target_state,
      reached_route=urlsplit(page.url).path,
    )
  except BaseException as exc:
    primary_error = exc
    raise
  finally:
    try:
      await context.close()
    except Exception as cleanup_error:
      if primary_error is None:
        raise
      primary_error.add_note(
        f"Booking browser-context cleanup also failed: {cleanup_error}"
      )
