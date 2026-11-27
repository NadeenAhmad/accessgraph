"""For items whose replay could not reach the recorded screen, use the screenshot AccessGraph recorded during
exploration instead: a 1280 x 800 view around the element (headings and regions near the top, page-level checks from
the top of the page), with the element outlined. Free.

  python -m eval.d5_review_fallback [ITEM ...]   # default: every captured item that still has a problem

The item keeps its path as text (its screenshots, s2 and the clip are dropped: they came from a replay that went off course), and
meta.json gets "fallback": "recorded" so the site can say that the screen is the recorded one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from eval.d5_review import PAGE_LEVEL, PLACE_TOP

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "d5" / "export165" / "items"
CAPTURED = ROOT / "results" / "d5" / "review" / "items"
RUNS = ROOT / "runs" / "w4a-d5"
_OVERRIDES_FILE = ROOT / "results" / "d5" / "review" / "overrides.json"  # item-by-item review decisions (optional)
OVERRIDES = json.loads(_OVERRIDES_FILE.read_text(encoding="utf-8")) if _OVERRIDES_FILE.exists() else {}
MARK = (232, 89, 12)


def fallback(item_id: str) -> str:
  out = CAPTURED / item_id
  meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
  ev = json.loads((SRC / item_id / "evidence.json").read_text(encoding="utf-8"))
  state = ev["state_id"]
  shot = RUNS / meta["app"] / "explore" / "states" / state / "screenshot.png"
  coords = json.loads((RUNS / meta["app"] / "explore" / "states" / state / "metadata.json").read_text())["coordinate_space"]
  offset = coords["screenshot_capture"]["scroll_offset"]["y"]
  im = Image.open(shot).convert("RGB")
  # the outline marks the judged element only: the recording also measured other elements (e.g. the first field of a
  # form when the judged element is a live region), whose box must not be outlined in its place
  judged = ((ev.get("element_refs") or [{}])[0]).get("element_id")
  boxes = (ev.get("evidence") or {}).get("bounding_boxes") or []
  box = next((b.get("bounding_box") for b in boxes if b.get("element_id") == judged), None)
  override = OVERRIDES.get(item_id, {})
  if box and meta["type"] in PLACE_TOP:  # headings and regions near the top, so their content shows below them
    top = int(max(0, min(im.height - 800, box["y"] + offset - 90)))
  elif box and meta["type"] not in PAGE_LEVEL:
    y = box["y"] + offset
    top = int(max(0, min(im.height - 800, y + box["height"] / 2 - 400)))
  else:
    top = 0
  view = im.crop((0, top, 1280, min(im.height, top + 800)))
  outline = "none"
  if box:
    x0, y0 = box["x"] - 5, box["y"] + offset - top - 5
    x1, y1 = box["x"] + box["width"] + 5, box["y"] + offset - top + box["height"] + 5
    if box["width"] <= 2 or box["height"] <= 2:
      outline = "no size"
    elif y1 < 0 or y0 > view.height or x1 < 0 or x0 > view.width or box["y"] + offset >= im.height:
      outline = "outside"
    elif override.get("outline") is False:
      outline = "override"
    else:
      d = ImageDraw.Draw(view)
      for k in range(4):
        d.rectangle([x0 - k, y0 - k, x1 + k, y1 + k], outline=MARK)
      outline = "drawn"
  elif boxes:
    outline = "other element measured"
  view.save(out / "s1.jpg", quality=86)
  for name in ("s2.jpg", "clip.mp4"):
    (out / name).unlink(missing_ok=True)
  # the path screenshots come from the replay that did not reproduce the recording: keep the steps as text only
  for step in meta.get("steps", []):
    (out / step["file"]).unlink(missing_ok=True) if step.get("file") else None
    step["file"] = ""
  meta.update({"fallback": "recorded", "kind": "still", "outline": outline, "s1_url": (ev.get("state_context") or {}).get("url", ""),
               "s1_title": (ev.get("state_context") or {}).get("title", ""), "replay_problems": meta["problems"], "problems": []})
  meta.pop("s2_url", None), meta.pop("s2_title", None), meta.pop("clip", None)
  (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
  return f"{item_id}: recorded screen used (outline: {outline})"


def main(argv: list[str]) -> int:
  ids = argv or [m.parent.name for m in CAPTURED.glob("*/meta.json") if json.loads(m.read_text())["problems"]]
  for item_id in sorted(ids):
    print(fallback(item_id))
  return 0


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
