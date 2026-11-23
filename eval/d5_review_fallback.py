"""For items whose replay could not reach the recorded screen, use the screenshot AccessGraph recorded during
exploration instead: a 1280 x 800 view around the element, with the element outlined. Free.

  python -m eval.d5_review_fallback [ITEM ...]   # default: every captured item that still has a problem

The item keeps its path screenshots; s2 and the clip are dropped (they came from a replay that went off course), and
meta.json gets "fallback": "recorded" so the site can say that the screen is the recorded one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "d5" / "export165" / "items"
CAPTURED = ROOT / "results" / "d5" / "review" / "items"
RUNS = ROOT / "runs" / "w4a-d5"
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
  boxes = (ev.get("evidence") or {}).get("bounding_boxes") or []
  box = (boxes[0] or {}).get("bounding_box") if boxes else None
  if box:
    y = box["y"] + offset
    top = int(max(0, min(im.height - 800, y + box["height"] / 2 - 400)))
  else:
    top = 0
  view = im.crop((0, top, 1280, min(im.height, top + 800)))
  if box:
    d = ImageDraw.Draw(view)
    x0, y0 = box["x"] - 5, box["y"] + offset - top - 5
    x1, y1 = box["x"] + box["width"] + 5, box["y"] + offset - top + box["height"] + 5
    for k in range(4):
      d.rectangle([x0 - k, y0 - k, x1 + k, y1 + k], outline=MARK)
  view.save(out / "s1.jpg", quality=86)
  for name in ("s2.jpg", "clip.mp4"):
    (out / name).unlink(missing_ok=True)
  meta.update({"fallback": "recorded", "kind": "still", "s1_url": (ev.get("state_context") or {}).get("url", ""),
               "s1_title": (ev.get("state_context") or {}).get("title", ""), "replay_problems": meta["problems"], "problems": []})
  meta.pop("s2_url", None), meta.pop("s2_title", None), meta.pop("clip", None)
  (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
  return f"{item_id}: recorded screen used ({'element outlined' if box else 'no element box'})"


def main(argv: list[str]) -> int:
  ids = argv or [m.parent.name for m in CAPTURED.glob("*/meta.json") if json.loads(m.read_text())["problems"]]
  for item_id in sorted(ids):
    print(fallback(item_id))
  return 0


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
