import asyncio
import hashlib

import pytest

from src.crawler.state.hashing import (
  canonicalize_url_for_state,
  normalized_rendered_dom_snapshot_for_page,
  raw_html_state_identity_hash,
  rendered_dom_identity_hash_for_page,
  state_dedup_key,
)


class FakeRenderedDomPage:
  url = "https://example.com/app"

  def __init__(self, rendered_snapshot: str):
    self.rendered_snapshot = rendered_snapshot
    self.script_seen = ""

  async def evaluate(self, script: str) -> str:
    self.script_seen = script
    return self.rendered_snapshot


class FakeFallbackHtmlPage:
  def __init__(self, html: str):
    self.html = html

  async def content(self) -> str:
    return self.html


def test_canonicalize_url_for_state_removes_tracking_params():
  url = "https://Example.com/docs/?utm_source=a&ref=nav&utm_medium=email"
  canonical = canonicalize_url_for_state(url)

  assert canonical == "https://example.com/docs?ref=nav"


def test_canonicalize_url_for_state_sorts_query_and_keeps_fragment():
  url = "https://example.com/path?b=2&a=1#section"
  canonical = canonicalize_url_for_state(url)

  assert canonical == "https://example.com/path?a=1&b=2#section"


def test_state_dedup_key_uses_dom_identity_hash_and_canonical_url():
  same_dom_identity_hash = "abc123"
  key_a = state_dedup_key(
    dom_identity_hash=same_dom_identity_hash,
    url="https://example.com/docs?utm_source=a&ref=nav",
  )
  key_b = state_dedup_key(
    dom_identity_hash=same_dom_identity_hash,
    url="https://example.com/docs?ref=nav&utm_medium=email",
  )

  assert key_a == key_b


def test_state_dedup_key_changes_with_meaningful_url_change():
  same_dom_identity_hash = "abc123"
  key_a = state_dedup_key(dom_identity_hash=same_dom_identity_hash, url="https://example.com/docs")
  key_b = state_dedup_key(dom_identity_hash=same_dom_identity_hash, url="https://example.com/docs/next")

  assert key_a != key_b


def test_state_dedup_key_with_raw_html_identity_ignores_head_only_html_noise():
  html_a = "<html><head><meta name='a'><meta name='b'></head><body><main>Docs</main></body></html>"
  html_b = "<html><head><meta name='b'><meta name='a'></head><body><main>Docs</main></body></html>"

  key_a = state_dedup_key(
    dom_identity_hash=raw_html_state_identity_hash(html_a),
    url="https://example.com/docs",
  )
  key_b = state_dedup_key(
    dom_identity_hash=raw_html_state_identity_hash(html_b),
    url="https://example.com/docs",
  )

  assert key_a == key_b


def test_state_dedup_key_with_raw_html_identity_changes_with_meaningful_body_difference():
  html_a = "<html><body><main>Docs</main></body></html>"
  html_b = "<html><body><main>Docs changed</main></body></html>"

  key_a = state_dedup_key(
    dom_identity_hash=raw_html_state_identity_hash(html_a),
    url="https://example.com/docs",
  )
  key_b = state_dedup_key(
    dom_identity_hash=raw_html_state_identity_hash(html_b),
    url="https://example.com/docs",
  )

  assert key_a != key_b


def test_raw_html_state_identity_hash_ignores_generated_code_tab_ids_and_group_names():
  html_a = """
  <html>
    <body>
      <main>
        <div class="vp-code-group">
          <div class="tabs">
            <input id="tab-pas2wm-0" type="radio" name="code-group-tabs-pas2wm" checked>
            <label for="tab-pas2wm-0">npm</label>
            <input id="tab-pas2wm-1" type="radio" name="code-group-tabs-pas2wm">
            <label for="tab-pas2wm-1">Yarn</label>
          </div>
        </div>
      </main>
    </body>
  </html>
  """
  html_b = """
  <html>
    <body>
      <main>
        <div class="vp-code-group">
          <div class="tabs">
            <input id="tab-o0oi9c-0" type="radio" name="code-group-tabs-o0oi9c" checked>
            <label for="tab-o0oi9c-0">npm</label>
            <input id="tab-o0oi9c-1" type="radio" name="code-group-tabs-o0oi9c">
            <label for="tab-o0oi9c-1">Yarn</label>
          </div>
        </div>
      </main>
    </body>
  </html>
  """

  assert raw_html_state_identity_hash(html_a) == raw_html_state_identity_hash(html_b)


