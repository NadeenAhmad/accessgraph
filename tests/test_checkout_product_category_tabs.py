from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_DIR = REPO_ROOT / "benchmarks" / "local-spas" / "checkout-flow"
CHECKOUT_SUPPORT_TARGET_DIR = CHECKOUT_DIR / "public"
VIEWPORT = {"width": 1280, "height": 720}
CHECKOUT_PROFILE_GLOBAL = "__ACCESSGRAPH_CHECKOUT_PROFILE__"
CHECKOUT_SUPPORT_ORIGIN_GLOBAL = "__ACCESSGRAPH_CHECKOUT_SUPPORT_ORIGIN__"
RETURNS_SUPPORT_PATH = "/returns-and-refunds.html"
SHIPPING_INFORMATION_SUPPORT_PATH = "/shipping-information.html"
OPAQUE_SUPPORT_RESOURCE_PATH = "/resource.html"
DESK_LAMP_BASELINE_ALT = "Desk lamp with adjustable brass shade"
DESK_LAMP_SPANISH_ALT = "Lámpara de escritorio con pantalla de latón ajustable"
NOTEBOOK_SET_BASELINE_ALT = "Three notebooks with blue, teal, and coral covers"
NOTEBOOK_SET_SPANISH_ALT = (
  "Tres cuadernos con cubiertas de color azul, verde azulado y coral"
)
DESK_LAMP_IMAGE_ALT_CASES = {
  "checkout-co-sem-006": "A dog",
  "checkout-co-sem-007": "Floor lamp",
  "checkout-co-sem-008": "User profile avatar",
  "checkout-co-sem-009": "Purple desk lamp",
  "checkout-co-sem-010": "Two desk lamps",
  "checkout-co-sem-095": "Image",
}
ROOT_LANG_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
)
LINK_TEXT_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
)
BUTTON_LABEL_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
)
BUTTON_LABEL_WRONG_RESULT_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
  "checkout-co-sem-028",
)
WIDGET_LABEL_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
)
PAGE_TITLE_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
  "checkout-co-sem-052",
)
FORM_LABEL_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
  "checkout-co-sem-087",
)
ADDRESS_FORM_LABEL_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
  "checkout-co-sem-086",
  "checkout-co-sem-088",
)
AUTOCOMPLETE_BASELINE_PROFILE_CASES = (
  (None, {}),
  ("checkout-clean-v1", {}),
  ("checkout-unknown-profile", {}),
  ("checkout-co-sem-006", {}),
  ("checkout-co-sem-087", {"address-email": "Full name"}),
  ("checkout-co-sem-064", {}),
  ("checkout-co-sem-065", {}),
)
AUTOCOMPLETE_TARGET_PROFILE_CASES = (
  ("checkout-pilot-001", {"address-street": "email"}),
  ("checkout-co-sem-061", {"address-full-name": "organization-title"}),
  ("checkout-co-sem-062", {"address-street": "email"}),
  ("checkout-co-sem-063", {"address-postal-code": "address-level2"}),
  ("checkout-co-sem-122", {"address-city": "address-level1"}),
  ("checkout-co-sem-123", {"address-state": "address-level2"}),
  ("checkout-co-sem-124", {"address-street": "billing street-address"}),
  ("checkout-co-sem-126", {"address-country": "address-level1"}),
)
AUTOCOMPLETE_PAYMENT_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
  "checkout-co-sem-061",
  "checkout-co-sem-062",
  "checkout-co-sem-063",
)
AUTOCOMPLETE_PAYMENT_TARGET_PROFILE_CASES = (
  ("checkout-co-sem-064", {"payment-card-number": "cc-name"}),
  ("checkout-co-sem-065", {"payment-security-code": "cc-exp"}),
  ("checkout-co-sem-125", {"payment-expiry": "cc-csc"}),
)
ARIA_CURRENT_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
  "checkout-co-sem-089",
)
LINK_TEXT_SEEDED_CASES = {
  "checkout-co-sem-020": {
    "visible_text": "Weather forecast",
    "accessible_name": "Weather forecast",
    "aria_label": None,
  },
  "checkout-co-sem-021": {
    "visible_text": "Cart",
    "accessible_name": "Weather forecast",
    "aria_label": "Weather forecast",
  },
  "checkout-co-sem-023": {
    "visible_text": "Shipping address",
    "accessible_name": "Shipping address",
    "aria_label": None,
  },
  "checkout-co-sem-024": {
    "visible_text": "Cart",
    "accessible_name": "Shipping address",
    "aria_label": "Shipping address",
  },
}
BUTTON_LABEL_SEEDED_CASES = {
  "checkout-co-sem-028": {
    "visible_text": "Weather forecast",
    "accessible_name": "Weather forecast",
    "aria_label": None,
  },
  "checkout-co-sem-029": {
    "visible_text": "Add Notebook set",
    "accessible_name": "Weather forecast",
    "aria_label": "Weather forecast",
  },
  "checkout-co-sem-031": {
    "visible_text": "Remove Notebook set",
    "accessible_name": "Remove Notebook set",
    "aria_label": None,
  },
  "checkout-co-sem-032": {
    "visible_text": "Add Notebook set",
    "accessible_name": "Remove Notebook set",
    "aria_label": "Remove Notebook set",
  },
  "checkout-co-sem-035": {
    "visible_text": "Add Cable organizer",
    "accessible_name": "Add Cable organizer",
    "aria_label": None,
  },
}
WIDGET_LABEL_SEEDED_CASES = {
  "checkout-co-sem-036": {
    "visible_text": "Fishing supplies",
    "accessible_name": "Fishing supplies",
    "aria_label": None,
  },
  "checkout-co-sem-037": {
    "visible_text": "Stationery",
    "accessible_name": "Stationery",
    "aria_label": None,
  },
  "checkout-co-sem-038": {
    "visible_text": "Desk accessories",
    "accessible_name": "Fishing supplies",
    "aria_label": "Fishing supplies",
  },
}
FORM_LABEL_SEEDED_CASES = {
  "checkout-co-sem-086": {
    "payment-card-number": "Security code",
    "payment-security-code": "Card number",
  },
  "checkout-co-sem-088": {
    "payment-card-number": "Street address",
  },
}
ADDRESS_FORM_LABEL_SEEDED_CASES = {
  "checkout-co-sem-087": {
    "address-email": "Full name",
  },
  "checkout-co-sem-107": {
    "address-country": "State",
  },
  "checkout-co-sem-108": {
    "address-delivery-instructions": "Street address",
  },
  "checkout-co-sem-109": {
    "address-city": "State",
  },
}
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


def _start_static_http(directory: Path, *, port: int) -> subprocess.Popen[str]:
  if not directory.exists():
    pytest.fail(f"Static fixture directory is unavailable: {directory}")
  return subprocess.Popen(
    [
      sys.executable,
      "-m",
      "http.server",
      str(port),
      "--bind",
      "127.0.0.1",
      "--directory",
      str(directory),
    ],
    cwd=directory,
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


async def _with_checkout_page(
  callback,
  *,
  profile: str | None = None,
  support_origin: str | None = None,
):
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
    if support_origin is not None:
      await context.add_init_script(
        f"window[{CHECKOUT_SUPPORT_ORIGIN_GLOBAL!r}] = {support_origin!r};"
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


async def _assert_tab_state(page, *, selected_tab_id: str, inactive_tab_id: str) -> None:
  selected_tab = page.locator(f"#{selected_tab_id}")
  inactive_tab = page.locator(f"#{inactive_tab_id}")

  assert await selected_tab.get_attribute("aria-selected") == "true"
  assert await inactive_tab.get_attribute("aria-selected") == "false"
  assert await selected_tab.get_attribute("tabindex") == "0"
  assert await inactive_tab.get_attribute("tabindex") == "-1"
  selected_classes = (await selected_tab.get_attribute("class")) or ""
  inactive_classes = (await inactive_tab.get_attribute("class")) or ""
  assert "is-selected" in selected_classes.split()
  assert "is-selected" not in inactive_classes.split()


async def _assert_active_element(page, expected_id: str) -> None:
  await page.wait_for_function(
    "expectedId => document.activeElement && document.activeElement.id === expectedId",
    arg=expected_id,
  )


async def _fill_testid_values(page, values: dict[str, str]) -> None:
  for test_id, value in values.items():
    await page.locator(f'[data-testid="{test_id}"]').fill(value)


async def _complete_checkout_to_review(page) -> None:
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


async def _complete_checkout_to_payment(page) -> None:
  await page.get_by_role("link", name="Cart").click()
  await page.wait_for_url("**/cart")
  await page.locator('[data-testid="continue-to-address"]').click()
  await page.wait_for_url("**/checkout/address")
  await _fill_testid_values(page, VALID_ADDRESS_VALUES)
  await page.locator('[data-testid="continue-to-payment"]').click()
  await page.wait_for_url("**/checkout/payment")


async def _complete_checkout_to_address(page) -> None:
  await page.get_by_role("link", name="Cart").click()
  await page.wait_for_url("**/cart")
  await page.locator('[data-testid="continue-to-address"]').click()
  await page.wait_for_url("**/checkout/address")


async def _label_text_for_testid(page, test_id: str) -> str:
  return await page.evaluate(
    """(testId) => {
      const input = document.querySelector(`[data-testid="${testId}"]`);
      if (!input || !input.id) {
        return "";
      }
      const label = document.querySelector(`label[for="${input.id}"]`);
      const primary = label ? label.querySelector("span:first-child") : null;
      return primary ? primary.textContent.trim().replace(/\\s+/g, " ") : "";
    }""",
    arg=test_id,
  )


async def _label_for_matches_input_id(page, test_id: str) -> bool:
  return await page.evaluate(
    """(testId) => {
      const input = document.querySelector(`[data-testid="${testId}"]`);
      if (!input || !input.id) {
        return false;
      }
      return Boolean(document.querySelector(`label[for="${input.id}"]`));
    }""",
    arg=test_id,
  )


def test_checkout_product_category_tabs_are_accessible_and_preserve_products():
  async def run(page):
    footer = page.locator(
      '[data-testid="checkout-benchmark-app"] > footer.app-footer'
    )
    tablist = page.get_by_role("tablist", name="Product categories")
    desk_tab = page.get_by_role("tab", name="Desk accessories")
    office_tab = page.get_by_role("tab", name="Office supplies")
    desk_panel = page.locator("#desk-accessories-panel")
    office_panel = page.locator("#office-supplies-panel")

    assert await footer.count() == 1
    assert "AccessGraph Shop" in ((await footer.text_content()) or "")
    assert await tablist.is_visible()
    assert await desk_tab.is_visible()
    assert await office_tab.is_visible()

    assert await desk_tab.get_attribute("aria-controls") == "desk-accessories-panel"
    assert await office_tab.get_attribute("aria-controls") == "office-supplies-panel"
    assert await desk_panel.get_attribute("role") == "tabpanel"
    assert await office_panel.get_attribute("role") == "tabpanel"
    assert await desk_panel.get_attribute("aria-labelledby") == "desk-accessories-tab"
    assert await office_panel.get_attribute("aria-labelledby") == "office-supplies-tab"

    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )
    assert await desk_panel.is_visible()
    assert not await office_panel.is_visible()
    assert "Desk lamp" in ((await desk_panel.text_content()) or "")
    assert "Cable organizer" in ((await desk_panel.text_content()) or "")

    for product_id in (
      "prod-desk-lamp",
      "prod-notebook-set",
      "prod-cable-organizer",
    ):
      assert await page.locator(f'[data-testid="product-{product_id}"]').is_visible()

    notebook_add = page.locator('[data-testid="product-add-prod-notebook-set"]')
    assert await notebook_add.is_visible()
    assert ((await notebook_add.text_content()) or "").strip() == "Add Notebook set"
    assert await page.locator('[data-testid^="product-add-prod-"]').count() == 3

    await office_tab.click()
    await _assert_tab_state(
      page,
      selected_tab_id="office-supplies-tab",
      inactive_tab_id="desk-accessories-tab",
    )
    assert await office_panel.is_visible()
    assert not await desk_panel.is_visible()
    assert "Notebook set" in ((await office_panel.text_content()) or "")

    await desk_tab.click()
    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )
    assert await desk_panel.is_visible()
    assert "Desk lamp" in ((await desk_panel.text_content()) or "")
    assert "Cable organizer" in ((await desk_panel.text_content()) or "")

    await desk_tab.focus()
    await page.keyboard.press("ArrowRight")
    await _assert_active_element(page, "office-supplies-tab")
    await _assert_tab_state(
      page,
      selected_tab_id="office-supplies-tab",
      inactive_tab_id="desk-accessories-tab",
    )

    await page.keyboard.press("ArrowLeft")
    await _assert_active_element(page, "desk-accessories-tab")
    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )

    await page.keyboard.press("End")
    await _assert_active_element(page, "office-supplies-tab")
    await _assert_tab_state(
      page,
      selected_tab_id="office-supplies-tab",
      inactive_tab_id="desk-accessories-tab",
    )

    await page.keyboard.press("Home")
    await _assert_active_element(page, "desk-accessories-tab")
    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )

    await notebook_add.click()
    cart_count = (
      (await page.locator('[data-testid="cart-summary-count"]').text_content())
      or ""
    ).strip()
    assert cart_count == "2 items"
    assert "Notebook set added to cart." in (
      (await page.locator('[data-testid="status-region"]').text_content()) or ""
    )

  asyncio.run(_with_checkout_page(run))


def test_checkout_widget_label_case_updates_category_tab_label_only():
  async def assert_category_tab_state(
    page,
    *,
    expected_accessible_name: str,
    expected_aria_label: str | None,
    expected_visible_text: str,
  ):
    target_tab = page.locator('[data-testid="product-category-tab-desk-accessories"]')
    office_tab = page.locator('[data-testid="product-category-tab-office-supplies"]')
    desk_panel = page.locator("#desk-accessories-panel")
    office_panel = page.locator("#office-supplies-panel")

    assert await page.locator("h1", has_text="Products").is_visible()
    assert await target_tab.evaluate("node => node.tagName.toLowerCase()") == "button"
    assert await target_tab.get_attribute("type") == "button"
    assert await target_tab.get_attribute("role") == "tab"
    assert await target_tab.get_attribute("id") == "desk-accessories-tab"
    assert await target_tab.get_attribute("aria-controls") == "desk-accessories-panel"
    assert await target_tab.get_attribute("aria-label") == expected_aria_label
    assert ((await target_tab.text_content()) or "").strip() == expected_visible_text
    assert await page.get_by_role("tab", name=expected_accessible_name).is_visible()
    assert await page.get_by_role(
      "tabpanel",
      name=expected_accessible_name,
    ).is_visible()

    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )
    assert await desk_panel.get_attribute("role") == "tabpanel"
    assert await desk_panel.get_attribute("aria-labelledby") == "desk-accessories-tab"
    assert await desk_panel.is_visible()
    desk_panel_text = (await desk_panel.text_content()) or ""
    assert "Desk lamp" in desk_panel_text
    assert "Cable organizer" in desk_panel_text
    assert expected_visible_text not in desk_panel_text

    assert ((await office_tab.text_content()) or "").strip() == "Office supplies"
    assert await office_tab.get_attribute("aria-label") is None
    assert await page.get_by_role("tab", name="Office supplies").is_visible()
    assert "Notebook set" in ((await office_panel.text_content()) or "")
    assert "Stationery" in (
      (await page.locator('[data-testid="product-prod-notebook-set"]').text_content())
      or ""
    )

    await office_tab.click()
    await _assert_tab_state(
      page,
      selected_tab_id="office-supplies-tab",
      inactive_tab_id="desk-accessories-tab",
    )
    assert not await desk_panel.is_visible()
    assert await office_panel.is_visible()

    await target_tab.click()
    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )
    assert await desk_panel.is_visible()
    assert "Desk lamp" in ((await desk_panel.text_content()) or "")
    assert "Cable organizer" in ((await desk_panel.text_content()) or "")

  for profile in WIDGET_LABEL_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_category_tab_state(
          page,
          expected_accessible_name="Desk accessories",
          expected_aria_label=None,
          expected_visible_text="Desk accessories",
        ),
        profile=profile,
      )
    )

  for profile, expected in WIDGET_LABEL_SEEDED_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected=expected: assert_category_tab_state(
          page,
          expected_accessible_name=expected["accessible_name"],
          expected_aria_label=expected["aria_label"],
          expected_visible_text=expected["visible_text"],
        ),
        profile=profile,
      )
    )


