from __future__ import annotations

import asyncio
import re
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
CLEAN_VTT_PATH = MEDIA_DIR / "brightlane-checkout-walkthrough.en.vtt"
SEEDED_VTT_PATH = MEDIA_DIR / "brightlane-checkout-walkthrough.co-sem-139.en.vtt"
PROFILE = "checkout-co-sem-139"
PROFILE_GLOBAL = "__ACCESSGRAPH_CHECKOUT_PROFILE__"
CLEAN_CUE = "Next, provide your payment details, then move to Review."
SEEDED_CUE = "Next, provide your payment details, then move to Cart."
TIMING_RE = re.compile(
  r"^(?P<start>\d{2}:\d{2}:\d{2}\.\d{3}) --> "
  r"(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})$"
)


def _vtt_cues(path: Path) -> list[dict[str, str]]:
  blocks = re.split(r"\r?\n\r?\n", path.read_text(encoding="utf-8").strip())
  assert blocks[0] == "WEBVTT"
  cues: list[dict[str, str]] = []
  for block in blocks[1:]:
    lines = block.splitlines()
    match = TIMING_RE.fullmatch(lines[0])
    assert match is not None
    cues.append(
      {
        "start": match.group("start"),
        "end": match.group("end"),
        "text": " ".join(" ".join(lines[1:]).split()),
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
  return subprocess.Popen(
    [
      "npm.cmd",
      "run",
      "dev",
      "--",
      "--host",
      "127.0.0.1",
      "--port",
      str(port),
      "--strictPort",
    ],
    cwd=CHECKOUT_DIR,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
  )


def _stop_process(process: subprocess.Popen[str]) -> None:
  if process.poll() is not None:
    return
  process.terminate()
  try:
    process.wait(timeout=5)
  except subprocess.TimeoutExpired:
    process.kill()


def test_seeded_vtt_changes_exactly_one_cue_text() -> None:
  clean_cues = _vtt_cues(CLEAN_VTT_PATH)
  seeded_cues = _vtt_cues(SEEDED_VTT_PATH)

  assert len(clean_cues) == len(seeded_cues) == 9
  assert [cue["start"] for cue in clean_cues] == [
    cue["start"] for cue in seeded_cues
  ]
  assert [cue["end"] for cue in clean_cues] == [
    cue["end"] for cue in seeded_cues
  ]
  differences = [
    (index, clean_cue["text"], seeded_cue["text"])
    for index, (clean_cue, seeded_cue) in enumerate(
      zip(clean_cues, seeded_cues, strict=True)
    )
    if clean_cue["text"] != seeded_cue["text"]
  ]
  assert differences == [(4, CLEAN_CUE, SEEDED_CUE)]


def test_co_sem_139_profile_preserves_video_and_track_metadata() -> None:
  async def run() -> None:
    playwright = pytest.importorskip("playwright.async_api")
    port = _find_free_port()
    server = _start_vite_dev(port=port)
    manager = None
    browser = None
    clean_context = None
    seeded_context = None
    try:
      base_url = f"http://127.0.0.1:{port}"
      _wait_for_url(base_url, timeout_seconds=20)
      manager = await playwright.async_playwright().start()
      browser = await manager.chromium.launch(headless=True)
      clean_context = await browser.new_context(viewport={"width": 1280, "height": 720})
      seeded_context = await browser.new_context(viewport={"width": 1280, "height": 720})
      await seeded_context.add_init_script(
        f"window[{PROFILE_GLOBAL!r}] = {PROFILE!r};"
      )
      clean_page = await clean_context.new_page()
      seeded_page = await seeded_context.new_page()
      await clean_page.goto(f"{base_url}/products", wait_until="domcontentloaded")
      await seeded_page.goto(f"{base_url}/products", wait_until="domcontentloaded")

      async def snapshot(page):
        await page.wait_for_function(
          "document.querySelector('[data-testid=\"checkout-walkthrough-captions\"]').readyState === 2"
        )
        return await page.evaluate(
          """() => {
            const video = document.querySelector('.checkout-walkthrough-video');
            const track = document.querySelector('[data-testid="checkout-walkthrough-captions"]');
            return {
              route: window.location.pathname,
              productsText: document.querySelector('[data-testid="route-products"]').innerText,
              video: {
                src: video.getAttribute('src'),
                currentSrc: video.currentSrc,
                controls: video.controls,
                preload: video.preload,
                autoplay: video.autoplay,
                muted: video.defaultMuted,
                loop: video.loop,
                duration: video.duration,
                ariaLabelledby: video.getAttribute('aria-labelledby'),
              },
              track: {
                kind: track.getAttribute('kind'),
                src: track.getAttribute('src'),
                srclang: track.getAttribute('srclang'),
                label: track.getAttribute('label'),
                default: track.default,
                mode: track.track.mode,
                cues: Array.from(track.track.cues || [], cue => ({
                  start: cue.startTime,
                  end: cue.endTime,
                  text: cue.text,
                })),
              },
            };
          }"""
        )

      clean = await snapshot(clean_page)
      seeded = await snapshot(seeded_page)

      assert clean["route"] == seeded["route"] == "/products"
      assert clean["productsText"] == seeded["productsText"]
      assert clean["video"] == seeded["video"]
      assert clean["track"] | {"src": seeded["track"]["src"], "cues": seeded["track"]["cues"]} == seeded["track"]
      assert clean["track"]["src"] == "/media/brightlane-checkout-walkthrough.en.vtt"
      assert seeded["track"]["src"] == (
        "/media/brightlane-checkout-walkthrough.co-sem-139.en.vtt"
      )
      clean_cues = clean["track"]["cues"]
      seeded_cues = seeded["track"]["cues"]
      assert len(clean_cues) == len(seeded_cues) == 9
      assert [(cue["start"], cue["end"]) for cue in clean_cues] == [
        (cue["start"], cue["end"]) for cue in seeded_cues
      ]
      assert [cue["text"] for cue in clean_cues][4] == CLEAN_CUE
      assert [cue["text"] for cue in seeded_cues][4] == SEEDED_CUE
      assert [cue["text"] for cue in clean_cues[:4] + clean_cues[5:]] == [
        cue["text"] for cue in seeded_cues[:4] + seeded_cues[5:]
      ]
    finally:
      if clean_context is not None:
        await clean_context.close()
      if seeded_context is not None:
        await seeded_context.close()
      if browser is not None:
        await browser.close()
      if manager is not None:
        await manager.stop()
      _stop_process(server)

  asyncio.run(run())
