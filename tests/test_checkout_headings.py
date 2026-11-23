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
CHECKOUT_DIR = REPO_ROOT / "benchmarks" / "local-spas" / "checkout-flow"
CHECKOUT_PROFILE_GLOBAL = "__ACCESSGRAPH_CHECKOUT_PROFILE__"
VIEWPORT = {"width": 1280, "height": 720}
PRODUCTS_TITLE = "Products | Brightlane Checkout"
CART_TITLE = "Cart | Brightlane Checkout"
ADDRESS_TITLE = "Shipping address | Brightlane Checkout"
PAYMENT_TITLE = "Payment | Brightlane Checkout"
HEADING_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
)
CART_HEADING_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-095",
  "checkout-co-sem-092",
)
EMPTY_CART_HEADING_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-co-sem-095",
)
PRODUCTS_PAGE_HEADING_CASES = {
  "checkout-co-sem-041": "Payment details",
  "checkout-co-sem-042": "Fishing techniques",
}
FEATURED_PRODUCTS_HEADING_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-006",
)
FEATURED_PRODUCTS_HEADING_CASES = {
  "checkout-co-sem-044": "Order summary",
  "checkout-co-sem-045": "Weather forecast",
}
CART_PAGE_HEADING_CASES = {
  "checkout-co-sem-047": "Products",
  "checkout-co-sem-091": "Shipping address",
}
PAYMENT_METHOD_HEADING_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-091",
)
PAYMENT_METHOD_HEADING_CASES = {
  "checkout-co-sem-093": "Card number",
}
VALID_ADDRESS_VALUES = {
  "address-full-name": "Jordan Lee",
  "address-email": "jordan.lee@example.test",
  "address-street": "42 Market Street",
  "address-city": "Portland",
  "address-state": "OR",
  "address-postal-code": "97205",
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
    await page.wait_for_selector('[data-testid="route-products"]')
    return await callback(page)
  finally:
    if context is not None:
      await context.close()
    if browser is not None:
      await browser.close()
    if manager is not None:
      await manager.stop()
    _stop_process(server)


async def _assert_products_heading_state(page, *, expected_h1: str) -> None:
  h1 = page.locator("main h1")
  route_text = (await page.locator('[data-testid="route-products"]').inner_text()) or ""

  assert await page.title() == PRODUCTS_TITLE
  assert (await h1.text_content() or "").strip() == expected_h1
  assert await h1.evaluate("node => node.tagName.toLowerCase()") == "h1"
  assert await h1.get_attribute("id") is None
  assert await h1.get_attribute("role") is None
  assert await h1.get_attribute("aria-label") is None
  assert await h1.get_attribute("aria-labelledby") is None
  assert await page.get_by_role(
    "heading",
    level=1,
    name=expected_h1,
    exact=True,
  ).is_visible()
  assert page.url.endswith("/products")

  assert "Browse featured products and update the cart summary." in route_text
  assert "Featured products" in route_text
  assert "Browse by category" in route_text
  assert "Desk lamp" in route_text
  assert "Notebook set" in route_text
  assert "Cable organizer" in route_text
  assert await page.get_by_role(
    "heading",
    level=2,
    name="Featured products",
    exact=True,
  ).is_visible()
  assert await page.get_by_role(
    "heading",
    level=3,
    name="Browse by category",
    exact=True,
  ).is_visible()


async def _assert_featured_products_heading_state(
  page,
  *,
  expected_h2: str,
) -> None:
  h1 = page.locator("main h1")
  h2 = page.locator("#product-list-heading")
  product_region = page.locator('[data-testid="products-list-region"]')
  route_text = (await page.locator('[data-testid="route-products"]').inner_text()) or ""

  assert await page.title() == PRODUCTS_TITLE
  assert (await h1.text_content() or "").strip() == "Products"
  assert await h1.evaluate("node => node.tagName.toLowerCase()") == "h1"
  assert await page.get_by_role(
    "heading",
    level=1,
    name="Products",
    exact=True,
  ).is_visible()
  assert (await h2.text_content() or "").strip() == expected_h2
  assert await h2.evaluate("node => node.tagName.toLowerCase()") == "h2"
  assert await h2.get_attribute("role") is None
  assert await h2.get_attribute("aria-label") is None
  assert await h2.get_attribute("aria-labelledby") is None
  assert await product_region.get_attribute("aria-labelledby") == "product-list-heading"
  assert await page.get_by_role(
    "heading",
    level=2,
    name=expected_h2,
    exact=True,
  ).is_visible()
  assert await page.get_by_role("region", name=expected_h2, exact=True).is_visible()
  assert page.url.endswith("/products")

  assert "Browse featured products and update the cart summary." in route_text
  assert "Browse by category" in route_text
  assert "Desk lamp" in route_text
  assert "Notebook set" in route_text
  assert "Cable organizer" in route_text
  assert await page.get_by_role(
    "heading",
    level=3,
    name="Browse by category",
    exact=True,
  ).is_visible()


async def _open_cart(page) -> None:
  await page.locator('[data-testid="nav-cart"]').click()
  await page.wait_for_selector('[data-testid="route-cart"]')
  assert page.url.endswith("/cart")


async def _open_payment(page) -> None:
  await _open_cart(page)
  await page.locator('[data-testid="continue-to-address"]').click()
  await page.wait_for_url("**/checkout/address")
  for test_id, value in VALID_ADDRESS_VALUES.items():
    await page.locator(f'[data-testid="{test_id}"]').fill(value)
  await page.locator('[data-testid="continue-to-payment"]').click()
  await page.wait_for_url("**/checkout/payment")


async def _assert_payment_method_heading_state(page, *, expected_h2: str) -> None:
  await _open_payment(page)
  h1 = page.locator("main h1")
  h2 = page.locator("#payment-form-heading")
  payment_section = page.locator(
    'section[aria-labelledby="payment-form-heading"]'
  )

  assert await page.title() == PAYMENT_TITLE
  assert page.url.endswith("/checkout/payment")
  assert (await h1.text_content() or "").strip() == "Payment"
  assert await page.get_by_role(
    "heading",
    level=1,
    name="Payment",
    exact=True,
  ).is_visible()
  assert (await h2.text_content() or "").strip() == expected_h2
  assert await h2.evaluate("node => node.tagName.toLowerCase()") == "h2"
  assert await h2.get_attribute("id") == "payment-form-heading"
  assert await h2.get_attribute("role") is None
  assert await h2.get_attribute("aria-label") is None
  assert await h2.get_attribute("aria-labelledby") is None
  assert await payment_section.get_attribute("aria-labelledby") == (
    "payment-form-heading"
  )
  assert await page.get_by_role(
    "heading",
    level=2,
    name=expected_h2,
    exact=True,
  ).is_visible()
  assert await page.get_by_role(
    "heading",
    level=2,
    name="Checkout progress",
    exact=True,
  ).is_visible()
  assert await page.get_by_role(
    "heading",
    level=2,
    name="Cart summary",
    exact=True,
  ).is_visible()

  assert await page.locator('[data-testid="checkout-progress-payment"]').get_attribute(
    "aria-current"
  ) == "step"
  assert await page.locator('[data-testid="checkout-progress-address"]').get_attribute(
    "aria-current"
  ) is None
  assert await page.locator('[data-testid="payment-form"]').is_visible()
  assert await page.get_by_text("Card details", exact=True).is_visible()
  for test_id, label in {
    "payment-cardholder": "Cardholder name",
    "payment-card-number": "Card number",
    "payment-expiry": "Expiry",
    "payment-security-code": "Security code",
  }.items():
    control = page.locator(f'[data-testid="{test_id}"]')
    control_id = await control.get_attribute("id")
    assert control_id
    assert (
      await page.locator(f'label[for="{control_id}"] span').first.text_content()
      or ""
    ).strip() == label
  assert await page.locator('[data-testid="continue-to-review"]').is_visible()


async def _assert_cart_heading_state(
  page,
  *,
  expected_h1: str,
  expected_summary: str = "Review cart items and quantity controls.",
) -> None:
  await _open_cart(page)
  h1 = page.locator("main h1")
  route_text = (await page.locator('[data-testid="route-cart"]').inner_text()) or ""

  assert await page.title() == CART_TITLE
  assert (await h1.text_content() or "").strip() == expected_h1
  assert await h1.evaluate("node => node.tagName.toLowerCase()") == "h1"
  assert await h1.get_attribute("id") is None
  assert await h1.get_attribute("role") is None
  assert await h1.get_attribute("aria-label") is None
  assert await h1.get_attribute("aria-labelledby") is None
  assert await page.get_by_role(
    "heading",
    level=1,
    name=expected_h1,
    exact=True,
  ).is_visible()

  assert expected_summary in route_text
  assert "Checkout progress" in route_text
  assert "Cart items" in route_text
  assert "Desk lamp" in route_text
  assert "Cart summary" in route_text
  assert "Continue to address" in route_text
  assert await page.get_by_role(
    "heading",
    level=2,
    name="Checkout progress",
    exact=True,
  ).is_visible()
  assert await page.get_by_role(
    "heading",
    level=2,
    name="Cart items",
    exact=True,
  ).is_visible()
  assert await page.get_by_role(
    "heading",
    level=2,
    name="Desk lamp",
    exact=True,
  ).is_visible()
  assert await page.get_by_role(
    "heading",
    level=2,
    name="Cart summary",
    exact=True,
  ).is_visible()
  assert await page.locator('[data-testid="cart-totals-region"]').get_attribute(
    "aria-label"
  ) == "Order totals"
  assert (
    await page.locator('[data-testid="cart-quantity-prod-desk-lamp"]').text_content()
    or ""
  ).strip() == "1"


async def _assert_empty_cart_heading_state(page, *, expected_h2: str) -> None:
  await _open_cart(page)
  await page.locator('[data-testid="cart-decrement-prod-desk-lamp"]').click()
  await page.locator("#empty-cart-heading").wait_for(state="visible")

  route = page.locator('[data-testid="route-cart"]')
  empty_section = page.locator(
    'section[aria-labelledby="empty-cart-heading"]'
  )
  h1 = page.locator("main h1")
  h2 = page.locator("#empty-cart-heading")

  assert page.url.endswith("/cart")
  assert await page.title() == CART_TITLE
  assert (await h1.text_content() or "").strip() == "Cart"
  assert (await h2.text_content() or "").strip() == expected_h2
  assert await h2.evaluate("node => node.tagName.toLowerCase()") == "h2"
  assert await h2.get_attribute("id") == "empty-cart-heading"
  assert await h2.get_attribute("role") is None
  assert await h2.get_attribute("aria-label") is None
  assert await h2.get_attribute("aria-labelledby") is None
  assert await empty_section.get_attribute("aria-labelledby") == (
    "empty-cart-heading"
  )
  assert await page.get_by_role(
    "heading",
    level=2,
    name=expected_h2,
    exact=True,
  ).is_visible()
  assert await page.get_by_role(
    "region",
    name=expected_h2,
    exact=True,
  ).is_visible()
  assert await route.get_by_text(
    "Add a product before continuing checkout.",
    exact=True,
  ).is_visible()
  assert await route.get_by_role(
    "button",
    name="Browse products",
    exact=True,
  ).is_visible()
  assert await page.locator('[data-testid^="cart-item-"]').count() == 0
  assert await page.locator('[data-testid="cart-list"]').count() == 0
  assert await page.locator('[data-testid="continue-to-address"]').count() == 0
  assert await page.locator("main h1, main h2").all_text_contents() == [
    "Cart",
    expected_h2,
  ]


def test_checkout_products_page_heading_baseline_profiles():
  for profile in HEADING_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: _assert_products_heading_state(
          page,
          expected_h1="Products",
        ),
        profile=profile,
      )
    )


