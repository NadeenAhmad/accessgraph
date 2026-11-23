import asyncio
import json

import pytest

from src.crawler.evidence import extract_accessibility_context, write_accessibility_context
from src.crawler.evidence.accessibility_context_schema import (
  EVIDENCE_CATEGORIES,
  EXTRACTION_LIMITS,
  FORBIDDEN_EVIDENCE_KEYS,
  ACCESSIBILITY_CONTEXT_SCHEMA_VERSION,
)


class FakeEvidencePage:
  url = "https://example.com/app"

  async def title(self) -> str:
    return "Example App"

  async def evaluate(self, _script: str, args: dict) -> dict:
    return {
      "schema_version": args["schemaVersion"],
      "state_id": args["stateId"],
      "state_context": args["stateContext"],
      "page": {
        "url": self.url,
        "title": "Example App",
        "document_lang": "en",
        "html_lang": "en",
        "body_text_sample": "Example App",
        "body_text_length": 11,
      },
      "referenced_elements": [],
      "images": [{"element_id": "e_img", "kind": "image", "selector": "img#logo", "alt": "Logo", "bounding_box": {}}],
      "videos": [],
      "links": [{"element_id": "e_link", "kind": "link", "selector": "a:nth-of-type(1)", "text": "Docs", "href": "/docs"}],
      "buttons": [{"element_id": "e_button", "kind": "button", "selector": "button#save", "text": "Save"}],
      "forms": [],
      "form_controls": [{"element_id": "e_control", "kind": "form_control", "selector": "input#email", "label": "Email"}],
      "headings": [{"element_id": "e_heading", "kind": "heading", "selector": "h1", "level": 1, "text": "Welcome"}],
      "landmarks": [{"element_id": "e_main", "kind": "landmark", "selector": "main", "tag": "main"}],
      "focusables": [{"element_id": "e_button", "kind": "focusable", "selector": "button#save", "dom_order_index": 0}],
      "focus_order": [{"order": 1, "element_id": "e_button"}],
      "relationships": [],
      "extraction_metadata": {
        "status": "success",
        "screenshot_path": args["screenshotPath"],
        "truncated": False,
        "truncation": {},
        "limits": args["limits"],
      },
    }


class BrokenEvidencePage:
  url = "https://example.com/app"

  async def title(self) -> str:
    return "Broken App"

  async def evaluate(self, _script: str, _args: dict) -> dict:
    raise RuntimeError("browser context failed")


def _contains_forbidden_key(value):
  if isinstance(value, dict):
    for key, child in value.items():
      lowered = str(key).lower()
      if any(forbidden in lowered for forbidden in FORBIDDEN_EVIDENCE_KEYS):
        return True
      if _contains_forbidden_key(child):
        return True
  if isinstance(value, list):
    return any(_contains_forbidden_key(item) for item in value)
  return False


def test_write_accessibility_context_writes_full_accessibility_context_schema(tmp_path):
  path = asyncio.run(
    write_accessibility_context(
      FakeEvidencePage(),
      tmp_path,
      state_id="state_0000",
      screenshot_path=tmp_path / "state_0000.png",
      depth=2,
      parent_state="state_0001",
      action_from_parent={"type": "click", "text": "Open"},
    )
  )

  payload = json.loads(path.read_text(encoding="utf-8"))
  assert path.name == "accessibility_context.json"
  assert payload["schema_version"] == ACCESSIBILITY_CONTEXT_SCHEMA_VERSION
  assert payload["state_context"] == {
    "depth": 2,
    "parent_state": "state_0001",
    "action_from_parent": {"type": "click", "text": "Open"},
  }
  assert payload["page"]["body_text_sample"] == "Example App"
  assert payload["extraction_metadata"]["status"] == "success"
  assert payload["extraction_metadata"]["limits"] == EXTRACTION_LIMITS
  for category in EVIDENCE_CATEGORIES:
    assert category in payload
    assert isinstance(payload[category], list)
  assert payload["focus_traversal_metadata"] == {
    "start_strategy": "focus_body_scroll_to_top_then_tab",
    "max_steps": EXTRACTION_LIMITS["max_focus_traversal_steps"],
    "captured_steps": 0,
    "traversal_complete": False,
    "partial": True,
    "cycle_detected": False,
    "stop_reason": "keyboard_unavailable",
    "initial_focus_selector": "",
    "focus_reset_target": "",
  }
  assert not _contains_forbidden_key(payload)


