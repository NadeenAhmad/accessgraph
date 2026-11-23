import asyncio
import json

from PIL import Image

try:
  from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
  PlaywrightTimeoutError = TimeoutError

from src.crawler.state.state_extractor import capture_state_artifacts


class FakeLocator:
  async def aria_snapshot(self) -> str:
    return "body: root"


class FailingAriaLocator:
  async def aria_snapshot(self) -> str:
    raise RuntimeError("ARIA snapshot failed")


class FakePage:
  def __init__(self, *, fail_full_page: bool = False):
    self.url = "https://example.com/docs"
    self.viewport_size = {"width": 1280, "height": 720}
    self._fail_full_page = fail_full_page
    self.screenshot_calls: list[bool] = []

  async def content(self) -> str:
    return "<html><body><main>docs</main></body></html>"

  async def title(self) -> str:
    return "Docs"

  async def screenshot(self, *, path: str, full_page: bool) -> None:
    self.screenshot_calls.append(full_page)
    if full_page and self._fail_full_page:
      raise PlaywrightTimeoutError("full page screenshot timed out")
    size = (1280, 900) if full_page else (1280, 720)
    Image.new("RGB", size, color=(255, 255, 255)).save(path, format="PNG")

  async def evaluate(self, _script: str, args: dict | None = None) -> dict:
    if args is not None:
      raise TypeError("FakePage does not support evidence extraction")
    return {
      "marker": "accessgraph_coordinate_space_v1",
      "viewport": {"width": 1280, "height": 720, "client_width": 1280, "client_height": 720},
      "device_pixel_ratio": 1,
      "scroll_offset": {"x": 0, "y": 0},
      "document": {"scroll_width": 1280, "scroll_height": 900},
    }

  def locator(self, _selector: str) -> FakeLocator:
    return FakeLocator()


class FakeAriaFailurePage(FakePage):
  def locator(self, _selector: str) -> FailingAriaLocator:
    return FailingAriaLocator()


class FakeEvidencePage(FakePage):
  async def evaluate(self, _script: str, args: dict | None = None) -> dict:
    if args is None:
      return await super().evaluate(_script)
    return {
      "schema_version": args["schemaVersion"],
      "state_id": args["stateId"],
      "state_context": args["stateContext"],
      "page": {
        "url": self.url,
        "title": "Docs",
        "document_lang": "en",
        "html_lang": "en",
        "body_text_sample": "docs",
        "body_text_length": 4,
      },
      "referenced_elements": [],
      "images": [],
      "videos": [],
      "links": [],
      "buttons": [],
      "forms": [],
      "form_controls": [],
      "headings": [],
      "landmarks": [],
      "focusables": [],
      "focus_order": [],
      "relationships": [],
      "extraction_metadata": {
        "status": "success",
        "screenshot_path": args["screenshotPath"],
        "truncated": False,
        "truncation": {},
        "limits": args["limits"],
      },
    }


