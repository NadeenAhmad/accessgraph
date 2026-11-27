"""D5 expert review site: a static website (for Netlify) built from the captured items. Free.

  python -m eval.d5_site build [--endpoint URL]

Writes the Netlify project (eval/paths.py, D5_REVIEW_SITE_DIR): public/ (index.html with instructions, review.html one item
at a time, items.json with what each item shows: question, rule, neutral facts, screenshots, clip, path; items/<id>/
with the captured images and clips) and a write-only function /api/save that stores each answer in the Netlify Blobs
store `d5-expert-review`. AccessGraph's verdicts are never written into the site. Answers are also kept in the
reviewer's browser so they can stop and resume. Personal links are made once in <D5_REVIEW_DATA_DIR>/links.csv
(chmod 600): main-... (all items), three shared-... (only the 30 items marked `shared` by eval/d5_shared30.py; PI
decision 2026-11-25, replacing a single second reviewer on 50 items) and preview-... (the PI; excluded later).
"""
from __future__ import annotations

import argparse
import csv
import functools
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "d5" / "export165"
CAPTURED = ROOT / "results" / "d5" / "review" / "items"
from eval.paths import D5_REVIEW_DATA, D5_REVIEW_SITE  # noqa: E402
SITE = D5_REVIEW_SITE  # Netlify project (outside the repo: large, deploy state)
PUBLIC = SITE / "public"
PRIVATE = D5_REVIEW_DATA  # reviewer links (never in a repo, never printed)
TEMPLATES = ROOT / "eval" / "d5_site"

QUESTIONS = {
  "link-text-mismatch": ("Does the link text that screen readers read describe where the link goes?", "2.4.4 Link Purpose (In Context), level A: the purpose of each link can be determined from the link text, alone or together with its surrounding text.", "link"),
  "button-label-mismatch": ("Does the button label that screen readers read describe what the button does?", "2.4.6 Headings and Labels, level AA: labels describe the topic or purpose of their control.", "button"),
  "widget-label-purpose-mismatch": ("Does the control label that screen readers read describe what the control does?", "2.4.6 Headings and Labels, level AA, and 4.1.2 Name, Role, Value, level A: the control's name describes its purpose.", "control"),
  "image-alt-not-descriptive": ("Does the text alternative that screen readers read describe the image or its purpose?", "1.1.1 Non-text Content, level A: an image that carries information has a text alternative that serves the same purpose; a purely decorative image may have none.", "image"),
  "heading-not-descriptive": ("Does the heading describe the content of its section?", "2.4.6 Headings and Labels, level AA: headings describe the topic or purpose of their section.", "heading"),
  "landmark-purpose-mismatch": ("Do the region type and the region name that screen readers read describe what the region contains?", "1.3.6 Identify Purpose, level AAA (landmark regions): the purpose of each page region can be determined.", "region"),
  "page-title-not-descriptive": ("Does the page title (the browser tab text) describe this screen?", "2.4.2 Page Titled, level A: the page has a title that describes its topic or purpose.", "page"),
  "form-label-mismatch": ("Does the field label that screen readers read describe what the field is for?", "2.4.6 Headings and Labels, level AA: labels describe the purpose of their field.", "field"),
  "aria-state-mismatch": ("Does the state announced to screen readers match what the control shows?", "4.1.2 Name, Role, Value, level A: the state of a control (open, selected, checked, pressed) is available to assistive technologies and matches what is shown.", "control"),
  "lang-mismatch": ("Is the page's language set correctly?", "3.1.1 Language of Page, level A: the main language of the page is declared correctly.", "page"),
  "error-message-mismatch": ("If there is an input error on this screen, is it identified and described in text?", "3.3.1 Error Identification, level A: when an input error is detected, the field is identified and the error is described in text.", "field"),
  "autocomplete-purpose-mismatch": ("Does the field's autocomplete value match the information the field asks for?", "1.3.5 Identify Input Purpose, level AA: fields that ask for information about the user declare that purpose correctly.", "field"),
}
# one plain line under each question: what it is about (pilot review by the PI, 2026-11-27: terms like "state",
# "region" or "live region" were not understood without it)
HINTS = {
  "link-text-mismatch": "Screen readers read a link's text to the user, often without the text around it (for example in a list of all links on the page).",
  "button-label-mismatch": "Screen readers read a button's label to the user; it should say what the button does.",
  "widget-label-purpose-mismatch": "Screen readers read the label of a control (a tab, a menu, a switch, an option in a list …); it should say what the control does.",
  "image-alt-not-descriptive": "People who cannot see the image hear its text alternative instead. A purely decorative image may have none.",
  "heading-not-descriptive": "Screen reader users jump from heading to heading to find what they need; a heading should say what its section is about.",
  "landmark-purpose-mismatch": "A region is a part of the page that screen readers list so users can jump to it (navigation, main content, a form, a footer …). Screen readers announce each region's type and name.",
  "page-title-not-descriptive": "The page title is the text in the browser tab. Screen readers read it first when a page opens.",
  "form-label-mismatch": "Screen readers read a field's label when the user reaches the field; it should say what to enter.",
  "aria-state-mismatch": "The state of a control is whether it is selected, checked, open or pressed. Screen readers tell the user the state; it should match what the screen shows.",
  "lang-mismatch": "The page code says which language the page is in, so that screen readers pronounce the text correctly.",
  "error-message-mismatch": "When a user makes an input error (for example, submits a form with a required field left empty), the field must be identified and the error described in text. If there is no input error on this screen, answer Yes, it's fine.",
  "autocomplete-purpose-mismatch": "The autocomplete value in the page code tells the browser what a field asks for (for example a name or an email address), so the browser can fill it in.",
}
LANDMARKS = {"nav": "navigation", "main": "main content", "header": "banner (header)", "footer": "content info (footer)",
             "aside": "complementary", "section": "region (a general section of the page)", "form": "form", "search": "search",
             "region": "region (a general section of the page)"}