def test_checkout_widget_content_binding_case_preserves_tab_semantics():
  async def run(page):
    origin = await page.evaluate("window.location.origin")
    await page.goto(f"{origin}/products", wait_until="domcontentloaded")

    tablist = page.get_by_role("tablist", name="Product categories")
    desk_tab = page.locator(
      '[data-testid="product-category-tab-desk-accessories"]'
    )
    office_tab = page.locator(
      '[data-testid="product-category-tab-office-supplies"]'
    )
    desk_panel = page.locator("#desk-accessories-panel")
    office_panel = page.locator("#office-supplies-panel")

    assert page.url.endswith("/products")
    assert await page.title() == "Products | Brightlane Checkout"
    assert await page.locator("h1", has_text="Products").is_visible()
    assert await tablist.is_visible()

    assert ((await desk_tab.text_content()) or "").strip() == "Desk accessories"
    assert await page.get_by_role("tab", name="Desk accessories").is_visible()
    assert await desk_tab.get_attribute("role") == "tab"
    assert await desk_tab.get_attribute("id") == "desk-accessories-tab"
    assert await desk_tab.get_attribute("aria-controls") == (
      "desk-accessories-panel"
    )
    assert await desk_tab.get_attribute("aria-label") is None

    assert ((await office_tab.text_content()) or "").strip() == "Office supplies"
    assert await page.get_by_role("tab", name="Office supplies").is_visible()
    assert await office_tab.get_attribute("role") == "tab"
    assert await office_tab.get_attribute("id") == "office-supplies-tab"
    assert await office_tab.get_attribute("aria-controls") == (
      "office-supplies-panel"
    )
    assert await office_tab.get_attribute("aria-label") is None

    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )
    assert await desk_panel.get_attribute("role") == "tabpanel"
    assert await desk_panel.get_attribute("aria-labelledby") == (
      "desk-accessories-tab"
    )
    assert await desk_panel.is_visible()
    desk_panel_text = (await desk_panel.text_content()) or ""
    assert "Everyday supplies for notes and planning." in desk_panel_text
    assert "Notebook set" in desk_panel_text
    assert "Desk lamp" not in desk_panel_text
    assert "Cable organizer" not in desk_panel_text

    assert await office_panel.get_attribute("role") == "tabpanel"
    assert await office_panel.get_attribute("aria-labelledby") == (
      "office-supplies-tab"
    )
    assert not await office_panel.is_visible()
    office_panel_text = (await office_panel.text_content()) or ""
    assert "Everyday supplies for notes and planning." in office_panel_text
    assert "Notebook set" in office_panel_text

    for product_id in (
      "prod-desk-lamp",
      "prod-notebook-set",
      "prod-cable-organizer",
    ):
      product = page.locator(f'[data-testid="product-{product_id}"]')
      assert await product.is_visible()

    await desk_tab.focus()
    await page.keyboard.press("ArrowRight")
    await _assert_active_element(page, "office-supplies-tab")
    await _assert_tab_state(
      page,
      selected_tab_id="office-supplies-tab",
      inactive_tab_id="desk-accessories-tab",
    )
    assert not await desk_panel.is_visible()
    assert await office_panel.is_visible()
    assert "Notebook set" in ((await office_panel.text_content()) or "")

    await page.keyboard.press("ArrowLeft")
    await _assert_active_element(page, "desk-accessories-tab")
    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )
    assert await desk_panel.is_visible()
    assert "Notebook set" in ((await desk_panel.text_content()) or "")

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-113"))


def test_checkout_widget_label_swap_preserves_tab_panel_behavior():
  async def run(page):
    origin = await page.evaluate("window.location.origin")
    await page.goto(f"{origin}/products", wait_until="domcontentloaded")

    tablist = page.get_by_role("tablist", name="Product categories")
    desk_tab = page.locator(
      '[data-testid="product-category-tab-desk-accessories"]'
    )
    office_tab = page.locator(
      '[data-testid="product-category-tab-office-supplies"]'
    )
    desk_panel = page.locator("#desk-accessories-panel")
    office_panel = page.locator("#office-supplies-panel")

    assert page.url.endswith("/products")
    assert await tablist.is_visible()
    assert ((await desk_tab.text_content()) or "").strip() == "Office supplies"
    assert ((await office_tab.text_content()) or "").strip() == "Desk accessories"
    assert await desk_tab.get_attribute("aria-label") is None
    assert await office_tab.get_attribute("aria-label") is None
    assert await page.get_by_role("tab", name="Office supplies").get_attribute(
      "id"
    ) == "desk-accessories-tab"
    assert await page.get_by_role("tab", name="Desk accessories").get_attribute(
      "id"
    ) == "office-supplies-tab"

    assert await desk_tab.get_attribute("id") == "desk-accessories-tab"
    assert await desk_tab.get_attribute("aria-controls") == (
      "desk-accessories-panel"
    )
    assert await office_tab.get_attribute("id") == "office-supplies-tab"
    assert await office_tab.get_attribute("aria-controls") == (
      "office-supplies-panel"
    )
    assert await desk_panel.get_attribute("aria-labelledby") == (
      "desk-accessories-tab"
    )
    assert await office_panel.get_attribute("aria-labelledby") == (
      "office-supplies-tab"
    )

    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )
    assert await desk_panel.is_visible()
    assert not await office_panel.is_visible()
    desk_content = (await desk_panel.text_content()) or ""
    office_content = (await office_panel.text_content()) or ""
    assert "Lighting and cable tools for a tidy workspace." in desk_content
    assert "Desk lamp" in desk_content
    assert "Cable organizer" in desk_content
    assert "Everyday supplies for notes and planning." in office_content
    assert "Notebook set" in office_content

    await desk_tab.focus()
    await page.keyboard.press("ArrowRight")
    await _assert_active_element(page, "office-supplies-tab")
    await _assert_tab_state(
      page,
      selected_tab_id="office-supplies-tab",
      inactive_tab_id="desk-accessories-tab",
    )
    assert not await desk_panel.is_visible()
    assert await office_panel.is_visible()
    assert "Notebook set" in ((await office_panel.text_content()) or "")

    await page.keyboard.press("ArrowLeft")
    await _assert_active_element(page, "desk-accessories-tab")
    await page.keyboard.press("End")
    await _assert_active_element(page, "office-supplies-tab")
    await page.keyboard.press("Home")
    await _assert_active_element(page, "desk-accessories-tab")
    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-112"))


def test_checkout_tablist_name_case_preserves_child_tabs_panels_and_keyboard():
  async def assert_tablist_state(page, *, expected_name: str):
    origin = await page.evaluate("window.location.origin")
    await page.goto(f"{origin}/products", wait_until="domcontentloaded")

    tablist = page.locator('[data-testid="product-category-tablist"]')
    desk_tab = page.locator(
      '[data-testid="product-category-tab-desk-accessories"]'
    )
    office_tab = page.locator(
      '[data-testid="product-category-tab-office-supplies"]'
    )
    desk_panel = page.locator("#desk-accessories-panel")
    office_panel = page.locator("#office-supplies-panel")

    assert page.url.endswith("/products")
    assert await page.title() == "Products | Brightlane Checkout"
    assert await page.locator("h1", has_text="Products").is_visible()
    assert await tablist.evaluate("node => node.tagName.toLowerCase()") == "div"
    assert await tablist.get_attribute("role") == "tablist"
    assert await tablist.get_attribute("aria-label") == expected_name
    assert await tablist.get_attribute("aria-labelledby") is None
    assert await page.get_by_role("tablist", name=expected_name).is_visible()

    assert ((await desk_tab.text_content()) or "").strip() == "Desk accessories"
    assert await desk_tab.get_attribute("id") == "desk-accessories-tab"
    assert await desk_tab.get_attribute("role") == "tab"
    assert await desk_tab.get_attribute("aria-label") is None
    assert await desk_tab.get_attribute("aria-controls") == (
      "desk-accessories-panel"
    )
    assert ((await office_tab.text_content()) or "").strip() == "Office supplies"
    assert await office_tab.get_attribute("id") == "office-supplies-tab"
    assert await office_tab.get_attribute("role") == "tab"
    assert await office_tab.get_attribute("aria-label") is None
    assert await office_tab.get_attribute("aria-controls") == (
      "office-supplies-panel"
    )

    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )
    assert await desk_panel.get_attribute("role") == "tabpanel"
    assert await desk_panel.get_attribute("aria-labelledby") == (
      "desk-accessories-tab"
    )
    assert await office_panel.get_attribute("role") == "tabpanel"
    assert await office_panel.get_attribute("aria-labelledby") == (
      "office-supplies-tab"
    )
    assert await desk_panel.is_visible()
    assert not await office_panel.is_visible()
    desk_content = (await desk_panel.text_content()) or ""
    office_content = (await office_panel.text_content()) or ""
    assert "Lighting and cable tools for a tidy workspace." in desk_content
    assert "Desk lamp" in desk_content
    assert "Cable organizer" in desk_content
    assert "Everyday supplies for notes and planning." in office_content
    assert "Notebook set" in office_content

    await desk_tab.focus()
    await page.keyboard.press("ArrowRight")
    await _assert_active_element(page, "office-supplies-tab")
    await _assert_tab_state(
      page,
      selected_tab_id="office-supplies-tab",
      inactive_tab_id="desk-accessories-tab",
    )
    assert not await desk_panel.is_visible()
    assert await office_panel.is_visible()
    assert "Notebook set" in ((await office_panel.text_content()) or "")

    await page.keyboard.press("ArrowLeft")
    await _assert_active_element(page, "desk-accessories-tab")
    await page.keyboard.press("End")
    await _assert_active_element(page, "office-supplies-tab")
    await page.keyboard.press("Home")
    await _assert_active_element(page, "desk-accessories-tab")
    await _assert_tab_state(
      page,
      selected_tab_id="desk-accessories-tab",
      inactive_tab_id="office-supplies-tab",
    )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_tablist_state(
        page,
        expected_name="Product categories",
      ),
      profile="checkout-clean-v1",
    )
  )
  asyncio.run(
    _with_checkout_page(
      lambda page: assert_tablist_state(
        page,
        expected_name="Payment methods",
      ),
      profile="checkout-co-sem-114",
    )
  )


def test_checkout_form_label_case_swaps_payment_labels_only():
  async def assert_payment_labels(page, expected_labels: dict[str, str]):
    await _complete_checkout_to_payment(page)

    assert await page.locator("h1", has_text="Payment").is_visible()
    assert await page.get_by_role("group", name="Card details").is_visible()

    baseline_labels = {
      "payment-cardholder": "Cardholder name",
      "payment-card-number": "Card number",
      "payment-expiry": "Expiry",
      "payment-security-code": "Security code",
    }
    expected = {**baseline_labels, **expected_labels}

    for test_id, label in expected.items():
      assert await _label_for_matches_input_id(page, test_id)
      label_text = await _label_text_for_testid(page, test_id)
      assert label_text == label

    autocomplete = {
      "payment-cardholder": "cc-name",
      "payment-card-number": "cc-number",
      "payment-expiry": "cc-exp",
      "payment-security-code": "cc-csc",
    }
    for test_id, expected_autocomplete in autocomplete.items():
      assert (
        await page.locator(f'[data-testid="{test_id}"]').get_attribute(
          "autocomplete",
        )
      ) == expected_autocomplete

    assert (
      await page.locator('[data-testid="payment-card-number"]').get_attribute(
        "inputmode",
      )
    ) == "numeric"
    assert (
      await page.locator('[data-testid="payment-security-code"]').get_attribute(
        "inputmode",
      )
    ) == "numeric"
    assert await page.locator('[data-testid="continue-to-review"]').is_visible()

  for profile in FORM_LABEL_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_payment_labels(page, {}),
        profile=profile,
      )
    )

  for profile, expected_labels in FORM_LABEL_SEEDED_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected_labels=expected_labels: assert_payment_labels(
          page,
          expected_labels,
        ),
        profile=profile,
      )
    )


@pytest.mark.parametrize(
  ("profile", "expected_accessible_name", "expected_aria_label"),
  [
    (None, "Cardholder name Required", None),
    ("checkout-co-sem-109", "Cardholder name Required", None),
    ("checkout-co-sem-110", "Card number", "Card number"),
  ],
)
def test_checkout_cardholder_accessible_name_override_preserves_field_semantics(
  profile,
  expected_accessible_name,
  expected_aria_label,
):
  async def run(page):
    await _complete_checkout_to_payment(page)

    assert page.url.endswith("/checkout/payment")
    assert await page.title() == "Payment | Brightlane Checkout"
    assert await page.locator("h1", has_text="Payment").is_visible()
    assert await page.get_by_role("group", name="Card details").is_visible()

    cardholder = page.locator('[data-testid="payment-cardholder"]')
    assert await _label_for_matches_input_id(page, "payment-cardholder")
    assert await _label_text_for_testid(page, "payment-cardholder") == (
      "Cardholder name"
    )
    assert await cardholder.get_attribute("id") == "payment-cardholder"
    assert await cardholder.get_attribute("name") == "cardholder"
    assert await cardholder.get_attribute("type") == "text"
    assert await cardholder.get_attribute("autocomplete") == "cc-name"
    assert await cardholder.get_attribute("inputmode") is None
    assert await cardholder.get_attribute("required") == ""
    assert await cardholder.get_attribute("aria-label") == expected_aria_label
    assert (
      f'textbox "{expected_accessible_name}"'
      in await cardholder.aria_snapshot()
    )

    card_number = page.locator('[data-testid="payment-card-number"]')
    assert await _label_for_matches_input_id(page, "payment-card-number")
    assert await _label_text_for_testid(page, "payment-card-number") == (
      "Card number"
    )
    assert await card_number.get_attribute("id") == "payment-cardNumber"
    assert await card_number.get_attribute("name") == "cardNumber"
    assert await card_number.get_attribute("type") == "text"
    assert await card_number.get_attribute("autocomplete") == "cc-number"
    assert await card_number.get_attribute("inputmode") == "numeric"
    assert await card_number.get_attribute("required") == ""
    assert await card_number.get_attribute("aria-label") is None
    assert 'textbox "Card number Required"' in await card_number.aria_snapshot()

    await _fill_testid_values(page, VALID_PAYMENT_VALUES)
    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")
    assert (
      (
        await page.locator(
          '[data-testid="review-payment-cardholder"]'
        ).text_content()
      )
      or ""
    ).strip() == "Jordan Lee"

  asyncio.run(_with_checkout_page(run, profile=profile))


def test_checkout_cardholder_visible_label_override_preserves_payment_semantics():
  async def run(page):
    await _complete_checkout_to_payment(page)

    assert page.url.endswith("/checkout/payment")
    assert await page.title() == "Payment | Brightlane Checkout"
    assert await page.locator("h1", has_text="Payment").is_visible()
    assert await page.get_by_role("group", name="Card details").is_visible()

    cardholder = page.locator('[data-testid="payment-cardholder"]')
    assert await _label_for_matches_input_id(page, "payment-cardholder")
    assert await _label_text_for_testid(page, "payment-cardholder") == "Card number"
    assert await cardholder.get_attribute("id") == "payment-cardholder"
    assert await cardholder.get_attribute("name") == "cardholder"
    assert await cardholder.get_attribute("type") == "text"
    assert await cardholder.get_attribute("autocomplete") == "cc-name"
    assert await cardholder.get_attribute("inputmode") is None
    assert await cardholder.get_attribute("required") == ""
    assert await cardholder.get_attribute("aria-label") is None
    assert 'textbox "Card number Required"' in await cardholder.aria_snapshot()

    card_number = page.locator('[data-testid="payment-card-number"]')
    assert await _label_for_matches_input_id(page, "payment-card-number")
    assert await _label_text_for_testid(page, "payment-card-number") == (
      "Card number"
    )
    assert await card_number.get_attribute("id") == "payment-cardNumber"
    assert await card_number.get_attribute("name") == "cardNumber"
    assert await card_number.get_attribute("type") == "text"
    assert await card_number.get_attribute("autocomplete") == "cc-number"
    assert await card_number.get_attribute("inputmode") == "numeric"
    assert await card_number.get_attribute("required") == ""
    assert await card_number.get_attribute("aria-label") is None
    assert 'textbox "Card number Required"' in await card_number.aria_snapshot()

    assert await _label_text_for_testid(page, "payment-expiry") == "Expiry"
    assert await _label_text_for_testid(page, "payment-security-code") == (
      "Security code"
    )

    await _fill_testid_values(page, VALID_PAYMENT_VALUES)
    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")
    assert (
      (
        await page.locator(
          '[data-testid="review-payment-cardholder"]'
        ).text_content()
      )
      or ""
    ).strip() == "Jordan Lee"

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-111"))


