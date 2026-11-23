from __future__ import annotations

import asyncio

from tests.test_checkout_product_category_tabs import _with_checkout_page


BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-068",
  "checkout-co-sem-069",
  "checkout-co-sem-070",
  "checkout-co-sem-071",
  "checkout-co-sem-072",
  "checkout-co-sem-073",
  "checkout-co-sem-090",
)

DISCLOSURE_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-066",
  "checkout-co-sem-067",
  "checkout-co-sem-068",
  "checkout-co-sem-070",
  "checkout-co-sem-071",
  "checkout-co-sem-072",
  "checkout-co-sem-073",
  "checkout-co-sem-090",
)

SWITCH_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-066",
  "checkout-co-sem-067",
  "checkout-co-sem-068",
  "checkout-co-sem-069",
  "checkout-co-sem-070",
  "checkout-co-sem-072",
  "checkout-co-sem-073",
  "checkout-co-sem-090",
)

PRESSED_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-066",
  "checkout-co-sem-067",
  "checkout-co-sem-068",
  "checkout-co-sem-069",
  "checkout-co-sem-070",
  "checkout-co-sem-071",
  "checkout-co-sem-090",
)

PROGRESS_BASELINE_PROFILES = (
  None,
  "checkout-clean-v1",
  "checkout-unknown-profile",
  "checkout-co-sem-090",
)


async def _assert_desk_tab_actual_state(
  page,
  *,
  expected_desk_aria_selected: str,
) -> None:
  desk_tab = page.locator('[data-testid="product-category-tab-desk-accessories"]')
  office_tab = page.locator('[data-testid="product-category-tab-office-supplies"]')
  desk_panel = page.locator("#desk-accessories-panel")
  office_panel = page.locator("#office-supplies-panel")

  assert await page.locator("h1", has_text="Products").is_visible()
  assert await page.get_by_role("tablist", name="Product categories").is_visible()
  assert await desk_tab.get_attribute("role") == "tab"
  assert await office_tab.get_attribute("role") == "tab"
  assert await desk_tab.get_attribute("id") == "desk-accessories-tab"
  assert await office_tab.get_attribute("id") == "office-supplies-tab"
  assert await desk_tab.get_attribute("aria-controls") == "desk-accessories-panel"
  assert await office_tab.get_attribute("aria-controls") == "office-supplies-panel"
  assert ((await desk_tab.text_content()) or "").strip() == "Desk accessories"
  assert ((await office_tab.text_content()) or "").strip() == "Office supplies"

  assert await desk_tab.get_attribute("aria-selected") == expected_desk_aria_selected
  assert await office_tab.get_attribute("aria-selected") == "false"
  assert await desk_tab.get_attribute("tabindex") == "0"
  assert await office_tab.get_attribute("tabindex") == "-1"

  desk_classes = ((await desk_tab.get_attribute("class")) or "").split()
  office_classes = ((await office_tab.get_attribute("class")) or "").split()
  assert "is-selected" in desk_classes
  assert "is-selected" not in office_classes

  assert await desk_panel.get_attribute("role") == "tabpanel"
  assert await desk_panel.get_attribute("aria-labelledby") == "desk-accessories-tab"
  assert await office_panel.get_attribute("role") == "tabpanel"
  assert await office_panel.get_attribute("aria-labelledby") == "office-supplies-tab"
  assert await desk_panel.is_visible()
  assert not await office_panel.is_visible()
  assert "Desk lamp" in ((await desk_panel.text_content()) or "")
  assert "Cable organizer" in ((await desk_panel.text_content()) or "")
  assert "Notebook set" in ((await office_panel.text_content()) or "")


