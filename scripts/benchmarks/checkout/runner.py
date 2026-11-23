from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Page, async_playwright

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from src.crawler.state.focused_run import (
  FocusedRunRecorder,
  FocusedStateSpec,
  capture_focused_transition_trigger,
)
from scripts.benchmarks.checkout.spa_process import (
  CHECKOUT_DIR,
  CHECKOUT_PUBLIC_DIR,
  CONTROLLED_SUPPORT_HOST,
  CONTROLLED_SUPPORT_ORIGIN,
  CONTROLLED_SUPPORT_PORT,
  CONTROLLED_SUPPORT_RESOURCE_PATH,
  CONTROLLED_SUPPORT_RESOURCE_URL,
  CONTROLLED_SUPPORT_RETURNS_PATH,
  CONTROLLED_SUPPORT_RETURNS_URL,
  build_checkout_app as _build_app,
  find_free_port as _find_free_port,
  requires_controlled_support_destination as _requires_controlled_support_destination_capture,
  run_command as _run_command,
  start_controlled_support_server as _start_controlled_support_server,
  start_vite_preview as _start_vite_preview,
  stop_process as _stop_process,
  wait_for_url as _wait_for_url,
)

DEFAULT_RUNS_ROOT = REPO_ROOT / "runs" / "benchmark" / "checkout_flow"
CLEAN_PROFILE = "checkout-clean-v1"
LANGUAGE_SWITCH_PROFILES = frozenset({
  "checkout-co-sem-012",
  "checkout-co-sem-014",
  "checkout-co-sem-015",
  "checkout-co-sem-019",
  "checkout-co-sem-130",
  "checkout-co-sem-137",
  "checkout-co-sem-138",
})
LANGUAGE_SWITCH_SPANISH_ROOT_LANG_BY_PROFILE = {
  "checkout-co-sem-012": "en",
  "checkout-co-sem-014": "es",
  "checkout-co-sem-015": "en",
  "checkout-co-sem-019": "es",
  "checkout-co-sem-130": "es",
  "checkout-co-sem-137": "es",
  "checkout-co-sem-138": "es",
}
LANGUAGE_SWITCH_SPANISH_ARIA_PRESSED_BY_PROFILE = {
  "checkout-co-sem-130": "false",
}
LANGUAGE_SWITCH_BACK_TO_ENGLISH_PROFILES = frozenset({
  "checkout-co-sem-137",
})
LANGUAGE_SWITCH_BACK_BENCHMARK_STATE_ID = "CO-S020"
LANGUAGE_SWITCH_BACK_FOCUSED_STATE = "products_english_restored"
CHECKOUT_PROFILE_GLOBAL = "__ACCESSGRAPH_CHECKOUT_PROFILE__"
CHECKOUT_SUPPORT_ORIGIN_GLOBAL = "__ACCESSGRAPH_CHECKOUT_SUPPORT_ORIGIN__"
CONTROLLED_SUPPORT_LINK_SELECTOR = '[data-testid="support-returns"]'
CONTROLLED_SUPPORT_SHIPPING_LINK_SELECTOR = '[data-testid="support-shipping"]'
CONTROLLED_SUPPORT_CAPTURE_BY_PROFILE = {
  "checkout-co-sem-027": {
    "link_selector": CONTROLLED_SUPPORT_LINK_SELECTOR,
    "source_url": CONTROLLED_SUPPORT_RETURNS_URL,
  },
  "checkout-co-sem-102": {
    "link_selector": CONTROLLED_SUPPORT_SHIPPING_LINK_SELECTOR,
    "source_url": CONTROLLED_SUPPORT_RESOURCE_URL,
  },
}
CONTROLLED_SUPPORT_DESTINATION_BENCHMARK_STATE_ID = "CO-S008"
CONTROLLED_SUPPORT_DESTINATION_FOCUSED_STATE = "controlled_support_destination"
DELIVERY_ESTIMATE_EXPANDED_PROFILE = "checkout-co-sem-068"
DELIVERY_ESTIMATE_WRONG_RESULT_PROFILE = "checkout-co-sem-089"
DELIVERY_ESTIMATE_TRIGGER_SELECTOR = '[data-testid="delivery-estimate-trigger"]'
DELIVERY_ESTIMATE_PANEL_SELECTOR = '[data-testid="delivery-estimate-panel"]'
DELIVERY_ESTIMATE_EXPANDED_BENCHMARK_STATE_ID = "CO-S013"
DELIVERY_ESTIMATE_EXPANDED_FOCUSED_STATE = "cart_delivery_estimate_expanded"
GIFT_RECEIPT_ENABLED_PROFILE = "checkout-co-sem-070"
GIFT_RECEIPT_SWITCH_SELECTOR = '[data-testid="gift-receipt-switch"]'
GIFT_RECEIPT_NOTE_SELECTOR = '[data-testid="gift-receipt-note"]'
GIFT_RECEIPT_ENABLED_BENCHMARK_STATE_ID = "CO-S014"
GIFT_RECEIPT_ENABLED_FOCUSED_STATE = "cart_gift_receipt_enabled"
SAVE_CART_ACTIVE_PROFILE = "checkout-co-sem-072"
SAVE_CART_TOGGLE_SELECTOR = '[data-testid="save-cart-toggle"]'
SAVE_CART_NOTE_SELECTOR = '[data-testid="save-cart-note"]'
SAVE_CART_ACTIVE_BENCHMARK_STATE_ID = "CO-S015"
SAVE_CART_ACTIVE_FOCUSED_STATE = "cart_saved"
SHIPPING_INFORMATION_DIALOG_PROFILE = "checkout-co-sem-138"
SHIPPING_INFORMATION_TRIGGER_SELECTOR = '[data-testid="shipping-information-trigger"]'
SHIPPING_INFORMATION_DIALOG_SELECTOR = '[data-testid="shipping-information-dialog"]'
SHIPPING_INFORMATION_BODY_SELECTOR = '[data-testid="shipping-information-body"]'
SHIPPING_INFORMATION_DIALOG_BENCHMARK_STATE_ID = "CO-S016"
SHIPPING_INFORMATION_DIALOG_FOCUSED_STATE = "cart_shipping_information_dialog"
EMPTY_CART_CAPTURE_PROFILE = "checkout-co-sem-092"
EMPTY_CART_DECREMENT_SELECTOR = '[data-testid="cart-decrement-prod-desk-lamp"]'
EMPTY_CART_HEADING_SELECTOR = "#empty-cart-heading"
EMPTY_CART_BENCHMARK_STATE_ID = "CO-S017"
EMPTY_CART_FOCUSED_STATE = "cart_empty"
DELIVERY_ESTIMATE_WRONG_RESULT_BENCHMARK_STATE_ID = "CO-S009"
DELIVERY_ESTIMATE_WRONG_RESULT_FOCUSED_STATE = "cart_delivery_estimate_shipping_dialog"
ADDRESS_CONTINUE_WRONG_RESULT_PROFILE = "checkout-co-sem-103"
ADDRESS_CONTINUE_TO_PAYMENT_SELECTOR = '[data-testid="continue-to-payment"]'
ADDRESS_CONTINUE_WRONG_RESULT_BENCHMARK_STATE_ID = "CO-S018"
ADDRESS_CONTINUE_WRONG_RESULT_FOCUSED_STATE = "address_continue_to_payment_cart"
CART_QUANTITY_WRONG_OBJECT_PROFILE = "checkout-co-sem-104"
DESK_LAMP_INCREMENT_SELECTOR = '[data-testid="cart-increment-prod-desk-lamp"]'
DESK_LAMP_CART_QUANTITY_SELECTOR = '[data-testid="cart-quantity-prod-desk-lamp"]'
NOTEBOOK_SET_INCREMENT_SELECTOR = '[data-testid="cart-increment-prod-notebook-set"]'
NOTEBOOK_SET_CART_QUANTITY_SELECTOR = '[data-testid="cart-quantity-prod-notebook-set"]'
CART_QUANTITY_RESULT_BENCHMARK_STATE_ID = "CO-S019"
CART_QUANTITY_RESULT_FOCUSED_STATE = "cart_quantity_result"
OFFICE_CATEGORY_CAPTURE_PROFILE = "checkout-co-sem-067"
DESK_CATEGORY_TAB_SELECTOR = '[data-testid="product-category-tab-desk-accessories"]'
OFFICE_CATEGORY_TAB_SELECTOR = '[data-testid="product-category-tab-office-supplies"]'
DESK_CATEGORY_PANEL_SELECTOR = '[data-testid="product-category-panel-desk-accessories"]'
OFFICE_CATEGORY_PANEL_SELECTOR = '[data-testid="product-category-panel-office-supplies"]'
OFFICE_CATEGORY_BENCHMARK_STATE_ID = "CO-S012"
OFFICE_CATEGORY_FOCUSED_STATE = "products_office_supplies"
TWO_ITEM_REVIEW_PROFILES = frozenset({
  "checkout-co-sem-131",
  "checkout-co-sem-132",
})
NOTEBOOK_SET_ADD_SELECTOR = '[data-testid="product-add-prod-notebook-set"]'
NOTEBOOK_SET_QUANTITY_SELECTOR = '[data-testid="product-quantity-prod-notebook-set"]'
POSTAL_CODE_FORMAT_INVALID_BENCHMARK_STATE_ID = "CO-S022"
POSTAL_CODE_FORMAT_INVALID_FOCUSED_STATE = "address_postal_code_format_error"
EMAIL_FORMAT_INVALID_BENCHMARK_STATE_ID = "CO-S021"
EMAIL_FORMAT_INVALID_FOCUSED_STATE = "address_email_format_error"
SECURITY_CODE_FORMAT_INVALID_BENCHMARK_STATE_ID = "CO-S023"
SECURITY_CODE_FORMAT_INVALID_FOCUSED_STATE = "payment_security_code_format_error"
INVALID_ADDRESS_SUBMIT_SCENARIOS = {
  "checkout-co-sem-076": {
    "empty_test_id": "address-email",
    "error_selector": "#address-email-error",
    "benchmark_state_id": "CO-S010",
    "focused_state_name": "address_email_error",
    "action_path": ["Products", "Cart", "Address", "Submit address with Email empty"],
    "transition_text": "Submit address with Email empty",
  },
  "checkout-co-sem-077": {
    "empty_test_id": "address-postal-code",
    "error_selector": "#address-postalCode-error",
    "benchmark_state_id": "CO-S010",
    "focused_state_name": "address_postal_code_error",
    "action_path": ["Products", "Cart", "Address", "Submit address with ZIP code empty"],
    "transition_text": "Submit address with ZIP code empty",
  },
  "checkout-co-sem-078": {
    "empty_test_id": "address-full-name",
    "error_selector": "#address-fullName-error",
    "benchmark_state_id": "CO-S010",
    "focused_state_name": "address_full_name_error",
    "action_path": ["Products", "Cart", "Address", "Submit address with Full name empty"],
    "transition_text": "Submit address with Full name empty",
  },
  "checkout-co-sem-134": {
    "empty_test_id": "address-postal-code",
    "error_selector": "#address-postalCode-error",
    "benchmark_state_id": "CO-S010",
    "focused_state_name": "address_postal_code_required_error",
    "action_path": ["Products", "Cart", "Address", "Submit address with ZIP code empty"],
    "transition_text": "Submit address with ZIP code empty",
    "changed_value": "1234",
    "changed_error_text": "ZIP code is required.",
    "changed_benchmark_state_id": POSTAL_CODE_FORMAT_INVALID_BENCHMARK_STATE_ID,
    "changed_focused_state_name": POSTAL_CODE_FORMAT_INVALID_FOCUSED_STATE,
    "changed_action_path": [
      "Products",
      "Cart",
      "Address",
      "Submit address with ZIP code empty",
      "Enter malformed ZIP code",
    ],
    "changed_transition_text": "Enter malformed ZIP code",
    "changed_native_validity": {
      "valid": False,
      "value_missing": False,
      "type_mismatch": False,
      "pattern_mismatch": True,
      "too_long": False,
      "too_short": False,
      "range_underflow": False,
      "range_overflow": False,
      "step_mismatch": False,
      "bad_input": False,
      "custom_error": False,
    },
  },
  "checkout-co-sem-135": {
    "empty_test_id": "address-email",
    "error_selector": "#address-email-error",
    "benchmark_state_id": "CO-S010",
    "focused_state_name": "address_email_required_error",
    "action_path": ["Products", "Cart", "Address", "Submit address with Email empty"],
    "transition_text": "Submit address with Email empty",
    "changed_value": "invalid-email",
    "changed_error_text": "Email is required.",
    "changed_benchmark_state_id": EMAIL_FORMAT_INVALID_BENCHMARK_STATE_ID,
    "changed_focused_state_name": EMAIL_FORMAT_INVALID_FOCUSED_STATE,
    "changed_action_path": [
      "Products",
      "Cart",
      "Address",
      "Submit address with Email empty",
      "Enter malformed Email",
    ],
    "changed_transition_text": "Enter malformed Email",
    "changed_native_validity": {
      "valid": False,
      "value_missing": False,
      "type_mismatch": True,
      "pattern_mismatch": True,
      "too_long": False,
      "too_short": False,
      "range_underflow": False,
      "range_overflow": False,
      "step_mismatch": False,
      "bad_input": False,
      "custom_error": False,
    },
  },
}
INVALID_PAYMENT_SUBMIT_SCENARIOS = {
  "checkout-co-sem-079": {
    "empty_test_id": "payment-card-number",
    "error_selector": "#payment-cardNumber-error",
    "benchmark_state_id": "CO-S011",
    "focused_state_name": "payment_card_number_error",
    "action_path": ["Products", "Cart", "Address", "Payment", "Submit payment with Card number empty"],
    "transition_text": "Submit payment with Card number empty",
  },
  "checkout-co-sem-080": {
    "empty_test_id": "payment-security-code",
    "error_selector": "#payment-securityCode-error",
    "benchmark_state_id": "CO-S011",
    "focused_state_name": "payment_security_code_error",
    "action_path": ["Products", "Cart", "Address", "Payment", "Submit payment with Security code empty"],
    "transition_text": "Submit payment with Security code empty",
  },
  "checkout-co-sem-081": {
    "empty_test_id": "payment-expiry",
    "error_selector": "#payment-expiry-error",
    "benchmark_state_id": "CO-S011",
    "focused_state_name": "payment_expiry_error",
    "action_path": ["Products", "Cart", "Address", "Payment", "Submit payment with Expiry empty"],
    "transition_text": "Submit payment with Expiry empty",
  },
  "checkout-co-sem-136": {
    "empty_test_id": "payment-security-code",
    "error_selector": "#payment-securityCode-error",
    "benchmark_state_id": "CO-S011",
    "focused_state_name": "payment_security_code_required_error",
    "action_path": ["Products", "Cart", "Address", "Payment", "Submit payment with Security code empty"],
    "transition_text": "Submit payment with Security code empty",
    "changed_value": "12",
    "changed_error_text": "Security code is required.",
    "changed_benchmark_state_id": SECURITY_CODE_FORMAT_INVALID_BENCHMARK_STATE_ID,
    "changed_focused_state_name": SECURITY_CODE_FORMAT_INVALID_FOCUSED_STATE,
    "changed_action_path": [
      "Products",
      "Cart",
      "Address",
      "Payment",
      "Submit payment with Security code empty",
      "Enter malformed Security code",
    ],
    "changed_transition_text": "Enter malformed Security code",
    "changed_native_validity": {
      "valid": False,
      "value_missing": False,
      "type_mismatch": False,
      "pattern_mismatch": True,
      "too_long": False,
      "too_short": False,
      "range_underflow": False,
      "range_overflow": False,
      "step_mismatch": False,
      "bad_input": False,
      "custom_error": False,
    },
  },
}
VIEWPORT = {"width": 1280, "height": 720}

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