def test_checkout_form_label_cases_update_only_the_target_address_label():
  async def assert_address_labels(page, expected_labels: dict[str, str]):
    await _complete_checkout_to_address(page)

    assert await page.locator("h1", has_text="Shipping address").is_visible()
    assert await page.locator('[data-testid="address-form"]').is_visible()

    baseline_labels = {
      "address-full-name": "Full name",
      "address-email": "Email",
      "address-street": "Street address",
      "address-city": "City",
      "address-state": "State",
      "address-country": "Country/region",
      "address-postal-code": "ZIP code",
      "address-delivery-instructions": "Delivery instructions",
    }
    expected = {**baseline_labels, **expected_labels}

    for test_id, label in expected.items():
      assert await _label_for_matches_input_id(page, test_id)
      label_text = await _label_text_for_testid(page, test_id)
      assert label_text == label

    assert await page.locator('[data-testid="address-email"]').get_attribute(
      "type",
    ) == "email"
    assert await page.locator('[data-testid="address-email"]').get_attribute(
      "autocomplete",
    ) == "email"
    assert await page.locator('[data-testid="address-full-name"]').get_attribute(
      "type",
    ) == "text"
    assert await page.locator('[data-testid="address-full-name"]').get_attribute(
      "autocomplete",
    ) == "name"

    city = page.locator('[data-testid="address-city"]')
    assert await city.get_attribute("id") == "address-city"
    assert await city.get_attribute("name") == "city"
    assert await city.get_attribute("type") == "text"
    assert await city.get_attribute("autocomplete") == "address-level2"
    assert await city.get_attribute("required") == ""
    assert (
      f'textbox "{expected["address-city"]} Required"'
      in await city.aria_snapshot()
    )

    state = page.locator('[data-testid="address-state"]')
    assert await state.get_attribute("id") == "address-state"
    assert await state.get_attribute("name") == "state"
    assert await state.get_attribute("type") == "text"
    assert await state.get_attribute("autocomplete") == "address-level1"
    assert await state.get_attribute("required") == ""
    assert 'textbox "State Required"' in await state.aria_snapshot()

    country = page.locator('[data-testid="address-country"]')
    assert await country.evaluate("node => node.tagName.toLowerCase()") == "select"
    assert await country.get_attribute("id") == "address-country"
    assert await country.get_attribute("name") == "country"
    assert await country.get_attribute("autocomplete") == "country-name"
    assert await country.get_attribute("required") == ""
    assert await country.get_attribute("aria-label") is None
    assert (
      f'combobox "{expected["address-country"]} Required"'
      in await country.aria_snapshot()
    )
    assert await country.input_value() == "United States"
    assert await country.locator("option").all_text_contents() == [
      "United States",
      "Canada",
      "Germany",
    ]

    delivery_instructions = page.locator(
      '[data-testid="address-delivery-instructions"]'
    )
    assert await delivery_instructions.evaluate(
      "node => node.tagName.toLowerCase()"
    ) == "textarea"
    assert await delivery_instructions.get_attribute("id") == (
      "address-deliveryInstructions"
    )
    assert await delivery_instructions.get_attribute("name") == (
      "deliveryInstructions"
    )
    assert await delivery_instructions.get_attribute("rows") == "3"
    assert await delivery_instructions.get_attribute("required") is None
    assert await delivery_instructions.get_attribute("aria-required") is None
    assert await delivery_instructions.get_attribute("autocomplete") is None
    assert await delivery_instructions.get_attribute("aria-describedby") == (
      "address-deliveryInstructions-description"
    )
    assert (
      f'textbox "{expected["address-delivery-instructions"]}"'
      in await delivery_instructions.aria_snapshot()
    )
    assert (
      (
        await page.locator(
          "#address-deliveryInstructions-description"
        ).text_content()
      )
      or ""
    ).strip() == (
      "Optional. Add gate codes, safe-place details, or delivery notes."
    )
    assert await page.locator('[data-testid="continue-to-payment"]').is_visible()

  for profile in ADDRESS_FORM_LABEL_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_address_labels(page, {}),
        profile=profile,
      )
    )

  for profile, expected_labels in ADDRESS_FORM_LABEL_SEEDED_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected_labels=expected_labels: assert_address_labels(
          page,
          expected_labels,
        ),
        profile=profile,
      )
    )


def test_checkout_autocomplete_cases_update_only_target_field_purpose():
  async def assert_address_autocomplete(
    page,
    *,
    expected_autocomplete_overrides: dict[str, str],
    expected_label_overrides: dict[str, str] | None = None,
  ):
    await _complete_checkout_to_address(page)

    assert await page.locator("h1", has_text="Shipping address").is_visible()
    assert await page.locator('[data-testid="address-form"]').is_visible()

    expected_labels = {
      "address-full-name": "Full name",
      "address-email": "Email",
      "address-street": "Street address",
      "address-city": "City",
      "address-state": "State",
      "address-country": "Country/region",
      "address-postal-code": "ZIP code",
    }
    expected_labels.update(expected_label_overrides or {})
    for test_id, label in expected_labels.items():
      assert await _label_for_matches_input_id(page, test_id)
      assert await _label_text_for_testid(page, test_id) == label

    expected_attributes = {
      "address-full-name": {
        "id": "address-fullName",
        "name": "fullName",
        "type": "text",
        "autocomplete": "name",
      },
      "address-email": {
        "id": "address-email",
        "name": "email",
        "type": "email",
        "autocomplete": "email",
      },
      "address-street": {
        "id": "address-streetAddress",
        "name": "streetAddress",
        "type": "text",
        "autocomplete": "street-address",
      },
      "address-city": {
        "id": "address-city",
        "name": "city",
        "type": "text",
        "autocomplete": "address-level2",
      },
      "address-state": {
        "id": "address-state",
        "name": "state",
        "type": "text",
        "autocomplete": "address-level1",
      },
      "address-country": {
        "id": "address-country",
        "name": "country",
        "type": None,
        "autocomplete": "country-name",
      },
      "address-postal-code": {
        "id": "address-postalCode",
        "name": "postalCode",
        "type": "text",
        "autocomplete": "postal-code",
      },
    }
    for test_id, autocomplete in expected_autocomplete_overrides.items():
      expected_attributes[test_id]["autocomplete"] = autocomplete

    assert await page.get_by_role("textbox", name="Street address").is_visible()
    assert await page.get_by_role("textbox", name="ZIP code").is_visible()
    assert (
      'textbox "City Required"'
      in await page.locator('[data-testid="address-city"]').aria_snapshot()
    )
    assert (
      'textbox "State Required"'
      in await page.locator('[data-testid="address-state"]').aria_snapshot()
    )
    for test_id, attributes in expected_attributes.items():
      control = page.locator(f'[data-testid="{test_id}"]')
      assert await control.get_attribute("id") == attributes["id"]
      assert await control.get_attribute("name") == attributes["name"]
      assert await control.get_attribute("type") == attributes["type"]
      assert (
        await control.get_attribute("autocomplete")
      ) == attributes["autocomplete"]
      assert await control.get_attribute("required") is not None
      assert await control.evaluate("node => node.validity.valueMissing") is (
        test_id != "address-country"
      )

    assert await page.locator('[data-testid="continue-to-payment"]').is_visible()

  async def assert_payment_autocomplete(
    page,
    *,
    expected_autocomplete_overrides: dict[str, str],
  ):
    await _complete_checkout_to_payment(page)

    assert await page.locator("h1", has_text="Payment").is_visible()
    assert await page.locator('[data-testid="payment-form"]').is_visible()
    assert await page.get_by_role("group", name="Card details").is_visible()

    expected_labels = {
      "payment-cardholder": "Cardholder name",
      "payment-card-number": "Card number",
      "payment-expiry": "Expiry",
      "payment-security-code": "Security code",
    }
    for test_id, label in expected_labels.items():
      assert await _label_for_matches_input_id(page, test_id)
      assert await _label_text_for_testid(page, test_id) == label

    expected_attributes = {
      "payment-cardholder": {
        "id": "payment-cardholder",
        "name": "cardholder",
        "type": "text",
        "autocomplete": "cc-name",
        "inputmode": None,
      },
      "payment-card-number": {
        "id": "payment-cardNumber",
        "name": "cardNumber",
        "type": "text",
        "autocomplete": "cc-number",
        "inputmode": "numeric",
      },
      "payment-expiry": {
        "id": "payment-expiry",
        "name": "expiry",
        "type": "text",
        "autocomplete": "cc-exp",
        "inputmode": "numeric",
      },
      "payment-security-code": {
        "id": "payment-securityCode",
        "name": "securityCode",
        "type": "text",
        "autocomplete": "cc-csc",
        "inputmode": "numeric",
      },
    }
    for test_id, autocomplete in expected_autocomplete_overrides.items():
      expected_attributes[test_id]["autocomplete"] = autocomplete

    assert await page.get_by_role("textbox", name="Card number").is_visible()
    assert (
      'textbox "Expiry Required"'
      in await page.locator('[data-testid="payment-expiry"]').aria_snapshot()
    )
    assert (
      'textbox "Security code Required"'
      in await page.locator('[data-testid="payment-security-code"]').aria_snapshot()
    )
    for test_id, attributes in expected_attributes.items():
      control = page.locator(f'[data-testid="{test_id}"]')
      assert await control.get_attribute("id") == attributes["id"]
      assert await control.get_attribute("name") == attributes["name"]
      assert await control.get_attribute("type") == attributes["type"]
      assert (
        await control.get_attribute("autocomplete")
      ) == attributes["autocomplete"]
      assert await control.get_attribute("inputmode") == attributes["inputmode"]
      assert await control.get_attribute("required") is not None
      assert await control.evaluate("node => node.validity.valueMissing")

    assert await page.locator('[data-testid="continue-to-review"]').is_visible()

  for profile, expected_label_overrides in AUTOCOMPLETE_BASELINE_PROFILE_CASES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_address_autocomplete(
          page,
          expected_autocomplete_overrides={},
          expected_label_overrides=expected_label_overrides,
        ),
        profile=profile,
      )
    )

  for profile in AUTOCOMPLETE_PAYMENT_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_payment_autocomplete(
          page,
          expected_autocomplete_overrides={},
        ),
        profile=profile,
      )
    )

  for profile, expected_autocomplete_overrides in AUTOCOMPLETE_PAYMENT_TARGET_PROFILE_CASES:
    asyncio.run(
      _with_checkout_page(
        lambda page, overrides=expected_autocomplete_overrides: assert_payment_autocomplete(
          page,
          expected_autocomplete_overrides=overrides,
        ),
        profile=profile,
      )
    )

  for profile, expected_autocomplete_overrides in AUTOCOMPLETE_TARGET_PROFILE_CASES:
    asyncio.run(
      _with_checkout_page(
        lambda page, overrides=expected_autocomplete_overrides: assert_address_autocomplete(
          page,
          expected_autocomplete_overrides=overrides,
          expected_label_overrides={},
        ),
        profile=profile,
      )
    )


def test_checkout_country_select_baseline_is_semantically_coherent():
  async def run(page):
    await _complete_checkout_to_address(page)

    country = page.locator('[data-testid="address-country"]')
    assert await country.evaluate("node => node.tagName.toLowerCase()") == "select"
    assert await country.get_attribute("id") == "address-country"
    assert await country.get_attribute("name") == "country"
    assert await country.get_attribute("autocomplete") == "country-name"
    assert await country.get_attribute("required") is not None
    assert await country.get_attribute("aria-label") is None
    assert await _label_for_matches_input_id(page, "address-country")
    assert await _label_text_for_testid(page, "address-country") == "Country/region"
    assert 'combobox "Country/region Required"' in await country.aria_snapshot()
    assert await country.input_value() == "United States"
    assert await country.locator("option").all_text_contents() == [
      "United States",
      "Canada",
      "Germany",
    ]

    await page.locator('[data-testid="continue-to-payment"]').click()
    assert page.url.endswith("/checkout/address")
    assert await page.locator('[data-testid="address-full-name"]').get_attribute(
      "aria-invalid"
    ) == "true"
    assert await country.get_attribute("aria-invalid") is None
    assert await country.input_value() == "United States"

  asyncio.run(_with_checkout_page(run))


def test_checkout_delivery_instructions_baseline_is_optional_and_blank_is_valid():
  async def run(page):
    await _complete_checkout_to_address(page)

    textarea = page.locator('[data-testid="address-delivery-instructions"]')
    assert await textarea.evaluate("node => node.tagName.toLowerCase()") == "textarea"
    assert await textarea.get_attribute("id") == "address-deliveryInstructions"
    assert await textarea.get_attribute("name") == "deliveryInstructions"
    assert await textarea.get_attribute("rows") == "3"
    assert await textarea.get_attribute("required") is None
    assert await textarea.get_attribute("aria-required") is None
    assert await textarea.get_attribute("autocomplete") is None
    assert await textarea.get_attribute("aria-describedby") == (
      "address-deliveryInstructions-description"
    )
    assert await _label_for_matches_input_id(page, "address-delivery-instructions")
    assert await _label_text_for_testid(
      page,
      "address-delivery-instructions",
    ) == "Delivery instructions"
    assert await page.get_by_role(
      "textbox",
      name="Delivery instructions",
      exact=True,
    ).is_visible()
    assert (
      (
        await page.locator(
          "#address-deliveryInstructions-description"
        ).text_content()
      )
      or ""
    ).strip() == (
      "Optional. Add gate codes, safe-place details, or delivery notes."
    )

    await _fill_testid_values(page, VALID_ADDRESS_VALUES)
    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_url("**/checkout/payment")
    await _fill_testid_values(page, VALID_PAYMENT_VALUES)
    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")

    assert await page.locator(
      '[data-testid="review-shipping-delivery-instructions"]'
    ).count() == 0

  asyncio.run(_with_checkout_page(run))


def test_checkout_delivery_instructions_label_case_preserves_textarea_behavior():
  async def run(page):
    delivery_instructions = "Leave package with concierge"
    await _complete_checkout_to_address(page)

    textarea = page.locator('[data-testid="address-delivery-instructions"]')
    street = page.locator('[data-testid="address-street"]')

    assert await _label_text_for_testid(
      page,
      "address-delivery-instructions",
    ) == "Street address"
    assert await _label_for_matches_input_id(page, "address-delivery-instructions")
    assert 'textbox "Street address"' in await textarea.aria_snapshot()
    assert await textarea.get_attribute("id") == "address-deliveryInstructions"
    assert await textarea.get_attribute("name") == "deliveryInstructions"
    assert await textarea.get_attribute("rows") == "3"
    assert await textarea.get_attribute("required") is None
    assert await textarea.get_attribute("aria-required") is None
    assert await textarea.get_attribute("autocomplete") is None
    assert await textarea.get_attribute("aria-describedby") == (
      "address-deliveryInstructions-description"
    )

    assert await _label_text_for_testid(page, "address-street") == (
      "Street address"
    )
    assert await street.get_attribute("id") == "address-streetAddress"
    assert await street.get_attribute("name") == "streetAddress"
    assert await street.get_attribute("autocomplete") == "street-address"
    assert await street.get_attribute("required") == ""
    assert 'textbox "Street address Required"' in await street.aria_snapshot()

    await textarea.fill(f"  {delivery_instructions}  ")
    await _fill_testid_values(page, VALID_ADDRESS_VALUES)
    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_url("**/checkout/payment")
    await _fill_testid_values(page, VALID_PAYMENT_VALUES)
    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")

    review_value = page.locator(
      '[data-testid="review-shipping-delivery-instructions"]'
    )
    assert await page.locator("dt", has_text="Delivery instructions").is_visible()
    assert ((await review_value.text_content()) or "").strip() == (
      delivery_instructions
    )

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-108"))