async def _assert_tab_switching_still_uses_application_state(
  page,
  *,
  office_selected_aria: tuple[str, str] = ("false", "true"),
  desk_reselected_aria: tuple[str, str] = ("true", "false"),
) -> None:
  desk_tab = page.locator('[data-testid="product-category-tab-desk-accessories"]')
  office_tab = page.locator('[data-testid="product-category-tab-office-supplies"]')
  desk_panel = page.locator("#desk-accessories-panel")
  office_panel = page.locator("#office-supplies-panel")

  await office_tab.click()
  assert await office_tab.get_attribute("tabindex") == "0"
  assert await desk_tab.get_attribute("tabindex") == "-1"
  assert "is-selected" in (((await office_tab.get_attribute("class")) or "").split())
  assert "is-selected" not in (((await desk_tab.get_attribute("class")) or "").split())
  assert await office_panel.is_visible()
  assert not await desk_panel.is_visible()
  assert await desk_tab.get_attribute("aria-selected") == office_selected_aria[0]
  assert await office_tab.get_attribute("aria-selected") == office_selected_aria[1]

  await desk_tab.click()
  assert await desk_tab.get_attribute("tabindex") == "0"
  assert await office_tab.get_attribute("tabindex") == "-1"
  assert "is-selected" in (((await desk_tab.get_attribute("class")) or "").split())
  assert "is-selected" not in (((await office_tab.get_attribute("class")) or "").split())
  assert await desk_panel.is_visible()
  assert not await office_panel.is_visible()
  assert await desk_tab.get_attribute("aria-selected") == desk_reselected_aria[0]
  assert await office_tab.get_attribute("aria-selected") == desk_reselected_aria[1]


def test_checkout_category_tabs_keep_baseline_aria_state_for_unrelated_profiles():
  async def run(page):
    await _assert_desk_tab_actual_state(
      page,
      expected_desk_aria_selected="true",
    )
    await _assert_tab_switching_still_uses_application_state(page)

  for profile in BASELINE_PROFILES:
    asyncio.run(_with_checkout_page(run, profile=profile))


def test_checkout_co_sem_066_marks_active_desk_tab_declared_unselected_only():
  async def run(page):
    await _assert_desk_tab_actual_state(
      page,
      expected_desk_aria_selected="false",
    )
    await _assert_tab_switching_still_uses_application_state(
      page,
      office_selected_aria=("false", "true"),
      desk_reselected_aria=("false", "false"),
    )

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-066"))


def test_checkout_co_sem_067_keeps_stale_declared_selection_after_office_activation():
  async def run(page):
    await _assert_desk_tab_actual_state(
      page,
      expected_desk_aria_selected="true",
    )
    await _assert_tab_switching_still_uses_application_state(
      page,
      office_selected_aria=("true", "false"),
      desk_reselected_aria=("true", "false"),
    )

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-067"))


async def _assert_delivery_estimate_collapsed(
  page,
  *,
  expected_aria_expanded: str,
) -> None:
  await page.get_by_role("link", name="Cart").click()
  await page.wait_for_url("**/cart")

  delivery_button = page.locator('[data-testid="delivery-estimate-trigger"]')
  delivery_panel = page.locator('[data-testid="delivery-estimate-panel"]')

  assert ((await delivery_button.text_content()) or "").strip() == "Delivery estimate"
  assert await delivery_button.get_attribute("aria-label") is None
  assert await delivery_button.get_attribute("aria-controls") == "delivery-estimate-panel"
  assert await delivery_button.get_attribute("aria-expanded") == expected_aria_expanded
  assert await delivery_panel.get_attribute("id") == "delivery-estimate-panel"
  assert await delivery_panel.get_attribute("hidden") == ""
  assert not await delivery_panel.is_visible()


def test_checkout_delivery_estimate_keeps_baseline_state_for_unrelated_profiles():
  async def run(page):
    await _assert_delivery_estimate_collapsed(
      page,
      expected_aria_expanded="false",
    )

  for profile in DISCLOSURE_BASELINE_PROFILES:
    asyncio.run(_with_checkout_page(run, profile=profile))


def test_checkout_co_sem_069_declares_collapsed_delivery_estimate_expanded_only():
  async def run(page):
    await _assert_delivery_estimate_collapsed(
      page,
      expected_aria_expanded="true",
    )

    delivery_button = page.locator('[data-testid="delivery-estimate-trigger"]')
    delivery_panel = page.locator('[data-testid="delivery-estimate-panel"]')

    await delivery_button.click()
    assert await delivery_button.get_attribute("aria-expanded") == "true"
    assert await delivery_panel.get_attribute("hidden") is None
    assert await delivery_panel.is_visible()
    assert "Standard delivery usually arrives in 3-5 business days after dispatch." in (
      (await delivery_panel.text_content()) or ""
    )

    await delivery_button.click()
    assert await delivery_button.get_attribute("aria-expanded") == "true"
    assert await delivery_panel.get_attribute("hidden") == ""
    assert not await delivery_panel.is_visible()

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-069"))


