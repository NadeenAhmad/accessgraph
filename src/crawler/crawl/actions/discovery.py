import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Sequence

if TYPE_CHECKING:
  from playwright.async_api import Locator, Page
else:
  Locator = Page = Any

ActionType = Literal["click", "type", "select", "check", "radio", "fill_submit", "hover", "key"]
# Words that make an action unsafe. On hosts the user explicitly allows (local apps), the ones in
# LOCAL_ONLY_ALLOWED_WORDS are permitted so that checkout and removal flows can be explored.
DESTRUCTIVE_WORDS = ("login", "log in", "sign in", "delete", "remove", "checkout", "purchase", "unsubscribe")
LOCAL_ONLY_ALLOWED_WORDS = ("delete", "remove", "checkout", "purchase")
BLOCKED_INPUT_TYPES = {"hidden", "file", "image"}
LINK_BUCKET_STRATEGIES = {"links", "role_link"}


@dataclass(frozen=True)
class LocatorStrategy:
  """Defines one way to discover actionable elements."""

  name: str
  selector: str


@dataclass(frozen=True)
class ActionCandidate:
  locator: Locator
  action_type: ActionType
  strategy_name: str
  identity: str = ""
  text: str = ""
  href: str | None = None
  tag_name: str = ""
  input_type: str | None = None
  button_type: str = ""
  role: str = ""
  inferred_role: str = ""
  aria_label: str = ""
  label_text: str = ""
  data_testid: str = ""
  dom_path: str = ""
  nearby_heading: str = ""
  aria_expanded: str | None = None
  aria_current: str | None = None
  selector: str = ""
  in_header: bool = False
  in_nav: bool = False
  in_main: bool = False
  in_footer: bool = False
  ancestor_roles: tuple[str, ...] = ()
  ancestor_tags: tuple[str, ...] = ()
  # fill_submit actions only: (field selector, value) pairs, value-set kind, and the form's submit control.
  form_values: tuple[tuple[str, str], ...] = ()
  value_set_kind: str = ""
  form_submit_selector: str = ""
  # "key" actions only: the key pressed on the focused element (W4A phase 1)
  key: str = ""


@dataclass(frozen=True)
class LocatorMeta:
  text: str = ""
  href: str = ""
  tag_name: str = ""
  input_type: str = ""
  button_type: str = ""
  role: str = ""
  inferred_role: str = ""
  aria_label: str = ""
  label_text: str = ""
  data_testid: str = ""
  dom_path: str = ""
  nearby_heading: str = ""
  aria_expanded: str = ""
  aria_current: str = ""
  selector: str = ""
  checked: bool = False
  radio_label_selector: str = ""
  is_form_submit: bool = False
  inside_form: bool = False
  form_is_safe_to_submit: bool = False
  destructive_text: bool = False
  in_header: bool = False
  in_nav: bool = False
  in_main: bool = False
  in_footer: bool = False
  ancestor_roles: tuple[str, ...] = ()
  ancestor_tags: tuple[str, ...] = ()


DEFAULT_CLICK_STRATEGIES: tuple[LocatorStrategy, ...] = (
  LocatorStrategy(name="buttons", selector="button"),
  LocatorStrategy(name="role_button", selector="[role='button']"),
  LocatorStrategy(name="summary", selector="summary"),
  LocatorStrategy(name="role_tab", selector="[role='tab']"),
  LocatorStrategy(name="disclosure", selector="[aria-expanded][aria-controls]"),
  LocatorStrategy(name="links", selector="a[href]"),
  LocatorStrategy(name="selects", selector="select"),
  LocatorStrategy(name="radios", selector="input[type='radio']"),
  LocatorStrategy(
    name="button_inputs",
    selector="input[type='button'], input[type='submit']",
  ),
  # W4A phase 1: what a user reaches by hovering and with the keyboard, not only by clicking
  LocatorStrategy(name="hover_popups",
                  selector="[aria-haspopup]:not([aria-haspopup='false']), [aria-describedby], abbr[title], [data-tooltip]"),
  LocatorStrategy(name="key_widgets",
                  selector="[role='tab'][aria-selected='true'], [role='menubar'] [role='menuitem'], [role='combobox'], "
                           "[role='listbox'], [role='slider'], [role='spinbutton'], [role='tree'] [role='treeitem']"),
  LocatorStrategy(name="dialog_escape", selector="dialog[open], [role='dialog'][aria-modal='true'], [role='alertdialog']"),
)
# The key pressed for each widget role (WAI-ARIA Authoring Practices keyboard interaction).
WIDGET_KEYS = {"tab": "ArrowRight", "menuitem": "ArrowDown", "combobox": "ArrowDown", "listbox": "ArrowDown",
               "slider": "ArrowRight", "spinbutton": "ArrowUp", "treeitem": "ArrowRight"}
