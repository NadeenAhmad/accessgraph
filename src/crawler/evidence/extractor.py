from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any

from .accessibility_context_schema import (
  EXTRACTION_LIMITS,
  ACCESSIBILITY_CONTEXT_SCHEMA_VERSION,
  empty_category_payload,
)


@lru_cache(maxsize=1)
def _browser_accessibility_context_extractor_script() -> str:
  """Load the browser-side accessibility context extractor once per Python process."""
  return Path(__file__).with_name("browser_accessibility_context_extractor.js").read_text(encoding="utf-8")


def _accessibility_context_path(out_dir: Path, state_id: str) -> Path:
  return out_dir / "accessibility_context.json"


def _state_context_payload(
  *,
  depth: int,
  parent_state: str | None,
  action_from_parent: dict[str, object] | None,
) -> dict[str, object]:
  action: dict[str, object] | None = None
  if action_from_parent is not None:
    allowed_action_keys = ("type", "selector", "text", "href", "input_type", "index")
    action = {
      key: action_from_parent[key]
      for key in allowed_action_keys
      if key in action_from_parent
    }

  return {
    "depth": depth,
    "parent_state": parent_state,
    "action_from_parent": action,
  }


def _extraction_metadata(
  *,
  status: str,
  screenshot_path: Path,
  error: str | None = None,
) -> dict[str, Any]:
  metadata: dict[str, Any] = {
    "status": status,
    "screenshot_path": screenshot_path.name,
    "truncated": False,
    "truncation": {},
    "limits": dict(EXTRACTION_LIMITS),
  }
  if error:
    metadata["error"] = error
  return metadata


def _empty_payload(
  *,
  state_id: str,
  url: str,
  title: str,
  screenshot_path: Path,
  depth: int,
  parent_state: str | None,
  action_from_parent: dict[str, object] | None,
  status: str,
  error: str | None = None,
) -> dict[str, Any]:
  payload: dict[str, Any] = {
    "schema_version": ACCESSIBILITY_CONTEXT_SCHEMA_VERSION,
    "state_id": state_id,
    "state_context": _state_context_payload(
      depth=depth,
      parent_state=parent_state,
      action_from_parent=action_from_parent,
    ),
    "page": {
      "url": url,
      "title": title,
      "document_lang": "",
      "html_lang": None,
      "body_text_sample": "",
      "body_text_length": 0,
    },
    "extraction_metadata": _extraction_metadata(
      status=status,
      screenshot_path=screenshot_path,
      error=error,
    ),
  }
  payload.update(empty_category_payload())
  return payload


async def extract_accessibility_context(
  page: Page,
  *,
  state_id: str,
  screenshot_path: Path,
  depth: int = 0,
  parent_state: str | None = None,
  action_from_parent: dict[str, object] | None = None,
) -> dict[str, Any]:
  """Collect structured accessibility context for one rendered state."""
  payload = await page.evaluate(
    _browser_accessibility_context_extractor_script(),
    {
      "stateId": state_id,
      "stateContext": _state_context_payload(
        depth=depth,
        parent_state=parent_state,
        action_from_parent=action_from_parent,
      ),
      "screenshotPath": screenshot_path.name,
      "limits": dict(EXTRACTION_LIMITS),
      "schemaVersion": ACCESSIBILITY_CONTEXT_SCHEMA_VERSION,
    },
  )
  if isinstance(payload, dict):
    for category, default_value in empty_category_payload().items():
      payload.setdefault(category, default_value)
    await apply_browser_accessible_names(page, payload)
    focus_traversal, focus_traversal_metadata = await _capture_focus_traversal(
      page,
      max_steps=EXTRACTION_LIMITS["max_focus_traversal_steps"],
    )
    payload["focus_traversal"] = focus_traversal
    payload["focus_traversal_metadata"] = focus_traversal_metadata
    try:  # let focus and ripple effects of the traversal fade before the crawler looks at the page again
      from ..state.hashing import wait_for_rendered_dom_stable
      await wait_for_rendered_dom_stable(page, timeout_ms=2000)
    except Exception:
      pass
  return payload