def test_checkout_featured_products_heading_baseline_profiles():
  for profile in FEATURED_PRODUCTS_HEADING_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: _assert_featured_products_heading_state(
          page,
          expected_h2="Featured products",
        ),
        profile=profile,
      )
    )


def test_checkout_cart_page_heading_baseline_profiles():
  for profile in CART_HEADING_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: _assert_cart_heading_state(
          page,
          expected_h1="Cart",
        ),
        profile=profile,
      )
    )


def test_checkout_payment_method_heading_baseline_profiles():
  for profile in PAYMENT_METHOD_HEADING_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: _assert_payment_method_heading_state(
          page,
          expected_h2="Payment method",
        ),
        profile=profile,
      )
    )


def test_checkout_empty_cart_heading_baseline_profiles():
  for profile in EMPTY_CART_HEADING_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: _assert_empty_cart_heading_state(
          page,
          expected_h2="Your cart is empty",
        ),
        profile=profile,
      )
    )


def test_checkout_products_page_heading_cases_update_h1_only():
  async def assert_seeded_heading(page, *, expected_h1: str):
    await _assert_products_heading_state(page, expected_h1=expected_h1)
    assert await page.locator("main h1", has_text="Products").count() == 0

  for profile, expected_heading in PRODUCTS_PAGE_HEADING_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected_heading=expected_heading: assert_seeded_heading(
          page,
          expected_h1=expected_heading,
        ),
        profile=profile,
      )
    )


