from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .hashing import sha256_hex
from .models import ReviewBundle

CANDIDATE_VISUAL_CONTEXT_SCHEMA_VERSION = "1"
IMAGE_ALT_CANDIDATE_TYPE = "image-alt-not-descriptive"
VISUAL_CONTEXT_DIR_NAME = "visual_context"


def prepare_candidate_visual_context(
  bundle: ReviewBundle,
  *,
  output_dir: Path,
  overwrite: bool = True,
) -> ReviewBundle:
  """Write candidate-specific visual artifacts and return an augmented bundle.

  The generated artifacts are confirmation-stage support files. They are derived
  from existing screenshots and candidate bounding boxes; they do not change
  crawl behavior or introduce semantic judgment.
  """

  if bundle.candidate_type != IMAGE_ALT_CANDIDATE_TYPE:
    return bundle

  screenshot_ref = bundle.artifact_refs.get("screenshot")
  if not isinstance(screenshot_ref, str) or not screenshot_ref.strip():
    return bundle

  bounding_box = _candidate_bounding_box(bundle)
  if bounding_box is None:
    return bundle

  try:
    screenshot_path = _resolve_run_relative_path(bundle.run_dir, screenshot_ref)
  except ValueError:
    return bundle
  if not screenshot_path.is_file():
    return bundle

  candidate_dir = output_dir / VISUAL_CONTEXT_DIR_NAME / _safe_path_part(bundle.candidate_id)
  target_crop_path = candidate_dir / "target_crop.png"
  highlighted_state_path = candidate_dir / "highlighted_state.png"
  manifest_path = candidate_dir / "manifest.json"

  if manifest_path.exists() and not overwrite:
    return _augment_bundle_with_visual_context(
      bundle,
      output_dir=output_dir,
      manifest_path=manifest_path,
      manifest=json.loads(manifest_path.read_text(encoding="utf-8")),
    )

  candidate_dir.mkdir(parents=True, exist_ok=True)
  with Image.open(screenshot_path) as raw_image:
    image = raw_image.convert("RGBA")
    crop_box = _padded_crop_box(bounding_box, image.size)
    target_crop = image.crop(crop_box)
    target_crop.save(target_crop_path)

    highlighted = image.copy()
    _draw_highlight(highlighted, bounding_box)
    highlighted.convert("RGB").save(highlighted_state_path)

  manifest = _build_manifest(
    bundle=bundle,
    output_dir=output_dir,
    screenshot_path=screenshot_path,
    screenshot_ref=screenshot_ref,
    target_crop_path=target_crop_path,
    highlighted_state_path=highlighted_state_path,
    manifest_path=manifest_path,
    bounding_box=bounding_box,
    crop_box=crop_box,
  )
  manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
    encoding="utf-8",
  )
  return _augment_bundle_with_visual_context(
    bundle,
    output_dir=output_dir,
    manifest_path=manifest_path,
    manifest=manifest,
  )


def _candidate_bounding_box(bundle: ReviewBundle) -> dict[str, float] | None:
  raw_boxes = bundle.evidence.get("bounding_boxes")
  if not isinstance(raw_boxes, list):
    return None

  preferred_element_id = _primary_element_id(bundle)
  for item in raw_boxes:
    if not isinstance(item, dict):
      continue
    if preferred_element_id and item.get("element_id") != preferred_element_id:
      continue
    box = _coerce_bounding_box(item.get("bounding_box"))
    if box is not None:
      return box

  for item in raw_boxes:
    if not isinstance(item, dict):
      continue
    box = _coerce_bounding_box(item.get("bounding_box"))
    if box is not None:
      return box
  return None


def _primary_element_id(bundle: ReviewBundle) -> str:
  if bundle.primary_element_ref:
    value = bundle.primary_element_ref.get("element_id")
    if isinstance(value, str) and value:
      return value
  for ref in bundle.element_refs:
    value = ref.get("element_id")
    if isinstance(value, str) and value:
      return value
  return ""


def _coerce_bounding_box(value: Any) -> dict[str, float] | None:
  if not isinstance(value, dict):
    return None
  try:
    box = {
      "x": float(value["x"]),
      "y": float(value["y"]),
      "width": float(value["width"]),
      "height": float(value["height"]),
    }
  except (KeyError, TypeError, ValueError):
    return None
  if box["width"] <= 0 or box["height"] <= 0:
    return None
  return box


def _resolve_run_relative_path(run_dir: Path, ref: str) -> Path:
  ref_path = Path(ref)
  if ref_path.is_absolute():
    raise ValueError("Artifact ref must be relative to run_dir")
  resolved_run_dir = run_dir.resolve()
  resolved = (resolved_run_dir / ref_path).resolve()
  try:
    resolved.relative_to(resolved_run_dir)
  except ValueError as exc:
    raise ValueError("Artifact ref resolves outside run_dir") from exc
  return resolved


