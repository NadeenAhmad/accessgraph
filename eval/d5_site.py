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
import json
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
  "link-text-mismatch": ("Does the link text describe where the link goes?", "2.4.4 Link Purpose (In Context), level A: the purpose of each link can be determined from the link text, alone or together with its surrounding text.", "link"),
  "button-label-mismatch": ("Does the button's label describe what the button does?", "2.4.6 Headings and Labels, level AA: labels describe the topic or purpose of their control.", "button"),
  "widget-label-purpose-mismatch": ("Does the control's label describe what the control does?", "2.4.6 Headings and Labels, level AA, and 4.1.2 Name, Role, Value, level A: the control's name describes its purpose.", "control"),
  "image-alt-not-descriptive": ("Does the image's text alternative describe the image or its purpose?", "1.1.1 Non-text Content, level A: an image that carries information has a text alternative that serves the same purpose; a purely decorative image may have none.", "image"),
  "heading-not-descriptive": ("Does the heading describe the content of its section?", "2.4.6 Headings and Labels, level AA: headings describe the topic or purpose of their section.", "heading"),
  "landmark-purpose-mismatch": ("Do the region's type and name describe what the region contains?", "1.3.6 Identify Purpose, level AAA (landmark regions): the purpose of each page region can be determined.", "region"),
  "page-title-not-descriptive": ("Does the page title (the browser tab text) describe this screen?", "2.4.2 Page Titled, level A: the page has a title that describes its topic or purpose.", "page"),
  "form-label-mismatch": ("Does the field's label describe what the field is for?", "2.4.6 Headings and Labels, level AA: labels describe the purpose of their field.", "field"),
  "aria-state-mismatch": ("Does the state announced to screen readers match what the control shows?", "4.1.2 Name, Role, Value, level A: the state of a control (open, selected, checked, pressed) is available to assistive technologies and matches what is shown.", "control"),
  "lang-mismatch": ("Is the page's language set correctly?", "3.1.1 Language of Page, level A: the main language of the page is declared correctly.", "page"),
  "error-message-mismatch": ("Is the input error identified and described to the user in text?", "3.3.1 Error Identification, level A: when an input error is detected, the field is identified and the error is described in text.", "field"),
  "autocomplete-purpose-mismatch": ("Does the field's autocomplete value match the information the field asks for?", "1.3.5 Identify Input Purpose, level AA: fields that ask for information about the user declare that purpose correctly.", "field"),
}
LANDMARKS = {"nav": "navigation", "main": "main content", "header": "banner (header)", "footer": "content info (footer)",
             "aside": "complementary", "section": "region", "form": "form", "search": "search"}


def _rows(path: Path) -> list[dict]:
  with path.open(encoding="utf-8", newline="") as stream:
    return list(csv.DictReader(stream))


def _v(value) -> str:
  text = " ".join(str(value).split()) if value not in (None, "") else ""
  return text if text else "(none)"


