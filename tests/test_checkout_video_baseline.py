from __future__ import annotations

import asyncio
import os
import re
import signal
import socket
import subprocess
import time
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_DIR = REPO_ROOT / "benchmarks" / "local-spas" / "checkout-flow"
MEDIA_DIR = CHECKOUT_DIR / "public" / "media"
VIDEO_PATH = MEDIA_DIR / "brightlane-checkout-walkthrough.mp4"
VTT_PATH = MEDIA_DIR / "brightlane-checkout-walkthrough.en.vtt"
REFERENCE_DIR = REPO_ROOT / "benchmarks" / "reference" / "brightlane-checkout"
TRANSCRIPT_PATH = REFERENCE_DIR / "narration-transcript.txt"
PROVENANCE_PATH = REFERENCE_DIR / "provenance.txt"
VITE_PATH = CHECKOUT_DIR / "node_modules" / "vite" / "bin" / "vite.js"
VIDEO_DURATION_SECONDS = 27.625
SHUTDOWN_TIMEOUT_SECONDS = 5
PROCESS_GROUP_POLL_INTERVAL_SECONDS = 0.05
EXPECTED_TITLE = "How Brightlane Checkout Works"
EXPECTED_CLAIM = "Exact narration transcript"
EXPECTED_NARRATION = (
  "Shopping with Brightlane takes just a few steps. First, choose your products "
  "and add them to your cart. In Cart, check quantities and the order total. "
  "Continue to Shipping address and enter your delivery details. Next, provide "
  "your payment details, then move to Review. Check your address, payment summary, "
  "items, and totals. When you are ready, use Place order. Need to change "
  "something? Use the navigation to return to Cart."
)
TIMING_RE = re.compile(
  r"^(?P<start>\d{2}:\d{2}:\d{2}\.\d{3}) --> "
  r"(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})$"
)


def _normalize_text(value: str) -> str:
  return " ".join(value.split())


def _timestamp_seconds(value: str) -> float:
  hours, minutes, seconds = value.split(":")
  return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)


def _vtt_cues() -> list[dict[str, object]]:
  content = VTT_PATH.read_text(encoding="utf-8")
  blocks = re.split(r"\r?\n\r?\n", content.strip())
  assert blocks[0] == "WEBVTT"

  cues = []
  for block in blocks[1:]:
    lines = block.splitlines()
    match = TIMING_RE.fullmatch(lines[0])
    assert match is not None
    cues.append(
      {
        "start": _timestamp_seconds(match.group("start")),
        "end": _timestamp_seconds(match.group("end")),
        "text": _normalize_text(" ".join(lines[1:])),
      }
    )
  return cues


def _find_free_port() -> int:
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
    sock.bind(("127.0.0.1", 0))
    return int(sock.getsockname()[1])


def _wait_for_url(url: str, *, timeout_seconds: float) -> None:
  deadline = time.monotonic() + timeout_seconds
  while time.monotonic() < deadline:
    try:
      with urlopen(url, timeout=1):
        return
    except OSError:
      time.sleep(0.1)
  pytest.fail(f"Checkout SPA did not become ready: {url}")


def _start_vite_dev(*, port: int) -> subprocess.Popen[str]:
  if not VITE_PATH.is_file():
    pytest.fail(f"Checkout Vite executable is unavailable: {VITE_PATH}")

  process_group_options = (
    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    if os.name == "nt"
    else {"start_new_session": True}
  )
  return subprocess.Popen(
    [
      "node",
      str(VITE_PATH),
      "--host",
      "127.0.0.1",
      "--port",
      str(port),
      "--strictPort",
    ],
    cwd=CHECKOUT_DIR,
    text=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    **process_group_options,
  )


def _wait_for_process_exit(process: subprocess.Popen[str]) -> None:
  try:
    process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
  except subprocess.TimeoutExpired:
    process.kill()
    process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)