def test_write_accessibility_context_records_failure_without_crashing(tmp_path):
  path = asyncio.run(
    write_accessibility_context(
      BrokenEvidencePage(),
      tmp_path,
      state_id="state_0000",
      screenshot_path=tmp_path / "state_0000.png",
    )
  )

  payload = json.loads(path.read_text(encoding="utf-8"))
  assert payload["schema_version"] == ACCESSIBILITY_CONTEXT_SCHEMA_VERSION
  assert payload["extraction_metadata"]["status"] == "failed"
  assert "RuntimeError" in payload["extraction_metadata"]["error"]
  for category in EVIDENCE_CATEGORIES:
    assert payload[category] == []


def test_forbidden_key_scan_is_recursive():
  payload = {
    "schema_version": ACCESSIBILITY_CONTEXT_SCHEMA_VERSION,
    "images": [
      {
        "element_id": "e_img",
        "nested": {"confidence_score": 0.9},
      }
    ],
  }

  assert _contains_forbidden_key(payload)


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


def _first_with_text(items: list[dict], text: str) -> dict:
  return next(item for item in items if item.get("text") == text)


DISALLOWED_HEADING_SCOPE_MARKERS = {
  "is_ambiguous",
  "violation_likely",
  "semantic_judgment",
  "heading_text_differs_from_scoped_content",
  "heading_text_differs_from_route_or_state",
  "scope_matches_heading",
  "semantic_mismatch",
}


def _contains_disallowed_heading_scope_marker(value):
  if isinstance(value, dict):
    for key, child in value.items():
      if str(key) in DISALLOWED_HEADING_SCOPE_MARKERS:
        return True
      if _contains_disallowed_heading_scope_marker(child):
        return True
  if isinstance(value, list):
    return any(_contains_disallowed_heading_scope_marker(item) for item in value)
  if isinstance(value, str):
    return any(marker in value for marker in DISALLOWED_HEADING_SCOPE_MARKERS)
  return False


