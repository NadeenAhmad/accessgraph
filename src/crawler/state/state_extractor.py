import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any

try:
  from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
  PlaywrightTimeoutError = TimeoutError

from src.crawler.evidence import write_accessibility_context

from .hashing import html_hash, rendered_dom_identity_hash_for_page, wait_for_page_settled
from .screenshots import screenshot_tiles


@dataclass(frozen=True)
class StateArtifact:
  url: str
  html_hash: str
  dom_identity_hash: str
  html_path: Path
  screenshot_path: Path
  aria_snapshot_path: Path
  accessibility_context_path: Path
  metadata_path: Path
  title: str
  route: str


@dataclass(frozen=True)
class _StateArtifactPaths:
  state_dir: Path
  html_path: Path
  screenshot_path: Path
  aria_snapshot_path: Path
  accessibility_context_path: Path
  metadata_path: Path


@dataclass(frozen=True)
class _CapturedState:
  url: str
  route: str
  title: str
  html: str
  html_hash: str
  dom_identity_hash: str


ScreenshotMode = str

_COORDINATE_SPACE_SCRIPT = """() => {
  const root = document.documentElement;
  const body = document.body;
  const maxDimension = (values) => Math.max(0, ...values.filter((value) => Number.isFinite(value)));
  return {
    marker: "accessgraph_coordinate_space_v1",
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      client_width: root ? root.clientWidth : null,
      client_height: root ? root.clientHeight : null,
    },
    device_pixel_ratio: window.devicePixelRatio || 1,
    scroll_offset: {
      x: window.scrollX || 0,
      y: window.scrollY || 0,
    },
    document: {
      scroll_width: maxDimension([
        root ? root.scrollWidth : 0,
        root ? root.offsetWidth : 0,
        body ? body.scrollWidth : 0,
        body ? body.offsetWidth : 0,
      ]),
      scroll_height: maxDimension([
        root ? root.scrollHeight : 0,
        root ? root.offsetHeight : 0,
        body ? body.scrollHeight : 0,
        body ? body.offsetHeight : 0,
      ]),
    },
  };
}"""


def _state_artifact_paths(out_dir: Path, state_id: str) -> _StateArtifactPaths:
  state_dir = out_dir / "states" / state_id
  return _StateArtifactPaths(
    state_dir=state_dir,
    html_path=state_dir / "dom.html",
    screenshot_path=state_dir / "screenshot.png",
    aria_snapshot_path=state_dir / "aria_snapshot.json",
    accessibility_context_path=state_dir / "accessibility_context.json",
    metadata_path=state_dir / "metadata.json",
  )


def _create_state_artifact_dir(paths: _StateArtifactPaths) -> None:
  paths.state_dir.mkdir(parents=True, exist_ok=True)


def _state_route(url: str) -> str:
  return urlparse(url).path or "/"


def _write_json(path: Path, payload: dict[str, object]) -> None:
  path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _error_payload(error: Exception) -> dict[str, str]:
  return {
    "type": type(error).__name__,
    "message": str(error),
  }


async def _capture_browser_state(page: Page) -> _CapturedState:
  await wait_for_page_settled(page)  # record the settled page, not a loading spinner (W4A dev round 2)
  url = page.url
  html = await page.content()
  return _CapturedState(
    url=url,
    route=_state_route(url),
    title=await page.title(),
    html=html,
    html_hash=html_hash(html),
    dom_identity_hash=await rendered_dom_identity_hash_for_page(page),
  )


def _state_metadata_payload(
  state_id: str,
  paths: _StateArtifactPaths,
  captured_state: _CapturedState,
  screenshot_tile_paths: list[str],
  screenshot_mode: ScreenshotMode,
  aria_snapshot: dict[str, object],
  depth: int,
  parent_state: str | None,
  action_from_parent: dict[str, object] | None,
  coordinate_space: dict[str, object],
) -> dict[str, object]:
  return {
    "state_id": state_id,
    "url": captured_state.url,
    "depth": depth,
    "parent_state": parent_state,
    "action_from_parent": action_from_parent,
    "route": captured_state.route,
    "title": captured_state.title,
    "html_hash": captured_state.html_hash,
    "dom_identity_hash": captured_state.dom_identity_hash,
    "html": paths.html_path.name,
    "screenshot": paths.screenshot_path.name,
    "screenshot_mode": screenshot_mode,
    "aria_snapshot": aria_snapshot,
    "accessibility_context": paths.accessibility_context_path.name,
    "screenshot_tiles": screenshot_tile_paths,
    "coordinate_space": coordinate_space,
  }


