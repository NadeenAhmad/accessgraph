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
LANDMARKS = {"nav": "navigation", "main": "main content", "header": "banner (header)", "footer": "content info (footer)",
             "aside": "complementary", "section": "region", "form": "form", "search": "search"}


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


AX_REGIONS = {"banner": "banner (page header)", "navigation": "navigation", "complementary": "complementary (aside)",
              "contentinfo": "content info (page footer)", "form": "form", "region": "region", "main": "main content",
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
    rows = [["Region type", kind or LANDMARKS.get(tag) or LANDMARKS.get(str(l.get("role") or "").lower()) or _shown(l.get("role") or tag, "(not recorded)")],
            ["Region name read by screen readers", _shown(name(l), "(no name: the region has no aria-label, aria-labelledby or title)")]]
    if not name(l) and l.get("aria_labelledby"):
      rows.append(["Name source", f"aria-labelledby points to the element with id \u201c{l.get('aria_labelledby')}\u201d, which gives no text"])
    inside = _no_icons(l.get("text_sample") or "")
    if inside:
      rows.append(["Text inside the region (start)", inside[:160] + ("\u2026" if len(inside) > 160 else "")])
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
    said = [f"{STATE_NAMES.get(k, (k, {}))[1].get(str(v), f'{k} = {v}')} ({k.replace('_', '-')}=\u201c{v}\u201d)" for k, v in attrs.items()]
    return [["Kind of control", _kind(a)], ["Text on the page", _shown(_no_icons(a.get("text")), "(no text)")],
            ["Name read by screen readers", _shown(name(a), "(no name)")],
            ["State announced to screen readers", _shown("; ".join(said), "(no state recorded)")]]
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
      rows = [["Element checked", "a live region: screen readers read its text out automatically when it changes"],
              ["Its text", " ".join(live[0]["text"].split())[:160]]]
      invalid = f if f and (f.get("invalid") or str(f.get("aria_invalid")) == "true") else None
      rows.append(["Fields marked invalid for screen readers (aria-invalid)",
                   _shown(invalid and f"the field \u201c{invalid.get('accessible_name')}\u201d", "(no field on this screen is marked invalid)")])
      return rows
    rows = [["Field (name read by screen readers)", _shown(name(f) if f else "", "(no name)")],
            ["Field type", _shown(f.get("type") or f.get("role") or f.get("tag"), "(not recorded)")]] if f else \
           [["Field", "(no single field: the question is about the whole screen)"]]
    if f:
      rows.append(["Field marked invalid for screen readers (aria-invalid)", "yes" if f.get("invalid") or str(f.get("aria_invalid")) == "true" else "no"])
    em = p.get("error_message") or {}
    if f or em:
      method = {"aria-describedby": "linked with aria-describedby", "aria-errormessage": "linked with aria-errormessage"}.get(em.get("method"), em.get("method") or "")
      rows.append(["Error message linked to the field (read by screen readers)",
                   f"\u201c{em['text']}\u201d ({method})" if em.get("text") else "(no error message linked)"])
    if live:
      rows.append(["Text in live regions (read out automatically by screen readers)", " | ".join(" ".join(t["text"].split())[:140] for t in live[:2])])
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
    jbox = meta.get("s2_box") if kind == "arrival" else meta.get("s1_box")
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
      item["facts"].append(["Visible on the screen", "no: the element takes up no space on the page"])
    elif meta.get("outline") == "outside":
      item["facts"].append(["Visible on the screen", "no: it is outside the part of the page shown here (for example further down in an open list)"])
    item["outlined"] = outlined
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