def _facts(ctype: str, ev: dict, meta: dict) -> list[list[str]]:
  p, s = ev.get("primary") or {}, ev.get("supporting") or {}
  if ctype == "link-text-mismatch":
    l = p.get("link") or {}
    return [["Link text", _v(l.get("text"))], ["Name read by screen readers", _v(l.get("accessible_name"))],
            ["Link address (href)", _v(l.get("href"))]]
  if ctype == "button-label-mismatch":
    b = p.get("button") or {}
    return [["Visible text", _v(b.get("text"))], ["Name read by screen readers", _v(b.get("accessible_name"))]]
  if ctype == "widget-label-purpose-mismatch":
    w = p.get("widget") or {}
    return [["Kind of control", _v(w.get("role") or w.get("tag"))], ["Visible text", _v(w.get("text"))],
            ["Name read by screen readers", _v(w.get("accessible_name"))]]
  if ctype == "image-alt-not-descriptive":
    i = p.get("image") or {}
    src = urlparse(str(i.get("src") or "")).path.rsplit("/", 1)[-1]
    rows = [["Text alternative (alt)", _v(i.get("alt"))], ["Name read by screen readers", _v(i.get("accessible_name"))]]
    if i.get("hidden_reason") or i.get("exposed_to_assistive_technology") is False:
      rows.append(["Hidden from screen readers", f"yes ({_v(i.get('hidden_reason'))})"])
    if src:
      rows.append(["Image file", src[:80]])
    return rows
  if ctype == "heading-not-descriptive":
    h = p.get("heading") or {}
    return [["Heading text", _v(h.get("text"))], ["Heading level", f"h{h.get('level')}" if h.get("level") else "(none)"]]
  if ctype == "landmark-purpose-mismatch":
    l = p.get("landmark") or {}
    tag = str(l.get("tag") or "").lower()
    return [["Region type", LANDMARKS.get(tag, _v(l.get("role") or tag))], ["Region name read by screen readers", _v(l.get("accessible_name"))]]
  if ctype == "page-title-not-descriptive":
    pg = p.get("page") or {}
    heads = [h.get("text") for h in (s.get("headings") or []) if isinstance(h, dict) and h.get("text")][:3]
    return [["Page title (browser tab)", _v(meta.get("s2_title") or pg.get("title"))], ["Headings on the screen", _v(", ".join(heads))]]
  if ctype == "form-label-mismatch":
    f = p.get("form_control") or {}
    return [["Field type", _v(f.get("type") or f.get("tag"))], ["Visible label", _v(f.get("label") or f.get("wrapping_label"))],
            ["Name read by screen readers", _v(f.get("accessible_name"))], ["Placeholder", _v(f.get("placeholder"))]]
  if ctype == "aria-state-mismatch":
    a = p.get("aria_state") or {}
    ctx = s.get("aria_state_context_v1") or {}
    states = ctx.get("aria_states") or ctx.get("states") or {}
    state_text = ", ".join(f"{k}={v}" for k, v in states.items()) if isinstance(states, dict) and states else _v(
      next((f"{k}={a[k]}" for k in ("aria_expanded", "aria_selected", "aria_checked", "aria_pressed") if a.get(k)), ""))
    return [["Kind of control", _v(a.get("role") or a.get("tag"))], ["Name read by screen readers", _v(a.get("accessible_name"))],
            ["State announced to screen readers", state_text]]
  if ctype == "lang-mismatch":
    pg = p.get("page") or {}
    sample = " ".join(str(s.get("body_text_sample") or pg.get("body_text_sample") or "").split())[:220]
    return [["Declared page language", _v(pg.get("html_lang") or pg.get("document_lang"))], ["Start of the page text", _v(sample)]]
  if ctype == "error-message-mismatch":
    f = p.get("form_control") or {}
    texts = [t.get("text") for t in (p.get("page_error_texts") or []) if isinstance(t, dict) and t.get("text")][:3]
    return [["Field (name read by screen readers)", _v(f.get("accessible_name"))], ["Field type", _v(f.get("type"))],
            ["Field marked invalid", "yes" if f.get("invalid") else "no"], ["Error texts on the screen", _v(" | ".join(texts))]]
  if ctype == "autocomplete-purpose-mismatch":
    f = p.get("form_control") or {}
    return [["Field label", _v(f.get("label") or f.get("accessible_name"))], ["Autocomplete value", _v(f.get("autocomplete"))],
            ["Field type", _v(f.get("type"))]]
  return []


def _control_action(ctype: str, ev: dict, noun: str) -> str:
  p = ev.get("primary") or {}
  el = p.get("link") or p.get("button") or p.get("widget") or {}
  text = " ".join(str(el.get("text") or el.get("accessible_name") or "").split())[:60]
  return f"clicks \u201c{text}\u201d" if text else f"clicks the outlined {noun}"


def build(endpoint: str) -> None:
  key = sorted(_rows(SRC / "key_do_not_share.csv"), key=lambda r: int(r["order"]))
  codes = _reviewer_codes()
  if PUBLIC.exists():
    shutil.rmtree(PUBLIC)
  (PUBLIC / "items").mkdir(parents=True)
  items, flagged = [], []
  for r in key:
    item_id, ctype = r["item_id"], r["type"]
    cap = CAPTURED / item_id
    meta = json.loads((cap / "meta.json").read_text(encoding="utf-8")) if (cap / "meta.json").exists() else {}
    ev = json.loads((SRC / "items" / item_id / "evidence.json").read_text(encoding="utf-8")).get("evidence") or {}
    question, rule, noun = QUESTIONS[ctype]
    dest = PUBLIC / "items" / item_id
    dest.mkdir()
    files = [f.name for f in cap.glob("*") if f.suffix in (".jpg", ".mp4")] if cap.exists() else []
    for name in files:
      shutil.copy(cap / name, dest / name)
    kind = meta.get("kind", "still")
    item = {"id": item_id, "n": int(r["order"]), "shared": r["shared"] == "1", "type": ctype, "kind": kind, "noun": noun,
            "question": question, "rule": rule, "facts": _facts(ctype, ev, meta),
            "s1": {"file": "s1.jpg", "url": meta.get("s1_url", ""), "title": meta.get("s1_title", "")} if "s1.jpg" in files else None,
            "s2": {"file": "s2.jpg", "url": meta.get("s2_url", ""), "title": meta.get("s2_title", "")} if "s2.jpg" in files else None,
            "clip": "clip.mp4" if "clip.mp4" in files else None,
            "action": meta.get("action_label") or (_control_action(ctype, ev, noun) if kind == "control" else ""),
            "external": meta.get("external"),
            "recorded": meta.get("fallback") == "recorded",
            "steps": [{"file": s["file"], "label": s["label"]} for s in meta.get("steps", []) if s["file"] in files]}
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
