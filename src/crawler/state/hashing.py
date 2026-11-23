"""State identity hashing for crawl deduplication.

The crawler's preferred path is browser-rendered DOM normalization, because it
sees the live DOM after SPA rendering and interaction. Python raw-HTML
normalization is a fallback/offline approximation for serialized HTML. These
hashes are state-identity fingerprints for deduplication and restore checks;
they are not semantic accessibility evidence.
"""

import hashlib
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_WS_RE = re.compile(r"\s+")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head>", re.IGNORECASE | re.DOTALL)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_MAIN_RE = re.compile(r"<main\b[^>]*>(.*?)</main>", re.IGNORECASE | re.DOTALL)
_BODY_RE = re.compile(r"<body\b[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)
_RAW_HTML_CODE_TAB_ID_RE = re.compile(r"\btab-[a-z0-9]{5,}-\d+\b", re.IGNORECASE)
_RAW_HTML_CODE_GROUP_NAME_RE = re.compile(r"\bcode-group-tabs-[a-z0-9]{5,}\b", re.IGNORECASE)
_DYNAMIC_RE = re.compile(
  r"(\b\d{4}-\d{2}-\d{2}\b)|"  # dates
  r"(\b\d{2}:\d{2}:\d{2}\b)|"  # times
  r"([0-9a-f]{8,})",  # long hex-ish strings
  re.IGNORECASE,
)
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"gclid", "fbclid", "msclkid", "_ga", "_gid", "_gl"}
_KEPT_ATTRS = {
  "role",
  "aria-label",
  "aria-labelledby",
  "aria-describedby",
  "aria-expanded",
  "aria-hidden",
  "aria-controls",
  "alt",
  "title",
  "href",
  "type",
  "name",
  "value",
  "checked",
  "selected",
  "disabled",
  "hidden",
  "class",
}
# TODO(test-plan): Evaluate adding more state/accessibility identity attributes
# in a dedicated behavior-changing PR, with browser and raw-HTML parity tests:
# aria-current, aria-pressed, aria-selected, aria-checked, aria-invalid,
# aria-required, aria-disabled, aria-modal, aria-live, aria-busy, open,
# placeholder, and for.
_KEPT_STYLE_FIELDS = {
  "display",
  "visibility",
  "opacity",
  "position",
  "z-index",
  "overflow",
  "pointer-events",
  "clip",
  "clip-path",
  "width",
  "height",
  "color",
  "background",
  "background-color",
  "border-color",
}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_IGNORED_TAGS = {"script", "style", "noscript"}

