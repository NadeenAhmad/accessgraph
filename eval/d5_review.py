"""D5 expert review material: replay each of the 165 items in its running app and capture what an expert sees.
Free (no model calls). Local apps only (eval/d5_apps.yaml); every item starts in a fresh browser context.

  python -m eval.d5_review capture [--apps APP ...] [--items D5-001 ...]

Per item (results/d5/review/items/<id>/): one screenshot per recorded step with the element about to be used
outlined (`step-<k>.jpg`), `s1.jpg` (the screen with the element or action that matters, outlined), `s2.jpg` (the
screen right after that action, when there is one), `clip.mp4` (the action, a few seconds, with a visible pointer),
and `meta.json` (what was reached, addresses, titles, and whether the replay matched the recording).

Three kinds of items:
- control: the element is a link, button or widget; s1 = the recorded screen with it outlined, the action = clicking
  it, s2 = right after (links to other sites are not opened; their address is recorded instead); the path is the
  shortest prefix of the recorded one after which the control looks the same and clicking it gives the same screen;
- arrival: the check is about a screen reached by an action (headings, landmarks, page titles, form labels on a
  `backward` item): s1 = the screen before, with the action's element outlined, s2 = the screen reached, with the
  element outlined;
- still: images, language, autocomplete, error messages and widget states: s1 only, element outlined.

Pilot review (2026-11-27): for all other items, the earliest screen of the path on which the judged element and what
it is compared with already look as judged is shown (an action that changes neither is left out); headings and regions
are placed near the top so their content is visible, other elements in the middle, page-level checks from the top.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "d5" / "export165"
OUT = ROOT / "results" / "d5" / "review"
VIEW = {"width": 1280, "height": 800}
FFMPEG = "/usr/local/bin/ffmpeg"
CONTROL = {"link-text-mismatch", "button-label-mismatch", "widget-label-purpose-mismatch"}
ARRIVAL = {"heading-not-descriptive", "landmark-purpose-mismatch", "page-title-not-descriptive", "form-label-mismatch"}
MARK = (232, 89, 12)
PLACE_TOP = {"heading-not-descriptive", "landmark-purpose-mismatch"}  # the element at the top, its content below it
PAGE_LEVEL = {"page-title-not-descriptive", "lang-mismatch"}           # the screen from its top
# What makes two screens equivalent for a question: the judged element looks the same (text, attributes, visible) and
# so does what the question compares it with (the content around it; for page-level checks, the page's content).
SIGNATURE = """([xp, type]) => {
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
  const txt = e => norm(e ? (e.innerText !== undefined ? e.innerText : e.textContent) : '');
  let n = null;
  if (xp) { try { n = document.evaluate(xp, document, null, 9, null).singleNodeValue; } catch (e) { n = null; } }
  const vis = e => { if (!e || !e.getBoundingClientRect) return false; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
                     return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const ATTRS = ['alt', 'aria-label', 'aria-labelledby', 'aria-describedby', 'aria-expanded', 'aria-pressed', 'aria-selected',
                 'aria-checked', 'aria-current', 'aria-invalid', 'autocomplete', 'src', 'href', 'placeholder', 'role', 'title'];
  const live = () => [...document.querySelectorAll('[aria-live],[role=alert],[role=status]')].map(txt).filter(Boolean).join(' | ').slice(0, 300);
  const page = type === 'page-title-not-descriptive' || type === 'lang-mismatch';
  let ctx = '';
  if (page) ctx = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading]')].filter(vis).map(txt).join(' | ').slice(0, 600)
                  + ' || ' + location.pathname + location.hash;
  else if (n) {
    if (type === 'landmark-purpose-mismatch') ctx = txt(n).slice(0, 600);
    else {
      const own = txt(n).length;
      let c = n.parentElement;
      while (c && c !== document.body && txt(c).length <= own + 40) c = c.parentElement;
      ctx = txt(c).slice(0, 600);
    }
    if (type === 'error-message-mismatch') {
      const d = (n.getAttribute('aria-describedby') || '').split(/\\s+/).filter(Boolean).map(id => document.getElementById(id)).filter(Boolean).map(txt).join(' | ');
      ctx += ' || ' + d;
    }
    if (type === 'aria-state-mismatch') {
      const ids = (n.getAttribute('aria-controls') || '').split(/\\s+/).filter(Boolean);
      ctx += ' || ' + ids.map(id => vis(document.getElementById(id)) ? 'shown' : 'hidden').join(',');
    }
  }
  if (type === 'error-message-mismatch') ctx += ' || ' + live();
  ctx = ctx.replace(/[0-9][0-9.,]*/g, '#');  // several apps make up new figures on every load
  return JSON.stringify({present: page || !!n, visible: page || vis(n), text: n ? txt(n).slice(0, 300) : '',
    attrs: n && n.getAttribute ? ATTRS.map(a => n.getAttribute(a)).join('|') : '', ctx, lang: document.documentElement.lang,
    title: page ? document.title : '', route: type === 'page-title-not-descriptive' ? location.pathname + location.hash : ''});
}"""

POINTER = """(p) => {
  let c = document.getElementById('__ptr');
  if (!c) { c = document.createElement('div'); c.id = '__ptr';
    c.style.cssText = 'position:fixed;z-index:2147483647;width:28px;height:28px;margin:-14px 0 0 -14px;border-radius:50%;'
      + 'background:rgba(232,89,12,.35);border:3px solid #e8590c;pointer-events:none;transition:left .7s ease, top .7s ease, transform .15s, opacity .4s';
    c.style.left = (innerWidth / 2) + 'px'; c.style.top = (innerHeight / 2) + 'px'; document.body.appendChild(c); }
  c.style.opacity = '1';
  requestAnimationFrame(() => { c.style.left = p.x + 'px'; c.style.top = p.y + 'px'; });
}"""
PRESS = "() => { const c = document.getElementById('__ptr'); if (c) { c.style.transform = 'scale(.6)'; setTimeout(() => c.style.transform = 'scale(1)', 180); } }"
OUTCOME = """() => {
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
  const shown = [...document.querySelectorAll('[role=dialog],[role=menu],[role=listbox],[role=alertdialog],dialog[open]')]
    .filter(e => e.getBoundingClientRect().height > 0).map(e => norm(e.innerText).slice(0, 200));
  return JSON.stringify({route: location.pathname + location.hash, title: document.title,
    text: norm((document.querySelector('main') || document.body).innerText).replace(/[0-9][0-9.,]*/g, '#').slice(0, 800),
    shown: shown.map(t => t.replace(/[0-9][0-9.,]*/g, '#'))});
}"""
HIDE = "() => { const c = document.getElementById('__ptr'); if (c) c.style.opacity = '0'; }"
BY_XPATH = """(xp) => { const n = document.evaluate(xp, document, null, 9, null).singleNodeValue; return !!n; }"""


def _rows(path: Path) -> list[dict]:
  with path.open(encoding="utf-8", newline="") as stream:
    return list(csv.DictReader(stream))


def _ns_free(xpath: str) -> str:
  return re.sub(r"/([A-Za-z][\w-]*)(?=\[|/|$)", lambda m: f'/*[local-name()="{m.group(1).lower()}"]', xpath)


def kind_of(ctype: str, direction: str, steps: int) -> str:
  if ctype in CONTROL:
    return "control"
  if ctype in ARRIVAL and direction == "backward" and steps > 0:
    return "arrival"
  return "still"


def _local(url: str) -> bool:
  host = urlparse(url).hostname or ""
  return host in ("127.0.0.1", "localhost", "")


def _settle(page, ms: int = 700) -> None:
  try:
    page.wait_for_load_state("networkidle", timeout=8000)
  except Exception:
    pass
  page.wait_for_timeout(ms)


def _locate(page, action: dict):
  """The element a recorded step used: its DOM path first, then link address and text, then text and tag. For a
  form fill-in, the first field it filled (where the pointer goes in the clip)."""
  if action.get("type") == "fill_submit":
    for selector, _value in action.get("form_values") or []:
      try:
        loc = page.locator(f"css={selector}").first
        if loc.count() and loc.is_visible():
          return loc
      except Exception:
        continue
    return None
  candidates = []
  dom_path = action.get("dom_path") or ""
  if dom_path:
    candidates.append(page.locator(f"css=body > {dom_path}" if not dom_path.startswith(("html", "body")) else f"css={dom_path}"))
    candidates.append(page.locator(f"css={dom_path}"))
  text = (action.get("text") or "").split("\n")[0].strip()
  tag = (action.get("tag_name") or "").lower()
  if action.get("href"):
    candidates.append(page.locator(f'a[href="{action["href"]}"]').filter(has_text=text) if text else page.locator(f'a[href="{action["href"]}"]'))
  if text and tag:
    candidates.append(page.locator(tag).filter(has_text=text))
  if action.get("selector"):
    candidates.append(page.locator(f"css={action['selector']}"))
  for loc in candidates:
    try:
      n = loc.count()
      for i in range(min(n, 8)):
        el = loc.nth(i)
        if el.is_visible():
          return el
    except Exception:
      continue
  return None


def _element_by_xpath(page, xpath: str):
  for xp in (xpath, _ns_free(xpath)):
    try:
      if page.evaluate(BY_XPATH, xp):
        loc = page.locator(f"xpath={xp}").first
        return loc
    except Exception:
      continue
  return None


def _unhover(page) -> None:
  """Moves the mouse off the page, so that a tooltip left by the last hover or click is not in the screenshot."""
  try:
    page.mouse.move(-20, -20)
    page.wait_for_timeout(350)
  except Exception:
    pass


def _shot(page, path: Path, element=None, place: str = "center") -> dict | None:
  """Viewport screenshot (JPEG) with the element outlined; returns the element's box in the image. `place`: "center"
  (the element in the middle, with what surrounds it), "top" (headings and regions: the element near the top, so the
  content it introduces is visible below it), "page" (page-level checks: the screen from its top)."""
  from PIL import Image, ImageDraw
  box = None
  _unhover(page)
  if place == "page":
    page.evaluate("() => scrollTo(0, 0)")
    page.wait_for_timeout(250)
  if element is not None:
    try:
      if place == "top":  # behavior 'instant': pages with smooth scrolling would still be moving at the screenshot
        element.evaluate("e => { e.style.scrollMarginTop = '90px'; e.scrollIntoView({block: 'start', behavior: 'instant'}); }")
      elif place == "center":
        element.evaluate("e => e.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'})")
      page.wait_for_timeout(250)
      box = element.bounding_box()
      if box and (box["y"] + box["height"] <= 0 or box["y"] >= VIEW["height"] or box["x"] + box["width"] <= 0 or box["x"] >= VIEW["width"]):
        element.scroll_into_view_if_needed(timeout=3000)
        page.wait_for_timeout(250)
        box = element.bounding_box()
    except Exception:
      try:
        element.scroll_into_view_if_needed(timeout=3000)
        page.wait_for_timeout(250)
        box = element.bounding_box()
      except Exception:
        box = None
  png = path.with_suffix(".png")
  page.screenshot(path=str(png))
  im = Image.open(png).convert("RGB")
  if box and box["width"] > 2 and box["height"] > 2:  # an element without size (hidden text) is not outlined
    x0, y0 = max(0, box["x"] - 5), max(0, box["y"] - 5)
    x1, y1 = min(im.width - 1, box["x"] + box["width"] + 5), min(im.height - 1, box["y"] + box["height"] + 5)
    if x1 > x0 and y1 > y0:
      d = ImageDraw.Draw(im)
      for k in range(4):
        d.rectangle([x0 - k, y0 - k, x1 + k, y1 + k], outline=MARK)
    else:  # the element is not on the screenshot: no outline, and the site check reports it
      box = None
  im.save(path, quality=86)
  png.unlink()
  return box


def _signature(page, xpath: str, ctype: str) -> dict | None:
  _unhover(page)
  for xp in ((xpath, _ns_free(xpath)) if xpath else ("",)):
    try:
      sig = json.loads(page.evaluate(SIGNATURE, [xp, ctype]))
    except Exception:
      continue
    if sig.get("present"):
      return sig
  return None


def _outcome(page) -> dict | None:
  _unhover(page)
  try:
    return json.loads(page.evaluate(OUTCOME))
  except Exception:
    return None


def shorter_control_path(browser, row: dict, storage: dict, meta: dict) -> int | None:
  """For a control: the fewest path steps after which the control looks as judged and clicking it leads to the same
  screen as after the full path. Each try starts in a fresh browser context; None if no shorter path gives that."""
  replay = json.loads((SRC / "items" / row["item_id"] / "replay.json").read_text(encoding="utf-8"))
  evidence = json.loads((SRC / "items" / row["item_id"] / "evidence.json").read_text(encoding="utf-8"))
  xpath = ((evidence.get("element_refs") or [{}])[0]).get("xpath") or ""
  want, outcome = meta.get("_final_sig"), meta.get("_outcome")
  if not xpath or not want or (not outcome and not meta.get("external")):
    return None
  for k in range(len(replay["steps"])):
    ctx = browser.new_context(viewport=VIEW)
    if storage:
      ctx.add_init_script("".join(f"if (localStorage.getItem({json.dumps(a)}) === null) localStorage.setItem({json.dumps(a)}, {json.dumps(b)});"
                                  for a, b in storage.items()))
    page = ctx.new_page()
    try:
      page.goto(replay["start_url"], wait_until="domcontentloaded", timeout=60000)
      _settle(page, 900)
      ok = True
      for step in replay["steps"][:k]:
        action = step["action"] or {}
        el = _locate(page, action)
        if el is None and action.get("type") not in ("fill_submit", "key"):
          ok = False
          break
        ok = _do(page, action, el) and ok
        _settle(page)
      if not ok or _signature(page, xpath, row["type"]) != want:
        continue
      if meta.get("external"):
        return k
      target = _element_by_xpath(page, xpath)
      if target is None or not _do(page, {"type": "click"}, target):
        continue
      _settle(page, 1500)
      if _outcome(page) == outcome:
        return k
    except Exception:
      continue
    finally:
      ctx.close()
  return None


def _place(ctype: str) -> str:
  return "top" if ctype in PLACE_TOP else ("page" if ctype in PAGE_LEVEL else "center")


def _candidate(page, out: Path, k: int, xpath: str, ctype: str) -> dict | None:
  """The screen after k path steps, kept in case the judged element already looks as judged here."""
  sig = _signature(page, xpath, ctype)
  if not sig:
    return None
  target = _element_by_xpath(page, xpath) if xpath else None
  shot = out / f"_cand-{k}.jpg"
  box = _shot(page, shot, target, _place(ctype))
  return {"k": k, "sig": sig, "file": shot, "box": box, "url": page.url, "title": page.title()}


def _use_earlier(out: Path, meta: dict, cand: dict) -> None:
  """Show the earliest screen on which the judged element and what it is compared with already look as judged:
  the later steps (and an action that does not change them) are not needed to answer the question."""
  k = cand["k"]
  (out / "s1.jpg").unlink(missing_ok=True)
  cand["file"].rename(out / "s1.jpg")
  for name in ("s2.jpg", "clip.mp4"):
    (out / name).unlink(missing_ok=True)
  for step in meta["steps"][k:]:
    (out / step["file"]).unlink(missing_ok=True)
  meta["trimmed"] = {"kind_before": meta["kind"], "steps_before": len(meta["steps"]) + (1 if meta["kind"] == "arrival" else 0),
                     "steps_now": k, "why": "the judged element and its content already look the same on this screen"}
  meta.update({"kind": "still", "steps": meta["steps"][:k], "s1_box": cand["box"], "s1_url": cand["url"], "s1_title": cand["title"]})
  for key in ("s2_box", "s2_url", "s2_title", "action_label"):
    meta.pop(key, None)


def _click(page, element) -> None:
  """Click like a user; an open menu or popover that covers the element is closed first (Escape), as a user would."""
  try:
    element.click(timeout=4000)
    return
  except Exception:
    pass
  page.keyboard.press("Escape")
  page.wait_for_timeout(300)
  try:
    element.click(timeout=4000)
  except Exception:
    element.click(timeout=4000, force=True)


def _do(page, action: dict, element) -> bool:
  kind = action.get("type")
  try:
    if kind == "click":
      _click(page, element)
    elif kind == "hover":
      try:
        element.hover(timeout=4000)
      except Exception:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        element.hover(timeout=4000, force=True)
    elif kind == "key":
      (element if element is not None else page.locator(":focus").first).press(action.get("key") or "Enter", timeout=5000)
    elif kind == "fill_submit":
      # React apps give fields new auto-generated ids on every run (e.g. #:r1b:); such a field is found by its
      # position among the form's fillable fields, in the order the recording filled them
      form = page.locator(f"css={action['selector']}").first if action.get("selector") else page.locator("form").first
      fields = form.locator("input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]), textarea")
      for index, (selector, value) in enumerate(action.get("form_values") or []):
        try:
          target = page.locator(f"css={selector}").first
          if not target.count() and index < fields.count():
            target = fields.nth(index)
          target.fill(str(value), timeout=3000)
        except Exception:
          pass
      if "no submit" not in (action.get("text") or ""):
        try:
          page.locator(f"css={action['form_submit_selector']}").first.click(timeout=4000)
        except Exception:  # a submit button that cannot be clicked: press Enter in the form, as a user would
          (fields.last if fields.count() else form).press("Enter", timeout=4000)
    else:
      return False
    return True
  except Exception:
    return False


def _film_action(page, element, action_fn) -> tuple[float, float] | None:
  """Pointer to the element, press, wait; returns (start, end) seconds of the clip within the page's video."""
  try:
    element.scroll_into_view_if_needed(timeout=3000)
    page.wait_for_timeout(300)
    box = element.bounding_box()
  except Exception:
    box = None
  if not box:
    return None
  t0 = time.monotonic()
  page.wait_for_timeout(1300)
  page.evaluate(POINTER, {"x": box["x"] + box["width"] / 2, "y": box["y"] + box["height"] / 2})
  page.wait_for_timeout(1100)
  page.evaluate(PRESS)
  ok = action_fn()
  page.wait_for_timeout(300)
  try:
    page.evaluate(HIDE)
  except Exception:
    pass
  _settle(page, 2200)
  return (t0, time.monotonic()) if ok else None