NON_CLICK_STRATEGIES = {"hover_popups": "hover", "key_widgets": "key", "dialog_escape": "key"}


async def _locator_fingerprint(loc: Locator) -> str:
  """Build a stable-enough key for de-duplicating candidates across strategies."""
  try:
    return await loc.evaluate(
      """
      (el) => {
        const tag = (el.tagName || '').toLowerCase();
        const id = el.id || '';
        const role = el.getAttribute('role') || '';
        const href = el.getAttribute('href') || '';
        const type = (el.getAttribute('type') || '').toLowerCase();
        const name = (el.getAttribute('name') || '').slice(0, 80);
        const txt = (el.innerText || el.value || '').trim().slice(0, 120);

        const path = [];
        let node = el;
        let depth = 0;
        while (node && node.nodeType === Node.ELEMENT_NODE && depth < 6) {
          const nodeTag = (node.tagName || '').toLowerCase();
          let part = nodeTag;
          if (node.id) {
            part += `#${node.id}`;
            path.unshift(part);
            break;
          }

          const parent = node.parentElement;
          if (parent) {
            const sameTagSiblings = Array.from(parent.children).filter(
              (sibling) => (sibling.tagName || '').toLowerCase() === nodeTag
            );
            const index = sameTagSiblings.indexOf(node);
            if (index >= 0) {
              part += `:nth-of-type(${index + 1})`;
            }
          }

          path.unshift(part);
          node = parent;
          depth += 1;
        }

        return [tag, id, role, href, type, name, txt, path.join('>')].join('|');
      }
      """
    )
  except Exception:
    return ""


async def _is_visible_and_enabled(loc: Locator) -> bool:
  try:
    if not await loc.is_visible():
      return False
    if not await loc.is_enabled():
      return False
    return True
  except Exception:
    return False


async def _input_type(loc: Locator) -> str:
  value = await loc.evaluate("(el) => (el.getAttribute('type') || 'text').toLowerCase()")
  return str(value or "text").lower()


async def _is_actionable_input(loc: Locator) -> bool:
  """Filter out input types that are not useful for crawler interactions."""
  try:
    return await _input_type(loc) not in BLOCKED_INPUT_TYPES
  except Exception:
    return False


