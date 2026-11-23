from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_hex
from .models import CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT, ReviewBundle


@dataclass(frozen=True)
class ScreenshotInput:
  relative_path: str
  absolute_path: Path
  sha256: str
  base64_data: str
  byte_length: int
  image_source: str = "state_screenshot"


def load_confirmation_image_inputs(
  bundle: ReviewBundle,
  *,
  context_mode: str | None = None,
) -> list[ScreenshotInput]:
  if context_mode == CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT:
    return [load_state_screenshot_input(bundle)]
  visual_inputs = _load_candidate_visual_context_inputs(bundle)
  if visual_inputs:
    return visual_inputs
  return [load_state_screenshot_input(bundle)]


def load_provider_image_inputs(
  bundle: ReviewBundle,
  *,
  provider: str,
  context_mode: str | None = None,
) -> list[ScreenshotInput]:
  image_inputs = load_confirmation_image_inputs(bundle, context_mode=context_mode)
  if provider == "ollama-vision":
    return image_inputs[:1]
  return image_inputs


def image_input_metadata(image_input: ScreenshotInput) -> dict[str, object]:
  return {
    "screenshot": image_input.relative_path,
    "image_path": image_input.relative_path,
    "image_source": image_input.image_source,
    "sha256": image_input.sha256,
    "byte_length": image_input.byte_length,
  }


def combined_image_source(image_inputs: list[ScreenshotInput]) -> str:
  sources = [image_input.image_source for image_input in image_inputs]
  if len(set(sources)) == 1:
    return sources[0]
  return "candidate_visual_context"


# W4A dev round 2: providers refuse very large images (a full-page screenshot of a long page can exceed 90 million
# pixels). Above this size, only a full-width band around the candidate's element is sent.
MAX_PROVIDER_IMAGE_PIXELS = 16_000_000


def _bounded_image_bytes(data: bytes, bundle: ReviewBundle | None) -> bytes:
  try:
    import io
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None  # our own screenshots, not untrusted uploads
    with Image.open(io.BytesIO(data)) as image:
      width, height = image.size
      if width * height <= MAX_PROVIDER_IMAGE_PIXELS:
        return data
      band = max(800, MAX_PROVIDER_IMAGE_PIXELS // max(width, 1))
      centre = 0
      if bundle is not None:
        from .visual_context import _candidate_bounding_box
        box = _candidate_bounding_box(bundle)
        if box is not None:
          centre = int(box["y"] + box["height"] / 2)
      top = min(max(0, centre - band // 2), max(0, height - band))
      cropped = image.crop((0, top, width, min(height, top + band)))
      out = io.BytesIO()
      cropped.save(out, format="PNG")
      return out.getvalue()
  except Exception:
    return data


def load_state_screenshot_input(bundle: ReviewBundle) -> ScreenshotInput:
  raw_ref = bundle.artifact_refs.get("screenshot")
  if not isinstance(raw_ref, str) or not raw_ref.strip():
    raise ValueError("Candidate artifact_refs.screenshot is missing or empty")

  ref_path = Path(raw_ref)
  if ref_path.is_absolute():
    raise ValueError("Candidate artifact_refs.screenshot must be relative to run_dir")

  run_dir = bundle.run_dir.resolve()
  screenshot_path = (run_dir / ref_path).resolve()
  try:
    relative_path = screenshot_path.relative_to(run_dir).as_posix()
  except ValueError as exc:
    raise ValueError("Candidate artifact_refs.screenshot resolves outside run_dir") from exc

  if not screenshot_path.is_file():
    raise FileNotFoundError(f"Screenshot artifact does not exist: {relative_path}")

  data = _bounded_image_bytes(screenshot_path.read_bytes(), bundle)
  return ScreenshotInput(
    relative_path=relative_path,
    absolute_path=screenshot_path,
    sha256=sha256_hex(data),
    base64_data=base64.b64encode(data).decode("ascii"),
    byte_length=len(data),
  )


def _load_candidate_visual_context_inputs(bundle: ReviewBundle) -> list[ScreenshotInput]:
  visual_context = bundle.artifact_refs.get("visual_context")
  if not isinstance(visual_context, dict):
    return []

  loaded: list[ScreenshotInput] = []
  for key, image_source in (
    ("target_crop", "candidate_target_crop"),
    ("highlighted_state", "candidate_highlighted_state"),
  ):
    raw_ref = visual_context.get(key)
    if not isinstance(raw_ref, str) or not raw_ref.strip():
      continue
    loaded.append(_load_run_relative_image(bundle, raw_ref, image_source=image_source))
  return loaded


def _load_run_relative_image(
  bundle: ReviewBundle,
  raw_ref: str,
  *,
  image_source: str,
) -> ScreenshotInput:
  ref_path = Path(raw_ref)
  if ref_path.is_absolute():
    raise ValueError("Candidate visual context image ref must be relative to run_dir")

  run_dir = bundle.run_dir.resolve()
  image_path = (run_dir / ref_path).resolve()
  try:
    relative_path = image_path.relative_to(run_dir).as_posix()
  except ValueError as exc:
    raise ValueError("Candidate visual context image ref resolves outside run_dir") from exc

  if not image_path.is_file():
    raise FileNotFoundError(f"Candidate visual context image artifact does not exist: {relative_path}")

  data = _bounded_image_bytes(image_path.read_bytes(), bundle)
  return ScreenshotInput(
    relative_path=relative_path,
    absolute_path=image_path,
    sha256=sha256_hex(data),
    base64_data=base64.b64encode(data).decode("ascii"),
    byte_length=len(data),
    image_source=image_source,
  )
