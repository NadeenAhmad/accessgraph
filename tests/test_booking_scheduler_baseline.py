from __future__ import annotations

import asyncio
import socket
import subprocess
import time
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOKING_DIR = REPO_ROOT / "benchmarks" / "local-spas" / "booking-scheduler"
VIEWPORT = {"width": 1280, "height": 800}
PROVIDER_NAME = "Harbor Point Clinic"
PROVIDER_LOCATION = "24 Cedar Lane, Northbridge"
BLOCKED_RUNTIME_MUTATION_TOKENS = (
  "bs-sem-",
  "co-sem-",
  "tm-sem-",
  "semanticVariants",
  "activeSemanticSeeds",
  "semanticSeed",
)


def _booking_runtime_source_files(src_dir: Path) -> list[Path]:
  benchmark_dir = src_dir / "benchmark"
  source_files = list(src_dir.rglob("*.js"))
  source_files.extend(src_dir.rglob("*.jsx"))
  return sorted(
    path
    for path in source_files
    if benchmark_dir not in path.parents
  )


def _assert_no_case_specific_runtime_mutations(source_files: list[Path]) -> None:
  for path in source_files:
    source_text = path.read_text(encoding="utf-8")
    for token in BLOCKED_RUNTIME_MUTATION_TOKENS:
      assert token not in source_text, (
        f"Blocked token {token!r} found in runtime source {path}"
      )


def _find_free_port() -> int:
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
    sock.bind(("127.0.0.1", 0))
    return int(sock.getsockname()[1])


def _wait_for_url(url: str, *, timeout_seconds: int) -> None:
  deadline = time.perf_counter() + timeout_seconds
  last_error: Exception | None = None
  while time.perf_counter() < deadline:
    try:
      with urlopen(url, timeout=1) as response:
        if response.status == 200:
          return
    except Exception as error:
      last_error = error
      time.sleep(0.25)
  raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _start_vite_dev(*, port: int) -> subprocess.Popen[str]:
  vite_bin = BOOKING_DIR / "node_modules" / "vite" / "bin" / "vite.js"
  if not vite_bin.exists():
    pytest.skip(f"Vite executable is unavailable: {vite_bin}")
  return subprocess.Popen(
    [
      "node",
      str(vite_bin),
      "--host",
      "127.0.0.1",
      "--port",
      str(port),
    ],
    cwd=BOOKING_DIR,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
  )


def _stop_process(process: subprocess.Popen[str]) -> None:
  if process.poll() is not None:
    return
  process.terminate()
  try:
    process.wait(timeout=5)
  except subprocess.TimeoutExpired:
    process.kill()


async def _with_booking_page(callback):
  playwright = pytest.importorskip("playwright.async_api")
  port = _find_free_port()
  server = _start_vite_dev(port=port)
  manager = None
  browser = None
  context = None
  try:
    base_url = f"http://127.0.0.1:{port}/"
    _wait_for_url(base_url, timeout_seconds=20)
    try:
      manager = await playwright.async_playwright().start()
      browser = await manager.chromium.launch(headless=True)
    except Exception as exc:
      pytest.skip(f"Playwright Chromium is unavailable: {exc}")
    context = await browser.new_context(viewport=VIEWPORT)
    page = await context.new_page()
    return await callback(page, base_url)
  finally:
    if context is not None:
      await context.close()
    if browser is not None:
      await browser.close()
    if manager is not None:
      await manager.stop()
    _stop_process(server)


async def _choose_consultation(page) -> None:
  await page.locator('[data-testid="service-radio-svc-consultation"]').check()
  await page.locator('[data-testid="continue-to-schedule"]').click()
  await page.wait_for_url("**/schedule")


async def _set_date(page, value: str) -> None:
  await page.locator('[data-testid="schedule-date-input"]').fill(value)


async def _complete_schedule(
  page,
  *,
  date: str = "2026-06-16",
  slot_test_id: str = "slot-button-0900",
) -> None:
  await _set_date(page, date)
  await page.locator(f'[data-testid="{slot_test_id}"]').click()
  await page.locator('[data-testid="continue-to-details"]').click()
  await page.wait_for_url("**/details")


async def _fill_customer_details(
  page,
  *,
  full_name: str = "Jordan Lee",
  email: str = "jordan.lee@example.test",
  phone: str = "555-0134",
) -> None:
  await page.locator('[data-testid="details-full-name"]').fill(full_name)
  await page.locator('[data-testid="details-email"]').fill(email)
  await page.locator('[data-testid="details-phone"]').fill(phone)