def test_checkout_co_sem_068_declares_expanded_delivery_estimate_collapsed_only():
  async def run(page):
    await _assert_delivery_estimate_collapsed(
      page,
      expected_aria_expanded="false",
    )

    delivery_button = page.locator('[data-testid="delivery-estimate-trigger"]')
    delivery_panel = page.locator('[data-testid="delivery-estimate-panel"]')

    await delivery_button.click()
    assert await delivery_button.get_attribute("aria-expanded") == "false"
    assert await delivery_panel.get_attribute("hidden") is None
    assert await delivery_panel.is_visible()
    assert "Standard delivery usually arrives in 3-5 business days after dispatch." in (
      (await delivery_panel.text_content()) or ""
    )

    await delivery_button.click()
    assert await delivery_button.get_attribute("aria-expanded") == "false"
    assert await delivery_panel.get_attribute("hidden") == ""
    assert not await delivery_panel.is_visible()

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-068"))


async def _assert_gift_receipt_off(
  page,
  *,
  expected_aria_checked: str,
) -> None:
  await page.get_by_role("link", name="Cart").click()
  await page.wait_for_url("**/cart")

  gift_receipt = page.locator('[data-testid="gift-receipt-switch"]')
  gift_receipt_note = page.locator('[data-testid="gift-receipt-note"]')

  assert await gift_receipt.get_attribute("role") == "switch"
  assert ((await gift_receipt.text_content()) or "").strip() == "Gift receipt"
  assert await gift_receipt.get_attribute("aria-checked") == expected_aria_checked
  assert "is-on" not in (
    ((await gift_receipt.get_attribute("class")) or "").split()
  )
  assert await gift_receipt_note.count() == 0


def test_checkout_gift_receipt_keeps_baseline_state_for_unrelated_profiles():
  async def run(page):
    await _assert_gift_receipt_off(
      page,
      expected_aria_checked="false",
    )

  for profile in SWITCH_BASELINE_PROFILES:
    asyncio.run(_with_checkout_page(run, profile=profile))


def test_checkout_co_sem_070_declares_enabled_gift_receipt_unchecked_only():
  async def run(page):
    await _assert_gift_receipt_off(
      page,
      expected_aria_checked="false",
    )

    gift_receipt = page.locator('[data-testid="gift-receipt-switch"]')
    gift_receipt_note = page.locator('[data-testid="gift-receipt-note"]')

    await gift_receipt.click()
    assert await gift_receipt.get_attribute("aria-checked") == "false"
    assert "is-on" in (
      ((await gift_receipt.get_attribute("class")) or "").split()
    )
    assert "A gift receipt will be included." in (
      (await gift_receipt_note.text_content()) or ""
    )

    await gift_receipt.click()
    assert await gift_receipt.get_attribute("aria-checked") == "false"
    assert "is-on" not in (
      ((await gift_receipt.get_attribute("class")) or "").split()
    )
    assert await gift_receipt_note.count() == 0

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-070"))


def test_checkout_co_sem_071_declares_disabled_gift_receipt_checked_only():
  async def run(page):
    await _assert_gift_receipt_off(
      page,
      expected_aria_checked="true",
    )

    gift_receipt = page.locator('[data-testid="gift-receipt-switch"]')
    gift_receipt_note = page.locator('[data-testid="gift-receipt-note"]')

    await gift_receipt.click()
    assert await gift_receipt.get_attribute("aria-checked") == "true"
    assert "is-on" in (
      ((await gift_receipt.get_attribute("class")) or "").split()
    )
    assert "A gift receipt will be included." in (
      (await gift_receipt_note.text_content()) or ""
    )

    await gift_receipt.click()
    assert await gift_receipt.get_attribute("aria-checked") == "true"
    assert "is-on" not in (
      ((await gift_receipt.get_attribute("class")) or "").split()
    )
    assert await gift_receipt_note.count() == 0

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-071"))