def _build_state_artifact(paths: _StateArtifactPaths, captured_state: _CapturedState) -> StateArtifact:
  return StateArtifact(
    url=captured_state.url,
    html_hash=captured_state.html_hash,
    dom_identity_hash=captured_state.dom_identity_hash,
    html_path=paths.html_path,
    screenshot_path=paths.screenshot_path,
    aria_snapshot_path=paths.aria_snapshot_path,
    accessibility_context_path=paths.accessibility_context_path,
    metadata_path=paths.metadata_path,
    title=captured_state.title,
    route=captured_state.route,
  )


def _write_dom_html(paths: _StateArtifactPaths, captured_state: _CapturedState) -> None:
  paths.html_path.write_text(captured_state.html, encoding="utf-8", errors="ignore")


async def _capture_primary_screenshot(page: Page, path: Path) -> ScreenshotMode:
  try:
    await page.screenshot(path=str(path), full_page=True)
    return "full_page"
  except PlaywrightTimeoutError:
    await page.screenshot(path=str(path), full_page=False)
    return "viewport_fallback"


async def _capture_page_coordinate_metrics(page: Page) -> dict[str, object]:
  captured_at_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
  try:
    payload = await page.evaluate(_COORDINATE_SPACE_SCRIPT)
  except Exception as error:
    viewport = getattr(page, "viewport_size", None)
    return {
      "captured_at_utc": captured_at_utc,
      "status": "partial",
      "viewport": dict(viewport) if isinstance(viewport, dict) else {},
      "error": _error_payload(error),
    }
  if not isinstance(payload, dict):
    return {
      "captured_at_utc": captured_at_utc,
      "status": "partial",
      "viewport": {},
      "error": {
        "type": "InvalidCoordinateMetrics",
        "message": "Browser returned a non-object coordinate-space payload",
      },
    }
  payload.pop("marker", None)
  payload["captured_at_utc"] = captured_at_utc
  payload["status"] = "ok"
  return payload


def _screenshot_image_metadata(path: Path) -> dict[str, object]:
  try:
    with Image.open(path) as image:
      return {
        "status": "ok",
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
      }
  except (OSError, UnidentifiedImageError) as error:
    return {
      "status": "error",
      "width": None,
      "height": None,
      "error": _error_payload(error),
    }


def _coordinate_space_metadata(
  *,
  screenshot_mode: ScreenshotMode,
  screenshot_image: dict[str, object],
  screenshot_capture: dict[str, object],
  evidence_capture: dict[str, object],
) -> dict[str, object]:
  warnings: list[str] = []
  screenshot_viewport = screenshot_capture.get("viewport")
  evidence_viewport = evidence_capture.get("viewport")
  if isinstance(screenshot_viewport, dict) and isinstance(evidence_viewport, dict):
    for dimension in ("width", "height"):
      before = screenshot_viewport.get(dimension)
      after = evidence_viewport.get(dimension)
      if isinstance(before, (int, float)) and isinstance(after, (int, float)) and abs(before - after) > 1:
        warnings.append(f"viewport_{dimension}_changed_between_screenshot_and_evidence")

  return {
    "schema_version": "coordinate_space_v1",
    "bounding_boxes": {
      "units": "css_pixels",
      "origin": "viewport",
      "source": "Element.getBoundingClientRect",
      "captured_with": "accessibility_context",
    },
    "screenshot": {
      "units": "image_pixels",
      "mode": screenshot_mode,
      "image": screenshot_image,
    },
    "screenshot_capture": screenshot_capture,
    "evidence_capture": evidence_capture,
    "capture_order": [
      "dom_snapshot",
      "screenshot_coordinate_metrics",
      "primary_screenshot",
      "tile_screenshots",
      "aria_snapshot",
      "accessibility_context",
      "evidence_coordinate_metrics",
    ],
    "transform_note": (
      "Bounding boxes use viewport-relative CSS pixels. Full-page screenshot coordinates require scroll-offset "
      "and image-scale handling; viewport screenshots require image-to-viewport scaling."
    ),
    "warnings": warnings,
  }