BROWSER_NORMALIZED_DOM_IDENTITY_SCRIPT = """
() => {
  const keptAttrs = new Set([
    'role', 'aria-label', 'aria-labelledby', 'aria-describedby',
    'aria-expanded', 'aria-hidden', 'aria-controls', 'alt', 'title',
    'href', 'type', 'name', 'value', 'checked', 'selected', 'disabled',
    'hidden', 'class'
  ]);
  const keptStyleFields = [
    'display', 'visibility', 'opacity', 'position', 'z-index', 'overflow',
    'pointer-events', 'clip', 'clip-path', 'width', 'height', 'color',
    'background', 'background-color', 'border-color'
  ];
  const ignoredTags = new Set(['script', 'style', 'noscript']);
  const voidTags = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);
  const trackingKeys = new Set(['gclid', 'fbclid', 'msclkid', '_ga', '_gid', '_gl']);
  const ws = /\\s+/g;

  const isTrackingKey = (key) => {
    const lowered = String(key || '').toLowerCase();
    return trackingKeys.has(lowered) || lowered.startsWith('utm_');
  };

  const normalizeHref = (value) => {
    try {
      const url = new URL(value, document.location.href);
      for (const key of Array.from(url.searchParams.keys())) {
        if (isTrackingKey(key)) {
          url.searchParams.delete(key);
        }
      }
      const entries = Array.from(url.searchParams.entries()).sort(([a], [b]) => a.localeCompare(b));
      url.search = '';
      for (const [key, val] of entries) {
        url.searchParams.append(key, val);
      }
      return url.href;
    } catch (_err) {
      return String(value || '').trim();
    }
  };

  const isHidden = (el) => {
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'html' || tag === 'body' || tag === 'option') {
      return false;
    }
    if (el.hidden) return true;
    if ((el.getAttribute('aria-hidden') || '').toLowerCase() === 'true') return true;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
      return true;
    }
    const rect = el.getBoundingClientRect();
    return rect.width === 0 && rect.height === 0 && style.position !== 'fixed';
  };

  const attrsFor = (el) => {
    const out = [];
    for (const attr of Array.from(el.attributes || [])) {
      const name = attr.name.toLowerCase();
      if (!keptAttrs.has(name)) continue;
      let value = attr.value || '';
      if (name === 'href') value = normalizeHref(value);
      if (name === 'class') value = value.split(/\\s+/).filter(Boolean).sort().join(' ');
      if (name === 'value') {
        const tag = (el.tagName || '').toLowerCase();
        if (!['input', 'textarea', 'select', 'option'].includes(tag)) continue;
      }
      out.push([name, value.replace(ws, ' ').trim()]);
    }

    const style = window.getComputedStyle(el);
    const stylePairs = [];
    for (const field of keptStyleFields) {
      const value = style.getPropertyValue(field);
      if (value) stylePairs.push(`${field}:${value.replace(ws, ' ').trim()}`);
    }
    if (stylePairs.length) out.push(['style', stylePairs.join(';')]);
    out.sort(([a], [b]) => a.localeCompare(b));
    return out;
  };

  const normalizeNode = (node) => {
    if (node.nodeType === Node.COMMENT_NODE) return '';
    if (node.nodeType === Node.TEXT_NODE) {
      return (node.textContent || '').replace(ws, ' ').trim();
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return '';

    const tag = (node.tagName || '').toLowerCase();
    if (!tag || ignoredTags.has(tag) || isHidden(node)) return '';

    const attrs = attrsFor(node)
      .map(([name, value]) => value ? `${name}="${value}"` : name)
      .join(' ');
    const open = attrs ? `<${tag} ${attrs}>` : `<${tag}>`;
    if (voidTags.has(tag)) return open;

    const children = Array.from(node.childNodes)
      .map(normalizeNode)
      .filter(Boolean)
      .join('');
    return `${open}${children}</${tag}>`;
  };

  const elementPath = (el) => {
    const path = [];
    let node = el;
    let depth = 0;
    while (node && node.nodeType === Node.ELEMENT_NODE && depth < 6) {
      const tag = (node.tagName || '').toLowerCase();
      let part = tag;
      if (node.id) {
        part += `#${node.id}`;
        path.unshift(part);
        break;
      }
      const parent = node.parentElement;
      if (parent) {
        const sameTagSiblings = Array.from(parent.children).filter(
          (sibling) => (sibling.tagName || '').toLowerCase() === tag
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
    return path.join('>');
  };

  const isInViewport = (rect) => (
    rect.width > 0
    && rect.height > 0
    && rect.right > 0
    && rect.bottom > 0
    && rect.left < (window.innerWidth || document.documentElement.clientWidth || 0)
    && rect.top < (window.innerHeight || document.documentElement.clientHeight || 0)
  );

  const isVisiblyInteractive = (el) => {
    if (!el || el.hidden) return false;
    if ((el.getAttribute('aria-hidden') || '').toLowerCase() === 'true') return false;
    if (el.hasAttribute('inert')) return false;
    const style = window.getComputedStyle(el);
    if (
      style.display === 'none'
      || style.visibility === 'hidden'
      || Number(style.opacity) === 0
      || style.pointerEvents === 'none'
    ) {
      return false;
    }
    return isInViewport(el.getBoundingClientRect());
  };

  const textForInteractive = (el) => (
    el.innerText
    || el.value
    || el.getAttribute('aria-label')
    || el.getAttribute('title')
    || ''
  ).replace(ws, ' ').trim().slice(0, 120);

  const interactiveContainerKind = (el) => {
    const tag = (el.tagName || '').toLowerCase();
    const role = (el.getAttribute('role') || '').toLowerCase();
    const marker = [
      tag,
      role,
      el.id || '',
      el.className || '',
      el.getAttribute('aria-modal') || '',
      el.getAttribute('popover') || '',
    ].join(' ').toLowerCase();
    if (
      tag === 'dialog'
      || tag === 'mat-sidenav'
      || tag === 'mat-drawer'
      || role === 'dialog'
      || role === 'menu'
      || role === 'menuitem'
      || el.hasAttribute('open')
      || el.hasAttribute('popover')
      || marker.match(/(^|[-_\\s])(menu|drawer|sidenav|sidebar|dialog|modal|overlay|popover)([-_\\s]|$)/)
    ) {
      return role || tag || 'container';
    }
    return '';
  };

  const interactiveState = () => {
    const actionableSelector = [
      'a[href]',
      'button',
      '[role="button"]',
      '[role="link"]',
      '[role="menuitem"]',
      '[role="tab"]',
      'summary',
      'select',
      'textarea',
      'input:not([type="hidden"])',
      '[aria-expanded][aria-controls]',
    ].join(',');
    const containerSelector = [
      'dialog',
      '[aria-modal="true"]',
      '[role="dialog"]',
      '[role="menu"]',
      '[popover]',
      '[open]',
      'mat-sidenav',
      'mat-drawer',
      '.mat-sidenav',
      '.mat-drawer',
      '.cdk-overlay-pane',
      '.cdk-overlay-container',
      '.modal',
      '.drawer',
      '.sidenav',
      '.sidebar',
      '.popover',
      '.menu',
    ].join(',');
    const containers = Array.from(document.querySelectorAll(containerSelector))
      .filter((el) => interactiveContainerKind(el) && isVisiblyInteractive(el))
      .slice(0, 40)
      .map((el) => ({
        kind: interactiveContainerKind(el),
        path: elementPath(el),
        text: textForInteractive(el),
        expanded: el.getAttribute('aria-expanded') || '',
        hidden: el.hidden || (el.getAttribute('aria-hidden') || '').toLowerCase() === 'true',
      }));
    const seen = new Set();
    const actions = [];
    for (const el of Array.from(document.querySelectorAll(actionableSelector))) {
      if (!isVisiblyInteractive(el)) continue;
      const tag = (el.tagName || '').toLowerCase();
      const role = el.getAttribute('role') || '';
      const href = tag === 'a' ? normalizeHref(el.getAttribute('href') || '') : '';
      const type = (el.getAttribute('type') || '').toLowerCase();
      const entry = {
        tag,
        role,
        href,
        type,
        text: textForInteractive(el),
        aria: el.getAttribute('aria-label') || '',
        expanded: el.getAttribute('aria-expanded') || '',
        controls: el.getAttribute('aria-controls') || '',
        path: elementPath(el),
      };
      const key = JSON.stringify(entry);
      if (seen.has(key)) continue;
      seen.add(key);
      actions.push(entry);
      if (actions.length >= 120) break;
    }
    return { containers, actions };
  };

  const root = document.body || document.documentElement;
  return root ? `${normalizeNode(root)}\n@@interactive:${JSON.stringify(interactiveState())}` : '';
}
"""