async def _extract_locator_meta(loc: Locator, destructive_words: Sequence[str] = DESTRUCTIVE_WORDS) -> LocatorMeta:
  try:
    raw = await loc.evaluate(
      """
      (el) => ({
        text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 120),
        href: el.getAttribute('href') || '',
        tag_name: (el.tagName || '').toLowerCase(),
        input_type: (el.getAttribute('type') || '').toLowerCase(),
        button_type: ((el.tagName || '').toLowerCase() === 'button' ? (el.getAttribute('type') || 'submit').toLowerCase() : ''),
        role: el.getAttribute('role') || '',
        inferred_role: (() => {
          const tag = (el.tagName || '').toLowerCase();
          const type = (el.getAttribute('type') || '').toLowerCase();
          if (tag === 'button') {
            return 'button';
          }
          if (tag === 'a' && el.getAttribute('href')) {
            return 'link';
          }
          if (tag === 'summary') {
            return 'button';
          }
          if (tag === 'select') {
            return el.multiple || el.size > 1 ? 'listbox' : 'combobox';
          }
          if (tag === 'textarea') {
            return 'textbox';
          }
          if (tag === 'input') {
            if (['button', 'submit', 'reset'].includes(type)) {
              return 'button';
            }
            if (type === 'checkbox') {
              return 'checkbox';
            }
            if (type === 'radio') {
              return 'radio';
            }
            if (type === 'range') {
              return 'slider';
            }
            if (type === 'search') {
              return 'searchbox';
            }
            return 'textbox';
          }
          return '';
        })(),
        aria_label: el.getAttribute('aria-label') || '',
        label_text: (() => {
          const labels = [];
          const seenLabels = new Set();
          const addLabel = (value) => {
            const normalized = (value || '').trim();
            if (!normalized || seenLabels.has(normalized)) {
              return;
            }
            seenLabels.add(normalized);
            labels.push(normalized);
          };
          if (el.labels) {
            Array.from(el.labels).forEach((label) => addLabel(label.innerText || ''));
          }
          const id = el.id || '';
          if (id) {
            const explicit = document.querySelector(`label[for="${CSS.escape(id)}"]`);
            if (explicit) {
              addLabel(explicit.innerText || '');
            }
          }
          const wrapping = el.closest('label');
          if (wrapping) {
            addLabel(wrapping.innerText || '');
          }
          return labels.join(' ').slice(0, 160);
        })(),
        data_testid: el.getAttribute('data-testid') || el.getAttribute('data-test-id') || '',
        dom_path: (() => {
          const path = [];
          let node = el;
          let depth = 0;
          while (node && node.nodeType === Node.ELEMENT_NODE && depth < 8) {
            const tag = (node.tagName || '').toLowerCase();
            let part = tag;
            const testId = node.getAttribute('data-testid') || node.getAttribute('data-test-id') || '';
            if (node.id) {
              part += `#${node.id}`;
              path.unshift(part);
              break;
            }
            if (testId) {
              part += `[data-testid="${testId}"]`;
              path.unshift(part);
              break;
            }
            const parent = node.parentElement;
            if (parent) {
              const sameTag = Array.from(parent.children).filter(
                (child) => (child.tagName || '').toLowerCase() === tag
              );
              const index = sameTag.indexOf(node);
              if (index >= 0) {
                part += `:nth-of-type(${index + 1})`;
              }
            }
            path.unshift(part);
            node = parent;
            depth += 1;
          }
          return path.join('>');
        })(),
        nearby_heading: (() => {
          const container = el.closest('section, article, main, aside, form, fieldset, [role="region"], [role="dialog"]');
          const heading = container ? container.querySelector('h1, h2, h3, h4, h5, h6, legend, [role="heading"]') : null;
          return heading ? (heading.innerText || '').trim().slice(0, 160) : '';
        })(),
        aria_expanded: el.getAttribute('aria-expanded') || '',
        aria_current: el.getAttribute('aria-current') || '',
        selector: (() => {
          const tag = (el.tagName || '').toLowerCase();
          if (el.id) {
            return `${tag}#${CSS.escape(el.id)}`;
          }
          const role = el.getAttribute('role') || '';
          const name = el.getAttribute('name') || '';
          if (role) {
            return `${tag}[role="${role}"]`;
          }
          if (name) {
            return `${tag}[name="${name}"]`;
          }
          const parent = el.parentElement;
          if (!parent) {
            return tag;
          }
          const sameTag = Array.from(parent.children).filter(
            (child) => (child.tagName || '').toLowerCase() === tag
          );
          const index = sameTag.indexOf(el);
          return index >= 0 ? `${tag}:nth-of-type(${index + 1})` : tag;
        })(),
        checked: !!el.checked,
        radio_label_selector: (() => {
          const tag = (el.tagName || '').toLowerCase();
          const type = (el.getAttribute('type') || '').toLowerCase();
          if (tag !== 'input' || type !== 'radio') {
            return '';
          }
          if (el.closest('label')) {
            return 'xpath=ancestor::label[1]';
          }
          if (!el.id) {
            return '';
          }
          return `label[for="${CSS.escape(el.id)}"]`;
        })(),
        is_form_submit: (() => {
          const tag = (el.tagName || '').toLowerCase();
          const type = (el.getAttribute('type') || '').toLowerCase();
          if (tag === 'input') {
            return type === 'submit';
          }
          if (tag === 'button') {
            return !!el.form && (!type || type === 'submit');
          }
          return false;
        })(),
        inside_form: !!(el.form || el.closest('form')),
        form_is_safe_to_submit: (() => {
          const form = el.form || el.closest('form');
          if (!form) {
            return false;
          }
          const text = [
            el.innerText || '',
            el.value || '',
            el.getAttribute('aria-label') || '',
            form.getAttribute('aria-label') || '',
            form.getAttribute('action') || ''
          ].join(' ').toLowerCase();
          const destructive = __DESTRUCTIVE_WORDS__.some((token) => text.includes(token));
          if (destructive) {
            return false;
          }
          const controls = Array.from(form.elements || []);
          if (controls.some((control) => {
            const type = (control.getAttribute('type') || '').toLowerCase();
            return type === 'password' || type === 'file';
          })) {
            return false;
          }
          const required = controls.filter((control) => control.required || control.getAttribute('aria-required') === 'true');
          if (required.some((control) => {
            const tag = (control.tagName || '').toLowerCase();
            const type = (control.getAttribute('type') || '').toLowerCase();
            if (tag === 'select') {
              return !control.value;
            }
            if (type === 'checkbox' || type === 'radio') {
              return !control.checked;
            }
            return !String(control.value || '').trim();
          })) {
            return false;
          }
          return typeof form.checkValidity === 'function' ? form.checkValidity() : true;
        })(),
        destructive_text: (() => {
          const text = [
            el.innerText || '',
            el.value || '',
            el.getAttribute('aria-label') || '',
            el.getAttribute('title') || ''
          ].join(' ').toLowerCase();
          return __DESTRUCTIVE_WORDS__.some((token) => text.includes(token));
        })(),
        in_header: !!el.closest('header, [role="banner"]'),
        in_nav: !!el.closest('nav, [role="navigation"]'),
        in_main: !!el.closest('main, [role="main"]'),
        in_footer: !!el.closest('footer, [role="contentinfo"]'),
        ancestor_roles: (() => {
          const roles = [];
          let node = el.parentElement;
          let depth = 0;
          while (node && depth < 6) {
            const role = (node.getAttribute('role') || '').trim();
            if (role) {
              roles.push(role);
            }
            node = node.parentElement;
            depth += 1;
          }
          return roles;
        })(),
        ancestor_tags: (() => {
          const tags = [];
          let node = el.parentElement;
          let depth = 0;
          while (node && depth < 6) {
            const tag = (node.tagName || '').toLowerCase();
            if (tag) {
              tags.push(tag);
            }
            node = node.parentElement;
            depth += 1;
          }
          return tags;
        })()
      })
      """.replace("__DESTRUCTIVE_WORDS__", json.dumps(list(destructive_words)))
    )
    if isinstance(raw, dict):
      ancestor_roles = raw.get("ancestor_roles")
      ancestor_tags = raw.get("ancestor_tags")
      return LocatorMeta(
        text=str(raw.get("text") or ""),
        href=str(raw.get("href") or ""),
        tag_name=str(raw.get("tag_name") or ""),
        input_type=str(raw.get("input_type") or ""),
        button_type=str(raw.get("button_type") or ""),
        role=str(raw.get("role") or ""),
        inferred_role=str(raw.get("inferred_role") or ""),
        aria_label=str(raw.get("aria_label") or ""),
        label_text=str(raw.get("label_text") or ""),
        data_testid=str(raw.get("data_testid") or ""),
        dom_path=str(raw.get("dom_path") or ""),
        nearby_heading=str(raw.get("nearby_heading") or ""),
        aria_expanded=str(raw.get("aria_expanded") or ""),
        aria_current=str(raw.get("aria_current") or ""),
        selector=str(raw.get("selector") or ""),
        checked=bool(raw.get("checked")),
        radio_label_selector=str(raw.get("radio_label_selector") or ""),
        is_form_submit=bool(raw.get("is_form_submit")),
        inside_form=bool(raw.get("inside_form")),
        form_is_safe_to_submit=bool(raw.get("form_is_safe_to_submit")),
        destructive_text=bool(raw.get("destructive_text")),
        in_header=bool(raw.get("in_header")),
        in_nav=bool(raw.get("in_nav")),
        in_main=bool(raw.get("in_main")),
        in_footer=bool(raw.get("in_footer")),
        ancestor_roles=tuple(
          str(value)
          for value in ancestor_roles
          if isinstance(ancestor_roles, list) and value
        ),
        ancestor_tags=tuple(
          str(value)
          for value in ancestor_tags
          if isinstance(ancestor_tags, list) and value
        ),
      )
  except Exception:
    pass
  return LocatorMeta()