async def _assert_save_cart_inactive(
  page,
  *,
  expected_aria_pressed: str,
) -> None:
  await page.get_by_role("link", name="Cart").click()
  await page.wait_for_url("**/cart")

  save_cart = page.locator('[data-testid="save-cart-toggle"]')
  save_cart_note = page.locator('[data-testid="save-cart-note"]')

  assert ((await save_cart.text_content()) or "").strip() == "Save cart"
  assert await save_cart.get_attribute("aria-pressed") == expected_aria_pressed
  assert "is-saved" not in (
    ((await save_cart.get_attribute("class")) or "").split()
  )
  assert await save_cart_note.count() == 0


def test_checkout_save_cart_keeps_baseline_state_for_unrelated_profiles():
  async def run(page):
    await _assert_save_cart_inactive(
      page,
      expected_aria_pressed="false",
    )

  for profile in PRESSED_BASELINE_PROFILES:
    asyncio.run(_with_checkout_page(run, profile=profile))


async def _assert_save_cart_active(
  page,
  *,
  expected_aria_pressed: str,
) -> None:
  save_cart = page.locator('[data-testid="save-cart-toggle"]')
  save_cart_note = page.locator('[data-testid="save-cart-note"]')

  await save_cart.click()
  assert await save_cart.get_attribute("aria-pressed") == expected_aria_pressed
  assert "is-saved" in (
    ((await save_cart.get_attribute("class")) or "").split()
  )
  assert "Cart saved for later." in (
    (await save_cart_note.text_content()) or ""
  )


def test_checkout_save_cart_active_state_is_correct_without_pressed_override():
  async def run(page):
    await _assert_save_cart_inactive(
      page,
      expected_aria_pressed="false",
    )
    await _assert_save_cart_active(
      page,
      expected_aria_pressed="true",
    )

  asyncio.run(_with_checkout_page(run, profile=None))


def test_checkout_co_sem_072_declares_saved_cart_unpressed_only():
  async def run(page):
    await _assert_save_cart_inactive(
      page,
      expected_aria_pressed="false",
    )
    await _assert_save_cart_active(
      page,
      expected_aria_pressed="false",
    )

    save_cart = page.locator('[data-testid="save-cart-toggle"]')
    save_cart_note = page.locator('[data-testid="save-cart-note"]')
    await save_cart.click()
    assert await save_cart.get_attribute("aria-pressed") == "false"
    assert "is-saved" not in (
      ((await save_cart.get_attribute("class")) or "").split()
    )
    assert await save_cart_note.count() == 0

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-072"))


def test_checkout_co_sem_073_declares_unsaved_cart_pressed_only():
  async def run(page):
    await _assert_save_cart_inactive(
      page,
      expected_aria_pressed="true",
    )

    save_cart = page.locator('[data-testid="save-cart-toggle"]')
    save_cart_note = page.locator('[data-testid="save-cart-note"]')

    await save_cart.click()
    assert await save_cart.get_attribute("aria-pressed") == "true"
    assert "is-saved" in (
      ((await save_cart.get_attribute("class")) or "").split()
    )
    assert "Cart saved for later." in (
      (await save_cart_note.text_content()) or ""
    )

    await save_cart.click()
    assert await save_cart.get_attribute("aria-pressed") == "true"
    assert "is-saved" not in (
      ((await save_cart.get_attribute("class")) or "").split()
    )
    assert await save_cart_note.count() == 0

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-073"))


async def _assert_cart_progress_current_mapping(
  page,
  *,
  declared_current_step: str,
) -> None:
  await page.get_by_role("link", name="Cart").click()
  await page.wait_for_url("**/cart")

  assert page.url.endswith("/cart")
  assert await page.title() == "Cart | Brightlane Checkout"
  assert await page.locator("h1", has_text="Cart").is_visible()
  assert await page.locator('[data-testid="cart-list"]').is_visible()
  assert await page.locator('[data-testid="cart-totals-region"]').is_visible()
  assert await page.locator('[data-testid="continue-to-address"]').is_visible()

  progress = page.get_by_role("region", name="Checkout progress", exact=True)
  steps = (
    ("cart", "Cart", "Current step"),
    ("address", "Shipping address", "Not started"),
    ("payment", "Payment", "Not started"),
    ("review", "Review", "Not started"),
  )
  for step_id, label, state_label in steps:
    step = progress.locator(f'[data-testid="checkout-progress-{step_id}"]')
    assert await step.locator(".progress-label").text_content() == label
    assert await step.locator(".progress-state").text_content() == state_label
    classes = ((await step.get_attribute("class")) or "").split()
    assert ("is-current" in classes) is (step_id == "cart")
    expected_aria_current = "step" if step_id == declared_current_step else None
    assert await step.get_attribute("aria-current") == expected_aria_current

  assert await progress.locator('[aria-current="step"]').count() == 1