def test_extract_accessibility_context_uses_refined_accessibility_context_schema(tmp_path):
  async def run(browser):
    page = await browser.new_page()
    try:
      long_text = "Long evidence text " * 80
      await page.set_content(
        f"""
        <!doctype html>
        <html lang="en">
          <head><title>Evidence fixture</title></head>
          <body>
            <main>
              <h1>Evidence heading</h1>
              <p>{long_text}</p>
              <form aria-label="Contact form">
                <label for="email">Email address</label>
                <input id="email" name="email" autocomplete="email" required>
                <span id="button-desc" hidden>Hidden button description</span>
                <button type="button" aria-describedby="button-desc">Save profile</button>
              </form>
              <button type="button" aria-expanded="false" aria-controls="details-panel">Details</button>
              <div id="details-panel" hidden>Hidden details panel</div>
              <table>
                <caption>Order lines</caption>
                <tr><th id="product">Product</th><th id="price">Price</th></tr>
                <tr><td headers="product">Desk lamp</td><td headers="price">EUR 39</td></tr>
              </table>
              <a href="/docs">Docs link</a>
              <img alt="Planning board" width="20" height="20"
                   src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==">
              <video controls width="320" height="180"></video>
            </main>
          </body>
        </html>
        """,
        wait_until="domcontentloaded",
      )

      first = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
        depth=1,
        parent_state="state_0000",
        action_from_parent={
          "type": "click",
          "text": "Save profile",
          "candidate_region": "main",
        },
      )
      second = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
        depth=1,
        parent_state="state_0000",
        action_from_parent={"type": "click", "text": "Save profile"},
      )
    finally:
      await page.close()

    assert first["schema_version"] == ACCESSIBILITY_CONTEXT_SCHEMA_VERSION
    assert "focusable_elements" not in first
    assert first["state_context"] == {
      "depth": 1,
      "parent_state": "state_0000",
      "action_from_parent": {"type": "click", "text": "Save profile"},
    }
    assert first["page"]["html_lang"] == "en"
    assert first["page"]["document_lang"] == "en"
    assert first["page"]["page_lang"] == "en"
    assert first["page"]["body_lang"] is None
    assert len(first["page"]["body_text_sample"]) <= EXTRACTION_LIMITS["max_text_length"]
    assert first["extraction_metadata"]["status"] == "success"
    assert first["extraction_metadata"]["truncated"] is False
    assert first["extraction_metadata"]["limits"] == EXTRACTION_LIMITS

    button = _first_with_text(first["buttons"], "Save profile")
    second_button = _first_with_text(second["buttons"], "Save profile")
    assert button["element_id"] == second_button["element_id"]
    assert button["element_id"].startswith("e_")
    assert button["kind"] == "button"
    assert button["selector"] == "button:nth-of-type(1)"
    assert button["xpath"].startswith("/html[1]/body[1]")
    assert button["accessible_name"] == "Save profile"
    assert button["aria_describedby"] == "button-desc"
    assert button["bounding_box"]["width"] > 0
    assert button["computed_style"]["display"]
    assert button["structure"]["nearest_landmark"]["tag"] == "form"
    assert button["context"]["section_heading"] == "Evidence heading"
    assert len(button["raw_html"]) <= EXTRACTION_LIMITS["max_text_length"]

    assert any(item["reference_type"] == "aria-describedby" for item in first["referenced_elements"])
    assert any(item["text"] == "Hidden button description" for item in first["referenced_elements"])
    assert any(item["type"] == "describes" and item["method"] == "aria-describedby" for item in first["relationships"])
    assert any(item["type"] == "labels" and item["method"] == "for" for item in first["relationships"])
    assert any(control.get("label") == "Email address" for control in first["form_controls"])
    assert any(item.get("kind") == "form" for item in first["forms"])
    assert any(item.get("kind") == "video" for item in first["videos"])
    details_button = _first_with_text(first["buttons"], "Details")
    assert details_button["aria_expanded"] == "false"
    assert details_button["aria_controls"] == "details-panel"
    assert any(cue["cue_attributes"].get("aria_expanded") == "false" for cue in first["visual_cues"])
    table = first["tables"][0]
    assert table["caption"] == "Order lines"
    assert table["header_count"] == 2
    assert table["data_cells"][0]["headers_all_resolved"] is True
    assert table["data_cells"][0]["associated_headers"][0]["text"] == "Product"
    assert first["focusables"]
    assert first["focus_order"][0]["order"] == 1
    assert not _contains_forbidden_key(first)

  asyncio.run(_with_chromium(run))


def test_extract_accessibility_context_separates_page_and_local_language_scopes(tmp_path):
  async def run(browser):
    page = await browser.new_page()
    try:
      await page.set_content(
        """
        <!doctype html>
        <html lang="en">
          <head><title>Language scope fixture</title></head>
          <body lang="en">
            <main>
              <h1>Language evidence</h1>
              <p id="plain">sehr interessant ohne lokale Deklaration</p>
              <p>
                Mixed copy
                <span id="local-lang" lang="fr">sehr interessant</span>
              </p>
            </main>
          </body>
        </html>
        """,
        wait_until="domcontentloaded",
      )

      payload = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
      )
    finally:
      await page.close()

    assert payload["page"]["html_lang"] == "en"
    assert payload["page"]["body_lang"] == "en"
    assert payload["page"]["page_lang"] == "en"

    language_samples = payload["language_samples"]
    assert not any(sample.get("tag") in {"html", "body"} for sample in language_samples)
    assert any(
      sample.get("selector") == "span#local-lang"
      and sample.get("local_lang") == "fr"
      and sample.get("ancestor_lang") == ""
      and sample.get("effective_lang") == "fr"
      for sample in language_samples
    )
    assert any(
      sample.get("selector") == "p#plain"
      and sample.get("local_lang") == ""
      and sample.get("ancestor_lang") == ""
      and sample.get("effective_lang") == "en"
      for sample in language_samples
    )

  asyncio.run(_with_chromium(run))