async def _capture_aria_snapshot(page: Page, path: Path) -> dict[str, object]:
  try:
    aria_yaml = await page.locator("body").aria_snapshot()
    _write_json(path, {"raw": aria_yaml})
    return {
      "status": "ok",
      "path": path.name,
    }
  except Exception as error:
    try:
      path.unlink(missing_ok=True)
    except OSError:
      pass
    return {
      "status": "error",
      "path": None,
      "error": _error_payload(error),
    }


async def _capture_tile_screenshots(
  page: Page,
  paths: _StateArtifactPaths,
  state_id: str,
  enable_tile_screenshots: bool,
) -> list[str]:
  if not enable_tile_screenshots:
    return []
  return await screenshot_tiles(page, paths.state_dir, state_id, max_tiles=6)


async def _write_accessibility_context(
  page: Page,
  paths: _StateArtifactPaths,
  *,
  state_id: str,
  depth: int,
  parent_state: str | None,
  action_from_parent: dict[str, object] | None,
) -> None:
  await write_accessibility_context(
    page,
    paths.state_dir,
    state_id=state_id,
    screenshot_path=paths.screenshot_path,
    depth=depth,
    parent_state=parent_state,
    action_from_parent=action_from_parent,
  )


def _write_state_metadata(
  paths: _StateArtifactPaths,
  *,
  state_id: str,
  captured_state: _CapturedState,
  screenshot_tile_paths: list[str],
  screenshot_mode: ScreenshotMode,
  aria_snapshot: dict[str, object],
  depth: int,
  parent_state: str | None,
  action_from_parent: dict[str, object] | None,
  coordinate_space: dict[str, object],
) -> None:
  _write_json(
    paths.metadata_path,
    _state_metadata_payload(
      state_id,
      paths,
      captured_state,
      screenshot_tile_paths,
      screenshot_mode,
      aria_snapshot,
      depth,
      parent_state,
      action_from_parent,
      coordinate_space,
    ),
  )


async def capture_state_artifacts(
  page: Page,
  out_dir: Path,
  state_id: str = "state_0000",
  depth: int = 0,
  parent_state: str | None = None,
  action_from_parent: dict[str, object] | None = None,
  enable_tile_screenshots: bool = True,
) -> StateArtifact:
  """Capture artifacts for the current browser page state.

  The caller is responsible for waiting/settling the page before calling this.
  `accessibility_context.json` stores bounded accessibility context for later
  offline analysis; it is not a violation, candidate, model judgment, or report.
  """
  paths = _state_artifact_paths(out_dir, state_id)
  _create_state_artifact_dir(paths)

  captured_state = await _capture_browser_state(page)
  _write_dom_html(paths, captured_state)

  screenshot_capture_metrics = await _capture_page_coordinate_metrics(page)
  screenshot_mode = await _capture_primary_screenshot(page, paths.screenshot_path)
  screenshot_image = _screenshot_image_metadata(paths.screenshot_path)
  screenshot_tile_paths = await _capture_tile_screenshots(page, paths, state_id, enable_tile_screenshots)
  aria_snapshot = await _capture_aria_snapshot(page, paths.aria_snapshot_path)
  await _write_accessibility_context(
    page,
    paths,
    state_id=state_id,
    depth=depth,
    parent_state=parent_state,
    action_from_parent=action_from_parent,
  )
  evidence_capture_metrics = await _capture_page_coordinate_metrics(page)
  coordinate_space = _coordinate_space_metadata(
    screenshot_mode=screenshot_mode,
    screenshot_image=screenshot_image,
    screenshot_capture=screenshot_capture_metrics,
    evidence_capture=evidence_capture_metrics,
  )
  _write_state_metadata(
    paths,
    state_id=state_id,
    captured_state=captured_state,
    screenshot_tile_paths=screenshot_tile_paths,
    screenshot_mode=screenshot_mode,
    aria_snapshot=aria_snapshot,
    depth=depth,
    parent_state=parent_state,
    action_from_parent=action_from_parent,
    coordinate_space=coordinate_space,
  )

  return _build_state_artifact(paths, captured_state)