def _rows(path: Path) -> list[dict]:
  with path.open(encoding="utf-8", newline="") as stream:
    return list(csv.DictReader(stream))


_OVERRIDES_FILE = ROOT / "results" / "d5" / "review" / "overrides.json"  # item-by-item review decisions (optional)
OVERRIDES = {k: v for k, v in (json.loads(_OVERRIDES_FILE.read_text(encoding="utf-8")) if _OVERRIDES_FILE.exists() else {}).items()
             if not k.startswith("_")}
ICON_RE = re.compile(r'<(?:i|span)\b[^>]*class="[^"]*(?:material-icons|material-symbols)[^"]*"[^>]*>\s*([a-z0-9_]+)\s*</(?:i|span)>')


@functools.lru_cache(maxsize=1)
def _icon_words() -> frozenset[str]:
  """Words that icon fonts draw as icons (e.g. <i class="material-icons">settings</i>), from the recorded pages; cached
  in results/d5/icon_words.json. Their text is in the recording but is not visible text."""
  cache = ROOT / "results" / "d5" / "icon_words.json"
  if cache.exists():
    return frozenset(json.loads(cache.read_text(encoding="utf-8")))
  words: set[str] = set()
  for dom in (ROOT / "runs" / "w4a-d5").glob("*/explore/states/*/dom.html"):
    words |= set(ICON_RE.findall(dom.read_text(encoding="utf-8", errors="ignore")))
  cache.write_text(json.dumps(sorted(words), indent=1) + "\n", encoding="utf-8")
  return frozenset(words)


LIPSUM = """a ac accumsan adipiscing aenean aliquam aliquet amet ante arcu at auctor augue bibendum blandit commodo condimentum
congue consectetur consequat convallis cras cubilia curabitur curae cursus dapibus diam dictum dictumst dignissim dis dolor
donec dui duis efficitur egestas eget eleifend elementum elit enim erat eros est et etiam eu euismod ex facilisi facilisis
fames faucibus felis fermentum feugiat finibus fringilla fusce gravida habitant habitasse hac hendrerit himenaeos iaculis id
imperdiet in inceptos integer interdum ipsum justo lacinia lacus laoreet lectus leo libero ligula litora lobortis lorem luctus
maecenas magna magnis malesuada massa mattis mauris maximus metus mi molestie mollis montes morbi mus nam nascetur natoque nec
neque netus nibh nisi nisl non nostra nulla nullam nunc odio orci ornare parturient pellentesque penatibus per pharetra
phasellus placerat platea porta porttitor posuere potenti praesent pretium primis proin pulvinar purus quam quis quisque
rhoncus ridiculus risus rutrum sagittis sapien scelerisque sed sem semper senectus sit sociosqu sodales sollicitudin suscipit
suspendisse taciti tellus tempor tempus tincidunt torquent tortor tristique turpis ullamcorper ultrices ultricies urna ut
varius vehicula vel velit venenatis vestibulum vitae vivamus viverra volutpat vulputate""".split()  # the lorem-ipsum vocabulary


