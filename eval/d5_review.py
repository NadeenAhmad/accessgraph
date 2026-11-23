"""D5 expert review material: replay each of the 165 items in its running app and capture what an expert sees.
Free (no model calls). Local apps only (eval/d5_apps.yaml); every item starts in a fresh browser context.

  python -m eval.d5_review capture [--apps APP ...] [--items D5-001 ...]

Per item (results/d5/review/items/<id>/): one screenshot per recorded step with the element about to be used
outlined (`step-<k>.jpg`), `s1.jpg` (the screen with the element or action that matters, outlined), `s2.jpg` (the
screen right after that action, when there is one), `clip.mp4` (the action, a few seconds, with a visible pointer),
and `meta.json` (what was reached, addresses, titles, and whether the replay matched the recording).

Three kinds of items:
- control: the element is a link, button or widget; s1 = the recorded screen with it outlined, the action = clicking
  it, s2 = right after (links to other sites are not opened; their address is recorded instead);
- arrival: the check is about a screen reached by an action (headings, landmarks, page titles, form labels on a
  `backward` item): s1 = the screen before, with the action's element outlined, s2 = the screen reached, with the
  element outlined;
- still: images, language, autocomplete, error messages and widget states: s1 only, element outlined.
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


def _shot(page, path: Path, element=None) -> dict | None:
  """Viewport screenshot (JPEG) with the element outlined; returns the element's box in the image."""
  from PIL import Image, ImageDraw
  box = None
  if element is not None:
    try:
      element.scroll_into_view_if_needed(timeout=3000)
      page.wait_for_timeout(250)
      box = element.bounding_box()
    except Exception:
      box = None
  png = path.with_suffix(".png")
  page.screenshot(path=str(png))
  im = Image.open(png).convert("RGB")
  if box and box["width"] > 0 and box["height"] > 0:
    d = ImageDraw.Draw(im)
    x0, y0 = max(0, box["x"] - 5), max(0, box["y"] - 5)
    x1, y1 = min(im.width - 1, box["x"] + box["width"] + 5), min(im.height - 1, box["y"] + box["height"] + 5)
    for k in range(4):
      d.rectangle([x0 - k, y0 - k, x1 + k, y1 + k], outline=MARK)
  im.save(path, quality=86)
  png.unlink()
  return box


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


def capture_item(browser, item_id: str, row: dict, storage: dict) -> dict:
  src = SRC / "items" / item_id
  out = OUT / "items" / item_id
  out.mkdir(parents=True, exist_ok=True)
  for old in out.glob("*"):
    old.unlink()
  evidence = json.loads((src / "evidence.json").read_text(encoding="utf-8"))
  replay = json.loads((src / "replay.json").read_text(encoding="utf-8"))
  steps = replay["steps"]
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
  try:
    page.goto(replay["start_url"], wait_until="domcontentloaded", timeout=60000)
    _settle(page, 900)
    path_steps = steps[:-1] if kind == "arrival" else steps
    for k, step in enumerate(path_steps, 1):
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
    xpath = ((evidence.get("element_refs") or [{}])[0]).get("xpath") or ""
    recorded_url = (evidence.get("state_context") or {}).get("url") or ""
    if kind == "arrival":
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
      meta["s2_box"] = _shot(page, out / "s2.jpg", target)
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
      meta["s1_box"] = _shot(page, out / "s1.jpg", target)
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
          meta["s2_box"] = _shot(shown, out / "s2.jpg")
          meta["s2_url"], meta["s2_title"] = shown.url, shown.title()
          if clip is None:
            meta["problems"].append("click on the element failed")
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
  return f"{verb} “{text}”" if text else f"{verb} a {(action.get('tag_name') or 'control').lower()} without a visible name"


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