def _infer_action_type(strategy_name: str, tag_name: str, input_type: str) -> ActionType | None:
  if strategy_name == "radios" and tag_name == "input" and input_type == "radio":
    return "radio"

  if strategy_name == "selects" or tag_name == "select":
    return "select"

  if tag_name == "input":
    normalized_type = input_type or "text"
    if normalized_type in BLOCKED_INPUT_TYPES:
      return None
    if normalized_type in {"checkbox", "radio"}:
      return None
    if normalized_type in {"button", "submit"}:
      return "click"
    return None

  return "click"


def _radio_option_name(meta: LocatorMeta) -> str:
  return (
    meta.label_text
    or meta.aria_label
    or meta.text
    or meta.data_testid
    or meta.selector
    or meta.dom_path
    or "option"
  )


async def _radio_activation_locator(page: Page, loc: Locator, meta: LocatorMeta) -> Locator | None:
  if meta.checked:
    return None

  try:
    if not await loc.is_enabled():
      return None
  except Exception:
    return None

  try:
    if await loc.is_visible():
      return loc
  except Exception:
    pass

  if not meta.radio_label_selector:
    return None

  try:
    label = (
      loc.locator(meta.radio_label_selector)
      if meta.radio_label_selector.startswith("xpath=")
      else page.locator(meta.radio_label_selector).first
    )
    if callable(label):
      label = label()
    if await label.is_visible() and await label.is_enabled():
      return label
  except Exception:
    return None

  return None