def _latin_words() -> frozenset[str]:
  """The made-up Latin of the apps' sample data (faker's lorem words, used by the react-admin examples, plus the classic
  lorem-ipsum vocabulary), without the words that are also English; cached in results/d5/latin_words.json. A fact
  with two or more of them gets a "Translate to English" link on the review page."""
  cache = ROOT / "results" / "d5" / "latin_words.json"
  if cache.exists():
    return frozenset(json.loads(cache.read_text(encoding="utf-8"))["words"])
  words = set(LIPSUM)
  from eval.paths import D5_APPS
  for f in (D5_APPS / "react-admin" / "node_modules" / "@faker-js" / "faker" / "dist").glob("en-*.js"):
    found = re.search(r"[\"'`](a\.ab\.[a-z.]+)[\"'`]", f.read_text(encoding="utf-8", errors="ignore"))
    if found:
      words |= set(found.group(1).split("."))
  english = Path("/usr/share/dict/words")
  if english.exists():
    words -= {w.strip().lower() for w in english.read_text(encoding="utf-8", errors="ignore").split()}
  cache.write_text(json.dumps({"source": "faker en lorem words (react-admin's @faker-js/faker) + lorem-ipsum vocabulary, "
                                         "minus /usr/share/dict/words", "words": sorted(words)}, indent=0) + "\n", encoding="utf-8")
  return frozenset(words)


def _needs_translation(text: str) -> bool:
  return sum(1 for t in re.findall(r"[a-z]+", str(text).lower()) if t in _latin_words()) >= 2


def _no_icons(text: str) -> str:
  """Drops icon-font words: one with an underscore (expand_more), or a lowercase one right before a capitalised word or
  a number ("settings Application settings" -> "Application settings")."""
  toks, words = str(text or "").split(), _icon_words()
  keep = [t for j, t in enumerate(toks)
          if not (t in words and ("_" in t or (j + 1 < len(toks) and toks[j + 1][:1].isupper())))]
  return " ".join(keep)


def _label(text: str) -> str:
  out = re.sub(r"\u201c([^\u201d]*)\u201d", lambda m: "\u201c" + _no_icons(m.group(1)) + "\u201d", text or "")
  return out.replace(" \u201c\u201d", " an icon without text")


AX_REGIONS = {"banner": "banner (page header)", "navigation": "navigation", "complementary": "complementary (a side section, for example a sidebar)",
              "contentinfo": "content info (page footer)", "form": "form", "region": "region (a general section of the page)", "main": "main content",
              "search": "search", "sectionheader": "header of a section (screen readers do not announce it as a region)",
              "sectionfooter": "footer of a section (screen readers do not announce it as a region)"}
ROLE_NAMES = {"button": "button", "a": "link", "menuitem": "menu item", "option": "option in a list", "tab": "tab",
              "combobox": "drop-down list (combobox)", "gridcell": "cell in a grid", "link": "link"}
STATE_NAMES = {"aria_pressed": ("pressed", {"true": "pressed", "false": "not pressed", "mixed": "partly pressed"}),
               "aria_selected": ("selected", {"true": "selected", "false": "not selected"}),
               "aria_expanded": ("expanded", {"true": "expanded (open)", "false": "collapsed (closed)"}),
               "aria_checked": ("checked", {"true": "checked", "false": "not checked", "mixed": "partly checked"}),
               "aria_current": ("current", {"page": "current page", "step": "current step", "true": "current item"})}


def _kind(el: dict) -> str:
  role, tag = str(el.get("role") or "").lower(), str(el.get("tag") or "").lower()
  return ROLE_NAMES.get(role) or ROLE_NAMES.get(tag) or (role or tag or "(not recorded)")