def test_extract_accessibility_context_adds_heading_scope_until_next_same_or_higher_heading(tmp_path):
  async def run(browser):
    page = await browser.new_page()
    try:
      await page.set_content(
        """
        <!doctype html>
        <html lang="en">
          <head><title>Heading scope fixture</title></head>
          <body>
            <main>
              <h1>Checkout</h1>
              <p>Shipping address</p>
              <button type="button">Edit shipping</button>
              <h2>Payment details</h2>
              <p>Card ending 4242</p>
              <h1>Account</h1>
              <p>Should not appear in checkout scope</p>
            </main>
          </body>
        </html>
        """,
        wait_until="domcontentloaded",
      )

      payload = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
      )
    finally:
      await page.close()

    checkout = _first_with_text(payload["headings"], "Checkout")
    scope = checkout["heading_scope"]

    assert scope["schema_version"] == "heading_scope_v1"
    assert scope["strategy"] == "within_nearest_scope_root_until_next_same_or_higher_heading"
    assert scope["truncated"] is False
    assert "Shipping address" in scope["text_excerpt"]
    assert "Edit shipping" in scope["text_excerpt"]
    assert "Card ending 4242" in scope["text_excerpt"]
    assert "Should not appear" not in scope["text_excerpt"]
    assert scope["content_counts"]["paragraphs"] == 2
    assert scope["content_counts"]["buttons"] == 1
    assert scope["content_counts"]["sampled_items"] == 3
    assert scope["content_counts"]["omitted_items"] == 0

    items = scope["sampled_items"]
    assert [item["kind"] for item in items] == ["paragraph", "button", "paragraph"]
    assert items[0]["text"] == "Shipping address"
    assert items[1]["text"] == "Edit shipping"
    assert items[1]["tag"] == "button"
    assert items[1]["selector"]
    assert items[1]["element_id"].startswith("e_")

  asyncio.run(_with_chromium(run))


def test_heading_scope_skips_hidden_content(tmp_path):
  async def run(browser):
    page = await browser.new_page()
    try:
      await page.set_content(
        """
        <!doctype html>
        <html lang="en">
          <head><title>Hidden scope fixture</title></head>
          <body>
            <main>
              <h1>Visible scope</h1>
              <p>Visible scoped paragraph</p>
              <p hidden>Hidden attribute paragraph</p>
              <div aria-hidden="true">
                <p>Aria hidden paragraph</p>
              </div>
              <p style="display: none">Display hidden paragraph</p>
              <h1>Next scope</h1>
            </main>
          </body>
        </html>
        """,
        wait_until="domcontentloaded",
      )

      payload = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
      )
    finally:
      await page.close()

    scope = _first_with_text(payload["headings"], "Visible scope")["heading_scope"]
    serialized = json.dumps(scope)

    assert "Visible scoped paragraph" in scope["text_excerpt"]
    assert "Hidden attribute paragraph" not in serialized
    assert "Aria hidden paragraph" not in serialized
    assert "Display hidden paragraph" not in serialized
    assert scope["content_counts"]["paragraphs"] == 1
    assert [item["text"] for item in scope["sampled_items"]] == ["Visible scoped paragraph"]

  asyncio.run(_with_chromium(run))


def test_heading_scope_truncates_text_and_items(tmp_path):
  async def run(browser):
    page = await browser.new_page()
    try:
      paragraphs = "\n".join(
        f"<p>Scoped paragraph {index} {'long evidence text ' * 16}</p>"
        for index in range(12)
      )
      await page.set_content(
        f"""
        <!doctype html>
        <html lang="en">
          <head><title>Long scope fixture</title></head>
          <body>
            <main>
              <h1>Long scope</h1>
              {paragraphs}
              <h1>Next scope</h1>
            </main>
          </body>
        </html>
        """,
        wait_until="domcontentloaded",
      )

      payload = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
      )
    finally:
      await page.close()

    scope = _first_with_text(payload["headings"], "Long scope")["heading_scope"]

    assert scope["truncated"] is True
    assert len(scope["text_excerpt"]) <= EXTRACTION_LIMITS["max_text_length"]
    assert len(scope["sampled_items"]) == 8
    assert scope["content_counts"]["paragraphs"] == 12
    assert scope["content_counts"]["sampled_items"] == 8
    assert scope["content_counts"]["omitted_items"] == 4
    assert all(len(item["text"]) <= 160 for item in scope["sampled_items"])

  asyncio.run(_with_chromium(run))