def _padded_crop_box(box: dict[str, float], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
  image_width, image_height = image_size
  padding = max(24, int(max(box["width"], box["height"]) * 0.35))
  # an element partly or wholly outside the screenshot still gives a valid (clamped) box (W4A dev round 2)
  left = min(max(0, int(box["x"]) - padding), max(0, image_width - 1))
  top = min(max(0, int(box["y"]) - padding), max(0, image_height - 1))
  right = min(image_width, int(box["x"] + box["width"]) + padding)
  bottom = min(image_height, int(box["y"] + box["height"]) + padding)
  if right <= left:
    right = min(image_width, left + 1)
  if bottom <= top:
    bottom = min(image_height, top + 1)
  return (left, top, right, bottom)


def _draw_highlight(image: Image.Image, box: dict[str, float]) -> None:
  draw = ImageDraw.Draw(image, "RGBA")
  left = int(box["x"])
  top = int(box["y"])
  right = int(box["x"] + box["width"])
  bottom = int(box["y"] + box["height"])
  stroke_width = max(4, int(max(box["width"], box["height"]) * 0.06))
  overlay_padding = stroke_width * 2
  width, height = image.size

  def clamp(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int] | None:
    # an element partly or wholly outside the screenshot (e.g. above its top) is drawn clipped, or not at all
    x0, x1 = max(0, min(x0, width - 1)), max(0, min(x1, width - 1))
    y0, y1 = max(0, min(y0, height - 1)), max(0, min(y1, height - 1))
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None

  outer = clamp(left - overlay_padding, top - overlay_padding, right + overlay_padding, bottom + overlay_padding)
  if outer:
    draw.rectangle(outer, outline=(255, 193, 7, 255), width=stroke_width)
  inner = clamp(left, top, right, bottom)
  if inner:
    draw.rectangle(inner, outline=(220, 38, 38, 255), width=stroke_width)


def _build_manifest(
  *,
  bundle: ReviewBundle,
  output_dir: Path,
  screenshot_path: Path,
  screenshot_ref: str,
  target_crop_path: Path,
  highlighted_state_path: Path,
  manifest_path: Path,
  bounding_box: dict[str, float],
  crop_box: tuple[int, int, int, int],
) -> dict[str, object]:
  return {
    "schema_version": CANDIDATE_VISUAL_CONTEXT_SCHEMA_VERSION,
    "candidate_id": bundle.candidate_id,
    "candidate_type": bundle.candidate_type,
    "state_id": bundle.state_id,
    "source_screenshot": screenshot_ref,
    "source_screenshot_sha256": sha256_hex(screenshot_path.read_bytes()),
    "bounding_box": bounding_box,
    "crop_box": {
      "left": crop_box[0],
      "top": crop_box[1],
      "right": crop_box[2],
      "bottom": crop_box[3],
    },
    "target_crop": _relative_to_output(target_crop_path, output_dir),
    "highlighted_state": _relative_to_output(highlighted_state_path, output_dir),
    "manifest": _relative_to_output(manifest_path, output_dir),
    "preferred_image_order": [
      "target_crop",
      "highlighted_state",
    ],
    "generator": {
      "name": "offline_candidate_visual_context",
      "version": "1",
    },
  }


def _augment_bundle_with_visual_context(
  bundle: ReviewBundle,
  *,
  output_dir: Path,
  manifest_path: Path,
  manifest: dict[str, object],
) -> ReviewBundle:
  output_dir = output_dir.resolve()
  run_dir = bundle.run_dir.resolve()
  visual_refs: dict[str, object] = {
    "manifest": _relative_to_run(manifest_path, run_dir),
    "source_screenshot": manifest.get("source_screenshot"),
  }
  for key in ("target_crop", "highlighted_state"):
    value = manifest.get(key)
    if isinstance(value, str) and value:
      visual_refs[key] = _relative_to_run(output_dir / value, run_dir)
  visual_refs["bounding_box"] = manifest.get("bounding_box")
  visual_refs["crop_box"] = manifest.get("crop_box")
  visual_refs["preferred_image_order"] = manifest.get("preferred_image_order")

  return replace(
    bundle,
    artifact_refs={
      **bundle.artifact_refs,
      "visual_context": visual_refs,
    },
  )


def _relative_to_output(path: Path, output_dir: Path) -> str:
  return path.resolve().relative_to(output_dir.resolve()).as_posix()


def _relative_to_run(path: Path, run_dir: Path) -> str:
  return path.resolve().relative_to(run_dir.resolve()).as_posix()


def _safe_path_part(value: str) -> str:
  safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
  return safe or "candidate"