def _stop_windows_process_tree(process: subprocess.Popen[str]) -> None:
  try:
    result = subprocess.run(
      ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
      text=True,
      capture_output=True,
      timeout=SHUTDOWN_TIMEOUT_SECONDS,
      check=False,
    )
  except subprocess.TimeoutExpired as exc:
    _wait_for_process_exit(process)
    raise RuntimeError(
      f"Timed out while stopping Checkout Vite process tree {process.pid}."
    ) from exc

  if result.returncode != 0 and process.poll() is None:
    _wait_for_process_exit(process)
    raise RuntimeError(
      "Could not stop Checkout Vite process tree "
      f"{process.pid}: {result.stderr.strip() or result.stdout.strip()}"
    )
  _wait_for_process_exit(process)


def _stop_posix_process_group(process: subprocess.Popen[str]) -> None:
  process_group_id = process.pid

  def process_group_exists() -> bool:
    try:
      os.killpg(process_group_id, 0)
    except ProcessLookupError:
      return False
    except PermissionError:
      return True
    return True

  def wait_for_process_group_exit() -> bool:
    deadline = time.monotonic() + SHUTDOWN_TIMEOUT_SECONDS
    while True:
      process.poll()
      if not process_group_exists():
        return True
      if time.monotonic() >= deadline:
        return False
      time.sleep(PROCESS_GROUP_POLL_INTERVAL_SECONDS)

  if not process_group_exists():
    process.poll()
    return

  try:
    os.killpg(process_group_id, signal.SIGTERM)
  except ProcessLookupError:
    process.poll()
    return

  if not wait_for_process_group_exit():
    try:
      os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
      pass
    if not wait_for_process_group_exit():
      raise RuntimeError(
        f"Checkout Vite process group {process_group_id} did not stop."
      )

  process.poll()


def _stop_process(process: subprocess.Popen[str]) -> None:
  if os.name == "nt":
    if process.poll() is None:
      _stop_windows_process_tree(process)
    return
  _stop_posix_process_group(process)


async def _cleanup_test_resources(
  *,
  context,
  browser,
  manager,
  server: subprocess.Popen[str],
  primary_error: BaseException | None,
) -> None:
  cleanup_errors: list[tuple[str, BaseException]] = []
  async_operations = (
    ("Playwright context cleanup failed", context, "close"),
    ("Playwright browser cleanup failed", browser, "close"),
    ("Playwright manager cleanup failed", manager, "stop"),
  )
  for message, resource, method_name in async_operations:
    if resource is None:
      continue
    try:
      await asyncio.wait_for(
        getattr(resource, method_name)(),
        timeout=SHUTDOWN_TIMEOUT_SECONDS,
      )
    except BaseException as exc:
      cleanup_errors.append((message, exc))

  try:
    _stop_process(server)
  except BaseException as exc:
    cleanup_errors.append(("Checkout Vite cleanup failed", exc))

  if not cleanup_errors:
    return
  if primary_error is not None:
    for message, error in cleanup_errors:
      primary_error.add_note(f"{message}: {error}")
    return

  first_message, first_error = cleanup_errors[0]
  first_error.add_note(first_message)
  for message, error in cleanup_errors[1:]:
    first_error.add_note(f"{message}: {error}")
  raise first_error


def test_walkthrough_reference_and_provenance_are_exact() -> None:
  lines = TRANSCRIPT_PATH.read_text(encoding="utf-8-sig").splitlines()
  assert lines[0] == EXPECTED_TITLE
  assert lines[1] == EXPECTED_CLAIM
  assert _normalize_text(" ".join(lines[2:])) == EXPECTED_NARRATION

  provenance = PROVENANCE_PATH.read_text(encoding="utf-8")
  assert "Source: Supervisor-provided." in provenance
  assert "Original transcript filename: Brightlane_Checkout_Transcript.txt" in provenance
  assert "Paired video filename: Brightlane_Checkout_Walkthrough.mp4" in provenance
  assert "Timestamp data supplied: No." in provenance
  assert "Crawler-generated: No." in provenance
  assert "Automatic speech recognition: No." in provenance


