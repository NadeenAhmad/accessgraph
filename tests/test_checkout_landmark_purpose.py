from __future__ import annotations

import asyncio
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
  sys.path.insert(0, str(TESTS_DIR))

from test_checkout_product_category_tabs import _with_checkout_page


BASELINE_FEATURED_REGION = {
  "products_region_name": "Featured products",
  "products_region_aria_label": None,
  "products_region_aria_labelledby": "product-list-heading",
  "footer_tag": "footer",
  "footer_role": None,
  "footer_landmark_role": "contentinfo",
  "footer_name": None,
  "footer_aria_label": None,
  "order_totals_role": None,
  "order_totals_landmark_role": "complementary",
  "progress_name": "Checkout progress",
  "progress_aria_label": None,
  "progress_aria_labelledby": "checkout-progress-heading",
}

NAVIGATION_LANDMARK_CASES = {
  None: {
    **BASELINE_FEATURED_REGION,
    "nav_name": "Checkout routes",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
  },
  "checkout-clean-v1": {
    **BASELINE_FEATURED_REGION,
    "nav_name": "Checkout routes",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
  },
  "checkout-unknown-profile": {
    **BASELINE_FEATURED_REGION,
    "nav_name": "Checkout routes",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
  },
  "checkout-co-sem-006": {
    **BASELINE_FEATURED_REGION,
    "nav_name": "Checkout routes",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
  },
  "checkout-co-sem-020": {
    **BASELINE_FEATURED_REGION,
    "nav_name": "Checkout routes",
    "cart_visible_text": "Weather forecast",
    "cart_accessible_name": "Weather forecast",
    "cart_aria_label": None,
  },
  "checkout-co-sem-052": {
    **BASELINE_FEATURED_REGION,
    "nav_name": "Order totals",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
  },
  "checkout-co-sem-053": {
    "products_region_name": "Checkout routes",
    "products_region_aria_label": "Checkout routes",
    "products_region_aria_labelledby": None,
    "footer_tag": "footer",
    "footer_role": None,
    "footer_landmark_role": "contentinfo",
    "footer_name": None,
    "footer_aria_label": None,
    "order_totals_role": None,
    "order_totals_landmark_role": "complementary",
    "nav_name": "Checkout routes",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
  },
  "checkout-co-sem-054": {
    **BASELINE_FEATURED_REGION,
    "nav_name": "Checkout routes",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
    "order_totals_role": "search",
    "order_totals_landmark_role": "search",
  },
  "checkout-co-sem-055": {
    **BASELINE_FEATURED_REGION,
    "footer_tag": "div",
    "footer_role": "search",
    "footer_landmark_role": "search",
    "nav_name": "Checkout routes",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
  },
  "checkout-co-sem-056": {
    **BASELINE_FEATURED_REGION,
    "footer_name": "Checkout routes",
    "footer_aria_label": "Checkout routes",
    "nav_name": "Checkout routes",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
  },
  "checkout-co-sem-116": {
    **BASELINE_FEATURED_REGION,
    "nav_name": "Checkout progress",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
  },
  "checkout-co-sem-117": {
    **BASELINE_FEATURED_REGION,
    "nav_name": "Checkout routes",
    "cart_visible_text": "Cart",
    "cart_accessible_name": "Cart",
    "cart_aria_label": None,
    "progress_name": "Order totals",
    "progress_aria_label": "Order totals",
    "progress_aria_labelledby": None,
  },
}

ADDRESS_TOTALS_LANDMARK_CASES = {
  "checkout-clean-v1": "Order totals",
  "checkout-co-sem-118": "Shipping details",
}