async def _reach_review(page, base_url: str) -> None:
  await page.goto(f"{base_url}services", wait_until="domcontentloaded")
  await _choose_consultation(page)
  await _complete_schedule(page)
  await _fill_customer_details(page)
  await page.locator('[data-testid="details-submit"]').click()
  await page.wait_for_url("**/review")


async def _confirm_booking(page) -> None:
  await page.locator('[data-testid="confirm-booking"]').click()
  await page.wait_for_url("**/confirmation")


async def _assert_current_progress(page, step_id: str) -> None:
  current_steps = page.locator('[aria-current="step"]')
  assert await current_steps.count() == 1
  assert await current_steps.get_attribute("data-testid") == (
    f"booking-progress-{step_id}"
  )
  assert await current_steps.get_by_role("link").count() == 0


def test_booking_baseline_completes_service_to_review_flow():
  async def run(page, base_url):
    await page.goto(f"{base_url}services", wait_until="domcontentloaded")

    assert await page.title() == "Select service | Booking Scheduler Benchmark"
    assert await page.locator("html").get_attribute("lang") == "en"
    assert await page.locator('[data-testid="route-services"]').count() == 1
    assert await page.get_by_role("group", name="Available services").count() == 1
    assert await page.locator('[data-testid="service-list"]').get_attribute(
      "role"
    ) is None
    assert (
      await page.locator('[data-testid="booking-progress-services"]').get_attribute(
        "aria-current"
      )
      == "step"
    )

    await _choose_consultation(page)
    assert await page.title() == "Schedule appointment | Booking Scheduler Benchmark"
    assert await page.locator('[data-testid="slot-empty-prompt"]').is_visible()

    await _set_date(page, "2026-06-16")
    assert await page.locator('[data-testid="slot-button-0900"]').is_visible()
    assert "Unavailable" in await page.locator(
      '[data-testid="slot-unavailable-1030"]'
    ).inner_text()

    await page.locator('[data-testid="slot-button-0900"]').click()
    assert (
      await page.locator('[data-testid="slot-button-0900"]').get_attribute(
        "aria-pressed"
      )
      == "true"
    )
    assert "Selected" in await page.locator(
      '[data-testid="slot-button-0900"]'
    ).inner_text()

    await _set_date(page, "2026-06-18")
    assert await page.locator('[data-testid="slot-button-0900"]').count() == 0
    assert await page.locator('[data-testid="summary-slot"]').inner_text() == (
      "No time selected"
    )
    assert "Selected time cleared" in await page.locator(
      '[data-testid="status-region"]'
    ).inner_text()

    await _set_date(page, "2026-06-16")
    await page.locator('[data-testid="slot-button-0900"]').click()
    await page.locator('[data-testid="continue-to-details"]').click()
    await page.wait_for_url("**/details")

    assert await page.title() == "Booking details | Booking Scheduler Benchmark"
    assert await page.locator("main").count() == 1
    assert await page.locator("aside").count() == 1
    assert await page.locator('[data-testid="details-full-name"]').get_attribute(
      "autocomplete"
    ) == "name"
    assert await page.locator('[data-testid="details-email"]').get_attribute(
      "autocomplete"
    ) == "email"
    assert await page.locator('[data-testid="details-phone"]').get_attribute(
      "autocomplete"
    ) == "tel"
    for test_id in ("details-full-name", "details-email", "details-phone"):
      field_id = await page.locator(f'[data-testid="{test_id}"]').get_attribute("id")
      assert await page.locator(f'label[for="{field_id}"]').count() == 1

    await page.locator('[data-testid="details-submit"]').click()
    assert await page.locator('[data-testid="details-validation-status"]').is_visible()
    assert await page.locator(
      '[data-testid="details-full-name"]'
    ).get_attribute("aria-invalid") == "true"
    assert await page.locator(
      '[data-testid="details-full-name"]'
    ).get_attribute("aria-describedby") == "details-fullName-error"
    assert await page.locator(
      '[data-testid="details-full-name-error"]'
    ).inner_text() == "Full name is required."

    await page.locator('[data-testid="details-full-name"]').fill("Jordan Lee")
    await page.locator('[data-testid="details-email"]').fill(
      "jordan.lee@example.test"
    )
    await page.locator('[data-testid="details-phone"]').fill("555-0134")
    await page.locator('[data-testid="details-submit"]').click()
    await page.wait_for_url("**/review")

    assert await page.title() == "Review appointment | Booking Scheduler Benchmark"
    assert await page.locator("html").get_attribute("lang") == "en"
    assert await page.locator("main").count() == 1
    assert await page.locator("aside").count() == 1
    assert await page.locator('[data-testid="review-service-name"]').inner_text() == (
      "Consultation"
    )
    assert await page.locator('[data-testid="review-date"]').inner_text() == (
      "June 16, 2026"
    )
    assert await page.locator('[data-testid="review-slot"]').inner_text() == "09:00"
    assert await page.locator(
      '[data-testid="review-customer-full-name"]'
    ).inner_text() == "Jordan Lee"

  asyncio.run(_with_booking_page(run))