async def _assert_address_progress_current_mapping(
  page,
  *,
  declared_current_step: str,
) -> None:
  await _assert_cart_progress_current_mapping(
    page,
    declared_current_step="cart",
  )

  await page.locator('[data-testid="continue-to-address"]').click()
  await page.wait_for_url("**/checkout/address")

  assert page.url.endswith("/checkout/address")
  assert await page.title() == "Shipping address | Brightlane Checkout"
  assert await page.get_by_role(
    "heading",
    name="Shipping address",
    exact=True,
  ).is_visible()
  assert await page.get_by_role(
    "heading",
    name="Shipping details",
    exact=True,
  ).is_visible()
  assert await page.locator('[data-testid="address-form"]').is_visible()
  assert await page.locator('[data-testid="continue-to-payment"]').is_visible()

  expected_fields = (
    ("address-full-name", "address-fullName", "Full name"),
    ("address-email", "address-email", "Email"),
    ("address-street", "address-streetAddress", "Street address"),
    ("address-city", "address-city", "City"),
    ("address-state", "address-state", "State"),
    ("address-postal-code", "address-postalCode", "ZIP code"),
  )
  for test_id, field_id, label in expected_fields:
    field = page.locator(f'[data-testid="{test_id}"]')
    assert await field.is_visible()
    assert await field.get_attribute("id") == field_id
    assert (
      (
        await page.locator(f'label[for="{field_id}"] > span').first.text_content()
      )
      or ""
    ).strip() == label

  progress = page.get_by_role("region", name="Checkout progress", exact=True)
  steps = (
    ("cart", "Cart", "Previous step"),
    ("address", "Shipping address", "Current step"),
    ("payment", "Payment", "Not started"),
    ("review", "Review", "Not started"),
  )
  for step_id, label, state_label in steps:
    step = progress.locator(f'[data-testid="checkout-progress-{step_id}"]')
    assert await step.locator(".progress-label").text_content() == label
    assert await step.locator(".progress-state").text_content() == state_label
    classes = ((await step.get_attribute("class")) or "").split()
    assert ("is-current" in classes) is (step_id == "address")
    expected_aria_current = "step" if step_id == declared_current_step else None
    assert await step.get_attribute("aria-current") == expected_aria_current

  assert await progress.locator('[aria-current="step"]').count() == 1


def test_checkout_progress_keeps_baseline_current_mapping_for_unrelated_profiles():
  for profile in PROGRESS_BASELINE_PROFILES:
    asyncio.run(
      _with_checkout_page(
        lambda page: _assert_cart_progress_current_mapping(
          page,
          declared_current_step="cart",
        ),
        profile=profile,
      )
    )


def test_checkout_co_sem_127_declares_shipping_current_while_cart_remains_actual():
  asyncio.run(
    _with_checkout_page(
      lambda page: _assert_cart_progress_current_mapping(
        page,
        declared_current_step="address",
      ),
      profile="checkout-co-sem-127",
    )
  )


def test_checkout_progress_moves_current_mapping_to_address_in_clean_profile():
  asyncio.run(
    _with_checkout_page(
      lambda page: _assert_address_progress_current_mapping(
        page,
        declared_current_step="address",
      ),
      profile="checkout-clean-v1",
    )
  )


def test_checkout_co_sem_128_keeps_cart_current_after_address_transition():
  asyncio.run(
    _with_checkout_page(
      lambda page: _assert_address_progress_current_mapping(
        page,
        declared_current_step="cart",
      ),
      profile="checkout-co-sem-128",
    )
  )