def _is_clean_profile(profile: str | None) -> bool:
  return profile in (None, "", CLEAN_PROFILE)


def _is_language_switch_profile(profile: str | None) -> bool:
  return profile in LANGUAGE_SWITCH_PROFILES


def _requires_language_switch_back_capture(profile: str | None) -> bool:
  return profile in LANGUAGE_SWITCH_BACK_TO_ENGLISH_PROFILES


def _requires_delivery_estimate_result_capture(profile: str | None) -> bool:
  return profile == DELIVERY_ESTIMATE_WRONG_RESULT_PROFILE


def _requires_address_continue_wrong_result_capture(profile: str | None) -> bool:
  return profile == ADDRESS_CONTINUE_WRONG_RESULT_PROFILE


def _requires_cart_quantity_result_capture(profile: str | None) -> bool:
  return profile == CART_QUANTITY_WRONG_OBJECT_PROFILE


def _requires_delivery_estimate_expanded_capture(profile: str | None) -> bool:
  return profile == DELIVERY_ESTIMATE_EXPANDED_PROFILE


def _requires_gift_receipt_enabled_capture(profile: str | None) -> bool:
  return profile == GIFT_RECEIPT_ENABLED_PROFILE


def _requires_save_cart_active_capture(profile: str | None) -> bool:
  return profile == SAVE_CART_ACTIVE_PROFILE


def _requires_shipping_information_dialog_capture(profile: str | None) -> bool:
  return profile == SHIPPING_INFORMATION_DIALOG_PROFILE


def _requires_empty_cart_capture(profile: str | None) -> bool:
  return profile == EMPTY_CART_CAPTURE_PROFILE


def _requires_office_category_capture(profile: str | None) -> bool:
  return profile == OFFICE_CATEGORY_CAPTURE_PROFILE


def _requires_two_item_review(profile: str | None) -> bool:
  return profile in TWO_ITEM_REVIEW_PROFILES


def _invalid_address_submit_scenario(profile: str | None) -> dict[str, object] | None:
  return INVALID_ADDRESS_SUBMIT_SCENARIOS.get(profile or "")


def _invalid_payment_submit_scenario(profile: str | None) -> dict[str, object] | None:
  return INVALID_PAYMENT_SUBMIT_SCENARIOS.get(profile or "")


async def _assert_visible(page: Page, selector: str, message: str) -> None:
  if not await page.locator(selector).is_visible():
    raise AssertionError(message)