def test_booking_baseline_guards_routes_and_handles_unsupported_date():
  async def run(page, base_url):
    for guarded_route in ("schedule", "details", "review"):
      await page.goto(f"{base_url}{guarded_route}", wait_until="domcontentloaded")
      await page.wait_for_url("**/services")
      assert await page.locator('[data-testid="route-services"]').count() == 1
      assert "Select a service" in await page.locator(
        '[data-testid="status-region"]'
      ).inner_text()

    await _choose_consultation(page)
    date_input = page.locator('[data-testid="schedule-date-input"]')
    await date_input.evaluate(
      """input => {
        input.value = "2026-06-17";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }"""
    )

    assert await date_input.input_value() == "2026-06-17"
    assert await page.locator('[data-testid="slot-list"]').count() == 0
    assert "supported fixture date" in (
      await page.locator('[data-testid="slot-empty-prompt"]').inner_text()
    )

  asyncio.run(_with_booking_page(run))


def test_booking_preserves_customer_draft_through_browser_history():
  async def run(page, base_url):
    await page.goto(f"{base_url}services", wait_until="domcontentloaded")
    await _choose_consultation(page)
    await _complete_schedule(page)
    await _fill_customer_details(page)

    await page.go_back()
    await page.wait_for_url("**/schedule")
    assert await page.title() == "Schedule appointment | Booking Scheduler Benchmark"
    assert await page.get_by_role("heading", name="Schedule appointment").count() == 1
    assert (
      await page.locator('[data-testid="booking-progress-schedule"]').get_attribute(
        "aria-current"
      )
      == "step"
    )
    assert await page.locator('[data-testid="schedule-date-input"]').input_value() == (
      "2026-06-16"
    )
    assert (
      await page.locator('[data-testid="slot-button-0900"]').get_attribute(
        "aria-pressed"
      )
      == "true"
    )

    await page.go_forward()
    await page.wait_for_url("**/details")
    assert await page.title() == "Booking details | Booking Scheduler Benchmark"
    assert await page.locator('[data-testid="details-full-name"]').input_value() == (
      "Jordan Lee"
    )
    assert await page.locator('[data-testid="details-email"]').input_value() == (
      "jordan.lee@example.test"
    )
    assert await page.locator('[data-testid="details-phone"]').input_value() == (
      "555-0134"
    )

    await page.locator('[data-testid="details-submit"]').click()
    await page.wait_for_url("**/review")
    await page.go_back()
    await page.wait_for_url("**/details")
    assert await page.locator('[data-testid="details-full-name"]').input_value() == (
      "Jordan Lee"
    )
    assert (
      await page.locator('[data-testid="booking-progress-review"]').get_attribute(
        "data-state"
      )
      == "available"
    )

    await page.go_forward()
    await page.wait_for_url("**/review")
    assert await page.title() == "Review appointment | Booking Scheduler Benchmark"
    assert (
      await page.locator('[data-testid="review-customer-full-name"]').inner_text()
      == "Jordan Lee"
    )
    assert (
      await page.locator('[data-testid="booking-progress-review"]').get_attribute(
        "aria-current"
      )
      == "step"
    )

  asyncio.run(_with_booking_page(run))


