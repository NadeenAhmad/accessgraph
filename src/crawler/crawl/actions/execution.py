from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from playwright.async_api import Locator
else:
  Locator = Any

try:
  from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
  PlaywrightTimeoutError = TimeoutError

from .discovery import ActionCandidate
from ...exceptions import CrawlerError
from ...platform.readiness import wait_after_action

DEFAULT_ACTION_TIMEOUT_MS = 10_000
POST_ACTION_READY_TIMEOUT_MS = 2_000


class ActionTimeout(CrawlerError):
  pass


async def _is_interactable(loc: Locator) -> bool:
  if not await loc.is_visible():
    return False
  if not await loc.is_enabled():
    return False
  return True


async def _settle_after_action(loc: Locator, wait_timeout_ms: int) -> None:
  await wait_after_action(loc.page, mutation_timeout_ms=wait_timeout_ms)


async def _run_interaction(
  *,
  loc: Locator,
  timeout_ms: int,
  wait_timeout_ms: int,
  timeout_message: str,
  perform: Callable[[], Awaitable[bool | None]],
) -> bool:
  try:
    if not await _is_interactable(loc):
      return False
    outcome = await perform()
    if outcome is False:
      return False
    await _settle_after_action(loc, wait_timeout_ms)
    return True
  except PlaywrightTimeoutError as error:
    raise ActionTimeout(timeout_message) from error
  except Exception:
    return False


async def click_locator(
  loc: Locator,
  timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS,
  wait_timeout_ms: int = POST_ACTION_READY_TIMEOUT_MS,
) -> bool:
  """Click a locator and wait for the page to settle."""
  async def do_click() -> None:
    await loc.click(timeout=timeout_ms)

  return await _run_interaction(
    loc=loc,
    timeout_ms=timeout_ms,
    wait_timeout_ms=wait_timeout_ms,
    timeout_message="Timeout while clicking a candidate",
    perform=do_click,
  )


async def type_locator(
  loc: Locator,
  value: str = "crawler_input",
  timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS,
  wait_timeout_ms: int = POST_ACTION_READY_TIMEOUT_MS,
) -> bool:
  async def do_type() -> None:
    await loc.fill(value, timeout=timeout_ms)

  return await _run_interaction(
    loc=loc,
    timeout_ms=timeout_ms,
    wait_timeout_ms=wait_timeout_ms,
    timeout_message="Timeout while typing into a candidate",
    perform=do_type,
  )


async def select_locator(
  loc: Locator,
  timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS,
  wait_timeout_ms: int = POST_ACTION_READY_TIMEOUT_MS,
) -> bool:
  try:
    if not await _is_interactable(loc):
      return False

    options = await loc.evaluate(
      """
      (el) => {
        const current = el.value || '';
        const values = Array.from(el.options || []).map((o) => o.value || '');
        return { current, values };
      }
      """
    )
    if not isinstance(options, dict):
      return False

    current = str(options.get("current") or "")
    values_raw = options.get("values") or []
    values = [str(v) for v in values_raw if isinstance(v, str)]
    if not values:
      return False

    target = next((value for value in values if value != current), values[0])
    await loc.select_option(value=target, timeout=timeout_ms)
    await _settle_after_action(loc, wait_timeout_ms)
    return True
  except PlaywrightTimeoutError as error:
    raise ActionTimeout("Timeout while selecting an option") from error
  except Exception:
    return False


async def check_locator(
  loc: Locator,
  timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS,
  wait_timeout_ms: int = POST_ACTION_READY_TIMEOUT_MS,
) -> bool:
  async def do_check() -> bool:
    if await loc.is_checked():
      return False
    await loc.check(timeout=timeout_ms)
    return True

  return await _run_interaction(
    loc=loc,
    timeout_ms=timeout_ms,
    wait_timeout_ms=wait_timeout_ms,
    timeout_message="Timeout while checking a candidate",
    perform=do_check,
  )


async def radio_locator(
  loc: Locator,
  timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS,
  wait_timeout_ms: int = POST_ACTION_READY_TIMEOUT_MS,
) -> bool:
  async def do_radio() -> bool:
    target = await loc.evaluate(
      """
      (el) => {
        const tag = (el.tagName || '').toLowerCase();
        const type = (el.getAttribute('type') || '').toLowerCase();
        return { is_radio_input: tag === 'input' && type === 'radio', checked: !!el.checked };
      }
      """
    )
    if isinstance(target, dict) and target.get("is_radio_input"):
      if target.get("checked"):
        return False
      await loc.check(timeout=timeout_ms)
      return True

    await loc.click(timeout=timeout_ms)
    return True

  return await _run_interaction(
    loc=loc,
    timeout_ms=timeout_ms,
    wait_timeout_ms=wait_timeout_ms,
    timeout_message="Timeout while selecting a radio candidate",
    perform=do_radio,
  )


async def perform_action(
  candidate: ActionCandidate,
  timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS,
  wait_timeout_ms: int = POST_ACTION_READY_TIMEOUT_MS,
) -> bool:
  loc = candidate.locator
  if candidate.action_type == "fill_submit":
    from .forms import perform_fill_submit

    page = loc.page

    async def do_fill_submit() -> bool:
      return await perform_fill_submit(page, candidate, timeout_ms=timeout_ms)

    try:
      if not await do_fill_submit():
        return False
      await wait_after_action(page, mutation_timeout_ms=wait_timeout_ms)
      return True
    except PlaywrightTimeoutError as error:
      raise ActionTimeout("Timeout while filling and submitting a form") from error
    except Exception:
      return False
  if candidate.action_type == "type":
    return await type_locator(loc, timeout_ms=timeout_ms, wait_timeout_ms=wait_timeout_ms)
  if candidate.action_type == "select":
    return await select_locator(loc, timeout_ms=timeout_ms, wait_timeout_ms=wait_timeout_ms)
  if candidate.action_type == "check":
    return await check_locator(loc, timeout_ms=timeout_ms, wait_timeout_ms=wait_timeout_ms)
  if candidate.action_type == "radio":
    return await radio_locator(loc, timeout_ms=timeout_ms, wait_timeout_ms=wait_timeout_ms)
  if candidate.action_type == "hover":  # W4A phase 1
    async def do_hover() -> None:
      await loc.hover(timeout=timeout_ms)

    return await _run_interaction(loc=loc, timeout_ms=timeout_ms, wait_timeout_ms=wait_timeout_ms,
                                  timeout_message="Timeout while hovering a candidate", perform=do_hover)
  if candidate.action_type == "key":  # W4A phase 1: focus the widget, press its key
    async def do_key() -> None:
      await loc.focus(timeout=timeout_ms)
      await loc.press(candidate.key or "ArrowDown", timeout=timeout_ms)

    return await _run_interaction(loc=loc, timeout_ms=timeout_ms, wait_timeout_ms=wait_timeout_ms,
                                  timeout_message="Timeout while pressing a key on a candidate", perform=do_key)
  return await click_locator(loc, timeout_ms=timeout_ms, wait_timeout_ms=wait_timeout_ms)