def test_checkout_co_sem_129_declares_spanish_pressed_while_locale_remains_english():
  async def run(page):
    english = page.locator('[data-testid="products-language-en"]')
    spanish = page.locator('[data-testid="products-language-es"]')
    route = page.locator('[data-testid="route-products"]')
    route_text = (await route.inner_text()) or ""

    assert page.url.endswith("/products")
    assert await page.evaluate("document.documentElement.lang") == "en"
    assert await page.title() == "Products | Brightlane Checkout"
    assert await page.get_by_role("heading", name="Products", exact=True).is_visible()
    assert await page.get_by_role("navigation", name="Checkout routes").is_visible()
    assert "Browse featured products and update the cart summary." in route_text
    assert "Featured products" in route_text
    assert "Desk lamp" in route_text
    assert "Add Desk lamp" in route_text
    assert "Productos destacados" not in route_text

    assert ((await english.text_content()) or "").strip() == "English"
    assert ((await spanish.text_content()) or "").strip() == "Spanish"
    assert await english.get_attribute("role") == "button"
    assert await spanish.get_attribute("role") == "button"
    assert await english.get_attribute("aria-pressed") == "false"
    assert await spanish.get_attribute("aria-pressed") == "true"
    assert "is-selected" in ((await english.get_attribute("class")) or "").split()
    assert "is-selected" not in ((await spanish.get_attribute("class")) or "").split()
    assert await route.locator('[aria-pressed="true"]').count() == 1

    await spanish.click()
    assert await page.evaluate("document.documentElement.lang") == "es"
    assert await page.get_by_role("heading", name="Productos", exact=True).is_visible()
    assert "is-selected" not in ((await english.get_attribute("class")) or "").split()
    assert "is-selected" in ((await spanish.get_attribute("class")) or "").split()
    assert await english.get_attribute("aria-pressed") == "false"
    assert await spanish.get_attribute("aria-pressed") == "true"
    assert await route.locator('[aria-pressed="true"]').count() == 1

  asyncio.run(_with_checkout_page(run, profile="checkout-co-sem-129"))


def test_checkout_co_sem_130_keeps_initial_language_state_clean_then_stale_after_spanish():
  async def assert_language_transition(page, *, expected_result_pressed):
    origin = await page.evaluate("window.location.origin")
    await page.goto(f"{origin}/products", wait_until="domcontentloaded")
    english = page.locator('[data-testid="products-language-en"]')
    spanish = page.locator('[data-testid="products-language-es"]')
    route = page.locator('[data-testid="route-products"]')

    assert page.url.endswith("/products")
    assert await page.evaluate("document.documentElement.lang") == "en"
    assert ((await english.text_content()) or "").strip() == "English"
    assert ((await spanish.text_content()) or "").strip() == "Spanish"
    assert await english.get_attribute("aria-pressed") == "true"
    assert await spanish.get_attribute("aria-pressed") == "false"
    assert "is-selected" in ((await english.get_attribute("class")) or "").split()
    assert "is-selected" not in ((await spanish.get_attribute("class")) or "").split()

    await spanish.click()
    route_text = (await route.inner_text()) or ""

    assert page.url.endswith("/products")
    assert await page.evaluate("document.documentElement.lang") == "es"
    assert await page.title() == "Productos | Brightlane Checkout"
    assert await page.get_by_role("heading", name="Productos", exact=True).is_visible()
    assert "Explora productos destacados y actualiza el resumen del carrito." in route_text
    assert "Productos destacados" in route_text
    assert "Lámpara de escritorio" in route_text
    assert ((await english.text_content()) or "").strip() == "Inglés"
    assert ((await spanish.text_content()) or "").strip() == "Español"
    assert await english.get_attribute("aria-pressed") == expected_result_pressed[0]
    assert await spanish.get_attribute("aria-pressed") == expected_result_pressed[1]
    assert "is-selected" not in ((await english.get_attribute("class")) or "").split()
    assert "is-selected" in ((await spanish.get_attribute("class")) or "").split()

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_language_transition(
        page,
        expected_result_pressed=("false", "true"),
      ),
      profile="checkout-clean-v1",
    )
  )
  asyncio.run(
    _with_checkout_page(
      lambda page: assert_language_transition(
        page,
        expected_result_pressed=("true", "false"),
      ),
      profile="checkout-co-sem-130",
    )
  )