def _is_safe_candidate(meta: LocatorMeta, action_type: ActionType) -> bool:
  if meta.destructive_text:
    return False
  if action_type in {"type", "check"}:
    return False
  if meta.is_form_submit and not meta.form_is_safe_to_submit:
    return False
  if action_type == "select" and meta.inside_form and not meta.form_is_safe_to_submit:
    return False
  return True


async def _collect_candidates_for_strategy(
  page: Page,
  strategy: LocatorStrategy,
  limit: int,
  seen: set[str],
  out: list[ActionCandidate],
  destructive_words: Sequence[str] = DESTRUCTIVE_WORDS,
) -> None:
  source = page.locator(strategy.selector)
  count = await source.count()

  for idx in range(count):
    if len(out) >= limit:
      return

    loc = source.nth(idx)
    if strategy.name != "radios" and not await _is_visible_and_enabled(loc):
      continue

    if strategy.name == "inputs" and not await _is_actionable_input(loc):
      continue

    fingerprint = await _locator_fingerprint(loc)
    if fingerprint and strategy.name in NON_CLICK_STRATEGIES:
      fingerprint = f"{fingerprint}|{strategy.name}"  # hovering or a key press is another action than a click
    if fingerprint and fingerprint in seen:
      continue

    meta = await _extract_locator_meta(loc, destructive_words)
    action_type = NON_CLICK_STRATEGIES.get(strategy.name) or _infer_action_type(
      strategy_name=strategy.name,
      tag_name=meta.tag_name,
      input_type=meta.input_type,
    )
    key = ""
    if strategy.name == "dialog_escape":
      key = "Escape"
    elif strategy.name == "key_widgets":
      key = WIDGET_KEYS.get((meta.role or meta.inferred_role or "").lower(), "ArrowDown")
    if action_type is None:
      continue
    activation_locator = loc
    if action_type == "radio":
      radio_locator = await _radio_activation_locator(page, loc, meta)
      if radio_locator is None:
        continue
      activation_locator = radio_locator
    if not _is_safe_candidate(meta, action_type):
      continue

    if fingerprint:
      seen.add(fingerprint)

    out.append(
      ActionCandidate(
        locator=activation_locator,
        action_type=action_type,
        strategy_name=strategy.name,
        identity=fingerprint,
        text=f"select radio: {_radio_option_name(meta)}" if action_type == "radio" else meta.text,
        href=meta.href or None,
        tag_name=meta.tag_name,
        input_type=meta.input_type or None,
        button_type=meta.button_type,
        role=meta.role,
        inferred_role=meta.inferred_role,
        aria_label=meta.aria_label,
        label_text=meta.label_text,
        data_testid=meta.data_testid,
        dom_path=meta.dom_path,
        nearby_heading=meta.nearby_heading,
        aria_expanded=meta.aria_expanded or None,
        aria_current=meta.aria_current or None,
        selector=meta.selector,
        in_header=meta.in_header,
        in_nav=meta.in_nav,
        in_main=meta.in_main,
        in_footer=meta.in_footer,
        ancestor_roles=meta.ancestor_roles,
        ancestor_tags=meta.ancestor_tags,
        key=key,
      )
    )