def _shown(value, empty: str) -> str:
  """A fact value; `empty` says in words what an empty value means (never a bare "(none)" that could be misread)."""
  text = " ".join(str(value).split()) if value not in (None, "") else ""
  if len(text) > 220:  # very long names (a whole review as link text) are shortened for reading
    text = text[:220].rsplit(" ", 1)[0] + " \u2026"
  return text if text else empty


def _field_facts(f: dict) -> list[list[str]]:
  return [["Field (name read by screen readers)", _shown(f.get("accessible_name"), "(no name)")],
          ["Field type", _shown(f.get("type") or f.get("role") or f.get("tag"), "(not recorded)")]]


def _empty_required(f: dict) -> bool:
  return bool(f.get("required")) and not f.get("has_value") and bool(f.get("invalid"))


def _facts(ctype: str, ev: dict, meta: dict, ax: dict | None = None) -> list[list[str]]:
  """Neutral facts from the recording. Rules (from the pilot review, 2026-11-27): each fact says whether it is what is
  visible or what screen readers read, uses the words of the question, reads the field the recording actually holds,
  and an empty value says what it means. Names "read by screen readers" are those Chromium's accessibility engine
  computes on the recorded page (eval/d5_ax_names.py), where available."""
  p, s = ev.get("primary") or {}, ev.get("supporting") or {}
  ax = ax if ax and ax.get("found") else None

  def name(el: dict) -> str:
    return ax["name"] if ax is not None else (el.get("accessible_name") or "")
  if ctype == "link-text-mismatch":
    l = p.get("link") or {}
    return [["Link text on the page", _shown(_no_icons(l.get("text")), "(no text)")],
            ["Link text read by screen readers", _shown(name(l), "(no text)")],
            ["Link address (href)", _shown(l.get("href"), "(no address)")]]
  if ctype == "button-label-mismatch":
    b = p.get("button") or {}
    return [["Button text on the page", _shown(_no_icons(b.get("text")), "(no text)")],
            ["Button label read by screen readers", _shown(name(b), "(no label)")]]
  if ctype == "widget-label-purpose-mismatch":
    w = p.get("widget") or {}
    return [["Kind of control", _kind(w)], ["Text on the page", _shown(_no_icons(w.get("text")), "(no text)")],
            ["Control label read by screen readers", _shown(name(w), "(no label)")]]
  if ctype == "image-alt-not-descriptive":
    i = p.get("image") or {}
    tag = str(i.get("tag") or "").lower()
    kind = "image (img element)" if tag == "img" else ("SVG graphic marked as an image" if tag == "svg" else f"icon ({tag} element marked as an image)")
    alt_name = name(i)
    if i.get("aria_labelledby"):
      source = "aria-labelledby (text of another element)"
    elif i.get("aria_label"):
      source = "aria-label attribute" + (" (the element has no alt attribute)" if i.get("alt") is None else "")
    elif i.get("alt") not in (None, ""):
      source = "alt attribute"
    elif i.get("alt") == "":
      source = "empty alt attribute (alt=\"\"): the image is marked as decorative"
    elif i.get("title"):
      source = "title attribute"
    else:
      source = "(no text alternative)"
    rows = [["Kind of image", kind], ["Text alternative read by screen readers", _shown(alt_name, "(no text alternative)")],
            ["Where the text alternative comes from", source]]
    if i.get("hidden_reason") or i.get("exposed_to_assistive_technology") is False:
      rows.append(["Hidden from screen readers", f"yes ({_shown(i.get('hidden_reason'), 'reason not recorded')})"])
    src = urlparse(str(i.get("src") or "")).path.rsplit("/", 1)[-1]
    if src:
      rows.append(["Image file", src[:80]])
    return rows
  if ctype == "heading-not-descriptive":
    h = p.get("heading") or {}
    return [["Heading text", _shown(h.get("text"), "(empty heading)")],
            ["Heading level", f"h{h.get('level')}" if h.get("level") else "(not recorded)"]]
  if ctype == "landmark-purpose-mismatch":
    l = p.get("landmark") or {}
    tag = str(l.get("tag") or "").lower()
    kind = AX_REGIONS.get(ax["role"]) if ax is not None else None
    rows = [["Region type (announced by screen readers)", kind or LANDMARKS.get(tag) or LANDMARKS.get(str(l.get("role") or "").lower()) or _shown(l.get("role") or tag, "(not recorded)")],
            ["Region name read by screen readers", _shown(name(l), "(no name)")]]
    if not name(l):
      rows.append(["Why it has no name", f"the page code says to take its name from another element (aria-labelledby=\u201c{l.get('aria_labelledby')}\u201d), but that element has no text"
                   if l.get("aria_labelledby") else "the page code gives it none (no aria-label, aria-labelledby or title)"])
    inside = _no_icons(l.get("text_sample") or "")
    rows.append(["Text inside the region (beginning)", inside[:160] + ("\u2026" if len(inside) > 160 else "") if inside else "(none: the region is empty)"])
    return rows
  if ctype == "page-title-not-descriptive":
    pg = p.get("page") or {}
    heads = [h.get("text") for h in (s.get("headings") or []) if isinstance(h, dict) and h.get("text")][:3]
    return [["Page title (browser tab)", _shown(meta.get("s2_title") or meta.get("s1_title") or pg.get("title"), "(no title)")],
            ["Headings on the screen (marked up for screen readers)", _shown(", ".join(heads), "(no headings marked up)")]]
  if ctype == "form-label-mismatch":
    f = p.get("form_control") or {}
    rows = [["Field type", _shown(f.get("type") or (ROLE_NAMES.get(str(f.get("role") or "").lower()) if f.get("role") else f.get("tag")), "(not recorded)")],
            ["Label text on the page", _shown(f.get("label") or f.get("wrapping_label"), "(no label text)")],
            ["Field label read by screen readers", _shown(name(f), "(no label)")]]
    if f.get("placeholder"):
      rows.append(["Placeholder (grey hint text in the field)", _shown(f.get("placeholder"), "")])
    return rows
  if ctype == "aria-state-mismatch":
    a = p.get("aria_state") or {}
    attrs = a.get("state_attributes") or ((s.get("aria_state_context_v1") or {}).get("declared_state")) or {}
    said = [STATE_NAMES.get(k, (k, {}))[1].get(str(v), f"{k} = {v}") for k, v in attrs.items()]
    code = [f"{k.replace('_', '-')}=\u201c{v}\u201d" for k, v in attrs.items()]
    return [["Kind of control", _kind(a)], ["Text on the page", _shown(_no_icons(a.get("text")), "(no text)")],
            ["Name read by screen readers", _shown(name(a), "(no name)")],
            ["State that screen readers announce", _shown(" and ".join(said), "(no state recorded)")],
            ["In the page code", _shown(", ".join(code), "(no state attribute)")]]
  if ctype == "lang-mismatch":
    pg = p.get("page") or {}
    sample = " ".join(str(s.get("body_text_sample") or pg.get("body_text_sample") or "").split())[:220]
    return [["Declared page language", _shown(pg.get("html_lang") or pg.get("document_lang"), "(no language declared)")],
            ["Start of the page text", _shown(sample, "(no text recorded)")]]
  if ctype == "error-message-mismatch":
    f = p.get("form_control") or p.get("first_invalid_or_first_field") or {}
    live = [t for t in (p.get("page_error_texts") or []) if isinstance(t, dict) and t.get("text")]
    outlined = ((ev.get("_element_refs") or [{}])[0]).get("xpath")
    if not p.get("form_control") and live and outlined and outlined == live[0].get("xpath"):
      # the outlined element is a live region, not a field
      rows = [["What the tool checked", "an announcement area (a \u201clive region\u201d): when its text changes, screen readers read the new "
               "text out loud. Apps often put error messages in such areas."],
              ["Text in the announcement area", " ".join(live[0]["text"].split())[:160]]]
      invalid = f if f and str(f.get("aria_invalid")) == "true" else None
      rows.append(["Fields marked as having an error, for screen readers (aria-invalid)",
                   _shown(invalid and f"the field \u201c{invalid.get('accessible_name')}\u201d", "none on this screen")])
      if f and not invalid and _empty_required(f):
        rows.append(["Required field left empty", f"the field \u201c{f.get('accessible_name')}\u201d (screen readers are not told it is invalid)"])
      return rows
    rows = [["Field (name read by screen readers)", _shown(name(f) if f else "", "(no name)")],
            ["Field type", _shown(f.get("type") or f.get("role") or f.get("tag"), "(not recorded)")]] if f else \
           [["Field", "(no single field: the question is about the whole screen)"]]
    if f:
      # aria-invalid only: a required field that is still empty fails the browser's own check (`invalid` in the
      # recording), but Chromium does not report it as invalid to screen readers (checked on D5-001, D5-129, D5-265)
      rows.append(["Field marked as having an error, for screen readers (aria-invalid)", "yes" if str(f.get("aria_invalid")) == "true" else "no"])
      if str(f.get("aria_invalid")) != "true" and _empty_required(f):
        rows.append(["Required field left empty", "yes (screen readers are not told it is invalid)"])
    em = p.get("error_message") or {}
    if f or em:
      method = {"aria-describedby": "connected with aria-describedby", "aria-errormessage": "connected with aria-errormessage"}.get(em.get("method"), em.get("method") or "")
      rows.append(["Error message connected to the field (screen readers read it with the field)",
                   f"\u201c{em['text']}\u201d ({method})" if em.get("text") else "(no error message connected)"])
    if live:
      rows.append(["Text in announcement areas (screen readers read it out loud when it changes)", " | ".join(" ".join(t["text"].split())[:140] for t in live[:2])])
    return rows
  if ctype == "autocomplete-purpose-mismatch":
    f = p.get("form_control") or {}
    return [["Field label", _shown(f.get("label") or f.get("accessible_name"), "(no label)")],
            ["Autocomplete value", _shown(f.get("autocomplete"), "(no autocomplete value)")], ["Field type", _shown(f.get("type"), "(not recorded)")]]
  return []