async def _assert_text(page: Page, selector: str, expected: str, message: str) -> None:
  actual = ((await page.locator(selector).text_content()) or "").strip()
  if actual != expected:
    raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


async def _assert_text_contains(
  page: Page,
  selector: str,
  expected: str,
  message: str,
) -> None:
  actual = ((await page.locator(selector).text_content()) or "").strip()
  if expected not in actual:
    raise AssertionError(f"{message}: expected text to include {expected!r}, got {actual!r}")


async def _assert_attribute(
  page: Page,
  selector: str,
  name: str,
  expected: str | None,
  message: str,
) -> None:
  actual = await page.locator(selector).get_attribute(name)
  if actual != expected:
    raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


async def _assert_label(page: Page, *, test_id: str, expected: str) -> None:
  actual = await page.evaluate(
    """({ testId }) => {
      const input = document.querySelector(`[data-testid="${testId}"]`);
      if (!input || !input.id) {
        return "";
      }
      const label = document.querySelector(`label[for="${input.id}"]`);
      return label ? label.textContent.trim() : "";
    }""",
    {"testId": test_id},
  )
  if expected not in actual:
    raise AssertionError(f"Label for {test_id} should include {expected!r}, got {actual!r}")


async def _assert_role_visible(page: Page, role: str, name: str, message: str) -> None:
  if not await page.get_by_role(role, name=name).is_visible():
    raise AssertionError(message)


async def _active_test_id(page: Page) -> str | None:
  return await page.evaluate(
    """() => {
      const active = document.activeElement;
      return active ? active.getAttribute("data-testid") : null;
    }"""
  )


async def _capture_state(
  page: Page,
  recorder: FocusedRunRecorder,
  *,
  benchmark_state_id: str,
  focused_state_name: str,
  action_path: list[str],
  key_validated_selectors: list[str],
  parent_focused_state_name: str | None = None,
  transition_text: str | None = None,
  transition_trigger: dict[str, object] | None = None,
) -> None:
  await recorder.capture_page_state(
    page,
    FocusedStateSpec(
      benchmark_state_id=benchmark_state_id,
      focused_state_name=focused_state_name,
      action_path=action_path,
      key_validated_selectors=key_validated_selectors,
      active_test_id=await _active_test_id(page),
      parent_focused_state_name=parent_focused_state_name,
      transition_text=transition_text,
      transition_trigger=transition_trigger or {},
    ),
  )


async def _capture_click_trigger(page: Page, selector: str) -> dict[str, object]:
  return await capture_focused_transition_trigger(
    page.locator(selector),
    action_type="click",
    selector=selector,
  )


async def _assert_products_workflow_ready(page: Page) -> None:
  await _assert_visible(page, '[data-testid="route-products"]', "Products route should be loaded")
  await _assert_visible(page, '[data-testid="product-list"]', "Product list should be visible")
  await _assert_visible(
    page,
    '[data-testid="product-add-prod-desk-lamp"]',
    "Desk lamp add button should be available for acquisition",
  )


async def _assert_products_clean_baseline(page: Page) -> None:
  await _assert_text(page, "h1", "Products", "Products route should have a clear h1")
  await _assert_attribute(
    page,
    '[data-testid="product-image-prod-desk-lamp"]',
    "alt",
    "Desk lamp with adjustable brass shade",
    "Desk lamp image alt should describe the baseline product image",
  )
  await _assert_role_visible(
    page,
    "button",
    "Add Desk lamp",
    "Desk lamp add button should expose the visible action name",
  )


async def _assert_office_category_selected(page: Page) -> None:
  await _assert_attribute(
    page,
    OFFICE_CATEGORY_TAB_SELECTOR,
    "tabindex",
    "0",
    "Office supplies should be the roving-tabindex target",
  )
  await _assert_attribute(
    page,
    DESK_CATEGORY_TAB_SELECTOR,
    "tabindex",
    "-1",
    "Desk accessories should leave the roving tabindex",
  )
  office_classes = (await page.locator(OFFICE_CATEGORY_TAB_SELECTOR).get_attribute("class")) or ""
  desk_classes = (await page.locator(DESK_CATEGORY_TAB_SELECTOR).get_attribute("class")) or ""
  if "is-selected" not in office_classes.split():
    raise AssertionError("Office supplies should have selected styling")
  if "is-selected" in desk_classes.split():
    raise AssertionError("Desk accessories should not have selected styling")
  await _assert_visible(
    page,
    OFFICE_CATEGORY_PANEL_SELECTOR,
    "Office supplies panel should be visible",
  )
  if await page.locator(DESK_CATEGORY_PANEL_SELECTOR).is_visible():
    raise AssertionError("Desk accessories panel should be hidden")


async def _assert_products_language_state(
  page: Page,
  *,
  expected_root_lang: str,
  expected_heading: str,
  expected_markers: list[str],
  selected_language_test_id: str,
  expected_selected_language_pressed: str = "true",
) -> None:
  actual_lang = await page.evaluate("document.documentElement.lang")
  if actual_lang != expected_root_lang:
    raise AssertionError(
      f"Products root language should be {expected_root_lang!r}, got {actual_lang!r}"
    )
  await _assert_text(
    page,
    "h1",
    expected_heading,
    "Products language state should expose the expected h1",
  )
  route_text = ((await page.locator('[data-testid="route-products"]').text_content()) or "")
  for marker in expected_markers:
    if marker not in route_text:
      raise AssertionError(
        f"Products language state should include {marker!r}; got {route_text!r}"
      )
  await _assert_attribute(
    page,
    f'[data-testid="{selected_language_test_id}"]',
    "aria-pressed",
    expected_selected_language_pressed,
    "Selected Products language control should expose pressed state",
  )


async def _assert_cart_workflow_ready(page: Page) -> None:
  await _assert_visible(page, '[data-testid="route-cart"]', "Cart route should be loaded")
  await _assert_visible(page, '[data-testid="cart-list"]', "Cart list should be visible")
  await _assert_visible(
    page,
    '[data-testid="continue-to-address"]',
    "Continue-to-address control should be available for acquisition",
  )


async def _assert_cart_clean_baseline(page: Page) -> None:
  await _assert_text(page, "h1", "Cart", "Cart route should have a clear h1")
  await _assert_attribute(
    page,
    '[data-testid="cart-totals-region"]',
    "aria-label",
    "Order totals",
    "Cart totals region should have a baseline landmark name",
  )
  await _assert_text(
    page,
    '[data-testid="cart-quantity-prod-desk-lamp"]',
    "1",
    "Initial desk lamp quantity should be deterministic",
  )
  await _assert_text(
    page,
    '[data-testid="cart-summary-total"]',
    "$37.00",
    "Cart total should include deterministic shipping",
  )


async def _assert_address_workflow_ready(page: Page) -> None:
  await _assert_visible(page, '[data-testid="route-address"]', "Address route should be loaded")
  await _assert_visible(page, '[data-testid="address-form"]', "Address form should be visible")
  for test_id in (
    "address-full-name",
    "address-email",
    "address-street",
    "address-city",
    "address-state",
    "address-postal-code",
    "continue-to-payment",
  ):
    await _assert_visible(
      page,
      f'[data-testid="{test_id}"]',
      f"{test_id} should be available for acquisition",
    )


async def _assert_address_clean_baseline(page: Page) -> None:
  await _assert_text(
    page,
    "h1",
    "Shipping address",
    "Address route should have a clear h1",
  )
  await _assert_label(page, test_id="address-full-name", expected="Full name")
  await _assert_label(page, test_id="address-email", expected="Email")
  await _assert_label(page, test_id="address-street", expected="Street address")
  await _assert_label(page, test_id="address-postal-code", expected="ZIP code")
  await _assert_attribute(
    page,
    '[data-testid="address-street"]',
    "autocomplete",
    "street-address",
    "Street field autocomplete should match its purpose",
  )
  await _assert_attribute(
    page,
    '[data-testid="address-postal-code"]',
    "autocomplete",
    "postal-code",
    "Postal-code field autocomplete should match its purpose",
  )


async def _assert_payment_workflow_ready(page: Page) -> None:
  await _assert_visible(page, '[data-testid="route-payment"]', "Payment route should be loaded")
  await _assert_visible(page, '[data-testid="payment-form"]', "Payment form should be visible")
  for test_id in (
    "payment-cardholder",
    "payment-card-number",
    "payment-expiry",
    "payment-security-code",
    "continue-to-review",
  ):
    await _assert_visible(
      page,
      f'[data-testid="{test_id}"]',
      f"{test_id} should be available for acquisition",
    )