def test_checkout_cart_page_heading_cases_update_cart_h1_only():
  async def assert_seeded_heading(page, *, expected_h1: str):
    await _assert_products_heading_state(page, expected_h1="Products")
    await _assert_cart_heading_state(page, expected_h1=expected_h1)
    assert await page.locator('[data-testid="route-cart"] h1', has_text="Cart").count() == 0

    await page.locator('[data-testid="continue-to-address"]').click()
    await page.wait_for_selector('[data-testid="route-address"]')
    assert page.url.endswith("/checkout/address")
    assert await page.title() == ADDRESS_TITLE
    assert await page.get_by_role(
      "heading",
      level=1,
      name="Shipping address",
      exact=True,
    ).is_visible()

  for profile, expected_heading in CART_PAGE_HEADING_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected_heading=expected_heading: assert_seeded_heading(
          page,
          expected_h1=expected_heading,
        ),
        profile=profile,
      )
    )


def test_checkout_stale_products_heading_block_is_retained_only_on_cart():
  async def assert_seeded_heading_block(page):
    products_intro = "Browse featured products and update the cart summary."
    cart_intro = "Review cart items and quantity controls."

    await _assert_products_heading_state(page, expected_h1="Products")
    assert (await page.locator(".route-heading p").text_content() or "").strip() == (
      products_intro
    )

    await _assert_cart_heading_state(
      page,
      expected_h1="Products",
      expected_summary=products_intro,
    )
    route = page.locator('[data-testid="route-cart"]')
    assert (await route.locator(".route-heading p").text_content() or "").strip() == (
      products_intro
    )
    assert await route.get_by_text(cart_intro, exact=True).count() == 0
    assert await page.locator('[data-testid="nav-cart"]').get_attribute(
      "aria-current"
    ) == "page"
    assert await page.locator('[data-testid="nav-products"]').get_attribute(
      "aria-current"
    ) is None
    assert await page.locator('[data-testid="checkout-progress-cart"]').get_attribute(
      "aria-current"
    ) == "step"
    assert await page.locator(
      '[data-testid="checkout-progress-address"]'
    ).get_attribute("aria-current") is None

  asyncio.run(
    _with_checkout_page(
      assert_seeded_heading_block,
      profile="checkout-co-sem-094",
    )
  )


