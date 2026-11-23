from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from src.analysis.confirmation.image_inputs import load_confirmation_image_inputs
from src.analysis.confirmation.models import ConfirmationConfig, ReviewBundle
from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation


class _FakeResponse:
  def __init__(self, payload: dict[str, object]):
    self.payload = payload

  def read(self) -> bytes:
    return json.dumps(self.payload).encode("utf-8")

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc, tb) -> bool:
    return False


def _ollama_payload(content: str) -> dict[str, object]:
  return {
    "message": {
      "role": "assistant",
      "content": content,
    },
    "done": True,
  }


def _write_png(path: Path, *, size: tuple[int, int] = (240, 160)) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  image = Image.new("RGB", size, "white")
  image.save(path)


def _candidate_record(
  *,
  candidate_id: str = "cand_image",
  candidate_type: str = "image-alt-not-descriptive",
  state_id: str = "state_0001",
  include_bounding_box: bool = True,
) -> dict[str, object]:
  evidence: dict[str, object] = {
    "primary": {
      "image": {
        "element_id": "img-1",
        "selector": "img.hero",
        "alt": "Calendar reminder illustration",
        "accessible_name": "Calendar reminder illustration",
      }
    },
    "supporting": {
      "context": {
        "nearby_text": "Completed tasks",
        "section_heading": "Completed tasks",
      }
    },
  }
  if include_bounding_box:
    evidence["bounding_boxes"] = [
      {
        "element_id": "img-1",
        "selector": "img.hero",
        "bounding_box": {
          "x": 80,
          "y": 48,
          "width": 40,
          "height": 32,
        },
      }
    ]
  return {
    "schema_version": "1",
    "candidate_id": candidate_id,
    "candidate_type": candidate_type,
    "state_id": state_id,
    "element_refs": [{"bucket": "images", "element_id": "img-1", "selector": "img.hero"}],
    "primary_element_ref": {"bucket": "images", "element_id": "img-1", "selector": "img.hero"},
    "selection_reason": ["visible_image_with_name_and_context_evidence"],
    "required_context": ["visual image context", "nearby text context", "image purpose"],
    "evidence": evidence,
    "state_context": {"url": "https://example.test/tasks/completed", "title": "Completed tasks"},
    "graph_context": {"transition_path": []},
    "artifact_refs": {
      "screenshot": f"states/{state_id}/screenshot.png",
      "accessibility_context": f"states/{state_id}/accessibility_context.json",
    },
    "generator": {"name": "offline_semantic_candidate_builder", "version": "1"},
  }


def _write_candidates(run_dir: Path, records: list[dict[str, object]]) -> None:
  candidate_dir = run_dir / "candidates"
  candidate_dir.mkdir(parents=True)
  with (candidate_dir / "candidates.jsonl").open("w", encoding="utf-8") as handle:
    for record in records:
      handle.write(json.dumps(record) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
  return [
    json.loads(line)
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip()
  ]


def _valid_confirmation_content(record: dict[str, object]) -> str:
  return json.dumps(
    {
      "candidate_id": record["candidate_id"],
      "candidate_type": record["candidate_type"],
      "state_id": record["state_id"],
      "decision": "uncertain",
      "confidence": 0.61,
      "reason": "Fake local vision response for visual-context traceability.",
      "supporting_evidence": ["candidate visual context"],
    }
  )


def _bundle_with_visual_context(run_dir: Path, artifact_refs: dict[str, object]) -> ReviewBundle:
  record = _candidate_record()
  record["artifact_refs"] = artifact_refs
  return ReviewBundle(
    run_dir=run_dir,
    source_path=run_dir / "candidates" / "candidates.jsonl",
    source_line_number=1,
    record=record,
    candidate_id=record["candidate_id"],
    candidate_type=record["candidate_type"],
    state_id=record["state_id"],
    element_refs=tuple(record["element_refs"]),
    primary_element_ref=record["primary_element_ref"],
    selection_reason=tuple(record["selection_reason"]),
    required_context=tuple(record["required_context"]),
    evidence=record["evidence"],
    state_context=record["state_context"],
    graph_context=record["graph_context"],
    artifact_refs=artifact_refs,
    generator=record["generator"],
  )


def test_confirmation_generates_visual_context_for_image_alt_candidate(tmp_path):
  screenshot_path = tmp_path / "states" / "state_0001" / "screenshot.png"
  _write_png(screenshot_path)
  _write_candidates(tmp_path, [_candidate_record()])

  run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="visual-context-run",
      candidate_ids=("cand_image",),
    ),
  )

  output_dir = tmp_path / "confirmations" / "visual-context-run"
  visual_dir = output_dir / "visual_context" / "cand_image"
  manifest = json.loads((visual_dir / "manifest.json").read_text(encoding="utf-8"))
  confirmation = _read_jsonl(output_dir / "confirmations.jsonl")[0]
  prompt_payload = json.loads(next((output_dir / "prompts").glob("*.json")).read_text(encoding="utf-8"))

  assert (visual_dir / "target_crop.png").is_file()
  assert (visual_dir / "highlighted_state.png").is_file()
  assert manifest["candidate_id"] == "cand_image"
  assert manifest["candidate_type"] == "image-alt-not-descriptive"
  assert manifest["state_id"] == "state_0001"
  assert manifest["source_screenshot"] == "states/state_0001/screenshot.png"
  assert manifest["bounding_box"] == {"height": 32.0, "width": 40.0, "x": 80.0, "y": 48.0}
  assert manifest["target_crop"] == "visual_context/cand_image/target_crop.png"
  assert manifest["highlighted_state"] == "visual_context/cand_image/highlighted_state.png"

  crop_size = Image.open(visual_dir / "target_crop.png").size
  assert crop_size[0] > 40
  assert crop_size[1] > 32
  assert confirmation["artifact_refs"]["visual_context"]["target_crop"].endswith(
    "confirmations/visual-context-run/visual_context/cand_image/target_crop.png"
  )
  assert '"visual_context"' in prompt_payload["user_prompt"]