def test_checkout_delivery_instructions_persist_to_review_and_back_navigation():
  async def run(page):
    delivery_instructions = "Leave package with concierge"
    await _complete_checkout_to_address(page)
    textarea = page.locator('[data-testid="address-delivery-instructions"]')
    await textarea.fill(f"  {delivery_instructions}  ")
    await _fill_testid_values(page, VALID_ADDRESS_VALUES)
    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_url("**/checkout/payment")
    await _fill_testid_values(page, VALID_PAYMENT_VALUES)
    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")

    review_value = page.locator(
      '[data-testid="review-shipping-delivery-instructions"]'
    )
    assert await page.locator("dt", has_text="Delivery instructions").is_visible()
    assert ((await review_value.text_content()) or "").strip() == delivery_instructions

    await page.go_back()
    await page.wait_for_url("**/checkout/payment")
    await page.go_back()
    await page.wait_for_url("**/checkout/address")

    assert await textarea.input_value() == delivery_instructions
    assert await page.locator('[data-testid="address-street"]').input_value() == (
      VALID_ADDRESS_VALUES["address-street"]
    )

  asyncio.run(_with_checkout_page(run))


def test_checkout_selected_country_persists_to_review():
  async def run(page):
    await _complete_checkout_to_address(page)
    country = page.locator('[data-testid="address-country"]')
    await country.select_option(label="Germany")
    assert await country.input_value() == "Germany"

    await _fill_testid_values(page, VALID_ADDRESS_VALUES)
    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_url("**/checkout/payment")
    await _fill_testid_values(page, VALID_PAYMENT_VALUES)
    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")

    review_country = page.locator('[data-testid="review-shipping-country"]')
    assert await review_country.is_visible()
    assert (await review_country.text_content() or "").strip() == "Germany"
    assert "Portland, OR 97205" in (
      await page.locator('[data-testid="review-shipping-summary"]').inner_text()
    )

  asyncio.run(_with_checkout_page(run))


def test_checkout_country_label_case_preserves_country_behavior_to_review():
  async def run(page):
    await _complete_checkout_to_address(page)

    country = page.locator('[data-testid="address-country"]')
    assert await _label_text_for_testid(page, "address-country") == "State"
    assert 'combobox "State Required"' in await country.aria_snapshot()
    assert await country.get_attribute("name") == "country"
    assert await country.get_attribute("autocomplete") == "country-name"
    assert await country.locator("option").all_text_contents() == [
      "United States",
      "Canada",
      "Germany",
    ]

    state = page.locator('[data-testid="address-state"]')
    assert await _label_text_for_testid(page, "address-state") == "State"
    assert await state.get_attribute("name") == "state"
    assert await state.get_attribute("autocomplete") == "address-level1"

    await country.select_option(label="Germany")
    await _fill_testid_values(page, VALID_ADDRESS_VALUES)
    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_url("**/checkout/payment")
    await _fill_testid_values(page, VALID_PAYMENT_VALUES)
    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")
    assert (
      (
        await page.locator(
          '[data-testid="review-shipping-country"]'
        ).text_content()
      )
      or ""
    ).strip() == "Germany"

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-107"))


def test_checkout_country_autocomplete_case_preserves_country_behavior_to_review():
  async def run(page):
    await _complete_checkout_to_address(page)

    country = page.locator('[data-testid="address-country"]')
    assert await country.evaluate("node => node.tagName.toLowerCase()") == "select"
    assert await country.get_attribute("id") == "address-country"
    assert await country.get_attribute("name") == "country"
    assert await country.get_attribute("autocomplete") == "address-level1"
    assert await country.get_attribute("required") == ""
    assert await country.get_attribute("aria-label") is None
    assert await _label_for_matches_input_id(page, "address-country")
    assert await _label_text_for_testid(page, "address-country") == "Country/region"
    assert 'combobox "Country/region Required"' in await country.aria_snapshot()
    assert await country.input_value() == "United States"
    assert await country.locator("option").all_text_contents() == [
      "United States",
      "Canada",
      "Germany",
    ]

    state = page.locator('[data-testid="address-state"]')
    assert await state.get_attribute("id") == "address-state"
    assert await state.get_attribute("name") == "state"
    assert await state.get_attribute("type") == "text"
    assert await state.get_attribute("autocomplete") == "address-level1"
    assert await _label_text_for_testid(page, "address-state") == "State"
    assert 'textbox "State Required"' in await state.aria_snapshot()

    await country.select_option(label="Germany")
    await _fill_testid_values(page, VALID_ADDRESS_VALUES)
    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_url("**/checkout/payment")
    await _fill_testid_values(page, VALID_PAYMENT_VALUES)
    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")
    assert (
      (
        await page.locator(
          '[data-testid="review-shipping-country"]'
        ).text_content()
      )
      or ""
    ).strip() == "Germany"

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-126"))


def test_checkout_page_title_cases_update_only_target_routes():
  async def assert_products_title(page, *, expected_products_title: str):
    if not page.url.endswith("/products"):
      origin = await page.evaluate("window.location.origin")
      await page.goto(f"{origin}/products", wait_until="domcontentloaded")
    assert page.url.endswith("/products")
    assert await page.title() == expected_products_title
    assert await page.locator("h1", has_text="Products").is_visible()
    assert await page.locator('[data-testid="product-list"]').is_visible()
    assert await page.get_by_role("heading", name="Featured products").is_visible()
    assert await page.get_by_role("heading", name="Desk lamp").is_visible()
    assert await page.get_by_role("heading", name="Notebook set").is_visible()
    assert await page.get_by_role("heading", name="Cable organizer").is_visible()
    assert await page.get_by_role("button", name="Add Notebook set").is_visible()

  async def assert_address_title(page, *, expected_address_title: str):
    await assert_products_title(
      page,
      expected_products_title="Products | Brightlane Checkout",
    )

    await page.get_by_role("link", name="Cart").click()
    await page.wait_for_url("**/cart")
    assert await page.title() == "Cart | Brightlane Checkout"
    assert await page.locator("h1", has_text="Cart").is_visible()

    await page.locator('[data-testid="continue-to-address"]').click()
    await page.wait_for_url("**/checkout/address")

    assert page.url.endswith("/checkout/address")
    assert await page.title() == expected_address_title
    assert await page.locator("h1", has_text="Shipping address").is_visible()
    assert await page.get_by_role("heading", name="Shipping details").is_visible()
    assert await page.locator('[data-testid="address-form"]').is_visible()
    assert (
      await page.locator('[data-testid="checkout-progress-address"]').get_attribute(
        "aria-current",
      )
    ) == "step"
    assert (
      await page.locator('[data-testid="checkout-progress-cart"]').get_attribute(
        "aria-current",
      )
    ) is None
    assert (
      await page.locator('[data-testid="checkout-progress-payment"]').get_attribute(
        "aria-current",
      )
    ) is None

    expected_address_fields = {
      "address-full-name": ("Full name", "name"),
      "address-email": ("Email", "email"),
      "address-street": ("Street address", "street-address"),
      "address-city": ("City", "address-level2"),
      "address-state": ("State", "address-level1"),
      "address-country": ("Country/region", "country-name"),
      "address-postal-code": ("ZIP code", "postal-code"),
    }
    for test_id, (
      expected_label,
      expected_autocomplete,
    ) in expected_address_fields.items():
      assert await _label_for_matches_input_id(page, test_id)
      assert await _label_text_for_testid(page, test_id) == expected_label
      assert (
        await page.locator(f'[data-testid="{test_id}"]').get_attribute(
          "autocomplete",
        )
      ) == expected_autocomplete

    assert await page.get_by_role(
      "button",
      name="Continue to payment",
      exact=True,
    ).is_visible()

    await _fill_testid_values(page, VALID_ADDRESS_VALUES)
    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_url("**/checkout/payment")
    assert await page.title() == "Payment | Brightlane Checkout"

    await _fill_testid_values(page, VALID_PAYMENT_VALUES)
    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")
    assert await page.title() == "Review | Brightlane Checkout"

  async def assert_payment_title(page, *, expected_payment_title: str):
    await assert_products_title(
      page,
      expected_products_title="Products | Brightlane Checkout",
    )

    await page.get_by_role("link", name="Cart").click()
    await page.wait_for_url("**/cart")
    assert await page.title() == "Cart | Brightlane Checkout"
    assert await page.locator("h1", has_text="Cart").is_visible()

    await page.locator('[data-testid="continue-to-address"]').click()
    await page.wait_for_url("**/checkout/address")
    assert await page.title() == "Shipping address | Brightlane Checkout"
    assert await page.locator("h1", has_text="Shipping address").is_visible()

    await _fill_testid_values(page, VALID_ADDRESS_VALUES)
    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_url("**/checkout/payment")

    assert page.url.endswith("/checkout/payment")
    assert await page.title() == expected_payment_title
    assert await page.locator("h1", has_text="Payment").is_visible()
    assert await page.get_by_role("heading", name="Payment method").is_visible()
    assert await page.get_by_role("group", name="Card details").is_visible()
    assert (
      await page.locator('[data-testid="checkout-progress-payment"]').get_attribute(
        "aria-current",
      )
    ) == "step"

    expected_labels = {
      "payment-cardholder": "Cardholder name",
      "payment-card-number": "Card number",
      "payment-expiry": "Expiry",
      "payment-security-code": "Security code",
    }
    for test_id, expected_label in expected_labels.items():
      assert await _label_for_matches_input_id(page, test_id)
      assert await _label_text_for_testid(page, test_id) == expected_label

    assert await page.locator('[data-testid="continue-to-review"]').is_visible()
    assert await page.get_by_role(
      "button",
      name="Continue to review",
      exact=True,
    ).is_visible()

  for profile in PAGE_TITLE_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_payment_title(
          page,
          expected_payment_title="Payment | Brightlane Checkout",
        ),
        profile=profile,
      )
    )

  async def assert_cart_title_carried_to_address(page):
    await assert_address_title(
      page,
      expected_address_title="Cart | Brightlane Checkout",
    )

    origin = await page.evaluate("window.location.origin")
    await page.goto(f"{origin}/checkout/address", wait_until="domcontentloaded")
    assert await page.title() == "Shipping address | Brightlane Checkout"
    assert await page.locator("h1", has_text="Shipping address").is_visible()
    assert await page.locator('[data-testid="address-form"]').is_visible()

  asyncio.run(
    _with_checkout_page(
      assert_cart_title_carried_to_address,
      profile="checkout-co-sem-119",
    )
  )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_address_title(
        page,
        expected_address_title="Billing address | Brightlane Checkout",
      ),
      profile="checkout-co-sem-120",
    )
  )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_payment_title(
        page,
        expected_payment_title="Shipping address | Brightlane Checkout",
      ),
      profile="checkout-co-sem-060",
    )
  )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_payment_title(
        page,
        expected_payment_title="Review | Brightlane Checkout",
      ),
      profile="checkout-co-sem-121",
    )
  )

  async def assert_products_wrong_title_case(page, *, expected_products_title: str):
    await assert_products_title(
      page,
      expected_products_title=expected_products_title,
    )

    await page.get_by_role("link", name="Cart").click()
    await page.wait_for_url("**/cart")
    assert await page.title() == "Cart | Brightlane Checkout"
    assert await page.locator("h1", has_text="Cart").is_visible()

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_products_wrong_title_case(
        page,
        expected_products_title="Payment | Brightlane Checkout",
      ),
      profile="checkout-co-sem-058",
    )
  )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_products_wrong_title_case(
        page,
        expected_products_title="Weather Forecast | Brightlane Checkout",
      ),
      profile="checkout-co-sem-059",
    )
  )


def test_checkout_products_exposes_controlled_support_links():
  support_port = _find_free_port()
  support_origin = f"http://127.0.0.1:{support_port}"
  support_url = f"{support_origin}{RETURNS_SUPPORT_PATH}"
  shipping_url = f"{support_origin}{SHIPPING_INFORMATION_SUPPORT_PATH}"
  support_server = _start_static_http(CHECKOUT_SUPPORT_TARGET_DIR, port=support_port)
  try:
    _wait_for_url(support_url, timeout_seconds=20)
    _wait_for_url(shipping_url, timeout_seconds=20)

    async def run(page):
      link = page.locator('[data-testid="support-returns"]')
      shipping_link = page.locator('[data-testid="support-shipping"]')
      page_origin = await page.evaluate("window.location.origin")
      href = await link.get_attribute("href")

      assert await page.locator("h1", has_text="Products").is_visible()
      assert await page.get_by_role("heading", name="Shipping help").is_visible()
      assert await shipping_link.is_visible()
      assert ((await shipping_link.text_content()) or "").strip() == (
        "Shipping information"
      )
      assert await shipping_link.get_attribute("aria-label") is None
      assert await shipping_link.get_attribute("href") == shipping_url
      assert await page.get_by_role("link", name="Shipping information").is_visible()
      assert await link.is_visible()
      assert ((await link.text_content()) or "").strip() == "Returns and refunds"
      assert await link.get_attribute("aria-label") is None
      assert href == support_url
      assert urlparse(href).netloc != urlparse(page_origin).netloc
      assert await page.get_by_role("link", name="Returns and refunds").is_visible()

      await page.get_by_role("link", name="Cart").click()
      await page.wait_for_url("**/cart")
      assert await page.title() == "Cart | Brightlane Checkout"
      assert await page.locator("h1", has_text="Cart").is_visible()
      await page.get_by_role("link", name="Products").click()
      await page.wait_for_url("**/products")

      await shipping_link.click()
      await page.wait_for_url(shipping_url)
      assert await page.title() == "Shipping information"
      assert await page.locator("h1", has_text="Shipping information").is_visible()
      assert "shipping options" in ((await page.locator("main").inner_text()) or "")

      await page.go_back()
      await page.wait_for_url("**/products")

      await link.click()
      await page.wait_for_url(support_url)
      assert await page.title() == "Returns and refunds"
      assert await page.locator("h1", has_text="Returns and refunds").is_visible()

    asyncio.run(
      _with_checkout_page(
        run,
        support_origin=support_origin,
      )
    )
  finally:
    _stop_process(support_server)


def test_checkout_external_link_text_case_updates_support_label_only():
  support_port = _find_free_port()
  support_origin = f"http://127.0.0.1:{support_port}"
  support_url = f"{support_origin}{RETURNS_SUPPORT_PATH}"
  support_server = _start_static_http(CHECKOUT_SUPPORT_TARGET_DIR, port=support_port)
  try:
    _wait_for_url(support_url, timeout_seconds=20)

    async def assert_support_link(page, *, expected_label: str):
      link = page.locator('[data-testid="support-returns"]')
      cart_link = page.locator('[data-testid="nav-cart"]')

      assert await page.locator("h1", has_text="Products").is_visible()
      assert ((await cart_link.text_content()) or "").strip() == "Cart"
      assert await cart_link.get_attribute("href") == "/cart"
      assert ((await link.text_content()) or "").strip() == expected_label
      assert await link.get_attribute("aria-label") is None
      assert await link.get_attribute("href") == support_url
      assert f'link "{expected_label}"' in await link.aria_snapshot()

      await link.click()
      await page.wait_for_url(support_url)
      assert await page.title() == "Returns and refunds"
      assert await page.locator("h1", has_text="Returns and refunds").is_visible()

    asyncio.run(
      _with_checkout_page(
        lambda page: assert_support_link(
          page,
          expected_label="Returns and refunds",
        ),
        support_origin=support_origin,
      )
    )
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_support_link(
          page,
          expected_label="Shipping information",
        ),
        profile="checkout-co-sem-027",
        support_origin=support_origin,
      )
    )
  finally:
    _stop_process(support_server)