# Resolves "/html[1]/body[1]/x-el[1]>>/div[1]/a[1]": steps by tag and position, ">>" enters the element's open
# shadow root or same-origin iframe document.
RESOLVE_SCOPED_PATH_JS = """(path) => {
  let ctx = document, el = null;
  const parts = String(path).split('>>');
  for (let i = 0; i < parts.length; i++) {
    let cur = ctx;
    for (const step of parts[i].split('/').filter(Boolean)) {
      const m = step.match(/^([^\\[]+)(?:\\[(\\d+)\\])?$/);
      if (!m) return null;
      let count = 0, found = null;
      for (const child of Array.from(cur.children || [])) {
        if (child.localName === m[1].toLowerCase() && ++count === Number(m[2] || 1)) { found = child; break; }
      }
      if (!found) return null;
      cur = found;
    }
    el = cur;
    if (i < parts.length - 1) {
      let inner = el.shadowRoot;
      if (!inner && el.tagName === 'IFRAME') { try { inner = el.contentDocument; } catch (e) { inner = null; } }
      if (!inner) return null;
      ctx = inner;
    }
  }
  return el;
}"""


def _name_key(text: str) -> str:
  """Names that differ only in case and white space are the same name."""
  return "".join(str(text or "").lower().split())


# Categories whose items carry an accessible name, and the role the browser gives them when they are exposed.
BROWSER_NAME_CATEGORIES = ("links", "buttons", "images", "form_controls", "headings", "landmarks", "forms")


async def apply_browser_accessible_names(page: Page, payload: dict[str, Any]) -> None:
  """Replace the in-page approximate accessible names with the names the browser computes (W3C accname), so that a
  link named only by its image's alt text, an SVG <title> or a labelled descendant gets its real name. The
  approximation is kept as `approximate_accessible_name`; `accessible_name_source` says which one is used.
  Elements the browser does not expose keep the approximation. Never raises: on any error nothing changes."""
  try:
    cdp = await page.context.new_cdp_session(page)
  except Exception:
    return
  try:
    await cdp.send("DOM.enable")
    await cdp.send("Accessibility.enable")
    for category in BROWSER_NAME_CATEGORIES:
      items = payload.get(category)
      if not isinstance(items, list):
        continue
      for item in items:
        if not isinstance(item, dict) or not item.get("xpath"):
          continue
        try:
          found = await cdp.send("Runtime.evaluate", {"expression": f"({RESOLVE_SCOPED_PATH_JS})({json.dumps(str(item['xpath']))})"})
          object_id = (found.get("result") or {}).get("objectId")
          if not object_id:
            continue
          node = (await cdp.send("DOM.describeNode", {"objectId": object_id}))["node"]
          tree = await cdp.send("Accessibility.getPartialAXTree",
                                {"backendNodeId": node["backendNodeId"], "fetchRelatives": False})
          await cdp.send("Runtime.releaseObject", {"objectId": object_id})
        except Exception:
          continue
        ax = next((n for n in tree.get("nodes", []) if n.get("backendDOMNodeId") == node["backendNodeId"]), None)
        if not ax or ax.get("ignored"):
          continue
        name = str(((ax.get("name") or {}).get("value")) or "").strip()
        role = str(((ax.get("role") or {}).get("value")) or "")
        description = str(((ax.get("description") or {}).get("value")) or "").strip()
        if description:  # what assistive technologies announce as the element's description (e.g. an error icon's label)
          item["browser_description"] = description[:300]
        approximate = str(item.get("accessible_name") or "")
        item["browser_role"] = role or None
        if name and _name_key(name) != _name_key(approximate):
          # the browser's name differs in substance (e.g. it includes an image's alt text): use it
          item["approximate_accessible_name"] = approximate or None
          item["accessible_name"] = name[:500]
          item["accessible_name_source"] = "browser"
        else:
          item["accessible_name_source"] = "approximation (same as browser)" if name else "approximation"
  except Exception:
    return
  finally:
    try:
      await cdp.detach()
    except Exception:
      pass


