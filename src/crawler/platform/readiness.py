from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any

DOM_READY_STATES = {"interactive", "complete"}


async def _wait_for_load_state_best_effort(page: Page, state: str, timeout_ms: int) -> None:
  try:
    await page.wait_for_load_state(state, timeout=timeout_ms)
  except Exception:
    return


async def _wait_for_dom_stability(
  page: Page,
  *,
  timeout_ms: int,
  poll_interval_ms: int,
  stable_repeats_required: int,
) -> None:
  deadline = time.monotonic() + (max(timeout_ms, 1) / 1000.0)
  prev_snapshot: dict[str, object] | None = None
  stable_repeats = 0

  while time.monotonic() < deadline:
    try:
      snapshot = await page.evaluate(
        """
        () => {
          const root = document.documentElement;
          const text = document.body ? document.body.innerText || '' : '';
          return {
            ready_state: document.readyState || '',
            url: window.location.href || '',
            element_count: root ? root.getElementsByTagName('*').length : 0,
            text_length: text.length
          };
        }
        """
      )
    except Exception:
      return

    if not isinstance(snapshot, dict):
      return

    ready = str(snapshot.get("ready_state") or "")
    if prev_snapshot is not None and snapshot == prev_snapshot and ready in DOM_READY_STATES:
      stable_repeats += 1
      if stable_repeats >= stable_repeats_required:
        return
    else:
      stable_repeats = 0

    prev_snapshot = snapshot
    try:
      await page.wait_for_timeout(poll_interval_ms)
    except Exception:
      return


async def _wait_for_dom_mutation_or_timeout(page: Page, *, timeout_ms: int = 2_000) -> None:
  """
  Wait for the first DOM mutation after an action, or continue after timeout.

  SPAs commonly update the DOM without a fresh navigation or network-idle
  signal, so the default crawl stage uses this as its post-action wait.
  """
  try:
    await page.evaluate(
      """
      (timeoutMs) => new Promise((resolve) => {
        const root = document.documentElement || document.body;
        if (!root || typeof MutationObserver === 'undefined') {
          window.setTimeout(() => resolve('timeout'), timeoutMs);
          return;
        }

        let settled = false;
        let observer = null;
        const finish = (reason) => {
          if (settled) return;
          settled = true;
          if (observer) observer.disconnect();
          resolve(reason);
        };

        observer = new MutationObserver(() => finish('mutation'));
        observer.observe(root, {
          attributes: true,
          childList: true,
          characterData: true,
          subtree: true
        });
        window.setTimeout(() => finish('timeout'), timeoutMs);
      })
      """,
      timeout_ms,
    )
  except Exception:
    return


async def wait_for_page_ready(
  page: Page,
  *,
  timeout_ms: int = 3_000,
  network_idle_timeout_ms: int = 1_200,
  poll_interval_ms: int = 100,
  stable_repeats_required: int = 2,
) -> None:
  """
  Best-effort page settle strategy:
  1) domcontentloaded
  2) networkidle (short timeout, optional)
  3) lightweight DOM stability polling
  """
  await _wait_for_load_state_best_effort(page, "domcontentloaded", timeout_ms)
  await _wait_for_load_state_best_effort(
    page,
    "networkidle",
    min(timeout_ms, network_idle_timeout_ms),
  )
  await _wait_for_dom_stability(
    page,
    timeout_ms=timeout_ms,
    poll_interval_ms=poll_interval_ms,
    stable_repeats_required=stable_repeats_required,
  )


async def wait_after_action(
  page: Page,
  *,
  mutation_timeout_ms: int = 2_000,
  settle_timeout_ms: int = 3_000,
  network_idle_timeout_ms: int = 1_200,
  poll_interval_ms: int = 100,
  stable_repeats_required: int = 2,
) -> None:
  """
  Best-effort SPA settling after an action.

  This waits for either a DOM mutation or timeout, then runs the same lightweight
  readiness checks used after navigation. Failures are intentionally non-fatal.
  """
  await _wait_for_dom_mutation_or_timeout(page, timeout_ms=mutation_timeout_ms)
  await wait_for_page_ready(
    page,
    timeout_ms=settle_timeout_ms,
    network_idle_timeout_ms=network_idle_timeout_ms,
    poll_interval_ms=poll_interval_ms,
    stable_repeats_required=stable_repeats_required,
  )