def test_checkout_landmark_name_cases_update_only_their_target_landmark():
  async def assert_landmark_state(page, *, expected: dict[str, str | None]) -> None:
    nav = page.locator("nav.app-nav")
    products_link = page.locator('[data-testid="nav-products"]')
    cart_link = page.locator('[data-testid="nav-cart"]')
    product_region = page.locator('[data-testid="products-list-region"]')
    footer = page.locator('[data-testid="app-footer"]')

    products_heading = page.locator("h1", has_text="Products")
    await products_heading.wait_for()
    assert await products_heading.is_visible()
    assert await page.locator(
      '[data-testid="product-add-prod-notebook-set"]',
    ).is_visible()

    assert await nav.evaluate("node => node.tagName.toLowerCase()") == "nav"
    assert await nav.get_attribute("role") is None
    assert await nav.get_attribute("aria-label") == expected["nav_name"]
    assert await page.get_by_role(
      "navigation",
      name=expected["nav_name"],
    ).is_visible()

    assert await product_region.evaluate("node => node.tagName.toLowerCase()") == "section"
    assert await product_region.get_attribute("role") is None
    assert await product_region.get_attribute("aria-label") == expected[
      "products_region_aria_label"
    ]
    assert await product_region.get_attribute("aria-labelledby") == expected[
      "products_region_aria_labelledby"
    ]
    assert await page.get_by_role(
      "region",
      name=expected["products_region_name"],
    ).is_visible()
    assert await product_region.get_by_role(
      "heading",
      name="Featured products",
    ).is_visible()
    region_text = (await product_region.text_content()) or ""
    for product_name in ("Desk lamp", "Notebook set", "Cable organizer"):
      assert product_name in region_text

    assert ((await products_link.text_content()) or "").strip() == "Products"
    assert await products_link.get_attribute("href") == "/products"
    assert await products_link.get_attribute("aria-current") == "page"
    assert await products_link.get_attribute("aria-label") is None
    assert await nav.get_by_role("link", name="Products").is_visible()

    assert ((await cart_link.text_content()) or "").strip() == expected[
      "cart_visible_text"
    ]
    assert await cart_link.get_attribute("href") == "/cart"
    assert await cart_link.get_attribute("aria-current") is None
    assert await cart_link.get_attribute("aria-label") == expected["cart_aria_label"]
    assert await nav.get_by_role(
      "link",
      name=expected["cart_accessible_name"],
    ).is_visible()

    assert await page.locator("main").get_attribute("aria-label") is None
    assert await footer.evaluate("node => node.tagName.toLowerCase()") == expected["footer_tag"]
    assert await footer.get_attribute("role") == expected["footer_role"]
    assert await footer.get_attribute("aria-label") == expected["footer_aria_label"]
    footer_text = (await footer.text_content()) or ""
    assert "AccessGraph Shop" in footer_text
    assert "Demo checkout experience" in footer_text
    assert "2026 AccessGraph Shop" in footer_text
    if expected["footer_name"] is None:
      assert await page.get_by_role(expected["footer_landmark_role"]).is_visible()
    else:
      assert await page.get_by_role(
        expected["footer_landmark_role"],
        name=expected["footer_name"],
      ).is_visible()
    if expected["footer_landmark_role"] == "search":
      assert await page.get_by_role("contentinfo").count() == 0

    await cart_link.click()
    await page.wait_for_url("**/cart")

    assert await page.title() == "Cart | Brightlane Checkout"
    assert await page.locator("h1", has_text="Cart").is_visible()
    assert await page.locator('[data-testid="cart-list"]').is_visible()
    progress = page.locator('[data-testid="checkout-progress"]')
    assert await progress.evaluate("node => node.tagName.toLowerCase()") == "section"
    assert await progress.get_attribute("role") is None
    assert await progress.get_attribute("aria-label") == expected.get(
      "progress_aria_label"
    )
    assert await progress.get_attribute("aria-labelledby") == expected.get(
      "progress_aria_labelledby",
      "checkout-progress-heading",
    )
    assert await page.get_by_role(
      "region",
      name=expected.get("progress_name", "Checkout progress"),
      exact=True,
    ).is_visible()
    assert await progress.get_by_role(
      "heading",
      level=2,
      name="Checkout progress",
      exact=True,
    ).is_visible()
    cart_step = progress.locator(
      '[data-testid="checkout-progress-cart"]'
    )
    assert await cart_step.get_attribute("aria-current") == "step"
    assert (
      await cart_step.locator(".progress-label").text_content()
      == "Cart"
    )
    assert (
      await cart_step.locator(".progress-state").text_content()
      == "Current step"
    )
    for step_id, label in (
      ("address", "Shipping address"),
      ("payment", "Payment"),
      ("review", "Review"),
    ):
      step = progress.locator(f'[data-testid="checkout-progress-{step_id}"]')
      assert await step.get_attribute("aria-current") is None
      assert await step.locator(".progress-label").text_content() == label
      assert await step.locator(".progress-state").text_content() == "Not started"
    order_totals = page.locator('[data-testid="cart-totals-region"]')
    assert await order_totals.evaluate("node => node.tagName.toLowerCase()") == "aside"
    assert await order_totals.get_attribute("role") == expected["order_totals_role"]
    assert await order_totals.get_attribute("aria-label") == "Order totals"
    assert await page.get_by_role(
      expected["order_totals_landmark_role"],
      name="Order totals",
    ).is_visible()
    order_totals_text = (await order_totals.text_content()) or ""
    for expected_text in (
      "Cart summary",
      "Order total",
      "Delivery estimate",
      "Shipping information",
      "Continue to address",
    ):
      assert expected_text in order_totals_text
    assert await nav.get_attribute("aria-label") == expected["nav_name"]
    assert await page.locator('[data-testid="nav-products"]').get_attribute(
      "aria-current",
    ) is None
    assert await page.locator('[data-testid="nav-cart"]').get_attribute(
      "aria-current",
    ) == "page"
    assert (
      ((await page.locator('[data-testid="nav-cart"]').text_content()) or "")
      .strip()
    ) == expected["cart_visible_text"]

  for profile, expected in NAVIGATION_LANDMARK_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected=expected: assert_landmark_state(
          page,
          expected=expected,
        ),
        profile=profile,
      )
    )