def test_raw_html_state_identity_hash_ignores_hidden_elements():
  html_a = "<html><body><main><p>Visible</p><span hidden>Hidden A</span></main></body></html>"
  html_b = "<html><body><main><p>Visible</p><span hidden>Hidden B</span></main></body></html>"

  assert raw_html_state_identity_hash(html_a) == raw_html_state_identity_hash(html_b)


def test_raw_html_state_identity_hash_changes_for_color_and_background_styles():
  html_a = "<html><body><main><p style='color: red; background: white'>Status</p></main></body></html>"
  html_b = "<html><body><main><p style='color: blue; background: white'>Status</p></main></body></html>"

  assert raw_html_state_identity_hash(html_a) != raw_html_state_identity_hash(html_b)


def test_raw_html_state_identity_hash_ignores_transform_and_animation_styles():
  html_a = "<html><body><main><p style='transform: scale(1); animation: spin 1s'>Status</p></main></body></html>"
  html_b = "<html><body><main><p style='transform: scale(2); animation: fade 2s'>Status</p></main></body></html>"

  assert raw_html_state_identity_hash(html_a) == raw_html_state_identity_hash(html_b)


def test_rendered_dom_identity_hash_for_page_uses_browser_snapshot():
  page = FakeRenderedDomPage("<main> Rendered state </main>")

  digest = asyncio.run(rendered_dom_identity_hash_for_page(page))

  expected = hashlib.sha256("<main> Rendered state </main>".encode("utf-8")).hexdigest()
  assert digest == expected
  assert "normalizeNode" in page.script_seen


def test_normalized_rendered_dom_snapshot_for_page_falls_back_to_raw_html_identity():
  html = "<html><head><title>Noise</title></head><body><main>Fallback state</main></body></html>"
  page = FakeFallbackHtmlPage(html)

  snapshot = asyncio.run(normalized_rendered_dom_snapshot_for_page(page))

  assert snapshot == "Fallback state"


async def _with_chromium(callback):
  playwright = pytest.importorskip("playwright.async_api")
  try:
    manager = await playwright.async_playwright().start()
  except Exception as exc:
    pytest.skip(f"Playwright could not start in this environment: {exc}")
  browser = None
  try:
    try:
      browser = await manager.chromium.launch(headless=True)
    except Exception as exc:
      pytest.skip(f"Playwright Chromium is unavailable: {exc}")
    return await callback(browser)
  finally:
    if browser is not None:
      await browser.close()
    await manager.stop()


def test_rendered_dom_identity_changes_when_offscreen_menu_reveals_actionable_link():
  async def run_hash_check(browser):
    page = await browser.new_page(viewport={"width": 800, "height": 600})
    await page.set_content(
      """
      <html>
        <body>
          <button id="menu" type="button">menu</button>
          <mat-sidenav
            id="drawer"
            style="position: fixed; top: 0; left: 0; width: 220px; height: 100vh; transform: translateX(-260px);"
          >
            <a href="/about">About</a>
          </mat-sidenav>
          <script>
            document.querySelector("#menu").addEventListener("click", () => {
              document.querySelector("#drawer").style.transform = "translateX(0)";
            });
          </script>
        </body>
      </html>
      """,
      wait_until="domcontentloaded",
    )
    initial_hash = await rendered_dom_identity_hash_for_page(page)

    await page.click("#menu")

    assert await rendered_dom_identity_hash_for_page(page) != initial_hash

  asyncio.run(_with_chromium(run_hash_check))