def test_checkout_shipping_destination_case_updates_href_only():
  support_port = _find_free_port()
  support_origin = f"http://127.0.0.1:{support_port}"
  returns_url = f"{support_origin}{RETURNS_SUPPORT_PATH}"
  shipping_url = f"{support_origin}{SHIPPING_INFORMATION_SUPPORT_PATH}"
  opaque_resource_url = f"{support_origin}{OPAQUE_SUPPORT_RESOURCE_PATH}"
  support_server = _start_static_http(CHECKOUT_SUPPORT_TARGET_DIR, port=support_port)
  try:
    _wait_for_url(returns_url, timeout_seconds=20)
    _wait_for_url(shipping_url, timeout_seconds=20)
    _wait_for_url(opaque_resource_url, timeout_seconds=20)

    async def assert_support_links(
      page,
      *,
      expected_shipping_href: str,
      expected_returns_label: str,
      follow_shipping: bool = False,
    ):
      shipping_topic = page.locator(".support-topic")
      shipping_link = page.locator('[data-testid="support-shipping"]')
      returns_link = page.locator('[data-testid="support-returns"]')

      assert await page.locator("h1", has_text="Products").is_visible()
      assert await shipping_topic.get_by_role(
        "heading",
        name="Shipping help",
      ).is_visible()
      assert "Learn about delivery times and available shipping options." in (
        (await shipping_topic.text_content()) or ""
      )
      assert await shipping_link.evaluate("node => node.tagName.toLowerCase()") == "a"
      assert ((await shipping_link.text_content()) or "").strip() == (
        "Shipping information"
      )
      assert await shipping_link.get_attribute("aria-label") is None
      assert 'link "Shipping information"' in await shipping_link.aria_snapshot()
      assert await shipping_link.get_attribute("href") == expected_shipping_href

      assert ((await returns_link.text_content()) or "").strip() == (
        expected_returns_label
      )
      assert await returns_link.get_attribute("href") == returns_url

      if follow_shipping:
        await shipping_link.click()
        await page.wait_for_url(returns_url)
        assert await page.title() == "Returns and refunds"
        assert await page.locator("h1", has_text="Returns and refunds").is_visible()

    asyncio.run(
      _with_checkout_page(
        lambda page: assert_support_links(
          page,
          expected_shipping_href=shipping_url,
          expected_returns_label="Returns and refunds",
        ),
        support_origin=support_origin,
      )
    )
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_support_links(
          page,
          expected_shipping_href=returns_url,
          expected_returns_label="Returns and refunds",
          follow_shipping=True,
        ),
        profile="checkout-co-sem-101",
        support_origin=support_origin,
      )
    )
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_support_links(
          page,
          expected_shipping_href=opaque_resource_url,
          expected_returns_label="Returns and refunds",
          follow_shipping=True,
        ),
        profile="checkout-co-sem-102",
        support_origin=support_origin,
      )
    )
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_support_links(
          page,
          expected_shipping_href=shipping_url,
          expected_returns_label="Shipping information",
        ),
        profile="checkout-co-sem-027",
        support_origin=support_origin,
      )
    )
    assert not any(
      semantic_hint in OPAQUE_SUPPORT_RESOURCE_PATH.lower()
      for semantic_hint in ("returns", "refund", "shipping", "delivery", "exchange")
    )
  finally:
    _stop_process(support_server)


def test_checkout_button_label_case_updates_notebook_add_label_only():
  async def assert_button_state(
    page,
    *,
    expected_accessible_name: str,
    expected_aria_label: str | None,
    expected_visible_text: str,
  ):
    notebook_add = page.locator('[data-testid="product-add-prod-notebook-set"]')
    notebook_card = page.locator('[data-testid="product-prod-notebook-set"]')
    desk_add = page.locator('[data-testid="product-add-prod-desk-lamp"]')
    cable_add = page.locator('[data-testid="product-add-prod-cable-organizer"]')
    cable_card = page.locator('[data-testid="product-prod-cable-organizer"]')

    assert await page.locator("h1", has_text="Products").is_visible()
    assert await notebook_add.is_visible()
    assert await notebook_add.evaluate("node => node.tagName.toLowerCase()") == "button"
    assert await notebook_add.get_attribute("type") == "button"
    assert ((await notebook_add.text_content()) or "").strip() == expected_visible_text
    assert await notebook_add.get_attribute("aria-label") == expected_aria_label
    assert await notebook_card.get_by_role(
      "button",
      name=expected_accessible_name,
    ).is_visible()
    assert ((await desk_add.text_content()) or "").strip() == "Add Desk lamp"
    assert await desk_add.get_attribute("aria-label") is None
    assert ((await cable_add.text_content()) or "").strip() == "Add Cable organizer"
    assert await cable_add.get_attribute("aria-label") is None
    assert await cable_card.get_by_role(
      "button",
      name="Add Cable organizer",
    ).is_visible()
    assert (
      (await page.locator('[data-testid="product-quantity-prod-notebook-set"]').text_content())
      or ""
    ).strip() == "Not in cart"
    assert (
      (
        await page.locator(
          '[data-testid="product-quantity-prod-cable-organizer"]',
        ).text_content()
      )
      or ""
    ).strip() == "Not in cart"
    assert (
      (await page.locator('[data-testid="cart-summary-count"]').text_content())
      or ""
    ).strip() == "1 item"

    await notebook_add.click()

    assert (
      (await page.locator('[data-testid="product-quantity-prod-notebook-set"]').text_content())
      or ""
    ).strip() == "In cart: 1 item"
    assert (
      (
        await page.locator(
          '[data-testid="product-quantity-prod-cable-organizer"]',
        ).text_content()
      )
      or ""
    ).strip() == "Not in cart"
    assert (
      (await page.locator('[data-testid="cart-summary-count"]').text_content())
      or ""
    ).strip() == "2 items"
    assert "Notebook set added to cart." in (
      (await page.locator('[data-testid="status-region"]').text_content()) or ""
    )
    assert await page.locator("h1", has_text="Products").is_visible()

  for profile in BUTTON_LABEL_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_button_state(
          page,
          expected_accessible_name="Add Notebook set",
          expected_aria_label=None,
          expected_visible_text="Add Notebook set",
        ),
        profile=profile,
      )
    )

  for profile, expected in BUTTON_LABEL_SEEDED_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected=expected: assert_button_state(
          page,
          expected_accessible_name=expected["accessible_name"],
          expected_aria_label=expected["aria_label"],
          expected_visible_text=expected["visible_text"],
        ),
        profile=profile,
      )
    )


def test_checkout_button_label_wrong_result_case_uses_real_shipping_dialog():
  async def assert_baseline_delivery_result(page):
    await page.get_by_role("link", name="Cart").click()
    await page.wait_for_url("**/cart")

    delivery_button = page.locator('[data-testid="delivery-estimate-trigger"]')
    delivery_panel = page.locator('[data-testid="delivery-estimate-panel"]')

    assert ((await delivery_button.text_content()) or "").strip() == "Delivery estimate"
    assert await delivery_button.get_attribute("aria-label") is None
    assert await delivery_button.get_attribute("aria-expanded") == "false"
    assert await delivery_panel.get_attribute("hidden") == ""
    assert await page.locator('[data-testid="shipping-information-dialog"]').count() == 0

    await delivery_button.click()

    assert await delivery_button.get_attribute("aria-expanded") == "true"
    assert await delivery_panel.is_visible()
    assert "Standard delivery usually arrives in 3-5 business days after dispatch." in (
      (await delivery_panel.text_content()) or ""
    )
    assert await page.locator('[data-testid="shipping-information-dialog"]').count() == 0
    assert await page.get_by_role("button", name="Shipping information").is_visible()

  async def assert_seeded_wrong_result(page):
    await page.get_by_role("link", name="Cart").click()
    await page.wait_for_url("**/cart")

    delivery_button = page.locator('[data-testid="delivery-estimate-trigger"]')
    delivery_panel = page.locator('[data-testid="delivery-estimate-panel"]')
    shipping_trigger = page.locator('[data-testid="shipping-information-trigger"]')

    assert ((await delivery_button.text_content()) or "").strip() == "Delivery estimate"
    assert await delivery_button.get_attribute("aria-label") is None
    assert await delivery_button.get_attribute("aria-expanded") == "false"
    assert await delivery_button.get_attribute("aria-controls") == "delivery-estimate-panel"
    assert await delivery_panel.get_attribute("hidden") == ""
    assert not await delivery_panel.is_visible()
    assert ((await shipping_trigger.text_content()) or "").strip() == "Shipping information"

    await delivery_button.click()

    dialog = page.get_by_role("dialog", name="Shipping information")
    dialog_by_testid = page.locator('[data-testid="shipping-information-dialog"]')
    assert await dialog.is_visible()
    assert await dialog_by_testid.get_attribute("role") == "dialog"
    assert await dialog_by_testid.get_attribute("aria-modal") == "true"
    assert (
      await dialog_by_testid.get_attribute("aria-labelledby")
    ) == "shipping-information-title"
    assert (
      (await page.locator("#shipping-information-title").text_content()) or ""
    ).strip() == "Shipping information"
    assert "Standard shipping is calculated during checkout." in (
      (await dialog.text_content()) or ""
    )
    assert await delivery_button.get_attribute("aria-expanded") == "false"
    assert await delivery_panel.get_attribute("hidden") == ""
    assert not await delivery_panel.is_visible()
    assert await page.locator('[data-testid="continue-to-address"]').is_visible()

    await page.get_by_role("button", name="Close").click()
    assert await page.locator('[data-testid="shipping-information-dialog"]').count() == 0
    await page.wait_for_function(
      "() => document.activeElement?.dataset?.testid === 'delivery-estimate-trigger'",
    )

    await shipping_trigger.click()
    assert await dialog.is_visible()
    await page.get_by_role("button", name="Close").click()
    assert await page.locator('[data-testid="shipping-information-dialog"]').count() == 0
    await page.wait_for_function(
      "() => document.activeElement?.dataset?.testid === 'shipping-information-trigger'",
    )

  for profile in BUTTON_LABEL_WRONG_RESULT_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        assert_baseline_delivery_result,
        profile=profile,
      )
    )

  asyncio.run(
    _with_checkout_page(
      assert_seeded_wrong_result,
      profile="checkout-co-sem-089",
    )
  )


def test_checkout_continue_to_payment_wrong_result_preserves_button_contract():
  async def submit_address(page, *, expected_route: str, expected_title: str):
    await page.get_by_role("link", name="Cart").click()
    await page.wait_for_url("**/cart")
    await page.locator('[data-testid="continue-to-address"]').click()
    await page.wait_for_url("**/checkout/address")

    button = page.locator('[data-testid="continue-to-payment"]')
    assert ((await button.text_content()) or "").strip() == "Continue to payment"
    assert await button.get_attribute("type") == "submit"
    assert await button.get_attribute("aria-label") is None
    assert not await button.is_disabled()
    assert await page.get_by_role(
      "button",
      name="Continue to payment",
      exact=True,
    ).is_visible()
    assert (
      await page.locator('[data-testid="checkout-progress-address"]').get_attribute(
        "aria-current",
      )
    ) == "step"

    await _fill_testid_values(page, VALID_ADDRESS_VALUES)
    await button.click()
    await page.wait_for_url(f"**{expected_route}")
    assert await page.title() == expected_title

  async def assert_baseline(page):
    await submit_address(
      page,
      expected_route="/checkout/payment",
      expected_title="Payment | Brightlane Checkout",
    )
    assert await page.locator("h1", has_text="Payment").is_visible()
    assert await page.locator('[data-testid="payment-form"]').is_visible()

  async def assert_seeded(page):
    await submit_address(
      page,
      expected_route="/cart",
      expected_title="Cart | Brightlane Checkout",
    )
    assert await page.locator("h1", has_text="Cart").is_visible()
    assert await page.locator('[data-testid="cart-list"]').is_visible()
    assert await page.get_by_role(
      "button",
      name="Continue to address",
      exact=True,
    ).is_visible()

  asyncio.run(_with_checkout_page(assert_baseline, profile="checkout-clean-v1"))
  asyncio.run(_with_checkout_page(assert_seeded, profile="checkout-co-sem-103"))


def test_checkout_cart_increment_wrong_object_result_preserves_button_contract():
  async def assert_result(
    page,
    *,
    expected_desk_quantity: str,
    expected_notebook_quantity: str,
    verify_notebook_control: bool = False,
  ):
    await page.locator('[data-testid="product-add-prod-notebook-set"]').click()
    assert (
      (
        await page.locator(
          '[data-testid="product-quantity-prod-notebook-set"]'
        ).text_content()
      )
      or ""
    ).strip() == "In cart: 1 item"

    await page.locator('[data-testid="nav-cart"]').click()
    await page.wait_for_url("**/cart")

    desk_quantity = page.locator('[data-testid="cart-quantity-prod-desk-lamp"]')
    notebook_quantity = page.locator(
      '[data-testid="cart-quantity-prod-notebook-set"]'
    )
    desk_increment = page.locator(
      '[data-testid="cart-increment-prod-desk-lamp"]'
    )
    notebook_increment = page.locator(
      '[data-testid="cart-increment-prod-notebook-set"]'
    )

    assert ((await desk_quantity.text_content()) or "").strip() == "1"
    assert ((await notebook_quantity.text_content()) or "").strip() == "1"
    assert await desk_increment.evaluate("node => node.tagName.toLowerCase()") == "button"
    assert await desk_increment.get_attribute("type") == "button"
    assert ((await desk_increment.text_content()) or "").strip() == "+"
    assert await desk_increment.get_attribute("aria-label") == (
      "Increase Desk lamp quantity"
    )
    assert not await desk_increment.is_disabled()
    assert await page.get_by_role(
      "button",
      name="Increase Desk lamp quantity",
      exact=True,
    ).is_visible()

    await desk_increment.click()
    assert ((await desk_quantity.text_content()) or "").strip() == expected_desk_quantity
    assert ((await notebook_quantity.text_content()) or "").strip() == (
      expected_notebook_quantity
    )
    assert page.url.endswith("/cart")
    assert await page.title() == "Cart | Brightlane Checkout"
    assert await page.locator("h1", has_text="Cart").is_visible()

    if verify_notebook_control:
      assert await notebook_increment.get_attribute("aria-label") == (
        "Increase Notebook set quantity"
      )
      await notebook_increment.click()
      assert ((await desk_quantity.text_content()) or "").strip() == "1"
      assert ((await notebook_quantity.text_content()) or "").strip() == "3"

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_result(
        page,
        expected_desk_quantity="2",
        expected_notebook_quantity="1",
      ),
      profile="checkout-clean-v1",
    )
  )
  asyncio.run(
    _with_checkout_page(
      lambda page: assert_result(
        page,
        expected_desk_quantity="1",
        expected_notebook_quantity="2",
        verify_notebook_control=True,
      ),
      profile="checkout-co-sem-104",
    )
  )


def test_checkout_link_text_case_updates_cart_nav_label_only():
  async def assert_nav_state(
    page,
    *,
    expected_accessible_name: str,
    expected_aria_label: str | None,
    expected_visible_text: str,
  ):
    products_link = page.locator('[data-testid="nav-products"]')
    cart_link = page.locator('[data-testid="nav-cart"]')

    assert ((await products_link.text_content()) or "").strip() == "Products"
    assert ((await cart_link.text_content()) or "").strip() == expected_visible_text
    assert await cart_link.get_attribute("href") == "/cart"
    assert await cart_link.get_attribute("aria-label") == expected_aria_label
    assert await page.get_by_role("link", name=expected_accessible_name).is_visible()

    await cart_link.click()
    await page.wait_for_url("**/cart")
    assert await page.title() == "Cart | Brightlane Checkout"
    assert await page.locator("h1", has_text="Cart").is_visible()
    assert await page.locator('[data-testid="cart-list"]').is_visible()

  for profile in LINK_TEXT_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_nav_state(
          page,
          expected_accessible_name="Cart",
          expected_aria_label=None,
          expected_visible_text="Cart",
        ),
        profile=profile,
      )
    )

  for profile, expected in LINK_TEXT_SEEDED_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected=expected: assert_nav_state(
          page,
          expected_accessible_name=expected["accessible_name"],
          expected_aria_label=expected["aria_label"],
          expected_visible_text=expected["visible_text"],
        ),
        profile=profile,
      )
    )


