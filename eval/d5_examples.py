"""Two worked examples shown to the D5 labellers before the review (PI 2026-11-28: "judges should see two examples
before they start, so they understand what to do and that the tool can be right and can be wrong"). Free.

  python -m eval.d5_examples prepare   # copies the two items from results/d5/export into results/d5/examples
  python -m eval.d5_examples capture   # replays them like the study items -> results/d5/review/examples/items

Both come from the judged sample but are NOT among the expert items (results/d5/export165), so no labeller sees the
answer to an item they label. Example 1: AccessGraph is right (a link "Settings" that opens the Settings page).
Example 2: AccessGraph is wrong (a notification switch that screen readers read without any name; Chromium's
accessibility engine computes an empty name on the recorded page; AccessGraph judged it fine from the text around
it). The texts (tool's answer in one sentence, the correct answer and why) are in results/d5/examples/examples.json;
they are shown only on the practice page and nothing answered there is saved. eval/d5_site.py builds the page data.
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "results" / "d5" / "export"
STUDY = ROOT / "results" / "d5" / "export165"
EXAMPLES = ROOT / "results" / "d5" / "examples"
CAPTURED = ROOT / "results" / "d5" / "review" / "examples"
TEXTS = {
  "D5-046": {
    "sentence": "The link says “Settings” and leads to the User settings page, so its text describes where it goes.",
    "correct": "no_violation",
    "why": "The link text “Settings” says where the link goes, and it opens the User settings page. The tool is right.",
  },
  "D5-258": {
    "sentence": "The switch has no label of its own, but the text in its row is about buyer review notifications, and the "
                "tool saw no label that names a different purpose.",
    "correct": "violation",
    "why": "Screen readers read no label for this switch (a checkbox in the page code): the text next to it is not connected to it, so a screen reader "
           "user hears only “checkbox” and cannot tell what it turns on or off. The tool is wrong here: it judged "
           "from the visible text around the switch, which screen readers do not read as the switch's label.",
  },
}


def prepare() -> None:
  study = {r["item_id"] for r in csv.DictReader((STUDY / "key_do_not_share.csv").open(encoding="utf-8"))}
  rows = {r["item_id"]: r for r in csv.DictReader((EXPORT / "key_do_not_share.csv").open(encoding="utf-8"))}
  if EXAMPLES.exists():
    shutil.rmtree(EXAMPLES)
  (EXAMPLES / "items").mkdir(parents=True)
  key = []
  for order, item_id in enumerate(TEXTS, 1):
    assert item_id not in study, f"{item_id} is an expert item: it cannot be an example"
    shutil.copytree(EXPORT / "items" / item_id, EXAMPLES / "items" / item_id)
    key.append({**rows[item_id], "order": order, "double": 0, "shared": 0})
  with (EXAMPLES / "key_do_not_share.csv").open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(key[0]))
    writer.writeheader()
    writer.writerows(key)
  texts = {k: {**v, "tool": rows[k]["ag_decision"], "tool_right": rows[k]["ag_decision"] == v["correct"]} for k, v in TEXTS.items()}
  (EXAMPLES / "examples.json").write_text(json.dumps(texts, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
  print(f"{len(key)} examples prepared in {EXAMPLES}")


def capture() -> None:
  import eval.d5_review as review
  review.SRC, review.OUT = EXAMPLES, CAPTURED  # the same capture as the study items, other folders
  review.capture(None, None)


if __name__ == "__main__":
  {"prepare": prepare, "capture": capture}[sys.argv[1]]()