def _control_action(ctype: str, ev: dict, noun: str) -> str:
  p = ev.get("primary") or {}
  el = p.get("link") or p.get("button") or p.get("widget") or {}
  text = " ".join(str(el.get("text") or el.get("accessible_name") or "").split())[:60]
  return f"clicks \u201c{text}\u201d" if text else f"clicks the outlined {noun}"


MARK = (232, 89, 12)  # the orange of the outlines drawn at capture


def _draw_mark(path: Path, mark: dict) -> None:
  """A dashed orange box with a label: where the judged element is when it cannot be outlined."""
  from PIL import Image, ImageDraw, ImageFont
  im = Image.open(path).convert("RGB")
  d = ImageDraw.Draw(im)
  x, y, w, h = mark["box"]
  dash, gap, width = 12, 7, 4
  for x0, y0, x1, y1 in ((x, y, x + w, y), (x, y + h, x + w, y + h), (x, y, x, y + h), (x + w, y, x + w, y + h)):
    length = max(abs(x1 - x0), abs(y1 - y0))
    for t in range(0, int(length), dash + gap):
      e = min(t + dash, length)
      if y0 == y1:
        d.line((x0 + t, y0, x0 + e, y1), fill=MARK, width=width)
      else:
        d.line((x0, y0 + t, x1, y0 + e), fill=MARK, width=width)
  try:
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 16)
  except OSError:
    font = ImageFont.load_default()
  left, top, right, bottom = d.multiline_textbbox((0, 0), mark["label"], font=font, spacing=3)
  tw, th = right - left + 16, bottom - top + 10
  where = mark.get("label_at", "above")
  lx, ly = {"above": (x, y - th - 4), "below": (x, y + h + 4), "right": (x + w + 8, y + h / 2 - th / 2),
            "inside": (x + 6, y + 6)}[where]
  lx = max(2, min(lx, im.width - tw - 2))
  ly = max(2, min(ly, im.height - th - 2))
  d.rectangle((lx, ly, lx + tw, ly + th), fill=MARK)
  d.multiline_text((lx + 8 - left, ly + 5 - top), mark["label"], font=font, fill="white", spacing=3)
  im.save(path, quality=88)