def test_booking_upstream_changes_clear_slot_and_preserve_customer_details():
  async def run(page, base_url):
    await _reach_review(page, base_url)

    await page.go_back()
    await page.wait_for_url("**/details")
    await page.go_back()
    await page.wait_for_url("**/schedule")

    await _set_date(page, "2026-06-18")
    assert await page.locator('[data-testid="summary-slot"]').inner_text() == (
      "No time selected"
    )
    await page.locator('[data-testid="slot-button-0830"]').click()
    await page.locator('[data-testid="continue-to-details"]').click()
    await page.wait_for_url("**/details")
    assert await page.locator('[data-testid="details-full-name"]').input_value() == (
      "Jordan Lee"
    )
    assert (
      await page.locator('[data-testid="booking-progress-review"]').get_attribute(
        "data-state"
      )
      == "available"
    )

    await page.go_back()
    await page.wait_for_url("**/schedule")
    await page.go_back()
    await page.wait_for_url("**/services")
    await page.locator(
      '[data-testid="service-radio-svc-repair-assessment"]'
    ).check()

    assert await page.locator('[data-testid="summary-date"]').inner_text() == (
      "June 18, 2026"
    )
    assert await page.locator('[data-testid="summary-slot"]').inner_text() == (
      "No time selected"
    )

    await page.locator('[data-testid="continue-to-schedule"]').click()
    await page.wait_for_url("**/schedule")
    assert await page.locator('[data-testid="schedule-date-input"]').input_value() == (
      "2026-06-18"
    )
    await page.locator('[data-testid="slot-button-0830"]').click()
    await page.locator('[data-testid="continue-to-details"]').click()
    await page.wait_for_url("**/details")
    assert await page.locator('[data-testid="details-full-name"]').input_value() == (
      "Jordan Lee"
    )
    assert await page.locator('[data-testid="details-email"]').input_value() == (
      "jordan.lee@example.test"
    )
    assert (
      await page.locator('[data-testid="booking-progress-review"]').get_attribute(
        "data-state"
      )
      == "available"
    )

  asyncio.run(_with_booking_page(run))


def test_booking_detail_edit_blocks_stale_review_until_resubmitted():
  async def run(page, base_url):
    await _reach_review(page, base_url)

    await page.go_back()
    await page.wait_for_url("**/details")
    await page.locator('[data-testid="details-full-name"]').fill("")

    await page.go_forward()
    await page.wait_for_url("**/details")
    assert await page.title() == "Booking details | Booking Scheduler Benchmark"
    assert "Enter booking details" in await page.locator(
      '[data-testid="status-region"]'
    ).inner_text()
    assert await page.locator('[data-testid="details-full-name"]').input_value() == ""

    await page.locator('[data-testid="details-full-name"]').fill("Jordan Kim")
    await page.locator('[data-testid="details-submit"]').click()
    await page.wait_for_url("**/review")
    assert (
      await page.locator('[data-testid="review-customer-full-name"]').inner_text()
      == "Jordan Kim"
    )

  asyncio.run(_with_booking_page(run))


def test_booking_explicit_back_and_progress_navigation_preserve_state():
  async def run(page, base_url):
    await page.goto(f"{base_url}services", wait_until="domcontentloaded")

    assert await page.get_by_role("navigation", name="Booking progress").count() == 1
    await _assert_current_progress(page, "services")
    assert await page.locator(
      '[data-testid="booking-progress-schedule"] a'
    ).count() == 0
    assert await page.locator(
      '[data-testid="booking-progress-details"] a'
    ).count() == 0
    assert await page.locator(
      '[data-testid="booking-progress-review"] a'
    ).count() == 0

    await _choose_consultation(page)
    await _set_date(page, "2026-06-16")
    await page.locator('[data-testid="slot-button-0900"]').click()
    await _assert_current_progress(page, "schedule")
    assert await page.locator(
      '[data-testid="booking-progress-services"] a'
    ).get_attribute("href") == "/services"
    assert await page.locator(
      '[data-testid="booking-progress-details"] a'
    ).get_attribute("href") == "/details"
    assert await page.locator(
      '[data-testid="booking-progress-review"] a'
    ).count() == 0

    await page.locator('[data-testid="back-to-services"]').click()
    await page.wait_for_url("**/services")
    await _assert_current_progress(page, "services")
    assert await page.locator(
      '[data-testid="service-radio-svc-consultation"]'
    ).is_checked()
    assert await page.locator('[data-testid="summary-date"]').inner_text() == (
      "June 16, 2026"
    )
    assert await page.locator('[data-testid="summary-slot"]').inner_text() == "09:00"

    await page.locator(
      '[data-testid="booking-progress-schedule"] a'
    ).click()
    await page.wait_for_url("**/schedule")
    assert await page.locator('[data-testid="schedule-date-input"]').input_value() == (
      "2026-06-16"
    )
    assert (
      await page.locator('[data-testid="slot-button-0900"]').get_attribute(
        "aria-pressed"
      )
      == "true"
    )

    await page.locator('[data-testid="continue-to-details"]').click()
    await page.wait_for_url("**/details")
    await _fill_customer_details(page)
    await page.locator('[data-testid="back-to-schedule"]').click()
    await page.wait_for_url("**/schedule")
    assert await page.locator('[data-testid="summary-slot"]').inner_text() == "09:00"

    await page.locator(
      '[data-testid="booking-progress-details"] a'
    ).click()
    await page.wait_for_url("**/details")
    assert await page.locator('[data-testid="details-full-name"]').input_value() == (
      "Jordan Lee"
    )

    await page.go_back()
    await page.wait_for_url("**/schedule")
    assert await page.title() == "Schedule appointment | Booking Scheduler Benchmark"
    await _assert_current_progress(page, "schedule")
    await page.go_forward()
    await page.wait_for_url("**/details")
    assert await page.title() == "Booking details | Booking Scheduler Benchmark"
    await _assert_current_progress(page, "details")
    assert await page.locator('[data-testid="details-email"]').input_value() == (
      "jordan.lee@example.test"
    )

  asyncio.run(_with_booking_page(run))