async def _assert_payment_clean_baseline(page: Page) -> None:
  await _assert_text(page, "h1", "Payment", "Payment route should have a clear h1")
  await _assert_role_visible(
    page,
    "group",
    "Card details",
    "Payment fields should be grouped under a card details legend",
  )
  await _assert_label(page, test_id="payment-cardholder", expected="Cardholder name")
  await _assert_label(page, test_id="payment-card-number", expected="Card number")
  await _assert_label(page, test_id="payment-expiry", expected="Expiry")
  await _assert_label(page, test_id="payment-security-code", expected="Security code")
  await _assert_attribute(
    page,
    '[data-testid="payment-cardholder"]',
    "autocomplete",
    "cc-name",
    "Cardholder autocomplete should match its purpose",
  )
  await _assert_attribute(
    page,
    '[data-testid="payment-card-number"]',
    "autocomplete",
    "cc-number",
    "Card number autocomplete should match its purpose",
  )
  await _assert_attribute(
    page,
    '[data-testid="payment-expiry"]',
    "autocomplete",
    "cc-exp",
    "Expiry autocomplete should match its purpose",
  )
  await _assert_attribute(
    page,
    '[data-testid="payment-security-code"]',
    "autocomplete",
    "cc-csc",
    "Security code autocomplete should match its purpose",
  )
  await _assert_role_visible(
    page,
    "button",
    "Continue to review",
    "Payment submit button should expose its visible action name",
  )


async def _assert_review_workflow_ready(page: Page) -> None:
  await _assert_visible(page, '[data-testid="route-review"]', "Review route should be loaded")
  await _assert_visible(
    page,
    '[data-testid="review-shipping-summary"]',
    "Review should contain submitted shipping summary",
  )
  await _assert_visible(
    page,
    '[data-testid="review-payment-summary"]',
    "Review should contain submitted payment summary",
  )
  await _assert_visible(
    page,
    '[data-testid="review-order-summary"]',
    "Review should contain submitted order summary",
  )
  await _assert_visible(
    page,
    '[data-testid="review-place-order"]',
    "Place-order control should be available for acquisition",
  )


async def _assert_review_clean_baseline(page: Page) -> None:
  await _assert_text(page, "h1", "Review", "Review route should have a clear h1")
  await _assert_text_contains(
    page,
    '[data-testid="review-payment-card"]',
    "4242",
    "Review payment summary should expose a masked card ending",
  )
  await _assert_attribute(
    page,
    '[data-testid="review-product-image-prod-desk-lamp"]',
    "alt",
    "Desk lamp with adjustable brass shade",
    "Review product image alt should stay descriptive",
  )
  await _assert_role_visible(
    page,
    "button",
    "Place order",
    "Review route should expose the final order action by name",
  )


async def _assert_two_item_review_ready(page: Page) -> None:
  await _assert_text(
    page,
    '#review-item-header-prod-desk-lamp',
    "Desk lamp",
    "Two-item Review should retain the Desk lamp row",
  )
  await _assert_text(
    page,
    '#review-item-header-prod-notebook-set',
    "Notebook set",
    "Two-item Review should include the Notebook set row",
  )
  await _assert_text(
    page,
    '[data-testid="review-order-line-total-prod-desk-lamp"]',
    "$32.00",
    "Desk lamp line total should remain unchanged",
  )
  await _assert_text(
    page,
    '[data-testid="review-order-line-total-prod-notebook-set"]',
    "$18.00",
    "Notebook set line total should reflect one added item",
  )


async def _fill_values(page: Page, values: dict[str, str]) -> None:
  for test_id, value in values.items():
    await page.locator(f'[data-testid="{test_id}"]').fill(value)


async def _fill_values_except(
  page: Page,
  values: dict[str, str],
  *,
  skipped_test_id: str,
) -> None:
  for test_id, value in values.items():
    if test_id == skipped_test_id:
      continue
    await page.locator(f'[data-testid="{test_id}"]').fill(value)


async def _capture_invalid_address_submit(
  page: Page,
  recorder: FocusedRunRecorder,
  *,
  scenario: dict[str, object],
) -> None:
  empty_test_id = str(scenario["empty_test_id"])
  error_selector = str(scenario["error_selector"])
  transition_text = str(scenario["transition_text"])

  submit_trigger = await _capture_click_trigger(
    page,
    '[data-testid="continue-to-payment"]',
  )
  await page.locator('[data-testid="continue-to-payment"]').click()
  await _assert_visible(
    page,
    '[data-testid="route-address"]',
    "Invalid address submit should remain on the Address route",
  )
  await page.locator(error_selector).wait_for(state="visible")
  await _assert_attribute(
    page,
    f'[data-testid="{empty_test_id}"]',
    "aria-invalid",
    "true",
    "Invalid address target should expose aria-invalid",
  )
  await _assert_attribute(
    page,
    f'[data-testid="{empty_test_id}"]',
    "aria-describedby",
    error_selector.removeprefix("#"),
    "Invalid address target should keep its own error relationship",
  )
  await page.wait_for_function(
    """testId => document.activeElement?.getAttribute("data-testid") === testId""",
    arg=empty_test_id,
  )

  for test_id in VALID_ADDRESS_VALUES:
    if test_id == empty_test_id:
      continue
    await _assert_attribute(
      page,
      f'[data-testid="{test_id}"]',
      "aria-invalid",
      None,
      f"{test_id} should not be invalid in the focused invalid-address state",
    )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=str(scenario["benchmark_state_id"]),
    focused_state_name=str(scenario["focused_state_name"]),
    action_path=list(scenario["action_path"]),
    key_validated_selectors=[
      '[data-testid="address-form"]',
      f'[data-testid="{empty_test_id}"]',
      error_selector,
      '[data-testid="continue-to-payment"]',
    ],
    parent_focused_state_name="address",
    transition_text=transition_text,
    transition_trigger=submit_trigger,
  )

  changed_value = scenario.get("changed_value")
  if changed_value is None:
    return

  target_selector = f'[data-testid="{empty_test_id}"]'
  target = page.locator(target_selector)
  changed_value_trigger = await capture_focused_transition_trigger(
    target,
    action_type="fill",
    selector=target_selector,
  )
  await target.fill(str(changed_value))
  await page.locator(error_selector).wait_for(state="visible")
  await _assert_visible(
    page,
    '[data-testid="route-address"]',
    "Changed invalid address value should remain on the Address route",
  )
  await _assert_text(
    page,
    error_selector,
    str(scenario["changed_error_text"]),
    "Changed invalid address value should expose the configured error text",
  )
  await _assert_attribute(
    page,
    target_selector,
    "aria-invalid",
    "true",
    "Changed invalid address target should expose aria-invalid",
  )
  await _assert_attribute(
    page,
    target_selector,
    "aria-describedby",
    error_selector.removeprefix("#"),
    "Changed invalid address target should keep its own error relationship",
  )
  native_validity = await target.evaluate(
    """node => ({
      valid: node.validity.valid,
      value_missing: node.validity.valueMissing,
      type_mismatch: node.validity.typeMismatch,
      pattern_mismatch: node.validity.patternMismatch,
      too_long: node.validity.tooLong,
      too_short: node.validity.tooShort,
      range_underflow: node.validity.rangeUnderflow,
      range_overflow: node.validity.rangeOverflow,
      step_mismatch: node.validity.stepMismatch,
      bad_input: node.validity.badInput,
      custom_error: node.validity.customError,
    })"""
  )
  if native_validity != scenario["changed_native_validity"]:
    raise AssertionError(
      "Changed invalid address target should expose the expected native validity: "
      f"expected {scenario['changed_native_validity']!r}, got {native_validity!r}"
    )

  for test_id in VALID_ADDRESS_VALUES:
    if test_id == empty_test_id:
      continue
    await _assert_attribute(
      page,
      f'[data-testid="{test_id}"]',
      "aria-invalid",
      None,
      f"{test_id} should remain valid after changing the focused invalid value",
    )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=str(scenario["changed_benchmark_state_id"]),
    focused_state_name=str(scenario["changed_focused_state_name"]),
    action_path=list(scenario["changed_action_path"]),
    key_validated_selectors=[
      '[data-testid="address-form"]',
      target_selector,
      error_selector,
      '[data-testid="continue-to-payment"]',
    ],
    parent_focused_state_name=str(scenario["focused_state_name"]),
    transition_text=str(scenario["changed_transition_text"]),
    transition_trigger=changed_value_trigger,
  )