def test_checkout_link_destination_case_updates_products_destination_only():
  async def assert_nav_state(page, *, expected_products_destination: str):
    navigation = page.get_by_role("navigation", name="Checkout routes")
    products_link = page.locator('[data-testid="nav-products"]')
    cart_link = page.locator('[data-testid="nav-cart"]')

    assert await navigation.is_visible()
    assert ((await products_link.text_content()) or "").strip() == "Products"
    assert await products_link.get_attribute("aria-label") is None
    assert await products_link.get_attribute("href") == expected_products_destination
    assert await page.get_by_role("link", name="Products", exact=True).is_visible()
    assert ((await cart_link.text_content()) or "").strip() == "Cart"
    assert await cart_link.get_attribute("aria-label") is None
    assert await cart_link.get_attribute("href") == "/cart"
    assert await page.get_by_role("link", name="Cart", exact=True).is_visible()
    assert await page.title() == "Products | Brightlane Checkout"
    assert await page.locator("h1", has_text="Products").is_visible()

    if expected_products_destination == "/cart":
      await products_link.click()
      await page.wait_for_url("**/cart")
      assert await page.title() == "Cart | Brightlane Checkout"
      assert await page.locator("h1", has_text="Cart").is_visible()
      assert await page.locator('[data-testid="cart-list"]').is_visible()

  for profile in LINK_TEXT_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_nav_state(
          page,
          expected_products_destination="/products",
        ),
        profile=profile,
      )
    )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_nav_state(
        page,
        expected_products_destination="/cart",
      ),
      profile="checkout-co-sem-100",
    )
  )


def test_checkout_aria_current_stale_navigation_case_updates_current_state_only():
  async def assert_nav_current_state(page, *, seeded: bool) -> None:
    products_link = page.locator('[data-testid="nav-products"]')
    cart_link = page.locator('[data-testid="nav-cart"]')

    assert await page.title() == "Products | Brightlane Checkout"
    assert await page.locator("h1", has_text="Products").is_visible()
    assert await page.locator('[data-testid="route-products"]').is_visible()
    assert ((await products_link.text_content()) or "").strip() == "Products"
    assert ((await cart_link.text_content()) or "").strip() == "Cart"
    assert await products_link.get_attribute("href") == "/products"
    assert await cart_link.get_attribute("href") == "/cart"
    assert await products_link.get_attribute("aria-label") is None
    assert await cart_link.get_attribute("aria-label") is None
    assert await products_link.get_attribute("aria-current") == "page"
    assert await cart_link.get_attribute("aria-current") is None

    await cart_link.click()
    await page.wait_for_url("**/cart")

    assert page.url.endswith("/cart")
    assert await page.title() == "Cart | Brightlane Checkout"
    assert await page.locator("h1", has_text="Cart").is_visible()
    assert await page.locator('[data-testid="cart-list"]').is_visible()
    assert ((await products_link.text_content()) or "").strip() == "Products"
    assert ((await cart_link.text_content()) or "").strip() == "Cart"
    assert await products_link.get_attribute("href") == "/products"
    assert await cart_link.get_attribute("href") == "/cart"
    assert await products_link.get_attribute("aria-label") is None
    assert await cart_link.get_attribute("aria-label") is None
    assert "active" not in ((await products_link.get_attribute("class")) or "").split()
    assert "active" in ((await cart_link.get_attribute("class")) or "").split()

    if seeded:
      assert await products_link.get_attribute("aria-current") == "page"
      assert await cart_link.get_attribute("aria-current") is None
    else:
      assert await products_link.get_attribute("aria-current") is None
      assert await cart_link.get_attribute("aria-current") == "page"

  for profile in ARIA_CURRENT_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_nav_current_state(page, seeded=False),
        profile=profile,
      )
    )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_nav_current_state(page, seeded=True),
      profile="checkout-co-sem-090",
    )
  )


def test_checkout_products_language_switch_updates_copy_and_root_lang():
  async def assert_english_products(page):
    route_text = (
      (await page.locator('[data-testid="route-products"]').inner_text()) or ""
    )

    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.title() == "Products | Brightlane Checkout"
    assert await page.locator("h1", has_text="Products").is_visible()
    assert "Browse featured products and update the cart summary." in route_text
    assert "Featured products" in route_text
    assert "Desk accessories" in route_text
    assert "Add Desk lamp" in route_text
    assert "Cart summary" in route_text
    assert "Checkout Flow" in ((await page.locator(".app-header").inner_text()) or "")
    assert await page.get_by_role("navigation", name="Checkout routes").is_visible()
    assert await page.get_by_role("link", name="Products").is_visible()
    assert await page.get_by_role("link", name="Cart").is_visible()
    assert await page.get_by_role("group", name="Products language").is_visible()
    assert await page.get_by_role("button", name="English").is_visible()
    assert await page.get_by_role("button", name="Spanish").is_visible()
    assert "Support" in route_text
    assert "Shipping help" in route_text
    assert "Learn about delivery times and available shipping options." in route_text
    assert "Shipping information" in route_text
    assert "Returns and refunds" in route_text
    assert "Demo checkout experience" in (
      (await page.locator(".app-footer").inner_text()) or ""
    )
    assert (
      await page.locator('[data-testid="products-language-en"]').get_attribute(
        "aria-pressed"
      )
      == "true"
    )
    assert (
      await page.locator('[data-testid="products-language-es"]').get_attribute(
        "aria-pressed"
      )
      == "false"
    )

  async def assert_spanish_products(page):
    route_text = (
      (await page.locator('[data-testid="route-products"]').inner_text()) or ""
    )

    assert await page.evaluate("document.documentElement.lang") == "es"
    assert await page.title() == "Productos | Brightlane Checkout"
    assert await page.locator("h1", has_text="Productos").is_visible()
    assert "Explora productos destacados y actualiza el resumen del carrito." in route_text
    assert "Productos destacados" in route_text
    assert "Accesorios de escritorio" in route_text
    assert "Agregar Lámpara de escritorio" in route_text
    assert "Resumen del carrito" in route_text
    assert "Flujo de compra" in ((await page.locator(".app-header").inner_text()) or "")
    assert await page.get_by_role("navigation", name="Rutas de compra").is_visible()
    assert await page.get_by_role("link", name="Productos").is_visible()
    assert await page.get_by_role("link", name="Carrito").is_visible()
    assert await page.get_by_role("group", name="Idioma de productos").is_visible()
    assert await page.get_by_role("button", name="Inglés").is_visible()
    assert await page.get_by_role("button", name="Español").is_visible()
    assert "Ayuda" in route_text
    assert "Ayuda con el envío" in route_text
    assert (
      "Consulta los plazos de entrega y las opciones de envío disponibles."
      in route_text
    )
    assert "Información de envío" in route_text
    assert "Devoluciones y reembolsos" in route_text
    assert "Experiencia de compra de demostración" in (
      (await page.locator(".app-footer").inner_text()) or ""
    )
    assert (
      await page.locator('[data-testid="products-language-en"]').get_attribute(
        "aria-pressed"
      )
      == "false"
    )
    assert (
      await page.locator('[data-testid="products-language-es"]').get_attribute(
        "aria-pressed"
      )
      == "true"
    )

  async def run(page):
    english_button = page.locator('[data-testid="products-language-en"]')
    spanish_button = page.locator('[data-testid="products-language-es"]')

    assert await english_button.is_visible()
    assert await spanish_button.is_visible()
    await assert_english_products(page)

    await spanish_button.click()
    await assert_spanish_products(page)

    await page.get_by_role("link", name="Carrito").click()
    await page.wait_for_url("**/cart")
    assert await page.evaluate("document.documentElement.lang") == "es"
    assert await page.title() == "Carrito | Brightlane Checkout"
    assert await page.locator("h1", has_text="Carrito").is_visible()
    assert "Artículos del carrito" in (
      (await page.locator('[data-testid="route-cart"]').inner_text()) or ""
    )

    await page.get_by_role("link", name="Productos").click()
    await page.wait_for_url("**/products")
    await assert_spanish_products(page)

    await english_button.click()
    await assert_english_products(page)

  asyncio.run(_with_checkout_page(run))


def test_checkout_language_switch_case_keeps_root_lang_stale_after_spanish_selection():
  async def run(page):
    english_button = page.locator('[data-testid="products-language-en"]')
    spanish_button = page.locator('[data-testid="products-language-es"]')

    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.locator("h1", has_text="Products").is_visible()
    assert "Add Desk lamp" in (
      (await page.locator('[data-testid="route-products"]').inner_text()) or ""
    )
    assert await english_button.get_attribute("aria-pressed") == "true"

    await spanish_button.click()
    spanish_text = (
      (await page.locator('[data-testid="route-products"]').inner_text()) or ""
    )

    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.locator("h1", has_text="Productos").is_visible()
    assert "Flujo de compra" in ((await page.locator(".app-header").inner_text()) or "")
    assert await page.get_by_role("link", name="Carrito").is_visible()
    assert "Explora productos destacados y actualiza el resumen del carrito." in spanish_text
    assert "Agregar Lámpara de escritorio" in spanish_text
    assert await spanish_button.get_attribute("aria-pressed") == "true"

    await page.get_by_role("link", name="Carrito").click()
    await page.wait_for_url("**/cart")
    assert await page.evaluate("document.documentElement.lang") == "es"
    assert await page.locator("h1", has_text="Carrito").is_visible()

    await page.get_by_role("link", name="Productos").click()
    await page.wait_for_url("**/products")
    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.locator("h1", has_text="Productos").is_visible()

    await english_button.click()
    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.locator("h1", has_text="Products").is_visible()
    assert "Add Desk lamp" in (
      (await page.locator('[data-testid="route-products"]').inner_text()) or ""
    )

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-015"))


def test_checkout_language_switch_back_case_keeps_only_root_lang_stale():
  async def run(page, *, expected_final_root_lang: str):
    english_button = page.locator('[data-testid="products-language-en"]')
    spanish_button = page.locator('[data-testid="products-language-es"]')

    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.title() == "Products | Brightlane Checkout"
    assert await page.locator("h1", has_text="Products").is_visible()
    assert await english_button.get_attribute("aria-pressed") == "true"
    assert await spanish_button.get_attribute("aria-pressed") == "false"

    await spanish_button.click()
    spanish_text = (
      (await page.locator('[data-testid="route-products"]').inner_text()) or ""
    )
    assert await page.evaluate("document.documentElement.lang") == "es"
    assert await page.title() == "Productos | Brightlane Checkout"
    assert await page.locator("h1", has_text="Productos").is_visible()
    assert "Explora productos destacados y actualiza el resumen del carrito." in spanish_text
    assert await english_button.get_attribute("aria-pressed") == "false"
    assert await spanish_button.get_attribute("aria-pressed") == "true"

    await english_button.click()
    english_text = (
      (await page.locator('[data-testid="route-products"]').inner_text()) or ""
    )
    assert await page.evaluate("document.documentElement.lang") == expected_final_root_lang
    assert await page.title() == "Products | Brightlane Checkout"
    assert await page.locator("h1", has_text="Products").is_visible()
    assert "Browse featured products and update the cart summary." in english_text
    assert "Featured products" in english_text
    assert "Desk accessories" in english_text
    assert "Office supplies" in english_text
    assert "Desk lamp" in english_text
    assert "Notebook set" in english_text
    assert "Cable organizer" in english_text
    assert "Add Desk lamp" in english_text
    assert "Explora productos destacados y actualiza el resumen del carrito." not in english_text
    assert "Productos destacados" not in english_text
    assert "Flujo de compra" not in (
      (await page.locator(".app-header").inner_text()) or ""
    )
    assert "Checkout Flow" in (
      (await page.locator(".app-header").inner_text()) or ""
    )
    assert await page.get_by_role("navigation", name="Checkout routes").is_visible()
    assert await page.get_by_role("link", name="Products").is_visible()
    assert await page.get_by_role("link", name="Cart").is_visible()
    assert await page.get_by_role("group", name="Products language").is_visible()
    assert await page.get_by_role("button", name="English").is_visible()
    assert await page.get_by_role("button", name="Spanish").is_visible()
    assert await english_button.get_attribute("aria-pressed") == "true"
    assert await spanish_button.get_attribute("aria-pressed") == "false"
    assert await page.locator('[data-testid="products-description"]').get_attribute(
      "lang"
    ) is None

    await page.get_by_role("link", name="Cart").click()
    await page.wait_for_url("**/cart")
    assert await page.evaluate("document.documentElement.lang") == "en"

  async def run_clean(page):
    await run(page, expected_final_root_lang="en")

  async def run_seeded(page):
    await run(page, expected_final_root_lang="es")

  asyncio.run(_with_checkout_page(run_clean))
  asyncio.run(_with_checkout_page(run_seeded, profile="checkout-co-sem-137"))


def test_checkout_products_description_local_language_case_is_scoped():
  async def assert_description_state(
    page,
    *,
    expected_root_lang: str,
    expected_text: str,
    expected_local_lang: str | None,
    expected_add_label: str = "Add Desk lamp",
    expected_image_alt: str = DESK_LAMP_BASELINE_ALT,
    expected_cart_summary_lang: str | None = None,
  ):
    description = page.locator('[data-testid="products-description"]')

    assert await description.is_visible()
    assert ((await description.text_content()) or "").strip() == expected_text
    assert await description.get_attribute("lang") == expected_local_lang
    assert await page.evaluate("document.documentElement.lang") == expected_root_lang
    assert await page.locator("#product-list-heading").get_attribute("lang") is None
    assert await page.locator('[data-testid="products-list-region"]').get_attribute("lang") is None
    assert await page.locator('[data-testid="product-category-browser"]').get_attribute("lang") is None
    cart_summary = page.locator('[data-testid="cart-summary"]')
    assert await cart_summary.get_attribute("lang") == expected_cart_summary_lang
    assert await page.locator('[data-testid="product-image-prod-desk-lamp"]').get_attribute(
      "alt"
    ) == expected_image_alt
    assert (
      (await page.locator('[data-testid="product-add-prod-desk-lamp"]').text_content())
      or ""
    ).strip() == expected_add_label

  async def assert_baseline_english(page, *, expected_root_lang: str):
    await assert_description_state(
      page,
      expected_root_lang=expected_root_lang,
      expected_text="Browse featured products for your workspace.",
      expected_local_lang=None,
    )

  async def assert_static_spanish(page):
    await page.locator('[data-testid="products-language-es"]').click()
    await assert_description_state(
      page,
      expected_root_lang="en",
      expected_text="Explora productos destacados para tu espacio de trabajo.",
      expected_local_lang=None,
      expected_add_label="Agregar Lámpara de escritorio",
      expected_image_alt=DESK_LAMP_SPANISH_ALT,
    )

  async def assert_dynamic_spanish_stale_root(page):
    await page.locator('[data-testid="products-language-es"]').click()
    await assert_description_state(
      page,
      expected_root_lang="en",
      expected_text="Explora productos destacados para tu espacio de trabajo.",
      expected_local_lang=None,
      expected_add_label="Agregar Lámpara de escritorio",
      expected_image_alt=DESK_LAMP_SPANISH_ALT,
    )

  async def assert_seeded_local_language(page):
    await assert_description_state(
      page,
      expected_root_lang="en",
      expected_text="Browse featured products for your workspace.",
      expected_local_lang="fr",
    )
    assert await page.locator("h1", has_text="Products").is_visible()
    assert "Browse featured products and update the cart summary." in (
      (await page.locator('[data-testid="route-products"]').inner_text()) or ""
    )

  async def assert_seeded_cart_summary_language(page):
    await assert_description_state(
      page,
      expected_root_lang="en",
      expected_text="Browse featured products for your workspace.",
      expected_local_lang=None,
      expected_cart_summary_lang="de",
    )
    cart_summary_text = (
      (await page.locator('[data-testid="cart-summary"]').inner_text()) or ""
    )
    assert "Cart summary" in cart_summary_text
    assert "Items" in cart_summary_text
    assert "1 item" in cart_summary_text
    assert "Order total" in cart_summary_text

  async def assert_dynamic_spanish_stale_local_language(page):
    await assert_description_state(
      page,
      expected_root_lang="en",
      expected_text="Browse featured products for your workspace.",
      expected_local_lang="en",
    )
    await page.locator('[data-testid="products-language-es"]').click()
    await assert_description_state(
      page,
      expected_root_lang="es",
      expected_text="Explora productos destacados para tu espacio de trabajo.",
      expected_local_lang="en",
      expected_add_label="Agregar Lámpara de escritorio",
      expected_image_alt=DESK_LAMP_SPANISH_ALT,
    )
    assert await page.locator("h1", has_text="Productos").is_visible()

    await page.locator('[data-testid="products-language-en"]').click()
    await assert_description_state(
      page,
      expected_root_lang="en",
      expected_text="Browse featured products for your workspace.",
      expected_local_lang="en",
    )
    assert await page.locator("h1", has_text="Products").is_visible()

  for profile in (None, "checkout-clean-v1", "checkout-unknown-profile"):
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_baseline_english(page, expected_root_lang="en"),
        profile=profile,
      )
    )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_baseline_english(page, expected_root_lang="da"),
      profile="checkout-co-sem-011",
    )
  )
  asyncio.run(_with_checkout_page(assert_static_spanish, profile="checkout-co-sem-012"))
  asyncio.run(
    _with_checkout_page(
      assert_dynamic_spanish_stale_root,
      profile="checkout-co-sem-015",
    )
  )
  asyncio.run(
    _with_checkout_page(
      assert_seeded_local_language,
      profile="checkout-co-sem-016",
    )
  )
  asyncio.run(
    _with_checkout_page(
      assert_seeded_cart_summary_language,
      profile="checkout-co-sem-017",
    )
  )
  asyncio.run(
    _with_checkout_page(
      assert_dynamic_spanish_stale_local_language,
      profile="checkout-co-sem-019",
    )
  )