async def _capture_focus_traversal(
  page: Page,
  *,
  max_steps: int,
) -> tuple[list[dict[str, object]], dict[str, object]]:
  metadata: dict[str, object] = {
    "start_strategy": "focus_body_scroll_to_top_then_tab",
    "max_steps": max(0, max_steps),
    "captured_steps": 0,
    "traversal_complete": False,
    "partial": True,
    "cycle_detected": False,
    "stop_reason": "not_started",
    "initial_focus_selector": "",
    "focus_reset_target": "",
  }
  keyboard = getattr(page, "keyboard", None)
  if keyboard is None or not hasattr(keyboard, "press"):
    metadata["stop_reason"] = "keyboard_unavailable"
    return [], metadata

  initial_selector = ""
  try:
    initial_focus = await page.evaluate(
      """
      () => {
        const active = document.activeElement;
        const cssEscape = (value) => window.CSS && CSS.escape
          ? CSS.escape(String(value))
          : String(value).replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
        const selectorOf = (node) => {
          if (!node || node === document.body || node === document.documentElement) return '';
          const tag = (node.tagName || '').toLowerCase();
          if (node.id) return `${tag}#${cssEscape(node.id)}`;
          const classes = Array.from(node.classList || []).slice(0, 3);
          if (classes.length) return `${tag}.${classes.map(cssEscape).join('.')}`;
          const parent = node.parentElement;
          if (!parent) return tag;
          const siblings = Array.from(parent.children).filter(
            (child) => (child.tagName || '').toLowerCase() === tag
          );
          return `${tag}:nth-of-type(${siblings.indexOf(node) + 1})`;
        };
        const selector = selectorOf(active);
        if (active && typeof active.blur === 'function') active.blur();
        const body = document.body;
        let resetTarget = '';
        if (body && typeof body.focus === 'function') {
          const hadTabindex = body.hasAttribute('tabindex');
          const previousTabindex = body.getAttribute('tabindex');
          body.setAttribute('tabindex', '-1');
          body.focus({ preventScroll: true });
          resetTarget = document.activeElement === body ? 'document.body' : '';
          if (hadTabindex) {
            body.setAttribute('tabindex', previousTabindex || '');
          } else {
            body.removeAttribute('tabindex');
          }
        }
        window.scrollTo(0, 0);
        return { selector, reset_target: resetTarget };
      }
      """
    )
    if isinstance(initial_focus, dict):
      initial_selector = str(initial_focus.get("selector") or "")
      metadata["initial_focus_selector"] = initial_selector
      metadata["focus_reset_target"] = str(initial_focus.get("reset_target") or "")
  except Exception:
    metadata["stop_reason"] = "start_reset_failed"
    return [], metadata

  traversal: list[dict[str, object]] = []
  seen: set[str] = set()
  stop_reason = "max_steps_reached"
  traversal_complete = False
  cycle_detected = False
  try:
    for _ in range(max(0, max_steps)):
      await keyboard.press("Tab")
      item = await page.evaluate(
        """
        () => {
          const el = document.activeElement;
          if (!el || el === document.body || el === document.documentElement) return null;
          const tag = (el.tagName || '').toLowerCase();
          const cssEscape = (value) => window.CSS && CSS.escape
            ? CSS.escape(String(value))
            : String(value).replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
          const selectorOf = (node) => {
            if (node.id) return `${tag}#${cssEscape(node.id)}`;
            const classes = Array.from(node.classList || []).slice(0, 3);
            if (classes.length) return `${tag}.${classes.map(cssEscape).join('.')}`;
            const parent = node.parentElement;
            if (!parent) return tag;
            const siblings = Array.from(parent.children).filter(
              (child) => (child.tagName || '').toLowerCase() === tag
            );
            return `${tag}:nth-of-type(${siblings.indexOf(node) + 1})`;
          };
          const xpathOf = (node) => {
            const parts = [];
            let current = node;
            while (current && current.nodeType === Node.ELEMENT_NODE) {
              const currentTag = (current.tagName || '').toLowerCase();
              let index = 1;
              let previous = current.previousElementSibling;
              while (previous) {
                if ((previous.tagName || '').toLowerCase() === currentTag) index += 1;
                previous = previous.previousElementSibling;
              }
              parts.unshift(`${currentTag}[${index}]`);
              current = current.parentElement;
            }
            return `/${parts.join('/')}`;
          };
          const focusSelector = [
            'a[href]', 'button', 'input:not([type="hidden"])', 'textarea', 'select',
            'summary', '[contenteditable]:not([contenteditable="false"])', '[tabindex]'
          ].join(',');
          const focusables = Array.from(document.querySelectorAll(focusSelector)).filter((candidate) => {
            const style = window.getComputedStyle(candidate);
            const rect = candidate.getBoundingClientRect();
            return !!(rect.width || rect.height)
              && style.display !== 'none'
              && style.visibility !== 'hidden'
              && Number(style.opacity) !== 0
              && !candidate.hidden
              && candidate.getAttribute('aria-hidden') !== 'true'
              && candidate.getAttribute('tabindex') !== '-1';
          });
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          const tabindex = el.getAttribute('tabindex');
          const parsedTabindex = tabindex === null || tabindex.trim() === '' ? null : Number.parseInt(tabindex, 10);
          return {
            selector: selectorOf(el),
            xpath: xpathOf(el),
            tag,
            role: el.getAttribute('role') || null,
            type: el.getAttribute('type') || '',
            text: String(el.innerText || el.getAttribute('aria-label') || '')
              .replace(/\\s+/g, ' ').trim().slice(0, 500),
            accessible_name_hint: String(el.getAttribute('aria-label') || el.title || '')
              .replace(/\\s+/g, ' ').trim().slice(0, 500),
            tabindex,
            tabindex_value: Number.isFinite(parsedTabindex) ? parsedTabindex : null,
            dom_order_index: focusables.indexOf(el),
            is_visible: !!(rect.width || rect.height)
              && style.display !== 'none'
              && style.visibility !== 'hidden'
              && Number(style.opacity) !== 0
              && !el.hidden
              && el.getAttribute('aria-hidden') !== 'true',
            is_disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
            hidden: !!el.hidden,
            bounding_box: {
              x: Number(rect.x.toFixed(2)),
              y: Number(rect.y.toFixed(2)),
              width: Number(rect.width.toFixed(2)),
              height: Number(rect.height.toFixed(2))
            }
          };
        }
        """
      )
      if not isinstance(item, dict):
        stop_reason = "no_focusable_element"
        traversal_complete = True
        break
      key = f"{item.get('selector', '')}|{item.get('xpath', '')}"
      if not key.strip("|") or key in seen:
        stop_reason = "cycle_detected" if key in seen else "missing_focus_identity"
        cycle_detected = key in seen
        traversal_complete = key in seen
        break
      seen.add(key)
      item["order"] = len(traversal) + 1
      traversal.append(item)
  except Exception:
    stop_reason = "traversal_exception"
    traversal_complete = False
  finally:
    try:
      await page.evaluate(
        """
        (selector) => {
          const active = document.activeElement;
          if (active && typeof active.blur === 'function') active.blur();
          if (!selector) return;
          const original = document.querySelector(selector);
          if (original && typeof original.focus === 'function') original.focus();
        }
        """,
        initial_selector,
      )
    except Exception:
      pass
  metadata.update(
    {
      "captured_steps": len(traversal),
      "traversal_complete": traversal_complete,
      "partial": not traversal_complete,
      "cycle_detected": cycle_detected,
      "stop_reason": stop_reason,
    }
  )
  return traversal, metadata


async def write_accessibility_context(
  page: Page,
  out_dir: Path,
  *,
  state_id: str,
  screenshot_path: Path,
  depth: int = 0,
  parent_state: str | None = None,
  action_from_parent: dict[str, object] | None = None,
) -> Path:
  path = _accessibility_context_path(out_dir, state_id)
  try:
    payload = await extract_accessibility_context(
      page,
      state_id=state_id,
      screenshot_path=screenshot_path,
      depth=depth,
      parent_state=parent_state,
      action_from_parent=action_from_parent,
    )
  except Exception as exc:
    try:
      url = page.url
    except Exception:
      url = ""
    try:
      title = await page.title()
    except Exception:
      title = ""
    payload = _empty_payload(
      state_id=state_id,
      url=url,
      title=title,
      screenshot_path=screenshot_path,
      depth=depth,
      parent_state=parent_state,
      action_from_parent=action_from_parent,
      status="failed",
      error=f"{type(exc).__name__}: {exc}",
    )

  path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
  return path