async def _capture_invalid_payment_submit(
  page: Page,
  recorder: FocusedRunRecorder,
  *,
  scenario: dict[str, object],
) -> None:
  empty_test_id = str(scenario["empty_test_id"])
  error_selector = str(scenario["error_selector"])
  transition_text = str(scenario["transition_text"])

  submit_trigger = await _capture_click_trigger(
    page,
    '[data-testid="continue-to-review"]',
  )
  await page.locator('[data-testid="continue-to-review"]').click()
  await _assert_visible(
    page,
    '[data-testid="route-payment"]',
    "Invalid payment submit should remain on the Payment route",
  )
  await page.locator(error_selector).wait_for(state="visible")
  await _assert_attribute(
    page,
    f'[data-testid="{empty_test_id}"]',
    "aria-invalid",
    "true",
    "Invalid payment target should expose aria-invalid",
  )
  await _assert_attribute(
    page,
    f'[data-testid="{empty_test_id}"]',
    "aria-describedby",
    error_selector.removeprefix("#"),
    "Invalid payment target should keep its own error relationship",
  )
  await page.wait_for_function(
    """testId => document.activeElement?.getAttribute("data-testid") === testId""",
    arg=empty_test_id,
  )

  for test_id in VALID_PAYMENT_VALUES:
    if test_id == empty_test_id:
      continue
    await _assert_attribute(
      page,
      f'[data-testid="{test_id}"]',
      "aria-invalid",
      None,
      f"{test_id} should not be invalid in the focused invalid-payment state",
    )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=str(scenario["benchmark_state_id"]),
    focused_state_name=str(scenario["focused_state_name"]),
    action_path=list(scenario["action_path"]),
    key_validated_selectors=[
      '[data-testid="payment-form"]',
      f'[data-testid="{empty_test_id}"]',
      error_selector,
      '[data-testid="continue-to-review"]',
    ],
    parent_focused_state_name="payment",
    transition_text=transition_text,
    transition_trigger=submit_trigger,
  )

  changed_value = scenario.get("changed_value")
  if changed_value is None:
    return

  target_selector = f'[data-testid="{empty_test_id}"]'
  target = page.locator(target_selector)
  changed_value_trigger = await capture_focused_transition_trigger(
    target,
    action_type="fill",
    selector=target_selector,
  )
  await target.fill(str(changed_value))
  await page.locator(error_selector).wait_for(state="visible")
  await _assert_visible(
    page,
    '[data-testid="route-payment"]',
    "Changed invalid payment value should remain on the Payment route",
  )
  await _assert_text(
    page,
    error_selector,
    str(scenario["changed_error_text"]),
    "Changed invalid payment value should expose the configured error text",
  )
  await _assert_attribute(
    page,
    target_selector,
    "aria-invalid",
    "true",
    "Changed invalid payment target should expose aria-invalid",
  )
  await _assert_attribute(
    page,
    target_selector,
    "aria-describedby",
    error_selector.removeprefix("#"),
    "Changed invalid payment target should keep its own error relationship",
  )
  native_validity = await target.evaluate(
    """node => ({
      valid: node.validity.valid,
      value_missing: node.validity.valueMissing,
      type_mismatch: node.validity.typeMismatch,
      pattern_mismatch: node.validity.patternMismatch,
      too_long: node.validity.tooLong,
      too_short: node.validity.tooShort,
      range_underflow: node.validity.rangeUnderflow,
      range_overflow: node.validity.rangeOverflow,
      step_mismatch: node.validity.stepMismatch,
      bad_input: node.validity.badInput,
      custom_error: node.validity.customError,
    })"""
  )
  if native_validity != scenario["changed_native_validity"]:
    raise AssertionError(
      "Changed invalid payment target should expose the expected native validity: "
      f"expected {scenario['changed_native_validity']!r}, got {native_validity!r}"
    )

  for test_id in VALID_PAYMENT_VALUES:
    if test_id == empty_test_id:
      continue
    await _assert_attribute(
      page,
      f'[data-testid="{test_id}"]',
      "aria-invalid",
      None,
      f"{test_id} should remain valid after changing the focused invalid value",
    )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=str(scenario["changed_benchmark_state_id"]),
    focused_state_name=str(scenario["changed_focused_state_name"]),
    action_path=list(scenario["changed_action_path"]),
    key_validated_selectors=[
      '[data-testid="payment-form"]',
      target_selector,
      error_selector,
      '[data-testid="continue-to-review"]',
    ],
    parent_focused_state_name=str(scenario["focused_state_name"]),
    transition_text=str(scenario["changed_transition_text"]),
    transition_trigger=changed_value_trigger,
  )


async def _capture_controlled_support_destination(
  page: Page,
  recorder: FocusedRunRecorder,
  *,
  base_url: str,
  profile: str | None,
) -> None:
  capture_spec = CONTROLLED_SUPPORT_CAPTURE_BY_PROFILE.get(
    profile,
    CONTROLLED_SUPPORT_CAPTURE_BY_PROFILE["checkout-co-sem-027"],
  )
  link_selector = capture_spec["link_selector"]
  source_url = capture_spec["source_url"]
  await page.goto(f"{base_url}/products", wait_until="networkidle")
  await _assert_products_workflow_ready(page)
  await _assert_attribute(
    page,
    link_selector,
    "href",
    source_url,
    "Controlled support link should point at the fixed support origin",
  )

  support_trigger = await _capture_click_trigger(
    page,
    link_selector,
  )
  await page.locator(link_selector).click()
  await page.wait_for_url(CONTROLLED_SUPPORT_RETURNS_URL)
  await page.wait_for_load_state("networkidle")

  actual_title = await page.title()
  if actual_title != "Returns and refunds":
    raise AssertionError(
      "Controlled support destination title should be "
      f"'Returns and refunds', got {actual_title!r}"
    )
  await _assert_text(
    page,
    "h1",
    "Returns and refunds",
    "Controlled support destination should expose the expected h1",
  )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=CONTROLLED_SUPPORT_DESTINATION_BENCHMARK_STATE_ID,
    focused_state_name=CONTROLLED_SUPPORT_DESTINATION_FOCUSED_STATE,
    action_path=["Products", "Controlled support destination"],
    key_validated_selectors=["main", "h1"],
    parent_focused_state_name="products",
    transition_text="Open controlled support destination",
    transition_trigger=support_trigger,
  )


async def _capture_delivery_estimate_wrong_result(
  page: Page,
  recorder: FocusedRunRecorder,
) -> None:
  await _assert_visible(
    page,
    DELIVERY_ESTIMATE_TRIGGER_SELECTOR,
    "Delivery estimate trigger should be available for focused acquisition",
  )
  await _assert_attribute(
    page,
    DELIVERY_ESTIMATE_TRIGGER_SELECTOR,
    "aria-expanded",
    "false",
    "Delivery estimate should start collapsed before wrong-result activation",
  )
  await _assert_attribute(
    page,
    DELIVERY_ESTIMATE_TRIGGER_SELECTOR,
    "aria-controls",
    "delivery-estimate-panel",
    "Delivery estimate trigger should keep its stable control relationship",
  )
  delivery_estimate_trigger = await _capture_click_trigger(
    page,
    DELIVERY_ESTIMATE_TRIGGER_SELECTOR,
  )
  await page.locator(DELIVERY_ESTIMATE_TRIGGER_SELECTOR).click()
  await _assert_visible(
    page,
    '[data-testid="shipping-information-dialog"]',
    "Delivery estimate activation should open the Shipping information dialog for co-sem-089",
  )
  await _assert_attribute(
    page,
    '[data-testid="shipping-information-dialog"]',
    "role",
    "dialog",
    "Shipping information dialog role should remain valid",
  )
  await _assert_attribute(
    page,
    '[data-testid="shipping-information-dialog"]',
    "aria-modal",
    "true",
    "Shipping information dialog modal semantics should remain valid",
  )
  await _assert_text(
    page,
    "#shipping-information-title",
    "Shipping information",
    "Wrong-result destination should be the real Shipping information dialog",
  )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=DELIVERY_ESTIMATE_WRONG_RESULT_BENCHMARK_STATE_ID,
    focused_state_name=DELIVERY_ESTIMATE_WRONG_RESULT_FOCUSED_STATE,
    action_path=["Products", "Cart", "Delivery estimate"],
    key_validated_selectors=[
      '[data-testid="cart-list"]',
      DELIVERY_ESTIMATE_TRIGGER_SELECTOR,
      '[data-testid="shipping-information-dialog"]',
      "#shipping-information-title",
    ],
    parent_focused_state_name="cart",
    transition_text="Activate Delivery estimate",
    transition_trigger=delivery_estimate_trigger,
  )

  await page.locator('[data-testid="shipping-information-close"]').click()
  await page.locator('[data-testid="shipping-information-dialog"]').wait_for(state="detached")


async def _capture_cart_quantity_result(
  page: Page,
  recorder: FocusedRunRecorder,
  *,
  trigger_selector: str,
  action_path: list[str],
) -> None:
  await _assert_text(
    page,
    DESK_LAMP_CART_QUANTITY_SELECTOR,
    "1",
    "Desk lamp should start at quantity one before quantity-result capture",
  )
  await _assert_text(
    page,
    NOTEBOOK_SET_CART_QUANTITY_SELECTOR,
    "1",
    "Notebook set should start at quantity one before quantity-result capture",
  )
  await _assert_visible(
    page,
    trigger_selector,
    "Configured Cart quantity trigger should be visible",
  )
  quantity_trigger = await _capture_click_trigger(page, trigger_selector)
  trigger_name = str(quantity_trigger.get("accessible_name") or "quantity control")

  await page.locator(trigger_selector).click()
  await _assert_cart_workflow_ready(page)
  await _assert_text(page, "h1", "Cart", "Quantity result should remain on Cart")
  actual_title = await page.title()
  if actual_title != "Cart | Brightlane Checkout":
    raise AssertionError(
      "Cart quantity result title should remain "
      f"'Cart | Brightlane Checkout', got {actual_title!r}"
    )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=CART_QUANTITY_RESULT_BENCHMARK_STATE_ID,
    focused_state_name=CART_QUANTITY_RESULT_FOCUSED_STATE,
    action_path=[*action_path, trigger_name],
    key_validated_selectors=[
      trigger_selector,
      DESK_LAMP_CART_QUANTITY_SELECTOR,
      NOTEBOOK_SET_CART_QUANTITY_SELECTOR,
    ],
    parent_focused_state_name="cart",
    transition_text=f"Activate {trigger_name}",
    transition_trigger=quantity_trigger,
  )