def _parse_style(style: str) -> dict[str, str]:
  fields: dict[str, str] = {}
  for declaration in style.split(";"):
    if ":" not in declaration:
      continue
    key, value = declaration.split(":", 1)
    normalized_key = key.strip().lower()
    if normalized_key in _KEPT_STYLE_FIELDS:
      fields[normalized_key] = _WS_RE.sub(" ", value).strip()
  return fields


def _style_hides_element(style: str) -> bool:
  fields = _parse_style(style)
  return (
    fields.get("display", "").lower() == "none"
    or fields.get("visibility", "").lower() == "hidden"
    or fields.get("opacity", "").strip() in {"0", "0.0"}
  )


class _RawHTMLStateIdentityParser(HTMLParser):
  def __init__(self) -> None:
    super().__init__(convert_charrefs=True)
    self.out: list[str] = []
    self.stack: list[tuple[str, bool]] = []

  def _inside_hidden(self) -> bool:
    return any(hidden for _tag, hidden in self.stack)

  def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
    normalized_tag = tag.lower()
    attrs_dict = {name.lower(): value or "" for name, value in attrs}
    hidden = self._inside_hidden() or normalized_tag in _IGNORED_TAGS
    hidden = hidden or "hidden" in attrs_dict
    hidden = hidden or attrs_dict.get("aria-hidden", "").lower() == "true"
    hidden = hidden or _style_hides_element(attrs_dict.get("style", ""))
    if hidden:
      if normalized_tag not in _VOID_TAGS:
        self.stack.append((normalized_tag, hidden))
      return

    kept: list[tuple[str, str]] = []
    for name, value in attrs_dict.items():
      if name == "style":
        style_fields = _parse_style(value)
        if style_fields:
          kept.append(("style", ";".join(f"{key}:{style_fields[key]}" for key in sorted(style_fields))))
        continue
      if name not in _KEPT_ATTRS:
        continue
      if name == "class":
        value = " ".join(sorted(value.split()))
      if name == "href":
        value = value.strip()
      kept.append((name, _WS_RE.sub(" ", value).strip()))
    kept.sort()
    attr_text = "".join(f' {name}="{value}"' if value else f" {name}" for name, value in kept)
    self.out.append(f"<{normalized_tag}{attr_text}>")
    if normalized_tag not in _VOID_TAGS:
      self.stack.append((normalized_tag, hidden))

  def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
    before = len(self.stack)
    self.handle_starttag(tag, attrs)
    if len(self.stack) > before:
      self.handle_endtag(tag)

  def handle_endtag(self, tag: str) -> None:
    normalized_tag = tag.lower()
    if not self.stack:
      return
    open_tag, hidden = self.stack.pop()
    if hidden or normalized_tag in _VOID_TAGS:
      return
    self.out.append(f"</{open_tag}>")

  def handle_data(self, data: str) -> None:
    if self._inside_hidden():
      return
    text = _WS_RE.sub(" ", data).strip()
    if text:
      self.out.append(text)

  def normalized(self) -> str:
    return "".join(self.out)