def test_walkthrough_vtt_matches_transcript_and_has_sane_timing() -> None:
  cues = _vtt_cues()
  assert len(cues) == 9
  assert _normalize_text(" ".join(str(cue["text"]) for cue in cues)) == (
    EXPECTED_NARRATION
  )

  previous_end = 0.0
  for cue in cues:
    start = float(cue["start"])
    end = float(cue["end"])
    assert start >= previous_end
    assert end > start
    previous_end = end

  assert float(cues[0]["start"]) >= 0
  assert float(cues[-1]["end"]) <= VIDEO_DURATION_SECONDS
  assert "move to Cart" not in VTT_PATH.read_text(encoding="utf-8")
  assert "Cancel order" not in VTT_PATH.read_text(encoding="utf-8")


def test_walkthrough_video_is_an_accessible_products_support_feature() -> None:
  async def run() -> None:
    playwright = pytest.importorskip("playwright.async_api")
    port = _find_free_port()
    server = _start_vite_dev(port=port)
    manager = None
    browser = None
    context = None
    primary_error: BaseException | None = None
    try:
      base_url = f"http://127.0.0.1:{port}"
      _wait_for_url(base_url, timeout_seconds=20)
      manager = await playwright.async_playwright().start()
      browser = await manager.chromium.launch(headless=True)
      context = await browser.new_context(viewport={"width": 1280, "height": 720})
      page = await context.new_page()
      await page.goto(f"{base_url}/products", wait_until="domcontentloaded")

      support = page.get_by_role("region", name=EXPECTED_TITLE)
      assert await support.is_visible()
      assert await support.get_attribute("lang") == "en"
      assert await support.get_by_role("heading", name=EXPECTED_TITLE).is_visible()

      video = support.locator("video")
      assert await video.is_visible()
      assert await video.get_attribute("aria-labelledby") == (
        "checkout-walkthrough-heading"
      )
      assert await video.get_attribute("preload") == "metadata"
      assert await video.evaluate("element => element.controls") is True
      await page.wait_for_function(
        "document.querySelector('.checkout-walkthrough-video').readyState >= 1"
      )
      assert (await video.evaluate("element => element.currentSrc")).endswith(
        "/media/brightlane-checkout-walkthrough.mp4"
      )
      metadata = await video.evaluate(
        "element => ({"
        "duration: element.duration, "
        "width: element.videoWidth, "
        "height: element.videoHeight"
        "})"
      )
      assert metadata == {
        "duration": VIDEO_DURATION_SECONDS,
        "width": 1280,
        "height": 720,
      }

      track = video.locator("track")
      assert await track.get_attribute("kind") == "captions"
      assert await track.get_attribute("srclang") == "en"
      assert await track.get_attribute("label") == "English"
      assert await track.get_attribute("src") == (
        "/media/brightlane-checkout-walkthrough.en.vtt"
      )
      assert await track.evaluate("element => element.default") is True
      await page.wait_for_function(
        "document.querySelector('.checkout-walkthrough-video track').readyState === 2"
      )
      cue_text = await track.evaluate(
        "element => Array.from(element.track.cues || [], cue => cue.text).join(' ')"
      )
      assert _normalize_text(cue_text) == EXPECTED_NARRATION
      assert await track.evaluate("element => element.track.mode") == "showing"

      await video.evaluate("element => { element.muted = true; return element.play(); }")
      await page.wait_for_function(
        "document.querySelector('.checkout-walkthrough-video').currentTime >= 0.5"
      )
      active_cue_text = await track.evaluate(
        "element => Array.from(element.track.activeCues || [], cue => cue.text).join(' ')"
      )
      assert active_cue_text == "Shopping with Brightlane takes just a few steps."
      await video.evaluate("element => element.pause()")

      assert await page.get_by_role("button", name="Add Desk lamp").is_visible()
      assert await page.get_by_role("tab", name="Desk accessories").is_visible()
      assert await page.get_by_role("link", name="Shipping information").is_visible()
      assert VIDEO_PATH.is_file()
    except BaseException as exc:
      primary_error = exc
      raise
    finally:
      await _cleanup_test_resources(
        context=context,
        browser=browser,
        manager=manager,
        server=server,
        primary_error=primary_error,
      )

  asyncio.run(run())