def test_booking_review_edit_details_recomputes_review_reachability():
  async def run(page, base_url):
    await _reach_review(page, base_url)

    for test_id, href in (
      ("change-service", "/services"),
      ("change-appointment", "/schedule"),
      ("edit-details", "/details"),
    ):
      link = page.locator(f'[data-testid="{test_id}"]')
      assert await link.get_attribute("href") == href

    await page.locator('[data-testid="edit-details"]').click()
    await page.wait_for_url("**/details")
    assert await page.locator('[data-testid="details-full-name"]').input_value() == (
      "Jordan Lee"
    )
    assert await page.locator(
      '[data-testid="booking-progress-review"] a'
    ).count() == 1

    await page.locator('[data-testid="details-full-name"]').fill("")
    assert await page.locator(
      '[data-testid="booking-progress-review"] a'
    ).count() == 0
    assert (
      await page.locator('[data-testid="booking-progress-review"]').get_attribute(
        "data-state"
      )
      == "unavailable"
    )

    await page.locator('[data-testid="details-full-name"]').fill("Jordan Kim")
    await page.locator('[data-testid="details-submit"]').click()
    await page.wait_for_url("**/review")
    assert (
      await page.locator('[data-testid="review-customer-full-name"]').inner_text()
      == "Jordan Kim"
    )

    await page.go_back()
    await page.wait_for_url("**/details")
    await _assert_current_progress(page, "details")
    await page.go_forward()
    await page.wait_for_url("**/review")
    await _assert_current_progress(page, "review")
    assert await page.title() == "Review appointment | Booking Scheduler Benchmark"

  asyncio.run(_with_booking_page(run))


def test_booking_review_change_actions_preserve_then_invalidate_dependencies():
  async def run(page, base_url):
    await _reach_review(page, base_url)

    await page.locator('[data-testid="change-appointment"]').click()
    await page.wait_for_url("**/schedule")
    assert await page.locator('[data-testid="schedule-date-input"]').input_value() == (
      "2026-06-16"
    )
    assert (
      await page.locator('[data-testid="slot-button-0900"]').get_attribute(
        "aria-pressed"
      )
      == "true"
    )
    assert await page.locator(
      '[data-testid="booking-progress-review"] a'
    ).count() == 1

    await _set_date(page, "2026-06-18")
    assert await page.locator('[data-testid="summary-slot"]').inner_text() == (
      "No time selected"
    )
    assert await page.locator(
      '[data-testid="booking-progress-details"] a'
    ).count() == 0
    assert await page.locator(
      '[data-testid="booking-progress-review"] a'
    ).count() == 0

    await page.locator('[data-testid="slot-button-0830"]').click()
    await page.locator(
      '[data-testid="booking-progress-details"] a'
    ).click()
    await page.wait_for_url("**/details")
    assert await page.locator('[data-testid="details-email"]').input_value() == (
      "jordan.lee@example.test"
    )
    await page.locator(
      '[data-testid="booking-progress-review"] a'
    ).click()
    await page.wait_for_url("**/review")
    assert await page.locator('[data-testid="review-date"]').inner_text() == (
      "June 18, 2026"
    )
    assert await page.locator('[data-testid="review-slot"]').inner_text() == "08:30"

    await page.locator('[data-testid="change-service"]').click()
    await page.wait_for_url("**/services")
    assert await page.locator(
      '[data-testid="service-radio-svc-consultation"]'
    ).is_checked()
    assert await page.locator('[data-testid="summary-slot"]').inner_text() == "08:30"

    await page.locator(
      '[data-testid="service-radio-svc-repair-assessment"]'
    ).check()
    assert await page.locator('[data-testid="summary-date"]').inner_text() == (
      "June 18, 2026"
    )
    assert await page.locator('[data-testid="summary-slot"]').inner_text() == (
      "No time selected"
    )
    assert await page.locator(
      '[data-testid="booking-progress-review"] a'
    ).count() == 0

    await page.locator(
      '[data-testid="booking-progress-schedule"] a'
    ).click()
    await page.wait_for_url("**/schedule")
    assert await page.locator('[data-testid="schedule-date-input"]').input_value() == (
      "2026-06-18"
    )
    await page.locator('[data-testid="slot-button-0830"]').click()
    await page.locator(
      '[data-testid="booking-progress-review"] a'
    ).click()
    await page.wait_for_url("**/review")
    assert await page.locator('[data-testid="review-service-name"]').inner_text() == (
      "Repair assessment"
    )
    assert (
      await page.locator('[data-testid="review-customer-full-name"]').inner_text()
      == "Jordan Lee"
    )

  asyncio.run(_with_booking_page(run))