def test_checkout_cart_description_local_language_case_is_scoped():
  async def assert_cart_description_state(
    page,
    *,
    expected_local_lang: str | None,
  ):
    await page.get_by_role("link", name="Cart").click()
    await page.wait_for_url("**/cart")

    description = page.locator('[data-testid="cart-description"]')

    assert await description.is_visible()
    assert (
      (await description.text_content()) or ""
    ).strip() == "Review selected products before entering checkout details."
    assert await description.get_attribute("lang") == expected_local_lang
    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.locator('[data-testid="cart-list"]').get_attribute("lang") is None
    assert await page.locator('[data-testid="cart-totals-region"]').get_attribute("lang") is None
    assert await page.locator('[data-testid="cart-summary"]').get_attribute("lang") is None
    assert await page.locator('[data-testid="delivery-estimate-trigger"]').get_attribute("lang") is None
    assert await page.locator('[data-testid="shipping-information-trigger"]').get_attribute("lang") is None
    assert await page.locator('[data-testid="continue-to-address"]').is_visible()

  for profile in (None, "checkout-clean-v1", "checkout-co-sem-017"):
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_cart_description_state(page, expected_local_lang=None),
        profile=profile,
      )
    )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_cart_description_state(page, expected_local_lang="fr"),
      profile="checkout-co-sem-018",
    )
  )


def test_checkout_shipping_information_dialog_local_language_case_is_scoped():
  spanish_body = (
    "El envío estándar se calcula durante la compra. Los detalles de entrega "
    "se confirman después de ingresar la dirección de envío."
  )

  async def assert_dialog_state(page, *, expected_local_lang: str | None):
    spanish_control = page.locator('[data-testid="products-language-es"]')
    english_control = page.locator('[data-testid="products-language-en"]')
    assert await spanish_control.get_attribute("aria-pressed") == "false"
    assert await english_control.get_attribute("aria-pressed") == "true"

    await spanish_control.click()
    assert await spanish_control.get_attribute("aria-pressed") == "true"
    assert await english_control.get_attribute("aria-pressed") == "false"
    assert await page.evaluate("document.documentElement.lang") == "es"
    assert await page.locator("h1", has_text="Productos").is_visible()

    await page.get_by_role("link", name="Carrito").click()
    await page.wait_for_url("**/cart")
    assert await page.evaluate("document.documentElement.lang") == "es"
    assert await page.locator("h1", has_text="Carrito").is_visible()

    trigger = page.locator('[data-testid="shipping-information-trigger"]')
    assert ((await trigger.text_content()) or "").strip() == "Información de envío"
    await trigger.click()

    dialog_by_testid = page.locator('[data-testid="shipping-information-dialog"]')
    dialog = page.get_by_role("dialog", name="Información de envío")
    body = page.locator('[data-testid="shipping-information-body"]')
    close_button = page.get_by_role("button", name="Cerrar")
    assert await dialog.is_visible()
    assert await dialog_by_testid.get_attribute("role") == "dialog"
    assert await dialog_by_testid.get_attribute("aria-modal") == "true"
    assert (
      await dialog_by_testid.get_attribute("aria-labelledby")
    ) == "shipping-information-title"
    assert (
      (await page.locator("#shipping-information-title").text_content()) or ""
    ).strip() == "Información de envío"
    assert ((await body.text_content()) or "").strip() == spanish_body
    assert await body.get_attribute("lang") == expected_local_lang
    assert await body.evaluate(
      "node => node.closest('[lang]')?.getAttribute('lang')",
    ) == (expected_local_lang or "es")
    assert await page.evaluate("document.documentElement.lang") == "es"

    assert await dialog_by_testid.get_attribute("lang") is None
    assert await page.locator("#shipping-information-title").get_attribute("lang") is None
    assert await close_button.get_attribute("lang") is None
    assert await page.locator('[data-testid="cart-description"]').get_attribute("lang") is None
    assert await page.locator('[data-testid="cart-list"]').get_attribute("lang") is None

    await close_button.click()
    assert await dialog_by_testid.count() == 0
    await page.wait_for_function(
      "() => document.activeElement?.dataset?.testid === 'shipping-information-trigger'",
    )
    await page.get_by_role("link", name="Productos").click()
    await page.wait_for_url("**/products")
    assert await spanish_control.get_attribute("aria-pressed") == "true"
    assert await english_control.get_attribute("aria-pressed") == "false"
    assert await page.evaluate("document.documentElement.lang") == "es"

  for profile in (None, "checkout-clean-v1", "checkout-co-sem-019"):
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_dialog_state(page, expected_local_lang=None),
        profile=profile,
      )
    )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_dialog_state(page, expected_local_lang="en"),
      profile="checkout-co-sem-138",
    )
  )


def test_checkout_image_alt_cases_override_only_products_desk_lamp_image_alt():
  async def assert_baseline_alt(page):
    image = page.locator('[data-testid="product-image-prod-desk-lamp"]')
    notebook_image = page.locator(
      '[data-testid="product-image-prod-notebook-set"]'
    )

    assert await image.is_visible()
    assert (await image.get_attribute("src") or "").endswith("/desk-lamp.svg")
    assert await image.get_attribute("alt") == DESK_LAMP_BASELINE_ALT
    assert await notebook_image.is_visible()
    assert (await notebook_image.get_attribute("src") or "").endswith(
      "/notebook-set.svg"
    )
    assert await notebook_image.get_attribute("alt") == NOTEBOOK_SET_BASELINE_ALT
    assert await page.locator('[data-testid="product-prod-desk-lamp"]').is_visible()
    assert (
      (await page.locator("#product-title-prod-desk-lamp").text_content()) or ""
    ).strip() == "Desk lamp"
    assert (
      (await page.locator('[data-testid="product-add-prod-desk-lamp"]').text_content())
      or ""
    ).strip() == "Add Desk lamp"
    assert await page.locator('[data-testid="product-prod-cable-organizer"] img').count() == 0

  async def assert_historical_fixture_still_preserves_image_alt(page):
    await assert_baseline_alt(page)
    assert (
      await page.locator('[data-testid="product-add-prod-desk-lamp"]').get_attribute(
        "aria-label"
      )
    ) == "Remove Desk lamp"

  async def assert_seeded_image_alt(page, *, expected_alt: str):
    image = page.locator('[data-testid="product-image-prod-desk-lamp"]')
    notebook_image = page.locator(
      '[data-testid="product-image-prod-notebook-set"]'
    )

    assert await image.is_visible()
    assert (await image.get_attribute("src") or "").endswith("/desk-lamp.svg")
    assert await image.get_attribute("alt") == expected_alt
    assert await notebook_image.is_visible()
    assert (await notebook_image.get_attribute("src") or "").endswith(
      "/notebook-set.svg"
    )
    assert await notebook_image.get_attribute("alt") == NOTEBOOK_SET_BASELINE_ALT
    assert await page.locator('[data-testid="product-list"]').is_visible()
    assert await page.locator("h1", has_text="Products").is_visible()
    assert (
      (await page.locator("#product-title-prod-desk-lamp").text_content()) or ""
    ).strip() == "Desk lamp"
    assert (
      (await page.locator('[data-testid="product-add-prod-desk-lamp"]').text_content())
      or ""
    ).strip() == "Add Desk lamp"
    assert await page.locator('[data-testid="product-prod-cable-organizer"] img').count() == 0

  for profile in (None, "checkout-clean-v1", "checkout-unknown-profile"):
    asyncio.run(_with_checkout_page(assert_baseline_alt, profile=profile))

  asyncio.run(
    _with_checkout_page(
      assert_historical_fixture_still_preserves_image_alt,
      profile="checkout-pilot-001",
    )
  )
  for profile, expected_alt in DESK_LAMP_IMAGE_ALT_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected_alt=expected_alt: assert_seeded_image_alt(
          page,
          expected_alt=expected_alt,
        ),
        profile=profile,
      )
    )


def test_checkout_reciprocal_product_image_alt_swap_changes_only_both_alts():
  async def run(page):
    desk_image = page.locator('[data-testid="product-image-prod-desk-lamp"]')
    notebook_image = page.locator(
      '[data-testid="product-image-prod-notebook-set"]'
    )

    assert await desk_image.is_visible()
    assert (await desk_image.get_attribute("src") or "").endswith(
      "/desk-lamp.svg"
    )
    assert await desk_image.get_attribute("alt") == NOTEBOOK_SET_BASELINE_ALT
    assert await notebook_image.is_visible()
    assert (await notebook_image.get_attribute("src") or "").endswith(
      "/notebook-set.svg"
    )
    assert await notebook_image.get_attribute("alt") == DESK_LAMP_BASELINE_ALT

    assert (
      (await page.locator("#product-title-prod-desk-lamp").text_content()) or ""
    ).strip() == "Desk lamp"
    assert (
      (await page.locator("#product-title-prod-notebook-set").text_content()) or ""
    ).strip() == "Notebook set"
    assert (
      (await page.locator('[data-testid="product-add-prod-desk-lamp"]').text_content())
      or ""
    ).strip() == "Add Desk lamp"
    assert (
      (
        await page.locator(
          '[data-testid="product-add-prod-notebook-set"]'
        ).text_content()
      )
      or ""
    ).strip() == "Add Notebook set"

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-097"))


def test_checkout_notebook_image_localizes_and_reaches_review():
  async def run(page):
    desk_image = page.locator('[data-testid="product-image-prod-desk-lamp"]')
    notebook_image = page.locator(
      '[data-testid="product-image-prod-notebook-set"]'
    )

    assert await desk_image.is_visible()
    assert await desk_image.get_attribute("alt") == DESK_LAMP_BASELINE_ALT
    assert await notebook_image.is_visible()
    assert (await notebook_image.get_attribute("src") or "").endswith(
      "/notebook-set.svg"
    )
    assert await notebook_image.get_attribute("alt") == NOTEBOOK_SET_BASELINE_ALT

    await page.locator('[data-testid="products-language-es"]').click()
    assert await desk_image.get_attribute("alt") == DESK_LAMP_SPANISH_ALT
    assert await notebook_image.get_attribute("alt") == NOTEBOOK_SET_SPANISH_ALT

    await page.locator('[data-testid="products-language-en"]').click()
    assert await notebook_image.get_attribute("alt") == NOTEBOOK_SET_BASELINE_ALT
    await page.locator('[data-testid="product-add-prod-notebook-set"]').click()
    await _complete_checkout_to_review(page)

    review_notebook_image = page.locator(
      '[data-testid="review-product-image-prod-notebook-set"]'
    )
    assert await review_notebook_image.is_visible()
    assert (await review_notebook_image.get_attribute("src") or "").endswith(
      "/notebook-set.svg"
    )
    assert await review_notebook_image.get_attribute("alt") == NOTEBOOK_SET_BASELINE_ALT
    assert await page.locator(
      '[data-testid="review-product-image-prod-desk-lamp"]'
    ).get_attribute("alt") == DESK_LAMP_BASELINE_ALT

  asyncio.run(_with_checkout_page(run))


def test_checkout_root_language_case_preserves_english_products_content():
  async def assert_products_language(page, *, expected_lang: str):
    products_route = page.locator('[data-testid="route-products"]')
    route_text = (await products_route.inner_text()) or ""

    assert await page.evaluate("document.documentElement.lang") == expected_lang
    assert await page.locator("h1", has_text="Products").is_visible()
    assert await page.locator('[data-testid="product-list"]').is_visible()
    assert "Browse featured products and update the cart summary." in route_text
    assert "Desk lamp" in route_text
    assert "Cart summary" in route_text

  async def assert_cart_language(page, *, expected_lang: str):
    cart_route = page.locator('[data-testid="route-cart"]')
    route_text = (await cart_route.inner_text()) or ""

    assert await page.evaluate("document.documentElement.lang") == expected_lang
    assert await page.locator("h1", has_text="Cart").is_visible()
    assert "Cart items" in route_text
    assert "Review selected products before entering checkout details." in route_text
    assert "Order total" in route_text
    assert "Continue to address" in route_text

  async def assert_seeded_route_scope(page):
    await assert_products_language(page, expected_lang="da")
    await page.get_by_role("link", name="Cart").click()
    await page.wait_for_url("**/cart")
    await assert_cart_language(page, expected_lang="en")
    await page.get_by_role("link", name="Products").click()
    await page.wait_for_url("**/products")
    await assert_products_language(page, expected_lang="da")

  async def assert_cart_seeded_route_scope(page):
    await assert_products_language(page, expected_lang="en")
    await page.get_by_role("link", name="Cart").click()
    await page.wait_for_url("**/cart")
    await assert_cart_language(page, expected_lang="da")
    await page.locator('[data-testid="continue-to-address"]').click()
    await page.wait_for_url("**/checkout/address")
    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.locator("h1", has_text="Shipping address").is_visible()

  for profile in ROOT_LANG_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_products_language(page, expected_lang="en"),
        profile=profile,
      )
    )

  asyncio.run(
    _with_checkout_page(
      assert_seeded_route_scope,
      profile="checkout-co-sem-011",
    )
  )
  asyncio.run(
    _with_checkout_page(
      assert_cart_seeded_route_scope,
      profile="checkout-co-sem-013",
    )
  )