def test_address_totals_landmark_name_case_preserves_role_content_and_neighbor():
  async def assert_address_landmarks(
    page,
    *,
    expected_totals_name: str,
  ) -> None:
    await page.locator('[data-testid="nav-cart"]').click()
    await page.wait_for_url("**/cart")
    await page.locator('[data-testid="continue-to-address"]').click()
    await page.wait_for_url("**/checkout/address")

    assert page.url.endswith("/checkout/address")
    assert await page.title() == "Shipping address | Brightlane Checkout"
    assert await page.get_by_role(
      "heading",
      level=1,
      name="Shipping address",
      exact=True,
    ).is_visible()

    progress = page.get_by_role("region", name="Checkout progress", exact=True)
    assert await progress.locator(
      '[data-testid="checkout-progress-address"]'
    ).get_attribute("aria-current") == "step"

    shipping_details = page.locator("section.form-section")
    assert await shipping_details.evaluate(
      "node => node.tagName.toLowerCase()"
    ) == "section"
    assert await shipping_details.get_attribute("role") is None
    assert await shipping_details.get_attribute("aria-label") is None
    assert await shipping_details.get_attribute("aria-labelledby") == (
      "address-form-heading"
    )
    assert await page.get_by_role(
      "region",
      name="Shipping details",
      exact=True,
    ).is_visible()
    assert await shipping_details.get_by_role(
      "heading",
      level=2,
      name="Shipping details",
      exact=True,
    ).is_visible()
    assert await shipping_details.locator('[data-testid="address-form"]').is_visible()
    assert "Enter the shipping address for this order." in (
      (await shipping_details.text_content()) or ""
    )

    order_totals = page.locator('[data-testid="address-totals-region"]')
    assert await order_totals.evaluate(
      "node => node.tagName.toLowerCase()"
    ) == "aside"
    assert await order_totals.get_attribute("role") is None
    assert await order_totals.get_attribute("aria-labelledby") is None
    assert await order_totals.get_attribute("aria-label") == expected_totals_name
    assert await page.get_by_role(
      "complementary",
      name=expected_totals_name,
      exact=True,
    ).is_visible()

    totals_text = (await order_totals.text_content()) or ""
    for expected_text in (
      "Cart summary",
      "Items",
      "1 item",
      "Subtotal",
      "$32.00",
      "Shipping",
      "$5.00",
      "Order total",
      "$37.00",
    ):
      assert expected_text in totals_text

    assert await page.locator("main").count() == 1
    assert await page.locator('[data-testid="continue-to-payment"]').is_visible()

  for profile, expected_totals_name in ADDRESS_TOTALS_LANDMARK_CASES.items():
    asyncio.run(
      _with_checkout_page(
        lambda page, expected_totals_name=expected_totals_name: (
          assert_address_landmarks(
            page,
            expected_totals_name=expected_totals_name,
          )
        ),
        profile=profile,
      )
    )
