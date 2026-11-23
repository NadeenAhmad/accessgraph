from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_DIR = REPO_ROOT / "benchmarks" / "local-spas" / "checkout-flow"
VIEWPORT = {"width": 1280, "height": 720}
CHECKOUT_PROFILE_GLOBAL = "__ACCESSGRAPH_CHECKOUT_PROFILE__"
BASELINE_ERROR_MESSAGE_PROFILE_CASES = (
  (None, "Email"),
  ("checkout-clean-v1", "Email"),
  ("checkout-unknown-profile", "Email"),
  ("checkout-co-sem-006", "Email"),
  ("checkout-co-sem-063", "Email"),
  ("checkout-co-sem-087", "Full name"),
  ("checkout-co-sem-077", "Email"),
  ("checkout-co-sem-078", "Email"),
  ("checkout-co-sem-079", "Email"),
  ("checkout-co-sem-080", "Email"),
  ("checkout-co-sem-081", "Email"),
  ("checkout-co-sem-134", "Email"),
  ("checkout-co-sem-135", "Email"),
  ("checkout-co-sem-136", "Email"),
)
ADDRESS_ERROR_MESSAGE_CASES = (
  {
    "profile": None,
    "empty_test_id": "address-full-name",
    "expected_error_text": "Full name is required.",
    "expected_visible_label": "Full name",
  },
  {
    "profile": "checkout-co-sem-078",
    "empty_test_id": "address-full-name",
    "expected_error_text": "Street address is required.",
    "expected_visible_label": "Full name",
  },
  {
    "profile": "checkout-co-sem-078",
    "empty_test_id": "address-street",
    "expected_error_text": "Street address is required.",
    "expected_visible_label": "Street address",
  },
  {
    "profile": None,
    "empty_test_id": "address-postal-code",
    "expected_error_text": "ZIP code is required.",
    "expected_visible_label": "ZIP code",
  },
  {
    "profile": "checkout-co-sem-076",
    "empty_test_id": "address-postal-code",
    "expected_error_text": "ZIP code is required.",
    "expected_visible_label": "ZIP code",
  },
  {
    "profile": "checkout-co-sem-077",
    "empty_test_id": "address-postal-code",
    "expected_error_text": "Email is required.",
    "expected_visible_label": "ZIP code",
  },
  {
    "profile": "checkout-co-sem-134",
    "empty_test_id": "address-postal-code",
    "expected_error_text": "ZIP code is required.",
    "expected_visible_label": "ZIP code",
  },
)
ADDRESS_FIELD_EXPECTATIONS = {
  "address-full-name": {
    "id": "address-fullName",
    "name": "fullName",
    "type": "text",
    "autocomplete": "name",
    "error_id": "address-fullName-error",
  },
  "address-email": {
    "id": "address-email",
    "name": "email",
    "type": "email",
    "autocomplete": "email",
    "error_id": "address-email-error",
  },
  "address-street": {
    "id": "address-streetAddress",
    "name": "streetAddress",
    "type": "text",
    "autocomplete": "street-address",
    "error_id": "address-streetAddress-error",
  },
  "address-postal-code": {
    "id": "address-postalCode",
    "name": "postalCode",
    "type": "text",
    "autocomplete": "postal-code",
    "error_id": "address-postalCode-error",
  },
}
PAYMENT_ERROR_MESSAGE_CASES = (
  {
    "profile": None,
    "empty_test_id": "payment-card-number",
    "expected_error_text": "Card number is required.",
    "expected_visible_label": "Card number",
  },
  {
    "profile": "checkout-co-sem-079",
    "empty_test_id": "payment-card-number",
    "expected_error_text": "Security code is required.",
    "expected_visible_label": "Card number",
  },
  {
    "profile": "checkout-co-sem-079",
    "empty_test_id": "payment-security-code",
    "expected_error_text": "Security code is required.",
    "expected_visible_label": "Security code",
  },
  {
    "profile": None,
    "empty_test_id": "payment-security-code",
    "expected_error_text": "Security code is required.",
    "expected_visible_label": "Security code",
  },
  {
    "profile": "checkout-co-sem-080",
    "empty_test_id": "payment-security-code",
    "expected_error_text": "Card number is required.",
    "expected_visible_label": "Security code",
  },
  {
    "profile": "checkout-co-sem-080",
    "empty_test_id": "payment-card-number",
    "expected_error_text": "Card number is required.",
    "expected_visible_label": "Card number",
  },
  {
    "profile": "checkout-co-sem-136",
    "empty_test_id": "payment-security-code",
    "expected_error_text": "Security code is required.",
    "expected_visible_label": "Security code",
  },
  {
    "profile": None,
    "empty_test_id": "payment-expiry",
    "expected_error_text": "Expiry is required.",
    "expected_visible_label": "Expiry",
  },
  {
    "profile": "checkout-co-sem-081",
    "empty_test_id": "payment-expiry",
    "expected_error_text": "Cardholder name is required.",
    "expected_visible_label": "Expiry",
  },
  {
    "profile": "checkout-co-sem-081",
    "empty_test_id": "payment-card-number",
    "expected_error_text": "Card number is required.",
    "expected_visible_label": "Card number",
  },
  {
    "profile": "checkout-co-sem-081",
    "empty_test_id": "payment-security-code",
    "expected_error_text": "Security code is required.",
    "expected_visible_label": "Security code",
  },
)
PAYMENT_FIELD_EXPECTATIONS = {
  "payment-cardholder": {
    "id": "payment-cardholder",
    "name": "cardholder",
    "type": "text",
    "autocomplete": "cc-name",
    "inputmode": None,
    "error_id": "payment-cardholder-error",
  },
  "payment-card-number": {
    "id": "payment-cardNumber",
    "name": "cardNumber",
    "type": "text",
    "autocomplete": "cc-number",
    "inputmode": "numeric",
    "error_id": "payment-cardNumber-error",
  },
  "payment-expiry": {
    "id": "payment-expiry",
    "name": "expiry",
    "type": "text",
    "autocomplete": "cc-exp",
    "inputmode": "numeric",
    "error_id": "payment-expiry-error",
  },
  "payment-security-code": {
    "id": "payment-securityCode",
    "name": "securityCode",
    "type": "text",
    "autocomplete": "cc-csc",
    "inputmode": "numeric",
    "error_id": "payment-securityCode-error",
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
  from urllib.request import urlopen

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


async def _fill_address_except(page, skipped_test_id: str) -> None:
  await page.get_by_role("link", name="Cart").click()
  await page.wait_for_url("**/cart")
  await page.locator('[data-testid="continue-to-address"]').click()
  await page.wait_for_url("**/checkout/address")

  for test_id, value in VALID_ADDRESS_VALUES.items():
    if test_id == skipped_test_id:
      continue
    await page.locator(f'[data-testid="{test_id}"]').fill(value)


async def _fill_payment_except(page, skipped_test_id: str) -> None:
  await _fill_address_except(page, "")
  await page.locator('[data-testid="continue-to-payment"]').click()
  await page.wait_for_url("**/checkout/payment")

  for test_id, value in VALID_PAYMENT_VALUES.items():
    if test_id == skipped_test_id:
      continue
    await page.locator(f'[data-testid="{test_id}"]').fill(value)


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


def test_checkout_error_message_case_updates_only_email_error_text():
  async def assert_email_required_error(
    page,
    *,
    expected_error_text: str,
    expected_visible_label: str,
  ):
    await _fill_address_except(page, "address-email")

    email = page.locator('[data-testid="address-email"]')
    postal_code = page.locator('[data-testid="address-postal-code"]')

    assert await page.locator("h1", has_text="Shipping address").is_visible()
    assert await _label_text_for_testid(page, "address-email") == expected_visible_label
    assert await email.is_visible()
    assert await email.get_attribute("id") == "address-email"
    assert await email.get_attribute("name") == "email"
    assert await email.get_attribute("type") == "email"
    assert await email.get_attribute("autocomplete") == "email"
    assert await email.get_attribute("required") is not None
    assert await email.evaluate("node => node.validity.valueMissing")

    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_function(
      "() => document.activeElement?.getAttribute('data-testid') === 'address-email'",
    )

    error = page.locator("#address-email-error")
    assert page.url.endswith("/checkout/address")
    assert await page.locator('[data-testid="route-payment"]').count() == 0
    assert await email.get_attribute("aria-invalid") == "true"
    assert await email.get_attribute("aria-describedby") == "address-email-error"
    assert ((await error.text_content()) or "").strip() == expected_error_text
    assert await error.is_visible()
    assert await postal_code.get_attribute("aria-invalid") is None
    assert await page.locator("#address-postalCode-error").count() == 0

  for profile, expected_visible_label in BASELINE_ERROR_MESSAGE_PROFILE_CASES:
    asyncio.run(
      _with_checkout_page(
        lambda page, label=expected_visible_label: assert_email_required_error(
          page,
          expected_error_text="Email is required.",
          expected_visible_label=label,
        ),
        profile=profile,
      )
    )

  asyncio.run(
    _with_checkout_page(
      lambda page: assert_email_required_error(
        page,
        expected_error_text="ZIP code is required.",
        expected_visible_label="Email",
      ),
      profile="checkout-co-sem-076",
    )
  )


def test_checkout_error_message_case_updates_only_zip_error_text():
  async def assert_address_required_error(
    page,
    *,
    empty_test_id: str,
    expected_error_text: str,
    expected_visible_label: str,
  ):
    await _fill_address_except(page, empty_test_id)

    field = page.locator(f'[data-testid="{empty_test_id}"]')
    expected = ADDRESS_FIELD_EXPECTATIONS[empty_test_id]

    assert await page.locator("h1", has_text="Shipping address").is_visible()
    assert await _label_text_for_testid(page, empty_test_id) == expected_visible_label
    assert await field.is_visible()
    assert await field.get_attribute("id") == expected["id"]
    assert await field.get_attribute("name") == expected["name"]
    assert await field.get_attribute("type") == expected["type"]
    assert await field.get_attribute("autocomplete") == expected["autocomplete"]
    assert await field.get_attribute("required") is not None
    assert await field.evaluate("node => node.validity.valueMissing")

    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_function(
      """testId => document.activeElement?.getAttribute("data-testid") === testId""",
      arg=empty_test_id,
    )

    error = page.locator(f"#{expected['error_id']}")
    assert page.url.endswith("/checkout/address")
    assert await page.locator('[data-testid="route-payment"]').count() == 0
    assert await field.get_attribute("aria-invalid") == "true"
    assert await field.get_attribute("aria-describedby") == expected["error_id"]
    assert ((await error.text_content()) or "").strip() == expected_error_text
    assert await error.is_visible()

    for test_id in VALID_ADDRESS_VALUES:
      if test_id == empty_test_id:
        continue
      assert await page.locator(f'[data-testid="{test_id}"]').get_attribute("aria-invalid") is None

  for case in ADDRESS_ERROR_MESSAGE_CASES:
    asyncio.run(
      _with_checkout_page(
        lambda page, expected=case: assert_address_required_error(
          page,
          empty_test_id=expected["empty_test_id"],
          expected_error_text=expected["expected_error_text"],
          expected_visible_label=expected["expected_visible_label"],
        ),
        profile=case["profile"],
      )
    )


def test_checkout_error_message_cases_update_only_payment_target_error_text():
  async def assert_payment_required_error(
    page,
    *,
    empty_test_id: str,
    expected_error_text: str,
    expected_visible_label: str,
  ):
    await _fill_payment_except(page, empty_test_id)

    field = page.locator(f'[data-testid="{empty_test_id}"]')
    expected = PAYMENT_FIELD_EXPECTATIONS[empty_test_id]

    assert await page.locator("h1", has_text="Payment").is_visible()
    assert await page.get_by_role("group", name="Card details").is_visible()
    assert await _label_text_for_testid(page, empty_test_id) == expected_visible_label
    assert await field.is_visible()
    assert await field.get_attribute("id") == expected["id"]
    assert await field.get_attribute("name") == expected["name"]
    assert await field.get_attribute("type") == expected["type"]
    assert await field.get_attribute("autocomplete") == expected["autocomplete"]
    assert await field.get_attribute("inputmode") == expected["inputmode"]
    assert await field.get_attribute("required") is not None
    assert await field.evaluate("node => node.validity.valueMissing")

    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_function(
      """testId => document.activeElement?.getAttribute("data-testid") === testId""",
      arg=empty_test_id,
    )

    error = page.locator(f"#{expected['error_id']}")
    assert page.url.endswith("/checkout/payment")
    assert await page.locator('[data-testid="route-review"]').count() == 0
    assert await field.get_attribute("aria-invalid") == "true"
    assert await field.get_attribute("aria-describedby") == expected["error_id"]
    assert ((await error.text_content()) or "").strip() == expected_error_text
    assert await error.is_visible()

    for test_id in VALID_PAYMENT_VALUES:
      if test_id == empty_test_id:
        continue
      assert await page.locator(f'[data-testid="{test_id}"]').get_attribute("aria-invalid") is None

  for case in PAYMENT_ERROR_MESSAGE_CASES:
    asyncio.run(
      _with_checkout_page(
        lambda page, expected=case: assert_payment_required_error(
          page,
          empty_test_id=expected["empty_test_id"],
          expected_error_text=expected["expected_error_text"],
          expected_visible_label=expected["expected_visible_label"],
        ),
        profile=case["profile"],
      )
    )


def test_checkout_clean_format_validation_replaces_required_errors_and_accepts_valid_values():
  async def assert_clean_format_validation(page):
    await _fill_address_except(page, "address-postal-code")

    postal_code = page.locator('[data-testid="address-postal-code"]')
    postal_error = page.locator("#address-postalCode-error")
    assert await postal_code.get_attribute("pattern") == r"\d{5}"

    await page.locator('[data-testid="continue-to-payment"]').click()
    assert await postal_code.evaluate("node => node.validity.valueMissing")
    assert ((await postal_error.text_content()) or "").strip() == "ZIP code is required."
    assert await postal_code.get_attribute("aria-invalid") == "true"
    assert await postal_code.get_attribute("aria-describedby") == "address-postalCode-error"

    await postal_code.fill("1234")
    assert not await postal_code.evaluate("node => node.validity.valueMissing")
    assert await postal_code.evaluate("node => node.validity.patternMismatch")
    assert (
      (await postal_error.text_content()) or ""
    ).strip() == "Enter a valid 5-digit ZIP code."
    assert await postal_code.get_attribute("aria-invalid") == "true"
    assert await postal_code.get_attribute("aria-describedby") == "address-postalCode-error"

    await postal_code.fill(VALID_ADDRESS_VALUES["address-postal-code"])
    assert await postal_code.evaluate("node => node.validity.valid")
    assert await postal_code.get_attribute("aria-invalid") is None
    assert await postal_code.get_attribute("aria-describedby") is None
    assert await postal_error.count() == 0

    email = page.locator('[data-testid="address-email"]')
    email_error = page.locator("#address-email-error")
    await email.fill("")
    await page.locator('[data-testid="continue-to-payment"]').click()
    assert await email.evaluate("node => node.validity.valueMissing")
    assert ((await email_error.text_content()) or "").strip() == "Email is required."
    assert await email.get_attribute("aria-invalid") == "true"
    assert await email.get_attribute("aria-describedby") == "address-email-error"

    await email.fill("invalid-email")
    assert not await email.evaluate("node => node.validity.valueMissing")
    assert await email.evaluate("node => node.validity.typeMismatch")
    assert (
      (await email_error.text_content()) or ""
    ).strip() == "Enter a valid email address."
    assert await email.get_attribute("aria-invalid") == "true"
    assert await email.get_attribute("aria-describedby") == "address-email-error"

    await email.fill(VALID_ADDRESS_VALUES["address-email"])
    assert await email.evaluate("node => node.validity.valid")
    assert await email.get_attribute("aria-invalid") is None
    assert await email.get_attribute("aria-describedby") is None
    assert await email_error.count() == 0

    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_url("**/checkout/payment")

    for test_id, value in VALID_PAYMENT_VALUES.items():
      if test_id == "payment-security-code":
        continue
      await page.locator(f'[data-testid="{test_id}"]').fill(value)

    security_code = page.locator('[data-testid="payment-security-code"]')
    security_error = page.locator("#payment-securityCode-error")
    assert await security_code.get_attribute("pattern") == r"\d{3,4}"

    await page.locator('[data-testid="continue-to-review"]').click()
    assert await security_code.evaluate("node => node.validity.valueMissing")
    assert (
      (await security_error.text_content()) or ""
    ).strip() == "Security code is required."
    assert await security_code.get_attribute("aria-invalid") == "true"
    assert await security_code.get_attribute("aria-describedby") == "payment-securityCode-error"

    await security_code.fill("12")
    assert not await security_code.evaluate("node => node.validity.valueMissing")
    assert await security_code.evaluate("node => node.validity.patternMismatch")
    assert (
      (await security_error.text_content()) or ""
    ).strip() == "Enter a 3 or 4 digit security code."
    assert await security_code.get_attribute("aria-invalid") == "true"
    assert await security_code.get_attribute("aria-describedby") == "payment-securityCode-error"

    await security_code.fill("1234")
    assert await security_code.evaluate("node => node.validity.valid")
    assert await security_code.get_attribute("aria-invalid") is None
    assert await security_code.get_attribute("aria-describedby") is None
    assert await security_error.count() == 0

    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_url("**/checkout/review")
    assert await page.locator('[data-testid="checkout-review-content"]').is_visible()

  asyncio.run(_with_checkout_page(assert_clean_format_validation))


def test_checkout_co_sem_134_reports_required_for_malformed_zip_code():
  async def assert_wrong_zip_error(page):
    await _fill_address_except(page, "address-postal-code")

    postal_code = page.locator('[data-testid="address-postal-code"]')
    error = page.locator("#address-postalCode-error")
    assert page.url.endswith("/checkout/address")
    assert await page.locator("h1", has_text="Shipping address").is_visible()
    assert await _label_text_for_testid(page, "address-postal-code") == "ZIP code"
    assert await postal_code.get_attribute("id") == "address-postalCode"
    assert await postal_code.get_attribute("name") == "postalCode"
    assert await postal_code.get_attribute("type") == "text"
    assert await postal_code.get_attribute("autocomplete") == "postal-code"
    assert await postal_code.get_attribute("inputmode") == "numeric"
    assert await postal_code.get_attribute("required") is not None

    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_function(
      "() => document.activeElement?.getAttribute('data-testid') === 'address-postal-code'",
    )
    assert await postal_code.evaluate("node => node.validity.valueMissing")
    assert not await postal_code.evaluate("node => node.validity.typeMismatch")
    assert not await postal_code.evaluate("node => node.validity.patternMismatch")
    assert ((await error.text_content()) or "").strip() == "ZIP code is required."
    assert await postal_code.get_attribute("aria-invalid") == "true"
    assert await postal_code.get_attribute("aria-describedby") == "address-postalCode-error"

    await postal_code.fill("1234")
    await page.wait_for_function(
      """() => {
        const postalCode = document.querySelector('[data-testid="address-postal-code"]');
        return postalCode && !postalCode.validity.valueMissing
          && !postalCode.validity.typeMismatch
          && postalCode.validity.patternMismatch;
      }"""
    )
    assert page.url.endswith("/checkout/address")
    assert not await postal_code.evaluate("node => node.validity.valueMissing")
    assert not await postal_code.evaluate("node => node.validity.typeMismatch")
    assert await postal_code.evaluate("node => node.validity.patternMismatch")
    assert ((await error.text_content()) or "").strip() == "ZIP code is required."
    assert await postal_code.get_attribute("aria-invalid") == "true"
    assert await postal_code.get_attribute("aria-describedby") == "address-postalCode-error"

    for test_id in VALID_ADDRESS_VALUES:
      if test_id == "address-postal-code":
        continue
      assert await page.locator(
        f'[data-testid="{test_id}"]'
      ).get_attribute("aria-invalid") is None

    await postal_code.fill("97205")
    assert await postal_code.evaluate("node => node.validity.valid")
    assert await postal_code.get_attribute("aria-invalid") is None
    assert await postal_code.get_attribute("aria-describedby") is None
    assert await error.count() == 0

  asyncio.run(
    _with_checkout_page(
      assert_wrong_zip_error,
      profile="checkout-co-sem-134",
    )
  )


def test_checkout_co_sem_135_keeps_required_message_after_email_format_failure():
  async def assert_stale_email_error(page):
    await _fill_address_except(page, "address-email")

    email = page.locator('[data-testid="address-email"]')
    error = page.locator("#address-email-error")
    assert page.url.endswith("/checkout/address")
    assert await page.locator("h1", has_text="Shipping address").is_visible()
    assert await _label_text_for_testid(page, "address-email") == "Email"
    assert await email.get_attribute("id") == "address-email"
    assert await email.get_attribute("name") == "email"
    assert await email.get_attribute("type") == "email"
    assert await email.get_attribute("autocomplete") == "email"
    assert await email.get_attribute("required") is not None

    await page.locator('[data-testid="continue-to-payment"]').click()
    await page.wait_for_function(
      "() => document.activeElement?.getAttribute('data-testid') === 'address-email'",
    )
    assert await email.evaluate("node => node.validity.valueMissing")
    assert not await email.evaluate("node => node.validity.typeMismatch")
    assert not await email.evaluate("node => node.validity.patternMismatch")
    assert ((await error.text_content()) or "").strip() == "Email is required."
    assert await email.get_attribute("aria-invalid") == "true"
    assert await email.get_attribute("aria-describedby") == "address-email-error"

    await email.fill("invalid-email")
    await page.wait_for_function(
      """() => {
        const email = document.querySelector('[data-testid="address-email"]');
        return email && !email.validity.valueMissing
          && email.validity.typeMismatch
          && email.validity.patternMismatch;
      }"""
    )
    assert page.url.endswith("/checkout/address")
    assert not await email.evaluate("node => node.validity.valueMissing")
    assert await email.evaluate("node => node.validity.typeMismatch")
    assert await email.evaluate("node => node.validity.patternMismatch")
    assert ((await error.text_content()) or "").strip() == "Email is required."
    assert await email.get_attribute("aria-invalid") == "true"
    assert await email.get_attribute("aria-describedby") == "address-email-error"

    for test_id in VALID_ADDRESS_VALUES:
      if test_id == "address-email":
        continue
      assert await page.locator(
        f'[data-testid="{test_id}"]'
      ).get_attribute("aria-invalid") is None

    await email.fill(VALID_ADDRESS_VALUES["address-email"])
    assert await email.evaluate("node => node.validity.valid")
    assert await email.get_attribute("aria-invalid") is None
    assert await email.get_attribute("aria-describedby") is None
    assert await error.count() == 0

  asyncio.run(
    _with_checkout_page(
      assert_stale_email_error,
      profile="checkout-co-sem-135",
    )
  )


def test_checkout_co_sem_136_reports_required_for_malformed_security_code():
  async def assert_wrong_security_code_error(page):
    await _fill_payment_except(page, "payment-security-code")

    security_code = page.locator('[data-testid="payment-security-code"]')
    error = page.locator("#payment-securityCode-error")
    assert page.url.endswith("/checkout/payment")
    assert await page.locator("h1", has_text="Payment").is_visible()
    assert await page.get_by_role("group", name="Card details").is_visible()
    assert await _label_text_for_testid(page, "payment-security-code") == "Security code"
    assert await security_code.get_attribute("id") == "payment-securityCode"
    assert await security_code.get_attribute("name") == "securityCode"
    assert await security_code.get_attribute("type") == "text"
    assert await security_code.get_attribute("autocomplete") == "cc-csc"
    assert await security_code.get_attribute("inputmode") == "numeric"
    assert await security_code.get_attribute("pattern") == r"\d{3,4}"
    assert await security_code.get_attribute("required") is not None

    await page.locator('[data-testid="continue-to-review"]').click()
    await page.wait_for_function(
      "() => document.activeElement?.getAttribute('data-testid') === 'payment-security-code'",
    )
    assert await security_code.evaluate("node => node.validity.valueMissing")
    assert not await security_code.evaluate("node => node.validity.typeMismatch")
    assert not await security_code.evaluate("node => node.validity.patternMismatch")
    assert ((await error.text_content()) or "").strip() == "Security code is required."
    assert await security_code.get_attribute("aria-invalid") == "true"
    assert await security_code.get_attribute("aria-describedby") == "payment-securityCode-error"

    await security_code.fill("12")
    await page.wait_for_function(
      """() => {
        const securityCode = document.querySelector('[data-testid="payment-security-code"]');
        return securityCode && !securityCode.validity.valueMissing
          && !securityCode.validity.typeMismatch
          && securityCode.validity.patternMismatch;
      }"""
    )
    assert page.url.endswith("/checkout/payment")
    assert not await security_code.evaluate("node => node.validity.valueMissing")
    assert not await security_code.evaluate("node => node.validity.typeMismatch")
    assert await security_code.evaluate("node => node.validity.patternMismatch")
    assert ((await error.text_content()) or "").strip() == "Security code is required."
    assert await security_code.get_attribute("aria-invalid") == "true"
    assert await security_code.get_attribute("aria-describedby") == "payment-securityCode-error"

    for test_id in VALID_PAYMENT_VALUES:
      if test_id == "payment-security-code":
        continue
      assert await page.locator(
        f'[data-testid="{test_id}"]'
      ).get_attribute("aria-invalid") is None

    await security_code.fill("123")
    assert await security_code.evaluate("node => node.validity.valid")
    assert await security_code.get_attribute("aria-invalid") is None
    assert await security_code.get_attribute("aria-describedby") is None
    assert await error.count() == 0

  asyncio.run(
    _with_checkout_page(
      assert_wrong_security_code_error,
      profile="checkout-co-sem-136",
    )
  )