def capture_item(browser, item_id: str, row: dict, storage: dict, path_limit: int | None = None) -> dict:
  src = SRC / "items" / item_id
  out = OUT / "items" / item_id
  out.mkdir(parents=True, exist_ok=True)
  for old in out.glob("*"):
    old.unlink()
  evidence = json.loads((src / "evidence.json").read_text(encoding="utf-8"))
  replay = json.loads((src / "replay.json").read_text(encoding="utf-8"))
  steps = replay["steps"] if path_limit is None else replay["steps"][:path_limit]
  kind = kind_of(row["type"], row["direction"], len(steps))
  meta = {"item_id": item_id, "app": row["app"], "type": row["type"], "kind": kind, "steps": [], "problems": []}
  video_dir = out / "_video"
  ctx = browser.new_context(viewport=VIEW, record_video_dir=str(video_dir), record_video_size=VIEW)
  if storage:
    ctx.add_init_script("".join(f"if (localStorage.getItem({json.dumps(k)}) === null) localStorage.setItem({json.dumps(k)}, {json.dumps(v)});"
                                for k, v in storage.items()))
  t_start = time.monotonic()
  page = ctx.new_page()
  clip = None
  xpath = ((evidence.get("element_refs") or [{}])[0]).get("xpath") or ""
  trim = row["type"] not in CONTROL  # a control's outcome can depend on the path, so its path is always kept
  cands: list[dict | None] = []
  final = None
  try:
    page.goto(replay["start_url"], wait_until="domcontentloaded", timeout=60000)
    _settle(page, 900)
    path_steps = steps[:-1] if kind == "arrival" else steps
    for k, step in enumerate(path_steps, 1):
      if trim:
        cands.append(_candidate(page, out, k - 1, xpath, row["type"]))
      action = step["action"] or {}
      el = _locate(page, action)
      page.evaluate("() => scrollTo(0, 0)")
      shot = out / f"step-{k}.jpg"
      _shot(page, shot, el)
      label = _step_label(action)
      href = action.get("href") or ""
      if el is None and href and not href.startswith(("http:", "https:", "mailto:")):
        page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=30000)  # a link inside a closed menu
        _settle(page)
        meta["steps"].append({"file": shot.name, "label": label, "ok": True})
        continue
      if action.get("type") not in ("fill_submit", "key") and el is None:
        meta["problems"].append(f"step {k}: element not found ({label})")
        meta["steps"].append({"file": shot.name, "label": label, "ok": False})
        continue
      ok = _do(page, action, el)
      _settle(page)
      meta["steps"].append({"file": shot.name, "label": label, "ok": ok})
      if not ok:
        meta["problems"].append(f"step {k}: action failed ({label})")
    recorded_url = (evidence.get("state_context") or {}).get("url") or ""
    if kind == "arrival":
      if trim:
        cands.append(_candidate(page, out, len(path_steps), xpath, row["type"]))
      last = steps[-1]["action"] or {}
      el = _locate(page, last)
      meta["s1_box"] = _shot(page, out / "s1.jpg", el)
      meta["s1_url"], meta["s1_title"] = page.url, page.title()
      meta["action_label"] = _step_label(last)
      if el is not None:
        span = _film_action(page, el, lambda: _do(page, last, el))
        clip = span
      else:
        meta["problems"].append(f"last step: element not found ({meta['action_label']})")
        _do(page, last, None)
        _settle(page)
      target = _element_by_xpath(page, xpath) if xpath else None
      if _content_differs(target, evidence):
        meta["problems"].append("content differs from the recording")
      final = _signature(page, xpath, row["type"]) if trim else None
      meta["s2_box"] = _shot(page, out / "s2.jpg", target, _place(row["type"]))
      meta["s2_url"], meta["s2_title"] = page.url, page.title()
      meta["reached_url_matches"] = _same_route(page.url, recorded_url)
      if target is None and xpath and row["type"] != "page-title-not-descriptive":
        meta["problems"].append("judged element not found on the reached screen")
    else:
      target = _element_by_xpath(page, xpath) if xpath else None
      meta["reached_url_matches"] = _same_route(page.url, recorded_url)
      if target is None and xpath:  # page-level checks (page language) have no element to outline
        meta["problems"].append("judged element not found")
      elif _content_differs(target, evidence):
        meta["problems"].append("content differs from the recording")
      final = _signature(page, xpath, row["type"]) if trim else None
      if kind == "control":
        meta["_final_sig"] = _signature(page, xpath, row["type"])
      meta["s1_box"] = _shot(page, out / "s1.jpg", target, _place(row["type"]))
      meta["s1_url"], meta["s1_title"] = page.url, page.title()
      if kind == "control" and target is not None:
        href = target.evaluate("e => e.closest('a') ? e.closest('a').href : ''") or ""
        meta["href"] = href
        if href and not _local(href):
          meta["external"] = href
        else:
          popup = []
          ctx.on("page", lambda p: popup.append(p))
          clip = _film_action(page, target, lambda: _do(page, {"type": "click"}, target))
          shown = popup[-1] if popup else page
          if popup:
            _settle(shown, 1200)
            meta["opened_new_tab"] = True
          shown.evaluate("() => { const c = document.getElementById('__ptr'); if (c) c.remove(); }") if shown is page else None
          meta["_outcome"] = _outcome(shown)
          meta["s2_box"] = _shot(shown, out / "s2.jpg")
          meta["s2_url"], meta["s2_title"] = shown.url, shown.title()
          if clip is None:
            meta["problems"].append("click on the element failed")
    if final and not meta["problems"]:  # (an element without size matches only a screen where it also has none)
      match = next((c for c in cands if c and c["sig"] == final), None)
      if match:
        _use_earlier(out, meta, match)
        clip = None
  except Exception as error:  # the item keeps what was captured; the problem is flagged
    meta["problems"].append(f"error: {type(error).__name__}: {str(error)[:160]}")
  finally:
    video = page.video.path() if page.video else None
    ctx.close()
  if clip and video:
    start, end = clip[0] - t_start - 0.2, clip[1] - t_start
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{max(0.0, start):.2f}", "-to", f"{end:.2f}", "-i", str(video),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-preset", "medium", "-movflags", "+faststart", "-an",
                    str(out / "clip.mp4")], check=False)
    meta["clip"] = (out / "clip.mp4").exists()
  for f in out.glob("_cand-*.jpg"):
    f.unlink()
  for f in video_dir.glob("*"):
    f.unlink()
  if video_dir.exists():
    video_dir.rmdir()
  (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
  return meta


def _norm(text: str) -> str:
  return " ".join(str(text or "").lower().split())


def _recorded_text(evidence: dict) -> str:
  primary = (evidence.get("evidence") or {}).get("primary") or {}
  for value in primary.values():
    if isinstance(value, dict) and value.get("element_id"):
      return value.get("text") or value.get("accessible_name") or value.get("alt") or ""
  return ""


def _content_differs(target, evidence: dict) -> bool:
  """The replayed element shows other content than the recorded one (apps that make up new data on every start)."""
  recorded = _norm(_recorded_text(evidence))
  if not recorded or target is None:
    return False
  try:
    live = _norm(target.evaluate("e => e.innerText || e.getAttribute('aria-label') || e.getAttribute('alt') || e.value || ''"))
  except Exception:
    return False
  return bool(live) and recorded[:40] not in live and live[:40] not in recorded


def _same_route(a: str, b: str) -> bool:
  pa, pb = urlparse(a), urlparse(b)
  return (pa.path.rstrip("/"), pa.fragment.split("?")[0]) == (pb.path.rstrip("/"), pb.fragment.split("?")[0])


def _step_label(action: dict) -> str:
  text = " ".join((action.get("text") or action.get("accessible_name") or "").split())[:60]
  kind = action.get("type")
  if kind == "fill_submit":
    return "fills in the form" + ("" if "no submit" in (action.get("text") or "") else " and submits it")
  verb = {"click": "clicks", "hover": "points at", "key": "presses a key in"}.get(kind, kind)
  tag = (action.get("tag_name") or "").lower()
  noun = {"a": "link", "button": "button", "img": "image", "input": "field", "select": "drop-down list", "textarea": "text field",
          "svg": "icon", "i": "icon"}.get(tag, "control")
  return f"{verb} “{text}”" if text else f"{verb} a {noun} without a visible name"


def capture(apps_wanted: list[str] | None, items_wanted: list[str] | None) -> None:
  from playwright.sync_api import sync_playwright
  from eval.d5 import apps, serve
  rows = _rows(SRC / "key_do_not_share.csv")
  by_app: dict[str, list[dict]] = {}
  for r in rows:
    if (not apps_wanted or r["app"] in apps_wanted) and (not items_wanted or r["item_id"] in items_wanted):
      by_app.setdefault(r["app"], []).append(r)
  for app, items in by_app.items():
    print(f"[{app}] {len(items)} items", flush=True)
    storage = apps()[app].get("init_storage") or {}
    with serve(app):
      with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for r in items:
          started = time.monotonic()
          meta = capture_item(browser, r["item_id"], r, storage)
          full = len(meta["steps"])
          if meta["kind"] == "control" and full and not meta["problems"]:
            k = shorter_control_path(browser, r, storage, meta)
            if k is not None and k < full:
              short = capture_item(browser, r["item_id"], r, storage, path_limit=k)
              if not short["problems"] and short.get("_outcome") == meta.get("_outcome") and short.get("external") == meta.get("external"):
                short["trimmed"] = {"kind_before": "control", "steps_before": full, "steps_now": k,
                                    "why": "with fewer steps the control looks the same and clicking it leads to the same screen"}
                (OUT / "items" / r["item_id"] / "meta.json").write_text(json.dumps(short, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                meta = short
              else:
                meta = capture_item(browser, r["item_id"], r, storage)  # the shorter path did not hold up: back to the full one
          print(f"  {r['item_id']} {meta['kind']:8s} {time.monotonic() - started:5.1f}s "
                f"{'OK' if not meta['problems'] else 'FLAG ' + '; '.join(meta['problems'])[:140]}", flush=True)
        browser.close()


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("step", choices=("capture",))
  parser.add_argument("--apps", nargs="*")
  parser.add_argument("--items", nargs="*")
  args = parser.parse_args(argv)
  capture(args.apps, args.items)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