def test_confirmation_image_inputs_prefer_candidate_visual_context(tmp_path):
  _write_png(tmp_path / "states" / "state_0001" / "screenshot.png", size=(240, 160))
  _write_png(
    tmp_path
    / "confirmations"
    / "visual-context-run"
    / "visual_context"
    / "cand_image"
    / "target_crop.png",
    size=(96, 88),
  )
  _write_png(
    tmp_path
    / "confirmations"
    / "visual-context-run"
    / "visual_context"
    / "cand_image"
    / "highlighted_state.png",
    size=(240, 160),
  )
  bundle = _bundle_with_visual_context(
    tmp_path,
    {
      "screenshot": "states/state_0001/screenshot.png",
      "visual_context": {
        "target_crop": (
          "confirmations/visual-context-run/visual_context/cand_image/target_crop.png"
        ),
        "highlighted_state": (
          "confirmations/visual-context-run/visual_context/cand_image/highlighted_state.png"
        ),
      },
    },
  )

  image_inputs = load_confirmation_image_inputs(bundle)

  assert [item.image_source for item in image_inputs] == [
    "candidate_target_crop",
    "candidate_highlighted_state",
  ]
  assert image_inputs[0].relative_path.endswith("target_crop.png")
  assert image_inputs[1].relative_path.endswith("highlighted_state.png")


def test_confirmation_visual_context_falls_back_when_bbox_missing(tmp_path):
  _write_png(tmp_path / "states" / "state_0001" / "screenshot.png")
  _write_candidates(tmp_path, [_candidate_record(include_bounding_box=False)])

  run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="no-bbox-run",
      candidate_ids=("cand_image",),
    ),
  )

  output_dir = tmp_path / "confirmations" / "no-bbox-run"
  confirmation = _read_jsonl(output_dir / "confirmations.jsonl")[0]

  assert not (output_dir / "visual_context").exists()
  assert "visual_context" not in confirmation["artifact_refs"]


def test_ollama_vision_record_preserves_selected_candidate_crop(monkeypatch, tmp_path):
  _write_png(tmp_path / "states" / "state_0001" / "screenshot.png")
  record = _candidate_record()
  _write_candidates(tmp_path, [record])

  def fake_urlopen(req, timeout):
    return _FakeResponse(_ollama_payload(_valid_confirmation_content(record)))

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.ollama.urllib_request.urlopen",
    fake_urlopen,
  )

  run_confirmation(
    config=ConfirmationConfig(
      provider="ollama-vision",
      model="qwen2.5vl:7b",
      prompt_version="confirm_v4_1_vision",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="vision-visual-context-run",
      candidate_ids=("cand_image",),
    ),
  )

  output_dir = tmp_path / "confirmations" / "vision-visual-context-run"
  confirmation = _read_jsonl(output_dir / "confirmations.jsonl")[0]

  assert confirmation["image_source"] == "candidate_target_crop"
  assert [item["image_source"] for item in confirmation["image_inputs"]] == ["candidate_target_crop"]
  assert confirmation["image_input"] == confirmation["image_inputs"][0]
  assert confirmation["image_inputs"][0]["image_path"].endswith("target_crop.png")
  assert confirmation["artifact_refs"]["visual_context"]["target_crop"].endswith("target_crop.png")


def test_ollama_vision_client_error_preserves_selected_candidate_crop(monkeypatch, tmp_path):
  _write_png(tmp_path / "states" / "state_0001" / "screenshot.png")
  _write_candidates(tmp_path, [_candidate_record()])

  def fake_post_ollama_json(**kwargs):
    raise RuntimeError("local vision model context limit")

  monkeypatch.setattr(
    "src.analysis.confirmation.providers.ollama_vision.post_ollama_json",
    fake_post_ollama_json,
  )

  run_confirmation(
    config=ConfirmationConfig(
      provider="ollama-vision",
      model="qwen2.5vl:7b",
      prompt_version="confirm_v4_1_vision",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="vision-client-error-run",
      candidate_ids=("cand_image",),
    ),
  )

  output_dir = tmp_path / "confirmations" / "vision-client-error-run"
  confirmation = _read_jsonl(output_dir / "confirmations.jsonl")[0]

  assert confirmation["decision"] == "uncertain"
  assert confirmation["parse_status"] == "client_error"
  assert confirmation["image_source"] == "candidate_target_crop"
  assert [item["image_source"] for item in confirmation["image_inputs"]] == ["candidate_target_crop"]
  assert confirmation["image_input"] == confirmation["image_inputs"][0]
  assert confirmation["image_inputs"][0]["image_path"].endswith("target_crop.png")


def test_confirmation_visual_context_is_not_generated_for_non_image_candidates(tmp_path):
  _write_png(tmp_path / "states" / "state_0001" / "screenshot.png")
  _write_candidates(
    tmp_path,
    [
      _candidate_record(
        candidate_id="cand_button",
        candidate_type="button-label-mismatch",
      )
    ],
  )

  run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="button-run",
      candidate_ids=("cand_button",),
    ),
  )

  output_dir = tmp_path / "confirmations" / "button-run"
  confirmation = _read_jsonl(output_dir / "confirmations.jsonl")[0]

  assert not (output_dir / "visual_context").exists()
  assert "visual_context" not in confirmation["artifact_refs"]