def test_booking_confirmation_creates_terminal_snapshot():
  async def run(page, base_url):
    await _reach_review(page, base_url)

    confirm_button = page.get_by_role("button", name="Confirm booking")
    assert await confirm_button.count() == 1
    await _confirm_booking(page)

    assert await page.title() == "Booking confirmed | Booking Scheduler Benchmark"
    assert await page.get_by_role("heading", name="Booking confirmed").count() == 1
    await page.wait_for_function(
      "document.activeElement === document.querySelector('h1')"
    )
    assert await page.locator('[data-testid="confirmation-message"]').is_visible()
    assert await page.locator('[data-testid="confirmation-reference"]').inner_text() == (
      "BKG-20260616-0900-CONSULTATION"
    )
    assert await page.locator('[data-testid="confirmation-service"]').inner_text() == (
      "Consultation"
    )
    assert await page.locator('[data-testid="confirmation-date"]').inner_text() == (
      "June 16, 2026"
    )
    assert await page.locator('[data-testid="confirmation-time"]').inner_text() == (
      "09:00"
    )
    assert await page.locator(
      '[data-testid="confirmation-customer-name"]'
    ).inner_text() == "Jordan Lee"
    assert await page.locator(
      '[data-testid="confirmation-customer-email"]'
    ).inner_text() == "jordan.lee@example.test"
    assert await page.locator(
      '[data-testid="confirmation-customer-phone"]'
    ).inner_text() == "555-0134"

    await _assert_current_progress(page, "confirmation")
    for step_id in ("services", "schedule", "details", "review"):
      step = page.locator(f'[data-testid="booking-progress-{step_id}"]')
      assert await step.get_attribute("data-state") == "completed"
      assert await step.get_by_role("link").count() == 0

    assert await page.locator('[data-testid="confirm-booking"]').count() == 0
    assert await page.locator('[data-testid="change-service"]').count() == 0
    assert await page.locator('[data-testid="change-appointment"]').count() == 0
    assert await page.locator('[data-testid="edit-details"]').count() == 0

    await page.go_back()
    await page.wait_for_url("**/confirmation")
    await _assert_current_progress(page, "confirmation")
    assert await page.locator('[data-testid="confirmation-reference"]').inner_text() == (
      "BKG-20260616-0900-CONSULTATION"
    )

  asyncio.run(_with_booking_page(run))


def test_booking_confirmation_guard_and_book_another_reset_history():
  async def run(page, base_url):
    await page.goto(f"{base_url}confirmation", wait_until="domcontentloaded")
    await page.wait_for_url("**/services")
    assert await page.locator('[data-testid="confirmation-message"]').count() == 0
    assert "Complete and confirm" in await page.locator(
      '[data-testid="status-region"]'
    ).inner_text()

    await _reach_review(page, base_url)
    await _confirm_booking(page)
    await page.get_by_role("button", name="Book another appointment").click()
    await page.wait_for_url("**/services")

    assert await page.locator('input[name="service"]:checked').count() == 0
    assert await page.locator('[data-testid="summary-service"]').inner_text() == (
      "No service selected"
    )
    assert await page.locator('[data-testid="summary-date"]').inner_text() == (
      "No date selected"
    )
    assert await page.locator('[data-testid="summary-slot"]').inner_text() == (
      "No time selected"
    )
    await _assert_current_progress(page, "services")
    confirmation_step = page.locator(
      '[data-testid="booking-progress-confirmation"]'
    )
    assert await confirmation_step.get_attribute("data-state") == "unavailable"
    assert await confirmation_step.get_by_role("link").count() == 0

    await page.go_back()
    await page.wait_for_url("**/services")
    assert await page.locator('[data-testid="confirmation-message"]').count() == 0
    assert await page.locator('input[name="service"]:checked').count() == 0

    await _choose_consultation(page)
    await _complete_schedule(page)
    for test_id in ("details-full-name", "details-email", "details-phone"):
      assert await page.locator(f'[data-testid="{test_id}"]').input_value() == ""

  asyncio.run(_with_booking_page(run))