async def _capture_delivery_estimate_expanded(
  page: Page,
  recorder: FocusedRunRecorder,
) -> None:
  await _assert_visible(
    page,
    DELIVERY_ESTIMATE_TRIGGER_SELECTOR,
    "Delivery estimate trigger should be available for focused acquisition",
  )
  if await page.locator(DELIVERY_ESTIMATE_PANEL_SELECTOR).is_visible():
    raise AssertionError("Delivery estimate panel should start collapsed")

  delivery_estimate_trigger = await _capture_click_trigger(
    page,
    DELIVERY_ESTIMATE_TRIGGER_SELECTOR,
  )
  await page.locator(DELIVERY_ESTIMATE_TRIGGER_SELECTOR).click()
  await _assert_visible(
    page,
    DELIVERY_ESTIMATE_PANEL_SELECTOR,
    "Delivery estimate panel should be visible after activation",
  )
  await _assert_text(
    page,
    DELIVERY_ESTIMATE_PANEL_SELECTOR,
    "Standard delivery usually arrives in 3-5 business days after dispatch.",
    "Expanded Delivery estimate panel should keep its normal content",
  )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=DELIVERY_ESTIMATE_EXPANDED_BENCHMARK_STATE_ID,
    focused_state_name=DELIVERY_ESTIMATE_EXPANDED_FOCUSED_STATE,
    action_path=["Products", "Cart", "Delivery estimate"],
    key_validated_selectors=[
      '[data-testid="cart-list"]',
      DELIVERY_ESTIMATE_TRIGGER_SELECTOR,
      DELIVERY_ESTIMATE_PANEL_SELECTOR,
    ],
    parent_focused_state_name="cart",
    transition_text="Activate Delivery estimate",
    transition_trigger=delivery_estimate_trigger,
  )


async def _capture_gift_receipt_enabled(
  page: Page,
  recorder: FocusedRunRecorder,
) -> None:
  await _assert_visible(
    page,
    GIFT_RECEIPT_SWITCH_SELECTOR,
    "Gift receipt switch should be available for focused acquisition",
  )
  initial_classes = (
    await page.locator(GIFT_RECEIPT_SWITCH_SELECTOR).get_attribute("class")
  ) or ""
  if "is-on" in initial_classes.split():
    raise AssertionError("Gift receipt should start functionally off")
  if await page.locator(GIFT_RECEIPT_NOTE_SELECTOR).count() != 0:
    raise AssertionError("Gift receipt enabled helper should start absent")

  gift_receipt_trigger = await _capture_click_trigger(
    page,
    GIFT_RECEIPT_SWITCH_SELECTOR,
  )
  await page.locator(GIFT_RECEIPT_SWITCH_SELECTOR).click()

  enabled_classes = (
    await page.locator(GIFT_RECEIPT_SWITCH_SELECTOR).get_attribute("class")
  ) or ""
  if "is-on" not in enabled_classes.split():
    raise AssertionError("Gift receipt should have enabled styling after activation")
  await _assert_visible(
    page,
    GIFT_RECEIPT_NOTE_SELECTOR,
    "Gift receipt enabled helper should be visible after activation",
  )
  await _assert_text(
    page,
    GIFT_RECEIPT_NOTE_SELECTOR,
    "A gift receipt will be included.",
    "Gift receipt enabled helper should keep its normal content",
  )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=GIFT_RECEIPT_ENABLED_BENCHMARK_STATE_ID,
    focused_state_name=GIFT_RECEIPT_ENABLED_FOCUSED_STATE,
    action_path=["Products", "Cart", "Gift receipt"],
    key_validated_selectors=[
      '[data-testid="cart-list"]',
      GIFT_RECEIPT_SWITCH_SELECTOR,
      GIFT_RECEIPT_NOTE_SELECTOR,
    ],
    parent_focused_state_name="cart",
    transition_text="Activate Gift receipt",
    transition_trigger=gift_receipt_trigger,
  )


async def _capture_save_cart_active(
  page: Page,
  recorder: FocusedRunRecorder,
) -> None:
  await _assert_visible(
    page,
    SAVE_CART_TOGGLE_SELECTOR,
    "Save cart toggle should be available for focused acquisition",
  )
  initial_classes = (
    await page.locator(SAVE_CART_TOGGLE_SELECTOR).get_attribute("class")
  ) or ""
  if "is-saved" in initial_classes.split():
    raise AssertionError("Save cart should start functionally unsaved")
  if await page.locator(SAVE_CART_NOTE_SELECTOR).count() != 0:
    raise AssertionError("Saved-cart helper should start absent")

  save_cart_trigger = await _capture_click_trigger(
    page,
    SAVE_CART_TOGGLE_SELECTOR,
  )
  await page.locator(SAVE_CART_TOGGLE_SELECTOR).click()

  saved_classes = (
    await page.locator(SAVE_CART_TOGGLE_SELECTOR).get_attribute("class")
  ) or ""
  if "is-saved" not in saved_classes.split():
    raise AssertionError("Save cart should have active styling after activation")
  await _assert_visible(
    page,
    SAVE_CART_NOTE_SELECTOR,
    "Saved-cart helper should be visible after activation",
  )
  await _assert_text(
    page,
    SAVE_CART_NOTE_SELECTOR,
    "Cart saved for later.",
    "Saved-cart helper should keep its normal content",
  )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=SAVE_CART_ACTIVE_BENCHMARK_STATE_ID,
    focused_state_name=SAVE_CART_ACTIVE_FOCUSED_STATE,
    action_path=["Products", "Cart", "Save cart"],
    key_validated_selectors=[
      '[data-testid="cart-list"]',
      SAVE_CART_TOGGLE_SELECTOR,
      SAVE_CART_NOTE_SELECTOR,
    ],
    parent_focused_state_name="cart",
    transition_text="Activate Save cart",
    transition_trigger=save_cart_trigger,
  )


async def _capture_shipping_information_dialog(
  page: Page,
  recorder: FocusedRunRecorder,
) -> None:
  if await page.evaluate("document.documentElement.lang") != "es":
    raise AssertionError("Shipping information dialog capture requires Spanish root lang es")
  await _assert_text(
    page,
    SHIPPING_INFORMATION_TRIGGER_SELECTOR,
    "Información de envío",
    "Shipping information trigger should remain localized in Spanish",
  )

  shipping_information_trigger = await _capture_click_trigger(
    page,
    SHIPPING_INFORMATION_TRIGGER_SELECTOR,
  )
  await page.locator(SHIPPING_INFORMATION_TRIGGER_SELECTOR).click()

  await _assert_visible(
    page,
    SHIPPING_INFORMATION_DIALOG_SELECTOR,
    "Shipping information dialog should be visible after activation",
  )
  await _assert_attribute(
    page,
    SHIPPING_INFORMATION_DIALOG_SELECTOR,
    "role",
    "dialog",
    "Shipping information dialog should retain its dialog role",
  )
  await _assert_attribute(
    page,
    SHIPPING_INFORMATION_DIALOG_SELECTOR,
    "aria-modal",
    "true",
    "Shipping information dialog should retain modal semantics",
  )
  await _assert_attribute(
    page,
    SHIPPING_INFORMATION_DIALOG_SELECTOR,
    "aria-labelledby",
    "shipping-information-title",
    "Shipping information dialog should retain its title relationship",
  )
  await _assert_role_visible(
    page,
    "dialog",
    "Información de envío",
    "Shipping information dialog should retain its Spanish accessible name",
  )
  await _assert_text(
    page,
    "#shipping-information-title",
    "Información de envío",
    "Shipping information dialog should retain its Spanish title",
  )
  await _assert_text(
    page,
    SHIPPING_INFORMATION_BODY_SELECTOR,
    (
      "El envío estándar se calcula durante la compra. Los detalles de entrega "
      "se confirman después de ingresar la dirección de envío."
    ),
    "Shipping information dialog should retain its Spanish body copy",
  )
  await _assert_attribute(
    page,
    SHIPPING_INFORMATION_BODY_SELECTOR,
    "lang",
    "en",
    "Shipping information body should expose the seeded local English declaration",
  )
  if await page.evaluate("document.documentElement.lang") != "es":
    raise AssertionError("Shipping information body override must not change root lang es")

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=SHIPPING_INFORMATION_DIALOG_BENCHMARK_STATE_ID,
    focused_state_name=SHIPPING_INFORMATION_DIALOG_FOCUSED_STATE,
    action_path=["Products", "Spanish language", "Cart", "Shipping information"],
    key_validated_selectors=[
      SHIPPING_INFORMATION_TRIGGER_SELECTOR,
      SHIPPING_INFORMATION_DIALOG_SELECTOR,
      "#shipping-information-title",
      SHIPPING_INFORMATION_BODY_SELECTOR,
    ],
    parent_focused_state_name="cart",
    transition_text="Open Shipping information",
    transition_trigger=shipping_information_trigger,
  )

  await page.locator('[data-testid="shipping-information-close"]').click()
  await page.locator(SHIPPING_INFORMATION_DIALOG_SELECTOR).wait_for(state="detached")