def test_checkout_featured_products_heading_case_updates_h2_only():
  async def assert_seeded_heading(page, *, expected_h2: str):
    await _assert_featured_products_heading_state(page, expected_h2=expected_h2)
    assert await page.locator("#product-list-heading", has_text="Featured products").count() == 0

  for profile, expected_heading in FEATURED_PRODUCTS_HEADING_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected_heading=expected_heading: assert_seeded_heading(
          page,
          expected_h2=expected_heading,
        ),
        profile=profile,
      )
    )


def test_checkout_payment_method_heading_case_updates_h2_only():
  async def assert_seeded_heading(page, *, expected_h2: str):
    await _assert_payment_method_heading_state(page, expected_h2=expected_h2)
    assert await page.locator(
      "#payment-form-heading",
      has_text="Payment method",
    ).count() == 0

  for profile, expected_heading in PAYMENT_METHOD_HEADING_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected_heading=expected_heading: assert_seeded_heading(
          page,
          expected_h2=expected_heading,
        ),
        profile=profile,
      )
    )


def test_checkout_empty_cart_heading_case_updates_conditional_h2_only():
  async def assert_seeded_heading(page):
    await _assert_empty_cart_heading_state(page, expected_h2="Cart items")
    assert await page.locator(
      "#empty-cart-heading",
      has_text="Your cart is empty",
    ).count() == 0

  asyncio.run(
    _with_checkout_page(
      assert_seeded_heading,
      profile="checkout-co-sem-092",
    )
  )