def test_booking_help_route_is_unguarded_and_preserves_schedule_state():
  async def run(page, base_url):
    await page.goto(f"{base_url}help", wait_until="domcontentloaded")

    assert await page.title() == "Help & policies | Booking Scheduler Benchmark"
    assert await page.get_by_role("heading", name="Help & policies").count() == 1
    assert await page.locator('[data-testid="route-help"]').count() == 1
    assert await page.locator('[data-testid="booking-progress"]').count() == 0
    assert await page.get_by_role("navigation", name="General navigation").count() == 1
    help_link = page.get_by_role("link", name="Help & policies")
    assert await help_link.get_attribute("href") == "/help"
    assert await help_link.get_attribute("aria-current") == "page"

    for section_id, heading in (
      ("cancellation", "Cancellation policy"),
      ("rescheduling", "Rescheduling"),
      ("preparation", "Preparing for your appointment"),
      ("contact", "Contact"),
      ("directions", "Directions"),
    ):
      section = page.locator(f"section#{section_id}")
      assert await section.count() == 1
      assert await section.get_by_role("heading", name=heading, exact=True).count() == 1

    assert await page.locator('[data-testid="help-provider-name"]').inner_text() == (
      PROVIDER_NAME
    )
    assert await page.locator(
      '[data-testid="help-provider-location"]'
    ).inner_text() == PROVIDER_LOCATION
    assert "appointments@harborpoint.example" in await page.locator(
      "#contact"
    ).inner_text()
    assert "555-0168" in await page.locator("#contact").inner_text()

    await page.goto(f"{base_url}services", wait_until="domcontentloaded")
    assert await page.locator(
      '[data-testid="service-provider-name"]'
    ).inner_text() == PROVIDER_NAME
    assert await page.locator(
      '[data-testid="service-provider-location"]'
    ).inner_text() == PROVIDER_LOCATION
    preparation_link = page.locator('[data-testid="preparation-link"]')
    assert await preparation_link.evaluate("node => node.tagName") == "A"
    assert await preparation_link.get_attribute("href") == "/help#preparation"
    await preparation_link.click()
    await page.wait_for_url("**/help#preparation")
    assert await page.get_by_role(
      "heading", name="Preparing for your appointment"
    ).is_visible()
    assert await page.locator('[data-testid="booking-progress"]').count() == 0

    await page.go_back()
    await page.wait_for_url("**/services")
    await _choose_consultation(page)
    await _set_date(page, "2026-06-16")
    await page.locator('[data-testid="slot-button-0900"]').click()
    await page.get_by_role("link", name="Help & policies").click()
    await page.wait_for_url("**/help")
    await page.go_back()
    await page.wait_for_url("**/schedule")
    assert await page.locator('[data-testid="schedule-date-input"]').input_value() == (
      "2026-06-16"
    )
    assert (
      await page.locator('[data-testid="slot-button-0900"]').get_attribute(
        "aria-pressed"
      )
      == "true"
    )

  asyncio.run(_with_booking_page(run))


def test_booking_review_help_links_preserve_booking_state():
  async def run(page, base_url):
    await _reach_review(page, base_url)

    assert await page.locator('[data-testid="review-provider-name"]').inner_text() == (
      PROVIDER_NAME
    )
    assert await page.locator(
      '[data-testid="review-provider-location"]'
    ).inner_text() == PROVIDER_LOCATION

    cancellation_link = page.locator('[data-testid="cancellation-policy-link"]')
    rescheduling_link = page.locator('[data-testid="rescheduling-help-link"]')
    assert await cancellation_link.evaluate("node => node.tagName") == "A"
    assert await cancellation_link.get_attribute("href") == "/help#cancellation"
    assert await rescheduling_link.get_attribute("href") == "/help#rescheduling"

    await cancellation_link.click()
    await page.wait_for_url("**/help#cancellation")
    assert await page.get_by_role(
      "heading", name="Cancellation policy", exact=True
    ).is_visible()
    await page.go_back()
    await page.wait_for_url("**/review")

    assert await page.locator('[data-testid="review-service-name"]').inner_text() == (
      "Consultation"
    )
    assert await page.locator('[data-testid="review-date"]').inner_text() == (
      "June 16, 2026"
    )
    assert await page.locator('[data-testid="review-slot"]').inner_text() == "09:00"
    assert await page.locator(
      '[data-testid="review-customer-full-name"]'
    ).inner_text() == "Jordan Lee"
    await _assert_current_progress(page, "review")

  asyncio.run(_with_booking_page(run))