async def _capture_empty_cart(
  page: Page,
  recorder: FocusedRunRecorder,
) -> None:
  empty_cart_trigger = await _capture_click_trigger(
    page,
    EMPTY_CART_DECREMENT_SELECTOR,
  )
  await page.locator(EMPTY_CART_DECREMENT_SELECTOR).click()
  await page.locator(EMPTY_CART_HEADING_SELECTOR).wait_for(state="visible")

  if await page.locator('[data-testid^="cart-item-"]').count() != 0:
    raise AssertionError("Empty Cart capture should contain zero cart items")
  await _assert_visible(
    page,
    '[data-testid="empty-cart-continue"]',
    "Empty Cart should offer a return to Products",
  )
  await _assert_text_contains(
    page,
    '[data-testid="route-cart"]',
    "Add a product before continuing checkout.",
    "Empty Cart should retain its explanatory content",
  )

  await _capture_state(
    page,
    recorder,
    benchmark_state_id=EMPTY_CART_BENCHMARK_STATE_ID,
    focused_state_name=EMPTY_CART_FOCUSED_STATE,
    action_path=["Products", "Cart", "Decrease Desk lamp quantity"],
    key_validated_selectors=[
      '[data-testid="route-cart"]',
      EMPTY_CART_HEADING_SELECTOR,
      '[data-testid="empty-cart-continue"]',
    ],
    parent_focused_state_name="cart",
    transition_text="Decrease Desk lamp quantity to zero",
    transition_trigger=empty_cart_trigger,
  )

  await page.locator('[data-testid="empty-cart-continue"]').click()
  await page.wait_for_url("**/products")
  await page.locator('[data-testid="product-add-prod-desk-lamp"]').click()
  await _assert_text(
    page,
    '[data-testid="cart-summary-count"]',
    "1 item",
    "Desk lamp should be restored before the remaining checkout workflow",
  )
  await page.locator('[data-testid="nav-cart"]').click()
  await page.wait_for_url("**/cart")
  await _assert_cart_workflow_ready(page)


async def _run_capture(
  *,
  base_url: str,
  run_dir: Path,
  profile: str | None,
  capture_controlled_support_destination: bool = False,
  cart_quantity_result_trigger_selector: str | None = None,
) -> dict[str, object]:
  async with async_playwright() as playwright:
    browser = await playwright.chromium.launch()
    context = await browser.new_context(viewport=VIEWPORT)
    should_assert_clean_baseline = _is_clean_profile(profile)
    quantity_result_trigger_selector = cart_quantity_result_trigger_selector
    if (
      quantity_result_trigger_selector is None
      and _requires_cart_quantity_result_capture(profile)
    ):
      quantity_result_trigger_selector = DESK_LAMP_INCREMENT_SELECTOR
    if profile:
      await context.add_init_script(
        f"window[{json.dumps(CHECKOUT_PROFILE_GLOBAL)}] = {json.dumps(profile)};"
      )
    if capture_controlled_support_destination:
      await context.add_init_script(
        f"window[{json.dumps(CHECKOUT_SUPPORT_ORIGIN_GLOBAL)}] = "
        f"{json.dumps(CONTROLLED_SUPPORT_ORIGIN)};"
      )
    page = await context.new_page()

    recorder = FocusedRunRecorder(
      run_dir=run_dir,
      app_name="checkout-flow",
      benchmark_name="controlled-local-spas-checkout-flow",
      source_script=str(Path(__file__).relative_to(REPO_ROOT)),
    )

    await page.goto(f"{base_url}/products", wait_until="networkidle")
    await _assert_products_workflow_ready(page)
    if should_assert_clean_baseline:
      await _assert_products_clean_baseline(page)
    await _capture_state(
      page,
      recorder,
      benchmark_state_id="CO-S001",
      focused_state_name="products",
      action_path=["Products"],
      key_validated_selectors=[
        '[data-testid="product-list"]',
        '[data-testid="product-image-prod-desk-lamp"]',
        '[data-testid="product-add-prod-desk-lamp"]',
      ],
    )

    cart_parent_state = "products"
    cart_action_path = ["Products", "Cart"]
    checkout_action_path = ["Products", "Cart"]
    if _requires_office_category_capture(profile):
      activate_office_trigger = await _capture_click_trigger(
        page,
        OFFICE_CATEGORY_TAB_SELECTOR,
      )
      await page.locator(OFFICE_CATEGORY_TAB_SELECTOR).click()
      await _assert_office_category_selected(page)
      await _capture_state(
        page,
        recorder,
        benchmark_state_id=OFFICE_CATEGORY_BENCHMARK_STATE_ID,
        focused_state_name=OFFICE_CATEGORY_FOCUSED_STATE,
        action_path=["Products", "Office supplies"],
        key_validated_selectors=[
          DESK_CATEGORY_TAB_SELECTOR,
          OFFICE_CATEGORY_TAB_SELECTOR,
          OFFICE_CATEGORY_PANEL_SELECTOR,
        ],
        parent_focused_state_name="products",
        transition_text="Activate Office supplies",
        transition_trigger=activate_office_trigger,
      )
      cart_parent_state = OFFICE_CATEGORY_FOCUSED_STATE
      cart_action_path = ["Products", "Office supplies", "Cart"]

    if _is_language_switch_profile(profile):
      expected_spanish_root_lang = LANGUAGE_SWITCH_SPANISH_ROOT_LANG_BY_PROFILE[
        profile
      ]
      await _assert_products_language_state(
        page,
        expected_root_lang="en",
        expected_heading="Products",
        expected_markers=[
          "Browse featured products and update the cart summary.",
          "Desk accessories",
          "Add Desk lamp",
        ],
        selected_language_test_id="products-language-en",
      )
      choose_spanish_trigger = await _capture_click_trigger(
        page,
        '[data-testid="products-language-es"]',
      )
      await page.locator('[data-testid="products-language-es"]').click()
      await _assert_products_language_state(
        page,
        expected_root_lang=expected_spanish_root_lang,
        expected_heading="Productos",
        expected_markers=[
          "Explora productos destacados y actualiza el resumen del carrito.",
          "Accesorios de escritorio",
          "Agregar Lámpara de escritorio",
        ],
        selected_language_test_id="products-language-es",
        expected_selected_language_pressed=(
          LANGUAGE_SWITCH_SPANISH_ARIA_PRESSED_BY_PROFILE.get(profile, "true")
        ),
      )
      await _capture_state(
        page,
        recorder,
        benchmark_state_id="CO-S007",
        focused_state_name="products_spanish",
        action_path=["Products", "Spanish language"],
        key_validated_selectors=[
          '[data-testid="products-language-switcher"]',
          '[data-testid="products-language-es"]',
          '[data-testid="product-list"]',
        ],
        parent_focused_state_name="products",
        transition_text="Choose Spanish products language",
        transition_trigger=choose_spanish_trigger,
      )
      cart_parent_state = "products_spanish"
      cart_action_path = ["Products", "Spanish language", "Cart"]

      if _requires_language_switch_back_capture(profile):
        choose_english_trigger = await _capture_click_trigger(
          page,
          '[data-testid="products-language-en"]',
        )
        await page.locator('[data-testid="products-language-en"]').click()
        await _assert_products_language_state(
          page,
          expected_root_lang="es",
          expected_heading="Products",
          expected_markers=[
            "Browse featured products and update the cart summary.",
            "Desk accessories",
            "Add Desk lamp",
          ],
          selected_language_test_id="products-language-en",
        )
        await _capture_state(
          page,
          recorder,
          benchmark_state_id=LANGUAGE_SWITCH_BACK_BENCHMARK_STATE_ID,
          focused_state_name=LANGUAGE_SWITCH_BACK_FOCUSED_STATE,
          action_path=["Products", "Spanish language", "English language"],
          key_validated_selectors=[
            '[data-testid="products-language-switcher"]',
            '[data-testid="products-language-en"]',
            '[data-testid="product-list"]',
          ],
          parent_focused_state_name="products_spanish",
          transition_text="Choose English products language",
          transition_trigger=choose_english_trigger,
        )
        cart_parent_state = LANGUAGE_SWITCH_BACK_FOCUSED_STATE
        cart_action_path = [
          "Products",
          "Spanish language",
          "English language",
          "Cart",
        ]

    if _requires_two_item_review(profile) or quantity_result_trigger_selector:
      await page.locator(NOTEBOOK_SET_ADD_SELECTOR).click()
      await _assert_text(
        page,
        NOTEBOOK_SET_QUANTITY_SELECTOR,
        "In cart: 1 item",
        "Notebook set should be added once before checkout",
      )
      await _assert_text(
        page,
        '[data-testid="cart-summary-count"]',
        "2 items",
        "Multi-item Cart acquisition should have two cart items",
      )
      cart_action_path = ["Products", "Add Notebook set", "Cart"]
      checkout_action_path = ["Products", "Add Notebook set", "Cart"]

    open_cart_trigger = await _capture_click_trigger(page, '[data-testid="nav-cart"]')
    await page.locator('[data-testid="nav-cart"]').click()
    await page.wait_for_url("**/cart")
    await _assert_cart_workflow_ready(page)
    if should_assert_clean_baseline and not quantity_result_trigger_selector:
      await _assert_cart_clean_baseline(page)
    await _capture_state(
      page,
      recorder,
      benchmark_state_id="CO-S002",
      focused_state_name="cart",
      action_path=cart_action_path,
      key_validated_selectors=[
        '[data-testid="cart-list"]',
        '[data-testid="cart-totals-region"]',
        '[data-testid="continue-to-address"]',
      ],
      parent_focused_state_name=cart_parent_state,
      transition_text="Open cart",
      transition_trigger=open_cart_trigger,
    )

    if quantity_result_trigger_selector:
      await _capture_cart_quantity_result(
        page,
        recorder,
        trigger_selector=quantity_result_trigger_selector,
        action_path=cart_action_path,
      )
      await browser.close()
      return recorder.write_run_artifacts()

    if _requires_delivery_estimate_result_capture(profile):
      await _capture_delivery_estimate_wrong_result(page, recorder)

    if _requires_delivery_estimate_expanded_capture(profile):
      await _capture_delivery_estimate_expanded(page, recorder)

    if _requires_gift_receipt_enabled_capture(profile):
      await _capture_gift_receipt_enabled(page, recorder)

    if _requires_save_cart_active_capture(profile):
      await _capture_save_cart_active(page, recorder)

    if _requires_shipping_information_dialog_capture(profile):
      await _capture_shipping_information_dialog(page, recorder)

    if _requires_empty_cart_capture(profile):
      await _capture_empty_cart(page, recorder)

    continue_to_address_trigger = await _capture_click_trigger(
      page,
      '[data-testid="continue-to-address"]',
    )
    await page.locator('[data-testid="continue-to-address"]').click()
    await page.wait_for_url("**/checkout/address")
    await _assert_address_workflow_ready(page)
    if should_assert_clean_baseline:
      await _assert_address_clean_baseline(page)
    await _capture_state(
      page,
      recorder,
      benchmark_state_id="CO-S003",
      focused_state_name="address",
      action_path=[*checkout_action_path, "Address"],
      key_validated_selectors=[
        '[data-testid="address-form"]',
        '[data-testid="address-street"]',
        '[data-testid="continue-to-payment"]',
      ],
      parent_focused_state_name="cart",
      transition_text="Continue to address",
      transition_trigger=continue_to_address_trigger,
    )

    invalid_address_scenario = _invalid_address_submit_scenario(profile)
    if invalid_address_scenario:
      skipped_test_id = str(invalid_address_scenario["empty_test_id"])
      await _fill_values_except(
        page,
        VALID_ADDRESS_VALUES,
        skipped_test_id=skipped_test_id,
      )
      await _capture_invalid_address_submit(
        page,
        recorder,
        scenario=invalid_address_scenario,
      )
      await page.locator(f'[data-testid="{skipped_test_id}"]').fill(
        VALID_ADDRESS_VALUES[skipped_test_id],
      )
    else:
      await _fill_values(page, VALID_ADDRESS_VALUES)

    continue_to_payment_trigger = await _capture_click_trigger(
      page,
      ADDRESS_CONTINUE_TO_PAYMENT_SELECTOR,
    )
    await page.locator(ADDRESS_CONTINUE_TO_PAYMENT_SELECTOR).click()
    if _requires_address_continue_wrong_result_capture(profile):
      await page.wait_for_url("**/cart")
      await _assert_cart_workflow_ready(page)
      await _assert_text(
        page,
        "h1",
        "Cart",
        "Continue to payment should reach the seeded Cart result",
      )
      actual_title = await page.title()
      if actual_title != "Cart | Brightlane Checkout":
        raise AssertionError(
          "Seeded wrong-result destination title should be "
          f"'Cart | Brightlane Checkout', got {actual_title!r}"
        )
      await _capture_state(
        page,
        recorder,
        benchmark_state_id=ADDRESS_CONTINUE_WRONG_RESULT_BENCHMARK_STATE_ID,
        focused_state_name=ADDRESS_CONTINUE_WRONG_RESULT_FOCUSED_STATE,
        action_path=[*checkout_action_path, "Address", "Cart"],
        key_validated_selectors=[
          '[data-testid="cart-list"]',
          '[data-testid="cart-totals-region"]',
          '[data-testid="continue-to-address"]',
        ],
        parent_focused_state_name="address",
        transition_text="Submit shipping address",
        transition_trigger=continue_to_payment_trigger,
      )
      await browser.close()
      return recorder.write_run_artifacts()

    await page.wait_for_url("**/checkout/payment")
    await _assert_payment_workflow_ready(page)
    if should_assert_clean_baseline:
      await _assert_payment_clean_baseline(page)
    await _capture_state(
      page,
      recorder,
      benchmark_state_id="CO-S004",
      focused_state_name="payment",
      action_path=[*checkout_action_path, "Address", "Payment"],
      key_validated_selectors=[
        '[data-testid="payment-form"]',
        '[data-testid="payment-card-number"]',
        '[data-testid="continue-to-review"]',
      ],
      parent_focused_state_name="address",
      transition_text="Submit shipping address",
      transition_trigger=continue_to_payment_trigger,
    )

    invalid_payment_scenario = _invalid_payment_submit_scenario(profile)
    if invalid_payment_scenario:
      skipped_test_id = str(invalid_payment_scenario["empty_test_id"])
      await _fill_values_except(
        page,
        VALID_PAYMENT_VALUES,
        skipped_test_id=skipped_test_id,
      )
      await _capture_invalid_payment_submit(
        page,
        recorder,
        scenario=invalid_payment_scenario,
      )
      await page.locator(f'[data-testid="{skipped_test_id}"]').fill(
        VALID_PAYMENT_VALUES[skipped_test_id],
      )
    else:
      await _fill_values(page, VALID_PAYMENT_VALUES)

    continue_to_review_trigger = await _capture_click_trigger(
      page,
      '[data-testid="continue-to-review"]',
    )
    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")
    await _assert_review_workflow_ready(page)
    if _requires_two_item_review(profile):
      await _assert_two_item_review_ready(page)
    if should_assert_clean_baseline:
      await _assert_review_clean_baseline(page)
    await _capture_state(
      page,
      recorder,
      benchmark_state_id="CO-S005",
      focused_state_name="review",
      action_path=[*checkout_action_path, "Address", "Payment", "Review"],
      key_validated_selectors=[
        '[data-testid="review-shipping-summary"]',
        '[data-testid="review-payment-summary"]',
        '[data-testid="review-order-summary"]',
      ],
      parent_focused_state_name="payment",
      transition_text="Submit payment details",
      transition_trigger=continue_to_review_trigger,
    )

    if capture_controlled_support_destination:
      await _capture_controlled_support_destination(
        page,
        recorder,
        base_url=base_url,
        profile=profile,
      )

    await browser.close()
    return recorder.write_run_artifacts()