def _normalize_hash_input(value: str) -> str:
  # Shared final hash-input normalization: collapse whitespace and mask obvious dynamic tokens.
  value = _WS_RE.sub(" ", value).strip()
  value = _DYNAMIC_RE.sub("<DYN>", value)
  return value


def html_hash(html: str) -> str:
  """Hash serialized HTML without state-identity DOM normalization."""
  normalized = _normalize_hash_input(html).encode("utf-8", errors="ignore")
  return hashlib.sha256(normalized).hexdigest()


def _extract_raw_html_identity_region(html: str) -> str:
  main_match = _MAIN_RE.search(html)
  if main_match:
    return main_match.group(1)

  body_match = _BODY_RE.search(html)
  if body_match:
    return body_match.group(1)

  without_head = _HEAD_RE.sub(" ", html)
  return without_head


def _normalize_raw_html_for_state_identity(html: str) -> str:
  """Normalize serialized HTML as a fallback/offline state-identity input.

  This approximates the browser-rendered identity normalization when only raw
  HTML is available. The live crawler should prefer
  normalized_rendered_dom_snapshot_for_page().
  """
  region = _extract_raw_html_identity_region(html)
  region = _HTML_COMMENT_RE.sub(" ", region)
  region = _SCRIPT_STYLE_RE.sub(" ", region)
  # Some documentation SPAs generate unstable code-tab radio ids/names inside the
  # visible body content. These identifiers are not meaningful UI-state evidence.
  region = _RAW_HTML_CODE_TAB_ID_RE.sub("tab-<DYNID>", region)
  region = _RAW_HTML_CODE_GROUP_NAME_RE.sub("code-group-tabs-<DYNID>", region)
  parser = _RawHTMLStateIdentityParser()
  try:
    parser.feed(region)
    normalized = parser.normalized()
  except Exception:
    normalized = region
  return _normalize_hash_input(normalized)


def raw_html_state_identity_hash(html: str) -> str:
  """Hash serialized HTML for fallback/offline state identity checks."""
  normalized = _normalize_raw_html_for_state_identity(html).encode("utf-8", errors="ignore")
  return hashlib.sha256(normalized).hexdigest()


def _is_tracking_query_key(key: str) -> bool:
  lowered = key.lower()
  if lowered in _TRACKING_QUERY_KEYS:
    return True
  return lowered.startswith(_TRACKING_QUERY_PREFIXES)


def _canonical_netloc(*, scheme: str, host: str, port: int | None) -> str:
  is_default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
  if host and port is not None and not is_default_port:
    return f"{host}:{port}"
  return host


