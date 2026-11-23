from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_DIR = REPO_ROOT / "benchmarks" / "local-spas" / "checkout-flow"
VIEWPORT = {"width": 1280, "height": 720}
CHECKOUT_PROFILE_GLOBAL = "__ACCESSGRAPH_CHECKOUT_PROFILE__"
VALID_ADDRESS_VALUES = {
  "address-full-name": "Jordan Lee",
  "address-email": "jordan.lee@example.test",
  "address-street": "42 Market Street",
  "address-city": "Portland",
  "address-state": "OR",
  "address-postal-code": "97205",
}
VALID_PAYMENT_VALUES = {
  "payment-cardholder": "Jordan Lee",
  "payment-card-number": "4242424242424242",
  "payment-expiry": "12/30",
  "payment-security-code": "123",
}
BASELINE_QUANTITY_HEADERS = (
  "review-item-header-prod-desk-lamp review-quantity-header"
)
BASELINE_LINE_TOTAL_HEADERS = (
  "review-item-header-prod-desk-lamp review-line-total-header"
)
SEEDED_LINE_TOTAL_HEADERS = (
  "review-item-header-prod-desk-lamp review-quantity-header"
)
SEEDED_QUANTITY_HEADERS = (
  "review-item-header-prod-desk-lamp review-line-total-header"
)
NOTEBOOK_ROW_LINE_TOTAL_HEADERS = (
  "review-item-header-prod-notebook-set review-line-total-header"
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
  vite_bin = CHECKOUT_DIR / "node_modules" / "vite" / "bin" / "vite.js"
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
    cwd=CHECKOUT_DIR,
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


async def _with_checkout_page(callback, *, profile: str | None = None):
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
    except Exception as exc:
      pytest.skip(f"Playwright could not start in this environment: {exc}")
    try:
      browser = await manager.chromium.launch(headless=True)
    except Exception as exc:
      pytest.skip(f"Playwright Chromium is unavailable: {exc}")
    context = await browser.new_context(viewport=VIEWPORT)
    if profile is not None:
      await context.add_init_script(
        f"window[{CHECKOUT_PROFILE_GLOBAL!r}] = {profile!r};"
      )
    page = await context.new_page()
    await page.goto(base_url, wait_until="domcontentloaded")
    return await callback(page)
  finally:
    if context is not None:
      await context.close()
    if browser is not None:
      await browser.close()
    if manager is not None:
      await manager.stop()
    _stop_process(server)


async def _fill_testid_values(page, values: dict[str, str]) -> None:
  for test_id, value in values.items():
    await page.locator(f'[data-testid="{test_id}"]').fill(value)


async def _complete_checkout_to_review(page, *, add_notebook_set: bool = False) -> None:
  if add_notebook_set:
    await page.locator('[data-testid="product-add-prod-notebook-set"]').click()
    assert (
      (
        await page.locator(
          '[data-testid="product-quantity-prod-notebook-set"]'
        ).text_content()
      )
      or ""
    ).strip() == "In cart: 1 item"
  await page.get_by_role("link", name="Cart").click()
  await page.wait_for_url("**/cart")
  await page.locator('[data-testid="continue-to-address"]').click()
  await page.wait_for_url("**/checkout/address")
  await _fill_testid_values(page, VALID_ADDRESS_VALUES)
  await page.locator('[data-testid="continue-to-payment"]').click()
  await page.wait_for_url("**/checkout/payment")
  await _fill_testid_values(page, VALID_PAYMENT_VALUES)
  await page.locator('[data-testid="continue-to-review"]').click()
  await page.wait_for_url("**/checkout/review")

async def _review_table_snapshot(page) -> dict[str, object]:
  return await page.evaluate(
    """() => {
      const table = document.querySelector('[data-testid="review-order-table"]');
      const text = (selector) => document.querySelector(selector).textContent.trim();
      const attr = (selector, name) => document.querySelector(selector).getAttribute(name);
      const headerTexts = (headers) => headers.split(/\\s+/)
        .filter(Boolean)
        .map((id) => document.getElementById(id).textContent.trim());
      return {
        caption: table.querySelector('caption').textContent.trim(),
        rowCount: table.querySelectorAll('tbody tr').length,
        columnCount: table.querySelectorAll('thead th').length,
        columnHeaders: Array.from(table.querySelectorAll('thead th')).map((header) => ({
          id: header.id,
          text: header.textContent.trim(),
          scope: header.getAttribute('scope'),
        })),
        rowHeaderText: text('#review-item-header-prod-desk-lamp'),
        rowHeaderScope: attr('#review-item-header-prod-desk-lamp', 'scope'),
        quantityText: text('[data-testid="review-order-quantity-prod-desk-lamp"]'),
        quantityHeaders: attr('[data-testid="review-order-quantity-prod-desk-lamp"]', 'headers'),
        quantityAssociatedHeaders: headerTexts(attr('[data-testid="review-order-quantity-prod-desk-lamp"]', 'headers')),
        lineTotalText: text('[data-testid="review-order-line-total-prod-desk-lamp"]'),
        lineTotalHeaders: attr('[data-testid="review-order-line-total-prod-desk-lamp"]', 'headers'),
        lineTotalAssociatedHeaders: headerTexts(attr('[data-testid="review-order-line-total-prod-desk-lamp"]', 'headers')),
        rows: Array.from(table.querySelectorAll('tbody tr')).map((row) => {
          const rowHeader = row.querySelector('th[scope="row"]');
          const cells = row.querySelectorAll('td');
          return {
            rowTestId: row.getAttribute('data-testid'),
            rowHeaderId: rowHeader.id,
            rowHeaderText: rowHeader.textContent.trim(),
            rowHeaderScope: rowHeader.getAttribute('scope'),
            quantityText: cells[0].textContent.trim(),
            quantityHeaders: cells[0].getAttribute('headers'),
            lineTotalText: cells[1].textContent.trim(),
            lineTotalHeaders: cells[1].getAttribute('headers'),
          };
        }),
      };
    }"""
  )


def _assert_table_structure(snapshot: dict[str, object]) -> None:
  assert snapshot["caption"] == "Product quantities and totals"
  assert snapshot["rowCount"] == 1
  assert snapshot["columnCount"] == 3
  assert snapshot["columnHeaders"] == [
    {"id": "review-item-header", "text": "Item", "scope": "col"},
    {"id": "review-quantity-header", "text": "Quantity", "scope": "col"},
    {"id": "review-line-total-header", "text": "Line total", "scope": "col"},
  ]
  assert snapshot["rowHeaderText"] == "Desk lamp"
  assert snapshot["rowHeaderScope"] == "row"
  assert snapshot["quantityText"] == "1"
  assert snapshot["lineTotalText"] == "$32.00"


@pytest.mark.parametrize("profile", [None, "checkout-clean-v1", "checkout-co-sem-062"])
def test_review_table_header_associations_stay_correct_for_baseline_profiles(profile):
  async def run(page):
    await _complete_checkout_to_review(page)
    snapshot = await _review_table_snapshot(page)

    _assert_table_structure(snapshot)
    assert snapshot["quantityHeaders"] == BASELINE_QUANTITY_HEADERS
    assert snapshot["quantityAssociatedHeaders"] == ["Desk lamp", "Quantity"]
    assert snapshot["lineTotalHeaders"] == BASELINE_LINE_TOTAL_HEADERS
    assert snapshot["lineTotalAssociatedHeaders"] == ["Desk lamp", "Line total"]

  asyncio.run(_with_checkout_page(run, profile=profile))


def test_co_sem_074_changes_only_line_total_header_association():
  async def run(page):
    await _complete_checkout_to_review(page)
    snapshot = await _review_table_snapshot(page)

    _assert_table_structure(snapshot)
    assert snapshot["quantityHeaders"] == BASELINE_QUANTITY_HEADERS
    assert snapshot["quantityAssociatedHeaders"] == ["Desk lamp", "Quantity"]
    assert snapshot["lineTotalHeaders"] == SEEDED_LINE_TOTAL_HEADERS
    assert snapshot["lineTotalAssociatedHeaders"] == ["Desk lamp", "Quantity"]

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-074"))


def test_co_sem_075_changes_only_quantity_header_association():
  async def run(page):
    await _complete_checkout_to_review(page)
    snapshot = await _review_table_snapshot(page)

    _assert_table_structure(snapshot)
    assert snapshot["quantityHeaders"] == SEEDED_QUANTITY_HEADERS
    assert snapshot["quantityAssociatedHeaders"] == ["Desk lamp", "Line total"]
    assert snapshot["lineTotalHeaders"] == BASELINE_LINE_TOTAL_HEADERS
    assert snapshot["lineTotalAssociatedHeaders"] == ["Desk lamp", "Line total"]

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-075"))


@pytest.mark.parametrize(
  ("profile", "expected_desk_lamp_line_total_headers"),
  [
    (None, BASELINE_LINE_TOTAL_HEADERS),
    ("checkout-co-sem-131", NOTEBOOK_ROW_LINE_TOTAL_HEADERS),
  ],
)
def test_co_sem_131_changes_only_desk_lamp_line_total_row_header(
  profile,
  expected_desk_lamp_line_total_headers,
):
  async def run(page):
    await _complete_checkout_to_review(page, add_notebook_set=True)
    snapshot = await _review_table_snapshot(page)

    assert page.url.endswith("/checkout/review")
    assert await page.title() == "Review | Brightlane Checkout"
    assert ((await page.locator("h1").text_content()) or "").strip() == "Review"
    assert snapshot["caption"] == "Product quantities and totals"
    assert snapshot["rowCount"] == 2
    assert snapshot["columnCount"] == 3
    assert snapshot["columnHeaders"] == [
      {"id": "review-item-header", "text": "Item", "scope": "col"},
      {"id": "review-quantity-header", "text": "Quantity", "scope": "col"},
      {"id": "review-line-total-header", "text": "Line total", "scope": "col"},
    ]
    assert snapshot["rows"] == [
      {
        "rowTestId": "review-order-item-prod-desk-lamp",
        "rowHeaderId": "review-item-header-prod-desk-lamp",
        "rowHeaderText": "Desk lamp",
        "rowHeaderScope": "row",
        "quantityText": "1",
        "quantityHeaders": BASELINE_QUANTITY_HEADERS,
        "lineTotalText": "$32.00",
        "lineTotalHeaders": expected_desk_lamp_line_total_headers,
      },
      {
        "rowTestId": "review-order-item-prod-notebook-set",
        "rowHeaderId": "review-item-header-prod-notebook-set",
        "rowHeaderText": "Notebook set",
        "rowHeaderScope": "row",
        "quantityText": "1",
        "quantityHeaders": (
          "review-item-header-prod-notebook-set review-quantity-header"
        ),
        "lineTotalText": "$18.00",
        "lineTotalHeaders": NOTEBOOK_ROW_LINE_TOTAL_HEADERS,
      },
    ]

  asyncio.run(_with_checkout_page(run, profile=profile))


def test_co_sem_132_swaps_both_line_total_row_header_associations():
  async def run(page):
    await _complete_checkout_to_review(page, add_notebook_set=True)
    snapshot = await _review_table_snapshot(page)

    assert page.url.endswith("/checkout/review")
    assert await page.title() == "Review | Brightlane Checkout"
    assert ((await page.locator("h1").text_content()) or "").strip() == "Review"
    assert snapshot["caption"] == "Product quantities and totals"
    assert snapshot["rowCount"] == 2
    assert snapshot["columnCount"] == 3
    assert snapshot["columnHeaders"] == [
      {"id": "review-item-header", "text": "Item", "scope": "col"},
      {"id": "review-quantity-header", "text": "Quantity", "scope": "col"},
      {"id": "review-line-total-header", "text": "Line total", "scope": "col"},
    ]
    assert snapshot["rows"] == [
      {
        "rowTestId": "review-order-item-prod-desk-lamp",
        "rowHeaderId": "review-item-header-prod-desk-lamp",
        "rowHeaderText": "Desk lamp",
        "rowHeaderScope": "row",
        "quantityText": "1",
        "quantityHeaders": BASELINE_QUANTITY_HEADERS,
        "lineTotalText": "$32.00",
        "lineTotalHeaders": NOTEBOOK_ROW_LINE_TOTAL_HEADERS,
      },
      {
        "rowTestId": "review-order-item-prod-notebook-set",
        "rowHeaderId": "review-item-header-prod-notebook-set",
        "rowHeaderText": "Notebook set",
        "rowHeaderScope": "row",
        "quantityText": "1",
        "quantityHeaders": (
          "review-item-header-prod-notebook-set review-quantity-header"
        ),
        "lineTotalText": "$18.00",
        "lineTotalHeaders": BASELINE_LINE_TOTAL_HEADERS,
      },
    ]

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-132"))
