import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any


def _viewport_height(page: Page) -> int:
  viewport = page.viewport_size or {"width": 1280, "height": 720}
  return int(viewport["height"])


def _tile_scroll_offset(index: int, *, total_tiles: int, total_height: int, viewport_height: int) -> int:
  if total_tiles <= 1:
    return 0
  return int(index * (total_height - viewport_height) / (total_tiles - 1))


async def screenshot_tiles(
  page: Page,
  out_dir: Path,
  state_id: str,
  max_tiles: int = 6,
) -> list[str]:
  """
  Take multiple viewport-sized screenshots by scrolling down the page.
  Returns list of filenames.
  """
  viewport_height = _viewport_height(page)
  total_height = await page.evaluate("() => document.documentElement.scrollHeight")
  if not isinstance(total_height, (int, float)) or total_height <= 0:
    total_height = viewport_height

  tiles = min(max_tiles, max(1, math.ceil(total_height / viewport_height)))
  names: list[str] = []

  for index in range(tiles):
    offset = _tile_scroll_offset(
      index,
      total_tiles=tiles,
      total_height=int(total_height),
      viewport_height=viewport_height,
    )
    await page.evaluate("(y) => window.scrollTo(0, y)", offset)
    await page.wait_for_timeout(250)

    name = f"{state_id}.tile_{index:02d}.png"
    path = out_dir / name
    await page.screenshot(path=str(path), full_page=False)
    names.append(name)

  # Return to top so later actions run from a consistent viewport origin.
  await page.evaluate("() => window.scrollTo(0, 0)")
  await page.wait_for_timeout(150)
  return names