def _canonical_query(query: str) -> str:
  query_pairs = parse_qsl(query, keep_blank_values=True)
  filtered_pairs = [(k, v) for k, v in query_pairs if not _is_tracking_query_key(k)]
  filtered_pairs.sort()
  return urlencode(filtered_pairs, doseq=True)


def canonicalize_url_for_state(url: str) -> str:
  parsed = urlparse(url)
  scheme = parsed.scheme.lower()
  host = (parsed.hostname or "").lower()
  netloc = _canonical_netloc(scheme=scheme, host=host, port=parsed.port)

  path = parsed.path or "/"
  if path != "/":
    path = path.rstrip("/") or "/"

  query = _canonical_query(parsed.query)
  return urlunparse((scheme, netloc, path, "", query, parsed.fragment))


def state_dedup_key(*, dom_identity_hash: str, url: str) -> str:
  """Build a state deduplication key from DOM identity hash and canonical URL."""
  canonical_url = canonicalize_url_for_state(url)
  raw = f"{dom_identity_hash}|{canonical_url}".encode("utf-8", errors="ignore")
  return hashlib.sha256(raw).hexdigest()


async def normalized_rendered_dom_snapshot_for_page(page: Any) -> str:
  """Return the preferred browser-rendered DOM state-identity snapshot.

  The Playwright/browser path observes the rendered DOM after SPA updates. If
  browser evaluation is unavailable, fall back to raw page HTML normalization.
  """
  evaluate = getattr(page, "evaluate", None)
  if evaluate is not None:
    try:
      snapshot = await evaluate(BROWSER_NORMALIZED_DOM_IDENTITY_SCRIPT)
      if isinstance(snapshot, str):
        return _normalize_hash_input(snapshot)
    except Exception:
      pass

  content = getattr(page, "content", None)
  if content is None:
    return ""
  return _normalize_raw_html_for_state_identity(await content())


async def rendered_dom_identity_hash_for_page(page: Any) -> str:
  """Hash the rendered DOM for crawler state identity/deduplication."""
  normalized = (await normalized_rendered_dom_snapshot_for_page(page)).encode("utf-8", errors="ignore")
  return hashlib.sha256(normalized).hexdigest()


async def wait_for_rendered_dom_stable(page: Any, *, timeout_ms: int = 3000, interval_ms: int = 250) -> str:
  """Wait until the rendered-DOM identity stops changing (two equal readings in a row) and return it.

  Focus, ripple and transition effects, and data that arrives after `load`, change the DOM for a moment; comparing
  identities during that moment makes a page look like a different state (W4A dev round 2)."""
  import asyncio

  async def pause() -> None:
    wait = getattr(page, "wait_for_timeout", None)
    if wait is not None:
      await wait(interval_ms)
    else:
      await asyncio.sleep(interval_ms / 1000)

  previous = await rendered_dom_identity_hash_for_page(page)
  waited = 0
  while waited < timeout_ms:
    await pause()
    waited += interval_ms
    current = await rendered_dom_identity_hash_for_page(page)
    if current == previous:
      return current
    previous = current
  return previous


BUSY_INDICATORS_JS = """() => {
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const busy = [...document.querySelectorAll('[aria-busy="true"], [role="progressbar"]:not([aria-valuenow])')];
  return busy.some(visible);
}"""


async def wait_for_page_settled(page: Any, *, busy_timeout_ms: int = 5000, stable_timeout_ms: int = 2000) -> None:
  """Before a state is recorded or compared: wait (bounded) until no indeterminate loading indicator is visible
  (an element with aria-busy="true", or a progressbar without a value) and the rendered DOM stops changing.
  SPAs often render a spinner first and their data a moment later (W4A dev round 2)."""
  evaluate = getattr(page, "evaluate", None)
  if evaluate is not None:
    waited, step = 0, 250
    while waited < busy_timeout_ms:
      try:
        if not await evaluate(BUSY_INDICATORS_JS):
          break
      except Exception:
        break
      wait = getattr(page, "wait_for_timeout", None)
      if wait is None:
        break
      await wait(step)
      waited += step
  await wait_for_rendered_dom_stable(page, timeout_ms=stable_timeout_ms)

