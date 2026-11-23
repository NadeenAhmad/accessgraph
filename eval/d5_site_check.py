"""Checks the built D5 review site before it is uploaded (free). Exit code 1 if anything is wrong.

  python -m eval.d5_site_check

- every one of the 165 items is in the site, in the shuffled order, with its question, rule, facts and screen 1;
- the element is outlined where the check has one (page language and page title have none);
- actions have a screen 2 (or the other website's address) and a clip, unless the item uses the recorded screen;
- no capture problem is left; replayed elements show the recorded content (checked during capture);
- the second reviewer's list has the 50 marked items (30 the tool called violations, 20 others);
- the tool's answers are nowhere in the public files; they are only in the reveal function, one for each item.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "d5" / "export165"
CAPTURED = ROOT / "results" / "d5" / "review" / "items"
from eval.paths import D5_REVIEW_SITE as SITE  # noqa: E402
PAGE_LEVEL = {"lang-mismatch", "page-title-not-descriptive"}


def main() -> int:
  problems = []
  key = {r["item_id"]: r for r in csv.DictReader((SRC / "key_do_not_share.csv").open(encoding="utf-8"))}
  items = json.loads((SITE / "public" / "items.json").read_text(encoding="utf-8"))["items"]
  by_id = {it["id"]: it for it in items}
  if set(by_id) != set(key):
    problems.append(f"site has {len(by_id)} items, key has {len(key)}; missing {sorted(set(key) - set(by_id))[:5]}")
  for item_id, r in key.items():
    it = by_id.get(item_id)
    if not it:
      continue
    meta = json.loads((CAPTURED / item_id / "meta.json").read_text(encoding="utf-8"))
    folder = SITE / "public" / "items" / item_id
    where = f"{item_id} ({r['type']}, {it['kind']})"
    if it["n"] != int(r["order"]):
      problems.append(f"{where}: order {it['n']} != {r['order']}")
    if not it["question"] or not it["rule"] or not it["facts"]:
      problems.append(f"{where}: question, rule or facts missing")
    if any(v == "(none)" for k, v in it["facts"] if k in ("Link text", "Visible text", "Heading text")) and r["type"] not in ("button-label-mismatch", "widget-label-purpose-mismatch"):
      problems.append(f"{where}: main fact empty")
    if not it["s1"] or not (folder / "s1.jpg").exists():
      problems.append(f"{where}: no screen 1")
    if meta.get("problems"):
      problems.append(f"{where}: capture problems {meta['problems']}")
    outlined = meta.get("s2_box") if it["kind"] == "arrival" else meta.get("s1_box")
    if r["type"] not in PAGE_LEVEL and not meta.get("fallback") and not outlined and not (it["kind"] == "arrival" and meta.get("s1_box")):
      problems.append(f"{where}: element not outlined")
    if it["kind"] in ("control", "arrival") and not meta.get("fallback"):
      if not it["external"] and not (it["s2"] and (folder / "s2.jpg").exists()):
        problems.append(f"{where}: no screen 2")
      if not it["external"] and not it["clip"]:
        problems.append(f"{where}: no clip")
  second = [it for it in items if it["double"]]
  second_v = sum(1 for it in second if key[it["id"]]["ag_decision"] == "violation")
  if len(second) != 50 or second_v != 30:
    problems.append(f"second reviewer list: {len(second)} items, {second_v} violations (expected 50 / 30)")
  data_text = (SITE / "public" / "items.json").read_text(encoding="utf-8")  # the item data must carry no verdicts
  for word in ("ag_decision", '"decision"', '"sentence"', "explanation", "violation\""):
    if word in data_text:
      problems.append(f"items.json contains {word!r}")
  for page in ("index.html", "review.html"):
    if re.search(r"D5-\d{3}", (SITE / "public" / page).read_text(encoding="utf-8")):
      problems.append(f"{page} contains item data")
  reveal = (SITE / "netlify" / "functions" / "reveal.mjs").read_text(encoding="utf-8")
  tool = json.loads(re.search(r"const TOOL = (\{.*?\});\n", reveal, re.S).group(1))
  if set(tool) != set(key) or any(tool[k]["decision"] != key[k]["ag_decision"] for k in key):
    problems.append("reveal function: items or decisions do not match the key")
  stats = {k: sum(1 for it in items if it["kind"] == k) for k in ("control", "arrival", "still")}
  recorded = sum(1 for i in key if json.loads((CAPTURED / i / "meta.json").read_text()).get("fallback"))
  clips = sum(1 for it in items if it["clip"])
  print(f"{len(items)} items: {stats}; {clips} with a clip; {recorded} on the recorded screen; second list {len(second)} ({second_v} violations)")
  for p in problems:
    print("PROBLEM:", p)
  print("OK" if not problems else f"{len(problems)} problems")
  return 1 if problems else 0


if __name__ == "__main__":
  raise SystemExit(main())