def test_capture_state_artifacts_falls_back_to_viewport_screenshot(tmp_path):
  page = FakePage(fail_full_page=True)

  artifact = asyncio.run(
    capture_state_artifacts(
      page,
      tmp_path,
      state_id="state_0000",
      enable_tile_screenshots=False,
    )
  )

  metadata = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
  assert page.screenshot_calls == [True, False]
  assert artifact.screenshot_path.exists()
  assert metadata["screenshot_mode"] == "viewport_fallback"
  assert artifact.html_path.name == "dom.html"
  assert artifact.screenshot_path.name == "screenshot.png"
  assert artifact.metadata_path.name == "metadata.json"
  assert artifact.accessibility_context_path.name == "accessibility_context.json"
  assert metadata["accessibility_context"] == "accessibility_context.json"
  assert metadata["aria_snapshot"] == {
    "status": "ok",
    "path": "aria_snapshot.json",
  }
  assert artifact.aria_snapshot_path.exists()
  assert metadata["depth"] == 0
  assert metadata["parent_state"] is None
  assert metadata["action_from_parent"] is None
  assert metadata["html_hash"] == artifact.html_hash
  assert metadata["dom_identity_hash"] == artifact.dom_identity_hash
  assert metadata["coordinate_space"]["schema_version"] == "coordinate_space_v1"
  assert metadata["coordinate_space"]["bounding_boxes"] == {
    "units": "css_pixels",
    "origin": "viewport",
    "source": "Element.getBoundingClientRect",
    "captured_with": "accessibility_context",
  }
  assert metadata["coordinate_space"]["screenshot"]["mode"] == "viewport_fallback"
  assert metadata["coordinate_space"]["screenshot"]["image"]["width"] == 1280
  assert metadata["coordinate_space"]["screenshot"]["image"]["height"] == 720
  assert metadata["coordinate_space"]["evidence_capture"]["device_pixel_ratio"] == 1
  assert metadata["coordinate_space"]["evidence_capture"]["viewport"]["width"] == 1280
  assert "dom_hash" not in metadata
  assert "restore_hash" not in metadata
  evidence = json.loads(artifact.accessibility_context_path.read_text(encoding="utf-8"))
  assert evidence["extraction_metadata"]["status"] == "failed"
  assert evidence["state_id"] == "state_0000"
  assert evidence["images"] == []


def test_capture_state_artifacts_records_successful_aria_snapshot(tmp_path):
  page = FakePage()

  artifact = asyncio.run(
    capture_state_artifacts(
      page,
      tmp_path,
      state_id="state_0000",
      enable_tile_screenshots=False,
    )
  )

  metadata = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
  aria_snapshot = json.loads(artifact.aria_snapshot_path.read_text(encoding="utf-8"))
  assert metadata["aria_snapshot"] == {
    "status": "ok",
    "path": "aria_snapshot.json",
  }
  assert artifact.aria_snapshot_path.exists()
  assert aria_snapshot == {"raw": "body: root"}
  assert artifact.html_path.exists()
  assert artifact.screenshot_path.exists()
  assert artifact.metadata_path.exists()
  assert artifact.accessibility_context_path.exists()


def test_capture_state_artifacts_records_aria_snapshot_error_without_failing(tmp_path):
  page = FakeAriaFailurePage()

  artifact = asyncio.run(
    capture_state_artifacts(
      page,
      tmp_path,
      state_id="state_0000",
      enable_tile_screenshots=False,
    )
  )

  metadata = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
  assert metadata["aria_snapshot"] == {
    "status": "error",
    "path": None,
    "error": {
      "type": "RuntimeError",
      "message": "ARIA snapshot failed",
    },
  }
  assert not artifact.aria_snapshot_path.exists()
  assert artifact.html_path.exists()
  assert artifact.screenshot_path.exists()
  assert artifact.metadata_path.exists()
  assert artifact.accessibility_context_path.exists()


def test_capture_state_artifacts_writes_accessibility_context(tmp_path):
  page = FakeEvidencePage()

  artifact = asyncio.run(
    capture_state_artifacts(
      page,
      tmp_path,
      state_id="state_0000",
      enable_tile_screenshots=False,
    )
  )

  evidence = json.loads(artifact.accessibility_context_path.read_text(encoding="utf-8"))
  assert artifact.accessibility_context_path.name == "accessibility_context.json"
  assert evidence["schema_version"] == "1"
  assert evidence["extraction_metadata"]["status"] == "success"
  assert evidence["state_context"]["depth"] == 0
  assert evidence["state_context"]["parent_state"] is None
  assert evidence["state_context"]["action_from_parent"] is None
  for category in (
    "referenced_elements",
    "images",
    "videos",
    "links",
    "buttons",
    "forms",
    "form_controls",
    "headings",
    "landmarks",
    "tables",
    "focusables",
    "focus_order",
    "relationships",
  ):
    assert category in evidence
    assert isinstance(evidence[category], list)
  assert evidence["page"]["body_text_sample"] == "docs"
  assert "violation_target" not in evidence
  assert "candidate_id" not in evidence
  assert "precheck" not in evidence