def test_booking_confirmation_help_links_preserve_confirmed_snapshot():
  async def run(page, base_url):
    await _reach_review(page, base_url)
    await _confirm_booking(page)

    reference = await page.locator(
      '[data-testid="confirmation-reference"]'
    ).inner_text()
    assert await page.locator(
      '[data-testid="confirmation-provider-name"]'
    ).inner_text() == PROVIDER_NAME
    assert await page.locator(
      '[data-testid="confirmation-provider-location"]'
    ).inner_text() == PROVIDER_LOCATION

    directions_link = page.locator('[data-testid="directions-link"]')
    contact_link = page.locator('[data-testid="contact-clinic-link"]')
    assert await directions_link.evaluate("node => node.tagName") == "A"
    assert await directions_link.get_attribute("href") == "/help#directions"
    assert await contact_link.get_attribute("href") == "/help#contact"

    await directions_link.click()
    await page.wait_for_url("**/help#directions")
    assert await page.title() == "Help & policies | Booking Scheduler Benchmark"
    assert await page.get_by_role("heading", name="Directions", exact=True).is_visible()
    assert await page.locator('[data-testid="booking-progress"]').count() == 0

    await page.go_back()
    await page.wait_for_url("**/confirmation")
    assert await page.locator(
      '[data-testid="confirmation-reference"]'
    ).inner_text() == reference
    assert await page.locator('[data-testid="confirmation-service"]').inner_text() == (
      "Consultation"
    )
    await _assert_current_progress(page, "confirmation")

  asyncio.run(_with_booking_page(run))


def test_booking_runtime_scaffolding_has_no_production_mutations():
  src_dir = BOOKING_DIR / "src"
  benchmark_dir = BOOKING_DIR / "src" / "benchmark"
  runtime_source_files = _booking_runtime_source_files(src_dir)
  _assert_no_case_specific_runtime_mutations(runtime_source_files)

  runtime_paths = {
    path.relative_to(src_dir).as_posix()
    for path in runtime_source_files
  }
  assert "App.jsx" in runtime_paths
  assert "components/DetailsPage.jsx" in runtime_paths
  assert "components/ReviewPage.jsx" in runtime_paths
  assert not any(path.startswith("benchmark/") for path in runtime_paths)

  assert {path.name for path in benchmark_dir.glob("*.js")} == {
    "effects.js",
    "profiles.js",
    "seeds.js",
    "subjects.js",
  }
  benchmark_source_text = "\n".join(
    path.read_text(encoding="utf-8")
    for path in benchmark_dir.glob("*.js")
  )
  assert "bs-sem-" in benchmark_source_text
  assert "__ACCESSGRAPH_BOOKING_PROFILE__" in benchmark_source_text
  assert "booking-clean" in benchmark_source_text
  assert not (BOOKING_DIR / "src" / "utils" / "semanticVariants.js").exists()


def test_booking_runtime_guard_rejects_case_specific_component_branch(tmp_path):
  src_dir = tmp_path / "src"
  benchmark_dir = src_dir / "benchmark"
  component_dir = src_dir / "components"
  benchmark_dir.mkdir(parents=True)
  component_dir.mkdir()

  (benchmark_dir / "profiles.js").write_text(
    'export const profile = "booking-bs-sem-999";\n',
    encoding="utf-8",
  )
  (src_dir / "App.jsx").write_text(
    'export default function App() { return null; }\n',
    encoding="utf-8",
  )
  component_path = component_dir / "Example.jsx"
  component_path.write_text(
    'if (profile === "booking-bs-sem-999") { return null; }\n',
    encoding="utf-8",
  )

  runtime_source_files = _booking_runtime_source_files(src_dir)
  assert benchmark_dir / "profiles.js" not in runtime_source_files
  assert src_dir / "App.jsx" in runtime_source_files
  assert component_path in runtime_source_files

  with pytest.raises(AssertionError, match="bs-sem-"):
    _assert_no_case_specific_runtime_mutations(runtime_source_files)