def _profile_slug(profile: str | None) -> str:
  if not profile:
    return "no_profile"
  return "".join(character if character.isalnum() else "_" for character in profile).strip("_")


def _default_run_dir(profile: str | None) -> Path:
  timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  return DEFAULT_RUNS_ROOT / _profile_slug(profile) / f"run_{timestamp}"


def _parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Capture the clean Checkout benchmark baseline workflow."
  )
  parser.add_argument(
    "--profile",
    default=None,
    help=(
      "Checkout benchmark profile to inject. Omit for no profile. "
      f"The explicit clean profile is {CLEAN_PROFILE!r}."
    ),
  )
  parser.add_argument(
    "--run-dir",
    type=Path,
    default=None,
    help="Directory for the normalized focused run artifacts.",
  )
  parser.add_argument(
    "--skip-build",
    action="store_true",
    help="Use the existing dist output instead of running npm run build first.",
  )
  parser.add_argument(
    "--capture-controlled-support-destination",
    action="store_true",
    help=(
      "Opt into one controlled second-origin support destination capture. "
      "This starts a fixed local support server on 127.0.0.1:8771 and records "
      "a Products -> support destination edge."
    ),
  )
  return parser.parse_args()


def main() -> int:
  args = _parse_args()
  run_dir = args.run_dir or _default_run_dir(args.profile)

  if not args.skip_build:
    _build_app()

  capture_controlled_support_destination = (
    args.capture_controlled_support_destination
    or _requires_controlled_support_destination_capture(args.profile)
  )
  support_server: subprocess.Popen[str] | None = None
  if capture_controlled_support_destination:
    support_server = _start_controlled_support_server()
    _wait_for_url(CONTROLLED_SUPPORT_RETURNS_URL, timeout_seconds=20)

  preview: subprocess.Popen[str] | None = None
  try:
    port = _find_free_port()
    preview = _start_vite_preview(port=port)
    base_url = f"http://127.0.0.1:{port}"
    _wait_for_url(f"{base_url}/products", timeout_seconds=20)
    manifest = asyncio.run(
      _run_capture(
        base_url=base_url,
        run_dir=run_dir,
        profile=args.profile,
        capture_controlled_support_destination=capture_controlled_support_destination,
      )
    )
  finally:
    if preview is not None:
      _stop_process(preview)
    if support_server is not None:
      _stop_process(support_server)

  print(json.dumps(manifest, ensure_ascii=False, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