def test_heading_scope_handles_empty_scope(tmp_path):
  async def run(browser):
    page = await browser.new_page()
    try:
      await page.set_content(
        """
        <!doctype html>
        <html lang="en">
          <head><title>Empty scope fixture</title></head>
          <body>
            <main>
              <h1>Empty scope</h1>
              <h1>Next scope</h1>
              <p>Belongs to next scope</p>
            </main>
          </body>
        </html>
        """,
        wait_until="domcontentloaded",
      )

      payload = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
      )
    finally:
      await page.close()

    scope = _first_with_text(payload["headings"], "Empty scope")["heading_scope"]

    assert scope["schema_version"] == "heading_scope_v1"
    assert scope["text_excerpt"] == ""
    assert scope["truncated"] is False
    assert scope["sampled_items"] == []
    assert scope["content_counts"]["sampled_items"] == 0
    assert scope["content_counts"]["omitted_items"] == 0

  asyncio.run(_with_chromium(run))


def test_heading_scope_has_no_judgment_fields(tmp_path):
  async def run(browser):
    page = await browser.new_page()
    try:
      await page.set_content(
        """
        <!doctype html>
        <html lang="en">
          <head><title>Neutral scope fixture</title></head>
          <body>
            <main>
              <h1>Neutral heading</h1>
              <p>Neutral scoped facts only</p>
            </main>
          </body>
        </html>
        """,
        wait_until="domcontentloaded",
      )

      payload = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
      )
    finally:
      await page.close()

    scope = _first_with_text(payload["headings"], "Neutral heading")["heading_scope"]

    assert not _contains_forbidden_key(scope)
    assert not _contains_disallowed_heading_scope_marker(scope)

  asyncio.run(_with_chromium(run))