def build(endpoint: str) -> None:
  key = sorted(_rows(SRC / "key_do_not_share.csv"), key=lambda r: int(r["order"]))
  codes = _reviewer_codes()
  ax_file = ROOT / "results" / "d5" / "ax_names.json"  # eval/d5_ax_names.py
  ax_names = json.loads(ax_file.read_text(encoding="utf-8")) if ax_file.exists() else {}
  if PUBLIC.exists():
    shutil.rmtree(PUBLIC)
  (PUBLIC / "items").mkdir(parents=True)
  items, flagged = [], []
  for r in key:
    item_id, ctype = r["item_id"], r["type"]
    cap = CAPTURED / item_id
    meta = json.loads((cap / "meta.json").read_text(encoding="utf-8")) if (cap / "meta.json").exists() else {}
    full = json.loads((SRC / "items" / item_id / "evidence.json").read_text(encoding="utf-8"))
    ev, refs = full.get("evidence") or {}, full.get("element_refs") or []
    question, rule, noun = QUESTIONS[ctype]
    dest = PUBLIC / "items" / item_id
    dest.mkdir()
    files = [f.name for f in cap.glob("*") if f.suffix in (".jpg", ".mp4")] if cap.exists() else []
    for name in files:
      shutil.copy(cap / name, dest / name)
    kind = meta.get("kind", "still")
    item = {"id": item_id, "n": int(r["order"]), "shared": r["shared"] == "1", "type": ctype, "kind": kind, "noun": noun,
            "question": question, "rule": rule, "facts": _facts(ctype, {**ev, "_element_refs": refs}, meta, ax_names.get(item_id)),
            "s1": {"file": "s1.jpg", "url": meta.get("s1_url", ""), "title": meta.get("s1_title", "")} if "s1.jpg" in files else None,
            "s2": {"file": "s2.jpg", "url": meta.get("s2_url", ""), "title": meta.get("s2_title", "")} if "s2.jpg" in files else None,
            "clip": "clip.mp4" if "clip.mp4" in files else None,
            "action": _label(meta.get("action_label") or (_control_action(ctype, ev, noun) if kind == "control" else "")),
            "external": meta.get("external"),
            "recorded": meta.get("fallback") == "recorded",
            "steps": [{"file": s["file"] if s.get("file") in files else "", "label": _label(s["label"])} for s in meta.get("steps", [])]}
    # whether the element can be seen and is outlined on the judged screen; if not, a fact says why
    judged = (refs[0] if refs else {}).get("element_id")
    rbox = next((b.get("bounding_box") for b in ev.get("bounding_boxes") or [] if b.get("element_id") == judged), None)
    jbox = meta.get("s1_box")
    no_size = bool(rbox) and (rbox["width"] <= 2 or rbox["height"] <= 2)
    if meta.get("fallback"):
      outlined = meta.get("outline") == "drawn"
    else:
      outlined = bool(jbox) and jbox["width"] > 2 and jbox["height"] > 2
    if ctype in ("page-title-not-descriptive", "lang-mismatch"):
      outlined = None  # page-level questions have no element to outline
    if item_id in OVERRIDES and OVERRIDES[item_id].get("fact"):
      item["facts"].append(OVERRIDES[item_id]["fact"])
    elif no_size:
      empty = ctype == "landmark-purpose-mismatch" and not ((ev.get("primary") or {}).get("landmark") or {}).get("text_sample")
      item["facts"].append(["Visible on the screen", ("no: the region is empty, so it takes up no space on the page." if empty else
                            "no: it is hidden on the screen (it takes up no space), so only screen readers find it.")
                            + (" The dashed box shows where it is." if (OVERRIDES.get(item_id) or {}).get("mark") else "")])
    elif meta.get("outline") == "outside":
      item["facts"].append(["Visible on the screen", "no: it is outside the part of the page shown here (for example further down in an open list)"])
    item["outlined"] = outlined
    item["hint"] = HINTS[ctype]
    if ctype == "aria-state-mismatch":  # the question names the control and the state (pilot review: "state" alone was unclear)
      said, control = dict(item["facts"]).get("State that screen readers announce", ""), dict(item["facts"]).get("Kind of control", "control")
      if said and not said.startswith("("):
        item["question"] = f"Screen readers announce this {control} as \u201c{said}\u201d. Does the screen show the same?"
    item["facts"] = [[k, v, 1] if _needs_translation(v) else [k, v] for k, v in item["facts"]]  # 1: a translate link
    mark = (OVERRIDES.get(item_id) or {}).get("mark")
    if mark and "s1.jpg" in files:  # where an element that cannot be outlined is (dashed box with a label)
      _draw_mark(dest / "s1.jpg", mark)
      item["mark"] = True
    if ctype == "lang-mismatch":
      page = (ev.get("primary") or {}).get("page") or {}
      item["lang"] = page.get("html_lang") or page.get("document_lang") or ""
    if meta.get("problems") or not item["s1"]:
      flagged.append({"item_id": item_id, "problems": meta.get("problems") or ["not captured"]})
    items.append(item)
  (PUBLIC / "items.json").write_text(json.dumps({"items": items}, ensure_ascii=False) + "\n", encoding="utf-8")
  for name in ("index.html", "review.html", "style.css"):
    shutil.copy(TEMPLATES / name, PUBLIC / name)
  (SITE / "netlify" / "functions").mkdir(parents=True, exist_ok=True)
  save = (TEMPLATES / "functions" / "save.mjs").read_text(encoding="utf-8").replace("__REVIEWERS__", json.dumps(codes))
  (SITE / "netlify" / "functions" / "save.mjs").write_text(save, encoding="utf-8")
  # the tool's answers live only in the reveal function (server side), never in the public files
  tool = {k: {"decision": v["decision"], "sentence": v["sentence"]}
          for k, v in json.loads((SRC / "explanations.json").read_text(encoding="utf-8")).items()}
  reveal = (TEMPLATES / "functions" / "reveal.mjs").read_text(encoding="utf-8")
  reveal = reveal.replace("__REVIEWERS__", json.dumps(codes)).replace("__TOOL__", json.dumps(tool, ensure_ascii=False))
  (SITE / "netlify" / "functions" / "reveal.mjs").write_text(reveal, encoding="utf-8")
  shutil.copy(TEMPLATES / "netlify.toml", SITE / "netlify.toml")
  (SITE / "package.json").write_text(json.dumps({"name": "d5-expert-review", "private": True, "type": "module",
                                                 "dependencies": {"@netlify/blobs": "8.1.0"}}, indent=1) + "\n")
  (ROOT / "results" / "d5" / "site-flagged.json").write_text(json.dumps(flagged, indent=2) + "\n", encoding="utf-8")
  size = sum(f.stat().st_size for f in PUBLIC.rglob("*") if f.is_file()) / 1e6
  print(f"site: {len(items)} items, {len(flagged)} flagged, {size:.0f} MB -> {SITE}")