def test_checkout_spanish_products_content_case_keeps_english_root_lang():
  async def assert_english_products_copy(page, *, expected_lang: str):
    route_text = (
      (await page.locator('[data-testid="route-products"]').inner_text())
      or ""
    )

    assert await page.evaluate("document.documentElement.lang") == expected_lang
    assert await page.locator("h1", has_text="Products").is_visible()
    assert "Browse featured products and update the cart summary." in route_text
    assert "Featured products" in route_text
    assert "Desk accessories" in route_text
    assert "Desk lamp" in route_text
    assert "Add Desk lamp" in route_text
    assert "Cart summary" in route_text

  async def assert_spanish_products_copy(page):
    await page.locator('[data-testid="products-language-es"]').click()
    route = page.locator('[data-testid="route-products"]')
    route_text = (await route.inner_text()) or ""
    notebook_button = page.get_by_role(
      "button",
      name="Agregar Juego de cuadernos",
    )

    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.title() == "Productos | Brightlane Checkout"
    assert await page.locator("h1", has_text="Productos").is_visible()
    assert "Explora productos destacados y actualiza el resumen del carrito." in route_text
    assert "Productos destacados" in route_text
    assert "Accesorios de escritorio" in route_text
    assert "Lámpara de escritorio" in route_text
    assert "Agregar Lámpara de escritorio" in route_text
    assert "Resumen del carrito" in route_text
    assert "En el carrito: 1 artículo" in route_text
    assert "Flujo de compra" in ((await page.locator(".app-header").inner_text()) or "")
    assert await page.get_by_role("navigation", name="Rutas de compra").is_visible()
    assert await page.get_by_role("link", name="Productos").is_visible()
    assert await page.get_by_role("link", name="Carrito").is_visible()
    assert await page.get_by_role("group", name="Idioma de productos").is_visible()
    assert await page.get_by_role("button", name="Inglés").is_visible()
    assert await page.get_by_role("button", name="Español").is_visible()
    assert "Ayuda" in route_text
    assert "Devoluciones y reembolsos" in route_text
    assert "Experiencia de compra de demostración" in (
      (await page.locator(".app-footer").inner_text()) or ""
    )
    assert await page.locator('[data-testid="product-image-prod-desk-lamp"]').get_attribute(
      "alt"
    ) == DESK_LAMP_SPANISH_ALT
    assert await page.locator(
      '[data-testid="product-image-prod-notebook-set"]'
    ).get_attribute("alt") == NOTEBOOK_SET_SPANISH_ALT

    assert await notebook_button.is_visible()
    assert await notebook_button.get_attribute("aria-label") is None
    await notebook_button.click()
    assert (
      (await page.locator('[data-testid="cart-summary-count"]').text_content())
      or ""
    ).strip() == "2 artículos"
    assert "Juego de cuadernos agregado al carrito." in (
      (await page.locator('[data-testid="status-region"]').text_content()) or ""
    )

  for profile in (
    None,
    "checkout-clean-v1",
    "checkout-unknown-profile",
    "checkout-co-sem-006",
  ):
    asyncio.run(
      _with_checkout_page(
        lambda page: assert_english_products_copy(page, expected_lang="en"),
        profile=profile,
      )
    )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_english_products_copy(page, expected_lang="da"),
      profile="checkout-co-sem-011",
    )
  )
  asyncio.run(
    _with_checkout_page(
      assert_spanish_products_copy,
      profile="checkout-co-sem-012",
    )
  )


def test_checkout_spanish_cart_content_case_keeps_english_root_lang():
  async def open_cart(page, *, link_name: str = "Cart"):
    await page.get_by_role("link", name=link_name).click()
    await page.wait_for_url("**/cart")

  async def assert_english_cart_copy(page, *, expected_lang: str):
    await open_cart(page)
    route_text = (
      (await page.locator('[data-testid="route-cart"]').inner_text()) or ""
    )

    assert await page.evaluate("document.documentElement.lang") == expected_lang
    assert await page.locator("h1", has_text="Cart").is_visible()
    assert "Review cart items and quantity controls." in route_text
    assert "Cart items" in route_text
    assert "Review selected products before entering checkout details." in route_text
    assert "Gift receipt" in route_text
    assert "Delivery estimate" in route_text
    assert "Continue to address" in route_text

  async def assert_spanish_cart_copy(page):
    await page.locator('[data-testid="products-language-es"]').click()
    assert await page.evaluate("document.documentElement.lang") == "es"
    await open_cart(page, link_name="Carrito")
    route = page.locator('[data-testid="route-cart"]')
    route_text = (await route.inner_text()) or ""

    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.title() == "Carrito | Brightlane Checkout"
    assert await page.locator("h1", has_text="Carrito").is_visible()
    assert "Revisa los artículos del carrito y los controles de cantidad." in route_text
    assert "Progreso de compra" in route_text
    assert "Artículos del carrito" in route_text
    assert "Revisa los productos seleccionados antes de ingresar" in route_text
    assert "Precio unitario" in route_text
    assert "Máximo 3 por artículo." in route_text
    assert "Total de línea" in route_text
    assert "Resumen del carrito" in route_text
    assert "Recibo de regalo" in route_text
    assert "Estimación de entrega" in route_text
    assert "Información de envío" in route_text
    assert "Continuar a dirección" in route_text
    assert "Flujo de compra" in ((await page.locator(".app-header").inner_text()) or "")
    assert await page.get_by_role("navigation", name="Rutas de compra").is_visible()
    assert await page.get_by_role("link", name="Productos").is_visible()
    assert await page.get_by_role("link", name="Carrito").is_visible()
    assert "OFICINA EN CASA" in route_text
    assert "Lámpara de escritorio" in route_text

    await page.get_by_role(
      "button",
      name="Aumentar cantidad de Lámpara de escritorio",
    ).click()
    assert (
      (await page.locator('[data-testid="cart-summary-count"]').text_content())
      or ""
    ).strip() == "2 artículos"
    assert "Cantidad de Lámpara de escritorio actualizada a 2." in (
      (await page.locator('[data-testid="status-region"]').text_content()) or ""
    )

    await page.get_by_role("button", name="Guardar carrito").click()
    assert "Carrito guardado para después." in (
      (await page.locator('[data-testid="save-cart-note"]').text_content()) or ""
    )

    gift_receipt = page.get_by_role("switch", name="Recibo de regalo")
    assert await gift_receipt.get_attribute("aria-checked") == "false"
    await gift_receipt.click()
    assert await gift_receipt.get_attribute("aria-checked") == "true"
    assert "Se incluirá un recibo de regalo." in (
      (await page.locator('[data-testid="gift-receipt-note"]').text_content()) or ""
    )

    delivery = page.get_by_role("button", name="Estimación de entrega")
    assert await delivery.get_attribute("aria-expanded") == "false"
    await delivery.click()
    assert await delivery.get_attribute("aria-expanded") == "true"
    assert "La entrega estándar suele llegar en 3-5 días hábiles" in (
      (await page.locator('[data-testid="delivery-estimate-panel"]').text_content())
      or ""
    )

    await page.get_by_role("button", name="Información de envío").click()
    dialog = page.get_by_role("dialog", name="Información de envío")
    assert await dialog.is_visible()
    assert "Los detalles de entrega se confirman después" in (
      (await dialog.text_content()) or ""
    )
    await page.get_by_role("button", name="Cerrar").click()
    assert await page.locator('[data-testid="shipping-information-dialog"]').count() == 0

  for profile, expected_lang in (
    (None, "en"),
    ("checkout-clean-v1", "en"),
    ("checkout-unknown-profile", "en"),
    ("checkout-co-sem-013", "da"),
  ):
    asyncio.run(
      _with_checkout_page(
        lambda page, expected_lang=expected_lang: assert_english_cart_copy(
          page,
          expected_lang=expected_lang,
        ),
        profile=profile,
      )
    )

  asyncio.run(
    _with_checkout_page(
      assert_spanish_cart_copy,
      profile="checkout-co-sem-014",
    )
  )


def test_checkout_shipping_information_dialog_is_modal_and_accessible():
  async def run(page):
    await page.get_by_role("link", name="Cart").click()

    assert await page.locator("h1", has_text="Cart").is_visible()
    assert await page.locator('[data-testid="cart-list"]').is_visible()
    assert (
      (await page.locator('[data-testid="cart-quantity-prod-desk-lamp"]').text_content())
      or ""
    ).strip() == "1"
    assert (
      (await page.locator('[data-testid="cart-summary-count"]').text_content())
      or ""
    ).strip() == "1 item"
    assert (
      (await page.locator('[data-testid="cart-summary-shipping"]').text_content())
      or ""
    ).strip() == "$5.00"

    gift_receipt_switch = page.get_by_role("switch", name="Gift receipt")
    gift_receipt_note = page.locator('[data-testid="gift-receipt-note"]')
    save_cart_button = page.get_by_role("button", name="Save cart")
    save_cart_note = page.locator('[data-testid="save-cart-note"]')

    assert await gift_receipt_switch.is_visible()
    assert await gift_receipt_switch.get_attribute("aria-checked") == "false"
    assert "is-on" not in (
      (await gift_receipt_switch.get_attribute("class")) or ""
    ).split()
    assert await gift_receipt_note.count() == 0

    await gift_receipt_switch.click()
    assert await gift_receipt_switch.get_attribute("aria-checked") == "true"
    assert "is-on" in (
      (await gift_receipt_switch.get_attribute("class")) or ""
    ).split()
    assert "A gift receipt will be included." in (
      (await gift_receipt_note.text_content()) or ""
    )

    await gift_receipt_switch.click()
    assert await gift_receipt_switch.get_attribute("aria-checked") == "false"
    assert "is-on" not in (
      (await gift_receipt_switch.get_attribute("class")) or ""
    ).split()
    assert await gift_receipt_note.count() == 0

    assert await save_cart_button.is_visible()
    assert await save_cart_button.get_attribute("aria-pressed") == "false"
    assert "is-saved" not in (
      (await save_cart_button.get_attribute("class")) or ""
    ).split()
    assert await save_cart_note.count() == 0

    await save_cart_button.click()
    assert await save_cart_button.get_attribute("aria-pressed") == "true"
    assert "is-saved" in (
      (await save_cart_button.get_attribute("class")) or ""
    ).split()
    assert "Cart saved for later." in (
      (await save_cart_note.text_content()) or ""
    )

    await save_cart_button.click()
    assert await save_cart_button.get_attribute("aria-pressed") == "false"
    assert "is-saved" not in (
      (await save_cart_button.get_attribute("class")) or ""
    ).split()
    assert await save_cart_note.count() == 0

    delivery_button = page.get_by_role("button", name="Delivery estimate")
    delivery_panel = page.locator('[data-testid="delivery-estimate-panel"]')
    assert await delivery_button.is_visible()
    assert await delivery_button.get_attribute("aria-expanded") == "false"
    assert await delivery_button.get_attribute("aria-controls") == "delivery-estimate-panel"
    assert await delivery_panel.count() == 1
    assert await delivery_panel.get_attribute("hidden") == ""
    assert not await delivery_panel.is_visible()

    await delivery_button.click()
    assert await delivery_button.get_attribute("aria-expanded") == "true"
    assert await delivery_panel.get_attribute("hidden") is None
    assert await delivery_panel.is_visible()
    assert (
      "Standard delivery usually arrives in 3-5 business days after dispatch."
      in ((await delivery_panel.text_content()) or "")
    )

    await delivery_button.click()
    assert await delivery_button.get_attribute("aria-expanded") == "false"
    assert await delivery_panel.count() == 1
    assert await delivery_panel.get_attribute("hidden") == ""
    assert not await delivery_panel.is_visible()

    trigger = page.get_by_role("button", name="Shipping information")
    continue_button = page.locator('[data-testid="continue-to-address"]')
    assert await trigger.is_visible()
    assert await continue_button.is_visible()
    assert await page.locator('[data-testid="shipping-information-dialog"]').count() == 0

    await trigger.click()

    dialog_by_testid = page.locator('[data-testid="shipping-information-dialog"]')
    dialog = page.get_by_role("dialog", name="Shipping information")
    close_button = page.get_by_role("button", name="Close")
    assert await dialog.is_visible()
    assert await dialog_by_testid.get_attribute("role") == "dialog"
    assert await dialog_by_testid.get_attribute("aria-modal") == "true"
    assert (
      await dialog_by_testid.get_attribute("aria-labelledby")
    ) == "shipping-information-title"
    assert (
      (await page.locator("#shipping-information-title").text_content()) or ""
    ).strip() == "Shipping information"
    assert "Standard shipping is calculated during checkout." in (
      (await dialog.text_content()) or ""
    )

    await page.wait_for_function(
      "() => document.activeElement?.dataset?.testid === 'shipping-information-close'",
    )
    await page.keyboard.press("Tab")
    await page.wait_for_function(
      "() => document.activeElement?.dataset?.testid === 'shipping-information-close'",
    )
    await page.keyboard.press("Shift+Tab")
    await page.wait_for_function(
      "() => document.activeElement?.dataset?.testid === 'shipping-information-close'",
    )

    await close_button.click()
    assert await page.locator('[data-testid="shipping-information-dialog"]').count() == 0
    await page.wait_for_function(
      "() => document.activeElement?.dataset?.testid === 'shipping-information-trigger'",
    )

    await trigger.click()
    assert await dialog.is_visible()
    await page.keyboard.press("Escape")
    assert await page.locator('[data-testid="shipping-information-dialog"]').count() == 0
    await page.wait_for_function(
      "() => document.activeElement?.dataset?.testid === 'shipping-information-trigger'",
    )

    assert await page.locator("h1", has_text="Cart").is_visible()
    assert await page.locator('[data-testid="cart-list"]').is_visible()
    assert await continue_button.is_visible()
    assert (
      (await page.locator('[data-testid="cart-summary-total"]').text_content())
      or ""
    ).strip() == "$37.00"

  asyncio.run(_with_checkout_page(run))


def test_checkout_review_order_items_table_uses_explicit_headers():
  async def run(page):
    await _complete_checkout_to_review(page)

    table = page.locator('[data-testid="review-order-table"]')
    assert await page.locator("h1", has_text="Review").is_visible()
    assert await table.is_visible()
    assert ((await table.locator("caption").text_content()) or "").strip() == (
      "Product quantities and totals"
    )

    column_headers = {
      "review-item-header": "Item",
      "review-quantity-header": "Quantity",
      "review-line-total-header": "Line total",
    }
    for header_id, expected_text in column_headers.items():
      header = page.locator(f"#{header_id}")
      assert ((await header.text_content()) or "").strip() == expected_text
      assert await header.get_attribute("scope") == "col"

    row_header = page.locator("#review-item-header-prod-desk-lamp")
    assert await row_header.get_attribute("scope") == "row"
    assert "Desk lamp" in ((await row_header.text_content()) or "")
    assert await page.locator(
      '[data-testid="review-product-image-prod-desk-lamp"]'
    ).get_attribute("alt") == "Desk lamp with adjustable brass shade"

    quantity_cell = page.locator(
      '[data-testid="review-order-quantity-prod-desk-lamp"]'
    )
    line_total_cell = page.locator(
      '[data-testid="review-order-line-total-prod-desk-lamp"]'
    )
    assert ((await quantity_cell.text_content()) or "").strip() == "1"
    assert ((await line_total_cell.text_content()) or "").strip() == "$32.00"
    assert await quantity_cell.get_attribute("headers") == (
      "review-item-header-prod-desk-lamp review-quantity-header"
    )
    assert await line_total_cell.get_attribute("headers") == (
      "review-item-header-prod-desk-lamp review-line-total-header"
    )

    header_resolution = await page.evaluate(
      """() => Array.from(
        document.querySelectorAll('[data-testid="review-order-table"] td[headers]')
      ).map((cell) => {
        const ids = (cell.getAttribute("headers") || "").split(/\\s+/).filter(Boolean);
        return {
          testId: cell.getAttribute("data-testid"),
          headers: ids,
          allResolved: ids.every((id) => Boolean(document.getElementById(id))),
          headerTexts: ids.map((id) => document.getElementById(id).textContent.trim()),
        };
      })"""
    )

    assert header_resolution == [
      {
        "testId": "review-order-quantity-prod-desk-lamp",
        "headers": [
          "review-item-header-prod-desk-lamp",
          "review-quantity-header",
        ],
        "allResolved": True,
        "headerTexts": ["Desk lamp", "Quantity"],
      },
      {
        "testId": "review-order-line-total-prod-desk-lamp",
        "headers": [
          "review-item-header-prod-desk-lamp",
          "review-line-total-header",
        ],
        "allResolved": True,
        "headerTexts": ["Desk lamp", "Line total"],
      },
    ]

    row_header_ids = await page.evaluate(
      """() => Array.from(
        document.querySelectorAll('[data-testid="review-order-table"] tbody th[scope="row"]')
      ).map((header) => header.id)"""
    )
    assert len(row_header_ids) == len(set(row_header_ids))
    assert await page.get_by_role("button", name="Place order").is_visible()

  asyncio.run(_with_checkout_page(run))