def test_extract_accessibility_context_emits_relationships_without_form_value_leaks(tmp_path):
  async def run(browser):
    page = await browser.new_page()
    try:
      await page.set_content(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <title>Relationship evidence fixture</title>
            <style>.sr-only { position: absolute; width: 1px; height: 1px; clip: rect(0 0 0 0); }</style>
          </head>
          <body>
            <main>
              <h1>Relationship evidence</h1>
              <nav aria-label="Primary navigation">
                <form id="profile-form" aria-label="Profile form">
                  <label for="email">Email address</label>
                  <label for="email">Work email</label>
                  <span id="email-name" hidden>Hidden account email</span>
                  <span id="email-help" class="sr-only">Screen reader helper text</span>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    value="SENSITIVE-EMAIL-VALUE"
                    required
                    readonly
                    aria-labelledby="email-name"
                    aria-describedby="email-help"
                    aria-invalid="true"
                    autocomplete="email"
                    placeholder="name@example.com">
                  <label>
                    Preferred name
                    <input id="preferred" name="preferred" value="SENSITIVE-PREFERRED-VALUE">
                  </label>
                  <input id="empty-required" name="empty" required aria-label="Empty required field">
                  <button id="menu-button" type="button" aria-controls="panel" aria-owns="owned-panel" tabindex="3">
                    Open panel
                  </button>
                </form>
              </nav>
              <section id="panel" hidden><p>Controlled panel details</p></section>
              <div id="owned-panel" hidden><p>Owned panel details</p></div>
              <p id="hidden-noise" hidden>Do not collect this hidden noise</p>
              <video id="training-video" controls width="320" height="180">
                <track kind="captions" srclang="en" label="English captions" src="captions.vtt">
              </video>
              <section aria-label="Transcript">
                <h2>Transcript</h2>
                <p>Transcript text sample for the training video.</p>
              </section>
            </main>
          </body>
        </html>
        """,
        wait_until="domcontentloaded",
      )

      payload = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
      )
    finally:
      await page.close()

    serialized = json.dumps(payload)
    assert "SENSITIVE-EMAIL-VALUE" not in serialized
    assert "SENSITIVE-PREFERRED-VALUE" not in serialized
    assert "Do not collect this hidden noise" not in serialized
    assert not _contains_forbidden_key(payload)

    referenced_text = {item.get("text") for item in payload["referenced_elements"]}
    reference_types = {item.get("reference_type") for item in payload["referenced_elements"]}
    assert "Email address" in referenced_text
    assert "Work email" in referenced_text
    assert "Preferred name" in referenced_text
    assert "Hidden account email" in referenced_text
    assert "Screen reader helper text" in referenced_text
    assert "Controlled panel details" in referenced_text
    assert "Owned panel details" in referenced_text
    assert {"label[for]", "label-wrapper", "aria-labelledby", "aria-describedby", "aria-controls", "aria-owns"} <= reference_types

    relationships = payload["relationships"]
    assert sum(1 for item in relationships if item["type"] == "labels" and item["method"] == "for") >= 2
    assert any(item["type"] == "labels" and item["method"] == "wrapper" for item in relationships)
    assert any(item["type"] == "labelledby" and item["method"] == "aria-labelledby" for item in relationships)
    assert any(item["type"] == "describes" and item["method"] == "aria-describedby" for item in relationships)
    assert any(item["type"] == "controls" and item["method"] == "aria-controls" for item in relationships)
    assert any(item["type"] == "owns" and item["method"] == "aria-owns" for item in relationships)
    assert any(item["type"] == "form_contains" for item in relationships)
    assert any(item["type"] == "landmark_contains" for item in relationships)
    assert any(item["type"] == "heading_context" for item in relationships)

    controls_by_id = {control.get("id"): control for control in payload["form_controls"]}
    email = controls_by_id["email"]
    assert email["has_value"] is True
    assert email["text"] == ""
    assert email["required"] is True
    assert email["readonly"] is True
    assert email["aria_invalid"] == "true"
    assert email["invalid"] is True
    assert email["placeholder"] == "name@example.com"
    assert email["autocomplete"] == "email"
    assert email["parent_form"]["element_id"]
    assert email["raw_html"].find("value=") == -1

    empty_required = controls_by_id["empty-required"]
    assert empty_required["has_value"] is False
    assert empty_required["invalid"] is True
    assert empty_required["native_validity"]["value_missing"] is True

    focus_button = next(item for item in payload["focusables"] if item.get("text") == "Open panel")
    assert focus_button["tabindex_raw"] == "3"
    assert focus_button["tabindex_value"] == 3
    assert any(item["element_id"] == focus_button["element_id"] for item in payload["focus_order"])

    video = next(item for item in payload["videos"] if item.get("tag") == "video")
    assert video["controls"] is True
    assert video["autoplay"] is False
    assert video["muted"] is False
    assert video["loop"] is False
    assert len(video["tracks"]) == 1
    track = video["tracks"][0]
    assert track["element_id"]
    assert track["selector"] == "track:nth-of-type(1)"
    assert track["kind"] == "captions"
    assert track["srclang"] == "en"
    assert track["label"] == "English captions"
    assert track["src"] == "captions.vtt"
    assert track["default"] is False
    assert track["mode"] == "disabled"
    assert track["cue_count"] == 0
    assert track["cues"] == []
    assert track["cue_status"] in {"error", "timeout"}
    assert "Transcript text sample" in video["nearby_transcript_text"]

  asyncio.run(_with_chromium(run))


def test_extract_accessibility_context_loads_ordered_video_caption_cues_and_restores_modes(tmp_path):
  async def run(browser):
    page = await browser.new_page()

    async def route_fixture(route):
      url = route.request.url
      if url.endswith("/fixture"):
        await route.fulfill(
          content_type="text/html",
          body="""
            <!doctype html>
            <html lang="en">
              <head><title>Media evidence fixture</title></head>
              <body>
                <main>
                  <h1>Support</h1>
                  <section aria-labelledby="video-heading">
                    <h2 id="video-heading">Checkout walkthrough</h2>
                    <video id="walkthrough" aria-labelledby="video-heading" controls preload="metadata" muted>
                      <source src="/video.mp4" type="video/mp4">
                      <track id="english" kind="captions" srclang="en" label="English" src="/english.vtt" default>
                      <track id="french" kind="captions" srclang="fr" label="Francais" src="/french.vtt">
                    </video>
                  </section>
                </main>
              </body>
            </html>
          """,
        )
      elif url.endswith("/english.vtt"):
        await route.fulfill(
          content_type="text/vtt",
          body="WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nFirst cue.\n\n00:00:02.000 --> 00:00:03.500\nSecond cue.\n",
        )
      elif url.endswith("/french.vtt"):
        await route.fulfill(
          content_type="text/vtt",
          body="WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nPremier repere.\n",
        )
      else:
        await route.fulfill(status=200, content_type="video/mp4", body="")

    try:
      await page.route("https://media.test/**", route_fixture)
      await page.goto("https://media.test/fixture", wait_until="domcontentloaded")

      payload = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
      )

      video = payload["videos"][0]
      assert video["src"] == "https://media.test/video.mp4"
      assert video["current_src"] == "https://media.test/video.mp4"
      assert video["source_src"] == ""
      assert video["sources"] == [
        {
          "src": "/video.mp4",
          "current_src": "https://media.test/video.mp4",
          "type": "video/mp4",
          "media": "",
        }
      ]
      assert video["controls"] is True
      assert video["preload"] == "metadata"
      assert video["muted"] is True
      assert video["bounding_box"]["width"] > 0
      assert video["context"]["section_heading"] == "Checkout walkthrough"

      tracks = {track["srclang"]: track for track in video["tracks"]}
      english = tracks["en"]
      assert english["default"] is True
      assert english["mode"] == "showing"
      assert english["ready_state"] == "loaded"
      assert english["cue_status"] == "loaded"
      assert english["cue_count"] == 2
      assert english["cues_truncated"] is False
      assert english["cues"] == [
        {"index": 0, "start_time": 0, "end_time": 1.5, "text": "First cue."},
        {"index": 1, "start_time": 2, "end_time": 3.5, "text": "Second cue."},
      ]

      french = tracks["fr"]
      assert french["default"] is False
      assert french["mode"] == "disabled"
      assert french["ready_state"] == "loaded"
      assert french["cues"] == [
        {"index": 0, "start_time": 0, "end_time": 1.5, "text": "Premier repere."}
      ]
      restored_modes = await page.locator("track").evaluate_all(
        "tracks => tracks.map(track => track.track.mode)"
      )
      assert restored_modes == ["showing", "disabled"]
    finally:
      await page.close()

  asyncio.run(_with_chromium(run))


def test_extract_accessibility_context_preserves_label_text_segments(tmp_path):
  async def run(browser):
    page = await browser.new_page()
    try:
      await page.set_content(
        """
        <!doctype html>
        <html lang="en">
          <head><title>Label segment evidence</title></head>
          <body>
            <main>
              <h1>Label segments</h1>
              <form>
                <label for="adjacent"><span>State</span><span>Required</span></label>
                <input id="adjacent" name="adjacent" required>

                <label for="spaced"><span>State</span> <span>Required</span></label>
                <input id="spaced" name="spaced" required>

                <label for="direct">State <span>Required</span></label>
                <input id="direct" name="direct" required>

                <label for="uppercase"><span>State</span><span>REQUIRED</span></label>
                <input id="uppercase" name="uppercase" required>

                <label for="country"><span>Country/region</span><span>Required</span></label>
                <select id="country" name="country" autocomplete="country-name" required>
                  <option>United States</option>
                  <option>Canada</option>
                  <option>Germany</option>
                </select>
              </form>
            </main>
          </body>
        </html>
        """,
        wait_until="domcontentloaded",
      )

      payload = await extract_accessibility_context(
        page,
        state_id="state_0000",
        screenshot_path=tmp_path / "screenshot.png",
      )
    finally:
      await page.close()

    controls_by_id = {
      control["id"]: control
      for control in payload["form_controls"]
    }
    references_by_id = {
      reference["element_id"]: reference
      for reference in payload["referenced_elements"]
    }

    def label_reference(control_id):
      target_id = controls_by_id[control_id]["element_id"]
      relationship = next(
        item
        for item in payload["relationships"]
        if item["type"] == "labels"
        and item["method"] == "for"
        and item["to_element_id"] == target_id
      )
      return references_by_id[relationship["from_element_id"]]

    assert label_reference("adjacent")["text_segments"] == ["State", "Required"]
    assert label_reference("spaced")["text_segments"] == ["State", "Required"]
    assert label_reference("direct")["text_segments"] == ["State", "Required"]
    assert label_reference("uppercase")["text_segments"] == ["State", "REQUIRED"]
    assert label_reference("country")["text_segments"] == [
      "Country/region",
      "Required",
    ]

    assert label_reference("adjacent")["text"] == "StateRequired"
    assert label_reference("spaced")["text"] == "State Required"

  asyncio.run(_with_chromium(run))