async def get_action_candidates(
  page: Page,
  limit: int = 20,
  strategies: Sequence[LocatorStrategy] | None = None,
  allow_hosts: Sequence[str] = (),
) -> list[ActionCandidate]:
  """
  Return up to `limit` visible actionable candidates.

  Use `strategies` to extend or override locator discovery order. On hosts in `allow_hosts` (local apps the
  user allows to be changed), checkout, purchase, remove and delete actions are allowed; login, sign in and
  unsubscribe stay blocked everywhere.
  """
  if limit <= 0:
    return []

  active_strategies = tuple(strategies) if strategies is not None else DEFAULT_CLICK_STRATEGIES
  if not active_strategies:
    return []

  per_strategy_limit = min(
    limit,
    max(1, ((limit + len(active_strategies) - 1) // len(active_strategies)) + 2),
  )
  ordered_buckets: list[list[ActionCandidate]] = []
  seen: set[str] = set()
  destructive_words = DESTRUCTIVE_WORDS
  if allow_hosts:
    from urllib.parse import urlparse

    if (urlparse(page.url).hostname or "").lower() in {h.lower() for h in allow_hosts}:
      destructive_words = tuple(w for w in DESTRUCTIVE_WORDS if w not in LOCAL_ONLY_ALLOWED_WORDS)

  for strategy in active_strategies:
    bucket_limit = per_strategy_limit
    if strategy.name in LINK_BUCKET_STRATEGIES:
      bucket_limit = min(limit, max(per_strategy_limit * 3, per_strategy_limit + 5))
    bucket: list[ActionCandidate] = []
    await _collect_candidates_for_strategy(page, strategy, bucket_limit, seen, bucket, destructive_words)
    ordered_buckets.append(bucket)

  candidates: list[ActionCandidate] = []
  for bucket in ordered_buckets:
    for candidate in bucket:
      candidates.append(candidate)
      if len(candidates) >= limit:
        return candidates

  return candidates