ROLES = (("main", "main"), ("shared1", "shared"), ("shared2", "shared"), ("shared3", "shared"), ("preview", "preview"))


def _reviewer_codes() -> list[str]:
  """Personal codes, made once: main (all items), shared1-3 (the 30 shared items), preview (the PI; excluded later).

  Codes that already exist are kept; a role no longer in ROLES (the earlier single `second` reviewer, never used) is
  dropped, and missing roles get a new code."""
  import os
  import secrets
  import string
  links = PRIVATE / "links.csv"
  PRIVATE.mkdir(parents=True, exist_ok=True)
  os.chmod(PRIVATE, 0o700)
  old = {r["role"]: r["code"] for r in _rows(links)} if links.exists() else {}
  alphabet = string.ascii_lowercase + string.digits
  rows = [{"role": role, "code": old.get(role) or f"{prefix}-" + "".join(secrets.choice(alphabet) for _ in range(10))}
          for role, prefix in ROLES]
  if [(r["role"], r["code"]) for r in rows] != list(old.items()):
    with links.open("w", newline="", encoding="utf-8") as stream:
      writer = csv.DictWriter(stream, fieldnames=["role", "code"])
      writer.writeheader()
      writer.writerows(rows)
    os.chmod(links, 0o600)
  return [r["code"] for r in rows]


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("step", choices=("build",))
  parser.add_argument("--endpoint", default="")
  args = parser.parse_args(argv)
  build(args.endpoint)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
